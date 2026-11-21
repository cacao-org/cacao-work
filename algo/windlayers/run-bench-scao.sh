#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Wind-layer unit on the closed-loop scao_pyr bench, with scintillation: deploys the bench and
# the cacao loop in an isolated sandbox, runs cacao-fpsexec-windlayers on the live WFS and DM
# streams, prints the layers next to the simulated profile, and tears everything down.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../env.sh
source "${SCRIPT_DIR}/../../env.sh"
# shellcheck source=../../scripts/shm-sandbox.sh
source "${CACAO_WORK_ROOT}/scripts/shm-sandbox.sh"

RATE="400"
SLOW="4"
TINT="60"
SEEING="0.7"
GAIN="0.35"
PHA="dm"
KEEP_RUNNING=0
EXTRA=()

usage() {
    cat <<'EOF'
Usage: run-bench-scao.sh [options] [key=value ...]

Options:
  --rate <hz>        WFS and turbulence frame rate, physical [Hz] (default: 400)
  --slow <factor>    Run the simulation this many times slower than real time (default: 4).
                     Raise it when "turbulence frames" and "WFS frames" differ in the output:
                     the simulator then drops frames and every wind speed reads too high.
  --tint <s>         Physical time to integrate [s] (default: 60)
  --seeing <arcsec>  Seeing (default: 0.7)
  --gain <float>     Loop gain (default: 0.35)
  --pha <dm|none>    Phase space from the DM commands (default), or from the pyramid slopes
  --keep-running     Leave the bench, the loop and the unit running
  -h, --help         Show this help
  key=value          Extra parameters of the unit (e.g. corefrac=0.8)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rate) RATE="$2"; shift 2 ;;
        --slow) SLOW="$2"; shift 2 ;;
        --tint) TINT="$2"; shift 2 ;;
        --seeing) SEEING="$2"; shift 2 ;;
        --gain) GAIN="$2"; shift 2 ;;
        --pha) PHA="$2"; shift 2 ;;
        --keep-running) KEEP_RUNNING=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *=*) EXTRA+=("$1"); shift ;;
        *) echo "[windlayers-bench] ERROR: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
    esac
done

sandbox_init "windlay"
if [[ "${KEEP_RUNNING}" -eq 1 ]]; then
    SANDBOX_KEEP=1
fi

export CACAO_LOOPNAME="scao_pyr"
export CACAO_LOOPNUMBER=1
export CACAO_LOOPROOTDIR="${SANDBOX_WORK_DIR}/scao_pyr"
export CACAO_WFSFRATE="${RATE}"
export CACAO_LOOPGAIN="${GAIN}"
export ATMTURB_MASTER_SIZE="${ATMTURB_MASTER_SIZE:-2048}"

LOOP_CTRL="${CACAO_WORK_ROOT}/benches/scao_pyr/cacaoloop-scao-pyr.milk"
WL="${SCRIPT_DIR}/windlayers.milk"
BENCH="${SANDBOX_WORK_DIR}/scao_pyr_scint.bench"
PROF="${ATMTURB_SRC_DIR}/src/AtmosphericTurbulence/turbul.prof"

cleanup_run() {
    if [[ "${KEEP_RUNNING}" -eq 0 ]]; then
        "${WL}" stop --rm >/dev/null 2>&1 || true
        "${LOOP_CTRL}" teardown --purge-dm >/dev/null 2>&1 || true
    fi
    sandbox_cleanup
}
trap cleanup_run EXIT
cd "${SANDBOX_WORK_DIR}"

echo "[windlayers-bench] 1/6 Deploying scao_pyr with a scintillation input (${RATE} Hz)..."
sed '/^in_pup/a in_amp     = "outarrayamp"' \
    "${CACAO_WORK_ROOT}/benches/scao_pyr/scao_pyr.bench" > "${BENCH}"
cacaosim-bench deploy --workdir "${CACAOSIM_WORKDIR}" --config "${BENCH}" --mode fused \
    --rate "${RATE}" --atmturb --seeing "${SEEING}" --no-view >/dev/null
milk-stream-wait -q -t 20 outarraypha csim_wfs

echo "[windlayers-bench] 2/6 Calibrating the AO loop without turbulence..."
csim_set_turb_gain 0.0
shm_wait_frames "csim_wfs" 20 15
"${LOOP_CTRL}" deploy >/dev/null 2>&1
"${LOOP_CTRL}" calibrate --nframes 60 --nbloop 2 --svdlim 0.05 >/dev/null 2>&1

echo "[windlayers-bench] 3/6 Turbulence with Fresnel propagation (Rytov), ${SLOW}x slower..."
milk-fps-runstop -q csim_atmturb
milk-fps-wait -q -t 10 csim_atmturb >/dev/null 2>&1 || true
milk-fps-set -q "csim_atmturb.amplitude=1" "csim_atmturb.fresnel=2"
milk-fps-runstart -q csim_atmturb
milk-stream-wait -q -t 20 outarrayamp outarraypha
# physics unchanged, wall clock slower: both clocks by the same factor
milk-script -q -e <<EOF
@get fr=f.csim_htsim.frame_rate
@calc -v nfr "\${fr} / ${SLOW}"
@calc -v ntd "${SLOW} / ${RATE}"
@set "f.csim_htsim.frame_rate=\${nfr}" "f.csim_atmturb.procinfo.triggerdelay=\${ntd}"
EOF

echo "[windlayers-bench] 4/6 Closing the loop..."
csim_set_turb_gain 1.0
"${LOOP_CTRL}" close "${GAIN}" >/dev/null 2>&1
shm_wait_frames "csim_wfs" "$(( RATE * 2 ))" "$(( 4 * SLOW + 20 ))"

echo "[windlayers-bench] 5/6 Wind-layer unit on csim_wfs" \
     "$([[ "${PHA}" == "dm" ]] && echo "+ dm00disp" || echo "(pyramid slopes)")..."
TBIN=$(( RATE / 200 ))
(( TBIN >= 1 )) || TBIN=1
# scao_pyr: 8.2 m pupil, modulation 3 lambda/D at 0.75 um; 12 actuators span the pupil
# (pitch 8.2 m / 11), Gaussian influence of coupling 0.22, OPD = 2 x stroke [um]
UNIT_ARGS=(frate="${RATE}" tbin="${TBIN}" diam=8.2 modrad=3 lambda=0.75 vmax=30 tupdate=10)
if [[ "${PHA}" == "dm" ]]; then
    "${WL}" start csim_wfs dm00disp "${UNIT_ARGS[@]}" phaunit=2e-6 phapitch=0.7455 \
        phaifc=0.22 phalag=2 "${EXTRA[@]}"
else
    "${WL}" start csim_wfs "${UNIT_ARGS[@]}" "${EXTRA[@]}"
fi

TMO=$(( (TINT + 30) * SLOW + 60 ))
milk-script -q -e <<EOF
@get a0=s.outarraypha.cnt0 w0=s.csim_wfs.cnt0
@waitfor "f.windlayers.res.tint >= ${TINT}" -t ${TMO} || echo "[windlayers-bench] timed out"
@get a1=s.outarraypha.cnt0 w1=s.csim_wfs.cnt0 ti=f.windlayers.res.tint ng=f.windlayers.res.ngaps
@get sa=f.csim_htsim.strehl_ave
echo "[windlayers-bench] turbulence frames \$((a1 - a0)), WFS frames \$((w1 - w0))" \
     "(must match); integrated \${ti} s; unit frame gaps \${ng}; H-band Strehl \${sa}"
EOF

echo "[windlayers-bench] 6/6 Layers found:"
"${WL}" report
echo "[windlayers-bench] Simulated layers (pattern velocity = -wind of the profile):"
awk 'BEGIN { n = 0 }
     !/^#/ && NF >= 4 { alt[n] = $1; cn[n] = $2; sp[n] = $3; di[n] = $4; tot += $2
                         if (n == 0 || $1 < min) min = $1
                         n++ }
     END { printf "    %8s %8s %8s %7s %10s %7s\n", "vx[m/s]", "vy[m/s]", "speed", "dir",
                  "z[m]", "cn2"
           for (i = 0; i < n; i++) {
               d = di[i] * 180 / 3.14159265 + 180; while (d >= 360) d -= 360
               printf "    %8.2f %8.2f %8.2f %7.1f %10.0f %7.3f\n", -sp[i] * cos(di[i]),
                      -sp[i] * sin(di[i]), sp[i], d, alt[i] - min, cn[i] / tot } }' "${PROF}"
