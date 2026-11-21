#!/usr/bin/python3
"""Differenced lagged-A estimator with the stage-3 (LLOWFS) loop closed.

Stage 3 drives DM2 through its own channel, so part of the DM2 motion seen by WFS B is not in
aol2_modevalDM, and stage 2 is told to ignore it through a zero-point offset (ZPO) on WFS B.
The logged stage-3 DM command (aol3_dmC, DM2 actuator space, 500 Hz) is projected on the
stage-2 DM modes and added to the model as two regressors per mode:

    B_i = c psi_i + g D_i + a E_i + b Z_i + error
        E = stage-3 command at the optical timing (same delay kernel as D)   expected a = g
        Z = stage-3 command at the time it is issued (when the ZPO moves)    expected b = -g_zpo

Both are treated as exogenous (they instrument themselves); psi and D are instrumented by past
differenced psi as in realsim_est.py. Everything is first-differenced on the WFS A timeline.

Usage: realsim_lowfs.py <run dir> <window label>
"""
import glob
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

import realsim_est as R


def stage3_modal(run, tdir):
    """Stage-3 DM command projected on the leading stage-2 DM modes, with its timestamps."""
    m2 = fits.getdata(run / "calib_stg2" / "CMmodesDM.fits").astype(np.float64)
    m2 = m2.reshape(m2.shape[0], -1)
    files = sorted(glob.glob(str(tdir / "aol3_dmC_*.fits")))
    dm = np.concatenate([fits.getdata(f) for f in files]).astype(np.float64)
    dm = dm.reshape(dm.shape[0], -1)
    tim = np.concatenate([np.atleast_2d(np.loadtxt(f[:-5] + ".txt")) for f in files])
    coef = np.linalg.lstsq(m2.T, dm.T, rcond=1e-6)[0].T      # (n3, n modes)
    return coef[:, :R.NB], tim[:, 3]


def align_lowfs(run, win, w):
    tdir = run / f"win_{win}" / "telemetry"
    A, tA, cA = R.load_stream(tdir, "aol1_modevalWFS", R.NA)
    B, tB, cB = R.load_stream(tdir, "aol2_modevalWFS", R.NB)
    D, tD, cD = R.load_stream(tdir, "aol2_modevalDM", R.NB)
    c3, t3 = stage3_modal(run, tdir)
    iD = np.clip(np.searchsorted(tD, tB), 0, len(tD) - 1)
    oD, _ = R.mode_int(cD[iD] - cB)
    iB = np.clip(np.searchsorted(tB, tA) - 1, 0, len(tB) - 1)
    oA, _ = R.mode_int(cB[iB] - 2 * cA)
    # stage-3 command in force when D frame j was written (zero before the first one)
    j3 = np.searchsorted(t3, tD, side="right") - 1
    D3 = np.where((j3 >= 0)[:, None], c3[np.clip(j3, 0, len(c3) - 1)], 0.0)   # on D frames
    kD = np.arange(len(B)) + (cB[0] + oD - cD[0])
    ok = (kD - 3 >= 0) & (kD < len(D))
    Deff, Eeff, Znow = (np.full_like(B, np.nan) for _ in range(3))
    Deff[ok] = w * D[kD[ok] - 2] + (1.0 - w) * D[kD[ok] - 3]
    Eeff[ok] = w * D3[kD[ok] - 2] + (1.0 - w) * D3[kD[ok] - 3]
    Znow[ok] = D3[kD[ok]]
    kT = 2 * cA + oA - cB[0]
    good = (kT - 1 >= 0) & (kT < len(B))
    good &= np.isfinite(np.where(good, Deff[np.clip(kT - 1, 0, len(B) - 1), 0], np.nan))
    kT = kT[good]
    pair = lambda x: 0.5 * (x[kT - 1] + x[kT])
    return A[good], pair(B), pair(Deff), pair(Eeff), pair(Znow)


def estimate(A, B, D, E, Z, gstart):
    A, B, D, E, Z = (R.cen(x) for x in (A, B, D, E, Z))
    psi = R.psi_from(A, B, D + E, gstart)
    dB, dP, dD, dE, dZ = (np.diff(x, axis=0) for x in (B, psi, D, E, Z))
    td = np.arange(10, len(dB))
    names = ("no stage-3 term", "g on D+E, free Z", "free E and Z")
    out = {k: np.zeros(R.NB) for k in names}
    coef = {k: np.zeros(R.NB) for k in ("a", "b", "b_tot")}
    for i in range(R.NB):
        Zi = R.lagmat(dP[:, i], td, range(2, 10))
        y = dB[td, i]
        out[names[0]][i] = R.tsls(y, np.column_stack([dP[td, i], dD[td, i]]), Zi)[1]
        X = np.column_stack([dP[td, i], dD[td, i] + dE[td, i], dZ[td, i]])
        b1 = R.tsls(y, X, np.column_stack([Zi, dZ[td, i]]))
        out[names[1]][i], coef["b_tot"][i] = b1[1], b1[2]
        X = np.column_stack([dP[td, i], dD[td, i], dE[td, i], dZ[td, i]])
        b2 = R.tsls(y, X, np.column_stack([Zi, dE[td, i], dZ[td, i]]))
        out[names[2]][i], coef["a"][i], coef["b"][i] = b2[1], b2[2], b2[3]
    rel = np.array([np.std(dE[:, i]) / np.std(dD[:, i]) for i in range(R.NB)])
    return out, coef, rel


def main(run, win):
    run = Path(run)
    ref, err, og, rise_cal, rise_sky = R.selfrm_reference(run, win)
    A, B, D, E, Z = align_lowfs(run, win, rise_sky)
    tool = fits.getdata(run / f"win_{win}" / "calib_2wfs1dm" / "mdb_diag.fits").ravel()[:R.NB]
    out, coef, rel = estimate(A, B, D, E, Z, tool.astype(np.float64))
    print(f"window {win}: {len(A)} WFS A frames; reference median {np.median(ref[2:]):.3f}")
    print(f"stage-3 share of the differenced DM2 motion (rms E / rms D): modes 0-1"
          f" {rel[:2].mean():.2f}, 2-9 {np.median(rel[2:10]):.2f}, 10-39"
          f" {np.median(rel[10:]):.2f}")
    print(f"\n{'estimator':20s} {'bias of median [%]: modes 2-9':>30s} {'10-39':>8s} {'2-39':>8s}"
          f" {'per-mode |err| 2-39':>20s} {'tip':>6s} {'tilt':>6s}")
    for k, g in {"tool W(z)": tool, **out}.items():
        r = 100 * (g / ref - 1.0)
        print(f"{k:20s} {np.median(r[2:10]):+30.1f} {np.median(r[10:]):+8.1f}"
              f" {np.median(r[2:]):+8.1f} {np.median(np.abs(r[2:])):20.1f} {r[0]:+6.0f}"
              f" {r[1]:+6.0f}")
    sel = rel > np.percentile(rel, 60)
    print(f"\ncoefficients on the stage-3 terms, modes where stage 3 moves DM2 most"
          f" ({int(sel.sum())} modes):")
    ar = np.median(coef["a"][sel] / ref[sel])
    print(f"  a / g_ref (optical timing, expected 1): median {ar:+.2f}")
    print(f"  b (issue timing, expected -g_zpo ~ -1): median {np.median(coef['b'][sel]):+.2f}")
    print(f"  b with g tied to D+E                  : median {np.median(coef['b_tot'][sel]):+.2f}")


if __name__ == "__main__":
    main(*sys.argv[1:])
