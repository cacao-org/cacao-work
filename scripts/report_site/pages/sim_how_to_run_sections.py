#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Section helpers for Simulation How-to-Run page (customizer, checklist, hardware)."""

from __future__ import annotations

import html

from ..constants import COMPUTE_CATEGORY_ORDER
from .fragments import render_cat_badge, render_section_badges, safe_json_embed


def render_customizer_section(raw_cmd: str, defaults: dict[str, str]) -> str:
    """Render Section 1: Turnkey Command & Interactive Parameter Customizer."""
    cmd_badges_all = render_section_badges(COMPUTE_CATEGORY_ORDER)
    cmd_badges_sim = render_section_badges(["simulation"])
    cmd_badges_loop = render_section_badges(["calibration", "loop_operation"])
    return (
        '<h2 id="interactive-command-customizer">'
        "1. Turnkey Command &amp; Interactive Parameter Customizer</h2>\n"
        "<p>Pre-loaded with this simulation's exact parameters. Adjust any field below to "
        "generate custom commands for <code>run-ao3k-scexao.sh</code>, "
        "<code>cacaosim-bench</code>, and <code>cacaoloop-ao3k-scexao.milk</code>:</p>\n"
        '<div class="explorer-panel">\n'
        '<div class="customizer-grid">\n'
        '<div class="field-box"><label for="cust-seeing">Seeing [arcsec]</label>'
        '<input id="cust-seeing" type="number" step="0.05" min="0.2" max="2.0"></div>\n'
        '<div class="field-box"><label for="cust-phys_time">Phys Time [s]</label>'
        '<input id="cust-phys_time" type="number" step="0.5" min="0.5" max="60"></div>\n'
        '<div class="field-box"><label for="cust-bench_mode">cacaosim Mode</label>'
        '<select id="cust-bench_mode"><option value="fused">fused (csim_htsim)</option>'
        '<option value="modular">modular (per-element FPS)</option></select></div>\n'
        '<div class="field-box"><label for="cust-oversample">Oversample K</label>'
        '<select id="cust-oversample"><option value="1">1x (2 kHz)</option>'
        '<option value="2">2x (4 kHz)</option><option value="4">4x (8 kHz)</option>'
        "</select></div>\n"
        '<div class="field-box"><label for="cust-gain1">Stage-1 Gain</label>'
        '<input id="cust-gain1" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        '<div class="field-box"><label for="cust-gain2">Stage-2 Gain</label>'
        '<input id="cust-gain2" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        '<div class="field-box"><label for="cust-gain3">Stage-3 Gain</label>'
        '<input id="cust-gain3" type="number" step="0.05" min="0.0" max="1.0"></div>\n'
        '<div class="field-box"><label for="cust-llowfs">Stage-3 LLOWFS</label>'
        '<select id="cust-llowfs"><option value="closed">CLOSED</option>'
        '<option value="open">OPEN (--no-lowfs)</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_mode">Predictive Control</label>'
        '<select id="cust-pf_mode"><option value="off">OFF (Integrator)</option>'
        '<option value="ar">PSOL Diagonal AR(P)</option>'
        '<option value="eof">PSOL Cross-Mode Block-EOF</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_order">PF Order P</label>'
        '<select id="cust-pf_order"><option value="4">4</option><option value="8">8</option>'
        '<option value="16">16</option><option value="32">32</option>'
        '<option value="64">64</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_blocksize">EOF Block Size B</label>'
        '<select id="cust-pf_blocksize"><option value="64">64</option>'
        '<option value="128">128</option></select></div>\n'
        '<div class="field-box"><label for="cust-pf_reg">PF Reg lambda</label>'
        '<input id="cust-pf_reg" type="text"></div>\n'
        '<div class="field-box"><label for="cust-calib_2wfs1dm">2-WFS/1-DM Calib</label>'
        '<select id="cust-calib_2wfs1dm"><option value="off">OFF</option>'
        '<option value="on">ON (--calib-2wfs1dm)</option></select></div>\n'
        '<div class="field-box"><label for="cust-telemetry">Telemetry Mode</label>'
        '<select id="cust-telemetry"><option value="none">none</option>'
        '<option value="standard">standard</option>'
        '<option value="speckle">speckle</option>'
        '<option value="truth">truth</option></select></div>\n'
        "</div>\n"
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
