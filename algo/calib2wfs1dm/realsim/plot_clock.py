#!/usr/bin/python3
"""Figure: the differenced lagged-A estimate on the offset-clock run, per mode.

Same estimator, same telemetry, two alignments: the original recipe (which assumes aligned
1 kHz / 2 kHz clocks) and the clock-general alignment told the WFS B clock offset.
Reads realsim_est_fixed.json and realsim_est_boff<offset>.json written by realsim_est.py.

Usage: plot_clock.py <run dir> <window label> <offset us> <out png>
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# The recommended estimator keeps the hue it has in realsim_estimates.png; the superseded
# alignment is drawn in neutral ink. All text in neutral inks.
NEW, OLD = "#eb6834", "#8b949e"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f2328", "#6a737d", "#e6e8eb"


def main(run, win, off, out):
    wdir = Path(run) / f"win_{win}"
    series = []
    for fname, name, color, marker in (
            ("realsim_est_fixed.json", "Original recipe (assumes aligned clocks)", OLD, "s"),
            (f"realsim_est_boff{float(off):g}.json", "Clock-general alignment", NEW, "o")):
        js = json.loads((wdir / fname).read_text())
        row = {r["name"]: r for r in js["rows"]}["IV diff"]
        series.append((name, color, marker, row))
    fig, ax = plt.subplots(figsize=(8.6, 4.1), facecolor=SURFACE)
    modes = np.arange(len(series[0][3]["ratio"]))
    ax.axhspan(0.95, 1.05, color=GRID, alpha=0.7, linewidth=0, zorder=0)
    ax.axhline(1.0, color=MUTED, linewidth=1.0, zorder=1)
    for name, color, marker, row in series:
        ax.plot(modes, row["ratio"], color=color, linewidth=2.0, marker=marker, markersize=4.5,
                markeredgecolor=SURFACE, markeredgewidth=0.8, zorder=3 if color == NEW else 2,
                label=f"{name}: {row['med']:+.1f}%  (per mode {row['mae']:.1f}%)")
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    vals = np.concatenate([s[3]["ratio"] for s in series])
    ax.set_ylim(np.floor(vals.min() * 10) / 10 - 0.05, np.ceil(vals.max() * 10) / 10 + 0.2)
    ax.set_xlim(-1, modes[-1] + 1)
    ax.set_xlabel("Stage-2 mode index", color=INK, fontsize=10)
    ax.set_ylabel("Estimate / reference", color=INK, fontsize=10)
    ax.set_title(f"WFS B clock {float(off):g} us late: DM2-to-WFS-B gain from 20 s of closed-loop"
                 " telemetry", color=INK, fontsize=10.5, loc="left", pad=8)
    leg = ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK,
                    title="Differenced lagged-A, bias of the median over modes 2-39",
                    title_fontsize=8.5, alignment="left")
    leg.get_title().set_color(MUTED)
    ax.text(modes[-1] + 0.6, 0.945, "within 5% of the reference", color=MUTED, fontsize=8.5,
            va="top", ha="right")
    fig.tight_layout()
    fig.savefig(out, dpi=170, facecolor=SURFACE)


if __name__ == "__main__":
    main(*sys.argv[1:5])
