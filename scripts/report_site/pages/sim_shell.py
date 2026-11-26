#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared simulation 5-tab subnav shell wrapper."""

from __future__ import annotations

import html

from .shell import render_page_shell

SIM_TABS: tuple[tuple[str, str, str], ...] = (
    ("overview", "index.html", "Overview"),
    ("config", "config.html", "Configuration"),
    ("optical", "optical.html", "Optical Performance"),
    ("pyrwfs", "pyrwfs.html", "Pyramid WFS"),
    ("runtime", "runtime.html", "Runtime Performance"),
    ("how_to_run", "how_to_run.html", "How to Run It"),
)


def render_sim_page_shell(
    *,
    title: str,
    slug: str,
    domain_id: str,
    hierarchy: dict[str, object],
    active_tab: str,
    has_compute_report: bool,
    has_pyrwfs_report: bool = False,
    body_html: str,
    toc_items: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    page_scripts: tuple[str, ...] = (),
    has_mermaid: bool = False,
    updated_utc: str = "",
) -> str:
    """Wrap a simulation overview or sub-page in the unified site shell + subnav."""
    slug_esc = html.escape(slug, quote=False)
    active_tabs = tuple(
        t for t in SIM_TABS if (t[0] != "pyrwfs" or has_pyrwfs_report or active_tab == "pyrwfs")
    )
    tab_lbls = {k: lbl for k, _, lbl in active_tabs}
    tab_links: list[str] = []
    for tkey, thref, tlbl in active_tabs:
        t_disp = f"{tlbl} (N/A)" if (tkey == "runtime" and not has_compute_report) else tlbl
        cls = ' class="active"' if active_tab == tkey else ""
        tab_links.append(f'<a href="{thref}"{cls}>{html.escape(t_disp, quote=False)}</a>')

    cur_file = next(h for k, h, _ in active_tabs if k == active_tab)
    cur_label = tab_lbls.get(active_tab, "Overview")
    domain_map: dict[str, dict[str, object]] = hierarchy.get("domain_map") or {}  # type: ignore[assignment]
    dom = domain_map.get(domain_id) or {}
    dom_title = str(dom.get("title") or domain_id)

    subnav_html = (
        '<div class="subnav-bar">\n'
        '  <div class="subnav-inner">\n'
        '    <nav class="subnav-tabs" aria-label="Simulation pages">\n'
        f'      {"".join(tab_links)}\n'
        "    </nav>\n"
        f'    <div class="sim-switcher" data-current-page="{cur_file}">\n'
        "      <!-- SIM_SWITCHER_START -->\n"
        f"      <span>Simulation: <code>{slug_esc}</code></span>\n"
        "      <!-- SIM_SWITCHER_END -->\n"
        "    </div>\n"
        "  </div>\n"
        "</div>"
    )

    return render_page_shell(
        title=title,
        rel_root="..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="simulations",
        active_domain=domain_id,
        active_slug=slug,
        active_sim_tab=active_tab,
        has_compute_report=has_compute_report,
        has_pyrwfs_report=has_pyrwfs_report or active_tab == "pyrwfs",
        page_kind="simulation",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Topics", f"../topics/{domain_id}/index.html"),
            (dom_title, f"../topics/{domain_id}/index.html"),
            (slug, "index.html"),
            (cur_label, None),
        ],
        show_sidebar=True,
        subnav_html=subnav_html,
        toc_items=toc_items,
        page_scripts=page_scripts,
        has_mermaid=has_mermaid,
        footer_left=(
            f"Simulation <code>{slug_esc}</code> &middot; "
            '<a href="https://github.com/cacao-org/cacao-work" '
            'target="_blank" rel="noopener"><code>cacao-work</code></a>'
        ),
        footer_right=f"Updated {html.escape(updated_utc, quote=False)}",
    )
