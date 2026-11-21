#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Offline validation of Phase 0b: Closed-Loop Residual Whiteness / Predictability Monitor.

Validates:
  1. Synthetic MA(d-1) null calibration for:
       - Per-mode Bartlett-corrected Q_tilde_m,
       - Spatially-correlated vector MA(d-1) off-diagonal cross-mode Bartlett Q_xmode,
       - modalCTRL_stats.c 3-point / 4-point (buggy line 437 vs fixed) noise estimators.
  2. Empirical PSOL latency tau_hat and MA(d-1) autocorrelation cliff at k = ceil(tau)
     across 8 existing AO3k/SCExAO telemetry runs (Stage 1 & Stage 2), with mode-band
     decomposition (m=0..19 low-order, m=20..127 mid-Block-0, m=128..511, m>=512).
  3. Multi-lag Bartlett-corrected whiteness Q_tilde_m (k >= d), off-diagonal cross-mode
     Bartlett Q_xmode (in-block and cross-block), signed rho_m(d), and Zone 2 beyond-lookback.
  4. Out-of-sample Recoverable WFE (Delta WFE_recov [nm] and PRF [%]) for:
       - Per-mode lag >= d AR(8) and AR(16) on WFS residuals,
       - Residualized cross-mode block lag >= d (additional WFE beyond diagonal AR(8)),
       - Direct cross-mode block lag >= d (B=64 and B=128),
       - Per-mode lag >= d WFS-from-DM predictability.
  5. WFS-vs-DM cross-correlation Cov(w_t, u_{t-k}) at k >= d, including time-resolved
     pre-windup vs wind-up analysis of ao3k_scexao_calib2wfs1dm around t = 4.85 s.
  6. Comparison of mkEOFPF in-sample o_rms_pred vs live out-of-sample (OL - PF_delayed) RMS.

CPU-only, read-only on _work/, writes only under algo/whiteness/.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import time
from pathlib import Path
from typing import Any

from astropy.io import fits
import numpy as np

WORK_ROOT = Path("/home/guyon/src/cacao-work/_work")
OUT_DIR = Path("/home/guyon/src/cacao-work/algo/whiteness")

RUN_SPECS: list[dict[str, Any]] = [
    {
        "slug": "ao3k_scexao_lowfs_open",
        "label": "Integrator (LLOWFS open)",
        "ctrl": "Integrator",
        "pf_order": 0,
        "blocksize": 0,
    },
    {
        "slug": "ao3k_scexao_lowfs_closed",
        "label": "Integrator (LLOWFS closed)",
        "ctrl": "Integrator",
        "pf_order": 0,
        "blocksize": 0,
    },
    {
        "slug": "ao3k_scexao_calib2wfs1dm",
        "label": "AR(8) + LLOWFS (ZPO wind-up @4.85s)",
        "ctrl": "AR(8)",
        "pf_order": 8,
        "blocksize": 1,
    },
    {
        "slug": "ao3k_scexao_tlm20s_ar16",
        "label": "AR(16) 20s",
        "ctrl": "AR(16)",
        "pf_order": 16,
        "blocksize": 1,
    },
    {
        "slug": "ao3k_scexao_predictive_eof128_p8",
        "label": "EOF B=128 P=8",
        "ctrl": "EOF(128,8)",
        "pf_order": 8,
        "blocksize": 128,
    },
    {
        "slug": "ao3k_scexao_predictive_eof64_p8",
        "label": "EOF B=64 P=8",
        "ctrl": "EOF(64,8)",
        "pf_order": 8,
        "blocksize": 64,
    },
    {
        "slug": "ao3k_scexao_stg2unmod_eof128_p8",
        "label": "Stg2-Unmod EOF B=128 P=8 (m6)",
        "ctrl": "EOF(128,8)",
        "pf_order": 8,
        "blocksize": 128,
    },
    {
        "slug": "ao3k_scexao_stg2unmod_mh8_eof128_p32",
        "label": "Stg2-Unmod EOF B=128 P=32 (m8)",
        "ctrl": "EOF(128,32)",
        "pf_order": 32,
        "blocksize": 128,
    },
]


def load_fits_cube(tlm_dir: Path, prefix: str) -> np.ndarray | None:
    """Concatenate chronologically sorted streamFITSlog cubes into (N_frames, N_modes) in nm."""
    files = sorted(glob.glob(str(tlm_dir / f"{prefix}_*.fits")))
    if not files:
        return None
    chunks = [np.asarray(fits.getdata(fp), dtype=np.float64) for fp in files]
    arr = np.concatenate(chunks, axis=0)
    arr = arr.reshape(arr.shape[0], -1)
    # Modal telemetry is in microns -> convert to nm for all physical reporting
    return arr * 1e3


def estimate_psol_latency(
    wfs: np.ndarray, dm: np.ndarray, ol: np.ndarray, n_modes: int = 64, max_lag: int = 6
) -> dict[str, Any]:
    """Identify exact PSOL equation OL[t] = alpha * WFS[t] + sum_k c_k DM[t-k]."""
    n = min(len(wfs), len(dm), len(ol))
    m_use = min(n_modes, wfs.shape[1], dm.shape[1], ol.shape[1])
    t0 = max_lag + 2
    t1 = min(n, t0 + 3000)
    y = ol[t0:t1, :m_use].ravel()
    cols = [wfs[t0:t1, :m_use].ravel()]
    for k in range(max_lag + 1):
        cols.append(dm[t0 - k : t1 - k, :m_use].ravel())
    x = np.column_stack(cols)
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    rel_res = float(np.linalg.norm(y - x @ coef) / max(np.linalg.norm(y), 1e-30))
    dm_c = coef[1:]
    abs_c = np.abs(dm_c)
    s_abs = float(np.sum(abs_c))
    tau_hat = float(np.sum(np.arange(len(dm_c)) * abs_c) / max(s_abs, 1e-30))
    dm_sign = float(np.sign(dm_c[int(np.argmax(abs_c))]))
    return {
        "wfsfact_hat": float(coef[0]),
        "tau_hat": tau_hat,
        "d_ceil": int(math.ceil(tau_hat - 1e-6)),
        "dm_sign": dm_sign,
        "rel_res": rel_res,
        "dm_coefs": [float(v) for v in dm_c],
    }


def compute_autocorr_fft(x: np.ndarray, max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    """Compute per-mode variance [nm^2] and biased autocorrelation rho(0..max_lag) via FFT."""
    n, _m = x.shape
    xm = x - np.mean(x, axis=0, keepdims=True)
    nfft = 1 << int(math.ceil(math.log2(n + max_lag + 1)))
    fx = np.fft.rfft(xm, n=nfft, axis=0)
    ac = np.fft.irfft(fx.real**2 + fx.imag**2, n=nfft, axis=0)[: max_lag + 1] / float(n)
    var = ac[0].copy()
    rho = np.zeros_like(ac)
    valid = var > 1e-24
    rho[:, valid] = ac[:, valid] / var[None, valid]
    return var, rho


def compute_crosscorr_fft(w: np.ndarray, u: np.ndarray, max_lag: int) -> np.ndarray:
    """Compute per-mode normalized cross-correlation r_{wu}(k) = Cov(w[t], u[t-k])/(std_w*std_u)
    for k = 0..max_lag (biased 1/N normalization).
    """
    n, _m = w.shape
    wm = w - np.mean(w, axis=0, keepdims=True)
    um = u - np.mean(u, axis=0, keepdims=True)
    var_w = np.mean(wm**2, axis=0)
    var_u = np.mean(um**2, axis=0)
    denom = np.sqrt(np.maximum(var_w * var_u, 0.0))
    nfft = 1 << int(math.ceil(math.log2(n + max_lag + 1)))
    fw = np.fft.rfft(wm, n=nfft, axis=0)
    fu = np.fft.rfft(um, n=nfft, axis=0)
    cc = np.fft.irfft(fw * np.conj(fu), n=nfft, axis=0)[: max_lag + 1] / float(n)
    r = np.zeros_like(cc)
    valid = denom > 1e-24
    r[:, valid] = cc[:, valid] / denom[None, valid]
    return r


def bartlett_q_tilde(
    rho: np.ndarray, n: int, d: int, k_start: int, k_count: int
) -> tuple[np.ndarray, np.ndarray]:
    """Compute Bartlett-corrected Ljung-Box whiteness score Q_tilde_m over [k_start, k_start+k_count)."""
    v_m = 1.0 + 2.0 * np.sum(rho[1:d] ** 2, axis=0)
    ks = np.arange(k_start, k_start + k_count, dtype=np.float64)
    lb_weights = (float(n) * float(n + 2)) / (float(n) - ks)
    q_raw = np.sum(lb_weights[:, None] * (rho[k_start : k_start + k_count] ** 2), axis=0)
    q_tilde = q_raw / (float(k_count) * np.maximum(v_m, 1e-12))
    return v_m, q_tilde


def bartlett_q_xmode_block(
    x_tgt: np.ndarray,
    x_src: np.ndarray,
    rho_tgt: np.ndarray,
    rho_src: np.ndarray,
    d: int,
    k_start: int,
    k_count: int,
    exclude_diag: bool = True,
) -> dict[str, float]:
    """Exact Bartlett-corrected cross-mode lag >= d whiteness statistic Q_xmode.

    By Isserlis' theorem, for ANY vector MA(d-1) process (even with arbitrary lag-0..d-1
    spatial covariance), for every k >= d and every pair (i, j):
        Var(C_ij(k)) = (1/N) * (1 + 2 * sum_{l=1}^{d-1} rho_i(l) * rho_j(l)) = v_ij / N
    exactly, because |k - l| < d and |k + l| < d cannot both hold when k >= d.
    Thus E[Q_xmode] == 1.0 under the optimal-control null, parameter-free and O(K * B^2 * N).
    """
    n, bt = x_tgt.shape
    bs = x_src.shape[1]
    zt = x_tgt - np.mean(x_tgt, axis=0, keepdims=True)
    zs = x_src - np.mean(x_src, axis=0, keepdims=True)
    st = np.sqrt(np.maximum(np.mean(zt**2, axis=0), 1e-24))
    ss = np.sqrt(np.maximum(np.mean(zs**2, axis=0), 1e-24))
    zt = zt / st[None, :]
    zs = zs / ss[None, :]

    # Pairwise Bartlett variance factor v_ij = 1 + 2 * sum_{l=1}^{d-1} rho_tgt[l,i]*rho_src[l,j]
    v_ij = 1.0 + 2.0 * (rho_tgt[1:d].T @ rho_src[1:d])  # shape (bt, bs)
    v_ij = np.maximum(v_ij, 0.25)

    mask = np.ones((bt, bs), dtype=bool)
    if exclude_diag and bt == bs:
        np.fill_diagonal(mask, False)
    n_pairs = int(np.sum(mask))

    q_by_lag = []
    max_z_by_lag = []
    for k in range(k_start, k_start + k_count):
        # C(k) = (1/N) * zt[k:]^T @ zs[:-k]
        ck = (zt[k:].T @ zs[:-k]) / float(n)
        lb_w = (float(n) * float(n + 2)) / float(n - k)
        z2 = lb_w * (ck**2) / v_ij
        vals = z2[mask]
        q_by_lag.append(float(np.mean(vals)))
        max_z_by_lag.append(float(np.sqrt(np.max(vals))))

    return {
        "q_xmode_mean": float(np.mean(q_by_lag)),
        "q_xmode_lag_d": float(q_by_lag[0]),
        "q_xmode_max_z": float(max(max_z_by_lag)),
        "n_pairs": n_pairs,
    }


def bartlett_q_xcorr(
    r_wu: np.ndarray, rho_w: np.ndarray, rho_u: np.ndarray, n: int, d: int, k_start: int, k_count: int
) -> tuple[np.ndarray, np.ndarray]:
    """Bartlett-corrected multi-lag WFS-vs-DM cross-correlation score Q_wu_m for k >= d."""
    v_wu = 1.0 + 2.0 * np.sum(rho_w[1:d] * rho_u[1:d], axis=0)
    v_wu = np.maximum(v_wu, 0.25)
    ks = np.arange(k_start, k_start + k_count, dtype=np.float64)
    w_k = float(n) / (float(n) - ks)
    q_wu = np.sum(w_k[:, None] * float(n) * (r_wu[k_start : k_start + k_count] ** 2), axis=0)
    q_wu /= float(k_count) * v_wu
    return v_wu, q_wu


def modalctrl_stats_estimators(x: np.ndarray) -> dict[str, np.ndarray]:
    """Compare modalCTRL_stats.c finite-difference noise variance estimators."""
    var_tot = np.var(x, axis=0)
    d3 = 0.5 * (x[:-2] + x[2:]) - x[1:-1]
    var_3pt = np.mean(d3**2, axis=0) / 1.5
    # Buggy line 437: sample+1 repeated -> coeffs [-0.5, 1.5, -1.0], sum(c^2) = 3.5 != 5.0
    d4_bug = -0.5 * x[:-3] + 1.5 * x[1:-2] - 1.5 * x[2:-1] + 0.5 * x[2:-1]
    var_4pt_buggy = np.mean(d4_bug**2, axis=0) / 5.0
    # Fixed line 437: sample+2 -> coeffs [-0.5, 1.5, -1.5, 0.5], sum(c^2) = 5.0
    d4_fix = -0.5 * x[:-3] + 1.5 * x[1:-2] - 1.5 * x[2:-1] + 0.5 * x[3:]
    var_4pt_fixed = np.mean(d4_fix**2, axis=0) / 5.0
    return {
        "var_tot": var_tot,
        "var_3pt": var_3pt,
        "var_4pt_buggy": var_4pt_buggy,
        "var_4pt_fixed": var_4pt_fixed,
    }


def _solve_diag_ar_fold(
    y_tr: np.ndarray,
    x_tr: np.ndarray,
    y_te: np.ndarray,
    x_te: np.ndarray,
    d: int,
    p_order: int,
    lam_rel: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fit per-mode ridge y[t] ~ x[t-d..t-d-p+1] on train, return test (var_y, var_err, resid)."""
    n_tr, m = y_tr.shape
    n_te = y_te.shape[0]
    t0 = d + p_order - 1
    ytr = y_tr[t0:] - np.mean(y_tr[t0:], axis=0, keepdims=True)
    yte = y_te[t0:] - np.mean(y_te[t0:], axis=0, keepdims=True)
    xtr_m = x_tr - np.mean(x_tr, axis=0, keepdims=True)
    xte_m = x_te - np.mean(x_te, axis=0, keepdims=True)

    n_r = n_tr - t0
    n_e = n_te - t0
    Xtr = np.empty((m, n_r, p_order), dtype=np.float64)
    Xte = np.empty((m, n_e, p_order), dtype=np.float64)
    for k in range(p_order):
        lag = d + k
        Xtr[:, :, k] = xtr_m[t0 - lag : n_tr - lag].T
        Xte[:, :, k] = xte_m[t0 - lag : n_te - lag].T

    G = np.einsum("mni,mnj->mij", Xtr, Xtr)
    R = np.einsum("mni,nm->mi", Xtr, ytr)
    tr = np.trace(G, axis1=1, axis2=2) / float(p_order)
    eye = np.eye(p_order, dtype=np.float64)[None, :, :]
    A = G + (lam_rel * np.maximum(tr, 1e-24))[:, None, None] * eye
    W = np.linalg.solve(A, R[:, :, None])[:, :, 0]
    pred = np.einsum("mni,mi->nm", Xte, W)
    resid = yte - pred
    var_y = np.mean(yte**2, axis=0)
    var_err = np.mean(resid**2, axis=0)
    return var_y, var_err, resid


def oos_diag_predictability(
    target: np.ndarray,
    predictor: np.ndarray,
    d: int,
    p_order: int = 8,
    lam_rel: float = 1e-2,
) -> dict[str, Any]:
    """2-fold chronological split-half out-of-sample per-mode predictability at lag >= d."""
    n = min(len(target), len(predictor))
    mid = n // 2
    vy1, ve1, _ = _solve_diag_ar_fold(
        target[:mid], predictor[:mid], target[mid:n], predictor[mid:n], d, p_order, lam_rel
    )
    vy2, ve2, _ = _solve_diag_ar_fold(
        target[mid:n], predictor[mid:n], target[:mid], predictor[:mid], d, p_order, lam_rel
    )
    var_y = 0.5 * (vy1 + vy2)
    var_err = 0.5 * (ve1 + ve2)
    prf_m = np.zeros_like(var_y)
    valid = var_y > 1e-24
    prf_m[valid] = 1.0 - var_err[valid] / var_y[valid]
    recov_var_m = np.maximum(prf_m, 0.0) * var_y
    net_var_red = float(np.sum(var_y) - np.sum(var_err))
    return {
        "var_y": var_y,
        "var_err": var_err,
        "prf_m": prf_m,
        "wfs_rms_nm": float(np.sqrt(np.sum(var_y))),
        "recov_wfe_nm": float(np.sqrt(np.sum(recov_var_m))),
        "recov_var_pct": float(np.sum(recov_var_m) / max(np.sum(var_y), 1e-30) * 100.0),
        "net_wfe_nm": float(np.sqrt(max(net_var_red, 0.0))),
        "net_var_pct": float(net_var_red / max(np.sum(var_y), 1e-30) * 100.0),
    }


def _build_lag_matrix(x: np.ndarray, t0: int, d: int, p_order: int) -> np.ndarray:
    """Build (N - t0, p_order * B) lagged design matrix from mean-subtracted x."""
    n, b = x.shape
    xm = x - np.mean(x, axis=0, keepdims=True)
    nrows = n - t0
    H = np.empty((nrows, p_order * b), dtype=np.float64)
    for k in range(p_order):
        lag = d + k
        H[:, k * b : (k + 1) * b] = xm[t0 - lag : n - lag]
    return H


def _solve_block_fold_auto_ridge(
    y_tr: np.ndarray,
    x_tr: np.ndarray,
    y_te: np.ndarray,
    x_te: np.ndarray,
    d: int,
    p_order: int,
    lam_grid: tuple[float, ...] = (1e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0, 3.0, 10.0, float("inf")),
) -> tuple[np.ndarray, np.ndarray, float]:
    """Fit multi-output ridge Y ~ H(X) with inner-split ridge selection (incl. zero-predictor inf)."""
    t0 = d + p_order - 1
    H_tr = _build_lag_matrix(x_tr, t0, d, p_order)
    Y_tr = y_tr[t0:] - np.mean(y_tr[t0:], axis=0, keepdims=True)
    H_te = _build_lag_matrix(x_te, t0, d, p_order)
    Y_te = y_te[t0:] - np.mean(y_te[t0:], axis=0, keepdims=True)

    n_tr = H_tr.shape[0]
    n_in = int(0.75 * n_tr)
    H_in, Y_in = H_tr[:n_in], Y_tr[:n_in]
    H_va, Y_va = H_tr[n_in:], Y_tr[n_in:]
    D = H_in.shape[1]
    G_in = H_in.T @ H_in
    R_in = H_in.T @ Y_in
    tr_in = float(np.trace(G_in)) / float(D)
    eye = np.eye(D, dtype=np.float64)

    best_lam = float("inf")
    best_loss = float(np.sum(Y_va * Y_va))
    if tr_in > 1e-24:
        for lam in lam_grid:
            if not math.isfinite(lam):
                continue
            try:
                W_in = np.linalg.solve(G_in + (lam * tr_in) * eye, R_in)
            except np.linalg.LinAlgError:
                continue
            err = Y_va - H_va @ W_in
            loss = float(np.sum(err * err))
            if loss < best_loss:
                best_loss = loss
                best_lam = lam

    if math.isfinite(best_lam):
        G_tr = H_tr.T @ H_tr
        R_tr = H_tr.T @ Y_tr
        tr_tr = float(np.trace(G_tr)) / float(D)
        if tr_tr > 1e-24:
            W = np.linalg.solve(G_tr + (best_lam * tr_tr) * eye, R_tr)
            pred = H_te @ W
        else:
            pred = np.zeros_like(Y_te)
    else:
        pred = np.zeros_like(Y_te)

    var_y = np.mean(Y_te**2, axis=0)
    var_err = np.mean((Y_te - pred) ** 2, axis=0)
    return var_y, var_err, best_lam


def oos_block_xmode_predictability(
    target: np.ndarray,
    predictor: np.ndarray,
    d: int,
    p_order: int = 8,
    block_slices: list[tuple[int, int]] | None = None,
    pred_slices: list[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """2-fold chronological split-half OOS cross-mode block predictability at lag >= d."""
    n = min(len(target), len(predictor))
    mid = n // 2
    if block_slices is None:
        block_slices = [(0, min(128, target.shape[1]))]
    if pred_slices is None:
        pred_slices = block_slices

    var_y_all = []
    var_err_all = []
    lams = []
    for (ys0, ys1), (xs0, xs1) in zip(block_slices, pred_slices):
        vy1, ve1, l1 = _solve_block_fold_auto_ridge(
            target[:mid, ys0:ys1],
            predictor[:mid, xs0:xs1],
            target[mid:n, ys0:ys1],
            predictor[mid:n, xs0:xs1],
            d,
            p_order,
        )
        vy2, ve2, l2 = _solve_block_fold_auto_ridge(
            target[mid:n, ys0:ys1],
            predictor[mid:n, xs0:xs1],
            target[:mid, ys0:ys1],
            predictor[:mid, xs0:xs1],
            d,
            p_order,
        )
        var_y_all.append(0.5 * (vy1 + vy2))
        var_err_all.append(0.5 * (ve1 + ve2))
        lams.append(l1 if math.isfinite(l1) else -1.0)
        lams.append(l2 if math.isfinite(l2) else -1.0)

    var_y = np.concatenate(var_y_all)
    var_err = np.concatenate(var_err_all)
    prf_m = np.zeros_like(var_y)
    valid = var_y > 1e-24
    prf_m[valid] = 1.0 - var_err[valid] / var_y[valid]
    recov_var_m = np.maximum(prf_m, 0.0) * var_y
    net_var_red = float(np.sum(var_y) - np.sum(var_err))
    return {
        "wfs_rms_nm": float(np.sqrt(np.sum(var_y))),
        "recov_wfe_nm": float(np.sqrt(np.sum(recov_var_m))),
        "recov_var_pct": float(np.sum(recov_var_m) / max(np.sum(var_y), 1e-30) * 100.0),
        "net_wfe_nm": float(np.sqrt(max(net_var_red, 0.0))),
        "net_var_pct": float(net_var_red / max(np.sum(var_y), 1e-30) * 100.0),
        "lams": lams,
    }


def analyze_window(
    wfs: np.ndarray,
    dm: np.ndarray,
    ol: np.ndarray | None,
    pf: np.ndarray | None,
    d: int,
    tau: float,
    pf_order_run: int,
    run_blocksize: int,
    compute_xmode: bool = True,
    k_q: int = 16,
) -> dict[str, Any]:
    """Compute the full whiteness, cliff, recoverable WFE, and WFS-DM cross-corr suite."""
    n, n_modes = wfs.shape
    p_zone = pf_order_run if pf_order_run > 0 else 8
    k_beyond = int(math.floor(tau)) + p_zone
    max_lag = max(64, d + k_q + 20, k_beyond + 20)

    var_w, rho_w = compute_autocorr_fft(wfs, max_lag=max_lag)
    var_u, rho_u = compute_autocorr_fft(dm, max_lag=max_lag)
    r_wu = compute_crosscorr_fft(wfs, dm, max_lag=max_lag)

    b0 = min(128, n_modes)
    lo = min(20, n_modes)
    mid_end = min(128, n_modes)

    def band_weights(s0: int, s1: int) -> np.ndarray:
        v = var_w[s0:s1]
        return v / max(float(np.sum(v)), 1e-30)

    w_all = band_weights(0, n_modes)
    w_b0 = band_weights(0, b0)
    w_lo = band_weights(0, lo)
    w_m20_127 = band_weights(lo, mid_end)

    lags_12 = list(range(1, 13))
    rho_vw_all = [float(np.sum(w_all * rho_w[k])) for k in lags_12]
    rho_rms_all = [float(np.sqrt(np.sum(w_all * rho_w[k] ** 2))) for k in lags_12]
    rho_vw_b0 = [float(np.sum(w_b0 * rho_w[k, :b0])) for k in lags_12]
    rho_rms_b0 = [float(np.sqrt(np.sum(w_b0 * rho_w[k, :b0] ** 2))) for k in lags_12]
    rho_vw_lo = [float(np.sum(w_lo * rho_w[k, :lo])) for k in lags_12]
    rho_rms_lo = [float(np.sqrt(np.sum(w_lo * rho_w[k, :lo] ** 2))) for k in lags_12]
    rho_vw_m20_127 = [float(np.sum(w_m20_127 * rho_w[k, lo:mid_end])) for k in lags_12]
    rho_rms_m20_127 = [float(np.sqrt(np.sum(w_m20_127 * rho_w[k, lo:mid_end] ** 2))) for k in lags_12]

    cliff_all = rho_rms_all[d - 2] / max(rho_rms_all[d - 1], 1e-9)
    cliff_b0 = rho_rms_b0[d - 2] / max(rho_rms_b0[d - 1], 1e-9)
    cliff_lo = rho_rms_lo[d - 2] / max(rho_rms_lo[d - 1], 1e-9)
    cliff_m20_127 = rho_rms_m20_127[d - 2] / max(rho_rms_m20_127[d - 1], 1e-9)

    rho_d_b0 = rho_w[d, :b0]
    frac_pos_d_b0 = float(np.mean(rho_d_b0 > 0.0))
    frac_neg_d_b0 = float(np.mean(rho_d_b0 < 0.0))

    v_m, q_tilde = bartlett_q_tilde(rho_w, n=n, d=d, k_start=d, k_count=k_q)
    _, q_beyond = bartlett_q_tilde(rho_w, n=n, d=d, k_start=k_beyond, k_count=16)
    q_thresh_3sig = 1.0 + 3.0 * math.sqrt(2.0 / float(k_q))

    # WFS-vs-DM cross-correlation metrics for k = 0..12
    lags_0_12 = list(range(0, 13))
    rwu_vw_all = [float(np.sum(w_all * r_wu[k])) for k in lags_0_12]
    rwu_rms_all = [float(np.sqrt(np.sum(w_all * r_wu[k] ** 2))) for k in lags_0_12]
    rwu_vw_b0 = [float(np.sum(w_b0 * r_wu[k, :b0])) for k in lags_0_12]
    rwu_rms_b0 = [float(np.sqrt(np.sum(w_b0 * r_wu[k, :b0] ** 2))) for k in lags_0_12]
    rwu_vw_lo = [float(np.sum(w_lo * r_wu[k, :lo])) for k in lags_0_12]
    rwu_rms_lo = [float(np.sqrt(np.sum(w_lo * r_wu[k, :lo] ** 2))) for k in lags_0_12]
    rwu_vw_m20_127 = [float(np.sum(w_m20_127 * r_wu[k, lo:mid_end])) for k in lags_0_12]
    _, q_wu = bartlett_q_xcorr(r_wu, rho_w, rho_u, n=n, d=d, k_start=d, k_count=k_q)

    # Exact parameter-free Bartlett cross-mode Q_xmode (O(K*B^2*N), zero overfitting)
    q_xmode_b0 = bartlett_q_xmode_block(
        wfs[:, :b0], wfs[:, :b0], rho_w[:, :b0], rho_w[:, :b0], d=d, k_start=d, k_count=8, exclude_diag=True
    )
    q_xmode_m20_127 = bartlett_q_xmode_block(
        wfs[:, lo:mid_end], wfs[:, lo:mid_end], rho_w[:, lo:mid_end], rho_w[:, lo:mid_end],
        d=d, k_start=d, k_count=8, exclude_diag=True
    )
    q_xblk_64 = bartlett_q_xmode_block(
        wfs[:, :64], wfs[:, 64:128], rho_w[:, :64], rho_w[:, 64:128], d=d, k_start=d, k_count=8, exclude_diag=False
    )
    q_xblk_128 = bartlett_q_xmode_block(
        wfs[:, :128], wfs[:, 128:256], rho_w[:, :128], rho_w[:, 128:256], d=d, k_start=d, k_count=8, exclude_diag=False
    )

    # Out-of-sample per-mode lag >= d predictability
    diag_p8 = oos_diag_predictability(wfs, wfs, d=d, p_order=8, lam_rel=1e-2)
    diag_p16 = oos_diag_predictability(wfs, wfs, d=d, p_order=16, lam_rel=1e-2)
    w_from_u = oos_diag_predictability(wfs, dm, d=d, p_order=8, lam_rel=1e-2)

    def slice_recov(res_dict: dict[str, Any], s0: int, s1: int) -> tuple[float, float, float]:
        vy = res_dict["var_y"][s0:s1]
        pm = res_dict["prf_m"][s0:s1]
        rv = np.maximum(pm, 0.0) * vy
        w_rms = float(np.sqrt(np.sum(vy)))
        r_rms = float(np.sqrt(np.sum(rv)))
        r_pct = float(np.sum(rv) / max(np.sum(vy), 1e-30) * 100.0)
        return w_rms, r_rms, r_pct

    _, b0_diag_recov_nm, b0_diag_recov_pct = slice_recov(diag_p8, 0, b0)
    _, lo_diag_recov_nm, lo_diag_recov_pct = slice_recov(diag_p8, 0, lo)
    _, m20_diag_recov_nm, m20_diag_recov_pct = slice_recov(diag_p8, lo, mid_end)
    _, b0_wu_recov_nm, b0_wu_recov_pct = slice_recov(w_from_u, 0, b0)

    xmode_summary: dict[str, Any] = {
        "q_xmode_b0_mean": q_xmode_b0["q_xmode_mean"],
        "q_xmode_b0_lag_d": q_xmode_b0["q_xmode_lag_d"],
        "q_xmode_b0_max_z": q_xmode_b0["q_xmode_max_z"],
        "q_xmode_m20_127_mean": q_xmode_m20_127["q_xmode_mean"],
        "q_xmode_m20_127_max_z": q_xmode_m20_127["q_xmode_max_z"],
        "q_xblk_64_mean": q_xblk_64["q_xmode_mean"],
        "q_xblk_64_max_z": q_xblk_64["q_xmode_max_z"],
        "q_xblk_128_mean": q_xblk_128["q_xmode_mean"],
        "q_xblk_128_max_z": q_xblk_128["q_xmode_max_z"],
    }
    if compute_xmode and n >= 1000:
        # 1) Block 0 cross-mode (B=128, P=4 -> well-conditioned D=512; and B=128, P=8)
        xm_b0_p4 = oos_block_xmode_predictability(
            wfs, wfs, d=d, p_order=4, block_slices=[(0, b0)], pred_slices=[(0, b0)]
        )
        xm_b0_p8 = oos_block_xmode_predictability(
            wfs, wfs, d=d, p_order=8, block_slices=[(0, b0)], pred_slices=[(0, b0)]
        )
        # 2) Tiled blocks (B=64, P=4 -> D=256) on first 512 modes (well-conditioned even at N=5000)
        bs_64 = [(s, min(s + 64, n_modes)) for s in range(0, min(512, n_modes), 64)]
        xm_512_b64_p4 = oos_block_xmode_predictability(
            wfs, wfs, d=d, p_order=4, block_slices=bs_64, pred_slices=bs_64
        )
        w512_rms, diag512_nm, diag512_pct = slice_recov(diag_p8, 0, min(512, n_modes))

        # 3) Zone 3 Cross-block predictability with safe ridge (incl. inf)
        xb_64 = oos_block_xmode_predictability(
            wfs, wfs, d=d, p_order=4, block_slices=[(0, 64)], pred_slices=[(64, 128)]
        )
        xb_128 = oos_block_xmode_predictability(
            wfs, wfs, d=d, p_order=4, block_slices=[(0, 128)], pred_slices=[(128, 256)]
        )
        # 4) Zone 2 Beyond-lookback cross-mode (Block 0 B=64, lag >= k_beyond, P=4)
        z2_b0 = oos_block_xmode_predictability(
            wfs, wfs, d=k_beyond, p_order=4, block_slices=[(0, 64)], pred_slices=[(0, 64)]
        )
        xmode_summary.update(
            {
                "b0_128_p4_recov_nm": xm_b0_p4["recov_wfe_nm"],
                "b0_128_p4_recov_pct": xm_b0_p4["recov_var_pct"],
                "b0_128_p4_net_pct": xm_b0_p4["net_var_pct"],
                "b0_128_p8_recov_nm": xm_b0_p8["recov_wfe_nm"],
                "b0_128_p8_recov_pct": xm_b0_p8["recov_var_pct"],
                "b0_128_p8_net_pct": xm_b0_p8["net_var_pct"],
                "m512_wfs_rms_nm": w512_rms,
                "m512_diag_p8_recov_nm": diag512_nm,
                "m512_diag_p8_recov_pct": diag512_pct,
                "m512_xmode_b64_p4_recov_nm": xm_512_b64_p4["recov_wfe_nm"],
                "m512_xmode_b64_p4_recov_pct": xm_512_b64_p4["recov_var_pct"],
                "m512_xmode_b64_p4_net_pct": xm_512_b64_p4["net_var_pct"],
                "zone3_xblk_64_to_0_recov_nm": xb_64["recov_wfe_nm"],
                "zone3_xblk_64_to_0_net_pct": xb_64["net_var_pct"],
                "zone3_xblk_128_to_0_recov_nm": xb_128["recov_wfe_nm"],
                "zone3_xblk_128_to_0_net_pct": xb_128["net_var_pct"],
                "zone2_beyond_k": k_beyond,
                "zone2_b0_64_recov_nm": z2_b0["recov_wfe_nm"],
                "zone2_b0_64_net_pct": z2_b0["net_var_pct"],
            }
        )

    fd = modalctrl_stats_estimators(wfs)
    fd_summary = {
        "tot_rms_nm": float(np.sqrt(np.sum(fd["var_tot"]))),
        "est3pt_rms_nm": float(np.sqrt(np.sum(fd["var_3pt"]))),
        "est4pt_buggy_rms_nm": float(np.sqrt(np.sum(fd["var_4pt_buggy"]))),
        "est4pt_fixed_rms_nm": float(np.sqrt(np.sum(fd["var_4pt_fixed"]))),
        "n_neg_after_sub_fixed": int(np.sum(fd["var_tot"] < fd["var_4pt_fixed"])),
        "n_neg_after_sub_buggy": int(np.sum(fd["var_tot"] < fd["var_4pt_buggy"])),
    }

    pf_oos: dict[str, float] | None = None
    if ol is not None and pf is not None:
        lat_i = int(math.floor(tau))
        lat_a = tau - float(lat_i)
        n_c = min(len(ol), len(pf))
        if n_c > lat_i + 16:
            t_idx = np.arange(lat_i + 1, n_c)
            pf_del_exact = (1.0 - lat_a) * pf[t_idx - lat_i] + lat_a * pf[t_idx - lat_i - 1]
            ol_t = ol[t_idx]
            ol_zoh = (1.0 - lat_a) * ol[t_idx - lat_i] + lat_a * ol[t_idx - lat_i - 1]
            res_pf = ol_t - pf_del_exact
            res_zoh = ol_t - ol_zoh
            var_ol = float(np.sum(np.var(ol_t, axis=0)))
            var_zoh = float(np.sum(np.mean(res_zoh**2, axis=0)))
            var_pf = float(np.sum(np.mean(res_pf**2, axis=0)))
            pf_oos = {
                "rms_ol_nm": math.sqrt(var_ol),
                "rms_zoh_nm": math.sqrt(var_zoh),
                "rms_pf_oos_nm": math.sqrt(var_pf),
                "var_red_oos_pct": (1.0 - var_pf / max(var_zoh, 1e-30)) * 100.0,
            }

    return {
        "n_frames": int(n),
        "n_modes": int(n_modes),
        "tau": float(tau),
        "d": int(d),
        "wfs_rms_nm": float(np.sqrt(np.sum(var_w))),
        "wfs_b0_rms_nm": float(np.sqrt(np.sum(var_w[:b0]))),
        "wfs_lo_rms_nm": float(np.sqrt(np.sum(var_w[:lo]))),
        "wfs_m20_127_rms_nm": float(np.sqrt(np.sum(var_w[lo:mid_end]))),
        "dm_rms_nm": float(np.sqrt(np.sum(var_u))),
        "ol_rms_nm": float(np.sqrt(np.sum(np.var(ol, axis=0)))) if ol is not None else None,
        "rho_vw_all_1_12": rho_vw_all,
        "rho_rms_all_1_12": rho_rms_all,
        "rho_vw_b0_1_12": rho_vw_b0,
        "rho_rms_b0_1_12": rho_rms_b0,
        "rho_vw_lo_1_12": rho_vw_lo,
        "rho_rms_lo_1_12": rho_rms_lo,
        "rho_vw_m20_127_1_12": rho_vw_m20_127,
        "rho_rms_m20_127_1_12": rho_rms_m20_127,
        "cliff_ratio_all": float(cliff_all),
        "cliff_ratio_b0": float(cliff_b0),
        "cliff_ratio_lo": float(cliff_lo),
        "cliff_ratio_m20_127": float(cliff_m20_127),
        "rho_d_vw_all": float(rho_vw_all[d - 1]),
        "rho_d_vw_b0": float(rho_vw_b0[d - 1]),
        "rho_d_vw_lo": float(rho_vw_lo[d - 1]),
        "rho_d_vw_m20_127": float(rho_vw_m20_127[d - 1]),
        "rho_d_rms_b0": float(rho_rms_b0[d - 1]),
        "rho_d_frac_pos_b0": frac_pos_d_b0,
        "rho_d_frac_neg_b0": frac_neg_d_b0,
        "q_tilde_vw_all": float(np.sum(w_all * q_tilde)),
        "q_tilde_vw_b0": float(np.sum(w_b0 * q_tilde[:b0])),
        "q_tilde_med_b0": float(np.median(q_tilde[:b0])),
        "q_tilde_p90_b0": float(np.percentile(q_tilde[:b0], 90)),
        "q_tilde_mean_lo": float(np.mean(q_tilde[:lo])),
        "q_tilde_med_m20_127": float(np.median(q_tilde[lo:mid_end])),
        "q_tilde_vw_m20_127": float(np.sum(w_m20_127 * q_tilde[lo:mid_end])),
        "q_tilde_med_all": float(np.median(q_tilde)),
        "q_tilde_med_hi": float(np.median(q_tilde[min(512, n_modes - 1) :])),
        "q_tilde_frac_gt3sig_b0": float(np.mean(q_tilde[:b0] > q_thresh_3sig)),
        "q_beyond_vw_b0": float(np.sum(w_b0 * q_beyond[:b0])),
        "q_beyond_med_b0": float(np.median(q_beyond[:b0])),
        "bartlett_v_med_b0": float(np.median(v_m[:b0])),
        "diag_p8_recov_nm": diag_p8["recov_wfe_nm"],
        "diag_p8_recov_pct": diag_p8["recov_var_pct"],
        "diag_p8_net_pct": diag_p8["net_var_pct"],
        "diag_p16_recov_nm": diag_p16["recov_wfe_nm"],
        "diag_p16_recov_pct": diag_p16["recov_var_pct"],
        "diag_p8_b0_recov_nm": b0_diag_recov_nm,
        "diag_p8_b0_recov_pct": b0_diag_recov_pct,
        "diag_p8_lo_recov_nm": lo_diag_recov_nm,
        "diag_p8_lo_recov_pct": lo_diag_recov_pct,
        "diag_p8_m20_127_recov_nm": m20_diag_recov_nm,
        "diag_p8_m20_127_recov_pct": m20_diag_recov_pct,
        "xmode": xmode_summary,
        "rwu_vw_all_0_12": rwu_vw_all,
        "rwu_rms_all_0_12": rwu_rms_all,
        "rwu_vw_b0_0_12": rwu_vw_b0,
        "rwu_rms_b0_0_12": rwu_rms_b0,
        "rwu_vw_lo_0_12": rwu_vw_lo,
        "rwu_rms_lo_0_12": rwu_rms_lo,
        "rwu_vw_m20_127_0_12": rwu_vw_m20_127,
        "rwu_d_vw_b0": float(rwu_vw_b0[d]),
        "rwu_d_rms_b0": float(rwu_rms_b0[d]),
        "rwu_d_vw_lo": float(rwu_vw_lo[d]),
        "rwu_d_rms_lo": float(rwu_rms_lo[d]),
        "rwu_d_vw_m20_127": float(rwu_vw_m20_127[d]),
        "q_wu_vw_b0": float(np.sum(w_b0 * q_wu[:b0])),
        "q_wu_med_b0": float(np.median(q_wu[:b0])),
        "q_wu_mean_lo": float(np.mean(q_wu[:lo])),
        "q_wu_med_m20_127": float(np.median(q_wu[lo:mid_end])),
        "w_from_u_recov_nm": w_from_u["recov_wfe_nm"],
        "w_from_u_recov_pct": w_from_u["recov_var_pct"],
        "w_from_u_b0_recov_nm": b0_wu_recov_nm,
        "w_from_u_b0_recov_pct": b0_wu_recov_pct,
        "modalctrl_fd": fd_summary,
        "pf_oos": pf_oos,
    }


def run_synthetic_selftest() -> dict[str, Any]:
    """Verify Bartlett Q_tilde == 1.0, Q_xmode == 1.0 on spatially correlated MA(2), and FD bugs."""
    rng = np.random.default_rng(42)
    n, m = 5000, 128
    d = 3

    # 1) Pure white noise (sigma = 10 nm)
    eps = rng.normal(0.0, 10.0, size=(n, m))
    _, rho_wn = compute_autocorr_fft(eps, max_lag=32)
    v_wn, q_wn = bartlett_q_tilde(rho_wn, n=n, d=d, k_start=d, k_count=16)
    fd_wn = modalctrl_stats_estimators(eps)

    # 2) Spatially correlated optimal MA(2) residual (d=3, a=0.98) with strong lag-0 mixing matrix L
    #    w_t = e_t + a*e_{t-1} + a^2*e_{t-2}, where Cov(e_t) = L L^T has strong off-diag correlations
    a = 0.98
    L = np.eye(m) + 0.5 * rng.normal(0.0, 1.0 / math.sqrt(m), size=(m, m))
    e_raw = rng.normal(0.0, 10.0, size=(n + 4, m))
    e_corr = e_raw @ L.T
    w_ma2 = e_corr[2 : n + 2] + a * e_corr[1 : n + 1] + (a**2) * e_corr[0:n]
    _, rho_ma2 = compute_autocorr_fft(w_ma2, max_lag=32)
    v_ma2, q_ma2 = bartlett_q_tilde(rho_ma2, n=n, d=d, k_start=d, k_count=16)
    qx_ma2 = bartlett_q_xmode_block(
        w_ma2, w_ma2, rho_ma2, rho_ma2, d=d, k_start=d, k_count=8, exclude_diag=True
    )
    # Naive (uncorrected) Ljung-Box without Bartlett v_m
    ks = np.arange(d, d + 16, dtype=np.float64)
    lb_w = (float(n) * float(n + 2)) / (float(n) - ks)
    q_ma2_naive = np.sum(lb_w[:, None] * (rho_ma2[d : d + 16] ** 2), axis=0) / 16.0
    fd_ma2 = modalctrl_stats_estimators(w_ma2)

    # 3) Linear ramp + sigma=1 white noise
    t = np.arange(n, dtype=np.float64)[:, None]
    x_lin = 0.5 * t + rng.normal(0.0, 1.0, size=(n, m))
    fd_lin = modalctrl_stats_estimators(x_lin)

    return {
        "white_noise_sigma10": {
            "true_var": 100.0,
            "q_tilde_mean": float(np.mean(q_wn)),
            "v_m_mean": float(np.mean(v_wn)),
            "fd_3pt_var_mean": float(np.mean(fd_wn["var_3pt"])),
            "fd_4pt_buggy_var_mean": float(np.mean(fd_wn["var_4pt_buggy"])),
            "fd_4pt_fixed_var_mean": float(np.mean(fd_wn["var_4pt_fixed"])),
        },
        "optimal_corr_ma2_d3_a098": {
            "rho_mean_1_5": [float(np.mean(rho_ma2[k])) for k in range(1, 6)],
            "v_m_mean": float(np.mean(v_ma2)),
            "q_tilde_bartlett_mean": float(np.mean(q_ma2)),
            "q_naive_uncorrected_mean": float(np.mean(q_ma2_naive)),
            "q_xmode_bartlett_mean": qx_ma2["q_xmode_mean"],
            "q_xmode_max_z": qx_ma2["q_xmode_max_z"],
            "fd_4pt_fixed_frac_of_totvar": float(
                np.mean(fd_ma2["var_4pt_fixed"]) / np.mean(fd_ma2["var_tot"])
            ),
            "fd_3pt_frac_of_totvar": float(
                np.mean(fd_ma2["var_3pt"]) / np.mean(fd_ma2["var_tot"])
            ),
        },
        "linear_ramp_plus_sigma1": {
            "true_noise_var": 1.0,
            "fd_3pt_var_mean": float(np.mean(fd_lin["var_3pt"])),
            "fd_4pt_buggy_var_mean": float(np.mean(fd_lin["var_4pt_buggy"])),
            "fd_4pt_fixed_var_mean": float(np.mean(fd_lin["var_4pt_fixed"])),
        },
    }


def analyze_calib2wfs1dm_time_slices(
    wfs: np.ndarray,
    dm: np.ndarray,
    ol: np.ndarray,
    pf: np.ndarray | None,
    fs_hz: float,
    d: int,
    tau: float,
) -> dict[str, Any]:
    """Time-sliced pre-windup vs onset vs wind-up analysis for ao3k_scexao_calib2wfs1dm."""
    windows = [
        ("pre_0.0_4.0s", 0.0, 4.0),
        ("pre_2.0_4.0s", 2.0, 4.0),
        ("onset_4.0_4.5s", 4.0, 4.5),
        ("windup_4.5_5.0s", 4.5, 5.0),
        ("late_4.0_5.0s", 4.0, 5.0),
    ]
    named: dict[str, Any] = {}
    for wname, t0, t1 in windows:
        i0 = int(round(t0 * fs_hz))
        i1 = min(len(wfs), int(round(t1 * fs_hz)))
        if i1 - i0 < 200:
            continue
        named[wname] = analyze_window(
            wfs[i0:i1],
            dm[i0:i1],
            ol[i0:i1],
            pf[i0:i1] if pf is not None else None,
            d=d,
            tau=tau,
            pf_order_run=8,
            run_blocksize=1,
            compute_xmode=(i1 - i0 >= 1500),
            k_q=16,
        )

    win_n = int(round(0.5 * fs_hz))
    stride_n = int(round(0.25 * fs_hz))
    trace = []
    for i0 in range(0, len(wfs) - win_n + 1, stride_n):
        i1 = i0 + win_n
        sub = analyze_window(
            wfs[i0:i1],
            dm[i0:i1],
            ol[i0:i1],
            pf[i0:i1] if pf is not None else None,
            d=d,
            tau=tau,
            pf_order_run=8,
            run_blocksize=1,
            compute_xmode=False,
            k_q=12,
        )
        trace.append(
            {
                "t0_s": i0 / fs_hz,
                "t1_s": i1 / fs_hz,
                "wfs_rms_nm": sub["wfs_rms_nm"],
                "wfs_lo_rms_nm": sub["wfs_lo_rms_nm"],
                "dm_rms_nm": sub["dm_rms_nm"],
                "rho_d_vw_b0": sub["rho_d_vw_b0"],
                "rho_d_vw_lo": sub["rho_d_vw_lo"],
                "q_tilde_vw_b0": sub["q_tilde_vw_b0"],
                "q_tilde_mean_lo": sub["q_tilde_mean_lo"],
                "q_xmode_b0_mean": sub["xmode"]["q_xmode_b0_mean"],
                "diag_p8_recov_nm": sub["diag_p8_recov_nm"],
                "rwu_d_vw_b0": sub["rwu_d_vw_b0"],
                "rwu_d_rms_b0": sub["rwu_d_rms_b0"],
                "rwu_d_vw_lo": sub["rwu_d_vw_lo"],
                "rwu_d_rms_lo": sub["rwu_d_rms_lo"],
                "q_wu_mean_lo": sub["q_wu_mean_lo"],
                "w_from_u_recov_nm": sub["w_from_u_recov_nm"],
            }
        )
    return {"named_windows": named, "sliding_0p5s": trace}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phase 0b AO residual whiteness monitor.")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=OUT_DIR / "whiteness_results.json",
        help="Path to write full JSON results.",
    )
    args = parser.parse_args()
    t_start = time.time()

    print("=== 1. SYNTHETIC NULL & modalCTRL_stats.c SELF-TEST ===")
    selftest = run_synthetic_selftest()
    wn = selftest["white_noise_sigma10"]
    ma2 = selftest["optimal_corr_ma2_d3_a098"]
    lin = selftest["linear_ramp_plus_sigma1"]
    print(
        f"  White noise (true var=100): Q_tilde={wn['q_tilde_mean']:.3f}, v_m={wn['v_m_mean']:.3f} | "
        f"FD 3pt={wn['fd_3pt_var_mean']:.2f}, 4pt_buggy={wn['fd_4pt_buggy_var_mean']:.2f} (0.70x!), "
        f"4pt_fixed={wn['fd_4pt_fixed_var_mean']:.2f}"
    )
    print(
        f"  Spatially-correlated MA(2) (d=3, a=0.98): rho(1..5)={[round(v, 3) for v in ma2['rho_mean_1_5']]}, "
        f"v_m={ma2['v_m_mean']:.3f} | Q_Bartlett={ma2['q_tilde_bartlett_mean']:.3f} vs "
        f"Q_naive={ma2['q_naive_uncorrected_mean']:.3f} | Q_xmode_Bartlett={ma2['q_xmode_bartlett_mean']:.3f} "
        f"(max_z={ma2['q_xmode_max_z']:.2f}) | FD 4pt_fixed/totvar={ma2['fd_4pt_fixed_frac_of_totvar']:.3f}"
    )
    print(
        f"  Linear ramp + sigma=1 noise (true var=1.0): FD 3pt={lin['fd_3pt_var_mean']:.3f}, "
        f"4pt_buggy={lin['fd_4pt_buggy_var_mean']:.3f} (leaks slope!), 4pt_fixed={lin['fd_4pt_fixed_var_mean']:.3f}"
    )

    all_results: dict[str, Any] = {"selftest": selftest, "runs": {}}

    for spec in RUN_SPECS:
        slug = spec["slug"]
        rdir = WORK_ROOT / slug
        tdir = rdir / "telemetry"
        pfs_path = rdir / "pf_stats.json"
        pf_stats = json.loads(pfs_path.read_text()) if pfs_path.is_file() else None
        run_res: dict[str, Any] = {"spec": spec, "pf_stats": pf_stats, "stages": {}}

        print(f"\n==================== {slug} ({spec['label']}) ====================")
        for stg, fs_hz in ((1, 1000.0), (2, 2000.0)):
            wfs = load_fits_cube(tdir, f"aol{stg}_modevalWFS")
            dm = load_fits_cube(tdir, f"aol{stg}_modevalDM")
            ol = load_fits_cube(tdir, f"aol{stg}_modevalOL")
            pf = load_fits_cube(tdir, f"aol{stg}_modevalPF")
            if wfs is None or dm is None:
                continue

            lat_info = (
                estimate_psol_latency(wfs, dm, ol)
                if ol is not None
                else {"tau_hat": 2.4, "d_ceil": 3, "wfsfact_hat": 1.0, "rel_res": float("nan")}
            )
            tau = lat_info["tau_hat"]
            d = lat_info["d_ceil"]

            res = analyze_window(
                wfs,
                dm,
                ol,
                pf,
                d=d,
                tau=tau,
                pf_order_run=spec["pf_order"],
                run_blocksize=spec["blocksize"],
                compute_xmode=True,
                k_q=16,
            )
            res["psol_id"] = lat_info
            res["fs_hz"] = fs_hz

            if slug == "ao3k_scexao_calib2wfs1dm":
                res["calib2wfs1dm_time_slices"] = analyze_calib2wfs1dm_time_slices(
                    wfs, dm, ol, pf, fs_hz=fs_hz, d=d, tau=tau
                )

            run_res["stages"][f"stg{stg}"] = res
            xm = res["xmode"]
            print(
                f"  [Stg{stg}] N={res['n_frames']} M={res['n_modes']} tau={tau:.3f} (d={d}) "
                f"WFS={res['wfs_rms_nm']:.1f}nm (lo20={res['wfs_lo_rms_nm']:.1f}, m20-127={res['wfs_m20_127_rms_nm']:.1f}) DM={res['dm_rms_nm']:.1f}nm"
            )
            print(
                f"    Cliff B0 |rho|(1..6): {[round(v, 3) for v in res['rho_rms_b0_1_12'][:6]]} "
                f"(cliff={res['cliff_ratio_b0']:.2f}x) | m20-127 |rho|(1..6): {[round(v, 3) for v in res['rho_rms_m20_127_1_12'][:6]]} "
                f"(cliff={res['cliff_ratio_m20_127']:.2f}x) | signed B0(1..6): {[round(v, 3) for v in res['rho_vw_b0_1_12'][:6]]}"
            )
            print(
                f"    Q_tilde (k>=d): vw_all={res['q_tilde_vw_all']:.2f} vw_B0={res['q_tilde_vw_b0']:.2f} "
                f"med_B0={res['q_tilde_med_b0']:.2f} lo20={res['q_tilde_mean_lo']:.2f} "
                f"m20-127_med={res['q_tilde_med_m20_127']:.2f} | Q_xmode B0={xm['q_xmode_b0_mean']:.2f} "
                f"(lag_d={xm['q_xmode_b0_lag_d']:.2f}, max_z={xm['q_xmode_b0_max_z']:.1f}) "
                f"m20-127={xm['q_xmode_m20_127_mean']:.2f} | xblk64={xm['q_xblk_64_mean']:.2f} xblk128={xm['q_xblk_128_mean']:.2f}"
            )
            print(
                f"    Recov WFE: diag_P8={res['diag_p8_recov_nm']:.1f}nm ({res['diag_p8_recov_pct']:.1f}%) "
                f"diag_P16={res['diag_p16_recov_nm']:.1f}nm | "
                f"B0 diag={res['diag_p8_b0_recov_nm']:.1f}nm (lo20={res['diag_p8_lo_recov_nm']:.1f}, m20-127={res['diag_p8_m20_127_recov_nm']:.1f}) vs "
                f"xmode(128,4)={xm.get('b0_128_p4_recov_nm', 0):.1f}nm ({xm.get('b0_128_p4_recov_pct', 0):.1f}%) | "
                f"m512 diag={xm.get('m512_diag_p8_recov_nm', 0):.1f}nm vs xmode(64,4)={xm.get('m512_xmode_b64_p4_recov_nm', 0):.1f}nm"
            )
            print(
                f"    WFS-DM xcorr: r_wu_B0(d)={res['rwu_d_vw_b0']:+.3f} (lo20={res['rwu_d_vw_lo']:+.3f}, m20-127={res['rwu_d_vw_m20_127']:+.3f}), "
                f"Q_wu_B0={res['q_wu_vw_b0']:.2f}, Q_wu_lo20={res['q_wu_mean_lo']:.2f}, "
                f"W|U recov={res['w_from_u_recov_nm']:.1f}nm ({res['w_from_u_recov_pct']:.1f}%)"
            )
            if res["pf_oos"] is not None:
                po = res["pf_oos"]
                insamp = (
                    pf_stats[f"stage{stg}"]["rms_pred"] * 1e3
                    if pf_stats and f"stage{stg}" in pf_stats
                    else float("nan")
                )
                insamp_vr = (
                    pf_stats[f"stage{stg}"]["var_red_pct"]
                    if pf_stats and f"stage{stg}" in pf_stats
                    else float("nan")
                )
                print(
                    f"    PF OL->PF: in-sample={insamp:.1f}nm ({insamp_vr:.1f}%) vs "
                    f"live OOS={po['rms_pf_oos_nm']:.1f}nm ({po['var_red_oos_pct']:.1f}% vs ZOH {po['rms_zoh_nm']:.1f}nm)"
                )

        all_results["runs"][slug] = run_res

    print("\n=== CALIB2WFS1DM TIME-RESOLVED WIND-UP ANALYSIS (t = 4.85s) ===")
    c_res = all_results["runs"]["ao3k_scexao_calib2wfs1dm"]["stages"]
    for stg_key in ("stg1", "stg2"):
        ts = c_res[stg_key]["calib2wfs1dm_time_slices"]
        print(f"  --- {stg_key} named windows ---")
        for wname, wdata in ts["named_windows"].items():
            print(
                f"    {wname:16s} N={wdata['n_frames']:4d} WFS={wdata['wfs_rms_nm']:5.1f}nm (lo={wdata['wfs_lo_rms_nm']:4.1f}nm) "
                f"DM={wdata['dm_rms_nm']:5.1f}nm | rho_B0(d)={wdata['rho_d_vw_b0']:+.3f} "
                f"Q_B0={wdata['q_tilde_vw_b0']:6.2f} Q_lo={wdata['q_tilde_mean_lo']:6.2f} Q_xm={wdata['xmode']['q_xmode_b0_mean']:5.2f} "
                f"recov={wdata['diag_p8_recov_nm']:4.1f}nm | "
                f"r_wu_lo(d)={wdata['rwu_d_vw_lo']:+.3f} (rms {wdata['rwu_d_rms_lo']:.3f}) "
                f"Q_wu_lo={wdata['q_wu_mean_lo']:6.2f} W|U={wdata['w_from_u_recov_nm']:4.1f}nm"
            )
        print(f"  --- {stg_key} sliding 0.5s trace ---")
        for row in ts["sliding_0p5s"]:
            print(
                f"    t=[{row['t0_s']:4.2f},{row['t1_s']:4.2f}] WFS={row['wfs_rms_nm']:5.1f} (lo={row['wfs_lo_rms_nm']:4.1f}) "
                f"DM={row['dm_rms_nm']:5.1f} | rho_lo(d)={row['rho_d_vw_lo']:+.3f} Q_lo={row['q_tilde_mean_lo']:5.2f} "
                f"Q_xm={row['q_xmode_b0_mean']:4.2f} recov={row['diag_p8_recov_nm']:4.1f} | "
                f"r_wu_lo(d)={row['rwu_d_vw_lo']:+.3f} (rms {row['rwu_d_rms_lo']:.3f}) "
                f"Q_wu_lo={row['q_wu_mean_lo']:6.2f} W|U={row['w_from_u_recov_nm']:4.1f}"
            )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out_json} in {time.time() - t_start:.1f} s.")


if __name__ == "__main__":
    main()
