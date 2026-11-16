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
