# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Wind-layer compute unit (algo/windlayers): build, synthetic cube check, live stream check."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Synthetic layers built by `windlayers.milk selftest` (pattern velocity [m/s], distance [m])
TRUTH = (((18.75, 0.0), 8000.0), ((-6.25, 12.5), 15000.0))

# Replays two cubes into two streams, frame by frame: the OPD first, then the WFS frame that
# triggers the unit.
FEED_MILK = r"""#!/usr/bin/env -S milk-script -q
QC="$1"; PC="$2"; WS="$3"; PS="$4"; RATE="$5"
@get -v nz "s.${QC}.zsize"
unset t
for (( k = 0; k < nz; k++ )); do
    @calc "${PS} = ${PC}[*,*,${k}]; ${WS} = ${QC}[*,*,${k}]"
    @sleep --hz "${RATE}" t
done
"""


def _layers(text: str) -> list[tuple[float, float, float]]:
    """(vx, vy, z) of every layer row, from the unit's table (16 columns) or `report` (11)."""
    zcol = {16: 11, 11: 8}
    rows = []
    for line in text.splitlines():
        cols = line.split()
        if not re.match(r"^\s+\d+\s+-?[\d.]+\s+-?[\d.]+\s", line) or len(cols) not in zcol:
            continue
        rows.append((float(cols[1]), float(cols[2]), float(cols[zcol[len(cols)]])))
    return rows


def _has_layer(rows, vel, dist, dv, dz_frac) -> bool:
    for vx, vy, z in rows:
        if ((vx - vel[0]) ** 2 + (vy - vel[1]) ** 2) ** 0.5 < dv and abs(z / dist - 1) < dz_frac:
            return True
    return False


def test_windlayers_selftest(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Build the unit with milk-cc and recover two synthetic layers from telemetry cubes."""
    _, work_dir, env = shm_sandbox
    env = env | {"WINDLAYERS_BIN": str(work_dir / "bin")}
    tool = repo_root / "algo" / "windlayers" / "windlayers.milk"

    res = subprocess.run(
        [str(tool), "selftest"], cwd=work_dir, env=env, timeout=300, check=False,
        capture_output=True, text=True,
    )
    assert res.returncode == 0, f"stdout:\n{res.stdout}\nstderr:\n{res.stderr[-2000:]}"
    assert "[selftest] PASSED" in res.stdout
    assert (work_dir / "bin" / "cacao-fpsexec-windlayers").is_file()

    # the three input modes (intensity map, pyramid quadrants, given pupil centres) each print
    # the two layers
    rows = _layers(res.stdout)
    assert len(rows) == 6, res.stdout
    for vel, dist in TRUTH:
        assert sum(_has_layer([r], vel, dist, 0.3, 0.05) for r in rows) == 3, res.stdout


def test_windlayers_live_stream(
    repo_root: Path,
    shm_sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    """Run the unit on live streams and read the layers back from its outputs."""
    shm_dir, work_dir, env = shm_sandbox
    env = env | {"WINDLAYERS_BIN": str(work_dir / "bin")}
    tool = repo_root / "algo" / "windlayers" / "windlayers.milk"
    feed = work_dir / "feed.milk"
    feed.write_text(FEED_MILK, encoding="utf-8")
    feed.chmod(0o755)

    script = f"""
set -euo pipefail
"{tool}" selftest --keep >/dev/null
milk-script -q -e <<'EOF'
@calc "S:wlst_wfs = wlst_qcube[*,*,0]; S:wlst_pha = wlst_pcube[*,*,0]"
EOF
"{tool}" start wlst_wfs wlst_pha frate=200 diam=7.5 diampix=30 phaunit=1e-6 phasign=1 \\
    vmax=30 modrad=500 tupdate=3 twarm=1 >/dev/null
"{feed}" wlst_qcube wlst_pcube wlst_wfs wlst_pha 200
sleep 2
"{tool}" report
milk-script -q -e <<'EOF'
@get nf=f.windlayers.res.nframes nb=f.windlayers.res.nblocks st=f.windlayers.status
echo "UNIT status=$st frames=$nf blocks=$nb"
EOF
"{tool}" stop --rm
"""
    res = subprocess.run(
        ["bash", "-c", script], cwd=work_dir, env=env, timeout=400, check=False,
        capture_output=True, text=True,
    )
    assert res.returncode == 0, f"stdout:\n{res.stdout}\nstderr:\n{res.stderr[-2000:]}"
    m = re.search(r"UNIT status=(\w+) frames=(\d+) blocks=(\d+)", res.stdout)
    assert m, res.stdout
    assert m.group(1) == "running"
    assert int(m.group(2)) > 800 and int(m.group(3)) >= 2, res.stdout

    rows = _layers(res.stdout)
    for vel, dist in TRUTH:
        assert _has_layer(rows, vel, dist, 1.0, 0.2), res.stdout
    assert not list(shm_dir.glob("wl_*.im.shm"))
