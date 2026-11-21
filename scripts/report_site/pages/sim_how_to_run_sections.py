#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Section helpers for Simulation How-to-Run page (customizer, checklist, hardware)."""

from __future__ import annotations

import html

from ..constants import COMPUTE_CATEGORY_ORDER
from ..extractors.options_catalog import RUNNER_CLI_OPTIONS, make_runner_opt_anchor
from .fragments import render_cat_badge, render_section_badges, safe_json_embed


def _opt_label(for_id: str, text: str, flag: str) -> str:
    anc = html.escape(make_runner_opt_anchor(flag), quote=True)
    return (
        f'<label for="{html.escape(for_id, quote=True)}">'
        f'<a class="opt-ref-link" href="../reference/index.html#{anc}" '
        f'title="Open {html.escape(flag, quote=True)} in Options Reference">'
        f"{html.escape(text, quote=False)}</a></label>"
    )


def _render_advanced_customizer(
    run_options: dict[str, object] | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """Render collapsible Advanced Options accordion driven by RUNNER_CLI_OPTIONS."""
    raw_opts = (
        run_options.get("options")
        if isinstance(run_options, dict) and isinstance(run_options.get("options"), dict)
        else (run_options if isinstance(run_options, dict) else {})
    )
    adv_opts = [
        o
        for o in RUNNER_CLI_OPTIONS
        if o.get("tier") == "advanced" and not o.get("customizer_omit")
    ]
    groups: dict[str, list[dict[str, object]]] = {}
    for o in adv_opts:
        grp = str(o.get("group") or "Other")
        groups.setdefault(grp, []).append(o)

    specs_js: list[dict[str, object]] = []
    grp_blocks: list[str] = []
    for grp, items in groups.items():
        fields: list[str] = []
        for o in items:
            okey = str(o["key"])
            flag = str(o["flag"])
            otype = str(o.get("type") or "string")
            dflt = str(o.get("default") or "")
            lbl = str(o.get("label") or flag)
            cid = f"cust-adv-{okey}"
            init_val = ""
            if isinstance(raw_opts, dict):
                neg_map = {
                    "no_fast_calib": "fast_calib",
                    "no_selfrm": "run_selfrm",
                    "no_tlm_analysis": "run_tlm_analysis",
                }
                if okey in neg_map and neg_map[okey] in raw_opts:
                    raw_v = raw_opts[neg_map[okey]]
                    if str(raw_v) in ("0", "False", "false"):
                        init_val = "1"
                elif okey in raw_opts and raw_opts[okey] is not None:
                    cand = str(raw_opts[okey]).strip()
                    if otype == "bool":
                        if cand in ("1", "True", "true", "ON"):
                            init_val = "1"
                    elif cand and cand != dflt and not dflt.startswith("matches"):
                        init_val = cand
            specs_js.append(
                {
                    "key": okey,
                    "flag": flag,
                    "type": otype,
                    "default": dflt,
                    "init": init_val,
                }
            )
            lbl_html = _opt_label(cid, f"{lbl} ({flag})", flag)
            if otype == "bool":
                fields.append(
                    '<div class="field-box">'
                    f"{lbl_html}"
                    '<div class="field-check-row">'
                    f'<input id="{cid}" type="checkbox">'
                    f'<span class="muted">Enable <code>{html.escape(flag)}</code></span>'
                    "</div></div>"
                )
            else:
                ph = html.escape(dflt or str(o.get("arg") or ""), quote=True)
                itype = "number" if otype in ("float", "int") else "text"
                step_attr = (
                    ' step="any"'
                    if otype == "float"
                    else (' step="1"' if otype == "int" else "")
                )
                fields.append(
                    f'<div class="field-box">{lbl_html}'
                    f'<input id="{cid}" type="{itype}"{step_attr} placeholder="{ph}"></div>'
                )
        grp_blocks.append(
            '<div class="adv-customizer-group">'
            f'<div class="adv-customizer-group-hdr">{html.escape(grp, quote=False)}</div>'
            f'<div class="customizer-grid">{"".join(fields)}</div></div>'
        )
    ref_see_anc = html.escape(make_runner_opt_anchor("--seeing"), quote=True)
    html_block = (
        '<details class="adv-customizer">\n'
        f"<summary>Advanced Options ({len(adv_opts)} flags from "
        "<code>run-ao3k-scexao.sh</code>) &middot; "
        f'<a href="../reference/index.html#{ref_see_anc}">Full Reference &rarr;</a>'
        "</summary>\n"
        f'{"".join(grp_blocks)}\n'
        "</details>\n"
    )
    return html_block, specs_js


def render_customizer_section(
    raw_cmd: str,
    defaults: dict[str, str],
    run_options: dict[str, object] | None = None,
) -> str:
    """Render Section 1: Turnkey Command & Interactive Parameter Customizer."""
    cmd_badges_all = render_section_badges(COMPUTE_CATEGORY_ORDER)
    cmd_badges_sim = render_section_badges(["simulation"])
    cmd_badges_loop = render_section_badges(["calibration", "loop_operation"])
    adv_html, adv_specs = _render_advanced_customizer(run_options)
    return (
        '<h2 id="interactive-command-customizer">'
        "1. Turnkey Command &amp; Interactive Parameter Customizer</h2>\n"
        "<p>Pre-loaded with this simulation's exact parameters. Adjust any field below to "
        "generate custom commands for <code>run-ao3k-scexao.sh</code>, "
        "<code>cacaosim-bench</code>, and <code>cacaoloop-ao3k-scexao.milk</code>. "
        'Click any label to open its definition in the '
        '<a href="../reference/index.html">Options Reference</a>:</p>\n'
        '<div class="explorer-panel">\n'
        '<div class="customizer-grid">\n'
        f'<div class="field-box">{_opt_label("cust-seeing", "Seeing [arcsec]", "--seeing")}'
        '<input id="cust-seeing" type="number" step="0.05" min="0.2" max="2.0"></div>\n'
        f'<div class="field-box">{_opt_label("cust-phys_time", "Phys Time [s]", "--phys-time")}'
        '<input id="cust-phys_time" type="number" step="0.5" min="0.5" max="60"></div>\n'
        f'<div class="field-box">{_opt_label("cust-bench_mode", "cacaosim Mode", "--bench-mode")}'
        '<select id="cust-bench_mode"><option value="fused">fused (csim_htsim)</option>'
        '<option value="modular">modular (per-element FPS)</option></select></div>\n'
        f'<div class="field-box">{_opt_label("cust-oversample", "Oversample K", "--oversample")}'
        '<select id="cust-oversample"><option value="1">1x (2 kHz)</option>'
        '<option value="2">2x (4 kHz)</option><option value="4">4x (8 kHz)</option>'
        "</select></div>\n"
        f'<div class="field-box">{_opt_label("cust-gain1", "Stage-1 Gain", "--gain1")}'
        '<input id="cust-gain1" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        f'<div class="field-box">{_opt_label("cust-gain2", "Stage-2 Gain", "--gain2")}'
        '<input id="cust-gain2" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        f'<div class="field-box">{_opt_label("cust-gain3", "Stage-3 Gain", "--gain3")}'
        '<input id="cust-gain3" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        f'<div class="field-box">{_opt_label("cust-llowfs", "Stage-3 LLOWFS", "--no-lowfs")}'
        '<select id="cust-llowfs"><option value="closed">CLOSED</option>'
        '<option value="open">OPEN (--no-lowfs)</option></select></div>\n'
        f'<div class="field-box">{_opt_label("cust-pf_mode", "Predictive Control", "--pf-mode")}'
        '<select id="cust-pf_mode"><option value="off">OFF (Integrator)</option>'
        '<option value="ar">PSOL Diagonal AR(P)</option>'
        '<option value="eof">PSOL Cross-Mode Block-EOF</option></select></div>\n'
        f'<div class="field-box">{_opt_label("cust-pf_order", "PF Order P", "--pf-order")}'
        '<select id="cust-pf_order"><option value="4">4</option><option value="8">8</option>'
        '<option value="16">16</option><option value="32">32</option>'
        '<option value="64">64</option></select></div>\n'
        '<div class="field-box">'
        f'{_opt_label("cust-pf_blocksize", "EOF Block Size B", "--pf-blocksize")}'
        '<select id="cust-pf_blocksize"><option value="64">64</option>'
        '<option value="128">128</option></select></div>\n'
        f'<div class="field-box">{_opt_label("cust-pf_reg", "PF Reg lambda", "--pf-reg")}'
        '<input id="cust-pf_reg" type="text"></div>\n'
        '<div class="field-box">'
        f'{_opt_label("cust-calib_2wfs1dm", "2-WFS/1-DM Calib", "--calib-2wfs1dm")}'
        '<select id="cust-calib_2wfs1dm"><option value="off">OFF</option>'
        '<option value="on">ON (--calib-2wfs1dm)</option></select></div>\n'
        '<div class="field-box">'
        f'{_opt_label("cust-telemetry", "Telemetry Mode", "--save-telemetry")}'
        '<select id="cust-telemetry"><option value="none">none</option>'
        '<option value="standard">standard</option>'
        '<option value="speckle">speckle</option>'
        '<option value="truth">truth</option></select></div>\n'
        "</div>\n"
        f"{adv_html}"
        '<div class="toolbar">'
        '<span id="cust-advice" class="muted"></span>'
        '<button type="button" class="btn-sm" id="cust-reset">Reset to Simulation Defaults</button>'
        "</div>\n"
        f'<h4>Exact Simulation Command (<code>run-ao3k-scexao.sh</code>) {cmd_badges_all}</h4>'
        f'<pre><code id="cmd-turnkey">{html.escape(raw_cmd, quote=False)}</code></pre>\n'
        f'<h4>Optical Bench Only (<code>cacaosim-bench</code>) {cmd_badges_sim}</h4>'
        '<pre><code id="cmd-cacaosim"></code></pre>\n'
        f'<h4>CACAO Loops Only (<code>cacaoloop-ao3k-scexao.milk</code>) {cmd_badges_loop}</h4>'
        '<pre><code id="cmd-cacaoloop"></code></pre>\n'
        '<script id="howtorun-defaults" type="application/json">'
        f"{safe_json_embed(defaults)}</script>\n"
        '<script id="howtorun-adv-specs" type="application/json">'
        f"{safe_json_embed(adv_specs)}</script>\n"
        "</div>"
    )


def render_cacaosim_launcher_section(defaults: dict[str, str]) -> str:
    """Render Section 2: Launching cacaosim & SHM I/O table."""
    ov_v = html.escape(defaults["oversample"], quote=False)
    seeing_v = html.escape(defaults["seeing"], quote=False)
    bmode = html.escape(defaults["bench_mode"], quote=False)
    return (
        '<h2 id="launching-cacaosim">2. Launching <code>cacaosim</code> for This Configuration '
        f"{render_section_badges(['simulation'])}</h2>\n"
        "<p>Always isolate shared memory under <code>/dev/shm/cacao_*</code> so "
        "<code>/milk/shm</code> remains untouched. Inspect or launch the declarative optical "
        "bench <code>benches/ao3k_scexao/ao3k_scexao.bench</code> as follows:</p>\n"
        "<pre><code>source env.sh\n"
        "export MILK_SHM_DIR=/dev/shm/cacao_demo MILK_PROC_DIR=/dev/shm/cacao_demo/proc\n"
        'mkdir -p "${MILK_PROC_DIR}"\n\n'
        "# Inspect schematic in terminal or launch interactive cacaosim-CTRL GUI\n"
        "cacaosim-bench view -c benches/ao3k_scexao/ao3k_scexao.bench\n"
        "cacaosim-bench gui  -c benches/ao3k_scexao/ao3k_scexao.bench\n\n"
        "# Deploy optical bench with zero turbulence first for response-matrix calibration\n"
        f"cacaosim-bench deploy -c benches/ao3k_scexao/ao3k_scexao.bench "
        f"--mode {bmode} --oversample {ov_v} --atmturb --seeing {seeing_v}\n"
        'milk-fps-set "csim_htsim.turb_gain=0.0"  # Toggle to 1.0 after calibration</code></pre>\n'
        '<div class="table-wrap" data-sortable="1"><table><thead><tr>'
        "<th>Direction</th><th>Category</th><th>SHM Stream(s)</th>"
        "<th>Grid / Rate</th><th>Description</th>"
        "</tr></thead><tbody>"
        '<tr class="cat-row cat-simulation"><td>Input</td>'
        f'<td>{render_cat_badge("simulation")}</td>'
        "<td><code>outarraypha</code></td><td>256x256 @ 2 kHz</td>"
        "<td>Atmospheric phase screen from <code>csim_atmturb</code></td></tr>"
        '<tr class="cat-row cat-loop_operation"><td>Input</td>'
        f'<td>{render_cat_badge("loop_operation")}</td>'
        "<td><code>dm01disp</code>, <code>dm02disp</code></td>"
        "<td>64x64 / 50x50</td><td>Stage-1 &amp; Stage-2 DM surface actuators</td></tr>"
        '<tr class="cat-row cat-simulation"><td>Output (WFS)</td>'
        f'<td>{render_cat_badge("simulation")}</td>'
        "<td><code>csim_wfs_nir</code>, <code>csim_wfs_vis</code>, "
        "<code>csim_wfs_lowfs</code></td><td>160x160 / 120x120 / 64x64</td>"
        "<td>Polychromatic Stage 1/2/3 wavefront sensor frames</td></tr>"
        '<tr class="cat-row cat-analysis"><td>Output (Sci)</td>'
        f'<td>{render_cat_badge("analysis")}</td>'
        "<td><code>psf_vis_*</code>, <code>psf_nir_*</code>, "
        "<code>coro_pre_lyot</code></td><td>256x256</td>"
        "<td>Short/long-exposure Visible, H-band, and Lyot coronagraph cameras</td></tr>"
        "</tbody></table></div>"
    )


def render_deployment_checklist_section(
    defaults: dict[str, str],
    *,
    pc_on: bool,
    c2d_on: bool,
) -> str:
    """Render Section 4: 8-step deployment checklist."""
    ov_v = defaults["oversample"]
    pf_step = (
        f"CACAO_PF_MODE={defaults['pf_mode']} CACAO_PF_ORDER={defaults['pf_order']} "
        "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 testol\n"
        f"CACAO_PF_MODE={defaults['pf_mode']} CACAO_PF_ORDER={defaults['pf_order']} "
        "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 pf-on 0.90"
        if pc_on
        else "# Predictive control optional: --stage 1 testol && --stage 1 pf-on 0.90"
    )
    steps: list[tuple[str, str, str, tuple[str, ...]]] = [
        (
            "Step 1: Initialize Isolated SHM Sandbox & Environment",
            "source env.sh\nexport MILK_SHM_DIR=/dev/shm/cacao_run\n"
            'export MILK_PROC_DIR=/dev/shm/cacao_run/proc\nmkdir -p "${MILK_PROC_DIR}"',
            "simulation",
            ("simulation", "loop_operation"),
        ),
        (
            "Step 2: Launch cacaosim Optical Bench (Zero Turbulence for Calibration)",
            f"cacaosim-bench deploy -c benches/ao3k_scexao/ao3k_scexao.bench "
            f"--mode {defaults['bench_mode']} --oversample {ov_v} --atmturb\n"
            'milk-fps-set "csim_htsim.turb_gain=0.0"',
            "simulation",
            ("simulation",),
        ),
        (
            "Step 3: Deploy CACAO Loop Compute Units (Stage 1, Stage 2 + ZPO, Stage 3)",
            "CACAO_LOOPROOTDIR=/tmp/ao3k ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 1 deploy\n"
            "CACAO_LOOPROOTDIR=/tmp/scexao ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 2 deploy\n"
            "CACAO_LOOPROOTDIR=/tmp/llowfs ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 3 deploy",
            "loop_operation",
            ("loop_operation",),
        ),
        (
            "Step 4: Measure Latency (mlat), Acquire Hadamard RM & Solve SVD Control Matrix",
            "CACAO_LOOPROOTDIR=/tmp/ao3k ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 1 calibrate --save-rm _work/ao3k_scexao_rm/stage1\n"
            "CACAO_LOOPROOTDIR=/tmp/scexao ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 2 calibrate --save-rm _work/ao3k_scexao_rm/stage2\n"
            "CACAO_LOOPROOTDIR=/tmp/llowfs ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage 3 calibrate --save-rm _work/ao3k_scexao_rm/stage3",
            "calibration",
            ("calibration",),
        ),
        (
            "Step 5: Calibrate PSOL Latency (testOL) & Enable Predictive Filtering",
            pf_step,
            "calibration",
            ("calibration", "loop_operation"),
        ),
        (
            "Step 6: Ramp Atmospheric Turbulence & Close Loops Sequentially (1 -> 2 -> 3)",
            'milk-fps-set "csim_htsim.turb_gain=1.0"\n'
            "CACAO_LOOPROOTDIR=/tmp/ao3k ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            f"--stage 1 close {defaults['gain1']}\n"
            "CACAO_LOOPROOTDIR=/tmp/scexao ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            f"--stage 2 close {defaults['gain2']}\n"
            + (
                "CACAO_LOOPROOTDIR=/tmp/llowfs ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
                f"--stage 3 close {defaults['gain3']}"
                if defaults["llowfs"] == "closed"
                else "# Stage 3 LLOWFS remains OPEN for this configuration"
            ),
            "loop_operation",
            ("loop_operation", "simulation"),
        ),
        (
            "Step 7: Inspect Live TUIs & Record Telemetry / 2-WFS+1-DM Calibration",
            "milk-fpsCTRL        # Inspect & tune all FPS parameters live\n"
            "cacao-modalstatsTUI 1   # Inspect Stage-1 modal residuals\n"
            + (
                "milk-mlt-calib2wfs1dm ... # Probe-free Mab/Mdb/Mda_virt system ID"
                if c2d_on
                else "milk-stream-wait -t 10 psf_nir_final+100"
            ),
            "analysis",
            ("analysis", "calibration") if c2d_on else ("analysis",),
        ),
        (
            "Step 8: Safe Open, Zero DMs & Clean Teardown",
            "for s in 3 2 1; do ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage ${s} open; done\n"
            "for s in 3 2 1; do ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk "
            "--stage ${s} teardown --purge-dm; done\n"
            "cacaosim-bench teardown",
            "loop_operation",
            ("loop_operation", "simulation"),
        ),
    ]
    low_level_step3 = (
        '<details style="margin-top:0.45rem;"><summary><strong>Show low-level '
        "<code>milk-fps-init</code> / <code>milk-fps-set</code> / <code>milk-stream-link</code> "
        "primitives (Stage 1 example)</strong></summary>"
        "<pre><code>milk-fps-init DMch2disp-01 cacao-fpsexec-dmcomb\n"
        "milk-fps-init acquWFS-1    cacao-fpsexec-cacaoiot-acquireWFS\n"
        "milk-fps-init wfs2cmodeval-1 milk-fpsexec-linalg-MVMextract\n"
        "milk-fps-init mfilt-1      cacao-fpsexec-mfilt\n"
        "milk-fps-init mvalC2dm-1   milk-fpsexec-linalg-MVMextract\n"
        "milk-stream-link csim_wfs_nir=aol1_wfsim\n"
        "milk-fps-set acquWFS-1.insname=aol1_wfsim mfilt-1.loopgain="
        f"{html.escape(defaults['gain1'], quote=False)} mfilt-1.comp.OLmodes=ON\n"
        "milk-fps-runstart DMch2disp-01 acquWFS-1 wfs2cmodeval-1 mfilt-1 mvalC2dm-1"
        "</code></pre></details>"
    )
    chk_items = "".join(
        f'<div class="checklist-item cat-{pcat}">'
        f'<label class="checklist-hdr"><input type="checkbox" class="deploy-step-cb"> '
        f"<span>{html.escape(stitle, quote=False)}</span> "
        f'{"".join(render_cat_badge(b) for b in b_cats)}</label>'
        f"<pre><code>{html.escape(scmd, quote=False)}</code></pre>"
        f"{low_level_step3 if idx == 2 else ''}"
        "</div>"
        for idx, (stitle, scmd, pcat, b_cats) in enumerate(steps)
    )
    return (
        '<h2 id="step-by-step-deployment">4. Step-by-Step Deployment Checklist</h2>\n'
        '<div class="toolbar">'
        '<span id="deploy-progress-text"><strong>0 / 8 steps completed</strong></span>'
        '<div class="progress-track"><div class="progress-fill" id="deploy-progress-fill" '
        'style="width:0%"></div></div></div>\n'
        f'<div class="checklist">{chk_items}</div>'
    )


def render_real_hardware_section() -> str:
    """Render Section 5: Adapting This Configuration to Real Hardware."""
    return (
        '<h2 id="adapting-to-real-hardware">5. Adapting This Configuration to Real Hardware</h2>\n'
        "<ul>\n"
        f'<li>{render_cat_badge("simulation")} <strong>Swap WFS &amp; DM streams</strong>: '
        "Replace <code>csim_wfs_*</code> with your camera frame-grabber SHM streams via "
        "<code>CACAO_WFSSTREAM=&lt;cam_shm&gt;</code>, and replace simulated DM channels with "
        "your physical DM driver reading <code>dm01disp</code> / <code>dm02disp</code>.</li>\n"
        f'<li>{render_cat_badge("loop_operation")} <strong>GPU &amp; NUMA pinning</strong>: '
        "Keep <code>wfs2cmodeval-*</code>, <code>mvalC2dm-*</code>, and <code>zpo-2</code> on "
        "the same NUMA node as the CUDA GPU (<code>MILK_NUMANODE=auto</code>) and disable unused "
        "monitor SHM streams to save memory bandwidth.</li>\n"
        f'<li>{render_cat_badge("calibration")} {render_cat_badge("loop_operation")} '
        "<strong>Tune key loop parameters</strong>: Start conservatively with "
        "<code>svdlim=0.004</code> and <code>gain=0.30..0.35</code>, measure on-sky "
        "<code>selfRM</code> optical gain, then enable <code>--predictive --pf-mode ar "
        "--pf-order 16</code> (or <code>Block-EOF</code> after 12 s of stationary sky).</li>\n"
        "</ul>"
    )
