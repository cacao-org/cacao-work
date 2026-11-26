#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation Configuration sub-page renderer (<slug>/config.html)."""

from __future__ import annotations

import html
from pathlib import Path

from ..constants import friendly_figure_caption
from ..extractors.common import load_json_safe
from ..extractors.options_catalog import (
    RUNNER_CLI_OPTIONS,
    is_nondefault_bench_value,
    make_runner_opt_anchor,
)
from ..markdown.context import RenderContext
from ..markdown.parser import convert_markdown_to_html
from ..markdown.sim_split import extract_toc_html, extract_toc_items
from .fragments import render_section_badges
from .sim_shell import render_sim_page_shell
from .turbulence import render_sim_turbulence_card


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
    has_pyrwfs_report: bool = False,
    updated_utc: str,
    bench_opt_lookup: dict[tuple[str, str], dict[str, object]] | None = None,
    turb_profile: dict[str, object] | None = None,
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
        trs_list: list[str] = []
        for k, v in t_rows:
            val_esc = html.escape(str(v), quote=False)
            if k == "Atmosphere Profile":
                val_td = (
                    f'<a class="opt-ref-link" href="../turbulence/index.html">'
                    f"<code>{val_esc}</code> (Default Model Spec &rarr;)</a>"
                )
            else:
                val_td = f"<code>{val_esc}</code>"
            trs_list.append(
                f"<tr><td><strong>{html.escape(k, quote=False)}</strong></td>"
                f"<td>{val_td}</td></tr>"
            )
        trs = "".join(trs_list)
        summary_blocks.append(
            '<h2 id="system-summary">System &amp; Atmosphere Parameters '
            f'{render_section_badges(["simulation"])}</h2>'
            '<div class="table-wrap" data-sortable="1"><table><thead>'
            "<tr><th>Parameter</th><th>Value</th></tr></thead>"
            f"<tbody>{trs}</tbody></table></div>"
        )

    turb_cfg_html = render_sim_turbulence_card(
        turb_profile,
        rel_root="..",
        compact=False,
        detailed_table=True,
        has_perturb_fig=(out_slug_dir / "perturb_summary_2x2.png").is_file(),
    )
    if turb_cfg_html:
        summary_blocks.append(turb_cfg_html)

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
        opt_map = bench_opt_lookup or {}
        cats = sorted({str(s["category"]) for s in bench_sections})
        cat_btns = ['<button type="button" class="chip-btn active" data-bench-cat="all">All</button>']
        for c in cats:
            cat_btns.append(
                f'<button type="button" class="chip-btn" data-bench-cat="{html.escape(c)}">'
                f"{html.escape(c)}</button>"
            )
        cards: list[str] = []
        flat_rows: list[str] = []
        for s in bench_sections:
            hdr_raw = str(s["header"])
            cat_raw = str(s["category"])
            hdr = html.escape(hdr_raw, quote=False)
            cat = html.escape(cat_raw, quote=True)
            params_d = s["params"]
            assert isinstance(params_d, dict)
            kv_parts: list[str] = []
            for k, v in params_d.items():
                k_str = str(k)
                v_str = str(v)
                opt_meta = opt_map.get((cat_raw, k_str))
                k_esc = html.escape(k_str, quote=False)
                v_esc = html.escape(v_str, quote=False)
                dflt_str = str(opt_meta.get("default") or "") if opt_meta else ""
                unit_str = str(opt_meta.get("unit") or "") if opt_meta else ""
                desc_str = str(opt_meta.get("description") or "") if opt_meta else ""
                nondef = is_nondefault_bench_value(v_str, opt_meta)

                if opt_meta and opt_meta.get("anchor"):
                    anc = html.escape(str(opt_meta["anchor"]), quote=True)
                    tip_bits = [
                        b
                        for b in (
                            f"default: {dflt_str}" if dflt_str else "",
                            f"unit: {unit_str}" if unit_str else "",
                            desc_str,
                        )
                        if b
                    ]
                    tip = html.escape(" · ".join(tip_bits), quote=True)
                    key_link = (
                        f'<a class="opt-ref-link" href="../reference/index.html#{anc}" '
                        f'title="{tip}">{k_esc}</a>'
                    )
                else:
                    key_link = k_esc

                if nondef:
                    def_tip = html.escape(f"Default: {dflt_str}", quote=True)
                    dd_html = (
                        f'<dd class="opt-nondefault">{v_esc}'
                        f'<span class="opt-nondefault-tag" title="{def_tip}">custom</span></dd>'
                    )
                    val_cell = (
                        f'<code class="opt-nondefault">{v_esc}</code>'
                        f'<span class="opt-nondefault-tag" title="{def_tip}">custom</span>'
                    )
                else:
                    dd_html = f"<dd>{v_esc}</dd>"
                    val_cell = f"<code>{v_esc}</code>"

                kv_parts.append(f"<dt>{key_link}</dt>{dd_html}")
                dflt_cell = (
                    f"<code>{html.escape(dflt_str, quote=False)}</code>"
                    if dflt_str
                    else '<span class="muted">&mdash;</span>'
                )
                flat_rows.append(
                    f'<tr class="bench-flat-row" data-cat="{cat}">'
                    f"<td><code>[{hdr}]</code></td>"
                    f"<td><code>{key_link}</code></td>"
                    f"<td>{val_cell}</td>"
                    f"<td>{dflt_cell}</td>"
                    f'<td class="wrap-cell">{html.escape(desc_str, quote=False) or "&mdash;"}</td>'
                    "</tr>"
                )
            cards.append(
                f'<div class="bench-card" data-cat="{cat}">'
                f'<div class="bench-card-hdr"><strong><code>[{hdr}]</code></strong>'
                f'<span class="metric-pill">{cat}</span></div>'
                f'<dl class="bench-kv">{"".join(kv_parts)}</dl></div>'
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
            '<p class="muted">Click any key to open its full definition in the '
            '<a href="../reference/index.html">Options Reference</a>. '
            'Values differing from schema defaults are highlighted.</p>'
            '<div class="toolbar">'
            f'<div class="toolbar-group">{"".join(cat_btns)}</div>'
            '<div class="toolbar-group">'
            '<button type="button" class="chip-btn active" id="bench-view-cards">Cards</button>'
            '<button type="button" class="chip-btn" id="bench-view-table">Flat Table</button>'
            '<input type="search" id="bench-search" class="search-input" '
            'placeholder="Filter components, keys, or streams...">'
            "</div></div>"
            f'<div class="bench-grid" id="bench-card-grid">{"".join(cards)}</div>'
            '<div class="table-wrap hidden" id="bench-flat-wrap" data-sortable="1">'
            '<table id="bench-flat-table"><thead><tr>'
            "<th>Section</th><th>Key</th><th>Value</th><th>Default</th><th>Description</th>"
            f'</tr></thead><tbody>{"".join(flat_rows)}</tbody></table></div>'
            f"{raw_bench}"
        )

    run_opts_html = ""
    ropts_path = out_slug_dir / "run_options.json"
    if ropts_path.is_file():
        ropts_data = load_json_safe(ropts_path)
        ropts_map = (
            ropts_data.get("options")
            if isinstance(ropts_data.get("options"), dict)
            else ropts_data
        )
        if isinstance(ropts_map, dict) and ropts_map:
            runner_by_key = {str(o["key"]): o for o in RUNNER_CLI_OPTIONS}
            key_aliases: dict[str, str] = {
                "fast_calib": "no_fast_calib",
                "enable_lowfs": "no_lowfs",
                "run_selfrm": "no_selfrm",
                "run_tlm_analysis": "no_tlm_analysis",
                "eff_oversample": "oversample",
                "eff_psf_navg": "psf_navg",
                "selfrm_onsky_iter": "selfrm_iter",
            }
            r_rows: list[str] = []
            for rk, rv in ropts_map.items():
                if rv is None or rv == "":
                    continue
                rk_s = str(rk)
                rv_s = str(rv)
                rmeta = runner_by_key.get(rk_s) or runner_by_key.get(key_aliases.get(rk_s, ""))
                if rmeta:
                    flag_s = str(rmeta["flag"])
                    anc = html.escape(make_runner_opt_anchor(flag_s), quote=True)
                    key_cell = (
                        f'<a class="opt-ref-link" href="../reference/index.html#{anc}">'
                        f"<code>{html.escape(flag_s, quote=False)}</code></a>"
                    )
                    desc_cell = html.escape(str(rmeta.get("description") or ""), quote=False)
                else:
                    key_cell = f"<code>{html.escape(rk_s, quote=False)}</code>"
                    desc_cell = '<span class="muted">Resolved runtime parameter</span>'
                r_rows.append(
                    f"<tr><td>{key_cell}</td>"
                    f"<td><code>{html.escape(rv_s, quote=False)}</code></td>"
                    f'<td class="wrap-cell">{desc_cell}</td></tr>'
                )
            if r_rows:
                run_opts_html = (
                    '<h2 id="resolved-runner-options">Resolved Runner Options '
                    '(<code>run_options.json</code>) '
                    f'{render_section_badges(["simulation", "loop_operation"])}</h2>'
                    '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
                    "<th>Option / Flag</th><th>Resolved Value</th><th>Description</th>"
                    f'</tr></thead><tbody>{"".join(r_rows)}</tbody></table></div>'
                )

    raw_body = "\n\n".join(
        p
        for p in (
            f"<h1>{html.escape(title, quote=False)} &middot; Configuration</h1>",
            *summary_blocks,
            run_opts_html,
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
        has_pyrwfs_report=has_pyrwfs_report,
        body_html=raw_body,
        toc_items=toc_items,
        page_scripts=("config_page.js",),
        has_mermaid=gui_mermaid,
        updated_utc=updated_utc,
    )
