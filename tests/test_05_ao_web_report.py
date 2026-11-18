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
            "| Band | Strehl | Mode |",
            "| :--- | ---: | :---: |",
            "| Vis | 36.1% | `aol2_imWFS2` |",
            "",
            "```mermaid",
            "flowchart LR",
            "    ATM --> DM1",
            "```",
            "",
            "### Hardware Simulator GUI (cacaosim-CTRL)",
            "",
            "- ![cacaosim-CTRL Builder](cacaosim_gui_builder.png)",
            "- ![cacaosim-CTRL Tables](cacaosim_gui_tables.png)",
            "- ![cacaosim-CTRL Status](cacaosim_gui_status.png)",
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
    compute_html = (slug_out / "compute_report.html").read_text(encoding="utf-8")

    # Bullet with pipe stays in <ul>, while GFM table gets alignments.
    assert "<ul>" in index_html
    assert "<strong>Seeing</strong>:" in index_html
    assert "<strong>Internal Optical-Bench Clock</strong>:" in index_html
    assert "<code>8.0 kHz</code>" in index_html
    assert "<code>dt = 0.125 ms = 125 us</code>" in index_html
    assert 'style="text-align: left;"' in index_html
    assert 'style="text-align: right;"' in index_html
    assert 'style="text-align: center;"' in index_html

    # Underscores inside code spans and filenames are not turned into <em>.
    assert "<code>csim_htsim</code>" in index_html
    assert "<code>b_post_stg1</code>" in index_html
    assert "<code>aol2_imWFS2</code>" in index_html
    assert 'src="cacaosim_gui_schematic.png"' in index_html
    assert 'src="cacaosim_gui_builder.png"' in index_html
    assert 'src="cacaosim_gui_tables.png"' in index_html
    assert 'src="cacaosim_gui_status.png"' in index_html
    assert 'src="chromatic_passbands_2x1.png"' in index_html
    assert "<code>wfs_nir</code>" in index_html
    assert 'id="hardware-simulator-gui-cacaosim-ctrl"' in index_html
    assert 'href="#hardware-simulator-gui-cacaosim-ctrl"' in index_html
    assert 'href="ao3k_scexao.bench"' in index_html
    assert (slug_out / "ao3k_scexao.bench").is_file()
    assert 'src="psf_comparison_2x3.png"' in index_html
    assert 'src="wf_strehl_timeseries_4x1.png"' in index_html
    assert 'src="psf_inst_vis_5x3.png"' in index_html
    assert 'src="dm_samples_5x4.png"' in index_html
    assert 'src="wfs_samples_5x4.png"' in index_html
    assert "<em>" not in index_html

    # Image-only list avoids <ul> bullets and renders <div class="figure-stack">.
    assert '<div class="figure-stack">' in index_html
    assert "<li><img" not in index_html

    # Mermaid diagram and script enabled on index.html only.
    assert '<pre class="mermaid">' in index_html
    assert "mermaid.esm.min.mjs" in index_html
    assert "mermaid.esm.min.mjs" not in compute_html

    # Bidirectional report link rewriting works.
    assert 'href="compute_report.html"' in index_html
    assert 'href="index.html"' in compute_html

    # Extra unreferenced PNG appears on index.html; compute PNG and video poster are NOT duplicated.
    assert 'src="extra_wf_samples_5x3.png"' in index_html
    assert "Additional Diagnostic Figures" in index_html
    assert 'src="compute_timeline_4x1.png"' in compute_html
    assert 'src="compute_timeline_4x1.png"' not in index_html
    assert "<video controls loop autoplay muted playsinline" in index_html
    assert 'poster="wfs_psf_short_evolution_poster.png"' in index_html
    assert '<source src="wfs_psf_short_evolution.mp4" type="video/mp4">' in index_html
    assert 'src="wfs_psf_short_evolution_poster.png"' not in index_html
    assert (slug_out / "wfs_psf_short_evolution.mp4").is_file()
    assert 'href="wfs_psf_short_evolution_meta.json"' not in index_html

    # Excluded .fits and external ../ paths do not produce broken <a href> links.
    assert not (slug_out / "cube.fits").exists()
    assert 'href="cube.fits"' not in index_html
    assert 'href="../ao3k_scexao_rm"' not in index_html
    assert 'href="metrics.json"' in index_html
    assert 'href="wf_timeseries.csv"' in index_html
    assert 'href="strehl_timeseries.csv"' in index_html
    assert "(local artifact, omitted from web bundle)" in index_html

    # Report page includes nav links to Front Page, Reproduce anchor, and GitHub.
    assert 'href="../index.html">Front Page</a>' in index_html
    assert 'href="index.html#reproducibility-github-provenance">Reproduce</a>' in index_html
    assert 'id="reproducibility-github-provenance"' in index_html
    assert (
        'href="https://github.com/cacao-org/cacao-work/commit/'
        '1111111222222233333334444444555555566666"'
    ) in index_html

    # Root Front Page is served directly at / (no 302 redirect) with intro, repos & CLI recipe.
    fb_cfg = json.loads((site_dir / "firebase.json").read_text(encoding="utf-8"))
    assert "redirects" not in fb_cfg["hosting"]
    assert "mp4" in fb_cfg["hosting"]["headers"][0]["source"]

    front_html = (site_dir / "public" / "index.html").read_text(encoding="utf-8")
    reports_html = (site_dir / "public" / "reports.html").read_text(encoding="utf-8")
    assert front_html == reports_html
    assert "Closed-Loop Adaptive Optics Simulation" in front_html
    assert "https://github.com/cacao-org/cacao-work" in front_html
    assert "https://github.com/milk-org/milk" in front_html
    assert "git -C milk submodule update --init src/engine/ImageStreamIO" in front_html
    assert "./scripts/build-all.sh" in front_html
    assert "./scripts/run-ao3k-scexao.sh --save-telemetry speckle" in front_html
    assert "Vis SR 82.8%" in front_html
    assert "H SR 95.3%" in front_html
    assert './demo_run/index.html#reproducibility-github-provenance' in front_html


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
