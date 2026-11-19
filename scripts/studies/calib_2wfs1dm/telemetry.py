#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Telemetry loaders, selfRM references, git provenance, and milk-mlt-calib2wfs1dm runner."""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from astropy.io import fits
import numpy as np


def load_tlm(tlm_dir: Path, prefix: str, max_m: int) -> tuple[np.ndarray, np.ndarray]:
    """Load paired .fits/.txt telemetry cubes into (N, M) array and timestamp vector."""
    files = sorted(glob.glob(str(tlm_dir / f"{prefix}_*.fits")))
    if not files:
        raise FileNotFoundError(f"No {prefix}_*.fits in {tlm_dir}")
    arrs: list[np.ndarray] = []
    ts: list[np.ndarray] = []
    for fpath in files:
        data = fits.getdata(fpath).astype(np.float64)
        data = data.reshape(data.shape[0], -1)[:, :max_m]
        rows = np.loadtxt(fpath[:-5] + ".txt", usecols=(3, 4))
        tvec = rows[:, 1] if np.any(rows[:, 1] > 0) else rows[:, 0]
        n = min(len(data), len(tvec))
        arrs.append(data[:n])
        ts.append(tvec[:n])
    return np.concatenate(arrs, axis=0), np.concatenate(ts, axis=0)


def load_tlm_2d(tlm_dir: Path, prefix: str) -> tuple[np.ndarray, np.ndarray]:
    """Load paired 2D-frame .fits/.txt telemetry cubes into (N, Ny, Nx) and timestamps."""
    files = sorted(glob.glob(str(tlm_dir / f"{prefix}_*.fits")))
    if not files:
        raise FileNotFoundError(f"No {prefix}_*.fits in {tlm_dir}")
    arrs: list[np.ndarray] = []
    ts: list[np.ndarray] = []
    for fpath in files:
        data = fits.getdata(fpath).astype(np.float64)
        rows = np.loadtxt(fpath[:-5] + ".txt", usecols=(3, 4))
        tvec = rows[:, 1] if np.any(rows[:, 1] > 0) else rows[:, 0]
        n = min(len(data), len(tvec))
        arrs.append(data[:n])
        ts.append(tvec[:n])
    return np.concatenate(arrs, axis=0), np.concatenate(ts, axis=0)


def sync_window(
    t_ref: np.ndarray,
    arr: np.ndarray,
    t_src: np.ndarray,
    dt_win: float,
    lag_s: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Window-average source samples inside [t_ref - lag_s - dt/2, t_ref - lag_s + dt/2]."""
    tq = t_ref - lag_s
    i0 = np.searchsorted(t_src, tq - 0.5 * dt_win, side="left")
    i1 = np.searchsorted(t_src, tq + 0.5 * dt_win, side="right")
    out = np.zeros((len(t_ref), arr.shape[1]), dtype=np.float64)
    ok = np.zeros(len(t_ref), dtype=bool)
    for k in range(len(t_ref)):
        if i1[k] > i0[k]:
            out[k] = arr[i0[k] : i1[k]].mean(axis=0)
            ok[k] = True
    return out, ok


def load_selfrm_og(base_dir: Path, n_modes: int = 40, stage: int = 2) -> np.ndarray:
    """Same-lag-slice selfRM modal optical gain (simulated on-sky / calibration ratio).

    One lag slice is chosen per cube (largest mean |diag|) and used for every mode, and the
    signed diagonals are divided. This is the ALTERNATE reference; the primary one is the
    per-mode peak-|diag| ratio written by milk-mlt-calib2wfs1dm (og_selfrm.fits). Returns an
    empty vector when the selfRM cubes are absent.
    """
    p_cal = base_dir / f"selfRM_calib_stg{stage}.fits"
    p_sky = base_dir / f"selfRM_onsky_stg{stage}.fits"
    if not (p_cal.is_file() and p_sky.is_file()):
        return np.zeros(0)
    sc = fits.getdata(p_cal).astype(np.float64)
    ss = fits.getdata(p_sky).astype(np.float64)
    n = min(n_modes, sc.shape[1], sc.shape[2], ss.shape[1], ss.shape[2])
    zc = int(np.argmax([np.mean(np.abs(np.diag(s[:n, :n]))) for s in sc]))
    zs = int(np.argmax([np.mean(np.abs(np.diag(s[:n, :n]))) for s in ss]))
    return np.diag(ss[zs, :n, :n]) / np.maximum(np.diag(sc[zc, :n, :n]), 1e-6)


def load_reference_og(
    base_dir: Path, calib_dir: Path, n_modes: int = 40
) -> tuple[np.ndarray, np.ndarray, str]:
    """Return (primary, alternate, primary_kind) selfRM optical-gain reference vectors.

    Every error in the report is measured against the PRIMARY vector so that tables, figures
    and prose share a single reference. The primary is og_selfrm.fits from the calibration
    tool (per-mode peak ratio, kind "peak"), which is also what the live run summary plots;
    the alternate is the same-lag-slice ratio. Their spread is reported as the reference
    uncertainty. Falls back to the same-slice ratio (kind "slice") if og_selfrm.fits is absent.
    """
    alt = load_selfrm_og(base_dir, n_modes)
    p_og = calib_dir / "og_selfrm.fits"
    if p_og.is_file():
        pri = fits.getdata(p_og).astype(np.float64).ravel()[:n_modes]
        if pri.size == n_modes and np.any(pri > 1e-6):
            return pri, (alt if alt.size == n_modes else pri), "peak"
    if alt.size != n_modes:
        raise FileNotFoundError(f"No usable selfRM optical-gain reference under {base_dir}")
    return alt, alt, "slice"


def load_vec(path: Path) -> np.ndarray | None:
    """Load a FITS vector as float64, or None when the file does not exist."""
    return fits.getdata(path).astype(np.float64).ravel() if path.is_file() else None


def git_state(repo_dir: Path) -> dict[str, Any]:
    """Commit, branch and uncommitted-change flag of a git checkout (blank if not a repo)."""

    def query(*args: str) -> str | None:
        try:
            res = subprocess.run(
                ["git", "-C", str(repo_dir), *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return res.stdout.strip() if res.returncode == 0 else None

    sha = query("rev-parse", "HEAD") or ""
    status = query("status", "--porcelain", "--untracked-files=no") if sha else None
    return {
        "commit": sha,
        "short_commit": sha[:7],
        "branch": query("rev-parse", "--abbrev-ref", "HEAD") or "",
        "dirty": None if status is None else bool(status),
    }


def flags_missing_at_commit(repo_dir: Path, sha: str, run_cmd: str) -> list[str]:
    """Options used in `run_cmd` that do not exist anywhere in scripts/ or benches/ at `sha`.

    A non-empty result means the run was launched from a working tree newer than the recorded
    commit. Returns [] when the commit is not available locally.
    """
    if not sha or not run_cmd:
        return []
    flags = sorted({tok for tok in run_cmd.split() if tok.startswith("--") and len(tok) > 2})
    missing: list[str] = []
    for flag in flags:
        try:
            res = subprocess.run(
                ["git", "-C", str(repo_dir), "grep", "-q", "-F", "-e", flag, sha, "--"]
                + ["scripts", "benches"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if res.returncode == 1:
            missing.append(flag)
        elif res.returncode != 0:
            return []
    return missing


def resample_dm2_to_dm1(
    img2: np.ndarray,
    ny1: int = 64,
    nx1: int = 64,
    d1: float = 60.0,
    d2: float = 46.0,
) -> np.ndarray:
    """Bilinearly project a 50x50 DM2 (D=46) shape onto the 64x64 DM1 (D=60) pupil grid."""
    ny2, nx2 = img2.shape
    c1y, c1x = (ny1 - 1) / 2.0, (nx1 - 1) / 2.0
    c2y, c2x = (ny2 - 1) / 2.0, (nx2 - 1) / 2.0
    yy, xx = np.indices((ny1, nx1), dtype=np.float64)
    y2 = c2y + (yy - c1y) * (d2 / d1)
    x2 = c2x + (xx - c1x) * (d2 / d1)
    y0 = np.clip(np.floor(y2).astype(int), 0, ny2 - 1)
    y1 = np.clip(y0 + 1, 0, ny2 - 1)
    x0 = np.clip(np.floor(x2).astype(int), 0, nx2 - 1)
    x1 = np.clip(x0 + 1, 0, nx2 - 1)
    wy = np.clip(y2 - y0, 0.0, 1.0)
    wx = np.clip(x2 - x0, 0.0, 1.0)
    out = (
        (1.0 - wy) * (1.0 - wx) * img2[y0, x0]
        + (1.0 - wy) * wx * img2[y0, x1]
        + wy * (1.0 - wx) * img2[y1, x0]
        + wy * wx * img2[y1, x1]
    )
    oob = (y2 < 0) | (y2 > ny2 - 1) | (x2 < 0) | (x2 > nx2 - 1)
    out[oob] = 0.0
    return out


def run_calib2wfs1dm_cli(
    base_dir: Path,
    out_dir: Path,
    *,
    lag_ab: str = "auto",
    lag_db: str = "auto",
    whiten_order: int = 4,
    maxframes: int = 0,
) -> dict[str, Any]:
    """Run milk-mlt-calib2wfs1dm (or reuse cached summary if already present)."""
    sum_json = out_dir / "sysid_summary.json"
    if not sum_json.is_file():
        out_dir.mkdir(parents=True, exist_ok=True)
        sc2 = base_dir / "selfRM_calib_stg2.fits"
        ss2 = base_dir / "selfRM_onsky_stg2.fits"
        cmd = [
            "milk-mlt-calib2wfs1dm",
            str(base_dir / "telemetry"),
            str(out_dir),
            "aol1_modevalWFS",
            "aol2_modevalWFS",
            "aol2_modevalDM",
            "60",
            "40",
            "40",
            lag_ab,
            lag_db,
            str(whiten_order),
            "0.02",
            "0.70",
            str(sc2) if sc2.is_file() else "",
            str(ss2) if ss2.is_file() else "",
            "",
            "",
            "",
            "",
            str(maxframes),
        ]
        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = "16"
        env["OPENBLAS_NUM_THREADS"] = "1"
        t_cli = time.perf_counter()
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"milk-mlt-calib2wfs1dm failed:\n{res.stderr}\n{res.stdout}")
        (out_dir / "cli_elapsed_s.txt").write_text(
            f"{time.perf_counter() - t_cli:.3f}\n", encoding="utf-8"
        )
    return json.loads(sum_json.read_text(encoding="utf-8"))
