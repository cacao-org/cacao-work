#!/usr/bin/env python3
"""Estimation tools for the WFS -> PSF Hessian (degree-2 polynomial) model.

Model, for one PSF output y (a pixel or a PSF PCA coefficient) and the whitened WFS mode
vector a (K modes):

    y = c + g.a + a^T H a + residual

It is linear in (c, g, H), so it is fitted by least squares on the feature vector
z(a) = [1, a_k, (a_k^2 - 1)/sqrt(2), a_k a_l (k<l)], which is orthonormal when a is white and
Gaussian. Because the model is linear in z, a PSF frame exposed over several WFS frames obeys
the same model with z replaced by its average over the exposure: this is what makes the fit
possible with a science camera slower than the WFS, and what the lag scan relies on.
"""
import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize


class PCA:
    """PCA of an image set (N, npix) with optional per-pixel weights."""

    def fit(self, x, weight=None, chunk=20000):
        n, npix = x.shape
        self.mean = x.mean(0, dtype=np.float64)
        self.w = np.ones(npix) if weight is None else np.asarray(weight, np.float64)
        cov = np.zeros((npix, npix))
        for i in range(0, n, chunk):
            d = (x[i : i + chunk] - self.mean) * self.w
            cov += d.T @ d
        ev, vec = np.linalg.eigh(cov / n)
        self.ev = np.clip(ev[::-1], 0, None)
        self.vec = vec[:, ::-1]
        return self

    def transform(self, x, k, whiten=True):
        a = ((x - self.mean) * self.w) @ self.vec[:, :k]
        return a / np.sqrt(self.ev[:k]) if whiten else a

    def project(self, x, k):
        """Images reconstructed from their first k PCA coefficients."""
        a = ((x - self.mean) * self.w) @ self.vec[:, :k]
        return (a @ self.vec[:, :k].T) / self.w + self.mean


def nfeat(k):
    return 1 + k + k * (k + 1) // 2


def quad_features(a):
    """(N, K) whitened modes -> (N, F) features [1, a, Hermite-normalised products]."""
    a = np.asarray(a, np.float64)
    n, k = a.shape
    i, j = np.triu_indices(k)
    z = np.empty((n, 1 + k + i.size))
    z[:, 0] = 1.0
    z[:, 1 : 1 + k] = a
    q = a[:, i] * a[:, j]
    d = i == j
    q[:, d] = (q[:, d] - 1.0) / np.sqrt(2.0)
    z[:, 1 + k :] = q
    return z


def sub_features(k, ksub):
    """Indices, in the K-mode feature vector, of the features of the first ksub modes."""
    i, j = np.triu_indices(k)
    quad = np.flatnonzero((i < ksub) & (j < ksub)) + 1 + k
    return np.concatenate([[0], 1 + np.arange(ksub), quad])


def unpack(theta, k):
    """theta (F, J) -> c (J,), g (K, J), h (K, K, J) such that y = c + g.a + a^T h a."""
    theta = np.asarray(theta)
    i, j = np.triu_indices(k)
    q = theta[1 + k :]
    d = i == j
    h = np.zeros((k, k, theta.shape[1]), theta.dtype)
    h[i[~d], j[~d]] = q[~d] / 2.0
    h[j[~d], i[~d]] = q[~d] / 2.0
    h[i[d], j[d]] = q[d] / np.sqrt(2.0)
    c = theta[0] - q[d].sum(0) / np.sqrt(2.0)
    return c, theta[1 : 1 + k], h


def pack(c, g, h):
    """Inverse of unpack: (c (J,), g (K, J), h (K, K, J)) -> theta (F, J)."""
    k = g.shape[0]
    i, j = np.triu_indices(k)
    d = i == j
    q = np.where(d[:, None], np.sqrt(2.0) * h[i, j], 2.0 * h[i, j])
    return np.concatenate([(c + np.trace(h))[None], g, q], 0)


def channel_loss(v, z, y, w, shape):
    """Weighted squared error of y[n, p] ~ sum_c (z[n] . l[:, p, c])^2 and its gradient in l."""
    n = len(z)
    q = (z @ v.reshape(shape[0], -1)).reshape(n, shape[1], shape[2])
    res = (q**2).sum(2) - y
    grad = z.T @ ((2.0 / n) * (res * w)[:, :, None] * q).reshape(n, -1)
    return 0.5 * (res**2 * w).sum() / n, grad.ravel()


def fit_channels(z, y, l0, maxiter=300):
    """Fit y[n, p] ~ sum_c (z[n] . l[:, p, c])^2 by L-BFGS, starting from l0 (F, P, C).

    Each output p is modelled as an incoherent sum of C squared channels, every channel being
    linear in the features z (affine in the modes if z = [1, a]; a degree-2 polynomial of the
    modes if z is the quadratic feature vector). Outputs are weighted by 1/variance.
    """
    out = minimize(channel_loss, l0.ravel(), args=(z, y, 1.0 / y.var(0), l0.shape), jac=True,
                   method="L-BFGS-B", options=dict(maxiter=maxiter, maxcor=20))
    return out.x.reshape(l0.shape), out


class QuadFit:
    """Streaming normal equations: G = sum z z^T, R = sum z y^T. Memory is O(F^2 + F J).

    dtype is the precision of the per-batch products (the running sums are always float64).
    float32 halves the cost and is accurate to about 1e-6 per batch, which is harmless when the
    features are whitened and the frames outnumber the coefficients.
    """

    def __init__(self, k, nout, dtype=np.float64):
        self.k, self.nf, self.dtype = k, nfeat(k), dtype
        self.g = np.zeros((self.nf, self.nf))
        self.r = np.zeros((self.nf, nout))
        self.n = 0

    def update(self, z, y):
        """z: (B, F) features, already averaged over each PSF exposure; y: (B, J) outputs."""
        z = np.asarray(z, self.dtype)
        self.g += z.T @ z
        self.r += z.T @ np.asarray(y, self.dtype)
        self.n += len(z)

    def snapshot(self):
        return self.g.copy(), self.r.copy(), self.n


def solve(g, r, n, idx=None, ridge=1e-6):
    """Least-squares coefficients from accumulated (G, R, n), optionally on a feature subset."""
    if idx is not None:
        g, r = g[np.ix_(idx, idx)], r[idx]
    a = g / n
    a[np.diag_indices_from(a)] += ridge * np.trace(a) / len(a)
    return cho_solve(cho_factor(a, overwrite_a=True), r / n)


def sse(pred, truth):
    return ((pred - truth) ** 2).sum(0)


def eig_desc(h):
    """h (K, K, npix) symmetric -> eigenvalues (npix, K) descending, vectors (npix, K, K)."""
    ev, vec = np.linalg.eigh(np.moveaxis(np.asarray(h, np.float64), -1, 0))
    return ev[:, ::-1], vec[:, :, ::-1]


def channel_fractions(ev):
    """Shares of sum(ev^2): two largest positive eigenvalues, and all negative eigenvalues.

    For white Gaussian modes Var(a^T H a) = 2 sum(ev^2), so these are shares of the PSF
    variance produced by the quadratic term.
    """
    tot = (ev**2).sum(1)
    top2 = (np.clip(ev[:, :2], 0, None) ** 2).sum(1)
    neg = (np.clip(ev, None, 0) ** 2).sum(1)
    return top2 / tot, neg / tot


def subspace_cos(va, vb):
    """Principal-angle cosines between column spaces va, vb, each (npix, K, r)."""
    return np.linalg.svd(np.einsum("pki,pkj->pij", va, vb), compute_uv=False)


class FrameFeatures:
    """Exposure-averaged quadratic features of a uniformly sampled WFS mode series.

    WFS frame i spans [i, i+1) (time in WFS frames). The running integral of the features is
    piecewise linear, so the mean over any window [t0, t1), fractional ends included, costs
    two table look-ups.
    """

    def __init__(self, a=None, z=None):
        """a: (N, K) whitened modes, or z: (N, F) per-frame features (e.g. a subset)."""
        self.z = quad_features(a) if z is None else np.ascontiguousarray(z, np.float64)
        self.cs = np.concatenate([np.zeros((1, self.z.shape[1])), np.cumsum(self.z, 0)])
        self.nfr = len(self.z)

    def _cum(self, t):
        i = np.clip(np.floor(t).astype(np.int64), 0, self.nfr - 1)
        return self.cs[i] + (t - i)[:, None] * self.z[i]

    def mean(self, t0, t1):
        return (self._cum(t1) - self._cum(t0)) / (t1 - t0)[:, None]

    def valid(self, t0, t1, margin=0.0):
        return (t0 - margin >= 0) & (t1 + margin <= self.nfr)


def lag_r2(ff, y, t0, t1, lag, ntrain, idx=None, ridge=1e-6):
    """Held-out R2 of the quadratic model for a trial lag (PSF lags WFS by `lag` frames).

    Convention (as milk-mltools): the PSF frame stamped [t0, t1) saw the WFS over
    [t0 - lag, t1 - lag). Train on the first ntrain frames, test on the rest. idx selects a
    feature subset (e.g. the linear terms only).
    """
    zb = ff.mean(t0 - lag, t1 - lag)
    if idx is not None:
        zb = zb[:, idx]
    ztr, zte = zb[:ntrain], zb[ntrain:]
    th = solve(ztr.T @ ztr, ztr.T @ y[:ntrain], ntrain, ridge=ridge)
    yte = y[ntrain:]
    return 1.0 - sse(zte @ th, yte).sum() / sse(yte.mean(0)[None], yte).sum()


def find_lag(ff, y, t0, t1, lags, idx=None, train_frac=0.7, halfwidth=1.5, npts=7, niter=3):
    """Coarse scan over `lags`, then locate the centre of symmetry of the R2 peak.

    The peak of R2(lag) is not a smooth maximum: boxcar exposures give a cusp, and for
    exposures of about one WFS frame, interpolating between two noisy WFS frames averages
    their noise, which splits the top into two symmetric bumps. The refinement therefore fits
    a parabola on a window of +-halfwidth frames, re-centred on its own vertex until it
    settles: for a symmetric peak the vertex is the centre of symmetry, whatever the shape.
    Only frames valid for every trial lag are used, so all lags see the same data.
    Returns (lag, R2 at that lag, R2 curve over `lags`).
    """
    lags = np.asarray(lags, float)
    pad = 2.0 * halfwidth
    ok = ff.valid(t0 - lags.max() - pad, t1 - lags.min() + pad)
    y, t0, t1 = np.asarray(y, np.float64)[ok], t0[ok], t1[ok]
    ntrain = int(train_frac * len(y))
    curve = np.array([lag_r2(ff, y, t0, t1, lg, ntrain, idx) for lg in lags])
    c = lags[int(np.argmax(curve))]
    d = np.linspace(-halfwidth, halfwidth, npts)
    for _ in range(niter):
        v = [lag_r2(ff, y, t0, t1, c + dd, ntrain, idx) for dd in d]
        p = np.polyfit(d, v, 2)
        if p[0] >= 0:
            break
        c = c + float(np.clip(-p[1] / (2 * p[0]), -halfwidth, halfwidth))
    return float(c), float(lag_r2(ff, y, t0, t1, c, ntrain, idx)), curve


def pipeline(wfs, psf, t0, t1, k, lags, jsync=20, train_frac=0.8):
    """Reference implementation of the whole procedure on two recorded streams.

    wfs: (Nw, npix) WFS frames on a uniform clock, frame i spanning [i, i+1).
    psf: (Np, npsf) PSF frames stamped [t0, t1) in the same unit, with an unknown lag.
    Steps: noise-weighted PCA of the WFS (k whitened modes); lag search on the leading jsync
    PSF PCA modes; exposure-averaged quadratic features at that lag; least-squares fit of every
    PSF pixel on the first train_frac of the frames; R2 per pixel on the remaining frames.
    """
    pca = PCA().fit(wfs, weight=1.0 / np.sqrt(np.maximum(wfs.mean(0), 1e-12)))
    ff = FrameFeatures(pca.transform(wfs, k))
    y = PCA().fit(psf).transform(psf, jsync, whiten=False)
    lag, r2_lag, curve = find_lag(ff, y, t0, t1, lags)
    ok = ff.valid(t0 - lag, t1 - lag)
    zb, yy = ff.mean(t0[ok] - lag, t1[ok] - lag), np.asarray(psf, np.float64)[ok]
    ntr = int(train_frac * len(yy))
    fit = QuadFit(k, yy.shape[1])
    fit.update(zb[:ntr], yy[:ntr])
    theta = solve(fit.g, fit.r, fit.n)
    r2 = 1.0 - sse(zb[ntr:] @ theta, yy[ntr:]) / sse(yy[ntr:].mean(0)[None], yy[ntr:])
    c, g, h = unpack(theta, k)
    return dict(lag=lag, r2_lag=r2_lag, lag_curve=curve, wfs_pca=pca, theta=theta, c=c, g=g, h=h,
                r2=r2)
