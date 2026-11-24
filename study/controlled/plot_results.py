#!/usr/bin/env python3
"""Standalone publication figure from offline analysis.json; no live services."""

import argparse
import json
import math
from pathlib import Path
import statistics


def plot(data, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    cases = sorted({p["case_id"] for p in data["pairs"]})
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.7), sharey=True, layout="constrained")
    palette = ("#236192", "#b55b19")
    for ax, metric, title, color in zip(axes, ("input_tokens", "native_elapsed_s"), ("Input tokens (cached subset included)", "Native attempt elapsed time"), palette):
        all_values = []
        for y, case in enumerate(cases):
            values = [p[metric + "_ratio"] for p in data["pairs"] if p["case_id"] == case and p[metric + "_ratio"] is not None]
            values = [v for v in values if v > 0 and math.isfinite(v)]
            all_values += values
            if values:
                offsets = [(i - (len(values) - 1) / 2) * .055 for i in range(len(values))]
                ax.scatter(values, [y + offset for offset in offsets], color=color, s=35, alpha=.8, zorder=3)
                ax.plot([min(values), max(values)], [y, y], color=color, lw=1.5, zorder=2)
                ax.scatter([statistics.mean(values)], [y], color=color, marker="|", s=220, linewidths=2.4, zorder=4)
            ax.text(1.01, y, f"n={len(values)}", transform=ax.get_yaxis_transform(), va="center", fontsize=9)
        ax.axvline(1, color="#555555", linestyle="--", linewidth=1)
        ax.set_xscale("log", base=2)
        if metric == "input_tokens":
            low, high = min([1, *all_values]), max([1, *all_values])
            center, span = (low + high) / 2, max(high - low, .15)
            lower, upper = max(.0001, center - span * .65), center + span * .65
            ticks = [float(v) for v in MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]).tick_values(lower, upper)
                     if lower <= v <= upper]
        else:
            lower = min([.5, *all_values]) * .85
            upper = max([1.5, *all_values]) * 1.15
            ticks = [v for v in (.25, .5, .75, 1, 1.25, 1.5, 2, 3, 4) if lower <= v <= upper]
        ax.set_xlim(lower, upper)
        ax.set_xticks(ticks, [f"{v:g}" for v in ticks])
        ax.grid(axis="x", alpha=.2)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Compact / Full  (below 1 is lower)")
        ax.spines[["top", "right"]].set_visible(False)
    labels = []
    for case in cases:
        counts = {row["condition"]: row for row in data["summary"] if row["case_id"] == case}
        labels.append(f"{case.split('/')[0]}\nPass: full {counts['full']['native_passes']}/5, compact {counts['compact']['native_passes']}/5")
    axes[0].set_yticks(range(len(cases)), labels, fontsize=9)
    axes[0].set_ylim(len(cases) - .5, -.5)
    interim = f" (interim: {data['captured_trials']}/50 captured)" if data.get("captured_trials", 50) < 50 else ""
    fig.suptitle("Paired efficiency among successful, independently audited trials" + interim, fontsize=13)
    fig.supxlabel("Dots: paired replicates; bar: observed range; vertical mark: arithmetic mean.\nFailed/unaudited pairs and missing metrics are excluded from ratios, retained in success counts and trial tables. n ≤ 5 per task.", fontsize=9)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / "main-comparison.svg", bbox_inches="tight")
    fig.savefig(output / "main-comparison.png", dpi=180, bbox_inches="tight")
    fig.savefig(output / "main-comparison.pdf", bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=Path("study/controlled/final/analysis/analysis.json"))
    parser.add_argument("--out", type=Path, default=Path("report/figures"))
    args = parser.parse_args()
    plot(json.loads(args.analysis.read_text()), args.out)


if __name__ == "__main__":
    main()
