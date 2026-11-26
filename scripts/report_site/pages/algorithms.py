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


_PIPELINE_STAGE_TOGGLES: tuple[tuple[str, str, str], ...] = (
    ("stg1", "Stage 1 (AO3k)", "1 kHz ALPAO 64x64 + NIR PyWFS"),
    ("stg2", "Stage 2 (SCExAO)", "2 kHz MEMS 50x50 + Vis PyWFS"),
    ("stg3", "Stage 3 (LLOWFS)", "Coronagraphic Lyot low-order WFS"),
)

_PIPELINE_PRESETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "full-decoupled",
        "Full Decoupled Stack (Recommended)",
        (
            "SIM/FUSED",
            "SIM/PLATE",
            "SIM/TURB",
            "WFS/MOD",
            "MLAT",
            "RM/FAST",
            "RM/DIR",
            "3DRM/MIMO",
            "OG/POKE",
            "2WFS/IV",
            "WIND",
            "INT/MGAIN",
            "PSOL/MIMO",
            "EOF/BASE",
            "EOF/ZOH",
            "EOF/WIND",
            "SL/GLOBAL",
            "SL/CLUST",
            "CMODES/ROT",
            "CMODES/NOTCH",
            "PRESH/4K",
            "ZPO/OG",
            "OFFL/2TO1",
            "WHITE/RT",
            "WHITE/OOS",
        ),
    ),
    (
        "faint-m10-mr",
        "Faint-Star m=10 Slow-WFS + Multi-Rate DM",
        (
            "SIM/FUSED",
            "SIM/PLATE",
            "SIM/TURB",
            "WFS/MOD",
            "WFS/SLOW",
            "MLAT",
            "RM/FAST",
            "RM/DIR",
            "3DRM/MIMO",
            "OG/POKE",
            "2WFS/IV",
            "WIND",
            "INT/MGAIN",
            "PSOL/MIMO",
            "EOF/BASE",
            "EOF/ZOH",
            "EOF/WIND",
            "DM/MR",
            "PRESH/4K",
            "ZPO/OG",
            "OFFL/2TO1",
            "WHITE/RT",
            "WHITE/OOS",
        ),
    ),
    (
        "full-p15",
        "Verified C Stack (Phases 1-5 + Self-Learning)",
        (
            "SIM/FUSED",
            "SIM/PLATE",
            "SIM/TURB",
            "WFS/MOD",
            "MLAT",
            "RM/FAST",
            "RM/DIR",
            "3DRM/MIMO",
            "OG/POKE",
            "2WFS/IV",
            "WIND",
            "INT/MGAIN",
            "PSOL/MIMO",
            "EOF/BASE",
            "EOF/ZOH",
            "EOF/WIND",
            "SL/GLOBAL",
            "SL/CLUST",
            "PRESH/4K",
            "ZPO/OG",
            "OFFL/2TO1",
            "WHITE/RT",
            "WHITE/OOS",
        ),
    ),
    (
        "int-mopt",
        "Autotuned Integrator + Adaptive Modes",
        (
            "SIM/FUSED",
            "SIM/PLATE",
            "SIM/TURB",
            "WFS/MOD",
            "MLAT",
            "RM/FAST",
            "3DRM/DIAG",
            "INT/LEAK",
            "PSOL/DIAG",
            "MOPT",
            "CMODES/ROT",
            "CMODES/NOTCH",
            "WHITE/RT",
        ),
    ),
    (
        "unmod-2wfs",
        "Unmodulated 0 l/D + Self-Learning + 2WFS/ZPO",
        (
            "SIM/FUSED",
            "SIM/PLATE",
            "SIM/TURB",
            "WFS/UNMOD",
            "MLAT",
            "RM/FAST",
            "RM/DIR",
            "3DRM/MIMO",
            "SRM",
            "OG/POKE",
            "2WFS/IV",
            "INT/MGAIN",
            "PSOL/MIMO",
            "EOF/BASE",
            "EOF/ZOH",
            "SL/GLOBAL",
            "SL/CLUST",
            "PRESH/4K",
            "ZPO/OG",
            "OFFL/2TO1",
            "WHITE/RT",
        ),
    ),
    (
        "wind-eof",
        "Wind-Switch Rescue EOF",
        (
            "SIM/FUSED",
            "SIM/PLATE",
            "SIM/WROT",
            "WFS/MOD",
            "MLAT",
            "RM/FAST",
            "WIND",
            "INT/MGAIN",
            "PSOL/2TAP",
            "EOF/BASE",
            "EOF/ZOH",
            "EOF/WIND",
            "WHITE/RT",
            "WHITE/OOS",
        ),
    ),
    (
        "fx-eof",
        "Unshaped Plate FX-EOF",
        (
            "SIM/FUSED",
            "SIM/PLATE",
            "SIM/TURB",
            "WFS/MOD",
            "MLAT",
            "RM/FAST",
            "3DRM/MIMO",
            "INT/MGAIN",
            "PSOL/MIMO",
            "EOF/BASE",
            "EOF/FX",
            "WHITE/RT",
        ),
    ),
    (
        "mod-ar",
        "Modular Bench + AR(P)",
        (
            "SIM/MOD",
            "SIM/PLATE",
            "SIM/TURB",
            "WFS/MOD",
            "MLAT",
            "RM/HAD",
            "RM/DIR",
            "INT/MGAIN",
            "PSOL/2TAP",
            "PF/AR",
            "ZPO/FIX",
            "TLM/SYNC",
            "TLM/OPT",
            "TLM/PSFR",
            "2WFS/POST",
        ),
    ),
)


def _render_rel_ribbons() -> str:
    return (
        '<span class="pipe-rel-ribbon pipe-rel-focus">&#9733; Hovered</span>'
        '<span class="pipe-rel-ribbon pipe-rel-up">&larr; Required</span>'
        '<span class="pipe-rel-ribbon pipe-rel-opt">&#9671; Optional</span>'
        '<span class="pipe-rel-ribbon pipe-rel-down">&rarr; Enables</span>'
        '<span class="pipe-rel-ribbon pipe-rel-fb">&#8644; Feedback</span>'
        '<span class="pipe-rel-ribbon pipe-rel-excl">&#10005; Exclusive</span>'
    )


def _render_toggle_card(choice: dict[str, object]) -> str:
    """Render a standalone boolean algorithmic option as an ON/OFF toggle switch."""
    code = str(choice["code"])
    role = str(choice["role"])
    name = str(choice["name"])
    doc_href = str(choice["doc_href"])
    return (
        f'<div class="algo-pipe-card algo-pipe-toggle-card cat-{role}" '
        f'data-pipe-code="{html.escape(code, quote=True)}" '
        'tabindex="0" role="switch" aria-checked="false">'
        + _render_rel_ribbons()
        + '<div class="algo-toggle-body">'
        '<div class="algo-toggle-info">'
        '<div class="algo-toggle-top">'
        f'<a class="algo-code-badge algo-code-badge-sm cat-{role}" '
        f'href="{html.escape(doc_href, quote=True)}" '
        f'title="Open {html.escape(code, quote=True)} documentation">'
        f"{html.escape(code, quote=False)}</a>"
        f'<a class="algo-pipe-docs-link" href="{html.escape(doc_href, quote=True)}" '
        f'title="Open {html.escape(code, quote=True)} documentation">&nearr;</a>'
        "</div>"
        f'<div class="algo-pipe-card-name">{html.escape(name, quote=False)}</div>'
        "</div>"
        '<span class="algo-switch" aria-hidden="true">'
        '<span class="algo-switch-track"><span class="algo-switch-thumb"></span></span>'
        '<span class="algo-switch-lbl">OFF</span>'
        "</span>"
        "</div>"
        '<div class="algo-lock-reason hidden" aria-live="polite"></div>'
        "</div>"
    )


def _render_select_card(
    group_id: str,
    label: str,
    role: str,
    options: list[tuple[str, str, str, str]],
    *,
    allow_off: bool = True,
    off_label: str = "Off (None)",
    compact: bool = False,
) -> str:
    """Render mutually exclusive or ordered choices as a single pulldown menu (<select>).

    Each option tuple is ``(value, primary_code, display_label, doc_href)``.
    Composite ordered options use ``value = "CODE1+CODE2"`` with ``primary_code = "CODE2"``.
    """
    all_codes: list[str] = []
    for val, _pc, _lbl, _href in options:
        for tok in val.split("+"):
            t = tok.strip()
            if t and t not in all_codes:
                all_codes.append(t)

    opt_tags: list[str] = []
    if allow_off:
        opt_tags.append(
            f'<option value="" data-base-label="{html.escape(off_label, quote=True)}">'
            f"{html.escape(off_label, quote=False)}</option>"
        )
    for val, primary_code, disp_label, doc_href in options:
        opt_tags.append(
            f'<option value="{html.escape(val, quote=True)}" '
            f'data-pipe-code="{html.escape(primary_code, quote=True)}" '
            f'data-doc-href="{html.escape(doc_href, quote=True)}" '
            f'data-base-label="{html.escape(disp_label, quote=True)}">'
            f"{html.escape(disp_label, quote=False)}</option>"
        )

    first_code = options[0][1] if options else ""
    first_href = options[0][3] if options else "#"
    sel_id = f"algo-sel-{group_id}"
    extra_cls = " algo-pipe-select-compact" if compact else ""

    return (
        f'<div class="algo-pipe-card algo-pipe-select-card cat-{role}{extra_cls}" '
        f'data-pipe-select-group="{html.escape(group_id, quote=True)}" '
        f'data-pipe-codes="{html.escape(",".join(all_codes), quote=True)}" '
        f'data-pipe-allow-off="{"1" if allow_off else "0"}">'
        + _render_rel_ribbons()
        + '<div class="algo-select-top">'
        f'<label class="algo-select-lbl" for="{html.escape(sel_id, quote=True)}">'
        f"{html.escape(label, quote=False)}</label>"
        '<span class="algo-select-meta">'
        f'<a class="algo-code-badge algo-code-badge-sm cat-{role} algo-select-active-badge" '
        f'href="{html.escape(first_href, quote=True)}" '
        f'title="Open {html.escape(first_code, quote=True)} documentation">'
        f"{html.escape(first_code if not allow_off else 'OFF', quote=False)}</a>"
        f'<a class="algo-pipe-docs-link algo-select-docs-link" '
        f'href="{html.escape(first_href, quote=True)}" '
        f'title="Open active option documentation">&nearr;</a>'
        "</span>"
        "</div>"
        f'<select class="algo-ctrl-select" id="{html.escape(sel_id, quote=True)}" '
        f'aria-label="{html.escape(label, quote=True)}">'
        + "".join(opt_tags)
        + "</select>"
        '<div class="algo-lock-reason hidden" aria-live="polite"></div>'
        "</div>"
    )


def _render_pipeline_board(algo_catalog: dict[str, object]) -> str:
    pcat: dict[str, object] = algo_catalog["pipeline_choices"]  # type: ignore[assignment]
    items: list[dict[str, object]] = pcat["items"]  # type: ignore[assignment]
    by_c: dict[str, dict[str, object]] = pcat["by_code"]  # type: ignore[assignment]

    def _tog(code: str) -> str:
        return _render_toggle_card(by_c[code])

    def _opt(code: str, short_lbl: str | None = None) -> tuple[str, str, str, str]:
        it = by_c[code]
        lbl = short_lbl or f"{code} — {it['name']}"
        return (code, code, lbl, str(it["doc_href"]))

    def _combo_opt(codes: tuple[str, ...], disp_lbl: str) -> tuple[str, str, str, str]:
        primary = codes[-1]
        return ("+".join(codes), primary, disp_lbl, str(by_c[primary]["doc_href"]))

    stage_btns = "".join(
        f'<button type="button" class="algo-stage-btn active" '
        f'data-pipe-stage="{html.escape(skey, quote=True)}" role="switch" aria-checked="true" '
        f'title="{html.escape(sdesc, quote=True)}">'
        '<span class="algo-switch-track algo-stage-track" aria-hidden="true">'
        '<span class="algo-switch-thumb"></span></span>'
        f'<span>{html.escape(slbl, quote=False)}</span></button>'
        for skey, slbl, sdesc in _PIPELINE_STAGE_TOGGLES
    )

    sim_strip_html = (
        '<div class="algo-sim-strip" id="algo-sim-strip">\n'
        '  <div class="algo-sim-section algo-sim-stages">\n'
        '    <div class="algo-sim-section-hdr">Active AO Stages &amp; Faint-Star Cadence (Toggles)</div>\n'
        f'    <div class="algo-stage-toggles">{stage_btns}</div>\n'
        f'    <div class="algo-pipe-grid-1">{_tog("WFS/SLOW")}</div>\n'
        "  </div>\n"
        '  <div class="algo-sim-section algo-sim-models">\n'
        '    <div class="algo-sim-section-hdr">'
        "Simulation &amp; Bench Setup (Pulldown Choices)</div>\n"
        '    <div class="algo-sim-groups">\n'
        + _render_select_card(
            "bench-mode",
            "Bench Engine",
            "simulation",
            [_opt("SIM/FUSED"), _opt("SIM/MOD")],
            allow_off=False,
            compact=True,
        )
        + _render_select_card(
            "dm-phys",
            "Stage-1 DM Physics",
            "simulation",
            [_opt("SIM/PLATE"), _opt("SIM/IDEAL")],
            allow_off=False,
            compact=True,
        )
        + _render_select_card(
            "atm-mode",
            "Atmosphere Model",
            "simulation",
            [_opt("SIM/TURB"), _opt("SIM/WROT")],
            allow_off=False,
            compact=True,
        )
        + _render_select_card(
            "wfs-mod",
            "PyWFS Modulation",
            "simulation",
            [_opt("WFS/MOD"), _opt("WFS/UNMOD")],
            allow_off=False,
            compact=True,
        )
        + "    </div>\n"
        "  </div>\n"
        "</div>\n"
    )

    mid_board_html = (
        '<div class="algo-pipe-board" id="algo-pipeline-board">\n'
        '  <div class="algo-pipe-group algo-group-calib" id="algo-group-calibration">\n'
        '    <div class="algo-pipe-group-hdr">'
        "<span>Calibration</span>"
        '<span class="algo-pipe-group-sub">Pulldowns for exclusive modes &middot; Switches for toggles</span>'
        "</div>\n"
        '    <div class="algo-calib-split">\n'
        '      <div class="algo-pipe-sub algo-sub-offline" id="algo-sub-offline">\n'
        '        <div class="algo-pipe-sub-hdr">Offline Calibration</div>\n'
        + _render_select_card(
            "rm-mode",
            "Static RM Acquisition",
            "calibration",
            [_opt("RM/FAST"), _opt("RM/HAD")],
            allow_off=True,
            off_label="Off (No Stage-1/2 RM)",
        )
        + _render_select_card(
            "3drm-mode",
            "3D Dynamic Plant RM",
            "calibration",
            [_opt("3DRM/DIAG"), _opt("3DRM/MIMO")],
            allow_off=True,
            off_label="Off (Static RM Only)",
        )
        + '<div class="algo-choice-group">'
        '<div class="algo-choice-lbl">Timing, Stage-3 RM &amp; Reference (ON/OFF)</div>'
        f'<div class="algo-pipe-grid-1">{_tog("MLAT")}{_tog("RM/DIR")}{_tog("SRM")}</div></div>\n'
        "      </div>\n"
        '      <div class="algo-pipe-sub algo-sub-online" id="algo-sub-online">\n'
        '        <div class="algo-pipe-sub-hdr">Online Calibration (In-Loop)</div>\n'
        + _render_select_card(
            "2wfs-mode",
            "Stage-2 Passive 2WFS1DM",
            "online_calib",
            [_opt("2WFS/IV"), _opt("2WFS/W")],
            allow_off=True,
            off_label="Off (None)",
        )
        + '<div class="algo-choice-group">'
        '<div class="algo-choice-lbl">Active OG, Autotuner &amp; Wind (ON/OFF)</div>'
        f'<div class="algo-pipe-grid-1">{_tog("OG/POKE")}{_tog("MOPT")}{_tog("WIND")}</div></div>\n'
        "      </div>\n"
        "    </div>\n"
        "  </div>\n"
        '  <div class="algo-pipe-group-arrow" aria-hidden="true">&rarr;</div>\n'
        '  <div class="algo-pipe-group algo-group-control" id="algo-group-control">\n'
        '    <div class="algo-pipe-group-hdr">'
        "<span>Real-Time Control Architecture (3 Decoupled Layers)</span>"
        '<span class="algo-pipe-group-sub">'
        "Core Control &rarr; Inner Rotation &rarr; DM Actuation</span>"
        "</div>\n"
        '    <div class="algo-pipe-sub algo-sub-control" id="algo-sub-core-control">\n'
        '      <div class="algo-pipe-sub-hdr">'
        "1. Core Real-Time Control (Fixed Outer Modal Basis)</div>\n"
        '      <div class="algo-ctrl-grid-2">\n'
        + _render_select_card(
            "int-mode",
            "Base Integrator",
            "loop_operation",
            [_opt("INT/LEAK"), _opt("INT/MGAIN")],
            allow_off=True,
            off_label="Off (Open Loop)",
        )
        + _render_select_card(
            "psol-mode",
            "PSOL Observer Model",
            "loop_operation",
            [_opt("PSOL/2TAP"), _opt("PSOL/DIAG"), _opt("PSOL/MIMO")],
            allow_off=True,
            off_label="Off (No PSOL)",
        )
        + _render_select_card(
            "pred-mode",
            "Predictive Controller",
            "loop_operation",
            [_opt("PF/AR"), _opt("EOF/BASE")],
            allow_off=True,
            off_label="Off (Integrator Only)",
        )
        + _render_select_card(
            "eof-plant",
            "Block-EOF Physics / Plant Mode",
            "loop_operation",
            [_opt("EOF/WIND"), _opt("EOF/FX")],
            allow_off=True,
            off_label="Off (Empirical Block-EOF)",
        )
        + "      </div>\n"
        '      <div class="algo-choice-group">'
        '<div class="algo-choice-lbl">Block-EOF Ridge &amp; Memory Extensions (ON/OFF)</div>'
        f'<div class="algo-pipe-grid-3">{_tog("EOF/ZOH")}{_tog("EOF/MEM")}{_tog("EOF/REG")}</div></div>\n'
        + _render_select_card(
            "selflearn-mode",
            "Cascaded Online Self-Learning (requires EOF/BASE — never standalone)",
            "loop_operation",
            [
                _opt("SL/GLOBAL", "SL/GLOBAL — Global Online Adaptive Filter (RLS)"),
                _combo_opt(
                    ("SL/GLOBAL", "SL/CLUST"),
                    "SL/GLOBAL + SL/CLUST — Global + Clustered (libgric)",
                ),
            ],
            allow_off=True,
            off_label="Off (Fixed Block-EOF Only)",
        )
        + "    </div>\n"
        '    <div class="algo-pipe-sub algo-sub-cmodes" id="algo-sub-cmodes">\n'
        '      <div class="algo-pipe-sub-hdr">'
        "2. Inner Control-Mode Optimization (Decoupled Rotation Matrix Q)</div>\n"
        + _render_select_card(
            "cmodes-mode",
            "Inner Basis Rotation & Telescope-Vibration Notch (strictly inside modalfilter)",
            "planned",
            [
                _opt("CMODES/ROT", "CMODES/ROT — Noise-Whitened Inner Rotation Q"),
                _combo_opt(
                    ("CMODES/ROT", "CMODES/NOTCH"),
                    "CMODES/ROT + CMODES/NOTCH — Q-Rotation + 16-Mode AR(48) Notch",
                ),
            ],
            allow_off=True,
            off_label="Off (Fixed Inner Basis)",
        )
        + "    </div>\n"
        '    <div class="algo-pipe-sub algo-sub-dm" id="algo-sub-dm">\n'
        '      <div class="algo-pipe-sub-hdr">'
        "3. DM Control &amp; Multi-Stage Actuation (Downstream)</div>\n"
        '      <div class="algo-choice-group">'
        '<div class="algo-choice-lbl">'
        "DM Conditioning Order (ON/OFF): DM/MR (user f_DM) &rarr; DMch2disp &rarr; PRESH/4K (2-8 kHz) &rarr; DM</div>"
        f'<div class="algo-pipe-grid-2">{_tog("DM/MR")}{_tog("PRESH/4K")}</div></div>\n'
        '      <div class="algo-ctrl-grid-2">\n'
        + _render_select_card(
            "zpo-mode",
            "WFS Zero-Point Offset (Stg 3→2)",
            "loop_operation",
            [_opt("ZPO/FIX"), _opt("ZPO/OG")],
            allow_off=True,
            off_label="Off (No ZPO)",
        )
        + _tog("OFFL/2TO1")
        + "      </div>\n"
        "    </div>\n"
        "  </div>\n"
        "</div>\n"
    )

    diag_strip_html = (
        '<div class="algo-diag-strip" id="algo-diag-strip">\n'
        '  <div class="algo-pipe-group-hdr">'
        "<span>Diagnostics &amp; Telemetry (ON/OFF Toggles)</span>"
        '<span class="algo-pipe-group-sub">'
        "Online monitors, telemetry analysis, PSFR &amp; post-loop audits</span>"
        "</div>\n"
        '  <div class="algo-diag-cards">'
        + "".join(
            _tog(c)
            for c in (
                "WHITE/RT",
                "WHITE/OOS",
                "TLM/SYNC",
                "TLM/OPT",
                "TLM/PSFR",
                "2WFS/POST",
                "HESS/CORO",
            )
        )
        + "</div>\n"
        "</div>\n"
    )

    pipe_graph_payload = {
        str(it["code"]): {
            "name": str(it["name"]),
            "role": str(it["role"]),
            "radio_group": str(it.get("radio_group") or ""),
            "stage_req": dict(it.get("stage_req") or {"mode": "none", "stages": []}),
            "req_clauses": list(it.get("req_clauses") or []),
            "opt": list(it.get("opt") or []),
            "fb_in": list(it.get("fb_in") or []),
            "en": list(it.get("en") or []),
            "en_opt": list(it.get("en_opt") or []),
            "fb_out": list(it.get("fb_out") or []),
            "excl": list(it.get("excl") or []),
        }
        for it in items
    }

    preset_opts = "".join(
        f'<option value="{html.escape(pid, quote=True)}">'
        f"{html.escape(plbl, quote=False)}</option>"
        for pid, plbl, _ in _PIPELINE_PRESETS
    )
    preset_payload = {
        pid: {"label": plbl, "codes": list(pcodes)} for pid, plbl, pcodes in _PIPELINE_PRESETS
    }

    outline_legend = (
        '<div class="algo-outline-legend" id="algo-outline-legend">'
        "<strong>Choice State:</strong>"
        '<span class="outline-key-chip outline-key-sel">&#10003; Active</span>'
        '<span class="outline-key-chip outline-key-avail">&#9675; Available</span>'
        '<span class="outline-key-chip outline-key-lock">&#8856; Disabled (needs prereq)</span>'
        "<strong>Hover Preview:</strong>"
        '<span class="outline-key-chip outline-key-focus">&#9733; Hovered</span>'
        '<span class="outline-key-chip outline-key-req">&larr; Required</span>'
        '<span class="outline-key-chip outline-key-opt">&#9671; Optional</span>'
        '<span class="outline-key-chip outline-key-down">&rarr; Enables</span>'
        '<span class="outline-key-chip outline-key-fb">&#8644; Feedback</span>'
        '<span class="outline-key-chip outline-key-excl">&#10005; Exclusive</span>'
        "</div>\n"
    )

    return (
        '<div class="algo-pipe-toolbar">'
        '<div class="toolbar-group">'
        '<label class="filter-inline-label" for="algo-pipe-preset-select">Preset Stack:</label>'
        '<select class="algo-toolbar-select algo-preset-select" id="algo-pipe-preset-select" '
        'aria-label="Load Preset Stack">'
        '<option value="">Custom / Manual Configuration</option>'
        f"{preset_opts}</select>"
        '<button type="button" class="btn-sm" id="algo-pipe-reset">Reset Baseline</button>'
        '<button type="button" class="btn-sm" id="algo-pipe-clear">Clear Choices</button>'
        "</div>"
        '<div class="toolbar-group">'
        '<label class="filter-inline-label" for="algo-pipe-depth-select">Hover Scope:</label>'
        '<select class="algo-toolbar-select" id="algo-pipe-depth-select" '
        'aria-label="Hover Dependency Scope">'
        '<option value="direct" selected>Direct Neighbors</option>'
        '<option value="full">Full Dependency Chain</option>'
        "</select>"
        "</div></div>\n"
        + outline_legend
        + '<div class="algo-pipe-status" id="algo-pipe-status">'
        "<span>Use the pulldown menus for mutually exclusive / ordered choices and ON/OFF switches "
        "for standalone options. Disabled controls and unavailable menu options display their "
        "missing prerequisites directly in each box; hover any control to trace its dependency "
        "chain.</span>"
        "</div>\n"
        '<div class="algo-pipe-workspace" id="algo-pipe-workspace">\n'
        + sim_strip_html
        + mid_board_html
        + diag_strip_html
        + "</div>\n"
        + '<div class="algo-pipe-profile" id="algo-pipe-profile"></div>\n'
        + '<div class="algo-pipe-guidance" id="algo-pipe-guidance"></div>\n'
        f'<script type="application/json" id="algo-pipe-graph-data">'
        f"{safe_json_embed(pipe_graph_payload)}</script>\n"
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


def _build_variant_link_map(
    algo_catalog: dict[str, object],
) -> dict[str, tuple[str, str, str]]:
    """Map every algorithm code and CODE/OPT variant code to (href, role, tooltip)."""
    entries: list[dict[str, object]] = algo_catalog["entries"]  # type: ignore[assignment]
    vmap: dict[str, tuple[str, str, str]] = {}
    for e in entries:
        code = str(e["code"])
        slug = str(e["slug"])
        role = str(e["role"])
        name = str(e["name"])
        base_href = f"./{html.escape(slug, quote=True)}/index.html"
        vmap[code] = (base_href, role, f"{code} — {name}")
        for v in e.get("variants") or []:
            if not isinstance(v, dict):
                continue
            vcode = str(v.get("code") or "")
            vanc = str(v.get("anchor") or make_algo_slug(vcode))
            vsum = str(v.get("summary") or name)
            if vcode and vcode not in vmap:
                vmap[vcode] = (
                    f"{base_href}#{html.escape(vanc, quote=True)}",
                    role,
                    f"{vcode} — {vsum}",
                )
    return vmap


def _link_code(
    code: str,
    vmap: dict[str, tuple[str, str, str]],
    label: str | None = None,
) -> str:
    """Render an inline clickable code pill linking to the entry page or variant anchor."""
    info = vmap.get(code)
    text = html.escape(label or code, quote=False)
    if not info:
        return f"<code>{text}</code>"
    href, role, tip = info
    return (
        f'<a class="algo-inline-code cat-{role}" href="{href}" '
        f'title="{html.escape(tip, quote=True)}">{text}</a>'
    )


def _link_report(slug: str, label: str, staged_slugs: set[str]) -> str:
    """Link to a staged report under ../<slug>/index.html if present in this site build."""
    esc = html.escape(label, quote=False)
    if slug in staged_slugs:
        return f'<a href="../{html.escape(slug, quote=True)}/index.html">{esc}</a>'
    return f"<span>{esc}</span>"


def _render_executive_summary(
    hierarchy: dict[str, object],
    algo_catalog: dict[str, object],
) -> str:
    """Render a clear ~1-2 page executive summary of main algorithm options and rationale."""
    vmap = _build_variant_link_map(algo_catalog)
    staged_metas = list(hierarchy.get("all_metas") or [])
    staged_slugs = {
        str(m["slug"]) for m in staged_metas if isinstance(m, dict) and m.get("slug")
    }

    def C(code: str, label: str | None = None) -> str:
        return _link_code(code, vmap, label)

    def R(slug: str, label: str) -> str:
        return _link_report(slug, label, staged_slugs)

    ref_link = '<a href="../reference/index.html">CLI, Env &amp; FPS Options Reference</a>'

    return (
        '<section class="explorer-panel algo-guide-panel" id="algorithm-summary">\n'
        '<div class="algo-guide-header">\n'
        "  <h2>Executive Summary: Main Algorithm Options &amp; Design Rationale</h2>\n"
        '  <nav class="algo-guide-toc" aria-label="Algorithm summary navigation">'
        '<a href="#sum-calib">1. Calibration</a>'
        '<a href="#sum-core">2. Core Control</a>'
        '<a href="#sum-cmodes">3. Inner Rotation</a>'
        '<a href="#sum-dm">4. DM Actuation</a>'
        '<a href="#sum-diag">5. Diagnostics &amp; Sim</a>'
        '<a href="#sum-guide">6. Decision Guide</a>'
        '<a href="#dependency-graph">Interactive Map &darr;</a>'
        '<a href="#algorithms-root">Full Catalog &darr;</a>'
        "</nav>\n"
        "</div>\n"
        '<p class="algo-guide-lead">'
        "<strong>Core Design Principle &mdash; Why a 3-Layer Decoupled Architecture:</strong> "
        "Modern extreme-AO loops (such as Subaru AO3k + SCExAO) must handle four distinct physical "
        "challenges at once: time-varying Pyramid WFS optical gain, frozen-flow atmospheric lag and "
        "sudden wind changes, narrowband telescope/bench vibrations (10&ndash;150&nbsp;Hz), and "
        "high-frequency deformable mirror (DM) mechanical plate resonances (~1&ndash;2&nbsp;kHz). "
        "Our benchmarks show that entangling these concerns&mdash;for example, rotating the modal "
        "basis underneath a predictive filter, or running online self-learning without a fixed "
        "linear anchor&mdash;causes severe transients and noise amplification. CACAO therefore "
        "separates the loop into <strong>Offline &amp; Online Calibration</strong> feeding "
        "<strong>three strictly decoupled real-time layers</strong>: "
        "(1)&nbsp;<em>Core Control</em> in a fixed outer modal basis, "
        "(2)&nbsp;<em>Inner Control-Mode Rotation</em> confined inside <code>modalfilter</code>, and "
        "(3)&nbsp;<em>Downstream DM Actuation Conditioning</em> (multi-rate pacing upstream of "
        "anti-vibration pre-shaping). Every code pill below links directly to its specification, "
        f"CLI flags ({ref_link}), and full benchmark reports "
        f"({R('control_architecture_synthesis', 'Architecture Synthesis')}, "
        f"{R('control_implementation_plan', 'Implementation Plan')}).</p>\n"
        '<div class="algo-guide-sections">\n'
        # --- Section 1: Calibration ---
        '  <article class="algo-guide-block cat-calibration" id="sum-calib">\n'
        '    <div class="algo-synth-kicker">1 &middot; Offline &amp; Online Calibration</div>\n'
        "    <h3>Plant Identification, Optical Gain &amp; Wind Profiling</h3>\n"
        "    <p>Accurate control begins with an unbiased model of loop timing, DM dynamics, and "
        "time-varying Pyramid WFS sensitivity:</p>\n"
        "    <ul>\n"
        f"      <li><strong>Baseline Latency &amp; Static RM:</strong> {C('MLAT')} measures "
        f"fractional hardware/software lag (&lt;0.05&nbsp;fr); {C('RM')} acquires the static "
        f"response matrix via unthrottled lockstep ({C('RM/FAST')}), real-time Hadamard pokes "
        f"({C('RM/HAD')}), or direct low-order Zernikes ({C('RM/DIR')} for Stage-3 LLOWFS).</li>\n"
        f"      <li><strong>Dynamic 3D Plant RM (Continuous Plate DMs):</strong> Static RMs miss "
        "mechanical overshoot and 34% cross-mode plate coupling on the 64&times;64 ALPAO DM. "
        f"Sub-frame stroboscopic {C('3DRM/P1')} resolves the spatiotemporal tensor through the "
        f"operational WFS, {C('3DRM/FACT')} factors it into unity-DC {C('3DRM/DIAG')} (MEMS) or "
        f"{C('3DRM/MIMO')} (plate) kernels, and {C('LAG/2PT')} aligns science-cadence IPC lag. "
        f"When a DM pre-shaper is active, {C('3DRM/P2')} re-measures the shaped plant.</li>\n"
        f"      <li><strong>Online Optical Gain (PyWFS):</strong> On-sky PyWFS gain drops with "
        f"seeing and residual WFE. Standalone/Stage-1 loops track it with sparse held DM probes "
        f"({C('OG/POKE')}, 0.6% live error, zero PSOL leak); 2-stage systems use passive, "
        f"probe-free {C('2WFS/LIVE')} ({C('2WFS/IV')}) to calibrate Stage-2 optical gain "
        f"(0.8&ndash;3.3%), scale ZPO, and solve blind DM2&rarr;DM1 offload, cross-checked against "
        f"active {C('SRM')}.</li>\n"
        f"      <li><strong>Live Wind Profiling:</strong> {C('WIND')} tracks multi-layer frozen-flow "
        f"velocities ({C('WIND/2D')}, &lt;0.05&nbsp;m/s) and Fresnel layer altitudes "
        f"({C('WIND/ALT')}) from PSOL telemetry to supply instant physics priors to Block-EOF.</li>\n"
        "    </ul>\n"
        '    <div class="algo-guide-links"><strong>Deep dives:</strong> '
        f"{R('dm64_dyn_rm_calib', '64×64 3D RM Calibration')} &middot; "
        f"{R('calib_2wfs1dm_report', '2WFS1DM Online Calibration')} &middot; "
        f"{R('dm_dynamics_report', 'ALPAO Plate Dynamics')}</div>\n"
        "  </article>\n"
        # --- Section 2: Core Control ---
        '  <article class="algo-guide-block cat-loop_operation" id="sum-core">\n'
        '    <div class="algo-synth-kicker">2 &middot; Layer 1 &middot; Fixed Outer Modal Basis</div>\n'
        "    <h3>Core Real-Time Wavefront Control Ladder</h3>\n"
        "    <p>Every loop runs in a <strong>fixed outer modal basis</strong> built atop an unbiased "
        f"Pseudo Open-Loop observer ({C('PSOL')}: {C('PSOL/2TAP')} scalar delay, {C('PSOL/DIAG')} "
        f"diagonal FIR for MEMS, or {C('PSOL/MIMO')} 3D MIMO cutting coupled plate error 12.2&times;). "
        "Choose the control level matched to your SNR and regime:</p>\n"
        "    <ul>\n"
        f"      <li><strong>Leaky Integrator ({C('INT')} + {C('MOPT')}):</strong> {C('INT/LEAK')} / "
        f"{C('INT/MGAIN')} is the zero-warmup baseline. Adding {C('MOPT')} ({C('MOPT/LIVE')}, "
        f"{C('MOPT/FAINT')}, {C('MOPT/KERN')}) autotunes per-mode (gain, leak) online from "
        "multi-resolution PSDs with faint-star adaptive memory and a ringing guard (&minus;29.8% WFE).</li>\n"
        f"      <li><strong>Per-Mode Autoregressive ({C('PF/AR')}):</strong> Fast-converging "
        "(256-frame) diagonal temporal AR(P) predictor; captures per-mode vibrations but cannot "
        "model spatial wind transport across modes (mutually exclusive with Block-EOF).</li>\n"
        f"      <li><strong>Cross-Mode Block-EOF ({C('EOF')} &mdash; Recommended Anchor):</strong> "
        f"Learns coupled spatio-temporal frozen-flow prediction ({C('EOF/BASE')}) with composable "
        f"upgrades: {C('EOF/ZOH')} prevents Stage-1 DC collapse (keep OFF on Stage-2 high-pass "
        f"residuals), {C('EOF/MEM')} &amp; {C('EOF/REG')} retain long/multi-regime memory, "
        f"{C('EOF/WIND')} blends {C('WIND')} physics Grams for instant cold-start (+70% VR) and "
        f"6.2&times; wind-switch rescue, and {C('EOF/FX')} compensates unshaped ringing DMs "
        "(mutually exclusive with <code>EOF/WIND</code>).</li>\n"
        f"      <li><strong>Cascaded Online Self-Learning ({C('SELFLEARN')}):</strong> Adds "
        f"{C('SL/GLOBAL')} (single-model RLS) and {C('SL/CLUST')} (<code>libgric</code> multi-cluster "
        "RLS) strictly <em>on top of Fixed-Basis Block-EOF</em> with causal James-Stein gates. "
        "Cuts unmodulated PyWFS nonlinear residuals &minus;36.4% while maintaining 1.000&times; "
        "white-noise null safety (1.43&nbsp;nm vs. 18.35&nbsp;nm standalone leak).</li>\n"
        "    </ul>\n"
        '    <div class="algo-guide-links"><strong>Deep dives:</strong> '
        f"{R('predictive_control_report', 'Predictive Control Study')} &middot; "
        f"{R('control_architecture_synthesis', '7-Regime & Null-Test Shootout')}</div>\n"
        "  </article>\n"
        # --- Section 3: Inner Control Modes ---
        '  <article class="algo-guide-block cat-planned" id="sum-cmodes">\n'
        '    <div class="algo-synth-kicker">3 &middot; Layer 2 &middot; Decoupled Inner Loop (Planned C)</div>\n'
        "    <h3>Inner Control-Mode Rotation &amp; Telescope Vibration Notch</h3>\n"
        f"    <p>Adaptive basis optimization ({C('CMODES')}) improves SNR separation and cancels "
        "narrowband optical vibrations, provided it never disturbs outer predictive buffers:</p>\n"
        "    <ul>\n"
        f"      <li><strong>Noise-Whitened Rotation ({C('CMODES/ROT')}):</strong> Continuously "
        "rotates the inner modal subspace inside <code>modalfilter</code> via an orthogonal/"
        "whitened matrix <code>Q</code> (<code>WFS_rot = Q^T WFS</code>, "
        "<code>DM = Q DM_rot</code>) with atomic ping-pong updates (+2.4&nbsp;&mu;s RT cost @ 128 m).</li>\n"
        f"      <li><strong>16-Mode Telescope-Vibration Notch ({C('CMODES/NOTCH')}):</strong> "
        "Applies selective ridge-regularized <code>AR(48)</code> notch filters on the top rotated "
        "modes to suppress 10&ndash;150&nbsp;Hz telescope/bench structural lines (&minus;14% to "
        "&minus;19% WFE; automatically zeroed on pure white noise).</li>\n"
        "      <li><strong>Mandatory Decoupling &amp; History Re-Projection:</strong> Keeping "
        "<code>Q</code> strictly inside <code>modalfilter</code> leaves outer <code>modevalOL</code>, "
        f"{C('EOF')}, and {C('SELFLEARN')} invariant, while rotating the AR(48) history buffer "
        "(<code>H_new = (Q_new^T Q_old) H_old</code>) makes basis swaps bumpless (47.5&nbsp;nm vs. "
        "286.8&nbsp;nm unprojected or 213&ndash;367&nbsp;nm coupled spikes).</li>\n"
        "    </ul>\n"
        '    <div class="algo-guide-links"><strong>Deep dives:</strong> '
        f"{C('CMODES', 'CMODES Specification')} &middot; "
        f"{R('control_architecture_synthesis', 'Basis-Swap & Vibration Benchmarks')} &middot; "
        f"{R('control_implementation_plan', 'C/milk-mltools Plan (C1 & ML1)')}</div>\n"
        "  </article>\n"
        # --- Section 4: DM Control & Actuation ---
        '  <article class="algo-guide-block cat-calibration" id="sum-dm">\n'
        '    <div class="algo-synth-kicker">4 &middot; Layer 3 &middot; Downstream DM Conditioning &amp; Multi-Stage</div>\n'
        "    <h3>DM Pre-Shaping, Faint-Star Multi-Rate Pacing &amp; Offload</h3>\n"
        "    <p>Downstream of modal reconstruction, hardware-aware DM conditioning suppresses plate "
        "mechanics, bridges slow faint-star WFS rates, and coordinates multi-stage DMs:</p>\n"
        "    <ul>\n"
        f"      <li><strong>DM Mechanical Anti-Vibration Pre-Shaper ({C('PRESH')} / {C('PRESH/CAL')}):</strong> "
        "Causal 2&ndash;8&nbsp;kHz unity-DC FIR filter cancelling ~1&ndash;2&nbsp;kHz ALPAO plate "
        "resonances (distinct from optical vibrations) using Toeplitz WFS-exposure deconvolution "
        "(<code>deconv_exp=ON</code>). Supports five modes: uniform SISO (<code>KMODE=2</code>), "
        "per-actuator SISO (<code>KMODE=3</code>, 2.1&times; less free-rim ringing), "
        "<strong>per-actuator 5&times;5 local-stencil MIMO (<code>KMODE=4</code>, 100&ndash;278&times; "
        "2D wave energy cut across interior &amp; asymmetric free rim)</strong>, and modal MIMO "
        "(<code>KMODE=0</code>, crushing 500&nbsp;Hz astrogrid 1.5&nbsp;kHz resonance &minus;13&nbsp;dB).</li>\n"
        f"      <li><strong>Faint-Star Slow-WFS + Multi-Rate DM ({C('MRDM')}):</strong> At m=10, "
        f"slowing Stage-1 WFS to ~250&nbsp;Hz ({C('WFS/SLOW')}, staying above the 4-spider "
        "island-petaling floor) boosts predictive H-Strehl 68.2%&rarr;80.4% (86.9% 2-stage) where "
        f"integrators collapse. Driving smooth ramps ({C('EOF/VEL')} &rarr; {C('DM/MR')} at user "
        "hardware rate <code>f_DM</code>) strictly <em>upstream</em> of "
        f"<code>DMch2disp &rarr; {C('PRESH/4K')}</code> cuts pre-shaper stroke 18&ndash;40%, HF "
        "ripple &minus;35%, and 1&nbsp;kHz plate energy &minus;40% with 0 clips and 0.000&nbsp;fr lag.</li>\n"
        f"      <li><strong>Multi-Stage Coordination:</strong> Live OG-scaled {C('ZPO')} ({C('ZPO/OG')}) "
        "prevents Stage-2 PyWFS from fighting Stage-3 LLOWFS (6.6&times; less fightback); blind "
        f"{C('OFFL')} ({C('OFFL/2TO1')}) offloads 100% of static DM2 stroke onto DM1.</li>\n"
        "    </ul>\n"
        '    <div class="algo-guide-links"><strong>Deep dives:</strong> '
        f"{R('dm_preshaper_demo', '8 kHz DM Pre-Shaper Demo & Videos')} &middot; "
        f"{C('MRDM', 'Multi-Rate DM Spec')} &middot; "
        f"{R('control_implementation_plan', 'Work Packages C3 & C3b')}</div>\n"
        "  </article>\n"
        # --- Section 5: Diagnostics & Simulation ---
        '  <article class="algo-guide-block algo-guide-block-wide cat-analysis" id="sum-diag">\n'
        '    <div class="algo-synth-kicker">5 &middot; Verification, Safety Gates &amp; Physics Testbeds</div>\n'
        "    <h3>Online Whiteness Monitors, Pure-C Telemetry Analysis &amp; GPU Simulation</h3>\n"
        "    <p>Every real-time control choice is paired with non-intrusive health gates and "
        "hardware-calibrated physics validation: "
        f"{C('WHITE')} ({C('WHITE/RT')} &amp; {C('WHITE/OOS')}) monitors lag&nbsp;&ge;&nbsp;ceil(&tau;) "
        "residual whiteness (<code>Q_vw</code>), cross-mode coupling, ZPO fightback, and white-noise "
        f"null leakage; {C('TLM')} ({C('TLM/SYNC')}, {C('TLM/OPT')}, {C('TLM/PSFR')}) and "
        f"{C('2WFS/POST')} provide pure-C post-loop synchronization, ETF gain audits, polychromatic "
        "PSF reconstruction, and 2WFS1DM verification. All algorithms are stress-tested end-to-end "
        f"on {C('SIM/PLATE')} ({C('SIM/FUSED')} zero-hop GPU bench &amp; {C('SIM/MOD')} modular "
        f"daemons with a 64&times;64 coupled plate PDE) and {C('SIM/WROT')} ({C('SIM/TURB')} Mauna Kea "
        f"turbulence + phase-continuous wind rotation), paving the way for future coronagraphic "
        f"focal-plane control ({C('HESS/CORO')}).</p>\n"
        '    <div class="algo-guide-links"><strong>Explore more:</strong> '
        f"{C('WHITE', 'Whiteness Monitor')} &middot; "
        f"{C('TLM', 'Telemetry & PSFR')} &middot; "
        f"{C('SIM/PLATE', 'GPU Plate Bench')} &middot; "
        f"{C('HESS/CORO', 'Planned Coronagraphic Control')} &middot; "
        '<a href="../simulations/index.html">Live GPU Simulation Archive</a> &middot; '
        f"{ref_link}</div>\n"
        "  </article>\n"
        "</div>\n"
        # --- Section 6: Decision Guide Table ---
        '<div class="algo-decision-wrap" id="sum-guide">\n'
        "<h3>6. Quick Selection Guide: Choosing an Algorithm Stack by Observing Regime</h3>\n"
        '<div class="table-wrap"><table class="algo-synth-table"><thead><tr>'
        "<th>Observing / Hardware Regime</th>"
        "<th>Recommended Option Stack (Clickable)</th>"
        "<th>Key Rationale &amp; Detailed Report</th>"
        "</tr></thead><tbody>"
        "<tr>"
        "<td><strong>Bright-Star High-Contrast 2-Stage (Default Science)</strong></td>"
        f"<td>{C('3DRM/MIMO')} &rarr; {C('PRESH/4K')} &middot; {C('PSOL/MIMO')} &middot; "
        f"{C('EOF/BASE')} + {C('EOF/ZOH')} + {C('EOF/WIND')} &middot; {C('OG/POKE')} + "
        f"{C('2WFS/IV')} &middot; {C('ZPO/OG')} + {C('OFFL/2TO1')}</td>"
        f"<td>Linearizes ALPAO plate, predicts frozen-flow &amp; wind switches (6.2&times; rescue), "
        f"and tracks Stage-1/2 optical gain passively. "
        f"See {R('control_architecture_synthesis', 'Architecture Synthesis')}.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Unmodulated 0&nbsp;&lambda;/D PyWFS / Nonlinear Optical Gain</strong></td>"
        f"<td>Above + {C('SL/GLOBAL')} + {C('SL/CLUST')} (cascaded on {C('EOF/BASE')}) + "
        f"{C('2WFS/IV')} + {C('WHITE/RT')}</td>"
        f"<td>Clustered RLS tracks state-dependent PyWFS nonlinearity (&minus;36.4% WFE) while "
        f"causal Stein gates guarantee 1.000&times; white-noise safety. "
        f"See {C('SELFLEARN', 'SELFLEARN')} &amp; {R('calib_2wfs1dm_report', '2WFS1DM Report')}.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Faint-Star (m&nbsp;&ge;&nbsp;9&ndash;10) Photon/RON-Limited</strong></td>"
        f"<td>{C('WFS/SLOW')} (&ge;250&nbsp;Hz) + {C('EOF/BASE')} + {C('EOF/VEL')} + "
        f"{C('DM/MR')} (user <code>f_DM</code>) &rarr; {C('PRESH/4K')} + dark sub</td>"
        f"<td>Slower WFS boosts SNR (+12&nbsp;pts H-Strehl vs. 1&nbsp;kHz) while smooth ramps cut "
        f"pre-shaper stroke 18&ndash;40% and plate ripples &minus;40%. "
        f"See {C('MRDM', 'MRDM')} &amp; {R('control_architecture_synthesis', 'Faint-Star Shootout')}.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Telescope Vibrations (10&ndash;150&nbsp;Hz) &amp; Fast Astrogrids (500&nbsp;Hz)</strong></td>"
        f"<td>{C('CMODES/ROT')} + {C('CMODES/NOTCH')} (optical lines) &middot; "
        f"{C('PRESH/4K')} (<code>KMODE=0</code> astrogrid MIMO / <code>KMODE=4</code> 5&times;5 per-act)</td>"
        f"<td>Decoupled inner AR(48) notch kills 10&ndash;150&nbsp;Hz lines without basis-swap spikes; "
        f"8&nbsp;kHz pre-shaper crushes 1.5&nbsp;kHz astrogrid resonance &minus;13&nbsp;dB and 2D plate waves "
        f"100&ndash;278&times;. See {R('dm_preshaper_demo', 'DM Pre-Shaper Demo')}.</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Minimal-Calibration / Conservative Fallback Loop</strong></td>"
        f"<td>{C('MLAT')} + {C('RM/FAST')} + {C('PSOL/DIAG')} + {C('INT/MGAIN')} + "
        f"{C('MOPT/LIVE')} + {C('PRESH/4K')} (<code>KMODE=2/3</code>) + {C('WHITE/RT')}</td>"
        f"<td>Zero predictive training buffer required; {C('MOPT')} autotunes gains/leaks online and "
        f"per-actuator SISO pre-shaping damps DM overshoot &gt;10&times; at &lt;12&nbsp;&mu;s cost. "
        f"See {C('MOPT', 'MOPT')} &amp; {C('PRESH', 'PRESH')}.</td>"
        "</tr>"
        "</tbody></table></div>\n"
        "</div>\n"
        "</section>"
    )


def _render_architecture_synthesis(
    hierarchy: dict[str, object],
    algo_catalog: dict[str, object],
) -> str:
    """Render concise taxonomy, combination rules, and empirical benchmark findings."""
    vmap = _build_variant_link_map(algo_catalog)
    staged_metas = list(hierarchy.get("all_metas") or [])
    staged_slugs = {
        str(m["slug"]) for m in staged_metas if isinstance(m, dict) and m.get("slug")
    }

    def C(code: str, label: str | None = None) -> str:
        return _link_code(code, vmap, label)

    cta_btns: list[str] = []
    if "control_architecture_synthesis" in staged_slugs:
        cta_btns.append(
            '<a class="btn" href="../control_architecture_synthesis/index.html">'
            "Read Full Control Architecture &amp; Benchmark Synthesis Report (7 Figures) &rarr;</a>"
        )
    if "dm_preshaper_demo" in staged_slugs:
        cta_btns.append(
            '<a class="btn btn-secondary" href="../dm_preshaper_demo/index.html">'
            "View 8 kHz DM Pre-Shaper Demo &amp; Per-Actuator Videos &rarr;</a>"
        )
    if "control_implementation_plan" in staged_slugs:
        cta_btns.append(
            '<a class="btn btn-secondary" href="../control_implementation_plan/index.html">'
            "Read milk / cacao / milk-mltools Implementation Plan &rarr;</a>"
        )
    report_cta = (
        f'<div class="algo-synth-cta">{"".join(cta_btns)}</div>\n'
        if cta_btns
        else ""
    )

    return (
        '<section class="explorer-panel algo-synth-panel" id="architecture-synthesis">\n'
        "<h2>Algorithm Categories, Combination Rules &amp; Verified Benchmark Findings</h2>\n"
        '<p class="muted">Compact reference summarizing the three decoupled control layers, '
        "enforced combination rules, and quantitative benchmark verification across offline "
        "multi-regime and live GPU <code>cacaosim</code> runs. Click any algorithm code to open "
        "its specification.</p>\n"
        '<div class="algo-synth-grid">\n'
        '  <article class="algo-synth-card cat-loop_operation">\n'
        '    <div class="algo-synth-kicker">Category 1 &middot; Fixed Outer Modal Basis</div>\n'
        "    <h3>Core Real-Time Control Progression</h3>\n"
        '    <ol class="algo-synth-steps">\n'
        f"      <li><strong>Manual Leaky Integrator</strong> ({C('INT/LEAK')}, {C('INT/MGAIN')}) &mdash; static gain &amp; leak baseline.</li>\n"
        f"      <li><strong>Autotuned Leaky Integrator</strong> ({C('MOPT')}) &mdash; online per-mode PSD gain/leak optimization with faint-star memory &amp; ringing guard.</li>\n"
        f"      <li><strong>Per-Mode Autoregressive Filter</strong> ({C('PF/AR')}) &mdash; diagonal online <code>AR(P)</code> over PSOL; fast warmup, no cross-mode wind transport.</li>\n"
        f"      <li><strong>Cross-Mode Block-EOF</strong> ({C('EOF/BASE')} + {C('EOF/ZOH', 'ZOH')}/{C('EOF/MEM', 'MEM')}/{C('EOF/REG', 'REG')}/{C('EOF/WIND', 'WIND')}/{C('EOF/FX', 'FX')}) &mdash; spatio-temporal frozen-flow predictor &amp; mandatory linear anchor.</li>\n"
        f"      <li><strong>Cascaded Global Online Adaptive Filter</strong> ({C('SL/GLOBAL')}) &mdash; single-model online RLS residual refiner with causal Stein gate on top of Block-EOF.</li>\n"
        f"      <li><strong>Cascaded Clustered Self-Learning</strong> ({C('SL/CLUST')}) &mdash; <code>libgric</code> multi-cluster RLS residual layer handling nonlinear PyWFS optical gain &amp; state switches.</li>\n"
        "    </ol>\n"
        f'    <p class="algo-synth-note"><strong>Prerequisite:</strong> Unbiased {C("PSOL")} '
        f"({C('PSOL/2TAP', '2-tap')} / {C('PSOL/DIAG', 'Diag FIR')} / {C('PSOL/MIMO', '3D MIMO')} + "
        "exact multi-rate ramp integral), WFS dark subtraction, and online calibration "
        f"({C('OG/POKE')}, {C('2WFS/LIVE')}, {C('WIND')}).</p>\n"
        "  </article>\n"
        '  <article class="algo-synth-card cat-planned">\n'
        '    <div class="algo-synth-kicker">Category 2 &middot; Decoupled Inner Loop</div>\n'
        "    <h3>Inner Control-Mode Optimization (Rotation Matrix)</h3>\n"
        "    <ul>\n"
        f"      <li><strong>Noise-Whitened Inner Basis Rotation</strong> ({C('CMODES/ROT')}): "
        "adapts an inner orthogonal/whitened matrix <code>Q</code> inside <code>modalfilter</code> "
        "(<code>WFS_rot = Q^T WFS</code>, <code>DM = Q DM_rot</code>) to separate high-SNR from "
        "low-SNR directions with atomic swaps.</li>\n"
        f"      <li><strong>Inner 16-Mode Vibration Notch</strong> ({C('CMODES/NOTCH')}): "
        "targets narrowband <strong>telescope &amp; optical-bench vibrations</strong> (10&ndash;150 Hz) "
        "via <code>AR(48)</code> on the leading rotated modes, with mandatory in-place history "
        "re-projection <code>H_new = (Q_new^T Q_old) H_old</code>.</li>\n"
        "      <li><strong>Strict Decoupling Invariant:</strong> Outer <code>DMmodes</code>, "
        f"<code>modevalOL</code>, {C('EOF')}, and {C('SELFLEARN')} stay 100% fixed.</li>\n"
        "    </ul>\n"
        '    <p class="algo-synth-note"><strong>Status:</strong> Benchmark-validated '
        "(<code>47.5 nm</code> bumpless swaps, <code>+2.4 us</code> RT overhead); slated for "
        "<code>cacao</code> / <code>milk-mltools</code> C deployment.</p>\n"
        "  </article>\n"
        '  <article class="algo-synth-card cat-calibration">\n'
        '    <div class="algo-synth-kicker">Category 3 &middot; Downstream Actuation</div>\n'
        "    <h3>DM Control: Multi-Rate &amp; Anti-Vibration</h3>\n"
        "    <ul>\n"
        f"      <li><strong>Multi-Rate DM Pacing</strong> ({C('DM/MR')}): "
        "<code>cacao-fpsexec-mvalpacer</code> drives smooth centered linear ramps at a "
        "user-specified hardware-dependent rate <code>f_DM</code> (e.g. 1 kHz on AO3k ALPAO; "
        "<code>K_sub = round(f_DM / f_WFS)</code>, zero-latency <code>j=0</code> wake) from "
        f"Block-EOF's zero-DC velocity solver ({C('EOF/VEL')}) when a faint-star WFS slows to 250&ndash;500 Hz.</li>\n"
        f"      <li><strong>DM Mechanical Anti-Vibration Pre-Shaper</strong> ({C('PRESH/4K')}): "
        "2&ndash;8 kHz modal (<code>KMODE=0..2</code>) &amp; per-actuator (<code>KMODE=3, 4</code>) "
        "FIR filter (<code>dmpreshaper</code>) cancelling ALPAO <strong>mechanical plate vibrations</strong> "
        "(<code>f0 ~ 1 kHz</code>), free-rim reflections, &amp; cross-talk.</li>\n"
        f"      <li><strong>Multi-Stage DM Coordination:</strong> Live OG-scaled WFS Zero-Point Offset "
        f"({C('ZPO/OG')}) and blind DM2&rarr;DM1 static stroke offload ({C('OFFL/2TO1')}).</li>\n"
        "    </ul>\n"
        '    <p class="algo-synth-note"><strong>Required Hardware Chain:</strong> '
        "<code>mvalpacer (user f_DM) &rarr; mvalC2dm &rarr; DMch2disp &rarr; dmpreshaper (f_presh &ge; f_DM) &rarr; DM</code>.</p>\n"
        "  </article>\n"
        "</div>\n"
        '<div class="algo-synth-flow" aria-label="Recommended decoupled control signal flow">'
        '<span class="algo-flow-step cat-simulation">WFS (dark-sub)</span>'
        '<span class="algo-flow-arr">&rarr;</span>'
        f'<span class="algo-flow-step cat-loop_operation">{C("PSOL/MIMO", "PSOL (MIMO + MR ramp)")}</span>'
        '<span class="algo-flow-arr">&rarr;</span>'
        f'<span class="algo-flow-step cat-loop_operation">Fixed Outer Basis: {C("EOF", "Block-EOF")} &rarr; {C("SELFLEARN", "Cascaded Self-Learning")}</span>'
        '<span class="algo-flow-arr">&rarr;</span>'
        f'<span class="algo-flow-step cat-planned">Decoupled Inner modalfilter: {C("CMODES/ROT", "Q-Rotation")} + {C("CMODES/NOTCH", "AR(48) Notch")}</span>'
        '<span class="algo-flow-arr">&rarr;</span>'
        f'<span class="algo-flow-step cat-loop_operation">{C("DM/MR", "Multi-Rate Pacer")} (user f_DM) &rarr; DMch2disp &rarr; {C("PRESH/4K", "Plate Pre-Shaper")} &rarr; DM</span>'
        "</div>\n"
        "<h3>Combination Rules &amp; Verified Anti-Patterns</h3>\n"
        '<div class="table-wrap"><table class="algo-synth-table"><thead><tr>'
        "<th>Architectural Rule</th><th>Allowed / Recommended Pattern</th>"
        "<th>Anti-Pattern to Avoid</th><th>Measured Evidence</th>"
        "</tr></thead><tbody>"
        "<tr><td><strong>Self-Learning Cascade</strong></td>"
        f"<td>Cascade {C('SL/GLOBAL')} &rarr; {C('SL/CLUST')} on top of Fixed-Basis {C('EOF/BASE')} with causal Stein gates.</td>"
        "<td>Running self-learning standalone (replacing Block-EOF).</td>"
        "<td>Pure 40 nm white-noise null: <strong>1.43 nm (1.000&times;)</strong> cascaded vs <strong>18.35 nm (1.10&times;)</strong> standalone; pure turb 18.17 vs 33.5 nm.</td></tr>"
        "<tr><td><strong>Basis-Rotation Decoupling</strong></td>"
        f"<td>Keep {C('CMODES/ROT')} &amp; {C('CMODES/NOTCH')} strictly inside <code>modalfilter</code>; re-project AR(48) history on every swap.</td>"
        f"<td>Rotating the outer basis underneath {C('EOF')} or {C('SELFLEARN')}, or swapping <code>Q</code> without history re-projection.</td>"
        "<td>Mid-run basis swaps: <strong>47.5 nm bumpless</strong> decoupled + re-projected vs <strong>286.8 nm</strong> unprojected and <strong>213&ndash;367 nm</strong> coupled spikes.</td></tr>"
        "<tr><td><strong>Multi-Rate &times; Pre-Shaper Order</strong></td>"
        f"<td>Place {C('DM/MR')} (<code>mvalpacer</code>) upstream of <code>DMch2disp</code> &rarr; {C('PRESH/4K')} (<code>dmpreshaper</code>).</td>"
        "<td>Placing multi-rate pacer downstream of pre-shaper, or driving 250 Hz ZOH steps straight into pre-shaper.</td>"
        "<td>Smooth 1 kHz ramps cut pre-shaper stroke <strong>18&ndash;40%</strong>, <strong>0 clips</strong>, <strong>0.000 fr</strong> added lag, <strong>&minus;35%</strong> HF ripple, <strong>&minus;40%</strong> 1 kHz plate energy.</td></tr>"
        "<tr><td><strong>Faint-Star WFS Rate Floor</strong></td>"
        f"<td>Reduce Stage-1 WFS rate from 1000 &rarr; <strong>250 Hz</strong> ({C('WFS/SLOW')}) at m=10 under {C('EOF/BASE')} + {C('DM/MR')} + WFS dark subtraction.</td>"
        "<td>Slowing an integrator to 250 Hz, slowing Stage 1 below ~250 Hz on 4-spider pupil, or omitting WFS dark subtraction.</td>"
        "<td>m=10 live GPU H-Strehl climbs <strong>68.2% &rarr; 80.4%</strong> (vs integrator 50.7% @ 500 Hz, 38.6% @ 250 Hz); 100&ndash;200 Hz hits Subaru 4-spider island petaling.</td></tr>"
        "<tr><td><strong>EOF Plant Options</strong></td>"
        f"<td>Use {C('PRESH/4K')} + {C('PSOL/MIMO')} + {C('EOF/WIND')} when shaped; reserve {C('EOF/FX')} for unshaped ringing DMs.</td>"
        f"<td>Combining {C('EOF/FX')} with {C('EOF/WIND')}, or running {C('PF/AR')} and {C('EOF/BASE')} together.</td>"
        f"<td>{C('EOF/WIND')} cuts live +60&deg; wind-switch WFE 6.16&times;; {C('EOF/FX')} cuts unshaped plate ringing <code>Q_vw</code> 26.4&times;.</td></tr>"
        "</tbody></table></div>\n"
        "<h3>Headline Verified Benchmark Summary</h3>\n"
        '<div class="algo-synth-bench-grid">\n'
        '  <div class="table-wrap"><table class="algo-synth-table"><thead><tr>'
        "<th>Offline Multi-Regime &amp; RT Shootout</th><th>Integrator</th><th>Fixed Block-EOF</th><th>Full Decoupled Stack</th>"
        "</tr></thead><tbody>"
        "<tr><td>R1 &middot; Pure Turbulence</td><td>73.77 nm</td><td>19.23 nm</td><td><strong>18.17 nm</strong> (&minus;5.5%)</td></tr>"
        "<tr><td>R2 &middot; +30 nm Telescope Vibrations</td><td>78.40 nm</td><td>25.84 nm</td><td><strong>22.22 nm</strong> (&minus;14.0%)</td></tr>"
        "<tr><td>R3 &middot; +60&deg; Wind Direction Switch</td><td>74.12 nm</td><td>17.45 nm</td><td><strong>16.35 nm</strong> (&minus;6.3%)</td></tr>"
        "<tr><td>R4 &middot; Unmodulated PyWFS Nonlinearity</td><td>41.65 nm</td><td>16.16 nm</td><td><strong>10.27 nm</strong> (&minus;36.4%)</td></tr>"
        "<tr><td>R5 &middot; Combined OG + Vibration Stress</td><td>82.19 nm</td><td>33.46 nm</td><td><strong>27.06 nm</strong> (&minus;19.1%)</td></tr>"
        "<tr><td>R6 &middot; 40 nm Pure White-Noise Null (DM leak)</td><td>8.12 nm</td><td>1.53 nm</td><td><strong>1.43 nm (1.000&times;)</strong></td></tr>"
        "<tr><td>Mid-Run Basis Swap Peak / RT CPU (128 / 256 m)</td><td>&mdash; / 22.6 &mu;s</td><td>&mdash; / 18.8 &mu;s</td><td><strong>47.5 nm / 88.9 &amp; 113.9 &mu;s</strong></td></tr>"
        "</tbody></table></div>\n"
        '  <div class="table-wrap"><table class="algo-synth-table"><thead><tr>'
        "<th>Live GPU cacaosim (23-Run Faint-Star &amp; Multi-Rate)</th><th>Baseline</th><th>Best / Optimized</th><th>Measured Gain</th>"
        "</tr></thead><tbody>"
        "<tr><td>m=10 Stage-1 Integrator (1 kHz &rarr; 500 Hz opt)</td><td>415.3 nm / 47.5% H-Sr</td><td>400.8 nm / 50.7% H-Sr</td><td>Collapses to 38.6% @ 250 Hz</td></tr>"
        "<tr><td>m=10 Stage-1 Block-EOF (1 kHz &rarr; 250 Hz)</td><td>169.6 nm / 68.2% H-Sr</td><td>130.0 nm / 80.2% H-Sr</td><td><strong>+12.0 pts H-Strehl</strong></td></tr>"
        "<tr><td>m=10 Stage-1 EOF + Multi-Rate 1 kHz DM @ 250 Hz</td><td>ZOH 130.0 nm / 80.2%</td><td><strong>129.3 nm (108.7 SS) / 80.4%</strong></td><td>&minus;18% PS stroke, 0 clips, 0.000 fr lag</td></tr>"
        "<tr><td>m=10 Full 2-Stage (Stg1 250 Hz MR + Stg2 2 kHz)</td><td>Stg1 only 129.3 nm</td><td><strong>94.0 nm / 86.9% H-Sr</strong></td><td>53.8% Vis Sr &middot; <strong>9.19&times;10<sup>&minus;5</sup></strong> coro</td></tr>"
        "<tr><td>m=6 250 Hz 2&times;2 Ablation: MR 1 kHz + 2 kHz Pre-Shaper</td><td>ZOH/PS-OFF 74.9 nm</td><td><strong>71.8 nm / 69.0% Vis Sr</strong></td><td><strong>&minus;35% HF, &minus;40% 1 kHz plate, &minus;10% coro</strong></td></tr>"
        "<tr><td>8 kHz Per-Actuator Pre-Shaper (KMODE=4 5&times;5 Stencil)</td><td>Raw 15.3&ndash;17.0% 2D wave</td><td><strong>0.92&ndash;1.70% 2D wave</strong></td><td><strong>100&ndash;278&times; wave energy cut (int &amp; rim)</strong></td></tr>"
        "</tbody></table></div>\n"
        "</div>\n"
        + report_cta
        + "</section>"
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
        + kpi_card("Online In-Loop", str(counts.get("online_calib", 0)), "Live OG, MOPT & wind")
        + kpi_card("RT Loop Operation", str(counts.get("loop_operation", 0)), "Control & predictive filters")
        + "</div>\n"
        '<div class="hero-actions">'
        '<a class="btn" href="#algorithm-summary">1&ndash;2 Page Options Summary &amp; Rationale</a>'
        '<a class="btn btn-secondary" href="../predictive-control/index.html">Predictive Control Guide</a>'
        '<a class="btn btn-secondary" href="#dependency-graph">Interactive Options Map</a>'
        '<a class="btn btn-secondary" href="#architecture-synthesis">Rules &amp; Benchmarks</a>'
        '<a class="btn btn-secondary" href="#algorithms-root">Full Catalog &amp; 2D Matrix</a>'
        '<a class="btn btn-secondary" href="../reference/index.html">CLI / FPS Reference</a>'
        "</div>\n"
        "</section>"
    )

    role_opts = [f'<option value="all">All Roles ({counts["total"]})</option>']
    for rkey in ALGO_ROLE_ORDER:
        rcnt = counts.get(rkey, 0)
        if rcnt:
            role_opts.append(
                f'<option value="{rkey}">'
                f'{html.escape(ALGO_ROLES[rkey]["label"], quote=False)} ({rcnt})</option>'
            )

    stage_opts = (
        '<option value="all">All Stages</option>'
        '<option value="stg1">Stage 1 (AO3k)</option>'
        '<option value="stg2">Stage 2 (SCExAO)</option>'
        '<option value="stg3">Stage 3 (LLOWFS)</option>'
        '<option value="2stg">2-Stage Coupled</option>'
    )

    trace_opts = '<option value="">None (Show All)</option>' + "".join(
        f'<option value="{c}">{c} — {html.escape(str(by_code[c]["name"]), quote=False)}</option>'
        for c in ("PSOL", "OG/POKE", "2WFS/LIVE", "MOPT", "EOF", "SELFLEARN", "CMODES", "MRDM", "PRESH")
        if c in by_code
    )

    dep_graph_payload = {
        str(e["code"]): {
            "name": str(e["name"]),
            "role": str(e["role"]),
            "stages": list(e.get("stages") or []),
            "stage_req": dict(e.get("stage_req") or {"mode": "none", "stages": []}),
            "req": list(e.get("requires") or []),
            "opt": list(e.get("optional_requires") or []),
            "fb_in": list(e.get("feedback_from") or []),
            "en": list(e.get("enables") or []),
            "en_opt": list(e.get("enables_optional") or []),
            "fb_out": list(e.get("feeds_runtime") or []),
            "excl": list(e.get("excludes_codes") or []),
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
        '<div class="filter-actions-row">\n'
        '<div class="toolbar-group">'
        '<label class="filter-inline-label" for="algo-role-select">Role:</label>'
        '<select class="algo-toolbar-select" id="algo-role-select" aria-label="Filter by Role">'
        f'{"".join(role_opts)}</select>'
        '<label class="filter-inline-label" for="algo-stage-select">Stage:</label>'
        '<select class="algo-toolbar-select" id="algo-stage-select" aria-label="Filter by Stage">'
        f"{stage_opts}</select>"
        '<label class="filter-inline-label" for="algo-trace-select">Trace Chain:</label>'
        '<select class="algo-toolbar-select" id="algo-trace-select" aria-label="Trace Dependency Chain">'
        f"{trace_opts}</select></div>\n"
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
        "<h2>Interactive AO Loop Algorithmic Options Map</h2>\n"
        '<p class="muted">Each box is an algorithmic choice for running an AO loop (not tied '
        "1-to-1 to compute units). Configure active stages and simulation setup at the top, "
        "choose from <strong>Calibration</strong> (Offline &amp; Online) and the <strong>3-Layer "
        "Real-Time Control Architecture</strong> (Core Control &rarr; Inner Mode Rotation &rarr; "
        "DM Actuation) left-to-right, and pick <strong>Diagnostics &amp; Telemetry</strong> below. "
        "Unselectable choices are greyed out (e.g. Self-Learning requires Block-EOF; never "
        "standalone); mutually exclusive choices switch each other off.</p>\n"
        + _render_pipeline_board(algo_catalog)
        + "\n</section>"
    )

    summary_section = _render_executive_summary(hierarchy, algo_catalog)
    synth_section = _render_architecture_synthesis(hierarchy, algo_catalog)

    body_html = "\n\n".join(
        [hero_html, _render_role_legend(), summary_section, graph_section, synth_section, explorer_html]
    )
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

    pc_guide_btn = (
        '<a class="btn" href="../../predictive-control/index.html">Predictive Control Guide &rarr;</a>'
        if code in ("PF/AR", "EOF", "SELFLEARN", "PSOL", "WHITE", "MRDM", "WIND")
        else ""
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
        f"{pc_guide_btn}"
        '<a class="btn btn-secondary" href="../index.html">&larr; All Algorithms Table</a>'
        '<a class="btn btn-secondary" href="../index.html#matrix">2D Dependency Matrix</a>'
        '<a class="btn btn-secondary" href="../../reference/index.html">Options Reference</a>'
        "</div>\n"
        "</section>"
    )

    def _fmt_inline_code(text: str) -> str:
        esc = html.escape(text, quote=False)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)

    detail_paras = "".join(f"<p>{_fmt_inline_code(p)}</p>" for p in details)
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
