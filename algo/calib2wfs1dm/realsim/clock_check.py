#!/usr/bin/python3
"""Measure a shift between the WFS A and WFS B exposure clocks from the telemetry itself.

The alignment in realsim_est.py takes the exposure times from the simulator's clock model and
the configured offset. This is an independent check of those times.

    psi = A Mab0        incoming wavefront as WFS A sees it, one WFS A frame
    y   = B - g D_eff   the same as WFS B sees it, averaged over the last two WFS B frames logged
                        before that WFS A frame (the fixed 1 kHz / 2 kHz recipe)

Both are 1 ms averages of the same signal. If the two averages do not cover the same interval,
y is shifted in time by tau against psi, which adds -2 pi f tau to the phase of their
cross-spectrum. The phase itself is not zero for aligned clocks (WFS A noise fed back through
DM1 is in both signals with its own delays), so the shift is measured differentially: the phase
of each window minus the phase of a reference window recorded with aligned clocks, fitted
between 10 and 150 Hz (cross-spectra of modes 2-39 summed, each mode normalised; delete-one-mode
jackknife error).

Expected: (500 - s) us for a WFS B clock offset s, because the last WFS B frame logged before a
WFS A frame then ended (500 - s) us before it; 0 for another aligned window.

Usage: clock_check.py <reference run>:<window> <run>:<window> [...]
"""
import sys
from pathlib import Path

import numpy as np

import realsim_est as R

FS, NSEG, BAND = 1000.0, 256, (10.0, 150.0)


def spectra(arg):
    """Welch auto- and cross-spectra of (psi, y) per mode: (frequency, mode)."""
    run, win = arg.split(":")
    ref, _, _, _, rise = R.selfrm_reference(Path(run), win)
    A, B, D, _ = R.align_fixed(Path(run), win, rise)
    A, B, D = R.cen(A), R.cen(B), R.cen(D)
    x, y = R.psi_from(A, B, D, ref), B - D * ref
    x, y = x / x.std(0), y / y.std(0)
    step, win = NSEG // 2, np.hanning(NSEG)[:, None]
    sxy = sxx = syy = 0.0
    for b in range((len(x) - NSEG) // step + 1):
        sl = slice(b * step, b * step + NSEG)
        X = np.fft.rfft(win * (x[sl] - x[sl].mean(0)), axis=0)
        Y = np.fft.rfft(win * (y[sl] - y[sl].mean(0)), axis=0)
        sxy, sxx, syy = sxy + np.conj(X) * Y, sxx + np.abs(X) ** 2, syy + np.abs(Y) ** 2
    return sxy, sxx, syy


def pooled(spec, modes):
    sxy, sxx, syy = spec
    s = sxy[:, modes].sum(1)
    return s, np.abs(s) ** 2 / (sxx[:, modes].sum(1) * syy[:, modes].sum(1))


def shift(f, spec, spec0, modes):
    """Time shift [us] of a window's y against psi, relative to the reference window."""
    (s, coh), (s0, coh0) = pooled(spec, modes), pooled(spec0, modes)
    dph = np.angle(s * np.conj(s0))
    m = (f >= BAND[0]) & (f <= BAND[1])
    wgt = 1.0 / ((1.0 - coh[m]) / coh[m] + (1.0 - coh0[m]) / coh0[m])
    tau = -np.sum(wgt * f[m] * dph[m]) / (2.0 * np.pi * np.sum(wgt * f[m] ** 2))
    return 1e6 * tau, dph, coh


def main():
    f = np.fft.rfftfreq(NSEG, 1.0 / FS)
    at = [int(np.argmin(np.abs(f - v))) for v in (50.0, 100.0, 150.0)]
    modes = np.arange(2, R.NB)
    spec0 = spectra(sys.argv[1])
    ph0 = np.angle(pooled(spec0, modes)[0])
    print(f"reference {sys.argv[1]}: phase of the psi-y cross-spectrum at 50 / 100 / 150 Hz: "
          + " / ".join(f"{np.degrees(ph0[i]):+.1f}" for i in at) + " deg")
    print(f"{'window':22s} {'shift against reference':>24s}   phase difference [deg] at"
          " 50 / 100 / 150 Hz   coherence")
    for arg in sys.argv[2:]:
        spec = spectra(arg)
        tau, dph, coh = shift(f, spec, spec0, modes)
        jk = np.array([shift(f, spec, spec0, np.delete(modes, i))[0]
                       for i in range(len(modes))])
        err = np.sqrt((len(jk) - 1) / len(jk) * np.sum((jk - jk.mean()) ** 2))
        print(f"{arg:22s} {tau:+14.0f} +- {err:3.0f} us   "
              + " / ".join(f"{np.degrees(dph[i]):+6.1f}" for i in at) + "                    "
              + " / ".join(f"{coh[i]:.2f}" for i in at))


if __name__ == "__main__":
    main()
