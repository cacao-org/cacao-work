// SPDX-FileCopyrightText: 2026 Olivier Guyon et al
//
// SPDX-License-Identifier: LGPL-3.0-or-later

/**
 * @file    windlayers_core.h
 * @brief   Frozen-flow wind layer estimator: velocity maps, layer split and layer distance
 *
 * Self-contained C (libm + OpenMP, no milk dependency) so that the compute unit
 * (`windlayers.c`) and test drivers share one implementation.
 *
 * Two pupil-plane map sequences on the same n x n pixel grid are analysed together:
 *   K(x, t)  "phase space": wavefront curvature, laplacian of the OPD [1/m]
 *   I(x, t)  "intensity space": relative intensity fluctuation dI/I
 * Both are spatially near-white for Kolmogorov turbulence, which keeps spectral leakage from
 * the pupil edges harmless (raw phase is not: its low frequencies leak everywhere).
 *
 * 1. Lag spectra. F_a(f, t) is the spatial Fourier transform of masked channel a on a band
 *    limited frequency grid (half plane, computed as a separable matrix transform). Blocks of
 *    frames are Fourier transformed along time and the cross spectra accumulated (Welch). Back
 *    in the lag domain, S_ab(tau, f) = < conj(F_a(f, t)) F_b(f, t + tau) >, unbiased in tau.
 * 2. Velocity maps. A frozen layer moving at v gives S_aa(tau, f) = S_aa(0, f) t(v tau)
 *    exp(-2 pi i f.v tau), t(rho) being the pixel-pair count of the masks. R = S(tau) / S(0),
 *    weighted by |f| over the band and transformed back to rho, peaks at rho = v tau. These
 *    slices are stacked along rho = v tau with weight tau, which is the filtered back-projection
 *    of the Radon transform formed by the per-f temporal spectra. Only tau != 0 is used, so
 *    noise that is white in time does not enter.
 * 3. Layer split. With the peak velocities v_l, each S_ab(tau, f) is fitted per spatial
 *    frequency as sum_l p_l(f) t(v_l tau) exp(-2 pi i f.v_l tau), which separates layers whose
 *    planes nu = -f.v overlap at some frequencies.
 * 4. Distance. Geometric (transport of intensity) propagation over z gives
 *    dI/I = -z * laplacian(OPD). On each layer the cross power is x_l(f) = -z_l gain(f) a_l(f)
 *    (a_l: curvature power) and z_l is a weighted least-squares slope. The cross spectrum is
 *    used, never a power ratio: wavefront-induced fluctuations of a pyramid's 4-image sum are
 *    uncorrelated with the curvature, so they add noise but no bias.
 *
 * Pyramid WFS model (sidebands on a 4-sided pyramid, circular modulation of radius r):
 * a ripple of spatial frequency f puts sidebands at +-f around the PSF core; a sideband beats
 * with the core only while both go through the same facet.
 *   T_I(f) = < 1[Q(m) = Q(m + f)] >_m               intensity ripple seen in the 4-image sum
 *   T_x(f) = < sgn(m_x) (1[Q(m) = Q(m + f)] - 1[Q(m) = Q(m - f)]) >_m     x-slope per radian
 * with m on the modulation circle, blurred by the core width. Light scattered far from the core
 * (a halo of width `halo`) follows the same expressions with a wide blur; `corefrac` mixes both.
 */

#ifndef WINDLAYERS_CORE_H
#define WINDLAYERS_CORE_H

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _OPENMP
#    include <omp.h>
#endif

#define WL_MAXLAYERS 8
#define WL_NZBINS    8
#define WL_PI        3.14159265358979323846

/** @brief Estimator configuration (SI units unless noted). */
typedef struct
{
    int    n;         /**< Map size [pixels] (n x n) */
    double dx;        /**< Pixel pitch on the pupil [m] */
    double dt;        /**< Frame period of the pushed maps [s] */
    double diam;      /**< Pupil diameter [m] */
    double fmin;      /**< Lowest spatial frequency used [cycles/m] */
    double fmax;      /**< Highest spatial frequency used [cycles/m] */
    double fmaxk;     /**< Highest spatial frequency of the K channel [cycles/m] (<= fmax) */
    int    pad;       /**< Frequency oversampling: df = 1 / (pad n dx) */
    double lagmax_s;  /**< Largest lag [s] */
    double vmax;      /**< Velocity map half-width [m/s] */
    double dv;        /**< Velocity map step [m/s] */
    double nsigma;    /**< Detection threshold [robust sigma of the map] */
    double minsep;    /**< Peaks closer than this are one layer [m/s] */
    double minfrac;   /**< Reject peaks below this fraction of the strongest of a map */
    int    maxlayers; /**< Largest number of layers kept (<= WL_MAXLAYERS) */
    double tavg;      /**< Forgetting time of the spectra [s] (0: cumulative) */
    int    kmode;     /**< K channel: 0 = divergence of pyramid slopes, 1 = laplacian of OPD */
    double klag;      /**< Delay of the K channel relative to I [frames of dt] */
    int    ksign;     /**< Sign of K relative to the atmosphere: +1, -1, 0 = find it */
    double og;        /**< Extra optical gain of the slopes (kmode 0), 1 = model */
    double phapitch;  /**< Pitch of the OPD map before resampling [m] (kmode 1) */
    double phaifc;    /**< OPD map: <0 samples the wavefront, 0 bilinear surface, 0..1 DM
                           commands with Gaussian influence of that coupling */
    int    pyr;       /**< 1: I is the 4-image sum of a pyramid WFS (apply T_I) */
    double modrad;    /**< Pyramid modulation radius [lambda/D] */
    double blur;      /**< PSF core width on the pyramid [lambda/D] */
    double corefrac;  /**< Fraction of the light in the core (rest in the halo) */
    double halo;      /**< Halo width on the pyramid [lambda/D] */
    double igain;     /**< Intensity response of the sensor relative to the model (1: model) */
} wl_cfg_t;

/** @brief One detected layer. */
typedef struct
{
    double vx, vy;        /**< Pattern velocity on the map grid [m/s] */
    double speed, dir;    /**< Modulus [m/s] and direction atan2(vy, vx) [deg, 0..360) */
    double pk_k, pk_i;    /**< Velocity-map value in K and in I (coherent fraction) */
    double pk_x;          /**< Velocity-map value of the K-I cross map (sign removed) */
    double snr;           /**< Largest detection significance over the three maps */
    double frac_k;        /**< Fraction of the band K power carried by the layer */
    double frac_i;        /**< Fraction of the band I power carried by the layer */
    double z;             /**< Distance [m] */
    double zerr;          /**< Scatter of z between spatial-frequency bins [m] */
    double coh;           /**< K-I coherence of the layer */
    double z_axis;        /**< z from frequencies along the pyramid axes [m] */
    double z_diag;        /**< z from frequencies along the diagonals [m] */
    double ff[WL_NZBINS]; /**< Bin centres [cycles/m] */
    double zf[WL_NZBINS]; /**< z per bin [m] */
    int    nzf;           /**< Number of bins filled */
} wl_layer_t;

/** @brief Radix-2 complex FFT plan (separate real / imaginary arrays). */
typedef struct
{
    int    n;
    int   *rev;
    float *cs;
    float *sn;
} wl_fft_t;

/** @brief Estimator state. */
typedef struct
{
    wl_cfg_t cfg;
    /* frequency grid: fx = i df (i = 0..nfx-1), fy = (j - nfyh) df (j = 0..nfy-1) */
    double   df;
    int      nfx, nfy, nfyh;
    int      nm;      /**< Active modes (fmin' <= |f| <= fmax) */
    int     *mi, *mj; /**< Grid indices of the active modes */
    double  *mfx;     /**< Mode frequencies [cycles/m] */
    double  *mfy;
    double  *mw;      /**< Half-plane weight: 0.5 on fx = 0, else 1 */
    double  *gain;    /**< Model gain of dI/I against K, per mode (0: not usable) */
    double  *tint;    /**< Intensity transfer of the sensor, per mode */
    float   *exr, *exi; /**< Forward x kernel [nfx * n] */
    float   *eyr, *eyi; /**< Forward y kernel [nfy * n] */
    /* masks and pixel-pair tapers, (2n-1)^2, normalised to 1 at zero lag */
    float   *mask_k, *mask_i;
    double  *tap_kk, *tap_ii, *tap_ki;
    double   t0_kk, t0_ii, t0_ki;
    /* block buffers [nm * nt], mode major */
    int      lmax;    /**< Largest lag [frames] */
    int      nt;      /**< Block length [frames] */
    int      nfft;    /**< Temporal FFT length = 2 nt */
    int      nbuf;    /**< Frames in the current block */
    float   *bkr, *bki, *bir, *bii;
    float   *skr, *ski, *sir, *sii; /**< Copy of the last full block, being transformed */
    wl_fft_t fft;
    /* accumulated spectra [nm * nfft] */
    float   *pkk, *pii, *pxr, *pxi;
    double   nblk;    /**< Effective number of accumulated blocks */
    long     nblk_total;
    long     nframes;
    /* lag spectra [nm * (2 lmax + 1)], index tau + lmax */
    float   *skk_r, *skk_i, *sii_r, *sii_i, *ski_r, *ski_i;
    /* correlation (rho) grid */
    int      nr;      /**< Half-size of the rho grid [samples of dx / 2] */
    int      nrho;
    float   *rxr, *rxi; /**< Inverse x kernel [nfx * nrho] */
    float   *ryr, *ryi; /**< Inverse y kernel [nfy * nrho] */
    /* results */
    int        nv;    /**< Velocity map size (nv x nv) */
    float     *vmap_k, *vmap_i, *vmap_x;
    float     *vsup_k, *vsup_i, *vsup_x;
    double     med_k, sig_k, med_i, sig_i, med_x, sig_x;
    int        ksign_used;
    int        nlayers;
    wl_layer_t layers[WL_MAXLAYERS];
    double     pow_k, pow_i; /**< Band power of K and of I */
    double     tint_s;       /**< Integration time behind the current spectra [s] */
} wl_core_t;

/* ------------------------------------------------------------------------------------------ */
/* small helpers                                                                              */
/* ------------------------------------------------------------------------------------------ */

static inline double wl_sinc(double x)
{
    double a = WL_PI * x;
    return (fabs(a) < 1e-9) ? 1.0 : sin(a) / a;
}

static inline double wl_ncdf(double v)
{
    return 0.5 * (1.0 + erf(v * 0.70710678118654752440));
}

static int wl_cmp_float(const void *a, const void *b)
{
    float fa = *(const float *) a;
    float fb = *(const float *) b;
    return (fa > fb) - (fa < fb);
}

/** @brief Bilinear sample of a row-major (ny, nx) double array, 0 outside. */
static inline double wl_bilin_d(const double *img, int nx, int ny, double x, double y)
{
    if (!(x >= 0.0) || !(y >= 0.0) || x > (double) (nx - 1) || y > (double) (ny - 1))
    {
        return 0.0;
    }
    int x0 = (int) x;
    int y0 = (int) y;
    if (x0 > nx - 2)
    {
        x0 = nx - 2;
    }
    if (y0 > ny - 2)
    {
        y0 = ny - 2;
    }
    double        fx = x - x0;
    double        fy = y - y0;
    const double *p  = img + (size_t) y0 * nx + x0;
    return p[0] * (1.0 - fx) * (1.0 - fy) + p[1] * fx * (1.0 - fy) + p[nx] * (1.0 - fx) * fy +
           p[nx + 1] * fx * fy;
}

/** @brief Bilinear sample of a row-major (ny, nx) float array, 0 outside. */
static inline double wl_bilin_f(const float *img, int nx, int ny, double x, double y)
{
    if (!(x >= 0.0) || !(y >= 0.0) || x > (double) (nx - 1) || y > (double) (ny - 1))
    {
        return 0.0;
    }
    int x0 = (int) x;
    int y0 = (int) y;
    if (x0 > nx - 2)
    {
        x0 = nx - 2;
    }
    if (y0 > ny - 2)
    {
        y0 = ny - 2;
    }
    double       fx = x - x0;
    double       fy = y - y0;
    const float *p  = img + (size_t) y0 * nx + x0;
    return (double) p[0] * (1.0 - fx) * (1.0 - fy) + (double) p[1] * fx * (1.0 - fy) +
           (double) p[nx] * (1.0 - fx) * fy + (double) p[nx + 1] * fx * fy;
}

/* ------------------------------------------------------------------------------------------ */
/* pyramid WFS sideband model                                                                 */
/* ------------------------------------------------------------------------------------------ */

/** @brief E[sgn(u) 1(sgn(u + f) = sgn(u))] for u ~ N(m, s): the signed same-facet weight. */
static inline double wl_sgn_same(double m, double f, double s)
{
    return (1.0 - wl_ncdf((fmax(0.0, -f) - m) / s)) - wl_ncdf((fmin(0.0, -f) - m) / s);
}

/**
 * wl_pyr_model() - Intensity and slope transfer of a modulated 4-sided pyramid WFS
 * @fx, @fy:  Spatial frequency [cycles per aperture]
 * @rmod:     Modulation radius [lambda/D]
 * @blur:     Gaussian width of the light distribution on the pyramid [lambda/D]
 * @ti:       Out: fraction of an intensity ripple seen in the sum of the 4 pupil images
 * @tx, @ty:  Out: slope response, S_x(f) = i T_x(f) phi(f) for phi in radians
 */
static void wl_pyr_model(double fx, double fy, double rmod, double blur, double *ti, double *tx,
                         double *ty)
{
    const int npts = 48;
    double    si = 0.0, sx = 0.0, sy = 0.0;
    double    s = (blur > 1e-3) ? blur : 1e-3;

    for (int k = 0; k < npts; k++)
    {
        double th = (k + 0.5) * 2.0 * WL_PI / npts;
        double mx = rmod * cos(th);
        double my = rmod * sin(th);
        /* probability that u and u + f have the same sign, per axis, for +f and -f */
        double qxp = 1.0 - fabs(wl_ncdf((mx + fx) / s) - wl_ncdf(mx / s));
        double qyp = 1.0 - fabs(wl_ncdf((my + fy) / s) - wl_ncdf(my / s));
        double qxm = 1.0 - fabs(wl_ncdf((mx - fx) / s) - wl_ncdf(mx / s));
        double qym = 1.0 - fabs(wl_ncdf((my - fy) / s) - wl_ncdf(my / s));
        /* E[sgn(u) 1(sgn(u + f) = sgn(u))] per axis, for +f and -f */
        double axp = wl_sgn_same(mx, fx, s);
        double axm = wl_sgn_same(mx, -fx, s);
        double ayp = wl_sgn_same(my, fy, s);
        double aym = wl_sgn_same(my, -fy, s);

        si += qxp * qyp;
        sx += axp * qyp - axm * qym;
        sy += ayp * qxp - aym * qxm;
    }
    *ti = si / npts;
    *tx = sx / npts;
    *ty = sy / npts;
}

/* ------------------------------------------------------------------------------------------ */
/* FFT                                                                                        */
/* ------------------------------------------------------------------------------------------ */

static int wl_fft_init(wl_fft_t *p, int n)
{
    p->n   = n;
    p->rev = (int *) malloc(sizeof(int) * (size_t) n);
    p->cs  = (float *) malloc(sizeof(float) * (size_t) (n / 2));
    p->sn  = (float *) malloc(sizeof(float) * (size_t) (n / 2));
    if (p->rev == NULL || p->cs == NULL || p->sn == NULL)
    {
        return -1;
    }
    int bits = 0;
    while ((1 << bits) < n)
    {
        bits++;
    }
    for (int i = 0; i < n; i++)
    {
        int r = 0;
        for (int b = 0; b < bits; b++)
        {
            if (i & (1 << b))
            {
                r |= 1 << (bits - 1 - b);
            }
        }
        p->rev[i] = r;
    }
    for (int k = 0; k < n / 2; k++)
    {
        p->cs[k] = (float) cos(2.0 * WL_PI * k / n);
        p->sn[k] = (float) sin(2.0 * WL_PI * k / n);
    }
    return 0;
}

static void wl_fft_free(wl_fft_t *p)
{
    free(p->rev);
    free(p->cs);
    free(p->sn);
    p->rev = NULL;
    p->cs  = NULL;
    p->sn  = NULL;
}

/** @brief In-place forward FFT, exp(-2 pi i k n / N), no normalisation. */
static void wl_fft_fwd(const wl_fft_t *p, float *restrict re, float *restrict im)
{
    const int n = p->n;
    for (int i = 0; i < n; i++)
    {
        int j = p->rev[i];
        if (i < j)
        {
            float t = re[i];
            re[i]   = re[j];
            re[j]   = t;
            t       = im[i];
            im[i]   = im[j];
            im[j]   = t;
        }
    }
    for (int len = 2; len <= n; len <<= 1)
    {
        int half = len >> 1;
        int step = n / len;
        for (int i = 0; i < n; i += len)
        {
            for (int k = 0; k < half; k++)
            {
                float wr = p->cs[k * step];
                float wi = -p->sn[k * step];
                float xr = re[i + k + half];
                float xi = im[i + k + half];
                float vr = xr * wr - xi * wi;
                float vi = xr * wi + xi * wr;
                float ur = re[i + k];
                float ui = im[i + k];
                re[i + k]        = ur + vr;
                im[i + k]        = ui + vi;
                re[i + k + half] = ur - vr;
                im[i + k + half] = ui - vi;
            }
        }
    }
}

/* ------------------------------------------------------------------------------------------ */
/* setup                                                                                      */
/* ------------------------------------------------------------------------------------------ */

/** @brief Pixel-pair count t_ab(rho) = sum_x a(x) b(x + rho) on (2n-1)^2, returns t(0). */
static double wl_make_taper(const float *ma, const float *mb, int n, double *tap)
{
    const int nt2 = 2 * n - 1;
#pragma omp parallel for schedule(static)
    for (int ry = -(n - 1); ry <= n - 1; ry++)
    {
        for (int rx = -(n - 1); rx <= n - 1; rx++)
        {
            double s  = 0.0;
            int    y0 = (ry < 0) ? -ry : 0;
            int    y1 = (ry < 0) ? n : n - ry;
            int    x0 = (rx < 0) ? -rx : 0;
            int    x1 = (rx < 0) ? n : n - rx;
            for (int y = y0; y < y1; y++)
            {
                const float *pa = ma + (size_t) y * n;
                const float *pb = mb + (size_t) (y + ry) * n + rx;
                for (int x = x0; x < x1; x++)
                {
                    s += (double) pa[x] * (double) pb[x];
                }
            }
            tap[(size_t) (ry + n - 1) * nt2 + (rx + n - 1)] = s;
        }
    }
    double t0 = tap[(size_t) (n - 1) * nt2 + (n - 1)];
    if (t0 > 0.0)
    {
        for (size_t i = 0; i < (size_t) nt2 * nt2; i++)
        {
            tap[i] /= t0;
        }
    }
    return t0;
}

/** @brief Sample a taper at the pixel lag (rx, ry) [pixels, fractional]. */
static inline double wl_taper_at(const double *tap, int n, double rx, double ry)
{
    const int nt2 = 2 * n - 1;
    return wl_bilin_d(tap, nt2, nt2, rx + (n - 1), ry + (n - 1));
}

/** @brief Model gain of dI/I against the K channel for every active mode. */
static void wl_make_gain(wl_core_t *c)
{
    const wl_cfg_t *g  = &c->cfg;
    const double    dx = g->dx;

    for (int m = 0; m < c->nm; m++)
    {
        double fx = c->mfx[m];
        double fy = c->mfy[m];
        double f2 = fx * fx + fy * fy;
        double ti = 1.0, tx = 0.0, ty = 0.0;

        if (g->pyr || g->kmode == 0)
        {
            double tic, txc, tyc, tih, txh, tyh;
            double cf = (g->corefrac < 0.0) ? 0.0 : ((g->corefrac > 1.0) ? 1.0 : g->corefrac);
            wl_pyr_model(fx * g->diam, fy * g->diam, g->modrad, g->blur, &tic, &txc, &tyc);
            if (cf < 1.0)
            {
                wl_pyr_model(fx * g->diam, fy * g->diam, g->modrad, g->halo, &tih, &txh, &tyh);
            }
            else
            {
                tih = txh = tyh = 0.0;
            }
            ti = g->pyr ? (cf * tic + (1.0 - cf) * tih) : 1.0;
            ti *= (g->igain > 0.0) ? g->igain : 1.0;
            tx = cf * txc + (1.0 - cf) * txh;
            ty = cf * tyc + (1.0 - cf) * tyh;
        }
        c->tint[m] = ti;

        double gain = 0.0;
        if (g->kmode == 1)
        {
            /* K = 5-point laplacian of the OPD map resampled on the pupil grid */
            double sx  = sin(WL_PI * fx * dx);
            double sy  = sin(WL_PI * fy * dx);
            double lam = (4.0 / (dx * dx)) * (sx * sx + sy * sy);
            double rsp = 1.0;
            if (g->phapitch > 1.001 * dx && g->phaifc != 0.0)
            {
                double p  = g->phapitch;
                double b2 = wl_sinc(fx * p) * wl_sinc(fx * p) * wl_sinc(fy * p) * wl_sinc(fy * p);
                double h  = 1.0;
                if (g->phaifc > 0.0 && g->phaifc < 1.0)
                {
                    h = exp(-WL_PI * WL_PI * f2 * p * p / (-log(g->phaifc)));
                }
                rsp = (b2 > 0.05) ? (h / b2) : 0.0;
            }
            gain = (lam > 0.0) ? (4.0 * WL_PI * WL_PI * f2 * ti * rsp / lam) : 0.0;
        }
        else
        {
            /* K = lambda / (2 pi) * divergence (central differences) of the pyramid slopes */
            double sx = sin(2.0 * WL_PI * fx * dx) / dx;
            double sy = sin(2.0 * WL_PI * fy * dx) / dx;
            double gs = (sx * tx + sy * ty) * ((g->og > 0.0) ? g->og : 1.0);
            gain      = (gs > 1e-6 * sqrt(f2)) ? (4.0 * WL_PI * WL_PI * f2 * ti / gs) : 0.0;
        }
        c->gain[m] = gain;
    }
}

static void wl_destroy(wl_core_t *c)
{
    if (c == NULL)
    {
        return;
    }
    free(c->mi);
    free(c->mj);
    free(c->mfx);
    free(c->mfy);
    free(c->mw);
    free(c->gain);
    free(c->tint);
    free(c->exr);
    free(c->exi);
    free(c->eyr);
    free(c->eyi);
    free(c->mask_k);
    free(c->mask_i);
    free(c->tap_kk);
    free(c->tap_ii);
    free(c->tap_ki);
    free(c->bkr);
    free(c->bki);
    free(c->bir);
    free(c->bii);
    free(c->skr);
    free(c->ski);
    free(c->sir);
    free(c->sii);
    wl_fft_free(&c->fft);
    free(c->pkk);
    free(c->pii);
    free(c->pxr);
    free(c->pxi);
    free(c->skk_r);
    free(c->skk_i);
    free(c->sii_r);
    free(c->sii_i);
    free(c->ski_r);
    free(c->ski_i);
    free(c->rxr);
    free(c->rxi);
    free(c->ryr);
    free(c->ryi);
    free(c->vmap_k);
    free(c->vmap_i);
    free(c->vmap_x);
    free(c->vsup_k);
    free(c->vsup_i);
    free(c->vsup_x);
    free(c);
}

/**
 * wl_create() - Allocate the estimator for given masks
 * @cfg:    Configuration (copied)
 * @mask_k: Valid pixels of the K maps [n * n], 0 / 1
 * @mask_i: Valid pixels of the I maps [n * n], 0 / 1
 *
 * Return: new estimator, or NULL (bad configuration or out of memory).
 */
static wl_core_t *wl_create(const wl_cfg_t *cfg, const float *mask_k, const float *mask_i)
{
    if (cfg->n < 8 || cfg->dx <= 0.0 || cfg->dt <= 0.0 || cfg->fmax <= cfg->fmin ||
        cfg->dv <= 0.0 || cfg->vmax <= cfg->dv)
    {
        return NULL;
    }
    wl_core_t *c = (wl_core_t *) calloc(1, sizeof(wl_core_t));
    if (c == NULL)
    {
        return NULL;
    }
    c->cfg = *cfg;
    if (c->cfg.pad < 1)
    {
        c->cfg.pad = 2;
    }
    if (c->cfg.maxlayers < 1 || c->cfg.maxlayers > WL_MAXLAYERS)
    {
        c->cfg.maxlayers = WL_MAXLAYERS;
    }
    if (c->cfg.fmaxk <= 0.0 || c->cfg.fmaxk > c->cfg.fmax)
    {
        c->cfg.fmaxk = c->cfg.fmax;
    }
    const int    n  = cfg->n;
    const double dx = cfg->dx;

    /* frequency grid and active modes */
    c->df   = 1.0 / (c->cfg.pad * n * dx);
    c->nfx  = (int) floor(cfg->fmax / c->df) + 1;
    c->nfyh = c->nfx - 1;
    c->nfy  = 2 * c->nfyh + 1;
    int    nmax = c->nfx * c->nfy;
    double flo  = 0.9 * cfg->fmin - c->df;
    c->mi       = (int *) malloc(sizeof(int) * (size_t) nmax);
    c->mj       = (int *) malloc(sizeof(int) * (size_t) nmax);
    c->mfx      = (double *) malloc(sizeof(double) * (size_t) nmax);
    c->mfy      = (double *) malloc(sizeof(double) * (size_t) nmax);
    c->mw       = (double *) malloc(sizeof(double) * (size_t) nmax);
    c->gain     = (double *) malloc(sizeof(double) * (size_t) nmax);
    c->tint     = (double *) malloc(sizeof(double) * (size_t) nmax);
    if (!c->mi || !c->mj || !c->mfx || !c->mfy || !c->mw || !c->gain || !c->tint)
    {
        wl_destroy(c);
        return NULL;
    }
    c->nm = 0;
    for (int i = 0; i < c->nfx; i++)
    {
        for (int j = 0; j < c->nfy; j++)
        {
            double fx = i * c->df;
            double fy = (j - c->nfyh) * c->df;
            double fr = hypot(fx, fy);
            if (fr < flo || fr > cfg->fmax || fr <= 0.0)
            {
                continue;
            }
            c->mi[c->nm]  = i;
            c->mj[c->nm]  = j;
            c->mfx[c->nm] = fx;
            c->mfy[c->nm] = fy;
            c->mw[c->nm]  = (i == 0) ? 0.5 : 1.0;
            c->nm++;
        }
    }
    if (c->nm < 16)
    {
        wl_destroy(c);
        return NULL;
    }
    wl_make_gain(c);

    /* forward kernels, pixel coordinates centred on the map */
    c->exr = (float *) malloc(sizeof(float) * (size_t) c->nfx * n);
    c->exi = (float *) malloc(sizeof(float) * (size_t) c->nfx * n);
    c->eyr = (float *) malloc(sizeof(float) * (size_t) c->nfy * n);
    c->eyi = (float *) malloc(sizeof(float) * (size_t) c->nfy * n);
    if (!c->exr || !c->exi || !c->eyr || !c->eyi)
    {
        wl_destroy(c);
        return NULL;
    }
    for (int i = 0; i < c->nfx; i++)
    {
        for (int x = 0; x < n; x++)
        {
            double ph              = 2.0 * WL_PI * (i * c->df) * ((x - 0.5 * (n - 1)) * dx);
            c->exr[(size_t) i * n + x] = (float) cos(ph);
            c->exi[(size_t) i * n + x] = (float) -sin(ph);
        }
    }
    for (int j = 0; j < c->nfy; j++)
    {
        for (int y = 0; y < n; y++)
        {
            double ph = 2.0 * WL_PI * ((j - c->nfyh) * c->df) * ((y - 0.5 * (n - 1)) * dx);
            c->eyr[(size_t) j * n + y] = (float) cos(ph);
            c->eyi[(size_t) j * n + y] = (float) -sin(ph);
        }
    }

    /* masks and tapers */
    size_t npix = (size_t) n * n;
    size_t ntap = (size_t) (2 * n - 1) * (2 * n - 1);
    c->mask_k   = (float *) malloc(sizeof(float) * npix);
    c->mask_i   = (float *) malloc(sizeof(float) * npix);
    c->tap_kk   = (double *) malloc(sizeof(double) * ntap);
    c->tap_ii   = (double *) malloc(sizeof(double) * ntap);
    c->tap_ki   = (double *) malloc(sizeof(double) * ntap);
    if (!c->mask_k || !c->mask_i || !c->tap_kk || !c->tap_ii || !c->tap_ki)
    {
        wl_destroy(c);
        return NULL;
    }
    memcpy(c->mask_k, mask_k, sizeof(float) * npix);
    memcpy(c->mask_i, mask_i, sizeof(float) * npix);
    c->t0_kk = wl_make_taper(c->mask_k, c->mask_k, n, c->tap_kk);
    c->t0_ii = wl_make_taper(c->mask_i, c->mask_i, n, c->tap_ii);
    c->t0_ki = wl_make_taper(c->mask_k, c->mask_i, n, c->tap_ki);
    if (c->t0_kk < 4.0 || c->t0_ii < 4.0 || c->t0_ki < 4.0)
    {
        wl_destroy(c);
        return NULL;
    }

    /* blocks */
    c->lmax = (int) ceil(cfg->lagmax_s / cfg->dt);
    if (c->lmax < 4)
    {
        c->lmax = 4;
    }
    c->nt = 32;
    while (c->nt < 2 * c->lmax)
    {
        c->nt *= 2;
    }
    c->nfft = 2 * c->nt;
    if (wl_fft_init(&c->fft, c->nfft) != 0)
    {
        wl_destroy(c);
        return NULL;
    }
    size_t nb = (size_t) c->nm * c->nt;
    size_t np = (size_t) c->nm * c->nfft;
    size_t ns = (size_t) c->nm * (2 * c->lmax + 1);
    c->bkr    = (float *) calloc(nb, sizeof(float));
    c->bki    = (float *) calloc(nb, sizeof(float));
    c->bir    = (float *) calloc(nb, sizeof(float));
    c->bii    = (float *) calloc(nb, sizeof(float));
    c->skr    = (float *) calloc(nb, sizeof(float));
    c->ski    = (float *) calloc(nb, sizeof(float));
    c->sir    = (float *) calloc(nb, sizeof(float));
    c->sii    = (float *) calloc(nb, sizeof(float));
    c->pkk    = (float *) calloc(np, sizeof(float));
    c->pii    = (float *) calloc(np, sizeof(float));
    c->pxr    = (float *) calloc(np, sizeof(float));
    c->pxi    = (float *) calloc(np, sizeof(float));
    c->skk_r  = (float *) calloc(ns, sizeof(float));
    c->skk_i  = (float *) calloc(ns, sizeof(float));
    c->sii_r  = (float *) calloc(ns, sizeof(float));
    c->sii_i  = (float *) calloc(ns, sizeof(float));
    c->ski_r  = (float *) calloc(ns, sizeof(float));
    c->ski_i  = (float *) calloc(ns, sizeof(float));
    if (!c->bkr || !c->bki || !c->bir || !c->bii || !c->skr || !c->ski || !c->sir || !c->sii ||
        !c->pkk || !c->pii || !c->pxr || !c->pxi || !c->skk_r || !c->skk_i || !c->sii_r ||
        !c->sii_i || !c->ski_r || !c->ski_i)
    {
        wl_destroy(c);
        return NULL;
    }

    /* correlation grid: step dx / 2, half-width 0.85 n pixels */
    c->nr   = (int) ceil(0.85 * n * 2.0);
    c->nrho = 2 * c->nr + 1;
    c->rxr  = (float *) malloc(sizeof(float) * (size_t) c->nfx * c->nrho);
    c->rxi  = (float *) malloc(sizeof(float) * (size_t) c->nfx * c->nrho);
    c->ryr  = (float *) malloc(sizeof(float) * (size_t) c->nfy * c->nrho);
    c->ryi  = (float *) malloc(sizeof(float) * (size_t) c->nfy * c->nrho);
    if (!c->rxr || !c->rxi || !c->ryr || !c->ryi)
    {
        wl_destroy(c);
        return NULL;
    }
    for (int i = 0; i < c->nfx; i++)
    {
        for (int r = 0; r < c->nrho; r++)
        {
            double ph = 2.0 * WL_PI * (i * c->df) * ((r - c->nr) * 0.5 * dx);
            c->rxr[(size_t) i * c->nrho + r] = (float) cos(ph);
            c->rxi[(size_t) i * c->nrho + r] = (float) sin(ph);
        }
    }
    for (int j = 0; j < c->nfy; j++)
    {
        for (int r = 0; r < c->nrho; r++)
        {
            double ph = 2.0 * WL_PI * ((j - c->nfyh) * c->df) * ((r - c->nr) * 0.5 * dx);
            c->ryr[(size_t) j * c->nrho + r] = (float) cos(ph);
            c->ryi[(size_t) j * c->nrho + r] = (float) sin(ph);
        }
    }

    /* velocity maps */
    c->nv     = 2 * (int) floor(cfg->vmax / cfg->dv + 0.5) + 1;
    size_t nq = (size_t) c->nv * c->nv;
    c->vmap_k = (float *) calloc(nq, sizeof(float));
    c->vmap_i = (float *) calloc(nq, sizeof(float));
    c->vmap_x = (float *) calloc(nq, sizeof(float));
    c->vsup_k = (float *) calloc(nq, sizeof(float));
    c->vsup_i = (float *) calloc(nq, sizeof(float));
    c->vsup_x = (float *) calloc(nq, sizeof(float));
    if (!c->vmap_k || !c->vmap_i || !c->vmap_x || !c->vsup_k || !c->vsup_i || !c->vsup_x)
    {
        wl_destroy(c);
        return NULL;
    }
    c->ksign_used = (cfg->ksign != 0) ? cfg->ksign : 1;
    return c;
}

/* ------------------------------------------------------------------------------------------ */
/* accumulation                                                                               */
/* ------------------------------------------------------------------------------------------ */

/** @brief Spatial transform of one masked map on the frequency grid, active modes only. */
static void wl_mft(const wl_core_t *c, const float *restrict map, float *restrict tr,
                   float *restrict ti, float *restrict outr, float *restrict outi, int stride)
{
    const int n   = c->cfg.n;
    const int nfx = c->nfx;

    /* x transform of every row: t[i][y] */
    for (int i = 0; i < nfx; i++)
    {
        const float *er = c->exr + (size_t) i * n;
        const float *ei = c->exi + (size_t) i * n;
        for (int y = 0; y < n; y++)
        {
            const float *row = map + (size_t) y * n;
            float        sr = 0.0f, si = 0.0f;
#pragma omp simd reduction(+ : sr, si)
            for (int x = 0; x < n; x++)
            {
                sr += row[x] * er[x];
                si += row[x] * ei[x];
            }
            tr[(size_t) i * n + y] = sr;
            ti[(size_t) i * n + y] = si;
        }
    }
    /* y transform, active modes only */
    for (int m = 0; m < c->nm; m++)
    {
        const float *ar = tr + (size_t) c->mi[m] * n;
        const float *ai = ti + (size_t) c->mi[m] * n;
        const float *er = c->eyr + (size_t) c->mj[m] * n;
        const float *ei = c->eyi + (size_t) c->mj[m] * n;
        float        sr = 0.0f, si = 0.0f;
#pragma omp simd reduction(+ : sr, si)
        for (int y = 0; y < n; y++)
        {
            sr += ar[y] * er[y] - ai[y] * ei[y];
            si += ar[y] * ei[y] + ai[y] * er[y];
        }
        outr[(size_t) m * stride] = sr;
        outi[(size_t) m * stride] = si;
    }
}

/**
 * wl_block_process() - Fourier transform the block copy along time, add its cross spectra
 *
 * Works on the copy made by wl_block_take(), so it may run in another thread than wl_push().
 */
static void wl_block_process(wl_core_t *c)
{
    const int nt   = c->nt;
    const int nfft = c->nfft;
    double    keep = 1.0;

    if (c->cfg.tavg > 0.0)
    {
        keep = exp(-(0.5 * nt * c->cfg.dt) / c->cfg.tavg);
    }
    const float fk = (float) keep;

#pragma omp parallel
    {
        float *wr = (float *) malloc(sizeof(float) * (size_t) nfft * 4);
        float *wi = wr + nfft;
        float *vr = wi + nfft;
        float *vi = vr + nfft;
#pragma omp for schedule(static)
        for (int m = 0; m < c->nm; m++)
        {
            if (wr == NULL)
            {
                continue;
            }
            memcpy(wr, c->skr + (size_t) m * nt, sizeof(float) * (size_t) nt);
            memcpy(wi, c->ski + (size_t) m * nt, sizeof(float) * (size_t) nt);
            memcpy(vr, c->sir + (size_t) m * nt, sizeof(float) * (size_t) nt);
            memcpy(vi, c->sii + (size_t) m * nt, sizeof(float) * (size_t) nt);
            memset(wr + nt, 0, sizeof(float) * (size_t) (nfft - nt));
            memset(wi + nt, 0, sizeof(float) * (size_t) (nfft - nt));
            memset(vr + nt, 0, sizeof(float) * (size_t) (nfft - nt));
            memset(vi + nt, 0, sizeof(float) * (size_t) (nfft - nt));
            wl_fft_fwd(&c->fft, wr, wi);
            wl_fft_fwd(&c->fft, vr, vi);
            float *pk = c->pkk + (size_t) m * nfft;
            float *pi = c->pii + (size_t) m * nfft;
            float *xr = c->pxr + (size_t) m * nfft;
            float *xi = c->pxi + (size_t) m * nfft;
#pragma omp simd
            for (int k = 0; k < nfft; k++)
            {
                pk[k] = fk * pk[k] + wr[k] * wr[k] + wi[k] * wi[k];
                pi[k] = fk * pi[k] + vr[k] * vr[k] + vi[k] * vi[k];
                xr[k] = fk * xr[k] + wr[k] * vr[k] + wi[k] * vi[k];
                xi[k] = fk * xi[k] + wr[k] * vi[k] - wi[k] * vr[k];
            }
        }
        free(wr);
    }
    c->nblk = keep * c->nblk + 1.0;
    c->nblk_total++;
    /* integration time: blocks overlap by half */
    c->tint_s = keep * c->tint_s + ((c->nblk_total == 1) ? 1.0 : 0.5) * nt * c->cfg.dt;
}

/** @brief Forget the frames of the current, incomplete block (after a gap in the frames). */
static void wl_reset_block(wl_core_t *c)
{
    c->nbuf = 0;
}

/** @brief Forget everything accumulated. */
static void wl_reset(wl_core_t *c)
{
    size_t np = (size_t) c->nm * c->nfft;
    memset(c->pkk, 0, sizeof(float) * np);
    memset(c->pii, 0, sizeof(float) * np);
    memset(c->pxr, 0, sizeof(float) * np);
    memset(c->pxi, 0, sizeof(float) * np);
    c->nbuf       = 0;
    c->nblk       = 0.0;
    c->nblk_total = 0;
    c->tint_s     = 0.0;
}

/**
 * wl_push() - Add one frame of both channels
 * @kmap: K map [n * n], masked (0 outside its mask) and mean-subtracted
 * @imap: I map [n * n], masked and mean-subtracted
 * @work: Scratch [2 * nfx * n] floats
 *
 * Return: 1 when the block is full: call wl_block_take() before the next frame.
 */
static int wl_push(wl_core_t *c, const float *kmap, const float *imap, float *work)
{
    const int nt = c->nt;
    float    *tr = work;
    float    *ti = work + (size_t) c->nfx * c->cfg.n;

    if (c->nbuf >= nt)
    {
        return 1;
    }
    wl_mft(c, kmap, tr, ti, c->bkr + c->nbuf, c->bki + c->nbuf, nt);
    wl_mft(c, imap, tr, ti, c->bir + c->nbuf, c->bii + c->nbuf, nt);
    c->nbuf++;
    c->nframes++;
    return (c->nbuf >= nt);
}

/**
 * wl_block_take() - Close the full block and start the next one
 * @copy: 1: copy the block for wl_block_process(); 0: drop it (the previous copy is still
 *        being processed)
 *
 * The second half of the block starts the next one (50% overlap).
 */
static void wl_block_take(wl_core_t *c, int copy)
{
    const int nt   = c->nt;
    const int half = nt / 2;

    if (c->nbuf < nt)
    {
        return;
    }
    if (copy)
    {
        size_t nb = sizeof(float) * (size_t) c->nm * nt;
        memcpy(c->skr, c->bkr, nb);
        memcpy(c->ski, c->bki, nb);
        memcpy(c->sir, c->bir, nb);
        memcpy(c->sii, c->bii, nb);
    }
    for (int m = 0; m < c->nm; m++)
    {
        size_t o = (size_t) m * nt;
        memmove(c->bkr + o, c->bkr + o + half, sizeof(float) * (size_t) half);
        memmove(c->bki + o, c->bki + o + half, sizeof(float) * (size_t) half);
        memmove(c->bir + o, c->bir + o + half, sizeof(float) * (size_t) half);
        memmove(c->bii + o, c->bii + o + half, sizeof(float) * (size_t) half);
    }
    c->nbuf = half;
}

/* ------------------------------------------------------------------------------------------ */
/* analysis                                                                                   */
/* ------------------------------------------------------------------------------------------ */

/** @brief Accumulated spectra -> lag spectra S_ab(tau, f), per pixel pair, unbiased in tau. */
static void wl_lag_spectra(wl_core_t *c)
{
    const int nfft = c->nfft;
    const int lmax = c->lmax;
    const int nl   = 2 * lmax + 1;

#pragma omp parallel
    {
        float *wr = (float *) malloc(sizeof(float) * (size_t) nfft * 2);
        float *wi = wr + nfft;
#pragma omp for schedule(static)
        for (int m = 0; m < c->nm; m++)
        {
            if (wr == NULL)
            {
                continue;
            }
            for (int pair = 0; pair < 3; pair++)
            {
                const float *pr = (pair == 0) ? c->pkk : ((pair == 1) ? c->pii : c->pxr);
                const float *pi = (pair == 2) ? c->pxi : NULL;
                float       *sr = (pair == 0) ? c->skk_r : ((pair == 1) ? c->sii_r : c->ski_r);
                float       *si = (pair == 0) ? c->skk_i : ((pair == 1) ? c->sii_i : c->ski_i);
                double       t0 = (pair == 0) ? c->t0_kk : ((pair == 1) ? c->t0_ii : c->t0_ki);
                /* inverse FFT = conj(FFT(conj(P))) / nfft */
                for (int k = 0; k < nfft; k++)
                {
                    wr[k] = pr[(size_t) m * nfft + k];
                    wi[k] = (pi != NULL) ? -pi[(size_t) m * nfft + k] : 0.0f;
                }
                wl_fft_fwd(&c->fft, wr, wi);
                for (int tau = -lmax; tau <= lmax; tau++)
                {
                    int    idx = (tau >= 0) ? tau : (nfft + tau);
                    double nrm = 1.0 / ((double) nfft * c->nblk * (c->nt - abs(tau)) * t0);
                    sr[(size_t) m * nl + tau + lmax] = (float) (wr[idx] * nrm);
                    si[(size_t) m * nl + tau + lmax] = (float) (-wi[idx] * nrm);
                }
            }
        }
        free(wr);
    }
}

/** @brief Lag weight of the velocity maps: ramp times a Hann roll-off towards the last lag. */
static inline double wl_lag_weight(int k, int lmax)
{
    return (double) k * (0.5 + 0.5 * cos(WL_PI * k / (lmax + 1.0)));
}

/**
 * wl_velocity_map() - Filtered back-projection velocity map of one channel pair
 * @sr, @si:  Lag spectrum [nm * (2 lmax + 1)]
 * @norm:     Zero-lag power per mode used to normalise [nm]
 * @tap:      Pixel-pair taper of the pair
 * @fhi:      Upper band limit [cycles/m]
 * @both:     1: stack both lag signs (cross pair), 0: positive lags only
 * @lagoff:   Lag offset [frames] added to tau (delay of the first channel)
 * @vmap:     Out: map [nv * nv], row = vy, column = vx
 * @vsup:     Out: support (sum of squared weights)
 */
static void wl_velocity_map(const wl_core_t *c, const float *sr, const float *si,
                            const double *norm, const double *tap, double fhi, int both,
                            double lagoff, float *vmap, float *vsup)
{
    const wl_cfg_t *g    = &c->cfg;
    const int       nm   = c->nm;
    const int       lmax = c->lmax;
    const int       nl   = 2 * lmax + 1;
    const int       nv   = c->nv;
    const int       nrho = c->nrho;
    const int       nfx  = c->nfx;
    const int       nfy  = c->nfy;
    const size_t    nq   = (size_t) nv * nv;

    /* band and ramp weight per mode */
    double *b    = (double *) malloc(sizeof(double) * (size_t) nm);
    double  nmax = 0.0;
    double  bsum = 0.0;
    for (int m = 0; m < nm; m++)
    {
        if (norm[m] > nmax)
        {
            nmax = norm[m];
        }
    }
    const double edge = 0.1 * (fhi - g->fmin);
    for (int m = 0; m < nm; m++)
    {
        double fr = hypot(c->mfx[m], c->mfy[m]);
        double lo = (fr - g->fmin) / edge;
        double hi = (fhi - fr) / edge;
        lo        = (lo < 0.0) ? 0.0 : ((lo > 1.0) ? 1.0 : lo);
        hi        = (hi < 0.0) ? 0.0 : ((hi > 1.0) ? 1.0 : hi);
        double w  = fr * (0.5 - 0.5 * cos(WL_PI * lo)) * (0.5 - 0.5 * cos(WL_PI * hi)) * c->mw[m];
        if (!(norm[m] > 1e-3 * nmax))
        {
            w = 0.0;
        }
        b[m] = w;
        bsum += 2.0 * w;
    }
    double *num = (double *) calloc(nq, sizeof(double));
    double *den = (double *) calloc(nq, sizeof(double));
    if (b == NULL || num == NULL || den == NULL || !(bsum > 0.0))
    {
        memset(vmap, 0, sizeof(float) * nq);
        memset(vsup, 0, sizeof(float) * nq);
        free(b);
        free(num);
        free(den);
        return;
    }
    for (int m = 0; m < nm; m++)
    {
        b[m] /= bsum * ((norm[m] > 0.0) ? norm[m] : 1.0);
    }

    const int    nlag  = both ? 2 * lmax : lmax;
    const double rstep = 0.5 * g->dx; /* rho grid step [m] */

#pragma omp parallel
    {
        float  *gr  = (float *) calloc((size_t) nfx * nfy, sizeof(float));
        float  *gi  = (float *) calloc((size_t) nfx * nfy, sizeof(float));
        float  *ur  = (float *) malloc(sizeof(float) * (size_t) nfx * nrho);
        float  *ui  = (float *) malloc(sizeof(float) * (size_t) nfx * nrho);
        float  *gg  = (float *) malloc(sizeof(float) * (size_t) nrho * nrho);
        double *tnu = (double *) calloc(nq, sizeof(double));
        double *tde = (double *) calloc(nq, sizeof(double));
        int     ok  = (gr && gi && ur && ui && gg && tnu && tde);

#pragma omp for schedule(dynamic, 4)
        for (int il = 0; il < nlag; il++)
        {
            if (!ok)
            {
                continue;
            }
            int    k   = (il < lmax) ? (il + 1) : (il - lmax + 1);
            int    s   = (il < lmax) ? 1 : -1;
            double w   = wl_lag_weight(k, lmax);
            double tau = (s * k + lagoff) * g->dt;
            /* normalised, weighted spectrum of this lag on the full (i, j) grid */
            for (int m = 0; m < nm; m++)
            {
                size_t o  = (size_t) c->mi[m] * nfy + c->mj[m];
                size_t is = (size_t) m * nl + (s * k + lmax);
                gr[o]     = (float) (sr[is] * b[m]);
                gi[o]     = (float) (si[is] * b[m]);
            }
            /* u(i, ry) = sum_j g(i, j) exp(+2 pi i fy ry) */
            for (int i = 0; i < nfx; i++)
            {
                float *pur = ur + (size_t) i * nrho;
                float *pui = ui + (size_t) i * nrho;
                memset(pur, 0, sizeof(float) * (size_t) nrho);
                memset(pui, 0, sizeof(float) * (size_t) nrho);
                for (int j = 0; j < nfy; j++)
                {
                    float ar = gr[(size_t) i * nfy + j];
                    float ai = gi[(size_t) i * nfy + j];
                    if (ar == 0.0f && ai == 0.0f)
                    {
                        continue;
                    }
                    const float *er = c->ryr + (size_t) j * nrho;
                    const float *ei = c->ryi + (size_t) j * nrho;
#pragma omp simd
                    for (int r = 0; r < nrho; r++)
                    {
                        pur[r] += ar * er[r] - ai * ei[r];
                        pui[r] += ar * ei[r] + ai * er[r];
                    }
                }
            }
            /* gg(ry, rx) = 2 Re sum_i u(i, ry) exp(+2 pi i fx rx) */
            memset(gg, 0, sizeof(float) * (size_t) nrho * nrho);
            for (int i = 0; i < nfx; i++)
            {
                const float *er = c->rxr + (size_t) i * nrho;
                const float *ei = c->rxi + (size_t) i * nrho;
                for (int ry = 0; ry < nrho; ry++)
                {
                    float  ar  = 2.0f * ur[(size_t) i * nrho + ry];
                    float  ai  = 2.0f * ui[(size_t) i * nrho + ry];
                    float *row = gg + (size_t) ry * nrho;
#pragma omp simd
                    for (int rx = 0; rx < nrho; rx++)
                    {
                        row[rx] += ar * er[rx] - ai * ei[rx];
                    }
                }
            }
            /* stack along rho = v tau */
            for (int iy = 0; iy < nv; iy++)
            {
                double vy = (iy - nv / 2) * g->dv;
                for (int ix = 0; ix < nv; ix++)
                {
                    double vx = (ix - nv / 2) * g->dv;
                    double tv = wl_taper_at(tap, g->n, vx * tau / g->dx, vy * tau / g->dx);
                    if (tv <= 0.0)
                    {
                        continue;
                    }
                    double gv = wl_bilin_f(gg, nrho, nrho, vx * tau / rstep + c->nr,
                                           vy * tau / rstep + c->nr);
                    tnu[(size_t) iy * nv + ix] += w * tv * gv;
                    tde[(size_t) iy * nv + ix] += w * tv * tv;
                }
            }
        }
#pragma omp critical
        {
            if (ok)
            {
                for (size_t q = 0; q < nq; q++)
                {
                    num[q] += tnu[q];
                    den[q] += tde[q];
                }
            }
        }
        free(gr);
        free(gi);
        free(ur);
        free(ui);
        free(gg);
        free(tnu);
        free(tde);
    }
    for (size_t q = 0; q < nq; q++)
    {
        vmap[q] = (den[q] > 0.0) ? (float) (num[q] / den[q]) : 0.0f;
        vsup[q] = (float) den[q];
    }
    free(b);
    free(num);
    free(den);
}

/** @brief Candidate peak of a velocity map. */
typedef struct
{
    double vx, vy, val, snr;
    int    src; /**< 0: K map, 1: I map, 2: cross map */
} wl_peak_t;

static int wl_cmp_peak_snr(const void *a, const void *b)
{
    double sa = ((const wl_peak_t *) a)->snr;
    double sb = ((const wl_peak_t *) b)->snr;
    return (sa < sb) - (sa > sb);
}

/** @brief Median and robust sigma (1.4826 MAD) of sign * map over the supported pixels. */
static void wl_map_stats(const wl_core_t *c, const float *vmap, const float *vsup, double sign,
                         double *med, double *sig)
{
    const size_t nq   = (size_t) c->nv * c->nv;
    float       *tmp  = (float *) malloc(sizeof(float) * nq);
    float        smax = 0.0f;
    size_t       cnt  = 0;

    *med = 0.0;
    *sig = 1.0;
    if (tmp == NULL)
    {
        return;
    }
    for (size_t q = 0; q < nq; q++)
    {
        if (vsup[q] > smax)
        {
            smax = vsup[q];
        }
    }
    for (size_t q = 0; q < nq; q++)
    {
        if (vsup[q] > 0.02f * smax)
        {
            tmp[cnt++] = (float) (sign * vmap[q]);
        }
    }
    if (cnt > 8)
    {
        qsort(tmp, cnt, sizeof(float), wl_cmp_float);
        double m = tmp[cnt / 2];
        for (size_t q = 0; q < cnt; q++)
        {
            tmp[q] = (float) fabs(tmp[q] - m);
        }
        qsort(tmp, cnt, sizeof(float), wl_cmp_float);
        *med = m;
        *sig = 1.4826 * tmp[cnt / 2] + 1e-30;
    }
    free(tmp);
}

/** @brief Local maxima of sign * map above med + nsigma sig; parabolic sub-grid position. */
static int wl_find_peaks(const wl_core_t *c, const float *vmap, const float *vsup, double sign,
                         double med, double sig, int src, wl_peak_t *out, int nout)
{
    const wl_cfg_t *g    = &c->cfg;
    const int       nv   = c->nv;
    float           smax = 0.0f;
    int             np   = 0;
    wl_peak_t      *all  = (wl_peak_t *) malloc(sizeof(wl_peak_t) * 256);

    if (all == NULL)
    {
        return 0;
    }
    for (size_t q = 0; q < (size_t) nv * nv; q++)
    {
        if (vsup[q] > smax)
        {
            smax = vsup[q];
        }
    }
    for (int iy = 1; iy < nv - 1 && np < 256; iy++)
    {
        for (int ix = 1; ix < nv - 1 && np < 256; ix++)
        {
            size_t q = (size_t) iy * nv + ix;
            double v = sign * vmap[q];
            if (!(vsup[q] > 0.02f * smax) || (v - med) < g->nsigma * sig)
            {
                continue;
            }
            int ismax = 1;
            for (int dy = -1; dy <= 1 && ismax; dy++)
            {
                for (int dxx = -1; dxx <= 1; dxx++)
                {
                    if (sign * vmap[q + dy * nv + dxx] > v)
                    {
                        ismax = 0;
                        break;
                    }
                }
            }
            if (!ismax)
            {
                continue;
            }
            double cx = sign * (vmap[q - 1] + vmap[q + 1]) - 2.0 * v;
            double cy = sign * (vmap[q - nv] + vmap[q + nv]) - 2.0 * v;
            double ox = (cx < 0.0) ? 0.5 * sign * (vmap[q - 1] - vmap[q + 1]) / cx : 0.0;
            double oy = (cy < 0.0) ? 0.5 * sign * (vmap[q - nv] - vmap[q + nv]) / cy : 0.0;
            ox        = (ox < -1.0) ? -1.0 : ((ox > 1.0) ? 1.0 : ox);
            oy        = (oy < -1.0) ? -1.0 : ((oy > 1.0) ? 1.0 : oy);
            all[np].vx  = (ix - nv / 2 + ox) * g->dv;
            all[np].vy  = (iy - nv / 2 + oy) * g->dv;
            all[np].val = v;
            all[np].snr = (v - med) / sig;
            all[np].src = src;
            np++;
        }
    }
    qsort(all, (size_t) np, sizeof(wl_peak_t), wl_cmp_peak_snr);
    int nk = 0;
    for (int i = 0; i < np && nk < nout; i++)
    {
        if (all[i].val >= g->minfrac * all[0].val)
        {
            out[nk++] = all[i];
        }
    }
    free(all);
    return nk;
}

/** @brief Solve the complex n x n system a x = b in place (Gauss-Jordan), also invert a. */
static int wl_csolve(int n, double ar[WL_MAXLAYERS][WL_MAXLAYERS],
                     double ai[WL_MAXLAYERS][WL_MAXLAYERS], double invr[WL_MAXLAYERS][WL_MAXLAYERS],
                     double invi[WL_MAXLAYERS][WL_MAXLAYERS])
{
    for (int i = 0; i < n; i++)
    {
        for (int j = 0; j < n; j++)
        {
            invr[i][j] = (i == j) ? 1.0 : 0.0;
            invi[i][j] = 0.0;
        }
    }
    for (int col = 0; col < n; col++)
    {
        int    piv  = col;
        double best = ar[col][col] * ar[col][col] + ai[col][col] * ai[col][col];
        for (int r = col + 1; r < n; r++)
        {
            double v = ar[r][col] * ar[r][col] + ai[r][col] * ai[r][col];
            if (v > best)
            {
                best = v;
                piv  = r;
            }
        }
        if (!(best > 0.0))
        {
            return -1;
        }
        if (piv != col)
        {
            for (int j = 0; j < n; j++)
            {
                double t      = ar[col][j];
                ar[col][j]    = ar[piv][j];
                ar[piv][j]    = t;
                t             = ai[col][j];
                ai[col][j]    = ai[piv][j];
                ai[piv][j]    = t;
                t             = invr[col][j];
                invr[col][j]  = invr[piv][j];
                invr[piv][j]  = t;
                t             = invi[col][j];
                invi[col][j]  = invi[piv][j];
                invi[piv][j]  = t;
            }
        }
        double pr = ar[col][col] / best;
        double pi = -ai[col][col] / best; /* 1 / pivot */
        for (int j = 0; j < n; j++)
        {
            double xr    = ar[col][j] * pr - ai[col][j] * pi;
            double xi    = ar[col][j] * pi + ai[col][j] * pr;
            ar[col][j]   = xr;
            ai[col][j]   = xi;
            xr           = invr[col][j] * pr - invi[col][j] * pi;
            xi           = invr[col][j] * pi + invi[col][j] * pr;
            invr[col][j] = xr;
            invi[col][j] = xi;
        }
        for (int r = 0; r < n; r++)
        {
            if (r == col)
            {
                continue;
            }
            double fr = ar[r][col];
            double fi = ai[r][col];
            if (fr == 0.0 && fi == 0.0)
            {
                continue;
            }
            for (int j = 0; j < n; j++)
            {
                ar[r][j]   -= fr * ar[col][j] - fi * ai[col][j];
                ai[r][j]   -= fr * ai[col][j] + fi * ar[col][j];
                invr[r][j] -= fr * invr[col][j] - fi * invi[col][j];
                invi[r][j] -= fr * invi[col][j] + fi * invr[col][j];
            }
        }
    }
    return 0;
}

/**
 * wl_decompose() - Per-frequency least-squares split of one lag spectrum into frozen layers
 * @sr, @si:  Lag spectrum [nm * (2 lmax + 1)]
 * @tap:      Pixel-pair taper of the pair
 * @nk:       Number of layers
 * @vx, @vy:  Layer velocities [m/s]
 * @lagoff:   Lag offset [frames]
 * @pr, @pi:  Out: layer power per mode [nk * nm]
 * @cw:       Out: weight 1 / [G^-1]_ll per mode [nk * nm]
 */
static void wl_decompose(const wl_core_t *c, const float *sr, const float *si, const double *tap,
                         int nk, const double *vx, const double *vy, double lagoff, double *pr,
                         double *pi, double *cw)
{
    const wl_cfg_t *g    = &c->cfg;
    const int       lmax = c->lmax;
    const int       nl   = 2 * lmax + 1;
    const double    reg  = 1e-3;
    const int       nlag = 2 * lmax;

    /* taper of every layer at every lag, and the lag weights */
    double *tl    = (double *) malloc(sizeof(double) * (size_t) nlag * nk);
    double *wl    = (double *) malloc(sizeof(double) * (size_t) nlag);
    double *taus  = (double *) malloc(sizeof(double) * (size_t) nlag);
    double  scale[WL_MAXLAYERS];
    if (tl == NULL || wl == NULL || taus == NULL)
    {
        free(tl);
        free(wl);
        free(taus);
        return;
    }
    for (int l = 0; l < nk; l++)
    {
        scale[l] = 0.0;
    }
    for (int il = 0; il < nlag; il++)
    {
        int k    = (il < lmax) ? (il + 1) : (il - lmax + 1);
        int s    = (il < lmax) ? 1 : -1;
        taus[il] = (s * k + lagoff) * g->dt;
        wl[il]   = wl_lag_weight(k, lmax) / k;
        for (int l = 0; l < nk; l++)
        {
            double t = wl_taper_at(tap, g->n, vx[l] * taus[il] / g->dx, vy[l] * taus[il] / g->dx);
            tl[(size_t) il * nk + l] = t;
            scale[l] += wl[il] * t * t;
        }
    }

#pragma omp parallel for schedule(static)
    for (int m = 0; m < c->nm; m++)
    {
        double gr[WL_MAXLAYERS][WL_MAXLAYERS], gi[WL_MAXLAYERS][WL_MAXLAYERS];
        double ir[WL_MAXLAYERS][WL_MAXLAYERS], ii[WL_MAXLAYERS][WL_MAXLAYERS];
        double yr[WL_MAXLAYERS], yi[WL_MAXLAYERS], br[WL_MAXLAYERS], bi[WL_MAXLAYERS];
        double fv[WL_MAXLAYERS];

        for (int l = 0; l < nk; l++)
        {
            yr[l] = 0.0;
            yi[l] = 0.0;
            fv[l] = 2.0 * WL_PI * (c->mfx[m] * vx[l] + c->mfy[m] * vy[l]);
            for (int q = 0; q < nk; q++)
            {
                gr[l][q] = 0.0;
                gi[l][q] = 0.0;
            }
        }
        for (int il = 0; il < nlag; il++)
        {
            int           k  = (il < lmax) ? (il + 1) : (il - lmax + 1);
            int           s  = (il < lmax) ? 1 : -1;
            const double *t  = tl + (size_t) il * nk;
            double        w  = wl[il];
            double        xr = sr[(size_t) m * nl + (s * k + lmax)];
            double        xi = si[(size_t) m * nl + (s * k + lmax)];
            int           any = 0;
            /* beta_l = t_l exp(-i fv_l tau) */
            for (int l = 0; l < nk; l++)
            {
                br[l] = t[l] * cos(fv[l] * taus[il]);
                bi[l] = -t[l] * sin(fv[l] * taus[il]);
                any  |= (t[l] > 0.0);
            }
            if (!any)
            {
                continue;
            }
            for (int l = 0; l < nk; l++)
            {
                /* y_l += w conj(beta_l) S ; G_lq += w conj(beta_l) beta_q */
                yr[l] += w * (br[l] * xr + bi[l] * xi);
                yi[l] += w * (br[l] * xi - bi[l] * xr);
                for (int q = 0; q < nk; q++)
                {
                    gr[l][q] += w * (br[l] * br[q] + bi[l] * bi[q]);
                    gi[l][q] += w * (br[l] * bi[q] - bi[l] * br[q]);
                }
            }
        }
        for (int l = 0; l < nk; l++)
        {
            gr[l][l] += reg * scale[l] + 1e-300;
        }
        if (wl_csolve(nk, gr, gi, ir, ii) != 0)
        {
            for (int l = 0; l < nk; l++)
            {
                pr[(size_t) l * c->nm + m] = 0.0;
                pi[(size_t) l * c->nm + m] = 0.0;
                cw[(size_t) l * c->nm + m] = 0.0;
            }
            continue;
        }
        for (int l = 0; l < nk; l++)
        {
            double ar = 0.0, ai = 0.0;
            for (int q = 0; q < nk; q++)
            {
                ar += ir[l][q] * yr[q] - ii[l][q] * yi[q];
                ai += ir[l][q] * yi[q] + ii[l][q] * yr[q];
            }
            pr[(size_t) l * c->nm + m] = ar;
            pi[(size_t) l * c->nm + m] = ai;
            cw[(size_t) l * c->nm + m] = (ir[l][l] > 0.0) ? (1.0 / ir[l][l]) : 0.0;
        }
    }
    free(tl);
    free(wl);
    free(taus);
}

/**
 * wl_analyze() - Velocity maps, layer detection, layer split and distances
 *
 * Return: number of layers found (>= 0), or -1 when nothing has been accumulated yet.
 */
static int wl_analyze(wl_core_t *c)
{
    const wl_cfg_t *g    = &c->cfg;
    const int       nm   = c->nm;
    const int       lmax = c->lmax;
    const int       nl   = 2 * lmax + 1;

    if (c->nblk < 0.5)
    {
        return -1;
    }
    wl_lag_spectra(c);

    double *nk_ = (double *) malloc(sizeof(double) * (size_t) nm * 3);
    if (nk_ == NULL)
    {
        return -1;
    }
    double *n_k = nk_;
    double *n_i = nk_ + nm;
    double *n_x = nk_ + 2 * nm;
    for (int m = 0; m < nm; m++)
    {
        double a = c->skk_r[(size_t) m * nl + lmax];
        double b = c->sii_r[(size_t) m * nl + lmax];
        n_k[m]   = (a > 0.0) ? a : 0.0;
        n_i[m]   = (b > 0.0) ? b : 0.0;
        n_x[m]   = sqrt(n_k[m] * n_i[m]);
    }
    wl_velocity_map(c, c->skk_r, c->skk_i, n_k, c->tap_kk, g->fmaxk, 0, 0.0, c->vmap_k, c->vsup_k);
    wl_velocity_map(c, c->sii_r, c->sii_i, n_i, c->tap_ii, g->fmax, 0, 0.0, c->vmap_i, c->vsup_i);
    wl_velocity_map(c, c->ski_r, c->ski_i, n_x, c->tap_ki, g->fmaxk, 1, g->klag, c->vmap_x,
                    c->vsup_x);

    /* sign of K relative to the atmosphere: the cross map of a layer above the telescope is
     * negative (dI/I = -z laplacian(OPD)) when K has the sign of the atmosphere */
    int ksign = g->ksign;
    if (ksign == 0)
    {
        double vlo = 0.0, vhi = 0.0;
        for (size_t q = 0; q < (size_t) c->nv * c->nv; q++)
        {
            if (c->vmap_x[q] < vlo)
            {
                vlo = c->vmap_x[q];
            }
            if (c->vmap_x[q] > vhi)
            {
                vhi = c->vmap_x[q];
            }
        }
        ksign = (vhi > -vlo) ? -1 : 1;
    }
    c->ksign_used = ksign;

    /* peaks of the three maps, merged (highest significance first) */
    wl_peak_t cand[3 * WL_MAXLAYERS];
    int       nc = 0;
    wl_map_stats(c, c->vmap_k, c->vsup_k, 1.0, &c->med_k, &c->sig_k);
    wl_map_stats(c, c->vmap_i, c->vsup_i, 1.0, &c->med_i, &c->sig_i);
    wl_map_stats(c, c->vmap_x, c->vsup_x, -ksign, &c->med_x, &c->sig_x);
    nc += wl_find_peaks(c, c->vmap_k, c->vsup_k, 1.0, c->med_k, c->sig_k, 0, cand + nc,
                        WL_MAXLAYERS);
    nc += wl_find_peaks(c, c->vmap_i, c->vsup_i, 1.0, c->med_i, c->sig_i, 1, cand + nc,
                        WL_MAXLAYERS);
    nc += wl_find_peaks(c, c->vmap_x, c->vsup_x, -ksign, c->med_x, c->sig_x, 2, cand + nc,
                        WL_MAXLAYERS);
    qsort(cand, (size_t) nc, sizeof(wl_peak_t), wl_cmp_peak_snr);
    int    nk = 0;
    double vx[WL_MAXLAYERS], vy[WL_MAXLAYERS];
    memset(c->layers, 0, sizeof(c->layers));
    for (int i = 0; i < nc && nk < g->maxlayers; i++)
    {
        int isnew = 1;
        for (int l = 0; l < nk; l++)
        {
            if (hypot(cand[i].vx - vx[l], cand[i].vy - vy[l]) < g->minsep)
            {
                isnew = 0;
                break;
            }
        }
        if (isnew)
        {
            vx[nk]               = cand[i].vx;
            vy[nk]               = cand[i].vy;
            c->layers[nk].vx     = cand[i].vx;
            c->layers[nk].vy     = cand[i].vy;
            c->layers[nk].snr    = cand[i].snr;
            nk++;
        }
    }
    c->nlayers = nk;

    /* band power of both channels */
    double tot_k = 0.0, tot_i = 0.0;
    for (int m = 0; m < nm; m++)
    {
        double fr = hypot(c->mfx[m], c->mfy[m]);
        if (fr >= g->fmin && fr <= g->fmaxk)
        {
            tot_k += c->mw[m] * n_k[m];
        }
        if (fr >= g->fmin && fr <= g->fmax)
        {
            tot_i += c->mw[m] * n_i[m];
        }
    }
    c->pow_k = 2.0 * tot_k;
    c->pow_i = 2.0 * tot_i;
    if (nk == 0)
    {
        free(nk_);
        return 0;
    }

    /* layer split of the three lag spectra */
    size_t  sz  = (size_t) nk * nm;
    double *buf = (double *) malloc(sizeof(double) * sz * 8);
    if (buf == NULL)
    {
        free(nk_);
        return nk;
    }
    double *ar = buf, *ai = buf + sz, *ca = buf + 2 * sz;
    double *br = buf + 3 * sz, *bi = buf + 4 * sz, *cb = buf + 5 * sz;
    double *xr = buf + 6 * sz, *xi = buf + 7 * sz;
    double *cx = (double *) malloc(sizeof(double) * sz);
    if (cx == NULL)
    {
        free(buf);
        free(nk_);
        return nk;
    }
    wl_decompose(c, c->skk_r, c->skk_i, c->tap_kk, nk, vx, vy, 0.0, ar, ai, ca);
    wl_decompose(c, c->sii_r, c->sii_i, c->tap_ii, nk, vx, vy, 0.0, br, bi, cb);
    wl_decompose(c, c->ski_r, c->ski_i, c->tap_ki, nk, vx, vy, g->klag, xr, xi, cx);

    const int    nv   = c->nv;
    const double fbin = (g->fmaxk - g->fmin) / WL_NZBINS;
    for (int l = 0; l < nk; l++)
    {
        wl_layer_t *L = &c->layers[l];
        L->speed      = hypot(L->vx, L->vy);
        L->dir        = fmod(atan2(L->vy, L->vx) * 180.0 / WL_PI + 360.0, 360.0);
        if (L->dir > 359.95)
        {
            L->dir = 0.0; /* reads 360.0 with one decimal otherwise */
        }
        double px     = L->vx / g->dv + nv / 2;
        double py     = L->vy / g->dv + nv / 2;
        L->pk_k       = wl_bilin_f(c->vmap_k, nv, nv, px, py);
        L->pk_i       = wl_bilin_f(c->vmap_i, nv, nv, px, py);
        L->pk_x       = -ksign * wl_bilin_f(c->vmap_x, nv, nv, px, py);

        double wmax = 0.0;
        for (int m = 0; m < nm; m++)
        {
            double w = sqrt(ca[(size_t) l * nm + m] * cx[(size_t) l * nm + m]);
            if (w > wmax)
            {
                wmax = w;
            }
        }
        double num = 0.0, den = 0.0, sa = 0.0, sb = 0.0, sx = 0.0, pa = 0.0, pb = 0.0;
        double nax = 0.0, dax = 0.0, ndg = 0.0, ddg = 0.0;
        double bn[WL_NZBINS], bd[WL_NZBINS], bf[WL_NZBINS], bw[WL_NZBINS];
        for (int b = 0; b < WL_NZBINS; b++)
        {
            bn[b] = bd[b] = bf[b] = bw[b] = 0.0;
        }
        for (int m = 0; m < nm; m++)
        {
            double fr = hypot(c->mfx[m], c->mfy[m]);
            double a  = ar[(size_t) l * nm + m];
            double b  = br[(size_t) l * nm + m];
            double x  = xr[(size_t) l * nm + m];
            if (fr >= g->fmin && fr <= g->fmax)
            {
                pb += c->mw[m] * b;
            }
            if (fr < g->fmin || fr > g->fmaxk)
            {
                continue;
            }
            pa += c->mw[m] * a;
            double gn = -ksign * c->gain[m];
            if (gn == 0.0 || !(wmax > 0.0))
            {
                continue;
            }
            double w = c->mw[m] * sqrt(ca[(size_t) l * nm + m] * cx[(size_t) l * nm + m]) / wmax;
            num += w * gn * x;
            den += w * gn * gn * a;
            sa  += w * a;
            sb  += w * b;
            sx  += w * x;
            int ib = (int) ((fr - g->fmin) / fbin);
            ib     = (ib < 0) ? 0 : ((ib >= WL_NZBINS) ? WL_NZBINS - 1 : ib);
            bn[ib] += w * gn * x;
            bd[ib] += w * gn * gn * a;
            bf[ib] += w * fr;
            bw[ib] += w;
            /* sectors, beyond twice the modulation radius: along the pyramid axes, diagonals */
            double fxa = fabs(c->mfx[m]) * g->diam;
            double fya = fabs(c->mfy[m]) * g->diam;
            if (fr * g->diam > 2.0 * g->modrad)
            {
                if (fmin(fxa, fya) < 1.5)
                {
                    nax += w * gn * x;
                    dax += w * gn * gn * a;
                }
                else if (fabs(fxa - fya) < 2.0)
                {
                    ndg += w * gn * x;
                    ddg += w * gn * gn * a;
                }
            }
        }
        L->frac_k = (tot_k > 0.0) ? pa / tot_k : 0.0;
        L->frac_i = (tot_i > 0.0) ? pb / tot_i : 0.0;
        L->z      = (den > 0.0) ? num / den : NAN;
        L->coh    = (sa > 0.0 && sb > 0.0) ? (-ksign * sx / sqrt(sa * sb)) : 0.0;
        L->z_axis = (dax > 0.0) ? nax / dax : NAN;
        L->z_diag = (ddg > 0.0) ? ndg / ddg : NAN;
        L->nzf    = 0;
        double s1 = 0.0, s2 = 0.0;
        for (int b = 0; b < WL_NZBINS; b++)
        {
            if (bd[b] > 0.0 && bw[b] > 0.0)
            {
                L->ff[L->nzf] = bf[b] / bw[b];
                L->zf[L->nzf] = bn[b] / bd[b];
                s1 += bd[b];
                s2 += bd[b] * (L->zf[L->nzf] - L->z) * (L->zf[L->nzf] - L->z);
                L->nzf++;
            }
        }
        L->zerr = (L->nzf > 1 && s1 > 0.0) ? sqrt(s2 / s1 / (L->nzf - 1)) : NAN;
    }
    free(cx);
    free(buf);
    free(nk_);
    return nk;
}

#endif /* WINDLAYERS_CORE_H */
