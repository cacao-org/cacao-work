#!/usr/bin/python3
"""Lagged correlation of the whitened state: does the simulated turbulence repeat?"""
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selflearn_probe import load

tdir = sys.argv[1]
W, _ = load(tdir, "aol1_modevalWFS")
D, _ = load(tdir, "aol1_modevalDM")
for name, S in (("DM", D), ("WFS", W)):
    Z = ((S - S.mean(0)) / S.std(0)).astype(np.float64)
    T = len(Z)
    print(f"--- {name}: mean over modes of corr(state[t], state[t-lag]), by mode range")
    print("  lag[s]   0-9    10-49   50-299  300-1964   all")
    for lag in (1, 10, 100, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000,
                11000, 12000, 13000, 14000, 15000, 16000):
        c = (Z[lag:] * Z[:T - lag]).mean(0)
        print(f"  {lag / 1000:6.3f} " + " ".join(f"{c[a:b].mean():7.3f}" for a, b in
              ((0, 10), (10, 50), (50, 300), (300, 1965), (0, 1965))))
    # fine scan for the strongest recurrence at long lag, high-order modes only
    lags = np.arange(2000, 18000, 20)
    cc = np.array([(Z[l:, 50:] * Z[:T - l, 50:]).mean() for l in lags])
    i = np.argsort(cc)[::-1][:5]
    print("  strongest long-lag recurrences (modes 50+):",
          ", ".join(f"{lags[j] / 1000:.2f}s c={cc[j]:.3f}" for j in i))
