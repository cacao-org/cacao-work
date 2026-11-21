#!/usr/bin/env python3
"""Causal online comparison: memory length vs regime-weighted memory (refit every 1 s).

All methods refit at each 1 s boundary from 1 s chunk Gram matrices of the past only.
Usage: mem.py <data.npz> <t_test_start_s> <noise_frac(mean)> [P]
"""
import os
import sys
import time

import numpy as np

from an import gric_anchors, wind_descriptor

LI, LA = 2, 0.4
CH = 1000


def main():
    name, c_te0, nf = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
    p = int(sys.argv[4]) if len(sys.argv) > 4 else 8
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
    d_f = x.shape[1]
    nch = n_t // CH
    chunk = idx // CH
    causal = (idx % CH) < CH - (LI + 2)  # rows whose target lies inside the same chunk
    g_c = np.zeros((nch, d_f, d_f))
    r_c = np.zeros((nch, d_f, b))
    for c in range(nch):
        m = (chunk == c) & causal
        g_c[c] = x[m].T @ x[m]
        r_c[c] = x[m].T @ y[m]
    lab_c = np.array([np.bincount(lab[c * CH : (c + 1) * CH]).argmax() for c in range(nch)])
    # causal regime descriptor: modal optical-flow wind over the chunk just ended [m/s]
    z = wind_descriptor(a, d["dx_op"], d["dy_op"], CH, c_te0 * CH) * float(d["pxs"]) * float(
        d["fs"])
    z_c = z[np.arange(1, nch + 1) * CH - 1]
    z_c[0] = z_c[1]
    eye = np.eye(d_f)

    def fit(w):
        g = np.tensordot(w, g_c, axes=(0, 0))
        r = np.tensordot(w, r_c, axes=(0, 0))
        return np.linalg.solve(g + 1e-10 * np.trace(g) / d_f * eye, r)

    def w_slide(u, n):
        w = np.zeros(nch)
        w[max(0, u - n) : u] = 1.0
        return w

    def w_oracle(u, kappa):
        w = np.zeros(nch)
        w[:u] = kappa + (1 - kappa) * (lab_c[:u] == lab_c[u - 1])
        return w

    def w_kern(u, kappa, h):
        w = np.zeros(nch)
        d2 = np.sum((z_c[:u] - z_c[u - 1]) ** 2, axis=1)
        w[:u] = kappa + (1 - kappa) * np.exp(-d2 / (2 * h * h))
        return w

    methods = {
        "sliding 16 s (current mkEOFPF memory)": lambda u: w_slide(u, 16),
        "sliding 32 s": lambda u: w_slide(u, 32),
        "sliding 64 s": lambda u: w_slide(u, 64),
        "all past, unweighted (pooled regimes)": lambda u: w_slide(u, nch),
        "all past, oracle regime weights kappa=0": lambda u: w_oracle(u, 0.0),
        "all past, oracle regime weights kappa=0.1": lambda u: w_oracle(u, 0.1),
        "all past, oracle regime weights kappa=0.3": lambda u: w_oracle(u, 0.3),
        "all past, wind-descriptor kernel h=1.5 kappa=0.1": lambda u: w_kern(u, 0.1, 1.5),
        "all past, wind-descriptor kernel h=3 kappa=0.1": lambda u: w_kern(u, 0.1, 3.0),
        "all past, wind-descriptor kernel h=3 kappa=0.3": lambda u: w_kern(u, 0.3, 3.0),
    }
    # GRIC-quantized library: K accumulators indexed by gric-cluster anchors of the descriptor
    for rlim in (1.5, 3.0):
        try:
            anchors = gric_anchors(z_c[1:c_te0], rlim, f"mem_r{rlim}")
        except Exception as exc:  # noqa: BLE001
            print("gric-cluster failed:", str(exc)[:200])
            continue
        cid = np.argmin(np.linalg.norm(z_c[:, None, :] - anchors[None], axis=2), axis=1)
        k_n = anchors.shape[0]

        def w_gric(u, kappa=0.1, h=rlim, cid=cid, anchors=anchors):
            w = np.zeros(nch)
            d2 = np.sum((anchors[cid[:u]] - z_c[u - 1]) ** 2, axis=1)
            w[:u] = kappa + (1 - kappa) * np.exp(-d2 / (2 * h * h))
            return w

        methods[f"all past, GRIC library rlim={rlim} (K={k_n}) kappa=0.1"] = w_gric

    sw = np.flatnonzero(np.diff(lab) != 0) + 1
    last_sw = np.zeros(n_t, dtype=np.int64)
    last_sw[sw] = sw
    last_sw = np.maximum.accumulate(last_sw)
    te = idx >= c_te0 * CH
    tsw = (idx - last_sw[idx]) / 1000.0
    bins = [(0, 1), (1, 2), (2, 4), (4, 8), (8, 100)]
    zoh_e = np.sum((a[idx] - yt) ** 2, axis=1)
    print(f"{name} P={p} D={d_f} noise_frac={nf}; test = chunks {c_te0}..{nch - 1}; "
          f"chunk-descriptor std within regime ~ "
          f"{np.mean([z_c[1:][lab_c[1:] == k].std(axis=0).mean() for k in range(3)]):.2f} m/s")
    print(f"  {'method':<52s} resid/ZOH   by time since wind switch [s]: "
          + "  ".join(f"{lo}-{hi}" for lo, hi in bins))
    for label, wfun in methods.items():
        e = np.zeros(idx.size)
        for u in range(c_te0, nch):
            w_f = fit(wfun(u))
            m = chunk == u
            e[m] = np.sum((x[m] @ w_f - yt[m]) ** 2, axis=1)
        tot = e[te].sum() / zoh_e[te].sum()
        parts = []
        for lo, hi in bins:
            mm = te & (tsw >= lo) & (tsw < hi)
            parts.append(f"{e[mm].sum() / zoh_e[mm].sum():6.3f}")
        print(f"  {label:<52s} {tot:8.4f}    " + "  ".join(parts), flush=True)
    print(f"  done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
