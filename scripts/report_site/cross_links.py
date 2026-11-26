#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Site-wide cross-link refresher for headers, sidebars, sim switchers, and backlinks."""

from __future__ import annotations

import html
from pathlib import Path
import re

from .pages.shell import render_nav_inner, render_sidebar_tree_inner


def _replace_marker(text: str, start_tok: str, end_tok: str, replacement: str) -> str:
    pat = re.compile(
        re.escape(start_tok) + r".*?" + re.escape(end_tok),
        flags=re.DOTALL,
    )
    return pat.sub(f"{start_tok}\n{replacement}\n{end_tok}", text)


def _build_grouped_sim_switcher(
    hierarchy: dict[str, object],
    current_slug: str,
    target_page: str,
) -> str:
    """Build a domain-grouped <select> simulation switcher."""
    domains = hierarchy.get("domains") or []
    groups: list[str] = []
    seen: set[str] = set()
    for dom in domains:
        if not isinstance(dom, dict):
            continue
        p_sims = dom.get("primary_sims") or []
        opts: list[str] = []
        for rm in p_sims:
            if not isinstance(rm, dict):
                continue
            rs = str(rm.get("slug", ""))
            if not rs or rs in seen:
                continue
            seen.add(rs)
            sel = " selected" if rs == current_slug else ""
            opt_page = target_page
            if opt_page == "pyrwfs.html" and not rm.get("has_pyrwfs_report"):
                opt_page = "index.html"
            opts.append(
                f'<option value="../{html.escape(rs, quote=True)}/{opt_page}"{sel}>'
                f"{html.escape(rs, quote=False)}</option>"
            )
        if opts:
            groups.append(
                f'<optgroup label="{html.escape(str(dom["short_title"]), quote=True)}">'
                f'{"".join(opts)}</optgroup>'
            )
    return (
        '<label for="sim-sw-sel">Switch sim:</label>'
        '<select id="sim-sw-sel" onchange="if(this.value)location.href=this.value">'
        f'{"".join(groups)}</select>'
    )


def refresh_cross_links(public_dir: Path, hierarchy: dict[str, object]) -> None:
    """Refresh nav headers, sidebar trees, sim switchers, backlinks, and ref-sim tables."""
    study_metas = list(hierarchy.get("study_metas") or [])
    run_metas = list(hierarchy.get("run_metas") or [])
    run_by_slug: dict[str, dict[str, object]] = hierarchy.get("run_by_slug") or {}  # type: ignore[assignment]
    domain_by_slug: dict[str, str] = hierarchy.get("domain_by_slug") or {}  # type: ignore[assignment]
    sim_to_techs: dict[str, list[dict[str, object]]] = hierarchy.get("sim_to_techs") or {}  # type: ignore[assignment]

    sim_header = render_nav_inner("..", hierarchy, active_nav="simulations", has_sidebar=True)
    tech_header = render_nav_inner("..", hierarchy, active_nav="topics", has_sidebar=True)

    sim_pages = (
        "index.html",
        "config.html",
        "optical.html",
        "pyrwfs.html",
        "runtime.html",
        "how_to_run.html",
        "compute_report.html",
        "compute.html",
    )
    for m in run_metas:
        if not isinstance(m, dict):
            continue
        slug = str(m.get("slug", ""))
        sdir = public_dir / slug
        if not sdir.is_dir():
            continue
        dom_id = str(domain_by_slug.get(slug, "bench-runtime"))
        sidebar_tree = render_sidebar_tree_inner(
            "..", hierarchy, active_domain=dom_id, active_slug=slug
        )

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
            switcher_html = _build_grouped_sim_switcher(hierarchy, slug, target_page)
            txt = _replace_marker(txt, "<!-- SITE_HEADER_START -->", "<!-- SITE_HEADER_END -->", sim_header)
            txt = _replace_marker(
                txt, "<!-- SIDEBAR_TREE_START -->", "<!-- SIDEBAR_TREE_END -->", sidebar_tree
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

    for tm in study_metas:
        if not isinstance(tm, dict):
            continue
        tslug = str(tm.get("slug", ""))
        fpath = public_dir / tslug / "index.html"
        if not fpath.is_file():
            continue
        dom_id = str(domain_by_slug.get(tslug, "bench-runtime"))
        sidebar_tree = render_sidebar_tree_inner(
            "..", hierarchy, active_domain=dom_id, active_slug=tslug
        )
        refs = tm.get("referenced_simulations")
        ref_slugs = [str(r) for r in refs] if isinstance(refs, list) else []
        rows: list[str] = []
        for rs in ref_slugs:
            rm = run_by_slug.get(rs)
            if rm is None:
                continue
            c = rm.get("comparison") if isinstance(rm.get("comparison"), dict) else {}
            rs_esc = html.escape(rs, quote=True)
            s1_w = f'{float(c["stg1_wfe_nm"]):.1f} nm' if c.get("stg1_wfe_nm") is not None else "&mdash;"
            fin_w = f'{float(c["wfe_nm"]):.1f} nm' if c.get("wfe_nm") is not None else "&mdash;"
            vsr = f'{float(c["vis_sr_pct"]):.2f}%' if c.get("vis_sr_pct") is not None else "&mdash;"
            hsr = f'{float(c["nir_sr_pct"]):.2f}%' if c.get("nir_sr_pct") is not None else "&mdash;"
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
                + (f'<a href="../{rs_esc}/pyrwfs.html">PyWFS</a>' if rm.get("has_pyrwfs_report") else "")
                + f'<a href="../{rs_esc}/runtime.html">Runtime</a>'
                f'<a href="../{rs_esc}/how_to_run.html">How to Run</a>'
                "</div></td></tr>"
            )
        archived_raw = tm.get("archived_simulations")
        archived_slugs = (
            [str(a).strip() for a in archived_raw if str(a).strip()]
            if isinstance(archived_raw, list)
            else []
        )
        archived_note = ""
        if archived_slugs:
            pills = " ".join(
                f'<span class="param-pill"><code>{html.escape(a, quote=False)}</code></span>'
                for a in archived_slugs
            )
            archived_note = (
                '<p class="muted" style="margin-top:0.6rem;"><strong>Archived study runs '
                "(individual simulation pages retired; all plots, tables, and numerical "
                f"findings preserved below):</strong></p>"
                f'<div class="param-list" style="margin-top:0.25rem;">{pills}</div>'
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
                f"{archived_note}"
            )
        elif archived_note:
            tbl_html = archived_note
        else:
            tbl_html = '<p class="muted">No matching simulation reports staged locally yet.</p>'
        txt = fpath.read_text(encoding="utf-8")
        txt = _replace_marker(txt, "<!-- SITE_HEADER_START -->", "<!-- SITE_HEADER_END -->", tech_header)
        txt = _replace_marker(
            txt, "<!-- SIDEBAR_TREE_START -->", "<!-- SIDEBAR_TREE_END -->", sidebar_tree
        )
        txt = _replace_marker(
            txt, "<!-- REF_SIMS_TABLE_START -->", "<!-- REF_SIMS_TABLE_END -->", tbl_html
        )
        fpath.write_text(txt, encoding="utf-8")
