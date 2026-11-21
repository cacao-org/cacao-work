#!/usr/bin/python3
"""Controlled test of the window rule and of the instruments on one telemetry window.

The telemetry and the reference stay the same; only the windows change. On aligned-clock data
the original recipe (one WFS A frame against its two WFS B frames) cuts no frame, so every
other choice below can be compared with it on identical data.

Two sets of instruments for the differenced estimator:
    window lags   differenced psi of earlier windows, from lag 2 (no WFS A frame cut) or 3
    frame lags    the 8 most recent single-frame differences of psi whose WFS A frames end
                  before window k-1 begins, i.e. touch neither of the two windows differenced.
                  Identical to window lags 2-9 for the original recipe; for longer or cut
                  windows the instruments stay recent and keep the WFS A frame resolution.

Usage: window_checks.py <run> <window> [--b-offset-us s]
"""
import argparse
import json
from pathlib import Path

import numpy as np
from astropy.io import fits

import realsim_est as R


def load(run, win, w, b_offset_us):
    tdir = run / f"win_{win}" / "telemetry"
    A, tA, cA = R.load_stream(tdir, "aol1_modevalWFS", R.NA)
    B, tB, cB = R.load_stream(tdir, "aol2_modevalWFS", R.NB)
    D, tD, cD = R.load_stream(tdir, "aol2_modevalDM", R.NB)
    iD = np.clip(np.searchsorted(tD, tB), 0, len(tD) - 1)
    oD, _ = R.mode_int(cD[iD] - cB)
    kD = np.arange(len(B)) + (cB[0] + oD - cD[0])
    Deff = R.acting_command(D, kD, {2: w, 3: 1.0 - w})
    eA, eB, _, _ = R.sim_frame_times(tA, cA, tB, cB, b_offset_us)
    return A, eA, B, eB, Deff


def frame_lag_estimate(A, eA, Aw, Bw, Dw, w0, gstart, nlag=8, gap=0):
    """Differenced estimator with single-frame instruments (see the module docstring).

    gap leaves out that many of the most recent admissible WFS A frames.
    """
    mean = Aw.mean(0)
    Ac, Bc, Dc = Aw - mean, R.cen(Bw), R.cen(Dw)
    Saa = Ac.T @ Ac
    M = np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), Ac.T @ (Bc - Dc * gstart))
    psi_w, psi_f = Ac @ M, (A - mean) @ M
    dB, dP, dD = (np.diff(x, axis=0) for x in (Bc, psi_w, Dc))     # row k-1: window k minus k-1
    dF = np.diff(psi_f, axis=0)                                    # row j-1: frame j minus j-1
    # last WFS A frame ending by the start of window k-1, for the difference "k minus k-1"
    jlast = np.searchsorted(eA, w0[:-1] + 1e-6 * (eA[1] - eA[0]), side="right") - 1 - gap
    rows = np.flatnonzero(jlast - nlag >= 1)
    g, use = np.zeros(R.NB), np.zeros(R.NB)
    for i in range(R.NB):
        X = np.column_stack([dP[rows, i], dD[rows, i]])
        Z = np.column_stack([dF[jlast[rows] - 1 - m, i] for m in range(nlag)])
        g[i] = R.tsls(dB[rows, i], X, Z)[1]
        Q, _ = np.linalg.qr(Z)
        ph, dh = Q @ (Q.T @ X[:, 0]), Q @ (Q.T @ X[:, 1])
        dp = dh - ph * (ph @ dh) / (ph @ ph)
        use[i] = (dp @ dp) / (X[:, 1] @ X[:, 1])
    return g, use


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("win")
    ap.add_argument("--b-offset-us", type=float, default=0.0)
    ap.add_argument("--ref-from", default=None)
    ap.add_argument("--linear", action="store_true", help="linear model inside cut frames")
    a = ap.parse_args()
    run = Path(a.run)
    ref, _, _, _, rise = R.selfrm_reference(run, a.win, a.ref_from)
    cdir = run / f"win_{a.win}" / "calib_2wfs1dm"
    tool = fits.getdata(cdir / "mdb_diag.fits").astype(np.float64).ravel()[:R.NB]
    A, eA, B, eB, Deff = load(run, a.win, rise, a.b_offset_us)
    pa, pb = R.PERIOD_A_US, R.PERIOD_B_US
    first, n_auto, cut_auto = R.choose_windows(eA, pa, eB, pb)
    print(f"{a.run}:{a.win}, WFS B clock offset {a.b_offset_us:g} us; the rule picks"
          f" {n_auto} WFS B frames from frame {first}, WFS A frames cut: {cut_auto};"
          f" cut frames taken as {'linear' if a.linear else 'constant'}")
    print(f"{'WFS B frames per window, first frame':38s} {'cut':>4s}"
          f" {'window lags: bias (per mode) usable':>38s}"
          f" {'frame lags: bias (per mode) usable':>38s}")
    rows = []
    for n in (2, 3, 4, 5, 6, 8):
        for anchor in range(n if n <= 4 else 2):
            Aw, Bw, Dw, desc, w0 = R.align_frames(A, eA, pa, B, eB, pb, Deff, n, anchor,
                                                  int(a.linear), times=True)
            est, _, use = R.estimate(Aw, Bw, Dw, tool.copy(), desc["lag0"])
            s = R.summarize("w", est["IV diff"], ref)
            gf, usef = frame_lag_estimate(A, eA, Aw, Bw, Dw, w0, tool.copy())
            f = R.summarize("f", gf, ref)
            print(f"{n} frames from {anchor:<26d} {'yes' if desc['a_cut'] else 'no':>4s}"
                  f" {s['med']:+16.1f}% ({s['mae']:4.1f}%) {100 * np.median(use[2:]):5.1f}% L"
                  f"{desc['lag0']} {f['med']:+19.1f}% ({f['mae']:4.1f}%)"
                  f" {100 * np.median(usef[2:]):5.1f}%")
            rows.append(dict(n_b=n, anchor=anchor, cut=desc["a_cut"], lag0=desc["lag0"],
                             window=[s["med"], s["mae"], float(100 * np.median(use[2:]))],
                             frame=[f["med"], f["mae"], float(100 * np.median(usef[2:]))]))
    out = run / f"win_{a.win}" / f"window_checks{'_linear' * a.linear}.json"
    out.write_text(json.dumps(dict(run=str(run), window=a.win, b_offset_us=a.b_offset_us,
                                   linear=a.linear, rule=[int(first), int(n_auto),
                                                          bool(cut_auto)], rows=rows), indent=1))


if __name__ == "__main__":
    main()
