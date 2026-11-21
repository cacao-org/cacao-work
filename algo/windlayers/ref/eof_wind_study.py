#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Empirical study: EOF PF 3D cubes for wind estimation vs. windlayers -> physics-Gram EOF prior.

Evaluated on real cacaosim AO3k Stage-1 artifacts in _work/:
  - Converged Block-EOF(B=128, P=8) matrix: ao3k_scexao_predictive_eof128_p8/aol1_eofPFmat.fits
  - Clean 20 s 1 kHz PSOL telemetry:        ao3k_scexao_tlm20s_ar16/telemetry/aol1_modevalOL_*.fits
  - Exact 1965-mode DM basis:               wind_layers/ao3k_s1_dmmodes.fits

Part A (Wind from EOF PF cubes vs. Gram/covariance basis):
  1. Synthetic multi-layer nonlinearity test: NNLS on F(v) vs. Sigma_yx(v).
  2. Actual aol1_eofPFmat.fits: skew-symmetric modal optical flow + NNLS on {F(v)} (full & lag-0).
  3. Empirical short-lag Gram Sigma_yx (tau <= 9.4 ms) NNLS on {Sigma_yx(v)}.
  4. Extended-lag modal covariance R(tau) (tau <= 0.5 s) NNLS on {R(tau; v)} (modal windlayers).

Part B (Reverse synergy: windlayers -> physics-Gram Bayesian prior for mkEOFPF):
  Walk-forward out-of-sample (test = t=15..20 s) comparison across N_train = 0..14500:
    - Diag AR(16) (current mkEOFPF cold-start bootstrap)
    - Plain empirical Block-EOF(128, 8)
    - Linear sum of single-wind PF cubes: sum_l w_l F(v_l)
    - Pure physics-Gram EOF: (sum w_l S_yx(v_l)) (sum w_l S_xx(v_l) + S_nn)^-1
    - Bayesian physics-prior EOF: (S_yx^emp + gamma S_yx^phys)(S_xx^emp + gamma S_xx^phys)^-1
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy.optimize import nnls

REPO = Path(__file__).resolve().parents[3]
WORK = REPO / "_work"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wl_ref as wl  # noqa: E402


# Exact AO3k Stage-1 simulation ground truth in 7.95 m Subaru pupil coordinates
# (csim_atmturb used pupil_scale=0.068333 on 240 px -> 2.062883x turbul.prof in 7.95 m coords)
SCALE_V = 0.068333 / (7.95 / 240.0)
TURBUL_PROF = [
    (0.0, 5.32, 6.50, 1.47),
    (15.0, 1.47, 6.55, 1.57),
    (134.0, 1.08, 6.60, 1.67),
    (792.0, 2.11, 6.70, 1.77),
    (7785.0, 1.83, 22.00, 3.10),
    (11985.0, 1.48, 9.50, 3.20),
    (19486.0, 0.697, 5.60, 3.30),
]


def truth_layers_subaru() -> list[tuple[float, float, float, float]]:
    """Return list of (z_m, cn2_frac, vx, vy) in 7.95 m Subaru pupil coordinates."""
    tot = sum(r[1] for r in TURBUL_PROF)
    out = []
    for z, c, sp, d in TURBUL_PROF:
        v = sp * SCALE_V
        out.append((z, c / tot, -v * np.cos(d), -v * np.sin(d)))
    return out


class ModalWindModel:
    """Analytical Fourier-space modal lag-covariance engine for AO3k Stage-1 DM modes."""

    def __init__(
        self,
        modes_all: np.ndarray,
        dx: float = 7.95 / 60.0,
        npad: int = 128,
        l0_m: float = 25.0,
    ) -> None:
        self.dx = dx
        self.npad = npad
        n_m = modes_all.shape[0]
        m_flat = modes_all.reshape(n_m, -1).astype(np.float64)
        g_m = m_flat @ m_flat.T
        eig_max = float(np.linalg.eigvalsh(g_m)[-1])
        # Exact dual basis W such that a = dm @ W.T when dm = a @ M
        self.w_all = np.linalg.solve(g_m + 1e-6 * eig_max * np.eye(n_m), m_flat)

        f1 = np.fft.fftfreq(npad, dx)
        fx, fy = np.meshgrid(f1, f1)
        self.fx = fx.ravel()
        self.fy = fy.ravel()
        fr2 = self.fx**2 + self.fy**2
        psd = (fr2 + (1.0 / l0_m) ** 2) ** (-11.0 / 6.0)
        psd[0] = 0.0
        # Account for AO3k DM Gaussian influence roll-off (coupling=0.08) lightly
        self.psd_base = psd

    def block_wf(self, s0: int, s1: int) -> np.ndarray:
        """FFT of dual basis for modes [s0:s1] -> complex (B, npad*npad)."""
        wg = self.w_all[s0:s1].reshape(s1 - s0, 64, 64)
        return np.fft.fft2(wg, s=(self.npad, self.npad)).reshape(s1 - s0, -1)

    def lag_cov(
        self,
        wf: np.ndarray,
        tau_s: float,
        vx: float,
        vy: float,
        scale: np.ndarray | float = 1.0,
    ) -> np.ndarray:
        """Analytical R(tau) = E[a(t+tau) a(t)^T] for one frozen-flow layer at (vx, vy)."""
        ph = np.exp(2j * np.pi * (self.fx * vx + self.fy * vy) * tau_s)
        r = np.real((wf * (self.psd_base * ph)[None, :]) @ wf.conj().T)
        if np.ndim(scale) == 1:
            return (scale[:, None] * r) * scale[None, :]
        return float(scale) * r

    def derivative_ops(self, wf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Spatial derivative covariances D_x, D_y = d/dtau R(tau)|_{tau=0} for unit vx, vy."""
        c0 = np.real((wf * self.psd_base[None, :]) @ wf.conj().T)
        rx = np.real((wf * (2j * np.pi * self.fx * self.psd_base)[None, :]) @ wf.conj().T)
        ry = np.real((wf * (2j * np.pi * self.fy * self.psd_base)[None, :]) @ wf.conj().T)
        return c0, rx, ry

    def block_grams(
        self,
        wf: np.ndarray,
        vx: float,
        vy: float,
        p_ord: int,
        lat_fr: float,
        dt: float,
        scale: np.ndarray | float = 1.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Exact block-Toeplitz (Sigma_xx [PB x PB], Sigma_yx [B x PB]) for one wind layer.

        Matches mkEOFPF / solvers.py convention:
          x_t = [a(t), a(t-1), ..., a(t-P+1)]
          y_t = (1-a) a(t+li) + a a(t+li+1)
          Sigma_xx[k1, k2] = E[a(t-k1) a(t-k2)^T] = R((k2 - k1) dt)
          Sigma_yx[:, k]   = E[y_t a(t-k)^T]      = (1-a) R((li+k) dt) + a R((li+1+k) dt)
        """
        b = wf.shape[0]
        li = int(lat_fr)
        la = lat_fr - li
        # Compute R(m * dt) for m = 0..p_ord-1 and li..li+p_ord
        lags = set(range(p_ord)) | set(range(li, li + p_ord + 1))
        rc = {m: self.lag_cov(wf, m * dt, vx, vy, scale) for m in lags}
        sxx = np.zeros((p_ord * b, p_ord * b), dtype=np.float64)
        for k1 in range(p_ord):
            for k2 in range(p_ord):
                blk = rc[k2 - k1] if k2 >= k1 else rc[k1 - k2].T
                sxx[k1 * b : (k1 + 1) * b, k2 * b : (k2 + 1) * b] = blk
        syx = np.zeros((b, p_ord * b), dtype=np.float64)
        for k in range(p_ord):
            syx[:, k * b : (k + 1) * b] = (1.0 - la) * rc[li + k] + la * rc[li + 1 + k]
        return sxx, syx


def calibrate_block_scale_and_noise(
    model: ModalWindModel,
    wf: np.ndarray,
    u_cal: np.ndarray,
    layers: list[tuple[float, float, float]] | None = None,
    dt: float = 0.001,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate per-mode atmospheric scale and white noise variance from short calibration clip.

    When wind layers are provided, uses the physics lag-1 autocorrelation R_th(1): since white
    WFS noise drops out of R_emp(1), alpha_m = R_emp(1) / R_th(1) cleanly separates signal and
    noise even on low-order tip/tilt modes where parabolic extrapolation is noisy.
    """
    uc = u_cal - u_cal.mean(axis=0)
    c0_emp = np.mean(uc * uc, axis=0)
    r1 = np.mean(uc[1:] * uc[:-1], axis=0)
    c0_th = np.diag(model.lag_cov(wf, 0.0, 0.0, 0.0, 1.0))
    if layers:
        r1_unit = np.zeros_like(c0_th)
        for w, vx, vy in layers:
            r1_unit += w * np.diag(model.lag_cov(wf, dt, vx, vy, 1.0))
        alpha = np.clip(
            r1 / np.maximum(r1_unit, 1e-30),
            0.0,
            c0_emp / np.maximum(c0_th, 1e-30),
        )
        sig_est = alpha * c0_th
        noise_var = np.maximum(c0_emp - sig_est, 1e-3 * c0_emp)
        scale = np.sqrt(np.maximum(alpha, 1e-12))
        return scale, noise_var
    r2 = np.mean(uc[2:] * uc[:-2], axis=0)
    sig_est = np.where(
        r2 > 0.0, np.clip(r1 + (r1 - r2) / 3.0, 0.0, 0.995 * c0_emp), np.maximum(r1, 0.0)
    )
    sig_est = np.clip(sig_est, 0.05 * c0_emp, 0.998 * c0_emp)
    noise_var = np.maximum(c0_emp - sig_est, 1e-4 * c0_emp)
    scale = np.sqrt(sig_est / np.maximum(c0_th, 1e-30))
    return scale, noise_var


def solve_pf(sxx: np.ndarray, syx: np.ndarray, reg: float = 1e-4) -> np.ndarray:
    """Solve F = Sigma_yx (Sigma_xx + reg * tr/D * I)^-1 -> shape (B, PB)."""
    d = sxx.shape[0]
    tr = float(np.trace(sxx)) / float(d)
    a = sxx.copy()
    a.flat[:: d + 1] += reg * tr
    # Solve a @ W = syx.T -> F = W.T
    w = np.linalg.solve(a, syx.T)
    return w.T


def extract_wind_from_dm(tdir: Path) -> list[tuple[float, float, float]]:
    """Run windlayers (phase-space) on aol1_dmC to get data-driven layers (w, vx, vy)."""
    dm = np.concatenate(
        [fits.getdata(f) for f in sorted(tdir.glob("aol1_dmC_*.fits"))], axis=0
    ).astype(np.float64)
    dm_b = dm[:15000].reshape(7500, 2, 32, 2, 32, 2).mean(axis=(1, 3, 5))
    act = dm_b.std(axis=0)
    mask = (act > 0.2 * np.percentile(act, 90)).astype(np.float64)
    dx = 7.95 / 30.0
    lap, mk = wl.laplacian(dm_b, mask, dx)
    kap = wl.demean(lap, mk)
    spec, taper = wl.lagspec([kap], [mk], 250)
    vg, mkk, dkk = wl.velocity_map(
        spec[(0, 0)], taper[(0, 0)], dx=dx, dt=0.002, vmax=55.0, dv=0.5, fmin=0.15, fmax=1.6
    )
    peaks, _ = wl.find_peaks(mkk, dkk, vg, 8, 8.0, sign=1.0, minfrac=0.03)
    # Exclude static v ~ 0 peak
    mov = [(vx, vy) for vx, vy, _, _ in peaks if np.hypot(vx, vy) > 1.0]
    # Joint decomposition to get exact frac_k weights!
    pa, _ = wl.decompose(spec[(0, 0)], taper[(0, 0)], mov, dx, 0.002)
    f = np.fft.fftfreq(spec[(0, 0)].shape[1], dx)
    fr = np.hypot(f[None, :], f[:, None])
    sel = (fr >= 0.15) & (fr <= 1.6)
    pw = np.array([max(float(pa[i].real[sel].sum()), 0.0) for i in range(len(mov))])
    pw /= max(pw.sum(), 1e-30)
    return [(float(pw[i]), float(mov[i][0]), float(mov[i][1])) for i in range(len(mov))]


def main() -> None:
    t0 = time.time()
    modes_all = fits.getdata(WORK / "wind_layers/ao3k_s1_dmmodes.fits").astype(np.float64)
    pf_actual = fits.getdata(
        WORK / "ao3k_scexao_predictive_eof128_p8/aol1_eofPFmat.fits"
    ).astype(np.float64)
    tdir = WORK / "ao3k_scexao_tlm20s_ar16/telemetry"
    ol = np.concatenate(
        [fits.getdata(f)[:, 0, :] for f in sorted(tdir.glob("aol1_modevalOL_*.fits"))], axis=0
    ).astype(np.float64)

    truth = truth_layers_subaru()
    vbar_true = np.array([
        sum(w * vx for _, w, vx, _ in truth),
        sum(w * vy for _, w, _, vy in truth),
    ])
    print("=" * 80)
    print("AO3k Stage-1 Truth Layers (7.95 m Subaru pupil coords):")
    for z, w, vx, vy in truth:
        ang = np.degrees(np.arctan2(vy, vx)) % 360
        print(
            f"  z={z:6.0f} m  w={w:.3f}  v=({vx:+6.2f}, {vy:+6.2f})  "
            f"sp={np.hypot(vx, vy):5.2f}  dir={ang:5.1f} deg"
        )
    vbar_ang = np.degrees(np.arctan2(vbar_true[1], vbar_true[0])) % 360
    print(
        f"  Cn2-weighted mean wind: vbar = ({vbar_true[0]:+.2f}, {vbar_true[1]:+.2f}) m/s "
        f"(sp={np.hypot(*vbar_true):.2f}, dir={vbar_ang:.1f} deg)"
    )

    print("\nMeasuring wind layers from first 15 s of aol1_dmC via windlayers (no truth)...")
    wl_layers = extract_wind_from_dm(tdir)
    for w, vx, vy in wl_layers:
        ang = np.degrees(np.arctan2(vy, vx)) % 360
        print(
            f"  windlayers: w={w:.3f}  v=({vx:+6.2f}, {vy:+6.2f})  "
            f"sp={np.hypot(vx, vy):5.2f}  dir={ang:5.1f} deg"
        )
    vbar_wl = np.array([
        sum(w * vx for w, vx, _ in wl_layers),
        sum(w * vy for w, _, vy in wl_layers),
    ])
    print(
        f"  windlayers mean wind:   vbar = ({vbar_wl[0]:+.2f}, {vbar_wl[1]:+.2f}) m/s "
        f"(err vs truth: {np.linalg.norm(vbar_wl - vbar_true):.2f} m/s)"
    )

    model = ModalWindModel(modes_all)
    b_sz, p_ord, lat_fr, dt = 128, 8, 2.401, 0.001

    # =========================================================================
    # PART A: CAN EOF PF 3D CUBES BE DECOMPOSED INTO WIND BASIS CUBES?
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART A: WIND ESTIMATION FROM EOF PF 3D CUBES vs. GRAM / EXTENDED-LAG COVARIANCE")
    print("=" * 80)

    # A.1: Controlled multi-layer nonlinearity test on Blocks 0, 2, 6
    print(
        "\n[A.1] Multi-layer nonlinearity test "
        "(4-layer vs. linear span of {F(v)} & {Sigma_yx(v)}):"
    )
    # Test on the exact 4 representative layer velocities + a 2D velocity grid
    rep_vels = [(-0.02, -13.55), (45.35, -1.87), (19.56, 1.13), (11.41, 1.82)]
    rep_w_true = np.array([
        sum(w for z, w, _, _ in truth if z < 1000),
        truth[4][1],
        truth[5][1],
        truth[6][1],
    ])
    for bk in (0, 2, 6):
        s0, s1 = bk * b_sz, (bk + 1) * b_sz
        wf = model.block_wf(s0, s1)
        scale, noise_v = calibrate_block_scale_and_noise(model, wf, ol[:15000, s0:s1])
        snn = np.diag(np.tile(noise_v, p_ord))
        # True 4-layer combined Gram & PF
        sxx_m = snn.copy()
        syx_m = np.zeros((b_sz, p_ord * b_sz))
        f_basis = []
        f0_basis = []
        syx_basis = []
        for (vx, vy), wt in zip(rep_vels, rep_w_true):
            gx, gy = model.block_grams(wf, vx, vy, p_ord, lat_fr, dt, scale)
            sxx_m += wt * gx
            syx_m += wt * gy
            f_single = solve_pf(gx + snn, gy, reg=1e-4)
            f_basis.append(f_single.ravel())
            f0_basis.append(f_single[:, :b_sz].ravel())
            syx_basis.append(gy.ravel())
        f_multi = solve_pf(sxx_m, syx_m, reg=1e-4)
        # NNLS decomposition onto the 4 EXACT velocity templates!
        a_f = np.column_stack(f_basis)
        a_f0 = np.column_stack(f0_basis)
        a_g = np.column_stack(syx_basis)
        cf, res_f = nnls(a_f, f_multi.ravel())
        cf0, res_f0 = nnls(a_f0, f_multi[:, :b_sz].ravel())
        cg, res_g = nnls(a_g, syx_m.ravel())
        rel_f = res_f / np.linalg.norm(f_multi)
        rel_f0 = res_f0 / np.linalg.norm(f_multi[:, :b_sz])
        rel_g = res_g / np.linalg.norm(syx_m)
        # Check condition numbers of the 4-vector basis!
        cond_f = np.linalg.cond(a_f)
        cond_g = np.linalg.cond(a_g)
        print(f"  Block {bk:2d} ({s0:4d}:{s1:4d}) | truth w={np.round(rep_w_true, 3)}")
        print(
            f"    PF full (P=8)  NNLS w={np.round(cf, 3)} (sum={cf.sum():.3f})  "
            f"fit_err={rel_f * 100:5.2f}%  cond={cond_f:6.1f}"
        )
        print(
            f"    PF lag-0 only  NNLS w={np.round(cf0, 3)} (sum={cf0.sum():.3f})  "
            f"fit_err={rel_f0 * 100:5.2f}%"
        )
        print(
            f"    Gram Sigma_yx  NNLS w={np.round(cg, 3)} (sum={cg.sum():.3f})  "
            f"fit_err={rel_g * 100:5.2f}%  cond={cond_g:6.1f}"
        )

    # A.2: Test on ACTUAL converged aol1_eofPFmat.fits and empirical Gram from 20 s telemetry
    print("\n[A.2] ACTUAL aol1_eofPFmat.fits: skew-sym optical flow + 2D grid NNLS:")
    # 2D velocity basis grid (-15..55 m/s in vx, -25..20 m/s in vy, step 5 m/s)
    gvx = np.arange(-15.0, 56.0, 5.0)
    gvy = np.arange(-25.0, 21.0, 5.0)
    grid_v = [(float(x), float(y)) for y in gvy for x in gvx]
    print(
        f"  2D basis grid: {len(grid_v)} velocities "
        f"({gvx[0]:.0f}..{gvx[-1]:.0f} x {gvy[0]:.0f}..{gvy[-1]:.0f} m/s, step 5 m/s)"
    )

    summary_a = {}
    for bk in (0, 2, 6, 10):
        s0, s1 = bk * b_sz, (bk + 1) * b_sz
        wf = model.block_wf(s0, s1)
        u_blk = ol[:15000, s0:s1]
        u_blk = u_blk - u_blk.mean(axis=0)
        scale, noise_v = calibrate_block_scale_and_noise(model, wf, u_blk)
        snn = np.diag(np.tile(noise_v, p_ord))

        # Extract actual converged PF block [B x (P*B)] from aol1_eofPFmat.fits
        f_act = pf_actual[s0:s1, : p_ord * b_sz]
        # Empirical short-lag Gram Sigma_yx from tlm20s (same N=15000)
        li, la = int(lat_fr), lat_fr - int(lat_fr)
        itr = np.arange(p_ord - 1, len(u_blk) - li - 2)
        x_tr = np.hstack([u_blk[itr - k] for k in range(p_ord)])
        y_tr = (1.0 - la) * u_blk[itr + li] + la * u_blk[itr + li + 1]
        syx_emp = (y_tr.T @ x_tr) / len(itr)

        # (1) Skew-symmetric modal optical flow on lag-0 of actual PF and syx_emp:
        # For small d, R(d) ~ C0 + d*(vx*Rx + vy*Ry) -> antisym(R(d)) ~ d*(vx*Rx + vy*Ry)
        # For F_lag0 ~ I + d*(vx*Rx + vy*Ry) C0^-1 -> post-multiply by C0_emp
        c0_emp = (u_blk.T @ u_blk) / len(u_blk)
        _, rx_raw, ry_raw = model.derivative_ops(wf)
        rx_s = (scale[:, None] * rx_raw) * scale[None, :]
        ry_s = (scale[:, None] * ry_raw) * scale[None, :]
        # Antisymmetric parts
        a_dx = 0.5 * (rx_s - rx_s.T).ravel()
        a_dy = 0.5 * (ry_s - ry_s.T).ravel()
        dmat = np.column_stack([a_dx, a_dy])
        # From actual PF lag-0 * C0_emp:
        fc0 = f_act[:, :b_sz] @ c0_emp
        a_pf0 = 0.5 * (fc0 - fc0.T).ravel() / (lat_fr * dt)
        v_pf_skew, *_ = np.linalg.lstsq(dmat, a_pf0, rcond=None)
        # From empirical Sigma_yx lag-0 directly:
        a_syx0 = 0.5 * (syx_emp[:, :b_sz] - syx_emp[:, :b_sz].T).ravel() / (lat_fr * dt)
        v_syx_skew, *_ = np.linalg.lstsq(dmat, a_syx0, rcond=None)

        # (2) 2D grid NNLS decomposition on actual PF cube and empirical Sigma_yx
        a_pf_list, a_syx_list = [], []
        for vx, vy in grid_v:
            gx, gy = model.block_grams(wf, vx, vy, p_ord, lat_fr, dt, scale)
            fs = solve_pf(gx + snn, gy, reg=1e-4)
            a_pf_list.append(fs.ravel())
            a_syx_list.append(gy.ravel())
        mat_pf = np.column_stack(a_pf_list)
        mat_syx = np.column_stack(a_syx_list)
        w_pf, r_pf = nnls(mat_pf, f_act.ravel())
        w_syx, r_syx = nnls(mat_syx, syx_emp.ravel())

        def top_and_mean(w_vec):
            s = max(w_vec.sum(), 1e-30)
            wn = w_vec / s
            vm = np.array([
                sum(wn[i] * grid_v[i][0] for i in range(len(grid_v))),
                sum(wn[i] * grid_v[i][1] for i in range(len(grid_v))),
            ])
            idx = np.argsort(wn)[::-1][:4]
            top = [(grid_v[i], float(wn[i])) for i in idx if wn[i] > 0.03]
            return vm, s, top

        vm_pf, sum_pf, top_pf = top_and_mean(w_pf)
        vm_syx, sum_syx, top_syx = top_and_mean(w_syx)
        err_pf_fit = r_pf / max(np.linalg.norm(f_act), 1e-30)
        err_syx_fit = r_syx / max(np.linalg.norm(syx_emp), 1e-30)
        tpf_s = [(f"({v[0]:.0f},{v[1]:.0f})", round(w, 2)) for v, w in top_pf]
        tsy_s = [(f"({v[0]:.0f},{v[1]:.0f})", round(w, 2)) for v, w in top_syx]
        print(
            f"\n  Block {bk:2d} ({s0:4d}:{s1:4d}):  "
            f"[Truth vbar = ({vbar_true[0]:+5.1f},{vbar_true[1]:+5.1f})]"
        )
        print(
            f"    Skew-sym optical flow (PF*C0)  : v=({v_pf_skew[0]:+6.2f},{v_pf_skew[1]:+6.2f}) "
            f"err={np.linalg.norm(v_pf_skew - vbar_true):5.2f} m/s"
        )
        print(
            f"    Skew-sym optical flow (Sig_yx) : v=({v_syx_skew[0]:+6.2f},{v_syx_skew[1]:+6.2f}) "
            f"err={np.linalg.norm(v_syx_skew - vbar_true):5.2f} m/s"
        )
        print(
            f"    2D NNLS on ACTUAL PF cube      : vbar=({vm_pf[0]:+6.2f},{vm_pf[1]:+6.2f}) "
            f"err={np.linalg.norm(vm_pf - vbar_true):5.2f} m/s | sum={sum_pf:.2f} "
            f"misfit={err_pf_fit * 100:4.1f}% | top={tpf_s}"
        )
        print(
            f"    2D NNLS on emp Sig_yx (9.4ms)  : vbar=({vm_syx[0]:+6.2f},{vm_syx[1]:+6.2f}) "
            f"err={np.linalg.norm(vm_syx - vbar_true):5.2f} m/s | sum={sum_syx:.2f} "
            f"misfit={err_syx_fit * 100:4.1f}% | top={tsy_s}"
        )
        summary_a[f"blk{bk}"] = dict(
            v_pf_skew=v_pf_skew.tolist(),
            v_syx_skew=v_syx_skew.tolist(),
            vm_pf=vm_pf.tolist(),
            vm_syx=vm_syx.tolist(),
            err_pf_fit=float(err_pf_fit),
            err_syx_fit=float(err_syx_fit),
            top_pf=[(list(v), w) for v, w in top_pf],
            top_syx=[(list(v), w) for v, w in top_syx],
        )

    # A.3: Extended-lag modal covariance R(tau) (10..300 ms) NNLS on Block 2 (256:384)
    print("\n[A.3] Extended-lag modal covariance R(tau) (10..300 ms) NNLS on Block 2 (256:384):")
    s0, s1 = 256, 384
    wf = model.block_wf(s0, s1)
    u_blk = ol[:15000, s0:s1]
    u_blk = u_blk - u_blk.mean(axis=0)
    scale, _ = calibrate_block_scale_and_noise(model, wf, u_blk)
    ext_lags_ms = [10, 20, 40, 60, 80, 100, 140, 180, 240, 300]
    y_ext = np.concatenate([
        ((u_blk[L:].T @ u_blk[:-L]) / (len(u_blk) - L)).ravel() for L in ext_lags_ms
    ])
    mat_ext = np.column_stack([
        np.concatenate(
            [model.lag_cov(wf, L * 1e-3, vx, vy, scale).ravel() for L in ext_lags_ms]
        )
        for vx, vy in grid_v
    ])
    w_ext, r_ext = nnls(mat_ext, y_ext)
    wn_ext = w_ext / max(w_ext.sum(), 1e-30)
    # Cluster adjacent grid cells (within 7.5 m/s) to read resolved layers
    rem = list(np.argsort(wn_ext)[::-1])
    clusters = []
    used = set()
    for i in rem:
        if i in used or wn_ext[i] < 0.015:
            continue
        vx0, vy0 = grid_v[i]
        grp = [
            j
            for j in range(len(grid_v))
            if j not in used
            and np.hypot(grid_v[j][0] - vx0, grid_v[j][1] - vy0) <= 7.5
            and wn_ext[j] > 0.005
        ]
        for j in grp:
            used.add(j)
        wt = sum(wn_ext[j] for j in grp)
        cx = sum(wn_ext[j] * grid_v[j][0] for j in grp) / wt
        cy = sum(wn_ext[j] * grid_v[j][1] for j in grp) / wt
        clusters.append((wt, cx, cy))
    print(
        f"  Extended-lag R(tau) misfit={r_ext / np.linalg.norm(y_ext) * 100:.1f}%, "
        f"clusters (truth: GL 0.71@(0,-13.6), L1 0.13@(45.4,-1.9), L2 0.11@(19.6,1.1)):"
    )
    for wt, cx, cy in sorted(clusters, reverse=True)[:6]:
        ang = np.degrees(np.arctan2(cy, cx)) % 360
        print(
            f"    w={wt:.3f}  v=({cx:+6.2f}, {cy:+6.2f})  "
            f"sp={np.hypot(cx, cy):5.2f}  dir={ang:5.1f} deg"
        )

    # =========================================================================
    # PART B: REVERSE SYNERGY — WINDLAYERS -> PHYSICS-GRAM BAYESIAN PRIOR EOF
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART B: WALK-FORWARD BENCHMARK — WINDLAYERS -> PHYSICS-GRAM PRIOR FOR mkEOFPF")
    print("        (Real 20 s AO3k Stage-1 PSOL telemetry, strictly out-of-sample t = 15..20 s)")
    print("=" * 80)

    li, la = int(lat_fr), lat_fr - int(lat_fr)
    ite = np.arange(15000, len(ol) - li - 2)
    ntrains = [0, 256, 512, 1024, 2048, 4096, 8192, 14500]
    n_prior = 1024.0  # effective sample weight of physics Gram prior (~1 s)

    def eval_pred(u: np.ndarray, f_mat: np.ndarray, idx_te: np.ndarray) -> float:
        x_te = np.hstack([u[idx_te - k] for k in range(p_ord)])
        y_te = (1.0 - la) * u[idx_te + li] + la * u[idx_te + li + 1]
        zoh = np.sum((y_te - u[idx_te]) ** 2)
        prd = np.sum((y_te - x_te @ f_mat.T) ** 2)
        return (1.0 - prd / max(zoh, 1e-30)) * 100.0

    def diag_ar16(u: np.ndarray, ntr: int) -> float:
        if ntr < 64:
            return 0.0
        itr = np.arange(15, ntr - li - 1)
        y_tr = (1.0 - la) * u[itr + li] + la * u[itr + li + 1]
        y_te = (1.0 - la) * u[ite + li] + la * u[ite + li + 1]
        zoh = np.sum((y_te - u[ite]) ** 2)
        prd = 0.0
        eye = np.eye(16)
        for m in range(u.shape[1]):
            ts = u[:, m]
            x_tr = np.column_stack([ts[itr - k] for k in range(16)])
            g = x_tr.T @ x_tr
            rhs = x_tr.T @ y_tr[:, m]
            tr = float(np.trace(g)) / 16.0
            if tr <= 1e-26:
                prd += float(np.sum((y_te[:, m] - ts[ite]) ** 2))
                continue
            lam = 1e-4 * tr
            w = np.linalg.solve(g + lam * eye, rhs)
            for _ in range(12):
                if float(np.dot(w, w)) <= 1.35 and abs(float(np.sum(w))) <= 1.01:
                    break
                lam *= 3.0
                w = np.linalg.solve(g + lam * eye, rhs)
            dc = float(np.sum(w))
            if abs(dc) > 0.985:
                w *= 0.985 / abs(dc)
            x_te = np.column_stack([ts[ite - k] for k in range(16)])
            prd += float(np.sum((y_te[:, m] - x_te @ w) ** 2))
        return (1.0 - prd / max(zoh, 1e-30)) * 100.0

    results_b = {}
    for bk in (0, 1, 2, 4, 8):
        s0, s1 = bk * b_sz, (bk + 1) * b_sz
        u = ol[:, s0:s1]
        wf = model.block_wf(s0, s1)
        # Unit-scale physics Gram from windlayers measurements (NO ground truth!)
        sxx_unit = np.zeros((p_ord * b_sz, p_ord * b_sz))
        syx_unit = np.zeros((b_sz, p_ord * b_sz))
        gx_list, gy_list = [], []
        for w, vx, vy in wl_layers:
            gx, gy = model.block_grams(wf, vx, vy, p_ord, lat_fr, dt, 1.0)
            sxx_unit += w * gx
            syx_unit += w * gy
            gx_list.append((w, gx))
            gy_list.append((w, gy))

        # Calibrate 0-frame physics EOF from a 1 s clip (1024 frames) for scale & noise only
        sc_1k, nv_1k = calibrate_block_scale_and_noise(model, wf, u[:1024], wl_layers, dt)
        r_rep = np.tile(sc_1k, p_ord)
        snn_1k = np.diag(np.tile(nv_1k, p_ord))
        sxx_p0 = sxx_unit * np.outer(r_rep, r_rep) + snn_1k
        syx_p0 = syx_unit * np.outer(sc_1k, r_rep)
        f_phys = solve_pf(sxx_p0, syx_p0, reg=1e-4)
        f_sumpf = np.zeros((b_sz, p_ord * b_sz))
        for (w, gx), (_, gy) in zip(gx_list, gy_list):
            gxs = gx * np.outer(r_rep, r_rep) + snn_1k
            gys = gy * np.outer(sc_1k, r_rep)
            f_sumpf += w * solve_pf(gxs, gys, reg=1e-4)
        vr_phys = eval_pred(u, f_phys, ite)
        vr_sumpf = eval_pred(u, f_sumpf, ite)

        print(
            f"\n--- Stage-1 Block {bk} (modes {s0}:{s1}) | "
            f"Physics-Gram EOF = {vr_phys:+.2f}% | Linear Sum-of-PFs = {vr_sumpf:+.2f}% ---"
        )
        print(
            f"  {'N_train':>7s} | {'Diag AR(16)':>11s} | {'Emp EOF':>10s} | "
            f"{'Sum-of-PFs':>10s} | {'Phys EOF':>10s} | {'Bayes Prior':>11s} | {'vs Emp':>9s}"
        )
        rows_b = []
        for ntr in ntrains:
            vr_ar = diag_ar16(u, ntr)
            if ntr == 0:
                vr_emp = float("nan")
                vr_bayes = vr_phys
            else:
                itr = np.arange(p_ord - 1, ntr - li - 1)
                x_tr = np.hstack([u[itr - k] for k in range(p_ord)])
                y_tr = (1.0 - la) * u[itr + li] + la * u[itr + li + 1]
                n_eff = float(len(itr))
                sxx_e = (x_tr.T @ x_tr) / n_eff
                syx_e = (y_tr.T @ x_tr) / n_eff
                f_emp = solve_pf(sxx_e, syx_e, reg=1e-4)
                vr_emp = eval_pred(u, f_emp, ite)
                sc_n, nv_n = calibrate_block_scale_and_noise(model, wf, u[:ntr], wl_layers, dt)
                rn = np.tile(sc_n, p_ord)
                sxx_p = sxx_unit * np.outer(rn, rn) + np.diag(np.tile(nv_n, p_ord))
                syx_p = syx_unit * np.outer(sc_n, rn)
                sxx_b = (n_eff * sxx_e + n_prior * sxx_p) / (n_eff + n_prior)
                syx_b = (n_eff * syx_e + n_prior * syx_p) / (n_eff + n_prior)
                f_bayes = solve_pf(sxx_b, syx_b, reg=1e-4)
                vr_bayes = eval_pred(u, f_bayes, ite)
            emp_s = f"{vr_emp:+9.2f}%" if np.isfinite(vr_emp) else "       N/A"
            gain_s = f"{vr_bayes - vr_emp:+8.2f}pp" if np.isfinite(vr_emp) else "       --"
            print(
                f"  {ntr:7d} | {vr_ar:+10.2f}% | {emp_s} | "
                f"{vr_sumpf:+9.2f}% | {vr_phys:+9.2f}% | {vr_bayes:+10.2f}% | {gain_s}"
            )
            rows_b.append(dict(
                ntr=ntr, ar16=vr_ar, emp=None if not np.isfinite(vr_emp) else vr_emp,
                sumpf=vr_sumpf, phys=vr_phys, bayes=vr_bayes,
            ))
        results_b[f"blk{bk}"] = rows_b

    out_json = WORK / "wind_layers/eof_wind_study.json"
    out_json.write_text(json.dumps(dict(part_a=summary_a, part_b=results_b), indent=2))
    print(f"\nSaved {out_json} (total runtime {time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
