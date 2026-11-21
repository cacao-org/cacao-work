#!/usr/bin/env bash
# Scan of stage-2 loop states under one calibration of the stock AO3k + SCExAO simulation:
# for each state, wavefront statistics and a stage-2 self-response cube (the optical gain).
#
# The script that runs is assembled here on every call:
#   1. benches/ao3k_scexao/sim-ao3k-scexao.milk up to the marker line MARK, unchanged: bench
#      deployment, calibration of the three stages, calibration selfRM, turbulence on, stage 1
#      and stage 2 closed;
#   2. og-states-tail.part, which replaces the rest of the stock script (see its header).
# The marker is searched by text, so the stock script may grow above it. If the marker is gone
# the wrapper stops: find where the stock script finishes closing the loops and update MARK.
#
# Isolation is the same as scripts/run-ao3k-scexao.sh: a private /dev/shm/cacao_work_ogs_<pid>
# sandbox, removed on exit. Nothing is written to /milk/shm.
#
# usage: OGS_STATES=... run-og-states.sh [--assemble-only] <stock sim-ao3k-scexao.milk options>
#   --assemble-only   write the assembled script, print its path and stop (no simulation)
# The assembled script goes to $CALIB2WFS1DM_WORK (default: <repo>/_work/calib2wfs1dm), which
# is ignored by git. Give the run its output directory with the stock --outdir option.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../../.." && pwd)"
STOCK="${ROOT}/benches/ao3k_scexao/sim-ao3k-scexao.milk"
MARK='# Throttle master turbulence clock'
GEN_DIR="${CALIB2WFS1DM_WORK:-${ROOT}/_work/calib2wfs1dm}"
GEN="${GEN_DIR}/sim-og-states.milk"

if [[ ! -f "${ROOT}/env.sh" || ! -f "${STOCK}" ]]; then
    echo "run-og-states.sh: cannot find the cacao-work root from ${HERE}" >&2
    exit 1
fi
cut_line="$(grep -n -m1 -F "${MARK}" "${STOCK}" | cut -d: -f1 || true)"
if [[ -z "${cut_line}" ]]; then
    echo "run-og-states.sh: marker '${MARK}' not found in ${STOCK}." >&2
    echo "  The stock script changed: update MARK to the line that follows loop closure." >&2
    exit 1
fi
mkdir -p "${GEN_DIR}"
head -n "$(( cut_line - 1 ))" "${STOCK}" > "${GEN}"
cat "${HERE}/og-states-tail.part" >> "${GEN}"
chmod +x "${GEN}"
if [[ "${1:-}" == "--assemble-only" ]]; then
    echo "${GEN}"
    exit 0
fi

# The run ends with a compute report that draws figures, so the interpreter needs matplotlib
# as well as numpy and astropy. Keep PYTHON_BIN if it is set; otherwise take the first python3
# that has all three (on the original machine the default one lacked matplotlib).
if [[ -z "${PYTHON_BIN:-}" ]]; then
    for py in "$(command -v python3 || true)" /usr/bin/python3; do
        if [[ -n "${py}" ]] && "${py}" -c "import numpy, astropy, matplotlib" 2>/dev/null; then
            export PYTHON_BIN="${py}"
            break
        fi
    done
fi
# shellcheck source=../../../scripts/shm-sandbox.sh
source "${ROOT}/scripts/shm-sandbox.sh"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS=1

sandbox_init "ogs"
trap sandbox_cleanup EXIT

milk-script -q "${GEN}" "$@"
