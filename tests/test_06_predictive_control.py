# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end validation of CACAO PSOL AR predictive control and 3-way web comparison."""

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


def test_scao_predictive_control_improves_over_integrator(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Verify PSOL AR predictive control improves Strehl and modal RMS over integrator."""
    shm_dir, work_dir, env = shm_sandbox
    metrics_path = work_dir / "metrics_pred.json"

    res = subprocess.run(
        [
            str(repo_root / "scripts" / "run-scao-headless.sh"),
            "--mode",
            "fused",
            "--rate",
            "400",
            "--eval-frames",
            "300",
            "--predictive",
            "--shm-dir",
            str(shm_dir),
            "--workdir",
            str(work_dir),
            "--metrics-out",
            str(metrics_path),
        ],
        cwd=repo_root,
        env=env,
        timeout=180,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    assert metrics_path.is_file()

    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    ol = data["ol"]
    cl = data["cl"]
    cl_pf = data["cl_pf"]
    pred = data["predictive"]
    stats = pred["stats"]

    assert pred["enabled"] is True
    assert stats["n_updates"] >= 2, stats
    assert stats["timeout_cnt"] == 0, stats
    assert stats["var_red_pct"] > 5.0, stats
    assert cl["strehl_peak"] > ol["strehl_peak"] * 2.2, data
    assert cl_pf["strehl_peak"] > cl["strehl_peak"] * 1.15, data
    assert cl_pf["mval_rms"] < cl["mval_rms"] * 0.85, data
    assert list(shm_dir.glob("*.fps.shm")) == []


def test_web_report_three_way_predictive_comparison(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify Front Page renders 3-way Open LLOWFS vs Closed LLOWFS vs PSOL Predictive."""
    site_dir = tmp_path / "web_site"
    script = repo_root / "scripts" / "build-ao-web-report.py"

    configs = [
        ("run_open", False, False, 483.5, 520.0, 69.2, 46.9, 5.73e-4),
        ("run_closed", True, False, 69.2, 521.8, 72.4, 93.0, 1.32e-4),
        ("run_predictive", True, True, 58.4, 83.1, 78.5, 94.6, 1.05e-4),
    ]
    for slug, lo_on, pc_on, wfe_nm, s1_wfe, vis_sr, nir_sr, c310 in configs:
        rdir = tmp_path / slug
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "psf_comparison_2x3.png").write_bytes(TINY_PNG)
        if pc_on:
            (rdir / "predictive_control_summary_2x2.png").write_bytes(TINY_PNG)
        metrics: dict[str, object] = {
            "star_and_atmosphere": {"seeing_arcsec_500nm": 0.60, "physical_time_s": 5.0},
            "psf_metrics": {
                "vis": {"final": {"strehl_peak": vis_sr / 100.0}},
                "nir": {"final": {"strehl_peak": nir_sr / 100.0}},
            },
            "wavefront_metrics": {
                "locations": {
                    "stg1": {"quad_total_rms_nm": s1_wfe},
                    "final": {"quad_total_rms_nm": wfe_nm},
                }
            },
            "coronagraph_metrics": {
                "llowfs": {"enabled_closed_loop": lo_on, "dm3_stroke_rms_nm": 28.0},
                "closed_loop": {
                    "total_leakage_frac": 0.032,
                    "mean_planet_contrast_3_10ld": c310,
                },
                "lowfs_light_budget": {
                    "closed_loop": {
                        "frac_coro_in_reaching_lowfs_cam_fov": 0.073,
                        "frac_entrance_pup_h_reaching_lowfs_cam_fov": 0.063,
                    }
                },
                "contrast_table": [
                    {
                        "sep_ld": 5.0,
                        "cl_planet_contrast": 3.1e-4,
                        "cl_5sigma_planet_contrast": 5.8e-4,
                    }
                ],
            },
        }
        if pc_on:
            metrics["predictive_control"] = {
                "enabled": True,
                "pf_order": 8,
                "pf_mix": 0.90,
                "stage1": {"var_red_pct": 28.9},
                "stage2": {"var_red_pct": 25.0},
            }
        (rdir / "ao3k_scexao_metrics.json").write_text(
            json.dumps(metrics) + "\n", encoding="utf-8"
        )
        md_lines = [
            f"# Report {slug}",
            "",
            "![PSF Comparison](psf_comparison_2x3.png)",
        ]
        if pc_on:
            md_lines.extend(
                [
                    "",
                    "![Predictive Control Summary](predictive_control_summary_2x2.png)",
                ]
            )
        (rdir / "REPORT.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

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

    front_html = (site_dir / "public" / "index.html").read_text(encoding="utf-8")
    assert 'id="tech-reports-table"' in front_html
    assert 'id="sim-reports-table"' in front_html
    assert "PSOL AR(8) PREDICTIVE" in front_html
    assert "<strong>PSOL AR(8) Predictive</strong>" in front_html
    assert "Modal Integrator" in front_html
    assert "83.1 nm" in front_html

    idx_open = front_html.index("<code>run_open</code>")
    idx_closed = front_html.index("<code>run_closed</code>")
    idx_pred = front_html.index("<code>run_predictive</code>")
    assert idx_open < idx_closed < idx_pred

    pred_opt = (site_dir / "public" / "run_predictive" / "optical.html").read_text(
        encoding="utf-8"
    )
    assert 'src="predictive_control_summary_2x2.png"' in pred_opt
    pred_how = (site_dir / "public" / "run_predictive" / "how_to_run.html").read_text(
        encoding="utf-8"
    )
    assert "mkARPF-1" in pred_how
    assert "applyARPF-1" in pred_how


def test_web_report_ar_order_sweep_and_featured_study(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Verify numeric AR(4/8/16/32) sorting, Featured Study card, and sibling report links."""
    site_dir = tmp_path / "web_site"
    script = repo_root / "scripts" / "build-ao-web-report.py"

    for p_ord in (32, 4, 16, 8):
        slug = f"run_ar{p_ord}"
        rdir = tmp_path / slug
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "predictive_control_summary_2x2.png").write_bytes(TINY_PNG)
        metrics = {
            "star_and_atmosphere": {"seeing_arcsec_500nm": 0.60, "physical_time_s": 5.0},
            "psf_metrics": {
                "vis": {"final": {"strehl_peak": 0.80}},
                "nir": {"final": {"strehl_peak": 0.95}},
            },
            "wavefront_metrics": {"locations": {"final": {"quad_total_rms_nm": 58.0}}},
            "predictive_control": {
                "enabled": True,
                "pf_order": p_ord,
                "pf_mix": 0.90,
                "stage1": {"var_red_pct": 25.0, "n_samples": 2048},
                "stage2": {"var_red_pct": 26.0, "n_samples": 2048},
            },
        }
        (rdir / "ao3k_scexao_metrics.json").write_text(
            json.dumps(metrics) + "\n", encoding="utf-8"
        )
        (rdir / "REPORT.md").write_text(
            f"# Report AR({p_ord})\n\n![PF](predictive_control_summary_2x2.png)\n",
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

    study_dir = tmp_path / "predictive_control_report"
    study_dir.mkdir(parents=True, exist_ok=True)
    (study_dir / "ar_order_optical_coro_summary_2x3.png").write_bytes(TINY_PNG)
    (study_dir / "predictive_control_summary.csv").write_text("order\n4\n8\n16\n32\n", "utf-8")
    (study_dir / "study_meta.json").write_text(
        json.dumps(
            {
                "report_type": "study",
                "nav_label": "Predictive Control Report",
                "button_label": "Read Predictive Control Report",
                "summary": "AR(4), AR(8), AR(16), and AR(32) study.",
                "badges": ["FEATURED STUDY", "AR(4)/AR(8)/AR(16)/AR(32)"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (study_dir / "REPORT.md").write_text(
        "# Predictive Control Report\n\n"
        "- Best run: [AR(16)](../run_ar16/index.html)\n\n"
        "![Summary](ar_order_optical_coro_summary_2x3.png)\n",
        encoding="utf-8",
    )
    res_s = subprocess.run(
        [
            sys.executable,
            str(script),
            "--report-dir",
            str(study_dir),
            "--site-dir",
            str(site_dir),
            "--slug",
            "predictive_control_report",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_s.returncode == 0, res_s.stderr + res_s.stdout

    front_html = (site_dir / "public" / "index.html").read_text(encoding="utf-8")
    t1_html = front_html.split('id="tech-reports-table"')[1].split("</table>")[0]
    t2_html = front_html.split('id="sim-reports-table"')[1].split("</table>")[0]
    assert './predictive_control_report/index.html' in t1_html
    assert "Predictive Control Report" in t1_html
    assert t2_html.index("<code>run_ar4</code>") < t2_html.index("<code>run_ar8</code>")
    assert t2_html.index("<code>run_ar8</code>") < t2_html.index("<code>run_ar16</code>")
    assert t2_html.index("<code>run_ar16</code>") < t2_html.index("<code>run_ar32</code>")

    study_html = (
        site_dir / "public" / "predictive_control_report" / "index.html"
    ).read_text(encoding="utf-8")
    assert 'href="../run_ar16/index.html"' in study_html
    assert 'href="../run_ar16/how_to_run.html"' in study_html
    assert 'href="study_meta.json"' not in study_html
    assert 'href="predictive_control_summary.csv"' in study_html

    ar16_idx = (site_dir / "public" / "run_ar16" / "index.html").read_text(encoding="utf-8")
    assert '../predictive_control_report/index.html' in ar16_idx
