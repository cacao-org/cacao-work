# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Verify persistent live-bench.sh lifecycle, controls, and cleanup."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_live_bench_cli_lifecycle(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Exercise start, env, status, turb, and stop on live-bench.sh."""
    shm_dir, work_dir, base_env = shm_sandbox
    env = base_env.copy()
    state_file = work_dir / "live.state"
    env["CACAO_LIVE_STATE_FILE"] = str(state_file)
    script = str(repo_root / "scripts" / "live-bench.sh")

    def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [script, *args],
            cwd=repo_root,
            env=env,
            timeout=60,
            capture_output=True,
            text=True,
            check=False,
        )

    try:
        res_start = run_cmd(
            "start",
            "--rate",
            "300",
            "--shm-dir",
            str(shm_dir),
            "--workdir",
            str(work_dir),
        )
        assert res_start.returncode == 0, res_start.stderr + res_start.stdout

        res_env = run_cmd("env")
        assert res_env.returncode == 0, res_env.stderr
        assert f'MILK_SHM_DIR="{shm_dir}"' in res_env.stdout
        assert "CACAOSIM_WORKDIR=" in res_env.stdout
        assert "CACAO_LOOPNAME=" in res_env.stdout

        res_status = run_cmd("status")
        assert res_status.returncode == 0, res_status.stderr
        assert "Active FPS instances" in res_status.stdout
        assert "csim_" in res_status.stdout

        res_turb = run_cmd("turb", "0.0")
        assert res_turb.returncode == 0, res_turb.stderr

        res_stop = run_cmd("stop")
        assert res_stop.returncode == 0, res_stop.stderr
    finally:
        if state_file.exists():
            run_cmd("stop")

    assert not shm_dir.exists()
    assert not state_file.exists()
