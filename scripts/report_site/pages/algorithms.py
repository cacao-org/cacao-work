#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Algorithms & Dependencies index (/algorithms/index.html) and per-entry pages."""

from __future__ import annotations

import html
import re

from ..constants import DEFAULT_REPOS
from ..extractors.algorithms_catalog import (
    ALGO_ROLE_ORDER,
    ALGO_ROLES,
    STAGE_LABELS,
    make_algo_slug,
    resolve_option_anchor,
)
from ..markdown.sim_split import extract_toc_items
from .fragments import kpi_card, safe_json_embed
from .shell import render_page_shell

_REPO_URLS: dict[str, tuple[str, str]] = {
    r["name"]: (r["url"].rstrip("/"), r.get("branch", "main")) for r in DEFAULT_REPOS
}


def _mermaid_node_id(code: str) -> str:
    return "N_" + re.sub(r"[^A-Za-z0-9]+", "_", code).strip("_")


def _collect_valid_option_anchors(
    options_catalog: dict[str, object] | None,
) -> tuple[set[str], dict[str, dict[str, object]]]:
    valid: set[str] = set()
    by_anchor: dict[str, dict[str, object]] = {}
    if not isinstance(options_catalog, dict):
        return valid, by_anchor
    for grp_key in ("runner_cli", "env_vars", "cacaosim_cli"):
        for item in options_catalog.get(grp_key) or []:
            if isinstance(item, dict) and item.get("anchor"):
                anc = str(item["anchor"])
                valid.add(anc)
                by_anchor[anc] = item
    for u in options_catalog.get("fps_units") or []:
        if not isinstance(u, dict):
            continue
        for p in u.get("params") or []:
            if isinstance(p, dict) and p.get("anchor"):
                anc = str(p["anchor"])
                valid.add(anc)
                by_anchor[anc] = {
                    **p,
                    "tool": f"{u.get('package', '')}.{u.get('unit', '')}",
                    "flag": p.get("keyword", ""),
                }
    return valid, by_anchor


def _render_role_legend() -> str:
    pills: list[str] = []
    for rkey in ALGO_ROLE_ORDER:
        rmeta = ALGO_ROLES[rkey]
        pills.append(
            f'<span class="algo-legend-pill cat-{rkey}" '
            f'title="{html.escape(rmeta["description"], quote=True)}">'
            f'<span class="algo-sidebar-dot cat-{rkey}"></span>'
            f'{html.escape(rmeta["label"], quote=False)}</span>'
        )
    return (
        '<div class="algo-legend-bar">'
        "<strong>Color Key:</strong>"
        + "".join(pills)
        + '<span class="muted">Solid pill = required &middot; Dashed = optional</span>'
        "</div>"
    )


def _render_code_link(
    code: str,
    by_code: dict[str, dict[str, object]],
    href_prefix: str,
    *,
    optional: bool = False,
    small: bool = True,
) -> str:
    entry = by_code.get(code)
    if not entry:
        return f"<code>{html.escape(code, quote=False)}</code>"
    role = str(entry["role"])
    slug = str(entry["slug"])
    name = str(entry["name"])
    cls = f"algo-code-badge cat-{role}"
    if small:
        cls += " algo-code-badge-sm"
    if optional:
        cls += " algo-code-badge-opt"
    tip = f"{'Optional: ' if optional else ''}{code} — {name}"
    label = f"{code}?" if optional else code
    return (
        f'<a class="{cls}" href="{href_prefix}{html.escape(slug, quote=True)}/index.html" '
        f'title="{html.escape(tip, quote=True)}">{html.escape(label, quote=False)}</a>'
    )


def _render_stage_pills(stages: list[str]) -> str:
    short_map = {"stg1": "Stg 1", "stg2": "Stg 2", "stg3": "Stg 3", "2stg": "2-Stage"}
    return "".join(
        f'<span class="param-pill" title="{html.escape(STAGE_LABELS.get(s, s), quote=True)}">'
        f"{html.escape(short_map.get(s, s), quote=False)}</span>"
        for s in stages
    )


def _render_catalog_panel(algo_catalog: dict[str, object]) -> str:
    entries: list[dict[str, object]] = algo_catalog["entries"]  # type: ignore[assignment]
    by_code: dict[str, dict[str, object]] = algo_catalog["by_code"]  # type: ignore[assignment]
    tbodies: list[str] = []

    for rkey in ALGO_ROLE_ORDER:
        grp_entries = [e for e in entries if e["role"] == rkey]
        if not grp_entries:
            continue
        rmeta = ALGO_ROLES[rkey]
        grp_hdr = (
            f'<tr class="cat-group-row algo-group-row cat-{rkey}" data-group-role="{rkey}">'
            '<td colspan="8"><div class="cat-group-hdr">'
            '<span class="cat-group-title">'
            f'<strong>{html.escape(rmeta["label"], quote=False)}</strong>'
            f'<span class="muted">&mdash; {html.escape(rmeta["description"], quote=False)}</span>'
            "</span>"
            f'<span class="cat-group-count">{len(grp_entries)} entries</span>'
            "</div></td></tr>"
        )
        rows: list[str] = [grp_hdr]
        for e in grp_entries:
            code = str(e["code"])
            slug = str(e["slug"])
            name = str(e["name"])
            summary = str(e["summary"])
            stages = [str(s) for s in (e.get("stages") or [])]
            variants = list(e.get("variants") or [])
            req_list = [str(c) for c in (e.get("requires") or [])]
            opt_list = [str(c) for c in (e.get("optional_requires") or [])]
            fb_list = [str(c) for c in (e.get("feedback_from") or [])]
            en_list = [str(c) for c in (e.get("enables") or [])]
            en_opt = [str(c) for c in (e.get("enables_optional") or [])]
            flags = [str(f) for f in (e.get("cli_flags") or [])]
            units = [str(u) for u in (e.get("units") or [])]
            entry_href = f"./{html.escape(slug, quote=True)}/index.html"

            var_html = "".join(
                f'<a class="algo-var-pill" href="{entry_href}#'
                f'{html.escape(str(v["anchor"]), quote=True)}" '
                f'title="{html.escape(str(v["summary"]), quote=True)}">'
                f'{html.escape(str(v["code"]), quote=False)}</a>'
                for v in variants
                if isinstance(v, dict)
            )
            req_pills = (
                " ".join(_render_code_link(c, by_code, "./") for c in req_list)
                + (" " if req_list and (opt_list or fb_list) else "")
                + " ".join(
                    _render_code_link(c, by_code, "./", optional=True)
                    for c in [*opt_list, *fb_list]
                )
            ) or '<span class="muted">&mdash;</span>'
            en_pills = (
                " ".join(_render_code_link(c, by_code, "./") for c in en_list)
                + (" " if en_list and en_opt else "")
                + " ".join(_render_code_link(c, by_code, "./", optional=True) for c in en_opt)
            ) or '<span class="muted">&mdash;</span>'

            sblob = " ".join(
                [
                    code,
                    name,
                    summary,
                    rmeta["label"],
                    " ".join(str(v.get("code", "")) for v in variants if isinstance(v, dict)),
                    " ".join(flags),
                    " ".join(units),
                ]
            ).lower()
            rows.append(
                f'<tr class="cat-row algo-row cat-{rkey}" '
                f'data-code="{html.escape(code, quote=True)}" '
                f'data-role="{rkey}" '
                f'data-stages="{html.escape(" ".join(stages), quote=True)}" '
                f'data-search="{html.escape(sblob, quote=True)}">'
                f'<td><a class="algo-code-badge cat-{rkey}" href="{entry_href}">'
                f"{html.escape(code, quote=False)}</a>"
                '<span class="algo-trace-tag algo-trace-tag-sel">SEL</span>'
                '<span class="algo-trace-tag algo-trace-tag-req">REQ</span>'
                '<span class="algo-trace-tag algo-trace-tag-en">EN</span></td>'
                f'<td><span class="algo-legend-pill cat-{rkey}">'
                f'{html.escape(rmeta["short"], quote=False)}</span></td>'
                f'<td class="wrap-cell">'
                f'<a class="algo-entry-link" href="{entry_href}">'
                f'<span class="algo-entry-title">{html.escape(name, quote=False)}</span>'
                f'<span class="algo-entry-desc">{html.escape(summary, quote=False)}</span>'
                "</a></td>"
                f'<td class="param-cell">{var_html or "&mdash;"}</td>'
                f"<td>{_render_stage_pills(stages)}</td>"
                f'<td class="param-cell">{req_pills}</td>'
                f'<td class="param-cell">{en_pills}</td>'
                f'<td><button type="button" class="algo-trace-btn" '
                f'data-algo-trace="{html.escape(code, quote=True)}" '
                f'title="Highlight upstream calibrations &amp; downstream dependents">Trace</button>'
                "</td></tr>"
            )
        tbodies.append(f'<tbody class="cat-tbody cat-{rkey}">{"".join(rows)}</tbody>')

    return (
        '<div class="tab-panel ref-tab-panel active" id="algo-panel-catalog" '
        'data-algo-panel="catalog">\n'
        '<div id="algo-trace-banner" class="algo-trace-banner hidden">'
        '<span id="algo-trace-text"></span>'
        '<button type="button" class="btn-sm" id="algo-trace-clear">Clear Trace</button>'
        "</div>\n"
        '<div class="table-wrap">'
        '<table id="algo-catalog-table"><thead><tr>'
        "<th>Code</th><th>Role</th><th>Algorithm &amp; Description (Click to Open)</th>"
        "<th>Option Variants (CODE/OPT)</th><th>Stage</th><th>Requires</th>"
        "<th>Enables</th><th>Deps</th>"
        f'</tr></thead>{"".join(tbodies)}</table></div>\n'
        '<div id="algo-empty" class="cat-empty-note hidden">'
        "No algorithms match the active filters.</div>\n"
        "</div>"
    )


def _render_matrix_panel(algo_catalog: dict[str, object]) -> str:
    entries: list[dict[str, object]] = algo_catalog["entries"]  # type: ignore[assignment]
    by_code: dict[str, dict[str, object]] = algo_catalog["by_code"]  # type: ignore[assignment]
    col_codes: tuple[str, ...] = algo_catalog["matrix_columns"]  # type: ignore[assignment]

    hdr_cells = ['<th class="dep-sticky-col">Algorithm (Row) \\ Prereq (Col)</th>']
    for ccode in col_codes:
        centry = by_code.get(ccode)
        if not centry:
            continue
        crole = str(centry["role"])
        cslug = str(centry["slug"])
        cname = str(centry["name"])
        hdr_cells.append(
            "<th>"
            f'<a class="dep-col-hdr algo-code-badge cat-{crole}" '
            f'href="./{html.escape(cslug, quote=True)}/index.html" '
            f'title="{html.escape(ccode + " — " + cname, quote=True)}">'
            f"{html.escape(ccode, quote=False)}</a></th>"
        )

    body_rows: list[str] = []
    for e in entries:
        code = str(e["code"])
        slug = str(e["slug"])
        role = str(e["role"])
        name = str(e["name"])
        stages = [str(s) for s in (e.get("stages") or [])]
        req_set = set(str(c) for c in (e.get("requires") or []))
        opt_set = set(str(c) for c in (e.get("optional_requires") or []))
        fb_set = set(str(c) for c in (e.get("feedback_from") or []))
        entry_href = f"./{html.escape(slug, quote=True)}/index.html"
        sblob = f"{code} {name} {e.get('summary', '')}".lower()

        cells: list[str] = [
            f'<td class="dep-sticky-col">'
            f'<a class="algo-code-badge algo-code-badge-sm cat-{role}" href="{entry_href}">'
            f"{html.escape(code, quote=False)}</a> "
            f'<a class="algo-dep-name" href="{entry_href}">{html.escape(name, quote=False)}</a>'
            "</td>"
        ]
        for ccode in col_codes:
            if ccode in req_set:
                tip = f"{code} requires {ccode} (click to open {code})"
                cells.append(
                    f'<td><a class="dep-cell dep-cell-req" href="{entry_href}" '
                    f'title="{html.escape(tip, quote=True)}">REQ</a></td>'
                )
            elif ccode in fb_set:
                tip = f"{code} receives closed-loop runtime feedback from {ccode}"
                cells.append(
                    f'<td><a class="dep-cell dep-cell-fb" href="{entry_href}" '
                    f'title="{html.escape(tip, quote=True)}">FB</a></td>'
                )
            elif ccode in opt_set:
                tip = f"{code} optionally uses {ccode} for enhanced capability"
                cells.append(
                    f'<td><a class="dep-cell dep-cell-opt" href="{entry_href}" '
                    f'title="{html.escape(tip, quote=True)}">OPT</a></td>'
                )
            else:
                cells.append('<td class="muted">&middot;</td>')

        body_rows.append(
            f'<tr class="cat-row dep-matrix-row cat-{role}" '
            f'data-code="{html.escape(code, quote=True)}" '
            f'data-role="{role}" '
            f'data-stages="{html.escape(" ".join(stages), quote=True)}" '
            f'data-search="{html.escape(sblob, quote=True)}">'
            f'{"".join(cells)}</tr>'
        )

    return (
        '<div class="tab-panel ref-tab-panel" id="algo-panel-matrix" data-algo-panel="matrix">\n'
        '<p class="muted"><strong>Cell Legend:</strong> '
        '<span class="dep-cell dep-cell-req">REQ</span> Required calibration/input &middot; '
        '<span class="dep-cell dep-cell-opt">OPT</span> Optional enhancement &middot; '
        '<span class="dep-cell dep-cell-fb">FB</span> Live closed-loop feedback. '
        "Click any code header or cell to open its algorithm webpage.</p>\n"
        '<div class="table-wrap dep-matrix-wrap">'
        '<table id="algo-matrix-table" class="dep-matrix-table">'
        f'<thead><tr>{"".join(hdr_cells)}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>\n'
        "</div>"
    )


_PIPELINE_COLUMNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Step 1", "Bench & Base Calib", ("SIM/PLATE", "SIM/WROT", "MLAT", "RM", "SRM")),
    (
        "Step 2",
        "3D RM & DM Shaping",
        ("3DRM/P1", "PRESH/CAL", "PRESH", "3DRM/P2", "3DRM/FACT", "LAG/2PT"),
    ),
    ("Step 3", "RT Core & Online Calib", ("INT", "PSOL", "OG/POKE", "2WFS/LIVE", "WIND")),
    ("Step 4", "ZPO, Offload & Prediction", ("ZPO", "OFFL", "PF/AR", "EOF")),
    ("Step 5", "Diagnostics & Research", ("WHITE", "TLM", "2WFS/POST", "HESS/CORO")),
)

_PIPELINE_PRESETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "full-p15",
        "Full Phases 1-5 Stack",
        ("PRESH", "PSOL", "OG/POKE", "2WFS/LIVE", "ZPO", "WIND", "EOF", "WHITE"),
    ),
    (
        "plate-3drm",
        "3D RM & Plate Pre-Shaper",
        ("3DRM/P1", "PRESH/CAL", "PRESH", "3DRM/P2", "3DRM/FACT", "LAG/2PT", "PSOL"),
    ),
    (
        "stg1-og",
        "Stage-1 Online OG",
        ("RM", "3DRM/FACT", "LAG/2PT", "PSOL", "OG/POKE"),
    ),
    (
        "stg2-2wfs",
        "Stage-2 2WFS1DM + ZPO",
        ("RM", "PSOL", "2WFS/LIVE", "ZPO", "OFFL"),
    ),
    (
        "wind-eof",
        "Wind-Switch Rescue EOF",
        ("SIM/WROT", "PSOL", "WIND", "EOF", "WHITE"),
    ),
)


def _render_pipeline_board(
    entries: list[dict[str, object]],
    by_code: dict[str, dict[str, object]],
) -> str:
    placed: set[str] = set()
    cols_html: list[str] = []
    n_cols = len(_PIPELINE_COLUMNS)
    for col_idx, (step_lbl, col_title, codes) in enumerate(_PIPELINE_COLUMNS):
        cards: list[str] = []
        for code in codes:
            e = by_code.get(code)
            if not e:
                continue
            placed.add(code)
            role = str(e["role"])
            slug = str(e["slug"])
            name = str(e["name"])
            rmeta = ALGO_ROLES[role]
            n_in = len(e.get("requires") or []) + len(e.get("optional_requires") or [])
            n_out = len(e.get("enables") or []) + len(e.get("enables_optional") or [])
            entry_href = f"./{html.escape(slug, quote=True)}/index.html"
            cards.append(
                f'<div class="algo-pipe-card cat-{role}" '
                f'data-pipe-code="{html.escape(code, quote=True)}">'
                '<span class="pipe-rel-ribbon pipe-rel-focus">&#9733; Selected</span>'
                '<span class="pipe-rel-ribbon pipe-rel-up">&larr; Required</span>'
                '<span class="pipe-rel-ribbon pipe-rel-opt">&#9671; Optional</span>'
                '<span class="pipe-rel-ribbon pipe-rel-down">&rarr; Enables</span>'
                '<span class="pipe-rel-ribbon pipe-rel-fb">&#8644; Feedback</span>'
                '<div class="algo-pipe-card-top">'
                f'<a class="algo-code-badge algo-code-badge-sm cat-{role}" '
                f'href="{entry_href}">{html.escape(code, quote=False)}</a>'
                f'<button type="button" class="algo-pipe-pin" '
                f'data-pipe-pin="{html.escape(code, quote=True)}" '
                f'title="Lock dependency highlight for {html.escape(code, quote=True)}">Pin</button>'
                "</div>"
                f'<a class="algo-pipe-card-link" href="{entry_href}">'
                f'<div class="algo-pipe-card-name">{html.escape(name, quote=False)}</div>'
                "</a>"
                '<div class="algo-pipe-card-meta">'
                f'<span>{html.escape(rmeta["short"], quote=False)}</span>'
                f"<span>{n_in} in &middot; {n_out} out</span>"
                "</div></div>"
            )
        arrow_span = (
            '<span class="algo-pipe-col-arrow" aria-hidden="true">&rarr;</span>'
            if col_idx < n_cols - 1
            else ""
        )
        cols_html.append(
            '<div class="algo-pipe-col">'
            '<div class="algo-pipe-col-hdr">'
            "<div>"
            f'<div class="algo-pipe-col-step">{html.escape(step_lbl, quote=False)}</div>'
            f'<div class="algo-pipe-col-title">{html.escape(col_title, quote=False)}</div>'
            f"</div>{arrow_span}</div>"
            f'{"".join(cards)}</div>'
        )

    # Append any unplaced entries to the last column as safety net
    extras = [e for e in entries if str(e["code"]) not in placed]
    if extras:
        extra_cards = "".join(
            f'<div class="algo-pipe-card cat-{e["role"]}" '
            f'data-pipe-code="{html.escape(str(e["code"]), quote=True)}">'
            f'<a class="algo-code-badge algo-code-badge-sm cat-{e["role"]}" '
            f'href="./{html.escape(str(e["slug"]), quote=True)}/index.html">'
            f'{html.escape(str(e["code"]), quote=False)}</a>'
            f'<div class="algo-pipe-card-name">{html.escape(str(e["name"]), quote=False)}</div>'
            "</div>"
            for e in extras
        )
        cols_html.append(f'<div class="algo-pipe-col">{extra_cards}</div>')

    preset_btns = "".join(
        f'<button type="button" class="chip-btn" '
        f'data-pipe-preset="{html.escape(pid, quote=True)}">'
        f"{html.escape(plbl, quote=False)}</button>"
        for pid, plbl, _ in _PIPELINE_PRESETS
    )
    preset_payload = {
        pid: {"label": plbl, "codes": list(pcodes)} for pid, plbl, pcodes in _PIPELINE_PRESETS
    }

    outline_legend = (
        '<div class="algo-outline-legend" id="algo-outline-legend">'
        "<strong>Outline Code (on hover / Pin):</strong>"
        '<span class="outline-key-chip outline-key-focus">&#9733; Selected</span>'
        '<span class="outline-key-chip outline-key-req">&larr; Required Calib / Input</span>'
        '<span class="outline-key-chip outline-key-opt">&#9671; Optional Enhancement</span>'
        '<span class="outline-key-chip outline-key-down">&rarr; Enables Downstream</span>'
        '<span class="outline-key-chip outline-key-fb">&#8644; Runtime Feedback</span>'
        "</div>\n"
    )

    return (
        '<div class="algo-pipe-toolbar">'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Highlight Stack:</span>'
        f"{preset_btns}"
        '<button type="button" class="btn-sm" id="algo-pipe-clear">Clear</button>'
        "</div>"
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Scope:</span>'
        '<button type="button" class="chip-btn active" data-pipe-depth="direct">Direct</button>'
        '<button type="button" class="chip-btn" data-pipe-depth="full">Full Chain</button>'
        "</div></div>\n"
        + outline_legend
        + '<div class="algo-pipe-status" id="algo-pipe-status">'
        "<span>Hover any card to outline its <strong>Required</strong> calibrations (thick amber), "
        "<strong>Optional</strong> inputs (dashed teal), and <strong>Enabled</strong> algorithms "
        "(thick blue). Click any card to open its page, or click <strong>Pin</strong> to lock "
        "outlines while clicking prerequisites.</span></div>\n"
        '<div class="algo-pipe-board" id="algo-pipeline-board">\n'
        + "\n".join(cols_html)
        + "\n</div>\n"
        f'<script type="application/json" id="algo-pipe-presets">'
        f"{safe_json_embed(preset_payload)}</script>"
    )


def _render_detail_flow_strip(
    entry: dict[str, object],
    by_code: dict[str, dict[str, object]],
) -> str:
    code = str(entry["code"])
    role = str(entry["role"])
    name = str(entry["name"])
    rmeta = ALGO_ROLES[role]
    req_codes = [str(c) for c in (entry.get("requires") or []) if c in by_code]
    opt_codes = [str(c) for c in (entry.get("optional_requires") or []) if c in by_code]
    fb_codes = [str(c) for c in (entry.get("feedback_from") or []) if c in by_code]
    en_codes = [str(c) for c in (entry.get("enables") or []) if c in by_code]
    en_opt_codes = [str(c) for c in (entry.get("enables_optional") or []) if c in by_code]
    fb_out_codes = [str(c) for c in (entry.get("feeds_runtime") or []) if c in by_code]

    def _mini_card(c: str, outline_cls: str, ribbon_cls: str, ribbon_lbl: str) -> str:
        t = by_code[c]
        tr = str(t["role"])
        ts = str(t["slug"])
        tn = str(t["name"])
        href = f"../{html.escape(ts, quote=True)}/index.html"
        return (
            f'<div class="algo-pipe-card cat-{tr} {outline_cls}">'
            f'<span class="pipe-rel-ribbon {ribbon_cls}">{ribbon_lbl}</span>'
            '<div class="algo-pipe-card-top">'
            f'<a class="algo-code-badge algo-code-badge-sm cat-{tr}" href="{href}">'
            f"{html.escape(c, quote=False)}</a>"
            f'<span class="muted">{html.escape(ALGO_ROLES[tr]["short"], quote=False)}</span>'
            "</div>"
            f'<a class="algo-pipe-card-link" href="{href}">'
            f'<div class="algo-pipe-card-name">{html.escape(tn, quote=False)}</div>'
            "</a></div>"
        )

    up_cards = (
        [_mini_card(c, "pipe-up", "pipe-rel-up", "&larr; Required") for c in req_codes]
        + [_mini_card(c, "pipe-opt", "pipe-rel-opt", "&#9671; Optional") for c in opt_codes]
        + [_mini_card(c, "pipe-fb", "pipe-rel-fb", "&#8644; Feedback") for c in fb_codes]
    )
    down_cards = (
        [_mini_card(c, "pipe-down", "pipe-rel-down", "&rarr; Enables") for c in en_codes]
        + [_mini_card(c, "pipe-opt", "pipe-rel-opt", "&#9671; Optional") for c in en_opt_codes]
        + [_mini_card(c, "pipe-fb", "pipe-rel-fb", "&#8644; Feedback") for c in fb_out_codes]
    )

    center_card = (
        f'<div class="algo-pipe-card algo-flow-center cat-{role} pipe-focus">'
        '<span class="pipe-rel-ribbon pipe-rel-focus">&#9733; Current Entry</span>'
        '<div class="algo-pipe-card-top">'
        f'<span class="algo-code-badge cat-{role}">{html.escape(code, quote=False)}</span>'
        f'<span class="algo-legend-pill cat-{role}">{html.escape(rmeta["short"], quote=False)}</span>'
        "</div>"
        f'<div class="algo-pipe-card-name">{html.escape(name, quote=False)}</div>'
        "</div>"
    )

    up_html = (
        "".join(up_cards)
        if up_cards
        else '<p class="muted">Self-contained (no mandatory upstream calibration).</p>'
    )
    down_html = (
        "".join(down_cards)
        if down_cards
        else '<p class="muted">Terminal diagnostic or output stage.</p>'
    )

    return (
        '<div class="algo-flow-strip" id="algo-detail-flow">\n'
        '<div class="algo-flow-col">'
        '<div class="algo-flow-col-hdr">Upstream Calibrations &amp; Inputs</div>'
        f"{up_html}</div>\n"
        '<div class="algo-flow-chevron" aria-hidden="true">&rarr;</div>\n'
        '<div class="algo-flow-col">'
        '<div class="algo-flow-col-hdr">Selected Algorithm</div>'
        f"{center_card}</div>\n"
        '<div class="algo-flow-chevron" aria-hidden="true">&rarr;</div>\n'
        '<div class="algo-flow-col">'
        '<div class="algo-flow-col-hdr">Feeds &amp; Enables Downstream</div>'
        f"{down_html}</div>\n"
        "</div>"
    )


def build_algorithms_index_html(
    hierarchy: dict[str, object],
    algo_catalog: dict[str, object],
    options_catalog: dict[str, object] | None = None,
) -> str:
    """Render /algorithms/index.html with clickable Catalog Table, 2D Matrix & Mermaid Graph."""
    _ = options_catalog
    entries: list[dict[str, object]] = algo_catalog["entries"]  # type: ignore[assignment]
    by_code: dict[str, dict[str, object]] = algo_catalog["by_code"]  # type: ignore[assignment]
    counts: dict[str, int] = algo_catalog["counts"]  # type: ignore[assignment]

    hero_html = (
        '<section class="hero-banner">\n'
        "<h1>AO Algorithms, Calibration &amp; Options Dependency Matrix</h1>\n"
        "<p>Unified map of every calibration, online adaptive estimator, real-time control loop, "
        "predictive filter, and diagnostic algorithm using short composable codes "
        "(<code>CODE/OPT</code>). Color distinguishes <strong>Offline Calibration</strong>, "
        "<strong>Online In-Loop Calibration</strong>, <strong>Real-Time Operation</strong>, and "
        "<strong>Diagnostics</strong>. Click any code, title, description, or matrix cell to open "
        "its dedicated documentation page.</p>\n"
        '<div class="kpi-grid">'
        + kpi_card("Algorithms", str(counts["total"]), f'{counts["variants"]} CODE/OPT variants')
        + kpi_card("Offline Calibration", str(counts.get("calibration", 0)), "Pre-loop matrices & kernels")
        + kpi_card("Online In-Loop", str(counts.get("online_calib", 0)), "Live OG, 2WFS1DM & wind")
        + kpi_card("RT Loop Operation", str(counts.get("loop_operation", 0)), "Control & predictive filters")
        + "</div>\n"
        "</section>"
    )

    role_chips = [
        f'<button type="button" class="chip-btn active" data-algo-role-filter="all">'
        f'All ({counts["total"]})</button>'
    ]
    for rkey in ALGO_ROLE_ORDER:
        rcnt = counts.get(rkey, 0)
        if rcnt:
            role_chips.append(
                f'<button type="button" class="chip-btn" data-algo-role-filter="{rkey}">'
                f'{html.escape(ALGO_ROLES[rkey]["short"], quote=False)} ({rcnt})</button>'
            )

    stage_chips = (
        '<button type="button" class="chip-btn active" data-algo-stage-filter="all">All</button>'
        '<button type="button" class="chip-btn" data-algo-stage-filter="stg1">Stage 1</button>'
        '<button type="button" class="chip-btn" data-algo-stage-filter="stg2">Stage 2</button>'
        '<button type="button" class="chip-btn" data-algo-stage-filter="stg3">Stage 3</button>'
        '<button type="button" class="chip-btn" data-algo-stage-filter="2stg">2-Stage</button>'
    )

    trace_presets = "".join(
        f'<button type="button" class="chip-btn" data-algo-trace="{c}">{c}</button>'
        for c in ("PSOL", "OG/POKE", "2WFS/LIVE", "EOF")
        if c in by_code
    )

    dep_graph_payload = {
        str(e["code"]): {
            "name": str(e["name"]),
            "req": list(e.get("requires") or []),
            "opt": list(e.get("optional_requires") or []),
            "fb_in": list(e.get("feedback_from") or []),
            "en": list(e.get("enables") or []),
            "en_opt": list(e.get("enables_optional") or []),
            "fb_out": list(e.get("feeds_runtime") or []),
        }
        for e in entries
    }

    explorer_html = (
        '<div class="explorer-panel" id="algorithms-root">\n'
        '<div class="tab-bar ref-tab-bar" role="tablist">\n'
        '<button type="button" class="chip-btn ref-tab-btn active" role="tab" '
        'aria-selected="true" data-algo-view="catalog">'
        f'Short-Code Catalog Table ({counts["total"]})</button>\n'
        '<button type="button" class="chip-btn ref-tab-btn" role="tab" '
        'aria-selected="false" data-algo-view="matrix">'
        "2D Calibration Dependency Matrix</button>\n"
        "</div>\n"
        '<div class="sim-filter-panel">\n'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Role:</span>'
        f'{"".join(role_chips)}</div>\n'
        '<div class="filter-actions-row">\n'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Stage:</span>'
        f"{stage_chips}"
        '<span class="filter-inline-label">Trace Chain:</span>'
        f"{trace_presets}</div>\n"
        '<div class="toolbar-group">'
        '<input type="search" id="algo-search" class="search-input" '
        'placeholder="Search codes (EOF/WIND), options, flags...">'
        '<button type="button" class="btn-sm" id="algo-reset">Reset</button>'
        f'<span id="algo-count" class="muted">{counts["total"]} / {counts["total"]}</span>'
        "</div>\n</div>\n</div>\n"
        + _render_catalog_panel(algo_catalog)
        + "\n"
        + _render_matrix_panel(algo_catalog)
        + f'\n<script type="application/json" id="algo-dep-graph-data">'
        f"{safe_json_embed(dep_graph_payload)}</script>\n"
        "</div>"
    )

    graph_section = (
        '<section class="explorer-panel" id="dependency-graph">\n'
        "<h2>Interactive Calibration &amp; Operation Pipeline Map</h2>\n"
        '<p class="muted">Organized left-to-right from bench &amp; base calibration through '
        "3D dynamic shaping, core RT &amp; online calibration, prediction, and diagnostics. "
        "Hover any card (or select a stack preset) to highlight its dependency outline code; "
        "click any card to open its dedicated page.</p>\n"
        + _render_pipeline_board(entries, by_code)
        + "\n</section>"
    )

    body_html = "\n\n".join([hero_html, _render_role_legend(), graph_section, explorer_html])
    return render_page_shell(
        title="AO Algorithms & Dependencies · cacao-work",
        rel_root="..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="algorithms",
        page_kind="algorithms",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Algorithms & Matrix", None),
        ],
        show_sidebar=False,
        page_scripts=("algorithms.js",),
        has_mermaid=False,
        footer_right=f'{counts["total"]} AO algorithms · {counts["variants"]} CODE/OPT variants',
    )


def _render_algo_sidebar(
    algo_catalog: dict[str, object],
    active_slug: str,
    toc_items: list[tuple[str, str]],
) -> str:
    entries: list[dict[str, object]] = algo_catalog["entries"]  # type: ignore[assignment]
    parts: list[str] = [
        '<div class="sidebar-section">'
        '<div class="sidebar-heading">Algorithms Directory</div>'
        '<ul class="sidebar-list">'
        '<li><a href="../index.html"><strong>&larr; All Algorithms &amp; Matrix</strong></a></li>'
        "</ul></div>"
    ]
    for rkey in ALGO_ROLE_ORDER:
        grp = [e for e in entries if e["role"] == rkey]
        if not grp:
            continue
        rmeta = ALGO_ROLES[rkey]
        lis = "".join(
            f'<li><a{" class=\"active\"" if e["slug"] == active_slug else ""} '
            f'href="../{html.escape(str(e["slug"]), quote=True)}/index.html">'
            f'<span class="algo-sidebar-dot cat-{rkey}"></span>'
            f'<code>{html.escape(str(e["code"]), quote=False)}</code></a></li>'
            for e in grp
        )
        parts.append(
            '<div class="sidebar-section">'
            f'<div class="sidebar-heading">{html.escape(rmeta["short"], quote=False)}</div>'
            f'<ul class="sidebar-list">{lis}</ul></div>'
        )
    if len(toc_items) >= 2:
        t_lis = "".join(
            f'<li><a class="toc-link" href="#{html.escape(hid, quote=True)}">'
            f"{html.escape(lbl, quote=False)}</a></li>"
            for hid, lbl in toc_items
        )
        parts.append(
            '<div class="sidebar-section sidebar-toc">'
            '<div class="sidebar-heading">On This Page</div>'
            f'<ul class="sidebar-list">{t_lis}</ul></div>'
        )
    return (
        '<aside class="site-sidebar" id="site-sidebar" aria-label="Algorithms navigation">\n'
        + "\n".join(parts)
        + '\n</aside>\n<div class="sidebar-backdrop" id="sidebar-backdrop"></div>'
    )


def _render_dep_card(
    title: str,
    codes: list[str],
    by_code: dict[str, dict[str, object]],
    *,
    optional_set: set[str] | None = None,
    empty_msg: str = "None",
) -> str:
    opt_s = optional_set or set()
    if not codes:
        inner = f'<p class="muted">{html.escape(empty_msg, quote=False)}</p>'
    else:
        items: list[str] = []
        for c in codes:
            target = by_code.get(c)
            if not target:
                continue
            slug = str(target["slug"])
            tname = str(target["name"])
            is_opt = c in opt_s
            badge = _render_code_link(c, by_code, "../", optional=is_opt, small=True)
            items.append(
                f'<div class="algo-dep-item">{badge}'
                f'<a class="algo-dep-name" href="../{html.escape(slug, quote=True)}/index.html">'
                f"{html.escape(tname, quote=False)}</a></div>"
            )
        inner = f'<div class="algo-dep-list">{"".join(items)}</div>'
    return f'<div class="algo-dep-card"><h3>{html.escape(title, quote=False)}</h3>{inner}</div>'


def build_algorithm_detail_html(
    entry: dict[str, object],
    hierarchy: dict[str, object],
    algo_catalog: dict[str, object],
    options_catalog: dict[str, object] | None = None,
) -> str:
    """Render dedicated /algorithms/<slug>/index.html page for one algorithm entry."""
    by_code: dict[str, dict[str, object]] = algo_catalog["by_code"]  # type: ignore[assignment]
    valid_opt_anchors, opt_by_anchor = _collect_valid_option_anchors(options_catalog)

    code = str(entry["code"])
    slug = str(entry["slug"])
    name = str(entry["name"])
    role = str(entry["role"])
    rmeta = ALGO_ROLES[role]
    status = str(entry.get("status") or "verified")
    stages = [str(s) for s in (entry.get("stages") or [])]
    summary = str(entry.get("summary") or "")
    details = [str(p) for p in (entry.get("details") or [])]
    units = [str(u) for u in (entry.get("units") or [])]
    variants = [v for v in (entry.get("variants") or []) if isinstance(v, dict)]
    req_codes = [str(c) for c in (entry.get("requires") or [])]
    opt_codes = [str(c) for c in (entry.get("optional_requires") or [])]
    fb_codes = [str(c) for c in (entry.get("feedback_from") or [])]
    en_codes = [str(c) for c in (entry.get("enables") or [])]
    en_opt_codes = [str(c) for c in (entry.get("enables_optional") or [])]
    fb_out_codes = [str(c) for c in (entry.get("feeds_runtime") or [])]
    excludes = [x for x in (entry.get("excludes") or []) if isinstance(x, dict)]

    status_badge = (
        '<span class="metric-pill metric-pill-accent">VERIFIED</span>'
        if status == "verified"
        else '<span class="metric-pill">PLANNED</span>'
    )

    hero_html = (
        f'<section class="algo-hero cat-{role}">\n'
        '<div class="algo-hero-meta">'
        f'<span class="algo-code-badge cat-{role}">{html.escape(code, quote=False)}</span>'
        f'<span class="algo-legend-pill cat-{role}">'
        f'{html.escape(rmeta["label"], quote=False)}</span>'
        f"{status_badge}"
        f"{_render_stage_pills(stages)}"
        "</div>\n"
        f"<h1>{html.escape(name, quote=False)}</h1>\n"
        f"<p>{html.escape(summary, quote=False)}</p>\n"
        '<div class="hero-actions">'
        '<a class="btn btn-secondary" href="../index.html">&larr; All Algorithms Table</a>'
        '<a class="btn btn-secondary" href="../index.html#matrix">2D Dependency Matrix</a>'
        '<a class="btn btn-secondary" href="../../reference/index.html">Options Reference</a>'
        "</div>\n"
        "</section>"
    )

    detail_paras = "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in details)
    unit_pills = "".join(
        f'<span class="param-pill"><code>{html.escape(u, quote=False)}</code></span>'
        for u in units
    )
    metric_lis = "".join(
        f"<li>{html.escape(str(m), quote=False)}</li>" for m in (entry.get("metrics") or [])
    )
    overview_sec = (
        '<h2 id="overview">Overview &amp; Role</h2>\n'
        f"{detail_paras}\n"
        f'<p><strong>Compute Units / Entry Points:</strong> {unit_pills or "&mdash;"}</p>\n'
        + (f"<p><strong>Verified Highlights:</strong></p><ul>{metric_lis}</ul>" if metric_lis else "")
    )

    var_rows: list[str] = []
    for v in variants:
        vcode = str(v.get("code") or "")
        vanc = str(v.get("anchor") or make_algo_slug(vcode))
        vsum = str(v.get("summary") or "")
        vflags = [str(f) for f in (v.get("flags") or [])]
        fl_links: list[str] = []
        for fl in vflags:
            anc = resolve_option_anchor("cli", fl, valid_opt_anchors)
            if anc:
                fl_links.append(
                    f'<a class="opt-ref-link" href="../../reference/index.html#{anc}">'
                    f"<code>{html.escape(fl, quote=False)}</code></a>"
                )
            else:
                fl_links.append(f"<code>{html.escape(fl, quote=False)}</code>")
        var_rows.append(
            f'<tr id="{html.escape(vanc, quote=True)}">'
            f'<td><strong><code>{html.escape(vcode, quote=False)}</code></strong></td>'
            f'<td class="wrap-cell">{html.escape(vsum, quote=False)}</td>'
            f'<td class="param-cell">{" ".join(fl_links) or "&mdash;"}</td>'
            "</tr>"
        )
    variants_sec = (
        '<h2 id="variants">Option Variants (<code>CODE/OPT</code>)</h2>\n'
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Option Code</th><th>Behavior &amp; Usage</th><th>Main Flags</th>"
        f'</tr></thead><tbody>{"".join(var_rows)}</tbody></table></div>'
    )

    local_flow_html = _render_detail_flow_strip(entry, by_code)

    excl_html = "".join(
        '<div class="algo-excl-box"><strong>Interaction / Exclusion Note:</strong> '
        f'{html.escape(str(ex.get("reason") or ""), quote=False)}</div>'
        for ex in excludes
    )
    deps_sec = (
        '<h2 id="dependencies">Dependencies &amp; Calibration Chain</h2>\n'
        f"{local_flow_html}\n{excl_html}"
    )

    # Resolved CLI / Env / FPS options table
    opt_rows: list[str] = []
    for fl in entry.get("cli_flags") or []:
        fl_s = str(fl)
        anc = resolve_option_anchor("cli", fl_s, valid_opt_anchors)
        meta = opt_by_anchor.get(anc or "", {})
        dflt = str(meta.get("default") or "")
        desc = str(meta.get("description") or "")
        tok_html = (
            f'<a class="opt-ref-link" href="../../reference/index.html#{anc}">'
            f"<strong><code>{html.escape(fl_s, quote=False)}</code></strong></a>"
            if anc
            else f"<strong><code>{html.escape(fl_s, quote=False)}</code></strong>"
        )
        opt_rows.append(
            "<tr>"
            '<td><span class="metric-pill">CLI Flag</span></td>'
            f"<td>{tok_html}</td>"
            f'<td><code>{html.escape(dflt, quote=False) if dflt else "&mdash;"}</code></td>'
            f'<td class="wrap-cell">{html.escape(desc, quote=False) or "&mdash;"}</td>'
            "</tr>"
        )
    for ev in entry.get("env_vars") or []:
        ev_s = str(ev)
        anc = resolve_option_anchor("env", ev_s, valid_opt_anchors)
        meta = opt_by_anchor.get(anc or "", {})
        dflt = str(meta.get("default") or "")
        desc = str(meta.get("description") or "")
        tok_html = (
            f'<a class="opt-ref-link" href="../../reference/index.html#{anc}">'
            f"<strong><code>{html.escape(ev_s, quote=False)}</code></strong></a>"
            if anc
            else f"<strong><code>{html.escape(ev_s, quote=False)}</code></strong>"
        )
        opt_rows.append(
            "<tr>"
            '<td><span class="metric-pill">CACAO_* Env</span></td>'
            f"<td>{tok_html}</td>"
            f'<td><code>{html.escape(dflt, quote=False) if dflt else "&mdash;"}</code></td>'
            f'<td class="wrap-cell">{html.escape(desc, quote=False) or "&mdash;"}</td>'
            "</tr>"
        )
    for fref in entry.get("fps_refs") or []:
        if not isinstance(fref, tuple) or len(fref) != 3:
            continue
        pkg, unit, kw = fref
        anc = resolve_option_anchor("fps", fref, valid_opt_anchors)
        meta = opt_by_anchor.get(anc or "", {})
        dflt = str(meta.get("default") or "")
        desc = str(meta.get("description") or "")
        label = f"{unit}{kw}"
        tok_html = (
            f'<a class="opt-ref-link" href="../../reference/index.html#{anc}">'
            f"<strong><code>{html.escape(label, quote=False)}</code></strong></a>"
            if anc
            else f"<strong><code>{html.escape(label, quote=False)}</code></strong>"
        )
        opt_rows.append(
            "<tr>"
            f'<td><span class="metric-pill">FPS ({html.escape(str(pkg))})</span></td>'
            f"<td>{tok_html}</td>"
            f'<td><code>{html.escape(dflt, quote=False) if dflt else "&mdash;"}</code></td>'
            f'<td class="wrap-cell">{html.escape(desc, quote=False) or "&mdash;"}</td>'
            "</tr>"
        )

    options_sec = (
        '<h2 id="options">CLI Flags, Environment Variables &amp; FPS Parameters</h2>\n'
        + (
            '<div class="table-wrap"><table><thead><tr>'
            "<th>Layer</th><th>Option (Links to Reference)</th><th>Default</th><th>Description</th>"
            f'</tr></thead><tbody>{"".join(opt_rows)}</tbody></table></div>'
            if opt_rows
            else '<p class="muted">Configured directly via FPS unit parameters or calibration script.</p>'
        )
    )

    # Source code, tests, and staged technical reports
    src_lis: list[str] = []
    for repo_name, rel_path in entry.get("sources") or []:
        r_url, r_br = _REPO_URLS.get(str(repo_name), ("", "main"))
        if r_url:
            gh = f"{r_url}/blob/{r_br}/{rel_path}"
            src_lis.append(
                f'<li><strong>{html.escape(str(repo_name))}</strong>: '
                f'<a href="{html.escape(gh, quote=True)}" target="_blank" rel="noopener">'
                f"<code>{html.escape(str(rel_path), quote=False)}</code></a></li>"
            )
        else:
            src_lis.append(
                f"<li><strong>{html.escape(str(repo_name))}</strong>: "
                f"<code>{html.escape(str(rel_path), quote=False)}</code></li>"
            )
    test_lis = "".join(
        f"<li><code>{html.escape(str(t), quote=False)}</code></li>"
        for t in (entry.get("tests") or [])
    )

    staged_metas = list(hierarchy.get("all_metas") or [])
    staged_by_slug = {
        str(m["slug"]): m for m in staged_metas if isinstance(m, dict) and m.get("slug")
    }
    rel_rep_lis: list[str] = []
    for rslug in entry.get("related_reports") or []:
        rs = str(rslug)
        if rs in staged_by_slug:
            rm = staged_by_slug[rs]
            rtitle = str(rm.get("title") or rs)
            rel_rep_lis.append(
                f'<li><a href="../../{html.escape(rs, quote=True)}/index.html">'
                f"<strong>{html.escape(rtitle, quote=False)}</strong></a></li>"
            )

    impl_sec = (
        '<h2 id="implementation">Implementation, Tests &amp; Related Reports</h2>\n'
        f"<h3>Source Files</h3><ul>{''.join(src_lis)}</ul>\n"
        + (f"<h3>Verification Tests</h3><ul>{test_lis}</ul>\n" if test_lis else "")
        + (
            f"<h3>Related Staged Technical Reports</h3><ul>{''.join(rel_rep_lis)}</ul>"
            if rel_rep_lis
            else ""
        )
    )

    body_html = "\n\n".join([hero_html, overview_sec, variants_sec, deps_sec, options_sec, impl_sec])
    toc_items = extract_toc_items(body_html)
    sidebar_html = _render_algo_sidebar(algo_catalog, slug, toc_items)

    return render_page_shell(
        title=f"{code} · {name} · cacao-work",
        rel_root="../..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="algorithms",
        active_slug=slug,
        page_kind="algorithm_detail",
        breadcrumbs=[
            ("Home", "../../index.html"),
            ("Algorithms & Matrix", "../index.html"),
            (code, None),
        ],
        show_sidebar=True,
        sidebar_override_html=sidebar_html,
        toc_items=toc_items,
        page_scripts=("algorithms.js",),
        has_mermaid=False,
        footer_right=f'{code} ({rmeta["short"]}) · AO Algorithm Specification',
    )
