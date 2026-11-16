# AGENTS.md — Developer & Agent Guide for `cacao-work`

## Purpose

`cacao-work` is the integrated AO loop testing repository wiring together four local development
projects into one shared install prefix (`$MILK_INSTALL_ROOT`, auto-detected by `env.sh`):

- `milk` (`$MILK_SRC_DIR`, e.g. `../milk`)
- `cacao` (`$CACAO_SRC_DIR`, e.g. `../cacao`)
- `cacaosim` (`$CACAOSIM_SRC_DIR`, e.g. `../cacaosim`)
- `AtmosphericTurbulenceSimul` / `milkatmturb` (`$ATMTURB_SRC_DIR`, e.g.
  `../AtmosphericTurbulenceSimul` or `~/src/AtmosphericTurbulenceSimul`, alongside
  `OpticsMaterials` and `WFpropagate`)

## Hard Rules

1. **Branch Safety**: **NEVER** checkout, commit to, or push to `dev` in `milk`, `cacao`, or
   `ImageStreamIO`. Work only on `feat/bash-engine` (or feature branches) in `milk`/`cacao`,
   and keep all local uncommitted edits intact.
2. **Local Build Prefix**: Always build and install against local checkouts targeting
   `$MILK_INSTALL_ROOT` (`$MILK_SRC_DIR/_install/milk-<version>`) before querying any remote repo.
3. **SHM Sandbox Isolation**: Never run integration tests against `/milk/shm`. Every test and
   headless run uses an isolated `/dev/shm/cacao_work_<tag>_<pid>` via `MILK_SHM_DIR` and
   `MILK_PROC_DIR` (plus `CACAOSIM_WORKDIR` and `MILK_ROOT`), torn down cleanly on exit.
4. **Python Environment**: Use the active Python 3 environment (`$PYTHON_BIN`, with `pytest`,
   `numpy`, and `astropy` pre-installed). Do not run `pip install` globally.
5. **Formatting**: Keep source, scripts, configs, and Markdown lines `<= 100` characters.
6. **`fpspipe` / No Terminal Multiplexer**: All bench deployment and AO loop workflows use
   `cacaosim-bench deploy/teardown`, `cacaoloop-*.milk` (`milk-script`), `milk-fps-*`, and
   `milk-stream-wait` with direct background execution.

## Common Commands

```bash
source env.sh
./scripts/build-all.sh --check-only            # verify binaries, libs, and commands.d modules
./scripts/build-all.sh                         # incremental CMake build + install across repos
./scripts/run-scao-headless.sh                 # fpspipe + cacaoloop-scao-pyr.milk validation
./scripts/run-scao-cacao-workflow.sh           # fpspipe init + cacao-aorun-* validation
./scripts/live-bench.sh start --calibrate --close
pytest -v                                      # run full integration test suite
```
