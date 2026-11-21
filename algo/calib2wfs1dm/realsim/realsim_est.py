#!/usr/bin/python3
"""Passive 2-WFS + 1-DM gain estimators on real AO3k + SCExAO simulator telemetry.

Input (one telemetry window written by run-tlm.sh):
    <run>/selfRM_calib_stg2.fits                    calibration self-response cube
    <run>/win_<label>/selfRM_onsky_stg2.fits        self-response cube taken after the window
    <run>/win_<label>/telemetry/<stream>_*.fits|txt modal streams with per-frame counters
    <run>/win_<label>/calib_2wfs1dm/                output of the shipped milk-mlt-calib2wfs1dm

Streams: A = aol1_modevalWFS (1 kHz), B = aol2_modevalWFS (2 kHz), D = aol2_modevalDM (2 kHz).

Reference: the response of WFS B mode i to a unit step of DM2 mode i with the loops running,
from the on-sky cube (lag 4 minus the mean of lags 0-2). Every estimate of Mdb[i, i] is compared
with it.

Alignment: A, B and the DM2 command are put on one timeline with one exposure. Nothing in it
assumes a frame-rate ratio or aligned clocks; it works from the time each exposure ends.
    D_eff[k] = w D[k-2] + (1-w) D[k-3]      DM2 command as it acts during WFS B frame k; w is the
                                            rise fraction of the self-response (lag 3 / lag 4)
    windows    runs of whole WFS B frames, so B and D_eff are plain means with no sub-frame
               model. Length (choose_windows): the shortest run of at least two WFS B frames
               and one WFS A frame whose edges fall on WFS A frame edges; if there is none short
               enough, the shortest run holding two frames of each sensor.
    A          mean of the WFS A frames a window overlaps, weighted by the overlap.
    first lag  2 when no WFS A frame is cut by a window edge, 3 otherwise (a cut frame puts
               its noise in two neighbouring windows).
With WFS A at 1 kHz, WFS B at 2 kHz and aligned clocks this is the original recipe (one WFS A
frame against its two WFS B frames), kept as align_fixed() and --fixed for comparison.

The exposure end times come from sim_frame_times(), the only simulator-specific part: frame
counters, the two frame periods and the configured WFS B clock offset (--b-offset-us). A real
system would pass hardware timestamps to align_frames() instead.

Estimators of g_i = Mdb[i, i]:
    tool W(z)      shipped tool (mdb_diag.fits)
    LS             least squares of B on (psi, D), psi = A Mab0
    LS diff        the same on first differences
    IV             2SLS of B on (psi, D), instruments psi at lags 1-8
    IV diff        2SLS on first differences, instruments differenced psi at lags 2-9
                   (lags 2-9 and 3-10 when WFS A frames are cut)
Mab0 is a ridge fit of (B - g_start D) on the 60 leading A modes; g_start is the shipped tool's
diagonal unless --start is given (a factor applied to the reference, to test that the estimate
does not remember its starting point).

Usage: realsim_est.py <run dir> <window label> [--b-offset-us s] [--nb n] [--anchor f]
                      [--lag0 l] [--linear] [--fixed] [--tsub t0:t1] [--start f] [--pair e]
"""
import argparse
import glob
import json
from pathlib import Path

import numpy as np
from astropy.io import fits

NA, NB = 60, 40
PERIOD_A_US, PERIOD_B_US = 1000.0, 500.0   # frame periods of WFS A and WFS B in this bench


def load_stream(tdir, name, nmodes):
    files = sorted(glob.glob(str(tdir / f"{name}_*.fits")))
    if not files:
        raise FileNotFoundError(f"{tdir}/{name}_*.fits")
    val = np.concatenate([fits.getdata(f).reshape(-1, fits.getdata(f).shape[-1])[:, :nmodes]
                          for f in files]).astype(np.float64)
    tim = np.concatenate([np.atleast_2d(np.loadtxt(f[:-5] + ".txt")) for f in files])
    cnt = tim[:, 5].astype(np.int64)
    if np.any(np.diff(cnt) != 1):
        raise RuntimeError(f"{name}: stream counter is not consecutive (dropped frames)")
    return val, tim[:, 3], cnt


def mode_int(x):
    v, c = np.unique(x, return_counts=True)
    return int(v[np.argmax(c)]), float(c.max() / c.sum())


def selfrm_reference(run, win, ref_from=None):
    """Step response per mode (lag 4 minus pre-response lags), its error, and the rise w.

    ref_from = "<run dir>:<window>" takes the on-sky cube of another window instead.
    """
    cube = run / f"win_{win}" / "selfRM_onsky_stg2.fits"
    if ref_from:
        r2, w2 = ref_from.split(":")
        cube = Path(r2) / f"win_{w2}" / "selfRM_onsky_stg2.fits"
    sky = fits.getdata(cube).astype(np.float64)
    cal = fits.getdata(run / "selfRM_calib_stg2.fits").astype(np.float64)
    step = sky[4, :NB, :NB] - sky[0:3, :NB, :NB].mean(0)
    ref = np.diag(step).copy()
    err = np.array([np.sqrt(np.mean(np.delete(step[:, m], m) ** 2)) for m in range(NB)])
    cstep = np.array([cal[4:8, m, m].mean() - cal[1:3, m, m].mean() for m in range(NB)])
    rise_cal = np.array([cal[3, m, m] - cal[1:3, m, m].mean() for m in range(NB)]) / cstep
    rise_sky = np.diag(sky[3, :NB, :NB] - sky[0:3, :NB, :NB].mean(0)) / ref
    # The calibration cube is taken in the simulator's fast lockstep mode, which on this
    # machine sometimes returns a corrupted cube (not a clean step). It is only needed to turn
    # the step response into an optical gain, so flag it instead of using it.
    plat = np.array([np.mean(np.diag(cal[z, :NB, :NB])) for z in range(4, 8)])
    if np.ptp(plat) > 0.02 * abs(plat.mean()) or abs(np.median(rise_cal) - 0.88) > 0.05:
        return ref, err, None, float("nan"), float(np.median(rise_sky[2:]))
    return ref, err, ref / cstep, float(np.median(rise_cal)), float(np.median(rise_sky[2:]))


def sim_frame_times(tA, cA, tB, cB, b_offset_us=0.0, per_a=PERIOD_A_US, per_b=PERIOD_B_US):
    """End of exposure [us] of every WFS A and WFS B frame of a simulator window.

    The only simulator-specific step. Each sensor clock is regular, so a frame ends at its
    counter times the frame period; what has to be found is the phase between the two clocks.
    The simulator reads both sensors out on one fine clock: WFS A frames end on a WFS B period
    boundary and, with a WFS B clock offset s, WFS B frames end s after one. The last WFS B
    frame logged before a WFS A frame therefore ended (per_b - s) mod per_b before it.
    """
    ratio = per_a / per_b
    if abs(ratio - round(ratio)) > 1e-9:
        raise ValueError("simulator adapter: WFS A period must be a multiple of WFS B's")
    ratio = int(round(ratio))
    iB = np.clip(np.searchsorted(tB, tA) - 1, 0, len(tB) - 1)
    q, frac = mode_int(cB[iB] - ratio * cA)
    eA = (cA - cA[0]) * per_a
    eB = (cB - q - ratio * cA[0]) * per_b - (per_b - b_offset_us) % per_b
    return eA, eB, q, frac


def acting_command(D, kD, kernel):
    """DM2 command as it acts during each WFS B frame: sum over lags of weight * D[kD - lag].

    kD[k] is the index of the command written right after WFS B frame k; kernel maps a lag in
    WFS B frames to its weight (the increments of the measured step response).
    """
    out = np.full((len(kD), D.shape[1]), np.nan)
    ok = (kD - max(kernel) >= 0) & (kD - min(kernel) < len(D))
    out[ok] = sum(wgt * D[kD[ok] - lag] for lag, wgt in kernel.items())
    return out


def choose_windows(eA, per_a, eB, per_b, n_b=None, anchor=None, tol=1e-3):
    """Windows made of whole WFS B frames.

    Returns the index of the first WFS B frame, the number of WFS B frames per window, and
    whether window edges cut WFS A frames.
        n_cut    fewest WFS B frames holding at least two frames of each sensor
        n_exact  fewest WFS B frames (at least two, at least one WFS A frame long) whose edges
                 all fall on WFS A frame edges, so that no WFS A frame is cut
    n_exact is used when it exists and is not longer than n_cut. n_b and anchor override the
    length and the first frame.
    """
    s_b = eB[0] - per_b                                    # start of the first WFS B frame

    def on_a_edges(first, n):
        r = n * per_b / per_a
        p = (s_b + first * per_b - eA[0]) / per_a
        return abs(r - round(r)) < tol and abs(p - round(p)) < tol

    n_cut = max(2, int(np.ceil(2.0 * per_a / per_b - tol)))
    sizes = [n_b] if n_b else [n for n in range(2, n_cut + 1) if n * per_b > per_a * (1 - tol)]
    for n in sizes:
        for first in (range(n) if anchor is None else [anchor % n]):
            if on_a_edges(first, n):
                return first, n, False
    n = n_b if n_b else n_cut
    return (0 if anchor is None else anchor % n), n, True


def overlap_average(vals, f_end, f_len, w0, w1, order=0):
    """Average over windows [w0, w1) of a signal known through its frame averages.

    order 0 takes the signal as constant inside a frame: a window value is the mean of the
    frames it overlaps, weighted by the overlap (exact when no frame is cut). order 1 takes it
    as linear inside a frame, with the slope given by the two neighbouring frames.
    """
    mean = vals.mean(0)
    v = vals - mean                                        # keeps the running sum small
    cs = np.vstack([np.zeros((1, v.shape[1])), np.cumsum(v, axis=0)])
    f_start = f_end - f_len
    slope = np.zeros_like(v)
    if order == 1:
        slope[1:-1] = (v[2:] - v[:-2]) / (2.0 * f_len)

    def integral(t):                                       # of the rebuilt signal, up to t
        k = np.clip(np.searchsorted(f_end, t, side="left"), 0, len(f_end) - 1)
        x = np.clip(t - f_start[k], 0.0, f_len)[:, None]   # time into frame k
        lin = 0.5 * slope[k] * ((x - 0.5 * f_len) ** 2 - (0.5 * f_len) ** 2)
        return cs[k] * f_len + v[k] * x + lin

    return mean + (integral(w1) - integral(w0)) / (w1 - w0)[:, None]


def align_frames(A, eA, per_a, B, eB, per_b, Deff, n_b=None, anchor=None, order=0, times=False):
    """A, B and the acting DM2 command on one timeline with one exposure, for any two clocks.

    A, B         frame values of the two sensors
    eA, eB       times at which their exposures end; per_a, per_b the exposure lengths
    Deff         DM2 command as it acts during each WFS B frame (acting_command)
    Returns the window values of A, B and Deff, and a description of the windows (and the
    window start times with times=True).
    """
    first, n, cut = choose_windows(eA, per_a, eB, per_b, n_b, anchor)
    nw = (len(B) - first) // n
    sl = slice(first, first + n * nw)
    Bw = B[sl].reshape(nw, n, -1).mean(1)
    Dw = Deff[sl].reshape(nw, n, -1).mean(1)
    w1 = eB[first + n - 1 + n * np.arange(nw)]
    w0 = w1 - n * per_b
    Aw = overlap_average(A, eA, per_a, w0, w1, order)
    eps = 1e-6 * per_a
    edge = per_a if order else 0.0                         # order 1 needs both neighbours
    ok = (w0 >= eA[0] - per_a + edge - eps) & (w1 <= eA[-1] - edge + eps)
    ok &= np.isfinite(Dw[:, 0])
    desc = dict(first_b=int(first), b_per_window=int(n), a_cut=bool(cut),
                window_us=float(n * per_b), lag0=3 if cut else 2)
    if times:
        return Aw[ok], Bw[ok], Dw[ok], desc, w0[ok]
    return Aw[ok], Bw[ok], Dw[ok], desc


def align(run, win, w, pair=0, tsub=None, b_offset_us=0.0, n_b=None, anchor=None, order=0):
    """A, B, D on one timeline with one exposure, plus bookkeeping (see the module docstring).

    b_offset_us is the configured WFS B clock offset. pair shifts the assumed WFS B clock by
    that many WFS B frames (a deliberate pairing error, for checks).
    """
    tdir = run / f"win_{win}" / "telemetry"
    A, tA, cA = load_stream(tdir, "aol1_modevalWFS", NA)
    B, tB, cB = load_stream(tdir, "aol2_modevalWFS", NB)
    D, tD, cD = load_stream(tdir, "aol2_modevalDM", NB)
    # D frame written right after B frame k: constant counter offset, from the timestamps
    iD = np.clip(np.searchsorted(tD, tB), 0, len(tD) - 1)
    oD, fD = mode_int(cD[iD] - cB)
    kD = np.arange(len(B)) + (cB[0] + oD - cD[0])          # index into D for B frame k
    Deff = acting_command(D, kD, {2: w, 3: 1.0 - w})
    eA, eB, oA, fA = sim_frame_times(tA, cA, tB, cB, b_offset_us)
    eB = eB - pair * PERIOD_B_US
    Aw, Bw, Dw, desc = align_frames(A, eA, PERIOD_A_US, B, eB, PERIOD_B_US, Deff, n_b, anchor,
                                    order)
    info = dict(n_a=int(len(A)), n_b=int(len(B)), n_used=int(len(Aw)), off_d=oD, off_d_frac=fD,
                off_a=oA, off_a_frac=fA, wall_dt_a=float(np.median(np.diff(tA))),
                b_offset_us=float(b_offset_us), **desc)
    if tsub is not None:  # sub-window in physical seconds
        per_s = 1e6 / desc["window_us"]
        i0, i1 = int(round(tsub[0] * per_s)), int(round(tsub[1] * per_s))
        Aw, Bw, Dw = Aw[i0:i1], Bw[i0:i1], Dw[i0:i1]
        info["n_used"] = int(len(Aw))
    return Aw, Bw, Dw, info


def align_fixed(run, win, w, pair=0, tsub=None):
    """Original alignment: 1 kHz / 2 kHz sensors with aligned clocks only (for comparison)."""
    tdir = run / f"win_{win}" / "telemetry"
    A, tA, cA = load_stream(tdir, "aol1_modevalWFS", NA)
    B, tB, cB = load_stream(tdir, "aol2_modevalWFS", NB)
    D, tD, cD = load_stream(tdir, "aol2_modevalDM", NB)
    # D frame written right after B frame k: constant counter offset, from the timestamps
    iD = np.clip(np.searchsorted(tD, tB), 0, len(tD) - 1)
    oD, fD = mode_int(cD[iD] - cB)
    # last B frame before each A frame: the tick at which the A exposure ends
    iB = np.clip(np.searchsorted(tB, tA) - 1, 0, len(tB) - 1)
    oA, fA = mode_int(cB[iB] - 2 * cA)
    kD = np.arange(len(B)) + (cB[0] + oD - cD[0])          # index into D for B frame k
    Deff = np.full_like(B, np.nan)
    ok = (kD - 3 >= 0) & (kD - 2 < len(D))
    Deff[ok] = w * D[kD[ok] - 2] + (1.0 - w) * D[kD[ok] - 3]
    kT = 2 * cA + oA - cB[0] + pair                        # index into B of tick T per A frame
    good = (kT - 1 >= 0) & (kT < len(B))
    good &= np.isfinite(np.where(good, Deff[np.clip(kT - 1, 0, len(B) - 1), 0], np.nan))
    kT, Ag = kT[good], A[good]
    Bb = 0.5 * (B[kT - 1] + B[kT])
    Db = 0.5 * (Deff[kT - 1] + Deff[kT])
    t = (tA[good] - tA[good][0])
    info = dict(n_a=int(len(A)), n_b=int(len(B)), n_used=int(len(Ag)), off_d=oD, off_d_frac=fD,
                off_a=oA, off_a_frac=fA, wall_dt_a=float(np.median(np.diff(tA))),
                b_offset_us=0.0, first_b=-1, b_per_window=2, a_cut=False,
                window_us=PERIOD_A_US, lag0=2)
    if tsub is not None:  # sub-window in physical seconds (A frames are 1 ms apart)
        i0, i1 = int(round(tsub[0] * 1000)), int(round(tsub[1] * 1000))
        Ag, Bb, Db = Ag[i0:i1], Bb[i0:i1], Db[i0:i1]
        info["n_used"] = int(len(Ag))
    return Ag, Bb, Db, info


def cen(x):
    return x - x.mean(0)


def tsls(y, X, Z):
    Q, _ = np.linalg.qr(Z)
    Xh = Q @ (Q.T @ X)
    return np.linalg.solve(Xh.T @ X, Xh.T @ y)


def lagmat(x, t, lags):
    return np.column_stack([x[t - l] for l in lags])


def psi_from(A, B, D, gstart):
    Saa = A.T @ A
    return A @ np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), A.T @ (B - D * gstart))


def estimate(A, B, D, gstart, lag0=2, nlag=8):
    """All estimators; returns dict name -> g (NB,), plus the psi scale c and usable fraction.

    Instruments: differenced psi at lags lag0 .. lag0 + nlag - 1 (psi one lag earlier for the
    undifferenced form). lag0 = 2 unless window edges cut WFS A frames, then 3.
    """
    A, B, D = cen(A), cen(B), cen(D)
    psi = psi_from(A, B, D, gstart)
    dB, dP, dD = (np.diff(x, axis=0) for x in (B, psi, D))
    t, td = np.arange(lag0 + nlag, len(B)), np.arange(lag0 + nlag, len(dB))
    out = {k: np.zeros(NB) for k in ("LS", "LS diff", "IV", "IV diff")}
    c_iv, use = np.zeros(NB), np.zeros(NB)
    for i in range(NB):
        X, Xd = np.column_stack([psi[t, i], D[t, i]]), np.column_stack([dP[td, i], dD[td, i]])
        out["LS"][i] = np.linalg.lstsq(X, B[t, i], rcond=None)[0][1]
        out["LS diff"][i] = np.linalg.lstsq(Xd, dB[td, i], rcond=None)[0][1]
        out["IV"][i] = tsls(B[t, i], X, lagmat(psi[:, i], t, range(lag0 - 1, lag0 - 1 + nlag)))[1]
        Z = lagmat(dP[:, i], td, range(lag0, lag0 + nlag))
        c_iv[i], out["IV diff"][i] = tsls(dB[td, i], Xd, Z)
        Q, _ = np.linalg.qr(Z)
        ph, dh = Q @ (Q.T @ Xd[:, 0]), Q @ (Q.T @ Xd[:, 1])
        dp = dh - ph * (ph @ dh) / (ph @ ph)
        use[i] = (dp @ dp) / (Xd[:, 1] @ Xd[:, 1])
    return out, c_iv, use


def summarize(name, g, ref):
    r = g / ref - 1.0
    return dict(name=name, med=float(100 * np.median(r[2:])),
                mae=float(100 * np.median(np.abs(r[2:]))),
                q1=float(100 * np.percentile(r[2:], 25)), q3=float(100 * np.percentile(r[2:], 75)),
                tt=[float(100 * r[0]), float(100 * r[1])], med_all=float(100 * np.median(r)),
                ratio=(g / ref).tolist())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("win")
    ap.add_argument("--tsub", default=None)
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--pair", type=int, default=0)
    ap.add_argument("--rise", type=float, default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--ref-from", default=None)
    ap.add_argument("--b-offset-us", type=float, default=0.0,
                    help="configured WFS B clock offset (--clock-skew-us of the run)")
    ap.add_argument("--nb", type=int, default=None, help="WFS B frames per window")
    ap.add_argument("--anchor", type=int, default=None, help="first WFS B frame of a window")
    ap.add_argument("--lag0", type=int, default=None, help="first instrument lag")
    ap.add_argument("--linear", action="store_true", help="linear model inside cut frames")
    ap.add_argument("--fixed", action="store_true", help="original fixed-clock alignment")
    a = ap.parse_args()
    run = Path(a.run)
    ref, err, og, rise_cal, rise_sky = selfrm_reference(run, a.win, a.ref_from)
    w = a.rise if a.rise is not None else rise_sky
    tsub = tuple(float(x) for x in a.tsub.split(":")) if a.tsub else None
    if a.fixed:
        A, B, D, info = align_fixed(run, a.win, w, a.pair, tsub)
    else:
        A, B, D, info = align(run, a.win, w, a.pair, tsub, a.b_offset_us, a.nb, a.anchor,
                              int(a.linear))
    lag0 = info["lag0"] if a.lag0 is None else a.lag0
    cdir = run / f"win_{a.win}" / "calib_2wfs1dm"
    tool = fits.getdata(cdir / "mdb_diag.fits").astype(np.float64).ravel()[:NB]
    tool_og = fits.getdata(cdir / "og_selfrm.fits").astype(np.float64).ravel()[:NB]
    gstart = tool.copy() if a.start is None else a.start * ref
    est, c_iv, use = estimate(A, B, D, gstart, lag0)
    est = {"tool W(z)": tool, **est}
    res = dict(run=str(run), window=a.win, tsub=tsub, rise=w, rise_cal=rise_cal,
               ref_from=a.ref_from, fixed=a.fixed, linear=a.linear, lag0=lag0,
               rise_sky=rise_sky, pair=a.pair, start=a.start, info=info,
               ref=ref.tolist(), ref_err=err.tolist(), og=None if og is None else og.tolist(),
               usable_pct=float(100 * np.median(use[2:])), c_iv=c_iv.tolist(),
               usable=use.tolist(), rows=[summarize(k, v, ref) for k, v in est.items()])
    res["tool_og_selfrm_med"] = float(np.median(tool_og[2:]))
    if not a.quiet:
        dur = info["n_used"] * info["window_us"] * 1e-6
        print(f"window {a.win}: {info['n_used']} samples of {info['b_per_window']} WFS B frames"
              f" ({info['window_us']:g} us, {dur:.2f} s){' [fixed-clock recipe]' * a.fixed};"
              f" WFS B clock offset {info['b_offset_us']:g} us;"
              f" WFS A frames cut: {'yes' if info['a_cut'] else 'no'};"
              f" instruments from lag {lag0}")
        print(f"counter offsets D-B {info['off_d']} ({info['off_d_frac']:.3f}),"
              f" B-2A {info['off_a']} ({info['off_a_frac']:.3f}); rise w = {w:.3f}")
        ogs = ("calibration cube corrupted, optical gain not computed" if og is None
               else f"optical gain {np.median(og[2:]):.3f}")
        print(f"reference step response: median {np.median(ref[2:]):.3f} ({ogs}),"
              f" per-mode error {np.median(err[2:]):.4f};"
              f" shipped og_selfrm median {res['tool_og_selfrm_med']:.3f}")
        weak = "" if res["usable_pct"] >= 5.0 else (
            "  ** below 5%: instruments too old or windows too long; expect a biased estimate **")
        print(f"usable part of differenced DM2 command: {res['usable_pct']:.1f}%{weak}\n")
        print(f"{'estimator':12s} {'bias of median, modes 2-39':>27s} {'quartiles':>17s}"
              f" {'per-mode |err|':>15s} {'tip':>7s} {'tilt':>7s}")
        for r in res["rows"]:
            print(f"{r['name']:12s} {r['med']:+26.1f}% {r['q1']:+8.1f}/{r['q3']:+6.1f}%"
                  f" {r['mae']:14.1f}% {r['tt'][0]:+6.0f}% {r['tt'][1]:+6.0f}%")
    tag = "" if tsub is None else f"_{tsub[0]:g}_{tsub[1]:g}"
    tag += "" if a.start is None else f"_start{a.start:g}"
    tag += "" if a.pair == 0 else f"_pair{a.pair:+d}"
    tag += "" if a.rise is None else f"_rise{a.rise:g}"
    tag += "" if a.b_offset_us == 0 else f"_boff{a.b_offset_us:g}"
    tag += "" if a.nb is None else f"_nb{a.nb}"
    tag += "" if a.anchor is None else f"_anchor{a.anchor}"
    tag += "" if a.lag0 is None else f"_lag{a.lag0}"
    tag += "_linear" * a.linear + "_fixed" * a.fixed
    (run / f"win_{a.win}" / f"realsim_est{tag}.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    main()
