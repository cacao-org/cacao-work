#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Calibration helpers for PyWFS mask dilation and harmonic DM actuator slaving.

Subcommands:
  dilate-wfsmask    Central-obstruction-cavity (default) or full Euclidean-disk
                    dilation of a 2D PyWFS pixel mask.
  harmonic-slave-dm Strictly linear discrete harmonic slaving (Laplacian = 0) of
                    uncontrolled central-obstruction and outer-rim DM actuators
                    across a 3D DM modal basis cube.

Why CO-cavity PyWFS mask dilation (instead of isotropic dilation into spider arms):
  On an unmodulated PyWFS, the Hilbert transform pushes flat-wavefront flux out of
  the inner central-obstruction edge, carving oversized CO holes in `wfsmask`.
  Dilating inward into each quadrant's CO cavity (`r <= cobs_scale * r_co`) recovers
  sensitivity to CO-rim/corner phase wraps without adding outer dark-bias pixels or
  radial spider-arm shadow pixels (where strictly positive quadratic diffraction
  from thermal petaling across the spider can drive high-order across-spider dipole
  modes past the plate-DM stroke rail).

Why harmonic slaving on a continuous-facesheet plate DM:
  For the ALPAO force-driven plate PDE `(w0^2 I - c_m^2 L + beta^2 L^2) w = w0^2 u`,
  a harmonic field (`L u = 0`) on the slaved region S = D \\ A with free/Neumann
  boundary conditions on the outer rim of D and Dirichlet boundary values on the
  actively controlled mask A satisfies:
    1. Exact linearity `u_S = S u_A`, preserved identically through SVD (`CMmodesDM`)
       and live closed-loop MVM (`mvalC2dm`), with zero real-time latency cost.
    2. Discrete Maximum Principle (`min_d u <= u_S <= max_d u`), preventing high-order
       SVD modal amplification inside the central obstruction.
    3. Stress-free smooth equilibrium (`L w = 0 => L^2 w = 0 => u = w`) spanning the
       central obstruction instead of pinning unilluminated CO actuators to zero.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy import sparse
from scipy.ndimage import binary_dilation, binary_fill_holes, distance_transform_edt, label
from scipy.sparse.linalg import factorized


def _cobs_hole_region(mask: np.ndarray, cobs_scale: float) -> np.ndarray:
    """Identify central-obstruction cavities across the 4 PyWFS pupil quadrants.

    Uses binary_fill_holes + Euclidean distance transform per quadrant to locate
    each pupil's CO center (cy, cx) and inscribed radius r_co automatically,
    returning enclosed hole pixels within r <= cobs_scale * r_co (excluding outer
    background and radial spider-arm shadows beyond cobs_scale * r_co).
    """
    ny, nx = mask.shape
    holes = binary_fill_holes(mask) & (~mask)
    if not np.any(holes):
        return holes
    hy, hx = ny // 2, nx // 2
    yy, xx = np.mgrid[:ny, :nx]
    region = np.zeros_like(mask)
    for y0, y1, x0, x1 in ((0, hy, 0, hx), (0, hy, hx, nx), (hy, ny, 0, hx), (hy, ny, hx, nx)):
        qh = holes[y0:y1, x0:x1]
        if not np.any(qh):
            continue
        edt = distance_transform_edt(qh)
        iy, ix = np.unravel_index(int(np.argmax(edt)), edt.shape)
        r_co = float(edt[iy, ix])
        if r_co < 1.5:
            continue
        cy = y0 + iy
        cx = x0 + ix
        region |= (np.hypot(xx - cx, yy - cy) <= (r_co * cobs_scale)) & holes
    return region


def dilate_wfsmask(
    in_path: Path,
    out_path: Path,
    radius: float,
    mode: str = "cobs",
    cobs_scale: float = 1.37,
) -> None:
    raw = np.asarray(fits.getdata(in_path), dtype=np.float32)
    if raw.ndim != 2:
        raise ValueError(f"Expected 2D wfsmask in {in_path}, got shape {raw.shape}")
    mask = raw > 0.5
    n_orig = int(mask.sum())
    eff_mode = mode
    if radius > 0.0:
        ir = int(np.ceil(radius))
        gy, gx = np.mgrid[-ir : ir + 1, -ir : ir + 1]
        struct = (gx * gx + gy * gy) <= (radius * radius + 1e-9)
        dil = binary_dilation(mask, structure=struct)
        if mode == "inward":
            holes = binary_fill_holes(mask) & (~mask)
            if np.any(holes):
                dil = mask | (dil & holes)
            else:
                eff_mode = "full-fallback"
        elif mode == "cobs":
            co_reg = _cobs_hole_region(mask, cobs_scale)
            if np.any(co_reg):
                dil = mask | (dil & co_reg)
            else:
                eff_mode = "full-fallback"
    else:
        dil = mask
    n_new = int(dil.sum())
    fits.writeto(out_path, dil.astype(np.float32), overwrite=True)
    print(
        f"[calib_masks_slave] dilate-wfsmask r={radius:g} ({eff_mode}) pix: "
        f"{n_orig} -> {n_new} active pixels (+{n_new - n_orig})"
    )


def build_harmonic_slaving_operator(
    ctrl_mask: np.ndarray,
    act_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, sparse.csc_matrix, sparse.csc_matrix, np.ndarray]:
    """Build discrete 5-point Laplace operator blocks on slaved actuators S = D \\ A.

    Uses free/Neumann boundary conditions outside D (`act_mask`) and Dirichlet
    boundary values on A (`ctrl_mask`).
    """
    ny, nx = ctrl_mask.shape
    a_mask = ctrl_mask > 0.5
    d_mask = (act_mask > 0.5) | a_mask
    s_mask = d_mask & (~a_mask)

    # Keep only slaved components that are 4-connected to at least one active actuator.
    # (Disconnected islands, if any, have no Dirichlet anchor and remain zero.)
    lbl, ncomp = label(s_mask)
    if ncomp > 0:
        touch_a = binary_dilation(a_mask)  # default 4-connected cross
        keep = np.zeros_like(s_mask)
        for cid in range(1, ncomp + 1):
            comp = lbl == cid
            if np.any(comp & touch_a):
                keep |= comp
        s_mask = keep

    a_idx = np.flatnonzero(a_mask.ravel())
    s_idx = np.flatnonzero(s_mask.ravel())
    n_pix = ny * nx

    if s_idx.size == 0 or a_idx.size == 0:
        empty = sparse.csc_matrix((s_idx.size, s_idx.size), dtype=np.float64)
        empty_sa = sparse.csc_matrix((s_idx.size, a_idx.size), dtype=np.float64)
        return a_idx, s_idx, empty, empty_sa, d_mask

    # Map global flat index -> local row in S or col in A
    s_pos = np.full(n_pix, -1, dtype=np.int64)
    s_pos[s_idx] = np.arange(s_idx.size, dtype=np.int64)
    a_pos = np.full(n_pix, -1, dtype=np.int64)
    a_pos[a_idx] = np.arange(a_idx.size, dtype=np.int64)

    ss_r: list[int] = []
    ss_c: list[int] = []
    ss_v: list[float] = []
    sa_r: list[int] = []
    sa_c: list[int] = []
    sa_v: list[float] = []

    for loc_i, flat_i in enumerate(s_idx):
        ay = int(flat_i // nx)
        ax = int(flat_i % nx)
        diag = 0.0
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny2 = ay + dy
            nx2 = ax + dx
            if 0 <= ny2 < ny and 0 <= nx2 < nx and d_mask[ny2, nx2]:
                nb = ny2 * nx + nx2
                diag -= 1.0
                sp = s_pos[nb]
                if sp >= 0:
                    ss_r.append(loc_i)
                    ss_c.append(int(sp))
                    ss_v.append(1.0)
                else:
                    ap = a_pos[nb]
                    if ap >= 0:
                        sa_r.append(loc_i)
                        sa_c.append(int(ap))
                        sa_v.append(1.0)
            # Neighbors outside D obey free/Neumann BC (u_nb = u_i => zero flux).
        ss_r.append(loc_i)
        ss_c.append(loc_i)
        ss_v.append(diag)

    l_ss = sparse.csc_matrix((ss_v, (ss_r, ss_c)), shape=(s_idx.size, s_idx.size), dtype=np.float64)
    l_sa = sparse.csc_matrix((sa_v, (sa_r, sa_c)), shape=(s_idx.size, a_idx.size), dtype=np.float64)
    return a_idx, s_idx, l_ss, l_sa, d_mask


def harmonic_slave_dm(
    modes_path: Path,
    ctrl_mask_path: Path,
    act_mask_path: Path,
    out_path: Path,
) -> None:
    modes = np.asarray(fits.getdata(modes_path), dtype=np.float64)
    ctrl_mask = np.asarray(fits.getdata(ctrl_mask_path), dtype=np.float64)
    act_mask = np.asarray(fits.getdata(act_mask_path), dtype=np.float64)

    if modes.ndim != 3:
        raise ValueError(f"Expected 3D DM modes cube in {modes_path}, got shape {modes.shape}")
    nmodes, ny, nx = modes.shape
    if ctrl_mask.shape != (ny, nx) or act_mask.shape != (ny, nx):
        raise ValueError(
            f"Mask shapes ctrl={ctrl_mask.shape}, act={act_mask.shape} do not match DM ({ny}, {nx})"
        )

    a_idx, s_idx, l_ss, l_sa, d_mask = build_harmonic_slaving_operator(ctrl_mask, act_mask)

    flat_in = modes.reshape(nmodes, ny * nx)
    flat_out = np.zeros_like(flat_in)
    if a_idx.size > 0:
        u_a = flat_in[:, a_idx].T  # (n_act, nmodes)
        flat_out[:, a_idx] = u_a.T
        if s_idx.size > 0:
            solve_lss = factorized(l_ss)
            rhs = -(l_sa @ u_a)  # (n_slave, nmodes)
            u_s = solve_lss(rhs)
            flat_out[:, s_idx] = u_s.T

    out_cube = flat_out.reshape(nmodes, ny, nx).astype(np.float32)
    fits.writeto(out_path, out_cube, overwrite=True)
    print(
        f"[calib_masks_slave] harmonic-slave-dm: {nmodes} modes ({nx}x{ny}), "
        f"active={a_idx.size}, slaved={s_idx.size}, total_act={int(d_mask.sum())}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="PyWFS mask dilation and harmonic DM slaving helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_dil = sub.add_parser("dilate-wfsmask", help="Binary disk dilation of 2D WFS mask")
    p_dil.add_argument("--in", dest="in_path", required=True, type=Path)
    p_dil.add_argument("--out", dest="out_path", required=True, type=Path)
    p_dil.add_argument("--radius", required=True, type=float)
    p_dil.add_argument("--mode", choices=("cobs", "inward", "full"), default="cobs")
    p_dil.add_argument("--cobs-scale", type=float, default=1.37)

    p_slv = sub.add_parser("harmonic-slave-dm", help="Harmonic slaving of DM modes on act \\ ctrl")
    p_slv.add_argument("--modes", required=True, type=Path)
    p_slv.add_argument("--ctrl-mask", required=True, type=Path)
    p_slv.add_argument("--act-mask", required=True, type=Path)
    p_slv.add_argument("--out", required=True, type=Path)

    args = ap.parse_args()
    if args.cmd == "dilate-wfsmask":
        dilate_wfsmask(args.in_path, args.out_path, args.radius, mode=args.mode, cobs_scale=args.cobs_scale)
    elif args.cmd == "harmonic-slave-dm":
        harmonic_slave_dm(args.modes, args.ctrl_mask, args.act_mask, args.out)


if __name__ == "__main__":
    main()
