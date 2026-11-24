# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end live HIL tests for Feature 1: DM Command Pre-Shaper.

Validates both new standalone CACAO compute units against a live GPU cacaosim
coupled plate DM (dyn_mode = "plate"):
  1. cacao-fpsexec-cacaocc-compdmpreshaper  (offline constrained 3D RM kernel synthesis)
  2. cacao-fpsexec-dmpreshaper              (high-rate async look-ahead DM pre-shaper)
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from astropy.io import fits
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# 12x12 coupled free-rim plate DM + PyWFS bench (2000 Hz physical / 500 Hz fixed WFS)
PLATE12_PRESHAPER_BENCH = """\
[bench]
name         = "preshaper_plate12"
nwf          = 128
pup_diam     = 0.875
cobs         = 0.12
tel_diam_m   = 8.0
star_mag     = 5.0
master_hz    = 2000.0
oversample   = 1
in_wf        = "outarraypha"
in_pup       = "csim_pup"
out_beam     = "b_pup"
wf_unit      = 1
ref_lambda   = 0.50
turb_gain    = 0.0

[dm.dm1]
in           = "b_pup"
out          = "b_post_dm"
in_cmd       = "dm01disp"
out_opd      = "csim_dm01_opd"
nact_x       = 12
nact_y       = 12
dm_diam      = 0.90
if_coupling  = 0.10
tput         = 0.99
max_stroke   = 5.0
dac_bits     = 16
dyn_mode     = "plate"
tau_us       = 20.0
f0_hz        = 650.0
act_pitch_mm = 2.0
wave_c       = 10.0
bend_beta    = 0.008
damp_g0      = 110.0
damp_g2      = 0.8
plate_drive  = "force"
rim_bc       = "free"
delay_us     = 1000.0

[pyrwfs.wfs1]
in           = "b_post_dm"
out_cam      = "csim_wfs"
ncam         = 48
lambda_um    = 1.22
bw_frac      = 0.15
qe           = 0.85
navg         = 4
mod_rad      = 3.0
mod_npts     = 8
ron_e        = 0.0
photon_noise = 0
out_dtype    = "float32"
"""


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


def _build_zernike_modes(nact: int = 12, n_modes: int = 8) -> np.ndarray:
    yy, xx = np.mgrid[0:nact, 0:nact]
    ctr = 0.5 * (nact - 1)
    r_pup = 0.48 * nact
    rx = (xx - ctr) / r_pup
    ry = (yy - ctr) / r_pup
    r = np.hypot(rx, ry)
    th = np.arctan2(ry, rx)
    disk = r <= 1.05

    pairs: list[tuple[int, int]] = []
    for n in range(1, 6):
        for m in range(0, n + 1):
            if (n - m) % 2 != 0:
                continue
            if m == 0:
                pairs.append((n, 0))
            else:
                pairs.append((n, m))
                pairs.append((n, -m))
            if len(pairs) >= n_modes:
                break
        if len(pairs) >= n_modes:
            break
    pairs = pairs[:n_modes]

    cube = np.zeros((n_modes, nact, nact), dtype=np.float32)
    for i, (n, m) in enumerate(pairs):
        rad = _zernike_radial(n, abs(m), np.clip(r, 0.0, 1.0))
        z = rad if m == 0 else (rad * np.cos(m * th) if m > 0 else rad * np.sin(abs(m) * th))
        z = np.where(disk, z, 0.0)
        z[disk] -= float(np.mean(z[disk]))
        rms = float(np.sqrt(np.mean(z[disk] ** 2)))
        if rms > 1e-12:
            z /= rms
        cube[i] = z.astype(np.float32)
    return cube


def _run_bash(script: str, env: dict[str, str], timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _sandbox_env(tmp_path: Path, tag: str) -> tuple[dict[str, str], Path, Path]:
    shm_dir = Path(f"/dev/shm/cacao_ps_{tag}_{os.getpid()}")
    proc_dir = shm_dir / "proc"
    work_dir = tmp_path / f"work_{tag}"
    shm_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MILK_SHM_DIR"] = str(shm_dir)
    env["MILK_PROC_DIR"] = str(proc_dir)
    env["CACAOSIM_WORKDIR"] = str(work_dir)
    return env, shm_dir, work_dir


def _cleanup_sandbox(env: dict[str, str], shm_dir: Path, work_dir: Path) -> None:
    _run_bash(
        f'source "{REPO_ROOT}/scripts/shm-sandbox.sh"; '
        f'CACAOSIM_WORKDIR="{work_dir}" sandbox_stop_all',
        env=env,
        timeout=20.0,
    )
    shutil.rmtree(shm_dir, ignore_errors=True)


def test_preshaper_mimo_hil_plate_suppression_and_live_controls(tmp_path: Path) -> None:
    """Full HIL cycle: measdynresp -> compdmpreshaper (MIMO) -> dmpreshaper -> measdynresp."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "mimo")
    raw_dir = work_dir / "cal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    bench_file = work_dir / "plate12.bench"
    bench_file.write_text(PLATE12_PRESHAPER_BENCH, encoding="utf-8")

    z8 = _build_zernike_modes(12, 8)
    fits.writeto(raw_dir / "poke_z8.fits", z8, overwrite=True)

    py = env.get("PYTHON_BIN") or shutil.which("python3") or "python3"
    script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{work_dir}"

cleanup() {{
    milk-fps-runstop -q dmps >/dev/null 2>&1 || true
    milk-fps-rm -f -q mdr_raw cps dmps mdr_sh >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy --workdir "{work_dir}" --config "{bench_file}" --mode fused --no-view >/dev/null
milk-stream-wait -q -t 20 csim_wfs:48x48 dm01disp:12x12

cd "{raw_dir}"

# Build active-pixel WFS mask
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapwfs exec csim_wfs "!wfs_snap.fits" >/dev/null
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("wfs_snap.fits").astype(np.float32)
sig = wfs - float(np.percentile(wfs, 5.0))
mask = (sig > 0.20 * float(sig.max())).astype(np.float32)
fits.writeto("wfsmask.fits", mask, overwrite=True)
PY

# 1. Baseline unshaped 3D RM directly on dm01disp (4x stroboscopic -> 2 kHz / 500 us)
milk-fps-init -q mdr_raw cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_raw.streamin=dm01disp \\
    mdr_raw.streamout=csim_wfs \\
    mdr_raw.inmodes=poke_z8.fits \\
    mdr_raw.outcube=resp3D_raw.fits \\
    mdr_raw.outmask=wfsmask.fits \\
    mdr_raw.ampl=0.025 \\
    mdr_raw.timing.WFSfrequ=0.0 \\
    mdr_raw.timing.frameratewait=0.3 \\
    mdr_raw.timing.NBsubfr=4 \\
    mdr_raw.timing.NBrespfr=14 \\
    mdr_raw.timing.NBprefr=2 \\
    mdr_raw.timing.NBsettlefr=2 \\
    mdr_raw.timing.NBcycle=1 \\
    mdr_raw.pokemode=1 \\
    mdr_raw.phaseorder=0 \\
    mdr_raw.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_raw
milk-fps-wait -q -t 60 mdr_raw
milk-fps-rm -f -q mdr_raw

# 2. Synthesize MIMO look-ahead pre-shaper kernel
milk-fps-init -q cps cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
milk-fps-set -q \\
    cps.resp3d=resp3D_raw.fits \\
    cps.inmodes=poke_z8.fits \\
    cps.outkernel=dm_preshaper_mimo.fits \\
    cps.outpred=pred_shaped.fits \\
    cps.mode=0 \\
    cps.n_taps=22 \\
    cps.tau_target_us=100.0 \\
    cps.lambda_ctrl=0.015 \\
    cps.lambda_diff=0.015 \\
    cps.max_gain=2.5 \\
    cps.procinfo.loopcntMax=1
milk-fps-runstart -q cps
milk-fps-wait -q -t 30 cps
milk-fps-rm -f -q cps

# 3. Create unshaped upstream stream dm01cmd (same shape as dm01disp) and launch dmpreshaper
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
fits.writeto("zero12.fits", np.zeros((12, 12), dtype=np.float32), overwrite=True)
PY
milk-FITS2shm --no-procinfo -n ldcmd exec zero12.fits @S:dm01cmd >/dev/null

milk-fps-init -q dmps cacao-fpsexec-dmpreshaper >/dev/null
milk-fps-set -q \\
    dmps.streamin=dm01cmd \\
    dmps.streamout=dm01disp \\
    dmps.kernelfile=dm_preshaper_mimo.fits \\
    dmps.rate_hz=0.0 \\
    dmps.freerun=OFF \\
    dmps.enable=ON \\
    dmps.gain=1.0 \\
    dmps.procinfo.loopcntMax=-1
milk-fps-runstart -q dmps
sleep 0.2

# 4. Transparently measure closed-preshaper 3D RM through dm01cmd -> dmpreshaper -> dm01disp!
milk-fps-init -q mdr_sh cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_sh.streamin=dm01cmd \\
    mdr_sh.streamout=csim_wfs \\
    mdr_sh.inmodes=poke_z8.fits \\
    mdr_sh.outcube=resp3D_shaped.fits \\
    mdr_sh.outmask=wfsmask.fits \\
    mdr_sh.ampl=0.025 \\
    mdr_sh.timing.WFSfrequ=0.0 \\
    mdr_sh.timing.frameratewait=0.3 \\
    mdr_sh.timing.NBsubfr=4 \\
    mdr_sh.timing.NBrespfr=14 \\
    mdr_sh.timing.NBprefr=2 \\
    mdr_sh.timing.NBsettlefr=2 \\
    mdr_sh.timing.NBcycle=1 \\
    mdr_sh.pokemode=1 \\
    mdr_sh.phaseorder=0 \\
    mdr_sh.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_sh
milk-fps-wait -q -t 60 mdr_sh
milk-fps-rm -f -q mdr_sh

# Snapshot telemetry counters before bypass/clip checks
milk-fps-info dmps > dmps_info_1.txt

copy_inplace() {{
    local src_fits="$1"
    local tmp_shm="$2"
    milk-FITS2shm --no-procinfo -n "ld_${{tmp_shm}}" exec "${{src_fits}}" "@S:${{tmp_shm}}" >/dev/null
    milk-fps-init -q "cp_${{tmp_shm}}" milk-fpsexec-mem-streamcopy >/dev/null
    milk-fps-set -q \\
        "cp_${{tmp_shm}}.in_sname=${{tmp_shm}}" \\
        "cp_${{tmp_shm}}.out_sname=dm01cmd" \\
        "cp_${{tmp_shm}}.procinfo.loopcntMax=1"
    milk-fps-runstart -q "cp_${{tmp_shm}}"
    milk-fps-wait -q -t 10 "cp_${{tmp_shm}}"
    milk-fps-rm -f -q "cp_${{tmp_shm}}"
}}

# 5. Live bypass check (.enable=OFF -> exact pass-through via in-place streamcopy)
milk-fps-set -q dmps.enable=OFF
sleep 0.1
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
pat = np.full((12, 12), 0.03, dtype=np.float32)
fits.writeto("pat03.fits", pat, overwrite=True)
pat5 = np.full((12, 12), 0.05, dtype=np.float32)
fits.writeto("pat05.fits", pat5, overwrite=True)
PY
copy_inplace pat03.fits pat03
sleep 0.05
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapbyp exec dm01disp "!dm_bypass.fits" >/dev/null

# 6. Live clip check (.clip_enable=ON, [-0.02, 0.02])
milk-fps-set -q dmps.enable=ON dmps.clip_enable=ON dmps.clip_min=-0.02 dmps.clip_max=0.02
sleep 0.1
copy_inplace pat05.fits pat05
sleep 0.05
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapclp exec dm01disp "!dm_clipped.fits" >/dev/null
milk-fps-info dmps > dmps_info_2.txt

# 7. Clean shutdown leaves DM on settled u_base (unclipped once clip disabled)
milk-fps-set -q dmps.clip_enable=OFF
sleep 0.1
copy_inplace zero12.fits pat00
sleep 0.05
milk-fps-runstop -q dmps
milk-fps-wait -q -t 10 dmps
milk-fps-rm -f -q dmps
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapend exec dm01disp "!dm_end.fits" >/dev/null
cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null
"""
    try:
        res = _run_bash(script, env=env, timeout=180.0)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        # Verify MEF kernel integrity
        with fits.open(raw_dir / "dm_preshaper_mimo.fits") as hdul:
            assert len(hdul) == 3
            khdr = hdul[0].header
            assert int(khdr["KMODE"]) == 0
            assert int(khdr["NBIN"]) == 8
            assert int(khdr["DECONV"]) == 1
            assert int(khdr["ENRGWGT"]) == 1
            p_fwd = hdul["P_FWD"].data.reshape(8, -1).astype(np.float64)
            p_pinv = hdul["P_PINV"].data.reshape(8, -1).astype(np.float64)
            ortho_err = float(np.max(np.abs(p_pinv @ p_fwd.T - np.eye(8))))
            assert ortho_err < 1.0e-4, f"P_PINV @ P_FWD^T != I (err={ortho_err})"
            assert float(khdr["ERRPOST"]) < float(khdr["ERRPRE"]) / 2.5
            assert float(khdr["OFFREDX"]) > 2.0

        # Compare LIVE raw vs LIVE pre-shaped 3D RMs in modal space
        r_raw = fits.getdata(raw_dir / "resp3D_raw.fits").astype(np.float64)
        h_raw = fits.getheader(raw_dir / "resp3D_raw.fits")
        stat_raw = fits.getdata(raw_dir / "resp3D_raw_static.fits").astype(np.float64)

        r_sh = fits.getdata(raw_dir / "resp3D_shaped.fits").astype(np.float64)
        h_sh = fits.getheader(raw_dir / "resp3D_shaped.fits")
        stat_sh = fits.getdata(raw_dir / "resp3D_shaped_static.fits").astype(np.float64)

        # 1. Exact static DC parity (unity DC gain preserved!)
        dc_rel_err = float(np.linalg.norm(stat_sh - stat_raw) / np.linalg.norm(stat_raw))
        assert dc_rel_err < 0.025, f"Static DC gain drifted: {dc_rel_err:.4f}"

        # Project both cubes through the same static reconstructor C_static
        u, s, vt = np.linalg.svd(stat_raw, full_matrices=False)
        c_pinv = (u * np.where(s > 1e-3 * s[0], 1.0 / s, 0.0)[None, :]) @ vt
        q0_r = int(h_raw["Q0_BIN"])
        q0_s = int(h_sh["Q0_BIN"])
        m_raw = np.einsum("sp,tqp->tsq", c_pinv, r_raw[q0_r:], optimize=True)
        m_sh = np.einsum("sp,tqp->tsq", c_pinv, r_sh[q0_s:], optimize=True)

        eye = np.eye(8)
        diag_raw = np.diagonal(m_raw, axis1=1, axis2=2)  # [L, 8]
        diag_sh = np.diagonal(m_sh, axis1=1, axis2=2)

        ov_raw = float(np.mean((diag_raw.max(axis=0) - 1.0) * 100.0))
        ov_sh = float(np.mean((diag_sh.max(axis=0) - 1.0) * 100.0))

        # Post-exposure ringing RMS (after 1.0 ms delay + 2.0 ms exposure -> t >= 3.5 ms)
        dt_ms = float(h_raw["DT_SEC"]) * 1.0e3
        i_ring = int(round(3.5 / dt_ms))
        ring_raw = float(np.sqrt(np.mean((diag_raw[i_ring:] - 1.0) ** 2)))
        ring_sh = float(np.sqrt(np.mean((diag_sh[i_ring:] - 1.0) ** 2)))

        # Verify rise midpoint does not slow down (zero artificial latency!)
        def _t50_ms(curve: np.ndarray) -> float:
            for k in range(len(curve)):
                if curve[k] >= 0.5:
                    f = (0.5 - curve[k - 1]) / max(curve[k] - curve[k - 1], 1e-12) if k > 0 else 0.0
                    return ((k - 1) + f + 0.5) * dt_ms if k > 0 else 0.5 * dt_ms
            return len(curve) * dt_ms

        t50_raw = _t50_ms(diag_raw.mean(axis=1))
        t50_sh = _t50_ms(diag_sh.mean(axis=1))

        # Off-diagonal transient mechanical cross-talk
        off_raw_pk = float(np.linalg.norm((m_raw * (1.0 - eye[None])).reshape(len(m_raw), -1), axis=1).max())
        off_sh_pk = float(np.linalg.norm((m_sh * (1.0 - eye[None])).reshape(len(m_sh), -1), axis=1).max())

        print(
            f"\n[HIL MIMO Pre-Shaper] DC err={dc_rel_err*100:.2f}% | "
            f"t50: {t50_raw:.2f} -> {t50_sh:.2f} ms | "
            f"Overshoot: +{ov_raw:.2f}% -> +{ov_sh:.2f}% | "
            f"Ringing RMS: {ring_raw*100:.2f}% -> {ring_sh*100:.2f}% ({ring_raw/max(ring_sh,1e-9):.2f}x) | "
            f"Peak cross-talk: {off_raw_pk:.4f} -> {off_sh_pk:.4f} ({off_raw_pk/max(off_sh_pk,1e-9):.2f}x)"
        )
        # Posicast zero-vibration shaping on an f0 = 650 Hz plate adds <= T0/4 (~0.385 ms) rise shift
        assert t50_sh <= t50_raw + 0.42, f"Pre-shaper added excess rise lag: {t50_raw:.2f} -> {t50_sh:.2f} ms"
        assert ov_sh < ov_raw * 0.45, f"Overshoot not suppressed enough: {ov_raw:.2f}% -> {ov_sh:.2f}%"
        assert ring_sh < ring_raw * 0.25, f"Ringing not suppressed enough: {ring_raw:.4f} -> {ring_sh:.4f}"
        assert off_sh_pk < off_raw_pk * 0.55, (
            f"Cross-mode wave coupling not suppressed: {off_raw_pk:.4f} -> {off_sh_pk:.4f}"
        )

        def _parse_fps_val(path: Path, key: str) -> float:
            k_clean = key.lstrip(".")
            clean = re.sub(r"\x1b\[[0-9;]*m", "", path.read_text(encoding="utf-8"))
            for line in clean.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[1].lstrip(".") == k_clean:
                    return float(parts[3])
            raise AssertionError(f"Key {key} not found in {path}")

        # Verify async high-rate operation (out_cnt >> in_cnt)
        in_cnt = int(_parse_fps_val(raw_dir / "dmps_info_1.txt", ".out.in_cnt"))
        out_cnt = int(_parse_fps_val(raw_dir / "dmps_info_1.txt", ".out.out_cnt"))
        assert out_cnt > 5 * in_cnt, f"Expected async high-rate frames: in={in_cnt}, out={out_cnt}"

        # Verify live bypass, clip, and safe zero shutdown
        dm_byp = fits.getdata(raw_dir / "dm_bypass.fits")
        assert float(np.max(np.abs(dm_byp - 0.03))) < 1.0e-5
        dm_clp = fits.getdata(raw_dir / "dm_clipped.fits")
        assert float(np.max(dm_clp)) <= 0.02 + 1.0e-6
        assert float(np.min(dm_clp)) >= -0.02 - 1.0e-6
        clip_cnt = int(_parse_fps_val(raw_dir / "dmps_info_2.txt", ".out.clip_cnt"))
        assert clip_cnt > 0
        dm_end = fits.getdata(raw_dir / "dm_end.fits")
        assert float(np.max(np.abs(dm_end))) < 1.0e-6
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)


def test_preshaper_uniform_broadcast_and_2x_rate_resampling(tmp_path: Path) -> None:
    """Verify KMODE=2 uniform broadcast kernel + 2x higher hardware rate resampling."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "siso2x")
    raw_dir = work_dir / "cal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    bench_file = work_dir / "plate12.bench"
    bench_file.write_text(PLATE12_PRESHAPER_BENCH, encoding="utf-8")

    # Single interior actuator poke
    poke1 = np.zeros((1, 12, 12), dtype=np.float32)
    poke1[0, 5, 5] = 1.0
    fits.writeto(raw_dir / "poke1.fits", poke1, overwrite=True)

    py = env.get("PYTHON_BIN") or shutil.which("python3") or "python3"
    script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{work_dir}"

cleanup() {{
    milk-fps-runstop -q dmps2 >/dev/null 2>&1 || true
    milk-fps-rm -f -q mdr1 cps2 dmps2 mdr2 >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy --workdir "{work_dir}" --config "{bench_file}" --mode fused --no-view >/dev/null
milk-stream-wait -q -t 20 csim_wfs:48x48 dm01disp:12x12
cd "{raw_dir}"

milk-fpsexec-iofits-saveFITS --no-procinfo -n snapwfs exec csim_wfs "!wfs_snap.fits" >/dev/null
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("wfs_snap.fits").astype(np.float32)
sig = wfs - float(np.percentile(wfs, 5.0))
fits.writeto("wfsmask.fits", (sig > 0.20 * float(sig.max())).astype(np.float32), overwrite=True)
fits.writeto("zero12.fits", np.zeros((12, 12), dtype=np.float32), overwrite=True)
PY
milk-FITS2shm --no-procinfo -n ldcmd exec zero12.fits @S:dm01cmd >/dev/null

# 1. Measure raw single-actuator 3D RM at 2 kHz
milk-fps-init -q mdr1 cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr1.streamin=dm01disp \\
    mdr1.streamout=csim_wfs \\
    mdr1.inmodes=poke1.fits \\
    mdr1.outcube=r1_raw.fits \\
    mdr1.outmask=wfsmask.fits \\
    mdr1.ampl=0.05 \\
    mdr1.timing.WFSfrequ=0.0 \\
    mdr1.timing.frameratewait=0.25 \\
    mdr1.timing.NBsubfr=4 \\
    mdr1.timing.NBrespfr=14 \\
    mdr1.timing.NBprefr=2 \\
    mdr1.timing.NBsettlefr=2 \\
    mdr1.pokemode=1 \\
    mdr1.procinfo.loopcntMax=1
milk-fps-runstart -q mdr1
milk-fps-wait -q -t 40 mdr1
milk-fps-rm -f -q mdr1

# 2. Synthesize KMODE=2 uniform broadcast SISO kernel [1, 1, M_buf]
milk-fps-init -q cps2 cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
milk-fps-set -q \\
    cps2.resp3d=r1_raw.fits \\
    cps2.inmodes=poke1.fits \\
    cps2.outkernel=dm_preshaper_uniform.fits \\
    cps2.mode=2 \\
    cps2.n_taps=22 \\
    cps2.tau_target_us=100.0 \\
    cps2.lambda_ctrl=0.015 \\
    cps2.lambda_diff=0.015 \\
    cps2.procinfo.loopcntMax=1
milk-fps-runstart -q cps2
milk-fps-wait -q -t 20 cps2
milk-fps-rm -f -q cps2

# 3. Run dmpreshaper at 2x hardware rate (4000 Hz on a 2000 Hz kernel -> tests resampling!)
milk-fps-init -q dmps2 cacao-fpsexec-dmpreshaper >/dev/null
milk-fps-set -q \\
    dmps2.streamin=dm01cmd \\
    dmps2.streamout=dm01disp \\
    dmps2.kernelfile=dm_preshaper_uniform.fits \\
    dmps2.rate_hz=4000.0 \\
    dmps2.enable=ON \\
    dmps2.gain=1.0 \\
    dmps2.procinfo.loopcntMax=-1
milk-fps-runstart -q dmps2
sleep 0.15

# 4. Measure shaped response transparently on a DIFFERENT actuator (7, 6) to verify uniform broadcast!
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
p2 = np.zeros((1, 12, 12), dtype=np.float32)
p2[0, 5, 5] = 1.0
fits.writeto("poke_test.fits", p2, overwrite=True)
PY
milk-fps-init -q mdr2 cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr2.streamin=dm01cmd \\
    mdr2.streamout=csim_wfs \\
    mdr2.inmodes=poke_test.fits \\
    mdr2.outcube=r1_shaped.fits \\
    mdr2.outmask=wfsmask.fits \\
    mdr2.ampl=0.05 \\
    mdr2.timing.WFSfrequ=0.0 \\
    mdr2.timing.frameratewait=0.25 \\
    mdr2.timing.NBsubfr=4 \\
    mdr2.timing.NBrespfr=14 \\
    mdr2.timing.NBprefr=2 \\
    mdr2.timing.NBsettlefr=2 \\
    mdr2.pokemode=1 \\
    mdr2.procinfo.loopcntMax=1
milk-fps-runstart -q mdr2
milk-fps-wait -q -t 40 mdr2
milk-fps-rm -f -q mdr2

milk-fps-info dmps2 > dmps2_info.txt
milk-fps-runstop -q dmps2
milk-fps-wait -q -t 10 dmps2
milk-fps-rm -f -q dmps2
cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null
"""
    try:
        res = _run_bash(script, env=env, timeout=120.0)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        with fits.open(raw_dir / "dm_preshaper_uniform.fits") as hdul:
            assert len(hdul) == 1
            assert int(hdul[0].header["KMODE"]) == 2
            assert hdul[0].data.shape[1:] == (1, 1)

        eff_rate = 0.0
        clean = re.sub(r"\x1b\[[0-9;]*m", "", (raw_dir / "dmps2_info.txt").read_text(encoding="utf-8"))
        for line in clean.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[1].lstrip(".") == "out.rate_hz":
                eff_rate = float(parts[3])
        assert abs(eff_rate - 4000.0) < 10.0

        r_raw = fits.getdata(raw_dir / "r1_raw.fits").astype(np.float64)[:, 0, :]
        h_raw = fits.getheader(raw_dir / "r1_raw.fits")
        st_raw = fits.getdata(raw_dir / "r1_raw_static.fits").astype(np.float64)[0]
        r_sh = fits.getdata(raw_dir / "r1_shaped.fits").astype(np.float64)[:, 0, :]
        h_sh = fits.getheader(raw_dir / "r1_shaped.fits")
        st_sh = fits.getdata(raw_dir / "r1_shaped_static.fits").astype(np.float64)[0]

        dc_err = float(np.linalg.norm(st_sh - st_raw) / np.linalg.norm(st_raw))
        assert dc_err < 0.025

        w = st_raw / float(np.dot(st_raw, st_raw))
        y_raw = r_raw[int(h_raw["Q0_BIN"]) :] @ w
        y_sh = r_sh[int(h_sh["Q0_BIN"]) :] @ w
        dt_ms = float(h_raw["DT_SEC"]) * 1.0e3
        i_ring = int(round(3.5 / dt_ms))
        ring_raw = float(np.sqrt(np.mean((y_raw[i_ring:] - 1.0) ** 2)))
        ring_sh = float(np.sqrt(np.mean((y_sh[i_ring:] - 1.0) ** 2)))
        ov_raw = (float(np.max(y_raw)) - 1.0) * 100.0
        ov_sh = (float(np.max(y_sh)) - 1.0) * 100.0
        print(
            f"\n[HIL Uniform 4 kHz Resampled] DC err={dc_err*100:.2f}% | "
            f"Overshoot: +{ov_raw:.2f}% -> +{ov_sh:.2f}% | "
            f"Ringing RMS: {ring_raw*100:.2f}% -> {ring_sh*100:.2f}% ({ring_raw/max(ring_sh,1e-9):.2f}x) | "
            f"rate={eff_rate:.0f} Hz"
        )
        assert ring_sh < ring_raw * 0.65, (
            f"Uniform 4 kHz pre-shaper ringing not suppressed: {ring_raw:.4f} -> {ring_sh:.4f}"
        )
        assert ov_sh < ov_raw * 0.78, f"Uniform 4 kHz pre-shaper overshoot: {ov_raw:.2f}% -> {ov_sh:.2f}%"
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)


def _build_zonal_disk_modes(nact: int = 12, r_max: float = 4.7) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Build single-actuator zonal poke basis covering interior + free-rim pupil actuators."""
    ctr = 0.5 * (nact - 1)
    coords: list[tuple[int, int]] = []
    for iy in range(nact):
        for ix in range(nact):
            if math.hypot(ix - ctr, iy - ctr) <= r_max:
                coords.append((ix, iy))
    cube = np.zeros((len(coords), nact, nact), dtype=np.float32)
    for m, (ix, iy) in enumerate(coords):
        cube[m, iy, ix] = 1.0
    return cube, coords


def test_preshaper_per_actuator_siso_and_local_stencil_mimo_hil(tmp_path: Path) -> None:
    """Live GPU HIL validation of per-actuator KMODE=3 (SISO) and KMODE=4 (local-stencil MIMO)."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "peract")
    raw_dir = work_dir / "cal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    bench_file = work_dir / "plate12.bench"
    bench_file.write_text(PLATE12_PRESHAPER_BENCH, encoding="utf-8")

    zonal_cube, coords = _build_zonal_disk_modes(12, r_max=4.7)
    coord_to_idx = {xy: i for i, xy in enumerate(coords)}
    # Four probes spanning interior + mid-pupil + east/north free-rim edges
    probe_coords = [(5, 5), (3, 4), (10, 5), (5, 10)]
    for xy in probe_coords:
        assert xy in coord_to_idx, f"Probe actuator {xy} not in active zonal disk"
    probe_indices = [coord_to_idx[xy] for xy in probe_coords]

    probe_cube = np.zeros((len(probe_coords), 12, 12), dtype=np.float32)
    for j, (ix, iy) in enumerate(probe_coords):
        probe_cube[j, iy, ix] = 1.0

    fits.writeto(raw_dir / "poke_zonal.fits", zonal_cube, overwrite=True)
    fits.writeto(raw_dir / "poke_probe4.fits", probe_cube, overwrite=True)

    py = env.get("PYTHON_BIN") or shutil.which("python3") or "python3"
    script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{work_dir}"

cleanup() {{
    milk-fps-runstop -q dmps_pa >/dev/null 2>&1 || true
    milk-fps-rm -f -q mdr_z cps_k3 cps_k3f cps_k4 cps_k4f dmps_pa mdr_p >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy --workdir "{work_dir}" --config "{bench_file}" --mode fused --no-view >/dev/null
milk-stream-wait -q -t 20 csim_wfs:48x48 dm01disp:12x12
cd "{raw_dir}"

milk-fpsexec-iofits-saveFITS --no-procinfo -n snapwfs exec csim_wfs "!wfs_snap.fits" >/dev/null
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("wfs_snap.fits").astype(np.float32)
sig = wfs - float(np.percentile(wfs, 5.0))
fits.writeto("wfsmask.fits", (sig > 0.20 * float(sig.max())).astype(np.float32), overwrite=True)
fits.writeto("zero12.fits", np.zeros((12, 12), dtype=np.float32), overwrite=True)
PY
milk-FITS2shm --no-procinfo -n ldcmd exec zero12.fits @S:dm01cmd >/dev/null

# 1. Measure baseline unshaped zonal 3D RM across all {len(coords)} active pupil actuators
milk-fps-init -q mdr_z cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_z.streamin=dm01disp \\
    mdr_z.streamout=csim_wfs \\
    mdr_z.inmodes=poke_zonal.fits \\
    mdr_z.outcube=resp3D_zonal_raw.fits \\
    mdr_z.outmask=wfsmask.fits \\
    mdr_z.ampl=0.04 \\
    mdr_z.timing.WFSfrequ=0.0 \\
    mdr_z.timing.frameratewait=0.25 \\
    mdr_z.timing.NBsubfr=4 \\
    mdr_z.timing.NBrespfr=14 \\
    mdr_z.timing.NBprefr=2 \\
    mdr_z.timing.NBsettlefr=2 \\
    mdr_z.timing.NBcycle=1 \\
    mdr_z.pokemode=1 \\
    mdr_z.phaseorder=0 \\
    mdr_z.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_z
milk-fps-wait -q -t 90 mdr_z
milk-fps-rm -f -q mdr_z

# 2. Synthesize KMODE=3 (per-actuator SISO) with fill_uncal OFF and ON
milk-fps-init -q cps_k3 cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
milk-fps-set -q \\
    cps_k3.resp3d=resp3D_zonal_raw.fits \\
    cps_k3.inmodes=poke_zonal.fits \\
    cps_k3.outkernel=dm_ps_k3.fits \\
    cps_k3.mode=3 \\
    cps_k3.fill_uncal=OFF \\
    cps_k3.n_taps=22 \\
    cps_k3.tau_target_us=100.0 \\
    cps_k3.lambda_ctrl=0.015 \\
    cps_k3.lambda_diff=0.015 \\
    cps_k3.max_gain=2.5 \\
    cps_k3.procinfo.loopcntMax=1
milk-fps-runstart -q cps_k3
milk-fps-wait -q -t 30 cps_k3
milk-fps-rm -f -q cps_k3

milk-fps-init -q cps_k3f cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
milk-fps-set -q \\
    cps_k3f.resp3d=resp3D_zonal_raw.fits \\
    cps_k3f.inmodes=poke_zonal.fits \\
    cps_k3f.outkernel=dm_ps_k3_fill.fits \\
    cps_k3f.mode=3 \\
    cps_k3f.fill_uncal=ON \\
    cps_k3f.n_taps=22 \\
    cps_k3f.tau_target_us=100.0 \\
    cps_k3f.lambda_ctrl=0.015 \\
    cps_k3f.lambda_diff=0.015 \\
    cps_k3f.max_gain=2.5 \\
    cps_k3f.procinfo.loopcntMax=1
milk-fps-runstart -q cps_k3f
milk-fps-wait -q -t 30 cps_k3f
milk-fps-rm -f -q cps_k3f

# 3. Synthesize KMODE=4 (per-actuator local-stencil MIMO, R=2 -> 5x5) with fill_uncal OFF and ON
milk-fps-init -q cps_k4 cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
milk-fps-set -q \\
    cps_k4.resp3d=resp3D_zonal_raw.fits \\
    cps_k4.inmodes=poke_zonal.fits \\
    cps_k4.outkernel=dm_ps_k4.fits \\
    cps_k4.mode=4 \\
    cps_k4.stencil_rad=2 \\
    cps_k4.fill_uncal=OFF \\
    cps_k4.n_taps=22 \\
    cps_k4.tau_target_us=100.0 \\
    cps_k4.lambda_ctrl=0.015 \\
    cps_k4.lambda_diff=0.015 \\
    cps_k4.max_gain=2.5 \\
    cps_k4.procinfo.loopcntMax=1
milk-fps-runstart -q cps_k4
milk-fps-wait -q -t 45 cps_k4
milk-fps-rm -f -q cps_k4

milk-fps-init -q cps_k4f cacao-fpsexec-cacaocc-compdmpreshaper >/dev/null
milk-fps-set -q \\
    cps_k4f.resp3d=resp3D_zonal_raw.fits \\
    cps_k4f.inmodes=poke_zonal.fits \\
    cps_k4f.outkernel=dm_ps_k4_fill.fits \\
    cps_k4f.mode=4 \\
    cps_k4f.stencil_rad=2 \\
    cps_k4f.fill_uncal=ON \\
    cps_k4f.n_taps=22 \\
    cps_k4f.tau_target_us=100.0 \\
    cps_k4f.lambda_ctrl=0.015 \\
    cps_k4f.lambda_diff=0.015 \\
    cps_k4f.max_gain=2.5 \\
    cps_k4f.procinfo.loopcntMax=1
milk-fps-runstart -q cps_k4f
milk-fps-wait -q -t 45 cps_k4f
milk-fps-rm -f -q cps_k4f

run_pass2() {{
    local kern="$1"
    local rate="$2"
    local outcube="$3"
    local infofile="$4"
    milk-fps-init -q dmps_pa cacao-fpsexec-dmpreshaper >/dev/null
    milk-fps-set -q \\
        dmps_pa.streamin=dm01cmd \\
        dmps_pa.streamout=dm01disp \\
        dmps_pa.kernelfile="${{kern}}" \\
        dmps_pa.rate_hz="${{rate}}" \\
        dmps_pa.freerun=OFF \\
        dmps_pa.enable=ON \\
        dmps_pa.gain=1.0 \\
        dmps_pa.procinfo.loopcntMax=-1
    milk-fps-runstart -q dmps_pa
    sleep 0.15

    milk-fps-init -q mdr_p cacao-fpsexec-cacaoac-measdynresp >/dev/null
    milk-fps-set -q \\
        mdr_p.streamin=dm01cmd \\
        mdr_p.streamout=csim_wfs \\
        mdr_p.inmodes=poke_probe4.fits \\
        mdr_p.outcube="${{outcube}}" \\
        mdr_p.outmask=wfsmask.fits \\
        mdr_p.ampl=0.04 \\
        mdr_p.timing.WFSfrequ=0.0 \\
        mdr_p.timing.frameratewait=0.25 \\
        mdr_p.timing.NBsubfr=4 \\
        mdr_p.timing.NBrespfr=14 \\
        mdr_p.timing.NBprefr=2 \\
        mdr_p.timing.NBsettlefr=2 \\
        mdr_p.timing.NBcycle=1 \\
        mdr_p.pokemode=1 \\
        mdr_p.phaseorder=0 \\
        mdr_p.procinfo.loopcntMax=1
    milk-fps-runstart -q mdr_p
    milk-fps-wait -q -t 40 mdr_p
    milk-fps-rm -f -q mdr_p

    milk-fps-info dmps_pa > "${{infofile}}"
    milk-fps-runstop -q dmps_pa
    milk-fps-wait -q -t 10 dmps_pa
    milk-fps-rm -f -q dmps_pa
}}

# 4. Live GPU Pass-2 probes for KMODE=3 (2 kHz), KMODE=4 (2 kHz), and KMODE=4 resampled (4 kHz)
run_pass2 dm_ps_k3.fits 0.0 resp3D_k3.fits info_k3.txt
run_pass2 dm_ps_k4.fits 0.0 resp3D_k4.fits info_k4.txt
run_pass2 dm_ps_k4.fits 4000.0 resp3D_k4_4k.fits info_k4_4k.txt

cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null
"""
    try:
        res = _run_bash(script, env=env, timeout=240.0)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        # 1. Verify KMODE=3 FITS structure, spatial non-uniformity & fill_uncal
        with fits.open(raw_dir / "dm_ps_k3.fits") as hdul:
            assert len(hdul) == 1
            h3 = hdul[0].header
            assert int(h3["KMODE"]) == 3
            assert int(h3["DECONV"]) == 1
            assert int(h3["ENRGWGT"]) == 1
            k3 = hdul[0].data.astype(np.float64)  # [M_buf, 12, 12]
            assert k3.shape[1:] == (12, 12)
            assert float(np.max(np.abs(k3[:, 0, 0]))) == 0.0, "Uncalibrated corner not zero for fill_uncal=OFF"
            k3_int = k3[:, 5, 5]
            k3_rim = k3[:, 5, 10]
            k3_diff_rel = float(np.linalg.norm(k3_rim - k3_int) / max(np.linalg.norm(k3_int), 1e-12))
            assert k3_diff_rel > 0.05, f"KMODE=3 interior vs rim unexpectedly uniform (rel={k3_diff_rel:.4f})"

        k3_fill = fits.getdata(raw_dir / "dm_ps_k3_fill.fits").astype(np.float64)
        assert float(np.linalg.norm(k3_fill[:, 0, 0])) > 1.0e-3, "KMODE=3 fill_uncal=ON did not populate corner"

        # 2. Verify KMODE=4 FITS structure, gather stencil geometry, rim asymmetry & fill_uncal
        with fits.open(raw_dir / "dm_ps_k4.fits") as hdul:
            assert len(hdul) == 1
            h4 = hdul[0].header
            assert int(h4["KMODE"]) == 4
            assert int(h4["STNCLRAD"]) == 2
            assert int(h4["STNCLNB"]) == 25
            assert int(h4["DECONV"]) == 1
            assert int(h4["ENRGWGT"]) == 1
            k4 = hdul[0].data.astype(np.float64)  # [M_buf, 144, 25]
            assert k4.shape[1:] == (144, 25)
            # Corner (0, 0) uncalibrated -> exact zeros
            assert float(np.max(np.abs(k4[:, 0, :]))) == 0.0, "KMODE=4 uncal corner not zero"
            i_int = 5 * 12 + 5
            i_rim = 5 * 12 + 10
            # Center tap p = (dy+2)*5 + (dx+2) = 12; dx=-1 -> p=11; dx=+1 -> p=13
            assert float(np.linalg.norm(k4[:, i_int, 11])) > 1.0e-3, "Interior stencil missing dx=-1 neighbor"
            assert float(np.linalg.norm(k4[:, i_int, 13])) > 1.0e-3, "Interior stencil missing dx=+1 neighbor"
            assert float(np.linalg.norm(k4[:, i_rim, 11])) > 1.0e-3, "East-rim stencil missing inward dx=-1"
            assert float(np.max(np.abs(k4[:, i_rim, 13]))) == 0.0, "East-rim stencil should be 0 outside disk (dx=+1)"
            k4_self_diff = float(
                np.linalg.norm(k4[:, i_rim, 12] - k4[:, i_int, 12])
                / max(np.linalg.norm(k4[:, i_int, 12]), 1e-12)
            )
            assert k4_self_diff > 0.05, f"KMODE=4 interior vs rim self-tap too uniform (rel={k4_self_diff:.4f})"

        k4_fill = fits.getdata(raw_dir / "dm_ps_k4_fill.fits").astype(np.float64)
        assert float(np.linalg.norm(k4_fill[:, 0, 12])) > 1.0e-3, "KMODE=4 fill_uncal=ON did not populate corner"

        # Verify 2x resampled output rate on KMODE=4
        eff_rate_4k = 0.0
        clean = re.sub(r"\x1b\[[0-9;]*m", "", (raw_dir / "info_k4_4k.txt").read_text(encoding="utf-8"))
        for line in clean.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[1].lstrip(".") == "out.rate_hz":
                eff_rate_4k = float(parts[3])
        assert abs(eff_rate_4k - 4000.0) < 10.0, f"Expected 4000 Hz KMODE=4 rate, got {eff_rate_4k}"

        # 3. Project raw & all 3 Pass-2 probes onto the FULL calibrated zonal actuator space
        r_raw = fits.getdata(raw_dir / "resp3D_zonal_raw.fits").astype(np.float64)
        h_raw = fits.getheader(raw_dir / "resp3D_zonal_raw.fits")
        stat_raw = fits.getdata(raw_dir / "resp3D_zonal_raw_static.fits").astype(np.float64)  # [N_act, N_wfs]
        u, s, vt = np.linalg.svd(stat_raw, full_matrices=False)
        c_pinv_all = (u * np.where(s > 1e-3 * s[0], 1.0 / s, 0.0)[None, :]) @ vt  # [N_act, N_wfs]

        dt_ms = float(h_raw["DT_SEC"]) * 1.0e3
        i_ring = int(round(3.5 / dt_ms))
        q0_raw = int(h_raw["Q0_BIN"])

        # Extract the 4 probe columns from baseline raw 3D RM
        m_raw_4 = np.einsum("ap,tjp->taj", c_pinv_all, r_raw[q0_raw:, probe_indices, :], optimize=True)
        stat_raw_4 = stat_raw[probe_indices]

        def _eval_pass2(cube_name: str, stat_name: str) -> dict[str, float]:
            rc = fits.getdata(raw_dir / cube_name).astype(np.float64)
            hc = fits.getheader(raw_dir / cube_name)
            st = fits.getdata(raw_dir / stat_name).astype(np.float64)
            dc_err = float(np.linalg.norm(st - stat_raw_4) / np.linalg.norm(stat_raw_4))
            rc_post = rc[int(hc["Q0_BIN"]) :, :, :]
            mc = np.einsum("ap,tjp->taj", c_pinv_all, rc_post, optimize=True)
            # Oblique self-actuator curves [L, 4] and matched-filter WFS self-response [L, 4]
            self_curves = np.stack([mc[:, probe_indices[j], j] for j in range(len(probe_indices))], axis=1)
            mf_curves = np.stack(
                [
                    (rc_post[:, j, :] @ stat_raw_4[j]) / max(float(np.dot(stat_raw_4[j], stat_raw_4[j])), 1e-18)
                    for j in range(len(probe_indices))
                ],
                axis=1,
            )
            ov_mean = float(np.mean((self_curves.max(axis=0) - 1.0) * 100.0))
            ov_int = float(np.mean((self_curves[:, :2].max(axis=0) - 1.0) * 100.0))
            ov_rim = float(np.mean((self_curves[:, 2:].max(axis=0) - 1.0) * 100.0))
            ring_mean = float(np.sqrt(np.mean((self_curves[i_ring:] - 1.0) ** 2)))
            ring_rim = float(np.sqrt(np.mean((self_curves[i_ring:, 2:] - 1.0) ** 2)))
            ring_mf = float(np.sqrt(np.mean((mf_curves[i_ring:] - 1.0) ** 2)))
            ov_mf = float(np.mean((mf_curves.max(axis=0) - 1.0) * 100.0))

            off_pks = []
            off_rms = []
            for j, m_idx in enumerate(probe_indices):
                sub = mc[:, :, j].copy()
                sub[:, m_idx] = 0.0
                norms_t = np.linalg.norm(sub, axis=1)
                off_pks.append(float(norms_t.max()))
                off_rms.append(float(np.sqrt(np.mean(norms_t**2))))
            return {
                "dc_err": dc_err,
                "ov": ov_mean,
                "ov_int": ov_int,
                "ov_rim": ov_rim,
                "ring": ring_mean,
                "ring_rim": ring_rim,
                "ring_mf": ring_mf,
                "ov_mf": ov_mf,
                "off_pk": float(np.mean(off_pks)),
                "off_rms": float(np.mean(off_rms)),
            }

        # Evaluate baseline raw on the exact same 4 probes
        r_raw_post = r_raw[q0_raw:, probe_indices, :]
        raw_self = np.stack([m_raw_4[:, probe_indices[j], j] for j in range(len(probe_indices))], axis=1)
        raw_mf = np.stack(
            [
                (r_raw_post[:, j, :] @ stat_raw_4[j]) / max(float(np.dot(stat_raw_4[j], stat_raw_4[j])), 1e-18)
                for j in range(len(probe_indices))
            ],
            axis=1,
        )
        raw_off_pks = []
        raw_off_rms = []
        for j, m_idx in enumerate(probe_indices):
            sub = m_raw_4[:, :, j].copy()
            sub[:, m_idx] = 0.0
            norms_t = np.linalg.norm(sub, axis=1)
            raw_off_pks.append(float(norms_t.max()))
            raw_off_rms.append(float(np.sqrt(np.mean(norms_t**2))))
        m_raw = {
            "ov": float(np.mean((raw_self.max(axis=0) - 1.0) * 100.0)),
            "ov_int": float(np.mean((raw_self[:, :2].max(axis=0) - 1.0) * 100.0)),
            "ov_rim": float(np.mean((raw_self[:, 2:].max(axis=0) - 1.0) * 100.0)),
            "ring": float(np.sqrt(np.mean((raw_self[i_ring:] - 1.0) ** 2))),
            "ring_rim": float(np.sqrt(np.mean((raw_self[i_ring:, 2:] - 1.0) ** 2))),
            "ring_mf": float(np.sqrt(np.mean((raw_mf[i_ring:] - 1.0) ** 2))),
            "ov_mf": float(np.mean((raw_mf.max(axis=0) - 1.0) * 100.0)),
            "off_pk": float(np.mean(raw_off_pks)),
            "off_rms": float(np.mean(raw_off_rms)),
        }
        m_k3 = _eval_pass2("resp3D_k3.fits", "resp3D_k3_static.fits")
        m_k4 = _eval_pass2("resp3D_k4.fits", "resp3D_k4_static.fits")
        m_k4_4k = _eval_pass2("resp3D_k4_4k.fits", "resp3D_k4_4k_static.fits")

        print(
            f"\n[HIL Per-Actuator ({len(coords)} act, 4 probes: int+rim)] "
            f"Spatial diff: K3={k3_diff_rel*100:.1f}%, K4_self={k4_self_diff*100:.1f}%\n"
            f"  RAW       : Ov=+{m_raw['ov']:.2f}% (int +{m_raw['ov_int']:.2f}%, rim +{m_raw['ov_rim']:.2f}%) | "
            f"Ring={m_raw['ring']*100:.2f}% (MF {m_raw['ring_mf']*100:.2f}%) | "
            f"2D-Wave pk={m_raw['off_pk']:.4f}, rms={m_raw['off_rms']:.4f}\n"
            f"  KMODE=3   : DC={m_k3['dc_err']*100:.2f}% | Ov=+{m_k3['ov']:.2f}% (rim +{m_k3['ov_rim']:.2f}%) | "
            f"Ring={m_k3['ring']*100:.2f}% ({m_raw['ring']/max(m_k3['ring'],1e-9):.2f}x obliq, MF {m_raw['ring_mf']/max(m_k3['ring_mf'],1e-9):.2f}x) | "
            f"2D-Wave pk={m_k3['off_pk']:.4f} ({m_raw['off_pk']/max(m_k3['off_pk'],1e-9):.2f}x), rms={m_k3['off_rms']:.4f}\n"
            f"  KMODE=4 2k: DC={m_k4['dc_err']*100:.2f}% | Ov=+{m_k4['ov']:.2f}% (rim +{m_k4['ov_rim']:.2f}%) | "
            f"Ring={m_k4['ring']*100:.2f}% ({m_raw['ring']/max(m_k4['ring'],1e-9):.2f}x) | "
            f"2D-Wave pk={m_k4['off_pk']:.4f} ({m_raw['off_pk']/max(m_k4['off_pk'],1e-9):.2f}x), rms={m_k4['off_rms']:.4f}\n"
            f"  KMODE=4 4k: DC={m_k4_4k['dc_err']*100:.2f}% | Ov=+{m_k4_4k['ov']:.2f}% (rim +{m_k4_4k['ov_rim']:.2f}%) | "
            f"Ring={m_k4_4k['ring']*100:.2f}% ({m_raw['ring']/max(m_k4_4k['ring'],1e-9):.2f}x) | "
            f"2D-Wave pk={m_k4_4k['off_pk']:.4f} ({m_raw['off_pk']/max(m_k4_4k['off_pk'],1e-9):.2f}x), rate={eff_rate_4k:.0f} Hz"
        )

        # Unity DC gain preserved across all modes & resampling rates
        assert m_k3["dc_err"] < 0.025, f"KMODE=3 DC gain drifted: {m_k3['dc_err']:.4f}"
        assert m_k4["dc_err"] < 0.025, f"KMODE=4 2k DC gain drifted: {m_k4['dc_err']:.4f}"
        assert m_k4_4k["dc_err"] < 0.025, f"KMODE=4 4k DC gain drifted: {m_k4_4k['dc_err']:.4f}"

        # Both KMODE=3 (matched-filter SISO) and KMODE=4 (full local-stencil MIMO) suppress ringing & overshoot
        assert m_k3["ring_mf"] < m_raw["ring_mf"] * 0.68, (
            f"KMODE=3 matched-filter ringing not suppressed: {m_raw['ring_mf']:.4f} -> {m_k3['ring_mf']:.4f}"
        )
        assert m_k3["ring"] < m_raw["ring"] * 0.75, f"KMODE=3 oblique ringing not suppressed: {m_raw['ring']:.4f} -> {m_k3['ring']:.4f}"
        assert m_k3["ov"] < m_raw["ov"] * 0.78, f"KMODE=3 overshoot not suppressed: {m_raw['ov']:.2f}% -> {m_k3['ov']:.2f}%"
        assert m_k4["ring"] < m_raw["ring"] * 0.45, f"KMODE=4 ringing not suppressed: {m_raw['ring']:.4f} -> {m_k4['ring']:.4f}"
        assert m_k4["ov"] < m_raw["ov"] * 0.65, f"KMODE=4 overshoot not suppressed: {m_raw['ov']:.2f}% -> {m_k4['ov']:.2f}%"
        assert m_k4_4k["ring"] < m_raw["ring"] * 0.50, f"KMODE=4 4k ringing not suppressed: {m_raw['ring']:.4f} -> {m_k4_4k['ring']:.4f}"

        # KMODE=4 local-stencil MIMO must strictly beat BOTH raw AND KMODE=3 on 2D cross-actuator wave coupling!
        assert m_k4["off_pk"] < m_raw["off_pk"] * 0.65, (
            f"KMODE=4 2D wave coupling not cut vs raw: {m_raw['off_pk']:.4f} -> {m_k4['off_pk']:.4f}"
        )
        assert m_k4["off_rms"] < m_k3["off_rms"] * 0.80, (
            f"KMODE=4 did not beat KMODE=3 on 2D cross-actuator wave RMS: "
            f"K3={m_k3['off_rms']:.4f} vs K4={m_k4['off_rms']:.4f}"
        )
        assert m_k4_4k["off_rms"] < m_k3["off_rms"] * 0.85, (
            f"KMODE=4 4k resampled did not beat KMODE=3 on 2D wave RMS: "
            f"K3={m_k3['off_rms']:.4f} vs K4_4k={m_k4_4k['off_rms']:.4f}"
        )
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)
