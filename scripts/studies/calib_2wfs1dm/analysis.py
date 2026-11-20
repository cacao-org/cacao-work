#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""W(z) sweeps, geometric DM2->DM1 offload validation, and frequency-domain ID analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astropy.io import fits
import numpy as np

from .telemetry import (
    load_selfrm_og,
    load_tlm,
    resample_dm2_to_dm1,
    run_calib2wfs1dm_cli,
    sync_window,
)


def eval_ols_and_freq_dynamics(
    base_dir: Path,
    n_lim: int | None = None,
    f_lo: float = 20.0,
    f_hi: float = 480.0,
) -> dict[str, Any]:
    """Evaluate Unwhitened OLS, Residual Diagnostics, and Exact-Window Freq-Domain ID."""
    tlm = base_dir / "telemetry"
    A, tA = load_tlm(tlm, "aol1_modevalWFS", 60)
    B, tB = load_tlm(tlm, "aol2_modevalWFS", 40)
    D, tD = load_tlm(tlm, "aol2_modevalDM", 40)
    og_true = load_selfrm_og(base_dir, 40)
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

    B_c, vBc = sync_window(tA, B, tB, dtA, lag_s=0.0)
    D_c, vDc = sync_window(tA, D, tD, dtA, lag_s=2.5 * dtB)
    okc = vBc & vDc
    Ac = A[okc] - A[okc].mean(0)
    Bc = B_c[okc] - B_c[okc].mean(0)
    Dc = D_c[okc] - D_c[okc].mean(0)
    dA, dB, dD = 60, 40, 40

    X0 = np.hstack([Ac, Dc])
    G0 = X0.T @ X0
    reg0 = np.concatenate([1e-6 * np.diag(G0[:dA, :dA]), 1e-6 * np.diag(G0[dA:, dA:])])
    Th0 = np.linalg.solve(G0 + np.diag(reg0), X0.T @ Bc).T
    d_ols = np.diag(Th0[:, dA:])

    B_ol = Bc - Dc * og_true[None, :]
    Mab_ol = np.linalg.lstsq(Ac, B_ol, rcond=1e-3)[0].T
    res_true = B_ol - Ac @ Mab_ol.T
    ac1_res = float(np.median([np.corrcoef(res_true[1:, i], res_true[:-1, i])[0, 1] for i in range(dB)]))
    corr_res_d = float(np.median([np.corrcoef(res_true[:, i], Dc[:, i])[0, 1] for i in range(dB)]))

    nperseg = 128
    step = 64
    win = np.hanning(nperseg)[:, None]
    win_norm = float(np.sum(win[:, 0] ** 2))
    starts_c = list(range(0, len(Ac) - nperseg + 1, step))
    freqs = np.fft.rfftfreq(nperseg, d=0.001)
    rf = np.array([np.fft.rfft(res_true[s : s + nperseg] * win, axis=0) for s in starts_c])
    psd_res = np.median(np.mean(np.abs(rf) ** 2, axis=0) / win_norm, axis=1)

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

    return {
        "og_true": og_true,
        "srm_med": srm_med,
        "d_ols": d_ols,
        "ols_med": float(np.median(d_ols)),
        "ols_err_pct": abs(float(np.median(d_ols)) - srm_med) / srm_med * 100.0,
        "ols_tt_mae": float(np.mean(np.abs(d_ols[:4] - og_true[:4]))),
        "d_freq": d_freq,
        "freq_med": float(np.median(d_freq)),
        "freq_err_pct": abs(float(np.median(d_freq)) - srm_med) / srm_med * 100.0,
        "freq_mae": float(np.mean(np.abs(d_freq - og_true))),
        "freq_tt_mae": float(np.mean(np.abs(d_freq[:4] - og_true[:4]))),
        "freq_offdiag": off_freq,
        "ac1_res": ac1_res,
        "corr_res_d": corr_res_d,
        "freqs": freqs,
        "psd_res": psd_res,
        "lags_ab_ms": lags_ab_fr * 0.5,
        "hf_corrs": np.array(hf_corrs),
        "raw_corrs": np.array(raw_corrs),
    }


def run_all_sweeps(
    base_cal: Path,
    base_op: Path,
    base_cl: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    """Run W(z) AR(p) sweeps, convergence sweeps, and multi-regime benchmarks."""
    cdir_pred5 = base_cal / "calib_2wfs1dm"
    sum_pred5 = json.loads((cdir_pred5 / "sysid_summary.json").read_text(encoding="utf-8"))
    cdir_pred4 = cache_dir / "calib_pred4s"
    sum_pred4 = run_calib2wfs1dm_cli(
        base_cal, cdir_pred4, lag_ab="0.0", lag_db="2.5", whiten_order=4, maxframes=4000
    )
    cdir_op = cache_dir / "calib_lowfs_open"
    sum_op = run_calib2wfs1dm_cli(base_op, cdir_op)
    cdir_cl = cache_dir / "calib_lowfs_closed"
    sum_cl = run_calib2wfs1dm_cli(base_cl, cdir_cl)

    sweep_p: list[dict[str, Any]] = []
    for p_ord in [0, 1, 2, 4, 6, 8]:
        sp = run_calib2wfs1dm_cli(
            base_cal, cache_dir / f"sweep_p{p_ord}", lag_ab="0.0", lag_db="2.5", whiten_order=p_ord
        )
        sweep_p.append({"order": p_ord, **sp})

    conv_dirs: dict[int, Path] = {}
    conv_sums: list[dict[str, Any]] = []
    for nf in [500, 1000, 1500, 2000, 3000, 4000]:
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


def compute_offload_and_zpo(base_cal: Path, sweeps: dict[str, Any]) -> dict[str, Any]:
    """Compute geometric DM2->DM1 offload accuracy, eigenvalues, and 2D snapshot maps."""
    cm1 = fits.getdata(base_cal / "telemetry/calib_stg1/CMmodesDM.fits").astype(np.float64)
    cm2 = fits.getdata(base_cal / "telemetry/calib_stg2/CMmodesDM.fits").astype(np.float64)
    dm1m = fits.getdata(base_cal / "telemetry/calib_stg1/dmmask.fits").astype(np.float64) > 0.5
    dm2m = fits.getdata(base_cal / "telemetry/calib_stg2/dmmask.fits").astype(np.float64) > 0.5
    dA, dD = 60, 40
    B1 = np.array([cm1[i][dm1m] for i in range(dA)])
    B2 = np.array([resample_dm2_to_dm1(cm2[j])[dm1m] for j in range(dD)])
    M_geom = np.linalg.lstsq(B1.T, B2.T, rcond=1e-4)[0]

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

    cos4, scl4, mda4 = geom_stats(sweeps["cdir_pred4"])
    cos5, _, _ = geom_stats(sweeps["cdir_pred5"])
    for row in sweeps["conv_sums"]:
        cv, _, _ = geom_stats(sweeps["conv_dirs"][row["n_req"]])
        row["geom_cos_med"] = float(np.median(cv))

    D_all, _ = load_tlm(base_cal / "telemetry", "aol2_modevalDM", 40)
    D_eval = D_all[5600:8000]
    opd_dm2 = D_eval @ B2
    opd_off_raw = (D_eval @ mda4.T) @ B1
    opd_off_geom = (D_eval @ M_geom.T) @ B1
    rms_dm2_t = np.sqrt(np.mean(opd_dm2**2, axis=1)) * 2000.0
    rms_res_raw_t = np.sqrt(np.mean((opd_dm2 - opd_off_raw) ** 2, axis=1)) * 2000.0
    rms_res_geom_t = np.sqrt(np.mean((opd_dm2 - opd_off_geom) ** 2, axis=1)) * 2000.0

    M_loop = np.linalg.lstsq(B2.T, B1.T @ mda4, rcond=1e-4)[0]
    eigs = np.linalg.eigvals(M_loop)
    spec_rad_05 = float(np.max(np.abs(np.eye(dD) - 0.5 * M_loop)))
    spec_rad_02 = float(np.max(np.abs(np.eye(dD) - 0.2 * M_loop)))

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
    d_cur = d_snap.copy()
    for _ in range(5):
        u_dm1 = 0.5 * (mda4 @ d_cur)
        d_cur = d_cur - np.linalg.lstsq(B2.T, B1.T @ u_dm1, rcond=1e-4)[0]
    res_5iter = float(np.sqrt(np.mean((d_cur @ B2) ** 2)) * 2000.0)

    offload_stats = {
        "geom_cos_med_4s": float(np.median(cos4)),
        "geom_cos_mean_4s": float(np.mean(cos4)),
        "geom_cos_med_5s": float(np.median(cos5)),
        "scale_ratio_med_4s": float(np.median(scl4)),
        "scale_ratio_iqr_4s": float(np.percentile(scl4, 75) - np.percentile(scl4, 25)),
        "mean_dm2_rms_nm": float(np.mean(rms_dm2_t)),
        "oneshot_res_rms_nm": float(np.mean(rms_res_raw_t)),
        "oneshot_rms_red_pct": (1.0 - float(np.mean(rms_res_raw_t)) / float(np.mean(rms_dm2_t))) * 100.0,
        "oneshot_var_red_pct": (1.0 - (float(np.mean(rms_res_raw_t)) / float(np.mean(rms_dm2_t))) ** 2) * 100.0,
        "ideal_geom_res_nm": float(np.mean(rms_res_geom_t)),
        "snap_in_nm": snap_rms_in,
        "snap_res_1shot_nm": snap_rms_res,
        "snap_red_1shot_pct": snap_red,
        "snap_res_5iter_nm": res_5iter,
        "snap_red_5iter_pct": (1.0 - res_5iter / snap_rms_in) * 100.0,
        "eig_real_min": float(np.min(eigs.real)),
        "eig_real_max": float(np.max(eigs.real)),
        "spec_rad_g05": spec_rad_05,
        "spec_rad_g02": spec_rad_02,
    }
    return {
        "dD": dD,
        "dm2m": dm2m,
        "cos4": cos4,
        "cos5": cos5,
        "scl4": scl4,
        "map_dm2": map_dm2,
        "map_dm1": map_dm1,
        "map_res": map_res,
        "res_5iter": res_5iter,
        "offload_stats": offload_stats,
    }


def compute_method_benchmarks(
    base_cal: Path,
    base_op: Path,
    base_cl: Path,
    sweeps: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Run Exact-Window Frequency-Domain AO-Dynamics benchmarks across 4 control regimes."""
    regimes = [
        ("int_open", "Integrator, LLOWFS OPEN (5 s)", base_op, sweeps["cdir_op"], sweeps["sum_op"], None),
        ("int_closed", "Integrator, LLOWFS CLOSED (5 s)", base_cl, sweeps["cdir_cl"], sweeps["sum_cl"], None),
        ("pred_4s", "PSOL AR(8) Predictive, clean 0-4 s", base_cal, sweeps["cdir_pred4"], sweeps["sum_pred4"], 4000),
        ("pred_5s", "PSOL AR(8) Predictive, full 5 s (+ZPO)", base_cal, sweeps["cdir_pred5"], sweeps["sum_pred5"], None),
    ]
    method_bench: dict[str, dict[str, Any]] = {}
    for key, lbl, bdir, cdir, s_w, nlim in regimes:
        ev = eval_ols_and_freq_dynamics(bdir, n_lim=nlim)
        d_w = np.diag(fits.getdata(cdir / "Mdb.fits").astype(np.float64))
        og = ev["og_true"]
        srm_med = ev["srm_med"]
        method_bench[key] = {
            "label": lbl,
            "srm_med": srm_med,
            "w_med": float(np.median(d_w)),
            "w_err_pct": abs(float(np.median(d_w)) - srm_med) / srm_med * 100.0,
            "w_mae": float(np.mean(np.abs(d_w - og))),
            "w_tt_mae": float(np.mean(np.abs(d_w[:4] - og[:4]))),
            "w_d": d_w,
            "w_summary": s_w,
            **ev,
        }
    return method_bench
