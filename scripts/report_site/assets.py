#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Static CSS/JS asset stager and client-side search-index generator."""

from __future__ import annotations

import html
import json
from pathlib import Path
import shutil

STATIC_DIR = Path(__file__).resolve().parent / "static"

CSS_FILES: tuple[str, ...] = (
    "tokens.css",
    "layout.css",
    "nav.css",
    "components.css",
    "tables.css",
    "explorers.css",
)

COMMON_JS_FILES: tuple[str, ...] = (
    "common.js",
    "nav.js",
    "search-index.js",
)


def stage_site_assets(public_dir: Path) -> None:
    """Copy static CSS and JS files into <public_dir>/assets/{css,js}/."""
    css_dst = public_dir / "assets" / "css"
    js_dst = public_dir / "assets" / "js"
    css_dst.mkdir(parents=True, exist_ok=True)
    js_dst.mkdir(parents=True, exist_ok=True)

    for fname in CSS_FILES:
        src = STATIC_DIR / "css" / fname
        if src.is_file():
            shutil.copy2(src, css_dst / fname)

    js_src_dir = STATIC_DIR / "js"
    if js_src_dir.is_dir():
        for src in sorted(js_src_dir.glob("*.js")):
            shutil.copy2(src, js_dst / src.name)


def write_search_index_js(
    public_dir: Path,
    hierarchy: dict[str, object],
    *,
    options_catalog: dict[str, object] | None = None,
) -> None:
    """Generate <public_dir>/assets/js/search-index.js for file:// and HTTP search."""
    entries: list[dict[str, str]] = [
        {
            "title": "Home — AO Knowledge Repository",
            "path": "index.html",
            "kind": "Hub",
            "domain": "All Domains",
            "summary": "Executive overview, AO research domains, and featured technical reports",
        },
        {
            "title": "All Simulation Suites Catalog",
            "path": "simulations/index.html",
            "kind": "Catalog",
            "domain": "All Domains",
            "summary": "Filterable and comparable simulation matrix across all runs",
        },
        {
            "title": "Simulator Options & Parameter Reference",
            "path": "reference/index.html",
            "kind": "Reference",
            "domain": "Options Reference",
            "summary": (
                "Complete .bench optical keys, cacaosim & milkatmturb FPS compute unit "
                "parameters, runner CLI flags, and CACAO_* environment variables"
            ),
        },
        {
            "title": "Open-Source Stack & Reproduction Guide",
            "path": "stack/index.html",
            "kind": "Guide",
            "domain": "Stack & Guides",
            "summary": "9 GitHub repositories, build-all.sh, CLI reproduction, and adding reports",
        },
    ]

    for dom in hierarchy.get("domains") or []:
        if not isinstance(dom, dict):
            continue
        did = str(dom["id"])
        dtitle = str(dom["title"])
        entries.append(
            {
                "title": dtitle,
                "path": f"topics/{did}/index.html",
                "kind": "Topic Hub",
                "domain": dtitle,
                "summary": str(dom.get("description") or ""),
            }
        )

    domain_map = hierarchy.get("domain_map") or {}
    domain_by_slug = hierarchy.get("domain_by_slug") or {}

    for tm in hierarchy.get("study_metas") or []:
        if not isinstance(tm, dict) or not tm.get("slug"):
            continue
        slug = str(tm["slug"])
        did = str(domain_by_slug.get(slug, ""))
        dtitle = str((domain_map.get(did) or {}).get("title") or did)
        entries.append(
            {
                "title": str(tm.get("title") or slug),
                "path": f"{slug}/index.html",
                "kind": "Tech Report",
                "domain": dtitle,
                "summary": str(tm.get("summary") or ""),
            }
        )

    for rm in hierarchy.get("run_metas") or []:
        if not isinstance(rm, dict) or not rm.get("slug"):
            continue
        slug = str(rm["slug"])
        did = str(domain_by_slug.get(slug, ""))
        dtitle = str((domain_map.get(did) or {}).get("title") or did)
        params = rm.get("parameters") if isinstance(rm.get("parameters"), dict) else {}
        ctrl = str(params.get("control_law") or "")
        lo = str(params.get("llowfs") or "")
        sum_parts = [p for p in (ctrl, f"LLOWFS {lo}" if lo else "") if p]
        summary = " | ".join(sum_parts)
        entries.append(
            {
                "title": slug,
                "path": f"{slug}/index.html",
                "kind": "Simulation",
                "domain": dtitle,
                "summary": summary or str(rm.get("title") or ""),
            }
        )
        for sub_file, sub_lbl in (
            ("config.html", "Configuration"),
            ("optical.html", "Optical Performance"),
            ("runtime.html", "Runtime Performance"),
            ("how_to_run.html", "How to Run It"),
        ):
            entries.append(
                {
                    "title": f"{slug} — {sub_lbl}",
                    "path": f"{slug}/{sub_file}",
                    "kind": f"Sim · {sub_lbl}",
                    "domain": dtitle,
                    "summary": summary,
                }
            )

    if isinstance(options_catalog, dict):
        for bo in options_catalog.get("bench_options") or []:
            if not isinstance(bo, dict):
                continue
            sec = str(bo.get("section") or "")
            key = str(bo.get("key") or "")
            al = str(bo.get("aliases") or "")
            anc = str(bo.get("anchor") or "")
            desc = str(bo.get("description") or "")
            summary = f"[{sec}] {desc}" + (f" (aliases: {al})" if al else "")
            entries.append(
                {
                    "title": f"[{sec}] {key}",
                    "path": f"reference/index.html#{anc}",
                    "kind": ".bench Option",
                    "domain": "Options Reference",
                    "summary": summary,
                }
            )
        for u in options_catalog.get("fps_units") or []:
            if not isinstance(u, dict):
                continue
            pkg = str(u.get("package") or "")
            uname = str(u.get("unit") or "")
            uanc = str(u.get("anchor") or "")
            entries.append(
                {
                    "title": f"{pkg}.{uname} ({u.get('binary', '')})",
                    "path": f"reference/index.html#{uanc}",
                    "kind": "FPS Unit",
                    "domain": "Options Reference",
                    "summary": str(u.get("description") or ""),
                }
            )
            for p in u.get("params") or []:
                if not isinstance(p, dict):
                    continue
                kw = str(p.get("keyword") or "")
                panc = str(p.get("anchor") or "")
                entries.append(
                    {
                        "title": f"{uname}{kw}",
                        "path": f"reference/index.html#{panc}",
                        "kind": f"FPS · {pkg}",
                        "domain": "Options Reference",
                        "summary": str(p.get("description") or ""),
                    }
                )
        for group_key, kind_lbl in (
            ("runner_cli", "Runner CLI"),
            ("env_vars", "CACAO_* Env"),
            ("cacaosim_cli", "cacaosim CLI"),
        ):
            for co in options_catalog.get(group_key) or []:
                if not isinstance(co, dict):
                    continue
                flag = str(co.get("flag") or "")
                tool = str(co.get("tool") or "")
                anc = str(co.get("anchor") or "")
                entries.append(
                    {
                        "title": f"{flag} ({tool})",
                        "path": f"reference/index.html#{anc}",
                        "kind": kind_lbl,
                        "domain": "Options Reference",
                        "summary": str(co.get("description") or ""),
                    }
                )

    js_dir = public_dir / "assets" / "js"
    js_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(entries, separators=(",", ":")).replace("</", "<\\/")
    (js_dir / "search-index.js").write_text(
        f"window.CACAO_SEARCH_INDEX={payload};\n", encoding="utf-8"
    )


def render_css_tags(rel_root: str) -> str:
    """Return <link rel='stylesheet'> tags using relative paths from rel_root."""
    base = rel_root.rstrip("/") or "."
    return "\n".join(
        f'<link rel="stylesheet" href="{html.escape(base, quote=True)}/assets/css/{f}">'
        for f in CSS_FILES
    )


def render_js_tags(rel_root: str, page_scripts: tuple[str, ...] = ()) -> str:
    """Return <script src='...'> tags for common and page-specific scripts."""
    base = rel_root.rstrip("/") or "."
    all_scripts = list(COMMON_JS_FILES)
    for sc in page_scripts:
        if sc and sc not in all_scripts:
            all_scripts.append(sc)
    return "\n".join(
        f'<script src="{html.escape(base, quote=True)}/assets/js/{s}"></script>'
        for s in all_scripts
    )
