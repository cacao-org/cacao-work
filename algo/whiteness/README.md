# Phase 0b: Closed-Loop Residual Whiteness & Predictability Monitor

CPU-only offline validation on existing AO3k/SCExAO telemetry (`_work/ao3k_scexao_*`) and exact C implementation specification for CACAO (`modalCTRL_stats.c` bugfix, standalone `cacao-fpsexec-modalwhite`, and `mkEOFPF` out-of-sample logging).

- **Reference validator:** [validate_whiteness.py](file:///home/guyon/src/cacao-work/algo/whiteness/validate_whiteness.py)
- **Raw quantitative dump:** [whiteness_results.json](file:///home/guyon/src/cacao-work/algo/whiteness/whiteness_results.json)

---

## 1. Theory & Synthetic Null Calibration

For a closed-loop WFS modal residual $w_t = \phi_t + u_{t-\tau} + n_t$ with total fractional loop latency $\tau$ frames and integer ceiling $d = \lceil \tau \rceil$ (for all 8 runs here, $\tau \in [2.09, 2.82] \implies d = 3$):

1. **Optimal residual is `MA(d-1)`, not white noise:** innovations during $[t-\tau, t]$ stay correlated for $1 \le k < d$, then drop cleanly to zero at $k \ge d$:
   $$\operatorname{Cov}(w_t, w_{t-k}) = 0 \quad \text{and} \quad \operatorname{Cov}(w_t, u_{t-k}) = 0 \qquad \forall k \ge \lceil\tau\rceil.$$
2. **Per-mode Bartlett-corrected Ljung–Box score** ($K = 16$ lags $k \in [d, d+K-1]$):
   $$v_m = 1 + 2\sum_{j=1}^{d-1}\hat{\rho}_m(j)^2, \qquad \tilde{Q}_m = \frac{1}{K\,v_m}\sum_{k=d}^{d+K-1}\frac{N(N+2)}{N-k}\,\hat{\rho}_m(k)^2 \quad (\mathbb{E}[\tilde{Q}_m] = 1 \text{ under null}).$$
3. **Exact parameter-free cross-mode Bartlett whiteness $\tilde{Q}_{\text{xmode}}$** (by Isserlis' theorem, since $|k-l| < d$ and $|k+l| < d$ cannot both hold when $k \ge d$, lag-0..$(d-1)$ spatial covariance drops out identically):
   $$v_{ij} = 1 + 2\sum_{l=1}^{d-1}\hat{\rho}_i(l)\hat{\rho}_j(l), \qquad \tilde{Q}_{\text{xmode}}^{(\text{blk})} = \frac{1}{K\,|\mathcal{P}|}\sum_{k=d}^{d+K-1}\sum_{(i,j)\in\mathcal{P}}\frac{N(N+2)}{N-k}\frac{\hat{C}_{ij}(k)^2}{v_{ij}} \quad (\mathbb{E}[\tilde{Q}_{\text{xmode}}] = 1).$$
4. **Out-of-sample Recoverable WFE** (2-fold chronological split-half CV, lag $\ge d$ ridge predictor):
   $$\text{PRF}_m = 1 - \frac{\operatorname{Var}_{\text{oos}}(w_m - \hat{w}_m)}{\operatorname{Var}_{\text{oos}}(w_m)}, \qquad \Delta\text{WFE}_{\text{recov}} = \sqrt{\sum_m \max(\text{PRF}_m, 0)\,\sigma_{w,m}^2}.$$
5. **WFS–DM cross-correlation** $r_{wu,m}(k) = \operatorname{Cov}(w_m[t], u_m[t-k])/(\sigma_{w,m}\sigma_{u,m})$ at $k \ge d$. In CACAO's PSOL sign convention ($\text{OL}_t = \alpha w_t - u_{t-\tau}$, verified to `rel_res ~ 3.6e-8` across all runs), $u \approx -\phi$, so **$r_{wu}(d) < 0$ flags under-correction / lag / leak / ZPO ramp** and **$r_{wu}(d) > 0$ flags over-correction / optical-gain overshoot**.

### Synthetic Self-Test (`N = 5000, M = 128, d = 3`)

| Synthetic Process | Metric | Measured | Theoretical / Note |
|---|---|---:|---|
| White noise ($\sigma^2 = 100$) | $\tilde{Q}$ / $v_m$ | `0.982` / `1.001` | Exact `1.0` null |
| White noise ($\sigma^2 = 100$) | `modalCTRL_stats` 3-pt / 4-pt buggy / 4-pt fixed | `100.35` / **`70.24`** / `100.40` | Line 437 bug gives `3.5/5.0 = 0.70x` variance |
| Spatially correlated `MA(2)` ($a=0.98$, 0 noise) | $\rho(1..5)$ | `[0.666, 0.331, -0.004, -0.005, -0.004]` | Exact `2/3, 1/3, 0, 0, 0` cliff at $k=3$ |
| Spatially correlated `MA(2)` ($a=0.98$, 0 noise) | $\tilde{Q}_{\text{Bartlett}}$ vs naive Ljung–Box | **`1.003`** vs `2.114` | Naive test has `>2x` false-positive inflation |
| Spatially correlated `MA(2)` ($a=0.98$, 0 noise) | $\tilde{Q}_{\text{xmode}}$ (off-diag, strong lag-0 $L$) | **`0.993`** | Exact `1.0` even with correlated modes |
| Spatially correlated `MA(2)` ($a=0.98$, 0 noise) | Fixed 4-pt FD / total variance | **`0.200`** | Analytical $1/5$ — over-subtracts Brownian innovations |

---

## 2. Quantitative Results Across All 8 Telemetry Runs

All runs have $\tau \in [2.09, 2.82]$ frames $\implies d = \lceil\tau\rceil = 3$. Band definitions: `lo20` = modes `0..19`, `m20-127` = modes `20..127`, `B0` = modes `0..127`, `all` = full modal basis (`1024–1965` modes). `WFS`, `DM`, and $\Delta\text{WFE}_{\text{recov}}$ are quadrature modal RMS in **nm**.

### 2.1 Stage 1 (1000 Hz, AO3k)

| Run (Controller) | $N$ | $\hat{\tau}$ (fr) | WFS tot / B0 (nm) | $\|\rho\|_{B0}(1..6)$ | Cliff $\frac{d-1}{d}$ (B0 / m20–127) | $\rho_{B0}(d)$ | $\tilde{Q}_{B0}$ / $\tilde{Q}_{\text{lo20}}$ | $\tilde{Q}_{\text{xmode}}^{B0}$ (`xblk64` / `128`) | $\Delta\text{WFE}_{\text{recov}}$ diag P8 (all / B0) | $\Delta\text{WFE}$ xmode m512 (diag / B64) | $r_{wu,\text{lo20}}(d)$ / $Q_{wu,B0}$ | $W\|U$ recov (nm) | PF OL$\to$PF in-samp / OOS (nm) |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `lowfs_open` (Int) | 5k | 2.25 | 76.3 / 26.9 | `96,95,92,90,87,85`% | 1.03x / 1.06x | `+0.919` | 607 / 611 | 6.08 (4.47 / 3.01) | **38.8** (26.0%) / 25.0 | 29.0 / 28.9 | `-0.736` / 299 | 35.5 (21.9%) | — |
| `lowfs_closed` (Int) | 5k | 2.25 | 77.0 / 27.7 | `96,95,92,90,87,84`% | 1.03x / 1.06x | `+0.919` | 604 / 599 | 6.03 (4.36 / 2.94) | **39.5** (26.5%) / 25.7 | 29.7 / 29.6 | `-0.740` / 307 | 36.1 (22.1%) | — |
| `calib2wfs1dm` (AR8) | 5k | 2.40 | 66.9 / 16.6 | `90,86,80,78,75,73`% | 1.07x / 1.27x | `+0.775` | 513 / 379 | 5.79 (3.00 / 1.95) | **16.0** (5.8%) / 13.4 | 13.9 / 14.8 | `-0.414` / 90 | 12.7 (3.6%) | 61.4 / 68.5 |
| `tlm20s_ar16` (AR16) | 20k | 2.68 | 67.3 / 16.0 | `89,83,74,69,63,58`% | 1.12x / 1.24x | `+0.719` | 1083 / 989 | **19.83** (9.98 / 5.44) | **15.4** (5.3%) / 12.0 | 12.9 / **15.1** | `-0.415` / 346 | 11.7 (3.0%) | 62.5 / 69.5 |
| `eof128_p8` (EOF) | 5k | 2.40 | 62.4 / 9.9 | `74,61,44,39,36,36`% | 1.39x / 1.48x | `+0.432` | 235 / 298 | **3.88** (3.66 / 1.84) | **8.2** (1.7%) / 5.3 | 5.5 / 3.9 | `-0.391` / 77 | 6.9 (1.2%) | 54.4 / 64.2 |
| `eof64_p8` (EOF) | 5k | 2.28 | 62.5 / 9.0 | `65,46,24,22,18,21`% | **1.89x / 1.99x** | `+0.209` | **106 / 155** | **2.11** (2.19 / 1.60) | **6.7** (1.1%) / 3.3 | 3.5 / 2.1 | `-0.436` / 100 | 6.4 (1.1%) | 54.3 / 63.5 |
| `stg2unmod_eof128_p8` | 5k | 2.13 | 166.2 / 14.3 | `67,54,45,43,43,44`% | 1.19x / 1.23x | `+0.435` | 452 / 596 | 13.27 (13.14 / 2.56) | 23.3 (2.0%) / 8.9 | 13.3 / 5.3 | `-0.380` / 65 | 19.7 (1.4%) | 151.2 / 173.3 |
| `stg2unmod_mh8_p32` | 5k | 2.09 | 422.4 / 38.3 | `64,58,56,56,56,57`% | 1.03x / 1.04x | `+0.550` | 601 / 643 | **28.69** (29.09 / 2.92) | 30.4 (0.5%) / 26.0 | 28.3 / 21.3 | `-0.179` / 31 | **69.5** (2.7%) | **329.0 / 458.3** |

### 2.2 Stage 2 (2000 Hz, SCExAO PyWFS)

| Run (Controller) | $N$ | $\hat{\tau}$ (fr) | WFS tot / B0 (nm) | $\|\rho\|_{B0}(1..6)$ | Cliff $\frac{d-1}{d}$ (B0 / m20–127) | $\rho_{B0}(d)$ | $\tilde{Q}_{B0}$ / $\tilde{Q}_{\text{lo20}}$ | $\tilde{Q}_{\text{xmode}}^{B0}$ (`xblk64` / `128`) | $\Delta\text{WFE}_{\text{recov}}$ diag P8 (all / B0) | $\Delta\text{WFE}$ xmode m512 (diag / B64) | $r_{wu,\text{lo20}}(d)$ / $Q_{wu,B0}$ | $W\|U$ recov (nm) | PF OL$\to$PF in-samp / OOS (nm) |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `lowfs_open` (Int) | 10k | 2.29 | 43.4 / 6.5 | `70,64,50,45,37,34`% | 1.27x / 1.34x | `+0.487` | 348 / 361 | 6.91 (3.45 / 2.57) | **25.1** (33.6%) / 3.3 | 9.0 / 8.9 | `-0.537` / 337 | 24.5 (31.9%) | — |
| `lowfs_closed` (Int) | 10k | 2.29 | 45.1 / 9.3 | `86,83,77,76,73,72`% | 1.07x / 1.28x | `+0.742` | 1142 / 554 | 11.12 (6.56 / 4.53) | **26.9** (36.0%) / 6.6 | 11.1 / 10.7 | **`-0.872`** / 1090 | 24.5 (30.0%) | — |
| `calib2wfs1dm` (AR8) | 10k | 2.58 | 38.2 / 6.0 | `54,34,05,06,04,04`% | **6.99x / 13.74x** | `+0.013` | 12.1 / 22.8 | 2.30 (1.75 / 1.57) | 6.6 (3.0%) / 0.2 | 0.7 / 1.4 | `-0.088` / 19.9 | 6.3 (2.7%) | 35.5 / 39.2 |
| `tlm20s_ar16` (AR16) | 40k | 2.82 | 39.2 / 6.4 | `57,38,04,03,02,01`% | **8.39x / 12.28x** | `+0.039` | **8.5 / 11.2** | **6.19** (4.11 / 2.76) | 7.6 (3.8%) / **0.5** | 1.3 / **2.5** | `-0.025` / 4.85 | 7.4 (3.6%) | 37.9 / 40.4 |
| `eof128_p8` (EOF) | 10k | 2.58 | 36.5 / 6.0 | `54,35,05,06,07,07`% | **7.42x / 7.28x** | `+0.035` | 42.5 / 59.8 | **1.76** (1.73 / **1.20**) | **5.0** (1.9%) / 0.9 | 1.2 / **0.9** | **`+0.178`** / 41.3 | 5.6 (2.4%) | 32.5 / 37.8 |
| `eof64_p8` (EOF) | 10k | 2.32 | 37.3 / 6.3 | `49,22,15,06,06,03`% | 1.50x / 1.35x | **`-0.138`** | 40.0 / 61.4 | **1.42** (1.26 / **1.17**) | 5.6 (2.2%) / 1.4 | 2.5 / 1.6 | **`+0.199`** / 42.1 | 6.0 (2.6%) | 33.9 / **34.6** |
| `stg2unmod_eof128_p8` | 10k | 2.58 | 19.2 / 6.1 | `27,56,33,33,36,30`% | 1.68x / 2.87x | **`-0.259`** | **511 / 906** | 4.97 (3.48 / 1.63) | 3.6 (3.5%) / 3.0 | 3.0 / 2.7 | `+0.041` / 33.2 | 2.7 (2.0%) | 18.0 / 21.9 |
| `stg2unmod_mh8_p32` | 10k | 2.42 | 44.1 / 11.8 | `29,44,22,26,21,26`% | 1.96x / 3.86x | **`-0.105`** | 312 / 466 | 8.06 (7.23 / 3.18) | 5.6 (1.6%) / 4.5 | 4.8 / 4.1 | `-0.034` / 134.6 | 8.6 (3.8%) | **33.8 / 53.1** |

### 2.3 Key Diagnostic Findings Verified on Telemetry

1. **Textbook `MA(d-1)` latency cliff at $k = \lceil\tau\rceil = 3$:**
   - **Integrator** shows no cliff (`1.03x–1.34x`) and leaves `26–36%` of total WFS variance linearly predictable (`39 nm` Stage 1, `25–27 nm` Stage 2).
   - **AR(8)/AR(16) on Stage 2** produces a razor-sharp **`12–14x` cliff** right at $k = 3$: on `tlm20s_ar16` Stage 2, signed $\bar{\rho}_{B0}(1..12) = `[+0.570, +0.379, +0.039, +0.006, -0.020, +0.001, -0.004, +0.013, -0.010, 0.000, -0.007, +0.008]`$ — flat `< 0.02` out to lag 12.
2. **Cross-mode $\tilde{Q}_{\text{xmode}}$ exposes frozen-flow wind coupling missed by diagonal AR:**
   - On `tlm20s_ar16` Stage 2, per-mode AR(16) whitens individual modes (`B0 diag recov = 0.5 nm`, `0.5%`), so a per-mode monitor would declare Stage 2 whitened — yet **$\tilde{Q}_{\text{xmode}}^{B0} = 6.19$ (`max_z = 19.2`)** and cross-mode regression recovers `2.5 nm` (`3.2 nm` at $P=8$) on `m0..511` (vs `1.3 nm` diag). Switching to **Block-EOF** (`eof128_p8` / `eof64_p8`) drops $\tilde{Q}_{\text{xmode}}^{B0}$ to **`1.76` / `1.42`** (and on Stage 1 from **`19.83` $\to$ `3.88` / `2.11`**) and reduces `xblk128` to **`1.17–1.20`** (confirming `B = 128` captures virtually all cross-mode wind coupling).
3. **Zone-2 (`k >= floor(tau) + P`) and Stage-1 DC leak cleanly diagnosed:**
   - On Stage 1 `eof128_p8` / `eof64_p8`, `pf_mix = 0.90` + `maxdcgain = 0.995` leaves `~1%` DC leak on `455 nm` of low-order turbulence (`lo20 recov = 3.8 / 2.5 nm`, negative $r_{wu,\text{lo20}}(3) = -0.391 / -0.436$, while mid-order $r_{wu,m20\text{--}127}(3) \approx -0.05$). Furthermore, a slight lag bump at $k = 9..11$ (`-0.10` on Stage 2, `+0.24..+0.39` on Stage 1 — exactly at $\lfloor\tau\rfloor + P = 10$ for $P=8$, absent in `AR(16)`) and `diag_P16 > diag_P8` (`10.6` vs `8.2 nm` on Stg1) flag mild `P = 8` lookback truncation.
4. **Signed $\rho(d) < 0$ & alternating `-, +, -, +` catches Stage-2 unmodulated PyWFS ringing:**
   - `stg2unmod_eof128_p8` Stage 2 exhibits sustained period-2 Nyquist ringing: $\bar{\rho}_{B0}(1..12) = `[+0.052, +0.541, -0.259, +0.270, -0.298, +0.236, -0.294, +0.218, -0.300, +0.188, -0.320, +0.170]`$ (`Q_lo20 = 905.5`) — immediate diagnosis of optical-gain overshoot / loop under-damping.
   - `eof64_p8` Stage 2 shows mild over-correction: $\rho_{B0}(3) = -0.138$ paired with positive $r_{wu,B0}(3) = +0.193$ (opposite sign to Stage 1's under-correction).
5. **Massive `mh8_eof128_p32` overfitting hidden by `mkEOFPF` in-sample metrics:**
   - With $B = 128, P = 32$ ($D = 4096$ on $N = 16\text{k}/29\text{k}$), `mkEOFPF`'s in-sample `o_rms_pred` reports **`329.0 nm (+58.7%)`** (Stg1) and **`33.8 nm (+50.0%)`** (Stg2), whereas true live out-of-sample `OL - PF_delayed` is **`458.3 nm (+22.1%)`** (Stg1) and **`53.1 nm (-1.6% — worse than ZOH 52.7 nm!)`** (Stg2), matching `modalfilter.c`'s `mvalPFresrms` (`458.6` / `50.0 nm`).
6. **`ao3k_scexao_calib2wfs1dm` ZPO wind-up (`t = 4.85 s`) triggers a >10x alarm on Stage 2 despite flat WFS RMS:**

| Window (`calib2wfs1dm` Stage 2, 2 kHz) | $N$ | WFS tot / lo20 (nm) | DM tot (nm) | $\rho_{B0}(3)$ | $\rho_{\text{lo20}}(3)$ | $\tilde{Q}_{B0}$ / $\tilde{Q}_{\text{lo20}}$ | $\tilde{Q}_{\text{xmode}}^{B0}$ | $r_{wu,\text{lo20}}(3)$ (rms) | $Q_{wu,\text{lo20}}$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Pre-windup `2.0–4.0 s` | 4000 | 38.0 / 2.9 | 37.0 | `+0.000` | `+0.023` | 3.37 / 7.78 | 1.42 | `-0.014` (`0.031`) | `3.01` |
| Sliding `1.5–4.5 s` (0.5 s bins, $K=12$) | 1000 | 37.9 / 2.9 | 36.2 | `~0.00` | `-0.02..+0.06` | `~2.0` / `2.1–3.2` | `1.12–1.19` | `-0.04..+0.05` (`0.05`) | **`0.90–2.22`** |
| Pre-onset `4.0–4.5 s` | 1000 | 38.0 / 3.1 | 38.4 | `+0.003` | `+0.055` | 1.96 / 3.27 | 1.14 | `-0.037` (`0.065`) | `1.55` |
| **Wind-up `4.5–5.0 s`** (`t = 4.85 s`) | 1000 | **38.6** (+1.5%) / 3.4 | **63.3** | **`+0.108`** | **`+0.231`** (**4x**) | **10.05 / 9.37** | **`1.99`** | **`-0.219`** (`0.256`, **6x**) | **`12.77`** (**>8x**) |
| Late `4.0–5.0 s` | 2000 | 38.5 / 3.3 | 58.0 | `+0.072` | `+0.176` | 12.73 / 13.57 | `2.10` | `-0.208` (`0.249`) | **`18.58`** |

- Stage 1's own `modevalWFS` is partially blinded to its own `wfszpo` runaway (`66.6` $\to$ `66.3 nm`), whereas Stage 2 sees the physical sky aberration pushed by Stage 1's ZPO ramp. A `0.5–1.0 s` (`1000–2000` frame) buffer preserves the slow ramp without detrending it away (unlike a `0.2 s` window), lighting up $Q_{wu,\text{lo20}}$ **>10x** (`1.0` $\to$ `12.7`) while scalar WFS RMS shifts by only `0.6 nm`.

---

## 3. Exact C Implementation Plan (Apply After Session `95081576` Finishes)

### 3.1 Bugfix & Hardening in `cacao/AOloopControl/modalCTRL_stats.c`

| Location | Verified Bug / Defect | Exact Fix |
|---|---|---|
| **Line 437** | `tmpv3` reads `(sample + 1) * NBmode + mi` (duplicate of `tmpv2`), turning `[-0.5, 1.5, -1.5, 0.5]` into `[-0.5, 1.5, -1.0]`. Breaks linear/quadratic annihilation and reduces white-noise variance multiplier from `5.0` to `3.5` (`0.70x` variance / `0.837x` RMS — verified as `0.825–0.853x` across all 16 real telemetry cubes). | Change `(sample + 1)` to `(sample + 2)` (safe: loop ends at `sample < NBsample - 2`, max index `NBsample - 1`). Fix comment on line 424 to `// quadratic noise derivation`. |
| **Lines 470–471** | Divisor `5` on line 471 IS **algebraically exact** once line 437 is fixed: $(-0.5)^2 + 1.5^2 + (-1.5)^2 + 0.5^2 = 0.25 + 2.25 + 2.25 + 0.25 = \mathbf{5.0}$ (NOT `2.5`). However `(NBsample - 3) * 5` evaluates in `uint32_t` before promotion. | Change to `mvalWFS_mrms2[mi] /= (double)(NBsample - 2) * 1.5;` and `mvalWFS_mqrms2[mi] /= (double)(NBsample - 3) * 5.0;` with comment documenting `0.25 + 2.25 + 2.25 + 0.25 = 5.0`. |
| **Lines 495–506** | `mvalWFS_rms2[mi] -= mvalWFS_mqrms2[mi]` has no floor: on ringing/high-order modes (`56/1061` modes in `stg2unmod_eof128_p8` Stg2, `25/1062` in `mh8_p32` Stg2), `var_4pt > var_tot`, causing negative block variance and `sqrtf` $\to$ `NaN`. Also `block` (line 499) is unchecked. | Clamp `if (mvalWFS_rms2[mi] < 0.0) mvalWFS_rms2[mi] = 0.0;` (same for `mvalOL_rms2[mi]`); check `if (block >= 0 && block < (int32_t) mblksizemax)`. |
| **Line 232** | Stack OOB write when `NBblk == MAXBLK (10)`: `blki++` reaches `10` and writes `blkoffset[10]`. | Guard `if (blki < (uint32_t) MAXBLK) { blkoffset[blki] = blkoffset[blki - 1] + blksize[blki - 1]; }`. |
| **Lines 338, 382, 394, 445** | Raw `md->cnt1` used as double-buffer slice index. | Mask `slice = (int)(imgtbuff_*.md->cnt1 & 1ULL);` (matching `mkEOFPF.c:497`). |

### 3.2 Standalone Controller-Agnostic FPS Unit: `cacao-fpsexec-modalwhite`

- **Files:** Add `cacao/AOloopControl/modalwhite.c` + `extern const MILK_RUNNABLE runnable_AOloopControl_modalwhite;` in `cacao/AOloopControl/AOloopControl.h` + `EXPORT_FPSEXEC(cacao, "modalwhite", runnable_AOloopControl_modalwhite);` (`AOloopControl/CMakeLists.txt` auto-globs `*.c` and generates `cacao-fpsexec-modalwhite`; link BLAS via `// MILK_CMAKE_REQUEST_BLAS` or fallback loop).
- **Inputs (FPS params):**
  - `.AOloopindex` (`uint64`, default `0`)
  - `.inWFSbuff` (`streamname`, `FPFLAG_DEFAULT_TRIGGER_STREAM`, default `aol0_modevalWFS_buff`, double-buffered `[NBmode x Nslice x 2]`)
  - `.inDMbuff` (`streamname`, optional, default `aol0_modevalDM_buff`)
  - `.latency_fr` (`float32`, `WRITERUN`, default `2.5f`; $d = \max(1, \lceil\tau - 10^{-4}\rceil)$)
  - `.NBwin` (`uint32`, default `2048` frames — ring buffer over `0.5–2.0 s`, preserving slow ZPO/drift ramps)
  - `.K_lags` (`uint32`, default `16`, max `64`), `.P_recov` (`uint32`, default `8`), `.P_ctrl` (`uint32`, default `8`), `.blocksize` (`uint32`, default `128`), `.reglambda` (`float32`, default `0.01f`)
- **Output SHM streams (`float32`):**
  - `aol<N>_mwhite_Q` `[NBmode x 1]`: per-mode Bartlett $\tilde{Q}_m$ ($k \in [d, d+K-1]$)
  - `aol<N>_mwhite_rhod` `[NBmode x 1]`: signed $\hat{\rho}_m(d)$ ($>0$ lag/drift, $<0$ ringing/over-prediction)
  - `aol<N>_mwhite_prf` `[NBmode x 1]` & `aol<N>_mwhite_recov` `[NBmode x 1]`: split-half OOS $\text{PRF}_m$ and $\sqrt{\max(\text{PRF}_m, 0)}\,\sigma_{w,m}$ [$\mu\text{m}$]
  - `aol<N>_mwhite_rwud` `[NBmode x 1]` & `aol<N>_mwhite_Qwu` `[NBmode x 1]`: signed $r_{wu,m}(d)$ and Bartlett $Q_{wu,m}$ (zeroed if `inDMbuff` unavailable)
  - `aol<N>_mwhite_acf` `[Kmax x NBmode]`: full $\hat{\rho}_m(0..K_{\max}-1)$ for TUI `MA(d-1)` cliff display
- **Output FPS scalars (`.out.*`):**
  - `wfs_rms_nm`, `recov_wfe_nm`, `recov_var_pct`, `b0_recov_wfe_nm`, `Q_vw_all`, `Q_vw_b0`, `Q_lo20`, `Q_beyond_b0`, `Q_xmode_b0`, `Q_xblk_b01`, `rho_d_b0`, `cliff_ratio_b0`, `rwu_d_lo20`, `Q_wu_lo20`, `wu_recov_wfe_nm`, `alert_flags` (`uint32` bitmask: `0x1` lag/under-pred, `0x2` ringing/over-pred $\rho(d) < -0.08$, `0x4` cross-mode $\tilde{Q}_{\text{xmode}} > 2.5$, `0x8` WFS–DM/ZPO ramp $Q_{wu,\text{lo20}} > 6.0 \land |r_{wu,\text{lo20}}(d)| > 0.15$).
- **Complexity & Budget (`NBwin = 2048, NBmode = 2000, Kmax = 32, B = 128, P = 8`):**
  - Contiguous SIMD lag ACF + WFS–DM XCF (`k = 0..32`, no FFT dep): $2.7 \times 10^8$ FLOPs $\approx 0.5\text{ ms}$ (4 threads).
  - Split-half per-mode $8 \times 8$ ridge Cholesky (`diag` $\Delta\text{WFE}_{\text{recov}}$): $7.4 \times 10^7$ FLOPs $\approx 0.4\text{ ms}$.
  - Exact Isserlis/Bartlett $\tilde{Q}_{\text{xmode}}$ on Block 0 ($8$ lags $\times$ `cblas_sgemm` $128 \times 2048 \times 128$): $5.4 \times 10^8$ FLOPs $\approx 1.2\text{ ms}$.
  - **Total:** `~2–3 ms` per `0.5–2.0 s` buffer (`< 0.3%` CPU, `< 35 MB` RSS, **zero RT loop overhead**).

### 3.3 Out-of-Sample Logging Hook in `AOloopControl_PredictiveControl_mkEOFPF.c`

- **Add FPS outputs (lines 60–66 & 112–124):**
  - `.out.rms_zoh_oos`, `.out.rms_pred_oos`, `.out.var_red_oos_pct`, `.out.overfit_ratio` (`rms_pred_oos / rms_pred`), `.out.oos_rho_d_b0` (lag-$d$ autocorrelation of Block-0 OOS prediction residual).
- **Exact placement (lines 553–566, right after appending `n_add` frames to `hist_fm`, BEFORE `if (do_eof)` / `bufs_since_ef` skip):**
  - Whenever `o_n_updates > 0` and `n_add > lat_i + 1`: define `new_start = n_valid - n_add` and `P_eff = (o_eof_active == 2) ? P : P_diag`.
  - Evaluate the **existing published filter** `imgoutPF.im->array.F` strictly out-of-sample on all targets `tk + lat_i >= new_start` and `tk + lat_i + 1 < n_valid` (`n_oos ~ n_add - 1` frames that the current filter has never seen):
    - In `o_eof_active == 2`, reuse `X_blk`/`Y_blk` with one `cblas_dgemm` per block (`(n_oos x D) * (D x b)`) against the unpacked current filter rows — `< 5 ms` total across all blocks, updating on every incoming buffer slice even when `updateperiod > 1`.
    - In `o_eof_active == 1`, evaluate the `P_diag` diagonal taps per mode in `< 0.2 ms`.
  - Immediately exposes severe overfitting (e.g., `mh8_eof128_p32` Stage 2 `overfit_ratio = 1.57`, `var_red_oos_pct = -1.6%` vs in-sample `+50.0%`) and provides the self-supervised trigger for future adaptive regularization / forgetting in `mkEOFPF`.
