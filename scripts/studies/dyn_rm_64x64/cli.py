# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CLI entrypoint for the ALPAO 64x64 Plate DM 3D Response Matrix Calibration Report."""

from __future__ import annotations

import argparse
from pathlib import Path

from .acquire import run_live_64x64_acquisition
from .markdown import write_report_outputs
from .plots import (
    render_exposure_deconv_1x2,
    render_modal_28x28_2x2,
    render_radial_and_timing_2x2,
    render_wave_video_and_contact_sheet,
)


def main(argv: list[str] | None = None) -> int:
    """Acquire live 64x64 ALPAO plate 3D RMs and build the complete web report bundle."""
    parser = argparse.ArgumentParser(
        description="Build the ALPAO 64x64 Plate DM Raw 3D RM Calibration Report."
    )
    parser.add_argument("--work-root", default="_work", help="Path to _work directory")
    parser.add_argument(
        "--outdir",
        default="",
        help="Output report directory (default: <work-root>/dm64_dyn_rm_calib)",
    )
    parser.add_argument(
        "--rerun-acq",
        action="store_true",
        help="Force re-running live cacaosim + cacaoac-measdynresp acquisitions",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[3]
    src_root = repo_root.parent
    work_root = (
        Path(args.work_root).resolve()
        if Path(args.work_root).is_absolute()
        else (repo_root / args.work_root).resolve()
    )
    out_dir = Path(args.outdir).resolve() if args.outdir else (work_root / "dm64_dyn_rm_calib")
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw_calib"

    print(f"[dm64-dyn-rm] Step 1/5: Live 64x64 ALPAO plate acquisition -> {raw_dir}")
    summary = run_live_64x64_acquisition(
        repo_root=repo_root,
        out_dir=out_dir,
        rerun=args.rerun_acq,
    )

    print("[dm64-dyn-rm] Step 2/5: Rendering stroboscopic 3D RM video & contact sheet...")
    video_info = render_wave_video_and_contact_sheet(raw_dir, out_dir, summary, fps=12.0)

    print("[dm64-dyn-rm] Step 3/5: Rendering 2x2 radial dynamics, timing & static-parity plots...")
    render_radial_and_timing_2x2(raw_dir, out_dir, summary)

    print("[dm64-dyn-rm] Step 4/5: Rendering 2x2 28x28 modal dispersion & PSOL benchmark...")
    render_modal_28x28_2x2(raw_dir, out_dir, summary)

    print("[dm64-dyn-rm] Step 5/5: Rendering exposure deconvolution preview & REPORT.md...")
    _, deconv_info = render_exposure_deconv_1x2(raw_dir, out_dir, summary)
    write_report_outputs(
        out_dir=out_dir,
        src_root=src_root,
        summary=summary,
        video_info=video_info,
        deconv_info=deconv_info,
    )
    print(f"[dm64-dyn-rm] Done -> {out_dir / 'REPORT.md'}")
    return 0
