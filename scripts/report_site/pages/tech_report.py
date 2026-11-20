#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Standalone Technical Report page renderer (<slug>/index.html)."""

from __future__ import annotations

import html

from ..markdown.sim_split import extract_toc_html, extract_toc_items
from .fragments import render_domain_badge
from .shell import render_page_shell


def build_tech_report_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    study_meta: dict[str, object],
    hierarchy: dict[str, object],
    report_body_html: str,
    extra_figs_html: str,
    data_files_html: str,
    has_repro_section: bool,
    has_mermaid: bool,
    updated_utc: str,
) -> str:
    """Build a standalone Technical Report page (public/<slug>/index.html)."""
    slug_esc = html.escape(slug, quote=False)
    nav_lbl = str(study_meta.get("nav_label") or title or slug)
    domain_map: dict[str, dict[str, object]] = hierarchy.get("domain_map") or {}  # type: ignore[assignment]
    dom = domain_map.get(domain_id) or {}
    dom_title = str(dom.get("title") or domain_id)

    badges = study_meta.get("badges")
    badge_pills: list[str] = [render_domain_badge(domain_id, domain_map, rel_root="..")]
    if isinstance(badges, list):
        badge_pills.extend(
            f'<span class="metric-pill">{html.escape(str(b), quote=False)}</span>'
            for b in badges
        )
    badge_html = f'<div class="badge-row">{"".join(badge_pills)}</div>'

    summary = str(study_meta.get("summary") or "")
    sum_html = (
        f'<blockquote class="callout"><p>{html.escape(summary, quote=False)}</p></blockquote>'
        if summary
        else ""
    )
    ref_sims_slot = (
        '<h2 id="referenced-simulations">Referenced Simulation Reports</h2>\n'
        "<!-- REF_SIMS_TABLE_START -->\n"
        '<p class="muted">Simulation links are populated across the site index.</p>\n'
        "<!-- REF_SIMS_TABLE_END -->"
    )
    raw_body = "\n\n".join(
        p
        for p in (
            badge_html,
            sum_html,
            ref_sims_slot,
            report_body_html,
            extra_figs_html,
            data_files_html,
        )
        if p
    )
    toc = extract_toc_html(raw_body)
    if toc:
        raw_body = toc + "\n\n" + raw_body
    toc_items = extract_toc_items(raw_body)

    repro_href = (
        "#reproducibility-github-provenance"
        if has_repro_section
        else "../stack/index.html#reproduce-results"
    )
    extra_bar = (
        '<div class="subnav-bar"><div class="subnav-inner">'
        f'<div class="subnav-tabs"><a href="index.html" class="active">{html.escape(nav_lbl, quote=False)}</a>'
        f'<a href="#referenced-simulations">Referenced Simulations</a>'
        f'<a href="{repro_href}">Reproduce Study</a></div>'
        f'<div class="sim-switcher"><a class="btn-sm" href="../topics/{html.escape(domain_id, quote=True)}/index.html">'
        f"{html.escape(str(dom.get('short_title') or dom_title), quote=False)} Hub &rarr;</a></div>"
        "</div></div>"
    )

    return render_page_shell(
        title=title,
        rel_root="..",
        hierarchy=hierarchy,
        body_html=raw_body,
        active_nav="topics",
        active_domain=domain_id,
        active_slug=slug,
        page_kind="tech_report",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Topics", f"../topics/{domain_id}/index.html"),
            (dom_title, f"../topics/{domain_id}/index.html"),
            (nav_lbl, None),
        ],
        show_sidebar=True,
        subnav_html=extra_bar,
        toc_items=toc_items,
        has_mermaid=has_mermaid,
        footer_left=f"Technical Report <code>{slug_esc}</code>",
        footer_right=f"Updated {html.escape(updated_utc, quote=False)}",
    )
