#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Export per-run summary metrics CSV for the predictive control study."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

def write_summary_csv(
    bundles: list[dict[str, Any]],
    out_path: Path,
    eof_bundles: list[dict[str, Any]] | None = None,
) -> None:
    """Write machine-readable CSV summary across all Part I and Part II compared runs."""
    cols = [
        "key",
        "label",
        "slug",
        "pf_mode",
        "blocksize",
        "order",
        "n_min",
        "n_train",
        "raw_wfe_nm",
        "stg1_wfe_nm",
        "stg1_mean_nm",
        "stg1_std_nm",
        "final_wfe_nm",
        "final_std_nm",
        "vis_stg1_sr_pct",
        "vis_final_sr_pct",
        "nir_stg1_sr_pct",
        "nir_final_sr_pct",
        "coro_leak_pct",
        "coro_c3_10",
        "coro_c5_20",
        "coro_c5",
        "coro_c10",
        "coro_5s_5",
        "stg1_var_red_pct",
        "stg2_var_red_pct",
        "mkarpf1_p50_ms",
        "mkarpf2_p50_ms",
        "applyarpf1_p50_us",
        "applyarpf2_p50_us",
        "pf_total_cpu_pct",
    ]
    all_runs = list(bundles) + (list(eof_bundles) if eof_bundles else [])
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for b in all_runs:
            s = b["summary"]
            pf = s["pf_stats"] or {}
            pr = s["procs"]
            is_eof = s.get("pf_mode") == "eof"
            mk1_k = "mkEOFPF-1" if is_eof else "mkARPF-1"
            mk2_k = "mkEOFPF-2" if is_eof else "mkARPF-2"
            ap1_k = "applyEOFPF-1" if is_eof else "applyARPF-1"
            ap2_k = "applyEOFPF-2" if is_eof else "applyARPF-2"
            pf_cpu = sum(
                pr.get(nm, {}).get("cl_cpu_pct", 0.0) for nm in (mk1_k, mk2_k, ap1_k, ap2_k)
            )
            writer.writerow(
                {
                    "key": s["key"],
                    "label": s["label"],
                    "slug": s["slug"],
                    "pf_mode": s.get("pf_mode", "ar"),
                    "blocksize": s.get("blocksize", 1),
                    "order": s["order"],
                    "n_min": s["n_min"],
                    "n_train": s["n_train"],
                    "raw_wfe_nm": f"{s['raw_wfe_nm']:.2f}",
                    "stg1_wfe_nm": f"{s['stg1_wfe_nm']:.2f}",
                    "stg1_mean_nm": f"{s['stg1_mean_nm']:.2f}",
                    "stg1_std_nm": f"{s['stg1_std_nm']:.2f}",
                    "final_wfe_nm": f"{s['final_wfe_nm']:.2f}",
                    "final_std_nm": f"{s['final_std_nm']:.2f}",
                    "vis_stg1_sr_pct": f"{s['vis_stg1_sr_pct']:.3f}",
                    "vis_final_sr_pct": f"{s['vis_final_sr_pct']:.3f}",
                    "nir_stg1_sr_pct": f"{s['nir_stg1_sr_pct']:.3f}",
                    "nir_final_sr_pct": f"{s['nir_final_sr_pct']:.3f}",
                    "coro_leak_pct": f"{s['coro_leak_pct']:.4f}",
                    "coro_c3_10": f"{s['coro_c3_10']:.4e}",
                    "coro_c5_20": f"{s['coro_c5_20']:.4e}",
                    "coro_c5": f"{s['coro_c5']:.4e}",
                    "coro_c10": f"{s['coro_c10']:.4e}",
                    "coro_5s_5": f"{s['coro_5s_5']:.4e}",
                    "stg1_var_red_pct": (
                        f"{pf['stage1']['var_red_pct']:.3f}" if "stage1" in pf else ""
                    ),
                    "stg2_var_red_pct": (
                        f"{pf['stage2']['var_red_pct']:.3f}" if "stage2" in pf else ""
                    ),
                    "mkarpf1_p50_ms": (
                        f"{pr[mk1_k]['exec_p50_us'] / 1e3:.2f}" if mk1_k in pr else ""
                    ),
                    "mkarpf2_p50_ms": (
                        f"{pr[mk2_k]['exec_p50_us'] / 1e3:.2f}" if mk2_k in pr else ""
                    ),
                    "applyarpf1_p50_us": (
                        f"{pr[ap1_k]['exec_p50_us']:.2f}" if ap1_k in pr else ""
                    ),
                    "applyarpf2_p50_us": (
                        f"{pr[ap2_k]['exec_p50_us']:.2f}" if ap2_k in pr else ""
                    ),
                    "pf_total_cpu_pct": f"{pf_cpu:.2f}",
                }
            )
