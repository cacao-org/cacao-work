#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Shared-memory sandbox and telemetry helpers for isolated integration runs.
# Intended to be sourced by orchestration scripts (`source shm-sandbox.sh`).

if [[ -z "${CACAO_WORK_ROOT:-}" ]]; then
    _ss_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # shellcheck source=../env.sh
    source "${_ss_dir}/../env.sh"
    unset _ss_dir
fi

sandbox_init() {
    local tag="${1:-run}"
    local explicit_shm="${2:-}"
    local explicit_work="${3:-}"

    if [[ -n "${explicit_shm}" ]]; then
        export MILK_SHM_DIR="${explicit_shm}"
        SANDBOX_OWNED_SHM=0
    else
        export MILK_SHM_DIR="/dev/shm/cacao_work_${tag}_$$"
        SANDBOX_OWNED_SHM=1
    fi

    if [[ -n "${explicit_work}" ]]; then
        SANDBOX_WORK_DIR="${explicit_work}"
        SANDBOX_OWNED_WORK=0
    else
        SANDBOX_WORK_DIR="/tmp/cacao_work_${tag}_$$"
        SANDBOX_OWNED_WORK=1
    fi

    export MILK_PROC_DIR="${MILK_SHM_DIR}/proc"
    export CACAOSIM_WORKDIR="${SANDBOX_WORK_DIR}/csim"
    export MILK_QUIET=1
    export SANDBOX_WORK_DIR
    export SANDBOX_OWNED_SHM
    export SANDBOX_OWNED_WORK

    mkdir -p "${MILK_SHM_DIR}" "${MILK_PROC_DIR}" "${SANDBOX_WORK_DIR}" "${CACAOSIM_WORKDIR}"
}

sandbox_stop_all() {
    if [[ -z "${MILK_SHM_DIR:-}" || ! -d "${MILK_SHM_DIR}" ]]; then
        return 0
    fi

    local csim_wdir="${CACAOSIM_WORKDIR:-${SANDBOX_WORK_DIR:-${MILK_SHM_DIR}}/csim}"
    cacaosim-bench teardown --workdir "${csim_wdir}" --no-view >/dev/null 2>&1 || true

    shopt -s nullglob
    local fps_files=("${MILK_SHM_DIR}"/*.fps.shm)
    shopt -u nullglob

    if (( ${#fps_files[@]} )); then
        local -a fps_names=()
        local fps_path
        for fps_path in "${fps_files[@]}"; do
            fps_names+=("$(basename "${fps_path}" .fps.shm)")
        done
        milk-fps-runstop -q "${fps_names[@]}" >/dev/null 2>&1 || true
        milk-fps-confstop -q "${fps_names[@]}" >/dev/null 2>&1 || true
        milk-fps-rm -f -q --ignore-missing "${fps_names[@]}" >/dev/null 2>&1 || true
    fi

    rm -rf "${MILK_SHM_DIR}"/cacaoloop-* >/dev/null 2>&1 || true
}

sandbox_cleanup() {
    if [[ "${SANDBOX_KEEP:-0}" -eq 1 ]]; then
        return 0
    fi
    sandbox_stop_all
    if [[ "${SANDBOX_OWNED_SHM:-0}" -eq 1 && -n "${MILK_SHM_DIR:-}" ]] &&
       [[ "${MILK_SHM_DIR}" == /dev/shm/cacao_* ]]; then
        rm -rf "${MILK_SHM_DIR}"
    fi
    if [[ "${SANDBOX_OWNED_WORK:-0}" -eq 1 && -n "${SANDBOX_WORK_DIR:-}" ]] &&
       [[ "${SANDBOX_WORK_DIR}" == /tmp/cacao_* ]]; then
        rm -rf "${SANDBOX_WORK_DIR}"
    fi
}

shm_wait_stream() {
    local stream_name="$1"
    local timeout_s="${2:-10}"
    if ! milk-stream-wait -q -t "${timeout_s}" "${stream_name}"; then
        echo "[shm-sandbox] ERROR: timed out waiting for stream '${stream_name}' in" \
             "${MILK_SHM_DIR}" >&2
        return 1
    fi
}

shm_wait_frames() {
    local stream_name="$1"
    local delta_frames="$2"
    local timeout_s="${3:-15}"
    if ! milk-stream-wait -q -t "${timeout_s}" "${stream_name}+${delta_frames}"; then
        echo "[shm-sandbox] ERROR: stream '${stream_name}+${delta_frames}' timed out" \
             "after ${timeout_s}s" >&2
        return 1
    fi
}

shm_dump_fits() {
    local stream_name="$1"
    local out_fits="$2"
    local out_dir out_base fps_name="savefits_dump"
    out_dir="$(dirname "${out_fits}")"
    out_base="$(basename "${out_fits}")"
    mkdir -p "${out_dir}"
    milk-fps-rm -f -q --ignore-missing "${fps_name}" >/dev/null 2>&1 || true
    (
        cd "${out_dir}" || exit 1
        milk-fpsexec-iofits-saveFITS --no-procinfo -n "${fps_name}" exec \
            .in_name="${stream_name}" \
            .out_fname="!${out_base}" >/dev/null
    )
    milk-fps-rm -f -q --ignore-missing "${fps_name}" >/dev/null 2>&1 || true
}

csim_set_turb_gain() {
    local gain="$1"
    local found=0
    found="$(milk-script -q -e <<EOF
shopt -s nullglob
hit=0
for fp in "\${MILK_SHM_DIR}"/csim_*.fps.shm; do
    u="\${fp##*/}"
    u="\${u%.fps.shm}"
    if @get _v="f.\${u}.turb_gain" 2>/dev/null; then
        @set "f.\${u}.turb_gain=${gain}"
        hit=1
    fi
done
printf '%d\n' "\${hit}"
EOF
)"
    if [[ "${found:-0}" -eq 0 ]]; then
        echo "[shm-sandbox] WARNING: no csim_* FPS with .turb_gain found" >&2
    fi
}

csim_reset_long() {
    local found=0
    found="$(milk-script -q -e <<'EOF'
shopt -s nullglob
hit=0
for fp in "${MILK_SHM_DIR}"/csim_*.fps.shm; do
    u="${fp##*/}"
    u="${u%.fps.shm}"
    if @get _v="f.${u}.reset_long" 2>/dev/null; then
        @set "f.${u}.reset_long=ON"
        hit=1
    fi
done
printf '%d\n' "${hit}"
EOF
)"
    if [[ "${found:-0}" -eq 0 ]]; then
        echo "[shm-sandbox] WARNING: no csim_* FPS with .reset_long found" >&2
    fi
}

compute_ao_metrics() {
    local stage_label="$1"
    local out_json="$2"
    local loop_num="${CACAO_LOOPNUMBER:-1}"
    local dump_dir="${SANDBOX_WORK_DIR}/metrics_${stage_label}_$$"
    mkdir -p "${dump_dir}"

    shm_dump_fits "csim_fplong" "${dump_dir}/fplong.fits"
    if [[ -e "${MILK_SHM_DIR}/aol${loop_num}_imWFS2.im.shm" ]]; then
        shm_dump_fits "aol${loop_num}_imWFS2" "${dump_dir}/imWFS2.fits"
    fi
    if [[ -e "${MILK_SHM_DIR}/aol${loop_num}_modevalWFS.im.shm" ]]; then
        shm_dump_fits "aol${loop_num}_modevalWFS" "${dump_dir}/modevalWFS.fits"
    fi
    if [[ -e "${MILK_SHM_DIR}/aol${loop_num}_dmC.im.shm" ]]; then
        shm_dump_fits "aol${loop_num}_dmC" "${dump_dir}/dmC.fits"
    fi

    local strehl_ave="0.0"
    strehl_ave="$(milk-script -q -e <<'EOF' 2>/dev/null || echo "0.0"
val="0.0"
for u in csim_htsim csim_sci; do
    if @get _v="f.${u}.strehl_ave" 2>/dev/null; then
        val="${_v}"
        break
    fi
done
printf '%s\n' "${val}"
EOF
)"

    "${PYTHON_BIN}" - "${stage_label}" "${dump_dir}" "${out_json}" "${strehl_ave:-0.0}" <<'PY'
import json
import os
import sys
import numpy as np
from astropy.io import fits

stage, dump_dir, out_json, strehl_fps = sys.argv[1:5]

def load_opt(name):
    path = os.path.join(dump_dir, name)
    if not os.path.exists(path):
        return None
    return np.asarray(fits.getdata(path), dtype=np.float64)

fplong = load_opt("fplong.fits")
wfs2 = load_opt("imWFS2.fits")
mval = load_opt("modevalWFS.fits")
dmc = load_opt("dmC.fits")

data = {
    "stage": stage,
    "strehl_peak": float(np.max(fplong)) if fplong is not None else 0.0,
    "strehl_sum": float(np.sum(fplong)) if fplong is not None else 0.0,
    "strehl_fps_ave": float(strehl_fps) if strehl_fps else 0.0,
    "wfs_rms": float(np.sqrt(np.mean(wfs2 ** 2))) if wfs2 is not None else 0.0,
    "mval_rms": float(np.sqrt(np.mean(mval ** 2))) if mval is not None else 0.0,
    "dm_rms": float(np.sqrt(np.mean(dmc ** 2))) if dmc is not None else 0.0,
}

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY

    rm -rf "${dump_dir}"
}
