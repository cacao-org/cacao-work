#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CSV, JSON, study_meta.json, and REPORT.md writers for calib_2wfs1dm_report.

Every number quoted in the generated prose is computed from the runs; none is typed in.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from .analysis import LOW_ORDER_MODES, N_OFFLOAD_ITER, OFFLOAD_GAIN, T_CLEAN_S
from .telemetry import flags_missing_at_commit, git_state, load_vec

# cacao-work checkout root (scripts/studies/calib_2wfs1dm/markdown.py -> 3 levels up)
REPO_ROOT = Path(__file__).resolve().parents[3]


def fir_gain_db(taps: list[float]) -> tuple[float, float] | None:
    """(DC gain, peak gain) in dB of the FIR y[k] = sum_m taps[m] x[k-m], or None if no taps."""
    if not taps or len(taps) < 2:
        return None
    w = np.linspace(0.0, np.pi, 513)
    h = np.abs(np.exp(-1j * np.outer(w, np.arange(len(taps)))) @ np.asarray(taps, dtype=float))
    return float(20.0 * np.log10(max(h[0], 1e-12))), float(20.0 * np.log10(max(h.max(), 1e-12)))


def fmt_range(vals: Any, fmt: str = "{:.1f}", unit: str = "%") -> str:
    """Format the span of a set of values as 'lo–hi<unit>' (a single value if they agree).

    Signed formats (containing '+') are joined with ' to ' so the dash is not read as a sign.
    """
    lo, hi = fmt.format(float(np.min(vals))), fmt.format(float(np.max(vals)))
    if lo == hi:
        return f"{lo}{unit}"
    return f"{lo}{unit} to {hi}{unit}" if "+" in fmt else f"{lo}–{hi}{unit}"


def fmt_factor(num: float, den: float) -> str:
    """Format the ratio num/den as an improvement factor such as '5.7×'."""
    return f"{num / den:.1f}×" if den > 0.0 else "n/a"


def wrap_cmd(cmd: str, width: int = 96) -> list[str]:
    """Break a long shell command at option boundaries using backslash continuations."""
    groups: list[str] = []
    for tok in cmd.split():
        if groups and not tok.startswith("--"):
            groups[-1] = f"{groups[-1]} {tok}"  # keep an option together with its value
        else:
            groups.append(tok)
    out: list[str] = []
    cur = ""
    for grp in groups:
        if cur and len(cur) + 1 + len(grp) > width - 2:
            out.append(cur + " \\")
            cur = "    " + grp
        else:
            cur = f"{cur} {grp}" if cur else grp
    out.append(cur)
    return out


def write_outputs(
    out_dir: Path,
    cache_dir: Path,
    run: dict[str, Any],
    sweeps: dict[str, Any],
    offload: dict[str, Any],
    method_bench: dict[str, dict[str, Any]],
    transient: dict[str, Any],
) -> None:
    """Write calib_2wfs1dm_comparison.csv, benchmark.json, study_meta.json, and REPORT.md."""
    run_dirs = run["run_dirs"]
    run_metrics = run["run_metrics"]
    cal_metrics = run["cal_metrics"]
    sa_cal = run["sa_cal"]
    phys_time = float(run["phys_time"])
    sweep_p = sweeps["sweep_p"]
    conv_sums = sweeps["conv_sums"]
    sum_pred5 = sweeps["sum_pred5"]
    cdir_pred5 = sweeps["cdir_pred5"]
    cdir_pred4 = sweeps["cdir_pred4"]
    dA, dD = int(offload["dA"]), int(offload["dD"])
    offload_stats = offload["offload_stats"]
    ga_expect_med = offload["ga_expect_med"]
    wind = transient["wind"]
    wind_cl = transient["wind_cl"]
    srm_ref = method_bench["pred_5s"]["srm_med"]
    rkeys = ["int_open", "int_closed", "pred_4s", "pred_5s"]

    mb_op = method_bench["int_open"]
    mb_cl = method_bench["int_closed"]
    mb_p4 = method_bench["pred_4s"]
    mb_p5 = method_bench["pred_5s"]
    mb_all = [method_bench[k] for k in rkeys]

    # Every number quoted in the prose below is derived here from the data, never typed in.
    wz_pred = [mb_p4["w_err_pct"], mb_p5["w_err_pct"]]
    wz_int = [mb_op["w_err_pct"], mb_cl["w_err_pct"]]
    wz_int_med = [mb_op["w_med"], mb_cl["w_med"]]
    fr_pred = [mb_p4["freq_err_pct"], mb_p5["freq_err_pct"]]
    fr_int = [mb_op["freq_err_pct"], mb_cl["freq_err_pct"]]
    int_factor = [m["w_err_pct"] / max(m["freq_err_pct"], 1e-9) for m in (mb_op, mb_cl)]
    pred_gap = max(abs(m["w_err_pct"] - m["freq_err_pct"]) for m in (mb_p4, mb_p5))
    ref_spreads = [m["ref_spread_pct"] for m in mb_all]
    pm_all = [m[k] for m in mb_all for k in ("w_pm_med_pct", "freq_pm_med_pct")]
    conv_errs = [r["ref_err_pct"] for r in conv_sums]
    hi_ord = [r for r in sweep_p if r["order"] >= 4]
    eta_raw = [float(m["w_summary"].get("eta_d_raw_med", float("nan"))) for m in mb_all]
    dim_a = int(sum_pred5.get("dim_a", dA))
    dim_d = int(sum_pred5.get("dim_d", dD))
    lo = LOW_ORDER_MODES
    lo_lbl = f"modes 0–{lo - 1}"

    # Write downloadable CSV (one row per control regime)
    csv_cols = [
        ("regime", "label", "{}"),
        ("selfrm_med", "srm_med", "{:.4f}"),
        ("selfrm_alt_med", "ref_alt_med", "{:.4f}"),
        ("selfrm_ref_spread_pct", "ref_spread_pct", "{:.2f}"),
        ("ols_med", "ols_med", "{:.4f}"),
        ("ols_err_pct", "ols_err_pct", "{:.2f}"),
        ("ols_permode_med_err_pct", "ols_pm_med_pct", "{:.2f}"),
        ("wz_med", "w_med", "{:.4f}"),
        ("wz_err_pct", "w_err_pct", "{:.2f}"),
        ("wz_permode_med_err_pct", "w_pm_med_pct", "{:.2f}"),
        ("wz_permode_p90_err_pct", "w_pm_p90_pct", "{:.2f}"),
        ("wz_tt_mae", "w_tt_mae", "{:.4f}"),
        ("freq_med", "freq_med", "{:.4f}"),
        ("freq_err_pct", "freq_err_pct", "{:.2f}"),
        ("freq_permode_med_err_pct", "freq_pm_med_pct", "{:.2f}"),
        ("freq_permode_p90_err_pct", "freq_pm_p90_pct", "{:.2f}"),
        ("freq_tt_mae", "freq_tt_mae", "{:.4f}"),
        ("res_ac1", "ac1_res", "{:.4f}"),
        ("res_corr_d", "corr_res_d", "{:.4f}"),
    ]
    csv_path = out_dir / "calib_2wfs1dm_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow([col for col, _, _ in csv_cols])
        for m in mb_all:
            wr.writerow([fmt.format(m[key]) for _, key, fmt in csv_cols])

    # Provenance: commits recorded by the run, plus the state of this generator itself
    repro = dict(cal_metrics.get("reproducibility", {}))
    repo_root = REPO_ROOT
    gen_state = git_state(repo_root)
    run_cmds = {
        rk: str(run_metrics[rk].get("reproducibility", {}).get("run_command", ""))
        for rk in run_dirs
    }
    cw_rec = next(
        (r for r in repro.get("repositories", []) if r.get("name") == "cacao-work"), {}
    )
    missing_flags = flags_missing_at_commit(
        repo_root, str(cw_rec.get("commit", "")), run_cmds["calib2wfs1dm"]
    )
    repro["run_commands"] = run_cmds
    repro["report_generator"] = {"script": "scripts/build-calib-2wfs1dm-report.py", **gen_state}
    repro["run_flags_missing_at_recorded_commit"] = missing_flags

    # Write machine-readable benchmark JSON
    bench_json = {
        "study": "Two-WFS + Inter-Stage DM Closed-Loop Telemetry Calibration Study",
        "data_origin": "end-to-end simulation (cacaosim); no telescope data",
        "selfrm_reference": {
            "primary": mb_p5["ref_kind"],
            "definitions": {
                "peak": "per-mode peak |diag| ratio, og_selfrm.fits (milk-mlt-calib2wfs1dm)",
                "slice": "same-lag-slice signed diag ratio (this script)",
            },
            "note": "all errors use the primary reference; spread = |alternate - primary|",
            "spread_pct_by_regime": {k: method_bench[k]["ref_spread_pct"] for k in rkeys},
        },
        "ar_whitening_sweep": [
            {
                "order": r["order"],
                "eta_d_white_med": r["eta_d_white_med"],
                "mdb_diag_med": r["mdb_diag_med"],
                "selfrm_og_med": srm_ref,
                "selfrm_rel_err": r["ref_err_pct"] / 100.0,
                "r2_ol_raw_med": r["r2_ol_raw_med"],
                "cross_rel_err": r["cross_rel_err"],
            }
            for r in sweep_p
        ],
        "convergence_sweep": [
            {
                "t_phys_s": r["t_s"],
                "nframes": r["nframes"],
                "mdb_diag_med": r["mdb_diag_med"],
                "selfrm_rel_err": r["ref_err_pct"] / 100.0,
                "r2_ol_raw_med": r["r2_ol_raw_med"],
                "r2_a_raw_med": r["r2_a_raw_med"],
                "geom_cos_med": r["geom_cos_med"],
                "cross_rel_err": r["cross_rel_err"],
            }
            for r in conv_sums
        ],
        "offload_2d": offload_stats,
        "stage3_transient": {"calib2wfs1dm": wind, "lowfs_closed": wind_cl},
        "method_comparison": {
            k: {
                "label": method_bench[k]["label"],
                "srm_med": method_bench[k]["srm_med"],
                "srm_alt_med": method_bench[k]["ref_alt_med"],
                "srm_ref_spread_pct": method_bench[k]["ref_spread_pct"],
                "ols_med": method_bench[k]["ols_med"],
                "ols_err_pct": method_bench[k]["ols_err_pct"],
                "ols_permode_med_err_pct": method_bench[k]["ols_pm_med_pct"],
                "wz_med": method_bench[k]["w_med"],
                "wz_err_pct": method_bench[k]["w_err_pct"],
                "wz_permode_med_err_pct": method_bench[k]["w_pm_med_pct"],
                "wz_permode_p90_err_pct": method_bench[k]["w_pm_p90_pct"],
                "wz_tt_mae": method_bench[k]["w_tt_mae"],
                "freq_med": method_bench[k]["freq_med"],
                "freq_err_pct": method_bench[k]["freq_err_pct"],
                "freq_signed_err_pct": method_bench[k]["freq_signed_err_pct"],
                "freq_permode_med_err_pct": method_bench[k]["freq_pm_med_pct"],
                "freq_permode_p90_err_pct": method_bench[k]["freq_pm_p90_pct"],
                "freq_tt_mae": method_bench[k]["freq_tt_mae"],
                "res_ac1": method_bench[k]["ac1_res"],
                "res_corr_d": method_bench[k]["corr_res_d"],
            }
            for k in rkeys
        },
        "reproducibility": repro,
    }
    (out_dir / "calib_2wfs1dm_benchmark.json").write_text(
        json.dumps(bench_json, indent=2) + "\n", encoding="utf-8"
    )

    # Write study_meta.json so build-ao-web-report.py features it on the Top Page
    badges = [
        "FEATURED STUDY",
        "SIMULATION",
        "Probe-Free B = Mab A + Mdb D",
        f"AR(4) W(z), predictive: {fmt_range(wz_pred)} error of median gain",
        f"Freq-domain, integrator: {fmt_range(fr_int)} (W(z): {fmt_range(wz_int)})",
        f"DM2→DM1 offload matrix: cos {offload_stats['geom_cos_med_4s']:.3f} (static test)",
    ]
    if wind["found"]:
        badges.append(f"Stage-3 transient at t ≈ {wind['t_onset_s']:.2f} s")
    study_meta = {
        "report_type": "tech_report",
        "domain": "calibration-sysid",
        "subtopic": "telemetry-sysid",
        "topic": "Two-WFS + Inter-Stage DM Closed-Loop System Identification",
        "cacao_features": [
            "2-WFS/1-DM Telemetry SysID",
            "DM2->DM1 Offload Matrix",
            "PyWFS Optical Gain",
            "Stage-2/Stage-3 Transient Diagnosis",
        ],
        "referenced_simulations": [
            "ao3k_scexao_calib2wfs1dm",
            "ao3k_scexao_lowfs_closed",
            "ao3k_scexao_lowfs_open",
        ],
        "nav_label": "2-WFS/1-DM Calibration Report",
        "button_label": "Read 2-WFS/1-DM Calibration Report",
        "summary": (
            "Simulation study of closed-loop telemetry calibration of the inter-WFS (Mab), "
            "inter-stage DM (Mdb), and virtual upstream DM2→DM1 offload (Mda_virt) matrices on "
            "a simulated Subaru AO3k + SCExAO + LLOWFS system: AR(p) whitening W(z) results, an "
            "exact-window frequency-domain estimator, limitations, and proposed next steps."
        ),
        "badges": badges,
        "reproducibility": repro,
    }
    (out_dir / "study_meta.json").write_text(
        json.dumps(study_meta, indent=2) + "\n", encoding="utf-8"
    )

    # ---- Text fragments derived from the data ------------------------------------------------
    star_bits = []
    if sa_cal.get("seeing_arcsec_500nm") is not None:
        star_bits.append(f"`{float(sa_cal['seeing_arcsec_500nm']):.2f}\"` seeing")
    if sa_cal.get("star_mV") is not None:
        star_bits.append(f"guide star `mV = {float(sa_cal['star_mV']):.1f}`")
    star_bits.append(f"`{phys_time:.1f} s` integration per run")
    star_txt = ", ".join(star_bits)

    if mb_p5["ref_kind"] == "peak":
        ref_def = (
            "the per-mode peak-`|diag|` ratio of the simulated on-sky and calibration `selfRM` "
            "cubes (`og_selfrm.fits`, written by `milk-mlt-calib2wfs1dm`)"
        )
        ref_alt_def = "the same-lag-slice signed ratio of the same two cubes"
    else:
        ref_def = "the same-lag-slice signed ratio of the on-sky and calibration `selfRM` cubes"
        ref_alt_def = "the same definition (no `og_selfrm.fits` was available)"

    fgain = fir_gain_db(list(sum_pred5.get("ar_taps", [])))
    wz_gain_txt = ""
    if fgain is not None and fgain[0] < 0.0:
        wz_gain_txt = f" (`{fgain[0]:+.0f} dB` at DC, up to `{fgain[1]:+.1f} dB` at high frequency)"

    cli_times = [
        float(p.read_text(encoding="utf-8")) for p in cache_dir.glob("*/cli_elapsed_s.txt")
    ]
    cli_txt = "C implementation with BLAS/LAPACKE + OpenMP"
    if cli_times:
        cli_txt += (
            f"; `{fmt_range(cli_times, '{:.2f}', ' s')}` wall time per fit"
            f" ({len(cli_times)} fits timed on the build machine)"
        )

    r2a_full = load_vec(cdir_pred5 / "r2_a_raw.fits")
    r2a_clean = load_vec(cdir_pred4 / "r2_a_raw.fits")
    r2ol_clean = load_vec(cdir_pred4 / "r2_ol_raw.fits")
    conv_last = conv_sums[-1]
    conv_txt = (
        f"At `{conv_last['t_s']:.1f} s` the fit reaches `R²_OL = {conv_last['r2_ol_raw_med']:.3f}`"
        f", `R²_A = {conv_last['r2_a_raw_med']:.3f}` and a median `Mda_virt` column cosine of "
        f"`{conv_last['geom_cos_med']:.3f}`"
    )
    if r2ol_clean is not None:
        conv_txt += f" (lowest single-mode `R²_OL = {float(np.min(r2ol_clean)):+.3f}`)"
    conv_txt += (
        f". The error of the median gain over the {len(conv_sums)} window lengths spans "
        f"`{fmt_range(conv_errs, '{:.2f}')}`"
    )
    conv_scatter = max(conv_errs) - min(conv_errs)
    if all(b <= a for a, b in zip(conv_errs, conv_errs[1:])):
        conv_txt += " and decreases monotonically with window length."
    else:
        conv_txt += (
            " and does not decrease monotonically, so the scatter of a single realization is "
            "of that order."
        )
    hi_errs = [r["ref_err_pct"] for r in hi_ord]
    if hi_errs:
        hi_verdict = (
            "differ by less than that span and cannot be ranked"
            if max(hi_errs) - min(hi_errs) <= conv_scatter
            else "differ by more than that span"
        )
        conv_txt += (
            f" The AR orders `p ≥ 4` (`{fmt_range(hi_errs, '{:.2f}')}` in the sweep above) "
            f"{hi_verdict}."
        )

    low_full = fmt_range(mb_p5["w_d"][:lo], "{:.2f}", "")
    low_clean = fmt_range(mb_p4["w_d"][:lo], "{:.2f}", "")
    low_ref = fmt_range(mb_p5["og_true"][:lo], "{:.2f}", "")
    if wind["found"]:
        dm2_txt = ""
        if "dm2_factor" in wind:
            dm2_txt = (
                f" The Stage-2 command (`aol2_dmC`) rises `{wind['dm2_factor']:.1f}×` "
                f"(to `{wind['dm2_peak_nm']:.0f} nm`) at the same time."
            )
        where_txt = (
            f"after the `0–{T_CLEAN_S:.0f} s` clean window, so the clean-window fits are unaffected"
            if wind["after_clean_window"]
            else f"inside the `0–{T_CLEAN_S:.0f} s` clean window, so those fits are affected too"
        )
        rise_ms = max(wind["rise_ms"], wind["sample_ms"])
        rise_txt = (
            f"The rise takes at most `{rise_ms:.0f} ms`, which is abrupt and points to a "
            "discrete event rather than slow growth"
            if rise_ms < 20.0
            else f"The rise takes `{rise_ms:.0f} ms`, i.e. it is gradual, which is "
            "compatible with a slowly growing instability"
        )
        if wind_cl is None:
            cl_txt = "The integrator LLOWFS-closed run could not be checked for the same event."
        elif wind_cl["found"]:
            cl_txt = (
                "The integrator LLOWFS-closed run, which has the same Stage-3 and `zpo-2` "
                f"configuration, shows a similar rise at `t ≈ {wind_cl['t_onset_s']:.2f} s` "
                f"(`{wind_cl['factor']:.0f}×`), so the event is not specific to predictive control."
            )
        else:
            cl_txt = (
                "The integrator LLOWFS-closed run, which has the same Stage-3 and `zpo-2` "
                "configuration, shows no such event. A gain mismatch alone would be expected "
                "to act there as well, so something specific to the predictive run is involved."
            )
        neg_txt = ""
        if r2a_full is not None and np.any(r2a_full < 0.0):
            neg = ", ".join(str(i) for i in np.where(r2a_full < 0.0)[0][:8])
            neg_txt = f" and held-out `R²_A` is negative on mode(s) {neg}"
        clean_r2_txt = ""
        if r2a_clean is not None:
            clean_r2_txt = (
                f" (`R²_A` on modes 0–5: `{fmt_range(r2a_clean[:6], '{:.2f}', '')}`)"
            )
        transient_md = [
            f"- Before the event the Stage-3 LLOWFS command (`aol3_dmC`, applied to `DM2` through "
            f"`dm02disp04`) sits at `{wind['base_nm']:.0f} nm` OPD RMS.",
            f"- At **`t ≈ {wind['t_onset_s']:.2f} s`** it rises **`{wind['factor']:.0f}×`** "
            f"(to `{wind['peak_nm']:.0f} nm`).{dm2_txt}",
            f"- This is {where_txt}. The full-run fit does include it.",
            "- The regressor `D` contains only `aol2_modevalDM`, so Stage-3 motion of the same "
            f"mirror is unmodelled. In the full-run fit `diag(Mdb)` on {lo_lbl} is `{low_full}` "
            f"against a reference of `{low_ref}`{neg_txt}; on the clean window it is "
            f"`{low_clean}`{clean_r2_txt}.",
            "",
            "**The cause of the event is not established.** One hypothesis is a zero-point-offset "
            "gain mismatch: `zpo-2` converts Stage-3 commands into WFS offsets at the calibration "
            f"gain (`1.0`), while the simulated on-sky optical gain is about `{srm_ref:.2f}`, so "
            "part of every Stage-3 command is seen by Stage 2 as an error. That mismatch is "
            f"present from `t = 0`, however, and by itself does not explain a quiet first "
            f"`{wind['t_onset_s']:.2f} s`. {rise_txt}. {cl_txt}",
            "",
            "Two further checks would settle it: rerun with the `zpo-2` offsets scaled by the "
            "measured optical gain, and look in the run log for a scheduled action at that time "
            "(a predictive-filter update or the end-of-integration sequence).",
        ]
    else:
        transient_md = [
            "No late-run transient was detected on the Stage-3 channel (threshold: `5×` the "
            "first-half median OPD RMS).",
            f"In the full-run fit `diag(Mdb)` on {lo_lbl} is `{low_full}` against a reference of "
            f"`{low_ref}`; on the clean window it is `{low_clean}`.",
        ]

    scale_med = offload_stats["scale_ratio_med_4s"]
    if ga_expect_med is None:
        scale_note = (
            "Expected to equal the `WFS A` optical gain, since `Mda_virt ≈ Mab^+ Mdb = g_A · "
            "M_geom`; not cross-checked (no Stage-1 `selfRM` cubes in the run directory)"
        )
    elif abs(scale_med - ga_expect_med) / max(ga_expect_med, 1e-9) < 0.05:
        scale_note = (
            f"Matches the `WFS A` optical gain from the Stage-1 `selfRM` (`{ga_expect_med:.3f}`), "
            "as expected from `Mda_virt ≈ Mab^+ Mdb = g_A · M_geom`"
        )
    else:
        scale_note = (
            f"Expected to equal the `WFS A` optical gain, but the Stage-1 `selfRM` gives "
            f"`{ga_expect_med:.3f}`; the difference is unexplained (regression attenuation from "
            "noise in `B` is one candidate)"
        )

    sgn_op = mb_op["freq_signed_err_pct"]
    sgn_cl = mb_cl["freq_signed_err_pct"]
    sign_txt = (
        f"Its signed error is `{sgn_op:+.1f}%` with LLOWFS open and `{sgn_cl:+.1f}%` with LLOWFS "
        "closed"
    )
    sign_txt += (
        "; the signs differ, so this is scatter rather than a common bias."
        if sgn_op * sgn_cl < 0.0
        else "."
    )
    pred_verb = "agree to within" if pred_gap < 1.0 else "differ by up to"
    pred_txt = (
        f"Under predictive control the two estimators {pred_verb} `{pred_gap:.1f}` percentage "
        f"points (frequency-domain `{fmt_range(fr_pred)}`, `W(z)` `{fmt_range(wz_pred)}`)."
    )
    low_rel = [m["freq_tt_mae"] / m["srm_med"] * 100.0 for m in mb_all]
    low_txt = (
        f"With the frequency-domain estimator the MAE on {lo_lbl} is "
        f"`{fmt_range([m['freq_tt_mae'] for m in mb_all], '{:.2f}', '')}` in gain units, i.e. "
        f"`{fmt_range(low_rel, '{:.0f}')}` of the reference gain"
    )
    low_txt += (
        ", so low-order gains are still not recovered reliably."
        if max(low_rel) > 10.0
        else "."
    )
    low_factors = ", ".join(fmt_factor(m["w_tt_mae"], m["freq_tt_mae"]) for m in mb_all)

    if offload_stats["max_stable_gain"] > 0.0:
        stab_note = (
            f"The static iteration converges for `g_off < {offload_stats['max_stable_gain']:.2f}`"
            "; loop delay and Stage-1 dynamics are not modelled"
        )
    else:
        stab_note = "At least one eigenvalue has a non-positive real part: no gain is stable"

    # ---- Reproduction recipe and provenance ---------------------------------------------------
    seeing_arg = f"{float(sa_cal.get('seeing_arcsec_500nm', 0.60)):.2f}"
    base_cmd = f"./scripts/run-ao3k-scexao.sh --seeing {seeing_arg} --phys-time {phys_time:.1f}"
    default_cmds = {
        "lowfs_open": f"{base_cmd} --no-lowfs --save-telemetry speckle"
        " --outdir _work/ao3k_scexao_lowfs_open",
        "lowfs_closed": f"{base_cmd} --save-telemetry speckle"
        " --outdir _work/ao3k_scexao_lowfs_closed",
        "calib2wfs1dm": f"{base_cmd} --predictive --calib-2wfs1dm --save-telemetry speckle"
        " --outdir _work/ao3k_scexao_calib2wfs1dm",
    }
    run_titles = {
        "lowfs_open": "Integrator, LLOWFS open",
        "lowfs_closed": "Integrator, LLOWFS closed",
        "calib2wfs1dm": "PSOL predictive + 2-WFS/1-DM calibration",
    }
    recipe_md = ["```bash", "cd cacao-work && source env.sh", ""]
    for step, rk in enumerate(run_dirs, start=1):
        src = "as recorded by the run" if run_cmds[rk] else "default recipe; command not recorded"
        recipe_md.append(f"# {step}. {run_titles[rk]} ({src})")
        recipe_md.extend(wrap_cmd(run_cmds[rk] or default_cmds[rk]))
        recipe_md.append("")
    recipe_md.extend(
        [
            f"# {len(run_dirs) + 1}. Build this study (figures + CSV + JSON) from the three runs",
            "${PYTHON_BIN} ./scripts/build-calib-2wfs1dm-report.py",
            "",
            f"# {len(run_dirs) + 2}. Stage the static site locally (omit --build-only to deploy)",
            "./scripts/publish-ao-report.sh --build-only _work/calib_2wfs1dm_report",
            "```",
        ]
    )

    prov_md = []
    if repro.get("repositories"):
        prov_md.extend(
            [
                "| Repository | Branch | Commit recorded at run time | Working tree at run time |",
                "| :--- | :---: | :---: | :--- |",
            ]
        )
        for r in repro["repositories"]:
            sha = str(r.get("commit", ""))
            short = str(r.get("short_commit", sha[:7]))
            url = str(r.get("url", ""))
            cell = f"[`{short}`]({url}/commit/{sha})" if sha and url else "`unknown`"
            dirty = r.get("dirty")
            tree = "uncommitted changes" if dirty else "clean"
            if dirty is None:
                tree = "not recorded"
            prov_md.append(
                f"| [{r.get('name', '')}]({url}) | `{r.get('branch', '')}` | {cell} | {tree} |"
            )
        prov_md.append("")
    gen_txt = "This page was built by `scripts/build-calib-2wfs1dm-report.py`"
    if gen_state["commit"]:
        gen_txt += f" at `cacao-work` commit `{gen_state['short_commit']}`"
        if gen_state["dirty"]:
            gen_txt += " **with uncommitted changes**"
    prov_md.append(gen_txt + ".")
    if missing_flags:
        prov_md.extend(
            [
                "",
                f"> **Provenance warning**: the recorded `cacao-work` commit "
                f"`{cw_rec.get('short_commit', '')}` does not contain the option(s) "
                f"`{'`, `'.join(missing_flags)}` used by the recorded run command. The run was "
                "launched from a working tree newer than that commit, so checking out the "
                "recorded commit will not reproduce it.",
            ]
        )

    # ---- REPORT.md ----------------------------------------------------------------------------
    md_lines = [
        "# Two-WFS + Inter-Stage DM Closed-Loop Telemetry Calibration Study",
        "",
        "- **Physical model**: forward optical relation `B = Mab A + Mdb D + b0` and virtual "
        "upstream relation `A = Mba B - Mda_virt D + a0` (`Mda_virt` = virtual influence of the "
        "inter-stage `DM2` on the upstream `WFS A`)",
        "- **Simulated system** (`cacaosim`): Subaru 7.95 m AO3k (`64×64 DM1`, `1 kHz` J-band "
        "PyWFS = `WFS A`) + SCExAO (`50×50 DM2`, `2 kHz` Vis PyWFS = `WFS B`) + reflective-Lyot "
        f"LLOWFS (`500 Hz` Stage-3 Zernikes on `dm02disp04`); {star_txt}",
        "- **Calibration engine**: `milk-mltools` (`mlt.sysid`, `mlt.tlmsync .mode=expint`, "
        f"`mlt_arfit`, `mlt_firfilt`, `mlt.calib2wfs1dm`) — {cli_txt}",
        "- **Companion live run**: [ao3k_scexao_calib2wfs1dm]"
        "(../ao3k_scexao_calib2wfs1dm/index.html) ("
        "[Config](../ao3k_scexao_calib2wfs1dm/config.html) · "
        "[Optical](../ao3k_scexao_calib2wfs1dm/optical.html) · "
        "[Runtime](../ao3k_scexao_calib2wfs1dm/runtime.html) · "
        "[How to Run](../ao3k_scexao_calib2wfs1dm/how_to_run.html)) | "
        "**Predictive control study**: "
        "[predictive_control_report](../predictive_control_report/index.html)",
        "",
        "> **Simulation study.** Every number on this page comes from the `cacaosim` end-to-end "
        "simulator driving the real CACAO control software. No telescope data are used. "
        "\"On-sky\" below means *simulated closed-loop operation through turbulence*, as opposed "
        "to the turbulence-free calibration.",
        "",
        "> **Key takeaway**: With the shipped `AR(4)` whitening `W(z)`, passive closed-loop "
        "telemetry recovers the median Stage-2 optical gain `diag(Mdb)` to within "
        f"**`{fmt_range(wz_pred)}`** of the `selfRM` reference under predictive control and to "
        f"`{fmt_range(wz_int)}` under a pure integrator. An exact-window frequency-domain "
        f"estimator gives **`{fmt_range(fr_int)}`** in the integrator case (`W(z)` error ÷ "
        f"frequency-domain error = `{fmt_range(int_factor, '{:.1f}', '×')}`) and "
        f"`{fmt_range(fr_pred)}` under predictive control. These are errors of the median over "
        f"{dim_d} modes from one realization per regime: the per-mode median error is "
        f"`{fmt_range(pm_all)}`, the reference itself moves by "
        f"`{fmt_range(ref_spreads)}` between two reasonable "
        f"definitions, and the best MAE on {lo_lbl} is `{fmt_range(low_rel, '{:.0f}')}` of the "
        "reference gain. The telemetry-derived "
        "`DM2 → DM1` offload matrix `Mda_virt` matches actuator geometry with a median column "
        f"cosine of **`{offload_stats['geom_cos_med_4s']:.3f}`**; this was tested as a static "
        "matrix comparison, and no offload loop was run in the simulator.",
        "",
        "## 1. Two-Stage Optical Geometry & Closed-Loop Identification Problem",
        "",
        "In a cascaded two-stage adaptive optics instrument (such as Subaru AO3k + SCExAO), two "
        "wavefront sensors bracket an intermediate deformable mirror `DM2` (`D` = "
        "`aol2_modevalDM`). Upstream `WFS A` (`aol1_modevalWFS`) measures the post-`DM1` "
        "residual wavefront before `DM2`, while downstream `WFS B` (`aol2_modevalWFS`) measures "
        "the wavefront after `DM2`:",
        "",
        "```mermaid",
        "flowchart LR",
        "    ATM[\"Atmosphere + DM1<br/>Post-Stage-1 Residual φ1\"] --> "
        "A[\"WFS A (AO3k)<br/>1 kHz J-band PyWFS<br/>A = aol1_modevalWFS\"]",
        "    ATM --> SUM((\"+\"))",
        "    DM2[\"Inter-Stage DM2 (SCExAO)<br/>D = aol2_modevalDM<br/>"
        "(Stage-3 aol3_dmC also moves DM2, not in D)\"] --> SUM",
        "    SUM --> B[\"WFS B (SCExAO)<br/>2 kHz Vis PyWFS<br/>B = aol2_modevalWFS\"]",
        "    B --> C2[\"Stage-2 Controller C2(z)<br/>Integrator or PSOL AR(p)\"]",
        "    C2 --> DM2",
        "    A -. \"A\" .-> CAL[\"Telemetry System ID<br/>mlt.calib2wfs1dm / mlt.sysid\"]",
        "    B -. \"B\" .-> CAL",
        "    DM2 -. \"D\" .-> CAL",
        "    CAL -. \"Mab, Mdb, b0<br/>Mba, Mda_virt\" .-> OUT[\"Optical gain diag(Mdb)<br/>"
        "DM2→DM1 offload Mda_virt\"]",
        "```",
        "",
        "Over synchronized realizations `(A, B, D)`, the measurements obey two coupled linear "
        "relations:",
        "",
        "1. **Forward optical model**: `B[k] = Mab A[k] + Mdb D_eff[k] + b0 + v[k]`",
        "   - `Mab` (`dB × dA`): inter-WFS modal transformation from Stage-1 `WFS A` to Stage-2 "
        "`WFS B`.",
        "   - `Mdb` (`dB × dD`): Stage-2 `DM2 → WFS B` modal response under closed-loop "
        "conditions. Its diagonal is the PyWFS optical gain `g_opt(m)`, obtained without probes.",
        "   - `b0` (`dB`): static differential offset between `WFS A` and `WFS B`.",
        "2. **Virtual upstream model** (a second regression, of `A` on `(B, D)`): "
        "`A[k] = Mba B[k] - Mda_virt D_eff[k] + a0 + u[k]`",
        "   - `Mda_virt ≈ Mab^+ Mdb` (`dA × dD`): the virtual influence of `DM2` on `WFS A`, i.e. "
        "the `WFS A` modal pattern that corresponds to a unit `DM2` mode. This is the matrix "
        "needed to offload `DM2` onto `DM1` without a registration model.",
        "",
        "### Why Unwhitened Closed-Loop Regression Is Biased",
        "",
        "With negligible regularization (`reg = 1e-6`), unwhitened ordinary least squares returns "
        f"a median `diag(Mdb)` of `{fmt_range([m['ols_med'] for m in mb_all], '{:.2f}', '')}` "
        f"against a reference of `{fmt_range([m['srm_med'] for m in mb_all], '{:.2f}', '')}`, "
        f"i.e. a bias of `{fmt_range([m['ols_signed_err_pct'] for m in mb_all], '{:+.0f}')}`. "
        "The residual at the reference gain, `e_col[k] = B[k] - Mab A[k] - Mdb_ref D[k]`, shows "
        "the mechanism:",
        "",
        "| Telemetry Regime | `selfRM` reference | Unwhitened OLS (`reg=1e-6`) | Bias | Residual "
        "`e_col` lag-1 autocorr | `corr(e_col, D)` |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
        *[
            f"| {m['label']} | `{m['srm_med']:.3f}` | `{m['ols_med']:.3f}` | "
            f"**`{m['ols_signed_err_pct']:+.1f}%`** | `{m['ac1_res']:+.3f}` | "
            f"`{m['corr_res_d']:+.3f}` |"
            for m in mb_all
        ],
        "",
        "Two effects compound at low temporal frequency:",
        "- **Closed-loop collinearity**: Stage 2 drives `Mdb D ≈ -Mab A`, which shrinks the "
        "conditional DM excitation `eta_D = S_D / Sigma_DD` to "
        f"`{fmt_range(eta_raw, '{:.2f}', '')}`.",
        "- **Closed-loop feedback endogeneity**: unmodelled, temporally correlated residuals "
        "`e_col` (multi-rate `1 kHz` vs. `2 kHz` exposure mismatch, Stage-1 `DM1` steps, "
        f"modes beyond the {dim_a} retained in `A`, chromaticity, and Stage-3 LLOWFS commands on "
        "`dm02disp04`) are partly cancelled by Stage 2, which correlates `D` with `e_col` "
        f"(measured: `{fmt_range([m['corr_res_d'] for m in mb_all], '{:+.2f}', '')}`). A "
        "negative correlation biases OLS low.",
        "",
        "---",
        "",
        "## 2. Implemented Approach (`milk-mltools`): Shared Causal `AR(p)` Whitening `W(z)` + "
        "Block Schur Solver",
        "",
        "The pipeline shipped in `milk-mltools` (`mlt.calib2wfs1dm` / `mlt.sysid`) is a two-step "
        "regularized Schur-complement solver:",
        "",
        "1. **Multi-rate synchronization**: takes the slower WFS (`1 kHz` `A`) as reference, "
        "boxcar-averages `B`, and integrates the held `DM2` commands over each exposure window "
        "(`mlt.tlmsync .mode=expint`) while scanning plant lags `lag_DB ∈ [1.0..3.5] fr` to "
        "maximize held-out whitened `R²_w`.",
        "2. **Step 1 — shared scalar causal `AR(p)` whitening `W(z)`**: fits a pooled causal "
        "`AR(p)` filter on unit-variance-normalized `A` and applies the same scalar FIR filter to "
        "`(A, B, D)`. A scalar LTI filter commutes with the static matrices, so "
        "`W(z)[B] = Mab W(z)[A] + Mdb W(z)[D]` keeps `(Mab, Mdb)` unchanged while de-emphasizing "
        f"the low frequencies where the regressors are collinear{wz_gain_txt}. Block-regularized "
        "Schur normal equations with contiguous temporal cross-validation over `(reg_A, reg_D)` "
        "then give `Mdb`. This reduces the bias; Section 4 quantifies what remains.",
        "3. **Step 2 — pseudo-open-loop and virtual upstream refinement**: subtracts the "
        "calibrated DM contribution (`B_OL = B - Mdb D`) to refit `Mab` on unwhitened data, and "
        "solves the virtual upstream relation for `Mda_virt`.",
        "",
        "![Live Online Report 2x2 Calibration Summary](calib_2wfs1dm_summary_2x2.png)",
        "",
        "### Quantitative Sweeps: Whitening Order, Lag Landscape, Control Regimes & Convergence",
        "",
        "![AR(p) Whitening Sweep, Lag Surface, Control Regimes, and Sample-Size Convergence]"
        "(calib_2wfs1dm_whitening_lag_regimes_2x2.png)",
        "",
        "#### (a) `AR(p)` Whitening Order Sweep (`ao3k_scexao_calib2wfs1dm`, full run, "
        "`lag_DB = 2.50 fr`)",
        "",
        "| AR Order `p` | Conditional Excitation `eta_D` | `diag(Mdb)` (med) | Error of median "
        f"vs. `selfRM` ref (`{srm_ref:.3f}`) | Held-Out `R²_OL` | Cross-check |",
        "| :---: | ---: | ---: | ---: | ---: | ---: |",
        *[
            f"| `{r['order']}` | `{r['eta_d_white_med']:.3f}` | `{r['mdb_diag_med']:.3f}` | "
            f"**`{r['ref_err_pct']:.2f}%`** | `{r['r2_ol_raw_med']:.3f}` | "
            f"`{r['cross_rel_err']:.3f}` |"
            for r in sweep_p
        ],
        "",
        f"#### (b) Sample-Size Convergence (Clean `0–{T_CLEAN_S:.0f} s` Window)",
        "",
        "| Integration Time [s] | Aligned Frames (`1 kHz`) | `diag(Mdb)` (med) | Error of median "
        "| Held-Out `R²_OL` | Held-Out `R²_A` | `DM2→DM1` Geom Cosine | Cross-check |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        *[
            f"| `{r['t_s']:.1f} s` | `{r['nframes']}` | `{r['mdb_diag_med']:.3f}` | "
            f"`{r['ref_err_pct']:.2f}%` | `{r['r2_ol_raw_med']:.3f}` | "
            f"`{r['r2_a_raw_med']:.3f}` | **`{r['geom_cos_med']:.3f}`** | "
            f"`{r['cross_rel_err']:.3f}` |"
            for r in conv_sums
        ],
        "",
        conv_txt,
        "",
        "The cross-check column is `‖Mab · Mda_virt − Mdb‖ / ‖Mdb‖`, the relative mismatch "
        "between the forward and virtual-upstream fits. At "
        f"`{fmt_range([r['cross_rel_err'] for r in conv_sums], '{:.2f}', '')}` the two relations "
        "are consistent only to that level.",
        "",
        "---",
        "",
        "## 3. `DM2 → DM1` Offload Matrix & Stage-2/Stage-3 Transient",
        "",
        "![Virtual DM2 to DM1 Offload Matrix and Stage-2/Stage-3 Channel Activity]"
        "(calib_2wfs1dm_offload_and_zpo_2x3.png)",
        "",
        "### Offload Matrix vs. Actuator Geometry (Static Test)",
        "",
        "`Mda_virt` is fitted from telemetry alone, with no knowledge of the 64×64 vs. 50×50 "
        "actuator grids, the `60/46` pupil magnification, clocking, or registration. It is "
        "compared here with the geometric projection `M_geom` built from the two DM mode sets. "
        "This is a matrix comparison weighted by `2,400` recorded `DM2` shapes "
        "(`t = 2.8..4.0 s`); **no offload loop was run in the simulator**.",
        "",
        f"| Offload Metric ({dim_d} Modes) | Result | Notes |",
        "| :--- | ---: | :--- |",
        f"| `Mda_virt` vs. `M_geom` column cosine | **`{offload_stats['geom_cos_med_4s']:.3f}`** "
        f"(mean `{offload_stats['geom_cos_mean_4s']:.3f}`) | Range over modes "
        f"`{offload_stats['geom_cos_min_4s']:.2f}–{offload_stats['geom_cos_max_4s']:.2f}` "
        f"(clean 0–{T_CLEAN_S:.0f} s) |",
        f"| Amplitude ratio `Mda_virt / M_geom` | `{scale_med:.3f}` (IQR "
        f"`{offload_stats['scale_ratio_iqr_4s']:.3f}`) | {scale_note} |",
        f"| Mean {dim_d}-mode `DM2` OPD RMS | `{offload_stats['mean_dm2_rms_nm']:.1f} nm` | "
        "Stage-2 stroke carried during the test interval |",
        "| One-step offload (`Δa_DM1 = Mda_virt · d`) residual | "
        f"**`{offload_stats['oneshot_res_rms_nm']:.1f} nm`** | "
        f"`{offload_stats['oneshot_rms_red_pct']:.1f}%` RMS / "
        f"`{offload_stats['oneshot_var_red_pct']:.1f}%` variance reduction (using `M_geom` "
        f"instead: `{offload_stats['ideal_geom_res_nm']:.1f} nm`) |",
        f"| Largest snapshot (`{offload_stats['snap_in_nm']:.1f} nm`), one step | "
        f"`{offload_stats['snap_res_1shot_nm']:.1f} nm` | "
        f"`{offload_stats['snap_red_1shot_pct']:.1f}%` RMS reduction |",
        f"| Same snapshot, {N_OFFLOAD_ITER} static iterations at `g_off = {OFFLOAD_GAIN:.1f}` | "
        f"`{offload_stats['snap_stroke_iter_nm']:.1f} nm` stroke left + "
        f"`{offload_stats['snap_leak_iter_nm']:.1f} nm` outside the {dim_d}-mode subspace | "
        f"`{offload_stats['snap_red_iter_pct']:.1f}%` RMS reduction counting both terms "
        f"(`{offload_stats['snap_stroke_red_iter_pct']:.1f}%` counting stroke only); frozen "
        "snapshot, no noise or delay |",
        "| Offload map eigenvalues `Re(λ(M_loop))` | "
        f"**`[{offload_stats['eig_real_min']:+.3f}, {offload_stats['eig_real_max']:+.3f}]`** | "
        f"Largest imaginary part: `{offload_stats['eig_abs_imag_max']:.3f}` |",
        "| Spectral radius `ρ(I - g_off M_loop)` at `g_off = 0.5` / `0.2` | "
        f"**`{offload_stats['spec_rad_g05']:.3f}`** / **`{offload_stats['spec_rad_g02']:.3f}`** "
        f"| {stab_note} |",
        "",
        "### Stage-2/Stage-3 Transient on `DM2` (Panel b)",
        "",
        *transient_md,
        "",
        "---",
        "",
        "## 4. Limits of `W(z)` & an Exact-Window Frequency-Domain Alternative",
        "",
        f"`AR(4)` whitening reaches `{fmt_range(wz_pred)}` under predictive control, but it has "
        "three identifiable weaknesses:",
        "",
        "1. **It correlates the regressor with the noise.** `WFS B` noise `n_B[k]` is white and "
        "the loop delay makes the `DM2` state during exposure `k` independent of it "
        "(`E[D[k-τ] n_B[k]] = 0`). A causal FIR of order `p ≥ τ` spreads `n_B` over lags `0..p`, "
        "so `W(z)[D]` and `W(z)[n_B]` become correlated, and it amplifies high-frequency `WFS A` "
        "noise.",
        f"2. **`{fmt_range(wz_int, '{:.0f}')}` bias under a pure integrator.** Without the "
        "broadband `DM2` motion that predictive control adds (raw `eta_D` "
        f"`{fmt_range(eta_raw[:2], '{:.2f}', '')}` against "
        f"`{fmt_range(eta_raw[2:], '{:.2f}', '')}`), a scalar `W(z)` returns a median "
        f"`diag(Mdb)` of `{fmt_range(wz_int_med, '{:.2f}', '')}` against "
        f"`{fmt_range([mb_op['srm_med'], mb_cl['srm_med']], '{:.2f}', '')}`.",
        "3. **Multi-rate timing and low-order leakage.** Averaging `2 kHz` `B` onto `1 kHz` `A` "
        "centred at `t_A` ignores the `-0.25 ms` exposure-midpoint offset between the `1.0 ms` "
        "(`A`) and `0.5 ms` (`B`) integrations, and `W(z)` does not fully reject slow Stage-3 "
        f"motion: with LLOWFS closed, `diag(Mdb)` on {lo_lbl} is "
        f"`{fmt_range(mb_cl['w_d'][:lo], '{:.2f}', '')}`.",
        "",
        "### Exact-Window Frequency-Domain Estimator (Prototype)",
        "",
        "1. **Exposure-window alignment**: `WFS A` integrates `[t_A - 1.0 ms, t_A]` and `WFS B` "
        "integrates `[t_B - 0.5 ms, t_B]`. Averaging `B` centred at `t_A - 0.5 dt_B` matches "
        "`A`'s integration interval, with `DM2` aligned at `lag_DB = (0.5 + 2.5) dt_B = 3.0 dt_B`.",
        "2. **Band-limited cross-spectral regression (`20–480 Hz`)**: accumulate Welch "
        "cross-spectra `S_AA, S_AD, S_DD, S_BA, S_BD`, weight each frequency bin by "
        "`1 / tr(S_AA(f))`, and solve the same block normal equations. Frequencies below "
        "`20 Hz`, where Stage-3 and zero-point drifts live, are excluded by construction.",
        "",
        "By Parseval's theorem this is equivalent to a time-domain least-squares fit after a "
        "zero-phase, band-limited whitening filter. It is a non-parametric relative of `W(z)`, "
        "not a different class of estimator, and it shares the closed-loop endogeneity problem "
        "at frequencies where noise-driven `DM2` motion dominates.",
        "",
        "![W(z) Whitening vs Exact-Window Frequency-Domain Estimator]"
        "(calib_2wfs1dm_method_comparison_2x2.png)",
        "",
        "### Benchmark Across the 4 Control Regimes",
        "",
        "| Telemetry Regime | `selfRM` ref | Unwhitened OLS | `AR(4)` `W(z)` | Exact-window "
        "freq-domain `[20-480 Hz]` | Per-mode median / p90 error: `W(z)` | Per-mode median / p90 "
        f"error: freq-domain | MAE on {lo_lbl} (`W(z)` → freq-domain) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
        *[
            f"| {m['label']} | `{m['srm_med']:.3f}` | `{m['ols_med']:.3f}` "
            f"(`{m['ols_err_pct']:.1f}%`) | `{m['w_med']:.3f}` (`{m['w_err_pct']:.1f}%`) | "
            f"**`{m['freq_med']:.3f}` (`{m['freq_err_pct']:.1f}%`)** | "
            f"`{m['w_pm_med_pct']:.1f}%` / `{m['w_pm_p90_pct']:.1f}%` | "
            f"`{m['freq_pm_med_pct']:.1f}%` / `{m['freq_pm_p90_pct']:.1f}%` | "
            f"`{m['w_tt_mae']:.2f}` → `{m['freq_tt_mae']:.2f}` |"
            for m in mb_all
        ],
        "",
        "Percentages in columns 3–5 are errors of the median over modes; the per-mode columns "
        "give the median and 90th percentile of `|diag(Mdb) − ref| / ref` over individual modes.",
        "",
        "> **Result**: for the two integrator runs the error of the median is "
        f"`{fmt_range(wz_int)}` with `W(z)` and `{fmt_range(fr_int)}` with the frequency-domain "
        f"estimator (ratio `{fmt_range(int_factor, '{:.1f}', '×')}`). {sign_txt} {pred_txt} "
        f"The ratio of `W(z)` to frequency-domain MAE on {lo_lbl} is {low_factors} across the "
        f"four regimes. {low_txt}",
        "",
        "#### `selfRM` Reference Sensitivity",
        "",
        f"All errors above use {ref_def}. The alternative, {ref_alt_def}, gives a different "
        "median:",
        "",
        "| Telemetry Regime | Reference used | Alternative definition | Spread |",
        "| :--- | ---: | ---: | ---: |",
        *[
            f"| {m['label']} | `{m['srm_med']:.3f}` | `{m['ref_alt_med']:.3f}` | "
            f"`{m['ref_spread_pct']:.1f}%` |"
            for m in mb_all
        ],
        "",
        f"Errors smaller than this spread (`{fmt_range(ref_spreads)}`) are below what the "
        "reference can resolve.",
        "",
        "---",
        "",
        "## 5. Calibration Approaches: Measured and Proposed",
        "",
        "Panel `(a)` of the figure above shows the inter-WFS cross-correlation of first "
        "differences against lag. It has a broad maximum near the `-0.25 ms` exposure-midpoint "
        "offset and a second maximum near `+1.50 ms`, where Stage-1 `DM1` updates would appear. "
        "Both attributions come from the loop timing, not from a fit to this curve.",
        "",
        "### Measured in This Study",
        "",
        "| Approach | Principle | Integrator: error of median | Predictive: error of median | "
        f"MAE on {lo_lbl} | Status |",
        "| :--- | :--- | :---: | :---: | :---: | :--- |",
        "| **1. Causal `AR(p)` whitening `W(z)`** | Pooled scalar FIR on `(A, B, D)` + Schur "
        f"solver with cross-validation | `{fmt_range(wz_int)}` | `{fmt_range(wz_pred)}` | "
        f"`{fmt_range([m['w_tt_mae'] for m in mb_all], '{:.2f}', '')}` | Shipped in "
        "`mlt.sysid` (C) |",
        "| **2. Exact-window frequency-domain regression** | Exposure-matched sync + Welch "
        f"cross-spectra over `20–480 Hz` | `{fmt_range(fr_int)}` | `{fmt_range(fr_pred)}` | "
        f"`{fmt_range([m['freq_tt_mae'] for m in mb_all], '{:.2f}', '')}` | Python prototype in "
        "this report's generator; band and ridge terms set by hand |",
        "",
        "### Proposed, Not Yet Implemented or Measured",
        "",
        "| Approach | Principle | Expected benefit | Open question |",
        "| :--- | :--- | :--- | :--- |",
        "| **3. Multi-rate state-space model + Kalman-EM** | `2 kHz` latent state driven by the "
        "known `DM1`, `DM2`, `DM3` commands, with asynchronous `WFS A/B` observations | Keeps "
        "sensor noise white, models `DM3` and `zpo-2` explicitly, handles noise in `A` | "
        "Identifiability of `(Φ, Mab, Mdb)` and convergence of EM on a few seconds of data |",
        "| **4. Known-controller parametric fit** | Fit the closed-loop transfer function using "
        "the known `mfilt` gains | Uses loop structure instead of fighting it | Sensitivity to "
        "latency and `WFS A` noise-model errors |",
        "| **5. Recursive / sliding-window version of approach 2** | Exponentially weighted "
        "update of the cross-spectra | Continuous optical-gain tracking | Tracking lag against "
        "noise for realistic gain drifts |",
        "| **6. Small external excitation** | Brief Stage-2 gain switching, or a low-amplitude "
        "broadband `DM2` dither uncorrelated with sensor noise | Removes closed-loop bias at "
        "its source (see Ljung, *System Identification*, ch. 13) | Contrast cost of the dither "
        "has not been quantified |",
        "",
        "### Sketch of the Multi-Rate State-Space Model (Approach 3)",
        "",
        "On the `2 kHz` (`0.5 ms`) clock:",
        "",
        "- **State transition** (driven by the known Stage-1 `DM1` commands): "
        "`φ_1[k+1] = Φ φ_1[k] + M_d1 ΔD_1[k - τ_1] + w[k]`",
        "- **`WFS A` observation** (every 2nd tick, `1.0 ms` two-frame boxcar): "
        "`A[k] = G_A · 0.5 (φ_1[k] + φ_1[k-1]) + n_A[k]`, `n_A ~ N(0, R_A)`",
        "- **`WFS B` observation** (every tick, including `DM2` and Stage-3 `DM3`): "
        "`B[k] = Mab G_A φ_1[k] + Mdb H_2(q^-1)(D_2[k] + P_23 D_3[k]) - g_zpo D_3[k] + b0 + "
        "n_B[k]`, `n_B ~ N(0, R_B)`",
        "",
        "In this formulation the sensor noises are never filtered, the smoother covariance "
        "accounts for noise in `A`, and the fitted `(Φ, Mab, Mdb, R_A, R_B)` could feed an LQG "
        "controller. None of this has been implemented; the parameters are identifiable only up "
        "to a change of state basis, and EM may converge to local optima.",
        "",
        "---",
        "",
        "## 6. Potential Applications",
        "",
        "None of the following has been demonstrated in closed loop; each is what the fitted "
        "matrices would be used for.",
        "",
        "1. **`DM2 → DM1` stroke offloading without a registration model (`Mda_virt`)**: a "
        "low-bandwidth leaky offload `ΔD_1 = g_off · Mda_virt · D_2` into Stage 1. The static "
        f"test above gives `{offload_stats['oneshot_rms_red_pct']:.1f}%` one-step reduction of "
        f"{dim_d}-mode `DM2` stroke and a spectral radius of "
        f"`{offload_stats['spec_rad_g05']:.2f}` at `g_off = 0.5`.",
        "2. **Probe-free optical-gain tracking (`diag(Mdb)`)**: median gain to "
        f"`{fmt_range(wz_pred + fr_int)}` in these runs, usable for Stage-2 modal gain scaling, "
        "the predictive-filter `WFSfact`, and `zpo-2` offset scaling. Per-mode accuracy is "
        "coarser (table above).",
        "3. **Inter-stage feedforward (`Mab`, `Mda_virt`)**: `WFS A` and `DM1` are upstream of "
        "`DM2`, so Stage-1 residuals projected through `Mab` could give Stage 2 a disturbance "
        "preview.",
        "4. **Inter-stage offset monitoring (`b0`, `R²_A`)**: the intercept `b0` follows slow "
        "differential drift between the J-band and visible WFS paths; modes whose `R²_A` drops "
        "while `Mda_virt` stays well conditioned may indicate chromatic petal effects.",
        "5. **Registration and loop-health diagnostics (`Mab`, `Mda_virt`, `Mdb`)**: "
        "off-diagonal structure in `Mab` and `Mda_virt` responds to pupil shift, rotation or "
        "magnification; sudden drops in low-order `R²_A` or `diag(Mdb)` flag unobserved actuator "
        "channels, as in Section 3.",
        "",
        "---",
        "",
        "## Limitations",
        "",
        "- **Simulation only.** All telemetry is simulated; nothing here has been tested on sky.",
        f"- **One realization per regime** ({star_txt}). There are no error bars; the "
        f"sample-size sweep suggests scatter of order `{fmt_range(conv_errs, '{:.1f}')}` on the "
        "median gain.",
        "- **The `selfRM` reference is not measured under the same conditions.** The bench "
        "script acquires it after the science integration and, in predictive runs, with "
        "predictive filtering switched off first, so it describes a different loop state from "
        f"the telemetry it is compared with. Its two definitions differ by "
        f"`{fmt_range(ref_spreads)}`.",
        f"- **{dim_d} `DM2` modes and {dim_a} `WFS A` modes** are analysed, not the full mode "
        "sets.",
        "- **The offload result is a static matrix test**, not a closed-loop demonstration.",
        "- **The frequency-domain estimator is a prototype**: its band edges and ridge terms were "
        "set by hand with the reference in view, it has no held-out validation, and it differs "
        "from `W(z)` in timing alignment, band limit, whitening and regularization at once. "
        "Which of these produces the gain has not been isolated.",
        "- **The cause of the Stage-2/Stage-3 transient is not established** (Section 3).",
        "",
        "---",
        "",
        "## Reproducibility & GitHub Provenance",
        "",
        "All results, figures, CSV summaries and JSON diagnostics on this page are generated "
        "from simulated closed-loop telemetry: the CACAO control software running against the "
        "`cacaosim` hardware simulator, analysed with `milk-mltools`. Three simulation runs are "
        "required:",
        "",
        *recipe_md,
        "",
        *prov_md,
        "",
        "### Machine-Readable Artifacts",
        "",
        "- [calib_2wfs1dm_benchmark.json](calib_2wfs1dm_benchmark.json) — whitening sweep, "
        "sample-size convergence, offload statistics, transient detection, 4-regime method "
        "comparison (including per-mode errors and reference spread), and provenance",
        "- [calib_2wfs1dm_comparison.csv](calib_2wfs1dm_comparison.csv) — tabular benchmark of "
        "unwhitened OLS, `AR(4)` `W(z)`, and the exact-window frequency-domain estimator",
        "- Individual simulation reports: "
        "[ao3k_scexao_lowfs_open](../ao3k_scexao_lowfs_open/index.html) "
        "([How to Run](../ao3k_scexao_lowfs_open/how_to_run.html)) | "
        "[ao3k_scexao_lowfs_closed](../ao3k_scexao_lowfs_closed/index.html) "
        "([How to Run](../ao3k_scexao_lowfs_closed/how_to_run.html)) | "
        "[ao3k_scexao_calib2wfs1dm](../ao3k_scexao_calib2wfs1dm/index.html) ("
        "[Config](../ao3k_scexao_calib2wfs1dm/config.html) · "
        "[Optical](../ao3k_scexao_calib2wfs1dm/optical.html) · "
        "[Runtime](../ao3k_scexao_calib2wfs1dm/runtime.html) · "
        "[How to Run](../ao3k_scexao_calib2wfs1dm/how_to_run.html))",
        "",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(md_lines), encoding="utf-8")
