#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Pure-stdlib GFM Markdown parser, section splitter, and TOC extractor."""

from __future__ import annotations

from .context import RenderContext
from .parser import (
    apply_emph,
    convert_markdown_to_html,
    is_table_start,
    parse_alignments,
    render_figure_block,
    render_inline,
    slugify_heading,
    split_table_row,
)
from .sim_split import extract_toc_html, extract_toc_items, split_simulation_markdown

__all__ = [
    "RenderContext",
    "apply_emph",
    "convert_markdown_to_html",
    "extract_toc_html",
    "extract_toc_items",
    "is_table_start",
    "parse_alignments",
    "render_figure_block",
    "render_inline",
    "slugify_heading",
    "split_simulation_markdown",
    "split_table_row",
]
