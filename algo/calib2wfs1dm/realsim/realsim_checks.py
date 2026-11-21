#!/usr/bin/python3
"""Battery of checks of the real-telemetry estimators on one window.

    pairing   which two WFS B frames go with a WFS A frame (offset in master ticks)
    rise      share of the DM2 command acting two frames later (the rest acts three later)
    start     starting gain used to build psi (factor on the reference)
    windows   independent sub-windows of the telemetry

Usage: realsim_checks.py <run dir> <window label> [total seconds]
"""
import sys
from pathlib import Path

import numpy as np

import realsim_est as R

EST = ("tool W(z)", "LS", "LS diff", "IV", "IV diff")


def run_one(run, win, ref, w, pair=0, tsub=None, start=None, tool=None):
    A, B, D, info = R.align(run, win, w, pair, tsub)
    gstart = tool if start is None else start * ref
    est, c_iv, use = R.estimate(A, B, D, gstart)
    out = {}
    for k, g in est.items():
        r = g / ref - 1.0
        out[k] = (100 * np.median(r[2:]), 100 * np.median(np.abs(r[2:])), 100 * r[:2].mean())
    out["usable"] = 100 * np.median(use[2:])
    return out


def timing_scans(run, win, ref):
    """Pairing check that does not look at the gain estimates.

    The fast part of WFS A must correlate best with the disturbance rebuilt at WFS B,
    B - g D_eff, when the latter is averaged over the two WFS B frames of the same exposure.
    (A similar "smoothest rebuilt disturbance" scan of the DM2 lag is NOT valid in closed loop:
    WFS B noise fed back through the integrator favours a lag of one frame. The DM2 timing is
    taken from the self-response cube instead, which measures it directly.)
    """
    # The stage-2 integrator is software: D[k] = mult D[k-1] - gain_i B[k+s] exactly, for the
    # right frame shift s. This checks the B-to-D frame association with no noise ambiguity.
    tdir = run / f"win_{win}" / "telemetry"
    B, tB, cB = R.load_stream(tdir, "aol2_modevalWFS", R.NB)
    D, tD, cD = R.load_stream(tdir, "aol2_modevalDM", R.NB)
    iD = np.clip(np.searchsorted(tD, tB), 0, len(tD) - 1)
    oD, _ = R.mode_int(cD[iD] - cB)
    k = np.arange(4, len(B) - 4)
    kD = k + (cB[0] + oD - cD[0])
    ok = (kD - 1 >= 0) & (kD < len(D))
    k, kD = k[ok], kD[ok]
    print("controller check: D[k] - mult D[k-1] against B[k+s] (mult 0.98), modes 2-39:")
    for sft in (-2, -1, 0, 1, 2):
        u = D[kD] - 0.98 * D[kD - 1]
        v = B[k + sft]
        c = [np.corrcoef(u[:, i], v[:, i])[0, 1] for i in range(2, R.NB)]
        gn = [-(u[:, i] @ v[:, i]) / (v[:, i] @ v[:, i]) for i in range(2, R.NB)]
        print(f"  s = {sft:+d}: median correlation {np.median(c):+.4f}, fitted gain"
              f" {np.median(gn):.4f}")
    print("pairing scan: correlation of diff(A) with diff of the rebuilt disturbance:")
    _, _, _, rc, rs = R.selfrm_reference(run, win)
    for p in (-3, -2, -1, 0, 1, 2, 3):
        A, Bb, Db, _ = R.align(run, win, rs, p)
        dA, dS = np.diff(A[:, :R.NB], axis=0), np.diff(Bb - ref * Db, axis=0)
        c = [np.corrcoef(dA[:, i], dS[:, i])[0, 1] for i in range(2, R.NB)]
        print(f"  pair {p:+d}: median correlation {np.median(c):+.3f}")


def line(tag, o, keys=("LS", "LS diff", "IV", "IV diff")):
    s = f"  {tag:22s}"
    for k in keys:
        s += f"  {o[k][0]:+6.1f} / {o[k][1]:4.1f}"
    return s + f"   usable {o['usable']:.1f}%"


def main(run, win, total=20.0):
    from astropy.io import fits
    run, total = Path(run), float(total)
    ref, err, og, rise_cal, rise_sky = R.selfrm_reference(run, win)
    tool = fits.getdata(run / f"win_{win}" / "calib_2wfs1dm" / "mdb_diag.fits").ravel()[:R.NB]
    tool = tool.astype(np.float64)
    timing_scans(run, win, ref)
    hdr = "LS            LS diff       IV            IV diff"
    print(f"window {win}: bias of median / per-mode median |err| [%], modes 2-39")
    print(f"  {'':22s}  {hdr}")
    print(line("baseline", run_one(run, win, ref, rise_sky, tool=tool)))
    print("pairing offset [ticks]:")
    for p in (-2, -1, 1, 2):
        print(line(f"pair {p:+d}", run_one(run, win, ref, rise_sky, pair=p, tool=tool)))
    print("rise fraction w (baseline %.3f):" % rise_sky)
    for w in (1.0, 0.75, 0.5, 0.0):
        print(line(f"w = {w:.2f}", run_one(run, win, ref, w, tool=tool)))
    print("starting gain for psi (factor on the reference):")
    for s in (0.5, 1.0, 1.5):
        print(line(f"start x{s:g}", run_one(run, win, ref, rise_sky, start=s)))
    for nsub in (2, 4):
        print(f"independent sub-windows of {total / nsub:g} s:")
        vals = []
        for j in range(nsub):
            ts = (j * total / nsub, (j + 1) * total / nsub)
            o = run_one(run, win, ref, rise_sky, tsub=ts, tool=tool)
            vals.append([o[k][0] for k in ("LS", "LS diff", "IV", "IV diff")])
            print(line(f"{ts[0]:g}-{ts[1]:g} s", o))
        v = np.array(vals)
        print(f"  {'mean +- sd':22s}" + "".join(f"  {m:+6.1f} +- {s:4.1f}"
                                                 for m, s in zip(v.mean(0), v.std(0, ddof=1))))


if __name__ == "__main__":
    main(*sys.argv[1:])
