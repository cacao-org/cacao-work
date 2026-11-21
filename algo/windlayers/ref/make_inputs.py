#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Small inputs derived from the milkatmturb truth cubes.

usage: make_inputs.py <dir with outarrayamp.fits>
writes int32.fits   pupil intensity map cube (amplitude squared, 4 x 4 binned, annular pupil)
       zeropha.fits flat-wavefront cube, to push scintillation alone through the pyramid WFS
"""
import sys

import numpy as np
from astropy.io import fits

import wl_ref as wl

d = sys.argv[1]
amp = fits.getdata(f"{d}/outarrayamp.fits").astype(np.float64)
pup = wl.pupil_mask(amp.shape[1] // 4, 30.0, 0.3)
fits.writeto(f"{d}/int32.fits", (wl.bin_cube(amp ** 2, 4) * pup).astype(np.float32),
             overwrite=True)
fits.writeto(f"{d}/zeropha.fits", np.zeros((2000,) + amp.shape[1:], dtype=np.float32),
             overwrite=True)
print(f"wrote {d}/int32.fits and {d}/zeropha.fits")
