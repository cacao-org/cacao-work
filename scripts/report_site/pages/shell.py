#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared responsive page shell: pull-down navbar, collapsible sidebar, and search modal."""

from __future__ import annotations

import html

from ..assets import render_css_tags, render_js_tags
from .fragments import mermaid_tag


def render_nav_inner(
    rel_root: str,
    hierarchy: dict[str, object],
    *,
    active_nav: str = "",
    has_sidebar: bool = True,
) -> str:
    """Render the unified top navigation bar with pull-down menus."""
    base = rel_root.rstrip("/") or "."
    domains = hierarchy.get("domains") or []
    run_metas = hierarchy.get("run_metas") or []

    topics_items: list[str] = []
    for dom in domains:
        if not isinstance(dom, dict):
            continue
        did = str(dom["id"])
        dtitle = str(dom["title"])
        t_list = dom.get("tech_reports") or []
        p_sims = dom.get("primary_sims") or []
        c_sims = dom.get("crossref_sims") or []
        sim_cnt = len(p_sims) + len(c_sims)
        topics_items.append(
            f'<div class="drop-group-title">{html.escape(dtitle, quote=False)}</div>'
        )
        topics_items.append(
            f'<a class="drop-item" href="{base}/topics/{html.escape(did, quote=True)}/index.html">'
            f'<span><strong>Topic Hub</strong>'
            f'<span class="drop-item-sub">{html.escape(str(dom.get("short_title", dtitle)), quote=False)} overview</span></span>'
            f'<span class="drop-count">{len(t_list)} TR &middot; {sim_cnt} sim</span></a>'
        )
        for tm in t_list:
            if not isinstance(tm, dict):
                continue
            ts = str(tm.get("slug", ""))
            tlbl = str(tm.get("nav_label") or tm.get("title") or ts)
            topics_items.append(
                f'<a class="drop-item" href="{base}/{html.escape(ts, quote=True)}/index.html">'
                f'<span>{html.escape(tlbl, quote=False)}</span>'
                f'<span class="drop-count">Report</span></a>'
            )

    sim_items: list[str] = [
        f'<a class="drop-item" href="{base}/simulations/index.html">'
        f'<span><strong>All Simulations Catalog</strong>'
        f'<span class="drop-item-sub">Filter, compare &amp; sort parameters</span></span>'
        f'<span class="drop-count">{len(run_metas)}</span></a>'
    ]
    for dom in domains:
        if not isinstance(dom, dict):
            continue
        p_sims = dom.get("primary_sims") or []
        if not p_sims:
            continue
        sim_items.append(
            f'<div class="drop-group-title">{html.escape(str(dom["short_title"]), quote=False)}</div>'
        )
        for rm in list(p_sims)[:8]:
            if not isinstance(rm, dict):
                continue
            rs = str(rm.get("slug", ""))
            sim_items.append(
                f'<a class="drop-item" href="{base}/{html.escape(rs, quote=True)}/index.html">'
                f'<code>{html.escape(rs, quote=False)}</code></a>'
            )
        if len(p_sims) > 8:
            did = str(dom["id"])
            sim_items.append(
                f'<a class="drop-item" href="{base}/topics/{html.escape(did, quote=True)}/index.html">'
                f'<span class="muted">View all {len(p_sims)} runs &rarr;</span></a>'
            )

    stack_items = (
        f'<a class="drop-item" href="{base}/stack/index.html#github-repositories">'
        f'<span><strong>GitHub Repositories</strong>'
        f'<span class="drop-item-sub">9 open-source MILK/CACAO checkouts</span></span></a>'
        f'<a class="drop-item" href="{base}/stack/index.html#reproduce-results">'
        f'<span><strong>Reproduction Guide</strong>'
        f'<span class="drop-item-sub">End-to-end build &amp; CLI workflow</span></span></a>'
        f'<a class="drop-item" href="{base}/stack/index.html#adding-reports">'
        f'<span><strong>Adding Topics &amp; Reports</strong>'
        f'<span class="drop-item-sub">Declarative taxonomy.json guide</span></span></a>'
        '<div class="drop-group-title">External</div>'
        '<a class="drop-item" href="https://github.com/cacao-org/cacao-work" '
        'target="_blank" rel="noopener"><span>GitHub: cacao-org/cacao-work</span>'
        '<span class="drop-count">&nearr;</span></a>'
    )

    sb_btn = (
        '<button type="button" class="nav-icon-btn" id="sidebar-toggle" '
        'aria-expanded="true" aria-label="Toggle navigation sidebar" '
        'title="Toggle Sidebar">&#9776;</button>'
        if has_sidebar
        else ""
    )
    home_cls = " active" if active_nav == "home" else ""
    top_cls = " active" if active_nav == "topics" else ""
    sim_cls = " active" if active_nav == "simulations" else ""
    stk_cls = " active" if active_nav == "stack" else ""

    return (
        '<div class="nav-inner">\n'
        '  <div class="nav-left">\n'
        f"    {sb_btn}\n"
        f'    <a class="brand" href="{base}/index.html">'
        "cacao-work &middot; AO Knowledge Repository</a>\n"
        "  </div>\n"
        '  <nav class="nav-links" aria-label="Primary navigation">\n'
        f'    <a class="nav-link{home_cls}" href="{base}/index.html">Home</a>\n'
        '    <div class="nav-dropdown">\n'
        f'      <button type="button" class="nav-drop-btn{top_cls}" aria-expanded="false">'
        'Topics <span class="nav-caret">&#9662;</span></button>\n'
        f'      <div class="nav-drop-menu">{"".join(topics_items)}</div>\n'
        "    </div>\n"
        '    <div class="nav-dropdown">\n'
        f'      <button type="button" class="nav-drop-btn{sim_cls}" aria-expanded="false">'
        'Simulations <span class="nav-caret">&#9662;</span></button>\n'
        f'      <div class="nav-drop-menu">{"".join(sim_items)}</div>\n'
        "    </div>\n"
        '    <div class="nav-dropdown">\n'
        f'      <button type="button" class="nav-drop-btn{stk_cls}" aria-expanded="false">'
        'Stack &amp; Guides <span class="nav-caret">&#9662;</span></button>\n'
        f'      <div class="nav-drop-menu align-right">{stack_items}</div>\n'
        "    </div>\n"
        '    <button type="button" class="nav-icon-btn" id="global-search-open" '
        'title="Search site (/)">Search <span class="kbd-hint">/</span></button>\n'
        '    <button type="button" class="theme-btn" id="theme-toggle">Theme</button>\n'
        "  </nav>\n"
        "</div>"
    )


def render_sidebar_tree_inner(
    rel_root: str,
    hierarchy: dict[str, object],
    *,
    active_domain: str = "",
    active_slug: str = "",
) -> str:
    """Render the collapsible sidebar domain tree HTML (refreshable across pages)."""
    base = rel_root.rstrip("/") or "."
    domains = hierarchy.get("domains") or []
    domain_map = hierarchy.get("domain_map") or {}
    dom = domain_map.get(active_domain) if active_domain in domain_map else None

    parts: list[str] = []
    if isinstance(dom, dict):
        did = str(dom["id"])
        dtitle = str(dom["short_title"])
        techs = dom.get("tech_reports") or []
        p_sims = dom.get("primary_sims") or []
        c_sims = dom.get("crossref_sims") or []
        hub_act = ' class="active"' if not active_slug else ""
        items: list[str] = [
            f'<li><a{hub_act} href="{base}/topics/{html.escape(did, quote=True)}/index.html">'
            f"Overview: {html.escape(dtitle, quote=False)}</a></li>"
        ]
        for tm in techs:
            if not isinstance(tm, dict):
                continue
            ts = str(tm.get("slug", ""))
            tl = str(tm.get("nav_label") or tm.get("title") or ts)
            cls = ' class="active"' if ts == active_slug else ""
            items.append(
                f'<li><a{cls} href="{base}/{html.escape(ts, quote=True)}/index.html">'
                f"{html.escape(tl, quote=False)}</a></li>"
            )
        for rm in list(p_sims) + list(c_sims):
            if not isinstance(rm, dict):
                continue
            rs = str(rm.get("slug", ""))
            cls = ' class="active"' if rs == active_slug else ""
            items.append(
                f'<li><a{cls} href="{base}/{html.escape(rs, quote=True)}/index.html">'
                f"<code>{html.escape(rs, quote=False)}</code></a></li>"
            )
        parts.append(
            '<div class="sidebar-section">'
            f'<div class="sidebar-heading">{html.escape(dtitle, quote=False)}</div>'
            f'<ul class="sidebar-list">{"".join(items)}</ul>'
            "</div>"
        )

    dom_links: list[str] = []
    for d in domains:
        if not isinstance(d, dict):
            continue
        did = str(d["id"])
        cls = ' class="active"' if did == active_domain and not active_slug else ""
        dom_links.append(
            f'<li><a{cls} href="{base}/topics/{html.escape(did, quote=True)}/index.html">'
            f'{html.escape(str(d["title"]), quote=False)}</a></li>'
        )
    parts.append(
        '<div class="sidebar-section">'
        '<div class="sidebar-heading">AO Research Domains</div>'
        f'<ul class="sidebar-list">{"".join(dom_links)}</ul>'
        "</div>"
    )
    return "\n".join(parts)


def render_sidebar_html(
    rel_root: str,
    hierarchy: dict[str, object],
    *,
    active_domain: str = "",
    active_slug: str = "",
    active_sim_tab: str = "",
    has_compute_report: bool = False,
    toc_items: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    page_kind: str = "",
) -> str:
    """Render the complete <aside id='site-sidebar'> panel."""
    tree_html = render_sidebar_tree_inner(
        rel_root,
        hierarchy,
        active_domain=active_domain,
        active_slug=active_slug,
    )
    views_sec = ""
    if page_kind == "simulation":
        tabs = (
            ("overview", "index.html", "Overview"),
            ("config", "config.html", "Configuration"),
            ("optical", "optical.html", "Optical Performance"),
            (
                "runtime",
                "runtime.html",
                "Runtime Performance" if has_compute_report else "Runtime Performance (N/A)",
            ),
            ("how_to_run", "how_to_run.html", "How to Run It"),
        )
        v_lis = "".join(
            f'<li><a{" class=\"active\"" if k == active_sim_tab else ""} href="{href}">'
            f"{html.escape(lbl, quote=False)}</a></li>"
            for k, href, lbl in tabs
        )
        views_sec = (
            '<div class="sidebar-section">'
            '<div class="sidebar-heading">Simulation Views</div>'
            f'<ul class="sidebar-list">{v_lis}</ul>'
            "</div>"
        )

    toc_sec = ""
    if len(toc_items) >= 2:
        t_lis = "".join(
            f'<li><a class="toc-link" href="#{html.escape(hid, quote=True)}">'
            f"{html.escape(lbl, quote=False)}</a></li>"
            for hid, lbl in toc_items
        )
        toc_sec = (
            '<div class="sidebar-section sidebar-toc">'
            '<div class="sidebar-heading">On This Page</div>'
            f'<ul class="sidebar-list">{t_lis}</ul>'
            "</div>"
        )

    return (
        '<aside class="site-sidebar" id="site-sidebar" aria-label="Section &amp; topic navigation">\n'
        "<!-- SIDEBAR_TREE_START -->\n"
        f"{tree_html}\n"
        "<!-- SIDEBAR_TREE_END -->\n"
        f"{views_sec}\n"
        f"{toc_sec}\n"
        "</aside>\n"
        '<div class="sidebar-backdrop" id="sidebar-backdrop"></div>'
    )


def render_page_shell(
    *,
    title: str,
    rel_root: str,
    hierarchy: dict[str, object],
    body_html: str,
    active_nav: str = "",
    active_domain: str = "",
    active_slug: str = "",
    active_sim_tab: str = "",
    has_compute_report: bool = False,
    page_kind: str = "",
    breadcrumbs: list[tuple[str, str | None]] = (),
    show_sidebar: bool = True,
    subnav_html: str = "",
    toc_items: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    page_scripts: tuple[str, ...] = (),
    has_mermaid: bool = False,
    footer_left: str = "",
    footer_right: str = "",
) -> str:
    """Wrap page content in the unified site shell with external CSS & JS."""
    base = rel_root.rstrip("/") or "."
    title_esc = html.escape(title, quote=False)
    header_inner = render_nav_inner(
        base, hierarchy, active_nav=active_nav, has_sidebar=show_sidebar
    )
    sidebar_html = (
        render_sidebar_html(
            base,
            hierarchy,
            active_domain=active_domain,
            active_slug=active_slug,
            active_sim_tab=active_sim_tab,
            has_compute_report=has_compute_report,
            toc_items=toc_items,
            page_kind=page_kind,
        )
        if show_sidebar
        else ""
    )

    bc_html = ""
    if breadcrumbs:
        bc_parts: list[str] = []
        for lbl, href in breadcrumbs:
            lbl_esc = html.escape(lbl, quote=False)
            if href:
                bc_parts.append(f'<a href="{html.escape(href, quote=True)}">{lbl_esc}</a>')
            else:
                bc_parts.append(f"<span>{lbl_esc}</span>")
        bc_html = f'<nav class="breadcrumb" aria-label="Breadcrumb">{" / ".join(bc_parts)}</nav>'

    shell_cls = "page-shell has-sidebar" if show_sidebar else "page-shell"
    f_left = footer_left or (
        'Open-source AO stack: <a href="https://github.com/cacao-org/cacao-work" '
        'target="_blank" rel="noopener"><code>cacao-org/cacao-work</code></a>'
    )
    f_right = footer_right or "Static AO Knowledge Repository"

    return f"""<!DOCTYPE html>
<html lang="en" data-rel-root="{html.escape(base, quote=True)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc}</title>
{render_css_tags(base)}
</head>
<body data-page-kind="{html.escape(page_kind, quote=True)}" data-active-nav="{html.escape(active_nav, quote=True)}" data-domain="{html.escape(active_domain, quote=True)}" data-slug="{html.escape(active_slug, quote=True)}">
<header class="site-header">
<!-- SITE_HEADER_START -->
{header_inner}
<!-- SITE_HEADER_END -->
{subnav_html}
</header>
<div class="{shell_cls}">
{sidebar_html}
<main class="container">
{bc_html}
{body_html}
</main>
</div>
<div class="search-modal-backdrop" id="global-search-backdrop" role="dialog" aria-modal="true" aria-label="Search site">
  <div class="search-modal">
    <div class="search-modal-bar">
      <input type="search" id="global-search-input" placeholder="Search AO topics, technical reports, simulations, or guides...">
      <button type="button" class="btn-sm" id="global-search-close">Esc</button>
    </div>
    <div class="search-results" id="global-search-results"></div>
  </div>
</div>
<footer class="site-footer">
  <span>{f_left}</span>
  <span>{f_right}</span>
</footer>
{render_js_tags(base, page_scripts)}{mermaid_tag(has_mermaid)}
</body>
</html>
"""
