# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end unit & live GPU HIL tests for Phase 2 (TP-2): 3D RM Factoring & Dynamic PSOL.

Validates:
  1. cacao-fpsexec-cacaoac-factordynrm:
     - Dropped-bin temporal repair, exact DC unity closure (sum_l H[l] = I),
       strict causality (H[0] = 0), compute-delay phase_fr centroid shift,
       block/threshold pruning preserving DC gain, and Kolmogorov PSOL benchmark.
  2. cacao-fpsexec-mfilt (Dynamic PSOL + probe isolation + zpo unit fix + RT speed):
     - Lock-step deterministic validation against a coupled 28-mode plate DM model:
       legacy 2-tap vs 2D H_diag vs 3D H_mimo, hybrid span (N_dyn < NBmode),
       uniform [1, L] broadcast, live hot-swap/toggle, zero selfRM probe leakage
       into aol0_modevalOL, zpo * WFSfact consistency under PF=ON + g_opt != 1,
       and < 50 us/frame RT overhead at NBmode=1255 (diag) and N_dyn=64 (MIMO).
  3. Full live GPU HIL test on cacaosim 12x12 coupled plate DM:
     - measdynresp -> factordynrm -> live closed-loop mfilt (2-tap vs H_diag vs H_mimo)
       with zero turbulence and AR(1) auxDM excitation proving live GPU PSOL error
       collapses and DM-ripple leakage into modevalOL vanishes.
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

PLATE12_BENCH = """\
[bench]
name         = "dynpsol_plate12"
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
in            = "b_post_dm"
out_cam       = "csim_wfs"
ncam          = 48
lambda_um     = 1.22
bw_frac       = 0.15
qe            = 0.85
navg          = 4
mod_rad       = 3.0
mod_npts      = 8
ron_e         = 0.0
photon_noise  = 0
out_dtype     = "float32"
"""

LOCKSTEP_DRIVER_C = r"""
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1.0e-9 * (double)ts.tv_nsec;
}

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

/* Usage:
 *   lockstep_driver <n_mode> <L> <n_step> <g_opt> <H_true.bin> <phi.bin> <ol_out.bin> <dm_out.bin>
 *                   [<pf_in.bin>]
 */
int main(int argc, char **argv) {
    if (argc < 9) return 2;
    int n_mode = atoi(argv[1]);
    int L      = atoi(argv[2]);
    int n_step = atoi(argv[3]);
    float gopt = (float)atof(argv[4]);
    const char *h_path   = argv[5];
    const char *phi_path = argv[6];
    const char *ol_path  = argv[7];
    const char *dm_path  = argv[8];
    const char *pf_path  = (argc >= 10 && argv[9][0] != '\0') ? argv[9] : NULL;

    float *H   = (float *)calloc((size_t)L * n_mode * n_mode, sizeof(float));
    float *phi = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *ol  = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *dm  = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *pf  = pf_path ? (float *)calloc((size_t)n_step * n_mode, sizeof(float)) : NULL;
    float *u_hist = (float *)calloc((size_t)L * n_mode, sizeof(float));
    if (!H || !phi || !ol || !dm || !u_hist) return 3;
    if (read_bin_f32(h_path, H, (size_t)L * n_mode * n_mode) != 0) return 4;
    if (read_bin_f32(phi_path, phi, (size_t)n_step * n_mode) != 0) return 5;
    if (pf_path && read_bin_f32(pf_path, pf, (size_t)n_step * n_mode) != 0) return 6;

    IMAGE im_wfs, im_dm, im_ol, im_pf;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalWFS", &im_wfs) != 0) return 10;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalDM", &im_dm) != 0) return 11;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalOL", &im_ol) != 0) return 12;
    int has_pf = 0;
    if (pf_path &&
        ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalPF", &im_pf) == 0) {
        has_pf = 1;
    }

    int sem_dm = ImageStreamIO_getsemwaitindex(&im_dm, -1);
    int sem_ol = ImageStreamIO_getsemwaitindex(&im_ol, -1);
    ImageStreamIO_semflush(&im_dm, sem_dm);
    ImageStreamIO_semflush(&im_ol, sem_ol);

    int head = 0;
    double t0 = now_sec();
    for (int k = 0; k < n_step; k++) {
        /* Compute physical WFS = g_opt * (phi[k] + sum_{l=1}^{L-1} H[l] * u[k-l]) */
        im_wfs.md[0].write = 1;
        for (int s = 0; s < n_mode; s++) {
            double acc = (double)phi[(size_t)k * n_mode + s];
            for (int l = 1; l < L; l++) {
                int slot = (head - l + L) % L;
                const float *u_l = &u_hist[(size_t)slot * n_mode];
                const float *h_r = &H[((size_t)l * n_mode + s) * n_mode];
                for (int q = 0; q < n_mode; q++) {
                    acc += (double)h_r[q] * (double)u_l[q];
                }
            }
            im_wfs.array.F[s] = gopt * (float)acc;
        }
        if (has_pf) {
            im_pf.md[0].write = 1;
            memcpy(im_pf.array.F, &pf[(size_t)k * n_mode], sizeof(float) * (size_t)n_mode);
            im_pf.md[0].cnt0++;
            im_pf.md[0].write = 0;
            ImageStreamIO_sempost(&im_pf, -1);
        }
        im_wfs.md[0].cnt0++;
        im_wfs.md[0].write = 0;
        ImageStreamIO_sempost(&im_wfs, -1);

        /* Wait for mfilt to publish both OL and DM */
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += 5;
        if (ImageStreamIO_semtimedwait(&im_dm, sem_dm, &ts) != 0) return 20;
        if (ImageStreamIO_semtimedwait(&im_ol, sem_ol, &ts) != 0) return 21;

        memcpy(&dm[(size_t)k * n_mode], im_dm.array.F, sizeof(float) * (size_t)n_mode);
        memcpy(&ol[(size_t)k * n_mode], im_ol.array.F, sizeof(float) * (size_t)n_mode);
        memcpy(&u_hist[(size_t)head * n_mode], im_dm.array.F, sizeof(float) * (size_t)n_mode);
        head = (head + 1) % L;
    }
    double elapsed_us = (now_sec() - t0) * 1.0e6 / (double)n_step;
    printf("US_PER_STEP=%.3f\n", elapsed_us);

    write_bin_f32(ol_path, ol, (size_t)n_step * n_mode);
    write_bin_f32(dm_path, dm, (size_t)n_step * n_mode);
    free(H); free(phi); free(ol); free(dm); free(pf); free(u_hist);
    return 0;
}
"""

HIL_BRIDGE_C = r"""
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

/* Live GPU bridge:
 *   csim_wfs -> (mask & C_pinv) -> aol0_modevalWFS -> mfilt -> aol0_modevalDM -> poke -> dm01disp
 * Injects aux_seq into aol0_modevalauxDM before each WFS step, records wfs_mod, dm_mod, ol_mod.
 * Usage:
 *   hil_bridge <n_mode> <n_out> <n_dm> <n_step>
 *              <mask_idx.i32> <wfs_ref.f32> <c_pinv.f32> <poke.f32> <aux.f32>
 *              <wfs_out.f32> <dm_out.f32> <ol_out.f32>
 */
int main(int argc, char **argv) {
    if (argc < 13) return 2;
    int n_mode = atoi(argv[1]);
    int n_out  = atoi(argv[2]);
    int n_dm   = atoi(argv[3]);
    int n_step = atoi(argv[4]);

    int32_t *idx    = (int32_t *)malloc(sizeof(int32_t) * (size_t)n_out);
    float   *wref   = (float *)malloc(sizeof(float) * (size_t)n_out);
    float   *cpinv  = (float *)malloc(sizeof(float) * (size_t)n_mode * n_out);
    float   *poke   = (float *)malloc(sizeof(float) * (size_t)n_mode * n_dm);
    float   *aux    = (float *)malloc(sizeof(float) * (size_t)n_step * n_mode);
    float   *w_log  = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float   *d_log  = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float   *o_log  = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float   *w_vec  = (float *)malloc(sizeof(float) * (size_t)n_out);
    if (!idx || !wref || !cpinv || !poke || !aux || !w_log || !d_log || !o_log || !w_vec) return 3;

    FILE *fi = fopen(argv[5], "rb");
    if (!fi || fread(idx, sizeof(int32_t), (size_t)n_out, fi) != (size_t)n_out) return 4;
    fclose(fi);
    if (read_bin_f32(argv[6], wref, (size_t)n_out) != 0) return 5;
    if (read_bin_f32(argv[7], cpinv, (size_t)n_mode * n_out) != 0) return 6;
    if (read_bin_f32(argv[8], poke, (size_t)n_mode * n_dm) != 0) return 7;
    if (read_bin_f32(argv[9], aux, (size_t)n_step * n_mode) != 0) return 8;

    IMAGE im_cam, im_dm2d, im_mwfs, im_mdm, im_mol, im_maux;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("csim_wfs", &im_cam) != 0) return 10;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("dm01disp", &im_dm2d) != 0) return 11;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalWFS", &im_mwfs) != 0) return 12;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalDM", &im_mdm) != 0) return 13;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalOL", &im_mol) != 0) return 14;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalauxDM", &im_maux) != 0) return 15;

    int sem_cam = ImageStreamIO_getsemwaitindex(&im_cam, -1);
    int sem_mdm = ImageStreamIO_getsemwaitindex(&im_mdm, -1);
    int sem_mol = ImageStreamIO_getsemwaitindex(&im_mol, -1);
    ImageStreamIO_semflush(&im_cam, sem_cam);
    ImageStreamIO_semflush(&im_mdm, sem_mdm);
    ImageStreamIO_semflush(&im_mol, sem_mol);

    for (int k = 0; k < n_step; k++) {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += 5;
        if (ImageStreamIO_semtimedwait(&im_cam, sem_cam, &ts) != 0) return 20;

        /* Extract normalized active pixels (same convention as measdynresp normalize=1) */
        double sum = 0.0;
        for (int p = 0; p < n_out; p++) {
            float v = im_cam.array.F[idx[p]];
            w_vec[p] = v;
            sum += (double)v;
        }
        float invs = (sum > 1.0e-12) ? (float)(1.0 / sum) : 1.0f;
        for (int p = 0; p < n_out; p++) {
            w_vec[p] = w_vec[p] * invs - wref[p];
        }

        /* Update auxDM disturbance before triggering mfilt */
        im_maux.md[0].write = 1;
        memcpy(im_maux.array.F, &aux[(size_t)k * n_mode], sizeof(float) * (size_t)n_mode);
        im_maux.md[0].cnt0++;
        im_maux.md[0].write = 0;

        /* Project WFS into modal space and trigger mfilt */
        im_mwfs.md[0].write = 1;
        for (int m = 0; m < n_mode; m++) {
            const float *cr = &cpinv[(size_t)m * n_out];
            double acc = 0.0;
            for (int p = 0; p < n_out; p++) acc += (double)cr[p] * (double)w_vec[p];
            im_mwfs.array.F[m] = (float)acc;
            w_log[(size_t)k * n_mode + m] = (float)acc;
        }
        im_mwfs.md[0].cnt0++;
        im_mwfs.md[0].write = 0;
        ImageStreamIO_sempost(&im_mwfs, -1);

        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += 5;
        if (ImageStreamIO_semtimedwait(&im_mdm, sem_mdm, &ts) != 0) return 21;
        if (ImageStreamIO_semtimedwait(&im_mol, sem_mol, &ts) != 0) return 22;

        const float *mdm = im_mdm.array.F;
        memcpy(&d_log[(size_t)k * n_mode], mdm, sizeof(float) * (size_t)n_mode);
        memcpy(&o_log[(size_t)k * n_mode], im_mol.array.F, sizeof(float) * (size_t)n_mode);

        /* Reconstruct 2D DM command and publish to dm01disp */
        im_dm2d.md[0].write = 1;
        for (int a = 0; a < n_dm; a++) {
            double acc = 0.0;
            for (int m = 0; m < n_mode; m++) {
                acc += (double)mdm[m] * (double)poke[(size_t)m * n_dm + a];
            }
            im_dm2d.array.F[a] = (float)acc;
        }
        im_dm2d.md[0].cnt0++;
        im_dm2d.md[0].write = 0;
        ImageStreamIO_sempost(&im_dm2d, -1);
    }

    /* Zero DM cleanly */
    im_dm2d.md[0].write = 1;
    memset(im_dm2d.array.F, 0, sizeof(float) * (size_t)n_dm);
    im_dm2d.md[0].cnt0++;
    im_dm2d.md[0].write = 0;
    ImageStreamIO_sempost(&im_dm2d, -1);

    write_bin_f32(argv[10], w_log, (size_t)n_step * n_mode);
    write_bin_f32(argv[11], d_log, (size_t)n_step * n_mode);
    write_bin_f32(argv[12], o_log, (size_t)n_step * n_mode);
    free(idx); free(wref); free(cpinv); free(poke); free(aux);
    free(w_log); free(d_log); free(o_log); free(w_vec);
    return 0;
}
"""


def _sandbox_env(tmp_path: Path, tag: str) -> tuple[dict[str, str], Path, Path]:
    shm_dir = Path(f"/dev/shm/cacao_dp_{tag}_{os.getpid()}")
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


def _run_bash(
    script: str, env: dict[str, str], timeout: float = 120.0
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _cleanup_sandbox(env: dict[str, str], shm_dir: Path, work_dir: Path) -> None:
    _run_bash(
        f'source "{REPO_ROOT}/scripts/shm-sandbox.sh"; '
        f'CACAOSIM_WORKDIR="{work_dir}" sandbox_stop_all',
        env=env,
        timeout=20.0,
    )
    shutil.rmtree(shm_dir, ignore_errors=True)


def _parse_fps_info(text: str) -> dict[str, float]:
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    out: dict[str, float] = {}
    for line in clean.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1].startswith((".", "out.", "comp.")):
            try:
                out[parts[1].lstrip(".")] = float(parts[3])
            except ValueError:
                pass
    return out


def _compile_helper(src: str, out_bin: Path, env: dict[str, str]) -> Path:
    src_path = out_bin.with_suffix(".c")
    src_path.write_text(src, encoding="utf-8")
    cmd = (
        f'source "{REPO_ROOT}/env.sh" && '
        f'cc -O2 -Wall -Wextra "{src_path}" '
        f'-I"$MILK_INSTALL_ROOT/include" -L"$MILK_INSTALL_ROOT/lib" '
        f'-Wl,-rpath,"$MILK_INSTALL_ROOT/lib" -lImageStreamIO -lm -o "{out_bin}"'
    )
    res = _run_bash(cmd, env=env, timeout=30.0)
    assert res.returncode == 0, f"Compile failed:\n{res.stdout}\n{res.stderr}"
    return out_bin


def _zernike_modes(nact: int = 12, n_modes: int = 8) -> np.ndarray:
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
    cube = np.zeros((n_modes, nact, nact), dtype=np.float32)
    for i, (n, m) in enumerate(pairs[:n_modes]):
        rad = np.zeros_like(r)
        am = abs(m)
        for s in range((n - am) // 2 + 1):
            num = ((-1) ** s) * math.factorial(n - s)
            den = (
                math.factorial(s)
                * math.factorial((n + am) // 2 - s)
                * math.factorial((n - am) // 2 - s)
            )
            rad += (num / den) * (np.clip(r, 0.0, 1.0) ** (n - 2 * s))
        z = rad if m == 0 else (rad * np.cos(m * th) if m > 0 else rad * np.sin(am * th))
        z = np.where(disk, z, 0.0)
        z[disk] -= float(np.mean(z[disk]))
        z /= max(float(np.sqrt(np.mean(z[disk] ** 2))), 1e-12)
        cube[i] = z.astype(np.float32)
    return cube


def test_factordynrm_synthetic_repair_causality_and_pruning(tmp_path: Path) -> None:
    """Verify factordynrm dropped-bin repair, causality, phase_fr shift, DC closure & pruning."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "fdr")
    try:
        n_in, n_out, nbsub, n_pre, n_post = 6, 32, 4, 4, 60
        n_t = n_pre + n_post
        dt_s = 0.00025
        rng = np.random.default_rng(12345)
        m_true = rng.normal(0.0, 1.0, size=(n_in, n_out))

        # Coupled damped oscillator step response with 1.0 ms delay + 1.0 ms boxcar exposure
        tau = (np.arange(n_t) - n_pre + 0.5) * dt_s
        s_raw = np.zeros((n_t, n_in, n_in), dtype=np.float64)
        for ti, t in enumerate(tau):
            if t <= 0.001:
                continue
            dt_d = t - 0.001
            # 2nd-order underdamped step + transient cross-mode coupling
            env_d = np.exp(-380.0 * dt_d)
            w_rad = 2.0 * np.pi * 600.0 * dt_d
            diag_v = 1.0 - env_d * (np.cos(w_rad) + 0.15 * np.sin(w_rad))
            off_v = 0.30 * env_d * np.sin(2.0 * np.pi * 450.0 * dt_d)
            mat = np.eye(n_in) * diag_v
            for i in range(n_in - 1):
                mat[i, i + 1] = off_v
                mat[i + 1, i] = -0.6 * off_v
            s_raw[ti] = mat
        # Apply causal 1.0 ms (nbsub=4 bins) WFS exposure boxcar moving average
        s_mod = np.zeros_like(s_raw)
        for ti in range(n_t):
            j0 = max(0, ti - nbsub + 1)
            s_mod[ti] = s_raw[j0 : ti + 1].sum(axis=0) / float(nbsub)

        # r3[t, q, p] = sum_s s_mod[t, s, q] * m_true[s, p]
        r3 = np.einsum("tsq,sp->tqp", s_mod, m_true).astype(np.float32)
        cnt = np.ones((n_t, n_in), dtype=np.uint32)
        # Inject 2 dropped bins (one mid-ringing, one tail)
        r3[14, 2, :] = 0.0
        cnt[14, 2] = 0
        r3[61, 4, :] = 0.0
        cnt[61, 4] = 0

        hdu = fits.PrimaryHDU(r3)
        hdu.header["DT_SEC"] = dt_s
        hdu.header["WFSFREQ"] = 1.0 / (dt_s * nbsub)
        hdu.header["Q0_BIN"] = n_pre
        hdu.header["NBSUBFR"] = nbsub
        hdu.header["NBRESPFR"] = n_post // nbsub
        hdu.writeto(work_dir / "syn3d.fits", overwrite=True)
        fits.writeto(work_dir / "syn3d_cnt.fits", cnt, overwrite=True)

        script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
cd "{work_dir}"
"$MILK_INSTALL_ROOT/bin/cacao-fpsexec-cacaoac-factordynrm" --no-procinfo -n f0 exec \
    .resp3d=syn3d.fits .outmimo=Hm0.fits .outdiag=Hd0.fits .outstatic=Mc.fits \
    .n_taps=14 .phase_fr=0.0
milk-fps-info f0 > f0.txt
"$MILK_INSTALL_ROOT/bin/cacao-fpsexec-cacaoac-factordynrm" --no-procinfo -n f25 exec \
    .resp3d=syn3d.fits .outmimo=Hm25.fits .outdiag=Hd25.fits \
    .n_taps=14 .phase_fr=0.25
milk-fps-info f25 > f25.txt
"$MILK_INSTALL_ROOT/bin/cacao-fpsexec-cacaoac-factordynrm" --no-procinfo -n fblk exec \
    .resp3d=syn3d.fits .outmimo=Hm_blk.fits .outdiag=Hd_blk.fits \
    .n_taps=14 .phase_fr=0.0 .blocksize=2 .offdiag_thr=0.02
milk-fps-info fblk > fblk.txt
"""
        res = _run_bash(script, env=env, timeout=30.0)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        v0 = _parse_fps_info((work_dir / "f0.txt").read_text())
        v25 = _parse_fps_info((work_dir / "f25.txt").read_text())
        vblk = _parse_fps_info((work_dir / "fblk.txt").read_text())

        assert int(v0["out.n_repaired"]) == 2
        assert v0["out.dc_err_max"] < 1.0e-6
        assert vblk["out.dc_err_max"] < 1.0e-6
        # Increasing controller compute delay phase_fr by +0.25 shifts centroid right by ~+0.25 fr
        d_lat = v25["out.lat_centroid_fr"] - v0["out.lat_centroid_fr"]
        assert 0.15 < d_lat < 0.35, f"Unexpected centroid shift for +0.25 phase_fr: {d_lat}"
        assert v0["out.psol_mimo_pct"] < 0.30
        assert v0["out.psol_mimo_pct"] < v0["out.psol_diag_pct"] / 4.0
        assert v0["out.psol_mimo_pct"] < v0["out.psol_2tap_pct"] / 5.0

        hm0 = fits.getdata(work_dir / "Hm0.fits")
        hd0 = fits.getdata(work_dir / "Hd0.fits")
        hm_blk = fits.getdata(work_dir / "Hm_blk.fits")
        assert hm0.shape == (14, n_in, n_in)
        assert hd0.shape == (14, n_in)
        assert float(np.max(np.abs(hm0[0]))) == 0.0, "Strict causality violated: H[0] != 0"
        assert float(np.max(np.abs(hm0.sum(axis=0) - np.eye(n_in)))) < 1.0e-5
        assert float(np.max(np.abs(hm_blk.sum(axis=0) - np.eye(n_in)))) < 1.0e-5
        # Cross-block entries zeroed by blocksize=2
        assert float(np.max(np.abs(hm_blk[:, 0:2, 2:6]))) == 0.0
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)


def test_modalfilter_dynpsol_mimo_diag_probe_zpo_and_speed(tmp_path: Path) -> None:
    """Lock-step RT validation of modalfilter Dynamic PSOL, probe isolation, zpo fix & speed."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "mfilt")
    try:
        driver = _compile_helper(LOCKSTEP_DRIVER_C, work_dir / "lockstep_driver", env)

        # Use real Pass-1 64x64 plate DM MIMO kernel if available, else build coupled 28-mode kernel
        p1_hm = REPO_ROOT / "_work/dm64_dyn_rm_calib/raw_calib/fdr_p1/H_mimo16.fits"
        p1_hd = REPO_ROOT / "_work/dm64_dyn_rm_calib/raw_calib/fdr_p1/H_diag16.fits"
        if p1_hm.exists() and p1_hd.exists():
            h_true = fits.getdata(p1_hm).astype(np.float32)  # [L, N, N]
            h_diag = fits.getdata(p1_hd).astype(np.float32)  # [L, N]
            n_mode = h_true.shape[1]
            n_taps = h_true.shape[0]
        else:
            n_mode, n_taps = 16, 12
            h_true = np.zeros((n_taps, n_mode, n_mode), dtype=np.float32)
            for m in range(n_mode):
                taps = np.array(
                    [0.0, 0.0, 0.85, 0.30, -0.22, 0.12, -0.07, 0.03, -0.01, 0.0, 0.0, 0.0],
                    dtype=np.float32,
                )
                h_true[:, m, m] = taps / taps.sum()
                if m + 1 < n_mode:
                    c = np.array(
                        [0.0, 0.0, 0.25, -0.18, -0.07, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                        dtype=np.float32,
                    )
                    h_true[:, m, m + 1] = c
                    h_true[:, m + 1, m] = -0.8 * c
            h_diag = np.diagonal(h_true, axis1=1, axis2=2).copy()

        fits.writeto(work_dir / "H_mimo.fits", h_true, overwrite=True)
        fits.writeto(work_dir / "H_diag.fits", h_diag, overwrite=True)
        fits.writeto(work_dir / "H_mimo12.fits", h_true[:, :12, :12].copy(), overwrite=True)
        fits.writeto(work_dir / "H_bcast.fits", h_diag[:, :1].copy(), overwrite=True)

        # Synthetic Kolmogorov AR(1) open-loop truth turbulence
        n_step = 700
        rng = np.random.default_rng(2026)
        phi = np.zeros((n_step, n_mode), dtype=np.float32)
        for m in range(n_mode):
            rad = math.sqrt(m + 1.0)
            rho = max(0.80, 0.985 - 0.02 * rad)
            amp = ((rad + 1.0) ** -1.1) * math.sqrt(1.0 - rho * rho)
            for k in range(1, n_step):
                phi[k, m] = rho * phi[k - 1, m] + amp * float(rng.standard_normal())

        h_true.astype(np.float32).tofile(work_dir / "H_true.bin")
        phi.astype(np.float32).tofile(work_dir / "phi.bin")
        z_in = np.zeros((1, n_mode), dtype=np.float32)
        fits.writeto(work_dir / "z_in.fits", z_in, overwrite=True)

        # Sub-test A: 2-tap vs H_diag vs H_mimo vs hybrid (N_dyn=12) vs selfRM probe isolation
        script_a = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
cd "{work_dir}"
cleanup() {{
    milk-fps-runstop -q mf0 >/dev/null 2>&1 || true
    milk-fps-rm -f -q mf0 >/dev/null 2>&1 || true
}}
trap cleanup EXIT

milk-FITS2shm --no-procinfo -n ldin exec z_in.fits @S:aol0_modevalWFS >/dev/null
milk-fps-init -q mf0 cacao-fpsexec-mfilt >/dev/null
milk-fps-set -q \
    mf0.inmval=aol0_modevalWFS \
    mf0.outmval=aol0_modevalDM \
    mf0.AOloopindex=0 \
    mf0.loopON=ON \
    mf0.loopgain=0.35 \
    mf0.loopmult=0.99 \
    mf0.looplimit=10.0 \
    mf0.comp.OLmodes=ON \
    mf0.comp.WFSfact=1.0 \
    mf0.comp.latencyhardwfr=2.14 \
    mf0.comp.latencysoftwfr=0.0 \
    mf0.comp.dynpsol.enable=OFF \
    mf0.selfRM.zsize=12 \
    mf0.procinfo.loopcntMax=-1
milk-fps-runstart -q mf0
milk-stream-wait -q -t 10 aol0_modevalDM aol0_modevalOL

# 1. Legacy 2-tap PSOL
"{driver}" {n_mode} {n_taps} {n_step} 1.0 H_true.bin phi.bin ol_2tap.bin dm_2tap.bin

# 2. Dynamic Diagonal FIR PSOL
milk-fps-set -q mf0.loopZERO=ON mf0.comp.dynpsol.kernel=H_diag.fits mf0.comp.dynpsol.enable=ON
sleep 0.05
"{driver}" {n_mode} {n_taps} {n_step} 1.0 H_true.bin phi.bin ol_diag.bin dm_diag.bin
milk-fps-info mf0 > mf_diag.txt

# 3. Dynamic MIMO FIR PSOL (hot-swap kernel!)
milk-fps-set -q mf0.loopZERO=ON mf0.comp.dynpsol.kernel=H_mimo.fits
sleep 0.05
"{driver}" {n_mode} {n_taps} {n_step} 1.0 H_true.bin phi.bin ol_mimo.bin dm_mimo.bin
milk-fps-info mf0 > mf_mimo.txt

# 4. Hybrid span (N_dyn=12 < NBmode={n_mode})
milk-fps-set -q mf0.loopZERO=ON mf0.comp.dynpsol.kernel=H_mimo12.fits
sleep 0.05
"{driver}" {n_mode} {n_taps} {n_step} 1.0 H_true.bin phi.bin ol_hyb.bin dm_hyb.bin
milk-fps-info mf0 > mf_hyb.txt

# 5. Live selfRM probe isolation (large pokeampl=0.50 during MIMO PSOL -> ZERO leakage!)
milk-fps-set -q mf0.loopZERO=ON mf0.comp.dynpsol.kernel=H_mimo.fits \
    mf0.selfRM.NBmode=4 mf0.selfRM.pokeampl=0.50 \
    mf0.selfRM.nbiter=2 mf0.selfRM.saveFITS=OFF mf0.selfRM.enable=ON
sleep 0.05
"{driver}" {n_mode} {n_taps} {n_step} 1.0 H_true.bin phi.bin ol_srm.bin dm_srm.bin
"""
        res_a = _run_bash(script_a, env=env, timeout=60.0)
        assert res_a.returncode == 0, f"STDOUT:\n{res_a.stdout}\nSTDERR:\n{res_a.stderr}"

        sl = slice(n_taps + 20, n_step)
        phi_ref = phi[sl]
        phi_rms = float(np.sqrt(np.mean(phi_ref**2)))

        def _err_pct(fname: str, cols: slice = slice(None)) -> float:
            ol = np.fromfile(work_dir / fname, dtype=np.float32).reshape(n_step, n_mode)
            e = ol[sl, cols] - phi_ref[:, cols]
            ref = float(np.sqrt(np.mean(phi_ref[:, cols] ** 2)))
            return 100.0 * float(np.sqrt(np.mean(e**2))) / max(ref, 1e-12)

        e_2tap = _err_pct("ol_2tap.bin")
        e_diag = _err_pct("ol_diag.bin")
        e_mimo = _err_pct("ol_mimo.bin")
        e_hyb_lo = _err_pct("ol_hyb.bin", slice(0, 12))
        e_srm = _err_pct("ol_srm.bin")

        # Verify selfRM actually poked the DM strongly while leaking 0 into modevalOL
        dm_mimo = np.fromfile(work_dir / "dm_mimo.bin", dtype=np.float32).reshape(n_step, n_mode)
        dm_srm = np.fromfile(work_dir / "dm_srm.bin", dtype=np.float32).reshape(n_step, n_mode)
        dm_diff = float(np.max(np.abs(dm_srm[sl, :4] - dm_mimo[sl, :4])))

        print(
            f"\n[Lockstep mfilt N={n_mode} L={n_taps}] "
            f"2-tap={e_2tap:.3f}% | diag={e_diag:.3f}% | MIMO={e_mimo:.4f}% | "
            f"hybrid(0:12)={e_hyb_lo:.4f}% | selfRM(poke=0.50, max|dDM|={dm_diff:.2f})={e_srm:.4f}%"
        )

        assert e_mimo < 0.05, f"MIMO PSOL should match exact truth (<0.05%), got {e_mimo:.4f}%"
        assert e_2tap > 1.0, f"Expected significant 2-tap plate error, got {e_2tap:.3f}%"
        assert e_mimo < e_2tap / 25.0
        assert e_mimo < e_diag / 20.0
        assert dm_diff > 0.35, f"selfRM poke did not fire on DM (max diff={dm_diff:.3f})"
        assert e_srm < 0.05, f"selfRM leaked into modevalOL: {e_srm:.4f}%"
        assert e_hyb_lo < e_diag * 0.80, f"Hybrid low modes did not beat diag: {e_hyb_lo:.4f}%"

        info_d = _parse_fps_info((work_dir / "mf_diag.txt").read_text())
        info_m = _parse_fps_info((work_dir / "mf_mimo.txt").read_text())
        info_h = _parse_fps_info((work_dir / "mf_hyb.txt").read_text())
        assert int(info_d["comp.dynpsol.mode"]) == 1
        assert int(info_m["comp.dynpsol.mode"]) == 2
        assert int(info_m["comp.dynpsol.ntaps"]) == n_taps
        assert int(info_m["comp.dynpsol.nmode"]) == n_mode
        assert int(info_h["comp.dynpsol.nmode"]) == 12

        # Sub-test B: Zero-point + g_opt=0.80 + PF=ON unit consistency check
        n_b = 4
        n_tb = 4
        h_id = np.zeros((n_tb, n_b, n_b), dtype=np.float32)
        h_id[2] = np.eye(n_b, dtype=np.float32)
        fits.writeto(work_dir / "Hb.fits", h_id, overwrite=True)
        h_id.tofile(work_dir / "Hb.bin")
        phi_b = np.full((60, n_b), 0.15, dtype=np.float32)
        phi_b.tofile(work_dir / "phi_b.bin")
        zb_in = np.zeros((1, n_b), dtype=np.float32)
        zpo_b = np.full((1, n_b), 0.20, dtype=np.float32)
        pfst_b = np.ones((1, n_b), dtype=np.float32)
        fits.writeto(work_dir / "zb_in.fits", zb_in, overwrite=True)
        fits.writeto(work_dir / "zpo_b.fits", zpo_b, overwrite=True)
        fits.writeto(work_dir / "pfst_b.fits", pfst_b, overwrite=True)

        script_b = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
cd "{work_dir}"
cleanup() {{
    milk-fps-runstop -q mfb >/dev/null 2>&1 || true
    milk-fps-rm -f -q mfb >/dev/null 2>&1 || true
}}
trap cleanup EXIT
rm -f "{shm_dir}"/aol0_*

milk-FITS2shm --no-procinfo -n lb1 exec zb_in.fits @S:aol0_modevalWFS >/dev/null
milk-fps-init -q mfb cacao-fpsexec-mfilt >/dev/null
milk-fps-set -q \
    mfb.inmval=aol0_modevalWFS mfb.outmval=aol0_modevalDM mfb.AOloopindex=0 \
    mfb.loopON=ON mfb.loopgain=0.2 mfb.loopmult=0.99 mfb.looplimit=10.0 \
    mfb.comp.OLmodes=ON mfb.comp.WFSfact=1.25 \
    mfb.comp.dynpsol.kernel=Hb.fits mfb.comp.dynpsol.enable=ON \
    mfb.PF.enable=ON mfb.PF.mixcoeff=1.0 mfb.PF.NBblock=0 \
    mfb.procinfo.loopcntMax=-1
milk-fps-runstart -q mfb
milk-stream-wait -q -t 10 aol0_modevalDM aol0_mzeropoint aol0_outPFstat aol0_modevalPF

# Load zpo=0.20 and outPFstat=1.0 in-place via streamcopy
milk-FITS2shm --no-procinfo -n lz1 exec zpo_b.fits @S:tmp_zpo >/dev/null
milk-FITS2shm --no-procinfo -n ls1 exec pfst_b.fits @S:tmp_pfs >/dev/null
milk-fps-init -q cpz milk-fpsexec-mem-streamcopy >/dev/null
milk-fps-set -q cpz.in_sname=tmp_zpo cpz.out_sname=aol0_mzeropoint cpz.procinfo.loopcntMax=1
milk-fps-runstart -q cpz && milk-fps-wait -q -t 10 cpz && milk-fps-rm -f -q cpz
milk-fps-init -q cpp milk-fpsexec-mem-streamcopy >/dev/null
milk-fps-set -q cpp.in_sname=tmp_pfs cpp.out_sname=aol0_outPFstat cpp.procinfo.loopcntMax=1
milk-fps-runstart -q cpp && milk-fps-wait -q -t 10 cpp && milk-fps-rm -f -q cpp

"{driver}" {n_b} {n_tb} 60 0.80 Hb.bin phi_b.bin ol_b.bin dm_b.bin phi_b.bin
"""
        res_b = _run_bash(script_b, env=env, timeout=30.0)
        assert res_b.returncode == 0, f"STDOUT:\n{res_b.stdout}\nSTDERR:\n{res_b.stderr}"
        dm_b = np.fromfile(work_dir / "dm_b.bin", dtype=np.float32).reshape(60, n_b)
        ol_b = np.fromfile(work_dir / "ol_b.bin", dtype=np.float32).reshape(60, n_b)
        # Expected steady state: u_dm = (1/0.80)*0.20 - 0.15 = +0.10 => wfs = 0.20 == zpo
        assert float(np.max(np.abs(dm_b[-10:] - 0.10))) < 1.0e-4, f"DM mismatch: {dm_b[-1]}"
        assert float(np.max(np.abs(ol_b[-10:] - 0.15))) < 1.0e-4, f"OL mismatch: {ol_b[-1]}"

        # Sub-test C: RT overhead benchmark (< 50 us at NBmode=1255 diag & N_dyn=64 MIMO)
        nb_rt = 1255
        l_rt = 12
        n_mimo_rt = 64
        n_st_rt = 1000
        hd_rt = np.zeros((l_rt, nb_rt), dtype=np.float32)
        hd_rt[2, :] = 0.7
        hd_rt[3, :] = 0.3
        hm_rt = np.zeros((l_rt, n_mimo_rt, n_mimo_rt), dtype=np.float32)
        hm_rt[2] = 0.7 * np.eye(n_mimo_rt, dtype=np.float32)
        hm_rt[3] = 0.3 * np.eye(n_mimo_rt, dtype=np.float32)
        fits.writeto(work_dir / "Hd_rt.fits", hd_rt, overwrite=True)
        fits.writeto(work_dir / "Hm_rt.fits", hm_rt, overwrite=True)
        fits.writeto(work_dir / "z_rt.fits", np.zeros((1, nb_rt), dtype=np.float32), overwrite=True)

        # Tiny pure-timing C driver (no heavy H matmul in driver, just posts WFS and waits on DM/OL)
        bench_c = r"""
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"
static double now_s(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1.0e-9 * (double)ts.tv_nsec;
}
int main(int argc, char **argv) {
    int n_step = atoi(argv[1]);
    IMAGE w, d, o;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalWFS", &w) != 0) return 1;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalDM", &d) != 0) return 2;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalOL", &o) != 0) return 3;
    int sd = ImageStreamIO_getsemwaitindex(&d, -1);
    int so = ImageStreamIO_getsemwaitindex(&o, -1);
    ImageStreamIO_semflush(&d, sd); ImageStreamIO_semflush(&o, so);
    double t0 = now_s();
    for (int k = 0; k < n_step; k++) {
        w.md[0].cnt0++;
        ImageStreamIO_sempost(&w, -1);
        ImageStreamIO_semwait(&d, sd);
        ImageStreamIO_semwait(&o, so);
    }
    printf("%.3f\n", (now_s() - t0) * 1.0e6 / (double)n_step);
    return 0;
}
"""
        bench_bin = _compile_helper(bench_c, work_dir / "rt_bench", env)
        script_c = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
cd "{work_dir}"
cleanup() {{
    milk-fps-runstop -q mfrt >/dev/null 2>&1 || true
    milk-fps-rm -f -q mfrt >/dev/null 2>&1 || true
}}
trap cleanup EXIT
rm -f "{shm_dir}"/aol0_*

milk-FITS2shm --no-procinfo -n lrt exec z_rt.fits @S:aol0_modevalWFS >/dev/null
milk-fps-init -q mfrt cacao-fpsexec-mfilt >/dev/null
milk-fps-set -q \
    mfrt.inmval=aol0_modevalWFS mfrt.outmval=aol0_modevalDM mfrt.AOloopindex=0 \
    mfrt.loopON=ON mfrt.loopgain=0.1 mfrt.loopmult=0.99 mfrt.comp.OLmodes=ON \
    mfrt.comp.dynpsol.enable=OFF mfrt.procinfo.loopcntMax=-1
milk-fps-runstart -q mfrt
milk-stream-wait -q -t 10 aol0_modevalDM aol0_modevalOL

T_2TAP=$("{bench_bin}" {n_st_rt})
milk-fps-set -q mfrt.comp.dynpsol.kernel=Hd_rt.fits mfrt.comp.dynpsol.enable=ON
sleep 0.05
T_DIAG=$("{bench_bin}" {n_st_rt})
milk-fps-set -q mfrt.comp.dynpsol.kernel=Hm_rt.fits
sleep 0.05
T_MIMO=$("{bench_bin}" {n_st_rt})
echo "RT_US 2tap=$T_2TAP diag=$T_DIAG mimo64=$T_MIMO"
"""
        res_c = _run_bash(script_c, env=env, timeout=30.0)
        assert res_c.returncode == 0, f"STDOUT:\n{res_c.stdout}\nSTDERR:\n{res_c.stderr}"
        m_rt = re.search(r"RT_US 2tap=([\d.]+) diag=([\d.]+) mimo64=([\d.]+)", res_c.stdout)
        assert m_rt is not None, res_c.stdout
        t_2tap, t_diag, t_mimo = (float(m_rt.group(i)) for i in (1, 2, 3))
        print(
            f"[RT Speed NBmode={nb_rt} L={l_rt}] "
            f"2-tap={t_2tap:.1f} us | diag={t_diag:.1f} us (+{t_diag-t_2tap:.1f} us) | "
            f"MIMO64+hyb={t_mimo:.1f} us (+{t_mimo-t_2tap:.1f} us)"
        )
        assert (t_diag - t_2tap) < 50.0, f"Diag FIR overhead too high: {t_diag - t_2tap:.1f} us"
        assert (t_mimo - t_2tap) < 50.0, f"MIMO64 FIR overhead too high: {t_mimo - t_2tap:.1f} us"
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)


def test_hil_live_plate_dm_dynpsol_and_whiteness(tmp_path: Path) -> None:
    """Live GPU HIL: measdynresp -> factordynrm -> closed-loop mfilt (2-tap vs diag vs MIMO)."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "hil")
    raw_dir = work_dir / "cal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    bench_file = work_dir / "plate12.bench"
    bench_file.write_text(PLATE12_BENCH, encoding="utf-8")

    n_mode = 8
    z8 = _zernike_modes(12, n_mode)
    fits.writeto(raw_dir / "poke_z8.fits", z8, overwrite=True)

    # Zero-turbulence Kolmogorov AR(1) auxDM excitation (strictly linear PyWFS regime)
    n_step = 450
    rng = np.random.default_rng(777)
    aux = np.zeros((n_step, n_mode), dtype=np.float32)
    for m in range(n_mode):
        rho = 0.94 - 0.015 * m
        amp = 0.004 * ((m + 1.0) ** -0.4) * math.sqrt(1.0 - rho * rho)
        for k in range(1, n_step):
            aux[k, m] = rho * aux[k - 1, m] + amp * float(rng.standard_normal())
    aux.tofile(raw_dir / "aux.bin")

    bridge = _compile_helper(HIL_BRIDGE_C, work_dir / "hil_bridge", env)
    py = env.get("PYTHON_BIN") or shutil.which("python3") or "python3"

    script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
cd "{raw_dir}"

cleanup() {{
    milk-fps-runstop -q mf0 >/dev/null 2>&1 || true
    milk-fps-rm -f -q mdr fdr mf0 >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy --workdir "{work_dir}" --config "{bench_file}" \\
    --mode fused --no-view >/dev/null
milk-stream-wait -q -t 20 csim_wfs:48x48 dm01disp:12x12

# Snapshot reference WFS frame & build active-pixel mask
milk-fpsexec-iofits-saveFITS --no-procinfo -n snapw exec csim_wfs "!wfs_snap.fits" >/dev/null
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
wfs = fits.getdata("wfs_snap.fits").astype(np.float32)
sig = wfs - float(np.percentile(wfs, 5.0))
mask = (sig > 0.20 * float(sig.max())).astype(np.float32)
fits.writeto("wfsmask.fits", mask, overwrite=True)
idx = np.flatnonzero(mask.ravel() > 0.5).astype(np.int32)
idx.tofile("mask_idx.bin")
w_act = wfs.ravel()[idx].astype(np.float64)
(w_act / w_act.sum()).astype(np.float32).tofile("wfs_ref.bin")
print("N_OUT=", len(idx))
PY

# 1. Measure live 3D RM on GPU coupled plate DM (with normalize=ON matching hil_bridge!)
milk-fps-init -q mdr cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr.streamin=dm01disp mdr.streamout=csim_wfs mdr.normalize=ON \\
    mdr.inmodes=poke_z8.fits mdr.outcube=resp3D.fits mdr.outmask=wfsmask.fits \\
    mdr.ampl=0.010 mdr.timing.WFSfrequ=0.0 mdr.timing.frameratewait=0.3 \\
    mdr.timing.NBsubfr=4 mdr.timing.NBrespfr=16 mdr.timing.NBprefr=2 \\
    mdr.timing.NBsettlefr=2 mdr.timing.NBcycle=1 mdr.pokemode=1 mdr.phaseorder=0 \\
    mdr.procinfo.loopcntMax=1
milk-fps-runstart -q mdr
milk-fps-wait -q -t 60 mdr
milk-fps-rm -f -q mdr

# 2. Factor 3D RM -> M_cal, H_diag, H_mimo (default phase_fr=-1 auto -> exact phase_idx=0 bin)
"$MILK_INSTALL_ROOT/bin/cacao-fpsexec-cacaoac-factordynrm" --no-procinfo -n fdr exec \\
    .resp3d=resp3D.fits .outmimo=H_mimo.fits .outdiag=H_diag.fits .outstatic=M_cal.fits \\
    .n_taps=14
milk-fps-info fdr > fdr_info.txt

# Export C_pinv and poke binary tables for live C bridge
"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
mcal = fits.getdata("M_cal.fits").astype(np.float64)  # [N_in, N_out]
u, s, vt = np.linalg.svd(mcal, full_matrices=False)
cpinv = ((u * np.where(s > 1e-4 * s[0], 1.0 / s, 0.0)[None, :]) @ vt).astype(np.float32)
cpinv.tofile("cpinv.bin")
poke = fits.getdata("poke_z8.fits").astype(np.float32).reshape(mcal.shape[0], -1)
poke.tofile("poke.bin")
fits.writeto("zero_m.fits", np.zeros((1, mcal.shape[0]), dtype=np.float32), overwrite=True)
with open("lat_c.txt", "w") as f:
    f.write(f"{{float(fits.getheader('H_mimo.fits')['LATCENT']):.4f}}")
PY

N_OUT=$("{py}" -c 'import numpy as np; print(len(np.fromfile("mask_idx.bin", dtype=np.int32)))')
LAT_C=$(cat lat_c.txt)

# 3. Launch live cacao-fpsexec-mfilt
milk-FITS2shm --no-procinfo -n lmw exec zero_m.fits @S:aol0_modevalWFS >/dev/null
milk-fps-init -q mf0 cacao-fpsexec-mfilt >/dev/null
milk-fps-set -q \\
    mf0.inmval=aol0_modevalWFS mf0.outmval=aol0_modevalDM mf0.AOloopindex=0 \\
    mf0.loopON=ON mf0.loopgain=0.25 mf0.loopmult=0.98 mf0.looplimit=1.0 \\
    mf0.comp.OLmodes=ON mf0.comp.WFSfact=1.0 \\
    mf0.comp.latencyhardwfr="$LAT_C" mf0.comp.latencysoftwfr=0.0 \\
    mf0.comp.dynpsol.enable=OFF \\
    mf0.auxDMmval.enable=ON mf0.auxDMmval.mixfact=1.0 \\
    mf0.procinfo.loopcntMax=-1
milk-fps-runstart -q mf0
milk-stream-wait -q -t 10 aol0_modevalDM aol0_modevalOL aol0_modevalauxDM

# Run A: Live GPU closed-loop with Legacy 2-tap PSOL (zero turb -> modevalOL == pure PSOL err!)
"{bridge}" {n_mode} "$N_OUT" 144 {n_step} mask_idx.bin wfs_ref.bin cpinv.bin poke.bin aux.bin \\
    wfs_2tap.bin dm_2tap.bin ol_2tap.bin

# Run B: Live GPU closed-loop with Dynamic Diagonal FIR (H_diag.fits)
milk-fps-set -q mf0.loopZERO=ON mf0.comp.dynpsol.kernel=H_diag.fits mf0.comp.dynpsol.enable=ON
sleep 0.10
"{bridge}" {n_mode} "$N_OUT" 144 {n_step} mask_idx.bin wfs_ref.bin cpinv.bin poke.bin aux.bin \\
    wfs_diag.bin dm_diag.bin ol_diag.bin

# Run C: Live GPU closed-loop with Dynamic MIMO FIR (H_mimo.fits)
milk-fps-set -q mf0.loopZERO=ON mf0.comp.dynpsol.kernel=H_mimo.fits
sleep 0.10
"{bridge}" {n_mode} "$N_OUT" 144 {n_step} mask_idx.bin wfs_ref.bin cpinv.bin poke.bin aux.bin \\
    wfs_mimo.bin dm_mimo.bin ol_mimo.bin

milk-fps-runstop -q mf0
milk-fps-wait -q -t 10 mf0
milk-fps-rm -f -q mf0
cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null
"""
    try:
        res = _run_bash(script, env=env, timeout=180.0)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        sl = slice(40, n_step)

        def _hil_metrics(tag: str) -> tuple[float, float]:
            d = np.fromfile(raw_dir / f"dm_{tag}.bin", dtype=np.float32).reshape(n_step, n_mode)
            o = np.fromfile(raw_dir / f"ol_{tag}.bin", dtype=np.float32).reshape(n_step, n_mode)
            ol_pct = 100.0 * float(np.sqrt(np.mean(o[sl] ** 2))) / max(
                float(np.sqrt(np.mean(d[sl] ** 2))), 1e-12
            )
            # Peak DM->OL leakage gain |cov(o, d[k-lag])| / var(d) over lags 1..8
            best_leak = 0.0
            for lag in range(1, 9):
                dl = d[sl.start - lag : sl.stop - lag]
                cov = np.mean(o[sl] * dl, axis=0)
                var_d = np.maximum(np.mean(dl**2, axis=0), 1e-12)
                leak = float(np.mean(np.abs(cov / var_d)))
                best_leak = max(best_leak, leak)
            return ol_pct, best_leak

        err_2t, l_2t = _hil_metrics("2tap")
        err_dg, l_dg = _hil_metrics("diag")
        err_mm, l_mm = _hil_metrics("mimo")
        fdr_info = _parse_fps_info((raw_dir / "fdr_info.txt").read_text())

        print(
            f"\n[LIVE GPU Plate12 HIL PSOL] "
            f"fdr_bench(2tap/diag/mimo)={fdr_info['out.psol_2tap_pct']:.2f}/"
            f"{fdr_info['out.psol_diag_pct']:.2f}/{fdr_info['out.psol_mimo_pct']:.2f}% | "
            f"LIVE_ERR: 2-tap={err_2t:.2f}% -> diag={err_dg:.2f}% -> MIMO={err_mm:.2f}% "
            f"({err_2t / max(err_mm, 1e-9):.1f}x vs 2-tap, "
            f"{err_dg / max(err_mm, 1e-9):.1f}x vs diag) | "
            f"DM-leakage gain: 2-tap={l_2t:.4f} -> MIMO={l_mm:.4f} ({l_2t / max(l_mm, 1e-9):.1f}x)"
        )

        assert err_mm < err_2t / 4.0, f"MIMO vs 2-tap <4x: {err_2t:.2f}% -> {err_mm:.2f}%"
        assert err_mm < err_dg / 3.0, f"MIMO vs diag <3x: {err_dg:.2f}% -> {err_mm:.2f}%"
        assert err_mm < 8.0, f"Live GPU MIMO PSOL error too high: {err_mm:.2f}%"
        assert l_mm < l_2t / 4.0, f"DM leakage gain not suppressed >4x: {l_2t:.4f} -> {l_mm:.4f}"
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)
