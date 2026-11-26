#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared utility helpers for metadata, JSON loading, and sorting."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

REL_SIBLING_RE = re.compile(r"\(\.\./([A-Za-z0-9_.-]+)/(?:[A-Za-z0-9_.-]+\.html)?\)")

SIM_DATE_PRIMARY_FILES: tuple[str, ...] = (
    "wf_stats.json",
    "wf_timeseries.csv",
    "strehl_timeseries.csv",
    "ao3k_scexao.bench",
    "compute_telemetry.json",
    "compute_perf_metrics.json",
    "pf_stats.json",
)

_EXPLICIT_DATE_KEYS: tuple[str, ...] = (
    "simulation_utc",
    "simulation_iso",
    "run_utc",
    "simulation_date",
    "generated_utc",
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


def format_utc_timestamp(epoch: float) -> tuple[str, str, float]:
    """Format a Unix epoch timestamp into (display_utc, iso_utc, epoch)."""
    ep = round(float(epoch), 3)
    dt = datetime.fromtimestamp(ep, timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC"), dt.strftime("%Y-%m-%dT%H:%M:%SZ"), ep


def parse_utc_timestamp(raw: object) -> tuple[str, str, float] | None:
    """Parse an ISO-8601, 'YYYY-MM-DD HH:MM UTC', or numeric epoch into UTC strings + epoch."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if float(raw) > 0.0:
            return format_utc_timestamp(float(raw))
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    iso_cand = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso_cand)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return format_utc_timestamp(dt.timestamp())
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S UTC",
        "%Y-%m-%d %H:%M UTC",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return format_utc_timestamp(dt.timestamp())
        except ValueError:
            continue
    return None


def extract_simulation_timestamp(
    report_dir: Path | None,
    out_slug_dir: Path | None,
    *,
    metrics_data: dict[str, object] | None = None,
    run_options: dict[str, object] | None = None,
) -> tuple[str, str, float]:
    """Resolve the true simulation run timestamp, avoiding post-hoc report/web rebuild times."""
    dicts_to_check: list[dict[str, object]] = []
    if isinstance(run_options, dict):
        dicts_to_check.append(run_options)
    if isinstance(metrics_data, dict):
        dicts_to_check.append(metrics_data)
        repro = metrics_data.get("reproducibility")
        if isinstance(repro, dict):
            dicts_to_check.append(repro)

    for src_d in dicts_to_check:
        for key in _EXPLICIT_DATE_KEYS:
            parsed = parse_utc_timestamp(src_d.get(key))
            if parsed is not None:
                return parsed

    search_dirs = [d for d in (report_dir, out_slug_dir) if d is not None and d.is_dir()]
    for d in search_dirs:
        for fname in SIM_DATE_PRIMARY_FILES:
            cand = d / fname
            if cand.is_file():
                try:
                    return format_utc_timestamp(cand.stat().st_mtime)
                except OSError:
                    continue
        for bench in sorted(d.glob("*.bench")):
            if bench.is_file() and bench.name != "csim_active.bench":
                try:
                    return format_utc_timestamp(bench.stat().st_mtime)
                except OSError:
                    continue

    for d in search_dirs:
        fallbacks: list[Path] = []
        mpath = find_metrics_path(d)
        if mpath is not None:
            fallbacks.append(mpath)
        fallbacks.extend([d / "REPORT.md", d / "run_options.json"])
        for cand in fallbacks:
            if cand.is_file():
                try:
                    return format_utc_timestamp(cand.stat().st_mtime)
                except OSError:
                    continue
    return "", "", 0.0


def simulation_sort_epoch(meta: dict[str, object]) -> float:
    """Return numeric UTC epoch seconds for sorting a simulation by its run date."""
    raw_ep = meta.get("simulation_epoch")
    if isinstance(raw_ep, (int, float)) and not isinstance(raw_ep, bool) and float(raw_ep) > 0.0:
        return float(raw_ep)
    for key in ("simulation_iso", "simulation_utc", "updated_utc"):
        parsed = parse_utc_timestamp(meta.get(key))
        if parsed is not None:
            return parsed[2]
    return 0.0


def baseline_sort_key(meta: dict[str, object]) -> tuple[int, int, str]:
    """Deterministic control-complexity key used to pick the baseline reference row."""
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


def meta_sort_key(meta: dict[str, object]) -> tuple[int, float, int, int, str]:
    """Default ordering: tech reports first, then simulations newest-first by simulation date."""
    if is_tech_report_meta(meta):
        return (-1, 0.0, 0, 0, str(meta.get("slug", "")))
    tier, sub_ord, slug = baseline_sort_key(meta)
    epoch = simulation_sort_epoch(meta)
    if epoch > 0.0:
        return (0, -epoch, tier, sub_ord, slug)
    return (1, 0.0, tier, sub_ord, slug)
