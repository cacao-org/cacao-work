#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared constants, repository metadata, and compute-category definitions."""

from __future__ import annotations

from pathlib import Path

ASSET_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".mp4",
    ".webm",
    ".json",
    ".csv",
    ".tsv",
    ".txt",
    ".dat",
    ".bench",
}
DATA_EXTS = {".json", ".csv", ".tsv", ".txt", ".dat", ".fits", ".bench"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
VIDEO_EXTS = {".mp4", ".webm"}

GUI_CONFIG_IMAGES = {
    "cacaosim_gui_schematic.png",
    "cacaosim_gui_builder.png",
    "cacaosim_gui_tables.png",
    "cacaosim_gui_status.png",
    "chromatic_passbands_2x1.png",
}

COMPUTE_IMAGES = {
    "compute_timeline_4x1.png",
    "compute_process_breakdown_2x2.png",
    "compute_shm_and_calib_2x2.png",
}

FRIENDLY_FIG_LABELS: dict[str, str] = {
    "wfs_psf_short_evolution.mp4": (
        "Short-Timescale Polychromatic PyWFS & Speckle PSF Evolution (Video)"
    ),
    "cacaosim_gui_schematic.png": (
        "cacaosim-CTRL 2D Optical Bench Schematic & 32-Bin Polychromatic Spectra (F3:SCHEMATIC)"
    ),
    "cacaosim_gui_builder.png": (
        "cacaosim-CTRL 3-Pane Hardware Configurator & Parameter Inspector (F2:BUILDER)"
    ),
    "cacaosim_gui_tables.png": (
        "cacaosim-CTRL Hardware Mirrors, Sensors & Splitters Summary (F4:TABLES)"
    ),
    "cacaosim_gui_status.png": (
        "cacaosim-CTRL Live Shared-Memory Streams & Active MILK FPS Units (F5:STATUS)"
    ),
    "chromatic_passbands_2x1.png": (
        "Optical Bench 32-Bin Spectra & Polychromatic Sensor Sub-Band Sampling (2x1)"
    ),
    "psf_comparison_2x3.png": "Long-Exposure Polychromatic PSF Comparison (2x3)",
    "psf_radial_profiles.png": "PSF Radial Profiles & Encircled Energy",
    "coro_before_after_psf.png": (
        "H-Band Focal-Plane PSF Before vs After Lyot Coronagraph (2x3)"
    ),
    "coro_lyot_stop_illumination.png": (
        "Light Incident on Pupil-Plane Lyot Stop & Reflective-Lyot LOWFS Power Budget (2x3)"
    ),
    "coro_lowfs_summary.png": (
        "Subaru H-Band Lyot Coronagraph & Reflective-Lyot Defocused LLOWFS Summary (2x3)"
    ),
    "wf_strehl_timeseries_4x1.png": (
        "RMS Wavefront Error & Strehl Ratio Time Series with Sampled Instants (4x1)"
    ),
    "psf_inst_vis_5x3.png": (
        "Instantaneous Visible 0.75 um (15% BW, 3ch) PSFs at Sampled Instants (5x3)"
    ),
    "psf_inst_nir_5x3.png": (
        "Instantaneous Near-IR H-Band 1.65 um (18% BW, 3ch) PSFs at Sampled Instants (5x3)"
    ),
    "wf_stats_2x3.png": "Wavefront Mean & Temporal Std Dev (2x3)",
    "wf_samples_5x3.png": "Instantaneous Pupil Wavefront OPD Samples at Sampled Instants (5x3)",
    "wfs_samples_5x4.png": (
        "Instantaneous Polychromatic Pyramid WFS Frames & Signals at Sampled Instants (5x4)"
    ),
    "dm_samples_5x4.png": (
        "Instantaneous DM Actuator Commands & Pupil OPD Shapes at Sampled Instants (5x4)"
    ),
    "mlat_latency_1x2.png": "Hardware Latency Measurement (mlat)",
    "modal_gains_1x2.png": "Modal Loop Gain Curves",
    "selfrm_summary_2x4.png": "Modal Self-Response Matrix Summary (selfRM)",
    "predictive_control_summary_2x2.png": (
        "PSOL Auto-Regressive Predictive Control Filter & Modal Residual Summary (2x2)"
    ),
    "eof_pf_matrix_3d.png": (
        "3D Modal Predictive Matrix PF(out_i, lag_k, in_j) — Volumetric Slices, "
        "Cross-Mode Coupling & Block/Lag Structure (2x3)"
    ),
    "eof_pf_lag_slices.png": (
        "3D Modal Predictive Matrix PF — Signed 2D Cross-Mode Lag Slices Across Lookback Taps"
    ),
    "ar_order_optical_coro_summary_2x3.png": (
        "Optical, Wavefront & Lyot Coronagraph Performance vs. AR Predictive Order (2x3)"
    ),
    "ar_order_timeseries_and_petals_2x3.png": (
        "Synchronized 5.0 s Time Series & Subaru V-Spider Petal OPD Maps (2x3)"
    ),
    "ar_order_filter_weights_and_freq_2x2.png": (
        "Learned AR(P) Filter Impulse Responses, Cauchy-Schwarz Phase Lead & Freq Response (2x2)"
    ),
    "ar_order_modal_and_psd_2x2.png": (
        "Closed-Loop 1 kHz / 2 kHz Temporal PSDs & Spatial Modal Residual Spectra (2x2)"
    ),
    "ar_order_bias_variance_sample_complexity_2x2.png": (
        "Walk-Forward Bias-Variance Tradeoff & Sample-Complexity Scaling (2x2)"
    ),
    "ar_order_psf_and_compute_2x3.png": (
        "H-Band Coronagraphic PSFs, Real-Time Compute Scaling & Pareto Frontier (2x3)"
    ),
    "eof_vs_ar_offline_20s_2x2.png": (
        "Cross-Mode Block-EOF vs. Diagonal AR(16): 20 s Walk-Forward Scaling & Coupling (2x2)"
    ),
    "eof_vs_ar_closed_loop_2x3.png": (
        "Cross-Mode Block-EOF vs. Diagonal AR(16): Closed-Loop Optical, Coro & Compute (2x3)"
    ),
    "calib_2wfs1dm_summary_2x2.png": (
        "Joint 2-WFS + Inter-Stage DM Telemetry Calibration Summary (2x2)"
    ),
    "calib_2wfs1dm_whitening_lag_regimes_2x2.png": (
        "2-WFS + 1-DM Calibration Sweeps: Whitening Order, Lag Surface, Regimes & Convergence (2x2)"
    ),
    "calib_2wfs1dm_offload_and_zpo_2x3.png": (
        "DM2->DM1 Offload Matrix vs Actuator Geometry & Stage-2/Stage-3 Channel Activity (2x3)"
    ),
    "calib_2wfs1dm_method_comparison_2x2.png": (
        "Beyond W(z): Exact-Window Frequency-Domain AO-Dynamics vs AR(4) W(z) & OLS (2x2)"
    ),
    "dm_poke_actual_vs_sim_20khz.mp4": (
        "Side-by-Side 20 kHz ALPAO 64x64 DM Poke: Actual SCExAO Measurement (LepICSaBL-E) vs cacaosim Plate PDE (Video)"
    ),
    "dm_poke_actual_vs_sim_contact_sheet.png": (
        "Synchronized Actual SCExAO Measurement vs cacaosim Plate PDE Contact Sheet (t = +0.5 to +11.5 ms)"
    ),
    "dm_shape_vs_deriv_20khz.mp4": (
        "ALPAO 64x64 DM Instantaneous Surface Shape w(t) vs. 1 ms Time Derivative (20 kHz Video)"
    ),
    "dm_shape_vs_deriv_contact_sheet.png": (
        "ALPAO 64x64 DM Surface Shape w(t) (1x, 50x, w - w_DC) vs. 1 ms Derivative Contact Sheet (4x6)"
    ),
    "dm_poke_sim_20khz.mp4": (
        "Simulated 64x64 ALPAO DM (dyn_mode=plate) 20 kHz Single-Actuator Poke — 1 ms Diff (Video)"
    ),
    "dm_poke_sim_contact_sheet.png": (
        "ALPAO 64x64 DM 20 kHz Single-Actuator Poke Contact Sheet (t = +0.6 to +17.5 ms)"
    ),
    "dm_plate_physics_diagnostics_2x2.png": (
        "ALPAO 64x64 Coupled Plate PDE Diagnostics: Wavefront Space-Time, Decay, Dispersion & Latency (2x2)"
    ),
    "compute_timeline_4x1.png": "Compute & Power Timeline (4x1)",
    "compute_process_breakdown_2x2.png": "Per-Process CPU & Latency Breakdown (2x2)",
    "compute_shm_and_calib_2x2.png": "SHM Bandwidth & Calibration Breakdown (2x2)",
}

DEFAULT_REPOS: list[dict[str, str]] = [
    {
        "name": "cacao-work",
        "url": "https://github.com/cacao-org/cacao-work",
        "branch": "main",
        "role": (
            "Integration workspace, AO3k+SCExAO bench & runner, pytest suite, "
            "and static web report builder"
        ),
    },
    {
        "name": "cacaosim",
        "url": "https://github.com/cacao-org/cacaosim",
        "branch": "main",
        "role": (
            "GPU-fused & modular polychromatic AO hardware simulator, "
            "multi-rate sub-stepping, TUI, and report generator"
        ),
    },
    {
        "name": "cacao",
        "url": "https://github.com/cacao-org/cacao",
        "branch": "feat/bash-engine",
        "role": (
            "Compute and Control for Adaptive Optics (acquireWFS, mlat, "
            "Hadamard RM, SVD CM, modalfilter)"
        ),
    },
    {
        "name": "milk",
        "url": "https://github.com/milk-org/milk",
        "branch": "feat/bash-engine",
        "role": (
            "Core FPS shared-memory engine, milk-script orchestrator, "
            "streamFITSlog telemetry, and milk-perf-report"
        ),
    },
    {
        "name": "ImageStreamIO",
        "url": "https://github.com/milk-org/ImageStreamIO",
        "branch": "dev",
        "role": "Low-latency POSIX/CUDA shared-memory stream transport (milk submodule)",
    },
    {
        "name": "milk-mltools",
        "url": "https://github.com/milk-org/milk-mltools",
        "branch": "main",
        "role": (
            "C telemetry indexing & sync, @calc JIT extensions, AO loop "
            "optimizer, and polychromatic PSF reconstruction"
        ),
    },
    {
        "name": "AtmosphericTurbulenceSimul",
        "url": "https://github.com/oguyon/AtmosphericTurbulenceSimul",
        "branch": "feat/bash-engine",
        "role": "Multi-layer Maunakea frozen-flow & boiling turbulence generator (milkatmturb)",
    },
    {
        "name": "OpticsMaterials",
        "url": "https://github.com/milk-org/OpticsMaterials",
        "branch": "feat/bash-engine",
        "role": "Optical material dispersion & air refractive-index library for milk",
    },
    {
        "name": "WFpropagate",
        "url": "https://github.com/milk-org/WFpropagate",
        "branch": "feat/bash-engine",
        "role": "Fresnel & angular-spectrum wavefront propagation library for milk",
    },
]

DEFAULT_RUN_COMMAND = (
    "./scripts/run-ao3k-scexao.sh --seeing 0.60 --phys-time 10.0 --oversample 4 "
    "--bench-mode fused --save-rm _work/ao3k_scexao_rm --save-telemetry speckle"
)

COMPUTE_CATEGORY_ORDER: tuple[str, ...] = (
    "simulation",
    "calibration",
    "loop_operation",
    "analysis",
)

COMPUTE_CATEGORIES: dict[str, dict[str, str]] = {
    "simulation": {
        "key": "simulation",
        "label": "Simulation",
        "short": "Sim",
        "description": (
            "Atmospheric turbulence & polychromatic cacaosim optical bench"
        ),
        "mermaid_class": "cat_simulation",
        "mermaid_def": "fill:#f3e8ff,stroke:#7e22ce,stroke-width:2px,color:#3b0764",
    },
    "calibration": {
        "key": "calibration",
        "label": "Calibration",
        "short": "Calib",
        "description": (
            "Latency measurement, Hadamard RM, SVD CM, PF solver & 2-WFS/1-DM SysID"
        ),
        "mermaid_class": "cat_calibration",
        "mermaid_def": "fill:#fef3c7,stroke:#b45309,stroke-width:2px,color:#78350f",
    },
    "loop_operation": {
        "key": "loop_operation",
        "label": "Loop Operation",
        "short": "Loop",
        "description": (
            "Real-time WFS acquisition, MVM, modal filtering, PSOL, ZPO & DM driving"
        ),
        "mermaid_class": "cat_loop_operation",
        "mermaid_def": "fill:#e0f2fe,stroke:#0369a1,stroke-width:2px,color:#0c4a6e",
    },
    "analysis": {
        "key": "analysis",
        "label": "Analysis",
        "short": "Analysis",
        "description": (
            "Modal RMS monitors, FITS/telemetry loggers, PSF & performance reporting"
        ),
        "mermaid_class": "cat_analysis",
        "mermaid_def": "fill:#d1fae5,stroke:#047857,stroke-width:2px,color:#064e3b",
    },
}


def friendly_figure_caption(filename: str) -> str:
    """Return human-friendly caption for a diagnostic PNG filename."""
    if filename in FRIENDLY_FIG_LABELS:
        return FRIENDLY_FIG_LABELS[filename]
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() if stem else filename
