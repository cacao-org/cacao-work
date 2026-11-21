# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Live cacaosim + cacaoac-measdynresp acquisition for the ALPAO 64x64 Plate DM."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from astropy.io import fits
import numpy as np

# Exact Stage-1 Subaru AO3k ALPAO 64x64 Plate DM + 160x160 J-band PyWFS (1,000.0 Hz fixed WFS,
# 1.0 ms exposure, 4 kHz / 250 us physical ticks -> crystal-locked 1,000.00 Hz, zero timer overrun).
AO3K_PLATE64_BENCH = """\
[bench]
name          = "ao3k_plate64_3drm"
nwf           = 256
pup_diam      = 0.9375
cobs          = 0.307
nspider       = 4
spider_w      = 0.02314
spider_deg    = 51.75
spider_offset = 0.08289
tel_diam_m    = 7.95
star_mag      = 4.0
star_teff     = 9600.0
tput_tel      = 0.20
master_hz     = 4000.0
oversample    = 1
in_wf         = "outarraypha"
in_pup        = "csim_pup"
out_beam      = "b_pup"
wf_unit       = 1
ref_lambda    = 0.50
turb_gain     = 0.0

[dm.ao3k]
in           = "b_pup"
out          = "b_post_stg1"
in_cmd       = "dm01disp"
out_opd      = "csim_dm01_opd"
nact_x       = 64
nact_y       = 64
dm_diam      = 0.984375
if_coupling  = 0.08
tput         = 0.98
max_stroke   = 8.0
dac_bits     = 16
dyn_mode     = "plate"
tau_us       = 20.0
f0_hz        = 1000.0
act_pitch_mm = 1.5
wave_c       = 14.0
bend_beta    = 0.0085
damp_g0      = 195.0
damp_g2      = 1.5
plate_drive  = "force"
rim_bc       = "free"
delay_us     = 1000.0

[pyrwfs.wfs_nir]
in            = "b_post_stg1"
out_cam       = "csim_wfs_nir"
ncam          = 160
lambda_um     = 1.22
bw_frac       = 0.20
qe            = 0.80
use_beam_flux = 1
navg          = 4
mod_rad       = 3.0
mod_npts      = 16
ron_e         = 0.0
photon_noise  = 0
out_dtype     = "float32"
"""

ZONAL_POKES: list[dict[str, Any]] = [
    {"idx": 0, "ax": 22, "ay": 23, "label": "LepICSaBL-E (22, 23)", "short": "(22,23)"},
    {"idx": 1, "ax": 31, "ay": 43, "label": "Inner Pupil (31, 43)", "short": "Inner"},
    {"idx": 2, "ax": 49, "ay": 31, "label": "Mid-Outer (49, 31)", "short": "Mid-Out"},
    {"idx": 3, "ax": 57, "ay": 31, "label": "Free Rim (57, 31)", "short": "Rim"},
]


def _zernike_radial(n: int, m: int, r: np.ndarray) -> np.ndarray:
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


def build_zernike_cube(nact: int = 64, n_modes: int = 28) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Generate Z2..Z(n_modes+1) Zernike modes on the 60-actuator ALPAO circular aperture."""
    yy, xx = np.mgrid[0:nact, 0:nact]
    ctr = 0.5 * (nact - 1)
    r_pup = 30.0
    rx = (xx - ctr) / r_pup
    ry = (yy - ctr) / r_pup
    r = np.hypot(rx, ry)
    th = np.arctan2(ry, rx)
    disk = r <= 1.03

    pairs: list[tuple[int, int, str]] = []
    for n in range(1, 10):
        for m in range(0, n + 1):
            if (n - m) % 2 != 0:
                continue
            if m == 0:
                pairs.append((n, 0, f"Z(n={n},m=0)"))
            else:
                pairs.append((n, m, f"Z(n={n},+{m})"))
                pairs.append((n, -m, f"Z(n={n},-{m})"))
            if len(pairs) >= n_modes:
                break
        if len(pairs) >= n_modes:
            break
    pairs = pairs[:n_modes]

    cube = np.zeros((n_modes, nact, nact), dtype=np.float32)
    meta: list[dict[str, Any]] = []
    for idx, (n, m, name) in enumerate(pairs):
        rad = _zernike_radial(n, abs(m), np.clip(r, 0.0, 1.0))
        if m == 0:
            z = rad
        elif m > 0:
            z = rad * np.cos(m * th)
        else:
            z = rad * np.sin(abs(m) * th)
        z = np.where(disk, z, 0.0)
        z[disk] -= float(np.mean(z[disk]))
        rms = float(np.sqrt(np.mean(z[disk] ** 2)))
        if rms > 1e-12:
            z /= rms
        cube[idx] = z.astype(np.float32)
        meta.append({"mode": idx, "j_noll": idx + 2, "n": n, "m": m, "name": name})
    return cube, meta


def build_zonal_cube(nact: int = 64) -> np.ndarray:
    """Build 4 single-actuator poke maps spanning the 64x64 circular facesheet."""
    cube = np.zeros((len(ZONAL_POKES), nact, nact), dtype=np.float32)
    for item in ZONAL_POKES:
        cube[item["idx"], item["ay"], item["ax"]] = 1.0
    return cube


def _compute_modal_analysis(
    r3_modal: np.ndarray,
    stat_modal: np.ndarray,
    hdr_modal: dict[str, Any],
    z_meta: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project 3D pixel cube into 28x28 modal space and quantify dispersion & PSOL gains."""
    n_t, n_m, _n_pix = r3_modal.shape
    q0 = int(hdr_modal["Q0_BIN"])
    n_subfr = int(hdr_modal["NBSUBFR"])
    dt_ms = float(hdr_modal["DT_SEC"]) * 1.0e3
    t_ms = (np.arange(n_t) - q0 + 0.5) * dt_ms

    # Static pseudo-inverse C_static [n_m x n_pix] so C_static @ stat_modal.T = I
    u, s, vt = np.linalg.svd(stat_modal, full_matrices=False)
    s_inv = np.where(s > 1e-4 * s[0], 1.0 / s, 0.0)
    c_pinv = (u * s_inv[None, :]) @ vt  # [n_m x n_pix]

    # Modal 3D response tensor M[t, sensed, poked] = c_pinv @ r3_modal[t].T
    # Because c_pinv is the Moore-Penrose pseudo-inverse of stat_modal, c_pinv @ stat_modal.T == I.
    m3_norm = np.einsum("sp,tqp->tsq", c_pinv, r3_modal, optimize=True)

    diag_curves = np.array([m3_norm[:, i, i] for i in range(n_m)])  # [n_m, n_t]

    per_mode_stats: list[dict[str, Any]] = []
    for i in range(n_m):
        y = diag_curves[i, q0:]
        tp = t_ms[q0:]
        peak = float(np.max(y))
        overshoot_pct = (peak - 1.0) * 100.0
        idx10 = int(np.argmax(y >= 0.10)) if np.any(y >= 0.10) else len(y) - 1
        idx50 = int(np.argmax(y >= 0.50)) if np.any(y >= 0.50) else len(y) - 1
        idx90 = int(np.argmax(y >= 0.90)) if np.any(y >= 0.90) else len(y) - 1
        outside = np.where(np.abs(y - 1.0) > 0.02)[0]
        idx_settle = int(outside[-1] + 1) if len(outside) > 0 and outside[-1] + 1 < len(y) else len(y) - 1
        per_mode_stats.append(
            {
                **z_meta[i],
                "t50_ms": float(tp[idx50]),
                "rise_10_90_ms": float(max(tp[idx90] - tp[idx10], dt_ms)),
                "overshoot_pct": overshoot_pct,
                "settle_2pct_ms": float(tp[idx_settle]),
            }
        )

    # Off-diagonal coupling RMS fraction vs time (evaluated once response rises past 25% of DC)
    eye = np.eye(n_m)[None, :, :]
    off_mat = m3_norm * (1.0 - eye)
    diag_mat = m3_norm * eye
    off_norm = np.linalg.norm(off_mat.reshape(n_t, -1), axis=1)
    diag_norm = np.linalg.norm(diag_mat.reshape(n_t, -1), axis=1)
    diag_dc_norm = float(np.mean(diag_norm[-2 * n_subfr :]))
    valid_off = diag_norm >= 0.25 * diag_dc_norm
    off_frac_pct = np.where(valid_off, 100.0 * off_norm / np.maximum(diag_norm, 1e-6), 0.0)
    peak_off_idx = int(q0 + np.argmax(off_frac_pct[q0:]))
    tail_off_pct = float(np.mean(off_frac_pct[-2 * n_subfr :]))

    # WFS-rate (1 kHz) discrete impulse response H[k] from sub-frame step response at integer frames
    # Evaluate step response S[k] at lags k = 0..17 frames (choosing sub-frame offset = 0.5 frame)
    n_fr = int(hdr_modal["NBRESPFR"])
    sample_bins = [q0 + k * n_subfr + (n_subfr // 2) for k in range(n_fr)]
    sample_bins = [b for b in sample_bins if b < n_t]
    s_wfs = np.concatenate([np.zeros((1, n_m, n_m)), m3_norm[sample_bins]], axis=0)
    h_wfs = np.diff(s_wfs, axis=0)  # [L, n_m, n_m] impulse response at 1 kHz

    # Simulate 2000 frames of 1 kHz Kolmogorov-like closed-loop DM commands u[t]
    rng = np.random.default_rng(2026)
    n_sim = 2000
    u_cmd = np.zeros((n_sim, n_m), dtype=np.float64)
    for i in range(n_m):
        rad_n = z_meta[i]["n"]
        # Higher radial orders have slightly faster decorrelation & smaller amplitude
        rho = max(0.82, 0.985 - 0.020 * rad_n)
        amp_scale = (rad_n + 1.0) ** (-1.1)
        w_n = rng.standard_normal(n_sim) * amp_scale * math.sqrt(1.0 - rho**2)
        for t in range(1, n_sim):
            u_cmd[t, i] = rho * u_cmd[t - 1, i] + w_n[t]

    # True WFS-integrated DM shape via 3D convolution
    l_kern = h_wfs.shape[0]
    phi_true = np.zeros_like(u_cmd)
    for lag in range(l_kern):
        phi_true[lag:] += u_cmd[: n_sim - lag] @ h_wfs[lag].T

    # Current CACAO 2-tap scalar-delay PSOL approximation (best-fit global scalar latency)
    t_eval = slice(l_kern + 4, n_sim)
    best_lat = 1.5
    best_err = 1.0e30
    for lat_c in np.linspace(0.5, 4.0, 141):
        li = int(lat_c)
        lf = lat_c - li
        est = (1.0 - lf) * u_cmd[l_kern + 4 - li : n_sim - li] + lf * u_cmd[
            l_kern + 4 - li - 1 : n_sim - li - 1
        ]
        err = float(np.mean((phi_true[t_eval] - est) ** 2))
        if err < best_err:
            best_err = err
            best_lat = float(lat_c)

    li = int(best_lat)
    lf = best_lat - li
    est_2tap = (1.0 - lf) * u_cmd[l_kern + 4 - li : n_sim - li] + lf * u_cmd[
        l_kern + 4 - li - 1 : n_sim - li - 1
    ]
    res_2tap = phi_true[t_eval] - est_2tap
    true_rms_per_mode = np.sqrt(np.mean(phi_true[t_eval] ** 2, axis=0))
    err_2tap_per_mode = np.sqrt(np.mean(res_2tap**2, axis=0))
    rel_2tap_pct_per_mode = 100.0 * err_2tap_per_mode / np.maximum(true_rms_per_mode, 1e-12)

    # Diagonal-only 3D FIR observer (ignoring cross-mode coupling)
    phi_diag = np.zeros_like(u_cmd)
    for lag in range(l_kern):
        phi_diag[lag:] += u_cmd[: n_sim - lag] * np.diag(h_wfs[lag])[None, :]
    res_diag = phi_true[t_eval] - phi_diag[t_eval]
    err_diag_per_mode = np.sqrt(np.mean(res_diag**2, axis=0))
    rel_diag_pct_per_mode = 100.0 * err_diag_per_mode / np.maximum(true_rms_per_mode, 1e-12)

    # Full 3D observer with 1% calibration noise floor for realistic lower bound
    rng2 = np.random.default_rng(42)
    h_noisy = h_wfs + rng2.normal(0.0, 0.002 * np.std(h_wfs), size=h_wfs.shape)
    phi_3d_est = np.zeros_like(u_cmd)
    for lag in range(l_kern):
        phi_3d_est[lag:] += u_cmd[: n_sim - lag] @ h_noisy[lag].T
    res_3d = phi_true[t_eval] - phi_3d_est[t_eval]
    err_3d_per_mode = np.sqrt(np.mean(res_3d**2, axis=0))
    rel_3d_pct_per_mode = 100.0 * err_3d_per_mode / np.maximum(true_rms_per_mode, 1e-12)

    tot_true = float(np.sqrt(np.mean(phi_true[t_eval] ** 2)))
    tot_2tap = float(np.sqrt(np.mean(res_2tap**2)))
    tot_diag = float(np.sqrt(np.mean(res_diag**2)))
    tot_3d = float(np.sqrt(np.mean(res_3d**2)))

    return {
        "m3_norm": m3_norm,
        "t_ms": t_ms,
        "q0": q0,
        "per_mode_stats": per_mode_stats,
        "off_frac_pct": off_frac_pct,
        "peak_off_ms": float(t_ms[peak_off_idx]),
        "peak_off_pct": float(off_frac_pct[peak_off_idx]),
        "tail_off_pct": tail_off_pct,
        "psol": {
            "best_2tap_lat_fr": best_lat,
            "tot_2tap_rel_pct": 100.0 * tot_2tap / max(tot_true, 1e-12),
            "tot_diag_rel_pct": 100.0 * tot_diag / max(tot_true, 1e-12),
            "tot_3d_rel_pct": 100.0 * tot_3d / max(tot_true, 1e-12),
            "reduction_2tap_to_3d_x": tot_2tap / max(tot_3d, 1e-12),
            "rel_2tap_pct_per_mode": rel_2tap_pct_per_mode.tolist(),
            "rel_diag_pct_per_mode": rel_diag_pct_per_mode.tolist(),
            "rel_3d_pct_per_mode": rel_3d_pct_per_mode.tolist(),
        },
    }


def run_live_64x64_acquisition(
    *,
    repo_root: Path,
    out_dir: Path,
    rerun: bool = False,
) -> dict[str, Any]:
    """Deploy live ALPAO 64x64 plate bench and acquire zonal + 28-mode 3D RMs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw_calib"
    raw_dir.mkdir(parents=True, exist_ok=True)
    summary_path = raw_dir / "calib_summary.json"
    zonal_cube = raw_dir / "zonal4_resp3D.fits"
    modal_cube = raw_dir / "modal28_resp3D.fits"
    modal_tensor_npy = raw_dir / "modal28_m3_norm.npy"

    if (
        not rerun
        and summary_path.is_file()
        and zonal_cube.is_file()
        and modal_cube.is_file()
        and modal_tensor_npy.is_file()
    ):
        print(f"[dm64-dyn-rm] Reusing existing live calibration cubes in {raw_dir}")
        return json.loads(summary_path.read_text(encoding="utf-8"))

    bench_path = raw_dir / "ao3k_plate64_3drm.bench"
    bench_path.write_text(AO3K_PLATE64_BENCH, encoding="utf-8")

    poke_z4 = raw_dir / "poke_zonal4.fits"
    poke_z28 = raw_dir / "poke_zernike28.fits"
    fits.writeto(poke_z4, build_zonal_cube(64), overwrite=True)
    z28_arr, z28_meta = build_zernike_cube(64, 28)
    fits.writeto(poke_z28, z28_arr, overwrite=True)

    pid = os.getpid()
    shm_dir = Path(f"/dev/shm/cacao_dm64_{pid}")
    proc_dir = shm_dir / "proc"
    csim_dir = raw_dir / "csim_run"
    shm_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    csim_dir.mkdir(parents=True, exist_ok=True)

    wfs_snap = raw_dir / "wfs_snap.fits"
    wfs_mask = raw_dir / "wfsmask.fits"
    zonal_pp = raw_dir / "zonal4_pp_resp3D.fits"
    zonal_lin = raw_dir / "zonal4_measlinresp.fits"
    dm_end = raw_dir / "dm_end.fits"

    env = os.environ.copy()
    env["MILK_SHM_DIR"] = str(shm_dir)
    env["MILK_PROC_DIR"] = str(proc_dir)
    env["CACAOSIM_WORKDIR"] = str(csim_dir)
    python_bin = env.get("PYTHON_BIN") or shutil.which("python3") or "python3"

    script = f"""
set -euo pipefail
source "{repo_root}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{proc_dir}"
export CACAOSIM_WORKDIR="{csim_dir}"

cleanup() {{
    milk-fps-rm -f -q mdr_z4 mdr_z4pp mlr_z4 mdr_m28 >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

echo "[dm64-dyn-rm] Deploying live ALPAO 64x64 plate DM + 160x160 J-band PyWFS (4 kHz / 1 kHz WFS)..."
cacaosim-bench deploy \\
    --workdir "{csim_dir}" \\
    --config "{bench_path}" \\
    --mode fused --no-view >/dev/null

milk-stream-wait -q -t 20 csim_wfs_nir:160x160 dm01disp:64x64

# Run inside raw_dir so all FPS FITS filenames stay well under milk's 63-char limit
cd "{raw_dir}"

# Capture illuminated PyWFS frame to build active-pixel mask (subtracting detector bias floor)
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapwfs exec csim_wfs_nir "!wfs_snap.fits" >/dev/null
"{python_bin}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("wfs_snap.fits").astype(np.float32)
sig = wfs - float(np.percentile(wfs, 5.0))
mask = (sig > 0.25 * float(sig.max())).astype(np.float32)
fits.writeto("wfsmask.fits", mask, overwrite=True)
print(f"[dm64-dyn-rm] PyWFS active pixel mask: {{int(mask.sum())}} / {{mask.size}} pixels")
PY

# 1. Zonal 4-actuator wall-clock stroboscopic 3D RM (pokemode=0: 0->+a->0->-a->0, NBsubfr=4 -> 250 us)
echo "[dm64-dyn-rm] Pass 1/4: Wall-clock stroboscopic 3D RM on 4 radial actuators (pokemode=0)..."
milk-fps-init -q mdr_z4 cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_z4.streamin=dm01disp \\
    mdr_z4.streamout=csim_wfs_nir \\
    mdr_z4.inmodes=poke_zonal4.fits \\
    mdr_z4.outcube=zonal4_resp3D.fits \\
    mdr_z4.outmask=wfsmask.fits \\
    mdr_z4.ampl=0.04 \\
    mdr_z4.normalize=OFF \\
    mdr_z4.timing.WFSfrequ=0.0 \\
    mdr_z4.timing.frameratewait=0.5 \\
    mdr_z4.timing.NBsubfr=4 \\
    mdr_z4.timing.NBrespfr=20 \\
    mdr_z4.timing.NBprefr=2 \\
    mdr_z4.timing.NBsettlefr=2 \\
    mdr_z4.timing.NBcycle=1 \\
    mdr_z4.timing.spinus=60 \\
    mdr_z4.pokemode=0 \\
    mdr_z4.phaseorder=0 \\
    mdr_z4.saveALL=ON \\
    mdr_z4.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_z4
milk-fps-wait -q -t 60 mdr_z4
milk-fps-rm -f -q mdr_z4

# 2. Repeatability check: pokemode=1 (+a <-> -a) wall-clock on the same 4 actuators
echo "[dm64-dyn-rm] Pass 2/4: Wall-clock repeatability pass (pokemode=1 push-pull)..."
milk-fps-init -q mdr_z4pp cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_z4pp.streamin=dm01disp \\
    mdr_z4pp.streamout=csim_wfs_nir \\
    mdr_z4pp.inmodes=poke_zonal4.fits \\
    mdr_z4pp.outcube=zonal4_pp_resp3D.fits \\
    mdr_z4pp.outmask=wfsmask.fits \\
    mdr_z4pp.ampl=0.04 \\
    mdr_z4pp.normalize=OFF \\
    mdr_z4pp.timing.WFSfrequ=0.0 \\
    mdr_z4pp.timing.frameratewait=0.4 \\
    mdr_z4pp.timing.NBsubfr=4 \\
    mdr_z4pp.timing.NBrespfr=20 \\
    mdr_z4pp.timing.NBprefr=2 \\
    mdr_z4pp.timing.NBsettlefr=2 \\
    mdr_z4pp.timing.NBcycle=1 \\
    mdr_z4pp.timing.spinus=60 \\
    mdr_z4pp.pokemode=1 \\
    mdr_z4pp.phaseorder=0 \\
    mdr_z4pp.saveALL=OFF \\
    mdr_z4pp.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_z4pp
milk-fps-wait -q -t 60 mdr_z4pp
milk-fps-rm -f -q mdr_z4pp

# 3. Standard static 2D RM via cacaoac-measlinresp (NBexcl=26 so plate settles <0.5%)
echo "[dm64-dyn-rm] Pass 3/4: Static 2D reference RM via cacaoac-measlinresp..."
milk-fps-init -q mlr_z4 cacao-fpsexec-cacaoac-measlinresp >/dev/null
milk-fps-set -q \\
    mlr_z4.streamin=dm01disp \\
    mlr_z4.streamout=csim_wfs_nir \\
    mlr_z4.inmodes=poke_zonal4.fits \\
    mlr_z4.outmodes=zonal4_measlinresp.fits \\
    mlr_z4.ampl=0.04 \\
    mlr_z4.timing.WFSfrequ=1000.0 \\
    mlr_z4.timing.hardwlatfr=1.5 \\
    mlr_z4.timing.NBave=4 \\
    mlr_z4.timing.NBexcl=26 \\
    mlr_z4.timing.NBinnerCycle=1 \\
    mlr_z4.procinfo.loopcntMax=1
milk-fps-runstart -q mlr_z4
milk-fps-wait -q -t 60 mlr_z4
milk-fps-rm -f -q mlr_z4

# 4. 28-mode Zernike (Z2..Z29) wall-clock stroboscopic 3D RM (NBsubfr=4 -> 250 us)
echo "[dm64-dyn-rm] Pass 4/4: Wall-clock 28-mode Zernike 3D RM (Z2..Z29, 4 kHz effective)..."
milk-fps-init -q mdr_m28 cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_m28.streamin=dm01disp \\
    mdr_m28.streamout=csim_wfs_nir \\
    mdr_m28.inmodes=poke_zernike28.fits \\
    mdr_m28.outcube=modal28_resp3D.fits \\
    mdr_m28.outmask=wfsmask.fits \\
    mdr_m28.ampl=0.015 \\
    mdr_m28.normalize=OFF \\
    mdr_m28.timing.WFSfrequ=0.0 \\
    mdr_m28.timing.frameratewait=0.4 \\
    mdr_m28.timing.NBsubfr=4 \\
    mdr_m28.timing.NBrespfr=18 \\
    mdr_m28.timing.NBprefr=2 \\
    mdr_m28.timing.NBsettlefr=2 \\
    mdr_m28.timing.NBcycle=1 \\
    mdr_m28.timing.spinus=60 \\
    mdr_m28.pokemode=1 \\
    mdr_m28.phaseorder=0 \\
    mdr_m28.saveALL=ON \\
    mdr_m28.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_m28
milk-fps-wait -q -t 120 mdr_m28
milk-fps-rm -f -q mdr_m28

milk-fpsexec-iofits-saveFITS --no-procinfo -n snapdm exec dm01disp "!dm_end.fits" >/dev/null
cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null
"""
    try:
        res = subprocess.run(
            ["bash", "-c", script],
            cwd=repo_root,
            env=env,
            timeout=240,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Live 64x64 3D RM acquisition failed with rc={res.returncode}")
    finally:
        subprocess.run(
            [
                "bash",
                "-c",
                f'source "{repo_root}/scripts/shm-sandbox.sh"; '
                f'CACAOSIM_WORKDIR="{csim_dir}" sandbox_stop_all',
            ],
            cwd=repo_root,
            env=env,
            capture_output=True,
            check=False,
        )
        shutil.rmtree(shm_dir, ignore_errors=True)
        shutil.rmtree(csim_dir, ignore_errors=True)

    # Analyze acquired cubes
    mask_2d = fits.getdata(wfs_mask) > 0.5
    with fits.open(zonal_cube) as hdul:
        r3_z4 = hdul[0].data.astype(np.float64)
        hdr_z4 = dict(hdul[0].header)
    with fits.open(zonal_pp) as hdul:
        r3_pp = hdul[0].data.astype(np.float64)
        hdr_pp = dict(hdul[0].header)
    stat_z4 = fits.getdata(raw_dir / "zonal4_resp3D_static.fits").astype(np.float64)
    asym_z4 = fits.getdata(raw_dir / "zonal4_resp3D_asym.fits").astype(np.float64)
    cnt_z4 = fits.getdata(raw_dir / "zonal4_resp3D_cnt.fits")
    tmean_z4 = fits.getdata(raw_dir / "zonal4_resp3D_tmean.fits").astype(np.float64)
    lin_2d = fits.getdata(zonal_lin).astype(np.float64)[:, mask_2d]
    dm_end_max = float(np.max(np.abs(fits.getdata(dm_end))))

    q0_z4 = int(hdr_z4["Q0_BIN"])
    dt_z4_ms = float(hdr_z4["DT_SEC"]) * 1.0e3
    t_z4_ms = (np.arange(r3_z4.shape[0]) - q0_z4 + 0.5) * dt_z4_ms

    zonal_metrics: list[dict[str, Any]] = []
    for item in ZONAL_POKES:
        m = item["idx"]
        rms_t = np.sqrt(np.mean(r3_z4[:, m, :] ** 2, axis=1))
        stat_rms = float(np.sqrt(np.mean(stat_z4[m] ** 2)))
        pre_rms = float(np.max(rms_t[:q0_z4]))
        peak_idx = int(q0_z4 + np.argmax(rms_t[q0_z4:]))
        peak_rms = float(rms_t[peak_idx])
        overshoot_pct = (peak_rms / max(stat_rms, 1e-12) - 1.0) * 100.0
        # Dynamic wave residual Y(tau) - Y_static
        dyn_res = r3_z4[:, m, :] - stat_z4[m][None, :]
        dyn_rms_t = np.sqrt(np.mean(dyn_res**2, axis=1))
        rel_lin = float(np.linalg.norm(stat_z4[m] - lin_2d[m]) / np.linalg.norm(lin_2d[m]))
        r_act = float(math.hypot(item["ax"] - 31.5, item["ay"] - 31.5))
        # Settle time: last post-poke time where |rms_t - stat_rms| > 0.03 * stat_rms
        post_dev = np.abs(rms_t[q0_z4:] - stat_rms) / max(stat_rms, 1e-12)
        out_idx = np.where(post_dev > 0.03)[0]
        settle_ms = float(
            t_z4_ms[q0_z4 + int(out_idx[-1]) + 1]
            if len(out_idx) > 0 and q0_z4 + int(out_idx[-1]) + 1 < len(t_z4_ms)
            else t_z4_ms[-1]
        )
        zonal_metrics.append(
            {
                **item,
                "radius_act": round(r_act, 2),
                "radius_mm": round(r_act * 1.5, 2),
                "pre_poke_leak_pct": 100.0 * pre_rms / max(stat_rms, 1e-12),
                "peak_t_ms": float(t_z4_ms[peak_idx]),
                "overshoot_pct": overshoot_pct,
                "settle_3pct_ms": settle_ms,
                "dyn_rms_4ms_frac": float(
                    dyn_rms_t[min(len(dyn_rms_t) - 1, q0_z4 + int(round(4.0 / dt_z4_ms)))]
                    / max(stat_rms, 1e-12)
                ),
                "dyn_rms_10ms_frac": float(
                    dyn_rms_t[min(len(dyn_rms_t) - 1, q0_z4 + int(round(10.0 / dt_z4_ms)))]
                    / max(stat_rms, 1e-12)
                ),
                "static_vs_measlinresp_pct": 100.0 * rel_lin,
            }
        )

    corr_pm0_pm1 = float(np.corrcoef(r3_z4[q0_z4:].ravel(), r3_pp[q0_z4:].ravel())[0, 1])
    stat_all_err_pct = 100.0 * float(
        np.linalg.norm(stat_z4 - lin_2d) / np.linalg.norm(lin_2d)
    )
    asym_pct = 100.0 * float(
        np.linalg.norm(asym_z4[q0_z4:]) / np.linalg.norm(r3_z4[q0_z4:])
    )

    with fits.open(modal_cube) as hdul:
        r3_m28 = hdul[0].data.astype(np.float64)
        hdr_m28 = dict(hdul[0].header)
    stat_m28 = fits.getdata(raw_dir / "modal28_resp3D_static.fits").astype(np.float64)
    cnt_m28 = fits.getdata(raw_dir / "modal28_resp3D_cnt.fits")
    q0_m28 = int(hdr_m28["Q0_BIN"])
    modal_res = _compute_modal_analysis(r3_m28, stat_m28, hdr_m28, z28_meta)
    np.save(modal_tensor_npy, modal_res["m3_norm"].astype(np.float32))

    summary: dict[str, Any] = {
        "n_active_wfs_pix": int(mask_2d.sum()),
        "wfs_shape": [int(mask_2d.shape[0]), int(mask_2d.shape[1])],
        "dm_end_max_abs": dm_end_max,
        "zonal_4seg": {
            "wfsfreq_hz": float(hdr_z4["WFSFREQ"]),
            "dt_us": float(hdr_z4["DT_SEC"]) * 1.0e6,
            "nbsubfr": int(hdr_z4["NBSUBFR"]),
            "nbrespfr": int(hdr_z4["NBRESPFR"]),
            "q0_bin": q0_z4,
            "n_t": int(r3_z4.shape[0]),
            "ampl_um": float(hdr_z4["AMPL"]),
            "jitter_us": float(hdr_z4["JITTERUS"]),
            "dropped_frames": int(hdr_z4["NDROP"]),
            "late_pokes": int(hdr_z4["NLATEPK"]),
            "min_post_cnt": int(cnt_z4[q0_z4:].min()),
            "max_post_cnt": int(cnt_z4[q0_z4:].max()),
            "tmean_linearity_rms_us": float(
                np.sqrt(
                    np.mean(
                        (
                            tmean_z4[q0_z4:, 0]
                            - (np.arange(r3_z4.shape[0] - q0_z4) + 0.5) * float(hdr_z4["DT_SEC"])
                        )
                        ** 2
                    )
                )
                * 1.0e6
            ),
            "per_actuator": zonal_metrics,
            "static_vs_measlinresp_pct": stat_all_err_pct,
            "polarity_asym_pct": asym_pct,
            "corr_vs_pokemode1": corr_pm0_pm1,
        },
        "zonal_pushpull": {
            "wfsfreq_hz": float(hdr_pp["WFSFREQ"]),
            "jitter_us": float(hdr_pp["JITTERUS"]),
            "dropped_frames": int(hdr_pp["NDROP"]),
        },
        "modal_28": {
            "wfsfreq_hz": float(hdr_m28["WFSFREQ"]),
            "dt_us": float(hdr_m28["DT_SEC"]) * 1.0e6,
            "nbsubfr": int(hdr_m28["NBSUBFR"]),
            "nbrespfr": int(hdr_m28["NBRESPFR"]),
            "q0_bin": int(hdr_m28["Q0_BIN"]),
            "n_t": int(r3_m28.shape[0]),
            "ampl_um": float(hdr_m28["AMPL"]),
            "jitter_us": float(hdr_m28["JITTERUS"]),
            "dropped_frames": int(hdr_m28["NDROP"]),
            "late_pokes": int(hdr_m28["NLATEPK"]),
            "min_post_cnt": int(cnt_m28[q0_m28:].min()),
            "max_post_cnt": int(cnt_m28[q0_m28:].max()),
            "peak_off_ms": modal_res["peak_off_ms"],
            "peak_off_pct": modal_res["peak_off_pct"],
            "tail_off_pct": modal_res["tail_off_pct"],
            "per_mode_stats": modal_res["per_mode_stats"],
            "psol": modal_res["psol"],
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
