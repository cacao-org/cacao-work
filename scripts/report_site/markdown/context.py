#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Link-resolution context for Markdown-to-HTML rendering."""

from __future__ import annotations

from pathlib import Path


class RenderContext:
    """Shared context for resolving local links and tracking referenced images."""

    def __init__(
        self,
        out_slug_dir: Path,
        has_compute_report: bool,
        *,
        is_simulation: bool = True,
        known_siblings: set[str] | None = None,
    ) -> None:
        self.out_slug_dir = out_slug_dir.resolve()
        self.has_compute_report = has_compute_report
        self.is_simulation = is_simulation
        self.known_siblings = known_siblings or set()
        self.referenced_images: set[str] = set()
        self.has_mermaid = False

    def resolve_local_url(self, raw_url: str) -> tuple[str, bool, bool]:
        """Resolve URL -> (resolved_url, is_external, is_available_locally)."""
        url = raw_url.strip()
        if url.startswith(("http://", "https://", "mailto:", "#")):
            return url, not url.startswith("#"), True
        if url.startswith("./"):
            url = url[2:]
        path_part, sep, frag = url.partition("#")
        mapped = path_part
        if path_part == "REPORT.md":
            mapped = "optical.html" if self.is_simulation else "index.html"
        elif path_part == "COMPUTE_REPORT.md" and self.has_compute_report:
            mapped = "runtime.html"
        final_url = f"{mapped}{sep}{frag}" if sep else mapped
        sim_pages = {
            "index.html",
            "config.html",
            "optical.html",
            "runtime.html",
            "how_to_run.html",
            "compute_report.html",
            "compute.html",
        }
        if mapped in sim_pages:
            if mapped in ("runtime.html", "compute_report.html", "compute.html"):
                return final_url, False, self.has_compute_report
            if not self.is_simulation and mapped != "index.html":
                return final_url, False, False
            return final_url, False, True

        cand = (self.out_slug_dir / mapped).resolve()
        try:
            cand.relative_to(self.out_slug_dir)
            return final_url, False, cand.is_file()
        except ValueError:
            public_root = self.out_slug_dir.parent.resolve()
            try:
                rel = cand.relative_to(public_root)
                if cand.is_file():
                    return final_url, False, True
                parts = rel.parts
                if (
                    len(parts) == 2
                    and parts[1] in sim_pages
                    and (
                        parts[0] in self.known_siblings
                        or (public_root / parts[0]).is_dir()
                    )
                ):
                    return final_url, False, True
                return final_url, False, False
            except ValueError:
                return final_url, False, False
