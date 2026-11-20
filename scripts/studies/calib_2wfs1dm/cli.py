#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CLI entrypoint for the 2-WFS + Inter-Stage DM calibration study generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from .analysis import compute_method_benchmarks, compute_offload_and_zpo, run_all_sweeps
from .markdown import write_outputs
from .plots import render_all_figures


def main(argv: list[str] | None = None) -> int:
    """Build the 2-WFS + Inter-Stage DM Telemetry Calibration Technical Report."""
    parser = argparse.ArgumentParser(
        description="Build the 2-WFS + Inter-Stage DM Telemetry Calibration Technical Report."
    )
    parser.add_argument("--work-root", default="_work", help="Path to _work directory")
    parser.add_argument(
        "--outdir",
        default="",
        help="Output report directory (default: <work-root>/calib_2wfs1dm_report)",
    )
    args = parser.parse_args(argv)

    work_root = Path(args.work_root).resolve()
    out_dir = Path(args.outdir).resolve() if args.outdir else (work_root / "calib_2wfs1dm_report")
    cache_dir = out_dir / "_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    base_cal = work_root / "ao3k_scexao_calib2wfs1dm"
    base_op = work_root / "ao3k_scexao_lowfs_open"
    base_cl = work_root / "ao3k_scexao_lowfs_closed"
    for p in (base_cal, base_op, base_cl):
        if not (p / "telemetry").is_dir():
            raise FileNotFoundError(f"Missing required telemetry directory: {p / 'telemetry'}")

    print("[calib-report] Step 1/5: Loading/running W(z) AR(p) sweeps & regime calibrations...")
    sweeps = run_all_sweeps(base_cal, base_op, base_cl, cache_dir)

    print("[calib-report] Step 2/5: Computing geometric DM2->DM1 offload & ZPO diagnostics...")
    offload = compute_offload_and_zpo(base_cal, sweeps)

    print("[calib-report] Step 3/5: Running Exact-Window Frequency-Domain AO-Dynamics benchmarks...")
    method_bench = compute_method_benchmarks(base_cal, base_op, base_cl, sweeps)

    print("[calib-report] Step 4/5: Rendering 4 publication-grade diagnostic figures...")
    render_all_figures(base_cal, out_dir, sweeps, offload, method_bench)

    print("[calib-report] Step 5/5: Writing CSV, JSON, study_meta.json, and REPORT.md...")
    write_outputs(base_cal, out_dir, sweeps, offload["offload_stats"], method_bench)

    print(f"[calib-report] Done -> {out_dir / 'REPORT.md'}")
    return 0
