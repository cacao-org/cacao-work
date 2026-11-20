#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Front Page 2-table builder and site-wide bidirectional cross-link refresher."""

from __future__ import annotations

import html
import json
from pathlib import Path
import re

from . import DEFAULT_REPOS, DEFAULT_RUN_COMMAND
from .assets import COMMON_JS, CSS_STYLES, FRONT_PAGE_JS
from .metrics import (
    TRACKED_PARAMS,
    human_bytes,
    is_tech_report_meta,
    meta_sort_key,
    resolve_run_parameters,
)
from .sim_pages import safe_json_embed


def _format_param_pill(
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


def _sim_filter_attrs(meta: dict[str, object], pd: dict[str, str]) -> dict[str, str]:
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
        "ctrl": ctrl,
        "llowfs": llowfs,
        "calib2wfs": "on" if c2d_on else "off",
    }


def _sim_filter_tags(meta: dict[str, object], pd: dict[str, str]) -> str:
    """Compute space-separated filter tags for Table 2 client-side filtering."""
    attrs = _sim_filter_attrs(meta, pd)
    tags = [attrs["ctrl"]]
    if attrs["llowfs"] == "off":
        tags.append("llowfs_open")
    elif attrs["llowfs"] == "on":
        tags.append("llowfs_closed")
    if attrs["calib2wfs"] == "on":
        tags.append("calib2wfs")
    return " ".join(tags)


def _render_tristate_toggle(
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


def build_front_page_html(metas: list[dict[str, object]]) -> str:
    """Render the 2-table Knowledge Repository Front Page."""
    metas = sorted(metas, key=meta_sort_key)
    study_metas = [m for m in metas if is_tech_report_meta(m)]
    run_metas = [m for m in metas if not is_tech_report_meta(m)]

    sim_slug_set = {str(m.get("slug", "")) for m in run_metas if m.get("slug")}
    sim_to_techs: dict[str, list[tuple[str, str]]] = {s: [] for s in sim_slug_set}
    for tm in study_metas:
        tslug = str(tm.get("slug", ""))
        tlbl = str(tm.get("nav_label") or tm.get("title") or tslug)
        refs = tm.get("referenced_simulations")
        if isinstance(refs, list):
            for r in refs:
                rs = str(r)
                if rs in sim_to_techs:
                    sim_to_techs[rs].append((tslug, tlbl))

    latest_repro: dict[str, object] | None = None
    primary_slug = ""
    for meta in run_metas + study_metas:
        if not primary_slug and not is_tech_report_meta(meta):
            primary_slug = str(meta.get("slug", ""))
        rep = meta.get("reproducibility")
        if isinstance(rep, dict) and rep.get("repositories"):
            latest_repro = rep
            if not is_tech_report_meta(meta):
                primary_slug = str(meta.get("slug", primary_slug))

    repo_by_name: dict[str, dict[str, str]] = {r["name"]: dict(r) for r in DEFAULT_REPOS}
    repo_list: list[dict[str, str]] = [dict(r) for r in DEFAULT_REPOS]
    if latest_repro and isinstance(latest_repro.get("repositories"), list):
        merged_list: list[dict[str, str]] = []
        for item in latest_repro["repositories"]:
            if not isinstance(item, dict) or "name" not in item:
                continue
            rname = str(item["name"])
            base = dict(repo_by_name.get(rname, {}))
            for k in ("name", "url", "branch", "commit", "short_commit", "role"):
                if item.get(k):
                    base[k] = str(item[k])
            repo_by_name[rname] = base
            merged_list.append(base)
        if merged_list:
            repo_list = merged_list

    study_nav_links = [
        f'<a href="./{html.escape(str(m.get("slug", "")), quote=True)}/index.html">'
        f'{html.escape(str(m.get("nav_label") or m.get("title") or ""), quote=False)}</a>'
        for m in study_metas
    ]

    # Table 1: Technical Reports
    t1_rows: list[str] = []
    for meta in study_metas:
        slug = str(meta.get("slug", ""))
        slug_esc = html.escape(slug, quote=True)
        title = str(meta.get("title", slug))
        nav_lbl = str(meta.get("nav_label") or title)
        summary = str(meta.get("summary") or "")
        upd = str(meta.get("updated_utc") or "")
        feats = meta.get("cacao_features") if isinstance(meta.get("cacao_features"), list) else []
        badges = [
            str(b)
            for b in (meta.get("badges") if isinstance(meta.get("badges"), list) else [])
            if str(b) != "FEATURED STUDY"
        ]
        refs = (
            meta.get("referenced_simulations")
            if isinstance(meta.get("referenced_simulations"), list)
            else []
        )
        feat_pills = "".join(
            f'<span class="metric-pill metric-pill-accent">{html.escape(str(f))}</span>'
            for f in feats
        )
        hl_pills = "".join(
            f'<span class="metric-pill">{html.escape(str(b))}</span>'
            for b in badges[:4]
        )
        ref_links = "".join(
            f'<a class="param-pill param-pill-diff" '
            f'href="./{html.escape(str(r), quote=True)}/index.html">'
            f'<code>{html.escape(str(r), quote=False)}</code></a>'
            for r in refs
            if str(r) in sim_slug_set or not sim_slug_set
        )
        t1_rows.append(
            "<tr>"
            f'<td class="wrap-cell">'
            f'<a href="./{slug_esc}/index.html"><strong>{html.escape(title)}</strong></a>'
            f'<br><span class="muted">{html.escape(summary)}</span>'
            f'<div class="sublinks-row">'
            f'<a href="./{slug_esc}/index.html">Read {html.escape(nav_lbl)}</a>'
            f'<a href="./{slug_esc}/index.html#reproducibility-github-provenance">Reproduce</a>'
            "</div></td>"
            f'<td class="param-cell"><div class="param-list">{feat_pills or "&mdash;"}</div></td>'
            f'<td class="param-cell"><div class="param-list">{hl_pills or "&mdash;"}</div></td>'
            f'<td class="param-cell"><div class="param-list">{ref_links or "&mdash;"}</div></td>'
            f'<td style="text-align:right;"><span class="muted">{html.escape(upd)}</span></td>'
            "</tr>"
        )

    tech_table_html = (
        '<h2 id="tech-reports">1. Technical Reports</h2>\n'
        "<p>In-depth engineering analyses, physics studies, and architectural roadmaps linking "
        "directly to supporting closed-loop simulations.</p>\n"
        '<div class="toolbar">'
        f'<span><strong>{len(study_metas)}</strong> Technical Report(s)</span>'
        '<input type="search" id="tech-search" class="search-input" '
        'placeholder="Search technical reports, topics, or capabilities..."></div>\n'
        '<div class="table-wrap" data-sortable="1">'
        '<table id="tech-reports-table"><thead><tr>'
        "<th>Technical Report</th>"
        "<th>CACAO Capabilities</th>"
        "<th>Key Findings</th>"
        "<th>Referenced Simulations</th>"
        '<th style="text-align:right;">Updated</th>'
        "</tr></thead><tbody>"
        + (
            "".join(t1_rows)
            if t1_rows
            else '<tr><td colspan="5" class="muted">No technical reports staged yet.</td></tr>'
        )
        + "</tbody></table></div>"
    )

    # Table 2: Simulation Reports (Unified table with changed-params diff & sub-page links)
    param_dicts = [resolve_run_parameters(m) for m in run_metas]
    changed_specs: list[tuple[str, str]] = []
    shared_items: list[tuple[str, str]] = []
    if len(run_metas) >= 2:
        for pkey, plabel in TRACKED_PARAMS:
            present = [pd[pkey] for pd in param_dicts if pkey in pd]
            if len(set(present)) >= 2:
                changed_specs.append((pkey, plabel))
            elif len(present) == len(run_metas) and len(set(present)) == 1:
                shared_items.append((plabel, present[0]))
    elif len(run_metas) == 1:
        for pkey, plabel in TRACKED_PARAMS:
            if pkey in param_dicts[0]:
                shared_items.append((plabel, param_dicts[0][pkey]))

    ref_vals: dict[str, str] = {}
    for pkey, _ in changed_specs:
        ref_v = param_dicts[0].get(pkey) if param_dicts else None
        if ref_v is None:
            ref_v = next((pd[pkey] for pd in param_dicts if pkey in pd), "")
        ref_vals[pkey] = ref_v

    def has_cmp_key(key: str) -> bool:
        return any(
            isinstance(m.get("comparison"), dict) and m["comparison"].get(key) is not None
            for m in run_metas
        )

    def has_cmp_bool(key: str) -> bool:
        return any(
            isinstance(m.get("comparison"), dict) and bool(m["comparison"].get(key, False))
            for m in run_metas
        )

    has_any_s1wfe = has_cmp_key("stg1_wfe_nm")
    has_any_wfe = has_cmp_key("wfe_nm")
    has_any_vsr = has_cmp_key("vis_sr_pct")
    has_any_nsr = has_cmp_key("nir_sr_pct")
    has_any_coro = has_cmp_bool("has_coro")
    has_any_c2d = has_cmp_bool("calib_2wfs1dm_enabled")

    hdr_cells = [
        '<th data-nosort="1" style="text-align: center;">Cmp</th>',
        '<th style="text-align: left;">Simulation &amp; Sub-Pages</th>',
        '<th style="text-align: left;">Changed Parameters</th>',
    ]
    if has_any_s1wfe:
        hdr_cells.append('<th style="text-align: right;">Post-AO3k WFE</th>')
    if has_any_wfe:
        hdr_cells.append('<th style="text-align: right;">Post-SCExAO WFE</th>')
    if has_any_vsr:
        hdr_cells.append('<th style="text-align: right;">Vis 0.75 um SR</th>')
    if has_any_nsr:
        hdr_cells.append('<th style="text-align: right;">H 1.65 um SR</th>')
    if has_any_coro:
        hdr_cells.extend(
            [
                '<th style="text-align: right;">Coro Leakage</th>',
                '<th style="text-align: right;">Planet 3-10 l/D</th>',
                '<th style="text-align: right;">5-sig @ 5 l/D</th>',
            ]
        )
    if has_any_c2d:
        hdr_cells.append('<th style="text-align: right;">2-WFS/1-DM Calib</th>')
    hdr_cells.append('<th style="text-align: left;">Tech Reports</th>')

    compact_diff_only = len(changed_specs) > 4
    t2_rows: list[str] = []
    cmp_json_map: dict[str, dict[str, object]] = {}
    ctrl_counts = {"integrator": 0, "ar": 0, "eof": 0}
    llowfs_counts = {"on": 0, "off": 0}
    c2d_counts = {"on": 0, "off": 0}
    for row_idx, (m, pd) in enumerate(zip(run_metas, param_dicts)):
        mslug = str(m.get("slug", ""))
        mslug_esc = html.escape(mslug, quote=True)
        mslug_lbl = html.escape(mslug, quote=False)
        c = m.get("comparison") if isinstance(m.get("comparison"), dict) else {}
        cmp_json_map[mslug] = {
            k: c.get(k)
            for k in ("stg1_wfe_nm", "wfe_nm", "vis_sr_pct", "nir_sr_pct", "planet_contrast_3_10ld")
            if c.get(k) is not None
        }
        has_cmp = bool(m.get("has_compute_report", False))
        badges = m.get("badges") if isinstance(m.get("badges"), list) else []
        ctrl_pills = [
            str(b) for b in badges if "PSOL" in str(b) or "CALIB" in str(b)
        ]
        badge_line = "".join(
            f'<span class="metric-pill metric-pill-accent">{html.escape(p)}</span> '
            for p in ctrl_pills
        )
        rt_lbl = "Runtime" if has_cmp else "Runtime (N/A)"
        sub_links = (
            '<div class="sublinks-row">'
            f'<a href="./{mslug_esc}/index.html">Overview</a>'
            f'<a href="./{mslug_esc}/config.html">Config</a>'
            f'<a href="./{mslug_esc}/optical.html">Optical</a>'
            f'<a href="./{mslug_esc}/runtime.html">{rt_lbl}</a>'
            f'<a href="./{mslug_esc}/how_to_run.html">How to Run</a>'
            "</div>"
        )

        if len(run_metas) == 1:
            pills_out = [
                _format_param_pill(k, lbl, pd[k], False, c)
                for k, lbl in TRACKED_PARAMS[:5]
                if k in pd
            ]
            param_cell_html = (
                f'<div class="param-list">{"".join(pills_out)}</div>'
                if pills_out
                else '<span class="muted">&mdash;</span>'
            )
        elif not changed_specs:
            param_cell_html = '<span class="muted">Identical parameters</span>'
        else:
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
                pills_out.append(_format_param_pill(pkey, plabel, val, is_diff, c))
            if not pills_out:
                pills_out.append(
                    '<span class="param-pill param-pill-base">Same as baseline</span>'
                )
            param_cell_html = f'<div class="param-list">{"".join(pills_out)}</div>'

        f_attrs = _sim_filter_attrs(m, pd)
        ctrl_counts[f_attrs["ctrl"]] = ctrl_counts.get(f_attrs["ctrl"], 0) + 1
        if f_attrs["llowfs"] in llowfs_counts:
            llowfs_counts[f_attrs["llowfs"]] += 1
        c2d_counts[f_attrs["calib2wfs"]] = c2d_counts.get(f_attrs["calib2wfs"], 0) + 1
        tags_attr = html.escape(_sim_filter_tags(m, pd), quote=True)
        row_cells = [
            f'<td style="text-align:center;">'
            f'<input type="checkbox" class="sim-cmp-cb" value="{mslug_esc}" '
            f'aria-label="Compare {mslug_esc}"></td>',
            f'<td>{badge_line}<a href="./{mslug_esc}/index.html">'
            f'<strong><code>{mslug_lbl}</code></strong></a>{sub_links}</td>',
            f'<td class="param-cell">{param_cell_html}</td>',
        ]
        if has_any_s1wfe:
            s1_s = (
                f'<code>{float(c["stg1_wfe_nm"]):.1f} nm</code>'
                if c.get("stg1_wfe_nm") is not None
                else "&mdash;"
            )
            row_cells.append(f'<td style="text-align: right;">{s1_s}</td>')
        if has_any_wfe:
            wfe_s = (
                f'<code>{float(c["wfe_nm"]):.1f} nm</code>'
                if c.get("wfe_nm") is not None
                else "&mdash;"
            )
            row_cells.append(f'<td style="text-align: right;">{wfe_s}</td>')
        if has_any_vsr:
            vsr_s = (
                f'<code>{float(c["vis_sr_pct"]):.1f}%</code>'
                if c.get("vis_sr_pct") is not None
                else "&mdash;"
            )
            row_cells.append(f'<td style="text-align: right;">{vsr_s}</td>')
        if has_any_nsr:
            nsr_s = (
                f'<strong><code>{float(c["nir_sr_pct"]):.1f}%</code></strong>'
                if c.get("nir_sr_pct") is not None
                else "&mdash;"
            )
            row_cells.append(f'<td style="text-align: right;">{nsr_s}</td>')
        if has_any_coro:
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
        if has_any_c2d:
            if c.get("calib_2wfs1dm_enabled"):
                c2d_parts: list[str] = []
                if c.get("calib_2wfs1dm_mdb_diag") is not None:
                    mdb_s = f'<code>Mdb={float(c["calib_2wfs1dm_mdb_diag"]):.2f}</code>'
                    if c.get("calib_2wfs1dm_selfrm_err_pct") is not None:
                        mdb_s += f' ({float(c["calib_2wfs1dm_selfrm_err_pct"]):.1f}% selfRM)'
                    c2d_parts.append(mdb_s)
                if c.get("calib_2wfs1dm_r2_a") is not None:
                    c2d_parts.append(
                        f'<code>R&sup2;_A={float(c["calib_2wfs1dm_r2_a"]):.2f}</code>'
                    )
                c2d_cell = ", ".join(c2d_parts) if c2d_parts else "<strong>ON</strong>"
            else:
                c2d_cell = "&mdash;"
            row_cells.append(f'<td style="text-align: right;">{c2d_cell}</td>')

        t_refs = sim_to_techs.get(mslug, [])
        t_cell = (
            '<div class="param-list">'
            + "".join(
                f'<a class="param-pill" href="./{html.escape(ts, quote=True)}/index.html">'
                f"{html.escape(tl, quote=False)}</a>"
                for ts, tl in t_refs
            )
            + "</div>"
            if t_refs
            else '<span class="muted">&mdash;</span>'
        )
        row_cells.append(f'<td class="param-cell">{t_cell}</td>')
        t2_rows.append(
            f'<tr data-tags="{tags_attr}" '
            f'data-ctrl="{f_attrs["ctrl"]}" '
            f'data-llowfs="{f_attrs["llowfs"]}" '
            f'data-calib2wfs="{f_attrs["calib2wfs"]}">'
            f'{"".join(row_cells)}</tr>'
        )

    shared_strip = ""
    if shared_items and len(run_metas) >= 2:
        shared_html = " &middot; ".join(
            f"{html.escape(lbl, quote=False)}=<code>{html.escape(val, quote=False)}</code>"
            for lbl, val in shared_items
        )
        shared_strip = (
            f'<div class="shared-params"><strong>Shared parameters across all '
            f"{len(run_metas)} runs:</strong> {shared_html}</div>"
        )

    ctrl_pills_html = "".join(
        f'<button type="button" class="chip-btn cat-pill cat-loop_operation active" '
        f'data-sim-ctrl="{ck}" aria-pressed="true">'
        f'<span class="cat-dot"></span>{clbl} ({ctrl_counts[ck]})</button>'
        for ck, clbl in (
            ("integrator", "Integrator"),
            ("ar", "PSOL AR"),
            ("eof", "Block-EOF"),
        )
    )
    llowfs_tri_html = _render_tristate_toggle(
        "llowfs",
        llowfs_counts["on"],
        llowfs_counts["off"],
        "Closed-loop Stage-3 LLOWFS",
        "Open-loop Stage-3 LLOWFS (--no-lowfs)",
    )
    c2d_tri_html = _render_tristate_toggle(
        "calib2wfs",
        c2d_counts["on"],
        c2d_counts["off"],
        "2-WFS/1-DM telemetry calibration enabled",
        "2-WFS/1-DM telemetry calibration disabled",
    )

    sim_table_html = (
        '<h2 id="simulation-reports">2. Simulation Reports</h2>\n'
        "<p>Each simulation exposes 5 dedicated views: <strong>Overview</strong>, "
        "<strong>Configuration</strong>, <strong>Optical Performance</strong>, "
        "<strong>Runtime Performance</strong>, and a user-oriented "
        "<strong>How to Run It</strong> deployment guide. Select rows to compare visually:</p>\n"
        '<div class="sim-filter-panel">\n'
        '<div class="filter-categories">\n'
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
        f'<span id="sim-count" class="muted">{len(run_metas)} / {len(run_metas)} '
        "simulations</span>"
        "</div>\n</div>\n</div>\n"
        '<div id="cmp-drawer" class="cmp-drawer hidden">\n'
        '<div class="toolbar" style="margin-top:0;">'
        "<strong>Interactive Simulation Comparison</strong>"
        '<select id="cmp-metric-select" class="select-input">'
        '<option value="vis_sr_pct">Visible 0.75 um Strehl [%]</option>'
        '<option value="nir_sr_pct">H-Band 1.65 um Strehl [%]</option>'
        '<option value="wfe_nm">Post-SCExAO WFE [nm]</option>'
        '<option value="stg1_wfe_nm">Post-AO3k WFE [nm]</option>'
        '<option value="planet_contrast_3_10ld">Coro Planet Contrast 3-10 l/D</option>'
        "</select></div>\n"
        '<div id="cmp-chart"></div>\n</div>\n'
        '<div class="table-wrap" data-sortable="1">'
        '<table id="sim-reports-table">'
        f'<thead><tr>{"".join(hdr_cells)}</tr></thead>'
        f'<tbody>{"".join(t2_rows)}</tbody></table></div>\n'
        '<div id="sim-empty-msg" class="cat-empty-note hidden">'
        "No simulations match the active filters. Click Reset Filters to show all runs.</div>\n"
        f"{shared_strip}\n"
        '<script id="front-sim-compare-data" type="application/json">'
        f"{safe_json_embed(cmp_json_map)}</script>"
    )

    repo_rows: list[str] = [
        '<div class="table-wrap" data-sortable="1">',
        "<table><thead><tr>"
        '<th style="text-align: left;">Repository</th>'
        '<th style="text-align: center;">Branch</th>'
        '<th style="text-align: center;">Commit</th>'
        '<th style="text-align: left;">Role in Simulation Stack</th>'
        "</tr></thead><tbody>",
    ]
    for r in repo_list:
        rname = html.escape(r.get("name", ""), quote=False)
        rurl = html.escape(r.get("url", ""), quote=True)
        rbr = html.escape(r.get("branch", "main"), quote=False)
        rsha = r.get("commit", "")
        rshort = r.get("short_commit", rsha[:7] if rsha else "")
        rrole = html.escape(r.get("role", ""), quote=False)
        if rsha and rshort:
            c_url = html.escape(f"{r.get('url', '')}/commit/{rsha}", quote=True)
            sha_html = (
                f'<a href="{c_url}" target="_blank" rel="noopener">'
                f"<code>{html.escape(rshort, quote=False)}</code></a>"
            )
        else:
            sha_html = "<code>HEAD</code>"
        repo_rows.append(
            "<tr>"
            f'<td><a href="{rurl}" target="_blank" rel="noopener">'
            f"<strong>{rname}</strong></a></td>"
            f'<td style="text-align: center;"><code>{rbr}</code></td>'
            f'<td style="text-align: center;">{sha_html}</td>'
            f'<td class="wrap-cell">{rrole}</td></tr>'
        )
    repo_rows.append("</tbody></table></div>")

    def clone_cmd(rname: str) -> str:
        info = repo_by_name.get(rname, {"url": f"https://github.com/milk-org/{rname}"})
        url = info.get("url", "").rstrip("/") + ".git"
        br = info.get("branch", "main")
        sha = info.get("commit", "")
        line = f"git clone -b {br} {url} {rname}"
        if sha:
            line += f" && git -C {rname} checkout -q {sha}"
        return line

    isio_sha = repo_by_name.get("ImageStreamIO", {}).get("commit", "")
    isio_cmd = "git -C milk submodule update --init src/engine/ImageStreamIO"
    if isio_sha:
        isio_cmd += f" && git -C milk/src/engine/ImageStreamIO checkout -q {isio_sha}"

    run_cmd = (
        str(latest_repro.get("run_command", DEFAULT_RUN_COMMAND))
        if latest_repro
        else DEFAULT_RUN_COMMAND
    )
    stage_slug = primary_slug or "ao3k_scexao"
    artifact_note = ""
    if latest_repro and primary_slug:
        bfile = html.escape(str(latest_repro.get("bench_file", "ao3k_scexao.bench")))
        mfile = html.escape(
            str(latest_repro.get("metrics_file", "ao3k_scexao_metrics.json"))
        )
        p_esc = html.escape(primary_slug, quote=True)
        artifact_note = (
            "<li><strong>Machine-Readable Bench &amp; Provenance Manifest</strong>: "
            f'<a href="./{p_esc}/{bfile}"><code>{bfile}</code></a> and '
            f'<a href="./{p_esc}/{mfile}"><code>{mfile}</code></a> '
            "(records optical parameters, calibrated loop metrics, and commit SHAs).</li>\n"
        )

    bash_recipe = "\n".join(
        [
            "# 1. Clone all open-source stack repositories into ~/src",
            "mkdir -p ~/src && cd ~/src",
            clone_cmd("milk"),
            isio_cmd,
            clone_cmd("cacao"),
            clone_cmd("milk-mltools"),
            clone_cmd("OpticsMaterials"),
            clone_cmd("WFpropagate"),
            clone_cmd("AtmosphericTurbulenceSimul"),
            clone_cmd("cacaosim"),
            clone_cmd("cacao-work"),
            "",
            "# 2. Configure, compile, install into milk/_install, and run isolated sanity tests",
            "cd ~/src/cacao-work",
            "source env.sh",
            "./scripts/build-all.sh",
            "pytest -v tests/test_00_stack_sanity.py tests/test_05_ao_web_report.py",
            "",
            "# 3. Run closed-loop Subaru AO3k + SCExAO simulation, telemetry, video & reports",
            *(
                [
                    str((m.get("reproducibility") or {}).get("run_command", run_cmd))
                    for m in run_metas
                    if isinstance(m.get("reproducibility"), dict)
                    and (m.get("reproducibility") or {}).get("run_command")
                ]
                if len(run_metas) >= 2
                and any(
                    isinstance(m.get("reproducibility"), dict)
                    and (m.get("reproducibility") or {}).get("run_command")
                    for m in run_metas
                )
                else [run_cmd]
            ),
            *(
                [
                    "",
                    "# 3b. Compile comparative Predictive Control Report",
                    "${PYTHON_BIN} ./scripts/build-predictive-control-report.py",
                ]
                if any(m.get("slug") == "predictive_control_report" for m in study_metas)
                else []
            ),
            *(
                [
                    "",
                    "# 3c. Compile 2-WFS + 1-DM Telemetry Calibration Study Report",
                    "${PYTHON_BIN} ./scripts/build-calib-2wfs1dm-report.py",
                ]
                if any(m.get("slug") == "calib_2wfs1dm_report" for m in study_metas)
                else []
            ),
            "",
            "# 4. Stage static HTML website locally under _work/_web_site/public/",
            *(
                [
                    f"./scripts/publish-ao-report.sh --build-only _work/{m.get('slug')}"
                    for m in metas
                    if m.get("slug")
                ]
                if len(metas) >= 2
                else [f"./scripts/publish-ao-report.sh --build-only _work/{stage_slug}"]
            ),
        ]
    )
    bash_esc = html.escape(bash_recipe, quote=False)

    body = (
        "<h1>cacao-work &middot; Closed-Loop Adaptive Optics Knowledge Repository</h1>\n"
        "<p>Open-source hardware-in-the-loop adaptive optics simulation, real-time control, "
        "and deployment knowledge repository coupling "
        '<a href="https://github.com/cacao-org/cacao" target="_blank" rel="noopener">'
        "<strong>cacao</strong></a> real-time control, "
        '<a href="https://github.com/milk-org/milk" target="_blank" rel="noopener">'
        "<strong>milk</strong></a> / "
        '<a href="https://github.com/milk-org/ImageStreamIO" target="_blank" rel="noopener">'
        "<strong>ImageStreamIO</strong></a> shared-memory pipelines, "
        '<a href="https://github.com/cacao-org/cacaosim" target="_blank" rel="noopener">'
        "<strong>cacaosim</strong></a> GPU polychromatic propagation, "
        '<a href="https://github.com/oguyon/AtmosphericTurbulenceSimul" '
        'target="_blank" rel="noopener"><strong>milkatmturb</strong></a> turbulence, and '
        '<a href="https://github.com/milk-org/milk-mltools" target="_blank" rel="noopener">'
        "<strong>milk-mltools</strong></a> telemetry &amp; system ID.</p>\n"
        '<div class="badge-row">'
        f'<span class="metric-pill metric-pill-accent">{len(study_metas)} Technical Reports</span>'
        f'<span class="metric-pill metric-pill-accent">{len(run_metas)} Simulation Suites</span>'
        '<span class="metric-pill">9 Open-Source Repositories</span>'
        '<span class="metric-pill">Interactive Calculators &amp; Explorers</span>'
        "</div>\n"
        f"{tech_table_html}\n"
        f"{sim_table_html}\n"
        '<h2 id="github-repositories">Open-Source GitHub Repositories</h2>\n'
        "<p>All source repositories build into one relocatable prefix "
        "(<code>milk/_install/milk-&lt;version&gt;</code>) via "
        "<code>./scripts/build-all.sh</code>:</p>\n"
        + "\n".join(repo_rows)
        + '\n\n<h2 id="reproduce-results">'
        "End-to-End Reproduction Guide (CLI &amp; AI Agent Ready)</h2>\n"
        "<ul>\n"
        "<li><strong>System Prerequisites</strong>: Linux <code>x86_64</code> with "
        "<code>/dev/shm</code> (<code>tmpfs</code>), GCC/G++ with OpenMP, CMake &ge; 3.20, "
        "CFITSIO, FFTW3, OpenBLAS + LAPACKE, <code>ncurses</code>, NVIDIA CUDA Toolkit "
        "(CPU fallback supported), and Python &ge; 3.10.</li>\n"
        f"{artifact_note}"
        "</ul>\n"
        f"<pre><code>{bash_esc}</code></pre>\n"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>cacao-work &middot; AO Knowledge Repository &amp; Simulation Reports</title>
<style>
{CSS_STYLES}
</style>
</head>
<body>
<header class="site-header">
  <div class="nav-inner">
    <a class="brand" href="./index.html">cacao-work &middot; AO Knowledge Repository</a>
    <nav class="nav-links">
      {"".join(study_nav_links)}
      <a href="#tech-reports">Technical Reports</a>
      <a href="#simulation-reports">Simulations</a>
      <a href="#github-repositories">GitHub Repos</a>
      <a href="#reproduce-results">Reproduce</a>
      <a href="https://github.com/cacao-org/cacao-work" target="_blank" rel="noopener">GitHub</a>
      <button type="button" class="theme-btn" id="theme-toggle">Theme</button>
    </nav>
  </div>
</header>
<main class="container">
{body}</main>
<footer class="site-footer">
  <span>Open-source AO stack:
    <a href="https://github.com/cacao-org/cacao-work"
       target="_blank" rel="noopener"><code>cacao-org/cacao-work</code></a></span>
  <span>Self-contained interactive static knowledge repository</span>
</footer>
<script>
{COMMON_JS}
{FRONT_PAGE_JS}
</script>
</body>
</html>
"""


def _replace_marker(text: str, start_tok: str, end_tok: str, replacement: str) -> str:
    pat = re.compile(
        re.escape(start_tok) + r".*?" + re.escape(end_tok),
        flags=re.DOTALL,
    )
    return pat.sub(f"{start_tok}\n{replacement}\n{end_tok}", text)


def refresh_cross_links(public_dir: Path, metas: list[dict[str, object]]) -> None:
    """Populate sim switchers, tech-report backlinks, and referenced-sim tables."""
    metas = sorted(metas, key=meta_sort_key)
    study_metas = [m for m in metas if is_tech_report_meta(m)]
    run_metas = [m for m in metas if not is_tech_report_meta(m)]
    run_by_slug = {str(m.get("slug", "")): m for m in run_metas if m.get("slug")}

    sim_to_techs: dict[str, list[dict[str, object]]] = {s: [] for s in run_by_slug}
    for tm in study_metas:
        refs = tm.get("referenced_simulations")
        if isinstance(refs, list):
            for r in refs:
                rs = str(r)
                if rs in sim_to_techs:
                    sim_to_techs[rs].append(tm)

    # 1. Update simulation sub-pages (backlinks + switcher)
    sim_pages = (
        "index.html",
        "config.html",
        "optical.html",
        "runtime.html",
        "how_to_run.html",
        "compute_report.html",
        "compute.html",
    )
    for m in run_metas:
        slug = str(m.get("slug", ""))
        sdir = public_dir / slug
        if not sdir.is_dir():
            continue

        t_refs = sim_to_techs.get(slug, [])
        if t_refs:
            links_li = "".join(
                f'<li><a href="../{html.escape(str(tm.get("slug", "")), quote=True)}/index.html">'
                f'<strong>{html.escape(str(tm.get("title", "")), quote=False)}</strong></a>'
                f' &mdash; <span class="muted">'
                f'{html.escape(str(tm.get("summary", "")), quote=False)}</span></li>'
                for tm in t_refs
            )
            backlinks_block = (
                '<div class="explorer-panel"><strong>Referenced By Technical Reports</strong>'
                f'<ul style="margin:0.4rem 0 0 1.2rem;">{links_li}</ul></div>'
            )
        else:
            backlinks_block = ""

        for page_name in sim_pages:
            fpath = sdir / page_name
            if not fpath.is_file():
                continue
            txt = fpath.read_text(encoding="utf-8")
            target_page = (
                "runtime.html"
                if page_name in ("compute_report.html", "compute.html")
                else page_name
            )
            opts = "".join(
                f'<option value="../{html.escape(str(rm.get("slug", "")), quote=True)}/'
                f'{target_page}"'
                f'{" selected" if str(rm.get("slug", "")) == slug else ""}>'
                f'{html.escape(str(rm.get("slug", "")), quote=False)}</option>'
                for rm in run_metas
            )
            switcher_html = (
                '<label for="sim-sw-sel">Switch sim:</label>'
                '<select id="sim-sw-sel" '
                'onchange="if(this.value)location.href=this.value">'
                f"{opts}</select>"
            )
            txt = _replace_marker(
                txt, "<!-- SIM_SWITCHER_START -->", "<!-- SIM_SWITCHER_END -->", switcher_html
            )
            if page_name == "index.html":
                txt = _replace_marker(
                    txt,
                    "<!-- TECH_REPORT_BACKLINKS_START -->",
                    "<!-- TECH_REPORT_BACKLINKS_END -->",
                    backlinks_block,
                )
            fpath.write_text(txt, encoding="utf-8")

    # 2. Update tech report Referenced Simulations table
    for tm in study_metas:
        tslug = str(tm.get("slug", ""))
        tdir = public_dir / tslug
        fpath = tdir / "index.html"
        if not fpath.is_file():
            continue
        refs = tm.get("referenced_simulations")
        ref_slugs = [str(r) for r in refs] if isinstance(refs, list) else []
        rows: list[str] = []
        for rs in ref_slugs:
            rm = run_by_slug.get(rs)
            if rm is None:
                continue
            c = rm.get("comparison") if isinstance(rm.get("comparison"), dict) else {}
            rs_esc = html.escape(rs, quote=True)
            s1_w = (
                f'{float(c["stg1_wfe_nm"]):.1f} nm'
                if c.get("stg1_wfe_nm") is not None
                else "&mdash;"
            )
            fin_w = f'{float(c["wfe_nm"]):.1f} nm' if c.get("wfe_nm") is not None else "&mdash;"
            vsr = (
                f'{float(c["vis_sr_pct"]):.2f}%'
                if c.get("vis_sr_pct") is not None
                else "&mdash;"
            )
            hsr = (
                f'{float(c["nir_sr_pct"]):.2f}%'
                if c.get("nir_sr_pct") is not None
                else "&mdash;"
            )
            c310 = (
                f'{float(c["planet_contrast_3_10ld"]):.2e}'
                if c.get("planet_contrast_3_10ld") is not None
                else "&mdash;"
            )
            rows.append(
                "<tr>"
                f'<td><a href="../{rs_esc}/index.html"><strong><code>{html.escape(rs)}</code>'
                "</strong></a></td>"
                f'<td style="text-align:right;"><code>{s1_w}</code></td>'
                f'<td style="text-align:right;"><code>{fin_w}</code></td>'
                f'<td style="text-align:right;"><code>{vsr}</code></td>'
                f'<td style="text-align:right;"><code>{hsr}</code></td>'
                f'<td style="text-align:right;"><code>{c310}</code></td>'
                f'<td><div class="sublinks-row">'
                f'<a href="../{rs_esc}/index.html">Overview</a>'
                f'<a href="../{rs_esc}/config.html">Config</a>'
                f'<a href="../{rs_esc}/optical.html">Optical</a>'
                f'<a href="../{rs_esc}/runtime.html">Runtime</a>'
                f'<a href="../{rs_esc}/how_to_run.html">How to Run</a>'
                "</div></td></tr>"
            )
        if rows:
            tbl_html = (
                '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
                "<th>Simulation</th>"
                '<th style="text-align:right;">Post-AO3k WFE</th>'
                '<th style="text-align:right;">Final WFE</th>'
                '<th style="text-align:right;">Vis SR</th>'
                '<th style="text-align:right;">H SR</th>'
                '<th style="text-align:right;">Coro 3-10 l/D</th>'
                '<th data-nosort="1">Sub-Pages</th>'
                f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            )
        else:
            tbl_html = '<p class="muted">No matching simulation reports staged locally yet.</p>'
        txt = fpath.read_text(encoding="utf-8")
        txt = _replace_marker(
            txt, "<!-- REF_SIMS_TABLE_START -->", "<!-- REF_SIMS_TABLE_END -->", tbl_html
        )
        fpath.write_text(txt, encoding="utf-8")
