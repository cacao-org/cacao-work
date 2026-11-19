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
    "coro_before_after_psf.png": (
        "H-Band Focal-Plane PSF Before vs After Lyot Coronagraph (2x3)"
    ),
    "coro_lyot_stop_illumination.png": (
        "Light Incident on Pupil-Plane Lyot Stop & Reflective-Lyot LOWFS Power Budget (2x3)"
    ),
    "coro_lowfs_summary.png": (
        "Subaru H-Band Lyot Coronagraph & Reflective-Lyot Defocused LLOWFS Summary (2x3)"
    ),
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
    "predictive_control_summary_2x2.png": (
        "PSOL Auto-Regressive Predictive Control Filter & Modal Residual Summary (2x2)"
    ),
    "ar_order_optical_coro_summary_2x3.png": (
        "Optical, Wavefront & Lyot Coronagraph Performance vs. AR Predictive Order (2x3)"
    ),
    "ar_order_timeseries_and_petals_2x3.png": (
        "Synchronized 5.0 s Time Series & Subaru V-Spider Petal OPD Maps (2x3)"
    ),
    "ar_order_filter_weights_and_freq_2x2.png": (
        "Learned AR(P) Filter Impulse Responses, Cauchy-Schwarz Phase Lead & Freq Response (2x2)"
    ),
    "ar_order_modal_and_psd_2x2.png": (
        "Closed-Loop 1 kHz / 2 kHz Temporal PSDs & Spatial Modal Residual Spectra (2x2)"
    ),
    "ar_order_bias_variance_sample_complexity_2x2.png": (
        "Walk-Forward Bias-Variance Tradeoff & Sample-Complexity Scaling (2x2)"
    ),
    "ar_order_psf_and_compute_2x3.png": (
        "H-Band Coronagraphic PSFs, Real-Time Compute Scaling & Pareto Frontier (2x3)"
    ),
    "eof_vs_ar_offline_20s_2x2.png": (
        "Cross-Mode Block-EOF vs. Diagonal AR(16): 20 s Walk-Forward Scaling & Coupling (2x2)"
    ),
    "eof_vs_ar_closed_loop_2x3.png": (
        "Cross-Mode Block-EOF vs. Diagonal AR(16): Closed-Loop Optical, Coro & Compute (2x3)"
    ),
    "calib_2wfs1dm_summary_2x2.png": (
        "Joint 2-WFS + Inter-Stage DM Telemetry Calibration Summary (2x2)"
    ),
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
.study-card {
  border: 2px solid var(--accent);
  border-radius: 12px;
  padding: 1.25rem 1.35rem;
  background: var(--accent-soft);
  margin: 1rem 0 1.5rem;
}
.study-card h3 { margin-top: 0; font-size: 1.2rem; }
.study-card p.study-summary { margin: 0.45rem 0 0.75rem; font-size: 0.94rem; }
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
.param-cell {
  white-space: normal;
  min-width: 230px;
  max-width: 400px;
}
.param-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}
.param-pill {
  display: inline-block;
  padding: 0.12rem 0.45rem;
  border-radius: 6px;
  font-size: 0.78rem;
  line-height: 1.35;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--muted);
}
.param-pill-diff {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--text);
}
.param-pill-base {
  background: var(--surface);
  border: 1px dashed var(--border);
  color: var(--muted);
  font-weight: 600;
}
.shared-params {
  margin: -0.9rem 0 1.4rem;
  padding: 0.55rem 0.85rem;
  border-radius: 8px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.5;
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
            return final_url, False, cand.is_file()
        except ValueError:
            # Allow relative links to sibling published reports inside <site_dir>/public/
            public_root = self.out_slug_dir.parent.resolve()
            try:
                cand.relative_to(public_root)
                return final_url, False, cand.is_file()
            except ValueError:
                return final_url, False, False


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
        and p.name
        not in (
            "report_meta.json",
            "study_meta.json",
            "wfs_psf_short_evolution_meta.json",
        )
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
    primary_nav_label: str = "Optical & Control Report",
) -> str:
    """Wrap rendered article HTML inside the responsive site layout."""
    title_esc = html.escape(title, quote=False)
    slug_esc = html.escape(slug, quote=False)
    opt_cls = ' class="active"' if active_page == "optical" else ""
    cmp_cls = ' class="active"' if active_page == "compute" else ""
    primary_lbl_esc = html.escape(primary_nav_label, quote=False)
    repro_href = (
        "index.html#reproducibility-github-provenance"
        if has_repro_section
        else "../index.html#reproduce-results"
    )
    nav_links = [
        '<a href="../index.html">Front Page</a>',
        f'<a href="index.html"{opt_cls}>{primary_lbl_esc}</a>',
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


TRACKED_PARAMS: list[tuple[str, str]] = [
    ("control_law", "Control Law"),
    ("llowfs", "LLOWFS"),
    ("calib_2wfs1dm", "2-WFS/1-DM Calib"),
    ("seeing", "Seeing"),
    ("star_mag", "Star Mag"),
    ("phys_time", "Phys Time"),
    ("oversample", "Oversample"),
    ("bench_mode", "Bench"),
    ("gain1", "Gain1"),
    ("gain2", "Gain2"),
    ("gain3", "Gain3"),
    ("mult1", "Mult1"),
    ("mult2", "Mult2"),
    ("mult3", "Mult3"),
    ("mgain_alpha", "mgain α"),
    ("mgain_floor", "mgain floor"),
    ("mgain_tt", "mgain TT"),
    ("svdlim1", "SVDlim1"),
    ("svdlim2", "SVDlim2"),
    ("svdlim3", "SVDlim3"),
    ("pf_mix", "PF Mix"),
    ("pf_reg", "PF Reg"),
    ("pf_mgain_exp", "PF mgain exp"),
    ("pf_ntrain", "PF N_train"),
    ("telemetry", "Telemetry"),
]


def _parse_cmd_flag(cmd: str, flag: str) -> str | None:
    """Extract the value following a CLI --flag token in a saved run_command string."""
    if not cmd:
        return None
    m = re.search(rf"(?:^|\s){re.escape(flag)}\s+(\S+)", cmd)
    return m.group(1) if m else None


def extract_run_parameters(data: dict[str, object]) -> dict[str, str]:
    """Extract normalized simulation parameters from a metrics JSON dictionary."""
    params: dict[str, str] = {}
    sa = data.get("star_and_atmosphere")
    repro = data.get("reproducibility")
    cmd = str(repro.get("run_command", "")) if isinstance(repro, dict) else ""
    loops = data.get("loops") if isinstance(data.get("loops"), dict) else {}
    l1 = loops.get("stage1_ao3k") if isinstance(loops.get("stage1_ao3k"), dict) else {}
    l2 = loops.get("stage2_scexao") if isinstance(loops.get("stage2_scexao"), dict) else {}
    l3 = loops.get("stage3_llowfs") if isinstance(loops.get("stage3_llowfs"), dict) else {}
    cm = data.get("coronagraph_metrics")
    lo = cm.get("llowfs") if isinstance(cm, dict) and isinstance(cm.get("llowfs"), dict) else None
    pc = data.get("predictive_control")
    pc_on = bool(isinstance(pc, dict) and pc.get("enabled"))
    c2d = data.get("calib_2wfs1dm")
    c2d_on = bool(isinstance(c2d, dict) and c2d.get("enabled"))

    has_ao_cfg = bool(loops or lo is not None or isinstance(pc, dict) or isinstance(c2d, dict))
    if has_ao_cfg:
        if pc_on and isinstance(pc, dict):
            pf_mode = str(pc.get("pf_mode", "ar")).lower()
            pf_blk = int(pc.get("pf_blocksize", 128))
            pf_ord = int(pc.get("pf_order", 8))
            if pf_mode == "eof":
                params["control_law"] = f"PSOL Block-EOF(B={pf_blk}, P={pf_ord})"
            else:
                params["control_law"] = f"PSOL AR({pf_ord}) Predictive"
            if "pf_mix" in pc:
                params["pf_mix"] = f'{float(pc["pf_mix"]):.2f}'
            if "pf_reg" in pc:
                params["pf_reg"] = f'{float(pc["pf_reg"]):g}'
            if "pf_mgain_exp" in pc:
                params["pf_mgain_exp"] = f'{float(pc["pf_mgain_exp"]):.2f}'
            s1_pc = pc.get("stage1")
            if isinstance(s1_pc, dict) and s1_pc.get("n_samples"):
                params["pf_ntrain"] = str(int(s1_pc["n_samples"]))
        else:
            params["control_law"] = "Modal Integrator"

    lo_closed: bool | None = None
    if lo is not None:
        lo_closed = bool(lo.get("enabled_closed_loop", True))
        params["llowfs"] = "CLOSED" if lo_closed else "OPEN"

    if has_ao_cfg:
        if c2d_on and isinstance(c2d, dict):
            db = int(c2d.get("dim_b", 40))
            wo = int(c2d.get("whiten_order", 4))
            params["calib_2wfs1dm"] = f"ON ({db}m, AR({wo}))"
        else:
            params["calib_2wfs1dm"] = "OFF"

    if isinstance(sa, dict):
        if "seeing_arcsec_500nm" in sa and sa["seeing_arcsec_500nm"] is not None:
            params["seeing"] = f'{float(sa["seeing_arcsec_500nm"]):.2f}"'
        if "star_mV" in sa and "star_mH" in sa:
            params["star_mag"] = f'mV={float(sa["star_mV"]):.1f}/mH={float(sa["star_mH"]):.1f}'
        if "physical_time_s" in sa and sa["physical_time_s"] is not None:
            params["phys_time"] = f'{float(sa["physical_time_s"]):.1f} s'
        if "oversample" in sa and sa["oversample"] is not None:
            params["oversample"] = f'{int(sa["oversample"])}x'
    if "oversample" not in params:
        ov_f = _parse_cmd_flag(cmd, "--oversample")
        if ov_f:
            params["oversample"] = f"{ov_f}x"

    bmode = _parse_cmd_flag(cmd, "--bench-mode")
    if bmode:
        params["bench_mode"] = bmode

    if isinstance(l1, dict):
        if "gain" in l1 and l1["gain"] is not None:
            params["gain1"] = f'{float(l1["gain"]):.2f}'
        if "mult" in l1 and l1["mult"] is not None:
            params["mult1"] = f'{float(l1["mult"]):.2f}'
        if "mgain_alpha" in l1 and l1["mgain_alpha"] is not None:
            params["mgain_alpha"] = f'{float(l1["mgain_alpha"]):.2f}'
        if "mgain_floor" in l1 and l1["mgain_floor"] is not None:
            params["mgain_floor"] = f'{float(l1["mgain_floor"]):.2f}'
        if "mgain_tt_factor" in l1 and l1["mgain_tt_factor"] is not None:
            params["mgain_tt"] = f'{float(l1["mgain_tt_factor"]):.2f}'
        if "svdlim" in l1 and l1["svdlim"] is not None:
            params["svdlim1"] = f'{float(l1["svdlim"]):g}'
    if isinstance(l2, dict):
        if "gain" in l2 and l2["gain"] is not None:
            params["gain2"] = f'{float(l2["gain"]):.2f}'
        if "mult" in l2 and l2["mult"] is not None:
            params["mult2"] = f'{float(l2["mult"]):.2f}'
        if "svdlim" in l2 and l2["svdlim"] is not None:
            params["svdlim2"] = f'{float(l2["svdlim"]):g}'
    if isinstance(l3, dict) and lo_closed is not False:
        if "gain" in l3 and l3["gain"] is not None:
            params["gain3"] = f'{float(l3["gain"]):.2f}'
        if "mult" in l3 and l3["mult"] is not None:
            params["mult3"] = f'{float(l3["mult"]):.3f}'
        if "svdlim" in l3 and l3["svdlim"] is not None:
            params["svdlim3"] = f'{float(l3["svdlim"]):g}'

    tlm_mode = None
    if isinstance(repro, dict) and repro.get("telemetry_mode"):
        tlm_mode = str(repro["telemetry_mode"])
    else:
        tlm_mode = _parse_cmd_flag(cmd, "--save-telemetry")
    if tlm_mode:
        params["telemetry"] = tlm_mode

    return params


def _resolve_run_parameters(meta: dict[str, object]) -> dict[str, str]:
    """Return normalized parameter dict for a staged report meta (with legacy fallback)."""
    raw_p = meta.get("parameters")
    if isinstance(raw_p, dict) and raw_p:
        return {str(k): str(v) for k, v in raw_p.items() if v is not None}

    params: dict[str, str] = {}
    cmp_d = meta.get("comparison")
    if isinstance(cmp_d, dict):
        pc_on = bool(cmp_d.get("predictive_enabled", False))
        p_ord = int(cmp_d.get("pf_order", 8)) if pc_on else 0
        params["control_law"] = (
            f"PSOL AR({p_ord}) Predictive" if pc_on else "Modal Integrator"
        )
        if cmp_d.get("has_coro", "llowfs_closed" in cmp_d):
            params["llowfs"] = "CLOSED" if cmp_d.get("llowfs_closed", True) else "OPEN"
        c2d_on = bool(cmp_d.get("calib_2wfs1dm_enabled", False))
        if c2d_on:
            db = int(cmp_d.get("calib_2wfs1dm_dim_b", 40))
            wo = int(cmp_d.get("calib_2wfs1dm_whiten_order", 4))
            params["calib_2wfs1dm"] = f"ON ({db}m, AR({wo}))"
        else:
            params["calib_2wfs1dm"] = "OFF"
    repro = meta.get("reproducibility")
    cmd = str(repro.get("run_command", "")) if isinstance(repro, dict) else ""
    flag_map = (
        ("seeing", "--seeing", lambda s: f'{float(s):.2f}"'),
        ("phys_time", "--phys-time", lambda s: f"{float(s):.1f} s"),
        ("oversample", "--oversample", lambda s: f"{int(s)}x"),
        ("bench_mode", "--bench-mode", str),
        ("gain1", "--gain1", lambda s: f"{float(s):.2f}"),
        ("gain2", "--gain2", lambda s: f"{float(s):.2f}"),
        ("mult1", "--mult1", lambda s: f"{float(s):.2f}"),
        ("mult2", "--mult2", lambda s: f"{float(s):.2f}"),
        ("mgain_alpha", "--mgain-alpha", lambda s: f"{float(s):.2f}"),
        ("mgain_floor", "--mgain-floor", lambda s: f"{float(s):.2f}"),
        ("mgain_tt", "--mgain-tt", lambda s: f"{float(s):.2f}"),
        ("svdlim1", "--svdlim1", lambda s: f"{float(s):g}"),
        ("svdlim2", "--svdlim2", lambda s: f"{float(s):g}"),
        ("telemetry", "--save-telemetry", str),
    )
    for key, flag, fmt in flag_map:
        val = _parse_cmd_flag(cmd, flag)
        if val is not None:
            try:
                params[key] = fmt(val)
            except ValueError:
                params[key] = val
    return params


def extract_metrics_highlights(
    out_slug_dir: Path,
) -> tuple[
    list[str],
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, str],
]:
    """Extract badges, reproducibility, comparison stats, and normalized run parameters."""
    cands = [out_slug_dir / "ao3k_scexao_metrics.json"]
    cands.extend(sorted(out_slug_dir.glob("*_metrics.json")))
    metrics_path = next((p for p in cands if p.is_file()), None)
    if metrics_path is None:
        return [], None, None, {}
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], None, None, {}
    if not isinstance(data, dict):
        return [], None, None, {}

    badges: list[str] = []
    vis_sr_pct: float | None = None
    nir_sr_pct: float | None = None
    wfe_nm: float | None = None
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
            vis_sr_pct = float(vis_f["strehl_peak"]) * 100.0
            badges.append(f"Vis SR {vis_sr_pct:.1f}%")
        if isinstance(nir_f, dict) and "strehl_peak" in nir_f:
            nir_sr_pct = float(nir_f["strehl_peak"]) * 100.0
            badges.append(f"H SR {nir_sr_pct:.1f}%")
    stg1_wfe_nm: float | None = None
    wm = data.get("wavefront_metrics")
    if isinstance(wm, dict):
        locs = wm.get("locations")
        if isinstance(locs, dict):
            if isinstance(locs.get("stg1"), dict) and "quad_total_rms_nm" in locs["stg1"]:
                stg1_wfe_nm = float(locs["stg1"]["quad_total_rms_nm"])
            if isinstance(locs.get("final"), dict) and "quad_total_rms_nm" in locs["final"]:
                wfe_nm = float(locs["final"]["quad_total_rms_nm"])
                badges.append(f"WFE {wfe_nm:.1f} nm")

    pc = data.get("predictive_control")
    pc_on = bool(isinstance(pc, dict) and pc.get("enabled"))
    pf_mode = str(pc.get("pf_mode", "ar")).lower() if isinstance(pc, dict) and pc_on else "ar"
    pf_blocksize = int(pc.get("pf_blocksize", 128)) if isinstance(pc, dict) and pc_on else 1
    pf_order = int(pc.get("pf_order", 8)) if isinstance(pc, dict) and pc_on else 0
    pf_mix = float(pc.get("pf_mix", 0.90)) if isinstance(pc, dict) and pc_on else 0.0
    pf_vr1: float | None = None
    pf_vr2: float | None = None
    if isinstance(pc, dict) and pc_on:
        s1_pc = pc.get("stage1")
        s2_pc = pc.get("stage2")
        if isinstance(s1_pc, dict) and "var_red_pct" in s1_pc:
            pf_vr1 = float(s1_pc["var_red_pct"])
        if isinstance(s2_pc, dict) and "var_red_pct" in s2_pc:
            pf_vr2 = float(s2_pc["var_red_pct"])

    c2d = data.get("calib_2wfs1dm")
    c2d_on = bool(isinstance(c2d, dict) and c2d.get("enabled"))
    c2d_dim_b = int(c2d.get("dim_b", 40)) if isinstance(c2d, dict) and c2d_on else 0
    c2d_w_ord = int(c2d.get("whiten_order", 4)) if isinstance(c2d, dict) and c2d_on else 0
    c2d_mdb_raw = (
        c2d.get("mdb_diag_med")
        if isinstance(c2d, dict) and c2d_on and c2d.get("mdb_diag_med") is not None
        else (
            c2d.get("mdb_diag_white_med")
            if isinstance(c2d, dict) and c2d_on
            else None
        )
    )
    c2d_mdb = float(c2d_mdb_raw) if c2d_mdb_raw is not None else None
    c2d_r2a = (
        float(c2d["r2_a_raw_med"])
        if isinstance(c2d, dict) and c2d_on and c2d.get("r2_a_raw_med") is not None
        else None
    )
    c2d_srm_raw = None
    if isinstance(c2d, dict) and c2d_on:
        if c2d.get("has_selfrm", True):
            if c2d.get("selfrm_rel_err") is not None:
                c2d_srm_raw = c2d["selfrm_rel_err"]
            elif c2d.get("mdb_vs_selfrm_rel_err") is not None:
                c2d_srm_raw = c2d["mdb_vs_selfrm_rel_err"]
    c2d_srm_err = float(c2d_srm_raw) * 100.0 if c2d_srm_raw is not None else None
    c2d_eta_w = (
        float(c2d["eta_d_white_med"])
        if isinstance(c2d, dict) and c2d_on and c2d.get("eta_d_white_med") is not None
        else None
    )

    cmp_dict: dict[str, object] | None = None
    cm = data.get("coronagraph_metrics")
    has_coro = isinstance(cm, dict)
    lo_on = True
    dm3_rms_nm = 0.0
    coro_leak_pct: float | None = None
    p310_val: float | None = None
    c5_pl: float | None = None
    c5_5s: float | None = None
    lowfs_coro_pct: float | None = None
    lowfs_hpup_pct: float | None = None
    if isinstance(cm, dict):
        lo = cm.get("llowfs") if isinstance(cm.get("llowfs"), dict) else {}
        cl = cm.get("closed_loop") if isinstance(cm.get("closed_loop"), dict) else {}
        lb = cm.get("lowfs_light_budget")
        bcl = lb.get("closed_loop") if isinstance(lb, dict) else {}
        bcl = bcl if isinstance(bcl, dict) else {}
        lo_on = bool(lo.get("enabled_closed_loop", True))
        dm3_rms_nm = float(lo.get("dm3_stroke_rms_nm", 0.0))
        badges.insert(0, "LLOWFS CLOSED" if lo_on else "LLOWFS OPEN")
        if "mean_planet_contrast_3_10ld" in cl:
            p310_val = float(cl["mean_planet_contrast_3_10ld"])
            badges.append(f"Coro 3-10 l/D {p310_val:.2e}")
        if "total_leakage_frac" in cl:
            coro_leak_pct = float(cl["total_leakage_frac"]) * 100.0
        if "frac_coro_in_reaching_lowfs_cam_fov" in bcl:
            lowfs_coro_pct = float(bcl["frac_coro_in_reaching_lowfs_cam_fov"]) * 100.0
            badges.append(f"LOWFS Light {lowfs_coro_pct:.2f}%")
        if "frac_entrance_pup_h_reaching_lowfs_cam_fov" in bcl:
            lowfs_hpup_pct = float(bcl["frac_entrance_pup_h_reaching_lowfs_cam_fov"]) * 100.0

        ctbl = cm.get("contrast_table")
        if isinstance(ctbl, list):
            for row in ctbl:
                if isinstance(row, dict) and abs(float(row.get("sep_ld", 0.0)) - 5.0) < 0.5:
                    c5_pl = float(row.get("cl_planet_contrast", 0.0))
                    c5_5s = float(row.get("cl_5sigma_planet_contrast", 0.0))
                    break

    if c2d_on:
        badges.insert(0, "2-WFS/1-DM CALIB")
        if c2d_mdb is not None:
            badges.append(f"Mdb {c2d_mdb:.2f}")
        if c2d_r2a is not None:
            badges.append(f"R2_A {c2d_r2a:.2f}")
    if pc_on:
        if pf_mode == "eof":
            badges.insert(0, f"PSOL BLOCK-EOF(B={pf_blocksize}, P={pf_order})")
        else:
            badges.insert(0, f"PSOL AR({pf_order}) PREDICTIVE")

    if any(
        v is not None
        for v in (vis_sr_pct, nir_sr_pct, stg1_wfe_nm, wfe_nm)
    ) or has_coro or pc_on or c2d_on:
        cmp_dict = {
            "has_coro": has_coro,
            "predictive_enabled": pc_on,
            "pf_mode": pf_mode,
            "pf_blocksize": pf_blocksize,
            "pf_order": pf_order,
            "pf_mix": pf_mix,
            "pf_var_red_stg1_pct": pf_vr1,
            "pf_var_red_stg2_pct": pf_vr2,
            "llowfs_closed": lo_on,
            "dm3_rms_nm": dm3_rms_nm,
            "vis_sr_pct": vis_sr_pct,
            "nir_sr_pct": nir_sr_pct,
            "stg1_wfe_nm": stg1_wfe_nm,
            "wfe_nm": wfe_nm,
            "coro_leak_pct": coro_leak_pct,
            "planet_contrast_3_10ld": p310_val,
            "planet_contrast_5ld": c5_pl,
            "speckle_5sig_5ld": c5_5s,
            "lowfs_cam_coro_pct": lowfs_coro_pct,
            "lowfs_cam_hpup_pct": lowfs_hpup_pct,
            "calib_2wfs1dm_enabled": c2d_on,
            "calib_2wfs1dm_dim_b": c2d_dim_b,
            "calib_2wfs1dm_whiten_order": c2d_w_ord,
            "calib_2wfs1dm_mdb_diag": c2d_mdb,
            "calib_2wfs1dm_r2_a": c2d_r2a,
            "calib_2wfs1dm_selfrm_err_pct": c2d_srm_err,
            "calib_2wfs1dm_eta_white": c2d_eta_w,
        }

    repro = data.get("reproducibility")
    repro_dict = repro if isinstance(repro, dict) else None
    params_dict = extract_run_parameters(data)
    return badges, repro_dict, cmp_dict, params_dict


def _meta_sort_key(meta: dict[str, object]) -> tuple[int, int, str]:
    if meta.get("report_type") == "study":
        return (-1, 0, str(meta.get("slug", "")))
    cmp_d = meta.get("comparison")
    slug = str(meta.get("slug", ""))
    if isinstance(cmp_d, dict):
        has_coro = bool(cmp_d.get("has_coro", "llowfs_closed" in cmp_d))
        lo_on = bool(cmp_d.get("llowfs_closed", True)) if has_coro else True
        pc_on = bool(cmp_d.get("predictive_enabled", False))
        c2d_on = bool(cmp_d.get("calib_2wfs1dm_enabled", False))
        p_ord = int(cmp_d.get("pf_order", 0) or 0)
        p_mode = str(cmp_d.get("pf_mode", "ar")).lower()
        p_blk = int(cmp_d.get("pf_blocksize", 1) or 1)
        if not lo_on:
            tier = 0
        elif not pc_on and not c2d_on:
            tier = 1
        elif pc_on and not c2d_on:
            tier = 2
            if p_mode == "eof":
                return (tier, 200 + p_blk, slug)
            if "w14s" in slug:
                return (tier, 100 + p_ord, slug)
        else:
            tier = 3
        return (tier, p_ord, slug)
    return (4, 0, slug)


def _format_param_pill(
    key: str,
    label: str,
    val: str,
    is_diff: bool,
    cmp_d: dict[str, object] | None,
) -> str:
    """Format a single parameter key=value pill for the Front Page table."""
    lbl_esc = html.escape(label, quote=False)
    val_esc = html.escape(val, quote=False)
    cls = "param-pill param-pill-diff" if is_diff else "param-pill"

    if key == "control_law":
        if val.startswith("PSOL "):
            v_html = f"<strong>{val_esc}</strong>"
        else:
            v_html = val_esc
        return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'
    if key == "llowfs":
        if val == "CLOSED":
            dm3 = float((cmp_d or {}).get("dm3_rms_nm") or 0.0)
            extra = f" (<code>{dm3:.1f} nm</code>)" if dm3 > 0.0 else ""
            v_html = f"<strong>CLOSED</strong>{extra}"
        else:
            v_html = "OPEN (<code>--no-lowfs</code>)"
        return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'
    if key == "calib_2wfs1dm":
        if val.startswith("ON"):
            rest = val[2:].strip()
            extra = f" <code>{html.escape(rest, quote=False)}</code>" if rest else ""
            v_html = f"<strong>ON</strong>{extra}"
        else:
            v_html = val_esc
        return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'

    v_html = f"<strong><code>{val_esc}</code></strong>" if is_diff else f"<code>{val_esc}</code>"
    return f'<span class="{cls}">{lbl_esc}: {v_html}</span>'


def build_front_page_html(metas: list[dict[str, object]]) -> str:
    """Render the root Front Page with intro, report cards, GitHub repos, and CLI recipe."""
    metas = sorted(metas, key=_meta_sort_key)
    latest_repro: dict[str, object] | None = None
    primary_slug = ""
    for meta in metas:
        if meta.get("report_type") == "study":
            continue
        if not primary_slug:
            primary_slug = str(meta.get("slug", ""))
        rep = meta.get("reproducibility")
        if isinstance(rep, dict) and rep.get("repositories"):
            latest_repro = rep
            primary_slug = str(meta.get("slug", primary_slug))
    if not latest_repro:
        for meta in metas:
            rep = meta.get("reproducibility")
            if isinstance(rep, dict) and rep.get("repositories"):
                latest_repro = rep
                if not primary_slug:
                    primary_slug = str(meta.get("slug", ""))

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

    study_metas = [m for m in metas if m.get("report_type") == "study"]
    run_metas = [m for m in metas if m.get("report_type") != "study"]

    featured_html = ""
    study_nav_links: list[str] = []
    if study_metas:
        f_blocks: list[str] = ['<h2 id="featured-reports">Featured Technical Reports</h2>']
        for meta in study_metas:
            slug = str(meta.get("slug", ""))
            title = str(meta.get("title", slug))
            summary_txt = str(meta.get("summary", ""))
            nav_lbl = str(meta.get("nav_label", title))
            btn_lbl = str(meta.get("button_label", "Read Technical Report"))
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
            nav_esc = html.escape(nav_lbl, quote=False)
            btn_esc = html.escape(btn_lbl, quote=False)
            study_nav_links.append(f'<a href="./{slug_esc}/index.html">{nav_esc}</a>')
            repro_link = (
                f"./{slug_esc}/index.html#reproducibility-github-provenance"
                if has_repro
                else "#reproduce-results"
            )
            sum_html = (
                f'  <p class="study-summary">{html.escape(summary_txt, quote=False)}</p>\n'
                if summary_txt
                else ""
            )
            f_blocks.append(
                '<div class="study-card">\n'
                f"  <h3>{title_esc}</h3>\n"
                f"{sum_html}"
                f"{badge_html}"
                f'  <p class="muted"><code>{html.escape(slug, quote=False)}</code> &middot; '
                f"{nfiles} files ({sz}) &middot; Updated {html.escape(upd, quote=False)}</p>\n"
                f'  <div class="card-links">'
                f'<a class="btn" href="./{slug_esc}/index.html">{btn_esc}</a>'
                f'<a class="btn btn-secondary" href="{repro_link}">Reproduce</a>'
                "</div>\n"
                "</div>"
            )
        featured_html = "\n".join(f_blocks) + "\n"

    cards: list[str] = ['<div class="report-card-grid">']
    for meta in run_metas:
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

    cmp_metas = [m for m in metas if isinstance(m.get("comparison"), dict)]
    cmp_html = ""
    if len(cmp_metas) >= 2:
        param_dicts = [_resolve_run_parameters(m) for m in cmp_metas]
        changed_specs: list[tuple[str, str]] = []
        shared_items: list[tuple[str, str]] = []
        for pkey, plabel in TRACKED_PARAMS:
            present = [pd[pkey] for pd in param_dicts if pkey in pd]
            if len(set(present)) >= 2:
                changed_specs.append((pkey, plabel))
            elif len(present) == len(cmp_metas) and len(set(present)) == 1:
                shared_items.append((plabel, present[0]))

        ref_vals: dict[str, str] = {}
        for pkey, _ in changed_specs:
            ref_v = param_dicts[0].get(pkey)
            if ref_v is None:
                ref_v = next((pd[pkey] for pd in param_dicts if pkey in pd), "")
            ref_vals[pkey] = ref_v

        has_any_pred = any(
            bool((m.get("comparison") or {}).get("predictive_enabled", False))
            for m in cmp_metas
            if isinstance(m.get("comparison"), dict)
        )
        has_any_c2d = any(
            bool((m.get("comparison") or {}).get("calib_2wfs1dm_enabled", False))
            for m in cmp_metas
            if isinstance(m.get("comparison"), dict)
        )
        has_any_coro = any(
            bool((m.get("comparison") or {}).get("has_coro", False))
            for m in cmp_metas
            if isinstance(m.get("comparison"), dict)
        )
        has_any_s1wfe = any(
            (m.get("comparison") or {}).get("stg1_wfe_nm") is not None
            for m in cmp_metas
            if isinstance(m.get("comparison"), dict)
        )
        has_any_wfe = any(
            (m.get("comparison") or {}).get("wfe_nm") is not None
            for m in cmp_metas
            if isinstance(m.get("comparison"), dict)
        )
        has_any_vsr = any(
            (m.get("comparison") or {}).get("vis_sr_pct") is not None
            for m in cmp_metas
            if isinstance(m.get("comparison"), dict)
        )
        has_any_nsr = any(
            (m.get("comparison") or {}).get("nir_sr_pct") is not None
            for m in cmp_metas
            if isinstance(m.get("comparison"), dict)
        )

        if has_any_pred and has_any_c2d:
            cmp_heading = (
                "Side-by-Side Benchmark Comparison "
                "(Open LLOWFS vs. Closed LLOWFS vs. PSOL Predictive Control "
                "&amp; 2-WFS/1-DM Telemetry Calibration)"
            )
        elif has_any_pred:
            cmp_heading = (
                "Side-by-Side Benchmark Comparison "
                "(Open LLOWFS vs. Closed LLOWFS vs. PSOL Predictive Control)"
            )
        elif has_any_coro:
            cmp_heading = "Side-by-Side Comparison (Stage-3 LLOWFS Closed vs. Open)"
        else:
            cmp_heading = "Simulation Runs Comparison"

        hdr_cells = [
            '<th style="text-align: left;">Simulation</th>',
            '<th style="text-align: left;">Changed Parameters</th>',
        ]
        if has_any_s1wfe:
            hdr_cells.append('<th style="text-align: right;">Post-AO3k WFE</th>')
        if has_any_wfe:
            hdr_cells.append('<th style="text-align: right;">Post-SCExAO WFE</th>')
        if has_any_vsr:
            hdr_cells.append('<th style="text-align: right;">Vis 0.75 um SR</th>')
        if has_any_nsr:
            hdr_cells.append('<th style="text-align: right;">H 1.65 um SR</th>')
        if has_any_coro:
            hdr_cells.extend(
                [
                    '<th style="text-align: right;">Coro Leakage</th>',
                    '<th style="text-align: right;">Planet 3-10 l/D</th>',
                    '<th style="text-align: right;">5-sig @ 5 l/D</th>',
                ]
            )
        if has_any_c2d:
            hdr_cells.append('<th style="text-align: right;">2-WFS/1-DM Calib</th>')

        crows: list[str] = [
            f"\n<h3>{cmp_heading}</h3>",
            '<div class="table-wrap">',
            "<table>",
            f'<thead><tr>{"".join(hdr_cells)}</tr></thead>',
            "<tbody>",
        ]
        compact_diff_only = len(changed_specs) > 4
        for row_idx, (m, pd) in enumerate(zip(cmp_metas, param_dicts)):
            c = m["comparison"]
            assert isinstance(c, dict)
            mslug = html.escape(str(m.get("slug", "")), quote=True)
            mslug_lbl = html.escape(str(m.get("slug", "")), quote=False)

            if not changed_specs:
                param_cell_html = '<span class="muted">Identical parameters</span>'
            else:
                pills_out: list[str] = []
                if compact_diff_only and row_idx == 0:
                    pills_out.append('<span class="param-pill param-pill-base">Baseline</span>')
                for pkey, plabel in changed_specs:
                    if pkey not in pd:
                        continue
                    val = pd[pkey]
                    is_diff = val != ref_vals.get(pkey)
                    if compact_diff_only and row_idx > 0 and not is_diff:
                        continue
                    pills_out.append(_format_param_pill(pkey, plabel, val, is_diff, c))
                if not pills_out:
                    pills_out.append(
                        '<span class="param-pill param-pill-base">Same as baseline</span>'
                    )
                param_cell_html = f'<div class="param-list">{"".join(pills_out)}</div>'

            row_cells = [
                f'<td><a href="./{mslug}/index.html"><code>{mslug_lbl}</code></a></td>',
                f'<td class="param-cell">{param_cell_html}</td>',
            ]
            if has_any_s1wfe:
                s1_wfe_s = (
                    f'<code>{float(c["stg1_wfe_nm"]):.1f} nm</code>'
                    if c.get("stg1_wfe_nm") is not None
                    else "&mdash;"
                )
                row_cells.append(f'<td style="text-align: right;">{s1_wfe_s}</td>')
            if has_any_wfe:
                wfe_s = (
                    f'<code>{float(c["wfe_nm"]):.1f} nm</code>'
                    if c.get("wfe_nm") is not None
                    else "&mdash;"
                )
                row_cells.append(f'<td style="text-align: right;">{wfe_s}</td>')
            if has_any_vsr:
                vsr_s = (
                    f'<code>{float(c["vis_sr_pct"]):.1f}%</code>'
                    if c.get("vis_sr_pct") is not None
                    else "&mdash;"
                )
                row_cells.append(f'<td style="text-align: right;">{vsr_s}</td>')
            if has_any_nsr:
                nsr_s = (
                    f'<strong><code>{float(c["nir_sr_pct"]):.1f}%</code></strong>'
                    if c.get("nir_sr_pct") is not None
                    else "&mdash;"
                )
                row_cells.append(f'<td style="text-align: right;">{nsr_s}</td>')
            if has_any_coro:
                leak_s = (
                    f'<code>{float(c["coro_leak_pct"]):.2f}%</code>'
                    if c.get("coro_leak_pct") is not None
                    else "&mdash;"
                )
                p310_s = (
                    f'<code>{float(c["planet_contrast_3_10ld"]):.2e}</code>'
                    if c.get("planet_contrast_3_10ld") is not None
                    else "&mdash;"
                )
                s5_s = (
                    f'<code>{float(c["speckle_5sig_5ld"]):.2e}</code>'
                    if c.get("speckle_5sig_5ld") is not None
                    else "&mdash;"
                )
                row_cells.extend(
                    [
                        f'<td style="text-align: right;">{leak_s}</td>',
                        f'<td style="text-align: right;">{p310_s}</td>',
                        f'<td style="text-align: right;">{s5_s}</td>',
                    ]
                )
            if has_any_c2d:
                if c.get("calib_2wfs1dm_enabled"):
                    c2d_parts: list[str] = []
                    if c.get("calib_2wfs1dm_mdb_diag") is not None:
                        mdb_s = f'<code>Mdb={float(c["calib_2wfs1dm_mdb_diag"]):.2f}</code>'
                        if c.get("calib_2wfs1dm_selfrm_err_pct") is not None:
                            mdb_s += (
                                f' ({float(c["calib_2wfs1dm_selfrm_err_pct"]):.1f}% selfRM)'
                            )
                        c2d_parts.append(mdb_s)
                    if c.get("calib_2wfs1dm_r2_a") is not None:
                        c2d_parts.append(f'<code>R&sup2;_A={float(c["calib_2wfs1dm_r2_a"]):.2f}</code>')
                    c2d_cell = ", ".join(c2d_parts) if c2d_parts else "<strong>ON</strong>"
                else:
                    c2d_cell = "&mdash;"
                row_cells.append(f'<td style="text-align: right;">{c2d_cell}</td>')

            crows.append(f'<tr>{"".join(row_cells)}</tr>')
        crows.extend(["</tbody>", "</table>", "</div>"])
        if shared_items:
            shared_html = " &middot; ".join(
                f"{html.escape(lbl, quote=False)}=<code>{html.escape(val, quote=False)}</code>"
                for lbl, val in shared_items
            )
            crows.append(
                f'<div class="shared-params"><strong>Shared parameters across all '
                f"{len(cmp_metas)} runs:</strong> {shared_html}</div>"
            )
        cmp_html = "\n".join(crows)

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
            *(
                [
                    str((m.get("reproducibility") or {}).get("run_command", run_cmd))
                    for m in run_metas
                    if isinstance(m.get("reproducibility"), dict)
                    and (m.get("reproducibility") or {}).get("run_command")
                ]
                if len(run_metas) >= 2
                and any(
                    isinstance(m.get("reproducibility"), dict)
                    and (m.get("reproducibility") or {}).get("run_command")
                    for m in run_metas
                )
                else [run_cmd]
            ),
            *(
                ["", "# 3b. Compile comparative Predictive Control Report",
                 "${PYTHON_BIN} ./scripts/build-predictive-control-report.py"]
                if any(m.get("slug") == "predictive_control_report" for m in study_metas)
                else []
            ),
            "",
            "# 4. Stage static HTML website locally under _work/_web_site/public/",
            *(
                [
                    f"./scripts/publish-ao-report.sh --build-only _work/{m.get('slug')}"
                    for m in metas
                    if m.get("slug")
                ]
                if len(metas) >= 2
                else [f"./scripts/publish-ao-report.sh --build-only _work/{stage_slug}"]
            ),
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
        + featured_html
        + '<h2 id="published-reports">Published Simulation Reports</h2>\n'
        + "\n".join(cards)
        + cmp_html
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
      {"".join(study_nav_links)}
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
                    {"key": "Cache-Control", "value": "no-cache"}
                ],
            },
            {
                "source": "**/*.@(html|json|csv|tsv|txt|dat|bench)",
                "headers": [
                    {"key": "Cache-Control", "value": "no-cache"}
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

    study_meta_path = out_slug_dir / "study_meta.json"
    study_meta: dict[str, object] = {}
    if study_meta_path.is_file():
        try:
            loaded = json.loads(study_meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                study_meta = loaded
        except (OSError, json.JSONDecodeError):
            study_meta = {}

    primary_nav_label = str(study_meta.get("nav_label") or "Optical & Control Report")
    index_html = render_page_shell(
        title=report_title,
        slug=slug,
        active_page="optical",
        has_compute_report=has_compute,
        has_repro_section=has_repro_section,
        body_html=full_report_body,
        has_mermaid=report_mermaid,
        updated_utc=updated_utc,
        primary_nav_label=primary_nav_label,
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
            primary_nav_label=primary_nav_label,
        )
        (out_slug_dir / "compute_report.html").write_text(
            compute_html, encoding="utf-8"
        )
        (out_slug_dir / "compute.html").write_text(
            compute_html, encoding="utf-8"
        )

    badges, repro_dict, cmp_dict, params_dict = extract_metrics_highlights(out_slug_dir)
    if not badges and isinstance(study_meta.get("badges"), list):
        badges = [str(b) for b in study_meta["badges"]]
    if repro_dict is None and isinstance(study_meta.get("reproducibility"), dict):
        repro_dict = study_meta["reproducibility"]

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
    for skey in ("report_type", "nav_label", "button_label", "summary"):
        if study_meta.get(skey):
            meta[skey] = str(study_meta[skey])
    if repro_dict is not None:
        meta["reproducibility"] = repro_dict
    if cmp_dict is not None:
        meta["comparison"] = cmp_dict
    if params_dict:
        meta["parameters"] = params_dict
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
