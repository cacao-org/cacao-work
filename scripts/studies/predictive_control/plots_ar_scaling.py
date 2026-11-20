#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Figure 5: Walk-forward bias-variance tradeoff and warmup sample complexity."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

def plot_fig5_bias_variance(
    wf_study: dict[str, Any],
    bundles: list[dict[str, Any]],
    out_dir: Path,
) -> None:
    """Figure 5: Walk-Forward Bias-Variance, Modal-Band Gain & Cold-Start Sample Complexity."""
    fig, axes = plt.subplots(2, 2, figsize=(15.2, 9.6), constrained_layout=True)
    fig.suptitle(
        "Bias–Variance Tradeoff, Sample Complexity (N_train / P) & AR(32)/AR(64) "
        "Cold-Start Ablations\n"
        "(Walk-Forward Out-of-Sample Evaluation Up to P = 64 on Clean PSOL Telemetry + "
        "Full Closed-Loop Validation)",
        fontsize=11.5,
        fontweight="bold",
    )

    orders = np.asarray(wf_study["orders"], dtype=np.float64)
    ntr_colors = {256: "#dc2626", 512: "#d97706", 1024: "#2563eb", 2048: "#059669"}

    # (0,0) Stage 1 & (0,1) Stage 2 Walk-Forward Out-of-Sample vs In-Sample dVar
    for col_i, stg_key, title_s in (
        (0, "stage1", "Stage 1 (1 kHz, lag=2.40 fr) — Walk-Forward Generalization"),
        (1, "stage2", "Stage 2 (2 kHz, lag=2.58 fr) — Walk-Forward Generalization"),
    ):
        ax = axes[0, col_i]
        sd = wf_study["stages"][stg_key]
        for ntr in wf_study["ntrains"]:
            c = ntr_colors[ntr]
            v_in = np.asarray(sd["in_pct"][str(ntr)], dtype=np.float64)
            v_out = np.asarray(sd["out_pct"][str(ntr)], dtype=np.float64)
            ax.plot(orders, v_out, "-o", color=c, lw=1.8, ms=4.8, label=f"N={ntr} Out-of-Sample")
            ax.plot(orders, v_in, "--", color=c, lw=1.0, alpha=0.55)
        ax.axhline(0.0, color="#64748b", ls=":", lw=1.0)
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 2, 4, 8, 16, 32, 64])
        ax.set_xticklabels(["1", "2", "4", "8", "16", "32", "64"])
        ax.set_xlabel("AR Filter Order P (Solid = Out-of-Sample, Dashed = In-Sample)")
        ax.set_ylabel("Lag Variance Reduction vs. ZOH [%]")
        ax.set_title(title_s)
        ax.grid(True, alpha=0.28)
        if col_i == 0:
            ax.set_ylim(-12.0, 49.0)
            ax.legend(loc="upper left", framealpha=0.92, fontsize=7.6)
        else:
            ax.set_ylim(-5.0, 52.0)
            ax.legend(loc="upper left", framealpha=0.92, fontsize=7.6)

    # (1,0) Stage-1 Out-of-Sample Gain by Spatial Modal Band (N_train = 2048)
    ax = axes[1, 0]
    b2048 = wf_study["stages"]["stage1"]["bands_2048"]
    p_list = [4, 8, 16, 32, 64]
    xp = np.arange(len(p_list))
    w = 0.19
    band_specs = [
        ("tt_low", "TT + Low (0–19)", "#dc2626"),
        ("mid", "Mid (20–255)", "#2563eb"),
        ("high", "High (256–1964)", "#059669"),
        ("all", "All Modes", "#0f172a"),
    ]
    for bi, (bk, blbl, bc) in enumerate(band_specs):
        vals = [b2048[bk][str(p)]["out_pct"] for p in p_list]
        offs = (bi - 1.5) * w
        ax.bar(
            xp + offs,
            vals,
            width=w,
            color=bc,
            alpha=0.85,
            edgecolor="#0f172a",
            lw=0.6,
            label=blbl,
        )
    ax.axhline(0.0, color="#334155", lw=1.0)
    ax.set_xticks(xp)
    ax.set_xticklabels([f"AR({p})" for p in p_list])
    ax.set_ylabel("Out-of-Sample Lag ΔVar vs. ZOH [%]")
    ax.set_title("Stage-1 Generalization by Spatial Mode Band (N_train=2048)")
    ax.grid(axis="y", alpha=0.28)
    ax.legend(loc="lower right", ncol=2, framealpha=0.92, fontsize=7.6)

    # (1,1) Universal Overfitting Gap vs Sample-to-Parameter Ratio N_train / P
    ax = axes[1, 1]
    for stg_key, mk, col_s, lbl_s in (
        ("stage1", "o", "#2563eb", "Stage 1 (1 kHz)"),
        ("stage2", "s", "#059669", "Stage 2 (2 kHz)"),
    ):
        sd = wf_study["stages"][stg_key]
        ratios: list[float] = []
        gaps: list[float] = []
        for ntr in wf_study["ntrains"]:
            v_in = sd["in_pct"][str(ntr)]
            v_out = sd["out_pct"][str(ntr)]
            for p_ord, vi, vo in zip(wf_study["orders"], v_in, v_out):
                if p_ord >= 4:
                    ratios.append(float(ntr) / float(p_ord))
                    gaps.append(float(vi) - float(vo))
        ax.scatter(
            ratios,
            gaps,
            color=col_s,
            marker=mk,
            s=42,
            alpha=0.82,
            edgecolor="#0f172a",
            lw=0.5,
            label=lbl_s,
        )
    ax.axvspan(3.0, 16.0, color="#fef2f2", alpha=0.8, zorder=0)
    ax.axvline(16.0, color="#dc2626", ls="--", lw=1.1)
    ax.axvline(32.0, color="#059669", ls="--", lw=1.1)
    ax.text(
        4.5,
        49.5,
        "Cold-start AR(64)\nN=256 (N/P = 4)\n53 pp gap!",
        fontsize=7.6,
        color="#9d174d",
        fontweight="bold",
    )
    ax.text(
        8.6,
        25.5,
        "AR(32) N=256\n(N/P = 8)",
        fontsize=7.6,
        color="#b91c1c",
        fontweight="bold",
    )
    ax.text(
        38.0,
        36.0,
        "Safe Operating\nRegime (N/P ≥ 32)",
        fontsize=7.8,
        color="#065f46",
        fontweight="bold",
    )
    ax.set_xscale("log", base=2)
    ax.set_xlim(3.2, 700.0)
    ax.set_ylim(-2.0, 58.0)
    ax.set_xlabel("Sample-to-Parameter Ratio N_train / P")
    ax.set_ylabel("Generalization Gap (In-Sample − Out-of-Sample) [pp]")
    ax.set_title("Universal Sample-Complexity Scaling Across Both Stages")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="upper right", framealpha=0.92)

    fig.savefig(out_dir / "ar_order_bias_variance_sample_complexity_2x2.png")
    plt.close(fig)
