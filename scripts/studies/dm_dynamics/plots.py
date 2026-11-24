# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Diagnostic figures, video poster, and synchronized side-by-side comparison renderer."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _norm_gray_u8(img: np.ndarray, vmax: float) -> np.ndarray:
    v = max(float(vmax), 1e-12)
    x = np.clip(0.5 + 0.5 * (img / v), 0.0, 1.0)
    return (x * 255.0 + 0.5).astype(np.uint8)


def _resize_f32(img: np.ndarray, size: int) -> np.ndarray:
    if img.shape == (size, size):
        return img
    im = Image.fromarray(img.astype(np.float32), mode="F")
    im = im.resize((size, size), resample=Image.BILINEAR)
    return np.asarray(im, dtype=np.float32)


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


def _load_ttf(bold: bool = True, mono: bool = False, size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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


def _align_actual_pywfs_orientation(act_f: np.ndarray) -> np.ndarray:
    """Horizontally mirror the 3 top-row SCExAO PyWFS panels to match DM & cacaosim orientation.

    In actual_LepICSaBL-E.mp4 (scaled to 810x518), the bottom-row reconstructed DM surface
    already places the poke in the lower-left (matching cacaosim), whereas the raw top-row
    4-pupil NIR PyWFS camera view has an odd-mirror horizontal reflection (poke in lower-right
    of each pupil). Mirroring each exact 259x259 top-row PyWFS panel aligns all 4 pupils and
    their optical slope dipoles 1-to-1 with both the DM surface below and the simulation on the right.
    """
    out = act_f.copy()
    for x0, x1 in ((2, 261), (275, 534), (548, 807)):
        out[2:261, x0:x1] = out[2:261, x0:x1][:, ::-1]
    return out


def _render_sim_half_810x518(
    wfs_im: np.ndarray,
    dm_im: np.ndarray,
    wfs_lim: float,
    dm_lim: float,
) -> np.ndarray:
    """Render cacaosim 2x3 panels matching exact 810x518 pixel layout of actual LepICSaBL-E."""
    canvas = np.full((518, 810, 3), 255, dtype=np.uint8)
    w_r = _resize_f32(wfs_im, 258)
    d_r = _resize_f32(dm_im, 207)
    w_auto = max(float(np.max(np.abs(w_r))), 1e-12)
    d_auto = max(float(np.max(np.abs(d_r))), 1e-12)

    top_p = [
        _norm_gray_u8(w_r, wfs_lim),
        _norm_gray_u8(w_r, wfs_lim / 50.0),
        _norm_gray_u8(w_r, w_auto),
    ]
    bot_p = [
        _norm_gray_u8(d_r, dm_lim),
        _norm_gray_u8(d_r, dm_lim / 50.0),
        _norm_gray_u8(d_r, d_auto),
    ]
    top_xs = (2, 276, 550)
    bot_xs = (27, 300, 574)
    for col in range(3):
        x0_t = top_xs[col]
        x0_b = bot_xs[col]
        canvas[2 : 2 + 258, x0_t : x0_t + 258] = top_p[col][:, :, None]
        canvas[302 : 302 + 207, x0_b : x0_b + 207] = bot_p[col][:, :, None]
    return canvas


def _build_sbs_template(
    w_half: int,
    h_body: int,
    div_w: int,
    hdr_h: int,
    sub_h: int,
    ftr_h: int,
) -> tuple[np.ndarray, Any, Any]:
    """Pre-render static header, column subheader, vertical divider, and footer banner."""
    W = 2 * w_half + div_w
    H = hdr_h + sub_h + h_body + ftr_h
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)

    # Dark top banner
    dr.rectangle([0, 0, W, hdr_h], fill=(15, 23, 42))
    # Light subheader bar
    dr.rectangle([0, hdr_h, W, hdr_h + sub_h], fill=(241, 245, 249))
    dr.line([(0, hdr_h + sub_h - 1), (W, hdr_h + sub_h - 1)], fill=(203, 213, 225), width=1)
    # Center divider across subheader + body
    dr.rectangle([w_half, hdr_h, w_half + div_w, hdr_h + sub_h + h_body], fill=(15, 23, 42))
    # Bottom caption footer
    y_ftr = hdr_h + sub_h + h_body
    dr.rectangle([0, y_ftr, W, H], fill=(248, 250, 252))
    dr.line([(0, y_ftr), (W, y_ftr)], fill=(203, 213, 225), width=1)

    f_hdr = _load_ttf(bold=True, mono=False, size=18)
    f_sub = _load_ttf(bold=True, mono=False, size=13)
    f_ftr = _load_ttf(bold=False, mono=False, size=12)
    f_clk = _load_ttf(bold=True, mono=True, size=17)

    # Left & Right panel titles (leave center pill area clear)
    left_txt = "Actual SCExAO 20 kHz Measurement — ALPAO 64×64 (LepICSaBL-E)"
    right_txt = 'cacaosim Simulation — Coupled 2D Plate PDE (dyn_mode = "plate")'
    dr.text((w_half // 2 - 42, hdr_h // 2), left_txt, fill=(248, 250, 252), font=f_hdr, anchor="mm")
    dr.text(
        (w_half + div_w + w_half // 2 + 42, hdr_h // 2),
        right_txt,
        fill=(248, 250, 252),
        font=f_hdr,
        anchor="mm",
    )

    col_labels = ("Linear (1×)", "Linear (50×)", "Autoscale")
    col_centers = (131, 405, 679)
    for base_x in (0, w_half + div_w):
        for cx, lbl in zip(col_centers, col_labels):
            dr.text(
                (base_x + cx, hdr_h + sub_h // 2),
                lbl,
                fill=(30, 41, 59),
                font=f_sub,
                anchor="mm",
            )

    ftr_txt = (
        "Top row: NIR Pyramid WFS (1 ms diff)   |   Bottom row: DM Surface Shape (1 ms diff)   |   "
        "20 kHz (50 μs/frame), synchronized at poke onset t = 0.00 ms"
    )
    dr.text((W // 2, y_ftr + ftr_h // 2), ftr_txt, fill=(71, 85, 105), font=f_ftr, anchor="mm")
    return np.asarray(im, dtype=np.uint8), f_clk, (W // 2, hdr_h // 2)


def _boxcar_1ms_diff(arr: np.ndarray, n_diff: int) -> np.ndarray:
    """Compute exact LepICSaBL-E difference between two consecutive 1 ms exposure means."""
    n_tot = arr.shape[0]
    if n_tot < 2 * n_diff + 1:
        return (arr[n_diff:] - arr[:-n_diff]).astype(np.float32)
    cs = np.concatenate(
        [np.zeros((1,) + arr.shape[1:], dtype=np.float64), np.cumsum(arr, axis=0, dtype=np.float64)],
        axis=0,
    )
    k = np.arange(2 * n_diff, n_tot)
    diff = ((cs[k] - cs[k - n_diff]) - (cs[k - n_diff] - cs[k - 2 * n_diff])) / float(n_diff)
    return diff.astype(np.float32)


def render_side_by_side_video_and_sheet(
    sim_dir: Path,
    actual_mp4: Path,
    out_dir: Path,
    meta: dict[str, Any],
    gain_1x: float = 0.25,
    fps: float = 10.0,
) -> dict[str, Any]:
    """Build synchronized Actual vs Simulated 20 kHz side-by-side MP4, poster, and contact sheet."""
    ffmpeg = _find_ffmpeg()
    n_total = int(meta["n_total"])
    n_diff = int(meta["n_diff"])
    nwf = int(meta["nwf"])
    ncam = int(meta["ncam"])
    rate_hz = float(meta["rate_hz"])
    fr_poke = int(meta["fr_poke"])

    opd = np.fromfile(sim_dir / "dm_opd_20khz.f32", dtype=np.float32).reshape((n_total, nwf, nwf))
    wfs = np.fromfile(sim_dir / "pyrwfs_20khz.f32", dtype=np.float32).reshape((n_total, ncam, ncam))
    pup = np.fromfile(sim_dir / "pup.f32", dtype=np.float32).reshape((nwf, nwf)) > 0.5

    surf = 0.5 * opd
    wfs_diff = _boxcar_1ms_diff(wfs, n_diff)
    dm_diff = _boxcar_1ms_diff(surf, n_diff) * pup[None, :, :]
    n_sim = dm_diff.shape[0]

    wfs_lim = max(gain_1x, 0.05) * float(np.max(np.abs(wfs_diff)))
    dm_lim = max(gain_1x, 0.05) * float(np.max(np.abs(dm_diff)))

    # Actual LepICSaBL-E playback spans video frames 41..1588 (1547 fr = 400 steps @ 3.8675 fr/step)
    # Poke onset occurs at actual video frame ~103 (step k = 16 -> 0.80 ms pre-poke)
    lead = 2 * n_diff if n_total >= 2 * n_diff + 1 else n_diff
    k_onset_sim = fr_poke - lead
    sim_start = max(0, k_onset_sim - 16)
    n_frames_out = min(396, n_sim - sim_start)
    act_indices = [int(round(41.0 + k * 3.8675)) for k in range(n_frames_out)]
    needed_act = set(act_indices)
    max_act_idx = max(act_indices)

    # Stream-decode actual_mp4 at 810x518 keeping only the selected 20 kHz step frames
    w_half, h_body = 810, 518
    frame_bytes = w_half * h_body * 3
    dec = subprocess.Popen(
        [
            ffmpeg,
            "-i",
            str(actual_mp4),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-vf",
            f"scale={w_half}:{h_body}:flags=lanczos",
            "-v",
            "error",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert dec.stdout is not None
    actual_cache: dict[int, np.ndarray] = {}
    last_frame: np.ndarray | None = None
    idx_dec = 0
    while True:
        buf = dec.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        if idx_dec in needed_act:
            raw_f = np.frombuffer(buf, dtype=np.uint8).reshape((h_body, w_half, 3)).copy()
            actual_cache[idx_dec] = _align_actual_pywfs_orientation(raw_f)
        last_frame = _align_actual_pywfs_orientation(
            np.frombuffer(buf, dtype=np.uint8).reshape((h_body, w_half, 3))
        )
        idx_dec += 1
        if idx_dec > max_act_idx:
            break
    dec.stdout.close()
    dec.wait()
    assert last_frame is not None

    div_w, hdr_h, sub_h, ftr_h = 20, 52, 24, 22
    template, f_clk, (clk_cx, clk_cy) = _build_sbs_template(
        w_half, h_body, div_w, hdr_h, sub_h, ftr_h
    )
    H_out, W_out, _ = template.shape
    y_body = hdr_h + sub_h

    sbs_mp4 = out_dir / "dm_poke_actual_vs_sim_20khz.mp4"
    enc = subprocess.Popen(
        [
            ffmpeg,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{W_out}x{H_out}",
            "-r",
            f"{fps:.4f}",
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "21",
            "-movflags",
            "+faststart",
            str(sbs_mp4),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert enc.stdin is not None

    poster_target_ms = 4.1
    poster_saved = False
    sheet_targets_ms = [0.5, 1.5, 2.2, 4.1, 7.1, 11.5]
    sheet_frames: dict[float, np.ndarray] = {}

    for k in range(n_frames_out):
        si = sim_start + k
        t_ms = ((si - k_onset_sim) / rate_hz) * 1e3
        act_f = actual_cache.get(act_indices[k], last_frame)
        sim_f = _render_sim_half_810x518(wfs_diff[si], dm_diff[si], wfs_lim, dm_lim)

        frame = template.copy()
        frame[y_body : y_body + h_body, 0:w_half] = act_f
        frame[y_body : y_body + h_body, w_half + div_w : 2 * w_half + div_w] = sim_f

        # Stamp synchronized millisecond clock pill in center of top header
        fim = Image.fromarray(frame, mode="RGB")
        dr = ImageDraw.Draw(fim)
        pw_half, ph_half = 74, 16
        dr.rounded_rectangle(
            [clk_cx - pw_half, clk_cy - ph_half, clk_cx + pw_half, clk_cy + ph_half],
            radius=8,
            fill=(190, 18, 60),
        )
        dr.text((clk_cx, clk_cy), f"t = {t_ms:+5.2f} ms", fill=(255, 255, 255), font=f_clk, anchor="mm")
        out_arr = np.asarray(fim, dtype=np.uint8)
        enc.stdin.write(out_arr.tobytes())

        if not poster_saved and t_ms >= poster_target_ms:
            fim.save(out_dir / "dm_poke_actual_vs_sim_20khz_poster.png")
            poster_saved = True
        for tm in sheet_targets_ms:
            if tm not in sheet_frames and t_ms >= tm:
                sheet_frames[tm] = out_arr.copy()

    enc.stdin.close()
    err_b = enc.stderr.read() if enc.stderr else b""
    rc = enc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}): {err_b.decode('utf-8', 'ignore')}")

    # Assemble 3x2 Side-by-Side Contact Sheet (6 key timestamps comparing Actual vs Simulated)
    fig, axes = plt.subplots(3, 2, figsize=(15.5, 9.2), dpi=140)
    fig.patch.set_facecolor("white")
    for i, tm in enumerate(sheet_targets_ms):
        ax = axes[i // 2, i % 2]
        if tm in sheet_frames:
            ax.imshow(sheet_frames[tm][::-1], origin="lower")
        ax.axis("off")
    fig.suptitle(
        "Synchronized 20 kHz ALPAO 64×64 Single-Actuator Poke — "
        "Actual SCExAO Measurement (Left) vs. cacaosim Plate PDE (Right)",
        fontsize=12.0,
        fontweight="bold",
    )
    plt.tight_layout(rect=[0.0, 0.0, 1.0, 0.96])
    sheet_path = out_dir / "dm_poke_actual_vs_sim_contact_sheet.png"
    plt.savefig(sheet_path)
    plt.close(fig)

    return {
        "sbs_video": sbs_mp4.name,
        "sbs_width": W_out,
        "sbs_height": H_out,
        "sbs_frames": n_frames_out,
        "sbs_fps": fps,
        "sbs_duration_s": round(n_frames_out / fps, 1),
    }


def _build_rdbu_lut() -> np.ndarray:
    """Build a 256x3 uint8 RdBu_r diverging colormap LUT for fast video frame encoding."""
    cmap = matplotlib.colormaps["RdBu_r"]
    rgba = cmap(np.linspace(0.0, 1.0, 256))
    return (rgba[:, :3] * 255.0 + 0.5).astype(np.uint8)


def _colorize_pupil_rgb(
    img: np.ndarray,
    pup_mask: np.ndarray,
    vmax: float,
    lut: np.ndarray,
    bg_rgb: tuple[int, int, int] = (30, 41, 59),
) -> np.ndarray:
    """Map signed 2D float image to RGB via RdBu_r inside circular pupil, dark slate outside."""
    v = max(float(vmax), 1e-12)
    x = np.clip(0.5 + 0.5 * (img / v), 0.0, 1.0)
    idx = (x * 255.0 + 0.5).astype(np.uint8)
    rgb = lut[idx]
    if pup_mask is not None:
        rgb = rgb.copy()
        rgb[~pup_mask] = bg_rgb
    return rgb


def render_dm_shape_vs_deriv_media(
    sim_dir: Path,
    out_dir: Path,
    meta: dict[str, Any],
    gain_1x: float = 0.25,
    fps: float = 10.0,
) -> dict[str, Any]:
    """Render 20 kHz MP4, poster, and 4x6 contact sheet of DM surface shape w(t) vs 1 ms diff."""
    ffmpeg = _find_ffmpeg()
    n_total = int(meta["n_total"])
    n_diff = int(meta["n_diff"])
    nwf = int(meta["nwf"])
    rate_hz = float(meta["rate_hz"])
    fr_poke = int(meta["fr_poke"])
    poke_x = int(meta["poke_x"])
    poke_y = int(meta["poke_y"])

    opd = np.fromfile(sim_dir / "dm_opd_20khz.f32", dtype=np.float32).reshape((n_total, nwf, nwf))
    pup = np.fromfile(sim_dir / "pup.f32", dtype=np.float32).reshape((nwf, nwf)) > 0.5

    # Direct mechanical surface displacement w(x, y, t) [nm] and steady-state equilibrium w_DC [nm]
    surf_nm = (0.5 * opd * 1e3) * pup[None, :, :]
    w_dc_nm = np.mean(surf_nm[-20:], axis=0).astype(np.float32) * pup
    diff_nm = _boxcar_1ms_diff(surf_nm, n_diff) * pup[None, :, :]

    lead = 2 * n_diff if n_total >= 2 * n_diff + 1 else n_diff
    k_onset_diff = fr_poke - lead
    sim_start = max(0, k_onset_diff - 16)
    n_frames_out = min(396, diff_nm.shape[0] - sim_start)

    # Physical scales [nm]
    w_peak_nm = float(np.max(np.abs(surf_nm)))
    w_dc_peak_nm = float(np.max(np.abs(w_dc_nm)))
    w_lim_1x = max(600.0, round(w_dc_peak_nm * 1.07 / 50.0) * 50.0)
    w_lim_50x = w_lim_1x / 50.0
    d_lim_1x = max(gain_1x, 0.05) * float(np.max(np.abs(diff_nm)))
    d_lim_50x = d_lim_1x / 50.0

    # Far-ring comparison metrics (18..36 act from poke): instantaneous shape w(t) vs 1 ms diff
    yy, xx = np.mgrid[0:nwf, 0:nwf]
    r_act = np.hypot(xx - (1.5 + 4.0 * poke_x), yy - (1.5 + 4.0 * poke_y)) / 4.0
    far_ring = pup & (r_act >= 18.0) & (r_act <= 36.0)
    shape_samples: list[dict[str, float]] = []
    for dt_ms in (0.25, 0.5, 1.0, 1.5, 2.2, 4.1, 7.1, 11.5, 16.0):
        step_off = int(round(dt_ms * rate_hz * 1e-3))
        i_raw = min(n_total - 1, max(0, fr_poke + step_off))
        i_dif = min(diff_nm.shape[0] - 1, max(0, k_onset_diff + step_off))
        w_f = surf_nm[i_raw]
        r_f = (w_f - w_dc_nm) * pup
        d_f = diff_nm[i_dif]
        shape_samples.append(
            {
                "dt_ms": float(dt_ms),
                "shape_peak_nm": float(np.max(np.abs(w_f))),
                "shape_far_max_nm": float(np.max(np.abs(w_f[far_ring]))),
                "shape_far_rms_nm": float(np.std(w_f[far_ring])),
                "resid_peak_nm": float(np.max(np.abs(r_f))),
                "deriv_far_max_nm": float(np.max(np.abs(d_f[far_ring]))),
                "deriv_far_rms_nm": float(np.std(d_f[far_ring])),
            }
        )

    # Pre-render static video template (2x3 panels of 280x280, RdBu_r diverging colormap)
    lut = _build_rdbu_lut()
    panel_px = 280
    pad_x = 18
    pad_y = 14
    hdr_h = 54
    row_hdr_h = 34
    sub_h = 22
    cbar_h = 44
    W_out = 3 * panel_px + 4 * pad_x
    H_out = hdr_h + 2 * (row_hdr_h + sub_h + panel_px) + 2 * pad_y + cbar_h
    W_out += W_out & 1
    H_out += H_out & 1

    pup_r = (
        np.asarray(
            Image.fromarray((pup.astype(np.uint8) * 255), mode="L").resize(
                (panel_px, panel_px), resample=Image.NEAREST
            )
        )
        > 127
    )

    tpl = Image.new("RGB", (W_out, H_out), (255, 255, 255))
    dr = ImageDraw.Draw(tpl)
    f_hdr = _load_ttf(bold=True, mono=False, size=17)
    f_row = _load_ttf(bold=True, mono=False, size=14)
    f_sub = _load_ttf(bold=True, mono=False, size=12)
    f_sm = _load_ttf(bold=False, mono=False, size=11)
    f_clk = _load_ttf(bold=True, mono=True, size=16)
    f_mono = _load_ttf(bold=True, mono=True, size=11)

    # Top dark header bar
    dr.rectangle([0, 0, W_out, hdr_h], fill=(15, 23, 42))
    dr.text(
        (20, hdr_h // 2),
        "ALPAO 64×64 DM — Surface Shape w(t) vs. 1 ms Derivative Δw",
        fill=(248, 250, 252),
        font=f_hdr,
        anchor="lm",
    )

    y_r1 = hdr_h + pad_y // 2
    y_r1_sub = y_r1 + row_hdr_h
    y_r1_img = y_r1_sub + sub_h
    y_r2 = y_r1_img + panel_px + pad_y
    y_r2_sub = y_r2 + row_hdr_h
    y_r2_img = y_r2_sub + sub_h
    y_cbar = y_r2_img + panel_px + pad_y // 2

    # Row header banners
    dr.rectangle([pad_x, y_r1, W_out - pad_x, y_r1 + row_hdr_h - 4], fill=(239, 246, 255))
    dr.text(
        (W_out // 2, y_r1 + (row_hdr_h - 4) // 2),
        "TOP ROW: Instantaneous DM Surface Shape w(x, y, t)  [Direct Optical Surface, No Time Derivative]",
        fill=(30, 58, 138),
        font=f_row,
        anchor="mm",
    )
    dr.rectangle([pad_x, y_r2, W_out - pad_x, y_r2 + row_hdr_h - 4], fill=(241, 245, 249))
    dr.text(
        (W_out // 2, y_r2 + (row_hdr_h - 4) // 2),
        "BOTTOM ROW: 1 ms Consecutive-Exposure Derivative Δw₁ₘₛ(x, y, t)  [LepICSaBL-E Operator]",
        fill=(51, 65, 85),
        font=f_row,
        anchor="mm",
    )

    xs_col = [pad_x + c * (panel_px + pad_x) for c in range(3)]
    top_subs = (
        f"Shape w(t) — Linear 1× (±{w_lim_1x:.0f} nm)",
        f"Shape w(t) — High-Gain 50× (±{w_lim_50x:.1f} nm)",
        f"Transient w(t) − w_DC — 50× (±{w_lim_50x:.1f} nm)",
    )
    bot_subs = (
        f"1 ms Deriv Δw — Linear 1× (±{d_lim_1x:.0f} nm)",
        f"1 ms Deriv Δw — High-Gain 50× (±{d_lim_50x:.1f} nm)",
        "1 ms Deriv Δw — Per-Frame Autoscale",
    )
    for c in range(3):
        cx = xs_col[c] + panel_px // 2
        dr.text((cx, y_r1_sub + sub_h // 2), top_subs[c], fill=(15, 23, 42), font=f_sub, anchor="mm")
        dr.text((cx, y_r2_sub + sub_h // 2), bot_subs[c], fill=(15, 23, 42), font=f_sub, anchor="mm")

    # Footer diverging RdBu_r colorbar strip
    dr.rectangle([0, y_cbar, W_out, H_out], fill=(248, 250, 252))
    dr.line([(0, y_cbar), (W_out, y_cbar)], fill=(203, 213, 225), width=1)
    cb_w, cb_h = 340, 12
    cb_x0 = (W_out - cb_w) // 2
    cb_y0 = y_cbar + 8
    tpl_arr = np.asarray(tpl, dtype=np.uint8).copy()
    grad_idx = np.linspace(0, 255, cb_w).astype(np.uint8)
    tpl_arr[cb_y0 : cb_y0 + cb_h, cb_x0 : cb_x0 + cb_w] = lut[grad_idx][None, :, :]
    tpl = Image.fromarray(tpl_arr, mode="RGB")
    dr = ImageDraw.Draw(tpl)
    dr.rectangle([cb_x0, cb_y0, cb_x0 + cb_w, cb_y0 + cb_h], outline=(100, 116, 139), width=1)
    dr.text((cb_x0 - 8, cb_y0 + cb_h // 2), "−Full Scale", fill=(30, 64, 175), font=f_sm, anchor="rm")
    dr.text((cb_x0 + cb_w + 8, cb_y0 + cb_h // 2), "+Full Scale", fill=(153, 27, 27), font=f_sm, anchor="lm")
    dr.text((W_out // 2, cb_y0 + cb_h + 11), "0 nm (flat facesheet)  |  20 kHz (50 μs/frame), poke at t = 0.00 ms", fill=(71, 85, 105), font=f_sm, anchor="mm")
    template = np.asarray(tpl, dtype=np.uint8)

    vid_mp4 = out_dir / "dm_shape_vs_deriv_20khz.mp4"
    enc = subprocess.Popen(
        [
            ffmpeg,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{W_out}x{H_out}",
            "-r",
            f"{fps:.4f}",
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(vid_mp4),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert enc.stdin is not None

    poster_saved = False
    poster_target_ms = 3.2
    clk_cx, clk_cy = W_out - 98, hdr_h // 2

    for k in range(n_frames_out):
        si_diff = sim_start + k
        si_raw = lead + si_diff
        t_ms = ((si_diff - k_onset_diff) / rate_hz) * 1e3

        w_raw = surf_nm[si_raw]
        # Dynamic departure from commanded equilibrium (0 before poke, w_DC after poke)
        w_res = (w_raw - w_dc_nm) if (si_raw >= fr_poke) else w_raw
        d_raw = diff_nm[si_diff]

        w_r = _resize_f32(w_raw, panel_px)
        r_r = _resize_f32(w_res, panel_px)
        d_r = _resize_f32(d_raw, panel_px)
        d_auto = max(float(np.max(np.abs(d_r * pup_r))), 1e-6)

        top_imgs = (
            _colorize_pupil_rgb(w_r, pup_r, w_lim_1x, lut),
            _colorize_pupil_rgb(w_r, pup_r, w_lim_50x, lut),
            _colorize_pupil_rgb(r_r, pup_r, w_lim_50x, lut),
        )
        bot_imgs = (
            _colorize_pupil_rgb(d_r, pup_r, d_lim_1x, lut),
            _colorize_pupil_rgb(d_r, pup_r, d_lim_50x, lut),
            _colorize_pupil_rgb(d_r, pup_r, d_auto, lut),
        )

        frame = template.copy()
        for c in range(3):
            x0 = xs_col[c]
            frame[y_r1_img : y_r1_img + panel_px, x0 : x0 + panel_px] = top_imgs[c]
            frame[y_r2_img : y_r2_img + panel_px, x0 : x0 + panel_px] = bot_imgs[c]

        fim = Image.fromarray(frame, mode="RGB")
        dr = ImageDraw.Draw(fim)
        dr.rounded_rectangle(
            [clk_cx - 76, clk_cy - 16, clk_cx + 76, clk_cy + 16],
            radius=8,
            fill=(190, 18, 60),
        )
        dr.text((clk_cx, clk_cy), f"t = {t_ms:+5.2f} ms", fill=(255, 255, 255), font=f_clk, anchor="mm")

        # Live peak/RMS badges on bottom-right Autoscale and top-right Transient panels
        far_w_rms = float(np.std(w_raw[far_ring]))
        dr.rounded_rectangle(
            [xs_col[2] + 6, y_r1_img + panel_px - 22, xs_col[2] + 158, y_r1_img + panel_px - 4],
            radius=4,
            fill=(15, 23, 42),
        )
        dr.text(
            (xs_col[2] + 82, y_r1_img + panel_px - 13),
            f"far RMS {far_w_rms:4.2f} nm",
            fill=(248, 250, 252),
            font=f_mono,
            anchor="mm",
        )
        dr.rounded_rectangle(
            [xs_col[2] + 6, y_r2_img + panel_px - 22, xs_col[2] + 148, y_r2_img + panel_px - 4],
            radius=4,
            fill=(15, 23, 42),
        )
        dr.text(
            (xs_col[2] + 77, y_r2_img + panel_px - 13),
            f"auto ±{d_auto:5.1f} nm",
            fill=(248, 250, 252),
            font=f_mono,
            anchor="mm",
        )

        out_arr = np.asarray(fim, dtype=np.uint8)
        enc.stdin.write(out_arr.tobytes())
        if not poster_saved and t_ms >= poster_target_ms:
            fim.save(out_dir / "dm_shape_vs_deriv_20khz_poster.png")
            poster_saved = True

    enc.stdin.close()
    err_b = enc.stderr.read() if enc.stderr else b""
    rc = enc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}): {err_b.decode('utf-8', 'ignore')}")

    # Render 4x6 High-Res Contact Sheet comparing DM Shape vs 1 ms Derivative across 6 key epochs
    sheet_times = [0.25, 1.0, 2.2, 4.1, 7.1, 11.5]
    sheet_notes = [
        "Overshoot (+29%)",
        "1st Ring Detach",
        "Peak Wave (21 nm)",
        "Rim Reflection",
        "Interference",
        "Conjugate Focus",
    ]
    row_specs = [
        (f"DM Shape w(t)\nLinear 1× (±{w_lim_1x:.0f} nm)", w_lim_1x),
        (f"DM Shape w(t)\nHigh-Gain 50× (±{w_lim_50x:.0f} nm)", w_lim_50x),
        (f"Dynamic Error\nw(t) − w_DC (±{w_lim_50x:.0f} nm)", w_lim_50x),
        (f"1 ms Derivative Δw\nHigh-Gain 50× (±{d_lim_50x:.1f} nm)", d_lim_50x),
    ]

    fig, axes = plt.subplots(4, 6, figsize=(15.8, 10.6), dpi=150)
    fig.patch.set_facecolor("white")
    cmap_obj = matplotlib.colormaps["RdBu_r"].copy()
    cmap_obj.set_bad(color="#1e293b")
    row_mappables: list[Any] = [None] * 4

    for col, (t_ms, note) in enumerate(zip(sheet_times, sheet_notes)):
        step_off = int(round(t_ms * rate_hz * 1e-3))
        i_raw = min(n_total - 1, max(0, fr_poke + step_off))
        i_dif = min(diff_nm.shape[0] - 1, max(0, k_onset_diff + step_off))

        w_raw = np.where(pup, surf_nm[i_raw], np.nan)
        w_res = np.where(pup, surf_nm[i_raw] - w_dc_nm, np.nan)
        d_raw = np.where(pup, diff_nm[i_dif], np.nan)
        panels = (w_raw, w_raw, w_res, d_raw)

        for row in range(4):
            ax = axes[row, col]
            vlim = row_specs[row][1]
            # Flip vertically so row-0-top actuator coords match lower-left poke with origin="lower"
            im = ax.imshow(
                panels[row][::-1],
                origin="lower",
                cmap=cmap_obj,
                vmin=-vlim,
                vmax=vlim,
                interpolation="bilinear",
            )
            ax.set_xticks([])
            ax.set_yticks([])
            if row == 0:
                ax.set_title(f"t = +{t_ms:.2f} ms\n({note})", fontsize=9.2, fontweight="bold", pad=4)
            if col == 0:
                ax.set_ylabel(row_specs[row][0], fontsize=8.8, fontweight="bold")
            if col == 5:
                row_mappables[row] = im

    fig.suptitle(
        "ALPAO 64×64 Magnetic DM — Instantaneous Surface Shape w(x, y, t) vs. 1 ms Time Derivative Δw₁ₘₛ(x, y, t)",
        fontsize=12.4,
        fontweight="bold",
    )
    plt.subplots_adjust(left=0.075, right=0.910, top=0.905, bottom=0.025, wspace=0.06, hspace=0.08)
    for row in range(4):
        pos = axes[row, 5].get_position()
        cax = fig.add_axes([0.922, pos.y0, 0.013, pos.height])
        cb = fig.colorbar(row_mappables[row], cax=cax)
        cb.ax.tick_params(labelsize=8.0)
        cb.set_label("nm", fontsize=8.5, labelpad=3)
    sheet_path = out_dir / "dm_shape_vs_deriv_contact_sheet.png"
    plt.savefig(sheet_path)
    plt.close(fig)

    return {
        "shape_video": vid_mp4.name,
        "shape_poster": "dm_shape_vs_deriv_20khz_poster.png",
        "shape_sheet": sheet_path.name,
        "shape_width": W_out,
        "shape_height": H_out,
        "shape_frames": n_frames_out,
        "shape_fps": fps,
        "shape_duration_s": round(n_frames_out / fps, 1),
        "w_peak_nm": w_peak_nm,
        "w_dc_peak_nm": w_dc_peak_nm,
        "w_lim_1x_nm": w_lim_1x,
        "w_lim_50x_nm": w_lim_50x,
        "d_lim_1x_nm": d_lim_1x,
        "d_lim_50x_nm": d_lim_50x,
        "samples": shape_samples,
    }


def render_video_poster(
    sim_dir: Path,
    out_dir: Path,
    meta: dict[str, Any],
    gain_1x: float = 0.25,
    dt_post_poke_ms: float = 4.1,
    panel_px: int = 256,
    pad: int = 10,
) -> Path:
    """Save a crisp 2x3 poster frame matching dm_poke_sim_20khz.mp4 at peak ripple propagation."""
    n_total = int(meta["n_total"])
    n_diff = int(meta["n_diff"])
    nwf = int(meta["nwf"])
    ncam = int(meta["ncam"])
    rate_hz = float(meta["rate_hz"])
    pre_ms = float(meta["pre_ms"])

    opd = np.fromfile(sim_dir / "dm_opd_20khz.f32", dtype=np.float32).reshape((n_total, nwf, nwf))
    wfs = np.fromfile(sim_dir / "pyrwfs_20khz.f32", dtype=np.float32).reshape((n_total, ncam, ncam))
    pup = np.fromfile(sim_dir / "pup.f32", dtype=np.float32).reshape((nwf, nwf)) > 0.5

    surf = 0.5 * opd
    wfs_diff = _boxcar_1ms_diff(wfs, n_diff)
    dm_diff = _boxcar_1ms_diff(surf, n_diff) * pup[None, :, :]

    wfs_lim = max(gain_1x, 0.05) * float(np.max(np.abs(wfs_diff)))
    dm_lim = max(gain_1x, 0.05) * float(np.max(np.abs(dm_diff)))

    idx = min(
        dm_diff.shape[0] - 1,
        max(0, int(round((pre_ms + dt_post_poke_ms) * rate_hz * 1e-3))),
    )
    w_r = _resize_f32(wfs_diff[idx], panel_px)
    d_r = _resize_f32(dm_diff[idx], panel_px)
    w_auto = max(float(np.max(np.abs(w_r))), 1e-12)
    d_auto = max(float(np.max(np.abs(d_r))), 1e-12)

    top_p = [_norm_gray_u8(w_r, wfs_lim), _norm_gray_u8(w_r, wfs_lim / 50.0), _norm_gray_u8(w_r, w_auto)]
    bot_p = [_norm_gray_u8(d_r, dm_lim), _norm_gray_u8(d_r, dm_lim / 50.0), _norm_gray_u8(d_r, d_auto)]

    H = 2 * panel_px + 3 * pad
    W = 3 * panel_px + 4 * pad
    H += H & 1
    W += W & 1
    canvas = np.full((H, W, 3), 255, dtype=np.uint8)
    for col in range(3):
        x0 = pad + col * (panel_px + pad)
        canvas[pad : pad + panel_px, x0 : x0 + panel_px] = top_p[col][:, :, None]
        y0_b = 2 * pad + panel_px
        canvas[y0_b : y0_b + panel_px, x0 : x0 + panel_px] = bot_p[col][:, :, None]

    poster_path = out_dir / "dm_poke_sim_20khz_poster.png"
    Image.fromarray(canvas, mode="RGB").save(poster_path)
    return poster_path


def render_physics_diagnostics_2x2(
    sim_dir: Path,
    out_dir: Path,
    meta: dict[str, Any],
    bench_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render 2x2 publication-grade ALPAO 64x64 plate PDE diagnostic figure from live cube data."""
    n_total = int(meta["n_total"])
    n_diff = int(meta["n_diff"])
    nwf = int(meta["nwf"])
    nact = int(meta["nact"])
    rate_hz = float(meta["rate_hz"])
    pre_ms = float(meta["pre_ms"])
    fr_poke = int(meta["fr_poke"])
    poke_x = int(meta["poke_x"])
    poke_y = int(meta["poke_y"])

    f0_hz = float(meta["f0_hz"])
    wave_c = float(meta["wave_c_ms"])
    beta = float(meta["bend_beta_m2s"])
    g0 = float(meta["damp_g0"])
    g2 = float(meta["damp_g2"])
    tau_us = float(meta["tau_us"])
    pitch_mm = 1.5
    pitch_m = pitch_mm * 1e-3

    opd = np.fromfile(sim_dir / "dm_opd_20khz.f32", dtype=np.float32).reshape((n_total, nwf, nwf))
    pup = np.fromfile(sim_dir / "pup.f32", dtype=np.float32).reshape((nwf, nwf)) > 0.5
    surf_nm = 0.5 * opd * 1e3
    dm_diff_nm = _boxcar_1ms_diff(surf_nm, n_diff) * pup[None, :, :]
    n_out = dm_diff_nm.shape[0]
    t_diff_ms = (np.arange(n_out) / rate_hz) * 1e3 - pre_ms

    cx = 0.5 * (nwf - 1)
    cy = 0.5 * (nwf - 1)
    px_wf = 1.5 + 4.0 * poke_x
    py_wf = 1.5 + 4.0 * poke_y
    px_per_mm = 4.0 / pitch_mm

    vx = cx - px_wf
    vy = cy - py_wf
    vn = float(np.hypot(vx, vy))
    ux, uy = vx / vn, vy / vn
    s_mm = np.linspace(-46.5, 46.5, 240)
    xs = np.clip(np.round(cx + s_mm * px_per_mm * ux).astype(int), 0, nwf - 1)
    ys = np.clip(np.round(cy + s_mm * px_per_mm * uy).astype(int), 0, nwf - 1)
    s_poke_mm = ((px_wf - cx) * ux + (py_wf - cy) * uy) / px_per_mm

    post_mask = t_diff_ms >= -0.5
    t_hov = t_diff_ms[post_mask]
    hov = dm_diff_nm[post_mask][:, ys, xs]

    yy, xx = np.mgrid[0:nwf, 0:nwf]
    r_poke_act = np.hypot(xx - px_wf, yy - py_wf) / 4.0
    far_ring = pup & (r_poke_act >= 18.0) & (r_poke_act <= 36.0)
    far_vals = dm_diff_nm[:, far_ring]
    far_max = np.max(np.abs(far_vals), axis=1)
    far_rms = np.std(far_vals, axis=1)

    t_abs_ms = ((np.arange(n_total) - fr_poke) / rate_hz) * 1e3
    poke_surf_nm = surf_nm[:, int(round(py_wf)), int(round(px_wf))]
    dc_val = float(np.mean(poke_surf_nm[-20:]))
    poke_norm = poke_surf_nm / max(dc_val, 1e-6)
    peak_overshoot_pct = (float(np.max(poke_norm)) - 1.0) * 100.0

    t_step_s = np.maximum(t_abs_ms * 1e-3, 0.0)
    rc_step = np.where(t_abs_ms >= 0.0, 1.0 - np.exp(-t_step_s / (tau_us * 1e-6)), 0.0)
    w0 = 2.0 * np.pi * f0_hz
    zeta_ref = 0.25
    wd = w0 * np.sqrt(1.0 - zeta_ref**2)
    osc_step = np.where(
        t_abs_ms >= 0.0,
        1.0
        - np.exp(-zeta_ref * w0 * t_step_s)
        * (np.cos(wd * t_step_s) + (zeta_ref / np.sqrt(1.0 - zeta_ref**2)) * np.sin(wd * t_step_s)),
        0.0,
    )

    diam_m = 60.0 * pitch_m
    cyc_pup = np.linspace(0.5, 30.0, 300)
    k_m = 2.0 * np.pi * cyc_pup / diam_m
    lam_disc = 4.0 * np.sin(0.5 * k_m * pitch_m) ** 2 / (pitch_m**2)
    om_plate = np.sqrt(w0**2 + (wave_c**2) * lam_disc + (beta**2) * (lam_disc**2))
    om_mem = np.sqrt(w0**2 + (wave_c**2) * lam_disc)
    f_plate_khz = om_plate / (2.0 * np.pi * 1e3)
    f_mem_khz = om_mem / (2.0 * np.pi * 1e3)
    dlam_dk = (2.0 / pitch_m) * np.sin(k_m * pitch_m)
    vg_ms = (0.5 * (wave_c**2 + 2.0 * (beta**2) * lam_disc) * dlam_dk) / np.maximum(om_plate, 1.0)
    gamma_k = g0 + g2 * (lam_disc * pitch_m**2)
    tau_k_ms = 1e3 / gamma_k

    plt.rcParams.update(
        {
            "font.size": 9.5,
            "axes.titlesize": 10.5,
            "axes.labelsize": 9.5,
            "legend.fontsize": 8.2,
            "axes.grid": True,
            "grid.alpha": 0.28,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.6), dpi=150)
    fig.patch.set_facecolor("white")

    ax = axes[0, 0]
    im = ax.imshow(
        hov.T,
        aspect="auto",
        origin="lower",
        extent=[float(t_hov[0]), float(t_hov[-1]), float(s_mm[0]), float(s_mm[-1])],
        cmap="RdBu_r",
        vmin=-6.0,
        vmax=6.0,
    )
    ax.axhline(s_poke_mm, color="#f59e0b", ls="--", lw=1.1, label=f"Poke ({s_poke_mm:+.1f} mm)")
    ax.axhline(-46.5, color="#334155", ls=":", lw=1.0)
    ax.axhline(46.5, color="#334155", ls=":", lw=1.0, label="Free circular rim (±48 mm)")
    t_ray = np.linspace(0.0, 2.8, 40)
    ax.plot(t_ray, s_poke_mm + 24.0 * t_ray, color="#10b981", ls="-.", lw=1.4, label="~24 m/s phase crest")
    ax.set_title("(a) Space–Time Facesheet Ripple Propagation (1 ms Boxcar-Diff Slice)")
    ax.set_xlabel("Time after poke [ms]")
    ax.set_ylabel("Position along poke diameter [mm]")
    ax.set_xlim(-0.5, 18.0)
    ax.set_ylim(-47.0, 47.0)
    ax.legend(loc="upper right", framealpha=0.90)
    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.set_label("1 ms-diff DM surface [nm]")

    ax = axes[0, 1]
    sel = (t_diff_ms >= 0.0) & (t_diff_ms <= 18.5)
    ax.semilogy(t_diff_ms[sel], np.maximum(far_max[sel], 1e-2), color="#be123c", lw=2.0, label="Far-ring max |Δw₁ₘₛ|")
    ax.semilogy(t_diff_ms[sel], np.maximum(far_rms[sel], 1e-2), color="#2563eb", lw=1.8, label="Far-ring RMS Δw₁ₘₛ")
    t_env = np.linspace(3.5, 18.5, 100)
    idx_ref = int(np.argmin(np.abs(t_diff_ms - 4.0)))
    env_max = float(far_max[idx_ref]) * np.exp(-(t_env - 4.0) * g0 * 1e-3)
    ax.semilogy(
        t_env,
        env_max,
        color="#0f172a",
        ls="--",
        lw=1.3,
        label=f"Viscous envelope exp(-γ₀ t), τ={1e3/g0:.1f} ms",
    )
    ax.set_title("(b) Far-Ring Ripple Decay (18–36 act) & Poked-Actuator Step Response")
    ax.set_xlabel("Time after poke [ms]")
    ax.set_ylabel("1 ms-diff DM surface [nm]")
    ax.set_xlim(0.0, 18.5)
    ax.set_ylim(0.10, 28.0)
    ax.legend(loc="lower left", framealpha=0.92)

    ins = ax.inset_axes([0.52, 0.59, 0.45, 0.36])
    isel = (t_abs_ms >= -0.3) & (t_abs_ms <= 4.0)
    ins.plot(t_abs_ms[isel], poke_norm[isel], color="#be123c", lw=1.8, label="Plate PDE (force)")
    ins.plot(t_abs_ms[isel], rc_step[isel], color="#64748b", ls="--", lw=1.2, label="RC (mode 1)")
    ins.plot(t_abs_ms[isel], osc_step[isel], color="#0284c7", ls=":", lw=1.3, label="2nd-ord (mode 2)")
    ins.axhline(1.0, color="#0f172a", lw=0.7, alpha=0.5)
    ins.set_title(f"Poked act (peak={dc_val:.0f} nm, OS={peak_overshoot_pct:+.1f}%)", fontsize=7.6)
    ins.set_xlabel("t [ms]", fontsize=7.2, labelpad=1.5)
    ins.set_ylabel("w / w_DC", fontsize=7.2, labelpad=1.5)
    ins.tick_params(labelsize=7.0)
    ins.set_ylim(-0.05, 1.55)
    ins.legend(loc="lower right", fontsize=6.6, framealpha=0.92)

    ax = axes[1, 0]
    k_emp = np.array([4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16], dtype=float)
    f_emp_khz = np.array([1.419, 1.484, 1.484, 1.548, 1.613, 1.677, 1.806, 2.194, 2.323, 2.452, 2.581, 2.710])
    l1 = ax.plot(cyc_pup, f_plate_khz, color="#2563eb", lw=2.1, label="Model f(k) [kHz]")
    l2 = ax.plot(cyc_pup, f_mem_khz, color="#64748b", ls="--", lw=1.3, label="Membrane-only (β=0)")
    sc = ax.scatter(k_emp, f_emp_khz, color="#0f172a", marker="D", s=26, zorder=5, label="LepICSaBL-E empirical |F(k,f)|²")
    ax.axhline(1.0, color="#94a3b8", ls=":", lw=1.0, label="1 ms boxcar nulls (1, 2 kHz)")
    ax.axhline(2.0, color="#94a3b8", ls=":", lw=1.0)
    ax.set_title("(c) Empirical LepICSaBL-E Dispersion Fit, Group Speed & Modal Decay")
    ax.set_xlabel("Spatial frequency [cycles / clear pupil] (Nyquist = 30 c/pup)")
    ax.set_ylabel("Modal frequency f(k) [kHz]", color="#2563eb")
    ax.tick_params(axis="y", labelcolor="#2563eb")
    ax.set_xlim(0.0, 24.0)
    ax.set_ylim(0.5, 4.8)

    ax2 = ax.twinx()
    ax2.grid(False)
    l3 = ax2.plot(cyc_pup, vg_ms, color="#be123c", lw=1.8, label="Group velocity v_g(k) [m/s]")
    l4 = ax2.plot(cyc_pup, tau_k_ms, color="#047857", ls="-.", lw=1.6, label="Modal decay τ(k) [ms]")
    ax2.set_ylabel("v_g [m/s]  /  τ(k) [ms]", color="#be123c")
    ax2.tick_params(axis="y", labelcolor="#be123c")
    ax2.set_ylim(0.0, 32.0)
    h_null = ax.get_lines()[2]
    handles = [*l1, *l2, sc, h_null, *l3, *l4]
    ax.legend(handles, [h.get_label() for h in handles], loc="upper left", fontsize=7.4, framealpha=0.92)

    ax = axes[1, 1]
    labels = [r["short_label"] for r in bench_rows]
    cpu_us = [float(r["cpu_us"]) for r in bench_rows]
    gpu_us = [float(r["cuda_us"]) for r in bench_rows]
    y_pos = np.arange(len(labels))
    bar_h = 0.34
    b_cpu = ax.barh(y_pos + bar_h / 2, cpu_us, height=bar_h, color="#64748b", label="CPU (4 thr)")
    b_gpu = ax.barh(y_pos - bar_h / 2, gpu_us, height=bar_h, color="#be123c", label="CUDA (RTX PRO 6000)")
    ax.axvline(125.0, color="#047857", ls="--", lw=1.4, label="8 kHz (4× ovs) tick budget (125 μs)")
    for bars, col in ((b_cpu, "#334155"), (b_gpu, "#9f1239")):
        for bar in bars:
            w = float(bar.get_width())
            ax.text(
                w + 4.0,
                bar.get_y() + bar.get_height() / 2.0,
                f"{w:.1f} μs ({1000.0/w:.1f} kHz)",
                va="center",
                ha="left",
                fontsize=8.2,
                color=col,
                fontweight="bold",
            )
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Per-tick latency (ALPAO plate at 8 kHz / 4× ovs, dt = 125 μs, nsub = 5) [μs]")
    ax.set_title("(d) DM Engine Latency: ALPAO 64×64 Plate PDE vs. MEMS 50×50 RC")
    ax.set_xlim(0.0, max(max(cpu_us) * 1.45, 360.0))
    ax.legend(loc="upper right", framealpha=0.92)

    fig.suptitle(
        "ALPAO 64×64 Magnetic DM Coupled Facesheet PDE (dyn_mode = \"plate\") — "
        "Physics, Dispersion & Real-Time Performance",
        fontsize=12.0,
        fontweight="bold",
    )
    plt.tight_layout(rect=[0.0, 0.0, 1.0, 0.955])
    fig_path = out_dir / "dm_plate_physics_diagnostics_2x2.png"
    plt.savefig(fig_path)
    plt.close(fig)

    return {
        "poked_dc_surf_nm": dc_val,
        "poked_overshoot_pct": peak_overshoot_pct,
        "vg_5cpup_ms": float(np.interp(5.0, cyc_pup, vg_ms)),
        "vg_15cpup_ms": float(np.interp(15.0, cyc_pup, vg_ms)),
        "f_nyquist_khz": float(f_plate_khz[-1]),
        "tau_dc_ms": float(1e3 / g0),
        "tau_15cpup_ms": float(np.interp(15.0, cyc_pup, tau_k_ms)),
    }
