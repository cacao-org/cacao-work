"""Does the differenced lagged-A estimator depend on the loop frequencies?

Runs the toy model (simfreq.py) for several pairs of WFS A / WFS B frame rates, aligned or not,
and applies the estimator of estfreq.py with each way of choosing the common windows.
Reference noise condition; photon-noise-like scaling of the read noise with the frame rate;
both loop gains 0.35 per own frame; loop delay two own frames.
"""
import json
import sys
from multiprocessing import Pool

import numpy as np

import estfreq as E
from simfreq import simulate

LO = 4
NSEED = 12
FS = 24000.0
# label, ticks per WFS A frame, ticks per WFS B frame, WFS B clock offset [ticks]
CASES = [
    ("1 kHz / 2 kHz (tested so far)", 24, 12, 0),
    ("1 kHz / 1 kHz", 24, 24, 0),
    ("1 kHz / 3 kHz", 24, 8, 0),
    ("1 kHz / 4 kHz", 24, 6, 0),
    ("500 Hz / 2 kHz", 48, 12, 0),
    ("2 kHz / 1 kHz (A faster)", 12, 24, 0),
    ("2 kHz / 2 kHz", 12, 12, 0),
    ("1 kHz / 1.5 kHz", 24, 16, 0),
    ("1 kHz / 1.6 kHz", 24, 15, 0),
    ("1 kHz / 2.4 kHz", 24, 10, 0),
    ("1.2 kHz / 2 kHz", 20, 12, 0),
    ("1 kHz / 2 kHz, B clock +1/8 frame of A", 24, 12, 3),
    ("1 kHz / 2 kHz, B clock +1/4 frame of A", 24, 12, 6),
    ("1 kHz / 1 kHz, B clock +1/2 frame", 24, 24, 12),
]
MODES = ("slow", "lcm", "fast")


def one(args):
    seed, na, nb, off, tsci = args
    sim = simulate(seed, fs=FS, na_t=na, nb_t=nb, b_off=off, t_sci=tsci)
    g = sim["gB"]
    out = {}
    # check of the rebuilt DM2 position against the simulator's own per-frame average
    cs = E.dm2_position_cumsum(sim)
    be = sim["b_end"][5:-5]
    rec = (cs[be] - cs[be - nb]) / nb
    tru = sim["comp"]["dm"][5:-5] / g
    out["dmcheck"] = float(np.max(np.abs(rec - tru)) / np.std(tru))
    for mode in MODES:
        A, B, D, wl = E.align(sim, mode)
        est, use = E.estimate(A, B, D, 0.8 * g)
        for k, v in est.items():
            r = v[LO:] / g[LO:] - 1.0
            out[f"{mode}|{k}"] = (100 * np.median(r), 100 * np.median(np.abs(r)))
        out[f"{mode}|use"] = float(100 * np.median(use[LO:]))
        out[f"{mode}|rate"] = FS / wl
        out[f"{mode}|n"] = len(A)
    return out


if __name__ == "__main__":
    tsci = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    tasks = [(300 + s, na, nb, off, tsci) for _, na, nb, off in CASES for s in range(NSEED)]
    with Pool(20) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    print(f"differenced lagged-A, toy model, {tsci:g} s windows, {NSEED} runs per case")
    print("bias of the median / per-mode median error [%] (usable part of DM2 motion [%])\n")
    print(f"{'WFS A / WFS B':40s} {'slow-sensor windows':>26s} {'common-multiple windows':>30s}"
          f" {'fast-sensor windows':>26s}")
    for ci, (name, na, nb, off) in enumerate(CASES):
        rs = allr[ci * NSEED:(ci + 1) * NSEED]
        res[name] = {"dmcheck": float(np.max([r["dmcheck"] for r in rs]))}
        line = f"{name:40s}"
        for mode in MODES:
            v = np.array([r[f"{mode}|IV diff"] for r in rs])
            u = np.mean([r[f"{mode}|use"] for r in rs])
            rate = rs[0][f"{mode}|rate"]
            rec = {k: [float(np.mean([r[f"{mode}|{k}"][0] for r in rs])),
                       float(np.std([r[f"{mode}|{k}"][0] for r in rs]) / np.sqrt(NSEED)),
                       float(np.mean([r[f"{mode}|{k}"][1] for r in rs]))]
                   for k in ("IV diff", "IV", "LS", "LS diff")}
            rec.update(use=float(u), rate=float(rate))
            res[name][mode] = rec
            m, se, a = rec["IV diff"]
            line += f"   {m:+6.1f} ({se:.1f}) / {a:4.1f} ({u:4.1f}) @{rate:5.0f}Hz"
        print(line)
    print("\nrebuilt DM2 position against the simulator (max error / rms):",
          f"{max(v['dmcheck'] for v in res.values()):.1e}")
    json.dump(res, open(f"freq_scan_{tsci:g}s.json", "w"), indent=1)
