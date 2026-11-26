#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Pure-stdlib metadata, bench, optical, runtime, and compute-unit extractors."""

from __future__ import annotations

from .algorithms_catalog import (
    ALGO_ROLE_ORDER,
    ALGO_ROLES,
    build_algorithms_catalog,
    make_algo_slug,
    make_variant_anchor,
)
from .bench import find_bench_path, parse_bench_file
from .common import (
    REL_SIBLING_RE,
    baseline_sort_key,
    extract_simulation_timestamp,
    find_metrics_path,
    human_bytes,
    is_tech_report_meta,
    load_json_safe,
    meta_sort_key,
    parse_utc_timestamp,
    simulation_sort_epoch,
)
from .compute_units import build_compute_unit_catalog, extract_referenced_simulations
from .eof_pf import extract_eof_pf_data
from .highlights import extract_metrics_highlights
from .optical import extract_optical_explorer_data
from .options_catalog import (
    CACAOLOOP_ENV_VARS,
    RUNNER_CLI_OPTIONS,
    build_bench_opt_lookup,
    build_options_catalog,
    extract_atmturb_fps_units,
    extract_cacao_predictive_fps_units,
    is_nondefault_bench_value,
    load_cacaosim_schema,
    make_bench_opt_anchor,
    make_cli_opt_anchor,
    make_fps_opt_anchor,
    make_fps_unit_anchor,
    make_runner_opt_anchor,
)
from .params import TRACKED_PARAMS, extract_run_parameters, resolve_run_parameters
from .pyrwfs import extract_pyrwfs_telemetry_data
from .runtime import (
    classify_phase_category,
    classify_shm_category,
    classify_unit_category,
    extract_runtime_explorer_data,
    extract_runtime_summary,
)
from .turbulence_model import (
    DEFAULT_ATM_LAYERS,
    DEFAULT_DYNWIND_SPEC,
    DEFAULT_PERTURB_PARAMS,
    DEFAULT_PETAL_RMS_NM,
    DEFAULT_PETAL_TAU_S,
    DEFAULT_SEEING_ARCSEC,
    DEFAULT_VIB_MODES,
    DEFAULT_VIB_RMS_NM,
    TURBULENCE_VISUAL_FILES,
    compute_atmosphere_stats,
    compute_effective_l0_m,
    compute_petaling_stats,
    compute_piston_removed_opd_nm,
    compute_vibration_stats,
    extract_turbulence_profile,
    get_normalized_layers,
    solve_r0_for_seeing_m,
)

__all__ = [
    "ALGO_ROLES",
    "ALGO_ROLE_ORDER",
    "CACAOLOOP_ENV_VARS",
    "DEFAULT_ATM_LAYERS",
    "DEFAULT_DYNWIND_SPEC",
    "DEFAULT_PERTURB_PARAMS",
    "DEFAULT_PETAL_RMS_NM",
    "DEFAULT_PETAL_TAU_S",
    "DEFAULT_SEEING_ARCSEC",
    "DEFAULT_VIB_MODES",
    "DEFAULT_VIB_RMS_NM",
    "REL_SIBLING_RE",
    "RUNNER_CLI_OPTIONS",
    "TRACKED_PARAMS",
    "TURBULENCE_VISUAL_FILES",
    "baseline_sort_key",
    "build_algorithms_catalog",
    "build_bench_opt_lookup",
    "build_compute_unit_catalog",
    "build_options_catalog",
    "classify_phase_category",
    "classify_shm_category",
    "classify_unit_category",
    "compute_atmosphere_stats",
    "compute_effective_l0_m",
    "compute_petaling_stats",
    "compute_piston_removed_opd_nm",
    "compute_vibration_stats",
    "extract_atmturb_fps_units",
    "extract_cacao_predictive_fps_units",
    "extract_eof_pf_data",
    "extract_metrics_highlights",
    "extract_optical_explorer_data",
    "extract_pyrwfs_telemetry_data",
    "extract_referenced_simulations",
    "extract_run_parameters",
    "extract_runtime_explorer_data",
    "extract_runtime_summary",
    "extract_simulation_timestamp",
    "extract_turbulence_profile",
    "find_bench_path",
    "find_metrics_path",
    "get_normalized_layers",
    "human_bytes",
    "is_nondefault_bench_value",
    "is_tech_report_meta",
    "load_cacaosim_schema",
    "load_json_safe",
    "make_bench_opt_anchor",
    "make_cli_opt_anchor",
    "make_fps_opt_anchor",
    "make_fps_unit_anchor",
    "make_runner_opt_anchor",
    "meta_sort_key",
    "parse_bench_file",
    "parse_utc_timestamp",
    "resolve_run_parameters",
    "simulation_sort_epoch",
    "solve_r0_for_seeing_m",
]
