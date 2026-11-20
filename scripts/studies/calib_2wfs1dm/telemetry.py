#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Telemetry loaders, resampling, and milk-mlt-calib2wfs1dm runner."""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import subprocess
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


def load_selfrm_og(base_dir: Path, n_modes: int = 40) -> np.ndarray:
    """Compute on-sky/calibration active selfRM modal optical gain vector."""
    sc = fits.getdata(base_dir / "selfRM_calib_stg2.fits").astype(np.float64)
    ss = fits.getdata(base_dir / "selfRM_onsky_stg2.fits").astype(np.float64)
    zc = int(np.argmax([np.mean(np.abs(np.diag(sc[z, :n_modes, :n_modes]))) for z in range(len(sc))]))
    zs = int(np.argmax([np.mean(np.abs(np.diag(ss[z, :n_modes, :n_modes]))) for z in range(len(ss))]))
    return np.diag(ss[zs, :n_modes, :n_modes]) / np.maximum(np.diag(sc[zc, :n_modes, :n_modes]), 1e-6)


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
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"milk-mlt-calib2wfs1dm failed:\n{res.stderr}\n{res.stdout}")
    return json.loads(sum_json.read_text(encoding="utf-8"))
