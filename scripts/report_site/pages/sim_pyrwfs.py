#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation Pyramid WFS Telemetry sub-page renderer (<slug>/pyrwfs.html)."""

from __future__ import annotations

import html
from pathlib import Path

from ..constants import friendly_figure_caption
from ..extractors.common import human_bytes
from ..markdown.sim_split import extract_toc_html, extract_toc_items
from .fragments import kpi_card, render_section_badges, safe_json_embed
from .sim_shell import render_sim_page_shell


def _fmt_pct(val: object, signed: bool = False, digits: int = 2) -> str:
    if not isinstance(val, (int, float)):
        return "&mdash;"
    v = float(val) * 100.0
    fmt = f"{{:{'+' if signed else ''}.{digits}f}}%"
    return f"<code>{fmt.format(v)}</code>"


def _fmt_num(val: object, signed: bool = False, digits: int = 3, unit: str = "") -> str:
    if not isinstance(val, (int, float)):
        return "&mdash;"
    fmt = f"{{:{'+' if signed else ''}.{digits}f}}"
    u = f" {unit}" if unit else ""
    return f"<code>{fmt.format(float(val))}{u}</code>"


def _build_kpi_row(
    stages: dict[str, dict[str, object]],
    wl_data: dict[str, object] | None = None,
) -> str:
    cards: list[str] = []
    for skey, s_tag in (("stage1", "Stage 1 (AO3k NIR)"), ("stage2", "Stage 2 (SCExAO Vis)")):
        sd = stages.get(skey)
        if not isinstance(sd, dict):
            continue
        fl = sd.get("flux") if isinstance(sd.get("flux"), dict) else {}
        al = sd.get("alignment") if isinstance(sd.get("alignment"), dict) else {}
        xc = sd.get("crosscheck") if isinstance(sd.get("crosscheck"), dict) else {}
        fp = float(fl.get("f_pup_mean", 0.0) or 0.0) * 100.0
        df = float(fl.get("df_pup_mean", 0.0) or 0.0) * 100.0
        f0 = float(sd.get("f_pup0", 0.0) or 0.0) * 100.0
        r_s = xc.get("corr_dfpup_vs_1mS")
        r_note = f" | r(Δf,1−S)={float(r_s):+.2f}" if isinstance(r_s, (int, float)) else ""
        cards.append(
            kpi_card(
                f"{s_tag} In-Pupil Flux",
                f"{fp:.1f}%",
                f"Δf_pup {df:+.2f}% vs flat {f0:.1f}%{r_note}",
            )
        )
        max_d = max(
            float(al.get("pup_dx_max_abs", 0.0) or 0.0),
            float(al.get("pup_dy_max_abs", 0.0) or 0.0),
        )
        cmin = float(al.get("pup_corr_min", 1.0) or 1.0)
        cards.append(
            kpi_card(
                f"{s_tag} Pupil Drift",
                f"{max_d:.2f} pix",
                f"max |dx,dy| | min edge ZNCC {cmin:.3f}",
            )
        )
    for skey, s_tag in (("stage1", "Stg1"), ("stage2", "Stg2")):
        sd = stages.get(skey)
        if not isinstance(sd, dict):
            continue
        jt = sd.get("jitter") if isinstance(sd.get("jitter"), dict) else {}
        wf = sd.get("wavefront") if isinstance(sd.get("wavefront"), dict) else {}
        sc_raw = float(wf.get("scint_idx_mean", 0.0) or 0.0)
        sc_deb = wf.get("scint_debias_mean")
        sc_txt = (
            f"scint deb {float(sc_deb):.4f} (raw {sc_raw:.4f})"
            if isinstance(sc_deb, (int, float))
            else f"scint {sc_raw:.3f}"
        )
        cards.append(
            kpi_card(
                f"{s_tag} Jitter / Scint / LWE",
                f"{float(jt.get('q_tt_rms_quad', 0.0) or 0.0):.4f}",
                f"{sc_txt} | "
                f"curl {float(wf.get('curl_ratio_mean', 0.0) or 0.0):.2f} | "
                f"LWE {float(wf.get('lwe_metric_mean', 0.0) or 0.0):.3f}",
            )
        )
    if isinstance(wl_data, dict) and wl_data.get("enabled"):
        mov = [l for l in (wl_data.get("layers") or []) if isinstance(l, dict) and not l.get("is_static")]
        n_mov = int(wl_data.get("n_moving_layers", len(mov)) or 0)
        top_v = max((float(l.get("speed_mps", 0.0) or 0.0) for l in mov), default=0.0)
        max_z_km = max(
            (float(l["z_m"]) / 1000.0 for l in mov if isinstance(l.get("z_m"), (int, float))),
            default=0.0,
        )
        f_lbl = str(wl_data.get("atmturb_fresnel_label") or "")
        z_note = f" | max z {max_z_km:.1f} km" if max_z_km >= 0.5 else ""
        cards.append(
            kpi_card(
                "Wind Layers (mlt-windlayers)",
                f"{n_mov} moving",
                f"top {top_v:.1f} m/s{z_note}" + (f" | {f_lbl}" if f_lbl else ""),
            )
        )
    return f'<div class="kpi-grid">{"".join(cards)}</div>' if cards else ""


def _build_explorer_panel(pyrwfs_data: dict[str, object]) -> str:
    ts_map = pyrwfs_data.get("timeseries")
    if not isinstance(ts_map, dict) or not ts_map:
        return ""
    has_both = "stage1" in ts_map and "stage2" in ts_map
    stg_btns = ""
    if has_both:
        stg_btns = (
            '<div class="toolbar-group">'
            '<button type="button" class="chip-btn active" data-pyr-stg="both">Both Stages</button>'
            '<button type="button" class="chip-btn" data-pyr-stg="stage1">Stage 1 (NIR)</button>'
            '<button type="button" class="chip-btn" data-pyr-stg="stage2">Stage 2 (Vis)</button>'
            "</div>"
        )
    tabs = (
        ("flux", "Flux Budget"),
        ("dfpup", "Δf_pup Strehl Proxy"),
        ("aniso", "Aniso & Nonlinearity"),
        ("align", "6-DOF Pupil Drift"),
        ("jitter", "Quad-Cell Jitter"),
        ("wavefront", "Scint, Curl & LWE"),
    )
    t_btns = "".join(
        f'<button type="button" class="chip-btn{" active" if i == 0 else ""}" '
        f'data-pyr-tab="{k}">{lbl}</button>'
        for i, (k, lbl) in enumerate(tabs)
    )
    embed = {"timeseries": ts_map}
    return (
        '<h2 id="interactive-pyrwfs-explorer">Interactive Pyramid WFS Telemetry Explorer '
        f'{render_section_badges(["analysis"])}</h2>\n'
        '<div class="explorer-panel">\n'
        '  <div class="toolbar" style="margin-top:0;">\n'
        f'    <div class="toolbar-group">{t_btns}</div>\n'
        f"    {stg_btns}\n"
        "  </div>\n"
        '  <div class="canvas-wrap">\n'
        '    <canvas id="pyrwfs-canvas" class="chart-canvas"></canvas>\n'
        '    <div id="pyrwfs-tooltip" class="canvas-tooltip"></div>\n'
        "  </div>\n"
        '  <div id="pyrwfs-legend" class="opt-legend"></div>\n'
        '  <script id="pyrwfs-explorer-data" type="application/json">'
        f"{safe_json_embed(embed)}</script>\n"
        "</div>"
    )


def _build_metrics_tables(stages: dict[str, dict[str, object]]) -> str:
    ordered = [
        (sk, stages[sk]) for sk in ("stage1", "stage2") if isinstance(stages.get(sk), dict)
    ]
    if not ordered:
        return ""

    flux_rows: list[str] = []
    align_rows: list[str] = []
    wf_rows: list[str] = []
    geom_blocks: list[str] = []

    for _, sd in ordered:
        lbl = html.escape(str(sd.get("label") or f"Stage {sd.get('stage')}"), quote=False)
        lam = float(sd.get("lambda_um", 0.0) or 0.0)
        mod = sd.get("mod_rad_ld")
        mod_s = f"{float(mod):g} l/D" if isinstance(mod, (int, float)) else "default"
        nfr = int(sd.get("n_frames", 0) or 0)
        rate = float(sd.get("eff_rate_hz", sd.get("rate_hz", 0.0)) or 0.0)
        fl = sd.get("flux") if isinstance(sd.get("flux"), dict) else {}
        al = sd.get("alignment") if isinstance(sd.get("alignment"), dict) else {}
        jt = sd.get("jitter") if isinstance(sd.get("jitter"), dict) else {}
        wf = sd.get("wavefront") if isinstance(sd.get("wavefront"), dict) else {}
        hl = sd.get("health") if isinstance(sd.get("health"), dict) else {}
        xc = sd.get("crosscheck") if isinstance(sd.get("crosscheck"), dict) else {}

        flux_rows.append(
            "<tr>"
            f"<td><strong>{lbl}</strong><br><span class=\"muted\">"
            f"<code>{lam:.2f} um</code>, mod <code>{html.escape(mod_s, quote=False)}</code>, "
            f"<code>{nfr}</code> fr @ <code>{rate:.0f} Hz</code></span></td>"
            f'<td style="text-align:right;">{_fmt_pct(sd.get("f_pup0"), digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_pct(fl.get("f_pup_mean"), digits=2)} '
            f'<span class="muted">&plusmn;{_fmt_pct(fl.get("f_pup_std"), digits=2)}</span></td>'
            f'<td style="text-align:right;">{_fmt_pct(fl.get("df_pup_mean"), signed=True, digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_pct(fl.get("f_diam_mean"), digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_pct(fl.get("f_bH_mean"), digits=2)} / '
            f'{_fmt_pct(fl.get("f_bV_mean"), digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_pct(fl.get("f_out_mean"), digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_num(fl.get("aniso_mean"), signed=True, digits=3)}</td>'
            f'<td style="text-align:right;">{_fmt_num(fl.get("nl_ratio_mean"), digits=3)}</td>'
            f'<td style="text-align:right;">{_fmt_num(xc.get("corr_dfpup_vs_1mS"), signed=True, digits=2)}</td>'
            "</tr>"
        )

        align_rows.append(
            "<tr>"
            f"<td><strong>{lbl}</strong></td>"
            f'<td style="text-align:right;">{_fmt_num(al.get("pup_dx_mean"), signed=True, digits=3)} '
            f'<span class="muted">&plusmn;{_fmt_num(al.get("pup_dx_std"), digits=3)}</span></td>'
            f'<td style="text-align:right;">{_fmt_num(al.get("pup_dy_mean"), signed=True, digits=3)} '
            f'<span class="muted">&plusmn;{_fmt_num(al.get("pup_dy_std"), digits=3)}</span></td>'
            f'<td style="text-align:right;">{_fmt_num(al.get("pup_ds_mean"), signed=True, digits=3)}</td>'
            f'<td style="text-align:right;">{_fmt_num(al.get("pup_dast_mean"), signed=True, digits=3)}</td>'
            f'<td style="text-align:right;">{_fmt_num(al.get("pup_rot_mrad_mean"), signed=True, digits=2, unit="mrad")}</td>'
            f'<td style="text-align:right;">{_fmt_num(al.get("pup_corr_mean"), digits=3)} '
            f'<span class="muted">(min {_fmt_num(al.get("pup_corr_min"), digits=3)})</span></td>'
            "</tr>"
        )

        sc_deb = wf.get("scint_debias_mean")
        sc_cell = (
            f'{_fmt_num(sc_deb, digits=4)} <span class="muted">(raw {_fmt_num(wf.get("scint_idx_mean"), digits=4)})</span>'
            if isinstance(sc_deb, (int, float))
            else _fmt_num(wf.get("scint_idx_mean"), digits=4)
        )
        wf_rows.append(
            "<tr>"
            f"<td><strong>{lbl}</strong></td>"
            f'<td style="text-align:right;">{_fmt_num(jt.get("q_tt_rms_quad"), digits=4)}</td>'
            f'<td style="text-align:right;">{_fmt_num(jt.get("qx_mean"), signed=True, digits=4)} / '
            f'{_fmt_num(jt.get("qy_mean"), signed=True, digits=4)}</td>'
            f'<td style="text-align:right;">{sc_cell}</td>'
            f'<td style="text-align:right;">{_fmt_num(wf.get("curl_ratio_mean"), digits=3)}</td>'
            f'<td style="text-align:right;">{_fmt_num(wf.get("lwe_metric_mean"), digits=4)}</td>'
            f'<td style="text-align:right;">{_fmt_num(xc.get("corr_lwe_vs_petal"), signed=True, digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_num(hl.get("bg_mean"), digits=1, unit="ADU")}</td>'
            f'<td style="text-align:right;">{_fmt_num(hl.get("flux_ok_pct"), digits=1, unit="%")}</td>'
            "</tr>"
        )

        pgeom = al.get("pupgeom") if isinstance(al.get("pupgeom"), list) else []
        if pgeom:
            g_rows = "".join(
                "<tr>"
                f"<td><code>{html.escape(str(r.get('quadrant', '')), quote=False)}</code></td>"
                f'<td style="text-align:right;">{_fmt_num(r.get("xc_pix"), digits=2)}</td>'
                f'<td style="text-align:right;">{_fmt_num(r.get("yc_pix"), digits=2)}</td>'
                f'<td style="text-align:right;">{_fmt_num(r.get("rout_pix"), digits=2)}</td>'
                f'<td style="text-align:right;">{_fmt_num(r.get("corr"), digits=4)}</td>'
                "</tr>"
                for r in pgeom
                if isinstance(r, dict)
            )
            geom_blocks.append(
                f"<div><h3>{lbl} — Detected 4-Pupil Geometry</h3>"
                '<div class="table-wrap"><table><thead><tr>'
                "<th>Pupil</th>"
                '<th style="text-align:right;">x<sub>c</sub> [pix]</th>'
                '<th style="text-align:right;">y<sub>c</sub> [pix]</th>'
                '<th style="text-align:right;">R<sub>out</sub> [pix]</th>'
                '<th style="text-align:right;">Edge ZNCC</th>'
                f"</tr></thead><tbody>{g_rows}</tbody></table></div></div>"
            )

    parts = [
        '<h2 id="flux-budget-and-strehl-proxy">Flux Partitioning, Nonlinearity &amp; Strehl-Proxy Summary '
        f'{render_section_badges(["analysis"])}</h2>',
        '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
        "<th>PyWFS Stage</th>"
        '<th style="text-align:right;">Flat f<sub>pup,0</sub></th>'
        '<th style="text-align:right;">CL f<sub>pup</sub></th>'
        '<th style="text-align:right;">&Delta;f<sub>pup</sub></th>'
        '<th style="text-align:right;">Diamond</th>'
        '<th style="text-align:right;">Bridges H / V</th>'
        '<th style="text-align:right;">Outer</th>'
        '<th style="text-align:right;">Aniso</th>'
        '<th style="text-align:right;">NL Ratio</th>'
        '<th style="text-align:right;">r(&Delta;f, 1&minus;S)</th>'
        f"</tr></thead><tbody>{''.join(flux_rows)}</tbody></table></div>",
        '<h2 id="pupil-alignment-6dof">6-DOF Edge-Based Pupil Alignment Tracking '
        f'{render_section_badges(["loop_operation", "analysis"])}</h2>',
        '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
        "<th>PyWFS Stage</th>"
        '<th style="text-align:right;">dx [pix]</th>'
        '<th style="text-align:right;">dy [pix]</th>'
        '<th style="text-align:right;">ds [pix]</th>'
        '<th style="text-align:right;">Astig d<sub>ast</sub> [pix]</th>'
        '<th style="text-align:right;">Rot</th>'
        '<th style="text-align:right;">Min 4-Pupil ZNCC</th>'
        f"</tr></thead><tbody>{''.join(align_rows)}</tbody></table></div>",
        '<h2 id="jitter-scintillation-lwe">Quad-Cell Jitter, Scintillation, Slope Curl &amp; Spider LWE '
        f'{render_section_badges(["analysis"])}</h2>',
        '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
        "<th>PyWFS Stage</th>"
        '<th style="text-align:right;">TT Jitter RMS</th>'
        '<th style="text-align:right;">qx / qy Mean</th>'
        '<th style="text-align:right;">Scint (Deb / Raw)</th>'
        '<th style="text-align:right;">Curl / Div</th>'
        '<th style="text-align:right;">Spider LWE</th>'
        '<th style="text-align:right;">r(LWE, Petal)</th>'
        '<th style="text-align:right;">Corner BG</th>'
        '<th style="text-align:right;">Flux OK</th>'
        f"</tr></thead><tbody>{''.join(wf_rows)}</tbody></table></div>",
    ]
    if geom_blocks:
        parts.append(f'<div class="two-col-grid">{"".join(geom_blocks)}</div>')
    return "\n\n".join(parts)


def _build_windlayers_section(
    wl_data: dict[str, object] | None,
    out_slug_dir: Path,
) -> str:
    if not isinstance(wl_data, dict) or not wl_data.get("enabled"):
        return ""

    layers = wl_data.get("layers") if isinstance(wl_data.get("layers"), list) else []
    gt_layers = (
        wl_data.get("ground_truth_layers")
        if isinstance(wl_data.get("ground_truth_layers"), list)
        else []
    )
    fres_lbl = html.escape(str(wl_data.get("atmturb_fresnel_label") or ""), quote=False)
    in_pg = str(wl_data.get("in_pupgeom") or "").strip()
    pg_src = f"SHM <code>{html.escape(in_pg, quote=False)}</code> + autocal" if in_pg else "standalone temporal-variance autocal"

    wl_kpis = [
        kpi_card(
            "Detected Layers",
            f"{int(wl_data.get('n_moving_layers', 0) or 0)} moving",
            f"{int(wl_data.get('nlayers', len(layers)) or 0)} total | "
            f"{int(wl_data.get('n_matched_gt', 0) or 0)} matched Maunakea truth",
        ),
        kpi_card(
            "Scintillation Physics",
            fres_lbl or "fresnel=0",
            f"zenith {float(wl_data.get('zenith_deg', 30.0) or 30.0):.0f}&deg; "
            f"(airmass {float(wl_data.get('airmass', 1.155) or 1.155):.3f}) | "
            f"&lambda;={float(wl_data.get('lambda_um', 1.22) or 1.22):.2f} &mu;m",
        ),
        kpi_card(
            "Pupil Geometry & Dark",
            f"D = {float(wl_data.get('diampix', 0.0) or 0.0):.1f} pix",
            f"dx {float(wl_data.get('dx_m', 0.0) or 0.0):.4f} m | "
            f"bg {float(wl_data.get('bg_adu', 0.0) or 0.0):.1f} ADU | "
            f"{int(wl_data.get('npix', 0) or 0)} mask pix",
        ),
        kpi_card(
            "Integration",
            f"{float(wl_data.get('tint_s', 0.0) or 0.0):.2f} s",
            f"{int(wl_data.get('nframes', 0) or 0)} fr ({int(wl_data.get('nblocks', 0) or 0)} blocks) | "
            f"flux_in {float(wl_data.get('fluxin', 0.0) or 0.0)*100:.1f}%",
        ),
    ]

    l_rows: list[str] = []
    for l in layers:
        if not isinstance(l, dict):
            continue
        idx = int(l.get("index", 0) or 0)
        is_st = bool(l.get("is_static"))
        tag_s = f"<strong>L{idx}</strong>" + (' <span class="muted">(static)</span>' if is_st else "")
        z_v = l.get("z_m")
        ze_v = l.get("zerr_m")
        if isinstance(z_v, (int, float)):
            z_cell = f"<code>{float(z_v):.0f} m</code>"
            if isinstance(ze_v, (int, float)):
                z_cell += f' <span class="muted">&plusmn;{float(ze_v):.0f}</span>'
        else:
            z_cell = "&mdash;"
        gt_idx = l.get("matched_gt_index")
        if gt_idx is not None:
            gt_reg = html.escape(str(l.get("matched_gt_regime") or ""), quote=False)
            gt_cell = (
                f"<strong>GT{int(gt_idx)}</strong> ({gt_reg})<br>"
                f'<span class="muted"><code>{float(l.get("matched_gt_speed_mps", 0.0)):.1f} m/s</code> '
                f'@ <code>{float(l.get("matched_gt_dir_deg", 0.0)):.0f}&deg;</code>, '
                f'z<sub>LOS</sub>=<code>{float(l.get("matched_gt_z_los_m", 0.0)):.0f} m</code></span>'
            )
            dv = l.get("dv_mps")
            dz = l.get("dz_m")
            err_parts = []
            if isinstance(dv, (int, float)):
                err_parts.append(f"&Delta;v=<code>{float(dv):.2f} m/s</code>")
            if isinstance(dz, (int, float)):
                err_parts.append(f"&Delta;z=<code>{float(dz):+.0f} m</code>")
            err_cell = "<br>".join(err_parts) if err_parts else "&mdash;"
        elif is_st:
            gt_cell = '<span class="muted">Static / Dome / Thermal Petaling</span>'
            err_cell = "&mdash;"
        else:
            gt_cell = '<span class="muted">&mdash;</span>'
            err_cell = "&mdash;"

        l_rows.append(
            "<tr>"
            f"<td>{tag_s}</td>"
            f'<td style="text-align:right;">{_fmt_num(l.get("speed_mps"), digits=2, unit="m/s")}</td>'
            f'<td style="text-align:right;">{_fmt_num(l.get("dir_deg"), digits=1, unit="&deg;")}</td>'
            f'<td style="text-align:right;">{_fmt_num(l.get("vx_mps"), signed=True, digits=2)} / '
            f'{_fmt_num(l.get("vy_mps"), signed=True, digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_num(l.get("snr"), digits=1)}</td>'
            f'<td style="text-align:right;">{z_cell}</td>'
            f'<td style="text-align:right;">{_fmt_num(l.get("coh"), digits=2)}</td>'
            f'<td style="text-align:right;">{_fmt_pct(l.get("frac_k"), digits=1)} / '
            f'{_fmt_pct(l.get("frac_i"), digits=1)}</td>'
            f"<td>{gt_cell}</td>"
            f'<td style="text-align:right;">{err_cell}</td>'
            "</tr>"
        )

    tbl_html = (
        '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
        "<th>Layer</th>"
        '<th style="text-align:right;">Speed</th>'
        '<th style="text-align:right;">Dir</th>'
        '<th style="text-align:right;">v<sub>x</sub> / v<sub>y</sub> [m/s]</th>'
        '<th style="text-align:right;">SNR</th>'
        '<th style="text-align:right;">z<sub>LOS</sub> (&plusmn;&sigma;)</th>'
        '<th style="text-align:right;">Coh</th>'
        '<th style="text-align:right;">Frac K / I</th>'
        "<th>Matched Maunakea Truth</th>"
        '<th style="text-align:right;">Residual</th>'
        f"</tr></thead><tbody>{''.join(l_rows)}</tbody></table></div>"
        if l_rows
        else "<p class=\"muted\">No valid wind layers detected above SNR threshold.</p>"
    )

    fig_html = ""
    wl_png = "pyrwfs_windlayers_2x2.png"
    if (out_slug_dir / wl_png).is_file():
        cap = friendly_figure_caption(wl_png)
        c_esc = html.escape(cap, quote=False)
        fig_html = (
            '<figure class="report-figure">'
            f'<a href="{wl_png}" target="_blank" rel="noopener">'
            f'<img src="{wl_png}" alt="{c_esc}" loading="lazy"></a>'
            f"<figcaption>{c_esc}</figcaption>"
            "</figure>"
        )

    gt_note = ""
    if gt_layers:
        gt_rows = "".join(
            "<tr>"
            f"<td><code>GT{int(g.get('index', 0))}</code></td>"
            f"<td>{html.escape(str(g.get('regime', '')), quote=False)}</td>"
            f'<td style="text-align:right;">{_fmt_num(g.get("alt_agl_m"), digits=0, unit="m")}</td>'
            f'<td style="text-align:right;">{_fmt_num(g.get("z_los_m"), digits=0, unit="m")}</td>'
            f'<td style="text-align:right;">{_fmt_pct(g.get("cn2_frac"), digits=1)}</td>'
            f'<td style="text-align:right;">{_fmt_num(g.get("speed_mps"), digits=2, unit="m/s")}</td>'
            f'<td style="text-align:right;">{_fmt_num(g.get("dir_deg"), digits=1, unit="&deg;")}</td>'
            "</tr>"
            for g in gt_layers
            if isinstance(g, dict)
        )
        gt_note = (
            '<details style="margin-top:0.8rem;"><summary>Ground-Truth 7-Layer Maunakea Reference '
            "(mapped to WFS pupil pattern-motion frame &amp; zenith line-of-sight distance)</summary>"
            '<div class="table-wrap" style="margin-top:0.5rem;"><table><thead><tr>'
            "<th>Layer</th><th>Regime</th>"
            '<th style="text-align:right;">Alt AGL</th>'
            '<th style="text-align:right;">z<sub>LOS</sub></th>'
            '<th style="text-align:right;">C<sub>n</sub>&sup2; Share</th>'
            '<th style="text-align:right;">Speed</th>'
            '<th style="text-align:right;">Pattern Dir</th>'
            f"</tr></thead><tbody>{gt_rows}</tbody></table></div></details>"
        )

    rep_txt = str(wl_data.get("report_text") or "").strip()
    rep_html = (
        '<details style="margin-top:0.6rem;"><summary>Raw <code>mlt-windlayers</code> Text Report '
        "(<code>wl1_report.txt</code>)</summary>"
        f'<pre style="margin-top:0.5rem;overflow-x:auto;">{html.escape(rep_txt, quote=False)}</pre>'
        "</details>"
        if rep_txt
        else ""
    )

    intro_wl = (
        f"<p>Live Stage-1 atmospheric wind profiling from <code>milk-fpsexec-mlt-windlayers</code> "
        f"combining <code>{html.escape(str(wl_data.get('wfs_stream', 'csim_wfs_nir')), quote=False)}</code> "
        f"4-pupil intensity fluctuations with <code>{html.escape(str(wl_data.get('pha_stream', 'aol1_dmC')), quote=False)}</code> "
        f"wavefront curvature using {pg_src} and dark pedestal subtraction.</p>"
    )

    return "\n\n".join(
        p
        for p in (
            '<h2 id="wind-layers-reconstruction">Atmospheric Wind Layers Reconstruction '
            f'{render_section_badges(["loop_operation", "analysis"])}</h2>',
            intro_wl,
            f'<div class="kpi-grid">{"".join(wl_kpis)}</div>',
            tbl_html,
            fig_html,
            gt_note,
            rep_html,
        )
        if p
    )


def _build_figures_section(out_slug_dir: Path, has_wl_section: bool = False) -> str:
    figs: list[str] = []
    fig_list = [
        "pyrwfs_flux_strehl_2x2.png",
        "pyrwfs_align_jitter_2x2.png",
        "pyrwfs_pupil_maps_2x4.png",
    ]
    if not has_wl_section:
        fig_list.append("pyrwfs_windlayers_2x2.png")
    for fname in fig_list:
        if (out_slug_dir / fname).is_file():
            cap = friendly_figure_caption(fname)
            f_esc = html.escape(fname, quote=True)
            c_esc = html.escape(cap, quote=False)
            figs.append(
                '<figure class="report-figure">'
                f'<a href="{f_esc}" target="_blank" rel="noopener">'
                f'<img src="{f_esc}" alt="{c_esc}" loading="lazy"></a>'
                f"<figcaption>{c_esc}</figcaption>"
                "</figure>"
            )
    if not figs:
        return ""
    return (
        '<h2 id="pyrwfs-diagnostic-figures">Pyramid WFS Diagnostic Figures '
        f'{render_section_badges(["analysis"])}</h2>\n'
        f'<div class="figure-stack">{"".join(figs)}</div>'
    )


def _build_files_section(out_slug_dir: Path) -> str:
    items: list[str] = []
    for fname, desc in (
        ("pyrwfs_tlm_stg1.csv", "Stage 1 (AO3k J-Band PyWFS) per-frame telemetry time series"),
        ("pyrwfs_tlm_stg2.csv", "Stage 2 (SCExAO Vis PyWFS) per-frame telemetry time series"),
        ("pyrwfs_tlm_summary.json", "Aggregated per-stage Pyramid WFS telemetry & cross-check JSON"),
        ("pyrwfs_tlm_meta.json", "Live monitor capture metadata (rates, strides, flat f_pup0)"),
        ("windlayers_summary.json", "Stage-1 atmospheric wind layers reconstruction & Maunakea truth comparison JSON"),
        ("wl1_report.txt", "Live mlt-windlayers layer velocity, altitude & pupil geometry text report"),
        ("wl1_info.txt", "MILK FPS configuration & runtime telemetry snapshot for wl-1"),
    ):
        fp = out_slug_dir / fname
        if fp.is_file():
            sz = human_bytes(fp.stat().st_size)
            f_esc = html.escape(fname, quote=True)
            items.append(
                f'<li><a href="{f_esc}"><code>{html.escape(fname, quote=False)}</code></a> '
                f'<span class="muted">({sz})</span> &mdash; {html.escape(desc, quote=False)}</li>'
            )
    if not items:
        return ""
    return (
        '<h2 id="pyrwfs-telemetry-files">Pyramid WFS Telemetry Artifacts</h2>\n'
        f'<ul>{"".join(items)}</ul>'
    )


def _build_metric_reference() -> str:
    return (
        '<h2 id="pyrwfs-metric-definitions">Metric Definitions &amp; Physical Interpretation</h2>\n'
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Metric</th><th>Definition</th><th>Physical Interpretation</th>"
        "</tr></thead><tbody>"
        "<tr><td><code>f_pup</code>, <code>&Delta;f_pup</code></td>"
        "<td>Fraction of net flux inside the 4 geometric pupils; <code>f_pup &minus; f_pup,0</code></td>"
        "<td>Defocus-invariant Strehl / correction proxy. On a non-modulated or low-modulation PyWFS, "
        "strong diffraction pushes flat-WF light into the inter-pupil zones; aberrations break coherence "
        "and return light into the 4 pupils (<code>&Delta;f_pup &gt; 0</code>).</td></tr>"
        "<tr><td><code>f_diam</code>, <code>f_bH</code>, <code>f_bV</code></td>"
        "<td>Flux fraction in central apex diamond and horizontal/vertical inter-pupil bridges</td>"
        "<td>Separates symmetric radial diffraction (<code>f_diam</code>, first-order sensitive to defocus) "
        "from directional astigmatic / wind-driven leakage (<code>aniso = (f_bH&minus;f_bV)/(f_bH+f_bV)</code>).</td></tr>"
        "<tr><td><code>nl_ratio</code></td>"
        "<td>Projection of normalized WFS signal onto the even-order Strehl mode divided by pupil RMS</td>"
        "<td>Quantifies even-order nonlinearity / optical-gain departure relative to the flat-WF reference.</td></tr>"
        "<tr><td><code>dx, dy, ds, d_ast, rot</code></td>"
        "<td>6-DOF affine decomposition of temporal-variance + quadrupole-debiased 4-pupil geometry &amp; edge registration</td>"
        "<td>Locates all 4 pupils by minimizing the temporal variance of the aligned 4-pupil sum, "
        "debiased for scintillation via the quadrupole combination <code>(I0+I3)&minus;(I1+I2)</code>, "
        "and tracks live shift, magnification, astigmatic scale, and rotation without apex diffraction bias.</td></tr>"
        "<tr><td><code>scint_idx</code>, <code>scint_debias</code>, <code>curl_ratio</code>, <code>lwe_metric</code></td>"
        "<td>Raw &amp; lag-1 noise-debiased pupil intensity variance <code>&sigma;&sup2;/I&#772;&sup2;</code>, "
        "<code>RMS(&nabla;&times;S)/RMS(&nabla;&middot;S)</code>, spider-flanking flux RMS</td>"
        "<td>Exact EMA lag-1 white-noise cancellation isolates true temporally correlated flying-shadow "
        "scintillation from photon/readout noise; curl/div and spider LWE diagnose branch points and thermal petaling.</td></tr>"
        "<tr><td><code>mlt-windlayers</code></td>"
        "<td>Cross-spectral velocity mapping of 4-pupil sum intensity (<code>vmapi</code>) vs. wavefront curvature (<code>vmapk</code>)</td>"
        "<td>Reconstructs multi-layer wind vectors <code>(vx, vy)</code> and line-of-sight propagation altitudes "
        "<code>z_LOS</code> via Fresnel/Rytov curvature&ndash;scintillation cross-correlation using calibrated 4-pupil geometry.</td></tr>"
        "</tbody></table></div>"
    )


def build_sim_pyrwfs_html(
    *,
    slug: str,
    title: str,
    domain_id: str,
    hierarchy: dict[str, object],
    pyrwfs_data: dict[str, object],
    out_slug_dir: Path,
    has_compute_report: bool,
    updated_utc: str,
) -> str:
    """Build the dedicated Pyramid WFS Telemetry sub-page (<slug>/pyrwfs.html)."""
    stages = pyrwfs_data.get("stages") if isinstance(pyrwfs_data.get("stages"), dict) else {}
    wl_data = pyrwfs_data.get("windlayers") if isinstance(pyrwfs_data.get("windlayers"), dict) else None
    kpi_html = _build_kpi_row(stages, wl_data=wl_data)  # type: ignore[arg-type]
    explorer_html = _build_explorer_panel(pyrwfs_data)
    tables_html = _build_metrics_tables(stages)  # type: ignore[arg-type]
    wl_html = _build_windlayers_section(wl_data, out_slug_dir)
    figs_html = _build_figures_section(out_slug_dir, has_wl_section=bool(wl_html))
    files_html = _build_files_section(out_slug_dir)
    ref_html = _build_metric_reference()

    intro = (
        "<p>Live Pyramid WFS telemetry captured during closed-loop science integration by "
        "<code>cacao-fpsexec-pyrwfstlm</code> (<code>pyWFStlm</code>) and "
        "<code>milk-fpsexec-mlt-windlayers</code>: temporal-variance 4-pupil geometry, "
        "packed-zone flux partitioning, defocus-invariant Strehl proxy, quad-cell tip/tilt jitter, "
        "noise-debiased pupil scintillation, slope curl, Subaru spider-flanking LWE / petaling "
        "diagnostics, and multi-layer atmospheric wind reconstruction.</p>"
    )

    raw_body = "\n\n".join(
        p
        for p in (
            f"<h1>{html.escape(title, quote=False)} &middot; Pyramid WFS Telemetry</h1>",
            intro,
            kpi_html,
            explorer_html,
            tables_html,
            wl_html,
            figs_html,
            files_html,
            ref_html,
        )
        if p
    )
    toc = extract_toc_html(raw_body)
    if toc:
        h1_end = raw_body.find("</h1>") + 5
        raw_body = raw_body[:h1_end] + "\n\n" + toc + "\n\n" + raw_body[h1_end:]
    toc_items = extract_toc_items(raw_body)

    page_scripts = ("pyrwfs_explorer.js",) if explorer_html else ()
    return render_sim_page_shell(
        title=f"{title} — Pyramid WFS",
        slug=slug,
        domain_id=domain_id,
        hierarchy=hierarchy,
        active_tab="pyrwfs",
        has_compute_report=has_compute_report,
        has_pyrwfs_report=True,
        body_html=raw_body,
        toc_items=toc_items,
        page_scripts=page_scripts,
        has_mermaid=False,
        updated_utc=updated_utc,
    )
