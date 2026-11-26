#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Compute-unit catalog builder and tech-report simulation cross-reference extractor."""

from __future__ import annotations

from ..constants import COMPUTE_CATEGORIES, COMPUTE_CATEGORY_ORDER
from .common import REL_SIBLING_RE


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
    atm_pm = proc_map.get("csim_atmturb", {})
    atm_tm = atm_pm.get("triggermode")
    atm_ts = str(atm_pm.get("trigstream", "") or "").strip()
    if atm_tm == 3 and atm_ts:
        atm_trig_lbl = f"3 ({atm_ts})"
    elif atm_tm is not None:
        atm_trig_lbl = str(atm_tm)
    else:
        atm_trig_lbl = "3 (csim_wfs_vis)" if bench_mode == "fused" else "4"
    add_unit(
        "csim_atmturb",
        "milk-fpsexec-atmturb-mkwfs",
        "simulation",
        "Optical Sim",
        "2000 Hz",
        "Maunakea 7-layer config",
        "outarraypha (256x256)",
        "Frozen-flow + boiling multi-layer atmospheric OPD generator",
        {"seeing": f"{seeing:.2f}", "time_step": "0.0005", "triggermode": atm_trig_lbl},
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
            {"oversample": str(ov), "wfstat_enable": "ON", "triggermode": "3 (outarraypha)"},
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
        wfs_mvm_pm = proc_map.get(f"wfs2cmodeval-{idx}", {})
        wfs_mvm_gpu = (
            "99 (CPU BLAS)"
            if (idx == "3" and float(wfs_mvm_pm.get("vram_mib", 0.0) or 0.0) <= 0.0)
            else ("-1 (CUDA Graph)" if idx in ("1", "2") else "0")
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
            {"axmode": "0", "MODENORM": "ON", "GPUindex": wfs_mvm_gpu},
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
        dm_mvm_pm = proc_map.get(f"mvalC2dm-{idx}", {})
        dm_mvm_gpu = (
            "99 (CPU BLAS)"
            if (idx == "3" and float(dm_mvm_pm.get("vram_mib", 0.0) or 0.0) <= 0.0)
            else ("-1 (CUDA Graph)" if idx in ("1", "2") else "0")
        )
        add_unit(
            f"mvalC2dm-{idx}",
            "milk-fpsexec-linalg-MVMextract",
            "loop_operation",
            slbl,
            rate,
            f"aol{idx}_modevalDM, aol{idx}_CMmodesDM",
            f"aol{idx}_dmC -> {dm_out_ch}",
            "GPU/CPU MVM synthesis from modal commands to DM grid",
            {"axmode": "1", "MODENORM": "OFF", "GPUindex": dm_mvm_gpu},
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


NON_SIM_STATIC_ROUTES: frozenset[str] = frozenset(
    {
        "algorithms",
        "assets",
        "predictive-control",
        "reference",
        "simulations",
        "stack",
        "topics",
        "turbulence",
    }
)


def extract_referenced_simulations(
    md_text: str,
    study_meta: dict[str, object],
    known_sims: set[str] | None = None,
    excluded_slugs: set[str] | None = None,
) -> list[str]:
    """Extract ordered simulation slugs referenced by a technical report."""
    refs: list[str] = []
    seen: set[str] = set()
    excluded = set(NON_SIM_STATIC_ROUTES)
    if excluded_slugs:
        excluded.update(excluded_slugs)
    raw_list = study_meta.get("referenced_simulations")
    if isinstance(raw_list, list):
        for item in raw_list:
            slug = str(item).strip()
            if slug and slug not in seen and slug not in excluded:
                seen.add(slug)
                refs.append(slug)
    for m in REL_SIBLING_RE.finditer(md_text):
        cand = m.group(1).strip()
        if cand in seen or cand in excluded:
            continue
        if known_sims is not None and cand not in known_sims:
            continue
        if "report" in cand and (known_sims is None or cand not in known_sims):
            continue
        seen.add(cand)
        refs.append(cand)
    return refs
