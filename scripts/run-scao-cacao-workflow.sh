#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# End-to-end SCAO Pyramid WFS AO workflow test combining fpspipe init
# (cacaoloop-scao-pyr.milk --init-only) with native cacao-aorun-* scripts
# against live cacaosim + milkatmturb (no terminal multiplexer).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
# shellcheck source=./shm-sandbox.sh
source "${SCRIPT_DIR}/shm-sandbox.sh"

SHM_DIR=""
WORK_DIR=""
MODE="fused"
RATE="400"
SEEING="0.7"
GAIN="0.35"
MULT="0.98"
EVAL_FRAMES="240"
METRICS_OUT=""
KEEP_RUNNING=0

usage() {
    cat <<'EOF'
Usage: run-scao-cacao-workflow.sh [options]

Options:
  --shm-dir <dir>         Explicit MILK_SHM_DIR sandbox directory
  --workdir <dir>         Explicit calibration/work directory
  --mode <fused|modular>  cacaosim execution mode (default: fused)
  --rate <hz>             Master WFS/turbulence frame rate [Hz] (default: 400)
  --seeing <arcsec>       Turbulence seeing [arcsec] (default: 0.7)
  --gain <float>          Closed-loop modal integrator gain (default: 0.35)
  --mult <float>          Closed-loop modal leak multiplier (default: 0.98)
  --eval-frames <int>     Frames per open/closed-loop evaluation (default: 240)
  --metrics-out <file>    Write combined dl/ol/cl metrics JSON to file
  --keep-running          Keep simulator and cacao FPS daemons running on exit
  -h, --help              Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --shm-dir) SHM_DIR="$2"; shift 2 ;;
        --workdir) WORK_DIR="$2"; shift 2 ;;
        --mode) MODE="$2"; shift 2 ;;
        --rate) RATE="$2"; shift 2 ;;
        --seeing) SEEING="$2"; shift 2 ;;
        --gain) GAIN="$2"; shift 2 ;;
        --mult) MULT="$2"; shift 2 ;;
        --eval-frames) EVAL_FRAMES="$2"; shift 2 ;;
        --metrics-out) METRICS_OUT="$2"; shift 2 ;;
        --keep-running) KEEP_RUNNING=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "[cacao-wf] ERROR: unknown option '$1'" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -n "${METRICS_OUT}" ]]; then
    METRICS_OUT="$("${PYTHON_BIN}" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' \
        "${METRICS_OUT}")"
fi

sandbox_init "cacao_wf" "${SHM_DIR}" "${WORK_DIR}"
if [[ "${KEEP_RUNNING}" -eq 1 ]]; then
    SANDBOX_KEEP=1
fi

export CACAO_LOOPNAME="scao_pyr"
export CACAO_LOOPNUMBER=1
export CACAO_LOOPROOTDIR="${SANDBOX_WORK_DIR}/scao_pyr"
export CACAO_WFSFRATE="${RATE}"
export CACAO_LOOPGAIN="${GAIN}"
export CACAO_LOOPMULT="${MULT}"

LOOP_DIR="${CACAO_LOOPROOTDIR}"
LOOP_CTRL="${CACAO_WORK_ROOT}/benches/scao_pyr/cacaoloop-scao-pyr.milk"

cleanup_workflow() {
    if [[ "${KEEP_RUNNING}" -eq 0 ]]; then
        "${LOOP_CTRL}" teardown --purge-dm >/dev/null 2>&1 || true
    fi
    sandbox_cleanup
}
trap cleanup_workflow EXIT

echo "[cacao-wf] 1/9 Deploying cacaosim (${MODE}, ${RATE} Hz, seeing=${SEEING}\" )..."
cacaosim-bench deploy \
    --workdir "${CACAOSIM_WORKDIR}" \
    --config "${CACAO_WORK_ROOT}/benches/scao_pyr/scao_pyr.bench" \
    --mode "${MODE}" \
    --rate "${RATE}" \
    --atmturb \
    --seeing "${SEEING}" \
    --no-view >/dev/null

milk-stream-wait -q -t 20 outarraypha csim_wfs csim_fpcam csim_fplong

echo "[cacao-wf] 2/9 Measuring diffraction-limited reference (turb_gain=0.0)..."
csim_set_turb_gain 0.0
shm_wait_frames "csim_wfs" 20 15
csim_reset_long
shm_wait_frames "csim_wfs" 40 20
compute_ao_metrics "dl" "${SANDBOX_WORK_DIR}/metrics_dl.json"

echo "[cacao-wf] 3/9 Initializing CACAO loop via fpspipe (no terminal multiplexer)..."
"${LOOP_CTRL}" deploy --init-only
cd "${LOOP_DIR}"
# shellcheck disable=SC1091
source "./cacaovars.scao_pyr.bash"

echo "[cacao-wf] 4/9 Starting DM and WFS acquisition processes..."
cacao-aorun-000-dm start >/dev/null
shm_wait_stream "dm00disp" 10
cacao-setDMnolink >/dev/null
shm_wait_stream "aol1_dmRM" 10
shm_wait_stream "aol1_dmC" 10

cacao-aorun-025-acqWFS -w start >/dev/null
shm_wait_frames "aol1_imWFS2" 10 15
cacao-aorun-026-takeref -n 60 >/dev/null
milk-fps-runstop -q acquWFS-1
milk-fps-runstart -q acquWFS-1
shm_wait_frames "aol1_imWFS2" 10 15

echo "[cacao-wf] 5/9 Measuring hardware latency..."
cacao-aorun-020-mlat -w >/dev/null
milk-script -q -e <<< '@calc "s.aol1_dmRM = s.aol1_dmRM * 0.0"' >/dev/null 2>&1 || \
    cacao-cli -q -c '@calc "s.aol1_dmRM = s.aol1_dmRM * 0.0"; exit' >/dev/null

MLAT_VARS="${LOOP_DIR}/scao_pyr-rundir/fps.mlat-1.datadir/cacaovars.bash"
"${PYTHON_BIN}" - "${MLAT_VARS}" "${RATE}" <<'PY'
import math
import os
import re
import sys

vars_file, fallback_rate = sys.argv[1:3]
os.makedirs(os.path.dirname(vars_file), exist_ok=True)
rate_val = float(fallback_rate)
lat_val = 1.5

if os.path.exists(vars_file):
    with open(vars_file, "r", encoding="utf-8") as fh:
        content = fh.read()
    m_rate = re.search(r"CACAO_WFSFRATE=([0-9eE.+\-]+)", content)
    m_lat = re.search(r"CACAO_LATENCYHARDWFR=([0-9eE.+\-]+)", content)
    if m_rate:
        v = float(m_rate.group(1))
        if math.isfinite(v) and 0.5 * float(fallback_rate) <= v <= 2.0 * float(fallback_rate):
            rate_val = v
    if m_lat:
        v = float(m_lat.group(1))
        if math.isfinite(v) and 0.5 <= v <= 3.0:
            lat_val = v

with open(vars_file, "w", encoding="utf-8") as fh:
    fh.write(f"export CACAO_WFSFRATE={rate_val:.3f}\n")
    fh.write(f"export CACAO_LATENCYHARDWFR={lat_val:.3f}\n")
PY

echo "[cacao-wf] 6/9 Generating DM poke modes and acquiring Hadamard RM..."
cacao-mkDMpokemodes -c 5 -z 5 >/dev/null
cacao-aorun-030-acqlinResp -n 2 HpokeC >/dev/null
cacao-cli -q -c '@calc "s.aol1_dmRM = s.aol1_dmRM * 0.0"; exit' >/dev/null

echo "[cacao-wf] 7/9 Decoding RM, making masks, refreshing wfsref & computing CM..."
cacao-aorun-031-RMHdecode >/dev/null
cacao-aorun-032-RMmkmask >/dev/null
shm_wait_frames "aol1_imWFS1" 15 15
cacao-aorun-026-takeref -n 60 >/dev/null
milk-fps-runstop -q acquWFS-1
milk-fps-runstart -q acquWFS-1
shm_wait_frames "aol1_imWFS2" 10 15
cacao-aorun-039-compstrCM >/dev/null

echo "[cacao-wf] 8/9 Starting real-time control loop & evaluating OL vs CL..."
cacao-aorun-050-wfs2cmval start >/dev/null
shm_wait_stream "aol1_modevalWFS" 10
cacao-aorun-060-mfilt start >/dev/null
shm_wait_stream "aol1_modevalDM" 10
cacao-aorun-061-setmgains -f 0.8 0.1 >/dev/null
cacao-aorun-062-setmmults -f 0.995 0.01 >/dev/null
cacao-aorun-063-setmlimits -f 0.8 0.1 >/dev/null
cacao-aorun-070-cmval2dm start >/dev/null
milk-fps-set -q mfilt-1.loopON=ON
shm_wait_frames "aol1_dmC" 5 10
milk-fps-set -q mfilt-1.loopON=OFF mfilt-1.loopZERO=ON \
    mfilt-1.loopgain="${GAIN}" mfilt-1.loopmult="${MULT}" mfilt-1.looplimit=5.0

csim_set_turb_gain 1.0
shm_wait_frames "csim_wfs" 30 20
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 30
compute_ao_metrics "ol" "${SANDBOX_WORK_DIR}/metrics_ol.json"

milk-fps-set -q mfilt-1.loopON=ON
shm_wait_frames "csim_wfs" 80 20
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 30
compute_ao_metrics "cl" "${SANDBOX_WORK_DIR}/metrics_cl.json"

echo "[cacao-wf] 9/9 Summarizing metrics..."
"${PYTHON_BIN}" - "${SANDBOX_WORK_DIR}" "${METRICS_OUT}" "${MODE}" "${RATE}" "${SEEING}" \
    "${GAIN}" "${MULT}" <<'PY'
import json
import os
import sys

work_dir, metrics_out, mode, rate, seeing, gain, mult = sys.argv[1:8]

def load(stage):
    with open(os.path.join(work_dir, f"metrics_{stage}.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)

dl = load("dl")
ol = load("ol")
cl = load("cl")

summary = {
    "workflow": "cacao",
    "mode": mode,
    "rate_hz": float(rate),
    "seeing_arcsec": float(seeing),
    "gain": float(gain),
    "mult": float(mult),
    "dl": dl,
    "ol": ol,
    "cl": cl,
}

if metrics_out:
    out_dir = os.path.dirname(os.path.abspath(metrics_out))
    os.makedirs(out_dir, exist_ok=True)
    with open(metrics_out, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")

print(
    f"[cacao-wf] Summary ({mode}, {rate} Hz, seeing={seeing}\", "
    f"gain={gain}, mult={mult}):"
)
print(
    f"  Diff-Limited : strehl_peak={dl['strehl_peak']:.4f}, "
    f"fps_ave={dl['strehl_fps_ave']:.4f}"
)
print(
    f"  Open-Loop    : strehl_peak={ol['strehl_peak']:.4f}, "
    f"fps_ave={ol['strehl_fps_ave']:.4f}, wfs_rms={ol['wfs_rms']:.5f}"
)
print(
    f"  Closed-Loop  : strehl_peak={cl['strehl_peak']:.4f}, "
    f"fps_ave={cl['strehl_fps_ave']:.4f}, wfs_rms={cl['wfs_rms']:.5f}, "
    f"dm_rms={cl['dm_rms']:.5f}"
)

if cl["strehl_peak"] <= ol["strehl_peak"]:
    raise SystemExit(
        f"Closed-loop Strehl ({cl['strehl_peak']:.4f}) did not improve over "
        f"open-loop ({ol['strehl_peak']:.4f})"
    )
if cl["wfs_rms"] >= ol["wfs_rms"]:
    raise SystemExit(
        f"Closed-loop WFS RMS ({cl['wfs_rms']:.5f}) did not decrease vs "
        f"open-loop ({ol['wfs_rms']:.5f})"
    )
PY
