#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Pure-stdlib metadata, bench, optical, runtime, and compute-unit extractors."""

from __future__ import annotations

from .bench import find_bench_path, parse_bench_file
from .common import (
    REL_SIBLING_RE,
    find_metrics_path,
    human_bytes,
    is_tech_report_meta,
    load_json_safe,
    meta_sort_key,
)
from .compute_units import build_compute_unit_catalog, extract_referenced_simulations
from .highlights import extract_metrics_highlights
from .optical import extract_optical_explorer_data
from .params import TRACKED_PARAMS, extract_run_parameters, resolve_run_parameters
from .runtime import (
    classify_phase_category,
    classify_shm_category,
    classify_unit_category,
    extract_runtime_explorer_data,
    extract_runtime_summary,
)

__all__ = [
    "REL_SIBLING_RE",
    "TRACKED_PARAMS",
    "build_compute_unit_catalog",
    "classify_phase_category",
    "classify_shm_category",
    "classify_unit_category",
    "extract_metrics_highlights",
    "extract_optical_explorer_data",
    "extract_referenced_simulations",
    "extract_run_parameters",
    "extract_runtime_explorer_data",
    "extract_runtime_summary",
    "find_bench_path",
    "find_metrics_path",
    "human_bytes",
    "is_tech_report_meta",
    "load_json_safe",
    "meta_sort_key",
    "parse_bench_file",
    "resolve_run_parameters",
]
