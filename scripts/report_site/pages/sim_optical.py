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


def _build_eof_pf_section(eof_pf_data: dict[str, object] | None) -> str:
    """Build interactive 3D Block-EOF predictive matrix (PF) explorer HTML."""
    if not eof_pf_data or not eof_pf_data.get("stages"):
        return ""
    blk = int(eof_pf_data.get("blocksize") or 128)
    ord_p = int(eof_pf_data.get("order") or 8)
    stages = eof_pf_data.get("stages") or []
    st_desc = " &middot; ".join(
        f"Stage {st.get('stage')}: {st.get('n_modes')} modes "
        f"({st.get('n_blocks')} blocks, {st.get('offdiag_pct')}% off-diag)"
        for st in stages
        if isinstance(st, dict)
    )
    return (
        '<h2 id="eof-3d-predictive-matrix">Interactive 3D Modal Predictive Matrix (PF) '
        f'{render_section_badges(["calibration", "loop_operation"])}</h2>\n'
        '<div class="explorer-panel eof-pf-panel" id="eof-pf-panel">\n'
        '  <p class="muted" style="margin-top:0;">'
        f"Block-EOF <code>VAR({ord_p})</code> tensor "
        "<code>PF[out_i, lag_k, in_j]</code> "
        f"(<code>B={blk}</code> coupled modes/block): "
        "<code>a&#770;<sub>s0+i</sub>(t+d) = &Sigma;<sub>k,j</sub> "
        "F[i,k,j] a<sub>s0+j</sub>(t&minus;k)</code>. "
        f"{html.escape(st_desc, quote=False)}</p>\n"
        '  <div class="toolbar" style="margin-top:0;">\n'
        '    <div class="toolbar-group" id="eof-pf-stage-btns"></div>\n'
        '    <div class="toolbar-group">\n'
        '      <label class="eof-pf-ctrl-label" for="eof-pf-block-sel">Block:</label>\n'
        '      <select class="select-input" id="eof-pf-block-sel"></select>\n'
        "    </div>\n"
        '    <div class="toolbar-group">\n'
        '      <button type="button" class="chip-btn active" '
        'data-pf-view="cube3d">3D Cube</button>\n'
        '      <button type="button" class="chip-btn" '
        'data-pf-view="slice2d">Lag Slice (i, j)</button>\n'
        '      <button type="button" class="chip-btn" '
        'data-pf-view="l2norm">L2 Coupling</button>\n'
        '      <button type="button" class="chip-btn" '
        'data-pf-view="modelag">Mode &times; Lag (i, k)</button>\n'
        "    </div>\n"
        "  </div>\n"
        '  <div class="toolbar">\n'
        '    <div class="toolbar-group">\n'
        '      <label class="eof-pf-ctrl-label" for="eof-pf-lag-slider">Lag k:</label>\n'
        '      <input type="range" id="eof-pf-lag-slider" min="0" max="7" value="0">\n'
        '      <span id="eof-pf-lag-readout" class="muted">k=0</span>\n'
        '      <button type="button" class="btn-sm" id="eof-pf-play-btn">Play</button>\n'
        "    </div>\n"
        '    <div class="toolbar-group">\n'
        '      <label class="eof-pf-ctrl-label" for="eof-pf-zoom-sel">Zoom:</label>\n'
        '      <select class="select-input" id="eof-pf-zoom-sel">\n'
        '        <option value="0">Full Block</option>\n'
        '        <option value="64">First 64</option>\n'
        '        <option value="32">First 32</option>\n'
        "      </select>\n"
        '      <label class="eof-pf-ctrl-label" for="eof-pf-cmap-sel">Color:</label>\n'
        '      <select class="select-input" id="eof-pf-cmap-sel">\n'
        '        <option value="rdbu">Signed (RdBu)</option>\n'
        '        <option value="magma">Log |F| (Magma)</option>\n'
        "      </select>\n"
        '      <label class="eof-pf-ctrl-label">'
        '<input type="checkbox" id="eof-pf-hide-diag"> Hide Diag</label>\n'
        '      <label class="eof-pf-ctrl-label" for="eof-pf-thresh-slider">3D Cut:</label>\n'
        '      <input type="range" id="eof-pf-thresh-slider" min="0" max="15" value="2">\n'
        '      <span id="eof-pf-thresh-val" class="muted">0.015</span>\n'
        '      <button type="button" class="btn-sm" id="eof-pf-reset-btn">Reset 3D</button>\n'
        "    </div>\n"
        "  </div>\n"
        '  <div class="eof-pf-grid">\n'
        '    <div class="canvas-wrap">\n'
        '      <canvas id="eof-pf-main-canvas" class="eof-pf-canvas"></canvas>\n'
        '      <div id="eof-pf-tooltip" class="canvas-tooltip"></div>\n'
        '      <div class="eof-pf-hint muted" id="eof-pf-hint">'
        "Drag 3D cube to rotate orbit; switch to Lag Slice / L2 Coupling to inspect "
        "or click any mode pair (i, j).</div>\n"
        "    </div>\n"
        '    <div class="eof-pf-side">\n'
        '      <div class="eof-pf-side-card">\n'
        '        <h3 id="eof-pf-pair-title">Pair Temporal Kernel</h3>\n'
        '        <div class="canvas-wrap">\n'
        '          <canvas id="eof-pf-kernel-canvas" class="eof-pf-kernel-canvas"></canvas>\n'
        "        </div>\n"
        "      </div>\n"
        '      <div class="eof-pf-side-card">\n'
        "        <h3>Tensor &amp; Pair Statistics</h3>\n"
        '        <div id="eof-pf-stats" class="eof-pf-stats-grid"></div>\n'
        "      </div>\n"
        '      <div class="eof-pf-side-card">\n'
        "        <h3>Top Cross-Mode Pairs</h3>\n"
        '        <div id="eof-pf-pairs" class="eof-pf-pair-chips"></div>\n'
        "      </div>\n"
        "    </div>\n"
        "  </div>\n"
        '  <script src="eof_pf_data.js"></script>\n'
        "</div>"
    )


def build_sim_optical_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    hierarchy: dict[str, object],
    optical_md: str,
    explorer_data: dict[str, object],
    eof_pf_data: dict[str, object] | None = None,
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

    eof_html = _build_eof_pf_section(eof_pf_data)
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
            eof_html,
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

    page_scripts: list[str] = []
    if tabs:
        page_scripts.append("optical_explorer.js")
    if eof_html:
        page_scripts.append("eof_pf_viewer.js")

    return render_sim_page_shell(
        title=f"{title} — Optical Performance",
        slug=slug,
        domain_id=domain_id,
        hierarchy=hierarchy,
        active_tab="optical",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        toc_items=toc_items,
        page_scripts=tuple(page_scripts),
        has_mermaid=has_mermaid,
        updated_utc=updated_utc,
    )
