#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Extract headline badges, comparison metrics, and reproducibility metadata."""

from __future__ import annotations

from pathlib import Path

from .common import find_metrics_path, load_json_safe
from .params import extract_run_parameters


def extract_metrics_highlights(
    out_slug_dir: Path,
) -> tuple[
    list[str],
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, str],
    dict[str, object],
]:
    """Extract badges, reproducibility, comparison stats, params, and raw metrics dict."""
    metrics_path = find_metrics_path(out_slug_dir)
    if metrics_path is None:
        return [], None, None, {}, {}
    data = load_json_safe(metrics_path)
    if not data:
        return [], None, None, {}, {}

    badges: list[str] = []
    vis_sr_pct: float | None = None
    nir_sr_pct: float | None = None
    wfe_nm: float | None = None
    sa = data.get("star_and_atmosphere")
    if isinstance(sa, dict):
        if "seeing_arcsec_500nm" in sa:
            badges.append(f'Seeing {float(sa["seeing_arcsec_500nm"]):.2f}"')
        if "internal_bench_hz" in sa and "internal_dt_us" in sa:
            badges.append(
                f'{float(sa["internal_bench_hz"]) / 1000.0:.1f} kHz '
                f'({float(sa["internal_dt_us"]):.0f} us)'
            )
        if "physical_time_s" in sa:
            badges.append(f'{float(sa["physical_time_s"]):.1f} s phys')
    pm = data.get("psf_metrics")
    if isinstance(pm, dict):
        vis_f = pm.get("vis", {}).get("final", {}) if isinstance(pm.get("vis"), dict) else {}
        nir_f = pm.get("nir", {}).get("final", {}) if isinstance(pm.get("nir"), dict) else {}
        if isinstance(vis_f, dict) and "strehl_peak" in vis_f:
            vis_sr_pct = float(vis_f["strehl_peak"]) * 100.0
            badges.append(f"Vis SR {vis_sr_pct:.1f}%")
        if isinstance(nir_f, dict) and "strehl_peak" in nir_f:
            nir_sr_pct = float(nir_f["strehl_peak"]) * 100.0
            badges.append(f"H SR {nir_sr_pct:.1f}%")
    stg1_wfe_nm: float | None = None
    wm = data.get("wavefront_metrics")
    if isinstance(wm, dict):
        locs = wm.get("locations")
        if isinstance(locs, dict):
            if isinstance(locs.get("stg1"), dict) and "quad_total_rms_nm" in locs["stg1"]:
                stg1_wfe_nm = float(locs["stg1"]["quad_total_rms_nm"])
            if isinstance(locs.get("final"), dict) and "quad_total_rms_nm" in locs["final"]:
                wfe_nm = float(locs["final"]["quad_total_rms_nm"])
                badges.append(f"WFE {wfe_nm:.1f} nm")

    pc = data.get("predictive_control")
    pc_on = bool(isinstance(pc, dict) and pc.get("enabled"))
    pf_mode = str(pc.get("pf_mode", "ar")).lower() if isinstance(pc, dict) and pc_on else "ar"
    pf_blocksize = int(pc.get("pf_blocksize", 128)) if isinstance(pc, dict) and pc_on else 1
    pf_order = int(pc.get("pf_order", 8)) if isinstance(pc, dict) and pc_on else 0
    pf_mix = float(pc.get("pf_mix", 0.90)) if isinstance(pc, dict) and pc_on else 0.0
    pf_vr1: float | None = None
    pf_vr2: float | None = None
    if isinstance(pc, dict) and pc_on:
        s1_pc = pc.get("stage1")
        s2_pc = pc.get("stage2")
        if isinstance(s1_pc, dict) and "var_red_pct" in s1_pc:
            pf_vr1 = float(s1_pc["var_red_pct"])
        if isinstance(s2_pc, dict) and "var_red_pct" in s2_pc:
            pf_vr2 = float(s2_pc["var_red_pct"])

    c2d = data.get("calib_2wfs1dm")
    c2d_on = bool(isinstance(c2d, dict) and c2d.get("enabled"))
    c2d_dim_b = int(c2d.get("dim_b", 40)) if isinstance(c2d, dict) and c2d_on else 0
    c2d_w_ord = int(c2d.get("whiten_order", 4)) if isinstance(c2d, dict) and c2d_on else 0
    c2d_mdb_raw = (
        c2d.get("mdb_diag_med")
        if isinstance(c2d, dict) and c2d_on and c2d.get("mdb_diag_med") is not None
        else (
            c2d.get("mdb_diag_white_med")
            if isinstance(c2d, dict) and c2d_on
            else None
        )
    )
    c2d_mdb = float(c2d_mdb_raw) if c2d_mdb_raw is not None else None
    c2d_r2a = (
        float(c2d["r2_a_raw_med"])
        if isinstance(c2d, dict) and c2d_on and c2d.get("r2_a_raw_med") is not None
        else None
    )
    c2d_srm_raw = None
    if isinstance(c2d, dict) and c2d_on and c2d.get("has_selfrm", True):
        if c2d.get("selfrm_rel_err") is not None:
            c2d_srm_raw = c2d["selfrm_rel_err"]
        elif c2d.get("mdb_vs_selfrm_rel_err") is not None:
            c2d_srm_raw = c2d["mdb_vs_selfrm_rel_err"]
    c2d_srm_err = float(c2d_srm_raw) * 100.0 if c2d_srm_raw is not None else None
    c2d_eta_w = (
        float(c2d["eta_d_white_med"])
        if isinstance(c2d, dict) and c2d_on and c2d.get("eta_d_white_med") is not None
        else None
    )

    cmp_dict: dict[str, object] | None = None
    cm = data.get("coronagraph_metrics")
    has_coro = isinstance(cm, dict)
    lo_on = True
    dm3_rms_nm = 0.0
    coro_leak_pct: float | None = None
    p310_val: float | None = None
    c5_pl: float | None = None
    c5_5s: float | None = None
    lowfs_coro_pct: float | None = None
    lowfs_hpup_pct: float | None = None
    if isinstance(cm, dict):
        lo = cm.get("llowfs") if isinstance(cm.get("llowfs"), dict) else {}
        cl = cm.get("closed_loop") if isinstance(cm.get("closed_loop"), dict) else {}
        lb = cm.get("lowfs_light_budget")
        bcl = lb.get("closed_loop") if isinstance(lb, dict) else {}
        bcl = bcl if isinstance(bcl, dict) else {}
        lo_on = bool(lo.get("enabled_closed_loop", True))
        dm3_rms_nm = float(lo.get("dm3_stroke_rms_nm", 0.0))
        badges.insert(0, "LLOWFS CLOSED" if lo_on else "LLOWFS OPEN")
        if "mean_planet_contrast_3_10ld" in cl:
            p310_val = float(cl["mean_planet_contrast_3_10ld"])
            badges.append(f"Coro 3-10 l/D {p310_val:.2e}")
        if "total_leakage_frac" in cl:
            coro_leak_pct = float(cl["total_leakage_frac"]) * 100.0
        if "frac_coro_in_reaching_lowfs_cam_fov" in bcl:
            lowfs_coro_pct = float(bcl["frac_coro_in_reaching_lowfs_cam_fov"]) * 100.0
            badges.append(f"LOWFS Light {lowfs_coro_pct:.2f}%")
        if "frac_entrance_pup_h_reaching_lowfs_cam_fov" in bcl:
            lowfs_hpup_pct = float(bcl["frac_entrance_pup_h_reaching_lowfs_cam_fov"]) * 100.0

        ctbl = cm.get("contrast_table")
        if isinstance(ctbl, list):
            for row in ctbl:
                if isinstance(row, dict) and abs(float(row.get("sep_ld", 0.0)) - 5.0) < 0.5:
                    c5_pl = float(row.get("cl_planet_contrast", 0.0))
                    c5_5s = float(row.get("cl_5sigma_planet_contrast", 0.0))
                    break

    if c2d_on:
        badges.insert(0, "2-WFS/1-DM CALIB")
        if c2d_mdb is not None:
            badges.append(f"Mdb {c2d_mdb:.2f}")
        if c2d_r2a is not None:
            badges.append(f"R2_A {c2d_r2a:.2f}")
    if pc_on:
        if pf_mode == "eof":
            badges.insert(0, f"PSOL BLOCK-EOF(B={pf_blocksize}, P={pf_order})")
        else:
            badges.insert(0, f"PSOL AR({pf_order}) PREDICTIVE")

    if any(
        v is not None
        for v in (vis_sr_pct, nir_sr_pct, stg1_wfe_nm, wfe_nm)
    ) or has_coro or pc_on or c2d_on:
        cmp_dict = {
            "has_coro": has_coro,
            "predictive_enabled": pc_on,
            "pf_mode": pf_mode,
            "pf_blocksize": pf_blocksize,
            "pf_order": pf_order,
            "pf_mix": pf_mix,
            "pf_var_red_stg1_pct": pf_vr1,
            "pf_var_red_stg2_pct": pf_vr2,
            "llowfs_closed": lo_on,
            "dm3_rms_nm": dm3_rms_nm,
            "vis_sr_pct": vis_sr_pct,
            "nir_sr_pct": nir_sr_pct,
            "stg1_wfe_nm": stg1_wfe_nm,
            "wfe_nm": wfe_nm,
            "coro_leak_pct": coro_leak_pct,
            "planet_contrast_3_10ld": p310_val,
            "planet_contrast_5ld": c5_pl,
            "speckle_5sig_5ld": c5_5s,
            "lowfs_cam_coro_pct": lowfs_coro_pct,
            "lowfs_cam_hpup_pct": lowfs_hpup_pct,
            "calib_2wfs1dm_enabled": c2d_on,
            "calib_2wfs1dm_dim_b": c2d_dim_b,
            "calib_2wfs1dm_whiten_order": c2d_w_ord,
            "calib_2wfs1dm_mdb_diag": c2d_mdb,
            "calib_2wfs1dm_r2_a": c2d_r2a,
            "calib_2wfs1dm_selfrm_err_pct": c2d_srm_err,
            "calib_2wfs1dm_eta_white": c2d_eta_w,
        }

    repro = data.get("reproducibility")
    repro_dict = repro if isinstance(repro, dict) else None
    ropts_path = out_slug_dir / "run_options.json"
    run_options = load_json_safe(ropts_path) if ropts_path.is_file() else None
    params_dict = extract_run_parameters(data, run_options=run_options)
    return badges, repro_dict, cmp_dict, params_dict, data
