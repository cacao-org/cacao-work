"""Passive estimate on the low-order modes while a stage-3 (LLOWFS) loop drives DM2.
Nothing is injected: the stage-3 loop simply runs, with a zero-point-offset gain mismatch.
Compares the shipped whitening with the differenced lagged-A IV, without and with the logged
stage-3 command as an extra (exogenous) regressor."""
import json
import numpy as np
from multiprocessing import Pool
from sim import simulate
import estimators as E
from iv_variants import kclass

LOM = 4

def one(args):
    seed, kw = args
    sim = simulate(seed, sig_nA=0.002, sig_nB=0.002, c_hi=0.6, lo_modes=LOM, **kw); g = sim["gB"]
    Ae, Be, De, D3 = E.sync_exact(sim, extra=[sim["D3e"]])
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac, D3c = Be - Be.mean(0), De - De.mean(0), Ae - Ae.mean(0), D3 - D3.mean(0)
    Saa = Ac.T @ Ac
    psi = Ac @ np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), Ac.T @ (Bc - Dc @ tle["Mdb"].T))
    dpsi, dB, dD, dD3 = (np.diff(x, axis=0) for x in (psi, Bc, Dc, D3c))
    N = len(dB); t = np.arange(10, N)
    out = {"wz": np.diag(tle["Mdb"])[:LOM] / g[:LOM], "iv": np.zeros(LOM),
           "iv3": np.zeros(LOM), "c3": np.zeros(LOM),
           "wz_hi": np.median(np.diag(tle["Mdb"])[LOM:] / g[LOM:]), "iv_hi": 0.0}
    hi = []
    for i in range(40):
        Zp = [dpsi[t - l, i] for l in range(2, 10)]
        b0 = kclass(dB[t, i], np.column_stack([dpsi[t, i], dD[t, i]]), np.column_stack(Zp), False)
        if i < LOM:
            out["iv"][i] = b0[1] / g[i]
            b3 = kclass(dB[t, i], np.column_stack([dpsi[t, i], dD[t, i], dD3[t, i]]),
                        np.column_stack(Zp + [dD3[t, i]]), False)
            out["iv3"][i] = b3[1] / g[i]; out["c3"][i] = b3[2]
        else:
            hi.append(b0[1] / g[i])
    out["iv_hi"] = float(np.median(hi))
    out["expect"] = g[:LOM] - kw["lo_zpo_gain"]
    return out

if __name__ == "__main__":
    res = {}
    with Pool(12) as pool:
        for label, kw in (("ZPO at calibration gain 1.0 (mismatch)", dict(lo_zpo_gain=1.0)),
                          ("ZPO matched to the true gain 0.70", dict(lo_zpo_gain=0.70)),
                          ("mismatch, stage-3 gain x4", dict(lo_zpo_gain=1.0, lo_gain=0.8)),
                          ("mismatch, 20 s window", dict(lo_zpo_gain=1.0, t_sci=20.0))):
            rs = pool.map(one, [(400 + s, kw) for s in range(12)])
            m = lambda k: np.mean([r[k] for r in rs], 0)
            sd = lambda k: np.std([r[k] for r in rs], 0)
            res[label] = {k: np.asarray(m(k)).tolist() for k in rs[0]}
            res[label]["iv3_sd"] = sd("iv3").tolist()
            print(f"== {label}")
            print("   shipped W(z), modes 0-3           :", np.round(m("wz"), 2),
                  "| modes>=4:", round(float(m("wz_hi")), 2))
            print("   differenced lagged-A IV           :", np.round(m("iv"), 2),
                  "| modes>=4:", round(float(m("iv_hi")), 2))
            print("   same + logged stage-3 cmd regressor:", np.round(m("iv3"), 2), "+/-",
                  np.round(sd("iv3"), 2))
            print("   coefficient on stage-3 cmd        :", np.round(m("c3"), 2), "expected",
                  np.round(m("expect"), 2))
    json.dump(res, open("iv_lowfs.json", "w"), indent=1)
