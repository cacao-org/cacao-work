#!/usr/bin/env python3
"""Unit checks for hessmodel.py and toysim.py (pytest-compatible, or run directly)."""
import numpy as np

import hessmodel as hm
from toysim import Optics


def test_features_unpack_pack():
    rng = np.random.default_rng(0)
    k, j = 7, 3
    a = rng.standard_normal((50, k))
    theta = rng.standard_normal((hm.nfeat(k), j))
    c, g, h = hm.unpack(theta, k)
    direct = c[None] + a @ g + np.einsum("nk,nl,klj->nj", a, a, h)
    assert np.allclose(hm.quad_features(a) @ theta, direct)
    assert np.allclose(h, np.swapaxes(h, 0, 1))
    assert np.allclose(hm.pack(c, g, h), theta)


def test_sub_features():
    rng = np.random.default_rng(1)
    a = rng.standard_normal((20, 9))
    assert np.allclose(hm.quad_features(a)[:, hm.sub_features(9, 4)], hm.quad_features(a[:, :4]))


def test_streaming_fit_recovers_coefficients():
    rng = np.random.default_rng(2)
    k, j, n = 6, 4, 4000
    theta = rng.standard_normal((hm.nfeat(k), j))
    fit = hm.QuadFit(k, j)
    for _ in range(4):
        a = rng.standard_normal((n // 4, k))
        z = hm.quad_features(a)
        fit.update(z, z @ theta)
    assert np.allclose(hm.solve(fit.g, fit.r, fit.n, ridge=1e-12), theta, atol=1e-6)


def test_window_mean_matches_brute_force():
    rng = np.random.default_rng(3)
    a = rng.standard_normal((200, 3))
    ff = hm.FrameFeatures(a)
    t0 = np.array([3.0, 10.25, 57.9])
    t1 = t0 + np.array([1.0, 4.5, 16.3])
    fine = 400  # sub-samples per frame
    zf = np.repeat(ff.z, fine, axis=0)
    for i in range(3):
        brute = zf[int(round(t0[i] * fine)) : int(round(t1[i] * fine))].mean(0)
        assert np.allclose(ff.mean(t0, t1)[i], brute, atol=1e-9)


def test_find_lag_on_averaged_quadratic_signal():
    rng = np.random.default_rng(4)
    nfr, k, m, lag = 20000, 4, 3, 1.6
    e = rng.standard_normal((nfr + 50, k))
    a = np.apply_along_axis(lambda v: np.convolve(v, np.ones(6) / 6, "valid"), 0, e)[:nfr]
    a /= a.std(0)
    ff = hm.FrameFeatures(a)
    theta = rng.standard_normal((ff.z.shape[1], 5))
    start = np.arange(20, nfr - 40, m).astype(float)  # true exposure start, WFS frames
    y = ff.mean(start, start + m) @ theta
    y += 0.05 * y.std(0) * rng.standard_normal(y.shape)
    est, r2, _ = hm.find_lag(ff, y, start + lag, start + lag + m, np.arange(-6.0, 6.1, 1.0))
    assert abs(est - lag) < 0.02 and r2 > 0.95


def test_channel_loss_gradient_and_fit():
    from scipy.optimize import check_grad

    rng = np.random.default_rng(8)
    n, k, npx = 400, 3, 2
    z = np.concatenate([np.ones((n, 1)), rng.standard_normal((n, k))], 1)
    ltrue = rng.standard_normal((1 + k, npx, 2))
    y = ((z @ ltrue.reshape(1 + k, -1)).reshape(n, npx, 2) ** 2).sum(2)
    w, shape = 1.0 / y.var(0), ltrue.shape
    v = rng.standard_normal(ltrue.size)
    err = check_grad(lambda u: hm.channel_loss(u, z, y, w, shape)[0],
                     lambda u: hm.channel_loss(u, z, y, w, shape)[1], v)
    assert err < 1e-5 * np.linalg.norm(hm.channel_loss(v, z, y, w, shape)[1])
    lf, info = hm.fit_channels(z, y, ltrue + 0.05 * rng.standard_normal(shape), maxiter=500)
    assert info.fun < 1e-8  # noiseless data, start near the truth: exact fit


def test_taylor_expansion_matches_exact_psf():
    o = Optics(kmodes=8, psf_half=15, psf_bin=2)
    t = o.taylor(8)
    rng = np.random.default_rng(5)
    d = rng.standard_normal((2, 8))
    d /= np.sqrt((d**2).sum(1, keepdims=True))
    err = []
    for amp in (0.02, 0.04):
        b = amp * d
        psf, _ = o.forward(b, want_wfs=False)
        h = (t["hs"] + t["hp"]).astype(np.float64)
        model = t["c0"][None] + b @ t["g"] + np.einsum("nk,nl,klp->np", b, b, h)
        err.append(np.abs(psf - model).max())
    assert 6.0 < err[1] / err[0] < 10.0  # third-order remainder


def test_pyramid_response_is_linear_for_small_modes():
    o = Optics(kmodes=8)
    b = np.zeros((3, 8))
    b[1, 3], b[2, 3] = 0.02, -0.02
    _, w = o.forward(b)
    odd, even = (w[1] - w[2]) / 2, (w[1] + w[2]) / 2 - w[0]
    assert np.linalg.norm(even) < 0.05 * np.linalg.norm(odd)


def test_pipeline_end_to_end_on_simulated_streams():
    """Pyramid frames and slower, late-stamped PSF frames in; lag and model out."""
    from toysim import add_photon_noise, ar2_series, mode_sigmas

    k, nsub, m, nw, lag = 10, 2, 3, 9000, 1.4
    o = Optics(kmodes=k, psf_half=15)
    rng = np.random.default_rng(6)
    sig = mode_sigmas(k, 0.25)
    b = ar2_series(nw * nsub, sig, np.full(k, 3.0 * nsub), rng)
    psf, wfs = o.forward(b)
    wfr = add_photon_noise(wfs.reshape(nw, nsub, -1).mean(1), 1e7, rng)
    off = 1  # the PSF exposures start half a WFS frame late
    nfr = (len(psf) - off) // (m * nsub)
    fr = psf[off : off + nfr * m * nsub].reshape(nfr, m * nsub, -1).mean(1)
    start = off / nsub + np.arange(nfr) * m
    out = hm.pipeline(wfr, fr, start + lag, start + lag + m, k, np.arange(-5.0, 5.1, 1.0), 10)
    assert abs(out["lag"] - lag) < 0.05
    assert np.median(out["r2"]) > 0.9


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
