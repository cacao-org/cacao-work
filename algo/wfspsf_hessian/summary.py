#!/usr/bin/env python3
"""Print the result tables of the study (Markdown) from out/*.npz."""
import os

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
ZONES = (("core", 0.0, 1.25), ("1.25-4", 1.25, 4.0), ("4-8", 4.0, 8.0), (">8", 8.0, 99.0))


def load(name):
    path = os.path.join(OUT, name + ".npz")
    return np.load(path) if os.path.exists(path) else None


def zr2(sse, sst, r):
    return [1 - sse[(r >= lo) & (r < hi)].sum() / sst[(r >= lo) & (r < hi)].sum()
            for _, lo, hi in ZONES]


def zmed(v, r):
    return [float(np.median(v[(r >= lo) & (r < hi)])) for _, lo, hi in ZONES]


def row(label, vals, fmt="{:.3f}"):
    return f"| {label} | " + " | ".join(fmt.format(v) for v in vals) + " |"


def head(first, cols):
    print(f"| {first} | " + " | ".join(cols) + " |")
    print("|---|" + "---:|" * len(cols))


def amplitude():
    print("\n### Amplitude scan (R2 pooled per zone; zones in lambda/D)\n")
    zn = [z[0] for z in ZONES]
    head("WF RMS [rad]", [f"Hessian {z}" for z in zn] + [f"linear {z}" for z in zn]
         + ["H fit / H Taylor", "exp(-s^2)"])
    for a in (0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5):
        d = load("ref" if a == 0.3 else f"amp{a:g}")
        if d is None:
            continue
        n, r = int(d["ntrain"]), d["r"]
        g = float(np.median(d["coef__h_gain"][(r > 1.25) & (r < 8)]))
        print(row(f"{a:g}", zr2(d[f"oracle__quad_k80_n{n}"], d["oracle__sst"], r)
                  + zr2(d[f"oracle__lin_k80_n{n}"], d["oracle__sst"], r) + [g, np.exp(-a * a)]))
    print("\nPyramid PCA modes (K = 80, noiseless) versus true modes, Hessian model:\n")
    head("WF RMS [rad]", [f"pyramid {z}" for z in zn] + ["WFS modes linear in WF (median R2)"])
    for a in (0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5):
        d = load("ref" if a == 0.3 else f"amp{a:g}")
        if d is None:
            continue
        n, r = int(d["ntrain"]), d["r"]
        print(row(f"{a:g}", zr2(d[f"pyr__quad_k80_n{n}"], d["pyr__sst"], r)
                  + [float(np.median(d["pyr__lin_a"]))], "{:.4f}"))


def reference():
    d, e = load("ref"), load("refextra")
    if d is None:
        return
    r, sst = d["r"], d["oracle__sst"]
    zn = [z[0] for z in ZONES]
    print("\n### Training frames (reference case, 3321 coefficients per pixel)\n")
    head("frames", [f"LS {z}" for z in zn] + [f"cross-moments {z}" for z in zn])
    for n in (2000, 5000, 10000, 20000, 50000, 100000, 200000):
        v = zr2(d[f"oracle__quad_k80_n{n}"], sst, r)
        if e is not None:
            v += zr2(e[f"oracle__corr_k80_n{n}"], e["oracle__sst"], r)
        print(row(str(n), v))
    print("\n### WFS noise on the true modes (variance ratio s2 per mode)\n")
    head("s2", [f"Hessian {z}" for z in zn] + [f"linear {z}" for z in zn]
         + ["H gain", "expected H gain"])
    g0 = float(np.median(d["coef__h_gain"][(r > 1.25) & (r < 8)]))
    for s2 in (0.1, 0.3, 1.0, 3.0):
        k = f"oraclenoise{s2}"
        g = float(np.median(d[f"{k}__h_gain"][(r > 1.25) & (r < 8)]))
        print(row(f"{s2:g}", zr2(d[f"{k}__quad_k80_n200000"], d[f"{k}__sst"], r)
                  + zr2(d[f"{k}__lin_k80_n200000"], d[f"{k}__sst"], r) + [g, g0 / (1 + s2)]))
    print("\n### Pyramid WFS with photon noise (PCA, K = 80)\n")
    head("photons / WFS frame", ["equivalent s2"] + [f"Hessian {z}" for z in zn])
    for name, lab in (("pyr", "noiseless"), ("pyr1e+06", "1e6"), ("pyr100000", "1e5"),
                      ("pyr10000", "1e4"), ("pyr1000", "1e3")):
        la = float(np.median(d[f"{name}__lin_a"]))
        print(row(lab, [1 / la - 1] + zr2(d[f"{name}__quad_k80_n200000"], d[f"{name}__sst"], r)))
    print("\n### PSF photon noise (true modes; scored against noiseless PSFs)\n")
    head("photons / PSF frame, frames", [f"Hessian {z}" for z in zn])
    for nph in ("1e+06", "10000"):
        for n in (20000, 200000):
            k = f"psfnoise{nph}"
            print(row(f"{float(nph):g}, {n}", zr2(d[f"{k}__quad_k80_n{n}"], d[f"{k}__sst"], r)))
    print("\n### WFS modes kept\n")
    head("K", [f"true modes {z}" for z in zn])
    for k in (10, 20, 40, 60, 80):
        print(row(str(k), zr2(d[f"oracle__quad_k{k}_n200000"], sst, r)))
    print()
    head("K", [f"pyramid PCA {z}" for z in zn])
    for k in (20, 40, 60, 80, 100, 120):
        print(row(str(k), zr2(d[f"pyr__quad_k{k}_n200000"], d["pyr__sst"], r)))
    ev = d["pyr__wfs_ev"]
    print(f"\nPyramid PCA eigenvalues: ev1/ev80 = {ev[0] / ev[79]:.1f}, ev80/ev81 = "
          f"{ev[79] / ev[80]:.1f}")
    print("\n### PSF PCA modes kept (variance of the true PSF retained)\n")
    head("J", [f"weighted {z}" for z in zn] + [f"plain {z}" for z in zn])
    for j in (10, 25, 50, 100, 200, 400, 800, 1600):
        print(row(str(j), zr2(d[f"psfpca_sqrtmean__ceil_j{j}"], sst, r)
                  + zr2(d[f"psfpca_none__ceil_j{j}"], sst, r)))
    print("\n### Structure of the per-pixel Hessians (medians per zone)\n")
    head("quantity", zn)
    for key, lab in (("top2_spk", "top-2 share, analytic speckle term"),
                     ("top2_tay", "top-2 share, analytic full 2nd order"),
                     ("top2_fit", "top-2 share, fitted"), ("neg_tay", "negative share, analytic"),
                     ("neg_fit", "negative share, fitted"),
                     ("h_relerr", "relative error fitted vs analytic H"),
                     ("g_relerr", "relative error fitted vs analytic g")):
        print(row(lab, zmed(d["coef__" + key], r)))
    print(row("norm ratio pinned / speckle term", zmed(d["coef__hp_norm"] / d["coef__hs_norm"], r)))
    print(row("cos angle 1, fitted vs true channel plane", zmed(d["coef__cos2"][:, 0], r)))
    print(row("cos angle 2, fitted vs true channel plane", zmed(d["coef__cos2"][:, 1], r)))
    if e is not None:
        print("\n### Truncating the fitted Hessians to channels (reference case)\n")
        head("model", zn)
        es = e["oracle__sst"]
        print(row("full Hessian", zr2(e["oracle__quad_k80_n200000"], es, r)))
        for rk in (1, 2, 4, 8):
            print(row(f"c + g.a + {rk} positive channel(s) of H",
                      zr2(e[f"oracle__rank{rk}_k80_n200000"], es, r)))
        for rk in (1, 2, 4, 8):
            print(row(f"{rk} squared affine channel(s)",
                      zr2(e[f"oracle__aug{rk}_k80_n200000"], es, r)))


def bin1():
    print("\n### Unbinned PSF samples (6 per lambda/D), field +-6 lambda/D\n")
    head("WF RMS, quantity", [z[0] for z in ZONES[:3]])
    for a in (0.1, 0.3):
        d = load(f"bin1_amp{a:g}")
        if d is None:
            continue
        r = d["r"]
        n = int(d["ntrain"])
        print(row(f"{a:g}, Hessian R2", zr2(d[f"oracle__quad_k80_n{n}"], d["oracle__sst"], r)[:3]))
        for key, lab in (("top2_spk", "top-2 share, analytic speckle term"),
                         ("top2_tay", "top-2 share, analytic full"),
                         ("top2_fit", "top-2 share, fitted")):
            print(row(f"{a:g}, {lab}", zmed(d["coef__" + key], r)[:3], "{:.4f}"))
        print(row(f"{a:g}, cos angle 2 fitted vs true plane", zmed(d["coef__cos2"][:, 1], r)[:3]))


def channels():
    d = load("channels")
    if d is None:
        return
    r = d["r"]
    print("\n### Channel models on a radial cut of pixels (median R2 per zone, true modes)\n")
    zn = [z[0] for z in ZONES]
    for a in d["amps"]:
        print(f"\nWF RMS {a:g} rad:\n")
        head("model", zn)
        sst = d[f"amp{a:g}__sst"]
        for key, lab in (("lin", "linear"), ("aff2", "2 squared affine channels"),
                         ("poly2", "degree-2 polynomial (Hessian)"),
                         ("quad2", "2 squared quadratic channels")):
            print(row(lab, zmed(1 - d[f"amp{a:g}__{key}"] / sst, r)))


def sync():
    d = load("sync")
    if d is None:
        return
    t = d["lagtable"]
    names = [str(x) for x in d["lagmodels"]]
    print("\n### Lag recovery (errors in WFS frames)\n")
    head("PSF exposure, model", ["max abs error, all frames", "R2 at peak",
                                 "mean error, 1/8 segments", "scatter, 1/8 segments",
                                 "PSF frames per segment", "seconds per estimate"])
    for m in (1, 4, 16):
        for im, name in enumerate(names):
            s = t[(t[:, 0] == m) & (t[:, 4] == im) & (t[:, 3] == 0)]
            if len(s) == 0:
                continue
            print(row(f"{m}, {name}", [np.abs(s[:, 5]).max(), s[:, 6].mean(), s[:, 7].mean(),
                                       np.sqrt((s[:, 8] ** 2).mean()), s[:, 9].mean(),
                                       s[:, 10].mean()]))
    print("\nWith PSF photon noise (1e4 photons per frame), true lag 2.25:\n")
    head("PSF exposure, model", ["error, all frames", "scatter, 1/8 segments"])
    for m in (1, 4, 16):
        for im, name in enumerate(names):
            s = t[(t[:, 0] == m) & (t[:, 4] == im) & (t[:, 3] > 0)]
            if len(s):
                print(row(f"{m}, {name}", [s[0, 5], s[0, 8]]))
    r = d["r"]
    print("\n### Full model versus pairing of WFS features with PSF frames (R2 per zone)\n")
    zn = [z[0] for z in ZONES]
    for m in (1, 4, 16):
        print(f"\nPSF exposure = {m} WFS frame(s):\n")
        head("pairing", zn)
        sst = d[f"fit_m{m}__sst"]
        keys = [("exact", "exposure-averaged features"), ("exact_lin", "same, linear model"),
                ("naive", "features of the averaged modes")]
        if m == 1:
            keys.append(("nearest", "nearest WFS frame"))
        keys += [(f"lag{s:g}", f"timing error {s:g} frame") for s in (0.25, 0.5, 1.0, 2.0, 4.0)]
        for key, lab in keys:
            print(row(lab, zr2(d[f"fit_m{m}__{key}"], sst, r)))


def smooth():
    d = load("smooth")
    if d is None:
        return
    r, sst = d["r"], d["sst"]
    print("\n### Noisy WFS modes in a time series, with temporal smoothing (R2 per zone)\n")
    head("case", [z[0] for z in ZONES])
    print(row("noiseless", zr2(d["clean"], sst, r)))
    for s2 in ("0.3", "1", "3"):
        print(row(f"s2={s2}, raw", zr2(d[f"s{s2}__raw"], sst, r)))
        best = max((0.5, 0.75, 1.0, 1.5, 2.0, 3.0),
                   key=lambda w: -d[f"s{s2}__gauss{w:g}"].sum())
        print(row(f"s2={s2}, Gaussian sigma {best:g} frames",
                  zr2(d[f"s{s2}__gauss{best:g}"], sst, r)))
        print(row(f"s2={s2}, Wiener", zr2(d[f"s{s2}__wiener"], sst, r)))


if __name__ == "__main__":
    amplitude()
    reference()
    bin1()
    channels()
    smooth()
    sync()
