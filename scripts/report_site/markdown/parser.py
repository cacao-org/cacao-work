#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Pure-stdlib GFM Markdown parser and HTML fragment renderer."""

from __future__ import annotations

import html
from pathlib import Path
import re

from ..constants import IMAGE_EXTS, VIDEO_EXTS, friendly_figure_caption
from .context import RenderContext

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
    cap_txt = alt or friendly_figure_caption(Path(path_only).name)
    cap_esc = html.escape(cap_txt, quote=False)
    cap_attr = html.escape(cap_txt, quote=True)
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
            "  <video controls loop autoplay muted playsinline "
            f'preload="metadata"{poster_attr}>\n'
            f'    <source src="{src_esc}" type="{mime}">\n'
            "  </video>\n"
            f'  <figcaption>{cap_esc} &middot; '
            f'<a href="{src_esc}" download>Download {fmt_lbl}</a></figcaption>\n'
            "</figure>"
        )
    return (
        '<figure class="report-figure">\n'
        f'  <a href="{src_esc}" class="lightbox-trigger" '
        f'data-caption="{cap_attr}" target="_blank" rel="noopener">'
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
                    '<div class="mermaid-wrap">\n'
                    f'<pre class="mermaid">{code_esc}</pre>\n'
                    "</div>"
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
            tbl = ['<div class="table-wrap" data-sortable="1">', "<table>", "<thead>", "<tr>"]
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
