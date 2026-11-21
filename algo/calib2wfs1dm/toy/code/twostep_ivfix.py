"""Fair test of "keep the A-to-B relationship fixed": de-noise the step-1 fit.

A least-squares fit of B on A with stage 2 open is attenuated by WFS A noise. Here Mab1 is also
fitted with WFS A at lags 1-2 as instruments (immune to white noise in A). Step 2 then holds
Mab1 fixed and regresses (B - A Mab1) on D, with A-predicted instruments, undifferenced.

Columns: step-1 fit by least squares / by instruments, for the same or a lower WFS B gain in
step 1, plus the free-scale differenced fit using the instrumented Mab1.
"""
import json
from multiprocessing import Pool

import numpy as np

import estimators as E
from diff_why import cen, ridge_w
from sim import simulate
from twostep import LO, NSEED, gains, stat

NOISE = [("reference", 0.002, 0.002), ("noises /4", 0.0005, 0.0005),
         ("noises /16", 0.000125, 0.000125), ("no WFS A noise", 0.0, 0.002)]
COLS = ("fixed | LS step 1", "fixed | IV step 1", "fixed | IV step 1, lower gain",
        "scale diff | IV step 1")


def mab_iv(A, B, nlag=2, ridge=1e-3):
    """Multivariate 2SLS of B on A with A at lags 1..nlag as instruments."""
    t = np.arange(nlag, len(A))
    Q, _ = np.linalg.qr(np.hstack([A[t - l] for l in range(1, nlag + 1)]))
    Ah = Q @ (Q.T @ A[t])
    G = Ah.T @ A[t]
    return np.linalg.solve(G + ridge * np.diag(np.diag(G)), Ah.T @ B[t])


def step1(seed, kw, t1, lower):
    kw1 = dict(kw, gain2=0.0, predictive=False, t_sci=t1)
    if lower:
        kw1.update(gB_mean=0.56, gB_slope=0.10)
    A1, B1, _ = E.sync_exact(simulate(500 + seed, **kw1))
    A1, B1 = cen(A1), cen(B1)
    return ridge_w(A1, B1), mab_iv(A1, B1)


def one(args):
    seed, kw, t1 = args
    ls_same, iv_same = step1(seed, kw, t1, False)
    _, iv_low = step1(seed, kw, t1, True)
    s2 = simulate(300 + seed, **kw)
    g = s2["gB"]
    Ae, Be, De = E.sync_exact(s2)
    Bc, Dc, Ac = cen(Be), cen(De), cen(Ae)
    est = {"fixed | LS step 1": gains(Bc, Dc, Ac @ ls_same, True, False)[0],
           "fixed | IV step 1": gains(Bc, Dc, Ac @ iv_same, True, False)[0],
           "fixed | IV step 1, lower gain": gains(Bc, Dc, Ac @ iv_low, True, False)[0],
           "scale diff | IV step 1": gains(Bc, Dc, Ac @ iv_same, False, True)[0]}
    out = {}
    for k, v in est.items():
        r = v[LO:] / g[LO:] - 1.0
        out[k] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    return out


if __name__ == "__main__":
    tasks, labels = [], []
    for name, sa, sb in NOISE:
        for pred in (False, True):
            for t1 in (5.0, 20.0):
                kw = dict(c_hi=0.6, sig_nA=sa, sig_nB=sb, t_sci=5.0, predictive=pred)
                labels.append((name, "pred" if pred else "int", t1))
                tasks += [(s, kw, t1) for s in range(NSEED)]
    order = sorted(range(len(tasks)), key=lambda j: -tasks[j][2])
    with Pool(20) as pool:
        done = pool.map(one, [tasks[j] for j in order], chunksize=1)
    allr = [None] * len(tasks)
    for j, r in zip(order, done):
        allr[j] = r
    res = {}
    print(f"{'noise':>16s} {'law':>5s} {'step 1':>7s} " + "".join(f"{k:>32s}" for k in COLS))
    for ci, (name, law, t1) in enumerate(labels):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        line = f"{name:>16s} {law:>5s} {t1:5.0f} s "
        rec = {}
        for k in COLS:
            m, se, a = stat(rs, k)
            rec[k] = [float(m), float(se), float(a)]
            line += f"        {m:+6.1f} ({se:.1f}) / {a:5.1f}    "
        res[f"{name}|{law}|{t1}"] = rec
        print(line)
    json.dump(res, open("twostep_ivfix.json", "w"), indent=1)
