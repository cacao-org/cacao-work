#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Compatibility re-export shim for report_site.extractors."""

from __future__ import annotations

from .extractors import (  # noqa: F401
    REL_SIBLING_RE,
    TRACKED_PARAMS,
    baseline_sort_key,
    build_compute_unit_catalog,
    classify_phase_category,
    classify_shm_category,
    classify_unit_category,
    extract_metrics_highlights,
    extract_optical_explorer_data,
    extract_referenced_simulations,
    extract_run_parameters,
    extract_runtime_explorer_data,
    extract_runtime_summary,
    extract_simulation_timestamp,
    find_bench_path,
    find_metrics_path,
    human_bytes,
    is_tech_report_meta,
    load_json_safe,
    meta_sort_key,
    parse_bench_file,
    parse_utc_timestamp,
    resolve_run_parameters,
    simulation_sort_epoch,
)
