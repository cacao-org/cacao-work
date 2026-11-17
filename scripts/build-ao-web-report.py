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
    ".json",
    ".csv",
    ".tsv",
    ".txt",
    ".dat",
    ".bench",
}
DATA_EXTS = {".json", ".csv", ".tsv", ".txt", ".dat", ".fits", ".bench"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}

FRIENDLY_FIG_LABELS = {
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
    "psf_comparison_2x3.png": "Long-Exposure PSF Comparison (2x3)",
    "psf_radial_profiles.png": "PSF Radial Profiles & Encircled Energy",
    "wf_strehl_timeseries_4x1.png": (
        "RMS Wavefront Error & Strehl Ratio Time Series with Sampled Instants (4x1)"
    ),
    "psf_inst_vis_5x3.png": "Instantaneous Visible 0.75 um PSFs at Sampled Instants (5x3)",
    "psf_inst_nir_5x3.png": "Instantaneous Near-IR H-Band 1.65 um PSFs at Sampled Instants (5x3)",
    "wf_stats_2x3.png": "Wavefront Mean & Temporal Std Dev (2x3)",
    "wf_samples_5x3.png": "Instantaneous Pupil Wavefront OPD Samples at Sampled Instants (5x3)",
    "wfs_samples_5x4.png": (
        "Instantaneous Pyramid WFS Frames & Signals at Sampled Instants (5x4)"
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
"""


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
    """Render a standalone image as a clickable <figure> element."""
    resolved, is_ext, avail = ctx.resolve_local_url(raw_url)
    path_only = resolved.partition("#")[0]
    if not is_ext and Path(path_only).suffix.lower() in IMAGE_EXTS:
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
    """Build HTML section for staged PNG figures not embedded in Markdown."""
    extra_imgs = [
        p
        for p in staged_files
        if p.suffix.lower() in IMAGE_EXTS and p.name not in ctx.referenced_images
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
        if p.suffix.lower() in DATA_EXTS and p.name != "report_meta.json"
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
    body_html: str,
    has_mermaid: bool,
    updated_utc: str,
) -> str:
    """Wrap rendered article HTML inside the responsive site layout."""
    title_esc = html.escape(title, quote=False)
    slug_esc = html.escape(slug, quote=False)
    opt_cls = ' class="active"' if active_page == "optical" else ""
    cmp_cls = ' class="active"' if active_page == "compute" else ""
    nav_links = [
        f'<a href="index.html"{opt_cls}>Optical &amp; Control Report</a>',
    ]
    if has_compute_report:
        nav_links.append(
            f'<a href="compute_report.html"{cmp_cls}>Compute &amp; Optimization Report</a>'
        )
    nav_links.append('<a href="../reports.html">All Reports</a>')

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
    <a class="brand" href="index.html">cacao-work AO Report &middot; {slug_esc}</a>
    <nav class="nav-links">
      {"".join(nav_links)}
    </nav>
  </div>
</header>
<main class="container">
{body_html}
</main>
<footer class="site-footer">
  <span>Generated from <code>{slug_esc}</code> by <code>cacao-work</code></span>
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


def write_root_indices_and_firebase(
    site_dir: Path,
    project_id: str | None,
    site_id: str | None,
) -> None:
    """Build reports.html, root index.html redirect/index, and firebase.json."""
    public_dir = site_dir / "public"
    metas: list[dict[str, object]] = []
    for meta_path in sorted(public_dir.glob("*/report_meta.json")):
        try:
            metas.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue

    cards: list[str] = ['<div class="report-card-grid">']
    for meta in metas:
        slug = str(meta.get("slug", ""))
        title = str(meta.get("title", slug))
        has_cmp = bool(meta.get("has_compute_report", False))
        sz = human_bytes(int(meta.get("total_bytes", 0)))
        nfiles = int(meta.get("file_count", 0))
        upd = str(meta.get("updated_utc", ""))
        slug_esc = html.escape(slug, quote=True)
        title_esc = html.escape(title, quote=False)
        links = [f'<a class="btn" href="./{slug_esc}/index.html">Optical Report</a>']
        if has_cmp:
            links.append(
                f'<a class="btn btn-secondary" '
                f'href="./{slug_esc}/compute_report.html">Compute Report</a>'
            )
        cards.append(
            '<div class="report-card">\n'
            f"  <h3>{title_esc}</h3>\n"
            f'  <p class="muted"><code>{html.escape(slug, quote=False)}</code> &middot; '
            f"{nfiles} files ({sz})<br>Updated {html.escape(upd, quote=False)}</p>\n"
            f'  <div class="card-links">{"".join(links)}</div>\n'
            "</div>"
        )
    cards.append("</div>")
    reports_body = (
        "<h1>AO Simulation Reports</h1>\n"
        "<p>Published optical, control, and systems performance reports from "
        "<code>cacao-work</code>.</p>\n"
        + "\n".join(cards)
    )
    reports_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AO Simulation Reports</title>
<style>
{CSS_STYLES}
</style>
</head>
<body>
<header class="site-header">
  <div class="nav-inner">
    <span class="brand">cacao-work AO Simulation Reports</span>
  </div>
</header>
<main class="container">
{reports_body}
</main>
</body>
</html>
"""
    (public_dir / "reports.html").write_text(reports_html, encoding="utf-8")

    redirects: list[dict[str, object]] = []
    if len(metas) == 1:
        only_slug = str(metas[0]["slug"])
        only_esc = html.escape(only_slug, quote=True)
        redirect_html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            f'<meta http-equiv="refresh" content="0; url=./{only_esc}/">\n'
            f'<title>Redirecting to {only_esc}</title>\n'
            "</head>\n"
            "<body>\n"
            f'<p>Redirecting to <a href="./{only_esc}/">./{only_esc}/</a>...</p>\n'
            "</body>\n"
            "</html>\n"
        )
        (public_dir / "index.html").write_text(redirect_html, encoding="utf-8")
        redirects.append(
            {"source": "/", "destination": f"/{only_slug}/", "type": 302}
        )
    else:
        (public_dir / "index.html").write_text(reports_html, encoding="utf-8")

    hosting_cfg: dict[str, object] = {
        "public": "public",
        "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
        "cleanUrls": False,
        "headers": [
            {
                "source": "**/*.@(png|jpg|jpeg|svg|webp)",
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
    if redirects:
        hosting_cfg["redirects"] = redirects

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
            body_html=compute_body,
            has_mermaid=compute_mermaid,
            updated_utc=updated_utc,
        )
        (out_slug_dir / "compute_report.html").write_text(
            compute_html, encoding="utf-8"
        )

    all_slug_files = [p for p in out_slug_dir.iterdir() if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in all_slug_files)
    meta = {
        "title": report_title,
        "slug": slug,
        "has_compute_report": has_compute,
        "updated_utc": updated_utc,
        "total_bytes": total_bytes,
        "file_count": len(all_slug_files) + 1,
    }
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
