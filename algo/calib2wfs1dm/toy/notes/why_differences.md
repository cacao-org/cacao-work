# Why the estimator works on first differences

Toy-model analysis, 2026-11-19. It answers the question "why does the bias motivate working
with differences between consecutive measurements?" and is not part of `../REPORT.md`.

## Answer

In closed loop almost all of the variance of the two regressors sits at low temporal frequency,
where the DM2 command mirrors the disturbance and carries no information about the gain. The
information is above about 30 Hz. A fit on the signals as they are ("levels") therefore divides
a small, slowly varying error by a tiny usable signal, and any imperfection is amplified.
Differencing removes the low frequencies from both regressors before the fit. The usable part
of the DM2 motion goes from 0.2-2.5% of its variance to about 18%, and the result stops
depending on the noise level and on how the WFS A term was built.

## Terms

- Model per WFS B mode: `B = c psi + g D + e`, with `psi = A Mab0` the disturbance predicted
  from WFS A, `D` the DM2 command acting during the exposure, `g` the gain wanted.
- **Levels**: two-stage least squares (2SLS) of `B` on `(psi, D)`, instruments `psi` at lags
  1 to 8.
- **First difference**: the same on `x[t] - x[t-1]`, instruments differenced `psi` at lags 2
  to 9. Lag 1 is invalid: it shares a WFS A frame with the current difference.
- **Quasi-difference** `rho`: `x[t] - rho x[t-1]`; `rho = 0` is levels, `rho = 1` the first
  difference.
- **Usable part**: the variance of the DM2 command that the instruments predict and that is
  not a scaled copy of the instrument-predicted `psi`, as a percentage of the command variance.
  The estimator's error is every flaw of the instruments divided by this number.

All numbers: bias of the median over modes 4-39 (standard error over 12 runs) / per-mode median
error, in percent of the true gain; 5 s windows; integrator control unless stated.

## 1. Where the variance is, and where the information is

Share per temporal-frequency band (`diff_why.py`). "Strength" is the band's share of the
denominator of the estimator, that is of the identifying information.

Reference noise:

| Quantity | 0-2 Hz | 2-10 | 10-30 | 30-100 | 100-250 | 250-500 Hz |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `psi` variance, levels | 0.607 | 0.275 | 0.010 | 0.037 | 0.034 | 0.037 |
| `D` variance, levels | 0.631 | 0.268 | 0.022 | 0.051 | 0.026 | 0.003 |
| strength, levels | 0.003 | 0.004 | 0.002 | 0.328 | 0.618 | 0.046 |
| `psi` variance, differenced | 0.000 | 0.001 | 0.000 | 0.051 | 0.182 | 0.765 |
| `D` variance, differenced | 0.001 | 0.005 | 0.007 | 0.248 | 0.534 | 0.206 |
| strength, differenced | 0.000 | 0.002 | 0.001 | 0.365 | 0.604 | 0.027 |

WFS noise four times lower (a brighter star):

| Quantity | 0-2 Hz | 2-10 | 10-30 | 30-100 | 100-250 | 250-500 Hz |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `psi` variance, levels | 0.686 | 0.290 | 0.012 | 0.005 | 0.003 | 0.003 |
| `D` variance, levels | 0.680 | 0.295 | 0.017 | 0.005 | 0.002 | 0.000 |
| strength, levels | 0.018 | 0.040 | 0.018 | 0.257 | 0.598 | 0.070 |
| `D` variance, differenced | 0.018 | 0.064 | 0.042 | 0.248 | 0.454 | 0.174 |
| strength, differenced | 0.014 | 0.041 | 0.020 | 0.302 | 0.575 | 0.048 |

In levels, 88% (reference) to 98% (brighter star) of the variance of both regressors is below
10 Hz, and more than 90% of the information is above 30 Hz. Differencing moves the variance to
where the information is and leaves the information where it was.

The script also prints each band's contribution to the error. Those rows are not usable: the
term that comes from WFS A noise cancels only in the sum over bands, so the per-band values are
large numbers of opposite signs. Use the totals in the next sections.

## 2. The levels form degrades as the WFS noise drops; the differenced form does not

`diff_bright.py`. "Usable" in percent of the DM2 command variance; the last row has no
WFS A noise at all.

| Noise | Levels | Usable | `rho` = 0.9 | Usable | First difference | Usable |
| :--- | :---: | ---: | :---: | ---: | :---: | ---: |
| reference | +0.7 (0.4) / 4.8 | 2.5 | -0.0 (0.5) / 5.6 | 21.1 | +1.9 (0.4) / 4.3 | 18.4 |
| / 4 | -8.6 (0.7) / 8.9 | 0.21 | -5.2 (0.5) / 6.6 | 7.2 | -0.2 (0.5) / 4.6 | 18.1 |
| / 8 | -17.3 (2.1) / 20.7 | 0.14 | -3.8 (0.5) / 6.4 | 2.0 | -3.5 (0.3) / 4.5 | 21.5 |
| / 16 | -29.7 (2.0) / 33.6 | 0.16 | -4.7 (0.6) / 7.8 | 0.5 | -2.5 (0.4) / 4.9 | 11.5 |
| no A noise | -15.0 (1.8) / 27.5 | 0.13 | +6.3 (2.1) / 26.3 | 0.19 | +10.9 (1.6) / 29.2 | 0.27 |

With predictive control the pattern is the same (first difference: -0.2, -1.7, -3.8, -3.9%
down the same rows; levels: +1.0, -10.3, -17.1, -26.6%).

- The differenced form holds within 4% down to sixteen times less noise.
- With **no** WFS A noise neither form works. The method's excitation is WFS A noise turned
  into real wavefront by DM1; without it nothing separates `D` from `psi`.
- The quasi-difference must reach `rho = 1`: at four times less noise `rho = 0.9, 0.95, 0.98,
  0.99, 1` give -5.2, -5.0, -3.9, -2.2, -0.2%. A leaky difference leaves a bias.
- Least squares on differenced data, without instruments, is not an alternative: +23.8% at the
  reference noise (and +48% on real telemetry).

## 3. The levels form remembers its starting point; the differenced form does not

`psi` needs a first guess of the gain (`Mab0` is a fit of `B - g_start D` on `A`).
`diff_start.py`, starting from the shipped `W(z)` result or from 0.5, 1.0, 1.5 times the truth:

| Noise | Start | Levels | First difference |
| :--- | :--- | :---: | :---: |
| reference | tool | +0.7 (0.4) / 4.8 | +1.9 (0.4) / 4.3 |
| reference | 0.5 | +2.4 (0.2) / 3.6 | -0.8 (0.3) / 4.2 |
| reference | 1.0 | +3.5 (0.2) / 4.1 | +0.4 (0.4) / 4.2 |
| reference | 1.5 | +3.7 (0.2) / 4.3 | +0.7 (0.4) / 4.2 |
| / 4 | tool | -8.6 (0.7) / 8.9 | -0.2 (0.5) / 4.6 |
| / 4 | 0.5 | -13.4 (0.7) / 13.4 | -1.3 (0.4) / 4.3 |
| / 4 | 1.0 | -5.6 (0.5) / 6.0 | -1.2 (0.4) / 4.4 |
| / 4 | 1.5 | -3.9 (0.5) / 4.7 | -1.1 (0.4) / 4.4 |

A starting gain wrong by a factor of 3 moves the levels result by 9.5 points at low noise and
the differenced result by 0.2 points. The same test on real telemetry gave +1.9 / +2.8 / +2.9%.

## 4. How to build `psi`

`diff_psi.py`, differenced estimator, different ways of getting `Mab0`:

| Noise | Fit in levels (recipe) | True `Mab` | Fit on differenced data |
| :--- | :---: | :---: | :---: |
| reference | +1.9 (0.4) / 4.3 | +0.5 (0.3) / 3.8 | -8.1 (0.5) / 10.2 |
| / 4 | -0.2 (0.5) / 4.6 | +0.9 (0.3) / 3.6 | -8.0 (0.4) / 9.1 |
| / 8 | -3.5 (0.3) / 4.5 | -0.3 (0.2) / 2.7 | +1.0 (0.3) / 6.0 |
| / 16 | -2.5 (0.4) / 4.9 | -0.6 (0.2) / 3.5 | +2.7 (0.3) / 5.0 |

- Fit `Mab0` in levels, then difference. Fitting it on differenced data is worse.
- The -2.5 to -3.5% left at very low noise comes from the fitted `Mab0` (its cross terms
  between modes): with the true `Mab` it is within 1%.
- One refinement pass (refit `Mab0` with the first gains) changes nothing useful.

## Files

`code/diff_why.py`, `diff_start.py`, `diff_bright.py`, `diff_psi.py`, with their `.log` (text
tables) and `.json` outputs. Each runs in under a minute on 20 cores; set the BLAS threads to 1
first (see `../README.md`).
