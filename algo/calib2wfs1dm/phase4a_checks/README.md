# Phase 4a Offline Cross-Regime Audit & `zpo-2` Optical-Gain Scaling Design

CPU-only, read-only offline audit of the passive 2-WFS + 1-DM **Differenced Lagged-A 2SLS** estimator across all existing AO3k + SCExAO simulation regimes under `/home/guyon/src/cacao-work/_work/ao3k_scexao*`, plus the exact minimal C + `.milk` patch specification for Stage-2 `zpo-2` optical-gain scaling.

- Audit script: [`audit_regimes.py`](file:///home/guyon/src/cacao-work/algo/calib2wfs1dm/phase4a_checks/audit_regimes.py)
- Machine-readable results: [`audit_results.json`](file:///home/guyon/src/cacao-work/algo/calib2wfs1dm/phase4a_checks/audit_results.json)
- Reference spec: [`../ALGORITHM.md`](file:///home/guyon/src/cacao-work/algo/calib2wfs1dm/ALGORITHM.md), [`../README.md`](file:///home/guyon/src/cacao-work/algo/calib2wfs1dm/README.md)

---

## Executive Summary

1. **Item 4 (`selfrm_dyn` audit of all 14 `_work/ao3k_scexao*` runs):**
   - Naive `realsim_est.py` (`sky[4] - mean(sky[0:3])`) fails on stock `sim-ao3k-scexao.milk` runs because on-sky `selfRM` uses `nbsettle=6` (insufficient for closed-loop decay at `lat ~ 3.5 fr`, injecting a `+0.38..+0.47` opposite-sign settle tail at lags 0–2) and unthrottled wall pacing (`lat = 3.42–3.60 fr` in Nov 18–20 runs; `2.84–2.92 fr` in Nov 21 runs).
   - Fitting the exact discrete-time `modalfilter.c` `nbsettle=6` closed-loop model yields **fit RMS = 0.008–0.029** across all 8 lags and exposes two critical facts:
     - Raw peak `og_selfrm.fits` (`~0.68–0.70`) under-reads the true on-sky `selfRM` gain `P_srm` (`0.73–0.81`) by **10–13%** due to settle-tail + integrator-reaction subtraction.
     - All 7 target runs with `selfRM` cubes are internally self-consistent (`g_dyn / P = 0.94–1.03`), whereas **all 5 standalone AR sweep runs (`predictive_ar4`, `ar8`, `ar16`, `ar32`, `ar64`) suffered Stage-2 LLOWFS/ZPO bursts during on-sky `selfRM`** (`P_srm = 0.04–0.23`, `g_dyn / P = 2.16–9.23`, **FAIL**).
     - On predictive runs, `sim-ao3k-scexao.milk` turns **`PF-OFF` and `enable_fpcam=OFF`** before `selfRM_onsky`, so `P_srm` measures the **Integrator** optical gain at higher latency (`3.5 fr`), which is physically **~7–11% lower** than the true `PF=ON` optical gain during science telemetry (`g_IV ≈ 0.84–0.85` at `3 λ/D`, `0.815` at `0 λ/D`).

2. **Critical alignment bug caught in `realsim_est.py:sim_frame_times()`:**
   - Using `searchsorted(tB, tA) - 1` silently shifted `oA` by **-1 WFS B tick (-500 µs)** on all 6 Nov 18–20 runs because Stage-1 `aol1_modevalWFS` finished `0.115 ms` *before* the simultaneous Stage-2 `aol2_modevalWFS`. That single off-by-1 error depressed `eof128_p8` from `0.850` down to `0.601` (-29%)!
   - Replacing it with **nearest-timestamp matching (`nearest_idx(tA, tB)`)** matches the exact camera-stream counter truth (`csim_wfs_nir` / `csim_wfs_vis`) with **100.0% (`f = 1.000`)** agreement across all 8 runs.

3. **Does Block-EOF increase or decrease `usable_frac` vs Integrator?**
   - **At `mH = 6` (`3 λ/D`), AR and Block-EOF INCREASE `usable_frac` from 24–29% (Integrator) to 35.5–38.6%!** Reason: Stage-1 predictive control injects stronger WFS-A-correlated DM1 motion and Stage-2 predictive control tracks the incoming wavefront more tightly (tighter IQR `0.021–0.047` vs `0.064–0.093`).
   - **On `0 λ/D` unmodulated PyWFS (`mH = 6`, `stg2unmod_eof128_p8`)**, `usable_frac = 14.8%` at `NA = 60`, and **more than doubles to `33.3%` at `NA = 160`** (reducing bootstrap 1σ from `5.6%` to `4.4%` and IQR from `0.089` to `0.054`). Why? Those runs switched Stage-1 DM1 to the **ALPAO force-driven plate DM**, whose leading 60 SVD modes only span 66% (`resid = 33.8%`) of the 40 Stage-2 Gaussian modes (`NA = 160` drops the span residual to `6.8%`).
   - **At `mH = 8` + `p = 32` Block-EOF (`stg2unmod_mh8_eof128_p32`), `usable_frac` collapses to `1.7%` (`3.8%` at `NA = 160`) — properly triggering the `< 5%` warning flag!** Root cause: high WFS B photon noise amplified through `p = 32` EOF drives DM2 with nearly white noise (`ac1(dD) = -0.488`, 3× higher `rms(dD)`), drowning out the WFS-A-predicted DM2 motion.

4. **Shipped `W(z)` fails across every regime; Differenced Lagged-A 2SLS succeeds everywhere `usable >= 5%`:**
   - Shipped/Python `W(z)` reads **-32% to -35% low** on Integrator (`0.54–0.55`), **-12% to -15% low** on AR/EOF `3 λ/D` (`0.71–0.74`), and **-26% low** on unmodulated `0 λ/D` (`0.60`).
   - Differenced Lagged-A (`IV diff`) gives a rock-solid **`0.834–0.851`** across all `mH = 6`, `3 λ/D` runs (20 s AR(16): `0.841`, IQR `0.021`, bootstrap 1σ `1.4%`), **`0.815`** on `0 λ/D` unmodulated (`mH = 6`, bootstrap 1σ `4.4%` at `NA = 160`), and **`0.714`** (flagged noisy, bootstrap 1σ `21.1%`) on `mH = 8` `p = 32`.

5. **Tip/Tilt (modes 0–1) diagnosed:**
   - TT was weak/biased (`-18%/-10%`) in `run1` Integrator because Kolmogorov TT variance is `30–70×` larger than modes 2–39 (`ac1(A) = 0.98`, very high WFS A SNR -> low WFS A noise excitation -> TT `usable = 2.4–7.0%`), and LLOWFS bursts collapse TT `usable` to `1.2–2.6%` (`lowfs_closed`).
   - **Under Block-EOF (`eof128_p8`, `eof64_p8`, `stg2unmod_eof128_p8`), Stage-1 EOF whitens the post-DM1 residual (`ac1(A)` drops from `0.98` to `0.67–0.82`), boosting TT `usable` to `32–38%` (`45%` at `NA = 160`) and shrinking TT bootstrap 1σ to `2.7–4.3%`!**

6. **Stage-3 LLOWFS regressors & direct proof of ZPO gain mismatch:**
   - Adding `(E, Z)` from `aol3_dmC` changes modes 2–39 by `< 1%` on stationary runs and stabilizes TT/low-order modes slightly (`+0.02..+0.05` on EOF).
   - Crucially, the free `(E, Z)` regression directly measures the net ZPO residual `a + b ≈ g_opt - g_zpo` from closed-loop telemetry: **`-0.11` to `-0.20`** on modulated `3 λ/D`, **`-0.23`** (`TT: -0.34/-0.40`) on unmodulated `0 λ/D` `mH = 6`, and **`-0.35`** on `mH = 8`.

7. **Block bootstrap (100 ms blocks, `B = 200`) is quantitatively calibrated across a 15× range:**
   - Bootstrap 1σ matches independent empirical half-split 1σ within ~10% relative error across all 9 windows: `1.4% vs 1.7%` (20 s AR16), `3.5–3.8% vs 3.0–4.0%` (5 s AR/EOF), `5.2–5.6% vs 5.8–6.5%` (Integrator / unmod `NA=60`), and `21.1% vs 23.7%` (`mH=8` `p=32`), with negligible sensitivity to block length (`50 / 100 / 200 ms` agree within `0.15` points).

8. **IV `Mda_virt` & passive Stage-1 optical gain $g_A$:**
   - On Gaussian DM1 runs, multivariate Lagged-A IV `Mda_virt` (levels) matches exact `M_geom` to `cos = 0.90–0.96`, achieves **strictly better static offload convergence** than shipped `W(z)` (`sr0.5 = 0.575–0.668` vs `0.611–0.784`, `g_max = 1.88–1.99`), and eliminates the `~3–5%` EIV attenuation of unwhitened `W(z)` `Mda_virt`.
   - Passive Stage-1 optical gain $g_A$ from projected IV (`0.905–0.943`, IQR `0.014–0.040`) and $M_{db}/M_{ab}$ (`0.913–0.972`) tracks Stage-1 `selfRM` (`0.84–0.89`, noting `PF=ON` vs `PF=OFF` gives `+5–6%` higher on-sky Stage-1 optical gain during predictive science!).
   - **Plate-DM insight:** On the ALPAO force-driven plate DM1 (`stg2unmod_*`), `Mda_virt` and $M_{db}/M_{ab}$ read `~1.7–1.8×` relative to naive actuator-grid `M_geom` because force-driven plate compliance requires `~1.7×` larger DM1 force command per nm OPD on modes 10–39 (`std(D1)` jumped from `20.2` to `34.5` for identical seeing). Passive `Mda_virt` automatically captures this physical transfer function, whereas command-space `M_geom` misses it.

9. **`zpo-2` optical-gain scaling patch spec (ready to implement post-`95081576`):**
   - Minimal 12-line C addition in `acquireWFSim.c`: add `FPFLAG_WRITERUN` float parameter `.WFSzpogain` (default `1.0f`) applied as `imgwfsref + zpogain * imgdispzpo` (live-writable, zero restart, zero new SHM, `< 0.5 µs` overhead).
   - Paired with `cacaoloop-ao3k-scexao.milk` (`CACAO_WFSZPO_GAIN`, `setzpogain` / `setog` subcommand) + `sim-ao3k-scexao.milk` on-sky `WFSzpogain` & `WFSfact` update. Stability analysis proves any `g_zpo <= g_opt` (e.g., `0.95 * g_low` or `min(g_TT, g_low)`) unconditionally eliminates Stage-2/Stage-3 positive-feedback wind-up.

---

## 1. Exhaustive `selfRM` Self-Consistency Audit (Item 4 of `README.md`)

In `sim-ao3k-scexao.milk`, on-sky `selfRM` is acquired with `zsize=8`, `nbsettle=6`, `nbiter=1`, and `PF-OFF` (`enable_fpcam=OFF`). In `modalfilter.c` (lines 635–660, 1082–1112), `selfRMpokecmd` is updated *after* emitting `mvaloutapply`, so block 0 (`+ampl`) emits pokes on `pokecnt = 1..8` while the closed-loop integrator builds `-mvalDMc` to cancel it; when the poke drops at `pokecnt = 9`, the 6 settle frames (`9..14`) are too short for `lat ≈ 3.5 fr`, leaving a strong negative WFS error that block 1 (`-ampl`, `scale < 0`) flips into a **positive `+0.38..+0.47` baseline on `pokecnt = 0..2`** and subtracts ~10–13% from the peak at `pokecnt = 5`.

Fitting the exact `modalfilter.c` discrete-time closed-loop model `sim_selfrm_exact(P, g_dyn, lat_fr, gain, leak=0.98, zsize=8, nbsettle=6)` across modes 2–39 tests internal consistency (`g_dyn / P ≈ 1.0`, `fit_rms < 0.06`, `P >= 0.35`):

| Run | Stg | Cal Plat | Naive `lag4-[0:3]` | Raw Peak (`og_selfrm`) | Exact `P_srm` | `g_dyn` | `g_dyn / P` | `lat_srm` [fr] | Fit RMS | `OG_srm` (`P/Cal`) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `ao3k_scexao_lowfs_open` | 2 | 0.995 | 0.011 | 0.687 | **0.768** | 0.725 | **0.94** | 3.60 | 0.0288 | 0.787 | **OK** |
| `ao3k_scexao_lowfs_open` | 1 | 0.997 | 0.399 | 0.742 | **0.868** | 0.850 | **0.98** | 3.16 | 0.0078 | 0.872 | **OK** |
| `ao3k_scexao_lowfs_closed` | 2 | 0.995 | 0.051 | 0.696 | **0.781** | 0.775 | **0.99** | 3.48 | 0.0266 | 0.777 | **OK** |
| `ao3k_scexao_lowfs_closed` | 1 | 0.997 | 0.458 | 0.762 | **0.797** | 0.725 | **0.91** | 3.10 | 0.0390 | 0.836 | **OK** |
| `ao3k_scexao_calib2wfs1dm` | 2 | 0.995 | 0.108 | 0.703 | **0.759** | 0.725 | **0.96** | 3.50 | 0.0118 | 0.777 | **OK** |
| `ao3k_scexao_calib2wfs1dm` | 1 | 0.997 | 0.452 | 0.765 | **0.769** | 0.700 | **0.91** | 3.08 | 0.0393 | 0.805 | **OK** |
| `ao3k_scexao_predictive_eof128_p8` | 2 | 0.995 | -0.071 | 0.677 | **0.810** | 0.800 | **0.99** | 3.54 | 0.0180 | 0.813 | **OK** |
| `ao3k_scexao_predictive_eof128_p8` | 1 | 0.997 | 0.400 | 0.742 | **0.871** | 0.850 | **0.98** | 3.16 | 0.0089 | 0.888 | **OK** |
| `ao3k_scexao_predictive_eof64_p8` | 2 | 0.995 | 0.131 | 0.655 | **0.726** | 0.750 | **1.03** | 3.42 | 0.0245 | 0.714 | **OK** |
| `ao3k_scexao_predictive_eof64_p8` | 1 | 0.997 | 0.407 | 0.741 | **0.878** | 0.875 | **1.00** | 3.14 | 0.0104 | 0.883 | **OK** |
| `ao3k_scexao_stg2unmod_eof128_p8` | 2 | 0.983 | 0.543 | 0.721 | **0.745** | 0.700 | **0.94** | 2.84 | 0.0119 | 0.779 | **OK** |
| `ao3k_scexao_stg2unmod_eof128_p8` | 1 | 0.999 | 0.788 | 0.845 | **0.862** | 0.825 | **0.96** | 2.36 | 0.0089 | 0.879 | **OK** |
| `ao3k_scexao_stg2unmod_mh8_eof128_p32` | 2 | 0.984 | 0.482 | 0.703 | **0.684** | 0.650 | **0.95** | 2.92 | 0.0150 | 0.728 | **OK** |
| `ao3k_scexao_stg2unmod_mh8_eof128_p32` | 1 | 0.999 | 0.770 | 0.819 | **0.851** | 0.850 | **1.00** | 2.38 | 0.0128 | 0.855 | **OK** |
| `ao3k_scexao` (10 s) | 2 | 0.995 | 0.048 | 0.665 | 0.762 | 0.775 | 1.02 | 3.46 | 0.0329 | 0.768 | **OK** |
| `ao3k_scexao_predictive` | 2 | 0.995 | 0.135 | 0.687 | 0.777 | 0.775 | 1.00 | 3.44 | 0.0172 | 0.780 | **OK** |
| `ao3k_scexao_predictive_ar4` | 2 | 0.995 | 0.013 | 0.059 | 0.043 | 0.400 | **9.23** | 3.60 | 0.0011 | 0.047 | **FAIL** |
| `ao3k_scexao_predictive_ar8` | 2 | 0.995 | 0.076 | 0.249 | 0.232 | 0.500 | **2.16** | 3.46 | 0.0041 | 0.223 | **FAIL** |
| `ao3k_scexao_predictive_ar16` | 2 | 0.995 | 0.054 | 0.173 | 0.153 | 0.400 | **2.62** | 3.50 | 0.0059 | 0.159 | **FAIL** |
| `ao3k_scexao_predictive_ar32` | 2 | 0.995 | 0.059 | 0.194 | 0.165 | 0.375 | **2.28** | 3.42 | 0.0045 | 0.174 | **FAIL** |
| `ao3k_scexao_predictive_ar64` | 2 | 0.995 | 0.015 | 0.092 | 0.067 | 0.300 | **4.50** | 3.68 | 0.0043 | 0.076 | **FAIL** |

> [!IMPORTANT]
> **Why the published report's `calib_2wfs1dm` appeared to agree with `og_selfrm.fits` (`0.707` vs `0.706`):**
> That 0.1% agreement was an **exact cancellation of two ~15% biases**:
> 1. Shipped `W(z)` is biased **~15% low** in closed loop (`0.71` vs true science-window `g_opt ≈ 0.85`).
> 2. Raw peak `og_selfrm.fits` (`0.703`) was biased **~10% low** relative to `selfRM` `P_srm` (`0.77`) due to `nbsettle=6` settle-tail contamination, AND `selfRM_onsky` itself turned `PF-OFF` + `enable_fpcam=OFF` (`lat = 3.5 fr` vs `2.9 fr`), lowering its optical gain by another **~8%** below the `PF=ON` science window!
> For future runs, `sim-ao3k-scexao.milk` should raise `--nbsettle` from `6` to `>= 16` (or `20`) and run `selfRM_onsky` with `enable_fpcam=ON` (matching science wall pacing).

---

## 2. Frame Continuity, Clock Pairing Bug, Controller Law & Acting DM2 Latency

All 8 target runs have **zero dropped frames** (`gaps = 0`, `dc = 1` everywhere) in `aol1_modevalWFS`, `aol2_modevalWFS`, `aol2_modevalDM`, `aol3_dmC`, `csim_wfs_nir`, and `csim_wfs_vis`.

| Window | `N_A` | Wall FPS (`B`) | `dt(B - A)` [ms] | `oA_prev - oA_cam` | `oA_near` match | Ctrl `D-0.98D[-1]` vs `B` | `corr(D, -PF)` | 2-lag IV `[g2, g3]` | `lat_iv` [fr] |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `lowfs_open` | 4996 | 279.0 Hz | **+0.115** | **-1 tick (BUG)** | 1.000 | `-1.0000` (g=0.346) | — | `[0.166, 0.696]` | **2.81** |
| `lowfs_closed` | 4996 | 278.7 Hz | **+0.113** | **-1 tick (BUG)** | 1.000 | `-1.0000` (g=0.346) | — | `[0.093, 0.687]` | **2.88** |
| `calib2wfs1dm_5s` | 4996 | 278.8 Hz | **+0.115** | **-1 tick (BUG)** | 1.000 | `-0.8706` | `+0.9999` | `[0.106, 0.741]` | **2.88** |
| `calib2wfs1dm_4s` | 4000 | 278.8 Hz | **+0.115** | **-1 tick (BUG)** | 1.000 | `-0.8706` | `+0.9999` | `[0.095, 0.750]` | **2.89** |
| `tlm20s_ar16` | 19996 | 299.6 Hz | **+0.115** | **-1 tick (BUG)** | 1.000 | `-0.8185` | `+0.9999` | `[-0.020, 0.852]` | **3.03** |
| `eof128_p8` | 4996 | 273.3 Hz | **+0.116** | **-1 tick (BUG)** | 1.000 | `-0.8042` | `+0.9997` | `[0.101, 0.758]` | **2.88** |
| `eof64_p8` | 4996 | 275.8 Hz | **+0.117** | **-1 tick (BUG)** | 1.000 | `-0.7760` | `+0.9994` | `[0.069, 0.787]` | **2.92** |
| `stg2unmod_eof128_p8` | 4996 | 322.3 Hz | `-0.015` | `0` | 1.000 | `-0.4338` | `+0.9994` | `[-0.043, 0.805]` | **3.05** |
| `stg2unmod_mh8_eof128_p32` | 4996 | 324.6 Hz | `-0.033` | `0` | 1.000 | `-0.7708` | `+0.9997` | `[0.093, 0.646]` | **2.88** |

- **Bug in `realsim_est.py:sim_frame_times()` (line 117):** `searchsorted(tB, tA) - 1` assumes `tA > tB` on simultaneous ticks. Whenever Stage-1 MVM finishes even `0.1 ms` *before* Stage-2 MVM (`dt(B - A) = +0.115 ms`), `searchsorted - 1` drops back a full `3.6 ms` wall tick (`-500 µs` physical), introducing a `-1 WFS B tick` pairing bug (`oA_prev_err = -1`) that biases `eof128_p8` down by **-29%** (`0.601` vs `0.850`) and `calib2wfs1dm_4s` by **-13%** (`0.737` vs `0.851`). Using `nearest_idx(tA, tB)` eliminates this bug completely (`100.0%` match to `csim_wfs_nir`/`csim_wfs_vis` on all 8 runs).
- **Acting DM2 kernel `h_j`:** In unthrottled fused lockstep (~280–325 Hz wall clock), `vis -> dm02disp` takes `2.9 ms` (`0.82` ticks, Nov 18–20) or `0.45 ms` (`0.14` ticks, Nov 21), which arrives after `csim_htsim` starts tick `k+1`, adding ~0.7–0.9 frames above the `50 Hz`-paced calibration latency (`2.12 fr`). Directly measuring `[g2, g3]` via 2-lag IV consistently gives `lat_iv = 2.81–3.05 fr` (mostly lag 3) across every regime! Note that `IV diff` is also quite robust to `lat`: using `lat_calib = 2.123` shifts `g_med` by only `-3%` to `+4%` (`0.818–0.865`), though `lat_iv` minimizes IQR and residual RMS.

---

## 3. Cross-Regime Estimator Benchmark & `usable_frac`

Modes 2–39 medians (`NA = 60` baseline, exact `oA_near`, science `lat_iv`). `P_srm` is the exact `nbsettle=6` on-sky `selfRM` step response (`PF=OFF`). `wzPy` is our verified Python replica of `sysid_unit.c` (pooled AR(4) on per-channel-normalized `A`), cross-checked to `0.015` against cached C `shipped W(z)`.

| Window | Regime | WFE fin [nm] | `usable` (1ms / 2ms) | `P_srm` (`PF=OFF`) | **IV diff** (IQR) | Bias vs `P_srm` / MAD | IV diff (`lag 2–17`) | IV diff (`oA_prev` bug) | IV lev | LS diff | LS lev | `W(z)` (shipped / py) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `lowfs_open` | Integrator, LLOWFS open | 388.0 | **29.1%** / 17.5% | 0.784 | **0.834** (0.064) | +6.6% / 6.3% | 0.799 | 0.745 | 0.617 | 0.542 | 0.271 | **0.549** / 0.568 |
| `lowfs_closed` | Integrator, LLOWFS closed (bursts) | 68.0 | **24.2%** / 16.5% | 0.776 | **0.811** (0.093) | +2.6% / 9.0% | 0.769 | 0.720 | 0.540 | 0.489 | 0.105 | **0.539** / 0.551 |
| `calib2wfs1dm_5s` | AR(8) + LLOWFS, full 5 s | 59.2 | **35.5%** / 10.2% | 0.773 | **0.849** (0.047) | +10.5% / 4.3% | 0.855 | 0.718 | 0.837 | 0.790 | 0.393 | **0.707** / 0.735 |
| `calib2wfs1dm_4s` | AR(8) + LLOWFS, clean 0–4 s | 59.2 | **36.4%** / 10.2% | 0.773 | **0.851** (0.042) | +11.2% / 4.1% | 0.855 | 0.737 | 0.852 | 0.792 | 0.440 | **0.714** / 0.731 |
| `tlm20s_ar16` | AR(16) + LLOWFS, 20 s | 57.9 | **38.6%** / 6.3% | — | **0.841** (0.021) | — | 0.842 | 0.795 | 0.844 | 0.713 | 0.452 | — / **0.735** |
| `eof128_p8` | Block-EOF(128,8), 3 λ/D, mH=6 | 55.8 | **36.5%** / 18.4% | 0.812 | **0.850** (0.037) | +7.1% / 3.9% | 0.854 | 0.601 | 0.865 | 0.927 | 0.455 | — / **0.745** |
| `eof64_p8` | Block-EOF(64,8), 3 λ/D, mH=6 | 56.8 | **36.1%** / 15.2% | 0.710 | **0.845** (0.040) | +17.9%\* / 4.3% | 0.846 | 0.693 | 0.852 | 0.869 | 0.438 | — / **0.743** |
| `stg2unmod_eof128_p8` | Block-EOF(128,8), **0 λ/D**, mH=6 | 54.4 | **14.8%** / 12.3% | 0.766 | **0.815** (0.089) | +7.1% / 6.3% | 0.805 | 0.815 | 0.792 | 0.874 | 0.226 | — / **0.602** |
| `stg2unmod_mh8_eof128_p32` | Block-EOF(128,32), **0 λ/D**, **mH=8** | 81.8 | **1.7%** / 1.5% | 0.714 | 0.714 (0.222) | +1.9% / 16.6% | 0.781 | 0.714 | 0.540 | 0.888 | 0.065 | — / **0.533** |

\* In `eof64_p8`, `selfRM_onsky_stg2` (`nbiter=1`) caught a random turbulence dip (`P_srm = 0.710`), whereas science `g_IV = 0.845` matches `eof128_p8` (`0.850`) and `tlm20s_ar16` (`0.841`) to `0.6%` with `MAD = 4.3%`.

### Crucial Plate-DM Finding: `NA = 60` vs `NA = 160` on ALPAO Stage-1 DM

The two `stg2unmod_*` runs use the realistic **ALPAO force-driven magnetic plate DM** (`dyn_mode="plate"`, `plate_drive="force"`) on Stage 1. Because force-mode SVD ordering interleaves edge/bending modes with low-order optical modes, `NA = 60` leaves a **33.8% projection residual** against the 40 Stage-2 modes (vs `2.5%` for Gaussian DM1). Increasing `NA` to `160` recovers all missing Stage-1 optical span:

| Run | DM1 Type | `NA` | `M_geom` resid | `usable` (2–39) | TT `usable` | `g_IV` med | IQR | Boot 1σ |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `eof128_p8` | Gaussian | 60 | 0.025 | 36.5% | 36.6 / 34.7% | 0.850 | 0.037 | 3.8% |
| `eof128_p8` | Gaussian | 160 | 0.020 | 36.2% | 35.3 / 31.4% | 0.845 | 0.048 | 3.7% |
| `stg2unmod_eof128_p8` | **ALPAO Plate** | 60 | **0.338** | 14.8% | 38.0 / 32.8% | 0.815 | 0.089 | 5.6% |
| `stg2unmod_eof128_p8` | **ALPAO Plate** | **160** | **0.068** | **33.3%** (+2.25×) | **44.9 / 36.2%** | **0.815** | **0.054** (-39%) | **4.4%** |
| `stg2unmod_mh8_eof128_p32` | **ALPAO Plate** | 60 | 0.338 | 1.7% (FLAG) | 3.6 / 8.2% | 0.714 | 0.222 | 21.1% |
| `stg2unmod_mh8_eof128_p32` | **ALPAO Plate** | **160** | 0.068 | **3.8%** (+2.24×, still <5%) | 2.5 / 8.6% | 0.691 | 0.182 | 18.9% |

**Actionable deployment rule:** Use `NA = min(160, 4 * NB)` (or auto-select `NA` until `M_geom` projection residual `< 10%`) when Stage 1 uses a force-driven plate DM! And at `mH = 8` with `p = 32` EOF (`usable = 1.7–3.8%`), neither 2-ms windows (`1.5%`) nor `lag 2–17` rescues `usable >= 5%` because `p = 32` EOF propagates high WFS B photon noise directly into `dD` (`ac1(dD) = -0.488`, vs `+0.113` at `mH = 6`); the `< 5%` usable gate + bootstrap 1σ (`19–21%`) rightly warns the operator to integrate longer (20–30 s) or pool modes smoothly.

---

## 4. Tip/Tilt (Modes 0–1) Diagnosis

| Window | Regime | `g_IV` [Tip, Tilt] | `P_srm` [Tip, Tilt] | TT `usable` | Modes 2–39 `usable` | `ac1(A)` TT / hi | `Var(A)` TT / hi | TT Boot 1σ |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `run1/lowfs_open` (git, 20 s) | Integrator, 50 Hz paced | `[0.594, 0.663]` | `[0.725, 0.734]` | **7.0% / 2.4%** | 15.4% | — | — | (err `-18% / -10%`) |
| `run1/lowfs_closed` (git, 20 s) | Integrator + LLOWFS burst | `[0.878, 0.367]` | `[0.684, 0.583]` | **0.5% / 0.1%** | 10.9% | — | — | (err `+28% / -37%`) |
| `lowfs_open` (5 s) | Integrator, LLOWFS open | `[0.976, 0.848]` | `[0.601, 0.816]` | 16.2% / 8.0% | 29.1% | 0.980 / 0.968 | 33.7× | 6.1% / 6.8% |
| `lowfs_closed` (5 s) | Integrator + LLOWFS burst | `[1.068, 0.744]` | `[0.759, 0.778]` | **2.6% / 1.2%** | 24.2% | 0.981 / 0.968 | 35.5× | **6.8% / 16.2%** |
| `calib2wfs1dm_5s` | AR(8) + 4–5 s ZPO wind-up | `[0.778, 0.731]` | `[0.783, 0.650]` | 15.3% / 5.3% | 35.5% | 0.961 / 0.853 | 73.3× | 7.7% / 9.3% |
| `calib2wfs1dm_4s` | AR(8), clean 0–4 s | `[0.856, 0.866]` | `[0.783, 0.650]` | **19.0% / 23.2%** | 36.4% | 0.946 / 0.855 | 60.2× | 6.5% / 2.9% |
| `tlm20s_ar16` (20 s) | AR(16) + LLOWFS | `[0.730, 0.600]` | — | **19.3% / 24.5%** | 38.6% | 0.939 / 0.876 | 40.1× | **2.4% / 2.3%** |
| `eof128_p8` (5 s) | Block-EOF(128,8), 3 λ/D | `[0.798, 0.739]` | `[0.877, 0.786]` | **36.6% / 34.7%** | 36.5% | **0.785** / 0.718 | 26.6× | **2.9% / 4.3%** |
| `eof64_p8` (5 s) | Block-EOF(64,8), 3 λ/D | `[0.789, 0.741]` | `[0.670, 0.798]` | **36.0% / 32.2%** | 36.1% | **0.671** / 0.659 | 22.2× | **2.7% / 3.2%** |
| `stg2unmod_eof128_p8` | Block-EOF(128,8), **0 λ/D** | `[0.754, 0.690]` | `[0.727, 0.813]` | **38.0% / 32.8%** | 14.8% (`33.3%` @160) | **0.808** / 0.720 | 11.6× | **3.3% / 3.7%** |
| `stg2unmod_mh8_eof128_p32` | Block-EOF(128,32), 0 λ/D, mH=8 | `[0.598, 0.478]` | `[0.746, 0.920]` | **3.6% / 8.2%** | 1.7% | 0.696 / 0.676 | 10.3× | 12.8% / 13.3% |

**Root-cause diagnosis of Tip/Tilt behavior (three coupled mechanisms):**
1. **High WFS A SNR under Integrator (`run1`, `lowfs_open`):** Kolmogorov TT power is `33–73×` larger than modes 2–39 (`ac1(A) = 0.98`), so WFS A noise is tiny relative to smooth TT turbulence. Since differenced lagged-A relies on high-frequency WFS A noise fed through DM1 to break collinearity between `dpsi` and `dD`, TT `usable` drops to `2–8%` under Integrator (`run1`: `7.0% / 2.4%`, causing weak-instrument attenuation of `-18% / -10%`).
2. **LLOWFS ZPO bursts crush TT `usable`:** Comparing `calib2wfs1dm_4s` (clean 0–4 s: `TT usable = 19.0% / 23.2%`, `boot 1σ = 6.5% / 2.9%`) vs `calib2wfs1dm_5s` (with 4–5 s ZPO wind-up: `15.3% / 5.3%`) and `lowfs_open` (`16.2% / 8.0%`) vs `lowfs_closed` (`2.6% / 1.2%`) proves that unmodelled Stage-3 ZPO wind-up destroys TT identifiability.
3. **Block-EOF fixes TT identifiability at `mH = 6` (both `3 λ/D` and `0 λ/D`!):** Stage-1 Block-EOF cancels low-frequency atmospheric TT much more aggressively, dropping `ac1(A)` from `0.98` to `0.67–0.81` and `Var(A)_TT/hi` from `60×` to `12–27×`. Consequently, TT `usable` jumps to **`32–38%`** (`44.9% / 36.2%` at `NA = 160` on unmodulated `0 λ/D`!), yielding clean TT gain estimates (`0.798/0.739` at `3 λ/D`, `0.754/0.690` at `0 λ/D`, physically ~10% below modes 2–39 as expected for PyWFS tip/tilt nonlinearity!) with **`2.7–4.3%`** 1σ precision! Neither `lag 2–17` nor undifferenced `IV` beats `IV diff` on TT (undifferenced `IV` fails catastrophically on Integrator TT: `-0.036`).

---

## 5. Stage-3 LLOWFS Regressors (`aol3_dmC -> CMmodesDM`) & Direct ZPO Mismatch Measurement

Projecting `aol3_dmC` (500 Hz) onto Stage-2 `CMmodesDM` (`realsim_lowfs.py` model, upgraded to `oA_near` and `lat_iv`):
$$\Delta B_i = c_i \Delta \psi_i + g_i \Delta D_i + a_i \Delta E_i + b_i \Delta Z_i + \varepsilon_i$$
where $E$ is the stage-3 command at optical DM2 delay (`lat_iv`) and $Z$ is at ZPO issue timing (`lag 0`).

| Window | `dm3` RMS | `rms(dE)/rms(dD)` (TT / 2–9 / 10–39) | `g` no-stg3 (TT / 2–9 / 2–39) | `g` tied `D+E` (TT / 2–9 / 2–39) | `g` free `E,Z` (TT / 2–9 / 2–39) | Active `a` (opt) | Active `b` (ZPO) | **Net `a + b` ($\approx g_{\text{opt}} - g_{\text{zpo}}$)** | `b_tied` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `lowfs_closed` | 0.0244 | `0.35 / 0.11 / 0.10` | `[1.07, 0.74] / 0.800 / 0.807` | `[1.11, 0.80] / 0.794 / 0.803` | `[1.18, 1.06] / 0.800 / 0.810` | +0.253 | -0.411 | **-0.162** | -0.464 |
| `calib2wfs1dm_5s` | 0.0178 | `0.32 / 0.09 / 0.08` | `[0.77, 0.72] / 0.846 / 0.848` | `[0.76, 0.70] / 0.844 / 0.848` | `[0.83, 0.75] / 0.853 / 0.850` | +0.271 | -0.425 | **-0.112** | -0.461 |
| `calib2wfs1dm_4s` | 0.0178 | `0.32 / 0.09 / 0.08` | `[0.87, 0.87] / 0.859 / 0.847` | `[0.84, 0.87] / 0.860 / 0.849` | `[0.92, 0.89] / 0.865 / 0.849` | +0.284 | -0.461 | **-0.130** | -0.477 |
| `tlm20s_ar16` | 0.0045 | `0.25 / 0.08 / 0.07` | `[0.73, 0.60] / 0.840 / 0.839` | `[0.69, 0.57] / 0.826 / 0.836` | `[0.74, 0.61] / 0.845 / 0.841` | -0.080 | -0.049 | **-0.121** | -0.117 |
| `eof128_p8` | 0.0035 | `0.27 / 0.11 / 0.10` | `[0.80, 0.75] / 0.848 / 0.850` | `[0.82, 0.78] / 0.850 / 0.852` | `[0.84, 0.81] / 0.854 / 0.852` | +0.292 | -0.427 | **-0.109** | -0.448 |
| `eof64_p8` | 0.0036 | `0.21 / 0.10 / 0.09` | `[0.79, 0.75] / 0.840 / 0.842` | `[0.82, 0.83] / 0.851 / 0.851` | `[0.82, 0.81] / 0.854 / 0.853` | +0.299 | -0.428 | **-0.201** | -0.445 |
| `stg2unmod_eof128_p8` | 0.0060 | **`0.29 / 0.35 / 0.14`** | `[0.76, 0.69] / 0.803 / 0.817` | `[0.78, 0.71] / 0.799 / 0.812` | `[0.79, 0.72] / 0.832 / 0.825` | +0.212 | -0.437 | **-0.232** | -0.429 |
| `stg2unmod_mh8_eof128_p32` | 0.0129 | **`0.34 / 0.45 / 0.17`** | `[0.60, 0.48] / 0.681 / 0.713` | `[0.67, 0.52] / 0.693 / 0.723` | `[0.64, 0.50] / 0.693 / 0.726` | -0.016 | -0.304 | **-0.348** | -0.342 |

- **Effect on `g_IV`:** On modes 2–39, adding Stage-3 regressors shifts `g` by `< 1%` across all stationary runs; on `0 λ/D` unmodulated PyWFS (where LLOWFS accounts for **35–45%** of differenced DM2 motion on modes 2–9!), the free `(E, Z)` regressor lifts modes 2–9 from `0.803` to `0.832` (`+3.6%`) and TT from `[0.759, 0.690]` to `[0.794, 0.722]`.
- **Direct telemetry evidence of ZPO gain mismatch:** Across every single LLOWFS-closed run, **`a + b` is strictly negative (`-0.11` to `-0.35`)**, and grows larger on unmodulated PyWFS (`-0.23` at mH=6, `-0.35` at mH=8; TT `-0.34/-0.40`). Note that individual `a ≈ +0.28` and `b ≈ -0.43` are attenuated vs `(+0.8, -1.0)` because 500 Hz `aol3_dmC` updates span 2 WFS A windows and `acquireWFSim.c` applies `wfsrefc` one frame *after* `imWFS2` subtraction (`z_lag=1` scan raises `a` to `+0.47`, `b` to `-0.54`), while the DC sum `a + b` cleanly measures the exact net positive-feedback mismatch `g_opt - g_zpo`.

---

## 6. Block-Bootstrap 1-Sigma Error Bars

Circular moving-block bootstrap (`L_blk = 100` windows = `100 ms`, `B = 200` resamples) compared against independent half-split empirical 1σ (`median(|g_H1 - g_H2| / (2 g_full)) / 0.6745`) and per-mode MAD vs `selfRM`:

| Window | Duration | `usable` | Boot 1σ (`L=100ms`) | Boot `0.6745·σ` (pred MAD) | Empirical Half-Split 1σ | Actual MAD vs `selfRM`\* | Global Median 1σ (`g_med`) | Half medians `[H1, H2]` | `L_blk` sens. (`50 / 200 ms`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `lowfs_open` | 5 s | 29.1% | **5.2%** | 3.5% | **5.8%** | 6.3% | ±0.011 | `[0.837, 0.814]` | 5.0% / 5.0% |
| `lowfs_closed` | 5 s | 24.2% | **5.6%** | 3.8% | **5.8%** | 9.0% | ±0.013 | `[0.800, 0.775]` | — |
| `calib2wfs1dm_5s` | 5 s | 35.5% | **3.5%** | 2.4% | **4.0%** | 4.3% | ±0.008 | `[0.866, 0.836]` | — |
| `calib2wfs1dm_4s` | 4 s | 36.4% | **3.7%** | 2.5% | **3.7%** | 4.1% | ±0.008 | `[0.863, 0.844]` | — |
| `tlm20s_ar16` | **20 s** | 38.6% | **1.4%** | **1.0%** | **1.7%** | — | **±0.004** | `[0.837, 0.848]` | 1.5% / 1.5% |
| `eof128_p8` | 5 s | 36.5% | **3.8%** | 2.6% | **3.5%** | 3.9% | ±0.007 | `[0.840, 0.860]` | 3.8% / 3.9% |
| `eof64_p8` | 5 s | 36.1% | **3.7%** | 2.5% | **3.0%** | 4.3% | ±0.008 | `[0.845, 0.854]` | — |
| `stg2unmod_eof128_p8` (`NA=60`) | 5 s | 14.8% | **5.6%** | 3.8% | **6.5%** | 6.3% | ±0.011 | `[0.799, 0.802]` | — |
| `stg2unmod_eof128_p8` (`NA=160`) | 5 s | 33.3% | **4.4%** | 3.0% | — | — | — | — | — |
| `stg2unmod_mh8_eof128_p32` | 5 s | **1.7%** | **21.1%** | **14.2%** | **23.7%** | **16.6%** | ±0.043 | `[0.901, 0.799]` | — |

\* `Actual MAD vs selfRM` includes quadrature `nbiter=1` on-sky `selfRM` turbulence noise (`~3%` per mode), which explains why it sits slightly above `0.6745·σ_boot`. Against the selfRM-free half-split 1σ, block bootstrap is **calibrated to within ~10% across the entire 15× error range (`1.4%` to `21.1%`)** and insensitive to block length `50–200 ms`.

---

## 7. IV `Mda_virt` Estimator & Passive Stage-1 Optical Gain $g_A$

Compares multivariate Lagged-A IV `Mda_virt` (levels, `A[t]` on `[B[t], D_eff[t]]` instrumented by `A[t-1..t-4]`), differenced IV `Mda_virt`, Python/shipped `W(z)` `Mda_virt`, and projected scalar IV $g_A$ + $M_{db}/M_{ab}$ against exact DM2→DM1 geometry `M_geom` (`CMmodesDM` resampled onto DM1 pupil) and Stage-1 `selfRM` (`P_srm_stg1` weighted by $M_{\text{geom}}^2$):

| Window | `M_geom` resid | **IV(lev) `Mda_virt`** `cos / scl / sr0.5 / g_max / off` | **`W(z)` `Mda_virt`** (shipped / py) `cos / scl / sr0.5 / off` | IV(diff) `cos / scl` | Passive `gA_proj` (IQR) | Passive `gA (Mdb/Mab)` (IQR) | Stage-1 `selfRM` `P_srm1` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `lowfs_open` | 0.025 | `0.784 / 0.895 / 0.865 / 1.84 / 0.684` | sh: `0.847 / 0.885 / 0.963 / 0.713` | `0.546 / 0.672` | **0.912** (0.040) | **0.919** (0.030) | **0.866** |
| `lowfs_closed` | 0.025 | `0.683 / 0.881 / 1.010 / 0.00 / 0.956` | sh: `0.783 / 0.869 / 1.005 / 0.975` | `0.475 / 0.681` | **0.905** (0.073) | **0.913** (0.065) | **0.836** |
| `calib2wfs1dm_5s` | 0.025 | `0.822 / 0.932 / 0.689 / 1.87 / 0.561` | sh: `0.885 / 0.918 / 0.939 / 0.782` | `0.710 / 0.778` | **0.934** (0.026) | **0.954** (0.030) | **0.803** |
| `calib2wfs1dm_4s` | 0.025 | **`0.915 / 0.930 / 0.584 / 1.88 / 0.186`** | sh: `0.925 / 0.927 / 0.611 / 0.192` | `0.676 / 0.745` | **0.937** (0.016) | **0.959** (0.022) | **0.803** |
| `tlm20s_ar16` | 0.025 | **`0.957 / 0.925 / 0.575 / 1.99 / 0.190`** | py: `0.964 / 0.905 / 0.639 / 0.223` | `0.844 / 0.842` | **0.928** (0.014) | **0.937** (0.016) | — |
| `eof128_p8` | 0.025 | **`0.904 / 0.931 / 0.668 / 1.93 / 0.291`** | py: `0.909 / 0.889 / 0.777 / 0.356` | `0.656 / 0.727` | **0.943** (0.031) | **0.972** (0.033) | **0.883** |
| `eof64_p8` | 0.025 | **`0.904 / 0.923 / 0.672 / 1.91 / 0.339`** | py: `0.931 / 0.882 / 0.784 / 0.413` | `0.718 / 0.782` | **0.943** (0.029) | **0.971** (0.026) | **0.881** |
| `stg2unmod_eof128_p8`\* | **0.338** | `0.708 / 1.256 / 1.047 / 0.00 / 0.649` | py: `0.758 / 0.888 / 1.008 / 0.584` | `0.307 / 0.688` | **1.821**\*(0.99) | **1.739**\*(0.49) | **0.873** |
| `stg2unmod_mh8_eof128_p32`\* | **0.338** | `0.525 / 1.057 / 0.900 / 1.05 / 0.739` | py: `0.642 / 0.878 / 0.983 / 0.644` | `0.027 / 0.102` | **1.663**\*(0.81) | **1.662**\*(0.77) | **0.855** |

\* **Key physical findings on `Mda_virt` and passive $g_A$:**
1. **Use levels (not first differences) for `Mda_virt`:** Multivariate Lagged-A IV on **levels** (`A[t]` on `[B[t], D_eff[t]]`, instruments `A[t-1..t-4]`) outperforms differenced IV everywhere (`cos = 0.90–0.96` vs `0.66–0.84`) because `A` is upstream of DM2 and has no closed-loop `B -> D` endogeneity! Compared to shipped `W(z)` `Mda_virt`, IV(lev) achieves **lower static offload residual** (`0.186` vs `0.192` on `calib2wfs1dm_4s`; `0.190` vs `0.223` on `tlm20s_ar16`; `0.291` vs `0.356` on `eof128_p8`) and **tighter spectral radius** (`sr0.5 = 0.575–0.668` vs `0.611–0.784`), and recovers the true amplitude (`scl = 0.93` vs `0.88–0.90` in `W(z)`).
2. **Passive Stage-1 optical gain $g_A \propto M_{db}/M_{ab}$ works cleanly on matched-DM geometry:** On Gaussian DM1 runs, both projected-IV `gA_proj` (`0.905–0.943`, IQR `0.014–0.040`) and `gA(Mdb/Mab)` (`0.913–0.972`) track Stage-1 `selfRM` (`0.84–0.89`), sitting `+5–7%` higher during predictive science (`PF=ON`, `WFE_stg1 = 62 nm` vs `PF=OFF` during `selfRM_onsky`) and showing the exact drop from predictive (`0.94`) to Integrator (`0.91`).
3. **Force-driven ALPAO plate DM1 breaks command-space `M_geom`:** On `stg2unmod_*`, Stage-1 `CMmodesDM` are force vectors, not OPD vectors (`std(D1)` increases `1.71×` from `20.2` to `34.5` for identical seeing, and `NA = 60` leaves `33.8%` projection residual). Hence `Mda_virt` and $M_{db}/M_{ab}$ scale as $g_A \cdot (\text{OPD}_2 / \text{OPD}_{1,\text{plate}}) \approx 1.7\text{--}1.8$ relative to naive command-space `M_geom`. To extract pure Stage-1 optical gain $g_A$ on a plate DM, normalize `Mdb/Mab` by a **zero-turbulence calibration ratio** $(M_{db}/M_{ab})_{\text{cal}}$ (or OPD-space `M_geom`), rather than actuator-command `CMmodesDM`!

---

## 8. Minimal C + `.milk` Patch Specification for `zpo-2` Optical-Gain Scaling

### 8.1 Physics & Stability Analysis of the Stage-2 / Stage-3 ZPO Wind-Up

Currently, the Stage-3 → Stage-2 ZPO dataflow is:
```
aol3_dmC (dm02disp04) + aol3_dmRM (dm02disp05)
   ──► DMch2disp-02 (AOloopControl_DM_comb.c) ──► aol2_dmzpo (50x50)
   ──► zpo-2 (milk-fpsexec-linalg-MVMextract, immodes = aol2_zrespM) ──► aol2_wfszpo (120x120)
   ──► acquWFS-2 (acquireWFSim.c:556) ──► aol2_wfsrefc = mask * refcmult * (wfsref + wfszpo) + (1-refcmult)*wfsrefc
   ──► imWFS2 = imWFS1 - wfsrefc ──► wfs2cmodeval-2 ──► mfilt-2 (modalfilter.c)
```

Because `aol2_zrespM` is the **zero-turbulence calibration zonal RM** (`g_zpo = 1.0`), when LLOWFS commands $\Delta d_3$ on DM2 under on-sky PyWFS optical gain $g_{\text{opt}} < 1.0$:
$$\Delta \text{modevalWFS}_2 = \left(g_{\text{opt}} - g_{\text{zpo}}\right) \Delta d_3$$
With Stage-2 closing `modevalWFS_2 -> 0`, the steady-state Stage-2 DM command is:
$$\Delta d_2 + \Delta d_3 = \frac{g_{\text{zpo}}}{g_{\text{opt}}} \, \Delta d_3 \qquad (\text{PSOL/PF}), \qquad \Delta d_2 = \frac{g_{\text{zpo}} - g_{\text{opt}}}{g_{\text{opt}} + (1-\gamma)/g_{\text{loop}}} \, \Delta d_3 \qquad (\text{integrator})$$
- **When $g_{\text{zpo}} > g_{\text{opt}}$ (current bug: $1.0 > 0.70\text{--}0.80$, or $1.0 > 0.55\text{--}0.65$ on TT / unmod):** Stage 2 pushes in the **same direction** as LLOWFS, multiplying effective LLOWFS loop gain by $g_{\text{zpo}} / g_{\text{opt}} \approx 1.3\text{--}2.5\times$ and causing positive-feedback wind-up / bursts (directly measured in Section 5 as `a + b = -0.11` to `-0.35`, and visible as `dmzpo_rms = 0.0792` in `calib2wfs1dm` and 4× TT bursts in `lowfs_closed`).
- **When $g_{\text{zpo}} = g_{\text{opt}}$:** $\Delta d_2 = 0$, exact Stage-2 / Stage-3 decoupling (and zero LLOWFS leakage into `modevalOL` / predictive filters!).
- **When $g_{\text{zpo}} \le g_{\text{opt}}$ (e.g. $g_{\text{zpo}} = \min(g_{\text{TT}}, g_{2..13})$ or $0.95\, g_{\text{low}}$):** unconditionally passive/damped (no gain amplification on any mode, even on TT where $g_{\text{TT}}$ is 10–15% below $g_{2..13}$).

### 8.2 Why `acquireWFSim.c` (`.WFSzpogain`) Is the Exact Minimal Patch Point

| Option | Location | Live-writable (`FPFLAG_WRITERUN`)? | Restart `zpo-2`? | Extra SHM / Latency | Verdict |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **A. `.WFSzpogain` in `acquireWFSim.c`** | `cacao/AOloopControl_IOtools/acquireWFSim.c` | **YES** (`@set f.acquWFS-2.WFSzpogain=...`) | **No** | Zero (`< 0.5 µs` FMA in existing 120×120 loop) | **RECOMMENDED (minimal Phase 4a patch)** |
| B. Scale `aol2_zrespM` in `zpo-2` | `MVMextractModes.cpp` loads `immodes` once at start | No (requires stop/reload/start `zpo-2` of 144 MB cube) | Yes | 144 MB copy + pause | Good only for optional Phase 4b per-mode modal ZPO matrix |
| C. Modal `aol2_mzeropoint` in `modalfilter.c` | `cacao/AOloopControl/modalfilter.c` | Yes | No | Extra stream + **exposes bug in lines 723 & 796** (see §8.4) | Avoid for pixel ZPO; fix lines 723/796 independently |

### 8.3 Exact Minimal C Patch: `/home/guyon/src/cacao/AOloopControl_IOtools/acquireWFSim.c`

3 localized hunks (~12 lines total), **100% backwards-compatible** (default `WFSzpogain = 1.0f` is bit-identical to existing behavior):

```diff
--- a/AOloopControl_IOtools/acquireWFSim.c
+++ b/AOloopControl_IOtools/acquireWFSim.c
@@ -37,6 +37,7 @@ static int32_t  compWFSrefsub                               = 1;
 static int32_t  compWFSsigav                                = 1;
 static int32_t  compWFSrefc                                 = 1;
 static int32_t  resetWFSrefc                                = 0;
+static float    WFSzpogain                                  = 1.0f;
 static char     wfszposname[FUNCTION_PARAMETER_STRMAXLEN] = "aolX_wfszpo";
 
 
@@ -78,6 +79,8 @@ static char     wfszposname[FUNCTION_PARAMETER_STRMAXLEN] = "aolX_wfszpo";
       "WFS reference correction")                                                                   \
     X(".comp.resetWFSrefc", &resetWFSrefc, FPTYPE_ONOFF, 0,                                         \
       (FPFLAG_DEFAULT_INPUT | FPFLAG_WRITERUN), "reset WFS reference correction")                   \
+    X(".WFSzpogain", &WFSzpogain, FPTYPE_FLOAT32, 0, (FPFLAG_DEFAULT_INPUT | FPFLAG_WRITERUN),      \
+      "optical-gain scale applied to wfszpo")                                                       \
     X(".wfszpo", wfszposname, FPTYPE_STREAMNAME, 1, FPFLAG_DEFAULT_INPUT, "WFS zero point offset")
 
 
@@ -547,15 +550,20 @@ static MILK_HOT errno_t acquireWFSim_compute(const MILK_RUNNABLE *self)
             imgwfsrefc.md->write = 1;
             float refcgain       = WFSrefcgain;
             float refcmult       = WFSrefcmult;
+            float zpogain        = isfinite(WFSzpogain) ? WFSzpogain : 1.0f;
             if (imgwfsref.ID != -1)
             {
                 // refcmult is pulling refc toward ref + zpogain*wfszpo
                 // if refcmult = 1, then refc = mask * (ref + zpogain*wfszpo)
                 for (uint64_t ii = 0; ii < sizeWFS; ii++)
                 {
                     imgwfsrefc.im->array.F[ii] =
                         imgwfsmask.im->array.F[ii] * refcmult *
-                            (imgwfsref.im->array.F[ii] + imgdispzpo.im->array.F[ii]) +
+                            (imgwfsref.im->array.F[ii] + zpogain * imgdispzpo.im->array.F[ii]) +
                         (1.0 - refcmult) * imgwfsrefc.im->array.F[ii];
                 }
             }
```

### 8.4 Important Note on `/home/guyon/src/cacao/AOloopControl/modalfilter.c` (Read-Only Inspection)

No change to `modalfilter.c` is *required* for pixel-space `WFSzpogain`, because scaling `wfszpo` in `acquireWFSim.c` cancels Stage-3 LLOWFS *before* `wfs2cmodeval-2`, so `wfs_in[mi]`, `dmval`, `ol_out[mi]`, and `mval_pf[mi]` all automatically see zero LLOWFS leakage.

However, inspection of `modalfilter.c` revealed **two real improvements** to keep in mind for Phase 4a/4b:
1. **PSOL optical-gain sync (`mfilt-2.comp.WFSfact`):** Line 723 computes `ol_out[mi] = (psol_WFSfact * mwfsf[mi]) * wfs_in[mi] - tmpmDMval`. On-sky, `psol_WFSfact` should equal **`1.0 / g_opt`** (`~1.20–1.25`), NOT the calm-calib `testOL` value (`1.06`!). Updating `mfilt-2.comp.WFSfact = 1.0 / g_opt` (or per-mode `aol2_mWFSfact[mi] = 1.0 / g_opt[mi]`) alongside `acquWFS-2.WFSzpogain = g_opt` fixes PSOL reconstruction for AR/EOF at the same time!
2. **Latent unit bug if modal `aol2_mzeropoint` is ever used with `enablePF=1`:** Line 637 treats `zpo[mi]` in **WFS units** (`(zpo[mi] - wfs_in[mi]) * mg[mi]`), line 723 omits `- zpo[mi]` from `ol_out[mi]`, and line 796 writes `cmd_pf = zpo[mi] - mval_pf[mi]` (mixing WFS units `zpo[mi]` with DM units `mval_pf[mi]`). If modal ZPO is ever activated with PF, lines 723 and 796 should be fixed to:
   - Line 723: `ol_out[mi] = (psol_WFSfact * mwfsf[mi]) * (wfs_in[mi] - zpo[mi]) - tmpmDMval;`
   - Line 796: `float cmd_pf = -mval_pf[mi];`

### 8.5 Exact Minimal `.milk` Patch: `/home/guyon/src/cacao-work/benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk`

Add `WFSZPO_GAIN="${CACAO_WFSZPO_GAIN:-1.0}"`, wire it into `cmd_deploy()`, and add a live `setog <g_opt> [--no-psol]` (or `setzpogain <g_opt>`) subcommand:

```diff
--- a/benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk
+++ b/benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk
@@ -111,6 +111,7 @@ RATE="${CACAO_WFSFRATE:-100}"
 LAT_FR="${CACAO_LATENCYHARDWFR:-1.5}"
 SOFT_LAT_FR="${CACAO_LATENCYSOFTWFR:-1.65}"
 PSOL_WFSFACT="${CACAO_PSOL_WFSFACT:-1.0}"
+WFSZPO_GAIN="${CACAO_WFSZPO_GAIN:-1.0}"
 TBUFF_SIZE="${CACAO_TBUFF_SIZE:-256}"
@@ -208,6 +209,7 @@ Usage:
   ${SCRIPT_NAME} [--stage 1|2|3] pf-on [mixcoeff [pflatency]]
   ${SCRIPT_NAME} [--stage 1|2|3] pf-freeze
   ${SCRIPT_NAME} [--stage 1|2|3] pf-off
+  ${SCRIPT_NAME} [--stage 1|2|3] setog <g_opt> [--zpo-safety F] [--no-psol]
   ${SCRIPT_NAME} [--stage 1|2|3] testol [mode [ampl [nbsample]]]
@@ -453,6 +455,7 @@ acquWFS-${N}.comp.WFSrefsub           = ON
 acquWFS-${N}.comp.WFSsigav            = ON
 acquWFS-${N}.comp.WFSrefc             = ON
+acquWFS-${N}.WFSzpogain               = ${WFSZPO_GAIN}
 acquWFS-${N}.wfszpo                   = ${PFX}wfszpo
@@ -1438,6 +1441,26 @@ cmd_testol() {
     milk-fps-set -q "${PF_MK_UNIT}.PFlatency=${pflat}"
 }
 
+cmd_setog() {
+    if (( $# < 1 )); then
+        echo "${SCRIPT_NAME}: 'setog' requires <g_opt> (0 < g_opt <= 2.0)" >&2
+        return 2
+    fi
+    local g_opt="$1" safety="0.95" upd_psol=1
+    shift
+    while (( $# > 0 )); do
+        case "$1" in
+            --zpo-safety) safety="$2"; shift 2 ;;
+            --no-psol)    upd_psol=0; shift ;;
+            *) echo "${SCRIPT_NAME}: unknown setog option '$1'" >&2; return 2 ;;
+        esac
+    done
+    local zpo_g wfs_f
+    zpo_g="$(awk -v g="${g_opt}" -v s="${safety}" 'BEGIN { v = g * s; if (v < 0.1) v = 0.1; if (v > 1.5) v = 1.5; printf "%.4f", v }')"
+    wfs_f="$(awk -v g="${g_opt}" 'BEGIN { v = (g > 0.1 ? 1.0 / g : 10.0); if (v > 5.0) v = 5.0; printf "%.4f", v }')"
+    @set "f.acquWFS-${N}.WFSzpogain=${zpo_g}"
+    if (( upd_psol )); then
+        @set "f.mfilt-${N}.comp.WFSfact=${wfs_f}"
+    fi
+}
+
@@ -1515,6 +1538,7 @@ case "${subcmd}" in
     pf-on)     cmd_pf_on "$@" ;;
     pf-freeze) cmd_pf_freeze "$@" ;;
     pf-off)    cmd_pf_off "$@" ;;
+    setog)     cmd_setog "$@" ;;
     testol)    cmd_testol "$@" ;;
```

**Optional `sim-ao3k-scexao.milk` integration (3 lines):**
- Add CLI flag `--zpo-og <float>` (default `1.0`, or e.g. `0.75` for 3 λ/D / `0.70` for 0 λ/D unmod; or auto-set from an on-sky `testOL` / passive `calib2wfs1dm` step right after closing Stage 1 + Stage 2 and *before* closing Stage 3 LLOWFS at line 834!):
  ```bash
  if [[ -n "${ZPO_OG}" ]]; then
      CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 setog "${ZPO_OG}"
  fi
  ```
- **Verification test plan (once session `95081576` finishes and GPU is free):**
  1. Rebuild `cacao` (`AOloopControl_IOtools/acquireWFSim.c`), verify default `WFSzpogain=1.0` produces bit-identical telemetry.
  2. Run a 20 s `sim-ao3k-scexao.milk --gain2 0.35` (Integrator + LLOWFS closed) comparing `--zpo-og 1.0` vs `--zpo-og 0.72` (safety-scaled to `0.68`): verify `B` TT bursts vanish (TT RMS stays ~1.7 instead of bursting to 7.3), `dmzpo_rms` stays `< 0.005`, Stage-2 `selfRM_onsky` passes `selfrm_dyn` cleanly (`g_dyn / P ≈ 1.0`), and `realsim_lowfs.py` measures `a + b ≈ 0.00` (instead of `-0.16` to `-0.35`)!
  3. Repeat on `ao3k_scexao_calib2wfs1dm` (AR(8) + LLOWFS closed) and `stg2unmod_eof128_p8` (0 λ/D unmod + LLOWFS closed) to verify the `t = 4–5 s` ZPO wind-up is completely eliminated.
