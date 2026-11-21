#!/usr/bin/python3
"""Figure: WFS B optical gain per mode for each stage-2 loop state, and its ratio to nominal.

Usage: plot.py <scan dir> <label=legend name> ...   (first label is the reference state;
a label ending in "_repeat" is drawn as the same series as the reference, dashed)
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Categorical hues in fixed order (validated set), neutral inks for all text.
HUES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f2328", "#6a737d", "#e6e8eb"


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def main(scan, *pairs):
    scan = Path(scan)
    js = json.loads((scan / "og_vs_stage2_state.json").read_text())
    items = [p.split("=", 1) for p in pairs]
    ref = items[0][0]
    modes = np.arange(js["n_modes"])
    fig, (a0, a1) = plt.subplots(2, 1, figsize=(8.6, 7.4), sharex=True, facecolor=SURFACE,
                                 gridspec_kw=dict(height_ratios=[1.0, 1.0], hspace=0.16))
    hue = 0
    for label, name in items:
        st = js["states"][label]
        rep = label.endswith("_repeat")
        col = HUES[0] if rep else HUES[hue]
        kw = dict(color=col, linewidth=2.0, marker="o", markersize=4.5,
                  markeredgecolor=SURFACE, markeredgewidth=0.8)
        if rep:
            kw.update(linestyle=(0, (4, 2)), marker="o", markerfacecolor=SURFACE,
                      markeredgecolor=col, markeredgewidth=1.2)
        else:
            hue += 1
        a0.plot(modes, st["og_fixed"], label=name, **kw)
        if label != ref:
            wm, se = st["ratio_fixed_wmean_2_39"]
            a1.errorbar(modes, st["ratio_fixed"], yerr=st["ratio_fixed_err"], fmt="none",
                        ecolor=col, elinewidth=1.0, alpha=0.55, zorder=1)
            a1.plot(modes, st["ratio_fixed"], label=f"{name}: {wm:.3f}", **kw)
    a1.axhline(1.0, color=MUTED, linewidth=1.0)
    a1.axhspan(0.98, 1.02, color=GRID, alpha=0.7, linewidth=0, zorder=0)
    a1.text(39.6, 1.022, "within 2% of nominal", color=MUTED, fontsize=8.5, va="bottom",
            ha="right")
    for ax in (a0, a1):
        style(ax)
    a0.set_ylabel("Optical gain of WFS B", color=INK, fontsize=10)
    a1.set_ylabel("Ratio to nominal", color=INK, fontsize=10)
    a1.set_xlabel("Stage-2 mode index", color=INK, fontsize=10)
    a1.set_xlim(-1, modes[-1] + 1)
    a0.legend(loc="lower right", ncol=2, frameon=False, fontsize=9, labelcolor=INK)
    a1.legend(loc="lower right", ncol=2, frameon=False, fontsize=9, labelcolor=INK,
              title="Mean ratio, modes 2-39", title_fontsize=8.5, alignment="left")
    a1.get_legend().get_title().set_color(MUTED)
    a0.annotate("tip, tilt", xy=(0.5, 0.70), xytext=(2.6, 0.60), color=MUTED, fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.8))
    fig.suptitle("Opening stage 2 lowers the WFS B optical gain by 5%, and by a third for"
                 " tip and tilt", color=INK, fontsize=12, x=0.07, ha="left", y=0.965)
    fig.text(0.07, 0.905, "AO3k + SCExAO simulation: self-response gain of the 40 leading"
             " stage-2 modes.\nStage 1 closed, 0.6 arcsec seeing, mV = 6. Bars: 1 sigma.",
             color=MUTED, fontsize=9, ha="left", linespacing=1.4)
    fig.subplots_adjust(left=0.09, right=0.97, top=0.875, bottom=0.08)
    fig.savefig(scan / "og_vs_stage2_state.png", dpi=150, facecolor=SURFACE)
    print("wrote", scan / "og_vs_stage2_state.png")


if __name__ == "__main__":
    main(*sys.argv[1:])
