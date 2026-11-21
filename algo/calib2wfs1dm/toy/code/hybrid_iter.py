"""Can a single reduced-gain window stand on its own?

Iterate, in one window and undifferenced:
    Mab0 = ridge fit of (B - g D) on A;   psi = A Mab0;   g = lagged-A IV of B on (psi, D)
from three starting gains (the shipped W(z) estimate, 0.5 x truth, 1.5 x truth), four passes.
Reported: median bias / per-mode error after the last pass, and the spread between the three
starting points (a converged estimate does not remember where it started).
"""
import json
from multiprocessing import Pool

import numpy as np

import estimators as E
from diff_why import cen, ridge_w
from sim import simulate
from twostep import LO, NSEED, gains

NOISE = [("reference", 0.002, 0.002), ("noises /16", 0.000125, 0.000125),
         ("no WFS A noise", 0.0, 0.002)]
GAINS = (0.35, 0.2, 0.1, 0.05, 0.02)
LEAKS = (0.98, 0.999)
STARTS = ("tool", 0.5, 1.5)
NPASS = 4


def one(args):
    seed, kw = args
    sim = simulate(300 + seed, **kw)
    g, gA = sim["gB"], sim["gA"]
    Ae, Be, De = E.sync_exact(sim)
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = cen(Be), cen(De), cen(Ae)
    out, last = {}, []
    for s in STARTS:
        gk = np.diag(tle["Mdb"]).copy() if s == "tool" else s * g
        for _ in range(NPASS):
            gk = gains(Bc, Dc, Ac @ ridge_w(Ac, Bc - Dc * gk), False, False)[0]
        r = gk[LO:] / g[LO:] - 1.0
        out[str(s)] = (100 * np.median(r), 100 * np.median(np.abs(r)))
        last.append(r)
    out["spread"] = float(100 * np.median(np.max(last, axis=0) - np.min(last, axis=0)))
    r = gains(Bc, Dc, Ac[:, :40] * (g / gA), False, False)[0][LO:] / g[LO:] - 1.0
    out["true Mab"] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    return out


if __name__ == "__main__":
    tasks, labels = [], []
    for name, sa, sb in NOISE:
        for leak in LEAKS:
            for gain in GAINS:
                kw = dict(c_hi=0.6, sig_nA=sa, sig_nB=sb, t_sci=5.0, gain2=gain, leak2=leak)
                labels.append((name, leak, gain))
                tasks += [(s, kw) for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    for ci, (name, leak, gain) in enumerate(labels):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        if gain == GAINS[0]:
            print(f"\n=== {name} | leak {leak} ===")
            print(f"{'gain':>6s} " + "".join(f"{'start ' + str(s):>20s}" for s in STARTS)
                  + f"{'spread':>9s}{'true Mab':>20s}")
        line, rec = f"{gain:6.2f} ", {}
        for k in [str(s) for s in STARTS] + ["true Mab"]:
            v = np.array([r[k] for r in rs])
            rec[k] = [float(v[:, 0].mean()), float(v[:, 1].mean())]
            if k == "true Mab":
                line += f"{np.mean([r['spread'] for r in rs]):9.1f}"
            line += f"     {rec[k][0]:+6.1f} / {rec[k][1]:5.1f}  "
        rec["spread"] = float(np.mean([r["spread"] for r in rs]))
        res[f"{name}|{leak}|{gain}"] = rec
        print(line)
    json.dump(res, open("hybrid_iter.json", "w"), indent=1)
