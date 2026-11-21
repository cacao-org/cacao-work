#!/usr/bin/env python3
"""Individual frames: wavefront, WFS image, PSF, PSF reconstructed from the WFS image, residual.

The model is the Hessian model fitted on the pyramid PCA modes (K = 80), i.e. the full chain
WFS image -> PCA modes -> degree-2 polynomial -> PSF. With the same seed and frame count as
`exp_iid.py ref` (or `amp`), it is the same model as the "pyramid PCA modes" one reported there.
The frames shown are the first test frames, in order: they are not selected.

Usage: exp_gallery.py [rms=0.3] [ntrain=200000] [seed=11] [photons per WFS frame, 0 = none]
"""
import os
import sys
import time

import numpy as np

import hessmodel as hm
from exp_iid import OUT, log
from toysim import Optics, add_photon_noise, mode_sigmas


def main():
    sigtot = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
    ntrain = int(sys.argv[2]) if len(sys.argv) > 2 else 200000
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 11
    nph = float(sys.argv[4]) if len(sys.argv) > 4 and float(sys.argv[4]) > 0 else None
    k, nshow = 80, 8
    opt = Optics(kmodes=k)
    rng = np.random.default_rng(seed)
    sig = mode_sigmas(k, sigtot)
    # Same draw as exp_iid.run (ntrain + 10000 frames); only the first test frames are kept.
    b = (rng.standard_normal((ntrain + 10000, k)) * sig).astype(np.float32)[: ntrain + nshow]
    t = time.time()
    psf, wfs = opt.forward(b)
    log(f"forward model, {len(b)} frames: {time.time() - t:.0f} s")
    wfs = add_photon_noise(wfs, nph, rng)
    wgt = 1.0 / np.sqrt(np.maximum(wfs[:ntrain].mean(0), 1e-12))
    pca = hm.PCA().fit(wfs[:ntrain], weight=wgt)
    a = pca.transform(wfs, k)
    fit = hm.QuadFit(k, opt.npsf)
    for i in range(0, ntrain, 4000):
        fit.update(hm.quad_features(a[i : i + 4000]), psf[i : i + 4000])
    zs = hm.quad_features(a[ntrain:])
    lin = np.arange(1 + k)
    pred = zs @ hm.solve(fit.g, fit.r, fit.n)
    pred_lin = zs[:, lin] @ hm.solve(fit.g, fit.r, fit.n, lin)
    truth = psf[ntrain:].astype(np.float64)
    mean = psf[:ntrain].mean(0, dtype=np.float64)
    psf0, wfs0 = opt.forward(np.zeros((1, k)))
    for i in range(nshow):
        dev = ((truth[i] - mean) ** 2).sum()
        eh = 1 - ((truth[i] - pred[i]) ** 2).sum() / dev
        el = 1 - ((truth[i] - pred_lin[i]) ** 2).sum() / dev
        log(f"frame {i}: WF {np.sqrt((b[ntrain + i] ** 2).sum()):.3f} rad RMS, explained "
            f"fraction of (PSF - mean PSF): Hessian {eh:.4f}, linear {el:.4f}")
    tag = f"gallery_rms{sigtot:g}" + ("" if nph is None else f"_ph{nph:g}")
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(
        os.path.join(OUT, tag + ".npz"), sigtot=sigtot, ntrain=ntrain,
        nph=0 if nph is None else nph,
        phi=b[ntrain:].astype(np.float64) @ opt.modes, wfs=wfs[ntrain:], psf=truth, pred=pred,
        pred_lin=pred_lin, psf_mean=mean, psf0=psf0[0], wfs0=wfs0[0], npb=opt.npb,
        pidx=opt.pidx, nw=opt.nw, wfs_sel=opt.wfs_sel, wfs_centres=np.array(opt.wfs_centres),
        nside=opt.nside, half=opt.psf_half / opt.ld, dpix=opt.dpix, wfs_pitch=opt.wfs_pitch,
        pix_per_ld=opt.ld / opt.psf_bin)
    log(f"saved {tag}")


if __name__ == "__main__":
    main()
