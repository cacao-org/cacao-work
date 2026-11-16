# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Verify cacaosim-bench deploy/teardown and live milkatmturb phase screens."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_turbulence_drives_scao_bench(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Confirm warm deploy, frame advance, PSF degradation, and clean teardown."""
    shm_dir, work_dir, env = shm_sandbox
    csim_dir = work_dir / "csim"
    dl_json = work_dir / "dl.json"
    turb_json = work_dir / "turb.json"
    pid_txt = work_dir / "pids.txt"

    script = f"""
set -euo pipefail
source "{repo_root}/env.sh"
source "{repo_root}/scripts/shm-sandbox.sh"
export MILK_SHM_DIR="{shm_dir}"
export MILK_PROC_DIR="{shm_dir}/proc"
export SANDBOX_WORK_DIR="{work_dir}"
export CACAOSIM_WORKDIR="{csim_dir}"

cleanup() {{
    cacaosim-bench teardown --workdir "{csim_dir}" --no-view >/dev/null 2>&1 || true
}}
trap cleanup EXIT

cacaosim-bench deploy \\
    --workdir "{csim_dir}" \\
    --config "{repo_root}/benches/scao_pyr/scao_pyr.bench" \\
    --mode fused --rate 300 --atmturb --seeing 0.8 --no-view >/dev/null

pid1="$(milk-script -q -e <<< '@get p="f.csim_htsim.runpid"; printf "%s\\n" "${{p}}"')"
cacaosim-bench deploy \\
    --workdir "{csim_dir}" \\
    --config "{repo_root}/benches/scao_pyr/scao_pyr.bench" \\
    --mode fused --rate 300 --atmturb --seeing 0.8 --no-view >/dev/null
pid2="$(milk-script -q -e <<< '@get p="f.csim_htsim.runpid"; printf "%s\\n" "${{p}}"')"
printf '%s %s\\n' "${{pid1}}" "${{pid2}}" > "{pid_txt}"

milk-stream-wait -q -t 20 csim_pup dm00disp
milk-stream-wait -q -t 20 outarraypha+5 csim_wfs+5 csim_fpcam+5 csim_fplong+5

csim_set_turb_gain 0.0
shm_wait_frames "csim_wfs" 20 15
csim_reset_long
shm_wait_frames "csim_fplong" 30 15
compute_ao_metrics "dl" "{dl_json}"

csim_set_turb_gain 1.0
shm_wait_frames "csim_wfs" 30 15
csim_reset_long
shm_wait_frames "csim_fplong" 60 20
compute_ao_metrics "turb" "{turb_json}"

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

    pid1, pid2 = pid_txt.read_text(encoding="utf-8").strip().split()
    assert int(pid1) > 0 and pid1 == pid2, (pid1, pid2)

    dl = json.loads(dl_json.read_text(encoding="utf-8"))
    turb = json.loads(turb_json.read_text(encoding="utf-8"))
    assert dl["strehl_peak"] > 0.85, dl
    assert turb["strehl_peak"] < 0.65, turb

    assert list(shm_dir.glob("csim_*.fps.shm")) == []
    assert list(shm_dir.glob("csim_*.im.shm")) == []
