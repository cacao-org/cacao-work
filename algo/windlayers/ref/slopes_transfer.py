#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""PyWFS slope transfer check with pre-whitened quantities: div(S) against laplacian(phi).

Model: S_x(f) = i sgn T_x(f) phi(f)  =>  div(S)(f) / lap(phi)(f) = sgn (s_x T_x + s_y T_y) / L(f)
with s = sin(2 pi f dx) / dx (central difference) and L the 5-point laplacian magnitude.
"""
import sys
import numpy as np
from astropy.io import fits
from math import erf, sqrt
import wl_ref as wl

# usage: slopes_transfer.py <wfs cube> <phase cube [rad at 0.5 um]> <scale applied to the phase>
wfsf, phaf, scale = sys.argv[1], sys.argv[2], float(sys.argv[3])
w = fits.getdata(wfsf).astype(np.float64)
pha = fits.getdata(phaf)[:len(w)].astype(np.float64) * scale
n = 32
q00, q10, q01, q11 = w[:, :n, :n], w[:, :n, n:], w[:, n:, :n], w[:, n:, n:]
tot = q00 + q10 + q01 + q11
mask = wl.pupil_mask(n, 30.0, 0.3)
ts = np.where(tot > 0, tot, 1.0)
sx = ((q10 + q11) - (q00 + q01)) / ts
sy = ((q01 + q11) - (q00 + q10)) / ts
dx = 0.068333 * 4
diam = 30 * dx
phi = wl.bin_cube(pha, 4) * (0.5 / 0.75)                 # rad at the WFS wavelength
lap, mk = wl.laplacian(phi, mask, dx)
div = np.zeros_like(sx)
div[:, 1:-1, 1:-1] = ((sx[:, 1:-1, 2:] - sx[:, 1:-1, :-2])
                      + (sy[:, 2:, 1:-1] - sy[:, :-2, 1:-1])) / (2 * dx)
ks = wl.demean(div * mk, mk)
kp = wl.demean(lap, mk)
n2 = 64
fs = np.fft.fft2(ks, s=(n2, n2))
fp = np.fft.fft2(kp, s=(n2, n2))
ratio = (fs * np.conj(fp)).mean(axis=0) / (np.abs(fp) ** 2).mean(axis=0)
coh = np.abs((fs * np.conj(fp)).mean(axis=0)) / np.sqrt(
    (np.abs(fp) ** 2).mean(axis=0) * (np.abs(fs) ** 2).mean(axis=0))
fm = np.fft.fftfreq(n2, dx)
f = fm * diam
cdf = np.vectorize(lambda v: 0.5 * (1.0 + erf(v / sqrt(2.0))))


def model_tx(fxa, fya, rmod, blur, npts=64):
    out = np.zeros((len(fya), len(fxa)))
    for th in (np.arange(npts) + 0.5) * 2 * np.pi / npts:
        mx, my = rmod * np.cos(th), rmod * np.sin(th)

        def ax(fv):
            return (1.0 - cdf((np.maximum(0.0, -fv) - mx) / blur)) \
                - cdf((np.minimum(0.0, -fv) - mx) / blur)

        def qy(fv):
            return 1.0 - np.abs(cdf((my + fv) / blur) - cdf(my / blur))

        out += ax(fxa)[None, :] * qy(fya)[:, None] - ax(-fxa)[None, :] * qy(-fya)[:, None]
    return out / npts


tx = model_tx(f, f, 3.0, 0.6)
ty = tx.T
s1 = np.sin(2 * np.pi * fm * dx) / dx
s2 = np.sin(np.pi * fm * dx) ** 2
lam = (4 / dx ** 2) * (s2[None, :] + s2[:, None])
model = (s1[None, :] * tx + s1[:, None] * ty) / np.where(lam > 0, lam, 1.0)
fx, fy = np.meshgrid(f, f)
fr = np.hypot(fx, fy)
sel = (fr > 1.0) & (fr < 13)
c = np.sum(ratio.real[sel] * model[sel]) / np.sum(model[sel] ** 2)
mrms = np.sqrt(np.mean(model[sel] ** 2))
print(f"div(S)/lap(phi): measured = {c:+.3f} * model; residual rms / model rms ="
      f" {np.sqrt(np.mean((ratio.real[sel] - c * model[sel]) ** 2)) / mrms:.3f};"
      f" mean coherence = {coh[sel].mean():.3f}; imag rms/model rms ="
      f" {np.sqrt(np.mean(ratio.imag[sel] ** 2)) / np.sqrt(np.mean(model[sel] ** 2)):.3f}")
print("   |f| c/ap    measured/model (axis)   (diagonal)")
for lo, hi in ((1, 2), (2, 3), (3, 4.5), (4.5, 6.5), (6.5, 9), (9, 13)):
    ring = (fr >= lo) & (fr < hi)
    ax_ = ring & (np.minimum(np.abs(fx), np.abs(fy)) < 1.0)
    dg = ring & (np.abs(np.abs(fx) - np.abs(fy)) < 1.5)
    print(f"   {lo:4.1f}-{hi:4.1f}      {ratio.real[ax_].sum() / model[ax_].sum():+.3f}"
          f"                 {ratio.real[dg].sum() / model[dg].sum():+.3f}")
