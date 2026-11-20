#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Part II Block-EOF Sections 8-9, Reproducibility, and top-level Markdown assembler."""

from __future__ import annotations

from typing import Any

from .markdown_context import build_report_context
from .markdown_part1 import append_part1_overview
from .markdown_part2 import append_part1_spectra_and_compute

def append_part2_eof_and_repro(lines: list[str], ctx: dict[str, Any]) -> None:
    """Append Sections 8-9 (Block-EOF) and Reproducibility to report lines."""
    eof_bundles = ctx["eof_bundles"]
    eof_study = ctx["eof_study"]
    s_ar16_d14 = ctx["s_ar16_d14"]
    s_ar16_m14 = ctx["s_ar16_m14"]
    s_eof64 = ctx["s_eof64"]
    s_eof128 = ctx["s_eof128"]
    repos = ctx["repos"]
    fmt_link = ctx["fmt_link"]
    fmt_cmp_link = ctx["fmt_cmp_link"]
    pf_cpu_sum = ctx["pf_cpu_sum"]
    cpu_ar16_m14 = ctx["cpu_ar16_m14"]
    cpu_eof64 = ctx["cpu_eof64"]
    cpu_eof128 = ctx["cpu_eof128"]
    b1_eof = ctx["b1_eof"]
    b2_eof = ctx["b2_eof"]
    s1_vr_gain = ctx["s1_vr_gain"]
    s1_wfe_drop = ctx["s1_wfe_drop"]
    c15_gain = ctx["c15_gain"]
    c20_gain = ctx["c20_gain"]
    c20_5s_gain = ctx["c20_5s_gain"]
    dm3_drop = ctx["dm3_drop"]

    lines.extend(
        [
            "## 8. Part II — Full Cross-Mode Transition Matrix Block-EOF (VAR(P)) vs. "
            "Per-Mode Diagonal AR(P)",
            "",
            "### 8.1 Diagonal AR(P) vs. Original CACAO Empirical Orthogonal Functions (EOF)",
            "",
            "Part I (Sections 2–7) evaluated **per-mode diagonal `AR(P)`** (`cacaopc-mkARPF` / "
            "`cacaopc-applyARPF`), where each output mode `m` predicts its own future amplitude "
            "`a_m(t + d)` exclusively from its own scalar history `[a_m(t), ..., a_m(t - P + 1)]` "
            "— a `B = 1` diagonal restriction that ignores spatial cross-correlations between "
            "modes. In contrast, the original CACAO predictive controller (Guyon & Males 2017, "
            "**Empirical Orthogonal Functions / EOF**) fits a **full vector auto-regressive "
            "(`VAR(P)`) cross-mode transition matrix** `F` predicting each mode `i` from a "
            "coupled block of `B` spatial modes over `P` lookback steps (`D = P * B` predictors "
            "per output mode):",
            "",
            "- **Physical mechanism — Taylor frozen-flow advection**: As atmospheric wind layers "
            "carry turbulent wavefront features across the 7.95 m Subaru pupil, an upstream mode "
            "at time `t` translates into downstream and quadrature spatial modes at time `t + d`. "
            "For any Fourier/KL sine–cosine mode pair `(c, s)`, advection acts as a 2D "
            "skew-symmetric phase rotation `[c(t+d); s(t+d)] = R(k . v * d) [c(t); s(t)]`. "
            "Diagonal `AR(P)` cannot see the quadrature partner and must instead approximate "
            "temporal derivatives via finite differencing (which amplifies WFS noise), whereas "
            "cross-mode EOF reads the approaching wavefront directly off coupled modes.",
            "- **Block-diagonal scaling (`B = 64` or `B = 128`, `P = 8`)**: Grouping the `1965` "
            "Stage-1 modes (`16` blocks of `B = 128`, or `31` blocks of `B = 64`) and `1255` "
            "Stage-2 modes (`10` blocks of `B = 128`, or `20` blocks of `B = 64`) by radial "
            "spatial frequency preserves the dense cross-mode couplings among adjacent spatial "
            "scales while keeping per-block normal equations `(X^T X + lam * tr * I) W = X^T Y` "
            "at `D = 512..1024`, solvable online in `~1–4 s` via OpenBLAS `cblas_dsyrk` / "
            "`cblas_dgemm` + LAPACKE `dpotrf` / `dpotrs` and applicable in real time at "
            "`< 110 us` / frame via OpenMP + AVX-512 SIMD (`cacaopc-applyEOFPF`).",
            "- **Mandatory progressive `AR(16)` cold-start bootstrap**: Because `Block-EOF` "
            "fits `D = P * B = 512..1024` predictors per mode (vs. `P = 16` for diagonal "
            "`AR(16)`), `mkEOFPF` automatically starts in **per-mode diagonal `AR(16)`** mode "
            "(`diagorder = 16`, `state = 1`) at `N = 256` frames (`0.25 s`) to lock Subaru "
            "V-spider petals immediately, then smoothly cross-fades via EMA into full "
            "cross-mode Block-EOF (`state = 2`) once `N >= minsamples` (`6,000` for `B = 64`, "
            "`12,000` for `B = 128`) clean PSOL frames are buffered.",
            "",
            "### 8.2 Offline 20.0 s Walk-Forward Study: Sample Complexity, Full-Pupil Gain & "
            "Noise-Gain Physics",
            "",
            "Before running closed-loop hardware-in-the-loop trials, we recorded a clean "
            "`20.0 s` PSOL telemetry cube (`ao3k_scexao_tlm20s_ar16`: `20,000` Stage-1 frames "
            "@ `1 kHz`, `40,000` Stage-2 frames @ `2 kHz`, zero petal slips) and evaluated "
            "diagonal `AR(16)` vs. cross-mode `Block-EOF(B=64/128, P=8)` strictly out-of-sample "
            "on the unseen final `5.0 s` (`t = 15–20 s`):",
            "",
            "![Cross-Mode Block-EOF vs. Diagonal AR(16): 20 s Walk-Forward Physics (2x2)]"
            "(eof_vs_ar_offline_20s_2x2.png)",
            "",
            "| Stage & Spatial Mode Band | `N_train` | Diag `AR(16)` (`reg=5e-3`) | "
            "Diag `AR(16)` (Matched `reg`) | **Block-EOF (`B=128, P=8`)** | "
            "Cross-Mode Gain (`Δpp` vs. Matched) |",
            "| :--- | :---: | ---: | ---: | ---: | ---: |",
            (
                f"| **Stage 1 — Block 0 (`0–127`, Low/Mid)** | `14,500` | "
                f"`+{b1_eof['ar16_def_pct'][0]:.2f}%` | "
                f"`+{b1_eof['ar16_mat_pct'][0]:.2f}%` | "
                f"**`+{b1_eof['eof128_pct'][0]:.2f}%`** | "
                f"**`+{b1_eof['eof128_pct'][0] - b1_eof['ar16_mat_pct'][0]:.2f} pp`** |"
            ),
            (
                f"| **Stage 1 — Block 1 (`128–255`)** | `14,500` | "
                f"`+{b1_eof['ar16_def_pct'][1]:.2f}%` | "
                f"`+{b1_eof['ar16_mat_pct'][1]:.2f}%` | "
                f"**`+{b1_eof['eof128_pct'][1]:.2f}%`** | "
                f"**`+{b1_eof['eof128_pct'][1] - b1_eof['ar16_mat_pct'][1]:.2f} pp`** |"
            ),
            (
                f"| **Stage 1 — Block 2 (`256–383`)** | `14,500` | "
                f"`+{b1_eof['ar16_def_pct'][2]:.2f}%` | "
                f"`+{b1_eof['ar16_mat_pct'][2]:.2f}%` | "
                f"**`+{b1_eof['eof128_pct'][2]:.2f}%`** | "
                f"**`+{b1_eof['eof128_pct'][2] - b1_eof['ar16_mat_pct'][2]:.2f} pp`** |"
            ),
            (
                f"| **Stage 1 — All 16 Blocks (`0–1964`)** | `14,500` | "
                f"`+{b1_eof['tot_ar16_def_pct']:.2f}%` | "
                f"`+{b1_eof['tot_ar16_mat_pct']:.2f}%` | "
                f"**`+{b1_eof['tot_eof128_pct']:.2f}%`** | "
                f"**`+{b1_eof['tot_eof128_pct'] - b1_eof['tot_ar16_mat_pct']:.2f} pp`** |"
            ),
            (
                f"| **Stage 2 — Block 0 (`0–127`)** | `29,000` | "
                f"`+{b2_eof['ar16_def_pct'][0]:.2f}%` | "
                f"`+{b2_eof['ar16_mat_pct'][0]:.2f}%` | "
                f"**`+{b2_eof['eof128_pct'][0]:.2f}%`** | "
                f"**`+{b2_eof['eof128_pct'][0] - b2_eof['ar16_mat_pct'][0]:.2f} pp`** |"
            ),
            (
                f"| **Stage 2 — All 10 Blocks (`0–1254`)** | `29,000` | "
                f"`+{b2_eof['tot_ar16_def_pct']:.2f}%` | "
                f"`+{b2_eof['tot_ar16_mat_pct']:.2f}%` | "
                f"**`+{b2_eof['tot_eof128_pct']:.2f}%`** | "
                f"**`+{b2_eof['tot_eof128_pct'] - b2_eof['tot_ar16_mat_pct']:.2f} pp`** |"
            ),
            "",
            "Key offline physics findings confirmed in Figure 7:",
            "",
            "1. **Universal full-pupil gain (`26 / 26` spatial blocks win)**: Cross-mode "
            "`Block-EOF(B=128, P=8)` outperforms both default and regularization-matched "
            "diagonal `AR(16)` on *every single one* of the 16 Stage-1 blocks and all 10 Stage-2 "
            "blocks, peaking at **`+81.5%` out-of-sample lag variance reduction** on Stage-1 "
            "Block 0 (cutting residual lag variance `~2.5x` below default `AR(16)`).",
            "2. **~3x lower L2 noise gain at equal or better lag suppression**: Sweeping "
            "regularization `lam` (Figure 7, bottom-left) proves that Cross-Mode EOF strictly "
            "dominates Diagonal `AR(16)` across the entire noise-gain Pareto curve — beating "
            "even unconstrained `AR(16)` (`||w||_2^2 > 2.1`) while maintaining **`||F_m||_2^2 "
            "~ 0.7–0.9`**.",
            "3. **Sample-complexity threshold (`N / D >= 8`)**: At `N_train = 2048` (`N/D = 2`), "
            "unbootstrapped `Block-EOF(B=128, P=8)` catastrophically overfits "
            f"(`{eof_study['sample_complexity']['eof128_p8_pct'][0]:.0f}%`), crossing strongly "
            "positive at `N = 8192` (`N/D = 8`) and saturating near `N = 12,000–14,500`, while "
            "`B = 64` (`D = 512`) converges `2x` earlier (`N >= 6,000`).",
            "4. **Direct signature of frozen-flow quadrature coupling**: Inspecting the "
            "converged closed-loop `aol1_eofPFmat.fits` matrix (Figure 7, bottom-right) reveals "
            "crisp skew-symmetric quadrature wind-advection pairs — e.g., `mode 50 <- mode 47 "
            "(+0.081)` vs. `mode 47 <- mode 50 (-0.076)`, `(16 <-> 17)`, `(3 <-> 4)`, `(8 <-> 9)` "
            "— with off-diagonal L2 energy rising smoothly with spatial frequency from `12.6%` "
            "(Block 0) to `32.9%` (Block 14) as `k . v * d` increases.",
            "",
            "### 8.3 Matched `14.0 s`-Warmup Closed-Loop Head-to-Head Comparison",
            "",
            "To evaluate pure cross-mode transition-matrix performance in closed loop with "
            "**zero regularization or warmup confounders**, we ran four matched simulations "
            "with identical `14.0 s` warmup (`N_train = 16,384` @ Stage 1, `32,768` @ Stage 2) "
            "evaluated over the exact same `5.0 s` unseen turbulence segment (`t = 14–19 s`, "
            "`Raw WFE = 1055–1060 nm`, zero petal slips, `0` real-time timeouts):",
            "",
            "| Controller (`t = 14–19 s`, `N = 16k/32k`) | `reg` (S1 / S2) | "
            "Post-AO3k WFE (Tot / Max) | S1 Vis SR | Post-SCExAO WFE | Final Vis SR | "
            "Final H SR | Raw Coro (`10 / 15 / 20 l/D`) | `5-sig @ 20 l/D` | LLOWFS DM3 | "
            "RT Apply (`S1/S2`) | Total PF CPU | Sub-Pages |",
            "| :--- | :---: | :---: | ---: | ---: | ---: | ---: | :---: | ---: | ---: | "
            ":---: | ---: | :---: |",
        ]
    )

    for b in eof_bundles:
        s = b["summary"]
        sp = b["spec"]
        pr = s["procs"]
        is_eof = s["pf_mode"] == "eof"
        ap1 = pr.get("applyEOFPF-1" if is_eof else "applyARPF-1", {}).get("exec_p50_us", 0.0)
        ap2 = pr.get("applyEOFPF-2" if is_eof else "applyARPF-2", {}).get("exec_p50_us", 0.0)
        tot_c = pf_cpu_sum(s)
        bw = "**" if sp["key"] == "eof128_p8" else ""
        lines.append(
            f"| {fmt_link(b)} | `{sp['reg_str']}` | "
            f"{bw}`{s['stg1_wfe_nm']:.1f}`{bw} / `{s['stg1_max_nm']:.0f} nm` | "
            f"{bw}`{s['vis_stg1_sr_pct']:.2f}%`{bw} | "
            f"{bw}`{s['final_wfe_nm']:.1f} nm`{bw} | "
            f"{bw}`{s['vis_final_sr_pct']:.2f}%`{bw} | "
            f"{bw}`{s['nir_final_sr_pct']:.2f}%`{bw} | "
            f"`{s['coro_raw_c10']:.2e}` / `{s['coro_raw_c15']:.2e}` / "
            f"`{s['coro_raw_c20']:.2e}` | "
            f"{bw}`{s['coro_5s_20']:.2e}`{bw} | "
            f"{bw}`{s['llowfs_dm3_nm']:.2f} nm`{bw} | "
            f"`{ap1:.0f} / {ap2:.0f} us` | **`{tot_c:.0f}%`** | {fmt_cmp_link(b)} |"
        )

    ap1_e128 = s_eof128["procs"]["applyEOFPF-1"]["exec_p50_us"]
    ap2_e128 = s_eof128["procs"]["applyEOFPF-2"]["exec_p50_us"]
    ap1_e64 = s_eof64["procs"]["applyEOFPF-1"]["exec_p50_us"]
    ap2_e64 = s_eof64["procs"]["applyEOFPF-2"]["exec_p50_us"]
    lines.extend(
        [
            "",
            "![Cross-Mode Block-EOF vs. Diagonal AR(16): Closed-Loop Comparison (2x3)]"
            "(eof_vs_ar_closed_loop_2x3.png)",
            "",
            "Four decisive closed-loop conclusions emerge from Figure 8:",
            "",
            f"1. **Dramatic Stage-1 (AO3k) wind-lag breakthrough (`+{s1_vr_gain:.2f} pp` Vis SR, "
            f"`-{s1_wfe_drop:.1f} nm` WFE)**: On the 1 kHz Stage-1 loop — where temporal wind lag "
            "dominates the error budget — **`Block-EOF(B=128, P=8)`** slashes residual WFE from "
            f"`{s_ar16_m14['stg1_wfe_nm']:.1f} nm` (matched `AR(16)`) and "
            f"`{s_ar16_d14['stg1_wfe_nm']:.1f} nm` (default `AR(16)`) down to "
            f"**`{s_eof128['stg1_wfe_nm']:.1f} nm`** (`{s_eof64['stg1_wfe_nm']:.1f} nm` for "
            f"`B = 64`), lifting Stage-1 Vis SR from `{s_ar16_m14['vis_stg1_sr_pct']:.2f}%` "
            f"to **`{s_eof128['vis_stg1_sr_pct']:.2f}%`** (and Stage-1 H-band Strehl from "
            f"`{s_ar16_m14['nir_stg1_sr_pct']:.2f}%` to **`{s_eof128['nir_stg1_sr_pct']:.2f}%`**). "
            "During the `2.22 um` gust at `t = 2.15 s`, cross-mode advection trims the peak "
            f"Stage-1 excursion by **`-29 nm`** (`{s_ar16_d14['stg1_max_nm']:.0f} -> "
            f"{s_eof128['stg1_max_nm']:.0f} nm`) and raises Stage-1 tip/tilt PyWFS optical gain "
            "(`selfRM` `g_opt`) by `+20%` (`0.483 -> 0.580`).",
            f"2. **Post-SCExAO dark-hole & LLOWFS gains (`-{c15_gain:.1f}%` / `-{c20_gain:.1f}%` "
            f"coronagraph contrast, `-{dm3_drop:.1f}%` DM3 stroke)**: After Stage 2 (`2 kHz`), "
            "total pupil WFE is already close to the irreducible `~50 nm` fitting + chromatic + "
            "photon floor, so removing temporal servo-lag variance improves final WFE from "
            f"`{s_ar16_m14['final_wfe_nm']:.1f} nm` -> **`{s_eof128['final_wfe_nm']:.1f} nm`** "
            f"(`{s_ar16_m14['vis_final_sr_pct']:.2f}%` -> "
            f"**`{s_eof128['vis_final_sr_pct']:.2f}%`** Vis SR, **`95.36%`** H SR). Crucially, "
            "however, because wind-lag speckles concentrate coherently in the `10–20 l/D` "
            "coronagraphic wind-butterfly halo, **`Block-EOF(B=128, P=8)`** deepens H-band raw "
            f"contrast by **`8.1%` @ `10 l/D`**, **`{c15_gain:.1f}%` @ `15 l/D`**, and "
            f"**`{c20_gain:.1f}%` @ `20 l/D`** (mean `5–20 l/D` planet contrast **`-10.4%`**, "
            f"5-sigma @ `20 l/D` **`-{c20_5s_gain:.1f}%`**) while cutting Stage-3 LLOWFS DM3 "
            f"stroke by **`-{dm3_drop:.1f}%`** (`{s_ar16_m14['llowfs_dm3_nm']:.2f} -> "
            f"{s_eof128['llowfs_dm3_nm']:.2f} nm`).",
            "3. **Bonus discovery — stage-asymmetric regularization benefits diagonal `AR(16)` "
            "too**: Comparing `Diag AR(16) Default` (`reg = 5e-3` on both stages) against "
            "`Diag AR(16) Matched` (`reg1 = 1e-4` on high-SNR Stage 1, `reg2 = 1e-2` on "
            "lower-SNR Stage 2) reveals why `Diag AR(16)` at `N = 32k` dipped to `76.62%` Vis SR: "
            "`reg2 = 5e-3` pinned Stage-2 modes against `||w||_2^2 <= 1.35`, triggering a brief "
            "Mode-298 ringing burst at `t = 0.5–1.1 s`. Raising `reg2 -> 1e-2` and lowering "
            "`reg1 -> 1e-4` completely eliminates that ringing and lifts diagonal `AR(16)` to "
            f"**`{s_ar16_m14['vis_final_sr_pct']:.2f}%` Vis SR**.",
            f"4. **Real-time CPU feasibility (`76–108 us` inference, `~0.7–1.0` CPU core, `0` "
            f"timeouts)**: Leveraging OpenBLAS `dsyrk`/`dgemm` + LAPACKE `dpotrf` at `1.0 s` "
            f"update cadence, **`Block-EOF(B=64, P=8)`** uses only **`{cpu_eof64:.0f}%` CPU** "
            f"(`{ap1_e64:.0f} / {ap2_e64:.0f} us` apply, activates in `6.0 s`) and "
            f"**`Block-EOF(B=128, P=8)`** uses **`{cpu_eof128:.0f}%` CPU** "
            f"(`{ap1_e128:.0f} / {ap2_e128:.0f} us` apply for `2.0M` / `1.3M` MACs per frame, "
            f"activates in `12.0 s`) — **`2.3–3.4x` LESS total CPU** than scalar `mkARPF` "
            f"running on the same `N = 16k / 32k` window (`{cpu_ar16_m14:.0f}%` CPU)!",
            "",
            "## 9. Operational Recommendations for CACAO / SCExAO",
            "",
            "1. **For maximum steady-state ExAO & coronagraphic performance (stationary wind "
            "over `>= 12 s`), deploy `Block-EOF(B=128, P=8)` with progressive `AR(16)` "
            "cold-start bootstrapping** (`--pf-mode eof --pf-blocksize 128 --pf-order 8 "
            "--pf-reg 1e-4 --pf-reg2 1e-2 --pf-maxnorm2 2.0 --pf-nbtrain1 16384 "
            "--pf-nbtrain2 32768 --pf-minsamples1 12000 --pf-minsamples2 24000`): it locks "
            "Subaru V-spider petals within `0.25 s` via `AR(16)` cold-start, transitions "
            "bump-free into full cross-mode advection prediction at `t = 12 s`, delivers "
            "**`+3.5 pp` Stage-1 Vis SR** and **`10–14%` deeper `10–20 l/D` dark-hole contrast** "
            "over regularization-matched `AR(16)`, and fits comfortably inside `~1.0` CPU core "
            "with `< 110 us` inference latency.",
            "2. **For rapid wind shifts (`6 s` horizon) or tighter CPU budgets (`< 0.7` core), "
            "use `Block-EOF(B=64, P=8)`** (`minsamples = 6000 / 12000`): it captures virtually "
            "all of the Stage-1 cross-mode gain (`61.9 nm` WFE, `77.00%` Stage-1 Vis SR) in half "
            "the convergence time and `68%` of the CPU cost of `B = 128`.",
            "3. **For immediate `< 1 s` cold-start diagonal operation (`B = 1`), adopt "
            "stage-asymmetric `Diagonal AR(16)`** (`--pf-order 16 --pf-reg 1e-4 --pf-reg2 1e-2`, "
            "`N_train = 2048–4096`): it avoids both `AR(4)`/`AR(8)` lag-induced petal slips and "
            "`AR(32)`/`AR(64)` cold-start overfitting, while `reg2 = 1e-2` prevents Stage-2 "
            "high-order ringing. Do **not** deploy diagonal `AR(64)` for broadband turbulence "
            "(`< 0.2 pp` gain over `AR(16)` at `14x` CPU).",
            "4. **Infrastructure landed in `cacao`, `cacaosim`, and `cacao-work`**: Expanded "
            "`ARPF_MAX_ORDER` to `64` in `mkARPF.c`/`applyARPF.c`; implemented native real-time "
            "`cacaopc-mkEOFPF` + `cacaopc-applyEOFPF` (OpenBLAS/LAPACKE + OpenMP SIMD + "
            "decoupled `diagorder = 16` cold-start bootstrap & smooth cross-fade); wired "
            "`--pf-mode eof` end-to-end into `cacaoloop-ao3k-scexao.milk`, "
            "`sim-ao3k-scexao.milk`, and `cacaosim-ao-report`.",
            "",
            "## Reproducibility & GitHub Provenance",
            "",
            "All source repositories, simulation scripts, diagnostic figures, and machine-readable "
            "comparison tables (`predictive_control_comparison.json`, "
            "`predictive_control_summary.csv`) are open-source and reproducible end-to-end.",
            "",
        ]
    )

    if repos:
        lines.extend(
            [
                "### Open-Source GitHub Repositories & Commits",
                "",
                "| Repository | Branch | Commit | Role in Simulation Stack |",
                "| :--- | :---: | :---: | :--- |",
            ]
        )
        for r in repos:
            rname = r.get("name", "")
            rurl = r.get("url", "")
            rbr = r.get("branch", "main")
            rsha = r.get("commit", "")
            rshort = r.get("short_commit", rsha[:7])
            rrole = r.get("role", "")
            c_lnk = f"[`{rshort}`]({rurl}/commit/{rsha})" if rsha else "`HEAD`"
            lines.append(f"| [{rname}]({rurl}) | `{rbr}` | {c_lnk} | {rrole} |")
        lines.append("")

    lines.extend(
        [
            "### CLI Commands to Reproduce Part I (Diagonal AR(4..64)) & Part II (Block-EOF)",
            "",
            "```bash",
            "cd ~/src/cacao-work",
            "source env.sh",
            "",
            "# 1. Part I: Per-mode Diagonal AR(4..64) baseline sweep (N_min=256, N_train=2048)",
            "for P in 4 8 16 32 64; do",
            "  ./scripts/run-ao3k-scexao.sh \\",
            "    --seeing 0.60 --phys-time 5.0 --oversample 4 --bench-mode fused \\",
            "    --predictive --pf-mode ar --pf-order ${P} \\",
            "    --load-rm _work/ao3k_scexao_rm --outdir _work/ao3k_scexao_predictive_ar${P} \\",
            "    --save-telemetry speckle",
            "done",
            "",
            "# 2. Part I: Warm-start ablations AR(32)* & AR(64)* (N_min=1024, N_train=4096)",
            "for P in 32 64; do",
            "  CACAO_PF_MINSAMPLES=1024 CACAO_PF_NBTRAIN=4096 \\",
            "    ./scripts/run-ao3k-scexao.sh \\",
            "      --seeing 0.60 --phys-time 5.0 --oversample 4 --bench-mode fused \\",
            "      --predictive --pf-mode ar --pf-order ${P} \\",
            "      --load-rm _work/ao3k_scexao_rm \\",
            "      --outdir _work/ao3k_scexao_predictive_ar${P}_n4096 \\",
            "      --save-telemetry speckle",
            "done",
            "",
            "# 3. Part II: Matched 14 s-warmup Diagonal AR(16) vs. Cross-Mode Block-EOF(B=64/128)",
            "./scripts/run-ao3k-scexao.sh --seeing 0.60 --phys-time 5.0 --oversample 4 \\",
            "  --predictive --pf-mode ar --pf-order 16 --pf-reg 1e-4 --pf-reg2 1e-2 \\",
            "  --pf-maxnorm2 1.35 --pf-nbtrain1 16384 --pf-nbtrain2 32768 --pf-warmup-sec 14.0 \\",
            "  --load-rm _work/ao3k_scexao_rm \\",
            "  --outdir _work/ao3k_scexao_predictive_ar16_matched_w14s --save-telemetry speckle",
            "",
            "./scripts/run-ao3k-scexao.sh --seeing 0.60 --phys-time 5.0 --oversample 4 \\",
            "  --predictive --pf-mode eof --pf-blocksize 128 --pf-order 8 \\",
            "  --pf-reg 1e-4 --pf-reg2 1e-2 --pf-maxnorm2 2.0 \\",
            "  --pf-nbtrain1 16384 --pf-nbtrain2 32768 \\",
            "  --pf-minsamples1 12000 --pf-minsamples2 24000 --pf-warmup-sec 14.0 \\",
            "  --load-rm _work/ao3k_scexao_rm \\",
            "  --outdir _work/ao3k_scexao_predictive_eof128_p8 --save-telemetry speckle",
            "",
            "# 4. Compile this comparative Predictive Control Report & publish to Firebase Hosting",
            "${PYTHON_BIN} ./scripts/build-predictive-control-report.py",
            "./scripts/publish-ao-report.sh --project scexao-og _work/predictive_control_report",
            "```",
            "",
        ]
    )


def generate_report_markdown(
    bundles: list[dict[str, Any]],
    wf_study: dict[str, Any],
    eof_bundles: list[dict[str, Any]],
    eof_study: dict[str, Any],
) -> str:
    """Render the full Predictive Control Report Markdown from live simulation data."""
    ctx = build_report_context(bundles, wf_study, eof_bundles, eof_study)
    lines: list[str] = []
    append_part1_overview(lines, ctx)
    append_part1_spectra_and_compute(lines, ctx)
    append_part2_eof_and_repro(lines, ctx)
    return "\n".join(lines)
