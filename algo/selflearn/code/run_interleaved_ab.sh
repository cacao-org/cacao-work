#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Multi-cycle interleaved live GPU closed-loop A/B benchmark on scao_pyr.
# Cycles through INT -> ARPF -> ARPF+SL -> SL_L0 -> SL_GRIC repeatedly in one
# continuous run so seeing-patch variance cancels out across controllers.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
# shellcheck source=../../../env.sh
source "${REPO_ROOT}/env.sh"
# shellcheck source=../../../scripts/shm-sandbox.sh
source "${REPO_ROOT}/scripts/shm-sandbox.sh"

MOD_RAD="${1:-0.0}"
SEEING="${2:-0.35}"
NCYCLES="${3:-4}"
WIN_FRAMES="${4:-400}"
RM_DIR="${5:-}"
OUT_JSON="${6:-${REPO_ROOT}/_work/selflearn_interleaved_mod${MOD_RAD}_s${SEEING}.json}"
RATE="${RATE:-400}"
GAIN="${GAIN:-0.30}"
MULT="${MULT:-0.98}"
SVDLIM="${SVDLIM:-0.05}"
PF_MIX="${PF_MIX:-0.90}"

mkdir -p "$(dirname "${OUT_JSON}")"

sandbox_init "sliab"
LOOP_CTRL="${REPO_ROOT}/benches/scao_pyr/cacaoloop-scao-pyr.milk"
export CACAO_LOOPNAME="scao_pyr"
export CACAO_LOOPNUMBER=1
export CACAO_LOOPROOTDIR="${SANDBOX_WORK_DIR}/scao_pyr"
export CACAO_WFSFRATE="${RATE}"
export CACAO_LOOPGAIN="${GAIN}"
export CACAO_LOOPMULT="${MULT}"
export CACAO_SVDLIM="${SVDLIM}"

cleanup_iab() {
    milk-fps-runstop -q sl_iab-1 sl_cas-1 mkARPF-1 applyARPF-1 >/dev/null 2>&1 || true
    milk-fps-rm -f -q --ignore-missing sl_iab-1 sl_cas-1 >/dev/null 2>&1 || true
    "${LOOP_CTRL}" teardown --purge-dm >/dev/null 2>&1 || true
    sandbox_cleanup
}
trap cleanup_iab EXIT

BENCH_CFG="${SANDBOX_WORK_DIR}/scao_iab.bench"
awk -v mr="${MOD_RAD}" '
/^mod_rad[ \t]*=/ { printf "mod_rad       = %s\n", mr; next }
/^mod_npts[ \t]*=/ { if (mr + 0 == 0) { printf "mod_npts      = 1\n"; next } }
{ print }
' "${REPO_ROOT}/benches/scao_pyr/scao_pyr.bench" > "${BENCH_CFG}"

echo "[sliab] Deploying scao_pyr (mod_rad=${MOD_RAD}, seeing=${SEEING}\"," \
    "${NCYCLES}x${WIN_FRAMES} fr)..."
cacaosim-bench deploy \
    --workdir "${CACAOSIM_WORKDIR}" \
    --config "${BENCH_CFG}" \
    --mode fused \
    --rate "${RATE}" \
    --atmturb \
    --seeing "${SEEING}" \
    --no-view >/dev/null

milk-stream-wait -q -t 20 outarraypha csim_wfs csim_fpcam csim_fplong

# DL reference + deploy/calibrate AO loop
csim_set_turb_gain 0.0
shm_wait_frames "csim_wfs" 15 15
csim_reset_long
shm_wait_frames "csim_wfs" 30 15
compute_ao_metrics "dl" "${SANDBOX_WORK_DIR}/m_dl.json"

"${LOOP_CTRL}" deploy >/dev/null
if [[ -n "${RM_DIR}" && -f "${RM_DIR}/zrespC.fits" ]]; then
    "${LOOP_CTRL}" load-rm "${RM_DIR}" --svdlim "${SVDLIM}" >/dev/null
else
    "${LOOP_CTRL}" calibrate --nframes 60 --nbloop 2 --svdlim "${SVDLIM}" >/dev/null
fi

LAT_TOT="$(milk-script -q -e <<'MS'
@get lh="f.mfilt-1.comp.latencyhardwfr" ls="f.mfilt-1.comp.latencysoftwfr"
awk -v a="${lh:-1.5}" -v b="${ls:-0.6}" 'BEGIN { printf "%.3f\n", a + b }'
MS
)"
echo "[sliab] Latency=${LAT_TOT} fr; warming up ARPF & selflearn in closed loop..."

csim_set_turb_gain 1.0
"${LOOP_CTRL}" close "${GAIN}"
shm_wait_frames "csim_wfs" 120 20

# Start mkARPF + applyARPF feeding aol1_modevalPF_base (runs continuously in background)
milk-fps-set -q \
    mkARPF-1.PFlatency="${LAT_TOT}" \
    applyARPF-1.outdata=aol1_modevalPF_base \
    applyARPF-1.outPFstat=aol1_outPFstat_base
milk-fps-runstart -q mkARPF-1 applyARPF-1
milk-stream-wait -q -t 20 aol1_modevalPF_base aol1_outPFstat_base
shm_wait_frames "aol1_arPFmat" 1 30

# Start cascaded sl_cas-1 (applyARPF -> selflearn -> aol1_modevalPF)
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
    sl_cas-1.key_mode=0 \
    sl_cas-1.NBmodeMax=64 \
    sl_cas-1.kmax=16 \
    sl_cas-1.qshared=2 \
    sl_cas-1.nwarmup=40 \
    sl_cas-1.keywarmup=200 \
    sl_cas-1.blend_soft=ON \
    sl_cas-1.rlim=2.0 \
    sl_cas-1.latency="${LAT_TOT}" \
    sl_cas-1.max_wfs_gain=0.35 \
    sl_cas-1.max_ar_norm2=1.5 \
    sl_cas-1.lam0=40.0 \
    sl_cas-1.lam1=200.0 \
    sl_cas-1.gamma0=0.998 \
    sl_cas-1.gamma1=0.995 \
    sl_cas-1.max_tweak=0.20 \
    sl_cas-1.learnON=ON \
    sl_cas-1.shadow=ON \
    sl_cas-1.enable_l0=ON \
    sl_cas-1.enable_l1=ON \
    sl_cas-1.apply_gain=0.80 \
    sl_cas-1.procinfo.loopcntMax=-1 \
    sl_cas-1.procinfo.triggermode=3 \
    sl_cas-1.procinfo.triggersname=aol1_modevalPF_base
milk-fps-runstart -q sl_cas-1

# Start standalone sl_iab-1 (selflearn -> aol1_modevalPF_sl, warmed in parallel)
milk-fps-init -q sl_iab-1 cacao-fpsexec-cacaopc-selflearn >/dev/null
milk-fps-set -q \
    sl_iab-1.AOloopindex=1 \
    sl_iab-1.inwfs=aol1_modevalWFS \
    sl_iab-1.inol=aol1_modevalOL \
    sl_iab-1.indm=aol1_modevalDM \
    sl_iab-1.outdata=aol1_modevalPF_sl \
    sl_iab-1.outPFstat=aol1_outPFstat_sl \
    sl_iab-1.outtweak=aol1_sl_iab_tweak \
    sl_iab-1.out_mode=0 \
    sl_iab-1.key_mode=0 \
    sl_iab-1.NBmodeMax=64 \
    sl_iab-1.kmax=16 \
    sl_iab-1.qshared=2 \
    sl_iab-1.nwarmup=40 \
    sl_iab-1.keywarmup=200 \
    sl_iab-1.blend_soft=ON \
    sl_iab-1.rlim=2.0 \
    sl_iab-1.latency="${LAT_TOT}" \
    sl_iab-1.dc_leak=0.985 \
    sl_iab-1.max_wfs_gain=0.40 \
    sl_iab-1.max_ar_norm2=2.0 \
    sl_iab-1.lam0=20.0 \
    sl_iab-1.lam1=180.0 \
    sl_iab-1.gamma0=0.998 \
    sl_iab-1.gamma1=0.995 \
    sl_iab-1.max_tweak=0.25 \
    sl_iab-1.learnON=ON \
    sl_iab-1.shadow=OFF \
    sl_iab-1.enable_l0=ON \
    sl_iab-1.enable_l1=ON \
    sl_iab-1.apply_gain=1.0 \
    sl_iab-1.procinfo.loopcntMax=-1 \
    sl_iab-1.procinfo.triggermode=3 \
    sl_iab-1.procinfo.triggersname=aol1_modevalOL
milk-fps-runstart -q sl_iab-1

# Warm up both learners in PF mode (ARPF running) for 600 frames
milk-fps-set -q mfilt-1.PF.mixcoeff="${PF_MIX}" mfilt-1.PF.enable=ON
shm_wait_frames "csim_wfs" 600 35

measure_win() {
    local tag="$1"
    shm_wait_frames "csim_wfs" 80 25
    csim_reset_long
    shm_wait_frames "csim_wfs" "${WIN_FRAMES}" 35
    compute_ao_metrics "${tag}" "${SANDBOX_WORK_DIR}/m_${tag}.json"
}

# Cycle A (interleaved): INT -> ARPF -> ARPF+L0 -> ARPF+GRIC
for c in $(seq 1 "${NCYCLES}"); do
    echo "[sliab] Cycle ${c}/${NCYCLES}: INT | ARPF | ARPF+L0 | ARPF+GRIC..."
    milk-fps-set -q mfilt-1.PF.enable=OFF
    measure_win "int_c${c}"

    milk-fps-set -q sl_cas-1.shadow=ON mfilt-1.PF.enable=ON
    measure_win "arpf_c${c}"

    milk-fps-set -q sl_cas-1.shadow=OFF sl_cas-1.enable_l0=ON sl_cas-1.enable_l1=OFF
    measure_win "arpf_l0_c${c}"

    milk-fps-set -q sl_cas-1.shadow=OFF sl_cas-1.enable_l0=ON sl_cas-1.enable_l1=ON
    measure_win "arpf_gric_c${c}"
done

# Now switch mfilt PF sink to standalone sl_iab-1 (redirect aol1_modevalPF)
milk-fps-set -q mfilt-1.PF.enable=OFF
milk-fps-runstop -q sl_cas-1 sl_iab-1
milk-fps-set -q sl_iab-1.outdata=aol1_modevalPF sl_iab-1.outPFstat=aol1_outPFstat
milk-fps-runstart -q sl_iab-1
milk-fps-set -q sl_iab-1.shadow=OFF sl_iab-1.enable_l0=ON sl_iab-1.enable_l1=OFF
milk-fps-set -q mfilt-1.PF.enable=ON
shm_wait_frames "csim_wfs" 600 35

for c in $(seq 1 "${NCYCLES}"); do
    echo "[sliab] Standalone Cycle ${c}/${NCYCLES}: INT | SL_L0 | SL_GRIC..."
    milk-fps-set -q mfilt-1.PF.enable=OFF
    measure_win "int2_c${c}"

    milk-fps-set -q sl_iab-1.enable_l0=ON sl_iab-1.enable_l1=OFF mfilt-1.PF.enable=ON
    measure_win "sl_l0_c${c}"

    milk-fps-set -q sl_iab-1.enable_l0=ON sl_iab-1.enable_l1=ON mfilt-1.PF.enable=ON
    measure_win "sl_gric_c${c}"
done

# Dump final diagnostics of both units
dump_diag() {
    local u="$1" out="$2"
    milk-script -q -e <<MS > "${out}"
@get nc="f.${u}.out.n_clusters" ga="f.${u}.out.gric_active" \
     a0="f.${u}.out.alpha_l0" a1="f.${u}.out.alpha_l1" \
     vr0="f.${u}.out.oos_vr_l0_pct" vr1="f.${u}.out.oos_vr_l1_pct" \
     vrt="f.${u}.out.oos_vr_tot_pct" ol="f.${u}.out.outliers"
printf '{"gric_active":%s,"n_clusters":%s,"alpha_l0":%s,"alpha_l1":%s,' \
    "\${ga:-0}" "\${nc:-0}" "\${a0:-0}" "\${a1:-0}"
printf '"oos_vr_l0_pct":%s,"oos_vr_l1_pct":%s,"oos_vr_tot_pct":%s,"outliers":%s}\n' \
    "\${vr0:-0}" "\${vr1:-0}" "\${vrt:-0}" "\${ol:-0}"
MS
}
dump_diag "sl_cas-1" "${SANDBOX_WORK_DIR}/d_cas.json"
dump_diag "sl_iab-1" "${SANDBOX_WORK_DIR}/d_iab.json"

"${PYTHON_BIN}" - "${SANDBOX_WORK_DIR}" "${OUT_JSON}" "${MOD_RAD}" "${SEEING}" "${NCYCLES}" \
    "${WIN_FRAMES}" "${LAT_TOT}" <<'PY'
import json, os, sys
import numpy as np

wdir, out_json, mod_rad, seeing, ncyc, wfr, lat = sys.argv[1:8]
ncyc = int(ncyc)
groups = [
    ("Block A (ARPF cascade)", ["int", "arpf", "arpf_l0", "arpf_gric"]),
    ("Block B (Standalone SL)", ["int2", "sl_l0", "sl_gric"]),
]
res = {
    "mod_rad": float(mod_rad),
    "seeing": float(seeing),
    "ncycles": ncyc,
    "win_frames": int(wfr),
    "latency_fr": float(lat),
    "diag_cas": json.load(open(os.path.join(wdir, "d_cas.json"))),
    "diag_iab": json.load(open(os.path.join(wdir, "d_iab.json"))),
    "summary": {},
}

print(
    f"\n=== Interleaved {ncyc}x{wfr} fr Live GPU A/B "
    f"(mod_rad={mod_rad}, seeing={seeing}\", lat={lat} fr) ==="
)
for title, keys in groups:
    print(f"\n--- {title} ---")
    print(
        f"{'Controller':12s} | {'SR_ave mean±se':>15s} | {'SR_peak mean':>12s} "
        f"| {'wfs_rms':>9s} | {'dm_rms':>7s} | {'per-cycle SR_ave'}"
    )
    print("-" * 86)
    for k in keys:
        sr_a, sr_p, wr, dr = [], [], [], []
        for c in range(1, ncyc + 1):
            m = json.load(open(os.path.join(wdir, f"m_{k}_c{c}.json")))
            sr_a.append(m["strehl_fps_ave"])
            sr_p.append(m["strehl_peak"])
            wr.append(m["wfs_rms"])
            dr.append(m["dm_rms"])
        mean_a = float(np.mean(sr_a))
        se_a = float(np.std(sr_a, ddof=1) / np.sqrt(ncyc)) if ncyc > 1 else 0.0
        res["summary"][k] = {
            "sr_ave_mean": mean_a,
            "sr_ave_se": se_a,
            "sr_peak_mean": float(np.mean(sr_p)),
            "wfs_rms_mean": float(np.mean(wr)),
            "dm_rms_mean": float(np.mean(dr)),
            "sr_ave_cycles": sr_a,
        }
        cyc_str = " ".join(f"{v:.3f}" for v in sr_a)
        print(
            f"{k:12s} | {mean_a:7.4f} ± {se_a:5.4f} | {np.mean(sr_p):12.4f} "
            f"| {np.mean(wr):9.6f} | {np.mean(dr):7.4f} | [{cyc_str}]"
        )

print(f"\nDiag sl_cas (ARPF->SL): {res['diag_cas']}")
print(f"Diag sl_iab (Standalone): {res['diag_iab']}")
with open(out_json, "w", encoding="utf-8") as fh:
    json.dump(res, fh, indent=2)
print(f"Saved JSON -> {out_json}")
PY
