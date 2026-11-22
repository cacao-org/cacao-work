# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end lock-step closed-loop tests for cacao-fpsexec-modalopt + mfilt safety clamp.

Validates:
  1. Live joint per-mode (gain, leak) autotuning via cacao-fpsexec-modalopt updating
     cacao-fpsexec-mfilt over POSIX SHM (aol0_mgainfact, aol0_mmultfact) with automatic
     loopgain/loopmult reference detection across 3 distinct mode regimes:
       - Band A (m=0..7): slow Kolmogorov turbulence -> high gain, high alpha (~0.99+)
       - Band B (m=8..23): band-pass Stage-2-like turbulence -> stronger leak (lower alpha)
       - Band C (m=24..63): pure white WFS noise (faint regime) -> gain collapsed near floor,
         SNR-adaptive memory stretched (tau_C > 1.8 * tau_A), and large WFE drop vs static.
  2. Dual regime-change detector (mid-run 10x noise / flux drop), fast lag-d ringing guard
     (unmodeled 2.2x optical-gain jump keeps loop bounded), and modalfilter.c mmult<=1 clamp.
  3. Real cacaosim AO3k + SCExAO telemetry replay through compiled C binaries (when present).
"""

from __future__ import annotations

import math
from pathlib import Path
import re
import shutil
import subprocess

from astropy.io import fits
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

MOPT_LOCKSTEP_C = r"""
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"

static int read_bin_f32(const char *path, float *buf, size_t n) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    size_t got = fread(buf, sizeof(float), n, f);
    fclose(f);
    return (got == n) ? 0 : -1;
}

static int write_bin_f32(const char *path, const float *buf, size_t n) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    size_t put = fwrite(buf, sizeof(float), n, f);
    fclose(f);
    return (put == n) ? 0 : -1;
}

/*
 * Lock-step closed-loop driver for mfilt + optional modalopt with fractional delay
 * H(z) = (1 - lat_frac) * z^{-lat_int} + lat_frac * z^{-(lat_int + 1)} and time-varying
 * per-frame optical-gain multiplier og_step[k].
 *
 * Usage:
 *   mopt_lockstep <n_mode> <n_step> <tb_sz> <lat_fr> <wait_mopt>
 *                 <phi.bin> <noise.bin> <og_step.bin>
 *                 <res_out.bin> <g_snap.bin> <a_snap.bin> <mopt_final.bin>
 */
int main(int argc, char **argv) {
    if (argc < 13) return 2;
    int   n_mode    = atoi(argv[1]);
    int   n_step    = atoi(argv[2]);
    int   tb_sz     = atoi(argv[3]);
    float lat_fr    = (float)atof(argv[4]);
    int   wait_mopt = atoi(argv[5]);

    int   lat_i = (int)floorf(lat_fr);
    float lat_f = lat_fr - (float)lat_i;
    float w0    = 1.0f - lat_f;
    int   L     = lat_i + 3;

    float *phi     = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *noise   = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *og_step = (float *)calloc((size_t)n_step, sizeof(float));
    float *res_log = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    int    n_sl    = n_step / tb_sz;
    float *g_log   = (float *)calloc((size_t)(n_sl > 0 ? n_sl : 1) * n_mode, sizeof(float));
    float *a_log   = (float *)calloc((size_t)(n_sl > 0 ? n_sl : 1) * n_mode, sizeof(float));
    float *u_hist  = (float *)calloc((size_t)L * n_mode, sizeof(float));
    float *m_final = (float *)calloc((size_t)5 * n_mode, sizeof(float));
    if (!phi || !noise || !og_step || !res_log || !g_log || !a_log || !u_hist || !m_final)
        return 3;

    if (read_bin_f32(argv[6], phi, (size_t)n_step * n_mode) != 0) return 4;
    if (read_bin_f32(argv[7], noise, (size_t)n_step * n_mode) != 0) return 5;
    if (read_bin_f32(argv[8], og_step, (size_t)n_step) != 0) return 6;

    IMAGE im_wfs, im_dm, im_ol, im_mg, im_mm;
    IMAGE im_og, im_oa, im_osnr, im_otau, im_orng;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalWFS", &im_wfs) != 0) return 10;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalDM", &im_dm) != 0) return 11;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalOL", &im_ol) != 0) return 12;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mgain", &im_mg) != 0) return 13;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mmult", &im_mm) != 0) return 14;
    int sem_mopt = -1;
    if (wait_mopt) {
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mopt_gain", &im_og) != 0) return 15;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mopt_mult", &im_oa) != 0) return 16;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mopt_snr", &im_osnr) != 0) return 17;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mopt_taumem", &im_otau) != 0)
            return 18;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mopt_ring", &im_orng) != 0) return 19;
        sem_mopt = ImageStreamIO_getsemwaitindex(&im_og, -1);
        ImageStreamIO_semflush(&im_og, sem_mopt);
    }

    int sem_dm = ImageStreamIO_getsemwaitindex(&im_dm, -1);
    int sem_ol = ImageStreamIO_getsemwaitindex(&im_ol, -1);
    ImageStreamIO_semflush(&im_dm, sem_dm);
    ImageStreamIO_semflush(&im_ol, sem_ol);

    int head   = 0;
    int sl_idx = 0;
    for (int k = 0; k < n_step; k++) {
        int s0 = (head - lat_i + L) % L;
        int s1 = (head - lat_i - 1 + L) % L;
        const float *u0 = &u_hist[(size_t)s0 * n_mode];
        const float *u1 = &u_hist[(size_t)s1 * n_mode];
        float ogk = og_step[k];

        im_wfs.md[0].write = 1;
        for (int m = 0; m < n_mode; m++) {
            float u_eff = w0 * u0[m] + lat_f * u1[m];
            /* True noiseless sky residual: phi + u_eff (mfilt integrates -mg * w) */
            float res_true = phi[(size_t)k * n_mode + m] + u_eff;
            res_log[(size_t)k * n_mode + m] = res_true;
            im_wfs.array.F[m] = ogk * res_true + noise[(size_t)k * n_mode + m];
        }
        im_wfs.md[0].cnt0++;
        im_wfs.md[0].write = 0;
        ImageStreamIO_sempost(&im_wfs, -1);

        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += 5;
        if (ImageStreamIO_semtimedwait(&im_dm, sem_dm, &ts) != 0) return 20;
        if (ImageStreamIO_semtimedwait(&im_ol, sem_ol, &ts) != 0) return 21;

        memcpy(&u_hist[(size_t)head * n_mode], im_dm.array.F, sizeof(float) * (size_t)n_mode);
        head = (head + 1) % L;

        if (((k + 1) % tb_sz) == 0 && sl_idx < n_sl) {
            if (wait_mopt) {
                clock_gettime(CLOCK_REALTIME, &ts);
                ts.tv_sec += 5;
                if (ImageStreamIO_semtimedwait(&im_og, sem_mopt, &ts) != 0) return 22;
            }
            memcpy(&g_log[(size_t)sl_idx * n_mode], im_mg.array.F,
                   sizeof(float) * (size_t)n_mode);
            memcpy(&a_log[(size_t)sl_idx * n_mode], im_mm.array.F,
                   sizeof(float) * (size_t)n_mode);
            sl_idx++;
        }
    }

    if (wait_mopt) {
        memcpy(&m_final[(size_t)0 * n_mode], im_og.array.F, sizeof(float) * (size_t)n_mode);
        memcpy(&m_final[(size_t)1 * n_mode], im_oa.array.F, sizeof(float) * (size_t)n_mode);
        memcpy(&m_final[(size_t)2 * n_mode], im_osnr.array.F, sizeof(float) * (size_t)n_mode);
        memcpy(&m_final[(size_t)3 * n_mode], im_otau.array.F, sizeof(float) * (size_t)n_mode);
        memcpy(&m_final[(size_t)4 * n_mode], im_orng.array.F, sizeof(float) * (size_t)n_mode);
    }

    write_bin_f32(argv[9], res_log, (size_t)n_step * n_mode);
    write_bin_f32(argv[10], g_log, (size_t)sl_idx * n_mode);
    write_bin_f32(argv[11], a_log, (size_t)sl_idx * n_mode);
    write_bin_f32(argv[12], m_final, (size_t)5 * n_mode);
    free(phi); free(noise); free(og_step); free(res_log);
    free(g_log); free(a_log); free(u_hist); free(m_final);
    return 0;
}
"""

MFILT_CLAMP_C = r"""
#include <stdio.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"

int main(void) {
    IMAGE im_wfs, im_dm, im_mg, im_mm, im_mgf, im_mmf;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalWFS", &im_wfs) != 0) return 10;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalDM", &im_dm) != 0) return 11;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mgain", &im_mg) != 0) return 12;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mmult", &im_mm) != 0) return 13;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mgainfact", &im_mgf) != 0) return 14;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_mmultfact", &im_mmf) != 0) return 15;

    uint32_t n = im_wfs.md[0].size[0];
    int sem_dm = ImageStreamIO_getsemwaitindex(&im_dm, -1);
    ImageStreamIO_semflush(&im_dm, sem_dm);

    im_mgf.md[0].write = 1;
    im_mmf.md[0].write = 1;
    for (uint32_t i = 0; i < n; i++) {
        im_mgf.array.F[i] = 20.0f;
        im_mmf.array.F[i] = 1.5f;
    }
    im_mgf.md[0].cnt0++;
    im_mgf.md[0].write = 0;
    im_mmf.md[0].cnt0++;
    im_mmf.md[0].write = 0;

    im_wfs.md[0].write = 1;
    for (uint32_t i = 0; i < n; i++) im_wfs.array.F[i] = 0.0f;
    im_wfs.md[0].cnt0++;
    im_wfs.md[0].write = 0;
    ImageStreamIO_sempost(&im_wfs, -1);

    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += 5;
    if (ImageStreamIO_semtimedwait(&im_dm, sem_dm, &ts) != 0) return 20;

    for (uint32_t i = 0; i < n; i++) {
        if (im_mm.array.F[i] > 1.00001f || im_mm.array.F[i] < 0.0f) return 30;
        if (im_mg.array.F[i] > 2.00001f || im_mg.array.F[i] < 0.0f) return 31;
    }
    return 0;
}
"""


def _run(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int = 30) -> str:
    res = subprocess.run(
        cmd, cwd=cwd, env=env, timeout=timeout, check=True, capture_output=True, text=True
    )
    return res.stdout


def _compile_c(code: str, name: str, work_dir: Path, env: dict[str, str]) -> Path:
    src = work_dir / f"{name}.c"
    exe = work_dir / name
    src.write_text(code, encoding="utf-8")
    inc = Path(env["MILK_INSTALL_ROOT"]) / "include"
    lib = Path(env["MILK_INSTALL_ROOT"]) / "lib"
    cc = shutil.which("gcc") or "cc"
    subprocess.run(
        [
            cc, "-O2", "-Wall", "-Wextra", str(src), "-o", str(exe),
            f"-I{inc}", f"-L{lib}", f"-Wl,-rpath,{lib}",
            "-lImageStreamIO", "-lm", "-lpthread",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return exe


def _create_f32_shm(name: str, n_mode: int, cwd: Path, env: dict[str, str]) -> None:
    zname = f"_z_{name}.fits"
    fits.writeto(cwd / zname, np.zeros((1, n_mode), dtype=np.float32), overwrite=True)
    _run(
        ["milk-FITS2shm", "--no-procinfo", "-n", "ldz", "exec", zname, f"@S:{name}"],
        cwd=cwd,
        env=env,
    )


def _parse_fps_info(text: str) -> dict[str, float]:
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    out: dict[str, float] = {}
    for line in clean.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1].startswith((".", "out.")):
            try:
                out[parts[1].lstrip(".")] = float(parts[3])
            except ValueError:
                pass
    return out


def _make_mixed_regime_signals(
    n_step: int, n_mode: int, fs_hz: float, seed: int = 7
) -> tuple[np.ndarray, np.ndarray]:
    """Generate 3-band synthetic modal turbulence + WFS noise:
      - Band A (0..7):   slow Kolmogorov-like AR(2) turbulence (high SNR, strong DC/low-f)
      - Band B (8..23):  band-pass ~65 Hz turbulence (Stage-2-like, near-zero DC)
      - Band C (24..63): pure white WFS measurement noise (zero signal, faint high-order)
    """
    rng = np.random.default_rng(seed)
    phi = np.zeros((n_step, n_mode), dtype=np.float32)
    noise = np.zeros((n_step, n_mode), dtype=np.float32)

    for m in range(8):
        p = 0.996 - 0.0005 * m
        x = np.zeros(n_step, dtype=np.float64)
        exc = rng.standard_normal(n_step) * 0.025
        for k in range(2, n_step):
            x[k] = 1.65 * p * x[k - 1] - 0.65 * p * p * x[k - 2] + exc[k]
        x += 0.35 * (1.0 if (m % 2 == 0) else -1.0)
        phi[:, m] = x.astype(np.float32)
        noise[:, m] = (rng.standard_normal(n_step) * 0.015).astype(np.float32)

    w0 = 2.0 * math.pi * 65.0 / fs_hz
    r_bp = 0.88
    a1 = 2.0 * r_bp * math.cos(w0)
    a2 = -r_bp * r_bp
    for m in range(8, 24):
        x = np.zeros(n_step, dtype=np.float64)
        exc = rng.standard_normal(n_step) * 0.045
        for k in range(2, n_step):
            x[k] = a1 * x[k - 1] + a2 * x[k - 2] + exc[k]
        phi[:, m] = x.astype(np.float32)
        noise[:, m] = (rng.standard_normal(n_step) * 0.025).astype(np.float32)

    for m in range(24, n_mode):
        noise[:, m] = (rng.standard_normal(n_step) * 0.14).astype(np.float32)

    return phi, noise


def _run_lockstep_case(
    work_dir: Path,
    env: dict[str, str],
    exe: Path,
    phi: np.ndarray,
    noise: np.ndarray,
    og_step: np.ndarray,
    lat_fr: float,
    tb_sz: int,
    fs_hz: float,
    enable_modalopt: bool,
    apply_gain: bool = True,
    apply_mult: bool = True,
    loopgain: float = 0.35,
    loopmult: float = 0.98,
    alpha_min: float = 0.85,
    extra_mopt_params: list[str] | None = None,
) -> dict:
    n_step, n_mode = phi.shape
    case_dir = work_dir / ("mopt_on" if enable_modalopt else "mopt_off")
    case_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["milk-fps-runstop", "-q", "modalopt-0", "mfilt-0"],
        cwd=case_dir, env=env, check=False, capture_output=True,
    )
    subprocess.run(
        ["milk-fps-rm", "-f", "-q", "--ignore-missing", "modalopt-0", "mfilt-0"],
        cwd=case_dir, env=env, check=False, capture_output=True,
    )
    subprocess.run(
        ["milk-stream-rm", "-r", "-f", "-q", "--ignore-missing", "^aol0_"],
        cwd=case_dir, env=env, check=False, capture_output=True,
    )

    _create_f32_shm("aol0_modevalWFS", n_mode, case_dir, env)
    _run(["milk-fps-init", "-q", "mfilt-0", "cacao-fpsexec-mfilt"], cwd=case_dir, env=env)
    _run(
        [
            "milk-fps-set", "-q",
            "mfilt-0.AOloopindex=0",
            "mfilt-0.inmval=aol0_modevalWFS",
            "mfilt-0.outmval=aol0_modevalDM",
            "mfilt-0.loopON=ON",
            f"mfilt-0.loopgain={loopgain}",
            f"mfilt-0.loopmult={loopmult}",
            "mfilt-0.looplimit=10.0",
            "mfilt-0.comp.OLmodes=ON",
            "mfilt-0.comp.WFSfact=1.0",
            f"mfilt-0.comp.latencyhardwfr={lat_fr}",
            "mfilt-0.comp.latencysoftwfr=0.0",
            "mfilt-0.comp.tbuff=ON",
            f"mfilt-0.comp.tbuffsize={tb_sz}",
            "mfilt-0.PF.enable=OFF",
            "mfilt-0.procinfo.loopcntMax=-1",
            "mfilt-0.procinfo.triggermode=3",
            "mfilt-0.procinfo.triggersname=aol0_modevalWFS",
        ],
        cwd=case_dir,
        env=env,
    )
    _run(["milk-fps-runstart", "-q", "mfilt-0"], cwd=case_dir, env=env)
    _run(
        ["milk-stream-wait", "-q", "-t", "10", f"aol0_modevalOL_buff:{n_mode}x{tb_sz}x2"],
        cwd=case_dir, env=env,
    )

    if enable_modalopt:
        _run(["milk-fps-init", "-q", "modalopt-0", "cacao-fpsexec-modalopt"], cwd=case_dir, env=env)
        mopt_args = [
            "milk-fps-set", "-q",
            "modalopt-0.AOloopindex=0",
            "modalopt-0.inol=aol0_modevalOL_buff",
            "modalopt-0.inwfs=aol0_modevalWFS_buff",
            f"modalopt-0.fs_hz={fs_hz}",
            f"modalopt-0.latency_fr={lat_fr}",
            f"modalopt-0.alpha_min={alpha_min}",
            "modalopt-0.alpha_max=0.9995",
            "modalopt-0.g_min=0.005",
            "modalopt-0.g_max=0.80",
            "modalopt-0.tau_fast=2.0",
            "modalopt-0.tau_faint=12.0",
            "modalopt-0.eb_enable=ON",
            "modalopt-0.ring_enable=ON",
            f"modalopt-0.apply_gain={'ON' if apply_gain else 'OFF'}",
            f"modalopt-0.apply_mult={'ON' if apply_mult else 'OFF'}",
            "modalopt-0.loopgain_ref=0.0",
            "modalopt-0.loopmult_ref=0.0",
            "modalopt-0.procinfo.loopcntMax=-1",
            "modalopt-0.procinfo.triggermode=3",
            "modalopt-0.procinfo.triggersname=aol0_modevalOL_buff",
        ]
        if extra_mopt_params:
            mopt_args.extend(extra_mopt_params)
        _run(mopt_args, cwd=case_dir, env=env)
        _run(["milk-fps-runstart", "-q", "modalopt-0"], cwd=case_dir, env=env)
        _run(
            ["milk-stream-wait", "-q", "-t", "10", f"aol0_mopt_gain:{n_mode}x1"],
            cwd=case_dir, env=env,
        )

    p_phi = case_dir / "phi.bin"
    p_noi = case_dir / "noise.bin"
    p_og = case_dir / "og.bin"
    p_res = case_dir / "res.bin"
    p_g = case_dir / "g.bin"
    p_a = case_dir / "a.bin"
    p_mf = case_dir / "mopt_final.bin"
    phi.astype(np.float32).tofile(p_phi)
    noise.astype(np.float32).tofile(p_noi)
    og_step.astype(np.float32).tofile(p_og)

    subprocess.run(
        [
            str(exe), str(n_mode), str(n_step), str(tb_sz), f"{lat_fr:.4f}",
            "1" if enable_modalopt else "0",
            str(p_phi), str(p_noi), str(p_og), str(p_res), str(p_g), str(p_a), str(p_mf),
        ],
        cwd=case_dir,
        env=env,
        timeout=45,
        check=True,
    )

    out: dict = {
        "res": np.fromfile(p_res, dtype=np.float32).reshape(n_step, n_mode),
        "g_hist": np.fromfile(p_g, dtype=np.float32).reshape(-1, n_mode),
        "a_hist": np.fromfile(p_a, dtype=np.float32).reshape(-1, n_mode),
    }
    if enable_modalopt:
        mf = np.fromfile(p_mf, dtype=np.float32).reshape(5, n_mode)
        out["mopt_gain"] = mf[0]
        out["mopt_mult"] = mf[1]
        out["mopt_snr"] = mf[2]
        out["mopt_tau"] = mf[3]
        out["mopt_ring"] = mf[4]
        info = _parse_fps_info(_run(["milk-fps-info", "modalopt-0"], cwd=case_dir, env=env))
        out["n_updates"] = info.get("out.n_updates", 0.0)
        out["applied_cnt"] = info.get("out.applied_cnt", 0.0)
        out["chg_cnt"] = info.get("out.chg_cnt", 0.0)
        out["ring_cnt"] = info.get("out.ring_cnt", 0.0)
        out["solve_ms"] = info.get("out.solve_ms", 0.0)

    subprocess.run(
        ["milk-fps-runstop", "-q", "modalopt-0", "mfilt-0"],
        cwd=case_dir, env=env, check=False, capture_output=True,
    )
    return out


def test_modalopt_live_joint_gain_leak_and_faint_memory(shm_sandbox) -> None:
    """Test 1: Live mfilt + modalopt joint (g, alpha) across slow, band-pass, and faint."""
    _, work_dir, env = shm_sandbox
    exe = _compile_c(MOPT_LOCKSTEP_C, "mopt_lockstep", work_dir, env)

    n_mode = 64
    tb_sz = 256
    n_step = 4096
    fs_hz = 1000.0
    lat_fr = 2.45
    phi, noise = _make_mixed_regime_signals(n_step, n_mode, fs_hz, seed=11)
    og_step = np.ones(n_step, dtype=np.float32)

    base = _run_lockstep_case(
        work_dir, env, exe, phi, noise, og_step, lat_fr, tb_sz, fs_hz,
        enable_modalopt=False, loopgain=0.35, loopmult=0.98,
    )
    opt = _run_lockstep_case(
        work_dir, env, exe, phi, noise, og_step, lat_fr, tb_sz, fs_hz,
        enable_modalopt=True, apply_gain=True, apply_mult=True,
        loopgain=0.35, loopmult=0.98, alpha_min=0.85,
    )

    assert opt["n_updates"] == n_step // tb_sz
    assert opt["applied_cnt"] == opt["n_updates"]
    assert opt["solve_ms"] < 25.0

    sl = slice(n_step // 2, n_step)
    rms_base = float(np.sqrt(np.mean(np.sum(base["res"][sl] ** 2, axis=1))))
    rms_opt = float(np.sqrt(np.mean(np.sum(opt["res"][sl] ** 2, axis=1))))
    assert rms_opt < 0.72 * rms_base, (
        f"Expected >28% WFE reduction: base={rms_base:.4f}, opt={rms_opt:.4f}"
    )

    g_live = opt["g_hist"][-1]
    a_live = opt["a_hist"][-1]
    print(
        f"\n[Test 1] rms base={rms_base:.4f} -> opt={rms_opt:.4f} "
        f"({100*(1 - rms_opt/rms_base):.1f}% drop) solve={opt['solve_ms']:.2f}ms"
    )
    print(
        f"  BandA g={np.median(g_live[:8]):.3f} a={np.median(a_live[:8]):.4f} "
        f"tau={np.median(opt['mopt_tau'][:8]):.1f}s | "
        f"BandB g={np.median(g_live[8:24]):.3f} a={np.median(a_live[8:24]):.4f} | "
        f"BandC g={np.median(g_live[24:]):.4f} tau={np.median(opt['mopt_tau'][24:]):.1f}s"
    )
    # g_hist[-1] reflects slice N-2 applied on mfilt (1 slice behind mopt_gain on last frame)
    assert np.median(np.abs(g_live - opt["mopt_gain"])) < 0.02
    assert np.median(np.abs(a_live - opt["mopt_mult"])) < 0.01

    assert float(np.median(g_live[:8])) > 0.25
    assert float(np.median(a_live[:8])) > 0.99
    assert float(np.median(g_live[8:24])) > 0.20
    assert float(np.median(a_live[8:24])) < float(np.median(a_live[:8])) - 0.02
    assert float(np.median(g_live[24:])) < 0.05

    tau_a = float(np.median(opt["mopt_tau"][:8]))
    tau_c = float(np.median(opt["mopt_tau"][24:]))
    assert tau_c > 1.8 * tau_a, f"Expected faint Band-C tau ({tau_c:.2f}s) >> Band-A ({tau_a:.2f}s)"


def test_modalopt_flux_drop_and_ringing_guard(shm_sandbox) -> None:
    """Test 2: Dual change detector on flux drop and lag-d ringing guard on 2.2x OG jump."""
    _, work_dir, env = shm_sandbox
    exe = _compile_c(MOPT_LOCKSTEP_C, "mopt_lockstep", work_dir, env)

    n_mode = 48
    tb_sz = 256
    n_step = 4096
    fs_hz = 1000.0
    lat_fr = 2.40
    rng = np.random.default_rng(29)

    phi = np.zeros((n_step, n_mode), dtype=np.float32)
    noise = np.zeros((n_step, n_mode), dtype=np.float32)
    for m in range(n_mode):
        p = 0.985
        amp = 0.04 if m < 12 else 0.015
        x = np.zeros(n_step, dtype=np.float64)
        exc = rng.standard_normal(n_step) * amp
        for k in range(1, n_step):
            x[k] = p * x[k - 1] + exc[k]
        phi[:, m] = x.astype(np.float32)
        n_amp = 0.015
        noise[:2048, m] = (rng.standard_normal(2048) * n_amp).astype(np.float32)
        noise[2048:, m] = (rng.standard_normal(n_step - 2048) * (10.0 * n_amp)).astype(np.float32)
    og_ones = np.ones(n_step, dtype=np.float32)

    res_flux = _run_lockstep_case(
        work_dir / "flux", env, exe, phi, noise, og_ones, lat_fr, tb_sz, fs_hz,
        enable_modalopt=True, apply_gain=True, apply_mult=True,
        loopgain=1.0, loopmult=1.0, alpha_min=0.90,
    )
    assert res_flux["chg_cnt"] >= 1, "Dual change detector must trigger on sudden 10x noise surge"
    g_pre = float(np.median(res_flux["g_hist"][6, 16:]))
    g_post = float(np.median(res_flux["g_hist"][11, 16:]))
    print(f"\n[Test 2a] flux drop chg={res_flux['chg_cnt']:.0f} g_hi: {g_pre:.3f} -> {g_post:.3f}")
    assert g_post < 0.60 * g_pre, f"Expected fast gain drop: {g_pre:.3f} -> {g_post:.3f}"

    noise_lo = (rng.standard_normal((n_step, n_mode)) * 0.015).astype(np.float32)
    og_jump = np.ones(n_step, dtype=np.float32)
    og_jump[1536:] = 2.20
    res_ring = _run_lockstep_case(
        work_dir / "ring", env, exe, phi, noise_lo, og_jump, lat_fr, tb_sz, fs_hz,
        enable_modalopt=True, apply_gain=True, apply_mult=True,
        loopgain=1.0, loopmult=1.0, alpha_min=0.92,
    )
    assert res_ring["ring_cnt"] > 0, "Ringing guard must trigger on unmodeled 2.2x OG jump"
    assert float(np.min(res_ring["mopt_ring"])) < 0.85
    rms_post = float(np.sqrt(np.mean(res_ring["res"][2560:] ** 2)))
    print(f"[Test 2b] 2.2x OG jump ring_cnt={res_ring['ring_cnt']:.0f} rms_post={rms_post:.4f}")
    assert math.isfinite(rms_post) and rms_post < 1.5, f"Loop blew up after OG jump: {rms_post}"


def test_modalfilter_mmult_mgain_safety_clamp(shm_sandbox) -> None:
    """Test 2c: Verify modalfilter.c clamps mmult <= 1.0 and mgain <= 2.0 on extreme factors."""
    _, work_dir, env = shm_sandbox
    exe_clamp = _compile_c(MFILT_CLAMP_C, "mfilt_clamp", work_dir, env)
    clamp_dir = work_dir / "clamp"
    clamp_dir.mkdir(parents=True, exist_ok=True)
    _create_f32_shm("aol0_modevalWFS", 16, clamp_dir, env)
    _run(["milk-fps-init", "-q", "mfilt-0", "cacao-fpsexec-mfilt"], cwd=clamp_dir, env=env)
    _run(
        [
            "milk-fps-set", "-q",
            "mfilt-0.AOloopindex=0",
            "mfilt-0.inmval=aol0_modevalWFS",
            "mfilt-0.outmval=aol0_modevalDM",
            "mfilt-0.loopON=ON",
            "mfilt-0.loopgain=0.35",
            "mfilt-0.loopmult=0.98",
            "mfilt-0.procinfo.loopcntMax=-1",
            "mfilt-0.procinfo.triggermode=3",
            "mfilt-0.procinfo.triggersname=aol0_modevalWFS",
        ],
        cwd=clamp_dir, env=env,
    )
    _run(["milk-fps-runstart", "-q", "mfilt-0"], cwd=clamp_dir, env=env)
    _run(["milk-stream-wait", "-q", "-t", "10", "aol0_mmultfact:16x1"], cwd=clamp_dir, env=env)
    subprocess.run([str(exe_clamp)], cwd=clamp_dir, env=env, timeout=15, check=True)
    subprocess.run(
        ["milk-fps-runstop", "-q", "mfilt-0"],
        cwd=clamp_dir, env=env, check=False, capture_output=True,
    )


def test_modalopt_real_cacaosim_telemetry_replay(shm_sandbox) -> None:
    """Test 3: Replay real cacaosim Stage-1 & Stage-2 PSOL through compiled mfilt + modalopt."""
    tlm_dir = REPO_ROOT / "_work" / "ao3k_scexao_tlm20s_ar16" / "telemetry"
    ol1_files = sorted(tlm_dir.glob("aol1_modevalOL_*.fits"))
    ol2_files = sorted(tlm_dir.glob("aol2_modevalOL_*.fits"))
    if not ol1_files or not ol2_files:
        pytest.skip("Logged ao3k_scexao_tlm20s_ar16 telemetry not present in _work")

    _, work_dir, env = shm_sandbox
    exe = _compile_c(MOPT_LOCKSTEP_C, "mopt_lockstep", work_dir, env)

    for stage, files, fs_hz, lat_fr, alpha_min in [
        (1, ol1_files, 1000.0, 2.68, 0.92),
        (2, ol2_files, 2000.0, 2.82, 0.85),
    ]:
        chunks = [fits.getdata(f).astype(np.float32) for f in files[:3]]
        arr = np.vstack([c[:, 0, :] if c.ndim == 3 else c for c in chunks])
        n_mode = min(128, arr.shape[1])
        n_step = 6144
        phi = arr[500 : 500 + n_step, :n_mode].copy()
        zeros = np.zeros_like(phi)
        og_ones = np.ones(n_step, dtype=np.float32)

        sub_dir = work_dir / f"real_stg{stage}"
        base = _run_lockstep_case(
            sub_dir, env, exe, phi, zeros, og_ones, lat_fr, 512, fs_hz,
            enable_modalopt=False, loopgain=0.35, loopmult=0.98,
        )
        opt = _run_lockstep_case(
            sub_dir, env, exe, phi, zeros, og_ones, lat_fr, 512, fs_hz,
            enable_modalopt=True, apply_gain=True, apply_mult=True,
            loopgain=0.35, loopmult=0.98, alpha_min=alpha_min,
        )

        sl = slice(n_step // 2, n_step)
        rms_base = float(np.sqrt(np.mean(np.sum(base["res"][sl] ** 2, axis=1))))
        rms_opt = float(np.sqrt(np.mean(np.sum(opt["res"][sl] ** 2, axis=1))))
        print(
            f"\n[Test 3 Stg{stage}] rms base={rms_base:.4f} -> opt={rms_opt:.4f} "
            f"a_lo={np.median(opt['a_hist'][-1, :10]):.4f} "
            f"a_mid={np.median(opt['a_hist'][-1, 20:100]):.4f} solve={opt['solve_ms']:.2f}ms"
        )
        assert rms_opt < rms_base, (
            f"Stage {stage}: modalopt ({rms_opt:.4f}) did not beat baseline ({rms_base:.4f})"
        )
        if stage == 1:
            assert float(np.median(opt["a_hist"][-1, :10])) > 0.988
        else:
            assert float(np.median(opt["a_hist"][-1, 20:100])) < 0.95
