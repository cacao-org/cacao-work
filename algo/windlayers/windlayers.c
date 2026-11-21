// SPDX-FileCopyrightText: 2026 Olivier Guyon et al
//
// SPDX-License-Identifier: LGPL-3.0-or-later

/**
 * @file    windlayers.c
 * @brief   MILK_RUNNABLE compute unit: wind layers (speed, direction, distance) from a WFS
 *
 * Builds with `milk-cc windlayers.c` into `cacao-fpsexec-windlayers` (no CMake change).
 *
 * Inputs
 *   .wfs   WFS frames. Pyramid WFS (`.wfsmode 0`): the 4 pupil images are cut out and
 *          co-added into a pupil intensity map, which a wavefront changes only to second
 *          order; their differences give slope maps. `.wfsmode 1`: the stream already is a
 *          pupil intensity map.
 *   .pha   Optional wavefront OPD map (DM surface, pseudo-open-loop reconstruction...). When
 *          given, its laplacian is the "phase space" channel and layer distances are in
 *          metres. Without it the divergence of the pyramid slopes is used: layers are
 *          found in both spaces, but distances rest on the pyramid model and on the WFS
 *          seeing the full, unsaturated atmosphere (`.res.zvalid` = 0).
 * A 2-D `.wfs` stream is processed live, one frame per trigger. A 3-D image (telemetry cube)
 * is processed once, with `.pha` a cube of as many frames.
 *
 * Outputs (prefix `.outname`)
 *   <p>_vmapk, <p>_vmapi, <p>_vmapx  velocity maps (phase space, intensity, cross), row = vy,
 *                                    column = vx, keywords VMAX and DV [m/s]
 *   <p>_layers                       table [WLU_NCOL x WL_MAXLAYERS], one row per layer:
 *                                    vx vy speed dir snr pk_k pk_i pk_x frac_k frac_i z zerr
 *                                    coh z_axis z_diag valid
 *   <p>_imap, <p>_kmap               the two maps fed to the estimator (`.dbgmaps`)
 *   .res.*                           FPS outputs; `.report`: text table
 *
 * Velocities are the motion of the turbulence pattern across the pupil in WFS pixel
 * coordinates (x = column, y = row), direction = atan2(vy, vx). The method is in
 * `windlayers_core.h`.
 */

#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>

#include "milk_runnable.h"
#include "COREMOD_memory/COREMOD_memory.h"

#include "windlayers_core.h"

#define WLU_NCOL    16
#define WLU_NLAYOUT 3

/* ================================================================
 * 1.  PARAMETERS
 * ============================================================= */

static char    p_wfs[FUNCTION_PARAMETER_STRMAXLEN]     = "";
static char    p_pha[FUNCTION_PARAMETER_STRMAXLEN]     = "";
static char    p_outname[FUNCTION_PARAMETER_STRMAXLEN] = "wl";
static int32_t p_wfsmode                               = 0;
static double  p_frate                                 = 0.0;
static int32_t p_tbin                                  = 1;
static double  p_diam                                  = 8.0;
static double  p_diampix                               = 0.0;
static char    p_pupx[FUNCTION_PARAMETER_STRMAXLEN]    = "";
static char    p_pupy[FUNCTION_PARAMETER_STRMAXLEN]    = "";
static double  p_maskthr                               = 0.5;
static double  p_twarm                                 = 1.0;
static double  p_tmean                                 = 5.0;
static double  p_lagmax                                = 0.6;
static double  p_fmin                                  = 0.0;
static double  p_fmax                                  = 0.0;
static double  p_vmax                                  = 40.0;
static double  p_dv                                    = 0.5;
static double  p_nsigma                                = 8.0;
static double  p_minsep                                = 1.5;
static int32_t p_maxlayers                             = 6;
static double  p_tupdate                               = 10.0;
static double  p_tavg                                  = 0.0;
static double  p_modrad                                = 3.0;
static double  p_blur                                  = 0.6;
static double  p_corefrac                              = -1.0;
static double  p_halo                                  = 15.0;
static double  p_igain                                 = 1.0;
static int32_t p_pyrcoh                                = 1;
static int32_t p_fresnel                               = 1;
static double  p_lambda                                = 0.75;
static double  p_og                                    = 1.0;
static double  p_phaunit                               = 1e-6;
static int32_t p_phasign                               = 0;
static double  p_phapitch                              = 0.0;
static double  p_phacx                                 = 0.0;
static double  p_phacy                                 = 0.0;
static int32_t p_phaorient                             = 0;
static double  p_phalag                                = 0.0;
static double  p_phaifc                                = -1.0;
static int32_t p_dbgmaps                               = 0;
static char    p_report[FUNCTION_PARAMETER_STRMAXLEN]  = "";
static int32_t p_reset                                 = 0;
static int32_t p_nthread                               = 1;

static int64_t o_nframes  = 0;
static int64_t o_nblocks  = 0;
static double  o_tint     = 0.0;
static int64_t o_nlayers  = 0;
static int64_t o_ksign    = 0;
static int64_t o_zvalid   = 0;
static int64_t o_ngaps    = 0;
static int64_t o_npix     = 0;
static double  o_dx       = 0.0;
static double  o_corefrac = 1.0;
static double  o_fluxin   = 1.0;
static double  o_speed[WLU_NLAYOUT];
static double  o_dir[WLU_NLAYOUT];
static double  o_z[WLU_NLAYOUT];

#define WINDLAYERS_PARAMS(X)                                                                      \
    X(".wfs", p_wfs, FPTYPE_STREAMNAME, 1, FPFLAG_DEFAULT_INPUT | FPFLAG_TRIGGER_STREAM,          \
      "WFS stream: 2D live, or 3D telemetry cube")                                                \
    X(".pha", p_pha, FPTYPE_STRING, 1, FPFLAG_DEFAULT_INPUT,                                      \
      "Optional wavefront OPD map stream or cube (empty: pyramid slopes)")                        \
    X(".outname", p_outname, FPTYPE_STRING, 1, FPFLAG_DEFAULT_INPUT, "Output stream prefix")      \
    X(".wfsmode", &p_wfsmode, FPTYPE_INT32, 0, FPFLAG_DEFAULT_INPUT,                              \
      "0: pyramid WFS, 4 pupil images; 1: stream is a pupil intensity map")                       \
    X(".frate", &p_frate, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                \
      "WFS frame rate [Hz], physical time (required)")                                            \
    X(".tbin", &p_tbin, FPTYPE_INT32, 0, FPFLAG_DEFAULT_INPUT, "Frames averaged before analysis") \
    X(".diam", &p_diam, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT, "Pupil diameter [m]")            \
    X(".diampix", &p_diampix, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                            \
      "Pupil diameter [pixels of the intensity map] (0: from the mask)")                          \
    X(".pupx", p_pupx, FPTYPE_STRING, 0, FPFLAG_DEFAULT_INPUT,                                    \
      "Pyramid: x centres of the 4 pupil images \"a,b,c,d\" [pix] (empty: quadrants)")            \
    X(".pupy", p_pupy, FPTYPE_STRING, 0, FPFLAG_DEFAULT_INPUT,                                    \
      "Pyramid: y centres of the 4 pupil images, same order")                                     \
    X(".maskthr", &p_maskthr, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                            \
      "Pupil mask threshold [fraction of the bright level]")                                      \
    X(".twarm", &p_twarm, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                \
      "Live: time averaged to build the mean maps and the mask [s]")                              \
    X(".tmean", &p_tmean, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT | FPFLAG_WRITERUN,              \
      "Live: time constant of the running mean maps [s]")                                         \
    X(".lagmax", &p_lagmax, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT, "Largest time lag [s]")      \
    X(".fmin", &p_fmin, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                  \
      "Lowest spatial frequency [cycles/m] (0: 1.2 / diameter)")                                  \
    X(".fmax", &p_fmax, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                  \
      "Highest spatial frequency [cycles/m] (0: 0.85 Nyquist)")                                   \
    X(".vmax", &p_vmax, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT, "Largest speed searched [m/s]")  \
    X(".dv", &p_dv, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT, "Velocity map step [m/s]")           \
    X(".nsigma", &p_nsigma, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Detection threshold [robust sigma of a velocity map]")                                     \
    X(".minsep", &p_minsep, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Peaks closer than this are one layer [m/s]")                                               \
    X(".maxlayers", &p_maxlayers, FPTYPE_INT32, 0, FPFLAG_DEFAULT_INPUT, "Most layers kept")      \
    X(".tupdate", &p_tupdate, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT | FPFLAG_WRITERUN,          \
      "Live: time between two analyses [s]")                                                      \
    X(".tavg", &p_tavg, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                  \
      "Forgetting time of the spectra [s] (0: cumulative)")                                       \
    X(".modrad", &p_modrad, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Pyramid modulation radius [lambda/D]")                                                     \
    X(".blur", &p_blur, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                  \
      "Pyramid: width of the PSF core on the tip [lambda/D]")                                     \
    X(".corefrac", &p_corefrac, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                          \
      "Pyramid: PSF core fraction (<0: auto from inter-pupil flux, 0..1: fixed)")                 \
    X(".halo", &p_halo, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                  \
      "Pyramid: width of the PSF halo on the tip [lambda/D]")                                     \
    X(".igain", &p_igain, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                \
      "Intensity response of the WFS relative to the model (calibration)")                        \
    X(".pyrcoh", &p_pyrcoh, FPTYPE_ONOFF, 0, FPFLAG_DEFAULT_INPUT,                                \
      "Pyramid: coherent 2D Fourier-optics T_I(f) model from pupil mask (OFF: analytic)")         \
    X(".fresnel", &p_fresnel, FPTYPE_ONOFF, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Refine layer distances with pole-free Fresnel/Rytov model at .lambda")                     \
    X(".lambda", &p_lambda, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                              \
      "WFS wavelength [um] (Fresnel refinement, and slopes to OPD without .pha)")                 \
    X(".og", &p_og, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                      \
      "Extra optical gain of the slopes (without .pha)")                                          \
    X(".phaunit", &p_phaunit, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                            \
      "Metres of OPD per unit of .pha (1e-6: microns)")                                           \
    X(".phasign", &p_phasign, FPTYPE_INT32, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Sign of .pha against the atmosphere: 1, -1 (DM), 0: find it")                              \
    X(".phapitch", &p_phapitch, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                          \
      "Pitch of .pha [m/pixel] (0: same field as the intensity map)")                             \
    X(".phacx", &p_phacx, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                \
      "Pupil centre offset in .pha, x [pixels of .pha]")                                          \
    X(".phacy", &p_phacy, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                                \
      "Pupil centre offset in .pha, y [pixels of .pha]")                                          \
    X(".phaorient", &p_phaorient, FPTYPE_INT32, 0, FPFLAG_DEFAULT_INPUT,                          \
      "Orientation of .pha: +1 flip x, +2 flip y, +4 transpose")                                  \
    X(".phalag", &p_phalag, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Delay of .pha behind the WFS intensity [WFS frames]")                                      \
    X(".phaifc", &p_phaifc, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_INPUT,                              \
      ".pha is: <0 the wavefront, 0 a bilinear surface, 0..1 DM commands (coupling)")             \
    X(".dbgmaps", &p_dbgmaps, FPTYPE_ONOFF, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Post the two analysed maps as streams")                                                    \
    X(".report", p_report, FPTYPE_STRING, 0, FPFLAG_DEFAULT_INPUT, "Text report file (optional)") \
    X(".reset", &p_reset, FPTYPE_ONOFF, 0, FPFLAG_DEFAULT_INPUT | FPFLAG_WRITERUN,                \
      "Live: set ON to forget what was accumulated")                                              \
    X(".nthread", &p_nthread, FPTYPE_INT32, 0, FPFLAG_DEFAULT_INPUT,                              \
      "Live: threads of the low-priority analysis worker (cube: all cores)")                      \
    X(".res.nframes", &o_nframes, FPTYPE_INT64, 0, FPFLAG_DEFAULT_OUTPUT, "Frames analysed")      \
    X(".res.nblocks", &o_nblocks, FPTYPE_INT64, 0, FPFLAG_DEFAULT_OUTPUT, "Blocks accumulated")   \
    X(".res.tint", &o_tint, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Integration time [s]")     \
    X(".res.nlayers", &o_nlayers, FPTYPE_INT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layers found")         \
    X(".res.ksign", &o_ksign, FPTYPE_INT64, 0, FPFLAG_DEFAULT_OUTPUT, "Sign applied to .pha")     \
    X(".res.zvalid", &o_zvalid, FPTYPE_INT64, 0, FPFLAG_DEFAULT_OUTPUT,                           \
      "1: distances from an OPD stream, 0: from the slopes model")                                \
    X(".res.ngaps", &o_ngaps, FPTYPE_INT64, 0, FPFLAG_DEFAULT_OUTPUT, "Live: frame gaps seen")    \
    X(".res.npix", &o_npix, FPTYPE_INT64, 0, FPFLAG_DEFAULT_OUTPUT, "Pixels in the pupil mask")   \
    X(".res.dx", &o_dx, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Pixel pitch [m]")              \
    X(".res.corefrac", &o_corefrac, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT,                     \
      "Pyramid PSF core fraction used (auto or manual)")                                          \
    X(".res.fluxin", &o_fluxin, FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT,                         \
      "Fraction of WFS camera flux inside the 4 geometric pupils")                                \
    X(".res.l0speed", &o_speed[0], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 0 [m/s]")     \
    X(".res.l0dir", &o_dir[0], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 0 [deg]")         \
    X(".res.l0z", &o_z[0], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 0 distance [m]")      \
    X(".res.l1speed", &o_speed[1], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 1 [m/s]")     \
    X(".res.l1dir", &o_dir[1], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 1 [deg]")         \
    X(".res.l1z", &o_z[1], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 1 distance [m]")      \
    X(".res.l2speed", &o_speed[2], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 2 [m/s]")     \
    X(".res.l2dir", &o_dir[2], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 2 [deg]")         \
    X(".res.l2z", &o_z[2], FPTYPE_FLOAT64, 0, FPFLAG_DEFAULT_OUTPUT, "Layer 2 distance [m]")

MILK_PARAMS_DEFINE(windlayers, WINDLAYERS_PARAMS);

/* ================================================================
 * 2.  RUN-TIME STATE
 * ============================================================= */

/** @brief Everything the unit holds between frames. */
typedef struct
{
    int        fw, fh;       /**< WFS frame size */
    int        n;            /**< Map size (n x n) */
    int        sx0[4];       /**< x origin of the 4 pupil cut-outs (integer fast path) */
    int        sy0[4];       /**< y origin */
    double     fx0[4];       /**< Fractional x origin (when subpix == 1) */
    double     fy0[4];       /**< Fractional y origin */
    int        subpix;       /**< 1: bilinear sub-pixel cut-out extraction */
    int        shx[4];       /**< 1: cut-out is on the high-x side */
    int        shy[4];       /**< 1: cut-out is on the high-y side */
    int        kmode;        /**< 0: slopes, 1: OPD map */
    int        pnx, pny;     /**< OPD map size */
    int       *rptr;         /**< CSR row starts of the OPD resampling [n * n + 1] */
    int       *ridx;
    float     *rwgt;
    float     *rsum;         /**< Weight sum per output pixel */
    float     *fwfs;         /**< WFS frame as float */
    float     *fpha;         /**< OPD frame as float */
    double    *pmean;        /**< Mean OPD frame on its own grid (before the mask is known) */
    long       npmean;
    int        nacc;         /**< Frames in the current time bin */
    double     acc_tot;      /**< Bin sum of total WFS camera flux */
    double     mean_tot;     /**< Mean total WFS camera flux */
    double    *acc_i;        /**< Bin sums: intensity; a, b: slopes x, y or OPD */
    double    *acc_a;
    double    *acc_b;
    long       nmean;
    double    *mean_i;
    double    *mean_a;
    double    *mean_b;
    float     *mask_i;
    float     *mask_k;
    float     *imap;
    float     *kmap;
    float     *work;
    double     dx;
    double     dtbin;
    wl_core_t *core;
    long       blocks_at_analysis;
    long       nblkdrop;     /**< Live: blocks dropped because the worker was still busy */
    /* live mode: block transforms and analyses run in a worker thread, so that the frame
     * loop never waits on them */
    pthread_t       th;
    pthread_mutex_t mx;
    pthread_cond_t  cv;
    int             th_on;   /**< Worker thread exists */
    int             th_job;  /**< 1: a block copy waits for the worker */
    int             th_busy; /**< Worker is processing */
    int             th_ana;  /**< Analyse after this block */
    int             th_quit;
    IMGID      o_vk, o_vi, o_vx, o_lay, o_im, o_km;
} wlu_t;

/* ================================================================
 * 3.  HELPERS
 * ============================================================= */

/** @brief Copy slice @k of an image (any numeric type) into a float buffer. */
static int wlu_to_float(const IMAGE *im, long k, float *restrict dst)
{
    const size_t np  = (size_t) im->md->size[0] * im->md->size[1];
    const size_t off = (size_t) k * np;

    switch (im->md->datatype)
    {
    case _DATATYPE_FLOAT:
        memcpy(dst, im->array.F + off, sizeof(float) * np);
        break;
    case _DATATYPE_DOUBLE:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.D[off + i];
        }
        break;
    case _DATATYPE_UINT16:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.UI16[off + i];
        }
        break;
    case _DATATYPE_INT16:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.SI16[off + i];
        }
        break;
    case _DATATYPE_UINT8:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.UI8[off + i];
        }
        break;
    case _DATATYPE_INT8:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.SI8[off + i];
        }
        break;
    case _DATATYPE_UINT32:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.UI32[off + i];
        }
        break;
    case _DATATYPE_INT32:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.SI32[off + i];
        }
        break;
    case _DATATYPE_UINT64:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.UI64[off + i];
        }
        break;
    case _DATATYPE_INT64:
        for (size_t i = 0; i < np; i++)
        {
            dst[i] = (float) im->array.SI64[off + i];
        }
        break;
    default:
        return -1;
    }
    return 0;
}

static int wlu_cmp_float(const void *a, const void *b)
{
    float fa = *(const float *) a;
    float fb = *(const float *) b;
    return (fa > fb) - (fa < fb);
}

/** @brief 1-D Catmull-Rom cubic interpolation weights for fractional offset t in [0, 1]. */
static inline void wlu_catmull_w(double t, double w[4])
{
    double t2 = t * t;
    double t3 = t2 * t;
    w[0]      = -0.5 * t + t2 - 0.5 * t3;
    w[1]      = 1.0 - 2.5 * t2 + 1.5 * t3;
    w[2]      = 0.5 * t + 2.0 * t2 - 1.5 * t3;
    w[3]      = -0.5 * t2 + 0.5 * t3;
}

/** @brief Bicubic (Catmull-Rom) sample of a row-major (ny, nx) float image, clamped at edges. */
static inline double wlu_bicubic_f(const float *img, int nx, int ny, double x, double y)
{
    if (!(x >= 0.0) || !(y >= 0.0) || x > (double) (nx - 1) || y > (double) (ny - 1))
    {
        return 0.0;
    }
    int    ix = (int) floor(x);
    int    iy = (int) floor(y);
    double wx[4], wy[4];
    wlu_catmull_w(x - ix, wx);
    wlu_catmull_w(y - iy, wy);
    double acc = 0.0;
    for (int dy = -1; dy <= 2; dy++)
    {
        int py = iy + dy;
        py     = (py < 0) ? 0 : ((py >= ny) ? ny - 1 : py);
        const float *row = img + (size_t) py * nx;
        double       rx  = 0.0;
        for (int dx = -1; dx <= 2; dx++)
        {
            int px = ix + dx;
            px     = (px < 0) ? 0 : ((px >= nx) ? nx - 1 : px);
            rx += wx[dx + 1] * (double) row[px];
        }
        acc += wy[dy + 1] * rx;
    }
    return acc;
}

/** @brief Post a stream the unit wrote. */
static void wlu_post(PROCESSINFO *pinfo, IMGID *out, IMAGE *in)
{
    if (out->ID == -1)
    {
        return;
    }
    if (pinfo != NULL)
    {
        processinfo_update_output_stream(pinfo, out->im, in);
    }
    else
    {
        ImageStreamIO_UpdateIm(out->im);
    }
}

/** @brief Set up the pupil cut-outs of the WFS frame. Return 0, or -1 on bad geometry. */
static int wlu_setup_geometry(wlu_t *u)
{
    if (p_wfsmode != 0)
    {
        if (u->fw != u->fh)
        {
            printf("[windlayers] ERROR: intensity map must be square (%d x %d)\n", u->fw, u->fh);
            return -1;
        }
        u->n = u->fw;
        return 0;
    }
    double cx[4], cy[4];
    int    n = u->fw / 2;
    if (p_pupx[0] != '\0' && p_pupy[0] != '\0')
    {
        if (sscanf(p_pupx, "%lf,%lf,%lf,%lf", &cx[0], &cx[1], &cx[2], &cx[3]) != 4 ||
            sscanf(p_pupy, "%lf,%lf,%lf,%lf", &cy[0], &cy[1], &cy[2], &cy[3]) != 4)
        {
            printf("[windlayers] ERROR: .pupx / .pupy need 4 comma-separated values\n");
            return -1;
        }
        /* largest square cut-out that stays in the frame and off the neighbouring images:
         * the 4 images sit on a 2 x 2 grid around their common centre (mx, my) */
        double mx = 0.25 * (cx[0] + cx[1] + cx[2] + cx[3]);
        double my = 0.25 * (cy[0] + cy[1] + cy[2] + cy[3]);
        for (int q = 0; q < 4; q++)
        {
            double room = fmin(fmin(cx[q] + 0.5, u->fw - 0.5 - cx[q]),
                               fmin(cy[q] + 0.5, u->fh - 0.5 - cy[q]));
            room        = fmin(room, fmin(fabs(cx[q] - mx), fabs(cy[q] - my)));
            int m       = (int) floor(2.0 * room);
            if (m < n)
            {
                n = m;
            }
            u->shx[q] = (cx[q] > mx);
            u->shy[q] = (cy[q] > my);
        }
        u->subpix = 0;
        for (int q = 0; q < 4; q++)
        {
            u->fx0[q] = cx[q] - 0.5 * (n - 1);
            u->fy0[q] = cy[q] - 0.5 * (n - 1);
            u->sx0[q] = (int) lround(u->fx0[q]);
            u->sy0[q] = (int) lround(u->fy0[q]);
            if (fabs(u->fx0[q] - u->sx0[q]) > 1e-3 || fabs(u->fy0[q] - u->sy0[q]) > 1e-3)
            {
                u->subpix = 1;
            }
        }
    }
    else
    {
        if ((u->fw & 1) || u->fw != u->fh)
        {
            printf("[windlayers] ERROR: quadrant split needs an even square frame (%d x %d)\n",
                   u->fw, u->fh);
            return -1;
        }
        u->subpix = 0;
        for (int q = 0; q < 4; q++)
        {
            u->shx[q] = q & 1;
            u->shy[q] = (q >> 1) & 1;
            u->sx0[q] = u->shx[q] * n;
            u->sy0[q] = u->shy[q] * n;
            u->fx0[q] = (double) u->sx0[q];
            u->fy0[q] = (double) u->sy0[q];
        }
    }
    for (int q = 0; q < 4; q++)
    {
        int xlo = u->subpix ? (int) floor(u->fx0[q]) : u->sx0[q];
        int ylo = u->subpix ? (int) floor(u->fy0[q]) : u->sy0[q];
        int xhi = u->subpix ? ((int) ceil(u->fx0[q]) + n) : (u->sx0[q] + n);
        int yhi = u->subpix ? ((int) ceil(u->fy0[q]) + n) : (u->sy0[q] + n);
        if (n < 8 || xlo < 0 || ylo < 0 || xhi > u->fw || yhi > u->fh)
        {
            printf("[windlayers] ERROR: pupil cut-out %d (%d px at %.1f,%.1f) leaves the frame\n",
                   q, n, u->fx0[q], u->fy0[q]);
            return -1;
        }
    }
    u->n = n;
    return 0;
}

/**
 * wlu_setup_resample() - Sparse operator taking the OPD map onto the n x n pupil grid
 *
 * Each pupil pixel averages bilinear samples of the OPD map over its own area, so that the OPD
 * gets the same pixel integration as the intensity. Pixels outside the OPD map get weight 0.
 */
static int wlu_setup_resample(wlu_t *u, double dx)
{
    const int n     = u->n;
    double    pitch = (p_phapitch > 0.0) ? p_phapitch : (n * dx / u->pnx);
    /* finer OPD map: area average of its pixels (nearest sample on a dense sub-grid);
     * coarser: bilinear interpolation, averaged over the pupil pixel */
    const int fine  = (pitch < 0.75 * dx);
    int       ss    = fine ? 2 * (int) ceil(dx / pitch) : 3;
    ss              = (ss < 3) ? 3 : ((ss > 16) ? 16 : ss);
    const int maxe  = ss * ss * 4;
    size_t    cap   = (size_t) n * n * maxe;
    int      *tidx  = (int *) malloc(sizeof(int) * (size_t) maxe);
    double   *twgt  = (double *) malloc(sizeof(double) * (size_t) maxe);

    u->rptr = (int *) malloc(sizeof(int) * ((size_t) n * n + 1));
    u->ridx = (int *) malloc(sizeof(int) * cap);
    u->rwgt = (float *) malloc(sizeof(float) * cap);
    u->rsum = (float *) calloc((size_t) n * n, sizeof(float));
    if (!tidx || !twgt || !u->rptr || !u->ridx || !u->rwgt || !u->rsum)
    {
        free(tidx);
        free(twgt);
        return -1;
    }
    int ne = 0;
    for (int iy = 0; iy < n; iy++)
    {
        for (int ix = 0; ix < n; ix++)
        {
            int nt = 0;
            u->rptr[iy * n + ix] = ne;
            for (int b = 0; b < ss; b++)
            {
                for (int a = 0; a < ss; a++)
                {
                    /* position on the pupil [m], centred */
                    double px = (ix - 0.5 * (n - 1) + (a + 0.5) / ss - 0.5) * dx;
                    double py = (iy - 0.5 * (n - 1) + (b + 0.5) / ss - 0.5) * dx;
                    if (p_phaorient & 4)
                    {
                        double t = px;
                        px       = py;
                        py       = t;
                    }
                    if (p_phaorient & 1)
                    {
                        px = -px;
                    }
                    if (p_phaorient & 2)
                    {
                        py = -py;
                    }
                    double ux = px / pitch + 0.5 * (u->pnx - 1) + p_phacx;
                    double uy = py / pitch + 0.5 * (u->pny - 1) + p_phacy;
                    if (ux < 0.0 || uy < 0.0 || ux > u->pnx - 1 || uy > u->pny - 1)
                    {
                        continue;
                    }
                    int x0 = (int) ux;
                    int y0 = (int) uy;
                    x0     = (x0 > u->pnx - 2) ? u->pnx - 2 : x0;
                    y0     = (y0 > u->pny - 2) ? u->pny - 2 : y0;
                    if (x0 < 0 || y0 < 0)
                    {
                        continue;
                    }
                    double fx   = ux - x0;
                    double fy   = uy - y0;
                    if (fine)
                    {
                        fx = (fx < 0.5) ? 0.0 : 1.0;
                        fy = (fy < 0.5) ? 0.0 : 1.0;
                    }
                    double w[4] = { (1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy };
                    int    id[4] = { y0 * u->pnx + x0, y0 * u->pnx + x0 + 1,
                                     (y0 + 1) * u->pnx + x0, (y0 + 1) * u->pnx + x0 + 1 };
                    for (int e = 0; e < 4; e++)
                    {
                        int found = -1;
                        for (int t = 0; t < nt; t++)
                        {
                            if (tidx[t] == id[e])
                            {
                                found = t;
                                break;
                            }
                        }
                        if (found < 0)
                        {
                            found       = nt++;
                            tidx[found] = id[e];
                            twgt[found] = 0.0;
                        }
                        twgt[found] += w[e] / (ss * ss);
                    }
                }
            }
            double sum = 0.0;
            for (int t = 0; t < nt; t++)
            {
                u->ridx[ne] = tidx[t];
                u->rwgt[ne] = (float) twgt[t];
                sum += twgt[t];
                ne++;
            }
            u->rsum[iy * n + ix] = (float) sum;
        }
    }
    u->rptr[n * n] = ne;
    free(tidx);
    free(twgt);
    return 0;
}

/** @brief Add one WFS frame (and OPD frame) to the current time bin. Return 1 when full. */
static int wlu_ingest(wlu_t *u)
{
    const int    n  = u->n;
    const size_t np = (size_t) n * n;
    const float *f  = u->fwfs;

    if (u->nacc == 0)
    {
        u->acc_tot = 0.0;
        memset(u->acc_i, 0, sizeof(double) * np);
        memset(u->acc_a, 0, sizeof(double) * np);
        memset(u->acc_b, 0, sizeof(double) * np);
    }
    const size_t nfw = (size_t) u->fw * u->fh;
    double       ftot = 0.0;
    for (size_t i = 0; i < nfw; i++)
    {
        ftot += f[i];
    }
    u->acc_tot += ftot;
    if (p_wfsmode != 0)
    {
        for (size_t i = 0; i < np; i++)
        {
            u->acc_i[i] += f[i];
        }
    }
    else
    {
        for (int y = 0; y < n; y++)
        {
            for (int x = 0; x < n; x++)
            {
                double tot = 0.0, hx = 0.0, hy = 0.0;
                for (int q = 0; q < 4; q++)
                {
                    double v = u->subpix
                                   ? wlu_bicubic_f(f, u->fw, u->fh, u->fx0[q] + x, u->fy0[q] + y)
                                   : (double) f[(size_t) (u->sy0[q] + y) * u->fw + u->sx0[q] + x];
                    tot += v;
                    hx  += u->shx[q] ? v : -v;
                    hy  += u->shy[q] ? v : -v;
                }
                size_t i = (size_t) y * n + x;
                u->acc_i[i] += tot;
                if (u->kmode == 0 && tot > 0.0)
                {
                    u->acc_a[i] += hx / tot;
                    u->acc_b[i] += hy / tot;
                }
            }
        }
    }
    if (u->kmode == 1 && u->rptr != NULL)
    {
        for (size_t i = 0; i < np; i++)
        {
            double s = 0.0;
            for (int e = u->rptr[i]; e < u->rptr[i + 1]; e++)
            {
                s += (double) u->rwgt[e] * u->fpha[u->ridx[e]];
            }
            u->acc_a[i] += s;
        }
    }
    else if (u->kmode == 1)
    {
        /* mask and pixel pitch not known yet: average the OPD on its own grid */
        const size_t npp = (size_t) u->pnx * u->pny;
        for (size_t i = 0; i < npp; i++)
        {
            u->pmean[i] += u->fpha[i];
        }
        u->npmean++;
    }
    u->nacc++;
    if (u->nacc < p_tbin)
    {
        return 0;
    }
    double inv = 1.0 / u->nacc;
    u->acc_tot *= inv;
    for (size_t i = 0; i < np; i++)
    {
        u->acc_i[i] *= inv;
        u->acc_a[i] *= inv;
        u->acc_b[i] *= inv;
    }
    u->nacc = 0;
    return 1;
}

/** @brief Add the current bin to the plain averages (warm-up, or first pass over a cube). */
static void wlu_mean_add(wlu_t *u)
{
    const size_t np = (size_t) u->n * u->n;
    u->mean_tot += u->acc_tot;
    for (size_t i = 0; i < np; i++)
    {
        u->mean_i[i] += u->acc_i[i];
        u->mean_a[i] += u->acc_a[i];
        u->mean_b[i] += u->acc_b[i];
    }
    u->nmean++;
}

/** @brief Turn the sums of wlu_mean_add() into averages. */
static void wlu_mean_finish(wlu_t *u)
{
    const size_t np = (size_t) u->n * u->n;
    if (u->nmean < 1)
    {
        return;
    }
    u->mean_tot /= u->nmean;
    for (size_t i = 0; i < np; i++)
    {
        u->mean_i[i] /= u->nmean;
        u->mean_a[i] /= u->nmean;
        u->mean_b[i] /= u->nmean;
    }
}

/** @brief Pupil mask from the mean intensity, K mask, then the estimator itself. */
static int wlu_make_core(wlu_t *u)
{
    const int    n   = u->n;
    const size_t np  = (size_t) n * n;
    float       *tmp = (float *) malloc(sizeof(float) * np);

    if (tmp == NULL)
    {
        return -1;
    }
    for (size_t i = 0; i < np; i++)
    {
        tmp[i] = (float) u->mean_i[i];
    }
    qsort(tmp, np, sizeof(float), wlu_cmp_float);
    double ref = tmp[(size_t) (0.9 * (np - 1))];
    free(tmp);
    if (!(ref > 0.0))
    {
        printf("[windlayers] ERROR: no light in the intensity map\n");
        return -1;
    }
    int npix = 0, xlo = n, xhi = -1, ylo = n, yhi = -1;
    for (int y = 0; y < n; y++)
    {
        for (int x = 0; x < n; x++)
        {
            int in = (u->mean_i[(size_t) y * n + x] > p_maskthr * ref);
            u->mask_i[(size_t) y * n + x] = in ? 1.0f : 0.0f;
            if (in)
            {
                npix++;
                xlo = (x < xlo) ? x : xlo;
                xhi = (x > xhi) ? x : xhi;
                ylo = (y < ylo) ? y : ylo;
                yhi = (y > yhi) ? y : yhi;
            }
        }
    }
    if (npix < 32)
    {
        printf("[windlayers] ERROR: pupil mask has only %d pixels\n", npix);
        return -1;
    }
    double dpix = (p_diampix > 0.0) ? p_diampix : fmax(xhi - xlo + 1, yhi - ylo + 1);
    u->dx       = p_diam / dpix;
    o_dx        = u->dx;
    o_npix      = npix;

    if (u->kmode == 1)
    {
        /* the OPD resampling needs the pixel pitch: build it now, and take the mean OPD map
         * (averaged so far on its own grid) through it */
        if (wlu_setup_resample(u, u->dx) != 0)
        {
            return -1;
        }
        for (size_t i = 0; i < np; i++)
        {
            double s = 0.0;
            for (int e = u->rptr[i]; e < u->rptr[i + 1]; e++)
            {
                s += (double) u->rwgt[e] * u->pmean[u->ridx[e]];
            }
            u->mean_a[i] = (u->npmean > 0) ? s / u->npmean : 0.0;
            u->mean_b[i] = 0.0;
        }
    }
    /* K needs the pixel and its 4 neighbours (and, for an OPD map, full coverage by it) */
    for (int y = 0; y < n; y++)
    {
        for (int x = 0; x < n; x++)
        {
            size_t i  = (size_t) y * n + x;
            int    ok = (x > 0 && y > 0 && x < n - 1 && y < n - 1);
            if (ok)
            {
                ok = (u->mask_i[i] > 0.0f && u->mask_i[i - 1] > 0.0f && u->mask_i[i + 1] > 0.0f &&
                      u->mask_i[i - n] > 0.0f && u->mask_i[i + n] > 0.0f);
            }
            if (ok && u->kmode == 1)
            {
                ok = (u->rsum[i] > 0.999f && u->rsum[i - 1] > 0.999f && u->rsum[i + 1] > 0.999f &&
                      u->rsum[i - n] > 0.999f && u->rsum[i + n] > 0.999f);
            }
            u->mask_k[i] = ok ? 1.0f : 0.0f;
        }
    }

    /* fraction of camera flux inside the geometric pupil disk (r <= dpix/2 prevents bright
     * diffraction ringing on a flat WF from inflating flux_in via extra outer-rim pixels) */
    double cxm = 0.0, cym = 0.0, nm_f = 0.0;
    for (int y = 0; y < n; y++)
    {
        for (int x = 0; x < n; x++)
        {
            if (u->mask_i[(size_t) y * n + x] > 0.0f)
            {
                cxm += x;
                cym += y;
                nm_f += 1.0;
            }
        }
    }
    cxm /= (nm_f > 0.0) ? nm_f : 1.0;
    cym /= (nm_f > 0.0) ? nm_f : 1.0;
    double rmax2   = 0.25 * dpix * dpix;
    double in_flux = 0.0;
    for (int y = 0; y < n; y++)
    {
        for (int x = 0; x < n; x++)
        {
            size_t i  = (size_t) y * n + x;
            double r2 = (x - cxm) * (x - cxm) + (y - cym) * (y - cym);
            if (u->mask_i[i] > 0.0f && r2 <= rmax2)
            {
                in_flux += u->mean_i[i];
            }
        }
    }
    double flux_in = (u->mean_tot > 0.0) ? (in_flux / u->mean_tot) : 0.0;

    wl_cfg_t cfg  = { 0 };
    cfg.n         = n;
    cfg.dx        = u->dx;
    cfg.dt        = u->dtbin;
    cfg.diam      = p_diam;
    cfg.fmin      = (p_fmin > 0.0) ? p_fmin : (1.2 / p_diam);
    cfg.fmax      = (p_fmax > 0.0) ? p_fmax : (0.85 * 0.5 / u->dx);
    cfg.fmaxk     = cfg.fmax;
    cfg.pad       = 2;
    cfg.lagmax_s  = p_lagmax;
    cfg.vmax      = p_vmax;
    cfg.dv        = p_dv;
    cfg.nsigma    = p_nsigma;
    cfg.minsep    = p_minsep;
    cfg.minfrac   = 0.05;
    cfg.maxlayers = p_maxlayers;
    cfg.tavg      = p_tavg;
    cfg.kmode     = u->kmode;
    cfg.klag      = (u->kmode == 1) ? (p_phalag / p_tbin) : 0.0;
    cfg.ksign     = (u->kmode == 1) ? p_phasign : 1;
    cfg.og        = p_og;
    cfg.phaifc    = p_phaifc;
    cfg.pyr       = (p_wfsmode == 0);
    cfg.modrad    = p_modrad;
    cfg.blur      = p_blur;
    cfg.corefrac  = p_corefrac;
    cfg.halo      = p_halo;
    cfg.igain     = (p_igain > 0.0) ? p_igain : 1.0;
    cfg.pyr_coh   = (p_pyrcoh != 0);
    cfg.flux_in   = flux_in;
    cfg.lambda_m  = (p_lambda > 0.0) ? (p_lambda * 1e-6) : 0.0;
    cfg.fresnel   = (p_fresnel != 0);
    if (u->kmode == 1)
    {
        cfg.phapitch = (p_phapitch > 0.0) ? p_phapitch : (n * u->dx / u->pnx);
        if (cfg.phapitch > 1.001 * u->dx)
        {
            /* a coarser OPD map carries nothing beyond its own Nyquist frequency */
            double fk = 0.8 * 0.5 / cfg.phapitch;
            cfg.fmaxk = (fk < cfg.fmax) ? fk : cfg.fmax;
        }
    }
    u->core = wl_create(&cfg, u->mask_k, u->mask_i);
    if (u->core == NULL)
    {
        printf("[windlayers] ERROR: cannot set up the estimator (band %.3f-%.3f cycles/m,"
               " dx %.4f m, dt %.4f s)\n",
               cfg.fmin, cfg.fmax, cfg.dx, cfg.dt);
        return -1;
    }
    o_corefrac = u->core->corefrac_used;
    o_fluxin   = flux_in;
    u->work = (float *) malloc(sizeof(float) * 2 * (size_t) u->core->nfx * n);
    if (u->work == NULL)
    {
        return -1;
    }
    printf("[windlayers] map %d x %d%s, dx = %.4f m, %d pupil pixels (%d for K), dt = %.2f ms\n", n,
           n, u->subpix ? " (subpix)" : "", u->dx, npix, (int) lround(u->core->t0_kk),
           1e3 * u->dtbin);
    printf("[windlayers] band %.3f-%.3f cycles/m (K: %.3f), %d modes, lags to %d frames,"
           " blocks of %d frames\n",
           cfg.fmin, cfg.fmax, u->core->cfg.fmaxk, u->core->nm, u->core->lmax, u->core->nt);
    if (cfg.pyr)
    {
        printf("[windlayers] pyr T_I: %s, flux_in=%.4f (model %.4f..%.4f) -> corefrac=%.2f%s,"
               " fresnel=%s\n",
               cfg.pyr_coh ? "coherent" : "analytic", flux_in, u->core->flux_flat,
               u->core->flux_halo, u->core->corefrac_used, (p_corefrac < 0.0) ? " (auto)" : "",
               cfg.fresnel ? "ON" : "OFF");
    }
    fflush(stdout);
    return 0;
}

/** @brief Build the K and I maps of the current bin and hand them to the estimator. */
static int wlu_push(wlu_t *u, int update_mean)
{
    const int    n  = u->n;
    const size_t np = (size_t) n * n;

    if (update_mean && p_tmean > 0.0)
    {
        double a = u->dtbin / p_tmean;
        a        = (a > 1.0) ? 1.0 : a;
        for (size_t i = 0; i < np; i++)
        {
            u->mean_i[i] += a * (u->acc_i[i] - u->mean_i[i]);
            u->mean_a[i] += a * (u->acc_a[i] - u->mean_a[i]);
            u->mean_b[i] += a * (u->acc_b[i] - u->mean_b[i]);
        }
    }
    double si = 0.0, ni = 0.0;
    for (size_t i = 0; i < np; i++)
    {
        float v = 0.0f;
        if (u->mask_i[i] > 0.0f && u->mean_i[i] > 0.0)
        {
            v  = (float) (u->acc_i[i] / u->mean_i[i] - 1.0);
            si += v;
            ni += 1.0;
        }
        u->imap[i] = v;
    }
    float mi = (ni > 0.0) ? (float) (si / ni) : 0.0f;
    for (size_t i = 0; i < np; i++)
    {
        if (u->mask_i[i] > 0.0f)
        {
            u->imap[i] -= mi;
        }
    }
    /* K: laplacian of the OPD [1/m], or divergence of the slopes times lambda / (2 pi) */
    const double ka = u->kmode ? (p_phaunit / (u->dx * u->dx))
                               : (p_lambda * 1e-6 / (2.0 * WL_PI) / (2.0 * u->dx));
    double       sk = 0.0, nk = 0.0;
    for (size_t i = 0; i < np; i++)
    {
        float v = 0.0f;
        if (u->mask_k[i] > 0.0f)
        {
            if (u->kmode)
            {
                v = (float) (ka * ((u->acc_a[i - 1] - u->mean_a[i - 1]) +
                                   (u->acc_a[i + 1] - u->mean_a[i + 1]) +
                                   (u->acc_a[i - n] - u->mean_a[i - n]) +
                                   (u->acc_a[i + n] - u->mean_a[i + n]) -
                                   4.0 * (u->acc_a[i] - u->mean_a[i])));
            }
            else
            {
                v = (float) (ka * ((u->acc_a[i + 1] - u->mean_a[i + 1]) -
                                   (u->acc_a[i - 1] - u->mean_a[i - 1]) +
                                   (u->acc_b[i + n] - u->mean_b[i + n]) -
                                   (u->acc_b[i - n] - u->mean_b[i - n])));
            }
            sk += v;
            nk += 1.0;
        }
        u->kmap[i] = v;
    }
    float mk = (nk > 0.0) ? (float) (sk / nk) : 0.0f;
    for (size_t i = 0; i < np; i++)
    {
        if (u->mask_k[i] > 0.0f)
        {
            u->kmap[i] -= mk;
        }
    }
    return wl_push(u->core, u->kmap, u->imap, u->work);
}

/** @brief Text table of the layers. */
static void wlu_report(const wlu_t *u, FILE *f)
{
    const wl_core_t *c = u->core;
    fprintf(f, "# windlayers: %ld frames, %.1f s, %d layers, K from %s, sign %+d\n",
            (long) c->nframes, c->tint_s, c->nlayers, u->kmode ? "OPD map" : "pyramid slopes",
            c->ksign_used);
    if (o_ngaps > 0 || u->nblkdrop > 0)
    {
        fprintf(f, "# live: %ld frame gaps, %ld blocks dropped\n", (long) o_ngaps, u->nblkdrop);
    }
    fprintf(f, "# dx %.4f m, dt %.4f s, band %.3f-%.3f cycles/m, corefrac %.2f, distance %s\n",
            u->dx, u->dtbin, c->cfg.fmin, c->cfg.fmax, c->corefrac_used,
            u->kmode ? "calibrated by the OPD stream" : "from the slopes model (indicative)");
    fprintf(f, "# %2s %7s %7s %7s %7s %7s %6s %6s %6s %6s %6s %9s %8s %6s %9s %9s\n", "l", "vx",
            "vy", "speed", "dir", "snr", "pk_k", "pk_i", "pk_x", "frac_k", "frac_i", "z[m]",
            "zerr", "coh", "z_axis", "z_diag");
    for (int l = 0; l < c->nlayers; l++)
    {
        const wl_layer_t *L = &c->layers[l];
        fprintf(f, "  %2d %7.2f %7.2f %7.2f %7.1f %7.1f %6.3f %6.3f %6.3f %6.3f %6.3f %9.0f"
                   " %8.0f %6.2f %9.0f %9.0f\n",
                l, L->vx, L->vy, L->speed, L->dir, L->snr, L->pk_k, L->pk_i, L->pk_x, L->frac_k,
                L->frac_i, L->z, L->zerr, L->coh, L->z_axis, L->z_diag);
    }
    if (c->nlayers > 0)
    {
        fprintf(f, "# diag (xarg[rad], zerr_f/zerr_blk[m]):");
        for (int l = 0; l < c->nlayers; l++)
        {
            const wl_layer_t *L = &c->layers[l];
            fprintf(f, " l%d=(%+.2f,%.0f/%.0f)", l, L->xarg, L->zerr_f, L->zerr_blk);
        }
        fprintf(f, "\n");
    }
    fflush(f);
}

/** @brief Run the analysis and publish maps, table, FPS outputs and report. */
static void wlu_analyze(wlu_t *u, PROCESSINFO *pinfo)
{
    wl_core_t *c  = u->core;
    int        nk = wl_analyze(c);
    if (nk < 0)
    {
        return;
    }
    const size_t nq = (size_t) c->nv * c->nv;
    IMGID       *vm[3] = { &u->o_vk, &u->o_vi, &u->o_vx };
    const float *sv[3] = { c->vmap_k, c->vmap_i, c->vmap_x };
    for (int k = 0; k < 3; k++)
    {
        if (vm[k]->ID == -1)
        {
            continue;
        }
        vm[k]->md->write = 1;
        memcpy(vm[k]->im->array.F, sv[k], sizeof(float) * nq);
        wlu_post(pinfo, vm[k], NULL);
    }
    if (u->o_lay.ID != -1)
    {
        float *t         = u->o_lay.im->array.F;
        u->o_lay.md->write = 1;
        memset(t, 0, sizeof(float) * WLU_NCOL * WL_MAXLAYERS);
        for (int l = 0; l < nk; l++)
        {
            const wl_layer_t *L = &c->layers[l];
            float            *r = t + (size_t) l * WLU_NCOL;
            r[0]  = (float) L->vx;
            r[1]  = (float) L->vy;
            r[2]  = (float) L->speed;
            r[3]  = (float) L->dir;
            r[4]  = (float) L->snr;
            r[5]  = (float) L->pk_k;
            r[6]  = (float) L->pk_i;
            r[7]  = (float) L->pk_x;
            r[8]  = (float) L->frac_k;
            r[9]  = (float) L->frac_i;
            r[10] = (float) L->z;
            r[11] = (float) L->zerr;
            r[12] = (float) L->coh;
            r[13] = (float) L->z_axis;
            r[14] = (float) L->z_diag;
            r[15] = 1.0f;
        }
        wlu_post(pinfo, &u->o_lay, NULL);
    }
    o_nlayers = nk;
    o_nblocks = c->nblk_total;
    o_tint    = c->tint_s;
    o_ksign   = c->ksign_used;
    o_zvalid  = u->kmode;
    for (int l = 0; l < WLU_NLAYOUT; l++)
    {
        o_speed[l] = (l < nk) ? c->layers[l].speed : 0.0;
        o_dir[l]   = (l < nk) ? c->layers[l].dir : 0.0;
        o_z[l]     = (l < nk && isfinite(c->layers[l].z)) ? c->layers[l].z : 0.0;
    }
    wlu_report(u, stdout);
    if (p_report[0] != '\0')
    {
        FILE *f = fopen(p_report, "w");
        if (f != NULL)
        {
            wlu_report(u, f);
            fclose(f);
        }
    }
    o_nblocks = c->nblk_total;
}

/* ---------------------------------------------------------------- worker thread (live) */

/** @brief Worker: transform each block copy, and analyse when asked. */
static void *wlu_worker(void *arg)
{
    wlu_t *u = (wlu_t *) arg;

    /* the worker must never take CPU from the loops it observes: few threads, low priority */
#ifdef _OPENMP
    omp_set_num_threads((p_nthread > 0) ? p_nthread : 1);
#endif
    if (setpriority(PRIO_PROCESS, (id_t) syscall(SYS_gettid), 10) != 0)
    {
        /* not fatal: the worker then runs at the priority of the unit */
    }

    pthread_mutex_lock(&u->mx);
    while (!u->th_quit)
    {
        if (!u->th_job)
        {
            pthread_cond_wait(&u->cv, &u->mx);
            continue;
        }
        int ana    = u->th_ana;
        u->th_job  = 0;
        u->th_busy = 1;
        pthread_mutex_unlock(&u->mx);

        wl_block_process(u->core);
        if (ana)
        {
            /* streams are posted without the processinfo of the frame loop */
            wlu_analyze(u, NULL);
        }

        pthread_mutex_lock(&u->mx);
        u->th_busy = 0;
        pthread_cond_broadcast(&u->cv);
    }
    pthread_mutex_unlock(&u->mx);
    return NULL;
}

static int wlu_worker_start(wlu_t *u)
{
    pthread_mutex_init(&u->mx, NULL);
    pthread_cond_init(&u->cv, NULL);
    u->th_job = u->th_busy = u->th_ana = u->th_quit = 0;
    if (pthread_create(&u->th, NULL, wlu_worker, u) != 0)
    {
        printf("[windlayers] ERROR: cannot start the worker thread\n");
        return -1;
    }
    u->th_on = 1;
    return 0;
}

/** @brief Wait until the worker has nothing left to do. */
static void wlu_worker_wait(wlu_t *u)
{
    if (!u->th_on)
    {
        return;
    }
    pthread_mutex_lock(&u->mx);
    while (u->th_job || u->th_busy)
    {
        pthread_cond_wait(&u->cv, &u->mx);
    }
    pthread_mutex_unlock(&u->mx);
}

/**
 * wlu_worker_submit() - Give the full block to the worker
 *
 * Return: 1 when the block was taken, 0 when it was dropped because the worker is still on the
 * previous one (the frame loop does not wait).
 */
static int wlu_worker_submit(wlu_t *u, int analyze)
{
    int taken = 0;

    pthread_mutex_lock(&u->mx);
    if (!u->th_job && !u->th_busy)
    {
        wl_block_take(u->core, 1);
        u->th_job = 1;
        u->th_ana = analyze;
        taken     = 1;
        pthread_cond_broadcast(&u->cv);
    }
    else
    {
        wl_block_take(u->core, 0);
        u->nblkdrop++;
    }
    pthread_mutex_unlock(&u->mx);
    return taken;
}

static void wlu_worker_stop(wlu_t *u)
{
    if (!u->th_on)
    {
        return;
    }
    pthread_mutex_lock(&u->mx);
    u->th_quit = 1;
    pthread_cond_broadcast(&u->cv);
    pthread_mutex_unlock(&u->mx);
    pthread_join(u->th, NULL);
    pthread_mutex_destroy(&u->mx);
    pthread_cond_destroy(&u->cv);
    u->th_on = 0;
}

static void wlu_free(wlu_t *u)
{
    free(u->rptr);
    free(u->ridx);
    free(u->rwgt);
    free(u->rsum);
    free(u->fwfs);
    free(u->fpha);
    free(u->pmean);
    free(u->acc_i);
    free(u->acc_a);
    free(u->acc_b);
    free(u->mean_i);
    free(u->mean_a);
    free(u->mean_b);
    free(u->mask_i);
    free(u->mask_k);
    free(u->imap);
    free(u->kmap);
    free(u->work);
    wl_destroy(u->core);
    imgid_free(&u->o_vk);
    imgid_free(&u->o_vi);
    imgid_free(&u->o_vx);
    imgid_free(&u->o_lay);
    imgid_free(&u->o_im);
    imgid_free(&u->o_km);
}

/** @brief Create the output streams once the estimator exists. */
static void wlu_make_outputs(wlu_t *u)
{
    char      name[STRINGMAXLEN_IMAGE_NAME];
    const int nv = u->core->nv;
    IMGID    *vm[3]  = { &u->o_vk, &u->o_vi, &u->o_vx };
    const char *sf[3] = { "vmapk", "vmapi", "vmapx" };

    for (int k = 0; k < 3; k++)
    {
        snprintf(name, sizeof(name), "%.40s_%s", p_outname, sf[k]);
        *vm[k] = stream_connect_create_2Df32(name, (uint32_t) nv, (uint32_t) nv);
        image_write_keyword_D(name, "VMAX", (nv / 2) * u->core->cfg.dv, "map half-width [m/s]");
        image_write_keyword_D(name, "DV", u->core->cfg.dv, "map step [m/s]");
    }
    snprintf(name, sizeof(name), "%.40s_layers", p_outname);
    u->o_lay = stream_connect_create_2Df32(name, WLU_NCOL, WL_MAXLAYERS);
    if (p_dbgmaps)
    {
        snprintf(name, sizeof(name), "%.40s_imap", p_outname);
        u->o_im = stream_connect_create_2Df32(name, (uint32_t) u->n, (uint32_t) u->n);
        snprintf(name, sizeof(name), "%.40s_kmap", p_outname);
        u->o_km = stream_connect_create_2Df32(name, (uint32_t) u->n, (uint32_t) u->n);
    }
}

/** @brief Post the two analysed maps (debug). */
static void wlu_post_maps(wlu_t *u, PROCESSINFO *pinfo)
{
    const size_t np = (size_t) u->n * u->n;
    if (u->o_im.ID != -1)
    {
        u->o_im.md->write = 1;
        memcpy(u->o_im.im->array.F, u->imap, sizeof(float) * np);
        wlu_post(pinfo, &u->o_im, NULL);
    }
    if (u->o_km.ID != -1)
    {
        u->o_km.md->write = 1;
        memcpy(u->o_km.im->array.F, u->kmap, sizeof(float) * np);
        wlu_post(pinfo, &u->o_km, NULL);
    }
}

/* ================================================================
 * 4.  COMPUTE
 * ============================================================= */

static errno_t windlayers_compute(const MILK_RUNNABLE *self)
{
    wlu_t u;
    memset(&u, 0, sizeof(u));
    u.o_vk.ID = u.o_vi.ID = u.o_vx.ID = u.o_lay.ID = u.o_im.ID = u.o_km.ID = -1;

    IMGID img_wfs = stream_connect(p_wfs);
    if (img_wfs.ID == -1)
    {
        printf("[windlayers] ERROR: WFS stream \"%s\" not found\n", p_wfs);
        return RETURN_FAILURE;
    }
    IMGID img_pha = { 0 };
    img_pha.ID    = -1;
    if (p_pha[0] != '\0')
    {
        img_pha = stream_connect(p_pha);
        if (img_pha.ID == -1)
        {
            printf("[windlayers] ERROR: OPD stream \"%s\" not found\n", p_pha);
            return RETURN_FAILURE;
        }
    }
    const int  iscube = (img_wfs.md->naxis == 3);
    const long nz     = iscube ? (long) img_wfs.md->size[2] : 0;

    u.fw    = (int) img_wfs.md->size[0];
    u.fh    = (int) img_wfs.md->size[1];
    u.kmode = (img_pha.ID != -1) ? 1 : 0;
    if (p_tbin < 1)
    {
        p_tbin = 1;
    }
    if (!(p_frate > 0.0))
    {
        printf("[windlayers] ERROR: set .frate, the WFS frame rate [Hz]\n");
        return RETURN_FAILURE;
    }
    if (u.kmode == 0 && p_wfsmode != 0)
    {
        printf("[windlayers] ERROR: an intensity map (.wfsmode 1) needs an OPD stream (.pha)\n");
        return RETURN_FAILURE;
    }
    if (iscube && u.kmode == 1 &&
        (img_pha.md->naxis != 3 || (long) img_pha.md->size[2] < nz))
    {
        printf("[windlayers] ERROR: .pha must be a cube of at least %ld frames\n", nz);
        return RETURN_FAILURE;
    }
    if (wlu_setup_geometry(&u) != 0)
    {
        return RETURN_FAILURE;
    }
    u.dtbin = p_tbin / p_frate;

    const size_t np = (size_t) u.n * u.n;
    u.fwfs   = (float *) malloc(sizeof(float) * (size_t) u.fw * u.fh);
    u.acc_i  = (double *) calloc(np, sizeof(double));
    u.acc_a  = (double *) calloc(np, sizeof(double));
    u.acc_b  = (double *) calloc(np, sizeof(double));
    u.mean_i = (double *) calloc(np, sizeof(double));
    u.mean_a = (double *) calloc(np, sizeof(double));
    u.mean_b = (double *) calloc(np, sizeof(double));
    u.mask_i = (float *) calloc(np, sizeof(float));
    u.mask_k = (float *) calloc(np, sizeof(float));
    u.imap   = (float *) calloc(np, sizeof(float));
    u.kmap   = (float *) calloc(np, sizeof(float));
    int ok   = (u.fwfs && u.acc_i && u.acc_a && u.acc_b && u.mean_i && u.mean_a && u.mean_b &&
                u.mask_i && u.mask_k && u.imap && u.kmap);
    if (ok && u.kmode == 1)
    {
        u.pnx  = (int) img_pha.md->size[0];
        u.pny  = (int) img_pha.md->size[1];
        u.fpha  = (float *) malloc(sizeof(float) * (size_t) u.pnx * u.pny);
        u.pmean = (double *) calloc((size_t) u.pnx * u.pny, sizeof(double));
        ok      = (u.fpha != NULL && u.pmean != NULL);
    }
    if (!ok)
    {
        wlu_free(&u);
        return RETURN_FAILURE;
    }
    o_nframes = 0;
    o_ngaps   = 0;
    o_nlayers = 0;

    errno_t ret      = RETURN_SUCCESS;
    long    nsub     = 0; /* blocks handed to the worker */
    long    nwarm    = (long) ceil(p_twarm / u.dtbin);
    long    lastcnt  = -1;
    int     warming  = 1;
    nwarm            = (nwarm < 8) ? 8 : nwarm;

    MILK_PROCINFO_INIT(self)
    MILK_PROCINFO_LOOPSTART(self)
    {
        if (iscube)
        {
            /* telemetry cube: first pass for the mean maps and the mask, second pass to
             * accumulate, then one analysis */
            for (int pass = 0; pass < 2 && ret == RETURN_SUCCESS; pass++)
            {
                u.nacc = 0;
                for (long k = 0; k < nz; k++)
                {
                    if (wlu_to_float(img_wfs.im, k, u.fwfs) != 0 ||
                        (u.kmode == 1 && wlu_to_float(img_pha.im, k, u.fpha) != 0))
                    {
                        printf("[windlayers] ERROR: unsupported image data type\n");
                        ret = RETURN_FAILURE;
                        break;
                    }
                    if (!wlu_ingest(&u))
                    {
                        continue;
                    }
                    if (pass == 0)
                    {
                        wlu_mean_add(&u);
                    }
                    else
                    {
                        if (wlu_push(&u, 0))
                        {
                            wl_block_take(u.core, 1);
                            wl_block_process(u.core);
                        }
                        o_nframes += p_tbin;
                    }
                }
                if (pass == 0 && ret == RETURN_SUCCESS)
                {
                    wlu_mean_finish(&u);
                    if (wlu_make_core(&u) != 0)
                    {
                        ret = RETURN_FAILURE;
                        break;
                    }
                    wlu_make_outputs(&u);
                }
            }
            if (ret == RETURN_SUCCESS)
            {
                wlu_analyze(&u, processinfo);
            }
            processloopOK = 0;
        }
        else
        {
            long cnt   = (long) img_wfs.md->cnt0;
            int  fresh = (cnt != lastcnt); /* 0: woken twice for one frame */
            if (fresh && lastcnt >= 0 && cnt != lastcnt + 1)
            {
                /* frames were missed: the time series is broken, start the bin and block again */
                o_ngaps++;
                u.nacc = 0;
                if (u.core != NULL)
                {
                    wl_reset_block(u.core);
                }
            }
            lastcnt = cnt;
            if (!fresh)
            {
                /* nothing new to analyse */
            }
            else if (wlu_to_float(img_wfs.im, 0, u.fwfs) != 0 ||
                     (u.kmode == 1 && wlu_to_float(img_pha.im, 0, u.fpha) != 0))
            {
                printf("[windlayers] ERROR: unsupported image data type\n");
                ret           = RETURN_FAILURE;
                processloopOK = 0;
            }
            else if (wlu_ingest(&u))
            {
                if (warming)
                {
                    wlu_mean_add(&u);
                    if (u.nmean >= nwarm)
                    {
                        wlu_mean_finish(&u);
                        if (wlu_make_core(&u) != 0)
                        {
                            ret           = RETURN_FAILURE;
                            processloopOK = 0;
                        }
                        else
                        {
                            wlu_make_outputs(&u);
                            warming = 0;
                            if (wlu_worker_start(&u) != 0)
                            {
                                ret           = RETURN_FAILURE;
                                processloopOK = 0;
                            }
                        }
                    }
                }
                else
                {
                    if (p_reset)
                    {
                        wlu_worker_wait(&u);
                        wl_reset(u.core);
                        u.blocks_at_analysis = 0;
                        nsub                 = 0;
                        p_reset              = 0;
                    }
                    int full   = wlu_push(&u, 1);
                    o_nframes += p_tbin;
                    if (p_dbgmaps)
                    {
                        wlu_post_maps(&u, processinfo);
                    }
                    if (full)
                    {
                        /* hand the block to the worker; analyse every .tupdate seconds */
                        double hop = 0.5 * u.core->nt * u.dtbin;
                        int    ana = ((nsub + 1 - u.blocks_at_analysis) * hop >= p_tupdate);
                        if (wlu_worker_submit(&u, ana))
                        {
                            nsub++;
                            if (ana)
                            {
                                u.blocks_at_analysis = nsub;
                            }
                        }
                    }
                }
            }
        }
    }
    MILK_PROCINFO_END(self)

    wlu_worker_stop(&u);
    if (dcfpsptr != NULL)
    {
        fpsresync_modvar_to_fps(dcfpsptr, dcfpsbindings, dcfpsnbindings);
    }
    wlu_free(&u);
    imgid_free(&img_wfs);
    if (img_pha.ID != -1)
    {
        imgid_free(&img_pha);
    }
    return ret;
}

const MILK_RUNNABLE runnable_windlayers = {
    .kind = MILK_RUNNABLE_FPS,
    .app  = { .fps_name         = "windlayers",
              .cmdkey           = "windlayers",
              .description      = "estimate wind layers (speed, direction, distance) from a WFS",
              .description_long = "Finds frozen-flow turbulence layers in the pupil intensity map "
                                  "of a WFS (sum of the 4 pupil images of a pyramid WFS) and in "
                                  "its wavefront curvature, and derives each layer's distance "
                                  "from the intensity-curvature cross spectrum." },
    .srcfile = __FILE__,
    MILK_PARAMS_REF(windlayers),
    .compute = windlayers_compute,
};

EXPORT_FPSEXEC(cacao, "windlayers", runnable_windlayers);
