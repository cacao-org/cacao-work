#!/usr/bin/env python3
"""Sample complexity of plain EOF vs noise level, ridge, and regressor normalization."""
import sys, time
import numpy as np
from an import load, res, P, LI

name = sys.argv[1]
t_tr = int(float(sys.argv[2]) * 1000)
for nf in [float(q) for q in sys.argv[3].split(",")]:
    d, a_true, a, lab, idx, x, y, yt, sig2, zoh_mode = load(name, nf)
    te = np.where(idx >= t_tr)[0]
    x_te, yt_te = x[te], yt[te]
    zoh = res(a[idx[te]], yt_te)
    zoh_noisy_t = res(a[idx[te]], y[te])
    print(f"noise_frac={nf} sig2={sig2:.2e} ZOH(truth)={zoh:.3e} lag-only={zoh_mode.sum():.3e}")
    sd = x[: t_tr].std(axis=0)
    for n in (8192, 16384, 32768, 65536):
        m = (idx >= t_tr - n) & (idx < t_tr - LI - 2)
        xm, ym = x[m], y[m]
        g, r = xm.T @ xm, xm.T @ ym
        row = []
        for reg in (0.0, 1e-8, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2):
            lam = reg * np.trace(g) / g.shape[0]
            lam += 1e-12 * np.trace(g) / g.shape[0]
            w = np.linalg.solve(g + lam * np.eye(g.shape[0]), r)
            yh = x_te @ w
            row.append(f"{res(yh, yt_te) / zoh:7.3f}")
        # whitened-regressor ridge (per-column normalization)
        gn = g / np.outer(sd, sd)
        rn = r / sd[:, None]
        roww = []
        for reg in (1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1):
            lam = reg * np.trace(gn) / gn.shape[0]
            w = np.linalg.solve(gn + lam * np.eye(gn.shape[0]), rn) / sd[:, None]
            roww.append(f"{res(x_te @ w, yt_te) / zoh:7.3f}")
        print(f"  N={n:6d} raw ridge reg[0,1e-8,1e-6,1e-5,1e-4,1e-3,1e-2]: " + " ".join(row))
        print(f"           col-normalized reg[1e-6..1e-1]:               " + " ".join(roww))
