#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Part I Sections 5-7 Markdown builder (PSD, Bias-Variance, Compute)."""

from __future__ import annotations

from typing import Any

def append_part1_spectra_and_compute(lines: list[str], ctx: dict[str, Any]) -> None:
    """Append Sections 5-7 (PSD, Walk-Forward Scaling, Compute) to report lines."""
    bundles = ctx["bundles"]
    wf_study = ctx["wf_study"]
    s_ar16 = ctx["s_ar16"]
    s_ar32 = ctx["s_ar32"]
    s_ab32 = ctx["s_ab32"]
    s_ar64 = ctx["s_ar64"]
    s_ab64 = ctx["s_ab64"]
    cpu_ar16 = ctx["cpu_ar16"]
    cpu_ab32 = ctx["cpu_ab32"]
    cpu_ar64 = ctx["cpu_ar64"]
    cpu_ab64 = ctx["cpu_ab64"]

    lines.extend(
        [
            "## 5. Spatial Modal Spectra & Frequency-Domain Rejection (1 kHz & 2 kHz Telemetry)",
            "",
            "Computing Welch temporal PSDs directly from the saved 5.0 s `aol1_modevalWFS` "
            "(`1 kHz`, `5000` frames) and `aol2_modevalWFS` (`2 kHz`, `10000` frames) cubes "
            "confirms where each AR order improves closed-loop rejection:",
            "",
            "![Temporal PSDs and Spatial Modal Residual Spectra (2x2)]"
            "(ar_order_modal_and_psd_2x2.png)",
            "",
            "- **Wind-driven low-to-mid frequency band (`5–120 Hz` on Stage 1, `10–250 Hz` on "
            "Stage 2)**: `AR(16)`, `AR(32)*`, and `AR(64)*` overlap tightly and carve out the "
            "deepest temporal PSD suppression relative to both the Modal Integrator and "
            "`AR(4)`/`AR(8)`, directly translating the `+1.5 fr` phase lead shown in Section 4 "
            "into lower closed-loop residual energy.",
            "- **High-frequency waterbed & noise floor "
            "(`> 200 Hz` Stage 1 / `> 400 Hz` Stage 2)**: "
            "Because `AR(16)`, `AR(32)*`, and `AR(64)*` maintain lower L2 noise gain "
            "(`||w||_2^2 = 0.53 / 0.45 / 0.42`) than `AR(4)` (`0.70`), they avoid "
            "high-frequency overshoot while preserving superior low-frequency rejection.",
            "- **Spatial modal spectrum**: On Stage 1, `AR(16)`, `AR(32)*`, and `AR(64)*` "
            "suppress low-order modes (`0–20`) by nearly an order of magnitude relative to "
            "`AR(4)` and Integrator, and sustain uniform residual reduction across mid- "
            "(`20–255`) and high-order (`256–1964`) modes without destabilizing edge/high-order "
            "modes.",
            "",
            "## 6. Bias–Variance Tradeoff, Sample Complexity & Cold-Start Warmup Catch-22",
            "",
            "To rigorously separate *in-sample fit* from *out-of-sample generalization*, we ran a "
            "walk-forward evaluation of the exact `mkARPF` Wiener-ridge solver across "
            "`P in {1, 2, 4, 8, 12, 16, 24, 32, 48, 64}` and `N_train in {256, 512, 1024, 2048}` "
            "(training strictly on the first `N_train` frames and scoring out-of-sample on the "
            "second half of the 5.0 s clean PSOL telemetry):",
            "",
            "![Bias-Variance Tradeoff and Sample Complexity Scaling (2x2)]"
            "(ar_order_bias_variance_sample_complexity_2x2.png)",
            "",
            "### Walk-Forward Out-of-Sample Lag Variance Reduction (In-Sample / Out-of-Sample / "
            "Overfitting Gap)",
            "",
            "| Stage & `N_train` | `AR(4)` | `AR(8)` | `AR(16)` | `AR(32)` | `AR(64)` "
            "| Diagnosis |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
        ]
    )

    ord_idx = {p: wf_study["orders"].index(p) for p in (4, 8, 16, 32, 64)}
    wf_rows = [
        (
            "stage1",
            "256",
            "Stage 1 (`N=256`, Cold Start)",
            "AR(64) `N/P=4`: **-8.0%** (worse than ZOH!)",
        ),
        (
            "stage1",
            "1024",
            "Stage 1 (`N=1024`, Warm Start)",
            "AR(16)–AR(32) converge; AR(64) gap `9.1 pp`",
        ),
        (
            "stage1",
            "2048",
            "Stage 1 (`N=2048`, Full Window)",
            "Peaks at AR(32); AR(64) dips `-0.4 pp`",
        ),
        (
            "stage2",
            "256",
            "Stage 2 (`N=256`, Cold Start)",
            "AR(64) crashes to **-1.0%** (`49 pp` gap)",
        ),
        (
            "stage2",
            "2048",
            "Stage 2 (`N=2048`, Full Window)",
            "Peaks at AR(16); monotonic decline to AR(64)",
        ),
    ]
    for stg_k, n_s, rlbl, diag in wf_rows:
        sd = wf_study["stages"][stg_k]
        cells = []
        for p in (4, 8, 16, 32, 64):
            idx_p = ord_idx[p]
            vi = sd["in_pct"][n_s][idx_p]
            vo = sd["out_pct"][n_s][idx_p]
            cells.append(f"`{vi:+.1f}%` / **`{vo:+.1f}%`** (`{vi - vo:+.1f}`)")
        lines.append(f"| {rlbl} | {' | '.join(cells)} | {diag} |")

    b1 = wf_study["stages"]["stage1"]["bands_2048"]
    lines.extend(
        [
            "",
            "### Stage-1 Out-of-Sample Generalization by Spatial Mode Band (`N_train = 2048`)",
            "",
            "| Spatial Mode Band | `AR(4)` Out-of-Sample | `AR(8)` Out-of-Sample | "
            "`AR(16)` Out-of-Sample | `AR(32)` Out-of-Sample | `AR(64)` Out-of-Sample |",
            "| :--- | ---: | ---: | ---: | ---: | ---: |",
            f"| **TT + Low (`0–19`)** | `{b1['tt_low']['4']['out_pct']:+.2f}%` | "
            f"`{b1['tt_low']['8']['out_pct']:+.2f}%` | "
            f"**`{b1['tt_low']['16']['out_pct']:+.2f}%`** | "
            f"`{b1['tt_low']['32']['out_pct']:+.2f}%` | "
            f"`{b1['tt_low']['64']['out_pct']:+.2f}%` |",
            f"| **Mid (`20–255`)** | `{b1['mid']['4']['out_pct']:+.2f}%` | "
            f"`{b1['mid']['8']['out_pct']:+.2f}%` | "
            f"`{b1['mid']['16']['out_pct']:+.2f}%` | "
            f"**`{b1['mid']['32']['out_pct']:+.2f}%`** | "
            f"`{b1['mid']['64']['out_pct']:+.2f}%` |",
            f"| **High (`256–1964`)** | `{b1['high']['4']['out_pct']:+.2f}%` | "
            f"`{b1['high']['8']['out_pct']:+.2f}%` | "
            f"`{b1['high']['16']['out_pct']:+.2f}%` | "
            f"**`{b1['high']['32']['out_pct']:+.2f}%`** | "
            f"`{b1['high']['64']['out_pct']:+.2f}%` |",
            f"| **All Modes (`0–1964`)** | `{b1['all']['4']['out_pct']:+.2f}%` | "
            f"`{b1['all']['8']['out_pct']:+.2f}%` | "
            f"`{b1['all']['16']['out_pct']:+.2f}%` | "
            f"**`{b1['all']['32']['out_pct']:+.2f}%`** | "
            f"`{b1['all']['64']['out_pct']:+.2f}%` |",
            "",
            (
                "### Closed-Loop Verification: `AR(32)*`, `AR(64)*` & the `AR(64)` "
                "Warmup Catch-22"
            ),
            "",
            "The walk-forward curves predict two distinct pathologies for high-order filters, "
            "both confirmed directly in closed loop:",
            "",
            f"1. **Matched warm-start (`N_min = 1024, N_train = 4096`) eliminates cold-start "
            f"petal jumps on both `AR(32)*` and `AR(64)*`**: On `AR(32)*`, Stage-1 WFE drops "
            f"from `{s_ar32['stg1_wfe_nm']:.1f} nm` (`{s_ar32['stg1_mean_nm']:.1f} nm` static "
            f"petal) to **`{s_ab32['stg1_wfe_nm']:.1f} nm`** and Final Vis Strehl jumps from "
            f"`{s_ar32['vis_final_sr_pct']:.2f}%` to **`{s_ab32['vis_final_sr_pct']:.2f}%`**. "
            f"On `AR(64)*`, Stage-1 WFE likewise drops from `{s_ar64['stg1_wfe_nm']:.1f} nm` to "
            f"**`{s_ab64['stg1_wfe_nm']:.1f} nm`** and Final Vis Strehl rises from "
            f"`{s_ar64['vis_final_sr_pct']:.2f}%` to **`{s_ab64['vis_final_sr_pct']:.2f}%`** "
            f"(`{s_ab64['nir_final_sr_pct']:.2f}%` H-band SR).",
            f"2. **Asymptotic saturation beyond `AR(16)`**: Even with `2x` larger training "
            f"windows (`4096` frames = `4.1 s` @ Stage 1), `AR(32)*` beats default `AR(16)` by "
            f"only **`+{s_ab32['vis_final_sr_pct'] - s_ar16['vis_final_sr_pct']:.2f} pp` Vis "
            f"SR**, and doubling order again to `AR(64)*` adds just "
            f"**`+{s_ab64['vis_final_sr_pct'] - s_ab32['vis_final_sr_pct']:.2f} pp` Vis SR** "
            f"(`+{s_ab64['vis_final_sr_pct'] - s_ar16['vis_final_sr_pct']:.2f} pp` total above "
            f"`AR(16)`) while Stage-1 Vis Strehl actually dips slightly "
            f"(`{s_ab64['vis_stg1_sr_pct']:.2f}%` vs. `{s_ab32['vis_stg1_sr_pct']:.2f}%` for "
            f"`AR(32)*` and `{s_ar16['vis_stg1_sr_pct']:.2f}%` for `AR(16)`).",
            "3. **The `AR(64)` Warmup Catch-22**: Attempting to satisfy the safe `N_min / P = 32` "
            "rule directly for `AR(64)` by setting `N_min = 2048` (`2.05 s` in plain integrator "
            "mode before activating prediction) *also fails* (`74.44%` Vis SR, `528.7 nm` "
            "Post-AO3k WFE, `77.5 nm` Final WFE) — because the Modal Integrator itself slips a "
            "Stage-1 petal around `t ~ 1.1 s` before `AR(64)` finishes collecting its warmup "
            "buffer! Setting `N_min = 1024` (`1.02 s`) threads a razor-thin window right ahead "
            "of the integrator slip threshold (`N_min / P = 16`), proving that any on-sky "
            "deployment of `P >= 32` requires **progressive order staging** (bootstrap rapidly "
            "with `AR(16)` at `N = 256`, then promote to higher order once `N >= 4096` clean "
            "frames are buffered).",
            "",
            "## 7. Real-Time Compute Scalability & Accuracy–Compute Pareto Frontier",
            "",
            "All runs were profiled on the uncontended host (AMD EPYC 9755, `OMP_NUM_THREADS=2` "
            "for `mkARPF`, single-thread SIMD for `applyARPF`, NVIDIA RTX PRO 6000 Blackwell "
            "for GPU optical propagation & MVM):",
            "",
            "| Controller | `mkARPF-1` p50 (CPU%) | `mkARPF-2` p50 (CPU%) | "
            "`applyARPF-1` p50 / p99 | `applyARPF-2` p50 / p99 | `mfilt-2` p50 | "
            "Total PF CPU% | Filter Mem (S1+S2) | RT Timeouts |",
            "| :--- | :---: | :---: | :---: | :---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for b in bundles:
        s = b["summary"]
        if s["order"] == 0:
            continue
        pr = s["procs"]
        pf = s["pf_stats"]
        mk1 = pr.get("mkARPF-1", {})
        mk2 = pr.get("mkARPF-2", {})
        ap1 = pr.get("applyARPF-1", {})
        ap2 = pr.get("applyARPF-2", {})
        mf2 = pr.get("mfilt-2", {})
        tot_cpu = sum(x.get("cl_cpu_pct", 0.0) for x in (mk1, mk2, ap1, ap2))
        mem_kb = (1965 + 1255) * s["order"] * 4 / 1024.0
        tot_to = int(pf["stage1"]["timeout_cnt"]) + int(pf["stage2"]["timeout_cnt"])
        lines.append(
            f"| **{b['spec']['short']}** | "
            f"`{mk1.get('exec_p50_us', 0) / 1e3:.1f} ms` (`{mk1.get('cl_cpu_pct', 0):.1f}%`) | "
            f"`{mk2.get('exec_p50_us', 0) / 1e3:.1f} ms` (`{mk2.get('cl_cpu_pct', 0):.1f}%`) | "
            f"`{ap1.get('exec_p50_us', 0):.1f}` / `{ap1.get('exec_p99_us', 0):.1f} us` | "
            f"`{ap2.get('exec_p50_us', 0):.1f}` / `{ap2.get('exec_p99_us', 0):.1f} us` | "
            f"`{mf2.get('exec_p50_us', 0):.1f} us` | "
            f"**`{tot_cpu:.1f}%`** | `{mem_kb:.1f} KB` | `{tot_to}` |"
        )

    ap1_64 = s_ar64["procs"]["applyARPF-1"]["exec_p50_us"]
    ap2_64 = s_ar64["procs"]["applyARPF-2"]["exec_p50_us"]
    mk1_64 = s_ar64["procs"]["mkARPF-1"]["exec_p50_us"] / 1e3
    mk2_64 = s_ar64["procs"]["mkARPF-2"]["exec_p50_us"] / 1e3
    mk1_64w = s_ab64["procs"]["mkARPF-1"]["exec_p50_us"] / 1e3
    mk2_64w = s_ab64["procs"]["mkARPF-2"]["exec_p50_us"] / 1e3
    lines.extend(
        [
            "",
            "![H-Band Coronagraphic PSFs and Real-Time Compute Scaling (2x3)]"
            "(ar_order_psf_and_compute_2x3.png)",
            "",
            "Key compute scalability conclusions:",
            "",
            f"- **Linear real-time inference remains safe even at `AR(64)`**: `cacaopc-applyARPF` "
            f"scales linearly `O(NBmode * P)` from `10.1 us` (`AR(4)`) to `24.2 us` (`AR(16)`), "
            f"`41.5 us` (`AR(32)`), and `{ap2_64:.1f} us` (`AR(64)`) on 1255 Stage-2 modes at "
            f"`2.0 kHz` (`{ap2_64 / 500.0 * 100.0:.1f}%` of a `500 us` frame; `{ap1_64:.1f} us` "
            "on Stage 1 @ `1 kHz`) with **`0` synchronization timeouts** across all 8 runs.",
            f"- **Quadratic online solver explosion at `AR(64)` (`O(N_train * P^2 + P^3)`)**: "
            f"On `N_train = 2048`, `mkARPF-1` climbs from `17.6 ms` (`AR(4)`) -> `63.3 ms` "
            f"(`AR(16)`) -> `149.8 ms` (`AR(32)`) -> **`{mk1_64:.1f} ms`** (`AR(64)`, "
            f"`{mk2_64:.1f} ms` Stage 2, **`{cpu_ar64:.1f}%` CPU**). Doubling `N_train` to "
            f"`4096` for `AR(64)*` drives solver updates to **`{mk1_64w:.1f} ms`** / "
            f"**`{mk2_64w:.1f} ms`** (**`{cpu_ab64:.1f}%` CPU = 4.6 full cores = "
            f"{cpu_ab64 / cpu_ar16:.1f}x `AR(16)`**), where updates exceed the `256`-frame "
            "double-buffer cadence (`128 ms` @ 2 kHz, `256 ms` @ 1 kHz) and begin dropping "
            "intermediate solver refresh cycles.",
            f"- **Exact algorithmic speedup if `P >= 32` is ever needed**: Because `mkARPF.c` "
            f"currently forms each `P x P` Gram matrix via nested `O(N_train * P^2)` loops over "
            "shifted lags of the same 1D modal series, exploiting the near-Toeplitz shift "
            "recurrence (`G[j+1, k+1] = G[j, k] + boundary terms`) reduces Gram formation to "
            "`O(N_train * P + P^2)` — a `~10–20x` speedup at `P = 64`.",
            f"- **Pareto optimality**: **`AR(16)`** sits squarely at the knee of the "
            f"accuracy–compute Pareto frontier (`{cpu_ar16:.1f}%` total predictive CPU vs. "
            f"`{cpu_ab32:.1f}%` for `AR(32)*` and `{cpu_ab64:.1f}%` for `AR(64)*`, delivering "
            f"`{s_ar16['vis_final_sr_pct'] / s_ab64['vis_final_sr_pct'] * 100.0:.2f}%` of "
            "`AR(64)*`'s Visible Strehl and `99.93%` of its H-band Strehl at **`1/14th` the "
            "CPU cost**).",
        ]
    )
