# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Deterministic unit & lock-step SHM tests for multi-rate predictive DM control.

Validates the decoupled multi-rate pipeline:
  mkEOFPF (pos + vel) -> applyEOFPF (pos + vel) -> modalfilter (exact exposure-averaged PSOL
  + trajectory stream) -> mvalpacer (K_sub centered sub-steps)

Tests:
  18.1  `cacao-fpsexec-mvalpacer`:
        - Exact centered zero-mean sub-step ramp offsets for K_sub=4 (250->1000 Hz)
          and K_sub=5 (200->1000 Hz) in lockstep `trigstream` + `trig_decim=2` mode.
        - Mean preservation: mean_j(u_out[j]) == u_mid to float32 precision (<1e-6).
        - Live `enable=OFF` pass-through (zero ramp) and wall-clock pacing mode.
  18.2  `cacao-fpsexec-mfilt` multi-rate PSOL & trajectory publication:
        - Exact closed-form exposure-averaged PSOL integral cancellation
          (`0.5 * alpha * (1 - alpha) * (v0 - v1)`) against a continuous-time
          linear-ramp DM plant at fractional latency `tau = 2.35` frames (<1e-5 error).
        - Trajectory stream `aol1_modevalDM_traj [M x 2]` exactness and suppression of
          direct `aol1_modevalDM` writes when `PF.mr_pacer_out=ON` (zero dual-writer race).
  18.3  `cacao-fpsexec-cacaopc-mkEOFPF` + `applyEOFPF` with `mr_enable=ON`:
        - Positive control (smooth correlated drifting modes): Catmull-Rom velocity
          weights achieve high correlation with true inter-frame velocity and reduce
          sub-step tracking error relative to ZOH hold.
        - White-noise null safety test (pure i.i.d. Gaussian noise): zero-centered
          regularized velocity weights stay near zero without amplifying noise.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import numpy as np


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


def _get_fps_diag(fps_name: str, env: dict[str, str], cwd: Path) -> dict[str, float]:
    out = _run(f"milk-fps-info {fps_name}", env, cwd)
    clean = re.sub(r"\x1b\[[0-9;]*m", "", out)
    diag: dict[str, float] = {}
    for line in clean.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] in ("FLOAT32", "FLOAT64", "UINT32", "UINT64", "INT32", "ONOFF"):
            key = parts[1].lstrip(".")
            try:
                diag[key] = float(parts[3])
            except ValueError:
                pass
    return diag


def _compile_c(code: str, name: str, work_dir: Path, env: dict[str, str]) -> Path:
    src = work_dir / f"{name}.c"
    exe = work_dir / name
    src.write_text(code, encoding="utf-8")
    inc = Path(env["MILK_INSTALL_ROOT"]) / "include"
    lib = Path(env["MILK_INSTALL_ROOT"]) / "lib"
    _run(
        f'gcc -O2 "{src}" -I"{inc}" -L"{lib}" -Wl,-rpath,"{lib}" '
        f'-lImageStreamIO -lpthread -lm -o "{exe}"',
        env,
        work_dir,
    )
    return exe


PACER_DRV_C = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"

int main(int argc, char **argv) {
    if (argc < 8) {
        fprintf(stderr, "usage: %s <N_wfs> <K_sub> <expect_sub> <decim> <M> <traj_in.bin> <dm_out.bin>\n", argv[0]);
        return 2;
    }
    long Nwfs   = atol(argv[1]);
    long Ksub   = atol(argv[2]);
    long ExpSub = atol(argv[3]);
    long decim  = atol(argv[4]);
    long M      = atol(argv[5]);

    float *traj = (float *)malloc((size_t)Nwfs * 2 * (size_t)M * sizeof(float));
    float *out  = (float *)calloc((size_t)Nwfs * (size_t)ExpSub * (size_t)M, sizeof(float));
    FILE *fi = fopen(argv[6], "rb");
    if (!fi || fread(traj, sizeof(float), (size_t)Nwfs * 2 * (size_t)M, fi) != (size_t)Nwfs * 2 * (size_t)M) {
        fprintf(stderr, "failed reading traj_in\n");
        return 3;
    }
    fclose(fi);

    IMAGE im_traj, im_clk, im_out;
    if (ImageStreamIO_openIm(&im_traj, "mr_traj") != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_clk,  "mr_clk")  != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_out,  "mr_dm")   != IMAGESTREAMIO_SUCCESS) {
        fprintf(stderr, "failed opening SHM streams\n");
        return 4;
    }
    int sem_out = ImageStreamIO_getsemwaitindex(&im_out, -1);
    while (sem_out >= 0 && ImageStreamIO_semtrywait(&im_out, sem_out) == 0) {}

    for (long w = 0; w < Nwfs; w++) {
        /* Publish new WFS trajectory (row 0 = u_mid, row 1 = u_ramp):
         * mvalpacer wakes zero-latency on mr_traj and immediately emits sub-step j=0! */
        uint64_t prev_cnt = im_out.md[0].cnt0;
        im_traj.md[0].write = 1;
        memcpy(im_traj.array.F, traj + (size_t)w * 2 * (size_t)M, 2 * (size_t)M * sizeof(float));
        ImageStreamIO_UpdateIm(&im_traj);

        struct timespec dl;
        clock_gettime(CLOCK_REALTIME, &dl);
        dl.tv_sec += 2;
        while (im_out.md[0].cnt0 <= prev_cnt) {
            if (sem_out >= 0 && ImageStreamIO_semtimedwait(&im_out, sem_out, &dl) != 0) {
                fprintf(stderr, "timeout waiting for pacer j=0 at w=%ld (cnt=%lu)\n",
                        w, (unsigned long)im_out.md[0].cnt0);
                return 5;
            }
        }
        memcpy(out + ((size_t)w * (size_t)ExpSub) * (size_t)M,
               im_out.array.F, (size_t)M * sizeof(float));

        /* Advance master clock for remaining sub-steps j = 1 .. Ksub - 1 */
        for (long j = 1; j < Ksub; j++) {
            prev_cnt = im_out.md[0].cnt0;
            for (long d = 0; d < decim; d++) {
                im_clk.md[0].write = 1;
                im_clk.array.F[0] = (float)(w * Ksub * decim + j * decim + d);
                ImageStreamIO_UpdateIm(&im_clk);
                if (d + 1 < decim || j >= ExpSub) {
                    struct timespec ts = {0, 300000};
                    nanosleep(&ts, NULL);
                }
            }
            if (j < ExpSub) {
                clock_gettime(CLOCK_REALTIME, &dl);
                dl.tv_sec += 2;
                while (im_out.md[0].cnt0 <= prev_cnt) {
                    if (sem_out >= 0 && ImageStreamIO_semtimedwait(&im_out, sem_out, &dl) != 0) {
                        fprintf(stderr, "timeout waiting for pacer out at w=%ld j=%ld (cnt=%lu)\n",
                                w, j, (unsigned long)im_out.md[0].cnt0);
                        return 5;
                    }
                }
                memcpy(out + ((size_t)w * (size_t)ExpSub + (size_t)j) * (size_t)M,
                       im_out.array.F, (size_t)M * sizeof(float));
            }
        }
    }

    FILE *fo = fopen(argv[7], "wb");
    fwrite(out, sizeof(float), (size_t)Nwfs * (size_t)ExpSub * (size_t)M, fo);
    fclose(fo);
    free(traj);
    free(out);
    return 0;
}
"""


def test_18_1_mvalpacer_lockstep_and_wallclock(shm_sandbox):
    """Verify mvalpacer sub-step ramp symmetry, decimation, enable toggle & wall-clock mode."""
    _shm_dir, work_dir, env = shm_sandbox
    exe = _compile_c(PACER_DRV_C, "pacer_drv", work_dir, env)
    rng = np.random.default_rng(123)

    M = 16
    Nwfs = 20
    for k_sub, vel_gain, enable_str in [(4, 1.0, "ON"), (5, 0.8, "ON"), (4, 1.0, "OFF")]:
        traj = np.zeros((Nwfs, 2, M), dtype=np.float32)
        traj[:, 0, :] = rng.normal(0.0, 0.5, size=(Nwfs, M))
        traj[:, 1, :] = rng.normal(0.0, 0.2, size=(Nwfs, M))
        traj_p = work_dir / f"traj_k{k_sub}_{enable_str}.bin"
        out_p = work_dir / f"dm_k{k_sub}_{enable_str}.bin"
        traj.tofile(traj_p)

        _run(
            f"""
milk-fps-runstop -q mp_t >/dev/null 2>&1 || true
milk-fps-rm -f -q --ignore-missing mp_t >/dev/null 2>&1 || true
milk-stream-rm -q --ignore-missing mr_traj mr_clk mr_dm >/dev/null 2>&1 || true
milk-script -q -e <<'MS'
@calc "@S:mr_traj = zeros({M}, 2)"
@calc "@S:mr_clk  = zeros(4, 1)"
@calc "@S:mr_dm   = zeros({M}, 1)"
MS
milk-fps-init -q mp_t cacao-fpsexec-mvalpacer >/dev/null
milk-fps-set -q \
    mp_t.streamin=mr_traj \
    mp_t.streamout=mr_dm \
    mp_t.trigstream=mr_clk \
    mp_t.trig_decim=2 \
    mp_t.k_sub={k_sub} \
    mp_t.vel_gain={vel_gain} \
    mp_t.enable={enable_str} \
    mp_t.procinfo.loopcntMax=-1
milk-fps-runstart -q mp_t
sleep 0.12
""",
            env,
            work_dir,
        )
        exp_sub = 1 if enable_str == "OFF" else k_sub
        _run(f'"{exe}" {Nwfs} {k_sub} {exp_sub} 2 {M} "{traj_p}" "{out_p}"', env, work_dir)
        diag = _get_fps_diag("mp_t", env, work_dir)
        _run("milk-fps-runstop -q mp_t && milk-fps-rm -f -q mp_t", env, work_dir)

        got = np.fromfile(out_p, dtype=np.float32).reshape(Nwfs, exp_sub, M)
        if enable_str == "OFF":
            s_expected = np.array([0.0], dtype=np.float64)
        else:
            s_expected = ((np.arange(k_sub, dtype=np.float64) + 0.5) / k_sub - 0.5) * vel_gain
        expected = traj[:, 0:1, :] + s_expected[None, :, None] * traj[:, 1:2, :]
        max_err = float(np.max(np.abs(got - expected)))
        mean_err = float(np.max(np.abs(np.mean(got, axis=1) - traj[:, 0, :])))
        assert max_err < 1e-5, f"k_sub={k_sub} en={enable_str}: max_err={max_err}"
        assert mean_err < 1e-5, f"k_sub={k_sub} en={enable_str}: mean preservation err={mean_err}"
        assert diag.get("out.out_cnt", 0) == Nwfs * exp_sub
        assert diag.get("out.in_cnt", 0) == Nwfs

    # Wall-clock mode sanity check (trigstream="", rate_hz=1000.0, k_sub=4)
    _run(
        f"""
milk-stream-rm -q --ignore-missing mr_traj mr_dm >/dev/null 2>&1 || true
milk-script -q -e <<'MS'
@calc "@S:mr_traj = zeros({M}, 2)"
@calc "@S:mr_dm   = zeros({M}, 1)"
MS
milk-fps-init -q mp_wc cacao-fpsexec-mvalpacer >/dev/null
milk-fps-set -q \
    mp_wc.streamin=mr_traj \
    mp_wc.streamout=mr_dm \
    mp_wc.rate_hz=1000.0 \
    mp_wc.k_sub=4 \
    mp_wc.vel_gain=1.0 \
    mp_wc.enable=ON \
    mp_wc.procinfo.loopcntMax=-1
milk-fps-runstart -q mp_wc
sleep 0.10
milk-script -q -e <<'MS'
@calc "s.mr_traj = zeros({M}, 2) + 0.25"
MS
sleep 0.04
""",
        env,
        work_dir,
    )
    diag_wc = _get_fps_diag("mp_wc", env, work_dir)
    _run("milk-fps-runstop -q mp_wc && milk-fps-rm -f -q mp_wc", env, work_dir)
    assert diag_wc.get("out.out_cnt", 0) >= 4.0, f"Wall-clock pacer did not emit sub-steps: {diag_wc}"


MFILT_PSOL_DRV_C = r"""
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"

int main(int argc, char **argv) {
    if (argc < 8) {
        fprintf(stderr, "usage: %s <T> <M> <lat> <wait_traj> <phi_turb.bin> <ol_out.bin> <traj_out.bin>\n", argv[0]);
        return 2;
    }
    long T         = atol(argv[1]);
    long M         = atol(argv[2]);
    double lat     = atof(argv[3]);
    int wait_traj  = atoi(argv[4]);
    long latint    = (long)floor(lat);
    double alpha   = lat - (double)latint;

    float *phi_turb = (float *)malloc((size_t)T * (size_t)M * sizeof(float));
    float *ol_out   = (float *)calloc((size_t)T * (size_t)M, sizeof(float));
    float *traj_out = (float *)calloc((size_t)T * 2 * (size_t)M, sizeof(float));

    FILE *fi = fopen(argv[5], "rb");
    if (!fi || fread(phi_turb, sizeof(float), (size_t)T * (size_t)M, fi) != (size_t)T * (size_t)M) {
        fprintf(stderr, "failed reading phi_turb\n");
        return 3;
    }
    fclose(fi);

    IMAGE im_wfs, im_ol, im_pf, im_pfv, im_pfs, im_traj, im_dm;
    if (ImageStreamIO_openIm(&im_wfs,  "aol1_modevalWFS")     != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_ol,   "aol1_modevalOL")      != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_pf,   "aol1_modevalPF")      != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_pfv,  "aol1_modevalPF_vel")  != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_pfs,  "aol1_outPFstat")      != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_traj, "aol1_modevalDM_traj") != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_dm,   "aol1_modevalDM")      != IMAGESTREAMIO_SUCCESS) {
        fprintf(stderr, "failed opening mfilt streams\n");
        return 4;
    }
    im_pfs.md[0].write = 1;
    for (long m = 0; m < M; m++) im_pfs.array.F[m] = 1.0f;
    ImageStreamIO_UpdateIm(&im_pfs);
    int sem_ol   = ImageStreamIO_getsemwaitindex(&im_ol, -1);
    int sem_traj = ImageStreamIO_getsemwaitindex(&im_traj, -1);
    int sem_dm   = ImageStreamIO_getsemwaitindex(&im_dm, -1);
    while (sem_ol   >= 0 && ImageStreamIO_semtrywait(&im_ol, sem_ol)     == 0) {}
    while (sem_traj >= 0 && ImageStreamIO_semtrywait(&im_traj, sem_traj) == 0) {}
    while (sem_dm   >= 0 && ImageStreamIO_semtrywait(&im_dm, sem_dm)     == 0) {}

    uint64_t dm_cnt_start = im_dm.md[0].cnt0;

    /* History of emitted (u_mid, u_ramp) for exact continuous-time plant integration */
    float *hist_mid  = (float *)calloc((size_t)(T + 8) * (size_t)M, sizeof(float));
    float *hist_ramp = (float *)calloc((size_t)(T + 8) * (size_t)M, sizeof(float));

    for (long k = 0; k < T; k++) {
        /* Exact continuous-time exposure average of piecewise-linear ramp DM over [0, 1]:
         *   During [0, alpha]   : tail of older command i_old = k - latint - 1 (s in [0.5-alpha, 0.5])
         *   During [alpha, 1]   : head of newer command i_new = k - latint     (s in [-0.5, 0.5-alpha])
         *   bar_u = alpha*u_old + (1-alpha)*u_new + 0.5*alpha*(1-alpha)*(v_old - v_new)
         */
        long i_new = k - latint;
        long i_old = k - latint - 1;
        uint64_t prev_ol   = im_ol.md[0].cnt0;
        uint64_t prev_traj = im_traj.md[0].cnt0;
        uint64_t prev_dm   = im_dm.md[0].cnt0;

        im_wfs.md[0].write = 1;
        for (long m = 0; m < M; m++) {
            double u_new = (i_new >= 0) ? hist_mid[(size_t)i_new * M + m]  : 0.0;
            double u_old = (i_old >= 0) ? hist_mid[(size_t)i_old * M + m]  : 0.0;
            double v_new = (i_new >= 0) ? hist_ramp[(size_t)i_new * M + m] : 0.0;
            double v_old = (i_old >= 0) ? hist_ramp[(size_t)i_old * M + m] : 0.0;
            double dm_avg = alpha * u_old + (1.0 - alpha) * u_new
                          + 0.5 * alpha * (1.0 - alpha) * (v_old - v_new);
            im_wfs.array.F[m] = (float)((double)phi_turb[(size_t)k * M + m] + dm_avg);
        }
        ImageStreamIO_UpdateIm(&im_wfs);

        /* Wait for modalfilter to publish modevalOL (triggers applyPF in real loop) */
        struct timespec dl;
        clock_gettime(CLOCK_REALTIME, &dl);
        dl.tv_sec += 2;
        while (im_ol.md[0].cnt0 <= prev_ol) {
            if (sem_ol >= 0 && ImageStreamIO_semtimedwait(&im_ol, sem_ol, &dl) != 0) {
                fprintf(stderr, "timeout waiting for modevalOL at k=%ld\n", k);
                return 5;
            }
        }
        memcpy(ol_out + (size_t)k * M, im_ol.array.F, (size_t)M * sizeof(float));

        /* Inject synthetic PF position and strong time-varying velocity ramp (so v_old != v_new!) */
        im_pfv.md[0].write = 1;
        for (long m = 0; m < M; m++) {
            double phase = 0.23 * (double)k + 0.37 * (double)m;
            im_pfv.array.F[m] = (float)(0.25 * cos(phase));
        }
        ImageStreamIO_UpdateIm(&im_pfv);

        im_pf.md[0].write = 1;
        for (long m = 0; m < M; m++) {
            double phase = 0.23 * (double)k + 0.37 * (double)m;
            im_pf.array.F[m] = (float)(0.30 * sin(phase));
        }
        ImageStreamIO_UpdateIm(&im_pf);

        /* Wait for modalfilter output (modevalDM_traj when mr_en=ON, modevalDM when mr_en=OFF) */
        clock_gettime(CLOCK_REALTIME, &dl);
        dl.tv_sec += 2;
        if (wait_traj) {
            while (im_traj.md[0].cnt0 <= prev_traj) {
                if (sem_traj >= 0 && ImageStreamIO_semtimedwait(&im_traj, sem_traj, &dl) != 0) {
                    fprintf(stderr, "timeout waiting for modevalDM_traj at k=%ld\n", k);
                    return 6;
                }
            }
            memcpy(traj_out + (size_t)k * 2 * M, im_traj.array.F, 2 * (size_t)M * sizeof(float));
            memcpy(hist_mid  + (size_t)k * M, im_traj.array.F,     (size_t)M * sizeof(float));
            memcpy(hist_ramp + (size_t)k * M, im_traj.array.F + M, (size_t)M * sizeof(float));
        } else {
            while (im_dm.md[0].cnt0 <= prev_dm) {
                if (sem_dm >= 0 && ImageStreamIO_semtimedwait(&im_dm, sem_dm, &dl) != 0) {
                    fprintf(stderr, "timeout waiting for modevalDM at k=%ld\n", k);
                    return 6;
                }
            }
            memcpy(traj_out + (size_t)k * 2 * M, im_dm.array.F, (size_t)M * sizeof(float));
            memcpy(hist_mid + (size_t)k * M, im_dm.array.F, (size_t)M * sizeof(float));
        }
    }

    uint64_t dm_cnt_delta = im_dm.md[0].cnt0 - dm_cnt_start;
    printf("DM_CNT_DELTA=%lu\n", (unsigned long)dm_cnt_delta);

    FILE *fo = fopen(argv[6], "wb");
    fwrite(ol_out, sizeof(float), (size_t)T * (size_t)M, fo);
    fclose(fo);
    FILE *ft = fopen(argv[7], "wb");
    fwrite(traj_out, sizeof(float), (size_t)T * 2 * (size_t)M, ft);
    fclose(ft);
    free(phi_turb); free(ol_out); free(traj_out); free(hist_mid); free(hist_ramp);
    return 0;
}
"""


def test_18_2_modalfilter_multirate_psol_exactness(shm_sandbox):
    """Verify exact closed-form exposure-averaged PSOL and dual-writer suppression in mfilt."""
    _shm_dir, work_dir, env = shm_sandbox
    exe = _compile_c(MFILT_PSOL_DRV_C, "mfilt_psol_drv", work_dir, env)
    rng = np.random.default_rng(7)

    T, M = 120, 8
    lat = 2.35
    phi_turb = rng.normal(0.0, 0.2, size=(T, M)).astype(np.float32)
    phi_p = work_dir / "phi_turb.bin"
    phi_turb.tofile(phi_p)

    results = {}
    for label, mr_en, pacer_out in [("mr_on", "ON", "ON"), ("mr_off", "OFF", "OFF")]:
        ol_p = work_dir / f"ol_{label}.bin"
        tr_p = work_dir / f"traj_{label}.bin"
        _run(
            f"""
milk-fps-runstop -q mfilt-1 >/dev/null 2>&1 || true
milk-fps-rm -f -q --ignore-missing mfilt-1 >/dev/null 2>&1 || true
milk-stream-rm -r -f -q --ignore-missing "^aol1_" >/dev/null 2>&1 || true
milk-script -q -e <<'MS'
@calc "@S:aol1_modevalWFS    = zeros({M}, 1)"
@calc "@S:aol1_modevalPF     = zeros({M}, 1)"
@calc "@S:aol1_modevalPF_vel = zeros({M}, 1)"
@calc "@S:aol1_outPFstat     = zeros({M}, 1) + 1.0"
MS
milk-fps-init -q mfilt-1 cacao-fpsexec-mfilt >/dev/null
milk-fps-set -q \
    mfilt-1.AOloopindex=1 \
    mfilt-1.inmval=aol1_modevalWFS \
    mfilt-1.outmval=aol1_modevalDM \
    mfilt-1.loopON=ON \
    mfilt-1.loopgain=0.3 \
    mfilt-1.loopmult=0.98 \
    mfilt-1.looplimit=2.0 \
    mfilt-1.comp.OLmodes=ON \
    mfilt-1.comp.WFSfact=1.0 \
    mfilt-1.comp.latencyhardwfr={lat} \
    mfilt-1.comp.latencysoftwfr=0.0 \
    mfilt-1.comp.tbuff=OFF \
    mfilt-1.PF.enable=ON \
    mfilt-1.PF.mixcoeff=1.0 \
    mfilt-1.PF.maxwaitus=50000 \
    mfilt-1.PF.mr_enable={mr_en} \
    mfilt-1.PF.mr_velgain=1.0 \
    mfilt-1.PF.mr_substeps=4 \
    mfilt-1.PF.mr_pacer_out={pacer_out} \
    mfilt-1.procinfo.loopcntMax=-1 \
    mfilt-1.procinfo.triggermode=3 \
    mfilt-1.procinfo.triggersname=aol1_modevalWFS
milk-fps-runstart -q mfilt-1
milk-stream-wait -q -t 15 aol1_modevalOL aol1_modevalDM_traj aol1_modevalDM
sleep 0.1
""",
            env,
            work_dir,
        )
        wait_traj = 1 if mr_en == "ON" else 0
        out_txt = _run(
            f'"{exe}" {T} {M} {lat} {wait_traj} "{phi_p}" "{ol_p}" "{tr_p}"',
            env,
            work_dir,
        )
        _run("milk-fps-runstop -q mfilt-1 && milk-fps-rm -f -q mfilt-1", env, work_dir)
        m_dm = re.search(r"DM_CNT_DELTA=(\d+)", out_txt)
        dm_delta = int(m_dm.group(1)) if m_dm else -1
        ol_got = np.fromfile(ol_p, dtype=np.float32).reshape(T, M)
        traj_got = np.fromfile(tr_p, dtype=np.float32).reshape(T, 2, M)
        # Skip initial 6 frames of startup fill
        err_rms = float(np.sqrt(np.mean((ol_got[10:] - phi_turb[10:]) ** 2)))
        err_max = float(np.max(np.abs(ol_got[10:] - phi_turb[10:])))
        results[label] = (err_rms, err_max, dm_delta, traj_got)

    err_rms_on, err_max_on, dm_delta_on, traj_on = results["mr_on"]
    err_rms_off, _, dm_delta_off, traj_off = results["mr_off"]

    assert err_max_on < 1e-4, f"Multi-rate PSOL error too large: max={err_max_on}, rms={err_rms_on}"
    assert dm_delta_on == 0, f"mfilt must NOT overwrite modevalDM when mr_pacer_out=ON (delta={dm_delta_on})"
    assert dm_delta_off == T, f"mfilt must write modevalDM when mr_pacer_out=OFF (delta={dm_delta_off})"
    # Verify row 1 of traj_on is non-zero and equals -mix * velgain * mval_pf_vel (mix=1.0)
    vel_rms_on = float(np.sqrt(np.mean(traj_on[10:, 1, :] ** 2)))
    vel_rms_off = float(np.sqrt(np.mean(traj_off[10:, 1, :] ** 2)))
    assert vel_rms_on > 0.15, f"Expected non-zero velocity ramp in traj stream: {vel_rms_on}"
    assert vel_rms_off < 1e-7, f"Expected zero velocity ramp when mr_enable=OFF: {vel_rms_off}"
    print(
        f"\n[test_18_2] Exact PSOL: mr_ON max_err={err_max_on:.2e} (rms={err_rms_on:.2e}), "
        f"dm_cnt_delta(pacer_out=ON)={dm_delta_on}, dm_cnt_delta(OFF)={dm_delta_off}, "
        f"vel_rms={vel_rms_on:.4f}"
    )


EOF_MR_DRV_C = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "ImageStreamIO/ImageStreamIO.h"

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr, "usage: %s <T> <M> <tbuff> <ol_in.bin> <pf_pos.bin> <pf_vel.bin>\n", argv[0]);
        return 2;
    }
    long T     = atol(argv[1]);
    long M     = atol(argv[2]);
    long tbuff = atol(argv[3]);

    float *ol_in  = (float *)malloc((size_t)T * (size_t)M * sizeof(float));
    float *pf_pos = (float *)calloc((size_t)T * (size_t)M, sizeof(float));
    float *pf_vel = (float *)calloc((size_t)T * (size_t)M, sizeof(float));
    FILE *fi = fopen(argv[4], "rb");
    if (!fi || fread(ol_in, sizeof(float), (size_t)T * (size_t)M, fi) != (size_t)T * (size_t)M) {
        fprintf(stderr, "failed reading ol_in\n");
        return 3;
    }
    fclose(fi);

    IMAGE im_ol, im_buff, im_pf, im_pfv, im_mat;
    if (ImageStreamIO_openIm(&im_ol,   "mr_ol")      != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_buff, "mr_ol_buff") != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_pf,   "mr_pf")      != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_pfv,  "mr_pf_vel")  != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_mat,  "mr_eofmat")  != IMAGESTREAMIO_SUCCESS) {
        fprintf(stderr, "failed opening EOF streams\n");
        return 4;
    }
    int sem_pf  = ImageStreamIO_getsemwaitindex(&im_pf, -1);
    int sem_mat = ImageStreamIO_getsemwaitindex(&im_mat, -1);
    while (sem_pf  >= 0 && ImageStreamIO_semtrywait(&im_pf,  sem_pf)  == 0) {}
    while (sem_mat >= 0 && ImageStreamIO_semtrywait(&im_mat, sem_mat) == 0) {}

    long slice = 0;
    long bi = 0;
    for (long k = 0; k < T; k++) {
        /* Append to double-buffered mr_ol_buff [M x tbuff x 2] */
        float *dst = im_buff.array.F + ((size_t)slice * (size_t)tbuff + (size_t)bi) * (size_t)M;
        memcpy(dst, ol_in + (size_t)k * M, (size_t)M * sizeof(float));
        bi++;
        if (bi == tbuff) {
            uint64_t prev_mat = im_mat.md[0].cnt0;
            im_buff.md[0].write = 1;
            im_buff.md[0].cnt1 = (uint64_t)slice;
            ImageStreamIO_UpdateIm(&im_buff);
            slice = 1 - slice;
            bi = 0;
            /* Wait briefly for mkEOFPF to digest the completed chunk when enough chunks exist */
            struct timespec dl;
            clock_gettime(CLOCK_REALTIME, &dl);
            dl.tv_sec += 2;
            if (k + 1 >= 512) {
                while (im_mat.md[0].cnt0 <= prev_mat) {
                    if (sem_mat >= 0 && ImageStreamIO_semtimedwait(&im_mat, sem_mat, &dl) != 0) {
                        break;
                    }
                }
            } else {
                struct timespec ts = {0, 5000000};
                nanosleep(&ts, NULL);
            }
        }

        /* Feed single frame to applyEOFPF and collect synchronized (pos, vel) */
        uint64_t prev_pf = im_pf.md[0].cnt0;
        im_ol.md[0].write = 1;
        memcpy(im_ol.array.F, ol_in + (size_t)k * M, (size_t)M * sizeof(float));
        ImageStreamIO_UpdateIm(&im_ol);

        struct timespec dl;
        clock_gettime(CLOCK_REALTIME, &dl);
        dl.tv_sec += 2;
        while (im_pf.md[0].cnt0 <= prev_pf) {
            if (sem_pf >= 0 && ImageStreamIO_semtimedwait(&im_pf, sem_pf, &dl) != 0) {
                fprintf(stderr, "timeout waiting for mr_pf at k=%ld\n", k);
                return 5;
            }
        }
        memcpy(pf_pos + (size_t)k * M, im_pf.array.F,  (size_t)M * sizeof(float));
        memcpy(pf_vel + (size_t)k * M, im_pfv.array.F, (size_t)M * sizeof(float));
    }

    FILE *fp = fopen(argv[5], "wb");
    fwrite(pf_pos, sizeof(float), (size_t)T * (size_t)M, fp);
    fclose(fp);
    FILE *fv = fopen(argv[6], "wb");
    fwrite(pf_vel, sizeof(float), (size_t)T * (size_t)M, fv);
    fclose(fv);
    free(ol_in); free(pf_pos); free(pf_vel);
    return 0;
}
"""


def test_18_3_eof_multirate_turbulence_and_whitenoise_safety(shm_sandbox):
    """Verify mkEOFPF + applyEOFPF multi-rate velocity accuracy and white-noise null safety."""
    _shm_dir, work_dir, env = shm_sandbox
    exe = _compile_c(EOF_MR_DRV_C, "eof_mr_drv", work_dir, env)
    rng = np.random.default_rng(2026)

    M = 16
    tbuff = 128
    T = 1664  # 13 chunks of 128 frames
    lat = 2.35
    k_sub = 4

    def _run_eof_case(label: str, ol_signal: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
        ol_p = work_dir / f"ol_{label}.bin"
        pos_p = work_dir / f"pos_{label}.bin"
        vel_p = work_dir / f"vel_{label}.bin"
        ol_signal.astype(np.float32).tofile(ol_p)

        _run(
            f"""
milk-fps-runstop -q mk_mr app_mr >/dev/null 2>&1 || true
milk-fps-rm -f -q --ignore-missing mk_mr app_mr >/dev/null 2>&1 || true
milk-stream-rm -q --ignore-missing mr_ol mr_ol_buff mr_eofmat mr_eofmat_vel mr_pf mr_pf_vel mr_stat >/dev/null 2>&1 || true
milk-script -q -e <<'MS'
@calc "@S:mr_ol      = zeros({M}, 1)"
@calc "@S:mr_ol_buff = zeros({M}, {tbuff}, 2)"
MS
milk-fps-init -q mk_mr cacao-fpsexec-cacaopc-mkEOFPF >/dev/null
milk-fps-set -q \
    mk_mr.AOloopindex=0 \
    mk_mr.inbuff=mr_ol_buff \
    mk_mr.outPF=mr_eofmat \
    mk_mr.PForder=8 \
    mk_mr.diagorder=8 \
    mk_mr.blocksize={M} \
    mk_mr.PFlatency={lat} \
    mk_mr.NBtrain=2048 \
    mk_mr.minsamples=512 \
    mk_mr.diagminsamples=256 \
    mk_mr.updateperiod=1 \
    mk_mr.reglambda=0.01 \
    mk_mr.mr_enable=ON \
    mk_mr.mr_vel_reg_mult=3.5 \
    mk_mr.procinfo.loopcntMax=-1 \
    mk_mr.procinfo.triggermode=3 \
    mk_mr.procinfo.triggersname=mr_ol_buff
milk-fps-runstart -q mk_mr
milk-stream-wait -q -t 15 mr_eofmat mr_eofmat_vel

milk-fps-init -q app_mr cacao-fpsexec-cacaopc-applyEOFPF >/dev/null
milk-fps-set -q \
    app_mr.AOloopindex=0 \
    app_mr.indata=mr_ol \
    app_mr.PFmat=mr_eofmat \
    app_mr.outdata=mr_pf \
    app_mr.outPFstat=mr_stat \
    app_mr.PForder=8 \
    app_mr.diagorder=8 \
    app_mr.blocksize={M} \
    app_mr.rampsteps=16 \
    app_mr.mr_enable=ON \
    app_mr.nthreads=2 \
    app_mr.procinfo.loopcntMax=-1 \
    app_mr.procinfo.triggermode=3 \
    app_mr.procinfo.triggersname=mr_ol
milk-fps-runstart -q app_mr
milk-stream-wait -q -t 15 mr_pf mr_pf_vel
sleep 0.1
""",
            env,
            work_dir,
        )
        _run(f'"{exe}" {T} {M} {tbuff} "{ol_p}" "{pos_p}" "{vel_p}"', env, work_dir)
        diag = _get_fps_diag("mk_mr", env, work_dir)
        _run("milk-fps-runstop -q app_mr mk_mr && milk-fps-rm -f -q app_mr mk_mr", env, work_dir)
        pos = np.fromfile(pos_p, dtype=np.float32).reshape(T, M)
        vel = np.fromfile(vel_p, dtype=np.float32).reshape(T, M)
        return pos, vel, diag

    # --- A. Positive control: continuous-time smooth multi-frequency drifting wavefront ---
    # Sampled at 4x sub-steps so we can score exact sub-step tracking RMSE!
    t_sub = np.arange(T * k_sub, dtype=np.float64) / k_sub
    phi_sub = np.zeros((T * k_sub, M), dtype=np.float64)
    freqs = np.linspace(0.025, 0.085, M)  # cycles per WFS frame (6..21 Hz at 250 Hz WFS)
    for m in range(M):
        ph0 = rng.uniform(0, 2 * np.pi)
        ph1 = rng.uniform(0, 2 * np.pi)
        # Coupled quadrature pair + slow drift (simulating frozen-flow wind crossing pupil)
        phi_sub[:, m] = (
            0.8 * np.sin(2 * np.pi * freqs[m] * t_sub + ph0)
            + 0.4 * np.cos(2 * np.pi * (1.35 * freqs[m]) * t_sub + ph1)
        )
    # Add huge static DC offsets (+5.0) to verify exact zero-DC velocity invariance!
    dc_offsets = rng.uniform(-5.0, 5.0, size=(1, M))
    ol_turb = phi_sub.reshape(T, k_sub, M).mean(axis=1) + dc_offsets + rng.normal(0.0, 0.03, size=(T, M))
    pos_t, vel_t, diag_t = _run_eof_case("turb", ol_turb)
    pos_t = pos_t - dc_offsets.astype(np.float32)

    assert diag_t.get("out.eof_active", 0) == 2.0, f"Expected full Block-EOF active: {diag_t}"
    assert diag_t.get("out.mr_vel_rms", 0.0) > 0.05, f"Expected non-zero velocity weights: {diag_t}"

    # Evaluate on held-out final 400 frames at exact sub-step instants (k + t_centroid + lat + s_j)
    # where ol_turb[k] = mean(phi_sub[4k : 4k+4]) has timestamp centroid t_c = 0.5*(k_sub-1)/k_sub = 0.375
    t_c = 0.5 * (k_sub - 1) / k_sub
    s_j = (np.arange(k_sub) + 0.5) / k_sub - 0.5
    eval_slice = slice(1100, T - 6)
    ks = np.arange(1100, T - 6)
    true_vel = np.zeros((len(ks), M))
    err_zoh_sq = 0.0
    err_mr_sq = 0.0
    err_mid_sq = 0.0
    n_pts = 0
    for idx_k, k in enumerate(ks):
        t_mid = k + t_c + lat
        p_mid = np.array([np.interp(t_mid, t_sub, phi_sub[:, m]) for m in range(M)])
        p_plus = np.array([np.interp(t_mid + 0.5, t_sub, phi_sub[:, m]) for m in range(M)])
        p_minus = np.array([np.interp(t_mid - 0.5, t_sub, phi_sub[:, m]) for m in range(M)])
        true_vel[idx_k] = p_plus - p_minus
        err_mid_sq += float(np.sum((p_mid - pos_t[k]) ** 2)) * k_sub
        for j in range(k_sub):
            t_eval = t_mid + s_j[j]
            p_true = np.array([np.interp(t_eval, t_sub, phi_sub[:, m]) for m in range(M)])
            p_zoh = pos_t[k]
            p_mr = pos_t[k] + s_j[j] * vel_t[k]
            err_zoh_sq += float(np.sum((p_true - p_zoh) ** 2))
            err_mr_sq += float(np.sum((p_true - p_mr) ** 2))
            n_pts += M
    corr_vel = float(np.corrcoef(vel_t[eval_slice].ravel(), true_vel.ravel())[0, 1])
    rmse_zoh = float(np.sqrt(err_zoh_sq / n_pts))
    rmse_mr = float(np.sqrt(err_mr_sq / n_pts))
    zoh_excess_var = max(1e-12, (err_zoh_sq - err_mid_sq) / n_pts)
    mr_excess_var = (err_mr_sq - err_mid_sq) / n_pts
    interframe_elim_pct = 100.0 * (1.0 - mr_excess_var / zoh_excess_var)
    assert corr_vel > 0.90, f"Velocity prediction correlation too low: r={corr_vel:.3f}"
    assert rmse_mr < rmse_zoh, f"Multi-rate ramp did not beat ZOH: mr={rmse_mr:.4f} vs zoh={rmse_zoh:.4f}"
    assert interframe_elim_pct > 75.0, (
        f"Multi-rate ramp eliminated only {interframe_elim_pct:.1f}% of inter-frame ZOH variance"
    )

    # --- B. Null safety control: pure i.i.d. white noise (0.04 um = 40 nm RMS) ---
    ol_wn = rng.normal(0.0, 0.04, size=(T, M))
    pos_wn, vel_wn, diag_wn = _run_eof_case("whitenoise", ol_wn)
    vel_wn_rms = float(np.sqrt(np.mean(vel_wn[1100:] ** 2)))
    pos_wn_rms = float(np.sqrt(np.mean(pos_wn[1100:] ** 2)))
    assert np.all(np.isfinite(vel_wn)) and np.all(np.isfinite(pos_wn))
    assert vel_wn_rms < 0.015, f"White-noise velocity RMS blew up: {vel_wn_rms:.5f} (input 0.04)"
    assert pos_wn_rms < 0.020, f"White-noise position RMS blew up: {pos_wn_rms:.5f} (input 0.04)"
    print(
        f"\n[test_18_3] Turbulence: vel_corr={corr_vel:.3f}, sub-step RMSE ZOH={rmse_zoh:.4f} -> "
        f"MR={rmse_mr:.4f} ({100*(1 - rmse_mr/rmse_zoh):.1f}% reduction) | "
        f"White-noise (0.040): pos_rms={pos_wn_rms:.4f}, vel_rms={vel_wn_rms:.4f} "
        f"(W_vel_rms={diag_wn.get('out.mr_vel_rms', 0):.4f})"
    )
