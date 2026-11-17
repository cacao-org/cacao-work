#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Environment setup for integrated testing across milk, cacao, cacaosim, and
# AtmosphericTurbulenceSimul (milkatmturb). Source this file before running scripts
# or pytest: `source env.sh`

if [ -n "${BASH_SOURCE[0]:-}" ]; then
    _cacao_work_src="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    # shellcheck disable=SC2296
    _cacao_work_src="${(%):-%x}"
else
    _cacao_work_src="$0"
fi

export CACAO_WORK_ROOT
CACAO_WORK_ROOT="$(cd "$(dirname "${_cacao_work_src}")" && pwd)"
unset _cacao_work_src

_cacao_parent="$(cd "${CACAO_WORK_ROOT}/.." && pwd)"

_cacao_find_src_dir() {
    local name="$1"
    local cand
    for cand in \
        "${_cacao_parent}/${name}" \
        "${HOME}/src/${name}"; do
        if [ -d "${cand}" ]; then
            printf '%s\n' "${cand}"
            return 0
        fi
    done
    printf '%s\n' "${_cacao_parent}/${name}"
}

export MILK_SRC_DIR="${MILK_SRC_DIR:-$(_cacao_find_src_dir milk)}"
export CACAO_SRC_DIR="${CACAO_SRC_DIR:-$(_cacao_find_src_dir cacao)}"
export CACAOSIM_SRC_DIR="${CACAOSIM_SRC_DIR:-$(_cacao_find_src_dir cacaosim)}"
_atmturb_def="$(_cacao_find_src_dir AtmosphericTurbulenceSimul)"
export ATMTURB_SRC_DIR="${ATMTURB_SRC_DIR:-${_atmturb_def}}"
export OPTICSMAT_SRC_DIR="${OPTICSMAT_SRC_DIR:-$(_cacao_find_src_dir OpticsMaterials)}"
export WFPROP_SRC_DIR="${WFPROP_SRC_DIR:-$(_cacao_find_src_dir WFpropagate)}"
unset -f _cacao_find_src_dir
unset _cacao_parent _atmturb_def

if [ -z "${MILK_INSTALL_ROOT:-}" ]; then
    for _cand in "${MILK_SRC_DIR}"/_install/milk-*; do
        if [ -x "${_cand}/bin/milk-cli" ]; then
            MILK_INSTALL_ROOT="${_cand}"
        fi
    done
    unset _cand
    if [ -z "${MILK_INSTALL_ROOT:-}" ] && [ -x "${MILK_SRC_DIR}/_install/bin/milk-cli" ]; then
        MILK_INSTALL_ROOT="${MILK_SRC_DIR}/_install"
    elif [ -z "${MILK_INSTALL_ROOT:-}" ] &&
         [ -n "${MILK_INSTALLDIR:-}" ] && [ -x "${MILK_INSTALLDIR}/bin/milk-cli" ]; then
        MILK_INSTALL_ROOT="${MILK_INSTALLDIR}"
    elif [ -z "${MILK_INSTALL_ROOT:-}" ] &&
         [ -n "${MILK_ROOT:-}" ] && [ -x "${MILK_ROOT}/bin/milk-cli" ]; then
        MILK_INSTALL_ROOT="${MILK_ROOT}"
    elif [ -z "${MILK_INSTALL_ROOT:-}" ] && command -v milk-cli >/dev/null 2>&1; then
        _milk_bin="$(command -v milk-cli)"
        MILK_INSTALL_ROOT="$(cd "$(dirname "${_milk_bin}")/.." && pwd)"
        unset _milk_bin
    elif [ -z "${MILK_INSTALL_ROOT:-}" ]; then
        MILK_INSTALL_ROOT="${MILK_SRC_DIR}/_install"
    fi
fi
export MILK_INSTALL_ROOT
export MILK_INSTALLDIR="${MILK_INSTALL_ROOT}"
export MILK_ROOT="${MILK_INSTALL_ROOT}"

if [ -z "${PYTHON_BIN:-}" ]; then
    if command -v python3 >/dev/null 2>&1 &&
       python3 -c "import numpy, astropy" >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    else
        for _py in \
            "${CONDA_PREFIX:+${CONDA_PREFIX}/bin/python3}" \
            "${HOME}/miniforge3/bin/python3" \
            "${HOME}/mambaforge/bin/python3" \
            "${HOME}/miniconda3/bin/python3" \
            "${HOME}/anaconda3/bin/python3"; do
            if [ -n "${_py}" ] && [ -x "${_py}" ]; then
                PYTHON_BIN="${_py}"
                break
            fi
        done
        unset _py
    fi
    if [ -z "${PYTHON_BIN:-}" ]; then
        PYTHON_BIN="$(command -v python3)"
    fi
fi
export PYTHON_BIN

# Cap OpenMP/OpenBLAS thread pools & enable passive spin + GPU-local NUMA (overridable).
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_WAIT_POLICY="${OMP_WAIT_POLICY:-PASSIVE}"
export GOMP_SPINCOUNT="${GOMP_SPINCOUNT:-0}"
export MILK_OMP_WAIT_POLICY="${MILK_OMP_WAIT_POLICY:-PASSIVE}"
export MILK_NUMANODE="${MILK_NUMANODE:-auto}"

# Ensure tput calls inside cacao scripts do not fail under set -e when
# running in non-interactive shells (e.g. pytest, CI, TERM=dumb).
if [ -z "${TERM:-}" ] || [ "${TERM}" = "dumb" ]; then
    export TERM="xterm-256color"
fi

case ":${PATH}:" in
    *":${MILK_INSTALL_ROOT}/bin:"*) ;;
    *) export PATH="${MILK_INSTALL_ROOT}/bin:${PATH}" ;;
esac

case ":${PATH}:" in
    *":${CACAO_WORK_ROOT}/scripts:"*) ;;
    *) export PATH="${CACAO_WORK_ROOT}/scripts:${PATH}" ;;
esac

case ":${LD_LIBRARY_PATH:-}:" in
    *":${MILK_INSTALL_ROOT}/lib:"*) ;;
    *)
        if [ -n "${LD_LIBRARY_PATH:-}" ]; then
            export LD_LIBRARY_PATH="${MILK_INSTALL_ROOT}/lib:${LD_LIBRARY_PATH}"
        else
            export LD_LIBRARY_PATH="${MILK_INSTALL_ROOT}/lib"
        fi
        ;;
esac
