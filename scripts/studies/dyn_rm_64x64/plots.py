# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Publication-grade plots and stroboscopic 3D RM video for the ALPAO 64x64 Plate DM."""

from __future__ import annotations

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

from .acquire import ZONAL_POKES


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


def _unmask_cube(r3_masked: np.ndarray, mask_2d: np.ndarray) -> np.ndarray:
    """Expand [N_t, N_in, N_pix] masked cube back into [N_t, N_in, H, W]."""
    n_t, n_in, _ = r3_masked.shape
    h, w = mask_2d.shape
    out = np.zeros((n_t, n_in, h, w), dtype=np.float32)
    out[:, :, mask_2d] = r3_masked.astype(np.float32)
    return out


def _colorize_diverging(img: np.ndarray, vmax: float) -> np.ndarray:
    """Map signed 2D field to RGB uint8 using RdBu_r-style diverging perceptual palette."""
    v = max(float(vmax), 1e-12)
    x = np.clip(0.5 + 0.5 * (img / v), 0.0, 1.0)
    cmap = matplotlib.colormaps["RdBu_r"]
    rgb = (cmap(x)[:, :, :3] * 255.0 + 0.5).astype(np.uint8)
    return rgb


def _colorize_gray(img: np.ndarray, vmax: float) -> np.ndarray:
    v = max(float(vmax), 1e-12)
    x = np.clip(0.5 + 0.5 * (img / v), 0.0, 1.0)
    g = (x * 255.0 + 0.5).astype(np.uint8)
    return np.repeat(g[:, :, None], 3, axis=2)


def _resize_rgb(arr: np.ndarray, size: int) -> np.ndarray:
    if arr.shape[0] == size and arr.shape[1] == size:
        return arr
    return np.asarray(Image.fromarray(arr).resize((size, size), resample=Image.BILINEAR))


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
            "font.size": 10.5,
            "axes.titlesize": 11.5,
            "axes.labelsize": 10.5,
            "legend.fontsize": 9.0,
        }
    )


def render_wave_video_and_contact_sheet(
    raw_dir: Path,
    out_dir: Path,
    summary: dict[str, Any],
    fps: float = 12.0,
) -> dict[str, Any]:
    """Render stroboscopic 3D RM MP4, poster frame, and 4x6 multi-radius contact sheet."""
    mask_2d = fits.getdata(raw_dir / "wfsmask.fits") > 0.5
    r3_m = fits.getdata(raw_dir / "zonal4_resp3D.fits").astype(np.float32)
    stat_m = fits.getdata(raw_dir / "zonal4_resp3D_static.fits").astype(np.float32)

    z4 = summary["zonal_4seg"]
    q0 = int(z4["q0_bin"])
    n_sub = int(z4["nbsubfr"])
    dt_ms = float(z4["dt_us"]) * 1.0e-3
    n_t = r3_m.shape[0]
    t_ms = (np.arange(n_t) - q0 + 0.5) * dt_ms

    cube_2d = _unmask_cube(r3_m, mask_2d)  # [N_t, 4, 160, 160]
    stat_2d = np.zeros((4, 160, 160), dtype=np.float32)
    stat_2d[:, mask_2d] = stat_m

    # Dynamic residual Y(tau) - Y_static and 1 ms exposure difference Y(tau) - Y(tau - 1 ms)
    dyn_2d = cube_2d - stat_2d[None, :, :, :]
    diff1ms = np.zeros_like(cube_2d)
    diff1ms[n_sub:] = cube_2d[n_sub:] - cube_2d[:-n_sub]

    # Scales based on mode 0 (LepICSaBL-E) steady-state peak
    lim_step = 0.85 * float(np.max(np.abs(cube_2d[q0:, 0])))
    lim_dyn = lim_step / 10.0
    lim_diff = lim_step / 14.0

    # Video canvas: 2 rows x 3 cols of 276x276 panels + generous header/subheader/footer spacing
    ps = 276
    pad = 14
    hdr_h = 54
    sub_h = 30
    ftr_h = 34
    w_tot = 3 * ps + 4 * pad
    h_tot = hdr_h + 2 * (sub_h + ps + pad) + ftr_h
    w_tot += w_tot & 1
    h_tot += h_tot & 1

    f_hdr = _load_ttf(bold=True, size=16)
    f_sub = _load_ttf(bold=True, size=12)
    f_mono = _load_ttf(bold=True, mono=True, size=14)
    f_ftr = _load_ttf(bold=False, size=12)

    base_im = Image.new("RGB", (w_tot, h_tot), (255, 255, 255))
    dr = ImageDraw.Draw(base_im)
    dr.rectangle([0, 0, w_tot, hdr_h], fill=(15, 23, 42))
    dr.text(
        (16, 16),
        "ALPAO 64×64 Plate DM · Live 3D RM (1 kHz PyWFS)",
        fill=(248, 250, 252),
        font=f_hdr,
    )

    row_titles = [
        [
            "(22,23): Raw 1 ms Step Y(τ) [1×]",
            "(22,23): Wave Y − Y_static [10×]",
            "(22,23): 1 ms Diff ΔY₁ₘₛ [14×]",
        ],
        [
            "Inner (31,43): Wave [10×]",
            "Mid-Out (49,31): Wave [10×]",
            "Free Rim (57,31): Wave [10×]",
        ],
    ]

    panel_xy: list[list[tuple[int, int]]] = []
    for row in range(2):
        y_sub = hdr_h + row * (sub_h + ps + pad)
        dr.rectangle([0, y_sub, w_tot, y_sub + sub_h], fill=(241, 245, 249))
        dr.line([(0, y_sub + sub_h - 1), (w_tot, y_sub + sub_h - 1)], fill=(203, 213, 225))
        r_xy: list[tuple[int, int]] = []
        for col in range(3):
            x0 = pad + col * (ps + pad)
            y0 = y_sub + sub_h + (pad // 2)
            dr.text((x0 + 4, y_sub + 7), row_titles[row][col], fill=(15, 23, 42), font=f_sub)
            r_xy.append((x0, y0))
        panel_xy.append(r_xy)

    y_ftr = h_tot - ftr_h
    dr.rectangle([0, y_ftr, w_tot, h_tot], fill=(248, 250, 252))
    dr.line([(0, y_ftr), (w_tot, y_ftr)], fill=(203, 213, 225))
    dr.text(
        (16, y_ftr + 9),
        f"cacaoac-measdynresp wall-clock stroboscopic (NBsubfr={n_sub}, Δt={z4['dt_us']:.1f} μs, "
        f"jitter={z4['jitter_us']:.2f} μs, ndrop={z4['dropped_frames']}) · Subaru J-band PyWFS",
        fill=(51, 65, 85),
        font=f_ftr,
    )
    base_np = np.asarray(base_im, dtype=np.uint8)

    mp4_path = out_dir / "dm64_3drm_wave.mp4"
    poster_path = out_dir / "dm64_3drm_wave_poster.png"
    ffmpeg = _find_ffmpeg()
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
        f"{w_tot}x{h_tot}",
        "-r",
        f"{fps:.2f}",
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
        str(mp4_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None

    poster_idx = min(n_t - 1, q0 + int(round(3.5 / dt_ms)))
    # Render t = -1.0 ms to +16.0 ms (136 frames @ 12 fps = 11.3 s)
    end_idx = min(n_t, q0 + int(round(16.0 / dt_ms)))

    for k in range(end_idx):
        frame = base_np.copy()
        panels = [
            [
                _colorize_diverging(cube_2d[k, 0], lim_step),
                _colorize_diverging(dyn_2d[k, 0], lim_dyn),
                _colorize_gray(diff1ms[k, 0], lim_diff),
            ],
            [
                _colorize_diverging(dyn_2d[k, 1], lim_dyn),
                _colorize_diverging(dyn_2d[k, 2], lim_dyn),
                _colorize_diverging(dyn_2d[k, 3], lim_dyn * 1.4),
            ],
        ]
        for r in range(2):
            for c in range(3):
                x0, y0 = panel_xy[r][c]
                frame[y0 : y0 + ps, x0 : x0 + ps] = _resize_rgb(panels[r][c], ps)

        im_f = Image.fromarray(frame)
        dr_f = ImageDraw.Draw(im_f)
        tag = f"τ = {t_ms[k]:+6.2f} ms  (bin {k:03d}/{end_idx - 1:03d})"
        dr_f.rectangle([w_tot - 265, 11, w_tot - 12, 42], fill=(30, 41, 59))
        dr_f.text((w_tot - 256, 18), tag, fill=(56, 189, 248), font=f_mono)
        out_arr = np.asarray(im_f, dtype=np.uint8)
        proc.stdin.write(out_arr.tobytes())
        if k == poster_idx:
            im_f.save(poster_path)

    proc.stdin.close()
    err_bytes = proc.stderr.read() if proc.stderr else b""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}): {err_bytes.decode(errors='ignore')}")

    # Contact sheet: 4 rows (4 actuators) x 6 timestamps showing dynamic wave residual Y - Y_DC
    _set_mpl_style()
    t_snaps = [1.25, 2.25, 3.50, 5.25, 8.00, 12.00]
    fig, axes = plt.subplots(4, len(t_snaps), figsize=(14.5, 9.6), constrained_layout=True)
    for r, item in enumerate(ZONAL_POKES):
        scale_r = lim_dyn * (1.4 if r == 3 else 1.0)
        for c, ts in enumerate(t_snaps):
            ax = axes[r, c]
            idx = min(n_t - 1, max(0, q0 + int(round(ts / dt_ms))))
            ax.imshow(
                dyn_2d[idx, r],
                cmap="RdBu_r",
                vmin=-scale_r,
                vmax=scale_r,
                origin="lower",
                interpolation="nearest",
            )
            ax.set_xticks([])
            ax.set_yticks([])
            if r == 0:
                ax.set_title(f"τ = +{t_ms[idx]:.2f} ms", fontsize=11)
            if c == 0:
                ax.set_ylabel(
                    f"{item['label']}\nr = {z4['per_actuator'][r]['radius_mm']:.1f} mm",
                    fontsize=9.5,
                    fontweight="bold",
                )
    fig.suptitle(
        f"Live 3D RM Dynamic Wave Residual Y(τ) − Y_static Across 4 Actuator Radii "
        f"(Fixed 1 kHz J-band PyWFS, Δt = {z4['dt_us']:.1f} μs)",
        fontsize=13,
        fontweight="bold",
    )
    sheet_path = out_dir / "dm64_3drm_zonal_contact_sheet.png"
    fig.savefig(sheet_path, dpi=160)
    plt.close(fig)

    return {
        "video_file": mp4_path.name,
        "poster_file": poster_path.name,
        "sheet_file": sheet_path.name,
        "n_frames": int(end_idx),
        "fps": fps,
        "duration_s": float(end_idx / fps),
        "width": int(w_tot),
        "height": int(h_tot),
    }


def render_radial_and_timing_2x2(
    raw_dir: Path,
    out_dir: Path,
    summary: dict[str, Any],
) -> Path:
    """Render 2x2 zonal step dynamics, PyWFS Hovmoller wave diagram, timing & static parity."""
    _set_mpl_style()
    mask_2d = fits.getdata(raw_dir / "wfsmask.fits") > 0.5
    r3_z4 = fits.getdata(raw_dir / "zonal4_resp3D.fits").astype(np.float64)
    r3_pp = fits.getdata(raw_dir / "zonal4_pp_resp3D.fits").astype(np.float64)
    stat_z4 = fits.getdata(raw_dir / "zonal4_resp3D_static.fits").astype(np.float64)
    tmean_z4 = fits.getdata(raw_dir / "zonal4_resp3D_tmean.fits").astype(np.float64)
    lin_2d = fits.getdata(raw_dir / "zonal4_measlinresp.fits").astype(np.float64)[:, mask_2d]

    z4 = summary["zonal_4seg"]
    q0 = int(z4["q0_bin"])
    dt_ms = float(z4["dt_us"]) * 1.0e-3
    n_t = r3_z4.shape[0]
    t_ms = (np.arange(n_t) - q0 + 0.5) * dt_ms

    colors = ["#2563eb", "#059669", "#d97706", "#dc2626"]
    fig, axes = plt.subplots(2, 2, figsize=(14.0, 9.6), constrained_layout=True)

    # Panel (a): Normalized WFS RMS step response across 4 actuator radii
    ax = axes[0, 0]
    for m, item in enumerate(ZONAL_POKES):
        rms_t = np.sqrt(np.mean(r3_z4[:, m, :] ** 2, axis=1))
        stat_rms = float(np.sqrt(np.mean(stat_z4[m] ** 2)))
        ov = z4["per_actuator"][m]["overshoot_pct"]
        ax.plot(
            t_ms,
            rms_t / max(stat_rms, 1e-12),
            color=colors[m],
            lw=2.0,
            label=f"{item['label']} (+{ov:.1f}% pk)",
        )
    ax.axvline(0.0, color="#64748b", ls="--", lw=1.0, label="Poke onset τ = 0")
    ax.axhline(1.0, color="#0f172a", ls=":", lw=1.0)
    ax.axhspan(0.97, 1.03, color="#94a3b8", alpha=0.14)
    ax.set_xlim(-1.0, 18.0)
    ax.set_ylim(-0.05, 1.45)
    ax.set_xlabel("Lag after DM command τ [ms]")
    ax.set_ylabel("Normalized PyWFS RMS response ‖Y(τ)‖ / ‖Y_static‖")
    ax.set_title("(a) 64×64 ALPAO Plate Step Response vs. Actuator Radius")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white")

    # Panel (b): Space-time Hovmoller wave diagram in a single PyWFS sub-pupil (mode 0)
    ax = axes[0, 1]
    cube_2d = _unmask_cube(r3_z4, mask_2d)
    stat_2d = np.zeros((4, 160, 160), dtype=np.float64)
    stat_2d[:, mask_2d] = stat_z4
    dyn_m0 = cube_2d[:, 0, :, :] - stat_2d[0][None, :, :]
    # Upper-left PyWFS sub-pupil sits near [0:80, 0:80]; take diagonal chord across sub-pupil
    sub_mask = mask_2d[:80, :80]
    ys_m, xs_m = np.where(sub_mask)
    cy_p, cx_p = float(np.mean(ys_m)), float(np.mean(xs_m))
    rad_p = 0.5 * (float(xs_m.max() - xs_m.min()) + float(ys_m.max() - ys_m.min())) * 0.5
    s_frac = np.linspace(-0.96, 0.96, 120)
    ang = np.deg2rad(42.0)
    xs_c = np.clip(np.round(cx_p + s_frac * rad_p * np.cos(ang)).astype(int), 0, 79)
    ys_c = np.clip(np.round(cy_p + s_frac * rad_p * np.sin(ang)).astype(int), 0, 79)
    hov = dyn_m0[:, ys_c, xs_c]
    wave_start = min(n_t - 1, q0 + int(round(2.2 / dt_ms)))
    v_hov = float(np.percentile(np.abs(hov[wave_start:]), 99.2))
    im = ax.imshow(
        hov.T,
        aspect="auto",
        origin="lower",
        cmap="RdBu_r",
        vmin=-v_hov,
        vmax=v_hov,
        extent=[t_ms[0], t_ms[-1], -45.0, 45.0],
    )
    ax.axvline(0.0, color="#0f172a", ls="--", lw=1.0)
    ax.axvline(1.0, color="#0f172a", ls=":", lw=1.0, alpha=0.7)
    ax.set_xlim(-0.5, 14.5)
    ax.set_xlabel("Lag after DM command τ [ms]")
    ax.set_ylabel("Sub-pupil diagonal chord position [mm on DM]")
    ax.set_title("(b) Space–Time Wave & Free-Rim Reflection in PyWFS 3D RM")
    fig.colorbar(im, ax=ax, label="Dynamic PyWFS residual Y − Y_static [ADU/μm]", pad=0.02)

    # Panel (c): Wall-clock repeatability (pokemode=0 vs pokemode=1) & sub-frame timestamp linearity
    ax = axes[1, 0]
    m0_rms0 = np.sqrt(np.mean(r3_z4[:, 0, :] ** 2, axis=1))
    m0_rms1 = np.sqrt(np.mean(r3_pp[:, 0, :] ** 2, axis=1))
    norm0 = float(np.sqrt(np.mean(stat_z4[0] ** 2)))
    ax.plot(t_ms, m0_rms0 / norm0, color="#2563eb", lw=2.2, label="pokemode=0 (0→+a→0→−a→0)")
    ax.plot(
        t_ms,
        m0_rms1 / norm0,
        color="#f97316",
        ls="--",
        lw=1.8,
        label=f"pokemode=1 (+a↔−a), r = {z4['corr_vs_pokemode1']:.5f}",
    )
    ax.set_xlim(0.5, 9.0)
    ax.set_xlabel("Lag after DM command τ [ms]")
    ax.set_ylabel("Normalized PyWFS RMS response")
    ax.set_title(
        f"(c) Stroboscopic Repeatability & Timing "
        f"(jitter={z4['jitter_us']:.2f} μs, ndrop={z4['dropped_frames']})"
    )
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white")

    # Inset: measured bin timestamp residual (tmean - ideal) in microseconds
    ax_in = ax.inset_axes([0.48, 0.29, 0.48, 0.34])
    t_ideal_ms = (np.arange(n_t - q0) + 0.5) * dt_ms
    t_res_us = (tmean_z4[q0:, 0] * 1.0e3 - t_ideal_ms) * 1.0e3
    ax_in.plot(t_ideal_ms, t_res_us, color="#0f766e", lw=1.1)
    ax_in.axhline(0.0, color="#64748b", ls=":", lw=0.8)
    ax_in.set_title(f"t_mean − t_grid (RMS {z4['tmean_linearity_rms_us']:.1f} μs)", fontsize=8.5)
    ax_in.set_xlabel("τ [ms]", fontsize=8)
    ax_in.set_ylabel("Δt [μs]", fontsize=8)
    ax_in.tick_params(labelsize=7.5)
    ax_in.grid(True, alpha=0.5)

    # Panel (d): Static tail vs cacaoac-measlinresp 2D RM parity scatter
    ax = axes[1, 1]
    for m, item in enumerate(ZONAL_POKES):
        sub_s = slice(None, None, 4)
        ax.scatter(
            lin_2d[m, sub_s],
            stat_z4[m, sub_s],
            s=8,
            alpha=0.55,
            color=colors[m],
            label=f"{item['short']} (err {z4['per_actuator'][m]['static_vs_measlinresp_pct']:.2f}%)",
        )
    lim_sc = float(np.max(np.abs(lin_2d))) * 1.05
    ax.plot([-lim_sc, lim_sc], [-lim_sc, lim_sc], color="#0f172a", ls="--", lw=1.1)
    ax.set_xlim(-lim_sc, lim_sc)
    ax.set_ylim(-lim_sc, lim_sc)
    ax.set_xlabel("cacaoac-measlinresp 2D static RM [ADU/μm]")
    ax.set_ylabel("cacaoac-measdynresp settled tail [ADU/μm]")
    ax.set_title(
        f"(d) Static-Tail Parity vs. measlinresp (rel L2 = {z4['static_vs_measlinresp_pct']:.2f}%, "
        f"asym = {z4['polarity_asym_pct']:.2f}%)"
    )
    ax.grid(True)
    ax.legend(loc="upper left", frameon=True, facecolor="white", markerscale=1.8)

    fig.suptitle(
        f"ALPAO 64×64 Plate DM Live Wall-Clock 3D RM Calibration Diagnostics "
        f"(1,000 Hz Fixed PyWFS, {int(z4['nbsubfr'])}× Stroboscopic)",
        fontsize=13,
        fontweight="bold",
    )
    out_path = out_dir / "dm64_3drm_radial_and_timing_2x2.png"
    fig.savefig(out_path, dpi=165)
    plt.close(fig)
    return out_path


def render_modal_28x28_2x2(
    raw_dir: Path,
    out_dir: Path,
    summary: dict[str, Any],
) -> Path:
    """Render 2x2 modal 3D RM diagnostics: dispersion, coupling matrices, settling & PSOL error."""
    _set_mpl_style()
    m3_norm = np.load(raw_dir / "modal28_m3_norm.npy").astype(np.float64)
    m28 = summary["modal_28"]
    q0 = int(m28["q0_bin"])
    dt_ms = float(m28["dt_us"]) * 1.0e-3
    n_t, n_m, _ = m3_norm.shape
    t_ms = (np.arange(n_t) - q0 + 0.5) * dt_ms
    pstats = m28["per_mode_stats"]

    fig, axes = plt.subplots(2, 2, figsize=(14.2, 10.0), constrained_layout=True)

    # Panel (a): Diagonal modal step responses grouped by Zernike radial order n = 1..6
    ax = axes[0, 0]
    ord_colors = {1: "#1d4ed8", 2: "#0284c7", 3: "#059669", 4: "#d97706", 5: "#ea580c", 6: "#be123c"}
    for n_ord in range(1, 7):
        idxs = [s["mode"] for s in pstats if s["n"] == n_ord]
        if not idxs:
            continue
        mean_curve = np.mean([m3_norm[:, i, i] for i in idxs], axis=0)
        ov_mean = float(np.mean([pstats[i]["overshoot_pct"] for i in idxs]))
        ax.plot(
            t_ms,
            mean_curve,
            color=ord_colors[n_ord],
            lw=2.0,
            label=f"Radial order n={n_ord} ({len(idxs)} modes, +{ov_mean:.1f}% pk)",
        )
    ax.axvline(0.0, color="#64748b", ls="--", lw=1.0)
    ax.axhline(1.0, color="#0f172a", ls=":", lw=1.0)
    ax.set_xlim(-0.8, 14.0)
    ax.set_ylim(-0.08, 1.32)
    ax.set_xlabel("Lag after DM command τ [ms]")
    ax.set_ylabel("Normalized modal step response M_ii(τ)")
    ax.set_title("(a) Modal Step-Response Dispersion Across Zernike Radial Orders (Z2–Z29)")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white")

    # Panel (b): 2x2 sub-grid inside axes[0, 1] showing |M_ij(tau)| at 4 timestamps
    axes[0, 1].set_axis_off()
    gs_sub = axes[0, 1].get_subplotspec().subgridspec(
        2, 3, width_ratios=[1.0, 1.0, 0.08], wspace=0.22, hspace=0.34
    )
    snap_ts = [1.5, 2.5, 4.5, 15.0]
    im_m = None
    for sidx, ts in enumerate(snap_ts):
        sax = fig.add_subplot(gs_sub[sidx // 2, sidx % 2])
        k = min(n_t - 1, q0 + int(round(ts / dt_ms)))
        mat = np.log10(np.clip(np.abs(m3_norm[k]), 1e-3, 1.5))
        im_m = sax.imshow(mat, cmap="magma", vmin=-2.8, vmax=0.1, origin="upper")
        sax.set_title(f"τ = +{t_ms[k]:.2f} ms", fontsize=10.0)
        sax.set_xlabel("Poked mode", fontsize=8.5)
        sax.set_ylabel("Sensed mode", fontsize=8.5)
        sax.tick_params(labelsize=8.0)
    cax = fig.add_subplot(gs_sub[:, 2])
    assert im_m is not None
    fig.colorbar(im_m, cax=cax, label="log₁₀ |M_ij(τ)|")

    # Panel (c): Off-diagonal coupling energy vs time (after 25% signal onset)
    ax = axes[1, 0]
    eye = np.eye(n_m)[None, :, :]
    off_norm = np.linalg.norm((m3_norm * (1.0 - eye)).reshape(n_t, -1), axis=1)
    diag_norm = np.linalg.norm((m3_norm * eye).reshape(n_t, -1), axis=1)
    diag_dc_norm = float(np.mean(diag_norm[-2 * int(m28["nbsubfr"]) :]))
    valid_off = diag_norm >= 0.25 * diag_dc_norm
    off_pct = np.where(valid_off, 100.0 * off_norm / np.maximum(diag_norm, 1e-6), 0.0)
    ax.plot(
        t_ms[q0:],
        off_pct[q0:],
        color="#be123c",
        lw=2.2,
        label="Off-diagonal coupling ‖M_off‖/‖M_diag‖",
    )
    ax.fill_between(t_ms[q0:], 0.0, off_pct[q0:], color="#be123c", alpha=0.12)
    ax.axvline(
        m28["peak_off_ms"],
        color="#be123c",
        ls="--",
        lw=1.0,
        label=f"Peak cross-talk {m28['peak_off_pct']:.1f}% @ +{m28['peak_off_ms']:.2f} ms",
    )
    ax.axhline(
        m28["tail_off_pct"],
        color="#334155",
        ls=":",
        lw=1.1,
        label=f"Settled tail floor ({m28['tail_off_pct']:.2f}%)",
    )
    ax.set_xlim(0.0, 17.5)
    ax.set_xlabel("Lag after DM command τ [ms]")
    ax.set_ylabel("Cross-mode coupling energy [%]")
    ax.set_title("(c) Transient Cross-Mode Mechanical Wave Coupling vs. Time")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white")

    # Panel (d): PSOL leakage residual per Zernike mode (2-tap scalar vs 3D dynamic DM observer)
    ax = axes[1, 1]
    psol = m28["psol"]
    modes_j = np.array([s["j_noll"] for s in pstats])
    e_2tap = np.array(psol["rel_2tap_pct_per_mode"])
    e_diag = np.array(psol["rel_diag_pct_per_mode"])
    e_3d = np.array(psol["rel_3d_pct_per_mode"])
    ax.plot(
        modes_j,
        e_2tap,
        "o-",
        color="#dc2626",
        lw=2.0,
        ms=4.5,
        label=f"Current CACAO 2-tap scalar lag ({psol['tot_2tap_rel_pct']:.2f}% RMS)",
    )
    ax.plot(
        modes_j,
        e_diag,
        "s-",
        color="#d97706",
        lw=1.8,
        ms=4.0,
        label=f"3D diagonal-only DM observer ({psol['tot_diag_rel_pct']:.2f}% RMS)",
    )
    ax.plot(
        modes_j,
        e_3d,
        "^-",
        color="#059669",
        lw=2.0,
        ms=4.5,
        label=f"Full 3D MIMO DM observer ({psol['tot_3d_rel_pct']:.2f}% RMS, {psol['reduction_2tap_to_3d_x']:.1f}× lower)",
    )
    ax.set_xlabel("Noll Zernike mode index j (Z2 = Tip/Tilt → Z29 = 6th radial order)")
    ax.set_ylabel("PSOL DM-model residual error [% of DM RMS]")
    ax.set_title("(d) Closed-Loop PSOL Error (1 kHz Kolmogorov Stream)")
    ax.set_yscale("log")
    ax.set_ylim(0.05, max(25.0, float(np.max(e_2tap)) * 1.8))
    ax.grid(True, which="both", alpha=0.6)
    ax.legend(loc="lower right", frameon=True, facecolor="white")

    fig.suptitle(
        f"ALPAO 64×64 Plate DM 28×28 Modal 3D Response Matrix "
        f"(Z2–Z29, {int(m28['nbsubfr'])} kHz Stroboscopic Calibration)",
        fontsize=13,
        fontweight="bold",
    )
    out_path = out_dir / "dm64_3drm_modal_28x28_2x2.png"
    fig.savefig(out_path, dpi=165)
    plt.close(fig)
    return out_path


def render_exposure_deconv_1x2(
    raw_dir: Path,
    out_dir: Path,
    summary: dict[str, Any],
) -> tuple[Path, dict[str, float]]:
    """Render fixed 1 ms exposure boxcar transfer function & regularized Wiener deconvolution."""
    _set_mpl_style()
    r3_z4 = fits.getdata(raw_dir / "zonal4_resp3D.fits").astype(np.float64)
    stat_z4 = fits.getdata(raw_dir / "zonal4_resp3D_static.fits").astype(np.float64)
    z4 = summary["zonal_4seg"]
    q0 = int(z4["q0_bin"])
    n_sub = int(z4["nbsubfr"])
    dt_s = float(z4["dt_us"]) * 1.0e-6
    t_exp_s = float(n_sub) * dt_s  # 1.0 ms fixed exposure
    n_t = r3_z4.shape[0]
    t_ms = (np.arange(n_t) - q0 + 0.5) * dt_s * 1.0e3

    # Project each actuator's 3D PyWFS response onto its own static spatial pattern -> 1D step s(t)
    w_m0 = stat_z4[0] / max(float(np.dot(stat_z4[0], stat_z4[0])), 1e-18)
    y_step_m0 = r3_z4[:, 0, :] @ w_m0  # normalized to 1.0 at steady state
    w_m3 = stat_z4[3] / max(float(np.dot(stat_z4[3], stat_z4[3])), 1e-18)
    y_step_m3 = r3_z4[:, 3, :] @ w_m3

    # Differentiate step -> exposure-integrated impulse response h_raw[n]
    h_raw_m0 = np.diff(y_step_m0, prepend=0.0)
    h_raw_m3 = np.diff(y_step_m3, prepend=0.0)

    # Zero-padded FFT for frequency spectrum & regularized Wiener deconvolution of 1 ms boxcar
    n_fft = 1024
    freqs = np.fft.rfftfreq(n_fft, d=dt_s)
    h_box = np.zeros(n_fft, dtype=np.float64)
    h_box[:n_sub] = 1.0 / float(n_sub)
    H_box = np.fft.rfft(h_box)

    H_m0 = np.fft.rfft(h_raw_m0, n=n_fft)
    H_m3 = np.fft.rfft(h_raw_m3, n=n_fft)

    # Wiener filter with zero DC bias (reg[0]=0 -> exact steady-state gain 1.0) & high-freq rolloff
    nyq_hz = 0.5 / dt_s
    eff_khz = (1.0 / dt_s) / 1.0e3
    f_hp = (freqs / 550.0) ** 2
    reg = 0.015 * (f_hp / (1.0 + f_hp)) + 0.08 * (freqs / (0.95 * nyq_hz)) ** 4
    W_deconv = np.conj(H_box) / (np.abs(H_box) ** 2 + reg)
    h_dec_m0 = np.fft.irfft(H_m0 * W_deconv, n=n_fft)[:n_t]
    h_dec_m3 = np.fft.irfft(H_m3 * W_deconv, n=n_fft)[:n_t]
    s_dec_m0 = np.cumsum(h_dec_m0)
    s_dec_m3 = np.cumsum(h_dec_m3)
    # Shift by +0.5*T_exp so deconvolved instantaneous step aligns in physical time with exposure midpoint
    t_inst_ms = t_ms - 0.5 * t_exp_s * 1.0e3

    raw_ov_m0 = (float(np.max(y_step_m0[q0:])) - 1.0) * 100.0
    dec_ov_m0 = (float(np.max(s_dec_m0[q0:])) - 1.0) * 100.0
    raw_ov_m3 = (float(np.max(y_step_m3[q0:])) - 1.0) * 100.0
    dec_ov_m3 = (float(np.max(s_dec_m3[q0:])) - 1.0) * 100.0

    fig, axes = plt.subplots(1, 2, figsize=(13.8, 5.2), constrained_layout=True)

    # Left panel: Frequency transfer functions & 1 ms sinc nulls
    ax = axes[0]
    sinc_mag = np.abs(np.sinc(freqs * t_exp_s))
    ax.plot(freqs, sinc_mag, color="#64748b", ls="--", lw=1.8, label="|sinc(f · T_exp)| (1.0 ms camera)")
    ax.plot(
        freqs,
        np.abs(H_m0) / max(float(np.abs(H_m0[0])), 1e-12),
        color="#2563eb",
        lw=2.0,
        label="Measured raw 3D RM |H(f)| — (22,23)",
    )
    ax.plot(
        freqs,
        np.abs(H_m3) / max(float(np.abs(H_m3[0])), 1e-12),
        color="#dc2626",
        lw=1.8,
        alpha=0.85,
        label="Measured raw 3D RM |H(f)| — Free Rim (57,31)",
    )
    ax.axvline(1000.0, color="#be123c", ls=":", lw=1.3, label="f₀ = 1 kHz & 1st exposure null")
    ax.axvline(2000.0, color="#be123c", ls=":", lw=1.0, alpha=0.6)
    ax.set_xlim(0.0, nyq_hz * 0.98)
    ax.set_ylim(0.0, 1.15)
    ax.set_xlabel("Temporal frequency f [Hz]")
    ax.set_ylabel("Normalized magnitude |H(f)|")
    ax.set_title(f"(a) Fixed 1 ms Exposure vs. {eff_khz:.0f} kHz Stroboscopic Spectrum")
    ax.grid(True)
    ax.legend(loc="upper right", frameon=True, facecolor="white")

    # Right panel: Raw 1 ms exposure-integrated step vs Wiener-deconvolved instantaneous step
    ax = axes[1]
    ax.plot(
        t_ms,
        y_step_m0,
        color="#2563eb",
        ls="--",
        lw=1.8,
        label=f"Raw 1 ms-integrated (22,23) (+{raw_ov_m0:.1f}% pk)",
    )
    ax.plot(
        t_inst_ms,
        s_dec_m0,
        color="#1d4ed8",
        lw=2.3,
        label=f"Wiener-deconvolved (22,23) (+{dec_ov_m0:.1f}% pk)",
    )
    ax.plot(
        t_ms,
        y_step_m3,
        color="#f97316",
        ls="--",
        lw=1.7,
        label=f"Raw 1 ms-integrated Rim (57,31) (+{raw_ov_m3:.1f}% pk)",
    )
    ax.plot(
        t_inst_ms,
        s_dec_m3,
        color="#dc2626",
        lw=2.2,
        label=f"Wiener-deconvolved Rim (57,31) (+{dec_ov_m3:.1f}% pk)",
    )
    ax.axvline(1.0, color="#64748b", ls=":", lw=1.1, label="Hardware transport delay (1.0 ms)")
    ax.axhline(1.0, color="#0f172a", ls=":", lw=0.9)
    ax.set_xlim(0.0, 8.0)
    ax.set_ylim(-0.08, 1.55)
    ax.set_xlabel("Physical time after DM command [ms]")
    ax.set_ylabel("Projected step response (static = 1.0)")
    ax.set_title("(b) Regularized Boxcar Deconvolution Preview")
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor="white")

    out_path = out_dir / "dm64_3drm_exposure_deconv_1x2.png"
    fig.savefig(out_path, dpi=165)
    plt.close(fig)
    return out_path, {
        "raw_overshoot_m0_pct": raw_ov_m0,
        "deconv_overshoot_m0_pct": dec_ov_m0,
        "raw_overshoot_m3_pct": raw_ov_m3,
        "deconv_overshoot_m3_pct": dec_ov_m3,
    }
