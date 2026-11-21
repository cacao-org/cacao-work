"""How should psi = A Mab0 be built for the differenced lagged-A estimate?

  fit    : Mab0 = ridge fit of (B - Mdb_tool D) on A, in levels (the recipe of iv_variants.py)
  oracle : the true Mab
  dfit   : the same ridge fit made on first-differenced data
  iter   : 'fit', then one refinement pass: rebuild B - g_iv D with the first IV gains, refit
  diag   : 'fit' with only the matching WFS A mode kept (no cross terms)
All are then used in the same differenced 2SLS (instruments: differenced psi at lags 2-9).
"""
import json
from multiprocessing import Pool

import numpy as np

import estimators as E
from diff_why import cen, ridge_w
from sim import simulate

KINDS = ("fit", "oracle", "dfit", "iter", "diag")
CASES = [("reference", 0.002), ("noises /4", 0.0005), ("noises /8", 0.00025),
         ("noises /16", 0.000125)]
NSEED = 12
LO = 4


def iv_diff(Bc, Dc, psi, lags=range(2, 10)):
    """Differenced 2SLS per mode; returns the DM2 gain estimates."""
    y_a, p_a, d_a = (np.diff(x, axis=0) for x in (Bc, psi, Dc))
    t = np.arange(10, len(y_a))
    gh = np.zeros(Bc.shape[1])
    for i in range(Bc.shape[1]):
        Q, _ = np.linalg.qr(np.column_stack([p_a[t - l, i] for l in lags]))
        X = np.column_stack([p_a[t, i], d_a[t, i]])
        Xh = Q @ (Q.T @ X)
        gh[i] = np.linalg.solve(Xh.T @ X, Xh.T @ y_a[t, i])[1]
    return gh


def one(args):
    seed, kw = args
    sim = simulate(seed, **kw)
    g, gA = sim["gB"], sim["gA"]
    Ae, Be, De = E.sync_exact(sim)
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = cen(Be), cen(De), cen(Ae)
    Bol = Bc - Dc @ tle["Mdb"].T
    W = ridge_w(Ac, Bol)
    idx = np.arange(40)
    psis = dict(fit=Ac @ W, oracle=Ac[:, :40] * (g / gA),
                dfit=Ac @ ridge_w(np.diff(Ac, axis=0), np.diff(Bol, axis=0)),
                diag=Ac[:, :40] * W[idx, idx])
    out = {}
    for kind in KINDS:
        if kind == "iter":
            gh = iv_diff(Bc, Dc, Ac @ ridge_w(Ac, Bc - Dc * out_g))
        else:
            gh = iv_diff(Bc, Dc, psis[kind])
            if kind == "fit":
                out_g = gh
        r = gh[LO:] / g[LO:] - 1.0
        out[kind] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    return out


if __name__ == "__main__":
    tasks = []
    for name, sn in CASES:
        for pred in (False, True):
            kw = dict(c_hi=0.6, sig_nA=sn, sig_nB=sn, t_sci=5.0, predictive=pred)
            tasks += [(300 + s, kw) for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res, k = {}, 0
    print("differenced form: median bias (se) / per-mode |err|, percent")
    print(f"{'case':22s}" + "".join(f"{kd:>22s}" for kd in KINDS))
    for name, _ in CASES:
        for pred in (False, True):
            rs = allr[k : k + NSEED]
            k += NSEED
            case = f"{name}, {'pred' if pred else 'int'}"
            res[case] = {}
            line = f"{case:22s}"
            for kd in KINDS:
                v = np.array([r[kd] for r in rs])
                m, se, a = v[:, 0].mean(), v[:, 0].std() / np.sqrt(NSEED), v[:, 1].mean()
                res[case][kd] = [float(m), float(se), float(a)]
                line += f"   {m:+5.1f} ({se:.1f}) / {a:4.1f}  "
            print(line)
    json.dump(res, open("diff_psi.json", "w"), indent=1)
