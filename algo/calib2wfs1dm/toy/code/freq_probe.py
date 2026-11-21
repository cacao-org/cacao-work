"""Why are equal loop rates harder? Window length, instrument lags and loop delay at 1:1."""
import sys
from multiprocessing import Pool

import numpy as np

import estfreq as E
from simfreq import simulate

LO, NSEED, FS = 4, 12, 24000.0
LAGS = {"2-9": range(2, 10), "3-10": range(3, 11), "2-17": range(2, 18), "4-11": range(4, 12)}


def one(args):
    seed, kw = args
    sim = simulate(seed, fs=FS, **kw)
    g = sim["gB"]
    A, B, D, wl = E.align(sim, "slow")
    out = {}
    for name, lags in LAGS.items():
        est, use = E.estimate(A, B, D, 0.8 * g, lags)
        r = est["IV diff"][LO:] / g[LO:] - 1.0
        out[name] = (100 * np.median(r), 100 * np.median(np.abs(r)), 100 * np.median(use[LO:]))
    return out


if __name__ == "__main__":
    cases = [("1k/2k, 5 s", dict(na_t=24, nb_t=12, t_sci=5.0)),
             ("1k/1k, 5 s", dict(na_t=24, nb_t=24, t_sci=5.0)),
             ("1k/1k, 20 s", dict(na_t=24, nb_t=24, t_sci=20.0)),
             ("1k/1k, 40 s", dict(na_t=24, nb_t=24, t_sci=40.0)),
             ("1k/1k, 20 s, stage-2 delay 1 frame", dict(na_t=24, nb_t=24, t_sci=20.0,
                                                          delay2_fr=1.0)),
             ("1k/1k, 20 s, stage-1 delay 1 frame", dict(na_t=24, nb_t=24, t_sci=20.0,
                                                          delay1_fr=1.0)),
             ("1k/1k, 20 s, no B-only disturbance", dict(na_t=24, nb_t=24, t_sci=20.0,
                                                          c_hi=0.0, sig_alias=0.0)),
             ("1k/1k, 20 s, WFS B noise / 4", dict(na_t=24, nb_t=24, t_sci=20.0,
                                                    sig_nB=0.0005)),
             ("2k/2k, 20 s", dict(na_t=12, nb_t=12, t_sci=20.0))]
    tasks = [(300 + s, kw) for _, kw in cases for s in range(NSEED)]
    order = sorted(range(len(tasks)), key=lambda j: -tasks[j][1]["t_sci"])
    with Pool(20) as pool:
        done = pool.map(one, [tasks[j] for j in order], chunksize=1)
    allr = [None] * len(tasks)
    for j, r in zip(order, done):
        allr[j] = r
    print(f"{'case':38s}" + "".join(f"{'lags ' + k:>26s}" for k in LAGS))
    for ci, (name, _) in enumerate(cases):
        rs = allr[ci * NSEED:(ci + 1) * NSEED]
        line = f"{name:38s}"
        for k in LAGS:
            v = np.array([r[k] for r in rs])
            se = v[:, 0].std() / np.sqrt(NSEED)
            line += (f"   {v[:, 0].mean():+5.1f} ({se:.1f}) / {v[:, 1].mean():4.1f}"
                     f" [{v[:, 2].mean():4.1f}]")
        print(line)
