# Differenced lagged-A estimator: specification

What to implement, written for a port. The reference implementation is
`realsim/realsim_est.py` (functions named below); `toy/code/estfreq.py` is an independent
second implementation, and `toy/code/selftest.py` checks one against the other.

## Purpose

From closed-loop telemetry of the two-stage system, with nothing injected, estimate for each
WFS B mode `i` the gain `g_i = Mdb[i, i]` with which a DM2 modal command appears in the WFS B
modal measurement. Normalised by the same response without turbulence, it is the WFS B optical
gain.

Per mode the model is

    B_i = c_i psi_i + g_i D_i + e_i        psi = A Mab0

- `A`: WFS A (stage 1) modal measurements; `psi` is the incoming wavefront as WFS A predicts it
  for WFS B mode `i`.
- `D`: DM2 modal command as it acts during the WFS B exposure.
- `e`: everything else (WFS B noise, what WFS A does not see).

Least squares on this model fails in closed loop: `D` was computed from `B`. The estimator uses
instead the DM2 motion that is driven by what WFS A measured earlier.

## Inputs

| Input | Content | In the simulator telemetry |
| :--- | :--- | :--- |
| `A` | WFS A modal values per frame, leading 60 modes | stream `aol1_modevalWFS` |
| `B` | WFS B modal values per frame, 40 modes | stream `aol2_modevalWFS` |
| `D` | stage-2 modal DM command per frame, 40 modes | stream `aol2_modevalDM` |
| exposure times | end time and length of every WFS A and WFS B exposure | see "Clocks" |
| DM2 timing | weights of the DM2 step response, per WFS B frame | self-response cube |
| `g_start` | rough starting gain per mode; the result does not depend on it | shipped tool |

`B` and `D` must be in the same modal basis (the stage-2 control modes). The stage-2 controller
of the bench obeys `D[k] = 0.98 D[k-1] - gain B[k]`, checked on the telemetry (correlation
-1.0000), which fixes which command belongs to which WFS B frame.

Telemetry files: one FITS cube `(frames, 1, modes)` and one text file per stream and chunk,
written by `milk-fpsexec-mem-streamFITSlog`. In the text file, column 4 is the log time and
column 6 the stream counter (`load_stream`). **Counters must be consecutive**: a dropped frame
breaks the frame association, and the loader refuses the window.

## Steps

### 1. DM2 command as it acts (`acting_command`)

    D_eff[k] = sum over j of h_j D[k - j]

`D[k]` is the command computed from WFS B frame `k`; `h_j` are the increments of the DM2 step
response sampled per WFS B frame. On this bench `h_2 = w`, `h_3 = 1 - w` with `w = 0.883`: the
command computed from frame `k-2` becomes the DM2 target at the start of frame `k` (the 500 us
DM2 delay), and the 60 us servo lag takes the rest. `w` is the ratio of the self-response at
lags 3 and 4.

Re-measure `h` whenever the timing changes. With the WFS B clock offset by 250 us the simulator
gives `w = 0.386`, and keeping 0.883 costs +16%.

### 2. Clocks (`sim_frame_times`)

The alignment needs the time at which every exposure ends, for both sensors, on one clock.
Both clocks are regular, so each is `counter x period`; the unknown is their relative phase.

In the simulator the phase comes from its clock model: WFS A frames end on a WFS B period
boundary, and with a WFS B clock offset `s` the last WFS B frame logged before a WFS A frame
ended `(T_B - s) mod T_B` before it. This function is the only simulator-specific step. A real
system must supply hardware timestamps. The phase has to be right to a few tens of
microseconds: 125 us of error moves the result by about 4%. `realsim/clock_check.py` measures a
shift from the telemetry (259 +- 3 us for a configured 250), but only relative to a window
recorded with aligned clocks.

### 3. Common timeline (`choose_windows`, `align_frames`, `overlap_average`)

Windows are runs of whole WFS B frames. `B` and `D_eff` over a window are plain means.
`A` over a window is the mean of the WFS A frames it overlaps, weighted by the overlap.

Window length, in WFS B frames:

- `n_cut`: the fewest frames that hold two frames of each sensor.
- `n_exact`: the fewest frames, at least two and at least one WFS A frame long, for which every
  window edge falls on a WFS A frame edge.
- Use `n_exact` if it exists and is not larger than `n_cut`: no WFS A frame is cut, first
  instrument lag 2. Otherwise use `n_cut`: WFS A frames are cut, first instrument lag 3.

For 1 kHz / 2 kHz with aligned clocks this is one WFS A frame against its own two WFS B frames.
With a 250 us offset it is four WFS B frames (2 ms).

### 4. `psi` (`psi_from`)

Subtract the time mean from `A`, `B`, `D_eff` (window values). Then

    Mab0 = (A'A + 0.01 diag(A'A))^-1 A' (B - D_eff g_start)        psi = A Mab0

`g_start` multiplies column by column. Fit `Mab0` on the levels, not on differenced data.

### 5. Differences and two-stage least squares (`estimate`, `tsls`)

Take first differences in time of `B`, `psi`, `D_eff`: `dx[t] = x[t+1] - x[t]`. For each mode:

    y = dB_i[t]       X = [dpsi_i[t], dD_i[t]]       Z = [dpsi_i[t - l] for l = lag0 .. lag0 + 7]
    Xh = Z (Z'Z)^-1 Z' X          (c_i, g_i) = (Xh' X)^-1 Xh' y

Lag 1 is never valid after differencing: it shares a WFS A frame with the current difference.

### 6. Diagnostic: the usable fraction

With `ph`, `dh` the two columns of `Xh`:

    usable_i = | dh - ph (ph.dh) / (ph.ph) |^2 / | dD_i |^2

This is the part of the DM2 motion that the instruments predict and that is not a copy of the
predicted `psi`. Every flaw of the instruments is divided by it. Values seen: 15 to 19% when
the estimate is good, under 5% whenever it was biased. The script prints the median over modes
and flags it below 5%.

## Fixed choices and how much they matter

Measured on the nominal real-telemetry window (`realsim/README.md`), where the result is +2.7%
(4.4% per mode):

| Choice | Value | Alternatives tried |
| :--- | :--- | :--- |
| Instrument lags | 2 to 9 | 2-17: +0.7% (2.8%); 3-10: +2.1%; 2-5: +4.5%; 1-8: +60% (invalid) |
| Ridge on `Mab0` | 0.01, relative | 10 times smaller or larger: +2.7 / +2.3% |
| WFS A modes | 60 | 40: +3.2%; 100: +1.7% |
| DM2 timing | measured `w` | all weight at lag 2: -1.1% |
| Starting gain | shipped tool | 0.5, 1, 1.5 times the reference: +1.9 / +2.8 / +2.9% |
| Telemetry length | 20 s | 10 s halves: +2.4, +1.9%; 5 s quarters: +0.9 to +6.0% |
| Inside cut frames | constant | linear: within 2 points, not clearly better |

## When it fails

- **Usable fraction below 5%**: windows too long, or instruments too old. With cut frames the
  window must be about two WFS A frames, no shorter (+6 to +14%) and no longer (-3 to -25%).
- **No noise in WFS A** (toy): the excitation is WFS A noise turned into wavefront by DM1.
  In the toy the estimate holds within 4% down to one sixteenth of the reference noise and
  fails with none at all.
- **Stage-2 gain well below nominal**: +7.3% (12% per mode) at a quarter of the gain.
- **Wrong clock phase or wrong DM2 timing**: see steps 1 and 2.
- **Tip and tilt** are not recovered (18% and 10% low on the nominal window).
- **Stage 3 (LLOWFS) closed**: in the toy the logged stage-3 command must be added as a
  regressor for the low-order modes. On the simulator this case is not cleanly tested.

## Not implemented

- Error bars. A block bootstrap over time would give them at negligible cost.
- Pooling modes through a smooth gain-versus-mode curve.
- `Mda_virt`: in the toy, `A` on `(B, D)` with `A` at lags 1-8 as instruments is within 0.5%
  (2 to 3.5% per mode) where the shipped joint fit is 8 to 16% low. Untested on the simulator.

## Reference values for a port

Without the simulator: `python3 toy/code/selftest.py` (a few seconds). It runs toy data through
both implementations. Recorded values (seed 300, 5 s): -0.49% for aligned clocks and -0.74% with
the WFS B clock 250 us late; the two implementations agree within 0.1 points.

With the telemetry of the runs (not in git, see `README.md`), bias of the median over modes
2-39 against the probed reference, and per-mode median error:

| Run, window | Options | Differenced lagged-A | Other estimators |
| :--- | :--- | :---: | :--- |
| `run1`, `lowfs_open` | none | +2.689% (4.358%) | tool -22.2, LS -92.5, LS diff +47.6, IV -1.6 |
| `run1`, `gain_quarter` | none | +7.335% (12.366%) | tool -42.7 |
| `run1`, `lowfs_closed` | `--ref-from run2:dbg_closed` | +1.037% (6.101%) | tool -25.9 |
| `run3`, `skew_open` | `--fixed` | -3.3% (5.9%) | |
| `run3`, `skew_open` | `--b-offset-us 250` | +1.9% (4.3%) | tool -18.7 |

Per-mode values are in `realsim/results/<run>/<window>/realsim_est*.json`: `ref` is the
reference per mode and each entry of `rows` has `ratio`, the estimate divided by the reference.

## Notes for the port into the milk framework

The user's direction (2026-11-20): deployment uses the milk framework (calc, JIT, compute
units) and existing plugins such as `milk-mltools`; no new Python on the deployed path.

- The shipped tool is `mlt.calib2wfs1dm` / `mlt.sysid` in `milk-mltools` (`sysid_unit.c`,
  `tlm_sync_unit.c`, `commands.d/mltools.bash`). `toy/REPORT.md` section 2 describes what it
  does: resampling of `B` and `D` on the WFS A timeline, a lag scan, AR(4) whitening, a ridge
  solve. Steps 3 to 5 above replace the whitening and the solve; the resampling must become
  the exposure-based alignment of step 3.
- Its command line as used in `realsim/tlm-tail.part`:
  `milk-mlt-calib2wfs1dm <telemetry dir> <out dir> aol1_modevalWFS aol2_modevalWFS`
  `aol2_modevalDM 60 40 40 auto auto 4 0.02 0.70 <selfRM calib> <selfRM on-sky>`.
  It writes `Mab.fits`, `Mdb.fits`, `mdb_diag.fits`, `Mda_virt.fits`, `og_selfrm.fits`,
  `lag_scan.txt` and `sysid_summary.txt`.
- The shipped tool works from the loggers' wall-clock timestamps. This prototype works from
  the stream counters and a clock model; on a paced simulation the wall clock is not the
  physical time.
- The calc and JIT layers of the framework were not examined for this study. Read them before
  designing the port.
