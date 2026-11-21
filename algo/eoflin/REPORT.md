# Local linearity in EOF predictive control: synthetic study

Date: 2026-11-20. Status: exploratory, toy data only. No cacaosim or bench telemetry was used.

## 1. Question

The EOF predictor (Guyon & Males 2017; cacao `mkEOFPF`) is a single linear map from a history
vector h_t (P lags x B modes, D = P*B) to the future modal state. Real AO telemetry is at best
*locally* linear. Proposal under study (from O. Guyon):

> Instead of expressing the current state as a linear sum of all previous states, express it as
> a linear sum of *similar* past states, with a proximity coefficient. The PCA step of EOF must
> be modified to encode proximity. The clustering code `gric-cluster`
> (https://github.com/oguyon/gric-cluster) could provide the proximity structure.

## 2. Short answer

1. **Proximity between states (history vectors) does not help.** It never beat the global EOF
   in the toy, and it cannot help in the linear-Gaussian case (see 4.1).
2. **Proximity between observing conditions does help, a little.** Weighting past training data
   by similarity of a low-dimensional *regime descriptor* (here a wind estimate) gained 3-8% in
   residual variance over equal weights, matching what oracle wind labels give.
3. **Memory length matters far more.** Using all past data instead of the last 16 s (the
   current `mkEOFPF` `NBtrain` = 16384 frames) halved the residual in the toy.
4. **A weight floor is required.** Dissimilar data must keep a weight around 0.1; training on
   same-regime data only was worse than not weighting at all.
5. `gric-cluster`, run on the descriptor stream (not on the modes), works as the quantizer for a
   regime-indexed library of Gram accumulators, at the same performance as a continuous kernel.

## 3. Setup

Generator: `code/gen.py`.

- Two-layer frozen-flow von Karman turbulence, 4096^2 periodic screens, L0 = 25 m.
- 8 m pupil sampled on 24 px; 64 KL modes from the exact pupil covariance. Spectral cutoff
  `KCUT` = 0.35 cycles/px.
- 1 kHz frame rate. Prediction target is the state 2.4 frames ahead:
  `0.6 a[t+2] + 0.4 a[t+3]`.
- Upper layer wind switches among three recurring vectors, (14 m/s, 0 deg), (14 m/s, 40 deg) and
  (8 m/s, -30 deg), with dwell times drawn uniformly in 6-14 s. The ground layer is fixed at
  (4 m/s, 200 deg). A 17.3 deg offset keeps tracks from retracing on the periodic screen.
- Layer variance split 60/40 (`sw.npz`), or 90/10 (`sw90.npz`, one dominant layer).
  `st.npz` holds a single constant wind (stationary control case).
- Open loop. White measurement noise is added to the modes, with variance set to
  `noise_frac` x the mean per-mode zero-order-hold error. `noise_frac` = 0.6 unless stated,
  which makes noise about 37% of the ZOH error.
- EOF: P = 8 lags, D = 512, least squares with a tiny ridge (1e-10 x trace/D).

Metric: **resid/ZOH** = prediction error variance against the *true* (noise-free) future,
divided by the error of the no-prediction (zero-order-hold) predictor. Lower is better.

## 4. Findings

### 4.1 Proximity between history vectors (the literal proposal): no gain

Script `code/smap.py`, logs `logs/smap_*.log`. This is locally weighted least squares (S-map):
for each query h_q, sample i gets weight `w_i = kappa + (1-kappa) exp(-theta d(h_q,h_i)/dbar)`,
and a separate EOF is solved per query. theta = 0 is the global EOF. Distances are either raw or
per-mode normalized. 150 queries were used, with 35-40k training rows.

| data | metric | global | theta=1 | 2 | 4 | 8 | theta=8, kappa=0.1 |
|---|---|---|---|---|---|---|---|
| stationary | raw | 0.3053 | 0.3055 | 0.3071 | 0.3145 | 0.3535 | 0.3083 |
| stationary | norm | 0.3053 | 0.3053 | 0.3056 | 0.3066 | 0.3115 | 0.3075 |
| switching | raw | 0.3156 | 0.3157 | 0.3167 | 0.3212 | 0.3422 | 0.3173 |
| switching | norm | 0.3156 | 0.3157 | 0.3160 | 0.3168 | 0.3201 | 0.3168 |

Why it fails:

- **Theory.** For Gaussian turbulence and a linear sensor, (history, future) are jointly
  Gaussian, so the conditional mean is exactly linear in the history. Locality then only
  reduces the effective sample size.
- **No near neighbours.** For history vectors in D = 512, the nearest neighbour sits at 0.47
  (raw) or 0.74 (normalized) of the median distance. Neighbours from the same 2 s of trajectory
  are excluded from this count. The 100th neighbour is barely further. Local intrinsic
  dimension (Levina-Bickel) is 49-58 (`logs/lid.log`). "Similar past states" do not exist in a
  useful sense.
- **State similarity is blind to the regime.** On switching data, the proximity weights put
  0.366-0.373 of their mass on same-wind samples, against 0.364 by chance.

### 4.2 Where the nonlinearity actually lives: slowly varying conditions

Script `code/rg.py`, log `logs/rg.log`. A filter trained on one wind regime is compared with a
filter pooled over all regimes, both scored on that regime's test data (160 s train).

| data | regime | train rows | pooled | own-regime | pooled excess | wrong-regime filter |
|---|---|---|---|---|---|---|
| 60/40 | 0 | 68814 | 0.2867 | 0.2789 | +2.8% | 0.47-0.67 |
| 60/40 | 1 | 57484 | 0.2935 | 0.2791 | +5.2% | 0.44-1.33 |
| 60/40 | 2 | 33541 | 0.4668 | 0.5473 | -14.7% | 0.48-0.72 |
| 90/10 | 0 | 68814 | 0.2605 | 0.2337 | +11.5% | 0.68-0.83 |
| 90/10 | 1 | 57484 | 0.2735 | 0.2333 | +17.3% | 0.62-1.98 |
| 90/10 | 2 | 33541 | 0.4668 | 0.3981 | +17.2% | 0.57-1.22 |

- The optimal filter does depend on the regime: using another regime's filter costs 2-8x.
- A single pooled filter nevertheless gets within 3-5% (two layers) or 11-17% (one dominant
  layer) of the regime-specific filter. With several lags the linear filter extrapolates each
  mode's trend without knowing the wind, so EOF is already partly regime-adaptive.
- With little data (regime 2, 60/40) the pooled filter wins: data sharing beats specificity.
- At low noise (`noise_frac` = 0.06) the pooled excess shrinks to 2-6%.

### 4.3 Causal online comparison: memory vs regime weighting

Script `code/mem.py`, logs `logs/mem_sw.log` and `logs/mem_sw90.log`. Telemetry is cut into 1 s
chunks with one Gram matrix (X^T X, X^T Y) per chunk. At each 1 s boundary every method refits
from a weighted sum of *past* chunk Grams only, then predicts the next second. Test window is
100-240 s.

| method | 60/40 | 90/10 |
|---|---|---|
| sliding 16 s (current `mkEOFPF` memory) | 0.6738 | 0.5304 |
| sliding 32 s | 0.3660 | 0.3419 |
| sliding 64 s | 0.3339 | 0.3165 |
| all past, equal weights | 0.3215 | 0.3013 |
| all past, oracle labels, kappa = 0 (same regime only) | 0.3642 | 0.3112 |
| all past, oracle labels, kappa = 0.1 | 0.3108 | 0.2770 |
| all past, oracle labels, kappa = 0.3 | 0.3134 | 0.2852 |
| all past, wind-descriptor kernel h = 3 m/s, kappa = 0.1 | 0.3109 | 0.2756 |
| all past, `gric-cluster` library rlim = 3 (K = 5), kappa = 0.1 | 0.3110 | 0.2757 |
| all past, `gric-cluster` library rlim = 1.5 (K = 13 / 7), kappa = 0.1 | 0.3116 | 0.2763 |

Regime descriptor: a modal optical-flow wind estimate over the chunk just ended. It uses
`a_t - a_{t-s} ~ -s (vx Dx + vy Dy) a_bar`, with optimal linear modal derivative operators
Dx, Dy built from shifted pupil covariances (`gen.py` stores `dx_op`, `dy_op`). The estimate
scatters by 0.9 m/s (60/40) or 0.55 m/s (90/10) within a regime.

Weighting: `w_c = kappa + (1-kappa) exp(-|z_c - z_now|^2 / 2h^2)`, where z_c is chunk c's
descriptor. In the `gric-cluster` variant z_c is replaced by its anchor: K accumulators, one per
anchor.

Conclusions:

- **Memory is the dominant lever (~2x).** The toy's EOF is data-hungry: D = 512 needs well over
  16k rows. The repo's offline walk-forward study
  (`scripts/studies/predictive_control/solvers.py`, `ntrs_s1` up to 14,500) never trains past
  14,500 frames, so it cannot show this effect either way. The toy may be hungrier for data than
  the real system (its sample complexity was worse than the report's curve), so check this first
  on real telemetry.
- **Regime weighting adds 3% (60/40) to 8% (90/10)** over equal weights. The automatic
  descriptor matches oracle labels, so better regime detection is not the bottleneck.
- **The floor is essential.** kappa = 0 is worse than no weighting. Shared structure (ground
  layer, spatial statistics, noise) is learned from all data.
- **Transient cost.** In the first second after a wind switch, weighted methods score
  0.347-0.371 against 0.336-0.320 for equal weights, because the descriptor lags by a chunk.
  From 1 s on they win.

### 4.4 Side results

- **Cross-mode coupling is weak in this toy** (`code/xm.py`, `logs/xm.log`). Full EOF beats
  per-mode AR by a factor of only 1.1-1.3 at P = 8, and the off-diagonal L2 fraction of the
  pooled filter is about 1%. Two opposing layers limit the spatial route, which explains at
  most about 39% of da/dt. Lower `KCUT` and a Fourier basis did not change this. The 90/10
  dataset was added to bracket it. Real telemetry with a dominant layer should show stronger
  coupling, which would raise the value of regime-specific filters.
- **Isotropic ridge on raw targets is harmful** (`code/an.py`, exploratory). It shrinks the
  prediction toward 0, not toward ZOH, and drags the DC gain down. Later scripts use a
  negligible ridge. A ridge toward the identity/ZOH map would be the safer regularizer.
- **Sliding-window EOF in the first exploration** (`code/an.py`, no log kept) was catastrophic
  at N = 8192 (3.1x ZOH) and poor at N = 16384. This is the same sample-complexity issue as
  4.3.
- **`gric-cluster` anomaly, not investigated.** On a shuffled (non-time-ordered) 3-blob 2-D
  file, `gric-cluster` returned about one cluster per frame at rlim 1.5 and 3.0, and
  `-scandist` aborted with "double free or corruption (!prev)". On time-ordered streams it
  matched a numpy leader clustering exactly (K = 56/56, K = 18/18).

## 5. Interpretation: what "PCA encoding proximity" should mean

In the dual view of EOF the prediction is a linear combination of past futures, with the
coefficients from the Gram (PCA) step. Weighting training sample i by w_i in the primal problem
is exactly equivalent to penalizing its dual coefficient by 1/w_i. So "a linear sum of similar
past states" means the Gram/SVD of the row-weighted data matrix, `X^T W X`, and the question is
only how to choose W:

- W from **state proximity**: no benefit (4.1), and a per-query solve, which is infeasible in
  real time.
- W from **condition proximity** with a floor: small, consistent benefit (4.3). It needs only one
  solve per refit, because the per-chunk or per-anchor Grams are simply re-blended.

## 6. Recommended design (if pursued in cacao)

Per the project rule, deployment should use milk/cacao C units, not Python.

1. **First, lengthen the memory.** Replace or augment the 16k sliding window in `mkEOFPF`
   (`../cacao/AOloopControl_PredictiveControl/AOloopControl_PredictiveControl_mkEOFPF.c`,
   `p_nbtrain` at line 44) with an exponentially forgotten Gram, or a ring of per-chunk Grams
   spanning minutes. This is the largest expected gain and the simplest change.
2. **Regime descriptor stream.** Compute a few numbers per chunk: a wind estimate from modal
   optical flow; residual variance per radial band, for seeing, SNR and PyWFS optical gain.
3. **Quantize with `gric-cluster`.** Feed the descriptor stream to the milk FPS daemon
   (`milk-fpsexec-gric-cluster`, output `<out>_assign`) or the C API
   (`gric_cluster_feed_frame`). Keep one Gram accumulator (X^T X, X^T Y) per anchor.
4. **Refit.** Compute `G = sum_k w_k G_k` with `w_k = kappa + (1-kappa) K(|z_k - z_now|)`,
   kappa ~ 0.1, then one Cholesky solve as now. The apply side is unchanged.

## 7. Not tested / open questions

- **PyWFS optical-gain nonlinearity.** This is the most physical source of local nonlinearity,
  and it argues for a seeing/OG descriptor, but the toy has a linear sensor.
- **Closed loop.** The study used open-loop modes, not pseudo-open-loop (PSOL) reconstruction
  with DM dynamics.
- **Real or cacaosim telemetry.** None of these numbers have been checked on it. Suggested next
  test: cacaosim AO3k run with a scripted wind change, PSOL telemetry saved for several
  minutes, then rerun `mem.py`-style chunk-Gram comparisons. See
  `../../scripts/run-ao3k-scexao.sh`. Pace the simulation slowly enough that no frames are
  dropped: the printed `d(pha)` and `d(wfs2)` counters must be equal.
- Faster descriptor response at regime switches, e.g. sub-second chunks or a hysteresis-free
  kernel.
- Ridge toward ZOH, instead of toward zero, combined with weighting.
