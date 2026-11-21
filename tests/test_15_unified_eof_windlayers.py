# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Phase 5 (TP-5) verification: promoted mlt-windlayers + unified mkEOFPF upgrades.

Covers:
  5.1  milk-fpsexec-mlt-windlayers synthetic 2-layer (vx, vy, z) recovery.
  5.2  mkEOFPF ZOH-centered ridge, extended-memory Gram accumulator, and regime-weighted
       Gram library across recurring switching regimes.
  5.3  mkEOFPF windlayers physics-Gram Bayesian prior: cold-start rescue (N=256 vs D=192)
       and instantaneous recovery after a scripted 90-degree jet wind switch.
  5.4  mkEOFPF Pass-2 Filtered-X EOF under an underdamped ringing 3D plate-DM kernel
       plus lag->=ceil(tau) whiteness validation with cacao-fpsexec-modalwhite (TP-0).
  5.5  Real 20 s AO3k Stage-1 PSOL telemetry replay (skipped if _work artifacts absent).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

_COPY_INPLACE_FN = """
copy_inplace() {
    local src_fits="$1"
    local tmp_shm="$2"
    local dst_shm="$3"
    milk-FITS2shm --no-procinfo -n "ld_${tmp_shm}" exec "${src_fits}" "@S:${tmp_shm}" >/dev/null
    milk-fps-init -q "cp_${tmp_shm}" milk-fpsexec-mem-streamcopy >/dev/null
    milk-fps-set -q \\
        "cp_${tmp_shm}.in_sname=${tmp_shm}" \\
        "cp_${tmp_shm}.out_sname=${dst_shm}" \\
        "cp_${tmp_shm}.procinfo.loopcntMax=1"
    milk-fps-runstart -q "cp_${tmp_shm}"
    milk-fps-wait -q -t 10 "cp_${tmp_shm}"
    milk-fps-rm -f -q "cp_${tmp_shm}"
}
"""


def _run(cmd: str, env: dict[str, str], cwd: Path, timeout: int = 120) -> str:
    res = subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{cmd}"],
        cwd=cwd,
        env=env,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise AssertionError(
            f"Command failed (rc={res.returncode}):\n{cmd}\n"
            f"--- STDOUT ---\n{res.stdout}\n--- STDERR ---\n{res.stderr[-2500:]}"
        )
    return res.stdout


def _parse_fps_info(txt: str) -> dict[str, float]:
    out: dict[str, float] = {}
    clean = re.sub(r"\x1b\[[0-9;]*m", "", txt)
    for line in clean.splitlines():
        parts = line.split()
        num_types = ("FLOAT32", "FLOAT64", "UINT32", "UINT64", "INT32", "INT64")
        if len(parts) >= 4 and parts[2] in num_types:
            key = "." + parts[1].lstrip(".")
            try:
                out[key] = float(parts[3])
            except ValueError:
                pass
    return out


def _wait_cnt(shm_name: str, target_cnt: int) -> str:
    cmd = f'@get -v c s.{shm_name}.cnt0; echo \\$c'
    return (
        f'for _w in $(seq 1 200); do '
        f'c=$(milk-cli -q -e -o -c "{cmd}" 2>/dev/null || echo 0); '
        f'[ "${{c:-0}}" -ge "{target_cnt}" ] && break; sleep 0.02; done'
    )


def _eval_pf_sequence(
    pf_mat: np.ndarray,
    ol_seq: np.ndarray,
    p_eof: int,
    b_blk: int,
    lat_fr: float,
    h_mimo: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate published mkEOFPF matrix [NBmode x stride] on held-out OL sequence [T x M]."""
    t_len, nbmode = ol_seq.shape
    stride = pf_mat.shape[1]
    pb_len = p_eof * b_blk
    diag_tail = max(0, stride - pb_len)
    p_need = p_eof + diag_tail

    u_pred = np.zeros_like(ol_seq, dtype=np.float64)
    nblocks = (nbmode + b_blk - 1) // b_blk
    for blk in range(nblocks):
        s0 = blk * b_blk
        s1 = min(s0 + b_blk, nbmode)
        b = s1 - s0
        w_blk = np.zeros((p_eof * b, b), dtype=np.float64)
        for j in range(b):
            row = pf_mat[s0 + j]
            for k in range(p_eof):
                w_blk[k * b : (k + 1) * b, j] = row[k * b_blk : k * b_blk + b]
        x_rows = np.hstack(
            [ol_seq[p_need - 1 - k : t_len - k, s0:s1] for k in range(p_eof)]
        )
        u_pred[p_need - 1 :, s0:s1] = x_rows @ w_blk
        if diag_tail > 0:
            for j in range(b):
                tail = pf_mat[s0 + j, pb_len : pb_len + diag_tail]
                for kt in range(diag_tail):
                    lag = p_eof + kt
                    u_pred[p_need - 1 :, s0 + j] += (
                        tail[kt] * ol_seq[p_need - 1 - lag : t_len - lag, s0 + j]
                    )

    if h_mimo is not None:
        l_taps = h_mimo.shape[0]
        y_del = np.zeros_like(ol_seq, dtype=np.float64)
        zoh_del = np.zeros_like(ol_seq, dtype=np.float64)
        for l_idx in range(l_taps):
            y_del[l_idx:] += u_pred[: t_len - l_idx] @ h_mimo[l_idx].T
            zoh_del[l_idx:] += ol_seq[: t_len - l_idx] @ h_mimo[l_idx].T
        t0 = p_need - 1 + l_taps
        return ol_seq[t0:] - y_del[t0:], ol_seq[t0:] - zoh_del[t0:]

    lat_i = int(lat_fr)
    lat_a = lat_fr - lat_i
    t0 = p_need - 1
    t1 = t_len - lat_i - 1
    y_true = (1.0 - lat_a) * ol_seq[t0 + lat_i : t1 + lat_i] + lat_a * ol_seq[
        t0 + lat_i + 1 : t1 + lat_i + 1
    ]
    return y_true - u_pred[t0:t1], y_true - ol_seq[t0:t1]


def test_51_mlt_windlayers_promoted_unit(shm_sandbox):
    """TP-5.1: Promoted milk-fpsexec-mlt-windlayers recovers 2 synthetic layers (vx, vy, z)."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(31)
    nfr, nf, n = 2000, 256, 32
    dxf = 0.0625
    frate = 200.0
    za, zb = 8000.0, 15000.0
    sfx, sfy = 1, 0
    tfx, tfy = -1, 1
    truth = (
        ((sfx * dxf * frate, sfy * dxf * frate), za),
        ((tfx * dxf * frate, tfy * dxf * frate), zb),
    )

    k1 = np.fft.fftfreq(nf) * nf
    kx, ky = np.meshgrid(k1, k1)
    flt = np.exp(-(kx**2 + ky**2) / (2.0 * 14.0**2))

    def _scr():
        s = np.fft.ifft2(np.fft.fft2(rng.normal(size=(nf, nf))) * flt).real
        return s * (1e-7 / np.std(s))

    sa, sb = _scr(), _scr()
    d2 = dxf * dxf
    la = (
        np.roll(sa, 1, axis=1) + np.roll(sa, -1, axis=1)
        + np.roll(sa, 1, axis=0) + np.roll(sa, -1, axis=0) - 4.0 * sa
    ) / d2
    lb = (
        np.roll(sb, 1, axis=1) + np.roll(sb, -1, axis=1)
        + np.roll(sb, 1, axis=0) + np.roll(sb, -1, axis=0) - 4.0 * sb
    ) / d2

    yy, xx = np.mgrid[0:n, 0:n]
    rr = np.hypot(xx - (n / 2.0 - 0.5), yy - (n / 2.0 - 0.5))
    pup = ((rr <= 15.0) & (rr >= 4.5)).astype(np.float64)

    icube = np.empty((nfr, n, n), dtype=np.float32)
    pcube = np.empty((nfr, 2 * n, 2 * n), dtype=np.float32)
    for k in range(nfr):
        ra = np.roll(np.roll(sa, sfx * k, axis=1), sfy * k, axis=0)[:128, :128]
        rb = np.roll(np.roll(sb, tfx * k, axis=1), tfy * k, axis=0)[:128, :128]
        qa = np.roll(np.roll(la, sfx * k, axis=1), sfy * k, axis=0)[:128, :128]
        qb = np.roll(np.roll(lb, tfx * k, axis=1), tfy * k, axis=0)[:128, :128]
        im = pup * (1.0 - za * qa.reshape(n, 4, n, 4).mean(axis=(1, 3))
                    - zb * qb.reshape(n, 4, n, 4).mean(axis=(1, 3)))
        icube[k] = im.astype(np.float32)
        opd_m = (ra + rb).reshape(2 * n, 2, 2 * n, 2).mean(axis=(1, 3)) * 1e6
        pcube[k] = opd_m.astype(np.float32)

    fits.writeto(work_dir / "ic.fits", icube, overwrite=True)
    fits.writeto(work_dir / "pc.fits", pcube, overwrite=True)

    cmd = """
milk-FITS2shm --no-procinfo -n ldi exec ic.fits @S:w51_i >/dev/null
milk-FITS2shm --no-procinfo -n ldp exec pc.fits @S:w51_p >/dev/null
milk-fpsexec-mlt-windlayers --no-procinfo -n w51 exec \\
    .wfs=w51_i .pha=w51_p .outname=w51 .wfsmode=1 \\
    .frate=200 .diam=7.5 .diampix=30 .phaunit=1e-6 .phasign=1 .vmax=30 >/dev/null
milk-fpsexec-iofits-saveFITS --no-procinfo -n sv51 exec w51_layers "!w51_layers.fits" >/dev/null
"""
    _run(cmd, env, work_dir)
    tbl = fits.getdata(work_dir / "w51_layers.fits").astype(np.float64)
    valid = tbl[tbl[:, 15] >= 0.5]
    assert len(valid) >= 2, f"Expected >=2 layers, got {tbl}"
    for (vx_t, vy_t), z_t in truth:
        found = any(
            np.hypot(r[0] - vx_t, r[1] - vy_t) < 0.5 and abs(r[10] / z_t - 1.0) < 0.08
            for r in valid
        )
        assert found, f"Missing ({vx_t}, {vy_t}) @ {z_t} m in {valid[:, [0, 1, 10, 15]]}"


def test_52_mkeofpf_zoh_ridge_extended_memory_and_regime_library(shm_sandbox):
    """TP-5.2: ZOH-centered ridge, extended-memory Gram, and regime-weighted Gram library."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(101)

    # --- Part A: ZOH-centered ridge beats zero-centered ridge on slow modes at high lambda ---
    nbm, nsl = 32, 256
    t_tot = nsl * 3
    slow = np.zeros((t_tot, nbm), dtype=np.float32)
    eps = rng.normal(0.0, 0.03, size=(t_tot, nbm)).astype(np.float32)
    for t in range(1, t_tot):
        slow[t] = 0.985 * slow[t - 1] + eps[t]
    for i in range(3):
        fits.writeto(work_dir / f"zoh_s{i}.fits", slow[i * nsl : (i + 1) * nsl], overwrite=True)

    res_zoh: dict[str, dict[str, float]] = {}
    for mode_tag, zoh_flag in (("off", "OFF"), ("on", "ON")):
        cmd = f"""
{_COPY_INPLACE_FN}
milk-FITS2shm --no-procinfo -n l0_{mode_tag} exec zoh_s0.fits @S:ol_zoh_{mode_tag} >/dev/null
milk-fps-init -q mk_{mode_tag} cacao-fpsexec-cacaopc-mkEOFPF
milk-fps-set -q \\
    mk_{mode_tag}.inbuff=ol_zoh_{mode_tag} \\
    mk_{mode_tag}.outPF=pf_zoh_{mode_tag} \\
    mk_{mode_tag}.PForder=6 \\
    mk_{mode_tag}.diagorder=6 \\
    mk_{mode_tag}.blocksize=32 \\
    mk_{mode_tag}.PFlatency=2.0 \\
    mk_{mode_tag}.NBtrain=512 \\
    mk_{mode_tag}.diagminsamples=128 \\
    mk_{mode_tag}.minsamples=256 \\
    mk_{mode_tag}.updateperiod=1 \\
    mk_{mode_tag}.reglambda=0.08 \\
    mk_{mode_tag}.zoh_ridge={zoh_flag} \\
    mk_{mode_tag}.loopgain=1.0 \\
    mk_{mode_tag}.procinfo.triggermode=3 \\
    mk_{mode_tag}.procinfo.triggersname=ol_zoh_{mode_tag} \\
    mk_{mode_tag}.procinfo.loopcntMax=-1
milk-fps-runstart -q mk_{mode_tag}
sleep 0.15
for i in 0 1 2; do
    copy_inplace "zoh_s${{i}}.fits" "ztmp_{mode_tag}_${{i}}" ol_zoh_{mode_tag}
    sleep 0.15
done
milk-fps-info mk_{mode_tag}
milk-fps-runstop -q mk_{mode_tag}
milk-fps-wait -q -t 10 mk_{mode_tag}
milk-fps-rm -f -q mk_{mode_tag}
"""
        res_zoh[mode_tag] = _parse_fps_info(_run(cmd, env, work_dir))

    assert res_zoh["on"][".out.rms_pred_oos"] < res_zoh["off"][".out.rms_pred_oos"], res_zoh
    assert res_zoh["on"][".out.var_red_oos_pct"] > res_zoh["off"][".out.var_red_oos_pct"] + 2.0, (
        res_zoh
    )

    # --- Part B: Extended-memory + regime-weighted Gram library across recurring regimes ---
    # Two distinct coupled-mode advection regimes A (+shift) and B (-shift), 1024 frames/slice:
    # Sequence: 6 slices of A (6k) -> 6 slices of B (6k) -> 1 slice of A (return to A) + test A.
    nbm_r, nsl_r, p_r, b_r = 24, 1024, 4, 24
    # Build two orthogonal cross-mode shift-coupled stable VAR(1) transition matrices
    a_mat = np.zeros((nbm_r, nbm_r), dtype=np.float64)
    b_mat = np.zeros((nbm_r, nbm_r), dtype=np.float64)
    for m in range(nbm_r):
        a_mat[m, m] = 0.35
        a_mat[m, (m + 1) % nbm_r] = 0.62
        b_mat[m, m] = 0.35
        b_mat[m, (m - 1) % nbm_r] = 0.62

    def _gen_regime(mat: np.ndarray, n_fr: int) -> np.ndarray:
        x = np.zeros((n_fr + 64, nbm_r), dtype=np.float64)
        e = rng.normal(0.0, 0.05, size=(n_fr + 64, nbm_r))
        for t in range(1, n_fr + 64):
            x[t] = x[t - 1] @ mat.T + e[t]
        return x[64:].astype(np.float32)

    seq_a1 = _gen_regime(a_mat, 6 * nsl_r)
    seq_b1 = _gen_regime(b_mat, 6 * nsl_r)
    seq_a_ret = _gen_regime(a_mat, 512)
    seq_a_test = _gen_regime(a_mat, 2048)

    slices = (
        [(seq_a1[i * nsl_r : (i + 1) * nsl_r], (+6.0, 0.0, 0.0, 0.0)) for i in range(6)]
        + [(seq_b1[i * nsl_r : (i + 1) * nsl_r], (-6.0, 0.0, 0.0, 0.0)) for i in range(6)]
        + [(seq_a_ret, (+6.0, 0.0, 0.0, 0.0))]
    )
    for idx, (arr, rvec) in enumerate(slices):
        fits.writeto(work_dir / f"rg_s{idx}.fits", arr, overwrite=True)
        fits.writeto(
            work_dir / f"rg_d{idx}.fits", np.array(rvec, dtype=np.float32), overwrite=True
        )

    configs = {
        "slide": "gram_halflife=0 regime_kmax=0",
        "pool": "gram_halflife=1000000 regime_kmax=0",
        "regime": (
            "gram_halflife=1000000 regime_kmax=4 regime_kappa=0.05 "
            "regime_bw=1.5 regime_rlim=2.0 regime_in=reg_vec"
        ),
    }
    eval_rms: dict[str, float] = {}
    infos: dict[str, dict[str, float]] = {}

    for tag, extra in configs.items():
        extra_set = " ".join(f"mk_{tag}.{kv}" for kv in extra.split())
        cmd = f"""
{_COPY_INPLACE_FN}
milk-FITS2shm --no-procinfo -n l0_{tag} exec rg_s0.fits @S:ol_{tag} >/dev/null
milk-FITS2shm --no-procinfo -n d0_{tag} exec rg_d0.fits @S:reg_vec >/dev/null
milk-fps-init -q mk_{tag} cacao-fpsexec-cacaopc-mkEOFPF
milk-fps-set -q \\
    mk_{tag}.inbuff=ol_{tag} \\
    mk_{tag}.outPF=pf_{tag} \\
    mk_{tag}.PForder={p_r} \\
    mk_{tag}.diagorder={p_r} \\
    mk_{tag}.blocksize={b_r} \\
    mk_{tag}.PFlatency=2.0 \\
    mk_{tag}.NBtrain=2048 \\
    mk_{tag}.diagminsamples=256 \\
    mk_{tag}.minsamples=1024 \\
    mk_{tag}.updateperiod=1 \\
    mk_{tag}.reglambda=1e-4 \\
    mk_{tag}.maxnorm2=8.0 \\
    mk_{tag}.loopgain=1.0 \\
    {extra_set} \\
    mk_{tag}.procinfo.triggermode=3 \\
    mk_{tag}.procinfo.triggersname=ol_{tag} \\
    mk_{tag}.procinfo.loopcntMax=-1
milk-fps-runstart -q mk_{tag}
sleep 0.15
for i in $(seq 0 {len(slices) - 1}); do
    copy_inplace "rg_d${{i}}.fits" "dt_{tag}_${{i}}" reg_vec
    copy_inplace "rg_s${{i}}.fits" "st_{tag}_${{i}}" ol_{tag}
    sleep 0.12
done
milk-fps-info mk_{tag}
milk-fpsexec-iofits-saveFITS --no-procinfo -n sv_{tag} exec pf_{tag} "!pf_{tag}.fits" >/dev/null
milk-fps-runstop -q mk_{tag}
milk-fps-wait -q -t 10 mk_{tag}
milk-fps-rm -f -q mk_{tag}
"""
        infos[tag] = _parse_fps_info(_run(cmd, env, work_dir))
        pf = fits.getdata(work_dir / f"pf_{tag}.fits").astype(np.float64)
        err_p, err_z = _eval_pf_sequence(pf, seq_a_test, p_r, b_r, 2.0)
        vr_pct = (1.0 - float(np.mean(err_p**2) / np.mean(err_z**2))) * 100.0
        eval_rms[tag] = vr_pct

    assert infos["regime"][".out.eff_samples"] > 4000.0, infos["regime"]
    assert int(infos["regime"][".out.regime_k"]) == 2, infos["regime"]
    assert eval_rms["regime"] > eval_rms["slide"] + 8.0, f"vr_pct: {eval_rms}"
    assert eval_rms["regime"] > eval_rms["pool"] + 5.0, f"vr_pct: {eval_rms}"
    assert eval_rms["regime"] > 55.0, f"vr_pct: {eval_rms}"
    print(f"[TP-5.2] ZOH on={res_zoh['on']['.out.var_red_oos_pct']:.1f}% vs "
          f"off={res_zoh['off']['.out.var_red_oos_pct']:.1f}% | "
          f"Regime VR%={eval_rms}")


def _build_frozen_flow_modal_problem(
    rng: np.random.Generator,
    nx: int = 16,
    n_modes: int = 32,
    pup_diam: float = 8.0,
    frate: float = 200.0,
    l0_m: float = 25.0,
):
    """Build 32 orthogonal 2D modes on an nx x nx pupil and an exact frozen-flow generator."""
    yy, xx = np.mgrid[0:nx, 0:nx]
    x_n = (xx - (nx - 1) / 2.0) / (nx / 2.0)
    y_n = (yy - (nx - 1) / 2.0) / (nx / 2.0)
    pup = (x_n**2 + y_n**2 <= 0.92**2).astype(np.float64)

    # Low-order 2D Fourier / polynomial modes orthonormalized on the pupil
    basis = []
    for ky in range(-3, 4):
        for kx in range(-3, 4):
            if kx == 0 and ky == 0:
                continue
            r2 = kx * kx + ky * ky
            basis.append((r2, np.cos(np.pi * (kx * x_n + ky * y_n)) * pup))
            basis.append((r2, np.sin(np.pi * (kx * x_n + ky * y_n)) * pup))
    basis.sort(key=lambda item: item[0])
    raw = np.stack([b[1].ravel() for b in basis[: n_modes + 8]], axis=0)
    q_mat, _ = np.linalg.qr(raw.T)
    modes = q_mat[:, :n_modes].T.reshape(n_modes, nx, nx).astype(np.float64)

    # Exact dual basis W so a = screen_flat @ W.T
    m_flat = modes.reshape(n_modes, -1)
    g_m = m_flat @ m_flat.T
    w_dual = np.linalg.solve(g_m + 1e-6 * np.eye(n_modes), m_flat)

    dx = pup_diam / nx
    n_scr = 128
    f1 = np.fft.fftfreq(n_scr, dx)
    fx, fy = np.meshgrid(f1, f1)
    psd = (fx**2 + fy**2 + (1.0 / l0_m) ** 2) ** (-11.0 / 6.0)
    psd[0, 0] = 0.0
    amp = np.sqrt(psd)

    def _sim(layers: list[tuple[float, float, float]], n_frames: int, noise_rel: float = 0.03):
        screens_f = []
        weights = []
        for vx, vy, w_l in layers:
            white = rng.normal(size=(n_scr, n_scr))
            sf = np.fft.fft2(white) * amp
            screens_f.append((sf, vx, vy))
            weights.append(np.sqrt(w_l))
        dt = 1.0 / frate
        out = np.zeros((n_frames, n_modes), dtype=np.float64)
        for t in range(n_frames):
            tau = t * dt
            tot_opd = np.zeros((nx, nx), dtype=np.float64)
            for (sf, vx, vy), wt in zip(screens_f, weights):
                ph = np.exp(-2j * np.pi * (fx * vx + fy * vy) * tau)
                scr = np.fft.ifft2(sf * ph).real
                tot_opd += wt * scr[:nx, :nx]
            out[t] = tot_opd.ravel() @ w_dual.T
        sig_rms = np.sqrt(np.mean(out**2))
        out /= (sig_rms + 1e-12)
        out += rng.normal(0.0, noise_rel, size=out.shape)
        return out.astype(np.float32)

    return modes.astype(np.float32), _sim


def _make_wl_table(layers: list[tuple[float, float, float]]) -> np.ndarray:
    """Create [8 x 16] wl_layers table matching windlayers_unit.c column layout."""
    tbl = np.zeros((8, 16), dtype=np.float32)
    for idx, (vx, vy, frac) in enumerate(layers[:8]):
        tbl[idx, 0] = vx
        tbl[idx, 1] = vy
        tbl[idx, 2] = np.hypot(vx, vy)
        tbl[idx, 3] = np.degrees(np.arctan2(vy, vx))
        tbl[idx, 4] = 40.0
        tbl[idx, 5] = frac
        tbl[idx, 8] = frac
        tbl[idx, 15] = 1.0
    return tbl


def test_53_mkeofpf_windlayers_physics_prior_coldstart_and_switch(shm_sandbox):
    """TP-5.3: windlayers physics-Gram prior rescues cold start (N=256) and 90-deg wind switch."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(77)

    modes, sim_fn = _build_frozen_flow_modal_problem(
        rng, nx=16, n_modes=32, pup_diam=8.0, frate=200.0
    )
    fits.writeto(work_dir / "dmmodes.fits", modes, overwrite=True)

    layers_east = [(10.0, 0.0, 0.55), (26.0, 0.0, 0.45)]
    layers_north = [(0.0, 10.0, 0.55), (0.0, 26.0, 0.45)]
    fits.writeto(work_dir / "wl_east.fits", _make_wl_table(layers_east), overwrite=True)
    fits.writeto(work_dir / "wl_north.fits", _make_wl_table(layers_north), overwrite=True)

    # Generate East-wind cold-start slice (256 frames), long East-wind warm slices, and North switch
    east_all = sim_fn(layers_east, 4608, noise_rel=0.04)
    north_all = sim_fn(layers_north, 2304, noise_rel=0.04)
    east_cold = east_all[:256]
    east_test = east_all[256:1536]
    north_trig = north_all[:256]
    north_test = north_all[256:1792]

    fits.writeto(work_dir / "east_cold.fits", east_cold, overwrite=True)
    for k in range(4):
        fits.writeto(
            work_dir / f"east_w{k}.fits",
            east_all[1536 + k * 768 : 1536 + (k + 1) * 768],
            overwrite=True,
        )
    fits.writeto(work_dir / "north_trig.fits", north_trig, overwrite=True)

    # 1) Cold-start (N=256 vs D=192): plain empirical EOF vs windlayers physics-Gram prior
    p_ord, b_sz = 6, 32
    vr_cold: dict[str, float] = {}
    vr_sw: dict[str, float] = {}
    info_phys: dict[str, float] = {}

    for tag, use_phys in (("emp", False), ("phys", True)):
        phys_args = (
            f"mk_{tag}.dmmodes=dmmodes.fits mk_{tag}.wl_layers=wl_{tag} "
            f"mk_{tag}.pup_diam=8.0 mk_{tag}.frate_hz=200.0 mk_{tag}.l0_m=25.0 "
            f"mk_{tag}.n_prior=2048 mk_{tag}.wl_switch_decay=0.15"
            if use_phys
            else f"mk_{tag}.n_prior=0"
        )
        cmd = f"""
{_COPY_INPLACE_FN}
milk-FITS2shm --no-procinfo -n l0_{tag} exec east_cold.fits @S:ol_{tag} >/dev/null
milk-FITS2shm --no-procinfo -n wl0_{tag} exec wl_east.fits @S:wl_{tag} >/dev/null
milk-fps-init -q mk_{tag} cacao-fpsexec-cacaopc-mkEOFPF
milk-fps-set -q \\
    mk_{tag}.inbuff=ol_{tag} \\
    mk_{tag}.outPF=pf_{tag} \\
    mk_{tag}.PForder={p_ord} \\
    mk_{tag}.diagorder={p_ord} \\
    mk_{tag}.blocksize={b_sz} \\
    mk_{tag}.PFlatency=2.0 \\
    mk_{tag}.NBtrain=4096 \\
    mk_{tag}.diagminsamples=128 \\
    mk_{tag}.minsamples=256 \\
    mk_{tag}.updateperiod=1 \\
    mk_{tag}.reglambda=1e-4 \\
    mk_{tag}.gram_halflife=4096 \\
    mk_{tag}.loopgain=1.0 \\
    {phys_args} \\
    mk_{tag}.procinfo.triggermode=3 \\
    mk_{tag}.procinfo.triggersname=ol_{tag} \\
    mk_{tag}.procinfo.loopcntMax=-1
milk-fps-runstart -q mk_{tag}
sleep 0.15
# Cold start: single 256-frame East slice
copy_inplace east_cold.fits cs_{tag} ol_{tag}
sleep 0.25
milk-fpsexec-iofits-saveFITS --no-procinfo -n svc_{tag} \\
    exec pf_{tag} "!pf_cold_{tag}.fits" >/dev/null
# Warm up on 3072 more East frames
for k in 0 1 2 3; do
    copy_inplace "east_w${{k}}.fits" "ew_{tag}_${{k}}" ol_{tag}
    sleep 0.15
done
# Scripted 90-degree wind switch to North + 256-frame North trigger
copy_inplace wl_north.fits wln_{tag} wl_{tag}
copy_inplace north_trig.fits nt_{tag} ol_{tag}
sleep 0.25
milk-fps-info mk_{tag}
milk-fpsexec-iofits-saveFITS --no-procinfo -n svs_{tag} exec pf_{tag} "!pf_sw_{tag}.fits" >/dev/null
milk-fps-runstop -q mk_{tag}
milk-fps-wait -q -t 10 mk_{tag}
milk-fps-rm -f -q mk_{tag}
"""
        inf = _parse_fps_info(_run(cmd, env, work_dir))
        if use_phys:
            info_phys = inf
        pf_c = fits.getdata(work_dir / f"pf_cold_{tag}.fits").astype(np.float64)
        ep_c, ez_c = _eval_pf_sequence(pf_c, east_test, p_ord, b_sz, 2.0)
        vr_cold[tag] = (1.0 - float(np.mean(ep_c**2) / np.mean(ez_c**2))) * 100.0

        pf_s = fits.getdata(work_dir / f"pf_sw_{tag}.fits").astype(np.float64)
        ep_s, ez_s = _eval_pf_sequence(pf_s, north_test, p_ord, b_sz, 2.0)
        vr_sw[tag] = (1.0 - float(np.mean(ep_s**2) / np.mean(ez_s**2))) * 100.0

    assert int(info_phys[".out.phys_active"]) == 1, info_phys
    assert int(info_phys[".out.wl_switches"]) >= 1, info_phys
    # Cold start: physics-Gram prior strongly beats overfitted empirical N=256 EOF
    assert vr_cold["phys"] > 35.0, f"Cold-start VR%: {vr_cold}"
    assert vr_cold["phys"] > vr_cold["emp"] + 15.0, f"Cold-start VR%: {vr_cold}"
    # Post 90-deg wind switch: physics-Gram prior rescues OOS immediately vs stale East empirical
    assert vr_sw["phys"] > 30.0, f"Wind-switch VR%: {vr_sw}"
    assert vr_sw["phys"] > vr_sw["emp"] + 25.0, f"Wind-switch VR%: {vr_sw}"
    print(f"[TP-5.3] Cold-start VR%={vr_cold} | Post-switch VR%={vr_sw} | "
          f"switches={int(info_phys['.out.wl_switches'])}")


def test_54_mkeofpf_filtered_x_ringing_dm_and_modalwhite(shm_sandbox):
    """TP-5.4: Pass-2 Filtered-X EOF beats pure-delay EOF on ringing 3D DM + modalwhite check."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(2026)

    nbm, p_ord, b_sz = 16, 10, 16
    # Underdamped 2nd-order 10-tap plate-DM kernel (f_res = 0.20 fs, zeta = 0.18) + MIMO coupling
    t_ir = np.arange(8, dtype=np.float64)
    w0 = 2.0 * np.pi * 0.20
    zeta = 0.18
    wd = w0 * np.sqrt(1.0 - zeta**2)
    h_tap = np.zeros(10, dtype=np.float64)
    h_tap[2:] = np.exp(-zeta * w0 * t_ir) * (np.cos(wd * t_ir) + 0.3 * np.sin(wd * t_ir))
    h_tap /= np.sum(h_tap)
    l_taps = len(h_tap)
    h_mimo = np.zeros((l_taps, nbm, nbm), dtype=np.float32)
    for l_idx, hv in enumerate(h_tap):
        h_mimo[l_idx] = hv * np.eye(nbm, dtype=np.float32)
    # Cross-mode plate coupling at ringing taps 2 & 4
    for m in range(nbm - 1):
        h_mimo[2, m, m + 1] = 0.18
        h_mimo[2, m + 1, m] = 0.18
        h_mimo[4, m, m + 1] = -0.18
        h_mimo[4, m + 1, m] = -0.18
    centroid = float(np.sum(np.arange(l_taps) * h_tap) / np.sum(h_tap))
    fits.writeto(work_dir / "H_mimo.fits", h_mimo, overwrite=True)

    # Correlated AR(2) modal turbulence: 6 training slices (6144 fr) + 2048 held-out test frames
    n_tr, n_te = 6144, 2048
    ol_all = np.zeros((n_tr + n_te + 64, nbm), dtype=np.float64)
    eps = rng.normal(0.0, 0.05, size=ol_all.shape)
    for t in range(2, len(ol_all)):
        ol_all[t] = 1.65 * ol_all[t - 1] - 0.72 * ol_all[t - 2] + eps[t]
    ol_tr = ol_all[64 : 64 + n_tr].astype(np.float32)
    ol_te = ol_all[64 + n_tr :].astype(np.float32)

    nsl = 1024
    for i in range(6):
        fits.writeto(work_dir / f"fx_s{i}.fits", ol_tr[i * nsl : (i + 1) * nsl], overwrite=True)

    res_fx: dict[str, dict[str, float]] = {}
    del_err: dict[str, np.ndarray] = {}
    del_rms: dict[str, float] = {}
    zoh_rms = 0.0

    for tag, kern_arg in (("delay", ""), ("fx", "H_mimo.fits")):
        k_set = f"mk_{tag}.dm_kernel={kern_arg}" if kern_arg else ""
        cmd = f"""
{_COPY_INPLACE_FN}
milk-FITS2shm --no-procinfo -n l0_{tag} exec fx_s0.fits @S:ol_{tag} >/dev/null
milk-fps-init -q mk_{tag} cacao-fpsexec-cacaopc-mkEOFPF
milk-fps-set -q \\
    mk_{tag}.inbuff=ol_{tag} \\
    mk_{tag}.outPF=pf_{tag} \\
    mk_{tag}.PForder={p_ord} \\
    mk_{tag}.diagorder={p_ord} \\
    mk_{tag}.blocksize={b_sz} \\
    mk_{tag}.PFlatency={centroid:.3f} \\
    mk_{tag}.NBtrain=6144 \\
    mk_{tag}.diagminsamples=256 \\
    mk_{tag}.minsamples=2048 \\
    mk_{tag}.updateperiod=1 \\
    mk_{tag}.reglambda=1e-4 \\
    mk_{tag}.maxnorm2=8.0 \\
    mk_{tag}.loopgain=1.0 \\
    {k_set} \\
    mk_{tag}.procinfo.triggermode=3 \\
    mk_{tag}.procinfo.triggersname=ol_{tag} \\
    mk_{tag}.procinfo.loopcntMax=-1
milk-fps-runstart -q mk_{tag}
sleep 0.15
for i in 0 1 2 3 4 5; do
    copy_inplace "fx_s${{i}}.fits" "ft_{tag}_${{i}}" ol_{tag}
    sleep 0.15
done
milk-fps-info mk_{tag}
milk-fpsexec-iofits-saveFITS --no-procinfo -n sv_{tag} exec pf_{tag} "!pf_{tag}.fits" >/dev/null
milk-fps-runstop -q mk_{tag}
milk-fps-wait -q -t 10 mk_{tag}
milk-fps-rm -f -q mk_{tag}
"""
        res_fx[tag] = _parse_fps_info(_run(cmd, env, work_dir))
        pf = fits.getdata(work_dir / f"pf_{tag}.fits").astype(np.float64)
        ep, ez = _eval_pf_sequence(
            pf, ol_te, p_ord, b_sz, centroid, h_mimo=h_mimo.astype(np.float64)
        )
        del_err[tag] = ep
        del_rms[tag] = float(np.sqrt(np.mean(ep**2)))
        zoh_rms = float(np.sqrt(np.mean(ez**2)))

    assert int(res_fx["fx"][".out.fx_active"]) == 1, res_fx["fx"]
    assert int(res_fx["delay"][".out.fx_active"]) == 0, res_fx["delay"]
    assert res_fx["fx"][".out.var_red_oos_pct"] > 25.0, res_fx["fx"]
    # Filtered-X strictly beats both pure-delay EOF (which excites ringing) and ZOH
    assert del_rms["fx"] < del_rms["delay"] * 0.85, f"del_rms={del_rms}, zoh={zoh_rms}"
    assert del_rms["fx"] < zoh_rms * 0.88, f"del_rms={del_rms}, zoh={zoh_rms}"

    # Verify TP-0 modalwhite lag->=ceil(tau) whiteness improvement on delivered residuals
    mw_q: dict[str, dict[str, float]] = {}
    for tag in ("delay", "fx"):
        fits.writeto(work_dir / f"res_{tag}.fits", del_err[tag].astype(np.float32), overwrite=True)
        cmd_mw = f"""
milk-FITS2shm --no-procinfo -n lw_{tag} exec res_{tag}.fits @S:wfs_{tag} >/dev/null
milk-fps-init -q mw_{tag} cacao-fpsexec-modalwhite
milk-fps-set -q \\
    mw_{tag}.AOloopindex=0 \\
    mw_{tag}.inWFSbuff=wfs_{tag} \\
    mw_{tag}.inDMbuff=none \\
    mw_{tag}.latency_fr=2.0 \\
    mw_{tag}.NBwin={del_err[tag].shape[0]} \\
    mw_{tag}.K_lags=12 \\
    mw_{tag}.P_recov=8 \\
    mw_{tag}.blocksize={b_sz} \\
    mw_{tag}.procinfo.triggermode=0 \\
    mw_{tag}.procinfo.loopcntMax=1
milk-fps-runstart -q mw_{tag}
milk-fps-wait -q -t 15 mw_{tag}
milk-fps-info mw_{tag}
milk-fps-rm -f -q mw_{tag}
"""
        mw_q[tag] = _parse_fps_info(_run(cmd_mw, env, work_dir))

    assert mw_q["fx"][".out.Q_vw_b0"] < mw_q["delay"][".out.Q_vw_b0"] * 0.35, mw_q
    assert mw_q["fx"][".out.recov_var_pct"] < mw_q["delay"][".out.recov_var_pct"], mw_q
    assert mw_q["fx"][".out.recov_var_pct"] < 5.0, mw_q
    print(f"[TP-5.4] del_rms={del_rms} zoh={zoh_rms:.4f} | "
          f"fx_oos_vr={res_fx['fx']['.out.var_red_oos_pct']:.1f}% | "
          f"Q_vw delay={mw_q['delay']['.out.Q_vw_b0']:.1f} -> fx={mw_q['fx']['.out.Q_vw_b0']:.2f}")


def test_55_mkeofpf_real_ao3k_20s_psol_telemetry(repo_root, shm_sandbox):
    """TP-5.5: Real AO3k Stage-1 1 kHz PSOL telemetry cold-start & 10 s replay check."""
    tlm_dir = repo_root / "_work" / "ao3k_scexao_tlm20s_ar16" / "telemetry"
    dmm_path = repo_root / "_work" / "wind_layers" / "ao3k_s1_dmmodes.fits"
    ol_files = sorted(tlm_dir.glob("aol1_modevalOL_*.fits"))
    if not ol_files or not dmm_path.is_file():
        pytest.skip("AO3k 20 s PSOL telemetry or ao3k_s1_dmmodes.fits not present")

    _shm_dir, work_dir, env = shm_sandbox
    nbm = 64
    chunks = []
    for p in ol_files[:3]:
        arr = fits.getdata(p).astype(np.float32)
        chunks.append(arr.reshape(-1, arr.shape[-1])[:, :nbm])
    ol_seq = np.concatenate(chunks, axis=0)
    if ol_seq.shape[0] < 6144:
        pytest.skip("Insufficient AO3k PSOL frames")

    dm64 = fits.getdata(dmm_path).astype(np.float32)[:nbm]
    fits.writeto(work_dir / "ao3k_dm64.fits", dm64, overwrite=True)

    # Known AO3k Subaru 7.95 m pupil truth wind profile (from eof_wind_study.py)
    scale_v = 0.068333 / (7.95 / 240.0)
    prof = [
        (5.32, 6.50, 1.47),
        (1.47, 6.55, 1.57),
        (1.08, 6.60, 1.67),
        (2.11, 6.70, 1.77),
        (1.83, 22.00, 3.10),
        (1.48, 9.50, 3.20),
        (0.697, 5.60, 3.30),
    ]
    c_tot = sum(r[0] for r in prof)
    wl_layers = [
        (-sp * scale_v * np.cos(ang), -sp * scale_v * np.sin(ang), cn2 / c_tot)
        for cn2, sp, ang in prof
    ]
    fits.writeto(work_dir / "ao3k_wl.fits", _make_wl_table(wl_layers), overwrite=True)

    # Cold start: 1024 frames training, 2048 frames held-out evaluation (B=64, P=8, D=512)
    ol_cold = ol_seq[1000:2024]
    ol_test = ol_seq[2024:4072]
    fits.writeto(work_dir / "ao3k_c0.fits", ol_cold, overwrite=True)

    vr_ao3k: dict[str, float] = {}
    for tag, use_phys in (("emp", False), ("phys", True)):
        p_args = (
            f"mk_{tag}.dmmodes=ao3k_dm64.fits mk_{tag}.wl_layers=wl_ao3k "
            f"mk_{tag}.pup_diam=7.95 mk_{tag}.dm_dx={7.95 / 60.0:.6f} "
            f"mk_{tag}.frate_hz=1000.0 mk_{tag}.l0_m=25.0 mk_{tag}.n_prior=2048"
            if use_phys
            else f"mk_{tag}.n_prior=0"
        )
        cmd = f"""
{_COPY_INPLACE_FN}
milk-FITS2shm --no-procinfo -n l0_{tag} exec ao3k_c0.fits @S:ol_{tag} >/dev/null
milk-FITS2shm --no-procinfo -n w0_{tag} exec ao3k_wl.fits @S:wl_ao3k >/dev/null
milk-fps-init -q mk_{tag} cacao-fpsexec-cacaopc-mkEOFPF
milk-fps-set -q \\
    mk_{tag}.inbuff=ol_{tag} \\
    mk_{tag}.outPF=pf_{tag} \\
    mk_{tag}.PForder=8 \\
    mk_{tag}.diagorder=8 \\
    mk_{tag}.blocksize=64 \\
    mk_{tag}.PFlatency=2.4 \\
    mk_{tag}.NBtrain=4096 \\
    mk_{tag}.diagminsamples=256 \\
    mk_{tag}.minsamples=1024 \\
    mk_{tag}.updateperiod=1 \\
    mk_{tag}.reglambda=1e-4 \\
    mk_{tag}.zoh_ridge=ON \\
    mk_{tag}.loopgain=1.0 \\
    {p_args} \\
    mk_{tag}.procinfo.triggermode=3 \\
    mk_{tag}.procinfo.triggersname=ol_{tag} \\
    mk_{tag}.procinfo.loopcntMax=-1
milk-fps-runstart -q mk_{tag}
sleep 0.2
copy_inplace ao3k_c0.fits c0_{tag} ol_{tag}
sleep 0.6
milk-fpsexec-iofits-saveFITS --no-procinfo -n sv_{tag} \\
    exec pf_{tag} "!pf_ao3k_{tag}.fits" >/dev/null
milk-fps-runstop -q mk_{tag}
milk-fps-wait -q -t 10 mk_{tag}
milk-fps-rm -f -q mk_{tag}
"""
        _run(cmd, env, work_dir)
        pf = fits.getdata(work_dir / f"pf_ao3k_{tag}.fits").astype(np.float64)
        ep, ez = _eval_pf_sequence(pf, ol_test, 8, 64, 2.4)
        vr_ao3k[tag] = (1.0 - float(np.mean(ep**2) / np.mean(ez**2))) * 100.0

    assert vr_ao3k["phys"] > 50.0, f"AO3k cold-start VR%: {vr_ao3k}"
    assert vr_ao3k["phys"] > vr_ao3k["emp"] + 15.0, f"AO3k cold-start VR%: {vr_ao3k}"
    print(f"[TP-5.5] Real AO3k 1 kHz Block-0 cold-start (N=1024) VR%={vr_ao3k}")
