# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end closed-loop SCAO validation via fpspipe and .milk controller."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["fused", "modular"])
def test_scao_headless_closed_loop(
    mode: str,
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Verify fpspipe closed-loop improves Strehl and cuts residuals."""
    shm_dir, work_dir, env = shm_sandbox
    metrics_path = work_dir / "metrics.json"

    res = subprocess.run(
        [
            str(repo_root / "scripts" / "run-scao-headless.sh"),
            "--mode",
            mode,
            "--rate",
            "400",
            "--eval-frames",
            "240",
            "--shm-dir",
            str(shm_dir),
            "--workdir",
            str(work_dir),
            "--metrics-out",
            str(metrics_path),
        ],
        cwd=repo_root,
        env=env,
        timeout=150,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    assert metrics_path.is_file()

    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert data["workflow"] == "fpspipe"
    dl, ol, cl = data["dl"], data["ol"], data["cl"]

    assert dl["strehl_peak"] > 0.85, data
    assert cl["strehl_peak"] > ol["strehl_peak"] + 0.04, data
    assert cl["strehl_fps_ave"] > ol["strehl_fps_ave"] + 0.04, data
    assert cl["strehl_peak"] > ol["strehl_peak"] * 2.2, data
    assert cl["wfs_rms"] < ol["wfs_rms"] * 0.98, data
    assert cl["mval_rms"] < ol["mval_rms"] * 0.85, data
    assert cl["dm_rms"] > 0.05, data

    assert list(shm_dir.glob("*.fps.shm")) == []


def test_cacaoloop_milk_controller_lifecycle(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Verify cacaoloop-scao-pyr.milk warm deploy, controls, status, and teardown."""
    shm_dir, work_dir, env = shm_sandbox
    csim_dir = work_dir / "csim"
    loop_dir = work_dir / "scao_pyr"
    ctrl = repo_root / "benches" / "scao_pyr" / "cacaoloop-scao-pyr.milk"

    script = f"""
set -euo pipefail
source "{repo_root}/env.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export CACAOSIM_WORKDIR="{csim_dir}"
export CACAO_LOOPROOTDIR="{loop_dir}"
export CACAO_LOOPNUMBER=1
export CACAO_LOOPNAME=scao_pyr

cleanup() {{
    "{ctrl}" teardown --purge-dm >/dev/null 2>&1 || true
    cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy \\
    --workdir "{csim_dir}" \\
    --config "{repo_root}/benches/scao_pyr/scao_pyr.bench" \\
    --mode fused --rate 300 --atmturb --seeing 0.7 --no-view >/dev/null
milk-stream-wait -q -t 20 csim_wfs

"{ctrl}" deploy
"{ctrl}" deploy
"{ctrl}" status
"{ctrl}" close 0.25
"{ctrl}" open
"{ctrl}" zero
"{ctrl}" teardown --purge-dm
cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null
"""
    res = subprocess.run(
        ["bash", "-c", script],
        cwd=repo_root,
        env=env,
        timeout=90,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    assert "Loop scao_pyr (aol1): loopON=OFF" in res.stdout
    assert list(shm_dir.glob("aol1_*")) == []
    assert list(shm_dir.glob("*.fps.shm")) == []


def test_scao_save_and_reload_rm(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Verify saving calibrated RM and rerunning closed-loop from saved RM."""
    shm_dir, work_dir, env = shm_sandbox
    rm_dir = work_dir / "saved_rm"
    work_run1 = work_dir / "run1"
    work_run2 = work_dir / "run2"
    metrics1 = work_dir / "metrics_cal.json"
    metrics2 = work_dir / "metrics_rerun.json"

    res1 = subprocess.run(
        [
            str(repo_root / "scripts" / "run-scao-headless.sh"),
            "--mode",
            "fused",
            "--rate",
            "400",
            "--eval-frames",
            "200",
            "--shm-dir",
            str(shm_dir),
            "--workdir",
            str(work_run1),
            "--save-rm",
            str(rm_dir),
            "--metrics-out",
            str(metrics1),
        ],
        cwd=repo_root,
        env=env,
        timeout=150,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res1.returncode == 0, f"stderr:\n{res1.stderr}\nstdout:\n{res1.stdout}"

    for fname in (
        "zpokeC.fits",
        "zrespC.fits",
        "RMmodesDM.fits",
        "RMmodesWFS.fits",
        "zrespM.fits",
        "dmmask.fits",
        "wfsmask.fits",
        "wfsref.fits",
        "CMmodesDM.fits",
        "CMmodesWFS.fits",
        "rm_meta.env",
    ):
        assert (rm_dir / fname).exists(), f"missing saved RM artifact {fname}"

    data1 = json.loads(metrics1.read_text(encoding="utf-8"))
    assert data1["calib"]["source"] == "calibrated"
    assert data1["calib"]["n_rm_modes"] > 0
    assert data1["calib"]["n_cm_modes"] > 0

    res2 = subprocess.run(
        [
            str(repo_root / "scripts" / "run-scao-headless.sh"),
            "--mode",
            "fused",
            "--rate",
            "400",
            "--svdlim",
            "0.06",
            "--eval-frames",
            "200",
            "--shm-dir",
            str(shm_dir),
            "--workdir",
            str(work_run2),
            "--load-rm",
            str(rm_dir),
            "--metrics-out",
            str(metrics2),
        ],
        cwd=repo_root,
        env=env,
        timeout=120,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res2.returncode == 0, f"stderr:\n{res2.stderr}\nstdout:\n{res2.stdout}"

    data2 = json.loads(metrics2.read_text(encoding="utf-8"))
    assert data2["calib"]["source"] == "load-rm"
    dl2, ol2, cl2 = data2["dl"], data2["ol"], data2["cl"]
    assert dl2["strehl_peak"] > 0.85, data2
    assert cl2["strehl_peak"] > ol2["strehl_peak"] * 2.0, data2
    assert cl2["wfs_rms"] < ol2["wfs_rms"] * 0.98, data2
    assert cl2["mval_rms"] < ol2["mval_rms"] * 0.85, data2
    assert list(shm_dir.glob("*.fps.shm")) == []
