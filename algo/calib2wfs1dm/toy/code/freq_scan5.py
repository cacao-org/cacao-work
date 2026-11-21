"""Fifth frequency scan: the window rule with two kinds of instruments.

Windows: the rule of realsim_est.choose_windows (whole WFS B frames; the shortest run that cuts
no WFS A frame if there is one short enough, otherwise two frames of each sensor).

    window lags   differenced psi of earlier windows, from lag 2 (no frame cut) or 3
    frame lags    the 8 most recent single-frame differences of psi that touch neither of the
                  two windows being differenced
each with cut WFS A frames taken as constant (order 0) or linear (order 1) inside the frame.
Frame lags are also run with three frames of each sensor when frames have to be cut.
Adds cases with a slow WFS A and offset clocks, where the rule gives long windows.
"""
import json
import sys
from multiprocessing import Pool

import numpy as np

import estfreq as E
from freq_scan3 import CASES
from simfreq import simulate

LO, NSEED, FS = 4, 12, 24000.0
EXTRA = [("500 Hz / 2 kHz, clocks offset 1/8 A frame", 48, 12, 6),
         ("500 Hz / 1 kHz, clocks offset 1/4 A frame", 48, 24, 12),
         ("500 Hz / 1.2 kHz", 48, 20, 0),
         ("2 kHz / 1 kHz (A faster), offset 1/2 A frame", 12, 24, 6)]
# name, instruments, order inside cut frames, frames of each sensor when frames are cut
VARIANTS = [("window lags", "w", 0, 2), ("window lags, linear", "w", 1, 2),
            ("frame lags", "f", 0, 2), ("frame lags, linear", "f", 1, 2),
            ("frame lags, 3 frames", "f", 0, 3), ("same, linear", "f", 1, 3)]


def one(args):
    seed, na, nb, off, tsci = args
    sim = simulate(seed, fs=FS, na_t=na, nb_t=nb, b_off=off, t_sci=tsci)
    g = sim["gB"]
    nfr, cut = E.rule_frames(na, nb, off)
    out = {"nfr": nfr, "cut": cut}
    for name, kind, order, nmin in VARIANTS:
        if kind == "w":
            A, B, D, _ = E.align(sim, f"rule{nmin}", order=order)
            l0 = 3 if cut else 2
            est, use = E.estimate(A, B, D, 0.8 * g, range(l0, l0 + 8))
            gi = est["IV diff"]
        else:
            gi, use = E.estimate_frame_lags(sim, f"rule{nmin}", 0.8 * g, order)
        r = gi[LO:] / g[LO:] - 1.0
        out[name] = (100 * np.median(r), 100 * np.median(np.abs(r)), 100 * np.median(use[LO:]))
    return out


if __name__ == "__main__":
    tsci = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    nproc = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    cases = list(CASES) + EXTRA
    tasks = [(300 + s, na, nb, off, tsci) for _, na, nb, off in cases for s in range(NSEED)]
    with Pool(nproc) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    res = {}
    print(f"differenced lagged-A, toy model, {tsci:g} s windows, {NSEED} runs per case")
    print("bias of the median (standard error) / per-mode median error [%], usable DM2 motion\n")
    print(f"{'WFS A / WFS B':46s} {'window':>12s}" + "".join(f"{v[0]:>31s}" for v in VARIANTS))
    for ci, (name, na, nb, off) in enumerate(cases):
        rs = allr[ci * NSEED:(ci + 1) * NSEED]
        wtxt = f"{rs[0]['nfr']} B{', cut' if rs[0]['cut'] else ''}"
        line, res[name] = f"{name:46s} {wtxt:>12s}", {"nfr": rs[0]["nfr"], "cut": rs[0]["cut"]}
        for vn in (v[0] for v in VARIANTS):
            v = np.array([r[vn] for r in rs])
            m, se, a = v[:, 0].mean(), v[:, 0].std() / np.sqrt(NSEED), v[:, 1].mean()
            res[name][vn] = [float(m), float(se), float(a), float(v[:, 2].mean())]
            line += f"  {m:+6.1f} ({se:.1f}) / {a:4.1f}  {v[:, 2].mean():4.1f}%  "
        print(line)
    worst = {v[0]: max(abs(res[c][v[0]][0]) for c in res) for v in VARIANTS}
    print("\nlargest |bias| over all cases: "
          + ", ".join(f"{k}: {v:.1f}%" for k, v in worst.items()))
    json.dump(res, open(f"freq_scan5_{tsci:g}s.json", "w"), indent=1)
