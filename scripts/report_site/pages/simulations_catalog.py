#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""All Simulations Catalog page renderer (/simulations/index.html)."""

from __future__ import annotations

from ..markdown.sim_split import extract_toc_items
from .fragments import kpi_card
from .shell import render_page_shell
from .sim_table import render_simulations_section


def build_simulations_catalog_html(hierarchy: dict[str, object]) -> str:
    """Render the full filterable/comparable Simulation Suites catalog page."""
    run_metas = list(hierarchy.get("run_metas") or [])
    domains = hierarchy.get("domains") or []

    hero = (
        '<section class="hero-banner">\n'
        "<h1>All Closed-Loop AO Simulation Suites</h1>\n"
        "<p>Complete side-by-side matrix of all staged simulation runs across all AO "
        "research domains, ordered newest-first by simulation date (click any column "
        "header to re-sort). Filter by research domain, control law, Stage-3 LLOWFS state, "
        "or 2-WFS/1-DM system ID, and select runs to compare Strehl, WFE, and contrast. "
        "Every simulation references the "
        '<a href="../turbulence/index.html"><strong>Default Turbulence &amp; Perturbation Model</strong></a> '
        "and explicitly notes any atmosphere, wind, vibration, or petaling overrides.</p>\n"
        '<div class="kpi-grid">'
        + kpi_card("Total Simulations", str(len(run_metas)), "Staged in repository")
        + kpi_card("Research Domains", str(len(domains)), "Filterable below")
        + kpi_card("Views per Run", "5 Pages", "Overview, Config, Optical, Runtime, How-to-Run")
        + "</div>\n"
        '<div class="hero-actions">'
        '<a class="btn btn-secondary" href="../turbulence/index.html">'
        "Default Turbulence &amp; Perturbation Model &rarr;</a>"
        "</div>\n"
        "</section>"
    )

    sim_sec = render_simulations_section(
        run_metas,
        rel_root="..",
        hierarchy=hierarchy,
        show_domain_filter=True,
        section_heading="Simulation Comparison Matrix",
        section_id="simulation-reports",
    )
    body_html = "\n\n".join([hero, sim_sec])
    toc_items = extract_toc_items(body_html)

    return render_page_shell(
        title="All Simulation Suites · cacao-work AO Repository",
        rel_root="..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="simulations",
        page_kind="simulations_catalog",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Simulations", None),
        ],
        show_sidebar=True,
        toc_items=toc_items,
        page_scripts=("sim_catalog.js",),
        footer_right=f"{len(run_metas)} Simulation Suites",
    )
