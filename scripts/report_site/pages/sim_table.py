#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Reusable filterable & comparable simulation matrix table and controls."""

from __future__ import annotations

import html

from ..extractors.common import meta_sort_key
from ..extractors.params import TRACKED_PARAMS, resolve_run_parameters
from .fragments import safe_json_embed
from .sim_table_helpers import (
    build_sim_table_headers,
    build_sim_table_row,
    render_filter_panel,
)


def render_simulations_section(
    run_metas: list[dict[str, object]],
    *,
    rel_root: str,
    hierarchy: dict[str, object],
    show_domain_filter: bool = True,
    crossref_slugs: set[str] | None = None,
    section_heading: str = "Simulation Suites",
    section_id: str = "simulation-reports",
    intro_html: str = "",
) -> str:
    """Render the interactive, filterable simulation table and comparison drawer."""
    base = rel_root.rstrip("/") or "."
    run_metas = sorted(run_metas, key=meta_sort_key)
    param_dicts = [resolve_run_parameters(m) for m in run_metas]
    domain_by_slug: dict[str, str] = hierarchy.get("domain_by_slug") or {}  # type: ignore[assignment]
    domain_map: dict[str, dict[str, object]] = hierarchy.get("domain_map") or {}  # type: ignore[assignment]
    sim_to_techs: dict[str, list[dict[str, object]]] = hierarchy.get("sim_to_techs") or {}  # type: ignore[assignment]
    domains: list[dict[str, object]] = hierarchy.get("domains") or []  # type: ignore[assignment]
    cross_set = crossref_slugs or set()

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

    cols = {
        "s1wfe": has_cmp_key("stg1_wfe_nm"),
        "wfe": has_cmp_key("wfe_nm"),
        "vsr": has_cmp_key("vis_sr_pct"),
        "nsr": has_cmp_key("nir_sr_pct"),
        "coro": has_cmp_bool("has_coro"),
        "c2d": has_cmp_bool("calib_2wfs1dm_enabled"),
    }
    hdr_cells = build_sim_table_headers(cols)

    compact_diff_only = len(changed_specs) > 4
    t_rows: list[str] = []
    cmp_json_map: dict[str, dict[str, object]] = {}
    ctrl_counts = {"integrator": 0, "ar": 0, "eof": 0}
    llowfs_counts = {"on": 0, "off": 0}
    c2d_counts = {"on": 0, "off": 0}
    dom_counts: dict[str, int] = {str(d["id"]): 0 for d in domains}

    for row_idx, (m, pd) in enumerate(zip(run_metas, param_dicts)):
        mslug = str(m.get("slug", ""))
        rdom = str(domain_by_slug.get(mslug) or m.get("domain") or "bench-runtime")
        dom_counts[rdom] = dom_counts.get(rdom, 0) + 1
        tr_html, f_attrs, cmp_payload = build_sim_table_row(
            row_idx,
            len(run_metas),
            m,
            pd,
            rdom,
            base,
            cols,
            changed_specs,
            ref_vals,
            compact_diff_only,
            domain_map,
            sim_to_techs,
            cross_set,
        )
        t_rows.append(tr_html)
        cmp_json_map[mslug] = cmp_payload
        ctrl_counts[f_attrs["ctrl"]] = ctrl_counts.get(f_attrs["ctrl"], 0) + 1
        if f_attrs["llowfs"] in llowfs_counts:
            llowfs_counts[f_attrs["llowfs"]] += 1
        c2d_counts[f_attrs["calib2wfs"]] = c2d_counts.get(f_attrs["calib2wfs"], 0) + 1

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

    filter_panel_html = render_filter_panel(
        n_runs=len(run_metas),
        show_domain_filter=show_domain_filter,
        domains=domains,
        dom_counts=dom_counts,
        ctrl_counts=ctrl_counts,
        llowfs_counts=llowfs_counts,
        c2d_counts=c2d_counts,
    )

    intro = intro_html or (
        "<p>Each simulation exposes 5 dedicated views: <strong>Overview</strong>, "
        "<strong>Configuration</strong>, <strong>Optical Performance</strong>, "
        "<strong>Runtime Performance</strong>, and <strong>How to Run It</strong>. "
        "Select checkboxes to compare metrics visually:</p>"
    )

    empty_row = (
        f"<tr><td colspan={len(hdr_cells)} class=muted>No simulation reports staged yet.</td></tr>"
    )
    return (
        f'<h2 id="{html.escape(section_id, quote=True)}">{html.escape(section_heading, quote=False)}</h2>\n'
        f"{intro}\n"
        f"{filter_panel_html}"
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
        f'<tbody class="sim-tbody">{"".join(t_rows) if t_rows else empty_row}</tbody>'
        "</table></div>\n"
        '<div id="sim-empty-msg" class="cat-empty-note hidden">'
        "No simulations match the active filters. Click Reset Filters to show all runs.</div>\n"
        f"{shared_strip}\n"
        '<script id="front-sim-compare-data" type="application/json">'
        f"{safe_json_embed(cmp_json_map)}</script>"
    )
