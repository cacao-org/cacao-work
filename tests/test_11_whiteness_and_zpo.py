# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit & HIL tests for Phase 0b (modalwhite, modalCTRL_stats, mkEOFPF OOS) & Phase 4a (WFSzpogain).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
from astropy.io import fits


def _run(cmd: str, env: dict[str, str], cwd: Path, timeout: int = 45) -> str:
    res = subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{cmd}"],
        cwd=cwd,
        env=env,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise AssertionError(
            f"Command failed (rc={res.returncode}):\n{cmd}\n"
            f"--- STDOUT ---\n{res.stdout}\n--- STDERR ---\n{res.stderr}"
        )
    return res.stdout


def _parse_fps_info(txt: str) -> dict[str, float]:
    out: dict[str, float] = {}
    clean = re.sub(r"\x1b\[[0-9;]*m", "", txt)
    for line in clean.splitlines():
        parts = line.split()
        num_types = ("FLOAT32", "FLOAT64", "UINT32", "UINT64", "INT32", "INT64")
        if len(parts) >= 4 and parts[2] in num_types:
            key = "." + parts[1].lstrip(".")
            try:
                out[key] = float(parts[3])
            except ValueError:
                pass
    return out


_COPY_INPLACE_FN = """
copy_inplace() {
    local src_fits="$1"
    local tmp_shm="$2"
    local dst_shm="$3"
    milk-FITS2shm --no-procinfo -n "ld_${tmp_shm}" exec "${src_fits}" "@S:${tmp_shm}" >/dev/null
    milk-fps-init -q "cp_${tmp_shm}" milk-fpsexec-mem-streamcopy >/dev/null
    milk-fps-set -q \\
        "cp_${tmp_shm}.in_sname=${tmp_shm}" \\
        "cp_${tmp_shm}.out_sname=${dst_shm}" \\
        "cp_${tmp_shm}.procinfo.loopcntMax=1"
    milk-fps-runstart -q "cp_${tmp_shm}"
    milk-fps-wait -q -t 10 "cp_${tmp_shm}"
    milk-fps-rm -f -q "cp_${tmp_shm}"
}
"""


def _run_modalwhite_once(
    wfs_nm: np.ndarray,
    dm_nm: np.ndarray | None,
    work_dir: Path,
    env: dict[str, str],
    tag: str,
    latency_fr: float = 2.5,
    blocksize: int = 32,
) -> dict[str, float]:
    """Load [N, M] arrays (converted to um) into SHM and run cacao-fpsexec-modalwhite once."""
    wfs_um = (wfs_nm * 1e-3).astype(np.float32)  # FITS shape (N, M) -> SHM [M, N]
    wfs_path = work_dir / f"wfs_{tag}.fits"
    fits.writeto(wfs_path, wfs_um, overwrite=True)

    load_dm = ""
    dm_stream = "no_dm_stream"
    if dm_nm is not None:
        dm_um = (dm_nm * 1e-3).astype(np.float32)
        dm_path = work_dir / f"dm_{tag}.fits"
        fits.writeto(dm_path, dm_um, overwrite=True)
        load_dm = (
            f'milk-FITS2shm --no-procinfo -n lddm_{tag} exec '
            f'"{dm_path}" @S:aol0_dm_{tag} >/dev/null'
        )
        dm_stream = f"aol0_dm_{tag}"

    fps_name = f"mw_{tag}"
    wfs_stream = f"aol0_wfs_{tag}"
    cmd = f"""
milk-FITS2shm --no-procinfo -n ldwfs_{tag} exec "{wfs_path}" @S:{wfs_stream} >/dev/null
{load_dm}
milk-fps-init -q {fps_name} cacao-fpsexec-modalwhite
milk-fps-set -q \\
    {fps_name}.AOloopindex=0 \\
    {fps_name}.inWFSbuff={wfs_stream} \\
    {fps_name}.inDMbuff={dm_stream} \\
    {fps_name}.latency_fr={latency_fr} \\
    {fps_name}.NBwin={wfs_nm.shape[0]} \\
    {fps_name}.K_lags=16 \\
    {fps_name}.P_recov=8 \\
    {fps_name}.blocksize={blocksize} \\
    {fps_name}.procinfo.triggermode=0 \\
    {fps_name}.procinfo.loopcntMax=1
milk-fps-runstart -q {fps_name}
milk-fps-wait -q -t 20 {fps_name}
milk-fps-info {fps_name}
milk-fps-rm -f -q {fps_name}
"""
    txt = _run(cmd, env, work_dir)
    info = _parse_fps_info(txt)
    assert ".out.Q_vw_b0" in info, f"Failed to parse milk-fps-info:\n{txt}"
    return info


def test_modalwhite_synthetic_null_and_pathologies(shm_sandbox):
    """Verify Bartlett MA(d-1) null, lag, Nyquist ringing, cross-mode wind, and WFS-DM alerts."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(42)
    n, m = 2048, 64

    # 1. Spatially correlated MA(2) optimal-control null (d = 3)
    L = rng.normal(0.0, 1.0, size=(m, m))
    L /= np.linalg.norm(L, axis=1, keepdims=True)
    eps = rng.normal(0.0, 1.0, size=(n + 4, m)) @ L.T
    ma2 = eps[2 : n + 2] + eps[1 : n + 1] + eps[0:n]
    out_null = _run_modalwhite_once(ma2, None, work_dir, env, "null", latency_fr=2.5, blocksize=32)

    assert int(out_null[".out.d_ceil"]) == 3
    assert 0.65 <= out_null[".out.Q_vw_b0"] <= 1.45, f"Unexpected null Q_vw_b0: {out_null}"
    assert 0.75 <= out_null[".out.Q_xmode_b0"] <= 1.35, f"Unexpected null Q_xmode: {out_null}"
    assert out_null[".out.cliff_ratio_b0"] > 5.0
    assert out_null[".out.recov_var_pct"] < 2.0
    assert int(out_null[".out.alert_flags"]) == 0

    # 2. Under-corrected AR(1) lag + WFS-DM negative correlation (flags 0x1 | 0x8)
    ar1 = np.zeros((n, m), dtype=np.float64)
    z = rng.normal(0.0, 1.0, size=(n, m))
    for t in range(1, n):
        ar1[t] = 0.85 * ar1[t - 1] + z[t]
    dm_corr = -ar1.copy()
    out_lag = _run_modalwhite_once(ar1, dm_corr, work_dir, env, "lag", latency_fr=2.5, blocksize=32)
    assert out_lag[".out.rho_d_b0"] > 0.50
    # Theoretical Bartlett Q for AR(1) a=0.85, N=2048, d=3, K=16 is ~49.0
    assert out_lag[".out.Q_vw_b0"] > 35.0
    assert out_lag[".out.recov_var_pct"] > 20.0
    assert out_lag[".out.rwu_d_lo20"] < -0.45
    assert out_lag[".out.Q_wu_lo20"] > 20.0
    assert (int(out_lag[".out.alert_flags"]) & 0x9) == 0x9

    # 3. Period-2 Nyquist ringing / optical-gain overshoot (flag 0x2)
    ring = np.zeros((n, m), dtype=np.float64)
    z2 = rng.normal(0.0, 1.0, size=(n, m))
    for t in range(1, n):
        ring[t] = -0.65 * ring[t - 1] + z2[t]
    out_ring = _run_modalwhite_once(ring, None, work_dir, env, "ring", latency_fr=2.5, blocksize=32)
    assert out_ring[".out.rho_d_b0"] < -0.15
    assert (int(out_ring[".out.alert_flags"]) & 0x2) == 0x2

    # 4. Cross-mode frozen-flow coupling missed by diagonal whiteness (flag 0x4)
    xmode = rng.normal(0.0, 1.0, size=(n, m))
    for j in range(1, 32):
        xmode[3:, j] = 0.7 * xmode[3:, j] + 0.7 * xmode[:-3, j - 1]
    out_xm = _run_modalwhite_once(xmode, None, work_dir, env, "xm", latency_fr=2.5, blocksize=32)
    assert out_xm[".out.Q_vw_b0"] < 3.0
    assert out_xm[".out.Q_xmode_b0"] > 4.0
    assert (int(out_xm[".out.alert_flags"]) & 0x4) == 0x4


def test_modalctrl_stats_4pt_noise_fix(shm_sandbox):
    """Verify modalCTRL_stats.c line 437 4-pt noise fix (1.0x vs 0.837x) and zero-NaN clamp."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(7)
    nbmode, nsample = 16, 1024
    sigma_um = 0.10  # 100 nm per mode

    # Double-buffered [2, nsample, nbmode] in FITS (SHM [nbmode, nsample, 2])
    wfs = rng.normal(0.0, sigma_um, size=(2, nsample, nbmode)).astype(np.float32)
    # Inject pure period-2 ringing mode on mode 15 so var_4pt > var_tot (tests NaN clamp)
    t_idx = np.arange(nsample, dtype=np.float32)
    wfs[:, :, 15] = 0.05 * ((-1.0) ** t_idx)[None, :]
    dm = np.zeros_like(wfs)
    ol = wfs.copy()
    blk = np.zeros((1, nbmode), dtype=np.int32)
    blk[0, 15] = 1

    fits.writeto(work_dir / "wfs_b.fits", wfs, overwrite=True)
    fits.writeto(work_dir / "dm_b.fits", dm, overwrite=True)
    fits.writeto(work_dir / "ol_b.fits", ol, overwrite=True)
    fits.writeto(work_dir / "blk.fits", blk, overwrite=True)

    cmd = f"""
cd "{work_dir}"
milk-FITS2shm --no-procinfo -n l1 exec wfs_b.fits @S:aol0_modevalWFS_buff >/dev/null
milk-FITS2shm --no-procinfo -n l2 exec dm_b.fits  @S:aol0_modevalDM_buff  >/dev/null
milk-FITS2shm --no-procinfo -n l3 exec ol_b.fits  @S:aol0_modevalOL_buff  >/dev/null
milk-FITS2shm --no-procinfo -n l4 exec blk.fits   @S:aol0_mblk            >/dev/null
milk-fps-init -q mcs cacao-fpsexec-modalCTRLstats
milk-fps-set -q \\
    mcs.AOloopindex=0 \\
    mcs.comp.statswrite=ON \\
    mcs.procinfo.triggermode=0 \\
    mcs.procinfo.loopcntMax=1
milk-fps-runstart -q mcs
milk-fps-wait -q -t 20 mcs
milk-fps-rm -f -q mcs
"""
    _run(cmd, env, work_dir)
    stat_txt = (work_dir / "AOmodalstat.dat").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in stat_txt.splitlines() if ln.strip()]
    assert len(lines) >= 2, f"Expected 2 blocks in AOmodalstat.dat, got:\n{stat_txt}"
    # Block 0: 15 white-noise modes at 100 nm each -> expected 4-pt noise = sqrt(15)*100 = 387.3 nm
    # Buggy line 437 would give 0.837 * 387.3 = 324 nm!
    b0_fields = lines[0].split()
    b0_noise_nm = float(b0_fields[3])
    expected_nm = np.sqrt(15.0) * 100.0
    assert abs(b0_noise_nm - expected_nm) / expected_nm < 0.05, (
        f"4-pt noise {b0_noise_nm:.2f} nm vs expected {expected_nm:.2f} nm\n{stat_txt}"
    )
    assert "nan" not in stat_txt.lower()


def test_mkeofpf_oos_logging(shm_sandbox):
    """Verify mkEOFPF strictly out-of-sample OOS RMS, variance reduction, and overfit ratio."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(123)
    nbmode, nslice = 32, 256
    # Generate strongly predictable AR(2) damped-oscillator turbulence across 4 slices (1024 frames)
    # (ZOH suffers large velocity lag; EOF beats ZOH decisively out-of-sample)
    total = nslice * 4
    ol_seq = np.zeros((total, nbmode), dtype=np.float32)
    eps = rng.normal(0.0, 0.02, size=(total, nbmode)).astype(np.float32)
    for t in range(2, total):
        ol_seq[t] = 1.75 * ol_seq[t - 1] - 0.85 * ol_seq[t - 2] + eps[t]

    for i in range(4):
        sl = ol_seq[i * nslice : (i + 1) * nslice]
        fits.writeto(work_dir / f"sl{i}.fits", sl, overwrite=True)

    cmd = f"""
{_COPY_INPLACE_FN}
cd "{work_dir}"
milk-FITS2shm --no-procinfo -n l0 exec sl0.fits @S:aol0_modevalOL_buff >/dev/null
milk-fps-init -q mkpf cacao-fpsexec-cacaopc-mkEOFPF
milk-fps-set -q \\
    mkpf.AOloopindex=0 \\
    mkpf.inbuff=aol0_modevalOL_buff \\
    mkpf.outPF=aol0_eofPFmat \\
    mkpf.PForder=4 \\
    mkpf.diagorder=8 \\
    mkpf.blocksize=16 \\
    mkpf.PFlatency=2.0 \\
    mkpf.NBtrain=1024 \\
    mkpf.diagminsamples=128 \\
    mkpf.minsamples=512 \\
    mkpf.updateperiod=1 \\
    mkpf.procinfo.triggermode=3 \\
    mkpf.procinfo.triggersname=aol0_modevalOL_buff \\
    mkpf.procinfo.loopcntMax=-1
milk-fps-runstart -q mkpf
sleep 0.2
for i in 0 1 2 3; do
    copy_inplace "sl${{i}}.fits" "sltmp_${{i}}" aol0_modevalOL_buff
    sleep 0.2
done
milk-fps-info mkpf
milk-fps-runstop -q mkpf
milk-fps-wait -q -t 10 mkpf
milk-fps-rm -f -q mkpf
"""
    txt = _run(cmd, env, work_dir)
    info = _parse_fps_info(txt)
    assert info.get(".out.n_updates", 0) >= 3, f"Parsed info:\n{txt}"
    assert info[".out.rms_zoh_oos"] > 0.0
    assert info[".out.rms_pred_oos"] > 0.0
    assert info[".out.rms_pred_oos"] < info[".out.rms_zoh_oos"]
    assert info[".out.var_red_oos_pct"] > 20.0
    assert 0.5 < info[".out.overfit_ratio"] < 2.0


def test_acquirewfsim_wfszpogain_live(shm_sandbox):
    """Verify acquireWFSim .WFSzpogain live WRITERUN scaling of wfszpo without restart."""
    _shm_dir, work_dir, env = shm_sandbox
    nx, ny = 16, 16
    wfs_img = np.full((ny, nx), 100.0, dtype=np.float32)
    # Zero-sum pattern on wfszpo so compWFSnormalize preserves exact linear scaling!
    zpo_pat = np.zeros((ny, nx), dtype=np.float32)
    zpo_pat[:, : nx // 2] = 0.001
    zpo_pat[:, nx // 2 :] = -0.001
    wfs_ref = np.full((ny, nx), 1.0 / (nx * ny), dtype=np.float32)
    wfs_mask = np.ones((ny, nx), dtype=np.float32)

    fits.writeto(work_dir / "wfsim.fits", wfs_img, overwrite=True)
    fits.writeto(work_dir / "wfszpo.fits", zpo_pat, overwrite=True)
    fits.writeto(work_dir / "wfsref.fits", wfs_ref, overwrite=True)
    fits.writeto(work_dir / "wfsmask.fits", wfs_mask, overwrite=True)

    cmd = f"""
{_COPY_INPLACE_FN}
cd "{work_dir}"
milk-FITS2shm --no-procinfo -n s1 exec wfsim.fits   @S:aol0_wfsim   >/dev/null
milk-FITS2shm --no-procinfo -n s2 exec wfszpo.fits  @S:aol0_wfszpo  >/dev/null
milk-FITS2shm --no-procinfo -n s3 exec wfsref.fits  @S:aol0_wfsref  >/dev/null
milk-FITS2shm --no-procinfo -n s4 exec wfsmask.fits @S:aol0_wfsmask >/dev/null
milk-fps-init -q acq cacao-fpsexec-cacaoiot-acquireWFS
milk-fps-set -q \\
    acq.AOloopindex=0 \\
    acq.insname=aol0_wfsim \\
    acq.wfszpo=aol0_wfszpo \\
    acq.WFSnormfloor=0.0 \\
    acq.comp.darksub=OFF \\
    acq.comp.WFSnormalize=ON \\
    acq.comp.WFSrefsub=ON \\
    acq.comp.WFSsigav=OFF \\
    acq.comp.WFSrefc=ON \\
    acq.WFSrefcmult=1.0 \\
    acq.WFSrefcgain=0.0 \\
    acq.WFSzpogain=1.0 \\
    acq.procinfo.triggermode=3 \\
    acq.procinfo.triggersname=aol0_wfsim \\
    acq.procinfo.loopcntMax=-1
milk-fps-runstart -q acq
sleep 0.2
# Trigger 2 frames at WFSzpogain=1.0 (frame 1 updates wfsrefc off critical path; frame 2 applies it)
copy_inplace wfsim.fits wfstrig1a aol0_wfsim
sleep 0.1
copy_inplace wfsim.fits wfstrig1b aol0_wfsim
sleep 0.1
milk-fpsexec-iofits-saveFITS --no-procinfo -n sv1 exec aol0_imWFS2 "!imwfs2_g100.fits" >/dev/null
# Live WRITERUN change to WFSzpogain=0.70 (no restart!)
milk-fps-set -q acq.WFSzpogain=0.70
sleep 0.05
copy_inplace wfsim.fits wfstrig2a aol0_wfsim
sleep 0.1
copy_inplace wfsim.fits wfstrig2b aol0_wfsim
sleep 0.1
milk-fpsexec-iofits-saveFITS --no-procinfo -n sv2 exec aol0_imWFS2 "!imwfs2_g070.fits" >/dev/null
milk-fps-runstop -q acq
milk-fps-wait -q -t 10 acq
milk-fps-rm -f -q acq
"""
    _run(cmd, env, work_dir)
    im100 = fits.getdata(work_dir / "imwfs2_g100.fits").astype(np.float64)
    im070 = fits.getdata(work_dir / "imwfs2_g070.fits").astype(np.float64)
    # Since wfsim normalized == wfsref, imWFS2 == -WFSzpogain * zpo_pat
    assert np.max(np.abs(im100 + zpo_pat)) < 1e-6
    assert np.max(np.abs(im070 + 0.70 * zpo_pat)) < 1e-6
    ratio = float(np.median(im070 / im100))
    assert abs(ratio - 0.70) < 1e-4, f"Expected live ratio 0.70, got {ratio:.6f}"
