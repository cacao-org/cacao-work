#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Simulation run-parameter normalization and CLI fallback extraction."""

from __future__ import annotations

from .common import _parse_cmd_flag

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


def extract_run_parameters(
    data: dict[str, object],
    run_options: dict[str, object] | None = None,
) -> dict[str, str]:
    """Extract normalized simulation parameters from metrics JSON and optional run_options.json."""
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

    if isinstance(repro, dict) and repro.get("telemetry_mode"):
        tlm_mode = str(repro["telemetry_mode"])
    else:
        tlm_mode = _parse_cmd_flag(cmd, "--save-telemetry")
    if tlm_mode:
        params["telemetry"] = tlm_mode

    if isinstance(run_options, dict):
        raw_opts = (
            run_options.get("options")
            if isinstance(run_options.get("options"), dict)
            else run_options
        )
        if isinstance(raw_opts, dict):
            if "bench_mode" not in params and raw_opts.get("bench_mode"):
                params["bench_mode"] = str(raw_opts["bench_mode"])
            if "oversample" not in params and raw_opts.get("eff_oversample"):
                params["oversample"] = f'{int(raw_opts["eff_oversample"])}x'
            if "telemetry" not in params and raw_opts.get("save_telemetry"):
                params["telemetry"] = str(raw_opts["save_telemetry"])
            extra_fmt: tuple[tuple[str, str], ...] = (
                ("clock_skew_us", "{:g} us"),
                ("pf_mix2", "{:.2f}"),
                ("pf_reg2", "{:g}"),
                ("pf_maxnorm2", "{:g}"),
                ("pf_warmup_sec", "{:g} s"),
                ("pf_nbtrain1", "{}"),
                ("pf_nbtrain2", "{}"),
                ("pf_minsamples1", "{}"),
                ("pf_minsamples2", "{}"),
                ("nbloop", "{}"),
                ("selfrm_modes", "{}"),
                ("eff_psf_navg", "{}"),
                ("wall_rate", "{} Hz"),
                ("wfstat_validate", "{}"),
                ("fast_calib", "{}"),
            )
            for ek, fmt in extra_fmt:
                ev = raw_opts.get(ek)
                if ev is None or ev == "" or ek in params:
                    continue
                if ek in ("wfstat_validate", "fast_calib"):
                    params[ek] = "ON" if str(ev) not in ("0", "False", "false") else "OFF"
                else:
                    try:
                        params[ek] = fmt.format(ev)
                    except (ValueError, TypeError):
                        params[ek] = str(ev)

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
