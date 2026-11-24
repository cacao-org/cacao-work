#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Capture closed-loop telemetry on scao_pyr with configurable PyWFS modulation radius
# (default: mod_rad=0.0, unmodulated PyWFS) in an isolated SHM sandbox.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
# shellcheck source=../../../env.sh
source "${REPO_ROOT}/env.sh"
# shellcheck source=../../../scripts/shm-sandbox.sh
source "${REPO_ROOT}/scripts/shm-sandbox.sh"

MOD_RAD="${1:-0.0}"
SEEING="${2:-0.7}"
NFRAMES="${3:-4000}"
OUTDIR="${4:-${REPO_ROOT}/_work/selflearn_scao_unmod0}"
RATE="${RATE:-400}"
GAIN="${GAIN:-0.30}"
MULT="${MULT:-0.98}"
SVDLIM="${SVDLIM:-0.05}"

mkdir -p "${OUTDIR}/telemetry" "${OUTDIR}/rm"

sandbox_init "slcap"
LOOP_CTRL="${REPO_ROOT}/benches/scao_pyr/cacaoloop-scao-pyr.milk"
export CACAO_LOOPNAME="scao_pyr"
export CACAO_LOOPNUMBER=1
export CACAO_LOOPROOTDIR="${SANDBOX_WORK_DIR}/scao_pyr"
export CACAO_WFSFRATE="${RATE}"
export CACAO_LOOPGAIN="${GAIN}"
export CACAO_LOOPMULT="${MULT}"
export CACAO_SVDLIM="${SVDLIM}"

TLM_LINK="/tmp/sl_tlm_$$"
ln -sfn "${OUTDIR}/telemetry" "${TLM_LINK}"

cleanup_cap() {
    milk-fps-runstop -q log_wfs log_dm log_ol >/dev/null 2>&1 || true
    milk-fps-rm -f -q --ignore-missing log_wfs log_dm log_ol >/dev/null 2>&1 || true
    "${LOOP_CTRL}" teardown --purge-dm >/dev/null 2>&1 || true
    rm -f "${TLM_LINK}"
    sandbox_cleanup
}
trap cleanup_cap EXIT

# Generate custom bench config with desired mod_rad
BENCH_CFG="${SANDBOX_WORK_DIR}/scao_unmod.bench"
awk -v mr="${MOD_RAD}" '
/^mod_rad[ \t]*=/ { printf "mod_rad       = %s\n", mr; next }
/^mod_npts[ \t]*=/ { if (mr + 0 == 0) { printf "mod_npts      = 1\n"; next } }
{ print }
' "${REPO_ROOT}/benches/scao_pyr/scao_pyr.bench" > "${BENCH_CFG}"

echo "[slcap] Deploying scao_pyr (mod_rad=${MOD_RAD}, seeing=${SEEING}\", rate=${RATE} Hz)..."
cacaosim-bench deploy \
    --workdir "${CACAOSIM_WORKDIR}" \
    --config "${BENCH_CFG}" \
    --mode fused \
    --rate "${RATE}" \
    --atmturb \
    --seeing "${SEEING}" \
    --no-view >/dev/null

milk-stream-wait -q -t 20 outarraypha csim_wfs csim_fpcam csim_fplong

echo "[slcap] Measuring diffraction-limited reference..."
csim_set_turb_gain 0.0
shm_wait_frames "csim_wfs" 15 15
csim_reset_long
shm_wait_frames "csim_wfs" 30 15
compute_ao_metrics "dl" "${OUTDIR}/metrics_dl.json"

echo "[slcap] Deploying & calibrating AO loop..."
"${LOOP_CTRL}" deploy
if [[ -f "${OUTDIR}/rm/zrespC.fits" ]]; then
    echo "[slcap] Loading cached RM from ${OUTDIR}/rm ..."
    "${LOOP_CTRL}" load-rm "${OUTDIR}/rm" --svdlim "${SVDLIM}"
else
    "${LOOP_CTRL}" calibrate --nframes 60 --nbloop 2 --svdlim "${SVDLIM}" \
        --save-rm "${OUTDIR}/rm"
fi

echo "[slcap] Running open-loop baseline..."
"${LOOP_CTRL}" zero
csim_set_turb_gain 1.0
shm_wait_frames "csim_wfs" 30 20
csim_reset_long
shm_wait_frames "csim_wfs" 200 25
compute_ao_metrics "ol" "${OUTDIR}/metrics_ol.json"

echo "[slcap] Closing loop (gain=${GAIN}, mult=${MULT}) and warming up..."
"${LOOP_CTRL}" close "${GAIN}"
shm_wait_frames "csim_wfs" 120 20
csim_reset_long

# Arm streamFITSlog on modevalWFS, modevalDM, modevalOL
rm -f "${OUTDIR}/telemetry"/*.fits "${OUTDIR}/telemetry"/*.txt
CSZ=2000
MFC=$(( (NFRAMES + CSZ - 1) / CSZ + 4 ))
for pair in "log_wfs:aol1_modevalWFS" "log_dm:aol1_modevalDM" "log_ol:aol1_modevalOL"; do
    u="${pair%%:*}"
    s="${pair#*:}"
    milk-fps-init -q "${u}" milk-fpsexec-mem-streamFITSlog >/dev/null
    milk-fps-set -q \
        "${u}.sname=${s}" \
        "${u}.dirname=${TLM_LINK}" \
        "${u}.cubesize=${CSZ}" \
        "${u}.maxframecnt=${NFRAMES}" \
        "${u}.maxfilecnt=${MFC}" \
        "${u}.saveON=ON" \
        "${u}.procinfo.loopcntMax=-1" \
        "${u}.procinfo.triggermode=3" \
        "${u}.procinfo.triggersname=${s}" \
        "${u}.procinfo.triggertimeout=0.5"
done
milk-fps-runstart -q log_wfs log_dm log_ol

echo "[slcap] Capturing ${NFRAMES} closed-loop frames..."
shm_wait_frames "aol1_modevalWFS" "${NFRAMES}" 60
milk-fps-runstop -q log_wfs log_dm log_ol
sleep 0.3
compute_ao_metrics "cl" "${OUTDIR}/metrics_cl.json"

"${PYTHON_BIN}" - "${OUTDIR}" <<'PY'
import json, os, sys
od = sys.argv[1]
for s in ("dl", "ol", "cl"):
    d = json.load(open(os.path.join(od, f"metrics_{s}.json")))
    print(f"  {s.upper():3s}: strehl_peak={d['strehl_peak']:.4f}  "
          f"fps_ave={d['strehl_fps_ave']:.4f}  wfs_rms={d['wfs_rms']:.5f}  "
          f"mval_rms={d['mval_rms']:.5f}  dm_rms={d['dm_rms']:.5f}")
PY
echo "[slcap] Saved telemetry -> ${OUTDIR}/telemetry"
