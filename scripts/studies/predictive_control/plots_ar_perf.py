#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Figures 1-2: Optical/coronagraphic performance and Subaru petal timeseries."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from matplotlib.gridspec import GridSpec
import matplotlib.pyplot as plt
import numpy as np

def plot_fig1_optical_coro(bundles: list[dict[str, Any]], out_dir: Path) -> None:
    """Figure 1: Optical, Wavefront, Coronagraphic & Predictor Summary (2x3)."""
    fig, axes = plt.subplots(2, 3, figsize=(16.5, 9.4), constrained_layout=True)
    fig.suptitle(
        "Subaru 7.95 m AO3k + SCExAO + Lyot Coronagraph — Optical & Coronagraphic Performance "
        "vs. AR Predictive Order\n"
        "(0.60\" Seeing, 8.0 kHz Internal Sub-Stepping, 5.0 s Physical, "
        "Default N_min=256 / N_train=2048 vs. Warm-Start AR(32)* & AR(64)* N=1024/4096)",
        fontsize=11.5,
        fontweight="bold",
    )

    labels = [b["spec"]["short"] for b in bundles]
    colors = [b["spec"]["color"] for b in bundles]
    x = np.arange(len(bundles))

    # (0,0) Wavefront Error: Post-AO3k & Post-SCExAO (Total vs Dynamic Std)
    ax = axes[0, 0]
    w = 0.38
    fin_tot = [b["summary"]["final_wfe_nm"] for b in bundles]
    fin_std = [b["summary"]["final_std_nm"] for b in bundles]
    bars1 = ax.bar(
        x - w / 2,
        fin_tot,
        width=w,
        color=colors,
        alpha=0.88,
        edgecolor="#0f172a",
        lw=0.8,
        label="Final Total WFE (Post-SCExAO)",
    )
    ax.bar(
        x + w / 2,
        fin_std,
        width=w,
        color=colors,
        alpha=0.45,
        hatch="//",
        edgecolor="#0f172a",
        lw=0.8,
        label="Final Dynamic Std (Excl. Static)",
    )
    for bar, val in zip(bars1, fin_tot):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 1.0,
            f"{val:.1f}",
            ha="center",
            va="bottom",
            fontsize=7.0,
            fontweight="bold",
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylim(0, max(fin_tot) * 1.24)
    ax.set_ylabel("Residual Wavefront Error [nm RMS]")
    ax.set_title("Post-SCExAO Residual WFE (Total vs. Dynamic)")
    ax.grid(axis="y", alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.6)

    # (0,1) Long-Exposure Strehl Ratios (Vis & H, Stage 1 & Final)
    ax = axes[0, 1]
    vis_f = [b["summary"]["vis_final_sr_pct"] for b in bundles]
    nir_f = [b["summary"]["nir_final_sr_pct"] for b in bundles]
    vis_1 = [b["summary"]["vis_stg1_sr_pct"] for b in bundles]
    ax.plot(x, nir_f, "-o", color="#059669", lw=2.0, ms=6.0, label="Final H-Band (1.65 µm)")
    ax.plot(x, vis_f, "-D", color="#2563eb", lw=2.0, ms=6.0, label="Final Vis (0.75 µm)")
    ax.plot(x, vis_1, "--^", color="#d97706", lw=1.6, ms=5.5, label="Stage-1 Only Vis (AO3k)")
    for xi, vf, nf in zip(x, vis_f, nir_f):
        ax.annotate(
            f"{vf:.1f}%",
            (xi, vf),
            textcoords="offset points",
            xytext=(0, -14),
            ha="center",
            fontsize=7.0,
            color="#1e40af",
            fontweight="bold",
        )
        ax.annotate(
            f"{nf:.1f}%",
            (xi, nf),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=7.0,
            color="#047857",
            fontweight="bold",
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylim(15, 104)
    ax.set_ylabel("Long-Exposure Strehl Ratio [%]")
    ax.set_title("Long-Exposure Optical Strehl (Visible & H-Band)")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", framealpha=0.92, fontsize=7.6)

    # (0,2) H-Band Lyot Coronagraphic Planet Contrast Radial Profiles
    ax = axes[0, 2]
    prof0 = bundles[0]["metrics"]["coronagraph_metrics"]["profiles"]
    rad_ld = np.asarray(prof0["rad_ld"], dtype=np.float64)
    dl_pl = np.asarray(prof0["dl_planet"], dtype=np.float64)
    mask_r = (rad_ld >= 2.5) & (rad_ld <= 22.0)
    ax.semilogy(
        rad_ld[mask_r],
        dl_pl[mask_r],
        color="#0f172a",
        ls=":",
        lw=1.7,
        label="Diffraction-Limited Coro",
    )
    for b in bundles:
        sp = b["spec"]
        pr = b["metrics"]["coronagraph_metrics"]["profiles"]
        ax.semilogy(
            rad_ld[mask_r],
            np.asarray(pr["cl_planet"], dtype=np.float64)[mask_r],
            color=sp["color"],
            ls=sp["ls"],
            lw=1.7 if sp["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else 1.2,
            alpha=0.92,
            label=sp["short"],
        )
    ax.axvline(3.0, color="#94a3b8", ls="--", lw=0.9, alpha=0.7)
    ax.text(3.2, 1.3e-3, "3 λ/D FPM", fontsize=7.5, color="#475569")
    ax.set_xlim(2.5, 22.0)
    ax.set_ylim(3e-7, 3e-3)
    ax.set_xlabel("Angular Separation [λ/D @ 1.65 µm]")
    ax.set_ylabel("Planet Contrast (Azimuthal Mean)")
    ax.set_title("H-Band Lyot Coronagraph Contrast Curves")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="upper right", ncol=2, framealpha=0.92, fontsize=7.0)

    # (1,0) Coronagraphic Key Metrics: Mean 3-10 l/D & 5-20 l/D Planet Contrast
    ax = axes[1, 0]
    c310 = [b["summary"]["coro_c3_10"] * 1e4 for b in bundles]
    c520 = [b["summary"]["coro_c5_20"] * 1e4 for b in bundles]
    b1 = ax.bar(
        x - w / 2,
        c310,
        width=w,
        color=colors,
        alpha=0.88,
        edgecolor="#0f172a",
        lw=0.8,
        label="Mean 3–10 λ/D [×10⁻⁴]",
    )
    b2 = ax.bar(
        x + w / 2,
        c520,
        width=w,
        color=colors,
        alpha=0.45,
        hatch="..",
        edgecolor="#0f172a",
        lw=0.8,
        label="Mean 5–20 λ/D [×10⁻⁴]",
    )
    for bar, val in zip(b1, c310):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.03,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=6.5,
            fontweight="bold",
        )
    for bar, val in zip(b2, c520):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.03,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=6.3,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylim(0, max(c310) * 1.26)
    ax.set_ylabel("Mean Planet Contrast [×10⁻⁴]")
    ax.set_title("Coronagraph Dark-Hole Contrast (Lower Is Better)")
    ax.grid(axis="y", alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.6)

    # (1,1) PSOL Predictor Lag Variance Reduction vs Order (Stage 1 & Stage 2)
    ax = axes[1, 1]
    pf_bundles = [b for b in bundles if b["summary"]["pf_stats"] is not None]
    xp = np.arange(len(pf_bundles))
    plbls = [b["spec"]["short"] for b in pf_bundles]
    vr1 = [b["summary"]["pf_stats"]["stage1"]["var_red_pct"] for b in pf_bundles]
    vr2 = [b["summary"]["pf_stats"]["stage2"]["var_red_pct"] for b in pf_bundles]
    ax.bar(
        xp - w / 2,
        vr1,
        width=w,
        color="#2563eb",
        alpha=0.85,
        edgecolor="#0f172a",
        lw=0.8,
        label="Stage 1 (AO3k, 1 kHz)",
    )
    ax.bar(
        xp + w / 2,
        vr2,
        width=w,
        color="#059669",
        alpha=0.85,
        edgecolor="#0f172a",
        lw=0.8,
        label="Stage 2 (SCExAO, 2 kHz)",
    )
    for xi, v1, v2 in zip(xp, vr1, vr2):
        ax.text(xi - w / 2, v1 + 0.6, f"{v1:.1f}", ha="center", va="bottom", fontsize=6.6)
        ax.text(xi + w / 2, v2 + 0.6, f"{v2:.1f}", ha="center", va="bottom", fontsize=6.6)
    ax.set_xticks(xp)
    ax.set_xticklabels(plbls, rotation=18, ha="right")
    ax.set_ylim(0, max(max(vr1), max(vr2)) * 1.24)
    ax.set_ylabel("Lag Variance Reduction vs. Pure ZOH [%]")
    ax.set_title("Online PSOL Predictor Variance Reduction")
    ax.grid(axis="y", alpha=0.28)
    ax.legend(loc="upper left", framealpha=0.92, fontsize=7.6)

    # (1,2) Quiescent Steady-State [1.5..4.5 s] vs Peak Gust [4.5..5.0 s] Resilience
    ax = axes[1, 2]
    ss_fin = [b["summary"]["ss_final_nm"] for b in bundles]
    gust_fin = [b["summary"]["gust_final_nm"] for b in bundles]
    ax.bar(
        x - w / 2,
        ss_fin,
        width=w,
        color=colors,
        alpha=0.88,
        edgecolor="#0f172a",
        lw=0.8,
        label="Steady-State [1.5–4.5 s]",
    )
    ax.bar(
        x + w / 2,
        gust_fin,
        width=w,
        color=colors,
        alpha=0.45,
        hatch="xx",
        edgecolor="#0f172a",
        lw=0.8,
        label="Peak 1.85 µm Gust [4.5–5.0 s]",
    )
    for xi, sv, gv in zip(x, ss_fin, gust_fin):
        ax.text(xi - w / 2, sv + 1.2, f"{sv:.1f}", ha="center", va="bottom", fontsize=6.4)
        ax.text(xi + w / 2, gv + 1.2, f"{gv:.1f}", ha="center", va="bottom", fontsize=6.4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_ylim(0, max(gust_fin) * 1.24)
    ax.set_ylabel("Mean Final WFE [nm RMS]")
    ax.set_title("Quiescent Tracking vs. Peak-Gust Resilience")
    ax.grid(axis="y", alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.6)

    fig.savefig(out_dir / "ar_order_optical_coro_summary_2x3.png")
    plt.close(fig)


def plot_fig2_timeseries_and_petals(bundles: list[dict[str, Any]], out_dir: Path) -> None:
    """Figure 2: Synchronized 5.0 s Time Series & Subaru V-Spider Petal OPD Maps."""
    n_runs = len(bundles)
    fig = plt.figure(figsize=(16.8, 10.8), constrained_layout=True)
    gs = GridSpec(4, n_runs, figure=fig, height_ratios=[1.05, 1.05, 1.0, 1.15])
    fig.suptitle(
        "Temporal Closed-Loop Evolution, Turbulence-Gust Resilience & Subaru V-Spider "
        "Petal-Jump Physics\n"
        "(Identical Maunakea 0.60\" Realization: AR(16), AR(32)*, and AR(64)* Maintain "
        "Zero-Petal Lock Through Peak 1.85 µm Gust)",
        fontsize=11.5,
        fontweight="bold",
    )

    ax_s1 = fig.add_subplot(gs[0, :])
    ax_fin = fig.add_subplot(gs[1, :], sharex=ax_s1)
    ax_sr = fig.add_subplot(gs[2, :], sharex=ax_s1)

    # Lightly shade the peak turbulence gust window
    for ax in (ax_s1, ax_fin, ax_sr):
        ax.axvspan(4.35, 5.0, color="#fef2f2", alpha=0.7, zorder=0)

    # Plot smoothed (20-sample = 10 ms) trajectories for legibility
    win = 20
    kernel = np.ones(win) / win
    for b in bundles:
        sp = b["spec"]
        ts = b["wf_ts"]
        t = ts[:, 1]
        s1_sm = np.convolve(ts[:, 3], kernel, mode="same")
        fin_sm = np.convolve(ts[:, 4], kernel, mode="same")
        lw = 1.85 if sp["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else 1.25
        ax_s1.plot(t[win:-win], s1_sm[win:-win], color=sp["color"], ls=sp["ls"], lw=lw,
                   label=f"{sp['short']} (Tot {b['summary']['stg1_wfe_nm']:.0f} nm)")
        ax_fin.plot(t[win:-win], fin_sm[win:-win], color=sp["color"], ls=sp["ls"], lw=lw,
                    label=f"{sp['short']} (Tot {b['summary']['final_wfe_nm']:.1f} nm)")

        st = b["sr_ts"]
        t_s = st[:, 2]
        # vis_final_inst is column 7
        vis_inst = st[:, 7] * 100.0
        vis_sm = np.convolve(vis_inst, kernel, mode="same")
        ax_sr.plot(t_s[win:-win], vis_sm[win:-win], color=sp["color"], ls=sp["ls"], lw=lw,
                   label=f"{sp['short']} (Long {b['summary']['vis_final_sr_pct']:.1f}%)")

    # Overlay scaled entrance turbulence reference on top panel
    t_ref = bundles[3]["wf_ts"][:, 1]
    raw_ref = np.convolve(bundles[3]["wf_ts"][:, 2], kernel, mode="same")
    ax_s1_r = ax_s1.twinx()
    ax_s1_r.plot(
        t_ref[win:-win],
        raw_ref[win:-win],
        color="#94a3b8",
        lw=0.9,
        alpha=0.55,
        label="Entrance Raw WFE",
    )
    ax_s1_r.set_ylabel("Entrance Raw WFE [nm]", color="#64748b", fontsize=8.5)
    ax_s1_r.set_ylim(300, 2200)
    ax_s1_r.spines["right"].set_visible(True)
    ax_s1_r.spines["right"].set_color("#94a3b8")

    ax_s1.set_ylabel("Post-AO3k WFE [nm]")
    ax_s1.set_ylim(40, 1050)
    ax_s1.set_yscale("log")
    ax_s1.set_title("Stage 1 (AO3k, 1 kHz) Post-DM1 Residual WFE vs. Time (10 ms Moving Mean)")
    ax_s1.grid(True, which="both", alpha=0.25)
    ax_s1.legend(loc="upper left", ncol=4, framealpha=0.92, fontsize=7.2)
    ax_s1.text(4.40, 740, "1.85 µm\nGust", color="#b91c1c", fontsize=8.0, fontweight="bold")

    ax_fin.set_ylabel("Post-SCExAO WFE [nm]")
    ax_fin.set_ylim(44, 175)
    ax_fin.set_title("Stage 2 (SCExAO, 2 kHz) Final Residual WFE vs. Time (10 ms Moving Mean)")
    ax_fin.grid(True, alpha=0.28)
    ax_fin.legend(loc="upper left", ncol=4, framealpha=0.92, fontsize=7.2)

    ax_sr.set_ylabel("Vis 0.75 µm SR [%]")
    ax_sr.set_xlabel("Physical Integration Time [s]")
    ax_sr.set_xlim(0.0, 5.0)
    ax_sr.set_ylim(30, 88)
    ax_sr.set_title("Final Visible (0.75 µm) Short-Exposure Strehl Ratio vs. Time")
    ax_sr.grid(True, alpha=0.28)
    ax_sr.legend(loc="lower left", ncol=4, framealpha=0.92, fontsize=7.2)

    # Bottom row: 2D Mean Stage-1 Pupil OPD Maps showing Subaru V-spider petal jumps
    for i, b in enumerate(bundles):
        ax_m = fig.add_subplot(gs[3, i])
        opd = np.where(b["pup_mask"], b["wf_mean_stg1"], np.nan)
        cmap = plt.get_cmap("RdBu_r").copy()
        cmap.set_bad("#0f172a")
        im = ax_m.imshow(opd, origin="lower", cmap=cmap, vmin=-650.0, vmax=650.0)
        ax_m.set_xticks([])
        ax_m.set_yticks([])
        ptv = b["summary"]["petal_ptv_stg1_nm"]
        s1m = b["summary"]["stg1_mean_nm"]
        ax_m.set_title(
            f"{b['spec']['short']}\nMean={s1m:.0f} nm\nΔPetal={ptv:.0f} nm",
            fontsize=7.8,
            color=b["spec"]["color"],
            fontweight="bold",
        )
        if i == n_runs - 1:
            cbar = fig.colorbar(im, ax=ax_m, fraction=0.055, pad=0.04)
            cbar.set_label("Mean Stg1 OPD [nm]", fontsize=7.6)

    fig.savefig(out_dir / "ar_order_timeseries_and_petals_2x3.png")
    plt.close(fig)
