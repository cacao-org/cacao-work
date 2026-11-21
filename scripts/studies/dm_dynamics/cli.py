# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CLI entrypoint for building the ALPAO 64x64 DM Spatiotemporal Dynamics technical report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .markdown import write_report_outputs
from .plots import (
    render_dm_shape_vs_deriv_media,
    render_physics_diagnostics_2x2,
    render_side_by_side_video_and_sheet,
    render_video_poster,
)

_BENCH_LINE_RE = re.compile(
    r"^\s*(DM [^|]+?)\s*\|\s*(CPU|CUDA)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*"
    r"([0-9.]+)\s*\|\s*([0-9.]+)\s*kHz"
)


def _run_dm_benchmarks(cacaosim_root: Path) -> list[dict[str, Any]]:
    bench_bin = cacaosim_root / "_build" / "cacaosim-benchmark"
    defaults = [
        {
            "name": "DM 20x20 -> 128x128 OPD",
            "short_label": "20×20 RC\n(128² OPD)",
            "display": "DM 20×20 RC → 128×128 OPD",
            "cpu_us": 21.5,
            "cpu_p50_us": 21.5,
            "cpu_khz": 46.5,
            "cuda_us": 12.5,
            "cuda_p50_us": 12.8,
            "cuda_khz": 80.0,
        },
        {
            "name": "DM 50x50 -> 256x256 OPD",
            "short_label": "50×50 MEMS RC\n(256² OPD)",
            "display": "DM 50×50 MEMS (`dyn_mode=rc`) → 256×256 OPD",
            "cpu_us": 81.6,
            "cpu_p50_us": 81.2,
            "cpu_khz": 12.25,
            "cuda_us": 25.7,
            "cuda_p50_us": 25.6,
            "cuda_khz": 38.93,
        },
        {
            "name": "DM 64x64 plate -> 256x256 OPD",
            "short_label": "64×64 ALPAO Plate\n(256² OPD, 8 kHz tick)",
            "display": "**DM 64×64 ALPAO (`dyn_mode=plate`, `dt=125 μs` / `4×` ovs, `nsub=5`) → 256×256 OPD**",
            "cpu_us": 249.0,
            "cpu_p50_us": 247.0,
            "cpu_khz": 4.02,
            "cuda_us": 97.5,
            "cuda_p50_us": 97.4,
            "cuda_khz": 10.25,
        },
    ]
    if not bench_bin.is_file():
        return defaults
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = "4"
    env["CACAOSIM_SRC_DIR"] = str(cacaosim_root)
    try:
        res = subprocess.run(
            [str(bench_bin)],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            check=False,
        )
    except Exception:
        return defaults
    by_name = {r["name"]: dict(r) for r in defaults}
    for line in res.stdout.splitlines():
        m = _BENCH_LINE_RE.match(line)
        if not m:
            continue
        name, back, mean_s, p50_s, _p99_s, khz_s = m.groups()
        row = by_name.get(name.strip())
        if row is None:
            continue
        if back == "CPU":
            row["cpu_us"] = float(mean_s)
            row["cpu_p50_us"] = float(p50_s)
            row["cpu_khz"] = float(khz_s)
        elif back == "CUDA":
            row["cuda_us"] = float(mean_s)
            row["cuda_p50_us"] = float(p50_s)
            row["cuda_khz"] = float(khz_s)
    return [by_name[r["name"]] for r in defaults]


def main(argv: list[str] | None = None) -> int:
    """Build the ALPAO 64x64 DM Spatiotemporal Plate Dynamics Technical Report."""
    parser = argparse.ArgumentParser(
        description="Build the ALPAO 64x64 DM Spatiotemporal Plate Dynamics Technical Report."
    )
    parser.add_argument("--work-root", default="_work", help="Path to _work directory")
    parser.add_argument(
        "--sim-dir",
        default="",
        help="Path to 20 kHz poke simulation directory (default: <work-root>/dm_ripple_demo)",
    )
    parser.add_argument(
        "--actual-video",
        default="",
        help="Optional path to actual SCExAO LepICSaBL-E MP4 for side-by-side comparison",
    )
    parser.add_argument(
        "--outdir",
        default="",
        help="Output report directory (default: <work-root>/dm_dynamics_report)",
    )
    parser.add_argument(
        "--rerun-sim",
        action="store_true",
        help="Force re-running cacaosim-dm-poke-sim & cacaosim-dm-ripple-video",
    )
    parser.add_argument(
        "--skip-bench",
        action="store_true",
        help="Skip live cacaosim-benchmark run and reuse cached/default 2 kHz timings",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[3]
    src_root = repo_root.parent
    cacaosim_root = src_root / "cacaosim"
    work_root = (
        Path(args.work_root).resolve()
        if Path(args.work_root).is_absolute()
        else (repo_root / args.work_root).resolve()
    )
    sim_dir = Path(args.sim_dir).resolve() if args.sim_dir else (work_root / "dm_ripple_demo")
    out_dir = Path(args.outdir).resolve() if args.outdir else (work_root / "dm_dynamics_report")
    out_dir.mkdir(parents=True, exist_ok=True)

    poke_bin = cacaosim_root / "_build" / "cacaosim-dm-poke-sim"
    vid_bin = cacaosim_root / "scripts" / "cacaosim-dm-ripple-video"

    need_sim = args.rerun_sim or not (sim_dir / "dm_opd_20khz.f32").is_file()
    if need_sim:
        print(f"[dm-dynamics-report] Step 1/6: Running {poke_bin.name} -> {sim_dir}...")
        subprocess.run([str(poke_bin), "--outdir", str(sim_dir)], check=True)
    else:
        print(f"[dm-dynamics-report] Step 1/6: Reusing 20 kHz poke cube in {sim_dir}")

    need_vid = (
        args.rerun_sim
        or not (sim_dir / "dm_poke_sim_20khz.mp4").is_file()
        or not (sim_dir / "ripple_metrics.json").is_file()
    )
    if need_vid:
        print("[dm-dynamics-report] Step 2/6: Rendering standalone simulated MP4 & contact sheet...")
        subprocess.run(
            [str(vid_bin), "--diff-mode", "boxcar", "--gain-1x", "0.25", str(sim_dir)],
            check=True,
        )
    else:
        print("[dm-dynamics-report] Step 2/6: Reusing rendered 20 kHz MP4 & contact sheet")

    meta = json.loads((sim_dir / "meta.json").read_text(encoding="utf-8"))
    ripple_metrics = json.loads((sim_dir / "ripple_metrics.json").read_text(encoding="utf-8"))

    for fname in (
        "dm_poke_sim_20khz.mp4",
        "dm_poke_sim_contact_sheet.png",
        "ripple_metrics.json",
    ):
        shutil.copy2(sim_dir / fname, out_dir / fname)

    actual_mp4 = (
        Path(args.actual_video).resolve()
        if args.actual_video
        else (sim_dir / "actual_LepICSaBL-E.mp4")
    )
    sbs_info: dict[str, Any] | None = None
    if actual_mp4.is_file():
        print(
            f"[dm-dynamics-report] Step 3/6: Rendering synchronized side-by-side MP4 & sheet "
            f"using {actual_mp4.name}..."
        )
        sbs_info = render_side_by_side_video_and_sheet(
            sim_dir, actual_mp4, out_dir, meta, gain_1x=0.25, fps=10.0
        )
    else:
        print("[dm-dynamics-report] Step 3/6: No actual_LepICSaBL-E.mp4 found; skipping SBS video")

    if args.skip_bench:
        bench_rows = _run_dm_benchmarks(Path("/nonexistent"))
    else:
        print("[dm-dynamics-report] Step 4/6: Measuring live 2 kHz DM CPU/CUDA benchmarks...")
        bench_rows = _run_dm_benchmarks(cacaosim_root)

    print("[dm-dynamics-report] Step 5/6: Rendering instantaneous DM shape vs 1 ms derivative video & sheet...")
    gain_1x = float(ripple_metrics.get("gain_1x", 0.25))
    shape_info = render_dm_shape_vs_deriv_media(sim_dir, out_dir, meta, gain_1x=gain_1x, fps=10.0)

    print("[dm-dynamics-report] Step 6/6: Rendering poster, 2x2 physics diagnostics & REPORT.md...")
    render_video_poster(sim_dir, out_dir, meta, gain_1x=gain_1x)
    diag = render_physics_diagnostics_2x2(sim_dir, out_dir, meta, bench_rows)
    write_report_outputs(
        out_dir=out_dir,
        src_root=src_root,
        meta=meta,
        ripple_metrics=ripple_metrics,
        diag=diag,
        bench_rows=bench_rows,
        sbs_info=sbs_info,
        shape_info=shape_info,
    )
    print(f"[dm-dynamics-report] Done -> {out_dir / 'REPORT.md'}")
    return 0
