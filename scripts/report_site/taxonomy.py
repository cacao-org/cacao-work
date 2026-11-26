#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Declarative AO research-domain taxonomy loading, classification, and tree builder."""

from __future__ import annotations

import json
from pathlib import Path

from .extractors.common import is_tech_report_meta, meta_sort_key

TAXONOMY_JSON_PATH = Path(__file__).resolve().parent / "taxonomy.json"


def load_taxonomy(path: Path | None = None) -> list[dict[str, object]]:
    """Load the ordered AO research-domain taxonomy definition from JSON."""
    src = path or TAXONOMY_JSON_PATH
    data = json.loads(src.read_text(encoding="utf-8"))
    domains = data.get("domains")
    if not isinstance(domains, list) or not domains:
        raise ValueError(f"Invalid taxonomy definition in {src}")
    return [dict(d) for d in domains if isinstance(d, dict) and d.get("id")]


def _default_subtopic(domain: dict[str, object]) -> str:
    subs = domain.get("subgroups")
    if isinstance(subs, list) and subs and isinstance(subs[0], dict):
        return str(subs[0].get("id", "general"))
    return "general"


def _subtopic_label_map(taxonomy: list[dict[str, object]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for dom in taxonomy:
        did = str(dom["id"])
        subs: dict[str, str] = {}
        for sg in dom.get("subgroups") or []:
            if isinstance(sg, dict) and sg.get("id"):
                subs[str(sg["id"])] = str(sg.get("label") or sg["id"])
        out[did] = subs
    return out


def classify_report(
    meta: dict[str, object],
    taxonomy: list[dict[str, object]],
) -> tuple[str, str]:
    """Return (primary_domain_id, subtopic_id) for a report metadata dictionary."""
    dom_by_id = {str(d["id"]): d for d in taxonomy}
    explicit_dom = str(meta.get("domain", "")).strip()
    if explicit_dom in dom_by_id:
        dom = dom_by_id[explicit_dom]
        valid_subs = {
            str(sg.get("id", ""))
            for sg in (dom.get("subgroups") or [])
            if isinstance(sg, dict)
        }
        explicit_sub = str(meta.get("subtopic", "")).strip()
        sub = explicit_sub if explicit_sub in valid_subs and explicit_sub else _default_subtopic(dom)
        return explicit_dom, sub

    if is_tech_report_meta(meta):
        slug_l = str(meta.get("slug", "")).lower()
        topic_l = str(meta.get("topic", "")).lower()
        title_l = str(meta.get("title", "")).lower()
        feats = meta.get("cacao_features")
        feats_l = " ".join(str(x).lower() for x in feats) if isinstance(feats, list) else ""
        sum_l = str(meta.get("summary", "")).lower()

        best_id = "bench-runtime" if "bench-runtime" in dom_by_id else str(taxonomy[0]["id"])
        best_score = 0
        for dom in taxonomy:
            did = str(dom["id"])
            kws = [str(k).lower() for k in (dom.get("keywords") or [])]
            score = 0
            for kw in kws:
                if kw in slug_l or kw in topic_l or kw in title_l:
                    score += 5
                if kw in feats_l:
                    score += 2
                if kw in sum_l:
                    score += 1
            if score > best_score:
                best_score = score
                best_id = did
        dom = dom_by_id[best_id]
        sub = _default_subtopic(dom)
        if best_id == "wavefront-control" and "eof" in slug_l and "ar" not in slug_l:
            sub = "block-eof"
        return best_id, sub

    cmp_d = meta.get("comparison") if isinstance(meta.get("comparison"), dict) else {}
    params = meta.get("parameters") if isinstance(meta.get("parameters"), dict) else {}
    ctrl_law = str(params.get("control_law", ""))
    c2d_param = str(params.get("calib_2wfs1dm", ""))

    if (bool(cmp_d.get("calib_2wfs1dm_enabled")) or c2d_param.startswith("ON")) and (
        "calibration-sysid" in dom_by_id
    ):
        return "calibration-sysid", "telemetry-sysid"

    if (bool(cmp_d.get("predictive_enabled")) or ctrl_law.startswith("PSOL ")) and (
        "wavefront-control" in dom_by_id
    ):
        pf_mode = str(cmp_d.get("pf_mode", "")).lower()
        sub = "block-eof" if (pf_mode == "eof" or "Block-EOF" in ctrl_law) else "diagonal-ar"
        return "wavefront-control", sub

    if (
        bool(cmp_d.get("has_coro")) or ("llowfs_closed" in cmp_d) or ("llowfs" in params)
    ) and ("coronagraphy-lowfs" in dom_by_id):
        return "coronagraphy-lowfs", "llowfs-control"

    fallback_id = "bench-runtime" if "bench-runtime" in dom_by_id else str(taxonomy[-1]["id"])
    return fallback_id, _default_subtopic(dom_by_id[fallback_id])


def build_site_hierarchy(
    metas: list[dict[str, object]],
    taxonomy: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Organize all staged reports into a single AO research-domain hierarchy."""
    tax = taxonomy or load_taxonomy()
    sorted_metas = sorted(metas, key=meta_sort_key)
    study_metas = [m for m in sorted_metas if is_tech_report_meta(m)]
    run_metas = [m for m in sorted_metas if not is_tech_report_meta(m)]

    run_by_slug = {str(m.get("slug", "")): m for m in run_metas if m.get("slug")}
    tech_by_slug = {str(m.get("slug", "")): m for m in study_metas if m.get("slug")}
    domain_by_slug: dict[str, str] = {}
    subtopic_by_slug: dict[str, str] = {}

    for m in sorted_metas:
        slug = str(m.get("slug", ""))
        if not slug:
            continue
        did, sub = classify_report(m, tax)
        domain_by_slug[slug] = did
        subtopic_by_slug[slug] = sub

    sim_to_techs: dict[str, list[dict[str, object]]] = {s: [] for s in run_by_slug}
    for tm in study_metas:
        refs = tm.get("referenced_simulations")
        if isinstance(refs, list):
            for r in refs:
                rs = str(r)
                if rs in sim_to_techs:
                    sim_to_techs[rs].append(tm)

    subtopic_labels = _subtopic_label_map(tax)
    domains_out: list[dict[str, object]] = []
    domain_map: dict[str, dict[str, object]] = {}

    for dom in tax:
        did = str(dom["id"])
        dom_techs = [
            tm for tm in study_metas if domain_by_slug.get(str(tm.get("slug", ""))) == did
        ]
        primary_sims = [
            rm for rm in run_metas if domain_by_slug.get(str(rm.get("slug", ""))) == did
        ]
        primary_slugs = {str(rm.get("slug", "")) for rm in primary_sims}

        cross_seen: set[str] = set()
        crossref_sims: list[dict[str, object]] = []
        for tm in dom_techs:
            for r in tm.get("referenced_simulations") or []:
                rs = str(r)
                if rs in run_by_slug and rs not in primary_slugs and rs not in cross_seen:
                    cross_seen.add(rs)
                    crossref_sims.append(run_by_slug[rs])

        if did == "coronagraphy-lowfs":
            # Showcase top coronagraphic runs as cross-references (prefer LLOWFS-closed runs).
            coro_cands: list[dict[str, object]] = []
            for rm in run_metas:
                rs = str(rm.get("slug", ""))
                cmp_d = rm.get("comparison") if isinstance(rm.get("comparison"), dict) else {}
                if rs not in primary_slugs and rs not in cross_seen and bool(cmp_d.get("has_coro")):
                    coro_cands.append(rm)
            legacy_favs = {"ao3k_scexao_predictive_ar16", "ao3k_scexao_predictive_eof128_p8"}
            fav_cands = [rm for rm in coro_cands if str(rm.get("slug", "")) in legacy_favs]
            picked_coro = fav_cands if fav_cands else sorted(
                coro_cands,
                key=lambda rm: (
                    0
                    if bool(
                        (rm.get("comparison") or {}).get("llowfs_closed", False)
                        if isinstance(rm.get("comparison"), dict)
                        else False
                    )
                    else 1,
                    meta_sort_key(rm),
                ),
            )[:4]
            for rm in picked_coro:
                rs = str(rm.get("slug", ""))
                if rs not in cross_seen:
                    cross_seen.add(rs)
                    crossref_sims.append(rm)

        if did == "bench-runtime":
            # Showcase representative runs with runtime/config instrumentation across other domains.
            rep_picks: list[dict[str, object]] = []
            picked_doms: set[str] = set()
            for rm in run_metas:
                rs = str(rm.get("slug", ""))
                if rs in primary_slugs or rs in cross_seen:
                    continue
                rdom = domain_by_slug.get(rs, "")
                if rm.get("has_compute_report") or rm.get("runtime_summary"):
                    if rdom not in picked_doms or len(rep_picks) < 4:
                        picked_doms.add(rdom)
                        rep_picks.append(rm)
                        cross_seen.add(rs)
                        if len(rep_picks) >= 4:
                            break
            if not rep_picks:
                for rm in run_metas[:4]:
                    rs = str(rm.get("slug", ""))
                    if rs not in primary_slugs and rs not in cross_seen:
                        rep_picks.append(rm)
                        cross_seen.add(rs)
            crossref_sims.extend(rep_picks)

        crossref_sims.sort(key=meta_sort_key)
        entry: dict[str, object] = {
            **dom,
            "tech_reports": dom_techs,
            "primary_sims": primary_sims,
            "crossref_sims": crossref_sims,
            "subtopic_labels": subtopic_labels.get(did, {}),
        }
        domains_out.append(entry)
        domain_map[did] = entry

    return {
        "taxonomy": tax,
        "domains": domains_out,
        "domain_map": domain_map,
        "all_metas": sorted_metas,
        "study_metas": study_metas,
        "run_metas": run_metas,
        "run_by_slug": run_by_slug,
        "tech_by_slug": tech_by_slug,
        "domain_by_slug": domain_by_slug,
        "subtopic_by_slug": subtopic_by_slug,
        "sim_to_techs": sim_to_techs,
    }
