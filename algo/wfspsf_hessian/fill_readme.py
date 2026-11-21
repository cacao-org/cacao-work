#!/usr/bin/env python3
"""Fill the tables of README.md from out/*.npz.

Every block between `<!-- table:NAME -->` and `<!-- /table -->` is regenerated; the prose is
left alone. Run after the experiments: /usr/bin/python3 fill_readme.py
"""
import os
import re

import numpy as np

from summary import ZONES, load, zmed, zr2

HERE = os.path.dirname(os.path.abspath(__file__))
REF_AMPS = (0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5)


def z4(v):
    return " / ".join(f"{x:.3f}" for x in v)


def amp_file(a):
    return load("ref" if a == 0.3 else f"amp{a:g}")


def t_concept():
    d = load("ref")
    r = d["r"]
    rows = ["| model | core | 1.25-4 | 4-8 | >8 |", "|---|---:|---:|---:|---:|"]
    for lab, key, sst in (("linear in the true modes", "oracle__lin_k80_n200000", "oracle__sst"),
                          ("Hessian, true modes", "oracle__quad_k80_n200000", "oracle__sst"),
                          ("Hessian, pyramid PCA modes (K = 80, noiseless)",
                           "pyr__quad_k80_n200000", "pyr__sst")):
        rows.append(f"| {lab} | " + " | ".join(f"{x:.3f}" for x in zr2(d[key], d[sst], r)) + " |")
    return rows


def t_amplitude():
    rows = ["| WF RMS [rad] | Hessian model | linear model | H fit / analytic | exp(-rms^2) |",
            "|---|---|---|---:|---:|"]
    for a in REF_AMPS:
        d = amp_file(a)
        if d is None:
            continue
        n, r = int(d["ntrain"]), d["r"]
        g = float(np.median(d["coef__h_gain"][(r > 1.25) & (r < 8)]))
        rows.append(f"| {a:g} | {z4(zr2(d[f'oracle__quad_k80_n{n}'], d['oracle__sst'], r))} | "
                    f"{z4(zr2(d[f'oracle__lin_k80_n{n}'], d['oracle__sst'], r))} | {g:.3f} | "
                    f"{np.exp(-a * a):.3f} |")
    return rows


def t_frames():
    d, e = load("ref"), load("refextra")
    r, sst = d["r"], d["oracle__sst"]
    rows = ["| training frames | least squares | cross-moments only |", "|---:|---|---|"]
    for n in (2000, 5000, 10000, 20000, 50000, 200000):
        ls = zr2(d[f"oracle__quad_k80_n{n}"], sst, r)
        cm = zr2(e[f"oracle__corr_k80_n{n}"], e["oracle__sst"], r) if e is not None else None
        a = "fails (fewer frames than coefficients)" if min(ls) < 0 else z4(ls)
        b = "" if cm is None else ("fails" if min(cm) < 0 else z4(cm))
        rows.append(f"| {n:,} | {a} | {b} |".replace(",", " "))
    return rows


def t_wfsnoise():
    d = load("ref")
    r = d["r"]
    g0 = float(np.median(d["coef__h_gain"][(r > 1.25) & (r < 8)]))
    rows = [f"| s2 | Hessian R2 | linear R2 | H fit / analytic | {g0:.3f} / (1 + s2) |",
            "|---:|---|---|---:|---:|"]
    for s2 in (0.1, 0.3, 1.0, 3.0):
        k = f"oraclenoise{s2}"
        g = float(np.median(d[f"{k}__h_gain"][(r > 1.25) & (r < 8)]))
        rows.append(f"| {s2:g} | {z4(zr2(d[f'{k}__quad_k80_n200000'], d[f'{k}__sst'], r))} | "
                    f"{z4(zr2(d[f'{k}__lin_k80_n200000'], d[f'{k}__sst'], r))} | {g:.3f} | "
                    f"{g0 / (1 + s2):.3f} |")
    return rows


def t_photons():
    d = load("ref")
    r = d["r"]
    rows = ["| photons per WFS frame | equivalent s2 | Hessian R2 |", "|---:|---:|---|"]
    for name, lab in (("pyr1e+06", "1e6"), ("pyr100000", "1e5"), ("pyr10000", "1e4"),
                      ("pyr1000", "1e3")):
        la = float(np.median(d[f"{name}__lin_a"]))
        rows.append(f"| {lab} | {1 / la - 1:.3g} | "
                    f"{z4(zr2(d[f'{name}__quad_k80_n200000'], d[f'{name}__sst'], r))} |")
    return rows


def t_smooth():
    d = load("smooth")
    r, sst = d["r"], d["sst"]
    rows = ["| s2 | modes used in the features | R2 |", "|---:|---|---|",
            f"| 0 | noiseless | {z4(zr2(d['clean'], sst, r))} |"]
    for s2 in ("0.3", "1", "3"):
        best = min((0.5, 0.75, 1.0, 1.5, 2.0, 3.0), key=lambda w: d[f"s{s2}__gauss{w:g}"].sum())
        rows.append(f"| {s2} | noisy, as they are | {z4(zr2(d[f's{s2}__raw'], sst, r))} |")
        rows.append(f"| {s2} | Gaussian kernel, sigma {best:g} frames (best) | "
                    f"{z4(zr2(d[f's{s2}__gauss{best:g}'], sst, r))} |")
        rows.append(f"| {s2} | Wiener smoother | {z4(zr2(d[f's{s2}__wiener'], sst, r))} |")
    return rows


def t_modes():
    d = load("ref")
    r = d["r"]
    rows = ["| K kept | true modes, by wavefront variance | pyramid PCA, by WFS variance |",
            "|---:|---|---|"]
    for k in (20, 40, 60, 80, 120):
        a = (z4(zr2(d[f"oracle__quad_k{k}_n200000"], d["oracle__sst"], r))
             if f"oracle__quad_k{k}_n200000" in d else "not run")
        b = z4(zr2(d[f"pyr__quad_k{k}_n200000"], d["pyr__sst"], r))
        rows.append(f"| {k} | {a} | {b} |")
    return rows


def t_psfpca():
    d = load("ref")
    r, sst = d["r"], d["oracle__sst"]
    rows = ["| J | noise-weighted PCA | plain PCA |", "|---:|---|---|"]
    for j in (25, 100, 200, 400, 800, 1600):
        rows.append(f"| {j} | {z4(zr2(d[f'psfpca_sqrtmean__ceil_j{j}'], sst, r))} | "
                    f"{z4(zr2(d[f'psfpca_none__ceil_j{j}'], sst, r))} |")
    return rows


def t_structure():
    d = load("ref")
    r = d["r"]
    rows = ["| quantity | core | 1.25-4 | 4-8 | >8 |", "|---|---:|---:|---:|---:|"]
    for lab, v in (
            ("share of the 2 largest positive eigenvalues, `S` alone", d["coef__top2_spk"]),
            ("same, analytic `S + T`", d["coef__top2_tay"]),
            ("same, fitted from data", d["coef__top2_fit"]),
            ("share of the negative eigenvalues, fitted", d["coef__neg_fit"]),
            ("norm of `T` / norm of `S`", d["coef__hp_norm"] / d["coef__hs_norm"]),
            ("cosine of angle 1, fitted vs true channel plane", d["coef__cos2"][:, 0]),
            ("cosine of angle 2, fitted vs true channel plane", d["coef__cos2"][:, 1])):
        rows.append(f"| {lab} | " + " | ".join(f"{x:.3f}" for x in zmed(v, r)) + " |")
    return rows


def t_channels():
    d = load("channels")
    r = d["r"]
    rows = ["| WF RMS [rad] | model | core | 1.25-4 | 4-8 | >8 |", "|---:|---|---:|---:|---:|---:|"]
    for a in d["amps"]:
        sst = d[f"amp{a:g}__sst"]
        for key, lab in (("aff2", "2 squared affine channels"), ("poly2", "Hessian polynomial"),
                         ("quad2", "2 squared quadratic channels")):
            v = zmed(1 - d[f"amp{a:g}__{key}"] / sst, r)
            rows.append(f"| {a:g} | {lab} | " + " | ".join(f"{x:.3f}" for x in v) + " |")
    return rows


def t_lag():
    d = load("sync")
    t = d["lagtable"]
    names = [str(x) for x in d["lagmodels"]]
    rows = ["| PSF exposure | sync model | R2 at peak | largest error, all frames | "
            "scatter, 1/8 of the frames |", "|---:|---|---:|---:|---:|"]
    for m in (1, 4, 16):
        for im, name in enumerate(names):
            s = t[(t[:, 0] == m) & (t[:, 4] == im) & (t[:, 3] == 0)]
            if len(s) == 0 or name == "lead12":
                continue
            rows.append(f"| {m} | {name} | {s[:, 6].mean():.2f} | {np.abs(s[:, 5]).max():.3f} | "
                        f"{np.sqrt((s[:, 8] ** 2).mean()):.3f} |")
    s = t[(t[:, 4] == names.index("lead12")) & (t[:, 3] == 0)]
    rows.append(f"| 1, 4, 16 | lead12 | {s[:, 6].mean():.2f} | not meaningful | "
                f"{s[:, 8].min():.1f} to {s[:, 8].max():.1f} |")
    return rows


def t_pairing():
    d = load("sync")
    r = d["r"]
    rows = ["| pairing | exposure 1 | exposure 4 | exposure 16 |", "|---|---:|---:|---:|"]
    labs = [("exact", "features averaged over the exposure, exact timing"),
            ("naive", "features of the exposure-averaged modes"),
            ("nearest", "nearest whole WFS frame")]
    labs += [(f"lag{s:g}", f"timing error {s:g} frame" + ("s" if s > 1 else ""))
             for s in (0.25, 0.5, 1.0, 2.0, 4.0)]
    labs.append(("exact_lin", "linear model, exact timing"))
    for key, lab in labs:
        cells = []
        for m in (1, 4, 16):
            k = f"fit_m{m}__{key}"
            cells.append(f"{zr2(d[k], d[f'fit_m{m}__sst'], r)[2]:.3f}" if k in d else "")
        rows.append(f"| {lab} | " + " | ".join(cells) + " |")
    return rows


TABLES = dict(concept=t_concept, amplitude=t_amplitude, frames=t_frames, wfsnoise=t_wfsnoise,
              photons=t_photons, smooth=t_smooth, modes=t_modes, psfpca=t_psfpca,
              structure=t_structure, channels=t_channels, lag=t_lag, pairing=t_pairing)


def main():
    path = os.path.join(HERE, "README.md")
    text = open(path).read()

    def repl(m):
        name = m.group(1)
        try:
            body = "\n".join(TABLES[name]())
        except Exception as exc:  # missing result file: leave a visible marker
            body = f"(table `{name}` not generated: {type(exc).__name__}: {exc})"
        return f"<!-- table:{name} -->\n{body}\n<!-- /table -->"

    new = re.sub(r"<!-- table:(\w+) -->.*?<!-- /table -->", repl, text, flags=re.S)
    open(path, "w").write(new)
    long = [i + 1 for i, ln in enumerate(new.splitlines()) if len(ln) > 100]
    print("README tables filled;", f"lines over 100 chars: {long}" if long else "all lines <= 100")


if __name__ == "__main__":
    main()
