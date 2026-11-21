"""Synchronisation kernels and Mdb estimators for the 2-WFS + 1-DM calibration study.

`sync_tool` and `est_tool` re-implement, in numpy, what mlt.tlmsync / mlt.sysid do in C
(milk-mltools: tlm_sync_unit.c, sysid_unit.c, commands.d/mltools.bash). They are a port written
from the source, not the C binary itself.
"""

import numpy as np

# --------------------------------------------------------------------------------------------
# Synchronisation (ports of mlt.tlmsync .mode=window and .mode=expint)
# --------------------------------------------------------------------------------------------


def _cum_integral(knots, x):
    """Cumulative integral of a piecewise-constant signal: x[k] on [knots[k], knots[k+1])."""
    c = np.zeros((len(knots), x.shape[1]))
    np.cumsum(x * np.diff(knots)[:, None], axis=0, out=c[1:])
    return c


def _eval_integral(knots, c, x, tq):
    tq = np.clip(tq, knots[0], knots[-1])
    idx = np.clip(np.searchsorted(knots, tq, side="right") - 1, 0, len(knots) - 2)
    return c[idx] + x[idx] * (tq - knots[idx])[:, None], tq


def tlmsync(t_ref, x, t_src, lag, mode, texp=0.0):
    """Resample x(t_src) onto t_ref + lag. mode 'window' or 'expint' as in mlt.tlmsync."""
    dt_ref = np.median(np.diff(t_ref))
    t_c = t_ref + lag
    if mode == "expint":
        knots = np.append(t_src, t_src[-1] + (t_src[-1] - t_src[-2]))  # ZOH: [t[k], t[k+1])
        w_lo, w_hi = t_c - 0.5 * texp, t_c + 0.5 * texp
    else:
        mid = 0.5 * (t_src[1:] + t_src[:-1])  # cell edges at midpoints between samples
        knots = np.concatenate(
            [[t_src[0] - 0.5 * (t_src[1] - t_src[0])], mid,
             [t_src[-1] + 0.5 * (t_src[-1] - t_src[-2])]]
        )
        w_lo, w_hi = t_c - 0.5 * dt_ref, t_c + 0.5 * dt_ref
    c = _cum_integral(knots, x)
    f_hi, hi = _eval_integral(knots, c, x, w_hi)
    f_lo, lo = _eval_integral(knots, c, x, w_lo)
    wsum = hi - lo
    ok = (t_c >= t_src[0]) & (t_c <= t_src[-1]) & (wsum > 0.9 * (w_hi - w_lo))
    out = (f_hi - f_lo) / np.maximum(wsum, 1e-15)[:, None]
    return out, ok


def sync_tool(sim, lag_ab_fr=0.0, lag_db_fr=2.5, dA=60, extra=()):
    """Tool alignment onto the A timeline: B by 'window', D by 'expint' (texp = dt_A).

    `extra` lists additional B-rate arrays to pass through the same kernel as B.
    Returns A, B, D, [extras...] trimmed to the common valid range.
    """
    tA, tB = sim["tA"], sim["tB"]
    dtA, dtB = np.median(np.diff(tA)), np.median(np.diff(tB))
    Bs, okb = tlmsync(tA, sim["B"], tB, lag_ab_fr * dtB, "window")
    Ds, okd = tlmsync(tA, sim["D"], tB, (lag_ab_fr - lag_db_fr) * dtB, "expint", texp=dtA)
    ok = okb & okd
    i0, i1 = np.where(ok)[0][0] + 2, np.where(ok)[0][-1] - 2
    sl = slice(i0, i1 + 1)
    outs = [sim["A"][sl, :dA], Bs[sl], Ds[sl]]
    for arr in extra:
        outs.append(tlmsync(tA, arr, tB, lag_ab_fr * dtB, "window")[0][sl])
    return outs


def sync_exact(sim, dA=60, delay_fr=3, extra=(), a_lags=()):
    """Same-kernel alignment: average the B frames inside each A exposure, and apply the SAME
    kernel to the per-B-frame effective command D[k - delay_fr]. Optional lagged copies of A."""
    nA = len(sim["tA"])
    nB = len(sim["tB"])
    k1 = 2 * np.arange(nA) + 1  # B frame ending with the A exposure
    k0 = k1 - 1
    pad = max(2, int(np.ceil((delay_fr + 2) / 2)) + (max(map(abs, a_lags)) if a_lags else 0))
    sl = slice(pad, min(nA, nB // 2) - pad)
    k0, k1 = k0[sl], k1[sl]

    def pair(x):
        return 0.5 * (x[k0] + x[k1])

    D = sim["D"]
    Dal = 0.5 * (D[k0 - delay_fr] + D[k1 - delay_fr])
    idx = np.arange(nA)[sl]
    A = sim["A"][idx, :dA]
    if a_lags:
        A = np.hstack([A] + [sim["A"][idx + j, :dA] for j in a_lags])
    return [A, pair(sim["B"]), Dal] + [pair(arr) for arr in extra]


# --------------------------------------------------------------------------------------------
# Linear algebra helpers
# --------------------------------------------------------------------------------------------


def solve_block(Saa, Sdd, Sad, Sba, Sbd, ra, rd):
    """Joint ridge solve (identical to the tool's Schur-complement route). Returns Mab, Mdb, eta."""
    dA, dD = Saa.shape[0], Sdd.shape[0]
    Saa_r = Saa + np.diag(ra * np.diag(Saa))
    Sdd_r = Sdd + np.diag(rd * np.diag(Sdd))
    G12 = np.linalg.solve(Saa_r, Sad)
    Sch = Sdd_r - Sad.T @ G12
    Mdb = np.linalg.solve(Sch, (Sbd - Sba @ G12).T).T
    Mab = np.linalg.solve(Saa_r, (Sba - Mdb @ Sad.T).T).T
    eta = np.clip(np.diag(Sch) / np.diag(Sdd), 0.0, 1.0)
    return Mab, Mdb, eta


def covs(A, D, B):
    n = len(A) - 1
    return A.T @ A / n, D.T @ D / n, A.T @ D / n, B.T @ A / n, B.T @ D / n


def ar_taps(X, order, ridge=0.02):
    """Pooled AR(p) whitening taps [1, -a1..-ap] on unit-variance channels (as the tool)."""
    if order <= 0:
        return np.array([1.0])
    r = np.zeros(order + 1)
    for mlag in range(order + 1):
        num = np.einsum("tc,tc->c", X[mlag:], X[: len(X) - mlag])
        r[mlag] = np.sum(num / np.einsum("tc,tc->c", X, X))
    r /= r[0]
    r[0] = 1.0 + ridge
    R = np.array([[r[abs(i - j)] for j in range(order)] for i in range(order)])
    a = np.linalg.solve(R, r[1:])
    return np.concatenate([[1.0], -a])


def fir_valid(X, taps):
    p = len(taps) - 1
    out = taps[0] * X[p:]
    for mlag in range(1, p + 1):
        out = out + taps[mlag] * X[p - mlag : len(X) - mlag]
    return out


def r2_med(Y, P):
    return float(np.median(1.0 - np.sum((Y - P) ** 2, 0) / np.sum(Y**2, 0)))


# --------------------------------------------------------------------------------------------
# Estimators
# --------------------------------------------------------------------------------------------


def est_ols(A, B, D, ra=1e-6, rd=1e-6):
    A, B, D = A - A.mean(0), B - B.mean(0), D - D.mean(0)
    Mab, Mdb, eta = solve_block(*covs(A, D, B), ra, rd)
    return dict(Mab=Mab, Mdb=Mdb, eta=eta)


def est_tool(A, B, D, order=4, ridge=0.02, train_frac=0.7, ra=None, rd=None, taps=None):
    """Port of mlt.sysid: AR(p) on A_train, shared causal FIR, CV ridge, full-window refit."""
    N = len(A)
    ntr = int(np.floor(N * train_frac))
    mu = [x[:ntr].mean(0) for x in (A, B, D)]
    tr = [x[:ntr] - m for x, m in zip((A, B, D), mu)]
    te = [x[ntr:] - m for x, m in zip((A, B, D), mu)]
    fl = [x - x.mean(0) for x in (A, B, D)]
    if taps is None:
        taps = ar_taps(tr[0], order, ridge)
    trw = [fir_valid(x, taps) for x in tr]
    tew = [fir_valid(x, taps) for x in te]
    flw = [fir_valid(x, taps) for x in fl]
    Saa, Sdd, Sad, Sba, Sbd = covs(trw[0], trw[2], trw[1])
    best = (-1e9, 1e-2, 1e-3)
    if ra is None or rd is None:
        for ra_c in (1e-3, 3e-3, 1e-2, 3e-2, 1e-1) if ra is None else (ra,):
            for rd_c in (1e-4, 1e-3, 3e-3, 1e-2) if rd is None else (rd,):
                Mab, Mdb, _ = solve_block(Saa, Sdd, Sad, Sba, Sbd, ra_c, rd_c)
                sc = r2_med(tew[1], tew[0] @ Mab.T + tew[2] @ Mdb.T)
                if sc > best[0]:
                    best = (sc, ra_c, rd_c)
    else:
        Mab, Mdb, _ = solve_block(Saa, Sdd, Sad, Sba, Sbd, ra, rd)
        best = (r2_med(tew[1], tew[0] @ Mab.T + tew[2] @ Mdb.T), ra, rd)
    Mab, Mdb, eta = solve_block(*covs(flw[0], flw[2], flw[1]), best[1], best[2])
    raw = solve_block(*covs(tr[0], tr[2], tr[1]), 1e-2, 1e-3)
    return dict(Mab=Mab, Mdb=Mdb, eta=eta, taps=taps, r2w=best[0], ra=best[1], rd=best[2],
                eta_raw=raw[2], Mdb_raw=raw[1])


def cross_spectra(X, Y, nperseg=256, step=None):
    """Welch cross-spectral matrices S_XX (nf, dx, dx) and S_YX (nf, dy, dx), Hann window."""
    step = step or nperseg // 2
    win = np.hanning(nperseg)[:, None]
    starts = range(0, len(X) - nperseg + 1, step)
    Sxx = 0.0
    Syx = 0.0
    for s in starts:
        xf = np.fft.rfft((X[s : s + nperseg] - X[s : s + nperseg].mean(0)) * win, axis=0)
        yf = np.fft.rfft((Y[s : s + nperseg] - Y[s : s + nperseg].mean(0)) * win, axis=0)
        Sxx = Sxx + np.einsum("fi,fj->fij", xf, xf.conj())
        Syx = Syx + np.einsum("fi,fj->fij", yf, xf.conj())
    norm = len(starts) * float(np.sum(win**2))
    return Sxx / norm, Syx / norm


def est_weighted(Sxx, Syx, w, dA, ra=1e-3, rd=1e-4):
    """Frequency-weighted least squares: minimise sum_f w[f] |Y - M X|^2 per output row.

    w is (nf,) shared or (nf, dy) per output row. Returns Mab, Mdb.
    """
    dy = Syx.shape[1]
    w = np.asarray(w, dtype=float)
    reg = np.concatenate([np.full(dA, ra), np.full(Sxx.shape[1] - dA, rd)])
    if w.ndim == 1:
        G = np.einsum("f,fij->ij", w, Sxx.real)
        R = np.einsum("f,fij->ij", w, Syx.real)
        M = np.linalg.solve(G + np.diag(reg * np.diag(G)), R.T).T
    else:
        M = np.zeros((dy, Sxx.shape[1]))
        for i in range(dy):
            G = np.einsum("f,fij->ij", w[:, i], Sxx.real)
            R = np.einsum("f,fj->j", w[:, i], Syx[:, i, :].real)
            M[i] = np.linalg.solve(G + np.diag(reg * np.diag(G)), R)
    return M[:, :dA], M[:, dA:]


def resid_psd(Sxx, Syx, Syy_diag, M):
    """Per-row residual PSD S_ee[f, i] of Y - M X from the cross-spectra."""
    t1 = np.einsum("ij,fjk,ik->fi", M, Sxx, M).real
    t2 = 2.0 * np.einsum("fij,ij->fi", Syx, M).real
    return np.maximum(Syy_diag + t1 - t2, 1e-30)


def est_gls(A, B, D, iters=3, nperseg=256, ra=1e-3, rd=1e-4, smooth=3, fmin=0.0, fs=1000.0):
    """Iterated feasible GLS: weight each output row by the inverse of ITS OWN residual spectrum.

    This is the Box-Jenkins / prediction-error estimate with a non-parametric noise model.
    """
    X = np.hstack([A - A.mean(0), D - D.mean(0)])
    Y = B - B.mean(0)
    dA = A.shape[1]
    Sxx, Syx = cross_spectra(X, Y, nperseg)
    Syy = cross_spectra(Y, Y, nperseg)[0]
    Syy_d = np.einsum("fii->fi", Syy).real
    freqs = np.fft.rfftfreq(nperseg, 1.0 / fs)
    band = (freqs >= fmin).astype(float)
    band[0] = 0.0
    w = band.copy()
    hist = []
    for _ in range(iters + 1):
        Mab, Mdb = est_weighted(Sxx, Syx, w, dA, ra, rd)
        hist.append(np.diag(Mdb).copy())
        see = resid_psd(Sxx, Syx, Syy_d, np.hstack([Mab, Mdb]))
        if smooth > 1:
            ker = np.ones(smooth) / smooth
            see = np.apply_along_axis(lambda v: np.convolve(v, ker, mode="same"), 0, see)
        w = band[:, None] / see
    return dict(Mab=Mab, Mdb=Mdb, hist=hist, see=see, freqs=freqs, Sxx=Sxx, Syx=Syx)


def est_freq_proto(A, B, D, flo=20.0, fhi=480.0, nperseg=128, ra=0.05, rd=0.005, fs=1000.0):
    """The report generator's band-limited 1/tr(S_AA) cross-spectral regression."""
    X = np.hstack([A - A.mean(0), D - D.mean(0)])
    Y = B - B.mean(0)
    dA = A.shape[1]
    Sxx, Syx = cross_spectra(X, Y, nperseg)
    freqs = np.fft.rfftfreq(nperseg, 1.0 / fs)
    w = np.where((freqs >= flo) & (freqs <= fhi), 1.0, 0.0)
    w = w / (np.einsum("fii->f", Sxx[:, :dA, :dA]).real + 1e-30)
    Mab, Mdb = est_weighted(Sxx, Syx, w, dA, ra, rd)
    return dict(Mab=Mab, Mdb=Mdb)


def ecol_diag(A, B, D, g):
    """Report diagnostics: residual at the true Mdb, its lag-1 autocorrelation and corr with D."""
    A, B, D = A - A.mean(0), B - B.mean(0), D - D.mean(0)
    B_ol = B - D * g[None, :]
    Mab = np.linalg.lstsq(A, B_ol, rcond=1e-3)[0].T
    res = B_ol - A @ Mab.T
    ac1 = np.median([np.corrcoef(res[1:, i], res[:-1, i])[0, 1] for i in range(B.shape[1])])
    cd = np.median([np.corrcoef(res[:, i], D[:, i])[0, 1] for i in range(B.shape[1])])
    r2 = np.median(1.0 - res.var(0) / B_ol.var(0))
    return float(ac1), float(cd), float(r2)


def est_pem(A, B, D, order=16, iters=4, ra=1e-3, rd=1e-4):
    """Time-domain prediction-error estimate: each output row is whitened by an AR(order) model
    of ITS OWN residual (iterated). Uses lagged covariances, so cost is O(order * d^2) per row."""
    X = np.hstack([A - A.mean(0), D - D.mean(0)])
    Y = B - B.mean(0)
    N, dx = X.shape
    dA = A.shape[1]
    Cxx = [X[l:].T @ X[: N - l] / N for l in range(order + 1)]
    Cxy = [X[l:].T @ Y[: N - l] / N for l in range(order + 1)]
    Cyx = [Y[l:].T @ X[: N - l] / N for l in range(order + 1)]
    reg = np.concatenate([np.full(dA, ra), np.full(dx - dA, rd)])
    M = np.linalg.solve(Cxx[0] + np.diag(reg * np.diag(Cxx[0])), Cxy[0]).T
    for _ in range(iters):
        Er = Y - X @ M.T
        Mn = np.zeros_like(M)
        for i in range(Y.shape[1]):
            e = Er[:, i]
            r = np.array([np.dot(e[l:], e[: N - l]) for l in range(order + 1)])
            R = np.array([[r[abs(a - b)] for b in range(order)] for a in range(order)])
            w = np.r_[1.0, -np.linalg.solve(R + 1e-6 * r[0] * np.eye(order), r[1:])]
            cw = np.array([np.dot(w[: order + 1 - l], w[l:]) for l in range(order + 1)])
            G = cw[0] * Cxx[0]
            rhs = cw[0] * Cxy[0][:, i]
            for l in range(1, order + 1):
                G = G + cw[l] * (Cxx[l] + Cxx[l].T)
                rhs = rhs + cw[l] * (Cxy[l][:, i] + Cyx[l][i, :])
            Mn[i] = np.linalg.solve(G + np.diag(reg * np.diag(G)), rhs)
        M = Mn
    return dict(Mab=M[:, :dA], Mdb=M[:, dA:])


def est_iv_modal(A, B, D, Mab0, lags=(-4, -3, -2, -1, 1, 2, 3, 4), instrument_a=True):
    """Per-mode two-stage least squares using WFS A as the exogenous excitation.

    psi_i = (Mab0 A)_i is the A-predicted disturbance for B mode i. Model:
        B_i[t] = c_i psi_i[t] + g_i D_i[t] + v_i[t]
    Instruments are lagged/advanced psi_i (A is upstream of DM2, hence exogenous at every lag).
    With instrument_a=True the current psi is NOT its own instrument, which removes the
    errors-in-variables bias caused by white noise in A.
    Returns g (dB,), c (dB,) and the first-stage partial R^2 of D given the instruments.
    """
    psi = (A - A.mean(0)) @ Mab0.T
    Bc, Dc = B - B.mean(0), D - D.mean(0)
    N, dB = Bc.shape
    lo, hi = max(0, -min(lags)), N - max(0, max(lags))
    t = np.arange(lo, hi)
    g = np.zeros(dB)
    c = np.zeros(dB)
    pr2 = np.zeros(dB)
    for i in range(dB):
        Z = np.column_stack([psi[t + l, i] for l in lags])
        if not instrument_a:
            Z = np.column_stack([psi[t, i], Z])
        X = np.column_stack([psi[t, i], Dc[t, i]])
        y = Bc[t, i]
        Q, _ = np.linalg.qr(Z)
        Xh = Q @ (Q.T @ X)
        beta = np.linalg.solve(Xh.T @ X, Xh.T @ y)
        c[i], g[i] = beta
        # strength: variance of the part of D-hat not collinear with psi-hat, relative to var(D)
        dh = Xh[:, 1] - Xh[:, 0] * (Xh[:, 0] @ Xh[:, 1]) / (Xh[:, 0] @ Xh[:, 0])
        pr2[i] = float(dh @ dh) / float(X[:, 1] @ X[:, 1])
    return dict(g=g, c=c, pr2=pr2)


def est_dither(B, D, Z):
    """Instrumental-variable gain estimate with a known exogenous DM dither Z (same kernel as D)."""
    Bc, Dc, Zc = B - B.mean(0), D - D.mean(0), Z - Z.mean(0)
    return np.einsum("ti,ti->i", Bc, Zc) / np.einsum("ti,ti->i", Dc, Zc)


def est_mda(A, B, D, rb=1e-2, rd=1e-3):
    """Virtual upstream fit as in the tool: unwhitened A = Mba B + Mda D; returns Mda_virt."""
    A, B, D = A - A.mean(0), B - B.mean(0), D - D.mean(0)
    Mba, Mda, _ = solve_block(*covs(B, D, A), rb, rd)
    return -Mda, Mba
