#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Static Firebase Hosting knowledge-repository builder and asset stager."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from .assets import stage_site_assets, write_search_index_js
from .constants import ASSET_EXTS
from .cross_links import refresh_cross_links
from .extractors import (
    build_compute_unit_catalog,
    extract_eof_pf_data,
    extract_metrics_highlights,
    extract_optical_explorer_data,
    extract_referenced_simulations,
    extract_runtime_explorer_data,
    extract_runtime_summary,
    find_bench_path,
    is_tech_report_meta,
    load_json_safe,
    parse_bench_file,
)
from .markdown import RenderContext, convert_markdown_to_html, split_simulation_markdown
from .pages import (
    build_extra_figures_section,
    build_front_page_html,
    build_sim_config_html,
    build_sim_how_to_run_html,
    build_sim_optical_html,
    build_sim_overview_html,
    build_sim_runtime_html,
    build_simulations_catalog_html,
    build_stack_guide_html,
    build_tech_report_html,
    build_telemetry_files_section,
    build_topic_hub_html,
)
from .pages.fragments import safe_json_embed
from .taxonomy import build_site_hierarchy, classify_report, load_taxonomy


def stage_assets(
    report_dir: Path,
    out_slug_dir: Path,
    include_fits: bool,
) -> list[Path]:
    """Recreate <site-dir>/public/<slug>/ and copy eligible report artifacts."""
    if out_slug_dir.exists():
        shutil.rmtree(out_slug_dir)
    out_slug_dir.mkdir(parents=True, exist_ok=True)
    allowed = set(ASSET_EXTS)
    if include_fits:
        allowed.add(".fits")
    staged: list[Path] = []
    for item in sorted(report_dir.iterdir(), key=lambda p: p.name.lower()):
        if not item.is_file() or item.name == "report_meta.json":
            continue
        if item.suffix.lower() in allowed:
            dest = out_slug_dir / item.name
            shutil.copy2(item, dest)
            staged.append(dest)
    return staged


def _load_staged_metas(public_dir: Path) -> list[dict[str, object]]:
    metas: list[dict[str, object]] = []
    if not public_dir.is_dir():
        return metas
    for meta_path in sorted(public_dir.glob("*/report_meta.json")):
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metas.append(loaded)
        except (OSError, json.JSONDecodeError):
            continue
    return metas


def write_root_indices_and_firebase(
    site_dir: Path,
    project_id: str | None,
    site_id: str | None,
) -> None:
    """Build Hub, Topic Hubs, Simulations Catalog, Stack Guide, Assets, & firebase.json."""
    public_dir = site_dir / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy()
    metas = _load_staged_metas(public_dir)
    hierarchy = build_site_hierarchy(metas, taxonomy)

    stage_site_assets(public_dir)
    write_search_index_js(public_dir, hierarchy)

    front_html = build_front_page_html(hierarchy)
    (public_dir / "reports.html").write_text(front_html, encoding="utf-8")
    (public_dir / "index.html").write_text(front_html, encoding="utf-8")

    sims_dir = public_dir / "simulations"
    sims_dir.mkdir(parents=True, exist_ok=True)
    (sims_dir / "index.html").write_text(
        build_simulations_catalog_html(hierarchy), encoding="utf-8"
    )

    stack_dir = public_dir / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    (stack_dir / "index.html").write_text(
        build_stack_guide_html(hierarchy), encoding="utf-8"
    )

    topics_dir = public_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    valid_dom_ids = {str(d["id"]) for d in taxonomy}
    for old in list(topics_dir.iterdir()):
        if old.is_dir() and old.name not in valid_dom_ids:
            shutil.rmtree(old)
    for dom in taxonomy:
        did = str(dom["id"])
        ddir = topics_dir / did
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / "index.html").write_text(
            build_topic_hub_html(did, hierarchy), encoding="utf-8"
        )

    refresh_cross_links(public_dir, hierarchy)

    hosting_cfg: dict[str, object] = {
        "public": "public",
        "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
        "cleanUrls": False,
        "headers": [
            {
                "source": "**/*.@(png|jpg|jpeg|svg|webp|mp4|webm)",
                "headers": [{"key": "Cache-Control", "value": "no-cache"}],
            },
            {
                "source": "**/*.@(html|css|js|json|csv|tsv|txt|dat|bench)",
                "headers": [{"key": "Cache-Control", "value": "no-cache"}],
            },
        ],
    }
    if site_id:
        hosting_cfg["site"] = site_id

    (site_dir / "firebase.json").write_text(
        json.dumps({"hosting": hosting_cfg}, indent=2) + "\n", encoding="utf-8"
    )
    if project_id:
        (site_dir / ".firebaserc").write_text(
            json.dumps({"projects": {"default": project_id}}, indent=2) + "\n",
            encoding="utf-8",
        )


def build_site(
    report_dir: Path,
    site_dir: Path,
    slug: str,
    project_id: str | None = None,
    site_id: str | None = None,
    include_fits: bool = False,
    *,
    skip_root_refresh: bool = False,
) -> dict[str, object]:
    """Stage assets and build static web pages for report_dir into site_dir."""
    report_dir = report_dir.resolve()
    site_dir = site_dir.resolve()
    report_md_path = report_dir / "REPORT.md"
    if not report_md_path.is_file():
        raise FileNotFoundError(f"Missing REPORT.md in {report_dir}")

    md_text = report_md_path.read_text(encoding="utf-8")
    compute_md_path = report_dir / "COMPUTE_REPORT.md"
    has_compute = compute_md_path.is_file()
    out_slug_dir = site_dir / "public" / slug
    staged_files = stage_assets(report_dir, out_slug_dir, include_fits)
    updated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    taxonomy = load_taxonomy()
    study_meta = load_json_safe(out_slug_dir / "study_meta.json")
    is_tech = is_tech_report_meta(study_meta)
    public_dir = site_dir / "public"
    existing_metas = [
        m for m in _load_staged_metas(public_dir) if str(m.get("slug", "")) != slug
    ]
    known_siblings = {str(m.get("slug", "")) for m in existing_metas if m.get("slug")}

    if is_tech:
        ref_sims = extract_referenced_simulations(md_text, study_meta)
        ctx = RenderContext(
            out_slug_dir,
            has_compute_report=False,
            is_simulation=False,
            known_siblings=known_siblings | set(ref_sims),
        )
        report_body, det_rtitle = convert_markdown_to_html(md_text, ctx)
        report_title = det_rtitle or f"Technical Report ({slug})"
        has_repro = 'id="reproducibility-github-provenance"' in report_body
        extra_figs_html = build_extra_figures_section(staged_files, ctx)
        data_files_html = build_telemetry_files_section(staged_files)

        all_slug_files = [p for p in out_slug_dir.iterdir() if p.is_file()]
        meta: dict[str, object] = {
            "title": report_title,
            "slug": slug,
            "report_type": "tech_report",
            "has_compute_report": False,
            "has_repro_section": has_repro,
            "badges": [str(b) for b in (study_meta.get("badges") or [])]
            if isinstance(study_meta.get("badges"), list)
            else [],
            "referenced_simulations": ref_sims,
            "updated_utc": updated_utc,
            "total_bytes": sum(p.stat().st_size for p in all_slug_files),
            "file_count": len(all_slug_files) + 1,
        }
        for skey in ("nav_label", "button_label", "summary", "topic", "domain", "subtopic"):
            if study_meta.get(skey):
                meta[skey] = str(study_meta[skey])
        if isinstance(study_meta.get("cacao_features"), list):
            meta["cacao_features"] = [str(f) for f in study_meta["cacao_features"]]
        if isinstance(study_meta.get("reproducibility"), dict):
            meta["reproducibility"] = study_meta["reproducibility"]

        dom_id, sub_id = classify_report(meta, taxonomy)
        meta["domain"] = dom_id
        meta["subtopic"] = sub_id
        hierarchy = build_site_hierarchy([*existing_metas, meta], taxonomy)

        tech_html = build_tech_report_html(
            slug=slug,
            title=report_title,
            domain_id=dom_id,
            study_meta=study_meta,
            hierarchy=hierarchy,
            report_body_html=report_body,
            extra_figs_html=extra_figs_html,
            data_files_html=data_files_html,
            has_repro_section=has_repro,
            has_mermaid=ctx.has_mermaid,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "index.html").write_text(tech_html, encoding="utf-8")
    else:
        sections = split_simulation_markdown(md_text)
        badges, repro_dict, cmp_dict, params_dict, metrics_data = extract_metrics_highlights(
            out_slug_dir
        )
        bench_path = find_bench_path(out_slug_dir)
        bench_sections = parse_bench_file(bench_path)
        explorer_data = extract_optical_explorer_data(out_slug_dir, metrics_data)
        eof_pf_data = extract_eof_pf_data(report_dir, metrics_data)
        if eof_pf_data is not None:
            (out_slug_dir / "eof_pf_data.js").write_text(
                f"window.CACAO_EOF_PF_DATA={safe_json_embed(eof_pf_data)};\n",
                encoding="utf-8",
            )
        runtime_data = extract_runtime_explorer_data(out_slug_dir)
        runtime_summary = extract_runtime_summary(runtime_data)
        units = build_compute_unit_catalog(
            metrics_data, bench_sections, runtime_data, params_dict
        )

        ctx = RenderContext(
            out_slug_dir,
            has_compute_report=has_compute,
            is_simulation=True,
            known_siblings=known_siblings,
        )
        preamble_html, _ = (
            convert_markdown_to_html(sections["preamble"], ctx, {})
            if sections["preamble"]
            else ("", "")
        )
        report_title = sections["title"] or f"AO Simulation Report ({slug})"

        all_slug_files = [p for p in out_slug_dir.iterdir() if p.is_file()]
        meta = {
            "title": report_title,
            "slug": slug,
            "report_type": "simulation",
            "has_compute_report": has_compute,
            "has_repro_section": True,
            "badges": badges,
            "updated_utc": updated_utc,
            "total_bytes": sum(p.stat().st_size for p in all_slug_files),
            "file_count": len(all_slug_files) + 1,
        }
        if repro_dict is not None:
            meta["reproducibility"] = repro_dict
        if cmp_dict is not None:
            meta["comparison"] = cmp_dict
        if params_dict:
            meta["parameters"] = params_dict
        if runtime_summary:
            meta["runtime_summary"] = runtime_summary
        for skey in ("domain", "subtopic"):
            if study_meta.get(skey):
                meta[skey] = str(study_meta[skey])

        dom_id, sub_id = classify_report(meta, taxonomy)
        meta["domain"] = dom_id
        meta["subtopic"] = sub_id
        hierarchy = build_site_hierarchy([*existing_metas, meta], taxonomy)

        overview_html = build_sim_overview_html(
            slug=slug,
            title=report_title,
            domain_id=dom_id,
            hierarchy=hierarchy,
            preamble_html=preamble_html,
            badges=badges,
            params=params_dict,
            cmp_dict=cmp_dict,
            runtime_summary=runtime_summary,
            metrics_data=metrics_data,
            out_slug_dir=out_slug_dir,
            staged_files=staged_files,
            has_compute_report=has_compute,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "index.html").write_text(overview_html, encoding="utf-8")

        config_html = build_sim_config_html(
            slug=slug,
            title=report_title,
            domain_id=dom_id,
            hierarchy=hierarchy,
            config_md=sections["config"],
            gui_md=sections["gui_md"],
            metrics_data=metrics_data,
            bench_sections=bench_sections,
            bench_path=bench_path,
            out_slug_dir=out_slug_dir,
            ctx=ctx,
            has_compute_report=has_compute,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "config.html").write_text(config_html, encoding="utf-8")

        optical_html = build_sim_optical_html(
            slug=slug,
            title=report_title,
            domain_id=dom_id,
            hierarchy=hierarchy,
            optical_md=sections["optical"],
            explorer_data=explorer_data,
            eof_pf_data=eof_pf_data,
            staged_files=staged_files,
            ctx=ctx,
            has_compute_report=has_compute,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "optical.html").write_text(optical_html, encoding="utf-8")

        runtime_html = build_sim_runtime_html(
            slug=slug,
            title=report_title,
            domain_id=dom_id,
            hierarchy=hierarchy,
            compute_md_path=compute_md_path,
            runtime_data=runtime_data,
            ctx=ctx,
            has_compute_report=has_compute,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "runtime.html").write_text(runtime_html, encoding="utf-8")
        if has_compute:
            (out_slug_dir / "compute_report.html").write_text(runtime_html, encoding="utf-8")
            (out_slug_dir / "compute.html").write_text(runtime_html, encoding="utf-8")

        how_to_run_html = build_sim_how_to_run_html(
            slug=slug,
            title=report_title,
            domain_id=dom_id,
            hierarchy=hierarchy,
            params=params_dict,
            metrics_data=metrics_data,
            units=units,
            repro_md=sections["repro"],
            ctx=ctx,
            has_compute_report=has_compute,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "how_to_run.html").write_text(how_to_run_html, encoding="utf-8")

        all_slug_files = [p for p in out_slug_dir.iterdir() if p.is_file()]
        meta["total_bytes"] = sum(p.stat().st_size for p in all_slug_files)
        meta["file_count"] = len(all_slug_files) + 1

    (out_slug_dir / "report_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    if not skip_root_refresh:
        write_root_indices_and_firebase(site_dir, project_id, site_id)
    return meta


def rebuild_all_published(
    work_root: Path,
    site_dir: Path,
    project_id: str | None = None,
    site_id: str | None = None,
    include_fits: bool = False,
) -> list[dict[str, object]]:
    """Rebuild every existing published slug in site_dir whose source dir is in work_root."""
    public_dir = site_dir.resolve() / "public"
    if not public_dir.is_dir():
        raise FileNotFoundError(f"Missing public directory: {public_dir}")
    slugs: list[str] = []
    for mpath in sorted(public_dir.glob("*/report_meta.json")):
        slug = mpath.parent.name
        src_dir = work_root / slug
        if (src_dir / "REPORT.md").is_file():
            slugs.append(slug)
    metas: list[dict[str, object]] = []
    for slug in slugs:
        print(f"[build-ao-web-report] Rebuilding {slug}...")
        metas.append(
            build_site(
                work_root / slug,
                site_dir,
                slug,
                project_id=project_id,
                site_id=site_id,
                include_fits=include_fits,
                skip_root_refresh=True,
            )
        )
    write_root_indices_and_firebase(site_dir, project_id, site_id)
    return metas
