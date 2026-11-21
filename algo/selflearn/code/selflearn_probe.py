#!/usr/bin/python3
"""Feasibility probe: lookup-table correction on top of a linear AO predictor.

Part A  How often does the AO state recur?  Distance from a state to its best match in a
        database of earlier frames, relative to the distance to a typical database frame.
Part B  Does a lookup add anything to a global linear predictor on held-out telemetry?
        Includes a shifted-pairing control and a synthetic state-dependent-gain injection
        (positive control: shows the test can see a nonlinear effect when there is one).

Usage: selflearn_probe.py <telemetry dir with aol1_modevalWFS_*.fits / aol1_modevalDM_*.fits>
"""
import glob
import sys
import time

import numpy as np
from astropy.io import fits

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def load(tdir, name):
    files = sorted(glob.glob(f"{tdir}/{name}_*.fits"))
    val, tc = [], []
    for f in files:
        d = fits.getdata(f)
        val.append(d.reshape(-1, d.shape[-1]).astype(np.float32))
        tc.append(np.atleast_2d(np.loadtxt(f[:-5] + ".txt"))[:, [3, 5]])
    val, tc = np.concatenate(val), np.concatenate(tc)
    assert np.all(np.diff(tc[:, 1].astype(np.int64)) == 1), f"{name}: dropped frames"
    return val, tc[:, 0]


# ----------------------------------------------------------------------------- Part A
def recur(S, nlag, lens, q0):
    """Median over queries of d(best match) / d(median database frame), per database length.

    Queries are frames >= q0; the database is frames [0, L), all earlier than any query by at
    least q0 - max(lens) frames, so a match is a recurrence and not the same piece of trajectory.
    """
    a = S[q0 - (nlag - 1):]
    b = S[:max(lens)]
    d2 = (a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2.0 * (a @ b.T)
    off = nlag - 1
    if nlag > 1:
        nq, nr = a.shape[0] - off, b.shape[0] - off
        acc = np.zeros((nq, nr))
        for j in range(nlag):
            acc += d2[off - j:off - j + nq, off - j:off - j + nr]
        d2 = acc
    d2 = np.maximum(d2, 0.0)
    rho = []
    for L in lens:
        sub = d2[:, :L - off]
        rho.append(float(np.median(np.sqrt(sub.min(1) / np.median(sub, 1)))))
    slope = np.polyfit(np.log(lens), np.log(rho), 1)[0]
    return rho, slope


def part_a(W, D, fs):
    lens, q0 = (2000, 4000, 8000, 16000), 18000
    night = 8 * 3600 * fs
    print("\n=== Part A: recurrence of the state (database = earlier frames only) ===")
    print("rho = d(best match)/d(typical frame); corr = 1 - rho^2 = correlation of a state with")
    print("its best match.  'night' = power-law extrapolation of rho to an 8 h log (optimistic).")
    hdr = f"{'state':46s}" + "".join(f"{L / fs:>7.0f}s" for L in lens)
    print(hdr + f"{'corr@16s':>10s}{'d_rec':>8s}{'rho@night':>11s}{'corr@night':>11s}")

    def row(name, S, nlag):
        rho, sl = recur(S, nlag, lens, q0)
        rn = rho[-1] * (night / lens[-1]) ** sl
        drec = -1.0 / sl if sl < -1e-4 else float("inf")
        print(f"{name:46s}" + "".join(f"{r:8.3f}" for r in rho)
              + f"{1 - rho[-1] ** 2:10.3f}{drec:8.1f}{rn:11.3f}{1 - rn ** 2:11.3f}")

    Wz = ((W - W[:16000].mean(0)) / W[:16000].std(0)).astype(np.float64)
    Dz = ((D - D[:16000].mean(0)) / D[:16000].std(0)).astype(np.float64)
    Wr = (W - W[:16000].mean(0)).astype(np.float64)
    Dr = (D - D[:16000].mean(0)).astype(np.float64)
    for n in (2, 5, 10, 20, 50, 100, 300, 1000, Dz.shape[1]):
        row(f"DM (~turbulence), {n:4d} modes whitened, 1 frame", Dz[:, :n], 1)
    row("DM, all modes, raw um, 1 frame", Dr, 1)
    row("DM, all modes whitened, 16 frames", Dz, 16)
    for n in (2, 5, 10, 20, 50, 300, Wz.shape[1]):
        row(f"WFS residual, {n:4d} modes whitened, 1 frame", Wz[:, :n], 1)
    row("WFS residual, all modes, raw um, 1 frame", Wr, 1)
    for n in (2, 5, 10, 50, Wz.shape[1]):
        row(f"WFS residual, {n:4d} modes whitened, 16 frames", Wz[:, :n], 16)
    row("WFS+DM, all modes whitened, 16 frames", np.concatenate([Wz, Dz], 1), 16)

    for name, S in (("DM", Dr), ("WFS residual", Wr)):
        ev = np.linalg.eigvalsh(np.cov(S[:16000].T))[::-1]
        ev = np.maximum(ev, 0)
        cum = np.cumsum(ev) / ev.sum()
        print(f"PCA of {name} (raw um): participation ratio {ev.sum() ** 2 / (ev ** 2).sum():.1f}"
              f", comps for 90% / 99% variance: {np.searchsorted(cum, 0.9) + 1}"
              f" / {np.searchsorted(cum, 0.99) + 1}")


# ----------------------------------------------------------------------------- Part B
LAMS = (1e-4, 1e-3, 1e-2, 1e-1, 1.0)


def ridge(X, Y, lam):
    G = X.T @ X
    G[np.diag_indices_from(G)] += lam * np.trace(G) / G.shape[0]
    return np.linalg.solve(G, X.T @ Y)


def oof_ridge(X, Y, nfold=5):
    """Out-of-fold predictions on contiguous folds; lambda picked on the same OOF error."""
    edges = np.linspace(0, len(X), nfold + 1).astype(int)
    best = None
    for lam in LAMS:
        P = np.empty_like(Y)
        for i in range(nfold):
            m = np.ones(len(X), bool)
            m[edges[i]:edges[i + 1]] = False
            P[~m] = X[~m] @ ridge(X[m], Y[m], lam)
        sse = ((Y - P) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, lam, P)
    return best[1], best[2]


def kmeans(Z, K, it=30, seed=0):
    rng = np.random.default_rng(seed)
    C = Z[rng.choice(len(Z), K, replace=False)].copy()
    for _ in range(it):
        lab = ((Z[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
        for k in range(K):
            if (lab == k).any():
                C[k] = Z[lab == k].mean(0)
    return C


def assign(Z, C):
    return ((Z[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)


def knn_idx(Zq, Zr, k):
    d2 = (Zq * Zq).sum(1)[:, None] + (Zr * Zr).sum(1)[None, :] - 2.0 * (Zq @ Zr.T)
    return np.argpartition(d2, k, axis=1)[:, :k]


def gain(E, Ehat):
    return 1.0 - ((E - Ehat) ** 2).sum() / (E ** 2).sum()


def cluster_lin(Ftr, Etr, ltr, Fte, lte, K):
    """Per-cluster ridge of the residual on features F (+ intercept); lambda by inner holdout."""
    ntr = len(Ftr)
    cut = int(0.8 * ntr)
    one = lambda F: np.concatenate([F, np.ones((len(F), 1))], 1)
    Ftr1, Fte1 = one(Ftr), one(Fte)
    best = None
    for lam in (1e-3, 1e-1, 10.0):
        sse = 0.0
        for k in range(K):
            m = ltr == k
            fit, val = m.copy(), m.copy()
            fit[cut:] = False
            val[:cut] = False
            if fit.sum() < 5 or val.sum() == 0:
                sse += (Etr[val] ** 2).sum()
                continue
            sse += ((Etr[val] - Ftr1[val] @ ridge(Ftr1[fit], Etr[fit], lam)) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, lam)
    Ehat = np.zeros((len(Fte), Etr.shape[1]))
    for k in range(K):
        m = ltr == k
        if m.sum() >= 5 and (lte == k).any():
            Ehat[lte == k] = Fte1[lte == k] @ ridge(Ftr1[m], Etr[m], best[1])
    return Ehat


def lookups(tag, Ztr, Zte, Xtr, Xte, Ptr, Pte, Etr, Ete, roll):
    """All second-stage variants for one matching space Z; returns printable gains."""
    out = []
    q = Ztr.shape[1]
    for k in (20, 200):
        nn = knn_idx(Zte, Ztr, k)
        eh = Etr[nn].mean(1)
        out.append((f"kNN mean residual, k={k}", gain(Ete, eh), gain(np.roll(Ete, roll, 0), eh)))
    if 1 < q <= 8:
        k = 200
        nn = knn_idx(Zte, Ztr, k)
        A = np.concatenate([Ztr[nn] - Zte[:, None, :], np.ones((len(Zte), k, 1))], 2)
        G = np.einsum("nki,nkj->nij", A, A)
        G += 1e-3 * np.trace(G, axis1=1, axis2=2)[:, None, None] / (q + 1) * np.eye(q + 1)
        coef = np.linalg.solve(G, np.einsum("nki,nkm->nim", A, Etr[nn]))
        eh = coef[:, -1, :]
        out.append((f"kNN local-linear in Z, k={k}", gain(Ete, eh),
                    gain(np.roll(Ete, roll, 0), eh)))
    for K in (1, 4, 16):
        C = kmeans(Ztr, K) if K > 1 else Ztr.mean(0, keepdims=True)
        ltr, lte = assign(Ztr, C), assign(Zte, C)
        eh = cluster_lin(Ptr, Etr, ltr, Pte, lte, K)
        out.append((f"K={K:2d} clusters, linear in global prediction", gain(Ete, eh),
                    gain(np.roll(Ete, roll, 0), eh)))
        if K <= 4:
            eh = cluster_lin(Xtr, Etr, ltr, Xte, lte, K)
            out.append((f"K={K:2d} clusters, full linear refit", gain(Ete, eh),
                        gain(np.roll(Ete, roll, 0), eh)))
    print(f"  matching space: {tag}", flush=True)
    for name, g, g0 in out:
        print(f"    {name:46s} gain {100 * g:+7.2f}%   shifted control {100 * g0:+7.2f}%")


def part_b(W, D, idx, h, delta, ntr, gap, inject):
    T = W.shape[0]
    t = np.arange(h - 1, T - delta)
    X = np.concatenate([np.concatenate([W[t - j][:, idx], D[t - j][:, idx]], 1)
                        for j in range(h)], 1).astype(np.float64)
    Y = W[t + delta][:, idx].astype(np.float64)
    tr, te = t < ntr, (t >= ntr + gap) & (t % 3 == 0)
    mu, sd = X[tr].mean(0), X[tr].std(0)
    X = (X - mu) / sd
    Y = Y - Y[tr].mean(0)

    # scalar "how big is the residual right now" (optical-gain proxy): log window energy
    sig = W[:ntr].std(0)
    ef = ((W / sig) ** 2).sum(1).astype(np.float64)
    cs = np.concatenate([[0.0], np.cumsum(ef)])
    s = np.log(cs[t + 1] - cs[t + 1 - h])
    s = (s - s[tr].mean()) / s[tr].std()

    lam, _ = oof_ridge(X[tr], Y[tr])
    if inject > 0:
        P0 = X @ ridge(X[tr], Y[tr], lam)
        E0 = (Y - P0)[te]
        c = s[:, None] * P0
        c *= np.sqrt(inject * (E0 ** 2).sum() / (c[te] ** 2).sum())
        Y = Y + c
        lam, _ = oof_ridge(X[tr], Y[tr])
    lam, Ptr = oof_ridge(X[tr], Y[tr])
    Etr = Y[tr] - Ptr
    Pte = X[te] @ ridge(X[tr], Y[tr], lam)
    Ete = Y[te] - Pte
    r2 = 1.0 - (Ete ** 2).sum() / (Y[te] ** 2).sum()
    print(f"\n--- modes {idx[0]}-{idx[-1]}, {h} past frames of WFS+DM -> WFS residual {delta} "
          f"frames ahead, inject={inject:g}")
    print(f"  train {tr.sum()} / test {te.sum()} frames, {X.shape[1]} features, lambda {lam:g}")
    print(f"  global linear predictor removes {100 * r2:.1f}% of the baseline residual variance")
    if inject > 0:
        orc = 100 * (1 - (E0 ** 2).sum() / (Ete ** 2).sum())
        print(f"  oracle for the injected term: {orc:.1f}% of what the linear predictor leaves")
    for k in (20, 200):
        w, V = np.linalg.eigh(X[tr].T @ X[tr])
        V8 = V[:, ::-1][:, :8]
        nn = knn_idx(X[te] @ V8, X[tr] @ V8, k)
        yh = Y[tr][nn].mean(1)
        print(f"  pure lookup (kNN in 8 PCA dims, k={k}, no linear stage) removes "
              f"{100 * (1 - ((Y[te] - yh) ** 2).sum() / (Y[te] ** 2).sum()):.1f}%")
    print("  second stage on what the linear predictor leaves (gain = further variance removed):")
    roll = 500
    w, V = np.linalg.eigh(X[tr].T @ X[tr])
    V = V[:, ::-1]
    for q in (4, 16):
        log(f"matching space q={q}")
        Z = X @ V[:, :q]
        lookups(f"top {q} PCA dims of the state", Z[tr], Z[te], X[tr], X[te], Ptr, Pte, Etr, Ete,
                roll)
    Zs = s[:, None]
    lookups("residual-energy scalar only (1-D)", Zs[tr], Zs[te], X[tr], X[te], Ptr, Pte, Etr, Ete,
            roll)
    Z = np.concatenate([X @ V[:, :4], s[:, None] * np.sqrt(w[::-1][0] / tr.sum())], 1)
    lookups("top 4 PCA dims + residual-energy scalar", Z[tr], Z[te], X[tr], X[te], Ptr, Pte, Etr,
            Ete, roll)


def main():
    tdir = sys.argv[1]
    parts = sys.argv[2] if len(sys.argv) > 2 else "AB"
    W, tW = load(tdir, "aol1_modevalWFS")
    D, tD = load(tdir, "aol1_modevalDM")
    assert len(W) == len(D)
    dt = np.median(tD - tW)
    fs = 1000.0
    log(f"loaded W {W.shape}, D {D.shape}; DM frame written {1e3 * dt:.2f} ms (wall) after WFS")
    print(f"rms over time, median over modes: WFS {np.median(W.std(0)):.4g}  DM "
          f"{np.median(D.std(0)):.4g} (um)")
    if "A" in parts:
        part_a(W, D, fs)
        log("part A done")
    if "B" in parts:
        print("\n=== Part B: global linear predictor vs lookup, held-out ===")
        for lo, inject in ((0, 0.0), (0, 0.1), (200, 0.0)):
            part_b(W, D, np.arange(lo, lo + 50), h=10, delta=2, ntr=14000, gap=500,
                   inject=inject)
            log("block done")


if __name__ == "__main__":
    main()
