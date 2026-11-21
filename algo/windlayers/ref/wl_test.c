// SPDX-FileCopyrightText: 2026 Olivier Guyon et al
// SPDX-License-Identifier: LGPL-3.0-or-later
// Development driver: run windlayers_core.h on raw float32 cubes written by numpy.
#include "windlayers_core.h"
#include <time.h>

static float *rd(const char *fn, size_t nel)
{
    FILE  *f = fopen(fn, "rb");
    float *p = (float *) malloc(sizeof(float) * nel);
    if (!f || !p || fread(p, sizeof(float), nel, f) != nel)
    {
        fprintf(stderr, "cannot read %s\n", fn);
        exit(1);
    }
    fclose(f);
    return p;
}

static double now(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + 1e-9 * t.tv_nsec;
}

int main(int argc, char **argv)
{
    if (argc < 12)
    {
        fprintf(stderr, "usage: n nfr dx dt diam K I maskK maskI kmode pyr [corefrac halo klag"
                        " ksign fmaxk vmapout]\n");
        return 2;
    }
    int      n   = atoi(argv[1]);
    long     nfr = atol(argv[2]);
    wl_cfg_t cfg = { 0 };
    cfg.n        = n;
    cfg.dx       = atof(argv[3]);
    cfg.dt       = atof(argv[4]);
    cfg.diam     = atof(argv[5]);
    cfg.fmin     = 0.15;
    cfg.fmax     = 1.6;
    cfg.fmaxk    = (argc > 16) ? atof(argv[16]) : 1.6;
    cfg.pad      = 2;
    cfg.lagmax_s = 160 * cfg.dt;
    cfg.vmax     = 30.0;
    cfg.dv       = 0.5;
    cfg.nsigma   = 8.0;
    cfg.minsep   = 1.5;
    cfg.minfrac  = 0.05;
    cfg.maxlayers = 8;
    cfg.kmode    = atoi(argv[10]);
    cfg.pyr      = atoi(argv[11]);
    cfg.modrad   = 3.0;
    cfg.blur     = 0.6;
    cfg.corefrac = (argc > 12) ? atof(argv[12]) : 1.0;
    cfg.halo     = (argc > 13) ? atof(argv[13]) : 15.0;
    cfg.klag     = (argc > 14) ? atof(argv[14]) : 0.0;
    cfg.ksign    = (argc > 15) ? atoi(argv[15]) : 1;
    cfg.og       = 1.0;
    cfg.phaifc   = -1.0;
    float *kc = rd(argv[6], (size_t) nfr * n * n);
    float *ic = rd(argv[7], (size_t) nfr * n * n);
    float *mk = rd(argv[8], (size_t) n * n);
    float *mi = rd(argv[9], (size_t) n * n);
    double t0 = now();
    wl_core_t *c = wl_create(&cfg, mk, mi);
    if (!c)
    {
        fprintf(stderr, "wl_create failed\n");
        return 1;
    }
    float *work = (float *) malloc(sizeof(float) * 2 * (size_t) c->nfx * n);
    printf("grid: nfx=%d nfy=%d nm=%d df=%.4f lmax=%d nt=%d nrho=%d nv=%d (create %.2fs)\n",
           c->nfx, c->nfy, c->nm, c->df, c->lmax, c->nt, c->nrho, c->nv, now() - t0);
    t0 = now();
    for (long t = 0; t < nfr; t++)
    {
        if (wl_push(c, kc + (size_t) t * n * n, ic + (size_t) t * n * n, work))
        {
            wl_block_take(c, 1);
            wl_block_process(c);
        }
    }
    double tp = now() - t0;
    t0        = now();
    int nk    = wl_analyze(c);
    printf("push: %.2fs (%.1f us/frame), analyze: %.2fs, blocks=%.0f, tint=%.1fs, ksign=%d\n", tp,
           1e6 * tp / nfr, now() - t0, c->nblk, c->tint_s, c->ksign_used);
    printf("map stats: K med=%.4f sig=%.4f | I med=%.4f sig=%.4f | X med=%.4f sig=%.4f\n",
           c->med_k, c->sig_k, c->med_i, c->sig_i, c->med_x, c->sig_x);
    for (int l = 0; l < nk; l++)
    {
        wl_layer_t *L = &c->layers[l];
        printf("  v=(%6.2f,%6.2f) speed=%5.2f dir=%6.1f snr=%6.1f pk K/I/X=%+.3f/%+.3f/%+.3f |"
               " fK=%.3f fI=%.3f | z=%8.0f +-%5.0f coh=%+.2f zax=%.0f zdg=%.0f\n",
               L->vx, L->vy, L->speed, L->dir, L->snr, L->pk_k, L->pk_i, L->pk_x, L->frac_k,
               L->frac_i, L->z, L->zerr, L->coh, L->z_axis, L->z_diag);
        printf("      z(f):");
        for (int b = 0; b < L->nzf; b++)
        {
            printf(" %.2f:%.0f", L->ff[b], L->zf[b]);
        }
        printf("\n");
    }
    if (argc > 17)
    {
        FILE *f = fopen(argv[17], "wb");
        fwrite(c->vmap_k, sizeof(float), (size_t) c->nv * c->nv, f);
        fwrite(c->vmap_i, sizeof(float), (size_t) c->nv * c->nv, f);
        fwrite(c->vmap_x, sizeof(float), (size_t) c->nv * c->nv, f);
        fclose(f);
    }
    wl_destroy(c);
    return 0;
}
