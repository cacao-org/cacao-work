#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Dedicated Options Reference page renderer (/reference/index.html)."""

from __future__ import annotations

import html

from ..extractors.options_catalog import make_fps_opt_anchor
from .fragments import kpi_card
from .shell import render_page_shell

_BENCH_SECTION_ORDER: tuple[str, ...] = (
    "bench",
    "common",
    "dm",
    "splitter",
    "coro",
    "wfe",
    "sensor",
    "pyrwfs",
    "shwfs",
    "zwfs",
    "fpcam",
)


def _render_copy_btn(anchor: str) -> str:
    anc_esc = html.escape(anchor, quote=True)
    return (
        f'<button type="button" class="opt-copy-btn" data-copy-anchor="#{anc_esc}" '
        f'title="Copy deep link #{anc_esc}" aria-label="Copy link">#</button>'
    )


def _render_used_in_pills(used_in: object, target_page: str = "config.html") -> str:
    if not isinstance(used_in, list) or not used_in:
        return '<span class="muted">&mdash;</span>'
    shown = used_in[:3]
    pills: list[str] = []
    for item in shown:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "")
        val = str(item.get("value") or "")
        if not slug:
            continue
        tip = f"{slug}: {val}" if val else slug
        pills.append(
            f'<a class="param-pill" href="../{html.escape(slug, quote=True)}/{target_page}" '
            f'title="{html.escape(tip, quote=True)}">'
            f"<code>{html.escape(slug, quote=False)}</code></a>"
        )
    if len(used_in) > 3:
        extra_tip = ", ".join(
            f'{it.get("slug", "")}={it.get("value", "")}'
            for it in used_in[3:]
            if isinstance(it, dict)
        )
        pills.append(
            f'<span class="param-pill" title="{html.escape(extra_tip, quote=True)}">'
            f"+{len(used_in) - 3}</span>"
        )
    return f'<div class="param-list">{"".join(pills)}</div>'


def _render_fps_link(fps_param: str, valid_fps_anchors: set[str]) -> str:
    fp = fps_param.strip()
    if not fp:
        return '<span class="muted">&mdash;</span>'
    if "." in fp and not fp.startswith("<"):
        unit, kw = fp.split(".", 1)
        cand = make_fps_opt_anchor("cacaosim", unit, kw)
        if cand in valid_fps_anchors:
            return (
                f'<a class="opt-ref-link" href="#{html.escape(cand, quote=True)}">'
                f"<code>{html.escape(fp, quote=False)}</code></a>"
            )
    return f"<code>{html.escape(fp, quote=False)}</code>"


def _render_bench_tab(
    bench_opts: list[dict[str, object]],
    valid_fps_anchors: set[str],
) -> str:
    present_secs = {str(o.get("section") or "") for o in bench_opts}
    ordered_secs = [s for s in _BENCH_SECTION_ORDER if s in present_secs] + sorted(
        present_secs - set(_BENCH_SECTION_ORDER)
    )
    sec_btns = [
        '<button type="button" class="chip-btn active" data-ref-sec="all">All '
        f"({len(bench_opts)})</button>"
    ]
    for sec in ordered_secs:
        cnt = sum(1 for o in bench_opts if str(o.get("section") or "") == sec)
        sec_btns.append(
            f'<button type="button" class="chip-btn" '
            f'data-ref-sec="{html.escape(sec, quote=True)}">'
            f"{html.escape(sec, quote=False)} ({cnt})</button>"
        )

    rows: list[str] = []
    for o in bench_opts:
        sec = str(o.get("section") or "")
        key = str(o.get("key") or "")
        aliases = str(o.get("aliases") or "")
        otype = str(o.get("type") or "")
        enum_v = str(o.get("enum_values") or "")
        dflt = str(o.get("default") or "")
        unit = str(o.get("unit") or "")
        rng = str(o.get("range") or "")
        mode = str(o.get("mode") or "fused+modular")
        tier = str(o.get("tier") or "basic")
        fps_p = str(o.get("fps_param") or "")
        desc = str(o.get("description") or "")
        anchor = str(o.get("anchor") or "")

        key_html = f"<strong><code>{html.escape(key, quote=False)}</code></strong>"
        if aliases:
            al_str = ", ".join(a.strip() for a in aliases.split(",") if a.strip())
            key_html += f'<div class="opt-sub-meta">alias: <code>{html.escape(al_str)}</code></div>'
        type_html = f"<code>{html.escape(otype, quote=False)}</code>"
        if enum_v:
            type_html += f'<div class="opt-sub-meta">{html.escape(enum_v, quote=False)}</div>'
        ur_parts = [p for p in (unit, rng) if p]
        ur_html = (
            f'<code>{html.escape(" · ".join(ur_parts), quote=False)}</code>'
            if ur_parts
            else '<span class="muted">&mdash;</span>'
        )
        mode_cls = "opt-badge-fused" if mode == "fused-only" else "opt-badge-both"
        mode_lbl = "fused-only" if mode == "fused-only" else "fused+mod"
        tier_pill = (
            ' <span class="opt-badge-adv" title="Visible under [v:Adv] in cacaosim-CTRL">Adv</span>'
            if tier == "advanced"
            else ""
        )
        dflt_html = (
            f"<code>{html.escape(dflt, quote=False)}</code>"
            if dflt
            else '<span class="muted">&mdash;</span>'
        )
        search_blob = f"{sec} {key} {aliases} {otype} {enum_v} {fps_p} {desc}".lower()
        rows.append(
            f'<tr id="{html.escape(anchor, quote=True)}" class="ref-bench-row" '
            f'data-sec="{html.escape(sec, quote=True)}" '
            f'data-mode="{html.escape(mode, quote=True)}" '
            f'data-tier="{html.escape(tier, quote=True)}" '
            f'data-search="{html.escape(search_blob, quote=True)}">'
            f'<td>{_render_copy_btn(anchor)}<code>[{html.escape(sec, quote=False)}]</code></td>'
            f"<td>{key_html}{tier_pill}</td>"
            f"<td>{type_html}</td>"
            f"<td>{dflt_html}</td>"
            f"<td>{ur_html}</td>"
            f'<td><span class="opt-badge {mode_cls}">{mode_lbl}</span></td>'
            f"<td>{_render_fps_link(fps_p, valid_fps_anchors)}</td>"
            f'<td class="param-cell">{_render_used_in_pills(o.get("used_in"))}</td>'
            f'<td class="wrap-cell">{html.escape(desc, quote=False)}</td>'
            "</tr>"
        )

    return (
        '<div class="tab-panel ref-tab-panel active" id="ref-panel-bench" data-ref-panel="bench">\n'
        '<div class="sim-filter-panel">\n'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Section:</span>'
        f'{"".join(sec_btns)}</div>\n'
        '<div class="filter-actions-row">\n'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Engine Mode:</span>'
        '<button type="button" class="chip-btn active" data-ref-mode="all">All</button>'
        '<button type="button" class="chip-btn" data-ref-mode="fused+modular">Fused+Mod</button>'
        '<button type="button" class="chip-btn" data-ref-mode="fused-only">Fused-only</button>'
        '<span class="filter-inline-label">TUI Tier:</span>'
        '<button type="button" class="chip-btn active" data-ref-tier="all">All</button>'
        '<button type="button" class="chip-btn" data-ref-tier="basic">Basic</button>'
        '<button type="button" class="chip-btn" data-ref-tier="advanced">Advanced</button>'
        "</div>\n"
        '<div class="toolbar-group">'
        '<input type="search" id="ref-bench-search" class="search-input" '
        'placeholder="Search .bench keys, aliases, or physics...">'
        '<button type="button" class="btn-sm" id="ref-bench-reset">Reset</button>'
        f'<span id="ref-bench-count" class="muted">{len(bench_opts)} / {len(bench_opts)}</span>'
        "</div>\n</div>\n</div>\n"
        '<div class="table-wrap" data-sortable="1">'
        '<table id="ref-bench-table"><thead><tr>'
        "<th>Section</th><th>Key / Aliases</th><th>Type</th><th>Default</th>"
        "<th>Unit &middot; Range</th><th>Mode</th><th>FPS Param</th>"
        "<th>Used In</th><th>Description</th>"
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>\n'
        '<div id="ref-bench-empty" class="cat-empty-note hidden">'
        "No .bench options match the active filters.</div>\n"
        "</div>"
    )


def _render_fps_tab(fps_units: list[dict[str, object]]) -> str:
    n_csim = sum(1 for u in fps_units if u.get("package") == "cacaosim")
    n_atm = sum(1 for u in fps_units if u.get("package") == "milkatmturb")
    n_cacao = sum(1 for u in fps_units if u.get("package") == "cacao")
    unit_opts = ['<option value="all">All Units</option>']
    unit_chips: list[str] = []
    rows: list[str] = []

    for u in fps_units:
        pkg = str(u.get("package") or "")
        uname = str(u.get("unit") or "")
        binary = str(u.get("binary") or "")
        udesc = str(u.get("description") or "")
        uanchor = str(u.get("anchor") or "")
        params = u.get("params") if isinstance(u.get("params"), list) else []
        ukey = f"{pkg}.{uname}"
        unit_opts.append(
            f'<option value="{html.escape(ukey, quote=True)}">'
            f"{html.escape(ukey, quote=False)} ({len(params)})</option>"
        )
        pkg_cls = (
            "cat-simulation"
            if pkg == "cacaosim"
            else ("cat-loop_operation" if pkg == "cacao" else "cat-analysis")
        )
        unit_chips.append(
            f'<button type="button" class="chip-btn ref-unit-chip {pkg_cls}" '
            f'id="{html.escape(uanchor, quote=True)}" '
            f'data-ref-unit-jump="{html.escape(ukey, quote=True)}" '
            f'title="{html.escape(binary + ": " + udesc, quote=True)}">'
            f"<code>{html.escape(ukey, quote=False)}</code> ({len(params)})</button>"
        )
        for p in params:
            if not isinstance(p, dict):
                continue
            kw = str(p.get("keyword") or "")
            ptype = str(p.get("type") or "")
            dflt = str(p.get("default") or "")
            acc = str(p.get("access") or "init")
            desc = str(p.get("description") or "")
            anchor = str(p.get("anchor") or "")

            acc_cls = (
                "opt-badge-live"
                if acc == "live"
                else ("opt-badge-out" if acc == "output" else "opt-badge-init")
            )
            acc_lbl = "LIVE (WRITERUN)" if acc == "live" else acc.upper()
            dflt_html = (
                f"<code>{html.escape(dflt, quote=False)}</code>"
                if dflt != ""
                else '<span class="muted">&mdash;</span>'
            )
            sblob = f"{pkg} {uname} {binary} {kw} {ptype} {acc} {desc}".lower()
            rows.append(
                f'<tr id="{html.escape(anchor, quote=True)}" class="ref-fps-row" '
                f'data-pkg="{html.escape(pkg, quote=True)}" '
                f'data-unit="{html.escape(ukey, quote=True)}" '
                f'data-access="{html.escape(acc, quote=True)}" '
                f'data-search="{html.escape(sblob, quote=True)}">'
                f'<td>{_render_copy_btn(anchor)}'
                f'<span class="metric-pill">{html.escape(pkg, quote=False)}</span></td>'
                f'<td><code>{html.escape(uname, quote=False)}</code>'
                '<div class="opt-sub-meta">'
                f'<code>{html.escape(binary, quote=False)}</code></div></td>'
                f"<td><strong><code>{html.escape(kw, quote=False)}</code></strong></td>"
                f"<td><code>{html.escape(ptype, quote=False)}</code></td>"
                f"<td>{dflt_html}</td>"
                f'<td><span class="opt-badge {acc_cls}">{acc_lbl}</span></td>'
                f'<td class="wrap-cell">{html.escape(desc, quote=False)}</td>'
                "</tr>"
            )

    total = len(rows)
    return (
        '<div class="tab-panel ref-tab-panel" id="ref-panel-fps" data-ref-panel="fps">\n'
        '<div class="sim-filter-panel">\n'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Package:</span>'
        '<button type="button" class="chip-btn active" data-ref-pkg="all">'
        f"All ({len(fps_units)} units)</button>"
        '<button type="button" class="chip-btn" data-ref-pkg="cacaosim">'
        f"cacaosim ({n_csim})</button>"
        '<button type="button" class="chip-btn" data-ref-pkg="milkatmturb">'
        f"milkatmturb ({n_atm})</button>"
        + (
            f'<button type="button" class="chip-btn" data-ref-pkg="cacao">cacao ({n_cacao})</button>'
            if n_cacao
            else ""
        )
        + '<span class="filter-inline-label">Access:</span>'
        '<button type="button" class="chip-btn active" data-ref-acc="all">All</button>'
        '<button type="button" class="chip-btn" data-ref-acc="live">Live (WRITERUN)</button>'
        '<button type="button" class="chip-btn" data-ref-acc="init">Init</button>'
        '<button type="button" class="chip-btn" data-ref-acc="output">Output</button>'
        "</div>\n"
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Compute Units:</span>'
        f'{"".join(unit_chips)}</div>\n'
        '<div class="filter-actions-row">\n'
        '<div class="toolbar-group">'
        '<label class="filter-inline-label" for="ref-fps-unit-select">Unit:</label>'
        f'<select id="ref-fps-unit-select" class="select-input">{"".join(unit_opts)}</select>'
        "</div>\n"
        '<div class="toolbar-group">'
        '<input type="search" id="ref-fps-search" class="search-input" '
        'placeholder="Search FPS keywords, units, or descriptions...">'
        '<button type="button" class="btn-sm" id="ref-fps-reset">Reset</button>'
        f'<span id="ref-fps-count" class="muted">{total} / {total}</span>'
        "</div>\n</div>\n</div>\n"
        '<div class="table-wrap" data-sortable="1">'
        '<table id="ref-fps-table"><thead><tr>'
        "<th>Package</th><th>Compute Unit</th><th>FPS Keyword</th><th>Type</th>"
        "<th>Default</th><th>Access</th><th>Description</th>"
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>\n'
        '<div id="ref-fps-empty" class="cat-empty-note hidden">'
        "No FPS parameters match the active filters.</div>\n"
        "</div>"
    )


def _render_cli_tab(
    runner_cli: list[dict[str, object]],
    env_vars: list[dict[str, object]],
    cacaosim_cli: list[dict[str, object]],
) -> str:
    all_items: list[dict[str, object]] = [*runner_cli, *env_vars, *cacaosim_cli]
    tools_order = [
        ("run-ao3k-scexao.sh", f"run-ao3k-scexao.sh ({len(runner_cli)})"),
        ("cacaoloop-ao3k-scexao.milk", f"CACAO_* Env Vars ({len(env_vars)})"),
        ("cacaosim-bench", "cacaosim-bench"),
        ("cacaosim-bench-view", "cacaosim-bench-view"),
        ("cacaosim-CTRL", "cacaosim-CTRL"),
    ]
    tool_btns = [
        f'<button type="button" class="chip-btn active" data-ref-tool="all">'
        f"All ({len(all_items)})</button>"
    ]
    for tkey, tlbl in tools_order:
        cnt = sum(1 for it in all_items if str(it.get("tool") or "") == tkey)
        if cnt:
            lbl = tlbl if "(" in tlbl else f"{tlbl} ({cnt})"
            tool_btns.append(
                f'<button type="button" class="chip-btn" '
                f'data-ref-tool="{html.escape(tkey, quote=True)}">'
                f"{html.escape(lbl, quote=False)}</button>"
            )

    rows: list[str] = []
    for it in all_items:
        tool = str(it.get("tool") or "")
        flag = str(it.get("flag") or "")
        arg = str(it.get("arg") or "")
        dflt = str(it.get("default") or "")
        grp = str(it.get("group") or "")
        desc = str(it.get("description") or "")
        anchor = str(it.get("anchor") or "")
        sblob = f"{tool} {flag} {arg} {grp} {desc}".lower()

        arg_html = (
            f"<code>{html.escape(arg, quote=False)}</code>"
            if arg
            else '<span class="muted">&mdash;</span>'
        )
        dflt_html = (
            f"<code>{html.escape(dflt, quote=False)}</code>"
            if dflt
            else '<span class="muted">&mdash;</span>'
        )
        used_html = _render_used_in_pills(it.get("used_in"), target_page="how_to_run.html")
        rows.append(
            f'<tr id="{html.escape(anchor, quote=True)}" class="ref-cli-row" '
            f'data-tool="{html.escape(tool, quote=True)}" '
            f'data-search="{html.escape(sblob, quote=True)}">'
            f'<td>{_render_copy_btn(anchor)}'
            f"<code>{html.escape(tool, quote=False)}</code></td>"
            f"<td><strong><code>{html.escape(flag, quote=False)}</code></strong></td>"
            f"<td>{arg_html}</td>"
            f"<td>{dflt_html}</td>"
            f'<td><span class="metric-pill">{html.escape(grp, quote=False)}</span></td>'
            f'<td class="param-cell">{used_html}</td>'
            f'<td class="wrap-cell">{html.escape(desc, quote=False)}</td>'
            "</tr>"
        )

    total = len(rows)
    return (
        '<div class="tab-panel ref-tab-panel" id="ref-panel-cli" data-ref-panel="cli">\n'
        '<div class="sim-filter-panel">\n'
        '<div class="toolbar-group">'
        '<span class="filter-inline-label">Tool / Script:</span>'
        f'{"".join(tool_btns)}</div>\n'
        '<div class="filter-actions-row">\n'
        '<span class="muted">Includes <code>run-ao3k-scexao.sh</code> / '
        "<code>sim-ao3k-scexao.milk</code> flags, <code>cacaoloop-ao3k-scexao.milk</code> "
        "<code>CACAO_*</code> env vars, and <code>cacaosim</code> CLIs.</span>"
        '<div class="toolbar-group">'
        '<input type="search" id="ref-cli-search" class="search-input" '
        'placeholder="Search CLI flags, env vars, or descriptions...">'
        '<button type="button" class="btn-sm" id="ref-cli-reset">Reset</button>'
        f'<span id="ref-cli-count" class="muted">{total} / {total}</span>'
        "</div>\n</div>\n</div>\n"
        '<div class="table-wrap" data-sortable="1">'
        '<table id="ref-cli-table"><thead><tr>'
        "<th>Tool</th><th>Flag / Env Var</th><th>Argument</th><th>Default</th>"
        "<th>Group</th><th>Used In</th><th>Description</th>"
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>\n'
        '<div id="ref-cli-empty" class="cat-empty-note hidden">'
        "No CLI flags or environment variables match the active filters.</div>\n"
        "</div>"
    )


def build_options_reference_html(
    hierarchy: dict[str, object],
    catalog: dict[str, object],
) -> str:
    """Render /reference/index.html with filterable .bench, FPS, and CLI option tables."""
    counts = catalog.get("counts") if isinstance(catalog.get("counts"), dict) else {}
    bench_opts = list(catalog.get("bench_options") or [])
    fps_units = list(catalog.get("fps_units") or [])
    cacaosim_cli = list(catalog.get("cacaosim_cli") or [])
    runner_cli = list(catalog.get("runner_cli") or [])
    env_vars = list(catalog.get("env_vars") or [])

    valid_fps_anchors: set[str] = set()
    for u in fps_units:
        if not isinstance(u, dict):
            continue
        for p in u.get("params") or []:
            if isinstance(p, dict) and p.get("anchor"):
                valid_fps_anchors.add(str(p["anchor"]))

    n_bench = int(counts.get("bench_options", len(bench_opts)))
    n_fps_u = int(counts.get("fps_units", len(fps_units)))
    n_fps_p = int(counts.get("fps_params", 0))
    n_csim_u = int(counts.get("cacaosim_units", 0))
    n_atm_u = int(counts.get("atmturb_units", 0))
    n_cacao_u = int(counts.get("cacao_units", 0))
    n_cli_all = len(runner_cli) + len(env_vars) + len(cacaosim_cli)
    unit_breakdown = f"{n_csim_u}+{n_atm_u}+{n_cacao_u}" if n_cacao_u else f"{n_csim_u}+{n_atm_u}"

    hero_html = (
        '<section class="hero-banner">\n'
        "<h1>Simulator &amp; CACAO Options Reference</h1>\n"
        "<p>Authoritative, schema-generated reference covering every declarative "
        "<code>.bench</code> optical bench key, all compiled <code>cacaosim</code>, "
        "<code>milkatmturb</code>, and <code>cacao</code> predictive-control FPS compute unit "
        "parameters, and all <code>cacao-work</code> simulation runner CLI flags and "
        "<code>CACAO_*</code> environment variables.</p>\n"
        '<div class="kpi-grid">'
        + kpi_card(".bench DSL Keys", str(n_bench), "From compiled C schema")
        + kpi_card(
            "FPS Compute Units",
            f"{n_fps_u} ({unit_breakdown})",
            f"{n_fps_p} introspected FPS params",
        )
        + kpi_card(
            "Runner &amp; CLI Flags",
            str(len(runner_cli) + len(cacaosim_cli)),
            "Auto-verified vs usage()",
        )
        + kpi_card("CACAO_* Env Vars", str(len(env_vars)), "cacaoloop-ao3k-scexao.milk")
        + "</div>\n"
        '<div class="opt-cli-tip">'
        "<strong>In-Tool Equivalents:</strong> "
        "<code>cacaosim-bench options --section pyrwfs</code> &middot; "
        "<code>cacaosim-bench options --fps all --live</code> &middot; "
        "<code>cacaosim-CTRL</code> (press <code>?</code> for Option Reference, "
        "<code>v</code> in F2:Builder for Advanced keys)"
        "</div>\n"
        "</section>"
    )

    tab_bar = (
        '<div class="explorer-panel" id="options-ref-root">\n'
        '<div class="tab-bar ref-tab-bar" role="tablist">\n'
        f'<button type="button" class="chip-btn ref-tab-btn active" role="tab" '
        f'aria-selected="true" data-ref-tab="bench">.bench Optical Elements ({n_bench})</button>\n'
        f'<button type="button" class="chip-btn ref-tab-btn" role="tab" '
        f'aria-selected="false" data-ref-tab="fps">'
        f"FPS Runtime Units ({n_fps_u} units &middot; {n_fps_p} params)</button>\n"
        f'<button type="button" class="chip-btn ref-tab-btn" role="tab" '
        f'aria-selected="false" data-ref-tab="cli">'
        f"CLI Flags &amp; Runners ({n_cli_all})</button>\n"
        "</div>\n"
        + _render_bench_tab(bench_opts, valid_fps_anchors)
        + "\n"
        + _render_fps_tab(fps_units)
        + "\n"
        + _render_cli_tab(runner_cli, env_vars, cacaosim_cli)
        + "\n</div>"
    )

    body_html = f"{hero_html}\n\n{tab_bar}"
    return render_page_shell(
        title="Simulator Options Reference · cacao-work",
        rel_root="..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="reference",
        page_kind="reference",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Options Reference", None),
        ],
        show_sidebar=False,
        page_scripts=("options_ref.js",),
        footer_right=(
            f"{n_bench} .bench keys · {n_fps_p} FPS params · {n_cli_all} CLI/env options"
        ),
    )
