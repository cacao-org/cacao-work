#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Clean Executive Hub Front Page (index.html and reports.html)."""

from __future__ import annotations

import html

from .fragments import kpi_card, render_domain_badge
from .shell import render_page_shell


def build_front_page_html(hierarchy: dict[str, object]) -> str:
    """Render the clean Executive Hub Front Page organized by AO research domains."""
    domains = hierarchy.get("domains") or []
    study_metas = hierarchy.get("study_metas") or []
    run_metas = hierarchy.get("run_metas") or []
    domain_by_slug: dict[str, str] = hierarchy.get("domain_by_slug") or {}  # type: ignore[assignment]
    domain_map: dict[str, dict[str, object]] = hierarchy.get("domain_map") or {}  # type: ignore[assignment]
    sim_slug_set = {str(m.get("slug", "")) for m in run_metas if isinstance(m, dict) and m.get("slug")}

    hero_html = (
        '<section class="hero-banner">\n'
        "<h1>cacao-work &middot; Closed-Loop Adaptive Optics Knowledge Repository</h1>\n"
        "<p>Open-source hardware-in-the-loop adaptive optics simulation, real-time control, "
        "system identification, and coronagraphic research coupling "
        '<a href="https://github.com/cacao-org/cacao" target="_blank" rel="noopener"><strong>cacao</strong></a>, '
        '<a href="https://github.com/milk-org/milk" target="_blank" rel="noopener"><strong>milk</strong></a> / '
        '<a href="https://github.com/milk-org/ImageStreamIO" target="_blank" rel="noopener"><strong>ImageStreamIO</strong></a>, '
        '<a href="https://github.com/cacao-org/cacaosim" target="_blank" rel="noopener"><strong>cacaosim</strong></a>, '
        '<a href="https://github.com/oguyon/AtmosphericTurbulenceSimul" target="_blank" rel="noopener"><strong>milkatmturb</strong></a>, '
        'and <a href="https://github.com/milk-org/milk-mltools" target="_blank" rel="noopener"><strong>milk-mltools</strong></a>.</p>\n'
        '<div class="kpi-grid">'
        + kpi_card("AO Research Domains", str(len(domains)), "Single topic hierarchy")
        + kpi_card("Technical Reports", str(len(study_metas)), "In-depth physics & SysID")
        + kpi_card("Simulation Suites", str(len(run_metas)), "5 views per simulation")
        + kpi_card("Open-Source Stack", "9 Repos", "Relocatable CMake build")
        + "</div>\n"
        '<div class="hero-actions">'
        '<a class="btn" href="./simulations/index.html">Browse All Simulations &rarr;</a>'
        '<a class="btn btn-secondary" href="./algorithms/index.html">Algorithms &amp; Matrix</a>'
        '<a class="btn btn-secondary" href="./reference/index.html">Options Reference</a>'
        '<a class="btn btn-secondary" href="./stack/index.html">Stack &amp; Reproduction Guide</a>'
        "</div>\n"
        "</section>"
    )

    domain_cards: list[str] = []
    for dom in domains:
        if not isinstance(dom, dict):
            continue
        did = str(dom["id"])
        did_esc = html.escape(did, quote=True)
        dtitle = str(dom["title"])
        ddesc = str(dom.get("description") or "")
        techs = dom.get("tech_reports") or []
        p_sims = dom.get("primary_sims") or []
        c_sims = dom.get("crossref_sims") or []
        subgroups = dom.get("subgroups") or []

        sg_pills = "".join(
            f'<span class="param-pill">{html.escape(str(sg.get("label", "")), quote=False)}</span>'
            for sg in subgroups
            if isinstance(sg, dict)
        )
        tr_links = "".join(
            f'<a href="./{html.escape(str(tm["slug"]), quote=True)}/index.html">'
            f'<strong>{html.escape(str(tm.get("nav_label") or tm.get("title") or tm["slug"]), quote=False)}</strong></a>'
            for tm in techs
            if isinstance(tm, dict)
        )
        sim_preview_items = list(p_sims)[:3] or list(c_sims)[:3]
        sim_pills = "".join(
            f'<a class="param-pill" href="./{html.escape(str(rm["slug"]), quote=True)}/index.html">'
            f'<code>{html.escape(str(rm["slug"]), quote=False)}</code></a>'
            for rm in sim_preview_items
            if isinstance(rm, dict)
        )
        cnt_lbl = f"{len(techs)} report(s) &middot; {len(p_sims)} primary"
        if c_sims:
            cnt_lbl += f" (+{len(c_sims)} ref)"

        domain_cards.append(
            f'<article class="domain-card domain-{did_esc}">\n'
            "  <div>\n"
            '    <div class="domain-card-hdr">\n'
            f'      <h3><a href="./topics/{did_esc}/index.html">{html.escape(dtitle, quote=False)}</a></h3>\n'
            f'      <span class="muted">{cnt_lbl}</span>\n'
            "    </div>\n"
            f"    <p>{html.escape(ddesc, quote=False)}</p>\n"
            f'    <div class="param-list" style="margin-top:0.55rem;">{sg_pills}</div>\n'
            "  </div>\n"
            '  <div class="domain-card-links">\n'
            + (f"    <div><strong>Studies:</strong> {tr_links}</div>\n" if tr_links else "")
            + (
                f'    <div class="param-list">{sim_pills}</div>\n'
                if sim_pills
                else '    <div class="muted">Cross-referenced runs available inside hub.</div>\n'
            )
            + f'    <a class="subpage-cta" href="./topics/{did_esc}/index.html">'
            f"Open {html.escape(str(dom.get('short_title', dtitle)), quote=False)} Hub &rarr;</a>\n"
            "  </div>\n"
            "</article>"
        )

    domains_html = (
        '<h2 id="research-domains">Research &amp; Technology Domains</h2>\n'
        "<p>Every technical study and simulation run is organized into one unified hierarchy "
        "by adaptive optics research domain:</p>\n"
        f'<div class="domain-grid">{"".join(domain_cards)}</div>'
    )

    t1_rows: list[str] = []
    for meta in study_metas:
        if not isinstance(meta, dict):
            continue
        slug = str(meta.get("slug", ""))
        slug_esc = html.escape(slug, quote=True)
        title = str(meta.get("title", slug))
        nav_lbl = str(meta.get("nav_label") or title)
        summary = str(meta.get("summary") or "")
        upd = str(meta.get("updated_utc") or "")
        did = str(domain_by_slug.get(slug) or meta.get("domain") or "bench-runtime")
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
            for r in refs[:6]
            if str(r) in sim_slug_set or not sim_slug_set
        )
        if len(refs) > 6:
            ref_links += f'<span class="param-pill">+{len(refs) - 6} more</span>'
        t1_rows.append(
            "<tr>"
            f'<td class="wrap-cell">'
            f'<a href="./{slug_esc}/index.html"><strong>{html.escape(title)}</strong></a>'
            f'<br><span class="muted">{html.escape(summary)}</span>'
            f'<div class="sublinks-row">'
            f'<a href="./{slug_esc}/index.html">Read {html.escape(nav_lbl)}</a>'
            f'<a href="./{slug_esc}/index.html#reproducibility-github-provenance">Reproduce</a>'
            "</div></td>"
            f'<td>{render_domain_badge(did, domain_map, rel_root=".")}</td>'
            f'<td class="param-cell"><div class="param-list">{feat_pills or "&mdash;"}</div></td>'
            f'<td class="param-cell"><div class="param-list">{hl_pills or "&mdash;"}</div></td>'
            f'<td class="param-cell"><div class="param-list">{ref_links or "&mdash;"}</div></td>'
            f'<td style="text-align:right;"><span class="muted">{html.escape(upd)}</span></td>'
            "</tr>"
        )

    tech_table_html = (
        '<h2 id="tech-reports">Featured Technical Reports</h2>\n'
        "<p>In-depth engineering analyses, physics studies, and architectural roadmaps linking "
        "directly to supporting closed-loop simulations.</p>\n"
        '<div class="toolbar">'
        f'<span><strong>{len(study_metas)}</strong> Technical Report(s)</span>'
        '<input type="search" id="tech-search" class="search-input" '
        'placeholder="Search technical reports, domains, or capabilities..."></div>\n'
        '<div class="table-wrap" data-sortable="1">'
        '<table id="tech-reports-table"><thead><tr>'
        "<th>Technical Report</th>"
        "<th>Domain</th>"
        "<th>CACAO Capabilities</th>"
        "<th>Key Findings</th>"
        "<th>Referenced Simulations</th>"
        '<th style="text-align:right;">Updated</th>'
        "</tr></thead><tbody>"
        + (
            "".join(t1_rows)
            if t1_rows
            else '<tr><td colspan="6" class="muted">No technical reports staged yet.</td></tr>'
        )
        + "</tbody></table></div>"
    )

    quick_links_html = (
        '<div class="subpage-grid">'
        '<a class="subpage-card" href="./simulations/index.html">'
        '<div><h3>All Simulation Suites Matrix</h3>'
        f"<p>Filter, compare, and inspect all {len(run_metas)} closed-loop runs with "
        "parameter diffs, optical Strehl/contrast charts, and runtime explorers.</p></div>"
        '<span class="subpage-cta">Open Simulation Catalog &rarr;</span></a>'
        '<a class="subpage-card" href="./algorithms/index.html">'
        '<div><h3>Algorithms &amp; Dependency Matrix</h3>'
        "<p>Color-coded catalog and 2D matrix distinguishing Offline Calibration, Online "
        "Calibration, and RT Operation using short <code>CODE/OPT</code> tags, with a "
        "dedicated webpage per entry.</p></div>"
        '<span class="subpage-cta">Open Algorithms Matrix &rarr;</span></a>'
        '<a class="subpage-card" href="./reference/index.html">'
        '<div><h3>Simulator Options Reference</h3>'
        "<p>Searchable tables for every <code>.bench</code> optical element key, "
        "all 17 <code>cacaosim</code> &amp; <code>milkatmturb</code> FPS compute units, "
        "runner CLI flags, and <code>CACAO_*</code> environment variables.</p></div>"
        '<span class="subpage-cta">Open Options Reference &rarr;</span></a>'
        '<a class="subpage-card" href="./stack/index.html">'
        '<div><h3>Open-Source Stack &amp; Reproduction</h3>'
        "<p>Pinned commits across all 9 MILK/CACAO/cacaosim repositories, CMake build "
        "steps, CLI replay commands, and guide to adding new topics.</p></div>"
        '<span class="subpage-cta">Open Stack &amp; Guides &rarr;</span></a>'
        "</div>"
    )

    guide_html = (
        '<section class="guide-box" id="quick-guide" aria-label="Quick navigation guide">\n'
        '  <div class="guide-hdr">'
        "<h2>Quick Guide</h2>"
        '<span class="muted">How topics, technical reports, and simulations are organized</span>'
        "</div>\n"
        '  <div class="guide-grid">\n'
        '    <div class="guide-step">\n'
        '      <div class="guide-step-title"><span class="guide-num">1</span>'
        "<strong>Browse by Research Domain</strong></div>\n"
        '      <p>Use <strong>Topics &#9662;</strong> or the '
        f'<a href="#research-domains">{len(domains)} domain cards</a> below for Wavefront Control, '
        "Calibration &amp; SysID, Coronagraphy &amp; LLOWFS, Optical Bench &amp; Runtime, "
        "or Hardware &amp; DM Dynamics hubs.</p>\n"
        "    </div>\n"
        '    <div class="guide-step">\n'
        '      <div class="guide-step-title"><span class="guide-num">2</span>'
        "<strong>Reports vs. 5-View Simulations</strong></div>\n"
        '      <p>Start with <a href="#tech-reports">Technical Reports</a> for multi-run '
        "physics studies; open any simulation for 5 views "
        "(<em>Overview</em>, <em>Config</em>, <em>Optical</em>, <em>Runtime</em>, "
        "<em>How to Run</em>).</p>\n"
        "    </div>\n"
        '    <div class="guide-step">\n'
        '      <div class="guide-step-title"><span class="guide-num">3</span>'
        "<strong>Filter, Compare &amp; Search</strong></div>\n"
        '      <p>Use the <a href="./simulations/index.html">Simulations Catalog</a> to filter '
        "runs and plot Strehl/WFE/contrast side by side, or press <kbd>/</kbd> anywhere for "
        "instant site search.</p>\n"
        "    </div>\n"
        '    <div class="guide-step">\n'
        '      <div class="guide-step-title"><span class="guide-num">4</span>'
        "<strong>Build &amp; Reproduce Locally</strong></div>\n"
        '      <p>Open <a href="./stack/index.html">Stack &amp; Guides</a> for pinned commits '
        "across all 9 MILK/CACAO/<code>cacaosim</code> repos, CLI replay commands, and adding "
        "reports via <code>taxonomy.json</code>.</p>\n"
        "    </div>\n"
        "  </div>\n"
        "</section>"
    )

    body = "\n\n".join([hero_html, guide_html, domains_html, tech_table_html, quick_links_html])
    return render_page_shell(
        title="cacao-work · AO Knowledge Repository & Simulation Reports",
        rel_root=".",
        hierarchy=hierarchy,
        body_html=body,
        active_nav="home",
        page_kind="home",
        show_sidebar=False,
        page_scripts=("sim_catalog.js",),
        footer_right="Self-contained interactive static knowledge repository",
    )
