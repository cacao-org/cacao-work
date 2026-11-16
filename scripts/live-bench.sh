#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Persistent interactive SCAO bench manager supporting live TUI inspection
# (milk-CTRL, milk-fpsCTRL, milk-procCTRL, cacaosim-CTRL, cacao-modalstatsTUI).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
# shellcheck source=./shm-sandbox.sh
source "${SCRIPT_DIR}/shm-sandbox.sh"

RUN_USER="${USER:-$(id -un)}"
LIVE_STATE_FILE="${CACAO_LIVE_STATE_FILE:-/tmp/cacao_work_live_${RUN_USER}.state}"
LOOP_CTRL="${CACAO_WORK_ROOT}/benches/scao_pyr/cacaoloop-scao-pyr.milk"

usage() {
    cat <<'EOF'
Usage: live-bench.sh <command> [options]

Commands:
  start [opts]   Launch persistent optical bench (optionally calibrated/closed)
                 Options: --workflow <fpspipe|cacao>  (default: fpspipe)
                          --calibrate                 Run full calibration
                          --save-rm <dir>             Save calibrated RM to <dir>
                          --load-rm <dir>             Load saved RM from <dir>
                          --close                     Close loop after calibrate
                          --shm-dir <dir>             Explicit MILK_SHM_DIR
                          --workdir <dir>             Explicit work directory
                          --rate <hz>                 Frame rate (default: 400)
                          --seeing <arcsec>           Seeing (default: 0.7)
                          --mode <fused|modular>      cacaosim mode (default: fused)
                          --gain <float>              Modal gain (default: 0.35)
                          --mult <float>              Modal leak (default: 0.98)
  status         Show optical bench status, active FPS units, and loop telemetry
  open           Open AO loop (mfilt-1.loopON OFF)
  close [gain]   Close AO loop (optionally set mfilt-1.loopgain <gain>)
  zero           Zero DM modal commands (mfilt-1.loopZERO ON) and dm00disp03
  turb <gain>    Set live turbulence multiplier (.turb_gain) and reset long PSF
  env            Print shell export statements for connecting to the active bench
  tui <which>    Launch interactive TUI: milk | fps | proc | cacaosim | mstat
  stop           Stop all running units, remove sandbox SHM, and clear state
EOF
}

resolve_live_env() {
    local opt_shm="${1:-}"
    local env_file=""
    if [[ -n "${opt_shm}" && -f "${opt_shm}/live_bench.env" ]]; then
        env_file="${opt_shm}/live_bench.env"
    elif [[ -n "${MILK_SHM_DIR:-}" && -f "${MILK_SHM_DIR}/live_bench.env" ]]; then
        env_file="${MILK_SHM_DIR}/live_bench.env"
    elif [[ -f "${LIVE_STATE_FILE}" ]]; then
        local recorded_shm
        recorded_shm="$(cat "${LIVE_STATE_FILE}")"
        if [[ -n "${recorded_shm}" && -f "${recorded_shm}/live_bench.env" ]]; then
            env_file="${recorded_shm}/live_bench.env"
        fi
    fi

    if [[ -z "${env_file}" || ! -f "${env_file}" ]]; then
        echo "[live-bench] ERROR: no active live bench found; run 'live-bench.sh start'" >&2
        exit 1
    fi
    # shellcheck disable=SC1090
    source "${env_file}"
}

cmd_start() {
    local workflow="fpspipe"
    local calibrate=0
    local close_loop=0
    local shm_dir=""
    local work_dir=""
    local rate="400"
    local seeing="0.7"
    local mode="fused"
    local gain="0.35"
    local mult="0.98"
    local save_rm=""
    local load_rm=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --workflow) workflow="$2"; shift 2 ;;
            --calibrate) calibrate=1; shift ;;
            --save-rm) save_rm="$2"; calibrate=1; shift 2 ;;
            --load-rm) load_rm="$2"; calibrate=1; shift 2 ;;
            --close) close_loop=1; shift ;;
            --shm-dir) shm_dir="$2"; shift 2 ;;
            --workdir) work_dir="$2"; shift 2 ;;
            --rate) rate="$2"; shift 2 ;;
            --seeing) seeing="$2"; shift 2 ;;
            --mode) mode="$2"; shift 2 ;;
            --gain) gain="$2"; shift 2 ;;
            --mult) mult="$2"; shift 2 ;;
            -h|--help) usage; exit 0 ;;
            *)
                echo "[live-bench] ERROR: unknown start option '$1'" >&2
                exit 2
                ;;
        esac
    done

    if [[ "${workflow}" == "headless" ]]; then
        workflow="fpspipe"
    fi

    if [[ -z "${shm_dir}" ]]; then
        shm_dir="/dev/shm/cacao_work_live_${RUN_USER}_$$"
        LIVE_OWNED_SHM=1
    else
        LIVE_OWNED_SHM=0
    fi
    if [[ -z "${work_dir}" ]]; then
        work_dir="/tmp/cacao_work_live_${RUN_USER}_$$"
        LIVE_OWNED_WORK=1
    else
        LIVE_OWNED_WORK=0
    fi

    sandbox_init "live" "${shm_dir}" "${work_dir}"
    export SANDBOX_KEEP=1
    export CACAO_LOOPNUMBER=1
    export CACAO_LOOPNAME="scao_pyr"

    local loop_root=""
    if [[ "${calibrate}" -eq 1 ]]; then
        loop_root="${SANDBOX_WORK_DIR}/scao_pyr"
        if [[ "${workflow}" == "fpspipe" ]]; then
            local -a hl_args=(
                --shm-dir "${MILK_SHM_DIR}"
                --workdir "${SANDBOX_WORK_DIR}"
                --mode "${mode}"
                --rate "${rate}"
                --seeing "${seeing}"
                --gain "${gain}"
                --mult "${mult}"
                --eval-frames 60
                --keep-running
            )
            [[ -n "${save_rm}" ]] && hl_args+=(--save-rm "${save_rm}")
            [[ -n "${load_rm}" ]] && hl_args+=(--load-rm "${load_rm}")
            "${SCRIPT_DIR}/run-scao-headless.sh" "${hl_args[@]}"
        elif [[ "${workflow}" == "cacao" ]]; then
            "${SCRIPT_DIR}/run-scao-cacao-workflow.sh" \
                --shm-dir "${MILK_SHM_DIR}" \
                --workdir "${SANDBOX_WORK_DIR}" \
                --mode "${mode}" \
                --rate "${rate}" \
                --seeing "${seeing}" \
                --gain "${gain}" \
                --mult "${mult}" \
                --eval-frames 60 \
                --keep-running
        else
            echo "[live-bench] ERROR: unknown workflow '${workflow}'" >&2
            exit 2
        fi

        if [[ -f "${MILK_SHM_DIR}/mfilt-1.fps.shm" ]]; then
            if [[ "${close_loop}" -eq 1 ]]; then
                "${LOOP_CTRL}" close "${gain}"
            else
                "${LOOP_CTRL}" zero
            fi
            csim_reset_long
        fi
    else
        ATMTURB_MASTER_SIZE="${ATMTURB_MASTER_SIZE:-512}" \
        cacaosim-bench deploy \
            --workdir "${CACAOSIM_WORKDIR}" \
            --config "${CACAO_WORK_ROOT}/benches/scao_pyr/scao_pyr.bench" \
            --mode "${mode}" \
            --rate "${rate}" \
            --atmturb \
            --seeing "${seeing}" \
            --no-view >/dev/null

        milk-stream-wait -q -t 20 outarraypha csim_wfs csim_fpcam csim_fplong
    fi

    cat > "${MILK_SHM_DIR}/live_bench.env" <<EOF
export MILK_SHM_DIR="${MILK_SHM_DIR}"
export MILK_PROC_DIR="${MILK_PROC_DIR}"
export CACAOSIM_WORKDIR="${CACAOSIM_WORKDIR}"
export CACAO_WORK_ROOT="${CACAO_WORK_ROOT}"
export CACAO_LOOPNAME="scao_pyr"
export CACAO_LOOPNUMBER="1"
export CACAO_LOOPROOTDIR="${loop_root}"
export WORKFLOW="${workflow}"
export BENCH_MODE="${mode}"
export BENCH_RATE="${rate}"
export BENCH_SEEING="${seeing}"
export BENCH_WORK_DIR="${SANDBOX_WORK_DIR}"
export LIVE_OWNED_SHM="${LIVE_OWNED_SHM}"
export LIVE_OWNED_WORK="${LIVE_OWNED_WORK}"
EOF

    mkdir -p "$(dirname "${LIVE_STATE_FILE}")"
    printf '%s\n' "${MILK_SHM_DIR}" > "${LIVE_STATE_FILE}"

    echo "[live-bench] Live bench active."
    echo "  MILK_SHM_DIR=${MILK_SHM_DIR}"
    echo "  WORKFLOW=${workflow}  MODE=${mode}  RATE=${rate} Hz  SEEING=${seeing}\""
    echo "  Connect shell : eval \"\$(${SCRIPT_DIR}/live-bench.sh env)\""
    echo "  Launch TUIs   : ${SCRIPT_DIR}/live-bench.sh tui <milk|fps|proc|cacaosim|mstat>"
}

cmd_status() {
    local shm_opt=""
    if [[ "${1:-}" == "--shm-dir" ]]; then
        shm_opt="${2:-}"
    fi
    resolve_live_env "${shm_opt}"
    echo "=== live-bench status ==="
    echo "MILK_SHM_DIR=${MILK_SHM_DIR}  WORKFLOW=${WORKFLOW}  MODE=${BENCH_MODE}"
    cacaosim-bench status --workdir "${CACAOSIM_WORKDIR}" --no-view || true
    echo "--- Active FPS instances ---"
    shopt -s nullglob
    for f in "${MILK_SHM_DIR}"/*.fps.shm; do
        echo "  - $(basename "${f}" .fps.shm)"
    done
    shopt -u nullglob
    if [[ -f "${MILK_SHM_DIR}/mfilt-1.fps.shm" ]]; then
        echo "--- mfilt-1 telemetry ---"
        milk-fps-info mfilt-1 | grep -E "loopON|loopgain|loopmult|looplimit" || true
    fi
    if [[ -f "${MILK_SHM_DIR}/csim_htsim.fps.shm" ]]; then
        echo "--- csim_htsim telemetry ---"
        milk-fps-info csim_htsim | grep -E "turb_gain|strehl_" || true
    elif [[ -f "${MILK_SHM_DIR}/csim_sci.fps.shm" ]]; then
        echo "--- csim_sci telemetry ---"
        milk-fps-info csim_sci | grep -E "strehl_" || true
    fi
}

cmd_stop() {
    local shm_opt=""
    if [[ "${1:-}" == "--shm-dir" ]]; then
        shm_opt="${2:-}"
    fi
    resolve_live_env "${shm_opt}"
    if [[ -n "${CACAO_LOOPROOTDIR:-}" && -d "${CACAO_LOOPROOTDIR}" ]]; then
        CACAO_LOOPROOTDIR="${CACAO_LOOPROOTDIR}" \
            "${LOOP_CTRL}" teardown --purge-dm >/dev/null 2>&1 || true
    fi
    sandbox_stop_all
    if [[ -n "${MILK_SHM_DIR:-}" ]] &&
       [[ "${MILK_SHM_DIR}" == /dev/shm/cacao_* || "${LIVE_OWNED_SHM:-0}" -eq 1 ]]; then
        rm -rf "${MILK_SHM_DIR}"
    fi
    if [[ "${LIVE_OWNED_WORK:-0}" -eq 1 && -n "${BENCH_WORK_DIR:-}" ]] &&
       [[ "${BENCH_WORK_DIR}" == /tmp/cacao_* ]]; then
        rm -rf "${BENCH_WORK_DIR}"
    fi
    rm -f "${LIVE_STATE_FILE}"
    echo "[live-bench] Stopped and cleaned up."
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

SUBCMD="$1"
shift

case "${SUBCMD}" in
    -h|--help)
        usage
        ;;
    start)
        cmd_start "$@"
        ;;
    status)
        cmd_status "$@"
        ;;
    open)
        resolve_live_env
        "${LOOP_CTRL}" open
        echo "[live-bench] Loop opened (mfilt-1.loopON=OFF)"
        ;;
    close)
        resolve_live_env
        "${LOOP_CTRL}" close "${1:-}"
        echo "[live-bench] Loop closed (mfilt-1.loopON=ON)"
        ;;
    zero)
        resolve_live_env
        "${LOOP_CTRL}" zero
        echo "[live-bench] DM correction channel zeroed."
        ;;
    turb)
        if [[ $# -lt 1 ]]; then
            echo "[live-bench] ERROR: 'turb' requires <gain>" >&2
            exit 2
        fi
        resolve_live_env
        csim_set_turb_gain "$1"
        csim_reset_long
        echo "[live-bench] Turbulence gain set to $1 and long PSF reset."
        ;;
    env)
        resolve_live_env
        echo "export MILK_SHM_DIR=\"${MILK_SHM_DIR}\""
        echo "export MILK_PROC_DIR=\"${MILK_PROC_DIR}\""
        echo "export CACAOSIM_WORKDIR=\"${CACAOSIM_WORKDIR}\""
        echo "export CACAO_WORK_ROOT=\"${CACAO_WORK_ROOT}\""
        echo "export CACAO_LOOPNAME=\"${CACAO_LOOPNAME}\""
        echo "export CACAO_LOOPNUMBER=\"${CACAO_LOOPNUMBER}\""
        echo "export CACAO_LOOPROOTDIR=\"${CACAO_LOOPROOTDIR:-}\""
        ;;
    tui)
        if [[ $# -lt 1 ]]; then
            echo "[live-bench] ERROR: 'tui' requires <milk|fps|proc|cacaosim|mstat>" >&2
            exit 2
        fi
        resolve_live_env
        case "$1" in
            milk) exec milk-CTRL ;;
            fps) exec milk-fpsCTRL ;;
            proc) exec milk-procCTRL ;;
            cacaosim) exec cacaosim-CTRL ;;
            mstat) exec cacao-modalstatsTUI "${CACAO_LOOPNUMBER:-1}" ;;
            *)
                echo "[live-bench] ERROR: unknown tui target '$1'" >&2
                exit 2
                ;;
        esac
        ;;
    stop)
        cmd_stop "$@"
        ;;
    *)
        echo "[live-bench] ERROR: unknown subcommand '${SUBCMD}'" >&2
        usage >&2
        exit 2
        ;;
esac
