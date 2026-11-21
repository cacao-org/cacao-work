#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Reference estimator on PyWFS frames: I = sum of the 4 pupil images, K = curvature of a
wavefront cube (truth OPD here)."""

import argparse
import time

import numpy as np
from astropy.io import fits

import wl_ref as wl

ap = argparse.ArgumentParser()
ap.add_argument("wfs")
ap.add_argument("pha")
ap.add_argument("--prof", default=None)
ap.add_argument("--dx", type=float, default=0.068333)
ap.add_argument("--dt", type=float, default=0.004)
ap.add_argument("--lam", type=float, default=0.5e-6)
ap.add_argument("--maxlag", type=int, default=160)
ap.add_argument("--vmax", type=float, default=30.0)
ap.add_argument("--dv", type=float, default=0.5)
ap.add_argument("--fmin", type=float, default=0.15)
ap.add_argument("--fmax", type=float, default=1.6)
ap.add_argument("--nframes", type=int, default=0)
ap.add_argument("--nsigma", type=float, default=8.0)
ap.add_argument("--minsep", type=float, default=1.5)
ap.add_argument("--minfrac", type=float, default=0.05)
ap.add_argument("--rmod", type=float, default=3.0)
ap.add_argument("--blur", type=float, default=0.6)
ap.add_argument("--notint", action="store_true")
ap.add_argument("--save", default=None)
args = ap.parse_args()

w = fits.getdata(args.wfs).astype(np.float64)
pha = fits.getdata(args.pha)
nfr = min(len(w), len(pha)) if not args.nframes else args.nframes
w, pha = w[:nfr], pha[:nfr]
n = w.shape[1] // 2
inten = w[:, :n, :n] + w[:, :n, n:] + w[:, n:, :n] + w[:, n:, n:]
dx = args.dx * (pha.shape[1] // n)
diam = 30.0 * dx
opd = wl.bin_cube(pha.astype(np.float64), pha.shape[1] // n) * args.lam / (2 * np.pi)
mask = wl.pupil_mask(n, 30.0, 0.3)
lap, mk = wl.laplacian(opd, mask, dx)
kap = wl.demean(lap, mk)
di = wl.demean(inten, mask, relative=True)
print(f"frames={nfr} grid={n} dx={dx:.4f} m  T={nfr * args.dt:.1f} s; curvature rms ="
      f" {kap[:, mk > 0].std():.3e} 1/m, 4-pupil-sum dI/I rms = {di[:, mask > 0].std():.4f}")

t0 = time.time()
spec, taper = wl.lagspec([kap, di], [mk, mask], args.maxlag)
lm = args.maxlag
kw = dict(dx=dx, dt=args.dt, vmax=args.vmax, dv=args.dv, fmin=args.fmin, fmax=args.fmax)
vg, mkk, dkk = wl.velocity_map(spec[(0, 0)], taper[(0, 0)], **kw)
_, mii, dii = wl.velocity_map(spec[(1, 1)], taper[(1, 1)], **kw)
nrm = np.sqrt(np.maximum(spec[(0, 0)][lm].real, 0) * np.maximum(spec[(1, 1)][lm].real, 0))
_, mki, dki = wl.velocity_map(spec[(0, 1)], taper[(0, 1)], norm=nrm, **kw)
print(f"lag spectra + maps: {time.time() - t0:.1f}s")

if args.prof:
    rows = [ln.split() for ln in open(args.prof) if ln.strip() and not ln.startswith("#")]
    alt0 = min(float(r[0]) for r in rows)
    cn2 = sum(float(r[1]) for r in rows)
    print("truth layers (pattern velocity = -wind):  z[m]  cn2frac   vx     vy   speed  dir[deg]")
    for r in rows:
        spd, d = float(r[2]), float(r[3])
        print(f"  {float(r[0]) - alt0:8.0f} {float(r[1]) / cn2:7.3f} {-spd * np.cos(d):7.2f}"
              f" {-spd * np.sin(d):7.2f} {spd:6.2f} {(np.degrees(d) + 180) % 360:7.1f}")

lists = []
for name, vm, dn, sg in (("curvature", mkk, dkk, 1), ("4-pupil sum", mii, dii, 1),
                         ("cross K*I", mki, dki, -1)):
    peaks, (med, sig) = wl.find_peaks(vm, dn, vg, 8, args.nsigma, sign=sg, minfrac=args.minfrac)
    lists.append(peaks)
    print(f"--- {name} velocity map: median={med:+.4f} sigma={sig:.4f}")
    for vx, vy, val, snr in peaks:
        print(f"  v=({vx:6.2f},{vy:6.2f}) speed={np.hypot(vx, vy):5.2f}"
              f" dir={np.degrees(np.arctan2(vy, vx)) % 360:6.1f} peak={val:+.3f} snr={snr:6.1f}")

layers = wl.merge_peaks(lists, args.minsep)
vels = [(p[0], p[1]) for p in layers]
n2 = spec[(0, 0)].shape[1]
gain = 1.0 / wl.lap_gain(n2, dx)
if not args.notint:
    gain = gain * wl.pyr_tint(n2, dx, diam, args.rmod, args.blur)
res = wl.layer_distances(spec, taper, vels, dx, args.dt, args.fmin, args.fmax, gain=gain)
print(f"=== joint decomposition of {len(vels)} layers"
      f" (T_I model: {'off' if args.notint else f'rmod={args.rmod} blur={args.blur}'})")
for r in sorted(res, key=lambda r: np.hypot(r['vx'], r['vy'])):
    print(f"  v=({r['vx']:6.2f},{r['vy']:6.2f}) speed={np.hypot(r['vx'], r['vy']):5.2f}"
          f" dir={np.degrees(np.arctan2(r['vy'], r['vx'])) % 360:6.1f}"
          f" | fK={r['fa']:.3f} fI={r['fb']:.3f} | z={r['z']:8.0f} m  zamp={r['zamp']:7.0f}"
          f" coh={r['coh']:+.2f}")
    print("      z(f): " + " ".join(f"{f:.2f}:{z:.0f}" for f, z in zip(r['f'], r['zf'])))
if args.save:
    np.savez(args.save, vg=vg, mkk=mkk, mii=mii, mki=mki, dkk=dkk, dii=dii, dki=dki)
