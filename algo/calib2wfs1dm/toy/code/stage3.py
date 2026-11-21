"""Unlogged stage-3 channel on DM2 with a zero-point-offset gain mismatch: effect on low-order
gain estimates, and what adding the stage-3 command as a regressor recovers."""
import sys
import numpy as np
from multiprocessing import Pool
from sim import simulate
import estimators as E

LOM = 4

def one(args):
    seed, kw = args
    sim = simulate(seed, sig_nA=0.002, sig_nB=0.002, c_hi=0.6, lo_modes=LOM, **kw)
    g = sim["gB"]
    A, B, D, D3 = E.sync_exact(sim, extra=[sim["D3e"]])
    D3 = D3[:, :LOM]
    out = {}
    tl = E.est_tool(A, B, D)
    out["wz"] = np.diag(tl["Mdb"])[:LOM] / g[:LOM]
    out["wz_hi"] = np.median(np.diag(tl["Mdb"])[LOM:] / g[LOM:])
    Dx = np.hstack([D, D3])
    tl2 = E.est_tool(A, B, Dx)
    out["wz+d3"] = np.diag(tl2["Mdb"][:, :40])[:LOM] / g[:LOM]
    out["wz+d3_c3"] = np.array([tl2["Mdb"][i, 40 + i] for i in range(LOM)])
    out["d3_rms"] = sim["D3e"][:, :LOM].std(0)
    out["d_rms"] = sim["D"][:, :LOM].std(0)
    out["b_rms"] = sim["B"][:, :LOM].std(0)
    out["g"] = g[:LOM]
    return out

if __name__ == "__main__":
    import json
    dump = {}
    for label, kw in (("ZPO at calibration gain 1.0 (mismatch)", dict(lo_zpo_gain=1.0)),
                      ("ZPO scaled by true gain 0.70 (matched)", dict(lo_zpo_gain=0.70)),
                      ("mismatch, stage-3 gain x2", dict(lo_zpo_gain=1.0, lo_gain=0.4)),
                      ("mismatch, stage-3 gain x4", dict(lo_zpo_gain=1.0, lo_gain=0.8))):
        with Pool(8) as pool:
            res = pool.map(one, [(200 + s, kw) for s in range(8)])
        m = lambda k: np.mean([r[k] for r in res], 0)
        print(f"== {label}")
        print("   stage-3 command rms:", np.round(m("d3_rms"), 4),
              " stage-2 command rms:", np.round(m("d_rms"), 4),
              " B rms:", np.round(m("b_rms"), 4))
        print("   W(z), D only            g_hat/g modes 0-3:", np.round(m("wz"), 2),
              " | modes>=4:", round(float(m("wz_hi")), 3))
        print("   W(z), D + stage-3 cmd   g_hat/g modes 0-3:", np.round(m("wz+d3"), 2))
        print("   coefficient on stage-3 cmd (expect gB - g_zpo):", np.round(m("wz+d3_c3"), 2),
              " expected:", np.round(m("g") - kw["lo_zpo_gain"], 2))
        dump[label] = dict(wz=m("wz").tolist(), wz_d3=m("wz+d3").tolist(),
                           c3=m("wz+d3_c3").tolist(),
                           expect=(m("g") - kw["lo_zpo_gain"]).tolist(), wz_hi=float(m("wz_hi")),
                           d3_rms=m("d3_rms").tolist())
    json.dump(dump, open("stage3.json", "w"), indent=1)
