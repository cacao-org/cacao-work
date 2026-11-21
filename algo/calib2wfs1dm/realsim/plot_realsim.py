#!/usr/bin/python3
"""Figure: gain estimates divided by the self-response reference, per mode, per window.

Reads the realsim_est.json written by realsim_est.py for each window.
Usage: plot_realsim.py <run dir> <out png> <label=panel title> ...
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Categorical hues in fixed order (validated set); all text in neutral inks.
HUES = {"tool W(z)": "#2a78d6", "IV diff": "#eb6834"}
NAMES = {"tool W(z)": "Shipped tool, W(z)", "IV diff": "Differenced lagged-A"}
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f2328", "#6a737d", "#e6e8eb"


def main(run, out, *pairs):
    run = Path(run)
    items = [p.split("=", 1) for p in pairs]
    fig, axes = plt.subplots(len(items), 1, figsize=(8.6, 2.75 * len(items) + 1.2), sharex=True,
                             facecolor=SURFACE, squeeze=False)
    for ax, (label, title) in zip(axes[:, 0], items):
        js = json.loads((run / f"win_{label}" / "realsim_est.json").read_text())
        rows = {r["name"]: r for r in js["rows"]}
        modes = np.arange(len(js["ref"]))
        ax.axhspan(0.95, 1.05, color=GRID, alpha=0.7, linewidth=0, zorder=0)
        ax.axhline(1.0, color=MUTED, linewidth=1.0, zorder=1)
        for k in ("tool W(z)", "IV diff"):
            r = rows[k]
            ax.plot(modes, r["ratio"], color=HUES[k], linewidth=2.0, marker="o", markersize=4.5,
                    markeredgecolor=SURFACE, markeredgewidth=0.8,
                    label=f"{NAMES[k]}: {r['med']:+.1f}%", zorder=3)
        ax.set_facecolor(SURFACE)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        vals = np.concatenate([rows[k]["ratio"] for k in ("tool W(z)", "IV diff")])
        ax.set_ylim(min(0.0, np.floor(vals.min() * 10) / 10),
                    max(1.45, np.ceil(vals.max() * 10) / 10))
        ax.set_xlim(-1, modes[-1] + 1)
        ax.set_ylabel("Estimate / reference", color=INK, fontsize=10)
        ax.set_title(title, color=INK, fontsize=10, loc="left", pad=6)
        leg = ax.legend(loc="best", ncol=2, frameon=False, fontsize=9, labelcolor=INK,
                        title="Bias of the median, modes 2-39", title_fontsize=8.5,
                        alignment="left")
        leg.get_title().set_color(MUTED)
    axes[0, 0].text(39.6, 1.06, "within 5% of the reference", color=MUTED, fontsize=8.5,
                    va="bottom", ha="right")
    axes[-1, 0].set_xlabel("Stage-2 mode index", color=INK, fontsize=10)
    n = len(items)
    height = 2.75 * n + 1.2
    fig.suptitle("Simulator telemetry: differenced estimate within a few percent,"
                 " shipped fit low", color=INK, fontsize=11.5, x=0.07, ha="left",
                 y=1.0 - 0.22 / height)
    fig.text(0.07, 1.0 - 0.52 / height,
             "DM2-to-WFS-B gain per mode, from 20 s of closed-loop telemetry, divided by the"
             " self-response reference", color=MUTED, fontsize=9, ha="left")
    fig.subplots_adjust(left=0.09, right=0.97, top=1.0 - 0.95 / height, bottom=0.55 / height,
                        hspace=0.28)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:])
