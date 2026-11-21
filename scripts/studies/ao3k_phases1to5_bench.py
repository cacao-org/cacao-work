#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""End-to-end live GPU ao3k_scexao 2-stage integration benchmark (Phases 1-5).

Executes head-to-head A/B live GPU simulations on Subaru 7.95m AO3k (64x64 ALPAO plate DM,
1 kHz NIR PyWFS) + SCExAO (50x50 MEMS DM, 2 kHz Vis PyWFS) + H-band Lyot Coronagraph + 500 Hz
LLOWFS in isolated SHM sandboxes:
  Exp 1: Cold-start (0 s warmup) + live phase-continuous 60-deg wind switch (mH=6, 3 l/D).
  Exp 2: Unmodulated Stage-2 PyWFS (0 l/D) bright stress test (mH=6).
  Exp 3: Unmodulated Stage-2 PyWFS (0 l/D) faint stress test (mH=8).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_SCRIPT = REPO_ROOT / "benches" / "ao3k_scexao" / "sim-ao3k-scexao.milk"
CALIB_DIR = REPO_ROOT / "_work" / "ao3k_phases1to5_calib"
BENCH_ROOT = REPO_ROOT / "_work" / "ao3k_phases1to5_bench"


def _parse_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _parse_fps_info(txt: str) -> dict[str, float]:
    out: dict[str, float] = {}
    clean = re.sub(r"\x1b\[[0-9;]*m", "", txt)
    for line in clean.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] in (
            "FLOAT32", "FLOAT64", "UINT32", "UINT64", "INT32", "INT64"
        ):
            try:
                out["." + parts[1].lstrip(".")] = float(parts[3])
            except ValueError:
                pass
    return out


def _load_modal_cube(tlm_dir: Path, prefix: str) -> np.ndarray | None:
    files = sorted(tlm_dir.glob(f"{prefix}_*.fits"))
    if not files:
        return None
    chunks = []
    for f in files:
        arr = fits.getdata(f).astype(np.float32)
        chunks.append(arr.reshape(-1, arr.shape[-1]))
    return np.concatenate(chunks, axis=0)


def _run_modalwhite(
    wfs_cube: np.ndarray,
    dm_cube: np.ndarray | None,
    latency_fr: float,
    tag: str,
) -> dict[str, float]:
    """Run cacao-fpsexec-modalwhite (TP-0) on closed-loop modal cubes in an isolated SHM."""
    pid = os.getpid()
    shm_dir = Path(f"/dev/shm/cacao_mw_{tag}_{pid}")
    proc_dir = shm_dir / "proc"
    tmp_dir = Path(f"/tmp/cacao_mw_{tag}_{pid}")
    proc_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["MILK_SHM_DIR"] = str(shm_dir)
    env["MILK_PROC_DIR"] = str(proc_dir)
    env["OMP_NUM_THREADS"] = "4"
    env["OPENBLAS_NUM_THREADS"] = "4"

    try:
        n_fr = min(wfs_cube.shape[0], 4096)
        n_m = min(wfs_cube.shape[1], 256)
        wfs_sub = wfs_cube[-n_fr:, :n_m].astype(np.float32)
        fits.writeto(tmp_dir / "wfs.fits", wfs_sub, overwrite=True)

        dm_cmd = ""
        dm_name = "none"
        if dm_cube is not None and dm_cube.shape[0] >= n_fr:
            dm_sub = dm_cube[-n_fr:, :n_m].astype(np.float32)
            fits.writeto(tmp_dir / "dm.fits", dm_sub, overwrite=True)
            dm_cmd = 'milk-FITS2shm --no-procinfo -n ldm exec dm.fits @S:mw_dm >/dev/null'
            dm_name = "mw_dm"

        script = f"""
set -euo pipefail
cd "{tmp_dir}"
milk-FITS2shm --no-procinfo -n lwfs exec wfs.fits @S:mw_wfs >/dev/null
{dm_cmd}
milk-fps-init -q mw cacao-fpsexec-modalwhite >/dev/null
milk-fps-set -q \\
    mw.AOloopindex=0 \\
    mw.inWFSbuff=mw_wfs \\
    mw.inDMbuff={dm_name} \\
    mw.latency_fr={latency_fr:.2f} \\
    mw.NBwin={n_fr} \\
    mw.K_lags=16 \\
    mw.P_recov=8 \\
    mw.blocksize=32 \\
    mw.procinfo.triggermode=0 \\
    mw.procinfo.loopcntMax=1
milk-fps-runstart -q mw
milk-fps-wait -q -t 25 mw
milk-fps-info mw
milk-fps-rm -f -q mw
"""
        res = subprocess.run(
            ["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60
        )
        if res.returncode != 0:
            return {"error": 1.0}
        info = _parse_fps_info(res.stdout)
        return {
            "Q_vw_b0": round(info.get(".out.Q_vw_b0", 0.0), 2),
            "Q_xmode_b0": round(info.get(".out.Q_xmode_b0", 0.0), 2),
            "rho_d_b0": round(info.get(".out.rho_d_b0", 0.0), 4),
            "recov_var_pct": round(info.get(".out.recov_var_pct", 0.0), 2),
            "Q_wu_lo20": round(info.get(".out.Q_wu_lo20", 0.0), 2),
            "alert_flags": int(info.get(".out.alert_flags", 0.0)),
        }
    finally:
        shutil.rmtree(shm_dir, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _coro_contrast(out_dir: Path) -> dict[str, float]:
    """Compute H-band Lyot coronagraph raw 1-sigma & mean contrast at 3-5 and 5-10 l/D."""
    p_coro = out_dir / "psf_nir_coro.fits"
    p_unocc = out_dir / "psf_nir_final.fits"
    if not p_coro.is_file() or not p_unocc.is_file():
        return {}
    im_c = fits.getdata(p_coro).astype(np.float64)
    im_u = fits.getdata(p_unocc).astype(np.float64)
    # Account for Lyot coronagraph throughput (tput=0.92) & peak normalization
    peak_u = float(np.max(im_u))
    if peak_u <= 1e-12:
        return {}
    ny, nx = im_c.shape[-2], im_c.shape[-1]
    if im_c.ndim == 3:
        im_c = im_c[0]
    cy, cx = (ny - 1) / 2.0, (nx - 1) / 2.0
    yy, xx = np.mgrid[0:ny, 0:nx]
    # ao3k_scexao.bench [fpcam.nir_coro]: pixscale_ld = 2.50 pix / (lambda/D)
    rr_ld = np.hypot(xx - cx, yy - cy) / 2.50
    norm = im_c / (peak_u * 0.92)
    out: dict[str, float] = {}
    for label, r0, r1 in (("3_5ld", 3.0, 5.0), ("5_10ld", 5.0, 10.0)):
        m = (rr_ld >= r0) & (rr_ld < r1)
        vals = norm[m]
        out[f"mean_{label}"] = float(np.mean(vals))
        out[f"std_{label}"] = float(np.std(vals))
    return out


def _selfrm_og(out_dir: Path, stg: int, n_modes: int = 40) -> float | None:
    p_c = out_dir / f"selfRM_calib_stg{stg}.fits"
    p_s = out_dir / f"selfRM_onsky_stg{stg}.fits"
    if not p_c.is_file() or not p_s.is_file():
        return None
    c = fits.getdata(p_c).astype(np.float64)
    s = fits.getdata(p_s).astype(np.float64)
    # selfRM shape [zsize, n_in, n_out] -> peak positive slice diagonal
    dc = np.array([c[:, m, m] for m in range(min(n_modes, c.shape[1]))])
    ds = np.array([s[:, m, m] for m in range(min(n_modes, s.shape[1]))])
    idx = int(np.argmax(np.median(dc, axis=0)))
    vc = dc[:, idx]
    vs = ds[:, idx]
    valid = vc > 0.1 * np.median(vc)
    if not np.any(valid):
        return None
    return float(np.median(vs[valid] / vc[valid]))


def _timeseries_splits(out_dir: Path, switch_s: float) -> dict[str, Any]:
    """Compute pre-switch and post-switch WFE & Strehl splits from wf_timeseries.csv."""
    csv_p = out_dir / "wf_timeseries.csv"
    if not csv_p.is_file():
        return {}
    t_arr, s1_arr, fin_arr = [], [], []
    with csv_p.open(encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        for row in rdr:
            try:
                t_val = float(row.get("t_phys_s", row.get("t_s", 0.0)))
                s1 = float(row.get("rms_stg1_nm", row.get("stg1_rms_nm", 0.0)))
                fin = float(row.get("rms_final_nm", row.get("final_rms_nm", 0.0)))
                t_arr.append(t_val)
                s1_arr.append(s1)
                fin_arr.append(fin)
            except (ValueError, TypeError):
                continue
    if not t_arr:
        return {}
    t = np.array(t_arr)
    s1 = np.array(s1_arr)
    fin = np.array(fin_arr)

    def _stats(mask: np.ndarray) -> dict[str, float]:
        if not np.any(mask):
            return {}
        r1 = float(np.sqrt(np.mean(s1[mask] ** 2)))
        rf = float(np.sqrt(np.mean(fin[mask] ** 2)))
        return {
            "stg1_rms_nm": round(r1, 2),
            "final_rms_nm": round(rf, 2),
            "final_sr_vis": round(float(np.exp(-((2.0 * np.pi * rf / 750.0) ** 2))), 4),
            "final_sr_nir": round(float(np.exp(-((2.0 * np.pi * rf / 1650.0) ** 2))), 4),
        }

    res: dict[str, Any] = {"all": _stats(np.ones_like(t, dtype=bool))}
    if switch_s > 0.0:
        res["pre_switch"] = _stats(t < switch_s)
        res["post_0_1p5s"] = _stats((t >= switch_s) & (t < switch_s + 1.5))
        res["post_1p5_3s"] = _stats(t >= switch_s + 1.5)
    return res


def _run_sim(name: str, extra_args: list[str], switch_s: float = 0.0) -> dict[str, Any]:
    out_dir = BENCH_ROOT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    shm_dir = Path(f"/dev/shm/cacao_b_{name[:12]}_{pid}")
    proc_dir = shm_dir / "proc"
    work_dir = Path(f"/tmp/cacao_b_{name[:12]}_{pid}")
    proc_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["MILK_SHM_DIR"] = str(shm_dir)
    env["MILK_PROC_DIR"] = str(proc_dir)
    env["SANDBOX_WORK_DIR"] = str(work_dir)
    env["CACAOSIM_WORKDIR"] = str(work_dir / "csim")
    env["OMP_NUM_THREADS"] = "4"
    env["OPENBLAS_NUM_THREADS"] = "4"

    cmd = [str(SIM_SCRIPT), "--outdir", str(out_dir)] + extra_args
    print(f"\n[bench] === Running {name} ===", flush=True)
    t0 = time.monotonic()
    try:
        res = subprocess.run(
            cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600
        )
    finally:
        subprocess.run(
            [
                "bash",
                "-c",
                f'source "{REPO_ROOT}/scripts/shm-sandbox.sh"; sandbox_stop_all >/dev/null 2>&1',
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            timeout=20,
            check=False,
        )
        shutil.rmtree(shm_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
    dt = time.monotonic() - t0
    (out_dir / "run_stdout.log").write_text(res.stdout, encoding="utf-8")
    (out_dir / "run_stderr.log").write_text(res.stderr, encoding="utf-8")
    if res.returncode != 0:
        tail = "\n".join((res.stdout + "\n" + res.stderr).splitlines()[-40:])
        raise RuntimeError(f"Run {name} failed (rc={res.returncode}, {dt:.1f}s):\n{tail}")
    print(f"[bench] Finished {name} in {dt:.1f} s wall-clock.", flush=True)

    return _collect_metrics(name, out_dir, dt, switch_s)


def _collect_metrics(name: str, out_dir: Path, wall_s: float, switch_s: float) -> dict[str, Any]:
    rec: dict[str, Any] = {"name": name, "wall_s": round(wall_s, 1), "outdir": str(out_dir)}
    wf_p = out_dir / "wf_stats.json"
    if wf_p.is_file():
        wf = json.loads(wf_p.read_text(encoding="utf-8"))
        locs = wf.get("locations", {})
        rec["raw_rms_nm"] = round(locs.get("raw", {}).get("quad_total_rms_nm", 0.0), 2)
        rec["stg1_rms_nm"] = round(locs.get("stg1", {}).get("quad_total_rms_nm", 0.0), 2)
        rec["final_rms_nm"] = round(locs.get("final", {}).get("quad_total_rms_nm", 0.0), 2)
        rec["stg1_sr_vis"] = round(locs.get("stg1", {}).get("marechal_sr_vis_750nm", 0.0), 4)
        rec["final_sr_vis"] = round(locs.get("final", {}).get("marechal_sr_vis_750nm", 0.0), 4)
        rec["final_sr_nir"] = round(locs.get("final", {}).get("marechal_sr_nir_1650nm", 0.0), 4)

    rec["splits"] = _timeseries_splits(out_dir, switch_s)
    rec["coro"] = _coro_contrast(out_dir)

    pf_p = out_dir / "pf_stats.json"
    if pf_p.is_file():
        rec["pf"] = json.loads(pf_p.read_text(encoding="utf-8"))

    og1_p = out_dir / "online_og_stg1.json"
    if og1_p.is_file():
        rec["modalog_stg1"] = json.loads(og1_p.read_text(encoding="utf-8"))

    rec["selfrm_og_stg1"] = _selfrm_og(out_dir, 1, 40)
    rec["selfrm_og_stg2"] = _selfrm_og(out_dir, 2, 40)

    c2_live = _parse_kv(out_dir / "live_2wfs1dm" / "sysid_summary.txt")
    if c2_live:
        rec["live_2wfs1dm"] = c2_live
    c2_post = _parse_kv(out_dir / "calib_2wfs1dm" / "sysid_summary.txt")
    if c2_post:
        rec["post_2wfs1dm"] = c2_post

    wl_p = out_dir / "wl1_layers.fits"
    if wl_p.is_file():
        tbl = fits.getdata(wl_p).astype(np.float64)
        val = tbl[tbl[:, 15] >= 0.5]
        rec["wl1_layers"] = [
            {
                "vx": round(float(r[0]), 2),
                "vy": round(float(r[1]), 2),
                "speed": round(float(r[2]), 2),
                "frac_k": round(float(r[8]), 3),
                "z_m": round(float(r[10]), 0),
            }
            for r in val
        ]

    tlm_dir = out_dir / "telemetry"
    if tlm_dir.is_dir():
        w1 = _load_modal_cube(tlm_dir, "aol1_modevalWFS")
        d1 = _load_modal_cube(tlm_dir, "aol1_modevalDM")
        w2 = _load_modal_cube(tlm_dir, "aol2_modevalWFS")
        d2 = _load_modal_cube(tlm_dir, "aol2_modevalDM")
        if w1 is not None:
            rec["modalwhite_stg1"] = _run_modalwhite(w1, d1, 2.5, f"{name[:8]}_s1")
        if w2 is not None:
            rec["modalwhite_stg2"] = _run_modalwhite(w2, d2, 2.0, f"{name[:8]}_s2")

    return rec


def _format_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Live GPU Subaru AO3k + SCExAO Phases 1–5 Integration Benchmark",
        "",
        "| Run | Stg1 WFE [nm] | Final WFE [nm] | Vis SR | NIR SR | Coro 3–5 λ/D (1σ) | "
        "Stg1 `Q_vw` | Stg2 `Q_vw` | Stg1 OOS VR% | Stg2 `2WFS1DM` g2 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]
    for r in results:
        c35 = r.get("coro", {}).get("std_3_5ld")
        c_str = f"{c35:.2e}" if c35 is not None else "—"
        q1 = r.get("modalwhite_stg1", {}).get("Q_vw_b0", "—")
        q2 = r.get("modalwhite_stg2", {}).get("Q_vw_b0", "—")
        pf1 = r.get("pf", {}).get("stage1", {})
        vr1 = pf1.get("var_red_oos_pct", "—")
        vr1_s = f"{vr1:.1f}%" if isinstance(vr1, (int, float)) else str(vr1)
        c2 = r.get("post_2wfs1dm") or r.get("live_2wfs1dm") or {}
        g2_s = (
            f"{float(c2['mdb_diag_med']):.3f} (u={float(c2['usable_med'])*100:.1f}%, "
            f"ok={c2.get('usable_ok', '?')})"
            if "mdb_diag_med" in c2
            else "—"
        )
        lines.append(
            f"| `{r['name']}` | {r.get('stg1_rms_nm', 0):.2f} | {r.get('final_rms_nm', 0):.2f} | "
            f"{r.get('final_sr_vis', 0):.4f} | {r.get('final_sr_nir', 0):.4f} | {c_str} | "
            f"{q1} | {q2} | {vr1_s} | {g2_s} |"
        )
    lines.append("")
    for r in results:
        lines.append(f"## `{r['name']}` (`{r['wall_s']} s` wall)")
        if r.get("splits"):
            lines.append(f"- **Time splits:** `{json.dumps(r['splits'])}`")
        if r.get("coro"):
            lines.append(f"- **Coronagraph contrast:** `{json.dumps(r['coro'])}`")
        if r.get("modalog_stg1") or r.get("selfrm_og_stg1"):
            lines.append(
                f"- **Stage-1 OG:** modalog=`{r.get('modalog_stg1')}` | "
                f"selfRM=`{r.get('selfrm_og_stg1')}`"
            )
        if r.get("live_2wfs1dm") or r.get("post_2wfs1dm") or r.get("selfrm_og_stg2"):
            lines.append(
                f"- **Stage-2 OG:** live=`{r.get('live_2wfs1dm')}` | "
                f"post=`{r.get('post_2wfs1dm')}` | selfRM=`{r.get('selfrm_og_stg2')}`"
            )
        if r.get("pf"):
            s1, s2 = r["pf"].get("stage1", {}), r["pf"].get("stage2", {})
            lines.append(
                f"- **PF Stage 1:** state={s1.get('eof_active')} effN={s1.get('eff_samples')} "
                f"phys={s1.get('phys_active')} fx={s1.get('fx_active')} "
                f"regK={s1.get('regime_k')} wlSw={s1.get('wl_switches')} "
                f"oosVR={s1.get('var_red_oos_pct')}% overfit={s1.get('overfit_ratio')}"
            )
            lines.append(
                f"- **PF Stage 2:** state={s2.get('eof_active')} effN={s2.get('eff_samples')} "
                f"fx={s2.get('fx_active')} regK={s2.get('regime_k')} "
                f"oosVR={s2.get('var_red_oos_pct')}% overfit={s2.get('overfit_ratio')}"
            )
        if r.get("wl1_layers"):
            lines.append(f"- **`mlt-windlayers` Stage 1:** `{r['wl1_layers']}`")
        if r.get("modalwhite_stg1") or r.get("modalwhite_stg2"):
            lines.append(
                f"- **`modalwhite` (`TP-0`):** Stg1=`{r.get('modalwhite_stg1')}` | "
                f"Stg2=`{r.get('modalwhite_stg2')}`"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional subset of run names to execute",
    )
    args = ap.parse_args()

    BENCH_ROOT.mkdir(parents=True, exist_ok=True)
    ps_kern = CALIB_DIR / "dm01_preshaper_m32.fits"
    h1_mimo = CALIB_DIR / "H_mimo_stg1_p2.fits"
    h2_diag = CALIB_DIR / "H_diag_stg2.fits"
    cm1_b0 = CALIB_DIR / "cm1_b0.fits"
    for req in (ps_kern, h1_mimo, h2_diag, cm1_b0):
        if not req.is_file():
            raise FileNotFoundError(f"Missing calibration artifact {req}; run calib script first.")

    rm_mod = REPO_ROOT / "_work" / "ao3k_scexao_rm"
    rm_unmod6 = REPO_ROOT / "_work" / "ao3k_scexao_stg2unmod_rm"
    rm_unmod8 = REPO_ROOT / "_work" / "ao3k_scexao_stg2unmod_mh8_rm"

    p15_common = [
        "--dm1-preshaper", str(ps_kern),
        "--dynpsol1", str(h1_mimo),
        "--dynpsol2", str(h2_diag),
        "--online-og1", "--og1-ampl", "0.0018", "--og1-nbmode", "128",
        "--og1-stride", "4", "--og1-hold", "3",
        "--live-2wfs1dm-sec", "1.2",
        "--windlayers1",
        "--pf-dmmodes1", str(cm1_b0),
        "--pf-n-prior", "2048",
        "--pf-wl-switch-decay", "0.20",
        "--pf-zoh-ridge", "ON",
        "--pf-zoh-ridge2", "OFF",
        "--pf-gram-halflife", "16384",
        "--pf-regime-kmax", "4",
        "--pf-minsamples1", "8192",
        "--pf-minsamples2", "4096",
    ]

    common_flags = [
        "--save-rm", "",
        "--save-telemetry", "standard",
        "--calib-2wfs1dm",
        "--skip-microbench",
        "--no-tlm-analysis",
        "--selfrm-modes", "128",
    ]

    runs: list[tuple[str, list[str], float]] = [
        (
            "exp1_windsw_base",
            [
                "--load-rm", str(rm_mod),
                "--predictive", "--pf-mode", "eof", "--pf-order", "8", "--pf-blocksize", "64",
                "--pf-mix", "0.90", "--pf-reg", "0.005", "--pf-reg2", "0.015",
                "--pf-zoh-ridge", "OFF",
                "--pf-warmup-sec", "0", "--phys-time", "6.0",
                "--wind-switch-sec", "3.0", "--wind-switch-deg", "60.0",
            ] + common_flags,
            3.0,
        ),
        (
            "exp1_windsw_p15",
            [
                "--load-rm", str(rm_mod),
                "--predictive", "--pf-mode", "eof", "--pf-order", "8", "--pf-blocksize", "64",
                "--pf-mix", "0.90", "--pf-reg", "0.005", "--pf-reg2", "0.015",
                "--pf-warmup-sec", "0", "--phys-time", "6.0",
                "--wind-switch-sec", "3.0", "--wind-switch-deg", "60.0",
            ] + p15_common + common_flags,
            3.0,
        ),
        (
            "exp2_unmod_mh6_base",
            [
                "--load-rm", str(rm_unmod6),
                "--wfs2-mod-rad", "0",
                "--predictive", "--pf-mode", "eof", "--pf-order", "8", "--pf-blocksize", "64",
                "--pf-mix", "0.90", "--pf-reg", "0.005", "--pf-reg2", "0.015",
                "--pf-zoh-ridge", "OFF",
                "--pf-warmup-sec", "3.0", "--phys-time", "5.0",
            ] + common_flags,
            0.0,
        ),
        (
            "exp2_unmod_mh6_p15",
            [
                "--load-rm", str(rm_unmod6),
                "--wfs2-mod-rad", "0",
                "--predictive", "--pf-mode", "eof", "--pf-order", "8", "--pf-blocksize", "64",
                "--pf-mix", "0.90", "--pf-reg", "0.005", "--pf-reg2", "0.015",
                "--pf-warmup-sec", "3.0", "--phys-time", "5.0",
            ] + p15_common + common_flags,
            0.0,
        ),
        (
            "exp3_unmod_mh8_base",
            [
                "--load-rm", str(rm_unmod8),
                "--star-mag", "8.0", "--wfs2-mod-rad", "0",
                "--predictive", "--pf-mode", "eof", "--pf-order", "8", "--pf-blocksize", "64",
                "--pf-mix", "0.85", "--pf-reg", "0.010", "--pf-reg2", "0.025",
                "--pf-zoh-ridge", "OFF",
                "--pf-warmup-sec", "3.0", "--phys-time", "5.0",
            ] + common_flags,
            0.0,
        ),
        (
            "exp3_unmod_mh8_p15",
            [
                "--load-rm", str(rm_unmod8),
                "--star-mag", "8.0", "--wfs2-mod-rad", "0",
                "--predictive", "--pf-mode", "eof", "--pf-order", "8", "--pf-blocksize", "64",
                "--pf-mix", "0.85", "--pf-reg", "0.010", "--pf-reg2", "0.025",
                "--pf-warmup-sec", "3.0", "--phys-time", "5.0",
            ] + p15_common + ["--live-2wfs1dm-sec", "0.8"] + common_flags,
            0.0,
        ),
    ]

    if args.only:
        want = set(args.only)
        runs = [r for r in runs if r[0] in want]

    results: list[dict[str, Any]] = []
    sum_path = BENCH_ROOT / "SUMMARY.json"
    if sum_path.is_file() and args.only:
        prev = {r["name"]: r for r in json.loads(sum_path.read_text(encoding="utf-8"))}
    else:
        prev = {}

    for name, flags, sw_s in runs:
        rec = _run_sim(name, flags, sw_s)
        prev[name] = rec
        results = list(prev.values())
        sum_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        rep = _format_report(results)
        (BENCH_ROOT / "REPORT.md").write_text(rep, encoding="utf-8")
        print(rep.splitlines()[2])
        print(rep.splitlines()[-1] if len(rep.splitlines()) < 4 else "")

    print("\n" + (BENCH_ROOT / "REPORT.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
