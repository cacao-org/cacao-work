#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Pure-stdlib 3D Block-EOF predictive matrix (PF) FITS extractor."""

from __future__ import annotations

import array
import base64
import math
from pathlib import Path
import sys

from .common import load_json_safe


def _read_fits_2d_f32(fits_path: Path) -> tuple[int, int, array.array] | None:
    """Read a 2D big-endian IEEE float FITS image without external dependencies."""
    if not fits_path.is_file():
        return None
    try:
        with fits_path.open("rb") as fh:
            cards: list[str] = []
            found_end = False
            while not found_end:
                blk = fh.read(2880)
                if len(blk) < 2880:
                    return None
                for off in range(0, 2880, 80):
                    card = blk[off : off + 80].decode("ascii", errors="ignore")
                    cards.append(card)
                    if card[:8].strip() == "END":
                        found_end = True
                        break

            meta: dict[str, str] = {}
            for card in cards:
                key = card[:8].strip()
                if len(card) >= 10 and card[8:10] == "= ":
                    val_part = card[10:].split("/", 1)[0].strip()
                    meta[key] = val_part

            bitpix = int(meta.get("BITPIX", "0"))
            naxis = int(meta.get("NAXIS", "0"))
            if naxis != 2 or bitpix not in (-32, -64):
                return None
            naxis1 = int(meta.get("NAXIS1", "0"))
            naxis2 = int(meta.get("NAXIS2", "0"))
            if naxis1 <= 0 or naxis2 <= 0:
                return None
            bscale = float(meta.get("BSCALE", "1.0"))
            bzero = float(meta.get("BZERO", "0.0"))

            tcode = "f" if bitpix == -32 else "d"
            elem_sz = 4 if bitpix == -32 else 8
            n_elems = naxis1 * naxis2
            raw = fh.read(n_elems * elem_sz)
            if len(raw) < n_elems * elem_sz:
                return None
    except (OSError, ValueError):
        return None

    arr = array.array(tcode)
    arr.frombytes(raw)
    if sys.byteorder == "little":
        arr.byteswap()
    if bitpix == -64:
        arr = array.array("f", (float(v) for v in arr))
    if bscale != 1.0 or bzero != 0.0:
        arr = array.array("f", (v * bscale + bzero for v in arr))
    return naxis2, naxis1, arr


def _select_block_indices(n_blocks: int) -> list[int]:
    """Select representative low/mid/high spatial block indices for interactive UI."""
    if n_blocks <= 4:
        return list(range(n_blocks))
    return sorted({0, 1, n_blocks // 2, n_blocks - 2})


def _quantize_block_signed_sqrt_int8(vals: list[float], vmax: float) -> str:
    """Encode float tensor values via signed-sqrt int8 quantization + base64."""
    scale = vmax if vmax > 1.0e-12 else 1.0
    inv_scale = 1.0 / scale
    buf = bytearray(len(vals))
    for i, val in enumerate(vals):
        mag = abs(val) * inv_scale
        if mag > 1.0:
            mag = 1.0
        q = int(round(math.sqrt(mag) * 127.0))
        if val < 0.0:
            q = -q
        if q > 127:
            q = 127
        elif q < -127:
            q = -127
        buf[i] = q & 0xFF
    return base64.b64encode(bytes(buf)).decode("ascii")


def extract_eof_pf_data(
    report_dir: Path,
    metrics_data: dict[str, object],
) -> dict[str, object] | None:
    """Extract compact 3D Block-EOF PF tensor payload from aol{1,2}_eofPFmat.fits."""
    pc_raw = metrics_data.get("predictive_control")
    pc: dict[str, object] = dict(pc_raw) if isinstance(pc_raw, dict) else {}
    if not pc:
        pc = load_json_safe(report_dir / "pf_stats.json")

    pf_mode = str(pc.get("pf_mode", "")).lower()
    has_eof_fits = any(
        (report_dir / f"aol{stg}_eofPFmat.fits").is_file() for stg in (1, 2)
    )
    if pf_mode != "eof" and not has_eof_fits:
        return None
    if not has_eof_fits:
        return None

    cfg_b = int(pc.get("pf_blocksize") or 128)
    cfg_p = int(pc.get("pf_order") or 8)
    stages_out: list[dict[str, object]] = []

    for stg_idx, stg_key, label, rate_hz in (
        (1, "stage1", "Stage 1 (AO3k, 1.0 kHz)", 1000.0),
        (2, "stage2", "Stage 2 (SCExAO, 2.0 kHz)", 2000.0),
    ):
        fits_p = report_dir / f"aol{stg_idx}_eofPFmat.fits"
        parsed = _read_fits_2d_f32(fits_p)
        if parsed is None:
            continue
        n_modes, stride, arr = parsed
        st_m_raw = pc.get(stg_key)
        st_m = st_m_raw if isinstance(st_m_raw, dict) else {}

        b_sz = max(1, int(st_m.get("blocksize") or cfg_b))
        if b_sz > n_modes:
            b_sz = n_modes
        p_ord = max(1, int(st_m.get("tap_order") or cfg_p))
        if stride < p_ord * b_sz:
            p_ord = max(1, stride // b_sz)
        if stride < p_ord * b_sz:
            continue

        n_blocks = (n_modes + b_sz - 1) // b_sz
        selected = set(_select_block_indices(n_blocks))

        lag_e = [0.0] * p_ord
        lag_off = [0.0] * p_ord
        tot_e = 0.0
        tot_off = 0.0
        block_summary: list[dict[str, object]] = []
        blocks_payload: list[dict[str, object]] = []

        for bk in range(n_blocks):
            s0 = bk * b_sz
            b_cur = min(b_sz, n_modes - s0)
            is_sel = bk in selected
            vals = [0.0] * (b_cur * p_ord * b_cur) if is_sel else []
            l2_sq = [0.0] * (b_cur * b_cur) if is_sel else []
            vmax = 0.0
            b_tot = 0.0
            b_diag = 0.0

            for out_i in range(b_cur):
                row_base = (s0 + out_i) * stride
                for lag_k in range(p_ord):
                    col_base = row_base + lag_k * b_sz
                    for in_j in range(b_cur):
                        v = float(arr[col_base + in_j])
                        v2 = v * v
                        b_tot += v2
                        lag_e[lag_k] += v2
                        if out_i == in_j:
                            b_diag += v2
                        else:
                            lag_off[lag_k] += v2
                        if is_sel:
                            vals[(out_i * p_ord + lag_k) * b_cur + in_j] = v
                            l2_sq[out_i * b_cur + in_j] += v2
                            av = abs(v)
                            if av > vmax:
                                vmax = av

            tot_e += b_tot
            tot_off += max(0.0, b_tot - b_diag)
            off_pct = round((b_tot - b_diag) / max(b_tot, 1.0e-30) * 100.0, 2)
            frob_rms = round(math.sqrt(b_tot / max(b_cur, 1)), 4)
            block_summary.append(
                {
                    "blk": bk,
                    "s0": s0,
                    "b": b_cur,
                    "offdiag_pct": off_pct,
                    "frob_rms": frob_rms,
                }
            )
            if is_sel:
                off_cands: list[tuple[float, int, int]] = []
                for out_i in range(b_cur):
                    row_l2 = out_i * b_cur
                    for in_j in range(b_cur):
                        if out_i == in_j:
                            continue
                        n2v = l2_sq[row_l2 + in_j]
                        if n2v > 0.0:
                            off_cands.append((n2v, s0 + out_i, s0 + in_j))
                off_cands.sort(reverse=True)
                top_pairs = [
                    [oi, ij, round(math.sqrt(n2v), 5)]
                    for n2v, oi, ij in off_cands[:8]
                ]
                blocks_payload.append(
                    {
                        "blk": bk,
                        "s0": s0,
                        "b": b_cur,
                        "vmax": round(vmax, 6),
                        "offdiag_pct": off_pct,
                        "top_pairs": top_pairs,
                        "data_b64": _quantize_block_signed_sqrt_int8(vals, vmax),
                    }
                )

        tot_e_safe = max(tot_e, 1.0e-30)
        lag_energy_pct = [round(e / tot_e_safe * 100.0, 2) for e in lag_e]
        lag_offdiag_pct = [
            round(lag_off[k] / max(lag_e[k], 1.0e-30) * 100.0, 2)
            for k in range(p_ord)
        ]
        stages_out.append(
            {
                "stage": stg_idx,
                "key": stg_key,
                "label": label,
                "rate_hz": rate_hz,
                "dt_ms": round(1000.0 / rate_hz, 4),
                "n_modes": n_modes,
                "blocksize": b_sz,
                "order": p_ord,
                "n_blocks": n_blocks,
                "pflatency_fr": round(float(st_m.get("pflatency_fr") or 0.0), 3),
                "var_red_pct": round(float(st_m.get("var_red_pct") or 0.0), 2),
                "offdiag_pct": round(tot_off / tot_e_safe * 100.0, 2),
                "lag_energy_pct": lag_energy_pct,
                "lag_offdiag_pct": lag_offdiag_pct,
                "block_summary": block_summary,
                "blocks": blocks_payload,
            }
        )

    if not stages_out:
        return None

    return {
        "pf_mode": "eof",
        "blocksize": int(stages_out[0]["blocksize"]),
        "order": int(stages_out[0]["order"]),
        "stages": stages_out,
    }
