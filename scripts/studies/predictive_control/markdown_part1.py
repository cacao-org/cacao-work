#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Part I Sections 1-4 Markdown builder (Optical, Petals, Filter Anatomy)."""

from __future__ import annotations

from typing import Any

def append_part1_overview(lines: list[str], ctx: dict[str, Any]) -> None:
    """Append Title, Executive Takeaways, and Sections 1-4 to report lines."""
    bundles = ctx["bundles"]
    bmap = ctx["bmap"]
    s_int = ctx["s_int"]
    s_ar8 = ctx["s_ar8"]
    s_ar16 = ctx["s_ar16"]
    s_ab32 = ctx["s_ab32"]
    s_ab64 = ctx["s_ab64"]
    s_ar16_m14 = ctx["s_ar16_m14"]
    s_eof128 = ctx["s_eof128"]
    fmt_link = ctx["fmt_link"]
    fmt_cmp_link = ctx["fmt_cmp_link"]
    cpu_ar16 = ctx["cpu_ar16"]
    cpu_ab64 = ctx["cpu_ab64"]
    cpu_eof128 = ctx["cpu_eof128"]
    b1_eof = ctx["b1_eof"]
    s1_vr_gain = ctx["s1_vr_gain"]
    s1_wfe_drop = ctx["s1_wfe_drop"]
    s1_var_drop = ctx["s1_var_drop"]
    c15_gain = ctx["c15_gain"]
    c20_gain = ctx["c20_gain"]
    c20_5s_gain = ctx["c20_5s_gain"]
    dm3_drop = ctx["dm3_drop"]

    lines.extend(
        [
        "# Predictive Control Report: Per-Mode Diagonal AR(4..64) & Full Cross-Mode "
        "Block-EOF (VAR) Study",
        "",
        "Controlled hardware-in-the-loop study on the cascaded **Subaru 7.95 m AO3k + SCExAO + "
        "Lyot Coronagraph + Reflective-Lyot LLOWFS** closed-loop benchmark comparing two "
        "generations of CACAO pseudo-open-loop (PSOL) predictive control:",
        "",
        "- **Part I (Sections 2–7) — Per-Mode Diagonal `AR(P)` (`B = 1`)**: Independent "
        "per-mode Wiener auto-regressive filters (`cacaopc-mkARPF` + `cacaopc-applyARPF` + "
        "`mfilt`, zero cross-mode coupling) swept across **`AR(4)`**, **`AR(8)`**, **`AR(16)`**, "
        "**`AR(32)`**, and **`AR(64)`** (+ matched warm-start ablations `AR(32)*` & `AR(64)*`).",
        "- **Part II (Section 8) — Full Cross-Mode Transition Matrix Block-EOF (`VAR(P)`)**: "
        "The original CACAO Empirical Orthogonal Functions transition-matrix formulation "
        "(Guyon & Males 2017) capturing frozen-flow wind advection *between* coupled spatial "
        "modes across lookback lags, implemented natively in real-time C (`cacaopc-mkEOFPF` + "
        "`cacaopc-applyEOFPF`, OpenBLAS/LAPACKE + OpenMP SIMD) and benchmarked both offline on "
        "20.0 s PSOL telemetry and head-to-head in closed loop (**`Block-EOF(B=64, P=8)`** & "
        "**`Block-EOF(B=128, P=8)`**) against matched diagonal `AR(16)`.",
        "",
        "> **Executive Findings — Both Diagonal `AR(16)` and Cross-Mode `Block-EOF(B=128, P=8)` "
        "Have Distinct, Complementary Roles**:",
        ">",
        f"> 1. **Per-Mode Diagonal `AR(P)` (`B = 1`, Part I)**: At rapid online startup "
        f"(`N_min = 256`, `N_train = 2048`), **`Diagonal AR(16)`** is the clear Pareto optimum "
        f"across `AR(4)..AR(64)`: **`{s_ar16['vis_final_sr_pct']:.2f}%` Vis SR** "
        f"(`+{s_ar16['vis_final_sr_pct'] - s_int['vis_final_sr_pct']:.2f} pp` vs. Modal "
        f"Integrator), **`{s_ar16['nir_final_sr_pct']:.2f}%` H SR**, "
        f"**`{s_ar16['final_wfe_nm']:.1f} nm` final WFE**, zero Subaru V-spider petal slips "
        f"through a `1.85 um` gust, at **`24 us` / frame** and **`{cpu_ar16:.1f}%` CPU**. "
        f"Extending diagonal order to warm-start `AR(32)*` / `AR(64)*` (`N = 4096`) adds only "
        f"`+{s_ab64['vis_final_sr_pct'] - s_ar16['vis_final_sr_pct']:.2f} pp` Vis SR at "
        f"`{cpu_ab64 / cpu_ar16:.1f}x` CPU.",
        ">",
        f"> 2. **Full Cross-Mode Transition Matrix `Block-EOF(B=128, P=8)` (Part II)**: "
        f"Unlocking cross-mode advection coupling delivers a **qualitative leap** impossible "
        f"for any per-mode diagonal `AR(P)` order. On 20 s walk-forward telemetry, Block-EOF "
        f"beats diagonal `AR(16)` on **26 / 26 spatial blocks** (Stage-1 Block 0: "
        f"**`+{b1_eof['eof128_pct'][0]:.1f}%` vs. `+{b1_eof['ar16_def_pct'][0]:.1f}%`**) at "
        f"**`~3x` lower L2 noise gain**. In confounder-free closed loop on identical "
        f"`t = 14–19 s` unseen turbulence (`reg1 = 1e-4, reg2 = 1e-2`, `N_train = 16k / 32k`), "
        f"**`Block-EOF(B=128, P=8)`** cuts Stage-1 (AO3k) WFE by **`-{s1_wfe_drop:.1f} nm`** "
        f"(`{s_ar16_m14['stg1_wfe_nm']:.1f} -> {s_eof128['stg1_wfe_nm']:.1f} nm`, "
        f"`-{s1_var_drop:.1f}%` variance), boosts **Stage-1 Vis SR by `+{s1_vr_gain:.2f} pp`** "
        f"(`{s_ar16_m14['vis_stg1_sr_pct']:.2f}% -> {s_eof128['vis_stg1_sr_pct']:.2f}%`), "
        f"reaches **`{s_eof128['vis_final_sr_pct']:.2f}%` Final Vis SR / "
        f"{s_eof128['nir_final_sr_pct']:.2f}% H SR (`{s_eof128['final_wfe_nm']:.1f} nm`)**, "
        f"deepens H-band coronagraphic raw contrast by **`{c15_gain:.1f}%` @ `15 l/D` and "
        f"`{c20_gain:.1f}%` @ `20 l/D`** (`-{c20_5s_gain:.1f}%` 5-sigma planet contrast), and "
        f"cuts LLOWFS DM3 stroke by **`-{dm3_drop:.1f}%`** "
        f"(`{s_ar16_m14['llowfs_dm3_nm']:.1f} -> {s_eof128['llowfs_dm3_nm']:.1f} nm`) — "
        f"running in **`88–108 us` / frame** (`{cpu_eof128:.0f}%` CPU = 1.0 core, `0` RT "
        f"timeouts) via automatic `AR(16)` cold-start bootstrapping.",
        "",
        "## 1. Study Design & PSOL Predictive Control Architecture",
        "",
        "All simulations execute real native MILK/CACAO real-time daemons in isolated "
        "`/dev/shm/cacao_*` sandboxes coupled to the GPU-fused `8.0 kHz` (`dt = 125 us`) "
        "polychromatic Subaru optical bench (`ao3k_scexao.bench`, `0.60\"` Maunakea seeing, "
        "`mV = mH = 6.0`, `20%` throughput, identical response matrices loaded from "
        "`_work/ao3k_scexao_rm`, deterministic atmospheric phase screen realization). To "
        "support both studies cleanly, we expanded `ARPF_MAX_ORDER` from `32` to `64` in "
        "`mkARPF.c`/`applyARPF.c` and implemented native real-time cross-mode Block-EOF daemons "
        "`AOloopControl_PredictiveControl_mkEOFPF.c` and `_applyEOFPF.c`:",
        "",
        "- **Stage 1 (`AO3k`, `aol1`)**: `64x64` DM (`D = 60`), `160x160` J-band (`1.22 um`) "
        "PyWFS @ `1.0 kHz`, `1965` SVD modes, `testOL` PSOL latency `~2.28–2.52 fr` (`~2.4 ms`), "
        "`WFSfact = 1.04–1.06`",
        "- **Stage 2 (`SCExAO`, `aol2`)**: `50x50` DM (`D = 46`), `120x120` Vis (`0.75 um`) "
        "PyWFS @ `2.0 kHz`, `1255` SVD modes, `testOL` PSOL latency `~2.16–2.82 fr` (`~1.3 ms`), "
        "`WFSfact = 1.04–1.06`",
        "- **Stage 3 (`LLOWFS`, `aol3`)**: Closed-loop `14` Zernike modes (`Z2..Z15`) @ `500 Hz` "
        "from light reflected by the H-band Lyot stop (`3.0 l/D` focal mask, `+200 nm` Z4 "
        "defocus) with real-time `zpo-2` offloading into Stage-2 PyWFS",
        "- **Part I — Per-Mode Diagonal `AR(P)` (`B = 1`, Sections 2–7)**: `mkARPF` + "
        "`applyARPF`, `PF.mixcoeff = 0.90`, `reglambda = 0.005`, `pf_mgain_exp = 0.50`, "
        "`||w||_2^2 <= 1.35`, `|sum(w)| <= 0.985`, `tbuffsize = 256` frames, swept across "
        "`Modal Integrator`, `AR(4)`, `AR(8)`, `AR(16)`, `AR(32)`, `AR(64)` (`N = 256/2048`) "
        "plus warm-start ablations `AR(32)*` & `AR(64)*` (`N = 1024/4096`).",
        "- **Part II — Cross-Mode Block-EOF (`VAR(P)`, Section 8)**: `mkEOFPF` + "
        "`applyEOFPF`, coupled spatial blocks of size `B = 64` or `B = 128` across `P = 8` "
        "lags (`D = 512` or `1024` cross-mode predictors per output mode), progressive diagonal "
        "`AR(16)` cold-start bootstrap with smooth EMA cross-fade once `N >= minsamples`, "
        "evaluated after a matched `14.0 s` warmup (`N_train = 16384 / 32768`) on the exact "
        "same `5.0 s` unseen turbulence segment (`t = 14–19 s`) against both default and "
        "matched-regularization (`reg1 = 1e-4, reg2 = 1e-2`) diagonal `AR(16)`.",
        "",
        "```mermaid",
        "flowchart LR",
        (
            '    WFS["PyWFS + mfilt<br/>modevalWFS & modevalDM"] --> '
            'PSOL["PSOL Reconstructor<br/>modevalOL = WFSfact*WFS - DM(t-d)"]'
        ),
        '    PSOL --> BUFF["Double Buffer (256 fr)<br/>aolN_modevalOL_buff"]',
        (
            '    BUFF --> MK["Part I: mkARPF (Diag AR(P), B=1)<br/>'
            'Part II: mkEOFPF (Block-EOF VAR(P), B=64/128)"]'
        ),
        (
            '    MK --> MAT["Filter Matrix<br/>aolN_arPFmat [M x P] or<br/>'
            'aolN_eofPFmat [M x (P*B)]"]'
        ),
        (
            '    PSOL --> APP["Real-Time Inference (CPU SIMD/OMP)<br/>'
            'applyARPF (10-70 us) / applyEOFPF (76-108 us)"]'
        ),
        '    MAT --> APP',
        '    APP --> MIX["mfilt Blender (mix = 0.90)<br/>dmC = mix*(zpo - PF) + (1-mix)*Integ"]',
        "```",
        "",
        "## 2. Part I — Per-Mode Diagonal AR(4..64): Headline Optical & Coronagraphic Comparison",
        "",
        "Every row below links directly to the complete standalone Optical & Control Report "
        "(including 200 ms slow-motion speckle video, selfRM, and downloadable CSVs) and Compute "
        "Report for that simulation run:",
        "",
        "| Controller | `N_min / N_train` | Mem. Horizon (S1 / S2) | Post-AO3k WFE (Tot / Dyn) | "
        "Post-SCExAO WFE (Tot / Dyn) | S1 Vis SR | Final Vis SR | Final H SR | Coro Leak | "
        "Planet 3–10 l/D | 5-sig @ 5 l/D | Sub-Pages |",
        (
            "| :--- | :---: | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: "
            "| ---: | :---: |"
        ),
        ]
    )

    for b in bundles:
        s = b["summary"]
        ord_n = s["order"]
        n_str = "—" if ord_n == 0 else f"`{s['n_min']} / {s['n_train']}`"
        mem_str = "—" if ord_n == 0 else f"`{ord_n} ms / {ord_n / 2:.0f} ms`"
        bold_w = "**" if s["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else ""
        lines.append(
            f"| {fmt_link(b)} | {n_str} | {mem_str} | "
            f"{bold_w}`{s['stg1_wfe_nm']:.1f}`{bold_w} / `{s['stg1_std_nm']:.1f} nm` | "
            f"{bold_w}`{s['final_wfe_nm']:.1f}`{bold_w} / `{s['final_std_nm']:.1f} nm` | "
            f"`{s['vis_stg1_sr_pct']:.2f}%` | "
            f"{bold_w}`{s['vis_final_sr_pct']:.2f}%`{bold_w} | "
            f"{bold_w}`{s['nir_final_sr_pct']:.2f}%`{bold_w} | "
            f"`{s['coro_leak_pct']:.2f}%` | "
            f"{bold_w}`{s['coro_c3_10']:.2e}`{bold_w} | "
            f"`{s['coro_5s_5']:.2e}` | {fmt_cmp_link(b)} |"
        )

    lines.extend(
        [
            "",
            "![Optical & Coronagraphic Performance vs AR Order (2x3)]"
            "(ar_order_optical_coro_summary_2x3.png)",
            "",
            "### Coronagraphic Planet Contrast & 5-Sigma Speckle Profile Breakdown (H-Band, "
            "3.0 l/D Lyot Mask)",
            "",
            "| Controller | `3 l/D` Planet | `5 l/D` Planet | `10 l/D` Planet | "
            "`15 l/D` Planet | `20 l/D` Planet | `5-sig @ 15 l/D` | `5-sig @ 20 l/D` | "
            "LLOWFS DM3 RMS |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for b in bundles:
        s = b["summary"]
        lines.append(
            f"| **{b['spec']['short']}** | `{s['coro_c3']:.2e}` | `{s['coro_c5']:.2e}` | "
            f"`{s['coro_c10']:.2e}` | `{s['coro_c15']:.2e}` | `{s['coro_c20']:.2e}` | "
            f"`{s['coro_5s_15']:.2e}` | `{s['coro_5s_20']:.2e}` | `{s['llowfs_dm3_nm']:.1f} nm` |"
        )

    lines.extend(
        [
            "",
            "Key coronagraphic takeaways:",
            "",
            f"- **Inner-to-outer dark-hole gain**: Switching from Modal Integrator to "
            f"**`AR(16)`** improves mean 3–10 l/D planet contrast by **`19.7%`** "
            f"(`{s_int['coro_c3_10']:.2e}` -> `{s_ar16['coro_c3_10']:.2e}`), mean 5–20 l/D "
            f"contrast by **`24.0%`** (`{s_int['coro_c5_20']:.2e}` -> "
            f"`{s_ar16['coro_c5_20']:.2e}`), and cuts 5-sigma speckle noise at `15 l/D` by "
            f"**`5.3x`** (`{s_int['coro_5s_15']:.2e}` -> `{s_ar16['coro_5s_15']:.2e}`) and at "
            f"`20 l/D` by **`3.4x`** "
            f"(`{s_int['coro_5s_20']:.2e}` -> `{s_ar16['coro_5s_20']:.2e}`).",
            f"- **Outer-halo ceiling with warm-start `AR(32)*` / `AR(64)*`**: At `3–5 l/D`, "
            f"`AR(16)`, `AR(32)*`, and `AR(64)*` are statistically indistinguishable "
            f"(`3.14e-4` at `5 l/D`, `1.05e-4–1.06e-4` mean `3–10 l/D`). Only in the outer "
            f"control halo (`10–20 l/D`) does warm-start `AR(64)*` shave an extra `~3–9%` "
            f"off `AR(16)` (`{s_ab64['coro_c10']:.2e}` @ `10 l/D`, `{s_ab64['coro_c20']:.2e}` "
            f"@ `20 l/D`) and lower coronagraphic leakage slightly "
            f"(`{s_ab64['coro_leak_pct']:.2f}%` vs. `{s_ar16['coro_leak_pct']:.2f}%`).",
            f"- **Reduced Stage-3 LLOWFS workload**: Because Stage 1 and Stage 2 suppress "
            f"low-order wind-driven residuals cleanly under `AR(16)`, `AR(32)*`, and `AR(64)*`, "
            f"Stage-3 LLOWFS `dm02disp04` stroke drops from `{s_int['llowfs_dm3_nm']:.1f} nm` "
            f"(Integrator) and `{s_ar8['llowfs_dm3_nm']:.1f} nm` (`AR(8)`, fighting the late "
            f"petal transient) down to **`{s_ar16['llowfs_dm3_nm']:.1f} nm`** (`AR(16)`), "
            f"**`{s_ab32['llowfs_dm3_nm']:.1f} nm`** (`AR(32)*`), and "
            f"**`{s_ab64['llowfs_dm3_nm']:.1f} nm`** (`AR(64)*`).",
            "",
            "## 3. Temporal Evolution, Peak-Gust Resilience & Subaru V-Spider Petal Physics",
            "",
            "Because `milkatmturb` replays the exact same deterministic multi-layer Maunakea "
            "turbulence realization (`raw WFE = 994.7–995.0 nm` across all five default AR runs, "
            "with a major **`1845 nm` turbulence gust** arriving at `t = 4.4–4.9 s`), the time "
            "series exposes a critical nonlinear stability boundary on the Subaru Nasmyth-IR "
            "pupil (four pupil islands separated by `51.75 deg` V-spiders):",
            "",
            "| Controller | Full Med. WFE (S1 / Fin) | Early `[0–1 s]` (S1 / Fin) | "
            "Steady `[1.5–4.5 s]` (S1 / Fin, P95) | Peak Gust `[4.5–5.0 s]` (S1 / Fin, Max) | "
            "Stg-1 Island ΔPetal PTV | Petal Status |",
            "| :--- | :---: | :---: | :---: | :---: | ---: | :--- |",
        ]
    )

    petal_notes = {
        "integrator": "Slips at t~1.1 s (large lag)",
        "ar4": "Slips -1 λ_J on Right island @ t~0.7 s",
        "ar8": "Locked 0–4.7 s; slips @ 1.85 µm gust",
        "ar16": "**Zero petal slips across full 5.0 s**",
        "ar32": "Slips +1 λ_J on Left island at cold start",
        "ar32_n4096": "**Zero petal slips across full 5.0 s**",
        "ar64": "Slips +1 λ_J on Left island at cold start",
        "ar64_n4096": "**Zero petal slips across full 5.0 s**",
    }
    for b in bundles:
        s = b["summary"]
        lines.append(
            f"| **{b['spec']['short']}** | `{s['stg1_med_nm']:.1f} / {s['final_med_nm']:.1f} nm` | "
            f"`{s['early_stg1_nm']:.1f} / {s['early_final_nm']:.1f} nm` | "
            f"`{s['ss_stg1_nm']:.1f} / {s['ss_final_nm']:.1f} nm` (`{s['ss_final_p95_nm']:.1f}`) | "
            f"`{s['gust_stg1_nm']:.1f} / {s['gust_final_nm']:.1f} nm` "
            f"(`{s['gust_final_max_nm']:.1f}`) | "
            f"`{s['petal_ptv_stg1_nm']:.0f} nm` | {petal_notes[s['key']]} |"
        )

    lines.extend(
        [
            "",
            "![Temporal Evolution and Subaru V-Spider Petal OPD Maps (2x3)]"
            "(ar_order_timeseries_and_petals_2x3.png)",
            "",
            "Notice how cleanly the 2D mean Stage-1 pupil maps diagnose each failure mode:",
            "",
            "- **Subaru J-band `1 λ_J` island ambiguity (`1.22 um`)**: Whenever Stage-1 "
            "instantaneous temporal lag exceeds half a J-band wavelength across a V-spider gap, "
            "the Stage-1 J-band PyWFS wraps by `2 pi` and locks one pupil island at `±1 λ_J` "
            "(`~1136 nm` PTV on the Left island in default `AR(32)` and `AR(64)`; `~925 nm` "
            "time-averaged PTV on the Right island in `AR(4)`). Stage 2 (Vis PyWFS) + Stage 3 "
            "(H-band LLOWFS) absorb most of that static piston step, but residual "
            "diffraction/chromatic mismatch still costs `~4–8 pp` in Visible Strehl.",
            "- **Why `AR(8)` loses to `AR(16)`**: During quiescent seeing (`t = 1.5–4.5 s`), "
            "`AR(8)` tracks closely behind `AR(16)` (`56.0 nm` vs. `55.6 nm` mean final WFE, "
            "`81.1%` vs. `81.3%` Vis SR at `t = 4.0 s`). However, when the `1.85 um` gust hits "
            "at `t = 4.5–5.0 s`, `AR(8)`'s weaker low-order phase lead causes a Stage-1 petal "
            "excursion (`532 nm` Stg1 / `195 nm` Final peak), whereas **`AR(16)`, `AR(32)*`, "
            "and `AR(64)*` all stay locked through the gust (`~78 nm` Stg1 / `~62 nm` Final)**.",
            "- **Dynamic vs. static separation in default `AR(32)` and `AR(64)`**: Even after "
            "their cold-start petal offsets latch at `t < 0 s` (`488.6 nm` static mean), default "
            "`AR(32)` and `AR(64)` hold Stage-1 *dynamic* turbulence RMS at **`70.6 nm`** and "
            "**`71.7 nm`** (essentially tied with `AR(16)`'s `69.8 nm`) and survive the `1.85 um` "
            "gust without further slips — proving that default `AR(32)`/`AR(64)` failures are "
            "purely cold-start sample starvation rather than steady-state instability.",
            "",
            "## 4. Learned AR(P) Filter Anatomy: Why AR(16) Unlocks Low-Order Phase Lead",
            "",
            "Inspecting the actual converged `aol1_arPFmat.fits` and `aol2_arPFmat.fits` weight "
            "matrices reveals the exact mathematical mechanism governing `AR(4)` through `AR(64)` "
            "— the **Cauchy–Schwarz tradeoff between phase lead and L2 noise amplification**:",
            "",
            "| Controller | Stg-1 Low-Order `‖w‖₂²` | Stg-1 Low-Order DC | **Stg-1 Eff. Lead "
            "`-Σ k·w_k`** | Stg-1 Tail `Σ_{k≥8} w_k` | Stg-1 Med `‖w‖₂²` | Stg-2 Low-Order "
            "Eff. Lead | Stg-1 / Stg-2 Lag ΔVar |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
        ]
    )

    for b in bundles:
        if not b["filters"]:
            continue
        f1 = b["filters"][1]
        f2 = b["filters"][2]
        pf = b["summary"]["pf_stats"]
        lines.append(
            f"| **{b['spec']['short']}** | `{f1['lo_norm2']:.3f}` | `{f1['lo_dc']:.3f}` | "
            f"**`{f1['lo_lead_fr']:+.2f} fr`** | `{f1['tail_gt8_sum_lo']:+.3f}` | "
            f"`{f1['med_norm2']:.3f}` | `{f2['lo_lead_fr']:+.2f} fr` | "
            f"`{pf['stage1']['var_red_pct']:.1f}%` / `{pf['stage2']['var_red_pct']:.1f}%` |"
        )

    f1_4 = bmap["ar4"]["filters"][1]
    f1_8 = bmap["ar8"]["filters"][1]
    f1_16 = bmap["ar16"]["filters"][1]
    f1_32 = bmap["ar32"]["filters"][1]
    f1_64 = bmap["ar64"]["filters"][1]
    f1_64w = bmap["ar64_n4096"]["filters"][1]
    e_gt32_64 = (1.0 - float(f1_64["cum_tap_energy"][31])) * 100.0
    e_gt32_64w = (1.0 - float(f1_64w["cum_tap_energy"][31])) * 100.0
    lines.extend(
        [
            "",
            "![Learned AR Filter Impulse Responses, Cauchy-Schwarz Lead & Freq Response (2x2)]"
            "(ar_order_filter_weights_and_freq_2x2.png)",
            "",
            "Why this single physical mechanism governs the entire `AR(4)`–`AR(64)` sweep:",
            "",
            f"1. **`AR(4)` is trapped by the L2 noise-gain constraint**: To extrapolate a smooth "
            f"low-order atmospheric mode forward by `2.40 frames` using only 4 taps (`0..3 ms`), "
            f"a finite-difference extrapolator requires steep opposing weights whose L2 norm "
            f"exceeds `maxnorm2 = 1.35`. Regularization damping therefore forces `AR(4)` to "
            f"`w_lo = [0.66, 0.38, 0.10, -0.16]` — an effective phase lead of "
            f"**`{f1_4['lo_lead_fr']:+.2f} fr`** (it actually *lags* zero-order hold!) despite "
            f"carrying the **highest** noise gain (`||w||_2^2 = {f1_4['lo_norm2']:.3f}`).",
            f"2. **`AR(8)` reaches half-compensation**: Extending to 8 taps unlocks negative "
            f"differentiating weights on taps `k = 5..7`, lifting effective lead to "
            f"**`{f1_8['lo_lead_fr']:+.2f} fr`** while trimming `||w||_2^2` to "
            f"`{f1_8['lo_norm2']:.3f}`.",
            f"3. **`AR(16)` unlocks full low-order phase lead at lower noise**: Spreading the "
            f"negative differentiating tail smoothly across `k = 6..15 ms` "
            f"(`sum(w[8:]) = {f1_16['tail_gt8_sum_lo']:+.3f}`) raises effective lead by **`+46%`** "
            f"to **`{f1_16['lo_lead_fr']:+.2f} fr`** while *simultaneously cutting* low-order "
            f"noise-gain squared by **`17%`** (`{f1_8['lo_norm2']:.3f}` -> "
            f"`{f1_16['lo_norm2']:.3f}`)! By Cauchy–Schwarz, doubling the negative-lobe baseline "
            f"produces the same derivative slope with half the L2 weight energy.",
            f"4. **`AR(32)` hits atmospheric phase-lead saturation**: Extending from 16 to 32 "
            f"taps lowers `||w||_2^2` another `14%` (`{f1_32['lo_norm2']:.3f}`), but effective "
            f"phase lead saturates at **`{f1_32['lo_lead_fr']:+.2f} fr`** (`>98%` of Stage-2 "
            f"and `>97%` of Stage-1 tap energy lies inside the first `16 ms`).",
            f"5. **`AR(64)` confirms tail exhaustion beyond `32 ms`**: Doubling again to `64` "
            f"taps (`64 ms` @ Stage 1, `32 ms` @ Stage 2) leaves default `AR(64)` phase lead "
            f"identical to `AR(32)` (`{f1_64['lo_lead_fr']:+.2f} fr`, `||w||_2^2 = "
            f"{f1_64['lo_norm2']:.3f}`). In warm-start `AR(64)*`, tiny `~-0.005` tail weights "
            f"around `k = 35–50 ms` raise the DC linear moment `-sum(k * w_k)` to "
            f"**`{f1_64w['lo_lead_fr']:+.2f} fr`**, yet its `5–60 Hz` frequency-domain phase "
            "response overlaps `AR(32)*` tightly and only "
            f"**`{e_gt32_64w:.2f}%`** (`AR(64)*`) to **`{e_gt32_64:.2f}%`** (`AR(64)`) of total "
            "Stage-1 filter tap energy resides in taps `k = 32..63`, meaning the extra `32` "
            "parameters primarily fit finite-window estimation noise rather than physical "
            "frozen-flow wind transport.",
        ]
    )
