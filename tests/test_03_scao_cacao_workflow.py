# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end SCAO validation via fpspipe init and cacao-aorun-* scripts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_scao_cacao_workflow(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Verify fpspipe --init-only + cacao-aorun-* closed-loop workflow."""
    shm_dir, work_dir, env = shm_sandbox
    metrics_path = work_dir / "metrics.json"

    res = subprocess.run(
        [
            str(repo_root / "scripts" / "run-scao-cacao-workflow.sh"),
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
        timeout=180,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    assert metrics_path.is_file()

    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    dl, ol, cl = data["dl"], data["ol"], data["cl"]

    assert dl["strehl_peak"] > 0.85, data
    assert cl["strehl_peak"] > ol["strehl_peak"] + 0.04, data
    assert cl["strehl_fps_ave"] > ol["strehl_fps_ave"] + 0.04, data
    assert cl["strehl_peak"] > ol["strehl_peak"] * 2.2, data
    assert cl["wfs_rms"] < ol["wfs_rms"] * 0.98, data
    assert cl["mval_rms"] < ol["mval_rms"] * 0.85, data
    assert cl["dm_rms"] > 0.05, data

    loop_dir = work_dir / "scao_pyr"
    assert (loop_dir / "cacaovars.scao_pyr.bash").is_file()
    assert (loop_dir / "conf" / "CMmodesDM.fits").is_file()
    assert list(shm_dir.glob("*.fps.shm")) == []
