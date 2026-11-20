#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared context builder and link formatters for Predictive Control REPORT.md."""

from __future__ import annotations

from typing import Any

def build_report_context(
    bundles: list[dict[str, Any]],
    wf_study: dict[str, Any],
    eof_bundles: list[dict[str, Any]],
    eof_study: dict[str, Any],
) -> dict[str, Any]:
    """Compute summary handles and percentages shared across report sections."""
    bmap = {b["spec"]["key"]: b for b in bundles}
    emap = {b["spec"]["key"]: b for b in eof_bundles}
    s_int = bmap["integrator"]["summary"]
    s_ar8 = bmap["ar8"]["summary"]
    s_ar16 = bmap["ar16"]["summary"]
    s_ar32 = bmap["ar32"]["summary"]
    s_ab32 = bmap["ar32_n4096"]["summary"]
    s_ar64 = bmap["ar64"]["summary"]
    s_ab64 = bmap["ar64_n4096"]["summary"]
    s_ar16_d14 = emap["ar16_w14s"]["summary"]
    s_ar16_m14 = emap["ar16_matched_w14s"]["summary"]
    s_eof64 = emap["eof64_p8"]["summary"]
    s_eof128 = emap["eof128_p8"]["summary"]

    repro = bmap["ar16"]["metrics"].get("reproducibility", {})
    repos = repro.get("repositories", [])

    def fmt_link(b: dict[str, Any]) -> str:
        slug = b["spec"]["slug"]
        lbl = b["spec"]["label"]
        return f"[{lbl}](../{slug}/index.html)"

    def fmt_cmp_link(b: dict[str, Any]) -> str:
        slug = b["spec"]["slug"]
        return (
            f"[Config](../{slug}/config.html) · "
            f"[Optical](../{slug}/optical.html) · "
            f"[Runtime](../{slug}/runtime.html) · "
            f"[Run](../{slug}/how_to_run.html)"
        )

    def pf_cpu_sum(s: dict[str, Any]) -> float:
        pr = s["procs"]
        is_eof = s.get("pf_mode") == "eof"
        names = (
            ("mkEOFPF-1", "mkEOFPF-2", "applyEOFPF-1", "applyEOFPF-2")
            if is_eof
            else ("mkARPF-1", "mkARPF-2", "applyARPF-1", "applyARPF-2")
        )
        return sum(pr.get(nm, {}).get("cl_cpu_pct", 0.0) for nm in names)

    cpu_ar16 = pf_cpu_sum(s_ar16)
    cpu_ab32 = pf_cpu_sum(s_ab32)
    cpu_ar64 = pf_cpu_sum(s_ar64)
    cpu_ab64 = pf_cpu_sum(s_ab64)
    cpu_ar16_m14 = pf_cpu_sum(s_ar16_m14)
    cpu_eof64 = pf_cpu_sum(s_eof64)
    cpu_eof128 = pf_cpu_sum(s_eof128)

    b1_eof = eof_study["blocks"]["stage1"]
    b2_eof = eof_study["blocks"]["stage2"]
    s1_vr_gain = s_eof128["vis_stg1_sr_pct"] - s_ar16_m14["vis_stg1_sr_pct"]
    s1_wfe_drop = s_ar16_m14["stg1_wfe_nm"] - s_eof128["stg1_wfe_nm"]
    s1_var_drop = (
        1.0 - (s_eof128["stg1_wfe_nm"] / s_ar16_m14["stg1_wfe_nm"]) ** 2
    ) * 100.0
    c15_gain = (1.0 - s_eof128["coro_raw_c15"] / s_ar16_m14["coro_raw_c15"]) * 100.0
    c20_gain = (1.0 - s_eof128["coro_raw_c20"] / s_ar16_m14["coro_raw_c20"]) * 100.0
    c20_5s_gain = (1.0 - s_eof128["coro_5s_20"] / s_ar16_m14["coro_5s_20"]) * 100.0
    dm3_drop = (1.0 - s_eof128["llowfs_dm3_nm"] / s_ar16_m14["llowfs_dm3_nm"]) * 100.0
    return {
        "bundles": bundles,
        "wf_study": wf_study,
        "eof_bundles": eof_bundles,
        "eof_study": eof_study,
        "bmap": bmap,
        "emap": emap,
        "s_int": s_int,
        "s_ar8": s_ar8,
        "s_ar16": s_ar16,
        "s_ar32": s_ar32,
        "s_ab32": s_ab32,
        "s_ar64": s_ar64,
        "s_ab64": s_ab64,
        "s_ar16_d14": s_ar16_d14,
        "s_ar16_m14": s_ar16_m14,
        "s_eof64": s_eof64,
        "s_eof128": s_eof128,
        "repro": repro,
        "repos": repos,
        "fmt_link": fmt_link,
        "fmt_cmp_link": fmt_cmp_link,
        "pf_cpu_sum": pf_cpu_sum,
        "cpu_ar16": cpu_ar16,
        "cpu_ab32": cpu_ab32,
        "cpu_ar64": cpu_ar64,
        "cpu_ab64": cpu_ab64,
        "cpu_ar16_m14": cpu_ar16_m14,
        "cpu_eof64": cpu_eof64,
        "cpu_eof128": cpu_eof128,
        "b1_eof": b1_eof,
        "b2_eof": b2_eof,
        "s1_vr_gain": s1_vr_gain,
        "s1_wfe_drop": s1_wfe_drop,
        "s1_var_drop": s1_var_drop,
        "c15_gain": c15_gain,
        "c20_gain": c20_gain,
        "c20_5s_gain": c20_5s_gain,
        "dm3_drop": dm3_drop
    }
