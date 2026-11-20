# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Validate 2-WFS + 1-DM telemetry calibration CLI flags and Front Page changed-parameters UI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _stage_synthetic_run(
    repo_root: Path,
    tmp_path: Path,
    site_dir: Path,
    slug: str,
    *,
    seeing: float = 0.60,
    phys_time: float = 5.0,
    gain1: float = 0.35,
    gain2: float = 0.35,
    mult1: float = 0.98,
    mult2: float = 0.98,
    oversample: int = 4,
    lo_on: bool = True,
    pc_on: bool = False,
    c2d_on: bool = False,
    c2d_modes: int = 40,
    c2d_whiten: int = 4,
    wfe_nm: float = 65.0,
) -> None:
    rdir = tmp_path / slug
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "psf_comparison_2x3.png").write_bytes(TINY_PNG)
    if c2d_on:
        (rdir / "calib_2wfs1dm_summary_2x2.png").write_bytes(TINY_PNG)
        (rdir / "calib_2wfs1dm_summary.json").write_text(
            json.dumps({"dim_b": c2d_modes, "whiten_order": c2d_whiten}) + "\n",
            encoding="utf-8",
        )

    metrics: dict[str, object] = {
        "star_and_atmosphere": {
            "seeing_arcsec_500nm": seeing,
            "physical_time_s": phys_time,
            "oversample": oversample,
        },
        "loops": {
            "stage1_ao3k": {
                "gain": gain1,
                "mult": mult1,
                "mgain_alpha": 0.80,
                "mgain_floor": 0.10,
                "mgain_tt_factor": 1.00,
                "svdlim": 0.004,
            },
            "stage2_scexao": {
                "gain": gain2,
                "mult": mult2,
                "svdlim": 0.004,
            },
            "stage3_llowfs": {
                "gain": 0.20 if lo_on else 0.0,
                "mult": 0.99,
                "svdlim": 0.02,
            },
        },
        "psf_metrics": {
            "vis": {"final": {"strehl_peak": 0.78}},
            "nir": {"final": {"strehl_peak": 0.945}},
        },
        "wavefront_metrics": {
            "locations": {
                "stg1": {"quad_total_rms_nm": 110.0},
                "final": {"quad_total_rms_nm": wfe_nm},
            }
        },
        "coronagraph_metrics": {
            "llowfs": {"enabled_closed_loop": lo_on, "dm3_stroke_rms_nm": 24.5},
            "closed_loop": {
                "total_leakage_frac": 0.029,
                "mean_planet_contrast_3_10ld": 1.10e-4,
            },
            "lowfs_light_budget": {
                "closed_loop": {
                    "frac_coro_in_reaching_lowfs_cam_fov": 0.071,
                    "frac_entrance_pup_h_reaching_lowfs_cam_fov": 0.062,
                }
            },
            "contrast_table": [
                {
                    "sep_ld": 5.0,
                    "cl_planet_contrast": 2.9e-4,
                    "cl_5sigma_planet_contrast": 5.1e-4,
                }
            ],
        },
        "reproducibility": {
            "run_command": (
                f"./scripts/run-ao3k-scexao.sh --seeing {seeing:.2f} "
                f"--phys-time {phys_time:.1f} --oversample {oversample} "
                f"--bench-mode fused --gain2 {gain2:.2f} --save-telemetry speckle"
            ),
            "telemetry_mode": "speckle",
        },
    }
    if pc_on:
        metrics["predictive_control"] = {
            "enabled": True,
            "pf_order": 8,
            "pf_mix": 0.90,
            "pf_reg": 0.005,
            "stage1": {"var_red_pct": 28.0},
            "stage2": {"var_red_pct": 24.0},
        }
    if c2d_on:
        metrics["calib_2wfs1dm"] = {
            "enabled": True,
            "dim_a": 60,
            "dim_b": c2d_modes,
            "dim_d": c2d_modes,
            "whiten_order": c2d_whiten,
            "eta_d_raw_med": 0.19,
            "eta_d_white_med": 0.90,
            "mdb_diag_raw_med": 0.37,
            "mdb_diag_med": 0.722,
            "has_selfrm": True,
            "selfrm_rel_err": 0.0385,
            "r2_a_raw_med": 0.766,
            "geom_col_cos_med": 0.89,
        }
    (rdir / "ao3k_scexao_metrics.json").write_text(
        json.dumps(metrics) + "\n", encoding="utf-8"
    )

    md_lines = [
        f"# AO Report ({slug})",
        "",
        "![PSF Comparison](psf_comparison_2x3.png)",
    ]
    if c2d_on:
        md_lines.extend(
            [
                "",
                "## Two-WFS + Inter-Stage DM Telemetry Calibration",
                "",
                "![2-WFS + 1-DM Calibration Summary](calib_2wfs1dm_summary_2x2.png)",
            ]
        )
    (rdir / "REPORT.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    script = repo_root / "scripts" / "build-ao-web-report.py"
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


def test_run_ao3k_help_lists_calib_2wfs1dm_flags(
    repo_root: Path,
    stack_env: dict[str, str],
) -> None:
    """Verify run-ao3k-scexao.sh --help documents the 2-WFS + 1-DM calibration flags."""
    res = subprocess.run(
        [str(repo_root / "scripts" / "run-ao3k-scexao.sh"), "--help"],
        cwd=repo_root,
        env=stack_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    assert "--calib-2wfs1dm" in res.stdout
    assert "--sysid-modes" in res.stdout
    assert "--sysid-whiten-order" in res.stdout


def test_front_page_changed_parameters_and_calib_2wfs1dm(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify Front Page renders Changed Parameters column, shared params, and 2-WFS/1-DM col."""
    site_dir = tmp_path / "web_site"

    # Stage 4 runs where 3 parameters vary (Control Law, LLOWFS, 2-WFS/1-DM Calib)
    _stage_synthetic_run(repo_root, tmp_path, site_dir, "r1_open", lo_on=False)
    _stage_synthetic_run(repo_root, tmp_path, site_dir, "r2_closed", lo_on=True)
    _stage_synthetic_run(
        repo_root, tmp_path, site_dir, "r3_pred", lo_on=True, pc_on=True, wfe_nm=58.0
    )
    _stage_synthetic_run(
        repo_root,
        tmp_path,
        site_dir,
        "r4_calib",
        lo_on=True,
        pc_on=True,
        c2d_on=True,
        wfe_nm=57.5,
    )

    front_html = (site_dir / "public" / "index.html").read_text(encoding="utf-8")
    assert '<th style="text-align: left;">Changed Parameters</th>' in front_html
    assert '<th style="text-align: right;">2-WFS/1-DM Calib</th>' in front_html
    assert "2-WFS/1-DM CALIB" in front_html
    assert "Mdb=0.72" in front_html
    assert "3.9% selfRM" in front_html
    assert "R&sup2;_A=0.77" in front_html
    assert "param-pill-diff" in front_html
    assert "Shared parameters across all 4 runs:" in front_html
    # Seeing & Gain2 did NOT change yet, so they must appear in the shared strip.
    shared_section = front_html.split("Shared parameters across all 4 runs:")[1].split("</div>")[0]
    assert 'Seeing=<code>0.60"</code>' in shared_section
    assert "Gain2=<code>0.35</code>" in shared_section
    assert "Control Law=" not in shared_section

    # Verify individual calibration pages stage figure, downloadable JSON, & compute unit.
    calib_idx = (site_dir / "public" / "r4_calib" / "index.html").read_text(encoding="utf-8")
    calib_opt = (site_dir / "public" / "r4_calib" / "optical.html").read_text(encoding="utf-8")
    calib_how = (site_dir / "public" / "r4_calib" / "how_to_run.html").read_text(
        encoding="utf-8"
    )
    assert 'src="calib_2wfs1dm_summary_2x2.png"' in calib_opt
    assert 'href="calib_2wfs1dm_summary.json"' in calib_idx
    assert "milk-mlt-calib2wfs1dm" in calib_how

    # Stage 2 more runs varying Seeing, Gain2, and Phys Time -> >4 varying params switches to
    # compact diff-only pills against Baseline so the table remains readable.
    _stage_synthetic_run(
        repo_root, tmp_path, site_dir, "r5_seeing08", seeing=0.80, gain2=0.50, phys_time=10.0
    )
    front_html_5 = (site_dir / "public" / "index.html").read_text(encoding="utf-8")
    assert "Baseline</span>" in front_html_5
    assert 'Seeing: <strong><code>0.80"</code></strong>' in front_html_5
    assert "Gain2: <strong><code>0.50</code></strong>" in front_html_5
    assert "Phys Time: <strong><code>10.0 s</code></strong>" in front_html_5
    shared_5 = front_html_5.split("Shared parameters across all 5 runs:")[1].split("</div>")[0]
    assert "Seeing=" not in shared_5
    assert "Gain2=" not in shared_5
    assert "Gain1=<code>0.35</code>" in shared_5
    assert "Oversample=<code>4x</code>" in shared_5
