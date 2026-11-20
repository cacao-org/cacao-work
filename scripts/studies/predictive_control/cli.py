#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CLI entrypoint for the Predictive Control Technical Report generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .csv_summary import write_summary_csv
from .loader import load_run_bundle
from .markdown_eof import generate_report_markdown
from .plots_ar_analysis import plot_fig3_filter_anatomy, plot_fig4_modal_and_psd
from .plots_ar_compute import plot_fig6_psf_and_compute
from .plots_ar_perf import plot_fig1_optical_coro, plot_fig2_timeseries_and_petals
from .plots_ar_scaling import plot_fig5_bias_variance
from .plots_eof_closed_loop import plot_fig8_eof_closed_loop
from .plots_eof_offline import plot_fig7_eof_offline
from .solvers import run_eof_offline_20s_study, run_walk_forward_study
from .specs import EOF_RUN_SPECS, RUN_SPECS, configure_matplotlib

def main(argv: list[str] | None = None) -> int:
    """Generate the comparative Predictive Control Report (Diag AR & Block-EOF)."""
    configure_matplotlib()
    parser = argparse.ArgumentParser(
        description="Build the comparative Predictive Control Report (Diag AR & Block-EOF)."
    )
    parser.add_argument(
        "--work-root",
        default=str(Path(__file__).resolve().parent.parent / "_work"),
        help="Root _work directory containing ao3k_scexao_* runs",
    )
    parser.add_argument(
        "--outdir",
        default="",
        help="Output report directory (default: <work-root>/predictive_control_report)",
    )
    args = parser.parse_args(argv)

    work_root = Path(args.work_root).resolve()
    out_dir = (
        Path(args.outdir).resolve()
        if args.outdir
        else (work_root / "predictive_control_report")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[predictive-report] Loading {len(RUN_SPECS)} Part I + {len(EOF_RUN_SPECS)} Part II "
        f"simulation bundles from {work_root}..."
    )
    bundles = [load_run_bundle(work_root, spec) for spec in RUN_SPECS]
    eof_bundles = [load_run_bundle(work_root, spec) for spec in EOF_RUN_SPECS]

    print("[predictive-report] Running Part I walk-forward bias-variance analysis...")
    wf_study = run_walk_forward_study(work_root)

    print("[predictive-report] Running Part II 20 s offline cross-mode Block-EOF study...")
    eof_study = run_eof_offline_20s_study(work_root)

    print("[predictive-report] Rendering 8 publication-grade comparison figures...")
    plot_fig1_optical_coro(bundles, out_dir)
    plot_fig2_timeseries_and_petals(bundles, out_dir)
    plot_fig3_filter_anatomy(bundles, out_dir)
    plot_fig4_modal_and_psd(bundles, out_dir)
    plot_fig5_bias_variance(wf_study, bundles, out_dir)
    plot_fig6_psf_and_compute(bundles, out_dir)
    bmap = {b["spec"]["key"]: b for b in bundles}
    plot_fig7_eof_offline(eof_study, eof_bundles, out_dir)
    plot_fig8_eof_closed_loop(eof_bundles, bmap["ar16"], out_dir)

    print("[predictive-report] Writing JSON, CSV, study_meta.json, and REPORT.md...")
    write_summary_csv(bundles, out_dir / "predictive_control_summary.csv", eof_bundles)

    emap = {b["spec"]["key"]: b for b in eof_bundles}
    s_ar16 = bmap["ar16"]["summary"]
    s_ab32 = bmap["ar32_n4096"]["summary"]
    s_ab64 = bmap["ar64_n4096"]["summary"]
    s_e128 = emap["eof128_p8"]["summary"]
    s_am14 = emap["ar16_matched_w14s"]["summary"]
    repro = bmap["ar16"]["metrics"].get("reproducibility", {})

    comp_json = {
        "study": (
            "Per-Mode Diagonal AR(4..64) & Cross-Mode Transition Matrix Block-EOF (VAR) "
            "Predictive Control Study"
        ),
        "runs": [b["summary"] for b in bundles],
        "eof_runs": [b["summary"] for b in eof_bundles],
        "filter_anatomy": {
            b["spec"]["key"]: {
                f"stage{stg}": {
                    "order": fd["order"],
                    "lo_norm2": fd["lo_norm2"],
                    "lo_dc": fd["lo_dc"],
                    "lo_lead_fr": fd["lo_lead_fr"],
                    "mid_norm2": fd["mid_norm2"],
                    "mid_lead_fr": fd["mid_lead_fr"],
                    "med_dc": fd["med_dc"],
                    "med_norm2": fd["med_norm2"],
                    "max_norm2": fd["max_norm2"],
                    "tail_gt8_sum_lo": fd["tail_gt8_sum_lo"],
                }
                for stg, fd in b["filters"].items()
            }
            for b in bundles
            if b["filters"]
        },
        "walk_forward": wf_study,
        "eof_offline_20s": eof_study,
        "reproducibility": repro,
    }
    (out_dir / "predictive_control_comparison.json").write_text(
        json.dumps(comp_json, indent=2) + "\n", encoding="utf-8"
    )

    study_meta = {
        "report_type": "tech_report",
        "domain": "wavefront-control",
        "subtopic": "diagonal-ar",
        "topic": "PSOL Predictive Control (Diagonal AR & Cross-Mode Block-EOF)",
        "cacao_features": [
            "PSOL Predictive Control",
            "Diagonal AR(4..64)",
            "Cross-Mode Block-EOF (VAR)",
            "Stage-3 LLOWFS",
        ],
        "referenced_simulations": list(
            dict.fromkeys(spec["slug"] for spec in RUN_SPECS + EOF_RUN_SPECS)
        ),
        "nav_label": "Predictive Control Report",
        "button_label": "Read Predictive Control Report",
        "summary": (
            "Hardware-in-the-loop comparison of Part I per-mode diagonal AR(4..64) and "
            "Part II full cross-mode transition-matrix Block-EOF(B=64/128, P=8) predictive "
            "controllers on Subaru AO3k + SCExAO + Lyot Coronagraph + LLOWFS."
        ),
        "badges": [
            "FEATURED STUDY",
            "Part I: Diag AR(4..64) | Part II: Cross-Mode Block-EOF",
            f"Block-EOF(128,8): Final Vis SR {s_e128['vis_final_sr_pct']:.1f}%",
            f"Stg1 Vis SR {s_e128['vis_stg1_sr_pct']:.1f}% "
            f"(+{s_e128['vis_stg1_sr_pct'] - s_am14['vis_stg1_sr_pct']:.1f} pp vs AR16)",
            f"WFE {s_e128['final_wfe_nm']:.1f} nm",
            f"Diag AR(16) {s_ar16['vis_final_sr_pct']:.1f}%",
            f"Warm AR(32)*/AR(64)* "
            f"{s_ab32['vis_final_sr_pct']:.1f}/{s_ab64['vis_final_sr_pct']:.1f}%",
            "0 RT Timeouts",
        ],
        "reproducibility": repro,
    }
    (out_dir / "study_meta.json").write_text(
        json.dumps(study_meta, indent=2) + "\n", encoding="utf-8"
    )

    md_text = generate_report_markdown(bundles, wf_study, eof_bundles, eof_study)
    (out_dir / "REPORT.md").write_text(md_text, encoding="utf-8")

    print(f"[predictive-report] Done -> {out_dir / 'REPORT.md'}")
    return 0
