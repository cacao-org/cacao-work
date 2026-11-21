"""Brighter-star limit: plain vs differenced lagged-A IV as the WFS A noise goes to zero.

Prints, per case and control law, the median bias (standard error over runs), the per-mode
median error and the usable part of the DM2 command (percent of its variance), for psi built
with the recipe's fitted Mab0 and with the true Mab.
"""
import json
from multiprocessing import Pool

import numpy as np

import diff_why as W

CASES = [("reference", 0.002, 0.002), ("noises /4", 0.0005, 0.0005),
         ("noises /8", 0.00025, 0.00025), ("noises /16", 0.000125, 0.000125),
         ("no WFS A noise, B ref", 0.0, 0.002), ("no WFS A noise, B /4", 0.0, 0.0005)]
SHOW = ("levels, lags 1-8", "rho=0.9", "first difference")
NSEED = 12

if __name__ == "__main__":
    tasks = []
    for name, sa, sb in CASES:
        for pred in (False, True):
            kw = dict(c_hi=0.6, sig_nA=sa, sig_nB=sb, t_sci=5.0, predictive=pred)
            tasks += [(300 + s, kw) for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(W.one, tasks, chunksize=1)
    res, k = {}, 0
    print("median bias (se) / per-mode |err| / usable %      psi: recipe fit | true Mab")
    for name, sa, sb in CASES:
        for pred in (False, True):
            rs = allr[k : k + NSEED]
            k += NSEED
            case = f"{name}, {'pred' if pred else 'int'}"
            res[case] = {}
            print(f"\n{case}")
            for lab in SHOW:
                line = f"  {lab:18s}"
                for kind in ("fit", "oracle"):
                    key = f"{kind}|{lab}"
                    m = np.array([r[key]["med"] for r in rs])
                    a = float(np.mean([r[key]["mae"] for r in rs]))
                    u = float(np.mean([r[key]["use"] for r in rs]))
                    se = float(m.std() / np.sqrt(NSEED))
                    res[case][key] = [float(m.mean()), se, a, u]
                    line += f"  {m.mean():+6.1f} ({se:.1f}) / {a:4.1f} / {u:6.3f}  |"
                print(line)
    json.dump(res, open("diff_bright.json", "w"), indent=1)
