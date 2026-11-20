#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation Configuration sub-page renderer (<slug>/config.html)."""

from __future__ import annotations

import html
from pathlib import Path

from ..constants import friendly_figure_caption
from ..markdown.context import RenderContext
from ..markdown.parser import convert_markdown_to_html
from ..markdown.sim_split import extract_toc_html, extract_toc_items
from .fragments import render_section_badges
from .sim_shell import render_sim_page_shell


def build_sim_config_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    hierarchy: dict[str, object],
    config_md: str,
    gui_md: str = "",
    metrics_data: dict[str, object],
    bench_sections: list[dict[str, object]],
    bench_path: Path | None,
    out_slug_dir: Path,
    ctx: RenderContext,
    has_compute_report: bool,
    updated_utc: str,
) -> str:
    """Build the simulation Configuration sub-page (config.html)."""
    heading_seen: dict[str, int] = {}
    config_html, _ = (
        convert_markdown_to_html(config_md, ctx, heading_seen)
        if config_md
        else ("", "")
    )
    gui_mermaid = ctx.has_mermaid

    tel = metrics_data.get("telescope")
    sa = metrics_data.get("star_and_atmosphere")
    loops = metrics_data.get("loops")
    summary_blocks: list[str] = []
    if isinstance(tel, dict) or isinstance(sa, dict):
        t_rows = []
        if isinstance(tel, dict):
            t_rows.extend(
                [
                    ("Telescope Diameter", f"{tel.get('diameter_m', '?')} m"),
                    ("Central Obstruction", f"{float(tel.get('cobs', 0))*100:.1f}%"),
                    ("Pupil Grid", f"{tel.get('nwf', '?')}x{tel.get('nwf', '?')} px"),
                    ("Throughput", f"{float(tel.get('tput_tel', 0))*100:.0f}%"),
                ]
            )
        if isinstance(sa, dict):
            t_rows.extend(
                [
                    ("Seeing (0.50 um)", f'{sa.get("seeing_arcsec_500nm", "?")}"'),
                    ("Atmosphere Profile", str(sa.get("profile", "Maunakea"))),
                    (
                        "Internal Bench Clock",
                        f'{float(sa.get("internal_bench_hz", 8000))/1000:.1f} kHz '
                        f'({sa.get("oversample", 4)}x oversample)',
                    ),
                ]
            )
        trs = "".join(
            f"<tr><td><strong>{html.escape(k, quote=False)}</strong></td>"
            f"<td><code>{html.escape(str(v), quote=False)}</code></td></tr>"
            for k, v in t_rows
        )
        summary_blocks.append(
            '<h2 id="system-summary">System &amp; Atmosphere Parameters '
            f'{render_section_badges(["simulation"])}</h2>'
            '<div class="table-wrap" data-sortable="1"><table><thead>'
            "<tr><th>Parameter</th><th>Value</th></tr></thead>"
            f"<tbody>{trs}</tbody></table></div>"
        )

    if isinstance(loops, dict) and loops:
        l_rows: list[str] = []
        for skey, sname in (
            ("stage1_ao3k", "Stage 1 (AO3k)"),
            ("stage2_scexao", "Stage 2 (SCExAO)"),
            ("stage3_llowfs", "Stage 3 (LLOWFS)"),
        ):
            ld = loops.get(skey)
            if not isinstance(ld, dict):
                continue
            l_rows.append(
                "<tr>"
                f"<td><strong>{sname}</strong></td>"
                f"<td><code>{html.escape(str(ld.get('dm_grid', '?')), quote=False)}</code></td>"
                f"<td><code>{html.escape(str(ld.get('wfs_detector', '?')), quote=False)}</code></td>"
                f'<td style="text-align:right;">{float(ld.get("phys_rate_hz", 0)):.0f} Hz</td>'
                f'<td style="text-align:right;">{ld.get("n_cm_modes", "?")}</td>'
                f'<td style="text-align:right;">{ld.get("gain", "?")} / '
                f'{ld.get("mult", "?")}</td>'
                f'<td style="text-align:right;">{ld.get("svdlim", "?")}</td>'
                "</tr>"
            )
        if l_rows:
            summary_blocks.append(
                '<h2 id="ao-control-stages">AO Control Stages '
                f'{render_section_badges(["loop_operation"])}</h2>'
                '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
                "<th>Stage</th><th>DM Grid</th><th>WFS</th>"
                '<th style="text-align:right;">Rate</th>'
                '<th style="text-align:right;">Modes</th>'
                '<th style="text-align:right;">Gain / Mult</th>'
                '<th style="text-align:right;">SVD Lim</th></tr></thead>'
                f'<tbody>{"".join(l_rows)}</tbody></table></div>'
            )

    gui_tabs_html = ""
    gui_specs = [
        ("schematic", "cacaosim_gui_schematic.png", "F3: Schematic"),
        ("builder", "cacaosim_gui_builder.png", "F2: Builder"),
        ("tables", "cacaosim_gui_tables.png", "F4: Tables"),
        ("status", "cacaosim_gui_status.png", "F5: Status"),
    ]
    avail_gui = [(k, f, l) for k, f, l in gui_specs if (out_slug_dir / f).is_file()]
    if avail_gui:
        for _, f, _ in avail_gui:
            ctx.referenced_images.add(f)
        btns = "".join(
            f'<button type="button" class="chip-btn tab-btn{" active" if i == 0 else ""}" '
            f'data-tab="{k}">{l}</button>'
            for i, (k, _, l) in enumerate(avail_gui)
        )
        panels = "".join(
            f'<div class="tab-panel{" active" if i == 0 else ""}" data-panel="{k}">'
            '<figure class="report-figure">'
            f'<a href="{f}" class="lightbox-trigger" '
            f'data-caption="{html.escape(friendly_figure_caption(f), quote=True)}">'
            f'<img src="{f}" alt="{html.escape(l, quote=True)}" loading="lazy"></a>'
            f"<figcaption>{html.escape(friendly_figure_caption(f), quote=False)}</figcaption>"
            "</figure></div>"
            for i, (k, f, l) in enumerate(avail_gui)
        )
        gui_tabs_html = (
            '<h2 id="hardware-simulator-gui-cacaosim-ctrl">'
            "Hardware Simulator GUI (<code>cacaosim-CTRL</code>)</h2>"
            f'<div class="explorer-panel gui-tabs"><div class="tab-bar">{btns}</div>'
            f"{panels}</div>"
        )
    elif gui_md:
        gui_tabs_html, _ = convert_markdown_to_html(gui_md, ctx, heading_seen)

    bench_html = ""
    if bench_sections:
        cats = sorted({str(s["category"]) for s in bench_sections})
        cat_btns = ['<button type="button" class="chip-btn active" data-bench-cat="all">All</button>']
        for c in cats:
            cat_btns.append(
                f'<button type="button" class="chip-btn" data-bench-cat="{html.escape(c)}">'
                f"{html.escape(c)}</button>"
            )
        cards: list[str] = []
        for s in bench_sections:
            hdr = html.escape(str(s["header"]), quote=False)
            cat = html.escape(str(s["category"]), quote=True)
            params_d = s["params"]
            assert isinstance(params_d, dict)
            kv_items = "".join(
                f"<dt>{html.escape(k, quote=False)}</dt>"
                f"<dd>{html.escape(str(v), quote=False)}</dd>"
                for k, v in list(params_d.items())[:14]
            )
            cards.append(
                f'<div class="bench-card" data-cat="{cat}">'
                f'<div class="bench-card-hdr"><strong><code>[{hdr}]</code></strong>'
                f'<span class="metric-pill">{cat}</span></div>'
                f'<dl class="bench-kv">{kv_items}</dl></div>'
            )
        raw_bench = ""
        if bench_path and bench_path.is_file():
            raw_txt = html.escape(bench_path.read_text(encoding="utf-8", errors="replace"))
            raw_bench = (
                f'<details style="margin-top:0.75rem;"><summary><strong>'
                f'View raw <code>{html.escape(bench_path.name)}</code></strong> &middot; '
                f'<a href="{html.escape(bench_path.name, quote=True)}" download>Download</a>'
                f"</summary><pre><code>{raw_txt}</code></pre></details>"
            )
        bench_html = (
            '<h2 id="bench-explorer">Interactive Optical Bench (<code>.bench</code>) Explorer '
            f'{render_section_badges(["simulation"])}</h2>'
            '<div class="toolbar">'
            f'<div class="toolbar-group">{"".join(cat_btns)}</div>'
            '<input type="search" id="bench-search" class="search-input" '
            'placeholder="Filter components or streams...">'
            "</div>"
            f'<div class="bench-grid" id="bench-card-grid">{"".join(cards)}</div>'
            f"{raw_bench}"
        )

    raw_body = "\n\n".join(
        p
        for p in (
            f"<h1>{html.escape(title, quote=False)} &middot; Configuration</h1>",
            *summary_blocks,
            config_html,
            gui_tabs_html,
            bench_html,
        )
        if p
    )
    toc = extract_toc_html(raw_body)
    if toc:
        h1_end = raw_body.find("</h1>") + 5
        raw_body = raw_body[:h1_end] + "\n\n" + toc + "\n\n" + raw_body[h1_end:]
    toc_items = extract_toc_items(raw_body)

    return render_sim_page_shell(
        title=f"{title} — Configuration",
        slug=slug,
        domain_id=domain_id,
        hierarchy=hierarchy,
        active_tab="config",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        toc_items=toc_items,
        page_scripts=("config_page.js",),
        has_mermaid=gui_mermaid,
        updated_utc=updated_utc,
    )
