#!/usr/bin/env python3
"""Literal proposal: locally weighted EOF with proximity between history vectors (S-map).

w_i(q) = kappa + (1 - kappa) * exp(-theta * d(q, h_i) / dbar);  theta = 0 is the global EOF.
Usage: smap.py <data.npz> <t_train_s> <noise_frac> <sub> <nq> <metric raw|norm> [P]
"""
import sys
import time

import numpy as np

LI, LA = 2, 0.4


def main():
    name, t_tr, nf = sys.argv[1], int(float(sys.argv[2]) * 1000), float(sys.argv[3])
    sub, nq, metric = int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
    p = int(sys.argv[7]) if len(sys.argv) > 7 else 8
    t0 = time.time()
    d = np.load(name)
    a_true, lab = d["a_true"], d["lab"]
    n_t, b = a_true.shape
    idx = np.arange(p - 1, n_t - LI - 2)
    yt = (1 - LA) * a_true[idx + LI] + LA * a_true[idx + LI + 1]
    sig2 = nf * float(np.mean(np.mean((yt - a_true[idx]) ** 2, axis=0)))
    a = a_true + np.sqrt(sig2) * np.random.default_rng(11).standard_normal(a_true.shape)
    y = (1 - LA) * a[idx + LI] + LA * a[idx + LI + 1]
    x = np.hstack([a[idx - k] for k in range(p)])
    tr = np.where(idx < t_tr - LI - 2)[0][::sub]
    te_all = np.where(idx >= t_tr)[0]
    te = te_all[np.linspace(0, te_all.size - 1, nq).astype(int)]
    xs, ys = x[tr], y[tr]
    d_f = xs.shape[1]
    scale = np.ones(d_f) if metric == "raw" else 1.0 / np.tile(a[:t_tr].std(axis=0), p)
    xm = xs * scale
    xm2 = np.sum(xm**2, axis=1)
    lab_tr = lab[idx[tr]]
    zoh = float(np.sum(np.mean((a[idx[te]] - yt[te]) ** 2, axis=0)))

    g0 = xs.T @ xs
    r0 = xs.T @ ys
    eps = 1e-10 * np.trace(g0) / d_f
    w0 = np.linalg.solve(g0 + eps * np.eye(d_f), r0)
    base = float(np.sum(np.mean((x[te] @ w0 - yt[te]) ** 2, axis=0)))
    print(f"{name} metric={metric} P={p} D={d_f} Ntrain(sub {sub})={tr.size} queries={nq} "
          f"noise_frac={nf}")
    print(f"  theta=0 (global EOF on same rows): resid/ZOH={base / zoh:.4f}")

    thetas = [1.0, 2.0, 4.0, 8.0]
    kappas = [0.0, 0.1]
    err = {(th, ka): 0.0 for th in thetas for ka in kappas}
    neff = {th: [] for th in thetas}
    same = {th: [] for th in thetas}
    nn_ratio = []
    for qi, r in enumerate(te):
        q = x[r]
        qm = q * scale
        dist = np.sqrt(np.maximum(xm2 - 2.0 * (xm @ qm) + qm @ qm, 0.0))
        dbar = dist.mean()
        med = np.median(dist)
        nn_ratio.append((dist.min() / med, np.partition(dist, 100)[100] / med))
        for th in thetas:
            wk = np.exp(-th * dist / dbar)
            neff[th].append(wk.sum() ** 2 / np.sum(wk**2))
            same[th].append(np.sum(wk[lab_tr == lab[idx[r]]]) / wk.sum())
            for ka in kappas:
                w = ka + (1.0 - ka) * wk / wk.max()
                sw = np.sqrt(w)[:, None]
                xw = xs * sw
                g = xw.T @ xw
                rr = xw.T @ (ys * sw)
                wq = np.linalg.solve(g + eps * np.eye(d_f), rr)
                err[(th, ka)] += float(np.sum((q @ wq - yt[r]) ** 2))
        if qi % 25 == 0:
            print(f"   query {qi}/{nq}  {time.time() - t0:.0f}s", flush=True)
    nn = np.array(nn_ratio)
    chance = np.mean([np.mean(lab_tr == lab[idx[r]]) for r in te])
    print(f"  nearest-neighbour distance / median distance: median={np.median(nn[:, 0]):.3f}; "
          f"100th-NN / median: {np.median(nn[:, 1]):.3f}")
    for th in thetas:
        line = f"  theta={th:3.0f}: n_eff={np.median(neff[th]):8.0f}/{tr.size}  "
        line += f"same-regime weight={np.mean(same[th]):.3f} (chance {chance:.3f})  "
        for ka in kappas:
            line += f"resid/ZOH[kappa={ka}]={err[(th, ka)] / nq / zoh:8.4f}  "
        print(line)
    print(f"  done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
