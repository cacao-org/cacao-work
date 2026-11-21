#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Open-Source Stack, End-to-End Reproduction, and Taxonomy Guide (/stack/index.html)."""

from __future__ import annotations

import html

from ..constants import DEFAULT_RUN_COMMAND
from ..markdown.sim_split import extract_toc_items
from .fragments import merge_repo_list
from .shell import render_page_shell


def build_stack_guide_html(hierarchy: dict[str, object]) -> str:
    """Render /stack/index.html containing GitHub repos, reproduction script, and taxonomy guide."""
    study_metas = list(hierarchy.get("study_metas") or [])
    run_metas = list(hierarchy.get("run_metas") or [])
    all_metas = list(hierarchy.get("all_metas") or [])

    latest_repro: dict[str, object] | None = None
    primary_slug = ""
    for meta in run_metas + study_metas:
        if not isinstance(meta, dict):
            continue
        if not primary_slug and meta in run_metas:
            primary_slug = str(meta.get("slug", ""))
        rep = meta.get("reproducibility")
        if isinstance(rep, dict) and rep.get("repositories"):
            latest_repro = rep
            if meta in run_metas:
                primary_slug = str(meta.get("slug", primary_slug))

    repo_list, repo_by_name = merge_repo_list(latest_repro)

    repo_rows: list[str] = [
        '<div class="table-wrap" data-sortable="1">',
        "<table><thead><tr>"
        '<th style="text-align: left;">Repository</th>'
        '<th style="text-align: center;">Branch</th>'
        '<th style="text-align: center;">Commit</th>'
        '<th style="text-align: left;">Role in Simulation Stack</th>'
        "</tr></thead><tbody>",
    ]
    for r in repo_list:
        rname = html.escape(r.get("name", ""), quote=False)
        rurl = html.escape(r.get("url", ""), quote=True)
        rbr = html.escape(r.get("branch", "main"), quote=False)
        rsha = r.get("commit", "")
        rshort = r.get("short_commit", rsha[:7] if rsha else "")
        rrole = html.escape(r.get("role", ""), quote=False)
        if rsha and rshort:
            c_url = html.escape(f"{r.get('url', '')}/commit/{rsha}", quote=True)
            sha_html = (
                f'<a href="{c_url}" target="_blank" rel="noopener">'
                f"<code>{html.escape(rshort, quote=False)}</code></a>"
            )
        else:
            sha_html = "<code>HEAD</code>"
        repo_rows.append(
            "<tr>"
            f'<td><a href="{rurl}" target="_blank" rel="noopener">'
            f"<strong>{rname}</strong></a></td>"
            f'<td style="text-align: center;"><code>{rbr}</code></td>'
            f'<td style="text-align: center;">{sha_html}</td>'
            f'<td class="wrap-cell">{rrole}</td></tr>'
        )
    repo_rows.append("</tbody></table></div>")

    def clone_cmd(rname: str) -> str:
        info = repo_by_name.get(rname, {"url": f"https://github.com/milk-org/{rname}"})
        url = info.get("url", "").rstrip("/") + ".git"
        br = info.get("branch", "main")
        sha = info.get("commit", "")
        line = f"git clone -b {br} {url} {rname}"
        if sha:
            line += f" && git -C {rname} checkout -q {sha}"
        return line

    isio_sha = repo_by_name.get("ImageStreamIO", {}).get("commit", "")
    isio_cmd = "git -C milk submodule update --init src/engine/ImageStreamIO"
    if isio_sha:
        isio_cmd += f" && git -C milk/src/engine/ImageStreamIO checkout -q {isio_sha}"

    run_cmd = (
        str(latest_repro.get("run_command", DEFAULT_RUN_COMMAND))
        if latest_repro
        else DEFAULT_RUN_COMMAND
    )
    stage_slug = primary_slug or "ao3k_scexao"
    artifact_note = ""
    if latest_repro and primary_slug:
        bfile = html.escape(str(latest_repro.get("bench_file", "ao3k_scexao.bench")))
        mfile = html.escape(str(latest_repro.get("metrics_file", "ao3k_scexao_metrics.json")))
        p_esc = html.escape(primary_slug, quote=True)
        artifact_note = (
            "<li><strong>Machine-Readable Bench &amp; Provenance Manifest</strong>: "
            f'<a href="../{p_esc}/{bfile}"><code>{bfile}</code></a> and '
            f'<a href="../{p_esc}/{mfile}"><code>{mfile}</code></a> '
            "(records optical parameters, calibrated loop metrics, and commit SHAs).</li>\n"
        )

    sim_cmds = [
        str((m.get("reproducibility") or {}).get("run_command", run_cmd))
        for m in run_metas
        if isinstance(m, dict)
        and isinstance(m.get("reproducibility"), dict)
        and (m.get("reproducibility") or {}).get("run_command")
    ]
    bash_recipe = "\n".join(
        [
            "# 1. Clone all open-source stack repositories into ~/src",
            "mkdir -p ~/src && cd ~/src",
            clone_cmd("milk"),
            isio_cmd,
            clone_cmd("cacao"),
            clone_cmd("milk-mltools"),
            clone_cmd("OpticsMaterials"),
            clone_cmd("WFpropagate"),
            clone_cmd("AtmosphericTurbulenceSimul"),
            clone_cmd("cacaosim"),
            clone_cmd("cacao-work"),
            "",
            "# 2. Configure, compile, install into milk/_install, and run isolated sanity tests",
            "cd ~/src/cacao-work",
            "source env.sh",
            "./scripts/build-all.sh",
            '"$PYTHON_BIN" -m pytest -v tests/test_00_stack_sanity.py tests/test_05_ao_web_report.py',
            "",
            "# 3. Run closed-loop Subaru AO3k + SCExAO simulations, telemetry & reports",
            *(sim_cmds if len(run_metas) >= 2 and sim_cmds else [run_cmd]),
            *(
                [
                    "",
                    "# 3b. Compile comparative Predictive Control Report",
                    "${PYTHON_BIN} ./scripts/build-predictive-control-report.py",
                ]
                if any(isinstance(m, dict) and m.get("slug") == "predictive_control_report" for m in study_metas)
                else []
            ),
            *(
                [
                    "",
                    "# 3c. Compile 2-WFS + 1-DM Telemetry Calibration Study Report",
                    "${PYTHON_BIN} ./scripts/build-calib-2wfs1dm-report.py",
                ]
                if any(isinstance(m, dict) and m.get("slug") == "calib_2wfs1dm_report" for m in study_metas)
                else []
            ),
            "",
            "# 4. Stage static HTML website locally under _work/_web_site/public/",
            *(
                [
                    f"./scripts/publish-ao-report.sh --build-only _work/{m.get('slug')}"
                    for m in all_metas
                    if isinstance(m, dict) and m.get("slug")
                ]
                if len(all_metas) >= 2
                else [f"./scripts/publish-ao-report.sh --build-only _work/{stage_slug}"]
            ),
        ]
    )

    adding_sec = (
        '<h2 id="adding-reports">Adding New Research Topics &amp; Reports</h2>\n'
        "<p>The entire navigation hierarchy, topic hubs, and pull-down menus are driven "
        "declaratively by <code>scripts/report_site/taxonomy.json</code> and each report's "
        "<code>study_meta.json</code>:</p>\n"
        "<ul>\n"
        "<li><strong>Assign an existing domain</strong>: Add <code>\"domain\"</code> "
        "(one of <code>wavefront-control</code>, <code>calibration-sysid</code>, "
        "<code>coronagraphy-lowfs</code>, <code>bench-runtime</code>) and optional "
        "<code>\"subtopic\"</code> inside <code>study_meta.json</code>.</li>\n"
        "<li><strong>Add a new domain</strong>: Append a new domain object to "
        "<code>scripts/report_site/taxonomy.json</code> and rebuild via "
        "<code>build-ao-web-report.py --rebuild-all _work</code>.</li>\n"
        "</ul>"
    )

    body_html = "\n\n".join(
        [
            "<h1>Open-Source AO Stack &amp; Reproduction Guide</h1>",
            "<p>Complete source repository provenance, CMake build instructions, and "
            "automated CLI commands to reproduce all simulations and technical reports. "
            'Browse every optical bench key, FPS parameter, and CLI flag in the '
            '<a href="../reference/index.html"><strong>Simulator Options Reference</strong></a>.</p>',
            '<h2 id="github-repositories">Open-Source GitHub Repositories</h2>',
            "<p>All source repositories build into one relocatable prefix "
            "(<code>milk/_install/milk-&lt;version&gt;</code>) via "
            "<code>./scripts/build-all.sh</code>:</p>",
            "\n".join(repo_rows),
            '<h2 id="reproduce-results">End-to-End Reproduction Guide (CLI &amp; AI Agent Ready)</h2>',
            "<ul>\n"
            "<li><strong>System Prerequisites</strong>: Linux <code>x86_64</code> with "
            "<code>/dev/shm</code> (<code>tmpfs</code>), GCC/G++ with OpenMP, CMake &ge; 3.20, "
            "CFITSIO, FFTW3, OpenBLAS + LAPACKE, <code>ncurses</code>, NVIDIA CUDA Toolkit "
            "(CPU fallback supported), and Python &ge; 3.10.</li>\n"
            f"{artifact_note}</ul>",
            f"<pre><code>{html.escape(bash_recipe, quote=False)}</code></pre>",
            adding_sec,
        ]
    )
    toc_items = extract_toc_items(body_html)

    return render_page_shell(
        title="Open-Source Stack & Reproduction Guide · cacao-work",
        rel_root="..",
        hierarchy=hierarchy,
        body_html=body_html,
        active_nav="stack",
        page_kind="stack",
        breadcrumbs=[
            ("Home", "../index.html"),
            ("Stack & Guides", None),
        ],
        show_sidebar=True,
        toc_items=toc_items,
        footer_right="9 Repositories · Relocatable MILK/CACAO Build",
    )
