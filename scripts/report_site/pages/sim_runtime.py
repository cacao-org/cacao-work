#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation Runtime Performance sub-page renderer (<slug>/runtime.html)."""

from __future__ import annotations

import html
from pathlib import Path

from ..constants import COMPUTE_CATEGORY_ORDER
from ..extractors.runtime import classify_shm_category, classify_unit_category
from ..markdown.context import RenderContext
from ..markdown.parser import convert_markdown_to_html
from ..markdown.sim_split import extract_toc_html, extract_toc_items
from .fragments import (
    render_cat_badge,
    render_cat_group_row,
    render_category_filter_pills,
    render_category_legend_html,
    safe_json_embed,
)
from .sim_shell import render_sim_page_shell


def build_sim_runtime_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    hierarchy: dict[str, object],
    compute_md_path: Path,
    runtime_data: dict[str, object],
    ctx: RenderContext,
    has_compute_report: bool,
    updated_utc: str,
) -> str:
    """Build the simulation Runtime Performance sub-page (runtime.html)."""
    ctx.has_mermaid = False
    if has_compute_report:
        compute_body, det_title = convert_markdown_to_html(
            compute_md_path.read_text(encoding="utf-8"), ctx, {}
        )
        page_title = det_title or f"{title} — Runtime Performance"
    else:
        page_title = f"{title} — Runtime Performance"
        compute_body = (
            '<blockquote class="callout"><p>No <code>COMPUTE_REPORT.md</code> '
            "was generated for this run.</p></blockquote>"
        )
    has_mermaid = ctx.has_mermaid

    rt_explorer_html = ""
    if runtime_data:
        parts: list[str] = [
            '<h2 id="interactive-runtime-diagnostics">Interactive Runtime Diagnostics</h2>',
            render_category_legend_html(compact=True),
        ]
        if runtime_data.get("phases"):
            parts.append(
                '<div class="explorer-panel">'
                '<div class="toolbar" style="margin-top:0;">'
                "<strong>Phase Resource Profile</strong>"
                '<select id="rt-phase-metric" class="select-input">'
                '<option value="duration_s">Wall Duration [s]</option>'
                '<option value="sim_cores_mean">Sim Mean CPU Cores</option>'
                '<option value="gpu_util_mean_pct">GPU SM Utilization [%]</option>'
                '<option value="shm_bw_mean_mb_s">SHM Bandwidth [MB/s]</option>'
                '<option value="gpu_power_mean_w">GPU Power [W]</option>'
                "</select></div>"
                '<div id="rt-phase-bars" class="hbar-list"></div>'
                "</div>"
            )
        procs = runtime_data.get("processes")
        if isinstance(procs, list) and procs:
            proc_by_cat: dict[str, list[dict[str, object]]] = {
                k: [] for k in COMPUTE_CATEGORY_ORDER
            }
            for p in procs:
                if not isinstance(p, dict):
                    continue
                pcat = str(p.get("category") or classify_unit_category(str(p.get("name", ""))))
                if pcat not in proc_by_cat:
                    pcat = "loop_operation"
                proc_by_cat[pcat].append(p)
            proc_counts = {k: len(proc_by_cat[k]) for k in COMPUTE_CATEGORY_ORDER}
            p_tbodies: list[str] = []
            for pcat in COMPUTE_CATEGORY_ORDER:
                grp = proc_by_cat[pcat]
                if not grp:
                    continue
                grp_hdr = render_cat_group_row(pcat, 9, len(grp))
                g_rows = "".join(
                    f'<tr class="cat-row cat-{pcat}" data-category="{pcat}" '
                    f'data-subsys="{html.escape(str(p.get("subsystem", "")), quote=True)}">'
                    f'<td><code>{html.escape(str(p["name"]), quote=False)}</code></td>'
                    f'<td>{render_cat_badge(pcat)}</td>'
                    f'<td>{html.escape(str(p.get("subsystem", "")), quote=False)}</td>'
                    f'<td>{html.escape(str(p["backend"]), quote=False)}</td>'
                    f'<td style="text-align:right;">{float(p["cl_cpu_pct"]):.2f}%</td>'
                    f'<td style="text-align:right;">{float(p["exec_p50_us"]):.1f}</td>'
                    f'<td style="text-align:right;">{float(p["exec_p99_us"]):.1f}</td>'
                    f'<td style="text-align:right;">{float(p["rss_mb"]):.1f}</td>'
                    f'<td style="text-align:right;">{int(p["timeouts"])}</td>'
                    "</tr>"
                    for p in grp
                )
                p_tbodies.append(
                    f'<tbody class="cat-tbody cat-{pcat}" data-category="{pcat}">'
                    f"{grp_hdr}{g_rows}</tbody>"
                )
            p_pills = render_category_filter_pills("rt-proc", proc_counts, "processes")
            parts.append(
                '<div class="explorer-panel">'
                '<div class="toolbar" style="margin-top:0;">'
                "<strong>Interactive Process Explorer</strong>"
                '<input type="search" id="rt-proc-search" class="search-input" '
                'placeholder="Filter process..."></div>'
                f'<div class="toolbar">{p_pills}</div>'
                '<div class="table-wrap" data-sortable="1">'
                '<table id="rt-proc-table"><thead><tr>'
                "<th>Process</th><th>Category</th><th>Subsystem</th><th>Backend</th>"
                '<th style="text-align:right;">CL CPU%</th>'
                '<th style="text-align:right;">p50 [us]</th>'
                '<th style="text-align:right;">p99 [us]</th>'
                '<th style="text-align:right;">RSS [MB]</th>'
                '<th style="text-align:right;">Timeouts</th>'
                f'</tr></thead>{"".join(p_tbodies)}</table></div>'
                '<div id="rt-proc-empty-msg" class="cat-empty-note hidden">'
                "No processes match the selected categories or search query.</div></div>"
            )
        streams = runtime_data.get("streams")
        if isinstance(streams, list) and streams:
            shm_counts: dict[str, int] = {k: 0 for k in COMPUTE_CATEGORY_ORDER}
            s_rows_l: list[str] = []
            for s in streams:
                if not isinstance(s, dict):
                    continue
                scat = str(s.get("category") or classify_shm_category(str(s.get("name", ""))))
                if scat not in shm_counts:
                    scat = "loop_operation"
                shm_counts[scat] += 1
                s_rows_l.append(
                    f'<tr class="cat-row cat-{scat}" data-category="{scat}" '
                    f'data-readers="{int(s["nb_readers"])}">'
                    f'<td><code>{html.escape(str(s["name"]), quote=False)}</code></td>'
                    f'<td>{render_cat_badge(scat, short=True)}</td>'
                    f'<td><code>{html.escape(str(s["dims"]), quote=False)}</code></td>'
                    f'<td style="text-align:right;">{float(s["frame_kb"]):.1f}</td>'
                    f'<td style="text-align:right;">{float(s["mean_hz"]):.1f}</td>'
                    f'<td style="text-align:right;">{float(s["mean_mb_s"]):.2f}</td>'
                    f'<td style="text-align:right;">{int(s["nb_readers"])}</td>'
                    "</tr>"
                )
            s_pills = render_category_filter_pills("rt-shm", shm_counts, "streams")
            parts.append(
                '<div class="explorer-panel">'
                '<div class="toolbar" style="margin-top:0;">'
                "<strong>Interactive SHM Stream Explorer</strong>"
                '<div class="toolbar-group">'
                '<button type="button" class="chip-btn" id="rt-shm-zero">'
                "Zero-Reader Streams Only</button>"
                '<input type="search" id="rt-shm-search" class="search-input" '
                'placeholder="Filter SHM stream..."></div></div>'
                f'<div class="toolbar">{s_pills}</div>'
                '<div class="table-wrap" data-sortable="1">'
                '<table id="rt-shm-table"><thead><tr>'
                "<th>Stream</th><th>Category</th><th>Dims</th>"
                '<th style="text-align:right;">Frame [KB]</th>'
                '<th style="text-align:right;">Mean Hz</th>'
                '<th style="text-align:right;">BW [MB/s]</th>'
                '<th style="text-align:right;">Readers</th>'
                f'</tr></thead><tbody>{"".join(s_rows_l)}</tbody></table></div>'
                '<div id="rt-shm-empty-msg" class="cat-empty-note hidden">'
                "No SHM streams match the selected categories or filters.</div></div>"
            )
        parts.append(
            '<script id="runtime-explorer-data" type="application/json">'
            f"{safe_json_embed(runtime_data)}</script>"
        )
        rt_explorer_html = "\n\n".join(parts)

    raw_body = "\n\n".join(p for p in (compute_body, rt_explorer_html) if p)
    toc = extract_toc_html(raw_body)
    if toc and "</h1>" in raw_body:
        h1_end = raw_body.find("</h1>") + 5
        raw_body = raw_body[:h1_end] + "\n\n" + toc + "\n\n" + raw_body[h1_end:]
    toc_items = extract_toc_items(raw_body)

    return render_sim_page_shell(
        title=page_title,
        slug=slug,
        domain_id=domain_id,
        hierarchy=hierarchy,
        active_tab="runtime",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        toc_items=toc_items,
        page_scripts=("runtime_explorer.js",) if runtime_data else (),
        has_mermaid=has_mermaid,
        updated_utc=updated_utc,
    )
