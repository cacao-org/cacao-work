"""Does a longer step 1 (stage 2 open) improve the step-2 estimates?

Step 2 is a 5 s window with a near-pure integrator (leak 0.999) at the listed gain. Step 1 lasts
5 s or 20 s. Estimators are those of twostep.py.
"""
import json
from multiprocessing import Pool

from twostep import NSEED, one, stat

ROWS = ("fixed, IV", "scale, IV", "scale, IV diff", "true Mab, IV", "true Mab, IV diff",
        "mda|Mba1, IV")
NOISE = [("reference", 0.002, 0.002), ("noises /16", 0.000125, 0.000125),
         ("no WFS A noise", 0.0, 0.002)]

if __name__ == "__main__":
    tasks, labels = [], []
    for name, sa, sb in NOISE:
        for gain in (0.35, 0.05, 0.02):
            for t1 in (5.0, 20.0, 60.0):
                kw = dict(c_hi=0.6, sig_nA=sa, sig_nB=sb, t_sci=5.0, predictive=False,
                          gain2=gain, leak2=0.999, t1=t1)
                labels.append((name, gain, t1))
                tasks += [(s, kw, "same") for s in range(NSEED)]
    order = sorted(range(len(tasks)), key=lambda j: -tasks[j][1]["t1"])
    with Pool(20) as pool:
        done = pool.map(one, [tasks[j] for j in order], chunksize=1)
    allr = [None] * len(tasks)
    for j, r in zip(order, done):
        allr[j] = r
    res = {}
    print(f"{'noise':>16s} {'gain':>5s} {'step 1':>7s} " + "".join(f"{k:>20s}" for k in ROWS))
    for ci, (name, gain, t1) in enumerate(labels):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        line = f"{name:>16s} {gain:5.2f} {t1:5.0f} s "
        rec = {}
        for k in ROWS:
            m, se, a = stat(rs, k)
            rec[k] = [float(m), float(se), float(a)]
            line += f"   {m:+6.1f} / {a:5.1f}    "
        res[f"{name}|{gain}|{t1}"] = rec
        print(line)
    json.dump(res, open("twostep_t1.json", "w"), indent=1)
