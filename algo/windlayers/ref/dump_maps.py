#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Write the K / I maps of the truth test as raw float32 for the C development driver.

usage: dump_maps.py <dir with outarraypha.fits outarrayamp.fits> <output prefix>
"""
import sys
import numpy as np
from astropy.io import fits
import wl_ref as wl
d, out = sys.argv[1], sys.argv[2]
pha = fits.getdata(f"{d}/outarraypha.fits")
amp = fits.getdata(f"{d}/outarrayamp.fits")
dx = 0.068333 * 4
opd = wl.bin_cube(pha.astype(np.float64), 4) * 0.5e-6 / (2 * np.pi)
inten = wl.bin_cube(amp.astype(np.float64) ** 2, 4)
mask = wl.pupil_mask(32, 30.0, 0.3)
lap, mk = wl.laplacian(opd, mask, dx)
wl.demean(lap, mk).astype(np.float32).tofile(f"{out}_k.f32")
wl.demean(inten, mask, relative=True).astype(np.float32).tofile(f"{out}_i.f32")
mk.astype(np.float32).tofile(f"{out}_mk.f32")
mask.astype(np.float32).tofile(f"{out}_mi.f32")
print(len(opd))
