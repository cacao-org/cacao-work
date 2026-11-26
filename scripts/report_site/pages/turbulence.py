#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Default Turbulence & Perturbation Model page (/turbulence/index.html) & per-sim cards."""

from __future__ import annotations

import html
import math

from ..extractors.common import meta_sort_key
from ..extractors.options_catalog import RUNNER_CLI_OPTIONS, make_runner_opt_anchor
from ..extractors.turbulence_model import (
    DEFAULT_DYNWIND_SPEC,
    DEFAULT_PETAL_RMS_NM,
    DEFAULT_PETAL_TAU_S,
    DEFAULT_SEEING_ARCSEC,
    DEFAULT_TEL_DIAM_M,
    DEFAULT_VIB_RMS_NM,
    TURBULENCE_VISUAL_FILES,
    compute_atmosphere_stats,
    compute_petaling_stats,
    compute_vibration_stats,
    get_normalized_layers,
    solve_r0_for_seeing_m,
)
from ..markdown.sim_split import extract_toc_items
from .fragments import kpi_card, render_section_badges, safe_json_embed
from .shell import render_page_shell

_RUNNER_FLAG_SET: set[str] = {str(o["flag"]) for o in RUNNER_CLI_OPTIONS}


def _flag_link(flag: str, rel_root: str) -> str:
    """Return a clickable <code> link into Options Reference when flag is registered."""
    base = rel_root.rstrip("/") or "."
    f_esc = html.escape(flag, quote=False)
    if flag in _RUNNER_FLAG_SET:
        anc = html.escape(make_runner_opt_anchor(flag), quote=True)
        return (
            f'<a class="opt-ref-link" href="{base}/reference/index.html#{anc}">'
            f"<code>{f_esc}</code></a>"
        )
    return f"<code>{f_esc}</code>"


def _format_realized_strip(realized: dict[str, object]) -> str:
    """Format realized closed-loop perturbation telemetry into concise metric pills."""
    if not realized:
        return ""
    pills: list[str] = []
    if (
        realized.get("wind_scale_min") is not None
        and realized.get("wind_scale_max") is not None
    ):
        w_mean = realized.get("wind_scale_mean")
        m_txt = f" (mean {float(w_mean):.2f}x)" if w_mean is not None else ""
        pills.append(
            f'<span class="metric-pill">Wind scale '
            f'{float(realized["wind_scale_min"]):.2f}&ndash;'
            f'{float(realized["wind_scale_max"]):.2f}x{m_txt}</span>'
        )
    if (
        realized.get("wind_deg_min") is not None
        and realized.get("wind_deg_max") is not None
    ):
        pills.append(
            f'<span class="metric-pill">Heading '
            f'{float(realized["wind_deg_min"]):+.1f}&deg;..'
            f'{float(realized["wind_deg_max"]):+.1f}&deg;</span>'
        )
    if realized.get("burst_peak") is not None and float(realized["burst_peak"]) > 0.01:
        b_frac = realized.get("burst_frac_pct")
        bf_txt = f" ({float(b_frac):.0f}% active)" if b_frac is not None else ""
        cn2_m = realized.get("cn2_scale_max")
        cn2_txt = f", Cn2 max {float(cn2_m):.2f}x" if cn2_m is not None else ""
        pills.append(
            f'<span class="metric-pill">Gust peak '
            f'{float(realized["burst_peak"]):.2f}{bf_txt}{cn2_txt}</span>'
        )
    if realized.get("vib_rms_nm_quad") is not None and float(realized["vib_rms_nm_quad"]) > 0.1:
        pills.append(
            f'<span class="metric-pill">Realized Vib '
            f'{float(realized["vib_rms_nm_quad"]):.1f} nm RMS</span>'
        )
    if (
        realized.get("petal_rms_nm_mean") is not None
        and float(realized["petal_rms_nm_mean"]) > 0.1
    ):
        ptv_m = realized.get("petal_ptv_nm_max")
        ptv_txt = f" (max PTV {float(ptv_m):.0f} nm)" if ptv_m is not None else ""
        pills.append(
            f'<span class="metric-pill">Realized Petaling '
            f'{float(realized["petal_rms_nm_mean"]):.0f} nm mean{ptv_txt}</span>'
        )
    if not pills:
        return ""
    return (
        '<div class="turb-realized-strip">'
        '<span class="turb-sub-lbl">Realized telemetry:</span> '
        f'{"".join(pills)}</div>'
    )


def _unchanged_summary(resolved: dict[str, object], changed_keys: set[str]) -> str:
    """List key perturbation components that stayed at default model settings."""
    kept: list[str] = []
    if "seeing" not in changed_keys:
        kept.append(f'Seeing {DEFAULT_SEEING_ARCSEC:.2f}" (7-layer Maunakea)')
    if "wind_speed_scale" not in changed_keys:
        kept.append("Wind speeds 1.0x")
    if "wind_var" not in changed_keys and "wind_var_scale" not in changed_keys:
        kept.append("Wind meandering ON (1.0x)")
    if "wind_burst" not in changed_keys and "wind_burst_scale" not in changed_keys:
        kept.append("Gust bursts ON (1.0x)")
    if "vib_enable" not in changed_keys and "vib_rms_nm" not in changed_keys:
        kept.append(f"Vibrations ON ({DEFAULT_VIB_RMS_NM:.0f} nm)")
    if (
        "petal_enable" not in changed_keys
        and "petal_rms_nm" not in changed_keys
        and "petal_tau_s" not in changed_keys
    ):
        kept.append(
            f"Thermal petaling ON ({DEFAULT_PETAL_RMS_NM:.0f} nm, {DEFAULT_PETAL_TAU_S:.1f} s)"
        )
    if not kept:
        return ""
    return (
        '<div class="turb-kept-strip">'
        '<span class="turb-sub-lbl">Unchanged from default:</span> '
        f'{" &middot; ".join(html.escape(k, quote=False) for k in kept)}</div>'
    )


def _render_detailed_comparison_table(
    turb_profile: dict[str, object],
    rel_root: str,
) -> str:
    """Render full Resolved vs. Default Turbulence & Perturbation comparison table."""
    base = rel_root.rstrip("/") or "."
    res = turb_profile.get("resolved")
    if not isinstance(res, dict):
        return ""
    changes = turb_profile.get("changes")
    chg_by_key: dict[str, dict[str, str]] = {
        str(c["key"]): c
        for c in (changes if isinstance(changes, list) else [])
        if isinstance(c, dict) and c.get("key")
    }

    st_def = compute_atmosphere_stats(DEFAULT_SEEING_ARCSEC, 1.0)
    r0_def = float(st_def["r0_vk_500_cm"])
    tau0_def = float(st_def["bands"][0]["tau0_ms"])  # type: ignore[index]
    veff_def = float(st_def["v_eff_53_mps"])

    seeing = float(res.get("seeing_arcsec", DEFAULT_SEEING_ARCSEC))
    r0_cm = float(res.get("r0_500nm_cm", r0_def))
    v_eff = float(res.get("v_eff_53_mps", veff_def))
    tau0 = float(res.get("tau0_500nm_ms", tau0_def))
    w_spd = float(res.get("wind_speed_scale", 1.0))
    w_var = bool(res.get("wind_var", True))
    w_var_s = float(res.get("wind_var_scale", 1.0))
    w_bst = bool(res.get("wind_burst", True))
    w_bst_s = float(res.get("wind_burst_scale", 1.0))
    vib_on = bool(res.get("vib_enable", True))
    vib_rms = float(res.get("vib_rms_nm", DEFAULT_VIB_RMS_NM))
    pet_on = bool(res.get("petal_enable", True))
    pet_rms = float(res.get("petal_rms_nm", DEFAULT_PETAL_RMS_NM))
    pet_tau = float(res.get("petal_tau_s", DEFAULT_PETAL_TAU_S))
    w_sw_s = float(res.get("wind_switch_sec", 0.0))
    w_sw_d = float(res.get("wind_switch_deg", 60.0))
    boil_m = int(res.get("boil_mode", 0))

    rows_spec: list[tuple[str, str, str, str, str, str | None]] = [
        (
            "Atmospheric Profile & Seeing (0.50 um)",
            f'7-layer Maunakea, {seeing:.2f}" (r0={r0_cm:.1f} cm, tau0={tau0:.2f} ms)',
            f'7-layer Maunakea, {DEFAULT_SEEING_ARCSEC:.2f}" '
            f"(r0={r0_def:.1f} cm, tau0={tau0_def:.2f} ms)",
            "atmosphere-profile",
            "--seeing",
            "seeing" if "seeing" in chg_by_key else None,
        ),
        (
            "Layer Wind Speed Scale",
            f"{w_spd:g}x nominal (v_eff = {v_eff:.1f} m/s)",
            f"1.0x nominal (v_eff = {veff_def:.1f} m/s)",
            "wind-dynamics",
            "--wind-speed-scale",
            "wind_speed_scale" if "wind_speed_scale" in chg_by_key else None,
        ),
        (
            "Wind Meandering (Matern-3/2)",
            f"ON ({w_var_s:g}x)" if w_var else "OFF (stationary wind vectors)",
            "ON (1.0x: BL 22%/22 deg, FA 14%/10 deg)",
            "wind-dynamics",
            "--no-wind-var" if not w_var else "--wind-var-scale",
            "wind_var"
            if "wind_var" in chg_by_key
            else ("wind_var_scale" if "wind_var_scale" in chg_by_key else None),
        ),
        (
            "Wind Gust Bursts & Cn2 Surges",
            f"ON ({w_bst_s:g}x)" if w_bst else "OFF",
            "ON (1.0x: +80-135% speed, +22-36% Cn2)",
            "wind-dynamics",
            "--no-wind-burst" if not w_bst else "--wind-burst-scale",
            "wind_burst"
            if "wind_burst" in chg_by_key
            else ("wind_burst_scale" if "wind_burst_scale" in chg_by_key else None),
        ),
        (
            "Telescope & Bench Vibrations",
            f"ON ({vib_rms:.1f} nm RMS)" if vib_on else "OFF",
            f"ON ({DEFAULT_VIB_RMS_NM:.1f} nm RMS across 14.5-138 Hz)",
            "vibrations-model",
            "--no-vib" if not vib_on else "--vib-rms-nm",
            "vib_enable"
            if "vib_enable" in chg_by_key
            else ("vib_rms_nm" if "vib_rms_nm" in chg_by_key else None),
        ),
        (
            "Thermal Petaling / LWE (4 Islands)",
            f"ON ({pet_rms:.0f} nm RMS, tau={pet_tau:g} s)" if pet_on else "OFF",
            f"ON ({DEFAULT_PETAL_RMS_NM:.0f} nm RMS, tau={DEFAULT_PETAL_TAU_S:.1f} s, 75% piston)",
            "petaling-model",
            "--no-petal" if not pet_on else "--petal-rms-nm",
            "petal_enable"
            if "petal_enable" in chg_by_key
            else (
                "petal_rms_nm"
                if "petal_rms_nm" in chg_by_key
                else ("petal_tau_s" if "petal_tau_s" in chg_by_key else None)
            ),
        ),
        (
            "Live Wind-Direction Step",
            f"ON ({w_sw_d:+.0f} deg @ t={w_sw_s:g} s)" if w_sw_s > 0.0 else "OFF",
            "OFF (0 s)",
            "wind-dynamics",
            "--wind-switch-sec",
            "wind_switch" if "wind_switch" in chg_by_key else None,
        ),
        (
            "Fourier Turbulence Boiling",
            f"AR({abs(boil_m)})" if boil_m != 0 else "OFF (rolling cross-fade)",
            "OFF (rolling cross-fade)",
            "atmosphere-profile",
            "--boil-mode",
            "boil_mode" if "boil_mode" in chg_by_key else None,
        ),
    ]

    trs: list[str] = []
    for label, val_s, def_s, anc, flag, chg_key in rows_spec:
        is_chg = chg_key is not None
        # Special case: petaling can change BOTH rms and tau simultaneously
        notes: list[str] = []
        if chg_key and chg_key in chg_by_key:
            notes.append(chg_by_key[chg_key]["explanation"])
        if label.startswith("Thermal Petaling") and "petal_tau_s" in chg_by_key:
            if chg_key != "petal_tau_s":
                notes.append(chg_by_key["petal_tau_s"]["explanation"])
        row_cls = ' class="turb-row-changed"' if is_chg else ""
        stat_cell = (
            '<span class="turb-status-pill turb-pill-mod">Changed</span> '
            + html.escape("; ".join(notes), quote=False)
            if is_chg
            else '<span class="turb-status-pill turb-pill-def">Default</span>'
        )
        val_html = (
            f'<code class="opt-nondefault">{html.escape(val_s, quote=False)}</code>'
            if is_chg
            else f"<code>{html.escape(val_s, quote=False)}</code>"
        )
        trs.append(
            f"<tr{row_cls}>"
            f'<td><a class="opt-ref-link" href="{base}/turbulence/index.html#{anc}">'
            f"<strong>{html.escape(label, quote=False)}</strong></a></td>"
            f"<td>{val_html}</td>"
            f'<td><span class="muted">{html.escape(def_s, quote=False)}</span></td>'
            f'<td class="wrap-cell">{stat_cell}</td>'
            f"<td>{_flag_link(flag, base)}</td>"
            "</tr>"
        )
    return (
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Component</th><th>This Simulation</th><th>Default Model</th>"
        "<th>Difference vs. Default</th><th>Override Flag</th>"
        f'</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
    )


def render_sim_turbulence_card(
    turb_profile: dict[str, object] | None,
    *,
    rel_root: str = "..",
    compact: bool = False,
    has_perturb_fig: bool = False,
    detailed_table: bool = False,
    heading_id: str = "turbulence-perturbation-model",
) -> str:
    """Render a prominent Turbulence & Perturbation Model card for any simulation page."""
    if not isinstance(turb_profile, dict) or not turb_profile:
        return ""
    base = rel_root.rstrip("/") or "."
    model_href = f"{base}/turbulence/index.html"
    matches_def = bool(turb_profile.get("matches_default"))
    is_legacy = bool(turb_profile.get("is_legacy_stationary"))
    all_off = bool(turb_profile.get("all_perturb_off"))
    changes = turb_profile.get("changes")
    chg_list = [c for c in changes if isinstance(c, dict)] if isinstance(changes, list) else []
    resolved = (
        turb_profile.get("resolved")
        if isinstance(turb_profile.get("resolved"), dict)
        else {}
    )
    realized = (
        turb_profile.get("realized")
        if isinstance(turb_profile.get("realized"), dict)
        else {}
    )

    if matches_def:
        card_cls = "turb-model-card turb-card-default"
        pill_html = '<span class="turb-status-pill turb-pill-def">Matches Default Model</span>'
    elif is_legacy or all_off:
        card_cls = "turb-model-card turb-card-legacy"
        pill_html = (
            '<span class="turb-status-pill turb-pill-legacy">'
            "Modified: Stationary Frozen-Flow (Perturbations OFF)</span>"
        )
    else:
        card_cls = "turb-model-card turb-card-modified"
        n_chg = len(chg_list)
        pill_html = (
            f'<span class="turb-status-pill turb-pill-mod">'
            f'Modified from Default ({n_chg} change{"s" if n_chg != 1 else ""})</span>'
        )

    see_v = float(resolved.get("seeing_arcsec", DEFAULT_SEEING_ARCSEC))
    r0_v = float(resolved.get("r0_500nm_cm", solve_r0_for_seeing_m(DEFAULT_SEEING_ARCSEC, 0.50) * 100.0))
    tau0_v = float(resolved.get("tau0_500nm_ms", 3.46))
    veff_v = float(resolved.get("v_eff_53_mps", 9.7))

    if matches_def:
        lead_html = (
            f"<p>This simulation uses the exact "
            f'<a href="{model_href}"><strong>Default Turbulence &amp; Perturbation Model</strong></a> '
            f'with <strong>no parameter overrides</strong>: 7-layer Maunakea von Karman '
            f'turbulence at <code>{see_v:.2f}"</code> seeing '
            f"(<code>r0={r0_v:.1f} cm</code>, <code>tau0={tau0_v:.2f} ms</code>, "
            f"<code>v_eff={veff_v:.1f} m/s</code>), Matern-3/2 wind meandering &amp; gust bursts "
            f"ON (1.0x), 5-line telescope/bench vibrations ON (<code>{DEFAULT_VIB_RMS_NM:.1f} nm</code> RMS), and "
            f"4-island Subaru thermal petaling ON (<code>{DEFAULT_PETAL_RMS_NM:.0f} nm</code> RMS, "
            f"<code>tau={DEFAULT_PETAL_TAU_S:.1f} s</code>).</p>"
        )
        diff_html = ""
    else:
        if is_legacy:
            lead_html = (
                "<p>This simulation uses the 7-layer Maunakea von Karman atmosphere from the "
                f'<a href="{model_href}"><strong>Default Turbulence &amp; Perturbation Model'
                "</strong></a>, executed in <strong>stationary frozen-flow mode</strong> "
                "(recorded before realistic non-stationary perturbations were enabled by default). "
                "<strong>Changes relative to the default model:</strong></p>"
            )
        else:
            lead_html = (
                "<p>This simulation builds on the "
                f'<a href="{model_href}"><strong>Default Turbulence &amp; Perturbation Model'
                "</strong></a> with the following <strong>explicit parameter changes</strong>:</p>"
            )
        items: list[str] = []
        for chg in chg_list:
            anc = html.escape(str(chg.get("anchor") or "atmosphere-profile"), quote=True)
            lbl = html.escape(str(chg.get("label") or ""), quote=False)
            val = html.escape(str(chg.get("value") or ""), quote=False)
            dflt = html.escape(str(chg.get("default") or ""), quote=False)
            expl = html.escape(str(chg.get("explanation") or ""), quote=False)
            flg = str(chg.get("flag") or "")
            flg_s = f" &middot; {_flag_link(flg, base)}" if flg else ""
            items.append(
                f'<li><a class="opt-ref-link" href="{model_href}#{anc}"><strong>{lbl}</strong></a>: '
                f'<code class="opt-nondefault">{val}</code> '
                f'<span class="muted">(default: {dflt})</span> &mdash; {expl}{flg_s}</li>'
            )
        diff_html = f'<ul class="turb-diff-list">{"".join(items)}</ul>'

    chg_keys = {str(c.get("key") or "") for c in chg_list}
    kept_html = "" if matches_def or compact else _unchanged_summary(resolved, chg_keys)
    realized_html = _format_realized_strip(realized)
    fig_link = ""
    if has_perturb_fig and not compact:
        fig_link = (
            ' <a class="btn-sm lightbox-trigger" href="perturb_summary_2x2.png" '
            'data-caption="Realistic Perturbations: Wind, Vibrations &amp; Thermal Petaling (2x2)">'
            "Run Perturbation Plot &rarr;</a>"
        )

    if compact:
        return (
            f'<div class="{card_cls} turb-card-compact">\n'
            '  <div class="turb-card-hdr">\n'
            f'    <div class="turb-card-title">{pill_html} '
            f'<span class="muted">Baseline: '
            f'<a href="{model_href}">Default Turbulence &amp; Perturbation Model</a></span></div>\n'
            f'    <div class="turb-card-actions">'
            f'<a class="btn-sm" href="{model_href}">Model Spec &amp; Visuals &rarr;</a>'
            "</div>\n"
            "  </div>\n"
            f"  {diff_html if not matches_def else lead_html}\n"
            f"  {realized_html}\n"
            "</div>"
        )

    table_html = _render_detailed_comparison_table(turb_profile, base) if detailed_table else ""
    hdr_block = (
        f'<h2 id="{html.escape(heading_id, quote=True)}">Turbulence &amp; Perturbation Model '
        f'{render_section_badges(["simulation"])}</h2>\n'
    )
    return (
        f"{hdr_block}"
        f'<section class="{card_cls}" aria-label="Turbulence and perturbation model status">\n'
        '  <div class="turb-card-hdr">\n'
        f'    <div class="turb-card-title">{pill_html}</div>\n'
        '    <div class="turb-card-actions">'
        f'<a class="btn-sm" href="{model_href}">Default Model Spec &amp; Visuals &rarr;</a>'
        f"{fig_link}</div>\n"
        "  </div>\n"
        f"  {lead_html}\n"
        f"  {diff_html}\n"
        f"  {kept_html}\n"
        f"  {realized_html}\n"
        f"  {table_html}\n"
        "</section>"
    )


def _render_figure_block(fname: str, caption: str, fig_id: str) -> str:
    f_esc = html.escape(fname, quote=True)
    c_esc = html.escape(caption, quote=False)
    c_attr = html.escape(caption, quote=True)
    return (
        f'<figure class="report-figure" id="{html.escape(fig_id, quote=True)}">\n'
        f'  <a href="{f_esc}" class="lightbox-trigger" data-caption="{c_attr}">\n'
        f'    <img src="{f_esc}" alt="{c_attr}" loading="lazy">\n'
        "  </a>\n"
        f"  <figcaption>{c_esc}</figcaption>\n"
        "</figure>"
    )


def _build_calculator_payload() -> dict[str, object]:
    """Precompute exact von Karman r0(seeing) & OPD lookup grid for turbulence_explorer.js."""
    see_grid = [round(0.20 + 0.05 * i, 2) for i in range(37)]  # 0.20" .. 2.00"
    r0_500_cm: list[float] = []
    opd_vk_nm: list[float] = []
    opd_kolm_nm: list[float] = []
    for s in see_grid:
        st = compute_atmosphere_stats(s, 1.0)
        r0_500_cm.append(round(float(st["r0_vk_500_cm"]), 4))
        opd_vk_nm.append(round(float(st["opd_vk_nm"]), 2))
        opd_kolm_nm.append(round(float(st["opd_kolm_nm"]), 2))
    st_def = compute_atmosphere_stats(DEFAULT_SEEING_ARCSEC, 1.0)
    return {
        "seeing_grid": see_grid,
        "r0_500_cm": r0_500_cm,
        "opd_vk_nm": opd_vk_nm,
        "opd_kolm_nm": opd_kolm_nm,
        "tel_diam_m": DEFAULT_TEL_DIAM_M,
        "v_eff_nom_mps": round(float(st_def["v_eff_53_mps"]), 4),
        "h_eff_m": round(float(st_def["h_eff_53_m"]), 2),
        "defaults": {
            "seeing": DEFAULT_SEEING_ARCSEC,
            "wind_speed_scale": 1.0,
            "wind_var": True,
            "wind_var_scale": 1.0,
            "wind_burst": True,
            "wind_burst_scale": 1.0,
            "vib_enable": True,
            "vib_rms_nm": DEFAULT_VIB_RMS_NM,
            "petal_enable": True,
            "petal_rms_nm": DEFAULT_PETAL_RMS_NM,
            "petal_tau_s": DEFAULT_PETAL_TAU_S,
        },
        "vib_z_shares": [
            round(float(z["share_pct"]) / 100.0, 6)
            for z in compute_vibration_stats(45.0)["zernikes"]  # type: ignore[index]
        ],
    }


def _render_simulations_usage_section(hierarchy: dict[str, object]) -> str:
    """Render auto-generated table of all staged simulations showing default-match or diffs."""
    run_metas = sorted(list(hierarchy.get("run_metas") or []), key=meta_sort_key)
    if not run_metas:
        return (
            '<h2 id="simulations-using-model">Staged Simulations Using This Model</h2>'
            '<p class="muted">No simulation runs are currently staged.</p>'
        )

    n_default = 0
    n_custom = 0
    n_legacy = 0
    rows: list[str] = []
    for rm in run_metas:
        if not isinstance(rm, dict) or not rm.get("slug"):
            continue
        slug = str(rm["slug"])
        slug_esc = html.escape(slug, quote=True)
        tp = rm.get("turbulence_profile")
        if not isinstance(tp, dict):
            continue
        is_def = bool(tp.get("matches_default"))
        is_leg = bool(tp.get("is_legacy_stationary"))
        all_off = bool(tp.get("all_perturb_off"))
        res = tp.get("resolved") if isinstance(tp.get("resolved"), dict) else {}
        chgs = tp.get("changes") if isinstance(tp.get("changes"), list) else []
        realized = tp.get("realized") if isinstance(tp.get("realized"), dict) else {}

        if is_def:
            n_default += 1
            stat_badge = '<span class="turb-status-pill turb-pill-def">Matches Default</span>'
            diff_cell = '<span class="muted">All parameters match default model</span>'
        elif is_leg or all_off:
            n_legacy += 1
            stat_badge = '<span class="turb-status-pill turb-pill-legacy">Stationary (OFF)</span>'
            tags = [str(c.get("label") or "") + ": " + str(c.get("value") or "") for c in chgs if isinstance(c, dict)]
            diff_cell = (
                "<strong>Stationary 7-layer frozen-flow</strong>: "
                + html.escape("; ".join(tags), quote=False)
            )
        else:
            n_custom += 1
            stat_badge = '<span class="turb-status-pill turb-pill-mod">Modified</span>'
            parts = [
                f'<strong>{html.escape(str(c.get("label", "")), quote=False)}</strong>: '
                f'<code class="opt-nondefault">{html.escape(str(c.get("value", "")), quote=False)}</code> '
                f'<span class="muted">({html.escape(str(c.get("explanation", "")), quote=False)})</span>'
                for c in chgs
                if isinstance(c, dict)
            ]
            diff_cell = "<br>".join(parts)

        see_s = f'{float(res.get("seeing_arcsec", DEFAULT_SEEING_ARCSEC)):.2f}"'
        r0_s = f'{float(res.get("r0_500nm_cm", 10.7)):.1f} cm'
        tlm_bits: list[str] = []
        if realized.get("wind_scale_max") is not None:
            tlm_bits.append(f'Wind max {float(realized["wind_scale_max"]):.2f}x')
        if realized.get("vib_rms_nm_quad") is not None:
            tlm_bits.append(f'Vib {float(realized["vib_rms_nm_quad"]):.1f} nm')
        if realized.get("petal_rms_nm_mean") is not None:
            tlm_bits.append(f'Petal {float(realized["petal_rms_nm_mean"]):.0f} nm')
        tlm_cell = (
            f'<code>{html.escape(" · ".join(tlm_bits), quote=False)}</code>'
            if tlm_bits
            else '<span class="muted">&mdash;</span>'
        )
        rows.append(
            "<tr>"
            f'<td><a href="../{slug_esc}/index.html"><strong><code>{html.escape(slug)}</code>'
            "</strong></a>"
            '<div class="sublinks-row">'
            f'<a href="../{slug_esc}/index.html">Overview</a>'
            f'<a href="../{slug_esc}/config.html#turbulence-perturbation-model">Config Diff</a>'
            f'<a href="../{slug_esc}/optical.html">Optical</a>'
            "</div></td>"
            f"<td>{stat_badge}</td>"
            f'<td><code>{see_s}</code> <span class="muted">(r0={r0_s})</span></td>'
            f'<td class="wrap-cell">{diff_cell}</td>'
            f"<td>{tlm_cell}</td>"
            "</tr>"
        )

    return (
        '<h2 id="simulations-using-model">Staged Simulations Using This Model '
        f'{render_section_badges(["simulation", "analysis"])}</h2>\n'
        f"<p>All <strong>{len(rows)}</strong> staged closed-loop simulations reference this "
        "baseline model and report any parameter overrides on their Overview, Configuration, "
        f"and Optical pages ({n_default} exact default, {n_custom} active-perturbation modified, "
        f"{n_legacy} legacy stationary frozen-flow):</p>\n"
        '<div class="table-wrap" data-sortable="1">'
        '<table id="turb-sim-usage-table"><thead><tr>'
        "<th>Simulation</th><th>Model Status</th><th>Seeing / r0</th>"
        "<th>Changes Relative to Default Model</th><th>Realized Telemetry</th>"
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def build_turbulence_model_html(
    hierarchy: dict[str, object],
    options_catalog: dict[str, object] | None = None,
) -> str:
    """Build the dedicated /turbulence/index.html documentation and interactive explorer page."""
    del options_catalog
    layers = get_normalized_layers()
    atm_stats = compute_atmosphere_stats(DEFAULT_SEEING_ARCSEC, 1.0)
    vib_stats = compute_vibration_stats(DEFAULT_VIB_RMS_NM)
    pet_stats = compute_petaling_stats(DEFAULT_PETAL_RMS_NM, DEFAULT_PETAL_TAU_S)
    dyn = DEFAULT_DYNWIND_SPEC
    bands: list[dict[str, object]] = atm_stats["bands"]  # type: ignore[assignment]
    r0_500 = float(atm_stats["r0_vk_500_cm"])
    tau0_500 = float(bands[0]["tau0_ms"])
    fg_500 = float(bands[0]["greenwood_hz"])
    tot_quad_nm = math.sqrt(
        float(atm_stats["opd_vk_nm"]) ** 2 + DEFAULT_PETAL_RMS_NM ** 2 + DEFAULT_VIB_RMS_NM ** 2
    )

    hero_html = (
        '<section class="hero-banner">\n'
        "<h1>Default Atmospheric Turbulence &amp; Perturbation Model</h1>\n"
        "<p>Authoritative reference specification and statistical diagnostics for the default "
        "entrance-pupil disturbance model driving <code>cacaosim</code> + "
        "<code>milkatmturb</code> closed-loop Subaru AO3k + SCExAO simulations. Combines a "
        "<strong>7-layer Maunakea von Karman atmosphere</strong>, "
        "<strong>non-stationary Matern-3/2 wind meandering &amp; gust bursts</strong>, "
        "<strong>5-line AR(2) telescope/bench vibrations</strong>, and "
        "<strong>4-island thermally induced Subaru V-spider petaling (LWE)</strong>. "
        "Every simulation page points here and highlights any modified parameters.</p>\n"
        '<div class="kpi-grid">'
        + kpi_card("Atmospheric Profile", "7 Layers", "Maunakea · 71.4% BL / 28.6% FA")
        + kpi_card(
            "Default Seeing (0.5 um)",
            f'{DEFAULT_SEEING_ARCSEC:.2f}"',
            f"r0 = {r0_500:.1f} cm · L0_eff = 35.0 m",
        )
        + kpi_card(
            "Wind & Coherence",
            f"tau0 = {tau0_500:.2f} ms",
            f"v_eff = 9.7 m/s · fG = {fg_500:.1f} Hz",
        )
        + kpi_card(
            "Mechanical Vibrations",
            f"{DEFAULT_VIB_RMS_NM:.1f} nm RMS",
            "5 AR(2) lines · 14.5-138 Hz",
        )
        + kpi_card(
            "Thermal Petaling (LWE)",
            f"{DEFAULT_PETAL_RMS_NM:.0f} nm RMS",
            f"4 islands · tau = {DEFAULT_PETAL_TAU_S:.1f} s · "
            f'PTV ~{float(pet_stats["expected_ptv_nm"]):.0f} nm',
        )
        + "</div>\n"
        '<div class="hero-actions">'
        '<a class="btn" href="#parameter-calculator">Interactive Scaling Calculator &darr;</a>'
        '<a class="btn btn-secondary" href="#atmosphere-profile">Atmosphere &amp; Stats</a>'
        '<a class="btn btn-secondary" href="#wind-dynamics">Wind Dynamics</a>'
        '<a class="btn btn-secondary" href="#vibrations-model">Vibrations</a>'
        '<a class="btn btn-secondary" href="#petaling-model">Petaling (LWE)</a>'
        '<a class="btn btn-secondary" href="#simulations-using-model">Simulations Matrix</a>'
        "</div>\n"
        "</section>"
    )

    # Interactive Scaling & Override Calculator
    calc_payload = _build_calculator_payload()
    calc_html = (
        '<h2 id="parameter-calculator">Interactive Parameter Scaling &amp; CLI Override Explorer '
        f'{render_section_badges(["simulation"])}</h2>\n'
        '<div class="explorer-panel" id="turb-calc-panel">\n'
        '<p class="muted" style="margin-top:0;">Adjust seeing, wind speed scaling, wind dynamics, '
        "vibrations, or thermal petaling to compute exact von Karman atmospheric statistics and "
        "generate the corresponding <code>run-ao3k-scexao.sh</code> override flags:</p>\n"
        '<div class="turb-calc-grid">\n'
        '  <div class="field-box">'
        '    <label for="tc-seeing">Zenith Seeing @ 0.50 um [arcsec] '
        f'(<span id="tc-seeing-val">{DEFAULT_SEEING_ARCSEC:.2f}"</span>)</label>'
        f'    <input id="tc-seeing" type="range" min="0.25" max="1.60" step="0.05" '
        f'value="{DEFAULT_SEEING_ARCSEC:.2f}">'
        "  </div>\n"
        '  <div class="field-box">'
        '    <label for="tc-wind-scale">Layer Wind Speed Multiplier '
        '(<span id="tc-wind-scale-val">1.00x</span>)</label>'
        '    <input id="tc-wind-scale" type="range" min="0.25" max="3.00" step="0.05" value="1.00">'
        "  </div>\n"
        '  <div class="field-box">'
        '    <label for="tc-vib-rms">Vibration Total RMS [nm] '
        f'(<span id="tc-vib-rms-val">{DEFAULT_VIB_RMS_NM:.0f} nm</span>)</label>'
        f'    <input id="tc-vib-rms" type="range" min="0" max="150" step="5" '
        f'value="{DEFAULT_VIB_RMS_NM:.0f}">'
        "  </div>\n"
        '  <div class="field-box">'
        '    <label for="tc-petal-rms">Thermal Petaling RMS [nm] '
        f'(<span id="tc-petal-rms-val">{DEFAULT_PETAL_RMS_NM:.0f} nm</span>)</label>'
        f'    <input id="tc-petal-rms" type="range" min="0" max="2500" step="10" '
        f'value="{DEFAULT_PETAL_RMS_NM:.0f}">'
        "  </div>\n"
        '  <div class="field-box">'
        '    <label for="tc-petal-tau">Petaling Timescale tau [s] '
        f'(<span id="tc-petal-tau-val">{DEFAULT_PETAL_TAU_S:.1f} s</span>)</label>'
        f'    <input id="tc-petal-tau" type="range" min="0.5" max="15.0" step="0.5" '
        f'value="{DEFAULT_PETAL_TAU_S:.1f}">'
        "  </div>\n"
        '  <div class="field-box">'
        "    <label>Dynamic Perturbation Channels</label>"
        '    <div class="turb-check-grid">'
        '      <label class="field-check-row"><input id="tc-wind-var" type="checkbox" checked>'
        "<span>Wind meandering</span></label>"
        '      <label class="field-check-row"><input id="tc-wind-burst" type="checkbox" checked>'
        "<span>Gust bursts</span></label>"
        '      <label class="field-check-row"><input id="tc-vib-on" type="checkbox" checked>'
        "<span>Vibrations</span></label>"
        '      <label class="field-check-row"><input id="tc-petal-on" type="checkbox" checked>'
        "<span>Petaling (LWE)</span></label>"
        "    </div>"
        "  </div>\n"
        "</div>\n"
        '<div class="turb-calc-outputs" id="tc-outputs">\n'
        '  <div class="turb-stat-box"><span>r0 (0.50 / 1.65 um)</span>'
        f'    <strong id="tc-out-r0">{r0_500:.1f} / {float(bands[3]["r0_cm"]):.1f} cm</strong></div>\n'
        '  <div class="turb-stat-box"><span>v_eff (5/3) &amp; tau0 (0.5 um)</span>'
        f'    <strong id="tc-out-tau0">9.7 m/s &middot; {tau0_500:.2f} ms</strong></div>\n'
        '  <div class="turb-stat-box"><span>Greenwood f_G &amp; theta_0</span>'
        f'    <strong id="tc-out-fg">{fg_500:.1f} Hz &middot; {float(bands[0]["theta0_arcsec"]):.2f}"</strong></div>\n'
        '  <div class="turb-stat-box"><span>Entrance OPD (Atm / Total)</span>'
        f'    <strong id="tc-out-opd">{float(atm_stats["opd_vk_nm"]):.0f} / {tot_quad_nm:.0f} nm</strong></div>\n'
        '  <div class="turb-stat-box"><span>Vib Tip / Tilt / Focus RMS</span>'
        '    <strong id="tc-out-vib">32.5 / 28.9 / 8.3 nm</strong></div>\n'
        '  <div class="turb-stat-box"><span>Petaling Piston / E[PTV] / f_c</span>'
        f'    <strong id="tc-out-petal">{float(pet_stats["piston_rms_nm"]):.0f} / '
        f'{float(pet_stats["expected_ptv_nm"]):.0f} nm &middot; '
        f'{float(pet_stats["corner_hz"]):.3f} Hz</strong></div>\n'
        "</div>\n"
        '<div class="turb-cmd-row">\n'
        '  <div class="turb-cmd-hdr">'
        '    <span id="tc-diff-summary" class="turb-status-pill turb-pill-def">'
        "Matches Default Model</span>"
        '    <div class="toolbar-group">'
        '      <button type="button" class="btn-sm" id="tc-copy-btn">Copy Command</button>'
        '      <button type="button" class="btn-sm" id="tc-reset-btn">Reset to Default</button>'
        "    </div>\n"
        "  </div>\n"
        '  <pre><code id="tc-cli-cmd">./scripts/run-ao3k-scexao.sh</code></pre>\n'
        "</div>\n"
        '<script id="turb-model-data" type="application/json">'
        f"{safe_json_embed(calc_payload)}</script>\n"
        "</div>"
    )

    # Section 1: Atmospheric Profile & Multi-band Statistics
    layer_rows: list[str] = []
    for lay in layers:
        reg_cls = "metric-pill metric-pill-accent" if lay["is_bl"] else "metric-pill"
        layer_rows.append(
            "<tr>"
            f'<td><strong>L{lay["index"]}</strong></td>'
            f'<td><span class="{reg_cls}">{html.escape(str(lay["regime"]), quote=False)}</span></td>'
            f'<td style="text-align:right;"><code>{float(lay["alt_asl_m"]):.0f} m</code></td>'
            f'<td style="text-align:right;"><code>{float(lay["alt_agl_m"]):.0f} m</code></td>'
            f'<td style="text-align:right;"><strong>{float(lay["cn2_pct"]):.2f}%</strong></td>'
            f'<td style="text-align:right;"><code>{float(lay["speed_mps"]):.2f} m/s</code></td>'
            f'<td style="text-align:right;"><code>{float(lay["dir_rad"]):.2f} rad '
            f'({float(lay["dir_deg"]):.1f}&deg;)</code></td>'
            f'<td style="text-align:right;"><code>{float(lay["L0_m"]):.0f} m</code></td>'
            "</tr>"
        )

    band_rows: list[str] = []
    for b in bands:
        band_rows.append(
            "<tr>"
            f'<td><strong>{html.escape(str(b["band"]), quote=False)}</strong></td>'
            f'<td style="text-align:right;"><code>{float(b["lambda_um"]):.2f} um</code></td>'
            f'<td style="text-align:right;"><strong><code>{float(b["r0_cm"]):.2f} cm</code></strong></td>'
            f'<td style="text-align:right;"><code>{float(b["d_over_r0"]):.1f}</code></td>'
            f'<td style="text-align:right;"><code>{float(b["tau0_ms"]):.2f} ms</code></td>'
            f'<td style="text-align:right;"><code>{float(b["greenwood_hz"]):.2f} Hz</code></td>'
            f'<td style="text-align:right;"><code>{float(b["theta0_arcsec"]):.2f}"</code></td>'
            "</tr>"
        )

    atm_sec = (
        '<h2 id="atmosphere-profile">1. Atmospheric Turbulence Profile &amp; Statistics '
        f'{render_section_badges(["simulation"])}</h2>\n'
        "<p>The baseline atmospheric profile is the 7-layer Maunakea summit profile "
        "(<code>h_site = 4215 m</code> ASL, <code>AtmosphericTurbulenceSimul/"
        "atmturb_profile.c</code>) split between four boundary-layer slabs "
        "(<strong>71.35%</strong> of total C<sub>n</sub><sup>2</sup>, outer scale "
        "<code>L0 = 25 m</code>, moving at 6.5&ndash;6.7 m/s along 84&deg;&ndash;101&deg;) and "
        "three free-atmosphere layers (<strong>28.65%</strong> C<sub>n</sub><sup>2</sup>, "
        "<code>L0 = 100 m</code>, dominated by the 12 km ASL jet stream at 22.0 m/s along "
        "178&deg;). The effective C<sub>n</sub><sup>2</sup>-weighted outer scale is "
        f'<code>L0_eff = {float(atm_stats["l0_eff_m"]):.2f} m</code>, mean wind '
        f'<code>v_mean = {float(atm_stats["v_mean_mps"]):.2f} m/s</code>, effective 5/3-moment '
        f'wind <code>v_eff = {float(atm_stats["v_eff_53_mps"]):.2f} m/s</code>, and effective '
        f'turbulence altitude <code>h_eff = {float(atm_stats["h_eff_53_m"]):.0f} m</code> AGL.</p>\n'
        "<p><strong>Exact von Karman seeing solver:</strong> Because finite outer scale "
        "(<code>L0 = 25/100 m</code>) reduces low-order tilt and narrows the long-exposure PSF "
        "relative to Kolmogorov turbulence, <code>atmturb_seeing.c</code> numerically inverts the "
        "exact Hankel-transformed long-exposure OTF so that the simulated 0.50 um PSF FWHM equals "
        f'the requested seeing (at default <code>{DEFAULT_SEEING_ARCSEC:.2f}"</code>, von Karman '
        f'<code>r0 = {r0_500:.2f} cm</code> vs. Kolmogorov <code>'
        f'{float(atm_stats["r0_kolm_500_cm"]):.2f} cm</code>). Across the Subaru '
        f"<code>D = {DEFAULT_TEL_DIAM_M:.2f} m</code> pupil, exact piston-removed OPD RMS is "
        f'<strong><code>{float(atm_stats["opd_vk_nm"]):.0f} nm</code></strong> '
        f'(vs. <code>{float(atm_stats["opd_kolm_nm"]):.0f} nm</code> Kolmogorov; tip/tilt-removed '
        f'<code>{float(atm_stats["opd_tt_removed_nm"]):.0f} nm</code>).</p>\n'
        "<h3>7-Layer Maunakea Vertical Profile (<code>atmturb_profile.c</code>)</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Layer</th><th>Regime</th>"
        '<th style="text-align:right;">Alt ASL</th>'
        '<th style="text-align:right;">Alt AGL</th>'
        '<th style="text-align:right;">Cn2 Share</th>'
        '<th style="text-align:right;">Nominal Wind</th>'
        '<th style="text-align:right;">Heading</th>'
        '<th style="text-align:right;">Outer Scale L0</th>'
        f'</tr></thead><tbody>{"".join(layer_rows)}</tbody></table></div>\n'
        f'<h3>Derived Multi-Band Statistics at Default {DEFAULT_SEEING_ARCSEC:.2f}" '
        "Seeing &amp; Nominal Wind</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Band / Channel</th>"
        '<th style="text-align:right;">Wavelength</th>'
        '<th style="text-align:right;">r0 (von Karman)</th>'
        '<th style="text-align:right;">D / r0 (7.95 m)</th>'
        '<th style="text-align:right;">Coherence tau0</th>'
        '<th style="text-align:right;">Greenwood f_G</th>'
        '<th style="text-align:right;">Isoplanatic theta_0</th>'
        f'</tr></thead><tbody>{"".join(band_rows)}</tbody></table></div>\n'
        "<p><strong>Wavefront synthesis &amp; stepping:</strong> Master screens are synthesized on "
        "<code>1024x1024</code> grids (<code>master_oversample = 2</code>, "
        "<code>lowfreq = 1</code> sub-harmonics), sampled onto the <code>256x256</code> pupil "
        "(<code>0.0331 m/px</code>) using Keys bicubic interpolation (<code>interp = 1</code>) and "
        "variance-preserving quadrature rolling cross-fade (<code>rolling = 1</code>, "
        "<code>boil_mode = 0</code>, <code>fresnel = 0</code>). Outer turbulence ticks advance at "
        "<code>2.0 kHz</code> (<code>dt = 500 us</code>) and are linearly interpolated on GPU "
        "across <code>4x</code> sub-steps to the <code>8.0 kHz</code> (<code>125 us</code>) "
        "polychromatic optical bench clock.</p>\n"
        + _render_figure_block(
            TURBULENCE_VISUAL_FILES[0][0],
            TURBULENCE_VISUAL_FILES[0][1],
            "fig-turb-profile",
        )
        + "\n"
        + _render_figure_block(
            TURBULENCE_VISUAL_FILES[1][0],
            TURBULENCE_VISUAL_FILES[1][1],
            "fig-turb-screens",
        )
    )

    # Section 2: Wind Dynamics
    bg0, bg1 = dyn["burst_first_gap_s"]  # type: ignore[misc]
    g0, g1 = dyn["burst_gap_s"]  # type: ignore[misc]
    r0_b, r1_b = dyn["burst_rise_s"]  # type: ignore[misc]
    d0_b, d1_b = dyn["burst_decay_s"]  # type: ignore[misc]
    bs0, bs1 = dyn["burst_spd_amp"]  # type: ignore[misc]
    bd0, bd1 = dyn["burst_dir_deg"]  # type: ignore[misc]
    bc0, bc1 = dyn["burst_cn2_amp"]  # type: ignore[misc]

    wind_sec = (
        '<h2 id="wind-dynamics">2. Non-Stationary Wind Statistics, Meandering &amp; Gust Bursts '
        f'{render_section_badges(["simulation"])}</h2>\n'
        "<p>Real Maunakea turbulence is non-stationary: both wind vectors and local C<sub>n</sub>"
        "<sup>2</sup> strength evolve continuously over multi-second timescales. Implemented in "
        "<code>AtmosphericTurbulenceSimul/atmturb_dynwind.c</code> and enabled by default "
        f"({_flag_link('--wind-var-scale', '..')} <code>1.0</code>, "
        f"{_flag_link('--wind-burst-scale', '..')} <code>1.0</code>), each layer's screen "
        "translation is integrated along a <strong>phase-continuous</strong> trajectory "
        "<code>dx_k += vx_k(t) * dt</code> so wind shifts never cause artificial phase jumps.</p>\n"
        "<h3>Matern-3/2 Wind Meandering &amp; Asymmetric C<sup>1</sup> Gust Burst Parameters</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Component</th><th>Default State</th><th>Timescale / Cadence</th>"
        "<th>Amplitude &amp; Coupling</th><th>Physical Effect</th>"
        "</tr></thead><tbody>"
        "<tr><td><strong>Boundary Layer Band (h_AGL &le; 2 km)</strong></td>"
        "<td><code>ON (1.0x)</code></td>"
        f'<td><code>tau_s={dyn["bl_spd_tau_s"]} s</code>, <code>tau_d={dyn["bl_dir_tau_s"]} s</code></td>'
        f'<td><code>sigma_log={dyn["bl_spd_sigma_log"]}</code> (~&plusmn;22%), '
        f'<code>sigma_dir=&plusmn;{dyn["bl_dir_sigma_deg"]:.0f}&deg;</code></td>'
        "<td class='wrap-cell'>Smooth C<sup>1</sup> (-40 dB/dec) dome &amp; summit wind drift shared "
        "across L0&ndash;L3 (weight 0.78)</td></tr>"
        "<tr><td><strong>Free Atmosphere Band (h_AGL &gt; 2 km)</strong></td>"
        "<td><code>ON (1.0x)</code></td>"
        f'<td><code>tau_s={dyn["fa_spd_tau_s"]} s</code>, <code>tau_d={dyn["fa_dir_tau_s"]} s</code></td>'
        f'<td><code>sigma_log={dyn["fa_spd_sigma_log"]}</code> (~&plusmn;14%), '
        f'<code>sigma_dir=&plusmn;{dyn["fa_dir_sigma_deg"]:.0f}&deg;</code></td>'
        "<td class='wrap-cell'>Slower jet-stream shear modulation shared across L4&ndash;L6 "
        "(weight 0.78)</td></tr>"
        "<tr><td><strong>Per-Layer Independent Residuals</strong></td>"
        "<td><code>ON (1.0x)</code></td>"
        f'<td>BL <code>{dyn["lay_bl_tau_s"]} s</code> / FA <code>{dyn["lay_fa_tau_s"]} s</code></td>'
        f'<td>BL <code>{dyn["lay_bl_spd_sigma_log"]}/{dyn["lay_bl_dir_sigma_deg"]:.0f}&deg;</code>; '
        f'FA <code>{dyn["lay_fa_spd_sigma_log"]}/{dyn["lay_fa_dir_sigma_deg"]:.0f}&deg;</code> (wt 0.62)</td>'
        "<td class='wrap-cell'>Breaks rigid inter-layer lockstep; combined speed factor clamped to "
        f'<code>[{dyn["speed_clamp_min"]}x, {dyn["speed_clamp_max"]}x]</code></td></tr>'
        "<tr><td><strong>Asymmetric C<sup>1</sup> Gust Bursts</strong></td>"
        "<td><code>ON (1.0x)</code></td>"
        f"<td>1st gap <code>{bg0}&ndash;{bg1} s</code>, next <code>{g0}&ndash;{g1} s</code>; "
        f"rise <code>{r0_b}&ndash;{r1_b} s</code>, decay <code>{d0_b}&ndash;{d1_b} s</code></td>"
        f"<td>Speed <code>+{bs0:.2f}&ndash;{bs1:.2f}x</code> (0.35x FA), "
        f"dir <code>&plusmn;{bd0:.0f}&ndash;{bd1:.0f}&deg;</code>, "
        f"Cn2 <code>+{bc0*100:.0f}&ndash;{bc1*100:.0f}%</code> (0.20x FA)</td>"
        "<td class='wrap-cell'>Half-cosine onset + <code>exp(-1.2u) cos^2(pi u / 2)</code> tail; "
        "active ~28% of time, driving transient tau0 drops and predictor adaptation tests</td></tr>"
        "<tr><td><strong>Live Wind-Direction Step (Optional)</strong></td>"
        "<td><code>OFF (0 s)</code></td>"
        f"<td>Trigger via {_flag_link('--wind-switch-sec', '..')}</td>"
        f"<td>Rotation angle via {_flag_link('--wind-switch-deg', '..')} (default 60&deg;)</td>"
        "<td class='wrap-cell'>Deterministic phase-continuous heading rotation step for "
        "<code>windlayers</code> / EOF regime-switch benchmarks</td></tr>"
        "</tbody></table></div>\n"
        + _render_figure_block(
            TURBULENCE_VISUAL_FILES[2][0],
            TURBULENCE_VISUAL_FILES[2][1],
            "fig-turb-wind",
        )
    )

    # Section 3: Vibrations
    vib_line_rows: list[str] = []
    for ln in vib_stats["lines"]:  # type: ignore[union-attr]
        zw = ln["z_wt"]
        zw_s = ", ".join(
            f"Z{i+2}={float(zw[i]):+.2f}" for i in range(5) if abs(float(zw[i])) > 1e-4
        )
        vib_line_rows.append(
            "<tr>"
            f'<td><strong>Line {ln["index"]}</strong></td>'
            f'<td style="text-align:right;"><strong><code>{float(ln["f0_hz"]):.1f} Hz</code></strong></td>'
            f'<td style="text-align:right;"><code>{float(ln["zeta"]):.3f}</code></td>'
            f'<td style="text-align:right;"><code>{float(ln["q_factor"]):.1f}</code></td>'
            f'<td style="text-align:right;"><code>{float(ln["fwhm_hz"]):.2f} Hz</code></td>'
            f'<td style="text-align:right;"><code>{float(ln["share_pct"]):.0f}%</code></td>'
            f'<td style="text-align:right;"><strong><code>{float(ln["rms_nm"]):.1f} nm</code></strong></td>'
            f"<td><code>{html.escape(zw_s, quote=False)}</code></td>"
            f'<td class="wrap-cell">{html.escape(str(ln["source"]), quote=False)}</td>'
            "</tr>"
        )
    vib_z_rows = "".join(
        f'<tr><td><strong>{html.escape(str(z["mode"]), quote=False)}</strong></td>'
        f'<td style="text-align:right;"><code>{float(z["share_pct"]):.2f}%</code></td>'
        f'<td style="text-align:right;"><strong><code>{float(z["rms_nm"]):.2f} nm</code></strong></td></tr>'
        for z in vib_stats["zernikes"]  # type: ignore[union-attr]
    )

    vib_sec = (
        '<h2 id="vibrations-model">3. Telescope &amp; Optical-Bench Vibrations '
        f'{render_section_badges(["simulation"])}</h2>\n'
        "<p>Implemented in <code>cacaosim/src/common/cacaosim_perturb.c</code> and enabled by "
        f"default ({_flag_link('--vib-rms-nm', '..')} <code>45.0</code>), mechanical vibrations "
        "are synthesized as five independent, exact stationary discrete-time <code>AR(2)</code> "
        "damped harmonic resonators sampled at the 2 kHz outer clock (and interpolated across "
        "internal 8 kHz sub-steps). Each line's unit-variance process "
        "<code>x[n] = a1 x[n-1] + a2 x[n-2] + b g[n]</code> (primed with its exact stationary "
        "lag-1 correlation <code>rho1 = a1 / (1 - a2)</code>) drives a unit-norm coupling vector "
        "across five Gram-Schmidt pupil-orthonormalized low-order Zernike modes "
        "(<code>Z2..Z6</code>) on the actual Subaru V-spider pupil.</p>\n"
        "<h3>5-Line AR(2) Resonator Bank (Default Total RMS = 45.0 nm)</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Line</th>"
        '<th style="text-align:right;">f0</th>'
        '<th style="text-align:right;">Damping zeta</th>'
        '<th style="text-align:right;">Q Factor</th>'
        '<th style="text-align:right;">FWHM</th>'
        '<th style="text-align:right;">Var Share</th>'
        '<th style="text-align:right;">Line RMS</th>'
        "<th>Zernike Coupling</th><th>Physical Origin</th>"
        f'</tr></thead><tbody>{"".join(vib_line_rows)}</tbody></table></div>\n'
        "<h3>Stationary Per-Zernike OPD RMS Breakdown (Quadrature Sum = 45.0 nm)</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Orthonormal Pupil Mode</th>"
        '<th style="text-align:right;">Variance Share</th>'
        '<th style="text-align:right;">Stationary OPD RMS</th>'
        f"</tr></thead><tbody>{vib_z_rows}</tbody></table></div>\n"
        + _render_figure_block(
            TURBULENCE_VISUAL_FILES[3][0],
            TURBULENCE_VISUAL_FILES[3][1],
            "fig-turb-vibrations",
        )
    )

    # Section 4: Thermal Petaling / LWE
    pet_sec = (
        '<h2 id="petaling-model">4. Thermally Induced Petaling / Low-Wind Effect (LWE) '
        f'{render_section_badges(["simulation"])}</h2>\n'
        "<p>Radiative cooling of the Subaru telescope's thick Nasmyth-IR V-spiders creates "
        "differential air-temperature gradients across the four disjoint pupil segments, "
        "producing discontinuous piston and local tip/tilt steps (Low-Wind Effect / petaling) "
        "that are poorly sensed by standard Pyramid WFS slopes and split the coronagraphic core. "
        "Implemented in <code>cacaosim/src/common/cacaosim_perturb.c</code> and enabled by "
        f"default ({_flag_link('--petal-rms-nm', '..')} <code>{DEFAULT_PETAL_RMS_NM:.1f}</code>, "
        f"{_flag_link('--petal-tau-s', '..')} <code>{DEFAULT_PETAL_TAU_S:.1f}</code>), the simulator automatically "
        "discovers the 4 disconnected pupil islands via 4-connected BFS (East 22.2%, North 27.8%, "
        "West 22.2%, South 27.8%) and evolves each island's differential piston and local "
        "tip/tilt using independent exact Matern-3/2 processes.</p>\n"
        "<h3>Default Thermal Petaling / LWE Statistical Budget</h3>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Parameter / Statistic</th><th>Default Value</th><th>Formula / Notes</th>"
        "</tr></thead><tbody>"
        "<tr><td><strong>Pupil Island Segmentation</strong></td>"
        "<td><code>4 islands</code> (BFS)</td>"
        "<td class='wrap-cell'>East (22.2%), North (27.8%), West (22.2%), South (27.8%) ordered "
        "counter-clockwise by centroid azimuth</td></tr>"
        "<tr><td><strong>Total Petaling OPD RMS</strong></td>"
        f'<td><strong><code>{float(pet_stats["total_rms_nm"]):.1f} nm</code></strong></td>'
        "<td class='wrap-cell'>Area-weighted quadrature sum over differential island pistons + "
        "local island tip/tilt</td></tr>"
        "<tr><td><strong>Differential Island Piston RMS</strong></td>"
        f'<td><code>{float(pet_stats["piston_rms_nm"]):.1f} nm</code> (75.0% var)</td>'
        "<td class='wrap-cell'>Area-weighted global mean piston removed every step; raw draw "
        f'sigma = <code>{float(pet_stats["per_island_raw_sigma_nm"]):.1f} nm</code></td></tr>'
        "<tr><td><strong>Expected Island Piston PTV</strong></td>"
        f'<td><code>~{float(pet_stats["expected_ptv_nm"]):.0f} nm</code> (mean)</td>'
        "<td class='wrap-cell'>Max&minus;min step across the 4 islands "
        "(<code>E[R_4] = 2.059 * sigma_raw</code>); peaks reach ~1800&ndash;2200 nm</td></tr>"
        "<tr><td><strong>Local Island Tip &amp; Tilt RMS</strong></td>"
        f'<td><code>{float(pet_stats["local_tip_rms_nm"]):.1f} nm</code> each (12.5% + 12.5%)</td>'
        "<td class='wrap-cell'>Unit-RMS local x/y slopes centered on each island centroid</td></tr>"
        "<tr><td><strong>Temporal Correlation (Matern-3/2)</strong></td>"
        f'<td><code>tau = {float(pet_stats["tau_s"]):.1f} s</code> '
        f'(<code>f_c = {float(pet_stats["corner_hz"]):.3f} Hz</code>)</td>'
        "<td class='wrap-cell'>Smooth C<sup>1</sup> evolution with -40 dB/dec PSD rolloff above "
        "<code>f_c = 1 / (2 pi tau)</code>; no white-noise jitter</td></tr>"
        "</tbody></table></div>\n"
        + _render_figure_block(
            TURBULENCE_VISUAL_FILES[4][0],
            TURBULENCE_VISUAL_FILES[4][1],
            "fig-turb-petaling",
        )
    )

    # Section 5: CLI Overrides & Provenance
    override_flags = (
        "--seeing",
        "--no-wind-var",
        "--wind-var-scale",
        "--no-wind-burst",
        "--wind-burst-scale",
        "--no-vib",
        "--vib-rms-nm",
        "--no-petal",
        "--petal-rms-nm",
        "--petal-tau-s",
        "--no-perturb",
        "--wind-switch-sec",
        "--wind-switch-deg",
    )
    opt_by_flag = {str(o["flag"]): o for o in RUNNER_CLI_OPTIONS}
    cli_rows: list[str] = []
    for fl in override_flags:
        om = opt_by_flag.get(fl)
        if not om:
            continue
        cli_rows.append(
            "<tr>"
            f"<td>{_flag_link(fl, '..')} <code>{html.escape(str(om.get('arg') or ''), quote=False)}</code></td>"
            f'<td><code>{html.escape(str(om.get("default") or ""), quote=False)}</code></td>'
            f'<td class="wrap-cell">{html.escape(str(om.get("description") or ""), quote=False)}</td>'
            "</tr>"
        )
    cli_sec = (
        '<h2 id="cli-overrides">5. CLI Override Flags &amp; Source Implementation '
        f'{render_section_badges(["simulation"])}</h2>\n'
        "<p>Override any component when running <code>./scripts/run-ao3k-scexao.sh</code>. "
        "Any non-default choice is recorded in <code>run_options.json</code> and automatically "
        "surfaced as a parameter diff on the generated simulation report:</p>\n"
        '<div class="table-wrap" data-sortable="1">'
        "<table><thead><tr>"
        "<th>Runner Flag (<code>run-ao3k-scexao.sh</code>)</th>"
        "<th>Default</th><th>Effect</th>"
        f'</tr></thead><tbody>{"".join(cli_rows)}</tbody></table></div>\n'
        "<ul>\n"
        "<li><strong>Atmospheric Profile &amp; Seeing Solver</strong>: "
        "<code>AtmosphericTurbulenceSimul/src/AtmosphericTurbulence/atmturb_profile.c</code> &amp; "
        "<code>atmturb_seeing.c</code></li>\n"
        "<li><strong>Non-Stationary Wind Meandering &amp; Gust Bursts</strong>: "
        "<code>AtmosphericTurbulenceSimul/src/AtmosphericTurbulence/atmturb_dynwind.c</code></li>\n"
        "<li><strong>Vibrations &amp; Thermal Petaling (LWE)</strong>: "
        "<code>cacaosim/src/common/cacaosim_perturb.c</code> &amp; "
        "<code>cacaosim/src/pupil/cacaosim_pupil.c</code></li>\n"
        "<li><strong>Bench &amp; Runner Defaults</strong>: "
        "<code>cacao-work/benches/ao3k_scexao/sim-ao3k-scexao.milk</code> &amp; "
        "<code>ao3k_scexao.bench</code></li>\n"
        "</ul>"
    )

    usage_sec = _render_simulations_usage_section(hierarchy)

    body_html = "\n\n".join(
        [hero_html, calc_html, atm_sec, wind_sec, vib_sec, pet_sec, cli_sec, usage_sec]
    )
    toc_items = extract_toc_items(body_html)

    return render_page_shell(
        title="Default Turbulence & Perturbation Model · cacao-work AO Repository",
        rel_root="..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="turbulence",
        page_kind="turbulence",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Simulations", "../simulations/index.html"),
            ("Turbulence & Perturbation Model", None),
        ],
        show_sidebar=True,
        toc_items=toc_items,
        page_scripts=("turbulence_explorer.js",),
        footer_right="Default 7-Layer Maunakea + Dynamic Wind + Vibrations + Petaling Model",
    )
