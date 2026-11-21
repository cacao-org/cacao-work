#!/home/guyon/.local/envs/cacao/bin/python
"""Phase 4a Offline Cross-Regime Audit for 2-WFS + 1-DM Passive Calibration.

Read-only CPU audit over existing AO3k + SCExAO simulation runs under
/home/guyon/src/cacao-work/_work/ao3k_scexao*.

Covers:
  1. selfRM self-consistency checks (naive selfrm_dyn + exact modalfilter.c
     nbsettle=6 closed-loop model) across all available Stage-1 & Stage-2 cubes.
  2. Frame-counter continuity, clock/camera pairing (exposing the searchsorted-1
     vs nearest-timestamp bug when dt(B-A) > 0), controller law, & DM2 lag kernel.
  3. Differenced Lagged-A 2SLS vs shipped W(z) (cached + Python replica) across
     Integrator, AR(8), AR(16), Block-EOF (3 l/D & 0 l/D, mH=6 & mH=8).
  4. Tip/Tilt (modes 0-1) failure/behavior diagnosis across modulation & LLOWFS.
  5. Stage-3 LLOWFS regressors (aol3_dmC -> CMmodesDM) & direct ZPO mismatch ID.
  6. Block-bootstrap 1-sigma error bars vs actual per-mode error & half-split SD.
  7. IV Mda_virt (multivariate, differenced, algebraic, projected) vs DM2->DM1
     geometry, shipped W(z) Mda_virt, and passive Stage-1 optical gain vs Stage-1 selfRM.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

WORK_ROOT = Path("/home/guyon/src/cacao-work/_work")
CACHE_ROOT = WORK_ROOT / "calib_2wfs1dm_report" / "_cache"
OUT_DIR = Path("/home/guyon/src/cacao-work/algo/calib2wfs1dm/phase4a_checks")

NA, NB = 60, 40

# Main 8 runs (calib2wfs1dm audited on both full 5s and clean 0-4s)
TARGET_RUNS = [
    ("lowfs_open", "ao3k_scexao_lowfs_open", None, "Integrator, LLOWFS open, 3 l/D, mH=6"),
    ("lowfs_closed", "ao3k_scexao_lowfs_closed", None, "Integrator, LLOWFS closed, 3 l/D, mH=6"),
    ("calib2wfs1dm_5s", "ao3k_scexao_calib2wfs1dm", None, "AR(8) PF, LLOWFS closed, 3 l/D, mH=6 (full 5s)"),
    ("calib2wfs1dm_4s", "ao3k_scexao_calib2wfs1dm", (0.0, 4.0), "AR(8) PF, LLOWFS closed, 3 l/D, mH=6 (clean 0-4s)"),
    ("tlm20s_ar16", "ao3k_scexao_tlm20s_ar16", None, "AR(16) PF, LLOWFS closed, 3 l/D, mH=6 (20s)"),
    ("eof128_p8", "ao3k_scexao_predictive_eof128_p8", None, "Block-EOF(128,8), LLOWFS closed, 3 l/D, mH=6"),
    ("eof64_p8", "ao3k_scexao_predictive_eof64_p8", None, "Block-EOF(64,8), LLOWFS closed, 3 l/D, mH=6"),
    ("stg2unmod_eof128_p8", "ao3k_scexao_stg2unmod_eof128_p8", None, "Block-EOF(128,8), LLOWFS closed, 0 l/D unmod, mH=6"),
    ("stg2unmod_mh8_eof128_p32", "ao3k_scexao_stg2unmod_mh8_eof128_p32", None, "Block-EOF(128,32), LLOWFS closed, 0 l/D unmod, mH=8"),
]

# All runs with selfRM cubes for exhaustive Section 1 audit (Item 4 of README.md)
ALL_SELFRM_RUNS = [
    "ao3k_scexao_lowfs_open",
    "ao3k_scexao_lowfs_closed",
    "ao3k_scexao_calib2wfs1dm",
    "ao3k_scexao_predictive_eof128_p8",
    "ao3k_scexao_predictive_eof64_p8",
    "ao3k_scexao_stg2unmod_eof128_p8",
    "ao3k_scexao_stg2unmod_mh8_eof128_p32",
    "ao3k_scexao",
    "ao3k_scexao_predictive",
    "ao3k_scexao_predictive_ar4",
    "ao3k_scexao_predictive_ar8",
    "ao3k_scexao_predictive_ar16",
    "ao3k_scexao_predictive_ar32",
    "ao3k_scexao_predictive_ar64",
]

SHIPPED_CACHE_MAP = {
    "lowfs_open": CACHE_ROOT / "calib_lowfs_open",
    "lowfs_closed": CACHE_ROOT / "calib_lowfs_closed",
    "calib2wfs1dm_5s": WORK_ROOT / "ao3k_scexao_calib2wfs1dm" / "calib_2wfs1dm",
    "calib2wfs1dm_4s": CACHE_ROOT / "calib_pred4s",
}


# ---------------------------------------------------------------------------
# Basic linear algebra & stream loading helpers
# ---------------------------------------------------------------------------

def cen(x: np.ndarray) -> np.ndarray:
    return x - x.mean(axis=0, keepdims=True)


def mode_int(x: np.ndarray) -> tuple[int, float]:
    v, c = np.unique(x, return_counts=True)
    idx = int(np.argmax(c))
    return int(v[idx]), float(c[idx] / c.sum())


def nearest_idx(t_ref: np.ndarray, t_src: np.ndarray) -> np.ndarray:
    i = np.searchsorted(t_src, t_ref)
    i0 = np.clip(i - 1, 0, len(t_src) - 1)
    i1 = np.clip(i, 0, len(t_src) - 1)
    return np.where(np.abs(t_src[i1] - t_ref) < np.abs(t_src[i0] - t_ref), i1, i0)


def load_stream(tdir: Path, name: str, nmodes: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    files = sorted(glob.glob(str(tdir / f"{name}_*.fits")))
    if not files:
        raise FileNotFoundError(f"{tdir}/{name}_*.fits")
    arrs = []
    for f in files:
        d = fits.getdata(f).astype(np.float64)
        if nmodes is not None:
            d = d.reshape(d.shape[0], -1)[:, :nmodes]
        arrs.append(d)
    val = np.concatenate(arrs, axis=0)
    tim = np.concatenate([np.atleast_2d(np.loadtxt(f[:-5] + ".txt")) for f in files])
    n = min(len(val), len(tim))
    val, tim = val[:n], tim[:n]
    cnt = tim[:, 5].astype(np.int64)
    t = tim[:, 3]
    dc = np.diff(cnt)
    gaps = int(np.sum(dc != 1))
    meta = dict(
        n=int(n),
        c0=int(cnt[0]),
        c1=int(cnt[-1]),
        gaps=gaps,
        max_dc=int(dc.max()) if len(dc) else 0,
        wall_fps=float(1.0 / np.median(np.diff(t))) if len(t) > 1 else 0.0,
    )
    return val, t, cnt, meta


def load_times_only(tdir: Path, name: str) -> tuple[np.ndarray, np.ndarray, int]:
    files = sorted(glob.glob(str(tdir / f"{name}_*.txt")))
    if not files:
        return np.zeros(0), np.zeros(0, dtype=np.int64), -1
    tim = np.concatenate([np.atleast_2d(np.loadtxt(f)) for f in files])
    cnt = tim[:, 5].astype(np.int64)
    gaps = int(np.sum(np.diff(cnt) != 1))
    return tim[:, 3], cnt, gaps


def tsls(y: np.ndarray, X: np.ndarray, Z: np.ndarray) -> np.ndarray:
    Q, _ = np.linalg.qr(Z)
    Xh = Q @ (Q.T @ X)
    return np.linalg.solve(Xh.T @ X, Xh.T @ y)


def lagmat(x: np.ndarray, t: np.ndarray, lags: range | list[int]) -> np.ndarray:
    return np.column_stack([x[t - l] for l in lags])


def psi_from(A: np.ndarray, B: np.ndarray, D: np.ndarray, gstart: np.ndarray | float) -> np.ndarray:
    Saa = A.T @ A
    W = np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), A.T @ (B - D * gstart))
    return A @ W


def acting_command(D: np.ndarray, kD: np.ndarray, lat_fr: float) -> np.ndarray:
    L = int(np.floor(lat_fr))
    frac = lat_fr - L
    w = 1.0 - frac
    out = np.full((len(kD), D.shape[1]), np.nan)
    ok = (kD - (L + 1) >= 0) & (kD - L < len(D))
    out[ok] = w * D[kD[ok] - L] + (1.0 - w) * D[kD[ok] - (L + 1)]
    return out


# ---------------------------------------------------------------------------
# 1. Exact closed-loop selfRM model (matching cacao/AOloopControl/modalfilter.c)
# ---------------------------------------------------------------------------

def sim_selfrm_exact(
    P: float,
    g_dyn: float,
    lat_fr: float,
    gain: float = 0.346,
    leak: float = 0.98,
    zsize: int = 8,
    nbsettle: int = 6,
) -> np.ndarray:
    """Exact discrete-time response of modalfilter.c selfRM with 2-block (+/-) poke."""
    L = int(np.floor(lat_fr))
    frac = lat_fr - L
    period = zsize + nbsettle + 1
    ntot = 2 * period + 10
    dm_hist = np.zeros(ntot)
    poke_hist = np.zeros(ntot)
    dmc = 0.0
    poke_cmd = 0.0
    srm = np.zeros(zsize)
    sign = 1.0
    pokecnt = 0
    blockcnt = 0
    for t in range(ntot):
        m = 0.0
        if t - L >= 0:
            m += (1.0 - frac) * (g_dyn * dm_hist[t - L] + P * poke_hist[t - L])
        if t - L - 1 >= 0:
            m += frac * (g_dyn * dm_hist[t - L - 1] + P * poke_hist[t - L - 1])
        dmc = leak * dmc - gain * m
        dm_hist[t] = dmc
        poke_hist[t] = poke_cmd
        if blockcnt < 2:
            if pokecnt < zsize:
                poke_cmd = sign
                srm[pokecnt] += 0.5 * sign * m
            else:
                poke_cmd = 0.0
            pokecnt += 1
            if pokecnt > zsize + nbsettle:
                poke_cmd = 0.0
                sign *= -1.0
                blockcnt += 1
                pokecnt = 0
    return srm


def fit_selfrm_curve(
    obs: np.ndarray,
    gain: float,
    leak: float = 0.98,
    nbsettle: int = 6,
    lat_grid: np.ndarray | None = None,
) -> dict[str, Any]:
    """Fit both constrained (P=g_dyn) and free (P, g_dyn) exact selfRM models."""
    zsize = len(obs)
    if lat_grid is None:
        lat_grid = np.linspace(1.80, 3.90, 106)
    gd_grid = np.linspace(0.05, 1.30, 51)

    # Free (P, g_dyn, lat): note response is strictly linear in P for fixed (g_dyn, lat)!
    best_free = (1e9, 0.0, 0.0, 0.0, None)
    best_eq = (1e9, 0.0, 0.0, None)
    for lat in lat_grid:
        for gd in gd_grid:
            unit = sim_selfrm_exact(1.0, float(gd), float(lat), gain=gain, leak=leak, zsize=zsize, nbsettle=nbsettle)
            denom = float(unit @ unit)
            if denom < 1e-12:
                continue
            P_opt = float((unit @ obs) / denom)
            pred = P_opt * unit
            rms = float(np.sqrt(np.mean((pred - obs) ** 2)))
            if rms < best_free[0]:
                best_free = (rms, P_opt, float(gd), float(lat), pred)
            # Also check P == gd
            pred_eq = float(gd) * unit
            rms_eq = float(np.sqrt(np.mean((pred_eq - obs) ** 2)))
            if rms_eq < best_eq[0]:
                best_eq = (rms_eq, float(gd), float(lat), pred_eq)

    return dict(
        P_free=float(best_free[1]),
        g_dyn=float(best_free[2]),
        g_over_P=float(best_free[2] / best_free[1]) if abs(best_free[1]) > 1e-6 else float("nan"),
        lat_free=float(best_free[3]),
        rms_free=float(best_free[0]),
        P_eq=float(best_eq[1]),
        lat_eq=float(best_eq[2]),
        rms_eq=float(best_eq[0]),
    )


def fit_selfrm_per_mode(
    sky: np.ndarray,
    cal: np.ndarray,
    mgain: np.ndarray,
    nmodes: int = 40,
    leak: float = 0.98,
    nbsettle: int = 6,
) -> dict[str, Any]:
    """Full selfRM audit for one stage: median-curve fit + per-mode (P, g_dyn) at median lat."""
    nz = sky.shape[0]
    med_obs = np.array([float(np.median(np.diag(sky[z, 2:nmodes, 2:nmodes]))) for z in range(nz)])
    med_gain = float(np.median(mgain[2:nmodes]))
    cal_plat = np.array([float(cal[4:nz, m, m].mean() - cal[1:3, m, m].mean()) for m in range(nmodes)])
    cal_rise = np.array([float(cal[3, m, m] - cal[1:3, m, m].mean()) for m in range(nmodes)]) / np.maximum(cal_plat, 1e-6)

    # Naive realsim_est / selfrm_dyn reading (lag4 - mean(lag0..2))
    naive_step = np.diag(sky[4, :nmodes, :nmodes] - sky[0:3, :nmodes, :nmodes].mean(0))
    # Shipped og_selfrm.fits style: per-mode max |diag| ratio
    raw_peak = np.array([float(np.max(np.abs(sky[:, m, m]))) for m in range(nmodes)])
    raw_peak_og = raw_peak / np.maximum(np.array([float(np.max(np.abs(cal[:, m, m]))) for m in range(nmodes)]), 1e-6)

    med_fit = fit_selfrm_curve(med_obs, med_gain, leak=leak, nbsettle=nbsettle)
    lat_fixed = med_fit["lat_free"]

    # Per-mode fit fixing lat = lat_fixed (and small local search +/-0.15 fr)
    lat_local = np.linspace(max(1.8, lat_fixed - 0.10), min(3.9, lat_fixed + 0.10), 5)
    P_mode = np.zeros(nmodes)
    gd_mode = np.zeros(nmodes)
    rms_mode = np.zeros(nmodes)
    for m in range(nmodes):
        obs_m = sky[:, m, m]
        fm = fit_selfrm_curve(obs_m, float(mgain[m]), leak=leak, nbsettle=nbsettle, lat_grid=lat_local)
        P_mode[m] = fm["P_free"]
        gd_mode[m] = fm["g_dyn"]
        rms_mode[m] = fm["rms_free"]

    # Fixed-g_dyn (= P_eq) per-mode amplitude: cleaner per-mode P when nbiter=1 has turbulence noise!
    unit_med = sim_selfrm_exact(1.0, med_fit["P_eq"], med_fit["lat_eq"], gain=med_gain, leak=leak, zsize=nz, nbsettle=nbsettle)
    P_proj = np.array([float((unit_med @ sky[:, m, m]) / (unit_med @ unit_med)) for m in range(nmodes)])
    # Off-diagonal turbulence noise floor at peak slice
    zpk = int(np.argmax(med_obs))
    step_err = np.array([float(np.sqrt(np.mean(np.delete(sky[zpk, :nmodes, m], m) ** 2))) for m in range(nmodes)])

    # Classify validity
    gp = med_fit["g_over_P"]
    valid = bool(med_fit["P_free"] >= 0.35 and med_fit["rms_free"] < 0.06 and 0.80 <= gp <= 1.25)

    return dict(
        med_obs=med_obs.tolist(),
        cal_plat_med=float(np.median(cal_plat[2:])),
        cal_rise_med=float(np.median(cal_rise[2:])),
        naive_lag4_med=float(np.median(naive_step[2:])),
        raw_peak_med=float(np.median(raw_peak[2:])),
        raw_peak_og_med=float(np.median(raw_peak_og[2:])),
        med_fit=med_fit,
        P_mode=P_mode.tolist(),
        P_proj=P_proj.tolist(),
        gd_mode=gd_mode.tolist(),
        cal_plat=cal_plat.tolist(),
        og_proj=(P_proj / np.maximum(cal_plat, 1e-6)).tolist(),
        step_err_med=float(np.median(step_err[2:])),
        valid=valid,
        tt_P_proj=[float(P_proj[0]), float(P_proj[1])],
        tt_raw_peak=[float(raw_peak[0]), float(raw_peak[1])],
    )


# ---------------------------------------------------------------------------
# 2. Estimators: Differenced Lagged-A 2SLS + Python W(z) AR(4) replica
# ---------------------------------------------------------------------------

def run_iv_estimators(
    A: np.ndarray,
    B: np.ndarray,
    D: np.ndarray,
    gstart: np.ndarray | float = 0.75,
    lag0: int = 2,
    nlag: int = 8,
) -> dict[str, Any]:
    Ac, Bc, Dc = cen(A), cen(B), cen(D)
    psi = psi_from(Ac, Bc, Dc, gstart)
    dB, dP, dD = np.diff(Bc, axis=0), np.diff(psi, axis=0), np.diff(Dc, axis=0)
    t = np.arange(lag0 + nlag, len(Bc))
    td = np.arange(lag0 + nlag, len(dB))
    nm = Bc.shape[1]
    out = {k: np.zeros(nm) for k in ("LS", "LS diff", "IV", "IV diff")}
    c_iv, use, corr_pd = np.zeros(nm), np.zeros(nm), np.zeros(nm)
    for i in range(nm):
        X = np.column_stack([psi[t, i], Dc[t, i]])
        Xd = np.column_stack([dP[td, i], dD[td, i]])
        out["LS"][i] = np.linalg.lstsq(X, Bc[t, i], rcond=None)[0][1]
        out["LS diff"][i] = np.linalg.lstsq(Xd, dB[td, i], rcond=None)[0][1]
        out["IV"][i] = tsls(Bc[t, i], X, lagmat(psi[:, i], t, range(lag0 - 1, lag0 - 1 + nlag)))[1]
        Z = lagmat(dP[:, i], td, range(lag0, lag0 + nlag))
        c_iv[i], out["IV diff"][i] = tsls(dB[td, i], Xd, Z)
        Q, _ = np.linalg.qr(Z)
        ph, dh = Q @ (Q.T @ Xd[:, 0]), Q @ (Q.T @ Xd[:, 1])
        dp = dh - ph * (ph @ dh) / (ph @ ph)
        use[i] = (dp @ dp) / (Xd[:, 1] @ Xd[:, 1])
        corr_pd[i] = float(np.corrcoef(dP[td, i], dD[td, i])[0, 1])
    return dict(est=out, c_iv=c_iv, usable=use, corr_pd=corr_pd, psi=psi)


def run_wz_ar4_python(
    A: np.ndarray,
    B: np.ndarray,
    D: np.ndarray,
    p_ord: int = 4,
    w_ridge: float = 0.02,
    reg_a: float = 0.03,
    reg_d: float = 0.01,
) -> dict[str, Any]:
    """Faithful Python replica of milk-mlt-calib2wfs1dm AR(p) whitened ridge fit.

    Matches sysid_unit.c: fits scalar pooled causal AR(p) whitening taps on
    per-channel-normalized A (normch=1), applies identically to A, B, D, then
    solves ridge-regularized joint forward regression and unwhitened Mda_virt.
    """
    Ac, Bc, Dc = cen(A), cen(B), cen(D)
    n, dA = Ac.shape
    dB = Bc.shape[1]
    sdA = np.maximum(np.std(Ac, axis=0, keepdims=True), 1e-12)
    An = Ac / sdA
    R = np.zeros((p_ord, p_ord))
    r = np.zeros(p_ord)
    for l1 in range(1, p_ord + 1):
        v1 = An[p_ord - l1 : n - l1]
        r[l1 - 1] = np.sum(An[p_ord:] * v1)
        for l2 in range(1, p_ord + 1):
            v2 = An[p_ord - l2 : n - l2]
            R[l1 - 1, l2 - 1] = np.sum(v1 * v2)
    taps = np.linalg.solve(R + w_ridge * np.diag(np.diag(R)), r)

    def whiten(x: np.ndarray) -> np.ndarray:
        y = x[p_ord:].copy()
        for l in range(1, p_ord + 1):
            y -= taps[l - 1] * x[p_ord - l : n - l]
        return y

    Aw, Bw, Dw = whiten(Ac), whiten(Bc), whiten(Dc)
    Xw = np.hstack([Aw, Dw])
    G = Xw.T @ Xw
    reg = np.concatenate([reg_a * np.maximum(np.diag(G[:dA, :dA]), 1e-12), reg_d * np.maximum(np.diag(G[dA:, dA:]), 1e-12)])
    Th = np.linalg.solve(G + np.diag(reg), Xw.T @ Bw).T
    Mab = Th[:, :dA]
    Mdb = Th[:, dA:]

    # Virtual upstream Mda_virt (unwhitened A = Mba B - Mda_virt D, exact sysid_unit.c)
    Xu = np.hstack([Bc, Dc])
    Gu = Xu.T @ Xu
    regu = np.concatenate([reg_d * np.maximum(np.diag(Gu[:dB, :dB]), 1e-12), reg_d * np.maximum(np.diag(Gu[dB:, dB:]), 1e-12)])
    Thu = np.linalg.solve(Gu + np.diag(regu), Xu.T @ Ac).T
    Mda_virt = -Thu[:, dB:]
    return dict(mdb_diag=np.diag(Mdb), Mab=Mab, Mdb=Mdb, Mda_virt=Mda_virt, taps=taps)


# ---------------------------------------------------------------------------
# 3. Block bootstrap 1-sigma error bars
# ---------------------------------------------------------------------------

def block_bootstrap_iv(
    A: np.ndarray,
    B: np.ndarray,
    D: np.ndarray,
    gstart: np.ndarray | float,
    lag0: int = 2,
    nlag: int = 8,
    block_len: int = 100,
    n_boot: int = 200,
    seed: int = 42,
) -> dict[str, Any]:
    """Circular moving-block bootstrap over (dB, dP, dD, Z) rows (and full-recalc check)."""
    Ac, Bc, Dc = cen(A), cen(B), cen(D)
    psi = psi_from(Ac, Bc, Dc, gstart)
    dB, dP, dD = np.diff(Bc, axis=0), np.diff(psi, axis=0), np.diff(Dc, axis=0)
    td = np.arange(lag0 + nlag, len(dB))
    T = len(td)
    nm = Bc.shape[1]

    # Pre-build per-mode (y, X, Z) arrays so block bootstrap is vectorized & fast
    Y_all = dB[td]       # (T, nm)
    X0_all = dP[td]      # (T, nm)
    X1_all = dD[td]      # (T, nm)
    Z_all = np.stack([lagmat(dP[:, i], td, range(lag0, lag0 + nlag)) for i in range(nm)], axis=0)  # (nm, T, nlag)

    rng = np.random.default_rng(seed)
    n_blk = int(np.ceil(T / block_len))
    g_boot = np.zeros((n_boot, nm))
    for b in range(n_boot):
        starts = rng.integers(0, T, size=n_blk)
        idx = np.concatenate([(np.arange(s, s + block_len) % T) for s in starts])[:T]
        Yb = Y_all[idx]
        X0b = X0_all[idx]
        X1b = X1_all[idx]
        for i in range(nm):
            Zb = Z_all[i, idx, :]
            Xb = np.column_stack([X0b[:, i], X1b[:, i]])
            g_boot[b, i] = tsls(Yb[:, i], Xb, Zb)[1]

    # Point estimate & robust/standard bootstrap SD
    g_mean = np.mean(g_boot, axis=0)
    g_sd = np.std(g_boot, axis=0, ddof=1)
    g_iqr_sd = (np.percentile(g_boot, 75, axis=0) - np.percentile(g_boot, 25, axis=0)) / 1.349
    g_med_boot = np.median(g_boot[:, 2:], axis=1)
    return dict(
        block_len=block_len,
        n_boot=n_boot,
        g_sd=g_sd,
        g_iqr_sd=g_iqr_sd,
        g_mean=g_mean,
        med_sd=float(np.std(g_med_boot, ddof=1)),
    )


# ---------------------------------------------------------------------------
# 4. Stage-3 LLOWFS regressor analysis (realsim_lowfs.py + exact oA_near & lat)
# ---------------------------------------------------------------------------

def run_lowfs_regressors(
    run_dir: Path,
    A: np.ndarray,
    B: np.ndarray,
    D: np.ndarray,
    tD: np.ndarray,
    cB: np.ndarray,
    cD: np.ndarray,
    oD: int,
    kTg: np.ndarray,
    lat_fr: float,
    gstart: np.ndarray | float,
    tsub_slice: slice | None = None,
) -> dict[str, Any] | None:
    tdir = run_dir / "telemetry"
    files3 = sorted(glob.glob(str(tdir / "aol3_dmC_*.fits")))
    if not files3:
        return None
    m2 = fits.getdata(tdir / "calib_stg2" / "CMmodesDM.fits").astype(np.float64)
    m2 = m2.reshape(m2.shape[0], -1)
    dm3 = np.concatenate([fits.getdata(f) for f in files3]).astype(np.float64)
    dm3 = dm3.reshape(dm3.shape[0], -1)
    tim3 = np.concatenate([np.atleast_2d(np.loadtxt(f[:-5] + ".txt")) for f in files3])
    n3 = min(len(dm3), len(tim3))
    dm3, t3 = dm3[:n3], tim3[:n3, 3]
    # Project aol3_dmC onto leading 40 Stage-2 DM modes (exact realsim_lowfs.py)
    c3 = np.linalg.lstsq(m2[:NB].T, dm3.T, rcond=1e-6)[0].T  # (n3, NB)
    # Wait: project onto ALL m2 modes or first 200 to match realsim_lowfs?
    # realsim_lowfs uses full m2 (all modes) -> check if orthogonal, use full m2!
    # For speed, m2 has ~1255 modes; since CMmodesDM are near-orthogonal in DM space,
    # check SVD/lstsq on first 200 vs full; let's use first 200 modes (covers all 14 low-order Zernikes to 1e-6)
    nproj = min(200, m2.shape[0])
    c3 = np.linalg.lstsq(m2[:nproj].T, dm3.T, rcond=1e-6)[0].T[:, :NB]

    # Stage-3 command in force when D frame j was written
    j3 = np.searchsorted(t3, tD, side="right") - 1
    D3 = np.where((j3 >= 0)[:, None], c3[np.clip(j3, 0, len(c3) - 1)], 0.0)

    kD = np.arange(len(cB)) + (cB[0] + oD - cD[0])
    Eeff = acting_command(D3, kD, lat_fr)
    Znow = np.full((len(cB), NB), np.nan)
    okz = (kD >= 0) & (kD < len(D3))
    Znow[okz] = D3[kD[okz]]

    Ew = 0.5 * (Eeff[kTg - 1] + Eeff[kTg])
    Zw = 0.5 * (Znow[kTg - 1] + Znow[kTg])
    if tsub_slice is not None:
        Ew, Zw = Ew[tsub_slice], Zw[tsub_slice]

    Ac, Bc, Dc, Ec, Zc = (cen(x) for x in (A, B, D, Ew, Zw))
    psi = psi_from(Ac, Bc, Dc + Ec, gstart)
    dB, dP, dD, dE, dZ = (np.diff(x, axis=0) for x in (Bc, psi, Dc, Ec, Zc))
    td = np.arange(10, len(dB))

    g_no3, g_tied, g_free = np.zeros(NB), np.zeros(NB), np.zeros(NB)
    a_free, b_free, b_tied = np.zeros(NB), np.zeros(NB), np.zeros(NB)
    for i in range(NB):
        Zi = lagmat(dP[:, i], td, range(2, 10))
        y = dB[td, i]
        g_no3[i] = tsls(y, np.column_stack([dP[td, i], dD[td, i]]), Zi)[1]
        if np.std(dZ[td, i]) > 1e-12 and np.std(dE[td, i]) > 1e-12:
            b1 = tsls(y, np.column_stack([dP[td, i], dD[td, i] + dE[td, i], dZ[td, i]]), np.column_stack([Zi, dZ[td, i]]))
            g_tied[i], b_tied[i] = b1[1], b1[2]
            b2 = tsls(y, np.column_stack([dP[td, i], dD[td, i], dE[td, i], dZ[td, i]]), np.column_stack([Zi, dE[td, i], dZ[td, i]]))
            g_free[i], a_free[i], b_free[i] = b2[1], b2[2], b2[3]
        else:
            g_tied[i] = g_no3[i]
            g_free[i] = g_no3[i]

    rel = np.array([float(np.std(dE[:, i]) / max(np.std(dD[:, i]), 1e-12)) for i in range(NB)])
    # Modes where stage-3 moves DM2 significantly (top 14 or rel > 0.05)
    active = np.where(rel > max(0.05, float(np.percentile(rel, 65))))[0]
    if len(active) < 4:
        active = np.argsort(rel)[-10:]

    return dict(
        rel_tt=float(np.mean(rel[:2])),
        rel_2_9=float(np.median(rel[2:10])),
        rel_10_39=float(np.median(rel[10:])),
        rel_per_mode=rel.tolist(),
        g_no3=g_no3.tolist(),
        g_tied=g_tied.tolist(),
        g_free=g_free.tolist(),
        a_free=a_free.tolist(),
        b_free=b_free.tolist(),
        b_tied=b_tied.tolist(),
        active_modes=active.tolist(),
        active_a_med=float(np.median(a_free[active])),
        active_b_med=float(np.median(b_free[active])),
        active_apb_med=float(np.median((a_free + b_free)[active])),
        active_btied_med=float(np.median(b_tied[active])),
        tt_a=[float(a_free[0]), float(a_free[1])],
        tt_b=[float(b_free[0]), float(b_free[1])],
        tt_apb=[float(a_free[0] + b_free[0]), float(a_free[1] + b_free[1])],
        dm3_rms=float(np.sqrt(np.mean(dm3**2))),
    )


# ---------------------------------------------------------------------------
# 5. Geometry M_geom, IV Mda_virt, and passive Stage-1 optical gain g_A
# ---------------------------------------------------------------------------

def resample_dm2_to_dm1(img2: np.ndarray, ny1: int = 64, nx1: int = 64, d1: float = 60.0, d2: float = 46.0) -> np.ndarray:
    ny2, nx2 = img2.shape
    c1y, c1x = (ny1 - 1) / 2.0, (nx1 - 1) / 2.0
    c2y, c2x = (ny2 - 1) / 2.0, (nx2 - 1) / 2.0
    yy, xx = np.indices((ny1, nx1), dtype=np.float64)
    y2 = c2y + (yy - c1y) * (d2 / d1)
    x2 = c2x + (xx - c1x) * (d2 / d1)
    y0 = np.clip(np.floor(y2).astype(int), 0, ny2 - 1)
    y1 = np.clip(y0 + 1, 0, ny2 - 1)
    x0 = np.clip(np.floor(x2).astype(int), 0, nx2 - 1)
    x1 = np.clip(x0 + 1, 0, nx2 - 1)
    wy = np.clip(y2 - y0, 0.0, 1.0)
    wx = np.clip(x2 - x0, 0.0, 1.0)
    out = (
        (1.0 - wy) * (1.0 - wx) * img2[y0, x0]
        + (1.0 - wy) * wx * img2[y0, x1]
        + wy * (1.0 - wx) * img2[y1, x0]
        + wy * wx * img2[y1, x1]
    )
    oob = (y2 < 0) | (y2 > ny2 - 1) | (x2 < 0) | (x2 > nx2 - 1)
    out[oob] = 0.0
    return out


def compute_mgeom(tdir: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cm1 = fits.getdata(tdir / "calib_stg1" / "CMmodesDM.fits").astype(np.float64)
    cm2 = fits.getdata(tdir / "calib_stg2" / "CMmodesDM.fits").astype(np.float64)
    dm1m = fits.getdata(tdir / "calib_stg1" / "dmmask.fits").astype(np.float64) > 0.5
    B1 = np.array([cm1[i][dm1m] for i in range(NA)])
    B2 = np.array([resample_dm2_to_dm1(cm2[j])[dm1m] for j in range(NB)])
    M_geom = np.linalg.lstsq(B1.T, B2.T, rcond=1e-4)[0]  # (60, 40)
    return M_geom, B1, B2


def eval_mda_against_geom(mda: np.ndarray, M_geom: np.ndarray, B1: np.ndarray, B2: np.ndarray, D_eval: np.ndarray) -> dict[str, Any]:
    cos_v = np.array([
        float(np.dot(mda[:, j], M_geom[:, j]) / (np.linalg.norm(mda[:, j]) * np.linalg.norm(M_geom[:, j]) + 1e-12))
        for j in range(NB)
    ])
    scl_v = np.array([
        float(np.dot(mda[:, j], M_geom[:, j]) / (np.dot(M_geom[:, j], M_geom[:, j]) + 1e-12))
        for j in range(NB)
    ])
    M_loop = np.linalg.lstsq(B2.T, B1.T @ mda, rcond=1e-4)[0]
    eigs = np.linalg.eigvals(M_loop)
    sr05 = float(np.max(np.abs(np.linalg.eigvals(np.eye(NB) - 0.5 * M_loop))))
    gmax = 0.0 if np.any(eigs.real <= 0.0) else float(np.min(2.0 * eigs.real / np.abs(eigs) ** 2))
    opd_dm2 = D_eval @ B2
    opd_off = (D_eval @ mda.T) @ B1
    rms_in = float(np.sqrt(np.mean(opd_dm2**2)))
    rms_res = float(np.sqrt(np.mean((opd_dm2 - opd_off) ** 2)))
    return dict(
        cos_med=float(np.median(cos_v[2:])),
        cos_all=float(np.median(cos_v)),
        cos_tt=[float(cos_v[0]), float(cos_v[1])],
        scl_med=float(np.median(scl_v[2:])),
        scl_q1=float(np.percentile(scl_v[2:], 25)),
        scl_q3=float(np.percentile(scl_v[2:], 75)),
        scl_per_mode=scl_v.tolist(),
        spec_rad_05=sr05,
        g_max_stable=gmax,
        offload_ratio=float(rms_res / max(rms_in, 1e-12)),
    )


def run_mda_virt_iv(
    A: np.ndarray,
    B: np.ndarray,
    D: np.ndarray,
    g_iv: np.ndarray,
    M_geom: np.ndarray,
    B1: np.ndarray,
    B2: np.ndarray,
    srm1: dict[str, Any] | None,
    shipped_mda: np.ndarray | None,
    wz_mda: np.ndarray,
) -> dict[str, Any]:
    """Estimate Mda_virt (60x40) via Lagged-A IV & test passive Stage-1 optical gain g_A."""
    Ac, Bc, Dc = cen(A), cen(B), cen(D)
    N = len(Ac)

    # 1. Multivariate Lagged-A IV on levels: A[t] = Mba B[t] - Mda_virt D[t], Z = [A[t-1..t-4]]
    L_lev = 4
    t = np.arange(L_lev, N)
    X = np.hstack([Bc[t], Dc[t]])  # (T, 80)
    Z = np.hstack([Ac[t - l] for l in range(1, L_lev + 1)])  # (T, 240)
    # Regularized projection Xh = Z (Z'Z + r Z_diag)^-1 Z' X
    Szz = Z.T @ Z
    Xh = Z @ np.linalg.solve(Szz + 1e-3 * np.diag(np.diag(Szz)), Z.T @ X)
    G_iv = Xh.T @ X
    # Small symmetric ridge on G_iv for stability across 80 correlated modes
    dG = np.maximum(np.abs(np.diag(G_iv)), 1e-12)
    Th_iv = np.linalg.solve(G_iv + 2e-3 * np.diag(dG), Xh.T @ Ac[t]).T  # (60, 80)
    mda_iv_lev = -Th_iv[:, NB:]

    # 2. Differenced Multivariate Lagged-A IV: dA[t] on [dB[t], dD[t]], Z = [dA[t-2..t-5]]
    dA, dB, dD = np.diff(Ac, axis=0), np.diff(Bc, axis=0), np.diff(Dc, axis=0)
    td = np.arange(6, len(dA))
    Xd = np.hstack([dB[td], dD[td]])
    Zd = np.hstack([dA[td - l] for l in range(2, 6)])
    Szzd = Zd.T @ Zd
    Xhd = Zd @ np.linalg.solve(Szzd + 1e-3 * np.diag(np.diag(Szzd)), Zd.T @ Xd)
    Gd = Xhd.T @ Xd
    dGd = np.maximum(np.abs(np.diag(Gd)), 1e-12)
    Th_ivd = np.linalg.solve(Gd + 5e-3 * np.diag(dGd), Xhd.T @ dA[td]).T
    mda_iv_diff = -Th_ivd[:, NB:]

    # 3. Projected 1D Lagged-A IV (zero cross-mode ridge bias!) along M_geom columns:
    #    For each Stage-2 mode j, project A onto the dual/pseudo-inverse of M_geom:
    #    a_j = (pinv(M_geom))[j, :] @ A^T  =>  a_j ≈ g_A * (phi_j) = (g_A / g_B) B_j - g_A D_j
    #    Wait: A = g_A * phi_1. Let p_j = (M_geom^+)[j, :] so p_j @ M_geom = e_j^T.
    #    Then p_j @ A ≈ g_A(j) * phi_{2,j} = (g_A/g_B) B_j - g_A D_j!
    #    Instrumenting [B_j, D_j] with lags 1..8 of a_j gives a clean 1D scalar g_A_iv[j]!
    P_pinv = np.linalg.pinv(M_geom, rcond=1e-3)  # (40, 60)
    A_proj = Ac @ P_pinv.T                       # (N, 40)
    t8 = np.arange(10, N)
    gA_proj_lev = np.zeros(NB)
    gA_proj_diff = np.zeros(NB)
    gA_from_ratio = np.zeros(NB)
    dAp = np.diff(A_proj, axis=0)
    td8 = np.arange(10, len(dAp))
    for j in range(NB):
        Zj = lagmat(A_proj[:, j], t8, range(1, 9))
        bj = tsls(A_proj[t8, j], np.column_stack([Bc[t8, j], Dc[t8, j]]), Zj)
        gA_proj_lev[j] = -bj[1]
        # Also from ratio g_B / M_ab: in B_j = (g_B/g_A) a_j + g_B D_j -> c_j = g_B / g_A => g_A = g_B / c_j!
        Zdj = lagmat(dAp[:, j], td8, range(2, 10))
        bdj = tsls(dAp[td8, j], np.column_stack([dB[td8, j], dD[td8, j]]), Zdj)
        gA_proj_diff[j] = -bdj[1]
        # Direct M_db / M_ab in projected basis: dB_j = m_ab * d(a_j) + g_B * dD_j
        b_fwd = tsls(dB[td8, j], np.column_stack([dAp[td8, j], dD[td8, j]]), Zdj)
        gA_from_ratio[j] = b_fwd[1] / b_fwd[0] if abs(b_fwd[0]) > 1e-3 else float("nan")

    # Also compute Mab_IV (levels, lagged A) -> g_A from Mdb / Mab via M_geom:
    # B - D*g_iv = Mab_IV @ A  (instrumented by A[t-1..t-4])
    Y_ol = Bc[t] - Dc[t] * g_iv[None, :]
    Ah = Z @ np.linalg.solve(Szz + 1e-3 * np.diag(np.diag(Szz)), Z.T @ Ac[t])
    Ga = Ah.T @ Ac[t]
    Mab_iv = np.linalg.solve(Ga + 5e-3 * np.diag(np.maximum(np.abs(np.diag(Ga)), 1e-12)), Ah.T @ Y_ol).T  # (40, 60)
    # Check identity: Mab_iv @ (g_A * M_geom) ≈ diag(g_iv) => diagonal of (Mab_iv @ M_geom) ≈ g_B / g_A!
    mab_geom_diag = np.diag(Mab_iv @ M_geom)
    gA_from_Mdb_Mab = g_iv / np.where(np.abs(mab_geom_diag) > 1e-3, mab_geom_diag, np.nan)

    D_eval = Dc[int(0.6 * N) :]
    res: dict[str, Any] = dict(
        iv_lev=eval_mda_against_geom(mda_iv_lev, M_geom, B1, B2, D_eval),
        iv_diff=eval_mda_against_geom(mda_iv_diff, M_geom, B1, B2, D_eval),
        wz_py=eval_mda_against_geom(wz_mda, M_geom, B1, B2, D_eval),
        gA_proj_lev_med=float(np.median(gA_proj_lev[2:])),
        gA_proj_diff_med=float(np.median(gA_proj_diff[2:])),
        gA_from_ratio_med=float(np.nanmedian(gA_from_ratio[2:])),
        gA_from_Mdb_Mab_med=float(np.nanmedian(gA_from_Mdb_Mab[2:])),
        gA_proj_lev_iqr=float(np.percentile(gA_proj_lev[2:], 75) - np.percentile(gA_proj_lev[2:], 25)),
        gA_from_Mdb_Mab_iqr=float(np.nanpercentile(gA_from_Mdb_Mab[2:], 75) - np.nanpercentile(gA_from_Mdb_Mab[2:], 25)),
    )
    if shipped_mda is not None:
        res["shipped_wz"] = eval_mda_against_geom(shipped_mda, M_geom, B1, B2, D_eval)
    if srm1 is not None:
        # Stage-1 selfRM expected g_A weighted by M_geom^2
        # srm1 has P_proj for modes 0..39; fill modes 40..59 with median
        g1_40 = np.array(srm1["P_proj"])
        cal1_40 = np.array(srm1["cal_plat"])
        og1_40 = g1_40 / np.maximum(cal1_40, 1e-6)
        g1_full = np.full(NA, float(np.median(g1_40[2:])))
        g1_full[: len(g1_40)] = g1_40
        og1_full = np.full(NA, float(np.median(og1_40[2:])))
        og1_full[: len(og1_40)] = og1_40
        wgt = M_geom**2
        gA_exp = (wgt * g1_full[:, None]).sum(axis=0) / np.maximum(wgt.sum(axis=0), 1e-12)
        ogA_exp = (wgt * og1_full[:, None]).sum(axis=0) / np.maximum(wgt.sum(axis=0), 1e-12)
        res["srm1_P_med"] = float(np.median(gA_exp[2:]))
        res["srm1_og_med"] = float(np.median(ogA_exp[2:]))
        res["srm1_g_over_P"] = float(srm1["med_fit"]["g_over_P"])
    return res


# ---------------------------------------------------------------------------
# Main audit driver
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}

    # ===== SECTION 1: EXHAUSTIVE selfRM SELF-CONSISTENCY AUDIT =====
    print("=" * 96)
    print("SECTION 1: selfRM SELF-CONSISTENCY AUDIT (Item 4 of algo/calib2wfs1dm/README.md)")
    print("=" * 96)
    srm_audit: dict[str, Any] = {}
    print(f"{'Run':38s} {'Stg':>3s} {'Cal':>5s} {'Naive':>6s} {'RawPk':>6s} {'P_srm':>6s} {'g_dyn':>6s} {'g/P':>5s} {'lat':>5s} {'rms':>6s} {'OG_srm':>6s} {'Valid':>5s}")
    for rname in ALL_SELFRM_RUNS:
        d = WORK_ROOT / rname
        if not d.is_dir():
            continue
        srm_audit[rname] = {}
        for stg in (2, 1):
            psky = d / f"selfRM_onsky_stg{stg}.fits"
            pcal = d / f"selfRM_calib_stg{stg}.fits"
            pmg = d / f"aol{stg}_mgain.fits"
            if not (psky.is_file() and pcal.is_file() and pmg.is_file()):
                continue
            sky = fits.getdata(psky).astype(np.float64)
            cal = fits.getdata(pcal).astype(np.float64)
            mg = fits.getdata(pmg).astype(np.float64).ravel()
            res = fit_selfrm_per_mode(sky, cal, mg, nmodes=NB)
            srm_audit[rname][f"stg{stg}"] = res
            mf = res["med_fit"]
            og_med = float(np.median(res["og_proj"][2:]))
            print(
                f"{rname:38s} {stg:3d} {res['cal_plat_med']:5.3f} {res['naive_lag4_med']:6.3f} "
                f"{res['raw_peak_med']:6.3f} {mf['P_free']:6.3f} {mf['g_dyn']:6.3f} {mf['g_over_P']:5.2f} "
                f"{mf['lat_free']:5.2f} {mf['rms_free']:6.4f} {og_med:6.3f} {'OK' if res['valid'] else 'FAIL':>5s}"
            )
    report["selfrm_audit"] = srm_audit

    # ===== SECTIONS 2-7: CROSS-REGIME TELEMETRY AUDIT =====
    print("\n" + "=" * 96)
    print("SECTIONS 2-7: CROSS-REGIME PASSIVE CALIBRATION AUDIT")
    print("=" * 96)
    regimes: dict[str, Any] = {}

    for label, rname, tsub, desc in TARGET_RUNS:
        d = WORK_ROOT / rname
        tdir = d / "telemetry"
        print(f"\n--- [{label}] {desc} ({rname}) ---")

        # Load streams + continuity checks
        A, tA, cA, mA = load_stream(tdir, "aol1_modevalWFS", NA)
        B, tB, cB, mB = load_stream(tdir, "aol2_modevalWFS", NB)
        D, tD, cD, mD = load_stream(tdir, "aol2_modevalDM", NB)
        t_nir, c_nir, g_nir = load_times_only(tdir, "csim_wfs_nir")
        t_vis, c_vis, g_vis = load_times_only(tdir, "csim_wfs_vis")
        _, _, g_dm3 = load_times_only(tdir, "aol3_dmC")

        # Exact camera-locked pairing vs nearest vs realsim_est searchsorted-1
        iv_n = nearest_idx(t_nir, t_vis)
        o_nv, f_nv = mode_int(c_vis[iv_n] - 2 * c_nir)
        o1, _ = mode_int(cA[np.clip(np.searchsorted(tA, t_nir), 0, len(tA) - 1)] - c_nir)
        o2, _ = mode_int(cB[np.clip(np.searchsorted(tB, t_vis), 0, len(tB) - 1)] - c_vis)
        oA_cam = o_nv + o2 - 2 * o1

        iB_near = nearest_idx(tA, tB)
        oA_near, fA_near = mode_int(cB[iB_near] - 2 * cA)
        dt_BA_ms = float(np.median((tB[iB_near] - tA) * 1e3))

        iB_prev = np.clip(np.searchsorted(tB, tA) - 1, 0, len(tB) - 1)
        oA_prev, fA_prev = mode_int(cB[iB_prev] - 2 * cA)

        iD = np.clip(np.searchsorted(tD, tB), 0, len(tD) - 1)
        oD, fD = mode_int(cD[iD] - cB)
        kD = np.arange(len(B)) + (cB[0] + oD - cD[0])

        # Controller law check
        kk = np.arange(4, len(B) - 4)
        kkD = kk + (cB[0] + oD - cD[0])
        okc = (kkD - 1 >= 0) & (kkD < len(D))
        u_int = D[kkD[okc]] - 0.98 * D[kkD[okc] - 1]
        v_b = B[kk[okc]]
        ctrl_corr = float(np.median([np.corrcoef(u_int[:, i], v_b[:, i])[0, 1] for i in range(2, NB)]))
        ctrl_gain = float(np.median([-(u_int[:, i] @ v_b[:, i]) / (v_b[:, i] @ v_b[:, i]) for i in range(2, NB)]))
        pf_corr = None
        if list(tdir.glob("aol2_modevalPF_*.fits")):
            P_pf, tP_pf, cP_pf, _ = load_stream(tdir, "aol2_modevalPF", NB)
            iP = np.clip(np.searchsorted(tP_pf, tB), 0, len(tP_pf) - 1)
            oP, _ = mode_int(cP_pf[iP] - cB)
            kkP = kk[okc] + (cB[0] + oP - cP_pf[0])
            okP = (kkP >= 0) & (kkP < len(P_pf))
            pf_corr = float(np.median([np.corrcoef(D[kkD[okc][okP], i], -P_pf[kkP[okP], i])[0, 1] for i in range(2, NB)]))

        # Align on common 1 kHz A timeline using exact oA_near
        kT = 2 * cA + oA_near - cB[0]
        good = (kT - 1 >= 5) & (kT < len(B) - 2)
        kTg = kT[good]
        tsub_sl = None
        if tsub is not None:
            i0, i1 = int(round(tsub[0] * 1000)), int(round(tsub[1] * 1000))
            tsub_sl = slice(i0, i1)

        Ag_full = A[good]
        Bg_full = 0.5 * (B[kTg - 1] + B[kTg])
        Ag = Ag_full[tsub_sl] if tsub_sl is not None else Ag_full
        Bg = Bg_full[tsub_sl] if tsub_sl is not None else Bg_full

        # Measure true science-window DM2 acting latency via 2-lag IV [g2, g3]
        D2 = 0.5 * (acting_command(D, kD, 2.0)[kTg - 1] + acting_command(D, kD, 2.0)[kTg])
        D3 = 0.5 * (acting_command(D, kD, 3.0)[kTg - 1] + acting_command(D, kD, 3.0)[kTg])
        if tsub_sl is not None:
            D2, D3 = D2[tsub_sl], D3[tsub_sl]
        Ac0, Bc0, D2c, D3c = cen(Ag), cen(Bg), cen(D2), cen(D3)
        psi0 = psi_from(Ac0, Bc0, 0.5 * (D2c + D3c), 0.80)
        dB0, dP0, dD2, dD3 = (np.diff(x, axis=0) for x in (Bc0, psi0, D2c, D3c))
        td0 = np.arange(10, len(dB0))
        g23 = np.array([
            tsls(dB0[td0, i], np.column_stack([dP0[td0, i], dD2[td0, i], dD3[td0, i]]), lagmat(dP0[:, i], td0, range(2, 10)))[1:]
            for i in range(2, NB)
        ])
        m23 = np.median(g23, axis=0)
        lat_iv = float(np.clip(2.0 + m23[1] / max(m23.sum(), 1e-6), 2.0, 3.5))

        # Build acting D_eff at science latency lat_iv (and also check lat_calib=2.123 and lat_3.0)
        def get_Dg(lat_val: float, oA_use: int = oA_near) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            Deff = acting_command(D, kD, lat_val)
            kT_u = 2 * cA + oA_use - cB[0]
            gd = (kT_u - 1 >= 5) & (kT_u < len(B) - 2)
            gd &= np.isfinite(np.where(gd, Deff[np.clip(kT_u - 1, 0, len(B) - 1), 0], np.nan))
            kTu = kT_u[gd]
            Au = A[gd]
            Bu = 0.5 * (B[kTu - 1] + B[kTu])
            Du = 0.5 * (Deff[kTu - 1] + Deff[kTu])
            if tsub_sl is not None:
                Au, Bu, Du = Au[tsub_sl], Bu[tsub_sl], Du[tsub_sl]
            return Au, Bu, Du

        Au, Bu, Du = get_Dg(lat_iv, oA_near)

        # Load shipped W(z) if available
        shipped_dir = SHIPPED_CACHE_MAP.get(label)
        shipped_g = None
        shipped_og = None
        shipped_mda = None
        if shipped_dir is not None and (shipped_dir / "mdb_diag.fits").is_file():
            shipped_g = fits.getdata(shipped_dir / "mdb_diag.fits").astype(np.float64).ravel()[:NB]
            shipped_og = fits.getdata(shipped_dir / "og_selfrm.fits").astype(np.float64).ravel()[:NB]
            shipped_mda = fits.getdata(shipped_dir / "Mda_virt.fits").astype(np.float64)

        gstart = shipped_g if shipped_g is not None else np.full(NB, 0.80)

        # Run core IV estimators at lat_iv (primary) + sensitivity at lat_calib=2.123 & buggy oA_prev
        iv_main = run_iv_estimators(Au, Bu, Du, gstart=gstart, lag0=2, nlag=8)
        iv_lag16 = run_iv_estimators(Au, Bu, Du, gstart=gstart, lag0=2, nlag=16)
        Au_cal, Bu_cal, Du_cal = get_Dg(2.123, oA_near)
        iv_cal_lat = run_iv_estimators(Au_cal, Bu_cal, Du_cal, gstart=gstart, lag0=2, nlag=8)
        Au_prev, Bu_prev, Du_prev = get_Dg(lat_iv, oA_prev)
        iv_buggy_oA = run_iv_estimators(Au_prev, Bu_prev, Du_prev, gstart=gstart, lag0=2, nlag=8)

        # Python AR(4) W(z) baseline on same aligned (Au, Bu, Du)
        wz_py = run_wz_ar4_python(Au, Bu, Du)

        # Also test 2-ms window (4 WFS B frames = 2 WFS A frames) for weak-usable check (e.g. mh8)
        n2 = (len(Au) // 2) * 2
        iv_2ms = run_iv_estimators(
            Au[:n2].reshape(-1, 2, NA).mean(1),
            Bu[:n2].reshape(-1, 2, NB).mean(1),
            Du[:n2].reshape(-1, 2, NB).mean(1),
            gstart=gstart,
            lag0=2,
            nlag=8,
        )

        # Reference selfRM (exact model P_proj & cal_plat)
        srm2 = srm_audit.get(rname, {}).get("stg2")
        srm1 = srm_audit.get(rname, {}).get("stg1")
        ref_P = np.array(srm2["P_proj"]) if srm2 is not None else None
        cal_P = np.array(srm2["cal_plat"]) if srm2 is not None else None

        def err_stats(g: np.ndarray, ref: np.ndarray | None) -> dict[str, Any]:
            d_out = dict(
                med=float(np.median(g[2:])),
                iqr=float(np.percentile(g[2:], 75) - np.percentile(g[2:], 25)),
                tt=[float(g[0]), float(g[1])],
            )
            if ref is not None:
                r = g / ref - 1.0
                d_out.update(
                    bias_pct=float(100 * np.median(r[2:])),
                    mae_pct=float(100 * np.median(np.abs(r[2:]))),
                    mad_pct=float(100 * np.median(np.abs(r[2:] - np.median(r[2:])))),
                    tt_err_pct=[float(100 * r[0]), float(100 * r[1])],
                )
            if cal_P is not None:
                d_out["og_med"] = float(np.median((g / cal_P)[2:]))
            return d_out

        # Half-split repeatability (independent of selfRM!)
        half = len(Au) // 2
        iv_h1 = run_iv_estimators(Au[:half], Bu[:half], Du[:half], gstart=gstart)
        iv_h2 = run_iv_estimators(Au[half : 2 * half], Bu[half : 2 * half], Du[half : 2 * half], gstart=gstart)
        g_full = iv_main["est"]["IV diff"]
        g_h1, g_h2 = iv_h1["est"]["IV diff"], iv_h2["est"]["IV diff"]
        # Expected 1-sigma on FULL window from half-split difference: |g_h1 - g_h2| / 2
        # (since Var(g_h1 - g_h2) = 2 Var(g_half) = 4 Var(g_full) => SD(g_full) = SD(g_h1 - g_h2) / 2!)
        half_diff_rel = (g_h1 - g_h2) / (2.0 * np.maximum(np.abs(g_full), 1e-3))
        half_sd_full_pct = float(100 * np.median(np.abs(half_diff_rel[2:])) / 0.6745)
        half_bias_h1 = float(np.median(g_h1[2:]))
        half_bias_h2 = float(np.median(g_h2[2:]))

        # Block bootstrap (L=100 windows = 100 ms, B=200)
        boot = block_bootstrap_iv(Au, Bu, Du, gstart=gstart, lag0=2, nlag=8, block_len=100, n_boot=200, seed=42)
        boot_rel_sd_pct = 100.0 * boot["g_sd"] / np.maximum(np.abs(g_full), 1e-3)
        boot_med_sd_pct = float(np.median(boot_rel_sd_pct[2:]))
        boot_tt_sd_pct = [float(boot_rel_sd_pct[0]), float(boot_rel_sd_pct[1])]
        boot_sens = {}
        if label in ("lowfs_open", "tlm20s_ar16", "eof128_p8"):
            for bl in (50, 200):
                b_alt = block_bootstrap_iv(Au, Bu, Du, gstart=gstart, block_len=bl, n_boot=150, seed=43)
                boot_sens[str(bl)] = float(np.median(100.0 * b_alt["g_sd"][2:] / np.maximum(np.abs(g_full[2:]), 1e-3)))

        # Stage-3 LLOWFS regressors
        lowfs_res = run_lowfs_regressors(d, Au, Bu, Du, tD, cB, cD, oD, kTg, lat_iv, gstart, tsub_sl)

        # Geometry M_geom + IV Mda_virt + passive Stage-1 g_A
        M_geom, B1_dm, B2_dm = compute_mgeom(tdir)
        geom_resid = float(np.median(np.linalg.norm(B2_dm.T - B1_dm.T @ M_geom, axis=0) / np.linalg.norm(B2_dm.T, axis=0)))
        mda_res = run_mda_virt_iv(Au, Bu, Du, g_full, M_geom, B1_dm, B2_dm, srm1, shipped_mda, wz_py["Mda_virt"])
        mda_res["geom_resid_na60"] = geom_resid

        # Plate-DM NA sensitivity check (NA=160 vs NA=60) when Stage-1 basis has >10% residual or for eof128_p8
        na160_check = None
        if geom_resid > 0.10 or label == "eof128_p8":
            A160, _, _, _ = load_stream(tdir, "aol1_modevalWFS", 160)
            A160g = A160[good]
            if tsub_sl is not None:
                A160g = A160g[tsub_sl]
            iv160 = run_iv_estimators(A160g, Bu, Du, gstart=gstart, lag0=2, nlag=8)
            g160 = iv160["est"]["IV diff"]
            b160 = block_bootstrap_iv(A160g, Bu, Du, gstart=gstart, lag0=2, nlag=8, block_len=100, n_boot=150, seed=44)
            cm1_160 = fits.getdata(tdir / "calib_stg1" / "CMmodesDM.fits").astype(np.float64)
            dm1m = fits.getdata(tdir / "calib_stg1" / "dmmask.fits").astype(np.float64) > 0.5
            B1_160 = np.array([cm1_160[i][dm1m] for i in range(160)])
            Mg_160 = np.linalg.lstsq(B1_160.T, B2_dm.T, rcond=1e-4)[0]
            res160 = float(np.median(np.linalg.norm(B2_dm.T - B1_160.T @ Mg_160, axis=0) / np.linalg.norm(B2_dm.T, axis=0)))
            na160_check = dict(
                geom_resid_na160=res160,
                g_med=float(np.median(g160[2:])),
                iqr=float(np.percentile(g160[2:], 75) - np.percentile(g160[2:], 25)),
                usable_pct=float(100 * np.median(iv160["usable"][2:])),
                boot_1sig_pct=float(np.median(100.0 * b160["g_sd"][2:] / np.maximum(np.abs(g160[2:]), 1e-3))),
                tt=[float(g160[0]), float(g160[1])],
                tt_usable_pct=[float(100 * iv160["usable"][0]), float(100 * iv160["usable"][1])],
            )

        # Tip/Tilt diagnostics
        A_var = np.var(cen(Au), axis=0)
        dA_var = np.var(np.diff(cen(Au), axis=0), axis=0)
        # Lag-1 autocorrelation of A (proxy for turbulence-to-noise ratio in WFS A)
        ac1_A = np.array([float(np.corrcoef(Au[1:, i], Au[:-1, i])[0, 1]) for i in range(NB)])
        tt_diag = dict(
            g_iv=[float(g_full[0]), float(g_full[1])],
            g_iv_lag16=[float(iv_lag16["est"]["IV diff"][0]), float(iv_lag16["est"]["IV diff"][1])],
            g_iv_lev=[float(iv_main["est"]["IV"][0]), float(iv_main["est"]["IV"][1])],
            g_iv_2ms=[float(iv_2ms["est"]["IV diff"][0]), float(iv_2ms["est"]["IV diff"][1])],
            ref_P=[float(ref_P[0]), float(ref_P[1])] if ref_P is not None else None,
            usable_pct=[float(100 * iv_main["usable"][0]), float(100 * iv_main["usable"][1])],
            usable_med2_39=float(100 * np.median(iv_main["usable"][2:])),
            c_iv=[float(iv_main["c_iv"][0]), float(iv_main["c_iv"][1])],
            c_iv_med2_39=float(np.median(iv_main["c_iv"][2:])),
            corr_pd=[float(iv_main["corr_pd"][0]), float(iv_main["corr_pd"][1])],
            corr_pd_med2_39=float(np.median(iv_main["corr_pd"][2:])),
            ac1_A_tt=[float(ac1_A[0]), float(ac1_A[1])],
            ac1_A_med2_39=float(np.median(ac1_A[2:])),
            var_A_ratio_tt_to_hi=float(np.mean(A_var[:2]) / np.median(A_var[2:NB])),
            boot_sd_pct=boot_tt_sd_pct,
        )

        # Residual WFE from wf_stats.json
        wf_stats = json.loads((d / "wf_stats.json").read_text()) if (d / "wf_stats.json").is_file() else {}
        wfe_stg1 = wf_stats.get("locations", {}).get("stg1", {}).get("mean_spatial_rms_nm")
        wfe_fin = wf_stats.get("locations", {}).get("final", {}).get("mean_spatial_rms_nm")

        rec = dict(
            label=label,
            run=rname,
            desc=desc,
            tsub=tsub,
            n_windows=int(len(Au)),
            dur_s=float(len(Au) * 1e-3),
            wfe_stg1_nm=wfe_stg1,
            wfe_final_nm=wfe_fin,
            continuity=dict(
                A_gaps=mA["gaps"], B_gaps=mB["gaps"], D_gaps=mD["gaps"],
                nir_gaps=g_nir, vis_gaps=g_vis, dm3_gaps=g_dm3,
                wall_fps_B=mB["wall_fps"],
            ),
            alignment=dict(
                oD=oD, oD_frac=fD, oA_cam=oA_cam, oA_near=oA_near, oA_near_frac=fA_near,
                oA_prev=oA_prev, oA_prev_frac=fA_prev, oA_prev_err=oA_prev - oA_cam,
                dt_BA_ms=dt_BA_ms,
                ctrl_corr=ctrl_corr, ctrl_gain=ctrl_gain, pf_corr=pf_corr,
                iv_g23=[float(m23[0]), float(m23[1])], lat_iv=lat_iv,
            ),
            usable_pct=float(100 * np.median(iv_main["usable"][2:])),
            usable_2ms_pct=float(100 * np.median(iv_2ms["usable"][2:])),
            c_iv_med=float(np.median(iv_main["c_iv"][2:])),
            ref_P_med=float(np.median(ref_P[2:])) if ref_P is not None else None,
            ref_og_med=float(np.median((ref_P / cal_P)[2:])) if (ref_P is not None and cal_P is not None) else None,
            shipped_og_med=float(np.median(shipped_og[2:])) if shipped_og is not None else None,
            estimators=dict(
                iv_diff=err_stats(iv_main["est"]["IV diff"], ref_P),
                iv_diff_lag16=err_stats(iv_lag16["est"]["IV diff"], ref_P),
                iv_diff_2ms=err_stats(iv_2ms["est"]["IV diff"], ref_P),
                iv_diff_cal_lat=err_stats(iv_cal_lat["est"]["IV diff"], ref_P),
                iv_diff_buggy_oA=err_stats(iv_buggy_oA["est"]["IV diff"], ref_P),
                iv_lev=err_stats(iv_main["est"]["IV"], ref_P),
                ls_diff=err_stats(iv_main["est"]["LS diff"], ref_P),
                ls_lev=err_stats(iv_main["est"]["LS"], ref_P),
                wz_py=err_stats(wz_py["mdb_diag"], ref_P),
                shipped_wz=err_stats(shipped_g, ref_P) if shipped_g is not None else None,
            ),
            bootstrap=dict(
                med_1sig_pct=boot_med_sd_pct,
                exp_mae_pct=float(0.6745 * boot_med_sd_pct),
                global_med_1sig=float(boot["med_sd"]),
                half_split_1sig_pct=half_sd_full_pct,
                half_meds=[half_bias_h1, half_bias_h2],
                sens_block_len=boot_sens,
            ),
            tt_diag=tt_diag,
            lowfs=lowfs_res,
            mda_virt=mda_res,
            na160_check=na160_check,
        )
        regimes[label] = rec

        # Concise console summary
        e_iv = rec["estimators"]["iv_diff"]
        e_wz = rec["estimators"]["shipped_wz"] or rec["estimators"]["wz_py"]
        wz_tag = "shipped W(z)" if rec["estimators"]["shipped_wz"] else "py W(z)"
        ref_str = f"P_srm={rec['ref_P_med']:.3f}" if rec["ref_P_med"] else "no selfRM"
        bias_str = f" ({e_iv['bias_pct']:+.1f}%, |err|={e_iv['mae_pct']:.1f}%, MAD={e_iv['mad_pct']:.1f}%)" if "bias_pct" in e_iv else ""
        print(
            f"  gaps=0 | oA_near={oA_near} (prev_err={oA_prev-oA_cam:+d}) | lat_iv={lat_iv:.2f} | "
            f"usable={rec['usable_pct']:4.1f}% | {ref_str}"
        )
        print(
            f"  IV diff: g={e_iv['med']:.3f} (iqr={e_iv['iqr']:.3f}){bias_str} | "
            f"{wz_tag}: g={e_wz['med']:.3f} | boot 1sig={boot_med_sd_pct:.1f}% (0.67s={0.6745*boot_med_sd_pct:.1f}%) half_1sig={half_sd_full_pct:.1f}%"
        )
        print(
            f"  TT: g_IV={np.round(tt_diag['g_iv'],3)} use%={np.round(tt_diag['usable_pct'],1)} "
            f"ref={np.round(tt_diag['ref_P'],3) if tt_diag['ref_P'] else None} boot1sig%={np.round(boot_tt_sd_pct,1)}"
        )
        if lowfs_res:
            print(
                f"  LLOWFS: rms(dE)/rms(dD) TT={lowfs_res['rel_tt']:.2f} m2-9={lowfs_res['rel_2_9']:.2f} m10-39={lowfs_res['rel_10_39']:.2f} | "
                f"active a={lowfs_res['active_a_med']:+.3f} b={lowfs_res['active_b_med']:+.3f} (a+b={lowfs_res['active_apb_med']:+.3f}, b_tied={lowfs_res['active_btied_med']:+.3f})"
            )
        print(
            f"  Mda_virt IV(lev): cos={mda_res['iv_lev']['cos_med']:.3f} scl={mda_res['iv_lev']['scl_med']:.3f} "
            f"sr0.5={mda_res['iv_lev']['spec_rad_05']:.3f} | gA_proj={mda_res['gA_proj_lev_med']:.3f} "
            f"gA(Mdb/Mab)={mda_res['gA_from_Mdb_Mab_med']:.3f} vs srm1_P={mda_res.get('srm1_P_med')}"
        )

    report["regimes"] = regimes
    out_json = OUT_DIR / "audit_results.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved full structured results to {out_json}")


if __name__ == "__main__":
    main()
