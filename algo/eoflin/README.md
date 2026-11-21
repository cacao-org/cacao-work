# eoflin: local-linearity study for EOF predictive control

Can EOF prediction be made "locally linear" by weighting past training samples by proximity,
possibly using `gric-cluster`? Synthetic-toy study from 2026-11-20.

- **Findings and analysis:** [REPORT.md](REPORT.md). Start here.
- **Code:** `code/` (numpy, single files).
- **Raw outputs behind every table in the report:** `logs/`.

One-line summary: state-proximity weighting does not help. Condition-proximity weighting (a
wind descriptor, quantized by `gric-cluster`, with a weight floor of about 0.1) gains 3-8%.
Training on all past data instead of the last 16 s gains about 2x and matters most. All of this
is toy data and still needs checking on real telemetry.

## Layout

| path | content |
|---|---|
| `code/gen.py` | synthetic 2-layer frozen-flow modal telemetry with switching wind regimes |
| `code/an.py` | first exploration (global / sliding / per-regime / proximity EOF); helpers |
| `code/mem.py` | causal online comparison, refit every 1 s from chunk Grams (main result) |
| `code/rg.py` | pooled vs regime-specific EOF at equal data |
| `code/smap.py` | literal proposal: S-map weighting by history-vector proximity |
| `code/lid.py` | nearest-neighbour ratio and local intrinsic dimension of history vectors |
| `code/xm.py` | per-mode AR vs full EOF vs number of lags (cross-mode coupling) |
| `code/sc.py` | sample complexity of plain EOF vs noise, ridge, normalization |
| `logs/*.log` | outputs quoted in REPORT.md |

`mem.py` imports `wind_descriptor` and `gric_anchors` from `an.py`; `sc.py` imports from
`an.py`.

## Reproduce

Requirements:

- `/usr/bin/python3` with numpy and scipy. The miniforge `$PYTHON_BIN` also works, since no
  plotting is used.
- `gric-cluster` and `gric-bin2ascii` on `PATH`, for `mem.py` and `an.py`. Built from
  `~/src/gric-cluster` and symlinked into `~/.local/bin`.
- Set `OMP_NUM_THREADS` and `OPENBLAS_NUM_THREADS` to a small number when running several jobs
  at once.

Datasets (`*.npz`, 30-120 MB each) are **not committed**. They are regenerated
deterministically from seeds. Run everything from `code/`, because `an.py` resolves data paths
relative to its own directory:

```bash
cd algo/eoflin/code
python3 gen.py st.npz 100 0 5                  # stationary wind
python3 gen.py sw.npz 240 1 3                  # 3 recurring winds, layers 60/40
python3 gen.py sw90.npz 240 1 3 0.35 kl 0.9    # same seed, one dominant layer 90/10
python3 mem.py sw.npz 100 0.6 8   > ../logs/mem_sw.log     # ~1 min
python3 mem.py sw90.npz 100 0.6 8 > ../logs/mem_sw90.log
python3 rg.py sw.npz 160 0.6 8                 # also 0.06, and sw90.npz -> logs/rg.log
python3 smap.py st.npz 70 0.6 2 150 raw        # ~20 min each; also norm, and sw.npz 160 .. 4
python3 lid.py st.npz 0.6
python3 xm.py st.npz 70 1.0,0.1
python3 sc.py st.npz 70 1.0,0.1,0.01
```

Generator arguments are
`gen.py <out> <seconds> <switch 0|1> <seed> [kcut=0.35] [kl|fourier] [layer-1 frac=0.6]`.
`mem.py` and `an.py` create `code/gric_<tag>/` scratch directories (git-ignored).

Notes for whoever picks this up:

- **Noise definitions differ between scripts.** `an.py`/`sc.py` scale noise by the *median*
  per-mode ZOH error. `mem.py`, `rg.py`, `smap.py`, `lid.py` and `xm.py` use the *mean*. The
  REPORT numbers use the mean-based definition.
- `an.py` picks the ridge on the test set (exploratory only). Do not quote its numbers as
  out-of-sample.
- Earlier exploratory logs from `an.py` and `sc.py` were not kept.

## Suggested next steps

1. Rerun the `mem.py` comparison on cacaosim PSOL telemetry with a scripted wind change, several
   minutes long. Check first whether memory beyond 16k frames helps on real data.
2. If it does, prototype an exponentially forgotten or chunk-ring Gram in `mkEOFPF` (C, cacao
   `feat/` branch, never `dev`).
3. Then add a descriptor stream and a `gric-cluster` anchor library with floor-weighted Gram
   blending (REPORT.md section 6).
4. Add a seeing/optical-gain descriptor once a PyWFS-nonlinear telemetry set exists.
