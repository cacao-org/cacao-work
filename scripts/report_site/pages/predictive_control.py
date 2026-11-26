#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Practical CACAO Predictive Control Guide (/predictive-control/index.html).

Human-readable explanation of AR(P), Cross-Mode Block-EOF (and extensions), and
Cascaded Online Self-Learning (Global RLS + Clustered libgric), structured as a
practical commissioning, setup, parameter-tuning, and troubleshooting manual.
"""

from __future__ import annotations

import html

from ..extractors.options_catalog import (
    make_cli_opt_anchor,
    make_fps_opt_anchor,
    make_runner_opt_anchor,
)
from ..markdown.sim_split import extract_toc_items
from .fragments import kpi_card, render_section_badges
from .shell import render_page_shell


def _collect_ref_anchors(
    options_catalog: dict[str, object] | None,
) -> tuple[set[str], dict[str, dict[str, object]]]:
    valid: set[str] = set()
    by_anc: dict[str, dict[str, object]] = {}
    if not isinstance(options_catalog, dict):
        return valid, by_anc
    for gkey in ("runner_cli", "env_vars", "cacaosim_cli"):
        for item in options_catalog.get(gkey) or []:
            if isinstance(item, dict) and item.get("anchor"):
                anc = str(item["anchor"])
                valid.add(anc)
                by_anc[anc] = item
    for u in options_catalog.get("fps_units") or []:
        if not isinstance(u, dict):
            continue
        for p in u.get("params") or []:
            if isinstance(p, dict) and p.get("anchor"):
                anc = str(p["anchor"])
                valid.add(anc)
                by_anc[anc] = p
    return valid, by_anc


class _GuideLinker:
    """Resolve safe relative links to Options Reference, Algorithms, and staged reports."""

    def __init__(
        self,
        hierarchy: dict[str, object],
        options_catalog: dict[str, object] | None,
    ) -> None:
        self.valid_anc, self.by_anc = _collect_ref_anchors(options_catalog)
        staged_metas = list(hierarchy.get("all_metas") or [])
        self.staged_slugs: set[str] = {
            str(m["slug"])
            for m in staged_metas
            if isinstance(m, dict) and m.get("slug")
        }

    def fps(self, unit: str, kw: str, label: str | None = None) -> str:
        text = html.escape(label or f"{unit}{kw}", quote=False)
        anc = make_fps_opt_anchor("cacao", unit, kw)
        if anc in self.valid_anc:
            return (
                f'<a class="opt-ref-link" href="../reference/index.html#{anc}">'
                f"<code>{text}</code></a>"
            )
        return f"<code>{text}</code>"

    def fps_default(self, unit: str, kw: str, fallback: str) -> str:
        anc = make_fps_opt_anchor("cacao", unit, kw)
        meta = self.by_anc.get(anc)
        if isinstance(meta, dict) and meta.get("default") not in (None, ""):
            return str(meta["default"])
        return fallback

    def flag(self, flag: str) -> str:
        text = html.escape(flag, quote=False)
        anc = make_runner_opt_anchor(flag)
        if anc in self.valid_anc:
            return (
                f'<a class="opt-ref-link" href="../reference/index.html#{anc}">'
                f"<code>{text}</code></a>"
            )
        return f"<code>{text}</code>"

    def env(self, var: str) -> str:
        text = html.escape(var, quote=False)
        anc = make_cli_opt_anchor("cacaoloop-env", var)
        if anc in self.valid_anc:
            return (
                f'<a class="opt-ref-link" href="../reference/index.html#{anc}">'
                f"<code>{text}</code></a>"
            )
        return f"<code>{text}</code>"

    def algo(self, slug: str, code: str, role: str = "loop_operation") -> str:
        return (
            f'<a class="algo-inline-code cat-{html.escape(role, quote=True)}" '
            f'href="../algorithms/{html.escape(slug, quote=True)}/index.html">'
            f"{html.escape(code, quote=False)}</a>"
        )

    def report(self, slug: str, label: str) -> str:
        esc = html.escape(label, quote=False)
        if slug in self.staged_slugs:
            return f'<a href="../{html.escape(slug, quote=True)}/index.html"><strong>{esc}</strong></a>'
        return f"<strong>{esc}</strong>"


def _render_param_rows(
    lk: _GuideLinker,
    unit: str,
    specs: list[tuple[str, str, str, str, str]],
) -> str:
    """Render FPS parameter tuning rows: (kw, fallback_def, access, role_summary, tuning_guide)."""
    rows: list[str] = []
    for kw, fb_def, access, what_it_does, tuning in specs:
        dflt = lk.fps_default(unit, kw, fb_def)
        acc_cls = (
            "opt-badge-live"
            if access == "LIVE"
            else ("opt-badge-out" if access == "OUTPUT" else "opt-badge-init")
        )
        rows.append(
            "<tr>"
            f"<td>{lk.fps(unit, kw, kw)}</td>"
            f"<td><code>{html.escape(dflt, quote=False)}</code></td>"
            f'<td><span class="opt-badge {acc_cls}">{html.escape(access, quote=False)}</span></td>'
            f'<td class="wrap-cell">{what_it_does}</td>'
            f'<td class="wrap-cell">{tuning}</td>'
            "</tr>"
        )
    return "".join(rows)


def _render_hero_and_toc(lk: _GuideLinker) -> str:
    return (
        '<section class="hero-banner">\n'
        '<div class="badge-row">'
        '<span class="domain-badge domain-wavefront-control">Wavefront Control &amp; Prediction</span>'
        '<span class="metric-pill metric-pill-accent">Practical Guide &amp; Tuning Manual</span>'
        '<span class="metric-pill">AR(P) &middot; Block-EOF &middot; Self-Learning</span>'
        "</div>\n"
        "<h1>CACAO Predictive Control Guide: AR, Block-EOF &amp; Cascaded Self-Learning</h1>\n"
        "<p>A human-readable guide to the physics, algorithms, real-time architecture, and "
        "practical parameter tuning of CACAO's three predictive control layers&mdash;from fast "
        "per-mode diagonal <strong>AR(P)</strong>, to spatial-temporal cross-mode "
        "<strong>Block-EOF</strong> (with ZOH ridge, difference-space DC pinning, wind-layer "
        "physics priors, regime memory, Filtered-X, and multi-rate velocity), to "
        "<strong>Cascaded Online Self-Learning</strong> (Global RLS + Clustered "
        "<code>libgric</code> with causal James-Stein safety gates).</p>\n"
        '<div class="kpi-grid">'
        + kpi_card("Control Ladder", "3 Predictive Tiers", "AR(P) → Block-EOF → Self-Learning")
        + kpi_card("Core Units", "6 Real-Time Daemons", "mfilt, mk/apply AR & EOF, selflearn")
        + kpi_card("RT Inference", "24–114 µs / frame", "Fits cleanly inside 1–2 kHz loops")
        + kpi_card("Safety Guarantee", "1.000x Null Noise", "Causal OOS Stein gates & modalwhite")
        + "</div>\n"
        '<div class="hero-actions">'
        '<a class="btn" href="#setup-workflow">Step-by-Step Setup &rarr;</a>'
        '<a class="btn btn-secondary" href="#tuning-presets">Recommended Presets</a>'
        '<a class="btn btn-secondary" href="#troubleshooting">Troubleshooting Cookbook</a>'
        '<a class="btn btn-secondary" href="../algorithms/index.html">Interactive Options Map</a>'
        '<a class="btn btn-secondary" href="../reference/index.html">Full FPS &amp; CLI Reference</a>'
        "</div>\n"
        "</section>\n"
        '<nav class="toc-bar" aria-label="Quick section jump">'
        '<span class="toc-label">Jump to:</span>'
        '<a class="toc-chip" href="#psol-prerequisite">1. Motivation &amp; PSOL</a>'
        '<a class="toc-chip" href="#controller-ladder">2. Choosing a Tier</a>'
        '<a class="toc-chip" href="#diagonal-ar">3. Diagonal AR(P)</a>'
        '<a class="toc-chip" href="#block-eof">4. Cross-Mode Block-EOF</a>'
        '<a class="toc-chip" href="#self-learning">5. Cascaded Self-Learning</a>'
        '<a class="toc-chip" href="#setup-workflow">6. Setup &amp; Commissioning</a>'
        '<a class="toc-chip" href="#tuning-presets">7. Regime Presets</a>'
        '<a class="toc-chip" href="#troubleshooting">8. Diagnostics &amp; Troubleshooting</a>'
        "</nav>"
    )


def _render_sec1_motivation_and_psol(lk: _GuideLinker) -> str:
    mermaid_graph = (
        '<div class="mermaid-wrap"><pre class="mermaid">\n'
        "flowchart LR\n"
        '    WFS["PyWFS / SHWFS<br/>(dark-sub + norm)"] --> M1["modalfilter (PSOL Observer)<br/>'
        'OL = WFSfact*mWFSfact*WFS - DM_eff"]\n'
        '    M1 -->|"aolN_modevalOL_buff<br/>(256-fr double buffer)"| MK["Async Solver (0.25-1 s)<br/>'
        'mkARPF or mkEOFPF<br/>(+ windlayers / H_eff)"]\n'
        '    MK -->|"arPFmat or eofPFmat<br/>(+ optional eofPFmat_vel)"| APP["Real-Time Predictor<br/>'
        'applyARPF (24 us) or<br/>applyEOFPF (80-108 us)"]\n'
        '    M1 -->|"aolN_modevalOL (live)"| APP\n'
        '    APP -->|"Optional cascade:<br/>aolN_modevalPF_eof"| SL["Cascaded Self-Learning<br/>'
        'cacaopc-selflearn<br/>Global RLS + libgric + Stein gates"]\n'
        '    SL -->|"aolN_modevalPF<br/>+ outPFstat"| BLEND["modalfilter Blender<br/>'
        'cmd = mix*(zpo/g - PF) + (1-mix)*Int"]\n'
        '    APP -.->|"Direct (no selflearn):<br/>aolN_modevalPF"| BLEND\n'
        '    BLEND -->|"aolN_modevalDM<br/>(or traj -> mvalpacer)"| DM["DM (+ Pre-Shaper)"]\n'
        '    M1 -.->|"WFS & DM buffers"| WH["modalwhite<br/>Q_vw, Q_xmode, Alerts"]\n'
        "</pre></div>"
    )
    return (
        '<h2 id="psol-prerequisite">1. Why Predictive Control? Physical Motivation &amp; '
        f'the PSOL Prerequisite {render_section_badges(["loop_operation", "calibration"])}</h2>\n'
        "<p>Every real adaptive optics loop suffers an unavoidable delay <code>&tau;</code> "
        "(typically <strong>2.0&ndash;2.8 WFS frames</strong>, combining WFS integration, camera "
        "readout, MVM compute, and DM settling). A classical leaky integrator "
        f"({lk.algo('int', 'INT')}) only reacts <em>after</em> an error has already passed through "
        "the focal plane. Pushing integrator gain higher cannot eliminate servo lag: once the loop "
        "phase lag approaches 180&deg;, the waterbed effect amplifies high-frequency WFS noise and "
        "drives ringing.</p>\n"
        "<p>In practice, servo lag causes three concrete scientific penalties:</p>\n"
        "<ul>\n"
        "<li><strong>Coronagraphic wind-butterfly halo:</strong> Frozen-flow wind translates "
        "phase ripples across the pupil faster than the integrator updates, piling coherent "
        "speckles along the wind axis at 3&ndash;20 &lambda;/D.</li>\n"
        "<li><strong>V-spider / segmented-pupil petaling slips:</strong> During strong gusts, "
        "if lag exceeds ~&lambda;<sub>WFS</sub>/2 across a spider gap, a Pyramid WFS wraps by "
        "2&pi; and locks an island at &plusmn;1 &lambda;.</li>\n"
        "<li><strong>Faint-star frame-rate ceiling:</strong> Integrators force you to run the WFS "
        "fast enough to keep lag small, starving faint targets (m &ge; 9&ndash;10) of photons per "
        "exposure. Predictive control lets you slow the WFS 2&ndash;4&times; to recover SNR while "
        "still cancelling temporal lag.</li>\n"
        "</ul>\n"
        "<h3>The Pseudo Open-Loop (PSOL) Architecture</h3>\n"
        "<p>Instead of predicting closed-loop WFS residuals directly (which change whenever you "
        "adjust loop gain), CACAO's predictive controllers work in <strong>Pseudo Open-Loop (PSOL) "
        f"coordinates</strong> reconstructed every frame inside {lk.algo('psol', 'PSOL')} "
        "(<code>cacao-fpsexec-mfilt</code>):</p>\n"
        '<div class="pcg-eq-box">'
        '<span class="pcg-eq-lbl">Real-Time PSOL Reconstruction &amp; Blending inside modalfilter.c</span>'
        "1. Open-loop estimate:   modevalOL[m](t) = (comp.WFSfact * mWFSfact[m]) * modevalWFS[m](t) - DM_eff[m](t)\n"
        "2. Predictive target:    modevalPF[m](t) ≈ modevalOL[m](t + PFlatency)   [computed by applyARPF / applyEOFPF / selflearn]\n"
        "3. Effective mix:        mixf[m]         = clamp(PF.mixcoeff * mPFmixfact[m] * outPFstat[m], 0, 1)\n"
        "4. Blended DM command:   dmC[m](t)       = mixf[m] * (WFSfact*mWFSfact[m]*zpo[m] - modevalPF[m](t)) + (1 - mixf[m]) * dmC_integrator[m](t)"
        "</div>\n"
        "<p>Because <code>modevalOL</code> estimates the true incoming atmospheric + vibration "
        "wavefront (independent of controller gain), an online solver can learn temporal and "
        "spatial-temporal dynamics cleanly while the loop stays closed, and <code>modalfilter</code> "
        "smoothly blends the predictive command with the baseline leaky integrator via "
        f"{lk.fps('modalfilter', '.PF.mixcoeff')} and per-mode rolloff "
        f"<code>mPFmixfact = mgainfact<sup>{lk.env('CACAO_PF_MGAIN_EXP')}</sup></code>. "
        "<strong>Sign convention note:</strong> <code>modevalOL</code> and <code>modevalPF</code> "
        "carry the <em>positive</em> turbulence sign in DM units, so <code>modalfilter</code> "
        "subtracts <code>modevalPF</code> from the scaled zero-point offset to cancel the wavefront.</p>\n"
        + mermaid_graph
        + '<div class="pcg-callout-warn">'
        "<p><strong>Rule #1 — Garbage PSOL = Garbage Prediction:</strong> A predictor can only be "
        "as accurate as <code>modevalOL</code>. Before blaming AR, EOF, or Self-Learning, verify "
        "four observer prerequisites:</p>"
        "<ol>"
        f"<li><strong>Accurate latency ({lk.algo('mlat', 'MLAT', 'calibration')} &amp; "
        f"<code>testOL</code>):</strong> Hardware + software lag ({lk.fps('modalfilter', '.comp.latencyhardwfr')}, "
        f"{lk.fps('modalfilter', '.comp.latencysoftwfr')}) must be aligned within &lt; 0.1 frame, "
        "otherwise the DM subtraction leaks DM motion into <code>modevalOL</code> and creates fake "
        "self-oscillation.</li>"
        f"<li><strong>Dynamic DM plant model ({lk.algo('3drm-fact', '3DRM/FACT', 'calibration')}):</strong> "
        "On fast MEMS DMs, 2-tap fractional lag or diagonal FIR (<code>PSOL/DIAG</code>) suffices. "
        "On resonant continuous-facesheet plate DMs (e.g., 64&times;64 ALPAO), enable 3D MIMO FIR "
        f"({lk.fps('modalfilter', '.comp.dynpsol.enable')}, {lk.fps('modalfilter', '.comp.dynpsol.kernel')}) "
        "&mdash; this cuts live PSOL error by <strong>12.2&times;</strong> (34.1% &rarr; 2.8%).</li>"
        f"<li><strong>Optical-gain scaling ({lk.algo('og-poke', 'OG/POKE', 'online_calib')} / "
        f"{lk.algo('2wfs-live', '2WFS/LIVE', 'online_calib')}):</strong> On Pyramid WFSs, on-sky "
        "optical gain <code>g_opt &lt; 1</code> shrinks WFS amplitude. Supply live "
        f"<code>aolN_mWFSfact = 1/g_opt</code> (keeping scalar {lk.fps('modalfilter', '.comp.WFSfact')} "
        "= 1.0) so WFS residuals match DM units.</li>"
        f"<li><strong>WFS dark subtraction ({lk.flag('--wfs-dark-adu')} / {lk.env('CACAO_WFS_DARKSUB')}):</strong> "
        "Mandatory on faint stars so camera bias pedestals do not distort WFS flux normalization "
        "and optical gain.</li>"
        "</ol></div>"
    )


def _render_sec2_ladder(lk: _GuideLinker) -> str:
    return (
        '<h2 id="controller-ladder">2. Choosing Your Controller Tier: AR vs. Block-EOF vs. '
        f'Cascaded Self-Learning {render_section_badges(["loop_operation"])}</h2>\n'
        "<p>CACAO's predictive controllers form a deliberate capability ladder. Each tier adds "
        "specific physical modeling power and comes with its own warmup horizon, sample requirement, "
        "and real-time CPU footprint:</p>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Controller Tier</th>"
        "<th>Physics Captured</th>"
        "<th>Warmup &amp; Sample Rule</th>"
        "<th>RT Apply Cost (1–2 kHz)</th>"
        "<th>When to Choose It</th>"
        "</tr></thead><tbody>"
        "<tr>"
        f"<td><strong>Tier 0 · Leaky Integrator</strong><br>{lk.algo('int', 'INT')} + {lk.algo('mopt', 'MOPT', 'online_calib')}</td>"
        "<td class='wrap-cell'>Pure feedback damping; zero temporal lookahead. Autotuned "
        "<code>MOPT</code> optimizes per-mode (gain, leak) from PSDs.</td>"
        "<td><code>0 frames</code> (instant)</td>"
        "<td><code>~23 µs</code> (1,255 m)</td>"
        "<td class='wrap-cell'>Loop bring-up, ultra-low calibration budgets, or fallback path "
        "blended alongside predictive control (<code>1 - mix</code>).</td>"
        "</tr>"
        "<tr>"
        f"<td><strong>Tier 1 · Diagonal AR(P)</strong><br>{lk.algo('pf-ar', 'PF/AR')}</td>"
        "<td class='wrap-cell'>Per-mode temporal correlation &amp; single-mode vibrations "
        "(<code>B = 1</code>, zero cross-mode coupling).</td>"
        "<td><code>N_min = 256</code> (0.25 s @ 1 kHz)<br>Rule: <code>N_train / P &ge; 128</code></td>"
        "<td><code>24–34 µs</code> for <code>AR(16)</code><br>(<code>~33%</code> total CPU)</td>"
        "<td class='wrap-cell'>Sub-second cold-start locking, rapidly changing conditions, "
        "minimal CPU budgets, and automatic bootstrap inside Block-EOF.</td>"
        "</tr>"
        "<tr>"
        f"<td><strong>Tier 2 · Cross-Mode Block-EOF</strong><br>{lk.algo('eof', 'EOF')}</td>"
        "<td class='wrap-cell'>Spatial-temporal <strong>Taylor frozen-flow wind advection</strong> "
        "across coupled mode blocks (<code>B = 64</code> or <code>128</code>), plus ZOH ridge, "
        "difference-space DC pinning, wind physics prior, regime memory, FX-DM, &amp; multi-rate velocity.</td>"
        "<td>Locks in <code>0.25 s</code> via AR(16) bootstrap; full EOF at <code>N/D &ge; 8–12</code> "
        "(<code>6 s</code> for B=64, <code>12 s</code> for B=128; instant with <code>EOF/WIND</code>)</td>"
        "<td><code>76–108 µs</code><br>(<code>0.7–1.0</code> CPU core)</td>"
        "<td class='wrap-cell'><strong>Recommended default anchor</strong> for science ExAO, "
        "coronagraphy, wind-lag suppression (<code>~3&times;</code> lower noise gain than AR), and "
        "faint-star slow-WFS operation.</td>"
        "</tr>"
        "<tr>"
        f"<td><strong>Tier 3 · Block-EOF + Cascaded Self-Learning</strong><br>{lk.algo('selflearn', 'SELFLEARN')}</td>"
        "<td class='wrap-cell'>Everything in Block-EOF <em>plus</em> fast per-frame tracking of "
        "global gain drift (<code>SL/GLOBAL</code>) and state-dependent nonlinear PyWFS optical "
        "gain / regime shifts (<code>SL/CLUST</code> via <code>libgric</code>).</td>"
        "<td><code>keywarmup = 200</code> fr + causal Stein gates auto-open only when OOS error drops</td>"
        "<td><code>89 µs</code> @ 128 m<br><code>114 µs</code> @ 256 m<br>(full decoupled stack)</td>"
        "<td class='wrap-cell'>Unmodulated <code>0 &lambda;/D</code> PyWFS, strong nonlinear optical "
        "gain (<strong>&minus;36.4%</strong> residual vs. fixed EOF), or combined OG + vibration stress.</td>"
        "</tr>"
        "</tbody></table></div>\n"
        '<div class="pcg-callout-good">'
        "<p><strong>Two Non-Negotiable Architectural Rules:</strong> "
        "(1)&nbsp;<strong>Always cascade Self-Learning on top of Fixed-Basis Block-EOF</strong> "
        "(<code>u_total = u_EOF + &delta;u_L0 + &delta;u_L1</code>)&mdash;never run Self-Learning "
        "standalone, which degrades pure turbulence (33.5 vs. 19.2 nm) and leaks 18.35 nm (1.10&times;) "
        "on pure white noise. "
        "(2)&nbsp;<strong>Keep the outer modal basis fixed</strong> for PSOL, Block-EOF, and "
        "Self-Learning; any adaptive basis rotation (<code>CMODES</code>) must remain strictly "
        "decoupled inside <code>modalfilter</code>.</p></div>"
    )


def _render_sec3_ar(lk: _GuideLinker) -> str:
    ar_specs = [
        (
            ".PForder",
            "8",
            "INIT",
            "Number of temporal lookback taps <code>P</code> (1..64) per mode.",
            "<strong>Start with <code>16</code></strong> (Pareto optimum). <code>4</code> lags ZOH; "
            "<code>8</code> misses strong gusts; <code>32–64</code> adds &lt;0.2 pp Vis SR at "
            "4–14&times; CPU and overfits unless <code>NBtrain &ge; 4096</code>.",
        ),
        (
            ".PFlatency",
            "2.3",
            "LIVE",
            "Fractional prediction horizon <code>d</code> [WFS frames]. Target is linearly "
            "interpolated between <code>t+floor(d)</code> and <code>t+floor(d)+1</code>.",
            "Match measured total loop delay from <code>MLAT</code> / <code>testOL</code> "
            "(typically <code>2.2–2.5</code> fr). Too small leaves positive lag; too large "
            "over-extrapolates and raises noise gain.",
        ),
        (
            ".NBtrain",
            "2048",
            "INIT",
            "Rolling PSOL ring buffer length [frames] used to build each <code>P&times;P</code> Gram.",
            "Keep <code>NBtrain / P &ge; 128</code> (e.g., <code>2048–4096</code> for AR(16)). "
            "Shorter windows track faster wind changes but increase weight variance.",
        ),
        (
            ".minsamples",
            "512",
            "LIVE",
            "Minimum non-zero PSOL frames required before publishing the first AR filter.",
            "Keep <code>minsamples / P &ge; 16</code> (<code>256</code> is safe for AR(16) at "
            "0.25 s startup; for AR(32)+ you need <code>&ge; 1024</code> or progressive bootstrap).",
        ),
        (
            ".reglambda",
            "0.005",
            "LIVE",
            "Relative Tikhonov ridge damping <code>&lambda; = reglambda * tr(G)/P</code>.",
            "<strong>Stage-asymmetric tuning works best:</strong> <code>1e-4–1e-3</code> on "
            "high-SNR Stage 1; <code>5e-3–1e-2</code> on lower-SNR Stage 2 to suppress "
            "high-order mode ringing.",
        ),
        (
            ".maxnorm2",
            "1.35",
            "LIVE",
            "Hard ceiling on per-mode noise amplification <code>||w||_2^2</code>; solver triples "
            "<code>&lambda;</code> (up to 12&times;) until satisfied.",
            "<code>1.35</code> is safe for broadband turbulence; raise to <code>1.8–2.0</code> "
            "only on high-SNR loops with narrowband vibrations. Lower toward <code>1.0</code> on "
            "faint stars.",
        ),
        (
            ".maxdcgain",
            "0.985",
            "LIVE",
            "Strict upper bound on <code>|sum(w)|</code> (&lt; 1.0) preventing null-mode DC drift.",
            "Keep <code>0.985–0.995</code>. Never set &ge; 1.0, or weakly sensed modes will slowly "
            "integrate into the DM rail.",
        ),
        (
            ".loopgain",
            "0.30",
            "LIVE",
            "EMA smoothing factor blending each new solve into live <code>aolN_arPFmat</code> "
            "(first publish always uses 1.0).",
            "<code>0.25–0.40</code> suppresses update-to-update jitter without sluggishness.",
        ),
        (
            ".priorgain",
            "0.0",
            "LIVE",
            "DC gain of optional exponentially decaying low-pass shrinkage prior (decay via "
            f"{lk.fps('mkARPF', '.priordecay')}).",
            "Leave at <code>0.0</code> for standard operation; raise to <code>0.5–0.8</code> only "
            "when testing very short windows on faint stars to pull weights toward smoothing.",
        ),
    ]
    return (
        f'<h2 id="diagonal-ar">3. Diagonal Autoregressive Control — AR(P) '
        f'{render_section_badges(["loop_operation"])}</h2>\n'
        f"<p>Implemented in <code>cacao-fpsexec-cacaopc-mkARPF</code> (async solver) and "
        f"<code>cacao-fpsexec-cacaopc-applyARPF</code> (real-time SIMD dot product), "
        f"{lk.algo('pf-ar', 'PF/AR')} fits an independent scalar linear predictor of order "
        "<code>P</code> for every mode <code>m</code> using only that mode's own recent PSOL "
        "history:</p>\n"
        '<div class="pcg-eq-box">'
        '<span class="pcg-eq-lbl">Per-Mode Wiener-Ridge AR(P) Formulation (mkARPF.c / applyARPF.c)</span>'
        "Prediction:     y_hat_m(t + d) = sum_{k=0}^{P-1} w_{m,k} * x_m(t - k)\n"
        "Normal Eq.:     (G_m + lam * I) w_m = rhs_m + lam * w_prior,   lam = reglambda * tr(G_m) / P\n"
        "Safety guards:  ||w_m||_2^2 <= maxnorm2 (auto lam *= 3 backoff),  |sum_k w_{m,k}| <= maxdcgain < 1\n"
        "Live publish:   w_pub = (1 - loopgain) * w_pub + loopgain * w_m   (first update uses 1.0)"
        "</div>\n"
        "<h3>Why AR(16) Is the Diagonal Sweet Spot (The Cauchy&ndash;Schwarz Intuition)</h3>\n"
        "<p>You might expect a 4-tap predictor to predict a smooth low-order mode 2.4 frames ahead. "
        "In reality, benchmarking <code>AR(4)</code> through <code>AR(64)</code> reveals a crisp "
        "physical constraint&mdash;the <strong>Cauchy&ndash;Schwarz tradeoff between phase lead "
        "and L2 noise gain</strong>:</p>\n"
        '<div class="pcg-card-grid">'
        '<div class="pcg-card pcg-card-warn">'
        "<h4>Too Short: AR(4) &amp; AR(8)</h4>"
        "<p>To estimate a derivative over only 4 frames and extrapolate +2.4 frames forward "
        "requires huge positive/negative tap weights that violate <code>||w||_2^2 &le; 1.35</code>. "
        "Regularization collapses <code>AR(4)</code> to a smoothing filter with <strong>&minus;0.11 "
        "fr effective lead</strong> (worse than zero-order hold!) and the highest noise gain "
        "(0.70). <code>AR(8)</code> reaches +1.04 fr lead but still slips a V-spider petal during "
        "strong gusts.</p>"
        "</div>"
        '<div class="pcg-card pcg-card-good">'
        "<h4>Pareto Optimum: AR(16)</h4>"
        "<p>Spreading the negative differentiating lobe smoothly over taps <code>k = 6..15</code> "
        "achieves <strong>+1.52 fr effective phase lead</strong> while <em>simultaneously cutting</em> "
        "noise-gain squared by 17% (0.64 &rarr; 0.53). It locks within 0.25 s "
        "(<code>N_min = 256</code>), survives 1.85 &mu;m gusts with zero petal slips, and runs "
        "in <strong>24&ndash;34 &mu;s/frame</strong> (33% total CPU across 2 stages).</p>"
        "</div>"
        '<div class="pcg-card pcg-card-warn">'
        "<h4>Too Long: AR(32) &amp; AR(64)</h4>"
        "<p>Beyond ~16–20 ms, &gt;97% of single-mode atmospheric autocorrelation is already "
        "captured. At <code>N_min = 256</code>, <code>AR(64)</code> has only <code>N/P = 4</code> "
        "samples per parameter and catastrophically overfits (&minus;8% OOS variance reduction), "
        "triggering cold-start petal jumps. Even warm-started at <code>N = 4096</code>, it gains "
        "&lt;0.2 pp Vis Strehl over <code>AR(16)</code> at <strong>14&times; the CPU cost</strong> "
        "(<code>O(N_train * P^2)</code> Gram build).</p>"
        "</div>"
        "</div>\n"
        "<h3>Key <code>mkARPF</code> &amp; <code>applyARPF</code> Parameters</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>FPS Parameter</th><th>Default</th><th>Access</th>"
        "<th>What It Does</th><th>Practical Tuning Guidance</th>"
        "</tr></thead><tbody>"
        + _render_param_rows(lk, "mkARPF", ar_specs)
        + _render_param_rows(
            lk,
            "applyARPF",
            [
                (
                    ".rampsteps",
                    "64",
                    "LIVE",
                    "Number of frames over which <code>outPFstat</code> linearly ramps from 0 to 1 "
                    "once the first filter arrives.",
                    "Keep <code>32–64</code> frames (32–64 ms @ 1 kHz) for a completely bumpless "
                    "hand-off from integrator to predictor.",
                ),
            ],
        )
        + "</tbody></table></div>\n"
        "<p class='muted'>Watch live <code>mkARPF</code> outputs: "
        f"{lk.fps('mkARPF', '.out.n_samples')}, {lk.fps('mkARPF', '.out.rms_zoh')}, "
        f"{lk.fps('mkARPF', '.out.rms_pred')}, and {lk.fps('mkARPF', '.out.var_red_pct')}. "
        "Healthy broadband turbulence yields <code>var_red_pct</code> of +20% to +45%.</p>"
    )


def _render_sec4_eof(lk: _GuideLinker) -> str:
    eof_core_specs = [
        (
            ".blocksize",
            "128",
            "INIT",
            "Number of contiguous spatial modes <code>B</code> coupled inside each block "
            "(<code>D = P * B</code> predictors per mode).",
            "<strong><code>128</code></strong> for maximum steady-state contrast (needs "
            "<code>minsamples &ge; 12,000</code>, ~1.0 core); <strong><code>64</code></strong> "
            "converges 2&times; faster (<code>6,000</code> fr, 0.7 core) with nearly identical "
            "Stage-1 WFE. Use <code>16–32</code> when pairing with longer <code>PForder = 32</code>.",
        ),
        (
            ".PForder",
            "8",
            "INIT",
            "Cross-mode temporal lookback depth <code>P</code> (1..64).",
            "<strong><code>8</code></strong> is optimal for <code>B = 64–128</code>: spatial "
            "neighbors already supply phase-lead information without needing deep temporal lags. "
            "Keep <code>D = P * B &le; 1024</code> for fast Cholesky solves.",
        ),
        (
            ".diagorder",
            "16",
            "INIT",
            "Per-mode diagonal AR order used during cold-start bootstrap (<code>state = 1</code>) "
            "before <code>N &ge; minsamples</code>.",
            "Keep at <strong><code>16</code></strong> (paired with "
            f"{lk.fps('mkEOFPF', '.diagminsamples')} <code>= 256</code>) so Subaru V-spider petals "
            "lock within 0.25 s while the cross-mode training buffer fills.",
        ),
        (
            ".NBtrain",
            "16384",
            "INIT",
            "Sliding PSOL training window [frames] (up to 65,536).",
            "Maintain <code>NBtrain / (P * B) &ge; 12–16</code>: e.g., <code>16384</code> @ 1 kHz "
            "Stage 1 and <code>32768</code> @ 2 kHz Stage 2 for <code>B=128, P=8</code> "
            "(or use <code>gram_halflife &gt; 0</code> to extend memory without larger RAM).",
        ),
        (
            ".minsamples",
            "12000",
            "LIVE",
            "Minimum frames before promoting from diagonal bootstrap (<code>state=1</code>) to "
            "full cross-mode Block-EOF (<code>state=2</code>).",
            "<strong>Critical overfitting guard:</strong> enforce <code>minsamples / (P * B) "
            "&ge; 8–12</code> (<code>6,000</code> for B=64/P=8; <code>12,000</code> for B=128/P=8). "
            "With <code>EOF/WIND</code> active, the physics prior supplies <code>n_prior</code> "
            "virtual samples immediately.",
        ),
        (
            ".reglambda",
            "1.0e-4",
            "LIVE",
            "Relative Tikhonov ridge <code>&lambda; = reglambda * tr(G)/D</code> for cross-mode "
            "blocks.",
            "<strong>Use stage-asymmetric values:</strong> <code>1e-4</code> on high-SNR Stage 1 "
            "(strong atmospheric signal); <code>5e-3–1e-2</code> on lower-SNR Stage 2 or faint "
            "stars. Raise if <code>out.overfit_ratio &gt; 1.25</code>.",
        ),
        (
            ".zoh_ridge",
            "ON",
            "LIVE",
            "Shrinks ridge penalty toward the identity zero-order-hold map <code>[I; 0; ...]</code> "
            "instead of zero.",
            "<strong>ON for Stage 1</strong> (prevents DC-gain collapse on strong low-order "
            "turbulence); <strong>OFF for Stage 2</strong> (Stage 2 sees zero-mean high-pass "
            "residuals where shrinking toward 0 avoids amplifying noise).",
        ),
        (
            ".maxnorm2",
            "2.0",
            "LIVE",
            "p95 row L2 norm-squared cap <code>||F_m||_2^2</code> triggering automatic "
            "<code>&lambda;</code> backoff.",
            "<code>2.0</code> gives healthy headroom for cross-mode advection without ringing; "
            "tighten to <code>1.2–1.5</code> on photon-starved loops.",
        ),
        (
            ".updateperiod",
            "4",
            "LIVE",
            "Number of incoming double-buffer flips between full Block-EOF re-solves.",
            "With <code>tbuffsize = 256</code>: <code>4</code> (~1.0 s @ 1 kHz) on Stage 1 and "
            "<code>8</code> (~1.0 s @ 2 kHz) on Stage 2 keeps background solver CPU &lt; 1 core.",
        ),
    ]
    eof_ext_specs = [
        (
            ".diff_nmode",
            "0",
            "INIT",
            "Number of leading modes (e.g., 16–32) solved in temporal-difference coordinates "
            "<code>dx(t) = x(t) - x(t-1)</code> with exact pinned DC gain "
            f"({lk.fps('mkEOFPF', '.diff_maxdcgain')} <code>= 0.9995</code>, "
            f"{lk.fps('mkEOFPF', '.diff_order')}, {lk.fps('mkEOFPF', '.diff_reg')}).",
            "Set to <code>16–32</code> when heavy thermal petaling or slow tip/tilt drift causes "
            "DC sag in standard position-space EOF; weights pack transparently into "
            "<code>eofPFmat</code> with zero RT apply overhead.",
        ),
        (
            ".gram_halflife",
            "0.0",
            "LIVE",
            "Extended-memory chunk-Gram exponential half-life [frames] (<code>0</code> = sliding "
            "<code>NBtrain</code> window).",
            "Set to <code>15,000–30,000</code> frames in steady seeing to build deep statistical "
            "leverage beyond <code>NBtrain</code>; keep shorter (<code>4,000–8,000</code>) when "
            "wind drifts rapidly.",
        ),
        (
            ".regime_kmax",
            "0",
            "INIT",
            "Multi-anchor regime-weighted Gram library size <code>K</code> (<code>0</code>=off, "
            "<code>2..16</code>=on), blended via "
            f"{lk.fps('mkEOFPF', '.regime_kappa')}, {lk.fps('mkEOFPF', '.regime_bw')}, and "
            f"{lk.fps('mkEOFPF', '.regime_rlim')}.",
            "Enable (<code>4–8</code> anchors) during intermittent gust/lull cycles or recurring "
            "wind headings so returning to a prior regime restores its Gram instantly without "
            "re-learning from scratch.",
        ),
        (
            ".n_prior",
            "1024.0",
            "LIVE",
            "Equivalent sample weight of the <code>mlt-windlayers</code> Fourier frozen-flow "
            f"physics Gram (requires {lk.fps('mkEOFPF', '.wl_layers')} and "
            f"{lk.fps('mkEOFPF', '.dmmodes')}).",
            "Set <code>512–2048</code> on Stage 1 for instant cold-start cross-mode prediction "
            "(+70% VR at t=0). Pair with "
            f"{lk.fps('mkEOFPF', '.wl_switch_decay')} <code>= 0.20–0.25</code> to discount stale "
            "empirical Grams 6.2&times; faster on sudden wind switches. <strong>Do not mix with "
            "<code>.dm_kernel</code> (EOF/FX).</strong>",
        ),
        (
            ".dm_kernel",
            "",
            "INIT",
            "Pass-2 dynamic DM plant kernel FITS (<code>H_diag</code> / <code>H_mimo</code>) for "
            "Filtered-X EOF coordinates (<code>EOF/FX</code>).",
            "Use <strong>only</strong> on unshaped ringing DMs (cuts ringing <code>Q_vw</code> "
            "26.4&times;). When <code>dmpreshaper</code> + <code>PSOL/MIMO</code> already "
            "linearize the plate, leave empty and use <code>EOF/WIND</code> instead.",
        ),
        (
            ".mr_enable",
            "OFF",
            "LIVE",
            "Solves an additional zero-DC centered velocity matrix <code>outPFvel</code> via "
            "Catmull-Rom interpolation with extra ridge "
            f"{lk.fps('mkEOFPF', '.mr_vel_reg_mult')} (default <code>3.5</code>) and cap "
            f"{lk.fps('mkEOFPF', '.mr_vel_maxnorm2')}.",
            "Turn ON only for faint-star slow-WFS loops (250–500 Hz) paired with "
            f"{lk.algo('mrdm', 'MRDM')} (<code>mvalpacer</code>) so the DM executes smooth "
            "high-rate ramps instead of 250 Hz staircase jumps.",
        ),
    ]
    return (
        f'<h2 id="block-eof">4. Cross-Mode Transition Matrix — Block-EOF '
        f'{render_section_badges(["loop_operation"])}</h2>\n'
        f"<p>Implemented in <code>cacao-fpsexec-cacaopc-mkEOFPF</code> (OpenBLAS "
        "<code>dsyrk</code>/<code>dgemm</code> + LAPACKE Cholesky + <code>eoflin_phys.c</code>) "
        "and <code>cacao-fpsexec-cacaopc-applyEOFPF</code> (OpenMP + AVX SIMD), "
        f"{lk.algo('eof', 'EOF')} implements Guyon &amp; Males (2017) Empirical Orthogonal "
        "Functions (a vector autoregressive <code>VAR(P)</code> transition matrix) partitioned "
        "into spatial-frequency blocks of <code>B</code> coupled modes.</p>\n"
        "<h3>Physical Motivation: Why Cross-Mode Coupling Beats Any Diagonal AR Order</h3>\n"
        "<p>Under Taylor frozen-flow turbulence, wind advects wavefront phase across the telescope "
        "pupil. For any sine/cosine Fourier or KL mode pair <code>(c, s)</code> of spatial wave "
        "vector <code>k</code> moving at wind velocity <code>v</code>, advancing time by "
        "<code>d</code> frames is an <strong>exact 2D rotation</strong>:</p>\n"
        '<div class="pcg-eq-box">'
        '<span class="pcg-eq-lbl">Frozen-Flow Quadrature Coupling &amp; Block-EOF Normal Equations</span>'
        "Frozen-flow physics:  [c(t+d); s(t+d)] = R(k · v · d) [c(t); s(t)]   (skew-symmetric cross-mode energy flow)\n"
        "Block regressor:      x_blk(t) = [a_{s0..s0+B-1}(t), ..., a_{s0..s0+B-1}(t-P+1)]  in R^{D},  D = P * B\n"
        "Regularized solve:    (G_emp + w_phys*G_phys + lam*I) W = R_emp + w_phys*R_phys + lam * W_target\n"
        "                      where W_target = [I_B; 0; ...] if zoh_ridge=ON, else 0"
        "</div>\n"
        "<p>A diagonal <code>AR(P)</code> filter cannot see the quadrature partner <code>s(t)</code> "
        "and must instead approximate the time derivative by taking noisy finite differences of "
        "<code>c(t)</code> alone. Cross-mode <code>Block-EOF</code> reads the approaching "
        "wavefront directly off neighboring spatial modes&mdash;delivering <strong>+81.6% vs. "
        "+45.6%</strong> Stage-1 Block-0 variance reduction at <strong>~3&times; lower L2 noise "
        "gain</strong> (<code>||F_m||_2^2 ~ 0.7–0.9</code> vs. <code>&gt; 2.1</code> for "
        "unconstrained AR).</p>\n"
        "<h3>Automatic Progressive Cold-Start Bootstrap (<code>state 0 &rarr; 1 &rarr; 2</code>)</h3>\n"
        "<p>Because each block fits <code>D = P &times; B = 512..1024</code> weights per mode, "
        "activating unpriored Block-EOF too early (<code>N &lt; D</code>) causes severe "
        "overfitting. <code>mkEOFPF</code> prevents this automatically via a 3-state lifecycle "
        f"reported in {lk.fps('mkEOFPF', '.out.eof_active')}:</p>\n"
        '<div class="pcg-card-grid">'
        '<div class="pcg-card">'
        "<h4>State 0 · Accumulating (0–0.25 s)</h4>"
        "<p><code>n_samples &lt; diagminsamples</code> (256). Loop runs cleanly on the baseline "
        "modal leaky integrator while <code>modalfilter</code> fills the PSOL buffer.</p>"
        "</div>"
        '<div class="pcg-card pcg-card-good">'
        "<h4>State 1 · Diagonal AR(16) Bootstrap</h4>"
        "<p>At <code>256</code> frames (0.25 s @ 1 kHz), <code>mkEOFPF</code> fits diagonal "
        "<code>AR(diagorder=16)</code> directly into the Block-EOF matrix layout (extra taps "
        "<code>P..P_diag-1</code> sit in trailing <code>diag_tail</code> columns), locking petals "
        "immediately while clean PSOL samples accumulate.</p>"
        "</div>"
        '<div class="pcg-card pcg-card-good">'
        "<h4>State 2 · Full Cross-Mode Block-EOF</h4>"
        "<p>Once <code>eff_samples &ge; minsamples</code> (or immediately if "
        "<code>EOF/WIND</code> provides a live physics prior), blocks promote smoothly via EMA "
        f"({lk.fps('mkEOFPF', '.loopgain')}) into full cross-mode prediction. High-order "
        "unpriored blocks stay on diagonal bootstrap until enough data exist.</p>"
        "</div>"
        "</div>\n"
        "<h3>Core <code>mkEOFPF</code> &amp; <code>applyEOFPF</code> Parameters</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>FPS Parameter</th><th>Default</th><th>Access</th>"
        "<th>What It Does</th><th>Practical Tuning Guidance</th>"
        "</tr></thead><tbody>"
        + _render_param_rows(lk, "mkEOFPF", eof_core_specs)
        + _render_param_rows(
            lk,
            "applyEOFPF",
            [
                (
                    ".nthreads",
                    "4",
                    "LIVE",
                    "OpenMP thread count parallelizing real-time inference across spatial blocks.",
                    "<code>4</code> threads achieves <code>88–108 &mu;s</code> across 1,255–1,965 "
                    "modes with zero RT timeouts; avoid oversubscribing physical cores when "
                    "running two AO stages concurrently.",
                ),
            ],
        )
        + "</tbody></table></div>\n"
        "<h3>Composable Block-EOF Extensions (When &amp; How to Enable Each)</h3>\n"
        "<p>All extensions execute inside <code>mkEOFPF</code> with zero changes to "
        "<code>applyEOFPF</code>'s hot path (except <code>.mr_enable</code>, which adds the "
        "optional velocity stream):</p>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Extension Parameter</th><th>Default</th><th>Access</th>"
        "<th>Mechanism</th><th>When to Use &amp; Tuning Rules</th>"
        "</tr></thead><tbody>"
        + _render_param_rows(lk, "mkEOFPF", eof_ext_specs)
        + "</tbody></table></div>"
    )


def _render_sec5_selflearn(lk: _GuideLinker) -> str:
    sl_specs = [
        (
            ".inbasePF",
            "",
            "INIT",
            "Upstream Block-EOF prediction stream (<code>aolN_modevalPF_eof</code>) that "
            "Self-Learning refines additively.",
            "<strong>Always wire to <code>applyEOFPF</code>'s output!</strong> Never leave blank "
            "for science runs (standalone RLS lacks cross-mode frozen-flow advection and fails "
            "the white-noise null test).",
        ),
        (
            ".NBmodeMax",
            "64",
            "INIT",
            "Leading modal span <code>M</code> refined by Self-Learning (higher modes pass "
            "Block-EOF through untouched).",
            "<code>64–128</code> covers the low/mid spatial frequencies where PyWFS optical-gain "
            "nonlinearity and vibrations concentrate (89 &mu;s @ 128 m; 114 &mu;s @ 256 m).",
        ),
        (
            ".nl_mode",
            "0",
            "INIT",
            "Feature basis: <code>0</code> = linear zero-DC increments + WFS; "
            "<code>1</code> = +3 odd PyWFS nonlinear terms (S-curve saturation, log-energy OG, "
            "TT off-apex OG); <code>2</code> = +shared low-order WFS crosstalk.",
            "Use <code>0</code> for modulated 3 &lambda;/D PyWFS; set <strong><code>1</code></strong> "
            "(or <code>2</code>) for unmodulated <code>0 &lambda;/D</code> PyWFS where S-curve "
            "saturation and TT-modulated optical gain dominate.",
        ),
        (
            ".key_mode",
            "0",
            "INIT",
            "Low-D state-space key clustered by <code>libgric</code>: "
            "<code>0</code>=TT2_E2 (4D), <code>1</code>=E1_LOGE (1D), <code>2</code>=WFS_LO4 (4D), "
            "<code>3</code>=TT2_DM2_E2 (6D), <code>4</code>=REGIME_E2_VEL (3D), "
            "<code>5</code>=EXTERNAL.",
            "<strong><code>0</code> (TT2_E2)</strong> is the best all-around choice for PyWFS "
            "nonlinearity (tracks tip/tilt apex excursion + low/high WFS energy); use "
            "<code>4</code> (REGIME) for seeing/wind-speed regime switches.",
        ),
        (
            ".kmax",
            "16",
            "INIT",
            "Maximum number of <code>libgric</code> state-space cluster anchors (1..64).",
            "<code>8–16</code> clusters capture distinct tip-tilt / seeing regimes without "
            "fragmenting per-cluster sample counts. Pair with "
            f"{lk.fps('selflearn', '.rlim')} <code>= 1.8–2.5</code>.",
        ),
        (
            ".lam0",
            "20.0",
            "INIT",
            "Level-0 Global Online Adaptive Filter RLS ridge prior.",
            "<code>20.0</code> responds smoothly in ~100–300 frames; raise to <code>50–100</code> "
            "on noisy faint stars.",
        ),
        (
            ".lam1",
            "200.0",
            "INIT",
            "Level-1 per-cluster RLS shrinkage ridge toward Level 0 (always keep "
            "<code>lam1 &ge; 5–10 &times; lam0</code>).",
            "<code>150–300</code> forces clusters to deviate from Level 0 <em>only</em> when a "
            "cluster accumulates strong, repeatable state-dependent evidence.",
        ),
        (
            ".gamma0",
            "0.998",
            "INIT",
            "Level-0 exponential forgetting factor (effective memory "
            "<code>1/(1-&gamma;0) = 500</code> fr) and Level-1 "
            f"{lk.fps('selflearn', '.gamma1')} (<code>0.995</code> = 200 fr per active cluster).",
            "Use <code>0.997–0.999</code> for global drift; set <code>gamma1 = 0.995–0.999</code> "
            "(higher preserves rarely visited clusters longer).",
        ),
        (
            ".gate_eta",
            "0.995",
            "INIT",
            "EMA decay of the causal out-of-sample James-Stein shrinkage gates "
            "(<code>alpha_l0</code>, <code>alpha_l1</code>).",
            "<code>0.995</code> (~200-frame window) reacts quickly when regimes change while "
            "holding steady at <code>0.00</code> under pure noise.",
        ),
        (
            ".max_wfs_gain",
            "0.5",
            "INIT",
            "Hard physical stability cap on learned WFS optical-gain weight (also bounds odd NL "
            "terms inside a stability ball).",
            "Set <strong><code>0.35–0.45</code></strong> on closed-loop PyWFS (0.40 default in "
            "<code>cacaoloop</code>) to guarantee closed-loop gain margin even under 3–5&times; "
            "optical-gain swings.",
        ),
        (
            ".max_tweak",
            "0.25",
            "INIT",
            "Hard per-mode absolute clamp on applied residual tweak [modal units].",
            "Keep <code>0.15–0.25</code> (and "
            f"{lk.fps('selflearn', '.max_ar_norm2')} <code>= 2.0</code>) so a sudden glitch can "
            "never inject a large DM kick.",
        ),
        (
            ".shadow",
            "OFF",
            "LIVE",
            "Shadow commissioning mode: runs GRIC clustering, RLS updates, and OOS scoring "
            "without adding any tweak to the DM.",
            "<strong>Always start with <code>shadow=ON</code></strong> for 5–10 s to inspect "
            "<code>out.oos_vr_l0_pct</code>, <code>out.oos_vr_l1_pct</code>, and "
            "<code>out.alpha_l0/l1</code> before engaging live output.",
        ),
        (
            ".enable_l0",
            "ON",
            "LIVE",
            "Live A/B switch for Level-0 Global Online Adaptive Filter (and "
            f"{lk.fps('selflearn', '.enable_l1')} for Level-1 Clustered Self-Learning).",
            "Toggle independently on sky to measure exact WFE/Strehl gain of Global RLS alone "
            "vs. Global + Clustered.",
        ),
        (
            ".apply_gain",
            "1.0",
            "LIVE",
            "Live scalar blend multiplier <code>[0..1]</code> on the Stein-gated tweak (plus "
            f"{lk.fps('selflearn', '.learnON')} and {lk.fps('selflearn', '.reset')}).",
            "Ramp smoothly <code>0.25 &rarr; 0.5 &rarr; 1.0</code> on first on-sky test; set "
            "<code>learnON=OFF</code> to freeze weights during photometric/coronagraphic sequences.",
        ),
    ]
    return (
        f'<h2 id="self-learning">5. Cascaded Online Self-Learning (Global RLS + Clustered '
        f'libgric) {render_section_badges(["loop_operation"])}</h2>\n'
        "<p>Even an ideal linear <code>Block-EOF</code> predictor assumes the plant is "
        "<strong>linear and stationary</strong> over its 10–30 s training window. Real extreme-AO "
        "loops break both assumptions: an unmodulated <code>0 &lambda;/D</code> Pyramid WFS "
        "exhibits an odd S-curve saturation and instantaneous optical-gain drops whenever tip/tilt "
        "excursions move the PSF off the pyramid apex, while seeing bursts and narrowband "
        "vibrations evolve on sub-second timescales.</p>\n"
        f"<p>Implemented in <code>cacao-fpsexec-cacaopc-selflearn</code> ({lk.algo('selflearn', 'SELFLEARN')}), "
        "Cascaded Online Self-Learning solves this by learning a <strong>strictly bounded, "
        "zero-DC residual refinement</strong> on top of Fixed-Basis Block-EOF every single frame:</p>\n"
        '<div class="pcg-eq-box">'
        '<span class="pcg-eq-lbl">2-Level Hierarchical Cascade &amp; Causal Stein Gate (selflearn_core.c)</span>'
        "Cascade sum:      u_total(t)   = u_EOF(t) + apply_gain * clamp(alpha_L0 * sh0 * d_L0(t) + alpha_L1 * d_L1(t, z_t), ±max_tweak)\n"
        "Zero-DC features: phi_{t,m}    = [dOL_m(t..t-3),  w_m(t),  (opt: odd PyWFS NL terms),  dOL_{0..q-1}(t),  (opt: w_{0..q-1}(t))]\n"
        "Causal target:    y_t(s)       = OL(s + d) - u_EOF(s)   [evaluated strictly causally at frame t = s + floor(d) + 1]\n"
        "Level 0 (Global): (G0 + lam0*I) w0 = b0                 [100% of frames, exponential forgetting gamma0 = 0.998]\n"
        "Level 1 (GRIC):   (G1_k + lam1*I) w1_k = b1_k           [trained on unbiased residual y_t - y_L0_fit; soft LWPR blend across K clusters]\n"
        "Stein gate:       alpha_L      = clamp( EMA(y · y_hat) / EMA(y_hat · y_hat), 0, 1 )   [closes to 0.00 on pure white noise]"
        "</div>\n"
        "<h3>Four Built-In Stability Invariants (Why It Cannot Blow Up Your Loop)</h3>\n"
        '<div class="pcg-card-grid">'
        '<div class="pcg-card pcg-card-good">'
        "<h4>1. Zero-DC Increment Basis</h4>"
        "<p>Every PSOL regressor is a first difference <code>dOL(t) = OL(t) - OL(t-1)</code>, "
        "which vanishes identically at DC. There is no unconstrained intercept, so Self-Learning "
        "can never wind up a mode into the DM rail.</p>"
        "</div>"
        '<div class="pcg-card pcg-card-good">'
        "<h4>2. Physical Stability Ball Projection</h4>"
        "<p>After every exact SPD Cholesky update, weights are projected back onto a physical "
        "stability ball: AR increment <code>||w_AR||_2^2 &le; max_ar_norm2</code> and WFS "
        "optical-gain weight <code>w_phys &in; [-0.35, +max_wfs_gain]</code> (with nonlinear odd "
        "terms jointly L1-bounded).</p>"
        "</div>"
        '<div class="pcg-card pcg-card-good">'
        "<h4>3. Independent Causal OOS Stein Gates</h4>"
        "<p>Before updating weights with frame <code>s</code>'s newly revealed target, the engine "
        "scores the <em>strictly out-of-sample</em> prediction made <code>d</code> frames earlier. "
        "If a layer has no genuine predictive skill (e.g., pure white noise), its Stein gate "
        "<code>alpha_l0</code> / <code>alpha_l1</code> automatically shrinks to <strong>0.00</strong> "
        "(verified: 1.43 nm / 1.000&times; leakage on 40 nm pure white-noise null test).</p>"
        "</div>"
        '<div class="pcg-card pcg-card-good">'
        "<h4>4. Distance Fail-Safe &amp; Outlier Skip</h4>"
        "<p>If the current state key <code>z_t</code> lands farther than "
        f"{lk.fps('selflearn', '.gate_mult')}<code> &times; rlim</code> from every known "
        "<code>libgric</code> cluster anchor, Level-1 smoothly gates off and falls back cleanly "
        "to Level 0 + Block-EOF. Glitches exceeding <code>outlier_sig</code> skip RLS updates "
        "entirely.</p>"
        "</div>"
        "</div>\n"
        "<h3>Choosing <code>.key_mode</code> for GRIC State-Space Clustering</h3>\n"
        '<div class="table-wrap"><table><thead><tr>'
        "<th><code>.key_mode</code></th><th>Enum / Dim</th><th>State Vector Features</th>"
        "<th>Best Physical Use Case</th>"
        "</tr></thead><tbody>"
        "<tr><td><code>0</code> (default)</td><td><code>TT2_E2</code> (4D)</td>"
        "<td><code>[w_0, w_1, log E_lo, log E_hi]</code></td>"
        "<td class='wrap-cell'><strong>Default for PyWFS:</strong> directly tracks tip/tilt "
        "excursion off pyramid apex plus low/high spatial-frequency residual energy.</td></tr>"
        "<tr><td><code>1</code></td><td><code>E1_LOGE</code> (1D)</td>"
        "<td><code>[log E_tot]</code></td>"
        "<td class='wrap-cell'>Pure seeing / Strehl-dependent scalar optical gain tracking with "
        "minimal cluster fragmentation.</td></tr>"
        "<tr><td><code>2</code></td><td><code>WFS_LO4</code> (4D)</td>"
        "<td><code>[w_0, w_1, w_2, w_3]</code></td>"
        "<td class='wrap-cell'>Tip/tilt + focus/astigmatism nonlinear cross-coupling on "
        "unmodulated PyWFS or strong low-order static aberrations.</td></tr>"
        "<tr><td><code>3</code></td><td><code>TT2_DM2_E2</code> (6D)</td>"
        "<td><code>[w_0, w_1, dm_0, dm_1, log E_lo, log E_hi]</code></td>"
        "<td class='wrap-cell'>Adds DM tip/tilt position when hysteresis or edge-actuator "
        "saturation depends on absolute DM stroke.</td></tr>"
        "<tr><td><code>4</code></td><td><code>REGIME_E2_VEL</code> (3D)</td>"
        "<td><code>[log E_lo, log E_hi, log E_dOL]</code></td>"
        "<td class='wrap-cell'>Separates slow/calm vs. fast-wind/gust dynamical regimes using "
        "rolling 64-frame PSOL velocity energy.</td></tr>"
        "<tr><td><code>5</code></td><td><code>EXTERNAL</code> (&le;16D)</td>"
        f"<td>Custom 1D SHM stream via {lk.fps('selflearn', '.inkey')}</td>"
        "<td class='wrap-cell'>Feed external telemetry (e.g., wind vector, focal-plane Strehl, "
        "or telescope elevation) directly into <code>libgric</code>.</td></tr>"
        "</tbody></table></div>\n"
        "<h3>Key <code>cacaopc-selflearn</code> Parameters &amp; Live A/B Controls</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>FPS Parameter</th><th>Default</th><th>Access</th>"
        "<th>What It Does</th><th>Practical Tuning Guidance</th>"
        "</tr></thead><tbody>"
        + _render_param_rows(lk, "selflearn", sl_specs)
        + "</tbody></table></div>"
    )


def _render_sec6_setup_workflow(lk: _GuideLinker) -> str:
    return (
        '<h2 id="setup-workflow">6. Step-by-Step Setup &amp; Safe Commissioning Workflow '
        f'{render_section_badges(["calibration", "loop_operation", "analysis"])}</h2>\n'
        "<p>Follow this six-step bring-up sequence whenever deploying predictive control on a new "
        "AO loop, instrument mode, or simulation bench. Each step has a quantitative go/no-go "
        "check before you engage live DM commands.</p>\n"
        '<div class="pcg-step-list">'
        # Step 1
        '<div class="pcg-step">'
        '<div class="pcg-step-hdr"><span class="guide-num">1</span>'
        "<strong>Validate Baseline Loop &amp; Unbiased PSOL Observer</strong></div>"
        "<p>Close the baseline leaky integrator, verify <code>MLAT</code> / <code>testOL</code> "
        "latency alignment (&lt; 0.1 fr mismatch), enable 3D dynamic PSOL "
        f"({lk.fps('modalfilter', '.comp.dynpsol.enable')}) on plate DMs, verify optical-gain "
        f"scaling (<code>mWFSfact = 1/g_opt</code>), and turn on WFS dark subtraction "
        f"({lk.flag('--wfs-dark-adu')}) for faint stars.</p>"
        "<p><strong>Go check:</strong> During a small modal poke or <code>testOL</code> probe, "
        "<code>aolN_modevalOL</code> shows zero probe leakage and stays stationary regardless of "
        "loop gain.</p>"
        "</div>"
        # Step 2
        '<div class="pcg-step">'
        '<div class="pcg-step-hdr"><span class="guide-num">2</span>'
        "<strong>Enable PSOL Double-Buffer Telemetry</strong></div>"
        f"<p>Set {lk.fps('modalfilter', '.comp.OLmodes')}<code>=ON</code>, "
        f"{lk.fps('modalfilter', '.comp.tbuff')}<code>=ON</code>, and "
        f"{lk.fps('modalfilter', '.comp.tbuffsize')}<code>=256</code>. This publishes both "
        "per-frame <code>aolN_modevalOL</code> (triggering <code>applyARPF</code> / "
        "<code>applyEOFPF</code>) and the 256-frame ping-pong buffer "
        "<code>aolN_modevalOL_buff</code> (triggering <code>mkARPF</code> / "
        "<code>mkEOFPF</code>).</p>"
        "</div>"
        # Step 3
        '<div class="pcg-step">'
        '<div class="pcg-step-hdr"><span class="guide-num">3</span>'
        "<strong>Start Solver &amp; Applier in Shadow (Observation) Mode</strong></div>"
        f"<p>Start <code>mkEOFPF-N</code> + <code>applyEOFPF-N</code> (or <code>mkARPF-N</code> + "
        f"<code>applyARPF-N</code>) while keeping {lk.fps('modalfilter', '.PF.enable')}<code>=OFF</code> "
        f"(or {lk.fps('modalfilter', '.PF.mixcoeff')}<code>=0.0</code>). Watch the built-in "
        "out-of-sample diagnostics as the buffer fills:</p>"
        "<p><strong>Go check:</strong> "
        f"{lk.fps('mkEOFPF', '.out.eof_active')} reaches <code>1</code> (bootstrap) then "
        f"<code>2</code> (EOF); {lk.fps('mkEOFPF', '.out.var_red_oos_pct')} is strongly positive "
        "(+20% to +70%); and "
        f"{lk.fps('mkEOFPF', '.out.overfit_ratio')} stays within <code>1.00–1.20</code>.</p>"
        "</div>"
        # Step 4
        '<div class="pcg-step">'
        '<div class="pcg-step-hdr"><span class="guide-num">4</span>'
        "<strong>Engage Predictive Control Smoothly in <code>modalfilter</code></strong></div>"
        f"<p>Set {lk.fps('modalfilter', '.PF.NBblock')}<code>=1</code>, "
        f"{lk.fps('modalfilter', '.PF.maxwaitus')}<code>=3000</code>, "
        f"{lk.fps('modalfilter', '.PF.enable')}<code>=ON</code>, and ramp "
        f"{lk.fps('modalfilter', '.PF.mixcoeff')} from <code>0.3 &rarr; 0.6 &rarr; 0.90</code> "
        "(with per-mode rolloff <code>CACAO_PF_MGAIN_EXP = 0.50</code> so noisy high-order modes "
        "blend conservatively).</p>"
        "<p><strong>Go check:</strong> "
        f"{lk.fps('modalfilter', '.PF.timeout_cnt')} stays at <code>0</code>, WFS modal RMS drops "
        "across low/mid modes, and no high-frequency ringing appears.</p>"
        "</div>"
        # Step 5
        '<div class="pcg-step">'
        '<div class="pcg-step-hdr"><span class="guide-num">5</span>'
        "<strong>Optionally Layer Cascaded Self-Learning (Shadow &rarr; Live)</strong></div>"
        "<p>Route <code>applyEOFPF-N.outdata = aolN_modevalPF_eof</code> and "
        "<code>applyEOFPF-N.outPFstat = aolN_outPFstat_eof</code> into "
        f"{lk.fps('selflearn', '.inbasePF')} / {lk.fps('selflearn', '.inbaseStat')}, with "
        "<code>selflearn-N.outdata = aolN_modevalPF</code> and <code>out_mode = 0</code>. "
        f"Start with {lk.fps('selflearn', '.shadow')}<code>=ON</code> for 5&ndash;10 s, verify "
        f"{lk.fps('selflearn', '.out.oos_vr_l0_pct')} &gt; 0 and "
        f"{lk.fps('selflearn', '.out.alpha_l0')} &gt; 0.2, then switch "
        f"{lk.fps('selflearn', '.shadow')}<code>=OFF</code> and ramp "
        f"{lk.fps('selflearn', '.apply_gain')} <code>0.25 &rarr; 1.0</code>.</p>"
        "</div>"
        # Step 6
        '<div class="pcg-step">'
        '<div class="pcg-step-hdr"><span class="guide-num">6</span>'
        "<strong>Audit Optimality with <code>modalwhite</code></strong></div>"
        f"<p>Run {lk.algo('white', 'WHITE', 'analysis')} (<code>cacao-fpsexec-modalwhite</code>) "
        "non-intrusively on <code>aolN_modevalWFS_buff</code> and <code>aolN_modevalDM_buff</code>. "
        "An optimal linear predictor leaves an <code>MA(d-1)</code> innovation whose "
        "autocorrelation and cross-mode correlation vanish for all lags <code>k &ge; ceil(&tau;)</code>.</p>"
        "<p><strong>Go check:</strong> "
        f"{lk.fps('modalwhite', '.out.alert_flags')}<code> == 0</code>, "
        f"{lk.fps('modalwhite', '.out.Q_vw_b0')} and {lk.fps('modalwhite', '.out.Q_xmode_b0')} "
        "drop dramatically relative to the integrator baseline, and "
        f"{lk.fps('modalwhite', '.out.recov_wfe_nm')} is near the noise floor.</p>"
        "</div>"
        "</div>\n"
        "<h3>Quick Command-Line Recipes (<code>cacao-work</code> &amp; Live FPS)</h3>\n"
        "<pre><code>"
        "# 1. Steady High-Contrast 2-Stage Block-EOF (B=128, P=8) + AR(16) bootstrap + ZOH ridge on Stg1\n"
        "./scripts/run-ao3k-scexao.sh --predictive --pf-mode eof --pf-blocksize 128 --pf-order 8 \\\n"
        "    --pf-reg 1e-4 --pf-reg2 1e-2 --pf-maxnorm2 2.0 --pf-zoh-ridge --no-pf-zoh-ridge2 \\\n"
        "    --pf-nbtrain1 16384 --pf-nbtrain2 32768 --pf-minsamples1 12000 --pf-minsamples2 24000 \\\n"
        "    --modalwhite --phys-time 10.0\n"
        "\n"
        "# 2. Dynamic Wind / Fast Cold-Start: Block-EOF(B=64, P=8) + live windlayers physics prior\n"
        "./scripts/run-ao3k-scexao.sh --predictive --pf-mode eof --pf-blocksize 64 --pf-order 8 \\\n"
        "    --pf-reg 1e-4 --pf-reg2 1e-2 --windlayers1 --pf-n-prior 1024 --pf-wl-switch-decay 0.20 \\\n"
        "    --pf-minsamples1 6000 --pf-minsamples2 12000 --modalwhite --phys-time 10.0\n"
        "\n"
        "# 3. Unmodulated 0 l/D PyWFS with Cascaded Self-Learning (Global RLS + Clustered libgric)\n"
        "CACAO_SELFLEARN_ENABLE=1 CACAO_SELFLEARN_MODES=128 CACAO_SELFLEARN_NL_MODE=1 \\\n"
        "CACAO_SELFLEARN_KEYMODE=0 CACAO_SELFLEARN_KMAX=16 CACAO_SELFLEARN_MAX_WFS_GAIN=0.40 \\\n"
        "./scripts/run-ao3k-scexao.sh --wfs2-mod-rad 0.0 --predictive --pf-mode eof \\\n"
        "    --pf-blocksize 64 --pf-order 8 --live-2wfs1dm-sec 2.0 --modalwhite --phys-time 10.0\n"
        "\n"
        "# 4. Live FPS commissioning toggles (zero restart needed on a running CACAO loop)\n"
        "milk-fps-set selflearn-1 .shadow ON              # observe OOS VR &amp; Stein gates safely\n"
        "milk-fps-set selflearn-1 .shadow OFF .apply_gain 0.5\n"
        "milk-fps-set selflearn-1 .enable_l1 OFF          # live A/B: Global RLS alone vs. Clustered\n"
        "milk-fps-set mfilt-1     .PF.mixcoeff 0.90       # adjust predictive blend live\n"
        "</code></pre>"
    )


def _render_sec7_presets(lk: _GuideLinker) -> str:
    return (
        '<h2 id="tuning-presets">7. Ready-to-Use Parameter Presets by Observing Regime '
        f'{render_section_badges(["loop_operation"])}</h2>\n'
        "<p>Use these verified starting configurations to match your telescope, guide-star "
        "brightness, WFS modulation, and wind stationarity:</p>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Observing Regime</th>"
        "<th>Recommended Stack</th>"
        "<th>Key Starting Parameters</th>"
        "<th>Expected Behavior &amp; Watch-Outs</th>"
        "</tr></thead><tbody>"
        "<tr>"
        "<td><strong>Fast Cold-Start / Rapidly Changing Seeing</strong></td>"
        f"<td>{lk.algo('pf-ar', 'PF/AR')} (<code>AR(16)</code>)</td>"
        "<td class='wrap-cell'><code>PForder=16</code>, <code>NBtrain=2048–4096</code>, "
        "<code>minsamples=256</code>, <code>reg1=1e-4</code>, <code>reg2=1e-2</code>, "
        "<code>maxnorm2=1.35</code>, <code>mix=0.90</code></td>"
        "<td class='wrap-cell'>Locks in 0.25 s, survives gusts with zero petal slips, 24–34 &mu;s "
        "RT cost. Does not capture cross-mode wind advection.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Bright-Star Steady High-Contrast ExAO (Default)</strong></td>"
        f"<td>{lk.algo('eof', 'EOF')} (<code>B=128, P=8</code> + <code>ZOH</code> Stg1)</td>"
        "<td class='wrap-cell'><code>blocksize=128</code>, <code>PForder=8</code>, "
        "<code>diagorder=16</code>, <code>NBtrain=16384/32768</code>, "
        "<code>minsamples=12000/24000</code>, <code>reg=1e-4 / 1e-2</code>, "
        "<code>zoh_ridge=ON(S1)/OFF(S2)</code>, <code>maxnorm2=2.0</code></td>"
        "<td class='wrap-cell'>Deepest 10–20 &lambda;/D coronagraph contrast (&minus;13–14% vs. "
        "matched AR(16)) and &minus;41% LLOWFS stroke at ~1.0 CPU core.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Meandering Wind / Sudden Heading Switches</strong></td>"
        f"<td>{lk.algo('eof', 'EOF')} (<code>B=64, P=8</code>) + "
        f"{lk.algo('wind', 'WIND', 'online_calib')} + <code>EOF/MEM</code></td>"
        "<td class='wrap-cell'><code>blocksize=64</code>, <code>PForder=8</code>, "
        "<code>minsamples=6000</code>, <code>n_prior=1024</code>, "
        "<code>wl_switch_decay=0.20</code>, optional <code>regime_kmax=6</code></td>"
        "<td class='wrap-cell'>Instant cold-start (+70% VR) and 6.2&times; lower WFE across "
        "+60&deg; wind switches. Never combine <code>EOF/WIND</code> with <code>EOF/FX</code>.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Unmodulated 0 &lambda;/D PyWFS / Nonlinear Optical Gain</strong></td>"
        f"<td>{lk.algo('eof', 'EOF')} + {lk.algo('selflearn', 'SELFLEARN')} "
        "(<code>SL/GLOBAL</code> + <code>SL/CLUST</code>)</td>"
        "<td class='wrap-cell'><code>NBmodeMax=128</code>, <code>nl_mode=1</code>, "
        "<code>key_mode=0</code> (TT2_E2), <code>kmax=12–16</code>, <code>rlim=2.0</code>, "
        "<code>lam0=20</code>, <code>lam1=200</code>, <code>max_wfs_gain=0.40</code>, "
        "<code>max_tweak=0.25</code></td>"
        "<td class='wrap-cell'>Cuts unmodulated PyWFS residual <strong>&minus;36.4%</strong> over "
        "fixed EOF while Stein gates guarantee 1.000&times; white-noise safety.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Faint Star (m &ge; 9–10) Photon/RON-Limited</strong></td>"
        f"<td>Slow WFS (250–500 Hz) + {lk.algo('eof', 'EOF')} + {lk.algo('mrdm', 'MRDM')}</td>"
        "<td class='wrap-cell'><code>wfs1_rate=250 Hz</code>, <code>wfs_dark_adu</code> ON, "
        "<code>WFSnormfloor=0.001</code>, <code>blocksize=64</code>, <code>reg=1e-3–5e-3</code>, "
        "<code>mr_enable=ON</code>, <code>mr_vel_reg_mult=3.5</code>, <code>mvalpacer</code> "
        "upstream of <code>dmpreshaper</code></td>"
        "<td class='wrap-cell'>+12 pts Stage-1 H-Strehl over 1 kHz EOF (80.4% vs. 50.7% best "
        "integrator). Stay &ge; 250 Hz on 4-spider pupils to avoid island petaling.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Heavy Low-Order Thermal Petaling / Slow Drift</strong></td>"
        f"<td>{lk.algo('eof', 'EOF')} with Difference-Space Leading Modes</td>"
        "<td class='wrap-cell'><code>diff_nmode=16–32</code>, <code>diff_order=16</code>, "
        "<code>diff_reg=0.05</code>, <code>diff_maxnorm2=4.0</code>, "
        "<code>diff_maxdcgain=0.9995</code>, <code>zoh_ridge=ON</code></td>"
        "<td class='wrap-cell'>Pins exact DC gain on lowest-order modes so slow island/TT "
        "drifts never sag, while retaining cross-mode velocity coupling.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Unshaped Resonant Plate DM (No Pre-Shaper)</strong></td>"
        f"<td>{lk.algo('eof', 'EOF')} + <code>EOF/FX</code> + {lk.algo('psol', 'PSOL')} MIMO</td>"
        "<td class='wrap-cell'><code>dm_kernel=H_mimo.fits</code> (Pass-1/2), "
        "<code>dynpsol.enable=ON</code>, <code>n_prior=0</code> (keep <code>EOF/WIND</code> OFF)</td>"
        "<td class='wrap-cell'>Convolves EOF regressors through the DM impulse response, cutting "
        "ringing whiteness <code>Q_vw</code> by 26.4&times;.</td>"
        "</tr>"
        "</tbody></table></div>"
    )


def _render_sec8_troubleshooting(lk: _GuideLinker) -> str:
    return (
        '<h2 id="troubleshooting">8. Live Diagnostics &amp; Troubleshooting Cookbook '
        f'{render_section_badges(["analysis", "loop_operation"])}</h2>\n'
        "<p>Every CACAO predictive unit exports live health counters over FPS shared memory so "
        "you can diagnose mistuning objectively without guessing.</p>\n"
        "<h3>Key Live Health Counters to Monitor</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Unit &amp; Output</th><th>Healthy Range</th><th>What It Measures</th>"
        "</tr></thead><tbody>"
        f"<tr><td>{lk.fps('mkEOFPF', '.out.eof_active')}</td>"
        '<td><span class="pcg-tag-ok">1 &rarr; 2</span></td>'
        "<td class='wrap-cell'><code>0</code>=warming up, <code>1</code>=diagonal AR bootstrap, "
        "<code>2</code>=full cross-mode Block-EOF active.</td></tr>"
        f"<tr><td>{lk.fps('mkEOFPF', '.out.var_red_oos_pct')}</td>"
        '<td><span class="pcg-tag-ok">+15% to +75%</span></td>'
        "<td class='wrap-cell'>Strict out-of-sample lag variance reduction vs. ZOH on each newly "
        "arrived buffer <em>before</em> training on it. Negative means overfitting or bad lag!</td></tr>"
        f"<tr><td>{lk.fps('mkEOFPF', '.out.overfit_ratio')}</td>"
        '<td><span class="pcg-tag-ok">1.00 – 1.20</span></td>'
        "<td class='wrap-cell'>Ratio <code>rms_pred_oos / rms_pred_insample</code>. Values "
        "<code>&gt; 1.30</code> warn that <code>reglambda</code> is too low or <code>NBtrain</code> "
        "is too short for <code>P*B</code>.</td></tr>"
        f"<tr><td>{lk.fps('mkEOFPF', '.out.oos_rho_d_b0')}</td>"
        '<td><span class="pcg-tag-ok">|&rho;(d)| &lt; 0.08</span></td>'
        "<td class='wrap-cell'>Signed lag-<code>d</code> autocorrelation of Block-0 OOS residual: "
        "<code>&gt; +0.10</code> = under-corrected lag; <code>&lt; &minus;0.10</code> = over-gain / ringing.</td></tr>"
        f"<tr><td>{lk.fps('selflearn', '.out.alpha_l0')} / {lk.fps('selflearn', '.out.alpha_l1')}</td>"
        '<td><span class="pcg-tag-ok">0.00 (null) or 0.2–0.9</span></td>'
        "<td class='wrap-cell'>Causal OOS James-Stein shrinkage gates. Near <code>0.00</code> when "
        "EOF already whitened the loop or under white noise; opens automatically when nonlinear OG "
        "or extra residual structure appears.</td></tr>"
        f"<tr><td>{lk.fps('modalwhite', '.out.alert_flags')}</td>"
        '<td><span class="pcg-tag-ok">0</span></td>'
        "<td class='wrap-cell'>Controller-agnostic bitmask: <code>1</code>=uncorrected lag, "
        "<code>2</code>=high-freq ringing, <code>4</code>=cross-mode coupling left on table, "
        "<code>8</code>=ZPO / DM fightback.</td></tr>"
        f"<tr><td>{lk.fps('modalfilter', '.PF.timeout_cnt')}</td>"
        '<td><span class="pcg-tag-ok">0</span></td>'
        "<td class='wrap-cell'>Frames where <code>modalfilter</code> timed out waiting for "
        "<code>applyARPF</code> / <code>applyEOFPF</code> / <code>selflearn</code>. Must remain 0.</td></tr>"
        "</tbody></table></div>\n"
        "<h3>Symptom &rarr; Root Cause &rarr; Fix Matrix</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Observed Symptom</th><th>Likely Root Cause</th><th>Concrete Parameter Fix</th>"
        "</tr></thead><tbody>"
        "<tr>"
        '<td><span class="pcg-tag-bad">Overfitting</span><br><code>overfit_ratio &gt; 1.3</code> '
        "or <code>var_red_oos_pct &lt; 0</code></td>"
        "<td class='wrap-cell'>Too few independent samples for <code>D = P * B</code>, or "
        "<code>reglambda</code> too small for current SNR.</td>"
        "<td class='wrap-cell'>Increase <code>reglambda</code> (e.g., 3–10&times;), reduce "
        "<code>blocksize</code> (128 &rarr; 64) or <code>PForder</code>, increase "
        "<code>minsamples</code> (<code>N/D &ge; 10</code>), or enable "
        "<code>gram_halflife</code> / <code>EOF/WIND</code>.</td>"
        "</tr>"
        "<tr>"
        '<td><span class="pcg-tag-bad">Ringing</span><br><code>alert_flags &amp; 2</code>, '
        "<code>rho_d_b0 &lt; -0.1</code>, Stage-2 HF bursts</td>"
        "<td class='wrap-cell'>Regularization too weak on lower-SNR Stage-2 modes, "
        "<code>maxnorm2</code> too loose, or <code>zoh_ridge=ON</code> on Stage-2 high-pass residuals.</td>"
        "<td class='wrap-cell'>Raise Stage-2 <code>reglambda</code> to <code>1e-2</code>, set "
        "<code>zoh_ridge=OFF</code> on Stage 2, lower <code>maxnorm2</code> toward <code>1.35</code>, "
        "or raise <code>CACAO_PF_MGAIN_EXP</code> (0.5 &rarr; 0.7) to roll off high-order mix.</td>"
        "</tr>"
        "<tr>"
        '<td><span class="pcg-tag-warn">Cold-Start Petal Slip</span><br>1 &lambda; island jump '
        "in first 1–2 s</td>"
        "<td class='wrap-cell'>High-order AR(32/64) activated at <code>N=256</code> (starved), OR "
        "<code>minsamples</code> waited too long in integrator mode before locking.</td>"
        "<td class='wrap-cell'>Use <code>AR(16)</code> with <code>minsamples=256</code>, or use "
        "<code>mkEOFPF</code> with default <code>diagorder=16</code> / "
        "<code>diagminsamples=256</code> bootstrap (and <code>EOF/WIND</code> if available).</td>"
        "</tr>"
        "<tr>"
        '<td><span class="pcg-tag-warn">Lag Remains</span><br><code>alert_flags &amp; 1</code>, '
        "<code>rho_d_b0 &gt; +0.1</code></td>"
        "<td class='wrap-cell'><code>PFlatency</code> underestimates true delay, PSOL "
        "<code>WFSfact</code> / optical gain is mismatched, or <code>PF.mixcoeff</code> is low.</td>"
        "<td class='wrap-cell'>Re-check <code>testOL</code> latency and set <code>PFlatency</code> "
        "to match; verify live <code>mWFSfact = 1/g_opt</code>; verify <code>PF.mixcoeff=0.90</code> "
        "and <code>zoh_ridge=ON</code> on Stage 1.</td>"
        "</tr>"
        "<tr>"
        '<td><span class="pcg-tag-warn">Cross-Mode Residual</span><br><code>alert_flags &amp; 4</code>, '
        "high <code>Q_xmode_b0</code></td>"
        "<td class='wrap-cell'>Running diagonal <code>AR(P)</code> (<code>B=1</code>) under strong "
        "frozen-flow wind, or <code>blocksize</code> too small for spatial advection coupling.</td>"
        "<td class='wrap-cell'>Switch from <code>mkARPF</code> to <code>mkEOFPF</code> with "
        "<code>blocksize=64</code> or <code>128</code>, <code>PForder=8</code>.</td>"
        "</tr>"
        "<tr>"
        '<td><span class="pcg-tag-bad">ZPO Fightback</span><br><code>alert_flags &amp; 8</code>, '
        "high <code>Q_wu_lo20</code></td>"
        "<td class='wrap-cell'>Stage-2 WFS zero-point offset (<code>wfszpo</code>) is unscaled "
        "when on-sky PyWFS optical gain drops below 1.</td>"
        f"<td class='wrap-cell'>Enable {lk.algo('2wfs-live', '2WFS/LIVE', 'online_calib')} / "
        f"{lk.algo('zpo', 'ZPO/OG')} so <code>acquWFS-2.WFSzpogain = 0.95 * g_opt</code> tracks "
        "live optical gain.</td>"
        "</tr>"
        "<tr>"
        '<td><span class="pcg-tag-warn">SL Gates = 0.00</span><br><code>alpha_l0/l1 &approx; 0</code></td>'
        "<td class='wrap-cell'>Either EOF is already near-optimal (good! safety gate is doing its "
        "job), or <code>selflearn.latency</code> mismatches loop delay, or <code>nl_mode=0</code> "
        "on an unmodulated PyWFS.</td>"
        "<td class='wrap-cell'>First verify <code>selflearn.latency</code> matches "
        "<code>PFlatency</code> and <code>inbasePF</code> is live. On unmodulated PyWFS, set "
        "<code>nl_mode=1</code> and <code>key_mode=0</code>. If <code>oos_vr_tot_pct &le; 0</code> "
        "persists, leave gates closed&mdash;there is no extra predictable signal to exploit.</td>"
        "</tr>"
        "<tr>"
        '<td><span class="pcg-tag-bad">RT Timeouts</span><br><code>PF.timeout_cnt &gt; 0</code></td>'
        "<td class='wrap-cell'><code>applyEOFPF</code> + <code>selflearn</code> exceeded "
        "<code>PF.maxwaitus</code>, or background <code>mkEOFPF</code> threads contended with RT "
        "cores.</td>"
        "<td class='wrap-cell'>Pin RT processes to isolated cores, lower "
        "<code>CACAO_PF_MKTHREADS</code>, set <code>applyEOFPF.nthreads=4</code>, reduce "
        "<code>selflearn.NBmodeMax</code> (256 &rarr; 128), and confirm "
        "<code>PF.maxwaitus &ge; 2000–3000</code>.</td>"
        "</tr>"
        "</tbody></table></div>"
    )


def _render_sec9_references(lk: _GuideLinker) -> str:
    return (
        '<h2 id="deep-dives">9. Supporting Benchmark Reports, Algorithm Specs &amp; Source Map '
        f'{render_section_badges(["analysis"])}</h2>\n'
        '<div class="subpage-grid">'
        '<a class="subpage-card" href="../algorithms/index.html">'
        "<div><h3>Interactive AO Algorithmic Options Map</h3>"
        "<p>Explore valid combinations, live constraints, and full dependency traces across all "
        "calibration, predictive control, and actuation layers.</p></div>"
        '<span class="subpage-cta">Open Algorithms Matrix &rarr;</span></a>'
        '<a class="subpage-card" href="../reference/index.html">'
        "<div><h3>Full FPS, CLI &amp; Environment Reference</h3>"
        "<p>Search every introspected FPS parameter for <code>mkARPF</code>, "
        "<code>applyARPF</code>, <code>mkEOFPF</code>, <code>applyEOFPF</code>, "
        "<code>selflearn</code>, <code>modalfilter</code>, and <code>modalwhite</code>.</p></div>"
        '<span class="subpage-cta">Open Options Reference &rarr;</span></a>'
        '<a class="subpage-card" href="../topics/wavefront-control/index.html">'
        "<div><h3>Wavefront Control Topic Hub</h3>"
        "<p>Browse all staged closed-loop simulations comparing Modal Integrator, AR(4..64), "
        "Block-EOF, and multi-rate configurations side by side.</p></div>"
        '<span class="subpage-cta">Open Topic Hub &rarr;</span></a>'
        "</div>\n"
        "<h3>Related Technical Studies &amp; Specifications</h3>\n"
        "<ul>\n"
        f"<li>{lk.report('predictive_control_report', 'Predictive Control Study Report')}: "
        "Controlled HIL sweep of Diagonal AR(4..64) &amp; Cross-Mode Block-EOF(B=64/128, P=8) "
        "on Subaru AO3k + SCExAO + Lyot Coronagraph.</li>\n"
        f"<li>{lk.report('control_architecture_synthesis', 'Control Architecture & Benchmark Synthesis')}: "
        "7-regime multi-controller shootout, 40 nm pure white-noise null safety test, mid-run "
        "basis swaps, and faint-star m=10 live GPU multi-rate shootout.</li>\n"
        f"<li>{lk.report('control_implementation_plan', 'Unified Control Implementation Plan')}: "
        "Cross-repository C / SHM engineering roadmap across <code>milk</code>, "
        "<code>cacao</code>, and <code>milk-mltools</code>.</li>\n"
        f"<li><strong>Algorithm Spec Cards:</strong> "
        f"{lk.algo('psol', 'PSOL')} &middot; "
        f"{lk.algo('pf-ar', 'PF/AR')} &middot; "
        f"{lk.algo('eof', 'EOF')} &middot; "
        f"{lk.algo('selflearn', 'SELFLEARN')} &middot; "
        f"{lk.algo('mrdm', 'MRDM')} &middot; "
        f"{lk.algo('wind', 'WIND', 'online_calib')} &middot; "
        f"{lk.algo('white', 'WHITE', 'analysis')}</li>\n"
        "<li><strong>C Implementation Sources (<code>cacao</code>):</strong> "
        "<code>AOloopControl/modalfilter.c</code>, "
        "<code>AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_mkARPF.c</code>, "
        "<code>_applyARPF.c</code>, <code>_mkEOFPF.c</code>, <code>_applyEOFPF.c</code>, "
        "<code>eoflin_phys.c</code>, <code>_selflearn.c</code>, <code>selflearn_core.c</code>, "
        "and <code>AOloopControl/modalwhite.c</code>.</li>\n"
        "</ul>"
    )


def build_predictive_control_guide_html(
    hierarchy: dict[str, object],
    options_catalog: dict[str, object] | None = None,
) -> str:
    """Render /predictive-control/index.html practical guide covering AR, Block-EOF & Self-Learning."""
    lk = _GuideLinker(hierarchy, options_catalog)

    body_html = "\n\n".join(
        [
            _render_hero_and_toc(lk),
            _render_sec1_motivation_and_psol(lk),
            _render_sec2_ladder(lk),
            _render_sec3_ar(lk),
            _render_sec4_eof(lk),
            _render_sec5_selflearn(lk),
            _render_sec6_setup_workflow(lk),
            _render_sec7_presets(lk),
            _render_sec8_troubleshooting(lk),
            _render_sec9_references(lk),
        ]
    )
    toc_items = extract_toc_items(body_html)

    return render_page_shell(
        title="CACAO Predictive Control Guide (AR, Block-EOF & Self-Learning) · cacao-work",
        rel_root="..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="predictive_control",
        active_domain="wavefront-control",
        active_slug="__predictive_control__",
        page_kind="predictive_control",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Wavefront Control", "../topics/wavefront-control/index.html"),
            ("Predictive Control Guide", None),
        ],
        show_sidebar=True,
        toc_items=toc_items,
        has_mermaid=True,
        footer_right="Practical CACAO Predictive Control Guide · AR(P), Block-EOF & Cascaded Self-Learning",
    )
