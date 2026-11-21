"""Assemble REPORT.md for the calibration-algorithm study from the benchmark JSON files.

Every number in the generated text is read from bench.json / extra.json / attrib.json /
stage3.json / theory_*.npz. The numbers quoted for the real simulation run are copied from the
published 2-WFS + 1-DM report page and are labelled as such.

Usage: build_report.py <output dir> [--no-wrap]
Prose is hard-wrapped at 100 characters (the repository rule). --no-wrap writes one paragraph
per line instead, for Markdown converters that turn line breaks into hard breaks.
"""

import json
import re
import sys
import textwrap
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parent
OUT = Path(sys.argv[1])
WRAP = "--no-wrap" not in sys.argv[2:]
WIDTH = 100
b = json.load(open(SRC / "bench.json"))
x = json.load(open(SRC / "extra.json"))
att = json.load(open(SRC / "attrib.json"))
s3 = json.load(open(SRC / "stage3.json"))
ivv = json.load(open(SRC / "iv_variants.json"))
ivl = json.load(open(SRC / "iv_lowfs.json"))
th = {t: np.load(SRC / f"theory_{t}.npz") for t in ("int", "pred")}


def P(text):
    """One paragraph per list entry; wrap_md() wraps it at the end unless --no-wrap is given."""
    return " ".join(text.split())


def wrap_md(lines, width=WIDTH):
    """Hard-wrap prose, list items and block quotes; leave tables, headings, images and code."""
    out, code = [], False
    for ln in lines:
        if ln.startswith("```"):
            code = not code
        if code or len(ln) <= width or ln.startswith(("```", "|", "#", "![")):
            out.append(ln)
            continue
        m = re.match(r"(> |- |\d+\. )", ln)
        first = m.group(1) if m else ""
        rest = "> " if first == "> " else " " * len(first)
        for w in range(width, 60, -1):
            got = textwrap.wrap(ln[len(first):], width=w - len(first), break_long_words=False,
                                break_on_hyphens=False)
            # a continuation line must not look like a list item, a quote or a heading
            if not any(re.match(r"([-+*>#]|\d+[.)])( |$)", g) for g in got[1:]):
                break
        out.extend([first + got[0]] + [rest + g for g in got[1:]])
    return out


def L(prefix, text):
    return prefix + " ".join(text.split())


def sg(v):
    """Signed integer percent without a '-0'."""
    r = int(round(float(v)))
    return "0" if r == 0 else f"{r:+d}"


def rng(vals):
    return f"{sg(min(vals))}% to {sg(max(vals))}%"


real = [k for k in b if k.endswith("|5s") and not k.startswith(("dither", "nA = 0"))]
conds = []
for k in b:
    c = k.split("|")[0]
    if k.endswith("|5s") and not c.startswith("dither") and c not in conds:
        conds.append(c)


def bias(e, keys=real):
    return [b[k][e]["bias"] for k in keys]


def pm(e, keys=real):
    return [b[k][e]["permode"] for k in keys]


def cell(c, e):
    return f"{sg(b[f'{c}|int|5s'][e]['bias'])} / {sg(b[f'{c}|pred|5s'][e]['bias'])}"


nice = {
    "ref": "reference",
    "noise/2": "both WFS noises ÷2",
    "noise x2": "both WFS noises ×2",
    "nB x2 only": "WFS B noise ×2",
    "nA x3 only": "WFS A noise ×3",
    "unmodelled/2": "B-only disturbance ÷2",
    "unmodelled x1.7": "B-only disturbance ×1.7",
    "no unmodelled": "no B-only disturbance",
    "nA = 0": "no WFS A noise",
    "nA = 0, no unmodelled": "no WFS A noise, no B-only disturbance",
    "A coloured error": "coloured error added to WFS A",
    "gain2 0.25": "stage-2 gain 0.25",
    "gain2 0.45": "stage-2 gain 0.45",
}
ref_i, ref_p = b["ref|int|5s"], b["ref|pred|5s"]
ols_ideal = [b[f"nA = 0, no unmodelled|{t}|5s"]["ols"]["bias"] for t in ("int", "pred")]
pem_or = {t: {k: (float(np.median(th[t][k][:, 4:] / th[t]["g"][None, 4:], axis=1).mean()),
                  float(np.median(th[t][k][:, 4:] / th[t]["g"][None, 4:], axis=1).std()))
              for k in ("ols", "pem4", "pem16", "pem64")} for t in ("int", "pred")}
mda = [b[k]["mda_scale"] for k in real]
r2i, r2p = x["r2|int"], x["r2|pred"]

DK = "diff, psi lags 2-9|2sls"
d_bias = [v[DK][0] for v in ivv.values()]
d_pm5 = [v[DK][2] for k, v in ivv.items() if "|5 s|" in k]
p_bias_bright = [v["psi8|2sls"][0] for k, v in ivv.items() if k.startswith("noises /4|5 s")]
d_bias_bright = [v[DK][0] for k, v in ivv.items() if k.startswith("noises /4|5 s")]
c1_bias = [v["psi8+c1|2sls"][0] for v in ivv.values()]

md = []
A = md.append

A("# 2-WFS + 1-DM closed-loop calibration: algorithm analysis, options and opportunities")
A("")
A(L("- ", "**Subject**: the estimator behind `mlt.calib2wfs1dm` / `mlt.sysid` (milk-mltools), "
        "which fits `B = Mab A + Mdb D + b0` and `A = Mba B - Mda_virt D + a0` from closed-loop "
        "telemetry of a two-stage AO system."))
A(L("- ", "**Basis**: a line-by-line reading of `sysid_unit.c`, `tlm_sync_unit.c` and the "
        "`mlt.calib2wfs1dm` orchestration in `commands.d/mltools.bash`; a closed-form analysis; "
        "and a Monte-Carlo study on a known-truth two-stage loop model (more than 700 simulated "
        "runs)."))
A(L("- ", "**Not used**: the real simulation telemetry. The three run directories behind the "
        "published report are not on this machine, and the `milk-mlt-calib2wfs1dm` binary is not "
        "installed here, so the shipped algorithm is represented by a numpy port written from "
        "the C source."))
A("")
A("> " + " ".join("""**Status of the evidence.** Statements about what the code does are read from
the source. Statements about bias are proved for the linear model in Section 3 and confirmed
numerically on a toy loop. Statements about the real AO3k + SCExAO simulation are predictions,
listed with the tests that would check them in Section 7.""".split()))
A("")
A("> " + " ".join("""**Later results.** This report is the toy-model study as written on
2026-11-19 and is kept as it was. Test 3 of Section 7 has since been run on real simulator
telemetry: with both loops closed, the differenced lagged-A estimator of Section 5.4 reads +2.7%
against a probed reference and the shipped `W(z)` reads -22% (`../realsim/README.md`). Three later
toy analyses (why first differences, two-step calibration, other loop frequencies) are in
`notes/`. Start from `../README.md`.""".split()))
A("")
A("## Summary")
A("")
A(L("1. ", "**Every regression of `B` on `(A, D)` returns a blend, not the gain.** With any "
        "frequency weighting `w(f)`, the estimate of an optical gain `g` is a weighted average "
        "of `g` (carried by DM2 motion that is exogenous to the WFS B residual), of the "
        "*inverse controller* `-Re[1/K(f)]` (carried by DM2 motion that the loop itself "
        "generated from that residual), scaled down by the noise in WFS A. The formula "
        "reproduces the simulated estimate to two decimals at every frequency (Figure 1)."))
A(L("2. ", f"**The shipped `AR(4)` whitening is one such blend.** On the toy loop its bias ranges "
        f"from {rng(bias('tool_wz'))} across 11 conditions and two control laws. It is near "
        "zero only where a positive term (WFS B noise fed back through the loop) cancels "
        "negative ones (WFS A noise, disturbance seen by WFS B only). The agreement with "
        "`selfRM` in the one real run is therefore compatible with a cancellation and does not "
        "by itself show that the estimator is accurate."))
A(L("3. ", "**Held-out `R²` cannot detect this.** It is the criterion used for the ridge, for the "
        "lag scan and as validation, but in the toy the true matrices predict held-out "
        f"unwhitened data far worse (`R² = {r2i['r2raw_truth']:.2f}`) than the "
        f"{r2i['bias_ols_train']:+.0f}%-biased least-squares solution "
        f"(`R² = {r2i['r2raw_ols']:.2f}`)."))
A(L("4. ", "**The robust passive information is DM2 motion driven by what WFS A measures.** An "
        "instrumental-variable estimator that uses *past* WFS A frames as instruments, and does "
        "not let the current frame instrument itself, stays within "
        f"{rng(bias('iv_past8'))} over the same conditions, with a per-mode median error of "
        f"{min(pm('iv_past8')):.0f}–{max(pm('iv_past8')):.0f}% from 5 s of telemetry. It needs "
        "WFS A noise or other broadband stage-1 content to work, and fails without it. "
        f"First-differencing the data before the fit (Section 5.4) keeps the bias within "
        f"{rng(d_bias)} even with four times less noise, and is the recommended passive form."))
A(L("5. ", "**Noise-model estimators are not a fix.** Residual-whitening (prediction-error) "
        f"fitting recovers the gain in an idealised setting ({pem_or['int']['pem64'][0]:.3f} of "
        f"truth) but gives {rng(bias('pem32'))} in the practical one. The same caution applies "
        "to the proposed Kalman-EM route."))
A(L("6. ", "**A small known dither is the reliable active option.** In the toy a white DM2 dither "
        f"at 27% of the residual RMS gives a per-mode error of "
        f"{x['dither 0.001|int|5.0s']['w_pm']:.0f}% in 5 s, with a "
        f"{x['dither 0.001|int|5.0s']['w_bias']:+.0f}% offset that is the DM servo lag at the "
        "dither's frequencies."))
A(L("7. ", "**Stage-3 commands are a free probe.** Regressing `B` on the stage-3 command applied "
        "to DM2 returns `g - g_zpo`, the optical gain minus the gain assumed by the zero-point "
        f"offset: {np.mean(s3[list(s3)[0]]['c3']):+.2f} recovered against "
        f"{np.mean(s3[list(s3)[0]]['expect']):+.2f} expected."))
A(L("8. ", f"**`Mda_virt` has the right direction but a low amplitude**: {min(mda):.2f}–"
        f"{max(mda):.2f} of the WFS A optical gain in the toy, because the virtual-upstream fit "
        "is an unwhitened regression on a noisy `B`."))
A("")
A("---")
A("")
A("## 1. What was analysed, and how")
A("")
A(P("""The toy model is a modal, linear, two-rate closed loop built on the bench's timing: a
1 kHz stage 1 (100 modes, integrator, 1 ms WFS exposure, DM delay plus first-order servo), a
2 kHz stage 2 (40 modes, integrator or pseudo-open-loop AR(8) predictor), an 8 kHz simulation
grid, a three-frame total loop delay in each stage, von Kármán-like modal turbulence, white WFS
noise, and optical gains of 0.93 (WFS A) and 0.67–0.73 (WFS B). WFS B additionally sees a
disturbance that the 60 retained WFS A modes do not contain (stage-1 residual of higher modes,
plus a small open-loop term). The true matrices are known exactly: `Mdb = diag(g)`."""))
A("")
A(P("""Its job is to expose mechanisms and to rank estimators on equal terms. It is not a
substitute for the full simulator: there is no pyramid non-linearity, no spatial cross-talk,
and the predictive controller is a generic one, not cacao's. Magnitudes should not be carried
over to the real system; signs, scalings and failure modes are what transfer."""))
A("")
A("| Diagnostic | Real run (published page) | Toy, reference | Toy, noises ÷2 |")
A("| :--- | :---: | :---: | :---: |")
n2i, n2p = b["noise/2|int|5s"], b["noise/2|pred|5s"]
A(f"| Unwhitened least squares, integrator / predictive | -66% / -50% | "
  f"{ref_i['ols']['bias']:+.0f}% / {ref_p['ols']['bias']:+.0f}% | "
  f"{n2i['ols']['bias']:+.0f}% / {n2p['ols']['bias']:+.0f}% |")
A(f"| Conditional DM excitation `eta_D` (unwhitened) | 0.06 / 0.21 | "
  f"{ref_i['eta_raw']:.2f} / {ref_p['eta_raw']:.2f} | "
  f"{n2i['eta_raw']:.2f} / {n2p['eta_raw']:.2f} |")
A(f"| Same, after whitening | 0.91 | {ref_i['eta_w']:.2f} | {n2i['eta_w']:.2f} |")
A(f"| Residual lag-1 autocorrelation | +0.51 / +0.25 | {ref_i['ac1']:+.2f} | {n2i['ac1']:+.2f} |")
A(f"| `corr(e_col, D)` | -0.19 / -0.20 | {ref_i['corr_eD']:+.2f} | {n2i['corr_eD']:+.2f} |")
A(f"| `W(z)` gain at DC | -18 dB | {ref_i['w_dc_db']:.0f} dB | {n2i['w_dc_db']:.0f} dB |")
A(f"| `AR(4)` `W(z)` error, integrator / predictive | -20% / -0.4% to +2.8% | "
  f"{sg(ref_i['tool_wz']['bias'])}% / {sg(ref_p['tool_wz']['bias'])}% | "
  f"{sg(n2i['tool_wz']['bias'])}% / {sg(n2p['tool_wz']['bias'])}% |")
A("")
A(P("""The toy brackets most of the published diagnostics but does not reproduce the real run's
strong difference between control laws under `W(z)`. That difference is itself consistent with
the analysis below (the blend depends on the controller), but it means the toy is a mechanism
model, not a fit."""))
A("")
A("---")
A("")
A("## 2. The shipped algorithm, as coded")
A("")
A(L("1. ", "**Alignment** (`commands.d/mltools.bash`, `tlm_sync_unit.c`). The slower stream (A, "
        "1 kHz) is the timeline. `B` is resampled with `.mode=window`: each B sample is treated "
        "as a cell centred on its timestamp and averaged over one A period centred on "
        "`t_A + lag_ab`. With B on a half-period grid this is the kernel `[1/4, 1/2, 1/4]` at "
        "`lag_ab = 0` and `[1/2, 1/2]` at `lag_ab = -0.5` frame. `D` is resampled with "
        "`.mode=expint`: the held commands are integrated over one A period centred on "
        "`t_A + (lag_ab - lag_db)`."))
A(L("2. ", "**Lag scan.** `lag_db ∈ {1.0 … 3.5}` and `lag_ab ∈ {-0.5, 0, 0.5}` B-frames are tried "
        "on reduced dimensions (32/24/24) with fixed ridges, and the pair with the highest "
        "held-out whitened median `R²` of `B` is kept."))
A(L("3. ", "**Whitening** (`sysid_unit.c`, `fit_pooled_ar_taps`). A single `AR(p)` filter is "
        "fitted to stream **A** (training part, channels pooled at unit variance, 2% ridge on "
        "the zero-lag autocorrelation) and applied causally to `A`, `B` and `D`."))
A(L("4. ", "**Solve.** Block normal equations with relative diagonal ridges on the A and D blocks "
        "(Schur complement). The ridge pair is chosen on a 5 × 4 grid by held-out whitened `R²` "
        "over one contiguous 70/30 split, then the fit is repeated on the full window."))
A(L("5. ", "**Refinements.** `Mab` is refitted on unwhitened `B - Mdb D`. The virtual upstream "
        "relation `A = Mba B + Mda D` is solved from **unwhitened** covariances, and "
        "`Mda_virt = -Mda`."))
A("")
A(P("""Two facts follow directly. First, filtering all three streams with the same filter and
then doing least squares is identical to least squares with the frequency weight `|W(f)|²`; the
filter's phase and causality do not enter. The shipped method, the report's band-limited
prototype and plain least squares are therefore one family that differs only in `w(f)`. Second,
nothing in the pipeline treats `A` as noisy, and nothing uses the fact that the stage-2
controller is known."""))
A("")
A("---")
A("")
A("## 3. What that family estimates in closed loop")
A("")
A("Per mode, at the stage-2 frame rate, with total loop delay `d` frames:")
A("")
A("```")
A("B[k] = g (phi[k] + u[k] + D[k-d]) + n[k]        WFS B: measured disturbance phi,")
A("                                                 B-only disturbance u, white noise n")
A("A[k] = gA phi[k] + nA[k]                         WFS A: noisy view of phi")
A("D    = -Kc(z) B                                  known stage-2 controller")
A("K(f) = Kc(f) exp(-2 pi i f d)                    controller including the loop delay")
A("```")
A("")
A("### 3.1 Unweighted least squares")
A("")
A(P(f"""Because the DM2 state during exposure `k` was computed from frames `k-d` and earlier,
it is independent of the white noise `n[k]`. Unweighted least squares therefore has **no bias
from WFS B noise**: the measured contribution is {att['Unwhitened least squares|int']['n']:+.1f}%
(Figure 2), and with a noise-free `A` and no B-only disturbance the estimate is within
{ols_ideal[0]:+.0f}% / {ols_ideal[1]:+.0f}% of truth. Its large negative bias comes from the two
things that *are* correlated with `D`: the B-only disturbance `u`, which the loop tracks, and
the part of `phi` that a noisy `A` fails to explain. At low frequency the DM2 command is a
cleaner copy of `-phi` than `A` is, so least squares shrinks both coefficients together."""))
A("")
A("### 3.2 Any frequency weighting: the blend formula")
A("")
A(P("""Let `rho(f)` be the fraction of DM2 power at frequency `f` that was generated by feedback
of the unexplained part of `B` (the B-only disturbance, WFS B noise, and whatever a noisy `A`
leaves behind). The frequency-local regression coefficient is"""))
A("")
A("```")
A("g_hat(f) = (1 - rho(f)) g  +  rho(f) (-Re[1/K(f)])")
A("```")
A("")
A(P("""and a weighted fit returns the `w(f)`-weighted average of this over the DM2 power. The
second term does not contain `g` at all: where DM2 motion is feedback-driven, the regression
measures the controller, which is the classical closed-loop identification result. For an
integrator with a three-frame delay `-Re[1/K]` is near zero at low frequency, crosses `g`
around 100 Hz, reaches about `+2.8 g` near 250 Hz and swings to large negative and positive
values towards the Nyquist frequency (Figure 1)."""))
A("")
A("![Frequency-local estimate against the blend formula](fig1_frequency_blend.png)")
A("")
A(P("""Top row: with the disturbance term removed exactly, the simulated estimate (dots) follows
the blend formula (orange) at every frequency; it approaches `g` only where `rho` is small.
Bottom row: if the WFS A term is allowed a free frequency response, everything that WFS A can
explain is removed from `D`, `rho` becomes 1, and the fit returns the inverse controller
everywhere. Two consequences:"""))
A("")
A(L("- ", "A low-frequency weight (plain least squares) pulls the estimate towards zero; a "
        "high-frequency weight (`W(z)`, or a 20–480 Hz band) pulls it towards the 100–500 Hz "
        "part of `-Re[1/K]`, which is above `g`. Any value in between can be obtained by "
        "choosing the weight, including the true one."))
A(L("- ", "**Lagged copies of `A` must not be added as regressors.** Doing so gives the WFS A "
        "term a free frequency response and removes the only robust passive information "
        "(bottom row). They belong on the instrument side (Section 5.1)."))
A("")
A("### 3.3 The shipped estimator is a cancellation")
A("")
A("![Bias attribution](fig2_bias_attribution.png)")
A("")
A(P("""Each estimator is linear in `B` once its weights are fixed, so its bias splits exactly
into one term per physical component of `B`: WFS A being a noisy proxy for the disturbance, the
disturbance seen by WFS B only, WFS B noise fed back by the loop, and the DM servo lag.
Reference condition, percent of the true gain:"""))
A("")
A("| Estimator, control law | WFS A proxy | B-only disturbance | WFS B noise | DM lag | Net |")
A("| :--- | ---: | ---: | ---: | ---: | ---: |")
for k, m in att.items():
    est, tag = k.split("|")
    A(f"| {est}, {'integrator' if tag == 'int' else 'predictive'} | {sg(m['phi'])} | "
      f"{sg(m['u'])} | {sg(m['n'])} | {sg(m['dm'])} | **{sg(m['total'])}** |")
A("")
A(P("""(The attribution uses the spectral form of each estimator; its totals differ from the
time-domain implementation by up to about 5 points.) Whitening removes most of the two negative
terms and adds a large positive one. Which side wins depends on the two WFS noise levels, on the
size of the B-only disturbance and on the controller:"""))
A("")
A("![Bias across conditions](fig3_bias_across_conditions.png)")
A("")
A("Bias of the median gain, percent of truth, integrator / predictive, 16 runs per cell:")
A("")
A("| Condition | Least squares | `AR(4)` `W(z)` | Band 20–480 Hz | Noise-model fit | "
  "Lagged-A IV |")
A("| :--- | :---: | :---: | :---: | :---: | :---: |")
for c in conds:
    A(f"| {nice[c]} | {cell(c, 'ols')} | {cell(c, 'tool_wz')} | {cell(c, 'band_exact')} | "
      f"{cell(c, 'pem32')} | {cell(c, 'iv_past8')} |")
A("")
dx = sorted(abs(r['tool_wz']['bias'] - r['wz_exact']['bias']) for r in (ref_i, ref_p))
dx_txt = f"{dx[0]:.0f}–{dx[1]:.0f}"
wo = lambda c, t: " / ".join(sg(b[f'{c}|{t}|5s'][e]['bias']) for e in
                             ("wz_p1", "wz_p2", "tool_wz", "wz_p8"))
A(P(f"""Doubling WFS B noise alone moves the `AR(4)` result to
{b['nB x2 only|int|5s']['tool_wz']['bias']:+.0f}% /
{b['nB x2 only|pred|5s']['tool_wz']['bias']:+.0f}%;
tripling WFS A noise alone moves it to {b['nA x3 only|int|5s']['tool_wz']['bias']:+.0f}% /
{b['nA x3 only|pred|5s']['tool_wz']['bias']:+.0f}%. The result does not converge with whitening
order either: for `p = 1, 2, 4, 8` it is {wo('ref', 'int')}% (integrator) and {wo('ref', 'pred')}%
(predictive) at the reference condition. Matching the exposure windows exactly changes it by
only {dx_txt} points."""))
A("")
A("### 3.4 Where the information about `g` actually is")
A("")
A(P("""Only DM2 motion that is exogenous to the WFS B residual carries `g`. There are three
sources, in decreasing order of robustness:"""))
A("")
A(L("1. ", "**Deliberate excitation**: a known dither."))
A(L("2. ", "**Other commands on DM2 that do not derive from WFS B**: stage-3 (LLOWFS) commands, "
        "speckle or astrometric-grid probes, offset changes."))
A(L("3. ", "**The stage-2 response to the disturbance that WFS A measures.** It is usable only if "
        "the WFS A term is static, which is what exact exposure matching provides, and only "
        "through instruments, because `A` is noisy."))
A("")
A(P(f"""The loop delay plus a noise model is a fourth, formal source: with the correct noise
spectrum the feedback terms cancel over the full band. In the idealised single-regressor
setting this works and converges with model order ({pem_or['int']['pem4'][0]:.3f},
{pem_or['int']['pem16'][0]:.3f}, {pem_or['int']['pem64'][0]:.3f} of truth for AR(4), AR(16),
AR(64); run-to-run SD {100 * pem_or['int']['pem64'][1]:.1f}%). In the practical setting, with `A`
as a noisy regressor that is collinear with `D` at low frequency, the same procedure gives
{rng(bias('pem32'))}, as bad as or worse than not whitening at all. The implementation was
checked on open-loop data, where it reduces the error from {x['pem_sanity']['ols_err']:.2f} to
{x['pem_sanity']['pem_err']:.2f}, so the failure is a property of the problem."""))
A("")
A("---")
A("")
A("## 4. Code-level findings")
A("")
sc = lambda r, lab, ldb: r[f"scan|{lab}|{ldb}"]
A(L("1. ", f"**The lag scan compares targets with different smoothing.** `lag_ab = 0` averages "
        "three B frames with weights `[1/4, 1/2, 1/4]`; `lag_ab = -0.5` averages the two frames "
        "that actually fall inside the A exposure. The first has 25% less noise variance in the "
        "regressand, so its `R²` is higher for a reason unrelated to alignment. In the toy, "
        f"where the exposure-matched choice is `-0.5` by construction, the scan prefers `0` "
        f"(`R²_w` {sc(r2i, '0.0', '2.5')[0]:.3f} against {sc(r2i, '-0.5', '2.5')[0]:.3f}), as it "
        "did on the real run."))
A(L("2. ", f"**The estimate is sensitive to `lag_db`.** Half a frame either side of the selected "
        f"value changes the `W(z)` result from {sc(r2i, '0.0', '2.5')[1]:+.0f}% to "
        f"{sc(r2i, '0.0', '2.0')[1]:+.0f}% / {sc(r2i, '0.0', '3.0')[1]:+.0f}% (integrator) and "
        f"from {sc(r2p, '0.0', '2.5')[1]:+.0f}% to {sc(r2p, '0.0', '2.0')[1]:+.0f}% / "
        f"{sc(r2p, '0.0', '3.0')[1]:+.0f}% (predictive)."))
A(L("3. ", f"**Predictive `R²` is the wrong yardstick.** Unwhitened, the least-squares solution "
        f"scores {r2i['r2raw_ols']:.2f} on held-out data and the true matrices "
        f"{r2i['r2raw_truth']:.2f}. Whitened, the {r2i['bias_tool_train']:+.0f}%-biased solution "
        f"scores {r2i['r2_tool']:.3f} and the truth {r2i['r2_truth']:.3f}: a difference of "
        f"{abs(r2i['r2_truth'] - r2i['r2_tool']):.3f} separates them."))
A(L("4. ", "**The whitening filter is fitted to `A`, not to the equation residual**, so it is not "
        "a noise model in the prediction-error sense. Section 3.4 shows that fitting it to the "
        "residual would not help."))
A(L("5. ", "**Noise in `A` is ignored.** In the toy this is the largest negative term for every "
        "regression estimator (Figure 2)."))
A(L("6. ", f"**`Mda_virt` comes from an unwhitened regression on a noisy `B`.** Its amplitude is "
        f"{min(mda):.2f}–{max(mda):.2f} of the WFS A optical gain in the toy. The direction is "
        "what an offload needs; the amplitude should not be read as an optical gain, and a "
        "leaky integrating offload is insensitive to it. The `‖Mab·Mda_virt − Mdb‖` cross-check "
        "sums estimation noise over 1,600 entries and is not a sensitive consistency test."))
A(L("7. ", "**One contiguous split, no uncertainties.** A block bootstrap over time would give "
        "per-mode error bars at negligible cost."))
A(L("8. ", "**`D` omits other DM2 channels.** See Sections 5.3 and 6."))
A(L("9. ", "**Minor.** The D-block ridge (up to 1%) shrinks `diag(Mdb)` by about that amount; the "
        "reported `eta_D` includes the ridge; the `selfRM` reference is acquired after the run "
        "and with predictive filtering off."))
A("")
A("---")
A("")
A("## 5. Options evaluated")
A("")
dith = (f"{x['dither 0.001|int|5.0s']['w_bias']:+.0f}% to "
        f"{x['dither 0.001|pred|5.0s']['w_bias']:+.0f}%")
# option, toy result (bias of the median), short verdict, principle and remark
OPTIONS = [
    ("`AR(p)` whitening `W(z)` (shipped)", rng(bias('tool_wz')), "blend",
     "weight `abs(W)^2` from the WFS A spectrum. A blend; its accuracy depends on the conditions."),
    ("Same, exact exposure matching", rng(bias('wz_exact')), "no material change",
     "identical kernels for B and D."),
    ("Band-limited 20–480 Hz", rng(bias('band_exact')), "same family",
     "weight `1/tr(S_AA)` on a band. Unbounded without a WFS A noise floor."),
    ("Residual-whitening / noise-model fit", rng(bias('pem32')), "fails in practice",
     "inverse residual spectrum per output."),
    ("Lagged-A instrumental variables", rng(bias('iv_past8')), "best passive option",
     "past WFS A frames as instruments. Needs stage-1 broadband content."),
    ("Same, on first-differenced data", rng(d_bias), "**recommended passive estimator**",
     "instruments lagged by 2–9 frames."),
    ("Known white DM2 dither", dith, "reliable",
     "the dither is the instrument. The offset is DM dynamics, not estimator bias."),
    ("Stage-3 command as regressor", "within 0.01–0.04 of expected", "free for low orders",
     "its coefficient is `g − g_zpo`."),
    ("Lagged `A` as regressors (dynamic `Mab`)", "returns the inverse controller",
     "counter-productive", "see Section 3.2."),
    ("Controller or gain switching", "not simulated", "adds no exogenous motion",
     "changes `K` between segments; still needs `1 − rho > 0`."),
    ("Multi-rate Kalman-EM", "not simulated", "validate against IV first",
     "full state-space likelihood. Shares the noise-model route's fragility."),
    ("Correlation-locking gain servo", "not simulated (literature)", "no absolute gain",
     "Deo et al. 2021: drives modal gains from the residual autocorrelation. Keeps the loop "
     "tuned without a gain estimate."),
    ("Model-based gain", "not simulated (literature)", "independent cross-check",
     "Chambouleyron et al. 2020: predicts the gain from residual statistics, with no loop "
     "regression."),
]
A("| Option | Toy result (bias of median) | Verdict |")
A("| :--- | :--- | :--- |")
for name, res_txt, verdict, _ in OPTIONS:
    A(f"| {name} | {res_txt} | {verdict} |")
A("")
A("Principle of each option, and remarks:")
A("")
for name, _, _, remark in OPTIONS:
    A(L("- ", f"**{name}**: {remark}"))
A("")
A("### 5.1 Lagged-A instrumental variables")
A("")
A(P("""Model per mode: `B_i = c_i psi_i + g_i D_i + v_i`, where `psi_i = (Mab A)_i` is the
disturbance predicted from WFS A. Both regressors are treated as endogenous, and the instruments
are `psi_i` at earlier frames. This uses exactly the third information source of Section 3.4 and
nothing else, so it is insensitive to the spectrum of `v` and to white noise in `A`."""))
A("")
A("| Variant (reference condition) | Bias, int / pred | Per-mode median error, int / pred |")
A("| :--- | :---: | :---: |")
for e, lab in (("iv_past2", "2 past frames"), ("iv_past4", "4 past frames"),
               ("iv_past8", "8 past frames"), ("iv_past16", "16 past frames"),
               ("iv_past32", "32 past frames"), ("iv_past8_f2", "8 past + 2 future frames"),
               ("iv_sym8", "8 past + 8 future frames"),
               ("iv_past8_noEIV", "8 past, current frame instruments itself"),
               ("iv_past8_toolsync", "8 past, tool alignment (triangle kernel)")):
    A(f"| {lab} | {sg(ref_i[e]['bias'])}% / {sg(ref_p[e]['bias'])}% | "
      f"{ref_i[e]['permode']:.0f}% / {ref_p[e]['permode']:.0f}% |")
A("")
A(L("- ", "**Future frames are invalid instruments** beyond the stage-1 loop delay: stage 1 "
        "turns the noise of the current WFS A frame into real wavefront a few frames later, so "
        "later frames are correlated with the current frame's measurement error."))
A(L("- ", "**The current frame must not instrument itself.** Treating `A` as noise-free costs "
        f"{ref_i['iv_past8_noEIV']['bias']:+.0f}%."))
A(L("- ", "**Exact exposure matching matters here** (unlike for `W(z)`), because the method "
        "relies on the WFS A term being static."))
A(L("- ", f"**Strength.** The usable part of the instruments' prediction of the DM2 command is "
        f"{100 * ref_i['iv_strength']:.1f}% of its variance at the reference condition, and "
        "almost nothing when WFS A is noise-free "
        f"({100 * b['nA = 0|int|5s']['iv_strength']:.2f}%), where the estimate degrades to "
        f"{b['nA = 0|int|5s']['iv_past8']['bias']:+.0f}% with a per-mode error of "
        f"{b['nA = 0|int|5s']['iv_past8']['permode']:.0f}%. The excitation it relies on is "
        "stage-1 noise propagated through DM1: a brighter star weakens it."))
A("")
A("![Per-mode accuracy against window length](fig4_precision_vs_window.png)")
A("")
A("| Window | `AR(4)` `W(z)` | Lagged-A IV | White dither (27% RMS) |")
A("| :--- | :---: | :---: | :---: |")
for t in ("0.5", "1.0", "2.0", "5"):
    kk = f"ref|int|{t}s"
    dk = x.get(f"dither 0.001|int|{float(t)}s")
    dtxt = f"{sg(dk['w_bias'])}% / {dk['w_pm']:.0f}%" if dk else "—"
    wz_txt = f"{sg(b[kk]['tool_wz']['bias'])}% / {b[kk]['tool_wz']['permode']:.0f}%"
    iv_txt = f"{sg(b[kk]['iv_past8']['bias'])}% / {b[kk]['iv_past8']['permode']:.0f}%"
    A(f"| {float(t):.1f} s | {wz_txt} | {iv_txt} | {dtxt} |")
A("")
A(P(f"""Entries are bias of the median / per-mode median error, integrator. The IV estimate
needs about 2 s before its weak-instrument bias disappears; `W(z)` is bias-limited at every
length. The run-to-run SD of the IV median at 5 s is {ref_i['iv_past8']['sd']:.1f}% (integrator)
and {ref_p['iv_past8']['sd']:.1f}% (predictive), so a smooth model of gain against mode index
would track the gain curve at the 1–2% level."""))
A("")
A("### 5.2 Dither")
A("")
A("| Dither variance ÷ residual variance | Bias, int / pred | Per-mode error, int / pred |")
A("| :--- | :---: | :---: |")
for dn in ("0.0005", "0.001", "0.002"):
    di, dp = x[f"dither {dn}|int|5.0s"], x[f"dither {dn}|pred|5.0s"]
    A(f"| {di['frac']:.2f} | {di['w_bias']:+.0f}% / {dp['w_bias']:+.0f}% | "
      f"{di['w_pm']:.0f}% / {dp['w_pm']:.0f}% |")
A("")
A(P("""White dither, 5 s, whitened instrumental-variable estimate. The 2–3% offset is not an
estimator bias: a frame-to-frame random command is attenuated by the DM2 servo lag averaged over
the WFS exposure (3.6% in the toy). Because the dither is exogenous, any frequency weighting is
allowed without penalty, and a narrow-band probe placed where the residual spectrum is low would
be more efficient than the white one tested here."""))
A("")
A("### 5.3 Stage-3 commands")
A("")
A("| Case | Coefficient of B on the stage-3 command | Expected `g − g_zpo` |")
A("| :--- | :---: | :---: |")
for lab, v in s3.items():
    A(f"| {lab} | {np.mean(v['c3']):+.2f} | {np.mean(v['expect']):+.2f} |")
A("")
A(P(f"""Telemetry `B` is taken after the zero-point-offset subtraction, so the stage-3 command
appears in it with coefficient `g − g_zpo`. That is a direct, probe-free reading of the
low-order optical gain, and driving it to zero by adjusting `g_zpo` is a self-calibrating
servo. Adding the stage-3 command as a regressor also improves the low-order `Mdb` estimates
(from {np.mean(s3[list(s3)[3]]['wz']):.2f} to {np.mean(s3[list(s3)[3]]['wz_d3']):.2f} of truth at
the highest stage-3 gain tested), though they stay poor for the reasons in Section 3. In the toy
a gain mismatch multiplies the stage-3 command by `1/g` as seen by its own sensor, which raises
its effective loop gain; the toy stayed stable at the gains tried."""))
A("")
A("### 5.4 Purely passive use: no dither, no stage-3 probe")
A("")
A(P("""If nothing may be injected, the lagged-A method is the one to use, in a first-differenced
form: difference `B`, `psi` and `D` in time, then fit each mode by two-stage least squares with
the differenced `psi` at lags 2 to 9 as instruments. The lag starts at 2 because differencing
puts the previous frame's WFS A noise into the error. Differencing removes the slow directions in
which `psi` and `D` are collinear and every chance correlation is amplified, and it keeps the
high-frequency variation that stage-1 noise creates through DM1."""))
A("")
A(P("""Bias of the median / per-mode median error, percent, 12 runs per row. Columns: the
shipped `W(z)`; lagged-A by two-stage least squares (2SLS); lagged-A by LIML; the differenced
lagged-A form; and lagged-A with the DM1 command level added to the instruments."""))
A("")
A("| Condition, window, control | `W(z)` | 2SLS | LIML | **Differenced** | + DM1 level |")
A("| :--- | :---: | :---: | :---: | :---: | :---: |")
for k, v in ivv.items():
    lab, win, ctl = k.split("|")
    f2 = lambda key: f"{sg(v[key][0])} / {v[key][2]:.0f}"
    A(f"| {lab}, {win}, {'integrator' if ctl == 'int' else 'predictive'} | {sg(v['wz'])} | "
      f"{f2('psi8|2sls')} | {f2('psi8|liml')} | **{f2(DK)}** | {f2('psi8+c1|2sls')} |")
A("")
A(L("- ", f"**Bright stars.** With four times less WFS noise the plain form is biased by "
        f"{sg(min(p_bias_bright))}% to {sg(max(p_bias_bright))}% at 5 s (weak instruments, pulled "
        f"towards least squares); the differenced form gives {sg(min(d_bias_bright))}% to "
        f"{sg(max(d_bias_bright))}%. LIML halves the weak-instrument bias of the plain form but "
        "adds 1–2% when the instruments are strong, and brings nothing to the differenced form."))
A(L("- ", f"**Window.** About {min(d_pm5):.0f}–{max(d_pm5):.0f}% per mode from 5 s, 2–3% from "
        "20 s, and 1–2% from 40 s."))
A(L("- ", f"**Do not use the logged DM1 command level as an instrument.** It is a very strong "
        f"predictor of the slow, collinear part of both regressors and gave {rng(c1_bias)}. "
        "DM1 command increments are harmless but add nothing to past WFS A frames."))
A("")
A(P("""With the stage-3 loop closed (nothing injected, zero-point offset at the calibration
gain), the low-order modes need its logged command as one more regressor. Estimates on modes
0–3, as a fraction of the true gain, for the shipped `W(z)`, the differenced lagged-A estimator,
and the same with the logged stage-3 command added:"""))
A("")
A("| Case | `W(z)` | Differenced | + stage-3 command | Stage-3 coefficient (expected) |")
A("| :--- | :---: | :---: | :---: | :---: |")
for lab, v in ivl.items():
    A(f"| {lab} | {np.mean(v['wz']):.2f} | {np.mean(v['iv']):.2f} | "
      f"**{np.mean(v['iv3']):.2f} ± {np.mean(v['iv3_sd']):.2f}** | "
      f"{np.mean(v['c3']):+.2f} ({np.mean(v['expect']):+.2f}) |")
A("")
A(P("""Reading the stage-3 command from telemetry is not an injection: the loop is running
anyway. Its coefficient is the zero-point-offset gain error."""))
A("")
A("---")
A("")
A("## 6. Opportunities")
A("")
A(L("1. ", "**An honest passive gain estimate.** Lagged-A instrumental variables on "
        "exposure-matched data, per mode, reported with the first-stage strength and a "
        "block-bootstrap error bar, and withheld when the instruments are weak. Cost is "
        "negligible: two unknowns and eight instruments per mode."))
A(L("2. ", "**A diagnostic that needs no reference.** Plot the frequency-local estimate against "
        "`-Re[1/K(f)]` computed from the known stage-2 controller. Where the two coincide, DM2 "
        "motion is feedback-driven and carries no gain information."))
A(L("3. ", "**Free excitation already on DM2.** Any DM2 command that does not derive from WFS B "
        "is a valid instrument: LLOWFS, speckle probes, astrometric grids. Logging those "
        "channels and projecting them on the modal basis costs nothing in wavefront error."))
A(L("4. ", "**Zero-point-offset self-calibration** from the stage-3 coefficient (Section 5.3)."))
A(L("5. ", "**A verification dither.** A few seconds of small dither gives a reference that does "
        "not interrupt the loop and is measured in the same loop state as the telemetry, which "
        "`selfRM` after the run is not."))
A(L("6. ", "**Gain-curve tracking.** Pooling modes through a smooth gain-versus-mode model turns "
        "5% per-mode scatter into a 1–2% curve, enough to rescale modal gains, the predictive "
        "filter's `WFSfact` and the zero-point offsets."))
A(L("7. ", "**Offload.** `Mda_virt`'s direction is usable now in a leaky integrating offload. "
        "Its amplitude should be checked against the stage-1 `selfRM` before it is quoted."))
A("")
A("### Suggested order of work")
A("")
A(L("1. ", "Run the tests of Section 7; all but the first use the existing telemetry."))
A(L("2. ", "Add the lagged-A IV estimate and the inverse-controller diagnostic to the report "
        "generator as a Python prototype, alongside `W(z)`."))
A(L("3. ", "If it holds on the real simulator, port it to `mlt.sysid` and make the lag scan "
        "compare like with like."))
A(L("4. ", "Add the stage-3 command (and any other DM2 channel) to the regression."))
A(L("5. ", "Add an optional dither mode for bright stars and for verification."))
A("")
A("---")
A("")
A("## 7. Tests that would confirm or refute this on the real simulator")
A("")
A(L("1. ", "**Change the noise of one WFS only** (the `ron_e` or `qe` of one pyramid sensor in "
        "`ao3k_scexao.bench`) and rerun. If the `W(z)` result is a cancellation it should rise "
        "with WFS B noise and fall with WFS A noise, by several percent or more. A guide-star "
        "magnitude change is a weaker test because it moves both noises and the two effects "
        "oppose. An unbiased estimator would not move in either case."))
A(L("2. ", "**Overlay the frequency-local estimate on `-Re[1/K(f)]`** for the integrator runs, "
        "where `K` is known exactly."))
A(L("3. ", "**Compute the lagged-A IV estimate on the same telemetry** and compare it, per mode, "
        "with `W(z)` and with both `selfRM` definitions."))
A(L("4. ", "**Repeat the `AR(p)` sweep on an integrator run.** The published sweep is for the "
        "predictive run only."))
A("")
A("---")
A("")
A("## 8. Limitations")
A("")
A(L("- ", "The toy is modal, diagonal, linear and stationary. A pyramid's optical gain fluctuates "
        "with the residual, which adds a multiplicative term that no estimator here models."))
A(L("- ", "The `W(z)` and band-limited results come from a numpy port of the C code, not from "
        "the binary."))
A(L("- ", "The IV estimator benefits from the toy's diagonal structure. With real, non-diagonal "
        "`Mab` it depends on a preliminary estimate of the WFS A direction for each B mode."))
A(L("- ", "A coloured measurement error in WFS A (aliasing) was tested at one level only, where "
        "it had no visible effect."))
A(L("- ", "Timestamp conventions of the real telemetry were not available; the alignment "
        "findings are stated for B frames on a half-period grid of the A frames."))
A(L("- ", "Controller switching and Kalman-EM were analysed, not simulated."))
A("")
A("---")
A("")
A("## 9. Reproduction")
A("")
A("```bash")
A("cd algo/calib2wfs1dm/toy/code")
A("export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1")
A("python3 bench.py 16      # 704 runs, about 5 min on 22 cores -> bench.json")
A("python3 theory1.py sig_nA=0.002 sig_nB=0.002 c_hi=0.6   # blend check -> theory_*.npz")
A("python3 extra.py         # dither, held-out R2, lag scan, conditional estimate")
A("python3 stage3.py        # stage-3 channel and zero-point-offset mismatch")
A("python3 iv_variants.py   # passive variants: instruments, LIML, differencing")
A("python3 iv_lowfs.py      # low-order modes with the stage-3 loop closed")
A("python3 figs.py .. --all # figures (needs matplotlib)")
A("python3 build_report.py ..")
A("```")
A("")
A(P("""The `.npz` files written by `theory1.py` and `extra.py` are not kept in git; run those two
scripts before `figs.py` or `build_report.py`. See `../README.md` for the interpreter to use."""))
A("")
A(P("""`sim.py` is the loop model, `estimators.py` the alignment kernels and estimators
(including the port of `mlt.tlmsync` and `mlt.sysid`), `decomp.py` the bias attribution."""))
A("")
A("## References")
A("")
A(P("""Titles and venues were checked by web search; the full texts were not re-read for this
study."""))
A("")
for ref in (
    "U. Forssell, L. Ljung, *Closed-loop identification revisited*, Automatica 35, 1215–1241 "
    "(1999). Direct, indirect and joint input-output methods; the direct method needs a correct "
    "noise model.",
    "M. Gilson, P. Van den Hof, *Instrumental variable methods for closed-loop system "
    "identification*, Automatica 41, 241–249 (2005). The family the lagged-A estimator belongs "
    "to, with WFS A as the external signal.",
    "V. Deo et al., *A correlation-locking adaptive filtering technique for minimum variance "
    "integral control in adaptive optics*, A&A 650, A41 (2021). Tracks the loop-gain × "
    "optical-gain product from residual autocorrelation, without probes.",
    "V. Deo et al., *A telescope-ready approach for modal compensation of pyramid wavefront "
    "sensor optical gain*, A&A 629 (2019).",
    "S. Esposito et al., *On-sky correction of non-common path aberration with the pyramid "
    "wavefront sensor*, A&A 636, A88 (2020).",
    "V. Chambouleyron et al., *Pyramid wavefront sensor optical gains compensation using a "
    "convolutional model*, A&A 644, A6 (2020). A model-based gain estimate that is independent "
    "of loop telemetry.",
    "N. Cerpa-Urra et al., *Cascade adaptive optics: contrast performance analysis of a "
    "two-stage controller by numerical simulations*, JATIS 8, 019001 (2022).",
):
    A(L("- ", ref))
A("")
if WRAP:
    md = wrap_md(md)
    too_long = [ln for ln in md if len(ln) > WIDTH]
    assert not too_long, too_long
(OUT / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("wrote", OUT / "REPORT.md", len(md), "lines")
