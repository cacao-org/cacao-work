#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation Optical Performance sub-page renderer (<slug>/optical.html)."""

from __future__ import annotations

import html
from pathlib import Path

from ..constants import COMPUTE_IMAGES, GUI_CONFIG_IMAGES
from ..markdown.context import RenderContext
from ..markdown.parser import convert_markdown_to_html
from ..markdown.sim_split import extract_toc_html, extract_toc_items
from .fragments import (
    build_extra_figures_section,
    render_section_badges,
    safe_json_embed,
)
from .sim_shell import render_sim_page_shell


def build_sim_optical_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    hierarchy: dict[str, object],
    optical_md: str,
    explorer_data: dict[str, object],
    staged_files: list[Path],
    ctx: RenderContext,
    has_compute_report: bool,
    updated_utc: str,
) -> str:
    """Build the simulation Optical Performance sub-page (optical.html)."""
    ctx.has_mermaid = False
    opt_html, _ = (
        convert_markdown_to_html(optical_md, ctx, {})
        if optical_md
        else ("<p>No optical sections found in REPORT.md.</p>", "")
    )
    has_mermaid = ctx.has_mermaid

    explorer_html = ""
    tabs: list[tuple[str, str]] = []
    if explorer_data.get("wf_timeseries"):
        tabs.append(("wfe", "WFE Time Series"))
    if explorer_data.get("strehl_timeseries"):
        tabs.append(("strehl", "Strehl Time Series"))
    if explorer_data.get("modal_stages"):
        tabs.append(("modal", "Modal Gain & Sensitivity"))
    if explorer_data.get("contrast_table"):
        tabs.append(("coro", "Coronagraph Contrast"))
    if tabs:
        t_btns = "".join(
            f'<button type="button" class="chip-btn{" active" if i == 0 else ""}" '
            f'data-opt-tab="{k}">{l}</button>'
            for i, (k, l) in enumerate(tabs)
        )
        explorer_html = (
            '<h2 id="interactive-optical-explorer">Interactive Optical Data Explorer '
            f'{render_section_badges(["analysis"])}</h2>'
            '<div class="explorer-panel">'
            '<div class="toolbar" style="margin-top:0;">'
            f'<div class="toolbar-group">{t_btns}</div>'
            '<div class="toolbar-group" id="opt-controls"></div>'
            "</div>"
            '<div class="canvas-wrap">'
            '<canvas id="opt-canvas" class="chart-canvas"></canvas>'
            '<div id="opt-tooltip" class="canvas-tooltip"></div>'
            "</div>"
            f'<script id="optical-explorer-data" type="application/json">'
            f"{safe_json_embed(explorer_data)}</script>"
            "</div>"
        )

    extra_figs = build_extra_figures_section(
        staged_files,
        ctx,
        exclude_names=GUI_CONFIG_IMAGES | COMPUTE_IMAGES,
    )
    raw_body = "\n\n".join(
        p
        for p in (
            f"<h1>{html.escape(title, quote=False)} &middot; Optical Performance</h1>",
            explorer_html,
            opt_html,
            extra_figs,
        )
        if p
    )
    toc = extract_toc_html(raw_body)
    if toc:
        h1_end = raw_body.find("</h1>") + 5
        raw_body = raw_body[:h1_end] + "\n\n" + toc + "\n\n" + raw_body[h1_end:]
    toc_items = extract_toc_items(raw_body)

    return render_sim_page_shell(
        title=f"{title} — Optical Performance",
        slug=slug,
        domain_id=domain_id,
        hierarchy=hierarchy,
        active_tab="optical",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        toc_items=toc_items,
        page_scripts=("optical_explorer.js",) if tabs else (),
        has_mermaid=has_mermaid,
        updated_utc=updated_utc,
    )
