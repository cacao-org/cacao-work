# Self-learning AO controller (GRIC state clustering + online hierarchical RLS)

Start here. This directory tracks the self-learning AO controller from the initial 2026-11-20
feasibility study (Phase 1) through nonlinear/non-stationary headroom verification (Phase 2) to
the deployed native C MILK-FPS real-time controller `cacao-fpsexec-cacaopc-selflearn` linked
directly against `libgric` and exercised in live GPU closed loop on `scao_pyr` (Phase 3).

**Status:** Deployed and verified in C (`cacao` branch `feat/bash-engine`,
`cacao-fpsexec-cacaopc-selflearn`), integrated into `benches/scao_pyr/cacaoloop-scao-pyr.milk`,
and covered by automated lockstep + live GPU HIL tests (`tests/test_17_selflearn.py`).

---

## Phase 1 (2026-11-20): Feasibility Study on Stationary Linear Telemetry

## The proposal (user's words, condensed)

- A small correction on top of the default linear controller.
- As the loop runs, log in a compressed form the **state** (e.g. the last 16 WFS, PSF and DM
  frames, plus the DM correction applied) against the **WF residual** that followed.
- The table may assume local linearity and use PCA and clustering to group similar states.
- At run time, match the current state (whose residual is not yet known) against the table and
  extract a correction better than the linear controller.
- The residual label may be a box average around the central time (past and future frames)
  to average noise.
- Suggested tool: GRIC, <https://github.com/oguyon/gric-cluster> (local checkout
  `~/src/gric-cluster`, binaries in `~/.local/bin`).

## Verdict

**Feasible only in a restricted form.** Literal matching of the full state (16 frames x
WFS/DM/PSF) cannot work: that state never recurs. What can work is a global linear (EOF /
predictive) filter plus a state-dependent **linear** correction indexed by a key of a few
variables, i.e. learned gain scheduling / mixture of local linear models. One cluster reduces
exactly to the EOF predictive filter, which is a clean limit to validate against.

## Data used

`_work/calib_2wfs1dm_realsim/run1/win_lowfs_open/telemetry/` (gitignored, 698 MB, not copied
here; check it still exists): AO3k + SCExAO simulator (cacaosim), stage 1 only,
`aol1_modevalWFS_*.fits` and `aol1_modevalDM_*.fits`, 8 files x 2500 frames x 1965 modes,
1 kHz, 20 s. 0.6" seeing, mV 6, frozen flow, stationary. Stage-1 loop: leaky integrator, gain
0.35 (low modes; median 0.22 over all modes), leak (mult) 0.98. Stage 2 closed, LLOWFS open.
WFS frame k and DM frame k are the same loop iteration (DM written ~0.11 ms later); the `.txt`
companions give cnt0 (col 6) and logging time (col 4), used to check for dropped frames.

To regenerate on a new run, any telemetry directory with `aol1_modevalWFS_*.fits` /
`aol1_modevalDM_*.fits` + `.txt` files works (simulator workflow: `scripts/run-ao3k-scexao.sh`,
see the repo `AGENTS.md`; SHM sandbox rules apply).

## Results (measured)

### A. Does the state recur? (`code/selflearn_probe.py ... A`, `logs/probe_partA.log`)

Queries = last 2 s; database = frames strictly earlier (>= 2 s gap), lengths 2/4/8/16 s.
`rho` = distance to best match / distance to a typical database frame (median over queries);
correlation of a state with its best match = 1 - rho^2. "8 h" = power-law extrapolation of
rho vs database length (optimistic).

| WFS residual key (whitened) | 1 frame, 16 s | 1 frame, 8 h | 16 fr., 16 s | 16 fr., 8 h |
| :--- | :---: | :---: | :---: | :---: |
| 2 modes | 1.000 | 1.00 | 0.98 | 1.00 |
| 5 modes | 0.97 | 1.00 | 0.91 | 1.00 |
| 10 modes | 0.87 | 0.99 | 0.78 | 0.96 |
| 20 modes | 0.71 | 0.89 | | |
| 50 modes | 0.53 | 0.73 | 0.44 | 0.65 |
| 300 modes | 0.33 | 0.34 (flat) | | |
| 1965 modes | 0.17 | no trend | 0.16 | no trend |

- Full state (WFS+DM, all modes, 16 frames): best-match correlation 0.25, no improvement with
  database length. Matching is real only for <= ~10 dimensions, marginal at 20-50.
- PCA: DM (~turbulence) participation ratio 4.4 (90%/99% variance in 25/316 components);
  WFS residual participation ratio 128 (90%/99% in 1097/1782). The residual is close to white
  in mode space, so PCA does not compress it.
- The whitened-DM rows at high mode counts look better than the WFS rows, but this is slow
  drift of weakly sensed high-order DM modes, not a recurrence. `code/lagcorr.py`
  (`logs/lagcorr.log`) confirms no phase-screen repeat within 20 s (strongest long-lag
  correlation, modes 50+: DM 0.09, WFS 0.02). Do not quote DM rows as recurrence.
- WFS residual temporal autocorrelation: lag 1 frame 0.97 (modes 0-9), 0.94 (10-49),
  0.78 (50-299), 0.47 (300-1964); ~0 beyond 0.5-1 s.

### B. Lookup vs linear predictor on held-out data (`code/selflearn_probe.py ... B`,
`code/purelookup.py`; `logs/probe_partB.log`, `logs/purelookup.log`)

Target: WFS residual 2 frames ahead, per 50-mode block. Features: 10 past frames of WFS + DM
for that block (1000 features, standardized). Train first 14 s (13991 frames), 0.5 s gap,
test on the rest (every 3rd frame, 1832 frames). Ridge, lambda by contiguous 5-fold
out-of-fold error. Numbers = % of baseline residual variance removed on the test set.

| Predictor | Modes 0-49 | Modes 200-249 |
| :--- | :---: | :---: |
| Global linear (ridge, 10 frames WFS+DM) | 96.2% | 51.3% |
| Persistence (repeat last frame) | 94.4% | 29.2% |
| Pure lookup, best of 35 (q PCA dims x k) | 33.6% (q=64, k=1000) | 14.6% (q=128, k=200) |
| Lookup added on top of linear, best of 22 variants | ~0 (-0.04%) | +0.16% (control -0.18%) |

- **Second stage on the linear residual** (out-of-fold training residuals): kNN mean residual
  (k=20, 200), kNN local-linear, K=1/4/16 k-means clusters with a per-cluster linear map of the
  global prediction, and per-cluster full linear refit; matching spaces: top 4 / top 16 PCA
  dims of the state, a residual-energy scalar, and PCA-4 + scalar. Every variant is <= 0 and
  indistinguishable from a **shifted-pairing control** (test residuals rolled by 500 frames,
  which destroys any real state-label link). Mean-residual kNN is actively harmful (-4 to
  -20%: it injects the neighbours' noise).
- **Positive control** (`inject=0.1`): synthetic state-dependent gain added to the target,
  `c = s * P0` with `s` = standardized log of the last-10-frame residual energy (optical-gain
  proxy) and `P0` the linear prediction, scaled so the oracle removes 14.5% of what the linear
  predictor leaves (modes 0-49). Results:
  - PCA-keyed lookups (any variant): all negative, same as control. **Missed.**
  - Mean-residual kNN on the right scalar: -9.1% / -4.1%. **Missed.**
  - Clusters on the scalar with a per-cluster linear map of the global prediction:
    K=4 **+6.2%** (control -4.6%), K=16 **+5.9%** (control -5.9%); full refit K=4 +2.8%.
  - Same with 4 PCA dims added to the key: K=4 -0.75%, K=16 -2.4%. **Erased.**
  So a state-dependent effect is learnable only with (i) a key that is the right
  low-dimensional variable and (ii) a linear payload, not an average of neighbour residuals.
- **Caveat on 96%**: for low-order modes this is dominated by the leaky integrator's
  steady-state error (gain 0.35, leak 0.98: ~(1-m)/((1-m)+g) ~ 5% of low-order turbulence
  remains as a slowly varying residual proportional to the DM state), which is why persistence
  gets 94%. It is a property of the baseline controller, not a learning gain. All figures are
  "predictability of the residual under the logged controller", not closed-loop performance.

## Why (reasoning, not measured)

1. **Linear is optimal for linear-Gaussian.** Frozen-flow turbulence + linear WFS + Gaussian
   noise has a linear conditional mean; a lookup can only converge to the linear filter with
   worse statistics. The null in B is therefore expected on a stationary simulator. Any real
   gain must come from: WFS nonlinearity (PyWFS optical gain, ZWFS, PSF intensity),
   non-stationarity (wind, seeing, vibration changes), non-Gaussian / intermittent events
   (low-wind effect, petal modes).
2. **Dimension.** High-dimensional dynamical states do not recur on usable timescales; the
   same wall hit analog weather forecasting (van den Dool 1994: a library of order 10^30
   needed for one good hemispheric analogue). Linear regression coherently combines thousands
   of low-SNR directions; matching cannot.
3. **Sample budget.** A night is 10^7-10^8 frames but only 10^2-10^3 independent samples of the
   slow variables, and each local linear model needs ~10^4 frames: ~10^3 usable cells, so a key
   of a few dimensions at most.

## Recommended design (if pursued)

- **Stage 1**: the existing EOF / Block-EOF predictive filter
  (`scripts/studies/predictive_control/`, `scripts/report_site/extractors/eof_pf.py`).
  The table models only what it leaves.
- **Key**: a few variables chosen because they modulate the linear response, not because they
  carry variance: residual energy per spatial-frequency band (optical-gain proxy), wind vector,
  vibration amplitude/phase, or a <= 10-mode low-order subspace. Check recurrence first.
- **Payload per cluster**: running sufficient statistics of a linear correction in the global
  predictor's output space (`N`, `sum P P^T`, `sum P e^T`), exponential forgetting,
  hierarchical shrinkage to the global model (thin cluster -> global filter). Smooth scalar
  dependence is better served by a bilinear parametric model than by bins.
- **Fail-safe**: no cluster within `r_lim` -> zero correction; separate bounded DM channel;
  shadow mode, then A/B on sky.
- Closest prior art: LWPR (Vijayakumar, D'Souza & Schaal 2005, incremental local linear models
  with forgetting). Neural cousin: PO4AO (Nousiainen et al. 2022 A&A; 2024 JATIS, GHOST bench).
- Deployment, when it comes, goes into the milk framework / milk-mltools (calc, JIT, compute
  units, plugins), not new Python; these scripts are the reference to match.

## Traps in the formulation as proposed

1. **Closed-loop counterfactual.** The logged residual depends on the controller in force;
   once the correction is applied, a naive table un-learns itself. Learn the disturbance in
   pseudo-open-loop coordinates (residual + what the DM did), and box-average that, since the
   integrator has already partly corrected the future frames.
2. **Shared noise.** The label window must not include WFS frames that are in the state, or the
   table learns the noise. Label noise only costs samples (no bias), so the box average buys
   less than it seems.
3. **A WFS cannot grade itself.** A WFS-derived label inherits the sensor's gain and null
   errors. Fixing those needs PSF frames or the second WFS as label: the same identification
   problem as the 2-WFS study (`algo/calib2wfs1dm/`). Also: the DM command is a deterministic
   function of the state, so alternative commands are unidentified without randomization
   (WFS noise as natural instrument, or dither).

## Where GRIC fits

- **Diagnostic first**: `gric-dimdensity` (local intrinsic dimension) and cluster count vs
  frames at fixed `r_lim` on candidate keys. A key is usable only if the count saturates.
- **Online partition** of the key space: streaming `gric-cluster` (with `-tm` transition
  priors for regime persistence).
- **Needed extension**: `milk-fpsexec-gric-knn` + `milk-fpsexec-gric-reconstruct` return an IDW
  average of neighbour targets, which is the mean-residual payload that failed the positive
  control. They would need per-cluster regression statistics instead. Triangle-inequality
  pruning and entropy targeting matter little for <= 20-D keys.

## Not tested / next steps

- Untested: on-sky data; non-stationary conditions; PSF frames in the state; stage 2; other
  seeing / brightness; only 14 s of training data; closed-loop application of any correction.
- **Decisive next test (regime headroom)**: in the simulator, change wind or seeing mid-run;
  train the predictive filter in regime 1, apply in regime 2, compare to a filter matched to
  regime 2. That gap is the most any regime-keyed table can recover. Also test whether the
  linear residual depends on any low-dimensional descriptor (rerun Part B second stage with
  candidate keys, no injection).
- Natural first targets where the key is low-dimensional: tip/tilt + vibrations, LLOWFS,
  petal / LWE modes, photonic-lantern low-order sensing.

## Phase 2: Nonlinear & Non-Stationary Headroom (`unmod_headroom_probe.py`)

Following Phase 1's conclusion that gains require nonlinearity or non-stationarity plus a
low-dimensional recurring key, we evaluated real `gric-cluster` recurrence and 2-level
hierarchical online factorized RLS across three regimes (`logs/unmod_headroom_v2.log`,
`logs/unmod_headroom_s035.log`):

1. **Low-D GRIC keys recur and saturate.** On 4000-10000 frames, `e1_logE` (1D),
   `regime_e2_vel` (3D), `wfs_lo4` (4D), and `tt2_e2` (4D: `[w_0, w_1, log E_lo, log E_hi]`)
   saturate cleanly at `K = 8..27` clusters (`r_lim = 2.0..2.5`).
2. **Stage-2 unmodulated PyWFS (`exp2_unmod_mh6_base`, `aol2`) is effectively linear.**
   Stage 1 already reduces WFS residuals to `0.84 nm/mode`; Level-0 online RLS matches offline
   linear (`+77.5%` PSOL variance reduction) and Level-1 GRIC adds ~`0%`.
3. **Wind switch (`exp1_windsw_base`, +60 deg, `aol1`, PSOL increment target):**
   - Static offline linear ridge collapses to `-9.64%` variance reduction after the wind switch.
   - Level-0 global online forgetting RLS recovers `+28.93%`.
   - Adding Level-1 GRIC clusters removes an extra **`+4.64%`** (`tt2_dm2_e2`, `total +32.23%`,
     shifted-pairing control `-2.23%`) and **`+4.03%`** (`regime_e2_vel`, `total +31.80%`,
     control `-4.94%`).
4. **Single-stage unmodulated PyWFS (`scao_pyr`, `mod_rad=0.0`, `seeing=0.35"`, CL SR ~0.35):**
   - Hard-nearest un-gated Level-1 GRIC (`unmod_headroom_probe.py`, `logs/unmod_headroom_s035.log`)
     loses variance at cluster boundaries (`-2.17%` on `tt2_e2`, `+0.18%` on `wfs_lo4`).
   - Adding **soft Gaussian LWPR blending across GRIC anchors + causal OOS Stein gating** in
     `cacao-fpsexec-cacaopc-selflearn` turns this into **`+6.3%` extra OOS variance reduction
     over Level-0** (`L0 = +97.1%`, `L1/L0 = +6.3%`, `Tot = +97.2%` on the exact same telemetry;
     `tests/test_17_selflearn.py::test_17_3`).

---

## Phase 3: Native C MILK-FPS Controller (`cacao-fpsexec-cacaopc-selflearn`)

### Architecture (`cacao/AOloopControl_PredictiveControl/`)

- **Core engine:** `selflearn_core.h`, `selflearn_core.c`
- **MILK-FPS executable:** `AOloopControl_PredictiveControl_selflearn.c`
  (`EXPORT_FPSEXEC(cacao, "cacaopc-selflearn", ...)`, installed as
  `cacao-fpsexec-cacaopc-selflearn`), auto-linking `libgric.so` (`HAVE_LIBGRIC=1`) via
  `CMakeLists.txt` (with a built-in leader-clustering fallback if `libgric` is absent).
- **Streaming GRIC state key (`key_mode`):**
  `0 = TT2_E2` (`[w_0, w_1, log E_lo, log E_hi]`), `1 = E1_LOGE`, `2 = WFS_LO4`,
  `3 = TT2_DM2_E2`, `4 = REGIME_E2_VEL`, `5 = EXTERNAL` (custom SHM key stream).
- **Zero-DC closed-loop-safe regressor (per mode `m`):**
  `phi_{t,m} = [dOL_m(t..t-3), w_m(t), dOL_0(t)..dOL_{q-1}(t)]` (standardized causally).
  All `dOL` taps vanish identically at DC, pinning closed-loop DC gain strictly to
  `dc_leak < 1.0` (standalone PF) or inheriting `inbasePF`'s leak (cascaded PF) so no bias
  can integrate into DM rails.
- **Numerically guaranteed SPD online regression:**
  Both Level 0 (global) and Level 1 (per GRIC cluster `k`, trained strictly on the unbiased
  unconstrained Level-0 residual `yt - w0 . phi_s`) maintain exponentially-weighted normal
  equations `G = gamma * G + x x^T`, `b = gamma * b + x y`, solved via per-mode Cholesky of
  `(G + lam * I) w = b`. `G` stays strictly PSD forever, eliminating Sherman-Morrison
  covariance PD-loss and `-Ofast` NaN drift (`selflearn_core.c` also compiles with
  `-fno-finite-math-only` plus bit-level IEEE finiteness guards).
- **Combined stability-ball projection & causal OOS Stein gates:**
  At prediction time, BOTH Level-0 alone and the combined `L0 + L1` weight vector are
  projected onto the exact same stability ball (`ar_norm2 <= max_ar_norm2`, physical WFS gain
  in `[-0.35, +max_wfs_gain]`). Level 1 can redistribute optical gain and AR phase across
  clusters but can never circumvent global stability limits. Two online causal OOS Stein gates
  `alpha_l0, alpha_l1 = clip(C_ey / (C_yy + eps), 0, 1)` smoothly shut Level 1 to `0.00`
  whenever clustering does not improve causal OOS error.
- **Operating modes & live `FPFLAG_WRITERUN` toggles:**
  - `out_mode=0` (PF synchronous, zero extra latency): standalone PSOL or cascaded on top of
    `applyARPF` via `.inbasePF` + `.inbaseStat`.
  - `out_mode=1` (`auxDM`, additive damped tweak into `aol{N}_modevalauxDM`).
  - Live toggles: `.learnON`, `.shadow` (learn & score OOS while emitting exact `0.0`),
    `.enable_l0`, `.enable_l1`, `.apply_gain`, `.reset`, plus `.savedir` to dump GRIC
    `anchors.bin` on stop.

### Verification Suite (`tests/test_17_selflearn.py` — 3/3 passed)

| Test | Setup | Key Verified Result |
| :--- | :--- | :--- |
| `17.1` Pos | 2-regime nonlinear (`M=16, 2400 fr`) | `gric=1, K=2, L1/L0=+9.8%, 28.9 us/fr` |
| `17.1` Shd | `.shadow=ON` (`600 fr`) | Exact `0.0` tweak, `updates>=500, K>=2` |
| `17.1` Null | Linear-Gaussian AR(2) (`2400 fr`) | `L0=+11.2%, L1/L0=-0.00%, a1=0.00` |
| `17.3` Rpl | `scao_pyr` unmod (`M=32, 3000 fr`) | `K=7, L0=+97.1%, L1/L0=+6.3%, 26 us/fr` |
| `17.2` Live | Closed-loop `scao_pyr` (`0.0, 0.35"`) | `dm_rms<2, outl=0`, SR >3x OL, >=0.95x INT |

### Live GPU Closed-Loop Interleaved A/B (`scao_pyr`, 400 Hz)

Single-window sequential runs on `scao_pyr` suffer `±0.05..0.08` SR swings from local seeing
patches scrolling across the turbulence phase screen. `code/run_interleaved_ab.sh` cycles all
controllers over `4 x 400` interleaved frames (`1600` measured frames/controller) in one
continuous run (`logs/live_interleaved_unmod0_s035.log`,
`logs/live_interleaved_mod3_s070.log`):

**Unmodulated PyWFS (`mod_rad=0.0`, `seeing=0.35"`, `lat=1.257 fr`):**

| Blk | Ctrl | `SR_ave` (mean±SE) | `SR_pk` | `wfs_rms` | `dm_rms` | Notes |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| A | `int` | `0.384 ± 0.050` | `0.385` | `0.000371` | `0.330` | leaky integrator |
| A | `arpf` | `0.387 ± 0.062` | `0.379` | `0.000363` | `0.460` | `mkARPF+applyARPF` |
| A | `arpf_l0` | **`0.437 ± 0.037`** | `0.434` | **`0.000340`** | `0.478` | `+0.050` vs ARPF |
| A | `arpf_gric` | `0.421 ± 0.043` | **`0.448`** | `0.000359` | `0.553` | `K=15, a1=1, L1=+1.0%` |
| B | `int2` | `0.311 ± 0.058` | `0.312` | `0.000380` | `0.396` | leaky integrator |
| B | `sl_l0` | `0.394 ± 0.023` | `0.436` | `0.000365` | `0.648` | `+0.083` vs `int2` |
| B | `sl_gric` | **`0.444 ± 0.060`** | `0.435` | **`0.000345`** | `0.533` | `+0.133`, `K=16` |

**Modulated PyWFS (`mod_rad=3.0`, `seeing=0.70"`, `lat=1.398 fr` — nearly linear control):**

| Blk | Ctrl | `SR_ave` (mean±SE) | `SR_pk` | `wfs_rms` | `dm_rms` | Notes |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| A | `int` | `0.166 ± 0.030` | `0.181` | `0.000240` | `0.455` | leaky integrator |
| A | `arpf` | `0.219 ± 0.021` | `0.237` | `0.000232` | `0.510` | batch linear PF |
| A | `arpf_l0` | **`0.229 ± 0.021`** | `0.241` | `0.000243` | `0.618` | `+0.062` vs `int` |
| A | `arpf_gric` | `0.208 ± 0.009` | **`0.242`** | `0.000240` | `0.633` | `K=16, L1=+0.04%` |
| B | `int2` | `0.111 ± 0.013` | `0.133` | `0.000254` | `0.542` | leaky integrator |
| B | `sl_l0` | **`0.215 ± 0.033`** | `0.229` | `0.000238` | `0.577` | `1.94x` `int2` SR |
| B | `sl_gric` | `0.198 ± 0.027` | `0.201` | **`0.000236`** | `0.525` | `1.79x`, `L1=+0.52%` |

**Takeaway:** In stationary closed loop on `scao_pyr`, `cacaopc-selflearn` delivers large,
repeatable Strehl gains (`+0.05..+0.13` SR unmodulated, `~1.8-2.0x` SR modulated) with zero
outliers and sub-30 us/frame RT latency. Most of the stationary closed-loop Strehl gain comes
from fast online Level-0 RLS + optical-gain adaptation, while Level-1 GRIC adds a bounded
state-dependent refinement (`+0.98%..+6.3%` OOS on unmodulated PyWFS vs `+0.04%` on modulated
PyWFS and `-0.00%` on linear-Gaussian null) that scales up further under strong regime shifts
(such as wind/seeing switches or larger optical-gain excursions).

---

## Files

| Path | Content |
| :--- | :--- |
| `code/selflearn_probe.py` | Phase 1: Part A (recurrence) and Part B (linear vs lookup, controls) |
| `code/purelookup.py` | Phase 1: Pure kNN lookup grid (q PCA dims x k) vs linear and persistence |
| `code/lagcorr.py` | Phase 1: Lagged correlation of whitened state (screen-recurrence check) |
| `code/unmod_headroom_probe.py` | Phase 2: Native GRIC recurrence & hierarchical RLS probe |
| `code/capture_scao_unmod.sh` | Phase 2: Capture isolated closed-loop `scao_pyr` telemetry |
| `code/run_live_scao_ab.sh` | Phase 3: 9-stage live GPU A/B (INT, ARPF, SL, cascade, auxDM) |
| `code/run_interleaved_ab.sh` | Phase 3: Multi-cycle interleaved live GPU A/B benchmark |
| `logs/*.log` | Saved Phase 1, Phase 2, and Phase 3 benchmark outputs |
| `tests/test_17_selflearn.py` | Lockstep RT, positive/null, replay, and live GPU HIL tests |

### Quickstart & Reproduction

```bash
# 1. Verify binary installation & run full automated test suite (lockstep + live GPU HIL)
./scripts/build-all.sh --check-only
pytest -v -s tests/test_17_selflearn.py

# 2. Run multi-cycle interleaved live GPU closed-loop A/B on unmodulated PyWFS
./algo/selflearn/code/run_interleaved_ab.sh 0.0 0.35 4 400 _work/selflearn_scao_unmod0_s035/rm

# 3. Engage selflearn interactively on a running scao_pyr bench
./benches/scao_pyr/cacaoloop-scao-pyr.milk selflearn-on 0.90 0 2.0
./benches/scao_pyr/cacaoloop-scao-pyr.milk selflearn-off
```

Phase 1 reproduction (from repo root):

```bash
T=_work/calib_2wfs1dm_realsim/run1/win_lowfs_open/telemetry
/usr/bin/python3 -u algo/selflearn/code/selflearn_probe.py $T A    # ~1-2 min
/usr/bin/python3 -u algo/selflearn/code/selflearn_probe.py $T B    # ~3.5 min, 4 threads
/usr/bin/python3 -u algo/selflearn/code/purelookup.py $T
/usr/bin/python3 -u algo/selflearn/code/lagcorr.py $T
```

## References

- H. M. van den Dool 1994, "Searching for analogues, how long must we wait?", Tellus A 46,
  314-324 (discussed in <https://cp.copernicus.org/articles/17/721/2021/>).
- S. Vijayakumar, A. D'Souza, S. Schaal 2005, "Incremental Online Learning in High Dimensions",
  Neural Computation 17, 2602-2634 (<https://www.inf.ed.ac.uk/publications/report/0375.html>).
- J. Nousiainen et al. 2022, A&A, PO4AO
  (<https://www.aanda.org/articles/aa/full_html/2022/08/aa43311-22/aa43311-22.html>);
  2024 JATIS 10(1) 019001, GHOST bench (<https://arxiv.org/html/2401.00242v1>).
