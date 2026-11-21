"""Figures for the 2-WFS + 1-DM calibration algorithm study (light surface, validated palette)."""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from multiprocessing import Pool
from sim import simulate
import estimators as E
import decomp as Dc

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "grid.linestyle": "-", "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 2.0, "figure.dpi": 150,
})
REF = dict(sig_nA=0.002, sig_nB=0.002, c_hi=0.6)

# ---------------------------------------------------------------------------------- figure 1
def fig_blend():
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 7.0), sharex=True, sharey=True,
                             constrained_layout=True)
    for j, tag in enumerate(("int", "pred")):
        t = np.load(f"theory_{tag}.npz"); c = np.load(f"cond_{tag}.npz")
        fr = t["fr"]; sl = slice(4, 40); k = np.arange(1, len(fr), 3)
        g = t["g"]
        med = lambda a: np.median(
            a[:, sl] / (g[None, sl] if a is not c["gc"] and a is not c["cfb"] else 1.0),
            axis=1)
        sim_o = np.median(t["gf"][:, sl] / g[None, sl], 1)
        bl = np.median(t["pf"][:, sl] / g[None, sl], 1)
        inv = np.median(t["cfb"][:, sl] / g[None, sl], 1)
        sim_c = np.median(c["gc"][:, sl], 1)
        name = "Integrator" if tag == "int" else "Predictive"
        for i, (ys, lab) in enumerate((
                (sim_o, "disturbance term known exactly (oracle)"),
                (sim_c, "WFS A term fitted with a free frequency response"))):
            ax = axes[i, j]
            ax.axhline(1.0, color=INK2, lw=1.0)
            ax.plot(fr[1:], inv[1:], color=C3, label="inverse-controller limit  −Re[1/K(f)] / g")
            if i == 0:
                ax.plot(fr[1:], bl[1:], color=C2, label="blend formula  (1−ρ)·g + ρ·(−Re[1/K])")
            ax.plot(fr[k], ys[k], "o", color=C1, ms=5.5, mec=SURF, mew=1.2,
                    label="simulated frequency-local estimate / g")
            ax.set_xscale("log"); ax.set_xlim(3, 1000); ax.set_ylim(-3.2, 4.2)
            ax.set_title(f"{name}: {lab}", fontsize=9.6)
            if j == 0:
                ax.set_ylabel("estimate ÷ true gain")
            if i == 1:
                ax.set_xlabel("temporal frequency [Hz]")
            ax.text(3.3, 1.12, "true gain", color=INK2, fontsize=8.5, va="bottom")
    axes[0, 0].legend(loc="lower left")
    axes[1, 0].legend(loc="lower left")
    fig.suptitle("What a frequency-local regression of WFS B on the DM2 command returns"
                 " (toy loop, 16 runs, modes 4–39)",
                 x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(OUT / "fig1_frequency_blend.png"); plt.close(fig)

# ---------------------------------------------------------------------------------- figure 2
def _dec(args):
    seed, pred = args
    sim = simulate(seed, predictive=pred, **REF)
    g = sim["gB"]
    c = sim["comp"]
    names = ("dm", "phi", "u", "n")
    A, B, D, *cs = E.sync_tool(sim, 0.0, 2.5, 60, extra=[c[k] for k in names])
    tl = E.est_tool(A, B, D)
    Sxx, Syx = Dc.spectra(A, D, dict(zip(names, cs)))
    fr = np.fft.rfftfreq(256, 1e-3)
    specs = {"Unwhitened least squares": (np.r_[0.0, np.ones(len(fr) - 1)], 1e-6, 1e-6),
             "AR(4) whitening W(z) (shipped)": (Dc.taps_weight(tl["taps"]), tl["ra"], tl["rd"]),
             "Band-limited 20–480 Hz": (np.where((fr >= 20) & (fr <= 480), 1.0, 0.0)
                                        / np.einsum("fii->f", Sxx[:, :60, :60]).real, 0.05, 0.005)}
    return {k: Dc.summarize(Dc.decompose(Sxx, Syx, w, 60, ra, rd, g))
            for k, (w, ra, rd) in specs.items()}

def fig_attrib():
    with Pool(16) as pool:
        res = {tag: pool.map(_dec, [(100 + s, tag == "pred") for s in range(8)])
               for tag in ("int", "pred")}
    comps = [("phi", "WFS A is a noisy proxy for the disturbance", C1),
             ("u", "disturbance seen by WFS B only", C2),
             ("n", "WFS B noise fed back through the loop", C3), ("dm", "DM servo lag", C4)]
    rows, table = [], {}
    for est in res["int"][0]:
        for tag in ("int", "pred"):
            m = {c: float(np.mean([r[est][c] for r in res[tag]]))
                 for c in ("phi", "u", "n", "dm", "total")}
            rows.append((f"{est}\n{'integrator' if tag == 'int' else 'predictive'}", m))
            table[f"{est}|{tag}"] = m
    fig, ax = plt.subplots(figsize=(10.5, 4.9), constrained_layout=True)
    y = np.arange(len(rows))[::-1] * 1.0
    for yi, (lab, m) in zip(y, rows):
        neg = pos = 0.0
        for key, _, col in comps:
            v = m[key]
            if v < 0:
                ax.barh(yi, v, left=neg, height=0.46, color=col, edgecolor=SURF, linewidth=2)
                neg += v
            else:
                ax.barh(yi, v, left=pos, height=0.46, color=col, edgecolor=SURF, linewidth=2)
                pos += v
        ax.plot([m["total"]], [yi], "D", color=INK, ms=7.5, mec=SURF, mew=1.5, zorder=5)
        ax.text(max(pos, m["total"]) + 1.5, yi, f"net {m['total']:+.0f}%", va="center",
                fontsize=9, color=INK)
    ax.axvline(0, color=INK2, lw=1.0)
    ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], fontsize=8.8)
    ax.set_xlabel("contribution to the bias of diag(Mdb), % of the true gain")
    ax.set_xlim(-70, 62); ax.grid(axis="y", visible=False)
    hs = ([plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in comps]
          + [plt.Line2D([], [], marker="D", color=INK, ls="", ms=7)])
    ax.legend(hs, [l for _, l, _ in comps] + ["net bias"], loc="upper right", ncol=1)
    ax.set_title("Where each estimator's bias comes from (toy loop, reference condition, 8 runs)")
    fig.savefig(OUT / "fig2_bias_attribution.png"); plt.close(fig)
    return table

# ---------------------------------------------------------------------------------- figure 3
def fig_conditions(b):
    ests = [("ols", "Unwhitened least squares"), ("tool_wz", "AR(4) whitening W(z) (shipped)"),
            ("band_exact", "Band-limited 20–480 Hz"),
            ("pem32", "Residual-whitening (noise-model) fit"),
            ("iv_past8", "Lagged-WFS-A instrumental variables")]
    keys = [k for k in b if k.endswith("|5s") and not k.startswith("dither")
            and not k.startswith("nA = 0")]
    fig, ax = plt.subplots(figsize=(10.5, 4.4), constrained_layout=True)
    rng = np.random.default_rng(1)
    for i, (e, lab) in enumerate(ests):
        yi = len(ests) - 1 - i
        for tag, col, off in (("int", C1, 0.14), ("pred", C2, -0.14)):
            xs = [b[k][e]["bias"] for k in keys if f"|{tag}|" in k]
            ax.plot(xs, yi + off + rng.uniform(-0.05, 0.05, len(xs)), "o", color=col, ms=6.5,
                    mec=SURF, mew=1.2,
                    label=("integrator" if tag == "int" else "predictive") if i == 0 else None)
    ax.axvline(0, color=INK2, lw=1.0)
    ax.set_yticks(range(len(ests))); ax.set_yticklabels([l for _, l in ests][::-1])
    ax.set_xlabel("bias of the median gain estimate, % of truth"
                  " (one dot per simulated condition, 16 runs each)")
    ax.set_xlim(-95, 55); ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", title="stage-2 control law")
    ax.set_title("Bias across 11 noise / disturbance / loop-gain conditions (WFS A noise present)")
    fig.savefig(OUT / "fig3_bias_across_conditions.png"); plt.close(fig)

# ---------------------------------------------------------------------------------- figure 4
def fig_precision(b, x):
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), sharey=True, constrained_layout=True)
    ts = [0.5, 1.0, 2.0, 5.0]
    for ax, tag in zip(axes, ("int", "pred")):
        wz = [b[f"ref|{tag}|{t}s" if t < 5 else f"ref|{tag}|5s"]["tool_wz"]["permode"] for t in ts]
        iv = [b[f"ref|{tag}|{t}s" if t < 5 else f"ref|{tag}|5s"]["iv_past8"]["permode"] for t in ts]
        dt = [x[f"dither 0.001|{tag}|{t}s"]["w_pm"] for t in (1.0, 2.0, 5.0)]
        for xs, ys, col, lab in (
                (ts, wz, C1, "AR(4) whitening W(z)"), (ts, iv, C2, "lagged-WFS-A IV"),
                ([1.0, 2.0, 5.0], dt, C3, "white DM2 dither, 27% of residual RMS")):
            ax.plot(xs, ys, "-o", color=col, ms=6.5, mec=SURF, mew=1.2, label=lab)
            ax.text(xs[-1] * 1.07, ys[-1], f"{ys[-1]:.0f}%", va="center", fontsize=9, color=INK)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(0.42, 7.5); ax.set_ylim(3, 30)
        ax.set_xticks(ts)
        ax.set_xticklabels([str(t) for t in ts])
        ax.set_yticks([3, 5, 10, 20, 30])
        ax.set_yticklabels(["3", "5", "10", "20", "30"]); ax.minorticks_off()
        ax.set_xlabel("telemetry window [s]")
        ax.set_title("Integrator" if tag == "int" else "Predictive")
    axes[0].set_ylabel("per-mode median |error| of diag(Mdb) [%]")
    axes[0].legend(loc="lower left")
    fig.suptitle("Per-mode accuracy against telemetry length"
                 " (toy loop, reference condition, 16 runs)",
                 x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    fig.savefig(OUT / "fig4_precision_vs_window.png"); plt.close(fig)

if __name__ == "__main__":
    b = json.load(open("bench.json")); x = json.load(open("extra.json"))
    fig_blend(); table = fig_attrib()
    if "--all" in sys.argv:
        fig_conditions(b); fig_precision(b, x)
    json.dump(table, open("attrib.json", "w"), indent=1)
    for k, m in table.items():
        print(f"{k:45s} " + "  ".join(f"{c}={v:+6.1f}" for c, v in m.items()))
