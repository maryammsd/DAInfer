#!/usr/bin/env python3
"""
setup_check.py – Environment checker and FlowDroid downloader helper
Verifies all prerequisites and prints a checklist.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

OK   = "✓"
WARN = "⚠"
ERR  = "✗"


def check(label, ok, detail=""):
    sym = OK if ok else ERR
    line = f"  [{sym}] {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


def main():
    print("\n" + "=" * 60)
    print("FlowDroid Comparison Pipeline – Environment Check")
    print("=" * 60)

    all_ok = True

    # Python version
    pv = sys.version_info
    ok = pv >= (3, 9)
    all_ok &= check(f"Python >= 3.9", ok, f"found {pv.major}.{pv.minor}")

    # Java
    java = shutil.which("java")
    if java:
        try:
            out = subprocess.check_output(
                ["java", "-version"], stderr=subprocess.STDOUT
            ).decode(errors="replace").split("\n")[0]
        except Exception:
            out = "unknown"
        ok = True
    else:
        out = "not found"
        ok = False
    all_ok &= check("Java (for FlowDroid)", ok, out)

    # Python packages
    for pkg in ("requests", "matplotlib", "pandas", "seaborn", "tqdm"):
        try:
            __import__(pkg)
            all_ok &= check(f"Python package: {pkg}", True)
        except ImportError:
            all_ok &= check(f"Python package: {pkg}", False, "pip install " + pkg)

    # FlowDroid JAR
    jar = Path("flowdroid/soot-infoflow-cmd.jar")
    ok  = jar.exists()
    if not ok:
        detail = (
            "Download from https://github.com/secure-software-engineering/FlowDroid/releases "
            f"and place at {jar}"
        )
    else:
        detail = str(jar)
    all_ok &= check("FlowDroid JAR", ok, detail if not ok else "found")

    # Android SDK
    android_home = os.environ.get("ANDROID_HOME", "/opt/android-sdk")
    platforms_dir = Path(android_home) / "platforms"
    jars = list(platforms_dir.glob("android-*/android.jar"))
    ok   = bool(jars)
    all_ok &= check(
        "Android SDK (android.jar)",
        ok,
        f"found {jars[0]}" if ok else
        f"Set $ANDROID_HOME or install SDK platforms into {platforms_dir}"
    )

    # YOUR custom XML summaries
    custom_dir = Path("custom_summaries")
    n_custom = sum(1 for _ in custom_dir.rglob("*.xml")) if custom_dir.exists() else 0
    all_ok &= check(
        "Your XML summaries (custom_summaries/)",
        n_custom > 0,
        f"{n_custom} .xml files" if n_custom else
        "Place your inferred .xml summary files in ./custom_summaries/  "
        "(or set CUSTOM_SUMMARIES env var to point elsewhere)"
    )

    # Stubdroid summaries
    stub_dir = Path("stubs")
    n_stubs = sum(1 for _ in stub_dir.rglob("*.xml")) if stub_dir.exists() else 0
    all_ok &= check(
        "Stubdroid XML summaries (stubs/)",
        n_stubs > 0,
        f"{n_stubs} .xml files" if n_stubs else
        "Clone https://github.com/secure-software-engineering/stubs into ./stubs/"
    )

    # Config files
    for cfg in ("config/custom_SourcesAndSinks.txt", "config/manual_SourcesAndSinks.txt"):
        p = Path(cfg)
        all_ok &= check(f"Config: {cfg}", p.exists(), "created" if p.exists() else "missing")

    # Directories
    for d in ("apks", "results", "logs", "config"):
        Path(d).mkdir(parents=True, exist_ok=True)
    check("Directories (apks/results/logs/config)", True, "created/existing")

    # wget / curl
    for tool in ("wget", "curl"):
        have = shutil.which(tool)
        check(f"CLI tool: {tool}", bool(have), "found" if have else "not found (optional)")

    print()
    if all_ok:
        print("All required checks passed! You're ready to run main.py")
    else:
        print(f"Some checks failed. Fix the items marked [{ERR}] before running the pipeline.")
        print()
        print("Quick-start commands:")
        print("  # Install Python deps")
        print("  pip install requests matplotlib pandas seaborn tqdm")
        print()
        print("  # Download FlowDroid JAR")
        print("  mkdir -p flowdroid && \\")
        print("  wget -O flowdroid/soot-infoflow-cmd.jar \\")
        print("    https://github.com/secure-software-engineering/FlowDroid/releases/download/v2.13.0/soot-infoflow-cmd-2.13.0-jar-with-dependencies.jar")
        print()
        print("  # Clone Stubdroid summaries")
        print("  git clone https://github.com/secure-software-engineering/stubs stubs")
        print()
        print("  # Place YOUR inferred XML summaries into custom_summaries/")
        print("  mkdir -p custom_summaries")
        print("  cp /path/to/your/xml/files/*.xml custom_summaries/")
        print("  # Or point to an existing folder via env var:")
        print("  # CUSTOM_SUMMARIES=/path/to/xmls python main.py")
        print()
        print("  # Install Android command-line tools, then:")
        print("  sdkmanager 'platforms;android-33'")
        print()
        print("  # Run demo (no FlowDroid or APKs needed):")
        print("  python main.py --dry-run")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
