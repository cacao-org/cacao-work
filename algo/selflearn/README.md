# Self-learning AO controller (lookup-table correction): feasibility study (handoff)

Start here. This directory holds a feasibility probe, done 2026-11-20, of a "self-learning"
AO controller proposed by the user. **Status: feasibility opinion given, one quick measurement
on simulator telemetry done, nothing designed or deployed.** Everything here is prototype
Python reading existing telemetry; no shipped tool was changed.

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

## Files

| Path | Content |
| :--- | :--- |
| `code/selflearn_probe.py` | Part A (recurrence) and Part B (linear vs lookup, controls) |
| `code/purelookup.py` | Pure kNN lookup grid (q PCA dims x k) vs linear and persistence |
| `code/lagcorr.py` | Lagged correlation of the whitened state (screen-recurrence check) |
| `logs/*.log` | Raw outputs of the runs quoted above |

`logs/probe_partB.log` is from the original run (2026-11-20, 4 BLAS threads, 213 s); the other
three logs were regenerated from the committed scripts the same day and reproduce the original
numbers exactly. The only later code edit is a line-length reflow of one print statement.

Run (from the repo root; `/usr/bin/python3` has numpy + astropy; cap BLAS threads if the
machine is busy, e.g. `OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4`):

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
