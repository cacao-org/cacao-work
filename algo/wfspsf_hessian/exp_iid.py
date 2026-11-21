#!/usr/bin/env python3
"""Experiments on independent wavefront draws.

Does a degree-2 polynomial of the WFS modes predict the PSF, how many samples does it take,
and what is the structure of the fitted per-pixel Hessians?

Usage: exp_iid.py {quick,minifull,ref,extra,amp,bin1}
Results go to out/<tag>.npz (per-pixel sums of squares, spectra, Hessian statistics).
"""
import os
import sys
import time

import numpy as np

import hessmodel as hm
from toysim import Optics, add_photon_noise, mode_sigmas

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
REGIONS = (("core<1.25", 0.0, 1.25), ("1.25-4", 1.25, 4.0), ("4-8", 4.0, 8.0), (">8", 8.0, 99.0))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def summ(sse, sst, r):
    """Pooled R2 (1 - sum SSE / sum SST) in radial zones [lambda/D]."""
    return " ".join(
        f"{name}:{1 - sse[(r >= lo) & (r < hi)].sum() / sst[(r >= lo) & (r < hi)].sum():6.3f}"
        for name, lo, hi in REGIONS if ((r >= lo) & (r < hi)).any())


def fit_suite(a_tr, y_tr, a_te, y_te, ksubs=(), nsnaps=(), corr=False, chunk=4000):
    """Fit linear and quadratic models; return sst, {key: sse map}, theta of the full fit.

    Keys are "<model>_k<modes>_n<samples>", models: quad (least squares), lin (least squares,
    linear terms only), corr (quadratic, plain correlation R/n: assumes white Gaussian modes).
    """
    n, k = a_tr.shape
    snaps = sorted(set(list(nsnaps) + [n]))
    edges = sorted(set(list(range(0, n, chunk)) + snaps))
    fit = hm.QuadFit(k, y_tr.shape[1], dtype=np.float32)
    snap = {}
    for i0, i1 in zip(edges[:-1], edges[1:]):
        fit.update(hm.quad_features(a_tr[i0:i1]), y_tr[i0:i1])
        if i1 in snaps:
            snap[i1] = fit.snapshot() if i1 < n else (fit.g, fit.r, fit.n)
    z_te = hm.quad_features(a_te)
    yt = np.asarray(y_te, np.float64)
    sst = hm.sse(yt.mean(0)[None], yt)
    res, theta = {}, None
    for ns in snaps:
        g, r, nn = snap[ns]
        th = hm.solve(g, r, nn)
        res[f"quad_k{k}_n{ns}"] = hm.sse(z_te @ th, yt)
        li = np.arange(1 + k)
        res[f"lin_k{k}_n{ns}"] = hm.sse(z_te[:, li] @ hm.solve(g, r, nn, li), yt)
        if corr:
            # Cross-moments only (no Gram inversion): exact in expectation for white Gaussian
            # modes. Outputs must be centred first, or their mean leaks into every feature.
            zbar, ybar = g[:, 0] / nn, r[0] / nn
            thc = r / nn - np.outer(zbar, ybar)
            thc[0] = ybar - zbar[1:] @ thc[1:]
            res[f"corr_k{k}_n{ns}"] = hm.sse(z_te @ thc, yt)
            res[f"corrraw_k{k}_n{ns}"] = hm.sse(z_te @ (r / nn), yt)
        if ns == n:
            theta = th
    g, r, nn = snap[n]
    for ks in ksubs:
        if ks >= k:
            continue
        idx = hm.sub_features(k, ks)
        res[f"quad_k{ks}_n{n}"] = hm.sse(z_te[:, idx] @ hm.solve(g, r, nn, idx), yt)
        li = np.arange(1 + ks)
        res[f"lin_k{ks}_n{n}"] = hm.sse(z_te[:, li] @ hm.solve(g, r, nn, li), yt)
    return sst, res, theta, z_te


def coeff_analysis(theta, sig, tay):
    """Compare fitted (c, g, H) with the Taylor expansion, in whitened mode coordinates."""
    k = len(sig)
    c, g, h = hm.unpack(theta, k)
    w2 = sig[:, None, None] * sig[None, :, None]
    ts, tp = tay["hs"] * w2, tay["hp"] * w2
    tt = ts + tp
    den = (tt**2).sum((0, 1))
    tg = tay["g"] * sig[:, None]
    ev_f, vec_f = hm.eig_desc(h)
    ev_t, _ = hm.eig_desc(tt)
    ev_s, vec_s = hm.eig_desc(ts)
    f2, fneg = hm.channel_fractions(ev_f)
    t2, tneg = hm.channel_fractions(ev_t)
    s2, _ = hm.channel_fractions(ev_s)
    return dict(
        h_gain=(h * tt).sum((0, 1)) / den,
        h_relerr=np.sqrt(((h - tt) ** 2).sum((0, 1)) / den),
        h_norm_tay=np.sqrt(den),
        hs_norm=np.sqrt((ts**2).sum((0, 1))),
        hp_norm=np.sqrt((tp**2).sum((0, 1))),
        g_gain=(g * tg).sum(0) / np.maximum((tg**2).sum(0), 1e-300),
        g_relerr=np.sqrt(((g - tg) ** 2).sum(0) / np.maximum((tg**2).sum(0), 1e-300)),
        g_norm_tay=np.sqrt((tg**2).sum(0)),
        c_fit=c, c_tay=tay["c0"],
        ev_fit=ev_f.astype(np.float32), ev_tay=ev_t.astype(np.float32),
        ev_spk=ev_s.astype(np.float32),
        top2_fit=f2, neg_fit=fneg, top2_tay=t2, neg_tay=tneg, top2_spk=s2,
        cos2=hm.subspace_cos(vec_f[:, :, :2], vec_s[:, :, :2]),
    )


def pyr_modes(wfs_tr, wfs_te, nph, kmax, rng):
    """Photon-noise-weighted PCA of (noisy) pyramid images -> whitened modes."""
    wtr = add_photon_noise(wfs_tr, nph, rng)
    wte = add_photon_noise(wfs_te, nph, rng)
    pca = hm.PCA().fit(wtr, weight=1.0 / np.sqrt(np.maximum(wtr.mean(0), 1e-12)))
    return pca.transform(wtr, kmax), pca.transform(wte, kmax), pca


def wfs_linearity(a, x):
    """R2 of each WFS PCA mode as a linear function of the true whitened modes x, and of
    each true mode as a linear function of the WFS PCA modes."""
    a = np.asarray(a, np.float64)
    x = np.asarray(x, np.float64)
    fa = x @ np.linalg.solve(x.T @ x, x.T @ a)
    fx = a @ np.linalg.solve(a.T @ a, a.T @ x)
    return 1 - ((a - fa) ** 2).sum(0) / (a**2).sum(0), 1 - ((x - fx) ** 2).sum(0) / (x**2).sum(0)


def put(res, prefix, sst, d):
    res[f"{prefix}__sst"] = sst
    for key, val in d.items():
        res[f"{prefix}__{key}"] = val


def run(opt, tay, sigtot, ntrain, ntest, seed, tag, full=False, pyr=True):
    """One wavefront amplitude: forward model, then oracle-WFS and pyramid-WFS fits."""
    rng = np.random.default_rng(seed)
    k = opt.kmodes
    sig = mode_sigmas(k, sigtot)
    b = (rng.standard_normal((ntrain + ntest, k)) * sig).astype(np.float32)
    t = time.time()
    psf, wfs = opt.forward(b, want_wfs=pyr)
    log(f"[{tag}] forward model, {len(b)} samples: {time.time() - t:.0f} s")
    y_tr, y_te = psf[:ntrain], psf[ntrain:]
    x = (b / sig).astype(np.float64)
    x_tr, x_te = x[:ntrain], x[ntrain:]
    r = opt.psf_r
    res = dict(sig=sig, r=r, sigtot=sigtot, ntrain=ntrain, psf_mean=y_tr.mean(0),
               psf_std=y_tr.std(0), c0=tay["c0"], half=opt.psf_half / opt.ld, npsf=opt.npsf,
               pix_per_ld=opt.ld / opt.psf_bin)
    nmax = f"n{ntrain}"

    # Oracle WFS: the modes are the true (whitened) KL coefficients.
    ksubs = (10, 20, 40, 60) if full else ()
    nsnaps = [m for m in (2000, 5000, 10000, 20000, 50000, 100000) if m < ntrain] if full else ()
    t = time.time()
    sst, d, theta, z_te = fit_suite(x_tr, y_tr, x_te, y_te, ksubs, nsnaps, corr=full)
    put(res, "oracle", sst, d)
    log(f"[{tag}] oracle fits: {time.time() - t:.0f} s")
    log(f"   oracle quad  R2  {summ(d[f'quad_k{k}_{nmax}'], sst, r)}")
    log(f"   oracle lin   R2  {summ(d[f'lin_k{k}_{nmax}'], sst, r)}")
    for key, val in coeff_analysis(theta, sig, tay).items():
        res[f"coef__{key}"] = val
    log(f"   H gain vs Taylor (median, r in 1.25-8): "
        f"{np.median(res['coef__h_gain'][(r > 1.25) & (r < 8)]):.3f}, rel. err "
        f"{np.median(res['coef__h_relerr'][(r > 1.25) & (r < 8)]):.3f}")

    if full:
        # PSF-side PCA: how many components before the prediction is truncation-limited?
        pred = z_te @ theta
        yt = np.asarray(y_te, np.float64)
        for wname, wgt in (("sqrtmean", 1.0 / np.sqrt(res["psf_mean"])), ("none", None)):
            pca = hm.PCA().fit(y_tr, weight=wgt)
            res[f"psfpca_{wname}__ev"] = pca.ev
            for j in (10, 25, 50, 100, 200, 400, 800, 1600):
                res[f"psfpca_{wname}__pred_j{j}"] = hm.sse(pca.project(pred, j), yt)
                res[f"psfpca_{wname}__ceil_j{j}"] = hm.sse(pca.project(yt, j), yt)
            log(f"   PSF PCA ({wname}) J=100: model "
                f"{summ(res[f'psfpca_{wname}__pred_j100'], sst, r)} | ceiling "
                f"{summ(res[f'psfpca_{wname}__ceil_j100'], sst, r)}")
        del pred
        # Noisy linear WFS: errors-in-variables. Expect H shrunk by 1/(1+s2).
        for s2 in (0.1, 0.3, 1.0, 3.0):
            an = (x + np.sqrt(s2) * rng.standard_normal(x.shape)) / np.sqrt(1 + s2)
            sst, d, th, _ = fit_suite(an[:ntrain], y_tr, an[ntrain:], y_te)
            put(res, f"oraclenoise{s2}", sst, d)
            ca = coeff_analysis(th, sig, tay)
            res[f"oraclenoise{s2}__h_gain"] = ca["h_gain"]
            res[f"oraclenoise{s2}__g_gain"] = ca["g_gain"]
            log(f"   oracle + noise s2={s2}: quad R2 {summ(d[f'quad_k{k}_{nmax}'], sst, r)} | "
                f"H gain {np.median(ca['h_gain'][(r > 1.25) & (r < 8)]):.3f}")
        # PSF photon noise: outputs are noisy, the truth used for scoring is not.
        for nph in (1e6, 1e4):
            yn = add_photon_noise(y_tr, nph, rng)
            sst, d, _, _ = fit_suite(x_tr, yn, x_te, y_te, (), nsnaps)
            put(res, f"psfnoise{nph:g}", sst, d)
            log(f"   PSF photon noise {nph:g}/frame: quad R2 "
                f"{summ(d[f'quad_k{k}_{nmax}'], sst, r)}")
            del yn
    del z_te

    if pyr:
        w_tr, w_te = wfs[:ntrain], wfs[ntrain:]
        levels = (None, 1e6, 1e5, 1e4, 1e3) if full else (None,)
        for nph in levels:
            kp = 120 if (full and nph is None) else k
            a_tr, a_te, pca = pyr_modes(w_tr, w_te, nph, kp, rng)
            name = "pyr" if nph is None else f"pyr{nph:g}"
            res[f"{name}__wfs_ev"] = pca.ev[:300]
            lin_a, lin_x = wfs_linearity(a_tr[:50000, :k], x_tr[:50000])
            res[f"{name}__lin_a"], res[f"{name}__lin_x"] = lin_a, lin_x
            t = time.time()
            ks = (20, 40, 60, 80, 100) if kp > k else ()
            sst, d, _, _ = fit_suite(a_tr, y_tr, a_te, y_te, ks)
            put(res, name, sst, d)
            log(f"[{tag}] pyramid ({name}, K={kp}) fits: {time.time() - t:.0f} s; WFS modes "
                f"linear in WF: median R2 {np.median(lin_a):.3f}; WF modes from WFS: "
                f"median R2 {np.median(lin_x):.3f}")
            for kk in sorted(set((k,) + tuple(ks) + (kp,))):
                log(f"   {name} K={kk:3d} quad R2 {summ(d[f'quad_k{kk}_{nmax}'], sst, r)}"
                    f" | lin {summ(d[f'lin_k{kk}_{nmax}'], sst, r)}")
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, f"{tag}.npz"), **res)
    log(f"[{tag}] saved")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    if mode == "quick":
        opt = Optics(kmodes=20)
        run(opt, opt.taylor(20), 0.3, 30000, 4000, 5, "quick", full=False)
    elif mode == "minifull":
        opt = Optics(kmodes=20)
        run(opt, opt.taylor(20), 0.3, 30000, 4000, 5, "minifull", full=True)
    elif mode == "ref":
        opt = Optics(kmodes=80)
        run(opt, opt.taylor(80), 0.3, 200000, 10000, 11, "ref", full=True)
    elif mode == "amp":
        opt = Optics(kmodes=80)
        tay = opt.taylor(80)
        for i, s in enumerate((0.1, 0.2, 0.5, 0.7, 1.0, 1.5)):
            run(opt, tay, s, 100000, 10000, 20 + i, f"amp{s:g}")
    elif mode == "extra":
        # Same samples as "ref" (same seed, same first draw). (1) Learning curve of the
        # cross-moment estimator. (2) Channel-constrained predictions: keep only the r largest
        # positive eigen-directions of each fitted per-pixel Hessian (rank<r>), or of the
        # augmented matrix [[c, g/2], [g/2, H]] (aug<r>: PSF = sum of r squared affine
        # channels). These are truncations of the unconstrained fit, not re-optimised fits.
        k, nt = 80, 200000
        opt = Optics(kmodes=k)
        rng = np.random.default_rng(11)
        sig = mode_sigmas(k, 0.3)
        b = (rng.standard_normal((210000, k)) * sig).astype(np.float32)
        psf, _ = opt.forward(b, want_wfs=False)
        x = (b / sig).astype(np.float64)
        r = opt.psf_r
        sst, d, theta, _ = fit_suite(x[:nt], psf[:nt], x[nt:], psf[nt:], (),
                                     (2000, 5000, 10000, 20000, 50000, 100000), corr=True)
        for n in (2000, 5000, 10000, 20000, 50000, 100000, 200000):
            log(f"N={n:6d} LS {summ(d[f'quad_k{k}_n{n}'], sst, r)} | centred cross-moments "
                f"{summ(d[f'corr_k{k}_n{n}'], sst, r)}")
        c, g, h = hm.unpack(theta, k)
        a_te, yt = x[nt:], psf[nt:].astype(np.float64)
        ev, vec = hm.eig_desc(h)
        base = c[None] + a_te @ g
        pred = base.copy()
        for j in range(8):
            pred += np.clip(ev[:, j], 0, None)[None] * (a_te @ vec[:, :, j].T) ** 2
            if j + 1 in (1, 2, 4, 8):
                d[f"rank{j + 1}_k{k}_n{nt}"] = hm.sse(pred, yt)
                log(f"H -> {j + 1} positive channel(s):  R2 "
                    f"{summ(d[f'rank{j + 1}_k{k}_n{nt}'], sst, r)}")
        m = np.empty((opt.npsf, k + 1, k + 1))
        m[:, 0, 0] = c
        m[:, 0, 1:] = m[:, 1:, 0] = g.T / 2.0
        m[:, 1:, 1:] = np.moveaxis(h, -1, 0)
        evm, vecm = np.linalg.eigh(m)
        evm, vecm = evm[:, ::-1], vecm[:, :, ::-1]
        at = np.concatenate([np.ones((len(a_te), 1)), a_te], 1)
        pred = np.zeros_like(yt)
        for j in range(8):
            pred += np.clip(evm[:, j], 0, None)[None] * (at @ vecm[:, :, j].T) ** 2
            if j + 1 in (1, 2, 4, 8):
                d[f"aug{j + 1}_k{k}_n{nt}"] = hm.sse(pred, yt)
                log(f"sum of {j + 1} squared affine channel(s): R2 "
                    f"{summ(d[f'aug{j + 1}_k{k}_n{nt}'], sst, r)}")
        res = dict(r=r, evm=evm.astype(np.float32))
        put(res, "oracle", sst, d)
        np.savez_compressed(os.path.join(OUT, "refextra.npz"), **res)
    elif mode == "bin1":
        opt = Optics(kmodes=80, psf_half=36, psf_bin=1)
        tay = opt.taylor(80)
        for i, s in enumerate((0.1, 0.3)):
            run(opt, tay, s, 100000, 10000, 40 + i, f"bin1_amp{s:g}", pyr=False)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
