"""Self-test of the differenced lagged-A estimator on toy data: no simulator, no data files.

Runs the toy two-stage loop (simfreq.py) for two clock configurations and estimates the DM2
gain with the two independent implementations kept in this directory tree:

    toy    estfreq.py: windows in grid ticks, DM2 position rebuilt on the fine grid
    real   ../../realsim/realsim_est.py: align_frames() and estimate(), the code used on
           simulator telemetry, fed here with the toy frames and their exposure end times

It checks that (1) the two implementations agree, (2) both are close to the true gain, and
(3) the numbers match the values recorded when this directory was committed. Use it to check
an installation, and as a reference when the estimator is ported.

Usage: selftest.py          a few seconds, single process, needs numpy and astropy
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "realsim"))

import estfreq as E  # noqa: E402
import realsim_est as R  # noqa: E402
from simfreq import simulate  # noqa: E402

LO, SEED, T_SCI, FS = 4, 300, 5.0, 24000.0
# name, grid ticks per WFS A frame, per WFS B frame, WFS B clock offset in ticks,
# recorded bias of the median [%] (toy implementation), WFS B frames per window, frames cut
CASES = [
    ("1 kHz / 2 kHz, aligned clocks", 24, 12, 0, -0.49, 2, False),
    ("1 kHz / 2 kHz, WFS B clock 250 us late", 24, 12, 6, -0.74, 4, True),
]
# Percentage points. When recorded (2026-11-20, numpy 2.3 and 2.5) the two implementations
# differed by 0.07 and 0.05: they use the same windows but drop different ones at the ends.
TOL_AGREE, TOL_TRUTH, TOL_RECORD = 0.3, 8.0, 0.2


def bias(g, truth):
    r = g[LO:] / truth[LO:] - 1.0
    return float(100 * np.median(r)), float(100 * np.median(np.abs(r)))


def toy_path(sim):
    p = sim["p"]
    nfr, cut = E.rule_frames(int(p["na_t"]), int(p["nb_t"]), int(p["b_off"]))
    A, B, D, _ = E.align(sim, "rule")
    lag0 = 3 if cut else 2
    est, _ = E.estimate(A, B, D, 0.8 * sim["gB"], range(lag0, lag0 + 8))
    return est["IV diff"], nfr, cut


def real_path(sim):
    p = sim["p"]
    na, nb = int(p["na_t"]), int(p["nb_t"])
    a_end, b_end = sim["a_end"], sim["b_end"]
    cs = E.dm2_position_cumsum(sim)
    deff = (cs[b_end] - cs[b_end - nb]) / nb             # DM2 position over each WFS B frame
    ka, kb = a_end > sim["t0"], b_end > sim["t0"]        # drop the warm-up second
    # Same window phase as the toy implementation, whose windows start at the clock offset
    # plus a whole number of windows. (With cut frames the phase is otherwise a free choice,
    # and the result depends on it at the level of the noise.)
    wl = E.rule_frames(na, nb, int(p["b_off"]))[0] * nb
    anchor = int(np.flatnonzero((b_end[kb] - nb - int(p["b_off"])) % wl == 0)[0])
    Aw, Bw, Dw, desc = R.align_frames(
        sim["A"][ka][:, :R.NA], a_end[ka].astype(float), float(na),
        sim["B"][kb], b_end[kb].astype(float), float(nb), deff[kb], anchor=anchor)
    est, _, use = R.estimate(Aw, Bw, Dw, 0.8 * sim["gB"], desc["lag0"])
    return est["IV diff"], desc, float(100 * np.median(use[LO:]))


def main():
    ok = True
    for name, na, nb, off, recorded, nfr_exp, cut_exp in CASES:
        sim = simulate(SEED, fs=FS, na_t=na, nb_t=nb, b_off=off, t_sci=T_SCI)
        g_toy, nfr, cut = toy_path(sim)
        g_real, desc, use = real_path(sim)
        (bt, et), (br, er) = bias(g_toy, sim["gB"]), bias(g_real, sim["gB"])
        checks = [
            ("window rule", nfr == nfr_exp and cut == cut_exp
             and desc["b_per_window"] == nfr_exp and desc["a_cut"] == cut_exp),
            ("implementations agree", abs(bt - br) < TOL_AGREE),
            ("close to the true gain", abs(bt) < TOL_TRUTH and abs(br) < TOL_TRUTH),
            ("matches the recorded value", recorded is None or abs(bt - recorded) < TOL_RECORD),
        ]
        print(f"{name}: {nfr} WFS B frames per window, WFS A frames cut: {cut}")
        print(f"    toy implementation   {bt:+6.2f}% (per mode {et:.2f}%)")
        print(f"    real implementation  {br:+6.2f}% (per mode {er:.2f}%), usable {use:.1f}%")
        for label, passed in checks:
            ok &= bool(passed)
            print(f"    {'ok  ' if passed else 'FAIL'} {label}")
    print("SELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
