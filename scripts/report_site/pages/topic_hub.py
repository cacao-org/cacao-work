#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Domain Hub page renderer (/topics/<domain_id>/index.html)."""

from __future__ import annotations

import html

from ..markdown.sim_split import extract_toc_items
from .fragments import kpi_card, render_domain_badge
from .shell import render_page_shell
from .sim_table import render_simulations_section


def build_topic_hub_html(
    domain_id: str,
    hierarchy: dict[str, object],
) -> str:
    """Render a dedicated Research Domain Hub page under public/topics/<domain_id>/."""
    domain_map: dict[str, dict[str, object]] = hierarchy.get("domain_map") or {}  # type: ignore[assignment]
    dom = domain_map[domain_id]
    dtitle = str(dom["title"])
    ddesc = str(dom.get("description") or "")
    subgroups = dom.get("subgroups") or []
    techs = list(dom.get("tech_reports") or [])
    p_sims = list(dom.get("primary_sims") or [])
    c_sims = list(dom.get("crossref_sims") or [])
    crossref_slugs = {str(m.get("slug", "")) for m in c_sims if isinstance(m, dict)}

    sg_pills = "".join(
        f'<span class="metric-pill">{html.escape(str(sg.get("label", "")), quote=False)}</span>'
        for sg in subgroups
        if isinstance(sg, dict)
    )
    hero = (
        '<section class="hero-banner">\n'
        f'<div class="badge-row">{render_domain_badge(domain_id, domain_map, rel_root="../..", linked=False)}'
        f"{sg_pills}</div>\n"
        f"<h1>{html.escape(dtitle, quote=False)}</h1>\n"
        f"<p>{html.escape(ddesc, quote=False)}</p>\n"
        '<div class="kpi-grid">'
        + kpi_card("Technical Studies", str(len(techs)), "Deep-dive analyses")
        + kpi_card("Primary Simulations", str(len(p_sims)), "Owned by this domain")
        + kpi_card("Cross-Referenced Runs", str(len(c_sims)), "Shared baselines & comparisons")
        + "</div>\n"
        "</section>"
    )

    if techs:
        tr_cards: list[str] = []
        for tm in techs:
            if not isinstance(tm, dict):
                continue
            ts = str(tm.get("slug", ""))
            ts_esc = html.escape(ts, quote=True)
            ttitle = str(tm.get("title") or ts)
            tsum = str(tm.get("summary") or "")
            badges = [
                str(b)
                for b in (tm.get("badges") if isinstance(tm.get("badges"), list) else [])
                if str(b) != "FEATURED STUDY"
            ]
            b_html = "".join(
                f'<span class="metric-pill">{html.escape(b, quote=False)}</span>'
                for b in badges[:4]
            )
            tr_cards.append(
                f'<a class="subpage-card" href="../../{ts_esc}/index.html">'
                f"<div><h3>{html.escape(ttitle, quote=False)}</h3>"
                f"<p>{html.escape(tsum, quote=False)}</p>"
                f'<div class="param-list" style="margin-top:0.5rem;">{b_html}</div></div>'
                '<span class="subpage-cta">Read Technical Study &rarr;</span></a>'
            )
        tech_sec = (
            '<h2 id="domain-technical-reports">Technical Reports in This Domain</h2>\n'
            f'<div class="subpage-grid">{"".join(tr_cards)}</div>'
        )
    else:
        tech_sec = (
            '<h2 id="domain-technical-reports">Technical Reports in This Domain</h2>\n'
            '<blockquote class="callout"><p>No standalone technical report is assigned '
            "primarily to this domain yet; inspect the simulation configurations, optical "
            "explorer, and runtime profiles below.</p></blockquote>"
        )

    guide_callout = ""
    if domain_id == "wavefront-control":
        guide_callout = (
            '<div class="explorer-panel">'
            '<div class="turb-card-hdr">'
            '<div><span class="metric-pill metric-pill-accent">Practical Tuning Manual</span> '
            "<strong>CACAO Predictive Control Guide: AR(P), Block-EOF &amp; Cascaded Self-Learning</strong></div>"
            '<a class="btn" href="../../predictive-control/index.html">'
            "Open Predictive Control Guide &rarr;</a>"
            "</div>"
            '<p class="muted" style="margin:0.45rem 0 0;">Human-readable walkthrough of PSOL '
            "prerequisites, Diagonal AR(P), Cross-Mode Block-EOF extensions, Cascaded Self-Learning "
            "(Global RLS + libgric + causal Stein gates), commissioning workflow, regime presets, "
            "and troubleshooting.</p>"
            "</div>"
        )

    combined_sims = p_sims + c_sims
    sim_sec = render_simulations_section(
        combined_sims,
        rel_root="../..",
        hierarchy=hierarchy,
        show_domain_filter=False,
        crossref_slugs=crossref_slugs,
        section_heading="Domain Simulations & Baselines",
        section_id="simulation-reports",
        intro_html=(
            "<p>Includes all primary simulations in this domain plus cross-referenced "
            "baseline/comparison runs. Check boxes to compare metrics interactively:</p>"
        ),
    )

    bench_matrix_sec = ""
    if domain_id == "bench-runtime" and combined_sims:
        m_rows: list[str] = []
        for rm in combined_sims:
            if not isinstance(rm, dict):
                continue
            rs = str(rm.get("slug", ""))
            rs_esc = html.escape(rs, quote=True)
            rt = rm.get("runtime_summary") if isinstance(rm.get("runtime_summary"), dict) else {}
            wall_s = f'{float(rt["wall_duration_s"]):.1f} s' if rt.get("wall_duration_s") is not None else "&mdash;"
            gpu_s = f'{float(rt["gpu_sm_pct"]):.0f}%' if rt.get("gpu_sm_pct") is not None else "&mdash;"
            cores_s = f'{float(rt["sim_cores_mean"]):.2f}' if rt.get("sim_cores_mean") is not None else "&mdash;"
            bw_s = f'{float(rt["shm_bw_mb_s"]):.0f} MB/s' if rt.get("shm_bw_mb_s") is not None else "&mdash;"
            m_rows.append(
                "<tr>"
                f'<td><a href="../../{rs_esc}/index.html"><code>{html.escape(rs, quote=False)}</code></a></td>'
                f'<td style="text-align:right;"><code>{wall_s}</code></td>'
                f'<td style="text-align:right;"><code>{gpu_s}</code></td>'
                f'<td style="text-align:right;"><code>{cores_s}</code></td>'
                f'<td style="text-align:right;"><code>{bw_s}</code></td>'
                f'<td><div class="sublinks-row">'
                f'<a href="../../{rs_esc}/config.html">Config (.bench &amp; GUI)</a>'
                f'<a href="../../{rs_esc}/runtime.html">Runtime Profile</a>'
                f'<a href="../../{rs_esc}/how_to_run.html">How to Run</a>'
                "</div></td></tr>"
            )
        bench_matrix_sec = (
            '<h2 id="bench-runtime-matrix">Optical Bench, Compute &amp; Deployment Matrix</h2>\n'
            "<p>Direct shortcuts to the declarative <code>.bench</code> explorer, "
            "<code>cacaosim-CTRL</code> GUI views, per-process latency profiles, and "
            "step-by-step deployment checklists:</p>\n"
            '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
            "<th>Simulation</th>"
            '<th style="text-align:right;">Wall Time</th>'
            '<th style="text-align:right;">GPU SM</th>'
            '<th style="text-align:right;">CPU Cores</th>'
            '<th style="text-align:right;">SHM BW</th>'
            '<th data-nosort="1">Architecture &amp; Deployment Views</th>'
            f'</tr></thead><tbody>{"".join(m_rows)}</tbody></table></div>'
        )

    body_html = "\n\n".join(
        p for p in (hero, guide_callout, tech_sec, sim_sec, bench_matrix_sec) if p
    )
    toc_items = extract_toc_items(body_html)
    return render_page_shell(
        title=f"{dtitle} · cacao-work AO Topics",
        rel_root="../..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="topics",
        active_domain=domain_id,
        page_kind="topic",
        breadcrumbs=[
            ("Home", "../../index.html"),
            ("Topics", "../../index.html#research-domains"),
            (dtitle, None),
        ],
        show_sidebar=True,
        toc_items=toc_items,
        page_scripts=("sim_catalog.js",),
        footer_right=f"Domain Hub · {dtitle}",
    )
