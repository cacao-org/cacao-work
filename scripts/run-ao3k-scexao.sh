#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# End-to-end Subaru 8.2m AO3k + SCExAO two-stage Pyramid WFS simulation:
#   - Stage 1 (AO3k)  : 16x16 DM + Near-IR J-band (1.22 um) PyWFS @ 1.0 kHz physical
#   - Stage 2 (SCExAO): 24x24 DM + Visible I-band (0.75 um) PyWFS @ 2.0 kHz physical
#   - Calibrations    : Zero-turbulence (turb_gain = 0.0) Hadamard RMs, saved for reruns
#   - Closed-Loop Run : 10.0 s physical time (20,000 ticks @ 2 kHz, 0.6" Maunakea seeing,
#                       guide star mV = 6, mH = 6), simultaneous Visible & Near-IR PSFs
#                       at Raw (uncorrected), Stage-1 (post-AO3k), and Final (post-SCExAO).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=shm-sandbox.sh
source "${SCRIPT_DIR}/shm-sandbox.sh"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS=1

SEEING="0.6"
PHYS_TIME="10.0"
WALL_RATE="80"
GAIN1="0.35"
GAIN2="0.35"
MULT1="0.98"
MULT2="0.98"
MGAIN_ALPHA="0.8"
MGAIN_FLOOR="0.10"
MGAIN_TT="1.0"
SVDLIM1="0.008"
SVDLIM2="0.007"
NBLOOP="1"
RUN_SELFRM="1"
SELFRM_MODES="2000"
SELFRM_ONSKY_ITER="1"
OUT_DIR="${CACAO_WORK_ROOT}/_work/ao3k_scexao"
SAVE_RM_DIR="${CACAO_WORK_ROOT}/_work/ao3k_scexao_rm"
LOAD_RM_DIR=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --seeing <arcsec>   Seeing FWHM at 0.50 um (default: ${SEEING})
  --phys-time <sec>   Physical closed-loop integration time [s] (default: ${PHYS_TIME})
  --wall-rate <hz>    Wall-clock master pacing rate [Hz] (default: ${WALL_RATE})
  --gain1 <float>     Stage-1 AO3k integrator gain (default: ${GAIN1})
  --gain2 <float>     Stage-2 SCExAO integrator gain (default: ${GAIN2})
  --mult1 <float>     Stage-1 leak multiplier (default: ${MULT1})
  --mult2 <float>     Stage-2 leak multiplier (default: ${MULT2})
  --mgain-alpha <f>   Modal gain power-law rolloff exponent (default: ${MGAIN_ALPHA})
  --mgain-floor <f>   Modal gain floor factor for highest mode (default: ${MGAIN_FLOOR})
  --mgain-tt <f>      Modal gain factor for Tip/Tilt modes 0,1 (default: ${MGAIN_TT})
  --svdlim1 <float>   Stage-1 SVD truncation threshold (default: ${SVDLIM1})
  --svdlim2 <float>   Stage-2 SVD truncation threshold (default: ${SVDLIM2})
  --nbloop <int>      Hadamard RM averaging cycles per stage (default: ${NBLOOP})
  --selfrm-modes <n>  Max modes probed in selfRM (default: ${SELFRM_MODES} = all)
  --selfrm-iter <n>   On-sky selfRM averaging iterations (default: ${SELFRM_ONSKY_ITER})
  --no-selfrm         Skip calibration and on-sky selfRM acquisition
  --save-rm <dir>     Directory to save Stage-1 & Stage-2 RMs (default: ${SAVE_RM_DIR})
  --load-rm <dir>     Load pre-saved RMs from <dir>/stage1 and <dir>/stage2
  --outdir <dir>      Output directory for FITS PSFs, plots, & JSON (default: ${OUT_DIR})
  -h, --help          Show this help message
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --seeing)    SEEING="$2"; shift 2 ;;
        --phys-time) PHYS_TIME="$2"; shift 2 ;;
        --wall-rate) WALL_RATE="$2"; shift 2 ;;
        --gain1)     GAIN1="$2"; shift 2 ;;
        --gain2)     GAIN2="$2"; shift 2 ;;
        --mult1)       MULT1="$2"; shift 2 ;;
        --mult2)       MULT2="$2"; shift 2 ;;
        --mgain-alpha) MGAIN_ALPHA="$2"; shift 2 ;;
        --mgain-floor) MGAIN_FLOOR="$2"; shift 2 ;;
        --mgain-tt)    MGAIN_TT="$2"; shift 2 ;;
        --svdlim1)      SVDLIM1="$2"; shift 2 ;;
        --svdlim2)      SVDLIM2="$2"; shift 2 ;;
        --nbloop)       NBLOOP="$2"; shift 2 ;;
        --selfrm-modes) SELFRM_MODES="$2"; shift 2 ;;
        --selfrm-iter)  SELFRM_ONSKY_ITER="$2"; shift 2 ;;
        --no-selfrm)    RUN_SELFRM="0"; shift ;;
        --save-rm)   SAVE_RM_DIR="$2"; shift 2 ;;
        --load-rm)   LOAD_RM_DIR="$2"; shift 2 ;;
        --outdir)    OUT_DIR="$2"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *) echo "[ao3k-scexao] Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

OUT_DIR="$(realpath -m "${OUT_DIR}")"
if [[ -n "${SAVE_RM_DIR}" ]]; then
    SAVE_RM_DIR="$(realpath -m "${SAVE_RM_DIR}")"
fi
if [[ -n "${LOAD_RM_DIR}" ]]; then
    LOAD_RM_DIR="$(realpath -m "${LOAD_RM_DIR}")"
fi
mkdir -p "${OUT_DIR}"

MASTER_TICKS="$(awk -v t="${PHYS_TIME}" 'BEGIN { printf "%d", int(t * 2000.0 + 0.5) }')"
LONG_READOUTS=$(( MASTER_TICKS / 20 ))
if (( LONG_READOUTS < 1 )); then
    LONG_READOUTS=1
fi
WALL_DT="$(awk -v r="${WALL_RATE}" 'BEGIN { printf "%.7f", 1.0 / r }')"
WFS1_WALL_RATE="$(awk -v r="${WALL_RATE}" 'BEGIN { printf "%.2f", 0.5 * r }')"

BENCH_CFG="${CACAO_WORK_ROOT}/benches/ao3k_scexao/ao3k_scexao.bench"
LOOP_CTRL="${CACAO_WORK_ROOT}/benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk"

sandbox_init "ao3k"
STG1_ROOT="${SANDBOX_WORK_DIR}/ao3k"
STG2_ROOT="${SANDBOX_WORK_DIR}/scexao"
WF_STOP_FILE="${SANDBOX_WORK_DIR}/wf_recorder.stop"
WF_READY_FILE="${SANDBOX_WORK_DIR}/wf_recorder.ready"
WF_REC_PID=""

cleanup_run() {
    if [[ -n "${WF_REC_PID}" ]]; then
        touch "${WF_STOP_FILE}" >/dev/null 2>&1 || true
        wait "${WF_REC_PID}" >/dev/null 2>&1 || true
    fi
    CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 teardown --purge-dm \
        >/dev/null 2>&1 || true
    CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 teardown --purge-dm \
        >/dev/null 2>&1 || true
    sandbox_cleanup
}
trap cleanup_run EXIT

get_stream_cnt0() {
    local sname="$1"
    milk-script -q -e <<EOF
@get _c="s.${sname}.cnt0"
printf '%s\n' "\${_c}"
EOF
}

echo "================================================================================"
echo " Subaru 8.2m AO3k + SCExAO Two-Stage Pyramid WFS Simulation"
echo "   Sandbox SHM : ${MILK_SHM_DIR}"
echo "   Seeing      : ${SEEING}\" @ 0.50 um | Star: mV = 6.0, mH = 6.0 (Teff = 9600 K)"
echo "   Loop Speeds : Stage 1 (AO3k NIR) = 1.0 kHz | Stage 2 (SCExAO Vis) = 2.0 kHz"
echo "   Integration : ${PHYS_TIME} s physical (${MASTER_TICKS} ticks, ${LONG_READOUTS} exposures)"
echo "   Wall Pacing : ${WALL_RATE} Hz master (${WFS1_WALL_RATE} Hz Stg1, ${WALL_RATE} Hz Stg2)"
echo "================================================================================"

echo "[ao3k-scexao] Step 1/7: Deploying modular optical bench (turb_gain = 0.0)..."
cacaosim-bench deploy \
    --workdir "${CACAOSIM_WORKDIR}" \
    --config "${BENCH_CFG}" \
    --mode modular \
    --atmturb \
    --seeing "${SEEING}" \
    --no-view >/dev/null

# Pause atmospheric generator & run optical bench cleanly with zero turbulence
milk-fps-runstop -q csim_mkbeam csim_atmturb
milk-fps-set -q \
    "csim_mkbeam.turb_gain=0.0" \
    "csim_mkbeam.frame_rate=${WALL_RATE}" \
    "csim_mkbeam.procinfo.triggermode=0"
milk-fps-runstart -q csim_mkbeam
shm_wait_stream "csim_wfs_nir" 20
shm_wait_stream "csim_wfs_vis" 20
shm_wait_stream "psf_vis_final_long" 20
shm_wait_stream "psf_nir_final_long" 20

echo "[ao3k-scexao] Step 2/7: Acquiring diffraction-limited reference PSFs (turb = 0)..."
shm_wait_frames "csim_wfs_vis" 40 20
csim_reset_long
shm_wait_frames "psf_vis_final_long" 15 30
shm_dump_fits "psf_vis_final_long" "${OUT_DIR}/psf_vis_dl.fits"
shm_dump_fits "psf_nir_final_long" "${OUT_DIR}/psf_nir_dl.fits"
for cam in vis_raw nir_raw vis_stg1 nir_stg1 vis_final nir_final; do
    shm_dump_fits "psf_${cam}" "${OUT_DIR}/det_${cam}_dl.fits"
done

echo "[ao3k-scexao] Step 3/7: Deploying Stage-1 (AO3k 16x16) & Stage-2 (SCExAO 24x24) loops..."
CACAO_LOOPROOTDIR="${STG1_ROOT}" \
CACAO_WFSFRATE="${WFS1_WALL_RATE}" \
CACAO_LOOPGAIN="${GAIN1}" \
CACAO_LOOPMULT="${MULT1}" \
    "${LOOP_CTRL}" --stage 1 deploy

CACAO_LOOPROOTDIR="${STG2_ROOT}" \
CACAO_WFSFRATE="${WALL_RATE}" \
CACAO_LOOPGAIN="${GAIN2}" \
CACAO_LOOPMULT="${MULT2}" \
    "${LOOP_CTRL}" --stage 2 deploy

CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 zero
CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 zero
shm_wait_frames "csim_wfs_vis" 20 20

TURB_CAL="$(milk-script -q -e <<< '@get v="f.csim_mkbeam.turb_gain"; printf "%s\n" "${v}"')"
echo "[ao3k-scexao] Step 4/7: Calibrating RMs with NO turbulence (turb_gain = ${TURB_CAL})..."

declare -a CAL1_ARGS=(--nframes 60 --nbloop "${NBLOOP}" --svdlim "${SVDLIM1}")
declare -a CAL2_ARGS=(--nframes 60 --nbloop "${NBLOOP}" --svdlim "${SVDLIM2}")
if [[ -n "${LOAD_RM_DIR}" ]]; then
    CAL1_ARGS+=(--load-rm "${LOAD_RM_DIR}/stage1")
    CAL2_ARGS+=(--load-rm "${LOAD_RM_DIR}/stage2")
fi
if [[ -n "${SAVE_RM_DIR}" ]]; then
    CAL1_ARGS+=(--save-rm "${SAVE_RM_DIR}/stage1")
    CAL2_ARGS+=(--save-rm "${SAVE_RM_DIR}/stage2")
fi

t_cal1_0="$(date +%s)"
echo "[ao3k-scexao]   -> Stage 1 (AO3k, 16x16 DM, J-band PyWFS)..."
CACAO_LOOPROOTDIR="${STG1_ROOT}" \
CACAO_WFSFRATE="${WFS1_WALL_RATE}" \
CACAO_MGAIN_ALPHA="${MGAIN_ALPHA}" \
CACAO_MGAIN_FLOOR="${MGAIN_FLOOR}" \
CACAO_MGAIN_TT="${MGAIN_TT}" \
    "${LOOP_CTRL}" --stage 1 calibrate "${CAL1_ARGS[@]}"
CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 zero
shm_wait_frames "csim_wfs_vis" 20 20
t_cal1_1="$(date +%s)"
echo "[ao3k-scexao]      Stage-1 calibration done in $(( t_cal1_1 - t_cal1_0 )) s."

t_cal2_0="$(date +%s)"
echo "[ao3k-scexao]   -> Stage 2 (SCExAO, 24x24 DM, Vis PyWFS)..."
CACAO_LOOPROOTDIR="${STG2_ROOT}" \
CACAO_WFSFRATE="${WALL_RATE}" \
CACAO_MGAIN_ALPHA="${MGAIN_ALPHA}" \
CACAO_MGAIN_FLOOR="${MGAIN_FLOOR}" \
CACAO_MGAIN_TT="${MGAIN_TT}" \
    "${LOOP_CTRL}" --stage 2 calibrate "${CAL2_ARGS[@]}"
CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 zero
shm_wait_frames "csim_wfs_vis" 20 20
t_cal2_1="$(date +%s)"
echo "[ao3k-scexao]      Stage-2 calibration done in $(( t_cal2_1 - t_cal2_0 )) s."

if (( RUN_SELFRM )); then
    echo "[ao3k-scexao] Step 4b/7: Acquiring calibration selfRM (no turbulence, open-loop)..."
    t_srmc_0="$(date +%s)"
    CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 selfrm \
        "${OUT_DIR}/selfRM_calib_stg1.fits" \
        --nbmode "${SELFRM_MODES}" --ampl 0.015 --nbiter 1 --nbsettle 2
    cp -f "${OUT_DIR}/selfRM_calib_stg1.fits" "${STG1_ROOT}/conf/selfRM_calib.fits"
    CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 zero
    shm_wait_frames "csim_wfs_vis" 15 20

    CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 selfrm \
        "${OUT_DIR}/selfRM_calib_stg2.fits" \
        --nbmode "${SELFRM_MODES}" --ampl 0.010 --nbiter 1 --nbsettle 2
    cp -f "${OUT_DIR}/selfRM_calib_stg2.fits" "${STG2_ROOT}/conf/selfRM_calib.fits"
    CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 zero
    shm_wait_frames "csim_wfs_vis" 15 20

    if [[ -n "${SAVE_RM_DIR}" ]]; then
        CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 save-rm "${SAVE_RM_DIR}/stage1"
        CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 save-rm "${SAVE_RM_DIR}/stage2"
    fi
    t_srmc_1="$(date +%s)"
    echo "[ao3k-scexao]      Calibration selfRM done in $(( t_srmc_1 - t_srmc_0 )) s."
fi

echo "[ao3k-scexao] Step 5/7: Enabling 1:1 lockstep Maunakea turbulence (${SEEING}\", dt=0.5 ms)..."
milk-fps-runstop -q csim_mkbeam csim_atmturb
milk-fps-set -q \
    "csim_atmturb.seeing=${SEEING}" \
    "csim_atmturb.time_step=0.0005" \
    "csim_atmturb.procinfo.triggermode=4" \
    "csim_atmturb.procinfo.triggerdelay=${WALL_DT}" \
    "csim_mkbeam.turb_gain=1.0" \
    "csim_mkbeam.frame_rate=0.0" \
    "csim_mkbeam.procinfo.triggermode=3" \
    "csim_mkbeam.procinfo.triggersname=outarraypha"
milk-fps-runstart -q csim_atmturb
shm_wait_frames "outarraypha" 5 30
milk-fps-runstart -q csim_mkbeam
shm_wait_frames "csim_wfs_vis" 20 30

echo "[ao3k-scexao] Step 6/7: Closing Stage 1 (1 kHz) -> Stage 2 (2 kHz) (${PHYS_TIME} s)..."
CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 close "${GAIN1}"
shm_wait_frames "csim_wfs_vis" 100 30
CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 close "${GAIN2}"
shm_wait_frames "csim_wfs_vis" 200 30

cnt_pha_0="$(get_stream_cnt0 outarraypha)"
cnt_wfs1_0="$(get_stream_cnt0 csim_wfs_nir)"
cnt_wfs2_0="$(get_stream_cnt0 csim_wfs_vis)"
cnt_long_0="$(get_stream_cnt0 psf_vis_final_long)"

rm -f "${WF_STOP_FILE}" "${WF_READY_FILE}"
"${PYTHON_BIN}" "${CACAO_WORK_ROOT}/scripts/record-ao3k-scexao-wf.py" \
    "${OUT_DIR}" "${MASTER_TICKS}" "${WF_STOP_FILE}" "${WF_READY_FILE}" &
WF_REC_PID=$!
for _ in $(seq 1 100); do
    [[ -f "${WF_READY_FILE}" ]] && break
    sleep 0.02
done

t_int_0="$(date +%s.%N)"

csim_reset_long

rem="${LONG_READOUTS}"
done_rd=0
chunk=100
while (( rem > 0 )); do
    step=$(( rem < chunk ? rem : chunk ))
    shm_wait_frames "psf_vis_final_long" "${step}" 60
    rem=$(( rem - step ))
    done_rd=$(( done_rd + step ))
    phys_done="$(awk -v d="${done_rd}" 'BEGIN { printf "%.2f", d * 0.01 }')"
    sr_live="$(milk-script -q -e <<'EOF'
@get s1="f.csim_nir_stg1.strehl_ave" s2="f.csim_nir_final.strehl_ave"
@get sv="f.csim_vis_final.strehl_ave"
printf 'NIR_Stg1=%.3f NIR_Final=%.3f Vis_Final=%.3f\n' "${s1}" "${s2}" "${sv}"
EOF
)"
    echo "[ao3k-scexao]      t_phys = ${phys_done} / ${PHYS_TIME} s  (${sr_live})"
done

t_int_1="$(date +%s.%N)"
cnt_pha_1="$(get_stream_cnt0 outarraypha)"
cnt_wfs1_1="$(get_stream_cnt0 csim_wfs_nir)"
cnt_wfs2_1="$(get_stream_cnt0 csim_wfs_vis)"
cnt_long_1="$(get_stream_cnt0 psf_vis_final_long)"

# Freeze master turbulence clock so all 6 cameras dump identical 10.0 s snapshots
milk-fps-runstop -q csim_atmturb
sleep 0.2
touch "${WF_STOP_FILE}"
wait "${WF_REC_PID}"
WF_REC_PID=""

d_pha=$(( cnt_pha_1 - cnt_pha_0 ))
d_wfs1=$(( cnt_wfs1_1 - cnt_wfs1_0 ))
d_wfs2=$(( cnt_wfs2_1 - cnt_wfs2_0 ))
d_long=$(( cnt_long_1 - cnt_long_0 ))
WALL_ELAPSED="$(awk -v t0="${t_int_0}" -v t1="${t_int_1}" 'BEGIN { printf "%.2f", t1 - t0 }')"

echo "[ao3k-scexao]      Completed in ${WALL_ELAPSED} s wall-clock:"
echo "[ao3k-scexao]      d(pha)=${d_pha}, d(wfs1)=${d_wfs1}, d(wfs2)=${d_wfs2}, d(long)=${d_long}"

echo "[ao3k-scexao] Step 7/7: Saving integrated PSFs, loop telemetry, & generating plots..."
for cam in vis_raw nir_raw vis_stg1 nir_stg1 vis_final nir_final; do
    shm_dump_fits "psf_${cam}_long" "${OUT_DIR}/psf_${cam}.fits"
    shm_dump_fits "psf_${cam}" "${OUT_DIR}/det_${cam}.fits"
done

for n in 1 2; do
    for sfx in imWFS2 modevalWFS modevalDM mgain mgainfact dmC; do
        if [[ -e "${MILK_SHM_DIR}/aol${n}_${sfx}.im.shm" ]]; then
            shm_dump_fits "aol${n}_${sfx}" "${OUT_DIR}/aol${n}_${sfx}.fits"
        fi
    done
done

if (( RUN_SELFRM )); then
    echo "[ao3k-scexao] Step 6b/7: Acquiring on-sky closed-loop selfRM (${SEEING}\" seeing)..."
    t_srms_0="$(date +%s)"
    milk-fps-runstart -q csim_atmturb
    shm_wait_frames "csim_wfs_vis" 40 30

    CACAO_LOOPROOTDIR="${STG1_ROOT}" "${LOOP_CTRL}" --stage 1 selfrm \
        "${OUT_DIR}/selfRM_onsky_stg1.fits" \
        --nbmode "${SELFRM_MODES}" --ampl 0.030 --nbiter "${SELFRM_ONSKY_ITER}" --nbsettle 6
    shm_wait_frames "csim_wfs_vis" 40 30

    CACAO_LOOPROOTDIR="${STG2_ROOT}" "${LOOP_CTRL}" --stage 2 selfrm \
        "${OUT_DIR}/selfRM_onsky_stg2.fits" \
        --nbmode "${SELFRM_MODES}" --ampl 0.020 --nbiter "${SELFRM_ONSKY_ITER}" --nbsettle 6

    milk-fps-runstop -q csim_atmturb
    t_srms_1="$(date +%s)"
    echo "[ao3k-scexao]      On-sky selfRM done in $(( t_srms_1 - t_srms_0 )) s."
fi

for stg_pair in "1:${STG1_ROOT}" "2:${STG2_ROOT}"; do
    sn="${stg_pair%%:*}"
    sroot="${stg_pair#*:}"
    for mf in mlat_hardwlatency.dat mlat_hardwlatencypts.dat mlat_diffseq.fits; do
        if [[ -f "${sroot}/conf/${mf}" ]]; then
            cp -f "${sroot}/conf/${mf}" "${OUT_DIR}/stg${sn}_${mf}"
        fi
    done
done

"${PYTHON_BIN}" "${CACAO_WORK_ROOT}/scripts/analyze-ao3k-scexao.py" \
    "${SANDBOX_WORK_DIR}" \
    "${OUT_DIR}" \
    "${SEEING}" \
    "${PHYS_TIME}" \
    "${d_pha}" \
    "${WALL_ELAPSED}" \
    "${GAIN1}" \
    "${GAIN2}" \
    "${MULT1}" \
    "${MULT2}" \
    "${MGAIN_ALPHA}" \
    "${MGAIN_FLOOR}" \
    "${MGAIN_TT}"

if [[ -n "${SAVE_RM_DIR}" ]]; then
    echo "[ao3k-scexao] Saved Stage-1 & Stage-2 response matrices in: ${SAVE_RM_DIR}"
fi
echo "[ao3k-scexao] Results & figures written to: ${OUT_DIR}"
