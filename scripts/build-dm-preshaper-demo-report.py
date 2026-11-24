#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CLI entrypoint for the live GPU DM Anti-Vibration Pre-Shaper Demonstration Report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.studies.dm_preshaper_demo.acquire import (  # noqa: E402
    run_acquisition,
    run_per_actuator_acquisition,
)
from scripts.studies.dm_preshaper_demo.markdown import write_report_and_meta  # noqa: E402
from scripts.studies.dm_preshaper_demo.plots import build_all_figures_and_metrics  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the live GPU 64x64 ALPAO Plate DM Pre-Shaper Demonstration Report."
    )
    parser.add_argument("--work-root", default="_work", help="Path to _work directory")
    parser.add_argument(
        "--outdir",
        default="",
        help="Output report directory (default: <work-root>/dm_preshaper_demo)",
    )
    parser.add_argument(
        "--raw-dir",
        default="",
        help="Raw calibration & replay cache directory (default: <work-root>/_dm_preshaper_demo_raw)",
    )
    parser.add_argument(
        "--rerun-acq",
        action="store_true",
        help="Force re-running live GPU cacaosim + cacao acquisition and replays",
    )
    parser.add_argument(
        "--rerun-per-act",
        action="store_true",
        help="Force re-running only the 8 kHz 64x64 per-actuator KMODE=3/4 acquisition and replays",
    )
    args = parser.parse_args(argv)

    work_root = (
        Path(args.work_root).resolve()
        if Path(args.work_root).is_absolute()
        else (REPO_ROOT / args.work_root).resolve()
    )
    out_dir = Path(args.outdir).resolve() if args.outdir else (work_root / "dm_preshaper_demo")
    raw_dir = Path(args.raw_dir).resolve() if args.raw_dir else (work_root / "_dm_preshaper_demo_raw")

    if args.rerun_acq or not (raw_dir / "calib_meta.json").is_file():
        print(f"[dm-preshaper-demo] Step 1/3: Running live GPU acquisition -> {raw_dir}")
        run_acquisition(raw_dir)
    elif args.rerun_per_act or not (raw_dir / "peract_meta.json").is_file():
        print(f"[dm-preshaper-demo] Step 1/3: Running live 8 kHz per-actuator KMODE=3/4 acquisition -> {raw_dir}")
        run_per_actuator_acquisition(raw_dir)
    else:
        print(f"[dm-preshaper-demo] Step 1/3: Using cached live GPU data in {raw_dir}")

    print(f"[dm-preshaper-demo] Step 2/3: Computing metrics, figures & side-by-side MP4 -> {out_dir}")
    summary = build_all_figures_and_metrics(raw_dir, out_dir)

    print(f"[dm-preshaper-demo] Step 3/3: Writing REPORT.md & study_meta.json -> {out_dir}")
    write_report_and_meta(out_dir, REPO_ROOT.parent, summary)
    print(f"[dm-preshaper-demo] Done -> {out_dir / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
