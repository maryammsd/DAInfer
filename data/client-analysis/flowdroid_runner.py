"""
FlowDroid Runner
================
Runs FlowDroid taint analysis on APKs under FOUR specification modes,
each corresponding to a different XML summary folder:

  Mode            summarydir arg          sources/sinks
  ─────────────────────────────────────────────────────────────────
  custom          ./custom_summaries/     config/SourcesAndSinks.txt
  stubdroid       ./stubs/               config/SourcesAndSinks.txt
  manual          ./manualsummaries/     config/SourcesAndSinks.txt
  nosummary       (none)                 config/SourcesAndSinks.txt

All four modes share the same SourcesAndSinks.txt so that the only
variable between runs is which set of XML summaries FlowDroid uses
to model library-internal taint propagation.

Safety gates (applied before FlowDroid launches):
  1. APK file-size gate
  2. DEX class-count gate
  3. Wall-clock timeout
  4. JVM heap cap
"""

import os
import re
import json
import time
import shutil
import logging
import subprocess
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ── Logging ───────────────────────────────────────────────────────────────────
Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/flowdroid_runner.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────
FLOWDROID_JAR     = Path("flowdroid/soot-infoflow-cmd.jar")
ANDROID_PLATFORMS = Path(os.environ.get("ANDROID_HOME", "/opt/android-sdk")) / "platforms"
RESULTS_DIR       = Path("results")
LOGS_DIR          = Path("logs")

# Shared sources/sinks declaration used by ALL four modes.
SOURCES_SINKS     = Path("config/SourcesAndSinks.txt")

# Default summary folder paths (all overridable via env vars or CLI)
_DEFAULT_DIRS = {
    "custom":    Path(os.environ.get("CUSTOM_SUMMARIES",   "custom_summaries")),
    "stubdroid": Path(os.environ.get("STUBDROID_SUMMARIES","stubs")),
    "manual":    Path(os.environ.get("MANUAL_SUMMARIES",   "manualsummaries")),
    # "nosummary" intentionally has no folder
}

# ── Thresholds ────────────────────────────────────────────────────────────────
MAX_APK_SIZE_MB    = 80
MAX_DEX_CLASSES    = 15_000
ANALYSIS_TIMEOUT_S = 600
JVM_MAX_HEAP       = "4g"

# ── Output parsing ────────────────────────────────────────────────────────────
RE_FOUND_LEAKS = re.compile(r"Found\s+(\d+)\s+(?:taint|leak|flow)", re.IGNORECASE)
RE_PATHS_FOUND = re.compile(r"(\d+)\s+path(?:s)?\s+found",           re.IGNORECASE)
RE_CONNECTED   = re.compile(r"(\d+)\s+connected",                     re.IGNORECASE)
RE_SOURCES     = re.compile(r"(\d+)\s+source",                        re.IGNORECASE)
RE_FOUND_LEAKS2 = re.compile(r"Found\s+(\d+)\s+leaks?", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# Spec modes
# ─────────────────────────────────────────────────────────────────────────────

class SpecMode(str, Enum):
    CUSTOM     = "custom"       # your inferred XML summaries
    STUBDROID  = "stubdroid"    # Stubdroid official XML summaries
    MANUAL     = "manual"       # your manual XML summaries
    NOSUMMARY  = "nosummary"    # no --summarydir at all (baseline)


# Human-readable labels used in plots
MODE_LABELS = {
    SpecMode.CUSTOM:    "Custom (inferred)",
    SpecMode.STUBDROID: "Stubdroid",
    SpecMode.MANUAL:    "Manual summaries",
    SpecMode.NOSUMMARY: "No summaries (baseline)",
}

# Colour palette for plots (colour-blind friendly)
MODE_COLORS = {
    SpecMode.CUSTOM:    "#2196F3",   # blue
    SpecMode.STUBDROID: "#4CAF50",   # green
    SpecMode.MANUAL:    "#FF9800",   # orange
    SpecMode.NOSUMMARY: "#9C27B0",   # purple
}


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    apk_path:          str
    package_name:      str
    spec_mode:         str
    success:           bool
    skipped:           bool  = False
    skip_reason:       str   = ""
    taints_found:      int   = 0
    sources_found:     int   = 0
    elapsed_sec:       float = 0.0
    summary_dir_used:  str   = ""
    summary_xml_count: int   = 0
    stdout_excerpt:    str   = ""
    stderr_excerpt:    str   = ""
    error:             str   = ""
    extra:             dict  = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def apk_size_mb(apk: Path) -> float:
    return apk.stat().st_size / (1024 * 1024)


def count_dex_classes(apk: Path) -> int:
    dexdump = shutil.which("dexdump")
    if dexdump:
        try:
            out = subprocess.check_output(
                [dexdump, "-l", "xml", str(apk)],
                timeout=30, stderr=subprocess.DEVNULL,
            ).decode(errors="replace")
            return out.count("<class ")
        except Exception:
            pass
    zipinfo = shutil.which("zipinfo")
    if zipinfo:
        try:
            out = subprocess.check_output(
                [zipinfo, str(apk)], timeout=15, stderr=subprocess.DEVNULL,
            ).decode(errors="replace")
            return out.count("classes") * 400
        except Exception:
            pass
    return 0


def find_android_jar(platforms_dir: Path) -> Optional[Path]:
    # Return the platforms root dir itself — FlowDroid auto-picks
    # the correct android-XX/android.jar based on the APK's targetSdk
    jars = sorted(platforms_dir.glob("android-*/android.jar"), reverse=True)
    if not jars:
        return None
    return jars[0].parent.parent   # .../platforms/android-34/android.jar
                                   # → .parent       = .../platforms/android-34
                                   # → .parent.parent = .../platforms   ✓


def count_xml_summaries(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(1 for _ in folder.rglob("*.xml"))


def parse_taints(stdout: str) -> tuple[int, int]:
    taints = 0
    for pat in (RE_FOUND_LEAKS, RE_FOUND_LEAKS2, RE_PATHS_FOUND, RE_CONNECTED):
        m = pat.search(stdout)
        if m:
            taints = max(taints, int(m.group(1)))
    sources = 0
    m = RE_SOURCES.search(stdout)
    if m:
        sources = int(m.group(1))
    return taints, sources


# ─────────────────────────────────────────────────────────────────────────────
# Command builder
# ─────────────────────────────────────────────────────────────────────────────
def _build_cmd(
    apk: Path,
    android_jar: Path,
    spec_mode: SpecMode,
    out_xml: Path,
    summary_dirs: dict[str, Path],
) -> tuple[list[str], str, int]:
    """
    Build the FlowDroid command for the given mode.

    FlowDroid's correct flags for Stubdroid summaries are:
      -tw STUBDROID          use the Stubdroid taint wrapper
      -t  <summaries_dir>    path to the XML summaries folder

    For nosummary mode we use -tw EASY (the simple default wrapper).

    Returns (cmd_list, summary_dir_used, xml_file_count).
    """
    cmd = [
        "java", f"-Xmx{JVM_MAX_HEAP}",
        "-jar", str(FLOWDROID_JAR),
        "-a",   str(apk),
        "-p",   str(android_jar),
        "-o",   str(out_xml),
        "-l",   "ALL",
    ]

    # Attach shared sources/sinks (same file for all modes)
    if SOURCES_SINKS.exists():
        cmd += ["-s", str(SOURCES_SINKS)]
    else:
        log.warning(f"SourcesAndSinks.txt not found at {SOURCES_SINKS} — "
                    "running without explicit source/sink list")

    summary_dir = ""
    xml_count   = 0

    if spec_mode == SpecMode.NOSUMMARY:
        # Baseline: simple easy taint wrapper, no summaries
        cmd += ["-tw", "None"]
        log.info(f"  [nosummary] -tw None  (baseline, no summaries)")
        return cmd, summary_dir, xml_count

    # For custom / stubdroid / manual: use Stubdroid taint wrapper
    # pointed at the appropriate XML summaries folder
    folder = summary_dirs.get(spec_mode.value)
    if folder is None:
        log.error(f"  [{spec_mode.value}] No summary folder configured")
        cmd += ["-tw", "EASY"]
        return cmd, summary_dir, xml_count

    n = count_xml_summaries(folder)
    if n > 0:
        cmd += ["-tw", "STUBDROID", "-t", str(folder)]
        summary_dir = str(folder)
        xml_count   = n
        log.info(f"  [{spec_mode.value}] -tw STUBDROID -t {folder}  ({n} XML files)")
    else:
        log.warning(
            f"  [{spec_mode.value}] No .xml files found in '{folder}' — "
            f"falling back to -tw EASY"
        )
        cmd += ["-tw", "EASY"]

    return cmd, summary_dir, xml_count


# ─────────────────────────────────────────────────────────────────────────────
# Single-APK runner
# ─────────────────────────────────────────────────────────────────────────────

def run_flowdroid(
    apk: Path,
    spec_mode: SpecMode,
    summary_dirs: dict[str, Path],
    package_name: str = "",
) -> AnalysisResult:
    """Run FlowDroid on one APK under one spec mode."""

    pkg = package_name or apk.stem
    result = AnalysisResult(
        apk_path=str(apk),
        package_name=pkg,
        spec_mode=spec_mode.value,
        success=False,
    )

    # Gate 1: APK size
    size = apk_size_mb(apk)
    if size > MAX_APK_SIZE_MB:
        result.skipped     = True
        result.skip_reason = f"APK too large ({size:.1f} MB > {MAX_APK_SIZE_MB} MB)"
        log.info(f"[SKIP] {pkg} [{spec_mode.value}]: {result.skip_reason}")
        return result

    # Gate 2: DEX class count
    cls = count_dex_classes(apk)
    if cls and cls > MAX_DEX_CLASSES:
        result.skipped     = True
        result.skip_reason = f"Too many DEX classes ({cls:,} > {MAX_DEX_CLASSES:,})"
        log.info(f"[SKIP] {pkg} [{spec_mode.value}]: {result.skip_reason}")
        return result

    # Gate 3: FlowDroid JAR
    if not FLOWDROID_JAR.exists():
        result.skipped     = True
        result.skip_reason = f"FlowDroid JAR not found at {FLOWDROID_JAR}"
        log.warning(f"[SKIP] {pkg}: {result.skip_reason}")
        return result

    # Gate 4: android.jar
    android_jar = find_android_jar(ANDROID_PLATFORMS)
    if not android_jar:
        result.skipped     = True
        result.skip_reason = f"No android platforms found under {ANDROID_PLATFORMS}"
        log.warning(f"[SKIP] {pkg}: {result.skip_reason}")
        return result

    # Build command
    out_xml = RESULTS_DIR / spec_mode.value / f"{pkg}.xml"
    out_xml.parent.mkdir(parents=True, exist_ok=True)

    cmd, summary_dir, xml_count = _build_cmd(
        apk, android_jar, spec_mode, out_xml, summary_dirs
    )
    result.summary_dir_used  = summary_dir
    result.summary_xml_count = xml_count

    log.info(
        f"[RUN] {pkg}  mode={spec_mode.value}  "
        f"summaries={xml_count}  timeout={ANALYSIS_TIMEOUT_S}s"
    )

    # Execute
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=ANALYSIS_TIMEOUT_S,
        )
        elapsed = time.time() - t0

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        log_file = LOGS_DIR / spec_mode.value / f"{pkg}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(
            f"CMD: {' '.join(cmd)}\n\n=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}"
        )

        #taints, sources = parse_taints(stdout)
        taints, sources = parse_taints(stdout + stderr)
        result.success        = (proc.returncode == 0)
        result.elapsed_sec    = round(elapsed, 2)
        result.taints_found   = taints
        result.sources_found  = sources
        result.stdout_excerpt = stdout[-2000:]
        result.stderr_excerpt = stderr[-1000:]
        if not result.success:
            result.error = f"Exit code {proc.returncode}"

        # Write detailed taint flow analysis log
        _write_flow_log(pkg, spec_mode, stderr, taints, sources, summary_dir)

        log.info(
            f"[{'OK' if result.success else 'ERR'}] {pkg}  "
            f"mode={spec_mode.value}  taints={taints}  elapsed={elapsed:.1f}s"
        )

    except subprocess.TimeoutExpired:
        elapsed            = time.time() - t0
        result.elapsed_sec = round(elapsed, 2)
        result.skipped     = True
        result.skip_reason = f"Timeout after {ANALYSIS_TIMEOUT_S}s"
        result.error       = "TIMEOUT"
        log.warning(f"[TIMEOUT] {pkg} [{spec_mode.value}] after {elapsed:.0f}s")

    except Exception as e:
        result.error = str(e)
        log.error(f"[ERROR] {pkg} [{spec_mode.value}]: {e}")

    return result

def _write_flow_log(
    pkg: str,
    spec_mode: SpecMode,
    stderr: str,
    taints_found: int,
    sources_found: int,
    summary_dir: str,
):
    """
    Write a human-readable taint flow log for a single APK+mode run.
    Saved to logs/<mode>/flow_details/<pkg>.txt
    Shows:
      - Which sources were active
      - Which sinks were reached
      - Full source→sink paths
      - Taint wrapper hit/miss ratio (indicates summary coverage)
      - Why flows may be missing (wrapper misses = uncovered library methods)
    """
    import re as _re

    out_dir = LOGS_DIR / spec_mode.value / "flow_details"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{pkg}.txt"

    lines = stderr.splitlines()

    # ── Extract key metrics ───────────────────────────────────────────────────
    RE_SS_MGR    = _re.compile(r"SourceSinkManager with (\d+) sources, (\d+) sinks")
    RE_LOOKUP    = _re.compile(r"Source lookup done, found (\d+) sources and (\d+) sinks")
    RE_HITS      = _re.compile(r"Taint wrapper hits:\s*(\d+)")
    RE_MISSES    = _re.compile(r"Taint wrapper misses:\s*(\d+)")
    RE_EDGES     = _re.compile(r"Callgraph has (\d+) edges")
    RE_IFDS      = _re.compile(r"IFDS problem with (\d+) forward and (\d+) backward edges")
    RE_SINK_LINE = _re.compile(r"The sink (.+?) in method <(.+?)>")
    RE_SRC_LINE  = _re.compile(r"- (.+?) in method <(.+?)>")
    RE_NO_SRC    = _re.compile(r"No sources found")
    RE_NO_RES    = _re.compile(r"No results found")

    ss_total    = RE_SS_MGR.search(stderr)
    ss_active   = RE_LOOKUP.search(stderr)
    hits        = RE_HITS.search(stderr)
    misses      = RE_MISSES.search(stderr)
    edges       = RE_EDGES.search(stderr)
    ifds        = RE_IFDS.search(stderr)
    no_sources  = bool(RE_NO_SRC.search(stderr))
    no_results  = bool(RE_NO_RES.search(stderr))

    tw_hits   = int(hits.group(1))   if hits   else 0
    tw_misses = int(misses.group(1)) if misses else 0
    tw_total  = tw_hits + tw_misses
    tw_pct    = f"{tw_hits/tw_total*100:.1f}%" if tw_total > 0 else "N/A"

    # ── Extract source→sink flows ─────────────────────────────────────────────
    flows = []
    current_sink   = None
    current_method = None
    current_srcs   = []

    for line in lines:
        sink_m = RE_SINK_LINE.search(line)
        if sink_m:
            if current_sink and current_srcs:
                flows.append((current_sink, current_method, list(current_srcs)))
            current_sink   = sink_m.group(1).strip()
            current_method = sink_m.group(2).strip()
            current_srcs   = []
        elif current_sink:
            src_m = RE_SRC_LINE.search(line)
            if src_m:
                current_srcs.append((src_m.group(1).strip(), src_m.group(2).strip()))

    if current_sink and current_srcs:
        flows.append((current_sink, current_method, current_srcs))

    # ── Write report ──────────────────────────────────────────────────────────
    with open(out_file, "w") as f:
        f.write(f"{'='*70}\n")
        f.write(f"TAINT FLOW ANALYSIS REPORT\n")
        f.write(f"{'='*70}\n")
        f.write(f"App          : {pkg}\n")
        f.write(f"Mode         : {spec_mode.value}\n")
        f.write(f"Summary dir  : {summary_dir or 'none (baseline)'}\n")
        f.write(f"Leaks found  : {taints_found}\n")
        f.write(f"\n{'─'*70}\n")
        f.write(f"COVERAGE METRICS\n")
        f.write(f"{'─'*70}\n")

        if ss_total:
            f.write(f"Sources defined in SourcesAndSinks.txt : {ss_total.group(1)}\n")
            f.write(f"Sinks   defined in SourcesAndSinks.txt : {ss_total.group(2)}\n")
        if ss_active:
            f.write(f"Sources actually reachable in app      : {ss_active.group(1)}\n")
            f.write(f"Sinks   actually reachable in app      : {ss_active.group(2)}\n")
        if edges:
            f.write(f"Callgraph edges                        : {edges.group(1)}\n")
        if ifds:
            f.write(f"IFDS forward edges                     : {ifds.group(1)}\n")
            f.write(f"IFDS backward edges                    : {ifds.group(2)}\n")

        f.write(f"\nTaint wrapper hits   : {tw_hits:>8,}\n")
        f.write(f"Taint wrapper misses : {tw_misses:>8,}\n")
        f.write(f"Summary coverage     : {tw_pct}\n")
        f.write(f"  (hits = library calls modelled by your XML summaries)\n")
        f.write(f"  (misses = library calls with NO matching summary — taint may be lost here)\n")

        # ── Diagnosis ─────────────────────────────────────────────────────────
        f.write(f"\n{'─'*70}\n")
        f.write(f"DIAGNOSIS\n")
        f.write(f"{'─'*70}\n")

        if no_sources:
            f.write("⚠ NO SOURCES FOUND — none of the defined source methods are called\n")
            f.write("  in this app's reachable code. No analysis possible.\n")
        elif no_results:
            f.write("⚠ SOURCES FOUND but NO FLOWS reached any sink.\n")
            f.write("  Possible reasons:\n")
            f.write(f"  1. Taint wrapper misses ({tw_misses:,}) — taint lost inside unmodelled\n")
            f.write(f"     library methods. Add XML summaries for those classes.\n")
            f.write(f"  2. Sinks not reachable from sources in this app's control flow.\n")
            f.write(f"  3. Access path length limit (max=5) truncated the propagation.\n")
        elif taints_found > 0:
            f.write(f"✓ {taints_found} flow(s) found successfully.\n")
            if tw_misses > tw_hits * 10:
                f.write(f"  Note: High miss rate ({tw_pct} coverage) suggests many library\n")
                f.write(f"  methods lack summaries. More flows may exist but taint is lost.\n")
        else:
            f.write("⚠ Analysis ran but found 0 leaks.\n")

        # ── Flows ─────────────────────────────────────────────────────────────
        if flows:
            f.write(f"\n{'─'*70}\n")
            f.write(f"TAINT FLOWS DETAIL ({len(flows)} flows)\n")
            f.write(f"{'─'*70}\n")
            for i, (sink, method, srcs) in enumerate(flows, 1):
                f.write(f"\nFlow #{i}\n")
                f.write(f"  Sink method   : {method}\n")
                f.write(f"  Sink call     : {sink}\n")
                f.write(f"  Source(s)     :\n")
                for src_call, src_method in srcs:
                    f.write(f"    • {src_call}\n")
                    f.write(f"      in {src_method}\n")
        else:
            f.write(f"\n{'─'*70}\n")
            f.write("NO TAINT FLOWS TO REPORT\n")

    log.info(
        f"[FLOW LOG] {pkg} [{spec_mode.value}] "
        f"leaks={taints_found}  tw_hits={tw_hits}  tw_misses={tw_misses}  "
        f"coverage={tw_pct}  → {out_file}"
    )
    
# ─────────────────────────────────────────────────────────────────────────────
# Batch runner
# ─────────────────────────────────────────────────────────────────────────────

def analyze_all(
    downloaded_meta: dict,
    custom_summaries_path:    Optional[Path] = None,
    stubdroid_summaries_path: Optional[Path] = None,
    manual_summaries_path:    Optional[Path] = None,
) -> list[AnalysisResult]:
    """
    Run all four spec modes on every downloaded APK.

    Folder priority (highest → lowest):
      1. Explicit argument passed here
      2. Environment variable (CUSTOM_SUMMARIES / STUBDROID_SUMMARIES / MANUAL_SUMMARIES)
      3. Default folder name (custom_summaries / stubs / manualsummaries)
    """
    summary_dirs: dict[str, Path] = dict(_DEFAULT_DIRS)

    if custom_summaries_path:
        summary_dirs["custom"] = Path(custom_summaries_path)
    if stubdroid_summaries_path:
        summary_dirs["stubdroid"] = Path(stubdroid_summaries_path)
    if manual_summaries_path:
        summary_dirs["manual"] = Path(manual_summaries_path)

    # Log what we're using
    for mode, folder in summary_dirs.items():
        n = count_xml_summaries(folder)
        status = f"{n} XML files" if n else "NOT FOUND"
        log.info(f"  [{mode}] summarydir = {folder}  ({status})")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Deduplicate APKs
    seen: set[str] = set()
    apk_list: list[dict] = []
    for entries in downloaded_meta.values():
        for e in entries:
            lp = e.get("localPath", "")
            if lp and lp not in seen:
                seen.add(lp)
                apk_list.append(e)

    log.info(f"Analyzing {len(apk_list)} unique APKs × {len(SpecMode)} modes …")

    all_results: list[AnalysisResult] = []
    checkpoint = Path("results/all_results.json")

    for entry in apk_list:
        apk = Path(entry["localPath"])
        pkg = entry["packageName"]
        if not apk.exists():
            log.warning(f"APK missing: {apk}")
            continue

        for mode in SpecMode:
            r = run_flowdroid(apk, mode, summary_dirs, pkg)
            all_results.append(r)
            checkpoint.write_text(
                json.dumps([x.to_dict() for x in all_results], indent=2)
            )
    log.info(f"Analyzing {len(apk_list)} unique APKs × {len(SpecMode)} modes …")

    log.info(f"Done — {len(all_results)} results in {checkpoint}")
    return all_results


if __name__ == "__main__":
    import sys
    meta = json.loads(Path("config/downloaded_apps.json").read_text())
    cs = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    ss = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    ms = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    analyze_all(meta, cs, ss, ms)
    
