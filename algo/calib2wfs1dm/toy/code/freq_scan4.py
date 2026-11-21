"""Fourth frequency scan: windows made of whole WFS B frames.

With whole WFS B frames, B and the DM2 position need no sub-frame model: the DM2 response is
only needed at WFS B frame resolution, which is what a measured step response gives. Only WFS A
frames can be cut by a window edge; then their noise is shared by neighbouring windows and the
instruments must start at lag 3.
"""
import json
import sys
from multiprocessing import Pool

import numpy as np

import estfreq as E
from freq_scan3 import CASES
from simfreq import simulate

LO, NSEED, FS = 4, 12, 24000.0
# name, window mode, sub-frame order for cut frames, first instrument lag (None = automatic)
VARIANTS = [("A or slow frame (as tested)", "slow", 0, 2),
            ("B frames >= 1 A frame", "bwin1", 0, None),
            ("B frames >= 2 A frames", "bwin2", 0, None), ("same, linear", "bwin2", 1, None),
            ("B frames >= 3 A frames", "bwin3", 0, None)]


def one(args):
    seed, na, nb, off, tsci = args
    sim = simulate(seed, fs=FS, na_t=na, nb_t=nb, b_off=off, t_sci=tsci)
    g = sim["gB"]
    out = {}
    for name, mode, order, l0 in VARIANTS:
        A, B, D, wl = E.align(sim, mode, order=order)
        if l0 is None:  # lag 2 only if every WFS A frame lies wholly inside one window
            l0 = 2 if (wl % na == 0 and off % na == 0) else 3
        est, use = E.estimate(A, B, D, 0.8 * g, range(l0, l0 + 8))
        r = est["IV diff"][LO:] / g[LO:] - 1.0
        out[name] = (100 * np.median(r), 100 * np.median(np.abs(r)), FS / wl, l0)
    return out


if __name__ == "__main__":
    tsci = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    tasks = [(300 + s, na, nb, off, tsci) for _, na, nb, off in CASES for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    print(f"differenced lagged-A, toy model, {tsci:g} s windows, {NSEED} runs per case")
    print("bias of the median (standard error) / per-mode median error [%]"
          " @ timeline rate, first lag\n")
    print(f"{'WFS A / WFS B':40s}" + "".join(f"{v[0]:>32s}" for v in VARIANTS))
    for ci, (name, na, nb, off) in enumerate(CASES):
        rs = allr[ci * NSEED:(ci + 1) * NSEED]
        line, res[name] = f"{name:40s}", {}
        for vn, _, _, _ in VARIANTS:
            v = np.array([r[vn] for r in rs])
            m, se, a = v[:, 0].mean(), v[:, 0].std() / np.sqrt(NSEED), v[:, 1].mean()
            res[name][vn] = [float(m), float(se), float(a), float(v[0, 2]), int(v[0, 3])]
            line += f"  {m:+6.1f} ({se:.1f}) / {a:4.1f} @{v[0, 2]:4.0f} L{int(v[0, 3])}  "
        print(line)
    worst = {vn: max(abs(res[c][vn][0]) for c in res) for vn, _, _, _ in VARIANTS}
    print("\nlargest |bias| over all cases: "
          + ", ".join(f"{k}: {v:.1f}%" for k, v in worst.items()))
    json.dump(res, open(f"freq_scan4_{tsci:g}s.json", "w"), indent=1)
