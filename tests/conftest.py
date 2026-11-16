# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Shared pytest fixtures for isolated AO bench integration testing."""

from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

_SANDBOX_SEQ = itertools.count(1)


def _prepend_env_path(existing: str | None, *entries: str) -> str:
    parts = [entry for entry in entries if entry]
    if existing:
        parts.extend(p for p in existing.split(":") if p and p not in parts)
    return ":".join(parts)


def _find_src_dir(repo_root: Path, name: str) -> str:
    for candidate in (repo_root.parent / name, Path.home() / "src" / name):
        if candidate.is_dir():
            return str(candidate)
    return str(repo_root.parent / name)


def _find_install_root(env: dict[str, str], milk_src: str) -> str:
    explicit = env.get("MILK_INSTALL_ROOT")
    if explicit and (Path(explicit) / "bin" / "milk-cli").is_file():
        return explicit
    install_dir = Path(milk_src) / "_install"
    candidates = sorted(
        p for p in install_dir.glob("milk-*") if (p / "bin" / "milk-cli").is_file()
    )
    if candidates:
        return str(candidates[-1])
    if (install_dir / "bin" / "milk-cli").is_file():
        return str(install_dir)
    for key in ("MILK_INSTALLDIR", "MILK_ROOT"):
        val = env.get(key)
        if val and (Path(val) / "bin" / "milk-cli").is_file():
            return val
    milk_cli = shutil.which("milk-cli")
    if milk_cli:
        return str(Path(milk_cli).resolve().parent.parent)
    return str(install_dir)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the root directory of the cacao-work repository."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def stack_env(repo_root: Path) -> dict[str, str]:
    """Build environment variables matching env.sh for subprocess calls."""
    env = os.environ.copy()
    preserved_src = {
        key: env[key]
        for key in ("CACAO_SRC_DIR", "CACAOSIM_SRC_DIR")
        if key in env
    }
    for k in list(env):
        if k.startswith("CACAO_") and k != "CACAO_WORK_ROOT":
            env.pop(k, None)
    milk_src = env.get("MILK_SRC_DIR") or _find_src_dir(repo_root, "milk")
    cacao_src = preserved_src.get("CACAO_SRC_DIR") or _find_src_dir(repo_root, "cacao")
    cacaosim_src = preserved_src.get("CACAOSIM_SRC_DIR") or _find_src_dir(
        repo_root, "cacaosim"
    )
    install_root = _find_install_root(env, milk_src)
    python_bin = env.get("PYTHON_BIN") or sys.executable

    env["CACAO_WORK_ROOT"] = str(repo_root)
    env["MILK_SRC_DIR"] = milk_src
    env["CACAO_SRC_DIR"] = cacao_src
    env["CACAOSIM_SRC_DIR"] = cacaosim_src
    env["MILK_INSTALL_ROOT"] = install_root
    env["MILK_INSTALLDIR"] = install_root
    env["MILK_ROOT"] = install_root
    env["PYTHON_BIN"] = python_bin
    env["ATMTURB_MASTER_SIZE"] = env.get("ATMTURB_MASTER_SIZE", "512")
    env["MILK_QUIET"] = "1"
    if not env.get("TERM") or env.get("TERM") == "dumb":
        env["TERM"] = "xterm-256color"

    env["PATH"] = _prepend_env_path(
        env.get("PATH"),
        f"{install_root}/bin",
        str(Path(python_bin).parent),
        str(repo_root / "scripts"),
    )
    env["LD_LIBRARY_PATH"] = _prepend_env_path(
        env.get("LD_LIBRARY_PATH"),
        f"{install_root}/lib",
    )
    return env


@pytest.fixture
def shm_sandbox(
    stack_env: dict[str, str],
    repo_root: Path,
) -> Iterator[tuple[Path, Path, dict[str, str]]]:
    """Create an isolated /dev/shm and work directory sandbox per test."""
    idx = next(_SANDBOX_SEQ)
    pid = os.getpid()
    shm_dir = Path(f"/dev/shm/cacao_pt_{idx}_{pid}")
    work_dir = Path(f"/tmp/cacao_pt_{idx}_{pid}")
    proc_dir = shm_dir / "proc"
    csim_dir = work_dir / "csim"

    shm_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    csim_dir.mkdir(parents=True, exist_ok=True)

    env = stack_env.copy()
    env["MILK_SHM_DIR"] = str(shm_dir)
    env["MILK_PROC_DIR"] = str(proc_dir)
    env["CACAOSIM_WORKDIR"] = str(csim_dir)

    try:
        yield shm_dir, work_dir, env
    finally:
        subprocess.run(
            [
                "bash",
                "-c",
                (
                    "source scripts/shm-sandbox.sh; "
                    f'CACAOSIM_WORKDIR="{csim_dir}" sandbox_stop_all'
                ),
            ],
            cwd=repo_root,
            env=env,
            timeout=20,
            check=False,
            capture_output=True,
            text=True,
        )
        shutil.rmtree(shm_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        assert not shm_dir.exists()
