"""Differenced lagged-A estimator for arbitrary loop frequencies (toy data from simfreq.py).

The only frequency-dependent step is putting the three signals on one timeline with one
exposure. Everything is expressed through a list of windows [w0, w1) in fine-grid ticks:

    A, B   frame values are averages over their own exposures; a window value is the average of
           the frames it overlaps, weighted by overlap ("expint"). Exact when the window is a
           union of whole frames, approximate when it cuts frames.
    D      the DM2 position is rebuilt on the fine grid from the logged commands and the known
           actuation timing (delay, servo lag), then averaged over the window exactly.

Window choices:
    slow   exposures of the slower sensor (the recipe; exact for aligned integer ratios)
    lcm    the shortest windows made of whole frames of BOTH sensors (always exact, but slower)
    fast   exposures of the faster sensor (the slower one is spread by overlap)
    slowN  N consecutive exposures of the slower sensor: partial frames of the other sensor at
           the two edges then carry 1/N of the weight they have with "slow"
    bwinN  whole WFS B frames, at least N WFS A frames long (only WFS A can be cut)
    bfrN   exactly N whole WFS B frames
    rule   the rule of realsim_est.choose_windows (see rule_frames); ruleN asks for N frames
           of each sensor instead of two when WFS A frames have to be cut
"""
from math import gcd

import numpy as np


def cen(x):
    return x - x.mean(0)


def dm2_position_cumsum(sim):
    """Cumulative sum over ticks of the DM2 position, rebuilt from the logged commands."""
    p, n_t, D, b_end = sim["p"], sim["n_t"], sim["D"], sim["b_end"]
    a2 = 1.0 - np.exp(-1e6 / (p["fs"] * p["tau2_us"]))
    tgt = np.zeros((n_t, D.shape[1]))
    start = b_end + sim["d2t"]                 # tick at which each command becomes the target
    k = np.searchsorted(start, np.arange(n_t), side="right") - 1
    ok = k >= 0
    tgt[ok] = D[k[ok]]
    pos = np.empty_like(tgt)
    cur = np.zeros(D.shape[1])
    for n in range(n_t):                        # first-order servo, as in the simulator
        cur = cur + a2 * (tgt[n] - cur)
        pos[n] = cur
    return np.vstack([np.zeros((1, D.shape[1])), np.cumsum(pos, axis=0)])


def frames_to_windows(vals, f_end, f_len, w0, w1, order=0):
    """Average of a frame-sampled signal over windows [w0, w1).

    Each frame value is the average of the signal over its own exposure. order 0 treats the
    signal as constant inside a frame (overlap weighting); order 1 as linear inside a frame,
    with the slope taken from the two neighbouring frames (still exact for whole frames, and
    second-order accurate for a frame cut by a window edge).
    """
    cs = np.vstack([np.zeros((1, vals.shape[1])), np.cumsum(vals, axis=0)])
    f_start = f_end - f_len
    slope = np.zeros_like(vals)
    if order == 1:
        slope[1:-1] = (vals[2:] - vals[:-2]) / (2.0 * f_len)

    def integral(t):  # integral of the reconstructed signal up to tick t
        k = np.clip(np.searchsorted(f_end, t, side="left"), 0, len(f_end) - 1)
        x = np.clip(t - f_start[k], 0.0, f_len)[:, None]          # ticks into frame k
        lin = 0.5 * slope[k] * ((x - 0.5 * f_len) ** 2 - (0.5 * f_len) ** 2)
        return cs[k] * f_len + vals[k] * x + lin

    return (integral(w1) - integral(w0)) / (w1 - w0)[:, None]


def windows(sim, mode):
    p = sim["p"]
    na, nb, off = int(p["na_t"]), int(p["nb_t"]), int(p["b_off"])
    t0, n_t = sim["t0"], sim["n_t"]
    mult = 1
    if mode.startswith(("bwin", "bfr", "rule")):
        # whole WFS B frames only: the shortest run of them at least N WFS A frames long.
        # B and the DM2 position stay exact; only WFS A frames can be cut by a window edge.
        if mode.startswith("rule"):
            nfr = rule_frames(na, nb, off, int(mode[4:] or 2))[0]
        elif mode.startswith("bfr"):
            nfr = int(mode[3:])
        else:
            nfr = int(np.ceil(int(mode[4:]) * na / nb))
        wl, first = nfr * nb, off
        k0 = int(np.ceil((t0 - first) / wl)) + 4
        k1 = (n_t - first) // wl - 4
        w0 = first + wl * np.arange(k0, k1)
        return w0, w0 + wl, wl
    if mode.startswith("slow") and mode != "slow":
        mult, mode = int(mode[4:]), "slow"      # "slow2": two frames of the slower sensor
    if mode == "lcm":
        wl = na * nb // gcd(na, nb)
        first = off if off % na == 0 else 0     # with a clock offset no window is exact
    elif (mode == "slow") == (na >= nb):
        wl, first = na * mult, 0                # WFS A exposures
    else:
        wl, first = nb * mult, off              # WFS B exposures
    k0 = int(np.ceil((t0 - first) / wl)) + 4
    k1 = (n_t - first) // wl - 4
    w0 = first + wl * np.arange(k0, k1)
    return w0, w0 + wl, wl


def rule_frames(na, nb, off, nmin=2):
    """WFS B frames per window and whether WFS A frames are cut (realsim_est.choose_windows).

    n_cut: fewest B frames holding nmin frames of each sensor (2 in the rule). n_exact: fewest
    B frames (at least two, at least one A frame long) whose edges fall on A frame edges.
    n_exact wins when it exists and is not longer than n_cut. Mode "rule3" uses nmin = 3.
    """
    n_cut = max(nmin, -(-nmin * na // nb))
    for n in range(2, n_cut + 1):
        if n * nb >= na and (n * nb) % na == 0 and off % na == 0:
            return n, False
    return n_cut, True


def align(sim, mode="slow", dA=60, order=0):
    p = sim["p"]
    w0, w1, wl = windows(sim, mode)
    A = frames_to_windows(sim["A"][:, :dA], sim["a_end"], int(p["na_t"]), w0, w1, order)
    B = frames_to_windows(sim["B"], sim["b_end"], int(p["nb_t"]), w0, w1, order)
    cs = dm2_position_cumsum(sim)
    D = (cs[w1] - cs[w0]) / wl
    return A, B, D, wl


def tsls(y, X, Z):
    Q, _ = np.linalg.qr(Z)
    Xh = Q @ (Q.T @ X)
    return np.linalg.solve(Xh.T @ X, Xh.T @ y)


def lagmat(x, t, lags):
    return np.column_stack([x[t - l] for l in lags])


def estimate(A, B, D, gstart, lags=range(2, 10)):
    """Differenced lagged-A, plain lagged-A and least squares; returns dict of g vectors."""
    A, B, D = cen(A), cen(B), cen(D)
    Saa = A.T @ A
    psi = A @ np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), A.T @ (B - D * gstart))
    dB, dP, dD = (np.diff(x, axis=0) for x in (B, psi, D))
    lmax = max(lags) + 2
    t, td = np.arange(lmax, len(B)), np.arange(lmax, len(dB))
    nm = B.shape[1]
    out = {k: np.zeros(nm) for k in ("IV diff", "IV", "LS", "LS diff")}
    use = np.zeros(nm)
    for i in range(nm):
        X, Xd = np.column_stack([psi[t, i], D[t, i]]), np.column_stack([dP[td, i], dD[td, i]])
        Z = lagmat(dP[:, i], td, lags)
        out["IV diff"][i] = tsls(dB[td, i], Xd, Z)[1]
        out["IV"][i] = tsls(B[t, i], X, lagmat(psi[:, i], t, [l - 1 for l in lags]))[1]
        out["LS"][i] = np.linalg.lstsq(X, B[t, i], rcond=None)[0][1]
        out["LS diff"][i] = np.linalg.lstsq(Xd, dB[td, i], rcond=None)[0][1]
        Q, _ = np.linalg.qr(Z)
        ph, dh = Q @ (Q.T @ Xd[:, 0]), Q @ (Q.T @ Xd[:, 1])
        dp = dh - ph * (ph @ dh) / (ph @ ph)
        use[i] = (dp @ dp) / (Xd[:, 1] @ Xd[:, 1])
    return out, use


def estimate_frame_lags(sim, mode, gstart, order=0, nlag=8, dA=60):
    """Differenced lagged-A with single-frame instruments.

    Instruments for the difference "window k minus window k-1": the nlag most recent
    frame-to-frame differences of psi whose WFS A frames end before window k-1 begins, so that
    they touch neither window. Equal to window lags 2-9 when a window is one WFS A frame.
    """
    w0, _, _ = windows(sim, mode)
    A, B, D, _ = align(sim, mode, dA, order)
    mean = A.mean(0)
    Ac, Bc, Dc = A - mean, cen(B), cen(D)
    Saa = Ac.T @ Ac
    M = np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), Ac.T @ (Bc - Dc * gstart))
    psi_w, psi_f = Ac @ M, (sim["A"][:, :dA] - mean) @ M
    dB, dP, dD = (np.diff(x, axis=0) for x in (Bc, psi_w, Dc))
    dF = np.diff(psi_f, axis=0)
    jlast = np.searchsorted(sim["a_end"], w0[:-1], side="right") - 1
    rows = np.flatnonzero(jlast - nlag >= 1)
    nm = B.shape[1]
    g, use = np.zeros(nm), np.zeros(nm)
    for i in range(nm):
        X = np.column_stack([dP[rows, i], dD[rows, i]])
        Z = np.column_stack([dF[jlast[rows] - 1 - m, i] for m in range(nlag)])
        g[i] = tsls(dB[rows, i], X, Z)[1]
        Q, _ = np.linalg.qr(Z)
        ph, dh = Q @ (Q.T @ X[:, 0]), Q @ (Q.T @ X[:, 1])
        dp = dh - ph * (ph @ dh) / (ph @ ph)
        use[i] = (dp @ dp) / (X[:, 1] @ X[:, 1])
    return g, use
