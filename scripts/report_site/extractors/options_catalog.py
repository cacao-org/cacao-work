#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unified option-catalog extractor spanning cacaosim, milkatmturb, and cacao-work runners."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

from .bench import find_bench_path, parse_bench_file
from .common import _parse_cmd_flag, load_json_safe

_REPO_ROOT = Path(__file__).resolve().parents[3]

_C_DEFAULT_RE = re.compile(
    r"^\s*static\s+(?:const\s+)?[a-zA-Z0-9_]+\s+"
    r"(param_[a-zA-Z0-9_]+)(?:\s*\[[^\]]*\])?\s*=\s*([^;]+);",
    re.MULTILINE,
)

_C_STATIC_VAR_DEFAULT_RE = re.compile(
    r"^\s*static\s+(?:const\s+)?[a-zA-Z0-9_]+\s+"
    r"([a-zA-Z_][a-zA-Z0-9_]*)(?:\s*\[[^\]]*\])?\s*=\s*([^;]+);",
    re.MULTILINE,
)

_X_MACRO_CALL_RE = re.compile(
    r'X\(\s*"([^"]+)"\s*,\s*&?(param_[a-zA-Z0-9_]+)\s*,\s*'
    r"(FPTYPE_[A-Z0-9_]+)\s*,\s*([01])\s*,\s*([^,]+?)\s*,\s*((?:\"[^\"]*\"\s*)+)\)",
    re.DOTALL,
)

_X_MACRO_ANY_CALL_RE = re.compile(
    r'X\(\s*"([^"]+)"\s*,\s*&?([a-zA-Z_][a-zA-Z0-9_]*)\s*,\s*'
    r"(FPTYPE_[A-Z0-9_]+)\s*,\s*([01])\s*,\s*([^,]+?)\s*,\s*((?:\"[^\"]*\"\s*)+)\)",
    re.DOTALL,
)

_RUNNABLE_FIELD_RE = re.compile(
    r"\.(fps_name|cmdkey|description)\s*=\s*((?:\"[^\"]*\"\s*)+)",
    re.DOTALL,
)

_EXPORT_FPSEXEC_RE = re.compile(
    r'EXPORT_FPSEXEC\(\s*([a-zA-Z0-9_]+)\s*,\s*"([^"]+)"\s*,',
)

_FPTYPE_MAP: dict[str, str] = {
    "FPTYPE_INT32": "int32",
    "FPTYPE_INT64": "int64",
    "FPTYPE_UINT32": "uint32",
    "FPTYPE_UINT64": "uint64",
    "FPTYPE_FLOAT32": "float32",
    "FPTYPE_FLOAT64": "float64",
    "FPTYPE_ONOFF": "onoff",
    "FPTYPE_STRING": "string",
    "FPTYPE_FILENAME": "filename",
    "FPTYPE_FITSFILENAME": "fitsfile",
    "FPTYPE_DIRNAME": "dirname",
    "FPTYPE_STREAMNAME": "stream",
}


def slugify_opt_id(raw: str) -> str:
    """Convert an option identifier into a deterministic, URL-safe HTML anchor token."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower())
    return cleaned.strip("-")


def make_bench_opt_anchor(section: str, key: str) -> str:
    """Return canonical anchor ID for a .bench option."""
    return f"opt-bench-{slugify_opt_id(section)}-{slugify_opt_id(key)}"


def make_fps_unit_anchor(package: str, unit: str) -> str:
    """Return canonical anchor ID for an FPS compute unit."""
    return f"opt-unit-{slugify_opt_id(package)}-{slugify_opt_id(unit)}"


def make_fps_opt_anchor(package: str, unit: str, keyword: str) -> str:
    """Return canonical anchor ID for an FPS compute unit parameter."""
    kw = keyword.lstrip(".")
    return f"opt-fps-{slugify_opt_id(package)}-{slugify_opt_id(unit)}-{slugify_opt_id(kw)}"


def make_cli_opt_anchor(tool: str, flag: str) -> str:
    """Return canonical anchor ID for a CLI flag or environment variable."""
    primary = flag.split(",")[-1].strip()
    return f"opt-cli-{slugify_opt_id(tool)}-{slugify_opt_id(primary)}"


def make_runner_opt_anchor(flag: str) -> str:
    """Return canonical anchor ID for a run-ao3k-scexao.sh / sim-ao3k-scexao.milk flag."""
    return make_cli_opt_anchor("run-ao3k-scexao.sh", flag)


RUNNER_CLI_OPTIONS: list[dict[str, object]] = [
    {
        "flag": "--seeing",
        "key": "seeing",
        "arg": "<arcsec>",
        "type": "float",
        "default": "0.8",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Seeing [arcsec]",
        "description": "Atmospheric seeing FWHM at 0.50 um reference wavelength [arcsec]",
    },
    {
        "flag": "--star-mag",
        "key": "star_mag",
        "arg": "<mag>",
        "type": "float",
        "default": "6.0 (bench)",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Star Mag [mV=mH]",
        "description": "Override guide/science star Vega magnitude mV=mH (A0V Teff=9600 K)",
    },
    {
        "flag": "--phys-time",
        "key": "phys_time",
        "arg": "<sec>",
        "type": "float",
        "default": "10.0",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Phys Time [s]",
        "description": "Physical closed-loop science integration time [s]",
    },
    {
        "flag": "--wall-rate",
        "key": "wall_rate",
        "arg": "<hz>",
        "type": "float",
        "default": "lockstep fused (1000 calib), 160 mod",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Wall Rate [Hz]",
        "description": "Optional wall-clock rate cap [Hz] on top of 1:1 lockstep pacing",
    },
    {
        "flag": "--calib-rate",
        "key": "calib_rate",
        "arg": "<hz>",
        "type": "float",
        "default": "matches --wall-rate",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Calib Rate [Hz]",
        "description": "Override wall-clock rate for mlat/takeref calibration steps [Hz]",
    },
    {
        "flag": "--no-fast-calib",
        "key": "no_fast_calib",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Disable Fast Calib",
        "description": "Disable fused lockstep step-and-shoot RM; use real-time paced RM",
    },
    {
        "flag": "--bench-mode",
        "key": "bench_mode",
        "arg": "<fused|modular>",
        "type": "choice",
        "choices": ["fused", "modular"],
        "default": "fused",
        "group": "Optical Bench",
        "tier": "core",
        "label": "cacaosim Mode",
        "description": "Optical bench engine: fused zero-hop htsim or modular per-element FPS",
    },
    {
        "flag": "--oversample",
        "key": "oversample",
        "arg": "<int>",
        "type": "int",
        "default": "0 (bench=4)",
        "group": "Optical Bench",
        "tier": "core",
        "label": "Oversample K",
        "description": "Temporal oversampling factor K (0 = inherit .bench value = 4 -> 8 kHz)",
    },
    {
        "flag": "--clock-skew-us",
        "key": "clock_skew_us",
        "arg": "<float>",
        "type": "float",
        "default": "",
        "group": "Optical Bench",
        "tier": "advanced",
        "label": "Clock Skew [us]",
        "description": "Stage-2 WFS clock trigger offset [us] relative to Stage 1",
    },
    {
        "flag": "--wfs1-mod-rad",
        "key": "wfs1_mod_rad",
        "arg": "<float>",
        "type": "float",
        "default": "3.0 (bench)",
        "group": "Optical Bench",
        "tier": "advanced",
        "label": "Stg1 PyWFS Mod [l/D]",
        "description": "Override Stage-1 NIR PyWFS modulation radius [l/D] (0 = unmodulated)",
    },
    {
        "flag": "--wfs2-mod-rad",
        "key": "wfs2_mod_rad",
        "arg": "<float>",
        "type": "float",
        "default": "3.0 (bench)",
        "group": "Optical Bench",
        "tier": "advanced",
        "label": "Stg2 PyWFS Mod [l/D]",
        "description": "Override Stage-2 Vis PyWFS modulation radius [l/D] (0 = unmodulated)",
    },
    {
        "flag": "--wfs1-rate",
        "key": "wfs1_rate",
        "arg": "<hz>",
        "type": "float",
        "default": "1000",
        "group": "Optical Bench",
        "tier": "advanced",
        "label": "Stg1 WFS Rate [Hz]",
        "description": "Stage-1 NIR PyWFS frame rate [Hz], integer divisor of 2000 (e.g. 250/500/1000)",
    },
    {
        "flag": "--mr-dm1",
        "key": "mr_dm1",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Loop Control",
        "tier": "core",
        "label": "Stg1 Multi-Rate DM",
        "description": "Enable Stage-1 multi-rate 1 kHz DM command pacing (mvalpacer-1 + EOF velocity)",
    },
    {
        "flag": "--mr-substeps",
        "key": "mr_substeps",
        "arg": "<int>",
        "type": "int",
        "default": "1000 / wfs1-rate",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "MR DM Substeps K_sub",
        "description": "Override Stage-1 DM sub-steps K_sub per WFS1 exposure frame",
    },
    {
        "flag": "--mr-vel-gain",
        "key": "mr_vel_gain",
        "arg": "<float>",
        "type": "float",
        "default": "1.0",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "MR Velocity Gain",
        "description": "Stage-1 multi-rate centered linear-ramp velocity gain multiplier",
    },
    {
        "flag": "--mr-vel-reg-mult",
        "key": "mr_vel_reg_mult",
        "arg": "<float>",
        "type": "float",
        "default": "3.5",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "MR Vel Reg Mult",
        "description": "Stage-1 multi-rate zero-DC temporal-difference velocity ridge multiplier",
    },
    {
        "flag": "--no-stage2",
        "key": "no_stage2",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Disable Stage 2",
        "description": "Keep Stage-2 SCExAO loop open to isolate Stage-1 AO3k on final/coro cameras",
    },
    {
        "flag": "--wfs-dark-adu",
        "key": "wfs_dark_adu",
        "arg": "<float>",
        "type": "float",
        "default": "0.0",
        "group": "Optical Bench",
        "tier": "advanced",
        "label": "WFS Dark Pedestal [ADU]",
        "description": "Camera dark/bias pedestal [ADU] subtracted before WFS intensity normalization",
    },
    {
        "flag": "--wfstat-validate",
        "key": "wfstat_validate",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Optical Bench",
        "tier": "advanced",
        "label": "WFStat Validate",
        "description": "Fused mode: export beams and run CPU csim_wfstat cross-check",
    },
    {
        "flag": "--gain1",
        "key": "gain1",
        "arg": "<float>",
        "type": "float",
        "default": "0.35",
        "group": "Loop Control",
        "tier": "core",
        "label": "Stage-1 Gain",
        "description": "Stage-1 AO3k modal integrator loop gain",
    },
    {
        "flag": "--gain2",
        "key": "gain2",
        "arg": "<float>",
        "type": "float",
        "default": "0.35",
        "group": "Loop Control",
        "tier": "core",
        "label": "Stage-2 Gain",
        "description": "Stage-2 SCExAO modal integrator loop gain",
    },
    {
        "flag": "--gain3",
        "key": "gain3",
        "arg": "<float>",
        "type": "float",
        "default": "0.20",
        "group": "Loop Control",
        "tier": "core",
        "label": "Stage-3 Gain",
        "description": "Stage-3 LLOWFS modal integrator loop gain",
    },
    {
        "flag": "--mult1",
        "key": "mult1",
        "arg": "<float>",
        "type": "float",
        "default": "0.98",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stage-1 Mult",
        "description": "Stage-1 AO3k leaky integrator multiplier",
    },
    {
        "flag": "--mult2",
        "key": "mult2",
        "arg": "<float>",
        "type": "float",
        "default": "0.98",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stage-2 Mult",
        "description": "Stage-2 SCExAO leaky integrator multiplier",
    },
    {
        "flag": "--mult3",
        "key": "mult3",
        "arg": "<float>",
        "type": "float",
        "default": "0.99",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stage-3 Mult",
        "description": "Stage-3 LLOWFS leaky integrator multiplier",
    },
    {
        "flag": "--mgain-alpha",
        "key": "mgain_alpha",
        "arg": "<float>",
        "type": "float",
        "default": "0.8",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Modal Gain Alpha",
        "description": "Modal gain power-law rolloff exponent across mode index",
    },
    {
        "flag": "--mgain-floor",
        "key": "mgain_floor",
        "arg": "<float>",
        "type": "float",
        "default": "0.10",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Modal Gain Floor",
        "description": "Modal gain floor factor applied at the highest controlled mode",
    },
    {
        "flag": "--mgain-tt",
        "key": "mgain_tt",
        "arg": "<float>",
        "type": "float",
        "default": "1.0",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Tip/Tilt Gain Factor",
        "description": "Modal gain multiplier for Tip/Tilt modes 0 and 1",
    },
    {
        "flag": "--svdlim1",
        "key": "svdlim1",
        "arg": "<float>",
        "type": "float",
        "default": "0.004",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Stage-1 SVD Limit",
        "description": "Stage-1 AO3k SVD singular-value truncation threshold",
    },
    {
        "flag": "--svdlim2",
        "key": "svdlim2",
        "arg": "<float>",
        "type": "float",
        "default": "0.004",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Stage-2 SVD Limit",
        "description": "Stage-2 SCExAO SVD singular-value truncation threshold",
    },
    {
        "flag": "--svdlim3",
        "key": "svdlim3",
        "arg": "<float>",
        "type": "float",
        "default": "0.02",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Stage-3 SVD Limit",
        "description": "Stage-3 LLOWFS SVD singular-value truncation threshold",
    },
    {
        "flag": "--no-lowfs",
        "key": "no_lowfs",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Loop Control",
        "tier": "core",
        "label": "Stage-3 LLOWFS",
        "description": "Keep Stage-3 Lyot LLOWFS loop open during science integration",
    },
    {
        "flag": "--psol-og1",
        "key": "psol_og1",
        "arg": "<float>",
        "type": "float",
        "default": "",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stg1 PSOL OG",
        "description": "Optional Stage-1 on-sky optical-gain scale for PSOL WFSfact (1/g_opt)",
    },
    {
        "flag": "--zpo-og",
        "key": "zpo_og",
        "arg": "<float>",
        "type": "float",
        "default": "1.0",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stage-2 ZPO OG",
        "description": "Stage-2 optical-gain scale applied to ZPO (0.95*g_opt) and PSOL (1/g_opt)",
    },
    {
        "flag": "--predictive",
        "key": "predictive",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Predictive Control",
        "tier": "core",
        "label": "Predictive Control",
        "description": "Enable PSOL predictive control on Stage 1 (AO3k) and Stage 2 (SCExAO)",
    },
    {
        "flag": "--pf-mode",
        "key": "pf_mode",
        "arg": "<ar|eof>",
        "type": "choice",
        "choices": ["ar", "eof"],
        "default": "ar",
        "group": "Predictive Control",
        "tier": "core",
        "label": "PF Mode",
        "description": "Predictive filter architecture: ar (diagonal) or eof (block cross-mode)",
    },
    {
        "flag": "--pf-blocksize",
        "key": "pf_blocksize",
        "arg": "<int>",
        "type": "int",
        "default": "128",
        "group": "Predictive Control",
        "tier": "core",
        "label": "EOF Block Size B",
        "description": "Cross-mode Block-EOF coupled mode block size B",
    },
    {
        "flag": "--pf-mix",
        "key": "pf_mix",
        "arg": "<float>",
        "type": "float",
        "default": "0.90",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Mix (Both)",
        "description": "Predictive control mixing coefficient applied to both Stage 1 & Stage 2",
    },
    {
        "flag": "--pf-mix1",
        "key": "pf_mix1",
        "arg": "<float>",
        "type": "float",
        "default": "matches --pf-mix",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Mix Stage 1",
        "description": "Stage-1 AO3k predictive mixing coefficient override",
    },
    {
        "flag": "--pf-mix2",
        "key": "pf_mix2",
        "arg": "<float>",
        "type": "float",
        "default": "matches --pf-mix",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Mix Stage 2",
        "description": "Stage-2 SCExAO predictive mixing coefficient override",
    },
    {
        "flag": "--pf-order",
        "key": "pf_order",
        "arg": "<int>",
        "type": "int",
        "default": "8",
        "group": "Predictive Control",
        "tier": "core",
        "label": "PF Order P",
        "description": "Predictive filter temporal lookback tap order P",
    },
    {
        "flag": "--pf-reg",
        "key": "pf_reg",
        "arg": "<float>",
        "type": "float",
        "default": "0.005",
        "group": "Predictive Control",
        "tier": "core",
        "label": "PF Reg lambda",
        "description": "Stage-1 / default Tikhonov ridge regularization parameter lambda",
    },
    {
        "flag": "--pf-reg2",
        "key": "pf_reg2",
        "arg": "<float>",
        "type": "float",
        "default": "matches --pf-reg",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Reg Stage 2",
        "description": "Optional Stage-2 SCExAO Tikhonov regularization lambda override",
    },
    {
        "flag": "--pf-maxnorm2",
        "key": "pf_maxnorm2",
        "arg": "<float>",
        "type": "float",
        "default": "",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Max ||F||^2",
        "description": "Optional per-row ||F_m||_2^2 noise amplification cap override",
    },
    {
        "flag": "--pf-nbtrain1",
        "key": "pf_nbtrain1",
        "arg": "<int>",
        "type": "int",
        "default": "2048 (ar) / 16384 (eof)",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Train Win Stg1",
        "description": "Stage-1 predictive filter training window length [frames]",
    },
    {
        "flag": "--pf-nbtrain2",
        "key": "pf_nbtrain2",
        "arg": "<int>",
        "type": "int",
        "default": "2048 (ar) / 32768 (eof)",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Train Win Stg2",
        "description": "Stage-2 predictive filter training window length [frames]",
    },
    {
        "flag": "--pf-minsamples1",
        "key": "pf_minsamples1",
        "arg": "<int>",
        "type": "int",
        "default": "256 (ar) / 12000 (eof)",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Min Samples Stg1",
        "description": "Stage-1 minimum PSOL samples before AR/EOF filter activates",
    },
    {
        "flag": "--pf-minsamples2",
        "key": "pf_minsamples2",
        "arg": "<int>",
        "type": "int",
        "default": "256 (ar) / 24000 (eof)",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Min Samples Stg2",
        "description": "Stage-2 minimum PSOL samples before AR/EOF filter activates",
    },
    {
        "flag": "--pf-warmup-sec",
        "key": "pf_warmup_sec",
        "arg": "<sec>",
        "type": "float",
        "default": "0",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Warmup [s]",
        "description": "Extra closed-loop warmup [s] before starting science integration",
    },
    {
        "flag": "--pf-mgain-exp",
        "key": "pf_mgain_exp",
        "arg": "<float>",
        "type": "float",
        "default": "0.50",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Modal Exp",
        "description": "Stage-1/default modal PF mix rolloff exponent applied to mgainfact",
    },
    {
        "flag": "--pf-mgain-exp2",
        "key": "pf_mgain_exp2",
        "arg": "<float>",
        "type": "float",
        "default": "(same as --pf-mgain-exp)",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Modal Exp (Stg 2)",
        "description": "Optional Stage-2 modal PF mix rolloff exponent applied to mgainfact (defaults to --pf-mgain-exp)",
    },
    {
        "flag": "--nbloop",
        "key": "nbloop",
        "arg": "<int>",
        "type": "int",
        "default": "1",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Hadamard Loops",
        "description": "Hadamard response-matrix averaging cycles per AO stage",
    },
    {
        "flag": "--selfrm-modes",
        "key": "selfrm_modes",
        "arg": "<int>",
        "type": "int",
        "default": "256",
        "group": "Calibration",
        "tier": "advanced",
        "label": "selfRM Modes",
        "description": "Maximum number of modes probed in selfRM optical-gain calibration",
    },
    {
        "flag": "--selfrm-iter",
        "key": "selfrm_iter",
        "arg": "<int>",
        "type": "int",
        "default": "1",
        "group": "Calibration",
        "tier": "advanced",
        "label": "selfRM Iterations",
        "description": "On-sky selfRM averaging iterations during closed-loop science",
    },
    {
        "flag": "--no-selfrm",
        "key": "no_selfrm",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Skip selfRM",
        "description": "Skip calibration and on-sky selfRM acquisition",
    },
    {
        "flag": "--save-rm",
        "key": "save_rm",
        "arg": "<dir>",
        "type": "string",
        "default": "_work/ao3k_scexao_rm",
        "group": "Output & Telemetry",
        "tier": "advanced",
        "label": "Save RM Dir",
        "description": "Directory to archive Stage-1 & Stage-2 calibrated response matrices",
        "customizer_omit": True,
    },
    {
        "flag": "--load-rm",
        "key": "load_rm",
        "arg": "<dir>",
        "type": "string",
        "default": "",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Load RM Dir",
        "description": "Load pre-saved response matrices from <dir>/stage1 and <dir>/stage2",
    },
    {
        "flag": "--outdir",
        "key": "outdir",
        "arg": "<dir>",
        "type": "string",
        "default": "_work/ao3k_scexao",
        "group": "Output & Telemetry",
        "tier": "advanced",
        "label": "Output Dir",
        "description": "Output directory for REPORT.md, plots, metrics JSON, and run_options.json",
        "customizer_omit": True,
    },
    {
        "flag": "--save-telemetry",
        "key": "save_telemetry",
        "arg": "[none|standard|speckle|truth]",
        "type": "choice",
        "choices": ["none", "standard", "speckle", "truth"],
        "default": "none",
        "group": "Output & Telemetry",
        "tier": "core",
        "label": "Telemetry Mode",
        "description": "Record WFS, PSF, DM, and modal FITS cubes (none/standard/speckle/truth)",
    },
    {
        "flag": "--telemetry-dir",
        "key": "telemetry_dir",
        "arg": "<dir>",
        "type": "string",
        "default": "<outdir>/telemetry",
        "group": "Output & Telemetry",
        "tier": "advanced",
        "label": "Telemetry Dir",
        "description": (
            "Override telemetry FITS output directory (overwritten unless --keep-telemetry)"
        ),
    },
    {
        "flag": "--keep-telemetry",
        "key": "keep_telemetry",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Output & Telemetry",
        "tier": "advanced",
        "label": "Keep Telemetry",
        "description": "Archive previous telemetry directory (<dir>_<UTC>) instead of erasing it",
    },
    {
        "flag": "--psf-navg",
        "key": "psf_navg",
        "arg": "<int>",
        "type": "int",
        "default": "20 (standard) / 1 (speckle)",
        "group": "Output & Telemetry",
        "tier": "advanced",
        "label": "PSF Subframe N_avg",
        "description": "Science PSF subframe integration count (20 = 100 Hz; 1 = 2 kHz speckle)",
    },
    {
        "flag": "--no-tlm-analysis",
        "key": "no_tlm_analysis",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Analysis & SysID",
        "tier": "advanced",
        "label": "Skip TLM Analysis",
        "description": "Skip post-run milk-mlt-aotlm PSFR & AO optimization report",
    },
    {
        "flag": "--calib-2wfs1dm",
        "key": "calib_2wfs1dm",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Analysis & SysID",
        "tier": "core",
        "label": "2-WFS/1-DM Calib",
        "description": "Run post-loop 2-WFS + 1-DM telemetry calibration (Mab, Mdb, Mda_virt)",
    },
    {
        "flag": "--sysid-modes",
        "key": "sysid_modes",
        "arg": "<int>",
        "type": "int",
        "default": "40",
        "group": "Analysis & SysID",
        "tier": "advanced",
        "label": "SysID Modes",
        "description": "Leading Stage-2 modes solved in --calib-2wfs1dm system identification",
    },
    {
        "flag": "--sysid-whiten-order",
        "key": "sysid_whiten_order",
        "arg": "<int>",
        "type": "int",
        "default": "4",
        "group": "Analysis & SysID",
        "tier": "advanced",
        "label": "SysID Whiten AR(p)",
        "description": "Causal AR(p) temporal whitening filter order W(z) for --calib-2wfs1dm",
    },
    {
        "flag": "--skip-microbench",
        "key": "skip_microbench",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Analysis & SysID",
        "tier": "advanced",
        "label": "Skip Microbench",
        "description": "Skip cacaosim-benchmark kernel sweep when generating COMPUTE_REPORT.md",
    },
    {
        "flag": "--compare-modes",
        "key": "compare_modes",
        "arg": "<file.json>",
        "type": "string",
        "default": "",
        "group": "Analysis & SysID",
        "tier": "advanced",
        "label": "Compare Modes JSON",
        "description": "Optional modular-vs-fused comparison JSON embedded into COMPUTE_REPORT.md",
    },
    {
        "flag": "--dm1-preshaper",
        "key": "dm1_preshaper",
        "arg": "<fits>",
        "type": "string",
        "default": "",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Stg1 DM Pre-Shaper",
        "description": "Stage-1 4 kHz DM pre-shaper MIMO FIR kernel FITS (dmpreshaper)",
    },
    {
        "flag": "--dynpsol1",
        "key": "dynpsol1",
        "arg": "<fits>",
        "type": "string",
        "default": "",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stg1 Dyn PSOL Kernel",
        "description": "Stage-1 Dynamic PSOL impulse kernel FITS (H_mimo / H_diag)",
    },
    {
        "flag": "--dynpsol2",
        "key": "dynpsol2",
        "arg": "<fits>",
        "type": "string",
        "default": "",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stg2 Dyn PSOL Kernel",
        "description": "Stage-2 Dynamic PSOL impulse kernel FITS (H_diag / H_mimo)",
    },
    {
        "flag": "--online-og1",
        "key": "online_og1",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Calibration",
        "tier": "core",
        "label": "Stg1 Online OG",
        "description": "Enable Stage-1 closed-loop DM-poke online optical gain (modalog)",
    },
    {
        "flag": "--og1-ampl",
        "key": "og1_ampl",
        "arg": "<float>",
        "type": "float",
        "default": "0.008",
        "group": "Calibration",
        "tier": "advanced",
        "label": "OG1 Probe Ampl",
        "description": "Stage-1 online-OG DM probe RMS amplitude [um]",
    },
    {
        "flag": "--og1-nbmode",
        "key": "og1_nbmode",
        "arg": "<int>",
        "type": "int",
        "default": "128",
        "group": "Calibration",
        "tier": "advanced",
        "label": "OG1 Mode Count",
        "description": "Stage-1 online-OG maximum probed modal index count",
    },
    {
        "flag": "--og1-stride",
        "key": "og1_stride",
        "arg": "<int>",
        "type": "int",
        "default": "4",
        "group": "Calibration",
        "tier": "advanced",
        "label": "OG1 Mode Stride",
        "description": "Stage-1 online-OG sparse modal probing stride",
    },
    {
        "flag": "--og1-hold",
        "key": "og1_hold",
        "arg": "<int>",
        "type": "int",
        "default": "3",
        "group": "Calibration",
        "tier": "advanced",
        "label": "OG1 Hold Frames",
        "description": "Stage-1 online-OG probe sample-and-hold length [frames]",
    },
    {
        "flag": "--og1-no-apply",
        "key": "og1_no_apply",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Calibration",
        "tier": "advanced",
        "label": "OG1 Shadow Mode",
        "description": "Run Stage-1 modalog in shadow mode without writing aol1_mWFSfact",
    },
    {
        "flag": "--live-2wfs1dm-sec",
        "key": "live_2wfs1dm_sec",
        "arg": "<sec>",
        "type": "float",
        "default": "0",
        "group": "Calibration",
        "tier": "core",
        "label": "Live 2WFS1DM [s]",
        "description": "Capture live Stage-2 2WFS1DM ivdiff burst [s] and apply via mlt.apply2wfs1dm",
    },
    {
        "flag": "--windlayers1",
        "key": "windlayers1",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Predictive Control",
        "tier": "core",
        "label": "Stg1 Windlayers",
        "description": "Enable live Stage-1 mlt-windlayers profiler feeding EOF physics-Gram prior",
    },
    {
        "flag": "--pf-zoh-ridge",
        "key": "pf_zoh_ridge",
        "arg": "<ON|OFF>",
        "type": "choice",
        "choices": ["ON", "OFF"],
        "default": "",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Stg1 PF ZOH Ridge",
        "description": "Stage-1 mkEOFPF ZOH-centered ridge regularization toggle (ON/OFF)",
    },
    {
        "flag": "--pf-zoh-ridge2",
        "key": "pf_zoh_ridge2",
        "arg": "<ON|OFF>",
        "type": "choice",
        "choices": ["ON", "OFF"],
        "default": "",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Stg2 PF ZOH Ridge",
        "description": "Stage-2 mkEOFPF ZOH-centered ridge regularization toggle (ON/OFF)",
    },
    {
        "flag": "--mult-tt",
        "key": "mult_tt",
        "arg": "<float>",
        "type": "float",
        "default": "",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stg1 TT Leak Mult",
        "description": "Optional Stage-1 Tip/Tilt (m=0,1) leak multiplier override",
    },
    {
        "flag": "--mmult-floor",
        "key": "mmult_floor",
        "arg": "<float>",
        "type": "float",
        "default": "",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stg1 Modal Leak Floor",
        "description": "Optional Stage-1 highest-mode leak multiplier floor (unset = flat mult1)",
    },
    {
        "flag": "--mmult-alpha",
        "key": "mmult_alpha",
        "arg": "<float>",
        "type": "float",
        "default": "1.0",
        "group": "Loop Control",
        "tier": "advanced",
        "label": "Stg1 Modal Leak Alpha",
        "description": "Stage-1 power-law exponent shaping per-mode leak multiplier rolloff",
    },
    {
        "flag": "--dmmask-rmax",
        "key": "dmmask_rmax",
        "arg": "<float>",
        "type": "float",
        "default": "",
        "group": "Calibration",
        "tier": "advanced",
        "label": "Stg1 Active DM Mask Rmax",
        "description": "Optional Stage-1 active DM mask outer radius [act] for outer-rim slaving",
    },
    {
        "flag": "--pf-mix-tt",
        "key": "pf_mix_tt",
        "arg": "<float>",
        "type": "float",
        "default": "",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Stg1 LO PF Mix",
        "description": "Optional Stage-1 leading low-order (0..lo-1) predictive mix override [0..1]",
    },
    {
        "flag": "--pf-lo-nmode",
        "key": "pf_lo_nmode",
        "arg": "<int>",
        "type": "int",
        "default": "2",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Stg1 LO Override Modes",
        "description": "Number of leading Stage-1 modes receiving --pf-mix-tt / --mult-tt overrides",
    },
    {
        "flag": "--pf-diff-nmode",
        "key": "pf_diff_nmode",
        "arg": "<int>",
        "type": "int",
        "default": "0",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Diff-Space Modes",
        "description": "Stage-1 leading modes solved in temporal-difference EOF space (0=off)",
    },
    {
        "flag": "--pf-diff-order",
        "key": "pf_diff_order",
        "arg": "<int>",
        "type": "int",
        "default": "0",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Diff-Space Order",
        "description": "Difference-space EOF lookback tap order (0=diagorder, 2..64)",
    },
    {
        "flag": "--pf-diff-reg",
        "key": "pf_diff_reg",
        "arg": "<float>",
        "type": "float",
        "default": "0.05",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Diff-Space Reg",
        "description": "Difference-space EOF relative Tikhonov regularization lambda",
    },
    {
        "flag": "--pf-diff-maxnorm2",
        "key": "pf_diff_maxnorm2",
        "arg": "<float>",
        "type": "float",
        "default": "4.0",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Diff MaxNorm2",
        "description": "Difference-space EOF position-equivalent ||W_m||_2^2 norm cap",
    },
    {
        "flag": "--pf-diff-maxdcgain",
        "key": "pf_diff_maxdcgain",
        "arg": "<float>",
        "type": "float",
        "default": "0.9995",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Diff MaxDCGain",
        "description": "Difference-space EOF exact self-DC gain (0.9..0.99995)",
    },
    {
        "flag": "--pf-gram-halflife",
        "key": "pf_gram_halflife",
        "arg": "<int>",
        "type": "int",
        "default": "0",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Gram Halflife",
        "description": "Extended-memory chunk-Gram exponential half-life [frames] (0=sliding)",
    },
    {
        "flag": "--pf-regime-kmax",
        "key": "pf_regime_kmax",
        "arg": "<int>",
        "type": "int",
        "default": "0",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Regime Anchors",
        "description": "Regime-weighted Gram library max cluster anchor count K (0=off, <=16)",
    },
    {
        "flag": "--pf-fx1",
        "key": "pf_fx1",
        "arg": "<fits>",
        "type": "string",
        "default": "",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Stg1 FX-EOF Kernel",
        "description": "Stage-1 Pass-2 Filtered-X EOF DM impulse kernel FITS",
    },
    {
        "flag": "--pf-fx2",
        "key": "pf_fx2",
        "arg": "<fits>",
        "type": "string",
        "default": "",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Stg2 FX-EOF Kernel",
        "description": "Stage-2 Pass-2 Filtered-X EOF DM impulse kernel FITS",
    },
    {
        "flag": "--pf-dmmodes1",
        "key": "pf_dmmodes1",
        "arg": "<fits>",
        "type": "string",
        "default": "",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Stg1 PF DM Modes",
        "description": "Stage-1 DM modal basis FITS cube for windlayers Fourier physics Gram",
    },
    {
        "flag": "--pf-n-prior",
        "key": "pf_n_prior",
        "arg": "<float>",
        "type": "float",
        "default": "1024",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Wind Prior N",
        "description": "Equivalent sample weight N_prior for Stage-1 windlayers physics Gram",
    },
    {
        "flag": "--pf-wl-switch-decay",
        "key": "pf_wl_switch_decay",
        "arg": "<float>",
        "type": "float",
        "default": "0.20",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "PF Switch Decay",
        "description": "Empirical Gram decay multiplier applied upon windlayers switch trigger",
    },
    {
        "flag": "--wind-switch-sec",
        "key": "wind_switch_sec",
        "arg": "<sec>",
        "type": "float",
        "default": "0",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Wind Switch [s]",
        "description": "Physical time [s] to trigger live phase-continuous wind rotation (0=off)",
    },
    {
        "flag": "--wind-switch-deg",
        "key": "wind_switch_deg",
        "arg": "<deg>",
        "type": "float",
        "default": "60.0",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Wind Switch [deg]",
        "description": "Phase-continuous wind direction rotation angle [deg] at --wind-switch-sec",
    },
    {
        "flag": "--modalwhite",
        "key": "modalwhite",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Analysis & SysID",
        "tier": "core",
        "label": "Modal Whiteness",
        "description": "Run real-time lag>=ceil(tau) closed-loop whiteness monitor (modalwhite)",
    },
    {
        "flag": "--selflearn",
        "key": "selflearn",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Predictive Control",
        "tier": "core",
        "label": "Cascaded Self-Learning",
        "description": "Cascade online Global + Clustered (libgric) self-learning on top of Block-EOF",
    },
    {
        "flag": "--selflearn-modes",
        "key": "selflearn_modes",
        "arg": "<int>",
        "type": "int",
        "default": "128",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Self-Learn Modes",
        "description": "Maximum controlled modal dimension tweaked by cacaopc-selflearn",
    },
    {
        "flag": "--selflearn-kmax",
        "key": "selflearn_kmax",
        "arg": "<int>",
        "type": "int",
        "default": "16",
        "group": "Predictive Control",
        "tier": "advanced",
        "label": "Self-Learn Clusters",
        "description": "Maximum libgric cluster anchors maintained by cacaopc-selflearn",
    },
    {
        "flag": "--no-pyrwfs-tlm",
        "key": "no_pyrwfs_tlm",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Telemetry & Reports",
        "tier": "common",
        "label": "Disable PyWFS Telemetry",
        "description": (
            "Disable live Stage-1 & Stage-2 Pyramid WFS telemetry monitors "
            "(cacao-fpsexec-pyrwfstlm; enabled by default)"
        ),
    },
    {
        "flag": "--pyrwfs-stride",
        "key": "pyrwfs_stride",
        "arg": "<int>",
        "type": "int",
        "default": "auto (~200 Hz)",
        "group": "Telemetry & Reports",
        "tier": "advanced",
        "label": "PyWFS Telemetry Stride",
        "description": (
            "Override Stage-1 frame decimation stride for cacao-fpsexec-pyrwfstlm "
            "(Stage-2 scales proportionally to match physical cadence)"
        ),
    },
    {
        "flag": "--petal-ctrl",
        "key": "petal_ctrl",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal-Unwrap Controller",
        "description": "Enable Stage-1 passive petal-unwrap JIT controller (petal-1 -> dm01disp06)",
    },
    {
        "flag": "--petal-use-sign",
        "key": "petal_use_sign",
        "arg": "<mode>",
        "type": "str",
        "default": "auto",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal Sign Mode",
        "description": "Petal sign disambiguation mode: auto (from chrom_sep), 1 (fused-silica), or 0 (achrom trial)",
    },
    {
        "flag": "--petal-alpha",
        "key": "petal_alpha",
        "arg": "<float>",
        "type": "float",
        "default": "0.0008",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal EMA Alpha",
        "description": "Petal EMA smoothing factor per Stage-1 WFS frame",
    },
    {
        "flag": "--petal-warmup",
        "key": "petal_warmup",
        "arg": "<int>",
        "type": "int",
        "default": "1500",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal Warmup Frames",
        "description": "Petal averaging warmup frames before jump trigger is armed",
    },
    {
        "flag": "--petal-th-even",
        "key": "petal_th_even",
        "arg": "<float>",
        "type": "float",
        "default": "0.58",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal Even Threshold",
        "description": "Petal even-mode jump detection threshold in waves",
    },
    {
        "flag": "--petal-th-sign",
        "key": "petal_th_sign",
        "arg": "<float>",
        "type": "float",
        "default": "0.35",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal Sign Threshold",
        "description": "Petal odd chromatic sign confirmation threshold",
    },
    {
        "flag": "--petal-enable-at",
        "key": "petal_enable_at",
        "arg": "<phase>",
        "type": "str",
        "default": "warmup",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal Enable Phase",
        "description": "When to enable petal jumps: warmup (default) or science (t_phys=0)",
    },
    {
        "flag": "--petal-test-inject",
        "key": "petal_test_inject",
        "arg": "<spec>",
        "type": "str",
        "default": "",
        "group": "Loop Operation",
        "tier": "advanced",
        "label": "Petal Test Injection",
        "description": "Optional test petal step injection spec written to dm01disp07 at t_phys=0",
    },
    {
        "flag": "--no-wind-var",
        "key": "no_wind_var",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Disable Wind Drift",
        "description": "Disable smooth wind speed & direction meandering (default: ON)",
    },
    {
        "flag": "--wind-var-scale",
        "key": "wind_var_scale",
        "arg": "<float>",
        "type": "float",
        "default": "1.0",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Wind Drift Scale",
        "description": "Amplitude multiplier for smooth wind speed & direction meandering",
    },
    {
        "flag": "--no-wind-burst",
        "key": "no_wind_burst",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Disable Wind Bursts",
        "description": "Disable stochastic atmospheric wind bursts & Cn2 surges (default: ON)",
    },
    {
        "flag": "--wind-burst-scale",
        "key": "wind_burst_scale",
        "arg": "<float>",
        "type": "float",
        "default": "1.0",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Wind Burst Scale",
        "description": "Strength multiplier for non-stationary atmospheric wind bursts",
    },
    {
        "flag": "--no-vib",
        "key": "no_vib",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Disable Vibrations",
        "description": "Disable stochastic telescope & optical-bench vibrations (default: ON)",
    },
    {
        "flag": "--vib-rms-nm",
        "key": "vib_rms_nm",
        "arg": "<float>",
        "type": "float",
        "default": "45.0",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Vibration RMS [nm]",
        "description": "Total telescope & optical-bench vibration OPD RMS [nm] (14.5..138 Hz)",
    },
    {
        "flag": "--no-petal",
        "key": "no_petal",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Disable Petaling",
        "description": "Disable thermally induced slow-varying pupil petaling / LWE (default: ON)",
    },
    {
        "flag": "--petal-rms-nm",
        "key": "petal_rms_nm",
        "arg": "<float>",
        "type": "float",
        "default": "1000.0",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Petaling RMS [nm]",
        "description": "Total thermally induced island petaling (LWE) OPD RMS [nm]",
    },
    {
        "flag": "--petal-tau-s",
        "key": "petal_tau_s",
        "arg": "<float>",
        "type": "float",
        "default": "3.0",
        "group": "Atmosphere & Timing",
        "tier": "advanced",
        "label": "Petaling Tau [s]",
        "description": "Correlation timescale [s] for slow thermal petaling evolution",
    },
    {
        "flag": "--no-perturb",
        "key": "no_perturb",
        "arg": "",
        "type": "bool",
        "default": "OFF",
        "group": "Atmosphere & Timing",
        "tier": "core",
        "label": "Disable All Perturb",
        "description": "Disable wind meandering, wind bursts, vibrations & thermal petaling",
    },
    {
        "flag": "-h, --help",
        "key": "help",
        "arg": "",
        "type": "bool",
        "default": "",
        "group": "General",
        "tier": "advanced",
        "label": "Help",
        "description": "Print runner CLI usage message and exit",
        "customizer_omit": True,
    },
]

CACAOLOOP_ENV_VARS: list[dict[str, str]] = [
    {"name": "CACAO_LOOPNAME", "default": "ao3k / scexao / llowfs", "group": "Loop Identity",
     "description": "CACAO loop name prefix for stage 1 / 2 / 3"},
    {"name": "CACAO_LOOPNUMBER", "default": "1 / 2 / 3", "group": "Loop Identity",
     "description": "Numeric CACAO loop index N (prefixes streams as aolN_*)"},
    {"name": "CACAO_DMINDEX", "default": "01 / 02 / 02", "group": "Hardware Geometry",
     "description": "Two-digit DM combiner index (dm01disp / dm02disp)"},
    {"name": "CACAO_DMX", "default": "64 / 50 / 50", "group": "Hardware Geometry",
     "description": "Deformable mirror actuator grid width X"},
    {"name": "CACAO_DMY", "default": "64 / 50 / 50", "group": "Hardware Geometry",
     "description": "Deformable mirror actuator grid height Y"},
    {"name": "CACAO_PUP_DIAM_ACT", "default": "60.0 / 46.0 / 46.0", "group": "Hardware Geometry",
     "description": "Illuminated telescope pupil diameter across DM actuators"},
    {"name": "CACAO_WFSSTREAM", "default": "csim_wfs_nir/vis/lowfs", "group": "Hardware Geometry",
     "description": "Input WFS camera SHM stream linked into aolN_wfsim"},
    {"name": "CACAO_WFSX", "default": "160 / 120 / 64", "group": "Hardware Geometry",
     "description": "Wavefront sensor camera frame width X [pixels]"},
    {"name": "CACAO_WFSY", "default": "160 / 120 / 64", "group": "Hardware Geometry",
     "description": "Wavefront sensor camera frame height Y [pixels]"},
    {"name": "CACAO_LOOPROOTDIR", "default": "${PWD}/${LOOPNAME}-rootdir", "group": "Runtime & GPU",
     "description": "Working root directory for loop configs, matrices, and FPS state"},
    {"name": "CACAO_GPUINDEX", "default": "0", "group": "Runtime & GPU",
     "description": "CUDA GPU device index for compstrCM SVD and default MVM device"},
    {"name": "CACAO_MVM_GPUINDEX", "default": "-1 (Stg1/2), 99 (Stg3)", "group": "Runtime & GPU",
     "description": "Override MVMextract GPUindex (<0 CUDA Graph, 0..N cuBLAS, 99 CPU BLAS)"},
    {"name": "CACAO_CUDA_MPS", "default": "1", "group": "Runtime & GPU",
     "description": "Enable per-sandbox NVIDIA CUDA MPS daemon (0 disables MPS)"},
    {"name": "CACAO_WFSFRATE", "default": "100", "group": "Timing & Latency",
     "description": "Expected WFS wall-clock frame rate [Hz] for calibration pacing"},
    {"name": "CACAO_LATENCYHARDWFR", "default": "1.5", "group": "Timing & Latency",
     "description": "Measured hardware loop latency [WFS frames]"},
    {"name": "CACAO_LATENCYSOFTWFR", "default": "1.65", "group": "Timing & Latency",
     "description": "Effective software + hardware loop latency [WFS frames]"},
    {"name": "CACAO_PSOL_WFSFACT", "default": "1.0", "group": "Timing & Latency",
     "description": "Pseudo open-loop (PSOL) WFS residual scaling factor"},
    {"name": "CACAO_WFSZPO_GAIN", "default": "1.0", "group": "Timing & Latency",
     "description": "Optical-gain scaling factor applied to WFS zero-point offset (wfszpo)"},
    {"name": "CACAO_TBUFF_SIZE", "default": "256", "group": "Timing & Latency",
     "description": "Modal telemetry ring-buffer depth [frames]"},
    {"name": "CACAO_PF_MODE", "default": "ar", "group": "Predictive Control",
     "description": "Predictive filter mode: 'ar' (diagonal AR) or 'eof' (block cross-mode EOF)"},
    {"name": "CACAO_PF_ORDER", "default": "8", "group": "Predictive Control",
     "description": "Predictive filter temporal tap lookback order P"},
    {"name": "CACAO_PF_DIAGORDER", "default": "16", "group": "Predictive Control",
     "description": "Bootstrap diagonal AR tap order used during Block-EOF warmup"},
    {"name": "CACAO_PF_BLOCKSIZE", "default": "128", "group": "Predictive Control",
     "description": "Block-EOF coupled modal block size B"},
    {"name": "CACAO_PF_NBTRAIN", "default": "2048", "group": "Predictive Control",
     "description": "Rolling PSOL training window size [frames] for mkARPF / mkEOFPF"},
    {"name": "CACAO_PF_MINSAMPLES", "default": "256", "group": "Predictive Control",
     "description": "Minimum PSOL samples required before activating full AR/EOF filter"},
    {"name": "CACAO_PF_DIAGMINSAMPLES", "default": "256", "group": "Predictive Control",
     "description": "Minimum PSOL samples before activating Block-EOF diagonal AR bootstrap"},
    {"name": "CACAO_PF_UPDATEPERIOD", "default": "4 (Stg1/3), 8 (Stg2)",
     "group": "Predictive Control", "description": "Filter re-solve cadence [WFS frames]"},
    {"name": "CACAO_PF_REG", "default": "0.005", "group": "Predictive Control",
     "description": "Tikhonov ridge regularization parameter lambda for PF solver"},
    {"name": "CACAO_PF_MAXNORM2", "default": "(unset)", "group": "Predictive Control",
     "description": "Optional per-row ||F_m||_2^2 filter norm ceiling"},
    {"name": "CACAO_PF_MAXDCGAIN", "default": "(unset)", "group": "Predictive Control",
     "description": "Optional mkEOFPF self-DC gain ceiling override"},
    {"name": "CACAO_PF_NTHREADS", "default": "4", "group": "Predictive Control",
     "description": "OpenMP thread count for real-time applyARPF / applyEOFPF execution"},
    {"name": "CACAO_PF_MKTHREADS", "default": "8", "group": "Predictive Control",
     "description": "OpenMP thread count for background mkARPF / mkEOFPF solver"},
    {"name": "CACAO_PF_MIX", "default": "0.90 (Stg1/2), 0.50 (Stg3)", "group": "Predictive Control",
     "description": "Predictive control mix weight [0..1] blending PF output with integrator"},
    {"name": "CACAO_PF_MIX_TT", "default": "(unset)", "group": "Predictive Control",
     "description": "Optional leading low-order (0..lo-1) predictive mix weight override [0..1]"},
    {"name": "CACAO_PF_LO_NMODE", "default": "2", "group": "Predictive Control",
     "description": "Leading modes receiving CACAO_PF_MIX_TT / CACAO_LOOPMULT_TT overrides"},
    {"name": "CACAO_PF_MGAIN_EXP", "default": "0.50", "group": "Predictive Control",
     "description": "Exponent rolling off PF mix across modes via mgainfact^exp"},
    {"name": "CACAO_PF_DIFF_NMODE", "default": "0", "group": "Predictive Control",
     "description": "Leading modes solved in temporal-difference EOF space (0=off)"},
    {"name": "CACAO_PF_DIFF_ORDER", "default": "0", "group": "Predictive Control",
     "description": "Difference-space EOF lookback tap order (0=diagorder, 2..64)"},
    {"name": "CACAO_PF_DIFF_REG", "default": "0.05", "group": "Predictive Control",
     "description": "Difference-space EOF relative Tikhonov lambda"},
    {"name": "CACAO_PF_DIFF_MAXNORM2", "default": "4.0", "group": "Predictive Control",
     "description": "Difference-space EOF position-equivalent ||W_m||_2^2 cap"},
    {"name": "CACAO_PF_DIFF_MAXDCGAIN", "default": "0.9995", "group": "Predictive Control",
     "description": "Difference-space EOF exact self-DC gain (0.9..0.99995)"},
    {"name": "CACAO_PF_MAXWAITUS", "default": "3000", "group": "Predictive Control",
     "description": "Maximum wait timeout [us] for applyPF synchronization with mfilt"},
    {"name": "CACAO_DYNPSOL_KERNEL", "default": "(unset)", "group": "Loop Control",
     "description": "Dynamic PSOL impulse kernel FITS path (H_mimo / H_diag) for modalfilter"},
    {"name": "CACAO_PF_ZOH_RIDGE", "default": "(unset)", "group": "Predictive Control",
     "description": "mkEOFPF ZOH-centered ridge regularization toggle (ON/OFF)"},
    {"name": "CACAO_PF_GRAM_HALFLIFE", "default": "0", "group": "Predictive Control",
     "description": "Extended-memory chunk-Gram exponential half-life [frames] (0=sliding)"},
    {"name": "CACAO_PF_DM_KERNEL", "default": "(unset)", "group": "Predictive Control",
     "description": "Pass-2 Filtered-X EOF DM impulse kernel FITS (H_diag / H_mimo)"},
    {"name": "CACAO_PF_WL_LAYERS", "default": "(unset)", "group": "Predictive Control",
     "description": "Live mlt-windlayers layer SHM stream consumed by mkEOFPF physics Gram"},
    {"name": "CACAO_PF_DMMODES", "default": "(unset)", "group": "Predictive Control",
     "description": "DM modal basis cube FITS for mkEOFPF Fourier-space physics Gram"},
    {"name": "CACAO_PF_PUP_DIAM", "default": "7.95", "group": "Predictive Control",
     "description": "Telescope pupil diameter [m] used by mkEOFPF windlayers physics Gram"},
    {"name": "CACAO_PF_DM_DX", "default": "0.0", "group": "Predictive Control",
     "description": "DM actuator pitch [m] override for mkEOFPF physics Gram (0=auto)"},
    {"name": "CACAO_PF_FRATE_HZ", "default": "1000.0", "group": "Predictive Control",
     "description": "Physical loop frame rate [Hz] for mkEOFPF wind-phase propagation"},
    {"name": "CACAO_PF_N_PRIOR", "default": "1024.0", "group": "Predictive Control",
     "description": "Equivalent sample weight N_prior for windlayers physics-Gram prior"},
    {"name": "CACAO_PF_WL_SWITCH_DECAY", "default": "0.20", "group": "Predictive Control",
     "description": "Empirical Gram decay multiplier upon windlayers switch trigger"},
    {"name": "CACAO_PF_REGIME_KMAX", "default": "0", "group": "Predictive Control",
     "description": "Regime-weighted Gram library max anchor count K (0=off, <=16)"},
    {"name": "CACAO_PF_REGIME_KAPPA", "default": "0.10", "group": "Predictive Control",
     "description": "Regime-weighted Gram similarity blending floor kappa"},
    {"name": "CACAO_PF_REGIME_BW", "default": "3.0", "group": "Predictive Control",
     "description": "Regime-weighted Gram Gaussian kernel bandwidth"},
    {"name": "CACAO_PF_REGIME_RLIM", "default": "4.0", "group": "Predictive Control",
     "description": "Regime-weighted Gram leader-clustering new-anchor radius threshold"},
    {"name": "CACAO_PF_MR_ENABLE", "default": "OFF", "group": "Predictive Control",
     "description": "Enable multi-rate zero-DC temporal-difference velocity output in mkEOFPF/applyEOFPF"},
    {"name": "CACAO_PF_MR_SUBSTEPS", "default": "1", "group": "Predictive Control",
     "description": "Multi-rate DM command sub-steps K_sub per WFS exposure frame"},
    {"name": "CACAO_PF_MR_VELGAIN", "default": "1.0", "group": "Predictive Control",
     "description": "Multi-rate centered linear-ramp velocity gain multiplier"},
    {"name": "CACAO_PF_MR_VEL_REG_MULT", "default": "3.5", "group": "Predictive Control",
     "description": "Multi-rate velocity ridge regularization multiplier on top of pf_reg"},
    {"name": "CACAO_PF_MR_PACER_OUT", "default": "OFF", "group": "Loop Control",
     "description": "Route modalfilter output via aolN_modevalDM_traj to mvalpacer (suppresses dual-writer race)"},
    {"name": "CACAO_WFS_DARK_ADU", "default": "0.0", "group": "Timing & Latency",
     "description": "Uniform WFS detector dark/bias pedestal [ADU] subtracted prior to normalization"},
    {"name": "CACAO_WFS_DARKSUB", "default": "OFF", "group": "Timing & Latency",
     "description": "Enable dark/bias pedestal subtraction in acquWFS (ON/OFF)"},
    {"name": "CACAO_WFS_NORMFLOOR", "default": "1.0", "group": "Timing & Latency",
     "description": "Minimum flux denominator floor in acquWFS intensity normalization (0.001 for faint stars)"},
    {"name": "CACAO_SELFLEARN_ENABLE", "default": "0", "group": "Predictive Control",
     "description": "Cascade cacaopc-selflearn (Global + Clustered libgric RLS) downstream of applyEOFPF (0/1)"},
    {"name": "CACAO_SELFLEARN_MODES", "default": "128", "group": "Predictive Control",
     "description": "Maximum modal dimension tweaked by cacaopc-selflearn"},
    {"name": "CACAO_SELFLEARN_KMAX", "default": "16", "group": "Predictive Control",
     "description": "Maximum libgric cluster anchors maintained by cacaopc-selflearn"},
    {"name": "CACAO_SELFLEARN_KEYMODE", "default": "0", "group": "Predictive Control",
     "description": "GRIC state key mode (0=TT2_E2, 1=E1, 2=WFS_LO4, 3=TT2_DM2_E2, 4=REGIME)"},
    {"name": "CACAO_SELFLEARN_QSHARED", "default": "2", "group": "Predictive Control",
     "description": "Shared low-order cross-mode feature count in cacaopc-selflearn (0..8)"},
    {"name": "CACAO_SELFLEARN_RLIM", "default": "2.0", "group": "Predictive Control",
     "description": "GRIC cluster spawn radius in standardized key space"},
    {"name": "CACAO_SELFLEARN_MAX_WFS_GAIN", "default": "0.40", "group": "Predictive Control",
     "description": "Physical stability cap on learned WFS optical-gain weight"},
    {"name": "CACAO_SELFLEARN_LAM0", "default": "20.0", "group": "Predictive Control",
     "description": "Level-0 global online RLS ridge regularization in cacaopc-selflearn"},
    {"name": "CACAO_SELFLEARN_LAM1", "default": "200.0", "group": "Predictive Control",
     "description": "Level-1 per-cluster RLS shrinkage ridge in cacaopc-selflearn"},
    {"name": "CACAO_SELFLEARN_MAX_TWEAK", "default": "0.25", "group": "Predictive Control",
     "description": "Hard per-mode absolute tweak clamp [modal units] in cacaopc-selflearn"},
    {"name": "CACAO_SELFLEARN_NWARMUP", "default": "40", "group": "Predictive Control",
     "description": "Per-cluster shrinkage warmup frame count in cacaopc-selflearn"},
    {"name": "CACAO_SELFLEARN_KEYWARMUP", "default": "200", "group": "Predictive Control",
     "description": "Key standardization warmup frame count in cacaopc-selflearn"},
    {"name": "CACAO_SELFLEARN_NL_MODE", "default": "0", "group": "Predictive Control",
     "description": "Nonlinear PyWFS basis (0=linear, 1=+odd sat/OG/TT, 2=+shared WFS xtalk)"},
    {"name": "CACAO_LOOPGAIN", "default": "0.35 / 0.35 / 0.20", "group": "Loop Control",
     "description": "Closed-loop modal integrator gain (stage 1 / 2 / 3)"},
    {"name": "CACAO_LOOPMULT", "default": "0.98 / 0.98 / 0.99", "group": "Loop Control",
     "description": "Closed-loop leaky integrator multiplier (stage 1 / 2 / 3)"},
    {"name": "CACAO_LOOPMULT_TT", "default": "(unset)", "group": "Loop Control",
     "description": "Optional Tip/Tilt (m=0,1) leaky integrator multiplier override"},
    {"name": "CACAO_MMULT_FLOOR", "default": "(unset)", "group": "Loop Control",
     "description": "Optional highest-mode leak multiplier floor for high-order rim stabilization"},
    {"name": "CACAO_MMULT_ALPHA", "default": "1.0", "group": "Loop Control",
     "description": "Power-law exponent shaping per-mode leak multiplier rolloff"},
    {"name": "CACAO_DMMASK_RMAX", "default": "(unset)", "group": "Calibration",
     "description": "Optional active DM mask outer radius [act] to slave unilluminated rim actuators"},
    {"name": "CACAO_LOOPLIMIT_TT", "default": "2.5 (Stg1), unset (Stg2/3)", "group": "Loop Control",
     "description": "Tip/Tilt (m=0,1) modal stroke limit [um] override on mlimitfact"},
    {"name": "CACAO_SVDLIM", "default": "0.004 / 0.004 / 0.02", "group": "Calibration",
     "description": "SVD singular-value cutoff threshold for control matrix inversion"},
    {"name": "CACAO_CPAMAX", "default": "28 / 22 / 4", "group": "Calibration",
     "description": "Maximum controlled spatial frequency [cycles/aperture] for KL/Zernike basis"},
    {"name": "CACAO_RCPAMAX", "default": "28.5 / 22.5 / 4.5", "group": "Calibration",
     "description": "Radial spatial frequency ceiling [cycles/aperture] for modal basis"},
    {"name": "CACAO_DELTACPA", "default": "1.0", "group": "Calibration",
     "description": "Spatial frequency bin step [cycles/aperture] for modal basis"},
    {"name": "CACAO_MGAIN_ALPHA", "default": "0.8 (Stg1/2), 0.4 (Stg3)", "group": "Loop Control",
     "description": "Power-law exponent shaping per-mode gain rolloff"},
    {"name": "CACAO_MGAIN_FLOOR", "default": "0.10 (Stg1/2), 0.40 (Stg3)", "group": "Loop Control",
     "description": "Minimum modal gain factor at the highest controlled mode"},
    {"name": "CACAO_MGAIN_TT", "default": "1.0", "group": "Loop Control",
     "description": "Modal gain scaling factor for tip/tilt modes 0 and 1"},
    {"name": "CACAO_MLAT_NBITER", "default": "30", "group": "Calibration",
     "description": "Number of poke-sequence iterations for mlat hardware latency measurement"},
    {"name": "CACAO_MLAT_CPA", "default": "4.0 (Stg1/2), 1.0 (Stg3)", "group": "Calibration",
     "description": "Spatial frequency [cpa] of Fourier poke pattern used by mlat"},
    {"name": "CACAO_NMODES_DIRECT", "default": "14", "group": "Calibration",
     "description": "Direct Zernike mode count used by Stage-3 LLOWFS modal calibration"},
    {"name": "CACAO_WFSMASK_RAD", "default": "20.0", "group": "Calibration",
     "description": "WFS active pupil mask radius [pixels] for Stage-3 LLOWFS"},
    {"name": "CACAO_SELFRM_ZSIZE", "default": "8", "group": "Calibration",
     "description": "Temporal modulation depth [frames] per mode during selfRM measurement"},
    {"name": "CACAO_POKEAMPL", "default": "0.015 / 0.010 / 0.015", "group": "Calibration",
     "description": "DM poke amplitude [um RMS] during response-matrix acquisition"},
    {"name": "CACAO_FAST_CALIB", "default": "0", "group": "Calibration",
     "description": "Enable unthrottled lockstep step-and-shoot RM via csim_htsim (0/1)"},
    {"name": "CACAO_HTSIM_UNIT", "default": "csim_htsim", "group": "Runtime & GPU",
     "description": "Fused cacaosim htsim FPS unit name targeted by fast calibration"},
]


def _find_cacaosim_schema_path() -> Path | None:
    """Locate compiled cacaosim options_schema.json across install and build trees."""
    candidates: list[Path] = []
    milk_root = os.environ.get("MILK_INSTALL_ROOT") or os.environ.get("MILK_ROOT")
    if milk_root:
        candidates.append(Path(milk_root) / "share" / "cacaosim" / "options_schema.json")
    src_parent = _REPO_ROOT.parent
    for inst in sorted((src_parent / "milk" / "_install").glob("milk-*"), reverse=True):
        candidates.append(inst / "share" / "cacaosim" / "options_schema.json")
    candidates.append(
        src_parent / "milk" / "_install" / "share" / "cacaosim" / "options_schema.json"
    )
    csim_dir = Path(os.environ.get("CACAOSIM_SRC_DIR", str(src_parent / "cacaosim")))
    candidates.append(csim_dir / "_build" / "options_schema.json")
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def load_cacaosim_schema() -> dict[str, object]:
    """Load cacaosim's compiled options_schema.json (or invoke cacaosim-bench-view)."""
    path = _find_cacaosim_schema_path()
    if path is not None:
        loaded = load_json_safe(path)
        if loaded and isinstance(loaded.get("bench_options"), list):
            return loaded
    try:
        proc = subprocess.run(
            ["cacaosim-bench-view", "--list-options", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip().startswith("{"):
            parsed = json.loads(proc.stdout)
            if isinstance(parsed, dict):
                return parsed
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        pass
    return {
        "schema_version": 1,
        "source": "cacaosim",
        "bench_options": [],
        "fps_units": [],
        "cli_options": [],
    }


def _clean_c_string_literal(raw: str) -> str:
    """Concatenate adjacent C string literals into a single clean string."""
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
    return "".join(parts).replace('\\"', '"').replace("\\n", " ").strip()


def _clean_c_default_val(raw: str, fptype_raw: str = "") -> str:
    """Normalize a C static initializer literal for table display."""
    s = raw.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if fptype_raw == "FPTYPE_ONOFF":
        if s in ("0", "0u", "0U", "false"):
            return "OFF"
        if s in ("1", "1u", "1U", "true"):
            return "ON"
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?[fF]", s):
        s = s[:-1]
    if re.fullmatch(r"-?[0-9]+[uUlL]+", s):
        s = re.sub(r"[uUlL]+$", "", s)
    if s.endswith(".0") and len(s) > 2:
        return s
    return s


def _parse_atmturb_fps_c(path: Path) -> dict[str, object] | None:
    """Parse one AtmosphericTurbulence/*_FPS.c file into a structured FPS unit dict."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    defaults: dict[str, str] = {}
    for m in _C_DEFAULT_RE.finditer(text):
        defaults[m.group(1)] = _clean_c_default_val(m.group(2))

    # Strip line-continuation backslashes inside macro blocks before matching X(...)
    unwrapped = text.replace("\\\n", "\n")

    meta: dict[str, str] = {}
    for m in _RUNNABLE_FIELD_RE.finditer(unwrapped):
        meta[m.group(1)] = _clean_c_string_literal(m.group(2))
    exp_m = _EXPORT_FPSEXEC_RE.search(unwrapped)
    binary = f"{exp_m.group(1)}-fpsexec-{exp_m.group(2)}" if exp_m else ""
    cmdkey = meta.get("cmdkey") or path.stem.replace("atmturb_", "").replace("_FPS", "")
    fps_name = meta.get("fps_name") or f"atmturb_{cmdkey}"
    desc = meta.get("description") or f"milkatmturb {cmdkey} compute unit"

    params: list[dict[str, object]] = []
    for m in _X_MACRO_CALL_RE.finditer(unwrapped):
        kw = m.group(1).strip()
        var_name = m.group(2).strip()
        fptype_raw = m.group(3).strip()
        is_primary = m.group(4).strip() == "1"
        flags_raw = m.group(5).strip()
        pdesc = _clean_c_string_literal(m.group(6))

        writerun = "FPFLAG_WRITERUN" in flags_raw
        is_output = "FPFLAG_DEFAULT_OUTPUT" in flags_raw or "FPFLAG_STATUS" in flags_raw
        access = "output" if is_output else ("live" if writerun else "init")
        params.append(
            {
                "keyword": kw,
                "type": _FPTYPE_MAP.get(fptype_raw, fptype_raw.lower()),
                "default": defaults.get(var_name, ""),
                "access": access,
                "writerun": writerun,
                "primary": is_primary,
                "trigger": "FPFLAG_STREAM_RUN_REQUIRED" in flags_raw,
                "description": pdesc,
                "anchor": make_fps_opt_anchor("milkatmturb", cmdkey, kw),
            }
        )

    return {
        "package": "milkatmturb",
        "unit": cmdkey,
        "cmdkey": cmdkey,
        "fps_name": fps_name,
        "binary": binary or f"milk-fpsexec-atmturb-{cmdkey}",
        "description": desc,
        "anchor": make_fps_unit_anchor("milkatmturb", cmdkey),
        "params": params,
    }


_CACAO_PREDICTIVE_FPS_FILES: tuple[tuple[str, str], ...] = (
    ("AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_mkARPF.c", "mkARPF"),
    ("AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_applyARPF.c", "applyARPF"),
    ("AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_mkEOFPF.c", "mkEOFPF"),
    ("AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_applyEOFPF.c", "applyEOFPF"),
    ("AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_selflearn.c", "selflearn"),
    ("AOloopControl/modalfilter.c", "modalfilter"),
    ("AOloopControl/modalwhite.c", "modalwhite"),
)


def _parse_cacao_fps_c(path: Path, unit_fallback: str) -> dict[str, object] | None:
    """Parse one CACAO MILK_RUNNABLE C source file into a structured FPS unit dict."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    raw_defaults: dict[str, str] = {}
    for m in _C_STATIC_VAR_DEFAULT_RE.finditer(text):
        raw_defaults[m.group(1)] = m.group(2).strip()

    unwrapped = text.replace("\\\n", "\n")

    meta: dict[str, str] = {}
    for m in _RUNNABLE_FIELD_RE.finditer(unwrapped):
        meta[m.group(1)] = _clean_c_string_literal(m.group(2))
    exp_m = _EXPORT_FPSEXEC_RE.search(unwrapped)
    binary = f"{exp_m.group(1)}-fpsexec-{exp_m.group(2)}" if exp_m else ""
    cmdkey = meta.get("cmdkey") or unit_fallback
    fps_name = meta.get("fps_name") or unit_fallback
    desc = meta.get("description") or f"cacao {cmdkey} compute unit"

    params: list[dict[str, object]] = []
    seen_kw: set[str] = set()
    for m in _X_MACRO_ANY_CALL_RE.finditer(unwrapped):
        kw = m.group(1).strip()
        if kw in seen_kw:
            continue
        seen_kw.add(kw)
        var_name = m.group(2).strip()
        fptype_raw = m.group(3).strip()
        is_primary = m.group(4).strip() == "1"
        flags_raw = m.group(5).strip()
        pdesc = _clean_c_string_literal(m.group(6))

        writerun = "FPFLAG_WRITERUN" in flags_raw
        is_output = "FPFLAG_DEFAULT_OUTPUT" in flags_raw or "FPFLAG_STATUS" in flags_raw
        access = "output" if is_output else ("live" if writerun else "init")
        raw_def = raw_defaults.get(var_name, "")
        params.append(
            {
                "keyword": kw,
                "type": _FPTYPE_MAP.get(fptype_raw, fptype_raw.lower()),
                "default": _clean_c_default_val(raw_def, fptype_raw) if raw_def else "",
                "access": access,
                "writerun": writerun,
                "primary": is_primary,
                "trigger": "FPFLAG_STREAM_RUN_REQUIRED" in flags_raw
                or "FPFLAG_DEFAULT_TRIGGER_STREAM" in flags_raw,
                "description": pdesc,
                "anchor": make_fps_opt_anchor("cacao", cmdkey, kw),
            }
        )

    if not params:
        return None
    return {
        "package": "cacao",
        "unit": cmdkey,
        "cmdkey": cmdkey,
        "fps_name": fps_name,
        "binary": binary or f"cacao-fpsexec-{cmdkey}",
        "description": desc,
        "anchor": make_fps_unit_anchor("cacao", cmdkey),
        "params": params,
    }


def extract_cacao_predictive_fps_units() -> list[dict[str, object]]:
    """Extract CACAO predictive-control, modalfilter, and modalwhite FPS units from C sources."""
    src_parent = _REPO_ROOT.parent
    cacao_root = Path(os.environ.get("CACAO_SRC_DIR", str(src_parent / "cacao")))
    units: list[dict[str, object]] = []
    if cacao_root.is_dir():
        for rel_path, unit_fb in _CACAO_PREDICTIVE_FPS_FILES:
            cpath = cacao_root / rel_path
            if cpath.is_file():
                parsed = _parse_cacao_fps_c(cpath, unit_fb)
                if parsed is not None:
                    units.append(parsed)
    return units


def extract_atmturb_fps_units() -> list[dict[str, object]]:
    """Extract all 5 milkatmturb FPS units from AtmosphericTurbulenceSimul sources."""
    src_parent = _REPO_ROOT.parent
    atmturb_root = Path(
        os.environ.get("ATMTURB_SRC_DIR", str(src_parent / "AtmosphericTurbulenceSimul"))
    )
    fps_dir = atmturb_root / "src" / "AtmosphericTurbulence"
    units: list[dict[str, object]] = []
    if fps_dir.is_dir():
        for cpath in sorted(fps_dir.glob("atmturb_*_FPS.c")):
            parsed = _parse_atmturb_fps_c(cpath)
            if parsed is not None:
                units.append(parsed)
    return units


def _values_equal(val: str, default_str: str, opt_type: str) -> bool:
    """Compare a .bench value against a schema default with numeric/bool tolerance."""
    v = val.strip()
    d = default_str.strip()
    if not d or d == "(required)" or d.startswith("<"):
        return True
    if "(" in d:
        d = d.split("(", 1)[0].strip()
    if opt_type == "bool":
        v_b = v.lower() in ("1", "true", "on", "yes")
        d_b = d.lower() in ("1", "true", "on", "yes")
        return v_b == d_b
    try:
        return abs(float(v) - float(d)) <= 1e-6 * max(1.0, abs(float(d)))
    except ValueError:
        return v.lower() == d.lower()


def is_nondefault_bench_value(val: str, opt_meta: dict[str, object] | None) -> bool:
    """Return True when a .bench key value intentionally differs from its schema default."""
    if not opt_meta:
        return False
    d = str(opt_meta.get("default") or "").strip()
    if not d or d == "(required)" or d.startswith("<"):
        return False
    return not _values_equal(val, d, str(opt_meta.get("type") or ""))


def build_bench_opt_lookup(
    catalog: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    """Build (section_category, key_or_alias) -> option metadata lookup map."""
    lookup: dict[tuple[str, str], dict[str, object]] = {}
    bench_opts = catalog.get("bench_options")
    if not isinstance(bench_opts, list):
        return lookup
    for opt in bench_opts:
        if not isinstance(opt, dict):
            continue
        sec = str(opt.get("section") or "")
        key = str(opt.get("key") or "")
        if "anchor" not in opt:
            opt = dict(opt)
            opt["anchor"] = make_bench_opt_anchor(sec, key)
        applies = [a.strip() for a in str(opt.get("applies_to") or sec).split(",") if a.strip()]
        keys = [key] + [a.strip() for a in str(opt.get("aliases") or "").split(",") if a.strip()]
        for cat in applies:
            for k in keys:
                if k:
                    lookup[(cat, k)] = opt
    return lookup


def _scan_used_in(
    public_dir: Path,
    bench_opts: list[dict[str, object]],
    runner_opts: list[dict[str, object]],
) -> None:
    """Populate `used_in` cross-references from staged simulations under public_dir."""
    if not public_dir.is_dir():
        return
    bench_lookup = build_bench_opt_lookup({"bench_options": bench_opts})
    runner_by_key = {str(o["key"]): o for o in runner_opts}
    runner_by_flag = {str(o["flag"]): o for o in runner_opts}

    for meta_path in sorted(public_dir.glob("*/report_meta.json")):
        meta = load_json_safe(meta_path)
        if not meta or meta.get("report_type") != "simulation":
            continue
        slug = str(meta.get("slug") or meta_path.parent.name)
        sim_dir = meta_path.parent

        bpath = find_bench_path(sim_dir)
        if bpath is not None:
            seen_opts: set[int] = set()
            for sec in parse_bench_file(bpath):
                cat = str(sec.get("category") or "")
                params = sec.get("params")
                if not isinstance(params, dict):
                    continue
                for k, v in params.items():
                    opt = bench_lookup.get((cat, str(k)))
                    if opt is None or id(opt) in seen_opts:
                        continue
                    seen_opts.add(id(opt))
                    used = opt.setdefault("used_in", [])
                    if isinstance(used, list):
                        used.append({"slug": slug, "value": str(v)})

        ropts_path = sim_dir / "run_options.json"
        ropts = load_json_safe(ropts_path) if ropts_path.is_file() else {}
        ropts_map = ropts.get("options") if isinstance(ropts.get("options"), dict) else {}
        seen_runner: set[str] = set()
        if isinstance(ropts_map, dict) and ropts_map:
            for k, v in ropts_map.items():
                if v is None or v == "":
                    continue
                opt = runner_by_key.get(str(k))
                if opt is None:
                    continue
                seen_runner.add(str(k))
                used = opt.setdefault("used_in", [])
                if isinstance(used, list):
                    used.append({"slug": slug, "value": str(v)})

        repro = meta.get("reproducibility")
        cmd = str(repro.get("run_command", "")) if isinstance(repro, dict) else ""
        if cmd:
            tokens = cmd.split()
            for flag, opt in runner_by_flag.items():
                if flag.startswith("-h"):
                    continue
                okey = str(opt["key"])
                if okey in seen_runner:
                    continue
                if opt.get("type") == "bool":
                    if flag in tokens:
                        used = opt.setdefault("used_in", [])
                        if isinstance(used, list):
                            used.append({"slug": slug, "value": "ON"})
                else:
                    val = _parse_cmd_flag(cmd, flag)
                    if val is not None:
                        used = opt.setdefault("used_in", [])
                        if isinstance(used, list):
                            used.append({"slug": slug, "value": str(val)})


def build_options_catalog(public_dir: Path | None = None) -> dict[str, object]:
    """Assemble the full multi-layer options catalog across cacaosim, milkatmturb, and runners."""
    raw_csim = load_cacaosim_schema()

    bench_opts: list[dict[str, object]] = []
    for raw_opt in raw_csim.get("bench_options") or []:
        if not isinstance(raw_opt, dict):
            continue
        opt = dict(raw_opt)
        sec = str(opt.get("section") or "")
        key = str(opt.get("key") or "")
        opt["anchor"] = make_bench_opt_anchor(sec, key)
        opt["used_in"] = []
        bench_opts.append(opt)

    fps_units: list[dict[str, object]] = []
    for raw_u in raw_csim.get("fps_units") or []:
        if not isinstance(raw_u, dict):
            continue
        u = dict(raw_u)
        pkg = str(u.get("package") or "cacaosim")
        uname = str(u.get("unit") or u.get("cmdkey") or "")
        u["package"] = pkg
        u["anchor"] = make_fps_unit_anchor(pkg, uname)
        params_out: list[dict[str, object]] = []
        for raw_p in u.get("params") or []:
            if not isinstance(raw_p, dict):
                continue
            p = dict(raw_p)
            p["anchor"] = make_fps_opt_anchor(pkg, uname, str(p.get("keyword") or ""))
            params_out.append(p)
        u["params"] = params_out
        fps_units.append(u)

    fps_units.extend(extract_atmturb_fps_units())
    fps_units.extend(extract_cacao_predictive_fps_units())

    cacaosim_cli: list[dict[str, object]] = []
    for raw_c in raw_csim.get("cli_options") or []:
        if not isinstance(raw_c, dict):
            continue
        c = dict(raw_c)
        c["anchor"] = make_cli_opt_anchor(str(c.get("tool") or ""), str(c.get("flag") or ""))
        c["used_in"] = []
        cacaosim_cli.append(c)

    runner_cli: list[dict[str, object]] = []
    for raw_r in RUNNER_CLI_OPTIONS:
        r = dict(raw_r)
        r["tool"] = "run-ao3k-scexao.sh"
        r["anchor"] = make_runner_opt_anchor(str(r["flag"]))
        r["used_in"] = []
        runner_cli.append(r)

    env_vars: list[dict[str, object]] = []
    for raw_e in CACAOLOOP_ENV_VARS:
        e = dict(raw_e)
        e["tool"] = "cacaoloop-ao3k-scexao.milk"
        e["flag"] = e["name"]
        e["arg"] = ""
        e["anchor"] = make_cli_opt_anchor("cacaoloop-env", str(e["name"]))
        env_vars.append(e)

    if public_dir is not None:
        _scan_used_in(public_dir, bench_opts, runner_cli)

    return {
        "bench_options": bench_opts,
        "fps_units": fps_units,
        "cacaosim_cli": cacaosim_cli,
        "runner_cli": runner_cli,
        "env_vars": env_vars,
        "counts": {
            "bench_options": len(bench_opts),
            "fps_units": len(fps_units),
            "fps_params": sum(len(u.get("params") or []) for u in fps_units),
            "cacaosim_units": sum(1 for u in fps_units if u.get("package") == "cacaosim"),
            "atmturb_units": sum(1 for u in fps_units if u.get("package") == "milkatmturb"),
            "cacao_units": sum(1 for u in fps_units if u.get("package") == "cacao"),
            "cacaosim_cli": len(cacaosim_cli),
            "runner_cli": len(runner_cli),
            "env_vars": len(env_vars),
        },
    }
