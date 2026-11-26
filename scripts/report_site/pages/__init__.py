#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""HTML page builders for the cacao-work static AO knowledge repository."""

from __future__ import annotations

from .algorithms import build_algorithm_detail_html, build_algorithms_index_html
from .fragments import build_extra_figures_section, build_telemetry_files_section
from .front_page import build_front_page_html
from .options_reference import build_options_reference_html
from .predictive_control import build_predictive_control_guide_html
from .sim_config import build_sim_config_html
from .sim_how_to_run import build_sim_how_to_run_html
from .sim_optical import build_sim_optical_html
from .sim_overview import build_sim_overview_html
from .sim_pyrwfs import build_sim_pyrwfs_html
from .sim_runtime import build_sim_runtime_html
from .simulations_catalog import build_simulations_catalog_html
from .stack_guide import build_stack_guide_html
from .tech_report import build_tech_report_html
from .topic_hub import build_topic_hub_html
from .turbulence import build_turbulence_model_html, render_sim_turbulence_card

__all__ = [
    "build_algorithm_detail_html",
    "build_algorithms_index_html",
    "build_extra_figures_section",
    "build_front_page_html",
    "build_options_reference_html",
    "build_predictive_control_guide_html",
    "build_sim_config_html",
    "build_sim_how_to_run_html",
    "build_sim_optical_html",
    "build_sim_overview_html",
    "build_sim_pyrwfs_html",
    "build_sim_runtime_html",
    "build_simulations_catalog_html",
    "build_stack_guide_html",
    "build_tech_report_html",
    "build_topic_hub_html",
    "build_turbulence_model_html",
    "render_sim_turbulence_card",
]
