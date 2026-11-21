#!/usr/bin/python3
"""Internal consistency of a closed-loop self-response cube.

With the loop closed, the response to a poke first rises to a plateau P (lags 3-4) and then
decays as the integrator reacts. The integrator is known exactly (gain_i, leak), so the decay
gives a second, independent reading of the DM2-to-WFS-B gain: the gain g_dyn with which the
loop's OWN commands act. If the poke plateau is a valid reference, g_dyn = P.

Model, frame k after the poke command (unit DM poke applied from frame 1):
    m[k] = P s(k-1) + g_dyn sum_j du[j] s(k-j),   du[j] = u[j] - u[j-1],
    u[j] = leak u[j-1] - gain m[j],                s(d) = 0 (d<2), w (d=2), 1 (d>=3)

Usage: selfrm_dyn.py <run dir> <window label> ...
"""
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits


def model(P, g, gain, w, leak=0.98, n=8):
    def s(d):
        return 0.0 if d < 2 else (w if d == 2 else 1.0)

    m, u = np.zeros(n), np.zeros(n)
    for k in range(n):
        val = P * s(k - 1)
        for j in range(k):
            val += g * (u[j] - (u[j - 1] if j > 0 else 0.0)) * s(k - j)
        m[k] = val
        u[k] = leak * (u[k - 1] if k > 0 else 0.0) - gain * m[k]
    return m


def fit(obs, gain):
    w = obs[3] / obs[4]
    grid = np.arange(0.05, 1.60, 0.005)
    cost = [np.sum((model(obs[4], g, gain, w)[5:8] - obs[5:8]) ** 2) for g in grid]
    return float(grid[int(np.argmin(cost))])


def main(run, *wins):
    run = Path(run)
    print(f"{'window':14s} {'loop gain':>9s} {'poke plateau P':>15s} {'g_dyn':>18s}"
          f" {'g_dyn / P':>10s}")
    for win in wins:
        d = run / f"win_{win}"
        sky = fits.getdata(d / "selfRM_onsky_stg2.fits").astype(np.float64)
        mg = fits.getdata(d / "aol2_mgainfact.fits").astype(np.float64).ravel()
        gl = float(open(d / "loop_state.txt").read().split("loopgain=")[1].split()[0])
        P, G = [], []
        for i in range(2, 40):
            obs = sky[:, i, i] - sky[0:3, i, i].mean()
            P.append(obs[4])
            G.append(fit(obs, gl * mg[i]))
        P, G = np.array(P), np.array(G)
        q = np.percentile(G, [25, 75])
        print(f"{win:14s} {gl:9.4f} {np.median(P):15.3f} {np.median(G):8.3f}"
              f" [{q[0]:.2f},{q[1]:.2f}] {np.median(G / P):10.2f}")
        np.save(d / "g_dyn.npy", np.column_stack([P, G]))


if __name__ == "__main__":
    main(*sys.argv[1:])
