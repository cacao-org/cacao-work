# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Sanity checks for build prefix, bench DAG/plan compiler, and clean scripts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def test_build_all_check_only(repo_root: Path, stack_env: dict[str, str]) -> None:
    """Verify all expected binaries, libs, and commands.d modules are installed."""
    res = subprocess.run(
        [str(repo_root / "scripts" / "build-all.sh"), "--check-only"],
        cwd=repo_root,
        env=stack_env,
        timeout=30,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    assert "OK: verified" in res.stdout


def test_bench_dag_valid(repo_root: Path, stack_env: dict[str, str]) -> None:
    """Verify the scao_pyr optical bench configuration defines a valid DAG."""
    res = subprocess.run(
        [
            "cacaosim-bench",
            "view",
            str(repo_root / "benches" / "scao_pyr" / "scao_pyr.bench"),
            "--no-footer",
        ],
        cwd=repo_root,
        env=stack_env,
        timeout=30,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    assert "VALID DAG" in res.stdout


def test_bench_plan_compiler(
    repo_root: Path,
    stack_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """Verify cacaosim-bench-view --emit-plan compiles modular fpspipe artifacts."""
    plan_dir = tmp_path / "plan"
    res = subprocess.run(
        [
            "cacaosim-bench-view",
            "--emit-plan",
            str(plan_dir),
            "--mode",
            "modular",
            "--atmturb",
            "--rate",
            "400",
            str(repo_root / "benches" / "scao_pyr" / "scao_pyr.bench"),
        ],
        cwd=repo_root,
        env=stack_env,
        timeout=30,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
    for artifact in ("units.manifest", "params.batch", "units.list", "streams.list", "meta.tsv"):
        assert (plan_dir / artifact).is_file(), f"missing {artifact}"


def test_milk_loop_controller_help(
    repo_root: Path,
    stack_env: dict[str, str],
) -> None:
    """Verify cacaoloop-scao-pyr.milk executes cleanly via milk-script."""
    ctrl = str(repo_root / "benches" / "scao_pyr" / "cacaoloop-scao-pyr.milk")
    for flag in ("-h1", "-h2", "-hm"):
        res = subprocess.run(
            [ctrl, flag],
            cwd=repo_root,
            env=stack_env,
            timeout=15,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"{flag} stderr:\n{res.stderr}\nstdout:\n{res.stdout}"
        assert res.stdout.strip()


def test_no_multiplexer_in_workspace(repo_root: Path) -> None:
    """Ensure all workspace scripts and configs omit legacy multiplexer calls."""
    forbidden = ("tmu" + "x", "TMUX_" + "TMPDIR", "cacao-" + "setup")
    files = [
        repo_root / "env.sh",
        *sorted((repo_root / "scripts").glob("*.sh")),
        *sorted((repo_root / "benches").rglob("*.milk")),
        *sorted((repo_root / "benches").rglob("*.bench")),
        *sorted((repo_root / "tests").glob("*.py")),
    ]
    offenders: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path.relative_to(repo_root)}: contains {token!r}")
    assert not offenders, "\n".join(offenders)


def test_sibling_repo_branch_safety(stack_env: dict[str, str]) -> None:
    """Confirm milk and cacao checkouts are not sitting on protected dev branches."""
    checked = 0
    for key in ("MILK_SRC_DIR", "CACAO_SRC_DIR"):
        repo = Path(stack_env[key])
        if not (repo / ".git").exists():
            continue
        res = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            timeout=10,
            capture_output=True,
            text=True,
            check=True,
        )
        branch = res.stdout.strip()
        assert branch and branch != "dev", f"{repo} is on forbidden branch {branch!r}"
        checked += 1
    if checked == 0:
        pytest.skip("No local milk/cacao git checkouts found under configured source dirs")
