# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Verify pure-stdlib AO Markdown-to-HTML web report builder and staging script."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _create_synthetic_report(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    for png_name in (
        "cacaosim_gui_schematic.png",
        "cacaosim_gui_builder.png",
        "cacaosim_gui_tables.png",
        "cacaosim_gui_status.png",
        "chromatic_passbands_2x1.png",
        "psf_comparison_2x3.png",
        "wf_strehl_timeseries_4x1.png",
        "psf_inst_vis_5x3.png",
        "dm_samples_5x4.png",
        "wfs_samples_5x4.png",
        "wfs_psf_short_evolution_poster.png",
        "compute_timeline_4x1.png",
        "extra_wf_samples_5x3.png",
    ):
        (report_dir / png_name).write_bytes(TINY_PNG)
    (report_dir / "wfs_psf_short_evolution.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (report_dir / "wfs_psf_short_evolution_meta.json").write_text(
        '{"video_file": "wfs_psf_short_evolution.mp4"}\n', encoding="utf-8"
    )
    (report_dir / "ao3k_scexao.bench").write_text(
        '[bench]\nname = "subaru_ao3k_scexao"\n', encoding="utf-8"
    )
    (report_dir / "ao3k_scexao_metrics.json").write_text(
        json.dumps(
            {
                "star_and_atmosphere": {
                    "seeing_arcsec_500nm": 0.60,
                    "internal_bench_hz": 8000.0,
                    "internal_dt_us": 125.0,
                    "physical_time_s": 10.0,
                },
                "psf_metrics": {
                    "vis": {"final": {"strehl_peak": 0.828}},
                    "nir": {"final": {"strehl_peak": 0.953}},
                },
                "wavefront_metrics": {
                    "locations": {"final": {"quad_total_rms_nm": 50.1}}
                },
                "reproducibility": {
                    "bench_file": "ao3k_scexao.bench",
                    "metrics_file": "ao3k_scexao_metrics.json",
                    "run_command": "./scripts/run-ao3k-scexao.sh --save-telemetry speckle",
                    "repositories": [
                        {
                            "name": "cacao-work",
                            "url": "https://github.com/cacao-org/cacao-work",
                            "branch": "main",
                            "commit": "1111111222222233333334444444555555566666",
                            "short_commit": "1111111",
                            "role": "Integration workspace & web report builder",
                        },
                        {
                            "name": "milk",
                            "url": "https://github.com/milk-org/milk",
                            "branch": "feat/bash-engine",
                            "commit": "abcdef0123456789abcdef0123456789abcdef01",
                            "short_commit": "abcdef0",
                            "role": "Core FPS shared-memory engine",
                        },
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "metrics.json").write_text('{"strehl": 0.36}\n', encoding="utf-8")
    (report_dir / "wf_timeseries.csv").write_text(
        "frame,t_phys_s,rms_raw_nm,rms_stg1_nm,rms_final_nm\n1,0.0005,900.0,300.0,150.0\n",
        encoding="utf-8",
    )
    (report_dir / "strehl_timeseries.csv").write_text(
        "exposure,frame,t_phys_s,vis_final_inst,vis_final_long\n1,20,0.0100,0.35,0.35\n",
        encoding="utf-8",
    )
    (report_dir / "cube.fits").write_bytes(b"SIMPLE  =                    T")

    report_md = "\n".join(
        [
            "# Synthetic AO Simulation Report",
            "",
            "- **Seeing**: `0.60\"` at 0.50 um | **Star**: mV=6.0, mH=6.0",
            "- **Internal Optical-Bench Clock**: **`8.0 kHz` (`dt = 0.125 ms = 125 us`), "
            "i.e., `4` sub-samples per `0.50 ms` (`2.0 kHz`) outer tick**",
            "- Code ref: `csim_htsim` and `b_post_stg1` stay literal",
            "",
            "> Companion report: [COMPUTE_REPORT.md](COMPUTE_REPORT.md)",
            "",
            "## Optical Bench & Hardware Configuration (`cacaosim-CTRL`)",
            "",
            "- **Declarative Bench**: [ao3k_scexao.bench](ao3k_scexao.bench)",
            "- **Views**: [Hardware Simulator GUI (`cacaosim-CTRL`)]"
            "(#hardware-simulator-gui-cacaosim-ctrl)",
            "",
            "![cacaosim-CTRL 2D Optical Bench Schematic](cacaosim_gui_schematic.png)",
            "",
            "### Internal Multi-Rate Timing & Sub-Stepping (`8.0 kHz` / `125 us`)",
            "",
            "> **Internal Timing Architecture**: `8.0 kHz` (`dt = 0.125 ms = 125 us`), "
            "`4` sub-samples per `0.50 ms` (`2.0 kHz`) outer tick.",
            "",
            "## Polychromatic Passbands, Sub-Band Sampling & Flux Scaling",
            "",
            "| Sensor | Bandpass [um] | Slices `N` |",
            "| :--- | :---: | ---: |",
            "| `wfs_nir` | 1.098-1.342 (`20%`) | 2 |",
            "",
            "![Optical Bench 32-Bin Spectra](chromatic_passbands_2x1.png)",
            "",
            "## Long-Exposure PSF Summary",
            "",
            "| Band | Strehl | Mode |",
            "| :--- | ---: | :---: |",
            "| Vis | 36.1% | `aol2_imWFS2` |",
            "",
            "```mermaid",
            "flowchart LR",
            "    ATM --> DM1",
            "```",
            "",
            "## Figures",
            "",
            "### Hardware Simulator GUI (cacaosim-CTRL)",
            "",
            "- ![cacaosim-CTRL Builder](cacaosim_gui_builder.png)",
            "- ![cacaosim-CTRL Tables](cacaosim_gui_tables.png)",
            "- ![cacaosim-CTRL Status](cacaosim_gui_status.png)",
            "",
            "### Time-Series & Sampled Instant Snapshots",
            "",
            "- ![PSF Comparison](psf_comparison_2x3.png)",
            "- ![Wavefront Error & Strehl Time Series](wf_strehl_timeseries_4x1.png)",
            "- ![Instantaneous Visible PSFs](psf_inst_vis_5x3.png)",
            "- ![Instantaneous DM Samples](dm_samples_5x4.png)",
            "- ![Instantaneous WFS Samples](wfs_samples_5x4.png)",
            "",
            "![Short-Timescale WFS & PSF Evolution](wfs_psf_short_evolution.mp4)",
            "",
            "- [metrics.json](metrics.json)",
            "- [wf_timeseries.csv](wf_timeseries.csv)",
            "- [strehl_timeseries.csv](strehl_timeseries.csv)",
            "- [cube.fits](cube.fits)",
            "- [rm_dir](../ao3k_scexao_rm)",
            "",
            "## Reproducibility & GitHub Provenance",
            "",
            "- [cacao-work](https://github.com/cacao-org/cacao-work) "
            "([`1111111`](https://github.com/cacao-org/cacao-work/commit/"
            "1111111222222233333334444444555555566666))",
        ]
    )
    compute_md = "\n".join(
        [
            "# Compute Performance Report",
            "",
            "> Optical report: [REPORT.md](REPORT.md)",
            "",
            "![Compute Timeline](compute_timeline_4x1.png)",
        ]
    )
    (report_dir / "REPORT.md").write_text(report_md + "\n", encoding="utf-8")
    (report_dir / "COMPUTE_REPORT.md").write_text(compute_md + "\n", encoding="utf-8")


def test_build_ao_web_report_markdown_and_staging(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify GFM tables, inline tokens, companion links, extra PNGs, and FITS filter."""
    report_dir = tmp_path / "demo_run"
    site_dir = tmp_path / "web_site"
    _create_synthetic_report(report_dir)

    script = repo_root / "scripts" / "build-ao-web-report.py"
    res = subprocess.run(
        [
            sys.executable,
            str(script),
            "--report-dir",
            str(report_dir),
            "--site-dir",
            str(site_dir),
            "--slug",
            "demo_run",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr + res.stdout

    slug_out = site_dir / "public" / "demo_run"
    index_html = (slug_out / "index.html").read_text(encoding="utf-8")
    config_html = (slug_out / "config.html").read_text(encoding="utf-8")
    optical_html = (slug_out / "optical.html").read_text(encoding="utf-8")
    runtime_html = (slug_out / "runtime.html").read_text(encoding="utf-8")
    compute_html = (slug_out / "compute_report.html").read_text(encoding="utf-8")
    how_html = (slug_out / "how_to_run.html").read_text(encoding="utf-8")

    # All 5 simulation views exist cleanly.
    assert runtime_html == compute_html
    for sub in ("config.html", "optical.html", "runtime.html", "how_to_run.html"):
        assert f'href="{sub}"' in index_html

    # Preamble bullet list stays on index.html; GFM tables & optical tokens on optical/config.
    assert "<ul>" in index_html
    assert "<strong>Seeing</strong>:" in index_html
    assert "<strong>Internal Optical-Bench Clock</strong>:" in index_html
    assert "<code>8.0 kHz</code>" in index_html
    assert "<code>dt = 0.125 ms = 125 us</code>" in index_html
    assert "<code>csim_htsim</code>" in index_html
    assert "<code>b_post_stg1</code>" in index_html
    assert 'style="text-align: left;"' in optical_html
    assert 'style="text-align: right;"' in optical_html
    assert 'style="text-align: center;"' in optical_html
    assert "<code>aol2_imWFS2</code>" in optical_html

    # Configuration sub-page has GUI screenshots (tabbed, no duplicate), passbands, & .bench.
    assert 'src="cacaosim_gui_schematic.png"' in config_html
    assert config_html.count("cacaosim_gui_builder.png") == 2
    assert 'src="cacaosim_gui_builder.png"' in config_html
    assert 'src="cacaosim_gui_tables.png"' in config_html
    assert 'src="cacaosim_gui_status.png"' in config_html
    assert 'src="chromatic_passbands_2x1.png"' in config_html
    assert "<code>wfs_nir</code>" in config_html
    assert 'id="hardware-simulator-gui-cacaosim-ctrl"' in config_html
    assert 'href="#hardware-simulator-gui-cacaosim-ctrl"' in config_html
    assert 'href="ao3k_scexao.bench"' in config_html
    assert 'id="bench-card-grid"' in config_html
    assert "subaru_ao3k_scexao" in config_html
    assert (slug_out / "ao3k_scexao.bench").is_file()

    # Optical Performance sub-page has interactive explorer, optical figures, video, & Mermaid.
    assert 'id="optical-explorer-data"' in optical_html
    assert 'src="psf_comparison_2x3.png"' in optical_html
    assert 'src="wf_strehl_timeseries_4x1.png"' in optical_html
    assert 'src="psf_inst_vis_5x3.png"' in optical_html
    assert 'src="dm_samples_5x4.png"' in optical_html
    assert 'src="wfs_samples_5x4.png"' in optical_html
    assert "<em>" not in optical_html
    assert '<div class="figure-stack">' in optical_html
    assert "<li><img" not in optical_html
    assert '<pre class="mermaid">' in optical_html
    assert "mermaid.esm.min.mjs" in optical_html
    assert "mermaid.esm.min.mjs" not in compute_html

    # Bidirectional report link rewriting maps REPORT.md -> optical.html & COMPUTE -> runtime.html.
    assert 'href="runtime.html"' in index_html
    assert 'href="optical.html"' in compute_html

    # Extra optical PNG appears on optical.html; GUI, compute, & video poster NOT duplicated.
    assert 'src="extra_wf_samples_5x3.png"' in optical_html
    assert "Additional Diagnostic Figures" in optical_html
    assert 'src="compute_timeline_4x1.png"' in compute_html
    assert 'src="compute_timeline_4x1.png"' not in optical_html
    assert 'src="cacaosim_gui_builder.png"' not in optical_html
    assert "<video controls loop autoplay muted playsinline" in optical_html
    assert 'poster="wfs_psf_short_evolution_poster.png"' in optical_html
    assert '<source src="wfs_psf_short_evolution.mp4" type="video/mp4">' in optical_html
    assert 'src="wfs_psf_short_evolution_poster.png"' not in optical_html
    assert (slug_out / "wfs_psf_short_evolution.mp4").is_file()
    assert 'href="wfs_psf_short_evolution_meta.json"' not in index_html

    # Excluded .fits and external ../ paths do not produce broken <a href> links.
    assert not (slug_out / "cube.fits").exists()
    assert 'href="cube.fits"' not in index_html
    assert 'href="../ao3k_scexao_rm"' not in optical_html
    assert 'href="metrics.json"' in index_html
    assert 'href="wf_timeseries.csv"' in index_html
    assert 'href="strehl_timeseries.csv"' in index_html
    assert "(local artifact, omitted from web bundle)" in optical_html

    # How-to-Run page includes cacaosim launcher, CACAO compute units, checklist, & provenance.
    assert 'id="howtorun-defaults"' in how_html
    assert "cacaosim-bench deploy" in how_html
    assert 'id="compute-units-table"' in how_html
    assert "csim_htsim" in how_html
    assert "DMch2disp-01" in how_html
    assert "acquWFS-1" in how_html
    assert "mfilt-1" in how_html
    assert "deploy-step-cb" in how_html
    assert 'id="reproducibility-github-provenance"' in how_html
    assert (
        'href="https://github.com/cacao-org/cacao-work/commit/'
        '1111111222222233333334444444555555566666"'
    ) in how_html
    tokens_css = (site_dir / "public" / "assets" / "css" / "tokens.css").read_text(encoding="utf-8")
    assert 'href="../index.html">Home</a>' in how_html
    assert 'href="../assets/css/tokens.css"' in how_html
    assert "<style" not in how_html
    for cat_key in ("simulation", "calibration", "loop_operation", "analysis"):
        assert f"--cat-{cat_key}:" in tokens_css
        assert f'data-cu-cat="{cat_key}"' in how_html
        assert f"classDef cat_{cat_key} " in how_html
        assert f"classDef cat_{cat_key} " in index_html
    assert 'aria-pressed="true"' in how_html
    assert 'data-cu-action="all"' in how_html
    assert 'data-cu-action="none"' in how_html
    assert 'id="cu-visible-count"' in how_html
    assert 'id="cu-empty-msg"' in how_html
    pos_sim = how_html.index('<tbody class="cat-tbody cat-simulation"')
    pos_cal = how_html.index('<tbody class="cat-tbody cat-calibration"')
    pos_loop = how_html.index('<tbody class="cat-tbody cat-loop_operation"')
    pos_ana = how_html.index('<tbody class="cat-tbody cat-analysis"')
    assert pos_sim < pos_cal < pos_loop < pos_ana
    assert "2. Launching cacaosim for This Configuration</a>" in how_html
    assert "1. Step-by-Step" not in how_html
    assert "class=\"checklist-item cat-calibration\"" in how_html
    assert "class=\"checklist-item cat-analysis\"" in how_html

    # Root Executive Hub is served directly at / while simulations live under /simulations/
    # and the open-source stack & reproduction recipe live under /stack/.
    fb_cfg = json.loads((site_dir / "firebase.json").read_text(encoding="utf-8"))
    assert "redirects" not in fb_cfg["hosting"]
    assert "mp4" in fb_cfg["hosting"]["headers"][0]["source"]
    assert "css" in fb_cfg["hosting"]["headers"][1]["source"]
    assert "js" in fb_cfg["hosting"]["headers"][1]["source"]

    front_html = (site_dir / "public" / "index.html").read_text(encoding="utf-8")
    reports_html = (site_dir / "public" / "reports.html").read_text(encoding="utf-8")
    assert front_html == reports_html
    assert 'id="tech-reports-table"' in front_html
    assert "Knowledge Repository" in front_html
    assert 'id="quick-guide"' in front_html
    assert "Quick Guide" in front_html
    assert 'class="domain-card domain-wavefront-control"' in front_html
    assert 'href="./simulations/index.html"' in front_html
    assert 'href="./stack/index.html"' in front_html
    assert 'data-rel-root="."' in front_html

    sims_html = (site_dir / "public" / "simulations" / "index.html").read_text(encoding="utf-8")
    assert 'id="sim-reports-table"' in sims_html
    assert "82.8%" in sims_html
    assert "95.3%" in sims_html
    assert "../demo_run/config.html" in sims_html
    assert "../demo_run/optical.html" in sims_html
    assert "../demo_run/runtime.html" in sims_html
    assert "../demo_run/how_to_run.html" in sims_html
    assert 'class="sim-filter-panel"' in sims_html
    assert 'class="filter-cat-box cat-loop_operation"' in sims_html
    assert 'class="filter-cat-box cat-calibration"' in sims_html
    for ck in ("integrator", "ar", "eof"):
        assert f'data-sim-ctrl="{ck}"' in sims_html
    assert 'data-sim-tri="llowfs"' in sims_html
    assert 'data-sim-tri="calib2wfs"' in sims_html
    assert 'data-val="any"' in sims_html
    assert 'data-val="on"' in sims_html
    assert 'data-val="off"' in sims_html
    assert 'data-ctrl="' in sims_html
    assert 'data-llowfs="' in sims_html
    assert 'data-calib2wfs="' in sims_html
    assert 'id="sim-filter-reset"' in sims_html
    assert 'id="sim-empty-msg"' in sims_html
    assert 'class="nav-drop-menu"' in sims_html

    stack_html = (site_dir / "public" / "stack" / "index.html").read_text(encoding="utf-8")
    assert "https://github.com/cacao-org/cacao-work" in stack_html
    assert "https://github.com/milk-org/milk" in stack_html
    assert "git -C milk submodule update --init src/engine/ImageStreamIO" in stack_html
    assert "./scripts/build-all.sh" in stack_html
    assert "./scripts/run-ao3k-scexao.sh --save-telemetry speckle" in stack_html


def test_publish_ao_report_build_only_and_include_fits(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify publish-ao-report.sh --build-only, --include-fits, and multi-slug index."""
    rep_a = tmp_path / "run_a"
    rep_b = tmp_path / "run_b"
    site_dir = tmp_path / "web_site"
    _create_synthetic_report(rep_a)
    _create_synthetic_report(rep_b)

    pub_sh = str(repo_root / "scripts" / "publish-ao-report.sh")
    res1 = subprocess.run(
        [
            pub_sh,
            "--build-only",
            "--include-fits",
            "--site-dir",
            str(site_dir),
            str(rep_a),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res1.returncode == 0, res1.stderr + res1.stdout
    assert (site_dir / "public" / "run_a" / "cube.fits").is_file()
    index_a = (site_dir / "public" / "run_a" / "index.html").read_text(encoding="utf-8")
    assert 'href="cube.fits"' in index_a

    # Adding a second slug removes the single-slug "/" redirect and serves reports index.
    res2 = subprocess.run(
        [pub_sh, "--build-only", "--site-dir", str(site_dir), str(rep_b)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res2.returncode == 0, res2.stderr + res2.stdout
    fb_cfg = json.loads((site_dir / "firebase.json").read_text(encoding="utf-8"))
    assert "redirects" not in fb_cfg["hosting"]
    root_idx = (site_dir / "public" / "index.html").read_text(encoding="utf-8")
    assert "run_a" in root_idx and "run_b" in root_idx


def test_publish_ao_report_requires_project_without_build_only(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify publish-ao-report.sh exits 2 when no --project, env, or .firebaserc exists."""
    rep_dir = tmp_path / "run_req"
    site_dir = tmp_path / "fresh_site"
    _create_synthetic_report(rep_dir)

    env = os.environ.copy()
    env.pop("FIREBASE_PROJECT", None)
    pub_sh = str(repo_root / "scripts" / "publish-ao-report.sh")
    res = subprocess.run(
        [pub_sh, "--site-dir", str(site_dir), str(rep_dir)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 2
    assert "specify --project <gcp-project> or set FIREBASE_PROJECT" in res.stderr


def test_cacaosim_telemetry_video_renderer(
    stack_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """Verify cacaosim-telemetry-video slices synthetic FITS cubes into a valid H.264 MP4."""
    import numpy as np
    from astropy.io import fits

    rep_dir = tmp_path / "ao_out"
    tlm_dir = rep_dir / "telemetry"
    tlm_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    yy, xx = np.indices((64, 64), dtype=np.float32)
    dl_psf = np.exp(-((xx - 32.0) ** 2 + (yy - 32.0) ** 2) / (2.0 * 1.8**2)).astype(np.float32)
    for bkey in ("vis", "nir"):
        fits.writeto(rep_dir / f"psf_{bkey}_dl.fits", dl_psf, overwrite=True)
        for skey in ("stg1", "final"):
            fits.writeto(
                rep_dir / f"det_{bkey}_{skey}_dl.fits",
                100.0 + 5000.0 * dl_psf,
                overwrite=True,
            )

    wf_rows = ["frame,t_phys_s,rms_raw_nm,rms_stg1_nm,rms_final_nm"]
    for i in range(1, 21):
        wf_rows.append(f"{i},{i*0.0005:.6f},850.0,190.0,85.0")
    (rep_dir / "wf_timeseries.csv").write_text("\n".join(wf_rows) + "\n", encoding="utf-8")
    (rep_dir / "ao3k_scexao.bench").write_text(
        "[bench]\nmaster_hz = 2000.0\noversample = 4\n", encoding="utf-8"
    )
    (tlm_dir / "telemetry_manifest.json").write_text(
        json.dumps(
            {
                "mode": "speckle",
                "seeing_arcsec": 0.6,
                "phys_time_s": 0.010,
                "master_ticks": 20,
                "psf_navg": 1,
                "fs_stg1_hz": 1000.0,
                "fs_stg2_hz": 2000.0,
            }
        ),
        encoding="utf-8",
    )

    def write_stream(name: str, nfr: int, ny: int, nx: int, base: float, scale: float) -> None:
        cube = (base + scale * rng.random((nfr, ny, nx), dtype=np.float32)).astype(np.float32)
        fits.writeto(tlm_dir / f"{name}_12:00:00.000000.fits", cube, overwrite=True)
        txt = [
            f"{k} {k} 12:00:00.000000 {1000.0 + k*1e-3:.9f} {1000.0 + k*1e-3:.9f} {100 + k} 0"
            for k in range(nfr)
        ]
        (tlm_dir / f"{name}_12:00:00.000000.txt").write_text(
            "\n".join(txt) + "\n", encoding="utf-8"
        )

    write_stream("csim_wfs_nir", 10, 40, 40, 100.0, 40.0)
    write_stream("csim_wfs_vis", 20, 32, 32, 100.0, 40.0)
    for bkey in ("vis", "nir"):
        for skey, sr in (("stg1", 0.25), ("final", 0.65)):
            pcube = np.empty((20, 64, 64), dtype=np.float32)
            for k in range(20):
                dx = 0.4 * np.sin(0.5 * k)
                sp = np.exp(-((xx - 32.0 - dx) ** 2 + (yy - 32.0) ** 2) / (2.0 * 1.9**2))
                pcube[k] = 100.0 + 5000.0 * sr * sp + 8.0 * rng.random((64, 64), dtype=np.float32)
            fits.writeto(
                tlm_dir / f"psf_{bkey}_{skey}_12:00:00.000000.fits", pcube, overwrite=True
            )
            txt = [
                f"{k} {k} 12:00:00.000000 {1000.0 + k*5e-4:.9f} {1000.0 + k*5e-4:.9f} {200 + k} 0"
                for k in range(20)
            ]
            (tlm_dir / f"psf_{bkey}_{skey}_12:00:00.000000.txt").write_text(
                "\n".join(txt) + "\n", encoding="utf-8"
            )

    out_mp4 = rep_dir / "wfs_psf_short_evolution.mp4"
    meta_out = rep_dir / "wfs_psf_short_evolution_meta.json"
    res = subprocess.run(
        [
            "cacaosim-telemetry-video",
            "--telemetry-dir",
            str(tlm_dir),
            "--report-dir",
            str(rep_dir),
            "--out",
            str(out_mp4),
            "--meta-out",
            str(meta_out),
            "--duration-ms",
            "8.0",
            "--fps",
            "10",
        ],
        env=stack_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    assert out_mp4.is_file() and out_mp4.stat().st_size > 1024
    assert (rep_dir / "wfs_psf_short_evolution_poster.png").is_file()
    vmeta = json.loads(meta_out.read_text(encoding="utf-8"))
    assert vmeta["n_frames"] >= 10
    assert vmeta["oversample"] == 4


def test_all_matrix_imshow_use_lower_origin(repo_root: Path) -> None:
    """Verify report plotters never use origin='upper' and always use origin='lower'."""
    import re

    targets = [
        repo_root / "scripts" / "build-calib-2wfs1dm-report.py",
        repo_root / "scripts" / "build-predictive-control-report.py",
        *sorted((repo_root / "scripts" / "studies").rglob("*.py")),
        repo_root.parent / "cacaosim" / "scripts" / "cacaosim-ao-report",
        repo_root.parent / "cacaosim" / "scripts" / "cacaosim-telemetry-video",
    ]
    for path in targets:
        if not path.is_file():
            continue
        txt = path.read_text(encoding="utf-8")
        assert 'origin="upper"' not in txt, f"Found origin='upper' in {path}"
        assert "origin='upper'" not in txt, f"Found origin='upper' in {path}"
        for m in re.finditer(r"\.imshow\(([^;]{0,300})", txt):
            snippet = m.group(1)
            assert 'origin="lower"' in snippet or "origin='lower'" in snippet, (
                f"imshow missing origin='lower' in {path}: {snippet[:80]}"
            )


def test_compute_unit_categories_and_multiselect(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify 4-category classification, grouping, colors, and multi-select pills."""
    scripts_dir = str(repo_root / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from report_site import COMPUTE_CATEGORY_ORDER
    from report_site.metrics import (
        build_compute_unit_catalog,
        classify_phase_category,
        classify_shm_category,
        classify_unit_category,
    )

    assert classify_unit_category("csim_atmturb") == "simulation"
    assert classify_unit_category("csim_htsim") == "simulation"
    assert classify_unit_category("milk-fpsexec-ca") == "simulation"
    assert classify_unit_category("mlat-1") == "calibration"
    assert classify_unit_category("compstrCM-2") == "calibration"
    assert classify_unit_category("mkEOFPF-1") == "calibration"
    assert classify_unit_category("DMch2disp-01") == "loop_operation"
    assert classify_unit_category("acquWFS-1") == "loop_operation"
    assert classify_unit_category("applyARPF-2") == "loop_operation"
    assert classify_unit_category("mctrlstats-1") == "analysis"
    assert classify_unit_category("tlog_00") == "analysis"

    assert classify_phase_category("deploy_bench") == "simulation"
    assert classify_phase_category("calib_stage1") == "calibration"
    assert classify_phase_category("closed_loop_10s") == "loop_operation"
    assert classify_phase_category("tlm_analysis") == "analysis"

    assert classify_shm_category("csim_wfs_nir_logbuff0") == "analysis"
    assert classify_shm_category("csim_wfs_nir") == "simulation"
    assert classify_shm_category("aol1_arPFmat") == "calibration"
    assert classify_shm_category("aol1_dmC") == "loop_operation"

    units = build_compute_unit_catalog({}, [], {}, {"telemetry": "speckle"})
    cat_ranks = [COMPUTE_CATEGORY_ORDER.index(str(u["category"])) for u in units]
    assert cat_ranks == sorted(cat_ranks)
    assert set(str(u["category"]) for u in units) == set(COMPUTE_CATEGORY_ORDER)

    report_dir = tmp_path / "rt_cat_run"
    site_dir = tmp_path / "rt_site"
    _create_synthetic_report(report_dir)
    (report_dir / "compute_perf_metrics.json").write_text(
        json.dumps(
            {
                "phases": [
                    {"id": "deploy_bench", "duration_s": 2.0, "gpu_util_mean_pct": 10.0},
                    {"id": "calib_stage1", "duration_s": 5.0, "gpu_util_mean_pct": 25.0},
                    {"id": "closed_loop_10s", "duration_s": 10.0, "gpu_util_mean_pct": 45.0},
                    {"id": "tlm_analysis", "duration_s": 3.0, "gpu_util_mean_pct": 5.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "compute_telemetry.json").write_text(
        json.dumps(
            {
                "processes": [
                    {"name": "csim_htsim", "cl_cpu_pct": 120.0, "gpu_vram_peak_mib": 512.0},
                    {"name": "compstrCM-1", "cl_cpu_pct": 15.0},
                    {"name": "acquWFS-1", "cl_cpu_pct": 42.0},
                    {"name": "mctrlstats-1", "cl_cpu_pct": 8.0},
                    {"name": "tlog_00", "cl_cpu_pct": 12.0},
                ],
                "streams": [
                    {"name": "csim_wfs_nir", "dims": [160, 160], "mean_hz": 1000.0},
                    {"name": "aol1_arPFmat", "dims": [1255, 16], "mean_hz": 1.0},
                    {"name": "aol1_dmC", "dims": [64, 64], "mean_hz": 1000.0},
                    {"name": "csim_wfs_nir_logbuff0", "dims": [160, 160, 100], "nb_readers": 1},
                ],
            }
        ),
        encoding="utf-8",
    )

    script = repo_root / "scripts" / "build-ao-web-report.py"
    res = subprocess.run(
        [
            sys.executable,
            str(script),
            "--report-dir",
            str(report_dir),
            "--site-dir",
            str(site_dir),
            "--slug",
            "rt_cat_run",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr + res.stdout

    slug_out = site_dir / "public" / "rt_cat_run"
    rt_html = (slug_out / "runtime.html").read_text(encoding="utf-8")
    how_html = (slug_out / "how_to_run.html").read_text(encoding="utf-8")

    assert "mermaid.esm.min.mjs" not in rt_html
    for cat_key in COMPUTE_CATEGORY_ORDER:
        assert f'data-rt-proc-cat="{cat_key}"' in rt_html
        assert f'data-rt-shm-cat="{cat_key}"' in rt_html
        assert f'<tbody class="cat-tbody cat-{cat_key}"' in rt_html
    rt_p_order = [
        rt_html.index(f'<tbody class="cat-tbody cat-{k}"') for k in COMPUTE_CATEGORY_ORDER
    ]
    assert rt_p_order == sorted(rt_p_order)
    assert '"category":"simulation"' in rt_html
    assert '"category":"calibration"' in rt_html
    assert '"category":"loop_operation"' in rt_html
    assert '"category":"analysis"' in rt_html
    assert 'class="checklist-item cat-simulation"' in how_html
    assert 'class="cat-badge cat-loop_operation"' in how_html


def test_topic_hierarchy_crossrefs_and_link_integrity(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify domain hubs, cross-refs, domain override, search index, and local link integrity."""
    from html.parser import HTMLParser

    site_dir = tmp_path / "web_site"
    script = repo_root / "scripts" / "build-ao-web-report.py"

    sim_specs = [
        (
            "ao3k_scexao_lowfs_closed",
            "AO3k + SCExAO Closed LLOWFS Baseline",
            "coronagraphy-lowfs",
            {"coronagraph_metrics": {"llowfs": {"enabled_closed_loop": True}}},
        ),
        (
            "ao3k_scexao_predictive_ar8",
            "AO3k + SCExAO PSOL AR(8)",
            "wavefront-control",
            {"predictive_control": {"enabled": True, "pf_order": 8}},
        ),
        (
            "ao3k_scexao_calib2wfs1dm",
            "AO3k + SCExAO 2-WFS/1-DM Calib",
            "calibration-sysid",
            {"calib_2wfs1dm": {"enabled": True}},
        ),
        ("ao3k_scexao", "AO3k + SCExAO Baseline Bench", "bench-runtime", {}),
    ]
    for idx, (slug, title, expected_dom, extra_metrics) in enumerate(sim_specs):
        rdir = tmp_path / slug
        rdir.mkdir(parents=True)
        (rdir / "REPORT.md").write_text(f"# {title}\n\nSummary body.\n", encoding="utf-8")
        metrics_payload: dict[str, object] = {
            "summary": {
                "total_wfe_nm": 90.0 + idx,
                "vis_strehl": 0.70 + 0.02 * idx,
                "nir_strehl": 0.90 + 0.01 * idx,
            },
            "parameters": {"bench_fps": 2000.0},
            **extra_metrics,
        }
        (rdir / "ao3k_scexao_metrics.json").write_text(
            json.dumps(metrics_payload),
            encoding="utf-8",
        )
        res = subprocess.run(
            [
                sys.executable,
                str(script),
                "--report-dir",
                str(rdir),
                "--site-dir",
                str(site_dir),
                "--slug",
                slug,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, res.stderr + res.stdout
        staged_meta = json.loads(
            (site_dir / "public" / slug / "report_meta.json").read_text(encoding="utf-8")
        )
        assert staged_meta["domain"] == expected_dom

    # Stage 2 tech reports: one overriding domain explicitly, one using keyword classification.
    tr1 = tmp_path / "tr_calib_override"
    tr1.mkdir(parents=True)
    (tr1 / "REPORT.md").write_text("# Custom Calib Report\n\nBody.\n", encoding="utf-8")
    (tr1 / "study_meta.json").write_text(
        json.dumps(
            {
                "report_type": "tech_report",
                "domain": "calibration-sysid",
                "title": "Explicit Calibration Domain Study",
                "referenced_simulations": ["ao3k_scexao_calib2wfs1dm", "ao3k_scexao_lowfs_closed"],
            }
        ),
        encoding="utf-8",
    )
    tr2 = tmp_path / "tr_pred_kw"
    tr2.mkdir(parents=True)
    (tr2 / "REPORT.md").write_text("# Predictive Study\n\nBody.\n", encoding="utf-8")
    (tr2 / "study_meta.json").write_text(
        json.dumps(
            {
                "report_type": "tech_report",
                "title": "PSOL Predictive Control Overview",
                "referenced_simulations": ["ao3k_scexao_predictive_ar8", "ao3k_scexao_lowfs_closed"],
            }
        ),
        encoding="utf-8",
    )
    for tdir, tslug in ((tr1, "tr_calib_override"), (tr2, "tr_pred_kw")):
        res = subprocess.run(
            [
                sys.executable,
                str(script),
                "--report-dir",
                str(tdir),
                "--site-dir",
                str(site_dir),
                "--slug",
                tslug,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, res.stderr + res.stdout

    pub_dir = site_dir / "public"
    for did in (
        "wavefront-control",
        "calibration-sysid",
        "coronagraphy-lowfs",
        "bench-runtime",
        "hardware-dynamics",
    ):
        hub = pub_dir / "topics" / did / "index.html"
        assert hub.is_file(), f"Missing topic hub: {hub}"
    cal_hub_html = (pub_dir / "topics" / "calibration-sysid" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "Custom Calib Report" in cal_hub_html
    assert "ao3k_scexao_lowfs_closed" in cal_hub_html
    assert "Cross-ref" in cal_hub_html
    bench_hub_html = (pub_dir / "topics" / "bench-runtime" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "Optical Bench, Compute &amp; Deployment Matrix" in bench_hub_html

    search_js = (pub_dir / "assets" / "js" / "search-index.js").read_text(encoding="utf-8")
    assert search_js.startswith("window.CACAO_SEARCH_INDEX=")
    search_items = json.loads(search_js.removeprefix("window.CACAO_SEARCH_INDEX=").rstrip(";\n"))
    assert any(item["path"] == "topics/wavefront-control/index.html" for item in search_items)
    assert any(item["path"] == "tr_calib_override/index.html" for item in search_items)

    class LinkCollector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.refs: list[str] = []
            self.has_style = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "style":
                self.has_style = True
            for k, v in attrs:
                if k in ("href", "src") and v:
                    self.refs.append(v)

    html_files = sorted(pub_dir.rglob("*.html"))
    assert len(html_files) >= 20
    for html_path in html_files:
        parser = LinkCollector()
        parser.feed(html_path.read_text(encoding="utf-8"))
        assert not parser.has_style, f"Unexpected inline <style> in {html_path}"
        for ref in parser.refs:
            if ref.startswith(("http://", "https://", "#", "data:", "javascript:", "mailto:")):
                continue
            rel_part = ref.split("#", 1)[0].split("?", 1)[0]
            if not rel_part:
                continue
            target = (html_path.parent / rel_part).resolve()
            assert target.exists(), f"Broken local link {ref!r} in {html_path}"

    for cli_name in (
        "build-ao-web-report.py",
        "build-calib-2wfs1dm-report.py",
        "build-predictive-control-report.py",
    ):
        res_help = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / cli_name), "--help"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_help.returncode == 0, f"{cli_name} --help failed: {res_help.stderr}"


def test_eof_pf_extractor_and_optical_page(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify pure-stdlib EOF 3D PF extractor, int8 round-trip, and optical page."""
    import base64
    import numpy as np
    from astropy.io import fits

    scripts_dir = str(repo_root / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from report_site.extractors import extract_eof_pf_data

    rep_dir = tmp_path / "eof_synth"
    rep_dir.mkdir(parents=True)
    n_modes, b_sz, p_ord, diag_tail = 32, 16, 4, 8

    def build_eof_mat(diag_scale: float) -> tuple[np.ndarray, np.ndarray]:
        sub0 = np.zeros((b_sz, p_ord, b_sz), dtype=np.float32)
        taps = np.array([0.65, 0.25, -0.05, -0.15], dtype=np.float32) * diag_scale
        for m in range(b_sz):
            sub0[m, :, m] = taps
        quad = np.array([0.18, 0.14, 0.08, 0.02], dtype=np.float32)
        sub0[3, :, 4] = quad
        sub0[4, :, 3] = -quad
        fmat = np.zeros((n_modes, p_ord * b_sz + diag_tail), dtype=np.float32)
        fmat[:b_sz, : p_ord * b_sz] = sub0.reshape(b_sz, p_ord * b_sz)
        for m in range(b_sz, n_modes):
            for k in range(p_ord):
                fmat[m, k * b_sz + (m - b_sz)] = taps[k] * 0.8
        return fmat, sub0

    fmat1, sub0_1 = build_eof_mat(1.0)
    fmat2, _ = build_eof_mat(0.85)
    fits.writeto(rep_dir / "aol1_eofPFmat.fits", fmat1, overwrite=True)
    fits.writeto(rep_dir / "aol2_eofPFmat.fits", fmat2[:, : p_ord * b_sz], overwrite=True)

    metrics = {
        "star_and_atmosphere": {"seeing_arcsec_500nm": 0.60, "physical_time_s": 5.0},
        "psf_metrics": {
            "vis": {"final": {"strehl_peak": 0.81}},
            "nir": {"final": {"strehl_peak": 0.95}},
        },
        "wavefront_metrics": {"locations": {"final": {"quad_total_rms_nm": 56.0}}},
        "predictive_control": {
            "enabled": True,
            "pf_mode": "eof",
            "pf_blocksize": b_sz,
            "pf_order": p_ord,
            "stage1": {"pflatency_fr": 2.40, "var_red_pct": 41.8},
            "stage2": {"pflatency_fr": 2.58, "var_red_pct": 34.1},
        },
    }
    (rep_dir / "ao3k_scexao_metrics.json").write_text(
        json.dumps(metrics) + "\n", encoding="utf-8"
    )
    (rep_dir / "REPORT.md").write_text(
        "# EOF Synthetic Run\n\n## Summary\n\nBody.\n", encoding="utf-8"
    )

    extracted = extract_eof_pf_data(rep_dir, metrics)
    assert extracted is not None
    assert extracted["pf_mode"] == "eof"
    assert len(extracted["stages"]) == 2
    st1 = extracted["stages"][0]
    assert st1["blocksize"] == b_sz
    assert st1["order"] == p_ord
    assert st1["n_blocks"] == 2
    blk0 = st1["blocks"][0]
    assert blk0["top_pairs"][0][:2] in ([3, 4], [4, 3])
    raw_q = np.frombuffer(base64.b64decode(blk0["data_b64"]), dtype=np.int8)
    rec = np.sign(raw_q) * ((raw_q.astype(np.float64) / 127.0) ** 2) * blk0["vmax"]
    rec_3d = rec.reshape(b_sz, p_ord, b_sz)
    assert np.max(np.abs(rec_3d - sub0_1)) < 0.01

    site_dir = tmp_path / "web_site"
    script = repo_root / "scripts" / "build-ao-web-report.py"
    res = subprocess.run(
        [
            sys.executable,
            str(script),
            "--report-dir",
            str(rep_dir),
            "--site-dir",
            str(site_dir),
            "--slug",
            "eof_synth",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    slug_out = site_dir / "public" / "eof_synth"
    assert (slug_out / "eof_pf_data.js").is_file()
    opt_html = (slug_out / "optical.html").read_text(encoding="utf-8")
    assert 'id="eof-pf-panel"' in opt_html
    assert "eof_pf_viewer.js" in opt_html
    assert 'src="eof_pf_data.js"' in opt_html

    ar_dir = tmp_path / "ar_synth"
    ar_dir.mkdir(parents=True)
    (ar_dir / "REPORT.md").write_text("# AR Run\n\nBody.\n", encoding="utf-8")
    (ar_dir / "ao3k_scexao_metrics.json").write_text(
        json.dumps({"predictive_control": {"enabled": True, "pf_mode": "ar", "pf_order": 8}}),
        encoding="utf-8",
    )
    res_ar = subprocess.run(
        [
            sys.executable,
            str(script),
            "--report-dir",
            str(ar_dir),
            "--site-dir",
            str(site_dir),
            "--slug",
            "ar_synth",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_ar.returncode == 0, res_ar.stderr + res_ar.stdout
    ar_out = site_dir / "public" / "ar_synth"
    assert not (ar_out / "eof_pf_data.js").exists()
    ar_opt = (ar_out / "optical.html").read_text(encoding="utf-8")
    assert 'id="eof-pf-panel"' not in ar_opt
    assert "eof_pf_viewer.js" not in ar_opt


def test_cacaosim_ao_report_replot_eof_pf(
    stack_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """Verify cacaosim-ao-report --replot-eof-pf generates 3D PF plots & REPORT.md."""
    import numpy as np
    from astropy.io import fits

    rep_dir = tmp_path / "eof_replot"
    rep_dir.mkdir(parents=True)
    n_modes, b_sz, p_ord = 32, 16, 4
    mat = np.zeros((n_modes, p_ord * b_sz), dtype=np.float32)
    taps = np.array([0.6, 0.2, -0.05, -0.1], dtype=np.float32)
    for m in range(b_sz):
        for k in range(p_ord):
            mat[m, k * b_sz + m] = taps[k]
    mat[3, 4] = 0.16
    mat[4, 3] = -0.16
    fits.writeto(rep_dir / "aol1_eofPFmat.fits", mat, overwrite=True)
    fits.writeto(rep_dir / "aol2_eofPFmat.fits", mat * 0.9, overwrite=True)

    (rep_dir / "pf_stats.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "pf_mode": "eof",
                "pf_blocksize": b_sz,
                "pf_order": p_ord,
                "pf_mix": 0.90,
                "pf_reg": 0.0001,
                "stage1": {"pflatency_fr": 2.4, "var_red_pct": 40.0, "offdiag_frac": 0.2},
                "stage2": {"pflatency_fr": 2.5, "var_red_pct": 33.0, "offdiag_frac": 0.1},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (rep_dir / "ao3k_scexao_metrics.json").write_text(
        json.dumps(
            {
                "configuration": "Synthetic EOF Run",
                "telescope": {"diameter_m": 7.95, "cobs": 0.307, "tput_tel": 0.20},
                "star_and_atmosphere": {"seeing_arcsec_500nm": 0.60, "physical_time_s": 5.0},
                "loops": {
                    "stage1_ao3k": {"n_cm_modes": n_modes, "gain": 0.35, "mult": 0.98},
                    "stage2_scexao": {"n_cm_modes": n_modes, "gain": 0.35, "mult": 0.98},
                },
                "psf_metrics": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    res = subprocess.run(
        ["cacaosim-ao-report", "--replot-eof-pf", str(rep_dir)],
        env=stack_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    assert (rep_dir / "eof_pf_matrix_3d.png").is_file()
    assert (rep_dir / "eof_pf_lag_slices.png").is_file()
    rep_txt = (rep_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "Block-EOF(B=16, P=4)" in rep_txt
    assert "eof_pf_matrix_3d.png" in rep_txt
    assert "eof_pf_lag_slices.png" in rep_txt


def test_runner_cli_and_cacaoloop_env_drift_guards(repo_root: Path) -> None:
    """Verify zero drift between sim-ao3k-scexao.milk, cacaoloop, usage(), and catalog."""
    import re

    sys.path.insert(0, str(repo_root / "scripts"))
    from report_site.extractors.options_catalog import (
        CACAOLOOP_ENV_VARS,
        RUNNER_CLI_OPTIONS,
        build_options_catalog,
    )

    sim_text = (repo_root / "benches" / "ao3k_scexao" / "sim-ao3k-scexao.milk").read_text(
        encoding="utf-8"
    )
    usage_m = re.search(r"usage\(\)\s*\{\s*cat <<EOF\n(.*?)\nEOF\n\}", sim_text, re.DOTALL)
    assert usage_m is not None, "Could not locate usage() heredoc in sim-ao3k-scexao.milk"
    usage_body = usage_m.group(1)

    case_m = re.search(r'case "\$1" in\n(.*?)\n\s*esac', sim_text, re.DOTALL)
    assert case_m is not None, "Could not locate option case block in sim-ao3k-scexao.milk"
    parsed_flags = set(re.findall(r"(--[a-z0-9-]+)", case_m.group(1)))
    usage_flags = set(re.findall(r"(--[a-z0-9-]+)", usage_body))
    catalog_flags = {
        tok
        for item in RUNNER_CLI_OPTIONS
        for tok in re.findall(r"(--[a-z0-9-]+)", str(item["flag"]))
    }

    assert len(parsed_flags) >= 54
    missing_usage = parsed_flags - usage_flags
    missing_catalog = parsed_flags - catalog_flags
    extra_catalog = catalog_flags - parsed_flags
    assert not missing_usage, f"Flags parsed in case but missing from usage(): {missing_usage}"
    assert not missing_catalog, f"Flags parsed in case but missing from catalog: {missing_catalog}"
    assert not extra_catalog, f"Stale flags in RUNNER_CLI_OPTIONS: {extra_catalog}"

    loop_lines = (
        repo_root / "benches" / "ao3k_scexao" / "cacaoloop-ao3k-scexao.milk"
    ).read_text(encoding="utf-8").splitlines()
    env_block = "\n".join(loop_lines[94:162])
    script_envs = set(re.findall(r"\$\{(CACAO_[A-Z0-9_]+):-", env_block))
    catalog_envs = {item["name"] for item in CACAOLOOP_ENV_VARS}
    assert len(script_envs) >= 40
    assert not (script_envs - catalog_envs), (
        f"CACAO_* env vars missing from CACAOLOOP_ENV_VARS: {script_envs - catalog_envs}"
    )

    catalog = build_options_catalog()
    counts = catalog["counts"]
    assert counts["bench_options"] >= 160
    assert counts["cacaosim_units"] == 12
    assert counts["atmturb_units"] == 5
    assert counts["fps_params"] >= 400
    unit_names = {(u["package"], u["unit"]) for u in catalog["fps_units"]}
    assert ("cacaosim", "wfstat") in unit_names
    assert ("cacaosim", "htsim") in unit_names
    assert ("milkatmturb", "mkwfs") in unit_names
    assert ("milkatmturb", "aoloop") in unit_names


def test_options_reference_config_and_run_options_tracking(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify /reference/, non-truncated config.html, Advanced customizer, & auto-diff."""
    from html.parser import HTMLParser

    class _Checker(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.has_style = False
            self.hrefs: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "style":
                self.has_style = True
            for k, v in attrs:
                if k in ("href", "src") and v:
                    self.hrefs.append(v)

    def _make_run(slug: str, clock_skew: float, extra_bench: bool = False) -> Path:
        rdir = tmp_path / slug
        _create_synthetic_report(rdir)
        bench_lines = [
            "[bench]",
            'name = "subaru_ao3k_scexao"',
            "nwf = 256",
            "cobs = 0.307",
            "oversample = 4",
            "[pyrwfs.vis]",
            "in = b_vis",
            "out_cam = csim_wfs_vis",
            "ncam = 120",
            "lambda_um = 0.75",
            "bw_frac = 0.25",
            "n_lambda = 5",
            "mod_rad = 3.0",
            "mod_pts = 16",
            "mod_mode = circle",
            "mod_rev = 1",
            "mod_phase_deg = 0.0",
            "pup_sep = 1.15",
            "pup_rad_px = 24.0",
            "roof_rad = 0.0",
            "fstop_frac = 1.0",
            "pad_factor = 2",
            "chrom_sep = 1",
            "ron_e = 0.4",
            "qe = 0.85",
            "tput = 0.90",
            "rate_hz = 2000.0",
        ]
        if extra_bench:
            bench_lines.append("rng_seed = 4242")
        (rdir / "ao3k_scexao.bench").write_text("\n".join(bench_lines) + "\n", encoding="utf-8")
        (rdir / "run_options.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "runner": "sim-ao3k-scexao.milk",
                    "options": {
                        "seeing": 0.6,
                        "phys_time": 10.0,
                        "bench_mode": "fused",
                        "eff_oversample": 4,
                        "clock_skew_us": clock_skew,
                        "pf_mix2": 0.85,
                        "fast_calib": 0,
                        "save_telemetry": "speckle",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return rdir

    r1 = _make_run("sim_skew_0", 0.0, extra_bench=True)
    r2 = _make_run("sim_skew_125", 125.0)
    site_dir = tmp_path / "web_site"
    script = repo_root / "scripts" / "build-ao-web-report.py"
    for rdir, slug in ((r1, "sim_skew_0"), (r2, "sim_skew_125")):
        res = subprocess.run(
            [
                sys.executable,
                str(script),
                "--report-dir",
                str(rdir),
                "--site-dir",
                str(site_dir),
                "--slug",
                slug,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, res.stderr + res.stdout

    pub = site_dir / "public"
    ref_path = pub / "reference" / "index.html"
    assert ref_path.is_file()
    ref_html = ref_path.read_text(encoding="utf-8")
    assert 'id="ref-panel-bench"' in ref_html
    assert 'id="ref-panel-fps"' in ref_html
    assert 'id="ref-panel-cli"' in ref_html
    assert 'id="opt-bench-pyrwfs-mod_rad"' in ref_html
    assert 'id="opt-bench-bench-oversample"' in ref_html
    assert 'id="opt-fps-cacaosim-wfstat-trig_beam"' in ref_html
    assert 'id="opt-fps-milkatmturb-mkwfs-fresnel"' in ref_html
    assert 'id="opt-cli-run-ao3k-scexao-sh-pf-mix2"' in ref_html
    assert 'id="opt-cli-cacaoloop-env-cacao_pf_mode"' in ref_html
    assert "../sim_skew_0/config.html" in ref_html

    idx_js = (pub / "assets" / "js" / "search-index.js").read_text(encoding="utf-8")
    assert idx_js.startswith("window.CACAO_SEARCH_INDEX=")
    idx_items = json.loads(idx_js[len("window.CACAO_SEARCH_INDEX=") :].rstrip(";\n"))
    paths = {it["path"] for it in idx_items}
    assert "reference/index.html" in paths
    assert "reference/index.html#opt-bench-pyrwfs-mod_rad" in paths
    assert "reference/index.html#opt-fps-milkatmturb-mkwfs-fresnel" in paths

    cfg_html = (pub / "sim_skew_0" / "config.html").read_text(encoding="utf-8")
    # 21 keys in [pyrwfs.vis] + rng_seed (22nd key) must ALL appear (no [:14] truncation)
    assert "rng_seed" in cfg_html
    assert "4242" in cfg_html
    assert "../reference/index.html#opt-bench-pyrwfs-mod_rad" in cfg_html
    assert "opt-nondefault" in cfg_html
    assert 'id="bench-flat-table"' in cfg_html
    assert 'id="resolved-runner-options"' in cfg_html
    assert "--clock-skew-us" in cfg_html

    htr_html = (pub / "sim_skew_0" / "how_to_run.html").read_text(encoding="utf-8")
    assert 'class="adv-customizer"' in htr_html
    assert 'id="howtorun-adv-specs"' in htr_html
    assert "../reference/index.html#opt-cli-run-ao3k-scexao-sh-seeing" in htr_html
    assert 'id="cust-adv-clock_skew_us"' in htr_html

    sims_html = (pub / "simulations" / "index.html").read_text(encoding="utf-8")
    assert "Clock Skew" in sims_html
    assert "125 us" in sims_html

    # Verify zero inline <style> tags and zero broken relative links across all pages
    for html_file in pub.rglob("*.html"):
        chk = _Checker()
        chk.feed(html_file.read_text(encoding="utf-8"))
        assert not chk.has_style, f"Inline <style> found in {html_file}"
        for raw_href in chk.hrefs:
            if raw_href.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            target = raw_href.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            resolved = (html_file.parent / target).resolve()
            assert resolved.exists(), f"Broken link {raw_href!r} in {html_file}"
