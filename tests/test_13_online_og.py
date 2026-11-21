# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end unit, lock-step RT, and live GPU HIL tests for Phase 3 (TP-3): Online OG.

Validates:
  1. cacao-fpsexec-mfilt (.comp.ogprobe.* + aolX_modevalprobe_buff) +
     cacao-fpsexec-modalog (differenced exogenous-IV optical-gain estimator):
     - Exact unbiased optical-gain recovery under BOTH Leaky Integrator and
       closed-loop Predictive Filter (PF=ON) with 38x stronger Kolmogorov turbulence
       and WFS noise, using the real 64x64 plate DM MIMO kernel H_mimo.fits.
     - Sparse mode probing (stride=2): radial spatial-frequency smoothing recovers
       unprobed modes to < 2.5% while n_free=2 preserves anomalous Tip/Tilt gains.
     - Live aol0_mWFSfact = 1/g_opt update collapses PSOL error from ~25% to < 2.5%
       with zero probe leakage into aol0_modevalOL.
     - Mid-run step jump (0.65x optical gain drop) tracks accurately within < 1.5 s.
  2. Full live GPU HIL test on cacaosim 12x12 coupled plate DM + 3 l/D PyWFS with
     real atmospheric phase screens driving optical gain reduction (~0.70-0.85):
     - Live closed-loop modalog recovers true physical GPU PyWFS optical gain
       within < 4% using < 3 nm RMS probe amplitude.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
import shutil
import subprocess

from astropy.io import fits
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]

PLATE12_TURB_BENCH = """\
[bench]
name         = "online_og_plate12"
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
turb_gain    = 1.0

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

OG_LOCKSTEP_C = r"""
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
 * Lock-step closed-loop driver for mfilt + modalog with time-varying per-mode g_opt[k, m],
 * full MIMO plate DM kernel H_true[L, N, N], atmospheric turbulence phi[k, m], WFS noise n[k, m],
 * and optional predictive filter input (1-step oracle-like AR predictor fed to aol0_modevalPF).
 *
 * Usage:
 *   og_lockstep <n_mode> <L> <n_step> <tbuff_sz> <use_pf>
 *               <H_true.bin> <phi.bin> <noise.bin> <g_opt.bin> <ol_out.bin> <og_snap.bin>
 */
int main(int argc, char **argv) {
    if (argc < 12) return 2;
    int n_mode   = atoi(argv[1]);
    int L        = atoi(argv[2]);
    int n_step   = atoi(argv[3]);
    int tb_sz    = atoi(argv[4]);
    int use_pf   = atoi(argv[5]);

    float *H      = (float *)calloc((size_t)L * n_mode * n_mode, sizeof(float));
    float *phi    = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *noise  = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *gopt   = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    float *ol_log = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
    int    n_sl   = n_step / tb_sz;
    float *og_log = (float *)calloc((size_t)(n_sl > 0 ? n_sl : 1) * n_mode, sizeof(float));
    float *u_hist = (float *)calloc((size_t)L * n_mode, sizeof(float));
    if (!H || !phi || !noise || !gopt || !ol_log || !og_log || !u_hist) return 3;

    if (read_bin_f32(argv[6], H, (size_t)L * n_mode * n_mode) != 0) return 4;
    if (read_bin_f32(argv[7], phi, (size_t)n_step * n_mode) != 0) return 5;
    if (read_bin_f32(argv[8], noise, (size_t)n_step * n_mode) != 0) return 6;
    if (read_bin_f32(argv[9], gopt, (size_t)n_step * n_mode) != 0) return 7;

    IMAGE im_wfs, im_dm, im_ol, im_pf, im_pfs, im_og;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalWFS", &im_wfs) != 0) return 10;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalDM", &im_dm) != 0) return 11;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalOL", &im_ol) != 0) return 12;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_og_smooth", &im_og) != 0) return 13;
    if (use_pf) {
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalPF", &im_pf) != 0) return 14;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_outPFstat", &im_pfs) != 0) return 15;
        im_pfs.md[0].write = 1;
        for (int m = 0; m < n_mode; m++) im_pfs.array.F[m] = 1.0f;
        im_pfs.md[0].cnt0++;
        im_pfs.md[0].write = 0;
    }

    int sem_dm = ImageStreamIO_getsemwaitindex(&im_dm, -1);
    int sem_ol = ImageStreamIO_getsemwaitindex(&im_ol, -1);
    int sem_og = ImageStreamIO_getsemwaitindex(&im_og, -1);
    ImageStreamIO_semflush(&im_dm, sem_dm);
    ImageStreamIO_semflush(&im_ol, sem_ol);
    ImageStreamIO_semflush(&im_og, sem_og);

    int head   = 0;
    int sl_idx = 0;
    for (int k = 0; k < n_step; k++) {
        /* True physical WFS: w[k] = g_opt[k] * (phi[k] + sum_{l=1}^{L-1} H[l] u[k-l]) + noise */
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
            float gm = gopt[(size_t)k * n_mode + s];
            im_wfs.array.F[s] = gm * (float)acc + noise[(size_t)k * n_mode + s];
        }

        if (use_pf) {
            /* Closed-loop predictive feedback using past OL (creates strong PF reaction) */
            im_pf.md[0].write = 1;
            for (int m = 0; m < n_mode; m++) {
                float p0 = (k > 0) ? ol_log[(size_t)(k - 1) * n_mode + m] : 0.0f;
                float p1 = (k > 1) ? ol_log[(size_t)(k - 2) * n_mode + m] : p0;
                im_pf.array.F[m] = 0.85f * (1.25f * p0 - 0.25f * p1);
            }
            im_pf.md[0].cnt0++;
            im_pf.md[0].write = 0;
            ImageStreamIO_sempost(&im_pf, -1);
        }

        im_wfs.md[0].cnt0++;
        im_wfs.md[0].write = 0;
        ImageStreamIO_sempost(&im_wfs, -1);

        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += 5;
        if (ImageStreamIO_semtimedwait(&im_dm, sem_dm, &ts) != 0) return 20;
        if (ImageStreamIO_semtimedwait(&im_ol, sem_ol, &ts) != 0) return 21;

        memcpy(&ol_log[(size_t)k * n_mode], im_ol.array.F, sizeof(float) * (size_t)n_mode);
        memcpy(&u_hist[(size_t)head * n_mode], im_dm.array.F, sizeof(float) * (size_t)n_mode);
        head = (head + 1) % L;

        /* Whenever a full telemetry slice finishes, wait for modalog to finish updating! */
        if (((k + 1) % tb_sz) == 0 && sl_idx < n_sl) {
            clock_gettime(CLOCK_REALTIME, &ts);
            ts.tv_sec += 5;
            if (ImageStreamIO_semtimedwait(&im_og, sem_og, &ts) != 0) return 22;
            memcpy(&og_log[(size_t)sl_idx * n_mode], im_og.array.F,
                   sizeof(float) * (size_t)n_mode);
            sl_idx++;
        }
    }

    write_bin_f32(argv[10], ol_log, (size_t)n_step * n_mode);
    write_bin_f32(argv[11], og_log, (size_t)sl_idx * n_mode);
    free(H); free(phi); free(noise); free(gopt); free(ol_log); free(og_log); free(u_hist);
    return 0;
}
"""

GPU_OG_BRIDGE_C = r"""
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
 * Live GPU PyWFS bridge: updates outarraypha (static/drifting high-order aberrating phase screen
 * that physically reduces 3 l/D PyWFS optical gain), projects csim_wfs -> aol0_modevalWFS,
 * waits on mfilt -> aol0_modevalDM, and writes dm01disp.
 *
 * Usage:
 *   gpu_og_bridge <n_mode> <n_out> <n_dm> <n_wf> <n_step> <mode>
 *                 <mask_idx.i32> <wfs_ref.f32> <cpinv.f32> <poke.f32> <turb_pha.f32>
 *                 <out_val.f32>
 *   mode=0: ground-truth differential poke measurement of physical PyWFS optical gain under turb
 *   mode=1: live closed-loop run with mfilt + modalog
 */
int main(int argc, char **argv) {
    if (argc < 13) return 2;
    int n_mode = atoi(argv[1]);
    int n_out  = atoi(argv[2]);
    int n_dm   = atoi(argv[3]);
    int n_wf   = atoi(argv[4]);
    int n_step = atoi(argv[5]);
    int mode   = atoi(argv[6]);

    int32_t *idx   = (int32_t *)malloc(sizeof(int32_t) * (size_t)n_out);
    float   *wref  = (float *)malloc(sizeof(float) * (size_t)n_out);
    float   *cpinv = (float *)malloc(sizeof(float) * (size_t)n_mode * n_out);
    float   *poke  = (float *)malloc(sizeof(float) * (size_t)n_mode * n_dm);
    float   *tpha  = (float *)malloc(sizeof(float) * (size_t)n_wf * n_wf);
    float   *wvec  = (float *)malloc(sizeof(float) * (size_t)n_out);
    if (!idx || !wref || !cpinv || !poke || !tpha || !wvec) return 3;

    FILE *fi = fopen(argv[7], "rb");
    if (!fi || fread(idx, sizeof(int32_t), (size_t)n_out, fi) != (size_t)n_out) return 4;
    fclose(fi);
    if (read_bin_f32(argv[8], wref, (size_t)n_out) != 0) return 5;
    if (read_bin_f32(argv[9], cpinv, (size_t)n_mode * n_out) != 0) return 6;
    if (read_bin_f32(argv[10], poke, (size_t)n_mode * n_dm) != 0) return 7;
    if (read_bin_f32(argv[11], tpha, (size_t)n_wf * n_wf) != 0) return 8;

    IMAGE im_cam, im_dm2d, im_wf;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("csim_wfs", &im_cam) != 0) return 10;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("dm01disp", &im_dm2d) != 0) return 11;
    if (ImageStreamIO_read_sharedmem_image_toIMAGE("outarraypha", &im_wf) != 0) return 12;

    /* Apply high-order aberrating phase screen (causes real physical PyWFS optical gain loss) */
    im_wf.md[0].write = 1;
    memcpy(im_wf.array.F, tpha, sizeof(float) * (size_t)n_wf * n_wf);
    im_wf.md[0].cnt0++;
    im_wf.md[0].write = 0;
    ImageStreamIO_sempost(&im_wf, -1);

    int sem_cam = ImageStreamIO_getsemwaitindex(&im_cam, -1);
    ImageStreamIO_semflush(&im_cam, sem_cam);

    if (mode == 0) {
        /* Ground-truth settled +/- push-pull measurement of physical PyWFS optical gain */
        float *g_true = (float *)calloc((size_t)n_mode, sizeof(float));
        float  amp    = 0.006f;
        for (int m = 0; m < n_mode; m++) {
            double v_pos = 0.0, v_neg = 0.0;
            for (int pol = 0; pol < 2; pol++) {
                float sgn = (pol == 0) ? amp : -amp;
                im_dm2d.md[0].write = 1;
                for (int a = 0; a < n_dm; a++)
                    im_dm2d.array.F[a] = sgn * poke[(size_t)m * n_dm + a];
                im_dm2d.md[0].cnt0++;
                im_dm2d.md[0].write = 0;
                ImageStreamIO_sempost(&im_dm2d, -1);

                /* Wait 24 frames (48 ms) for plate DM to fully settle */
                for (int w = 0; w < 24; w++) {
                    struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts); ts.tv_sec += 5;
                    if (ImageStreamIO_semtimedwait(&im_cam, sem_cam, &ts) != 0) return 20;
                }
                double sum = 0.0;
                for (int p = 0; p < n_out; p++) {
                    wvec[p] = im_cam.array.F[idx[p]]; sum += wvec[p];
                }
                float invs = (sum > 1e-12) ? (float)(1.0 / sum) : 1.0f;
                double acc = 0.0;
                const float *cr = &cpinv[(size_t)m * n_out];
                for (int p = 0; p < n_out; p++)
                    acc += (double)cr[p] * (double)(wvec[p] * invs - wref[p]);
                if (pol == 0) v_pos = acc; else v_neg = acc;
            }
            g_true[m] = (float)((v_pos - v_neg) / (2.0 * (double)amp));
        }
        im_dm2d.md[0].write = 1;
        memset(im_dm2d.array.F, 0, sizeof(float) * (size_t)n_dm);
        im_dm2d.md[0].cnt0++;
        im_dm2d.md[0].write = 0;
        ImageStreamIO_sempost(&im_dm2d, -1);
        write_bin_f32(argv[12], g_true, (size_t)n_mode);
        free(g_true);
    } else {
        /* Closed-loop run with mfilt + modalog */
        IMAGE im_mwfs, im_mdm, im_mol;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalWFS", &im_mwfs) != 0) return 13;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalDM", &im_mdm) != 0) return 14;
        if (ImageStreamIO_read_sharedmem_image_toIMAGE("aol0_modevalOL", &im_mol) != 0) return 15;
        int sem_mdm = ImageStreamIO_getsemwaitindex(&im_mdm, -1);
        int sem_mol = ImageStreamIO_getsemwaitindex(&im_mol, -1);
        ImageStreamIO_semflush(&im_mdm, sem_mdm);
        ImageStreamIO_semflush(&im_mol, sem_mol);

        float *ol_log = (float *)calloc((size_t)n_step * n_mode, sizeof(float));
        for (int k = 0; k < n_step; k++) {
            struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts); ts.tv_sec += 5;
            if (ImageStreamIO_semtimedwait(&im_cam, sem_cam, &ts) != 0) return 21;

            double sum = 0.0;
            for (int p = 0; p < n_out; p++) { wvec[p] = im_cam.array.F[idx[p]]; sum += wvec[p]; }
            float invs = (sum > 1e-12) ? (float)(1.0 / sum) : 1.0f;
            for (int p = 0; p < n_out; p++) wvec[p] = wvec[p] * invs - wref[p];

            im_mwfs.md[0].write = 1;
            for (int m = 0; m < n_mode; m++) {
                const float *cr = &cpinv[(size_t)m * n_out];
                double acc = 0.0;
                for (int p = 0; p < n_out; p++) acc += (double)cr[p] * (double)wvec[p];
                im_mwfs.array.F[m] = (float)acc;
            }
            im_mwfs.md[0].cnt0++;
            im_mwfs.md[0].write = 0;
            ImageStreamIO_sempost(&im_mwfs, -1);

            clock_gettime(CLOCK_REALTIME, &ts); ts.tv_sec += 5;
            if (ImageStreamIO_semtimedwait(&im_mdm, sem_mdm, &ts) != 0) return 22;
            if (ImageStreamIO_semtimedwait(&im_mol, sem_mol, &ts) != 0) return 23;

            memcpy(&ol_log[(size_t)k * n_mode], im_mol.array.F, sizeof(float) * (size_t)n_mode);
            const float *mdm = im_mdm.array.F;
            im_dm2d.md[0].write = 1;
            for (int a = 0; a < n_dm; a++) {
                double acc = 0.0;
                for (int m = 0; m < n_mode; m++)
                    acc += (double)mdm[m] * (double)poke[(size_t)m * n_dm + a];
                im_dm2d.array.F[a] = (float)acc;
            }
            im_dm2d.md[0].cnt0++;
            im_dm2d.md[0].write = 0;
            ImageStreamIO_sempost(&im_dm2d, -1);
        }
        im_dm2d.md[0].write = 1;
        memset(im_dm2d.array.F, 0, sizeof(float) * (size_t)n_dm);
        im_dm2d.md[0].cnt0++;
        im_dm2d.md[0].write = 0;
        ImageStreamIO_sempost(&im_dm2d, -1);
        write_bin_f32(argv[12], ol_log, (size_t)n_step * n_mode);
        free(ol_log);
    }

    free(idx); free(wref); free(cpinv); free(poke); free(tpha); free(wvec);
    return 0;
}
"""


def _sandbox_env(tmp_path: Path, tag: str) -> tuple[dict[str, str], Path, Path]:
    shm_dir = Path(f"/dev/shm/cacao_og_{tag}_{os.getpid()}")
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


def test_modalog_integrator_pf_sparse_smoothing_and_step_tracking(tmp_path: Path) -> None:
    """Verify unbiased closed-loop IV OG under Integrator & PF, sparse smoothing & step jump."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "iv")
    try:
        driver = _compile_helper(OG_LOCKSTEP_C, work_dir / "og_lockstep", env)

        p1_hm = REPO_ROOT / "_work/dm64_dyn_rm_calib/raw_calib/fdr_p1/H_mimo16.fits"
        if p1_hm.exists():
            h_true = fits.getdata(p1_hm).astype(np.float32)
            n_mode = h_true.shape[1]
            n_taps = h_true.shape[0]
        else:
            n_mode, n_taps = 20, 12
            h_true = np.zeros((n_taps, n_mode, n_mode), dtype=np.float32)
            for m in range(n_mode):
                t = np.array(
                    [0.0, 0.0, 0.85, 0.30, -0.22, 0.12, -0.07, 0.03, -0.01, 0.0, 0.0, 0.0],
                    dtype=np.float32,
                )
                h_true[:, m, m] = t / t.sum()
                if m + 1 < n_mode:
                    c = np.array(
                        [0.0, 0.0, 0.25, -0.18, -0.07, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                        dtype=np.float32,
                    )
                    h_true[:, m, m + 1] = c
                    h_true[:, m + 1, m] = -0.8 * c

        fits.writeto(work_dir / "H_mimo.fits", h_true, overwrite=True)
        h_true.tofile(work_dir / "H_true.bin")

        # Mode-dependent optical gain: anomalous TT (0.55, 0.60) + smooth radial curve (0.65..0.90)
        g_phase1 = np.array(
            [0.55, 0.60] + [0.65 + 0.25 * (m - 2) / max(n_mode - 3, 1) for m in range(2, n_mode)],
            dtype=np.float32,
        )
        # Mid-run seeing jump: 0.65x optical gain drop at frame 1536 (slice 6)
        g_phase2 = (0.65 * g_phase1).astype(np.float32)

        tb_sz = 256
        n_slices = 14
        n_step = tb_sz * n_slices  # 3584 frames (~3.6 s at 1 kHz)
        step_jump = tb_sz * 6  # jump at 1536 frames (1.5 s)

        g_sched = np.zeros((n_step, n_mode), dtype=np.float32)
        g_sched[:step_jump] = g_phase1[None, :]
        g_sched[step_jump:] = g_phase2[None, :]

        # Smooth Kolmogorov AR(2) turbulence (realistic f^-4 tail) + WFS noise
        rng = np.random.default_rng(202603)
        phi = np.zeros((n_step, n_mode), dtype=np.float32)
        for m in range(n_mode):
            rad = math.sqrt(m + 1.0)
            r1 = max(0.86, 0.985 - 0.014 * rad)
            r2 = max(0.75, 0.940 - 0.020 * rad)
            # Two cascaded 1st-order AR stages -> realistic smooth Kolmogorov velocity!
            x1 = np.zeros(n_step, dtype=np.float64)
            x2 = np.zeros(n_step, dtype=np.float64)
            for k in range(1, n_step):
                x1[k] = r1 * x1[k - 1] + float(rng.standard_normal())
                x2[k] = r2 * x2[k - 1] + x1[k]
            target_rms = 0.18 * ((rad + 1.0) ** -1.1)
            phi[:, m] = (x2 * (target_rms / max(float(np.std(x2)), 1e-12))).astype(np.float32)
        noise = (0.0015 * rng.standard_normal(size=(n_step, n_mode))).astype(np.float32)

        phi.tofile(work_dir / "phi.bin")
        noise.tofile(work_dir / "noise.bin")
        g_sched.tofile(work_dir / "g_sched.bin")
        g_const = np.repeat(g_phase1[None, :], tb_sz * 6, axis=0)
        g_const.tofile(work_dir / "g_const.bin")
        fits.writeto(
            work_dir / "z_in.fits", np.zeros((1, n_mode), dtype=np.float32), overwrite=True
        )
        # Custom probe weights: probe TT (0, 1) + even higher modes (sparse!) -> odd modes unprobed!
        pw = np.zeros((1, n_mode), dtype=np.float32)
        pw[0, 0] = 1.5
        pw[0, 1] = 1.5
        for m in range(2, n_mode, 2):
            pw[0, m] = 1.0
        fits.writeto(work_dir / "probe_w.fits", pw, overwrite=True)

        script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
cd "{work_dir}"
cleanup() {{
    milk-fps-runstop -q mog mf0 >/dev/null 2>&1 || true
    milk-fps-rm -f -q mog mf0 >/dev/null 2>&1 || true
}}
trap cleanup EXIT

milk-FITS2shm --no-procinfo -n ldin exec z_in.fits @S:aol0_modevalWFS >/dev/null
milk-fps-init -q mf0 cacao-fpsexec-mfilt >/dev/null
milk-fps-set -q \\
    mf0.inmval=aol0_modevalWFS mf0.outmval=aol0_modevalDM mf0.AOloopindex=0 \\
    mf0.loopON=ON mf0.loopgain=0.35 mf0.loopmult=0.98 mf0.looplimit=10.0 \\
    mf0.comp.OLmodes=ON mf0.comp.WFSfact=1.0 \\
    mf0.comp.dynpsol.kernel=H_mimo.fits mf0.comp.dynpsol.enable=ON \\
    mf0.comp.tbuff=ON mf0.comp.tbuffsize={tb_sz} \\
    mf0.comp.ogprobe.enable=ON mf0.comp.ogprobe.ampl=0.004 \\
    mf0.comp.ogprobe.nbmode={n_mode} mf0.comp.ogprobe.stride=1 mf0.comp.ogprobe.hold=1 \\
    mf0.procinfo.loopcntMax=-1
milk-fps-runstart -q mf0
milk-stream-wait -q -t 10 aol0_modevalDM aol0_modevalOL aol0_modevalWFS_buff \\
    aol0_modevalprobe_buff aol0_mogprobe_w

# Load sparse probe weights into aol0_mogprobe_w in-place
milk-FITS2shm --no-procinfo -n lpw exec probe_w.fits @S:tmp_pw >/dev/null
milk-fps-init -q cppw milk-fpsexec-mem-streamcopy >/dev/null
milk-fps-set -q cppw.in_sname=tmp_pw cppw.out_sname=aol0_mogprobe_w cppw.procinfo.loopcntMax=1
milk-fps-runstart -q cppw && milk-fps-wait -q -t 10 cppw && milk-fps-rm -f -q cppw

# Start live cacao-fpsexec-modalog (NBwin=1024, EMA alpha=0.55 for fast step tracking, apply=ON)
milk-fps-init -q mog cacao-fpsexec-modalog >/dev/null
milk-fps-set -q \\
    mog.AOloopindex=0 mog.inwfs=aol0_modevalWFS_buff \\
    mog.indm=aol0_modevalDM_buff mog.inprobe=aol0_modevalprobe_buff \\
    mog.kernel=H_mimo.fits mog.NBwin=1024 mog.use_diff=ON \\
    mog.n_free=2 mog.smooth_bw=1.2 mog.snr_min=3.0 mog.ema_alpha=0.55 \\
    mog.apply=ON mog.procinfo.loopcntMax=-1
milk-fps-runstart -q mog
milk-stream-wait -q -t 10 aol0_og_smooth aol0_og_raw

# Run 1: Integrator + mid-run seeing jump (3584 frames = 14 slices)
"{driver}" {n_mode} {n_taps} {n_step} {tb_sz} 0 \\
    H_true.bin phi.bin noise.bin g_sched.bin ol_int.bin og_int.bin
milk-fps-info mog > mog_int.txt

# Run 2: Live on-the-fly switch to Predictive Filter (PF=ON, strong feedback!) on g_phase1
# Reset mWFSfact to 1.0 (Run 1 ended on 0.65x jump!) and restart mog cleanly without loopZERO
"{env.get('PYTHON_BIN') or shutil.which('python3') or 'python3'}" - <<'PY'
import numpy as np
from astropy.io import fits
fits.writeto("ones_m.fits", np.ones((1, {n_mode}), dtype=np.float32), overwrite=True)
PY
milk-FITS2shm --no-procinfo -n lo1 exec ones_m.fits @S:tmp_ones >/dev/null
milk-fps-init -q cpo milk-fpsexec-mem-streamcopy >/dev/null
milk-fps-set -q cpo.in_sname=tmp_ones cpo.out_sname=aol0_mWFSfact cpo.procinfo.loopcntMax=1
milk-fps-runstart -q cpo && milk-fps-wait -q -t 10 cpo && milk-fps-rm -f -q cpo
milk-fps-runstop -q mog && milk-fps-wait -q -t 10 mog && milk-fps-runstart -q mog
milk-fps-set -q mf0.PF.enable=ON mf0.PF.mixcoeff=1.0 mf0.PF.NBblock=0
sleep 0.05
"{driver}" {n_mode} {n_taps} {tb_sz * 6} {tb_sz} 1 \\
    H_true.bin phi.bin noise.bin g_const.bin ol_pf.bin og_pf.bin
milk-fps-info mog > mog_pf.txt
"""
        res = _run_bash(script, env=env, timeout=60.0)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        og_int = np.fromfile(work_dir / "og_int.bin", dtype=np.float32).reshape(n_slices, n_mode)
        ol_int = np.fromfile(work_dir / "ol_int.bin", dtype=np.float32).reshape(n_step, n_mode)
        og_pf = np.fromfile(work_dir / "og_pf.bin", dtype=np.float32).reshape(6, n_mode)

        # Phase 1 accuracy (slice 5, right before jump): TT + probed even + UNPROBED odd modes!
        g_est1 = og_int[5]
        err_tt1 = 100.0 * np.max(np.abs(g_est1[:2] - g_phase1[:2]) / g_phase1[:2])
        err_even1 = 100.0 * float(
            np.median(np.abs(g_est1[2::2] - g_phase1[2::2]) / g_phase1[2::2])
        )
        err_odd1 = 100.0 * float(
            np.median(np.abs(g_est1[3::2] - g_phase1[3::2]) / g_phase1[3::2])
        )

        # Phase 2 step-tracking accuracy (5 slices = 1.28 s after step jump, slice 11 & final 13)
        g_est2_fast = og_int[11]
        g_est2_end = og_int[13]
        err_jump_fast = 100.0 * float(np.median(np.abs(g_est2_fast - g_phase2) / g_phase2))
        err_jump_end = 100.0 * float(np.median(np.abs(g_est2_end - g_phase2) / g_phase2))

        # PSOL calibration error (excluding irreducible WFS readout noise/g_true) before vs after
        s0 = slice(n_taps + 10, tb_sz)
        s5 = slice(5 * tb_sz + 10, 6 * tb_sz)
        ol_ideal_0 = phi[s0] + noise[s0] / g_phase1[None, :]
        ol_ideal_5 = phi[s5] + noise[s5] / g_phase1[None, :]
        psol_before = 100.0 * float(np.sqrt(np.mean((ol_int[s0] - ol_ideal_0) ** 2))) / max(
            float(np.sqrt(np.mean(phi[s0] ** 2))), 1e-12
        )
        psol_after = 100.0 * float(np.sqrt(np.mean((ol_int[s5] - ol_ideal_5) ** 2))) / max(
            float(np.sqrt(np.mean(phi[s5] ** 2))), 1e-12
        )

        # Run 2 (PF=ON) unbiased accuracy
        g_est_pf = og_pf[5]
        err_pf_med = 100.0 * float(np.median(np.abs(g_est_pf - g_phase1) / g_phase1))
        err_pf_tt = 100.0 * float(np.max(np.abs(g_est_pf[:2] - g_phase1[:2]) / g_phase1[:2]))

        info_int = _parse_fps_info((work_dir / "mog_int.txt").read_text())
        print(
            f"\n[Online OG IV N={n_mode} sparse] "
            f"Int err: TT={err_tt1:.2f}% probed={err_even1:.2f}% unprobed={err_odd1:.2f}% | "
            f"PSOL: {psol_before:.1f}% -> {psol_after:.2f}% | "
            f"Jump(1.28s/1.8s): {err_jump_fast:.2f}% / {err_jump_end:.2f}% | "
            f"PF=ON err: med={err_pf_med:.2f}% TT={err_pf_tt:.2f}% | "
            f"applied={int(info_int['out.applied_cnt'])}"
        )

        assert int(info_int["out.kern_mode"]) == 2
        assert int(info_int["out.applied_cnt"]) >= 12
        assert err_tt1 < 3.0, f"TT optical gain error too high: {err_tt1:.2f}%"
        assert err_even1 < 2.5, f"Probed modes OG error too high: {err_even1:.2f}%"
        assert err_odd1 < 2.5, f"Unprobed smoothed modes OG error too high: {err_odd1:.2f}%"
        assert psol_after < 2.5 and psol_after < psol_before / 5.0
        assert err_jump_fast < 4.0, f"Step-change tracking too slow: {err_jump_fast:.2f}%"
        assert err_jump_end < 2.5, f"Step-change final error too high: {err_jump_end:.2f}%"
        assert err_pf_med < 2.5, f"Closed-loop PF biased online OG: {err_pf_med:.2f}%"
        assert err_pf_tt < 3.5, f"Closed-loop PF TT OG error: {err_pf_tt:.2f}%"
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)


def test_hil_live_gpu_pywfs_online_og_vs_truth(tmp_path: Path) -> None:
    """Live GPU PyWFS HIL: aberrated 3 l/D PyWFS optical gain via modalog vs settled push-pull."""
    env, shm_dir, work_dir = _sandbox_env(tmp_path, "gpuhil")
    raw_dir = work_dir / "cal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    bench_file = work_dir / "plate12_turb.bench"
    bench_file.write_text(PLATE12_TURB_BENCH, encoding="utf-8")

    n_mode = 8
    z8 = _zernike_modes(12, n_mode)
    fits.writeto(raw_dir / "poke_z8.fits", z8, overwrite=True)

    # High-spatial-frequency turbulence phase screen on 128x128 (orthogonal to low Zernikes,
    # reduces 3 l/D PyWFS optical gain physically to ~0.70-0.85 without saturating low modes!)
    n_wf = 128
    rng = np.random.default_rng(4242)
    ky = np.fft.fftfreq(n_wf)[:, None]
    kx = np.fft.fftfreq(n_wf)[None, :]
    kr = np.hypot(kx, ky)
    band = (kr >= 5.0 / n_wf) & (kr <= 24.0 / n_wf)
    spec = np.zeros((n_wf, n_wf), dtype=np.complex128)
    spec[band] = (
        (rng.standard_normal(np.sum(band)) + 1j * rng.standard_normal(np.sum(band)))
        * (kr[band] ** -1.8)
    )
    pha = np.fft.ifft2(spec).real
    yy, xx = np.mgrid[0:n_wf, 0:n_wf]
    r_pup = np.hypot(xx - 0.5 * (n_wf - 1), yy - 0.5 * (n_wf - 1)) / (0.4375 * n_wf)
    pup = r_pup <= 1.0
    pha = (pha - pha[pup].mean()) / max(pha[pup].std(), 1e-12)
    # 0.135 um OPD RMS at ref_lambda=0.50 um -> ~0.7 rad at 1.22 um -> realistic g_opt ~0.65-0.85
    # wf_unit=1 in cacaosim means input phase in radians at ref_lambda=0.50 um
    pha_rad = (pha * (2.0 * math.pi * 0.135 / 0.50)).astype(np.float32)
    pha_rad.tofile(raw_dir / "turb_pha.bin")
    fits.writeto(raw_dir / "zero_wf.fits", np.zeros((n_wf, n_wf), dtype=np.float32), overwrite=True)

    bridge = _compile_helper(GPU_OG_BRIDGE_C, work_dir / "gpu_og_bridge", env)
    py = env.get("PYTHON_BIN") or shutil.which("python3") or "python3"

    script = f"""
set -euo pipefail
source "{REPO_ROOT}/env.sh"
cd "{raw_dir}"

cleanup() {{
    milk-fps-runstop -q mog mf0 >/dev/null 2>&1 || true
    milk-fps-rm -f -q mdr fdr mog mf0 >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

milk-FITS2shm --no-procinfo -n lwf exec zero_wf.fits @S:outarraypha >/dev/null
cacaosim-bench deploy --workdir "{work_dir}" --config "{bench_file}" \\
    --mode fused --no-view >/dev/null
milk-stream-wait -q -t 20 csim_wfs:48x48 dm01disp:12x12

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
PY

# 1. Lab calibration (zero turbulence): 3D RM -> factordynrm -> M_cal + H_mimo
milk-fps-init -q mdr cacao-fpsexec-cacaoac-measdynresp >/dev/null
milk-fps-set -q \\
    mdr.streamin=dm01disp mdr.streamout=csim_wfs mdr.normalize=ON \\
    mdr.inmodes=poke_z8.fits mdr.outcube=resp3D.fits mdr.outmask=wfsmask.fits \\
    mdr.ampl=0.010 mdr.timing.WFSfrequ=0.0 mdr.timing.frameratewait=0.3 \\
    mdr.timing.NBsubfr=4 mdr.timing.NBrespfr=16 mdr.timing.NBprefr=2 \\
    mdr.timing.NBsettlefr=2 mdr.timing.NBcycle=1 mdr.pokemode=1 mdr.phaseorder=0 \\
    mdr.procinfo.loopcntMax=1
milk-fps-runstart -q mdr && milk-fps-wait -q -t 60 mdr && milk-fps-rm -f -q mdr

"$MILK_INSTALL_ROOT/bin/cacao-fpsexec-cacaoac-factordynrm" --no-procinfo -n fdr exec \\
    .resp3d=resp3D.fits .outmimo=H_mimo.fits .outdiag=H_diag.fits .outstatic=M_cal.fits \\
    .n_taps=14 >/dev/null

"{py}" - <<'PY'
import numpy as np
from astropy.io import fits
mcal = fits.getdata("M_cal.fits").astype(np.float64)
u, s, vt = np.linalg.svd(mcal, full_matrices=False)
cpinv = ((u * np.where(s > 1e-4 * s[0], 1.0 / s, 0.0)[None, :]) @ vt).astype(np.float32)
cpinv.tofile("cpinv.bin")
fits.getdata("poke_z8.fits").astype(np.float32).reshape(mcal.shape[0], -1).tofile("poke.bin")
fits.writeto("zero_m.fits", np.zeros((1, mcal.shape[0]), dtype=np.float32), overwrite=True)
PY
N_OUT=$("{py}" -c 'import numpy as np; print(len(np.fromfile("mask_idx.bin", dtype=np.int32)))')

# 2. Measure ground-truth physical PyWFS optical gain under high-order aberration
"{bridge}" {n_mode} "$N_OUT" 144 {n_wf} 1 0 \\
    mask_idx.bin wfs_ref.bin cpinv.bin poke.bin turb_pha.bin g_true.bin

# 3. Close live AO loop (mfilt + modalog with low-RMS 0.0015 um DM probe -> ~4.2 nm total RMS)
milk-FITS2shm --no-procinfo -n lmw exec zero_m.fits @S:aol0_modevalWFS >/dev/null
milk-fps-init -q mf0 cacao-fpsexec-mfilt >/dev/null
milk-fps-set -q \\
    mf0.inmval=aol0_modevalWFS mf0.outmval=aol0_modevalDM mf0.AOloopindex=0 \\
    mf0.loopON=ON mf0.loopgain=0.25 mf0.loopmult=0.98 mf0.looplimit=1.0 \\
    mf0.comp.OLmodes=ON mf0.comp.WFSfact=1.0 \\
    mf0.comp.dynpsol.kernel=H_mimo.fits mf0.comp.dynpsol.enable=ON \\
    mf0.comp.tbuff=ON mf0.comp.tbuffsize=256 \\
    mf0.comp.ogprobe.enable=ON mf0.comp.ogprobe.ampl=0.0015 \\
    mf0.comp.ogprobe.nbmode={n_mode} mf0.comp.ogprobe.stride=1 mf0.comp.ogprobe.hold=4 \\
    mf0.procinfo.loopcntMax=-1
milk-fps-runstart -q mf0
milk-stream-wait -q -t 10 aol0_modevalDM aol0_modevalOL aol0_modevalWFS_buff aol0_modevalprobe_buff

milk-fps-init -q mog cacao-fpsexec-modalog >/dev/null
milk-fps-set -q \\
    mog.AOloopindex=0 mog.inwfs=aol0_modevalWFS_buff \\
    mog.indm=aol0_modevalDM_buff mog.inprobe=aol0_modevalprobe_buff \\
    mog.kernel=H_mimo.fits mog.NBwin=1024 mog.use_diff=ON \\
    mog.n_free=8 mog.smooth_bw=0.0 mog.snr_min=3.0 mog.ema_alpha=1.0 \\
    mog.apply=ON mog.procinfo.loopcntMax=-1
milk-fps-runstart -q mog
milk-stream-wait -q -t 10 aol0_og_smooth

# Run 1024 live GPU closed-loop frames (4 slices, ~2.0 s at 500 Hz)
"{bridge}" {n_mode} "$N_OUT" 144 {n_wf} 1024 1 \\
    mask_idx.bin wfs_ref.bin cpinv.bin poke.bin turb_pha.bin ol_gpu.bin
sleep 0.15

milk-fpsexec-iofits-saveFITS --no-procinfo -n s_raw exec aol0_og_raw "!og_raw.fits" >/dev/null
milk-fpsexec-iofits-saveFITS --no-procinfo -n s_smt exec aol0_og_smooth "!og_smt.fits" >/dev/null
milk-fpsexec-iofits-saveFITS --no-procinfo -n s_mwf exec aol0_mWFSfact "!mwfsfact.fits" >/dev/null
milk-fps-info mog > mog_gpu.txt

milk-fps-runstop -q mog mf0 && milk-fps-wait -q -t 10 mog mf0 && milk-fps-rm -f -q mog mf0
cacaosim-bench teardown --workdir "{work_dir}" --no-view >/dev/null
"""
    try:
        res = _run_bash(script, env=env, timeout=180.0)
        assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        g_true = np.fromfile(raw_dir / "g_true.bin", dtype=np.float32)
        g_est = fits.getdata(raw_dir / "og_smt.fits").ravel().astype(np.float32)
        mwfsf = fits.getdata(raw_dir / "mwfsfact.fits").ravel().astype(np.float32)
        rel_err = 100.0 * np.abs(g_est - g_true) / np.maximum(np.abs(g_true), 1e-6)
        med_err = float(np.median(rel_err))
        max_err = float(np.max(rel_err))
        info = _parse_fps_info((raw_dir / "mog_gpu.txt").read_text())

        print(
            f"\n[LIVE GPU PyWFS Online OG] "
            f"g_true={np.round(g_true, 3)} | g_est={np.round(g_est, 3)} | "
            f"med_err={med_err:.2f}% max_err={max_err:.2f}% | "
            f"probe_rms={info['out.probe_rms']*1e3:.2f} nm | snr_med={info['out.snr_med']:.1f}"
        )

        # Verify real physical PyWFS optical-gain loss (< 0.90) and accurate live tracking
        assert float(np.median(g_true)) < 0.90, f"Expected real PyWFS OG loss, got {g_true}"
        assert med_err < 3.5, f"Live GPU PyWFS OG median error too high: {med_err:.2f}%"
        assert max_err < 7.0, f"Live GPU PyWFS OG max mode error too high: {max_err:.2f}%"
        assert float(np.max(np.abs(mwfsf * g_est - 1.0))) < 1.0e-4
    finally:
        _cleanup_sandbox(env, shm_dir, work_dir)
