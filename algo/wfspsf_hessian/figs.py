#!/usr/bin/env python3
"""Figures for the WFS -> PSF Hessian toy study, from out/*.npz. Run with /usr/bin/python3."""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, LogNorm, SymLogNorm

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SURF, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"  # categorical slots 1-3 (validated)
ORD3 = ("#86b6ef", "#2a78d6", "#0d366b")  # ordinal ramp, one hue (validated)
SEQ = LinearSegmentedColormap.from_list("seqblue", [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
    "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"])
SEQ.set_bad(SURF)
# Diverging: blue <-> red around a neutral grey; the red arm is derived from categorical red.
DIV = LinearSegmentedColormap.from_list("divbr", [
    "#0d366b", "#1c5cab", "#3987e5", "#9ec5f4", "#f0efec", "#eda5a3", "#e34948", "#aa3535",
    "#6e2222"])
DIV.set_bad(SURF)
ZONES = (("core, r < 1.25", 0.0, 1.25), ("1.25 - 4", 1.25, 4.0), ("4 - 8", 4.0, 8.0),
         ("r > 8", 8.0, 99.0))

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.size": 9.5, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.labelcolor": INK2, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "grid.linestyle": "-", "axes.axisbelow": True, "lines.linewidth": 2.0,
    "lines.markersize": 6.5, "lines.markeredgecolor": SURF, "lines.markeredgewidth": 1.4,
    "legend.frameon": False, "legend.fontsize": 9, "figure.dpi": 150,
    "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
})


def load(name):
    path = os.path.join(OUT, name + ".npz")
    return np.load(path) if os.path.exists(path) else None


def zone_r2(sse, sst, r):
    return [1 - sse[(r >= lo) & (r < hi)].sum() / sst[(r >= lo) & (r < hi)].sum()
            for _, lo, hi in ZONES]


def image(ax, v, half, title, **kw):
    n = int(round(np.sqrt(v.size)))
    im = ax.imshow(v.reshape(n, n), origin="lower", extent=(-half, half, -half, half),
                   cmap=SEQ, interpolation="nearest", **kw)
    ax.set_title(title)
    ax.grid(False)
    ax.set_xlabel("x  [λ/D]")
    for s in ax.spines.values():
        s.set_visible(False)
    return im


def endlabel(ax, x, y, text, dy=0.0, ha="left", dx=6):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", color=INK2,
                fontsize=8.5, va="center", ha=ha)


def radial_median(v, r, edges):
    return np.array([np.median(v[(r >= a) & (r < b)]) for a, b in zip(edges[:-1], edges[1:])])


def fig1():
    d = load("ref")
    if d is None:
        return
    r, sst = d["r"], d["oracle__sst"]
    half = float(d["half"])
    ul = d["oracle__lin_k80_n200000"] / sst
    uq = d["oracle__quad_k80_n200000"] / sst
    fig, axs = plt.subplots(1, 4, figsize=(15.5, 4.1), layout="constrained",
                            gridspec_kw=dict(width_ratios=[1.08, 1, 1, 1.1]))
    im0 = image(axs[0], d["psf_mean"] / d["psf_mean"].max(), half, "Mean PSF (peak = 1)",
                norm=LogNorm(1e-5, 1))
    axs[0].set_ylabel("y  [λ/D]")
    fig.colorbar(im0, ax=axs[0], fraction=0.05, pad=0.03)
    norm = LogNorm(1e-3, 1)
    image(axs[1], np.clip(ul, 1e-3, 1), half, "Unexplained: linear model", norm=norm)
    im2 = image(axs[2], np.clip(uq, 1e-3, 1), half, "Unexplained: Hessian model", norm=norm)
    cb = fig.colorbar(im2, ax=axs[1:3], fraction=0.025, pad=0.02)
    cb.set_label("1 − R²  (held-out frames)", color=INK2)
    edges = np.arange(0, 12.01, 0.75)
    rc = 0.5 * (edges[:-1] + edges[1:])
    ax = axs[3]
    yl, yq = radial_median(ul, r, edges), radial_median(uq, r, edges)
    ax.plot(rc, yl, color=ORANGE, marker="o", label="linear in WFS modes")
    ax.plot(rc, yq, color=BLUE, marker="o", label="Hessian (degree 2)")
    ax.set_yscale("log")
    ax.set_ylim(3e-4, 1.5)
    ax.set_xlim(0, 13.4)
    ax.set_xlabel("distance from PSF centre  [λ/D]")
    ax.set_title("Median unexplained vs radius")
    ax.set_ylabel("1 − R²")
    ax.legend(loc="lower right")
    endlabel(ax, rc[-1], yl[-1], f"{yl[-1]:.2f}", dy=0)
    endlabel(ax, rc[-1], yq[-1], f"{yq[-1]:.3f}", dy=0)
    fig.suptitle("A degree-2 polynomial of the WFS modes predicts the PSF; a linear map does not"
                 "   (0.3 rad RMS, 80 modes, 200k training frames, noiseless)",
                 x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(os.path.join(HERE, "fig1_model_quality.png"))
    plt.close(fig)


def fig2():
    amps = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5]
    rows = []
    for a in amps:
        d = load("ref" if a == 0.3 else f"amp{a:g}")
        if d is None:
            continue
        n = int(d["ntrain"])
        r = d["r"]
        rows.append((a, zone_r2(d[f"oracle__quad_k80_n{n}"], d["oracle__sst"], r),
                     zone_r2(d[f"oracle__lin_k80_n{n}"], d["oracle__sst"], r)))
    if len(rows) < 2:
        return
    x = np.array([q[0] for q in rows])
    fig, axs = plt.subplots(1, 4, figsize=(15.5, 3.9), sharey=True,
                            layout="constrained")
    for iz, (zname, _, _) in enumerate(ZONES):
        ax = axs[iz]
        yq = np.array([q[1][iz] for q in rows])
        yl = np.array([q[2][iz] for q in rows])
        ax.plot(x, yl, color=ORANGE, marker="o", label="linear in WFS modes")
        ax.plot(x, yq, color=BLUE, marker="o", label="Hessian (degree 2)")
        ax.set_title(f"{zname} λ/D")
        ax.set_xlabel("wavefront RMS  [rad]")
        ax.set_ylim(0, 1.06)
        ax.set_xlim(0, 1.62)
        i3 = int(np.argmin(np.abs(x - 0.3)))
        endlabel(ax, x[i3], yq[i3], f"{yq[i3]:.2f}", dy=9, dx=4)
        endlabel(ax, x[i3], yl[i3], f"{yl[i3]:.2f}", dy=-9, ha="right", dx=-5)
        endlabel(ax, x[-1], yq[-1], f"{yq[-1]:.2f}", dy=7, ha="center", dx=0)
        if yl[-1] > 0.1:
            endlabel(ax, x[-1], yl[-1], f"{yl[-1]:.2f}", dy=-9, ha="center", dx=0)
    axs[0].set_ylabel("R²  (pooled over the zone, held-out frames)")
    axs[0].legend(loc="lower left")
    fig.suptitle("The Hessian model is accurate up to about 0.3 rad RMS and degrades beyond: "
                 "the PSF stops being a degree-2 function of the wavefront", x=0.01, ha="left",
                 fontsize=11.5, fontweight="bold")
    fig.savefig(os.path.join(HERE, "fig2_amplitude.png"))
    plt.close(fig)


def fig3():
    d, dc = load("ref"), load("refextra")
    if d is None:
        return
    r = d["r"]
    iz = 2  # 4-8 lambda/D zone
    fig, axs = plt.subplots(1, 4, figsize=(15.5, 3.9), layout="constrained")
    # (a) training-set size
    ax = axs[0]
    ns = np.array([2000, 5000, 10000, 20000, 50000, 100000, 200000])
    yq = np.array([zone_r2(d[f"oracle__quad_k80_n{n}"], d["oracle__sst"], r)[iz] for n in ns])
    yl = np.array([zone_r2(d[f"oracle__lin_k80_n{n}"], d["oracle__sst"], r)[iz] for n in ns])
    ax.plot(ns, yl, color=ORANGE, marker="o", label="linear, least squares")
    if dc is not None:
        yc = np.array([zone_r2(dc[f"oracle__corr_k80_n{n}"], dc["oracle__sst"], r)[iz]
                       for n in ns])
        ax.plot(ns, yc, color=AQUA, marker="s", label="Hessian, cross-moments only")
        endlabel(ax, ns[-1], yc[-1], f"{yc[-1]:.2f}", dy=-7)
    ax.plot(ns, yq, color=BLUE, marker="o", label="Hessian, least squares")
    ax.axvline(3321, color=AXIS, lw=1.0)
    ax.text(3321 * 1.12, 0.03, "3321 coefficients\nper PSF pixel", color=MUTED, fontsize=8.5,
            va="bottom")
    ax.set_xscale("log")
    ax.set_xlim(1.6e3, 4.5e5)
    ax.set_ylim(0, 1.04)
    ax.set_xlabel("training frames")
    ax.set_ylabel("R²  (4 - 8 λ/D zone, held-out frames)")
    ax.set_title("Training frames")
    ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.3))
    endlabel(ax, ns[-1], yq[-1], f"{yq[-1]:.2f}", dy=5)
    endlabel(ax, ns[-1], yl[-1], f"{yl[-1]:.2f}", dy=0)
    # (b) WFS noise
    ax = axs[1]
    s2 = np.array([0.1, 0.3, 1.0, 3.0])
    yq = [zone_r2(d[f"oraclenoise{s}__quad_k80_n200000"], d[f"oraclenoise{s}__sst"], r)[iz]
          for s in s2]
    yl = [zone_r2(d[f"oraclenoise{s}__lin_k80_n200000"], d[f"oraclenoise{s}__sst"], r)[iz]
          for s in s2]
    xp, yp = [], []
    for name in ("pyr1e+06", "pyr100000", "pyr10000", "pyr1000"):
        la = float(np.median(d[f"{name}__lin_a"]))
        xp.append(1.0 / la - 1.0)
        yp.append(zone_r2(d[f"{name}__quad_k80_n200000"], d[f"{name}__sst"], r)[iz])
    ax.plot(s2, yl, color=ORANGE, marker="o", label="linear, noisy true modes")
    ax.plot(s2, yq, color=BLUE, marker="o", label="Hessian, noisy true modes")
    ax.plot(xp, yp, color=AQUA, marker="s", ls="none", label="Hessian, pyramid + photon noise")
    for xx, yy, lab in zip(xp, yp, ("10⁶ ph/frame", "10⁵", "10⁴", "10³")):
        endlabel(ax, xx, yy, lab, dy=-11, ha="left", dx=4)
    ax.set_xscale("log")
    ax.set_xlim(1.5e-3, 6)
    ax.set_ylim(0, 1.04)
    ax.set_xlabel("WFS noise variance / signal variance, per mode")
    ax.set_title("WFS noise")
    ax.legend(loc="lower left")
    # (c) number of WFS modes kept
    ax = axs[2]
    ko = np.array([10, 20, 40, 60, 80])
    yo = [zone_r2(d[f"oracle__quad_k{k}_n200000"], d["oracle__sst"], r)[1] for k in ko]
    kp = np.array([20, 40, 60, 80, 100, 120])
    ypy = [zone_r2(d[f"pyr__quad_k{k}_n200000"], d["pyr__sst"], r)[1] for k in kp]
    ax.plot(ko, yo, color=BLUE, marker="o", label="true modes")
    ax.plot(kp, ypy, color=AQUA, marker="s", label="pyramid PCA")
    ax.axvline(80, color=AXIS, lw=1.0)
    ax.text(82, 0.03, "80 modes\nin the wavefront", color=MUTED, fontsize=8.5, va="bottom")
    ax.set_ylim(0, 1.04)
    ax.set_xlim(0, 126)
    ax.set_xlabel("WFS modes kept")
    ax.set_ylabel("R²  (1.25 - 4 λ/D zone)")
    ax.set_title("WFS modes kept")
    ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.5), title="kept in order of",
              title_fontsize=8.5)
    # (d) number of PSF PCA modes kept
    ax = axs[3]
    js = np.array([10, 25, 50, 100, 200, 400, 800, 1600])
    yw = [zone_r2(d[f"psfpca_sqrtmean__ceil_j{j}"], d["oracle__sst"], r)[iz] for j in js]
    yn = [zone_r2(d[f"psfpca_none__ceil_j{j}"], d["oracle__sst"], r)[iz] for j in js]
    ax.plot(js, yn, color=ORANGE, marker="o", label="plain PCA")
    ax.plot(js, yw, color=BLUE, marker="o", label="photon-noise-weighted PCA")
    ax.set_xscale("log")
    ax.set_ylim(0, 1.04)
    ax.set_xlabel(f"PSF PCA modes kept  (of {int(d['npsf'])} pixels)")
    ax.set_ylabel("variance retained  (4 - 8 λ/D zone)")
    ax.set_title("PSF modes kept")
    ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.42))
    fig.suptitle("What the fit needs: frames well beyond the coefficient count, a WFS with "
                 "high per-mode S/N, every excited mode, and hundreds of PSF modes",
                 x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(os.path.join(HERE, "fig3_requirements.png"))
    plt.close(fig)


def fig4():
    d = load("ref")
    if d is None:
        return
    r = d["r"]
    half = float(d["half"])
    fig, axs = plt.subplots(1, 4, figsize=(15.5, 4.1), layout="constrained",
                            gridspec_kw=dict(width_ratios=[1, 1, 1.1, 1.1]))
    image(axs[0], d["coef__top2_fit"], half, "Two largest positive eigenvalues", vmin=0, vmax=1)
    axs[0].set_ylabel("y  [λ/D]")
    im = image(axs[1], d["coef__neg_fit"], half, "All negative eigenvalues", vmin=0, vmax=1)
    cb = fig.colorbar(im, ax=axs[0:2], fraction=0.025, pad=0.02)
    cb.set_label("share of quadratic-term variance", color=INK2)
    # eigenvalue spectra at three radii
    ax = axs[2]
    for rr, col in zip((0.0, 3.0, 5.0), ORD3):
        i = int(np.argmin(np.abs(r - rr)))
        ev = d["coef__ev_fit"][i]
        ax.plot(np.arange(1, ev.size + 1), ev / np.abs(ev).max(), color=col, marker="o", ms=3.5,
                mew=0, lw=1.2, label=f"r = {r[i]:.1f} λ/D")
    ax.axhline(0, color=AXIS, lw=1.0)
    ax.set_xscale("log")
    ax.set_xlabel("eigenvalue rank")
    ax.set_ylabel("eigenvalue / largest magnitude")
    ax.set_title("Hessian spectrum of one pixel")
    ax.legend(loc="lower left", title="pixel at", title_fontsize=8.5)
    # radial profiles
    ax = axs[3]
    edges = np.arange(0, 12.01, 0.75)
    rc = 0.5 * (edges[:-1] + edges[1:])
    ys = radial_median(d["coef__top2_spk"], r, edges)
    yt = radial_median(d["coef__top2_tay"], r, edges)
    yf = radial_median(d["coef__top2_fit"], r, edges)
    ax.plot(rc, ys, color=AQUA, marker="s", label="analytic, S only")
    ax.plot(rc, yt, color=ORANGE, marker="o", label="analytic, S + T")
    ax.plot(rc, yf, color=BLUE, marker="o", ms=4.5, label="fitted from data")
    ax.set_ylim(0, 1.04)
    ax.set_xlim(0, 12.2)
    ax.set_xlabel("distance from PSF centre  [λ/D]")
    ax.set_ylabel("share in the two largest positive eigenvalues")
    ax.set_title("Two-channel share vs radius")
    ax.legend(loc="center left", bbox_to_anchor=(0.04, 0.42))
    fig.suptitle("Per-pixel Hessians: two dominant positive channels (real and imaginary part "
                 "of the speckle field), plus a full-rank signed remainder",
                 x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(os.path.join(HERE, "fig4_channels.png"))
    plt.close(fig)


def fig5():
    d = load("sync")
    if d is None:
        return
    r = d["r"]
    lags = d["lags"] - 2.25
    fig, axs = plt.subplots(1, 3, figsize=(15.5, 3.9), layout="constrained")
    for ax, name, title in ((axs[0], "quad", "Lag scan, full Hessian model"),
                            (axs[1], "qonly", "Lag scan, quadratic terms only")):
        for m, col in zip((1, 4, 16), ORD3):
            y = d[f"curve_{name}_m{m}"]
            ax.plot(lags, y, color=col, label=f"{m} WFS frame{'s' if m > 1 else ''}")
        ax.axvline(0, color=AXIS, lw=1.0)
        ax.set_xlabel("trial lag − true lag  [WFS frames]")
        ax.set_ylim(0, 1.04)
        ax.set_title(title)
    axs[0].set_ylabel("held-out R² of 20 PSF PCA modes")
    axs[0].legend(loc="lower center", title="PSF exposure", title_fontsize=8.5)
    axs[1].set_ylabel("same, point-symmetric part of the PSF")
    ax = axs[2]
    shifts = np.array([0.0, 0.25, 0.5, 1.0, 2.0, 4.0])
    for m, col in zip((1, 4, 16), ORD3):
        sst = d[f"fit_m{m}__sst"]
        y = [zone_r2(d[f"fit_m{m}__" + ("exact" if s == 0 else f"lag{s:g}")], sst, r)[2]
             for s in shifts]
        ax.plot(shifts, y, color=col, marker="o", label=f"{m} WFS frame{'s' if m > 1 else ''}")
        if m == 1:
            endlabel(ax, shifts[3], y[3], f"1 frame off: {y[3]:.2f}", dy=-12, ha="right", dx=-2)
    ax.set_ylim(0, 1.04)
    ax.set_xlabel("timing error  [WFS frames]")
    ax.set_ylabel("R² of the full model  (4 - 8 λ/D zone)")
    ax.set_title("Cost of a timing error")
    ax.legend(loc="lower left", title="PSF exposure", title_fontsize=8.5)
    fig.suptitle("Synchronisation: the model's own goodness of fit peaks at the true lag, and "
                 "the fit loses accuracy quickly when the timing is off",
                 x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(os.path.join(HERE, "fig6_sync.png"))
    plt.close(fig)


def fig6():
    d = load("channels")
    if d is None:
        return
    r, amps = d["r"], d["amps"]
    fig, axs = plt.subplots(1, 4, figsize=(15.5, 3.9), sharey=True, layout="constrained")
    series = (("aff2", ORANGE, "o", "2 squared affine channels"),
              ("poly2", BLUE, "o", "Hessian (degree-2 polynomial)"),
              ("quad2", AQUA, "s", "2 squared quadratic channels"))
    for iz, (zname, lo, hi) in enumerate(ZONES):
        ax = axs[iz]
        sel = (r >= lo) & (r < hi)
        for key, col, mk, lab in series:
            y = [np.median(1 - d[f"amp{a:g}__{key}"][sel] / d[f"amp{a:g}__sst"][sel])
                 for a in amps]
            ax.plot(amps, y, color=col, marker=mk, label=lab)
            endlabel(ax, amps[-1], y[-1], f"{y[-1]:.2f}")
        ax.set_title(f"{zname} λ/D")
        ax.set_xlabel("wavefront RMS  [rad]")
        ax.set_ylim(0, 1.06)
        ax.set_xlim(0.2, 1.16)
    axs[0].set_ylabel("median R² over the pixels of a radial cut")
    axs[0].legend(loc="lower left")
    fig.suptitle("Channel models: two squared quadratic channels track the PSF further than "
                 "the Hessian polynomial; two squared affine channels fall short", x=0.01,
                 ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(os.path.join(HERE, "fig5_channel_models.png"))
    plt.close(fig)


def gallery(tag, nshow=6):
    """One row per frame: WF, WFS image, PSF, PSF rebuilt from the WFS image, residual."""
    d = load(tag)
    if d is None:
        return
    npb, nw, ns, half = int(d["npb"]), int(d["nw"]), int(d["nside"]), float(d["half"])
    peak = d["psf0"].max()
    psf, pred, mean = d["psf"] / peak, d["pred"] / peak, d["psf_mean"] / peak
    nshow = min(nshow, len(psf))
    phi = np.full((nshow, npb * npb), np.nan)
    phi[:, d["pidx"]] = d["phi"][:nshow]
    phi = phi.reshape(nshow, npb, npb)
    # WFS frames, in units of the mean illuminated level of the flat-wavefront frame. The four
    # pupil images are 3 pupil diameters apart on the detector: show them side by side.
    full = np.full((nshow, nw * nw), np.nan)
    full[:, d["wfs_sel"]] = d["wfs"][:nshow] / d["wfs0"].mean()
    full = full.reshape(nshow, nw, nw)
    hw = int(np.ceil(d["dpix"] / 2 / float(d["wfs_pitch"]))) + 1
    step = 2 * hw + 2
    wim = np.full((nshow, step + 2 * hw + 1, step + 2 * hw + 1), np.nan)
    for iy, cy in enumerate(d["wfs_centres"]):
        for ix, cx in enumerate(d["wfs_centres"]):
            wim[:, iy * step : iy * step + 2 * hw + 1, ix * step : ix * step + 2 * hw + 1] = (
                full[:, cy - hw : cy + hw + 1, cx - hw : cx + hw + 1])
    vphi = float(np.ceil(np.nanmax(np.abs(phi)) * 10) / 10)
    vw = float(np.nanmax(wim))
    dmax = np.abs(psf[:nshow] - mean).max()
    vres = min(v for v in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0) if v >= dmax)
    axp = (np.arange(ns) - (ns - 1) / 2.0) * (2 * half / ns)
    halo = np.hypot(axp[:, None], axp[None, :]).ravel() >= 1.25
    lognorm = LogNorm(1e-5, 1)
    symnorm = SymLogNorm(linthresh=1e-5, linscale=0.6, vmin=-vres, vmax=vres)
    ext = (-half, half, -half, half)
    titles = ("Wavefront", "WFS image (4 pyramid pupils)", "PSF", "PSF rebuilt from WFS image",
              "PSF − mean PSF", "Residual: PSF − rebuilt")
    fig = plt.figure(figsize=(16.0, 2.5 * nshow + 1.5), layout="constrained")
    gs = fig.add_gridspec(nshow + 1, 6, height_ratios=[1] * nshow + [0.07])
    ims = [None] * 6
    for i in range(nshow):
        frac = 1 - ((psf[i] - pred[i]) ** 2).sum() / ((psf[i] - mean) ** 2).sum()
        fhalo = 1 - ((psf[i] - pred[i])[halo] ** 2).sum() / ((psf[i] - mean)[halo] ** 2).sum()
        panels = (
            (phi[i], dict(cmap=DIV, vmin=-vphi, vmax=vphi)),
            (wim[i], dict(cmap=SEQ, vmin=0, vmax=vw)),
            (psf[i].reshape(ns, ns), dict(cmap=SEQ, norm=lognorm, extent=ext)),
            (np.clip(pred[i], 1e-5, None).reshape(ns, ns),
             dict(cmap=SEQ, norm=lognorm, extent=ext)),
            ((psf[i] - mean).reshape(ns, ns), dict(cmap=DIV, norm=symnorm, extent=ext)),
            ((psf[i] - pred[i]).reshape(ns, ns), dict(cmap=DIV, norm=symnorm, extent=ext)),
        )
        for j, (img, kw) in enumerate(panels):
            ax = fig.add_subplot(gs[i, j])
            ims[j] = ax.imshow(img, origin="lower", interpolation="nearest", **kw)
            ax.grid(False)
            for sp in ax.spines.values():
                sp.set_visible(False)
            if j < 2:
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                ax.set_xticks([-10, -5, 0, 5, 10])
                ax.set_yticks([-10, -5, 0, 5, 10])
                ax.tick_params(labelsize=7.5, length=2)
                if i < nshow - 1:
                    ax.set_xticklabels([])
                if j > 2:
                    ax.set_yticklabels([])
            if i == 0:
                ax.set_title(titles[j])
            if j == 0:
                rms = np.sqrt(np.nanmean(phi[i] ** 2))
                ax.set_ylabel(f"frame {i},  WF {rms:.2f} rad RMS\nexplained: {100 * frac:.1f}% "
                              f"overall\n{100 * fhalo:.1f}% beyond 1.25 λ/D", color=INK,
                              fontsize=9.5)
    labels = ("phase  [rad]", "intensity / flat-wavefront mean", "intensity / unaberrated peak",
              "intensity / unaberrated peak", "difference / unaberrated peak",
              "difference / unaberrated peak")
    for j in range(6):
        cb = fig.colorbar(ims[j], cax=fig.add_subplot(gs[nshow, j]), orientation="horizontal")
        cb.set_label(labels[j], color=INK2, fontsize=8.5)
        cb.ax.tick_params(labelsize=7.5)
        if j >= 4:
            cb.set_ticks([-vres, -1e-3, 0, 1e-3, vres])
            cb.set_ticklabels([f"−{vres:g}", "−10⁻³", "0", "10⁻³", f"{vres:g}"])
    nph = float(d["nph"])
    fig.suptitle(
        f"Test frames at {float(d['sigtot']):g} rad RMS, {float(d['pix_per_ld']):g} pixels per "
        "λ/D, " + ("noiseless WFS" if nph == 0 else f"{nph:g} photons per WFS frame")
        + ": PSF rebuilt from the WFS image by the Hessian model",
        x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(os.path.join(HERE, tag + ".png"), dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        for name in sys.argv[1:]:
            gallery(name)
            print("gallery", name, "done")
        raise SystemExit
    for f in (fig1, fig2, fig3, fig4, fig5, fig6):
        f()
        print(f.__name__, "done")
