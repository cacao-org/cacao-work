#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Reference estimator on (emulated) closed-loop PyWFS frames.

I = sum of the 4 pupil images. K from --kchan: truth (curvature of the truth OPD), dm (curvature
of the DM OPD cube, upsampled to the WFS pupil grid) or slopes (divergence of the PyWFS slopes).
"""

import argparse
import time

import numpy as np
from astropy.io import fits

import wl_ref as wl

ap = argparse.ArgumentParser()
ap.add_argument("wfs")
ap.add_argument("--pha", default=None)
ap.add_argument("--dm", default=None)
ap.add_argument("--kchan", default="dm", choices=("truth", "dm", "slopes"))
ap.add_argument("--prof", default=None)
ap.add_argument("--dx", type=float, default=0.068333)
ap.add_argument("--dt", type=float, default=0.001)
ap.add_argument("--tbin", type=int, default=4)
ap.add_argument("--lam", type=float, default=0.5e-6)
ap.add_argument("--lamwfs", type=float, default=0.75e-6)
ap.add_argument("--maxlag", type=int, default=160)
ap.add_argument("--vmax", type=float, default=30.0)
ap.add_argument("--dv", type=float, default=0.5)
ap.add_argument("--fmin", type=float, default=0.15)
ap.add_argument("--fmax", type=float, default=1.6)
ap.add_argument("--nframes", type=int, default=0)
ap.add_argument("--skip", type=int, default=400)
ap.add_argument("--nsigma", type=float, default=8.0)
ap.add_argument("--minsep", type=float, default=1.5)
ap.add_argument("--minfrac", type=float, default=0.05)
ap.add_argument("--rmod", type=float, default=3.0)
ap.add_argument("--blur", type=float, default=0.6)
ap.add_argument("--tint", default="mod", choices=("mod", "one"))
ap.add_argument("--dlag", type=float, nargs="*", default=[0.0])
ap.add_argument("--noise", type=float, default=0.0, help="photons per frame (0: noiseless)")
args = ap.parse_args()


def tbin(c, b):
    t = (len(c) // b) * b
    return c[:t].reshape(t // b, b, *c.shape[1:]).mean(axis=1)


w = fits.getdata(args.wfs)[args.skip:].astype(np.float64)
if args.nframes:
    w = w[:args.nframes]
if args.noise > 0:
    rng = np.random.default_rng(7)
    w = rng.poisson(w * (args.noise / w.sum(axis=(1, 2)).mean())).astype(np.float64)
nfr0 = len(w)
n = w.shape[1] // 2
q00, q10, q01, q11 = w[:, :n, :n], w[:, :n, n:], w[:, n:, :n], w[:, n:, n:]
tot = q00 + q10 + q01 + q11
dx = args.dx * 4
diam = 30.0 * dx
dt = args.dt * args.tbin
mask = wl.pupil_mask(n, 30.0, 0.3)
di = wl.demean(tbin(tot, args.tbin), mask, relative=True)
n2 = 2 * n
gain = 1.0 / wl.lap_gain(n2, dx)

if args.kchan == "truth":
    pha = fits.getdata(args.pha)[args.skip:args.skip + nfr0]
    opd = tbin(wl.bin_cube(pha.astype(np.float64), 4), args.tbin) * args.lam / (2 * np.pi)
    lap, mk = wl.laplacian(opd, mask, dx)
elif args.kchan == "dm":
    dm = fits.getdata(args.dm)[args.skip:args.skip + nfr0].astype(np.float64) * 1e-6
    na = dm.shape[1]
    rep = n // na
    if rep > 1:
        xa = (np.arange(n) + 0.5) / rep - 0.5
        i0 = np.clip(np.floor(xa).astype(int), 0, na - 2)
        w1 = np.clip(xa - i0, 0.0, 1.0)
        up = np.zeros((n, na))
        up[np.arange(n), i0] = 1.0 - w1
        up[np.arange(n), i0 + 1] = w1
        dm = np.einsum("ia,tab,jb->tij", up, dm, up)
    lap, mk = wl.laplacian(tbin(dm, args.tbin), mask, dx)
else:
    ts = np.where(tot > 0, tot, 1.0)
    sx = tbin(((q10 + q11) - (q00 + q01)) / ts, args.tbin)
    sy = tbin(((q01 + q11) - (q00 + q10)) / ts, args.tbin)
    div = np.zeros_like(sx)
    div[:, 1:-1, 1:-1] = ((sx[:, 1:-1, 2:] - sx[:, 1:-1, :-2])
                          + (sy[:, 2:, 1:-1] - sy[:, :-2, 1:-1])) / (2 * dx)
    _, mk = wl.laplacian(sx, mask, dx)
    # linear modulated-PyWFS model: S = D / (pi^2 rmod) * grad(phi), phi = 2 pi OPD / lambda
    lap = div * mk / (diam / (np.pi ** 2 * args.rmod)) * args.lamwfs / (2 * np.pi)
kap = wl.demean(lap, mk)
print(f"K={args.kchan} frames={len(kap)} dt={dt * 1e3:.1f} ms  T={len(kap) * dt:.1f} s;"
      f" K rms={kap[:, mk > 0].std():.3e} 1/m, 4-pupil-sum dI/I rms={di[:, mask > 0].std():.4f}")

t0 = time.time()
spec, taper = wl.lagspec([kap, di], [mk, mask], args.maxlag)
lm = args.maxlag
kw = dict(dx=dx, dt=dt, vmax=args.vmax, dv=args.dv, fmin=args.fmin, fmax=args.fmax)
vg, mkk, dkk = wl.velocity_map(spec[(0, 0)], taper[(0, 0)], **kw)
_, mii, dii = wl.velocity_map(spec[(1, 1)], taper[(1, 1)], **kw)
nrm = np.sqrt(np.maximum(spec[(0, 0)][lm].real, 0) * np.maximum(spec[(1, 1)][lm].real, 0))
_, mki, dki = wl.velocity_map(spec[(0, 1)], taper[(0, 1)], norm=nrm, dlag=args.dlag[0], **kw)
print(f"lag spectra + maps: {time.time() - t0:.1f}s")
lists = []
for name, vm, dn, sg in (("K (phase space)", mkk, dkk, 1), ("4-pupil sum", mii, dii, 1),
                         ("cross K*I", mki, dki, -1)):
    peaks, (med, sig) = wl.find_peaks(vm, dn, vg, 8, args.nsigma, sign=sg, minfrac=args.minfrac)
    lists.append(peaks)
    print(f"--- {name} velocity map: " + "  ".join(
        f"({vx:.2f},{vy:.2f}) pk={val:+.3f} snr={snr:.0f}" for vx, vy, val, snr in peaks))
layers = wl.merge_peaks(lists, args.minsep)
vels = [(p[0], p[1]) for p in layers]
if args.tint == "mod":
    gain = gain * wl.pyr_tint(n2, dx, diam, args.rmod, args.blur)
for dl in args.dlag:
    res = wl.layer_distances(spec, taper, vels, dx, dt, args.fmin, args.fmax, gain=gain, dlag=dl)
    print(f"=== {len(vels)} layers, T_I={args.tint}, K delay={dl} frames")
    for r in sorted(res, key=lambda r: np.hypot(r['vx'], r['vy'])):
        print(f"  v=({r['vx']:6.2f},{r['vy']:6.2f}) | fK={r['fa']:.3f} fI={r['fb']:.3f}"
              f" | z={r['z']:8.0f} m coh={r['coh']:+.2f} xarg={r['xarg']:+.2f} | z(f): "
              + " ".join(f"{z:.0f}" for z in r['zf']))
