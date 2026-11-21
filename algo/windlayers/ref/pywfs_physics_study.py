#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Generate summary figures for:
  1. fig_pywfs_selfcal_and_leakage.png:
     - Coherent 2-D PyWFS T_I(f) vs. analytic sideband model & cacaosim measurements
     - Inter-pupil diffracted flux thermometer (flux_in vs. true WFS Strehl across B/C/F/O)
     - Coherent inter-pupil Hilbert-tail phase leakage vs. pupil separation S/D
     - Distance error reduction: old analytic (cf=1) vs. upgraded coherent auto-cal C unit
  2. fig_eof_wind_and_prior.png:
     - Multi-layer PF cube nonlinearity vs. linear Gram Sigma_yx
     - AO3k Stage-1 walk-forward cold-start curves (N_train = 0..14500) across Blocks 0, 1, 2, 4, 8
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits

REPO = Path(__file__).resolve().parents[3]
WORK = REPO / "_work"
WL_DIR = REPO / "algo" / "windlayers"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wl_ref as wl  # noqa: E402


def make_pywfs_figure(c_results: dict[str, dict[str, list[float]]]) -> None:
    """Create 2x2 figure summarizing PyWFS coherent T_I, flux_in Strehl, leakage & validation."""
    T1 = WORK / "wind_layers" / "truth1"
    C1 = WORK / "wind_layers" / "cl1k"
    n, n2 = 32, 64
    dx = 0.068333 * 4
    diam = 30.0 * dx
    mask32 = wl.pupil_mask(n, 30.0, 0.3)

    # Panel (0,0): Flat-WF T_I(f) radial profiles (cacaosim vs coherent 64x64 vs analytic)
    amp1 = fits.getdata(T1 / "outarrayamp.fits")[:2000].astype(np.float64)
    wa = fits.getdata(T1 / "wfs_a.fits")[:2000].astype(np.float64)
    sa = wa[:, :n, :n] + wa[:, :n, n:] + wa[:, n:, :n] + wa[:, n:, n:]
    dsa = wl.demean(sa, mask32, relative=True)
    dta = wl.demean(wl.bin_cube(amp1**2, 4), mask32, relative=True)
    fa, fta = np.fft.fft2(dsa, s=(n2, n2)), np.fft.fft2(dta, s=(n2, n2))
    tf_sim = (fa * np.conj(fta)).mean(axis=0).real / np.maximum(
        (np.abs(fta) ** 2).mean(axis=0), 1e-30
    )

    # Coherent 64x64 model from mask32 only (matches windlayers_core.h)
    nf = 64
    off = (nf - n) // 2
    pix_ld = nf / 30.0
    iu = np.fft.fftfreq(nf) * nf
    u_g, v_g = np.meshgrid(iu, iu)
    alpha = np.pi * 0.5

    def edge1d(u: np.ndarray) -> np.ndarray:
        au = np.abs(u)
        sh = np.sin(0.5 * alpha) / (0.5 * alpha)
        re = np.where(
            au >= 0.5,
            sh * np.cos(alpha * au),
            2.0 * np.cos(alpha * au) * np.sin(0.5 * alpha) / alpha,
        )
        im = np.where(
            au >= 0.5,
            -sh * np.sin(alpha * au),
            -2.0 * (1.0 - np.cos(alpha * au) * np.cos(0.5 * alpha)) / alpha,
        )
        return re + 1j * im

    masks = np.array(
        [
            edge1d(u_g - 3.0 * pix_ld * (1.0 / lr) * np.cos(2 * np.pi * (k + 0.5) / 16))
            * edge1d(v_g - 3.0 * pix_ld * (1.0 / lr) * np.sin(2 * np.pi * (k + 0.5) / 16))
            for lr in (0.9, 1.0, 1.1)
            for k in range(16)
        ],
        dtype=np.complex64,
    )

    def run64(a: np.ndarray, p: np.ndarray) -> np.ndarray:
        fld = np.zeros((nf, nf), dtype=np.complex64)
        fld[off : off + n, off : off + n] = (mask32 * a * np.exp(1j * p)).astype(np.complex64)
        det = np.mean(np.abs(np.fft.ifft2(np.fft.fft2(fld)[None] * masks)) ** 2, axis=0)
        return det[:n, :n] + det[:n, n:] + det[n:, :n] + det[n:, n:]

    rng = np.random.default_rng(123)
    s0 = run64(np.ones((n, n)), np.zeros((n, n)))
    noise = rng.normal(0.0, 0.05, size=(64, n, n))
    ic = np.array([run64(np.sqrt(1.0 + noise[b]), np.zeros((n, n))) for b in range(64)])
    di_c = (ic / np.where(s0 > 0, s0, 1.0) - 1.0) * mask32
    di_c -= (di_c.sum(axis=(1, 2)) / mask32.sum())[:, None, None] * mask32
    dt_c = noise * mask32
    dt_c -= (dt_c.sum(axis=(1, 2)) / mask32.sum())[:, None, None] * mask32
    fc, ft = np.fft.fft2(di_c, s=(64, 64)), np.fft.fft2(dt_c, s=(64, 64))
    tf_coh = (fc * np.conj(ft)).mean(axis=0).real / np.maximum(
        (np.abs(ft) ** 2).mean(axis=0), 1e-30
    )
    tf_coh = 0.25 * (
        tf_coh
        + np.roll(tf_coh[::-1, :], 1, 0)
        + np.roll(tf_coh[:, ::-1], 1, 1)
        + np.roll(np.roll(tf_coh[::-1, ::-1], 1, 0), 1, 1)
    )
    tf_coh = 0.5 * (tf_coh + tf_coh.T)
    tf_ana = wl.pyr_tint(n2, dx, diam, 3.0, 0.6)

    f = np.fft.fftfreq(n2, dx) * diam
    fx, fy = np.meshgrid(f, f)
    fr = np.hypot(fx, fy)
    bins = np.linspace(0.5, 13.5, 14)
    fc_pts = 0.5 * (bins[:-1] + bins[1:])

    def radial_ax_dg(tf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ax_v, dg_v = [], []
        for lo, hi in zip(bins[:-1], bins[1:]):
            ring = (fr >= lo) & (fr < hi)
            ax = ring & (np.minimum(np.abs(fx), np.abs(fy)) < 1.2)
            dg = ring & (np.abs(np.abs(fx) - np.abs(fy)) < 1.5)
            ax_v.append(tf[ax].mean() if ax.any() else np.nan)
            dg_v.append(tf[dg].mean() if dg.any() else np.nan)
        return np.array(ax_v), np.array(dg_v)

    # Panel (1,0): Coherent inter-pupil Hilbert-tail phase leakage vs pupil separation S/D
    # Use exact integer pupil shifts sh4 so cutout alignment has zero sub-pixel rounding artifact.
    nwf = 128
    diam_px = 0.9375 * nwf
    c_w = (nwf - 1) / 2.0
    yy, xx = np.mgrid[0:nwf, 0:nwf]
    r_w = np.hypot(xx - c_w, yy - c_w)
    pup128 = ((r_w <= diam_px / 2.0) & (r_w >= 0.30 * diam_px / 2.0)).astype(np.float64)
    x128 = (xx - c_w) / diam_px
    cos2 = np.cos(2 * np.pi * 2.0 * x128)
    x32 = (np.arange(n) - (n - 1) / 2.0) / 30.0
    x32_g, _ = np.meshgrid(x32, x32)
    c2_32 = np.cos(2 * np.pi * 2.0 * x32_g)
    cm = c2_32 - c2_32[mask32 > 0].mean()
    nf4 = 512
    off4 = (nf4 - nwf) // 2
    pix4 = nf4 / diam_px
    iu4 = np.fft.fftfreq(nf4) * nf4
    u4, v4 = np.meshgrid(iu4, iu4)
    sh_list = list(range(64, 122, 3))
    sep_d_arr, zleak_arr, ziso_arr = [], [], []
    # Precompute input fields for 0, +0.5*cos2, -0.5*cos2
    fcs = []
    for amp_p in (0.0, +0.5, -0.5):
        fl = np.zeros((nf4, nf4), dtype=np.complex64)
        fl[off4 : off4 + nwf, off4 : off4 + nwf] = (pup128 * np.exp(1j * amp_p * cos2)).astype(
            np.complex64
        )
        fcs.append(np.fft.fft2(fl))
    # Isolated-quadrant control (zero inter-pupil interference -> odd_rms ~ 1e-17)
    det_iso = [np.zeros((nwf, nwf), dtype=np.float64) for _ in range(3)]
    for k in range(16):
        ang = 2 * np.pi * (k + 0.5) / 16
        du = u4 - 3.0 * pix4 * np.cos(ang)
        dv = v4 - 3.0 * pix4 * np.sin(ang)
        for qx in (-1, 1):
            for qy in (-1, 1):
                qmask = ((qx * du > 0) & (qy * dv > 0)).astype(np.float32)
                for idx_f in range(3):
                    img = np.abs(np.fft.ifft2(fcs[idx_f] * qmask)) ** 2
                    det_iso[idx_f] += img[off4 : off4 + nwf, off4 : off4 + nwf]
    b_iso = [d.reshape(n, 4, n, 4).mean(axis=(1, 3)) / 16.0 for d in det_iso]
    odd_iso = 0.5 * (b_iso[1] - b_iso[2]) / np.where(
        b_iso[0] > 0.05 * b_iso[0].max(), b_iso[0], 1.0
    )
    coef_iso = (odd_iso[mask32 > 0] * cm[mask32 > 0]).sum() / (cm[mask32 > 0] ** 2).sum()
    z_iso_km = coef_iso / (2 * np.pi * 0.75e-6 * (2.0 / 8.2) ** 2 * 0.5) / 1e3

    for sh4 in sh_list:
        sep = 2.0 * sh4 / nf4
        sep_d = (2.0 * sh4) / diam_px
        a4 = np.pi * sep
        dets = [np.zeros((nf4, nf4), dtype=np.float64) for _ in range(3)]
        for k in range(16):
            ang = 2 * np.pi * (k + 0.5) / 16
            du = u4 - 3.0 * pix4 * np.cos(ang)
            dv = v4 - 3.0 * pix4 * np.sin(ang)
            m4 = np.exp(-1j * a4 * (np.abs(du) + np.abs(dv))).astype(np.complex64)
            for idx_f in range(3):
                dets[idx_f] += np.abs(np.fft.ifft2(fcs[idx_f] * m4)) ** 2
        bins3 = []
        for d in dets:
            d /= 16.0
            s4 = np.zeros((nwf, nwf), dtype=np.float64)
            for sx in (-sh4, sh4):
                for sy in (-sh4, sh4):
                    s4 += d[off4 + sy : off4 + sy + nwf, off4 + sx : off4 + sx + nwf]
            bins3.append(s4.reshape(n, 4, n, 4).mean(axis=(1, 3)))
        i0_4, ip_4, im_4 = bins3
        odd4 = 0.5 * (ip_4 - im_4) / np.where(i0_4 > 0.05 * i0_4.max(), i0_4, 1.0)
        coef = (odd4[mask32 > 0] * cm[mask32 > 0]).sum() / (cm[mask32 > 0] ** 2).sum()
        zlk = coef / (2 * np.pi * 0.75e-6 * (2.0 / 8.2) ** 2 * 0.5)
        sep_d_arr.append(sep_d)
        zleak_arr.append(zlk / 1e3)
        ziso_arr.append(z_iso_km)

    # Build figure
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.6), constrained_layout=True)
    fig.suptitle(
        "Pyramid WFS Intensity Physics: Coherent T_I(f), Auto-Strehl & Inter-Pupil Phase Leakage",
        fontsize=12.5,
        fontweight="bold",
    )

    # (0,0) Flat-WF T_I(f)
    ax = axes[0, 0]
    s_ax, s_dg = radial_ax_dg(tf_sim)
    c_ax, c_dg = radial_ax_dg(tf_coh)
    a_ax, a_dg = radial_ax_dg(tf_ana)
    ax.plot(fc_pts, s_ax, "-k", lw=2.2, label="cacaosim PyWFS (axis)")
    ax.plot(fc_pts, c_ax, "--o", color="#059669", lw=1.8, ms=4, label="Coherent FFT (axis)")
    ax.plot(fc_pts, a_ax, ":k", lw=1.5, alpha=0.65, label="Analytic sideband (axis)")
    ax.plot(fc_pts, s_dg, "-", color="#2563eb", lw=2.2, label="cacaosim PyWFS (diag)")
    ax.plot(fc_pts, c_dg, "--s", color="#d97706", lw=1.8, ms=4, label="Coherent FFT (diag)")
    ax.plot(
        fc_pts, a_dg, ":", color="#2563eb", lw=1.5, alpha=0.65, label="Analytic sideband (diag)"
    )
    ax.set_xlabel("|f| [cycles / aperture]")
    ax.set_ylabel("Intensity response T_I(f)")
    ax.set_title("(a) Flat-WF T_I(f): Coherent Model Eliminates 10-20% Bias")
    ax.set_ylim(0.15, 0.95)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7.5, ncol=2, loc="upper right")

    # (0,1) Inter-pupil flux thermometer
    ax = axes[0, 1]
    s_true = np.array([1.00, 0.60, 0.26, 0.02])
    fl_meas = np.array([0.9040, 0.9187, 0.9344, 0.9561])
    labels_fl = [
        ("Case B\n(Flat WF)", (-44, 12)),
        ("Case C\n(32x32 CL)", (10, 4)),
        ("Case F\n(16x16 CL)", (-66, -24)),
        ("Case O\n(Open loop)", (-4, -28)),
    ]
    ax.scatter(
        s_true, fl_meas, s=90, color="#2563eb", zorder=5, label="Measured geometric flux_in"
    )
    for st, fm, (lb, ofs) in zip(s_true, fl_meas, labels_fl):
        ax.annotate(lb, (st, fm), textcoords="offset points", xytext=ofs, fontsize=8)
    s_line = np.linspace(0.0, 1.0, 50)
    fl_mod = 0.9620 - s_line * (0.9620 - 0.8882)
    ax.plot(s_line, fl_mod, "--", color="#059669", lw=2.0, label="Coherent C model (flat..halo)")
    ax.set_xlabel("True WFS Strehl S = exp(-sigma_phi^2)")
    ax.set_ylabel("Geometric pupil flux fraction flux_in")
    ax.set_title("(b) Zero-Parameter Strehl Thermometer from Mean WFS Frame")
    ax.set_xlim(-0.08, 1.12)
    ax.set_ylim(0.882, 0.970)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8.5, loc="lower left")

    # (1,0) Coherent inter-pupil Hilbert-tail phase leakage
    ax = axes[1, 0]
    ax.plot(
        sep_d_arr,
        zleak_arr,
        "-o",
        color="#dc2626",
        lw=2.1,
        ms=4.5,
        label="Coherent 4-facet PyWFS (odd phase leakage)",
    )
    ax.plot(
        sep_d_arr,
        ziso_arr,
        "--",
        color="#059669",
        lw=2.0,
        label="Isolated quadrants (no overlap: 0.0 km)",
    )
    ax.axvline(sep_d_arr[0], color="#2563eb", lw=1.1, ls=":", alpha=0.8)
    ax.annotate(
        f"cacaosim (S = {sep_d_arr[0]:.2f} D)\n+42.6 km @ f=(2,0)",
        xy=(sep_d_arr[0], zleak_arr[0]),
        xytext=(sep_d_arr[0] + 0.14, 42.0),
        arrowprops={"arrowstyle": "->", "color": "#2563eb", "lw": 1.1},
        fontsize=8,
        color="#2563eb",
    )
    ax.set_ylim(-6, 52)
    ax.set_xlabel("Pupil centre-to-centre separation S / D")
    ax.set_ylabel("Effective phase-only z_leak at f=(2,0) c/ap [km]")
    ax.set_title("(c) Cause of Case F Ground-Layer Bias: Inter-Pupil Hilbert Interference")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8.2, loc="upper right")

    # (1,1) Distance accuracy across Cases B, O, C, F (Old vs Upgraded C unit)
    ax = axes[1, 1]
    truth = np.array([7785.0, 11985.0, 19486.0])
    cases = ["Case B\n(Flat WF)", "Case C\n(32x32 DM)", "Case F\n(16x16 DM)", "Case O\n(Open loop)"]
    old_errs = [
        np.mean(np.abs(np.array(c_results["old"][k]) / truth - 1.0)) * 100.0
        for k in ("B", "C", "F", "O")
    ]
    new_errs = [
        np.mean(np.abs(np.array(c_results["new"][k]) / truth - 1.0)) * 100.0
        for k in ("B", "C", "F", "O")
    ]
    x = np.arange(len(cases))
    w = 0.35
    b1 = ax.bar(x - w / 2, old_errs, w, color="#94a3b8", label="Previous (analytic T_core, cf=1)")
    b2 = ax.bar(
        x + w / 2,
        new_errs,
        w,
        color="#059669",
        label="Upgraded C unit (coherent T_I + auto cf)",
    )
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + 1.5,
                f"{h:.0f}%",
                ha="center",
                fontsize=8,
            )
    ax.set_xticks(x)
    ax.set_xticklabels(cases)
    ax.set_ylabel("Mean |z_meas / z_true - 1| over 3 high layers [%]")
    ax.set_title("(d) Zero-Tuning Distance Error Across All PyWFS Regimes")
    ax.set_ylim(0, max(old_errs) * 1.18)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=8, loc="upper left")

    out = WL_DIR / "fig_pywfs_selfcal_and_leakage.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Wrote {out}")


def make_eof_figure() -> None:
    """Create 1x3 figure summarizing Track 2 (PF vs Gram) and Track 3 (Bayes Prior EOF)."""
    data = json.loads((WORK / "wind_layers" / "eof_wind_study.json").read_text())
    pb = data["part_b"]

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.9), constrained_layout=True)
    fig.suptitle(
        "EOF PF 3D Cubes vs. Wind-Layer Physics-Gram Prior (Real AO3k Stage-1 20 s PSOL Telemetry)",
        fontsize=12.0,
        fontweight="bold",
    )

    # Panel 1 & 2: Block 0 and Block 1 walk-forward cold start
    for ax, bkey, title in [
        (axes[0], "blk0", "(a) Stage-1 Block 0 (Modes 0-127)"),
        (axes[1], "blk1", "(b) Stage-1 Block 1 (Modes 128-255)"),
    ]:
        rows = pb[bkey]
        ns = np.array([r["ntr"] for r in rows], dtype=float) / 1e3
        ar = [r["ar16"] for r in rows]
        emp = [r["emp"] if r["emp"] is not None else np.nan for r in rows]
        bay = [r["bayes"] for r in rows]
        phy = rows[0]["phys"]
        spf = rows[0]["sumpf"]
        ax.plot(ns[1:], ar[1:], "--s", color="#2563eb", lw=1.8, ms=5, label="Diag AR(16)")
        ax.plot(ns[1:], emp[1:], ":^", color="#dc2626", lw=1.8, ms=5, label="Emp Block-EOF(128,8)")
        ax.plot(ns, bay, "-o", color="#059669", lw=2.3, ms=5.5, label="Bayes Physics-Prior EOF")
        ax.axhline(
            phy, color="#0d9488", ls="-.", lw=1.3, alpha=0.8, label=f"0-fr Phys-Gram ({phy:+.1f}%)"
        )
        ax.axhline(0.0, color="#0f172a", lw=0.8, alpha=0.5)
        ax.text(
            0.97,
            0.05,
            f"Linear sum of PF cubes:\n{spf:+.1f}% (unstable)",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            color="#991b1b",
            bbox={"boxstyle": "round,pad=0.25", "fc": "#fef2f2", "ec": "#fca5a5"},
        )
        ax.set_ylim(-50, 90)
        ax.set_xlabel("Training window N_train [x1,000 frames @ 1 kHz]")
        ax.set_ylabel("Out-of-sample lag variance reduction [%]")
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7.6, loc="lower right", bbox_to_anchor=(1.0, 0.18))

    # Panel 3: Summary across all tested blocks at N=4096 (cold start) and N=14500 (converged)
    ax = axes[2]
    bkeys = ["blk0", "blk1", "blk2", "blk4", "blk8"]
    blabs = [
        "Blk 0\n(0-127)",
        "Blk 1\n(128-255)",
        "Blk 2\n(256-383)",
        "Blk 4\n(512-639)",
        "Blk 8\n(1024-1151)",
    ]
    x = np.arange(len(bkeys))
    w = 0.25

    def get_v(bk: str, ntr: int, key: str) -> float:
        return next(r[key] for r in pb[bk] if r["ntr"] == ntr)

    ar_4k = [get_v(bk, 4096, "ar16") for bk in bkeys]
    bay_4k = [get_v(bk, 4096, "bayes") for bk in bkeys]
    emp_14k = [get_v(bk, 14500, "emp") for bk in bkeys]
    bay_14k = [get_v(bk, 14500, "bayes") for bk in bkeys]
    ax.bar(x - w, ar_4k, w, color="#93c5fd", label="Diag AR(16) @ 4k fr")
    ax.bar(x, bay_4k, w, color="#34d399", label="Bayes Prior EOF @ 4k fr")
    ax.bar(x + w, bay_14k, w, color="#047857", label="Bayes Prior EOF @ 14.5k fr")
    ax.plot(x + w, emp_14k, "D", color="#dc2626", ms=5.5, label="Emp EOF @ 14.5k fr")
    ax.set_xticks(x)
    ax.set_xticklabels(blabs, fontsize=8)
    ax.set_ylabel("Out-of-sample lag variance reduction [%]")
    ax.set_title("(c) All Blocks: 4 s Cold Start & 14.5 s Converged")
    ax.set_ylim(0, 92)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=7.5, loc="upper right")

    out = WL_DIR / "fig_eof_wind_and_prior.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Wrote {out}")


if __name__ == "__main__":
    # Placeholder C results passed via JSON if present, else updated from latest run
    res_p = WORK / "wind_layers" / "c_validation_summary.json"
    if res_p.is_file():
        make_pywfs_figure(json.loads(res_p.read_text()))
    if (WORK / "wind_layers" / "eof_wind_study.json").is_file():
        make_eof_figure()
