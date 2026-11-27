# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Publication-grade figures, coronagraphic PSF analysis, and side-by-side MP4 video
for the live GPU ALPAO 64x64 plate DM 3D RM -> optimal pre-shaper demonstration.

NOTE: Every matplotlib `.imshow(...)` call explicitly passes `origin="lower"` to satisfy
the repository matrix-orientation policy (`test_05_ao_web_report.py`).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from astropy.io import fits
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

N_ACT = 64
N_WF = 256
N_WFS = 160
FS_HZ = 8000.0
DT_SEC = 1.0 / FS_HZ
DT_MS = DT_SEC * 1.0e3
N_STEP = 200
Q0_STEP = 16
N_AG = 320
T_ON_AG = 16
T_OFF_AG = 208
T_MOD0_AG = 32   # 4.0 ms -> [32:208] = 176 ticks = 11 exact 500 Hz cycles
T_RD0_AG = 220   # t_off + 12 ticks (1.5 ms after turn-off)
DELAY_TICKS = 8  # 1.0 ms hardware latency at 8 kHz


def _find_ffmpeg() -> str:
    for cand in (
        os.environ.get("FFMPEG_BIN", ""),
        shutil.which("ffmpeg") or "",
        os.path.expanduser("~/.local/bin/ffmpeg"),
    ):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    import imageio_ffmpeg  # type: ignore[import-not-found]

    return str(imageio_ffmpeg.get_ffmpeg_exe())


def _load_ttf(bold: bool = True, mono: bool = False, size: int = 16) -> Any:
    mpl_ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    if mono:
        names = ("DejaVuSansMono-Bold.ttf", "DejaVuSansMono.ttf") if bold else ("DejaVuSansMono.ttf",)
    else:
        names = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf") if bold else ("DejaVuSans.ttf",)
    for nm in names:
        p = mpl_ttf / nm
        if p.is_file():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def _set_mpl_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "#fbfcfe",
            "axes.edgecolor": "#cbd5e1",
            "axes.labelcolor": "#0f172a",
            "axes.titlecolor": "#0f172a",
            "axes.titleweight": "bold",
            "xtick.color": "#334155",
            "ytick.color": "#334155",
            "grid.color": "#e2e8f0",
            "grid.linestyle": "-",
            "grid.linewidth": 0.7,
            "font.family": "DejaVu Sans",
            "font.size": 10.2,
            "axes.titlesize": 11.2,
            "axes.labelsize": 10.2,
            "legend.fontsize": 8.6,
        }
    )


def _load_replay(raw_dir: Path, name: str, n_ticks: int) -> tuple[np.ndarray, np.ndarray]:
    rdir = raw_dir / "replays"
    disp = np.fromfile(rdir / f"{name}_disp.bin", dtype=np.float32).reshape(n_ticks, N_ACT, N_ACT)
    opd = np.fromfile(rdir / f"{name}_opd.bin", dtype=np.float32).reshape(n_ticks, N_WF, N_WF)
    return disp.astype(np.float64), opd.astype(np.float64)


def _compute_step_metrics(
    opd_off: np.ndarray,
    disp_run: np.ndarray,
    opd_run: np.ndarray,
    pup: np.ndarray,
    q0: int = Q0_STEP,
) -> dict[str, Any]:
    static_opd = opd_off[-32:].mean(axis=0)
    stat_rms = float(np.sqrt(np.mean(static_opd[pup] ** 2)))
    w_pat = static_opd[pup] / max(float(np.dot(static_opd[pup], static_opd[pup])), 1e-18)

    y = opd_run[:, pup] @ w_pat
    y_post = y[q0:]
    end_opd = opd_run[-24:].mean(axis=0)
    dc_err_pct = float(
        np.linalg.norm(end_opd[pup] - static_opd[pup])
        / max(np.linalg.norm(static_opd[pup]), 1e-18)
        * 100.0
    )
    ov_pct = (float(np.max(y_post)) - 1.0) * 100.0
    # Post-rise ringing window: tau >= 2.0 ms after command onset (1.0 ms delay + 1.0 ms rise)
    i_ring = q0 + int(round(2.0 / DT_MS))
    ring_proj_pct = float(np.sqrt(np.mean((y[i_ring:] - 1.0) ** 2))) * 100.0
    dyn_2d_rms = np.sqrt(np.mean((opd_run[:, pup] - static_opd[None, pup]) ** 2, axis=1))
    dyn_2d_norm_pct = (dyn_2d_rms / max(stat_rms, 1e-18)) * 100.0
    full_wave_ring_pct = float(np.sqrt(np.mean(dyn_2d_norm_pct[i_ring:] ** 2)))

    out_band = np.where(np.abs(y_post - 1.0) > 0.05)[0]
    t_settle_5_ms = (int(out_band[-1]) + 1) * DT_MS if len(out_band) else 0.0

    # Interpolated 50% rise crossing
    t50_ms = float(len(y_post) * DT_MS)
    for k in range(len(y_post)):
        if y_post[k] >= 0.5:
            if k == 0:
                t50_ms = 0.5 * DT_MS
            else:
                dy = y_post[k] - y_post[k - 1]
                frac = (0.5 - y_post[k - 1]) / dy if dy > 1e-12 else 0.0
                t50_ms = (k - 1 + frac + 0.5) * DT_MS
            break

    # Dynamic residual PSD on post-onset window (y[q0 + 1.5 ms:] - 1.0)
    i_psd = q0 + int(round(1.5 / DT_MS))
    seg = y[i_psd:] - 1.0
    win = np.hanning(len(seg))
    n_fft = 1024
    freqs = np.fft.rfftfreq(n_fft, d=DT_SEC)
    spec = np.abs(np.fft.rfft(seg * win, n=n_fft)) / max(float(np.sum(win) * 0.5), 1e-12)
    psd_db = 20.0 * np.log10(np.maximum(spec, 1e-6))

    return {
        "y": y,
        "dyn_2d_norm_pct": dyn_2d_norm_pct,
        "dyn_2d_nm": dyn_2d_rms * 1.0e3,
        "static_opd": static_opd,
        "stat_rms_nm": stat_rms * 1.0e3,
        "dc_err_pct": dc_err_pct,
        "t50_ms": t50_ms,
        "overshoot_pct": ov_pct,
        "ring_proj_pct": ring_proj_pct,
        "full_wave_ring_pct": full_wave_ring_pct,
        "t_settle_5_ms": t_settle_5_ms,
        "cmd_peak_um": float(np.max(np.abs(disp_run))),
        "freqs": freqs,
        "psd_db": psd_db,
    }


def _build_lyot_coronagraph(
    pup_2d: np.ndarray,
    lambda_um: float = 1.65,
    pad_factor: int = 2,
    fpm_rad_ld: float = 3.0,
    lyot_frac: float = 0.90,
) -> dict[str, Any]:
    """Precompute an H-band (1.65 um) Classical Lyot Coronagraph propagator on the exact Subaru pupil."""
    nwf = pup_2d.shape[0]
    npad = nwf * pad_factor  # 512 -> 0.5 lambda/D per pixel? Wait: pup_diam = 0.9375*nwf -> 2.133 pix/(l/D)
    pup_diam_pix = 0.9375 * nwf
    pix_per_ld = float(npad) / pup_diam_pix  # ~2.1333 px / (lambda/D)

    yy, xx = np.mgrid[0:npad, 0:npad]
    cy = npad // 2
    cx = npad // 2
    r_ld = np.hypot(xx - cx, yy - cy) / pix_per_ld

    # Smooth-edged opaque classical Lyot focal-plane mask (radius 3.0 lambda/D)
    fpm = 1.0 / (1.0 + np.exp(-6.0 * (r_ld - fpm_rad_ld)))
    fpm_fft = np.fft.ifftshift(fpm)

    # Lyot stop: slightly undersized circular outer + slightly oversized central obscuration
    py, px = np.mgrid[0:nwf, 0:nwf]
    pc = 0.5 * (nwf - 1)
    rp = np.hypot(px - pc, py - pc) / (0.5 * pup_diam_pix)
    lyot = (pup_2d > 0.5) & (rp <= lyot_frac) & (rp >= 0.34)
    lyot_f = lyot.astype(np.float64)

    # Unocculted reference peak intensity (flat zero-OPD wavefront)
    sl = slice((npad - nwf) // 2, (npad + nwf) // 2)
    ep0 = np.zeros((npad, npad), dtype=np.complex128)
    ep0[sl, sl] = pup_2d.astype(np.float64)
    ef0 = np.fft.fft2(ep0)
    peak_unocc = float(np.max(np.abs(ef0) ** 2))

    # Focal-plane crop window +-24 lambda/D
    half_crop = int(round(24.0 * pix_per_ld))
    crop_sl = slice(cy - half_crop, cy + half_crop)
    r_ld_crop = r_ld[crop_sl, crop_sl]
    x_ld_crop = (xx[crop_sl, crop_sl] - cx) / pix_per_ld
    y_ld_crop = (yy[crop_sl, crop_sl] - cy) / pix_per_ld

    return {
        "nwf": nwf,
        "npad": npad,
        "sl": sl,
        "pup": pup_2d.astype(np.float64),
        "lyot": lyot_f,
        "fpm_fft": fpm_fft,
        "peak_unocc": peak_unocc,
        "lambda_um": lambda_um,
        "pix_per_ld": pix_per_ld,
        "crop_sl": crop_sl,
        "r_ld_crop": r_ld_crop,
        "x_ld_crop": x_ld_crop,
        "y_ld_crop": y_ld_crop,
        "extent_ld": [-half_crop / pix_per_ld, half_crop / pix_per_ld, -half_crop / pix_per_ld, half_crop / pix_per_ld],
    }


def _propagate_coro_cube(opd_cube_um: np.ndarray, coro: dict[str, Any]) -> np.ndarray:
    """Propagate a [N_t, 256, 256] OPD cube [um] through the H-band Lyot coronagraph -> normalized contrast cube."""
    n_t = opd_cube_um.shape[0]
    npad = coro["npad"]
    sl = coro["sl"]
    crop_sl = coro["crop_sl"]
    pup = coro["pup"]
    lyot = coro["lyot"]
    fpm_fft = coro["fpm_fft"]
    inv_peak = 1.0 / coro["peak_unocc"]
    k_phase = 2.0 * np.pi / coro["lambda_um"]

    # Determine output shape
    c_h = crop_sl.stop - crop_sl.start
    out = np.empty((n_t, c_h, c_h), dtype=np.float32)
    ep = np.zeros((npad, npad), dtype=np.complex128)
    for t in range(n_t):
        ep.fill(0.0)
        ep[sl, sl] = pup * np.exp(1j * k_phase * opd_cube_um[t])
        # Pupil -> FPM -> Lyot plane -> Science focal plane
        ef1 = np.fft.fft2(ep) * fpm_fft
        ep2 = np.fft.ifft2(ef1)
        ep2_lyot = np.zeros_like(ep2)
        ep2_lyot[sl, sl] = ep2[sl, sl] * lyot
        ef2 = np.fft.fftshift(np.fft.fft2(ep2_lyot))
        psf = (np.abs(ef2) ** 2) * inv_peak
        out[t] = psf[crop_sl, crop_sl].astype(np.float32)
    return out


def _colorize_diverging(img: np.ndarray, vmax: float, mask: np.ndarray | None = None) -> np.ndarray:
    v = max(float(vmax), 1e-12)
    x = np.clip(0.5 + 0.5 * (img / v), 0.0, 1.0)
    rgb = (matplotlib.colormaps["RdBu_r"](x)[:, :, :3] * 255.0 + 0.5).astype(np.uint8)
    if mask is not None:
        rgb[~mask] = (241, 245, 249)
    # Flip vertically so visual display matches origin="lower"
    return np.flipud(rgb)


def _colorize_log_psf(psf: np.ndarray, vmin_log: float = -6.5, vmax_log: float = -1.5) -> np.ndarray:
    lp = np.log10(np.maximum(psf.astype(np.float64), 10.0 ** (vmin_log - 1.0)))
    x = np.clip((lp - vmin_log) / max(vmax_log - vmin_log, 1e-6), 0.0, 1.0)
    rgb = (matplotlib.colormaps["inferno"](x)[:, :, :3] * 255.0 + 0.5).astype(np.uint8)
    return np.flipud(rgb)


def _resize_rgb(arr: np.ndarray, size: int) -> np.ndarray:
    if arr.shape[0] == size and arr.shape[1] == size:
        return arr
    return np.asarray(Image.fromarray(arr).resize((size, size), resample=Image.BILINEAR))


def _project_3drm_modal(raw_dir: Path, resp_file: str, stat_file: str) -> tuple[np.ndarray, int, float]:
    r3 = fits.getdata(raw_dir / resp_file).astype(np.float64)
    hdr = fits.getheader(raw_dir / resp_file)
    stat = fits.getdata(raw_dir / stat_file).astype(np.float64)
    u, s, vt = np.linalg.svd(stat, full_matrices=False)
    c_pinv = (u * np.where(s > 1e-3 * s[0], 1.0 / s, 0.0)[None, :]) @ vt
    m3 = np.einsum("sp,tqp->tsq", c_pinv, r3, optimize=True)
    return m3, int(hdr["Q0_BIN"]), float(hdr["DT_SEC"]) * 1.0e3


def build_all_figures_and_metrics(raw_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Analyze all live GPU captures and render all 5 publication figures + side-by-side MP4."""
    _set_mpl_style()
    out_dir.mkdir(parents=True, exist_ok=True)
    calib_meta = json.loads((raw_dir / "calib_meta.json").read_text(encoding="utf-8"))
    pup_2d = fits.getdata(raw_dir / "pupil.fits").astype(np.float64)
    pup = pup_2d > 0.5

    # Load all lockstep 8 kHz replays
    d_pi_off, o_pi_off = _load_replay(raw_dir, "poke_interior_off", N_STEP)
    d_pi_siso, o_pi_siso = _load_replay(raw_dir, "poke_interior_siso", N_STEP)
    d_pi_mimo, o_pi_mimo = _load_replay(raw_dir, "poke_interior_mimo", N_STEP)

    d_pr_off, o_pr_off = _load_replay(raw_dir, "poke_rim_off", N_STEP)
    d_pr_siso, o_pr_siso = _load_replay(raw_dir, "poke_rim_siso", N_STEP)

    d_zf_off, o_zf_off = _load_replay(raw_dir, "zernike_focus_off", N_STEP)
    d_zf_mimo, o_zf_mimo = _load_replay(raw_dir, "zernike_focus_mimo", N_STEP)

    d_za_off, o_za_off = _load_replay(raw_dir, "zernike_astig_off", N_STEP)
    d_za_mimo, o_za_mimo = _load_replay(raw_dir, "zernike_astig_mimo", N_STEP)

    d_ag_off, o_ag_off = _load_replay(raw_dir, "astro_500hz_sq_off", N_AG)
    d_ag_siso, o_ag_siso = _load_replay(raw_dir, "astro_500hz_sq_siso", N_AG)
    d_ag_mimo, o_ag_mimo = _load_replay(raw_dir, "astro_500hz_sq_mimo", N_AG)

    d_ak_off, o_ak_off = _load_replay(raw_dir, "astro_500hz_k10_off", N_AG)
    d_ak_mimo, o_ak_mimo = _load_replay(raw_dir, "astro_500hz_k10_mimo", N_AG)

    d_aq_off, o_aq_off = _load_replay(raw_dir, "astro_500hz_quad_off", N_AG)
    d_aq_mimo, o_aq_mimo = _load_replay(raw_dir, "astro_500hz_quad_mimo", N_AG)

    # Compute step metrics
    m_pi = {
        "off": _compute_step_metrics(o_pi_off, d_pi_off, o_pi_off, pup),
        "siso": _compute_step_metrics(o_pi_off, d_pi_siso, o_pi_siso, pup),
        "mimo": _compute_step_metrics(o_pi_off, d_pi_mimo, o_pi_mimo, pup),
    }
    m_pr = {
        "off": _compute_step_metrics(o_pr_off, d_pr_off, o_pr_off, pup),
        "siso": _compute_step_metrics(o_pr_off, d_pr_siso, o_pr_siso, pup),
    }
    m_zf = {
        "off": _compute_step_metrics(o_zf_off, d_zf_off, o_zf_off, pup),
        "mimo": _compute_step_metrics(o_zf_off, d_zf_mimo, o_zf_mimo, pup),
    }
    m_za = {
        "off": _compute_step_metrics(o_za_off, d_za_off, o_za_off, pup),
        "mimo": _compute_step_metrics(o_za_off, d_za_mimo, o_za_mimo, pup),
    }

    # Build orthonormal pupil Zernike projection matrix (Z2..Z29 on 256x256 pupil) for cross-mode analysis
    yy_w, xx_w = np.mgrid[0:N_WF, 0:N_WF]
    ctr_w = 0.5 * (N_WF - 1)
    r_pup_w = 0.5 * 0.9375 * N_WF
    rx_w = (xx_w - ctr_w) / r_pup_w
    ry_w = (yy_w - ctr_w) / r_pup_w
    rr_w = np.hypot(rx_w, ry_w)
    th_w = np.arctan2(ry_w, rx_w)

    def _z_rad(n: int, m: int, r: np.ndarray) -> np.ndarray:
        import math

        res = np.zeros_like(r)
        for s in range((n - m) // 2 + 1):
            num = ((-1) ** s) * math.factorial(n - s)
            den = (
                math.factorial(s)
                * math.factorial((n + m) // 2 - s)
                * math.factorial((n - m) // 2 - s)
            )
            res += (num / den) * (r ** (n - 2 * s))
        return res

    z_basis_pup: list[np.ndarray] = []
    for n in range(1, 9):
        for m in range(0, n + 1):
            if (n - m) % 2 != 0:
                continue
            R = _z_rad(n, m, rr_w)
            if m == 0:
                v = R[pup]
                z_basis_pup.append(v)
            else:
                z_basis_pup.append((R * np.cos(m * th_w))[pup])
                z_basis_pup.append((R * np.sin(m * th_w))[pup])
            if len(z_basis_pup) >= 28:
                break
        if len(z_basis_pup) >= 28:
            break
    # Gram-Schmidt orthonormalize Zernike basis on obstructed Subaru pupil
    Z_mat = np.stack(z_basis_pup[:28], axis=0)  # [28, n_pup]
    for i in range(Z_mat.shape[0]):
        v = Z_mat[i].copy()
        v -= np.mean(v)
        for j in range(i):
            v -= np.dot(v, Z_mat[j]) * Z_mat[j]
        nrm = float(np.linalg.norm(v))
        if nrm > 1e-12:
            v /= nrm
        Z_mat[i] = v

    # Project Z4 Focus replay onto pupil Zernikes (index 2 = Z4 Focus, index 9 = Z11 Spherical!)
    # Identify exact Z4 and Z11 indices from static focus projection & radial symmetry
    zf_coeff_off = o_zf_off[:, pup] @ Z_mat.T  # [N_STEP, N_z]
    zf_coeff_mimo = o_zf_mimo[:, pup] @ Z_mat.T
    zf_stat_c = zf_coeff_off[-32:].mean(axis=0)
    idx_focus = int(np.argmax(np.abs(zf_stat_c)))
    zf_scale = float(zf_stat_c[idx_focus])
    zf_norm_off = zf_coeff_off / zf_scale
    zf_norm_mimo = zf_coeff_mimo / zf_scale
    zf_stat_norm = zf_stat_c / zf_scale
    off_mask_z = np.ones(Z_mat.shape[0], dtype=bool)
    off_mask_z[idx_focus] = False
    dyn_off_off = zf_norm_off - zf_stat_norm[None, :] * zf_norm_off[:, idx_focus : idx_focus + 1]
    dyn_off_mimo = zf_norm_mimo - zf_stat_norm[None, :] * zf_norm_mimo[:, idx_focus : idx_focus + 1]
    zf_xtalk_off = np.linalg.norm(dyn_off_off[:, off_mask_z], axis=1) * 100.0
    zf_xtalk_mimo = np.linalg.norm(dyn_off_mimo[:, off_mask_z], axis=1) * 100.0
    peak_off_mode = int(np.argmax(np.max(np.abs(dyn_off_off[Q0_STEP:, :] * off_mask_z[None, :]), axis=0)))

    # =========================================================================
    # FIGURE 1: Calibration (3D RM) -> Optimal Pre-Shaper Synthesis Pipeline
    # =========================================================================
    m3_z28_p1, q0_z1, dt_z1 = _project_3drm_modal(raw_dir, "zernike28_resp3D.fits", "zernike28_resp3D_static.fits")
    m3_z8_p2_raw = fits.getdata(raw_dir / "zernike8_p2_resp3D.fits").astype(np.float64)
    h_z8_p2 = fits.getheader(raw_dir / "zernike8_p2_resp3D.fits")
    st_z28 = fits.getdata(raw_dir / "zernike28_resp3D_static.fits").astype(np.float64)[:8]
    u_z, s_z, vt_z = np.linalg.svd(st_z28, full_matrices=False)
    c_z8 = (u_z * np.where(s_z > 1e-3 * s_z[0], 1.0 / s_z, 0.0)[None, :]) @ vt_z
    m3_z8_p1 = np.einsum("sp,tqp->tsq", c_z8, fits.getdata(raw_dir / "zernike28_resp3D.fits").astype(np.float64)[:, :8, :], optimize=True)
    m3_z8_p2 = np.einsum("sp,tqp->tsq", c_z8, m3_z8_p2_raw, optimize=True)
    st_z8_p2 = fits.getdata(raw_dir / "zernike8_p2_resp3D_static.fits").astype(np.float64)
    p2_z8_dc_err_pct = float(np.linalg.norm(st_z8_p2 - st_z28) / np.linalg.norm(st_z28)) * 100.0

    m3_ag_p1, q0_a1, dt_a1 = _project_3drm_modal(raw_dir, "astro20_resp3D.fits", "astro20_resp3D_static.fits")
    r_ag_p2 = fits.getdata(raw_dir / "astro20_p2_resp3D.fits").astype(np.float64)
    h_ag_p2 = fits.getheader(raw_dir / "astro20_p2_resp3D.fits")
    st_ag1 = fits.getdata(raw_dir / "astro20_resp3D_static.fits").astype(np.float64)
    st_ag2 = fits.getdata(raw_dir / "astro20_p2_resp3D_static.fits").astype(np.float64)
    u_a, s_a, vt_a = np.linalg.svd(st_ag1, full_matrices=False)
    c_ag = (u_a * np.where(s_a > 1e-3 * s_a[0], 1.0 / s_a, 0.0)[None, :]) @ vt_a
    m3_ag_p2 = np.einsum("sp,tqp->tsq", c_ag, r_ag_p2, optimize=True)
    p2_ag_dc_err_pct = float(np.linalg.norm(st_ag2 - st_ag1) / np.linalg.norm(st_ag1)) * 100.0

    # Kernel step command trajectories
    c_siso = fits.getdata(raw_dir / "ps_siso_uniform.fits").astype(np.float64)[:, 0, 0]
    c_ring = fits.getdata(raw_dir / "ps_rings8_mimo.fits").astype(np.float64)  # [M_buf, 8, 8]
    c_astro = fits.getdata(raw_dir / "ps_astro20_mimo.fits").astype(np.float64)  # [M_buf, 20, 20]
    c_zern = fits.getdata(raw_dir / "ps_zernike28_mimo.fits").astype(np.float64)  # [M_buf, 28, 28]

    fig, axes = plt.subplots(2, 2, figsize=(14.4, 9.6), constrained_layout=True)

    # Panel (a): Live wall-clock 1 kHz PyWFS Pass-1 vs Pass-2 3D RM step responses
    ax = axes[0, 0]
    t_z1 = (np.arange(m3_z8_p1.shape[0]) - q0_z1 + 0.5) * dt_z1
    t_z2 = (np.arange(m3_z8_p2.shape[0]) - int(h_z8_p2["Q0_BIN"]) + 0.5) * float(h_z8_p2["DT_SEC"]) * 1e3
    t_a1 = (np.arange(m3_ag_p1.shape[0]) - q0_a1 + 0.5) * dt_a1
    t_a2 = (np.arange(m3_ag_p2.shape[0]) - int(h_ag_p2["Q0_BIN"]) + 0.5) * float(h_ag_p2["DT_SEC"]) * 1e3
    ax.plot(t_z1, m3_z8_p1[:, 2, 2], color="#dc2626", ls="--", lw=1.9, label="Pass-1 Raw 3D RM — Focus Z4 (unshaped)")
    ax.plot(t_z2, m3_z8_p2[:, 2, 2], color="#dc2626", lw=2.3, label=f"Pass-2 Live 8 kHz dmpreshaper — Focus Z4 (DC err {p2_z8_dc_err_pct:.2f}%)")
    ax.plot(t_a1, m3_ag_p1[:, 0, 0], color="#2563eb", ls="--", lw=1.9, label="Pass-1 Raw 3D RM — Astrogrid k=8 (unshaped)")
    ax.plot(t_a2, m3_ag_p2[:, 0, 0], color="#2563eb", lw=2.3, label=f"Pass-2 Live 8 kHz dmpreshaper — Astrogrid k=8 (DC err {p2_ag_dc_err_pct:.2f}%)")
    ax.axvline(0.0, color="#64748b", ls=":", lw=1.0)
    ax.axhline(1.0, color="#0f172a", ls=":", lw=1.0)
    ax.set_xlim(-0.5, 11.5)
    ax.set_ylim(-0.08, 1.32)
    ax.set_xlabel("Lag after DM command τ [ms]")
    ax.set_ylabel("1 kHz PyWFS projected modal step response")
    ax.set_title("(a) Stroboscopic 3D RM Calibration: Pass-1 (Raw) vs. Pass-2 (8 kHz Pre-Shaped)")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=8.1)

    # Panel (b): Synthesized 8 kHz look-ahead command trajectories u_shaped(t) = u_step + C[k]
    ax = axes[0, 1]
    t_k_s = np.arange(len(c_siso) + 8) * DT_MS
    u_siso = np.concatenate([1.0 + c_siso, np.ones(8)])
    u_r0 = np.concatenate([1.0 + c_ring[:, 0, 0], np.ones(8)])
    u_r1 = np.concatenate([c_ring[:, 1, 0], np.zeros(8)])
    u_r2 = np.concatenate([c_ring[:, 2, 0], np.zeros(8)])
    t_k_a = np.arange(c_astro.shape[0] + 8) * DT_MS
    u_ag = np.concatenate([1.0 + c_astro[:, 0, 0], np.ones(8)])
    ax.step(t_k_s, np.ones_like(t_k_s), where="post", color="#94a3b8", ls=":", lw=1.4, label="Unshaped unit step command (1.0)")
    ax.step(t_k_s, u_siso, where="post", color="#d97706", lw=2.0, label="Uniform SISO (KMODE 2) on center actuator")
    ax.step(t_k_s, u_r0, where="post", color="#059669", lw=2.2, label="Radial-Ring MIMO (KMODE 0): center (r=0)")
    ax.step(t_k_s, u_r1, where="post", color="#0d9488", ls="--", lw=1.8, label="Radial-Ring MIMO: counter-wave Ring 1 (r=1)")
    ax.step(t_k_s, u_r2, where="post", color="#6366f1", ls="-.", lw=1.5, label="Radial-Ring MIMO: counter-wave Ring 2 (r=1.4)")
    ax.step(t_k_a, u_ag, where="post", color="#2563eb", lw=2.0, label="Astrogrid MIMO (KMODE 0): k=8 mode")
    ax.axhline(0.0, color="#64748b", lw=0.7)
    ax.set_xlim(0.0, 6.5)
    ax.set_ylim(-0.35, 1.55)
    ax.set_xlabel("Time after command update [ms] (8 kHz / 125 μs ticks)")
    ax.set_ylabel("Shaped DM command (unit step = 1.0)")
    ax.set_title("(b) Synthesized 8 kHz Look-Ahead Command Trajectories (Unity DC Gain)")
    ax.grid(True)
    ax.legend(loc="right", frameon=True, facecolor="white", fontsize=8.0)

    # Panel (c): Frequency-domain transfer function equalization (Plate vs Pre-Shaper FIR vs Combined)
    ax = axes[1, 0]
    n_f = 2048
    freqs_f = np.fft.rfftfreq(n_f, d=DT_SEC)

    def _step_tf(y_step: np.ndarray) -> np.ndarray:
        h = np.diff(y_step, prepend=0.0)
        H = np.fft.rfft(h, n=n_f)
        return np.abs(H) / max(float(np.abs(H[0])), 1e-12)

    def _fir_tf(c_vec: np.ndarray) -> np.ndarray:
        s = np.concatenate([1.0 + c_vec, np.ones(128)])
        h = np.diff(s, prepend=0.0)
        H = np.fft.rfft(h, n=n_f)
        return np.abs(H) / max(float(np.abs(H[0])), 1e-12)

    H_zf_off = _step_tf(m_zf["off"]["y"][Q0_STEP:])
    H_zf_on = _step_tf(m_zf["mimo"]["y"][Q0_STEP:])
    F_zf = _fir_tf(c_zern[:, 2, 2])
    F_ag = _fir_tf(c_astro[:, 0, 0])

    ax.plot(freqs_f, H_zf_off, color="#dc2626", lw=2.2, label="Unshaped plate DM |H_DM(f)| — Focus Z4 (f₀ ≈ 1.0 kHz)")
    ax.plot(freqs_f, F_zf, color="#dc2626", ls=":", lw=1.8, label="Focus MIMO Pre-Shaper |F_PS(f)| (notch @ 1.0 kHz)")
    ax.plot(freqs_f, H_zf_on, color="#059669", lw=2.3, label="Combined Pre-Shaped |H_DM · F_PS| — Focus Z4")
    ax.plot(freqs_f, F_ag, color="#2563eb", ls="--", lw=2.1, label="Astrogrid k=8 Pre-Shaper |F_PS(f)| (deep notch @ 1.57 kHz)")
    ax.axvline(1000.0, color="#dc2626", ls=":", lw=0.9, alpha=0.6)
    ax.axvline(1567.0, color="#2563eb", ls=":", lw=0.9, alpha=0.6)
    ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
    ax.set_xlim(0.0, 2800.0)
    ax.set_ylim(0.0, 3.6)
    ax.set_xlabel("Temporal frequency f [Hz]")
    ax.set_ylabel("Normalized magnitude |H(f)| (DC = 1)")
    ax.set_title("(c) Automatic Anti-Resonance Notching Across Plate Dispersion Frequencies")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.0)

    # Panel (d): Live 8 kHz Pass-1 vs Pass-2 Off-Diagonal Cross-Mode Mechanical Coupling
    ax = axes[1, 1]
    eye8 = np.eye(8)[None, :, :]
    off_z1 = np.linalg.norm((m3_z8_p1[q0_z1:] * (1.0 - eye8)).reshape(-1, 64), axis=1)
    off_z2 = np.linalg.norm((m3_z8_p2[int(h_z8_p2["Q0_BIN"]) :] * (1.0 - eye8)).reshape(-1, 64), axis=1)
    tz_p1 = (np.arange(len(off_z1)) + 0.5) * dt_z1
    tz_p2 = (np.arange(len(off_z2)) + 0.5) * float(h_z8_p2["DT_SEC"]) * 1e3
    dc_n8 = float(np.sqrt(8.0))
    pct_z1 = 100.0 * off_z1 / dc_n8
    pct_z2 = 100.0 * off_z2 / dc_n8

    n_ag_m = int(m3_ag_p1.shape[1])
    eye_ag = np.eye(n_ag_m)[None, :, :]
    dc_nag = float(np.sqrt(float(n_ag_m)))
    off_a1 = np.linalg.norm((m3_ag_p1[q0_a1:] * (1.0 - eye_ag)).reshape(-1, n_ag_m * n_ag_m), axis=1)
    off_a2 = np.linalg.norm((m3_ag_p2[int(h_ag_p2["Q0_BIN"]) :] * (1.0 - eye_ag)).reshape(-1, n_ag_m * n_ag_m), axis=1)
    ta_p1 = (np.arange(len(off_a1)) + 0.5) * dt_a1
    ta_p2 = (np.arange(len(off_a2)) + 0.5) * float(h_ag_p2["DT_SEC"]) * 1e3
    pct_a1 = 100.0 * off_a1 / dc_nag
    pct_a2 = 100.0 * off_a2 / dc_nag

    ax.plot(tz_p1, pct_z1, color="#dc2626", ls="--", lw=1.9, label=f"Zernike Z2–Z9 Pass-1 Unshaped (pk {pct_z1.max():.1f}%)")
    ax.plot(tz_p2, pct_z2, color="#dc2626", lw=2.3, label=f"Zernike Z2–Z9 Pass-2 Live 8 kHz Pre-Shaper (pk {pct_z2.max():.1f}%)")
    ax.plot(ta_p1, pct_a1, color="#2563eb", ls="--", lw=1.9, label=f"Astrogrid {n_ag_m}-mode Pass-1 Unshaped (pk {pct_a1.max():.1f}%)")
    ax.plot(ta_p2, pct_a2, color="#2563eb", lw=2.3, label=f"Astrogrid {n_ag_m}-mode Pass-2 Live 8 kHz Pre-Shaper (pk {pct_a2.max():.1f}%)")
    ax.set_xlim(0.0, 12.0)
    ax.set_xlabel("Lag after DM command τ [ms]")
    ax.set_ylabel("Off-diagonal cross-mode coupling ‖M_off(τ)‖ / √N [%]")
    ax.set_title("(d) Live 8 kHz Pass-2 Cross-Mode Mechanical Coupling Suppression")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.1)

    fig.suptitle(
        "End-to-End Pipeline: Fixed 1 kHz PyWFS 3D RM Calibration → Optimal 8 kHz DM Pre-Shaper Synthesis",
        fontsize=13,
        fontweight="bold",
    )
    fig.savefig(out_dir / "fig1_calib_3drm_to_preshaper.png", dpi=165)
    plt.close(fig)

    # =========================================================================
    # FIGURE 1b: Synthesized 8 kHz MIMO Pre-Shaper Kernels (C[k, out, in] & 2D DM Stamps)
    # =========================================================================
    def _kernel_stats(c_cube: np.ndarray, p_fwd_shape: tuple[int, ...], name: str, kfile: str) -> dict[str, Any]:
        m_b, n_m, _ = c_cube.shape
        eye_m = np.eye(n_m)
        e_mat = np.sqrt(np.sum(c_cube ** 2, axis=0))  # [N_in, N_in]
        frob_tot = float(np.linalg.norm(c_cube))
        frob_diag = float(np.linalg.norm(c_cube * eye_m[None]))
        frob_off = float(np.linalg.norm(c_cube * (1.0 - eye_m[None])))
        off_pct = 100.0 * (frob_off ** 2) / max(frob_tot ** 2, 1e-18)
        diag_taps = np.linalg.norm((c_cube * eye_m[None]).reshape(m_b, -1), axis=1)
        off_taps = np.linalg.norm((c_cube * (1.0 - eye_m[None])).reshape(m_b, -1), axis=1)
        max_gain = float(np.max(np.abs(eye_m[None] + c_cube)))
        return {
            "name": name,
            "file": kfile,
            "m_buf": int(m_b),
            "n_modes": int(n_m),
            "p_fwd_shape": list(p_fwd_shape),
            "frob_tot": round(frob_tot, 4),
            "frob_diag": round(frob_diag, 4),
            "frob_off": round(frob_off, 4),
            "off_energy_pct": round(off_pct, 1),
            "max_step_gain": round(max_gain, 3),
            "e_mat": e_mat,
            "diag_taps": diag_taps,
            "off_taps": off_taps,
        }

    with fits.open(raw_dir / "ps_rings8_mimo.fits") as hdul:
        pf_ring = hdul["P_FWD"].data.astype(np.float64)
    with fits.open(raw_dir / "ps_zernike28_mimo.fits") as hdul:
        pf_zern = hdul["P_FWD"].data.astype(np.float64)
    with fits.open(raw_dir / "ps_astro20_mimo.fits") as hdul:
        pf_astro = hdul["P_FWD"].data.astype(np.float64)

    ks_ring = _kernel_stats(c_ring, pf_ring.shape, "Radial-Ring MIMO", "ps_rings8_mimo.fits")
    ks_zern = _kernel_stats(c_zern, pf_zern.shape, "Zernike 28-Mode MIMO", "ps_zernike28_mimo.fits")
    ks_astro = _kernel_stats(c_astro, pf_astro.shape, "Astrogrid + Rim MIMO", "ps_astro20_mimo.fits")

    fig = plt.figure(figsize=(15.8, 9.8))
    gs = fig.add_gridspec(2, 6, height_ratios=[1.10, 1.05], left=0.055, right=0.975, top=0.915, bottom=0.065, hspace=0.34, wspace=0.62)

    vmin_k, vmax_k = -2.6, 0.35

    # (a) Radial-Ring MIMO 8x8 coupling matrix
    ax = fig.add_subplot(gs[0, 0:2])
    im_kr = ax.imshow(
        np.log10(np.maximum(ks_ring["e_mat"], 10.0 ** (vmin_k - 0.5))),
        cmap="magma",
        vmin=vmin_k,
        vmax=vmax_k,
        origin="lower",
        interpolation="nearest",
    )
    r_lbls = ["Ctr", "R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    ax.set_xticks(range(8))
    ax.set_xticklabels(r_lbls, fontsize=8.5)
    ax.set_yticks(range(8))
    ax.set_yticklabels(r_lbls, fontsize=8.5)
    ax.set_xlabel("Input commanded mode j")
    ax.set_ylabel("Output driven mode i")
    ax.set_title(f"(a) Radial-Ring MIMO [8×8×{ks_ring['m_buf']}]\n(Off-diag energy: {ks_ring['off_energy_pct']:.1f}%)")
    fig.colorbar(im_kr, ax=ax, shrink=0.86, label="log₁₀ ‖C[:, i, j]‖₂")

    # (b) Zernike 28x28 coupling matrix
    ax = fig.add_subplot(gs[0, 2:4])
    im_kz = ax.imshow(
        np.log10(np.maximum(ks_zern["e_mat"], 10.0 ** (vmin_k - 0.5))),
        cmap="magma",
        vmin=vmin_k,
        vmax=vmax_k,
        origin="lower",
        interpolation="nearest",
    )
    ztks = [0, 2, 4, 9, 14, 19, 24, 27]
    ax.set_xticks(ztks)
    ax.set_xticklabels([f"Z{i + 2}" for i in ztks], fontsize=8.0)
    ax.set_yticks(ztks)
    ax.set_yticklabels([f"Z{i + 2}" for i in ztks], fontsize=8.0)
    ax.set_xlabel("Input commanded Zernike j")
    ax.set_ylabel("Output driven Zernike i")
    ax.set_title(f"(b) Zernike MIMO [28×28×{ks_zern['m_buf']}]\n(Off-diag energy: {ks_zern['off_energy_pct']:.1f}% — radial rules)")
    fig.colorbar(im_kz, ax=ax, shrink=0.86, label="log₁₀ ‖C[:, i, j]‖₂")

    # (c) Astrogrid + Jacobi-Anger Rim 20x20 coupling matrix
    ax = fig.add_subplot(gs[0, 4:6])
    im_ka = ax.imshow(
        np.log10(np.maximum(ks_astro["e_mat"], 10.0 ** (vmin_k - 0.5))),
        cmap="magma",
        vmin=vmin_k,
        vmax=vmax_k,
        origin="lower",
        interpolation="nearest",
    )
    ax.axhline(7.5, color="#38bdf8", ls="--", lw=1.1, alpha=0.9)
    ax.axvline(7.5, color="#38bdf8", ls="--", lw=1.1, alpha=0.9)
    ax.set_xticks([0, 4, 7, 8, 12, 16, 19])
    ax.set_xticklabels(["c8+", "c7", "c10", "J0", "J8", "J16", "J3s"], fontsize=8.0)
    ax.set_yticks([0, 4, 7, 8, 12, 16, 19])
    ax.set_yticklabels(["c8+", "c7", "c10", "J0", "J8", "J16", "J3s"], fontsize=8.0)
    ax.set_xlabel("Input mode (0–7: Fourier | 8–19: Bessel Rim)")
    ax.set_ylabel("Output driven mode")
    ax.set_title(f"(c) Astrogrid + Rim MIMO [20×20×{ks_astro['m_buf']}]\n(Off-diag energy: {ks_astro['off_energy_pct']:.1f}%)")
    fig.colorbar(im_ka, ax=ax, shrink=0.86, label="log₁₀ ‖C[:, i, j]‖₂")

    # (d) Bottom-Left: 2D DM Actuator-Space Shaped Command Stamps u_DM(x,y; k) for Radial-Ring MIMO poke (22, 23)
    gs_st = gs[1, 0:3].subgridspec(2, 3, wspace=0.14, hspace=0.28)
    u_ring_step = np.eye(8)[None, :, 0] + c_ring[:, :, 0]  # [63, 8]
    u_ring_act = np.einsum("km,myx->kyx", u_ring_step, pf_ring)  # [63, 64, 64]
    ax_c, ay_c, rad_p = 22, 23, 8
    stamp_taps = [0, 1, 2, 3, 4, 16]
    im_st = None
    ax_st_list = []
    for idx_s, tk_s in enumerate(stamp_taps):
        ax_s = fig.add_subplot(gs_st[idx_s // 3, idx_s % 3])
        ax_st_list.append(ax_s)
        patch = u_ring_act[tk_s, ay_c - rad_p : ay_c + rad_p + 1, ax_c - rad_p : ax_c + rad_p + 1]
        im_st = ax_s.imshow(
            patch,
            cmap="RdBu_r",
            vmin=-0.35,
            vmax=0.35,
            origin="lower",
            interpolation="nearest",
            extent=[-rad_p - 0.5, rad_p + 0.5, -rad_p - 0.5, rad_p + 0.5],
        )
        u0_val = float(u_ring_act[tk_s, ay_c, ax_c])
        ax_s.set_title(f"k={tk_s} ({tk_s * DT_MS:.2f} ms) · u₀={u0_val:.2f}", fontsize=8.3, pad=3)
        ax_s.set_xticks([-6, 0, 6])
        ax_s.set_yticks([-6, 0, 6])
        ax_s.tick_params(labelsize=7.4)
        if idx_s // 3 == 1:
            ax_s.set_xlabel("Δx [act]", fontsize=8.0)
        if idx_s % 3 == 0:
            ax_s.set_ylabel("Δy [act]", fontsize=8.0)
    assert im_st is not None
    cb_st = fig.colorbar(im_st, ax=ax_st_list, shrink=0.90, pad=0.04, aspect=26)
    cb_st.set_label("DM cmd u(x,y; k) [unit poke]", fontsize=8.6)
    fig.text(
        0.045,
        0.470,
        "(d) 2D DM Stamps u_DM(x,y; k) Around Poke (22, 23): Ring-1 Lift & Ring-2 Wave-Cancel Moat",
        ha="left",
        va="bottom",
        fontsize=9.4,
        fontweight="bold",
        color="#0f172a",
    )

    # (e) Bottom-Right: Tap-by-Tap Frobenius Norm Decay (Diagonal vs. Off-Diagonal)
    ax = fig.add_subplot(gs[1, 3:6])
    t_r = np.arange(ks_ring["m_buf"]) * DT_MS
    t_z = np.arange(ks_zern["m_buf"]) * DT_MS
    t_a = np.arange(ks_astro["m_buf"]) * DT_MS
    ax.semilogy(t_r, np.maximum(ks_ring["diag_taps"], 1e-4), color="#059669", lw=2.0, label="Radial-Ring MIMO — diagonal ‖C_diag[k]‖")
    ax.semilogy(t_r, np.maximum(ks_ring["off_taps"], 1e-4), color="#059669", ls="--", lw=1.8, label="Radial-Ring MIMO — off-diag ‖C_off[k]‖ (wave cancel)")
    ax.semilogy(t_z, np.maximum(ks_zern["diag_taps"], 1e-4), color="#dc2626", lw=2.0, label="Zernike 28×28 MIMO — diagonal")
    ax.semilogy(t_z, np.maximum(ks_zern["off_taps"], 1e-4), color="#dc2626", ls="--", lw=1.6, label="Zernike 28×28 MIMO — off-diag (rim-reflection cancel)")
    ax.semilogy(t_a, np.maximum(ks_astro["diag_taps"], 1e-4), color="#2563eb", lw=2.0, label="Astrogrid 20×20 MIMO — diagonal")
    ax.semilogy(t_a, np.maximum(ks_astro["off_taps"], 1e-4), color="#2563eb", ls="--", lw=1.6, label="Astrogrid 20×20 MIMO — off-diag (Bessel rim cancel)")
    ax.axvline(0.50, color="#64748b", ls=":", lw=1.0, alpha=0.8)
    ax.text(0.55, 2.8, "Posicast\nT₀/2", fontsize=7.8, color="#475569")
    ax.set_xlim(0.0, 8.2)
    ax.set_ylim(3e-3, 5.5)
    ax.set_xlabel("Look-ahead buffer lag τ = k · 125 μs [ms]")
    ax.set_ylabel("Kernel slice Frobenius norm ‖C[k]‖_F")
    ax.set_title("(e) Temporal Tap Decay: Diagonal Braking vs. Off-Diagonal Wave/Rim Tail")
    ax.grid(True, which="both", alpha=0.55)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=7.6)

    fig.suptitle(
        "Synthesized 8 kHz Causal MIMO Pre-Shaper Kernels C[k, i, j] (deconv_exp = ON, energy_weight = ON)",
        fontsize=13,
        fontweight="bold",
    )
    fig.savefig(out_dir / "fig1b_mimo_kernels.png", dpi=165)
    plt.close(fig)

    # =========================================================================
    # FIGURE 2a: Single-Actuator Zonal Poke WITH vs WITHOUT (2x2 Quantitative)
    # =========================================================================
    t_step_ms = (np.arange(N_STEP) - Q0_STEP) * DT_MS
    fig, axes = plt.subplots(2, 2, figsize=(14.2, 9.6), constrained_layout=True)

    # (a) Interior (22, 23) projected step response
    ax = axes[0, 0]
    ax.plot(t_step_ms, m_pi["off"]["y"], color="#dc2626", lw=2.2,
            label=f"WITHOUT pre-shaper (+{m_pi['off']['overshoot_pct']:.1f}% pk, settle {m_pi['off']['t_settle_5_ms']:.2f} ms)")
    ax.plot(t_step_ms, m_pi["siso"]["y"], color="#d97706", lw=2.0,
            label=f"WITH Uniform SISO KMODE=2 (+{m_pi['siso']['overshoot_pct']:.1f}% pk, settle {m_pi['siso']['t_settle_5_ms']:.2f} ms)")
    ax.plot(t_step_ms, m_pi["mimo"]["y"], color="#059669", lw=2.4,
            label=f"WITH Radial-Ring MIMO KMODE=0 (+{m_pi['mimo']['overshoot_pct']:.1f}% pk, settle {m_pi['mimo']['t_settle_5_ms']:.2f} ms)")
    ax.axhspan(0.95, 1.05, color="#94a3b8", alpha=0.16, label="±5% settling band")
    ax.axvline(0.0, color="#64748b", ls="--", lw=1.0)
    ax.axvline(1.0, color="#64748b", ls=":", lw=1.0)
    ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
    ax.set_xlim(-0.5, 11.0)
    ax.set_ylim(-0.08, 1.58)
    ax.set_xlabel("Time after DM step command [ms]")
    ax.set_ylabel("Projected physical OPD step (static = 1.0)")
    ax.set_title("(a) Interior Single-Actuator Poke (22, 23): Overshoot & Settling")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=8.2)

    # (b) Full-pupil 2D traveling wave dynamic residual RMS vs time
    ax = axes[0, 1]
    ax.plot(t_step_ms, m_pi["off"]["dyn_2d_norm_pct"], color="#dc2626", lw=2.2,
            label=f"WITHOUT pre-shaper (post-2 ms RMS: {m_pi['off']['full_wave_ring_pct']:.2f}%)")
    ax.plot(t_step_ms, m_pi["siso"]["dyn_2d_norm_pct"], color="#d97706", lw=2.0,
            label=f"WITH Uniform SISO (post-2 ms RMS: {m_pi['siso']['full_wave_ring_pct']:.2f}%, {m_pi['off']['full_wave_ring_pct']/m_pi['siso']['full_wave_ring_pct']:.2f}× cut)")
    ax.plot(t_step_ms, m_pi["mimo"]["dyn_2d_norm_pct"], color="#059669", lw=2.4,
            label=f"WITH Radial-Ring MIMO (post-2 ms RMS: {m_pi['mimo']['full_wave_ring_pct']:.2f}%, {m_pi['off']['full_wave_ring_pct']/m_pi['mimo']['full_wave_ring_pct']:.2f}× cut)")
    ax.axvline(2.0, color="#64748b", ls=":", lw=1.0, label="Post-rise wave window (t ≥ 2.0 ms)")
    ax.set_xlim(1.0, 18.0)
    ax.set_ylim(0.0, 60.0)
    ax.set_xlabel("Time after DM step command [ms]")
    ax.set_ylabel("2D wave residual ‖OPD(t)−OPD_static‖ / ‖OPD_static‖ [%]", fontsize=9.0)
    ax.set_title("(b) Full-Pupil 2D Circular Plate Wave Energy vs. Time")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.2)

    # (c) Free-Rim Actuator (57, 31) generalization with Universal SISO KMODE=2
    ax = axes[1, 0]
    ax.plot(t_step_ms, m_pr["off"]["y"], color="#dc2626", lw=2.2,
            label=f"Rim (57,31) WITHOUT (+{m_pr['off']['overshoot_pct']:.1f}% pk, 2D wave {m_pr['off']['full_wave_ring_pct']:.1f}%)")
    ax.plot(t_step_ms, m_pr["siso"]["y"], color="#059669", lw=2.4,
            label=f"Rim (57,31) WITH Universal SISO (+{m_pr['siso']['overshoot_pct']:.1f}% pk, 2D wave {m_pr['siso']['full_wave_ring_pct']:.1f}%)")
    ax.axhspan(0.95, 1.05, color="#94a3b8", alpha=0.16)
    ax.axvline(0.0, color="#64748b", ls="--", lw=1.0)
    ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
    ax.set_xlim(-0.5, 11.0)
    ax.set_ylim(-0.08, 1.62)
    ax.set_xlabel("Time after DM step command [ms]")
    ax.set_ylabel("Projected physical OPD step (static = 1.0)")
    ax.set_title("(c) Free-Rim Actuator (57, 31): Universal 1-Kernel SISO Broadcast")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=8.2)

    # (d) Temporal PSD of dynamic residual for Interior Poke (22, 23)
    ax = axes[1, 1]
    ax.plot(m_pi["off"]["freqs"], m_pi["off"]["psd_db"], color="#dc2626", lw=2.1, label="WITHOUT pre-shaper")
    ax.plot(m_pi["siso"]["freqs"], m_pi["siso"]["psd_db"], color="#d97706", lw=1.9, label="WITH Uniform SISO (KMODE 2)")
    ax.plot(m_pi["mimo"]["freqs"], m_pi["mimo"]["psd_db"], color="#059669", lw=2.3, label="WITH Radial-Ring MIMO (KMODE 0)")
    ax.axvline(1000.0, color="#64748b", ls=":", lw=1.1, label="Plate fundamental f₀ = 1,000 Hz")
    ax.set_xlim(50.0, 2800.0)
    ax.set_ylim(-68.0, -5.0)
    ax.set_xlabel("Temporal frequency f [Hz]")
    ax.set_ylabel("Dynamic residual amplitude [dB rel. static]")
    ax.set_title("(d) Post-Step Vibration Spectrum on (22, 23)")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.3)

    fig.suptitle(
        "Example 1 — Single-Actuator Zonal Pokes on Live GPU 64×64 ALPAO Plate DM (8 kHz Pre-Shaper)",
        fontsize=12.8,
        fontweight="bold",
    )
    fig.savefig(out_dir / "fig2a_single_poke_dynamics.png", dpi=165)
    plt.close(fig)

    # =========================================================================
    # FIGURE 2b: 2D Facesheet Circular Traveling Wave Contact Sheet (3 x 6)
    # =========================================================================
    snaps_ms = [1.50, 2.00, 2.75, 3.75, 5.25, 8.00]
    static_pi = m_pi["off"]["static_opd"]
    vmax_wave = float(np.percentile(np.abs((o_pi_off[28:72] - static_pi[None])[:, pup]), 99.6)) * 1e3  # nm
    fig, axes = plt.subplots(3, len(snaps_ms), figsize=(14.5, 7.6), constrained_layout=True)
    row_specs = [
        ("WITHOUT Pre-Shaper\n(Raw Step)", o_pi_off),
        ("WITH Uniform SISO\n(KMODE 2 Broadcast)", o_pi_siso),
        ("WITH Radial-Ring MIMO\n(KMODE 0 Wave-Cancel)", o_pi_mimo),
    ]
    im_last = None
    for r, (rlabel, cube) in enumerate(row_specs):
        for c, tms in enumerate(snaps_ms):
            ax = axes[r, c]
            idx = Q0_STEP + int(round(tms / DT_MS))
            dyn_nm = np.where(pup, (cube[idx] - static_pi) * 1.0e3, np.nan)
            im_last = ax.imshow(
                dyn_nm,
                cmap="RdBu_r",
                vmin=-vmax_wave,
                vmax=vmax_wave,
                origin="lower",
                interpolation="nearest",
            )
            ax.set_facecolor("#f1f5f9")
            ax.set_xticks([])
            ax.set_yticks([])
            if r == 0:
                ax.set_title(f"t = +{tms:.2f} ms", fontsize=10.5)
            if c == 0:
                ax.set_ylabel(rlabel, fontsize=9.5, fontweight="bold")
            # Annotate per-frame 2D dynamic RMS inside top-left corner
            frm_rms = float(np.sqrt(np.mean(((cube[idx] - static_pi)[pup]) ** 2))) * 1.0e3
            ax.text(
                6,
                14,
                f"{frm_rms:.1f} nm",
                color="#0f172a",
                fontsize=8.2,
                fontweight="bold",
                bbox={"facecolor": "white", "alpha": 0.80, "edgecolor": "none", "pad": 1.6},
            )
    assert im_last is not None
    fig.colorbar(im_last, ax=axes[:, -1], shrink=0.92, label="Dynamic OPD wave residual [nm]")
    fig.suptitle(
        "2D Physical DM Surface Traveling Wave OPD(t) − OPD_static After Single-Actuator Poke (22, 23)",
        fontsize=12.8,
        fontweight="bold",
    )
    fig.savefig(out_dir / "fig2b_single_poke_wave_sheet.png", dpi=165)
    plt.close(fig)

    # =========================================================================
    # FIGURE 3: Low-Order Zernike Modal Step Pokes (28x28 MIMO)
    # =========================================================================
    fig, axes = plt.subplots(2, 2, figsize=(14.2, 9.4), constrained_layout=True)

    # (a) Z4 Focus
    ax = axes[0, 0]
    ax.plot(t_step_ms, m_zf["off"]["y"], color="#dc2626", lw=2.2,
            label=f"WITHOUT (+{m_zf['off']['overshoot_pct']:.1f}% pk, ring {m_zf['off']['ring_proj_pct']:.1f}%, settle {m_zf['off']['t_settle_5_ms']:.1f} ms)")
    ax.plot(t_step_ms, m_zf["mimo"]["y"], color="#059669", lw=2.4,
            label=f"WITH 28×28 MIMO (+{m_zf['mimo']['overshoot_pct']:.1f}% pk, ring {m_zf['mimo']['ring_proj_pct']:.1f}%, settle {m_zf['mimo']['t_settle_5_ms']:.1f} ms)")
    ax.axhspan(0.95, 1.05, color="#94a3b8", alpha=0.16)
    ax.axvline(0.0, color="#64748b", ls="--", lw=1.0)
    ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
    ax.set_xlim(-0.5, 18.0)
    ax.set_ylim(-0.10, 1.98)
    ax.set_xlabel("Time after DM step command [ms]")
    ax.set_ylabel("Projected Focus Z4 OPD step (static = 1.0)")
    ax.set_title("(a) Zernike Focus (Z4) Standing-Wave Ringing Suppression")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=8.1)

    # (b) Z5 Astigmatism
    ax = axes[0, 1]
    ax.plot(t_step_ms, m_za["off"]["y"], color="#dc2626", lw=2.2,
            label=f"WITHOUT (+{m_za['off']['overshoot_pct']:.1f}% pk, ring {m_za['off']['ring_proj_pct']:.1f}%, settle {m_za['off']['t_settle_5_ms']:.1f} ms)")
    ax.plot(t_step_ms, m_za["mimo"]["y"], color="#059669", lw=2.4,
            label=f"WITH 28×28 MIMO (+{m_za['mimo']['overshoot_pct']:.1f}% pk, ring {m_za['mimo']['ring_proj_pct']:.1f}%, settle {m_za['mimo']['t_settle_5_ms']:.1f} ms)")
    ax.axhspan(0.95, 1.05, color="#94a3b8", alpha=0.16)
    ax.axvline(0.0, color="#64748b", ls="--", lw=1.0)
    ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
    ax.set_xlim(-0.5, 18.0)
    ax.set_ylim(-0.10, 1.98)
    ax.set_xlabel("Time after DM step command [ms]")
    ax.set_ylabel("Projected Astigmatism Z5 OPD step (static = 1.0)")
    ax.set_title("(b) Zernike Astigmatism (Z5) Standing-Wave Ringing Suppression")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=8.1)

    # (c) Full-pupil 2D dynamic OPD error ||OPD(t) - OPD_static||_RMS for Focus Z4 & Astigmatism Z5
    ax = axes[1, 0]
    ax.plot(t_step_ms, m_zf["off"]["dyn_2d_norm_pct"], color="#dc2626", lw=2.1,
            label=f"Focus Z4 WITHOUT (post-2 ms 2D RMS: {m_zf['off']['full_wave_ring_pct']:.1f}%)")
    ax.plot(t_step_ms, m_zf["mimo"]["dyn_2d_norm_pct"], color="#059669", lw=2.3,
            label=f"Focus Z4 WITH 28×28 MIMO (RMS: {m_zf['mimo']['full_wave_ring_pct']:.1f}%, {m_zf['off']['full_wave_ring_pct']/m_zf['mimo']['full_wave_ring_pct']:.1f}× cut)")
    ax.plot(t_step_ms, m_za["off"]["dyn_2d_norm_pct"], color="#f97316", ls="--", lw=1.8,
            label=f"Astigmatism Z5 WITHOUT (RMS: {m_za['off']['full_wave_ring_pct']:.1f}%)")
    ax.plot(t_step_ms, m_za["mimo"]["dyn_2d_norm_pct"], color="#2563eb", ls="--", lw=2.0,
            label=f"Astigmatism Z5 WITH 28×28 MIMO (RMS: {m_za['mimo']['full_wave_ring_pct']:.1f}%, {m_za['off']['full_wave_ring_pct']/m_za['mimo']['full_wave_ring_pct']:.1f}× cut)")
    ax.axvline(2.0, color="#64748b", ls=":", lw=1.0)
    ax.set_xlim(1.0, 18.0)
    ax.set_ylim(0.0, 92.0)
    ax.set_xlabel("Time after DM step command [ms]")
    ax.set_ylabel("Full-pupil 2D wave residual ‖OPD(t)−OPD_static‖ [%]")
    ax.set_title("(c) Full-Pupil 2D Dynamic Surface Residual vs. Time (Z4 & Z5)")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.0)

    # (d) Vibration PSD for Focus Z4 and Astigmatism Z5
    ax = axes[1, 1]
    ax.plot(m_zf["off"]["freqs"], m_zf["off"]["psd_db"], color="#dc2626", lw=2.1, label="Focus Z4 WITHOUT")
    ax.plot(m_zf["mimo"]["freqs"], m_zf["mimo"]["psd_db"], color="#059669", lw=2.3, label="Focus Z4 WITH 28×28 MIMO")
    ax.plot(m_za["off"]["freqs"], m_za["off"]["psd_db"], color="#f97316", ls="--", lw=1.8, label="Astigmatism Z5 WITHOUT")
    ax.plot(m_za["mimo"]["freqs"], m_za["mimo"]["psd_db"], color="#2563eb", ls="--", lw=2.0, label="Astigmatism Z5 WITH 28×28 MIMO")
    ax.axvline(1000.0, color="#64748b", ls=":", lw=1.1, label="Plate fundamental f₀ = 1,000 Hz")
    ax.set_xlim(50.0, 2800.0)
    ax.set_ylim(-60.0, 5.0)
    ax.set_xlabel("Temporal frequency f [Hz]")
    ax.set_ylabel("Post-step ringing amplitude [dB rel. static]")
    ax.set_title("(d) Modal Standing-Wave Resonance Spectrum (1 kHz Peak Crushed)")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.2)

    fig.suptitle(
        "Example 2 — Low-Order Zernike Modal Step Pokes (8 kHz 28×28 MIMO Pre-Shaper)",
        fontsize=12.8,
        fontweight="bold",
    )
    fig.savefig(out_dir / "fig3_modal_poke_comparison.png", dpi=165)
    plt.close(fig)

    # =========================================================================
    # FIGURE 4: ~500 Hz Fast-Modulated Astrogrid WITH vs WITHOUT Pre-Shaper
    # =========================================================================
    t_ag_ms = np.arange(N_AG) * DT_MS
    t_on, t_off = T_ON_AG, T_OFF_AG

    def _analyze_astro(
        opd_off: np.ndarray,
        runs: dict[str, tuple[np.ndarray, np.ndarray]],
        is_quad: bool = False,
    ) -> dict[str, Any]:
        _, _, vt = np.linalg.svd(opd_off[T_MOD0_AG:t_off, pup], full_matrices=False)
        pat0 = vt[0]
        pat1 = vt[1]
        # Align sign with first positive half-cycle (~1.25 ms after t_on)
        if float(opd_off[t_on + 10, pup] @ pat0) < 0.0:
            pat0 = -pat0
        out_r: dict[str, Any] = {}
        sqrt_n = float(np.sqrt(pup.sum()))
        for tag, (disp, opd) in runs.items():
            proj0 = (opd[:, pup] @ pat0) * 1.0e3 / sqrt_n
            proj1 = (opd[:, pup] @ pat1) * 1.0e3 / sqrt_n
            rms_tot = np.sqrt(np.mean(opd[:, pup] ** 2, axis=1)) * 1.0e3
            if is_quad:
                recon = np.outer(opd[:, pup] @ pat0, pat0) + np.outer(opd[:, pup] @ pat1, pat1)
            else:
                recon = np.outer(opd[:, pup] @ pat0, pat0)
            orth_rms = np.sqrt(np.mean((opd[:, pup] - recon) ** 2, axis=1)) * 1.0e3

            # Exact integer-cycle FFT on [32:208] = 176 ticks = 11 full 500 Hz cycles at 8 kHz!
            seg = proj0[T_MOD0_AG:t_off]
            freqs = np.fft.rfftfreq(len(seg), d=DT_SEC)
            spec = np.abs(np.fft.rfft(seg)) * (2.0 / len(seg))
            i500 = int(np.argmin(np.abs(freqs - 500.0)))
            i1500 = int(np.argmin(np.abs(freqs - 1500.0)))
            a500 = float(spec[i500])
            a1500 = float(spec[i1500])

            # Turn-off mechanical ring-down (after 1.5 ms transport+settling: ticks 220..320)
            rd_rms = float(np.sqrt(np.mean(rms_tot[T_RD0_AG:] ** 2)))
            rd_pk = float(np.max(rms_tot[T_RD0_AG:]))
            mod_pk = float(np.max(np.abs(proj0[T_MOD0_AG:t_off])))
            out_r[tag] = {
                "proj0_nm": proj0,
                "proj1_nm": proj1,
                "rms_tot_nm": rms_tot,
                "orth_rms_nm": orth_rms,
                "freqs": freqs,
                "spec_nm": spec,
                "a500_nm": a500,
                "a1500_nm": a1500,
                "ratio_3_1": a1500 / max(a500, 1e-6),
                "mod_pk_nm": mod_pk,
                "orth_mean_nm": float(np.mean(orth_rms[T_MOD0_AG:t_off])),
                "ringdown_rms_nm": rd_rms,
                "ringdown_pk_nm": rd_pk,
                "cmd_pk_um": float(np.max(np.abs(disp))),
            }
        return out_r

    m_ag_sq = _analyze_astro(
        o_ag_off,
        {"off": (d_ag_off, o_ag_off), "siso": (d_ag_siso, o_ag_siso), "mimo": (d_ag_mimo, o_ag_mimo)},
    )
    m_ag_k10 = _analyze_astro(
        o_ak_off,
        {"off": (d_ak_off, o_ak_off), "mimo": (d_ak_mimo, o_ak_mimo)},
    )
    m_ag_quad = _analyze_astro(
        o_aq_off,
        {"off": (d_aq_off, o_aq_off), "mimo": (d_aq_mimo, o_aq_mimo)},
        is_quad=True,
    )

    # Ideal delayed square-wave reference (shifted by 1.0 ms = DELAY_TICKS ticks)
    ideal_flat_nm = m_ag_sq["mimo"]["a500_nm"] * (np.pi / 4.0)
    raw_sched_amp = np.array(calib_meta["schedules"]["astro_500hz_sq"]["target_amp"], dtype=np.float64) / 0.25
    ideal_sq_nm = np.zeros(N_AG, dtype=np.float64)
    ideal_sq_nm[DELAY_TICKS:] = raw_sched_amp[:-DELAY_TICKS] * ideal_flat_nm
    for tag in ("off", "siso", "mimo"):
        err_sq = float(np.sqrt(np.mean((m_ag_sq[tag]["proj0_nm"][T_MOD0_AG:t_off] - ideal_sq_nm[T_MOD0_AG:t_off]) ** 2)))
        m_ag_sq[tag]["track_err_nm"] = err_sq

    fig, axes = plt.subplots(2, 2, figsize=(14.4, 9.8), constrained_layout=True)

    # (a) Full 40 ms burst: Turn-On -> 12 cycles @ 500 Hz -> Turn-Off Ring-Down
    ax = axes[0, 0]
    ax.axvspan(t_on * DT_MS, t_off * DT_MS, color="#eff6ff", alpha=0.65, label="500 Hz modulation ON (12 cycles)")
    ax.axvspan(t_off * DT_MS, 40.0, color="#fef2f2", alpha=0.45, label="Turn-off ring-down window")
    ax.plot(t_ag_ms, ideal_sq_nm, color="#0f172a", ls=":", lw=1.2, alpha=0.85, label="Ideal delayed ±A square wave")
    ax.plot(t_ag_ms, m_ag_sq["off"]["proj0_nm"], color="#dc2626", lw=1.7, alpha=0.92,
            label=f"WITHOUT (pk {m_ag_sq['off']['mod_pk_nm']:.0f} nm, ring-down {m_ag_sq['off']['ringdown_rms_nm']:.1f} nm)")
    ax.plot(t_ag_ms, m_ag_sq["mimo"]["proj0_nm"], color="#059669", lw=2.0,
            label=f"WITH Astrogrid MIMO (pk {m_ag_sq['mimo']['mod_pk_nm']:.0f} nm, ring-down {m_ag_sq['mimo']['ringdown_rms_nm']:.1f} nm)")
    ax.set_xlim(0.0, 40.0)
    ax.set_ylim(-390.0, 390.0)
    ax.set_xlabel("Time [ms]")
    ax.set_ylabel("Astrogrid k=8 modal OPD [nm RMS]")
    ax.set_title("(a) 500 Hz Polarity-Flipping Astrogrid Burst: Turn-On, Modulation & Turn-Off")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=7.9)

    # (b) Zoomed 3-cycle window (10 - 16 ms) + shaped 8 kHz DM command trace
    ax = axes[0, 1]
    ax.step(t_ag_ms, ideal_sq_nm, where="mid", color="#0f172a", ls=":", lw=1.5, label="Ideal delayed target (±A)")
    ax.plot(t_ag_ms, m_ag_sq["off"]["proj0_nm"], "o-", color="#dc2626", ms=2.6, lw=1.8,
            label=f"WITHOUT (track err {m_ag_sq['off']['track_err_nm']:.1f} nm)")
    ax.plot(t_ag_ms, m_ag_sq["siso"]["proj0_nm"], color="#d97706", ls="--", lw=1.6,
            label=f"WITH Uniform SISO (track err {m_ag_sq['siso']['track_err_nm']:.1f} nm)")
    ax.plot(t_ag_ms, m_ag_sq["mimo"]["proj0_nm"], "s-", color="#059669", ms=2.6, lw=2.2,
            label=f"WITH Astrogrid MIMO (track err {m_ag_sq['mimo']['track_err_nm']:.1f} nm)")
    astro20 = fits.getdata(raw_dir / "astro20_modes.fits").astype(np.float64)
    a0_flat = astro20[0].ravel()
    w_a0 = a0_flat / float(np.dot(a0_flat, a0_flat))
    u_mimo_mod = (d_ag_mimo.reshape(N_AG, -1) @ w_a0)
    ax2 = ax.twinx()
    ax2.step(t_ag_ms, u_mimo_mod, where="post", color="#2563eb", alpha=0.45, lw=1.4, label="8 kHz shaped DM cmd [μm]")
    ax2.set_ylabel("8 kHz shaped DM command [μm]", color="#2563eb")
    ax2.tick_params(axis="y", labelcolor="#2563eb")
    ax2.set_ylim(-0.48, 0.48)
    ax.set_xlim(10.0, 16.0)
    ax.set_ylim(-390.0, 390.0)
    ax.set_xlabel("Time [ms] (zoomed 3 full 500 Hz cycles)")
    ax.set_ylabel("Astrogrid k=8 physical OPD [nm RMS]")
    ax.set_title("(b) Sub-Millisecond 8 kHz Command Shaping vs. Physical DM Surface")
    ax.grid(True)
    ax.legend(loc="upper left", frameon=True, facecolor="white", fontsize=8.0)

    # (c) Temporal amplitude spectrum during 500 Hz modulation
    ax = axes[1, 0]
    f_sp = m_ag_sq["off"]["freqs"]
    w_bar = 44.0
    ag_1500_title = m_ag_sq["off"]["a1500_nm"] / max(m_ag_sq["mimo"]["a1500_nm"], 1e-6)
    ax.bar(f_sp - w_bar, m_ag_sq["off"]["spec_nm"], width=w_bar, color="#dc2626", alpha=0.88,
           label=f"WITHOUT (1.5 kHz = {m_ag_sq['off']['a1500_nm']:.1f} nm, 3rd/1st = {m_ag_sq['off']['ratio_3_1']:.2f})")
    ax.bar(f_sp, m_ag_sq["siso"]["spec_nm"], width=w_bar, color="#d97706", alpha=0.85,
           label=f"WITH Uniform SISO (1.5 kHz = {m_ag_sq['siso']['a1500_nm']:.1f} nm)")
    ax.bar(f_sp + w_bar, m_ag_sq["mimo"]["spec_nm"], width=w_bar, color="#059669", alpha=0.92,
           label=f"WITH Astrogrid MIMO (1.5 kHz = {m_ag_sq['mimo']['a1500_nm']:.1f} nm, 3rd/1st = {m_ag_sq['mimo']['ratio_3_1']:.2f})")
    ax.axvline(1567.0, color="#1e40af", ls="--", lw=1.2, label="Plate resonance f_res(k=8) = 1,567 Hz")
    ax.set_xlim(0.0, 3050.0)
    ax.set_ylim(0.0, 355.0)
    ax.set_xlabel("Temporal frequency f [Hz]")
    ax.set_ylabel("Fourier amplitude [nm RMS]")
    ax.set_title(f"(c) 500 Hz Astrogrid Spectrum (8 kHz): 1.5 kHz Resonance Crushed {ag_1500_title:.1f}×")
    ax.grid(True, axis="y")
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=7.8)

    # (d) Summary across 3 Astrogrid regimes (1.5 kHz vibration & Turn-Off Ring-Down)
    ax = axes[1, 1]
    regimes = [
        "500 Hz Sq.\nk=8 (1.5 kHz)",
        "500 Hz Sq.\nk=8 (Ring-dn)",
        "500 Hz Quad.\nk=8 (1.5 kHz)",
        "500 Hz Quad.\nk=8 (Ring-dn)",
        "500 Hz Sq.\nk=10 (1.5 kHz)",
        "500 Hz Sq.\nk=10 (Ring-dn)",
    ]
    v_off = [
        m_ag_sq["off"]["a1500_nm"],
        m_ag_sq["off"]["ringdown_rms_nm"],
        m_ag_quad["off"]["a1500_nm"],
        m_ag_quad["off"]["ringdown_rms_nm"],
        m_ag_k10["off"]["a1500_nm"],
        m_ag_k10["off"]["ringdown_rms_nm"],
    ]
    v_on = [
        m_ag_sq["mimo"]["a1500_nm"],
        m_ag_sq["mimo"]["ringdown_rms_nm"],
        m_ag_quad["mimo"]["a1500_nm"],
        m_ag_quad["mimo"]["ringdown_rms_nm"],
        m_ag_k10["mimo"]["a1500_nm"],
        m_ag_k10["mimo"]["ringdown_rms_nm"],
    ]
    x_pos = np.arange(len(regimes))
    bw = 0.36
    b1 = ax.bar(x_pos - bw / 2, v_off, width=bw, color="#dc2626", alpha=0.88, label="WITHOUT Pre-Shaper")
    b2 = ax.bar(x_pos + bw / 2, v_on, width=bw, color="#059669", alpha=0.92, label="WITH Astrogrid MIMO Pre-Shaper")
    for idx_b, (vo, vn) in enumerate(zip(v_off, v_on)):
        fac = vo / max(vn, 1e-6)
        ax.text(
            idx_b,
            max(vo, vn) + 5.0,
            f"{fac:.1f}×",
            ha="center",
            va="bottom",
            fontsize=8.8,
            fontweight="bold",
            color="#0f172a",
        )
    ax.set_xticks(x_pos)
    ax.set_xticklabels(regimes, fontsize=8.4)
    ax.set_ylim(0.0, max(v_off) * 1.18)
    ax.set_ylabel("Vibration / Ring-Down Amplitude [nm RMS]")
    ax.set_title("(d) Mechanical Vibration Reduction Across 500 Hz Astrogrid Regimes")
    ax.grid(True, axis="y")
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.5)

    fig.suptitle(
        "Example 3 — 500 Hz Fast-Modulated Astrogrid on Subaru AO3k 64×64 ALPAO Plate DM (WITH vs. WITHOUT)",
        fontsize=12.8,
        fontweight="bold",
    )
    fig.savefig(out_dir / "fig4_astrogrid_500hz_comparison.png", dpi=165)
    plt.close(fig)

    # =========================================================================
    # FIGURE 5: H-Band (1.65 um) Lyot Coronagraphic Focal-Plane PSF Impact
    # =========================================================================
    coro = _build_lyot_coronagraph(pup_2d, lambda_um=1.65)
    psf_off_cube = _propagate_coro_cube(o_ag_off, coro)
    psf_mimo_cube = _propagate_coro_cube(o_ag_mimo, coro)

    # Average during steady 500 Hz modulation [32:208]
    psf_off_avg = np.mean(psf_off_cube[T_MOD0_AG:t_off], axis=0)
    psf_mimo_avg = np.mean(psf_mimo_cube[T_MOD0_AG:t_off], axis=0)
    # Also average during post-turn-off ring-down [220:320] (where dark hole should be clean!)
    psf_off_rd = np.mean(psf_off_cube[T_RD0_AG:], axis=0)
    psf_mimo_rd = np.mean(psf_mimo_cube[T_RD0_AG:], axis=0)

    r_ld = coro["r_ld_crop"]
    x_ld = coro["x_ld_crop"]
    y_ld = coro["y_ld_crop"]

    # Satellite spot aperture around (+8, 0) lambda/D (radius 1.2 lambda/D)
    spot_ap = (np.hypot(x_ld - 8.0, y_ld) <= 1.2)
    spot_flux_off = np.mean(psf_off_cube[:, spot_ap], axis=1)
    spot_flux_mimo = np.mean(psf_mimo_cube[:, spot_ap], axis=1)
    spot_pk_off = float(np.max(spot_flux_off[T_MOD0_AG:t_off]))
    spot_pk_mimo = float(np.max(spot_flux_mimo[T_MOD0_AG:t_off]))
    spot_mean_off = float(np.mean(spot_flux_off[T_MOD0_AG:t_off]))
    spot_mean_mimo = float(np.mean(spot_flux_mimo[T_MOD0_AG:t_off]))
    spot_ghost_off = float(np.mean(spot_flux_off[T_RD0_AG:]))
    spot_ghost_mimo = float(np.mean(spot_flux_mimo[T_RD0_AG:]))
    spot_ghost_gain_x = spot_ghost_off / max(spot_ghost_mimo, 1e-12)
    spot_cv_off_pct = float(np.std(spot_flux_off[T_MOD0_AG:t_off]) / max(spot_mean_off, 1e-12) * 100.0)
    spot_cv_mimo_pct = float(np.std(spot_flux_mimo[T_MOD0_AG:t_off]) / max(spot_mean_mimo, 1e-12) * 100.0)

    # 2nd-order harmonic / cross-term spurious spots at (+-16, 0), (0, +-16), (+-8, +-8) lambda/D
    spurious_mask = (
        (np.hypot(x_ld - 8.0, y_ld - 8.0) <= 1.4)
        | (np.hypot(x_ld + 8.0, y_ld - 8.0) <= 1.4)
        | (np.hypot(x_ld - 8.0, y_ld + 8.0) <= 1.4)
        | (np.hypot(x_ld + 8.0, y_ld + 8.0) <= 1.4)
        | (np.hypot(x_ld - 16.0, y_ld) <= 1.4)
        | (np.hypot(x_ld + 16.0, y_ld) <= 1.4)
        | (np.hypot(x_ld, y_ld - 16.0) <= 1.4)
        | (np.hypot(x_ld, y_ld + 16.0) <= 1.4)
    )
    # Dark-hole mask excluding the 4 primary satellite spots at (+-8, 0), (0, +-8)
    sat4_mask = (
        (np.hypot(x_ld - 8.0, y_ld) <= 2.2)
        | (np.hypot(x_ld + 8.0, y_ld) <= 2.2)
        | (np.hypot(x_ld, y_ld - 8.0) <= 2.2)
        | (np.hypot(x_ld, y_ld + 8.0) <= 2.2)
    )
    dh_mask = (r_ld >= 4.0) & (r_ld <= 18.0) & (~sat4_mask)
    dh_mod_off = float(np.mean(psf_off_avg[dh_mask]))
    dh_mod_mimo = float(np.mean(psf_mimo_avg[dh_mask]))
    dh_rd_off = float(np.mean(psf_off_rd[dh_mask]))
    dh_rd_mimo = float(np.mean(psf_mimo_rd[dh_mask]))
    spur_off = float(np.mean(psf_off_avg[spurious_mask]))
    spur_mimo = float(np.mean(psf_mimo_avg[spurious_mask]))

    # Azimuthally averaged radial contrast (excluding 4 primary spots)
    r_bins = np.arange(3.5, 22.5, 0.75)
    r_cent = 0.5 * (r_bins[:-1] + r_bins[1:])
    prof_mod_off, prof_mod_mimo, prof_rd_off, prof_rd_mimo = [], [], [], []
    for r0, r1 in zip(r_bins[:-1], r_bins[1:]):
        ann = (r_ld >= r0) & (r_ld < r1) & (~sat4_mask)
        prof_mod_off.append(float(np.mean(psf_off_avg[ann])))
        prof_mod_mimo.append(float(np.mean(psf_mimo_avg[ann])))
        prof_rd_off.append(float(np.mean(psf_off_rd[ann])))
        prof_rd_mimo.append(float(np.mean(psf_mimo_rd[ann])))

    fig, axes = plt.subplots(2, 2, figsize=(14.0, 10.0), constrained_layout=True)

    # (a) Average H-Band Coronagraphic PSF WITHOUT Pre-Shaper
    ax = axes[0, 0]
    im_c1 = ax.imshow(
        np.log10(np.maximum(psf_off_avg, 1e-7)),
        cmap="inferno",
        vmin=-6.5,
        vmax=-1.8,
        origin="lower",
        extent=coro["extent_ld"],
    )
    ax.set_xlabel("Δx [λ/D]")
    ax.set_ylabel("Δy [λ/D]")
    ax.set_title(f"(a) H-Band Coronagraphic PSF — WITHOUT Pre-Shaper\n(Spurious 2nd-order spots: {spur_off:.1e}, DH: {dh_mod_off:.1e})")
    fig.colorbar(im_c1, ax=ax, label="log₁₀ Contrast", shrink=0.88)

    # (b) Average H-Band Coronagraphic PSF WITH Pre-Shaper
    ax = axes[0, 1]
    im_c2 = ax.imshow(
        np.log10(np.maximum(psf_mimo_avg, 1e-7)),
        cmap="inferno",
        vmin=-6.5,
        vmax=-1.8,
        origin="lower",
        extent=coro["extent_ld"],
    )
    ax.set_xlabel("Δx [λ/D]")
    ax.set_ylabel("Δy [λ/D]")
    ax.set_title(
        f"(b) H-Band Coronagraphic PSF — WITH Pre-Shaper\n"
        f"(Spurious spots {spur_off/max(spur_mimo,1e-12):.1f}× fainter, DH {dh_mod_off/max(dh_mod_mimo,1e-12):.1f}× cleaner)"
    )
    fig.colorbar(im_c2, ax=ax, label="log₁₀ Contrast", shrink=0.88)

    # (c) Instantaneous Satellite-Spot Photometric Stability vs Time
    ax = axes[1, 0]
    ax.axvspan(t_on * DT_MS, t_off * DT_MS, color="#eff6ff", alpha=0.55)
    ax.axvspan(t_off * DT_MS, 40.0, color="#fef2f2", alpha=0.45)
    ax.plot(t_ag_ms, spot_flux_off * 1e3, color="#dc2626", lw=1.7,
            label=f"WITHOUT (pk {spot_pk_off*1e3:.1f}×10⁻³, post-off ghost {spot_ghost_off*1e3:.2f}×10⁻³)")
    ax.plot(t_ag_ms, spot_flux_mimo * 1e3, color="#059669", lw=2.1,
            label=f"WITH Astrogrid MIMO (flat pk {spot_pk_mimo*1e3:.1f}×10⁻³, ghost {spot_ghost_gain_x:.0f}× lower)")
    ax.set_xlim(0.0, 40.0)
    ax.set_xlabel("Time [ms]")
    ax.set_ylabel("(+8, 0) λ/D Satellite Spot Mean Contrast [×10⁻³]")
    ax.set_title("(c) Instantaneous Astrometric Satellite-Spot Photometry (8 kHz)")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.1)

    # (d) Radial Dark-Hole Contrast Profiles (Modulation & Turn-Off Ring-Down)
    ax = axes[1, 1]
    ax.semilogy(r_cent, prof_mod_off, color="#dc2626", lw=2.1,
                label=f"500 Hz Mod — WITHOUT (4–18 λ/D avg: {dh_mod_off:.2e})")
    ax.semilogy(r_cent, prof_mod_mimo, color="#059669", lw=2.3,
                label=f"500 Hz Mod — WITH Pre-Shaper (avg: {dh_mod_mimo:.2e}, {dh_mod_off/max(dh_mod_mimo,1e-12):.1f}× better)")
    ax.semilogy(r_cent, prof_rd_off, color="#dc2626", ls="--", lw=1.8,
                label=f"Turn-Off Ring-Down — WITHOUT (avg: {dh_rd_off:.2e})")
    ax.semilogy(r_cent, prof_rd_mimo, color="#059669", ls="--", lw=2.0,
                label=f"Turn-Off Ring-Down — WITH Pre-Shaper (avg: {dh_rd_mimo:.2e}, {dh_rd_off/max(dh_rd_mimo,1e-12):.1f}× better)")
    ax.set_xlim(3.5, 22.0)
    ax.set_ylim(1e-7, 8e-3)
    ax.set_xlabel("Angular separation [λ/D] (excluding 4 primary spots)")
    ax.set_ylabel("Azimuthally averaged H-band raw contrast")
    ax.set_title("(d) H-Band Coronagraphic Dark-Hole Contrast Leakage From DM Ringing")
    ax.grid(True, which="both", alpha=0.55)
    ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=8.0)

    fig.suptitle(
        "Science Impact — H-Band (1.65 μm) Lyot Coronagraphic Focal Plane During 500 Hz Astrogrid Operation",
        fontsize=12.6,
        fontweight="bold",
    )
    fig.savefig(out_dir / "fig5_astrogrid_coronagraph_psf.png", dpi=165)
    plt.close(fig)

    # =========================================================================
    # VIDEO 1: Dedicated Single-Actuator Poke WITH vs WITHOUT (2x3 layout: Interior + Free Rim)
    # =========================================================================
    fps_p1 = 20.0  # 400x slow motion at 8 kHz (125 us/frame)
    ps = 264
    pad = 14
    hdr_h = 54
    sub_h = 30
    ftr_h = 32
    w_p1 = 3 * ps + 4 * pad
    h_p1 = hdr_h + 2 * (sub_h + ps + pad) + ftr_h
    w_p1 += w_p1 & 1
    h_p1 += h_p1 & 1

    f_hdr = _load_ttf(bold=True, size=15)
    f_sub = _load_ttf(bold=True, size=12)
    f_mono = _load_ttf(bold=True, mono=True, size=13)
    f_sm = _load_ttf(bold=False, size=11)
    f_smb = _load_ttf(bold=True, size=11)
    f_xs = _load_ttf(bold=True, size=10)

    def _draw_sparkline(
        dr: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        t_arr: np.ndarray,
        curves: list[tuple[np.ndarray, tuple[int, int, int]]],
        cur_idx: int,
        ymin: float,
        ymax: float,
        ylabel: str,
        ref_line: float | None = None,
        label_font: Any = None,
    ) -> None:
        x0, y0, x1, y1 = box
        dr.rectangle([x0, y0, x1, y1], fill=(248, 250, 252), outline=(203, 213, 225))
        top_pad = 18
        if ref_line is not None and ymin < ref_line < ymax:
            yr = int(y1 - 6 - (y1 - y0 - top_pad - 6) * ((ref_line - ymin) / (ymax - ymin)))
            dr.line([(x0 + 2, yr), (x1 - 2, yr)], fill=(148, 163, 184), width=1)
        elif ymin < 0.0 < ymax:
            yz = int(y1 - 6 - (y1 - y0 - top_pad - 6) * ((0.0 - ymin) / (ymax - ymin)))
            dr.line([(x0 + 2, yz), (x1 - 2, yz)], fill=(203, 213, 225), width=1)
        n = len(t_arr)
        for arr, col in curves:
            pts = []
            for i in range(n):
                px = x0 + 6 + int((x1 - x0 - 12) * (i / max(n - 1, 1)))
                val = float(np.clip(arr[i], ymin, ymax))
                py = y1 - 6 - int((y1 - y0 - top_pad - 6) * ((val - ymin) / max(ymax - ymin, 1e-9)))
                pts.append((px, py))
            if len(pts) >= 2:
                dr.line(pts, fill=col, width=2)
        cx = x0 + 6 + int((x1 - x0 - 12) * (cur_idx / max(n - 1, 1)))
        dr.line([(cx, y0 + top_pad), (cx, y1 - 2)], fill=(15, 23, 42), width=2)
        dr.rectangle([x0 + 1, y0 + 1, x1 - 1, y0 + top_pad - 1], fill=(241, 245, 249))
        dr.text((x0 + 6, y0 + 3), ylabel, fill=(30, 41, 59), font=(label_font or f_smb))

    ffmpeg = _find_ffmpeg()

    def _start_ffmpeg(out_mp4: Path, width: int, height: int, fps_val: float) -> subprocess.Popen[bytes]:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            f"{fps_val:.2f}",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            "-movflags",
            "+faststart",
            str(out_mp4),
        ]
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    poke_mp4 = out_dir / "dm_preshaper_single_poke_sbs.mp4"
    poke_poster = out_dir / "dm_preshaper_single_poke_sbs_poster.png"
    proc_p1 = _start_ffmpeg(poke_mp4, w_p1, h_p1, fps_p1)
    assert proc_p1.stdin is not None

    static_pr = m_pr["off"]["static_opd"]
    vmax_p1 = vmax_wave / 1.0e3  # um
    vmax_pr = float(np.percentile(np.abs((o_pr_off[28:72] - static_pr[None])[:, pup]), 99.6))
    p1_ticks = list(range(12, 180))  # 168 frames: t = -0.50 ms to +20.38 ms at 8 kHz (20 fps = 8.4 s)
    p1_poster_tick = 34  # t = +2.25 ms: dramatic outgoing circular wave + free-rim reflection

    pi_ov_mimo_vid = m_pi["off"]["overshoot_pct"] / max(m_pi["mimo"]["overshoot_pct"], 0.1)
    pr_ov_x_vid = m_pr["off"]["overshoot_pct"] / max(m_pr["siso"]["overshoot_pct"], 0.1)
    pi_w_mimo_e_vid = (m_pi["off"]["full_wave_ring_pct"] / max(m_pi["mimo"]["full_wave_ring_pct"], 0.01)) ** 2

    for k_idx, tk in enumerate(p1_ticks):
        im = Image.new("RGB", (w_p1, h_p1), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, w_p1, hdr_h], fill=(15, 23, 42))
        dr.text(
            (16, 17),
            "Single-Actuator Poke WITH vs. WITHOUT Pre-Shaper · 2D Plate Wave",
            fill=(248, 250, 252),
            font=f_hdr,
        )
        t_cur = (tk - Q0_STEP) * DT_MS
        dr.rectangle([w_p1 - 165, 11, w_p1 - 12, 42], fill=(30, 41, 59))
        dr.text((w_p1 - 154, 18), f"t = {t_cur:+6.2f} ms", fill=(56, 189, 248), font=f_mono)

        y_sub1 = hdr_h
        y_img1 = y_sub1 + sub_h + 6
        y_sub2 = hdr_h + (sub_h + ps + pad)
        y_img2 = y_sub2 + sub_h + 6
        dr.rectangle([0, y_sub1, w_p1, y_sub1 + sub_h], fill=(241, 245, 249))
        dr.rectangle([0, y_sub2, w_p1, y_sub2 + sub_h], fill=(241, 245, 249))

        frame_np = np.asarray(im, dtype=np.uint8).copy()
        # Row 1: Interior poke (22, 23) — OFF | Uniform SISO | Radial-Ring MIMO
        cubes_r1 = [o_pi_off, o_pi_siso, o_pi_mimo]
        for col_i in range(3):
            x0 = pad + col_i * (ps + pad)
            panel_rgb = _resize_rgb(_colorize_diverging(cubes_r1[col_i][tk] - static_pi, vmax_p1, pup), ps)
            frame_np[y_img1 : y_img1 + ps, x0 : x0 + ps] = panel_rgb
        # Row 2 cols 0 & 1: Free-rim poke (57, 31) — OFF | Universal SISO
        cubes_r2 = [o_pr_off, o_pr_siso]
        for col_i in range(2):
            x0 = pad + col_i * (ps + pad)
            panel_rgb = _resize_rgb(_colorize_diverging(cubes_r2[col_i][tk] - static_pr, vmax_pr, pup), ps)
            frame_np[y_img2 : y_img2 + ps, x0 : x0 + ps] = panel_rgb

        im = Image.fromarray(frame_np)
        dr = ImageDraw.Draw(im)

        titles_r1 = [
            (f"Interior (22,23) WITHOUT (+{m_pi['off']['overshoot_pct']:.1f}%)", (220, 38, 38)),
            (f"Interior WITH SISO (+{m_pi['siso']['overshoot_pct']:.1f}%)", (217, 119, 6)),
            (f"Interior WITH MIMO (+{m_pi['mimo']['overshoot_pct']:.1f}%)", (5, 150, 105)),
        ]
        for col_i, (tl, col) in enumerate(titles_r1):
            x0 = pad + col_i * (ps + pad)
            dr.text((x0 + 4, y_sub1 + 7), tl, fill=col, font=f_sub)
            frm_rms = float(np.sqrt(np.mean(((cubes_r1[col_i][tk] - static_pi)[pup]) ** 2))) * 1e3
            dr.rectangle([x0 + 6, y_img1 + 6, x0 + 114, y_img1 + 26], fill=(255, 255, 255))
            dr.text((x0 + 10, y_img1 + 9), f"Wave: {frm_rms:4.1f} nm", fill=col, font=f_smb)

        titles_r2 = [
            (f"Free Rim (57,31) WITHOUT (+{m_pr['off']['overshoot_pct']:.1f}%)", (220, 38, 38)),
            (f"Free Rim WITH SISO (+{m_pr['siso']['overshoot_pct']:.1f}%)", (5, 150, 105)),
            ("Live Step & 2D Wave Traces (22,23)", (15, 23, 42)),
        ]
        for col_i, (tl, col) in enumerate(titles_r2):
            x0 = pad + col_i * (ps + pad)
            dr.text((x0 + 4, y_sub2 + 7), tl, fill=col, font=f_sub)
        for col_i, col in enumerate([(220, 38, 38), (5, 150, 105)]):
            x0 = pad + col_i * (ps + pad)
            frm_rms = float(np.sqrt(np.mean(((cubes_r2[col_i][tk] - static_pr)[pup]) ** 2))) * 1e3
            dr.rectangle([x0 + 6, y_img2 + 6, x0 + 114, y_img2 + 26], fill=(255, 255, 255))
            dr.text((x0 + 10, y_img2 + 9), f"Wave: {frm_rms:4.1f} nm", fill=col, font=f_smb)

        # Row 2 col 2: Dual scrolling live trace panel (Top: Step Response, Bottom: 2D Wave RMS)
        x_tr = pad + 2 * (ps + pad)
        half_h = (ps - 10) // 2
        _draw_sparkline(
            dr,
            (x_tr, y_img2, x_tr + ps, y_img2 + half_h),
            np.array([(t - Q0_STEP) * DT_MS for t in p1_ticks]),
            [
                (m_pi["off"]["y"][p1_ticks], (220, 38, 38)),
                (m_pi["siso"]["y"][p1_ticks], (217, 119, 6)),
                (m_pi["mimo"]["y"][p1_ticks], (5, 150, 105)),
            ],
            k_idx,
            -0.05,
            1.58,
            "Step y(t): Red=OFF Amb=SISO Grn=MIMO",
            ref_line=1.0,
            label_font=f_xs,
        )
        _draw_sparkline(
            dr,
            (x_tr, y_img2 + half_h + 10, x_tr + ps, y_img2 + ps),
            np.array([(t - Q0_STEP) * DT_MS for t in p1_ticks]),
            [
                (m_pi["off"]["dyn_2d_norm_pct"][p1_ticks], (220, 38, 38)),
                (m_pi["siso"]["dyn_2d_norm_pct"][p1_ticks], (217, 119, 6)),
                (m_pi["mimo"]["dyn_2d_norm_pct"][p1_ticks], (5, 150, 105)),
            ],
            k_idx,
            0.0,
            62.0,
            "2D Wave Residual [% of static]",
            label_font=f_xs,
        )

        y_ftr = h_p1 - ftr_h
        dr.rectangle([0, y_ftr, w_p1, h_p1], fill=(248, 250, 252))
        dr.text(
            (16, y_ftr + 9),
            f"ALPAO 64×64 Plate DM (8 kHz, 400× slow-mo) · Overshoot cut: {pi_ov_mimo_vid:.1f}× MIMO / {pr_ov_x_vid:.1f}× rim SISO · 2D wave energy: {pi_w_mimo_e_vid:.0f}× cut",
            fill=(51, 65, 85),
            font=f_sm,
        )
        proc_p1.stdin.write(np.asarray(im, dtype=np.uint8).tobytes())
        if tk == p1_poster_tick:
            im.save(poke_poster)

    proc_p1.stdin.close()
    err_p1 = proc_p1.stderr.read() if proc_p1.stderr else b""
    rc_p1 = proc_p1.wait()
    if rc_p1 != 0:
        raise RuntimeError(f"ffmpeg single-poke video failed ({rc_p1}): {err_p1.decode(errors='ignore')}")

    # =========================================================================
    # VIDEO 2: Dedicated 500 Hz Astrogrid WITH vs WITHOUT + H-Band Coronagraphic PSF
    # =========================================================================
    fps_p2 = 24.0  # 333x slow motion at 8 kHz (125 us/frame)
    bar_h = 108
    w_p2 = 3 * ps + 4 * pad
    h_p2 = hdr_h + sub_h + ps + pad + bar_h + ftr_h
    w_p2 += w_p2 & 1
    h_p2 += h_p2 & 1

    astro_mp4 = out_dir / "dm_preshaper_astrogrid_500hz_sbs.mp4"
    astro_poster = out_dir / "dm_preshaper_astrogrid_500hz_sbs_poster.png"
    proc_p2 = _start_ffmpeg(astro_mp4, w_p2, h_p2, fps_p2)
    assert proc_p2.stdin is not None

    p2_ticks = list(range(8, 304))  # 296 frames: t = 1.00 to 38.00 ms at 8 kHz (24 fps = 12.3 s)
    vmax_ag_um = 0.36
    poster_tick = 52  # mid-modulation peak contrast moment (t = 6.50 ms)
    ag_1500_fac = m_ag_sq["off"]["a1500_nm"] / max(m_ag_sq["mimo"]["a1500_nm"], 1e-6)
    ag_rd_fac = m_ag_sq["off"]["ringdown_rms_nm"] / max(m_ag_sq["mimo"]["ringdown_rms_nm"], 1e-6)

    for k_idx, tk in enumerate(p2_ticks):
        im = Image.new("RGB", (w_p2, h_p2), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, w_p2, hdr_h], fill=(15, 23, 42))
        phase_str = "PRE-ONSET" if tk < t_on else ("500 Hz MODULATION" if tk < t_off else "TURN-OFF RING-DOWN")
        dr.text(
            (16, 17),
            f"500 Hz Astrogrid (k=8 cpa) WITH vs. WITHOUT · {phase_str}",
            fill=(248, 250, 252),
            font=f_hdr,
        )
        t_cur = tk * DT_MS
        dr.rectangle([w_p2 - 165, 11, w_p2 - 12, 42], fill=(30, 41, 59))
        dr.text((w_p2 - 154, 18), f"t = {t_cur:6.2f} ms", fill=(56, 189, 248), font=f_mono)

        y_sub = hdr_h
        dr.rectangle([0, y_sub, w_p2, y_sub + sub_h], fill=(241, 245, 249))
        titles_p2 = [
            ("WITHOUT Pre-Shaper (DM OPD)", (220, 38, 38)),
            ("WITH Astrogrid MIMO (DM OPD)", (5, 150, 105)),
            ("H-Band PSF (Left: OFF | Right: ON)", (37, 99, 235)),
        ]
        p_off_rgb = _resize_rgb(_colorize_diverging(o_ag_off[tk], vmax_ag_um, pup), ps)
        p_on_rgb = _resize_rgb(_colorize_diverging(o_ag_mimo[tk], vmax_ag_um, pup), ps)
        psf_l = _resize_rgb(_colorize_log_psf(psf_off_cube[tk], -6.5, -1.8), ps)
        psf_r = _resize_rgb(_colorize_log_psf(psf_mimo_cube[tk], -6.5, -1.8), ps)
        psf_split = np.concatenate([psf_l[:, : ps // 2], psf_r[:, ps // 2 :]], axis=1)
        psf_split[:, ps // 2 - 1 : ps // 2 + 1] = (248, 250, 252)

        frame_np = np.asarray(im, dtype=np.uint8).copy()
        for col_i, prgb in enumerate([p_off_rgb, p_on_rgb, psf_split]):
            x0 = pad + col_i * (ps + pad)
            y0 = y_sub + sub_h + 6
            frame_np[y0 : y0 + ps, x0 : x0 + ps] = prgb
        im = Image.fromarray(frame_np)
        dr = ImageDraw.Draw(im)
        for col_i, (tl, col) in enumerate(titles_p2):
            x0 = pad + col_i * (ps + pad)
            dr.text((x0 + 4, y_sub + 7), tl, fill=col, font=f_sub)
        rms_o = float(m_ag_sq["off"]["rms_tot_nm"][tk])
        rms_m = float(m_ag_sq["mimo"]["rms_tot_nm"][tk])
        x0_0 = pad
        x0_1 = pad + (ps + pad)
        x0_2 = pad + 2 * (ps + pad)
        dr.rectangle([x0_0 + 6, y_sub + sub_h + 12, x0_0 + 122, y_sub + sub_h + 32], fill=(255, 255, 255))
        dr.text((x0_0 + 10, y_sub + sub_h + 15), f"RMS: {rms_o:5.1f} nm", fill=(220, 38, 38), font=f_smb)
        dr.rectangle([x0_1 + 6, y_sub + sub_h + 12, x0_1 + 122, y_sub + sub_h + 32], fill=(255, 255, 255))
        dr.text((x0_1 + 10, y_sub + sub_h + 15), f"RMS: {rms_m:5.1f} nm", fill=(5, 150, 105), font=f_smb)
        dr.text((x0_2 + 10, y_sub + sub_h + 14), "OFF", fill=(252, 165, 165), font=f_smb)
        dr.text((x0_2 + ps - 34, y_sub + sub_h + 14), "ON", fill=(110, 231, 183), font=f_smb)

        y_bar = y_sub + sub_h + ps + pad
        _draw_sparkline(
            dr,
            (pad, y_bar, w_p2 - pad, y_bar + bar_h - 6),
            t_ag_ms[p2_ticks],
            [
                (ideal_sq_nm[p2_ticks], (148, 163, 184)),
                (m_ag_sq["off"]["proj0_nm"][p2_ticks], (220, 38, 38)),
                (m_ag_sq["mimo"]["proj0_nm"][p2_ticks], (5, 150, 105)),
            ],
            k_idx,
            -380.0,
            380.0,
            f"Astrogrid k=8 OPD [nm] (Red=OFF: {m_ag_sq['off']['a1500_nm']:.0f} nm @ 1.5 kHz | Green=ON: {m_ag_sq['mimo']['a1500_nm']:.0f} nm, {ag_1500_fac:.1f}× lower)",
        )
        y_ftr = h_p2 - ftr_h
        dr.rectangle([0, y_ftr, w_p2, h_p2], fill=(248, 250, 252))
        dr.text(
            (16, y_ftr + 9),
            f"500 Hz Square-Wave Astrogrid (1 kHz flip, 8 kHz pre-shaper) · 1.5 kHz resonance: {ag_1500_fac:.1f}× cut · Ring-down: {ag_rd_fac:.1f}× cut",
            fill=(51, 65, 85),
            font=f_sm,
        )
        proc_p2.stdin.write(np.asarray(im, dtype=np.uint8).tobytes())
        if tk == poster_tick:
            im.save(astro_poster)

    proc_p2.stdin.close()
    err_p2 = proc_p2.stderr.read() if proc_p2.stderr else b""
    rc_p2 = proc_p2.wait()
    if rc_p2 != 0:
        raise RuntimeError(f"ffmpeg astrogrid video failed ({rc_p2}): {err_p2.decode(errors='ignore')}")

    # Clean up legacy combined video if present
    (out_dir / "dm_preshaper_demo_sbs.mp4").unlink(missing_ok=True)
    (out_dir / "dm_preshaper_demo_sbs_poster.png").unlink(missing_ok=True)

    def _strip_step(d: dict[str, Any]) -> dict[str, float]:
        return {
            k: round(float(d[k]), 4)
            for k in (
                "stat_rms_nm",
                "dc_err_pct",
                "t50_ms",
                "overshoot_pct",
                "ring_proj_pct",
                "full_wave_ring_pct",
                "t_settle_5_ms",
                "cmd_peak_um",
            )
        }

    # =========================================================================
    # FIGURE 6 & VIDEO 3: Per-Actuator Spatially-Varying KMODE=3 (SISO) & KMODE=4 (5x5 MIMO)
    # =========================================================================
    peract_summary: dict[str, Any] = {}
    vid_peract_meta: dict[str, Any] = {}
    pa_meta_path = raw_dir / "peract_meta.json"
    if pa_meta_path.is_file() and (raw_dir / "ps_peract_k4.fits").is_file():
        pa_meta = json.loads(pa_meta_path.read_text(encoding="utf-8"))
        pa_replays: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
        pa_metrics: dict[str, dict[str, dict[str, Any]]] = {}
        for pname in ("pa_int", "pa_midrim", "pa_edge"):
            pa_replays[pname] = {}
            for tag in ("off", "siso", "k3", "k4"):
                pa_replays[pname][tag] = _load_replay(raw_dir, f"{pname}_{tag}", N_STEP)
            o_off_p = pa_replays[pname]["off"][1]
            pa_metrics[pname] = {
                tag: _compute_step_metrics(o_off_p, pa_replays[pname][tag][0], pa_replays[pname][tag][1], pup)
                for tag in ("off", "siso", "k3", "k4")
            }

        k3_cube = fits.getdata(raw_dir / "ps_peract_k3.fits").astype(np.float64)  # [M3, 64, 64]
        k4_cube = fits.getdata(raw_dir / "ps_peract_k4.fits").astype(np.float64)  # [M4, 4096, 25]
        k4_hdr = fits.getheader(raw_dir / "ps_peract_k4.fits")
        st_rad = int(k4_hdr.get("STNCLRAD", 2))
        st_side = 2 * st_rad + 1
        st_ctr = st_rad * st_side + st_rad  # 12 for 5x5

        # Spatial heterogeneity along the calibrated actuators (horizontal slice iy=31 + full patches)
        act_list = pa_meta["actuators"]
        dist_rim_arr, k3_norm_arr, k4_self_arr, k4_m1_arr, k4_p1_arr, k4_off_pct_arr = [], [], [], [], [], []
        for a in act_list:
            ax_a, ay_a = int(a["ax"]), int(a["ay"])
            # Focus radial curve on clean y-center strip iy in [30, 31, 32] so patch-edge truncation is minimal
            if ay_a not in (30, 31, 32):
                continue
            # Also exclude left-edge patch boundary (ix=55 or ix=43) where dx=-1 is uncalibrated artificially
            if (a["patch"] == "interior" and math.hypot(ax_a - 46, ay_a - 31) > 1.5) or (
                a["patch"] == "rim" and ax_a < 57
            ):
                continue
            i_dm = ay_a * N_ACT + ax_a
            dist_rim_arr.append(float(a["dist_to_rim"]))
            k3_norm_arr.append(float(np.linalg.norm(k3_cube[:, ay_a, ax_a])))
            s_self = float(np.linalg.norm(k4_cube[:, i_dm, st_ctr]))
            s_tot = float(np.linalg.norm(k4_cube[:, i_dm, :]))
            k4_self_arr.append(s_self)
            k4_m1_arr.append(float(np.linalg.norm(k4_cube[:, i_dm, st_ctr - 1])))
            k4_p1_arr.append(float(np.linalg.norm(k4_cube[:, i_dm, st_ctr + 1])))
            k4_off_pct_arr.append(100.0 * max(s_tot**2 - s_self**2, 0.0) / max(s_tot**2, 1e-18))

        # Build exact 5x5 actuator-space pre-shaper correction stamps C_out(ax+ox, ay+oy; k) from KMODE=4 gather cube
        # Recall: C_gather[k, i_out, (dy+R)*S + (dx+R)] where dx = jx_in - ix_out = -ox, dy = jy_in - iy_out = -oy
        def _k4_outgoing_stamps(ax_in: int, ay_in: int, taps: list[int]) -> tuple[list[np.ndarray], list[float]]:
            stamps = []
            u0_vals = []
            for tk in taps:
                pat = np.zeros((st_side, st_side), dtype=np.float64)
                u0 = 1.0
                for oy in range(-st_rad, st_rad + 1):
                    iy_out = ay_in + oy
                    if iy_out < 0 or iy_out >= N_ACT:
                        continue
                    for ox in range(-st_rad, st_rad + 1):
                        ix_out = ax_in + ox
                        if ix_out < 0 or ix_out >= N_ACT:
                            continue
                        dx = -ox
                        dy = -oy
                        p_idx = (dy + st_rad) * st_side + (dx + st_rad)
                        val = float(k4_cube[tk, iy_out * N_ACT + ix_out, p_idx])
                        if ox == 0 and oy == 0:
                            u0 = 1.0 + val
                        pat[oy + st_rad, ox + st_rad] = val
                stamps.append(pat)
                u0_vals.append(u0)
            return stamps, u0_vals

        taps_st = [0, 1, 2, 4]
        st_int, u0_int = _k4_outgoing_stamps(46, 31, taps_st)
        st_edge, u0_edge = _k4_outgoing_stamps(61, 31, taps_st)

        # Render Figure 6 (2x3 comprehensive per-actuator KMODE=3 vs KMODE=4 figure)
        fig = plt.figure(figsize=(15.8, 10.2))
        gs6 = fig.add_gridspec(
            2, 3, left=0.055, right=0.975, top=0.910, bottom=0.070, hspace=0.36, wspace=0.32
        )

        # (a) Interior (46, 31) step response
        ax = fig.add_subplot(gs6[0, 0])
        mi = pa_metrics["pa_int"]
        ax.plot(t_step_ms, mi["off"]["y"], color="#dc2626", lw=2.0,
                label=f"WITHOUT (+{mi['off']['overshoot_pct']:.1f}%, ring {mi['off']['ring_proj_pct']:.2f}%)")
        ax.plot(t_step_ms, mi["siso"]["y"], color="#94a3b8", ls="--", lw=1.7,
                label=f"Uniform SISO K2 (+{mi['siso']['overshoot_pct']:.1f}%, ring {mi['siso']['ring_proj_pct']:.2f}%)")
        ax.plot(t_step_ms, mi["k3"]["y"], color="#d97706", lw=2.0,
                label=f"Per-Act SISO K3 (+{mi['k3']['overshoot_pct']:.1f}%, ring {mi['k3']['ring_proj_pct']:.2f}%)")
        ax.plot(t_step_ms, mi["k4"]["y"], color="#059669", lw=2.4,
                label=f"Per-Act 5×5 MIMO K4 (+{mi['k4']['overshoot_pct']:.1f}%, ring {mi['k4']['ring_proj_pct']:.2f}%)")
        ax.axhspan(0.95, 1.05, color="#94a3b8", alpha=0.14)
        ax.axvline(0.0, color="#64748b", ls="--", lw=0.9)
        ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
        ax.set_xlim(-0.5, 10.5)
        ax.set_ylim(-0.08, 1.62)
        ax.set_xlabel("Time after DM step [ms]")
        ax.set_ylabel("Projected OPD step (static = 1.0)")
        ax.set_title("(a) Interior Actuator (46, 31): Step Response")
        ax.grid(True)
        ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=7.6)

        # (b) Free-Rim Edge (61, 31) step response
        ax = fig.add_subplot(gs6[0, 1])
        me = pa_metrics["pa_edge"]
        ax.plot(t_step_ms, me["off"]["y"], color="#dc2626", lw=2.0,
                label=f"WITHOUT (+{me['off']['overshoot_pct']:.1f}%, ring {me['off']['ring_proj_pct']:.2f}%, {me['off']['t_settle_5_ms']:.1f} ms)")
        ax.plot(t_step_ms, me["siso"]["y"], color="#94a3b8", ls="--", lw=1.7,
                label=f"Uniform SISO K2 (+{me['siso']['overshoot_pct']:.1f}%, ring {me['siso']['ring_proj_pct']:.2f}%, {me['siso']['t_settle_5_ms']:.1f} ms)")
        ax.plot(t_step_ms, me["k3"]["y"], color="#d97706", lw=2.2,
                label=f"Per-Act SISO K3 (+{me['k3']['overshoot_pct']:.1f}%, ring {me['k3']['ring_proj_pct']:.2f}%, {me['k3']['t_settle_5_ms']:.1f} ms)")
        ax.plot(t_step_ms, me["k4"]["y"], color="#059669", lw=2.3,
                label=f"Per-Act 5×5 MIMO K4 (+{me['k4']['overshoot_pct']:.1f}%, ring {me['k4']['ring_proj_pct']:.2f}%)")
        ax.axhspan(0.95, 1.05, color="#94a3b8", alpha=0.14)
        ax.axvline(0.0, color="#64748b", ls="--", lw=0.9)
        ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
        ax.set_xlim(-0.5, 10.5)
        ax.set_ylim(-0.08, 1.56)
        ax.set_xlabel("Time after DM step [ms]")
        ax.set_ylabel("Projected OPD step (static = 1.0)")
        ax.set_title("(b) Free-Rim Edge (61, 31): Step & Ringing")
        ax.grid(True)
        ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=7.5)

        # (c) Full-pupil 2D traveling wave residual vs time (Interior + Free-Rim Edge)
        ax = fig.add_subplot(gs6[0, 2])
        ax.plot(t_step_ms, mi["off"]["dyn_2d_norm_pct"], color="#dc2626", lw=2.0,
                label=f"Interior OFF ({mi['off']['full_wave_ring_pct']:.1f}%)")
        ax.plot(t_step_ms, mi["k3"]["dyn_2d_norm_pct"], color="#d97706", lw=1.9,
                label=f"Interior K3 SISO ({mi['k3']['full_wave_ring_pct']:.1f}%)")
        ax.plot(t_step_ms, mi["k4"]["dyn_2d_norm_pct"], color="#059669", lw=2.4,
                label=f"Interior K4 5×5 MIMO ({mi['k4']['full_wave_ring_pct']:.2f}%, {mi['off']['full_wave_ring_pct']/mi['k4']['full_wave_ring_pct']:.1f}×)")
        ax.plot(t_step_ms, me["off"]["dyn_2d_norm_pct"], color="#dc2626", ls="--", lw=1.6, alpha=0.85,
                label=f"Free-Rim OFF ({me['off']['full_wave_ring_pct']:.1f}%)")
        ax.plot(t_step_ms, me["k3"]["dyn_2d_norm_pct"], color="#d97706", ls="--", lw=1.5, alpha=0.85,
                label=f"Free-Rim K3 SISO ({me['k3']['full_wave_ring_pct']:.1f}%)")
        ax.plot(t_step_ms, me["k4"]["dyn_2d_norm_pct"], color="#0284c7", ls="--", lw=2.2,
                label=f"Free-Rim K4 5×5 MIMO ({me['k4']['full_wave_ring_pct']:.2f}%, {me['off']['full_wave_ring_pct']/me['k4']['full_wave_ring_pct']:.1f}×)")
        ax.axvline(2.0, color="#64748b", ls=":", lw=1.0)
        ax.set_xlim(1.0, 16.0)
        ax.set_ylim(0.0, 60.0)
        ax.set_xlabel("Time after DM step [ms]")
        ax.set_ylabel("Full-pupil 2D wave ‖OPD(t)−OPD_static‖ [%]")
        ax.set_title("(c) Full-Pupil 2D Traveling Wave Residual")
        ax.grid(True)
        ax.legend(loc="upper right", frameon=True, facecolor="white", fontsize=7.3)

        # (d) Spatially-varying KMODE=4 5x5 local-stencil 2D correction stamps C_out(dx, dy; k)
        gs_d = gs6[1, 0].subgridspec(2, 4, wspace=0.14, hspace=0.40)
        im_pa_st = None
        ax_d_list = []
        for row_i, (rname, st_list, u0_list) in enumerate(
            [("Int (46,31)", st_int, u0_int), ("Rim (61,31)", st_edge, u0_edge)]
        ):
            for col_i, (tk_v, pat, u0v) in enumerate(zip(taps_st, st_list, u0_list)):
                ax_s = fig.add_subplot(gs_d[row_i, col_i])
                ax_d_list.append(ax_s)
                im_pa_st = ax_s.imshow(
                    pat,
                    cmap="RdBu_r",
                    vmin=-0.16,
                    vmax=0.16,
                    origin="lower",
                    interpolation="nearest",
                    extent=[-2.5, 2.5, -2.5, 2.5],
                )
                if row_i == 1:
                    # Mark uncalibrated outer pupil boundary at ox > 0
                    ax_s.axvline(0.5, color="#0f172a", ls="--", lw=1.0, alpha=0.85)
                ax_s.set_xticks([-2, 0, 2])
                ax_s.set_yticks([-2, 0, 2])
                ax_s.tick_params(labelsize=6.8)
                ax_s.set_title(f"k={tk_v} ({tk_v * DT_MS:.2f}ms)\nu₀={u0v:.2f}", fontsize=7.1, pad=2)
                if col_i == 0:
                    ax_s.set_ylabel(rname, fontsize=7.8, fontweight="bold")
        assert im_pa_st is not None
        cb6 = fig.colorbar(im_pa_st, ax=ax_d_list, shrink=0.88, pad=0.04, aspect=24)
        cb6.set_label("Δu_DM [unit]", fontsize=7.8)
        fig.text(
            0.055,
            0.460,
            "(d) K4 5×5 Wave-Cancel Stamps Δu(x,y; k): Interior vs. Rim",
            ha="left",
            va="bottom",
            fontsize=9.3,
            fontweight="bold",
            color="#0f172a",
        )

        # (e) Radial spatial symmetry breaking along exact horizontal centerline iy=31
        # (ix=46 complete 5x5 interior; ix=57..61 approaching optical free rim at ix=61)
        ax = fig.add_subplot(gs6[1, 1])
        pts_e = []
        for a in act_list:
            ax_a, ay_a = int(a["ax"]), int(a["ay"])
            if ay_a != 31:
                continue
            if a["patch"] == "interior" and ax_a != 46:
                continue
            if a["patch"] == "rim" and ax_a < 57:
                continue
            i_dm = ay_a * N_ACT + ax_a
            pts_e.append(
                (
                    ax_a,
                    float(a["dist_to_rim"]),
                    float(np.linalg.norm(k4_cube[:, i_dm, st_ctr - 1])),
                    float(np.linalg.norm(k4_cube[:, i_dm, st_ctr + 1])),
                    0.5
                    * (
                        float(np.linalg.norm(k4_cube[:, i_dm, st_ctr - st_side]))
                        + float(np.linalg.norm(k4_cube[:, i_dm, st_ctr + st_side]))
                    ),
                )
            )
        pts_e.sort(key=lambda t: t[0])
        d_plot = [t[1] for t in pts_e]
        m1_plot = [t[2] for t in pts_e]
        p1_plot = [t[3] for t in pts_e]
        ty_plot = [t[4] for t in pts_e]
        ax.plot(d_plot, m1_plot, "o-", color="#059669", lw=2.2, ms=6.4, label="Inward neighbor ‖C(dx=−1)‖₂")
        ax.plot(d_plot, p1_plot, "s--", color="#2563eb", lw=2.2, ms=6.2, label="Outward neighbor ‖C(dx=+1)‖₂")
        ax.plot(d_plot, ty_plot, "^:", color="#d97706", lw=2.0, ms=6.0, label="Tangential neighbor ‖C(dy=±1)‖₂")
        ax.axvline(2.0, color="#dc2626", ls=":", lw=1.1, alpha=0.75, label="Optical free-rim edge (ix = 61)")
        ax.invert_xaxis()
        ax.set_xlim(18.0, 1.2)
        ax.set_ylim(-0.008, max(max(m1_plot + p1_plot + ty_plot) * 1.15, 0.14))
        ax.set_xlabel("Distance to free circular DM rim (31.5 − r) [pitches]")
        ax.set_ylabel("Nearest-neighbor coupling norm ‖C‖₂")
        ax.set_title("(e) Spatial Symmetry Breaking Approaching Free Rim")
        ax.grid(True)
        ax.legend(loc="lower left", frameon=True, facecolor="white", fontsize=7.6)

        # (f) Summary grouped bar chart: Full-Pupil 2D Traveling Wave Residual across 3 Radii
        ax = fig.add_subplot(gs6[1, 2])
        loc_names = ["Interior\n(46, 31)\nr = 14.5", "Near-Rim\n(57, 31)\nr = 25.5", "Free-Rim Edge\n(61, 31)\nr = 29.5"]
        pnames = ["pa_int", "pa_midrim", "pa_edge"]
        x_g = np.arange(len(pnames))
        w_g = 0.19
        bar_specs = [
            ("off", "WITHOUT", "#dc2626", -1.5 * w_g),
            ("siso", "Uniform SISO (K2)", "#94a3b8", -0.5 * w_g),
            ("k3", "Per-Act SISO (K3)", "#d97706", 0.5 * w_g),
            ("k4", "Per-Act 5×5 MIMO (K4)", "#059669", 1.5 * w_g),
        ]
        for tag, lbl, col, offs in bar_specs:
            vals = [pa_metrics[p][tag]["full_wave_ring_pct"] for p in pnames]
            ax.bar(x_g + offs, vals, width=w_g, color=col, alpha=0.92, label=lbl)
        for i_p, p in enumerate(pnames):
            v_off = pa_metrics[p]["off"]["full_wave_ring_pct"]
            v_k3 = pa_metrics[p]["k3"]["full_wave_ring_pct"]
            v_k4 = pa_metrics[p]["k4"]["full_wave_ring_pct"]
            ax.annotate(
                f"{v_off / max(v_k4, 1e-6):.1f}×\n({(v_off / max(v_k4, 1e-6))**2:.0f}×E)",
                xy=(i_p + 1.5 * w_g, v_k4 + 0.15),
                xytext=(i_p + 1.5 * w_g, max(v_k3, v_k4) + 1.1),
                ha="center",
                va="bottom",
                fontsize=7.0,
                fontweight="bold",
                color="#065f46",
                arrowprops=dict(arrowstyle="->", color="#065f46", lw=0.9, shrinkA=1, shrinkB=1),
            )
        ax.set_xticks(x_g)
        ax.set_xticklabels(loc_names, fontsize=8.4)
        ax.set_ylim(0.0, 23.2)
        ax.set_ylabel("Post-2 ms 2D traveling wave RMS [%]")
        ax.set_title("(f) 2D Plate Wave Suppression: Interior → Free Rim")
        ax.grid(True, axis="y")
        ax.legend(loc="upper center", ncol=2, frameon=True, facecolor="white", fontsize=7.4)

        fig.suptitle(
            "Per-Actuator Spatially-Varying DM Pre-Shaping on 64×64 ALPAO Plate (8 kHz · KMODE=3 SISO vs. KMODE=4 5×5 Stencil MIMO)",
            fontsize=12.6,
            fontweight="bold",
        )
        fig.savefig(out_dir / "fig6_per_actuator_k3_k4.png", dpi=165)
        plt.close(fig)

        # Render Video 3: 8 kHz Side-by-Side 2D Wave Comparison (KMODE=3 vs KMODE=4 on Interior & Free-Rim Edge)
        pa_mp4 = out_dir / "dm_preshaper_per_actuator_sbs.mp4"
        pa_poster = out_dir / "dm_preshaper_per_actuator_sbs_poster.png"
        proc_p3 = _start_ffmpeg(pa_mp4, w_p1, h_p1, fps_p1)
        assert proc_p3.stdin is not None

        o_int_off = pa_replays["pa_int"]["off"][1]
        o_int_k3 = pa_replays["pa_int"]["k3"][1]
        o_int_k4 = pa_replays["pa_int"]["k4"][1]
        o_edg_off = pa_replays["pa_edge"]["off"][1]
        o_edg_k3 = pa_replays["pa_edge"]["k3"][1]
        o_edg_k4 = pa_replays["pa_edge"]["k4"][1]
        st_pa_int = pa_metrics["pa_int"]["off"]["static_opd"]
        st_pa_edg = pa_metrics["pa_edge"]["off"]["static_opd"]
        vmax_pa_i = float(np.percentile(np.abs((o_int_off[28:72] - st_pa_int[None])[:, pup]), 99.6))
        vmax_pa_e = float(np.percentile(np.abs((o_edg_off[28:72] - st_pa_edg[None])[:, pup]), 99.6))
        pa_int_wx = pa_metrics["pa_int"]["off"]["full_wave_ring_pct"] / max(pa_metrics["pa_int"]["k4"]["full_wave_ring_pct"], 0.01)
        pa_edg_wx = pa_metrics["pa_edge"]["off"]["full_wave_ring_pct"] / max(pa_metrics["pa_edge"]["k4"]["full_wave_ring_pct"], 0.01)

        for k_idx, tk in enumerate(p1_ticks):
            im = Image.new("RGB", (w_p1, h_p1), (255, 255, 255))
            dr = ImageDraw.Draw(im)
            dr.rectangle([0, 0, w_p1, hdr_h], fill=(15, 23, 42))
            dr.text(
                (16, 17),
                "Per-Actuator Pre-Shaper (KMODE 3 & 4) · Interior vs. Free-Rim Wave",
                fill=(248, 250, 252),
                font=f_hdr,
            )
            t_cur = (tk - Q0_STEP) * DT_MS
            dr.rectangle([w_p1 - 165, 11, w_p1 - 12, 42], fill=(30, 41, 59))
            dr.text((w_p1 - 154, 18), f"t = {t_cur:+6.2f} ms", fill=(56, 189, 248), font=f_mono)

            y_sub1 = hdr_h
            y_img1 = y_sub1 + sub_h + 6
            y_sub2 = hdr_h + (sub_h + ps + pad)
            y_img2 = y_sub2 + sub_h + 6
            dr.rectangle([0, y_sub1, w_p1, y_sub1 + sub_h], fill=(241, 245, 249))
            dr.rectangle([0, y_sub2, w_p1, y_sub2 + sub_h], fill=(241, 245, 249))

            frame_np = np.asarray(im, dtype=np.uint8).copy()
            r1_cubes = [o_int_off, o_int_k3, o_int_k4]
            r2_cubes = [o_edg_off, o_edg_k3, o_edg_k4]
            for col_i in range(3):
                x0 = pad + col_i * (ps + pad)
                frame_np[y_img1 : y_img1 + ps, x0 : x0 + ps] = _resize_rgb(
                    _colorize_diverging(r1_cubes[col_i][tk] - st_pa_int, vmax_pa_i, pup), ps
                )
                frame_np[y_img2 : y_img2 + ps, x0 : x0 + ps] = _resize_rgb(
                    _colorize_diverging(r2_cubes[col_i][tk] - st_pa_edg, vmax_pa_e, pup), ps
                )
            im = Image.fromarray(frame_np)
            dr = ImageDraw.Draw(im)

            r1_lbls = [
                (f"Interior (46,31) WITHOUT (+{mi['off']['overshoot_pct']:.1f}%)", (220, 38, 38)),
                (f"Interior K3 SISO (+{mi['k3']['overshoot_pct']:.1f}%)", (217, 119, 6)),
                (f"Interior K4 5×5 MIMO (+{mi['k4']['overshoot_pct']:.1f}%)", (5, 150, 105)),
            ]
            r2_lbls = [
                (f"Free-Rim (61,31) WITHOUT (+{me['off']['overshoot_pct']:.1f}%)", (220, 38, 38)),
                (f"Free-Rim K3 SISO (+{me['k3']['overshoot_pct']:.1f}%)", (217, 119, 6)),
                (f"Free-Rim K4 5×5 MIMO (+{me['k4']['overshoot_pct']:.1f}%)", (5, 150, 105)),
            ]
            for col_i in range(3):
                x0 = pad + col_i * (ps + pad)
                tl1, c1 = r1_lbls[col_i]
                tl2, c2 = r2_lbls[col_i]
                dr.text((x0 + 4, y_sub1 + 7), tl1, fill=c1, font=f_sub)
                dr.text((x0 + 4, y_sub2 + 7), tl2, fill=c2, font=f_sub)
                w1 = float(np.sqrt(np.mean(((r1_cubes[col_i][tk] - st_pa_int)[pup]) ** 2))) * 1e3
                w2 = float(np.sqrt(np.mean(((r2_cubes[col_i][tk] - st_pa_edg)[pup]) ** 2))) * 1e3
                dr.rectangle([x0 + 6, y_img1 + 6, x0 + 114, y_img1 + 26], fill=(255, 255, 255))
                dr.text((x0 + 10, y_img1 + 9), f"Wave: {w1:4.1f} nm", fill=c1, font=f_smb)
                dr.rectangle([x0 + 6, y_img2 + 6, x0 + 114, y_img2 + 26], fill=(255, 255, 255))
                dr.text((x0 + 10, y_img2 + 9), f"Wave: {w2:4.1f} nm", fill=c2, font=f_smb)

            y_ftr = h_p1 - ftr_h
            dr.rectangle([0, y_ftr, w_p1, h_p1], fill=(248, 250, 252))
            dr.text(
                (16, y_ftr + 9),
                f"ALPAO 64×64 (8 kHz, 400× slow-mo) · KMODE=4 5×5 local stencil wave cut: {pa_int_wx:.1f}× ({pa_int_wx**2:.0f}×E) interior · {pa_edg_wx:.1f}× ({pa_edg_wx**2:.0f}×E) free rim",
                fill=(51, 65, 85),
                font=f_sm,
            )
            proc_p3.stdin.write(np.asarray(im, dtype=np.uint8).tobytes())
            if tk == p1_poster_tick:
                im.save(pa_poster)

        proc_p3.stdin.close()
        err_p3 = proc_p3.stderr.read() if proc_p3.stderr else b""
        rc_p3 = proc_p3.wait()
        if rc_p3 != 0:
            raise RuntimeError(f"ffmpeg per-actuator video failed ({rc_p3}): {err_p3.decode(errors='ignore')}")

        # Compute summary stats for JSON & markdown
        def _k4_loc_stats(ax_l: int, ay_l: int) -> dict[str, float]:
            i_dm = ay_l * N_ACT + ax_l
            s_self = float(np.linalg.norm(k4_cube[:, i_dm, st_ctr]))
            s_tot = float(np.linalg.norm(k4_cube[:, i_dm, :]))
            return {
                "k3_norm": round(float(np.linalg.norm(k3_cube[:, ay_l, ax_l])), 4),
                "k4_self_norm": round(s_self, 4),
                "k4_off_pct": round(100.0 * max(s_tot**2 - s_self**2, 0.0) / max(s_tot**2, 1e-18), 1),
                "k4_dx_m1": round(float(np.linalg.norm(k4_cube[:, i_dm, st_ctr - 1])), 4),
                "k4_dx_p1": round(float(np.linalg.norm(k4_cube[:, i_dm, st_ctr + 1])), 4),
            }

        k3_int_v = k3_cube[:, 31, 46]
        k3_edg_v = k3_cube[:, 31, 61]
        peract_summary = {
            "n_act_cal": int(pa_meta["n_act_cal"]),
            "n_int": int(pa_meta["n_int"]),
            "n_rim": int(pa_meta["n_rim"]),
            "k3_m_buf": int(k3_cube.shape[0]),
            "k4_m_buf": int(k4_cube.shape[0]),
            "stencil_rad": st_rad,
            "stencil_nb": st_side * st_side,
            "mdr_info": pa_meta.get("mdr_info", {}),
            "k3_int_vs_edge_diff_pct": round(
                float(np.linalg.norm(k3_edg_v - k3_int_v) / max(np.linalg.norm(k3_int_v), 1e-12) * 100.0), 1
            ),
            "loc_stats": {
                "pa_int": _k4_loc_stats(46, 31),
                "pa_midrim": _k4_loc_stats(57, 31),
                "pa_edge": _k4_loc_stats(61, 31),
            },
            "pa_int": {k: _strip_step(v) for k, v in pa_metrics["pa_int"].items()},
            "pa_midrim": {k: _strip_step(v) for k, v in pa_metrics["pa_midrim"].items()},
            "pa_edge": {k: _strip_step(v) for k, v in pa_metrics["pa_edge"].items()},
        }
        vid_peract_meta = {
            "file": pa_mp4.name,
            "poster": pa_poster.name,
            "n_frames": len(p1_ticks),
            "fps": fps_p1,
            "duration_s": round(len(p1_ticks) / fps_p1, 1),
            "width": w_p1,
            "height": h_p1,
        }

    # Assemble clean JSON-serializable summary metrics dictionary
    def _strip_astro(d: dict[str, Any]) -> dict[str, float]:
        keys = [
            "a500_nm",
            "a1500_nm",
            "ratio_3_1",
            "mod_pk_nm",
            "orth_mean_nm",
            "ringdown_rms_nm",
            "ringdown_pk_nm",
            "cmd_pk_um",
        ]
        if "track_err_nm" in d:
            keys.append("track_err_nm")
        return {k: round(float(d[k]), 4) for k in keys}

    summary = {
        "calib_meta": calib_meta,
        "pass2_live_rt": {
            "zernike8_dc_err_pct": round(p2_z8_dc_err_pct, 3),
            "zernike8_off_peak_p1_pct": round(float(pct_z1.max()), 2),
            "zernike8_off_peak_p2_pct": round(float(pct_z2.max()), 2),
            "astro20_dc_err_pct": round(p2_ag_dc_err_pct, 3),
            "astro20_off_peak_p1_pct": round(float(pct_a1.max()), 2),
            "astro20_off_peak_p2_pct": round(float(pct_a2.max()), 2),
        },
        "poke_interior": {k: _strip_step(v) for k, v in m_pi.items()},
        "poke_rim": {k: _strip_step(v) for k, v in m_pr.items()},
        "zernike_focus": {
            **{k: _strip_step(v) for k, v in m_zf.items()},
            "xtalk_peak_off_pct": round(float(zf_xtalk_off[Q0_STEP:].max()), 2),
            "xtalk_peak_mimo_pct": round(float(zf_xtalk_mimo[Q0_STEP:].max()), 2),
            "peak_coupled_mode_idx": peak_off_mode,
        },
        "zernike_astig": {k: _strip_step(v) for k, v in m_za.items()},
        "astro_500hz_sq": {k: _strip_astro(v) for k, v in m_ag_sq.items()},
        "astro_500hz_k10": {k: _strip_astro(v) for k, v in m_ag_k10.items()},
        "astro_500hz_quad": {k: _strip_astro(v) for k, v in m_ag_quad.items()},
        "coronagraph_hband": {
            "spot_cv_off_pct": round(spot_cv_off_pct, 2),
            "spot_cv_mimo_pct": round(spot_cv_mimo_pct, 2),
            "spot_pk_off": spot_pk_off,
            "spot_pk_mimo": spot_pk_mimo,
            "spot_ghost_off": spot_ghost_off,
            "spot_ghost_mimo": spot_ghost_mimo,
            "spot_ghost_gain_x": round(spot_ghost_gain_x, 1),
            "dh_mod_off": dh_mod_off,
            "dh_mod_mimo": dh_mod_mimo,
            "dh_mod_gain_x": round(dh_mod_off / max(dh_mod_mimo, 1e-12), 2),
            "dh_rd_off": dh_rd_off,
            "dh_rd_mimo": dh_rd_mimo,
            "dh_rd_gain_x": round(dh_rd_off / max(dh_rd_mimo, 1e-12), 2),
            "spurious_off": spur_off,
            "spurious_mimo": spur_mimo,
            "spurious_gain_x": round(spur_off / max(spur_mimo, 1e-12), 2),
        },
        "mimo_kernels": {
            nm: {k: v for k, v in d.items() if k not in ("e_mat", "diag_taps", "off_taps")}
            for nm, d in [
                ("rings8_mimo", ks_ring),
                ("zernike28_mimo", ks_zern),
                ("astro20_mimo", ks_astro),
            ]
        },
        "video_single_poke": {
            "file": poke_mp4.name,
            "poster": poke_poster.name,
            "n_frames": len(p1_ticks),
            "fps": fps_p1,
            "duration_s": round(len(p1_ticks) / fps_p1, 1),
            "width": w_p1,
            "height": h_p1,
        },
        "video_astrogrid": {
            "file": astro_mp4.name,
            "poster": astro_poster.name,
            "n_frames": len(p2_ticks),
            "fps": fps_p2,
            "duration_s": round(len(p2_ticks) / fps_p2, 1),
            "width": w_p2,
            "height": h_p2,
        },
        "per_actuator": peract_summary,
        "video_per_actuator": vid_peract_meta,
    }
    (out_dir / "dm_preshaper_demo_metrics.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
