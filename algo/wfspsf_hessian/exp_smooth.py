#!/usr/bin/env python3
"""WFS noise in a time series: does temporal smoothing of the WFS modes restore the fit?

Same temporal model as exp_sync.py (30 modes, 0.3 rad RMS, smooth stationary process per mode,
time constants 1.5 to 5 WFS frames). The PSF camera runs at the WFS rate, synchronised. The WFS
modes are the true frame-averaged modes plus white noise of relative variance s2. Three ways to
form the quadratic features:
  raw     : the noisy modes of the same frame;
  gauss   : noisy modes smoothed in time by a symmetric Gaussian kernel, width chosen by the
            held-out R2 of the fit itself;
  wiener  : per-mode non-causal Wiener smoother built from the noisy modes alone: the noise
            variance is the step of the autocovariance at lag 0 (noise is white, signal is not).

Usage: exp_smooth.py [quick]
"""
import os
import sys

import numpy as np

import hessmodel as hm
from exp_iid import OUT, log, summ
from exp_sync import NSUB, frames
from toysim import Optics, ar2_series, mode_sigmas


def gauss_smooth(a, width):
    if width <= 0:
        return a
    j = np.arange(-int(4 * width) - 1, int(4 * width) + 2)
    h = np.exp(-0.5 * (j / width) ** 2)
    h /= h.sum()
    return np.apply_along_axis(lambda v: np.convolve(v, h, mode="same"), 0, a)


def wiener_smooth(a, half=10):
    """Non-causal FIR Wiener smoother per mode, from the autocovariance of the noisy series."""
    n, k = a.shape
    out = np.empty_like(a)
    noise = np.empty(k)
    for i in range(k):
        v = a[:, i] - a[:, i].mean()
        c = np.array([np.mean(v[: n - j] * v[j:]) for j in range(2 * half + 1)])
        c0 = (4.0 * c[1] - c[2]) / 3.0  # even parabola through lags 1, 2: signal power at lag 0
        c0 = min(max(c0, c[1]), c[0])
        noise[i] = c[0] - c0
        r = c.copy()
        r[0] = c0
        idx = np.abs(np.arange(-half, half + 1)[:, None] - np.arange(-half, half + 1)[None, :])
        w = np.linalg.solve(r[idx] + noise[i] * np.eye(2 * half + 1), r[np.abs(
            np.arange(-half, half + 1))])
        out[:, i] = np.convolve(v, w[::-1], mode="same")
    return out, noise


def main():
    quick = len(sys.argv) > 1 and sys.argv[1] == "quick"
    k = 30
    nw = 12000 if quick else 60000
    opt = Optics(kmodes=k)
    rng = np.random.default_rng(7)
    sig = mode_sigmas(k, 0.3)
    tau = np.geomspace(5.0, 1.5, k)
    b = ar2_series(nw * NSUB, sig, tau * NSUB, rng)
    psf, _ = opt.forward(b, want_wfs=False)
    y = frames(psf, NSUB, 0).astype(np.float64)
    del psf
    x = (b / sig).reshape(nw, NSUB, k).mean(1).astype(np.float64)
    x /= x.std(0)
    ntr = int(0.8 * nw)
    sst = hm.sse(y[ntr:].mean(0)[None], y[ntr:])
    r = opt.psf_r
    res = dict(r=r, sst=sst)

    def score(a):
        a = (a - a[:ntr].mean(0)) / a[:ntr].std(0)
        z = hm.quad_features(a)
        th = hm.solve(z[:ntr].T @ z[:ntr], z[:ntr].T @ y[:ntr], ntr)
        return hm.sse(z[ntr:] @ th, y[ntr:])

    e = score(x)
    res["clean"] = e
    log(f"noiseless modes:            R2 {summ(e, sst, r)}")
    widths = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
    for s2 in (0.3, 1.0, 3.0):
        a = x + np.sqrt(s2) * rng.standard_normal(x.shape)
        e = score(a)
        res[f"s{s2:g}__raw"] = e
        log(f"s2={s2:g} raw:                R2 {summ(e, sst, r)}")
        best = None
        for w in widths:
            e = score(gauss_smooth(a, w))
            res[f"s{s2:g}__gauss{w:g}"] = e
            tot = 1 - e.sum() / sst.sum()
            if best is None or tot > best[0]:
                best = (tot, w, e)
        log(f"s2={s2:g} gauss, sigma={best[1]:g} fr: R2 {summ(best[2], sst, r)}")
        aw, nv = wiener_smooth(a)
        e = score(aw)
        res[f"s{s2:g}__wiener"] = e
        log(f"s2={s2:g} wiener:             R2 {summ(e, sst, r)}   (noise variance "
            f"estimated / true: median {np.median(nv / s2):.2f})")
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, "smooth_quick.npz" if quick else "smooth.npz"), **res)
    log("saved")


if __name__ == "__main__":
    main()
