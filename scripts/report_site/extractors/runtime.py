#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Runtime phase, process, SHM stream classification and telemetry extractors."""

from __future__ import annotations

from pathlib import Path

from ..constants import COMPUTE_CATEGORIES
from .common import load_json_safe


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
