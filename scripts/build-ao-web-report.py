#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CLI wrapper to build a static Firebase Hosting knowledge repository from AO reports."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from report_site.builder import build_site, rebuild_all_published  # noqa: E402


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
