#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared HTML fragment helpers, category badges, KPI cards, and asset tables."""

from __future__ import annotations

import html
import json
from pathlib import Path

from ..constants import (
    COMPUTE_CATEGORIES,
    COMPUTE_CATEGORY_ORDER,
    DATA_EXTS,
    DEFAULT_REPOS,
    IMAGE_EXTS,
    VIDEO_EXTS,
    friendly_figure_caption,
)
from ..extractors.common import human_bytes
from ..markdown.context import RenderContext
from ..markdown.parser import render_figure_block


def safe_json_embed(obj: object) -> str:
    """Serialize JSON safely for inline <script type='application/json'> blocks."""
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def mermaid_tag(has_mermaid: bool) -> str:
    """Return the Mermaid ESM loader script when a page contains Mermaid diagrams."""
    if not has_mermaid:
        return ""
    return (
        '\n<script type="module">\n'
        "import mermaid from "
        '"https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";\n'
        "mermaid.initialize({ startOnLoad: true, theme: 'default' });\n"
        "</script>"
    )


def render_cat_badge(cat_key: str, *, short: bool = False) -> str:
    """Render a consistently color-coded pill badge for one of the 4 compute categories."""
    info = COMPUTE_CATEGORIES.get(cat_key) or COMPUTE_CATEGORIES["loop_operation"]
    key = info["key"]
    lbl = info["short"] if short else info["label"]
    return (
        f'<span class="cat-badge cat-{key}">'
        f'<span class="cat-dot"></span>{html.escape(lbl, quote=False)}</span>'
    )


def render_domain_badge(
    domain_id: str,
    domain_map: dict[str, dict[str, object]],
    *,
    rel_root: str = ".",
    linked: bool = True,
) -> str:
    """Render a domain pill badge optionally linked to its /topics/<domain>/ hub."""
    dom = domain_map.get(domain_id) or {}
    did = str(dom.get("id") or domain_id or "bench-runtime")
    lbl = str(dom.get("short_title") or dom.get("title") or did)
    cls = f"domain-badge domain-{html.escape(did, quote=True)}"
    if linked:
        base = rel_root.rstrip("/") or "."
        href = html.escape(f"{base}/topics/{did}/index.html", quote=True)
        return f'<a class="{cls}" href="{href}">{html.escape(lbl, quote=False)}</a>'
    return f'<span class="{cls}">{html.escape(lbl, quote=False)}</span>'


def render_section_badges(cats: list[str] | tuple[str, ...]) -> str:
    """Render inline category badges beside a section heading."""
    pills = "".join(render_cat_badge(c) for c in cats)
    return f'<small class="section-cat-badges">{pills}</small>'


def render_cat_group_row(cat_key: str, colspan: int, count: int) -> str:
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
    """Render a shared color-coded legend for the 4 canonical compute categories."""
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


def mermaid_cat_classdefs() -> str:
    """Return Mermaid classDef lines matching the 4 canonical compute-category colors."""
    return "\n".join(
        f'    classDef {COMPUTE_CATEGORIES[k]["mermaid_class"]} '
        f'{COMPUTE_CATEGORIES[k]["mermaid_def"]}'
        for k in COMPUTE_CATEGORY_ORDER
    )


def kpi_card(label: str, value: str, sub: str = "") -> str:
    """Render a compact KPI metric card."""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{html.escape(label, quote=False)}</div>'
        f'<div class="kpi-value">{value}</div>'
        f"{sub_html}</div>"
    )


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


def merge_repo_list(
    latest_repro: dict[str, object] | None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    """Merge pinned repository SHAs from latest reproducibility metadata with defaults."""
    repo_by_name: dict[str, dict[str, str]] = {r["name"]: dict(r) for r in DEFAULT_REPOS}
    repo_list: list[dict[str, str]] = [dict(r) for r in DEFAULT_REPOS]
    if latest_repro and isinstance(latest_repro.get("repositories"), list):
        merged_list: list[dict[str, str]] = []
        for item in latest_repro["repositories"]:
            if not isinstance(item, dict) or "name" not in item:
                continue
            rname = str(item["name"])
            base = dict(repo_by_name.get(rname, {}))
            for k in ("name", "url", "branch", "commit", "short_commit", "role"):
                if item.get(k):
                    base[k] = str(item[k])
            repo_by_name[rname] = base
            merged_list.append(base)
        if merged_list:
            repo_list = merged_list
    return repo_list, repo_by_name
