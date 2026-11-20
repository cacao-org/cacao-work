#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Figures 3-4: Learned AR(P) filter anatomy, poles, and modal PSD rejection."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

from .loader import compute_filter_freq_response

def plot_fig3_filter_anatomy(bundles: list[dict[str, Any]], out_dir: Path) -> None:
    """Figure 3: Learned AR(P) Filter Impulse Responses, Cauchy-Schwarz Lead & Freq Response."""
    pf_bundles = [b for b in bundles if b["filters"]]
    std_pf = [b for b in pf_bundles if not b["spec"]["is_ablation"]]
    fig, axes = plt.subplots(2, 2, figsize=(15.2, 9.6), constrained_layout=True)
    fig.suptitle(
        "Anatomy of Learned PSOL Wiener AR(P) Predictive Filters (aol1_arPFmat & aol2_arPFmat)\n"
        "(Cauchy–Schwarz Negative-Tail Extrapolation Explains Why AR(16) Unlocks Low-Order "
        "Phase Lead & Why Taps > 32 ms Saturate)",
        fontsize=11.5,
        fontweight="bold",
    )

    # (0,0) Stage-1 Low-Order (Modes 0..9) Learned Impulse Response w_k vs Lag [ms]
    ax = axes[0, 0]
    for b in pf_bundles:
        sp = b["spec"]
        f1 = b["filters"][1]
        lags_ms = np.arange(f1["order"], dtype=np.float64) * 1.0  # 1 kHz -> 1 ms/tap
        ax.plot(
            lags_ms,
            f1["w_lo"],
            color=sp["color"],
            ls=sp["ls"],
            marker=sp["marker"],
            ms=3.5 if f1["order"] <= 32 else 2.6,
            markevery=1 if f1["order"] <= 32 else 2,
            lw=1.7 if sp["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else 1.2,
            label=(
                f"{sp['short']} (Lead={f1['lo_lead_fr']:+.2f} fr, "
                f"‖w‖₂²={f1['lo_norm2']:.2f})"
            ),
        )
    ax.axhline(0.0, color="#64748b", lw=0.8, alpha=0.7)
    ax.axvspan(6.0, 16.0, color="#ecfdf5", alpha=0.6, zorder=0)
    ax.axvspan(32.0, 63.5, color="#f8fafc", alpha=0.8, zorder=0)
    ax.axvline(32.0, color="#94a3b8", ls=":", lw=1.0)
    ax.text(
        17.2,
        0.30,
        "Negative differentiating tail\n(k = 6..15 ms) builds phase\nlead at lower ‖w‖₂²",
        fontsize=7.6,
        color="#065f46",
    )
    ax.text(
        34.0,
        -0.11,
        "Taps 32–63 ms:\n< 2% of total energy",
        fontsize=7.6,
        color="#475569",
        fontweight="bold",
    )
    ax.set_xlim(-0.8, 63.8)
    ax.set_xlabel("Filter Tap Lag k [ms @ 1.0 kHz]")
    ax.set_ylabel("Mean Filter Weight w_k (Modes 0–9)")
    ax.set_title("Stage-1 Low-Order Impulse Response w_k Across AR(4)..AR(64)")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.92, fontsize=7.1)

    # (0,1) Effective Phase Lead vs L2 Noise Gain Squared (Cauchy-Schwarz Tradeoff)
    ax = axes[0, 1]
    cs_offsets = {
        "ar4": (-12, 8),
        "ar8": (8, 4),
        "ar16": (8, -6),
        "ar32": (8, -12),
        "ar32_n4096": (-52, -14),
        "ar64": (-38, 8),
        "ar64_n4096": (10, -4),
    }
    for stg, mk_off, lbl_s in ((1, "o", "Stage 1 (1 kHz)"), (2, "s", "Stage 2 (2 kHz)")):
        std_leads = [b["filters"][stg]["lo_lead_fr"] for b in std_pf]
        std_n2s = [b["filters"][stg]["lo_norm2"] for b in std_pf]
        ax.plot(
            std_n2s,
            std_leads,
            color="#0f172a" if stg == 1 else "#475569",
            ls="-" if stg == 1 else "--",
            lw=1.3,
            alpha=0.65,
            label=f"{lbl_s} trajectory (AR4→AR64)",
        )
        for b in pf_bundles:
            sp = b["spec"]
            xv = b["filters"][stg]["lo_norm2"]
            yv = b["filters"][stg]["lo_lead_fr"]
            ax.scatter(
                [xv],
                [yv],
                color=sp["color"],
                marker=mk_off if not sp["is_ablation"] else "*",
                s=115 if sp["is_ablation"] else 75,
                edgecolor="#0f172a",
                lw=0.8,
                zorder=5,
            )
            if stg == 1:
                dx, dy = cs_offsets.get(sp["key"], (6, 4))
                ax.annotate(
                    sp["short"],
                    (xv, yv),
                    textcoords="offset points",
                    xytext=(dx, dy),
                    fontsize=7.6,
                    fontweight="bold",
                    color=sp["color"],
                )
    ax.axhline(0.0, color="#94a3b8", ls=":", lw=0.9)
    ax.set_xlim(0.38, 0.725)
    ax.set_ylim(-0.85, 2.12)
    ax.set_xlabel("Low-Order Filter Noise-Gain Squared ‖w‖₂² (Lower = Less Noise)")
    ax.set_ylabel("Effective Low-Order Phase Lead −Σ k·w_k [frames]")
    ax.set_title("Cauchy–Schwarz Mechanism: Phase Lead vs. Noise Amplification")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", framealpha=0.92, fontsize=7.6)

    # (1,0) Frequency-Domain Amplitude & Phase Lead of Stage-1 Low-Order Filters
    ax = axes[1, 0]
    freqs = np.linspace(1.0, 120.0, 360)
    # Ideal pure phase lead for 2.40 frames @ 1 kHz: +2.40 * 360 * f / 1000 deg
    ideal_lead = 2.40 * 360.0 * (freqs / 1000.0)
    ax.plot(
        freqs,
        ideal_lead,
        color="#0f172a",
        ls=":",
        lw=1.6,
        label="Ideal Phase Lead (+2.40 fr lag)",
    )
    ax_mag = ax.twinx()
    for b in pf_bundles:
        sp = b["spec"]
        f1 = b["filters"][1]
        mag, ph = compute_filter_freq_response(f1["w_lo"], 1000.0, freqs)
        lw = 1.75 if sp["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else 1.2
        ax.plot(freqs, ph, color=sp["color"], ls=sp["ls"], lw=lw, label=f"{sp['short']} ∠H(f)")
        ax_mag.plot(freqs, mag, color=sp["color"], ls=":", lw=1.05, alpha=0.58)
    ax.axhline(0.0, color="#64748b", lw=0.7)
    ax.set_xlim(1.0, 110.0)
    ax.set_ylim(-65, 65)
    ax_mag.set_ylim(0.2, 1.8)
    ax_mag.set_ylabel("Amplitude Gain |H(f)| (dotted)", color="#475569", fontsize=8.5)
    ax_mag.spines["right"].set_visible(True)
    ax_mag.spines["right"].set_color("#94a3b8")
    ax.set_xlabel("Temporal Frequency [Hz]")
    ax.set_ylabel("Filter Phase Lead ∠H(f) [deg]")
    ax.set_title("Stage-1 Low-Order Frequency Response (1–110 Hz): Phase & Gain")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="upper right", ncol=2, framealpha=0.92, fontsize=6.9)

    # (1,1) Cumulative Tap Energy vs Physical Memory Horizon [ms]
    ax = axes[1, 1]
    for stg, fs_hz, alpha_s in ((1, 1000.0, 0.95), (2, 2000.0, 0.65)):
        for b in std_pf:
            sp = b["spec"]
            fd = b["filters"][stg]
            t_ms = (np.arange(fd["order"], dtype=np.float64) + 1.0) * (1000.0 / fs_hz)
            ax.plot(
                t_ms,
                fd["cum_tap_energy"] * 100.0,
                color=sp["color"],
                ls="-" if stg == 1 else "--",
                marker=sp["marker"],
                ms=3.2 if fd["order"] <= 32 else 2.5,
                markevery=1 if fd["order"] <= 32 else 3,
                lw=1.5 if stg == 1 else 1.15,
                alpha=alpha_s,
                label=(
                    f"Stg{stg} {sp['short']}"
                    if (stg == 1 or sp["order"] in (16, 32, 64))
                    else None
                ),
            )
    ax.axhline(99.0, color="#64748b", ls=":", lw=1.0)
    ax.axvline(32.0, color="#94a3b8", ls=":", lw=0.9)
    ax.text(35.0, 94.8, "99% tap energy\n(>98% inside 32 ms)", fontsize=7.5, color="#475569")
    ax.set_xlim(0.5, 64.5)
    ax.set_ylim(78, 100.8)
    ax.set_xlabel("Memory Horizon [ms] (k+1 taps)")
    ax.set_ylabel("Cumulative Filter Tap Energy Σ w_j² / ‖w‖₂² [%]")
    ax.set_title("Cumulative Filter Energy vs. Physical Memory Window (Out to 64 ms)")
    ax.grid(True, alpha=0.28)
    ax.legend(loc="lower right", ncol=2, framealpha=0.92, fontsize=7.2)

    fig.savefig(out_dir / "ar_order_filter_weights_and_freq_2x2.png")
    plt.close(fig)


def plot_fig4_modal_and_psd(bundles: list[dict[str, Any]], out_dir: Path) -> None:
    """Figure 4: Temporal PSD Rejection Transfer Functions & Spatial Modal Residual Spectra."""
    fig, axes = plt.subplots(2, 2, figsize=(14.8, 9.4), constrained_layout=True)
    fig.suptitle(
        "Frequency-Domain Rejection (1 kHz / 2 kHz Telemetry PSDs) & Spatial Modal Residual "
        "Spectra\n"
        "(Direct Computation from Saved 5.0 s Closed-Loop Modal Telemetry Cubes)",
        fontsize=11.5,
        fontweight="bold",
    )

    # (0,0) Stage-1 (1 kHz) Low-Order (Modes 0..19) & Total Rejection PSD
    for col_i, (stg, fs_hz, fmax) in enumerate(((1, 1000.0, 480.0), (2, 2000.0, 950.0))):
        ax = axes[0, col_i]
        # Reference OL PSD from AR(16)
        ref_psd = bundles[3]["psds"][stg]
        f = ref_psd["freqs"]
        m_f = (f >= 2.0) & (f <= fmax)
        ax.loglog(
            f[m_f],
            ref_psd["psd_ol"][m_f],
            color="#0f172a",
            ls=":",
            lw=1.5,
            alpha=0.75,
            label="PSOL Open-Loop (Ref)",
        )
        for b in bundles:
            if stg not in b["psds"]:
                continue
            sp = b["spec"]
            pd = b["psds"][stg]
            lw = 1.75 if sp["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else 1.2
            ax.loglog(
                pd["freqs"][m_f],
                pd["psd_wfs"][m_f],
                color=sp["color"],
                ls=sp["ls"],
                lw=lw,
                alpha=0.9,
                label=sp["short"],
            )
        ax.set_xlim(2.0, fmax)
        ax.set_xlabel("Temporal Frequency [Hz]")
        ax.set_ylabel("Summed Modal WFS PSD [nm²/Hz]")
        stg_name = "Stage 1 (AO3k, 1.0 kHz)" if stg == 1 else "Stage 2 (SCExAO, 2.0 kHz)"
        ax.set_title(f"{stg_name} — Closed-Loop Residual Temporal PSD")
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(loc="lower left", ncol=2, framealpha=0.92, fontsize=7.0)

    # Bottom row: Spatial Modal WFS Residual RMS vs Mode Index (binned for smooth comparison)
    for col_i, stg in enumerate((1, 2)):
        ax = axes[1, col_i]
        # Log-spaced mode bins for crystal-clear curves across 1965 / 1255 modes
        ref_v = bundles[3]["modal_rms"][stg].get("mvalOLrms")
        n_m = len(ref_v) if ref_v is not None else 1255
        edges = np.unique(
            np.concatenate(
                [
                    np.arange(0, 21),
                    np.geomspace(21, n_m, 45).astype(int),
                ]
            )
        )
        centers = 0.5 * (edges[:-1] + edges[1:])

        def bin_rms(vec: np.ndarray) -> np.ndarray:
            out_v = np.zeros(len(edges) - 1, dtype=np.float64)
            for j in range(len(edges) - 1):
                sl = vec[edges[j] : edges[j + 1]]
                out_v[j] = np.sqrt(np.mean(sl**2)) if sl.size else np.nan
            return out_v

        if ref_v is not None:
            ax.loglog(
                centers + 1.0,
                np.maximum(bin_rms(ref_v), 1e-3),
                color="#0f172a",
                ls=":",
                lw=1.4,
                alpha=0.7,
                label=f"PSOL OL ({np.linalg.norm(ref_v):.0f} nm)",
            )
        for b in bundles:
            v_wfs = b["modal_rms"][stg].get("mvalWFSrms")
            if v_wfs is None:
                continue
            sp = b["spec"]
            lw = 1.8 if sp["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else 1.2
            ax.loglog(
                centers + 1.0,
                np.maximum(bin_rms(v_wfs), 1e-3),
                color=sp["color"],
                ls=sp["ls"],
                lw=lw,
                alpha=0.92,
                label=f"{sp['short']} ({np.linalg.norm(v_wfs):.1f} nm)",
            )
        ax.set_xlim(1.0, float(n_m))
        ax.set_xlabel("Spatial Mode Index (1-indexed, Binned RMS)")
        ax.set_ylabel("Closed-Loop WFS Modal RMS [nm]")
        stg_name = "Stage 1 (AO3k, 1965 Modes)" if stg == 1 else "Stage 2 (SCExAO, 1255 Modes)"
        ax.set_title(f"{stg_name} — Spatial Modal Residual Spectrum")
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(loc="upper right", ncol=2, framealpha=0.92, fontsize=6.9)

    fig.savefig(out_dir / "ar_order_modal_and_psd_2x2.png")
    plt.close(fig)
