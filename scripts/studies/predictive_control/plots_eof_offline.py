#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Figure 7: Offline 20s walk-forward Block-EOF vs Diagonal AR(P) gain."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from matplotlib.colors import LogNorm
import matplotlib.pyplot as plt
import numpy as np

def plot_fig7_eof_offline(
    eof_study: dict[str, Any],
    eof_bundles: list[dict[str, Any]],
    out_dir: Path,
) -> None:
    """Figure 7: 20 s Walk-Forward Cross-Mode EOF Physics, Scaling & Coupling Matrix (2x2)."""
    fig, axes = plt.subplots(2, 2, figsize=(15.4, 10.0), constrained_layout=True)
    fig.suptitle(
        "Cross-Mode Block-EOF (VAR(P)) vs. Per-Mode Diagonal AR(16) — "
        "20 s Walk-Forward Physics & Learned Coupling Structure\n"
        "(Strictly Out-of-Sample on t = 15–20 s Clean PSOL Telemetry | "
        "All 16 Stage-1 + 10 Stage-2 Spatial Blocks)",
        fontsize=11.5,
        fontweight="bold",
    )

    # (0,0) Sample-complexity curve (Stage 1 Block 0 [0:128])
    ax = axes[0, 0]
    sc = eof_study["sample_complexity"]
    nt = np.array(sc["ntrains"], dtype=float) / 1e3
    ax.axvspan(1.5, 7.5, color="#fef3c7", alpha=0.55, label="Cold-Start Bootstrap Zone (AR(16))")
    ax.plot(
        nt,
        sc["ar16_def_pct"],
        "--s",
        color="#64748b",
        lw=1.8,
        ms=5.5,
        label="Diag AR(16) (reg=5e-3)",
    )
    ax.plot(
        nt,
        sc["ar16_low_pct"],
        "-D",
        color="#2563eb",
        lw=1.8,
        ms=5.5,
        label="Diag AR(16) (reg=1e-4)",
    )
    ax.plot(
        nt,
        sc["eof64_p8_pct"],
        "-^",
        color="#d97706",
        lw=2.1,
        ms=6.0,
        label="Block-EOF(B=64, P=8) [D=512]",
    )
    ax.plot(
        nt,
        sc["eof128_p8_pct"],
        "-o",
        color="#059669",
        lw=2.3,
        ms=6.2,
        label="Block-EOF(B=128, P=8) [D=1024]",
    )
    ax.axhline(0.0, color="#0f172a", lw=0.8, alpha=0.6)
    ax.annotate(
        f"N=2k overfits\n({sc['eof128_p8_pct'][0]:.0f}%)",
        (nt[0], -58.0),
        textcoords="offset points",
        xytext=(0, 38),
        ha="left",
        fontsize=7.6,
        fontweight="bold",
        color="#b91c1c",
    )
    ax.annotate(
        f"+{sc['eof128_p8_pct'][-1]:.1f}% vs +{sc['ar16_def_pct'][-1]:.1f}%",
        (nt[-1], sc["eof128_p8_pct"][-1]),
        textcoords="offset points",
        xytext=(-98, -18),
        fontsize=8.0,
        fontweight="bold",
        color="#047857",
    )
    ax.set_xlim(1.5, 15.2)
    ax.set_ylim(-65, 92)
    ax.set_xlabel("Stage-1 PSOL Training Window N_train [x1,000 frames @ 1 kHz]")
    ax.set_ylabel("Out-of-Sample Lag Variance Reduction [%]")
    ax.set_title("Sample Complexity Law (Stage-1 Block 0, Modes 0–127)")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", framealpha=0.92, fontsize=7.6)

    # (0,1) Full-pupil block-by-block variance reduction (Stage 1 + Stage 2)
    ax = axes[0, 1]
    b1 = eof_study["blocks"]["stage1"]
    b2 = eof_study["blocks"]["stage2"]
    x1 = np.arange(len(b1["labels"]))
    x2 = np.arange(len(b2["labels"]))
    ax.plot(
        x1,
        b1["eof128_pct"],
        "-o",
        color="#059669",
        lw=2.1,
        ms=5.2,
        label=f"Stg1 EOF(128,8) [All: +{b1['tot_eof128_pct']:.1f}%]",
    )
    ax.plot(
        x1,
        b1["ar16_mat_pct"],
        "--D",
        color="#2563eb",
        lw=1.7,
        ms=4.5,
        label=f"Stg1 Diag AR(16) [All: +{b1['tot_ar16_mat_pct']:.1f}%]",
    )
    ax.fill_between(x1, b1["ar16_mat_pct"], b1["eof128_pct"], color="#10b981", alpha=0.18)
    ax.plot(
        x2,
        b2["eof128_pct"],
        "-^",
        color="#d97706",
        lw=1.9,
        ms=5.0,
        label=f"Stg2 EOF(128,8) [All: +{b2['tot_eof128_pct']:.1f}%]",
    )
    ax.plot(
        x2,
        b2["ar16_mat_pct"],
        ":s",
        color="#7c3aed",
        lw=1.6,
        ms=4.3,
        label=f"Stg2 Diag AR(16) [All: +{b2['tot_ar16_mat_pct']:.1f}%]",
    )
    ax.fill_between(x2, b2["ar16_mat_pct"], b2["eof128_pct"], color="#f59e0b", alpha=0.14)
    ax.set_xticks(x1[::2])
    ax.set_xticklabels([b1["labels"][i] for i in range(0, len(x1), 2)], rotation=25, ha="right")
    ax.set_ylim(0, 90)
    ax.set_xlabel("Spatial Mode Block Index (128-Mode Contiguous Blocks)")
    ax.set_ylabel("Out-of-Sample Lag Variance Reduction [%]")
    ax.set_title("Full-Pupil Block-by-Block Gain: 26 / 26 Blocks Win")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.6)

    # (1,0) Noise-gain Pareto frontier (||F_m||_2^2 vs OOS dVar on Block 0)
    ax = axes[1, 0]
    p_ar = eof_study["pareto"]["diag_ar16"]
    p_ef = eof_study["pareto"]["eof128_p8"]
    ar_n2 = [r["n2_med"] for r in p_ar]
    ar_v = [r["vr_all"] for r in p_ar]
    ef_n2 = [r["n2_med"] for r in p_ef]
    ef_v = [r["vr_all"] for r in p_ef]
    ax.plot(
        ef_n2,
        ef_v,
        "-o",
        color="#059669",
        lw=2.3,
        ms=5.8,
        label="Cross-Mode EOF(B=128, P=8) [Modes 0–127]",
    )
    ax.plot(
        ar_n2,
        ar_v,
        "--D",
        color="#2563eb",
        lw=2.0,
        ms=5.4,
        label="Per-Mode Diag AR(16) [Modes 0–127]",
    )
    ax.plot(
        [r["n2_med"] for r in p_ef],
        [r["vr_20_127"] for r in p_ef],
        ":^",
        color="#10b981",
        lw=1.5,
        ms=4.5,
        label="Cross-Mode EOF (Mid Modes 20–127)",
    )
    ax.plot(
        [r["n2_med"] for r in p_ar],
        [r["vr_20_127"] for r in p_ar],
        ":s",
        color="#60a5fa",
        lw=1.5,
        ms=4.5,
        label="Per-Mode Diag AR(16) (Mid Modes 20–127)",
    )
    # Highlight lam=1e-4 operating point on EOF
    i_op = [r["lam"] for r in p_ef].index(1e-4)
    ax.scatter([ef_n2[i_op]], [ef_v[i_op]], s=110, color="#047857", zorder=6)
    ax.annotate(
        f"EOF λ=1e-4\n(+{ef_v[i_op]:.1f}%, ‖F‖²={ef_n2[i_op]:.2f})",
        (ef_n2[i_op], ef_v[i_op]),
        textcoords="offset points",
        xytext=(42, -8),
        fontsize=7.8,
        fontweight="bold",
        color="#047857",
        bbox={"boxstyle": "round,pad=0.25", "fc": "#ecfdf5", "ec": "#10b981", "alpha": 0.92},
        arrowprops={"arrowstyle": "->", "color": "#047857", "lw": 1.0},
    )
    ax.set_xlim(0.2, 2.8)
    ax.set_ylim(25, 86)
    ax.set_xlabel("Median Row L2 Noise-Gain Squared ‖Fₘ‖₂² (Regularization Sweep)")
    ax.set_ylabel("Out-of-Sample Lag Variance Reduction [%]")
    ax.set_title("Physics of Cross-Mode Advection: Higher Gain at ~3× Lower Noise")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", framealpha=0.92, fontsize=7.5)

    # (1,1) Learned Stage-1 Block-0 cross-mode coupling matrix (modes 0..63)
    ax = axes[1, 1]
    eof128_b = next(b for b in eof_bundles if b["spec"]["key"] == "eof128_p8")
    f1 = eof128_b["filters"][1]
    c64 = np.maximum(f1["blk0_coupling"][:64, :64], 1e-4)
    im = ax.imshow(
        c64,
        origin="lower",
        cmap="magma",
        norm=LogNorm(vmin=3e-3, vmax=1.0),
        aspect="auto",
    )
    cb = fig.colorbar(im, ax=ax, pad=0.02, shrink=0.95)
    cb.set_label("Cross-Mode Filter Weight ‖F[i, :, j]‖₂")
    ax.set_xlabel("Input Mode Index j (Past History t .. t−7 ms)")
    ax.set_ylabel("Predicted Output Mode Index i (t + 2.4 ms)")
    ax.set_title("Learned Stage-1 Cross-Mode Matrix (Block 0, Modes 0–63)")
    off_b = f1["offdiag_by_block"]
    ax.text(
        0.97,
        0.04,
        f"Off-diag energy: {off_b[0]:.1f}% (Blk 0) → {max(off_b):.1f}% (Blk 14)\n"
        "Quadrature wind pairs: (47↔50), (16↔17), (3↔4), (8↔9)",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.6,
        color="#f8fafc",
        bbox={"boxstyle": "round,pad=0.35", "fc": "#0f172a", "ec": "#334155", "alpha": 0.88},
    )

    fig.savefig(out_dir / "eof_vs_ar_offline_20s_2x2.png")
    plt.close(fig)
