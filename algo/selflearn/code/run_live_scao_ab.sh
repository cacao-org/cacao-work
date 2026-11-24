#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Live GPU closed-loop A/B exercise of cacao-fpsexec-cacaopc-selflearn on scao_pyr
# (unmodulated or modulated PyWFS), measuring optical H-band Strehl, WFS residual RMS,
# and online GRIC + hierarchical RLS telemetry across:
#   OL -> CL_INT -> CL_ARPF -> CL_SL_SHADOW -> CL_SL_L0 -> CL_SL_GRIC -> CL_ARPF_SL -> CL_SL_AUX

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
# shellcheck source=../../../env.sh
source "${REPO_ROOT}/env.sh"
# shellcheck source=../../../scripts/shm-sandbox.sh
source "${REPO_ROOT}/scripts/shm-sandbox.sh"

MOD_RAD="${1:-0.0}"
SEEING="${2:-0.35}"
EVAL_FRAMES="${3:-600}"
RM_DIR="${4:-}"
OUT_JSON="${5:-${REPO_ROOT}/_work/selflearn_ab_mod${MOD_RAD}_s${SEEING}.json}"
RATE="${RATE:-400}"
GAIN="${GAIN:-0.30}"
MULT="${MULT:-0.98}"
SVDLIM="${SVDLIM:-0.05}"
KEY_MODE="${KEY_MODE:-0}"
RLIM="${RLIM:-2.0}"
KMAX="${KMAX:-16}"
PF_MIX="${PF_MIX:-0.90}"

mkdir -p "$(dirname "${OUT_JSON}")"

sandbox_init "slab"
LOOP_CTRL="${REPO_ROOT}/benches/scao_pyr/cacaoloop-scao-pyr.milk"
export CACAO_LOOPNAME="scao_pyr"
export CACAO_LOOPNUMBER=1
export CACAO_LOOPROOTDIR="${SANDBOX_WORK_DIR}/scao_pyr"
export CACAO_WFSFRATE="${RATE}"
export CACAO_LOOPGAIN="${GAIN}"
export CACAO_LOOPMULT="${MULT}"
export CACAO_SVDLIM="${SVDLIM}"

cleanup_ab() {
    milk-fps-runstop -q sl-1 sl_cas-1 sl_aux-1 >/dev/null 2>&1 || true
    milk-fps-rm -f -q --ignore-missing sl-1 sl_cas-1 sl_aux-1 >/dev/null 2>&1 || true
    "${LOOP_CTRL}" teardown --purge-dm >/dev/null 2>&1 || true
    sandbox_cleanup
}
trap cleanup_ab EXIT

BENCH_CFG="${SANDBOX_WORK_DIR}/scao_ab.bench"
awk -v mr="${MOD_RAD}" '
/^mod_rad[ \t]*=/ { printf "mod_rad       = %s\n", mr; next }
/^mod_npts[ \t]*=/ { if (mr + 0 == 0) { printf "mod_npts      = 1\n"; next } }
{ print }
' "${REPO_ROOT}/benches/scao_pyr/scao_pyr.bench" > "${BENCH_CFG}"

echo "[slab] 1/9 Deploying scao_pyr (mod_rad=${MOD_RAD}, seeing=${SEEING}\", rate=${RATE} Hz)..."
cacaosim-bench deploy \
    --workdir "${CACAOSIM_WORKDIR}" \
    --config "${BENCH_CFG}" \
    --mode fused \
    --rate "${RATE}" \
    --atmturb \
    --seeing "${SEEING}" \
    --no-view >/dev/null

milk-stream-wait -q -t 20 outarraypha csim_wfs csim_fpcam csim_fplong

echo "[slab] 2/9 Diffraction-limited reference..."
csim_set_turb_gain 0.0
shm_wait_frames "csim_wfs" 15 15
csim_reset_long
shm_wait_frames "csim_wfs" 30 15
compute_ao_metrics "dl" "${SANDBOX_WORK_DIR}/m_dl.json"

echo "[slab] 3/9 Deploying & calibrating AO loop..."
"${LOOP_CTRL}" deploy
if [[ -n "${RM_DIR}" && -f "${RM_DIR}/zrespC.fits" ]]; then
    "${LOOP_CTRL}" load-rm "${RM_DIR}" --svdlim "${SVDLIM}"
else
    cal_args=(calibrate --nframes 60 --nbloop 2 --svdlim "${SVDLIM}")
    if [[ -n "${RM_DIR}" ]]; then
        mkdir -p "${RM_DIR}"
        cal_args+=(--save-rm "${RM_DIR}")
    fi
    "${LOOP_CTRL}" "${cal_args[@]}"
fi

# Read measured latency from mfilt-1
LAT_TOT="$(milk-script -q -e <<'MS'
@get lh="f.mfilt-1.comp.latencyhardwfr" ls="f.mfilt-1.comp.latencysoftwfr"
awk -v a="${lh:-1.5}" -v b="${ls:-0.6}" 'BEGIN { printf "%.3f\n", a + b }'
MS
)"
echo "[slab]     Measured total loop latency: ${LAT_TOT} frames"

dump_sl_diag() {
    local uname="$1"
    local outf="$2"
    milk-script -q -e <<MS > "${outf}"
@get fr="f.${uname}.out.frames" up="f.${uname}.out.updates" ol="f.${uname}.out.outliers" \
     ga="f.${uname}.out.gric_active" nc="f.${uname}.out.n_clusters" \
     cid="f.${uname}.out.last_cid" dst="f.${uname}.out.last_dist" \
     a0="f.${uname}.out.alpha_l0" a1="f.${uname}.out.alpha_l1" \
     vr0="f.${uname}.out.oos_vr_l0_pct" vr1="f.${uname}.out.oos_vr_l1_pct" \
     vrt="f.${uname}.out.oos_vr_tot_pct" tr="f.${uname}.out.tweak_rms" \
     lr="f.${uname}.out.l1_rms"
printf '{"frames":%s,"updates":%s,"outliers":%s,"gric_active":%s,"n_clusters":%s,' \
    "\${fr:-0}" "\${up:-0}" "\${ol:-0}" "\${ga:-0}" "\${nc:-0}"
printf '"last_cid":%s,"last_dist":%s,"alpha_l0":%s,"alpha_l1":%s,' \
    "\${cid:--1}" "\${dst:-0}" "\${a0:-0}" "\${a1:-0}"
printf '"oos_vr_l0_pct":%s,"oos_vr_l1_pct":%s,"oos_vr_tot_pct":%s,' \
    "\${vr0:-0}" "\${vr1:-0}" "\${vrt:-0}"
printf '"tweak_rms":%s,"l1_rms":%s}\n' "\${tr:-0}" "\${lr:-0}"
MS
}

echo "[slab] 4/9 Open-loop baseline..."
"${LOOP_CTRL}" zero
csim_set_turb_gain 1.0
shm_wait_frames "csim_wfs" 30 20
csim_reset_long
shm_wait_frames "csim_wfs" 240 25
compute_ao_metrics "ol" "${SANDBOX_WORK_DIR}/m_ol.json"

echo "[slab] 5/9 Closed-loop leaky integrator (gain=${GAIN}, mult=${MULT})..."
"${LOOP_CTRL}" close "${GAIN}"
shm_wait_frames "csim_wfs" 150 25
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 40
compute_ao_metrics "cl_int" "${SANDBOX_WORK_DIR}/m_cl_int.json"

echo "[slab] 6/9 Standard linear AR predictive filter (mkARPF + applyARPF)..."
"${LOOP_CTRL}" pf-on "${PF_MIX}" "${LAT_TOT}"
shm_wait_frames "aol1_arPFmat" 1 30
shm_wait_frames "csim_wfs" 200 30
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 40
compute_ao_metrics "cl_arpf" "${SANDBOX_WORK_DIR}/m_cl_arpf.json"
"${LOOP_CTRL}" pf-off
shm_wait_frames "csim_wfs" 80 20

echo "[slab] 7/9 cacaopc-selflearn (PF mode): Shadow -> L0 only -> L0+L1 GRIC..."
milk-fps-init -q sl-1 cacao-fpsexec-cacaopc-selflearn >/dev/null
milk-fps-set -q \
    sl-1.AOloopindex=1 \
    sl-1.inwfs=aol1_modevalWFS \
    sl-1.inol=aol1_modevalOL \
    sl-1.indm=aol1_modevalDM \
    sl-1.outdata=aol1_modevalPF \
    sl-1.outPFstat=aol1_outPFstat \
    sl-1.outtweak=aol1_selflearn_tweak \
    sl-1.out_mode=0 \
    sl-1.key_mode="${KEY_MODE}" \
    sl-1.NBmodeMax=64 \
    sl-1.kmax="${KMAX}" \
    sl-1.qshared=2 \
    sl-1.nwarmup=40 \
    sl-1.keywarmup=200 \
    sl-1.rampsteps=32 \
    sl-1.blend_soft=ON \
    sl-1.rlim="${RLIM}" \
    sl-1.gate_mult=1.5 \
    sl-1.blend_bw=1.0 \
    sl-1.tm_mix=0.5 \
    sl-1.latency="${LAT_TOT}" \
    sl-1.dc_leak=0.985 \
    sl-1.max_wfs_gain=0.40 \
    sl-1.max_ar_norm2=2.0 \
    sl-1.lam0=20.0 \
    sl-1.lam1=200.0 \
    sl-1.gamma0=0.998 \
    sl-1.gamma1=0.995 \
    sl-1.gate_eta=0.995 \
    sl-1.max_tweak=0.25 \
    sl-1.learnON=ON \
    sl-1.shadow=ON \
    sl-1.enable_l0=ON \
    sl-1.enable_l1=ON \
    sl-1.apply_gain=1.0 \
    sl-1.procinfo.loopcntMax=-1 \
    sl-1.procinfo.triggermode=3 \
    sl-1.procinfo.triggersname=aol1_modevalOL
milk-fps-runstart -q sl-1

# Wait for shadow learning (~800 frames = 2 s physical time) while integrator runs
shm_wait_frames "aol1_selflearn_tweak" 800 40
dump_sl_diag "sl-1" "${SANDBOX_WORK_DIR}/d_sl_shadow.json"
csim_reset_long
shm_wait_frames "csim_wfs" 240 30
compute_ao_metrics "cl_sl_shadow" "${SANDBOX_WORK_DIR}/m_cl_sl_shadow.json"

# Activate Level-0 online RLS only in synchronous PF mode
milk-fps-set -q sl-1.shadow=OFF sl-1.enable_l0=ON sl-1.enable_l1=OFF
milk-fps-set -q mfilt-1.PF.mixcoeff="${PF_MIX}" mfilt-1.PF.enable=ON
shm_wait_frames "csim_wfs" 200 30
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 40
compute_ao_metrics "cl_sl_l0" "${SANDBOX_WORK_DIR}/m_cl_sl_l0.json"
dump_sl_diag "sl-1" "${SANDBOX_WORK_DIR}/d_sl_l0.json"

# Activate Level-0 + Level-1 GRIC clustering in synchronous PF mode
milk-fps-set -q sl-1.enable_l0=ON sl-1.enable_l1=ON
shm_wait_frames "csim_wfs" 250 30
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 40
compute_ao_metrics "cl_sl_gric" "${SANDBOX_WORK_DIR}/m_cl_sl_gric.json"
dump_sl_diag "sl-1" "${SANDBOX_WORK_DIR}/d_sl_gric.json"

# Shut down standalone sl-1 and disable PF briefly
milk-fps-set -q mfilt-1.PF.enable=OFF
milk-fps-runstop -q sl-1
milk-fps-rm -f -q sl-1
shm_wait_frames "csim_wfs" 80 20

echo "[slab] 8/9 Cascaded applyARPF -> cacaopc-selflearn (Stage-2 tweak on top of ARPF)..."
# Point applyARPF to intermediate stream aol1_modevalPF_base, then sl_cas reads it -> aol1_modevalPF
milk-fps-set -q applyARPF-1.outdata=aol1_modevalPF_base applyARPF-1.outPFstat=aol1_outPFstat_base
milk-fps-runstart -q mkARPF-1 applyARPF-1
milk-stream-wait -q -t 20 aol1_modevalPF_base aol1_outPFstat_base
shm_wait_frames "aol1_arPFmat" 1 30

milk-fps-init -q sl_cas-1 cacao-fpsexec-cacaopc-selflearn >/dev/null
milk-fps-set -q \
    sl_cas-1.AOloopindex=1 \
    sl_cas-1.inwfs=aol1_modevalWFS \
    sl_cas-1.inol=aol1_modevalOL \
    sl_cas-1.indm=aol1_modevalDM \
    sl_cas-1.inbasePF=aol1_modevalPF_base \
    sl_cas-1.inbaseStat=aol1_outPFstat_base \
    sl_cas-1.outdata=aol1_modevalPF \
    sl_cas-1.outPFstat=aol1_outPFstat \
    sl_cas-1.outtweak=aol1_sl_cas_tweak \
    sl_cas-1.out_mode=0 \
    sl_cas-1.key_mode="${KEY_MODE}" \
    sl_cas-1.NBmodeMax=64 \
    sl_cas-1.kmax="${KMAX}" \
    sl_cas-1.qshared=2 \
    sl_cas-1.nwarmup=50 \
    sl_cas-1.keywarmup=200 \
    sl_cas-1.rampsteps=32 \
    sl_cas-1.blend_soft=ON \
    sl_cas-1.rlim="${RLIM}" \
    sl_cas-1.latency="${LAT_TOT}" \
    sl_cas-1.max_wfs_gain=0.30 \
    sl_cas-1.max_ar_norm2=1.5 \
    sl_cas-1.lam0=60.0 \
    sl_cas-1.lam1=250.0 \
    sl_cas-1.max_tweak=0.15 \
    sl_cas-1.learnON=ON \
    sl_cas-1.shadow=ON \
    sl_cas-1.enable_l0=ON \
    sl_cas-1.enable_l1=ON \
    sl_cas-1.apply_gain=0.75 \
    sl_cas-1.procinfo.loopcntMax=-1 \
    sl_cas-1.procinfo.triggermode=3 \
    sl_cas-1.procinfo.triggersname=aol1_modevalPF_base
milk-fps-runstart -q sl_cas-1
milk-fps-set -q mfilt-1.PF.mixcoeff="${PF_MIX}" mfilt-1.PF.enable=ON
# Warm up ARPF + shadow-learn GRIC Level-1 clusters on ARPF residual before engaging
shm_wait_frames "csim_wfs" 450 35
milk-fps-set -q sl_cas-1.shadow=OFF
shm_wait_frames "csim_wfs" 200 30
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 40
compute_ao_metrics "cl_arpf_sl" "${SANDBOX_WORK_DIR}/m_cl_arpf_sl.json"
dump_sl_diag "sl_cas-1" "${SANDBOX_WORK_DIR}/d_sl_cas.json"

milk-fps-set -q mfilt-1.PF.enable=OFF
milk-fps-runstop -q sl_cas-1 mkARPF-1 applyARPF-1
milk-fps-rm -f -q sl_cas-1
shm_wait_frames "csim_wfs" 80 20

echo "[slab] 9/9 auxDM mode (out_mode=1, additive GRIC tweak directly on leaky integrator)..."
LAT_AUX="$(awk -v l="${LAT_TOT}" 'BEGIN { printf "%.3f\n", l + 1.0 }')"
milk-fps-init -q sl_aux-1 cacao-fpsexec-cacaopc-selflearn >/dev/null
milk-fps-set -q \
    sl_aux-1.AOloopindex=1 \
    sl_aux-1.inwfs=aol1_modevalWFS \
    sl_aux-1.inol=aol1_modevalOL \
    sl_aux-1.indm=aol1_modevalDM \
    sl_aux-1.outdata=aol1_modevalauxDM \
    sl_aux-1.outtweak=aol1_sl_aux_tweak \
    sl_aux-1.out_mode=1 \
    sl_aux-1.key_mode="${KEY_MODE}" \
    sl_aux-1.NBmodeMax=64 \
    sl_aux-1.kmax="${KMAX}" \
    sl_aux-1.qshared=2 \
    sl_aux-1.nwarmup=50 \
    sl_aux-1.keywarmup=200 \
    sl_aux-1.blend_soft=ON \
    sl_aux-1.rlim="${RLIM}" \
    sl_aux-1.latency="${LAT_AUX}" \
    sl_aux-1.aux_leak=0.60 \
    sl_aux-1.wfs_to_dm=0.25 \
    sl_aux-1.max_wfs_gain=0.25 \
    sl_aux-1.max_ar_norm2=1.5 \
    sl_aux-1.lam0=80.0 \
    sl_aux-1.lam1=250.0 \
    sl_aux-1.max_tweak=0.10 \
    sl_aux-1.learnON=ON \
    sl_aux-1.shadow=ON \
    sl_aux-1.enable_l0=ON \
    sl_aux-1.enable_l1=ON \
    sl_aux-1.apply_gain=0.35 \
    sl_aux-1.procinfo.loopcntMax=-1 \
    sl_aux-1.procinfo.triggermode=3 \
    sl_aux-1.procinfo.triggersname=aol1_modevalOL
milk-fps-runstart -q sl_aux-1
shm_wait_frames "aol1_sl_aux_tweak" 500 35
milk-fps-set -q sl_aux-1.shadow=OFF mfilt-1.auxDMmval.mixfact=1.0 mfilt-1.auxDMmval.enable=ON
shm_wait_frames "csim_wfs" 250 30
csim_reset_long
shm_wait_frames "csim_wfs" "${EVAL_FRAMES}" 40
compute_ao_metrics "cl_sl_aux" "${SANDBOX_WORK_DIR}/m_cl_sl_aux.json"
dump_sl_diag "sl_aux-1" "${SANDBOX_WORK_DIR}/d_sl_aux.json"

"${PYTHON_BIN}" - "${SANDBOX_WORK_DIR}" "${OUT_JSON}" "${MOD_RAD}" "${SEEING}" "${LAT_TOT}" <<'PY'
import json, os, sys

wdir, out_json, mod_rad, seeing, lat_tot = sys.argv[1:6]
stages = [
    "dl", "ol", "cl_int", "cl_arpf",
    "cl_sl_shadow", "cl_sl_l0", "cl_sl_gric", "cl_arpf_sl", "cl_sl_aux",
]
diags = {
    "cl_sl_shadow": "d_sl_shadow.json",
    "cl_sl_l0": "d_sl_l0.json",
    "cl_sl_gric": "d_sl_gric.json",
    "cl_arpf_sl": "d_sl_cas.json",
    "cl_sl_aux": "d_sl_aux.json",
}
res = {
    "mod_rad": float(mod_rad),
    "seeing": float(seeing),
    "latency_fr": float(lat_tot),
    "stages": {},
}
print(
    f"\n=== Live GPU Closed-Loop A/B Summary "
    f"(mod_rad={mod_rad}, seeing={seeing}\", lat={lat_tot} fr) ==="
)
hdr = (
    f"{'Stage':14s} | {'SR_peak':>7s} | {'SR_ave':>7s} | {'mval_rms':>9s} "
    f"| {'GRIC K':>6s} | {'a0/a1':>9s} | {'OOS L0/L1/Tot %':>20s}"
)
print(hdr)
print("-" * 88)
for s in stages:
    m = json.load(open(os.path.join(wdir, f"m_{s}.json")))
    d = json.load(open(os.path.join(wdir, diags[s]))) if s in diags else None
    res["stages"][s] = {"metrics": m, "diag": d}
    if d:
        kstr = f"{d['n_clusters']:2d}(g{d['gric_active']})"
        astr = f"{d['alpha_l0']:.2f}/{d['alpha_l1']:.2f}"
        vstr = f"{d['oos_vr_l0_pct']:+5.1f}/{d['oos_vr_l1_pct']:+5.1f}/{d['oos_vr_tot_pct']:+5.1f}"
    else:
        kstr, astr, vstr = "  --  ", "   --    ", "         --         "
    print(
        f"{s:14s} | {m['strehl_peak']:7.4f} | {m['strehl_fps_ave']:7.4f} "
        f"| {m['mval_rms']:9.5f} | {kstr:>6s} | {astr:>9s} | {vstr:>20s}"
    )

with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=2)
print(f"\nSaved JSON -> {out_json}")
PY
