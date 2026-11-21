"""Second frequency scan: longer common windows for clocks that cannot be nested.

Window = N consecutive exposures of the slower sensor (N = 1, 2, 3). With N > 1 the frames of
the other sensor that are cut by a window edge weigh less, at the price of a slower timeline.
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
    ("1 kHz / 1 kHz", 24, 24, 0),
    ("1 kHz / 1 kHz, clocks offset 1/4 frame", 24, 24, 6),
    ("1 kHz / 1 kHz, clocks offset 1/2 frame", 24, 24, 12),
    ("1 kHz / 2 kHz, clocks offset 1/4 A frame", 24, 12, 6),
    ("1 kHz / 1.5 kHz", 24, 16, 0),
    ("1 kHz / 1.846 kHz (24:13 ticks)", 24, 13, 0),
    ("1 kHz / 1.2 kHz", 24, 20, 0),
    ("1.2 kHz / 1 kHz (A faster)", 20, 24, 0),
    ("1 kHz / 2.182 kHz (24:11 ticks)", 24, 11, 5),
]
MODES = ("slow", "slow2", "slow3")


def one(args):
    seed, na, nb, off, tsci = args
    sim = simulate(seed, fs=FS, na_t=na, nb_t=nb, b_off=off, t_sci=tsci)
    g = sim["gB"]
    out = {}
    for mode in MODES:
        A, B, D, wl = E.align(sim, mode)
        est, use = E.estimate(A, B, D, 0.8 * g)
        r = est["IV diff"][LO:] / g[LO:] - 1.0
        out[mode] = (100 * np.median(r), 100 * np.median(np.abs(r)), 100 * np.median(use[LO:]),
                     FS / wl)
    return out


if __name__ == "__main__":
    tsci = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    tasks = [(300 + s, na, nb, off, tsci) for _, na, nb, off in CASES for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    print(f"differenced lagged-A, toy model, {tsci:g} s windows, {NSEED} runs per case")
    print("bias of the median (standard error) / per-mode median error [%], timeline rate\n")
    print(f"{'WFS A / WFS B':42s}" + "".join(f"{m:>30s}" for m in
                                               ("1 slow frame", "2 slow frames", "3 slow frames")))
    for ci, (name, na, nb, off) in enumerate(CASES):
        rs = allr[ci * NSEED:(ci + 1) * NSEED]
        line, res[name] = f"{name:42s}", {}
        for mode in MODES:
            v = np.array([r[mode] for r in rs])
            m, se, a = v[:, 0].mean(), v[:, 0].std() / np.sqrt(NSEED), v[:, 1].mean()
            res[name][mode] = [float(m), float(se), float(a), float(v[0, 3])]
            line += f"   {m:+6.1f} ({se:.1f}) / {a:4.1f} @{v[0, 3]:5.0f} Hz"
        print(line)
    json.dump(res, open(f"freq_scan2_{tsci:g}s.json", "w"), indent=1)
