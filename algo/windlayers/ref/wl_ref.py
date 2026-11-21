#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Numpy reference for the wind-layer estimator (experiment only, not the deployed tool).

Channels (pupil-plane map sequences on one grid, pixel pitch dx, frame period dt):
  K(x, t)  wavefront curvature, laplacian of the OPD [1/m]   ("phase space")
  I(x, t)  relative intensity fluctuation dI/I               ("intensity space")
Both are spatially near-white for Kolmogorov turbulence, which keeps spectral leakage harmless.

Method
  1. Lag spectra. With F_a(f, t) the zero-padded spatial FFT of masked channel a,
       S_ab(tau, f) = < conj(F_a(f, t)) F_b(f, t + tau) >_t ,  tau = -L .. L.
     Its inverse FFT over f is the space-time covariance multiplied by the mask taper
     t_ab(rho) = number of pixel pairs at separation rho.
  2. Velocity maps. A frozen layer moving at v gives S_aa(tau, f) = S_aa(0, f) t(v tau)
     exp(-2 pi i f.v tau). R(tau, f) = S(tau, f) / S(0, f), weighted by |f| over a band and
     inverse transformed, is a correlation slice that peaks at rho = v tau. Slices are stacked
     along rho = v tau with weight tau (filtered back-projection of the Radon transform that the
     per-f temporal spectra form). Only lags tau != 0 enter, so temporally white noise drops out.
  3. Layer decomposition. With the peak velocities v_l, each S_ab(tau, f) is fitted, per spatial
     frequency, as a sum of frozen layers: S(tau, f) = sum_l p_l(f) t(v_l tau) exp(-2 pi i f.v_l
     tau). This separates layers whose planes nu = -f.v overlap at some frequencies.
  4. Distance. Geometric propagation over z gives dI/I = -z * laplacian(OPD), so on each layer
     x_l(f) = -z_l gain(f) a_l(f) (a: curvature power, x: curvature-intensity cross power) and z_l
     is a weighted least-squares slope.
"""

from __future__ import annotations

import numpy as np


def pupil_mask(n, diam_pix, cobs=0.0):
    """Centred annular pupil mask on an n x n grid (pixel centres at half-integers)."""
    c = (n - 1) / 2.0
    y, x = np.mgrid[0:n, 0:n]
    r = np.hypot(x - c, y - c)
    return ((r <= diam_pix / 2.0) & (r >= cobs * diam_pix / 2.0)).astype(np.float64)


def bin_cube(cube, b):
    """Average b x b pixel blocks of a (T, ny, nx) cube."""
    t, ny, nx = cube.shape
    return cube.reshape(t, ny // b, b, nx // b, b).mean(axis=(2, 4))


def laplacian(cube, mask, dx):
    """5-point laplacian of each frame, valid where the pixel and its 4 neighbours are in mask.

    Returns (lap [unit / m^2], valid mask).
    """
    m = mask > 0
    v = m.copy()
    v[1:, :] &= m[:-1, :]
    v[:-1, :] &= m[1:, :]
    v[:, 1:] &= m[:, :-1]
    v[:, :-1] &= m[:, 1:]
    v[0, :] = v[-1, :] = False
    v[:, 0] = v[:, -1] = False
    lap = np.zeros_like(cube, dtype=np.float64)
    lap[:, 1:-1, 1:-1] = (cube[:, 1:-1, 2:] + cube[:, 1:-1, :-2] + cube[:, 2:, 1:-1]
                          + cube[:, :-2, 1:-1] - 4.0 * cube[:, 1:-1, 1:-1]) / dx ** 2
    return lap * v, v.astype(np.float64)


def lap_gain(n2, dx):
    """|transfer| of the 5-point laplacian divided by (2 pi f)^2 on the FFT grid (1 at f -> 0)."""
    f = np.fft.fftfreq(n2, dx)
    s = np.sin(np.pi * f * dx) ** 2
    num = (4.0 / dx ** 2) * (s[None, :] + s[:, None])
    den = 4.0 * np.pi ** 2 * (f[None, :] ** 2 + f[:, None] ** 2)
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), 1.0)


def demean(cube, mask, relative=False):
    """Remove the temporal mean per pixel (relative=True: divide by it), then the frame mean."""
    c = cube.astype(np.float64)
    mt = c.mean(axis=0)
    c = (c / np.where(np.abs(mt) > 0, mt, 1.0) - 1.0) if relative else (c - mt)
    c = c * mask
    c -= (c.sum(axis=(1, 2)) / mask.sum())[:, None, None] * mask
    return c


def lagspec(chans, masks, maxlag, pad=2):
    """Lag spectra S_ab(tau, f) = <conj(F_a(f,t)) F_b(f,t+tau)>_t / t_ab(0), tau = -L..L.

    Returns (spec, taper): spec[(i, j)] complex (2L+1, n2, n2), index tau + L, FFT order in f;
    taper[(i, j)] real (n2, n2), fftshifted pixel-pair count t_ij(rho) / t_ij(0).
    """
    nfr, n, _ = chans[0].shape
    n2 = pad * n
    nt = 1
    while nt < nfr + maxlag + 1:
        nt *= 2
    fts = []
    for c in chans:
        f2 = np.fft.fft2(c.astype(np.float32), s=(n2, n2)).astype(np.complex64)
        fts.append(np.fft.fft(f2, n=nt, axis=0))
    cnt = nfr - np.abs(np.arange(-maxlag, maxlag + 1))
    spec, taper = {}, {}
    nch = len(chans)
    for i in range(nch):
        for j in range(i, nch):
            c = np.fft.ifft(np.conj(fts[i]) * fts[j], axis=0)
            s = np.concatenate([c[nt - maxlag:], c[:maxlag + 1]], axis=0).astype(np.complex128)
            fm = np.conj(np.fft.fft2(masks[i], s=(n2, n2))) * np.fft.fft2(masks[j], s=(n2, n2))
            t = np.fft.fftshift(np.fft.ifft2(fm).real)
            t0 = t[n2 // 2, n2 // 2]
            spec[(i, j)] = s / cnt[:, None, None] / t0
            taper[(i, j)] = t / t0
    return spec, taper


def band_ramp(n2, dx, fmin, fmax):
    """Ramp |f| weight on fmin <= |f| <= fmax (cosine edges), normalised to unit sum."""
    f = np.fft.fftfreq(n2, dx)
    fr = np.hypot(f[None, :], f[:, None])
    edge = 0.1 * (fmax - fmin)
    lo = np.clip((fr - fmin) / edge, 0.0, 1.0)
    hi = np.clip((fmax - fr) / edge, 0.0, 1.0)
    b = fr * (0.5 - 0.5 * np.cos(np.pi * lo)) * (0.5 - 0.5 * np.cos(np.pi * hi))
    return b / b.sum()


def _bilinear(img, x, y):
    """Bilinear sample of a 2-D array at float pixel coordinates (0 outside)."""
    ny, nx = img.shape
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = x - x0
    fy = y - y0
    ok = (x0 >= 0) & (x0 < nx - 1) & (y0 >= 0) & (y0 < ny - 1)
    x0 = np.clip(x0, 0, nx - 2)
    y0 = np.clip(y0, 0, ny - 2)
    v = (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
         + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)
    return np.where(ok, v, 0.0)


def lag_weight(maxlag):
    """Lag weights w(k), k = 1..L: ramp times a Hann roll-off towards the largest lag."""
    k = np.arange(1, maxlag + 1, dtype=np.float64)
    return k * (0.5 + 0.5 * np.cos(np.pi * k / (maxlag + 1)))


def velocity_map(spec, taper, dx, dt, vmax, dv, fmin, fmax, norm=None, pad=2, minpow=1e-3,
                 dlag=0.0):
    """Filtered back-projection velocity map of one channel pair.

    spec: (2L+1, n2, n2); norm: zero-lag power used to normalise (default: spec at tau = 0; for a
    cross pair give sqrt(S_aa(0) S_bb(0))). Both lag signs are stacked. Returns (vgrid, map,
    support): map = coherent fraction of the band power moving at v, support = sum of the squared
    weights (0 where no lag supports that velocity).
    """
    nl, n2, _ = spec.shape
    lmax = nl // 2
    if norm is None:
        norm = spec[lmax].real
    good = norm > minpow * norm.max()
    b = band_ramp(n2, dx, fmin, fmax) * good
    b = b / b.sum()
    r_all = np.where(good, spec / np.where(good, norm, 1.0), 0.0) * b
    np2 = n2 * pad
    c0 = np2 // 2 - n2 // 2
    vg = np.arange(-vmax, vmax + 0.5 * dv, dv)
    vx, vy = np.meshgrid(vg, vg)
    num = np.zeros_like(vx)
    den = np.zeros_like(vx)
    w = lag_weight(lmax)
    for k in range(1, lmax + 1):
        for s in (1, -1):
            rp = np.zeros((np2, np2), dtype=np.complex128)
            rp[c0:c0 + n2, c0:c0 + n2] = np.fft.fftshift(r_all[lmax + s * k])
            g = np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(rp)).real) * np2 * np2
            px = vx * ((s * k + dlag) * dt) / dx
            py = vy * ((s * k + dlag) * dt) / dx
            gv = _bilinear(g, px * pad + np2 // 2, py * pad + np2 // 2)
            tv = _bilinear(taper, px + n2 // 2, py + n2 // 2)
            num += w[k - 1] * tv * gv
            den += w[k - 1] * tv * tv
    vmap = np.where(den > 0, num / np.maximum(den, 1e-30), 0.0)
    return vg, vmap, den


def find_peaks(vmap, den, vg, nmax, nsigma, sign=1.0, minden_frac=0.02, minfrac=0.0):
    """Local maxima (3x3) above a robust median + nsigma * MAD threshold, parabolic refinement.

    Returns a list of (vx, vy, value, snr) sorted by decreasing value, and (median, sigma).
    """
    sm = sign * vmap
    usable = den > minden_frac * den.max()
    vals = sm[usable]
    med = np.median(vals)
    sig = 1.4826 * np.median(np.abs(vals - med)) + 1e-30
    dv = vg[1] - vg[0]
    nv = len(vg)
    cand = []
    for iy in range(1, nv - 1):
        for ix in range(1, nv - 1):
            v = sm[iy, ix]
            if not usable[iy, ix] or (v - med) < nsigma * sig:
                continue
            nb = sm[iy - 1:iy + 2, ix - 1:ix + 2]
            if v < nb.max():
                continue
            cx = sm[iy, ix - 1] - 2 * v + sm[iy, ix + 1]
            cy = sm[iy - 1, ix] - 2 * v + sm[iy + 1, ix]
            ox = np.clip(0.5 * (sm[iy, ix - 1] - sm[iy, ix + 1]) / cx, -1, 1) if cx < 0 else 0.0
            oy = np.clip(0.5 * (sm[iy - 1, ix] - sm[iy + 1, ix]) / cy, -1, 1) if cy < 0 else 0.0
            cand.append((vg[ix] + ox * dv, vg[iy] + oy * dv, sign * v, (v - med) / sig))
    cand.sort(key=lambda p: -abs(p[2]))
    if cand and minfrac > 0:
        cand = [p for p in cand if abs(p[2]) >= minfrac * abs(cand[0][2])]
    return cand[:nmax], (med, sig)


def merge_peaks(lists, minsep):
    """Merge peak lists (each a list of (vx, vy, value, snr)); keep the highest-snr of a group."""
    allp = sorted((p for lst in lists for p in lst), key=lambda p: -p[3])
    out = []
    for p in allp:
        if all(np.hypot(p[0] - q[0], p[1] - q[1]) >= minsep for q in out):
            out.append(p)
    return out


def decompose(spec, taper, vels, dx, dt, reg=1e-3, dlag=0.0):
    """Per-frequency least-squares split of one lag spectrum into frozen layers.

    Model: S(tau, f) = sum_l p_l(f) t(v_l tau) exp(-2 pi i f.v_l tau), tau != 0 (both signs).
    Returns (p, cw): p complex (nlayer, n2, n2) layer power per spatial frequency, cw real
    (nlayer, n2, n2) = 1 / [G^-1]_ll, the weight (inverse variance up to a constant) of p_l(f).
    """
    nl, n2, _ = spec.shape
    lmax = nl // 2
    nk = len(vels)
    f = np.fft.fftfreq(n2, dx)
    fx = f[None, :]
    fy = f[:, None]
    w = lag_weight(lmax) / np.arange(1, lmax + 1)
    gmat = np.zeros((n2, n2, nk, nk), dtype=np.complex128)
    yvec = np.zeros((n2, n2, nk), dtype=np.complex128)
    for k in range(1, lmax + 1):
        for s in (1, -1):
            tau = (s * k + dlag) * dt
            tl = np.array([float(_bilinear(taper, vx * tau / dx + n2 // 2,
                                           vy * tau / dx + n2 // 2)) for vx, vy in vels])
            if not np.any(tl > 0):
                continue
            ph = np.stack([np.exp(-2j * np.pi * (fx * vx + fy * vy) * tau) for vx, vy in vels],
                          axis=-1)
            beta = ph * tl
            yvec += w[k - 1] * np.conj(beta) * spec[lmax + s * k][:, :, None]
            gmat += w[k - 1] * np.conj(beta)[:, :, :, None] * beta[:, :, None, :]
    dg = np.real(np.einsum("xyll->xyl", gmat))
    scale = np.maximum(dg.max(axis=(0, 1)), 1e-300)
    gmat = gmat + reg * np.eye(nk)[None, None] * scale[None, None, :, None]
    ginv = np.linalg.inv(gmat)
    p = np.einsum("xylm,xym->xyl", ginv, yvec)
    cw = 1.0 / np.maximum(np.real(np.einsum("xyll->xyl", ginv)), 1e-300)
    return np.moveaxis(p, -1, 0), np.moveaxis(cw, -1, 0)


def layer_distances(spec, taper, vels, dx, dt, fmin, fmax, gain=None, nbins=8, reg=1e-3,
                    dlag=0.0):
    """Decompose the K, I and K x I lag spectra into layers and fit each layer's distance.

    Channel 0 = curvature K [1/m], channel 1 = intensity dI/I. gain(f): intensity transfer of the
    sensor relative to curvature (None = 1), so that on a layer x(f) = -z gain(f) a(f).
    Returns a list of dicts, one per velocity.
    """
    n2 = spec[(0, 0)].shape[1]
    f = np.fft.fftfreq(n2, dx)
    fr = np.hypot(f[None, :], f[:, None])
    sel = (fr >= fmin) & (fr <= fmax)
    g = -np.ones_like(fr) if gain is None else -gain
    pa, ca = decompose(spec[(0, 0)], taper[(0, 0)], vels, dx, dt, reg)
    pb, _ = decompose(spec[(1, 1)], taper[(1, 1)], vels, dx, dt, reg)
    px, cx = decompose(spec[(0, 1)], taper[(0, 1)], vels, dx, dt, reg, dlag)
    lmax = spec[(0, 0)].shape[0] // 2
    tot_a = spec[(0, 0)][lmax].real[sel].sum()
    tot_b = spec[(1, 1)][lmax].real[sel].sum()
    edges = np.linspace(fmin, fmax, nbins + 1)
    out = []
    for l in range(len(vels)):
        a = pa[l].real
        b = pb[l].real
        x = px[l]
        wgt = np.sqrt(ca[l] * cx[l]) * sel
        wgt = wgt / max(wgt.max(), 1e-300)
        den = (wgt * g * g * a).sum()
        z = (wgt * g * x.real).sum() / den if den > 0 else np.nan
        bsum = (wgt * b).sum()
        zamp = np.sqrt(bsum / den) if den > 0 and bsum > 0 else np.nan
        asum = (wgt * a).sum()
        coh = (wgt * x.real).sum() / np.sqrt(asum * bsum) if asum > 0 and bsum > 0 else 0.0
        fc, zf = [], []
        for k in range(nbins):
            s = (fr >= edges[k]) & (fr < edges[k + 1])
            d = (wgt * g * g * a)[s].sum()
            if s.sum() and d > 0:
                fc.append(fr[s].mean())
                zf.append((wgt * g * x.real)[s].sum() / d)
        xs = (wgt * g * x).sum()
        out.append(dict(vx=vels[l][0], vy=vels[l][1], z=z, zamp=zamp, coh=coh,
                        xarg=float(np.angle(xs)) if den > 0 else 0.0,
                        f=np.array(fc), zf=np.array(zf),
                        fa=a[sel].sum() / tot_a, fb=b[sel].sum() / tot_b,
                        pa=a[sel].sum(), pb=b[sel].sum()))
    return out


def pyr_tint(n2, dx, diam, rmod, blur=0.6, npts=64):
    """Intensity transfer function of the sum of the 4 pupil images of a modulated pyramid WFS.

    An intensity ripple of spatial frequency f puts two sidebands at +-f around the PSF core. A
    sideband beats with the core only while both go through the same pyramid facet, so the
    ripple seen in the 4-image sum is the true one times the fraction of the modulation cycle
    for which core and core + f share a facet: 1 for |f| << rmod, 1/2 along the pyramid edges and
    1/4 elsewhere for |f| >> rmod. The core is given a Gaussian width `blur` [lambda/D] (its own
    size, or a seeing-broadened residual). f is converted with diam [m] to cycles per aperture.
    Returns (n2, n2) on the FFT frequency grid.
    """
    from math import erf, sqrt
    f = np.fft.fftfreq(n2, dx) * diam
    cdf = np.vectorize(lambda v: 0.5 * (1.0 + erf(v / sqrt(2.0))))
    out = np.zeros((n2, n2))
    for th in (np.arange(npts) + 0.5) * 2 * np.pi / npts:
        mx, my = rmod * np.cos(th), rmod * np.sin(th)
        qx = 1.0 - np.abs(cdf((mx + f) / blur) - cdf(mx / blur))
        qy = 1.0 - np.abs(cdf((my + f) / blur) - cdf(my / blur))
        out += qy[:, None] * qx[None, :]
    return out / npts
