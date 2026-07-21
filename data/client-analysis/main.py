#!/usr/bin/env python3
"""
FlowDroid Specification Comparison Pipeline
============================================
Compares taint analysis results across FOUR summary modes:

  custom     – your inferred XML summaries  (custom_summaries/)
  stubdroid  – Stubdroid official summaries (stubs/)
  manual     – your manual XML summaries    (manualsummaries/)
  nosummary  – no summaries at all          (baseline)

Usage:
  python main.py                          # full pipeline
  python main.py --download-only          # step 1 only
  python main.py --analyze-only           # step 2 only
  python main.py --plot-only              # step 3 only
  python main.py --dry-run               # synthetic demo, no downloads/FlowDroid

  # Point at your actual folders:
  python main.py \\
    --custom-summaries   /path/to/custom_summaries \\
    --stubdroid-summaries /path/to/stubs \\
    --manual-summaries   /path/to/manualsummaries
"""

import argparse
import json
import random
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--download-only",  action="store_true")
    p.add_argument("--analyze-only",   action="store_true")
    p.add_argument("--plot-only",      action="store_true")
    p.add_argument("--dry-run",        action="store_true",
                   help="Generate synthetic data and plot it (no network/FlowDroid needed)")
    p.add_argument("--max-apk-mb",     type=int, default=80)
    p.add_argument("--timeout",        type=int, default=600)
    p.add_argument("--apps-per-cat",   type=int, default=10)
    p.add_argument("--custom-summaries",    default=None, metavar="DIR",
                   help="Path to YOUR inferred XML summaries folder")
    p.add_argument("--stubdroid-summaries", default=None, metavar="DIR",
                   help="Path to Stubdroid official XML summaries folder")
    p.add_argument("--manual-summaries",    default=None, metavar="DIR",
                   help="Path to your manual XML summaries folder")
    return p.parse_args()


# ── Demo data generator ───────────────────────────────────────────────────────

DEMO_CATEGORIES = [
    "Internet", "Phone & SMS", "Navigation", "Multimedia", "Graphics",
    "Security", "Science & Education", "System", "Development", "Writing",
    "Sports & Health", "Games", "Connectivity", "Money", "Reading",
    "Time", "Theming", "Network", "Contacts", "Productivity",
]
DEMO_APPS_PER_CAT = 10
DEMO_MODES = ["custom", "stubdroid", "manual", "nosummary"]

# Simulated taint-count bias per mode (custom finds slightly more than others)
_BIAS = {"custom": 3, "stubdroid": 0, "manual": 1, "nosummary": -4}


def _demo_app(cat: str, idx: int) -> dict:
    pkg = f"org.{cat.lower().replace(' & ','_').replace(' ','_')}.app{idx}"
    return dict(
        packageName=pkg, name=f"{cat} App {idx}", categories=[cat],
        popularityScore=random.randint(1, 200), versionCode=random.randint(10, 500),
        apkName=f"{pkg}.apk", size=random.randint(2, 60) * 1024 * 1024,
        sha256="demo", localPath=f"apks/{pkg}.apk",
    )


def _demo_result(pkg: str, mode: str) -> dict:
    roll = random.random()
    if roll < 0.05:
        return dict(apk_path=f"apks/{pkg}.apk", package_name=pkg, spec_mode=mode,
                    success=False, skipped=True,
                    skip_reason="APK too large (demo)", taints_found=0,
                    sources_found=0, elapsed_sec=0.0, summary_dir_used="",
                    summary_xml_count=0, stdout_excerpt="", stderr_excerpt="",
                    error="", extra={})
    if roll < 0.13:
        return dict(apk_path=f"apks/{pkg}.apk", package_name=pkg, spec_mode=mode,
                    success=False, skipped=True, skip_reason="Timeout after 600s",
                    taints_found=0, sources_found=0, elapsed_sec=600.0,
                    summary_dir_used="", summary_xml_count=0,
                    stdout_excerpt="", stderr_excerpt="", error="TIMEOUT", extra={})
    base   = random.randint(0, 20)
    taints = max(0, base + _BIAS[mode] + random.randint(-3, 3))
    xml_counts = {"custom": 45, "stubdroid": 120, "manual": 30, "nosummary": 0}
    return dict(apk_path=f"apks/{pkg}.apk", package_name=pkg, spec_mode=mode,
                success=True, skipped=False, skip_reason="",
                taints_found=taints,
                sources_found=max(0, taints + random.randint(-2, 4)),
                elapsed_sec=round(random.uniform(5, 280), 1),
                summary_dir_used="" if mode == "nosummary" else f"{mode}_summaries",
                summary_xml_count=xml_counts[mode],
                stdout_excerpt=f"[Demo] Found {taints} taint flows",
                stderr_excerpt="", error="", extra={})


def generate_demo_data():
    Path("config").mkdir(parents=True, exist_ok=True)
    Path("results").mkdir(parents=True, exist_ok=True)

    meta: dict[str, list] = {}
    all_results = []

    for cat in DEMO_CATEGORIES:
        meta[cat] = []
        for ai in range(1, DEMO_APPS_PER_CAT + 1):
            app = _demo_app(cat, ai)
            meta[cat].append(app)
            for mode in DEMO_MODES:
                all_results.append(_demo_result(app["packageName"], mode))

    Path("config/downloaded_apps.json").write_text(json.dumps(meta, indent=2))
    Path("results/all_results.json").write_text(json.dumps(all_results, indent=2))
    log.info(
        f"Demo data: {len(meta)} categories, "
        f"{sum(len(v) for v in meta.values())} apps, "
        f"{len(all_results)} results ({len(DEMO_MODES)} modes)"
    )


# ── Pipeline steps ────────────────────────────────────────────────────────────

def step_download(args):
    import fdroid_downloader as fd
    fd.APPS_PER_CAT = args.apps_per_cat
    return fd.run()


def step_analyze(args, meta):
    import flowdroid_runner as fr
    fr.MAX_APK_SIZE_MB    = args.max_apk_mb
    fr.ANALYSIS_TIMEOUT_S = args.timeout
    return fr.analyze_all(
        meta,
        custom_summaries_path    = Path(args.custom_summaries)    if args.custom_summaries    else None,
        stubdroid_summaries_path = Path(args.stubdroid_summaries) if args.stubdroid_summaries else None,
        manual_summaries_path    = Path(args.manual_summaries)    if args.manual_summaries    else None,
    )


def step_plot():
    import results_plotter as rp
    rp.run()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.dry_run:
        log.info("=== DRY-RUN: generating synthetic demo data ===")
        generate_demo_data()
        step_plot()
        return

    meta_path    = Path("config/downloaded_apps.json")
    results_path = Path("results/all_results.json")

    if not args.analyze_only and not args.plot_only:
        log.info("=== STEP 1: Downloading APKs from F-Droid ===")
        meta = step_download(args)
    elif meta_path.exists():
        meta = json.loads(meta_path.read_text())
    else:
        log.error(f"{meta_path} not found — run without --analyze-only first")
        raise SystemExit(1)

    if args.download_only:
        return

    if not args.plot_only:
        log.info("=== STEP 2: Running FlowDroid (4 modes) ===")
        step_analyze(args, meta)

    if args.analyze_only:
        return

    log.info("=== STEP 3: Generating comparison plots ===")
    step_plot()
    log.info("Pipeline complete ✓")


if __name__ == "__main__":
    main()
