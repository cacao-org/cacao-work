"""Two-step calibration on the toy model.

Step 1: stage 2 open (gain2 = 0): fit Mab1 (B on A) and Mba1 (A on B); DM2 does not move.
Step 2: stage 2 closed at its nominal gain, independent turbulence: psi = A Mab1.

Step-2 estimators of the DM2 gain g (truth: gB of step 2):
  fixed, LS       : least squares of (B - psi) on D                (Mab held fixed)
  fixed, W(z)     : the same after the shipped AR(4) whitening
  fixed, IV       : (B - psi) on D, instruments psi at lags 1-8
  fixed, IV diff  : the same on first differences, lags 2-9
  scale, IV       : B on (psi, D): one free scale per mode on psi, instruments psi at lags 1-8
  scale, IV diff  : the same on first differences, lags 2-9
References from the step-2 window alone: the recipe's fitted Mab0 and the true Mab.

Virtual upstream response Mda_virt (truth: gA), per mode:
  tool            : the shipped joint fit A = Mba B - Mda D
  Mba1, LS        : (A - Mba1 B) on D
  Mba1, IV        : the same with A at lags 1-8 as instruments
  from scale fit  : g / (c Mab1_ii), differenced scale fit

`og` selects the WFS B gain during step 1: "same", or "lower" (mean 0.56 instead of 0.70 and a
steeper slope) to emulate a pyramid whose optical gain differs between the two regimes.
"""
import json
from multiprocessing import Pool

import numpy as np

import estimators as E
from diff_why import cen, ridge_w
from sim import simulate

LO = 4
NSEED = 12
GEST = ("fixed, LS", "fixed, W(z)", "fixed, IV", "fixed, IV diff", "scale, IV",
        "scale, IV diff", "recipe, IV", "recipe, IV diff", "true Mab, IV", "true Mab, IV diff")
AEST = ("tool", "Mba1, LS", "Mba1, IV", "from scale fit")
NOISE = [("reference", 0.002, 0.002), ("noises /4", 0.0005, 0.0005),
         ("noises /16", 0.000125, 0.000125), ("no WFS A noise", 0.0, 0.002)]


def tsls(y, X, Z):
    Q, _ = np.linalg.qr(Z)
    Xh = Q @ (Q.T @ X)
    return np.linalg.solve(Xh.T @ X, Xh.T @ y)


def lagmat(x, t, lags):
    return np.column_stack([x[t - l] for l in lags])


def gains(Bc, Dc, psi, fixed, diff):
    """Per-mode IV fit. fixed: (B - psi) on D. Otherwise B on (psi, D). Returns g, c."""
    if diff:
        Bc, Dc, psi = (np.diff(x, axis=0) for x in (Bc, Dc, psi))
    lags = range(2, 10) if diff else range(1, 9)
    t = np.arange(10, len(Bc))
    nm = Bc.shape[1]
    g, c = np.zeros(nm), np.ones(nm)
    for i in range(nm):
        Z = lagmat(psi[:, i], t, lags)
        if fixed:
            g[i] = tsls(Bc[t, i] - psi[t, i], Dc[t, i][:, None], Z)[0]
        else:
            c[i], g[i] = tsls(Bc[t, i], np.column_stack([psi[t, i], Dc[t, i]]), Z)
    return g, c


def one(args):
    seed, kw, og = args
    kw = dict(kw)
    t1 = kw.pop("t1", kw.get("t_sci", 5.0))  # length of the step-1 window [s]
    kw1 = dict(kw, gain2=0.0, predictive=False, t_sci=t1)
    if og == "lower":
        kw1.update(gB_mean=0.56, gB_slope=0.10)
    s1 = simulate(500 + seed, **kw1)
    A1, B1, _ = E.sync_exact(s1)
    A1, B1 = cen(A1), cen(B1)
    Mab1 = ridge_w(A1, B1)
    Mba1 = ridge_w(B1, A1[:, :40])

    s2 = simulate(300 + seed, **kw)
    g, gA = s2["gB"], s2["gA"]
    Ae, Be, De = E.sync_exact(s2)
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = cen(Be), cen(De), cen(Ae)
    psi1 = Ac @ Mab1
    W = ridge_w(Ac, Bc - Dc @ tle["Mdb"].T)
    idx = np.arange(40)
    est = {}
    y = Bc - psi1
    est["fixed, LS"] = np.einsum("ti,ti->i", Dc, y) / np.einsum("ti,ti->i", Dc, Dc)
    yw, dw = E.fir_valid(y, tle["taps"]), E.fir_valid(Dc, tle["taps"])
    est["fixed, W(z)"] = np.einsum("ti,ti->i", dw, yw) / np.einsum("ti,ti->i", dw, dw)
    est["fixed, IV"] = gains(Bc, Dc, psi1, True, False)[0]
    est["fixed, IV diff"] = gains(Bc, Dc, psi1, True, True)[0]
    est["scale, IV"] = gains(Bc, Dc, psi1, False, False)[0]
    g_sd, c_sd = gains(Bc, Dc, psi1, False, True)
    est["scale, IV diff"] = g_sd
    est["recipe, IV"] = gains(Bc, Dc, Ac @ W, False, False)[0]
    est["recipe, IV diff"] = gains(Bc, Dc, Ac @ W, False, True)[0]
    psi0 = Ac[:, :40] * (g / gA)
    est["true Mab, IV"] = gains(Bc, Dc, psi0, False, False)[0]
    est["true Mab, IV diff"] = gains(Bc, Dc, psi0, False, True)[0]

    mda = {"tool": np.diag(E.est_mda(Ae, Be, De)[0][:40, :40])}
    ya = Ac[:, :40] - Bc @ Mba1
    mda["Mba1, LS"] = -np.einsum("ti,ti->i", Dc, ya) / np.einsum("ti,ti->i", Dc, Dc)
    t = np.arange(10, len(Ac))
    mda["Mba1, IV"] = np.array([-tsls(ya[t, i], Dc[t, i][:, None],
                                      lagmat(Ac[:, i], t, range(1, 9)))[0] for i in range(40)])
    mda["from scale fit"] = g_sd / (c_sd * Mab1[idx, idx])

    out = {}
    for k, v in est.items():
        r = v[LO:] / g[LO:] - 1.0
        out[k] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    for k, v in mda.items():
        r = v[LO:] / gA - 1.0
        out["mda|" + k] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    g1 = s1["gB"]
    off = lambda M: np.median([np.sqrt(np.mean(np.delete(M[:, i], i) ** 2)) / abs(M[i, i])
                               for i in range(LO, 40)])
    out["q|open"] = (np.median(Mab1[idx, idx][LO:] * gA / g1[LO:]), off(Mab1))
    out["q|closed"] = (np.median(W[idx, idx][LO:] * gA / g[LO:]), off(W))
    return out


def stat(rs, key):
    v = np.array([r[key] for r in rs])
    return v[:, 0].mean(), v[:, 0].std() / np.sqrt(len(rs)), v[:, 1].mean()


if __name__ == "__main__":
    tasks, labels = [], []
    for og in ("same", "lower"):
        for name, sa, sb in NOISE:
            for pred in (False, True):
                kw = dict(c_hi=0.6, sig_nA=sa, sig_nB=sb, t_sci=5.0, predictive=pred)
                labels.append((og, name, "pred" if pred else "int"))
                tasks += [(s, kw, og) for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    for ci, (og, name, law) in enumerate(labels):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        case = f"step-1 WFS B gain {og} | {name} | {law}"
        res[case] = {}
        qo, qc = stat(rs, "q|open"), stat(rs, "q|closed")
        print(f"\n=== {case} ===")
        print(f"  Mab diag / truth, off-diag rms / diag:  step 1 open {qo[0]:.3f}, {qo[2]:.4f}"
              f"   single closed window {qc[0]:.3f}, {qc[2]:.4f}")
        for k in GEST:
            m, se, a = stat(rs, k)
            res[case][k] = [float(m), float(se), float(a)]
            print(f"  g    {k:20s} {m:+7.1f} ({se:.1f}) / {a:5.1f}")
        for k in AEST:
            m, se, a = stat(rs, "mda|" + k)
            res[case]["mda|" + k] = [float(m), float(se), float(a)]
            print(f"  Mda  {k:20s} {m:+7.1f} ({se:.1f}) / {a:5.1f}")
    json.dump(res, open("twostep.json", "w"), indent=1)
