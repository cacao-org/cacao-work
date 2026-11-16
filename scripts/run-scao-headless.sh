#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# End-to-end SCAO Pyramid WFS closed-loop AO test via fpspipe,
# cacaosim-bench deploy, and cacaoloop-scao-pyr.milk (no terminal multiplexer).

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
SVDLIM="0.05"
EVAL_FRAMES="240"
METRICS_OUT=""
SAVE_RM_DIR=""
LOAD_RM_DIR=""
KEEP_RUNNING=0

usage() {
    cat <<'EOF'
Usage: run-scao-headless.sh [options]

Options:
  --shm-dir <dir>         Explicit MILK_SHM_DIR sandbox directory
  --workdir <dir>         Explicit calibration/work directory
  --mode <fused|modular>  cacaosim execution mode (default: fused)
  --rate <hz>             Master WFS/turbulence frame rate [Hz] (default: 400)
  --seeing <arcsec>       Turbulence seeing [arcsec] (default: 0.7)
  --gain <float>          Closed-loop modal integrator gain (default: 0.35)
  --mult <float>          Closed-loop modal leak multiplier (default: 0.98)
  --svdlim <float>        SVD pseudo-inverse cutoff (default: 0.05)
  --eval-frames <int>     Frames per open/closed-loop evaluation (default: 240)
  --save-rm <dir>         Save calibrated response matrix & masks to <dir>
  --load-rm <dir>         Reuse saved response matrix from <dir> (skip poking)
  --metrics-out <file>    Write combined dl/ol/cl metrics JSON to file
  --keep-running          Keep simulator and AO FPS daemons running on exit
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
        --svdlim) SVDLIM="$2"; shift 2 ;;
        --eval-frames) EVAL_FRAMES="$2"; shift 2 ;;
        --save-rm) SAVE_RM_DIR="$2"; shift 2 ;;
        --load-rm) LOAD_RM_DIR="$2"; shift 2 ;;
        --metrics-out) METRICS_OUT="$2"; shift 2 ;;
        --keep-running) KEEP_RUNNING=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "[fpspipe] ERROR: unknown option '$1'" >&2
            usage >&2
            exit 2
            ;;
    esac
done

abspath_py() {
    "${PYTHON_BIN}" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1"
}

if [[ -n "${METRICS_OUT}" ]]; then
    METRICS_OUT="$(abspath_py "${METRICS_OUT}")"
fi
if [[ -n "${SAVE_RM_DIR}" ]]; then
    SAVE_RM_DIR="$(abspath_py "${SAVE_RM_DIR}")"
fi
if [[ -n "${LOAD_RM_DIR}" ]]; then
    LOAD_RM_DIR="$(abspath_py "${LOAD_RM_DIR}")"
fi

sandbox_init "fpspipe" "${SHM_DIR}" "${WORK_DIR}"
if [[ "${KEEP_RUNNING}" -eq 1 ]]; then
    SANDBOX_KEEP=1
fi

export CACAO_LOOPNAME="scao_pyr"
export CACAO_LOOPNUMBER=1
export CACAO_LOOPROOTDIR="${SANDBOX_WORK_DIR}/scao_pyr"
export CACAO_WFSFRATE="${RATE}"
export CACAO_LOOPGAIN="${GAIN}"
export CACAO_LOOPMULT="${MULT}"
export CACAO_SVDLIM="${SVDLIM}"

LOOP_CTRL="${CACAO_WORK_ROOT}/benches/scao_pyr/cacaoloop-scao-pyr.milk"

cleanup_run() {
    if [[ "${KEEP_RUNNING}" -eq 0 ]]; then
        "${LOOP_CTRL}" teardown --purge-dm >/dev/null 2>&1 || true
    fi
    sandbox_cleanup
}
trap cleanup_run EXIT

echo "[fpspipe] 1/7 Deploying cacaosim (${MODE}, ${RATE} Hz, seeing=${SEEING}\" )..."
cacaosim-bench deploy \
    --workdir "${CACAOSIM_WORKDIR}" \
    --config "${CACAO_WORK_ROOT}/benches/scao_pyr/scao_pyr.bench" \
    --mode "${MODE}" \
    --rate "${RATE}" \
    --atmturb \
    --seeing "${SEEING}" \
    --no-view >/dev/null

milk-stream-wait -q -t 20 outarraypha csim_wfs csim_fpcam csim_fplong

echo "[fpspipe] 2/7 Measuring diffraction-limited reference (turb_gain=0.0)..."
csim_set_turb_gain 0.0
shm_wait_frames "csim_wfs" 20 15
csim_reset_long
shm_wait_frames "csim_wfs" 40 20
compute_ao_metrics "dl" "${SANDBOX_WORK_DIR}/metrics_dl.json"

echo "[fpspipe] 3/7 Deploying SCAO Pyramid AO pipeline (cacaoloop-scao-pyr.milk)..."
"${LOOP_CTRL}" deploy

if [[ -n "${LOAD_RM_DIR}" ]]; then
    echo "[fpspipe] 4/7 Loading saved RM (${LOAD_RM_DIR}) & computing SVD CM..."
    "${LOOP_CTRL}" load-rm "${LOAD_RM_DIR}" --svdlim "${SVDLIM}"
    if [[ -n "${SAVE_RM_DIR}" ]]; then
        "${LOOP_CTRL}" save-rm "${SAVE_RM_DIR}"
    fi
else
    echo "[fpspipe] 4/7 Calibrating WFS ref, latency, Hadamard RM & SVD CM..."
    cal_args=(calibrate --nframes 60 --nbloop 2 --svdlim "${SVDLIM}")
    if [[ -n "${SAVE_RM_DIR}" ]]; then
        cal_args+=(--save-rm "${SAVE_RM_DIR}")
    fi
    "${LOOP_CTRL}" "${cal_args[@]}"
fi

echo "[fpspipe] 5/7 Verifying closed-loop actuator path and warming up..."
"${LOOP_CTRL}" close "${GAIN}"
shm_wait_frames "aol1_dmC" 5 10
"${LOOP_CTRL}" zero

echo "[fpspipe] 6/7 Evaluating open-loop vs closed-loop performance..."
"${LOOP_CTRL}" zero
csim_set_turb_gain 1.0
shm_wait_frames "csim_wfs" 30 20
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 30
compute_ao_metrics "ol" "${SANDBOX_WORK_DIR}/metrics_ol.json"

"${LOOP_CTRL}" close "${GAIN}"
shm_wait_frames "csim_wfs" 80 20
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 30
compute_ao_metrics "cl" "${SANDBOX_WORK_DIR}/metrics_cl.json"

echo "[fpspipe] 7/7 Summarizing metrics..."
"${PYTHON_BIN}" - "${SANDBOX_WORK_DIR}" "${METRICS_OUT}" "${MODE}" "${RATE}" "${SEEING}" \
    "${GAIN}" "${MULT}" "${SVDLIM}" "${SAVE_RM_DIR}" "${LOAD_RM_DIR}" <<'PY'
import json
import os
import re
import sys
import numpy as np
from astropy.io import fits

(
    work_dir,
    metrics_out,
    mode,
    rate,
    seeing,
    gain,
    mult,
    svdlim,
    save_rm_dir,
    load_rm_dir,
) = sys.argv[1:11]

def load(stage):
    with open(os.path.join(work_dir, f"metrics_{stage}.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)

dl = load("dl")
ol = load("ol")
cl = load("cl")

conf_dir = os.path.join(work_dir, "scao_pyr", "conf")
calib = {
    "source": "load-rm" if load_rm_dir else "calibrated",
    "svdlim": float(svdlim),
    "save_rm_dir": save_rm_dir or None,
    "load_rm_dir": load_rm_dir or None,
}
zresp_p = os.path.join(conf_dir, "zrespC.fits")
cmdm_p = os.path.join(conf_dir, "CMmodesDM.fits")
dmmask_p = os.path.join(conf_dir, "dmmask.fits")
wfsmask_p = os.path.join(conf_dir, "wfsmask.fits")
meta_p = os.path.join(conf_dir, "rm_meta.env")

if os.path.isfile(zresp_p):
    calib["n_rm_modes"] = int(fits.getheader(zresp_p).get("NAXIS3", 0))
if os.path.isfile(cmdm_p):
    calib["n_cm_modes"] = int(fits.getheader(cmdm_p).get("NAXIS3", 0))
if os.path.isfile(dmmask_p):
    calib["active_dm_act"] = int(np.sum(np.asarray(fits.getdata(dmmask_p)) > 0.5))
if os.path.isfile(wfsmask_p):
    calib["active_wfs_pix"] = int(np.sum(np.asarray(fits.getdata(wfsmask_p)) > 0.5))
if os.path.isfile(meta_p):
    meta_txt = open(meta_p, "r", encoding="utf-8").read()
    m_f = re.search(r'RM_WFSFRATE="([0-9eE.+\-]+)"', meta_txt)
    m_l = re.search(r'RM_LATENCYHARDWFR="([0-9eE.+\-]+)"', meta_txt)
    if m_f:
        calib["measured_rate_hz"] = float(m_f.group(1))
    if m_l:
        calib["measured_latency_fr"] = float(m_l.group(1))

summary = {
    "workflow": "fpspipe",
    "mode": mode,
    "rate_hz": float(rate),
    "seeing_arcsec": float(seeing),
    "gain": float(gain),
    "mult": float(mult),
    "calib": calib,
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
    f"[fpspipe] Summary ({mode}, {rate} Hz, seeing={seeing}\", "
    f"gain={gain}, mult={mult}, calib={calib['source']}):"
)
if "n_cm_modes" in calib:
    print(
        f"  Calibration  : rm_modes={calib.get('n_rm_modes', 0)}, "
        f"cm_modes={calib['n_cm_modes']} (svdlim={svdlim}), "
        f"dm_act={calib.get('active_dm_act', 0)}/144, "
        f"wfs_pix={calib.get('active_wfs_pix', 0)}/4096"
    )
print(
    f"  Diff-Limited : strehl_peak={dl['strehl_peak']:.4f}, "
    f"fps_ave={dl['strehl_fps_ave']:.4f}"
)
print(
    f"  Open-Loop    : strehl_peak={ol['strehl_peak']:.4f}, "
    f"fps_ave={ol['strehl_fps_ave']:.4f}, wfs_rms={ol['wfs_rms']:.5f}, "
    f"mval_rms={ol['mval_rms']:.5f}"
)
print(
    f"  Closed-Loop  : strehl_peak={cl['strehl_peak']:.4f}, "
    f"fps_ave={cl['strehl_fps_ave']:.4f}, wfs_rms={cl['wfs_rms']:.5f}, "
    f"mval_rms={cl['mval_rms']:.5f}, dm_rms={cl['dm_rms']:.5f}"
)
if save_rm_dir:
    print(f"  Saved RM     : {save_rm_dir}")

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
