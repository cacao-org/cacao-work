#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation REPORT.md section splitter and HTML heading TOC extraction."""

from __future__ import annotations

import html
import re

from .parser import FENCE_OPEN_RE

H_TAG_RE = re.compile(r'<h([23])\s+id="([^"]+)">(.*?)</h\1>', re.DOTALL)


def split_simulation_markdown(md_text: str) -> dict[str, str]:
    """Split simulation REPORT.md into title, preamble, config, optical, and repro."""
    lines = md_text.splitlines()
    title = ""
    preamble_lines: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    cur_h2: str | None = None
    cur_lines: list[str] = []
    in_fence = False

    for line in lines:
        if FENCE_OPEN_RE.match(line.strip()) or (in_fence and line.strip().startswith("```")):
            in_fence = not in_fence
        if not in_fence and line.startswith("# ") and not title:
            title = re.sub(r"`([^`]*)`", r"\1", line[2:].strip())
            continue
        if not in_fence and line.startswith("## "):
            if cur_h2 is not None:
                sections.append((cur_h2, cur_lines))
            cur_h2 = line[3:].strip()
            cur_lines = [line]
        elif cur_h2 is None:
            preamble_lines.append(line)
        else:
            cur_lines.append(line)

    if cur_h2 is not None:
        sections.append((cur_h2, cur_lines))

    config_parts: list[str] = []
    gui_parts: list[str] = []
    optical_parts: list[str] = []
    repro_parts: list[str] = []

    for h2_title, sec_lines in sections:
        low = h2_title.lower()
        if "optical bench" in low or "polychromatic passbands" in low:
            config_parts.append("\n".join(sec_lines).strip())
        elif "reproducibility" in low:
            repro_parts.append("\n".join(sec_lines).strip())
        elif low == "figures":
            sub_pre: list[str] = []
            sub_groups: list[tuple[str, list[str]]] = []
            cur_h3: str | None = None
            cur_sub: list[str] = []
            sub_fence = False
            for sl in sec_lines[1:]:
                if FENCE_OPEN_RE.match(sl.strip()) or (
                    sub_fence and sl.strip().startswith("```")
                ):
                    sub_fence = not sub_fence
                if not sub_fence and sl.startswith("### "):
                    if cur_h3 is not None:
                        sub_groups.append((cur_h3, cur_sub))
                    cur_h3 = sl[4:].strip()
                    cur_sub = [sl]
                elif cur_h3 is None:
                    sub_pre.append(sl)
                else:
                    cur_sub.append(sl)
            if cur_h3 is not None:
                sub_groups.append((cur_h3, cur_sub))

            opt_figs: list[str] = ["## Figures", *sub_pre]
            for h3_title, h3_lines in sub_groups:
                if "hardware simulator gui" in h3_title.lower():
                    gui_parts.append("\n".join(h3_lines).strip())
                else:
                    opt_figs.extend(["", *h3_lines])
            if len(opt_figs) > 1 and any(x.strip() for x in opt_figs[1:]):
                optical_parts.append("\n".join(opt_figs).strip())
        else:
            optical_parts.append("\n".join(sec_lines).strip())

    preamble_text = "\n".join(preamble_lines).strip()
    if not optical_parts and preamble_text:
        optical_parts.append(preamble_text)

    return {
        "title": title,
        "preamble": preamble_text,
        "config": "\n\n".join(p for p in config_parts if p),
        "gui_md": "\n\n".join(p for p in gui_parts if p),
        "optical": "\n\n".join(p for p in optical_parts if p),
        "repro": "\n\n".join(p for p in repro_parts if p),
    }


def extract_toc_items(body_html: str) -> list[tuple[str, str]]:
    """Extract ordered (heading_id, label) pairs for all <h2> headings in body_html."""
    items: list[tuple[str, str]] = []
    for match in H_TAG_RE.finditer(body_html):
        lvl, hid, inner = match.groups()
        if lvl != "2":
            continue
        stripped = re.sub(
            r'<small class="section-cat-badges">.*?</small>',
            "",
            inner,
            flags=re.DOTALL,
        )
        plain = html.unescape(re.sub(r"<[^>]+>", "", stripped)).strip()
        if plain:
            items.append((hid, plain))
    return items


def extract_toc_html(body_html: str, title: str = "On This Page") -> str:
    """Build a compact inline Table of Contents bar from <h2> headings."""
    items = extract_toc_items(body_html)
    if len(items) < 2:
        return ""
    links = "".join(
        f'<a class="toc-chip" href="#{html.escape(hid, quote=True)}">'
        f"{html.escape(lbl, quote=False)}</a>"
        for hid, lbl in items
    )
    return (
        '<nav class="toc-bar" aria-label="Section navigation">'
        f'<span class="toc-label">{html.escape(title, quote=False)}:</span>'
        f"{links}</nav>"
    )
