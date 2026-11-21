#!/usr/bin/python3
"""What happens during the stage-2 self-response pokes (modal streams logged meanwhile).

The stage-2 integrator is exact software, D[k] = leak (D[k-1] - p[k-1]) - gain_i B[k] + p[k],
so the poke sequence p is recovered from the logged D and B to numerical precision. With p known:

    plateau     response of B to the poke alone, as the self-response cube reports it
                (lag 4 after each poke start, minus the three samples before the response),
                for positive and negative pokes separately
    dither IV   g = sum B[k] p[k-L] / sum D_eff[k] p[k-L]: the gain with which the TOTAL
                stage-2 command (poke plus loop reaction) acts, using the poke as an exogenous
                instrument. This is the textbook closed-loop identification with a probe.
    stage 3     how much of the poke the LLOWFS loop moves on DM2 (its command projected on the
                same stage-2 mode), at the lags where the plateau is read

Usage: poke_diag.py <run dir> <window label> ...
"""
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

import realsim_est as R
import realsim_lowfs as L

LEAK = 0.98


def recover_pokes(B, D, gain):
    p = np.zeros_like(D)
    for k in range(1, len(D)):
        p[k] = D[k] - LEAK * (D[k - 1] - p[k - 1]) + gain * B[k]
    return p


def main(run, *wins):
    run = Path(run)
    for win in wins:
        d = run / f"win_{win}"
        tdir = d / "telemetry"
        B, tB, cB = R.load_stream(tdir, "aol2_modevalWFS", R.NB)
        D, tD, cD = R.load_stream(tdir, "aol2_modevalDM", R.NB)
        iD = np.clip(np.searchsorted(tD, tB), 0, len(tD) - 1)
        oD, _ = R.mode_int(cD[iD] - cB)
        sh = cB[0] + oD - cD[0]
        n = min(len(B), len(D) - sh) if sh >= 0 else min(len(B) + sh, len(D))
        Bk, Dk = (B[:n], D[sh:sh + n]) if sh >= 0 else (B[-sh:-sh + n], D[:n])
        mg = fits.getdata(d / "aol2_mgainfact.fits").astype(np.float64).ravel()[:R.NB]
        gl = float(open(d / "loop_state.txt").read().split("loopgain=")[1].split()[0])
        p = recover_pokes(Bk, Dk, gl * mg)
        amp = np.percentile(np.abs(p), 99.9)
        p[np.abs(p) < 0.3 * amp] = 0.0
        have3 = len(list(tdir.glob("aol3_dmC_*.fits"))) > 0
        if have3:
            c3, t3 = L.stage3_modal(run, tdir)
            j3 = np.searchsorted(t3, tD, side="right") - 1
            D3 = np.where((j3 >= 0)[:, None], c3[np.clip(j3, 0, len(c3) - 1)], 0.0)
            D3 = D3[sh:sh + n] if sh >= 0 else D3[:n]
        res = {k: [] for k in ("plus", "minus", "iv", "iv3", "e3", "npoke")}
        for i in range(2, R.NB):
            starts = np.where((p[1:, i] != 0) & (p[:-1, i] == 0))[0] + 1
            starts = starts[(starts > 6) & (starts < n - 12)]
            sgn = np.sign(p[starts, i])
            # self-response convention: poke first present in output frame s, read at s+3
            resp = (Bk[starts + 3, i] - Bk[starts[:, None] + np.arange(-4, -1), i].mean(1))
            resp = resp / p[starts, i]
            res["plus"].append(resp[sgn > 0].mean() if np.any(sgn > 0) else np.nan)
            res["minus"].append(resp[sgn < 0].mean() if np.any(sgn < 0) else np.nan)
            res["npoke"].append(len(starts))
            # dither IV over all frames, D_eff with the measured rise kernel, instrument = poke
            w = 0.883
            k = np.arange(8, n)
            de = w * Dk[k - 2, i] + (1 - w) * Dk[k - 3, i]
            z = w * p[k - 2, i] + (1 - w) * p[k - 3, i]
            res["iv"].append((Bk[k, i] @ z) / (de @ z))
            if have3:
                e = w * D3[k - 2, i] + (1 - w) * D3[k - 3, i]
                # stage-3 motion per unit poke at the plateau lag, and IV with total DM2 motion
                res["e3"].append((e @ z) / (z @ z))
                res["iv3"].append((Bk[k, i] @ z) / ((de + e) @ z))
        med = lambda x: float(np.nanmedian(x))
        print(f"window {win}: {n} frames, poke amplitude {amp:.4f}, pokes per mode"
              f" {int(np.median(res['npoke']))}, loop gain {gl}")
        print(f"  poke plateau (as the cube reads it): + pokes {med(res['plus']):.3f},"
              f" - pokes {med(res['minus']):.3f}")
        print(f"  dither IV, gain of the total stage-2 command: {med(res['iv']):.3f}"
              f" [quartiles {np.nanpercentile(res['iv'], 25):.3f},"
              f" {np.nanpercentile(res['iv'], 75):.3f}]")
        if have3:
            print(f"  stage-3 motion on the poked mode per unit poke: {med(res['e3']):+.3f};"
                  f" dither IV counting stage-3 motion as DM2 motion: {med(res['iv3']):.3f}")
        np.save(d / "poke_diag_iv.npy", np.array(res["iv"]))


if __name__ == "__main__":
    main(*sys.argv[1:])
