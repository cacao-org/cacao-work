# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Live GPU cacaosim + cacao 3D RM -> optimal DM pre-shaper WITH vs. WITHOUT acquisition."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from astropy.io import fits
import numpy as np
from scipy.special import jv

from scripts.studies.dyn_rm_64x64.acquire import AO3K_PLATE64_BENCH, ZONAL_POKES, build_zernike_cube

REPO_ROOT = Path(__file__).resolve().parents[3]
REPLAY_C = Path(__file__).resolve().parent / "replay_capture.c"

N_ACT = 64
N_WF = 256
N_WFS = 160
FS_HZ = 8000.0
WFS_HZ = 1000.0
NB_SUBFR = 8
DT_SEC = 1.0 / FS_HZ  # 125 us (8 kHz master & DM pre-shaper clock; 1 kHz J-band PyWFS)
N_STEP_TICKS = 200    # 25.0 ms at 8 kHz
Q0_STEP = 16          # 2.0 ms pre-onset baseline
N_AG_TICKS = 320      # 40.0 ms at 8 kHz
T_ON_AG = 16          # 2.0 ms
HALF_TICKS_AG = 8     # 8 * 125 us = 1.0 ms half-period -> 500.0 Hz fundamental
QUAD_STEP_TICKS = 4   # 4 * 125 us = 0.5 ms -> 2 kHz steps = 500.0 Hz 4-phase rotation
WARMUP_TICKS = 128    # 16.0 ms dead-zero settling


def _active_dm_mask(nact: int = N_ACT, r_max: float = 30.8) -> np.ndarray:
    yy, xx = np.mgrid[0:nact, 0:nact]
    ctr = 0.5 * (nact - 1)
    return np.hypot(xx - ctr, yy - ctr) <= r_max


def build_zonal4_cube(nact: int = N_ACT) -> np.ndarray:
    cube = np.zeros((len(ZONAL_POKES), nact, nact), dtype=np.float32)
    for i, item in enumerate(ZONAL_POKES):
        cube[i, int(item["ay"]), int(item["ax"])] = 1.0
    return cube


def build_concentric_rings_cube(
    ax: int = 22,
    ay: int = 23,
    nact: int = N_ACT,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """8-mode orthogonal concentric radial-ring basis around actuator (ax, ay).

    Mode 0 is the pure unit single-actuator poke at (ax, ay); modes 1..7 are
    non-overlapping concentric rings out to r = 8.5 actuator pitches so a KMODE=0
    MIMO pre-shaper can actively fire counter-phase wave-absorption pulses on
    surrounding rings without any static projection loss on the single poke.
    """
    yy, xx = np.mgrid[0:nact, 0:nact]
    rr = np.hypot(xx - ax, yy - ay)
    act_mask = _active_dm_mask(nact)

    edges = [
        (0.0, 0.25, "Center (r=0)"),
        (0.25, 1.15, "Ring 1 (r=1.0)"),
        (1.15, 1.65, "Ring 2 (r=1.4)"),
        (1.65, 2.45, "Ring 3 (r=2.0-2.2)"),
        (2.45, 3.45, "Ring 4 (r=2.8-3.2)"),
        (3.45, 4.65, "Ring 5 (r=3.6-4.5)"),
        (4.65, 6.25, "Ring 6 (r=5.0-6.1)"),
        (6.25, 8.25, "Ring 7 (r=6.3-8.1)"),
    ]
    modes: list[np.ndarray] = []
    meta: list[dict[str, Any]] = []
    for idx, (r0, r1, label) in enumerate(edges):
        sel = (rr >= r0) & (rr <= r1) & act_mask
        if idx == 0:
            sel = np.zeros((nact, nact), dtype=bool)
            sel[ay, ax] = True
        arr = sel.astype(np.float32)
        modes.append(arr)
        meta.append(
            {
                "mode": idx,
                "label": label,
                "r_min": r0,
                "r_max": r1,
                "n_act": int(sel.sum()),
                "r_mean": float(rr[sel].mean()) if sel.any() else 0.0,
            }
        )
    return np.stack(modes, axis=0), meta


def build_astrogrid_basis(
    nact: int = N_ACT,
    k_main: float = 8.0,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """20-mode Astrogrid Fourier + Jacobi-Anger circular-plate free-rim subspace.

    Modes 0..7 span the axis-aligned crossed-sinusoid astrogrid subspace
    (k = 8 cpa cos/sin + k = 6, 7, 9, 10 sidebands), placing 4 astrometric
    satellite spots at (+-k, 0) and (0, +-k) lambda/D away from Subaru's spiders.
    Modes 8..19 append the exact Jacobi-Anger cylindrical plate eigenmodes
    J_m(2*pi*k*r) cos(m*theta) (m = 0, 4, 8, 12, 16 at k = 7.7, 8.2 cpa, plus
    quadrature J_1, J_3 at k = 8.0 cpa) excited when a Cartesian astrogrid
    scatters off the circular free rim of the 64x64 ALPAO facesheet.

    Mode 0 is the exact unperturbed k=8 cpa crossed cosine astrogrid; modes 1..19
    are Gram-Schmidt orthogonalized inside the active circular DM aperture so
    P_PINV recovers exact mode amplitudes with zero leakage.
    """
    yy, xx = np.mgrid[0:nact, 0:nact]
    ctr = 0.5 * (nact - 1)
    # Match optical pupil diameter fraction: pup_diam / dm_diam = 0.9375 / 0.984375 = 0.95238
    # Span across pupil in actuator pitches: 63 * (0.9375 / 0.984375) = 60.0 pitches
    d_pup = 60.0
    ux = (xx - ctr) / d_pup
    uy = (yy - ctr) / d_pup
    r_cyc = np.hypot(ux, uy)
    th = np.arctan2(uy, ux)
    mask = _active_dm_mask(nact, r_max=31.2).astype(np.float64)

    def _raw(k: float, kind: str) -> np.ndarray:
        thx = 2.0 * np.pi * k * ux
        thy = 2.0 * np.pi * k * uy
        if kind == "cos_plus":
            f = (np.cos(thx) + np.cos(thy)) / np.sqrt(2.0)
        elif kind == "cos_minus":
            f = (np.cos(thx) - np.cos(thy)) / np.sqrt(2.0)
        elif kind == "sin_plus":
            f = (np.sin(thx) + np.sin(thy)) / np.sqrt(2.0)
        elif kind == "sin_minus":
            f = (np.sin(thx) - np.sin(thy)) / np.sqrt(2.0)
        elif kind.startswith("bessel_c_"):
            m_az = int(kind.split("_")[-1])
            f = jv(m_az, 2.0 * np.pi * k * r_cyc) * np.cos(m_az * th)
        elif kind == "bessel_s_1":
            f = jv(1, 2.0 * np.pi * k * r_cyc) * (np.cos(th) + np.sin(th))
        elif kind == "bessel_s_3":
            f = jv(3, 2.0 * np.pi * k * r_cyc) * (np.cos(3.0 * th) - np.sin(3.0 * th))
        else:
            raise ValueError(kind)
        return f * mask

    specs = [
        (k_main, "cos_plus", f"Astrogrid k={k_main:.0f} cos+ (4-spot)"),
        (k_main, "sin_plus", f"Astrogrid k={k_main:.0f} sin+ (quadrature)"),
        (k_main, "cos_minus", f"Astrogrid k={k_main:.0f} cos- (orth)"),
        (k_main, "sin_minus", f"Astrogrid k={k_main:.0f} sin- (orth)"),
        (k_main - 1.0, "cos_plus", f"Sideband k={k_main - 1:.0f} cos+"),
        (k_main + 1.0, "cos_plus", f"Sideband k={k_main + 1:.0f} cos+"),
        (k_main - 2.0, "cos_plus", f"Astrogrid k={k_main - 2:.0f} cos+"),
        (k_main + 2.0, "cos_plus", f"Astrogrid k={k_main + 2:.0f} cos+"),
        # Jacobi-Anger circular free-rim scattered modes for cos(kx)+cos(ky) (m = 0,4,8,12,16)
        (k_main - 0.3, "bessel_c_0", f"Rim Bessel J0 k={k_main - 0.3:.1f}"),
        (k_main + 0.2, "bessel_c_0", f"Rim Bessel J0 k={k_main + 0.2:.1f}"),
        (k_main - 0.3, "bessel_c_4", f"Rim Bessel J4 cos4t k={k_main - 0.3:.1f}"),
        (k_main + 0.2, "bessel_c_4", f"Rim Bessel J4 cos4t k={k_main + 0.2:.1f}"),
        (k_main - 0.3, "bessel_c_8", f"Rim Bessel J8 cos8t k={k_main - 0.3:.1f}"),
        (k_main + 0.2, "bessel_c_8", f"Rim Bessel J8 cos8t k={k_main + 0.2:.1f}"),
        (k_main - 0.3, "bessel_c_12", f"Rim Bessel J12 cos12t k={k_main - 0.3:.1f}"),
        (k_main + 0.2, "bessel_c_12", f"Rim Bessel J12 cos12t k={k_main + 0.2:.1f}"),
        (k_main - 0.3, "bessel_c_16", f"Rim Bessel J16 cos16t k={k_main - 0.3:.1f}"),
        (k_main + 0.2, "bessel_c_16", f"Rim Bessel J16 cos16t k={k_main + 0.2:.1f}"),
        # Quadrature Jacobi-Anger rim modes for sin(kx)+sin(ky) (m = 1, 3)
        (k_main, "bessel_s_1", f"Rim Bessel J1 quad k={k_main:.0f}"),
        (k_main, "bessel_s_3", f"Rim Bessel J3 quad k={k_main:.0f}"),
    ]

    raw_modes = [_raw(k, kind) for k, kind, _ in specs]
    orth_modes: list[np.ndarray] = []
    meta: list[dict[str, Any]] = []
    for idx, ((k, kind, label), m) in enumerate(zip(specs, raw_modes)):
        v = m.copy()
        for prev in orth_modes:
            denom = float(np.sum(prev * prev))
            if denom > 1e-12:
                v -= (float(np.sum(v * prev)) / denom) * prev
        # Normalize peak amplitude inside pupil to 1.0 so actuator commands are in [um]
        vmax = float(np.max(np.abs(v)))
        if vmax > 1e-12:
            v /= vmax
        orth_modes.append(v)
        # Theoretical discrete plate resonant frequency [Hz]
        theta = 2.0 * np.pi * k / d_pup
        lam_k = 4.0 * (math.sin(0.5 * theta) ** 2)
        w0 = 2.0 * math.pi * 1000.0
        cmp = 14.0 / 0.0015
        betap = 0.0085 / (0.0015 ** 2)
        w_k = math.sqrt(w0 * w0 + cmp * cmp * lam_k + betap * betap * lam_k * lam_k)
        f_res_hz = w_k / (2.0 * math.pi)
        zeta_k = (195.0 + 1.5 * lam_k) / w_k
        dc_gain = (w0 * w0) / (w_k * w_k)
        meta.append(
            {
                "mode": idx,
                "k_cpa": k,
                "kind": kind,
                "label": label,
                "f_res_hz": round(f_res_hz, 1),
                "zeta": round(zeta_k, 4),
                "q_factor": round(0.5 / zeta_k, 1),
                "dc_gain_plate": round(dc_gain, 4),
            }
        )
    return np.stack(orth_modes, axis=0).astype(np.float32), meta


def _parse_fps_info(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    if not path.is_file():
        return out
    clean = re.sub(r"\x1b\[[0-9;]*m", "", path.read_text(encoding="utf-8", errors="ignore"))
    for line in clean.splitlines():
        parts = line.split()
        if len(parts) >= 4 and (parts[0] == "---" or parts[0].isdigit()):
            key = parts[1].lstrip(".")
            try:
                out[key] = float(parts[3])
            except ValueError:
                pass
    return out


def _read_fits_hdr_metrics(path: Path, keys: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    if not path.is_file():
        return out
    hdr = fits.getheader(path)
    for k in keys:
        if k in hdr:
            try:
                out[k] = float(hdr[k])
            except (TypeError, ValueError):
                pass
    return out


def _compile_replay_helper(out_bin: Path, env: dict[str, str]) -> Path:
    milk_root = env.get("MILK_ROOT") or "/home/guyon/src/milk/_install/milk-1.03.00"
    cmd = [
        "gcc",
        "-O2",
        "-Wall",
        "-Wextra",
        f"-I{milk_root}/include",
        str(REPLAY_C),
        f"-L{milk_root}/lib",
        f"-Wl,-rpath,{milk_root}/lib",
        "-lImageStreamIO",
        "-lm",
        "-lrt",
        "-lpthread",
        "-o",
        str(out_bin),
    ]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to compile replay_capture.c:\n{res.stderr}")
    return out_bin


def _build_replay_schedules(
    raw_dir: Path,
    rings8: np.ndarray,
    zern28: np.ndarray,
    astro8: np.ndarray,
) -> dict[str, dict[str, Any]]:
    """Build tick-exact 8 kHz DM command schedules (.bin float32) for all demo scenarios."""
    sched_dir = raw_dir / "schedules"
    sched_dir.mkdir(parents=True, exist_ok=True)
    specs: dict[str, dict[str, Any]] = {}

    def _save(name: str, seq: np.ndarray, meta: dict[str, Any]) -> None:
        arr = np.ascontiguousarray(seq, dtype=np.float32)
        p = sched_dir / f"{name}.bin"
        arr.tofile(p)
        specs[name] = {"path": str(p), "n_ticks": int(arr.shape[0]), **meta}

    # 1. Single-actuator interior poke (22, 23): 1.0 um step at tick 16 (2.0 ms), 200 ticks (25 ms)
    q0 = Q0_STEP
    n_step = N_STEP_TICKS
    seq = np.zeros((n_step, N_ACT, N_ACT), dtype=np.float32)
    seq[q0:] = 1.0 * rings8[0]
    _save(
        "poke_interior",
        seq,
        {"kind": "step", "q0": q0, "ampl_um": 1.0, "ax": 22, "ay": 23, "label": "Interior Poke (22, 23)"},
    )

    # 2. Single-actuator free-rim poke (57, 31): 1.0 um step at tick 16, 200 ticks (25 ms)
    seq = np.zeros((n_step, N_ACT, N_ACT), dtype=np.float32)
    seq[q0:, 31, 57] = 1.0
    _save(
        "poke_rim",
        seq,
        {"kind": "step", "q0": q0, "ampl_um": 1.0, "ax": 57, "ay": 31, "label": "Free-Rim Poke (57, 31)"},
    )

    # 3. Low-order modal step: Z4 Focus (index 2 in Z2..Z29), 0.25 um step at tick 16
    seq = np.zeros((n_step, N_ACT, N_ACT), dtype=np.float32)
    seq[q0:] = 0.25 * zern28[2]
    _save(
        "zernike_focus",
        seq,
        {"kind": "step", "q0": q0, "ampl_um": 0.25, "mode_idx": 2, "label": "Zernike Focus (Z4)"},
    )

    # 4. Low-order modal step: Z5 Oblique Astigmatism (index 3 in Z2..Z29), 0.25 um step at tick 16
    seq = np.zeros((n_step, N_ACT, N_ACT), dtype=np.float32)
    seq[q0:] = 0.25 * zern28[3]
    _save(
        "zernike_astig",
        seq,
        {"kind": "step", "q0": q0, "ampl_um": 0.25, "mode_idx": 3, "label": "Zernike Astigmatism (Z5)"},
    )

    # 5. 500 Hz Square-Wave Polarity-Flipping Astrogrid (k=8 cpa):
    #    0 for 2 ms (16 ticks) -> +-0.25 um flipping every 1.0 ms (8 ticks = 500 Hz full cycle)
    #    for 12 full cycles (192 ticks = 24 ms) -> 0 ring-down for 112 ticks (14 ms). Total: 320 ticks = 40 ms.
    n_ag = N_AG_TICKS
    t_on = T_ON_AG
    n_half = HALF_TICKS_AG
    n_cycles = 12
    t_off = t_on + n_cycles * 2 * n_half  # tick 208 (26.0 ms)
    seq = np.zeros((n_ag, N_ACT, N_ACT), dtype=np.float32)
    target_amp = np.zeros(n_ag, dtype=np.float32)
    for t in range(t_on, t_off):
        half_idx = (t - t_on) // n_half
        sign = 1.0 if (half_idx % 2 == 0) else -1.0
        target_amp[t] = 0.25 * sign
        seq[t] = target_amp[t] * astro8[0]
    _save(
        "astro_500hz_sq",
        seq,
        {
            "kind": "astro_sq",
            "t_on": t_on,
            "t_off": t_off,
            "half_ticks": n_half,
            "freq_hz": 500.0,
            "k_cpa": 8.0,
            "ampl_um": 0.25,
            "mode_idx": 0,
            "target_amp": target_amp.tolist(),
            "label": "500 Hz Square-Wave Astrogrid (k = 8 cpa)",
        },
    )

    # 6. 500 Hz Square-Wave Astrogrid at k=10 cpa (mode 7 in astro8): same burst timing
    seq = np.zeros((n_ag, N_ACT, N_ACT), dtype=np.float32)
    for t in range(t_on, t_off):
        half_idx = (t - t_on) // n_half
        sign = 1.0 if (half_idx % 2 == 0) else -1.0
        seq[t] = (0.25 * sign) * astro8[7]
    _save(
        "astro_500hz_k10",
        seq,
        {
            "kind": "astro_sq",
            "t_on": t_on,
            "t_off": t_off,
            "half_ticks": n_half,
            "freq_hz": 500.0,
            "k_cpa": 10.0,
            "ampl_um": 0.25,
            "mode_idx": 7,
            "target_amp": target_amp.tolist(),
            "label": "500 Hz Square-Wave Astrogrid (k = 10 cpa)",
        },
    )

    # 7. 500 Hz 4-Phase Quadrature Rotating Astrogrid (k=8 cpa):
    #    Steps every 0.5 ms (4 ticks = 2 kHz step rate -> 500 Hz full 4-phase rotation):
    #    +cos -> +sin -> -cos -> -sin
    seq = np.zeros((n_ag, N_ACT, N_ACT), dtype=np.float32)
    q_step = QUAD_STEP_TICKS
    t_off_q = t_on + n_cycles * 4 * q_step  # tick 208 (26.0 ms)
    target_cos = np.zeros(n_ag, dtype=np.float32)
    target_sin = np.zeros(n_ag, dtype=np.float32)
    for t in range(t_on, t_off_q):
        ph = ((t - t_on) // q_step) % 4
        if ph == 0:
            c, s = 0.25, 0.0
        elif ph == 1:
            c, s = 0.0, 0.25
        elif ph == 2:
            c, s = -0.25, 0.0
        else:
            c, s = 0.0, -0.25
        target_cos[t] = c
        target_sin[t] = s
        seq[t] = c * astro8[0] + s * astro8[1]
    _save(
        "astro_500hz_quad",
        seq,
        {
            "kind": "astro_quad",
            "t_on": t_on,
            "t_off": t_off_q,
            "step_ticks": q_step,
            "freq_hz": 500.0,
            "k_cpa": 8.0,
            "ampl_um": 0.25,
            "target_cos": target_cos.tolist(),
            "target_sin": target_sin.tolist(),
            "label": "500 Hz 4-Phase Quadrature Astrogrid (k = 8 cpa)",
        },
    )

    return specs


def run_acquisition(raw_dir: Path) -> dict[str, Any]:
    """Execute full live GPU calibration (3D RM -> optimal preshaper) and WITH/WITHOUT replays."""
    raw_dir = Path(raw_dir).resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build all spatial mode bases & replay schedules
    zonal4 = build_zonal4_cube()
    rings8, rings_meta = build_concentric_rings_cube(ax=22, ay=23)
    zern28, zern_meta = build_zernike_cube(nact=N_ACT, n_modes=28)
    astro20, astro_meta = build_astrogrid_basis(nact=N_ACT, k_main=8.0)

    fits.writeto(raw_dir / "zonal4_modes.fits", zonal4, overwrite=True)
    fits.writeto(raw_dir / "rings8_modes.fits", rings8, overwrite=True)
    fits.writeto(raw_dir / "zernike28_modes.fits", zern28, overwrite=True)
    fits.writeto(raw_dir / "zernike8_modes.fits", zern28[:8], overwrite=True)
    fits.writeto(raw_dir / "astro20_modes.fits", astro20, overwrite=True)
    fits.writeto(raw_dir / "zero64.fits", np.zeros((N_ACT, N_ACT), dtype=np.float32), overwrite=True)
    fits.writeto(raw_dir / "clk1.fits", np.zeros((1, 1), dtype=np.float32), overwrite=True)

    schedules = _build_replay_schedules(raw_dir, rings8, zern28, astro20)

    # 2. Isolated SHM + workdir sandbox
    pid = os.getpid()
    shm_dir = Path(f"/dev/shm/cacao_psdemo_{pid}")
    work_dir = Path(tempfile.mkdtemp(prefix="cacao_psdemo_work_"))
    shm_dir.mkdir(parents=True, exist_ok=True)
    (shm_dir / "proc").mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["MILK_SHM_DIR"] = str(shm_dir)
    env["MILK_PROC_DIR"] = str(shm_dir / "proc")
    env["CACAOSIM_WORKDIR"] = str(work_dir)
    env["MILK_QUIET"] = "1"

    bench_file = work_dir / "ao3k_plate64_demo.bench"
    # 8,000 Hz physical master & DM clock (dt = 125.0 us) with 1,000 Hz J-band PyWFS (navg = 8 -> 1.0 ms exposure).
    # During lockstep 3D RM calibration, csim_htsim paces wall-clock at 3,200 Hz while stepping exact 125 us physics
    # and pulsing csim_dm01_opd once per 125 us tick -> zero timer overruns, zero drops, exact 8 kHz lockstep.
    demo_bench = (
        AO3K_PLATE64_BENCH
        .replace("master_hz     = 4000.0", "master_hz     = 8000.0")
        .replace("navg          = 4", "navg          = 8")
        .replace("mod_npts      = 16", "mod_npts      = 10")
    )
    bench_file.write_text(demo_bench, encoding="utf-8")

    # Source env.sh to capture exact MILK_ROOT / PYTHON_BIN for compilation & bash script
    probe = subprocess.run(
        ["bash", "-lc", f'source "{REPO_ROOT}/env.sh" && printf "%s\\n%s\\n" "$MILK_ROOT" "$PYTHON_BIN"'],
        capture_output=True,
        text=True,
        check=True,
    )
    milk_root_str, py_bin = [ln.strip() for ln in probe.stdout.strip().splitlines()[:2]]
    env["MILK_ROOT"] = milk_root_str
    env["PYTHON_BIN"] = py_bin

    replay_bin = _compile_replay_helper(work_dir / "replay_capture", env)
    replays_dir = raw_dir / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)

    # Replay execution plan: (scenario_name, tag, kernel_file, enable_flag)
    replay_jobs = [
        ("poke_interior", "off", "ps_siso_uniform.fits", "OFF"),
        ("poke_interior", "siso", "ps_siso_uniform.fits", "ON"),
        ("poke_interior", "mimo", "ps_rings8_mimo.fits", "ON"),
        ("poke_rim", "off", "ps_siso_uniform.fits", "OFF"),
        ("poke_rim", "siso", "ps_siso_uniform.fits", "ON"),
        ("zernike_focus", "off", "ps_zernike28_mimo.fits", "OFF"),
        ("zernike_focus", "mimo", "ps_zernike28_mimo.fits", "ON"),
        ("zernike_astig", "off", "ps_zernike28_mimo.fits", "OFF"),
        ("zernike_astig", "mimo", "ps_zernike28_mimo.fits", "ON"),
        ("astro_500hz_sq", "off", "ps_astro20_mimo.fits", "OFF"),
        ("astro_500hz_sq", "siso", "ps_siso_uniform.fits", "ON"),
        ("astro_500hz_sq", "mimo", "ps_astro20_mimo.fits", "ON"),
        ("astro_500hz_k10", "off", "ps_astro20_mimo.fits", "OFF"),
        ("astro_500hz_k10", "mimo", "ps_astro20_mimo.fits", "ON"),
        ("astro_500hz_quad", "off", "ps_astro20_mimo.fits", "OFF"),
        ("astro_500hz_quad", "mimo", "ps_astro20_mimo.fits", "ON"),
    ]

    replay_cmds_lines: list[str] = []
    for scen, tag, kfile, en in replay_jobs:
        sc = schedules[scen]
        prefix = f"{replays_dir}/{scen}_{tag}"
        replay_cmds_lines.append(
            f'run_lockstep_replay "{scen}_{tag}" "{kfile}" "{en}" "{sc["n_ticks"]}" '
            f'"{sc["path"]}" "{prefix}_disp.bin" "{prefix}_opd.bin" "{prefix}_wfs.bin"'
        )
    replay_cmds_block = "\n".join(replay_cmds_lines)

    bash_script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{work_dir}"
export MILK_QUIET=1

cleanup() {{
    milk-fps-runstop -q dmps_rt >/dev/null 2>&1 || true
    milk-fps-runstop -q dmps_ls >/dev/null 2>&1 || true
    milk-fps-rm -f -q mdr_z4 mdr_r8 mdr_z28 mdr_ag20 mdr_p2z mdr_p2a cps_s cps_r cps_z cps_a dmps_rt dmps_ls >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

echo "[1/5] Deploying live GPU Subaru AO3k 64x64 ALPAO Plate DM bench (8 kHz DM/physics, 1 kHz J-band PyWFS)..."
cacaosim-bench deploy --workdir "{work_dir}" --config "{bench_file}" --mode fused --no-view >/dev/null
# Pace wall-clock cleanly at 3,200 Hz while simulating exact 8,000 Hz (125 us) plate & WFS physics
milk-fps-set -q csim_htsim.frame_rate=3200.0
milk-stream-wait -q -t 25 csim_wfs_nir:160x160 dm01disp:64x64 csim_dm01_opd:256x256 csim_pup:256x256

cd "{raw_dir}"

# Save exact Subaru Nasmyth-IR pupil & build PyWFS active pixel mask
milk-fpsexec-iofits-saveFITS --no-procinfo -n snappup exec csim_pup "!pupil.fits" >/dev/null
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapwfs exec csim_wfs_nir "!wfs_snap.fits" >/dev/null
"{py_bin}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("wfs_snap.fits").astype(np.float32)
sig = wfs - float(np.percentile(wfs, 5.0))
mask = (sig > 0.20 * float(sig.max())).astype(np.float32)
fits.writeto("wfsmask.fits", mask, overwrite=True)
print(f"PyWFS mask active pixels: {{int(mask.sum())}} / {{mask.size}}")
PY

milk-FITS2shm --no-procinfo -n ldcmd exec zero64.fits @S:dm01cmd >/dev/null
milk-FITS2shm --no-procinfo -n ldclk exec clk1.fits @S:step_clk >/dev/null

run_mdr() {{
    local name="$1"
    local streamin="$2"
    local inmodes="$3"
    local outcube="$4"
    local ampl="$5"
    local nbresp="$6"
    milk-fps-init -q "$name" cacao-fpsexec-cacaoac-measdynresp >/dev/null
    milk-fps-set -q \\
        "${{name}}.streamin=${{streamin}}" \\
        "${{name}}.streamout=csim_wfs_nir" \\
        "${{name}}.trigstream=csim_dm01_opd" \\
        "${{name}}.inmodes=${{inmodes}}" \\
        "${{name}}.outcube=${{outcube}}" \\
        "${{name}}.outmask=wfsmask.fits" \\
        "${{name}}.ampl=${{ampl}}" \\
        "${{name}}.timing.WFSfrequ=1000.0" \\
        "${{name}}.timing.NBsubfr=8" \\
        "${{name}}.timing.NBrespfr=${{nbresp}}" \\
        "${{name}}.timing.NBprefr=2" \\
        "${{name}}.timing.NBsettlefr=4" \\
        "${{name}}.pokemode=1" \\
        "${{name}}.phaseorder=1" \\
        "${{name}}.procinfo.loopcntMax=1"
    milk-fps-runstart -q "$name"
    milk-fps-wait -q -t 240 "$name"
    milk-fps-info "$name" > "${{name}}_info.txt"
    milk-fps-rm -f -q "$name"
    local status_line
    status_line=$("{py_bin}" -c "import re, pathlib; s=re.sub(r'\\x1b\\[[0-9;]*m','',pathlib.Path('${{name}}_info.txt').read_text()); kv={{p[1].lstrip('.'):p[3] for ln in s.splitlines() for p in [ln.split()] if len(p)>=4 and (p[0]=='---' or p[0].isdigit())}}; dr=int(float(kv.get('out.dropped_frames','0'))); dt=float(kv.get('out.dt_us','125.0')); print(f'dt={{dt:.2f}} us, drops={{dr}}')")
    echo "  -> $name: $status_line"
}}

run_cps() {{
    local name="$1"
    local resp3d="$2"
    local inmodes="$3"
    local outkern="$4"
    local outpred="$5"
    local mode="$6"
    local ntaps="$7"
    local tau_us="$8"
    local lctrl="$9"
    local ldiff="${{10}}"
    local maxg="${{11}}"
    local ldec="${{12}}"
    milk-fps-init -q "$name" cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
    milk-fps-set -q \\
        "${{name}}.resp3d=${{resp3d}}" \\
        "${{name}}.inmodes=${{inmodes}}" \\
        "${{name}}.outkernel=${{outkern}}" \\
        "${{name}}.outpred=${{outpred}}" \\
        "${{name}}.mode=${{mode}}" \\
        "${{name}}.n_taps=${{ntaps}}" \\
        "${{name}}.dt_us=125.0" \\
        "${{name}}.texp_us=1000.0" \\
        "${{name}}.tau_target_us=${{tau_us}}" \\
        "${{name}}.lambda_ctrl=${{lctrl}}" \\
        "${{name}}.lambda_diff=${{ldiff}}" \\
        "${{name}}.max_gain=${{maxg}}" \\
        "${{name}}.deconv_exp=ON" \\
        "${{name}}.lambda_deconv=${{ldec}}" \\
        "${{name}}.energy_weight=ON" \\
        "${{name}}.procinfo.loopcntMax=1"
    milk-fps-runstart -q "$name"
    milk-fps-wait -q -t 120 "$name"
    milk-fps-info "$name" > "${{name}}_info.txt"
    milk-fps-rm -f -q "$name"
}}

echo "[2/5] Phase A — Lockstep 8 kHz stroboscopic 3D RM calibration (1 kHz PyWFS -> 8 kHz / 125 us, NBsubfr=8)..."
run_mdr mdr_z4  dm01disp zonal4_modes.fits    zonal4_resp3D.fits    0.25 22
run_mdr mdr_r8  dm01disp rings8_modes.fits    rings8_resp3D.fits    0.15 22
run_mdr mdr_z28 dm01disp zernike28_modes.fits zernike28_resp3D.fits 0.04 22
run_mdr mdr_ag20 dm01disp astro20_modes.fits  astro20_resp3D.fits   0.08 22

echo "[3/5] Phase B — Synthesizing optimal causal 8 kHz DM pre-shaper kernels (deconv_exp=ON, energy_weight=ON)..."
run_cps cps_s zonal4_resp3D.fits    zonal4_modes.fits    ps_siso_uniform.fits    pred_siso.fits    2 64 180.0 0.008 0.025 2.5 0.016
run_cps cps_r rings8_resp3D.fits    rings8_modes.fits    ps_rings8_mimo.fits     pred_rings8.fits  0 64 180.0 0.008 0.025 2.5 0.016
run_cps cps_z zernike28_resp3D.fits zernike28_modes.fits ps_zernike28_mimo.fits  pred_zern28.fits  0 64 200.0 0.008 0.020 2.4 0.016
run_cps cps_a astro20_resp3D.fits   astro20_modes.fits   ps_astro20_mimo.fits    pred_astro20.fits 0 72 120.0 0.005 0.012 2.8 0.008

echo "[4/5] Phase C — Live 8 kHz Pass-2 3D RM verification through active dmpreshaper..."
# C1: Pass-2 on Zernikes Z2..Z9 with live 8 kHz dmpreshaper
milk-fps-init -q dmps_rt cacao-fpsexec-dmpreshaper >/dev/null
milk-fps-set -q \\
    dmps_rt.streamin=dm01cmd \\
    dmps_rt.streamout=dm01disp \\
    dmps_rt.trigstream=csim_dm01_opd \\
    dmps_rt.kernelfile=ps_zernike28_mimo.fits \\
    dmps_rt.rate_hz=8000.0 \\
    dmps_rt.enable=ON \\
    dmps_rt.gain=1.0 \\
    dmps_rt.procinfo.loopcntMax=-1
milk-fps-runstart -q dmps_rt
sleep 0.15
run_mdr mdr_p2z dm01cmd zernike8_modes.fits zernike8_p2_resp3D.fits 0.04 22
milk-fps-info dmps_rt > dmps_rt_zern_info.txt
milk-fps-runstop -q dmps_rt
milk-fps-wait -q -t 10 dmps_rt
milk-fps-rm -f -q dmps_rt

# C2: Pass-2 on Astrogrid + Jacobi-Anger rim modes with live 8 kHz dmpreshaper
milk-fps-init -q dmps_rt cacao-fpsexec-dmpreshaper >/dev/null
milk-fps-set -q \\
    dmps_rt.streamin=dm01cmd \\
    dmps_rt.streamout=dm01disp \\
    dmps_rt.trigstream=csim_dm01_opd \\
    dmps_rt.kernelfile=ps_astro20_mimo.fits \\
    dmps_rt.rate_hz=8000.0 \\
    dmps_rt.enable=ON \\
    dmps_rt.gain=1.0 \\
    dmps_rt.procinfo.loopcntMax=-1
milk-fps-runstart -q dmps_rt
sleep 0.15
run_mdr mdr_p2a dm01cmd astro20_modes.fits astro20_p2_resp3D.fits 0.08 22
milk-fps-info dmps_rt > dmps_rt_astro_info.txt
milk-fps-runstop -q dmps_rt
milk-fps-wait -q -t 10 dmps_rt
milk-fps-rm -f -q dmps_rt

echo "[5/5] Phase D — Deterministic lockstep 8 kHz GPU physical surface replays (WITH vs WITHOUT)..."
# Switch csim_htsim to exact dm01disp-triggered lockstep mode (exact 125 us physics ticks)
milk-fps-runstop -q csim_htsim
milk-fps-wait -q -t 10 csim_htsim
milk-fps-set -q \\
    csim_htsim.frame_rate=0 \\
    csim_htsim.procinfo.triggermode=3 \\
    csim_htsim.procinfo.triggersname=dm01disp
milk-fps-runstart -q csim_htsim
sleep 0.2

run_lockstep_replay() {{
    local label="$1"
    local kfile="$2"
    local enable="$3"
    local nticks="$4"
    local inbin="$5"
    local outdisp="$6"
    local outopd="$7"
    local outwfs="$8"

    milk-fps-init -q dmps_ls cacao-fpsexec-dmpreshaper >/dev/null
    milk-fps-set -q \\
        dmps_ls.streamin=dm01cmd \\
        dmps_ls.streamout=dm01disp \\
        dmps_ls.trigstream=step_clk \\
        dmps_ls.kernelfile="${{kfile}}" \\
        dmps_ls.rate_hz=8000.0 \\
        dmps_ls.enable="${{enable}}" \\
        dmps_ls.gain=1.0 \\
        dmps_ls.procinfo.loopcntMax=-1
    milk-fps-runstart -q dmps_ls
    sleep 0.05

    "{replay_bin}" "${{nticks}}" {WARMUP_TICKS} "${{inbin}}" "${{outdisp}}" "${{outopd}}" "${{outwfs}}" \\
        dm01cmd step_clk dm01disp csim_dm01_opd csim_wfs_nir

    milk-fps-runstop -q dmps_ls
    milk-fps-wait -q -t 10 dmps_ls
    milk-fps-rm -f -q dmps_ls
}}

{replay_cmds_block}

echo "ALL ACQUISITION & REPLAYS COMPLETE."
"""

    try:
        res = subprocess.run(
            ["bash", "-lc", bash_script],
            env=env,
            capture_output=True,
            text=True,
            timeout=600.0,
            check=False,
        )
        print(res.stdout)
        if res.returncode != 0:
            print("STDERR:\n", res.stderr)
            raise RuntimeError(f"Live acquisition script failed (rc={res.returncode})")
    finally:
        shutil.rmtree(shm_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)

    # Collect calibration & Pass-2 telemetry metadata
    calib_meta = {
        "dt_us": DT_SEC * 1.0e6,
        "master_hz": FS_HZ,
        "wfs_hz": WFS_HZ,
        "nbsubfr": NB_SUBFR,
        "n_act": N_ACT,
        "n_wf": N_WF,
        "n_wfs": N_WFS,
        "rings_meta": rings_meta,
        "zern_meta": zern_meta,
        "astro_meta": astro_meta,
        "mdr_info": {
            "zonal4": _parse_fps_info(raw_dir / "mdr_z4_info.txt"),
            "rings8": _parse_fps_info(raw_dir / "mdr_r8_info.txt"),
            "zernike28": _parse_fps_info(raw_dir / "mdr_z28_info.txt"),
            "astro20": _parse_fps_info(raw_dir / "mdr_ag20_info.txt"),
            "p2_zernike8": _parse_fps_info(raw_dir / "mdr_p2z_info.txt"),
            "p2_astro20": _parse_fps_info(raw_dir / "mdr_p2a_info.txt"),
        },
        "cps_info": {
            "siso_uniform": _parse_fps_info(raw_dir / "cps_s_info.txt"),
            "rings8_mimo": _parse_fps_info(raw_dir / "cps_r_info.txt"),
            "zernike28_mimo": _parse_fps_info(raw_dir / "cps_z_info.txt"),
            "astro20_mimo": _parse_fps_info(raw_dir / "cps_a_info.txt"),
        },
        "dmps_rt_info": {
            "zernike8": _parse_fps_info(raw_dir / "dmps_rt_zern_info.txt"),
            "astro20": _parse_fps_info(raw_dir / "dmps_rt_astro_info.txt"),
        },
        "kernel_hdrs": {
            nm: _read_fits_hdr_metrics(
                raw_dir / fn,
                [
                    "KMODE",
                    "DT_SEC",
                    "NBIN",
                    "MBUF",
                    "TAUTARUS",
                    "DELAYUS",
                    "TEXPUS",
                    "LAMCTRL",
                    "LAMDIFF",
                    "DECONV",
                    "LAMDEC",
                    "ENRGWGT",
                    "MAXGAIN",
                    "ERRPRE",
                    "ERRPOST",
                    "OVPRE",
                    "OVPOST",
                    "OFFREDX",
                ],
            )
            for nm, fn in [
                ("siso_uniform", "ps_siso_uniform.fits"),
                ("rings8_mimo", "ps_rings8_mimo.fits"),
                ("zernike28_mimo", "ps_zernike28_mimo.fits"),
                ("astro20_mimo", "ps_astro20_mimo.fits"),
            ]
        },
        "resp_hdrs": {
            nm: _read_fits_hdr_metrics(
                raw_dir / fn, ["DT_SEC", "WFSDT", "Q0_BIN", "NBSUBFR"]
            )
            for nm, fn in [
                ("zonal4", "zonal4_resp3D.fits"),
                ("rings8", "rings8_resp3D.fits"),
                ("zernike28", "zernike28_resp3D.fits"),
                ("astro20", "astro20_resp3D.fits"),
                ("p2_zernike8", "zernike8_p2_resp3D.fits"),
                ("p2_astro20", "astro20_p2_resp3D.fits"),
            ]
        },
        "schedules": {
            k: {mk: mv for mk, mv in v.items() if mk != "path"}
            for k, v in schedules.items()
        },
    }

    (raw_dir / "calib_meta.json").write_text(json.dumps(calib_meta, indent=2), encoding="utf-8")
    peract_meta = run_per_actuator_acquisition(raw_dir)
    calib_meta["per_actuator"] = peract_meta
    (raw_dir / "calib_meta.json").write_text(json.dumps(calib_meta, indent=2), encoding="utf-8")
    return calib_meta


def build_per_actuator_patches(nact: int = N_ACT) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Build 86-actuator 2-patch spider-free zonal basis on the 64x64 ALPAO plate DM.

    - Interior patch (37 actuators): r <= 3.2 around (46, 31) (r_pup = 14.5, 100% spider-free).
    - Free-rim patch (49 actuators): ix in [55..61], iy in [28..34] (100% spider-free,
      spanning near-rim (57, 31) at r = 25.5 to optical free-rim edge (61, 31) at r = 29.5).
    """
    ctr = 0.5 * (nact - 1)
    coords: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int]] = set()
    for iy in range(nact):
        for ix in range(nact):
            if math.hypot(ix - 46, iy - 31) <= 3.2:
                coords.append((ix, iy, "interior"))
                seen.add((ix, iy))
    for iy in range(28, 35):
        for ix in range(55, 62):
            if (ix, iy) not in seen:
                coords.append((ix, iy, "rim"))
                seen.add((ix, iy))

    cube = np.zeros((len(coords), nact, nact), dtype=np.float32)
    meta: list[dict[str, Any]] = []
    for idx, (ix, iy, patch) in enumerate(coords):
        cube[idx, iy, ix] = 1.0
        r_ctr = math.hypot(ix - ctr, iy - ctr)
        meta.append(
            {
                "mode": idx,
                "ax": ix,
                "ay": iy,
                "patch": patch,
                "r_act": round(r_ctr, 3),
                "dist_to_rim": round(31.5 - r_ctr, 3),
            }
        )
    return cube, meta


def run_per_actuator_acquisition(raw_dir: Path, reuse_3drm: bool = False) -> dict[str, Any]:
    """Run live 8 kHz 64x64 GPU acquisition for per-actuator KMODE=3 (SISO) & KMODE=4 (5x5 MIMO)."""
    raw_dir = Path(raw_dir).resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)
    replays_dir = raw_dir / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)
    sched_dir = raw_dir / "schedules"
    sched_dir.mkdir(parents=True, exist_ok=True)

    pa_modes, pa_act_meta = build_per_actuator_patches(N_ACT)
    fits.writeto(raw_dir / "peract_patch_modes.fits", pa_modes, overwrite=True)
    if not (raw_dir / "zero64.fits").is_file():
        fits.writeto(raw_dir / "zero64.fits", np.zeros((N_ACT, N_ACT), dtype=np.float32), overwrite=True)
    if not (raw_dir / "clk1.fits").is_file():
        fits.writeto(raw_dir / "clk1.fits", np.zeros((1, 1), dtype=np.float32), overwrite=True)

    # Three single-actuator step schedules spanning interior -> near-rim -> free-rim edge
    pa_probes = [
        ("pa_int", 46, 31, "Interior (46, 31)"),
        ("pa_midrim", 57, 31, "Near-Rim (57, 31)"),
        ("pa_edge", 61, 31, "Free-Rim Edge (61, 31)"),
    ]
    probe_specs: dict[str, dict[str, Any]] = {}
    for pname, ax, ay, label in pa_probes:
        seq = np.zeros((N_STEP_TICKS, N_ACT, N_ACT), dtype=np.float32)
        seq[Q0_STEP:, ay, ax] = 1.0
        pbin = sched_dir / f"{pname}.bin"
        np.ascontiguousarray(seq, dtype=np.float32).tofile(pbin)
        probe_specs[pname] = {
            "path": str(pbin),
            "n_ticks": N_STEP_TICKS,
            "ax": ax,
            "ay": ay,
            "r_act": round(math.hypot(ax - 31.5, ay - 31.5), 2),
            "label": label,
        }

    pid = os.getpid()
    shm_dir = Path(f"/dev/shm/cacao_pspa_{pid}")
    work_dir = Path(tempfile.mkdtemp(prefix="cacao_pspa_work_"))
    shm_dir.mkdir(parents=True, exist_ok=True)
    (shm_dir / "proc").mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["MILK_SHM_DIR"] = str(shm_dir)
    env["MILK_PROC_DIR"] = str(shm_dir / "proc")
    env["CACAOSIM_WORKDIR"] = str(work_dir)
    env["MILK_QUIET"] = "1"

    bench_file = work_dir / "ao3k_plate64_demo.bench"
    demo_bench = (
        AO3K_PLATE64_BENCH
        .replace("master_hz     = 4000.0", "master_hz     = 8000.0")
        .replace("navg          = 4", "navg          = 8")
        .replace("mod_npts      = 16", "mod_npts      = 10")
    )
    bench_file.write_text(demo_bench, encoding="utf-8")

    probe = subprocess.run(
        ["bash", "-lc", f'source "{REPO_ROOT}/env.sh" && printf "%s\\n%s\\n" "$MILK_ROOT" "$PYTHON_BIN"'],
        capture_output=True,
        text=True,
        check=True,
    )
    milk_root_str, py_bin = [ln.strip() for ln in probe.stdout.strip().splitlines()[:2]]
    env["MILK_ROOT"] = milk_root_str
    env["PYTHON_BIN"] = py_bin

    replay_bin = _compile_replay_helper(work_dir / "replay_capture", env)

    # 3 probes x 4 modes (OFF, Uniform SISO KMODE=2, Per-Act SISO KMODE=3, Per-Act 5x5 MIMO KMODE=4)
    pa_jobs = []
    for pname, _, _, _ in pa_probes:
        pa_jobs.extend([
            (pname, "off", "ps_siso_uniform.fits", "OFF"),
            (pname, "siso", "ps_siso_uniform.fits", "ON"),
            (pname, "k3", "ps_peract_k3.fits", "ON"),
            (pname, "k4", "ps_peract_k4.fits", "ON"),
        ])

    replay_lines = []
    for pname, tag, kfile, en in pa_jobs:
        sc = probe_specs[pname]
        prefix = f"{replays_dir}/{pname}_{tag}"
        replay_lines.append(
            f'run_lockstep_replay "{pname}_{tag}" "{kfile}" "{en}" "{sc["n_ticks"]}" '
            f'"{sc["path"]}" "{prefix}_disp.bin" "{prefix}_opd.bin" "{prefix}_wfs.bin"'
        )
    replay_block = "\n".join(replay_lines)

    bash_script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{work_dir}"
export MILK_QUIET=1

cleanup() {{
    milk-fps-runstop -q dmps_ls >/dev/null 2>&1 || true
    milk-fps-rm -f -q mdr_pa cps_k3 cps_k3f cps_k4 cps_k4f dmps_ls >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

echo "[Per-Act 1/3] Deploying 8 kHz 64x64 ALPAO Plate DM bench for 86-actuator 2-patch calibration..."
cacaosim-bench deploy --workdir "{work_dir}" --config "{bench_file}" --mode fused --no-view >/dev/null
milk-fps-set -q csim_htsim.frame_rate=3200.0
milk-stream-wait -q -t 25 csim_wfs_nir:160x160 dm01disp:64x64 csim_dm01_opd:256x256 csim_pup:256x256

cd "{raw_dir}"
if [ ! -f wfsmask.fits ]; then
    milk-fpsexec-iofits-saveFITS --no-procinfo -n snappup exec csim_pup "!pupil.fits" >/dev/null
    milk-fpsexec-iofits-saveFITS --no-procinfo -n snapwfs exec csim_wfs_nir "!wfs_snap.fits" >/dev/null
    "{py_bin}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("wfs_snap.fits").astype(np.float32)
sig = wfs - float(np.percentile(wfs, 5.0))
fits.writeto("wfsmask.fits", (sig > 0.20 * float(sig.max())).astype(np.float32), overwrite=True)
PY
fi

milk-FITS2shm --no-procinfo -n ldcmd exec zero64.fits @S:dm01cmd >/dev/null
milk-FITS2shm --no-procinfo -n ldclk exec clk1.fits @S:step_clk >/dev/null

if [ "{1 if reuse_3drm else 0}" -eq 1 ] && [ -f peract_patch_resp3D.fits ] && [ -f mdr_pa_info.txt ]; then
    echo "[Per-Act 2/3] Reusing freshly acquired 86-actuator 8 kHz 3D RM (peract_patch_resp3D.fits)..."
else
    echo "[Per-Act 2/3] Measuring 8 kHz lockstep 3D RM on {len(pa_act_meta)} interior + free-rim actuators..."
    milk-fps-init -q mdr_pa cacao-fpsexec-cacaoac-measdynresp >/dev/null
    milk-fps-set -q \\
        mdr_pa.streamin=dm01disp \\
        mdr_pa.streamout=csim_wfs_nir \\
        mdr_pa.trigstream=csim_dm01_opd \\
        mdr_pa.inmodes=peract_patch_modes.fits \\
        mdr_pa.outcube=peract_patch_resp3D.fits \\
        mdr_pa.outmask=wfsmask.fits \\
        mdr_pa.ampl=0.25 \\
        mdr_pa.timing.WFSfrequ=1000.0 \\
        mdr_pa.timing.NBsubfr=8 \\
        mdr_pa.timing.NBrespfr=20 \\
        mdr_pa.timing.NBprefr=2 \\
        mdr_pa.timing.NBsettlefr=4 \\
        mdr_pa.pokemode=1 \\
        mdr_pa.phaseorder=1 \\
        mdr_pa.procinfo.loopcntMax=1
    milk-fps-runstart -q mdr_pa
    milk-fps-wait -q -t 300 mdr_pa
    milk-fps-info mdr_pa > mdr_pa_info.txt
    milk-fps-rm -f -q mdr_pa
fi

run_pa_cps() {{
    local name="$1"
    local outkern="$2"
    local mode="$3"
    local ntaps="$4"
    local fill="$5"
    local srad="$6"
    milk-fps-init -q "$name" cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
    milk-fps-set -q \\
        "${{name}}.resp3d=peract_patch_resp3D.fits" \\
        "${{name}}.inmodes=peract_patch_modes.fits" \\
        "${{name}}.outkernel=${{outkern}}" \\
        "${{name}}.outpred=none" \\
        "${{name}}.mode=${{mode}}" \\
        "${{name}}.stencil_rad=${{srad}}" \\
        "${{name}}.fill_uncal=${{fill}}" \\
        "${{name}}.n_taps=${{ntaps}}" \\
        "${{name}}.dt_us=125.0" \\
        "${{name}}.texp_us=1000.0" \\
        "${{name}}.tau_target_us=180.0" \\
        "${{name}}.lambda_ctrl=0.008" \\
        "${{name}}.lambda_diff=0.025" \\
        "${{name}}.max_gain=2.5" \\
        "${{name}}.deconv_exp=ON" \\
        "${{name}}.lambda_deconv=0.016" \\
        "${{name}}.energy_weight=ON" \\
        "${{name}}.procinfo.loopcntMax=1"
    milk-fps-runstart -q "$name"
    milk-fps-wait -q -t 300 "$name"
    milk-fps-info "$name" > "${{name}}_info.txt"
    milk-fps-rm -f -q "$name"
}}

echo "  Synthesizing KMODE=3 (per-actuator SISO) & KMODE=4 (per-actuator 5x5 local-stencil MIMO)..."
run_pa_cps cps_k3  ps_peract_k3.fits      3 49 OFF 2
run_pa_cps cps_k3f ps_peract_k3_fill.fits 3 49 ON  2
run_pa_cps cps_k4  ps_peract_k4.fits      4 37 OFF 2
run_pa_cps cps_k4f ps_peract_k4_fill.fits 4 37 ON  2

echo "[Per-Act 3/3] Running 12 lockstep 8 kHz replays (Interior (46,31), Near-Rim (57,31), Free-Rim Edge (61,31))..."
milk-fps-runstop -q csim_htsim
milk-fps-wait -q -t 10 csim_htsim
milk-fps-set -q \\
    csim_htsim.frame_rate=0 \\
    csim_htsim.procinfo.triggermode=3 \\
    csim_htsim.procinfo.triggersname=dm01disp
milk-fps-runstart -q csim_htsim
sleep 0.2

run_lockstep_replay() {{
    local label="$1"
    local kfile="$2"
    local enable="$3"
    local nticks="$4"
    local inbin="$5"
    local outdisp="$6"
    local outopd="$7"
    local outwfs="$8"

    milk-fps-init -q dmps_ls cacao-fpsexec-dmpreshaper >/dev/null
    milk-fps-set -q \\
        dmps_ls.streamin=dm01cmd \\
        dmps_ls.streamout=dm01disp \\
        dmps_ls.trigstream=step_clk \\
        dmps_ls.kernelfile="${{kfile}}" \\
        dmps_ls.rate_hz=8000.0 \\
        dmps_ls.enable="${{enable}}" \\
        dmps_ls.gain=1.0 \\
        dmps_ls.procinfo.loopcntMax=-1
    milk-fps-runstart -q dmps_ls
    sleep 0.05

    "{replay_bin}" "${{nticks}}" {WARMUP_TICKS} "${{inbin}}" "${{outdisp}}" "${{outopd}}" "${{outwfs}}" \\
        dm01cmd step_clk dm01disp csim_dm01_opd csim_wfs_nir

    milk-fps-runstop -q dmps_ls
    milk-fps-wait -q -t 10 dmps_ls
    milk-fps-rm -f -q dmps_ls
}}

{replay_block}

echo "PER-ACTUATOR ACQUISITION & REPLAYS COMPLETE."
"""

    try:
        res = subprocess.run(
            ["bash", "-lc", bash_script],
            env=env,
            capture_output=True,
            text=True,
            timeout=600.0,
            check=False,
        )
        print(res.stdout)
        if res.returncode != 0:
            print("STDERR:\n", res.stderr)
            raise RuntimeError(f"Per-actuator acquisition failed (rc={res.returncode})")
    finally:
        shutil.rmtree(shm_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)

    peract_meta = {
        "n_act_cal": len(pa_act_meta),
        "n_int": sum(1 for a in pa_act_meta if a["patch"] == "interior"),
        "n_rim": sum(1 for a in pa_act_meta if a["patch"] == "rim"),
        "actuators": pa_act_meta,
        "probes": {k: {mk: mv for mk, mv in v.items() if mk != "path"} for k, v in probe_specs.items()},
        "mdr_info": _parse_fps_info(raw_dir / "mdr_pa_info.txt"),
        "cps_info": {
            "k3": _parse_fps_info(raw_dir / "cps_k3_info.txt"),
            "k4": _parse_fps_info(raw_dir / "cps_k4_info.txt"),
        },
        "kernel_hdrs": {
            nm: _read_fits_hdr_metrics(
                raw_dir / fn,
                [
                    "KMODE",
                    "DT_SEC",
                    "NBIN",
                    "MBUF",
                    "STNCLRAD",
                    "STNCLNB",
                    "TAUTARUS",
                    "DELAYUS",
                    "TEXPUS",
                    "DECONV",
                    "ENRGWGT",
                    "MAXGAIN",
                    "ERRPRE",
                    "ERRPOST",
                    "OVPRE",
                    "OVPOST",
                    "OFFREDX",
                ],
            )
            for nm, fn in [
                ("peract_k3", "ps_peract_k3.fits"),
                ("peract_k4", "ps_peract_k4.fits"),
            ]
        },
    }
    (raw_dir / "peract_meta.json").write_text(json.dumps(peract_meta, indent=2), encoding="utf-8")
    cm_path = raw_dir / "calib_meta.json"
    if cm_path.is_file():
        cm = json.loads(cm_path.read_text(encoding="utf-8"))
        cm["per_actuator"] = peract_meta
        cm_path.write_text(json.dumps(cm, indent=2), encoding="utf-8")
    return peract_meta


if __name__ == "__main__":
    default_raw = REPO_ROOT / "_work" / "_dm_preshaper_demo_raw"
    run_acquisition(default_raw)
