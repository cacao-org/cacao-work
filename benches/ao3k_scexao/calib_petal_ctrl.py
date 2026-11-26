#!/usr/bin/env python3
"""Calibrate Stage-1 passive petal-unwrap templates & DM1 Voronoi petal modes.

Generates:
  1. petal_dm_modes.fits : float32 FITS cube (4, nact_y, nact_x) -> milk (nact_x, nact_y, 4)
       Zero-mean Voronoi nearest-petal DM1 modes ordered [E, N, W, S], scaled so
       +1.0 applies +p_eq_um DM OPD (+p_eq_um/2 surface), which cancels a +1 lambda_J
       residual petal wrap since wf_stg1 = wf_raw - 2 * dm_cmd.
  2. petal_wfs_M.fits    : float32 FITS matrix (ncam*ncam, 7) -> milk (7, ncam*ncam)
       Linear matched filter matrix so `aol1_petalM @ vec(aol1_imWFS2)` yields:
         [0] ev_sn  : symmetry-clean Even(S - N)  (+1 for S=+-1w, -1 for N=+-1w)
         [1] ev_ew  : symmetry-clean Even(E - W)  (+1 for E=+-1w, -1 for W=+-1w)
         [2] ev_adj : symmetry-clean Even(SE - SW)(+1 for S+E / N+W, -1 for S+W / N+E)
         [3] sg_e   : edge-free chromatic Odd Sign for East  (+1 for E=+1w, -1 for E=-1w)
         [4] sg_n   : edge-free chromatic Odd Sign for North (+1 for N=+1w, -1 for N=-1w)
         [5] sg_w   : edge-free chromatic Odd Sign for West  (+1 for W=+1w, -1 for W=-1w)
         [6] sg_s   : edge-free chromatic Odd Sign for South (+1 for S=+1w, -1 for S=-1w)
  3. petal_ctrl_meta.json: calibration diagnostics, equilibrium p_eq_um, bias ratio,
       wfsref correlation, chrom_sep, and recommended use_sign mode.
"""

from __future__ import annotations

import argparse
import configparser
import glob
import json
import math
import time
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy import fft as spfft
from scipy.ndimage import distance_transform_edt, label

# Exact cacaosim_beam.c spectral grid constants
CACAOSIM_NSPEC = 32
CACAOSIM_SPEC_L0_UM = 0.40
CACAOSIM_SPEC_L1_UM = 2.40
CACAOSIM_SPEC_DL_UM = (CACAOSIM_SPEC_L1_UM - CACAOSIM_SPEC_L0_UM) / CACAOSIM_NSPEC


def parse_bench(bench_path: Path) -> dict[str, dict[str, str]]:
    """Parse TOML-like cacaosim .bench INI file into section -> key -> raw value."""
    cfg: dict[str, dict[str, str]] = {}
    sec = ""
    for raw in bench_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            sec = line[1:-1].strip()
            cfg.setdefault(sec, {})
            continue
        if "=" in line and sec:
            k, v = line.split("=", 1)
            cfg[sec][k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def bfloat(sec: dict[str, str], key: str, default: float) -> float:
    return float(sec[key]) if key in sec else float(default)


def bint(sec: dict[str, str], key: str, default: int) -> int:
    return int(round(float(sec[key]))) if key in sec else int(default)


def planck_photon_rel(lam_um: float, teff_k: float) -> float:
    hc_k = 14387.77
    t_eff = teff_k if teff_k > 500.0 else 5778.0
    x = hc_k / (lam_um * t_eff)
    x0 = hc_k / (0.55 * t_eff)
    if x > 80.0:
        return 0.0
    n_lam = 1.0 / ((lam_um**4) * math.expm1(x))
    n_v = 1.0 / ((0.55**4) * math.expm1(x0))
    return n_lam / n_v if n_v > 0.0 else 1.0


def smooth_step_lo(lam: float, cut: float, roll: float) -> float:
    w = roll if roll > 1e-4 else 0.02
    z = 4.0 * (lam - cut) / w
    if z > 40.0:
        return 0.0
    if z < -40.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(z))


def compute_wfs1_spectrum(bench: dict[str, dict[str, str]]) -> tuple[list[float], list[float], float, float]:
    """Replicate cacaosim_beam.c spectral propagation to [pyrwfs.wfs_nir]."""
    b = bench.get("bench", {})
    dm = bench.get("dm.ao3k", {})
    spl = bench.get("splitter.dichroic_stg1", {})
    wfs = bench.get("pyrwfs.wfs_nir", {})

    tel_diam = bfloat(b, "tel_diam_m", 7.95)
    cobs = bfloat(b, "cobs", 0.307)
    star_mag = bfloat(b, "star_mag", 6.0)
    star_teff = bfloat(b, "star_teff", 9600.0)
    tput_tel = bfloat(b, "tput_tel", 0.20)
    dm_tput = bfloat(dm, "tput", 0.98)

    area = 0.25 * math.pi * tel_diam * tel_diam * (1.0 - cobs * cobs)
    f0_v = 1.0e11 * (10.0 ** (-0.4 * star_mag))
    base_flx = f0_v * area * tput_tel * CACAOSIM_SPEC_DL_UM

    # 32-bin entrance photon spectrum -> DM1 throughput -> dichroic_stg1 reflection
    ph_s = np.zeros(CACAOSIM_NSPEC, dtype=np.float64)
    spl_mode = spl.get("mode", "dichroic_bp")
    lam_cut = bfloat(spl, "lambda_cut", 1.22)
    band_w = bfloat(spl, "band_width", 0.30)
    roll = bfloat(spl, "roll_um", 0.03)
    eff_r = bfloat(spl, "eff_refl", 0.95)
    eff_t = bfloat(spl, "eff_trans", 0.95)
    r_gray = bfloat(spl, "r_gray", 0.5)
    t_gray = bfloat(spl, "t_gray", 0.5)

    for idx in range(CACAOSIM_NSPEC):
        lam = CACAOSIM_SPEC_L0_UM + (idx + 0.5) * CACAOSIM_SPEC_DL_UM
        fl = base_flx * planck_photon_rel(lam, star_teff) * dm_tput
        if spl_mode == "gray":
            r, t = r_gray, t_gray
        elif spl_mode == "dichroic_lp":
            s = smooth_step_lo(lam, lam_cut, roll)
            r, t = eff_r * s, eff_t * (1.0 - s)
        elif spl_mode == "dichroic_sp":
            s = smooth_step_lo(lam, lam_cut, roll)
            r, t = eff_r * (1.0 - s), eff_t * s
        else:
            hw = 0.5 * (band_w if band_w > 0.01 else 0.20)
            s1 = 1.0 - smooth_step_lo(lam, lam_cut - hw, roll)
            s2 = smooth_step_lo(lam, lam_cut + hw, roll)
            bp = s1 * s2
            r, t = eff_r * bp, eff_t * (1.0 - bp)
        if r + t > 1.0:
            r /= r + t
        ph_s[idx] = fl * r

    # Exact piecewise-linear sub-band quadrature (cacaosim_spec_sample_band)
    lam0 = bfloat(wfs, "lambda_um", 1.22)
    bw = bfloat(wfs, "bw_frac", 0.20)
    nlam = max(1, bint(wfs, "nlambda", 2))
    qe = bfloat(wfs, "qe", 0.80)
    rate_hz = bfloat(wfs, "rate_hz", 1000.0)
    dt_s = 1.0 / max(rate_hz, 1.0)

    if bw <= 0.0:
        return [lam0] * nlam, [1.0 / nlam] * nlam, lam0, 0.0

    def integrate_interval(l_lo: float, l_hi: float) -> tuple[float, float]:
        if not (l_hi > l_lo):
            return 0.0, 0.0
        dl = CACAOSIM_SPEC_DL_UM
        inv_dl = 1.0 / dl
        sum_r = 0.0
        sum_w = 0.0
        for seg in range(CACAOSIM_NSPEC + 1):
            if seg == 0:
                x0 = CACAOSIM_SPEC_L0_UM
                x1 = x0 + 0.5 * dl
                d0 = d1 = ph_s[0] * inv_dl
            elif seg == CACAOSIM_NSPEC:
                x0 = CACAOSIM_SPEC_L1_UM - 0.5 * dl
                x1 = CACAOSIM_SPEC_L1_UM
                d0 = d1 = ph_s[CACAOSIM_NSPEC - 1] * inv_dl
            else:
                x0 = CACAOSIM_SPEC_L0_UM + (seg - 0.5) * dl
                x1 = x0 + dl
                d0 = ph_s[seg - 1] * inv_dl
                d1 = ph_s[seg] * inv_dl
            a = max(l_lo, x0)
            b_pt = min(l_hi, x1)
            if b_pt > a:
                slope = (d1 - d0) / (x1 - x0) if x1 > x0 else 0.0
                sa = d0 + slope * (a - x0)
                sb = d0 + slope * (b_pt - x0)
                h = b_pt - a
                sum_r += 0.5 * h * (sa + sb)
                sum_w += (h / 6.0) * ((2.0 * a + b_pt) * sa + (a + 2.0 * b_pt) * sb)
        return sum_r, sum_w

    lmin = max(0.05, lam0 * (1.0 - 0.5 * bw))
    lmax = lam0 * (1.0 + 0.5 * bw)
    sub_w = (lmax - lmin) / nlam
    sub_r = []
    sub_l = []
    tot_r = 0.0
    tot_wl = 0.0
    for c in range(nlam):
        c_lo = lmin + c * sub_w
        c_hi = lmax if (c + 1 == nlam) else (c_lo + sub_w)
        r_c, wl_c = integrate_interval(c_lo, c_hi)
        sub_r.append(r_c)
        sub_l.append(wl_c / r_c if r_c > 1e-30 else 0.5 * (c_lo + c_hi))
        tot_r += r_c
        tot_wl += wl_c

    if tot_r > 1e-30:
        weights = [r_c / tot_r for r_c in sub_r]
        eff_lam = tot_wl / tot_r
        flux_e = tot_r * dt_s * qe
    else:
        weights = [1.0 / nlam] * nlam
        eff_lam = lam0
        flux_e = 0.0
    return sub_l, weights, eff_lam, flux_e


def pyr_1d_edge(u: np.ndarray, alpha: float, roof2: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Exact replica of cacaosim_pyrwfs_engine.c::pyr_1d_edge."""
    au = np.abs(u)
    re = np.empty_like(u, dtype=np.float64)
    im = np.empty_like(u, dtype=np.float64)
    out_m = au >= 0.5
    if roof2 > 0.0:
        # Smooth roof edge approximation matching cacaosim_pyrwfs_engine.c
        phi = alpha * np.sqrt(u * u + roof2)
        re[:] = np.cos(phi)
        im[:] = -np.sin(phi)
        return re, im
    sinc_h = math.sin(0.5 * alpha) / (0.5 * alpha)
    re[out_m] = sinc_h * np.cos(alpha * au[out_m])
    im[out_m] = -sinc_h * np.sin(alpha * au[out_m])
    cu = np.cos(alpha * au[~out_m])
    re[~out_m] = (2.0 * cu * math.sin(0.5 * alpha)) / alpha
    im[~out_m] = -(2.0 * (1.0 - cu * math.cos(0.5 * alpha))) / alpha
    return re, im


def build_bin_matrix(nfft: int, ncam: int) -> np.ndarray:
    scale = float(nfft) / float(ncam)
    mat = np.zeros((ncam, nfft), dtype=np.float64)
    for c in range(ncam):
        f0 = c * scale
        f1 = (c + 1) * scale
        i0 = max(0, int(math.floor(f0)))
        i1 = min(nfft, int(math.ceil(f1)))
        for i in range(i0, i1):
            w = min(f1, float(i + 1)) - max(f0, float(i))
            if w > 0.0:
                mat[c, i] = w
    return mat


class PolyPyWFSModel:
    """Exact polychromatic (unmodulated or circularly modulated) PyWFS forward model."""

    def __init__(
        self,
        pup_amp: np.ndarray,
        ncam: int,
        lam0_um: float,
        chan_lam_um: list[float],
        chan_weight: list[float],
        pup_diam: float = 0.9375,
        pup_sep: float = 0.5,
        fstop_frac: float = 0.45,
        chrom_sep: float = 0.0,
        mod_rad_ld: float = 0.0,
        mod_npts: int = 1,
        roof_ld: float = 0.0,
    ) -> None:
        self.pup_amp = np.asarray(pup_amp, dtype=np.float64)
        self.nwf = int(self.pup_amp.shape[0])
        self.nfft = self.nwf * 2
        self.pad = (self.nfft - self.nwf) // 2
        self.ncam = int(ncam)
        self.lam0 = float(lam0_um)
        self.lams = np.asarray(chan_lam_um, dtype=np.float64)
        w_arr = np.asarray(chan_weight, dtype=np.float64)
        self.weights = w_arr / np.sum(w_arr)
        self.bin_m = build_bin_matrix(self.nfft, self.ncam)

        self.mod_rad_ld = float(mod_rad_ld)
        self.npts = int(mod_npts) if (self.mod_rad_ld > 0.0 and mod_npts > 1) else 1
        pix_ld = float(self.nfft) / (pup_diam * float(self.nwf))

        half = self.nfft // 2
        fstop0 = fstop_frac * float(self.nfft)
        coords = np.arange(self.nfft, dtype=np.int64)
        signed = np.where(coords < half, coords, coords - self.nfft).astype(np.float64)
        iv = signed[:, None]
        iu = signed[None, :]
        nyq_bad = (iu == -half) | (iv == -half)
        nlam = len(self.lams)

        # Build masks of shape (nlam, npts, nfft, nfft)
        masks = np.zeros((nlam, self.npts, self.nfft, self.nfft), dtype=np.complex128)
        for ci, lam_c in enumerate(self.lams):
            scale_c = self.lam0 / float(lam_c)
            alpha_c = math.pi * pup_sep * (1.0 + chrom_sep * ((float(lam_c) - self.lam0) / self.lam0))
            roof_c = roof_ld * pix_ld * scale_c if roof_ld > 0.0 else 0.0
            roof2 = roof_c * roof_c
            fstop_c = min(fstop0 * scale_c, 0.49 * float(self.nfft))
            aa = (nlam > 1) or (abs(scale_c - 1.0) > 1e-6)
            if not aa:
                w_stop = ((np.abs(iu) <= fstop_c) & (np.abs(iv) <= fstop_c)).astype(np.float64)
            else:
                wx = np.clip(fstop_c + 0.5 - np.abs(iu), 0.0, 1.0)
                wy = np.clip(fstop_c + 0.5 - np.abs(iv), 0.0, 1.0)
                w_stop = wx * wy
            w_stop[nyq_bad] = 0.0

            r_mod_c = (self.mod_rad_ld * pix_ld * scale_c) if self.npts > 1 else 0.0
            for k in range(self.npts):
                ang = (2.0 * math.pi * (k + 0.5)) / float(self.npts)
                uk = r_mod_c * math.cos(ang)
                vk = r_mod_c * math.sin(ang)
                rx, ix_c = pyr_1d_edge(signed + uk, alpha_c, roof2)
                ry, iy_c = pyr_1d_edge(signed + vk, alpha_c, roof2)
                tx = rx + 1j * ix_c
                ty = ry + 1j * iy_c
                masks[ci, k] = (
                    np.outer(ty, tx) * w_stop / (float(self.nfft * self.nfft) * math.sqrt(self.npts))
                )

        self.masks = masks
        self.lams_3d = self.lams[:, None, None]
        self.weights_3d = self.weights[:, None, None]

        raw0 = self._propagate_unnorm(np.zeros_like(self.pup_amp))
        self.norm0 = float(np.sum(raw0))
        self.ref_unit = raw0 / max(self.norm0, 1e-30)

    def _propagate_unnorm(self, opd_um: np.ndarray) -> np.ndarray:
        nlam = len(self.lams)
        pad, nwf = self.pad, self.nwf
        buf = np.zeros((nlam, self.nfft, self.nfft), dtype=np.complex128)
        phi = (2.0 * math.pi / self.lams_3d) * opd_um[None, :, :]
        buf[:, pad : pad + nwf, pad : pad + nwf] = self.pup_amp[None, :, :] * np.exp(1j * phi)
        foc = spfft.fft2(buf, axes=(-2, -1), workers=-1)  # (nlam, nfft, nfft)
        if self.npts == 1:
            det_f = spfft.ifft2(foc * self.masks[:, 0], axes=(-2, -1), workers=-1) * float(self.nfft * self.nfft)
            det = np.sum(self.weights_3d * (det_f.real * det_f.real + det_f.imag * det_f.imag), axis=0)
        else:
            det = np.zeros((self.nfft, self.nfft), dtype=np.float64)
            for ci in range(nlam):
                det_c = spfft.ifft2(foc[ci][None, :, :] * self.masks[ci], axes=(-2, -1), workers=-1) * float(
                    self.nfft * self.nfft
                )
                det += float(self.weights[ci]) * np.sum(det_c.real * det_c.real + det_c.imag * det_c.imag, axis=0)
        return self.bin_m @ det @ self.bin_m.T

    def forward_unit(self, opd_um: np.ndarray) -> np.ndarray:
        """Noise-free WFS image normalized to flat-WF unit total flux."""
        return self._propagate_unnorm(opd_um) / max(self.norm0, 1e-30)


def get_subaru_petals(pup_amp: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Return (strict_petals [pup>0.5], full_petals [pup>0 via nearest petal]) ordered [E, N, W, S]."""
    pmask = pup_amp > 0.5
    lbl, ncomp = label(pmask)
    if ncomp != 4:
        raise RuntimeError(f"Expected 4 disconnected petals in pupil, got {ncomp}")
    yy, xx = np.indices(pmask.shape)
    mid = 0.5 * (pmask.shape[0] - 1.0)
    comps = []
    for k in range(1, 5):
        mk = lbl == k
        ang = math.atan2(float(yy[mk].mean()) - mid, float(xx[mk].mean()) - mid)
        if ang < -math.pi / 4.0:
            ang += 2.0 * math.pi
        comps.append((ang, k, mk))
    comps.sort(key=lambda x: x[0])
    strict = [mk for _, _, mk in comps]
    dists = np.stack([distance_transform_edt(~mk) for mk in strict], axis=0)
    nearest = np.argmin(dists, axis=0)
    any_pup = pup_amp > 0.0
    full = [(nearest == p) & any_pup for p in range(4)]
    return strict, full


def build_dm1_stencil(
    nwf: int,
    nact_x: int,
    nact_y: int,
    dm_diam: float,
    if_coupling: float,
    refl_scale: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, float, float, float, float]:
    """Exact NumPy replica of cacaosim_dm_engine.c::dm_build_gather_stencil."""
    span = dm_diam * float(nwf)
    ctr = 0.5 * float(nwf - 1)
    px = span / float(nact_x - 1)
    py = span / float(nact_y - 1)
    x0 = ctr - 0.5 * float(nact_x - 1) * px
    y0 = ctr - 0.5 * float(nact_y - 1) * py

    coupl = min(max(if_coupling, 0.005), 0.45)
    alpha = -math.log(coupl)

    ix = np.arange(nwf, dtype=np.float64)[None, :]
    jy = np.arange(nwf, dtype=np.float64)[:, None]
    fx = (ix - x0) / px
    fy = (jy - y0) / py
    ax0 = np.floor(fx).astype(np.int32) - 1
    ay0 = np.floor(fy).astype(np.int32) - 1

    # Unclipped 4x4 lattice sum for exact interior partition of unity
    lat_sum = np.zeros((nwf, nwf), dtype=np.float64)
    for dy in range(4):
        ry = fy - (ay0 + dy)
        for dx in range(4):
            rx = fx - (ax0 + dx)
            lat_sum += np.exp(-alpha * (rx * rx + ry * ry))
    w_scale = np.where(lat_sum > 1e-8, refl_scale / lat_sum, refl_scale)

    st_idx = np.zeros((nwf, nwf, 16), dtype=np.int32)
    st_w = np.zeros((nwf, nwf, 16), dtype=np.float64)
    tap = 0
    for dy in range(4):
        ay = ay0 + dy
        for dx in range(4):
            ax = ax0 + dx
            valid = (ax >= 0) & (ax < nact_x) & (ay >= 0) & (ay < nact_y)
            rx = fx - ax
            ry = fy - ay
            w = np.where(valid, w_scale * np.exp(-alpha * (rx * rx + ry * ry)), 0.0)
            idx = np.where(valid, ay * nact_x + ax, 0)
            st_idx[:, :, tap] = idx
            st_w[:, :, tap] = w
            tap += 1
    return st_idx, st_w, x0, y0, px, py


def render_dm_opd(cmd_2d: np.ndarray, st_idx: np.ndarray, st_w: np.ndarray) -> np.ndarray:
    flat = cmd_2d.ravel()
    return np.sum(flat[st_idx] * st_w, axis=-1)


def build_voronoi_dm_petal_modes(
    strict_petals: list[np.ndarray],
    nact_x: int,
    nact_y: int,
    x0: float,
    y0: float,
    px: float,
    py: float,
    p_eq_um: float,
    refl_scale: float = 2.0,
) -> np.ndarray:
    """Build zero-mean Voronoi DM1 petal modes (4, nact_y, nact_x) in [um surface].

    Mode p has +0.75 * (p_eq_um / refl_scale) on petal p actuators and
    -0.25 * (p_eq_um / refl_scale) on the other 3 petals so global mean piston == 0
    and step(p - others) == +p_eq_um OPD (cancels +1 lambda_J residual wrap).
    """
    nwf = strict_petals[0].shape[0]
    dists = np.stack([distance_transform_edt(~mk) for mk in strict_petals], axis=0)
    nearest_wf = np.argmin(dists, axis=0)  # (nwf, nwf)

    ay_g, ax_g = np.indices((nact_y, nact_x), dtype=np.float64)
    wx = np.clip(np.rint(x0 + ax_g * px).astype(np.int32), 0, nwf - 1)
    wy = np.clip(np.rint(y0 + ay_g * py).astype(np.int32), 0, nwf - 1)
    act_petal = nearest_wf[wy, wx]  # (nact_y, nact_x) in {0, 1, 2, 3}

    step_surf = p_eq_um / refl_scale
    modes = np.zeros((4, nact_y, nact_x), dtype=np.float64)
    for p in range(4):
        modes[p] = np.where(act_petal == p, +0.75 * step_surf, -0.25 * step_surf)
    return modes


def fit_bias_over_flux(ref_unit: np.ndarray, wfsref: np.ndarray, msk: np.ndarray) -> tuple[float, float]:
    """Fit beta = bias_eff / flux_e from acquireWFSim wfsref.fits against model ref_unit.

    In acquireWFSim: wfsref = (beta + ref_unit) * msk / sum((beta + ref_unit) * msk).
    On active mask pixels (msk > 0.5), wfsref = c0 * 1 + c1 * ref_unit => beta = c0 / c1.
    """
    act = msk > 0.5
    y = wfsref[act].astype(np.float64)
    x = ref_unit[act].astype(np.float64)
    a_mat = np.column_stack([np.ones_like(x), x])
    coef, _, _, _ = np.linalg.lstsq(a_mat, y, rcond=None)
    c0, c1 = float(coef[0]), float(coef[1])
    beta = max(c0 / c1, 0.0) if c1 > 1e-12 else 0.0
    model_ref = (beta + ref_unit) * msk
    model_ref /= max(float(np.sum(model_ref)), 1e-30)
    corr = float(np.corrcoef(model_ref[act], y)[0, 1])
    return beta, corr


def find_eq_lock(
    wfs: PolyPyWFSModel,
    petal_mask: np.ndarray,
    lam_guess: float,
    msk: np.ndarray,
    beta: float,
) -> float:
    """Bisect exact 1-wave equilibrium lock OPD where linear WFS1 petal signal == 0."""
    def norm_img(opd_um: np.ndarray) -> np.ndarray:
        raw = (beta + wfs.forward_unit(opd_um)) * msk
        return raw / max(float(np.sum(raw)), 1e-30)

    ref_n = norm_img(np.zeros_like(wfs.pup_amp))
    dp = 0.02
    tpl = norm_img(np.where(petal_mask, +dp, 0.0)) - norm_img(np.where(petal_mask, -dp, 0.0))
    tpl /= max(float(np.linalg.norm(tpl)), 1e-30)

    p_lo, p_hi = lam_guess - 0.08, lam_guess + 0.08
    f_lo = float(np.sum((norm_img(np.where(petal_mask, p_lo, 0.0)) - ref_n) * tpl))
    for _ in range(22):
        mid = 0.5 * (p_lo + p_hi)
        f_m = float(np.sum((norm_img(np.where(petal_mask, mid, 0.0)) - ref_n) * tpl))
        if f_m * f_lo <= 0.0:
            p_hi = mid
        else:
            p_lo, f_lo = mid, f_m
    return 0.5 * (p_lo + p_hi)


def _orthonormal_basis(vecs: list[np.ndarray], rtol: float = 1e-10) -> np.ndarray:
    """Return rank-safe orthonormal column basis Q (npix, r) for a list of 1D/2D arrays."""
    blocks = []
    for v in vecs:
        a = np.asarray(v, dtype=np.float64)
        if a.ndim == 1:
            blocks.append(a[None, :])
        elif a.ndim == 2 and a.shape[0] > 0:
            blocks.append(a)
    if not blocks:
        return np.zeros((0, 0), dtype=np.float64)
    mat = np.vstack(blocks)  # (m, npix)
    u, s, _ = np.linalg.svd(mat.T, full_matrices=False)
    if s.size == 0 or s[0] <= 0.0:
        return np.zeros((mat.shape[1], 0), dtype=np.float64)
    return u[:, s > (rtol * s[0])]


def _extend_orthonormal_basis(q_base: np.ndarray, extra_vecs: list[np.ndarray], rtol: float = 1e-10) -> np.ndarray:
    """Extend an existing orthonormal basis q_base (npix, r0) with extra rows via rank-safe SVD."""
    blocks = []
    for v in extra_vecs:
        a = np.asarray(v, dtype=np.float64)
        if a.ndim == 1:
            blocks.append(a[None, :])
        elif a.ndim == 2 and a.shape[0] > 0:
            blocks.append(a)
    if not blocks:
        return q_base
    rem = np.vstack(blocks).T  # (npix, k)
    if q_base.shape[1] > 0:
        rem = rem - q_base @ (q_base.T @ rem)
    u, s, _ = np.linalg.svd(rem, full_matrices=False)
    if s.size == 0 or s[0] <= rtol:
        return q_base
    q_add = u[:, s > (rtol * s[0])]
    if q_base.shape[1] == 0:
        return q_add
    return np.hstack([q_base, q_add])


def build_filter_matrix(
    wfs: PolyPyWFSModel,
    strict_petals: list[np.ndarray],
    full_petals: list[np.ndarray],
    dm_modes: np.ndarray,
    st_idx: np.ndarray,
    st_w: np.ndarray,
    p_eq_um: float,
    msk: np.ndarray,
    wfsref: np.ndarray,
    beta: float,
    cm_wfs: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    """Build (7, npix) matched filter matrix [ev_sn, ev_ew, ev_adj, sg_e, sg_n, sg_w, sg_s].

    Rejects:
      - Centrosymmetric 4-spider turbulence/Zernike halo + mask constant + wfsref flux scale
      - Localized spider-corner / spider-edge DM windup modes (inner cobs, outer rim, mid-spider)
      - Continuous-facesheet DM1 spider-edge roll-off modes
      - Stage-1 linear AO mode subspace CMmodesWFS[:k_cm] (when provided)
    """
    pup_pos = wfs.pup_amp > 0.0
    nwf = wfs.pup_amp.shape[0]

    def sig(opd_um: np.ndarray) -> np.ndarray:
        raw = (beta + wfs.forward_unit(opd_um)) * msk
        return raw / max(float(np.sum(raw)), 1e-30)

    ref_n = sig(np.zeros_like(wfs.pup_amp))

    def dsig(opd_um: np.ndarray) -> np.ndarray:
        return (sig(opd_um) - ref_n) * msk

    # 1. Sharp-step +p_eq and -p_eq templates for all 4 single petals [E, N, W, S]
    ev_p = []
    od_p = []
    lin_p = []
    for p in range(4):
        opd_p = np.where(full_petals[p], +p_eq_um, 0.0)
        ip = dsig(+opd_p)
        im = dsig(-opd_p)
        ev_p.append(0.5 * (ip + im))
        od_p.append(0.5 * (ip - im))
        lp = dsig(np.where(full_petals[p], +0.02, 0.0)) - dsig(np.where(full_petals[p], -0.02, 0.0))
        lin_p.append(lp)

    # 2. Adjacent-pair even templates: (S+E) and (S+W)
    def ev_pair(pa: int, pb: int) -> np.ndarray:
        opd_ab = np.where(full_petals[pa] | full_petals[pb], +p_eq_um, 0.0)
        return 0.5 * (dsig(+opd_ab) + dsig(-opd_ab))

    ev_se = ev_pair(3, 0)
    ev_sw = ev_pair(3, 2)

    # 3. Continuous-facesheet DM1 spider-edge + localized spider-corner windup nuisance modes
    yy_w, xx_w = np.mgrid[:nwf, :nwf] - 0.5 * (nwf - 1.0)
    rr_w = np.hypot(xx_w, yy_w)
    pm = wfs.pup_amp > 0.5
    r_in = float(rr_w[pm].min())
    r_out = float(rr_w[pm].max())
    sp_gap = (~pm) & (rr_w > r_in + 4.0) & (rr_w < r_out - 4.0)
    dist_to_sp = distance_transform_edt(~sp_gap)
    near_sp = (dist_to_sp <= 10.0) & pup_pos

    # Localized spider-corner / spider-strip modes (inner cobs corner, outer rim corner, mid-spider)
    r_inner_cut = r_in + 0.30 * (r_out - r_in)
    r_outer_cut = r_out - 0.22 * (r_out - r_in)
    cn_ev_list = []
    cn_od_list = []
    for p in range(4):
        for rmask in (
            rr_w < r_inner_cut,
            rr_w > r_outer_cut,
            (rr_w >= r_inner_cut) & (rr_w <= r_outer_cut),
        ):
            patch = (full_petals[p] & near_sp & rmask).astype(np.float64) * np.exp(-dist_to_sp / 4.0)
            pmax = float(patch.max())
            if pmax > 0.0:
                patch /= pmax
                for amp in (0.15, 0.60):
                    ip = dsig(+amp * patch)
                    im = dsig(-amp * patch)
                    cn_ev_list.append((0.5 * (ip + im)).ravel())
                    cn_od_list.append((0.5 * (ip - im)).ravel())

    u_cne, s_cne, _ = np.linalg.svd(np.array(cn_ev_list).T, full_matrices=False)
    u_cno, s_cno, _ = np.linalg.svd(np.array(cn_od_list).T, full_matrices=False)
    k_cne_ev = min(16, int(np.sum(s_cne > 1e-8 * s_cne[0])))
    k_cno_ev = min(16, int(np.sum(s_cno > 1e-8 * s_cno[0])))
    k_cne_od = min(8, int(np.sum(s_cne > 1e-8 * s_cne[0])))
    k_cno_od = min(8, int(np.sum(s_cno > 1e-8 * s_cno[0])))

    dm_edge_od = []
    dm_edge_lin = []
    for p in range(4):
        opd_dm = render_dm_opd(dm_modes[p], st_idx, st_w)
        opd_sharp = np.where(full_petals[p], +0.75 * p_eq_um, -0.25 * p_eq_um)
        opd_edge = (opd_dm - opd_sharp) * pup_pos
        dm_edge_od.append(0.5 * (dsig(+opd_edge) - dsig(-opd_edge)))
        dm_edge_lin.append(0.5 * (dsig(+0.1 * opd_edge) - dsig(-0.1 * opd_edge)))

    # Optional Stage-1 linear AO mode subspace CMmodesWFS[:k_cm] (rank-safe SVD)
    k_cm_od = 0
    q_cm_od = np.zeros((msk.size, 0), dtype=np.float64)
    if cm_wfs is not None and cm_wfs.ndim == 3 and cm_wfs.shape[0] > 0:
        n_cm = int(cm_wfs.shape[0])
        k_cm_od = min(768, max(64, int(0.60 * n_cm)))
        k_cm_od = min(k_cm_od, n_cm)
        cm_sub = cm_wfs[:k_cm_od].reshape(k_cm_od, -1).astype(np.float64) * msk.ravel()[None, :]
        # Gram-matrix eigendecomposition is ~5x faster than full (25600 x 768) SVD!
        gram = cm_sub @ cm_sub.T  # (k_cm, k_cm)
        evals, evecs = np.linalg.eigh(gram)
        keep_g = evals > (1e-10 * max(float(evals.max()), 1e-30))
        q_cm_od = (cm_sub.T @ evecs[:, keep_g]) / np.sqrt(evals[keep_g])[None, :]

    # 4. Symmetry-clean 3-row Even matrix [ev_sn, ev_ew, ev_adj]
    t_sn = ev_p[3] - ev_p[1]
    t_ew = ev_p[0] - ev_p[2]
    t_adj = ev_se - ev_sw
    b_ev = np.stack([t_sn.ravel(), t_ew.ravel(), t_adj.ravel()], axis=0)  # (3, npix)

    qn_ev = _orthonormal_basis(
        [
            (ev_p[3] + ev_p[1]).ravel(),
            (ev_p[0] + ev_p[2]).ravel(),
            (ev_se + ev_sw).ravel(),
            np.array(lin_p).reshape(4, -1),
            np.array(od_p).reshape(4, -1),
            u_cne[:, :k_cne_ev].T,
            u_cno[:, :k_cno_ev].T,
            msk.ravel(),
            (wfsref * msk).ravel(),
        ]
    )
    b_ev_clean = b_ev - (b_ev @ qn_ev) @ qn_ev.T
    w_ev = np.linalg.pinv(b_ev_clean.T)  # (3, npix)
    w_ev[0] /= max(float(w_ev[0] @ ev_p[3].ravel()), 1e-30)
    w_ev[1] /= max(float(w_ev[1] @ ev_p[0].ravel()), 1e-30)
    w_ev[2] /= max(float(w_ev[2] @ ev_se.ravel()), 1e-30)

    # 5. Edge-free, AO-mode-orthogonal Odd Sign matrix (4 rows: E, N, W, S)
    qn_od = _extend_orthonormal_basis(
        q_cm_od,
        [
            np.array(ev_p).reshape(4, -1),
            ev_se.ravel(),
            ev_sw.ravel(),
            np.array(lin_p).reshape(4, -1),
            np.array(dm_edge_od).reshape(4, -1),
            np.array(dm_edge_lin).reshape(4, -1),
            u_cne[:, :k_cne_od].T,
            u_cno[:, :k_cno_od].T,
            msk.ravel(),
            (wfsref * msk).ravel(),
        ],
    )

    w_od = np.zeros((4, msk.size), dtype=np.float64)
    od_clean_norms = []
    for p in range(4):
        v = od_p[p].ravel()
        v_clean = v - qn_od @ (qn_od.T @ v)
        nrm = float(np.linalg.norm(v_clean))
        od_clean_norms.append(nrm)
        if nrm > 1e-12:
            w_od[p] = v_clean / (nrm * nrm)  # exact unit gain: dot(od_p[p], w_od[p]) == +1.0
        else:
            w_od[p] = 0.0

    # Stack full (7, npix) matrix and verify response on pure states & DM1-rendered petals!
    w_mat = np.vstack([w_ev, w_od])  # (7, npix)

    resp_sharp = {}
    resp_dm1 = {}
    pnames = ["E", "N", "W", "S"]
    for p, pn in enumerate(pnames):
        d_sh = dsig(np.where(full_petals[p], +p_eq_um, 0.0)).ravel()
        resp_sharp[f"{pn}+1w"] = [round(float(x), 4) for x in (w_mat @ d_sh)]
        d_dm = dsig(render_dm_opd(dm_modes[p], st_idx, st_w)).ravel()
        resp_dm1[f"{pn}+1w_dm"] = [round(float(x), 4) for x in (w_mat @ d_dm)]
    d_se = dsig(np.where(full_petals[3] | full_petals[0], +p_eq_um, 0.0)).ravel()
    resp_sharp["S+E+1w"] = [round(float(x), 4) for x in (w_mat @ d_se)]
    d_sw = dsig(np.where(full_petals[3] | full_petals[2], +p_eq_um, 0.0)).ravel()
    resp_sharp["S+W+1w"] = [round(float(x), 4) for x in (w_mat @ d_sw)]
    d_s2 = dsig(np.where(full_petals[3], +2.0 * p_eq_um, 0.0)).ravel()
    resp_sharp["S+2w"] = [round(float(x), 4) for x in (w_mat @ d_s2)]

    diag = {
        "od_clean_norms": [float(f"{x:.4e}") for x in od_clean_norms],
        "ev_row_norms": [float(f"{np.linalg.norm(w_ev[i]):.3e}") for i in range(3)],
        "od_row_norms": [float(f"{np.linalg.norm(w_od[i]):.3e}") for i in range(4)],
        "cm_wfs_proj_modes": k_cm_od,
        "nuis_ev_rank": int(qn_ev.shape[1]),
        "nuis_od_rank": int(qn_od.shape[1]),
        "response_sharp": resp_sharp,
        "response_dm1": resp_dm1,
    }
    return w_mat, diag


def self_test_telemetry(tlm_dir: Path, w_mat: np.ndarray, wfsref: np.ndarray, msk: np.ndarray, dark_adu: float) -> None:
    """Replay saved csim_wfs_nir telemetry exactly as acquireWFSim produces aol1_imWFS2."""
    files = sorted(glob.glob(str(tlm_dir / "csim_wfs_nir_[0-9][0-9]:*.fits")))
    if not files:
        print(f"[calib_petal_ctrl] No csim_wfs_nir_*.fits found in {tlm_dir}")
        return
    msk_f = msk.ravel()
    ref_f = (wfsref * msk).ravel()
    ref_f /= max(float(np.sum(ref_f)), 1e-30)

    chunks = []
    for fp in files:
        with fits.open(fp, memmap=True) as hdul:
            cube = np.asarray(hdul[0].data, dtype=np.float64)
            a = cube.reshape(cube.shape[0], -1)
            if dark_adu > 0.0:
                a = np.maximum(a - dark_adu, 0.0)
            a = a * msk_f[None, :]
            a /= np.maximum(a.sum(axis=1, keepdims=True), 1e-12)
            imwfs2 = a - ref_f[None, :]
            chunks.append(imwfs2 @ w_mat.T)
    ts = np.vstack(chunks)
    ss = ts[min(500, len(ts) // 5) :]
    names = ["ev_sn", "ev_ew", "ev_adj", "sg_e", "sg_n", "sg_w", "sg_s"]
    print(f"[calib_petal_ctrl] Live acquireWFSim replay (N={len(ts)}, dark_adu={dark_adu:.1f}):")
    for i, nm in enumerate(names):
        m = float(ss[:, i].mean())
        nb = len(ss) // 1000
        if nb >= 2:
            b1 = ss[: nb * 1000, i].reshape(nb, 1000).mean(axis=1)
            s1 = float(b1.std(ddof=1))
            snr1 = m / s1 if s1 > 1e-12 else 0.0
            print(f"  {nm:6s}: mean={m:+.3f} | 1s block std={s1:.3f} (SNR_1s={snr1:+.2f} sigma)")
        else:
            print(f"  {nm:6s}: mean={m:+.3f}")


def main() -> None:
    t0 = time.monotonic()
    ap = argparse.ArgumentParser(description="Calibrate Stage-1 passive petal unwrap controller")
    ap.add_argument("--bench", required=True, type=Path, help="Active cacaosim .bench file")
    ap.add_argument("--pup", required=True, type=Path, help="Pupil amplitude FITS (csim_pup.fits)")
    ap.add_argument("--wfsref", required=True, type=Path, help="Stage-1 wfsref.fits")
    ap.add_argument("--wfsmask", required=True, type=Path, help="Stage-1 wfsmask.fits")
    ap.add_argument("--cm-wfs", type=Path, default=None, help="Optional Stage-1 CMmodesWFS.fits for AO-mode orthogonalization")
    ap.add_argument("--outdir", required=True, type=Path, help="Output directory")
    ap.add_argument("--test-tlm", type=Path, default=None, help="Optional telemetry dir to replay")
    ap.add_argument("--test-dark-adu", type=float, default=0.0, help="Dark ADU subtracted in acquireWFSim during replay")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    bench = parse_bench(args.bench)
    b_sec = bench.get("bench", {})
    dm_sec = bench.get("dm.ao3k", {})
    wfs_sec = bench.get("pyrwfs.wfs_nir", {})

    pup_amp = np.asarray(fits.getdata(args.pup), dtype=np.float64)
    wfsref = np.asarray(fits.getdata(args.wfsref), dtype=np.float64)
    wfsmask = np.asarray(fits.getdata(args.wfsmask), dtype=np.float64)

    nwf = int(pup_amp.shape[0])
    ncam = bint(wfs_sec, "ncam", int(wfsref.shape[0]))
    lam0 = bfloat(wfs_sec, "lambda_um", 1.22)
    chrom_sep = bfloat(wfs_sec, "chrom_sep", 0.0)
    mod_rad = bfloat(wfs_sec, "mod_rad", 0.0)
    mod_npts = bint(wfs_sec, "mod_npts", 16 if mod_rad > 0.0 else 1)
    pup_sep = bfloat(wfs_sec, "pup_sep", 0.5)
    fstop_frac = bfloat(wfs_sec, "fstop_frac", 0.45)
    roof_ld = bfloat(wfs_sec, "roof_ld", 0.0)
    pup_diam = bfloat(b_sec, "pup_diam", 0.9375)

    nact_x = bint(dm_sec, "nact_x", 64)
    nact_y = bint(dm_sec, "nact_y", 64)
    dm_diam = bfloat(dm_sec, "dm_diam", 0.984375)
    if_coupling = bfloat(dm_sec, "if_coupling", 0.08)
    refl_scale = bfloat(dm_sec, "refl_scale", 2.0)

    chan_lams, chan_wts, eff_lam, flux_e = compute_wfs1_spectrum(bench)
    strict_petals, full_petals = get_subaru_petals(pup_amp)

    wfs = PolyPyWFSModel(
        pup_amp=pup_amp,
        ncam=ncam,
        lam0_um=lam0,
        chan_lam_um=chan_lams,
        chan_weight=chan_wts,
        pup_diam=pup_diam,
        pup_sep=pup_sep,
        fstop_frac=fstop_frac,
        chrom_sep=chrom_sep,
        mod_rad_ld=mod_rad,
        mod_npts=mod_npts,
        roof_ld=roof_ld,
    )

    beta, ref_corr = fit_bias_over_flux(wfs.ref_unit, wfsref, wfsmask)
    p_eq_um = find_eq_lock(wfs, full_petals[3], eff_lam, wfsmask, beta)

    st_idx, st_w, x0, y0, px, py = build_dm1_stencil(nwf, nact_x, nact_y, dm_diam, if_coupling, refl_scale)
    dm_modes = build_voronoi_dm_petal_modes(strict_petals, nact_x, nact_y, x0, y0, px, py, p_eq_um, refl_scale)

    cm_wfs = None
    if args.cm_wfs is not None and args.cm_wfs.exists():
        cm_wfs = np.asarray(fits.getdata(args.cm_wfs), dtype=np.float64)

    w_mat, diag = build_filter_matrix(
        wfs, strict_petals, full_petals, dm_modes, st_idx, st_w, p_eq_um, wfsmask, wfsref, beta, cm_wfs=cm_wfs
    )

    # Save FITS in exact milk axis convention:
    #   - petal_dm_modes.fits : NumPy (4, nact_y, nact_x) -> milk (nact_x, nact_y, 4)
    #   - petal_wfs_M.fits    : NumPy (ncam*ncam, 7)      -> milk (7, ncam*ncam), so M @ vec(im) = (7,)
    dm_path = args.outdir / "petal_dm_modes.fits"
    m_path = args.outdir / "petal_wfs_M.fits"
    meta_path = args.outdir / "petal_ctrl_meta.json"

    fits.writeto(dm_path, dm_modes.astype(np.float32), overwrite=True)
    fits.writeto(m_path, np.ascontiguousarray(w_mat.T, dtype=np.float32), overwrite=True)

    use_sign_rec = 1 if (abs(chrom_sep) >= 0.005 and min(diag["od_clean_norms"]) > 1e-7) else 0
    elapsed = time.monotonic() - t0
    meta = {
        "schema_version": 1,
        "bench": str(args.bench),
        "nwf": nwf,
        "ncam": ncam,
        "nact": [nact_x, nact_y],
        "lambda0_um": lam0,
        "eff_lambda_um": eff_lam,
        "nlambda": len(chan_lams),
        "chan_lam_um": [round(x, 6) for x in chan_lams],
        "chan_weight": [round(x, 6) for x in chan_wts],
        "chrom_sep": chrom_sep,
        "mod_rad_ld": mod_rad,
        "mod_npts": wfs.npts,
        "flux_e_est": round(flux_e, 1),
        "beta_bias_over_flux": beta,
        "est_bias_adu": round(beta * flux_e, 2),
        "wfsref_corr": round(ref_corr, 6),
        "p_eq_um": round(p_eq_um, 6),
        "dm_step_surface_um": round(p_eq_um / refl_scale, 6),
        "use_sign_recommended": use_sign_rec,
        "petal_order": ["E", "N", "W", "S"],
        "filter_rows": ["ev_sn", "ev_ew", "ev_adj", "sg_e", "sg_n", "sg_w", "sg_s"],
        "calib_time_s": round(elapsed, 3),
        "diagnostics": diag,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(
        f"[calib_petal_ctrl] Done in {elapsed:.2f}s | nlam={len(chan_lams)} chrom_sep={chrom_sep:+.4f} "
        f"mod={mod_rad:.2f} l/D | p_eq={p_eq_um*1000:.2f} nm | wfsref_corr={ref_corr:.6f} "
        f"(est_bias={beta*flux_e:.1f} ADU) | use_sign_rec={use_sign_rec}"
    )
    print(f"  DM1 +1w South response: {diag['response_dm1']['S+1w_dm']}")
    print(f"  Sharp +1w South resp  : {diag['response_sharp']['S+1w']}")
    print(f"  Sharp +2w South resp  : {diag['response_sharp']['S+2w']}")
    print(f"  Sharp +1w S+E resp    : {diag['response_sharp']['S+E+1w']}")

    if args.test_tlm is not None:
        self_test_telemetry(args.test_tlm, w_mat, wfsref, wfsmask, args.test_dark_adu)


if __name__ == "__main__":
    main()
