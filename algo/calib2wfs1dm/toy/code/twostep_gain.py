"""Two-step calibration with step 2 run at a reduced stage-2 gain (integrator only).

Step 1 (stage 2 open) gives Mab1; step 2 uses psi = A Mab1 at the listed gain and leak.
Estimators are those of twostep.py; `og` is the WFS B gain during step 1 (same / lower).
"""
import json
from multiprocessing import Pool

import numpy as np

from twostep import AEST, NSEED, one, stat

GROWS = ("fixed, IV", "fixed, IV diff", "scale, IV", "scale, IV diff", "true Mab, IV",
         "true Mab, IV diff", "recipe, IV", "recipe, IV diff")
NOISE = [("reference", 0.002, 0.002), ("noises /16", 0.000125, 0.000125),
         ("no WFS A noise", 0.0, 0.002)]
GAINS = (0.35, 0.1, 0.05, 0.02)
LEAKS = (0.98, 0.999)

if __name__ == "__main__":
    tasks, labels = [], []
    for og in ("same", "lower"):
        for name, sa, sb in NOISE:
            for leak in LEAKS:
                for gain in GAINS:
                    kw = dict(c_hi=0.6, sig_nA=sa, sig_nB=sb, t_sci=5.0, predictive=False,
                              gain2=gain, leak2=leak)
                    labels.append((og, name, leak, gain))
                    tasks += [(s, kw, og) for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    for ci, (og, name, leak, gain) in enumerate(labels):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        if gain == GAINS[0]:
            print(f"\n=== step-1 WFS B gain {og} | {name} | leak {leak} ===")
            print(f"{'gain':>6s} " + "".join(f"{k:>19s}" for k in GROWS + AEST))
        line = f"{gain:6.2f} "
        rec = {}
        for k in GROWS + tuple("mda|" + a for a in AEST):
            m, se, a = stat(rs, k)
            rec[k] = [float(m), float(se), float(a)]
            line += f"   {m:+6.1f} / {a:5.1f}   "
        res[f"{og}|{name}|{leak}|{gain}"] = rec
        print(line)
    json.dump(res, open("twostep_gain.json", "w"), indent=1)
