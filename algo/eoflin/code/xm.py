#!/usr/bin/env python3
"""How much does cross-mode coupling buy in the toy? diag AR vs EOF vs lag count."""
import sys
import numpy as np

LI, LA = 2, 0.4
name, t_tr = sys.argv[1], int(float(sys.argv[2]) * 1000)
d = np.load(name)
a_true = d["a_true"]
n_t, b = a_true.shape
for nf in [float(q) for q in sys.argv[3].split(",")]:
    pmax = 16
    idx = np.arange(pmax - 1, n_t - LI - 2)
    yt = (1 - LA) * a_true[idx + LI] + LA * a_true[idx + LI + 1]
    zm = np.mean((yt - a_true[idx]) ** 2, axis=0)
    sig2 = nf * np.median(zm)
    a = a_true + np.sqrt(sig2) * np.random.default_rng(11).standard_normal(a_true.shape)
    y = (1 - LA) * a[idx + LI] + LA * a[idx + LI + 1]
    tr, te = idx < t_tr - LI - 2, idx >= t_tr
    zoh = np.sum(np.mean((a[idx[te]] - yt[te]) ** 2, axis=0))
    print(f"noise_frac={nf}: noise/ZOH={b * sig2 / zoh:.3f}")
    for p in (1, 2, 4, 8, 16):
        # diagonal AR(p), per mode
        e = 0.0
        for m in range(b):
            xm = np.column_stack([a[idx - k, m] for k in range(p)])
            w = np.linalg.lstsq(xm[tr], y[tr, m], rcond=None)[0]
            e += np.mean((xm[te] @ w - yt[te, m]) ** 2)
        # cross-mode EOF(p)
        x = np.hstack([a[idx - k] for k in range(p)])
        g = x[tr].T @ x[tr]
        w = np.linalg.solve(g + 1e-10 * np.trace(g) / g.shape[0] * np.eye(g.shape[0]),
                            x[tr].T @ y[tr])
        ee = np.sum(np.mean((x[te] @ w - yt[te]) ** 2, axis=0))
        print(f"   P={p:2d}: diag AR resid/ZOH={e / zoh:.4f}   cross-mode EOF={ee / zoh:.4f}   "
              f"ratio={e / ee:.2f}")
