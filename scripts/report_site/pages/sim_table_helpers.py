#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Row formatting and filter-panel helpers for the Simulation Matrix table."""

from __future__ import annotations

import html

from ..extractors.params import TRACKED_PARAMS
from .fragments import render_domain_badge


def format_param_pill(
    key: str,
    label: str,
    val: str,
    is_diff: bool,
    cmp_d: dict[str, object] | None,
) -> str:
    """Format a single parameter key=value pill for the Simulation table."""
    lbl_esc = html.escape(label, quote=False)
    val_esc = html.escape(val, quote=False)
    cls = "param-pill param-pill-diff" if is_diff else "param-pill"

    if key == "control_law":
        v_html = f"<strong>{val_esc}</strong>" if val.startswith("PSOL ") else val_esc
        return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'
    if key == "llowfs":
        if val == "CLOSED":
            dm3 = float((cmp_d or {}).get("dm3_rms_nm") or 0.0)
            extra = f" (<code>{dm3:.1f} nm</code>)" if dm3 > 0.0 else ""
            v_html = f"<strong>CLOSED</strong>{extra}"
        else:
            v_html = "OPEN (<code>--no-lowfs</code>)"
        return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'
    if key == "calib_2wfs1dm":
        if val.startswith("ON"):
            rest = val[2:].strip()
            extra = f" <code>{html.escape(rest, quote=False)}</code>" if rest else ""
            v_html = f"<strong>ON</strong>{extra}"
        else:
            v_html = val_esc
        return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'

    v_html = f"<strong><code>{val_esc}</code></strong>" if is_diff else f"<code>{val_esc}</code>"
    return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'


def sim_filter_attrs(
    meta: dict[str, object],
    pd: dict[str, str],
    domain_id: str,
) -> dict[str, str]:
    """Return structured category filter attributes for a simulation row."""
    cmp_d = meta.get("comparison") if isinstance(meta.get("comparison"), dict) else {}
    ctrl_law = pd.get("control_law", "")
    if "Block-EOF" in ctrl_law or str(cmp_d.get("pf_mode", "")).lower() == "eof":
        ctrl = "eof"
    elif ctrl_law.startswith("PSOL ") or cmp_d.get("predictive_enabled"):
        ctrl = "ar"
    else:
        ctrl = "integrator"

    if pd.get("llowfs") == "OPEN" or cmp_d.get("llowfs_closed") is False:
        llowfs = "off"
    elif pd.get("llowfs") == "CLOSED" or cmp_d.get("llowfs_closed") is True:
        llowfs = "on"
    else:
        llowfs = "unknown"

    c2d_on = (
        pd.get("calib_2wfs1dm", "").startswith("ON")
        or bool(cmp_d.get("calib_2wfs1dm_enabled"))
    )
    return {
        "domain": domain_id,
        "ctrl": ctrl,
        "llowfs": llowfs,
        "calib2wfs": "on" if c2d_on else "off",
    }


def render_tristate_toggle(
    key: str,
    on_cnt: int,
    off_cnt: int,
    on_tip: str,
    off_tip: str,
) -> str:
    """Render an Any / On / Off tri-state segmented toggle group."""
    return (
        f'<div class="tristate" role="group" data-sim-tri="{html.escape(key, quote=True)}">'
        '<button type="button" class="tristate-btn active" data-val="any" '
        'aria-pressed="true">Any</button>'
        f'<button type="button" class="tristate-btn" data-val="on" aria-pressed="false" '
        f'title="{html.escape(on_tip, quote=True)}">On ({on_cnt})</button>'
        f'<button type="button" class="tristate-btn" data-val="off" aria-pressed="false" '
        f'title="{html.escape(off_tip, quote=True)}">Off ({off_cnt})</button>'
        "</div>"
    )


def build_sim_table_headers(cols: dict[str, bool]) -> list[str]:
    """Return ordered <th> cells for active comparison columns."""
    hdr_cells = [
        '<th data-nosort="1" style="text-align: center;">Cmp</th>',
        '<th style="text-align: left;">Simulation &amp; Sub-Pages</th>',
        '<th style="text-align: left;">Domain</th>',
        '<th style="text-align: left;">Changed Parameters</th>',
    ]
    if cols["s1wfe"]:
        hdr_cells.append('<th style="text-align: right;">Post-AO3k WFE</th>')
    if cols["wfe"]:
        hdr_cells.append('<th style="text-align: right;">Post-SCExAO WFE</th>')
    if cols["vsr"]:
        hdr_cells.append('<th style="text-align: right;">Vis 0.75 um SR</th>')
    if cols["nsr"]:
        hdr_cells.append('<th style="text-align: right;">H 1.65 um SR</th>')
    if cols["coro"]:
        hdr_cells.extend(
            [
                '<th style="text-align: right;">Coro Leakage</th>',
                '<th style="text-align: right;">Planet 3-10 l/D</th>',
                '<th style="text-align: right;">5-sig @ 5 l/D</th>',
            ]
        )
    if cols["c2d"]:
        hdr_cells.append('<th style="text-align: right;">2-WFS/1-DM Calib</th>')
    hdr_cells.append('<th style="text-align: left;">Tech Reports</th>')
    return hdr_cells


def _render_param_cell(
    row_idx: int,
    n_runs: int,
    pd: dict[str, str],
    c: dict[str, object],
    changed_specs: list[tuple[str, str]],
    ref_vals: dict[str, str],
    compact_diff_only: bool,
) -> str:
    """Format the Changed Parameters cell HTML for one simulation row."""
    if n_runs == 1:
        pills_out = [
            format_param_pill(k, lbl, pd[k], False, c)
            for k, lbl in TRACKED_PARAMS[:5]
            if k in pd
        ]
        return (
            f'<div class="param-list">{"".join(pills_out)}</div>'
            if pills_out
            else '<span class="muted">&mdash;</span>'
        )
    if not changed_specs:
        return '<span class="muted">Identical parameters</span>'

    pills_out = []
    if compact_diff_only and row_idx == 0:
        pills_out.append('<span class="param-pill param-pill-base">Baseline</span>')
    for pkey, plabel in changed_specs:
        if pkey not in pd:
            continue
        val = pd[pkey]
        is_diff = val != ref_vals.get(pkey)
        if compact_diff_only and row_idx > 0 and not is_diff:
            continue
        pills_out.append(format_param_pill(pkey, plabel, val, is_diff, c))
    if not pills_out:
        pills_out.append('<span class="param-pill param-pill-base">Same as baseline</span>')
    return f'<div class="param-list">{"".join(pills_out)}</div>'


def build_sim_table_row(
    row_idx: int,
    n_runs: int,
    m: dict[str, object],
    pd: dict[str, str],
    rdom: str,
    base: str,
    cols: dict[str, bool],
    changed_specs: list[tuple[str, str]],
    ref_vals: dict[str, str],
    compact_diff_only: bool,
    domain_map: dict[str, dict[str, object]],
    sim_to_techs: dict[str, list[dict[str, object]]],
    cross_set: set[str],
) -> tuple[str, dict[str, str], dict[str, object]]:
    """Build one <tr> HTML string, its filter attributes, and compare payload."""
    mslug = str(m.get("slug", ""))
    mslug_esc = html.escape(mslug, quote=True)
    mslug_lbl = html.escape(mslug, quote=False)
    c = m.get("comparison") if isinstance(m.get("comparison"), dict) else {}
    cmp_payload = {
        k: c.get(k)
        for k in ("stg1_wfe_nm", "wfe_nm", "vis_sr_pct", "nir_sr_pct", "planet_contrast_3_10ld")
        if c.get(k) is not None
    }
    has_cmp = bool(m.get("has_compute_report", False))
    badges = m.get("badges") if isinstance(m.get("badges"), list) else []
    ctrl_pills = [str(b) for b in badges if "PSOL" in str(b) or "CALIB" in str(b)]
    badge_line = "".join(
        f'<span class="metric-pill metric-pill-accent">{html.escape(p)}</span> '
        for p in ctrl_pills
    )
    if mslug in cross_set:
        badge_line += '<span class="metric-pill">Cross-ref</span> '
    rt_lbl = "Runtime" if has_cmp else "Runtime (N/A)"
    sub_links = (
        '<div class="sublinks-row">'
        f'<a href="{base}/{mslug_esc}/index.html">Overview</a>'
        f'<a href="{base}/{mslug_esc}/config.html">Config</a>'
        f'<a href="{base}/{mslug_esc}/optical.html">Optical</a>'
        f'<a href="{base}/{mslug_esc}/runtime.html">{rt_lbl}</a>'
        f'<a href="{base}/{mslug_esc}/how_to_run.html">How to Run</a>'
        "</div>"
    )
    param_cell_html = _render_param_cell(
        row_idx, n_runs, pd, c, changed_specs, ref_vals, compact_diff_only
    )
    f_attrs = sim_filter_attrs(m, pd, rdom)

    row_cells = [
        f'<td style="text-align:center;">'
        f'<input type="checkbox" class="sim-cmp-cb" value="{mslug_esc}" '
        f'aria-label="Compare {mslug_esc}"></td>',
        f'<td>{badge_line}<a href="{base}/{mslug_esc}/index.html">'
        f'<strong><code>{mslug_lbl}</code></strong></a>{sub_links}</td>',
        f"<td>{render_domain_badge(rdom, domain_map, rel_root=base)}</td>",
        f'<td class="param-cell">{param_cell_html}</td>',
    ]
    if cols["s1wfe"]:
        s1_s = (
            f'<code>{float(c["stg1_wfe_nm"]):.1f} nm</code>'
            if c.get("stg1_wfe_nm") is not None
            else "&mdash;"
        )
        row_cells.append(f'<td style="text-align: right;">{s1_s}</td>')
    if cols["wfe"]:
        wfe_s = (
            f'<code>{float(c["wfe_nm"]):.1f} nm</code>'
            if c.get("wfe_nm") is not None
            else "&mdash;"
        )
        row_cells.append(f'<td style="text-align: right;">{wfe_s}</td>')
    if cols["vsr"]:
        vsr_s = (
            f'<code>{float(c["vis_sr_pct"]):.1f}%</code>'
            if c.get("vis_sr_pct") is not None
            else "&mdash;"
        )
        row_cells.append(f'<td style="text-align: right;">{vsr_s}</td>')
    if cols["nsr"]:
        nsr_s = (
            f'<strong><code>{float(c["nir_sr_pct"]):.1f}%</code></strong>'
            if c.get("nir_sr_pct") is not None
            else "&mdash;"
        )
        row_cells.append(f'<td style="text-align: right;">{nsr_s}</td>')
    if cols["coro"]:
        leak_s = (
            f'<code>{float(c["coro_leak_pct"]):.2f}%</code>'
            if c.get("coro_leak_pct") is not None
            else "&mdash;"
        )
        p310_s = (
            f'<code>{float(c["planet_contrast_3_10ld"]):.2e}</code>'
            if c.get("planet_contrast_3_10ld") is not None
            else "&mdash;"
        )
        s5_s = (
            f'<code>{float(c["speckle_5sig_5ld"]):.2e}</code>'
            if c.get("speckle_5sig_5ld") is not None
            else "&mdash;"
        )
        row_cells.extend(
            [
                f'<td style="text-align: right;">{leak_s}</td>',
                f'<td style="text-align: right;">{p310_s}</td>',
                f'<td style="text-align: right;">{s5_s}</td>',
            ]
        )
    if cols["c2d"]:
        if c.get("calib_2wfs1dm_enabled"):
            c2d_parts: list[str] = []
            if c.get("calib_2wfs1dm_mdb_diag") is not None:
                mdb_s = f'<code>Mdb={float(c["calib_2wfs1dm_mdb_diag"]):.2f}</code>'
                if c.get("calib_2wfs1dm_selfrm_err_pct") is not None:
                    mdb_s += f' ({float(c["calib_2wfs1dm_selfrm_err_pct"]):.1f}% selfRM)'
                c2d_parts.append(mdb_s)
            if c.get("calib_2wfs1dm_r2_a") is not None:
                c2d_parts.append(f'<code>R&sup2;_A={float(c["calib_2wfs1dm_r2_a"]):.2f}</code>')
            c2d_cell = ", ".join(c2d_parts) if c2d_parts else "<strong>ON</strong>"
        else:
            c2d_cell = "&mdash;"
        row_cells.append(f'<td style="text-align: right;">{c2d_cell}</td>')

    t_refs = sim_to_techs.get(mslug, [])
    t_cell = (
        '<div class="param-list">'
        + "".join(
            f'<a class="param-pill" href="{base}/{html.escape(str(tm["slug"]), quote=True)}/index.html">'
            f'{html.escape(str(tm.get("nav_label") or tm.get("title") or tm["slug"]), quote=False)}</a>'
            for tm in t_refs
        )
        + "</div>"
        if t_refs
        else '<span class="muted">&mdash;</span>'
    )
    row_cells.append(f'<td class="param-cell">{t_cell}</td>')
    tr_html = (
        f'<tr data-domain="{html.escape(rdom, quote=True)}" '
        f'data-ctrl="{f_attrs["ctrl"]}" '
        f'data-llowfs="{f_attrs["llowfs"]}" '
        f'data-calib2wfs="{f_attrs["calib2wfs"]}">'
        f'{"".join(row_cells)}</tr>'
    )
    return tr_html, f_attrs, cmp_payload


def render_filter_panel(
    *,
    n_runs: int,
    show_domain_filter: bool,
    domains: list[dict[str, object]],
    dom_counts: dict[str, int],
    ctrl_counts: dict[str, int],
    llowfs_counts: dict[str, int],
    c2d_counts: dict[str, int],
) -> str:
    """Render the interactive multi-facet simulation filter & comparison bar."""
    domain_box = ""
    if show_domain_filter:
        dom_btns = "".join(
            f'<button type="button" class="chip-btn active" '
            f'data-sim-domain="{html.escape(str(d["id"]), quote=True)}" aria-pressed="true">'
            f'{html.escape(str(d["short_title"]), quote=False)} '
            f'({dom_counts.get(str(d["id"]), 0)})</button>'
            for d in domains
        )
        domain_box = (
            '<div class="filter-cat-box cat-simulation">'
            '<div class="filter-cat-title"><span class="cat-dot"></span>'
            "Research Domain</div>"
            f'<div class="toolbar-group">{dom_btns}</div></div>\n'
        )

    ctrl_pills_html = "".join(
        f'<button type="button" class="chip-btn cat-pill cat-loop_operation active" '
        f'data-sim-ctrl="{ck}" aria-pressed="true">'
        f'<span class="cat-dot"></span>{clbl} ({ctrl_counts[ck]})</button>'
        for ck, clbl in (("integrator", "Integrator"), ("ar", "PSOL AR"), ("eof", "Block-EOF"))
    )
    llowfs_tri_html = render_tristate_toggle(
        "llowfs",
        llowfs_counts["on"],
        llowfs_counts["off"],
        "Closed-loop Stage-3 LLOWFS",
        "Open-loop Stage-3 LLOWFS (--no-lowfs)",
    )
    c2d_tri_html = render_tristate_toggle(
        "calib2wfs",
        c2d_counts["on"],
        c2d_counts["off"],
        "2-WFS/1-DM telemetry calibration enabled",
        "2-WFS/1-DM telemetry calibration disabled",
    )

    return (
        '<div class="sim-filter-panel">\n'
        '<div class="filter-categories">\n'
        f"{domain_box}"
        '<div class="filter-cat-box cat-loop_operation">'
        '<div class="filter-cat-title"><span class="cat-dot"></span>'
        "Loop Operation &middot; Control Law</div>"
        f'<div class="toolbar-group">{ctrl_pills_html}</div></div>\n'
        '<div class="filter-cat-box cat-loop_operation">'
        '<div class="filter-cat-title"><span class="cat-dot"></span>'
        "Loop Operation &middot; Stage-3 LLOWFS</div>"
        f"{llowfs_tri_html}</div>\n"
        '<div class="filter-cat-box cat-calibration">'
        '<div class="filter-cat-title"><span class="cat-dot"></span>'
        "Calibration &middot; 2-WFS/1-DM</div>"
        f"{c2d_tri_html}</div>\n"
        "</div>\n"
        '<div class="filter-actions-row">\n'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Compare:</span>'
        '<button type="button" class="btn-sm" data-cmp-preset="ar-sweep">AR Sweep</button>'
        '<button type="button" class="btn-sm" data-cmp-preset="eof-vs-ar">EOF vs AR</button>'
        '<button type="button" class="btn-sm" data-cmp-preset="clear">Clear Selection</button>'
        "</div>\n"
        '<div class="toolbar-group">'
        '<input type="search" id="sim-search" class="search-input" '
        'placeholder="Filter simulations...">'
        '<button type="button" class="btn-sm" id="sim-filter-reset">Reset Filters</button>'
        f'<span id="sim-count" class="muted">{n_runs} / {n_runs} simulations</span>'
        "</div>\n</div>\n</div>\n"
    )
