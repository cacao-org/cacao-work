# Other loop frequencies and clock offsets

Toy-model analysis, 2026-11-20. Not part of `../REPORT.md`. The real-simulator side of the
same question is in `../../realsim/README.md` ("Arbitrary frame clocks").

## Question

The first real-telemetry test used WFS A at 1 kHz, WFS B at 2 kHz and frames that end
together. The user asked that the method work for arbitrary frequencies of the two loops.
Does it?

## Answer

The estimator itself does not depend on the frame rates. The step that puts `A`, `B` and the
DM2 command on one timeline does. With the alignment rule below, 17 of 18 clock configurations
are within 3% on the toy model (20 s, 12 runs each); the exception is a slow WFS A with a fast
WFS B and offset clocks (-4.2%).

**The rule** (implemented in `realsim/realsim_est.py: choose_windows`, and in
`code/estfreq.py: rule_frames` for the toy):

1. Windows are runs of whole WFS B frames, so `B` and the DM2 command are plain means.
2. Take the shortest run that holds two frames of each sensor. WFS A frames are cut by the
   window edges: weight them by overlap and start the instruments at lag 3.
3. Unless a run no longer than that, with at least two WFS B frames and one WFS A frame, has
   all its edges on WFS A frame edges. Then use the shortest such run and start at lag 2.

## The toy model for this question

`code/simfreq.py`: the two-stage loop of `sim.py` (integrator control only) on a 24 kHz grid,
so that many frame-rate pairs are integer numbers of ticks. Parameters: ticks per WFS A and
WFS B frame, and an offset between the two frame clocks. Each loop keeps a gain of 0.35 per own
frame, a leak of 0.98 and a delay of two own frames. Read noise scales as the square root of
the frame rate (a shorter exposure is noisier). `code/estfreq.py` holds the alignment variants
and the estimator; the DM2 position is rebuilt exactly from the logged commands.

Numbers: bias of the median over modes 4-39 (standard error over 12 runs) / per-mode median
error, in percent of the true gain.

## 1. The original recipe is exact only for nested, aligned clocks

`freq_scan.py`, 5 s windows. "As tested": the timeline is the frames of the slower sensor, and
the other sensor is weighted by overlap.

| WFS A / WFS B | As tested | Timeline of the faster sensor |
| :--- | :---: | :---: |
| 1 kHz / 2 kHz | +0.4 (0.3) / 4.1 | +18.2 (0.5) / 18.2 |
| 1 kHz / 3 kHz | -0.7 (0.4) / 5.0 | -71.2 (1.0) / 71.2 |
| 1 kHz / 4 kHz | -0.7 (0.4) / 6.0 | -161.1 (2.5) / 161.1 |
| 500 Hz / 2 kHz | -1.8 (0.7) / 7.7 | -146.5 (1.4) / 146.5 |
| 2 kHz / 1 kHz (A faster) | +0.3 (0.5) / 7.0 | +27.6 (1.0) / 27.6 |
| 1 kHz / 1 kHz | +6.1 (1.1) / 12.8 | same |
| 2 kHz / 2 kHz | +3.6 (0.7) / 11.1 | same |
| 1 kHz / 1.5 kHz | +3.3 (0.4) / 5.3 | +44.8 (0.7) / 44.8 |
| 1 kHz / 1.6 kHz | +2.2 (0.3) / 4.5 | +45.4 (0.7) / 45.4 |
| 1 kHz / 2.4 kHz | -1.5 (0.3) / 4.5 | -5.8 (0.5) / 10.2 |
| 1.2 kHz / 2 kHz | +0.9 (0.3) / 3.6 | +46.2 (0.4) / 46.2 |
| 1 kHz / 2 kHz, B clock late by 1/8 A frame | -1.3 (0.4) / 4.0 | +20.1 (0.8) / 20.1 |
| 1 kHz / 2 kHz, B clock late by 1/4 A frame | -1.6 (0.4) / 3.9 | +27.2 (0.7) / 27.2 |
| 1 kHz / 1 kHz, B clock late by 1/2 frame | +60.0 (0.6) / 60.0 | +150.2 (0.5) / 150.2 |

- Integer rate ratios with aligned clocks are fine (1:2, 1:3, 1:4, 2:1).
- **Never use a timeline finer than the slower sensor.** A frame of the slower sensor then
  spreads over several samples and the estimate is meaningless.
- Equal rates converge slowly; near-equal rates and offset clocks are biased, up to +60%. At
  20 s (`freq_scan3.py`) the same recipe gives +30.5% and +59.4% for equal rates with a quarter
  and half frame offset, +15.8% for 1 kHz / 1.2 kHz and +19.6% for 1.2 kHz / 1 kHz.

In this table the toy still weights the cut sensor by overlap and uses the exact DM2 position.
The original recipe on real telemetry does less: it pairs each WFS A frame with two whole
WFS B frames. For 1 kHz / 2 kHz with the WFS B clock a quarter of a WFS A frame late
(`freq_fixed_recipe.py`, 20 s) that reads -8.3 (0.2)%, against -0.1% with aligned clocks. The
real simulator gave -3.3% against +2.7% (6 points lower).

## 2. Towards the rule

`freq_scan2.py` and `freq_scan3.py` (20 s): windows of N frames of the slower sensor.

- N = 2 brings all 14 cases within 5.6%; N = 3 is too long when the slow loop is at 500 Hz
  (-14.8%).
- If window edges cut WFS A frames, the instruments must start at lag 3: a cut frame puts its
  noise in two neighbouring windows.

`freq_scan4.py` (20 s): windows made of whole WFS B frames, at least 1, 2 or 3 WFS A frames
long. Largest bias over the 14 cases: 20.7% (1 frame), **2.9% (2 frames)**, 8.1% (3 frames).
With whole WFS B frames nothing has to be assumed about the DM2 motion inside a frame, which is
what makes the method usable on real telemetry: the DM2 response is only needed frame by frame,
and that is what a measured step response gives.

Why equal rates are harder with one-frame windows (`freq_probe.py`, 1 kHz / 1 kHz): the bias
shrinks only slowly with the window (+6.1% at 5 s, +2.6% at 20 s, +1.0% at 40 s) and the
per-mode error is 7.3% at 20 s. Two-frame windows give +0.3 (0.3) / 3.1 at 20 s.

## 3. The rule on 18 clock configurations

`freq_scan5.py`, 20 s. "Window" is the number of WFS B frames per window chosen by the rule,
"cut" when WFS A frames are cut. "Usable" is the part of the DM2 motion that the instruments
separate from the WFS A signal, in percent of its variance (see `why_differences.md`).

| WFS A / WFS B | Window | Bias (per mode) | Usable |
| :--- | :---: | :---: | ---: |
| 1 kHz / 2 kHz | 2 | -0.1 (0.1) / 1.8 | 21.2 |
| 1 kHz / 3 kHz | 3 | +0.3 (0.2) / 2.2 | 11.2 |
| 500 Hz / 2 kHz | 4 | +0.0 (0.3) / 3.8 | 7.8 |
| 2 kHz / 1 kHz (A faster) | 2 | +0.7 (0.3) / 3.5 | 27.1 |
| 1 kHz / 1 kHz | 2 | +0.3 (0.3) / 3.1 | 16.0 |
| 1 kHz / 1 kHz, offset 1/4 frame | 2, cut | +2.9 (0.3) / 3.7 | 13.6 |
| 1 kHz / 1 kHz, offset 1/2 frame | 2, cut | +2.5 (0.3) / 3.5 | 13.9 |
| 1 kHz / 2 kHz, offset 1/4 A frame | 4, cut | +0.8 (0.1) / 1.7 | 23.0 |
| 1 kHz / 1.5 kHz | 3 | +0.1 (0.1) / 1.6 | 31.4 |
| 1 kHz / 1.846 kHz (24:13 ticks) | 4, cut | +0.3 (0.1) / 1.7 | 28.5 |
| 1 kHz / 1.2 kHz | 3, cut | +0.6 (0.1) / 2.0 | 28.8 |
| 1.2 kHz / 1 kHz (A faster) | 2, cut | +1.9 (0.3) / 4.0 | 8.0 |
| 1.846 kHz / 1 kHz (A faster, 13:24) | 2, cut | -0.0 (0.4) / 3.4 | 20.5 |
| 1 kHz / 2.182 kHz (24:11), offset | 5, cut | +0.4 (0.2) / 1.9 | 22.1 |
| 500 Hz / 2 kHz, offset 1/8 A frame | 8, cut | **-4.2 (0.5) / 8.1** | 1.5 |
| 500 Hz / 1 kHz, offset 1/4 A frame | 4, cut | +0.0 (0.3) / 3.9 | 7.1 |
| 500 Hz / 1.2 kHz | 5, cut | -0.3 (0.2) / 4.5 | 5.1 |
| 2 kHz / 1 kHz (A faster), offset 1/2 A frame | 2, cut | -0.7 (0.3) / 3.1 | 23.1 |

The failing case has a usable fraction of 1.5%: with a 500 Hz WFS A and a 2 kHz WFS B the
window is 4 ms, during which the fast stage-2 loop follows the disturbance closely, and the
first admissible instrument is 12 ms old. `realsim_est.py` flags a usable fraction below 5%.

### Variants of the instruments

Same scan; largest bias over the 18 cases, and the cases where the variant matters.

| Variant | Largest bias | 500 Hz / 2 kHz, offset | 1 kHz / 1 kHz | 1 kHz / 2 kHz, offset |
| :--- | :---: | :---: | :---: | :---: |
| Window lags (the rule) | 4.2% | -4.2 / 8.1 | +0.3 / 3.1 | +0.8 / 1.7 |
| Window lags, linear inside cut frames | 4.9% | -4.9 / 8.2 | +0.3 / 3.1 | -0.3 / 1.7 |
| Frame lags | 3.0% | +2.8 / 5.0 | +1.6 / 7.5 | +2.1 / 2.3 |
| Frame lags, linear | 4.8% | +2.8 / 5.1 | +1.6 / 7.5 | +1.5 / 1.9 |
| Frame lags, 3 frames of each sensor | 5.0% | -3.3 / 9.1 | +1.6 / 7.5 | +0.3 / 1.9 |

- **Window lags**: instruments are differenced `psi` of earlier windows (lag 2 or 3 onwards).
- **Frame lags**: the 8 most recent single-frame differences of `psi` whose WFS A frames touch
  neither of the two windows being differenced. Identical to window lags when a window is one
  WFS A frame.
- **Linear**: a cut WFS A frame is taken as linear in time, with the slope from its two
  neighbours, instead of constant.

No variant wins everywhere. Frame lags rescue the slow-A / fast-B case and are noisier when the
two rates are equal or close (per-mode error 5 to 9% against 3 to 4%).

## 4. What the real simulator added

From `../../realsim/README.md`, on real telemetry at 1 kHz / 2 kHz:

- With the WFS B clock 250 us late the rule reads +1.9%, against +2.7% with aligned clocks
  (0.8 points lower; the toy predicted 0.9 points higher, both within the noise).
- When frames are cut the window has no slack: one WFS A frame is too short (+6 to +14%), and
  2.5 WFS A frames or more is too long (-3 to -25%, usable fraction 1 to 5%). The toy shows the
  second effect only in the 500 Hz / 2 kHz case.
- Frame lags remove that collapse but read 1 to 3 points higher at the rule's window.

## Limits

- Everything in this note except section 4 is toy only. The bench runs at 1 kHz / 2 kHz; no
  other rate pair has been run on the real simulator.
- Drifting clocks were not simulated. The 24:13 and 24:11 tick ratios are the nearest thing:
  the window edges cut WFS A frames at a different place every time.
- In the toy both loops scale with their own frame rate (gain, delay, noise). A real system
  with other latencies needs its own check.
- The toy knows the DM2 position exactly. On real telemetry the DM2 response per WFS B frame
  must be measured, and the clock offset known to a few tens of microseconds.

## Files

`code/simfreq.py`, `estfreq.py`, `freq_scan.py` to `freq_scan5.py`, `freq_probe.py`,
`freq_fixed_recipe.py`, with `.log` (text tables) and `.json` outputs. The scans take 1 to 10
minutes on 20 cores.
