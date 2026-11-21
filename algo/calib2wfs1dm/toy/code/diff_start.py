"""Does the lagged-A estimate depend on the gain used to build psi?

psi = A Mab0, where Mab0 is a ridge fit of (B - Mdb0 D) on A. The starting matrix Mdb0 is
  tool : the shipped W(z) estimate (the recipe of iv_variants.py)
  s    : s times the true gain, for s = 0.5, 1.0, 1.5 (starting points wrong by -50%, 0, +50%)
The estimate should not remember where it started. Plain and differenced forms are compared.
"""
import json
from multiprocessing import Pool

import numpy as np

import estimators as E
from diff_why import analyse, cen, ridge_w
from sim import simulate

STARTS = ("tool", 0.5, 1.0, 1.5)
FORMS = [("levels, lags 1-8", 0.0, range(1, 9)), ("rho=0.9", 0.9, range(2, 10)),
         ("rho=0.99", 0.99, range(2, 10)), ("first difference", 1.0, range(2, 10))]
CASES = [("reference, 5 s, int", 0.002), ("noises /4, 5 s, int", 0.0005)]
NSEED = 12


def one(args):
    seed, kw = args
    sim = simulate(seed, **kw)
    g, gA, c = sim["gB"], sim["gA"], sim["comp"]
    Ae, Be, De, bphi, bu, bn, bdm = E.sync_exact(sim, extra=[c[k] for k in ("phi", "u", "n", "dm")])
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = cen(Be), cen(De), cen(Ae)
    comp = dict(phi=cen(bphi), u=cen(bu), n=cen(bn), lag=cen(bdm) - Dc * g)
    idx = np.arange(40)
    out = {"tool start": 100 * float(np.median(np.diag(tle["Mdb"])[4:] / g[4:]) - 1)}
    for s in STARTS:
        Bol = Bc - (Dc @ tle["Mdb"].T if s == "tool" else Dc * (s * g))
        W = ridge_w(Ac, Bol)
        psi, cstar = Ac @ W, g / (gA * W[idx, idx])
        for label, rho, lags in FORMS:
            r = analyse(Bc, Dc, psi, cstar, comp, g, rho, lags)
            out[f"{s}|{label}"] = (r["med"], r["mae"])
    return out


if __name__ == "__main__":
    tasks = []
    for name, sn in CASES:
        kw = dict(c_hi=0.6, sig_nA=sn, sig_nB=sn, t_sci=5.0, predictive=False)
        tasks += [(300 + s, kw) for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    for ci, (name, _) in enumerate(CASES):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        res[name] = {}
        tool = float(np.mean([r["tool start"] for r in rs]))
        print(f"\n=== {name} ===   (shipped W(z) estimate: {tool:+.1f}%)")
        print(f"{'start':>8s} " + "".join(f"{f[0]:>24s}" for f in FORMS))
        for s in STARTS:
            line = f"{str(s):>8s} "
            for label, _, _ in FORMS:
                v = np.array([r[f"{s}|{label}"] for r in rs])
                m, se, mae = v[:, 0].mean(), v[:, 0].std() / np.sqrt(len(rs)), v[:, 1].mean()
                res[name][f"{s}|{label}"] = [float(m), float(se), float(mae)]
                line += f"   {m:+6.1f} ({se:.1f}) / {mae:4.1f}  "
            print(line)
    json.dump(res, open("diff_start.json", "w"), indent=1)
