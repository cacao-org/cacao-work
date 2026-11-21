#!/usr/bin/env python3
"""Regime question: how much does one pooled linear EOF lose vs regime-specific EOFs?

Usage: rg.py <data.npz> <t_train_s> <noise_frac(mean-based)> [P]
"""
import sys
import time

import numpy as np

LI, LA = 2, 0.4
EPS = 1e-10


def res(yh, yt):
    return float(np.sum(np.mean((yh - yt) ** 2, axis=0)))


def solve(g, r, reg=EPS):
    d_f = g.shape[0]
    return np.linalg.solve(g + reg * np.trace(g) / d_f * np.eye(d_f), r)


def offdiag_frac(w, p, b):
    w3 = w.reshape(p, b, b)  # [lag, in_mode, out_mode]
    tot = float(np.sum(w3**2))
    dia = float(np.sum(np.stack([np.diag(w3[k]) for k in range(p)]) ** 2))
    return 1.0 - dia / tot


def main():
    name, t_tr, nf = sys.argv[1], int(float(sys.argv[2]) * 1000), float(sys.argv[3])
    p = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    t0 = time.time()
    d = np.load(name)
    a_true, lab = d["a_true"], d["lab"]
    n_t, b = a_true.shape
    idx = np.arange(p - 1, n_t - LI - 2)
    yt = (1 - LA) * a_true[idx + LI] + LA * a_true[idx + LI + 1]
    zm = np.mean((yt - a_true[idx]) ** 2, axis=0)
    sig2 = nf * float(np.mean(zm))
    a = a_true + np.sqrt(sig2) * np.random.default_rng(11).standard_normal(a_true.shape)
    y = (1 - LA) * a[idx + LI] + LA * a[idx + LI + 1]
    x = np.hstack([a[idx - k] for k in range(p)])
    tr = idx < t_tr - LI - 2
    te = idx >= t_tr
    nreg = int(lab.max()) + 1
    lt = lab[idx]
    pure = lab[idx - p + 1] == lab[idx + LI + 1]

    def zoh_of(m):
        return res(a[idx[m]], yt[m])

    zoh = zoh_of(te)
    print(f"{name} P={p} D={p * b} noise_frac={nf} noise/ZOH={b * sig2 / zoh:.3f} "
          f"modal var>1e-6: {int(np.sum(np.var(a_true, axis=0) > 1e-6))}/{b}")

    # diagonal AR(p), pooled
    e_ar = np.zeros(nreg + 1)
    for m in range(b):
        xm = np.column_stack([a[idx - k, m] for k in range(p)])
        w = np.linalg.lstsq(xm[tr], y[tr, m], rcond=None)[0]
        err = (xm @ w - yt[:, m]) ** 2
        e_ar[nreg] += err[te].mean()
        for k in range(nreg):
            e_ar[k] += err[te & (lt == k)].mean()

    g_all = x[tr].T @ x[tr]
    r_all = x[tr].T @ y[tr]
    w_g = solve(g_all, r_all)
    yh_g = x @ w_g
    w_k = []
    for k in range(nreg):
        m = tr & pure & (lt == k)
        w_k.append(solve(x[m].T @ x[m], x[m].T @ y[m]))
    yh_o = np.zeros_like(yt)
    for k in range(nreg):
        yh_o[lt == k] = x[lt == k] @ w_k[k]

    print(f"  pooled over test: diagAR={e_ar[nreg] / zoh:.4f}  "
          f"global EOF={res(yh_g[te], yt[te]) / zoh:.4f}"
          f"  oracle per-regime EOF={res(yh_o[te], yt[te]) / zoh:.4f}"
          f"   offdiag L2 frac(global)={offdiag_frac(w_g, p, b):.3f}")
    print("  per regime (resid/ZOH):  Ntrain   diagAR   global   own-regime   "
          "wrong-regime(best,worst)"
          "   global excess over own   offdiag(own)")
    for k in range(nreg):
        mt = te & (lt == k)
        zk = zoh_of(mt)
        own = res(x[mt] @ w_k[k], yt[mt]) / zk
        glo = res(yh_g[mt], yt[mt]) / zk
        wrong = [res(x[mt] @ w_k[j], yt[mt]) / zk for j in range(nreg) if j != k]
        n_k = int(np.sum(tr & pure & (lt == k)))
        print(f"     regime {k}: {n_k:7d}   {e_ar[k] / zk:.4f}   {glo:.4f}   "
              f"{own:.4f}       ({min(wrong):.3f},{max(wrong):.3f})        "
              f"{100 * (glo / own - 1):+6.1f}%              {offdiag_frac(w_k[k], p, b):.3f}")
    print(f"  done {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
