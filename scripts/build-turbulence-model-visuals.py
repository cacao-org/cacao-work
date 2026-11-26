#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Generate publication-quality visuals for the Default Turbulence & Perturbation Model page.

Synthesizes 5 high-DPI 2x2 diagnostic figures directly from the exact mathematical models
implemented in `AtmosphericTurbulenceSimul` (`atmturb_profile.c`, `atmturb_seeing.c`,
`atmturb_dynwind.c`) and `cacaosim` (`cacaosim_pupil.c`, `cacaosim_perturb.c`) and writes them
into `scripts/report_site/static/img/turbulence/`.
"""

from __future__ import annotations

import argparse
from collections import deque
import math
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from report_site.extractors.turbulence_model import (  # noqa: E402
    DEFAULT_DYNWIND_SPEC,
    DEFAULT_PETAL_RMS_NM,
    DEFAULT_PETAL_TAU_S,
    DEFAULT_SEEING_ARCSEC,
    DEFAULT_TEL_DIAM_M,
    DEFAULT_VIB_MODES,
    DEFAULT_VIB_RMS_NM,
    compute_atmosphere_stats,
    compute_petaling_stats,
    compute_piston_removed_opd_nm,
    compute_vibration_stats,
    get_normalized_layers,
    solve_r0_for_seeing_m,
)

DEFAULT_OUT_DIR = SCRIPT_DIR / "report_site" / "static" / "img" / "turbulence"


def _set_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "xtick.labelsize": 8.6,
            "ytick.labelsize": 8.6,
            "legend.fontsize": 8.2,
            "axes.edgecolor": "#475569",
            "axes.linewidth": 0.9,
            "grid.color": "#cbd5e1",
            "grid.alpha": 0.55,
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
        }
    )


def build_subaru_pupil(nwf: int = 256) -> np.ndarray:
    """Synthesize exact 4x4 anti-aliased Subaru Nasmyth-IR pupil (matches cacaosim_pupil.c)."""
    pup_diam = 0.9375
    cobs = 0.307
    spider_w = 0.02314
    spider_deg = 51.75
    spider_offset = 0.08289

    r_out = 0.5 * pup_diam * nwf
    r_out2 = r_out * r_out
    r_in2 = (cobs * r_out) ** 2
    ctr = 0.5 * (nwf - 1.0)
    half_w = 0.5 * spider_w * (2.0 * r_out)
    off_px = spider_offset * (2.0 * r_out)
    ang = math.radians(spider_deg)
    ca, sa = math.cos(ang), math.sin(ang)

    spiders = (
        (off_px, 0.0, ca, sa),
        (off_px, 0.0, ca, -sa),
        (-off_px, 0.0, -ca, sa),
        (-off_px, 0.0, -ca, -sa),
    )

    yy, xx = np.indices((nwf, nwf), dtype=np.float64)
    offs = (-0.375, -0.125, 0.125, 0.375)
    acc = np.zeros((nwf, nwf), dtype=np.float64)
    for dy in offs:
        ry = yy + dy - ctr
        for dx in offs:
            rx = xx + dx - ctr
            r2 = rx * rx + ry * ry
            inside = (r2 <= r_out2) & (r2 >= r_in2)
            for ox, oy, cx, sy in spiders:
                vx = rx - ox
                vy = ry - oy
                along = vx * cx + vy * sy
                perp = np.abs(vx * (-sy) + vy * cx)
                inside &= ~((along >= 0.0) & (perp <= half_w))
            acc += inside.astype(np.float64)
    return (acc / 16.0).astype(np.float32)


def segment_pupil_islands(pup_amp: np.ndarray) -> tuple[np.ndarray, int]:
    """Exact 4-connected BFS pupil island segmentation matching cacaosim_perturb.c."""
    nwf = pup_amp.shape[0]
    active = pup_amp > 0.5
    raw = np.full((nwf, nwf), -1, dtype=np.int32)
    comp_cnt: list[int] = []
    comp_sx: list[float] = []
    comp_sy: list[float] = []
    cid = 0
    for y in range(nwf):
        for x in range(nwf):
            if raw[y, x] >= 0 or not active[y, x]:
                continue
            q: deque[tuple[int, int]] = deque([(y, x)])
            raw[y, x] = cid
            cnt = 0
            sx = 0.0
            sy = 0.0
            while q:
                cy, cx = q.popleft()
                cnt += 1
                sx += cx
                sy += cy
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < nwf and 0 <= nx < nwf and raw[ny, nx] < 0 and active[ny, nx]:
                        raw[ny, nx] = cid
                        q.append((ny, nx))
            comp_cnt.append(cnt)
            comp_sx.append(sx)
            comp_sy.append(sy)
            cid += 1

    act_tot = int(np.sum(active))
    min_px = max(1, act_tot // 100)
    mid = 0.5 * (nwf - 1.0)
    kept: list[tuple[float, int]] = []
    for c in range(cid):
        if comp_cnt[c] >= min_px:
            mx = comp_sx[c] / comp_cnt[c] - mid
            my = comp_sy[c] / comp_cnt[c] - mid
            a = math.atan2(my, mx)
            if a < -math.pi / 4.0:
                a += 2.0 * math.pi
            kept.append((a, c))
    kept.sort(key=lambda item: item[0])

    labels = np.full((nwf, nwf), -1, dtype=np.int32)
    for new_p, (_, old_c) in enumerate(kept):
        labels[raw == old_c] = new_p
    return labels, len(kept)


def build_orthonormal_zernikes(pup_amp: np.ndarray, pup_diam: float = 0.9375) -> np.ndarray:
    """Build Gram-Schmidt pupil-orthonormalized Z2..Z6 maps (matches cacaosim_perturb.c)."""
    nwf = pup_amp.shape[0]
    active = pup_amp > 0.5
    mid = 0.5 * (nwf - 1.0)
    rad = 0.5 * pup_diam * nwf
    yy, xx = np.indices((nwf, nwf), dtype=np.float64)
    xn = (xx - mid) / rad
    yn = (yy - mid) / rad
    r2 = xn * xn + yn * yn
    raw = [
        xn,
        yn,
        2.0 * r2 - 1.0,
        2.0 * xn * yn,
        xn * xn - yn * yn,
    ]
    basis = np.zeros((5, nwf, nwf), dtype=np.float64)
    for m, arr in enumerate(raw):
        bm = np.where(active, arr, 0.0)
        bm[active] -= np.mean(bm[active])
        for p in range(m):
            dot = np.mean(bm[active] * basis[p][active])
            bm[active] -= dot * basis[p][active]
        rms = math.sqrt(float(np.mean(bm[active] ** 2)))
        if rms > 1e-12:
            bm /= rms
        basis[m] = bm
    return basis


def build_petal_basis(labels: np.ndarray, n_petals: int) -> tuple[np.ndarray, np.ndarray]:
    """Build [3 * n_petals, nwf, nwf] piston / local-tip / local-tilt petal basis maps."""
    nwf = labels.shape[0]
    yy, xx = np.indices((nwf, nwf), dtype=np.float64)
    basis = np.zeros((3 * n_petals, nwf, nwf), dtype=np.float64)
    fracs = np.zeros(n_petals, dtype=np.float64)
    tot = float(np.sum(labels >= 0))
    for p in range(n_petals):
        msk = labels == p
        cnt = int(np.sum(msk))
        fracs[p] = cnt / tot if tot > 0 else 1.0 / n_petals
        cx = float(np.mean(xx[msk]))
        cy = float(np.mean(yy[msk]))
        rx = math.sqrt(float(np.mean((xx[msk] - cx) ** 2)))
        ry = math.sqrt(float(np.mean((yy[msk] - cy) ** 2)))
        basis[3 * p + 0, msk] = 1.0
        basis[3 * p + 1, msk] = (xx[msk] - cx) / max(rx, 1.0)
        basis[3 * p + 2, msk] = (yy[msk] - cy) / max(ry, 1.0)
    return basis, fracs


def _kv_5_6_vec(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    out = np.zeros_like(x)
    pos = x > 1e-12
    xv = x[pos]
    u = np.linspace(0.0, 1.0, 65)
    tmax = np.arccosh(np.maximum(30.0 / xv, 1.0))
    tt = tmax[:, None] * u[None, :]
    integ = np.exp(-xv[:, None] * np.cosh(tt)) * np.cosh((5.0 / 6.0) * tt)
    dt = tmax / 64.0
    out[pos] = dt * (0.5 * (integ[:, 0] + integ[:, -1]) + np.sum(integ[:, 1:-1], axis=1))
    return out


def _sf_vonkarman(r_m: np.ndarray, r0_m: float, l0_m: float) -> np.ndarray:
    r_m = np.asarray(r_m, dtype=np.float64)
    if l0_m <= 0.0:
        return 6.883877 * (r_m / r0_m) ** (5.0 / 3.0)
    x = (2.0 * math.pi * r_m) / l0_m
    fac = (2.0 ** (1.0 / 6.0)) / math.gamma(5.0 / 6.0)
    xv = np.maximum(x, 1e-9)
    br = 1.0 - fac * (xv ** (5.0 / 6.0)) * _kv_5_6_vec(xv)
    return np.where(
        x < 1e-6,
        6.883877 * (r_m / r0_m) ** (5.0 / 3.0),
        0.172529795 * ((l0_m / r0_m) ** (5.0 / 3.0)) * br,
    )


def _matern32_coeffs(dt_s: float, tau_s: float) -> tuple[float, float, float, float, float, float, float]:
    lam = dt_s / tau_s
    em = math.exp(-lam)
    e2 = em * em
    p00 = em * (1.0 + lam)
    p01 = em * lam
    p10 = -em * lam
    p11 = em * (1.0 - lam)
    if lam < 1e-3:
        l2 = lam * lam
        l3 = l2 * lam
        q00 = (4.0 / 3.0) * l3 - 2.0 * l3 * lam + 1.6 * l3 * l2
        q01 = 2.0 * l2 * e2
        q11 = 4.0 * lam - 4.0 * l2 + (8.0 / 3.0) * l3
    else:
        q00 = 1.0 - e2 * (1.0 + 2.0 * lam + 2.0 * lam * lam)
        q01 = 2.0 * lam * lam * e2
        q11 = 1.0 - e2 * (1.0 - 2.0 * lam + 2.0 * lam * lam)
    l00 = math.sqrt(max(q00, 0.0))
    l10 = (q01 / l00) if l00 > 1e-15 else 0.0
    l11 = math.sqrt(max(q11 - l10 * l10, 0.0))
    return p00, p01, p10, p11, l00, l10, l11


def simulate_matern32(
    n_steps: int,
    dt_s: float,
    tau_s: float,
    sigma: float,
    rng: np.random.Generator,
    primed: bool = False,
) -> np.ndarray:
    """Exact 2-state Matern-3/2 discrete-time integration matching atmturb_dynwind/cacaosim."""
    p00, p01, p10, p11, l00, l10, l11 = _matern32_coeffs(dt_s, tau_s)
    g0 = rng.standard_normal(n_steps)
    g1 = rng.standard_normal(n_steps)
    out = np.empty(n_steps, dtype=np.float64)
    u = float(rng.standard_normal() * sigma) if primed else 0.0
    v = float(rng.standard_normal() * sigma) if primed else 0.0
    for i in range(n_steps):
        un = p00 * u + p01 * v + sigma * (l00 * g0[i])
        vn = p10 * u + p11 * v + sigma * (l10 * g0[i] + l11 * g1[i])
        u, v = un, vn
        out[i] = u
    return out


def make_fig1_profile_and_spectrum(out_dir: Path) -> None:
    """Figure 1: 7-layer Maunakea profile, wind hodograph, structure function & seeing scaling."""
    layers = get_normalized_layers()
    stats = compute_atmosphere_stats(DEFAULT_SEEING_ARCSEC)

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 8.6), constrained_layout=True)
    fig.suptitle(
        "Default Atmospheric Turbulence Model — 7-Layer Maunakea von Karman Profile\n"
        f'(Default Seeing = {DEFAULT_SEEING_ARCSEC:.2f}" @ 0.50 um | '
        f"r0 = {stats['r0_vk_500_cm']:.1f} cm | L0_eff = {stats['l0_eff_m']:.1f} m | "
        f"v_eff = {stats['v_eff_53_mps']:.1f} m/s | tau0 = {stats['bands'][0]['tau0_ms']:.2f} ms)",
        fontsize=12.5,
        fontweight="bold",
    )

    # Panel (0,0): Cn2 vertical distribution
    ax = axes[0, 0]
    y_pos = np.arange(len(layers))
    pcts = [float(l["cn2_pct"]) for l in layers]
    cols = ["#2563eb" if l["is_bl"] else "#d97706" for l in layers]
    bars = ax.barh(y_pos, pcts, color=cols, edgecolor="#1e293b", linewidth=0.7, height=0.68)
    y_lbls = [
        f"L{l['index']}: {float(l['alt_asl_m'])/1000:.2f} km ASL "
        f"({float(l['alt_agl_m'])/1000:.2f} AGL)"
        for l in layers
    ]
    ax.set_yticks(y_pos, y_lbls)
    ax.set_xlabel("Relative Cn2 Fraction [%]")
    ax.set_xlim(0, 68.0)
    ax.set_title("Vertical Cn2 Profile (71.4% BL L0=25 m | 28.6% FA L0=100 m)")
    ax.grid(True, axis="x")
    for bar, lay in zip(bars, layers):
        w = bar.get_width()
        ax.text(
            w + 0.8,
            bar.get_y() + bar.get_height() / 2.0,
            f"{w:.1f}%  (v={float(lay['speed_mps']):.1f} m/s, L0={int(lay['L0_m'])} m)",
            va="center",
            fontsize=8.1,
            color="#0f172a",
        )
    # Legend proxies placed in the wide open upper-right space above L0-L3
    leg_handles = [
        Patch(facecolor="#2563eb", edgecolor="#1e293b", label="BL (h_AGL <= 2 km, L0=25 m)"),
        Patch(facecolor="#d97706", edgecolor="#1e293b", label="FA (h_AGL > 2 km, L0=100 m)"),
    ]
    ax.legend(handles=leg_handles, loc="upper right", fontsize=8.0, framealpha=0.95)

    # Panel (0,1): Wind velocity vector hodograph (vx, vy)
    ax = axes[0, 1]
    for r_ring in (5, 10, 15, 20, 25):
        th = np.linspace(0.0, 2.0 * math.pi, 180)
        ax.plot(r_ring * np.cos(th), r_ring * np.sin(th), color="#e2e8f0", lw=0.8, zorder=1)
        ax.text(r_ring * 0.72, -r_ring * 0.72, f"{r_ring}", fontsize=7.5, color="#64748b")
    ax.axhline(0.0, color="#94a3b8", lw=0.8, ls=":")
    ax.axvline(0.0, color="#94a3b8", lw=0.8, ls=":")

    for lay in layers:
        spd = float(lay["speed_mps"])
        rad = float(lay["dir_rad"])
        vx = spd * math.cos(rad)
        vy = spd * math.sin(rad)
        col = "#2563eb" if lay["is_bl"] else "#d97706"
        sz = 45.0 + 9.0 * float(lay["cn2_pct"])
        ax.annotate(
            "",
            xy=(vx, vy),
            xytext=(0.0, 0.0),
            arrowprops={"arrowstyle": "->", "color": col, "lw": 1.6, "alpha": 0.75},
            zorder=2,
        )
        ax.scatter([vx], [vy], s=sz, color=col, edgecolors="#0f172a", linewidth=0.8, zorder=4)
    # Annotate cluster & jet cleanly without overlap
    ax.annotate(
        "BL Cluster (L0-L3)\n6.5-6.7 m/s @ 84-101 deg\n71.4% Cn2",
        xy=(0.0, 6.6),
        xytext=(5.5, 13.0),
        fontsize=8.2,
        bbox={"boxstyle": "round,pad=0.3", "fc": "#eff6ff", "ec": "#2563eb", "alpha": 0.95},
        arrowprops={"arrowstyle": "->", "color": "#2563eb", "lw": 1.0},
    )
    ax.annotate(
        "L4 Jet (12 km)\n22.0 m/s @ 178 deg (13.1%)",
        xy=(-22.0, 0.9),
        xytext=(-23.5, 11.5),
        fontsize=8.2,
        bbox={"boxstyle": "round,pad=0.3", "fc": "#fffbeb", "ec": "#d97706", "alpha": 0.95},
        arrowprops={"arrowstyle": "->", "color": "#d97706", "lw": 1.0},
    )
    ax.annotate(
        "L5 (16.2 km): 9.5 m/s\nL6 (23.7 km): 5.6 m/s",
        xy=(-9.5, -0.55),
        xytext=(-22.5, -16.5),
        fontsize=8.1,
        bbox={"boxstyle": "round,pad=0.3", "fc": "#fffbeb", "ec": "#d97706", "alpha": 0.92},
        arrowprops={"arrowstyle": "->", "color": "#d97706", "lw": 1.0},
    )
    ax.set_xlim(-26, 26)
    ax.set_ylim(-22, 22)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Wind Velocity Vx [m/s]")
    ax.set_ylabel("Wind Velocity Vy [m/s]")
    ax.set_title("Nominal Layer Wind Vectors (Marker Area ~ Cn2)")

    # Panel (1,0): Phase structure function D_phi(r) von Karman vs Kolmogorov
    ax = axes[1, 0]
    r_m = np.geomspace(0.02, 40.0, 300)
    r0_vk = solve_r0_for_seeing_m(DEFAULT_SEEING_ARCSEC, 0.50)
    r0_kolm = float(stats["r0_kolm_500_cm"]) / 100.0
    d_vk = np.zeros_like(r_m)
    for lay in layers:
        d_vk += float(lay["cn2_frac"]) * _sf_vonkarman(r_m, r0_vk, float(lay["L0_m"]))
    d_kolm = _sf_vonkarman(r_m, r0_kolm, 0.0)
    # Convert rad^2 @ 0.50 um to OPD RMS difference sqrt(D_OPD) in nm
    rad_to_nm = 500.0 / (2.0 * math.pi)
    ax.loglog(r_m, np.sqrt(d_kolm) * rad_to_nm, ls="--", color="#64748b", lw=1.6,
              label=f'Pure Kolmogorov (L0=inf, r0={r0_kolm*100:.1f} cm)')
    ax.loglog(r_m, np.sqrt(d_vk) * rad_to_nm, color="#1d4ed8", lw=2.2,
              label=f'Default 7-Layer von Karman (L0=25/100 m, r0={r0_vk*100:.1f} cm)')
    for xv, lbl, col in (
        (0.1325, "AO3k pitch\n0.13 m", "#059669"),
        (DEFAULT_TEL_DIAM_M, "Subaru D\n7.95 m", "#dc2626"),
        (35.0, "L0_eff\n35 m", "#7e22ce"),
    ):
        ax.axvline(xv, color=col, ls=":", lw=1.2, alpha=0.85)
        ax.text(xv * 1.07, 45.0, lbl, fontsize=7.8, color=col, fontweight="bold")
    ax.set_xlabel("Spatial Separation r [m]")
    ax.set_ylabel("RMS OPD Difference sqrt(D_OPD(r)) [nm]")
    ax.set_title(f'Phase Structure Function ({DEFAULT_SEEING_ARCSEC:.2f}" Seeing @ 0.50 um)')
    ax.set_ylim(30.0, 2.5e4)
    ax.grid(True, which="both", alpha=0.35)
    ax.legend(loc="upper left", framealpha=0.92)

    # Panel (1,1): Key atmospheric stats vs Seeing FWHM
    ax = axes[1, 1]
    see_arr = np.linspace(0.30, 1.50, 49)
    r0_500 = np.array([solve_r0_for_seeing_m(s, 0.50) * 100.0 for s in see_arr])
    r0_165 = np.array([solve_r0_for_seeing_m(s, 1.65) * 100.0 for s in see_arr])
    v_eff = float(stats["v_eff_53_mps"])
    tau0_500 = (0.314 * (r0_500 / 100.0) / v_eff) * 1000.0
    opd_vk = np.array(
        [compute_piston_removed_opd_nm(r / 100.0, DEFAULT_TEL_DIAM_M, layers) for r in r0_500]
    )

    l1 = ax.plot(see_arr, r0_500, color="#2563eb", lw=2.0, label="r0 @ 0.50 um [cm]")
    l2 = ax.plot(see_arr, r0_165, color="#0d9488", lw=1.8, ls="-.", label="r0 @ 1.65 um (H) [cm]")
    l3 = ax.plot(see_arr, tau0_500 * 5.0, color="#7e22ce", lw=1.6, ls="--",
                 label="5 x tau0 @ 0.50 um [ms]")
    ax.axvline(DEFAULT_SEEING_ARCSEC, color="#dc2626", ls=":", lw=1.4)
    ax.axvline(0.60, color="#059669", ls=":", lw=1.2)
    ax.text(
        DEFAULT_SEEING_ARCSEC + 0.02,
        118.0,
        f'Default\n{DEFAULT_SEEING_ARCSEC:.2f}"',
        color="#dc2626",
        fontsize=8.2,
        fontweight="bold",
    )
    ax.text(0.58, 118.0, '0.60"\ngood', color="#047857", ha="right", fontsize=8.0, fontweight="bold")
    ax.set_xlabel('Zenith Seeing FWHM at 0.50 um [arcsec]')
    ax.set_ylabel("r0 [cm]  |  5 x tau0 [ms]")
    ax.set_ylim(0, 145)
    ax.grid(True)

    ax2 = ax.twinx()
    l4 = ax2.plot(see_arr, opd_vk, color="#dc2626", lw=2.0, label="Pupil OPD RMS (von Karman) [nm]")
    ax2.set_ylabel("Entrance-Pupil OPD RMS [nm]", color="#dc2626")
    ax2.tick_params(axis="y", labelcolor="#dc2626")
    ax2.set_ylim(0, 2600)

    lines_all = l1 + l2 + l3 + l4
    ax.legend(lines_all, [ln.get_label() for ln in lines_all], loc="center right",
              fontsize=7.8, framealpha=0.92)
    ax.set_title("Turbulence Scaling vs. Seeing (D = 7.95 m, Nominal Wind)")

    fig.savefig(out_dir / "turb_profile_and_spectrum_2x2.png", dpi=170)
    plt.close(fig)


def make_fig2_wavefront_screens(out_dir: Path, pup: np.ndarray) -> None:
    """Figure 2: Simulated Subaru pupil OPD (Atm vs Atm+Perturb), spatial PSD & modal budget."""
    nwf = pup.shape[0]
    active = pup > 0.5
    layers = get_normalized_layers()
    r0_500 = solve_r0_for_seeing_m(DEFAULT_SEEING_ARCSEC, 0.50)
    dx_m = DEFAULT_TEL_DIAM_M / (nwf * 0.9375)

    # Synthesize multi-layer von Karman screen on a 1024x1024 grid (matching master_size=1024)
    # with exact PSD Phi(f) = 0.023 * r0^(-5/3) * (f^2 + 1/L0^2)^(-11/6)
    n_big = 1024
    rng = np.random.default_rng(20261124)
    fx = np.fft.fftfreq(n_big, d=dx_m)
    fy = np.fft.fftfreq(n_big, d=dx_m)
    fxx, fyy = np.meshgrid(fx, fy)
    f2 = fxx * fxx + fyy * fyy
    df = 1.0 / (n_big * dx_m)

    phi_big = np.zeros((n_big, n_big), dtype=np.float64)
    for lay in layers:
        l0_m = float(lay["L0_m"])
        f0_2 = 1.0 / (l0_m * l0_m)
        psd = 0.0229 * (r0_500 ** (-5.0 / 3.0)) * ((f2 + f0_2) ** (-11.0 / 6.0))
        psd[0, 0] = 0.0
        amp = np.sqrt(psd) * df * (n_big * n_big)
        # Unit-variance real & imag components so Re(ifft2) carries exact PSD variance
        cnoise = rng.standard_normal((n_big, n_big)) + 1j * rng.standard_normal((n_big, n_big))
        scr = np.fft.ifft2(cnoise * amp).real
        phi_big += math.sqrt(float(lay["cn2_frac"])) * scr

    # Crop central 256x256 pupil and convert rad @ 0.50 um -> nm OPD
    c0 = (n_big - nwf) // 2
    atm_nm = phi_big[c0 : c0 + nwf, c0 : c0 + nwf] * (500.0 / (2.0 * math.pi))
    atm_nm[active] -= np.mean(atm_nm[active])
    atm_nm = np.where(active, atm_nm, np.nan)
    atm_rms = float(np.sqrt(np.nanmean(atm_nm ** 2)))

    # Add representative instantaneous petaling (250 nm RMS) + vibrations (45 nm RMS)
    labels, n_petals = segment_pupil_islands(pup)
    p_basis, p_fracs = build_petal_basis(labels, n_petals)
    z_basis = build_orthonormal_zernikes(pup)
    # Representative stationary draw matching 250 nm LWE & 45 nm vib
    p_raw = np.array([-235.0, 265.0, -145.0, 115.0], dtype=np.float64)
    p_raw -= float(np.sum(p_fracs * p_raw))
    petal_map = np.zeros((nwf, nwf), dtype=np.float64)
    tx_vals = (68.0, -75.0, 52.0, -60.0)
    ty_vals = (-55.0, 62.0, -70.0, 48.0)
    for p in range(n_petals):
        petal_map += p_raw[p] * p_basis[3 * p + 0]
        petal_map += tx_vals[p] * p_basis[3 * p + 1]
        petal_map += ty_vals[p] * p_basis[3 * p + 2]
    p_rms_cur = float(np.sqrt(np.mean(petal_map[active] ** 2)))
    petal_map *= DEFAULT_PETAL_RMS_NM / max(p_rms_cur, 1e-6)

    vib_coeffs = np.array([32.5, -28.9, 8.3, 6.1, -5.4], dtype=np.float64)
    vib_map = np.tensordot(vib_coeffs, z_basis, axes=1)
    # Symmetric random sign orientation so sample realization illustrates expected quadrature addition
    pert_sum = petal_map + vib_map
    if float(np.mean(atm_nm[active] * pert_sum[active])) < 0.0:
        pert_sum = -pert_sum
    comb_nm = atm_nm + np.where(active, pert_sum, np.nan)
    comb_nm[active] -= float(np.nanmean(comb_nm))
    comb_rms = float(np.sqrt(np.nanmean(comb_nm ** 2)))

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 8.8), constrained_layout=True)
    fig.suptitle(
        "Entrance-Pupil Wavefront Realization & Spatial-Frequency Budget — Subaru 7.95 m\n"
        f'(Default {DEFAULT_SEEING_ARCSEC:.2f}" Maunakea von Karman + '
        f"{DEFAULT_PETAL_RMS_NM:.0f} nm Thermal Petaling + {DEFAULT_VIB_RMS_NM:.0f} nm Vibrations)",
        fontsize=12.5,
        fontweight="bold",
    )

    vmax = float(np.nanpercentile(np.abs(comb_nm), 99.2))
    cmap = plt.get_cmap("RdBu_r").copy()
    cmap.set_bad("#0f172a")
    ext = [-DEFAULT_TEL_DIAM_M / 2.0 / 0.9375, DEFAULT_TEL_DIAM_M / 2.0 / 0.9375] * 2

    # Panel (0,0): Atmosphere-only OPD
    ax = axes[0, 0]
    im0 = ax.imshow(atm_nm, origin="lower", cmap=cmap, vmin=-vmax, vmax=vmax, extent=ext)
    ax.set_xlabel("Pupil X [m]")
    ax.set_ylabel("Pupil Y [m]")
    ax.set_title(f'Atmosphere Only ({DEFAULT_SEEING_ARCSEC:.2f}", RMS = {atm_rms:.0f} nm)')
    cb0 = fig.colorbar(im0, ax=ax, fraction=0.046, pad=0.03)
    cb0.set_label("OPD [nm]")

    # Panel (0,1): Atmosphere + Petaling + Vibrations OPD
    ax = axes[0, 1]
    im1 = ax.imshow(comb_nm, origin="lower", cmap=cmap, vmin=-vmax, vmax=vmax, extent=ext)
    ax.set_xlabel("Pupil X [m]")
    ax.set_ylabel("Pupil Y [m]")
    ax.set_title(
        f"Atm + Petaling ({DEFAULT_PETAL_RMS_NM:.0f} nm) + Vib ({DEFAULT_VIB_RMS_NM:.0f} nm) "
        f"(RMS = {comb_rms:.0f} nm)"
    )
    cb1 = fig.colorbar(im1, ax=ax, fraction=0.046, pad=0.03)
    cb1.set_label("OPD [nm]")

    # Panel (1,0): Analytical spatial OPD PSD vs spatial frequency [cyc/pupil]
    ax = axes[1, 0]
    k_cyc = np.geomspace(0.08, 60.0, 300)  # cycles per pupil D
    f_m = k_cyc / DEFAULT_TEL_DIAM_M  # cycles / meter
    rad2_to_nm2 = (500.0 / (2.0 * math.pi)) ** 2
    psd_vk = np.zeros_like(f_m)
    for lay in layers:
        l0_m = float(lay["L0_m"])
        psd_vk += (
            float(lay["cn2_frac"])
            * 0.0229
            * (r0_500 ** (-5.0 / 3.0))
            * ((f_m ** 2 + (1.0 / l0_m) ** 2) ** (-11.0 / 6.0))
            * rad2_to_nm2
            / (DEFAULT_TEL_DIAM_M ** 2)
        )
    r0_kolm = 0.97586 * 0.50e-6 / (DEFAULT_SEEING_ARCSEC * math.pi / (180.0 * 3600.0))
    psd_kolm = (
        0.0229
        * (r0_kolm ** (-5.0 / 3.0))
        * (f_m ** (-11.0 / 3.0))
        * rad2_to_nm2
        / (DEFAULT_TEL_DIAM_M ** 2)
    )
    ax.loglog(k_cyc, psd_kolm, ls="--", color="#64748b", lw=1.5, label="Kolmogorov (f^-11/3)")
    ax.loglog(k_cyc, psd_vk, color="#1d4ed8", lw=2.2, label="Default 7-Layer von Karman")
    ax.axvline(23.0, color="#059669", ls=":", lw=1.4, label="SCExAO DM2 cutoff (23 cyc/D)")
    ax.axvline(30.0, color="#7e22ce", ls=":", lw=1.4, label="AO3k DM1 cutoff (30 cyc/D)")
    ax.axvspan(0.08, 3.0, color="#fef3c7", alpha=0.45, label="LWE / Vibration low-order band")
    ax.set_xlabel("Spatial Frequency [cycles / pupil D]")
    ax.set_ylabel("2D OPD PSD [nm^2 / (cyc/D)^2]")
    ax.set_title("Spatial Power Spectral Density & AO Control Radii")
    ax.grid(True, which="both", alpha=0.35)
    ax.legend(loc="lower left", fontsize=7.9, framealpha=0.92)

    # Panel (1,1): Component OPD RMS budget comparison bar chart
    ax = axes[1, 1]
    atm_vk_rms = compute_piston_removed_opd_nm(r0_500, DEFAULT_TEL_DIAM_M, layers)
    atm_kolm_rms = compute_piston_removed_opd_nm(r0_kolm, DEFAULT_TEL_DIAM_M, layers, kolmogorov=True)
    tt_rem_rms = float(compute_atmosphere_stats(DEFAULT_SEEING_ARCSEC)["opd_tt_removed_nm"])
    tot_quad = math.sqrt(atm_vk_rms ** 2 + DEFAULT_PETAL_RMS_NM ** 2 + DEFAULT_VIB_RMS_NM ** 2)
    cat_names = [
        "Atm (Kolm.\nL0=inf ref)",
        f'Atm (Default\nvK {DEFAULT_SEEING_ARCSEC:.2f}")',
        "Atm High-Ord\n(TT-rem)",
        "Thermal\nPetaling",
        "Telescope\nVibrations",
        "Total Comb.\n(Default)",
    ]
    cat_vals = [
        atm_kolm_rms,
        atm_vk_rms,
        tt_rem_rms,
        DEFAULT_PETAL_RMS_NM,
        DEFAULT_VIB_RMS_NM,
        tot_quad,
    ]
    cat_cols = ["#94a3b8", "#2563eb", "#0ea5e9", "#9333ea", "#dc2626", "#0f172a"]
    xb = np.arange(len(cat_names))
    bars = ax.bar(xb, cat_vals, color=cat_cols, edgecolor="#1e293b", linewidth=0.7, width=0.62)
    ax.set_xticks(xb, cat_names, fontsize=8.0)
    ax.set_ylabel("Entrance-Pupil OPD RMS [nm]")
    ax.set_ylim(0, max(cat_vals) * 1.18)
    ax.set_title("Entrance-Pupil OPD RMS Budget by Perturbation Source")
    ax.grid(True, axis="y")
    for b, v in zip(bars, cat_vals):
        ax.text(
            b.get_x() + b.get_width() / 2.0,
            v + 35.0,
            f"{v:.0f} nm",
            ha="center",
            va="bottom",
            fontsize=8.3,
            fontweight="bold",
        )

    fig.savefig(out_dir / "turb_wavefront_phase_screens_2x2.png", dpi=170)
    plt.close(fig)


def _simulate_dynwind_exact(
    duration_s: float,
    dt_s: float = 0.01,
    seed: int = 7771,
) -> dict[str, np.ndarray]:
    """Simulate exact non-stationary wind meandering & gust bursts matching atmturb_dynwind.c."""
    layers = get_normalized_layers()
    nl = len(layers)
    cn2 = np.array([float(l["cn2_frac"]) for l in layers])
    is_bl = np.array([bool(l["is_bl"]) for l in layers])
    v0 = np.array([float(l["speed_mps"]) for l in layers])
    n_steps = int(round(duration_s / dt_s))
    t_arr = np.arange(n_steps, dtype=np.float64) * dt_s
    rng = np.random.default_rng(seed)

    bl_spd = simulate_matern32(n_steps, dt_s, 3.5, 0.22, rng, primed=True)
    bl_dir = simulate_matern32(n_steps, dt_s, 4.0, math.radians(22.0), rng, primed=True)
    fa_spd = simulate_matern32(n_steps, dt_s, 6.0, 0.14, rng, primed=True)
    fa_dir = simulate_matern32(n_steps, dt_s, 6.5, math.radians(10.0), rng, primed=True)

    lay_spd = np.zeros((nl, n_steps))
    lay_dir = np.zeros((nl, n_steps))
    for k in range(nl):
        tau_s = 3.0 if is_bl[k] else 5.0
        sig_s = 0.12 if is_bl[k] else 0.08
        sig_d = math.radians(10.0 if is_bl[k] else 5.0)
        lay_spd[k] = simulate_matern32(n_steps, dt_s, tau_s, sig_s, rng, primed=True)
        lay_dir[k] = simulate_matern32(n_steps, dt_s, tau_s, sig_d, rng, primed=True)

    # Burst event schedule (exact formulas from atmturb_dynwind_schedule_burst)
    burst_env = np.zeros(n_steps)
    burst_spd_t = np.zeros(n_steps)
    burst_dir_t = np.zeros(n_steps)
    burst_cn2_t = np.zeros(n_steps)

    t_cur = 0.0
    first = True
    while t_cur < duration_s:
        gap = (1.8 + 1.2 * rng.random()) if first else (2.2 + 2.2 * rng.random())
        first = False
        t_start = t_cur + gap
        rise = 0.25 + 0.25 * rng.random()
        decay = 0.95 + 0.85 * rng.random()
        spd_amp = 0.80 + 0.55 * rng.random()
        d_rad = (-1.0 if rng.random() < 0.5 else 1.0) * math.radians(18.0 + 18.0 * rng.random())
        cn2_amp = 0.22 + 0.14 * rng.random()
        t_end = t_start + rise + decay
        m_r = (t_arr > t_start) & (t_arr < t_start + rise)
        if np.any(m_r):
            u = (t_arr[m_r] - t_start) / rise
            env = 0.5 * (1.0 - np.cos(math.pi * u))
            burst_env[m_r] = env
            burst_spd_t[m_r] = spd_amp * env
            burst_dir_t[m_r] = d_rad * env
            burst_cn2_t[m_r] = cn2_amp * env
        m_d = (t_arr >= t_start + rise) & (t_arr < t_end)
        if np.any(m_d):
            u = (t_arr[m_d] - (t_start + rise)) / decay
            c = np.cos(0.5 * math.pi * u)
            env = np.exp(-1.2 * u) * c * c
            burst_env[m_d] = env
            burst_spd_t[m_d] = spd_amp * env
            burst_dir_t[m_d] = d_rad * env
            burst_cn2_t[m_d] = cn2_amp * env
        t_cur = t_end

    spd_meand_k = np.zeros((nl, n_steps))
    spd_full_k = np.zeros((nl, n_steps))
    deg_full_k = np.zeros((nl, n_steps))
    amp_full_k = np.zeros((nl, n_steps))
    for k in range(nl):
        b_s = bl_spd if is_bl[k] else fa_spd
        b_d = bl_dir if is_bl[k] else fa_dir
        u_s = 0.78 * b_s + 0.62 * lay_spd[k]
        d_r = 0.78 * b_d + 0.62 * lay_dir[k]
        b_wt = 1.0 if is_bl[k] else 0.35
        spd_meand_k[k] = np.clip(np.exp(u_s), 0.35, 3.20)
        spd_full_k[k] = np.clip(np.exp(u_s) + b_wt * burst_spd_t, 0.35, 3.20)
        deg_full_k[k] = np.degrees(d_r + b_wt * burst_dir_t)
        amp_full_k[k] = 1.0 + (1.0 if is_bl[k] else 0.20) * burst_cn2_t

    w_scl_meand = cn2 @ spd_meand_k
    w_scl_full = cn2 @ spd_full_k
    w_deg_full = cn2 @ deg_full_k
    w_cn2_full = np.sqrt(cn2 @ (amp_full_k ** 2))

    # Effective wind v_{5/3}(t) [m/s]
    v_k_t = v0[:, None] * spd_full_k
    v_eff_t = (cn2 @ (v_k_t ** (5.0 / 3.0))) ** 0.6
    r0_500 = solve_r0_for_seeing_m(DEFAULT_SEEING_ARCSEC, 0.50)
    tau0_ms_t = (0.314 * (r0_500 / (w_cn2_full ** 1.2)) / v_eff_t) * 1000.0

    return {
        "t": t_arr,
        "w_scl_meand": w_scl_meand,
        "w_scl_full": w_scl_full,
        "w_deg_full": w_deg_full,
        "w_cn2_full": w_cn2_full,
        "burst_env": burst_env,
        "bl_scl": spd_full_k[0],
        "jet_scl": spd_full_k[4],
        "bl_deg": deg_full_k[0],
        "jet_deg": deg_full_k[4],
        "v_eff_t": v_eff_t,
        "tau0_ms_t": tau0_ms_t,
    }


def make_fig3_wind_dynamics(out_dir: Path) -> None:
    """Figure 3: Non-stationary wind meandering, gusts, stationary PDFs & temporal PSD."""
    sim30 = _simulate_dynwind_exact(30.0, dt_s=0.01, seed=7771)
    sim600 = _simulate_dynwind_exact(600.0, dt_s=0.02, seed=8881)

    t = sim30["t"]
    fig, axes = plt.subplots(2, 2, figsize=(13.6, 8.6), constrained_layout=True)
    fig.suptitle(
        "Default Wind Perturbation Model — Matern-3/2 Meandering & Asymmetric Gust Bursts\n"
        "(Phase-Continuous Per-Layer Advection | Boundary Layer <= 2 km vs. Free Atmosphere)",
        fontsize=12.5,
        fontweight="bold",
    )

    # Panel (0,0): 30 s wind speed scale + Cn2 surges + burst envelopes
    ax = axes[0, 0]
    ax.plot(t, sim30["w_scl_full"], color="#1d4ed8", lw=1.8, label="Cn2-weighted wind scale")
    ax.plot(t, sim30["jet_scl"], color="#7e22ce", lw=1.1, alpha=0.8, label="12 km Jet layer scale")
    ax.plot(t, sim30["w_cn2_full"], color="#dc2626", lw=1.4, ls="--", label="Cn2 RMS scale [x nom]")
    ax.axhline(1.0, color="#64748b", lw=0.9, ls=":")
    ax.fill_between(
        t,
        0.4,
        1.0 + sim30["burst_env"],
        where=sim30["burst_env"] > 0.02,
        color="#f59e0b",
        alpha=0.18,
        label="Gust burst window",
    )
    ax.set_xlim(0.0, 30.0)
    ax.set_ylim(0.55, max(2.25, float(np.max(sim30["w_scl_full"])) * 1.08))
    ax.set_xlabel("Physical Time t [s]")
    ax.set_ylabel("Multiplier [x nominal]")
    ax.set_title("Wind Speed Meandering & Gust Bursts (30 s Sample)")
    ax.grid(True)
    ax.legend(loc="upper right", ncol=2, fontsize=7.8, framealpha=0.92)

    # Panel (0,1): 30 s heading offset
    ax = axes[0, 1]
    ax.plot(t, sim30["w_deg_full"], color="#0d9488", lw=1.8, label="Cn2-weighted heading")
    ax.plot(t, sim30["bl_deg"], color="#2563eb", lw=1.0, alpha=0.72, label="Surface BL (L0)")
    ax.plot(t, sim30["jet_deg"], color="#d97706", lw=1.1, alpha=0.85, label="12 km Jet (L4)")
    ax.axhline(0.0, color="#64748b", lw=0.9, ls=":")
    ymin_d = float(np.min(sim30["bl_deg"])) - 4.0
    ymax_d = float(np.max(sim30["bl_deg"])) + 12.0
    ax.fill_between(
        t,
        ymin_d,
        ymax_d,
        where=sim30["burst_env"] > 0.05,
        color="#f59e0b",
        alpha=0.13,
        label="Gust window",
    )
    ax.set_xlim(0.0, 30.0)
    ax.set_ylim(ymin_d, ymax_d)
    ax.set_xlabel("Physical Time t [s]")
    ax.set_ylabel("Heading Offset [deg]")
    ax.set_title("Wind Direction Meandering & Gust Swings (30 s Sample)")
    ax.grid(True)
    ax.legend(loc="upper right", ncol=2, fontsize=7.8, framealpha=0.92)

    # Panel (1,0): 600 s stationary wind scale & tau0 PDF
    ax = axes[1, 0]
    bins = np.linspace(0.5, 2.5, 50)
    ax.hist(
        sim600["w_scl_meand"],
        bins=bins,
        density=True,
        alpha=0.45,
        color="#64748b",
        label=f"Meandering only (med={np.median(sim600['w_scl_meand']):.2f}x)",
    )
    ax.hist(
        sim600["w_scl_full"],
        bins=bins,
        density=True,
        alpha=0.60,
        color="#2563eb",
        label=f"Default: Meand + Bursts (med={np.median(sim600['w_scl_full']):.2f}x)",
    )
    p05, p50, p95 = np.percentile(sim600["w_scl_full"], [5, 50, 95])
    for pv, pl, pc, ha, dx, yf in (
        (p05, f"P05={p05:.2f}x", "#0f766e", "right", -0.025, 0.87),
        (p50, f"P50={p50:.2f}x", "#1e3a8a", "left", 0.025, 0.87),
        (p95, f"P95={p95:.2f}x", "#dc2626", "right", -0.025, 0.72),
    ):
        ax.axvline(pv, color=pc, ls="--", lw=1.3)
        ax.text(
            pv + dx,
            ax.get_ylim()[1] * yf,
            pl,
            color=pc,
            ha=ha,
            fontsize=7.8,
            fontweight="bold",
        )
    tau_p05, tau_p50, tau_p95 = np.percentile(sim600["tau0_ms_t"], [5, 50, 95])
    ax.text(
        0.97,
        0.58,
        f"600 s Stationary Stats:\n"
        f"v_eff P05-P95: {np.percentile(sim600['v_eff_t'], 5):.1f}-"
        f"{np.percentile(sim600['v_eff_t'], 95):.1f} m/s\n"
        f"tau0(0.5um): {tau_p50:.2f} ms (P05={tau_p05:.2f}, P95={tau_p95:.2f})\n"
        f"Burst active: {100*np.mean(sim600['burst_env']>0.05):.1f}% of time",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.0,
        bbox={"boxstyle": "round,pad=0.35", "fc": "#f8fafc", "ec": "#cbd5e1", "alpha": 0.95},
    )
    ax.set_xlabel("Cn2-Weighted Wind Speed Multiplier [x nominal]")
    ax.set_ylabel("Probability Density")
    ax.set_title("Long-Run Stationary Wind-Speed Distribution (600 s)")
    ax.grid(True)
    ax.legend(loc="upper right", fontsize=7.9, framealpha=0.92)

    # Panel (1,1): Matern-3/2 analytical PSD + asymmetric gust envelope inset
    ax = axes[1, 1]
    freqs = np.geomspace(5e-3, 3.0, 250)
    # One-sided Matern-3/2 PSD: S(f) = 4 * sigma^2 * (2 / tau) / (1/tau^2 + (2*pi*f)^2)^2 ...
    # Actually autocorrelation R(dt) = sigma^2*(1 + |dt|/tau)*exp(-|dt|/tau),
    # whose one-sided PSD is S_1(f) = 8 * sigma^2 * tau / (1 + (2*pi*f*tau)^2)^2
    for tau_s, sig, lbl, col, ls in (
        (3.5, 0.22, "BL Speed (tau=3.5 s, sig=0.22)", "#2563eb", "-"),
        (6.0, 0.14, "FA Speed (tau=6.0 s, sig=0.14)", "#d97706", "--"),
        (4.0, 22.0 / 57.2958, "BL Heading (tau=4.0 s, sig=22 deg [rad])", "#0d9488", "-."),
    ):
        psd = 8.0 * (sig ** 2) * tau_s / ((1.0 + (2.0 * math.pi * freqs * tau_s) ** 2) ** 2)
        ax.loglog(freqs, psd, color=col, ls=ls, lw=2.0, label=lbl)
    ax.set_xlabel("Temporal Frequency f [Hz]")
    ax.set_ylabel("One-Sided PSD [unit^2 / Hz]")
    ax.set_ylim(1e-8, 9e1)
    ax.set_title("Matern-3/2 Wind Drift PSD (-40 dB/dec) & Gust Envelope")
    ax.grid(True, which="both", alpha=0.35)
    ax.legend(loc="lower left", fontsize=7.8, framealpha=0.92)

    # Inset showing single canonical asymmetric gust envelope
    ins = ax.inset_axes([0.56, 0.56, 0.41, 0.37])
    ins.set_facecolor("#ffffff")
    ins.set_zorder(5)
    ts = np.linspace(0.0, 1.9, 200)
    rise_c, dec_c = 0.375, 1.375
    env_c = np.where(
        ts < rise_c,
        0.5 * (1.0 - np.cos(math.pi * ts / rise_c)),
        np.where(
            ts < rise_c + dec_c,
            np.exp(-1.2 * (ts - rise_c) / dec_c)
            * (np.cos(0.5 * math.pi * (ts - rise_c) / dec_c) ** 2),
            0.0,
        ),
    )
    ins.fill_between(ts, 0.0, env_c, color="#f59e0b", alpha=0.30)
    ins.plot(ts, env_c, color="#b45309", lw=1.6)
    ins.set_title("Canonical C1 Gust Envelope", fontsize=7.8, fontweight="bold", pad=2)
    ins.set_xlabel("t - t_start [s]", fontsize=7.2)
    ins.set_ylabel("Env [0..1]", fontsize=7.2)
    ins.tick_params(labelsize=7.0)
    ins.grid(True, alpha=0.4)

    fig.savefig(out_dir / "turb_wind_dynamics_2x2.png", dpi=170)
    plt.close(fig)


def make_fig4_vibrations(out_dir: Path, pup: np.ndarray) -> None:
    """Figure 4: 5-line AR(2) vibration PSD, cumulative RMS, 0.5 s beating & Z2-Z6 pupil basis."""
    vib_rms_nm = 45.0
    dt_s = 0.0005  # 2 kHz outer tick
    fs_hz = 1.0 / dt_s
    n_steps = 40000  # 20 s for clean Welch PSD
    rng = np.random.default_rng(101)

    z_ts = np.zeros((5, n_steps), dtype=np.float64)
    for m in DEFAULT_VIB_MODES:
        f0 = float(m["f0_hz"])
        zeta = float(m["zeta"])
        share = float(m["share"])
        z_wt = tuple(float(w) for w in m["z_wt"])  # type: ignore[union-attr]
        w0 = 2.0 * math.pi * f0
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        r = math.exp(-zeta * w0 * dt_s)
        a1 = 2.0 * r * math.cos(wd * dt_s)
        a2 = -(r * r)
        num = (1.0 + a2) * ((1.0 - a2) ** 2 - a1 * a1)
        den = 1.0 - a2
        b = math.sqrt(max(num / den, 0.0))
        rho1 = max(-0.999999, min(0.999999, a1 / den))
        g = rng.standard_normal(n_steps + 2)
        x = np.empty(n_steps, dtype=np.float64)
        x2 = g[0]
        x1 = rho1 * g[0] + math.sqrt(1.0 - rho1 * rho1) * g[1]
        for i in range(n_steps):
            xn = a1 * x1 + a2 * x2 + b * g[i + 2]
            x2, x1 = x1, xn
            x[i] = xn
        amp = vib_rms_nm * math.sqrt(share) * x
        for zm in range(5):
            if z_wt[zm] != 0.0:
                z_ts[zm] += amp * z_wt[zm]

    # Exact analytical one-sided AR(2) PSD for each mode
    freqs = np.linspace(4.0, 200.0, 2000)
    psd_z = np.zeros((5, freqs.size), dtype=np.float64)
    z_exp = np.exp(-1j * 2.0 * math.pi * freqs * dt_s)
    for m in DEFAULT_VIB_MODES:
        f0 = float(m["f0_hz"])
        zeta = float(m["zeta"])
        share = float(m["share"])
        z_wt = tuple(float(w) for w in m["z_wt"])  # type: ignore[union-attr]
        w0 = 2.0 * math.pi * f0
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        r = math.exp(-zeta * w0 * dt_s)
        a1 = 2.0 * r * math.cos(wd * dt_s)
        a2 = -(r * r)
        b2 = ((1.0 + a2) * ((1.0 - a2) ** 2 - a1 * a1)) / (1.0 - a2)
        h_mag2 = b2 / (np.abs(1.0 - a1 * z_exp - a2 * (z_exp ** 2)) ** 2)
        # One-sided discrete PSD [unit^2 / Hz] = (2 / fs) * |H(f)|^2
        s_line = (2.0 / fs_hz) * h_mag2 * (vib_rms_nm ** 2) * share
        for zm in range(5):
            if z_wt[zm] != 0.0:
                psd_z[zm] += s_line * (z_wt[zm] ** 2)

    psd_tot = np.sum(psd_z, axis=0)
    df = freqs[1] - freqs[0]
    rev_cum_nm = np.sqrt(np.cumsum(psd_tot[::-1])[::-1] * df)

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 8.6), constrained_layout=True)
    fig.suptitle(
        "Default Telescope & Optical Bench Vibration Model (cacaosim_perturb.c)\n"
        "(5 Exact Stationary AR(2) Resonators | 14.5-138 Hz | Default Total RMS = 45.0 nm)",
        fontsize=12.5,
        fontweight="bold",
    )

    # Panel (0,0): Analytical PSD per Zernike mode
    ax = axes[0, 0]
    vstats = compute_vibration_stats(vib_rms_nm)
    z_cols = ("#2563eb", "#dc2626", "#059669", "#9333ea", "#d97706")
    z_lbls = [
        f"{z['mode']} ({z['rms_nm']:.1f} nm)" for z in vstats["zernikes"]  # type: ignore[index]
    ]
    for zm in range(5):
        ax.semilogy(freqs, np.maximum(psd_z[zm], 1e-6), color=z_cols[zm], lw=1.45, label=z_lbls[zm])
    for m in DEFAULT_VIB_MODES:
        f0 = float(m["f0_hz"])
        q_f = 1.0 / (2.0 * float(m["zeta"]))
        ax.axvline(f0, color="#64748b", ls=":", lw=0.85, alpha=0.75)
        ax.text(
            f0 + 1.4,
            1.4e3,
            f"{f0:.1f} Hz\n(Q~{q_f:.0f})",
            fontsize=7.3,
            color="#334155",
            va="top",
        )
    ax.set_xlim(4.0, 200.0)
    ax.set_ylim(1e-5, 3e3)
    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("One-Sided OPD PSD [nm^2 / Hz]")
    ax.set_title("Exact Stationary AR(2) Vibration PSD Across Z2-Z6")
    ax.grid(True, which="both", alpha=0.32)
    ax.legend(loc="lower left", fontsize=7.8, framealpha=0.92)

    # Panel (0,1): Reverse-cumulative RMS spectrum
    ax = axes[0, 1]
    ax.plot(freqs, rev_cum_nm, color="#0f172a", lw=2.2, label="Total reverse-cum. RMS (>= f)")
    for zm, lbl, col in ((0, "Tip Z2", "#2563eb"), (1, "Tilt Z3", "#dc2626"),
                         (2, "Focus Z4", "#059669")):
        rc_z = np.sqrt(np.cumsum(psd_z[zm][::-1])[::-1] * df)
        ax.plot(freqs, rc_z, color=col, lw=1.4, ls="--", label=f"{lbl} (>= f)")
    for m in DEFAULT_VIB_MODES:
        f0 = float(m["f0_hz"])
        sh = int(round(float(m["share"]) * 100.0))
        ax.axvline(f0, color="#94a3b8", ls=":", lw=0.9)
        y_lbl = 16.5 if f0 > 120.0 else 46.5
        ax.text(f0 + 1.5, y_lbl, f"{sh}%", fontsize=7.8, color="#475569", fontweight="bold")
    ax.set_xlim(4.0, 200.0)
    ax.set_ylim(0.0, 51.0)
    ax.set_xlabel("Lower Frequency Bound f [Hz]")
    ax.set_ylabel("Reverse-Cumulative OPD RMS [nm]")
    ax.set_title("Reverse-Cumulative Vibration Budget (Step Drops = Line Variance)")
    ax.grid(True)
    ax.legend(loc="upper right", fontsize=8.0, framealpha=0.92)

    # Panel (1,0): 0.5 s stochastic beating time series
    ax = axes[1, 0]
    n_zoom = 1000  # 0.50 s
    t_z = np.arange(n_zoom) * dt_s * 1000.0  # ms
    tot_inst = np.sqrt(np.sum(z_ts[:, :n_zoom] ** 2, axis=0))
    ax.plot(t_z, z_ts[0, :n_zoom], color="#2563eb", lw=1.15, alpha=0.9, label="Tip Z2 [nm]")
    ax.plot(t_z, z_ts[1, :n_zoom], color="#dc2626", lw=1.10, alpha=0.82, label="Tilt Z3 [nm]")
    ax.plot(t_z, z_ts[2, :n_zoom], color="#059669", lw=1.0, alpha=0.85, label="Focus Z4 [nm]")
    ax.plot(t_z, tot_inst, color="#0f172a", lw=1.25, ls="--", alpha=0.75, label="Inst. Total RMS")
    ax.axhline(0.0, color="#94a3b8", lw=0.8, ls=":")
    ax.set_xlim(0.0, 500.0)
    ax.set_xlabel("Physical Time t [ms]")
    ax.set_ylabel("Modal OPD Amplitude [nm]")
    ax.set_title("0.5 s Stochastic Beating Realization (2 kHz Sampling)")
    ax.grid(True)
    ax.legend(loc="upper right", ncol=2, fontsize=7.8, framealpha=0.92)

    # Panel (1,1): Line variance budget bar chart + mini spatial Z2-Z6 pupil tiles
    ax = axes[1, 1]
    l_names = [f"{float(m['f0_hz']):.1f} Hz\n(Q~{1/(2*float(m['zeta'])):.0f})" for m in DEFAULT_VIB_MODES]
    l_rms = [vib_rms_nm * math.sqrt(float(m["share"])) for m in DEFAULT_VIB_MODES]
    l_cols = ["#0284c7", "#2563eb", "#7e22ce", "#d97706", "#dc2626"]
    xb = np.arange(len(l_names))
    bars = ax.bar(xb, l_rms, color=l_cols, edgecolor="#1e293b", linewidth=0.7, width=0.58)
    ax.set_xticks(xb, l_names)
    ax.set_ylabel("Per-Line Stationary RMS [nm]")
    ax.set_ylim(0, 50.0)
    ax.set_title("Resonant Line RMS Budget & Orthonormalized Z2-Z6 Modes")
    ax.grid(True, axis="y")
    for b, v, m in zip(bars, l_rms, DEFAULT_VIB_MODES):
        ax.text(
            b.get_x() + b.get_width() / 2.0,
            v + 0.8,
            f"{v:.1f} nm\n({int(round(float(m['share'])*100))}%)",
            ha="center",
            va="bottom",
            fontsize=7.8,
            fontweight="bold",
        )
    # Inset strip showing the 5 Gram-Schmidt pupil-orthonormalized Zernikes Z2..Z6
    z_basis = build_orthonormal_zernikes(pup)
    active = pup > 0.5
    z_short = ("Z2", "Z3", "Z4", "Z5", "Z6")
    cmap_z = plt.get_cmap("RdBu_r").copy()
    cmap_z.set_bad("#0f172a")
    for zi in range(5):
        ins = ax.inset_axes([0.04 + zi * 0.188, 0.74, 0.165, 0.22])
        zmap = np.where(active, z_basis[zi], np.nan)
        ins.imshow(zmap, origin="lower", cmap=cmap_z, vmin=-2.2, vmax=2.2)
        ins.set_xticks([])
        ins.set_yticks([])
        ins.set_title(z_short[zi], fontsize=7.5, fontweight="bold", pad=1.5)

    fig.savefig(out_dir / "turb_vibrations_2x2.png", dpi=170)
    plt.close(fig)


def make_fig5_petaling_lwe(out_dir: Path, pup: np.ndarray) -> None:
    """Figure 5: Subaru 4-island segmentation, LWE OPD + H-band split PSF, 30 s traces & PSD."""
    nwf = pup.shape[0]
    active = pup > 0.5
    labels, n_petals = segment_pupil_islands(pup)
    p_basis, p_fracs = build_petal_basis(labels, n_petals)
    petal_rms = DEFAULT_PETAL_RMS_NM
    petal_tau = DEFAULT_PETAL_TAU_S
    pstats = compute_petaling_stats(petal_rms, petal_tau, n_petals)

    # Simulate 30 s of exact Matern-3/2 petaling
    dt_s = 0.01
    n_steps = 3000
    t_arr = np.arange(n_steps) * dt_s
    rng = np.random.default_rng(202)
    sig_pis = petal_rms * math.sqrt(0.75 * n_petals / (n_petals - 1))
    sig_tt = petal_rms * math.sqrt(0.125)

    pis_raw = np.zeros((n_petals, n_steps))
    tx_ts = np.zeros((n_petals, n_steps))
    ty_ts = np.zeros((n_petals, n_steps))
    for p in range(n_petals):
        pis_raw[p] = simulate_matern32(n_steps, dt_s, petal_tau, sig_pis, rng, primed=True)
        tx_ts[p] = simulate_matern32(n_steps, dt_s, petal_tau, sig_tt, rng, primed=True)
        ty_ts[p] = simulate_matern32(n_steps, dt_s, petal_tau, sig_tt, rng, primed=True)

    mean_p = p_fracs @ pis_raw
    dp = pis_raw - mean_p[None, :]
    ptv_t = np.max(dp, axis=0) - np.min(dp, axis=0)
    rms_t = np.sqrt(p_fracs @ (dp ** 2 + tx_ts ** 2 + ty_ts ** 2))

    # Pick a representative strong-LWE snapshot instant for Panel (0,1)
    idx_snap = int(np.argmax(ptv_t[:1500]))
    lwe_map = np.zeros((nwf, nwf), dtype=np.float64)
    for p in range(n_petals):
        lwe_map += dp[p, idx_snap] * p_basis[3 * p + 0]
        lwe_map += tx_ts[p, idx_snap] * p_basis[3 * p + 1]
        lwe_map += ty_ts[p, idx_snap] * p_basis[3 * p + 2]
    snap_rms = float(rms_t[idx_snap])
    snap_ptv = float(ptv_t[idx_snap])

    # Compute corresponding H-band (1.65 um) PSF via 4x padded FFT to visualize split core
    npad = nwf * 4
    ef_dl = np.zeros((npad, npad), dtype=np.complex128)
    ef_lwe = np.zeros((npad, npad), dtype=np.complex128)
    ef_dl[:nwf, :nwf] = pup
    ef_lwe[:nwf, :nwf] = pup * np.exp(1j * (2.0 * math.pi * lwe_map / 1650.0))
    psf_dl = np.abs(np.fft.fftshift(np.fft.fft2(ef_dl))) ** 2
    psf_lwe = np.abs(np.fft.fftshift(np.fft.fft2(ef_lwe))) ** 2
    pk_dl = float(np.max(psf_dl))
    psf_lwe_norm = psf_lwe / max(pk_dl, 1e-12)
    sr_lwe = float(np.max(psf_lwe_norm)) * 100.0
    c_mid = npad // 2
    hw = 28
    psf_crop = psf_lwe_norm[c_mid - hw : c_mid + hw, c_mid - hw : c_mid + hw]

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 8.8), constrained_layout=True)
    fig.suptitle(
        "Default Thermally Induced Petaling / Low-Wind Effect (LWE) Model (cacaosim_perturb.c)\n"
        f"(4 Subaru V-Spider Islands | Default RMS = {petal_rms:.0f} nm "
        "[75% Piston, 25% Local Tip/Tilt] | "
        f"Matern-3/2 tau = {petal_tau:.1f} s, f_c = {pstats['corner_hz']:.3f} Hz)",
        fontsize=12.5,
        fontweight="bold",
    )

    ext = [-DEFAULT_TEL_DIAM_M / 2.0 / 0.9375, DEFAULT_TEL_DIAM_M / 2.0 / 0.9375] * 2

    # Panel (0,0): Automatic 4-connected BFS pupil island segmentation
    ax = axes[0, 0]
    p_cols = ("#2563eb", "#16a34a", "#dc2626", "#9333ea")
    p_names = ("Petal 0\nEast", "Petal 1\nNorth", "Petal 2\nWest", "Petal 3\nSouth")
    cmap_seg = ListedColormap(["#0f172a", *p_cols])
    ax.imshow(labels + 1, origin="lower", cmap=cmap_seg, vmin=0, vmax=4, extent=ext)
    yy, xx = np.indices((nwf, nwf), dtype=np.float64)
    scale_m = (ext[1] - ext[0]) / nwf
    for p in range(n_petals):
        msk = labels == p
        cx_m = ext[0] + float(np.mean(xx[msk])) * scale_m
        cy_m = ext[0] + float(np.mean(yy[msk])) * scale_m
        ax.text(
            cx_m,
            cy_m,
            f"{p_names[p]}\n({p_fracs[p]*100:.1f}%)",
            ha="center",
            va="center",
            color="#ffffff",
            fontsize=8.6,
            fontweight="bold",
            bbox={"boxstyle": "round,pad=0.22", "fc": "#0f172a", "ec": "none", "alpha": 0.55},
        )
    ax.set_xlabel("Pupil X [m]")
    ax.set_ylabel("Pupil Y [m]")
    ax.set_title("Automatic 4-Connected Subaru V-Spider Island Segmentation")

    # Panel (0,1): Instantaneous LWE OPD map + H-band split-core PSF inset
    ax = axes[0, 1]
    cmap_opd = plt.get_cmap("RdBu_r").copy()
    cmap_opd.set_bad("#0f172a")
    lwe_vis = np.where(active, lwe_map, np.nan)
    vlim = max(420.0, float(np.nanpercentile(np.abs(lwe_vis), 99.5)))
    im1 = ax.imshow(lwe_vis, origin="lower", cmap=cmap_opd, vmin=-vlim, vmax=vlim, extent=ext)
    ax.set_xlabel("Pupil X [m]")
    ax.set_ylabel("Pupil Y [m]")
    ax.set_title(f"Instantaneous LWE OPD (RMS={snap_rms:.0f} nm, PTV={snap_ptv:.0f} nm)")
    cb = fig.colorbar(im1, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("Petal OPD [nm]")

    ins = ax.inset_axes([0.65, 0.04, 0.32, 0.32])
    ins.imshow(np.log10(np.maximum(psf_crop, 1e-4)), origin="lower", cmap="inferno", vmin=-3.5, vmax=0.0)
    ins.set_xticks([])
    ins.set_yticks([])
    for sp in ins.spines.values():
        sp.set_edgecolor("#f8fafc")
        sp.set_linewidth(1.2)
    ins.set_title(f"H-Band PSF\n(SR={sr_lwe:.0f}%)", fontsize=7.6, color="#ffffff",
                  fontweight="bold", pad=2,
                  bbox={"boxstyle": "round,pad=0.15", "fc": "#0f172a", "ec": "none", "alpha": 0.7})

    # Panel (1,0): 30 s differential island piston + PTV trajectories
    ax = axes[1, 0]
    p_lbls = ("Petal 0 (East)", "Petal 1 (North)", "Petal 2 (West)", "Petal 3 (South)")
    for p in range(n_petals):
        ax.plot(t_arr, dp[p], color=p_cols[p], lw=1.45, label=p_lbls[p])
    ax.plot(
        t_arr,
        ptv_t,
        color="#0f172a",
        lw=1.5,
        ls="--",
        label=f"Island PTV (mean={np.mean(ptv_t):.0f}, max={np.max(ptv_t):.0f} nm)",
    )
    ax.axhline(0.0, color="#94a3b8", lw=0.85, ls=":")
    ax.set_xlim(0.0, 30.0)
    ax.set_xlabel("Physical Time t [s]")
    ax.set_ylabel("Differential Island Piston [nm]")
    ax.set_title(f"30 s Thermal Petaling Evolution (Mean Total RMS = {np.mean(rms_t):.0f} nm)")
    ax.grid(True)
    ax.legend(loc="upper right", ncol=2, fontsize=7.7, framealpha=0.92)

    # Panel (1,1): Matern-3/2 temporal PSD across tau + 75%/25% variance breakdown
    ax = axes[1, 1]
    freqs = np.geomspace(5e-3, 5.0, 300)
    for tau_v, col, ls, lbl in (
        (1.0, "#d97706", "--", "Fast LWE (tau = 1.0 s, f_c = 0.159 Hz)"),
        (petal_tau, "#1d4ed8", "-", f"Default LWE (tau = {petal_tau:.1f} s, f_c = {pstats['corner_hz']:.3f} Hz)"),
        (10.0, "#059669", "-.", "Slow LWE (tau = 10.0 s, f_c = 0.016 Hz)"),
    ):
        psd = 8.0 * (petal_rms ** 2) * tau_v / ((1.0 + (2.0 * math.pi * freqs * tau_v) ** 2) ** 2)
        ax.loglog(freqs, psd, color=col, ls=ls, lw=2.0, label=lbl)
    ax.axvline(1.0 / (2.0 * math.pi * petal_tau), color="#1d4ed8", ls=":", lw=1.1)
    ax.set_xlim(5e-3, 5.0)
    ax.set_ylim(4e-2, 2e8)
    ax.set_xlabel("Temporal Frequency f [Hz]")
    ax.set_ylabel("Total Petaling OPD PSD [nm^2 / Hz]")
    ax.set_title("Matern-3/2 Temporal PSD (-40 dB/dec) & Modal Variance Split")
    ax.grid(True, which="both", alpha=0.35)
    ax.legend(loc="lower left", fontsize=7.8, framealpha=0.92)

    # Inset horizontal bar chart of variance breakdown (75% piston, 12.5% tip, 12.5% tilt)
    ins2 = ax.inset_axes([0.55, 0.54, 0.42, 0.37])
    ins2.set_facecolor("#ffffff")
    ins2.set_zorder(5)
    b_lbls = (
        f"Piston\n({float(pstats['piston_rms_nm']):.0f} nm)",
        f"Tip\n({float(pstats['local_tip_rms_nm']):.0f} nm)",
        f"Tilt\n({float(pstats['local_tilt_rms_nm']):.0f} nm)",
    )
    b_vals = (75.0, 12.5, 12.5)
    b_cols = ("#7e22ce", "#2563eb", "#0d9488")
    yb = np.arange(3)
    ins2.barh(yb, b_vals, color=b_cols, edgecolor="#1e293b", linewidth=0.6, height=0.62)
    ins2.set_yticks(yb, b_lbls, fontsize=7.0)
    ins2.set_xlim(0, 98)
    ins2.set_xlabel("Variance Share [%]", fontsize=7.1)
    ins2.set_title(f"{petal_rms:.0f} nm LWE Budget", fontsize=7.8, fontweight="bold", pad=2)
    ins2.tick_params(axis="x", labelsize=6.9)
    ins2.grid(True, axis="x", alpha=0.4)
    for y_i, v in enumerate(b_vals):
        ins2.text(v + 2.0, y_i, f"{v:.1f}%", va="center", fontsize=7.0, fontweight="bold")

    fig.savefig(out_dir / "turb_petaling_lwe_2x2.png", dpi=170)
    plt.close(fig)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Default Turbulence & Perturbation Model visual figures."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory for PNG visuals (default: {DEFAULT_OUT_DIR})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir: Path = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    _set_style()
    pup = build_subaru_pupil(256)
    make_fig1_profile_and_spectrum(out_dir)
    make_fig2_wavefront_screens(out_dir, pup)
    make_fig3_wind_dynamics(out_dir)
    make_fig4_vibrations(out_dir, pup)
    make_fig5_petaling_lwe(out_dir, pup)
    for png in sorted(out_dir.glob("*.png")):
        print(f"[build-turbulence-model-visuals] Wrote {png.name} ({png.stat().st_size / 1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
