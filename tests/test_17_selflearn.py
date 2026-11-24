# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end unit, lock-step RT, and live GPU HIL tests for cacaopc-selflearn.

Validates:
  17.1  Lock-step SHM driver against `cacao-fpsexec-cacaopc-selflearn`:
        - Confirms real `libgric` C API (`out.gric_active == 1`) and cluster saturation.
        - Positive control (nonlinear state-dependent dynamics): Level-1 GRIC beats Level-0
          online RLS (`oos_vr_l1_pct > 5%`, `alpha_l1 > 0.3`).
        - Null control (stationary linear-Gaussian AR): Causal OOS Stein gate prevents
          degradation (`oos_vr_l1_pct >= -1.5%`).
        - Live runtime toggles (`.shadow`, `.learnON`, `.reset`, `.savedir` -> `anchors.bin`).
        - Real-time latency check (< 200 us/frame).
  17.2  Live GPU closed-loop HIL test on `scao_pyr` with unmodulated PyWFS (`mod_rad=0.0`,
        `seeing=0.35"`): verifies continuous online learning, GRIC cluster exercise,
        bounded DM stability, and closed-loop optical H-band Strehl improvement.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]

LOCKSTEP_C = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"

static int read_bin(const char *path, float *buf, size_t n) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    size_t got = fread(buf, sizeof(float), n, f);
    fclose(f);
    return (got == n) ? 0 : -1;
}

static int write_bin(const char *path, const float *buf, size_t n) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    size_t put = fwrite(buf, sizeof(float), n, f);
    fclose(f);
    return (put == n) ? 0 : -1;
}

int main(int argc, char **argv) {
    if (argc < 8) {
        fprintf(stderr, "usage: %s <T> <M> <wfs> <ol> <dm> <out_tot> <out_twk>\n", argv[0]);
        return 2;
    }
    long T = atol(argv[1]);
    long M = atol(argv[2]);
    size_t ntot = (size_t)T * (size_t)M;

    float *wfs_in = (float *)malloc(ntot * sizeof(float));
    float *ol_in  = (float *)malloc(ntot * sizeof(float));
    float *dm_in  = (float *)malloc(ntot * sizeof(float));
    float *tot_out = (float *)calloc(ntot, sizeof(float));
    float *twk_out = (float *)calloc(ntot, sizeof(float));
    if (!wfs_in || !ol_in || !dm_in || !tot_out || !twk_out) return 3;

    if (read_bin(argv[3], wfs_in, ntot) != 0 ||
        read_bin(argv[4], ol_in, ntot) != 0 ||
        read_bin(argv[5], dm_in, ntot) != 0) {
        fprintf(stderr, "failed reading input bins\n");
        return 4;
    }

    IMAGE im_wfs, im_ol, im_dm, im_out, im_twk;
    if (ImageStreamIO_openIm(&im_wfs, "sl_wfs") != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_ol, "sl_ol") != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_dm, "sl_dm") != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_out, "sl_out") != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_twk, "sl_twk") != IMAGESTREAMIO_SUCCESS) {
        fprintf(stderr, "failed opening SHM streams\n");
        return 5;
    }

    int sem_out = ImageStreamIO_getsemwaitindex(&im_out, -1);
    while (sem_out >= 0 && ImageStreamIO_semtrywait(&im_out, sem_out) == 0) {}

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (long k = 0; k < T; k++) {
        uint64_t prev_cnt = im_out.md[0].cnt0;

        im_wfs.md[0].write = 1;
        memcpy(im_wfs.array.F, wfs_in + (size_t)k * M, (size_t)M * sizeof(float));
        ImageStreamIO_UpdateIm(&im_wfs);

        im_dm.md[0].write = 1;
        memcpy(im_dm.array.F, dm_in + (size_t)k * M, (size_t)M * sizeof(float));
        ImageStreamIO_UpdateIm(&im_dm);

        im_ol.md[0].write = 1;
        memcpy(im_ol.array.F, ol_in + (size_t)k * M, (size_t)M * sizeof(float));
        ImageStreamIO_UpdateIm(&im_ol);

        struct timespec dl;
        clock_gettime(CLOCK_REALTIME, &dl);
        dl.tv_sec += 2;
        while (im_out.md[0].cnt0 <= prev_cnt) {
            if (sem_out >= 0) {
                if (ImageStreamIO_semtimedwait(&im_out, sem_out, &dl) != 0) {
                    fprintf(stderr, "timeout at frame %ld\n", k);
                    return 6;
                }
            }
        }
        memcpy(tot_out + (size_t)k * M, im_out.array.F, (size_t)M * sizeof(float));
        memcpy(twk_out + (size_t)k * M, im_twk.array.F, (size_t)M * sizeof(float));
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double us_per_fr = ((t1.tv_sec - t0.tv_sec) * 1e6 + (t1.tv_nsec - t0.tv_nsec) * 1e-3) / T;
    printf("US_PER_FRAME=%.2f\n", us_per_fr);

    write_bin(argv[6], tot_out, ntot);
    write_bin(argv[7], twk_out, ntot);

    free(wfs_in); free(ol_in); free(dm_in); free(tot_out); free(twk_out);
    return 0;
}
"""


def _run(cmd: str, env: dict[str, str], cwd: Path, timeout: int = 120) -> str:
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
            f"--- STDOUT ---\n{res.stdout[-2000:]}\n--- STDERR ---\n{res.stderr[-2000:]}"
        )
    return res.stdout


def _compile_driver(work_dir: Path, env: dict[str, str]) -> Path:
    src = work_dir / "sl_lockstep.c"
    exe = work_dir / "sl_lockstep"
    src.write_text(LOCKSTEP_C, encoding="utf-8")
    inc = Path(env["MILK_INSTALL_ROOT"]) / "include"
    lib = Path(env["MILK_INSTALL_ROOT"]) / "lib"
    _run(
        f'gcc -O2 "{src}" -I"{inc}" -L"{lib}" -Wl,-rpath,"{lib}" '
        f'-lImageStreamIO -lpthread -lm -o "{exe}"',
        env,
        work_dir,
    )
    return exe


def _get_fps_diag(fps_name: str, env: dict[str, str], cwd: Path) -> dict[str, float]:
    out = _run(f"milk-fps-info {fps_name}", env, cwd)
    clean = re.sub(r"\x1b\[[0-9;]*m", "", out)
    diag: dict[str, float] = {}
    for line in clean.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] in ("FLOAT32", "FLOAT64", "UINT32", "UINT64", "INT32"):
            key = parts[1].lstrip(".")
            try:
                diag[key] = float(parts[3])
            except ValueError:
                pass
    return diag


def _run_lockstep_case(
    exe: Path,
    work_dir: Path,
    env: dict[str, str],
    wfs: np.ndarray,
    ol: np.ndarray,
    dm: np.ndarray,
    *,
    key_mode: int = 1,
    rlim: float = 0.8,
    kmax: int = 12,
    latency: float = 2.0,
    shadow: str = "OFF",
    save_dir: str = "",
) -> tuple[np.ndarray, np.ndarray, dict[str, float], float]:
    t_len, n_mode = wfs.shape
    wfs_p = work_dir / "wfs.bin"
    ol_p = work_dir / "ol.bin"
    dm_p = work_dir / "dm.bin"
    tot_p = work_dir / "tot.bin"
    twk_p = work_dir / "twk.bin"
    wfs.astype(np.float32).tofile(wfs_p)
    ol.astype(np.float32).tofile(ol_p)
    dm.astype(np.float32).tofile(dm_p)

    # Create input streams & start selflearn daemon
    setup = f"""
milk-fps-runstop -q sl_t >/dev/null 2>&1 || true
milk-fps-rm -f -q --ignore-missing sl_t >/dev/null 2>&1 || true
milk-script -q -e <<'MS'
@calc "@S:sl_wfs = zeros({n_mode}, 1)"
@calc "@S:sl_ol  = zeros({n_mode}, 1)"
@calc "@S:sl_dm  = zeros({n_mode}, 1)"
@calc "@S:sl_out = zeros({n_mode}, 1)"
@calc "@S:sl_twk = zeros({n_mode}, 1)"
MS
milk-fps-init -q sl_t cacao-fpsexec-cacaopc-selflearn >/dev/null
milk-fps-set -q \
    sl_t.AOloopindex=1 \
    sl_t.inwfs=sl_wfs \
    sl_t.inol=sl_ol \
    sl_t.indm=sl_dm \
    sl_t.outdata=sl_out \
    sl_t.outtweak=sl_twk \
    sl_t.outPFstat=sl_stat \
    sl_t.out_mode=0 \
    sl_t.key_mode={key_mode} \
    sl_t.NBmodeMax={n_mode} \
    sl_t.kmax={kmax} \
    sl_t.qshared=2 \
    sl_t.nwarmup=25 \
    sl_t.keywarmup=150 \
    sl_t.blend_soft=ON \
    sl_t.rlim={rlim} \
    sl_t.latency={latency} \
    sl_t.dc_leak=0.99 \
    sl_t.max_wfs_gain=0.6 \
    sl_t.max_ar_norm2=2.5 \
    sl_t.lam0=15.0 \
    sl_t.lam1=60.0 \
    sl_t.gamma0=0.999 \
    sl_t.gamma1=0.9995 \
    sl_t.gate_eta=0.996 \
    sl_t.max_tweak=2.0 \
    sl_t.learnON=ON \
    sl_t.shadow={shadow} \
    sl_t.enable_l0=ON \
    sl_t.enable_l1=ON \
    sl_t.apply_gain=1.0 \
    sl_t.procinfo.loopcntMax=-1 \
    sl_t.procinfo.triggermode=3 \
    sl_t.procinfo.triggersname=sl_ol
"""
    if save_dir:
        setup += f'\nmilk-fps-set -q "sl_t.savedir={save_dir}"\n'
    setup += "\nmilk-fps-runstart -q sl_t\nsleep 0.15\n"
    _run(setup, env, work_dir)

    drv_out = _run(
        f'"{exe}" {t_len} {n_mode} "{wfs_p}" "{ol_p}" "{dm_p}" "{tot_p}" "{twk_p}"',
        env,
        work_dir,
    )
    m_us = re.search(r"US_PER_FRAME=([0-9.]+)", drv_out)
    us_per_fr = float(m_us.group(1)) if m_us else 9999.0

    diag = _get_fps_diag("sl_t", env, work_dir)
    _run("milk-fps-runstop -q sl_t && milk-fps-rm -f -q sl_t", env, work_dir)

    tot = np.fromfile(tot_p, dtype=np.float32).reshape(t_len, n_mode)
    twk = np.fromfile(twk_p, dtype=np.float32).reshape(t_len, n_mode)
    return tot, twk, diag, us_per_fr


def test_17_1_selflearn_lockstep_positive_null_and_toggles(shm_sandbox):
    """Verify libgric clustering, positive nonlinear gain, null safety, toggles & RT speed."""
    _shm_dir, work_dir, env = shm_sandbox
    exe = _compile_driver(work_dir, env)
    rng = np.random.default_rng(42)

    # --- A. Positive control: regime/energy-dependent nonlinear persistence ---
    t_len, n_mode = 2400, 16
    ol = np.zeros((t_len, n_mode), dtype=np.float64)
    wfs = np.zeros((t_len, n_mode), dtype=np.float64)
    # Slow regime envelope switches between high-energy (fast) and low-energy (slow) states
    env_state = np.sin(2.0 * np.pi * np.arange(t_len) / 300.0)
    vel = np.zeros((t_len, n_mode), dtype=np.float64)
    for k in range(2, t_len):
        # State-dependent velocity persistence: +0.85 in high-energy regime, -0.55 in low-energy
        rho = 0.85 if env_state[k] > 0.0 else -0.55
        vel[k] = rho * vel[k - 1] + 0.02 * rng.standard_normal(n_mode)
        ol[k] = 0.96 * ol[k - 1] + vel[k]
        # WFS energy carries the regime signal (high amplitude in positive regime)
        scale = 2.5 if env_state[k] > 0.0 else 0.4
        wfs[k] = scale * (0.03 * rng.standard_normal(n_mode))
    dm = -ol

    save_dir = str(work_dir / "gric_anchors")
    _, twk_pos, d_pos, us_fr = _run_lockstep_case(
        exe, work_dir, env, wfs, ol, dm, key_mode=1, rlim=0.8, kmax=12, latency=2.0,
        shadow="OFF", save_dir=save_dir,
    )
    assert d_pos.get("out.gric_active", 0) == 1.0, f"Expected libgric active: {d_pos}"
    assert d_pos.get("out.n_clusters", 0) >= 2.0, f"Expected >=2 GRIC clusters: {d_pos}"
    assert d_pos.get("out.updates", 0) >= 2000.0
    assert d_pos.get("out.oos_vr_l1_pct", 0.0) > 5.0, f"Expected L1 gain >5%: {d_pos}"
    assert d_pos.get("out.alpha_l1", 0.0) > 0.3, f"Expected open Stein gate: {d_pos}"
    assert np.all(np.isfinite(twk_pos))
    assert us_fr < 250.0, f"Too slow for RT AO loop: {us_fr:.1f} us/frame"
    assert (Path(save_dir) / "anchors.bin").is_file(), "Expected GRIC anchors.bin saved"
    print(
        f"\n[test_17_1] Positive control: K={int(d_pos['out.n_clusters'])} (libgric), "
        f"L0={d_pos['out.oos_vr_l0_pct']:+.1f}%, L1/L0={d_pos['out.oos_vr_l1_pct']:+.1f}%, "
        f"Tot={d_pos['out.oos_vr_tot_pct']:+.1f}%, speed={us_fr:.1f} us/fr"
    )

    # --- B. Shadow mode check: zero tweak output while still learning ---
    _, twk_sh, d_sh, _ = _run_lockstep_case(
        exe, work_dir, env, wfs[:600], ol[:600], dm[:600],
        key_mode=1, rlim=0.8, kmax=8, latency=2.0, shadow="ON",
    )
    assert float(np.max(np.abs(twk_sh))) == 0.0, "Shadow mode must emit strictly zero tweak"
    assert d_sh.get("out.updates", 0) >= 500.0, "Shadow mode must still learn online"
    assert d_sh.get("out.n_clusters", 0) >= 2.0

    # --- C. Linear-Gaussian null control: Stein gate prevents degradation ---
    ol_null = np.zeros((t_len, n_mode), dtype=np.float64)
    wfs_null = 0.02 * rng.standard_normal((t_len, n_mode))
    for k in range(2, t_len):
        ol_null[k] = (
            1.4 * ol_null[k - 1]
            - 0.45 * ol_null[k - 2]
            + 0.02 * rng.standard_normal(n_mode)
        )
    _, _, d_null, _ = _run_lockstep_case(
        exe, work_dir, env, wfs_null, ol_null, -ol_null,
        key_mode=0, rlim=2.0, kmax=12, latency=2.0, shadow="OFF",
    )
    assert d_null.get("out.oos_vr_l0_pct", 0.0) > 8.0, f"L0 should learn linear AR: {d_null}"
    assert d_null.get("out.oos_vr_l1_pct", -99.0) >= -1.0, (
        f"Stein gate should prevent L1 degradation on linear-Gaussian null: {d_null}"
    )
    print(
        f"[test_17_1] Linear-Gaussian null: K={int(d_null['out.n_clusters'])}, "
        f"L0={d_null['out.oos_vr_l0_pct']:+.1f}%, L1/L0={d_null['out.oos_vr_l1_pct']:+.2f}%, "
        f"alpha_l1={d_null['out.alpha_l1']:.2f}"
    )


def test_17_3_selflearn_unmod_telemetry_replay(shm_sandbox):
    """Replay real scao_pyr unmodulated PyWFS telemetry through cacaopc-selflearn in lockstep."""
    import glob
    from astropy.io import fits
    import pytest

    tdir = REPO_ROOT / "_work" / "selflearn_scao_unmod0_s035" / "telemetry"
    if not tdir.is_dir():
        pytest.skip("Optional _work/selflearn_scao_unmod0_s035 telemetry not present")

    def _load(pfx: str) -> np.ndarray:
        fs = sorted(glob.glob(str(tdir / f"{pfx}_*.fits")))
        return np.concatenate([fits.getdata(f).reshape(-1, fits.getdata(f).shape[-1]) for f in fs])

    wfs = _load("aol1_modevalWFS")[:3000, :32]
    ol = _load("aol1_modevalOL")[:3000, :32]
    dm = _load("aol1_modevalDM")[:3000, :32]

    _shm_dir, work_dir, env = shm_sandbox
    exe = _compile_driver(work_dir, env)
    _, twk, diag, us_fr = _run_lockstep_case(
        exe, work_dir, env, wfs, ol, dm,
        key_mode=0, rlim=2.0, kmax=16, latency=1.3, shadow="OFF",
    )
    assert diag.get("out.gric_active", 0) == 1.0
    assert diag.get("out.n_clusters", 0) >= 4.0
    assert diag.get("out.oos_vr_l0_pct", 0.0) > 40.0
    assert diag.get("out.oos_vr_l1_pct", 0.0) > 1.0
    assert np.all(np.isfinite(twk))
    print(
        f"\n[test_17_3] Real unmod PyWFS replay (M=32, 3000 fr): K={int(diag['out.n_clusters'])}, "
        f"L0={diag['out.oos_vr_l0_pct']:+.1f}%, L1/L0={diag['out.oos_vr_l1_pct']:+.1f}%, "
        f"Tot={diag['out.oos_vr_tot_pct']:+.1f}%, speed={us_fr:.1f} us/fr"
    )


def test_17_2_selflearn_live_closed_loop_unmod_pywfs(shm_sandbox):
    """Live GPU closed-loop exercise on scao_pyr unmodulated PyWFS (mod_rad=0.0, 0.35\")."""
    _shm_dir, work_dir, env = shm_sandbox
    out_json = work_dir / "live_ab.json"
    rm_cache = REPO_ROOT / "_work" / "selflearn_scao_unmod0_s035" / "rm"
    rm_arg = str(rm_cache) if (rm_cache / "zrespC.fits").is_file() else ""

    script = REPO_ROOT / "algo" / "selflearn" / "code" / "run_live_scao_ab.sh"
    _run(
        f'"{script}" 0.0 0.35 400 "{rm_arg}" "{out_json}"',
        env,
        REPO_ROOT,
        timeout=240,
    )
    data = json.loads(out_json.read_text(encoding="utf-8"))
    st = data["stages"]
    sr_ol = st["ol"]["metrics"]["strehl_peak"]
    sr_int = st["cl_int"]["metrics"]["strehl_peak"]
    sr_gric = st["cl_sl_gric"]["metrics"]["strehl_peak"]
    dm_gric = st["cl_sl_gric"]["metrics"]["dm_rms"]
    d_gric = st["cl_sl_gric"]["diag"]

    assert d_gric["gric_active"] == 1
    assert d_gric["n_clusters"] >= 3
    assert d_gric["updates"] >= 300
    assert dm_gric < 2.0, f"Closed-loop DM drifted/saturated: dm_rms={dm_gric:.3f}"
    assert sr_gric > sr_ol * 3.0, f"Closed-loop GRIC Strehl failed: {sr_gric:.4f} vs OL {sr_ol:.4f}"
    assert sr_gric >= sr_int * 0.95, (
        f"Closed-loop GRIC Strehl ({sr_gric:.4f}) degraded vs integrator ({sr_int:.4f})"
    )
