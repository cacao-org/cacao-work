#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""How well does the sum of the 4 PyWFS pupil images track the true pupil intensity?"""
import sys
import numpy as np
from astropy.io import fits
import wl_ref as wl

# usage: pyr_transfer.py <dir with wfs_a.fits wfs_p.fits wfs_pa.fits> <outarrayamp.fits>
d = sys.argv[1]
nfr = 2000
amp = fits.getdata(sys.argv[2])[:nfr].astype(np.float64)
itrue = wl.bin_cube(amp ** 2, 4)
n = 32
mask = wl.pupil_mask(n, 30.0, 0.3)


def quadsum(w):
    return w[:, :n, :n] + w[:, :n, n:] + w[:, n:, :n] + w[:, n:, n:]


out = {}
for tag in ("a", "p", "pa"):
    w = fits.getdata(f"{d}/wfs_{tag}.fits")[:nfr].astype(np.float64)
    s = quadsum(w)
    mean = s.mean(axis=0)
    tot = w.sum(axis=(1, 2))
    print(f"[{tag}] frame total: mean={tot.mean():.4g} rms/mean={tot.std() / tot.mean():.4f};"
          f" flux inside 4 geometric pupils={(s * mask).sum() / w.sum():.3f}")
    ds = wl.demean(s, mask, relative=True)
    out[tag] = ds
    print(f"[{tag}] dI/I rms of 4-pupil sum inside pupil = {ds[:, mask > 0].std():.4f}")
    if tag == "a":
        np.save(f"{d}/mean_wfs_a.npy", w.mean(axis=0))
dt_true = wl.demean(itrue, mask, relative=True)
print(f"true (binned) dI/I rms = {dt_true[:, mask > 0].std():.4f}")
for tag in ("a", "pa", "p"):
    c = (out[tag] * dt_true)[:, mask > 0].mean() / np.sqrt(
        (out[tag] ** 2)[:, mask > 0].mean() * (dt_true ** 2)[:, mask > 0].mean())
    reg = (out[tag] * dt_true)[:, mask > 0].mean() / (dt_true ** 2)[:, mask > 0].mean()
    print(f"[{tag}] correlation with true intensity = {c:+.3f}, regression slope = {reg:+.3f}")
# orientation check: try flips
for name, op in (("identity", lambda a: a), ("flipx", lambda a: a[:, :, ::-1]),
                 ("flipy", lambda a: a[:, ::-1, :]), ("rot180", lambda a: a[:, ::-1, ::-1]),
                 ("transpose", lambda a: a.transpose(0, 2, 1))):
    t = op(dt_true)
    c = (out["a"] * t)[:, mask > 0].mean() / np.sqrt(
        (out["a"] ** 2)[:, mask > 0].mean() * (t ** 2)[:, mask > 0].mean())
    print(f"   orientation {name:9s}: corr = {c:+.3f}")

# 2-D transfer function T(f) = <S conj(I)> / <|I|^2> on the zero-padded FFT grid
n2 = 64
fs = np.fft.fft2(out["a"], s=(n2, n2))
ft = np.fft.fft2(dt_true, s=(n2, n2))
tf = (fs * np.conj(ft)).mean(axis=0) / (np.abs(ft) ** 2).mean(axis=0)
coh = np.abs((fs * np.conj(ft)).mean(axis=0)) / np.sqrt(
    (np.abs(ft) ** 2).mean(axis=0) * (np.abs(fs) ** 2).mean(axis=0))
np.save(f"{d}/tf_a.npy", tf)
f = np.fft.fftfreq(n2, 1.0 / n2) * (30.0 / n2)      # cycles per pupil diameter (30 px)
fx, fy = np.meshgrid(f, f)
fr = np.hypot(fx, fy)
print("transfer function of the 4-pupil sum (amplitude-only case), cycles/aperture:")
print("  |f| range     axis(|fy|<1)   diagonal      coherence")
for lo, hi in ((0.5, 1.5), (1.5, 2.5), (2.5, 3.5), (3.5, 5), (5, 7), (7, 10), (10, 14)):
    ring = (fr >= lo) & (fr < hi)
    ax = ring & ((np.abs(fy) < 1.0) | (np.abs(fx) < 1.0))
    dg = ring & (np.abs(np.abs(fx) - np.abs(fy)) < 1.0)
    print(f"  {lo:4.1f}-{hi:4.1f}      {tf.real[ax].mean():6.3f}        {tf.real[dg].mean():6.3f}"
          f"        {coh[ring].mean():.3f}")
