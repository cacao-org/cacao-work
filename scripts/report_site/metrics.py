#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Pure-stdlib metrics, .bench, telemetry, and compute-unit extractors."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re

from . import COMPUTE_CATEGORIES, COMPUTE_CATEGORY_ORDER

TRACKED_PARAMS: list[tuple[str, str]] = [
    ("control_law", "Control Law"),
    ("llowfs", "LLOWFS"),
    ("calib_2wfs1dm", "2-WFS/1-DM Calib"),
    ("seeing", "Seeing"),
    ("star_mag", "Star Mag"),
    ("phys_time", "Phys Time"),
    ("oversample", "Oversample"),
    ("bench_mode", "Bench"),
    ("gain1", "Gain1"),
    ("gain2", "Gain2"),
    ("gain3", "Gain3"),
    ("mult1", "Mult1"),
    ("mult2", "Mult2"),
    ("mult3", "Mult3"),
    ("mgain_alpha", "mgain α"),
    ("mgain_floor", "mgain floor"),
    ("mgain_tt", "mgain TT"),
    ("svdlim1", "SVDlim1"),
    ("svdlim2", "SVDlim2"),
    ("svdlim3", "SVDlim3"),
    ("pf_mix", "PF Mix"),
    ("pf_reg", "PF Reg"),
    ("pf_mgain_exp", "PF mgain exp"),
    ("pf_ntrain", "PF N_train"),
    ("telemetry", "Telemetry"),
]

REL_SIBLING_RE = re.compile(r"\(\.\./([A-Za-z0-9_.-]+)/(?:[A-Za-z0-9_.-]+\.html)?\)")


def human_bytes(nbytes: int) -> str:
    """Format byte count using binary IEC-style readable units."""
    val = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if val < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(val)} B"
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{nbytes} B"


def _parse_cmd_flag(cmd: str, flag: str) -> str | None:
    """Extract the value following a CLI --flag token in a saved run_command string."""
    if not cmd:
        return None
    m = re.search(rf"(?:^|\s){re.escape(flag)}\s+(\S+)", cmd)
    return m.group(1) if m else None


def load_json_safe(path: Path) -> dict[str, object]:
    """Read a JSON object safely, returning {} on error or non-dict payload."""
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def find_metrics_path(out_slug_dir: Path) -> Path | None:
    """Find ao3k_scexao_metrics.json or any *_metrics.json file in out_slug_dir."""
    cands = [out_slug_dir / "ao3k_scexao_metrics.json"]
    cands.extend(sorted(out_slug_dir.glob("*_metrics.json")))
    return next((p for p in cands if p.is_file()), None)


def extract_run_parameters(data: dict[str, object]) -> dict[str, str]:
    """Extract normalized simulation parameters from a metrics JSON dictionary."""
    params: dict[str, str] = {}
    sa = data.get("star_and_atmosphere")
    repro = data.get("reproducibility")
    cmd = str(repro.get("run_command", "")) if isinstance(repro, dict) else ""
    loops = data.get("loops") if isinstance(data.get("loops"), dict) else {}
    l1 = loops.get("stage1_ao3k") if isinstance(loops.get("stage1_ao3k"), dict) else {}
    l2 = loops.get("stage2_scexao") if isinstance(loops.get("stage2_scexao"), dict) else {}
    l3 = loops.get("stage3_llowfs") if isinstance(loops.get("stage3_llowfs"), dict) else {}
    cm = data.get("coronagraph_metrics")
    lo = cm.get("llowfs") if isinstance(cm, dict) and isinstance(cm.get("llowfs"), dict) else None
    pc = data.get("predictive_control")
    pc_on = bool(isinstance(pc, dict) and pc.get("enabled"))
    c2d = data.get("calib_2wfs1dm")
    c2d_on = bool(isinstance(c2d, dict) and c2d.get("enabled"))

    has_ao_cfg = bool(
        loops or lo is not None or isinstance(pc, dict) or isinstance(c2d, dict)
    )
    if has_ao_cfg:
        if pc_on and isinstance(pc, dict):
            pf_mode = str(pc.get("pf_mode", "ar")).lower()
            pf_blk = int(pc.get("pf_blocksize", 128))
            pf_ord = int(pc.get("pf_order", 8))
            if pf_mode == "eof":
                params["control_law"] = f"PSOL Block-EOF(B={pf_blk}, P={pf_ord})"
            else:
                params["control_law"] = f"PSOL AR({pf_ord}) Predictive"
            if "pf_mix" in pc:
                params["pf_mix"] = f'{float(pc["pf_mix"]):.2f}'
            if "pf_reg" in pc:
                params["pf_reg"] = f'{float(pc["pf_reg"]):g}'
            if "pf_mgain_exp" in pc:
                params["pf_mgain_exp"] = f'{float(pc["pf_mgain_exp"]):.2f}'
            s1_pc = pc.get("stage1")
            if isinstance(s1_pc, dict) and s1_pc.get("n_samples"):
                params["pf_ntrain"] = str(int(s1_pc["n_samples"]))
        else:
            params["control_law"] = "Modal Integrator"

    lo_closed: bool | None = None
    if lo is not None:
        lo_closed = bool(lo.get("enabled_closed_loop", True))
        params["llowfs"] = "CLOSED" if lo_closed else "OPEN"

    if has_ao_cfg:
        if c2d_on and isinstance(c2d, dict):
            db = int(c2d.get("dim_b", 40))
            wo = int(c2d.get("whiten_order", 4))
            params["calib_2wfs1dm"] = f"ON ({db}m, AR({wo}))"
        else:
            params["calib_2wfs1dm"] = "OFF"

    if isinstance(sa, dict):
        if "seeing_arcsec_500nm" in sa and sa["seeing_arcsec_500nm"] is not None:
            params["seeing"] = f'{float(sa["seeing_arcsec_500nm"]):.2f}"'
        if "star_mV" in sa and "star_mH" in sa:
            params["star_mag"] = (
                f'mV={float(sa["star_mV"]):.1f}/mH={float(sa["star_mH"]):.1f}'
            )
        if "physical_time_s" in sa and sa["physical_time_s"] is not None:
            params["phys_time"] = f'{float(sa["physical_time_s"]):.1f} s'
        if "oversample" in sa and sa["oversample"] is not None:
            params["oversample"] = f'{int(sa["oversample"])}x'
    if "oversample" not in params:
        ov_f = _parse_cmd_flag(cmd, "--oversample")
        if ov_f:
            params["oversample"] = f"{ov_f}x"

    bmode = _parse_cmd_flag(cmd, "--bench-mode")
    if bmode:
        params["bench_mode"] = bmode

    if isinstance(l1, dict):
        for k_src, k_dst, fmt in (
            ("gain", "gain1", "{:.2f}"),
            ("mult", "mult1", "{:.2f}"),
            ("mgain_alpha", "mgain_alpha", "{:.2f}"),
            ("mgain_floor", "mgain_floor", "{:.2f}"),
            ("mgain_tt_factor", "mgain_tt", "{:.2f}"),
            ("svdlim", "svdlim1", "{:g}"),
        ):
            if k_src in l1 and l1[k_src] is not None:
                params[k_dst] = fmt.format(float(l1[k_src]))
    if isinstance(l2, dict):
        for k_src, k_dst, fmt in (
            ("gain", "gain2", "{:.2f}"),
            ("mult", "mult2", "{:.2f}"),
            ("svdlim", "svdlim2", "{:g}"),
        ):
            if k_src in l2 and l2[k_src] is not None:
                params[k_dst] = fmt.format(float(l2[k_src]))
    if isinstance(l3, dict) and lo_closed is not False:
        for k_src, k_dst, fmt in (
            ("gain", "gain3", "{:.2f}"),
            ("mult", "mult3", "{:.3f}"),
            ("svdlim", "svdlim3", "{:g}"),
        ):
            if k_src in l3 and l3[k_src] is not None:
                params[k_dst] = fmt.format(float(l3[k_src]))

    tlm_mode = None
    if isinstance(repro, dict) and repro.get("telemetry_mode"):
        tlm_mode = str(repro["telemetry_mode"])
    else:
        tlm_mode = _parse_cmd_flag(cmd, "--save-telemetry")
    if tlm_mode:
        params["telemetry"] = tlm_mode

    return params


def resolve_run_parameters(meta: dict[str, object]) -> dict[str, str]:
    """Return normalized parameter dict for a staged report meta (with legacy fallback)."""
    raw_p = meta.get("parameters")
    if isinstance(raw_p, dict) and raw_p:
        return {str(k): str(v) for k, v in raw_p.items() if v is not None}

    params: dict[str, str] = {}
    cmp_d = meta.get("comparison")
    if isinstance(cmp_d, dict):
        pc_on = bool(cmp_d.get("predictive_enabled", False))
        p_ord = int(cmp_d.get("pf_order", 8)) if pc_on else 0
        params["control_law"] = (
            f"PSOL AR({p_ord}) Predictive" if pc_on else "Modal Integrator"
        )
        if cmp_d.get("has_coro", "llowfs_closed" in cmp_d):
            params["llowfs"] = "CLOSED" if cmp_d.get("llowfs_closed", True) else "OPEN"
        c2d_on = bool(cmp_d.get("calib_2wfs1dm_enabled", False))
        if c2d_on:
            db = int(cmp_d.get("calib_2wfs1dm_dim_b", 40))
            wo = int(cmp_d.get("calib_2wfs1dm_whiten_order", 4))
            params["calib_2wfs1dm"] = f"ON ({db}m, AR({wo}))"
        else:
            params["calib_2wfs1dm"] = "OFF"
    repro = meta.get("reproducibility")
    cmd = str(repro.get("run_command", "")) if isinstance(repro, dict) else ""
    flag_map = (
        ("seeing", "--seeing", lambda s: f'{float(s):.2f}"'),
        ("phys_time", "--phys-time", lambda s: f"{float(s):.1f} s"),
        ("oversample", "--oversample", lambda s: f"{int(s)}x"),
        ("bench_mode", "--bench-mode", str),
        ("gain1", "--gain1", lambda s: f"{float(s):.2f}"),
        ("gain2", "--gain2", lambda s: f"{float(s):.2f}"),
        ("mult1", "--mult1", lambda s: f"{float(s):.2f}"),
        ("mult2", "--mult2", lambda s: f"{float(s):.2f}"),
        ("mgain_alpha", "--mgain-alpha", lambda s: f"{float(s):.2f}"),
        ("mgain_floor", "--mgain-floor", lambda s: f"{float(s):.2f}"),
        ("mgain_tt", "--mgain-tt", lambda s: f"{float(s):.2f}"),
        ("svdlim1", "--svdlim1", lambda s: f"{float(s):g}"),
        ("svdlim2", "--svdlim2", lambda s: f"{float(s):g}"),
        ("telemetry", "--save-telemetry", str),
    )
    for key, flag, fmt in flag_map:
        val = _parse_cmd_flag(cmd, flag)
        if val is not None:
            try:
                params[key] = fmt(val)
            except ValueError:
                params[key] = val
    return params


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
    if isinstance(c2d, dict) and c2d_on:
        if c2d.get("has_selfrm", True):
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
    params_dict = extract_run_parameters(data)
    return badges, repro_dict, cmp_dict, params_dict, data


def is_tech_report_meta(meta: dict[str, object]) -> bool:
    """Return True for tech reports (supporting legacy 'study' report_type)."""
    return str(meta.get("report_type", "")) in ("study", "tech_report")


def meta_sort_key(meta: dict[str, object]) -> tuple[int, int, str]:
    """Deterministic ordering for tech reports and simulation runs."""
    if is_tech_report_meta(meta):
        return (-1, 0, str(meta.get("slug", "")))
    cmp_d = meta.get("comparison")
    slug = str(meta.get("slug", ""))
    if isinstance(cmp_d, dict):
        has_coro = bool(cmp_d.get("has_coro", "llowfs_closed" in cmp_d))
        lo_on = bool(cmp_d.get("llowfs_closed", True)) if has_coro else True
        pc_on = bool(cmp_d.get("predictive_enabled", False))
        c2d_on = bool(cmp_d.get("calib_2wfs1dm_enabled", False))
        p_ord = int(cmp_d.get("pf_order", 0) or 0)
        p_mode = str(cmp_d.get("pf_mode", "ar")).lower()
        p_blk = int(cmp_d.get("pf_blocksize", 1) or 1)
        if not lo_on:
            tier = 0
        elif not pc_on and not c2d_on:
            tier = 1
        elif pc_on and not c2d_on:
            tier = 2
            if p_mode == "eof":
                return (tier, 200 + p_blk, slug)
            if "w14s" in slug:
                return (tier, 100 + p_ord, slug)
        else:
            tier = 3
        return (tier, p_ord, slug)
    return (4, 0, slug)


def parse_bench_file(bench_path: Path | None) -> list[dict[str, object]]:
    """Parse a cacaosim .bench INI file into structured component dictionaries."""
    if bench_path is None or not bench_path.is_file():
        return []
    sections: list[dict[str, object]] = []
    cur: dict[str, object] | None = None
    in_keys = {"in", "in_wf", "in_pup", "in_cmd", "in_wfe"}
    out_keys = {
        "out",
        "out_beam",
        "out_cam",
        "out_long",
        "out_opd",
        "out_refl",
        "out_trans",
        "out_lowfs",
        "out_pre_lyot",
        "out_pre_lyot_long",
    }
    for raw_line in bench_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            hdr = line[1:-1].strip()
            cat, _, comp_id = hdr.partition(".")
            cur = {
                "header": hdr,
                "category": cat.strip(),
                "id": comp_id.strip() or cat.strip(),
                "params": {},
                "in_streams": [],
                "out_streams": [],
            }
            sections.append(cur)
            continue
        if cur is not None and "=" in line:
            k, _, v = line.partition("=")
            key = k.strip()
            val = v.strip()
            if val.startswith('"') and val.endswith('"') and len(val) >= 2:
                val = val[1:-1]
            params = cur["params"]
            assert isinstance(params, dict)
            params[key] = val
            if key in in_keys and val:
                ins = cur["in_streams"]
                assert isinstance(ins, list)
                ins.append(val)
            elif key in out_keys and val:
                outs = cur["out_streams"]
                assert isinstance(outs, list)
                outs.append(val)
    return sections


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


def classify_unit_category(name: str) -> str:
    """Classify a compute/FPS unit or process into one of the 4 canonical categories."""
    low = name.lower()
    if any(
        k in low for k in ("htsim", "atmturb", "cacaosim")
    ) or low.startswith(("csim_", "milk-fpsexec-at", "milk-fpsexec-ca")):
        return "simulation"
    if (
        low.startswith(("tlog", "milk-fpsexec-me"))
        or any(k in low for k in ("mctrlstats", "streamfitslog", "report", "perf"))
    ):
        return "analysis"
    if any(
        k in low
        for k in (
            "mlat",
            "measlinresp",
            "compstrcm",
            "mkarpf",
            "mkeofpf",
            "calib",
            "selfrm",
            "testol",
        )
    ):
        return "calibration"
    if any(
        k in low
        for k in (
            "dmch2disp",
            "acquwfs",
            "acquirewfs",
            "wfs2cmodeval",
            "mfilt",
            "mvalc2dm",
            "zpo",
            "applyarpf",
            "applyeofpf",
            "dmcomb",
        )
    ) or low.startswith(("cacao-fpsexec-d", "cacao-fpsexec-m", "milk-fpsexec-li")):
        return "loop_operation"
    if low.startswith("cacao-fpsexec-c"):
        return "calibration"
    return "loop_operation"


def classify_phase_category(phase_id: str) -> str:
    """Classify a run phase ID into one of the 4 canonical categories."""
    low = phase_id.lower()
    if any(k in low for k in ("bench", "dl_reference", "atmturb", "sim")):
        return "simulation"
    if any(k in low for k in ("calib", "selfrm", "testol", "pf_warmup", "mlat")):
        return "calibration"
    if any(k in low for k in ("save_psf", "tlm", "analysis", "report", "plot")):
        return "analysis"
    if any(k in low for k in ("deploy_loops", "closed_loop", "loop")):
        return "loop_operation"
    return "loop_operation"


def classify_shm_category(stream_name: str) -> str:
    """Classify a shared-memory stream into one of the 4 canonical categories."""
    low = stream_name.lower()
    if any(k in low for k in ("_logbuff", "rms", "stat", "tlog", "cntfrac")):
        return "analysis"
    if low.startswith(("csim_", "psf_", "coro_")) or low == "outarraypha":
        return "simulation"
    if any(
        k in low
        for k in (
            "cmmodes",
            "rmsyn",
            "dmrm",
            "selfrm",
            "resp",
            "pfmat",
            "fmodes",
            "blkmask",
            "dmmask",
            "wfsmask",
            "eigenval",
            "eigenvec",
            "cpa_tmp",
            "calib",
        )
    ) or low in ("syn0", "zerc"):
        return "calibration"
    return "loop_operation"


def _classify_process(name: str) -> str:
    low = name.lower()
    if "htsim" in low or low.startswith("csim_"):
        return "Atmosphere" if "atmturb" in low else "Optical Bench"
    if "arpf" in low or "eofpf" in low:
        return "Predictive Control"
    if low.startswith("zpo"):
        return "ZPO"
    if low.startswith("tlog"):
        return "Telemetry"
    if any(k in low for k in ("dmch2disp", "acquwfs", "wfs2cmodeval", "mfilt", "mvalc2dm")):
        return "AO Control"
    if any(k in low for k in ("mlat", "measlinresp", "compstrcm", "mctrlstats")):
        return "Calib & Stats"
    return "Orchestration"


def extract_runtime_explorer_data(out_slug_dir: Path) -> dict[str, object]:
    """Extract structured runtime, phase, process, and SHM telemetry for runtime.html."""
    perf = load_json_safe(out_slug_dir / "compute_perf_metrics.json")
    tlm = load_json_safe(out_slug_dir / "compute_telemetry.json")
    out: dict[str, object] = {}

    if perf:
        for k in ("host", "gpu", "run", "calib_stage1", "calib_stage2", "summary"):
            if k in perf and perf[k] is not None:
                out[k] = perf[k]
        raw_phases = perf.get("phases")
        if isinstance(raw_phases, list):
            phases_clean: list[dict[str, object]] = []
            for ph in raw_phases:
                if not isinstance(ph, dict):
                    continue
                ph_copy = dict(ph)
                pcat = classify_phase_category(str(ph_copy.get("id", "")))
                ph_copy["category"] = pcat
                ph_copy["category_label"] = COMPUTE_CATEGORIES[pcat]["label"]
                phases_clean.append(ph_copy)
            out["phases"] = phases_clean

    raw_procs = tlm.get("processes") if isinstance(tlm.get("processes"), list) else []
    by_name: dict[str, dict[str, object]] = {}
    for p in raw_procs:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        pname = str(p["name"])
        score = (
            float(p.get("cl_cpu_s", 0.0) or 0.0),
            float(p.get("loopcnt", 0.0) or 0.0),
            float(p.get("cpu_total_s", 0.0) or 0.0),
        )
        prev = by_name.get(pname)
        prev_score = (
            float(prev.get("cl_cpu_s", 0.0) or 0.0),
            float(prev.get("loopcnt", 0.0) or 0.0),
            float(prev.get("cpu_total_s", 0.0) or 0.0),
        ) if prev else (-1.0, -1.0, -1.0)
        if score > prev_score:
            by_name[pname] = p

    procs_clean: list[dict[str, object]] = []
    for pname, p in sorted(
        by_name.items(),
        key=lambda kv: (
            -float(kv[1].get("cl_cpu_pct", 0.0) or 0.0),
            -float(kv[1].get("cpu_total_s", 0.0) or 0.0),
            kv[0],
        ),
    ):
        vram = float(p.get("gpu_vram_peak_mib", 0.0) or 0.0)
        rss_mb = float(p.get("vmrss_peak_kb", 0.0) or 0.0) / 1024.0
        pcat = classify_unit_category(pname)
        procs_clean.append(
            {
                "name": pname,
                "category": pcat,
                "category_label": COMPUTE_CATEGORIES[pcat]["label"],
                "subsystem": _classify_process(pname),
                "backend": f"CUDA ({vram:.0f} MiB)" if vram > 0 else "CPU",
                "vram_mib": round(vram, 1),
                "cl_cpu_pct": round(float(p.get("cl_cpu_pct", 0.0) or 0.0), 2),
                "cpu_total_s": round(float(p.get("cpu_total_s", 0.0) or 0.0), 2),
                "threads": int(p.get("threads_max", 1) or 1),
                "rss_mb": round(rss_mb, 1),
                "exec_p50_us": round(float(p.get("exec_p50_us", 0.0) or 0.0), 1),
                "exec_p99_us": round(float(p.get("exec_p99_us", 0.0) or 0.0), 1),
                "jitter_us": round(float(p.get("jitter_us", 0.0) or 0.0), 1),
                "loopcnt": int(p.get("loopcnt", 0) or 0),
                "timeouts": int(p.get("timeouts", 0) or 0),
            }
        )
    if procs_clean:
        out["processes"] = procs_clean

    raw_streams = tlm.get("streams") if isinstance(tlm.get("streams"), list) else []
    streams_clean: list[dict[str, object]] = []
    for s in raw_streams:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        dims = s.get("dims") if isinstance(s.get("dims"), list) else []
        dim_s = "x".join(str(d) for d in dims if int(d) > 1 or len(dims) <= 2)
        if not dim_s and dims:
            dim_s = "x".join(str(d) for d in dims)
        sname = str(s["name"])
        scat = classify_shm_category(sname)
        streams_clean.append(
            {
                "name": sname,
                "category": scat,
                "category_label": COMPUTE_CATEGORIES[scat]["label"],
                "dtype": str(s.get("dtype", "F32")),
                "dims": dim_s,
                "frame_kb": round(float(s.get("frame_bytes", 0) or 0) / 1024.0, 2),
                "mean_hz": round(float(s.get("mean_hz", 0.0) or 0.0), 1),
                "mean_mb_s": round(float(s.get("mean_mb_s", 0.0) or 0.0), 2),
                "nb_readers": int(s.get("nb_readers", 0) or 0),
                "e2e_us": round(float(s.get("e2e_latency_us", -1.0) or -1.0), 1),
            }
        )
    streams_clean.sort(key=lambda r: (-float(r["mean_mb_s"]), str(r["name"])))
    if streams_clean:
        out["streams"] = streams_clean[:120]
    return out


def extract_runtime_summary(runtime_data: dict[str, object]) -> dict[str, object]:
    """Build compact runtime summary fields for report_meta.json and KPI cards."""
    summary: dict[str, object] = {}
    run_d = runtime_data.get("run") if isinstance(runtime_data.get("run"), dict) else {}
    phases = runtime_data.get("phases") if isinstance(runtime_data.get("phases"), list) else []
    cl_phase = next(
        (p for p in phases if isinstance(p, dict) and p.get("id") == "closed_loop_10s"),
        None,
    )
    if run_d.get("wall_duration_s") is not None:
        summary["wall_duration_s"] = round(float(run_d["wall_duration_s"]), 2)
    if cl_phase:
        summary["cl_duration_s"] = round(float(cl_phase.get("duration_s", 0.0)), 2)
        summary["sim_cores_mean"] = round(float(cl_phase.get("sim_cores_mean", 0.0)), 2)
        summary["gpu_sm_pct"] = round(float(cl_phase.get("gpu_util_mean_pct", 0.0)), 1)
        summary["vram_gib"] = round(float(cl_phase.get("gpu_vram_peak_mib", 0.0)) / 1024.0, 2)
        summary["shm_bw_mb_s"] = round(float(cl_phase.get("shm_bw_mean_mb_s", 0.0)), 1)
    return summary


def build_compute_unit_catalog(
    metrics_data: dict[str, object],
    bench_sections: list[dict[str, object]],
    runtime_data: dict[str, object],
    params: dict[str, str],
) -> list[dict[str, object]]:
    """Build configuration-specific CACAO + cacaosim compute-unit inventory."""
    proc_map = {
        str(p["name"]): p
        for p in (runtime_data.get("processes") or [])
        if isinstance(p, dict) and p.get("name")
    }
    loops = metrics_data.get("loops") if isinstance(metrics_data.get("loops"), dict) else {}
    l1 = loops.get("stage1_ao3k") if isinstance(loops.get("stage1_ao3k"), dict) else {}
    l2 = loops.get("stage2_scexao") if isinstance(loops.get("stage2_scexao"), dict) else {}
    l3 = loops.get("stage3_llowfs") if isinstance(loops.get("stage3_llowfs"), dict) else {}
    cm = metrics_data.get("coronagraph_metrics")
    lo = cm.get("llowfs") if isinstance(cm, dict) and isinstance(cm.get("llowfs"), dict) else {}
    lo_on = bool(lo.get("enabled_closed_loop", params.get("llowfs", "CLOSED") != "OPEN"))
    pc = metrics_data.get("predictive_control")
    pc_on = bool(isinstance(pc, dict) and pc.get("enabled"))
    pf_mode = str(pc.get("pf_mode", "ar")).lower() if isinstance(pc, dict) else "ar"
    pf_ord = int(pc.get("pf_order", 8)) if isinstance(pc, dict) else 8
    pf_blk = int(pc.get("pf_blocksize", 128)) if isinstance(pc, dict) else 128
    pf_mix = float(pc.get("pf_mix", 0.90)) if isinstance(pc, dict) else 0.90
    pf_reg = float(pc.get("pf_reg", 0.005)) if isinstance(pc, dict) else 0.005
    c2d = metrics_data.get("calib_2wfs1dm")
    c2d_on = bool(isinstance(c2d, dict) and c2d.get("enabled"))
    bench_mode = params.get("bench_mode", "fused")

    units: list[dict[str, object]] = []

    def add_unit(
        unit: str,
        binary: str,
        category: str,
        stage: str,
        rate: str,
        inputs: str,
        outputs: str,
        role: str,
        fps_params: dict[str, str],
        always_active: bool = True,
    ) -> None:
        pm = proc_map.get(unit, {})
        cat_info = COMPUTE_CATEGORIES[category]
        units.append(
            {
                "unit": unit,
                "binary": binary,
                "category": category,
                "category_label": cat_info["label"],
                "stage": stage,
                "rate": rate,
                "inputs": inputs,
                "outputs": outputs,
                "role": role,
                "fps_params": fps_params,
                "active": always_active,
                "backend": pm.get("backend", "CUDA/CPU"),
                "cl_cpu_pct": pm.get("cl_cpu_pct"),
                "exec_p50_us": pm.get("exec_p50_us"),
                "exec_p99_us": pm.get("exec_p99_us"),
            }
        )

    sa = metrics_data.get("star_and_atmosphere")
    seeing = float(sa.get("seeing_arcsec_500nm", 0.60)) if isinstance(sa, dict) else 0.60
    ov = int(sa.get("oversample", 4)) if isinstance(sa, dict) else 4
    add_unit(
        "csim_atmturb",
        "milk-fpsexec-atmturb-mkwfs",
        "simulation",
        "Optical Sim",
        "2000 Hz",
        "Maunakea 7-layer config",
        "outarraypha (256x256)",
        "Frozen-flow + boiling multi-layer atmospheric OPD generator",
        {"seeing": f"{seeing:.2f}", "time_step": "0.0005", "triggermode": "4"},
    )
    if bench_mode == "modular":
        for sec in bench_sections:
            hdr = str(sec.get("header", ""))
            if hdr == "bench":
                continue
            uid = f"csim_{sec.get('id', hdr.replace('.', '_'))}"
            ins = ", ".join(sec.get("in_streams") or [])  # type: ignore[arg-type]
            outs = ", ".join(sec.get("out_streams") or [])  # type: ignore[arg-type]
            sec_params = sec.get("params") or {}
            add_unit(
                uid,
                f"milk-fpsexec-cacaosim-{sec.get('category', 'bench')}",
                "simulation",
                "Optical Sim",
                "2000 Hz",
                ins or "upstream beam",
                outs or "downstream beam",
                f"Modular optical component [{hdr}]",
                {k: str(v) for k, v in sec_params.items()},  # type: ignore[union-attr]
            )
    else:
        add_unit(
            "csim_htsim",
            "milk-fpsexec-cacaosim-htsim",
            "simulation",
            "Optical Sim",
            f"{2000 * ov} Hz ({ov}x)",
            "outarraypha, dm01disp, dm02disp",
            "csim_wfs_nir, csim_wfs_vis, csim_wfs_lowfs, psf_*",
            "GPU-fused polychromatic DAG optical bench + Lyot coronagraph + wfstat",
            {
                "oversample": str(ov),
                "wfstat_enable": "ON",
                "triggermode": "3 (outarraypha)",
            },
        )

    stage_specs = [
        ("1", "Stage 1 (AO3k)", "01", "64x64", "160x160", "1000 Hz", "csim_wfs_nir", l1, True),
        ("2", "Stage 2 (SCExAO)", "02", "50x50", "120x120", "2000 Hz", "csim_wfs_vis", l2, True),
        (
            "3",
            "Stage 3 (LLOWFS)",
            "02",
            "50x50",
            "64x64",
            "500 Hz",
            "csim_wfs_lowfs",
            l3,
            lo_on,
        ),
    ]
    for idx, slbl, dm, dmsz, wfssz, rate, wfs_in, ld, is_act in stage_specs:
        g_val = ld.get("gain", params.get(f"gain{idx}", "0.35"))
        m_val = ld.get("mult", params.get(f"mult{idx}", "0.98"))
        svd_val = ld.get("svdlim", params.get(f"svdlim{idx}", "0.004"))
        n_cm = ld.get("n_cm_modes", "14" if idx == "3" else "1255")
        if idx in ("1", "2"):
            add_unit(
                f"DMch2disp-{dm}",
                "cacao-fpsexec-dmcomb",
                "loop_operation",
                slbl,
                rate,
                f"dm{dm}disp00..11 ({dmsz})",
                f"dm{dm}disp, aol{idx}_dmzpo",
                "12-channel DM summer + ZPO accumulator",
                {
                    "DMxsize": dmsz.split("x")[0],
                    "NBchannel": "12",
                    "zpoffset": "ON" if idx == "2" else "OFF",
                },
            )
        add_unit(
            f"acquWFS-{idx}",
            "cacao-fpsexec-cacaoiot-acquireWFS",
            "loop_operation",
            slbl,
            rate,
            f"{wfs_in} ({wfssz}), aol{idx}_wfsref",
            f"aol{idx}_imWFS2",
            "WFS normalization, dark/reference & ZPO subtraction",
            {"WFSnormalize": "ON", "WFSrefsub": "ON", "wfszpo": f"aol{idx}_wfszpo"},
        )
        add_unit(
            f"wfs2cmodeval-{idx}",
            "milk-fpsexec-linalg-MVMextract",
            "loop_operation",
            slbl,
            rate,
            f"aol{idx}_imWFS2, aol{idx}_CMmodesWFS",
            f"aol{idx}_modevalWFS ({n_cm})",
            "GPU/CPU MVM projection from WFS pixels to control modes",
            {"axmode": "0", "MODENORM": "ON", "GPUindex": "0"},
        )
        add_unit(
            f"mfilt-{idx}",
            "cacao-fpsexec-mfilt",
            "loop_operation",
            slbl,
            rate,
            f"aol{idx}_modevalWFS, aol{idx}_modevalPF",
            f"aol{idx}_modevalDM, aol{idx}_modevalOL",
            f"Modal leaky integrator + PSOL reconstruction ({'CLOSED' if is_act else 'OPEN'})",
            {
                "loopgain": str(g_val),
                "loopmult": str(m_val),
                "OLmodes": "ON",
                "PF.enable": "ON" if (pc_on and idx in ("1", "2")) else "OFF",
            },
            always_active=is_act,
        )
        dm_out_ch = f"dm{dm}disp04" if idx == "3" else f"dm{dm}disp03"
        add_unit(
            f"mvalC2dm-{idx}",
            "milk-fpsexec-linalg-MVMextract",
            "loop_operation",
            slbl,
            rate,
            f"aol{idx}_modevalDM, aol{idx}_CMmodesDM",
            f"aol{idx}_dmC -> {dm_out_ch}",
            "GPU/CPU MVM synthesis from modal commands to DM grid",
            {"axmode": "1", "MODENORM": "OFF", "GPUindex": "0"},
            always_active=is_act,
        )
        add_unit(
            f"mlat-{idx}",
            "cacao-fpsexec-cacaopt-mlat",
            "calibration",
            slbl,
            "Calib",
            f"aol{idx}_dmRM, aol{idx}_imWFS2",
            "mlat_hardwlatency.dat",
            f"Stage-{idx} hardware loop latency measurement via poke bursts",
            {"CPA": "1.0" if idx == "3" else "4.0", "NBiter": "30"},
        )
        add_unit(
            f"measlinresp-{idx}",
            "cacao-fpsexec-cacaoac-measlinresp",
            "calibration",
            slbl,
            "Calib",
            f"aol{idx}_dmRM, aol{idx}_imWFS2, HpokeC.fits",
            "HrespC.fits -> zrespC.fits",
            f"Stage-{idx} Hadamard linear response matrix acquisition",
            {"NBave": "2", "NBexcl": "2"},
        )
        add_unit(
            f"compstrCM-{idx}",
            "cacao-fpsexec-cacaocc-compstrcm",
            "calibration",
            slbl,
            "Calib",
            f"RMsyn_modesDM/WFS, svdlim={svd_val}",
            f"CMmodesDM/WFS ({n_cm} modes)",
            f"Stage-{idx} SVD pseudo-inverse control matrix solver",
            {"svdlim": str(svd_val)},
        )
        add_unit(
            f"mctrlstats-{idx}",
            "cacao-fpsexec-modalCTRLstats",
            "analysis",
            slbl,
            rate,
            f"aol{idx}_modevalWFS, aol{idx}_modevalDM",
            f"aol{idx}_mvalWFSrms, aol{idx}_mvalDMrms",
            f"Stage-{idx} real-time modal RMS telemetry & stats monitor",
            {"AOloopindex": idx},
        )
        if idx == "2":
            add_unit(
                "zpo-2",
                "milk-fpsexec-linalg-MVMextract",
                "loop_operation",
                "Stage 2 -> 3 ZPO",
                "2000 Hz",
                "aol2_dmzpo (dm02disp04), aol2_zrespM",
                "aol2_wfszpo -> acquWFS-2",
                "Real-time zero-point offset feeding Stage-3 DM2 stroke into Stage-2 WFS",
                {"axmode": "1", "triggersname": "aol2_dmzpo"},
            )
        if pc_on and idx in ("1", "2"):
            mk_u = f"{'mkEOFPF' if pf_mode == 'eof' else 'mkARPF'}-{idx}"
            ap_u = f"{'applyEOFPF' if pf_mode == 'eof' else 'applyARPF'}-{idx}"
            mk_bin = (
                "cacao-fpsexec-cacaopc-mkEOFPF"
                if pf_mode == "eof"
                else "cacao-fpsexec-cacaopc-mkARPF"
            )
            ap_bin = (
                "cacao-fpsexec-cacaopc-applyEOFPF"
                if pf_mode == "eof"
                else "cacao-fpsexec-cacaopc-applyARPF"
            )
            mat_s = f"aol{idx}_{'eofPFmat' if pf_mode == 'eof' else 'arPFmat'}"
            add_unit(
                mk_u,
                mk_bin,
                "calibration",
                slbl,
                "Async",
                f"aol{idx}_modevalOL_buff",
                mat_s,
                f"Online {'Block-EOF VAR' if pf_mode == 'eof' else 'Wiener AR'} filter solver",
                {
                    "PForder": str(pf_ord),
                    "reglambda": f"{pf_reg:g}",
                    **(
                        {"blocksize": str(pf_blk), "diagorder": "16"}
                        if pf_mode == "eof"
                        else {}
                    ),
                },
            )
            add_unit(
                ap_u,
                ap_bin,
                "loop_operation",
                slbl,
                rate,
                f"aol{idx}_modevalOL, {mat_s}",
                f"aol{idx}_modevalPF (mix={pf_mix:.2f})",
                "Real-time SIMD predictive inference synced with mfilt",
                {"PForder": str(pf_ord), "mixcoeff": f"{pf_mix:.2f}"},
            )

    if c2d_on:
        add_unit(
            "milk-mlt-calib2wfs1dm",
            "milk-mlt-calib2wfs1dm",
            "calibration",
            "Cross-Stage",
            "Post-loop",
            "aol1_modevalWFS, aol2_modevalWFS, aol2_modevalDM",
            "Mab, Mdb, Mda_virt",
            "2-WFS + inter-stage DM closed-loop system identification via AR whitening W(z)",
            {
                "sysid_modes": str(int(c2d.get("dim_b", 40) or 40)),
                "whiten_order": str(int(c2d.get("whiten_order", 4) or 4)),
            },
        )
    if params.get("telemetry", "none") != "none":
        add_unit(
            "tlog_00..26",
            "milk-fpsexec-mem-streamFITSlog",
            "analysis",
            "Telemetry",
            "Lockstep",
            "WFS, PSF, DM, modal SHM streams",
            "telemetry/*.fits + *.txt",
            f"Lossless paired FITS + timestamp telemetry logger ({params.get('telemetry')})",
            {"mode": str(params.get("telemetry", "standard"))},
        )
    cat_rank = {k: i for i, k in enumerate(COMPUTE_CATEGORY_ORDER)}
    units.sort(key=lambda u: cat_rank.get(str(u["category"]), 99))
    return units


def extract_referenced_simulations(
    md_text: str,
    study_meta: dict[str, object],
    known_sims: set[str] | None = None,
) -> list[str]:
    """Extract ordered simulation slugs referenced by a technical report."""
    refs: list[str] = []
    seen: set[str] = set()
    raw_list = study_meta.get("referenced_simulations")
    if isinstance(raw_list, list):
        for item in raw_list:
            slug = str(item).strip()
            if slug and slug not in seen:
                seen.add(slug)
                refs.append(slug)
    for m in REL_SIBLING_RE.finditer(md_text):
        cand = m.group(1).strip()
        if cand in seen:
            continue
        if known_sims is not None and cand not in known_sims:
            continue
        if "report" in cand and (known_sims is None or cand not in known_sims):
            continue
        seen.add(cand)
        refs.append(cand)
    return refs
