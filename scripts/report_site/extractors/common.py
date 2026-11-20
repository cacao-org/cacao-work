#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared utility helpers for metadata, JSON loading, and sorting."""

from __future__ import annotations

import json
from pathlib import Path
import re

REL_SIBLING_RE = re.compile(r"\(\.\./([A-Za-z0-9_.-]+)/(?:[A-Za-z0-9_.-]+\.html)?\)")


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


def _parse_cmd_flag(cmd: str, flag: str) -> str | None:
    """Extract the value following a CLI --flag token in a saved run_command string."""
    if not cmd:
        return None
    m = re.search(rf"(?:^|\s){re.escape(flag)}\s+(\S+)", cmd)
    return m.group(1) if m else None


def load_json_safe(path: Path) -> dict[str, object]:
    """Read a JSON object safely, returning {} on error or non-dict payload."""
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def find_metrics_path(out_slug_dir: Path) -> Path | None:
    """Find ao3k_scexao_metrics.json or any *_metrics.json file in out_slug_dir."""
    cands = [out_slug_dir / "ao3k_scexao_metrics.json"]
    cands.extend(sorted(out_slug_dir.glob("*_metrics.json")))
    return next((p for p in cands if p.is_file()), None)


def is_tech_report_meta(meta: dict[str, object]) -> bool:
    """Return True for tech reports (supporting legacy 'study' report_type)."""
    return str(meta.get("report_type", "")) in ("study", "tech_report")


def meta_sort_key(meta: dict[str, object]) -> tuple[int, int, str]:
    """Deterministic ordering for tech reports and simulation runs."""
    if is_tech_report_meta(meta):
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
