"""Exact bias attribution: every estimator here is linear in B once its weights are fixed, so
diag(Mdb) splits into one term per physical component of B (DM, stage-1 residual seen through A,
B-only disturbance, WFS-B noise)."""
import numpy as np
import estimators as E

COMPS = ("dm", "phi", "u", "n")

def spectra(A, D, comps, nperseg=256):
    X = np.hstack([A - A.mean(0), D - D.mean(0)])
    Sxx, _ = E.cross_spectra(X, X[:, :1], nperseg)
    Syx = {c: E.cross_spectra(X, comps[c] - comps[c].mean(0), nperseg)[1] for c in comps}
    return Sxx, Syx

def taps_weight(taps, nperseg=256):
    w = np.linspace(0, np.pi, nperseg // 2 + 1)
    return np.abs(np.exp(-1j * np.outer(w, np.arange(len(taps)))) @ taps) ** 2

def decompose(Sxx, Syx, w, dA, ra, rd, g):
    """Return {component: median over modes>=4 of diag(Mdb_c)/g}."""
    out = {}
    for c, S in Syx.items():
        _, Mdb = E.est_weighted(Sxx, S, w, dA, ra, rd)
        out[c] = np.diag(Mdb) / g
    return out

def summarize(dec, lo=4):
    s = {c: 100.0 * float(np.median(v[lo:])) for c, v in dec.items()}
    s["dm"] -= 100.0
    s["total"] = sum(s.values())
    return s
