#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Compatibility re-export shim for report_site.markdown."""

from __future__ import annotations

from .markdown import (  # noqa: F401
    RenderContext,
    apply_emph,
    convert_markdown_to_html,
    extract_toc_html,
    extract_toc_items,
    is_table_start,
    parse_alignments,
    render_figure_block,
    render_inline,
    slugify_heading,
    split_simulation_markdown,
    split_table_row,
)
