#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Thin sandbox wrapper for Subaru 8.2m AO3k + SCExAO two-stage simulation.
# Simulation, telemetry profiling, and report generation run natively via
# milk-script (benches/ao3k_scexao/sim-ao3k-scexao.milk), sysmon, cacaosim-ao-report,
# and milk-perf-report.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=shm-sandbox.sh
source "${SCRIPT_DIR}/shm-sandbox.sh"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS=1

for arg in "$@"; do
    if [[ "${arg}" == "-h" || "${arg}" == "--help" ]]; then
        exec milk-script -q "${CACAO_WORK_ROOT}/benches/ao3k_scexao/sim-ao3k-scexao.milk" --help
    fi
done

sandbox_init "ao3k"
trap sandbox_cleanup EXIT

chmod +x "${CACAO_WORK_ROOT}/benches/ao3k_scexao/sim-ao3k-scexao.milk"
milk-script -q "${CACAO_WORK_ROOT}/benches/ao3k_scexao/sim-ao3k-scexao.milk" "$@"
