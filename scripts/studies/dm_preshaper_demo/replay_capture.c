// SPDX-FileCopyrightText: 2026 Olivier Guyon et al
// SPDX-License-Identifier: LGPL-3.0-or-later
/**
 * @file    replay_capture.c
 * @brief   Deterministic lockstep 4 kHz DM command replay & GPU OPD/WFS recorder
 *
 * Drives a live `dmpreshaper -> csim_htsim (GPU plate DM)` chain tick-by-tick using
 * shared-memory semaphores (`step_clk -> dm01disp -> csim_dm01_opd`), ensuring zero
 * OS timer jitter between WITH and WITHOUT pre-shaper runs and forcing GPU D2H OPD
 * publication on every single tick via an active semaphore reader on `csim_dm01_opd`.
 */

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "ImageStreamIO/ImageStreamIO.h"

static void add_ns(struct timespec *ts, uint64_t ns)
{
    ts->tv_nsec += (long) (ns % 1000000000ULL);
    ts->tv_sec += (time_t) (ns / 1000000000ULL);
    if (ts->tv_nsec >= 1000000000L)
    {
        ts->tv_sec += 1;
        ts->tv_nsec -= 1000000000L;
    }
}

static void write_f32_stream(IMAGE *im, const float *src, size_t n_elem, int post_sem)
{
    im->md->write = 1;
    memcpy(im->array.F, src, n_elem * sizeof(float));
    clock_gettime(CLOCK_REALTIME, &im->md->writetime);
    im->md->atime = im->md->writetime;
    im->md->cnt0++;
    im->md->write = 0;
    if (post_sem)
    {
        ImageStreamIO_sempost(im, -1);
    }
}

static int wait_sem_ms(IMAGE *im, int sem, uint64_t timeout_ms)
{
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    add_ns(&ts, timeout_ms * 1000000ULL);
    int rc = ImageStreamIO_semtimedwait(im, sem, &ts);
    if (rc != 0)
    {
        return -1;
    }
    ImageStreamIO_semflush(im, sem);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 7)
    {
        fprintf(stderr,
                "Usage: %s <n_ticks> <warmup_ticks> <in_cmd.bin> <out_disp.bin> <out_opd.bin> "
                "<out_wfs.bin> [cmd=dm01cmd] [clk=step_clk] [disp=dm01disp] [opd=csim_dm01_opd] "
                "[wfs=csim_wfs_nir]\n",
                argv[0]);
        return 2;
    }

    const size_t n_ticks      = (size_t) strtoull(argv[1], NULL, 10);
    const size_t warmup_ticks = (size_t) strtoull(argv[2], NULL, 10);
    const char  *in_cmd_path  = argv[3];
    const char  *out_disp_p   = argv[4];
    const char  *out_opd_p    = argv[5];
    const char  *out_wfs_p    = argv[6];
    const char  *cmd_name     = (argc > 7) ? argv[7] : "dm01cmd";
    const char  *clk_name     = (argc > 8) ? argv[8] : "step_clk";
    const char  *disp_name    = (argc > 9) ? argv[9] : "dm01disp";
    const char  *opd_name     = (argc > 10) ? argv[10] : "csim_dm01_opd";
    const char  *wfs_name     = (argc > 11) ? argv[11] : "csim_wfs_nir";

    IMAGE im_cmd, im_clk, im_disp, im_opd, im_wfs;
    memset(&im_cmd, 0, sizeof(im_cmd));
    memset(&im_clk, 0, sizeof(im_clk));
    memset(&im_disp, 0, sizeof(im_disp));
    memset(&im_opd, 0, sizeof(im_opd));
    memset(&im_wfs, 0, sizeof(im_wfs));

    if (ImageStreamIO_openIm(&im_cmd, cmd_name) != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_clk, clk_name) != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_disp, disp_name) != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_opd, opd_name) != IMAGESTREAMIO_SUCCESS ||
        ImageStreamIO_openIm(&im_wfs, wfs_name) != IMAGESTREAMIO_SUCCESS)
    {
        fprintf(stderr, "replay_capture: failed to open one or more SHM streams\n");
        return 1;
    }

    const size_t n_dm  = (size_t) im_cmd.md->nelement;
    const size_t n_opd = (size_t) im_opd.md->nelement;
    const size_t n_wfs = (size_t) im_wfs.md->nelement;
    if ((size_t) im_disp.md->nelement != n_dm)
    {
        fprintf(stderr, "replay_capture: dm01cmd (%zu) vs dm01disp (%zu) mismatch\n", n_dm,
                (size_t) im_disp.md->nelement);
        return 1;
    }

    float *cmd_seq = (float *) malloc(n_ticks * n_dm * sizeof(float));
    float *zeros   = (float *) calloc(n_dm, sizeof(float));
    float *prev_u  = (float *) calloc(n_dm, sizeof(float));
    if (!cmd_seq || !zeros || !prev_u)
    {
        fprintf(stderr, "replay_capture: OOM\n");
        return 1;
    }

    FILE *fin = fopen(in_cmd_path, "rb");
    if (!fin)
    {
        fprintf(stderr, "replay_capture: cannot open '%s': %s\n", in_cmd_path, strerror(errno));
        return 1;
    }
    if (fread(cmd_seq, sizeof(float), n_ticks * n_dm, fin) != n_ticks * n_dm)
    {
        fprintf(stderr, "replay_capture: short read on '%s'\n", in_cmd_path);
        fclose(fin);
        return 1;
    }
    fclose(fin);

    FILE *f_disp = fopen(out_disp_p, "wb");
    FILE *f_opd  = fopen(out_opd_p, "wb");
    FILE *f_wfs  = fopen(out_wfs_p, "wb");
    if (!f_disp || !f_opd || !f_wfs)
    {
        fprintf(stderr, "replay_capture: cannot open output binary files\n");
        return 1;
    }

    int sem_opd = ImageStreamIO_getsemwaitindex(&im_opd, -1);
    if (sem_opd < 0)
    {
        sem_opd = 0;
    }
    ImageStreamIO_semflush(&im_opd, sem_opd);

    float clk_val = 0.0f;

    /* 1. Warmup zero ticks to settle DM plate PDE, delay ring, and pre-shaper ring */
    write_f32_stream(&im_cmd, zeros, n_dm, 0);
    for (size_t w = 0; w < warmup_ticks; w++)
    {
        clk_val += 1.0f;
        write_f32_stream(&im_clk, &clk_val, 1, 1);
        if (wait_sem_ms(&im_opd, sem_opd, 3000ULL) != 0)
        {
            fprintf(stderr, "replay_capture: timeout waiting for %s during warmup %zu\n", opd_name,
                    w);
            im_opd.semReadPID[sem_opd] = 0;
            return 1;
        }
    }

    /* 2. Tick-exact replay & capture */
    size_t cmd_updates = 0;
    for (size_t t = 0; t < n_ticks; t++)
    {
        const float *u_cur = &cmd_seq[t * n_dm];
        int          diff  = 0;
        for (size_t i = 0; i < n_dm; i++)
        {
            if (fabsf(u_cur[i] - prev_u[i]) > 1.0e-12f)
            {
                diff = 1;
                break;
            }
        }
        if (diff)
        {
            /* Update dm01cmd before pulsing step_clk so dmpreshaper ingests on this exact tick */
            write_f32_stream(&im_cmd, u_cur, n_dm, 0);
            memcpy(prev_u, u_cur, n_dm * sizeof(float));
            cmd_updates++;
        }

        clk_val += 1.0f;
        write_f32_stream(&im_clk, &clk_val, 1, 1);
        if (wait_sem_ms(&im_opd, sem_opd, 3000ULL) != 0)
        {
            fprintf(stderr, "replay_capture: timeout waiting for %s at tick %zu\n", opd_name, t);
            im_opd.semReadPID[sem_opd] = 0;
            return 1;
        }

        if (fwrite(im_disp.array.F, sizeof(float), n_dm, f_disp) != n_dm ||
            fwrite(im_opd.array.F, sizeof(float), n_opd, f_opd) != n_opd ||
            fwrite(im_wfs.array.F, sizeof(float), n_wfs, f_wfs) != n_wfs)
        {
            fprintf(stderr, "replay_capture: short write at tick %zu\n", t);
            im_opd.semReadPID[sem_opd] = 0;
            return 1;
        }
    }

    /* Return DM cleanly to zero after capture */
    write_f32_stream(&im_cmd, zeros, n_dm, 0);
    for (size_t w = 0; w < 16; w++)
    {
        clk_val += 1.0f;
        write_f32_stream(&im_clk, &clk_val, 1, 1);
        (void) wait_sem_ms(&im_opd, sem_opd, 1000ULL);
    }

    im_opd.semReadPID[sem_opd] = 0;
    fclose(f_wfs);
    fclose(f_opd);
    fclose(f_disp);
    free(prev_u);
    free(zeros);
    free(cmd_seq);
    ImageStreamIO_closeIm(&im_wfs);
    ImageStreamIO_closeIm(&im_opd);
    ImageStreamIO_closeIm(&im_disp);
    ImageStreamIO_closeIm(&im_clk);
    ImageStreamIO_closeIm(&im_cmd);

    printf("replay_capture: OK ticks=%zu warmup=%zu cmd_updates=%zu\n", n_ticks, warmup_ticks,
           cmd_updates);
    return 0;
}
