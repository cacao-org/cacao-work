#!/usr/bin/python3
"""Per-mode optical gain of WFS B (stage-2 pyramid) for each stage-2 loop state of one scan.

Input, written by run-og-states.sh:
    <scan>/selfRM_calib_stg2.fits                 no turbulence, loop open  (lag, poked, sensed)
    <scan>/state_<label>/selfRM_onsky_stg2.fits   turbulence, loop in that state
    <scan>/state_<label>/wf_stats.json, strehl_timeseries.csv, wf_samples_*.fits
    <scan>/og_states_counts.csv                   stream counters around every measurement

Optical gain of mode m, three estimators:
    peak  : max_lag |sky[lag, m, m]| / max_lag |cal[lag, m, m]|   (milk-mlt-calib2wfs1dm)
    slice : sky[z_s, m, m] / cal[z_c, m, m], one lag per cube     (report: load_selfrm_og)
    fixed : (sky[ZF, m, m] - sky[pre, m, m]) / (cal_plateau[m] - cal[pre, m, m]), with the SAME
            lag ZF for every state and "pre" the lags before the response arrives
"peak" takes a maximum over noisy lags, so it is biased high by an amount that depends on how
many lags sit on the plateau, i.e. on the loop state. "fixed" has no such bias; subtracting the
pre-response lags also removes the slow-drift error that the +/- poke pairs leave behind (it
is common to all lags of a pair). "fixed" is the estimator used for the ratios between states.
The 1-sigma error of mode m is the RMS, over the other poked modes j, of the same quantity
measured on sensed mode m (those elements carry the same noise and no signal).

Usage: reduce.py <scan dir> [reference label]
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy import ndimage

NM = 40  # leading stage-2 modes
LAM_WFS_NM = 750.0  # WFS B wavelength


def lag_profile(cube, norm):
    """Mean over the NM leading modes of diag(cube[lag]) / norm, per lag."""
    return np.array([np.mean(np.diag(s[:NM, :NM]) / norm) for s in cube])


def og_peak(cal, sky):
    pc = np.array([np.max(np.abs(cal[:, m, m])) for m in range(NM)])
    ps = np.array([np.max(np.abs(sky[:, m, m])) for m in range(NM)])
    return ps / np.maximum(pc, 1e-12)


def og_slice(cal, sky):
    zc = int(np.argmax([np.mean(np.abs(np.diag(s[:NM, :NM]))) for s in cal]))
    zs = int(np.argmax([np.mean(np.abs(np.diag(s[:NM, :NM]))) for s in sky]))
    return np.diag(sky[zs, :NM, :NM]) / np.maximum(np.diag(cal[zc, :NM, :NM]), 1e-6), zc, zs


def petal_removed_rms(samples, mask, lam=LAM_WFS_NM):
    """Per-snapshot pupil RMS [nm] of the OPD as a sensor at wavelength `lam` can see it.

    The spiders cut the pupil into segments, and the loops leave piston steps of whole waves
    between them. Returns two arrays: the RMS with every segment's mean removed, and the RMS
    with every segment's mean wrapped to within half a wave of the common phase (a whole-wave
    step is invisible at `lam`, a fractional one is not), plus the number of segments.
    """
    lab, n = ndimage.label(mask)
    removed, wrapped = [], []
    for w in samples.astype(np.float64):
        r = w.copy()
        means, areas = np.zeros(n), np.zeros(n)
        for i in range(1, n + 1):
            means[i - 1], areas[i - 1] = w[lab == i].mean(), (lab == i).sum()
            r[lab == i] -= means[i - 1]
        removed.append(np.sqrt(np.mean(r[mask] ** 2)))
        phi = 2 * np.pi * means / lam
        phi0 = np.angle(np.sum(areas * np.exp(1j * phi)))
        frac = np.angle(np.exp(1j * (phi - phi0))) * lam / (2 * np.pi)
        for i in range(1, n + 1):
            r[lab == i] += frac[i - 1]
        wrapped.append(np.std(r[mask]))
    return np.array(removed), np.array(wrapped), n


def med_iqr(x):
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    return [float(med), float(q1), float(q3)]


def med_se(x):
    """Standard error of the median from the robust scatter (normal approximation)."""
    sig = 1.4826 * np.median(np.abs(x - np.median(x)))
    return float(1.2533 * sig / np.sqrt(len(x)))


def main(scan, ref=None):
    scan = Path(scan)
    cal = fits.getdata(scan / "selfRM_calib_stg2.fits").astype(np.float64)
    cal_max = np.array([np.max(np.abs(cal[:, m, m])) for m in range(NM)])
    cal_prof = lag_profile(cal, cal_max)
    zc_plateau = [z for z in range(cal.shape[0]) if cal_prof[z] > 0.98 * cal_prof.max()]
    cal_plateau = np.array([np.mean(cal[zc_plateau, m, m]) for m in range(NM)])
    # lags before the response arrives (calibration lag 0 still holds the previous poke)
    pre_cal = [z for z in range(1, cal.shape[0]) if abs(cal_prof[z]) < 0.01 * cal_prof.max()]
    cal_step = cal_plateau - np.array([np.mean(cal[pre_cal, m, m]) for m in range(NM)])

    counts = {}
    with open(scan / "og_states_counts.csv") as fh:
        for r in csv.DictReader(fh):
            counts.setdefault(r["state"], {})[r["window"]] = r
    labels = list(counts)
    ref = ref or labels[0]

    sky = {s: fits.getdata(scan / f"state_{s}" / "selfRM_onsky_stg2.fits").astype(np.float64)
           for s in labels}
    prof = {s: lag_profile(sky[s], cal_plateau) for s in labels}
    # Lags used by the "fixed" estimator: on the plateau of the open-loop state (or, without
    # one, of the lowest-gain state), where no loop reaction can have set in, and at least
    # 0.97 of that plateau in every state (so the response has fully risen everywhere).
    gains = {s: counts[s]["selfrm"]["gain2"] for s in labels}
    flat = next((s for s in labels if gains[s] == "open"), None)
    if flat is None:
        flat = min(labels, key=lambda s: float(gains[s]))
    top = prof[flat].max()
    zf = [z for z in range(len(prof[flat])) if prof[flat][z] > 0.97 * top]
    first = zf[0]
    # keep the first plateau lag only plus the next one if every state is still on it
    zf = [z for z in zf[:2] if all(prof[s][z] > 0.97 * prof[s].max() for s in labels)] or [first]
    pre = [z for z in range(first) if all(abs(prof[s][z]) < 0.02 for s in labels)]

    out = dict(n_modes=NM, reference=ref, calib_plateau_lags=zc_plateau, fixed_lags=zf,
               pre_lags=pre, pre_lags_calib=pre_cal,
               calib_lag_profile=cal_prof.tolist(), states={})
    for s in labels:
        d = scan / f"state_{s}"
        pk = og_peak(cal, sky[s])
        sl, zc, zs = og_slice(cal, sky[s])
        step = sky[s][zf, :NM, :NM].mean(0) - sky[s][pre, :NM, :NM].mean(0)  # (poked, sensed)
        fx = np.diag(step) / cal_step
        err = np.array([np.sqrt(np.mean(np.delete(step[:, m], m) ** 2)) for m in range(NM)])
        err = err / cal_step
        rec = dict(gain2=gains[s], og_peak=pk.tolist(), og_slice=sl.tolist(), og_fixed=fx.tolist(),
                   og_fixed_err=err.tolist(), slice_lags=[zc, zs], lag_profile=prof[s].tolist(),
                   baseline=(np.array([sky[s][pre, m, m].mean() for m in range(NM)])
                             / cal_step).tolist())
        rec["offdiag_rms"] = float(np.median(err[2:]))
        # wavefront and Strehl
        st = list(csv.DictReader(open(d / "strehl_timeseries.csv")))
        vf = np.array([float(r["vis_final_inst"]) for r in st])
        v1 = np.array([float(r["vis_stg1_inst"]) for r in st])
        mask = fits.getdata(d / "wf_pupil_mask.fits") > 0.5
        rf, wf, npet = petal_removed_rms(fits.getdata(d / "wf_samples_final.fits"), mask)
        r1, w1, _ = petal_removed_rms(fits.getdata(d / "wf_samples_stg1.fits"), mask)
        js = json.loads((d / "wf_stats.json").read_text())
        rec.update(
            strehl_vis_final=float(vf.mean()), strehl_vis_stg1=float(v1.mean()),
            strehl_vis_final_long=float(st[-1]["vis_final_long"]),
            strehl_vis_stg1_long=float(st[-1]["vis_stg1_long"]),
            strehl_vis_final_sd=float(vf.std()), n_exposures=len(vf),
            marechal_rms_final_nm=float(LAM_WFS_NM / (2 * np.pi) * np.sqrt(-np.log(vf.mean()))),
            marechal_rms_stg1_nm=float(LAM_WFS_NM / (2 * np.pi) * np.sqrt(-np.log(v1.mean()))),
            resid_final_nm=float(rf.mean()), resid_final_snap=rf.tolist(),
            resid_stg1_nm=float(r1.mean()), resid_stg1_snap=r1.tolist(), n_segments=npet,
            resid_wrapped_final_nm=float(wf.mean()), resid_wrapped_final_snap=wf.tolist(),
            resid_wrapped_stg1_nm=float(w1.mean()), resid_wrapped_stg1_snap=w1.tolist(),
            raw_rms_final_nm=js["locations"]["final"]["mean_spatial_rms_nm"],
            wf_frames=js["n_frames"],
            counts={w: [int(c["d_pha"]), int(c["d_wfs1"]), int(c["d_wfs2"]), float(c["wall_s"])]
                    for w, c in counts[s].items()})
        out["states"][s] = rec

    r0 = out["states"][ref]
    grp = [(0, 2), (2, 10), (10, 20), (20, 30), (30, 40)]
    for s in labels:
        rec = out["states"][s]
        for k in ("fixed", "peak", "slice"):
            ratio = np.array(rec[f"og_{k}"]) / np.array(r0[f"og_{k}"])
            rec[f"ratio_{k}"] = ratio.tolist()
            rec[f"ratio_{k}_med"] = med_iqr(ratio)
            rec[f"ratio_{k}_se"] = med_se(ratio)
            rec[f"og_{k}_med"] = med_iqr(np.array(rec[f"og_{k}"]))
        rf = np.array(rec["ratio_fixed"])
        re_ = rf * np.hypot(np.array(rec["og_fixed_err"]) / np.array(rec["og_fixed"]),
                            np.array(r0["og_fixed_err"]) / np.array(r0["og_fixed"]))
        rec["ratio_fixed_err"] = re_.tolist()
        w = 1.0 / re_ ** 2
        wm = lambda a, b: [float(np.sum(w[a:b] * rf[a:b]) / np.sum(w[a:b])),
                           float(1.0 / np.sqrt(np.sum(w[a:b])))]
        rec["ratio_fixed_groups"] = [float(np.median(rf[a:b])) for a, b in grp]
        rec["ratio_fixed_wmean_groups"] = [wm(a, b) for a, b in grp]
        rec["ratio_fixed_wmean_2_39"] = wm(2, NM)
        rec["ratio_fixed_med_2_39"] = med_iqr(rf[2:])
        rec["ratio_fixed_minmax_2_39"] = [float(rf[2:].min()), float(rf[2:].max())]
        rec["og_fixed_med_2_39"] = med_iqr(np.array(rec["og_fixed"])[2:])
        rec["ratio_fixed_slope_per10"] = float(np.polyfit(np.arange(2, NM), rf[2:], 1,
                                                          w=1.0 / re_[2:])[0] * 10)

    print(f"scan {scan.name}: reference {ref}; calibration plateau lags {zc_plateau};"
          f" fixed lags {zf}; pre-response lags {pre} (calibration {pre_cal})")
    print("\nlag profiles (mean over modes, units of the calibration plateau):")
    print(f"  {'calibration':12s} " + " ".join(f"{x:+.3f}" for x in cal_prof / cal_prof.max()))
    for s in labels:
        print(f"  {s:12s} " + " ".join(f"{x:+.3f}" for x in prof[s]))
    print("\nframe counters (pha, wfs1, wfs2) per measurement; pha must equal wfs2:")
    for s in labels:
        c = out["states"][s]["counts"]
        print(f"  {s:12s} wfstat {c['wfstat'][:3]} in {c['wfstat'][3]:.0f} s;"
              f" selfRM {c['selfrm'][:3]} in {c['selfrm'][3]:.0f} s")
    print(f"\n{'state':11s} {'gain':>7s} {'OG fixed med [IQR]':>24s} {'peak':>6s} {'slice':>6s}"
          f" {'ratio fixed [IQR] +-se':>30s} {'peak':>6s} {'slice':>6s} {'offd':>6s}")
    for s in labels:
        r = out["states"][s]
        m, q1, q3 = r["og_fixed_med"]
        a, b, c = r["ratio_fixed_med"]
        print(f"{s:11s} {r['gain2']:>7s} {m:8.3f} [{q1:.3f},{q3:.3f}] {r['og_peak_med'][0]:6.3f}"
              f" {r['og_slice_med'][0]:6.3f} {a:9.3f} [{b:.3f},{c:.3f}] +-{r['ratio_fixed_se']:.3f}"
              f" {r['ratio_peak_med'][0]:6.3f} {r['ratio_slice_med'][0]:6.3f}"
              f" {r['offdiag_rms']:6.3f}")
    print(f"\n{'state':11s} {'ratio, modes 2-39: wmean +-se':>30s} {'median [IQR]':>22s}"
          f" {'min':>6s} {'max':>6s} | {'tip':>12s} {'tilt':>12s} {'TT wmean':>14s}")
    for s in labels:
        r = out["states"][s]
        a, b = r["ratio_fixed_wmean_2_39"]
        m, q1, q3 = r["ratio_fixed_med_2_39"]
        lo, hi = r["ratio_fixed_minmax_2_39"]
        rf, re_ = r["ratio_fixed"], r["ratio_fixed_err"]
        t, te = r["ratio_fixed_wmean_groups"][0]
        print(f"{s:11s} {a:22.4f} +-{b:.4f} {m:8.3f} [{q1:.3f},{q3:.3f}] {lo:6.3f} {hi:6.3f} |"
              f" {rf[0]:6.3f}+-{re_[0]:.3f} {rf[1]:6.3f}+-{re_[1]:.3f} {t:8.3f}+-{te:.3f}")
    print(f"\n{'state':11s} {'ratio by mode group 0-1,2-9,10-19,20-29,30-39':>44s} {'slope/10':>9s}"
          f" {'Strehl vis final':>17s} {'stg1':>6s} | residual at WFS B [nm]:"
          f" {'seg-piston removed':>19s} {'wrapped':>8s} {'Marechal':>9s} | after stage 1:"
          f" {'removed':>8s} {'wrapped':>8s}")
    for s in labels:
        r = out["states"][s]
        g = " ".join(f"{x:.3f}" for x in r["ratio_fixed_groups"])
        print(f"{s:11s} {g:>44s} {r['ratio_fixed_slope_per10']:+9.3f}"
              f" {r['strehl_vis_final']:11.3f}+-{r['strehl_vis_final_sd']:.3f}"
              f" {r['strehl_vis_stg1']:6.3f} | {'':23s} {r['resid_final_nm']:19.1f}"
              f" {r['resid_wrapped_final_nm']:8.1f} {r['marechal_rms_final_nm']:9.1f} |"
              f" {'':14s} {r['resid_stg1_nm']:8.1f} {r['resid_wrapped_stg1_nm']:8.1f}")
    (scan / "og_vs_stage2_state.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
