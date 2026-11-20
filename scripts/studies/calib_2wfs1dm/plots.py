#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Matplotlib figure generators for the 2-WFS + 1-DM calibration technical study."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

from astropy.io import fits
import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.gridspec import GridSpec  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from .telemetry import load_tlm_2d


def configure_matplotlib() -> None:
    """Configure consistent publication rcParams for all calibration figures."""
    plt.rcParams.update(
        {
            "font.size": 9.5,
            "axes.titlesize": 10.4,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "legend.fontsize": 8.0,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "figure.dpi": 180,
            "savefig.dpi": 180,
        }
    )


def plot_whitening_lag_regimes(
    out_dir: Path,
    sweeps: dict[str, Any],
    method_bench: dict[str, dict[str, Any]],
    dD: int,
) -> None:
    """Render Figure 2: AR(p) whitening sweep, lag surface, regimes, and convergence."""
    mx = np.arange(dD)
    sum_pred5 = sweeps["sum_pred5"]
    cdir_pred5 = sweeps["cdir_pred5"]
    sweep_p = sweeps["sweep_p"]
    conv_sums = sweeps["conv_sums"]
    srm_ref = float(sum_pred5["selfrm_og_med"])

    fig2, axes = plt.subplots(2, 2, figsize=(13.6, 8.8), constrained_layout=True)
    fig2.suptitle(
        "2-WFS + Inter-Stage DM Calibration — Deep-Dive Diagnostics "
        "(Whitening, Lag, Control Regimes & Convergence)",
        fontsize=12.4,
        fontweight="bold",
    )

    ax = axes[0, 0]
    ps = [r["order"] for r in sweep_p]
    mdb_p = [r["mdb_diag_med"] for r in sweep_p]
    eta_p = [r["eta_d_white_med"] for r in sweep_p]
    err_p = [r["selfrm_rel_err"] * 100.0 for r in sweep_p]
    r2ol_p = [r["r2_ol_raw_med"] for r in sweep_p]
    ax.axhline(srm_ref, color="#111827", ls="--", lw=1.6, label=f"Active selfRM truth ({srm_ref:.3f})")
    ax.plot(ps, mdb_p, "o-", color="#1d4ed8", lw=2.2, ms=6.5, label="Calibrated med diag(Mdb)")
    ax.plot(ps, eta_p, "s--", color="#059669", lw=1.7, ms=5.5, label="Conditional excitation η_D")
    ax.plot(ps, r2ol_p, "^:", color="#d97706", lw=1.7, ms=5.5, label="Held-out Pseudo-OL R²")
    offsets = {
        0: (0.18, -0.075), 1: (0.05, -0.068), 2: (0.0, -0.068),
        4: (0.0, -0.068), 6: (0.0, -0.068), 8: (-0.18, -0.068),
    }
    for x, y, er in zip(ps, mdb_p, err_p):
        dx, dy = offsets[x]
        ax.annotate(
            f"{er:.1f}% err",
            (x, y),
            xytext=(x + dx, y + dy),
            ha="center",
            fontsize=7.9,
            color="#1e3a8a",
            fontweight="bold",
        )
    ax.set_xlabel("Causal AR(p) Whitening Order p")
    ax.set_ylabel("Modal Gain / Excitation / Held-Out R²")
    ax.set_title("(a) AR(p) Whitening Order Sweep (Bias Elimination)")
    ax.set_xticks(ps)
    ax.set_xlim(-0.45, 8.45)
    ax.set_ylim(0.15, 1.05)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", fontsize=8.0, framealpha=0.92)

    ax = axes[0, 1]
    lrows = np.loadtxt(cdir_pred5 / "lag_scan.txt")
    colors_ab = {-0.5: "#9333ea", 0.0: "#1d4ed8", 0.5: "#059669"}
    for lab in np.unique(lrows[:, 1]):
        sub = lrows[np.isclose(lrows[:, 1], lab)]
        sub = sub[np.argsort(sub[:, 0])]
        ax.plot(
            sub[:, 0],
            sub[:, 2],
            "o" + ("-" if abs(lab) < 1e-6 else "--"),
            color=colors_ab.get(float(lab), "#475569"),
            lw=2.4 if abs(lab) < 1e-6 else 1.5,
            ms=5.5,
            label=f"R²_w (lag_AB = {lab:+.1f} fr)",
        )
    ax2 = ax.twinx()
    sub0 = lrows[np.isclose(lrows[:, 1], 0.0)]
    sub0 = sub0[np.argsort(sub0[:, 0])]
    ax2.plot(sub0[:, 0], sub0[:, 3], "d:", color="#dc2626", lw=1.7, ms=5.0, label="med diag(Mdb) @ lag_AB=0")
    ax2.axhline(srm_ref, color="#dc2626", ls="-.", lw=1.0, alpha=0.55)
    ax2.set_ylabel("Recovered med diag(Mdb)", color="#dc2626")
    ax2.tick_params(axis="y", labelcolor="#dc2626")
    ax2.set_ylim(0.20, 0.90)
    ax.axvline(2.5, color="#111827", ls=":", lw=1.3, alpha=0.75)
    ax.annotate(
        "Auto-selected\nlag_DB = 2.50 fr\n(1.25 ms phys)",
        xy=(2.5, sub0[np.isclose(sub0[:, 0], 2.5), 2][0]),
        xytext=(1.60, 0.365),
        fontsize=8.0,
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#111827", lw=1.1),
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#94a3b8", alpha=0.9),
    )
    ax.set_xlabel("Causal DM2 → WFS B Plant Lag [Stage-2 Frames @ 2 kHz]")
    ax.set_ylabel("Held-Out Whitened Forward R²_w (med)")
    ax.set_title("(b) Causal Plant Lag Identification Surface")
    ax.set_ylim(0.0, 0.46)
    ax.grid(True, alpha=0.28)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="lower right", fontsize=7.8, framealpha=0.92)

    ax = axes[1, 0]
    og_ref = fits.getdata(cdir_pred5 / "og_selfrm.fits").ravel()
    ax.plot(mx, og_ref, "k--", lw=1.6, label=f"Active selfRM ({np.median(og_ref):.3f})")
    ax.plot(mx, method_bench["pred_4s"]["w_d"], "-", color="#1d4ed8", lw=2.0, label=f"PSOL Predictive, 0-4s clean (med={method_bench['pred_4s']['w_med']:.3f})")
    ax.plot(mx, method_bench["pred_5s"]["w_d"], "-", color="#60a5fa", lw=1.4, alpha=0.85, label=f"PSOL Predictive, full 5s (med={method_bench['pred_5s']['w_med']:.3f})")
    ax.plot(mx, method_bench["int_open"]["w_d"], "-.", color="#059669", lw=1.5, label=f"Integrator, LLOWFS OPEN (med={method_bench['int_open']['w_med']:.3f})")
    ax.plot(mx, method_bench["int_closed"]["w_d"], ":", color="#dc2626", lw=1.6, label=f"Integrator, LLOWFS CLOSED (med={method_bench['int_closed']['w_med']:.3f})")
    ax.axvspan(-0.5, 3.5, color="#fef3c7", alpha=0.55, zorder=0)
    ax.text(1.5, 0.95, "Low-order\nZPO/LLOWFS\nzone", ha="center", va="top", fontsize=7.6, color="#92400e", fontweight="bold")
    ax.set_xlabel("Stage-2 DM Mode Index")
    ax.set_ylabel("Recovered Modal Gain diag(Mdb)")
    ax.set_title("(c) AR(4) W(z) Sensitivity Across AO Control Regimes")
    ax.set_xlim(-0.5, dD - 0.5)
    ax.set_ylim(0.0, 1.02)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", fontsize=7.7, framealpha=0.92)

    ax = axes[1, 1]
    ts_s = [r["t_s"] for r in conv_sums]
    ax.plot(ts_s, [r["geom_cos_med"] for r in conv_sums], "o-", color="#7c3aed", lw=2.1, ms=6, label="DM2→DM1 Geom Cosine (med)")
    ax.plot(ts_s, [r["r2_a_raw_med"] for r in conv_sums], "s-", color="#059669", lw=2.0, ms=5.8, label="Virtual Upstream R²_A (med)")
    ax.plot(ts_s, [r["r2_ol_raw_med"] for r in conv_sums], "^--", color="#d97706", lw=1.8, ms=5.8, label="Pseudo-OL R²_OL (med)")
    ax.plot(ts_s, [r["cross_rel_err"] for r in conv_sums], "d:", color="#dc2626", lw=1.8, ms=5.5, label="Cross-check ||Mab Mda - Mdb|| / ||Mdb||")
    ax.set_xlabel("Integration Window [s physical] (@ 1 kHz Stage-1 reference)")
    ax.set_ylabel("Accuracy Metric / Relative Consistency Error")
    ax.set_title("(d) Sample-Size Convergence (Clean Stationary Window)")
    ax.set_ylim(0.15, 1.02)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="center right", fontsize=8.0, framealpha=0.92)
    fig2.savefig(out_dir / "calib_2wfs1dm_whitening_lag_regimes_2x2.png", dpi=180)
    plt.close(fig2)


def plot_offload_and_zpo(base_cal: Path, out_dir: Path, offload: dict[str, Any]) -> None:
    """Render Figure 3: Virtual DM2->DM1 offload fidelity and ZPO wind-up diagnosis."""
    dD = int(offload["dD"])
    mx = np.arange(dD)
    dm2m = offload["dm2m"]
    cos4, cos5, scl4 = offload["cos4"], offload["cos5"], offload["scl4"]
    map_dm2, map_dm1, map_res = offload["map_dm2"], offload["map_dm1"], offload["map_res"]
    res_5iter = float(offload["res_5iter"])
    stats = offload["offload_stats"]

    d2c, t2 = load_tlm_2d(base_cal / "telemetry", "aol2_dmC")
    d3c, t3 = load_tlm_2d(base_cal / "telemetry", "aol3_dmC")
    t2_p = (t2 - t2[0]) / (t2[-1] - t2[0]) * 5.0
    t3_p = (t3 - t3[0]) / (t3[-1] - t3[0]) * 5.0
    rms_d2c = np.sqrt(np.mean(d2c[:, dm2m] ** 2, axis=1)) * 2000.0
    rms_d3c = np.sqrt(np.mean(d3c[:, dm2m] ** 2, axis=1)) * 2000.0

    fig3 = plt.figure(figsize=(14.0, 9.0), constrained_layout=True)
    outer = GridSpec(2, 1, figure=fig3, height_ratios=[1.0, 1.02])
    top_gs = outer[0].subgridspec(1, 2, wspace=0.22)
    bot_gs = outer[1].subgridspec(1, 3, wspace=0.16)
    fig3.suptitle(
        "Virtual DM2 → DM1 Offload Calibration Fidelity & Stage-2/Stage-3 ZPO Transient Diagnosis",
        fontsize=12.4,
        fontweight="bold",
    )

    ax_a = fig3.add_subplot(top_gs[0, 0])
    ax_a.plot(mx, cos4, "o-", color="#1d4ed8", lw=1.9, ms=4.5, label=f"0-4s Clean Cosine (med={np.median(cos4):.3f})")
    ax_a.plot(mx, cos5, "s--", color="#93c5fd", lw=1.3, ms=3.5, label=f"Full 5s Cosine (med={np.median(cos5):.3f})")
    ax_a.plot(mx, scl4, "^:", color="#059669", lw=1.6, ms=4.2, label=f"Amplitude Ratio Mda/M_geom (med={np.median(scl4):.2f})")
    ax_a.axhline(1.0, color="#64748b", ls=":", lw=1.0)
    ax_a.set_xlabel("Stage-2 DM Mode Index")
    ax_a.set_ylabel("Column Cosine Similarity / Amplitude Ratio")
    ax_a.set_title("(a) Telemetry Mda_virt vs Independent Actuator Geometry (M_geom)")
    ax_a.set_xlim(-0.5, dD - 0.5)
    ax_a.set_ylim(0.20, 1.15)
    ax_a.grid(True, alpha=0.28)
    ax_a.legend(loc="lower left", fontsize=8.0, framealpha=0.92)

    ax_b = fig3.add_subplot(top_gs[0, 1])
    ax_b.plot(t2_p[::10], rms_d2c[::10], color="#1d4ed8", lw=1.6, label="Stage-2 DM2 (aol2_dmC) OPD RMS")
    ax_b.plot(t3_p[::3], rms_d3c[::3], color="#dc2626", lw=1.6, label="Stage-3 LLOWFS (aol3_dmC) OPD RMS")
    ax_b.axvspan(3.5, 5.0, color="#fee2e2", alpha=0.45, label="Full 5s held-out test split (3.5-5.0 s)")
    ax_b.axvline(4.0, color="#059669", ls="--", lw=1.5, label="Stationary cutoff (t = 4.0 s)")
    ax_b.annotate(
        "t ≈ 4.85 s: Stage-2/Stage-3 ZPO\noptical-gain wind-up (24× LLOWFS jump)\n→ unobserved by aol2_modevalDM!",
        xy=(4.83, 195),
        xytext=(1.25, 165),
        fontsize=8.0,
        fontweight="bold",
        color="#991b1b",
        arrowprops=dict(arrowstyle="->", color="#991b1b", lw=1.2),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#fca5a5", alpha=0.92),
    )
    ax_b.set_xlabel("Physical Simulation Time [s]")
    ax_b.set_ylabel("DM2 Channel OPD RMS [nm]")
    ax_b.set_title("(b) Stage-2 / Stage-3 ZPO Wind-Up at t = 4.85 s")
    ax_b.set_xlim(0.0, 5.0)
    ax_b.set_ylim(0.0, 310.0)
    ax_b.grid(True, alpha=0.28)
    ax_b.legend(loc="upper left", fontsize=7.6, framealpha=0.92)

    vlim = float(np.nanpercentile(np.abs(map_dm2), 99.5))
    titles_b = [
        f"(c) Live Stage-2 DM2 OPD (40 modes)\nRMS = {stats['snap_in_nm']:.1f} nm",
        f"(d) Blind Telemetry DM1 Offload (Mda_virt·d)\nZero DM geometry input | cos = {np.median(cos4):.3f}",
        f"(e) Residual OPD After 1-Shot Offload\nRMS = {stats['snap_res_1shot_nm']:.1f} nm ({stats['snap_red_1shot_pct']:.1f}% red; 5-iter CL: {res_5iter:.1f} nm)",
    ]
    for idx_p, (m2d, ttl) in enumerate(zip([map_dm2, map_dm1, map_res], titles_b)):
        ax_p = fig3.add_subplot(bot_gs[0, idx_p])
        im = ax_p.imshow(m2d, origin="lower", cmap="RdBu_r", vmin=-vlim, vmax=vlim, interpolation="nearest")
        ax_p.set_title(ttl, fontsize=9.6, fontweight="bold")
        ax_p.set_xlabel("DM1 Actuator X")
        if idx_p == 0:
            ax_p.set_ylabel("DM1 Actuator Y")
        cb = fig3.colorbar(im, ax=ax_p, fraction=0.046, pad=0.03)
        cb.set_label("OPD [nm]", fontsize=8.5)
    fig3.savefig(out_dir / "calib_2wfs1dm_offload_and_zpo_2x3.png", dpi=180)
    plt.close(fig3)


def plot_method_comparison(
    out_dir: Path,
    method_bench: dict[str, dict[str, Any]],
    dD: int,
) -> None:
    """Render Figure 4: Multi-rate signatures & Frequency-Domain vs W(z) vs OLS."""
    mx = np.arange(dD)
    fig4, axes4 = plt.subplots(2, 2, figsize=(13.8, 8.9), constrained_layout=True)
    fig4.suptitle(
        "Beyond W(z) — Root-Cause Physics & Exact-Window Frequency-Domain AO-Dynamics Calibration",
        fontsize=12.4,
        fontweight="bold",
    )

    ax = axes4[0, 0]
    ev_op = method_bench["int_open"]
    lags_ms = ev_op["lags_ab_ms"]
    ax.plot(lags_ms, ev_op["hf_corrs"], "o-", color="#1d4ed8", lw=2.0, ms=5.0, label="High-freq diff corr(ΔB_OL, ΔA)")
    ax.axvline(-0.25, color="#059669", ls="--", lw=1.4, label="Exact exposure midpoint (-0.25 ms)")
    ax.axvline(+1.50, color="#dc2626", ls=":", lw=1.5, label="Stage-1 DM1 latency step (+1.50 ms)")
    ax.annotate(
        "WFS A (1.0 ms) vs\nWFS B (0.5 ms)\nmidpoint = -0.25 ms",
        xy=(-0.25, ev_op["hf_corrs"][np.isclose(lags_ms, -0.25)][0]),
        xytext=(-1.90, 0.112),
        fontsize=7.7,
        fontweight="bold",
        color="#065f46",
        arrowprops=dict(arrowstyle="->", color="#059669", lw=1.1),
        bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#a7f3d0", alpha=0.92),
    )
    ax.annotate(
        "Stage-1 DM1 step\nvisible in B_OL\nat +1.50 ms!",
        xy=(1.50, ev_op["hf_corrs"][np.isclose(lags_ms, 1.50)][0]),
        xytext=(0.15, 0.123),
        fontsize=7.7,
        fontweight="bold",
        color="#991b1b",
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.1),
        bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#fecaca", alpha=0.92),
    )
    ax.set_xlabel("Inter-WFS Shift lag_AB [ms physical] (Stage-2 B_OL vs Stage-1 A)")
    ax.set_ylabel("Median High-Freq Cross-Correlation")
    ax.set_title("(a) Multi-Rate Optical & Stage-1 DM1 Timing Signatures")
    ax.set_ylim(0.02, 0.148)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower center", fontsize=7.6, framealpha=0.92)

    ax = axes4[0, 1]
    mb_cl = method_bench["int_closed"]
    ax.plot(mx, mb_cl["og_true"], "k--", lw=1.6, label=f"Active selfRM ({mb_cl['srm_med']:.3f})")
    ax.plot(mx, mb_cl["d_freq"], "-", color="#059669", lw=2.1, label=f"Freq-Domain Exact-Win [20-480 Hz] (med={mb_cl['freq_med']:.3f}, err={mb_cl['freq_err_pct']:.1f}%)")
    ax.plot(mx, mb_cl["w_d"], "-.", color="#2563eb", lw=1.5, label=f"AR(4) W(z) (med={mb_cl['w_med']:.3f}, err={mb_cl['w_err_pct']:.1f}%)")
    ax.plot(mx, mb_cl["d_ols"], ":", color="#dc2626", lw=1.5, label=f"Unwhitened OLS (med={mb_cl['ols_med']:.3f}, err={mb_cl['ols_err_pct']:.1f}%)")
    ax.axvspan(-0.5, 3.5, color="#fef3c7", alpha=0.55, zorder=0)
    ax.set_xlabel("Stage-2 DM Mode Index")
    ax.set_ylabel("Recovered Modal Gain diag(Mdb)")
    ax.set_title("(b) Pure Integrator (LLOWFS CLOSED): Fixes 22% Bias & Tip/Tilt")
    ax.set_xlim(-0.5, dD - 0.5)
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", fontsize=7.6, framealpha=0.92)

    ax = axes4[1, 0]
    mb_p5 = method_bench["pred_5s"]
    ax.plot(mx, mb_p5["og_true"], "k--", lw=1.6, label=f"Active selfRM ({mb_p5['srm_med']:.3f})")
    ax.plot(mx, mb_p5["d_freq"], "-", color="#059669", lw=2.1, label=f"Freq-Domain Exact-Win [20-480 Hz] (med={mb_p5['freq_med']:.3f}, TT MAE={mb_p5['freq_tt_mae']:.2f})")
    ax.plot(mx, mb_p5["w_d"], "-.", color="#2563eb", lw=1.5, label=f"AR(4) W(z) (med={mb_p5['w_med']:.3f}, TT MAE={mb_p5['w_tt_mae']:.2f})")
    ax.plot(mx, mb_p5["d_ols"], ":", color="#dc2626", lw=1.5, label=f"Unwhitened OLS (med={mb_p5['ols_med']:.3f})")
    ax.axvspan(-0.5, 3.5, color="#fef3c7", alpha=0.55, zorder=0)
    ax.text(1.5, 0.96, "ZPO-immune\n(f ≥ 20 Hz)", ha="center", va="top", fontsize=7.6, color="#065f46", fontweight="bold")
    ax.set_xlabel("Stage-2 DM Mode Index")
    ax.set_ylabel("Recovered Modal Gain diag(Mdb)")
    ax.set_title("(c) PSOL Predictive (Full 5 s + ZPO Wind-Up): Low-Order Recovery")
    ax.set_xlim(-0.5, dD - 0.5)
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", fontsize=7.6, framealpha=0.92)

    ax = axes4[1, 1]
    rkeys = ["int_open", "int_closed", "pred_4s", "pred_5s"]
    rshort = ["Integrator\nLLOWFS Open", "Integrator\nLLOWFS Closed", "PSOL Pred.\nClean 0-4 s", "PSOL Pred.\nFull 5 s (+ZPO)"]
    xpos = np.arange(len(rkeys))
    wbar = 0.25
    b1 = ax.bar(xpos - wbar, [method_bench[k]["ols_err_pct"] for k in rkeys], width=wbar, color="#ef4444", alpha=0.85, label="Unwhitened OLS (zero ridge)")
    b2 = ax.bar(xpos, [method_bench[k]["w_err_pct"] for k in rkeys], width=wbar, color="#3b82f6", alpha=0.88, label="AR(4) Whitening W(z)")
    b3 = ax.bar(xpos + wbar, [method_bench[k]["freq_err_pct"] for k in rkeys], width=wbar, color="#10b981", alpha=0.92, label="Exact-Window Freq-Domain [20-480 Hz]")
    for bars in (b1, b2, b3):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2.0, h + 1.0, f"{h:.1f}%", ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    ax.set_xticks(xpos)
    ax.set_xticklabels(rshort, fontsize=8.4)
    ax.set_ylabel("Median diag(Mdb) Error vs Active selfRM [%]")
    ax.set_title("(d) Head-to-Head Accuracy Across All 4 AO Control Regimes")
    ax.set_ylim(0.0, 78.0)
    ax.grid(True, axis="y", alpha=0.28)
    ax.legend(loc="upper right", fontsize=8.0, framealpha=0.92)
    fig4.savefig(out_dir / "calib_2wfs1dm_method_comparison_2x2.png", dpi=180)
    plt.close(fig4)


def render_all_figures(
    base_cal: Path,
    out_dir: Path,
    sweeps: dict[str, Any],
    offload: dict[str, Any],
    method_bench: dict[str, dict[str, Any]],
) -> None:
    """Copy Figure 1 and render Figures 2-4 into out_dir."""
    configure_matplotlib()
    shutil.copy2(
        base_cal / "calib_2wfs1dm_summary_2x2.png",
        out_dir / "calib_2wfs1dm_summary_2x2.png",
    )
    dD = int(offload["dD"])
    plot_whitening_lag_regimes(out_dir, sweeps, method_bench, dD)
    plot_offload_and_zpo(base_cal, out_dir, offload)
    plot_method_comparison(out_dir, method_bench, dD)
