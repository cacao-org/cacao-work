#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Emulate a closed AO loop on a truth phase cube (experiment harness).

Zonal integrator with a bilinear-influence DM of nact x nact actuators and a 2-frame delay.
Writes the residual phase cube (same unit as the input, rad at the reference wavelength) and
the DM OPD cube [um] on its own nact x nact grid, sign such that residual = phase - DM.
"""
import argparse
import numpy as np
from astropy.io import fits

ap = argparse.ArgumentParser()
ap.add_argument("pha")
ap.add_argument("outres")
ap.add_argument("outdm")
ap.add_argument("--nact", type=int, default=16)
ap.add_argument("--gain", type=float, default=0.4)
ap.add_argument("--leak", type=float, default=0.99)
ap.add_argument("--delay", type=int, default=2)
ap.add_argument("--lam", type=float, default=0.5)
args = ap.parse_args()

pha = fits.getdata(args.pha).astype(np.float32)
nfr, n, _ = pha.shape
na = args.nact
cell = n // na
# bilinear influence: actuators at cell centres, sample at pixel centres
xa = (np.arange(n) + 0.5) / cell - 0.5
i0 = np.clip(np.floor(xa).astype(int), 0, na - 2)
w1 = np.clip(xa - i0, 0.0, 1.0)
up = np.zeros((n, na), dtype=np.float32)
up[np.arange(n), i0] = 1.0 - w1
up[np.arange(n), i0 + 1] = w1
res = np.empty_like(pha)
dm = np.zeros((nfr, na, na), dtype=np.float32)
cmd = [np.zeros((na, na), dtype=np.float32) for _ in range(args.delay + 1)]
for t in range(nfr):
    c_app = cmd[0]
    d = up @ c_app @ up.T
    res[t] = pha[t] - d
    dm[t] = c_app
    r = res[t].reshape(na, cell, na, cell).mean(axis=(1, 3))
    cmd.append(args.leak * cmd[-1] + args.gain * r)
    cmd.pop(0)
k = args.lam / (2 * np.pi)
fits.writeto(args.outres, res, overwrite=True)
fits.writeto(args.outdm, dm * k, overwrite=True)
tail = slice(nfr // 10, None)
rr = res[tail] - res[tail].mean(axis=(1, 2), keepdims=True)
pp = pha[tail] - pha[tail].mean(axis=(1, 2), keepdims=True)
print(f"nact={na} gain={args.gain}: open-loop rms {pp.std() * k * 1e3:.0f} nm ->"
      f" residual rms {rr.std() * k * 1e3:.0f} nm"
      f" ({rr.std() * args.lam / 0.75:.2f} rad at 0.75 um)")
