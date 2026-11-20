#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Parser and locator for declarative cacaosim .bench configuration files."""

from __future__ import annotations

from pathlib import Path


def find_bench_path(out_slug_dir: Path) -> Path | None:
    """Locate the primary .bench configuration file inside a staged report directory."""
    cand = out_slug_dir / "ao3k_scexao.bench"
    if cand.is_file():
        return cand
    others = [p for p in sorted(out_slug_dir.glob("*.bench")) if p.name != "csim_active.bench"]
    return others[0] if others else None


def parse_bench_file(bench_path: Path | None) -> list[dict[str, object]]:
    """Parse a cacaosim .bench INI file into structured component dictionaries."""
    if bench_path is None or not bench_path.is_file():
        return []
    sections: list[dict[str, object]] = []
    cur: dict[str, object] | None = None
    in_keys = {"in", "in_wf", "in_pup", "in_cmd", "in_wfe"}
    out_keys = {
        "out",
        "out_beam",
        "out_cam",
        "out_long",
        "out_opd",
        "out_refl",
        "out_trans",
        "out_lowfs",
        "out_pre_lyot",
        "out_pre_lyot_long",
    }
    for raw_line in bench_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            hdr = line[1:-1].strip()
            cat, _, comp_id = hdr.partition(".")
            cur = {
                "header": hdr,
                "category": cat.strip(),
                "id": comp_id.strip() or cat.strip(),
                "params": {},
                "in_streams": [],
                "out_streams": [],
            }
            sections.append(cur)
            continue
        if cur is not None and "=" in line:
            k, _, v = line.partition("=")
            key = k.strip()
            val = v.strip()
            if val.startswith('"') and val.endswith('"') and len(val) >= 2:
                val = val[1:-1]
            params = cur["params"]
            assert isinstance(params, dict)
            params[key] = val
            if key in in_keys and val:
                ins = cur["in_streams"]
                assert isinstance(ins, list)
                ins.append(val)
            elif key in out_keys and val:
                outs = cur["out_streams"]
                assert isinstance(outs, list)
                outs.append(val)
    return sections
