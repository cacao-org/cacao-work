#!/usr/bin/python3
"""Pure lookup (no linear stage) over a grid of key sizes and neighbour counts."""
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selflearn_probe import load, knn_idx, oof_ridge, ridge

W, _ = load(sys.argv[1], "aol1_modevalWFS")
D, _ = load(sys.argv[1], "aol1_modevalDM")
h, delta, ntr, gap = 10, 2, 14000, 500
T = len(W)
t = np.arange(h - 1, T - delta)
tr, te = t < ntr, (t >= ntr + gap) & (t % 3 == 0)
for lo in (0, 200):
    idx = np.arange(lo, lo + 50)
    X = np.concatenate([np.concatenate([W[t - j][:, idx], D[t - j][:, idx]], 1)
                        for j in range(h)], 1).astype(np.float64)
    Y = W[t + delta][:, idx].astype(np.float64)
    X = (X - X[tr].mean(0)) / X[tr].std(0)
    Y = Y - Y[tr].mean(0)
    sst = (Y[te] ** 2).sum()
    lam, _ = oof_ridge(X[tr], Y[tr])
    lin = 1 - ((Y[te] - X[te] @ ridge(X[tr], Y[tr], lam)) ** 2).sum() / sst
    pers = 1 - ((Y[te] - W[t[te]][:, idx] + W[t[tr]][:, idx].mean(0)) ** 2).sum() / sst
    print(f"modes {lo}-{lo + 49}: linear {100 * lin:.1f}%   persistence (last frame) "
          f"{100 * pers:.1f}%")
    w, V = np.linalg.eigh(X[tr].T @ X[tr])
    V, w = V[:, ::-1], w[::-1]
    print("  pure lookup, % of baseline residual variance removed; rows = key dims (PCA),"
          " cols = k")
    print("  " + " " * 22 + "".join(f"{k:>8d}" for k in (5, 20, 50, 200, 1000)))
    for q in (2, 4, 8, 16, 32, 64, 128):
        r = []
        for k in (5, 20, 50, 200, 1000):
            nn = knn_idx(X[te] @ V[:, :q], X[tr] @ V[:, :q], k)
            r.append(1 - ((Y[te] - Y[tr][nn].mean(1)) ** 2).sum() / sst)
        print(f"  q={q:4d} ({100 * w[:q].sum() / w.sum():4.1f}% var)" + " " * 3
              + "".join(f"{100 * v:8.1f}" for v in r), flush=True)
