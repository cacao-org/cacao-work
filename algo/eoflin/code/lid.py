#!/usr/bin/env python3
"""Do 'similar past states' exist? NN-distance ratio and local intrinsic dimension of histories."""
import sys
import numpy as np

LI, LA, P = 2, 0.4, 8
name, nf = sys.argv[1], float(sys.argv[2])
d = np.load(name)
a_true = d["a_true"]
n_t, b = a_true.shape
idx = np.arange(P - 1, n_t - LI - 2)
yt = (1 - LA) * a_true[idx + LI] + LA * a_true[idx + LI + 1]
sig2 = nf * float(np.mean(np.mean((yt - a_true[idx]) ** 2, axis=0)))
a = a_true + np.sqrt(sig2) * np.random.default_rng(11).standard_normal(a_true.shape)
sd = a.std(axis=0)
rng = np.random.default_rng(3)
for label, blk, norm in (("modes 0-63 raw", slice(0, 64), False),
                         ("modes 0-63 per-mode normalized", slice(0, 64), True),
                         ("modes 32-63 raw (equal-variance block)", slice(32, 64), False)):
    aa = a[:, blk] / (sd[blk] if norm else 1.0)
    x = np.hstack([aa[idx - k] for k in range(P)])
    ref = np.arange(0, x.shape[0], 4)
    q = rng.choice(x.shape[0], 400, replace=False)
    xr = x[ref]
    xr2 = np.sum(xr**2, axis=1)
    ratio1, lid = [], []
    k = 20
    for r in q:
        dist = np.sqrt(np.maximum(xr2 - 2 * xr @ x[r] + x[r] @ x[r], 0))
        far = np.abs(idx[ref] - idx[r]) > 2000      # exclude the same 2 s stretch of trajectory
        dd = np.sort(dist[far])
        ratio1.append(dd[0] / np.median(dd))
        lid.append((k - 1) / np.sum(np.log(dd[k - 1] / dd[: k - 1])))
    print(f"{name} {label:<40s} N_ref={ref.size}  NN dist/median dist: {np.median(ratio1):.3f}   "
          f"LID (Levina-Bickel, k={k}): median {np.median(lid):.1f}")
