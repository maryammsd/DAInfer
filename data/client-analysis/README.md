# FlowDroid Specification Comparison Pipeline

Compare how **your custom specification**, **Stubdroid auto-generated stubs**, and **manual (DroidBench-style) specifications** affect FlowDroid taint analysis results across real Android apps from F-Droid.

---

## Directory layout

```
fdroid_analysis/
├── main.py                        ← orchestrator (run this)
├── fdroid_downloader.py           ← Step 1: download APKs from F-Droid
├── flowdroid_runner.py            ← Step 2: run FlowDroid (4 spec modes)
├── results_plotter.py             ← Step 3: compare & plot results
├── setup_check.py                 ← environment prerequisite checker
│
├── config/
│   ├── custom_SourcesAndSinks.txt ← YOUR specification (edit this)
│   ├── manual_SourcesAndSinks.txt ← standard/manual specification
│   └── downloaded_apps.json       ← generated: APK metadata
│
├── flowdroid/
│   └── soot-infoflow-cmd.jar      ← YOU must download this from flowdroid github (see below)
│
├── stubs/                         ← Stubdroid XML summaries (git clone)
├── apks/                          ← downloaded APK files
├── results/
│   ├── all_results.json           ← raw analysis results
│   ├── custom/    *.xml           ← FlowDroid XML output (dainfer+ mode)
│   ├── stubdroid/ *.xml           ← FlowDroid XML output (stubdroid mode)
│   ├── manual/    *.xml           ← FlowDroid XML output (manual mode)
│   ├── nosummary/    *.xml        ← no summary XML output (empty mode)
│   └── plots/                     ← generated PNG charts + CSV stats
└── logs/                          ← per-run FlowDroid stdout/stderr logs
```

---

## Prerequisites

### 1. Python packages
```bash
pip install requests matplotlib pandas seaborn tqdm
```

### 2. Java (≥ 11)
FlowDroid requires Java. Verify with:
```bash
java -version
```
Ensure that your java version is newer than Java 8. 

### 3. FlowDroid JAR
```bash
mkdir -p flowdroid
```
Then, download soot-infoflow-cmd-2.13.0-jar-with-dependencies.jar file from flowdroid github and rename it to soot-infoflow-cmd.jar and locate it in flowdroid folder. 
### 4. Android SDK platforms (android.jar)
```bash
# Install Android command-line tools, then:
sdkmanager "platforms;android-33"
export ANDROID_HOME=/path/to/android-sdk
```

### 5. Stubdroid summaries
```bash
git clone https://github.com/secure-software-engineering/stubs stubs
```
You can modify it to the stubs you want. We chose the ones that were also listed in dainfer+ and manual specifications to be fair.
### Verify everything
```bash
python setup_check.py
```

---

## Quick start

```bash
# Sanity check: no downloads or FlowDroid needed
python main.py --dry-run

# Full pipeline (download → analyze → plot)
python main.py

# Steps individually
python main.py --download-only     # just fetch APKs from F-Droid
python main.py --analyze-only      # just run FlowDroid (needs downloaded_apps.json)
python main.py --plot-only         # just regenerate plots (needs all_results.json)
```

### Useful flags
| Flag | Default | Description |
|------|---------|-------------|
| `--max-apk-mb N` | 80 | Skip APKs larger than N MB |
| `--timeout N` | 600 | Kill FlowDroid runs longer than N seconds |
| `--apps-per-cat N` | 10 | Apps to download per F-Droid category |
| `--dry-run` | — | Generate 600 synthetic results and plot them (no network/FlowDroid) |

---

## Thresholds and safety guards

The runner applies multiple gates **before** launching FlowDroid to avoid wasting time:

| Gate | Default | Config variable |
|------|---------|-----------------|
| APK file size | ≤ 80 MB | `MAX_APK_SIZE_MB` in `flowdroid_runner.py` |
| DEX class count | ≤ 15 000 | `MAX_DEX_CLASSES` |
| Wall-clock timeout | 600 s | `ANALYSIS_TIMEOUT_S` |
| JVM heap | 4 GB | `JVM_MAX_HEAP` |

Skipped/timed-out apps are recorded in `all_results.json` with `skipped=true` or `error="TIMEOUT"` and appear in Plot 4 (diagnostics).

---

## Customising your specification

Edit **`config/custom_SourcesAndSinks.txt`** to add/remove sources and sinks.

Format (one entry per line):
```
<fully.qualified.Class: returnType methodName(argTypes)> -> _SOURCE_ CATEGORY
<fully.qualified.Class: returnType methodName(argTypes)> -> _SINK_ CATEGORY
```

Available categories: `UNIQUE_IDENTIFIER`, `LOCATION`, `ACCOUNT`, `PHONE_CONNECTION`,
`FILE`, `SMS`, `NETWORK`, `VOIP`, `CALENDAR`, `DATABASE`, `EMAIL`, `BROWSER`,
`BLUETOOTH`, `AUDIO`, `SERIAL`, `NO_CATEGORY`

---

## Output plots

| File | Description |
|------|-------------|
| `01_taints_per_app.png` | Grouped bar chart: taint count per app × spec mode (top 40 apps) |
| `02_category_heatmap.png` | Heatmap: mean taints per F-Droid category × spec mode |
| `03_distribution.png` | Violin + box-plot of taint count distributions |
| `04_skip_diagnostics.png` | Success/skip/timeout/error breakdown per spec mode |
| `05_custom_vs_others_scatter.png` | Scatter: dainfer+ taints vs Stubdroid & manual (per app) |
| `summary_stats.csv` | Descriptive statistics table |

---

## F-Droid categories covered

Internet · Phone & SMS · Navigation · Multimedia · Graphics · Security ·
Science & Education · System · Development · Writing · Sports & Health ·
Games · Connectivity · Money · Reading · Time · Theming · Network · Contacts · Productivity

---

## Extending the pipeline

- **Add a 4th spec mode**: extend the `SpecMode` enum in `flowdroid_runner.py` and add a branch in `_build_flowdroid_cmd`.
- **Change category list**: edit `TARGET_CATEGORIES` in `fdroid_downloader.py`.
- **Add more plots**: add a `plot_*` function in `results_plotter.py` and call it from `run()`.
- **Resume interrupted runs**: the runner checkpoints `all_results.json` after every single FlowDroid invocation, so you can re-run `--analyze-only` after a crash without restarting from scratch (already-completed results are preserved).
