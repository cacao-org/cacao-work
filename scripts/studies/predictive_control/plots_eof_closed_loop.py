#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Figure 8: Closed-loop Block-EOF vs matched 14s-warmup Diagonal AR(16)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

def plot_fig8_eof_closed_loop(
    eof_bundles: list[dict[str, Any]],
    ar16_p1: dict[str, Any],
    out_dir: Path,
) -> None:
    """Figure 8: Matched 14 s-Warmup Closed-Loop Head-to-Head Comparison (2x3)."""
    fig, axes = plt.subplots(2, 3, figsize=(16.8, 9.6), constrained_layout=True)
    fig.suptitle(
        "Closed-Loop Hardware-in-the-Loop Comparison: Per-Mode Diagonal AR(16) vs. "
        "Cross-Mode Block-EOF(B=64/128, P=8)\n"
        "(Identical t = 14–19 s Unseen Maunakea Turbulence, 0.60\" Seeing, "
        "N_train = 16,384 / 32,768, 0 Petal Slips, 0 RT Timeouts)",
        fontsize=11.5,
        fontweight="bold",
    )

    labels = [b["spec"]["short"] for b in eof_bundles]
    colors = [b["spec"]["color"] for b in eof_bundles]
    x = np.arange(len(eof_bundles))

    # (0,0) Stage-1 & Post-SCExAO WFE + Vis Strehl bars
    ax = axes[0, 0]
    w = 0.36
    s1_w = [b["summary"]["stg1_wfe_nm"] for b in eof_bundles]
    fn_w = [b["summary"]["final_wfe_nm"] for b in eof_bundles]
    b1 = ax.bar(
        x - w / 2,
        s1_w,
        width=w,
        color=colors,
        alpha=0.55,
        hatch="//",
        edgecolor="#0f172a",
        lw=0.8,
        label="Stage 1 Only (Post-AO3k)",
    )
    b2 = ax.bar(
        x + w / 2,
        fn_w,
        width=w,
        color=colors,
        alpha=0.92,
        edgecolor="#0f172a",
        lw=0.8,
        label="Final (Post-SCExAO)",
    )
    for bar, val, b_obj in zip(b1, s1_w, eof_bundles):
        sr1 = b_obj["summary"]["vis_stg1_sr_pct"]
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.9,
            f"{val:.1f}\n({sr1:.1f}%)",
            ha="center",
            va="bottom",
            fontsize=6.8,
            fontweight="bold",
        )
    for bar, val, b_obj in zip(b2, fn_w, eof_bundles):
        srf = b_obj["summary"]["vis_final_sr_pct"]
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.9,
            f"{val:.1f}\n({srf:.1f}%)",
            ha="center",
            va="bottom",
            fontsize=6.8,
            fontweight="bold",
            color="#0f172a",
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=14, ha="right")
    ax.set_ylim(0, max(s1_w) * 1.28)
    ax.set_ylabel("Closed-Loop Total WFE [nm RMS] (Vis SR %)")
    ax.set_title("Post-AO3k & Post-SCExAO WFE (Annotated w/ Vis SR)")
    ax.grid(axis="y", alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.6)

    # (0,1) Synchronized 5.0 s Post-AO3k WFE time series (15 ms smooth)
    ax = axes[0, 1]
    win = np.ones(31) / 31.0
    for b in eof_bundles:
        sp = b["spec"]
        t = b["wf_ts"][:, 1]
        y_sm = np.convolve(b["wf_ts"][:, 3], win, mode="same")
        ax.plot(
            t,
            y_sm,
            color=sp["color"],
            ls=sp["ls"],
            lw=1.7 if sp["pf_mode"] == "eof" else 1.4,
            alpha=0.92,
            label=f"{sp['short']} (max {b['summary']['stg1_max_nm']:.0f} nm)",
        )
    ax.axvspan(1.95, 2.35, color="#fee2e2", alpha=0.45)
    ax.text(
        2.15,
        116.5,
        "2.22 µm Gust\n(-29 nm w/ EOF)",
        ha="center",
        va="top",
        fontsize=7.3,
        fontweight="bold",
        color="#991b1b",
    )
    ax.set_xlim(0.0, 5.0)
    ax.set_ylim(48, 118)
    ax.set_xlabel("Physical Science Time t [s] (after 14 s Warmup)")
    ax.set_ylabel("Stage-1 (Post-AO3k) Residual WFE [nm]")
    ax.set_title("Stage-1 Gust Rejection Over Identical 5.0 s Turbulence")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.2)

    # (0,2) H-Band Lyot Coronagraphic Raw Contrast & Relative Gain vs. Matched AR(16)
    ax = axes[0, 2]
    seps = np.array([3, 5, 10, 15, 20], dtype=float)
    for b in eof_bundles:
        sp = b["spec"]
        s = b["summary"]
        vals = [s[f"coro_raw_c{int(r)}"] for r in seps]
        ax.semilogy(
            seps,
            vals,
            marker=sp["marker"],
            color=sp["color"],
            ls=sp["ls"],
            lw=1.9,
            ms=5.6,
            label=f"{sp['short']} (5–20: {s['coro_c5_20']:.2e})",
        )
    s_mat = next(b["summary"] for b in eof_bundles if b["spec"]["key"] == "ar16_matched_w14s")
    s_e128 = next(b["summary"] for b in eof_bundles if b["spec"]["key"] == "eof128_p8")
    g15 = (1.0 - s_e128["coro_raw_c15"] / s_mat["coro_raw_c15"]) * 100.0
    g20 = (1.0 - s_e128["coro_raw_c20"] / s_mat["coro_raw_c20"]) * 100.0
    ax.annotate(
        f"EOF(128,8) vs AR(16) Match:\n-{g15:.1f}% @ 15 λ/D, -{g20:.1f}% @ 20 λ/D\n"
        f"LLOWFS DM3: {s_mat['llowfs_dm3_nm']:.1f}→{s_e128['llowfs_dm3_nm']:.1f} nm",
        (15.0, s_e128["coro_raw_c15"]),
        textcoords="offset points",
        xytext=(-148, -24),
        fontsize=7.3,
        fontweight="bold",
        color="#047857",
        bbox={"boxstyle": "round,pad=0.3", "fc": "#ecfdf5", "ec": "#10b981", "alpha": 0.92},
        arrowprops={"arrowstyle": "->", "color": "#047857", "lw": 1.0},
    )
    ax.set_xlim(2.5, 21.0)
    ax.set_ylim(3.5e-6, 3.2e-4)
    ax.set_xlabel("Angular Separation [λ/D @ 1.65 µm]")
    ax.set_ylabel("Coronagraph Raw Contrast (I / I_star)")
    ax.set_title("H-Band Lyot Coronagraph Raw Dark-Hole Contrast")
    ax.grid(True, which="both", alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.2)

    # (1,0) Stage-1 (1 kHz) Closed-Loop Residual PSD
    ax = axes[1, 0]
    for b in eof_bundles:
        sp = b["spec"]
        if 1 in b["psds"]:
            f = b["psds"][1]["freqs"]
            p = b["psds"][1]["psd_wfs"]
            m = f >= 2.0
            ax.loglog(f[m], p[m], color=sp["color"], ls=sp["ls"], lw=1.7, label=sp["short"])
    ax.set_xlim(2.0, 500.0)
    ax.set_xlabel("Temporal Frequency [Hz]")
    ax.set_ylabel("Summed Stage-1 WFS PSD [nm²/Hz]")
    ax.set_title("Stage 1 (1.0 kHz) Closed-Loop Temporal PSD")
    ax.grid(True, which="both", alpha=0.28)
    ax.legend(loc="lower left", framealpha=0.92, fontsize=7.5)

    # (1,1) Stage-2 (2 kHz) Closed-Loop Residual PSD
    ax = axes[1, 1]
    for b in eof_bundles:
        sp = b["spec"]
        if 2 in b["psds"]:
            f = b["psds"][2]["freqs"]
            p = b["psds"][2]["psd_wfs"]
            m = f >= 4.0
            ax.loglog(f[m], p[m], color=sp["color"], ls=sp["ls"], lw=1.7, label=sp["short"])
    ax.set_xlim(4.0, 1000.0)
    ax.set_xlabel("Temporal Frequency [Hz]")
    ax.set_ylabel("Summed Stage-2 WFS PSD [nm²/Hz]")
    ax.set_title("Stage 2 (2.0 kHz) Closed-Loop Temporal PSD")
    ax.grid(True, which="both", alpha=0.28)
    ax.legend(loc="lower left", framealpha=0.92, fontsize=7.5)

    # (1,2) Real-Time Compute Cost (CPU% & Inference Latency)
    ax = axes[1, 2]
    cmp_items = [
        ("AR(16)\n(N=2k)", ar16_p1, "#94a3b8"),
        ("AR(16) Match\n(N=16k/32k)", eof_bundles[1], "#2563eb"),
        ("EOF(B=64)\n(N=16k/32k)", eof_bundles[2], "#d97706"),
        ("EOF(B=128)\n(N=16k/32k)", eof_bundles[3], "#059669"),
    ]
    xc = np.arange(len(cmp_items))
    cpu_vals: list[float] = []
    lat1_vals: list[float] = []
    lat2_vals: list[float] = []
    for _, b_obj, _ in cmp_items:
        pr = b_obj["summary"]["procs"]
        is_eof = b_obj["summary"]["pf_mode"] == "eof"
        mk_p = "mkEOFPF" if is_eof else "mkARPF"
        ap_p = "applyEOFPF" if is_eof else "applyARPF"
        cpu_vals.append(
            sum(
                pr.get(f"{pfx}-{s}", {}).get("cl_cpu_pct", 0.0)
                for pfx in (mk_p, ap_p)
                for s in (1, 2)
            )
        )
        lat1_vals.append(pr.get(f"{ap_p}-1", {}).get("exec_p50_us", 0.0))
        lat2_vals.append(pr.get(f"{ap_p}-2", {}).get("exec_p50_us", 0.0))

    bars_c = ax.bar(
        xc - 0.18,
        cpu_vals,
        width=0.36,
        color=[c for _, _, c in cmp_items],
        alpha=0.88,
        edgecolor="#0f172a",
        lw=0.8,
        label="Total PF CPU [% of 1 Core]",
    )
    ax2 = ax.twinx()
    ax2.plot(
        xc + 0.18,
        lat1_vals,
        "o-",
        color="#dc2626",
        lw=1.8,
        ms=6.0,
        label="Stg-1 RT Apply p50 [µs]",
    )
    ax2.plot(
        xc + 0.18,
        lat2_vals,
        "s--",
        color="#7c3aed",
        lw=1.6,
        ms=5.5,
        label="Stg-2 RT Apply p50 [µs]",
    )
    for bar, cv in zip(bars_c, cpu_vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            cv + 4.0,
            f"{cv:.0f}%",
            ha="center",
            va="bottom",
            fontsize=7.4,
            fontweight="bold",
        )
    ax.set_xticks(xc)
    ax.set_xticklabels([lbl for lbl, _, _ in cmp_items], fontsize=7.8)
    ax.set_ylim(0, max(cpu_vals) * 1.25)
    ax2.set_ylim(0, max(lat1_vals) * 1.45)
    ax.set_ylabel("Total PF CPU Usage [% of 1 Core]")
    ax2.set_ylabel("Real-Time Inference Latency p50 [µs]", color="#991b1b")
    ax.set_title("Real-Time Compute: BLAS Block-EOF vs. Scalar AR(16)")
    ax.grid(axis="y", alpha=0.28)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", framealpha=0.92, fontsize=6.9)

    fig.savefig(out_dir / "eof_vs_ar_closed_loop_2x3.png")
    plt.close(fig)
