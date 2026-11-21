"""Toy prediction for the real-simulator test with an offset WFS B clock.

1 kHz WFS A, 2 kHz WFS B, WFS B clock late by a quarter of a WFS A frame (250 us), 20 s.
Compares, on the same data:

    fixed recipe   what the first real-telemetry test did: each WFS A frame against the last two
                   whole WFS B frames that ended before it. Exact for aligned clocks; with the
                   offset those two frames cover an interval a quarter frame early.
    2 B frames     whole WFS B frames, one WFS A frame long, WFS A overlap-weighted, lag 3
    4 B frames     the rule of realsim_est.choose_windows: two frames of each sensor, lag 3

Also with aligned clocks, where all three must agree with the tested recipe.
"""
import sys
from multiprocessing import Pool

import numpy as np

import estfreq as E
from simfreq import simulate

LO, FS, NA_T, NB_T = 4, 24000.0, 24, 12


def fixed_recipe(sim):
    """A frame j against the two whole B frames ending last before it (no overlap weights)."""
    p = sim["p"]
    na, nb = int(p["na_t"]), int(p["nb_t"])
    a_end, b_end = sim["a_end"], sim["b_end"]
    kT = np.searchsorted(b_end, a_end, side="right") - 1      # last B frame ended by then
    ok = (kT >= 5) & (a_end > sim["t0"] + 4 * na) & (a_end < sim["n_t"] - 4 * na)
    kT, A = kT[ok], sim["A"][ok][:, :60]
    B = 0.5 * (sim["B"][kT - 1] + sim["B"][kT])
    cs = E.dm2_position_cumsum(sim)
    w1 = b_end[kT]
    D = (cs[w1] - cs[w1 - 2 * nb]) / (2 * nb)
    return A, B, D


def one(args):
    seed, off, tsci = args
    sim = simulate(seed, fs=FS, na_t=NA_T, nb_t=NB_T, b_off=off, t_sci=tsci)
    g = sim["gB"]
    out = {}
    A, B, D = fixed_recipe(sim)
    cases = [("fixed recipe", (A, B, D), 2)]
    for name, mode in (("2 B frames", "bwin1"), ("4 B frames", "bwin2")):
        Aw, Bw, Dw, wl = E.align(sim, mode)
        cut = not (wl % NA_T == 0 and off % NA_T == 0)
        cases.append((name, (Aw, Bw, Dw), 3 if cut else 2))
    for name, (Aw, Bw, Dw), l0 in cases:
        est, _ = E.estimate(Aw, Bw, Dw, 0.8 * g, range(l0, l0 + 8))
        r = est["IV diff"][LO:] / g[LO:] - 1.0
        out[name] = (100 * np.median(r), 100 * np.median(np.abs(r)), l0)
    return out


if __name__ == "__main__":
    nproc = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    nseed, tsci = 12, 20.0
    offs = [(0, "clocks aligned"), (6, "WFS B clock late by 250 us")]
    tasks = [(300 + s, off, tsci) for off, _ in offs for s in range(nseed)]
    with Pool(nproc) as pool:
        allr = pool.map(one, tasks, chunksize=1)
    print(f"toy model, 1 kHz / 2 kHz, {tsci:g} s, {nseed} runs:"
          " bias of the median (standard error) / per-mode median error [%], first lag")
    for i, (off, label) in enumerate(offs):
        rs = allr[i * nseed:(i + 1) * nseed]
        line = f"{label:28s}"
        for name in ("fixed recipe", "2 B frames", "4 B frames"):
            v = np.array([r[name] for r in rs])
            line += (f"  {name}: {v[:, 0].mean():+5.1f} ({v[:, 0].std() / np.sqrt(nseed):.1f})"
                     f" / {v[:, 1].mean():4.1f} L{int(v[0, 2])}")
        print(line)
