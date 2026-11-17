#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Incremental CMake build, install, and binary/library sanity checker across
# milk (+ cacao plugin), OpticsMaterials, WFpropagate, AtmosphericTurbulenceSimul,
# and cacaosim into MILK_INSTALL_ROOT.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"

CHECK_ONLY=0
JOBS="$(nproc)"
ONLY="all"

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --check-only              Verify installed binaries and libraries without building
  --jobs <N>                Parallel build jobs (default: ${JOBS})
  --only <component>        Build one of: all, milk, optics, atmturb, cacaosim
  -h, --help                Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check-only) CHECK_ONLY=1; shift ;;
        --jobs)       JOBS="$2"; shift 2 ;;
        --only)       ONLY="$2"; shift 2 ;;
        -h|--help)    usage; exit 0 ;;
        *)            echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

check_branch_safety() {
    local repo="$1"
    local name="$2"
    if [[ ! -d "${repo}/.git" && ! -f "${repo}/.git" ]]; then
        return 0
    fi
    local branch
    branch="$(git -C "${repo}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
    if [[ "${branch}" == "dev" ]]; then
        if [[ -n "$(git -C "${repo}" status --porcelain 2>/dev/null || true)" ]]; then
            echo "[build-all] ERROR: ${name} (${repo}) has dirty state on 'dev'" >&2
            exit 1
        fi
        echo "[build-all] WARNING: ${name} is on 'dev' (do not modify/push dev)" >&2
    fi
}

build_and_install_repo() {
    local src_dir="$1"
    local label="$2"
    local build_dir="${src_dir}/_build"
    if [[ ! -d "${src_dir}" ]]; then
        echo "[build-all] SKIP ${label}: source directory not found (${src_dir})"
        return 0
    fi
    if [[ ! -d "${build_dir}" ]]; then
        echo "[build-all] ERROR: ${label} missing CMake build dir ${build_dir}" >&2
        exit 1
    fi
    check_branch_safety "${src_dir}" "${label}"
    echo "[build-all] Building ${label} (-j${JOBS})..."
    cmake --build "${build_dir}" -j "${JOBS}"
    echo "[build-all] Installing ${label} -> ${MILK_INSTALL_ROOT}..."
    cmake --install "${build_dir}"
}

verify_install() {
    local bins=(
        milk-cli
        milk-script
        cacao-cli
        milk-fpsCTRL
        milk-fps-init
        milk-fps-set
        milk-fps-list
        milk-fps-info
        milk-fps-wait
        milk-fps-confstart
        milk-fps-confstep
        milk-fps-confstop
        milk-fps-runstart
        milk-fps-runstop
        milk-fps-rm
        milk-sysmon
        milk-perf-report
        milk-stream-link
        milk-stream-rm
        milk-stream-wait
        milk-fpsexec-iofits-loadfits
        milk-fpsexec-iofits-saveFITS
        milk-fpsexec-mem-streamave
        milk-fpsexec-mem-streamFITSlog
        milk-fpsexec-linalg-MVMextract
        milk-fpsexec-mlt-tlmindex
        milk-fpsexec-mlt-tlmload
        milk-fpsexec-mlt-tlmsync
        milk-fpsexec-mlt-tlmsave
        milk-fpsexec-mlt-aoopt
        milk-fpsexec-mlt-psfrecon
        milk-mlt-aoopt
        milk-mlt-psfrecon
        milk-mlt-aotlm
        cacao-setDMnolink
        cacao-mkDMpokemodes
        cacao-modalstatsTUI
        cacao-modalstatsTUI-bin
        cacao-aorun-000-dm
        cacao-aorun-025-acqWFS
        cacao-aorun-026-takeref
        cacao-aorun-020-mlat
        cacao-aorun-030-acqlinResp
        cacao-aorun-031-RMHdecode
        cacao-aorun-032-RMmkmask
        cacao-aorun-039-compstrCM
        cacao-aorun-050-wfs2cmval
        cacao-aorun-060-mfilt
        cacao-aorun-070-cmval2dm
        cacao-fpsexec-dmcomb
        cacao-fpsexec-cacaoiot-acquireWFS
        cacao-fpsexec-mfilt
        cacao-fpsexec-modalCTRLstats
        cacao-fpsexec-cacaopt-mlat
        cacao-fpsexec-cacaoac-measlinresp
        cacao-fpsexec-cacaocc-compstrcm
        cacaosim-bench
        cacaosim-benchmark
        cacaosim-bench-view
        cacaosim-CTRL
        cacaosim-ao-report
        milk-fpsexec-cacaosim-htsim
        milk-fpsexec-cacaosim-mkbeam
        milk-fpsexec-cacaosim-dmsim
        milk-fpsexec-cacaosim-beamsplit
        milk-fpsexec-cacaosim-pyrwfs
        milk-fpsexec-cacaosim-fpcam
        milk-fpsexec-cacaosim-wfstat
        milk-fpsexec-atmturb-mkwfs
    )
    local libs=(
        libCLIcore.so
        libmilkcommon.so
        libImageStreamIO.so
        libmilkfps.so
        libmilkCOREMODmemory.so
        libmilklinalgebra.so
        libmilkmltools.so
        libcacaoAOloopControl.so
        libmilkOpticsMaterials.so
        libmilkWFpropagate.so
        libmilkcacaosim.so
        libmilkatmturb.so
    )
    local cmd_mods=(
        fpspipe.bash
        sysmon.bash
        cacaoloop.bash
        cacaosim.bash
        mltools.bash
    )

    local missing=0
    for b in "${bins[@]}"; do
        if [[ ! -x "${MILK_INSTALL_ROOT}/bin/${b}" ]]; then
            echo "[build-all] MISSING binary: ${MILK_INSTALL_ROOT}/bin/${b}" >&2
            missing=1
        fi
    done
    for lib in "${libs[@]}"; do
        if ! compgen -G "${MILK_INSTALL_ROOT}/lib/${lib}*" >/dev/null; then
            echo "[build-all] MISSING library: ${MILK_INSTALL_ROOT}/lib/${lib}" >&2
            missing=1
        fi
    done
    for mod in "${cmd_mods[@]}"; do
        if [[ ! -r "${MILK_INSTALL_ROOT}/share/milk/commands.d/${mod}" ]]; then
            echo "[build-all] MISSING commands.d module:" \
                 "${MILK_INSTALL_ROOT}/share/milk/commands.d/${mod}" >&2
            missing=1
        fi
    done

    if [[ "${missing}" -ne 0 ]]; then
        exit 1
    fi
    echo "[build-all] OK: verified ${#bins[@]} binaries, ${#libs[@]} libraries," \
         "${#cmd_mods[@]} commands.d modules in ${MILK_INSTALL_ROOT}"
}

check_branch_safety "${MILK_SRC_DIR}" "milk"
check_branch_safety "${CACAO_SRC_DIR}" "cacao"

if [[ "${CHECK_ONLY}" -eq 0 ]]; then
    case "${ONLY}" in
        all)
            build_and_install_repo "${MILK_SRC_DIR}" "milk+cacao"
            build_and_install_repo "${OPTICSMAT_SRC_DIR}" "OpticsMaterials"
            build_and_install_repo "${WFPROP_SRC_DIR}" "WFpropagate"
            build_and_install_repo "${ATMTURB_SRC_DIR}" "AtmosphericTurbulenceSimul"
            build_and_install_repo "${CACAOSIM_SRC_DIR}" "cacaosim"
            ;;
        milk)
            build_and_install_repo "${MILK_SRC_DIR}" "milk+cacao"
            ;;
        optics)
            build_and_install_repo "${OPTICSMAT_SRC_DIR}" "OpticsMaterials"
            build_and_install_repo "${WFPROP_SRC_DIR}" "WFpropagate"
            ;;
        atmturb)
            build_and_install_repo "${ATMTURB_SRC_DIR}" "AtmosphericTurbulenceSimul"
            ;;
        cacaosim)
            build_and_install_repo "${CACAOSIM_SRC_DIR}" "cacaosim"
            ;;
        *)
            echo "Unknown component '${ONLY}'" >&2
            usage
            exit 1
            ;;
    esac
fi

verify_install
