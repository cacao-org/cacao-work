#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Offline walk-forward ridge-AR and cross-mode Block-EOF solvers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .loader import load_fits_cube

def run_walk_forward_study(work_root: Path) -> dict[str, Any]:
    """Run exact Wiener-ridge walk-forward out-of-sample evaluation on clean AR(16) OL cubes."""
    tlm_dir = work_root / "ao3k_scexao_predictive_ar16" / "telemetry"
    orders = [1, 2, 4, 8, 12, 16, 24, 32, 48, 64]
    ntrains = [256, 512, 1024, 2048]
    results: dict[str, Any] = {"orders": orders, "ntrains": ntrains, "stages": {}}

    for stg, lat_fr in ((1, 2.40), (2, 2.58)):
        ol = load_fits_cube(tlm_dir, f"aol{stg}_modevalOL")
        assert ol is not None
        lat_i = int(lat_fr)
        lat_a = lat_fr - lat_i
        n_t, n_m_tot = ol.shape
        t_te0 = n_t // 2
        t_te1 = n_t - lat_i - 2
        idx_te = np.arange(t_te0, t_te1)

        # Grid over (ntrain, order) evaluated on all modes (vectorized via stride)
        # To keep runtime fast (<5 s), sample all low/mid modes (0..256) + every 4th high mode
        high_step = 4
        mode_idx = np.concatenate(
            [np.arange(min(256, n_m_tot)), np.arange(256, n_m_tot, high_step)]
        )
        mode_weights = np.ones(mode_idx.shape[0], dtype=np.float64)
        mode_weights[256:] = float(high_step)

        grid_in: dict[int, list[float]] = {}
        grid_out: dict[int, list[float]] = {}
        bands_2048: dict[str, dict[int, dict[str, float]]] = {
            "tt_low": {},
            "mid": {},
            "high": {},
            "all": {},
        }

        for ntr in ntrains:
            in_vals: list[float] = []
            out_vals: list[float] = []
            for p_ord in orders:
                idx_tr = np.arange(p_ord - 1, ntr - lat_i - 1)
                vz_i = vp_i = vz_o = vp_o = 0.0
                b_acc = {
                    b: [0.0, 0.0, 0.0, 0.0] for b in ("tt_low", "mid", "high", "all")
                }
                eye_p = np.eye(p_ord, dtype=np.float64)
                for pos, m_i in enumerate(mode_idx):
                    wt = mode_weights[pos]
                    ts = ol[:, m_i]
                    x_tr = np.column_stack([ts[idx_tr - k] for k in range(p_ord)])
                    y_tr = (1.0 - lat_a) * ts[idx_tr + lat_i] + lat_a * ts[idx_tr + lat_i + 1]
                    gram = x_tr.T @ x_tr
                    rhs = x_tr.T @ y_tr
                    tr_g = float(np.trace(gram)) / float(p_ord)
                    if tr_g <= 1e-26:
                        continue
                    lam = 0.005 * tr_g
                    w = np.linalg.solve(gram + lam * eye_p, rhs)
                    for _ in range(12):
                        if float(np.dot(w, w)) <= 1.35 and abs(float(np.sum(w))) <= 1.01:
                            break
                        lam *= 3.0
                        w = np.linalg.solve(gram + lam * eye_p, rhs)
                    dc = float(np.sum(w))
                    if abs(dc) > 0.985:
                        w *= 0.985 / abs(dc)

                    zi = float(np.mean((y_tr - ts[idx_tr]) ** 2)) * wt
                    pi = float(np.mean((y_tr - x_tr @ w) ** 2)) * wt

                    x_te = np.column_stack([ts[idx_te - k] for k in range(p_ord)])
                    y_te = (1.0 - lat_a) * ts[idx_te + lat_i] + lat_a * ts[idx_te + lat_i + 1]
                    zo = float(np.mean((y_te - ts[idx_te]) ** 2)) * wt
                    po = float(np.mean((y_te - x_te @ w) ** 2)) * wt

                    vz_i += zi
                    vp_i += pi
                    vz_o += zo
                    vp_o += po

                    if ntr == 2048 and p_ord in (4, 8, 16, 32, 64):
                        bkey = "tt_low" if m_i < 20 else ("mid" if m_i < 256 else "high")
                        for bk in (bkey, "all"):
                            b_acc[bk][0] += zi
                            b_acc[bk][1] += pi
                            b_acc[bk][2] += zo
                            b_acc[bk][3] += po

                vr_i = (1.0 - vp_i / max(vz_i, 1e-30)) * 100.0
                vr_o = (1.0 - vp_o / max(vz_o, 1e-30)) * 100.0
                in_vals.append(vr_i)
                out_vals.append(vr_o)

                if ntr == 2048 and p_ord in (4, 8, 16, 32, 64):
                    for bk, vals in b_acc.items():
                        bands_2048[bk][p_ord] = {
                            "in_pct": (1.0 - vals[1] / max(vals[0], 1e-30)) * 100.0,
                            "out_pct": (1.0 - vals[3] / max(vals[2], 1e-30)) * 100.0,
                        }

            grid_in[ntr] = in_vals
            grid_out[ntr] = out_vals

        results["stages"][f"stage{stg}"] = {
            "lag_fr": lat_fr,
            "in_pct": {str(k): v for k, v in grid_in.items()},
            "out_pct": {str(k): v for k, v in grid_out.items()},
            "bands_2048": {
                bk: {str(p): v for p, v in pmap.items()} for bk, pmap in bands_2048.items()
            },
        }
    return results


def _solve_diag_ar_block(
    u: np.ndarray,
    idx_tr: np.ndarray,
    idx_te: np.ndarray,
    lat_i: int,
    lat_a: float,
    p_ord: int,
    reg: float,
    max_n2: float | None = 1.35,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve per-mode diagonal AR(P) on a slice of modes and return (zoh, pred, n2)."""
    n_m = u.shape[1]
    y_tr = (1.0 - lat_a) * u[idx_tr + lat_i] + lat_a * u[idx_tr + lat_i + 1]
    y_te = (1.0 - lat_a) * u[idx_te + lat_i] + lat_a * u[idx_te + lat_i + 1]
    zoh = np.mean((y_te - u[idx_te]) ** 2, axis=0)
    pred = np.zeros(n_m, dtype=np.float64)
    n2_arr = np.zeros(n_m, dtype=np.float64)
    eye_p = np.eye(p_ord, dtype=np.float64)
    for m in range(n_m):
        ts = u[:, m]
        x_tr = np.column_stack([ts[idx_tr - k] for k in range(p_ord)])
        g = x_tr.T @ x_tr
        rhs = x_tr.T @ y_tr[:, m]
        tr = float(np.trace(g)) / float(p_ord)
        if tr <= 1e-26:
            continue
        lam = reg * tr
        w = np.linalg.solve(g + lam * eye_p, rhs)
        if max_n2 is not None:
            for _ in range(12):
                if float(np.dot(w, w)) <= max_n2 and abs(float(np.sum(w))) <= 1.01:
                    break
                lam *= 3.0
                w = np.linalg.solve(g + lam * eye_p, rhs)
            dc = float(np.sum(w))
            if abs(dc) > 0.985:
                w *= 0.985 / abs(dc)
        n2_arr[m] = float(np.dot(w, w))
        x_te = np.column_stack([ts[idx_te - k] for k in range(p_ord)])
        pred[m] = float(np.mean((y_te[:, m] - x_te @ w) ** 2))
    return zoh, pred, n2_arr


def _solve_eof_block(
    u: np.ndarray,
    idx_tr: np.ndarray,
    idx_te: np.ndarray,
    lat_i: int,
    lat_a: float,
    p_ord: int,
    reg: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve isotropic-ridge cross-mode Block-EOF on u [N x b] -> (zoh, pred, n2)."""
    b = u.shape[1]
    d_f = p_ord * b
    x_tr = np.hstack([u[idx_tr - k] for k in range(p_ord)])
    y_tr = (1.0 - lat_a) * u[idx_tr + lat_i] + lat_a * u[idx_tr + lat_i + 1]
    x_te = np.hstack([u[idx_te - k] for k in range(p_ord)])
    y_te = (1.0 - lat_a) * u[idx_te + lat_i] + lat_a * u[idx_te + lat_i + 1]
    zoh = np.mean((y_te - u[idx_te]) ** 2, axis=0)
    g = x_tr.T @ x_tr
    rhs = x_tr.T @ y_tr
    tr = float(np.trace(g)) / float(d_f)
    g.flat[:: d_f + 1] += reg * tr
    w = np.linalg.solve(g, rhs)
    yh = x_te @ w
    pred = np.mean((y_te - yh) ** 2, axis=0)
    n2_arr = np.sum(w**2, axis=0)
    return zoh, pred, n2_arr


def run_eof_offline_20s_study(work_root: Path) -> dict[str, Any]:
    """Walk-forward 20 s offline study: Cross-Mode Block-EOF vs. Per-Mode Diagonal AR(16)."""
    tlm_dir = work_root / "ao3k_scexao_tlm20s_ar16" / "telemetry"
    ol1 = load_fits_cube(tlm_dir, "aol1_modevalOL")
    ol2 = load_fits_cube(tlm_dir, "aol2_modevalOL")
    assert ol1 is not None and ol2 is not None

    def _vr(zoh: np.ndarray, prd: np.ndarray) -> float:
        return (1.0 - float(np.sum(prd)) / max(float(np.sum(zoh)), 1e-30)) * 100.0

    # 1. Sample-complexity curve on Stage 1 Block 0 [0:128] (test = last 5 s [15000:])
    lat1 = 2.40
    li1, la1 = int(lat1), lat1 - int(lat1)
    te1 = np.arange(15000, ol1.shape[0] - li1 - 2)
    ntrs_s1 = [2048, 4096, 6144, 8192, 10240, 12288, 14500]
    sc_ar16_def: list[float] = []
    sc_ar16_low: list[float] = []
    sc_eof64: list[float] = []
    sc_eof128: list[float] = []
    for ntr in ntrs_s1:
        itr = np.arange(15, ntr - li1 - 1)
        z_a, p_a, _ = _solve_diag_ar_block(ol1[:, :128], itr, te1, li1, la1, 16, 5e-3, 1.35)
        z_l, p_l, _ = _solve_diag_ar_block(ol1[:, :128], itr, te1, li1, la1, 16, 1e-4, 1.35)
        z_64a, p_64a, _ = _solve_eof_block(ol1[:, :64], itr, te1, li1, la1, 8, 1e-4)
        z_64b, p_64b, _ = _solve_eof_block(ol1[:, 64:128], itr, te1, li1, la1, 8, 1e-4)
        z_128, p_128, _ = _solve_eof_block(ol1[:, :128], itr, te1, li1, la1, 8, 1e-4)
        sc_ar16_def.append(_vr(z_a, p_a))
        sc_ar16_low.append(_vr(z_l, p_l))
        sc_eof64.append(_vr(np.concatenate([z_64a, z_64b]), np.concatenate([p_64a, p_64b])))
        sc_eof128.append(_vr(z_128, p_128))

    # 2. Full-pupil block-by-block comparison (all 16 Stage-1 + all 10 Stage-2 blocks, B=128)
    blocks_out: dict[str, dict[str, Any]] = {}
    for skey, ol, lat, ntr, te0, reg_eof in (
        ("stage1", ol1, 2.40, 14500, 15000, 1e-4),
        ("stage2", ol2, 2.58, 29000, 30000, 1e-2),
    ):
        li, la = int(lat), lat - int(lat)
        itr = np.arange(15, ntr - li - 1)
        ite = np.arange(te0, ol.shape[0] - li - 2)
        n_m = ol.shape[1]
        b_sz = 128
        nblk = (n_m + b_sz - 1) // b_sz
        blk_labels: list[str] = []
        vr_ar_def: list[float] = []
        vr_ar_mat: list[float] = []
        vr_eof: list[float] = []
        z_tot = p_ar_def_tot = p_ar_mat_tot = p_eof_tot = 0.0
        for bk in range(nblk):
            s0 = bk * b_sz
            s1 = min(s0 + b_sz, n_m)
            u = ol[:, s0:s1]
            z_d, p_d, _ = _solve_diag_ar_block(u, itr, ite, li, la, 16, 5e-3, 1.35)
            _, p_m, _ = _solve_diag_ar_block(u, itr, ite, li, la, 16, reg_eof, 1.35)
            z_e, p_e, _ = _solve_eof_block(u, itr, ite, li, la, 8, reg_eof)
            blk_labels.append(f"{s0}-{s1 - 1}")
            vr_ar_def.append(_vr(z_d, p_d))
            vr_ar_mat.append(_vr(z_d, p_m))
            vr_eof.append(_vr(z_e, p_e))
            z_tot += float(np.sum(z_d))
            p_ar_def_tot += float(np.sum(p_d))
            p_ar_mat_tot += float(np.sum(p_m))
            p_eof_tot += float(np.sum(p_e))
        blocks_out[skey] = {
            "n_train": ntr,
            "lag_fr": lat,
            "labels": blk_labels,
            "ar16_def_pct": vr_ar_def,
            "ar16_mat_pct": vr_ar_mat,
            "eof128_pct": vr_eof,
            "tot_ar16_def_pct": (1.0 - p_ar_def_tot / max(z_tot, 1e-30)) * 100.0,
            "tot_ar16_mat_pct": (1.0 - p_ar_mat_tot / max(z_tot, 1e-30)) * 100.0,
            "tot_eof128_pct": (1.0 - p_eof_tot / max(z_tot, 1e-30)) * 100.0,
        }

    # 3. Noise-gain Pareto frontier on Stage 1 Block 0 [0:128] (modes 20..127 & 0..19)
    itr1 = np.arange(15, 14500 - li1 - 1)
    lams = [1e-6, 3e-6, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2]
    pareto: dict[str, list[dict[str, float]]] = {"diag_ar16": [], "eof128_p8": []}
    for lam in lams:
        z_a, p_a, n2_a = _solve_diag_ar_block(ol1[:, :128], itr1, te1, li1, la1, 16, lam, None)
        z_e, p_e, n2_e = _solve_eof_block(ol1[:, :128], itr1, te1, li1, la1, 8, lam)
        pareto["diag_ar16"].append(
            {
                "lam": lam,
                "vr_all": _vr(z_a, p_a),
                "vr_0_19": _vr(z_a[:20], p_a[:20]),
                "vr_20_127": _vr(z_a[20:], p_a[20:]),
                "n2_med": float(np.median(n2_a)),
                "n2_p95": float(np.percentile(n2_a, 95)),
            }
        )
        pareto["eof128_p8"].append(
            {
                "lam": lam,
                "vr_all": _vr(z_e, p_e),
                "vr_0_19": _vr(z_e[:20], p_e[:20]),
                "vr_20_127": _vr(z_e[20:], p_e[20:]),
                "n2_med": float(np.median(n2_e)),
                "n2_p95": float(np.percentile(n2_e, 95)),
            }
        )

    return {
        "sample_complexity": {
            "ntrains": ntrs_s1,
            "ar16_def_pct": sc_ar16_def,
            "ar16_low_pct": sc_ar16_low,
            "eof64_p8_pct": sc_eof64,
            "eof128_p8_pct": sc_eof128,
        },
        "blocks": blocks_out,
        "pareto": pareto,
    }
