#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Calibration sweeps, offload statistics, method benchmarks and transient detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astropy.io import fits
import numpy as np

from .telemetry import (
    load_reference_og,
    load_selfrm_og,
    load_tlm,
    load_tlm_2d,
    resample_dm2_to_dm1,
    run_calib2wfs1dm_cli,
    sync_window,
)

T_CLEAN_S = 4.0  # stationary analysis window [s] (before any end-of-run transient)
N_CLEAN = 4000  # same window in 1 kHz Stage-1 frames
OFFLOAD_GAIN = 0.5  # gain of the static DM2 -> DM1 offload iteration
N_OFFLOAD_ITER = 5  # number of static offload iterations
LOW_ORDER_MODES = 4  # modes 0..3, reported separately as "low-order"


def mode_rel_err_stats(d: np.ndarray, ref: np.ndarray) -> tuple[float, float]:
    """Median and 90th-percentile per-mode |d - ref| / ref [%] over modes with a valid ref."""
    ok = ref > 1e-3
    err = np.abs(d[ok] - ref[ok]) / ref[ok] * 100.0
    return float(np.median(err)), float(np.percentile(err, 90))


def spectral_radius(mat: np.ndarray) -> float:
    """Largest eigenvalue magnitude of a square matrix."""
    return float(np.max(np.abs(np.linalg.eigvals(mat))))


def max_stable_gain(eigs: np.ndarray) -> float:
    """Largest g for which |1 - g*lam| < 1 holds for every eigenvalue (0 if none exists)."""
    if np.any(eigs.real <= 0.0):
        return 0.0
    return float(np.min(2.0 * eigs.real / np.abs(eigs) ** 2))


def detect_transient(t: np.ndarray, rms: np.ndarray, factor: float = 5.0) -> dict[str, Any]:
    """Locate an amplitude jump: first sample above `factor` x the first-half median.

    Also returns the rise time from 2x baseline to half of the peak, which separates an abrupt
    step (a few samples) from slow exponential growth.
    """
    base = float(np.median(rms[: max(4, len(rms) // 2)]))
    hits = np.where(rms > factor * base)[0]
    if base <= 0.0 or hits.size == 0:
        return {"found": False, "base_nm": base}
    k_on = int(hits[0])
    peak = float(np.max(rms[k_on:]))
    k_2x = k_on
    while k_2x > 0 and rms[k_2x - 1] > 2.0 * base:
        k_2x -= 1
    k_half = k_2x + int(np.argmax(rms[k_2x:] >= 0.5 * peak))
    return {
        "found": True,
        "t_onset_s": float(t[k_on]),
        "base_nm": base,
        "peak_nm": peak,
        "factor": peak / base,
        "rise_ms": float(t[k_half] - t[k_2x]) * 1000.0,
        "sample_ms": float(np.median(np.diff(t))) * 1000.0,
    }


def eval_ols_and_freq_dynamics(
    base_dir: Path,
    og_true: np.ndarray,
    n_lim: int | None = None,
    f_lo: float = 20.0,
    f_hi: float = 480.0,
) -> dict[str, Any]:
    """Evaluate Unwhitened OLS, Residual Diagnostics, and Exact-Window Freq-Domain ID.

    `og_true` is the selfRM optical-gain reference (see load_reference_og) against which every
    error is measured. Note that by Parseval the band-limited, 1/tr(S_AA)-weighted cross-spectral
    regression below equals a time-domain least-squares fit after a zero-phase band-pass
    whitening filter: it is a non-parametric relative of W(z), not a different estimator class.
    Its band edges and ridge terms are fixed by hand, not cross-validated.
    """
    tlm = base_dir / "telemetry"
    A, tA = load_tlm(tlm, "aol1_modevalWFS", 60)
    B, tB = load_tlm(tlm, "aol2_modevalWFS", 40)
    D, tD = load_tlm(tlm, "aol2_modevalDM", 40)
    srm_med = float(np.median(og_true))

    t0 = max(tA[0], tB[0], tD[0])
    t1 = min(tA[-1], tB[-1], tD[-1])
    mA = (tA >= t0) & (tA <= t1)
    tA = tA[mA]
    A = A[mA]
    if n_lim is not None:
        tA = tA[:n_lim]
        A = A[:n_lim]
    dtA = float(np.median(np.diff(tA)))
    dtB = float(np.median(np.diff(tB)))

    # 1) Legacy center-aligned window (for unwhitened OLS & residual diagnostics)
    B_c, vBc = sync_window(tA, B, tB, dtA, lag_s=0.0)
    D_c, vDc = sync_window(tA, D, tD, dtA, lag_s=2.5 * dtB)
    okc = vBc & vDc
    Ac = A[okc] - A[okc].mean(0)
    Bc = B_c[okc] - B_c[okc].mean(0)
    Dc = D_c[okc] - D_c[okc].mean(0)
    dA, dB, dD = 60, 40, 40

    # Zero-ridge unwhitened OLS
    X0 = np.hstack([Ac, Dc])
    G0 = X0.T @ X0
    reg0 = np.concatenate([1e-6 * np.diag(G0[:dA, :dA]), 1e-6 * np.diag(G0[dA:, dA:])])
    Th0 = np.linalg.solve(G0 + np.diag(reg0), X0.T @ Bc).T
    d_ols = np.diag(Th0[:, dA:])

    # Colored residual diagnostics at true Mdb ~ og_true
    B_ol = Bc - Dc * og_true[None, :]
    Mab_ol = np.linalg.lstsq(Ac, B_ol, rcond=1e-3)[0].T
    res_true = B_ol - Ac @ Mab_ol.T
    ac1_res = float(np.median([np.corrcoef(res_true[1:, i], res_true[:-1, i])[0, 1] for i in range(dB)]))
    corr_res_d = float(np.median([np.corrcoef(res_true[:, i], Dc[:, i])[0, 1] for i in range(dB)]))

    # Residual PSD (normalized) for plotting
    nperseg = 128
    step = 64
    win = np.hanning(nperseg)[:, None]
    win_norm = float(np.sum(win[:, 0] ** 2))
    starts_c = list(range(0, len(Ac) - nperseg + 1, step))
    freqs = np.fft.rfftfreq(nperseg, d=0.001)
    rf = np.array([np.fft.rfft(res_true[s : s + nperseg] * win, axis=0) for s in starts_c])
    psd_res = np.median(np.mean(np.abs(rf) ** 2, axis=0) / win_norm, axis=1)

    # 2) Exact exposure-midpoint alignment: A integrates [tA-1ms, tA] (mid tA-0.5ms),
    #    B integrates [tB-0.5ms, tB] (mid tB-0.25ms) -> B window center = tA - 0.5*dtB,
    #    D window center = tA - (0.5 + 2.5)*dtB = tA - 3.0*dtB!
    B_e, vBe = sync_window(tA, B, tB, dtA, lag_s=0.5 * dtB)
    D_e, vDe = sync_window(tA, D, tD, dtA, lag_s=3.0 * dtB)
    oke = vBe & vDe
    Ae = A[oke] - A[oke].mean(0)
    Be = B_e[oke] - B_e[oke].mean(0)
    De = D_e[oke] - D_e[oke].mean(0)

    starts_e = list(range(0, len(Ae) - nperseg + 1, step))
    nblk = len(starts_e)
    Af = np.array([np.fft.rfft(Ae[s : s + nperseg] * win, axis=0) for s in starts_e])
    Bf = np.array([np.fft.rfft(Be[s : s + nperseg] * win, axis=0) for s in starts_e])
    Df = np.array([np.fft.rfft(De[s : s + nperseg] * win, axis=0) for s in starts_e])

    S_AA = np.einsum("bfi,bfj->fij", Af, Af.conj()) / (nblk * win_norm)
    S_DD = np.einsum("bfi,bfj->fij", Df, Df.conj()) / (nblk * win_norm)
    S_AD = np.einsum("bfi,bfj->fij", Af, Df.conj()) / (nblk * win_norm)
    S_BA = np.einsum("bfi,bfj->fij", Bf, Af.conj()) / (nblk * win_norm)
    S_BD = np.einsum("bfi,bfj->fij", Bf, Df.conj()) / (nblk * win_norm)

    fidxs = np.where((freqs >= f_lo) & (freqs <= f_hi))[0]
    G_AA = np.zeros((dA, dA))
    G_AD = np.zeros((dA, dD))
    G_DD = np.zeros((dD, dD))
    G_BA = np.zeros((dB, dA))
    G_BD = np.zeros((dB, dD))
    for fi in fidxs:
        w = 1.0 / (float(np.real(np.trace(S_AA[fi]))) + 1e-12)
        G_AA += w * np.real(S_AA[fi])
        G_AD += w * np.real(S_AD[fi])
        G_DD += w * np.real(S_DD[fi])
        G_BA += w * np.real(S_BA[fi])
        G_BD += w * np.real(S_BD[fi])
    G_AA_r = G_AA + np.diag(0.05 * np.maximum(np.diag(G_AA), 1e-12))
    G_DD_r = G_DD + np.diag(0.005 * np.maximum(np.diag(G_DD), 1e-12))
    G_f = np.block([[G_AA_r, G_AD], [G_AD.T, G_DD_r]])
    Th_f = np.linalg.solve(G_f, np.hstack([G_BA, G_BD]).T).T
    Mdb_f = Th_f[:, dA:]
    d_freq = np.diag(Mdb_f)
    off_freq = float(np.sqrt(np.mean((Mdb_f - np.diag(d_freq)) ** 2)))

    # 3) High-frequency lag_AB cross-correlation at native 2 kHz (exposes -0.25 ms & +1.5 ms peaks)
    mB = (tB >= t0) & (tB <= t1)
    tB_2 = tB[mB]
    B_2 = B[mB]
    if n_lim is not None:
        tB_2 = tB_2[: 2 * n_lim]
        B_2 = B_2[: 2 * n_lim]
    D_2lag = np.column_stack([np.interp(tB_2 - 2.5 * dtB, tD, D[:, c]) for c in range(40)])
    B_ol2 = B_2 - D_2lag * og_true[None, :]
    lags_ab_fr = np.arange(-4.0, 4.5, 0.5)
    hf_corrs = []
    raw_corrs = []
    for lag_fr in lags_ab_fr:
        tq = tB_2 - lag_fr * dtB
        ok2 = (tq >= tA[0]) & (tq <= tA[-1])
        A_sh = np.column_stack([np.interp(tq[ok2], tA, A[:, c]) for c in range(40)])
        b_sub = B_ol2[ok2]
        raw_corrs.append(
            float(np.median([abs(np.corrcoef(b_sub[:, m], A_sh[:, m])[0, 1]) for m in range(4, 40)]))
        )
        db = np.diff(b_sub, axis=0)
        da = np.diff(A_sh, axis=0)
        hf_corrs.append(
            float(np.median([abs(np.corrcoef(db[:, m], da[:, m])[0, 1]) for m in range(4, 40)]))
        )

    lo = LOW_ORDER_MODES
    ols_pm_med, ols_pm_p90 = mode_rel_err_stats(d_ols, og_true)
    freq_pm_med, freq_pm_p90 = mode_rel_err_stats(d_freq, og_true)
    return {
        "og_true": og_true,
        "srm_med": srm_med,
        "d_ols": d_ols,
        "ols_med": float(np.median(d_ols)),
        "ols_err_pct": abs(float(np.median(d_ols)) - srm_med) / srm_med * 100.0,
        "ols_signed_err_pct": (float(np.median(d_ols)) - srm_med) / srm_med * 100.0,
        "ols_pm_med_pct": ols_pm_med,
        "ols_pm_p90_pct": ols_pm_p90,
        "ols_tt_mae": float(np.mean(np.abs(d_ols[:lo] - og_true[:lo]))),
        "d_freq": d_freq,
        "freq_med": float(np.median(d_freq)),
        "freq_err_pct": abs(float(np.median(d_freq)) - srm_med) / srm_med * 100.0,
        "freq_signed_err_pct": (float(np.median(d_freq)) - srm_med) / srm_med * 100.0,
        "freq_pm_med_pct": freq_pm_med,
        "freq_pm_p90_pct": freq_pm_p90,
        "freq_mae": float(np.mean(np.abs(d_freq - og_true))),
        "freq_tt_mae": float(np.mean(np.abs(d_freq[:lo] - og_true[:lo]))),
        "freq_offdiag": off_freq,
        "ac1_res": ac1_res,
        "corr_res_d": corr_res_d,
        "freqs": freqs,
        "psd_res": psd_res,
        "lags_ab_ms": lags_ab_fr * 0.5,
        "hf_corrs": np.array(hf_corrs),
        "raw_corrs": np.array(raw_corrs),
    }


def load_run_metrics(base_cal: Path, base_op: Path, base_cl: Path) -> dict[str, Any]:
    """Per-run metrics (star, seeing, integration time, recorded command line and commits)."""
    run_dirs = {"lowfs_open": base_op, "lowfs_closed": base_cl, "calib2wfs1dm": base_cal}
    run_metrics: dict[str, dict[str, Any]] = {}
    for rkey, rdir in run_dirs.items():
        mpath = rdir / "ao3k_scexao_metrics.json"
        run_metrics[rkey] = (
            json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else {}
        )
    cal_metrics = run_metrics["calib2wfs1dm"]
    sa_cal = cal_metrics.get("star_and_atmosphere", {})
    phys_time = float(sa_cal.get("physical_time_s", 5.0))
    return {
        "run_dirs": run_dirs,
        "run_metrics": run_metrics,
        "cal_metrics": cal_metrics,
        "sa_cal": sa_cal,
        "phys_time": phys_time,
    }


def run_all_sweeps(
    base_cal: Path,
    base_op: Path,
    base_cl: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    """Run (or reuse) every milk-mlt-calib2wfs1dm fit the study needs."""
    # Main 5s predictive calib (already generated during simulation!)
    cdir_pred5 = base_cal / "calib_2wfs1dm"
    sum_pred5 = json.loads((cdir_pred5 / "sysid_summary.json").read_text(encoding="utf-8"))
    # Clean 0-4s stationary predictive window
    cdir_pred4 = cache_dir / "calib_pred4s"
    sum_pred4 = run_calib2wfs1dm_cli(
        base_cal, cdir_pred4, lag_ab="0.0", lag_db="2.5", whiten_order=4, maxframes=N_CLEAN
    )
    # Integrator LLOWFS OPEN & CLOSED
    cdir_op = cache_dir / "calib_lowfs_open"
    sum_op = run_calib2wfs1dm_cli(base_op, cdir_op)
    cdir_cl = cache_dir / "calib_lowfs_closed"
    sum_cl = run_calib2wfs1dm_cli(base_cl, cdir_cl)

    # AR(p) whitening order sweep on full 5s predictive telemetry
    ar_orders = [0, 1, 2, 4, 6, 8]
    sweep_p: list[dict[str, Any]] = []
    for p_ord in ar_orders:
        cdir_p = cache_dir / f"sweep_p{p_ord}"
        sp = run_calib2wfs1dm_cli(
            base_cal, cdir_p, lag_ab="0.0", lag_db="2.5", whiten_order=p_ord
        )
        sweep_p.append({"order": p_ord, **sp})

    # Sample-size convergence sweep (0.5 s .. 4.0 s on clean stationary window)
    conv_ns = [500, 1000, 1500, 2000, 3000, 4000]
    conv_dirs: dict[int, Path] = {}
    conv_sums: list[dict[str, Any]] = []
    for nf in conv_ns:
        cdir_n = cache_dir / f"conv_n{nf}"
        sn = run_calib2wfs1dm_cli(
            base_cal, cdir_n, lag_ab="0.0", lag_db="2.5", whiten_order=4, maxframes=nf
        )
        conv_dirs[nf] = cdir_n
        conv_sums.append({"n_req": nf, "t_s": nf / 1000.0, **sn})
    return {
        "cdir_pred5": cdir_pred5,
        "sum_pred5": sum_pred5,
        "cdir_pred4": cdir_pred4,
        "sum_pred4": sum_pred4,
        "cdir_op": cdir_op,
        "sum_op": sum_op,
        "cdir_cl": cdir_cl,
        "sum_cl": sum_cl,
        "sweep_p": sweep_p,
        "conv_dirs": conv_dirs,
        "conv_sums": conv_sums,
    }


def compute_offload(base_cal: Path, sweeps: dict[str, Any]) -> dict[str, Any]:
    """Compare Mda_virt with the actuator geometry and run the static offload test.

    Also adds the median geometric cosine to every row of the sample-size sweep.
    """
    cdir_pred4 = sweeps["cdir_pred4"]
    cdir_pred5 = sweeps["cdir_pred5"]
    conv_dirs = sweeps["conv_dirs"]
    conv_sums = sweeps["conv_sums"]
    cm1 = fits.getdata(base_cal / "telemetry/calib_stg1/CMmodesDM.fits").astype(np.float64)
    cm2 = fits.getdata(base_cal / "telemetry/calib_stg2/CMmodesDM.fits").astype(np.float64)
    dm1m = fits.getdata(base_cal / "telemetry/calib_stg1/dmmask.fits").astype(np.float64) > 0.5
    dm2m = fits.getdata(base_cal / "telemetry/calib_stg2/dmmask.fits").astype(np.float64) > 0.5
    dA, dD = 60, 40
    B1 = np.array([cm1[i][dm1m] for i in range(dA)])
    B2 = np.array([resample_dm2_to_dm1(cm2[j])[dm1m] for j in range(dD)])
    M_geom = np.linalg.lstsq(B1.T, B2.T, rcond=1e-4)[0]  # (60, 40)

    def geom_stats(cdir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        mda = fits.getdata(cdir / "Mda_virt.fits").astype(np.float64)
        cos_v = np.array(
            [
                np.dot(mda[:, j], M_geom[:, j])
                / (np.linalg.norm(mda[:, j]) * np.linalg.norm(M_geom[:, j]) + 1e-12)
                for j in range(dD)
            ]
        )
        scl_v = np.array(
            [
                np.dot(mda[:, j], M_geom[:, j]) / (np.dot(M_geom[:, j], M_geom[:, j]) + 1e-12)
                for j in range(dD)
            ]
        )
        return cos_v, scl_v, mda

    cos4, scl4, mda4 = geom_stats(cdir_pred4)
    cos5, scl5, _ = geom_stats(cdir_pred5)
    for row in conv_sums:
        cv, _, _ = geom_stats(conv_dirs[row["n_req"]])
        row["geom_cos_med"] = float(np.median(cv))

    # Held-out 2D DM2 -> DM1 offload test (t = 2.8..4.0 s, 2400 frames)
    D_all, _ = load_tlm(base_cal / "telemetry", "aol2_modevalDM", 40)
    D_eval = D_all[5600:8000]
    opd_dm2 = D_eval @ B2
    opd_off_raw = (D_eval @ mda4.T) @ B1
    opd_off_geom = (D_eval @ M_geom.T) @ B1
    rms_dm2_t = np.sqrt(np.mean(opd_dm2**2, axis=1)) * 2000.0
    rms_res_raw_t = np.sqrt(np.mean((opd_dm2 - opd_off_raw) ** 2, axis=1)) * 2000.0
    rms_res_geom_t = np.sqrt(np.mean((opd_dm2 - opd_off_geom) ** 2, axis=1)) * 2000.0

    # Static offload map in DM2 modal space: one iteration is d <- (I - g * M_loop) d.
    # It converges iff the spectral radius of (I - g * M_loop) is below 1.
    M_loop = np.linalg.lstsq(B2.T, B1.T @ mda4, rcond=1e-4)[0]
    eigs = np.linalg.eigvals(M_loop)
    spec_rad_05 = spectral_radius(np.eye(dD) - 0.5 * M_loop)
    spec_rad_02 = spectral_radius(np.eye(dD) - 0.2 * M_loop)
    g_off_max = max_stable_gain(eigs)

    # Expected Mda_virt / M_geom amplitude ratio: Mda_virt ~ Mab^+ Mdb = g_A * M_geom, i.e. the
    # WFS A optical gain, weighted per DM2 mode by its squared projection on the WFS A modes.
    ga_stage1 = load_selfrm_og(base_cal, dA, stage=1)
    ga_expect_med: float | None = None
    if ga_stage1.size:
        ga_full = np.full(dA, float(np.median(ga_stage1)))
        ga_full[: ga_stage1.size] = ga_stage1
        wgt = M_geom**2
        ga_expect = (wgt * ga_full[:, None]).sum(axis=0) / np.maximum(wgt.sum(axis=0), 1e-12)
        ga_expect_med = float(np.median(ga_expect))

    k_best = int(np.argmax(rms_dm2_t))
    d_snap = D_eval[k_best]
    map_dm2 = np.full((64, 64), np.nan)
    map_dm1 = np.full((64, 64), np.nan)
    map_res = np.full((64, 64), np.nan)
    map_dm2[dm1m] = (d_snap @ B2) * 2000.0
    map_dm1[dm1m] = ((mda4 @ d_snap) @ B1) * 2000.0
    map_res[dm1m] = map_dm2[dm1m] - map_dm1[dm1m]
    snap_rms_in = float(np.sqrt(np.nanmean(map_dm2**2)))
    snap_rms_res = float(np.sqrt(np.nanmean(map_res**2)))
    snap_red = (1.0 - snap_rms_res / snap_rms_in) * 100.0
    # Static iteration on the frozen snapshot (no loop dynamics, delay or noise). Each DM1 move
    # is split into the part the 40 analysed DM2 modes can give up (stroke removed from DM2)
    # and the remainder outside that subspace (OPD that higher DM2 modes would have to absorb).
    d_cur = d_snap.copy()
    opd_leak = np.zeros(B1.shape[1])
    for _ in range(N_OFFLOAD_ITER):
        opd_dm1 = B1.T @ (OFFLOAD_GAIN * (mda4 @ d_cur))
        d_abs = np.linalg.lstsq(B2.T, opd_dm1, rcond=1e-4)[0]
        opd_leak += opd_dm1 - B2.T @ d_abs
        d_cur = d_cur - d_abs
    stroke_iter = float(np.sqrt(np.mean((d_cur @ B2) ** 2)) * 2000.0)
    leak_iter = float(np.sqrt(np.mean(opd_leak**2)) * 2000.0)
    res_iter = float(np.hypot(stroke_iter, leak_iter))

    offload_stats = {
        "geom_cos_med_4s": float(np.median(cos4)),
        "geom_cos_mean_4s": float(np.mean(cos4)),
        "geom_cos_med_5s": float(np.median(cos5)),
        "scale_ratio_med_4s": float(np.median(scl4)),
        "scale_ratio_iqr_4s": float(np.percentile(scl4, 75) - np.percentile(scl4, 25)),
        "mean_dm2_rms_nm": float(np.mean(rms_dm2_t)),
        "oneshot_res_rms_nm": float(np.mean(rms_res_raw_t)),
        "oneshot_rms_red_pct": (1.0 - float(np.mean(rms_res_raw_t)) / float(np.mean(rms_dm2_t)))
        * 100.0,
        "oneshot_var_red_pct": (
            1.0 - (float(np.mean(rms_res_raw_t)) / float(np.mean(rms_dm2_t))) ** 2
        )
        * 100.0,
        "ideal_geom_res_nm": float(np.mean(rms_res_geom_t)),
        "snap_in_nm": snap_rms_in,
        "snap_res_1shot_nm": snap_rms_res,
        "snap_red_1shot_pct": snap_red,
        "iter_gain": OFFLOAD_GAIN,
        "iter_count": N_OFFLOAD_ITER,
        "snap_stroke_iter_nm": stroke_iter,
        "snap_leak_iter_nm": leak_iter,
        "snap_res_iter_nm": res_iter,
        "snap_stroke_red_iter_pct": (1.0 - stroke_iter / snap_rms_in) * 100.0,
        "snap_red_iter_pct": (1.0 - res_iter / snap_rms_in) * 100.0,
        "eig_real_min": float(np.min(eigs.real)),
        "eig_real_max": float(np.max(eigs.real)),
        "eig_abs_imag_max": float(np.max(np.abs(eigs.imag))),
        "spec_rad_g05": spec_rad_05,
        "spec_rad_g02": spec_rad_02,
        "max_stable_gain": g_off_max,
        "geom_cos_min_4s": float(np.min(cos4)),
        "geom_cos_max_4s": float(np.max(cos4)),
        "wfs_a_gain_expected_med": ga_expect_med,
        "test": "static matrix comparison against actuator geometry; no offload loop was run",
    }
    return {
        "dA": dA,
        "dD": dD,
        "dm2m": dm2m,
        "cos4": cos4,
        "cos5": cos5,
        "scl4": scl4,
        "map_dm2": map_dm2,
        "map_dm1": map_dm1,
        "map_res": map_res,
        "snap_rms_in": snap_rms_in,
        "snap_rms_res": snap_rms_res,
        "snap_red": snap_red,
        "ga_expect_med": ga_expect_med,
        "offload_stats": offload_stats,
    }


def compute_method_benchmarks(
    base_cal: Path,
    base_op: Path,
    base_cl: Path,
    sweeps: dict[str, Any],
    phys_time: float,
) -> dict[str, dict[str, Any]]:
    """Benchmark OLS, AR(4) W(z) and the frequency-domain estimator on the 4 regimes.

    Also adds `ref_err_pct` (error against the predictive-run selfRM reference) to every row
    of the whitening-order and sample-size sweeps.
    """
    cdir_op, sum_op = sweeps["cdir_op"], sweeps["sum_op"]
    cdir_cl, sum_cl = sweeps["cdir_cl"], sweeps["sum_cl"]
    cdir_pred4, sum_pred4 = sweeps["cdir_pred4"], sweeps["sum_pred4"]
    cdir_pred5, sum_pred5 = sweeps["cdir_pred5"], sweeps["sum_pred5"]
    sweep_p, conv_sums = sweeps["sweep_p"], sweeps["conv_sums"]
    t_full = f"{phys_time:.0f} s"
    t_clean = f"0-{T_CLEAN_S:.0f} s"
    regimes = [
        ("int_open", f"Integrator, LLOWFS open ({t_full})", base_op, cdir_op, sum_op, None),
        ("int_closed", f"Integrator, LLOWFS closed ({t_full})", base_cl, cdir_cl, sum_cl, None),
        ("pred_4s", f"PSOL predictive, clean {t_clean}", base_cal, cdir_pred4, sum_pred4, N_CLEAN),
        ("pred_5s", f"PSOL predictive, full {t_full}", base_cal, cdir_pred5, sum_pred5, None),
    ]
    method_bench: dict[str, dict[str, Any]] = {}
    for key, lbl, bdir, cdir, s_w, nlim in regimes:
        # One selfRM reference per run, shared by every method, table, figure and sentence.
        og, og_alt, ref_kind = load_reference_og(bdir, cdir, 40)
        ev = eval_ols_and_freq_dynamics(bdir, og, n_lim=nlim)
        d_w = np.diag(fits.getdata(cdir / "Mdb.fits").astype(np.float64))
        srm_med = ev["srm_med"]
        alt_med = float(np.median(og_alt))
        w_pm_med, w_pm_p90 = mode_rel_err_stats(d_w, og)
        method_bench[key] = {
            "label": lbl,
            "srm_med": srm_med,
            "ref_kind": ref_kind,
            "ref_alt_med": alt_med,
            "ref_spread_pct": abs(alt_med - srm_med) / srm_med * 100.0,
            "w_med": float(np.median(d_w)),
            "w_err_pct": abs(float(np.median(d_w)) - srm_med) / srm_med * 100.0,
            "w_pm_med_pct": w_pm_med,
            "w_pm_p90_pct": w_pm_p90,
            "w_mae": float(np.mean(np.abs(d_w - og))),
            "w_tt_mae": float(np.mean(np.abs(d_w[:LOW_ORDER_MODES] - og[:LOW_ORDER_MODES]))),
            "w_d": d_w,
            "w_summary": s_w,
            **ev,
        }

    # Errors of the whitening-order and sample-size sweeps against the same reference
    # (all of these fits use the predictive run, hence its selfRM reference).
    srm_ref = method_bench["pred_5s"]["srm_med"]
    for row in sweep_p + conv_sums:
        row["ref_err_pct"] = abs(row["mdb_diag_med"] - srm_ref) / srm_ref * 100.0
    return method_bench


def compute_stage3_transient(
    base_cal: Path,
    base_cl: Path,
    run: dict[str, Any],
    sweeps: dict[str, Any],
    dm2m: np.ndarray,
) -> dict[str, Any]:
    """Stage-2 / Stage-3 DM2 channel RMS vs time and late-run transient detection."""
    phys_time = float(run["phys_time"])
    run_metrics = run["run_metrics"]
    sum_pred5 = sweeps["sum_pred5"]
    d2c, t2 = load_tlm_2d(base_cal / "telemetry", "aol2_dmC")
    d3c, t3 = load_tlm_2d(base_cal / "telemetry", "aol3_dmC")
    t2_p = (t2 - t2[0]) / (t2[-1] - t2[0]) * phys_time
    t3_p = (t3 - t3[0]) / (t3[-1] - t3[0]) * phys_time
    rms_d2c = np.sqrt(np.mean(d2c[:, dm2m] ** 2, axis=1)) * 2000.0
    rms_d3c = np.sqrt(np.mean(d3c[:, dm2m] ** 2, axis=1)) * 2000.0

    # Late-run transient on the Stage-3 channel (which drives DM2 but is not part of D).
    wind = detect_transient(t3_p, rms_d3c)
    if wind["found"]:
        pre2 = rms_d2c[t2_p < wind["t_onset_s"]]
        post2 = rms_d2c[t2_p >= wind["t_onset_s"]]
        if pre2.size and post2.size:
            wind["dm2_base_nm"] = float(np.median(pre2))
            wind["dm2_peak_nm"] = float(np.max(post2))
            wind["dm2_factor"] = wind["dm2_peak_nm"] / max(wind["dm2_base_nm"], 1e-9)
        wind["after_clean_window"] = bool(wind["t_onset_s"] > T_CLEAN_S)
    # Same check on the integrator LLOWFS-closed run (same Stage-3 / zpo-2 configuration).
    wind_cl: dict[str, Any] | None = None
    try:
        d3c_cl, t3_cl = load_tlm_2d(base_cl / "telemetry", "aol3_dmC")
        sa_cl = run_metrics["lowfs_closed"].get("star_and_atmosphere", {})
        pt_cl = float(sa_cl.get("physical_time_s", phys_time))
        t3_cl_p = (t3_cl - t3_cl[0]) / (t3_cl[-1] - t3_cl[0]) * pt_cl
        rms_cl = np.sqrt(np.mean(d3c_cl[:, dm2m] ** 2, axis=1)) * 2000.0
        wind_cl = detect_transient(t3_cl_p, rms_cl)
    except FileNotFoundError:
        wind_cl = None
    fs_ref = float(sum_pred5.get("fs_hz", 1000.0)) or 1000.0
    t_split = float(sum_pred5.get("n_train", 0.7 * phys_time * fs_ref)) / fs_ref
    return {
        "wind": wind,
        "wind_cl": wind_cl,
        "t2_p": t2_p,
        "rms_d2c": rms_d2c,
        "t3_p": t3_p,
        "rms_d3c": rms_d3c,
        "t_split": t_split,
    }
