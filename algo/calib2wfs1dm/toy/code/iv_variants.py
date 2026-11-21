"""Passive-only question: with no dither and no stage-3 probe, which instrument set and estimator
should the lagged-A method use, and what happens when the instruments are weak (bright star)?

Instruments tried, all strictly from the past (so independent of the current WFS A frame noise):
  psi8      : 8 past frames of the WFS-A-predicted disturbance
  psi8+c1   : the same plus 2 past frames of the logged DM1 command (long-memory instrument)
  c1x9      : 9 past frames of the logged DM1 command only
Estimators: two-stage least squares (2SLS) and LIML (less biased when instruments are weak).
"""
import json, sys
import numpy as np
from multiprocessing import Pool
from sim import simulate
import estimators as E

LO = 4

def kclass(y, X, Z, liml):
    Q, _ = np.linalg.qr(Z)
    PX, Py = Q @ (Q.T @ X), Q @ (Q.T @ y)
    k = 1.0
    if liml:
        W = np.column_stack([y, X])
        PW = Q @ (Q.T @ W)
        k = float(np.min(np.linalg.eigvals(np.linalg.solve(W.T @ W - W.T @ PW, W.T @ W)).real))
    Xk = X - k * (X - PX)            # (I - k M_Z) X
    return np.linalg.solve(Xk.T @ X, Xk.T @ y)

def one(args):
    seed, kw = args
    sim = simulate(seed, **kw); g = sim["gB"]
    Ae, Be, De = E.sync_exact(sim)
    nA, nB = len(sim["tA"]), len(sim["tB"])
    idx = np.arange(nA)[3 : min(nA, nB // 2) - 3]
    C1 = sim["C1"][idx, :40]; C1 = C1 - C1.mean(0)
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = Be - Be.mean(0), De - De.mean(0), Ae - Ae.mean(0)
    Bol = Bc - Dc @ tle["Mdb"].T
    Saa = Ac.T @ Ac
    psi = Ac @ np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), Ac.T @ Bol)
    N = len(Bc); L = 9; t = np.arange(L, N)
    dpsi, dB, dD = np.diff(psi, axis=0), np.diff(Bc, axis=0), np.diff(Dc, axis=0)
    td = np.arange(L + 1, N - 1)
    sets = {"psi8": (lambda i: [psi[t - l, i] for l in range(1, 9)], None),
            "psi8+c1": (lambda i: ([psi[t - l, i] for l in range(1, 9)]
                                   + [C1[t - l, i] for l in (1, 2)]), None),
            "diff, psi lags 2-9": (lambda i: [dpsi[td - l, i] for l in range(2, 10)], "d")}
    out = {"wz": 100 * (np.median(np.diag(tle["Mdb"])[LO:] / g[LO:]) - 1)}
    for nm, (f, mode) in sets.items():
        for liml in (False, True):
            gh = np.zeros(40)
            for i in range(40):
                if mode == "d":
                    X = np.column_stack([dpsi[td, i], dD[td, i]]); y = dB[td, i]
                else:
                    X = np.column_stack([psi[t, i], Dc[t, i]]); y = Bc[t, i]
                gh[i] = kclass(y, X, np.column_stack(f(i)), liml)[1]
            r = gh[LO:] / g[LO:] - 1
            out[f"{nm}|{'liml' if liml else '2sls'}"] = (100 * np.median(r),
                                                         100 * np.median(np.abs(r)))
    return out

if __name__ == "__main__":
    base = dict(c_hi=0.6)
    cases = [("reference", 0.002, 5.0), ("noises /2", 0.001, 5.0),
             ("noises /2", 0.001, 10.0), ("noises /2", 0.001, 20.0),
             ("noises /4", 0.0005, 5.0), ("noises /4", 0.0005, 20.0), ("noises /4", 0.0005, 40.0),
             ("WFS A noise x3", None, 5.0)]
    res = {}
    with Pool(20) as pool:
        for lab, sn, tsci in cases:
            for pred in (False, True):
                kw = dict(base, predictive=pred, t_sci=tsci)
                kw.update(dict(sig_nA=0.006, sig_nB=0.002) if sn is None
                          else dict(sig_nA=sn, sig_nB=sn))
                rs = pool.map(one, [(300 + s, kw) for s in range(12)])
                key = f"{lab}|{tsci:g} s|{'pred' if pred else 'int'}"
                res[key] = {k: (float(np.mean([r[k][0] for r in rs])),
                                float(np.std([r[k][0] for r in rs])),
                                float(np.mean([r[k][1] for r in rs]))) if k != "wz"
                            else float(np.mean([r[k] for r in rs]))
                            for k in rs[0]}
                v = res[key]
                print(f"{key:30s} W(z) {v['wz']:+6.1f} | " + " | ".join(
                    f"{k}: {v[k][0]:+5.1f}/{v[k][1]:3.1f}/{v[k][2]:4.1f}" for k in v if k != "wz"),
                    flush=True)
    json.dump(res, open("iv_variants.json", "w"), indent=1)
