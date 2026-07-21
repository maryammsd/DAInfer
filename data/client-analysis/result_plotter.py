"""
Results Comparator & Plotter — ACM half-page version
Reads results/all_results.json and generates publication-quality plots:
  01 – Grouped bar chart:  taints per app (numbered) × 4 modes
  02 – Category heatmap:   mean taints per category × 4 modes
  03 – Violin + box-plot:  taint distribution per mode
  04 – Outcome diagnostic: success / skip / timeout / error counts
  05 – Scatter matrix:     custom vs each other mode (per app)
  06 – App index table:    number → package name mapping
  07 – Summary CSV

ACM half-page: 3.33 inches wide, 300 DPI, Times-style fonts
"""

import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.patches as mpatches
import seaborn as sns
from pathlib import Path

RESULTS_FILE = Path("results/all_results.json")
OUT_DIR      = Path("results/plots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SPEC_MODES = ["custom", "stubdroid", "manual", "nosummary"]

MODE_LABELS = {
    "custom":    "Taint-Infer+",
    "stubdroid": "Taint-Stub",
    "manual":    "Taint-Manual",
    "nosummary": "Taint-Empty",
}
# ACM-friendly greyscale-safe palette with distinct hatches
PALETTE = {
    "custom":    "#c1121f",   # red
    "stubdroid": "#e76f51",   # warm coral
    "manual":    "#457b9d",   # steel blue
    "nosummary": "#f4a261",   # soft amber
}
HATCH = {
    "custom":    "",
    "stubdroid": "",
    "manual":    "",
    "nosummary": "",
}

# ── ACM half-page figure dimensions ──────────────────────────────────────────
# ACM text column = 3.33 in; use that as width for half-page figures
ACM_W   = 3.33   # inches
ACM_H   = 2.5    # inches — adjust per plot
ACM_DPI = 300

# ── Typography (ACM uses Times/serif; matplotlib uses DejaVu by default) ─────
matplotlib.rcParams.update({
    "font.family":       "serif",
    "font.size":         7,
    "axes.titlesize":    8,
    "axes.labelsize":    7,
    "xtick.labelsize":   6,
    "ytick.labelsize":   6,
    "legend.fontsize":   6,
    "legend.framealpha": 0.85,
    "figure.dpi":        ACM_DPI,
    "savefig.dpi":       ACM_DPI,
    "savefig.bbox":      "tight",
    "savefig.pad_inches": 0.02,
    "axes.linewidth":    0.6,
    "grid.linewidth":    0.4,
    "lines.linewidth":   0.8,
    "patch.linewidth":   0.4,
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_results() -> pd.DataFrame:
    df = pd.DataFrame(json.loads(RESULTS_FILE.read_text()))
    df["success"]       = df["success"].astype(bool)
    df["skipped"]       = df["skipped"].astype(bool)
    df["taints_found"]  = pd.to_numeric(df["taints_found"],  errors="coerce").fillna(0).astype(int)
    df["sources_found"] = pd.to_numeric(df["sources_found"], errors="coerce").fillna(0).astype(int)
    df["elapsed_sec"]   = pd.to_numeric(df["elapsed_sec"],   errors="coerce").fillna(0.0)
    return df


def _save(fig, name: str):
    p = OUT_DIR / name
    fig.savefig(p, dpi=ACM_DPI, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print(f"  Saved → {p}")


def _tick_labels(short=False):
    if short:
        return [MODE_LABELS[m].replace(" (Ours)", "") for m in SPEC_MODES]
    return [MODE_LABELS[m] for m in SPEC_MODES]


def _legend_patches():
    return [
        mpatches.Patch(facecolor=PALETTE[m], hatch=HATCH[m],
                       edgecolor="grey", linewidth=0.4,
                       label=MODE_LABELS[m])
        for m in SPEC_MODES
    ]


def build_app_index(df: pd.DataFrame) -> dict[str, int]:
    """
    Assign a stable integer ID to each app, sorted by total taints descending.
    Returns {package_name: app_number} starting from 1.
    """
    totals = (
        df.groupby("package_name")["taints_found"]
        .sum()
        .sort_values(ascending=False)
    )
    return {pkg: i + 1 for i, pkg in enumerate(totals.index)}


def save_app_index(index: dict[str, int]):
    """Save the app number → package name mapping as a text table."""
    lines = ["App#  Package name", "-" * 60]
    for pkg, num in sorted(index.items(), key=lambda x: x[1]):
        lines.append(f"{num:>4}  {pkg}")
    path = OUT_DIR / "app_index.txt"
    path.write_text("\n".join(lines))
    print(f"  Saved → {path}  ({len(index)} apps)")


# ── Plot 1 – Grouped bar: taints per app (numbered) ──────────────────────────

def plot_taints_per_app(df: pd.DataFrame, app_index: dict[str, int]):
    pivot = (
        df[df["success"] | (df["taints_found"] > 0)]
        .pivot_table(index="package_name", columns="spec_mode",
                     values="taints_found", aggfunc="max")
        .fillna(0).astype(int)
    )
    for m in SPEC_MODES:
        if m not in pivot.columns:
            pivot[m] = 0
    pivot = pivot[SPEC_MODES]

    # Keep only apps with at least one non-zero taint
    pivot = pivot[pivot.sum(axis=1) > 0]
    pivot["_total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("_total", ascending=False).drop("_total", axis=1)

    # Replace package names with app numbers
    pivot.index = [app_index.get(pkg, 0) for pkg in pivot.index]
    pivot = pivot.sort_index()

    n            = len(pivot)
    bw           = 0.18
    x            = range(n)
    offsets_base = [-1.5, -0.5, 0.5, 1.5]

    fig, ax = plt.subplots(figsize=(ACM_W, ACM_H))

    for i, mode in enumerate(SPEC_MODES):
        offs = [xi + offsets_base[i] * bw for xi in x]
        ax.bar(offs, pivot[mode], width=bw,
               color=PALETTE[mode], hatch=HATCH[mode],
               edgecolor="grey", linewidth=0.3,
               label=MODE_LABELS[mode], zorder=3)

    ax.set_xticks(list(x))
    ax.set_xticklabels([str(i) for i in pivot.index],
                       fontsize=5.5, rotation=0)
    ax.set_ylabel("Taint flows found", fontsize=7)
    ax.set_xlabel("Application ID", fontsize=7)
    #ax.set_title("Taint Flows per Application by Specification Mode", fontsize=8)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True, nbins=5))
    ax.legend(handles=_legend_patches(), ncol=2, fontsize=5.5,
              loc="upper right", framealpha=0.85,
              handlelength=1.2, handleheight=0.8)
    ax.grid(axis="y", linestyle="--", alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout(pad=0.3)
    _save(fig, "01_taints_per_app.pdf")
    _save(fig, "01_taints_per_app.png")


# ── Plot 2 – Category heatmap ─────────────────────────────────────────────────

def plot_category_heatmap(df: pd.DataFrame, meta: dict):
    pkg_cat = {e["packageName"]: cat
               for cat, entries in meta.items() for e in entries}
    df2 = df.copy()
    df2["category"] = df2["package_name"].map(pkg_cat).fillna("Other")

    pivot = (
        df2.groupby(["category", "spec_mode"])["taints_found"]
        .mean().unstack(fill_value=0)
    )
    for m in SPEC_MODES:
        if m not in pivot.columns:
            pivot[m] = 0.0
    pivot = pivot[SPEC_MODES].sort_index()
    pivot.columns = [MODE_LABELS[m] for m in SPEC_MODES]

    fig, ax = plt.subplots(figsize=(ACM_W, max(2.0, len(pivot) * 0.28)))
    sns.heatmap(
        pivot, ax=ax, annot=True, fmt=".1f",
        cmap="Blues", linewidths=0.3, linecolor="white",
        cbar_kws={"label": "Mean taints", "shrink": 0.8},
        annot_kws={"size": 5},
    )
    ax.set_title("Mean Taint Flows per Category", fontsize=8)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=20, ha="right", fontsize=6)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=6)
    fig.tight_layout(pad=0.3)
    _save(fig, "02_category_heatmap.pdf")
    _save(fig, "02_category_heatmap.png")


# ── Plot 3 – Distribution (violin + box) ─────────────────────────────────────

def plot_distribution(df: pd.DataFrame):
    data = df[df["success"]].copy()
    if data.empty or data["taints_found"].max() == 0:
        print("  [WARN] All taints are zero — skipping distribution plot")
        return

    fig, axes = plt.subplots(1, 2, figsize=(ACM_W, ACM_H))

    sns.violinplot(
        data=data, x="spec_mode", y="taints_found",
        hue="spec_mode", order=SPEC_MODES, palette=PALETTE,
        inner="quartile", cut=0, ax=axes[0], legend=False,
        linewidth=0.5,
    )
    axes[0].set_title("Violin", fontsize=7)
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Taint flows", fontsize=7)
    axes[0].set_xticks(range(len(SPEC_MODES)))
    axes[0].set_xticklabels(_tick_labels(short=True), fontsize=5.5, rotation=15, ha="right")
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)

    sns.boxplot(
        data=data, x="spec_mode", y="taints_found",
        hue="spec_mode", order=SPEC_MODES, palette=PALETTE,
        width=0.45, linewidth=0.5,
        flierprops=dict(marker="o", markersize=2, linewidth=0.3),
        ax=axes[1], legend=False,
    )
    axes[1].set_title("Box", fontsize=7)
    axes[1].set_xlabel("")
    axes[1].set_ylabel("")
    axes[1].set_xticks(range(len(SPEC_MODES)))
    axes[1].set_xticklabels(_tick_labels(short=True), fontsize=5.5, rotation=15, ha="right")
    axes[1].spines["top"].set_visible(False)
    axes[1].spines["right"].set_visible(False)

    for ax in axes:
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)

    fig.suptitle("Taint Flow Distribution by Specification Mode", fontsize=8, y=1.01)
    fig.tight_layout(pad=0.3)
    _save(fig, "03_distribution.pdf")
    _save(fig, "03_distribution.png")


# ── Plot 4 – Outcome diagnostic ───────────────────────────────────────────────

def plot_skip_diagnostics(df: pd.DataFrame):
    summary = (
        df.groupby("spec_mode")
        .apply(lambda g: pd.Series({
            "Success":  g["success"].sum(),
            "Skipped":  (g["skipped"] & (g["error"] != "TIMEOUT")).sum(),
            "Timeout":  (g["error"] == "TIMEOUT").sum(),
            "Error":    (~g["success"] & ~g["skipped"] &
                         (g["error"] != "TIMEOUT")).sum(),
        }), include_groups=False)
        .reindex(SPEC_MODES).fillna(0).astype(int)
    )

    statuses = ["Success", "Skipped", "Timeout", "Error"]
    colors   = ["#2d6a4f", "#adb5bd", "#e76f51", "#e63946"]
    bw       = 0.18
    x        = range(len(SPEC_MODES))

    fig, ax = plt.subplots(figsize=(ACM_W, ACM_H))
    for i, (stat, col) in enumerate(zip(statuses, colors)):
        offs = [xi + (i - 1.5) * bw for xi in x]
        ax.bar(offs, summary[stat], width=bw, color=col,
               label=stat, edgecolor="white", linewidth=0.3)

    ax.set_xticks(list(x))
    ax.set_xticklabels(_tick_labels(short=True), fontsize=6, rotation=15, ha="right")
    ax.set_ylabel("Number of APKs", fontsize=7)
    ax.set_title("Analysis Outcome per Specification Mode", fontsize=8)
    ax.legend(fontsize=5.5, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, 1.15), framealpha=0.85,
              handlelength=1.0)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout(pad=0.3)
    _save(fig, "04_skip_diagnostics.pdf")
    _save(fig, "04_skip_diagnostics.png")


# ── Plot 5 – Scatter: custom vs each other mode ───────────────────────────────

def plot_scatter_matrix(df: pd.DataFrame, app_index: dict[str, int]):
    pivot = (
        df[df["success"]]
        .pivot_table(index="package_name", columns="spec_mode",
                     values="taints_found", aggfunc="max")
        .fillna(0)
    )
    for m in SPEC_MODES:
        if m not in pivot.columns:
            pivot[m] = 0.0

    if pivot.max().max() == 0:
        print("  [WARN] All taints are zero — skipping scatter plot")
        return

    others = [m for m in SPEC_MODES if m != "custom"]
    fig, axes = plt.subplots(1, len(others),
                             figsize=(ACM_W, ACM_H),
                             sharey=False)

    for ax, other in zip(axes, others):
        x_vals = pivot["custom"]
        y_vals = pivot[other]

        # Plot points, annotate with app number
        for pkg in pivot.index:
            xv = pivot.loc[pkg, "custom"]
            yv = pivot.loc[pkg, other]
            ax.scatter(xv, yv, s=10, color=PALETTE[other],
                       alpha=0.7, edgecolors="none", zorder=3)

        lim = max(x_vals.max(), y_vals.max()) * 1.1 or 1
        ax.plot([0, lim], [0, lim], "k--", lw=0.6, alpha=0.4, label="y = x")
        ax.set_xlim(-0.3, lim)
        ax.set_ylim(-0.3, lim)
        ax.set_xlabel(f"DAInfer+", fontsize=6)
        ax.set_ylabel(MODE_LABELS[other], fontsize=6)
        ax.set_title(f"DAInfer+ vs {MODE_LABELS[other]}", fontsize=7)
        ax.grid(linestyle="--", alpha=0.35)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(labelsize=5.5)

    fig.suptitle("Per-App Taint Flows: DAInfer+ vs Other Modes", fontsize=8, y=1.02)
    fig.tight_layout(pad=0.3)
    _save(fig, "05_custom_vs_others_scatter.pdf")
    _save(fig, "05_custom_vs_others_scatter.png")


# ── Summary stats ─────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    print("\n" + "=" * 65)
    print("SUMMARY STATISTICS")
    print("=" * 65)
    for mode in SPEC_MODES:
        sub = df[df["spec_mode"] == mode]
        ok  = sub[sub["success"]]
        print(f"\n[{mode.upper()}]")
        print(f"  Runs        : {len(sub)}")
        print(f"  Successful  : {len(ok)}")
        print(f"  Skipped     : {sub['skipped'].sum()}")
        print(f"  Timeout     : {(sub['error'] == 'TIMEOUT').sum()}")
        if len(ok):
            print(f"  Taints min/mean/max : "
                  f"{ok['taints_found'].min()} / "
                  f"{ok['taints_found'].mean():.2f} / "
                  f"{ok['taints_found'].max()}")
        print(f"  Mean time   : {sub['elapsed_sec'].mean():.1f}s")

    stats    = df.groupby("spec_mode")["taints_found"].describe().round(2)
    csv_path = OUT_DIR / "summary_stats.csv"
    stats.to_csv(csv_path)
    print(f"\n  Full stats → {csv_path}")
    print("=" * 65)


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    if not RESULTS_FILE.exists():
        raise FileNotFoundError(
            f"{RESULTS_FILE} not found — run flowdroid_runner.py first")

    meta_file = Path("config/downloaded_apps.json")
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}

    print(f"Loading {RESULTS_FILE} …")
    df = load_results()
    print(f"  {len(df)} rows  |  {df['package_name'].nunique()} apps  |  "
          f"{df['spec_mode'].nunique()} modes: "
          f"{sorted(df['spec_mode'].unique())}")

    # Build app number index
    app_index = build_app_index(df)
    save_app_index(app_index)

    print("\nGenerating plots …")
    plot_taints_per_app(df, app_index)
    plot_category_heatmap(df, meta)
    plot_distribution(df)
    plot_skip_diagnostics(df)
    plot_scatter_matrix(df, app_index)
    print_summary(df)
    print(f"\nAll plots (PDF + PNG) → {OUT_DIR}/")
    print(f"App index table       → {OUT_DIR}/app_index.txt")
    print(f"\nIn your ACM paper, reference apps by number and cite the")
    print(f"app_index.txt as a table or appendix.")


if __name__ == "__main__":
    run()
