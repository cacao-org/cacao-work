#!/usr/bin/env python3
"""Channel models: is the PSF an incoherent sum of two squared channels?

Three models of each PSF pixel, all functions of the true whitened modes a (K of them):
  poly2 : c + g.a + a^T H a, unconstrained symmetric H (linear least squares);
  aff2  : (alpha_1 + beta_1.a)^2 + (alpha_2 + beta_2.a)^2, two squared affine channels,
          i.e. real and imaginary parts of a field that is affine in the modes;
  quad2 : q_1(a)^2 + q_2(a)^2 with q_c degree-2 polynomials, i.e. real and imaginary parts
          of a field expanded to second order in the modes.
aff2 and quad2 are fitted by L-BFGS, started from the poly2 solution. Pixels: a radial cut.

Usage: exp_channels.py [quick]
"""
import os
import sys
import time

import numpy as np

import hessmodel as hm
from exp_iid import OUT, log
from toysim import Optics, mode_sigmas


def init_channels(theta, k):
    """Starting points for aff2 (F=1+K) and quad2 (F=nfeat) from the poly2 coefficients."""
    c, g, h = hm.unpack(theta, k)
    npx = c.size
    la = np.zeros((1 + k, npx, 2))
    lq = np.zeros((theta.shape[0], npx, 2))
    for p in range(npx):
        # aff2: two leading positive eigen-directions of the augmented matrix.
        m = np.empty((k + 1, k + 1))
        m[0, 0], m[0, 1:], m[1:, 0], m[1:, 1:] = c[p], g[:, p] / 2, g[:, p] / 2, h[:, :, p]
        ev, vec = np.linalg.eigh(m)
        for j in range(2):
            la[:, p, j] = np.sqrt(max(ev[-1 - j], 0.0)) * vec[:, -1 - j]
        # quad2, gauge alpha_2 = 0: c = alpha^2, g = 2 alpha beta_1,
        # H = beta_1 beta_1^T + beta_2 beta_2^T + 2 alpha Gamma_1.
        alpha = np.sqrt(max(c[p], 1e-3 * abs(c).max()))
        b1 = g[:, p] / (2 * alpha)
        s = h[:, :, p] - np.outer(b1, b1)
        ev, vec = np.linalg.eigh(s)
        b2 = np.sqrt(max(ev[-1], 0.0)) * vec[:, -1]
        g1 = (s - np.outer(b2, b2)) / (2 * alpha)
        zero = np.zeros((k, k, 1))
        lq[:, p, 0] = hm.pack(np.array([alpha]), b1[:, None], g1[:, :, None])[:, 0]
        lq[:, p, 1] = hm.pack(np.array([0.0]), b2[:, None], zero)[:, 0]
    return la, lq


def main():
    quick = len(sys.argv) > 1 and sys.argv[1] == "quick"
    k = 20 if quick else 80
    ntr, nte = (20000, 4000) if quick else (100000, 10000)
    amps = (0.3, 0.7) if quick else (0.3, 0.5, 0.7, 1.0)
    opt = Optics(kmodes=k)
    n = opt.nside
    ctr = n // 2
    pix = np.arange(ctr, n) + ctr * n  # +x half of the central row, 3 pixels per lambda/D
    r = opt.psf_r[pix]
    res = dict(r=r, pix=pix, amps=np.array(amps))
    for ia, sigtot in enumerate(amps):
        rng = np.random.default_rng(60 + ia)
        sig = mode_sigmas(k, sigtot)
        b = (rng.standard_normal((ntr + nte, k)) * sig).astype(np.float32)
        psf, _ = opt.forward(b, want_wfs=False)
        y = psf[:, pix].astype(np.float64)
        del psf
        scale = y[:ntr].std(0)
        y /= scale  # unit-variance outputs: a common scale for the optimiser
        x = (b / sig).astype(np.float64)
        z = hm.quad_features(x)
        ztr, zte, ytr, yte = z[:ntr], z[ntr:], y[:ntr], y[ntr:]
        sst = hm.sse(yte.mean(0)[None], yte)
        theta = hm.solve(ztr.T @ ztr, ztr.T @ ytr, ntr)
        li = np.arange(1 + k)
        thl = hm.solve(ztr[:, li].T @ ztr[:, li], ztr[:, li].T @ ytr, ntr)
        out = dict(lin=hm.sse(zte[:, li] @ thl, yte), poly2=hm.sse(zte @ theta, yte))
        la, lq = init_channels(theta, k)
        for name, l0, cols in (("aff2", la, li), ("quad2", lq, slice(None))):
            t = time.time()
            p0 = ((zte[:, cols] @ l0.reshape(l0.shape[0], -1)).reshape(nte, -1, 2) ** 2).sum(2)
            lf, info = hm.fit_channels(ztr[:, cols], ytr, l0, maxiter=60 if quick else 300)
            pf = ((zte[:, cols] @ lf.reshape(lf.shape[0], -1)).reshape(nte, -1, 2) ** 2).sum(2)
            ptr = ((ztr[:, cols] @ lf.reshape(lf.shape[0], -1)).reshape(ntr, -1, 2) ** 2).sum(2)
            out[name + "_init"], out[name] = hm.sse(p0, yte), hm.sse(pf, yte)
            out[name + "_train"] = hm.sse(ptr, ytr) / hm.sse(ytr.mean(0)[None], ytr)
            log(f"[{sigtot}] {name}: {info.nit} iterations, {time.time() - t:.0f} s, "
                f"loss {info.fun:.4f}")
        res[f"amp{sigtot:g}__sst"] = sst
        for key, val in out.items():
            res[f"amp{sigtot:g}__{key}"] = val
        for zname, lo, hi in (("core<1.25", 0, 1.25), ("1.25-4", 1.25, 4), ("4-8", 4, 8),
                              (">8", 8, 99)):
            sel = (r >= lo) & (r < hi)
            log(f"[{sigtot}] {zname:>9} ({sel.sum():2d} px) median R2: " + "  ".join(
                f"{key} {np.median(1 - out[key][sel] / sst[sel]):.3f}"
                for key in ("lin", "poly2", "aff2_init", "aff2", "quad2_init", "quad2")))
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, "channels_quick.npz" if quick else "channels.npz"),
                        **res)
    log("saved")


if __name__ == "__main__":
    main()
