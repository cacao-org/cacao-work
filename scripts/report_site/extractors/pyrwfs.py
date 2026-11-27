#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Pyramid WFS live telemetry summary and time-series extractor."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from .common import load_json_safe
from .optical import _read_csv_downsampled

PYRWFS_TS_COLS: list[str] = [
    "t_phys_s",
    "ftot",
    "f_pup",
    "f_diam",
    "f_bH",
    "f_bV",
    "f_out",
    "df_pup",
    "aniso",
    "nl_ratio",
    "qx_mean",
    "qy_mean",
    "qx_rms",
    "qy_rms",
    "qdiag",
    "scint_idx",
    "scint_debias",
    "curl_ratio",
    "lwe_metric",
    "pup_dx",
    "pup_dy",
    "pup_ds",
    "pup_dast",
    "pup_rot",
    "pup_corr",
]


def _summarize_csv_fallback(csv_path: Path, stg_idx: int) -> dict[str, object] | None:
    """Compute a minimal stage summary directly from CSV if summary JSON is missing."""
    if not csv_path.is_file():
        return None
    cols: dict[str, list[float]] = {}
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames or "f_pup" not in reader.fieldnames:
                return None
            for fn in reader.fieldnames:
                cols[fn] = []
            for row in reader:
                for fn in reader.fieldnames:
                    try:
                        cols[fn].append(float(row[fn]))
                    except (TypeError, ValueError):
                        cols[fn].append(float("nan"))
    except OSError:
        return None
    n = len(cols.get("f_pup") or [])
    if n == 0:
        return None

    def _mean(k: str, default: float = 0.0) -> float:
        vals = [v for v in (cols.get(k) or []) if math.isfinite(v)]
        return sum(vals) / len(vals) if vals else default

    def _std(k: str) -> float:
        vals = [v for v in (cols.get(k) or []) if math.isfinite(v)]
        if len(vals) < 2:
            return 0.0
        m = sum(vals) / len(vals)
        return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))

    def _max_abs(k: str) -> float:
        vals = [abs(v) for v in (cols.get(k) or []) if math.isfinite(v)]
        return max(vals) if vals else 0.0

    def _min(k: str, default: float = 0.0) -> float:
        vals = [v for v in (cols.get(k) or []) if math.isfinite(v)]
        return min(vals) if vals else default

    t_vals = [v for v in (cols.get("t_phys_s") or []) if math.isfinite(v)]
    fp_m = _mean("f_pup")
    df_m = _mean("df_pup")
    qxr = _mean("qx_rms")
    qyr = _mean("qy_rms")
    lbl = (
        "Stage 1 (AO3k J-Band PyWFS)"
        if stg_idx == 1
        else "Stage 2 (SCExAO Vis PyWFS)"
    )
    short_lbl = "Stage 1 (AO3k NIR)" if stg_idx == 1 else "Stage 2 (SCExAO Vis)"
    return {
        "stage": stg_idx,
        "label": lbl,
        "short_label": short_lbl,
        "stream": "csim_wfs_nir" if stg_idx == 1 else "csim_wfs_vis",
        "loop_closed": True,
        "lambda_um": 1.22 if stg_idx == 1 else 0.75,
        "rate_hz": 1000.0 if stg_idx == 1 else 2000.0,
        "n_frames": n,
        "n_steady": n,
        "t_start_s": t_vals[0] if t_vals else 0.0,
        "t_end_s": t_vals[-1] if t_vals else 0.0,
        "csv_file": csv_path.name,
        "f_pup0": fp_m - df_m,
        "flux": {
            "f_pup_mean": fp_m,
            "f_pup_std": _std("f_pup"),
            "df_pup_mean": df_m,
            "df_pup_std": _std("df_pup"),
            "f_diam_mean": _mean("f_diam"),
            "f_diam_std": _std("f_diam"),
            "f_bH_mean": _mean("f_bH"),
            "f_bV_mean": _mean("f_bV"),
            "f_out_mean": _mean("f_out"),
            "aniso_mean": _mean("aniso"),
            "aniso_std": _std("aniso"),
            "nl_ratio_mean": _mean("nl_ratio"),
            "nl_ratio_std": _std("nl_ratio"),
        },
        "health": {
            "ftot_mean": _mean("ftot"),
            "ftot_std": _std("ftot"),
            "ftot_rel_std_pct": 100.0 * _std("ftot") / max(abs(_mean("ftot")), 1e-9),
            "bg_mean": _mean("bg_mean"),
            "bg_std": _mean("bg_std"),
            "sat_hi_frac_max": _max_abs("sat_hi_frac"),
            "sat_dark_frac_max": _max_abs("sat_dark_frac"),
            "flux_ok_pct": 100.0 * _mean("flux_ok", 1.0),
        },
        "jitter": {
            "qx_mean": _mean("qx_mean"),
            "qy_mean": _mean("qy_mean"),
            "qx_rms_mean": qxr,
            "qy_rms_mean": qyr,
            "q_tt_rms_quad": math.hypot(qxr, qyr),
            "qdiag_mean": _mean("qdiag"),
            "qdiag_std": _std("qdiag"),
        },
        "wavefront": {
            "scint_idx_mean": _mean("scint_idx"),
            **(
                {"scint_debias_mean": _mean("scint_debias")}
                if "scint_debias" in cols
                else {}
            ),
            "curl_ratio_mean": _mean("curl_ratio"),
            "lwe_metric_mean": _mean("lwe_metric"),
        },
        "alignment": {
            "pup_dx_mean": _mean("pup_dx"),
            "pup_dx_std": _std("pup_dx"),
            "pup_dx_max_abs": _max_abs("pup_dx"),
            "pup_dy_mean": _mean("pup_dy"),
            "pup_dy_std": _std("pup_dy"),
            "pup_dy_max_abs": _max_abs("pup_dy"),
            "pup_ds_mean": _mean("pup_ds"),
            "pup_ds_std": _std("pup_ds"),
            "pup_dast_mean": _mean("pup_dast"),
            "pup_dast_std": _std("pup_dast"),
            "pup_rot_mrad_mean": _mean("pup_rot"),
            "pup_rot_mrad_std": _std("pup_rot"),
            "pup_corr_mean": _mean("pup_corr", 1.0),
            "pup_corr_min": _min("pup_corr", 1.0),
            "pupgeom": [],
        },
        "crosscheck": {},
    }


def extract_pyrwfs_telemetry_data(
    out_slug_dir: Path,
    metrics_data: dict[str, object],
) -> dict[str, object] | None:
    """Extract Pyramid WFS telemetry summary and downsampled series for pyrwfs.html."""
    summary: dict[str, object] = {}
    sum_path = out_slug_dir / "pyrwfs_tlm_summary.json"
    if sum_path.is_file():
        loaded = load_json_safe(sum_path)
        if isinstance(loaded, dict):
            summary = dict(loaded)
    if not summary:
        mt = metrics_data.get("pyrwfs_telemetry")
        if isinstance(mt, dict):
            summary = dict(mt)

    stages_in = summary.get("stages") if isinstance(summary.get("stages"), dict) else {}
    stages: dict[str, dict[str, object]] = {}
    for skey in ("stage1", "stage2"):
        sd = stages_in.get(skey)
        if isinstance(sd, dict):
            stages[skey] = dict(sd)

    for stg_i, skey in ((1, "stage1"), (2, "stage2")):
        if skey not in stages:
            fb = _summarize_csv_fallback(out_slug_dir / f"pyrwfs_tlm_stg{stg_i}.csv", stg_i)
            if fb is not None:
                stages[skey] = fb

    wl_data: dict[str, object] | None = None
    wl_path = out_slug_dir / "windlayers_summary.json"
    if wl_path.is_file():
        loaded_wl = load_json_safe(wl_path)
        if isinstance(loaded_wl, dict) and loaded_wl.get("enabled"):
            wl_data = dict(loaded_wl)
    if wl_data is None:
        m_wl = metrics_data.get("windlayers")
        if isinstance(m_wl, dict) and m_wl.get("enabled"):
            wl_data = dict(m_wl)

    if not stages and wl_data is None:
        return None

    timeseries: dict[str, dict[str, list[float]]] = {}
    for stg_i, skey in ((1, "stage1"), (2, "stage2")):
        if skey not in stages:
            continue
        csv_name = str(stages[skey].get("csv_file") or f"pyrwfs_tlm_stg{stg_i}.csv")
        ts = _read_csv_downsampled(out_slug_dir / csv_name, PYRWFS_TS_COLS, max_pts=220)
        if ts:
            timeseries[skey] = ts

    return {
        "enabled": True,
        "spider_angle_deg": float(summary.get("spider_angle_deg", 51.75)),
        "reg_stride": int(summary.get("reg_stride", 20)),
        "stages": stages,
        "timeseries": timeseries,
        "windlayers": wl_data,
    }
