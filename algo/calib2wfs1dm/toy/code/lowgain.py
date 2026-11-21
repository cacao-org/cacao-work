"""Hybrid: one window with the stage-2 loop closed at a reduced gain.

For each stage-2 integrator gain (and leak) the script reports, on a single 5 s window:
  resid        : wavefront left in the 40 stage-2 modes, RMS relative to the nominal-gain loop
                 (the toy WFS is linear; on a pyramid this ratio sets how far the optical gain
                 is from its operating value)
  usable       : part of the DM2 command that past WFS A frames predict and that is not a scaled
                 copy of psi, percent of the DM2 variance (undifferenced)
  g estimates  : shipped W(z); plain least squares; lagged-A IV, undifferenced and differenced,
                 with the recipe's fitted Mab0 and with the true Mab
  c            : the A-to-B scale returned by the undifferenced true-Mab IV fit (truth 1)
  Mda          : shipped joint fit, and A on (B, D) with A at lags 1-8 as instruments
"""
import json
from multiprocessing import Pool

import numpy as np

import estimators as E
from diff_why import cen, ridge_w
from sim import simulate
from twostep import gains, lagmat, tsls

LO = 4
NSEED = 12
GAINS = (0.35, 0.2, 0.1, 0.05, 0.02, 0.01)
LEAKS = (0.98, 0.999)
NOISE = [("reference", 0.002, 0.002), ("noises /4", 0.0005, 0.0005),
         ("noises /16", 0.000125, 0.000125), ("no WFS A noise", 0.0, 0.002)]
KEYS = ("W(z)", "LS", "recipe IV", "recipe IV diff", "true IV", "true IV diff", "c",
        "Mda tool", "Mda IV")


def one(args):
    seed, kw = args
    sim = simulate(300 + seed, **kw)
    g, gA, c = sim["gB"], sim["gA"], sim["comp"]
    wf = (c["phi"] + c["u"] + c["dm"]) / g
    resid = float(np.sqrt(np.sum(wf.var(0))))
    if kw["gain2"] == 0.0:
        return {"resid": resid}
    Ae, Be, De = E.sync_exact(sim)
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = cen(Be), cen(De), cen(Ae)
    psi_r = Ac @ ridge_w(Ac, Bc - Dc @ tle["Mdb"].T)
    psi_0 = Ac[:, :40] * (g / gA)
    est = {"W(z)": np.diag(tle["Mdb"]), "LS": np.diag(E.est_ols(Ae, Be, De)["Mdb"])}
    est["recipe IV"] = gains(Bc, Dc, psi_r, False, False)[0]
    est["recipe IV diff"] = gains(Bc, Dc, psi_r, False, True)[0]
    g0, c0 = gains(Bc, Dc, psi_0, False, False)
    est["true IV"] = g0
    est["true IV diff"] = gains(Bc, Dc, psi_0, False, True)[0]
    out = {"resid": resid}
    for k, v in est.items():
        r = v[LO:] / g[LO:] - 1.0
        out[k] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    out["c"] = (100 * np.median(c0[LO:] - 1.0), 100 * np.median(np.abs(c0[LO:] - 1.0)))
    t = np.arange(10, len(Ac))
    mda_iv, use = np.zeros(40), np.zeros(40)
    for i in range(40):
        Z = lagmat(Ac[:, i], t, range(1, 9))
        mda_iv[i] = -tsls(Ac[t, i], np.column_stack([Bc[t, i], Dc[t, i]]), Z)[1]
        Q, _ = np.linalg.qr(lagmat(psi_r[:, i], t, range(1, 9)))
        ph, dh = Q @ (Q.T @ psi_r[t, i]), Q @ (Q.T @ Dc[t, i])
        dp = dh - ph * (ph @ dh) / (ph @ ph)
        use[i] = (dp @ dp) / (Dc[t, i] @ Dc[t, i])
    for k, v in (("Mda tool", np.diag(E.est_mda(Ae, Be, De)[0][:40, :40])), ("Mda IV", mda_iv)):
        r = v[LO:] / gA - 1.0
        out[k] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    out["usable"] = float(100 * np.median(use[LO:]))
    return out


if __name__ == "__main__":
    tasks, labels = [], []
    for name, sa, sb in NOISE:
        for leak in LEAKS:
            for gain in (0.0,) + GAINS:
                kw = dict(c_hi=0.6, sig_nA=sa, sig_nB=sb, t_sci=5.0, gain2=gain, leak2=leak)
                labels.append((name, leak, gain))
                tasks += [(s, kw) for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res, ref = {}, {}
    for ci, (name, leak, gain) in enumerate(labels):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        resid = float(np.mean([r["resid"] for r in rs]))
        if gain == 0.0:
            ref[(name, leak, "open")] = resid
            continue
        if gain == GAINS[0]:
            ref[(name, leak)] = resid
            print(f"\n=== {name} | leak {leak} ===   (stage 2 open: resid "
                  f"{ref[(name, leak, 'open')] / resid:.2f} x nominal)")
            print(f"{'gain':>6s} {'resid':>6s} {'usable':>7s}  "
                  + "".join(f"{k:>18s}" for k in KEYS))
        line = f"{gain:6.2f} {resid / ref[(name, leak)]:6.2f}"
        line += f" {np.mean([r['usable'] for r in rs]):7.2f}  "
        rec = {"resid": resid / ref[(name, leak)]}
        for k in KEYS:
            v = np.array([r[k] for r in rs])
            rec[k] = [float(v[:, 0].mean()), float(v[:, 0].std() / np.sqrt(NSEED)),
                      float(v[:, 1].mean())]
            line += f"  {rec[k][0]:+6.1f} / {rec[k][2]:5.1f}   "
        res[f"{name}|{leak}|{gain}"] = rec
        print(line)
    json.dump(res, open("lowgain.json", "w"), indent=1)
