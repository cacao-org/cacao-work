"""Third frequency scan: what makes the estimator independent of the loop clocks.

Three knobs on the common timeline:
    window   N consecutive exposures of the slower sensor
    order    0 = frames cut by a window edge are split by overlap; 1 = linear inside a frame
    lags     first instrument lag 2 (valid when no WFS A frame is cut) or 3 (always valid)
"""
import json
import sys
from multiprocessing import Pool

import numpy as np

import estfreq as E
from simfreq import simulate

LO, NSEED, FS = 4, 12, 24000.0
CASES = [
    ("1 kHz / 2 kHz", 24, 12, 0),
    ("1 kHz / 3 kHz", 24, 8, 0),
    ("500 Hz / 2 kHz", 48, 12, 0),
    ("2 kHz / 1 kHz (A faster)", 12, 24, 0),
    ("1 kHz / 1 kHz", 24, 24, 0),
    ("1 kHz / 1 kHz, clocks offset 1/4 frame", 24, 24, 6),
    ("1 kHz / 1 kHz, clocks offset 1/2 frame", 24, 24, 12),
    ("1 kHz / 2 kHz, clocks offset 1/4 A frame", 24, 12, 6),
    ("1 kHz / 1.5 kHz", 24, 16, 0),
    ("1 kHz / 1.846 kHz (24:13 ticks)", 24, 13, 0),
    ("1 kHz / 1.2 kHz", 24, 20, 0),
    ("1.2 kHz / 1 kHz (A faster)", 20, 24, 0),
    ("1.846 kHz / 1 kHz (A faster, 13:24)", 13, 24, 7),
    ("1 kHz / 2.182 kHz (24:11), offset", 24, 11, 5),
]
VARIANTS = [("N=1, split, lag 2", "slow", 0, 2), ("N=2, split, lag 2", "slow2", 0, 2),
            ("N=2, linear, lag 2", "slow2", 1, 2), ("N=2, linear, lag 3", "slow2", 1, 3),
            ("N=3, linear, lag 3", "slow3", 1, 3)]


def one(args):
    seed, na, nb, off, tsci = args
    sim = simulate(seed, fs=FS, na_t=na, nb_t=nb, b_off=off, t_sci=tsci)
    g = sim["gB"]
    out = {}
    for name, mode, order, l0 in VARIANTS:
        A, B, D, wl = E.align(sim, mode, order=order)
        est, use = E.estimate(A, B, D, 0.8 * g, range(l0, l0 + 8))
        r = est["IV diff"][LO:] / g[LO:] - 1.0
        out[name] = (100 * np.median(r), 100 * np.median(np.abs(r)))
    return out


if __name__ == "__main__":
    tsci = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    tasks = [(300 + s, na, nb, off, tsci) for _, na, nb, off in CASES for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    print(f"differenced lagged-A, toy model, {tsci:g} s windows, {NSEED} runs per case")
    print("bias of the median (standard error) / per-mode median error [%]\n")
    print(f"{'WFS A / WFS B':40s}" + "".join(f"{v[0]:>24s}" for v in VARIANTS))
    for ci, (name, na, nb, off) in enumerate(CASES):
        rs = allr[ci * NSEED:(ci + 1) * NSEED]
        line, res[name] = f"{name:40s}", {}
        for vn, _, _, _ in VARIANTS:
            v = np.array([r[vn] for r in rs])
            m, se, a = v[:, 0].mean(), v[:, 0].std() / np.sqrt(NSEED), v[:, 1].mean()
            res[name][vn] = [float(m), float(se), float(a)]
            line += f"   {m:+6.1f} ({se:.1f}) / {a:4.1f}  "
        print(line)
    worst = {vn: max(abs(res[c][vn][0]) for c in res) for vn, _, _, _ in VARIANTS}
    print("\nlargest |bias| over all cases: "
          + ", ".join(f"{k}: {v:.1f}%" for k, v in worst.items()))
    json.dump(res, open(f"freq_scan3_{tsci:g}s.json", "w"), indent=1)
