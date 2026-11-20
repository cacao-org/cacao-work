#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Renderers for Simulation Overview, 4 Simulation Sub-Pages, and Technical Reports."""

from __future__ import annotations

import html
import json
from pathlib import Path

from . import (
    COMPUTE_CATEGORIES,
    COMPUTE_CATEGORY_ORDER,
    COMPUTE_IMAGES,
    DATA_EXTS,
    DEFAULT_RUN_COMMAND,
    GUI_CONFIG_IMAGES,
    IMAGE_EXTS,
    VIDEO_EXTS,
    friendly_figure_caption,
)
from .assets import (
    COMMON_JS,
    CONFIG_PAGE_JS,
    CSS_STYLES,
    HOW_TO_RUN_JS,
    OPTICAL_PAGE_JS,
    RUNTIME_PAGE_JS,
)
from .markdown_render import (
    RenderContext,
    convert_markdown_to_html,
    extract_toc_html,
)
from .metrics import classify_shm_category, classify_unit_category, human_bytes


def safe_json_embed(obj: object) -> str:
    """Serialize JSON safely for inline <script type='application/json'> blocks."""
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def build_extra_figures_section(
    staged_files: list[Path],
    ctx: RenderContext,
    *,
    exclude_names: set[str] | None = None,
) -> str:
    """Build HTML section for staged optical figures/videos not yet embedded."""
    staged_names = {p.name for p in staged_files}
    excluded = set(exclude_names or set())
    poster_companions = {
        f"{p.stem}_poster.png"
        for p in staged_files
        if p.suffix.lower() in VIDEO_EXTS and f"{p.stem}_poster.png" in staged_names
    }
    extra_imgs = [
        p
        for p in staged_files
        if p.suffix.lower() in (IMAGE_EXTS | VIDEO_EXTS)
        and p.name not in ctx.referenced_images
        and p.name not in poster_companions
        and p.name not in excluded
    ]
    if not extra_imgs:
        return ""
    blocks = [
        '<h2 id="additional-diagnostic-figures">Additional Diagnostic Figures</h2>',
        '<div class="figure-grid">',
    ]
    from .markdown_render import render_figure_block

    for img_path in extra_imgs:
        cap = friendly_figure_caption(img_path.name)
        blocks.append(render_figure_block(cap, img_path.name, ctx))
    blocks.append("</div>")
    return "\n\n".join(blocks)


def build_telemetry_files_section(staged_files: list[Path]) -> str:
    """Build HTML table listing downloadable telemetry/data artifacts."""
    skip_names = {
        "report_meta.json",
        "study_meta.json",
        "wfs_psf_short_evolution_meta.json",
    }
    data_files = [
        p
        for p in staged_files
        if p.suffix.lower() in DATA_EXTS and p.name not in skip_names
    ]
    if not data_files:
        return ""
    rows = [
        '<h2 id="telemetry-data-files">Telemetry &amp; Data Files</h2>',
        '<div class="table-wrap" data-sortable="1">',
        "<table>",
        "<thead><tr><th>File</th><th>Format</th>"
        '<th style="text-align: right;">Size</th></tr></thead>',
        "<tbody>",
    ]
    for fpath in data_files:
        name_esc = html.escape(fpath.name, quote=False)
        href_esc = html.escape(fpath.name, quote=True)
        fmt = fpath.suffix.lstrip(".").upper() or "FILE"
        sz = human_bytes(fpath.stat().st_size)
        rows.append(
            f'<tr><td><a href="{href_esc}"><code>{name_esc}</code></a></td>'
            f'<td>{fmt}</td><td style="text-align: right;">{sz}</td></tr>'
        )
    rows.extend(["</tbody>", "</table>", "</div>"])
    return "\n\n".join(rows)


def _mermaid_tag(has_mermaid: bool) -> str:
    if not has_mermaid:
        return ""
    return (
        '\n<script type="module">\n'
        "import mermaid from "
        '"https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";\n'
        "mermaid.initialize({ startOnLoad: true, theme: 'default' });\n"
        "</script>"
    )


def render_sim_page_shell(
    *,
    title: str,
    slug: str,
    active_tab: str,
    has_compute_report: bool,
    body_html: str,
    has_mermaid: bool,
    updated_utc: str,
    extra_js: str = "",
) -> str:
    """Wrap a simulation overview or sub-page in the shared responsive shell."""
    title_esc = html.escape(title, quote=False)
    slug_esc = html.escape(slug, quote=False)
    tab_lbls = {
        "overview": "Overview",
        "config": "Configuration",
        "optical": "Optical Performance",
        "runtime": "Runtime Performance",
        "how_to_run": "How to Run It",
    }
    tabs = [
        ("overview", "index.html", "Overview"),
        ("config", "config.html", "Configuration"),
        ("optical", "optical.html", "Optical Performance"),
        ("runtime", "runtime.html", "Runtime Performance"),
        ("how_to_run", "how_to_run.html", "How to Run It"),
    ]
    tab_links: list[str] = []
    for tkey, thref, tlbl in tabs:
        if tkey == "runtime" and not has_compute_report:
            t_disp = f"{tlbl} (N/A)"
        else:
            t_disp = tlbl
        cls = ' class="active"' if active_tab == tkey else ""
        tab_links.append(f'<a href="{thref}"{cls}>{html.escape(t_disp, quote=False)}</a>')

    cur_file = next(h for k, h, _ in tabs if k == active_tab)
    cur_label = tab_lbls.get(active_tab, "Overview")
    mermaid_script = _mermaid_tag(has_mermaid)
    extra_js_tag = f"\n<script>\n{extra_js}\n</script>" if extra_js else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc}</title>
<style>
{CSS_STYLES}
</style>
</head>
<body>
<header class="site-header">
  <div class="nav-inner">
    <a class="brand" href="../index.html">cacao-work &middot; {slug_esc}</a>
    <nav class="nav-links">
      <a href="../index.html#tech-reports">Technical Reports</a>
      <a href="../index.html#simulation-reports">Simulations</a>
      <a href="how_to_run.html">How to Run</a>
      <a href="https://github.com/cacao-org/cacao-work"
         target="_blank" rel="noopener">GitHub</a>
      <button type="button" class="theme-btn" id="theme-toggle">Theme</button>
    </nav>
  </div>
  <div class="subnav-bar">
    <div class="subnav-inner">
      <nav class="subnav-tabs" aria-label="Simulation pages">
        {"".join(tab_links)}
      </nav>
      <div class="sim-switcher" data-current-page="{cur_file}">
        <!-- SIM_SWITCHER_START -->
        <span>Simulation: <code>{slug_esc}</code></span>
        <!-- SIM_SWITCHER_END -->
      </div>
    </div>
  </div>
</header>
<main class="container">
<div class="breadcrumb">
  <a href="../index.html">Front Page</a> /
  <a href="../index.html#simulation-reports">Simulations</a> /
  <a href="index.html"><code>{slug_esc}</code></a> /
  <span>{html.escape(cur_label, quote=False)}</span>
</div>
{body_html}
</main>
<footer class="site-footer">
  <span>Simulation <code>{slug_esc}</code> &middot;
    <a href="https://github.com/cacao-org/cacao-work"
       target="_blank" rel="noopener"><code>cacao-work</code></a></span>
  <span>Updated {html.escape(updated_utc, quote=False)}</span>
</footer>
<script>
{COMMON_JS}
</script>{extra_js_tag}{mermaid_script}
</body>
</html>
"""


def render_cat_badge(cat_key: str, *, short: bool = False) -> str:
    """Render a consistently color-coded pill badge for one of the 4 categories."""
    info = COMPUTE_CATEGORIES.get(cat_key) or COMPUTE_CATEGORIES["loop_operation"]
    key = info["key"]
    lbl = info["short"] if short else info["label"]
    return (
        f'<span class="cat-badge cat-{key}">'
        f'<span class="cat-dot"></span>{html.escape(lbl, quote=False)}</span>'
    )


def _render_section_badges(cats: list[str] | tuple[str, ...]) -> str:
    pills = "".join(render_cat_badge(c) for c in cats)
    return f'<small class="section-cat-badges">{pills}</small>'


def _render_cat_group_row(cat_key: str, colspan: int, count: int) -> str:
    """Render a color-coded category header row inside a grouped <tbody.cat-tbody>."""
    cinfo = COMPUTE_CATEGORIES[cat_key]
    desc = html.escape(cinfo["description"], quote=False)
    return (
        f'<tr class="cat-group-row cat-{cat_key}" data-category="{cat_key}">'
        f'<td colspan="{colspan}"><div class="cat-group-hdr">'
        f'<div class="cat-group-title">{render_cat_badge(cat_key)}'
        f'<span class="muted">{desc}</span></div>'
        f'<span class="cat-group-count">{count} / {count}</span>'
        "</div></td></tr>"
    )


def render_category_legend_html(compact: bool = False) -> str:
    """Render a shared color-coded legend for the 4 canonical categories."""
    items: list[str] = []
    for key in COMPUTE_CATEGORY_ORDER:
        info = COMPUTE_CATEGORIES[key]
        desc = (
            f'<span class="muted">{html.escape(info["description"], quote=False)}</span>'
            if not compact
            else ""
        )
        items.append(
            f'<span class="cat-legend-item">{render_cat_badge(key)}{desc}</span>'
        )
    return f'<div class="cat-legend">{"".join(items)}</div>'


def render_category_filter_pills(
    prefix: str,
    counts: dict[str, int],
    item_noun: str,
) -> str:
    """Render non-exclusive multi-select category pills and All/Clear buttons."""
    btns: list[str] = []
    total = sum(counts.get(k, 0) for k in COMPUTE_CATEGORY_ORDER)
    for key in COMPUTE_CATEGORY_ORDER:
        info = COMPUTE_CATEGORIES[key]
        cnt = counts.get(key, 0)
        btns.append(
            f'<button type="button" class="chip-btn cat-pill cat-{key} active" '
            f'data-{prefix}-cat="{key}" aria-pressed="true" '
            f'title="{html.escape(info["description"], quote=True)}">'
            f'<span class="cat-dot"></span>'
            f'{html.escape(info["label"], quote=False)} ({cnt})</button>'
        )
    btns.append(
        f'<button type="button" class="btn-sm" data-{prefix}-action="all">All</button>'
    )
    btns.append(
        f'<button type="button" class="btn-sm" data-{prefix}-action="none">Clear</button>'
    )
    btns.append(
        f'<span id="{prefix}-visible-count" class="muted">'
        f"Showing {total} / {total} {html.escape(item_noun, quote=False)}</span>"
    )
    return f'<div class="toolbar-group">{"".join(btns)}</div>'


def _mermaid_cat_classdefs() -> str:
    """Return Mermaid classDef lines matching the 4 canonical category colors."""
    return "\n".join(
        f'    classDef {COMPUTE_CATEGORIES[k]["mermaid_class"]} '
        f'{COMPUTE_CATEGORIES[k]["mermaid_def"]}'
        for k in COMPUTE_CATEGORY_ORDER
    )


def _kpi_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{html.escape(label, quote=False)}</div>'
        f'<div class="kpi-value">{value}</div>'
        f"{sub_html}</div>"
    )


def _dynamic_sim_mermaid(
    metrics_data: dict[str, object],
    params: dict[str, str],
) -> str:
    pc = metrics_data.get("predictive_control")
    pc_on = bool(isinstance(pc, dict) and pc.get("enabled"))
    pf_mode = str(pc.get("pf_mode", "ar")).upper() if isinstance(pc, dict) else "AR"
    pf_ord = int(pc.get("pf_order", 8)) if isinstance(pc, dict) else 8
    pf_blk = int(pc.get("pf_blocksize", 128)) if isinstance(pc, dict) else 128
    lo_closed = params.get("llowfs", "CLOSED") == "CLOSED"
    c2d_on = bool(
        isinstance(metrics_data.get("calib_2wfs1dm"), dict)
        and metrics_data["calib_2wfs1dm"].get("enabled")  # type: ignore[union-attr]
    )
    pf_txt = (
        f"Block-EOF(B={pf_blk},P={pf_ord})" if pf_mode == "EOF" else f"Diag AR({pf_ord})"
    )
    pf_edge = f'    MF1 -. "PSOL {pf_txt}" .-> DM1\n' if pc_on else ""
    lo_txt = "Stage 3 LLOWFS<br/>500 Hz CLOSED" if lo_closed else "Stage 3 LLOWFS<br/>OPEN"
    cal_lbl = (
        "Calib: mlat + RM/CM<br/>+ 2-WFS/1-DM SysID"
        if c2d_on
        else "Calib: mlat + RM/CM<br/>+ PSOL Filter"
    )
    c2d_edge = '    W1 -. "mlt.calib2wfs1dm" .-> CAL\n    W2 -.-> CAL\n' if c2d_on else ""
    bmode = html.escape(params.get("bench_mode", "fused"), quote=False)
    return (
        '<div class="mermaid-wrap">\n'
        '<pre class="mermaid">\n'
        "flowchart LR\n"
        '    ATM["milkatmturb<br/>7-layer 2 kHz"]:::cat_simulation --> '
        f'SIM["cacaosim GPU Bench<br/>{bmode}"]:::cat_simulation\n'
        '    SIM --> W1["Stage 1 AO3k<br/>1 kHz J-PyWFS"]:::cat_loop_operation\n'
        '    W1 --> MF1["mfilt-1"]:::cat_loop_operation --> '
        'DM1["DM1 64x64"]:::cat_loop_operation --> SIM\n'
        '    SIM --> W2["Stage 2 SCExAO<br/>2 kHz Vis-PyWFS"]:::cat_loop_operation\n'
        '    W2 --> MF2["mfilt-2"]:::cat_loop_operation --> '
        'DM2["DM2 50x50"]:::cat_loop_operation --> SIM\n'
        '    SIM --> CORO["H-Band Lyot Coro"]:::cat_simulation --> '
        f'W3["{lo_txt}"]:::cat_loop_operation\n'
        '    W3 -. "zpo-2" .-> W2\n'
        f'    CAL["{cal_lbl}"]:::cat_calibration -. "CM / PF" .-> MF1\n'
        '    W1 -.-> ANA["Analysis: mctrlstats<br/>tlog FITS + PSF"]:::cat_analysis\n'
        '    CORO -.-> ANA\n'
        f"{pf_edge}{c2d_edge}{_mermaid_cat_classdefs()}\n"
        "</pre>\n</div>"
    )


def build_sim_overview_html(
    *,
    slug: str,
    title: str,
    preamble_html: str,
    badges: list[str],
    params: dict[str, str],
    cmp_dict: dict[str, object] | None,
    runtime_summary: dict[str, object],
    metrics_data: dict[str, object],
    out_slug_dir: Path,
    staged_files: list[Path],
    has_compute_report: bool,
    updated_utc: str,
) -> str:
    """Build the Simulation Overview hub page (index.html)."""
    c = cmp_dict or {}
    badge_pills = "".join(
        f'<span class="metric-pill">{html.escape(b, quote=False)}</span>'
        for b in badges
    )
    kpis: list[str] = []
    if c.get("stg1_wfe_nm") is not None:
        kpis.append(_kpi_card("Post-AO3k WFE", f'{float(c["stg1_wfe_nm"]):.1f} nm', "Stage 1"))
    if c.get("wfe_nm") is not None:
        kpis.append(_kpi_card("Post-SCExAO WFE", f'{float(c["wfe_nm"]):.1f} nm', "Final Pupil"))
    if c.get("vis_sr_pct") is not None:
        kpis.append(_kpi_card("Visible Strehl", f'{float(c["vis_sr_pct"]):.2f}%', "0.75 um"))
    if c.get("nir_sr_pct") is not None:
        kpis.append(_kpi_card("H-Band Strehl", f'{float(c["nir_sr_pct"]):.2f}%', "1.65 um"))
    if c.get("planet_contrast_3_10ld") is not None:
        kpis.append(
            _kpi_card(
                "Coro Contrast 3-10 l/D",
                f'{float(c["planet_contrast_3_10ld"]):.2e}',
                f'Leakage {float(c.get("coro_leak_pct") or 0.0):.2f}%',
            )
        )
    if params.get("control_law"):
        vr1 = c.get("pf_var_red_stg1_pct")
        sub = f"Stg1 dVar -{float(vr1):.1f}%" if vr1 is not None else "Feedback law"
        kpis.append(
            _kpi_card("Control Law", html.escape(params["control_law"], quote=False), sub)
        )
    if runtime_summary.get("wall_duration_s") is not None:
        kpis.append(
            _kpi_card(
                "Wall / GPU SM",
                f'{float(runtime_summary["wall_duration_s"]):.1f} s',
                f'GPU {float(runtime_summary.get("gpu_sm_pct") or 0):.0f}% | '
                f'{float(runtime_summary.get("sim_cores_mean") or 0):.2f} cores',
            )
        )

    kpi_html = f'<div class="kpi-grid">{"".join(kpis)}</div>' if kpis else ""

    sub_cards = (
        '<div class="subpage-grid">\n'
        '<a class="subpage-card" href="config.html">'
        '<div><h3>1. Configuration</h3>'
        '<p>Telescope pupil, polychromatic passbands, <code>cacaosim-CTRL</code> GUI views, '
        'and searchable <code>.bench</code> hardware explorer.</p></div>'
        '<span class="subpage-cta">Open Configuration &rarr;</span></a>\n'
        '<a class="subpage-card" href="optical.html">'
        '<div><h3>2. Optical Performance</h3>'
        '<p>Interactive WFE/Strehl/modal/coronagraph charts, PSF maps, predictive &amp; SysID '
        'metrics, and slow-motion telemetry video.</p></div>'
        '<span class="subpage-cta">Open Optical Performance &rarr;</span></a>\n'
        '<a class="subpage-card" href="runtime.html">'
        '<div><h3>3. Runtime Performance</h3>'
        '<p>Phase-by-phase CPU/GPU/VRAM breakdown, per-process <code>PROCESSINFO</code> '
        'latency, SHM stream bandwidth, and optimization notes.</p></div>'
        '<span class="subpage-cta">'
        f'{"Open Runtime Performance &rarr;" if has_compute_report else "Runtime Summary &rarr;"}'
        "</span></a>\n"
        '<a class="subpage-card" href="how_to_run.html">'
        '<div><h3>4. How to Run It</h3>'
        '<p>Interactive CLI customizer, launching <code>cacaosim</code>, full CACAO compute '
        'unit catalog, and step-by-step deployment checklist.</p></div>'
        '<span class="subpage-cta">Open How-to-Run Guide &rarr;</span></a>\n'
        "</div>"
    )

    previews: list[str] = []
    for fname, href, lbl in (
        ("cacaosim_gui_schematic.png", "config.html", "Optical Bench Schematic (Configuration)"),
        ("psf_comparison_2x3.png", "optical.html", "Long-Exposure PSFs (Optical Performance)"),
        ("coro_before_after_psf.png", "optical.html", "Lyot Coronagraph (Optical Performance)"),
        ("compute_timeline_4x1.png", "runtime.html", "Compute & Power Timeline (Runtime)"),
    ):
        if (out_slug_dir / fname).is_file():
            f_esc = html.escape(fname, quote=True)
            l_esc = html.escape(lbl, quote=False)
            previews.append(
                '<figure class="report-figure">'
                f'<a href="{href}"><img src="{f_esc}" alt="{l_esc}" loading="lazy"></a>'
                f'<figcaption><a href="{href}">{l_esc}</a></figcaption>'
                "</figure>"
            )
    preview_html = (
        '<h2>Visual Previews</h2><div class="preview-grid">' + "".join(previews) + "</div>"
        if previews
        else ""
    )

    data_files_html = build_telemetry_files_section(staged_files)
    arch_html = (
        "<h2>Simulation Architecture</h2>"
        + _dynamic_sim_mermaid(metrics_data, params)
        + render_category_legend_html(compact=True)
    )
    backlinks_html = (
        "<!-- TECH_REPORT_BACKLINKS_START -->\n"
        '<div class="muted">Referenced by Technical Reports: check the '
        '<a href="../index.html#tech-reports">Front Page Technical Reports table</a>.</div>\n'
        "<!-- TECH_REPORT_BACKLINKS_END -->"
    )

    body = "\n\n".join(
        part
        for part in (
            f"<h1>{html.escape(title, quote=False)}</h1>",
            f'<div class="badge-row">{badge_pills}</div>' if badge_pills else "",
            kpi_html,
            preamble_html,
            "<h2>Simulation Report Sections</h2>",
            sub_cards,
            backlinks_html,
            arch_html,
            preview_html,
            data_files_html,
        )
        if part
    )
    return render_sim_page_shell(
        title=f"{title} — Overview",
        slug=slug,
        active_tab="overview",
        has_compute_report=has_compute_report,
        body_html=body,
        has_mermaid=True,
        updated_utc=updated_utc,
    )


def build_sim_config_html(
    *,
    slug: str,
    title: str,
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
            f'{_render_section_badges(["simulation"])}</h2>'
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
                f"<td><code>{html.escape(str(ld.get('wfs_detector', '?')), quote=False)}</code>"
                "</td>"
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
                f'{_render_section_badges(["loop_operation"])}</h2>'
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
        cat_btns = [
            '<button type="button" class="chip-btn active" data-bench-cat="all">All</button>'
        ]
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
            f'{_render_section_badges(["simulation"])}</h2>'
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

    return render_sim_page_shell(
        title=f"{title} — Configuration",
        slug=slug,
        active_tab="config",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        has_mermaid=gui_mermaid,
        updated_utc=updated_utc,
        extra_js=CONFIG_PAGE_JS,
    )


def build_sim_optical_html(
    *,
    slug: str,
    title: str,
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
            f'{_render_section_badges(["analysis"])}</h2>'
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

    return render_sim_page_shell(
        title=f"{title} — Optical Performance",
        slug=slug,
        active_tab="optical",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        has_mermaid=has_mermaid,
        updated_utc=updated_utc,
        extra_js=OPTICAL_PAGE_JS if tabs else "",
    )


def build_sim_runtime_html(
    *,
    slug: str,
    title: str,
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
                pcat = str(
                    p.get("category") or classify_unit_category(str(p.get("name", "")))
                )
                if pcat not in proc_by_cat:
                    pcat = "loop_operation"
                proc_by_cat[pcat].append(p)
            proc_counts = {k: len(proc_by_cat[k]) for k in COMPUTE_CATEGORY_ORDER}
            p_tbodies: list[str] = []
            for pcat in COMPUTE_CATEGORY_ORDER:
                grp = proc_by_cat[pcat]
                if not grp:
                    continue
                grp_hdr = _render_cat_group_row(pcat, 9, len(grp))
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
                scat = str(
                    s.get("category") or classify_shm_category(str(s.get("name", "")))
                )
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

    return render_sim_page_shell(
        title=page_title,
        slug=slug,
        active_tab="runtime",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        has_mermaid=has_mermaid,
        updated_utc=updated_utc,
        extra_js=RUNTIME_PAGE_JS if runtime_data else "",
    )


def build_sim_how_to_run_html(
    *,
    slug: str,
    title: str,
    params: dict[str, str],
    metrics_data: dict[str, object],
    units: list[dict[str, object]],
    repro_md: str,
    ctx: RenderContext,
    has_compute_report: bool,
    updated_utc: str,
) -> str:
    """Build the user-oriented How to Run It sub-page (how_to_run.html)."""
    ctx.has_mermaid = False
    repro_html, _ = (
        convert_markdown_to_html(repro_md, ctx, {})
        if repro_md
        else ("", "")
    )
    repro_mermaid = ctx.has_mermaid

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

    seeing_v = params.get("seeing", '0.60"').rstrip('"')
    phys_v = params.get("phys_time", "5.0 s").split()[0]
    ov_v = params.get("oversample", "4x").rstrip("x")
    defaults = {
        "slug": slug,
        "seeing": seeing_v,
        "phys_time": phys_v,
        "bench_mode": params.get("bench_mode", "fused"),
        "oversample": ov_v,
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

    cmd_badges_all = _render_section_badges(COMPUTE_CATEGORY_ORDER)
    cmd_badges_sim = _render_section_badges(["simulation"])
    cmd_badges_loop = _render_section_badges(["calibration", "loop_operation"])
    customizer_html = (
        '<h2 id="interactive-command-customizer">'
        "1. Turnkey Command &amp; Interactive Parameter Customizer</h2>\n"
        "<p>Pre-loaded with this simulation's exact parameters. Adjust any field below to "
        "generate custom commands for <code>run-ao3k-scexao.sh</code>, "
        "<code>cacaosim-bench</code>, and <code>cacaoloop-ao3k-scexao.milk</code>:</p>\n"
        '<div class="explorer-panel">\n'
        '<div class="customizer-grid">\n'
        '<div class="field-box"><label for="cust-seeing">Seeing [arcsec]</label>'
        '<input id="cust-seeing" type="number" step="0.05" min="0.2" max="2.0"></div>\n'
        '<div class="field-box"><label for="cust-phys_time">Phys Time [s]</label>'
        '<input id="cust-phys_time" type="number" step="0.5" min="0.5" max="60"></div>\n'
        '<div class="field-box"><label for="cust-bench_mode">cacaosim Mode</label>'
        '<select id="cust-bench_mode"><option value="fused">fused (csim_htsim)</option>'
        '<option value="modular">modular (per-element FPS)</option></select></div>\n'
        '<div class="field-box"><label for="cust-oversample">Oversample K</label>'
        '<select id="cust-oversample"><option value="1">1x (2 kHz)</option>'
        '<option value="2">2x (4 kHz)</option><option value="4">4x (8 kHz)</option>'
        "</select></div>\n"
        '<div class="field-box"><label for="cust-gain1">Stage-1 Gain</label>'
        '<input id="cust-gain1" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        '<div class="field-box"><label for="cust-gain2">Stage-2 Gain</label>'
        '<input id="cust-gain2" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        '<div class="field-box"><label for="cust-gain3">Stage-3 Gain</label>'
        '<input id="cust-gain3" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        '<div class="field-box"><label for="cust-llowfs">Stage-3 LLOWFS</label>'
        '<select id="cust-llowfs"><option value="closed">CLOSED</option>'
        '<option value="open">OPEN (--no-lowfs)</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_mode">Predictive Control</label>'
        '<select id="cust-pf_mode"><option value="off">OFF (Integrator)</option>'
        '<option value="ar">PSOL Diagonal AR(P)</option>'
        '<option value="eof">PSOL Cross-Mode Block-EOF</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_order">PF Order P</label>'
        '<select id="cust-pf_order"><option value="4">4</option><option value="8">8</option>'
        '<option value="16">16</option><option value="32">32</option>'
        '<option value="64">64</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_blocksize">EOF Block Size B</label>'
        '<select id="cust-pf_blocksize"><option value="64">64</option>'
        '<option value="128">128</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_reg">PF Reg lambda</label>'
        '<input id="cust-pf_reg" type="text"></div>\n'
        '<div class="field-box"><label for="cust-calib_2wfs1dm">2-WFS/1-DM Calib</label>'
        '<select id="cust-calib_2wfs1dm"><option value="off">OFF</option>'
        '<option value="on">ON (--calib-2wfs1dm)</option></select></div>\n'
        '<div class="field-box"><label for="cust-telemetry">Telemetry Mode</label>'
        '<select id="cust-telemetry"><option value="none">none</option>'
        '<option value="standard">standard</option>'
        '<option value="speckle">speckle</option>'
        '<option value="truth">truth</option></select></div>\n'
        "</div>\n"
        '<div class="toolbar">'
        '<span id="cust-advice" class="muted"></span>'
        '<button type="button" class="btn-sm" id="cust-reset">Reset to Simulation Defaults</button>'
        "</div>\n"
        f'<h4>Exact Simulation Command (<code>run-ao3k-scexao.sh</code>) {cmd_badges_all}</h4>'
        f'<pre><code id="cmd-turnkey">{html.escape(raw_cmd, quote=False)}</code></pre>\n'
        f'<h4>Optical Bench Only (<code>cacaosim-bench</code>) {cmd_badges_sim}</h4>'
        '<pre><code id="cmd-cacaosim"></code></pre>\n'
        f'<h4>CACAO Loops Only (<code>cacaoloop-ao3k-scexao.milk</code>) {cmd_badges_loop}</h4>'
        '<pre><code id="cmd-cacaoloop"></code></pre>\n'
        '<script id="howtorun-defaults" type="application/json">'
        f"{safe_json_embed(defaults)}</script>\n"
        "</div>"
    )

    cacaosim_html = (
        '<h2 id="launching-cacaosim">2. Launching <code>cacaosim</code> for This Configuration '
        f"{_render_section_badges(['simulation'])}</h2>\n"
        "<p>Always isolate shared memory under <code>/dev/shm/cacao_*</code> so "
        "<code>/milk/shm</code> remains untouched. Inspect or launch the declarative optical "
        "bench <code>benches/ao3k_scexao/ao3k_scexao.bench</code> as follows:</p>\n"
        "<pre><code>source env.sh\n"
        "export MILK_SHM_DIR=/dev/shm/cacao_demo MILK_PROC_DIR=/dev/shm/cacao_demo/proc\n"
        'mkdir -p "${MILK_PROC_DIR}"\n\n'
        "# Inspect schematic in terminal or launch interactive cacaosim-CTRL GUI\n"
        "cacaosim-bench view -c benches/ao3k_scexao/ao3k_scexao.bench\n"
        "cacaosim-bench gui  -c benches/ao3k_scexao/ao3k_scexao.bench\n\n"
        "# Deploy optical bench with zero turbulence first for response-matrix calibration\n"
        f'cacaosim-bench deploy -c benches/ao3k_scexao/ao3k_scexao.bench '
        f'--mode {html.escape(defaults["bench_mode"], quote=False)} '
        f'--oversample {html.escape(ov_v, quote=False)} --atmturb --seeing {seeing_v}\n'
        'milk-fps-set "csim_htsim.turb_gain=0.0"  # Toggle to 1.0 after calibration</code></pre>\n'
        '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
        "<th>Direction</th><th>Category</th><th>SHM Stream(s)</th>"
        "<th>Grid / Rate</th><th>Description</th>"
        "</tr></thead><tbody>"
        '<tr class="cat-row cat-simulation"><td>Input</td>'
        f'<td>{render_cat_badge("simulation")}</td>'
        "<td><code>outarraypha</code></td><td>256x256 @ 2 kHz</td>"
        "<td>Atmospheric phase screen from <code>csim_atmturb</code></td></tr>"
        '<tr class="cat-row cat-loop_operation"><td>Input</td>'
        f'<td>{render_cat_badge("loop_operation")}</td>'
        "<td><code>dm01disp</code>, <code>dm02disp</code></td>"
        "<td>64x64 / 50x50</td><td>Stage-1 &amp; Stage-2 DM surface actuators</td></tr>"
        '<tr class="cat-row cat-simulation"><td>Output (WFS)</td>'
        f'<td>{render_cat_badge("simulation")}</td>'
        "<td><code>csim_wfs_nir</code>, <code>csim_wfs_vis</code>, "
        "<code>csim_wfs_lowfs</code></td><td>160x160 / 120x120 / 64x64</td>"
        "<td>Polychromatic Stage 1/2/3 wavefront sensor frames</td></tr>"
        '<tr class="cat-row cat-analysis"><td>Output (Sci)</td>'
        f'<td>{render_cat_badge("analysis")}</td>'
        "<td><code>psf_vis_*</code>, <code>psf_nir_*</code>, "
        "<code>coro_pre_lyot</code></td><td>256x256</td>"
        "<td>Short/long-exposure Visible, H-band, and Lyot coronagraph cameras</td></tr>"
        "</tbody></table></div>"
    )

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
        grp_hdr = _render_cat_group_row(ucat, 9, len(grp))
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
        + f"{_mermaid_cat_classdefs()}\n</pre>\n</div>\n"
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

    pf_step = (
        f"CACAO_PF_MODE={defaults['pf_mode']} CACAO_PF_ORDER={defaults['pf_order']} "
        "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 testol\n"
        f"CACAO_PF_MODE={defaults['pf_mode']} CACAO_PF_ORDER={defaults['pf_order']} "
        "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 pf-on 0.90"
        if pc_on
        else "# Predictive control optional: --stage 1 testol && --stage 1 pf-on 0.90"
    )
    steps: list[tuple[str, str, str, tuple[str, ...]]] = [
        (
            "Step 1: Initialize Isolated SHM Sandbox & Environment",
            "source env.sh\nexport MILK_SHM_DIR=/dev/shm/cacao_run\n"
            "export MILK_PROC_DIR=/dev/shm/cacao_run/proc\nmkdir -p \"${MILK_PROC_DIR}\"",
            "simulation",
            ("simulation", "loop_operation"),
        ),
        (
            "Step 2: Launch cacaosim Optical Bench (Zero Turbulence for Calibration)",
            f"cacaosim-bench deploy -c benches/ao3k_scexao/ao3k_scexao.bench "
            f"--mode {defaults['bench_mode']} --oversample {ov_v} --atmturb\n"
            "milk-fps-set \"csim_htsim.turb_gain=0.0\"",
            "simulation",
            ("simulation",),
        ),
        (
            "Step 3: Deploy CACAO Loop Compute Units (Stage 1, Stage 2 + ZPO, Stage 3)",
            "CACAO_LOOPROOTDIR=/tmp/ao3k ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 1 deploy\n"
            "CACAO_LOOPROOTDIR=/tmp/scexao ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 2 deploy\n"
            "CACAO_LOOPROOTDIR=/tmp/llowfs ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 3 deploy",
            "loop_operation",
            ("loop_operation",),
        ),
        (
            "Step 4: Measure Latency (mlat), Acquire Hadamard RM & Solve SVD Control Matrix",
            "CACAO_LOOPROOTDIR=/tmp/ao3k ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 1 calibrate --save-rm _work/ao3k_scexao_rm/stage1\n"
            "CACAO_LOOPROOTDIR=/tmp/scexao ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 2 calibrate --save-rm _work/ao3k_scexao_rm/stage2\n"
            "CACAO_LOOPROOTDIR=/tmp/llowfs ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 3 calibrate --save-rm _work/ao3k_scexao_rm/stage3",
            "calibration",
            ("calibration",),
        ),
        (
            "Step 5: Calibrate PSOL Latency (testOL) & Enable Predictive Filtering",
            pf_step,
            "calibration",
            ("calibration", "loop_operation"),
        ),
        (
            "Step 6: Ramp Atmospheric Turbulence & Close Loops Sequentially (1 -> 2 -> 3)",
            "milk-fps-set \"csim_htsim.turb_gain=1.0\"\n"
            "CACAO_LOOPROOTDIR=/tmp/ao3k ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            f"--stage 1 close {defaults['gain1']}\n"
            "CACAO_LOOPROOTDIR=/tmp/scexao ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            f"--stage 2 close {defaults['gain2']}\n"
            + (
                "CACAO_LOOPROOTDIR=/tmp/llowfs ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
                f"--stage 3 close {defaults['gain3']}"
                if defaults["llowfs"] == "closed"
                else "# Stage 3 LLOWFS remains OPEN for this configuration"
            ),
            "loop_operation",
            ("loop_operation", "simulation"),
        ),
        (
            "Step 7: Inspect Live TUIs & Record Telemetry / 2-WFS+1-DM Calibration",
            "milk-fpsCTRL        # Inspect & tune all FPS parameters live\n"
            "cacao-modalstatsTUI 1   # Inspect Stage-1 modal residuals\n"
            + (
                "milk-mlt-calib2wfs1dm ... # Probe-free Mab/Mdb/Mda_virt system ID"
                if c2d_on
                else "milk-stream-wait -t 10 psf_nir_final+100"
            ),
            "analysis",
            ("analysis", "calibration") if c2d_on else ("analysis",),
        ),
        (
            "Step 8: Safe Open, Zero DMs & Clean Teardown",
            "for s in 3 2 1; do ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage ${s} open; done\n"
            "for s in 3 2 1; do ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage ${s} teardown --purge-dm; done\n"
            "cacaosim-bench teardown",
            "loop_operation",
            ("loop_operation", "simulation"),
        ),
    ]
    low_level_step3 = (
        '<details style="margin-top:0.45rem;"><summary><strong>Show low-level '
        "<code>milk-fps-init</code> / <code>milk-fps-set</code> / <code>milk-stream-link</code> "
        "primitives (Stage 1 example)</strong></summary>"
        "<pre><code>milk-fps-init DMch2disp-01 cacao-fpsexec-dmcomb\n"
        "milk-fps-init acquWFS-1    cacao-fpsexec-cacaoiot-acquireWFS\n"
        "milk-fps-init wfs2cmodeval-1 milk-fpsexec-linalg-MVMextract\n"
        "milk-fps-init mfilt-1      cacao-fpsexec-mfilt\n"
        "milk-fps-init mvalC2dm-1   milk-fpsexec-linalg-MVMextract\n"
        "milk-stream-link csim_wfs_nir=aol1_wfsim\n"
        "milk-fps-set acquWFS-1.insname=aol1_wfsim mfilt-1.loopgain="
        f"{html.escape(defaults['gain1'], quote=False)} mfilt-1.comp.OLmodes=ON\n"
        "milk-fps-runstart DMch2disp-01 acquWFS-1 wfs2cmodeval-1 mfilt-1 mvalC2dm-1"
        "</code></pre></details>"
    )
    chk_items = "".join(
        f'<div class="checklist-item cat-{pcat}">'
        f'<label class="checklist-hdr"><input type="checkbox" class="deploy-step-cb"> '
        f"<span>{html.escape(stitle, quote=False)}</span> "
        f'{"".join(render_cat_badge(b) for b in b_cats)}</label>'
        f"<pre><code>{html.escape(scmd, quote=False)}</code></pre>"
        f"{low_level_step3 if idx == 2 else ''}"
        "</div>"
        for idx, (stitle, scmd, pcat, b_cats) in enumerate(steps)
    )
    checklist_html = (
        '<h2 id="step-by-step-deployment">4. Step-by-Step Deployment Checklist</h2>\n'
        '<div class="toolbar">'
        '<span id="deploy-progress-text"><strong>0 / 8 steps completed</strong></span>'
        '<div class="progress-track"><div class="progress-fill" id="deploy-progress-fill" '
        'style="width:0%"></div></div></div>\n'
        f'<div class="checklist">{chk_items}</div>'
    )

    adapt_html = (
        '<h2 id="adapting-to-real-hardware">5. Adapting This Configuration to Real Hardware</h2>\n'
        "<ul>\n"
        f'<li>{render_cat_badge("simulation")} <strong>Swap WFS &amp; DM streams</strong>: '
        "Replace <code>csim_wfs_*</code> with your camera frame-grabber SHM streams via "
        "<code>CACAO_WFSSTREAM=&lt;cam_shm&gt;</code>, and replace simulated DM channels with "
        "your physical DM driver reading <code>dm01disp</code> / <code>dm02disp</code>.</li>\n"
        f'<li>{render_cat_badge("loop_operation")} <strong>GPU &amp; NUMA pinning</strong>: '
        "Keep <code>wfs2cmodeval-*</code>, <code>mvalC2dm-*</code>, and <code>zpo-2</code> on "
        "the same NUMA node as the CUDA GPU (<code>MILK_NUMANODE=auto</code>) and disable unused "
        "monitor SHM streams to save memory bandwidth.</li>\n"
        f'<li>{render_cat_badge("calibration")} {render_cat_badge("loop_operation")} '
        "<strong>Tune key loop parameters</strong>: Start conservatively with "
        "<code>svdlim=0.004</code> and <code>gain=0.30..0.35</code>, measure on-sky "
        "<code>selfRM</code> optical gain, then enable <code>--predictive --pf-mode ar "
        "--pf-order 16</code> (or <code>Block-EOF</code> after 12 s of stationary sky).</li>\n"
        "</ul>"
    )

    repro_block = repro_html or (
        '<h2 id="reproducibility-github-provenance">Reproducibility &amp; GitHub Provenance</h2>'
        '<p>See the <a href="../index.html#reproduce-results">Front Page Reproduction Guide</a> '
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

    return render_sim_page_shell(
        title=f"{title} — How to Run It",
        slug=slug,
        active_tab="how_to_run",
        has_compute_report=has_compute_report,
        body_html=raw_body,
        has_mermaid=True,
        updated_utc=updated_utc,
        extra_js=HOW_TO_RUN_JS,
    )


def build_tech_report_html(
    *,
    slug: str,
    title: str,
    study_meta: dict[str, object],
    report_body_html: str,
    extra_figs_html: str,
    data_files_html: str,
    has_repro_section: bool,
    has_mermaid: bool,
    updated_utc: str,
) -> str:
    """Build a standalone Technical Report page (index.html)."""
    title_esc = html.escape(title, quote=False)
    slug_esc = html.escape(slug, quote=False)
    nav_lbl = html.escape(
        str(study_meta.get("nav_label") or "Technical Report"), quote=False
    )
    badges = study_meta.get("badges")
    badge_html = ""
    if isinstance(badges, list) and badges:
        badge_html = (
            '<div class="badge-row">'
            + "".join(
                f'<span class="metric-pill">{html.escape(str(b), quote=False)}</span>'
                for b in badges
            )
            + "</div>"
        )
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

    repro_href = (
        "#reproducibility-github-provenance"
        if has_repro_section
        else "../index.html#reproduce-results"
    )
    mermaid_script = _mermaid_tag(has_mermaid)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc}</title>
<style>
{CSS_STYLES}
</style>
</head>
<body>
<header class="site-header">
  <div class="nav-inner">
    <a class="brand" href="../index.html">cacao-work &middot; {nav_lbl}</a>
    <nav class="nav-links">
      <a href="../index.html#tech-reports">Technical Reports</a>
      <a href="../index.html#simulation-reports">Simulations</a>
      <a href="index.html" class="active">{nav_lbl}</a>
      <a href="{repro_href}">Reproduce</a>
      <a href="https://github.com/cacao-org/cacao-work"
         target="_blank" rel="noopener">GitHub</a>
      <button type="button" class="theme-btn" id="theme-toggle">Theme</button>
    </nav>
  </div>
</header>
<main class="container">
<div class="breadcrumb">
  <a href="../index.html">Front Page</a> /
  <a href="../index.html#tech-reports">Technical Reports</a> /
  <span><code>{slug_esc}</code></span>
</div>
{raw_body}
</main>
<footer class="site-footer">
  <span>Technical Report <code>{slug_esc}</code> &middot;
    <a href="https://github.com/cacao-org/cacao-work"
       target="_blank" rel="noopener"><code>cacao-work</code></a></span>
  <span>Updated {html.escape(updated_utc, quote=False)}</span>
</footer>
<script>
{COMMON_JS}
</script>{mermaid_script}
</body>
</html>
"""
