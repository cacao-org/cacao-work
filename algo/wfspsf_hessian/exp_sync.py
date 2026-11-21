#!/usr/bin/env python3
"""Time-series experiment: a fast pyramid WFS and a slower PSF camera with an unknown lag.

The wavefront evolves on a grid of NSUB steps per WFS frame. A WFS frame is the average of the
pyramid image over its NSUB steps (plus photon noise); a PSF frame is the average of the
instantaneous PSF over M WFS frames, starting at an arbitrary sub-step, and is time-stamped
with an offset (the lag to be recovered).

Part 1: recover the lag by maximising the held-out R2 of a small quadratic model.
Part 2: quality of the full model versus the way features are paired with PSF frames.

Usage: exp_sync.py [quick]
"""
import os
import sys
import time

import numpy as np

import hessmodel as hm
from exp_iid import OUT, log, summ
from toysim import Optics, add_photon_noise, ar2_series, mode_sigmas

NSUB = 4


def frames(psf, m_sub, off):
    """Average the sub-step PSF series into frames of m_sub steps starting at step off."""
    nfr = (len(psf) - off) // m_sub
    return psf[off : off + nfr * m_sub].reshape(nfr, m_sub, -1).mean(1)


def main():
    quick = len(sys.argv) > 1 and sys.argv[1] == "quick"
    k = 30
    nw = 16000 if quick else 96000
    opt = Optics(kmodes=k)
    rng = np.random.default_rng(3)
    sig = mode_sigmas(k, 0.3)
    tau = np.geomspace(5.0, 1.5, k)  # per-stage e-folding time, WFS frames
    t = time.time()
    b = ar2_series(nw * NSUB, sig, tau * NSUB, rng)
    psf, wfs = opt.forward(b)
    log(f"forward model, {len(b)} steps: {time.time() - t:.0f} s")
    wfr = add_photon_noise(wfs.reshape(nw, NSUB, -1).mean(1), 1e6, rng)
    del wfs
    pca = hm.PCA().fit(wfr, weight=1.0 / np.sqrt(wfr.mean(0)))
    a = pca.transform(wfr, k)  # whitened WFS modes; frame i spans [i, i+1)
    x = (b / sig).reshape(nw, NSUB, k).mean(1)
    res = dict(r=opt.psf_r, tau=tau, sig=sig, wfs_ev=pca.ev[:100])
    ac = np.array([np.mean(x[: nw - j] * x[j:], 0) for j in range(0, 41)])
    res["autocorr"] = ac / ac[0]

    # ---- Part 1: lag recovery -------------------------------------------------------------
    # Sync models, on the K WFS modes: lin = linear terms only; quad = full quadratic model;
    # lead12 = full quadratic model of the 12 highest-variance WFS modes (a tempting but poor
    # shortcut). These predict the 20 leading PCA modes of the PSF frames.
    # qonly = quadratic terms only, predicting the point-symmetric part of the PSF frames,
    # (I(u) + I(-u))/2: for a centro-symmetric pupil the linear response is odd in u, so this
    # is the Hessian part alone, as behind a coronagraph where the linear response vanishes.
    jsync = 20
    ff = hm.FrameFeatures(a)
    cols = dict(lin=np.arange(1 + k), quad=np.arange(ff.z.shape[1]),
                qonly=np.delete(np.arange(ff.z.shape[1]), np.arange(1, 1 + k)),
                lead12=hm.sub_features(k, 12))
    ffm = {name: (ff if name == "quad" else hm.FrameFeatures(z=ff.z[:, c]))
           for name, c in cols.items()}
    lags = np.arange(-8.0, 8.01, 1.0)
    fine = np.arange(-6.0, 10.01, 0.25)
    cases = ((0, 0.0), (1, 2.25), (2, -3.5), (3, 5.75))
    nseg = 8
    rows = []
    for m in (1, 4, 16):
        hw = 1.5 + 0.25 * m
        for off, lag_true in cases:
            fr0 = frames(psf, m * NSUB, off)
            t0 = off / NSUB + np.arange(len(fr0)) * m + lag_true  # stamped exposure start
            t1 = t0 + m
            for nph in (None, 1e4) if off == 1 else (None,):
                fr = add_photon_noise(fr0, nph, rng)
                npca = min(len(fr), 20000)  # frames used to define the PSF PCA modes
                y = hm.PCA().fit(fr[:npca]).transform(fr, jsync, whiten=False)
                fe = 0.5 * (fr + fr[:, ::-1])  # reversing the pixel order maps u to -u
                ye = hm.PCA().fit(fe[:npca]).transform(fe, jsync, whiten=False)
                del fe
                seg = np.array_split(np.arange(len(fr)), nseg)
                msg = f"M={m:2d} true lag {lag_true:+5.2f} PSF nph {str(nph):>7}:"
                for im, name in enumerate(cols):
                    if name == "lead12" and off != 1:
                        continue
                    fm, yy = ffm[name], (ye if name == "qonly" else y)
                    tt = time.time()
                    est, r2, _ = hm.find_lag(fm, yy, t0, t1, lags, halfwidth=hw)
                    dt = time.time() - tt
                    es = [hm.find_lag(fm, yy[sg], t0[sg], t1[sg], lags, halfwidth=hw)[0]
                          - lag_true for sg in seg]
                    rows.append((m, off, lag_true, 0 if nph is None else nph, im, est - lag_true,
                                 r2, np.mean(es), np.std(es), len(fr) // nseg, dt))
                    msg += (f" {name} {est - lag_true:+.3f} (R2 {r2:.2f}; seg "
                            f"{np.mean(es):+.3f}+-{np.std(es):.3f}; {dt:.0f}s)")
                    if off == 1 and nph is None:
                        ok = fm.valid(t0 - fine.max() - 1, t1 - fine.min() + 1)
                        ntr = int(0.7 * ok.sum())
                        res[f"curve_{name}_m{m}"] = np.array(
                            [hm.lag_r2(fm, yy[ok], t0[ok], t1[ok], lg, ntr) for lg in fine])
                log(msg)
    del ffm
    res["lags"] = fine
    res["lagtable"] = np.array(rows)
    res["lagmodels"] = np.array(list(cols))

    # ---- Part 2: full model versus pairing method ------------------------------------------
    nfeat = ff.z.shape[1]
    off = 2
    shifts = (0.25, 0.5, 1.0, 2.0, 4.0)
    for m in (1, 4, 16):
        fr = frames(psf, m * NSUB, off)
        t0 = off / NSUB + np.arange(len(fr)) * m  # true exposure start, WFS frames
        t1 = t0 + m
        ok = ff.valid(t0 - 5, t1 + 5)
        fr, t0, t1 = fr[ok].astype(np.float64), t0[ok], t1[ok]
        ntr = int(0.8 * len(fr))
        sst = hm.sse(fr[ntr:].mean(0)[None], fr[ntr:])
        res[f"fit_m{m}__sst"] = sst

        def score(zb, name):
            th = hm.solve(zb[:ntr].T @ zb[:ntr], zb[:ntr].T @ fr[:ntr], ntr)
            e = hm.sse(zb[ntr:] @ th, fr[ntr:])
            res[f"fit_m{m}__{name}"] = e
            log(f"M={m:2d} {name:>10}: R2 {summ(e, sst, opt.psf_r)}")

        log(f"M={m}: {ntr} training PSF frames, {nfeat} features")
        zex = ff.mean(t0, t1)
        score(zex, "exact")
        score(zex[:, : 1 + k], "exact_lin")
        score(hm.quad_features(zex[:, 1 : 1 + k]), "naive")
        if m == 1:
            tn = np.floor(t0 + 0.5)
            score(ff.mean(tn, tn + 1), "nearest")
        for d in shifts:
            score(ff.mean(t0 - d, t1 - d), f"lag{d:g}")
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, "sync_quick.npz" if quick else "sync.npz"), **res)
    log("saved")


if __name__ == "__main__":
    main()
