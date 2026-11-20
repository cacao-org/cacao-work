#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Build a static Firebase Hosting knowledge repository from AO simulation & tech reports."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from report_site import ASSET_EXTS  # noqa: E402
from report_site.front_page import (  # noqa: E402
    build_front_page_html,
    refresh_cross_links,
)
from report_site.markdown_render import (  # noqa: E402
    RenderContext,
    convert_markdown_to_html,
    split_simulation_markdown,
)
from report_site.metrics import (  # noqa: E402
    build_compute_unit_catalog,
    extract_metrics_highlights,
    extract_optical_explorer_data,
    extract_referenced_simulations,
    extract_runtime_explorer_data,
    extract_runtime_summary,
    is_tech_report_meta,
    load_json_safe,
    parse_bench_file,
)
from report_site.sim_pages import (  # noqa: E402
    build_extra_figures_section,
    build_sim_config_html,
    build_sim_how_to_run_html,
    build_sim_optical_html,
    build_sim_overview_html,
    build_sim_runtime_html,
    build_tech_report_html,
    build_telemetry_files_section,
)


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


def _find_bench_path(out_slug_dir: Path) -> Path | None:
    cand = out_slug_dir / "ao3k_scexao.bench"
    if cand.is_file():
        return cand
    others = [p for p in sorted(out_slug_dir.glob("*.bench")) if p.name != "csim_active.bench"]
    return others[0] if others else None


def write_root_indices_and_firebase(
    site_dir: Path,
    project_id: str | None,
    site_id: str | None,
) -> None:
    """Build Front Page at public/index.html & reports.html, refresh links, and firebase.json."""
    public_dir = site_dir / "public"
    metas: list[dict[str, object]] = []
    for meta_path in sorted(public_dir.glob("*/report_meta.json")):
        try:
            metas.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue

    refresh_cross_links(public_dir, metas)
    front_html = build_front_page_html(metas)
    (public_dir / "reports.html").write_text(front_html, encoding="utf-8")
    (public_dir / "index.html").write_text(front_html, encoding="utf-8")

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
                "source": "**/*.@(html|json|csv|tsv|txt|dat|bench)",
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

    study_meta = load_json_safe(out_slug_dir / "study_meta.json")
    is_tech = is_tech_report_meta(study_meta)
    public_dir = site_dir / "public"
    known_siblings = {
        p.name for p in public_dir.iterdir() if p.is_dir() and (p / "report_meta.json").is_file()
    }

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
        tech_html = build_tech_report_html(
            slug=slug,
            title=report_title,
            study_meta=study_meta,
            report_body_html=report_body,
            extra_figs_html=extra_figs_html,
            data_files_html=data_files_html,
            has_repro_section=has_repro,
            has_mermaid=ctx.has_mermaid,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "index.html").write_text(tech_html, encoding="utf-8")

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
        for skey in ("nav_label", "button_label", "summary", "topic"):
            if study_meta.get(skey):
                meta[skey] = str(study_meta[skey])
        if isinstance(study_meta.get("cacao_features"), list):
            meta["cacao_features"] = [str(f) for f in study_meta["cacao_features"]]
        if isinstance(study_meta.get("reproducibility"), dict):
            meta["reproducibility"] = study_meta["reproducibility"]
    else:
        sections = split_simulation_markdown(md_text)
        badges, repro_dict, cmp_dict, params_dict, metrics_data = extract_metrics_highlights(
            out_slug_dir
        )
        bench_path = _find_bench_path(out_slug_dir)
        bench_sections = parse_bench_file(bench_path)
        explorer_data = extract_optical_explorer_data(out_slug_dir, metrics_data)
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

        overview_html = build_sim_overview_html(
            slug=slug,
            title=report_title,
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
            optical_md=sections["optical"],
            explorer_data=explorer_data,
            staged_files=staged_files,
            ctx=ctx,
            has_compute_report=has_compute,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "optical.html").write_text(optical_html, encoding="utf-8")

        runtime_html = build_sim_runtime_html(
            slug=slug,
            title=report_title,
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build static HTML knowledge repository from AO report directories."
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Path to simulation/tech-report output directory containing REPORT.md",
    )
    parser.add_argument(
        "--rebuild-all",
        type=Path,
        default=None,
        help="Rebuild all staged slugs in --site-dir from this _work directory",
    )
    parser.add_argument(
        "--site-dir",
        default=Path("_work/_web_site"),
        type=Path,
        help="Firebase Hosting staging directory (default: _work/_web_site)",
    )
    parser.add_argument(
        "--slug",
        default="",
        help="Target subpath under <site-dir>/public/<slug>/ (default: basename of --report-dir)",
    )
    parser.add_argument("--project", default="", help="Optional Firebase project ID")
    parser.add_argument("--site-id", default="", help="Optional Firebase Hosting site ID")
    parser.add_argument(
        "--include-fits",
        action="store_true",
        help="Also stage .fits files into the static web directory",
    )
    args = parser.parse_args(argv)
    if args.report_dir is None and args.rebuild_all is None:
        parser.error("Either --report-dir or --rebuild-all is required")
    return args


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    if args.rebuild_all is not None:
        metas = rebuild_all_published(
            work_root=args.rebuild_all,
            site_dir=args.site_dir,
            project_id=args.project or None,
            site_id=args.site_id or None,
            include_fits=args.include_fits,
        )
        print(
            f"[build-ao-web-report] Rebuilt {len(metas)} reports -> "
            f"{args.site_dir.resolve() / 'public'}"
        )
        return 0

    slug = args.slug or args.report_dir.resolve().name
    meta = build_site(
        report_dir=args.report_dir,
        site_dir=args.site_dir,
        slug=slug,
        project_id=args.project or None,
        site_id=args.site_id or None,
        include_fits=args.include_fits,
    )
    print(
        f"[build-ao-web-report] Built {meta['slug']} ({meta['file_count']} files) -> "
        f"{args.site_dir.resolve() / 'public' / slug}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
