#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation How-to-Run sub-page renderer (<slug>/how_to_run.html)."""

from __future__ import annotations

import html

from ..constants import COMPUTE_CATEGORY_ORDER, DEFAULT_RUN_COMMAND
from ..extractors.runtime import classify_unit_category
from ..markdown.context import RenderContext
from ..markdown.parser import convert_markdown_to_html
from ..markdown.sim_split import extract_toc_html, extract_toc_items
from .fragments import (
    mermaid_cat_classdefs,
    render_cat_badge,
    render_cat_group_row,
    render_category_filter_pills,
    render_category_legend_html,
)
from .sim_how_to_run_sections import (
    render_cacaosim_launcher_section,
    render_customizer_section,
    render_deployment_checklist_section,
    render_real_hardware_section,
)
from .sim_shell import render_sim_page_shell


def build_sim_how_to_run_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    hierarchy: dict[str, object],
    params: dict[str, str],
    metrics_data: dict[str, object],
    units: list[dict[str, object]],
    repro_md: str,
    ctx: RenderContext,
    has_compute_report: bool,
    updated_utc: str,
    run_options: dict[str, object] | None = None,
) -> str:
    """Build the user-oriented How to Run It sub-page (how_to_run.html)."""
    ctx.has_mermaid = False
    repro_html, _ = (
        convert_markdown_to_html(repro_md, ctx, {})
        if repro_md
        else ("", "")
    )

    repro = metrics_data.get("reproducibility")
    raw_cmd = (
        str(repro.get("run_command", DEFAULT_RUN_COMMAND))
        if isinstance(repro, dict)
        else DEFAULT_RUN_COMMAND
    )
    pc = metrics_data.get("predictive_control")
    pc_on = bool(isinstance(pc, dict) and pc.get("enabled"))
    c2d = metrics_data.get("calib_2wfs1dm")
    c2d_on = bool(isinstance(c2d, dict) and c2d.get("enabled"))

    defaults = {
        "slug": slug,
        "seeing": params.get("seeing", '0.60"').rstrip('"'),
        "phys_time": params.get("phys_time", "5.0 s").split()[0],
        "bench_mode": params.get("bench_mode", "fused"),
        "oversample": params.get("oversample", "4x").rstrip("x"),
        "gain1": params.get("gain1", "0.35"),
        "gain2": params.get("gain2", "0.35"),
        "gain3": params.get("gain3", "0.20"),
        "llowfs": "open" if params.get("llowfs") == "OPEN" else "closed",
        "pf_mode": (
            str(pc.get("pf_mode", "ar")).lower() if (pc_on and isinstance(pc, dict)) else "off"
        ),
        "pf_order": str(int(pc.get("pf_order", 16))) if isinstance(pc, dict) else "16",
        "pf_blocksize": str(int(pc.get("pf_blocksize", 128))) if isinstance(pc, dict) else "128",
        "pf_reg": str(pc.get("pf_reg", 0.005)) if isinstance(pc, dict) else "0.005",
        "calib_2wfs1dm": "on" if c2d_on else "off",
        "telemetry": params.get("telemetry", "speckle"),
    }

    customizer_html = render_customizer_section(raw_cmd, defaults, run_options=run_options)
    cacaosim_html = render_cacaosim_launcher_section(defaults)

    cu_by_cat: dict[str, list[dict[str, object]]] = {k: [] for k in COMPUTE_CATEGORY_ORDER}
    for u in units:
        ucat = str(u.get("category") or classify_unit_category(str(u.get("unit", ""))))
        if ucat not in cu_by_cat:
            ucat = "loop_operation"
        cu_by_cat[ucat].append(u)
    cu_counts = {k: len(cu_by_cat[k]) for k in COMPUTE_CATEGORY_ORDER}
    cu_pills = render_category_filter_pills("cu", cu_counts, "units")

    cu_tbodies: list[str] = []
    for ucat in COMPUTE_CATEGORY_ORDER:
        grp = cu_by_cat[ucat]
        if not grp:
            continue
        grp_hdr = render_cat_group_row(ucat, 9, len(grp))
        grp_rows: list[str] = []
        for u in grp:
            st_l = html.escape(str(u["stage"]).lower(), quote=True)
            stat_pill = (
                '<span class="metric-pill metric-pill-accent">Active</span>'
                if u["active"]
                else '<span class="metric-pill">Standby/Open</span>'
            )
            lat_str = (
                f'{float(u["exec_p50_us"]):.1f} / {float(u["exec_p99_us"]):.1f} us'
                if u.get("exec_p50_us") is not None
                else "&mdash;"
            )
            cpu_str = (
                f'{float(u["cl_cpu_pct"]):.1f}%'
                if u.get("cl_cpu_pct") is not None
                else "&mdash;"
            )
            fps_p = u.get("fps_params") if isinstance(u.get("fps_params"), dict) else {}
            fps_str = " &middot; ".join(
                f"<code>{html.escape(str(k))}={html.escape(str(v))}</code>"
                for k, v in fps_p.items()
            )
            grp_rows.append(
                f'<tr class="unit-row cat-row cat-{ucat}" data-category="{ucat}" '
                f'data-stage="{st_l}">'
                f'<td><code>{html.escape(str(u["unit"]), quote=False)}</code> {stat_pill}</td>'
                f'<td><code>{html.escape(str(u["binary"]), quote=False)}</code></td>'
                f"<td>{render_cat_badge(ucat)}</td>"
                f'<td>{html.escape(str(u["stage"]), quote=False)}</td>'
                f'<td>{html.escape(str(u["rate"]), quote=False)}</td>'
                f'<td>{html.escape(str(u["backend"]), quote=False)}</td>'
                f'<td style="text-align:right;">{cpu_str}</td>'
                f'<td style="text-align:right;">{lat_str}</td>'
                f'<td class="wrap-cell">{html.escape(str(u["role"]), quote=False)}</td>'
                "</tr>"
                f'<tr class="detail-row cat-detail-row cat-{ucat} hidden" '
                f'data-category="{ucat}"><td colspan="9">'
                f'<strong>Inputs:</strong> <code>{html.escape(str(u["inputs"]))}</code> &rarr; '
                f'<strong>Outputs:</strong> <code>{html.escape(str(u["outputs"]))}</code><br>'
                f"<strong>FPS Params:</strong> {fps_str}</td></tr>"
            )
        cu_tbodies.append(
            f'<tbody class="cat-tbody cat-{ucat}" data-category="{ucat}">'
            f'{grp_hdr}{"".join(grp_rows)}</tbody>'
        )

    cu_mermaid = (
        '<div class="mermaid-wrap">\n<pre class="mermaid">\n'
        "flowchart LR\n"
        '    AT["csim_atmturb"]:::cat_simulation --> '
        'HT["csim_htsim Bench"]:::cat_simulation\n'
        '    HT --> ACQ["acquWFS-N<br/>aolN_imWFS2"]:::cat_loop_operation\n'
        '    ZPO["zpo-2 (Stage 2)<br/>aol2_wfszpo"]:::cat_loop_operation -.-> ACQ\n'
        '    ACQ --> W2M["wfs2cmodeval-N<br/>aolN_modevalWFS"]:::cat_loop_operation\n'
        '    W2M --> MFILT["mfilt-N<br/>aolN_modevalDM + OL"]:::cat_loop_operation\n'
        '    MFILT --> M2D["mvalC2dm-N<br/>aolN_dmC"]:::cat_loop_operation --> '
        'DMC["DMch2disp-0N<br/>dm0Ndisp"]:::cat_loop_operation --> HT\n'
        '    ACQ -. "Hresp / mlat" .-> '
        'CAL["Calib: mlat / measlinresp<br/>compstrCM / mkPF"]:::cat_calibration '
        '-. "CM / PFmat" .-> MFILT\n'
        + (
            '    MFILT -.-> MK["mkARPF / mkEOFPF"]:::cat_calibration -.-> '
            'APP["applyARPF / applyEOFPF"]:::cat_loop_operation -.-> MFILT\n'
            if pc_on
            else ""
        )
        + '    W2M -.-> STATS["Analysis: mctrlstats-N<br/>&amp; tlog FITS"]:::cat_analysis\n'
        + "    HT -.-> STATS\n"
        + f"{mermaid_cat_classdefs()}\n</pre>\n</div>\n"
    )
    cu_html = (
        '<h2 id="cacao-compute-units">3. CACAO &amp; Simulator Compute Units + SHM Wiring</h2>\n'
        f"{cu_mermaid}"
        f"{render_category_legend_html(compact=True)}"
        "<p>Select one or more category pills below (multi-select) or click any unit row to "
        "inspect its exact input/output SHM streams and <code>milk-fps-set</code> parameters:</p>\n"
        f'<div class="toolbar">{cu_pills}'
        '<input type="search" id="cu-search" class="search-input" '
        'placeholder="Search unit, binary, or SHM stream..."></div>\n'
        '<div class="table-wrap" data-sortable="1"><table id="compute-units-table"><thead><tr>'
        "<th>FPS Unit</th><th>Binary</th><th>Category</th><th>Stage</th><th>Rate</th>"
        '<th>Backend</th><th style="text-align:right;">CL CPU%</th>'
        '<th style="text-align:right;">p50 / p99</th>'
        "<th>Role (click row for SHM &amp; params)</th>"
        f'</tr></thead>{"".join(cu_tbodies)}</table></div>'
        '<div id="cu-empty-msg" class="cat-empty-note hidden">'
        "No compute units match the selected categories or search query.</div>"
    )

    checklist_html = render_deployment_checklist_section(defaults, pc_on=pc_on, c2d_on=c2d_on)
    adapt_html = render_real_hardware_section()
    repro_block = repro_html or (
        '<h2 id="reproducibility-github-provenance">Reproducibility &amp; GitHub Provenance</h2>'
        '<p>See the <a href="../stack/index.html#reproduce-results">Stack &amp; Reproduction Guide</a> '
        "and repository table for full source build instructions.</p>"
    )

    raw_body = "\n\n".join(
        [
            f"<h1>{html.escape(title, quote=False)} &middot; How to Run It</h1>",
            render_category_legend_html(compact=False),
            customizer_html,
            cacaosim_html,
            cu_html,
            checklist_html,
            adapt_html,
            repro_block,
        ]
    )
    toc = extract_toc_html(raw_body)
    if toc:
        h1_end = raw_body.find("</h1>") + 5
        raw_body = raw_body[:h1_end] + "\n\n" + toc + "\n\n" + raw_body[h1_end:]
    toc_items = extract_toc_items(raw_body)

    return render_sim_page_shell(
        title=f"{title} — How to Run It",
        slug=slug,
        domain_id=domain_id,
        hierarchy=hierarchy,
        active_tab="how_to_run",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        toc_items=toc_items,
        page_scripts=("how_to_run.js",),
        has_mermaid=True,
        updated_utc=updated_utc,
    )
