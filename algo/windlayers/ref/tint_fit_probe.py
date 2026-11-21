#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Probe: can the intensity gain of the 4-pupil sum be self-calibrated?

Two-component model T_I = S T_core(f) + (1 - S) T_halo(f) (core: modulated PSF core, halo: broad
Gaussian). For each trial S the per-layer distances are refitted and the weighted residual of
x_l(f) = -z_l gain_S(f) a_l(f) is reported; the true gain should make z(f) flat and isotropic.
"""
import sys
import numpy as np
from astropy.io import fits
import wl_ref as wl

# usage: tint_fit_probe.py <wfs cube> <phase cube> <frame period [s]> <tbin> <skip> [halo]
wfsf, phaf = sys.argv[1], sys.argv[2]
dt0, tb, skip = float(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
halo = float(sys.argv[6]) if len(sys.argv) > 6 else 15.0


def tbin(c, b):
    t = (len(c) // b) * b
    return c[:t].reshape(t // b, b, *c.shape[1:]).mean(axis=1)


w = fits.getdata(wfsf)[skip:].astype(np.float64)
pha = fits.getdata(phaf)[skip:skip + len(w)]
n = 32
tot = w[:, :n, :n] + w[:, :n, n:] + w[:, n:, :n] + w[:, n:, n:]
dx = 0.068333 * 4
diam = 30 * dx
dt = dt0 * tb
mask = wl.pupil_mask(n, 30.0, 0.3)
di = wl.demean(tbin(tot, tb), mask, relative=True)
opd = tbin(wl.bin_cube(pha.astype(np.float64), 4), tb) * 0.5e-6 / (2 * np.pi)
lap, mk = wl.laplacian(opd, mask, dx)
kap = wl.demean(lap, mk)
spec, taper = wl.lagspec([kap, di], [mk, mask], 160)
vels = [(5.53, 0.88), (9.48, 0.55), (21.98, -0.91), (-0.3, -6.52), (1.25, -6.5)]
ztrue = [19486, 11985, 7785]
fmin, fmax = 0.15, 1.6
n2 = 2 * n
f = np.fft.fftfreq(n2, dx)
fx, fy = np.meshgrid(f, f)
fr = np.hypot(fx, fy)
sel = (fr >= fmin) & (fr <= fmax)
pa, ca = wl.decompose(spec[(0, 0)], taper[(0, 0)], vels, dx, dt)
px, cx = wl.decompose(spec[(0, 1)], taper[(0, 1)], vels, dx, dt)
g0 = 1.0 / wl.lap_gain(n2, dx)
tcore = wl.pyr_tint(n2, dx, diam, 3.0, 0.6)
thalo = wl.pyr_tint(n2, dx, diam, 3.0, halo)
ang = np.abs(np.arctan2(fy, fx))
axis = (np.minimum(np.abs(fx), np.abs(fy)) * diam < 1.5) & (fr * diam > 6)
diag = (np.abs(np.abs(fx) - np.abs(fy)) * diam < 2.0) & (fr * diam > 6)
print(f"halo sigma = {halo} l/D; T_core axis/diag(high f) = {tcore[axis & sel].mean():.3f}/"
      f"{tcore[diag & sel].mean():.3f}; T_halo = {thalo[axis & sel].mean():.3f}/"
      f"{thalo[diag & sel].mean():.3f}")
# measured anisotropy of the raw ratio (no T_I), high layers only
num_a = den_a = num_d = den_d = 0.0
for l in range(3):
    wgt = np.sqrt(ca[l] * cx[l]) * sel
    xw = wgt * g0 * (-px[l].real)
    aw = wgt * g0 * g0 * pa[l].real * ztrue[l]
    num_a += xw[axis].sum()
    den_a += aw[axis].sum()
    num_d += xw[diag].sum()
    den_d += aw[diag].sum()
print(f"measured effective T_I at high f (using true z): axis {num_a / den_a:.3f}"
      f"  diagonal {num_d / den_d:.3f}  ratio {num_a / den_a / (num_d / den_d):.2f}")
print("  S     chi2      z1      z2      z3   (truth 19486 11985 7785)")
best = None
for s in np.arange(0.0, 1.0001, 0.1):
    g = -g0 * (s * tcore + (1 - s) * thalo)
    chi = 0.0
    zs = []
    for l in range(3):
        wgt = np.sqrt(ca[l] * cx[l]) * sel
        wgt = wgt / wgt.max()
        a = pa[l].real
        x = px[l].real
        z = (wgt * g * x).sum() / (wgt * g * g * a).sum()
        # residual normalised per frequency by the layer power (relative misfit)
        r = (x - z * g * a)
        chi += (wgt * r * r).sum() / (wgt * (z * g * a) ** 2).sum()
        zs.append(z)
    print(f" {s:.1f}  {chi:8.4f}  " + "  ".join(f"{z:6.0f}" for z in zs))
