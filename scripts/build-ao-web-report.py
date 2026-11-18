#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Build a static Firebase Hosting website from an AO simulation report directory."""

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import shutil
import sys

ASSET_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".mp4",
    ".webm",
    ".json",
    ".csv",
    ".tsv",
    ".txt",
    ".dat",
    ".bench",
}
DATA_EXTS = {".json", ".csv", ".tsv", ".txt", ".dat", ".fits", ".bench"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
VIDEO_EXTS = {".mp4", ".webm"}

FRIENDLY_FIG_LABELS = {
    "wfs_psf_short_evolution.mp4": (
        "Short-Timescale Polychromatic PyWFS & Speckle PSF Evolution (Video)"
    ),
    "cacaosim_gui_schematic.png": (
        "cacaosim-CTRL 2D Optical Bench Schematic & 32-Bin Polychromatic Spectra (F3:SCHEMATIC)"
    ),
    "cacaosim_gui_builder.png": (
        "cacaosim-CTRL 3-Pane Hardware Configurator & Parameter Inspector (F2:BUILDER)"
    ),
    "cacaosim_gui_tables.png": (
        "cacaosim-CTRL Hardware Mirrors, Sensors & Splitters Summary (F4:TABLES)"
    ),
    "cacaosim_gui_status.png": (
        "cacaosim-CTRL Live Shared-Memory Streams & Active MILK FPS Units (F5:STATUS)"
    ),
    "chromatic_passbands_2x1.png": (
        "Optical Bench 32-Bin Spectra & Polychromatic Sensor Sub-Band Sampling (2x1)"
    ),
    "psf_comparison_2x3.png": "Long-Exposure Polychromatic PSF Comparison (2x3)",
    "psf_radial_profiles.png": "PSF Radial Profiles & Encircled Energy",
    "wf_strehl_timeseries_4x1.png": (
        "RMS Wavefront Error & Strehl Ratio Time Series with Sampled Instants (4x1)"
    ),
    "psf_inst_vis_5x3.png": (
        "Instantaneous Visible 0.75 um (15% BW, 3ch) PSFs at Sampled Instants (5x3)"
    ),
    "psf_inst_nir_5x3.png": (
        "Instantaneous Near-IR H-Band 1.65 um (18% BW, 3ch) PSFs at Sampled Instants (5x3)"
    ),
    "wf_stats_2x3.png": "Wavefront Mean & Temporal Std Dev (2x3)",
    "wf_samples_5x3.png": "Instantaneous Pupil Wavefront OPD Samples at Sampled Instants (5x3)",
    "wfs_samples_5x4.png": (
        "Instantaneous Polychromatic Pyramid WFS Frames & Signals at Sampled Instants (5x4)"
    ),
    "dm_samples_5x4.png": (
        "Instantaneous DM Actuator Commands & Pupil OPD Shapes at Sampled Instants (5x4)"
    ),
    "mlat_latency_1x2.png": "Hardware Latency Measurement (mlat)",
    "modal_gains_1x2.png": "Modal Loop Gain Curves",
    "selfrm_summary_2x4.png": "Modal Self-Response Matrix Summary (selfRM)",
    "compute_timeline_4x1.png": "Compute & Power Timeline (4x1)",
    "compute_process_breakdown_2x2.png": "Per-Process CPU & Latency Breakdown (2x2)",
    "compute_shm_and_calib_2x2.png": "SHM Bandwidth & Calibration Breakdown (2x2)",
}

TABLE_DELIM_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)+\s*\|?\s*$"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_OPEN_RE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")
UL_ITEM_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
OL_ITEM_RE = re.compile(r"^(\s*)\d+\.\s+(.*)$")
HR_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
STANDALONE_IMG_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
INLINE_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
INLINE_LNK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")

CSS_STYLES = """\
:root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-alt: #f1f5f9;
  --text: #0f172a;
  --muted: #475569;
  --border: #e2e8f0;
  --accent: #1d4ed8;
  --accent-soft: #eff6ff;
  --code-bg: #f1f5f9;
  --pre-bg: #0f172a;
  --pre-text: #e2e8f0;
  --shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b1120;
    --surface: #111827;
    --surface-alt: #1e293b;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --border: #334155;
    --accent: #60a5fa;
    --accent-soft: #1e293b;
    --code-bg: #1e293b;
    --pre-bg: #020617;
    --pre-text: #e2e8f0;
    --shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}
.site-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 20;
  box-shadow: var(--shadow);
}
.nav-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0.75rem 1.25rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.brand {
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--text);
  text-decoration: none;
}
.nav-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.nav-links a {
  text-decoration: none;
  color: var(--muted);
  font-size: 0.9rem;
  font-weight: 500;
  padding: 0.35rem 0.75rem;
  border-radius: 6px;
  border: 1px solid transparent;
}
.nav-links a:hover {
  color: var(--accent);
  background: var(--accent-soft);
}
.nav-links a.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--border);
}
main.container {
  max-width: 1180px;
  margin: 1.5rem auto 3rem;
  padding: 2rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
}
@media (max-width: 720px) {
  main.container {
    margin: 0.75rem;
    padding: 1.1rem;
  }
}
h1, h2, h3, h4 {
  line-height: 1.25;
  margin-top: 1.75rem;
  margin-bottom: 0.75rem;
}
h1 {
  margin-top: 0;
  font-size: 1.75rem;
  border-bottom: 2px solid var(--border);
  padding-bottom: 0.5rem;
}
h2 {
  font-size: 1.3rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.3rem;
}
a { color: var(--accent); }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.88em;
  background: var(--code-bg);
  padding: 0.15rem 0.35rem;
  border-radius: 4px;
}
pre {
  background: var(--pre-bg);
  color: var(--pre-text);
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.88rem;
}
pre code {
  background: transparent;
  padding: 0;
  color: inherit;
}
blockquote.callout {
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  border-left: 4px solid var(--accent);
  background: var(--accent-soft);
  border-radius: 0 8px 8px 0;
}
blockquote.callout p { margin: 0.25rem 0; }
.table-wrap {
  overflow-x: auto;
  margin: 1rem 0 1.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
th, td {
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
th {
  background: var(--surface-alt);
  font-weight: 600;
}
tr:last-child td { border-bottom: none; }
tbody tr:hover { background: var(--surface-alt); }
.figure-stack, .figure-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.25rem;
  margin: 1rem 0 1.5rem;
}
figure.report-figure {
  margin: 0;
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-alt);
}
figure.report-figure img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 6px;
  background: #ffffff;
}
figure.report-figure video {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 6px;
  background: #0f172a;
}
figure.report-figure figcaption {
  margin-top: 0.5rem;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--muted);
  text-align: center;
}
.mermaid-wrap {
  overflow-x: auto;
  margin: 1rem 0;
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #ffffff;
}
pre.mermaid {
  background: transparent;
  color: #0f172a;
  margin: 0;
  text-align: center;
}
.muted { color: var(--muted); font-size: 0.9em; }
.site-footer {
  max-width: 1180px;
  margin: 0 auto 2rem;
  padding: 0 1.25rem;
  color: var(--muted);
  font-size: 0.85rem;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
}
.report-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}
.report-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.1rem;
  background: var(--surface-alt);
}
.report-card h3 { margin-top: 0; font-size: 1.1rem; }
.card-links { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 0.75rem; }
.btn {
  display: inline-block;
  padding: 0.35rem 0.75rem;
  border-radius: 6px;
  background: var(--accent);
  color: #ffffff;
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 500;
}
.btn-secondary {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
}
.wrap-cell {
  white-space: normal;
  min-width: 220px;
}
.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.55rem 0;
}
.metric-pill {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 500;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
}
"""

DEFAULT_REPOS: list[dict[str, str]] = [
    {
        "name": "cacao-work",
        "url": "https://github.com/cacao-org/cacao-work",
        "branch": "main",
        "role": (
            "Integration workspace, AO3k+SCExAO bench & runner, pytest suite, "
            "and static web report builder"
        ),
    },
    {
        "name": "cacaosim",
        "url": "https://github.com/cacao-org/cacaosim",
        "branch": "main",
        "role": (
            "GPU-fused & modular polychromatic AO hardware simulator, "
            "multi-rate sub-stepping, TUI, and report generator"
        ),
    },
    {
        "name": "cacao",
        "url": "https://github.com/cacao-org/cacao",
        "branch": "feat/bash-engine",
        "role": (
            "Compute and Control for Adaptive Optics (acquireWFS, mlat, "
            "Hadamard RM, SVD CM, modalfilter)"
        ),
    },
    {
        "name": "milk",
        "url": "https://github.com/milk-org/milk",
        "branch": "feat/bash-engine",
        "role": (
            "Core FPS shared-memory engine, milk-script orchestrator, "
            "streamFITSlog telemetry, and milk-perf-report"
        ),
    },
    {
        "name": "ImageStreamIO",
        "url": "https://github.com/milk-org/ImageStreamIO",
        "branch": "dev",
        "role": "Low-latency POSIX/CUDA shared-memory stream transport (milk submodule)",
    },
    {
        "name": "milk-mltools",
        "url": "https://github.com/milk-org/milk-mltools",
        "branch": "main",
        "role": (
            "C telemetry indexing & sync, @calc JIT extensions, AO loop "
            "optimizer, and polychromatic PSF reconstruction"
        ),
    },
    {
        "name": "AtmosphericTurbulenceSimul",
        "url": "https://github.com/oguyon/AtmosphericTurbulenceSimul",
        "branch": "feat/bash-engine",
        "role": "Multi-layer Maunakea frozen-flow & boiling turbulence generator (milkatmturb)",
    },
    {
        "name": "OpticsMaterials",
        "url": "https://github.com/milk-org/OpticsMaterials",
        "branch": "feat/bash-engine",
        "role": "Optical material dispersion & air refractive-index library for milk",
    },
    {
        "name": "WFpropagate",
        "url": "https://github.com/milk-org/WFpropagate",
        "branch": "feat/bash-engine",
        "role": "Fresnel & angular-spectrum wavefront propagation library for milk",
    },
]

DEFAULT_RUN_COMMAND = (
    "./scripts/run-ao3k-scexao.sh --seeing 0.60 --phys-time 10.0 --oversample 4 "
    "--bench-mode fused --save-rm _work/ao3k_scexao_rm --save-telemetry speckle"
)


def human_bytes(nbytes: int) -> str:
    """Format byte count using binary IEC-style readable units."""
    val = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if val < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(val)} B"
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{nbytes} B"


def friendly_figure_caption(filename: str) -> str:
    """Return human-friendly caption for a diagnostic PNG filename."""
    if filename in FRIENDLY_FIG_LABELS:
        return FRIENDLY_FIG_LABELS[filename]
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() if stem else filename


def slugify_heading(text: str, seen: dict[str, int]) -> str:
    """Generate a unique lowercase anchor ID for a Markdown heading."""
    plain = re.sub(r"`([^`]*)`", r"\1", text)
    plain = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", plain)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "section"
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def split_table_row(line: str) -> list[str]:
    """Split a GFM table row on unescaped pipes outside backtick code spans."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith(r"\|"):
        s = s[:-1]
    cells: list[str] = []
    buf: list[str] = []
    in_code = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
        elif ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def parse_alignments(delim_line: str) -> list[str]:
    """Parse column alignment hints from a GFM table delimiter row."""
    aligns: list[str] = []
    for raw in split_table_row(delim_line):
        cell = raw.strip()
        if cell.startswith(":") and cell.endswith(":"):
            aligns.append("center")
        elif cell.endswith(":"):
            aligns.append("right")
        elif cell.startswith(":"):
            aligns.append("left")
        else:
            aligns.append("")
    return aligns


def is_table_start(lines: list[str], idx: int) -> bool:
    """Return True only when idx and idx+1 form a valid GFM pipe table header."""
    if idx + 1 >= len(lines):
        return False
    hdr = lines[idx]
    delim = lines[idx + 1]
    stripped = hdr.lstrip()
    if (
        not hdr.strip()
        or "|" not in hdr
        or stripped.startswith(("#", ">", "```"))
        or UL_ITEM_RE.match(hdr)
        or OL_ITEM_RE.match(hdr)
    ):
        return False
    if not TABLE_DELIM_RE.match(delim):
        return False
    return len(split_table_row(hdr)) == len(split_table_row(delim))


class RenderContext:
    """Shared context for resolving local links and tracking referenced images."""

    def __init__(
        self,
        out_slug_dir: Path,
        has_compute_report: bool,
    ) -> None:
        self.out_slug_dir = out_slug_dir.resolve()
        self.has_compute_report = has_compute_report
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
            mapped = "index.html"
        elif path_part == "COMPUTE_REPORT.md" and self.has_compute_report:
            mapped = "compute_report.html"
        final_url = f"{mapped}{sep}{frag}" if sep else mapped
        if mapped in ("index.html", "compute_report.html"):
            exists = mapped == "index.html" or self.has_compute_report
            return final_url, False, exists
        cand = (self.out_slug_dir / mapped).resolve()
        try:
            cand.relative_to(self.out_slug_dir)
        except ValueError:
            return final_url, False, False
        return final_url, False, cand.is_file()


def apply_emph(escaped_text: str) -> str:
    """Apply **bold** and *italic* formatting without touching underscores."""
    out = BOLD_RE.sub(r"<strong>\1</strong>", escaped_text)
    return ITALIC_RE.sub(r"<em>\1</em>", out)


def render_inline(text: str, ctx: RenderContext) -> str:
    """Render Markdown inline spans cleanly in safe token order."""
    code_tokens: list[str] = []
    img_tokens: list[str] = []
    lnk_tokens: list[str] = []

    def sub_code(match: re.Match[str]) -> str:
        idx = len(code_tokens)
        escaped = html.escape(match.group(1), quote=False)
        code_tokens.append(f"<code>{escaped}</code>")
        return f"\x00CODE{idx}\x00"

    def sub_img(match: re.Match[str]) -> str:
        alt = match.group(1)
        raw_url = match.group(2)
        resolved, is_ext, avail = ctx.resolve_local_url(raw_url)
        if not is_ext and Path(resolved.partition("#")[0]).suffix.lower() in IMAGE_EXTS:
            ctx.referenced_images.add(Path(resolved.partition("#")[0]).name)
        idx = len(img_tokens)
        if not avail:
            label = html.escape(alt or raw_url, quote=False)
            img_tokens.append(
                f"<code>{label}</code> "
                f'<span class="muted">(local artifact, omitted from web bundle)</span>'
            )
        else:
            src_esc = html.escape(resolved, quote=True)
            alt_esc = html.escape(alt, quote=True)
            img_tokens.append(f'<img src="{src_esc}" alt="{alt_esc}" loading="lazy">')
        return f"\x00IMG{idx}\x00"

    def sub_lnk(match: re.Match[str]) -> str:
        label = match.group(1)
        raw_url = match.group(2)
        resolved, is_ext, avail = ctx.resolve_local_url(raw_url)
        idx = len(lnk_tokens)
        rendered_lbl = apply_emph(html.escape(label, quote=False))
        if not avail:
            if re.fullmatch(r"\x00CODE\d+\x00", label.strip()):
                lbl_html = label.strip()
            else:
                lbl_html = f"<code>{rendered_lbl}</code>"
            lnk_tokens.append(
                f"{lbl_html} "
                f'<span class="muted">(local artifact, omitted from web bundle)</span>'
            )
        else:
            href_esc = html.escape(resolved, quote=True)
            attrs = ' target="_blank" rel="noopener"' if is_ext else ""
            lnk_tokens.append(f'<a href="{href_esc}"{attrs}>{rendered_lbl}</a>')
        return f"\x00LNK{idx}\x00"

    work = INLINE_CODE_RE.sub(sub_code, text)
    work = INLINE_IMG_RE.sub(sub_img, work)
    work = INLINE_LNK_RE.sub(sub_lnk, work)
    work = apply_emph(html.escape(work, quote=False))
    for i, val in enumerate(lnk_tokens):
        work = work.replace(f"\x00LNK{i}\x00", val)
    for i, val in enumerate(img_tokens):
        work = work.replace(f"\x00IMG{i}\x00", val)
    for i, val in enumerate(code_tokens):
        work = work.replace(f"\x00CODE{i}\x00", val)
    return work


def render_figure_block(alt: str, raw_url: str, ctx: RenderContext) -> str:
    """Render a standalone image or video as a styled <figure> element."""
    resolved, is_ext, avail = ctx.resolve_local_url(raw_url)
    path_only = resolved.partition("#")[0]
    suffix = Path(path_only).suffix.lower()
    if not is_ext and suffix in (IMAGE_EXTS | VIDEO_EXTS):
        ctx.referenced_images.add(Path(path_only).name)
    if not avail:
        lbl = html.escape(alt or raw_url, quote=False)
        return (
            f"<p><code>{lbl}</code> "
            f'<span class="muted">(local artifact, omitted from web bundle)</span></p>'
        )
    src_esc = html.escape(resolved, quote=True)
    alt_esc = html.escape(alt, quote=True)
    cap_esc = html.escape(alt or friendly_figure_caption(Path(path_only).name), quote=False)
    if suffix in VIDEO_EXTS:
        mime = "video/webm" if suffix == ".webm" else "video/mp4"
        poster_attr = ""
        if not is_ext:
            poster_name = f"{Path(path_only).stem}_poster.png"
            if (ctx.out_slug_dir / poster_name).is_file():
                ctx.referenced_images.add(poster_name)
                poster_esc = html.escape(poster_name, quote=True)
                poster_attr = f' poster="{poster_esc}"'
        fmt_lbl = suffix.lstrip(".").upper()
        return (
            '<figure class="report-figure report-video">\n'
            f"  <video controls loop autoplay muted playsinline "
            f'preload="metadata"{poster_attr}>\n'
            f'    <source src="{src_esc}" type="{mime}">\n'
            f"  </video>\n"
            f'  <figcaption>{cap_esc} &middot; '
            f'<a href="{src_esc}" download>Download {fmt_lbl}</a></figcaption>\n'
            "</figure>"
        )
    return (
        '<figure class="report-figure">\n'
        f'  <a href="{src_esc}" target="_blank" rel="noopener">'
        f'<img src="{src_esc}" alt="{alt_esc}" loading="lazy"></a>\n'
        f"  <figcaption>{cap_esc}</figcaption>\n"
        "</figure>"
    )


def convert_markdown_to_html(
    md_text: str,
    ctx: RenderContext,
    heading_seen: dict[str, int] | None = None,
) -> tuple[str, str]:
    """Convert GFM Markdown text to HTML and return (html_body, detected_title)."""
    cleaned = re.sub(r"<!--.*?-->", "", md_text, flags=re.DOTALL)
    lines = cleaned.splitlines()
    seen = heading_seen if heading_seen is not None else {}
    out: list[str] = []
    title = ""
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        fence_m = FENCE_OPEN_RE.match(line.strip())
        if fence_m:
            lang = fence_m.group(1).strip().lower()
            i += 1
            code_lines: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            code_esc = html.escape("\n".join(code_lines), quote=False)
            if lang == "mermaid":
                ctx.has_mermaid = True
                out.append(
                    f'<div class="mermaid-wrap">\n'
                    f'<pre class="mermaid">{code_esc}</pre>\n'
                    f"</div>"
                )
            elif lang:
                lang_esc = html.escape(lang, quote=True)
                out.append(f'<pre><code class="language-{lang_esc}">{code_esc}</code></pre>')
            else:
                out.append(f"<pre><code>{code_esc}</code></pre>")
            continue

        h_m = HEADING_RE.match(line)
        if h_m:
            lvl = len(h_m.group(1))
            raw_h = h_m.group(2).strip()
            if lvl == 1 and not title:
                title = re.sub(r"`([^`]*)`", r"\1", raw_h)
            hid = slugify_heading(raw_h, seen)
            out.append(f'<h{lvl} id="{hid}">{render_inline(raw_h, ctx)}</h{lvl}>')
            i += 1
            continue

        if HR_RE.match(line) and not UL_ITEM_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        if line.lstrip().startswith(">"):
            bq_lines: list[str] = []
            while i < n and lines[i].lstrip().startswith(">"):
                bq_lines.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner_html, _ = convert_markdown_to_html("\n".join(bq_lines), ctx, seen)
            out.append(f'<blockquote class="callout">\n{inner_html}\n</blockquote>')
            continue

        if is_table_start(lines, i):
            headers = split_table_row(lines[i])
            aligns = parse_alignments(lines[i + 1])
            i += 2
            rows: list[list[str]] = []
            while i < n:
                rline = lines[i]
                if (
                    not rline.strip()
                    or "|" not in rline
                    or rline.lstrip().startswith(("#", ">", "```"))
                    or UL_ITEM_RE.match(rline)
                    or OL_ITEM_RE.match(rline)
                ):
                    break
                cells = split_table_row(rline)
                if len(cells) < len(aligns):
                    cells.extend([""] * (len(aligns) - len(cells)))
                rows.append(cells[: len(aligns)])
                i += 1
            tbl = ['<div class="table-wrap">', "<table>", "<thead>", "<tr>"]
            for col_i, hcell in enumerate(headers):
                align = aligns[col_i] if col_i < len(aligns) else ""
                st = f' style="text-align: {align};"' if align else ""
                tbl.append(f"<th{st}>{render_inline(hcell, ctx)}</th>")
            tbl.extend(["</tr>", "</thead>", "<tbody>"])
            for row in rows:
                tbl.append("<tr>")
                for col_i, cell in enumerate(row):
                    align = aligns[col_i] if col_i < len(aligns) else ""
                    st = f' style="text-align: {align};"' if align else ""
                    tbl.append(f"<td{st}>{render_inline(cell, ctx)}</td>")
                tbl.append("</tr>")
            tbl.extend(["</tbody>", "</table>", "</div>"])
            out.append("\n".join(tbl))
            continue

        ul_m = UL_ITEM_RE.match(line)
        ol_m = OL_ITEM_RE.match(line)
        if ul_m or ol_m:
            is_ol = ol_m is not None
            items: list[str] = []
            while i < n:
                cur = lines[i]
                m = OL_ITEM_RE.match(cur) if is_ol else UL_ITEM_RE.match(cur)
                if not m:
                    break
                item_parts = [m.group(2).strip()]
                i += 1
                while i < n:
                    nxt = lines[i]
                    if (
                        not nxt.strip()
                        or UL_ITEM_RE.match(nxt)
                        or OL_ITEM_RE.match(nxt)
                        or nxt.lstrip().startswith(("#", ">", "```"))
                    ):
                        break
                    if re.match(r"^\s{2,}\S", nxt):
                        item_parts.append(nxt.strip())
                        i += 1
                    else:
                        break
                items.append(" ".join(item_parts))
            img_matches = [STANDALONE_IMG_RE.match(it) for it in items]
            if (not is_ol) and all(m is not None for m in img_matches):
                figs = ['<div class="figure-stack">']
                for im in img_matches:
                    assert im is not None
                    figs.append(render_figure_block(im.group(1), im.group(2), ctx))
                figs.append("</div>")
                out.append("\n".join(figs))
            else:
                tag = "ol" if is_ol else "ul"
                lis = [f"<{tag}>"]
                for it in items:
                    lis.append(f"  <li>{render_inline(it, ctx)}</li>")
                lis.append(f"</{tag}>")
                out.append("\n".join(lis))
            continue

        para_lines: list[str] = []
        while i < n:
            cur = lines[i]
            if (
                not cur.strip()
                or HEADING_RE.match(cur)
                or FENCE_OPEN_RE.match(cur.strip())
                or cur.lstrip().startswith(">")
                or UL_ITEM_RE.match(cur)
                or OL_ITEM_RE.match(cur)
                or (HR_RE.match(cur) and not UL_ITEM_RE.match(cur))
                or is_table_start(lines, i)
            ):
                break
            para_lines.append(cur.strip())
            i += 1
        para_text = " ".join(para_lines)
        img_m = STANDALONE_IMG_RE.match(para_text)
        if img_m:
            out.append(render_figure_block(img_m.group(1), img_m.group(2), ctx))
        else:
            out.append(f"<p>{render_inline(para_text, ctx)}</p>")

    return "\n\n".join(out), title


def build_extra_figures_section(
    staged_files: list[Path],
    ctx: RenderContext,
) -> str:
    """Build HTML section for staged figures/videos not embedded in Markdown."""
    staged_names = {p.name for p in staged_files}
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
    data_files = [
        p
        for p in staged_files
        if p.suffix.lower() in DATA_EXTS
        and p.name not in ("report_meta.json", "wfs_psf_short_evolution_meta.json")
    ]
    if not data_files:
        return ""
    rows = [
        '<h2 id="telemetry-data-files">Telemetry &amp; Data Files</h2>',
        '<div class="table-wrap">',
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


def render_page_shell(
    title: str,
    slug: str,
    active_page: str,
    has_compute_report: bool,
    has_repro_section: bool,
    body_html: str,
    has_mermaid: bool,
    updated_utc: str,
) -> str:
    """Wrap rendered article HTML inside the responsive site layout."""
    title_esc = html.escape(title, quote=False)
    slug_esc = html.escape(slug, quote=False)
    opt_cls = ' class="active"' if active_page == "optical" else ""
    cmp_cls = ' class="active"' if active_page == "compute" else ""
    repro_href = (
        "index.html#reproducibility-github-provenance"
        if has_repro_section
        else "../index.html#reproduce-results"
    )
    nav_links = [
        '<a href="../index.html">Front Page</a>',
        f'<a href="index.html"{opt_cls}>Optical &amp; Control Report</a>',
    ]
    if has_compute_report:
        nav_links.append(
            f'<a href="compute_report.html"{cmp_cls}>Compute &amp; Optimization Report</a>'
        )
    nav_links.extend(
        [
            f'<a href="{repro_href}">Reproduce</a>',
            '<a href="https://github.com/cacao-org/cacao-work" '
            'target="_blank" rel="noopener">GitHub</a>',
        ]
    )

    mermaid_script = ""
    if has_mermaid:
        mermaid_script = (
            '\n<script type="module">\n'
            'import mermaid from '
            '"https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";\n'
            "mermaid.initialize({ startOnLoad: true, theme: 'default' });\n"
            "</script>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc}</title>
<style>
{CSS_STYLES}
</style>
</head>
<body>
<header class="site-header">
  <div class="nav-inner">
    <a class="brand" href="../index.html">cacao-work AO Report &middot; {slug_esc}</a>
    <nav class="nav-links">
      {"".join(nav_links)}
    </nav>
  </div>
</header>
<main class="container">
{body_html}
</main>
<footer class="site-footer">
  <span>Generated from <code>{slug_esc}</code> by
    <a href="https://github.com/cacao-org/cacao-work"
       target="_blank" rel="noopener"><code>cacao-work</code></a></span>
  <span>Updated {html.escape(updated_utc, quote=False)}</span>
</footer>{mermaid_script}
</body>
</html>
"""


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


def extract_metrics_highlights(
    out_slug_dir: Path,
) -> tuple[list[str], dict[str, object] | None]:
    """Extract summary metric badges and reproducibility info from staged metrics JSON."""
    cands = [out_slug_dir / "ao3k_scexao_metrics.json"]
    cands.extend(sorted(out_slug_dir.glob("*_metrics.json")))
    metrics_path = next((p for p in cands if p.is_file()), None)
    if metrics_path is None:
        return [], None
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], None
    if not isinstance(data, dict):
        return [], None

    badges: list[str] = []
    sa = data.get("star_and_atmosphere")
    if isinstance(sa, dict):
        if "seeing_arcsec_500nm" in sa:
            badges.append(f'Seeing {float(sa["seeing_arcsec_500nm"]):.2f}"')
        if "internal_bench_hz" in sa and "internal_dt_us" in sa:
            badges.append(
                f'{float(sa["internal_bench_hz"]) / 1000.0:.1f} kHz '
                f'({float(sa["internal_dt_us"]):.0f} us)'
            )
        if "physical_time_s" in sa:
            badges.append(f'{float(sa["physical_time_s"]):.1f} s phys')
    pm = data.get("psf_metrics")
    if isinstance(pm, dict):
        vis_f = pm.get("vis", {}).get("final", {}) if isinstance(pm.get("vis"), dict) else {}
        nir_f = pm.get("nir", {}).get("final", {}) if isinstance(pm.get("nir"), dict) else {}
        if isinstance(vis_f, dict) and "strehl_peak" in vis_f:
            badges.append(f'Vis SR {float(vis_f["strehl_peak"]) * 100.0:.1f}%')
        if isinstance(nir_f, dict) and "strehl_peak" in nir_f:
            badges.append(f'H SR {float(nir_f["strehl_peak"]) * 100.0:.1f}%')
    wm = data.get("wavefront_metrics")
    if isinstance(wm, dict):
        locs = wm.get("locations")
        if isinstance(locs, dict) and isinstance(locs.get("final"), dict):
            fin_l = locs["final"]
            if "quad_total_rms_nm" in fin_l:
                badges.append(f'WFE {float(fin_l["quad_total_rms_nm"]):.1f} nm')

    repro = data.get("reproducibility")
    repro_dict = repro if isinstance(repro, dict) else None
    return badges, repro_dict


def build_front_page_html(metas: list[dict[str, object]]) -> str:
    """Render the root Front Page with intro, report cards, GitHub repos, and CLI recipe."""
    latest_repro: dict[str, object] | None = None
    primary_slug = ""
    for meta in metas:
        if not primary_slug:
            primary_slug = str(meta.get("slug", ""))
        rep = meta.get("reproducibility")
        if isinstance(rep, dict) and rep.get("repositories"):
            latest_repro = rep
            primary_slug = str(meta.get("slug", primary_slug))

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

    cards: list[str] = ['<div class="report-card-grid">']
    for meta in metas:
        slug = str(meta.get("slug", ""))
        title = str(meta.get("title", slug))
        has_cmp = bool(meta.get("has_compute_report", False))
        has_repro = bool(meta.get("has_repro_section", False))
        sz = human_bytes(int(meta.get("total_bytes", 0)))
        nfiles = int(meta.get("file_count", 0))
        upd = str(meta.get("updated_utc", ""))
        raw_badges = meta.get("badges", [])
        badge_items = raw_badges if isinstance(raw_badges, list) else []
        badge_html = ""
        if badge_items:
            pills = "".join(
                f'<span class="metric-pill">{html.escape(str(b), quote=False)}</span>'
                for b in badge_items
            )
            badge_html = f'  <div class="badge-row">{pills}</div>\n'
        slug_esc = html.escape(slug, quote=True)
        title_esc = html.escape(title, quote=False)
        repro_link = (
            f"./{slug_esc}/index.html#reproducibility-github-provenance"
            if has_repro
            else "#reproduce-results"
        )
        links = [
            f'<a class="btn" href="./{slug_esc}/index.html">'
            "Optical &amp; Control Report</a>"
        ]
        if has_cmp:
            links.append(
                f'<a class="btn btn-secondary" '
                f'href="./{slug_esc}/compute_report.html">Compute Report</a>'
            )
        links.append(
            f'<a class="btn btn-secondary" href="{repro_link}">Reproduce</a>'
        )
        cards.append(
            '<div class="report-card">\n'
            f"  <h3>{title_esc}</h3>\n"
            f"{badge_html}"
            f'  <p class="muted"><code>{html.escape(slug, quote=False)}</code> &middot; '
            f"{nfiles} files ({sz})<br>Updated {html.escape(upd, quote=False)}</p>\n"
            f'  <div class="card-links">{"".join(links)}</div>\n'
            "</div>"
        )
    cards.append("</div>")

    repo_rows: list[str] = [
        '<div class="table-wrap">',
        "<table>",
        "<thead><tr>"
        '<th style="text-align: left;">Repository</th>'
        '<th style="text-align: center;">Branch</th>'
        '<th style="text-align: center;">Commit</th>'
        '<th style="text-align: left;">Role in Simulation Stack</th>'
        "</tr></thead>",
        "<tbody>",
    ]
    for r in repo_list:
        rname = html.escape(r.get("name", ""), quote=False)
        rurl = html.escape(r.get("url", ""), quote=True)
        rbr = html.escape(r.get("branch", "main"), quote=False)
        rsha = r.get("commit", "")
        rshort = r.get("short_commit", rsha[:7] if rsha else "")
        rrole = html.escape(r.get("role", ""), quote=False)
        if rsha and rshort:
            c_url = html.escape(f"{r.get('url', '')}/commit/{rsha}", quote=True)
            sha_html = (
                f'<a href="{c_url}" target="_blank" rel="noopener">'
                f"<code>{html.escape(rshort, quote=False)}</code></a>"
            )
        else:
            sha_html = "<code>HEAD</code>"
        repo_rows.append(
            "<tr>"
            f'<td><a href="{rurl}" target="_blank" rel="noopener">'
            f"<strong>{rname}</strong></a></td>"
            f'<td style="text-align: center;"><code>{rbr}</code></td>'
            f'<td style="text-align: center;">{sha_html}</td>'
            f'<td class="wrap-cell">{rrole}</td>'
            "</tr>"
        )
    repo_rows.extend(["</tbody>", "</table>", "</div>"])

    def clone_cmd(rname: str) -> str:
        info = repo_by_name.get(rname, {"url": f"https://github.com/milk-org/{rname}"})
        url = info.get("url", "").rstrip("/") + ".git"
        br = info.get("branch", "main")
        sha = info.get("commit", "")
        line = f"git clone -b {br} {url} {rname}"
        if sha:
            line += f" && git -C {rname} checkout -q {sha}"
        return line

    isio_sha = repo_by_name.get("ImageStreamIO", {}).get("commit", "")
    isio_cmd = "git -C milk submodule update --init src/engine/ImageStreamIO"
    if isio_sha:
        isio_cmd += f" && git -C milk/src/engine/ImageStreamIO checkout -q {isio_sha}"

    run_cmd = (
        str(latest_repro.get("run_command", DEFAULT_RUN_COMMAND))
        if latest_repro
        else DEFAULT_RUN_COMMAND
    )
    stage_slug = primary_slug or "ao3k_scexao"
    artifact_note = ""
    if latest_repro and primary_slug:
        bfile = html.escape(str(latest_repro.get("bench_file", "ao3k_scexao.bench")))
        mfile = html.escape(
            str(latest_repro.get("metrics_file", "ao3k_scexao_metrics.json"))
        )
        p_esc = html.escape(primary_slug, quote=True)
        artifact_note = (
            "<li><strong>Machine-Readable Bench &amp; Provenance Manifest</strong>: "
            f'<a href="./{p_esc}/{bfile}"><code>{bfile}</code></a> and '
            f'<a href="./{p_esc}/{mfile}"><code>{mfile}</code></a> '
            "(records exact optical parameters, calibrated loop metrics, and repository "
            "commit SHAs).</li>\n"
        )

    bash_recipe = "\n".join(
        [
            "# 1. Clone all open-source stack repositories into ~/src",
            "mkdir -p ~/src && cd ~/src",
            clone_cmd("milk"),
            isio_cmd,
            clone_cmd("cacao"),
            clone_cmd("milk-mltools"),
            clone_cmd("OpticsMaterials"),
            clone_cmd("WFpropagate"),
            clone_cmd("AtmosphericTurbulenceSimul"),
            clone_cmd("cacaosim"),
            clone_cmd("cacao-work"),
            "",
            "# 2. Configure, compile, install into milk/_install, and run isolated sanity tests",
            "cd ~/src/cacao-work",
            "source env.sh",
            "./scripts/build-all.sh",
            "pytest -v tests/test_00_stack_sanity.py tests/test_05_ao_web_report.py",
            "",
            "# 3. Run closed-loop Subaru AO3k + SCExAO simulation, telemetry, video & reports",
            run_cmd,
            "",
            "# 4. Stage static HTML website locally under _work/_web_site/public/",
            f"./scripts/publish-ao-report.sh --build-only _work/{stage_slug}",
        ]
    )
    bash_esc = html.escape(bash_recipe, quote=False)

    body = (
        "<h1>cacao-work &middot; Closed-Loop Adaptive Optics Simulation &amp; Control</h1>\n"
        "<p>Open-source hardware-in-the-loop adaptive optics simulation and real-time control "
        "benchmark suite coupling "
        '<a href="https://github.com/cacao-org/cacao" target="_blank" rel="noopener">'
        "<strong>cacao</strong></a> real-time wavefront control, "
        '<a href="https://github.com/milk-org/milk" target="_blank" rel="noopener">'
        "<strong>milk</strong></a> / "
        '<a href="https://github.com/milk-org/ImageStreamIO" target="_blank" rel="noopener">'
        "<strong>ImageStreamIO</strong></a> POSIX &amp; CUDA shared-memory pipelines "
        "(<code>fpspipe</code> / <code>milk-script</code>), "
        '<a href="https://github.com/cacao-org/cacaosim" target="_blank" rel="noopener">'
        "<strong>cacaosim</strong></a> GPU polychromatic multi-rate optical propagation, "
        '<a href="https://github.com/oguyon/AtmosphericTurbulenceSimul" '
        'target="_blank" rel="noopener"><strong>milkatmturb</strong></a> multi-layer '
        "atmospheric turbulence, and "
        '<a href="https://github.com/milk-org/milk-mltools" target="_blank" rel="noopener">'
        "<strong>milk-mltools</strong></a> synchronized telemetry &amp; PSF reconstruction, "
        "orchestrated end-to-end by "
        '<a href="https://github.com/cacao-org/cacao-work" target="_blank" rel="noopener">'
        "<strong>cacao-work</strong></a> without any terminal multiplexer.</p>\n"
        '<blockquote class="callout"><p><strong>AI &amp; CLI Reproducible</strong>: '
        "Every simulation executes real CACAO real-time processes in isolated "
        "<code>/dev/shm/cacao_*</code> sandboxes (measured hardware latency <code>mlat</code>, "
        "Hadamard response matrices, SVD modal control, lossless telemetry cubes, and "
        "short-timescale WFS/PSF video rendering). Jump directly to "
        '<a href="#github-repositories">GitHub Repositories</a> or the copy-pasteable '
        '<a href="#reproduce-results">End-to-End Reproduction Guide</a>.</p></blockquote>\n'
        '<h2 id="published-reports">Published Simulation Reports</h2>\n'
        + "\n".join(cards)
        + '\n\n<h2 id="github-repositories">Open-Source GitHub Repositories</h2>\n'
        "<p>All source repositories below are public on GitHub and build into a single "
        "relocatable prefix (<code>milk/_install/milk-&lt;version&gt;</code>) via "
        "<code>./scripts/build-all.sh</code>:</p>\n"
        + "\n".join(repo_rows)
        + '\n\n<h2 id="reproduce-results">'
        "End-to-End Reproduction Guide (CLI &amp; AI Agent Ready)</h2>\n"
        "<p>An autonomous AI coding agent or human operator can reproduce the full closed-loop "
        "simulation, telemetry cubes, short-timescale WFS/PSF video, and static HTML reports "
        "from a clean Linux workspace using the specification below:</p>\n"
        "<ul>\n"
        "<li><strong>System Prerequisites</strong>: Linux <code>x86_64</code> with "
        "<code>/dev/shm</code> (<code>tmpfs</code>), GCC/G++ with OpenMP, CMake &ge; 3.20, "
        "<code>pkg-config</code>, CFITSIO, FFTW3 (<code>fftw3</code> &amp; <code>fftw3f</code>), "
        "OpenBLAS + LAPACKE, <code>ncurses</code>, NVIDIA CUDA Toolkit (<code>nvcc</code>, "
        "<code>cufft</code>, <code>cublas</code>; CPU fallback also supported), and Python &ge; "
        "3.10 with <code>numpy</code>, <code>astropy</code>, <code>matplotlib</code>, "
        "<code>pillow</code>, <code>imageio-ffmpeg</code>, and <code>pytest</code>.</li>\n"
        "<li><strong>Submodule Note</strong>: Initialize only "
        "<code>milk/src/engine/ImageStreamIO</code> (as shown below) rather than "
        "<code>git clone --recurse-submodules</code>, because <code>milk-extra-src</code> "
        "modules are tracked in-tree on <code>feat/bash-engine</code>.</li>\n"
        f"{artifact_note}"
        "</ul>\n"
        f"<pre><code>{bash_esc}</code></pre>\n"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>cacao-work &middot; AO Simulation Reports &amp; Reproduction Guide</title>
<style>
{CSS_STYLES}
</style>
</head>
<body>
<header class="site-header">
  <div class="nav-inner">
    <a class="brand" href="./index.html">cacao-work &middot; AO Simulation Suite</a>
    <nav class="nav-links">
      <a href="#published-reports">Reports</a>
      <a href="#github-repositories">GitHub Repos</a>
      <a href="#reproduce-results">Reproduce</a>
      <a href="https://github.com/cacao-org/cacao-work" target="_blank" rel="noopener">GitHub</a>
    </nav>
  </div>
</header>
<main class="container">
{body}</main>
<footer class="site-footer">
  <span>Open-source AO stack:
    <a href="https://github.com/cacao-org/cacao-work"
       target="_blank" rel="noopener"><code>cacao-org/cacao-work</code></a></span>
  <span>Self-contained static bundle for human &amp; AI reproduction</span>
</footer>
</body>
</html>
"""


def write_root_indices_and_firebase(
    site_dir: Path,
    project_id: str | None,
    site_id: str | None,
) -> None:
    """Build Front Page at public/index.html & reports.html, plus firebase.json."""
    public_dir = site_dir / "public"
    metas: list[dict[str, object]] = []
    for meta_path in sorted(public_dir.glob("*/report_meta.json")):
        try:
            metas.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue

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
                "headers": [
                    {"key": "Cache-Control", "value": "public, max-age=3600"}
                ],
            },
            {
                "source": "**/*.@(html|json)",
                "headers": [
                    {"key": "Cache-Control", "value": "public, max-age=300"}
                ],
            },
        ],
    }
    if site_id:
        hosting_cfg["site"] = site_id

    firebase_json = {"hosting": hosting_cfg}
    (site_dir / "firebase.json").write_text(
        json.dumps(firebase_json, indent=2) + "\n", encoding="utf-8"
    )
    if project_id:
        firebaserc = {"projects": {"default": project_id}}
        (site_dir / ".firebaserc").write_text(
            json.dumps(firebaserc, indent=2) + "\n", encoding="utf-8"
        )


def build_site(
    report_dir: Path,
    site_dir: Path,
    slug: str,
    project_id: str | None = None,
    site_id: str | None = None,
    include_fits: bool = False,
) -> dict[str, object]:
    """Stage assets and build static web pages for report_dir into site_dir."""
    report_dir = report_dir.resolve()
    site_dir = site_dir.resolve()
    report_md_path = report_dir / "REPORT.md"
    if not report_md_path.is_file():
        raise FileNotFoundError(f"Missing REPORT.md in {report_dir}")

    compute_md_path = report_dir / "COMPUTE_REPORT.md"
    has_compute = compute_md_path.is_file()
    out_slug_dir = site_dir / "public" / slug
    staged_files = stage_assets(report_dir, out_slug_dir, include_fits)

    ctx = RenderContext(out_slug_dir, has_compute)
    updated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    compute_body = ""
    compute_title = f"Compute Report ({slug})"
    compute_mermaid = False
    if has_compute:
        pre_mermaid = ctx.has_mermaid
        ctx.has_mermaid = False
        compute_body, det_ctitle = convert_markdown_to_html(
            compute_md_path.read_text(encoding="utf-8"), ctx
        )
        compute_mermaid = ctx.has_mermaid
        ctx.has_mermaid = pre_mermaid
        if det_ctitle:
            compute_title = det_ctitle

    ctx.has_mermaid = False
    report_body, det_rtitle = convert_markdown_to_html(
        report_md_path.read_text(encoding="utf-8"), ctx
    )
    report_mermaid = ctx.has_mermaid
    report_title = det_rtitle or f"AO Simulation Report ({slug})"
    has_repro_section = 'id="reproducibility-github-provenance"' in report_body

    extra_figs_html = build_extra_figures_section(staged_files, ctx)
    data_files_html = build_telemetry_files_section(staged_files)
    full_report_body = "\n\n".join(
        p for p in (report_body, extra_figs_html, data_files_html) if p
    )

    index_html = render_page_shell(
        title=report_title,
        slug=slug,
        active_page="optical",
        has_compute_report=has_compute,
        has_repro_section=has_repro_section,
        body_html=full_report_body,
        has_mermaid=report_mermaid,
        updated_utc=updated_utc,
    )
    (out_slug_dir / "index.html").write_text(index_html, encoding="utf-8")

    if has_compute:
        compute_html = render_page_shell(
            title=compute_title,
            slug=slug,
            active_page="compute",
            has_compute_report=True,
            has_repro_section=has_repro_section,
            body_html=compute_body,
            has_mermaid=compute_mermaid,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "compute_report.html").write_text(
            compute_html, encoding="utf-8"
        )

    badges, repro_dict = extract_metrics_highlights(out_slug_dir)
    all_slug_files = [p for p in out_slug_dir.iterdir() if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in all_slug_files)
    meta: dict[str, object] = {
        "title": report_title,
        "slug": slug,
        "has_compute_report": has_compute,
        "has_repro_section": has_repro_section,
        "badges": badges,
        "updated_utc": updated_utc,
        "total_bytes": total_bytes,
        "file_count": len(all_slug_files) + 1,
    }
    if repro_dict is not None:
        meta["reproducibility"] = repro_dict
    (out_slug_dir / "report_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    write_root_indices_and_firebase(site_dir, project_id, site_id)
    return meta


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build static HTML website from an AO simulation report directory."
    )
    parser.add_argument(
        "--report-dir",
        required=True,
        type=Path,
        help="Path to simulation output directory containing REPORT.md",
    )
    parser.add_argument(
        "--site-dir",
        default=Path("_work/_web_site"),
        type=Path,
        help="Firebase Hosting root staging directory (default: _work/_web_site)",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="URL subpath slug under public/ (default: report directory basename)",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Optional Firebase project ID to write into .firebaserc",
    )
    parser.add_argument(
        "--site-id",
        default=None,
        help="Optional Firebase Hosting site ID to write into firebase.json",
    )
    parser.add_argument(
        "--include-fits",
        action="store_true",
        help="Include large .fits data cubes in staged web assets",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    slug = args.slug or args.report_dir.resolve().name
    meta = build_site(
        report_dir=args.report_dir,
        site_dir=args.site_dir,
        slug=slug,
        project_id=args.project,
        site_id=args.site_id,
        include_fits=args.include_fits,
    )
    print(
        f"[web-report] Built {slug}: {meta['file_count']} files "
        f"({human_bytes(int(meta['total_bytes']))}) in {args.site_dir / 'public' / slug}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
