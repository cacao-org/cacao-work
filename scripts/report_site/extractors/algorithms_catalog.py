#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Declarative AO algorithm, calibration, option-variant, and dependency catalog."""

from __future__ import annotations

import re

from .options_catalog import make_cli_opt_anchor, make_fps_opt_anchor, make_runner_opt_anchor

ALGO_ROLE_ORDER: tuple[str, ...] = (
    "calibration",
    "online_calib",
    "loop_operation",
    "analysis",
    "simulation",
    "planned",
)

ALGO_ROLES: dict[str, dict[str, str]] = {
    "calibration": {
        "key": "calibration",
        "label": "Offline Calibration",
        "short": "Offline Calib",
        "description": (
            "Pre-loop or startup calibrations producing response matrices, "
            "dynamic plant kernels, pre-shapers, and latency alignments"
        ),
        "mermaid_class": "algo_calibration",
        "mermaid_def": "fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f",
    },
    "online_calib": {
        "key": "online_calib",
        "label": "Online Calibration (In-Loop)",
        "short": "Online Calib",
        "description": (
            "Adaptive estimators running during closed-loop science to track "
            "time-varying optical gain, modal gains/leaks, wind layers, and ZPO scaling"
        ),
        "mermaid_class": "algo_online_calib",
        "mermaid_def": "fill:#ccfbf1,stroke:#0f766e,stroke-width:2px,color:#115e59",
    },
    "loop_operation": {
        "key": "loop_operation",
        "label": "Real-Time Loop Operation",
        "short": "RT Operation",
        "description": (
            "Frame-synchronous wavefront control loops, dynamic PSOL observers, "
            "pre-shapers, ZPO scaling, and predictive controllers"
        ),
        "mermaid_class": "algo_loop_operation",
        "mermaid_def": "fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0c4a6e",
    },
    "analysis": {
        "key": "analysis",
        "label": "Diagnostics & Post-Loop Analysis",
        "short": "Diagnostics",
        "description": (
            "Non-intrusive whiteness monitors, telemetry sync, modal gain "
            "optimizers, offline SysID audits, and PSF reconstruction"
        ),
        "mermaid_class": "algo_analysis",
        "mermaid_def": "fill:#d1fae5,stroke:#059669,stroke-width:2px,color:#064e3b",
    },
    "simulation": {
        "key": "simulation",
        "label": "Simulation Physics",
        "short": "Sim Physics",
        "description": (
            "Coupled flexural+membrane DM plate PDE and phase-continuous "
            "atmospheric wind-rotation kernels used to stress-test AO algorithms"
        ),
        "mermaid_class": "algo_simulation",
        "mermaid_def": "fill:#f3e8ff,stroke:#7e22ce,stroke-width:2px,color:#3b0764",
    },
    "planned": {
        "key": "planned",
        "label": "Research Queue (Planned)",
        "short": "Planned",
        "description": "Validated offline research prototypes slated for C/milk-mltools deployment",
        "mermaid_class": "algo_planned",
        "mermaid_def": "fill:#f1f5f9,stroke:#64748b,stroke-width:2px,stroke-dasharray:5 3,color:#334155",
    },
}

STAGE_LABELS: dict[str, str] = {
    "stg1": "Stage 1 (AO3k)",
    "stg2": "Stage 2 (SCExAO)",
    "stg3": "Stage 3 (LLOWFS)",
    "2stg": "2-Stage Coupled",
}

MATRIX_COLUMN_CODES: tuple[str, ...] = (
    "MLAT",
    "RM",
    "3DRM/P1",
    "PRESH/CAL",
    "PRESH",
    "3DRM/P2",
    "3DRM/FACT",
    "LAG/2PT",
    "SRM",
    "PSOL",
    "OG/POKE",
    "2WFS/LIVE",
    "MOPT",
    "WIND",
)


def make_algo_slug(code: str) -> str:
    """Convert a short code like '3DRM/FACT' into a URL-safe directory slug."""
    return re.sub(r"[^a-z0-9]+", "-", code.strip().lower()).strip("-")


def make_variant_anchor(vcode: str) -> str:
    """Convert an option variant like 'EOF/WIND' into an HTML anchor ID."""
    return "opt-" + make_algo_slug(vcode)


ALGORITHMS_RAW: list[dict[str, object]] = [
    # ------------------------------------------------------------------
    # Offline / Pre-Loop Calibration
    # ------------------------------------------------------------------
    {
        "code": "MLAT",
        "name": "Hardware Loop Latency Calibration",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1", "stg2", "stg3"],
        "summary": "Measures exact DM-to-WFS hardware and software loop latency in WFS frames.",
        "details": [
            "Drives repeated spatial Fourier poke bursts onto the DM while cross-correlating "
            "WFS response timing to measure fractional hardware latency (frames) and effective "
            "software+hardware lag.",
            "Provides the timing baseline required for synchronous Hadamard response matrix "
            "acquisition, 2-tap PSOL fallback alignment, and predictive filter lookahead.",
        ],
        "units": ["cacao-fpsexec-cacaoac-mlat"],
        "variants": [
            {
                "code": "MLAT/FAST",
                "summary": "Lockstep-paced latency probe under fused cacaosim htsim.",
                "flags": ["--calib-rate"],
            },
            {
                "code": "MLAT/RT",
                "summary": "Wall-clock paced latency calibration for modular bench or hardware.",
                "flags": ["--wall-rate", "--calib-rate"],
            },
        ],
        "requires": ["SIM/PLATE"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--calib-rate", "--wall-rate"],
        "env_vars": [
            "CACAO_MLAT_NBITER",
            "CACAO_MLAT_CPA",
            "CACAO_LATENCYHARDWFR",
            "CACAO_LATENCYSOFTWFR",
        ],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl_acquireCalib/measure_linear_resp.c"),
            ("cacao-work", "benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk"),
        ],
        "tests": ["test_00_stack_sanity.py", "ao3k_scexao bench calibration"],
        "metrics": ["Sub-0.05 frame hardware delay accuracy across 500 Hz, 1 kHz, and 2 kHz loops"],
        "related_reports": ["predictive_control_report"],
    },
    {
        "code": "RM",
        "name": "Static Response Matrix & Modal Basis",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1", "stg2", "stg3"],
        "summary": "Acquires Hadamard/direct static RM and computes SVD modal control matrix.",
        "details": [
            "Takes a reference WFS image (`takeref`), probes zonal Hadamard or direct Zernike "
            "patterns (`RM`), and performs GPU SVD inversion (`compstrCM`) to build the modal "
            "basis (`DMmodes`), WFS reconstructor (`CM`), and modal-to-DM projection matrices.",
            "Supports unthrottled lockstep step-and-shoot calibration (`RM/FAST`) under fused "
            "`cacaosim` as well as archiving and reloading calibrated RMs across runs.",
        ],
        "units": ["cacao-fpsexec-cacaoac-measlinresp", "cacao-fpsexec-cacaocc-compstrcm"],
        "variants": [
            {
                "code": "RM/HAD",
                "summary": "Real-time paced Hadamard zonal RM + SVD KL/Fourier modal basis.",
                "flags": ["--nbloop", "--no-fast-calib", "--svdlim1", "--svdlim2"],
            },
            {
                "code": "RM/FAST",
                "summary": "Unthrottled fused-bench step-and-shoot RM acquisition (default).",
                "flags": ["--save-rm", "--load-rm"],
            },
            {
                "code": "RM/DIR",
                "summary": "Direct low-order Zernike modal RM used by Stage-3 LLOWFS.",
                "flags": ["--svdlim3"],
            },
        ],
        "requires": ["MLAT"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [
            "--nbloop",
            "--no-fast-calib",
            "--svdlim1",
            "--svdlim2",
            "--svdlim3",
            "--save-rm",
            "--load-rm",
        ],
        "env_vars": [
            "CACAO_SVDLIM",
            "CACAO_CPAMAX",
            "CACAO_RCPAMAX",
            "CACAO_DELTACPA",
            "CACAO_POKEAMPL",
            "CACAO_FAST_CALIB",
            "CACAO_NMODES_DIRECT",
        ],
        "fps_refs": [],
        "sources": [
            ("cacao", "computeCalib/compute_straight_CM.c"),
            ("cacao-work", "benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk"),
        ],
        "tests": ["test_00_stack_sanity.py", "ao3k_phases1to5_calib.milk"],
        "metrics": ["1,024+ controlled modes on Stage 1 (64x64) and 1,255 modes on Stage 2 (50x50)"],
        "related_reports": ["predictive_control_report", "calib_2wfs1dm_report"],
    },
    {
        "code": "3DRM/P1",
        "name": "Stroboscopic 3D Dynamic RM — Pass 1",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Sub-frame stroboscopic measurement of the raw DM+WFS spatio-temporal response.",
        "details": [
            "Injects periodic step pokes across modal channels at fine sub-frame phase offsets "
            "to record the full 3D spatiotemporal response tensor `H[lag, out_mode, in_mode]` "
            "plus dropped-bin sample counters and static gain.",
            "On the 64x64 ALPAO coupled plate DM, Pass-1 3D RM directly resolves mechanical "
            "overshoot, ringing, and 34.3% peak cross-mode plate coupling that static RMs miss.",
        ],
        "units": ["cacao-fpsexec-cacaoac-measdynresp"],
        "variants": [
            {
                "code": "3DRM/P1",
                "summary": "Raw unshaped plant 3D impulse response (input to pre-shaper or Stage-2 factoring).",
                "flags": [],
            },
        ],
        "requires": ["RM"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [],
        "env_vars": [],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl_acquireCalib/measure_dyn_resp.c"),
            ("cacao-work", "scripts/studies/ao3k_phases1to5_calib.milk"),
        ],
        "tests": ["test_09_measdynresp.py"],
        "metrics": ["1.69 us stroboscopic timing jitter, r = 0.998, 34.3% plate cross-mode coupling resolved"],
        "related_reports": ["dm64_dyn_rm_calib", "dm_dynamics_report"],
    },
    {
        "code": "PRESH/CAL",
        "name": "DM Pre-Shaper Kernel Synthesis",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1"],
        "summary": "Computes causal 4 kHz MIMO FIR inverse pre-shaper kernel from Pass-1 3D RM.",
        "details": [
            "Solves a Tikhonov-regularized causal MIMO FIR inversion of the Pass-1 3D response "
            "tensor (`H_raw`) at an upsampled 4 kHz rate with unity DC-gain constraint.",
            "Produces the `dm01_preshaper_m32.fits` kernel deployed by real-time `PRESH` "
            "(`dmpreshaper`) to cancel coupled flexural/membrane plate overshoot and ringing "
            "without adding artificial loop latency.",
        ],
        "units": ["cacao-fpsexec-cacaocc-compdmpreshaper"],
        "variants": [
            {
                "code": "PRESH/CAL",
                "summary": "Regularized causal MIMO FIR pre-shaper synthesis (default 4 kHz upsampling).",
                "flags": [],
            },
        ],
        "requires": ["3DRM/P1"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [],
        "env_vars": [],
        "fps_refs": [],
        "sources": [
            ("cacao", "computeCalib/compute_dm_preshaper.c"),
            ("cacao-work", "scripts/studies/ao3k_phases1to5_calib.milk"),
        ],
        "tests": ["test_10_dmpreshaper.py"],
        "metrics": ["0.09% DC parity on 12x12; 0.79% DC parity on 64x64 ALPAO plate; stable at +-10% plant mismatch"],
        "related_reports": ["dm64_dyn_rm_calib", "dm_dynamics_report"],
    },
    {
        "code": "3DRM/P2",
        "name": "Stroboscopic 3D Dynamic RM — Pass 2",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1"],
        "summary": "Measures the effective shaped DM+WFS plant with high-rate `PRESH` active.",
        "details": [
            "Re-runs `cacaoac-measdynresp` through the live `dmpreshaper` (`PRESH`) path so the "
            "calibrated dynamic kernel captures the true post-shaping plant `H_eff[lag]` seen by "
            "Dynamic PSOL, Online OG, and Predictive Control.",
            "Live 64x64 ALPAO Pass-2 verified 3.87x full MIMO ringing reduction while revealing "
            "19.25% residual transient cross-mode coupling that justifies 3D MIMO PSOL.",
        ],
        "units": ["cacao-fpsexec-cacaoac-measdynresp"],
        "variants": [
            {
                "code": "3DRM/P2",
                "summary": "Shaped-plant 3D RM capturing exact group delay & residual cross-talk after PRESH.",
                "flags": ["--dm1-preshaper"],
            },
        ],
        "requires": ["RM", "PRESH"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--dm1-preshaper"],
        "env_vars": [],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl_acquireCalib/measure_dyn_resp.c"),
            ("cacao-work", "scripts/studies/ao3k_phases1to5_calib.milk"),
        ],
        "tests": ["test_10_dmpreshaper.py", "ao3k_phases1to5_calib.milk"],
        "metrics": ["Overshoot +4.73% -> +2.82%, MIMO ringing RMS 3.64% -> 0.94% (3.87x), L=16 tail 0.60% -> 0.18%"],
        "related_reports": ["dm64_dyn_rm_calib"],
    },
    {
        "code": "3DRM/FACT",
        "name": "3D RM Factoring (Static Gain + Unit-DC Kernel)",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Factors 3D RM into static M_cal and causal unit-DC H_diag / H_mimo kernels.",
        "details": [
            "Repairs dropped stroboscopic bins via `*_cnt.fits`, auto-discovers static gains, "
            "enforces causal sampling (`H[0] = 0`, auto `phase_fr = 0.5/NBsubfr`), guarantees "
            "exact unity DC closure (`sum_l H_eff[l] = I`, err < 3e-7), and supports block or "
            "off-diagonal threshold pruning.",
            "Consumes `3DRM/P2` on pre-shaped Stage 1 and `3DRM/P1` on Stage-2 MEMS or unshaped DMs.",
        ],
        "units": ["cacao-fpsexec-cacaoac-factordynrm"],
        "variants": [
            {
                "code": "3DRM/MIMO",
                "summary": "Full 3D cross-mode kernel `H_mimo.fits` (0.10% Pass-2 64x64 PSOL err).",
                "flags": ["--dynpsol1"],
            },
            {
                "code": "3DRM/DIAG",
                "summary": "Fast per-mode diagonal FIR kernel `H_diag.fits` (Stage-2 MEMS default).",
                "flags": ["--dynpsol2"],
            },
        ],
        "requires": ["3DRM/P1"],
        "optional_requires": ["3DRM/P2"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--dynpsol1", "--dynpsol2", "--pf-fx1", "--pf-fx2"],
        "env_vars": ["CACAO_DYNPSOL_KERNEL", "CACAO_PF_DM_KERNEL"],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl_acquireCalib/factor_dyn_resp.c"),
            ("cacao-work", "scripts/studies/ao3k_phases1to5_calib.milk"),
        ],
        "tests": ["test_12_dyn_psol.py"],
        "metrics": ["DC closure error < 3e-7; Pass-2 64x64 Kolmogorov PSOL: 1.40% diag vs 0.10% MIMO"],
        "related_reports": ["dm64_dyn_rm_calib"],
    },
    {
        "code": "LAG/2PT",
        "name": "Science-Cadence 2-Point Fractional Lag Alignment",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Aligns open-loop 3D RM kernels to exact closed-loop IPC latency (< 0.05 fr).",
        "details": [
            "Open-loop 3D RM calibration at 1 kHz wall clock can differ from 300 Hz science-cadence "
            "IPC scheduling by 0.3–0.4 frames, and `PRESH` adds +0.13..+0.30 frames of group delay "
            "to shaped modes relative to unshaped high-order modes.",
            "Paces `testOL` at science cadence and probes two modal anchors (mode 2 preshaped + "
            "mode 40 unshaped) to apply exact unity-DC fractional-delay shifts (`sum H = I`) to "
            "`H_mimo` and `H_diag` before closing the science loop.",
        ],
        "units": ["sim-ao3k-scexao.milk (Step 4c/7 aligner)"],
        "variants": [
            {
                "code": "LAG/2PT",
                "summary": "Two-band fractional kernel alignment preserving exact DC unity.",
                "flags": ["--dynpsol1", "--dynpsol2"],
            },
        ],
        "requires": ["RM", "3DRM/FACT"],
        "optional_requires": ["PRESH"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--dynpsol1", "--dynpsol2"],
        "env_vars": ["CACAO_LATENCYHARDWFR", "CACAO_LATENCYSOFTWFR"],
        "fps_refs": [],
        "sources": [("cacao-work", "benches/ao3k_scexao/sim-ao3k-scexao.milk")],
        "tests": ["ao3k_phases1to5_bench.py (Exp 1-3)"],
        "metrics": ["< 0.05 frame closed-loop lag mismatch; eliminated Stage-2 lag instability & modalog attenuation"],
        "related_reports": [],
    },
    {
        "code": "SRM",
        "name": "Modal Self-Response Matrix (Optical-Gain Reference)",
        "role": "calibration",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Active modal poke sweep measuring calibration and on-sky PyWFS optical gain.",
        "details": [
            "Applies controlled modal pokes through the DM and projects WFS responses back into "
            "modal space (`selfRM`) both on the internal calibration source and on sky to provide "
            "ground-truth optical gain curves for validating `OG/POKE` and `2WFS/LIVE`.",
            "When `PRESH` (`dmpreshaper`) is active on Stage 1, `selfRM` runs real-time paced "
            "(disabling `--fast` lockstep step-and-shoot) so the upsampled pre-shaper settles cleanly.",
        ],
        "units": ["cacaoloop-ao3k-scexao.milk (selfRM)"],
        "variants": [
            {
                "code": "SRM/CAL",
                "summary": "Pre-loop calibration-source selfRM baseline (unit optical gain reference).",
                "flags": ["--selfrm-modes", "--no-selfrm"],
            },
            {
                "code": "SRM/SKY",
                "summary": "On-sky active selfRM sweep measuring physical PyWFS optical gain truth.",
                "flags": ["--selfrm-modes", "--selfrm-iter", "--no-selfrm"],
            },
        ],
        "requires": ["RM"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--selfrm-modes", "--selfrm-iter", "--no-selfrm"],
        "env_vars": ["CACAO_SELFRM_ZSIZE"],
        "fps_refs": [],
        "sources": [
            ("cacao-work", "benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk"),
            ("cacao-work", "benches/ao3k_scexao/sim-ao3k-scexao.milk"),
        ],
        "tests": ["test_14_calib2wfs1dm_live.py", "ao3k_phases1to5_bench.py"],
        "metrics": ["Matches live modalog to 0.6% (Exp 1) and live 2WFS1DM to 0.8-3.3% (Exp 2/3)"],
        "related_reports": ["calib_2wfs1dm_report"],
    },
    # ------------------------------------------------------------------
    # Online Calibration (In-Loop Adaptive)
    # ------------------------------------------------------------------
    {
        "code": "OG/POKE",
        "name": "Single-Stage Closed-Loop DM-Poke Online Optical Gain",
        "role": "online_calib",
        "status": "verified",
        "stages": ["stg1"],
        "summary": "Exogenous DM-poke IV optical-gain tracker with clamped local-linear smoothing.",
        "details": [
            "Injects low-amplitude held (`hold >= 3`) sparse modal probes inside `modalfilter` "
            "(`< 0.1 us` RT overhead) that are completely cancelled out of `modevalOL` by Dynamic "
            "PSOL. Async `cacao-fpsexec-modalog` convolves commands and probes through `H_eff`, "
            "computes differenced exogenous-IV gain estimates with autocorrelation-robust SEs, "
            "applies 1st-order local-linear radial smoothing clamped to the probed band `[f_lo, f_hi]`, "
            "and updates live `aol1_mWFSfact = 1/g_opt` (resetting scalar `comp.WFSfact = 1.0`).",
            "Primary online optical-gain solution for Stage 1 (which has no upstream WFS) and "
            "standalone single-stage loops; remains completely unbiased under closed-loop PF=ON.",
        ],
        "units": ["cacao-fpsexec-modalog", "modalfilter (.comp.ogprobe.*)"],
        "variants": [
            {
                "code": "OG/POKE",
                "summary": "Live closed-loop apply mode updating `aol1_mWFSfact` via clamped EMA.",
                "flags": ["--online-og1", "--og1-ampl", "--og1-nbmode", "--og1-stride", "--og1-hold"],
            },
            {
                "code": "OG/POKE-SHAD",
                "summary": "Shadow monitoring mode estimating optical gain without modifying loop gains.",
                "flags": ["--online-og1", "--og1-no-apply"],
            },
        ],
        "requires": ["RM", "3DRM/FACT", "LAG/2PT", "PSOL"],
        "optional_requires": ["SRM"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [
            "--online-og1",
            "--og1-ampl",
            "--og1-nbmode",
            "--og1-stride",
            "--og1-hold",
            "--og1-no-apply",
        ],
        "env_vars": ["CACAO_PSOL_WFSFACT"],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl/modalog.c"),
            ("cacao", "AOloopControl/modalfilter.c"),
        ],
        "tests": ["test_13_online_og.py", "ao3k_phases1to5_bench.py"],
        "metrics": ["1.18% lockstep err (0.72% under PF=ON), 2.77% HIL with 4.24 nm probe, 0.6% live AO3k err"],
        "related_reports": [],
    },
    {
        "code": "2WFS/LIVE",
        "name": "2-Stage Passive 2WFS1DM Online Calibration",
        "role": "online_calib",
        "status": "verified",
        "stages": ["stg2", "2stg"],
        "summary": "Probe-free Differenced Lagged-A 2SLS calibrating Stage-2 OG, ZPO, and DM2->DM1 offload.",
        "details": [
            "Uses natural Stage-1 turbulence leakage as a zero-contrast-hit instrumental variable "
            "in native C (`milk-fpsexec-mlt-sysid`, `.method=ivdiff`): exposure-overlap alignment, "
            "jitter-immune `nearest_idx` counter pairing, `NA=160` plate DM1 projection, optional "
            "Stage-2 `H_eff` DM2 kernel ingestion, circular block bootstrap SEs, and `< 5%` "
            "`usable_ok` health gating.",
            "Pure-MILK `mlt.apply2wfs1dm` applies outlier-clamped per-mode `aol2_mWFSfact` (with "
            "`.psol_safety=0.90` and scalar `comp.WFSfact=1.0` reset) and updates Stage-2 "
            "`acquWFS-2.WFSzpogain = 0.95 * g_med`, plus solves level-IV `Mda_virt` for blind offload.",
        ],
        "units": ["milk-fpsexec-mlt-sysid", "mlt.apply2wfs1dm"],
        "variants": [
            {
                "code": "2WFS/IV",
                "summary": "Default Differenced Lagged-A 2SLS (`ivdiff`) with overlap alignment & health gate.",
                "flags": ["--live-2wfs1dm-sec", "--sysid-modes", "--clock-skew-us"],
            },
            {
                "code": "2WFS/W",
                "summary": "Legacy AR(p) temporal whitening estimator (`whiten`) retained for comparison.",
                "flags": ["--sysid-whiten-order"],
            },
        ],
        "requires": ["RM", "PSOL"],
        "optional_requires": ["3DRM/FACT", "SRM"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [
            "--live-2wfs1dm-sec",
            "--sysid-modes",
            "--sysid-whiten-order",
            "--clock-skew-us",
        ],
        "env_vars": ["CACAO_WFSZPO_GAIN"],
        "fps_refs": [],
        "sources": [
            ("milk-mltools", "mltools/sysid_iv.c"),
            ("milk-mltools", "mltools/sysid_unit.c"),
            ("milk-mltools", "mltools/commands.d/mltools.bash"),
        ],
        "tests": ["test_14_calib2wfs1dm_live.py", "test_07_calib_2wfs1dm.py", "test_mltools_e2e.py"],
        "metrics": ["4.66e-8 C-vs-Py parity; 0.8-3.3% live unmodulated Stage-2 OG err; 6.6x less ZPO fightback"],
        "related_reports": ["calib_2wfs1dm_report"],
    },
    {
        "code": "WIND",
        "name": "Live Wind Velocity & Altitude Profiler",
        "role": "online_calib",
        "status": "verified",
        "stages": ["stg1"],
        "summary": "Real-time spatiotemporal cross-correlation wind (vx, vy), altitude z, and Strehl monitor.",
        "details": [
            "Consumes live Stage-1 PSOL modal/phase telemetry in standalone C "
            "(`milk-fpsexec-mlt-windlayers`) to extract dominant frozen-flow wind layers "
            "`(vx, vy, frac_k)`, Fresnel/Rytov layer altitudes `z`, and coherent PyWFS `flux_in` "
            "auto-Strehl.",
            "Publishes live layer streams into `EOF` (`EOF/WIND`), enabling instantaneous "
            "Fourier-space physics-Gram cold-start priors and automatic wind-switch rescue.",
        ],
        "units": ["milk-fpsexec-mlt-windlayers"],
        "variants": [
            {
                "code": "WIND/2D",
                "summary": "Real-time multi-layer `(vx, vy, weight)` velocity tracking for EOF physics Gram.",
                "flags": ["--windlayers1"],
            },
            {
                "code": "WIND/ALT",
                "summary": "Coherent PyWFS Fresnel/Rytov altitude `z` & `flux_in` Strehl estimation.",
                "flags": ["--windlayers1"],
            },
        ],
        "requires": ["RM", "PSOL"],
        "optional_requires": ["SIM/WROT"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--windlayers1", "--pf-dmmodes1"],
        "env_vars": ["CACAO_PF_WL_LAYERS", "CACAO_PF_PUP_DIAM", "CACAO_PF_DM_DX"],
        "fps_refs": [],
        "sources": [
            ("milk-mltools", "mltools/windlayers_unit.c"),
            ("milk-mltools", "mltools/windlayers_core.h"),
        ],
        "tests": ["test_15_unified_eof_windlayers.py", "test_mltools_e2e.py"],
        "metrics": ["Tracks rotated Mauna Kea layers (6.46, 9.47, 22.03 m/s) to < 0.05 m/s & < 0.5 deg"],
        "related_reports": [],
    },
    {
        "code": "MOPT",
        "name": "Online Per-Mode Leaky-Integrator Gain & Leak Autotuner",
        "role": "online_calib",
        "status": "verified",
        "stages": ["stg1", "stg2", "stg3"],
        "summary": (
            "Joint per-mode (gain, leak) autotuner via Parseval Multi-Res PSD, "
            "faint-star adaptive memory, and ringing guard."
        ),
        "details": [
            "Subscribes asynchronously to `aol<N>_modevalOL_buff` (and optional "
            "`aol<N>_modevalWFS_buff`, `aol<N>_og_smooth`/`aol<N>_mWFSfact`, "
            "`aol<N>_mlimitcntfrac`, and `dynpsol` `H_diag`/`H_mimo` FITS `.kernel`) in "
            "standalone C (`cacao-fpsexec-modalopt`). Builds a Parseval-exact unclamped "
            "2-band Multi-Resolution PSD (decimated sub-Hz ring with exact sinc^2 boxcar "
            "inversion + explicit DC line + Hann Welch high-frequency PSD) and minimizes "
            "J_m(g, a) = sum P_OL * (|ETF|^2 + lam_dm * |CTF|^2) via shared BLAS SGEMM "
            "subject to Argument-Principle Nyquist stability and max|ETF| <= ms_max.",
            "Decouples fast buffer-flip cadence (~0.25-0.5 s) from faint-star statistical "
            "memory using cumulative 1/k warmup into per-mode SNR-adaptive EWMA memory "
            "(tau_fast=3 s to tau_faint=15 s), dual regime-change flush (low-order power "
            "and HF noise floor), variance-aware James-Stein radial Empirical-Bayes pooling, "
            "and a statistically gated lag-d/lag-1 WFS ringing guard that backs off gain "
            "and freezes PSD updates on ringing slices. Publishes shadow `aol<N>_mopt_*` "
            "streams and opt-in live `aol<N>_mgainfact` / `aol<N>_mmultfact` paired with "
            "`[0, 2.0]` / `[0, 1.0]` safety clamps in `modalfilter.c`.",
        ],
        "units": ["cacao-fpsexec-modalopt", "modalfilter (mgain/mmult safety clamp)"],
        "variants": [
            {
                "code": "MOPT/SHAD",
                "summary": (
                    "Shadow monitoring mode (default `.apply_gain=OFF`, `.apply_mult=OFF`) "
                    "publishing `aol<N>_mopt_{gain,mult,snr,taumem,ring}` without touching loop."
                ),
                "flags": [],
            },
            {
                "code": "MOPT/LIVE",
                "summary": (
                    "Live joint `(gain, leak)` publisher writing `aol<N>_mgainfact` & "
                    "`aol<N>_mmultfact` (`.apply_gain=ON`, `.apply_mult=ON`, auto loopgain/mult)."
                ),
                "flags": [],
            },
            {
                "code": "MOPT/FAINT",
                "summary": (
                    "Faint-star SNR-adaptive memory (`tau_fast..tau_faint`, `1/k` warmup), "
                    "James-Stein radial EB pooling (`.eb_enable`), and dual change-detector flush."
                ),
                "flags": [],
            },
            {
                "code": "MOPT/KERN",
                "summary": (
                    "Exact discrete `dynpsol` `H_diag`/`H_mimo` FITS `.kernel` plant model "
                    "with Argument-Principle stability & lag-d WFS ringing guard (`.ring_enable`)."
                ),
                "flags": [],
            },
        ],
        "requires": ["MLAT", "RM", "PSOL"],
        "optional_requires": ["3DRM/FACT", "LAG/2PT", "OG/POKE", "2WFS/LIVE"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [],
        "env_vars": [
            "CACAO_LOOPGAIN",
            "CACAO_LOOPMULT",
            "CACAO_TBUFF_SIZE",
            "CACAO_DYNPSOL_KERNEL",
            "CACAO_PSOL_WFSFACT",
            "CACAO_LATENCYSOFTWFR",
        ],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl/modalopt.c"),
            ("cacao", "AOloopControl/modalfilter.c"),
        ],
        "tests": ["test_16_modalopt.py"],
        "metrics": [
            "-29.8% WFE vs static integrator in live SHM test (0.69 ms solve); "
            "real cacaosim replay: Stg1 a_lo=0.996, Stg2 a_mid=0.852 (1.5 ms solve)",
            "Faint-star adaptive memory stretches tau_C = 12 s vs tau_A = 2 s; "
            "dual change detector flushes on flux drop; 2.2x OG jump bounded by lag-d guard",
        ],
        "related_reports": ["predictive_control_report"],
    },
    # ------------------------------------------------------------------
    # Real-Time Loop Operation
    # ------------------------------------------------------------------
    {
        "code": "PRESH",
        "name": "High-Rate DM Command Pre-Shaper",
        "role": "loop_operation",
        "status": "verified",
        "stages": ["stg1"],
        "summary": "Real-time 4 kHz upsampled MIMO FIR filter linearizing coupled plate DM dynamics.",
        "details": [
            "Runs inline upstream of `dm01disp` (`cacao-fpsexec-dmpreshaper`), convolving modal "
            "commands at 4 kHz with the calibrated causal MIMO FIR kernel (`PRESH/CAL`) to suppress "
            "mechanical overshoot, ringing, and inter-mode cross-talk on the 64x64 ALPAO plate DM.",
            "Requires Pass-2 3D RM (`3DRM/P2`) when paired with Dynamic PSOL so downstream observers "
            "see the exact shaped plant group delay and residual coupling.",
        ],
        "units": ["cacao-fpsexec-dmpreshaper"],
        "variants": [
            {
                "code": "PRESH/4K",
                "summary": "4 kHz upsampled real-time MIMO FIR DM command pre-shaper.",
                "flags": ["--dm1-preshaper"],
            },
        ],
        "requires": ["PRESH/CAL"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--dm1-preshaper"],
        "env_vars": [],
        "fps_refs": [],
        "sources": [("cacao", "AOloopControl_DM/AOloopControl_DM_preshaper.c")],
        "tests": ["test_10_dmpreshaper.py", "ao3k_phases1to5_bench.py"],
        "metrics": ["5.88x ringing cut (12x12 HIL); 3.87x full MIMO ringing cut (64x64 ALPAO plate)"],
        "related_reports": ["dm64_dyn_rm_calib", "dm_dynamics_report"],
    },
    {
        "code": "INT",
        "name": "Modal Leaky Integrator",
        "role": "loop_operation",
        "status": "verified",
        "stages": ["stg1", "stg2", "stg3"],
        "summary": "Core frame-synchronous modal leaky integrator with spatial-frequency gain rolloff.",
        "details": [
            "Executes hard real-time modal filtering inside `modalfilter`, applying per-mode loop "
            "gains shaped by spatial-frequency power law (`--mgain-alpha`, `--mgain-floor`), "
            "Tip/Tilt scaling (`--mgain-tt`), and leaky multipliers (`--mult1/2/3`).",
            "Serves as the baseline closed-loop feedback law and the parallel fallback path when "
            "blended with predictive control (`--pf-mix`).",
        ],
        "units": ["cacao-fpsexec-modalfilter"],
        "variants": [
            {
                "code": "INT/LEAK",
                "summary": "Standard modal leaky integrator (`u_k = mult * u_{k-1} - gain * w_k`).",
                "flags": ["--gain1", "--gain2", "--gain3", "--mult1", "--mult2", "--mult3"],
            },
            {
                "code": "INT/MGAIN",
                "summary": "Spatial-frequency power-law modal gain curve with Tip/Tilt override.",
                "flags": ["--mgain-alpha", "--mgain-floor", "--mgain-tt"],
            },
        ],
        "requires": ["MLAT", "RM"],
        "optional_requires": ["PRESH"],
        "feedback_from": ["MOPT"],
        "excludes": [],
        "cli_flags": [
            "--gain1",
            "--gain2",
            "--gain3",
            "--mult1",
            "--mult2",
            "--mult3",
            "--mgain-alpha",
            "--mgain-floor",
            "--mgain-tt",
        ],
        "env_vars": [
            "CACAO_LOOPGAIN",
            "CACAO_LOOPMULT",
            "CACAO_MGAIN_ALPHA",
            "CACAO_MGAIN_FLOOR",
            "CACAO_MGAIN_TT",
        ],
        "fps_refs": [],
        "sources": [("cacao", "AOloopControl/modalfilter.c")],
        "tests": ["test_00_stack_sanity.py", "test_12_dyn_psol.py"],
        "metrics": ["22.6 us baseline RT execution at NBmode = 1,255"],
        "related_reports": ["predictive_control_report"],
    },
    {
        "code": "PSOL",
        "name": "Dynamic FIR / MIMO Pseudo Open-Loop Observer",
        "role": "loop_operation",
        "status": "verified",
        "stages": ["stg1", "stg2", "stg3"],
        "summary": "Reconstructs probe-free pseudo open-loop turbulence using 2-tap, diag, or 3D MIMO FIR.",
        "details": [
            "Upgrades `modalfilter.c` with live-toggleable `.comp.dynpsol.*` supporting 2-tap "
            "scalar lag, per-mode diagonal FIR (`H_diag.fits`), and full 3D cross-mode MIMO FIR "
            "(`H_mimo.fits` via `cblas_sgemv`) with hybrid fallback for high-order modes.",
            "Tracks total applied DM command (`u_ctrl + selfRM/testOL/ogprobe` pokes) for 0.0000% "
            "probe leakage into `modevalOL`, scales WFS residuals by live per-mode `aolN_mWFSfact`, "
            "and fixes `mzeropoint` units when predictive control is active.",
        ],
        "units": ["cacao-fpsexec-modalfilter (.comp.dynpsol.*)"],
        "variants": [
            {
                "code": "PSOL/2TAP",
                "summary": "Legacy fractional 2-tap scalar delay PSOL (default when no kernel given).",
                "flags": [],
            },
            {
                "code": "PSOL/DIAG",
                "summary": "Per-mode causal FIR PSOL (`+9.3 us` at 1,255 modes; Stage-2 MEMS default).",
                "flags": ["--dynpsol2"],
            },
            {
                "code": "PSOL/MIMO",
                "summary": "3D cross-mode MIMO FIR + hybrid fallback (`+24.2 us`; Stage-1 plate DM).",
                "flags": ["--dynpsol1"],
            },
        ],
        "requires": ["MLAT", "RM"],
        "optional_requires": ["PRESH", "3DRM/FACT", "LAG/2PT"],
        "feedback_from": ["OG/POKE", "2WFS/LIVE"],
        "excludes": [],
        "cli_flags": ["--dynpsol1", "--dynpsol2"],
        "env_vars": ["CACAO_DYNPSOL_KERNEL", "CACAO_PSOL_WFSFACT", "CACAO_TBUFF_SIZE"],
        "fps_refs": [],
        "sources": [("cacao", "AOloopControl/modalfilter.c")],
        "tests": ["test_12_dyn_psol.py"],
        "metrics": ["12.2x live GPU plate PSOL error cut (34.14% -> 2.79%); 0.0000% probe leak; +24.2 us MIMO-64"],
        "related_reports": ["dm64_dyn_rm_calib"],
    },
    {
        "code": "ZPO",
        "name": "WFS Zero-Point Offset & Optical-Gain Scaling",
        "role": "loop_operation",
        "status": "verified",
        "stages": ["stg2", "stg3", "2stg"],
        "summary": "Transfers Stage-3 LLOWFS offsets into Stage-2 PyWFS reference scaled by live OG.",
        "details": [
            "Computes the Stage-2 WFS reference offset (`wfszpo`) corresponding to Stage-3 LLOWFS "
            "DM2 commands so the fast Stage-2 PyWFS does not fight the coronagraphic focal-plane "
            "pointing loop.",
            "Live `FPFLAG_WRITERUN` `.WFSzpogain` in `acquireWFSim.c` scales `wfszpo` by `0.95*g_opt` "
            "(either statically via `--zpo-og` or online from `2WFS/LIVE`), preventing ZPO wind-up "
            "and over-subtraction when on-sky PyWFS optical gain drops below 1.",
        ],
        "units": ["cacao-fpsexec-acquWFS (.WFSzpogain)", "cacaoloop setog"],
        "variants": [
            {
                "code": "ZPO/FIX",
                "summary": "Static unit-gain or manual `--zpo-og` WFS zero-point offset transfer.",
                "flags": ["--zpo-og", "--no-lowfs"],
            },
            {
                "code": "ZPO/OG",
                "summary": "Live optical-gain scaled `acquWFS-2.WFSzpogain` updated by `2WFS/LIVE`.",
                "flags": ["--live-2wfs1dm-sec", "--zpo-og"],
            },
        ],
        "requires": ["RM"],
        "optional_requires": ["2WFS/LIVE"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--zpo-og", "--no-lowfs"],
        "env_vars": ["CACAO_WFSZPO_GAIN"],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl_IOtools/acquireWFSim.c"),
            ("cacao-work", "benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk"),
        ],
        "tests": ["test_11_whiteness_and_zpo.py", "test_14_calib2wfs1dm_live.py"],
        "metrics": ["-26% Stage-2 WFS TT RMS & Q_lo20 in live 8 s A/B; 6.6x less LLOWFS ZPO fightback"],
        "related_reports": ["calib_2wfs1dm_report"],
    },
    {
        "code": "OFFL",
        "name": "Blind DM2-to-DM1 Static Stroke Offload",
        "role": "loop_operation",
        "status": "verified",
        "stages": ["2stg"],
        "summary": "Offloads low-order static DM2 stroke onto Stage-1 DM1 using passive Mda_virt.",
        "details": [
            "Projects accumulated Stage-2 MEMS DM commands onto Stage-1 high-stroke ALPAO DM1 "
            "using the virtual cross-stage matrix `Mda_virt = Mab^-1 Mdb` solved passively from "
            "closed-loop telemetry by `2WFS/LIVE` (`mlt-sysid` multivariate Lagged-A level-IV).",
            "Requires zero dedicated hardware DM2-to-WFS1 optical cross-calibration.",
        ],
        "units": ["milk-fpsexec-mlt-sysid (Mda_virt.fits)"],
        "variants": [
            {
                "code": "OFFL/2TO1",
                "summary": "Blind modal projection offload relieving Stage-2 MEMS stroke.",
                "flags": ["--live-2wfs1dm-sec", "--calib-2wfs1dm"],
            },
        ],
        "requires": ["2WFS/LIVE"],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--live-2wfs1dm-sec", "--calib-2wfs1dm"],
        "env_vars": [],
        "fps_refs": [],
        "sources": [("milk-mltools", "mltools/sysid_iv.c")],
        "tests": ["test_14_calib2wfs1dm_live.py"],
        "metrics": ["Mda_virt cos = 0.987; 100.0% static DM2 stroke reduction in live coupled 2-stage HIL"],
        "related_reports": ["calib_2wfs1dm_report"],
    },
    {
        "code": "PF/AR",
        "name": "Diagonal Autoregressive Predictive Control",
        "role": "loop_operation",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Per-mode temporal AR(P) predictive filter trained online from PSOL telemetry.",
        "details": [
            "Solves independent per-mode ridge-regularized temporal linear predictors of order `P` "
            "over a rolling PSOL buffer (`mkARPF`) and applies predictions synchronously in "
            "`applyARPF` blended with the integrator via `--pf-mix`.",
            "Low sample complexity (`N ~ 256-2048`) makes `PF/AR` fast to converge and serves as "
            "the built-in bootstrap fallback inside Block-EOF.",
        ],
        "units": ["cacao-fpsexec-cacaopc-mkARPF", "cacao-fpsexec-cacaopc-applyARPF"],
        "variants": [
            {
                "code": "PF/AR",
                "summary": "Diagonal per-mode AR(P) predictive controller.",
                "flags": ["--predictive", "--pf-mode", "--pf-order", "--pf-reg", "--pf-mix"],
            },
        ],
        "requires": ["MLAT", "RM", "PSOL"],
        "optional_requires": ["OG/POKE", "2WFS/LIVE"],
        "feedback_from": [],
        "excludes": [
            {
                "code": "EOF",
                "reason": (
                    "Mutually exclusive predictive controller (--pf-mode ar vs --pf-mode eof): "
                    "selecting PF/AR turns EOF off."
                ),
            }
        ],
        "cli_flags": [
            "--predictive",
            "--pf-mode",
            "--pf-order",
            "--pf-reg",
            "--pf-reg2",
            "--pf-mix",
            "--pf-mix1",
            "--pf-mix2",
            "--pf-nbtrain1",
            "--pf-nbtrain2",
            "--pf-minsamples1",
            "--pf-minsamples2",
            "--pf-warmup-sec",
            "--pf-mgain-exp",
        ],
        "env_vars": [
            "CACAO_PF_MODE",
            "CACAO_PF_ORDER",
            "CACAO_PF_DIAGORDER",
            "CACAO_PF_NBTRAIN",
            "CACAO_PF_MINSAMPLES",
            "CACAO_PF_UPDATEPERIOD",
            "CACAO_PF_REG",
            "CACAO_PF_MIX",
        ],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_mkARPF.c"),
            ("cacao", "AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_applyARPF.c"),
        ],
        "tests": ["test_11_whiteness_and_zpo.py"],
        "metrics": ["Fast warmup (256 frames) and strong single-mode wind/vibration cancellation"],
        "related_reports": ["predictive_control_report"],
    },
    {
        "code": "EOF",
        "name": "Unified Cross-Mode Block-EOF Predictive Control",
        "role": "loop_operation",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Spatio-temporal Block-EOF with ZOH ridge, extended/regime Grams, wind prior & FX-DM.",
        "details": [
            "Learns coupled cross-mode spatio-temporal predictors (`B` modes x `P` lags) inside "
            "`cacaopc-mkEOFPF` and applies them with zero changes to `applyEOFPF`. Unpriored "
            "high-order blocks automatically stay on diagonal AR bootstrap until `avail_samples >= "
            "eof_req`, preventing underdetermined (`N < D`) cross-mode overfitting.",
            "Combines five composable extensions: `EOF/ZOH` (ZOH-centered ridge, recommended ON for "
            "Stage 1 and OFF for Stage-2 high-pass residuals), `EOF/MEM` (exponentially forgotten "
            "chunk Gram beyond `NBtrain`), `EOF/REG` (multi-anchor regime-weighted Gram library), "
            "`EOF/WIND` (`windlayers` Fourier-space physics-Gram Bayesian prior + automatic wind-switch "
            "rescue), and `EOF/FX` (Pass-2 Filtered-X DM plant for unshaped ringing DMs).",
        ],
        "units": [
            "cacao-fpsexec-cacaopc-mkEOFPF",
            "cacao-fpsexec-cacaopc-applyEOFPF",
            "eoflin_phys.c",
        ],
        "variants": [
            {
                "code": "EOF/BASE",
                "summary": "Standard sliding-window Block-EOF (`--pf-mode eof --pf-blocksize 64`).",
                "flags": ["--predictive", "--pf-mode", "--pf-blocksize", "--pf-order", "--pf-reg"],
            },
            {
                "code": "EOF/ZOH",
                "summary": "ZOH-centered ridge toward `[I; 0; ...]` preventing DC-gain collapse (Stg1 ON, Stg2 OFF).",
                "flags": ["--pf-zoh-ridge", "--pf-zoh-ridge2"],
            },
            {
                "code": "EOF/MEM",
                "summary": "Extended-memory chunk-Gram accumulator remembering beyond rolling `NBtrain`.",
                "flags": ["--pf-gram-halflife"],
            },
            {
                "code": "EOF/REG",
                "summary": "Multi-anchor (`K <= 16`) regime-weighted Gram library with similarity floor kappa.",
                "flags": ["--pf-regime-kmax"],
            },
            {
                "code": "EOF/WIND",
                "summary": "`windlayers` Fourier physics-Gram prior + instant wind-switch empirical Gram decay.",
                "flags": ["--windlayers1", "--pf-dmmodes1", "--pf-n-prior", "--pf-wl-switch-decay"],
            },
            {
                "code": "EOF/FX",
                "summary": "Pass-2 Filtered-X regressor convolution through `H_eff` for unshaped ringing DMs.",
                "flags": ["--pf-fx1", "--pf-fx2"],
            },
        ],
        "requires": ["MLAT", "RM", "PSOL"],
        "optional_requires": ["OG/POKE", "2WFS/LIVE", "WIND", "3DRM/FACT", "LAG/2PT"],
        "feedback_from": [],
        "excludes": [
            {
                "code": "PF/AR",
                "reason": (
                    "Mutually exclusive predictive controller (--pf-mode eof vs --pf-mode ar): "
                    "selecting EOF turns PF/AR off."
                ),
            },
            {
                "code": "EOF",
                "reason": (
                    "Do not combine sub-option EOF/FX (Filtered-X coordinates) directly with "
                    "EOF/WIND (pure-delay physics Gram): when PRESH + PSOL/MIMO already linearize "
                    "the plate, use EOF/WIND without --pf-fx1."
                ),
            },
        ],
        "cli_flags": [
            "--predictive",
            "--pf-mode",
            "--pf-blocksize",
            "--pf-order",
            "--pf-reg",
            "--pf-reg2",
            "--pf-maxnorm2",
            "--pf-zoh-ridge",
            "--pf-zoh-ridge2",
            "--pf-gram-halflife",
            "--pf-regime-kmax",
            "--pf-fx1",
            "--pf-fx2",
            "--pf-dmmodes1",
            "--pf-n-prior",
            "--pf-wl-switch-decay",
        ],
        "env_vars": [
            "CACAO_PF_BLOCKSIZE",
            "CACAO_PF_ZOH_RIDGE",
            "CACAO_PF_GRAM_HALFLIFE",
            "CACAO_PF_DM_KERNEL",
            "CACAO_PF_WL_LAYERS",
            "CACAO_PF_DMMODES",
            "CACAO_PF_N_PRIOR",
            "CACAO_PF_WL_SWITCH_DECAY",
            "CACAO_PF_REGIME_KMAX",
            "CACAO_PF_REGIME_KAPPA",
            "CACAO_PF_REGIME_BW",
            "CACAO_PF_REGIME_RLIM",
        ],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_mkEOFPF.c"),
            ("cacao", "AOloopControl_PredictiveControl/eoflin_phys.c"),
            ("cacao", "AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_applyEOFPF.c"),
        ],
        "tests": ["test_15_unified_eof_windlayers.py", "ao3k_phases1to5_bench.py"],
        "metrics": [
            "Real AO3k cold start -3,070% -> +69.9% VR; live +60 deg wind switch: 6.16x lower Stg1 WFE (8.3x post-switch); FX cuts ringing Q_vw 26.4x"
        ],
        "related_reports": ["predictive_control_report"],
    },
    # ------------------------------------------------------------------
    # Diagnostics & Post-Loop Analysis
    # ------------------------------------------------------------------
    {
        "code": "WHITE",
        "name": "Closed-Loop Whiteness & Predictability Monitor",
        "role": "analysis",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Lag >= ceil(tau) residual whiteness, cross-mode coupling, ZPO alarm & OOS EOF overfit.",
        "details": [
            "An optimal linear predictor leaves an `MA(d-1)` innovation whose autocorrelation and "
            "WFS-DM cross-covariance vanish at all lags `k >= ceil(tau)`. Standalone "
            "`cacao-fpsexec-modalwhite` scores `Q_vw` (temporal whiteness), `Q_xmode` (cross-mode "
            "coupling), `Q_wu_lo20` (ZPO wind-up alarm), and `recov_var_pct`.",
            "Paired with strict out-of-sample metrics inside `mkEOFPF` (`.out.var_red_oos_pct`, "
            "`.out.overfit_ratio`) and fixed 4-point white-noise statistics in `modalCTRL_stats.c`.",
        ],
        "units": ["cacao-fpsexec-modalwhite", "modalCTRL_stats.c", "mkEOFPF (.out.*_oos)"],
        "variants": [
            {
                "code": "WHITE/RT",
                "summary": "Real-time async whiteness & ZPO fightback monitor (`modalwhite`).",
                "flags": ["--modalwhite"],
            },
            {
                "code": "WHITE/OOS",
                "summary": "Built-in strict out-of-sample EOF variance reduction & overfit ratio.",
                "flags": ["--predictive", "--pf-mode"],
            },
        ],
        "requires": ["PSOL"],
        "optional_requires": ["PF/AR", "EOF"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--modalwhite"],
        "env_vars": [],
        "fps_refs": [],
        "sources": [
            ("cacao", "AOloopControl/modalwhite.c"),
            ("cacao", "AOloopControl/modalCTRL_stats.c"),
        ],
        "tests": ["test_11_whiteness_and_zpo.py", "ao3k_phases1to5_bench.py"],
        "metrics": ["Catches ZPO ringing (>8-10x) & EOF overfit (1.57); live AO3k Stg2 Q_vw cut 2.5-14.5x"],
        "related_reports": ["predictive_control_report"],
    },
    {
        "code": "TLM",
        "name": "Telemetry Sync, Gain Optimization & Polychromatic PSFR",
        "role": "analysis",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Native C telemetry indexing/sync, PCA/CCA, modal PSD/ETF gain opt & PSF reconstruction.",
        "details": [
            "Processes saved multi-rate FITS telemetry cubes (`--save-telemetry standard|speckle|truth`) "
            "in pure C via `milk-mltools`: timebase indexing and synchronization (`mlt-tlm*`), "
            "empirical transfer-function modal gain optimization (`mlt-aoopt`), and polychromatic "
            "PSF reconstruction (`mlt-psfrecon`).",
        ],
        "units": [
            "milk-fpsexec-mlt-tlmsync",
            "milk-fpsexec-mlt-aoopt",
            "milk-fpsexec-mlt-psfrecon",
        ],
        "variants": [
            {
                "code": "TLM/SYNC",
                "summary": "Multi-stream FITS telemetry indexing, sync, PCA/CCA, and latency check.",
                "flags": ["--save-telemetry", "--telemetry-dir", "--keep-telemetry"],
            },
            {
                "code": "TLM/OPT",
                "summary": "Modal PSD & error-transfer-function gain optimization (`mlt.aoopt`).",
                "flags": ["--no-tlm-analysis"],
            },
            {
                "code": "TLM/PSFR",
                "summary": "Polychromatic focal-plane PSF reconstruction (`mlt.psfr`).",
                "flags": ["--psf-navg"],
            },
        ],
        "requires": ["INT"],
        "optional_requires": ["PSOL"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [
            "--save-telemetry",
            "--telemetry-dir",
            "--keep-telemetry",
            "--psf-navg",
            "--no-tlm-analysis",
        ],
        "env_vars": [],
        "fps_refs": [],
        "sources": [
            ("milk-mltools", "mltools/tlm_sync_unit.c"),
            ("milk-mltools", "mltools/ao_opt_unit.c"),
            ("milk-mltools", "mltools/psf_recon_unit.c"),
        ],
        "tests": ["test_mltools_e2e.py (11/11 passed)"],
        "metrics": ["Zero-Python C telemetry analysis suite across all standard/speckle/truth runs"],
        "related_reports": ["calib_2wfs1dm_report"],
    },
    {
        "code": "2WFS/POST",
        "name": "Post-Loop 2WFS1DM Calibration Audit",
        "role": "analysis",
        "status": "verified",
        "stages": ["2stg"],
        "summary": "Offline 2WFS1DM system-identification report cross-checked against on-sky selfRM.",
        "details": [
            "Runs `milk-mlt-calib2wfs1dm` (`mlt-sysid` `ivdiff`) over full recorded closed-loop "
            "telemetry after science integration to validate `Mab`, `Mdb` (Stage-2 optical gain), "
            "`Mda_virt` (DM2->DM1 offload), bootstrap standard errors, and health-gate status "
            "directly against `SRM` (`selfRM`).",
        ],
        "units": ["milk-mlt-calib2wfs1dm", "milk-fpsexec-mlt-sysid"],
        "variants": [
            {
                "code": "2WFS/POST",
                "summary": "Post-run 2-WFS + 1-DM audit (auto-promotes `--save-telemetry standard`).",
                "flags": ["--calib-2wfs1dm", "--sysid-modes", "--sysid-whiten-order"],
            },
        ],
        "requires": ["TLM", "RM", "PSOL"],
        "optional_requires": ["3DRM/FACT", "SRM"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--calib-2wfs1dm", "--sysid-modes", "--sysid-whiten-order"],
        "env_vars": [],
        "fps_refs": [],
        "sources": [
            ("milk-mltools", "mltools/scripts/milk-mlt-calib2wfs1dm"),
            ("milk-mltools", "mltools/sysid_iv.c"),
        ],
        "tests": ["test_07_calib_2wfs1dm.py", "test_14_calib2wfs1dm_live.py"],
        "metrics": ["Cross-regime parity across Integrator, AR, Block-EOF, 3 l/D & 0 l/D, mH=6/8"],
        "related_reports": ["calib_2wfs1dm_report"],
    },
    # ------------------------------------------------------------------
    # Simulation Physics Algorithms
    # ------------------------------------------------------------------
    {
        "code": "SIM/PLATE",
        "name": "Coupled 64x64 Plate PDE DM & Polychromatic Bench",
        "role": "simulation",
        "status": "verified",
        "stages": ["stg1", "stg2", "stg3"],
        "summary": "GPU-fused polychromatic optical bench with calibrated ALPAO coupled plate PDE DM.",
        "details": [
            "Simulates full multi-stage Subaru AO3k + SCExAO + H-band Lyot coronagraph + LLOWFS "
            "optics at 8 kHz sub-stepping (`oversample=4`) with a calibrated 64x64 flexural + "
            "membrane plate PDE (`dyn_mode=plate`) matched to 20 kHz SCExAO interferometry.",
            "Drives both realistic plate cross-mode coupling (for `3DRM/P1`, `PRESH`, `PSOL/MIMO`) "
            "and modulated/unmodulated PyWFS optical-gain physics (for `OG/POKE`, `2WFS/LIVE`).",
        ],
        "units": ["cacaosim (csim_htsim / modular)", "cacaosim_dm_engine.c"],
        "variants": [
            {
                "code": "SIM/PLATE",
                "summary": "64x64 coupled flexural+membrane plate PDE DM (`[dm] dyn_mode = plate`).",
                "flags": ["--oversample"],
            },
            {
                "code": "SIM/FUSED",
                "summary": "Zero-hop fused GPU DAG engine (`csim_htsim`, lockstep calibration).",
                "flags": ["--bench-mode", "--wfstat-validate"],
            },
            {
                "code": "SIM/MOD",
                "summary": "Modular per-element FPS daemon topology.",
                "flags": ["--bench-mode", "--clock-skew-us"],
            },
        ],
        "requires": [],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [
            "--bench-mode",
            "--oversample",
            "--wfs1-mod-rad",
            "--wfs2-mod-rad",
            "--clock-skew-us",
            "--wfstat-validate",
        ],
        "env_vars": ["CACAO_HTSIM_UNIT", "CACAO_GPUINDEX", "CACAO_MVM_GPUINDEX"],
        "fps_refs": [("cacaosim", "htsim", ".oversample")],
        "sources": [("cacaosim", "src/cacaosim_dm_engine.c")],
        "tests": ["test_05_ao_web_report.py", "test_10_dmpreshaper.py"],
        "metrics": ["Matches 20 kHz LepICSaBL-E ALPAO 64x64 measurements; 34.3% natural plate cross-talk"],
        "related_reports": ["dm_dynamics_report", "dm64_dyn_rm_calib"],
    },
    {
        "code": "SIM/WROT",
        "name": "Multi-Layer Turbulence & Phase-Continuous Wind Rotation",
        "role": "simulation",
        "status": "verified",
        "stages": ["stg1", "stg2"],
        "summary": "Mauna Kea multi-layer atmosphere with live phase-continuous wind-direction switches.",
        "details": [
            "Generates frozen-flow and boiling multi-layer Mauna Kea phase screens via "
            "`atmturb_mkwfs` with live `FPFLAG_WRITERUN` `.wind_rot_deg` rotation: rotates "
            "`(vx_pix, vy_pix)` while shifting layer origins by `(v_old - v_new) * t_ref` so "
            "pupil wavefront phase remains 100% continuous across mid-run wind direction jumps.",
        ],
        "units": ["milk-fpsexec-atmturb-mkwfs"],
        "variants": [
            {
                "code": "SIM/TURB",
                "summary": "Steady multi-layer Mauna Kea frozen-flow + boiling turbulence.",
                "flags": ["--seeing", "--star-mag", "--phys-time"],
            },
            {
                "code": "SIM/WROT",
                "summary": "Live phase-continuous mid-run wind rotation stress test.",
                "flags": ["--wind-switch-sec", "--wind-switch-deg"],
            },
        ],
        "requires": [],
        "optional_requires": [],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": [
            "--seeing",
            "--star-mag",
            "--phys-time",
            "--wind-switch-sec",
            "--wind-switch-deg",
        ],
        "env_vars": [],
        "fps_refs": [("milkatmturb", "mkwfs", ".wind_rot_deg")],
        "sources": [
            ("AtmosphericTurbulenceSimul", "src/AtmosphericTurbulence/atmturb_wfs_stream.c"),
            ("AtmosphericTurbulenceSimul", "src/AtmosphericTurbulence/atmturb_mkwfs_FPS.c"),
        ],
        "tests": ["ao3k_phases1to5_bench.py (Exp 1 +60 deg switch)"],
        "metrics": ["Zero phase discontinuity on live +60 deg wind switch at t = 3.0 s"],
        "related_reports": [],
    },
    # ------------------------------------------------------------------
    # Research Queue (Planned — Phase 6a)
    # ------------------------------------------------------------------
    {
        "code": "HESS/CORO",
        "name": "Coronagraphic WFS-to-PSF Quadratic / Hessian Model",
        "role": "planned",
        "status": "planned",
        "stages": ["stg2", "2stg"],
        "summary": "Streaming quadratic WFS-to-focal-plane speckle model for NCPA & optical-gain anchoring.",
        "details": [
            "Models focal-plane speckle intensity as a streaming linear + quadratic Hessian "
            "function of modal WFS residuals. Behind a Lyot coronagraph where unaberrated `E_0` "
            "vanishes, rank-2 speckle channels dominate, providing a focal-plane truth anchor "
            "that WFS-only self-learning cannot supply.",
            "Offline feasibility study (`algo/wfspsf_hessian`) achieved R^2 = 0.95-0.999 and "
            "0.01-frame lag recovery; next step is coronagraphic telemetry evaluation and "
            "structured-channel deployment in `milk-mltools`.",
        ],
        "units": ["algo/wfspsf_hessian (prototype -> milk-mltools planned)"],
        "variants": [
            {
                "code": "HESS/QUAD",
                "summary": "Full quadratic feature expansion + streaming normal-eq accumulator (K <= 80).",
                "flags": ["--save-telemetry"],
            },
            {
                "code": "HESS/2CH",
                "summary": "Scalable structured two-channel speckle model for coronagraphs (K > 80).",
                "flags": ["--save-telemetry"],
            },
        ],
        "requires": ["PSOL", "TLM"],
        "optional_requires": ["ZPO"],
        "feedback_from": [],
        "excludes": [],
        "cli_flags": ["--save-telemetry", "--psf-navg"],
        "env_vars": [],
        "fps_refs": [],
        "sources": [("cacao-work", "algo/wfspsf_hessian/README.md")],
        "tests": ["TP-6a (planned): sub-0.05 fr WFS-PSF lag & coronagraphic speckle R^2 > 0.85"],
        "metrics": ["Toy benchmark: R^2 = 0.95-0.999 at 0.3 rad RMS, 0.01-frame lag recovery"],
        "related_reports": [],
    },
]


_STAGE_REQ_OVERRIDES: dict[str, dict[str, object]] = {
    "2WFS/LIVE": {"mode": "all", "stages": ["stg1", "stg2"]},
    "OFFL": {"mode": "all", "stages": ["stg1", "stg2"]},
    "2WFS/POST": {"mode": "all", "stages": ["stg1", "stg2"]},
    "ZPO": {"mode": "all", "stages": ["stg2", "stg3"]},
    "HESS/CORO": {"mode": "all", "stages": ["stg2"]},
}


def _compute_stage_req(entry: dict[str, object]) -> dict[str, object]:
    """Return explicit active-stage requirement {'mode': none|any|all, 'stages': [...]}."""
    code = str(entry["code"])
    if code in _STAGE_REQ_OVERRIDES:
        ov = _STAGE_REQ_OVERRIDES[code]
        return {"mode": str(ov["mode"]), "stages": list(ov["stages"])}  # type: ignore[arg-type]
    if str(entry.get("role")) == "simulation":
        return {"mode": "none", "stages": []}
    base_stages = [
        str(s) for s in (entry.get("stages") or []) if str(s) in ("stg1", "stg2", "stg3")
    ]
    if not base_stages:
        return {"mode": "none", "stages": []}
    mode = "all" if len(base_stages) == 1 else "any"
    return {"mode": mode, "stages": base_stages}


def build_algorithms_catalog() -> dict[str, object]:
    """Assemble and validate the AO algorithm catalog with reverse dependency maps."""
    entries: list[dict[str, object]] = []
    by_code: dict[str, dict[str, object]] = {}
    by_slug: dict[str, dict[str, object]] = {}

    for raw in ALGORITHMS_RAW:
        entry = dict(raw)
        code = str(entry["code"])
        slug = make_algo_slug(code)
        entry["slug"] = slug
        variants_out: list[dict[str, object]] = []
        for var in entry.get("variants") or []:
            if not isinstance(var, dict):
                continue
            vcopy = dict(var)
            vcopy["anchor"] = make_variant_anchor(str(vcopy["code"]))
            variants_out.append(vcopy)
        entry["variants"] = variants_out
        entry["stage_req"] = _compute_stage_req(entry)
        entry["enables"] = []
        entry["enables_optional"] = []
        entry["feeds_runtime"] = []
        entry["excludes_codes"] = []
        entries.append(entry)
        by_code[code] = entry
        by_slug[slug] = entry

    for entry in entries:
        src_code = str(entry["code"])
        for req_code in entry.get("requires") or []:
            if req_code not in by_code:
                raise ValueError(f"Unknown required code {req_code!r} in {src_code}")
            by_code[req_code]["enables"].append(src_code)  # type: ignore[union-attr]
        for opt_code in entry.get("optional_requires") or []:
            if opt_code not in by_code:
                raise ValueError(f"Unknown optional code {opt_code!r} in {src_code}")
            by_code[opt_code]["enables_optional"].append(src_code)  # type: ignore[union-attr]
        for fb_code in entry.get("feedback_from") or []:
            if fb_code not in by_code:
                raise ValueError(f"Unknown feedback code {fb_code!r} in {src_code}")
            by_code[fb_code]["feeds_runtime"].append(src_code)  # type: ignore[union-attr]
        for ex in entry.get("excludes") or []:
            if not isinstance(ex, dict):
                continue
            ex_code = str(ex.get("code") or "")
            if not ex_code or ex_code == src_code:
                continue
            if ex_code not in by_code:
                raise ValueError(f"Unknown excluded code {ex_code!r} in {src_code}")
            if ex_code not in entry["excludes_codes"]:  # type: ignore[operator]
                entry["excludes_codes"].append(ex_code)  # type: ignore[union-attr]
            rev_list = by_code[ex_code]["excludes_codes"]
            if src_code not in rev_list:  # type: ignore[operator]
                rev_list.append(src_code)  # type: ignore[union-attr]

    role_counts: dict[str, int] = {k: 0 for k in ALGO_ROLE_ORDER}
    total_variants = 0
    for entry in entries:
        rkey = str(entry["role"])
        role_counts[rkey] = role_counts.get(rkey, 0) + 1
        total_variants += len(entry.get("variants") or [])  # type: ignore[arg-type]

    return {
        "entries": entries,
        "by_code": by_code,
        "by_slug": by_slug,
        "role_order": ALGO_ROLE_ORDER,
        "roles": ALGO_ROLES,
        "matrix_columns": MATRIX_COLUMN_CODES,
        "pipeline_choices": build_pipeline_choices_catalog(),
        "counts": {
            "total": len(entries),
            "variants": total_variants,
            **role_counts,
        },
    }


# ----------------------------------------------------------------------
# Algorithmic-Choice Graph for the Interactive Pipeline Configurator
# (Choices represent AO algorithmic options, not 1-to-1 FPS binaries.)
# ----------------------------------------------------------------------
_RM_12 = ("RM/FAST", "RM/HAD")
_RM_ANY = ("RM/FAST", "RM/HAD", "RM/DIR")
_DYN_ANY = ("3DRM/DIAG", "3DRM/MIMO")
_LAG_ANY = ("MLAT", "3DRM/DIAG", "3DRM/MIMO")
_INT_ANY = ("INT/LEAK", "INT/MGAIN")
_PSOL_ANY = ("PSOL/2TAP", "PSOL/DIAG", "PSOL/MIMO")
_TWOWFS_ANY = ("2WFS/IV", "2WFS/W")

PIPELINE_CHOICES_RAW: list[dict[str, object]] = [
    # --- Simulation & Bench (Radio Choice Pairs) ---
    {
        "code": "SIM/FUSED",
        "name": "Fused GPU DAG (csim_htsim)",
        "role": "simulation",
        "zone": "sim_bench",
        "radio_group": "bench_mode",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["SIM/MOD"],
        "doc_slug": "sim-plate",
        "doc_anchor": "opt-sim-fused",
    },
    {
        "code": "SIM/MOD",
        "name": "Modular Per-Element FPS Bench",
        "role": "simulation",
        "zone": "sim_bench",
        "radio_group": "bench_mode",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["SIM/FUSED"],
        "doc_slug": "sim-plate",
        "doc_anchor": "opt-sim-mod",
    },
    {
        "code": "SIM/PLATE",
        "name": "64x64 Coupled Plate PDE DM",
        "role": "simulation",
        "zone": "sim_dm",
        "radio_group": "dm_phys",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["SIM/IDEAL"],
        "doc_slug": "sim-plate",
        "doc_anchor": "opt-sim-plate",
    },
    {
        "code": "SIM/IDEAL",
        "name": "Ideal / Uncoupled DM",
        "role": "simulation",
        "zone": "sim_dm",
        "radio_group": "dm_phys",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["SIM/PLATE"],
        "doc_slug": "sim-plate",
        "doc_anchor": "",
    },
    {
        "code": "SIM/TURB",
        "name": "Steady Mauna Kea Turbulence",
        "role": "simulation",
        "zone": "sim_atm",
        "radio_group": "atm_mode",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["SIM/WROT"],
        "doc_slug": "sim-wrot",
        "doc_anchor": "opt-sim-turb",
    },
    {
        "code": "SIM/WROT",
        "name": "Live Wind-Rotation Switch",
        "role": "simulation",
        "zone": "sim_atm",
        "radio_group": "atm_mode",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["SIM/TURB"],
        "doc_slug": "sim-wrot",
        "doc_anchor": "opt-sim-wrot",
    },
    {
        "code": "WFS/MOD",
        "name": "Modulated PyWFS (3 l/D)",
        "role": "simulation",
        "zone": "sim_wfs",
        "radio_group": "wfs_mod",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["WFS/UNMOD"],
        "doc_slug": "sim-plate",
        "doc_anchor": "",
    },
    {
        "code": "WFS/UNMOD",
        "name": "Unmodulated PyWFS (0 l/D)",
        "role": "simulation",
        "zone": "sim_wfs",
        "radio_group": "wfs_mod",
        "stage_req": {"mode": "none", "stages": []},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": ["WFS/MOD"],
        "doc_slug": "sim-plate",
        "doc_anchor": "",
    },
    # --- Calibration: Offline ---
    {
        "code": "MLAT",
        "name": "Loop Latency Calibration",
        "role": "calibration",
        "zone": "calib_offline_base",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "mlat",
        "doc_anchor": "",
    },
    {
        "code": "SRM",
        "name": "Self-RM Optical-Gain Reference",
        "role": "calibration",
        "zone": "calib_offline_base",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12)],
        "opt": ["WFS/UNMOD"],
        "fb_in": [],
        "excl": [],
        "doc_slug": "srm",
        "doc_anchor": "",
    },
    {
        "code": "RM/FAST",
        "name": "Lockstep Step-and-Shoot RM",
        "role": "calibration",
        "zone": "calib_offline_rm",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [["SIM/FUSED"]],
        "opt": [],
        "fb_in": [],
        "excl": ["RM/HAD"],
        "doc_slug": "rm",
        "doc_anchor": "opt-rm-fast",
    },
    {
        "code": "RM/HAD",
        "name": "RT Paced Hadamard RM",
        "role": "calibration",
        "zone": "calib_offline_rm",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [["MLAT"]],
        "opt": [],
        "fb_in": [],
        "excl": ["RM/FAST"],
        "doc_slug": "rm",
        "doc_anchor": "opt-rm-had",
    },
    {
        "code": "RM/DIR",
        "name": "Direct Zernike RM (Stage 3)",
        "role": "calibration",
        "zone": "calib_offline_base",
        "stage_req": {"mode": "all", "stages": ["stg3"]},
        "req_clauses": [["SIM/FUSED", "MLAT"]],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "rm",
        "doc_anchor": "opt-rm-dir",
    },
    {
        "code": "3DRM/DIAG",
        "name": "3D Dynamic RM — Diagonal FIR",
        "role": "calibration",
        "zone": "calib_offline_3drm",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12)],
        "opt": [],
        "fb_in": [],
        "excl": ["3DRM/MIMO"],
        "doc_slug": "3drm-fact",
        "doc_anchor": "opt-3drm-diag",
    },
    {
        "code": "3DRM/MIMO",
        "name": "3D Dynamic RM — Cross-Mode MIMO",
        "role": "calibration",
        "zone": "calib_offline_3drm",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12)],
        "opt": ["SIM/PLATE"],
        "fb_in": [],
        "excl": ["3DRM/DIAG"],
        "doc_slug": "3drm-fact",
        "doc_anchor": "opt-3drm-mimo",
    },
    # --- Calibration: Online (In-Loop) ---
    {
        "code": "OG/POKE",
        "name": "Active DM-Poke IV Optical Gain",
        "role": "online_calib",
        "zone": "calib_online_og",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12), list(_INT_ANY), list(_LAG_ANY)],
        "opt": [*_DYN_ANY, "SRM", "WFS/UNMOD"],
        "fb_in": [],
        "excl": [],
        "doc_slug": "og-poke",
        "doc_anchor": "opt-og-poke",
    },
    {
        "code": "2WFS/IV",
        "name": "Stage-2 Passive 2WFS1DM (2SLS)",
        "role": "online_calib",
        "zone": "calib_online_2wfs",
        "stage_req": {"mode": "all", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12), list(_INT_ANY)],
        "opt": [*_DYN_ANY, "SRM", "WFS/UNMOD"],
        "fb_in": [],
        "excl": ["2WFS/W"],
        "doc_slug": "2wfs-live",
        "doc_anchor": "opt-2wfs-iv",
    },
    {
        "code": "2WFS/W",
        "name": "Stage-2 Passive 2WFS1DM (AR Whiten)",
        "role": "online_calib",
        "zone": "calib_online_2wfs",
        "stage_req": {"mode": "all", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12), list(_INT_ANY)],
        "opt": [*_DYN_ANY, "SRM", "WFS/UNMOD"],
        "fb_in": [],
        "excl": ["2WFS/IV"],
        "doc_slug": "2wfs-live",
        "doc_anchor": "opt-2wfs-w",
    },
    {
        "code": "MOPT",
        "name": "Per-Mode Gain & Leak Autotuner",
        "role": "online_calib",
        "zone": "calib_online_adapt",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [list(_INT_ANY), list(_PSOL_ANY)],
        "opt": [*_DYN_ANY, "OG/POKE", *_TWOWFS_ANY],
        "fb_in": [],
        "excl": [],
        "doc_slug": "mopt",
        "doc_anchor": "",
    },
    {
        "code": "WIND",
        "name": "Live Wind Velocity & Altitude",
        "role": "online_calib",
        "zone": "calib_online_adapt",
        "stage_req": {"mode": "all", "stages": ["stg1"]},
        "req_clauses": [],
        "opt": [*_PSOL_ANY, "SIM/WROT"],
        "fb_in": [],
        "excl": [],
        "doc_slug": "wind",
        "doc_anchor": "",
    },
    # --- Control ---
    {
        "code": "INT/LEAK",
        "name": "Uniform Leaky Integrator",
        "role": "loop_operation",
        "zone": "ctrl_int",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [list(_RM_ANY)],
        "opt": [],
        "fb_in": ["MOPT", "OG/POKE", *_TWOWFS_ANY],
        "excl": ["INT/MGAIN"],
        "doc_slug": "int",
        "doc_anchor": "opt-int-leak",
    },
    {
        "code": "INT/MGAIN",
        "name": "Power-Law Modal Gain Integrator",
        "role": "loop_operation",
        "zone": "ctrl_int",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [list(_RM_ANY)],
        "opt": [],
        "fb_in": ["MOPT", "OG/POKE", *_TWOWFS_ANY],
        "excl": ["INT/LEAK"],
        "doc_slug": "int",
        "doc_anchor": "opt-int-mgain",
    },
    {
        "code": "PSOL/2TAP",
        "name": "2-Tap Fractional Lag PSOL",
        "role": "loop_operation",
        "zone": "ctrl_psol",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [list(_INT_ANY), ["MLAT"]],
        "opt": [],
        "fb_in": ["OG/POKE", *_TWOWFS_ANY],
        "excl": ["PSOL/DIAG", "PSOL/MIMO"],
        "doc_slug": "psol",
        "doc_anchor": "opt-psol-2tap",
    },
    {
        "code": "PSOL/DIAG",
        "name": "Diagonal Causal FIR PSOL",
        "role": "loop_operation",
        "zone": "ctrl_psol",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_INT_ANY), list(_DYN_ANY)],
        "opt": [],
        "fb_in": ["OG/POKE", *_TWOWFS_ANY],
        "excl": ["PSOL/2TAP", "PSOL/MIMO"],
        "doc_slug": "psol",
        "doc_anchor": "opt-psol-diag",
    },
    {
        "code": "PSOL/MIMO",
        "name": "3D Cross-Mode MIMO PSOL",
        "role": "loop_operation",
        "zone": "ctrl_psol",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_INT_ANY), ["3DRM/MIMO"]],
        "opt": ["PRESH/4K"],
        "fb_in": ["OG/POKE", *_TWOWFS_ANY],
        "excl": ["PSOL/2TAP", "PSOL/DIAG"],
        "doc_slug": "psol",
        "doc_anchor": "opt-psol-mimo",
    },
    {
        "code": "PF/AR",
        "name": "Diagonal AR(P) Prediction",
        "role": "loop_operation",
        "zone": "ctrl_pred",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12), list(_PSOL_ANY)],
        "opt": ["OG/POKE", *_TWOWFS_ANY],
        "fb_in": [],
        "excl": ["EOF/BASE"],
        "doc_slug": "pf-ar",
        "doc_anchor": "opt-pf-ar",
    },
    {
        "code": "EOF/BASE",
        "name": "Cross-Mode Block-EOF",
        "role": "loop_operation",
        "zone": "ctrl_pred",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12), list(_PSOL_ANY)],
        "opt": ["OG/POKE", *_TWOWFS_ANY],
        "fb_in": [],
        "excl": ["PF/AR"],
        "doc_slug": "eof",
        "doc_anchor": "opt-eof-base",
    },
    {
        "code": "EOF/ZOH",
        "name": "ZOH-Centered Ridge",
        "role": "loop_operation",
        "zone": "ctrl_eof_ext",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [["EOF/BASE"]],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "eof",
        "doc_anchor": "opt-eof-zoh",
    },
    {
        "code": "EOF/MEM",
        "name": "Extended Chunk-Gram Memory",
        "role": "loop_operation",
        "zone": "ctrl_eof_ext",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [["EOF/BASE"]],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "eof",
        "doc_anchor": "opt-eof-mem",
    },
    {
        "code": "EOF/REG",
        "name": "Regime-Weighted Gram Library",
        "role": "loop_operation",
        "zone": "ctrl_eof_ext",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [["EOF/BASE"]],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "eof",
        "doc_anchor": "opt-eof-reg",
    },
    {
        "code": "EOF/WIND",
        "name": "Wind Physics-Gram Prior",
        "role": "loop_operation",
        "zone": "ctrl_eof_ext",
        "stage_req": {"mode": "all", "stages": ["stg1"]},
        "req_clauses": [["EOF/BASE"], ["WIND"]],
        "opt": ["SIM/WROT"],
        "fb_in": [],
        "excl": ["EOF/FX"],
        "doc_slug": "eof",
        "doc_anchor": "opt-eof-wind",
    },
    {
        "code": "EOF/FX",
        "name": "Filtered-X DM Plant Coords",
        "role": "loop_operation",
        "zone": "ctrl_eof_ext",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [["EOF/BASE"], list(_DYN_ANY)],
        "opt": ["SIM/PLATE"],
        "fb_in": [],
        "excl": ["EOF/WIND"],
        "doc_slug": "eof",
        "doc_anchor": "opt-eof-fx",
    },
    {
        "code": "PRESH/4K",
        "name": "4 kHz DM Plate Pre-Shaper",
        "role": "loop_operation",
        "zone": "ctrl_aux",
        "stage_req": {"mode": "all", "stages": ["stg1"]},
        "req_clauses": [["SIM/PLATE"], ["3DRM/MIMO"]],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "presh",
        "doc_anchor": "opt-presh-4k",
    },
    {
        "code": "ZPO/FIX",
        "name": "Static WFS Zero-Point Offset",
        "role": "loop_operation",
        "zone": "ctrl_aux",
        "stage_req": {"mode": "all", "stages": ["stg2", "stg3"]},
        "req_clauses": [list(_RM_12), ["RM/DIR"], list(_INT_ANY)],
        "opt": [],
        "fb_in": [],
        "excl": ["ZPO/OG"],
        "doc_slug": "zpo",
        "doc_anchor": "opt-zpo-fix",
    },
    {
        "code": "ZPO/OG",
        "name": "Live OG-Scaled WFS ZPO",
        "role": "loop_operation",
        "zone": "ctrl_aux",
        "stage_req": {"mode": "all", "stages": ["stg2", "stg3"]},
        "req_clauses": [list(_RM_12), ["RM/DIR"], list(_INT_ANY), list(_TWOWFS_ANY)],
        "opt": ["WFS/UNMOD"],
        "fb_in": [],
        "excl": ["ZPO/FIX"],
        "doc_slug": "zpo",
        "doc_anchor": "opt-zpo-og",
    },
    {
        "code": "OFFL/2TO1",
        "name": "Blind DM2->DM1 Stroke Offload",
        "role": "loop_operation",
        "zone": "ctrl_aux",
        "stage_req": {"mode": "all", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_TWOWFS_ANY)],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "offl",
        "doc_anchor": "opt-offl-2to1",
    },
    # --- Diagnostics & Telemetry ---
    {
        "code": "WHITE/RT",
        "name": "RT Whiteness & ZPO Monitor",
        "role": "analysis",
        "zone": "diag",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [list(_INT_ANY), list(_LAG_ANY)],
        "opt": ["PF/AR", "EOF/BASE", "ZPO/FIX", "ZPO/OG"],
        "fb_in": [],
        "excl": [],
        "doc_slug": "white",
        "doc_anchor": "opt-white-rt",
    },
    {
        "code": "WHITE/OOS",
        "name": "OOS EOF Overfit Guard",
        "role": "analysis",
        "zone": "diag",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [["EOF/BASE"]],
        "opt": [],
        "fb_in": [],
        "excl": [],
        "doc_slug": "white",
        "doc_anchor": "opt-white-oos",
    },
    {
        "code": "TLM/SYNC",
        "name": "Telemetry Sync & PCA/CCA",
        "role": "analysis",
        "zone": "diag",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [list(_INT_ANY)],
        "opt": list(_PSOL_ANY),
        "fb_in": [],
        "excl": [],
        "doc_slug": "tlm",
        "doc_anchor": "opt-tlm-sync",
    },
    {
        "code": "TLM/OPT",
        "name": "Offline PSD/ETF Gain Opt",
        "role": "analysis",
        "zone": "diag",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2", "stg3"]},
        "req_clauses": [["TLM/SYNC"], ["MLAT", *_PSOL_ANY]],
        "opt": ["SRM"],
        "fb_in": [],
        "excl": [],
        "doc_slug": "tlm",
        "doc_anchor": "opt-tlm-opt",
    },
    {
        "code": "TLM/PSFR",
        "name": "Polychromatic PSF Recon",
        "role": "analysis",
        "zone": "diag",
        "stage_req": {"mode": "any", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12), ["TLM/SYNC"]],
        "opt": ["SRM"],
        "fb_in": [],
        "excl": [],
        "doc_slug": "tlm",
        "doc_anchor": "opt-tlm-psfr",
    },
    {
        "code": "2WFS/POST",
        "name": "Post-Loop 2WFS1DM Audit",
        "role": "analysis",
        "zone": "diag",
        "stage_req": {"mode": "all", "stages": ["stg1", "stg2"]},
        "req_clauses": [list(_RM_12), ["TLM/SYNC"]],
        "opt": [*_DYN_ANY, "SRM", "WFS/UNMOD"],
        "fb_in": [],
        "excl": [],
        "doc_slug": "2wfs-post",
        "doc_anchor": "opt-2wfs-post",
    },
    {
        "code": "HESS/CORO",
        "name": "Coro WFS-to-PSF Hessian (Plan)",
        "role": "planned",
        "zone": "diag",
        "stage_req": {"mode": "all", "stages": ["stg2"]},
        "req_clauses": [list(_RM_12), ["TLM/SYNC"]],
        "opt": ["ZPO/FIX", "ZPO/OG", *_PSOL_ANY],
        "fb_in": [],
        "excl": [],
        "doc_slug": "hess-coro",
        "doc_anchor": "",
    },
]


def validate_pipeline_selection(
    stages: set[str] | list[str] | tuple[str, ...],
    selected: set[str] | list[str] | tuple[str, ...],
    pcat: dict[str, object] | None = None,
) -> list[str]:
    """Return a list of constraint-violation errors (empty list = exact valid simulation)."""
    cat = pcat if pcat is not None else build_pipeline_choices_catalog()
    by_code: dict[str, dict[str, object]] = cat["by_code"]  # type: ignore[assignment]
    st_set = set(stages)
    sel_set = set(selected)
    errors: list[str] = []

    radio_seen: dict[str, list[str]] = {}
    for code in sorted(sel_set):
        if code not in by_code:
            errors.append(f"Unknown choice code: {code}")
            continue
        node = by_code[code]
        rg = str(node.get("radio_group") or "")
        if rg:
            radio_seen.setdefault(rg, []).append(code)
        sr = node.get("stage_req") or {}
        if isinstance(sr, dict):
            mode = str(sr.get("mode") or "none")
            req_st = list(sr.get("stages") or [])
            if mode == "all" and not all(s in st_set for s in req_st):
                errors.append(f"{code} requires all stages {req_st} (active: {sorted(st_set)})")
            elif mode == "any" and req_st and not any(s in st_set for s in req_st):
                errors.append(f"{code} requires any stage in {req_st} (active: {sorted(st_set)})")
        for clause in node.get("req_clauses") or []:
            if clause and not any(r in sel_set for r in clause):
                errors.append(f"{code} requires one of {clause}")
        for ex in node.get("excl") or []:
            if ex in sel_set and code < ex:
                errors.append(f"Mutually exclusive choices both active: {code} and {ex}")

    all_radios = {
        str(n.get("radio_group"))
        for n in by_code.values()
        if str(n.get("radio_group") or "")
    }
    for rg in sorted(all_radios):
        chosen = radio_seen.get(rg, [])
        if len(chosen) != 1:
            errors.append(f"Simulation radio group {rg!r} must have 1 choice, got {chosen}")
    return errors


def build_pipeline_choices_catalog() -> dict[str, object]:
    """Assemble and validate the algorithmic-choice graph for the Pipeline Map."""
    items: list[dict[str, object]] = []
    by_code: dict[str, dict[str, object]] = {}

    for raw in PIPELINE_CHOICES_RAW:
        it = dict(raw)
        code = str(it["code"])
        it["req_clauses"] = [list(cl) for cl in (it.get("req_clauses") or [])]
        it["opt"] = list(it.get("opt") or [])
        it["fb_in"] = list(it.get("fb_in") or [])
        it["excl"] = list(it.get("excl") or [])
        it["radio_group"] = str(it.get("radio_group") or "")
        it["en"] = []
        it["en_opt"] = []
        it["fb_out"] = []
        slug = str(it["doc_slug"])
        anc = str(it.get("doc_anchor") or "")
        it["doc_href"] = f"./{slug}/index.html" + (f"#{anc}" if anc else "")
        items.append(it)
        by_code[code] = it

    for it in items:
        src = str(it["code"])
        for clause in it["req_clauses"]:  # type: ignore[union-attr]
            for rc in clause:
                if rc not in by_code:
                    raise ValueError(f"Unknown pipeline choice req {rc!r} in {src}")
                if src not in by_code[rc]["en"]:  # type: ignore[operator]
                    by_code[rc]["en"].append(src)  # type: ignore[union-attr]
        for oc in it["opt"]:  # type: ignore[union-attr]
            if oc not in by_code:
                raise ValueError(f"Unknown pipeline choice opt {oc!r} in {src}")
            if src not in by_code[oc]["en_opt"]:  # type: ignore[operator]
                by_code[oc]["en_opt"].append(src)  # type: ignore[union-attr]
        for fc in it["fb_in"]:  # type: ignore[union-attr]
            if fc not in by_code:
                raise ValueError(f"Unknown pipeline choice fb_in {fc!r} in {src}")
            if src not in by_code[fc]["fb_out"]:  # type: ignore[operator]
                by_code[fc]["fb_out"].append(src)  # type: ignore[union-attr]
        for xc in list(it["excl"]):  # type: ignore[arg-type]
            if xc not in by_code:
                raise ValueError(f"Unknown pipeline choice excl {xc!r} in {src}")
            if src not in by_code[xc]["excl"]:  # type: ignore[operator]
                by_code[xc]["excl"].append(src)  # type: ignore[union-attr]

    return {"items": items, "by_code": by_code}


def resolve_option_anchor(
    kind: str,
    token: str,
    valid_anchors: set[str],
) -> str | None:
    """Return /reference/index.html anchor ID for a CLI flag, CACAO_* env var, or FPS ref."""
    if kind == "cli":
        cand = make_runner_opt_anchor(token)
        return cand if cand in valid_anchors else None
    if kind == "env":
        cand = make_cli_opt_anchor("cacaoloop-env", token)
        return cand if cand in valid_anchors else None
    if kind == "fps" and isinstance(token, tuple) and len(token) == 3:
        pkg, unit, kw = token
        cand = make_fps_opt_anchor(str(pkg), str(unit), str(kw))
        return cand if cand in valid_anchors else None
    return None
