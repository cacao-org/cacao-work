#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation Overview hub page renderer (<slug>/index.html)."""

from __future__ import annotations

import html
from pathlib import Path

from ..markdown.sim_split import extract_toc_items
from .fragments import (
    build_telemetry_files_section,
    kpi_card,
    mermaid_cat_classdefs,
    render_category_legend_html,
    render_domain_badge,
)
from .sim_shell import render_sim_page_shell
from .turbulence import render_sim_turbulence_card


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
        f"{pf_edge}{c2d_edge}{mermaid_cat_classdefs()}\n"
        "</pre>\n</div>"
    )


def build_sim_overview_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    hierarchy: dict[str, object],
    preamble_html: str,
    badges: list[str],
    params: dict[str, str],
    cmp_dict: dict[str, object] | None,
    runtime_summary: dict[str, object],
    metrics_data: dict[str, object],
    out_slug_dir: Path,
    staged_files: list[Path],
    has_compute_report: bool,
    has_pyrwfs_report: bool = False,
    updated_utc: str,
    turb_profile: dict[str, object] | None = None,
) -> str:
    """Build the Simulation Overview hub page (index.html)."""
    c = cmp_dict or {}
    domain_map: dict[str, dict[str, object]] = hierarchy.get("domain_map") or {}  # type: ignore[assignment]
    badge_pills = (
        render_domain_badge(domain_id, domain_map, rel_root="..")
        + "".join(
            f'<span class="metric-pill">{html.escape(b, quote=False)}</span>'
            for b in badges
        )
    )

    kpis: list[str] = []
    if c.get("stg1_wfe_nm") is not None:
        kpis.append(kpi_card("Post-AO3k WFE", f'{float(c["stg1_wfe_nm"]):.1f} nm', "Stage 1"))
    if c.get("wfe_nm") is not None:
        kpis.append(kpi_card("Post-SCExAO WFE", f'{float(c["wfe_nm"]):.1f} nm', "Final Pupil"))
    if c.get("vis_sr_pct") is not None:
        kpis.append(kpi_card("Visible Strehl", f'{float(c["vis_sr_pct"]):.2f}%', "0.75 um"))
    if c.get("nir_sr_pct") is not None:
        kpis.append(kpi_card("H-Band Strehl", f'{float(c["nir_sr_pct"]):.2f}%', "1.65 um"))
    if c.get("planet_contrast_3_10ld") is not None:
        kpis.append(
            kpi_card(
                "Coro Contrast 3-10 l/D",
                f'{float(c["planet_contrast_3_10ld"]):.2e}',
                f'Leakage {float(c.get("coro_leak_pct") or 0.0):.2f}%',
            )
        )
    if params.get("control_law"):
        vr1 = c.get("pf_var_red_stg1_pct")
        sub = f"Stg1 dVar -{float(vr1):.1f}%" if vr1 is not None else "Feedback law"
        kpis.append(kpi_card("Control Law", html.escape(params["control_law"], quote=False), sub))
    if runtime_summary.get("wall_duration_s") is not None:
        kpis.append(
            kpi_card(
                "Wall / GPU SM",
                f'{float(runtime_summary["wall_duration_s"]):.1f} s',
                f'GPU {float(runtime_summary.get("gpu_sm_pct") or 0):.0f}% | '
                f'{float(runtime_summary.get("sim_cores_mean") or 0):.2f} cores',
            )
        )

    kpi_html = f'<div class="kpi-grid">{"".join(kpis)}</div>' if kpis else ""
    pyrwfs_card = (
        '<a class="subpage-card" href="pyrwfs.html">'
        "<div><h3>3. Pyramid WFS</h3>"
        "<p>Live Stage-1/Stage-2 packed-zone flux budget, defocus-invariant Strehl proxy, "
        "6-DOF pupil registration, quad-cell jitter, scintillation &amp; spider LWE maps.</p></div>"
        '<span class="subpage-cta">Open Pyramid WFS &rarr;</span></a>\n'
        if has_pyrwfs_report
        else ""
    )
    rt_num = "4" if has_pyrwfs_report else "3"
    htr_num = "5" if has_pyrwfs_report else "4"
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
        f"{pyrwfs_card}"
        '<a class="subpage-card" href="runtime.html">'
        f'<div><h3>{rt_num}. Runtime Performance</h3>'
        '<p>Phase-by-phase CPU/GPU/VRAM breakdown, per-process <code>PROCESSINFO</code> '
        'latency, SHM stream bandwidth, and optimization notes.</p></div>'
        '<span class="subpage-cta">'
        f'{"Open Runtime Performance &rarr;" if has_compute_report else "Runtime Summary &rarr;"}'
        "</span></a>\n"
        '<a class="subpage-card" href="how_to_run.html">'
        f'<div><h3>{htr_num}. How to Run It</h3>'
        '<p>Interactive CLI customizer, launching <code>cacaosim</code>, full CACAO compute '
        'unit catalog, and step-by-step deployment checklist.</p></div>'
        '<span class="subpage-cta">Open How-to-Run Guide &rarr;</span></a>\n'
        "</div>"
    )

    previews: list[str] = []
    for fname, href, lbl in (
        ("cacaosim_gui_schematic.png", "config.html", "Optical Bench Schematic (Configuration)"),
        ("perturb_summary_2x2.png", "optical.html", "Realistic Perturbations: Wind, Vib & Petaling"),
        ("psf_comparison_2x3.png", "optical.html", "Long-Exposure PSFs (Optical Performance)"),
        ("coro_before_after_psf.png", "optical.html", "Lyot Coronagraph (Optical Performance)"),
        (
            "pyrwfs_flux_strehl_2x2.png",
            "pyrwfs.html",
            "Pyramid WFS Flux Budget & Strehl Proxy (Pyramid WFS)",
        ),
        (
            "pyrwfs_pupil_maps_2x4.png",
            "pyrwfs.html",
            "Pyramid WFS 2D Zone & Scintillation Maps (Pyramid WFS)",
        ),
        (
            "eof_pf_matrix_3d.png",
            "optical.html#eof-3d-predictive-matrix",
            "3D Modal Predictive Matrix PF (EOF)",
        ),
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
        '<h2 id="visual-previews">Visual Previews</h2><div class="preview-grid">'
        + "".join(previews)
        + "</div>"
        if previews
        else ""
    )

    data_files_html = build_telemetry_files_section(staged_files)
    arch_html = (
        '<h2 id="simulation-architecture">Simulation Architecture</h2>'
        + _dynamic_sim_mermaid(metrics_data, params)
        + render_category_legend_html(compact=True)
    )
    backlinks_html = (
        "<!-- TECH_REPORT_BACKLINKS_START -->\n"
        '<div class="muted">Referenced by Technical Reports: check the '
        '<a href="../index.html#tech-reports">Technical Reports directory</a>.</div>\n'
        "<!-- TECH_REPORT_BACKLINKS_END -->"
    )

    turb_card_html = render_sim_turbulence_card(
        turb_profile,
        rel_root="..",
        compact=False,
        has_perturb_fig=(out_slug_dir / "perturb_summary_2x2.png").is_file(),
    )

    body = "\n\n".join(
        part
        for part in (
            f"<h1>{html.escape(title, quote=False)}</h1>",
            f'<div class="badge-row">{badge_pills}</div>' if badge_pills else "",
            kpi_html,
            preamble_html,
            turb_card_html,
            '<h2 id="simulation-report-sections">Simulation Report Sections</h2>',
            sub_cards,
            backlinks_html,
            arch_html,
            preview_html,
            data_files_html,
        )
        if part
    )
    toc_items = extract_toc_items(body)
    return render_sim_page_shell(
        title=f"{title} — Overview",
        slug=slug,
        domain_id=domain_id,
        hierarchy=hierarchy,
        active_tab="overview",
        has_compute_report=has_compute_report,
        has_pyrwfs_report=has_pyrwfs_report,
        body_html=body,
        toc_items=toc_items,
        has_mermaid=True,
        updated_utc=updated_utc,
    )
