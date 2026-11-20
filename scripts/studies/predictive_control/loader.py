#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""FITS telemetry, process statistics, Welch PSD, and AR filter loaders."""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from astropy.io import fits
import numpy as np

def load_fits_cube(tlm_dir: Path, prefix: str) -> np.ndarray | None:
    """Concatenate chronologically sorted streamFITSlog cubes into shape (N_frames, N_modes)."""
    files = sorted(glob.glob(str(tlm_dir / f"{prefix}_*.fits")))
    if not files:
        return None
    chunks = [np.asarray(fits.getdata(fp), dtype=np.float64) for fp in files]
    arr = np.concatenate(chunks, axis=0)
    return arr.reshape(arr.shape[0], -1)


def extract_process_stats(ct_path: Path) -> dict[str, dict[str, float]]:
    """Extract closed-loop CPU% and timing stats for predictive/mfilt daemons."""
    out: dict[str, dict[str, float]] = {}
    if not ct_path.is_file():
        return out
    ct = json.loads(ct_path.read_text(encoding="utf-8"))
    procs = ct.get("processes", [])
    for pname in (
        "mkARPF-1",
        "mkARPF-2",
        "applyARPF-1",
        "applyARPF-2",
        "mkEOFPF-1",
        "mkEOFPF-2",
        "applyEOFPF-1",
        "applyEOFPF-2",
        "mfilt-1",
        "mfilt-2",
    ):
        cands = [p for p in procs if p.get("name") == pname and p.get("timing_valid")]
        if not cands:
            cands = [p for p in procs if p.get("name") == pname]
        if not cands:
            continue
        best = max(cands, key=lambda d: float(d.get("cl_cpu_s", 0.0)))
        out[pname] = {
            "cl_cpu_pct": float(best.get("cl_cpu_pct", 0.0)),
            "exec_p50_us": float(best.get("exec_p50_us", 0.0)),
            "exec_p95_us": float(best.get("exec_p95_us", 0.0)),
            "exec_p99_us": float(best.get("exec_p99_us", 0.0)),
            "exec_max_us": float(best.get("exec_max_us", 0.0)),
            "rss_mb": float(best.get("vmrss_peak_kb", 0.0)) / 1024.0,
            "loopcnt": float(best.get("cl_loopcnt", best.get("loopcnt", 0))),
        }
    return out


def compute_welch_psd_sum(
    cube: np.ndarray,
    fs_hz: float,
    n_modes: int | None = None,
    nperseg: int = 512,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute quadrature-summed Welch one-sided PSD [nm^2/Hz] across modes."""
    x = cube[:, :n_modes] if n_modes is not None else cube
    # Modal telemetry is stored in um; convert to nm
    x_nm = (x - np.mean(x, axis=0, keepdims=True)) * 1e3
    n_t = x_nm.shape[0]
    seg = min(nperseg, n_t)
    step = max(1, seg // 2)
    win = np.hanning(seg)
    scale = 1.0 / (fs_hz * np.sum(win**2))
    freqs = np.fft.rfftfreq(seg, d=1.0 / fs_hz)
    psd_acc = np.zeros(freqs.shape[0], dtype=np.float64)
    n_seg = 0
    for start in range(0, n_t - seg + 1, step):
        seg_x = x_nm[start : start + seg] * win[:, None]
        fft_x = np.fft.rfft(seg_x, axis=0)
        p2 = np.sum(fft_x.real**2 + fft_x.imag**2, axis=1) * scale
        psd_acc += p2
        n_seg += 1
    psd_acc /= max(1, n_seg)
    if psd_acc.size > 2:
        psd_acc[1:-1] *= 2.0
    return freqs, psd_acc


def compute_filter_freq_response(
    w_mean: np.ndarray,
    fs_hz: float,
    freqs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate |H(f)| and unwrapped phase [deg] for FIR AR filter w_k at freqs."""
    k = np.arange(w_mean.shape[0], dtype=np.float64)
    ang = -2.0 * np.pi * np.outer(freqs / fs_hz, k)
    h_cplx = np.exp(1j * ang) @ w_mean
    mag = np.abs(h_cplx)
    phase_deg = np.degrees(np.unwrap(np.angle(h_cplx)))
    return mag, phase_deg


def load_run_bundle(work_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Load metrics, time series, pupil maps, filter weights, PSFs, and compute telemetry."""
    rdir = work_root / spec["slug"]
    metrics = json.loads((rdir / "ao3k_scexao_metrics.json").read_text(encoding="utf-8"))
    pf_path = rdir / "pf_stats.json"
    pf_stats = json.loads(pf_path.read_text(encoding="utf-8")) if pf_path.is_file() else None
    wf_ts = np.loadtxt(rdir / "wf_timeseries.csv", delimiter=",", skiprows=1)
    sr_ts = np.loadtxt(rdir / "strehl_timeseries.csv", delimiter=",", skiprows=1)

    t = wf_ts[:, 1]
    raw_t, s1_t, fin_t = wf_ts[:, 2], wf_ts[:, 3], wf_ts[:, 4]
    m_early = t < 1.0
    m_ss = (t >= 1.5) & (t <= 4.5)
    m_gust = t >= 4.5

    wf_mean_stg1 = np.asarray(fits.getdata(rdir / "wf_mean_stg1.fits"), dtype=np.float64)
    wf_mean_final = np.asarray(fits.getdata(rdir / "wf_mean_final.fits"), dtype=np.float64)
    pup_mask = np.asarray(fits.getdata(rdir / "wf_pupil_mask.fits"), dtype=np.float64) > 0.5
    psf_coro = np.asarray(fits.getdata(rdir / "psf_nir_coro.fits"), dtype=np.float64)
    psf_vis_final = np.asarray(fits.getdata(rdir / "psf_vis_final.fits"), dtype=np.float64)

    ny, nx = pup_mask.shape
    yy, xx = np.indices((ny, nx))
    cy, cx = ny / 2.0, nx / 2.0
    quads = {
        "top": pup_mask & (yy < cy) & (np.abs(xx - cx) < (cy - yy) * 1.1),
        "bot": pup_mask & (yy > cy) & (np.abs(xx - cx) < (yy - cy) * 1.1),
        "left": pup_mask & (xx < cx) & (np.abs(yy - cy) < (cx - xx) * 0.9),
        "right": pup_mask & (xx > cx) & (np.abs(yy - cy) < (xx - cx) * 0.9),
    }
    petal_means_stg1 = {k: float(np.mean(wf_mean_stg1[msk])) for k, msk in quads.items()}
    petal_ptv_stg1 = float(max(petal_means_stg1.values()) - min(petal_means_stg1.values()))

    filters: dict[int, dict[str, Any]] = {}
    modal_rms: dict[int, dict[str, np.ndarray]] = {}
    for stg in (1, 2):
        m_dict: dict[str, np.ndarray] = {}
        for sfx in ("mvalOLrms", "mvalWFSrms", "mvalPFresrms", "mvalDMrms"):
            fp = rdir / f"aol{stg}_{sfx}.fits"
            if fp.is_file():
                m_dict[sfx] = np.asarray(fits.getdata(fp), dtype=np.float64).ravel() * 1e3
        modal_rms[stg] = m_dict

        pf_fp = rdir / f"aol{stg}_arPFmat.fits"
        eof_fp = rdir / f"aol{stg}_eofPFmat.fits"
        if eof_fp.is_file():
            fmat = np.asarray(fits.getdata(eof_fp), dtype=np.float64)
            n_m, stride = fmat.shape
            b_sz = int(spec.get("blocksize", 128))
            p_ord = int(spec.get("order", 8))
            pb_len = p_ord * b_sz
            n2_all = np.sum(fmat**2, axis=1)
            nblk = (n_m + b_sz - 1) // b_sz
            off_by_blk: list[float] = []
            for bk in range(nblk):
                s0 = bk * b_sz
                b_cur = min(b_sz, n_m - s0)
                sub = fmat[s0 : s0 + b_cur, :pb_len].reshape(b_cur, p_ord, b_sz)[:, :, :b_cur]
                tot_e = float(np.sum(sub**2))
                diag_e = float(np.sum(np.diagonal(sub, axis1=0, axis2=2) ** 2))
                off_by_blk.append((tot_e - diag_e) / max(tot_e, 1e-30) * 100.0)
            b0 = min(b_sz, n_m)
            sub0 = fmat[:b0, :pb_len].reshape(b0, p_ord, b_sz)[:, :, :b0]
            c_mat0 = np.sqrt(np.sum(sub0**2, axis=1))
            w_lag0 = sub0[:, 0, :]
            filters[stg] = {
                "pf_mode": "eof",
                "order": p_ord,
                "blocksize": b_sz,
                "n_modes": n_m,
                "n2_all": n2_all,
                "med_norm2": float(np.median(n2_all)),
                "max_norm2": float(np.max(n2_all)),
                "offdiag_by_block": off_by_blk,
                "blk0_coupling": c_mat0,
                "blk0_lag0": w_lag0,
            }
        elif pf_fp.is_file():
            w = np.asarray(fits.getdata(pf_fp), dtype=np.float64)
            if w.shape[0] > w.shape[1]:
                w = w.T
            p_ord, n_m = w.shape
            k_arr = np.arange(p_ord, dtype=np.float64)
            dc_all = np.sum(w, axis=0)
            n2_all = np.sum(w**2, axis=0)
            lead_all = -(k_arr @ w)
            tap_energy = np.sum(w**2, axis=1)
            tap_energy_frac = tap_energy / max(float(np.sum(tap_energy)), 1e-30)
            w_lo = np.mean(w[:, :10], axis=1)
            w_mid = np.mean(w[:, 20:100], axis=1)
            w_hi = np.mean(w[:, 200:500], axis=1)
            filters[stg] = {
                "wmat": w,
                "order": p_ord,
                "n_modes": n_m,
                "w_lo": w_lo,
                "w_mid": w_mid,
                "w_hi": w_hi,
                "dc_all": dc_all,
                "n2_all": n2_all,
                "lead_all": lead_all,
                "lo_norm2": float(np.mean(n2_all[:10])),
                "lo_dc": float(np.mean(dc_all[:10])),
                "lo_lead_fr": float(-np.sum(k_arr * w_lo)),
                "mid_norm2": float(np.mean(n2_all[20:100])),
                "mid_lead_fr": float(-np.sum(k_arr * w_mid)),
                "med_dc": float(np.median(dc_all)),
                "med_norm2": float(np.median(n2_all)),
                "max_norm2": float(np.max(n2_all)),
                "tap_energy_frac": tap_energy_frac,
                "cum_tap_energy": np.cumsum(tap_energy_frac),
                "tail_gt8_sum_lo": float(np.sum(w_lo[8:])) if p_ord > 8 else 0.0,
            }

    # Compute temporal PSDs from saved telemetry cubes
    tlm_dir = rdir / "telemetry"
    psds: dict[int, dict[str, Any]] = {}
    for stg, fs_hz, nseg in ((1, 1000.0, 512), (2, 2000.0, 1024)):
        wfs_c = load_fits_cube(tlm_dir, f"aol{stg}_modevalWFS")
        ol_c = load_fits_cube(tlm_dir, f"aol{stg}_modevalOL")
        if wfs_c is not None and ol_c is not None:
            if "mvalWFSrms" not in modal_rms[stg]:
                modal_rms[stg]["mvalWFSrms"] = np.sqrt(np.mean(wfs_c**2, axis=0)) * 1e3
            if "mvalOLrms" not in modal_rms[stg]:
                modal_rms[stg]["mvalOLrms"] = np.sqrt(np.mean(ol_c**2, axis=0)) * 1e3
            f_wfs, p_wfs = compute_welch_psd_sum(wfs_c, fs_hz, nperseg=nseg)
            _, p_ol = compute_welch_psd_sum(ol_c, fs_hz, nperseg=nseg)
            _, p_wfs_lo = compute_welch_psd_sum(wfs_c, fs_hz, n_modes=20, nperseg=nseg)
            _, p_ol_lo = compute_welch_psd_sum(ol_c, fs_hz, n_modes=20, nperseg=nseg)
            psds[stg] = {
                "freqs": f_wfs,
                "psd_wfs": p_wfs,
                "psd_ol": p_ol,
                "rej": p_wfs / np.maximum(p_ol, 1e-30),
                "psd_wfs_lo": p_wfs_lo,
                "psd_ol_lo": p_ol_lo,
                "rej_lo": p_wfs_lo / np.maximum(p_ol_lo, 1e-30),
            }

    procs = extract_process_stats(rdir / "compute_telemetry.json")
    wm = metrics["wavefront_metrics"]["locations"]
    pm = metrics["psf_metrics"]
    cm = metrics["coronagraph_metrics"]
    ctbl = {int(round(r["sep_ld"])): r for r in cm["contrast_table"]}

    summary = {
        "key": spec["key"],
        "label": spec["label"],
        "short": spec["short"],
        "slug": spec["slug"],
        "pf_mode": spec.get("pf_mode", "ar" if spec["order"] > 0 else "integrator"),
        "blocksize": int(spec.get("blocksize", 1 if spec["order"] > 0 else 0)),
        "order": spec["order"],
        "n_min": spec["n_min"],
        "n_train": spec["n_train"],
        "is_ablation": spec["is_ablation"],
        "raw_wfe_nm": float(wm["raw"]["quad_total_rms_nm"]),
        "stg1_wfe_nm": float(wm["stg1"]["quad_total_rms_nm"]),
        "stg1_mean_nm": float(wm["stg1"]["mean_map_rms_nm"]),
        "stg1_std_nm": float(wm["stg1"]["std_map_rms_nm"]),
        "final_wfe_nm": float(wm["final"]["quad_total_rms_nm"]),
        "final_mean_nm": float(wm["final"]["mean_map_rms_nm"]),
        "final_std_nm": float(wm["final"]["std_map_rms_nm"]),
        "vis_stg1_sr_pct": float(pm["vis"]["stg1"]["strehl_peak"]) * 100.0,
        "vis_final_sr_pct": float(pm["vis"]["final"]["strehl_peak"]) * 100.0,
        "nir_stg1_sr_pct": float(pm["nir"]["stg1"]["strehl_peak"]) * 100.0,
        "nir_final_sr_pct": float(pm["nir"]["final"]["strehl_peak"]) * 100.0,
        "coro_leak_pct": float(cm["closed_loop"]["total_leakage_frac"]) * 100.0,
        "coro_c3_10": float(cm["closed_loop"]["mean_planet_contrast_3_10ld"]),
        "coro_c5_20": float(cm["closed_loop"]["mean_planet_contrast_5_20ld"]),
        "coro_c3": float(ctbl[3]["cl_planet_contrast"]),
        "coro_c5": float(ctbl[5]["cl_planet_contrast"]),
        "coro_c10": float(ctbl[10]["cl_planet_contrast"]),
        "coro_c15": float(ctbl[15]["cl_planet_contrast"]),
        "coro_c20": float(ctbl[20]["cl_planet_contrast"]),
        "coro_raw_c3": float(ctbl[3]["cl_raw_contrast"]),
        "coro_raw_c5": float(ctbl[5]["cl_raw_contrast"]),
        "coro_raw_c10": float(ctbl[10]["cl_raw_contrast"]),
        "coro_raw_c15": float(ctbl[15]["cl_raw_contrast"]),
        "coro_raw_c20": float(ctbl[20]["cl_raw_contrast"]),
        "coro_5s_5": float(ctbl[5]["cl_5sigma_planet_contrast"]),
        "coro_5s_15": float(ctbl[15]["cl_5sigma_planet_contrast"]),
        "coro_5s_20": float(ctbl[20]["cl_5sigma_planet_contrast"]),
        "llowfs_dm3_nm": float(cm["llowfs"]["dm3_stroke_rms_nm"]),
        "lowfs_cam_pct": float(
            cm["lowfs_light_budget"]["closed_loop"]["frac_coro_in_reaching_lowfs_cam_fov"]
        )
        * 100.0,
        "stg1_med_nm": float(np.median(s1_t)),
        "stg1_p95_nm": float(np.percentile(s1_t, 95)),
        "stg1_max_nm": float(np.max(s1_t)),
        "final_med_nm": float(np.median(fin_t)),
        "early_stg1_nm": float(np.mean(s1_t[m_early])),
        "early_final_nm": float(np.mean(fin_t[m_early])),
        "ss_stg1_nm": float(np.mean(s1_t[m_ss])),
        "ss_final_nm": float(np.mean(fin_t[m_ss])),
        "ss_final_p95_nm": float(np.percentile(fin_t[m_ss], 95)),
        "gust_stg1_nm": float(np.mean(s1_t[m_gust])),
        "gust_final_nm": float(np.mean(fin_t[m_gust])),
        "gust_final_max_nm": float(np.max(fin_t[m_gust])),
        "petal_means_stg1_nm": petal_means_stg1,
        "petal_ptv_stg1_nm": petal_ptv_stg1,
        "pf_stats": pf_stats,
        "procs": procs,
    }

    return {
        "spec": spec,
        "summary": summary,
        "metrics": metrics,
        "wf_ts": wf_ts,
        "sr_ts": sr_ts,
        "wf_mean_stg1": wf_mean_stg1,
        "wf_mean_final": wf_mean_final,
        "pup_mask": pup_mask,
        "psf_coro": psf_coro,
        "psf_vis_final": psf_vis_final,
        "filters": filters,
        "modal_rms": modal_rms,
        "psds": psds,
    }
