#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Optical time-series, modal gain, and coronagraphic contrast extractors."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from .common import load_json_safe


def _downsample_indices(n_total: int, max_pts: int) -> list[int]:
    """Return evenly spaced row indices capped at max_pts."""
    if n_total <= max_pts:
        return list(range(n_total))
    step = (n_total - 1) / float(max_pts - 1)
    return sorted({int(round(i * step)) for i in range(max_pts)})


def _interp_clamped(t: float, xs: list[float], ys: list[float]) -> float:
    """Piecewise-linear interpolation with constant endpoint clamping."""
    if not xs or not ys:
        return 0.0
    if len(xs) == 1 or t <= xs[0]:
        return ys[0]
    if t >= xs[-1]:
        return ys[-1]
    lo = 0
    hi = len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= t:
            lo = mid
        else:
            hi = mid
    dt = xs[hi] - xs[lo]
    if dt <= 1.0e-12:
        return ys[lo]
    alpha = (t - xs[lo]) / dt
    return ys[lo] * (1.0 - alpha) + ys[hi] * alpha


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


def _attach_wf_ctrl_breakdown(
    wf_ts: dict[str, object],
    out_slug_dir: Path,
    metrics_data: dict[str, object],
) -> None:
    """Populate within/outside control-mode WFE curves & metadata in wf_ts."""
    t_arr = wf_ts.get("t_phys_s")
    if not isinstance(t_arr, list) or not t_arr:
        return

    bd = load_json_safe(out_slug_dir / "wf_ctrl_breakdown.json")
    if not bd:
        wfm = metrics_data.get("wavefront_metrics")
        if isinstance(wfm, dict) and isinstance(wfm.get("control_mode_breakdown"), dict):
            bd = dict(wfm["control_mode_breakdown"])

    loops = metrics_data.get("loops") if isinstance(metrics_data.get("loops"), dict) else {}
    s1_loop = loops.get("stage1_ao3k") if isinstance(loops.get("stage1_ao3k"), dict) else {}
    s2_loop = loops.get("stage2_scexao") if isinstance(loops.get("stage2_scexao"), dict) else {}
    wf_stats = load_json_safe(out_slug_dir / "wf_stats.json")
    cm_stat = wf_stats.get("control_modes") if isinstance(wf_stats.get("control_modes"), dict) else {}

    stg1_modes = int(
        bd.get("stg1_cm_modes")
        or cm_stat.get("stg1_cm_modes")
        or s1_loop.get("n_cm_modes")
        or 0
    )
    stg2_modes = int(
        bd.get("stg2_cm_modes")
        or cm_stat.get("stg2_cm_modes")
        or s2_loop.get("n_cm_modes")
        or 0
    )
    final_modes = int(
        bd.get("final_basis_rank")
        or cm_stat.get("final_basis_rank")
        or max(stg1_modes, stg2_modes)
    )

    has_exact = (
        isinstance(wf_ts.get("rms_stg1_in_nm"), list)
        and isinstance(wf_ts.get("rms_stg1_out_nm"), list)
        and len(wf_ts["rms_stg1_in_nm"]) == len(t_arr)
    )
    if has_exact:
        wf_ts["ctrl_meta"] = {
            "source": "exact_per_frame",
            "stg1_modes": stg1_modes,
            "stg2_modes": stg2_modes,
            "final_modes": final_modes,
        }
        return

    planes = bd.get("planes") if isinstance(bd.get("planes"), dict) else {}
    if not planes:
        return

    # Optional turbulence Cn2 scale time series to track bursts in out-of-control fitting error
    pert_ts = _read_csv_downsampled(
        out_slug_dir / "perturb_timeseries.csv",
        ["t_phys_s", "cn2_scale"],
        max_pts=400,
    )
    pt_t = pert_ts.get("t_phys_s") or []
    pt_cn2 = pert_ts.get("cn2_scale") or []
    has_cn2 = (
        len(pt_t) >= 2
        and len(pt_t) == len(pt_cn2)
        and (max(pt_cn2) - min(pt_cn2)) > 1.0e-3
    )

    any_added = False
    for pk in ("raw", "stg1", "final"):
        tot_key = f"rms_{pk}_nm"
        tot_vals = wf_ts.get(tot_key)
        pinfo = planes.get(pk)
        if not isinstance(tot_vals, list) or len(tot_vals) != len(t_arr) or not isinstance(pinfo, dict):
            continue
        samps = pinfo.get("samples")
        sx: list[float] = []
        sy_out: list[float] = []
        if isinstance(samps, list):
            pairs = []
            for sm in samps:
                if isinstance(sm, dict) and "t_phys_s" in sm and "out_nm" in sm:
                    pairs.append((float(sm["t_phys_s"]), float(sm["out_nm"])))
            pairs.sort(key=lambda pair: pair[0])
            sx = [p[0] for p in pairs]
            sy_out = [p[1] for p in pairs]
        out_fallback = float(pinfo.get("out_rms_nm") or 0.0)
        if not sy_out and out_fallback <= 0.0:
            continue

        # Normalize snapshot out_nm by local sqrt(cn2_scale) if bursts are active
        if has_cn2 and sx:
            sy_base = []
            for ts_s, ov in zip(sx, sy_out):
                c_s = max(_interp_clamped(ts_s, pt_t, pt_cn2), 1.0e-4)
                sy_base.append(ov / math.sqrt(c_s))
        else:
            sy_base = sy_out

        in_arr: list[float] = []
        out_arr: list[float] = []
        for t_val, tot_v in zip(t_arr, tot_vals):
            tot_f = float(tot_v)
            if sx:
                out_f = _interp_clamped(float(t_val), sx, sy_base)
                if has_cn2:
                    c_t = max(_interp_clamped(float(t_val), pt_t, pt_cn2), 1.0e-4)
                    out_f *= math.sqrt(c_t)
            else:
                out_f = out_fallback
                if has_cn2:
                    c_t = max(_interp_clamped(float(t_val), pt_t, pt_cn2), 1.0e-4)
                    out_f *= math.sqrt(c_t)
            if out_f > tot_f:
                out_f = tot_f
            if out_f < 0.0:
                out_f = 0.0
            in_f = math.sqrt(max(0.0, tot_f * tot_f - out_f * out_f))
            in_arr.append(round(in_f, 4))
            out_arr.append(round(out_f, 4))
        wf_ts[f"rms_{pk}_in_nm"] = in_arr
        wf_ts[f"rms_{pk}_out_nm"] = out_arr
        any_added = True

    if any_added:
        wf_ts["ctrl_meta"] = {
            "source": str(bd.get("source") or "snapshot_calibrated"),
            "stg1_modes": stg1_modes,
            "stg2_modes": stg2_modes,
            "final_modes": final_modes,
        }


def extract_optical_explorer_data(
    out_slug_dir: Path,
    metrics_data: dict[str, object],
) -> dict[str, object]:
    """Extract compact JSON arrays for the interactive Optical Performance Explorer."""
    payload: dict[str, object] = {}

    wf_ts: dict[str, object] = _read_csv_downsampled(
        out_slug_dir / "wf_timeseries.csv",
        [
            "t_phys_s",
            "rms_raw_nm",
            "rms_stg1_nm",
            "rms_final_nm",
            "rms_raw_in_nm",
            "rms_raw_out_nm",
            "rms_stg1_in_nm",
            "rms_stg1_out_nm",
            "rms_final_in_nm",
            "rms_final_out_nm",
        ],
        max_pts=200,
    )
    if wf_ts:
        _attach_wf_ctrl_breakdown(wf_ts, out_slug_dir, metrics_data)
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
