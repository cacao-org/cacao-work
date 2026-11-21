# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end validation of cacaoac-measdynresp on a cacaosim plate-PDE DM bench."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from astropy.io import fits

# 1600 Hz master bench with a coupled 2D circular-rim plate-PDE DM (dyn_mode = "plate")
# and a fixed 400 Hz (navg = 4) noiseless Pyramid WFS.
PLATE_BENCH_TEMPLATE = """\
[bench]
name       = "dynrm_plate"
nwf        = 128
pup_diam   = 0.9375
cobs       = 0.20
nspider    = 0
tel_diam_m = 8.0
star_mag   = 5.0
star_teff  = 5778.0
tput_tel   = 0.85
master_hz  = 1600.0
oversample = 1
in_wf      = "outarraypha"
in_pup     = "csim_pup"
out_beam   = "b_tel"
wf_unit    = 1
ref_lambda = 0.50
turb_gain  = 0.0

[dm.dm0]
in           = "b_tel"
out          = "b_corr"
in_cmd       = "dm00disp"
out_opd      = "csim_dm00_opd"
nact_x       = 12
nact_y       = 12
if_coupling  = 0.20
tput         = 0.98
max_stroke   = 10.0
dac_bits     = 0
dyn_mode     = "plate"
tau_us       = 150.0
f0_hz        = 220.0
act_pitch_mm = 2.0
wave_c       = 7.0
bend_beta    = 0.0025
damp_g0      = 140.0
damp_g2      = 0.5
plate_drive  = "disp"
rim_bc       = "clamped"
delay_us     = 625.0

[pyrwfs.wfs]
in            = "b_corr"
out_cam       = "csim_wfs"
ncam          = 64
lambda_um     = 0.75
bw_frac       = 0.20
qe            = 0.85
use_beam_flux = 1
navg          = 4
mod_rad       = 3.0
mod_npts      = 16
ron_e         = 0.0
photon_noise  = 0
out_dtype     = "float32"
"""


def _write_test_poke_modes(path: Path, nact: int = 12) -> None:
    """Create 3 poke modes: central actuator, off-center actuator, and radial focus."""
    modes = np.zeros((3, nact, nact), dtype=np.float32)
    # Mode 0: central actuator (6, 6) — launches circular plate wave toward rim
    modes[0, 6, 6] = 1.0
    # Mode 1: off-center actuator (6, 3) — asymmetric wave & rim reflection
    modes[1, 6, 3] = 1.0
    # Mode 2: low-order defocus (smooth r^2 mode)
    yy, xx = np.mgrid[0:nact, 0:nact]
    rr2 = ((xx - 5.5) ** 2 + (yy - 5.5) ** 2) / (5.5**2)
    fmode = (2.0 * rr2 - 1.0) * (rr2 <= 1.05)
    fmode /= np.max(np.abs(fmode))
    modes[2] = fmode.astype(np.float32)
    fits.writeto(path, modes, overwrite=True)


def _first_crossing_bin(curve: np.ndarray, q0: int, frac: float = 0.25) -> float:
    """Return fractional bin index >= q0 where |curve| first crosses frac * peak."""
    post = curve[q0:]
    peak = float(np.max(post))
    assert peak > 0.0, "empty response curve"
    thr = frac * peak
    for idx in range(len(post)):
        if post[idx] >= thr:
            if idx == 0:
                return float(q0)
            y0, y1 = float(post[idx - 1]), float(post[idx])
            alpha = (thr - y0) / max(y1 - y0, 1e-12)
            return float(q0 + idx - 1) + alpha
    return float(q0 + len(post) - 1)


def test_measdynresp_plate_waves_and_static_parity(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Validate wall-clock stroboscopic 3D RM, lockstep parity, plate waves, and static RM."""
    shm_dir, work_dir, env = shm_sandbox
    csim_dir = work_dir / "csim"
    bench_cfg = work_dir / "plate.bench"
    inmodes = work_dir / "poke3.fits"
    wfs_mask = work_dir / "wfsmask.fits"
    out_wc = work_dir / "resp3D_wc.fits"
    out_ls = work_dir / "resp3D_ls.fits"
    out_lin = work_dir / "resp2D_lin.fits"
    wfs_snap = work_dir / "wfs_snap.fits"
    dm_end = work_dir / "dm_end.fits"

    bench_cfg.write_text(PLATE_BENCH_TEMPLATE, encoding="utf-8")
    _write_test_poke_modes(inmodes)

    # Deploy bench, capture active WFS pixel mask, run wall-clock + lockstep 3D RM + 2D measlinresp
    script = f"""
set -euo pipefail
source "{repo_root}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{csim_dir}"

cleanup() {{
    cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy \\
    --workdir "{csim_dir}" \\
    --config "{bench_cfg}" \\
    --mode fused --no-view >/dev/null

milk-stream-wait -q -t 15 csim_wfs:64x64 csim_dm00_opd:128x128 dm00disp:12x12

# Snapshot one illuminated WFS frame to build an active-pixel mask
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapwfs exec csim_wfs "!{wfs_snap}" >/dev/null

"{env['PYTHON_BIN']}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("{wfs_snap}").astype(np.float32)
mask = (wfs > 0.20 * float(wfs.max())).astype(np.float32)
fits.writeto("{wfs_mask}", mask, overwrite=True)
PY

# 1. Wall-clock stroboscopic 3D RM (fixed 400 Hz WFS, NBsubfr=4 -> 1600 Hz effective)
milk-fps-init -q mdr_wc cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_wc.streamin=dm00disp \\
    mdr_wc.streamout=csim_wfs \\
    mdr_wc.inmodes="{inmodes}" \\
    mdr_wc.outcube="{out_wc}" \\
    mdr_wc.outmask="{wfs_mask}" \\
    mdr_wc.ampl=0.02 \\
    mdr_wc.normalize=OFF \\
    mdr_wc.timing.WFSfrequ=0.0 \\
    mdr_wc.timing.frameratewait=0.4 \\
    mdr_wc.timing.NBsubfr=4 \\
    mdr_wc.timing.NBrespfr=18 \\
    mdr_wc.timing.NBprefr=2 \\
    mdr_wc.timing.NBsettlefr=2 \\
    mdr_wc.timing.NBcycle=1 \\
    mdr_wc.timing.spinus=60 \\
    mdr_wc.pokemode=0 \\
    mdr_wc.phaseorder=0 \\
    mdr_wc.saveALL=ON \\
    mdr_wc.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_wc
milk-fps-wait -q -t 60 mdr_wc
milk-fps-rm -f -q mdr_wc

# Verify DM was zeroed on exit
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapdm exec dm00disp "!{dm_end}" >/dev/null

# 2. Lockstep trigstream 3D RM (pokemode=1 push-pull +a<->-a)
milk-fps-init -q mdr_ls cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_ls.streamin=dm00disp \\
    mdr_ls.streamout=csim_wfs \\
    mdr_ls.inmodes="{inmodes}" \\
    mdr_ls.outcube="{out_ls}" \\
    mdr_ls.outmask="{wfs_mask}" \\
    mdr_ls.trigstream=csim_dm00_opd \\
    mdr_ls.ampl=0.02 \\
    mdr_ls.normalize=OFF \\
    mdr_ls.timing.WFSfrequ=400.0 \\
    mdr_ls.timing.NBsubfr=4 \\
    mdr_ls.timing.NBrespfr=18 \\
    mdr_ls.timing.NBprefr=2 \\
    mdr_ls.timing.NBsettlefr=2 \\
    mdr_ls.timing.NBcycle=1 \\
    mdr_ls.pokemode=1 \\
    mdr_ls.phaseorder=0 \\
    mdr_ls.saveALL=OFF \\
    mdr_ls.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_ls
milk-fps-wait -q -t 60 mdr_ls
milk-fps-rm -f -q mdr_ls

# 3. Standard static 2D RM via cacaoac-measlinresp (NBexcl=28 -> RMdelayfr=15, >35 ms settle)
milk-fps-init -q mlr_ref cacao-fpsexec-cacaoac-measlinresp >/dev/null
milk-fps-set -q \\
    mlr_ref.streamin=dm00disp \\
    mlr_ref.streamout=csim_wfs \\
    mlr_ref.inmodes="{inmodes}" \\
    mlr_ref.outmodes="{out_lin}" \\
    mlr_ref.ampl=0.02 \\
    mlr_ref.timing.WFSfrequ=400.0 \\
    mlr_ref.timing.hardwlatfr=1.0 \\
    mlr_ref.timing.NBave=4 \\
    mlr_ref.timing.NBexcl=28 \\
    mlr_ref.timing.NBinnerCycle=1 \\
    mlr_ref.procinfo.loopcntMax=1
milk-fps-runstart -q mlr_ref
milk-fps-wait -q -t 60 mlr_ref
milk-fps-rm -f -q mlr_ref

cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null
"""
    res = subprocess.run(
        ["bash", "-c", script],
        cwd=work_dir,
        env=env,
        timeout=150,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"

    # --- Verify DM zeroed on exit ---
    dm_arr = fits.getdata(dm_end)
    assert float(np.max(np.abs(dm_arr))) == 0.0

    # --- Load wall-clock 3D cube and auxiliary files ---
    with fits.open(out_wc) as hdul:
        r3_wc = hdul[0].data.astype(np.float64)  # (N_t, N_in, N_out)
        hdr_wc = dict(hdul[0].header)

    cnt_wc = fits.getdata(work_dir / "resp3D_wc_cnt.fits")  # (N_t, N_in)
    tmean_wc = fits.getdata(work_dir / "resp3D_wc_tmean.fits")  # (N_t, N_in)
    stat_wc = fits.getdata(work_dir / "resp3D_wc_static.fits").astype(np.float64)  # (N_in, N_out)
    asym_wc = fits.getdata(work_dir / "resp3D_wc_asym.fits").astype(np.float64)
    mask_2d = fits.getdata(wfs_mask) > 0.5
    n_mask = int(mask_2d.sum())

    q0 = int(hdr_wc["Q0_BIN"])
    n_subfr = int(hdr_wc["NBSUBFR"])
    n_respfr = int(hdr_wc["NBRESPFR"])
    n_t = q0 + n_respfr * n_subfr

    assert n_subfr == 4
    assert q0 == 4
    assert r3_wc.shape == (n_t, 3, n_mask)
    assert hdr_wc["LOCKSTEP"] == 0
    assert 370.0 < float(hdr_wc["WFSFREQ"]) < 430.0
    assert float(hdr_wc["JITTERUS"]) < 50.0, f"high poke jitter: {hdr_wc['JITTERUS']} us"
    assert (work_dir / "resp3D_wc_meta.txt").is_file()

    # Every post-poke bin should have samples (no missing sub-frame bins)
    assert int(cnt_wc[q0:].min()) >= 1, f"empty post-poke bins: min={cnt_wc[q0:].min()}"
    # Measured mean lags should increase monotonically across post-poke bins
    t_post = tmean_wc[q0:, 0]
    assert np.all(np.diff(t_post) > 0.0), f"non-monotonic bin times: {t_post[:12]}"

    # Pre-poke bins [0..q0-1] must be flat zero relative to steady-state signal
    rms_all = np.sqrt(np.mean(r3_wc**2, axis=2))  # (N_t, N_in)
    for m in range(3):
        pre_rms = float(np.max(rms_all[:q0, m]))
        stat_rms = float(np.sqrt(np.mean(stat_wc[m] ** 2)))
        assert stat_rms > 0.0
        assert pre_rms < 1.0e-2 * stat_rms, f"mode {m} pre-poke leak: {pre_rms} vs {stat_rms}"

    # Verify plate-PDE mechanical dynamics: overshoot/ringing > settled steady state
    for m in (0, 1):
        peak_rms = float(np.max(rms_all[q0:, m]))
        stat_rms = float(np.sqrt(np.mean(stat_wc[m] ** 2)))
        assert peak_rms > 1.05 * stat_rms, (
            f"mode {m} expected plate overshoot: peak={peak_rms:.4g} stat={stat_rms:.4g}"
        )

    # Verify spatial plate-wave propagation from central actuator (mode 0) across PyWFS pupils:
    # Build pixel radius relative to each of the 4 PyWFS sub-pupil centers (16,16), (48,16), etc.
    yy, xx = np.mgrid[0:64, 0:64]
    cx = np.where(xx < 32, 15.5, 47.5)
    cy = np.where(yy < 32, 15.5, 47.5)
    rr_pup = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)[mask_2d]
    r_max = float(rr_pup.max())
    inner_sel = rr_pup < 0.35 * r_max
    outer_sel = rr_pup > 0.72 * r_max
    assert inner_sel.sum() > 20 and outer_sel.sum() > 20

    # Dynamic energy in inner core vs outer ring for central actuator poke (mode 0)
    m0 = r3_wc[:, 0, :]  # (N_t, N_out)
    inner_rms = np.sqrt(np.mean(m0[:, inner_sel] ** 2, axis=1))
    outer_rms = np.sqrt(np.mean(m0[:, outer_sel] ** 2, axis=1))
    t_inner = _first_crossing_bin(inner_rms, q0, frac=0.25)
    t_outer = _first_crossing_bin(outer_rms, q0, frac=0.25)
    assert t_outer > t_inner + 0.5, (
        f"expected outward plate wave delay: t_inner={t_inner:.2f} vs t_outer={t_outer:.2f}"
    )
    # Outer ring should exhibit a transient mechanical wave stronger than its final static footprint
    outer_peak = float(np.max(outer_rms[q0:]))
    outer_tail = float(np.mean(outer_rms[-8:]))
    assert outer_peak > 1.4 * outer_tail, (
        f"expected transient wave in outer ring: peak={outer_peak:.4g}, tail={outer_tail:.4g}"
    )

    # Linearity / polarity asymmetry must be small in the 0.02 um small-poke regime
    asym_ratio = float(np.linalg.norm(asym_wc[q0:]) / np.linalg.norm(r3_wc[q0:]))
    assert asym_ratio < 0.08, f"unexpected polarity asymmetry: {asym_ratio:.4f}"

    # --- Verify lockstep 3D RM matches wall-clock 3D RM ---
    with fits.open(out_ls) as hdul:
        r3_ls = hdul[0].data.astype(np.float64)
        hdr_ls = dict(hdul[0].header)
    cnt_ls = fits.getdata(work_dir / "resp3D_ls_cnt.fits")
    stat_ls = fits.getdata(work_dir / "resp3D_ls_static.fits").astype(np.float64)

    assert hdr_ls["LOCKSTEP"] == 1
    assert r3_ls.shape == r3_wc.shape
    # pokemode=1 executes 2 transitions per (mode, phase) -> exact count 2 in every post-poke bin
    assert np.all(cnt_ls[q0:] == 2), f"lockstep counts not uniformly 2: min={cnt_ls[q0:].min()}"

    # Correlation between wall-clock (pokemode=0) and lockstep (pokemode=1) full 3D tensors
    corr_3d = float(np.corrcoef(r3_wc[q0:].ravel(), r3_ls[q0:].ravel())[0, 1])
    assert corr_3d > 0.99, f"wall-clock vs lockstep 3D correlation too low: {corr_3d:.5f}"

    # --- Verify wall-clock vs lockstep static tails & cacaoac-measlinresp 2D RM parity ---
    wc_ls_stat_err = float(np.linalg.norm(stat_wc - stat_ls) / np.linalg.norm(stat_ls))
    assert wc_ls_stat_err < 0.005, f"stat_wc vs stat_ls rel_err={wc_ls_stat_err:.5f}"

    lin_2d = fits.getdata(out_lin).astype(np.float64)  # (3, 64, 64)
    lin_masked = lin_2d[:, mask_2d]

    for label, stat_rm in (("wall-clock", stat_wc), ("lockstep", stat_ls)):
        rel_err = float(np.linalg.norm(stat_rm - lin_masked) / np.linalg.norm(lin_masked))
        assert rel_err < 0.01, f"{label} static tail vs measlinresp rel_err={rel_err:.4f}"

    # Print diagnostic summary when run with pytest -s
    print(
        f"\n[measdynresp] WFSFREQ={hdr_wc['WFSFREQ']:.2f} Hz, dt={hdr_wc['DT_SEC']*1e6:.1f} us, "
        f"jitter={hdr_wc['JITTERUS']:.2f} us, ndrop={hdr_wc['NDROP']}, "
        f"wave_delay={t_outer - t_inner:.2f} bins, outer_peak/tail={outer_peak/outer_tail:.2f}x, "
        f"wc_vs_ls_corr={corr_3d:.5f}, stat_wc_vs_ls={wc_ls_stat_err:.5f}, asym={asym_ratio:.4f}"
    )


def test_measdynresp_early_stop_and_normalize(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Verify early milk-fps-runstop writes partial bit-reversed 3D cube and zeroes DM."""
    shm_dir, work_dir, env = shm_sandbox
    csim_dir = work_dir / "csim"
    bench_cfg = work_dir / "plate.bench"
    inmodes = work_dir / "poke3.fits"
    out_dir = work_dir / "early_out"
    out_cube = out_dir / "resp3D.fits"
    dm_end = work_dir / "dm_end_early.fits"

    bench_cfg.write_text(PLATE_BENCH_TEMPLATE, encoding="utf-8")
    _write_test_poke_modes(inmodes)

    script = f"""
set -euo pipefail
source "{repo_root}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{csim_dir}"

cleanup() {{
    milk-fps-rm -f -q mdr_early >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy \\
    --workdir "{csim_dir}" \\
    --config "{bench_cfg}" \\
    --mode fused --no-view >/dev/null
milk-stream-wait -q -t 15 csim_wfs:64x64 dm00disp:12x12

milk-fps-init -q mdr_early cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr_early.streamin=dm00disp \\
    mdr_early.streamout=csim_wfs \\
    mdr_early.inmodes="{inmodes}" \\
    mdr_early.outcube="{out_cube}" \\
    mdr_early.outdir="{out_dir}" \\
    mdr_early.ampl=0.02 \\
    mdr_early.normalize=ON \\
    mdr_early.timing.WFSfrequ=400.0 \\
    mdr_early.timing.frameratewait=0.2 \\
    mdr_early.timing.NBsubfr=8 \\
    mdr_early.timing.NBrespfr=12 \\
    mdr_early.timing.NBprefr=2 \\
    mdr_early.timing.NBsettlefr=2 \\
    mdr_early.timing.NBcycle=4 \\
    mdr_early.pokemode=2 \\
    mdr_early.phaseorder=0 \\
    mdr_early.procinfo.loopcntMax=1
milk-fps-runstart -q mdr_early

# Wait until at least 2 bit-reversed phases finish (~1.8 s), then stop early
sleep 2.2
milk-fps-runstop -q mdr_early
milk-fps-wait -q -t 15 mdr_early
milk-fps-rm -f -q mdr_early

milk-fpsexec-iofits-saveFITS --no-procinfo -n snapdm2 exec dm00disp "!{dm_end}" >/dev/null
cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null
"""
    res = subprocess.run(
        ["bash", "-c", script],
        cwd=work_dir,
        env=env,
        timeout=90,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    assert float(np.max(np.abs(fits.getdata(dm_end)))) == 0.0
    assert out_cube.is_file()
    assert (out_dir / "resp3D_cnt.fits").is_file()
    assert (out_dir / "resp3D_static.fits").is_file()

    with fits.open(out_cube) as hdul:
        cube = hdul[0].data.astype(np.float64)
        hdr = dict(hdul[0].header)
    cnt = fits.getdata(out_dir / "resp3D_cnt.fits")  # (N_t, N_in)
    q0 = int(hdr["Q0_BIN"])

    assert cube.shape == (q0 + 12 * 8, 3, 64 * 64)
    assert int(hdr["NCYCLE"]) < 4  # stopped before completing all 4 cycles
    # Every mode must already have populated bins across the window thanks to bit-reversed outer
    for m in range(3):
        assert int((cnt[q0:, m] > 0).sum()) >= 12, f"mode {m} missing partial coverage"
    assert float(np.max(np.abs(cube[q0:]))) > 0.0

