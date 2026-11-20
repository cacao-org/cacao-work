#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Optical time-series, modal gain, and coronagraphic contrast extractors."""

from __future__ import annotations

import csv
from pathlib import Path


def _downsample_indices(n_total: int, max_pts: int) -> list[int]:
    """Return evenly spaced row indices capped at max_pts."""
    if n_total <= max_pts:
        return list(range(n_total))
    step = (n_total - 1) / float(max_pts - 1)
    return sorted({int(round(i * step)) for i in range(max_pts)})


def _read_csv_downsampled(
    csv_path: Path,
    cols: list[str],
    max_pts: int = 200,
) -> dict[str, list[float]]:
    """Read numeric columns from a CSV file with even downsampling."""
    if not csv_path.is_file():
        return {}
    rows: list[list[float]] = []
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return {}
            avail_cols = [c for c in cols if c in reader.fieldnames]
            if not avail_cols:
                return {}
            for row in reader:
                vals: list[float] = []
                valid = True
                for c in avail_cols:
                    try:
                        vals.append(float(row[c]))
                    except (TypeError, ValueError):
                        valid = False
                        break
                if valid:
                    rows.append(vals)
    except OSError:
        return {}
    if not rows:
        return {}
    idxs = _downsample_indices(len(rows), max_pts)
    out: dict[str, list[float]] = {c: [] for c in avail_cols}
    for idx in idxs:
        r = rows[idx]
        for j, c in enumerate(avail_cols):
            out[c].append(round(r[j], 5))
    return out


def extract_optical_explorer_data(
    out_slug_dir: Path,
    metrics_data: dict[str, object],
) -> dict[str, object]:
    """Extract compact JSON arrays for the interactive Optical Performance Explorer."""
    payload: dict[str, object] = {}

    wf_ts = _read_csv_downsampled(
        out_slug_dir / "wf_timeseries.csv",
        ["t_phys_s", "rms_raw_nm", "rms_stg1_nm", "rms_final_nm"],
        max_pts=200,
    )
    if wf_ts:
        payload["wf_timeseries"] = wf_ts

    sr_ts = _read_csv_downsampled(
        out_slug_dir / "strehl_timeseries.csv",
        [
            "t_phys_s",
            "vis_stg1_inst",
            "vis_final_inst",
            "vis_final_long",
            "nir_stg1_inst",
            "nir_final_inst",
            "nir_final_long",
        ],
        max_pts=200,
    )
    if sr_ts:
        payload["strehl_timeseries"] = sr_ts

    loops = metrics_data.get("loops")
    if isinstance(loops, dict):
        modal_stages: list[dict[str, object]] = []
        for skey, slbl in (
            ("stage1_ao3k", "Stage 1 (AO3k)"),
            ("stage2_scexao", "Stage 2 (SCExAO)"),
            ("stage3_llowfs", "Stage 3 (LLOWFS)"),
        ):
            st = loops.get(skey)
            if not isinstance(st, dict):
                continue
            mg = st.get("mgain_curve")
            rg = st.get("mode_rel_grad")
            if isinstance(mg, list) and mg:
                idxs = _downsample_indices(len(mg), 180)
                entry: dict[str, object] = {
                    "key": skey,
                    "label": slbl,
                    "n_modes": len(mg),
                    "mode_idx": idxs,
                    "mgain": [round(float(mg[i]), 5) for i in idxs],
                }
                if isinstance(rg, list) and len(rg) == len(mg):
                    entry["rel_grad"] = [round(float(rg[i]), 6) for i in idxs]
                modal_stages.append(entry)
        if modal_stages:
            payload["modal_stages"] = modal_stages

    cm = metrics_data.get("coronagraph_metrics")
    if isinstance(cm, dict) and isinstance(cm.get("contrast_table"), list):
        ctbl = [
            {
                "sep_ld": float(r.get("sep_ld", 0.0)),
                "cl_raw": float(r.get("cl_raw_contrast", 0.0)),
                "cl_planet": float(r.get("cl_planet_contrast", 0.0)),
                "cl_5sig": float(r.get("cl_5sigma_planet_contrast", 0.0)),
                "dl_raw": float(r.get("dl_raw_contrast", 0.0)),
            }
            for r in cm["contrast_table"]
            if isinstance(r, dict)
        ]
        if ctbl:
            payload["contrast_table"] = ctbl

    return payload
