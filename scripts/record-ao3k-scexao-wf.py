#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Record synchronized pupil WF, WFS, DM, and instantaneous PSF samples + 10s WF stats."""

import ctypes
import json
import math
import os
import shutil
import sys
import time
import numpy as np
from astropy.io import fits

SAMPLE_FRACS = [0.10, 0.30, 0.50, 0.70, 0.95]
LOCATIONS = [
    ("raw", b"b_pup", "Before Stage 1 (Entrance Pupil)"),
    ("stg1", b"b_post_stg1", "Between Stages 1 & 2 (Post-AO3k)"),
    ("final", b"b_post_stg2", "After Stage 2 (Post-SCExAO)"),
]

EXTRA_2D_STREAMS = [
    ("wfs_raw_stg1", b"csim_wfs_nir", (64, 64), "ADU", "AO3k J-band PyWFS raw detector"),
    ("wfs_sig_stg1", b"aol1_imWFS2", (64, 64), "norm", "AO3k PyWFS ref-subtracted signal"),
    ("wfs_raw_stg2", b"csim_wfs_vis", (64, 64), "ADU", "SCExAO Vis PyWFS raw detector"),
    ("wfs_sig_stg2", b"aol2_imWFS2", (64, 64), "norm", "SCExAO PyWFS ref-subtracted signal"),
    ("dm_cmd_stg1", b"dm01disp", (16, 16), "um", "AO3k 16x16 DM stroke command"),
    ("dm_opd_stg1", b"csim_dm01_opd", (128, 128), "nm", "AO3k 128x128 reflective DM OPD"),
    ("dm_cmd_stg2", b"dm02disp", (24, 24), "um", "SCExAO 24x24 DM stroke command"),
    ("dm_opd_stg2", b"csim_dm02_opd", (128, 128), "nm", "SCExAO 128x128 reflective DM OPD"),
    ("psf_inst_vis_raw", b"psf_vis_raw", (192, 192), "ADU", "Inst Vis PSF Before Stage 1"),
    ("psf_inst_vis_stg1", b"psf_vis_stg1", (192, 192), "ADU", "Inst Vis PSF Post-Stage 1"),
    ("psf_inst_vis_final", b"psf_vis_final", (192, 192), "ADU", "Inst Vis PSF Post-Stage 2"),
    ("psf_inst_nir_raw", b"psf_nir_raw", (192, 192), "ADU", "Inst NIR PSF Before Stage 1"),
    ("psf_inst_nir_stg1", b"psf_nir_stg1", (192, 192), "ADU", "Inst NIR PSF Post-Stage 1"),
    ("psf_inst_nir_final", b"psf_nir_final", (192, 192), "ADU", "Inst NIR PSF Post-Stage 2"),
]


def load_isio_lib():
    candidates = []
    for key in ("MILK_INSTALL_ROOT", "MILK_INSTALLDIR", "MILK_ROOT"):
        val = os.environ.get(key)
        if val:
            candidates.append(os.path.join(val, "lib", "libImageStreamIO.so"))
    milk_cli = shutil.which("milk-cli")
    if milk_cli:
        prefix = os.path.dirname(os.path.dirname(os.path.realpath(milk_cli)))
        candidates.append(os.path.join(prefix, "lib", "libImageStreamIO.so"))
    so_path = next((p for p in candidates if os.path.isfile(p)), "libImageStreamIO.so")
    lib = ctypes.CDLL(so_path)
    lib.ImageStreamIO_openIm.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.ImageStreamIO_openIm.restype = ctypes.c_int
    lib.ImageStreamIO_get_image_d_ptr.argtypes = [ctypes.c_void_p]
    lib.ImageStreamIO_get_image_d_ptr.restype = ctypes.c_void_p
    lib.ImageStreamIO_getsemwaitindex.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.ImageStreamIO_getsemwaitindex.restype = ctypes.c_int
    lib.ImageStreamIO_semtrywait.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.ImageStreamIO_semtrywait.restype = ctypes.c_int
    lib.ImageStreamIO_semflush.argtypes = [ctypes.c_void_p, ctypes.c_long]
    lib.ImageStreamIO_semflush.restype = ctypes.c_long
    lib.ImageStreamIO_closeIm.argtypes = [ctypes.c_void_p]
    lib.ImageStreamIO_closeIm.restype = ctypes.c_int
    return lib


def write_fits_2d(path, arr, stage_desc, metric_desc, n_frames, phys_s):
    hdu = fits.PrimaryHDU(arr.astype(np.float32))
    hdr = hdu.header
    hdr["BUNIT"] = ("nm", "Wavefront OPD unit (nanometers)")
    hdr["STAGE"] = (stage_desc[:40], "Optical plane location")
    hdr["METRIC"] = (metric_desc[:40], "Statistic type")
    hdr["NFRAMES"] = (int(n_frames), "Accumulated frames")
    hdr["TPHYS_S"] = (float(phys_s), "Physical duration [s]")
    hdr["PISTREM"] = (True, "Instantaneous pupil piston removed")
    hdu.writeto(path, overwrite=True)


def main():
    out_dir = sys.argv[1]
    target_ticks = int(sys.argv[2])
    stop_file = sys.argv[3]
    ready_file = sys.argv[4]
    nwf = int(sys.argv[5]) if len(sys.argv) > 5 else 128

    lib = load_isio_lib()
    im_handles = {}
    cube_views = {}
    extra_handles = {}
    extra_views = {}

    for key, sname, _ in LOCATIONS:
        buf = ctypes.create_string_buffer(4096)
        rc = lib.ImageStreamIO_openIm(buf, sname)
        if rc != 0:
            raise RuntimeError(f"Failed to open SHM beam {sname.decode()} (rc={rc})")
        dptr = lib.ImageStreamIO_get_image_d_ptr(buf)
        im_handles[key] = buf
        cube_views[key] = np.ctypeslib.as_array(
            ctypes.cast(dptr, ctypes.POINTER(ctypes.c_float)),
            shape=(2, nwf, nwf),
        )

    for ekey, sname, shp, _, _ in EXTRA_2D_STREAMS:
        buf = ctypes.create_string_buffer(4096)
        rc = lib.ImageStreamIO_openIm(buf, sname)
        if rc == 0:
            dptr = lib.ImageStreamIO_get_image_d_ptr(buf)
            extra_handles[ekey] = buf
            extra_views[ekey] = np.ctypeslib.as_array(
                ctypes.cast(dptr, ctypes.POINTER(ctypes.c_float)),
                shape=shp,
            )

    pup_amp = cube_views["raw"][1].copy().astype(np.float64)
    mask = pup_amp > 0.5
    weights = (pup_amp**2) * mask
    w_sum = float(np.sum(weights))
    if w_sum <= 0.0:
        mask = np.ones((nwf, nwf), dtype=bool)
        weights = np.full((nwf, nwf), 1.0 / (nwf * nwf), dtype=np.float64)
    else:
        weights /= w_sum

    sample_targets = sorted(
        {max(1, int(round(frac * target_ticks))) for frac in SAMPLE_FRACS}
    )
    next_samp_ptr = 0

    sum_wf = {k: np.zeros((nwf, nwf), dtype=np.float64) for k, _, _ in LOCATIONS}
    sum2_wf = {k: np.zeros((nwf, nwf), dtype=np.float64) for k, _, _ in LOCATIONS}
    sum_srms = {k: 0.0 for k, _, _ in LOCATIONS}
    sum_svar = {k: 0.0 for k, _, _ in LOCATIONS}
    sample_cubes = {k: [] for k, _, _ in LOCATIONS}
    extra_cubes = {ekey: [] for ekey in extra_views}
    sample_meta = []

    trig_im = im_handles["final"]
    sem_idx = lib.ImageStreamIO_getsemwaitindex(trig_im, 0)
    if sem_idx < 0:
        sem_idx = 0
    lib.ImageStreamIO_semflush(trig_im, sem_idx)

    with open(ready_file, "w", encoding="utf-8") as fh:
        fh.write("ready\n")

    n_frames = 0
    max_frames = target_ticks + 1000

    try:
        while not os.path.exists(stop_file) and n_frames < max_frames:
            if lib.ImageStreamIO_semtrywait(trig_im, sem_idx) != 0:
                time.sleep(0.0005)
                continue
            while lib.ImageStreamIO_semtrywait(trig_im, sem_idx) == 0:
                pass

            raw_nm = {
                k: cube_views[k][0].copy().astype(np.float64) * 1000.0
                for k, _, _ in LOCATIONS
            }
            n_frames += 1

            is_sample = (
                next_samp_ptr < len(sample_targets)
                and n_frames >= sample_targets[next_samp_ptr]
            )
            s_entry = {
                "sample_index": next_samp_ptr,
                "frame": n_frames,
                "t_phys_s": round(n_frames * 0.0005, 6),
            }

            for k, _, _ in LOCATIONS:
                opd = raw_nm[k]
                piston = float(np.sum(weights * opd))
                wf = np.where(mask, opd - piston, 0.0)
                sum_wf[k] += wf
                sum2_wf[k] += wf * wf
                svar = float(np.sum(weights * wf * wf))
                srms = math.sqrt(max(svar, 0.0))
                sum_svar[k] += svar
                sum_srms[k] += srms

                if is_sample:
                    sample_cubes[k].append(wf.astype(np.float32))
                    vals = wf[mask]
                    ptv = float(np.max(vals) - np.min(vals)) if vals.size else 0.0
                    s_entry[k] = {"rms_nm": srms, "ptv_nm": ptv}

            if is_sample:
                s_extra = {}
                for ekey, _, _, unit, _ in EXTRA_2D_STREAMS:
                    if ekey not in extra_views:
                        continue
                    arr = extra_views[ekey].copy().astype(np.float64)
                    if ekey.startswith("dm_opd_"):
                        arr_nm = arr * 1000.0
                        pist = float(np.sum(weights * arr_nm))
                        arr_out = np.where(mask, arr_nm - pist, 0.0)
                        vals = arr_out[mask]
                        s_extra[ekey] = {
                            "rms_nm": math.sqrt(float(np.sum(weights * arr_out**2))),
                            "ptv_nm": float(np.max(vals) - np.min(vals)),
                        }
                        extra_cubes[ekey].append(arr_out.astype(np.float32))
                    elif ekey.startswith("dm_cmd_"):
                        s_extra[ekey] = {
                            "rms_um": float(np.sqrt(np.mean(arr**2))),
                            "ptv_um": float(np.max(arr) - np.min(arr)),
                        }
                        extra_cubes[ekey].append(arr.astype(np.float32))
                    elif ekey.startswith("wfs_raw_"):
                        s_extra[ekey] = {
                            "sum_adu": float(np.sum(arr)),
                            "max_adu": float(np.max(arr)),
                        }
                        extra_cubes[ekey].append(arr.astype(np.float32))
                    elif ekey.startswith("wfs_sig_"):
                        s_extra[ekey] = {
                            "rms": float(np.sqrt(np.mean(arr**2))),
                            "ptv": float(np.max(arr) - np.min(arr)),
                        }
                        extra_cubes[ekey].append(arr.astype(np.float32))
                    else:
                        sub = np.maximum(arr - 100.0, 0.0)
                        s_extra[ekey] = {
                            "peak_adu": float(np.max(sub)),
                            "sum_adu": float(np.sum(sub)),
                        }
                        extra_cubes[ekey].append(arr.astype(np.float32))
                s_entry["extra"] = s_extra
                sample_meta.append(s_entry)
                next_samp_ptr += 1
    finally:
        for buf in im_handles.values():
            lib.ImageStreamIO_closeIm(buf)
        for buf in extra_handles.values():
            lib.ImageStreamIO_closeIm(buf)

    denom = float(max(n_frames, 1))
    phys_s = n_frames * 0.0005

    pup_hdu = fits.PrimaryHDU(pup_amp.astype(np.float32))
    pup_hdu.header["BUNIT"] = ("amplitude", "Normalized pupil transmission amplitude")
    pup_hdu.header["ACTPIX"] = (int(np.sum(mask)), "Active clear pupil pixels")
    pup_hdu.writeto(os.path.join(out_dir, "wf_pupil_mask.fits"), overwrite=True)

    wf_summary = {
        "n_frames": n_frames,
        "phys_time_recorded_s": phys_s,
        "active_pupil_pixels": int(np.sum(mask)),
        "units": "nm",
        "locations": {},
        "samples": sample_meta,
    }

    for k, _, desc in LOCATIONS:
        mean_map = np.where(mask, sum_wf[k] / denom, 0.0)
        var_map = np.maximum(sum2_wf[k] / denom - mean_map**2, 0.0)
        std_map = np.where(mask, np.sqrt(var_map), 0.0)

        write_fits_2d(
            os.path.join(out_dir, f"wf_mean_{k}.fits"),
            mean_map,
            desc,
            "Time-averaged WF OPD [nm]",
            n_frames,
            phys_s,
        )
        write_fits_2d(
            os.path.join(out_dir, f"wf_std_{k}.fits"),
            std_map,
            desc,
            "Temporal std dev WF OPD [nm]",
            n_frames,
            phys_s,
        )

        if sample_cubes[k]:
            cube = np.stack(sample_cubes[k], axis=0).astype(np.float32)
            shdu = fits.PrimaryHDU(cube)
            shdu.header["BUNIT"] = ("nm", "Instantaneous piston-removed WF OPD [nm]")
            shdu.header["STAGE"] = (desc[:40], "Optical plane location")
            for idx, sm in enumerate(sample_meta):
                shdu.header[f"TSAMP{idx}"] = (sm["t_phys_s"], f"Sample {idx} time [s]")
                shdu.header[f"RMS{idx}"] = (
                    round(sm[k]["rms_nm"], 3),
                    f"Sample {idx} RMS [nm]",
                )
            shdu.writeto(os.path.join(out_dir, f"wf_samples_{k}.fits"), overwrite=True)

        mean_vals = mean_map[mask]
        std_vals = std_map[mask]
        mean_map_rms = math.sqrt(float(np.sum(weights * mean_map**2)))
        std_map_rms = math.sqrt(float(np.sum(weights * std_map**2)))
        quad_tot_rms = math.sqrt(sum_svar[k] / denom)
        mean_srms = sum_srms[k] / denom

        sr_vis = math.exp(-((2.0 * math.pi * (quad_tot_rms * 1e-3) / 0.75) ** 2))
        sr_nir = math.exp(-((2.0 * math.pi * (quad_tot_rms * 1e-3) / 1.65) ** 2))

        wf_summary["locations"][k] = {
            "label": desc,
            "mean_spatial_rms_nm": mean_srms,
            "quad_total_rms_nm": quad_tot_rms,
            "mean_map_rms_nm": mean_map_rms,
            "mean_map_ptv_nm": float(np.max(mean_vals) - np.min(mean_vals)),
            "std_map_rms_nm": std_map_rms,
            "std_map_median_nm": float(np.median(std_vals)),
            "std_map_p95_nm": float(np.percentile(std_vals, 95.0)),
            "std_map_max_nm": float(np.max(std_vals)),
            "marechal_sr_vis_750nm": sr_vis,
            "marechal_sr_nir_1650nm": sr_nir,
        }

    for ekey, _, _, unit, edesc in EXTRA_2D_STREAMS:
        frames = extra_cubes.get(ekey, [])
        if not frames:
            continue
        ecube = np.stack(frames, axis=0).astype(np.float32)
        ehdu = fits.PrimaryHDU(ecube)
        ehdu.header["BUNIT"] = (unit, edesc[:45])
        for idx, sm in enumerate(sample_meta):
            ehdu.header[f"TSAMP{idx}"] = (sm["t_phys_s"], f"Sample {idx} time [s]")
        ehdu.writeto(os.path.join(out_dir, f"{ekey}_samples.fits"), overwrite=True)

    with open(os.path.join(out_dir, "wf_stats.json"), "w", encoding="utf-8") as fh:
        json.dump(wf_summary, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
