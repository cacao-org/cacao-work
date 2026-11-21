# Two-step and low-gain calibration

Toy-model analysis, 2026-11-19, plus one measurement on the real simulator. Not part of
`../REPORT.md`.

## Question

Should the calibration be done in two steps?

- Step 1: stage 1 closed, stage 2 open. DM2 does not move, so the WFS-A-to-WFS-B relation
  `Mab` can be fitted without any closed-loop problem.
- Step 2: stage 2 closed, `Mab` held fixed, fit the DM2-to-WFS-B gain `Mdb` and the
  DM2-to-WFS-A relation `Mda_virt`.

And would a hybrid be possible, with the stage-2 loop closed at a low gain?

## Answer

**No: use one window with both loops closed at their nominal gains.**

1. Holding `Mab` fixed is well conditioned, but the result is the WFS B gain **as it was in
   step 1**. A pyramid's optical gain depends on the residual, and on the real simulator the
   WFS B gain is 5.4% lower with stage 2 open (about 35% lower for tip and tilt).
2. Keeping only the shape of the step-1 `Mab` and fitting one scale per mode in step 2 removes
   that problem, but then the two-step scheme is no more accurate than the single window.
3. A single window at reduced stage-2 gain is worse than at nominal gain, not better.
4. `Mda_virt` needs neither a second step nor a low gain.

The user confirmed the single-window plan on 2026-11-20.

The one thing a two-step scheme can do that the single window cannot: it still works when
WFS A has no noise at all (see section 1). That would matter only for a very bright star and
a WFS B gain known to be the same in both steps.

Numbers below: bias of the median over modes 4-39 (standard error over 12 runs) / per-mode
median error, in percent of the true gain. Step 2 is a 5 s window; integrator control.

## 1. `Mab` held fixed

Step-2 estimators, all with `psi = A Mab1` and `Mab1` from step 1 (`twostep.py`,
`twostep_ivfix.py`):

- **fixed**: regress `B - psi` on `D`, instruments `psi` at lags 1-8, undifferenced.
- **scale, differenced**: regress `B` on `(psi, D)`, so one free scale per mode on `psi`;
  first differences, instruments at lags 2-9. This is the recommended estimator with `psi`
  taken from step 1 instead of from the same window.

| Noise | Step 1 | Fixed, step 1 by LS | Fixed, step 1 by IV | Scale, differenced |
| :--- | :---: | :---: | :---: | :---: |
| reference | 5 s | -11.6 (0.3) / 12.5 | +8.7 (0.6) / 9.3 | +0.6 (0.3) / 4.2 |
| reference | 20 s | -11.3 (0.2) / 11.3 | +1.1 (0.2) / 3.2 | +0.6 (0.3) / 3.9 |
| / 4 | 20 s | -1.2 (0.2) / 3.2 | +1.6 (0.3) / 3.5 | +0.6 (0.3) / 3.7 |
| / 16 | 20 s | -0.1 (0.3) / 3.5 | +1.6 (0.2) / 3.6 | -0.6 (0.2) / 3.8 |
| no WFS A noise | 20 s | +0.0 (0.3) / 3.3 | +1.6 (0.2) / 3.5 | +15.4 (3.5) / 34.5 |

- A least-squares fit of `B` on `A` in step 1 is attenuated by WFS A noise (its diagonal is
  0.73 of the truth at the reference noise), which gives -11%. Fitting step 1 with WFS A at
  lags 1-2 as instruments removes that.
- With an instrumented step 1 of 20 s, "fixed" is within +1.1 to +1.6% at every noise level,
  including no WFS A noise. A 5 s step 1 is too short (+9 to +17%).

Now let the WFS B gain differ between the steps: 0.56 on average in step 1 instead of 0.70,
that is 20% lower (`og = "lower"`).

| Noise | Fixed, step 1 of 20 s by IV | Scale, differenced (step 1 of 5 s) |
| :--- | :---: | :---: |
| reference | -19.7 (0.2) / 19.7 | +0.4 (0.2) / 4.1 |
| / 4 | -20.1 (0.2) / 20.1 | +0.4 (0.3) / 4.4 |
| / 16 | -20.1 (0.2) / 20.1 | -1.0 (0.3) / 4.9 |
| no WFS A noise | -20.1 (0.2) / 20.1 | +12.6 (3.0) / 36.3 |

"Fixed" returns the step-1 gain exactly. This is the identity `Mdb = Mab x Mda_virt`: with
`Mab` frozen, the estimate can only be as right as `Mab` still is. The free-scale form gives
the same values as with an unchanged step-1 gain (+0.4, +0.4, -1.0, +12.7), because it uses
only the shape of `Mab1`.

For comparison, the single-window recipe on the same step-2 data gives +1.9 (0.4) / 4.3 at the
reference noise, -0.2 / 4.6 at a quarter of it and -2.5 / 4.9 at a sixteenth.

## 2. What the real simulator says about the gain difference

`../../og_vs_stage2_state/README.md`: WFS B self-response gain, relative to the nominal
stage-2 gain of 0.35 (0.6 arcsec seeing, mV = 6, LLOWFS open, leak 0.98, modes 2-39):

| Stage-2 state | Ratio to nominal | Tip/tilt |
| :--- | :---: | :---: |
| gain / 4 | 0.985 +- 0.001 | 0.96 +- 0.04 |
| gain / 10 | 0.973 +- 0.001 | 0.89 +- 0.05 |
| open, DM2 flat | 0.946 +- 0.001 | 0.65 +- 0.06 |
| nominal, repeated | 0.999 +- 0.001 | 1.03 +- 0.04 |

So a stage-2-open step 1 with `Mab` held fixed would read `Mdb` 5% low and tip/tilt a third
low. A step 1 at a quarter of the nominal gain would cost 1.5%. One seeing value and one star
brightness only.

## 3. A single window at reduced stage-2 gain

`lowgain.py`, one 5 s window, stage-2 leak 0.98 (the bench's value), reference noise:

| Gain | Residual | Differenced recipe | Undifferenced, true `Mab` | Shipped `W(z)` |
| :---: | :---: | :---: | :---: | :---: |
| 0.35 | 1.00 | +1.9 / 4.3 | +0.2 / 2.7 | +8.2 / 9.2 |
| 0.20 | 1.19 | +5.8 / 9.6 | +0.4 / 3.0 | +26.0 / 27.3 |
| 0.10 | 1.77 | +14.1 / 25.5 | -0.1 / 3.8 | +52.8 / 54.4 |
| 0.05 | 2.73 | +31.4 / 58.0 | -0.2 / 4.7 | +72.3 / 75.7 |
| 0.02 | 4.28 | +77.3 / 152 | -0.3 / 7.7 | +99.4 / 114 |

"Residual" is the wavefront left in the 40 stage-2 modes relative to the nominal loop.

- The recommended estimator degrades as soon as the gain is lowered. The real simulator
  agrees: at a quarter of the nominal gain it reads +7.3% (12% per mode) instead of +2.7% (4.4%).
- If `Mab` were known exactly, an undifferenced fit would be unbiased at every gain. The
  difficulty at low gain is entirely in getting `Mab` from the same window.
- Iterating in one window (refit `Mab0` with the last gains, undifferenced; `hybrid_iter.py`)
  converges to the wrong value: +3.5, +8.4, +14.2, +19.2 and +30.7% at gains 0.35, 0.20, 0.10,
  0.05 and 0.02, whatever the starting point. At a sixteenth of the noise it does not converge
  (-4 to -26% depending on the starting point, up to 17 points apart).

## 4. Two steps with a low-gain step 2

`twostep_t1.py`: step 1 with stage 2 open gives the shape of `Mab`; step 2 is 5 s with a
near-pure integrator (leak 0.999) at a low gain; undifferenced fit with one free scale per mode.

| Noise | Gain | Step 1 of 5 s | 20 s | 60 s |
| :--- | :---: | :---: | :---: | :---: |
| reference | 0.05 | +3.2 / 9.5 | -0.5 / 4.2 | -0.2 / 3.6 |
| reference | 0.02 | +3.6 / 9.7 | -0.4 / 4.3 | -0.3 / 3.8 |
| / 16 | 0.05 | -2.4 / 13.6 | -0.5 / 9.2 | -0.2 / 8.1 |
| / 16 | 0.02 | -1.8 / 10.1 | -0.4 / 6.4 | -0.2 / 5.6 |
| no WFS A noise | 0.05 | -3.4 / 14.7 | -1.0 / 9.3 | -0.3 / 8.6 |
| no WFS A noise | 0.02 | -2.0 / 10.2 | -0.7 / 6.2 | -0.2 / 5.7 |

A low gain moves the stage-2 crossover into the band where the turbulence has power, so the
fit no longer needs WFS A noise: it is unbiased even with a noise-free WFS A, at 4 to 9% per
mode. It needs a step 1 of 20 s or more, and at these gains the differenced form must not be
used (+21 to +56% at the reference noise). With the bench's leak of 0.98 instead of 0.999 the
per-mode error grows by a factor of 1.5 to 2.3 (`twostep_gain.py`, `lowgain.py`).

Together with "fixed" in section 1, this is a variant that would survive a noise-free WFS A.
It still measures the gain in a loop state that is not the operating one: at these gains the
residual is 1.1 to 1.9 times the nominal one with leak 0.999 and 2.7 to 4.3 times with leak
0.98, and section 2 says the optical gain moves with it.

## 5. `Mda_virt`

Per mode, percent of the true WFS A gain (`twostep.py`, `lowgain.py`):

| Noise | Shipped joint fit | Two-step, IV | Single window, IV |
| :--- | :---: | :---: | :---: |
| reference | -16.0 / 16.0 | +1.1 / 2.3 | +0.0 / 2.1 |
| / 4 | -8.0 / 8.0 | +1.2 / 2.3 | +0.2 / 2.3 |
| / 16 | -9.3 / 9.3 | +1.1 / 2.3 | +0.0 / 3.5 |
| no WFS A noise | -13.8 / 13.8 | +2.3 / 2.8 | +0.5 / 3.5 |

Two-step: regress `A - Mba1 B` on `D`, with `Mba1` from step 1. Single window: regress `A` on
`(B, D)`. Both use `A` at lags 1-8 as instruments. One closed-loop window at nominal gain is
enough. This has **not** been tried on the real simulator, where there is no reference
for `Mda_virt` (the stage-1 self-response cube came out empty on the test machine).

## Files

`code/twostep.py` (estimators and the two-step toy), `twostep_ivfix.py`, `twostep_t1.py`,
`twostep_gain.py`, `lowgain.py`, `hybrid_iter.py`, with their `.log` and `.json` outputs.
`twostep_t1.py` takes about 3 minutes on 20 cores, the others under 2.
