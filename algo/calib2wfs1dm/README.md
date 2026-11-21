# 2-WFS + 1-DM closed-loop calibration: algorithm study

Start here. This directory is the record of a study done on 2026-11-19 and 2026-11-20, written
so that someone else can pick it up. It answers one question: how to measure the gain between
DM2 and WFS B of the two-stage AO3k + SCExAO system (the WFS B optical gain) from ordinary
closed-loop telemetry, with nothing injected.

**Status: the experiments are finished and the method is chosen. Nothing is deployed.** All
code here is prototype Python. No shipped tool, bench script or report generator was changed.

## The problem

Stage 1 (AO3k) has WFS A at 1 kHz and DM1; stage 2 (SCExAO) has WFS B at 2 kHz and DM2;
stage 3 (LLOWFS) also drives DM2. The calibration model is

    B = Mab A + Mdb D + b0          A = Mba B - Mda_virt D + a0

with `A`, `B` the modal measurements of the two sensors and `D` the DM2 modal command.
`Mdb[i, i]` is the response of WFS B mode `i` to DM2 mode `i`; divided by the same response
without turbulence it is the optical gain of the pyramid. The shipped tool for this fit is
`mlt.calib2wfs1dm` / `mlt.sysid` in `milk-mltools` (binary `milk-mlt-calib2wfs1dm`), and
`scripts/build-calib-2wfs1dm-report.py` builds the published report from its output.

## What was found

1. **The shipped fit is biased in closed loop.** Any regression of `B` on `(A, D)` returns a
   blend of the gain and of the inverse of the stage-2 controller, because `D` was computed
   from `B`. On simulator telemetry the shipped `W(z)` result is 22% low and plain least
   squares 92% low. The agreement with a probed reference seen in one earlier run is
   compatible with opposite biases cancelling.
2. **An estimator that works: "differenced lagged-A".** Per WFS B mode, first differences in
   time and two-stage least squares, with earlier WFS A measurements as instruments. On
   simulator telemetry with both loops closed at nominal gains: +2.7% against a probed
   reference, 4.4% per mode, from 20 s. See `ALGORITHM.md`.
3. **One window, both loops closed.** A two-step scheme (stage 2 open, then closed) returns
   the WFS B gain of the first step, and that gain is 5% lower with stage 2 open (a third lower
   for tip and tilt). Lowering the stage-2 gain makes the estimate worse.
4. **It does not depend on the two frame clocks, provided the alignment step is done from
   exposure times.** With the WFS B clock 250 us late: +1.9% (the first, clock-specific recipe:
   -3.3%). Other frame rates were tested on the toy model only.

| Claim | Evidence | Where |
| :--- | :--- | :--- |
| Closed-loop regression is a blend | closed form, toy model (700 runs) | `toy/REPORT.md` 3 |
| Shipped `W(z)` -22%, least squares -92% | simulator, 20 s | `realsim/README.md` |
| Differenced lagged-A +2.7% (4.4% per mode) | simulator, 20 s, probed | `realsim/README.md` |
| Why differences and not levels | toy model | `toy/notes/why_differences.md` |
| WFS B gain 5% lower with stage 2 open | simulator, probed | `og_vs_stage2_state/README.md` |
| Two-step and low-gain schemes are not better | toy model | `toy/notes/two_step_calibration.md` |
| Offset clocks: +1.9% with the window rule | simulator, 20 s | `realsim/README.md` |
| Other frame rates: 17 of 18 cases within 3% | toy model only | `toy/notes/loop_frequencies.md` |

**Not established:** tip and tilt (18% and 10% low); the LLOWFS-closed case (the simulation
bursts and its probed reference becomes invalid); predictive control, other seeing or star
brightness; `Mda_virt` on the simulator; any frame-rate pair other than 1 kHz / 2 kHz on the
simulator; anything on the real instrument.

## Decisions already taken by the user

Do not reopen these without asking.

- The estimator must be passive: no DM2 dither, no LOWFS injection (2026-11-19).
- One calibration window with both loops closed, using differences (2026-11-20).
- It must work for arbitrary frequencies of the two loops (2026-11-20).
- **Deployment uses the milk framework (calc, JIT, compute units) and existing milk plugins
  such as `milk-mltools`, not new custom Python scripts** (2026-11-20). The Python here stays
  as the experiment record and as the numerical reference for a port.
- The work so far was planning and experimentation. Changing `milk-mltools`, the simulator,
  the loop scripts or the report generator needs an explicit request.

## Layout

| Path | Content |
| :--- | :--- |
| `ALGORITHM.md` | the estimator, specified for a port; reference values |
| `toy/` | toy-model study: `REPORT.md`, three notes, code and results (`toy/README.md`) |
| `og_vs_stage2_state/` | WFS B optical gain versus the state of the stage-2 loop, simulator |
| `realsim/` | the estimators on simulator telemetry; the clock-general alignment |
| `realsim/results/` | small per-window result files |

Related tracked code that this study did not change: `scripts/studies/calib_2wfs1dm/` and
`scripts/build-calib-2wfs1dm-report.py` (the published report, built on the shipped tool),
`tests/test_07_calib_2wfs1dm.py`, and `benches/ao3k_scexao/` (the simulation that the two
wrappers here run).

## Data that is not in git

Telemetry, self-response cubes and response matrices (14 GB) are not in git. On the machine
where the study was done they are in the ignored `_work/` directory:
`_work/calib_2wfs1dm_realsim/run1`, `run2`, `run3` and `_work/og_vs_stage2_state/scan50`.
They may no longer exist. The commands in `realsim/README.md` and
`og_vs_stage2_state/README.md` regenerate them (8 to 66 minutes per run). What is in git is
enough to read every number quoted, and to run the toy model.

## First steps on a new machine

```bash
cd algo/calib2wfs1dm
python3 toy/code/selftest.py           # a few seconds, needs numpy and astropy
realsim/run-tlm.sh --assemble-only     # checks that the stock simulation script still fits
```

`selftest.py` must print `SELFTEST PASSED`. The second command writes the simulation script
that a run would execute, without running it.

## Things that cost time

- **Simulator pacing.** On the laptop used, the simulation must run with
  `--wall-rate 50 --calib-rate 100`. Faster, it drops frames without saying so. Check in every
  window that the turbulence and WFS B frame counters advanced equally (`d(pha) == d(wfs2)`).
- **One simulation at a time.** Two runs sharing the GPU corrupt each other's pacing.
- **Isolation.** The wrappers use a private `/dev/shm/cacao_work_*` sandbox, as `AGENTS.md`
  requires. Never point them at `/milk/shm`.
- **The wrappers follow the stock script.** `run-tlm.sh` and `run-og-states.sh` take
  `benches/ao3k_scexao/sim-ao3k-scexao.milk` up to a marker comment and append their own tail.
  If the stock script changes after that point, or renames what the tails use, they need care.
- **A probed reference can be wrong.** With the LLOWFS loop closed, one self-response cube read
  0.33 where the loop's own reaction in the same cube gave 0.69. Check every reference with
  `realsim/selfrm_dyn.py`. The runs behind the published report had the LLOWFS loop closed and
  were not checked this way.
- **The calibration self-response cube** came out corrupted in several runs on that laptop,
  including the one run with `--clock-skew-us`. The on-sky cube is the one used here.
- **BLAS threads.** Set `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1` before any
  toy script that starts worker processes.
- **Interpreter.** Analysis needs numpy and astropy; figures need matplotlib, which the project
  interpreter (`$PYTHON_BIN`) lacked on that laptop (`/usr/bin/python3` had it).
- **Clock offsets change more than the exposures.** With `--clock-skew-us` the simulator also
  applies DM2 commands later, so the DM2 timing weight must be re-measured (`ALGORITHM.md`).

## What to do next

In rough order of value:

1. Decide with the user when to move to deployment, and read the milk calc / JIT / compute-unit
   layer and `milk-mltools` (`sysid_unit.c`, `tlm_sync_unit.c`, `mltools.bash`) before
   designing the port. `ALGORITHM.md` lists what has to be matched.
2. Simulator test at a frame-rate pair that is not an integer ratio (for example WFS B at
   1.6 kHz). It needs a modified copy of the bench file and may meet rate assumptions in the
   loop scripts. `realsim_est.py: sim_frame_times` currently accepts integer ratios only.
3. LLOWFS closed, with a reference that passes `selfrm_dyn.py`; add the logged stage-3 command
   as a regressor (`realsim/realsim_lowfs.py`, `toy/code/iv_lowfs.py`).
4. Check the published report's runs with `selfrm_dyn.py`.
5. Tip and tilt.
6. `Mda_virt` on the simulator: `A` on `(B, D)` with earlier `A` as instruments (toy only so
   far), which needs a working stage-1 self-response reference.
7. Error bars (block bootstrap), other seeing and brightness, predictive control.

## State of this directory

Moved from `_work/` into git on 2026-11-20. Checked after the move, from this location:

- `realsim_est.py` on five windows: per-mode results identical to the stored ones, with both
  interpreters. The other `realsim/` scripts and `og_vs_stage2_state/reduce.py` run and give
  the stored numbers. Regenerated figures are pixel-identical, except
  `realsim_estimates.png`, redrawn with other panel titles and not replaced.
- `toy/code/selftest.py` passes. `figs.py` regenerates the four figures pixel-identically and
  `build_report.py` regenerates `toy/REPORT.md`.
- **Not re-run:** the two simulator wrappers end to end (the GPU was in use). Their assembled
  scripts differ from the ones that produced the runs only by one blank line and by two lines
  of help text that the stock script has gained since. Most toy scans were not re-run either;
  see `toy/README.md`.

The directory was requested as `algo/calib2fs1dm`; it is named `calib2wfs1dm` after the tool.

## Glossary

- **WFS A, WFS B**: the stage-1 (AO3k, near-infrared) and stage-2 (SCExAO, visible) pyramid
  wavefront sensors. `A`, `B`: their modal measurements.
- **`D`, `D_eff`**: the stage-2 modal DM command as logged, and as it acts during a WFS B
  exposure.
- **`psi`**: `A Mab0`, the incoming wavefront predicted from WFS A for each WFS B mode.
- **Optical gain**: sensitivity of a pyramid sensor relative to its calibration, which drops as
  the residual wavefront grows.
- **selfRM, self-response**: response of the stage-2 modes to small pokes of DM2 made with the
  loops running. Here it is the reference ("probed") that the passive estimates are compared
  with.
- **Instruments, 2SLS**: two-stage least squares. The regressors are first projected on
  signals (the instruments) that cannot be correlated with the equation error.
- **Lagged-A**: the instruments are earlier WFS A measurements.
- **Usable fraction**: the share of the DM2 motion that the instruments separate from the
  WFS A signal. Under 5% the estimate is not to be trusted.
- **LLOWFS, stage 3, ZPO**: the low-order loop that also drives DM2, and the zero-point offset
  it applies to WFS B.
