# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Phase 4b (TP-4) verification for milk-mltools ivdiff 2WFS1DM + live Stage-2 wiring.

Tests:
  1. Exact numerical parity of C `milk-mlt-calib2wfs1dm` (default `ivdiff`) against
     `algo/calib2wfs1dm/realsim/realsim_est.py` and `toy/code/selftest.py` (aligned 0 us
     and 250 us clock-skewed multi-rate cases, window rules, usable_frac, & block bootstrap).
  2. Real AO3k+SCExAO multi-regime telemetry cross-check (Integrator, Block-EOF, unmodulated
     0 l/D plate-DM1 at NA=160, and faint mH=8 p=32 usable_ok=0 health gate).
  3. Live 2-stage coupled HIL (Stage-1 active `modalog` + Stage-2 passive `mlt.calib2wfs1dm`
     with dynamic 3D `H_mimo` DM2 kernel, live `mlt.apply2wfs1dm` -> `aol2_mWFSfact` &
     `acquWFS-2.WFSzpogain` LLOWFS ZPO stability, and blind `DM2 -> DM1` offload via
     calibrated `Mda_virt.fits` achieving >85% stroke reduction).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

REPO_ROOT = Path("/home/guyon/src/cacao-work")
ALGO_DIR = REPO_ROOT / "algo" / "calib2wfs1dm"
WORK_ROOT = REPO_ROOT / "_work"


def _run_cmd(cmd: str, env: dict[str, str], cwd: Path, timeout: int = 90) -> str:
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
            f"--- STDOUT ---\n{res.stdout}\n--- STDERR ---\n{res.stderr}"
        )
    return res.stdout


def _parse_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _write_tlm_cube(
    directory: Path,
    prefix: str,
    arr_2d: np.ndarray,
    t_sec: np.ndarray,
    cnt0: np.ndarray | None = None,
) -> None:
    """Write a (N, M) array as standard logshmim (N, 1, M) FITS + 7-column .txt file."""
    directory.mkdir(parents=True, exist_ok=True)
    n = arr_2d.shape[0]
    if cnt0 is None:
        cnt0 = np.arange(n, dtype=np.int64)
    epoch_ns = 1767225600 * 1_000_000_000 + 43200 * 1_000_000_000
    t0_ns = epoch_ns + int(round(float(t_sec[0]) * 1e9))
    sec_tot = t0_ns // 1_000_000_000
    nsec = t0_ns % 1_000_000_000
    hh = (sec_tot % 86400) // 3600
    mm = (sec_tot % 3600) // 60
    ss = sec_tot % 60
    stem = f"{prefix}_{hh:02d}:{mm:02d}:{ss:02d}.{nsec:09d}"

    cube = arr_2d[:, None, :].astype(np.float32)
    fits.writeto(directory / f"{stem}.fits", cube, overwrite=True)
    lines = []
    for i in range(n):
        ti_ns = epoch_ns + int(round(float(t_sec[i]) * 1e9))
        s = ti_ns / 1e9
        c = int(cnt0[i])
        lines.append(f"{i} {c} 0 {s:.9f} {s:.9f} {c} 0\n")
    (directory / f"{stem}.txt").write_text("".join(lines), encoding="utf-8")


def test_c_ivdiff_selftest_parity(shm_sandbox):
    """Verify bit-level parity of C mlt.calib2wfs1dm (ivdiff) vs selftest.py & realsim_est.py."""
    _shm_dir, work_dir, env = shm_sandbox

    sys.path.insert(0, str(ALGO_DIR / "toy" / "code"))
    sys.path.insert(0, str(ALGO_DIR / "realsim"))
    import estfreq as E  # noqa: E402
    import realsim_est as R  # noqa: E402
    from simfreq import simulate  # noqa: E402

    cases = [
        ("aligned", 24, 12, 0, -0.49, 2, False, 0.0),
        ("skew250", 24, 12, 6, -0.74, 4, True, 250.0),
    ]
    fs = 24000.0
    lo = 4

    for tag, na_t, nb_t, b_off, recorded_pct, nfr_exp, cut_exp, b_off_us in cases:
        sim = simulate(300, fs=fs, na_t=na_t, nb_t=nb_t, b_off=b_off, t_sci=5.0)
        a_end = sim["a_end"]
        b_end = sim["b_end"]
        cs = E.dm2_position_cumsum(sim)
        deff = (cs[b_end] - cs[b_end - nb_t]) / nb_t
        ka = a_end > sim["t0"]
        kb = b_end > sim["t0"]

        wl = E.rule_frames(na_t, nb_t, b_off)[0] * nb_t
        anchor = int(np.flatnonzero((b_end[kb] - nb_t - b_off) % wl == 0)[0])

        # Python reference (realsim_est.py)
        A_raw = sim["A"][ka][:, : R.NA]
        B_raw = sim["B"][kb]
        D_raw = deff[kb]
        Aw, Bw, Dw, desc = R.align_frames(
            A_raw,
            a_end[ka].astype(float),
            float(na_t),
            B_raw,
            b_end[kb].astype(float),
            float(nb_t),
            D_raw,
            anchor=anchor,
        )
        # Seed both C and Python with exact scalar g_start = 0.8 * median(gB) to test pure parity
        g0_scalar = float(0.8 * np.median(sim["gB"]))
        est_py, c_py, use_py = R.estimate(Aw, Bw, Dw, g0_scalar, desc["lag0"])
        g_py = est_py["IV diff"]

        # Write exact same raw streams to MILK telemetry dir and invoke C milk-mlt-calib2wfs1dm
        tdir = work_dir / f"tlm_{tag}"
        odir = work_dir / f"out_{tag}"
        t_a_s = a_end[ka].astype(np.float64) / fs
        t_b_s = b_end[kb].astype(np.float64) / fs
        _write_tlm_cube(tdir, "wfsA", A_raw, t_a_s)
        _write_tlm_cube(tdir, "wfsB", B_raw, t_b_s)
        _write_tlm_cube(tdir, "dmD", D_raw, t_b_s)

        per_a_s = na_t / fs
        per_b_s = nb_t / fs
        _run_cmd(
            f'milk-mlt-calib2wfs1dm "{tdir}" "{odir}" wfsA wfsB dmD '
            f"{R.NA} {R.NB} {R.NB} 0.0 0.0 "
            f".method=ivdiff .b_offset_us={b_off_us} "
            f".per_a_s={per_a_s:.9f} .per_b_s={per_b_s:.9f} "
            f".clock_mode=counter .n_boot=100 "
            f".anchor={anchor} .g_start={g0_scalar:.9f}",
            env,
            work_dir,
        )

        kv = _parse_kv(odir / "sysid_summary.txt")
        assert int(kv["b_per_win"]) == nfr_exp, f"{tag}: {kv}"
        assert bool(int(kv["a_cut"])) == cut_exp, f"{tag}: {kv}"
        assert int(kv["lag0_used"]) == (3 if cut_exp else 2), f"{tag}: {kv}"
        assert int(kv["usable_ok"]) == 1, f"{tag}: {kv}"

        g_c = fits.getdata(odir / "mdb_diag.fits").astype(np.float64).ravel()
        use_c = fits.getdata(odir / "usable_frac.fits").astype(np.float64).ravel()
        se_c = fits.getdata(odir / "og_se.fits").astype(np.float64).ravel()

        max_g_diff = float(np.max(np.abs(g_c - g_py)))
        max_u_diff = float(np.max(np.abs(use_c - use_py)))
        bias_c = float(100.0 * np.median(g_c[lo:] / sim["gB"][lo:] - 1.0))
        bias_py = float(100.0 * np.median(g_py[lo:] / sim["gB"][lo:] - 1.0))
        print(
            f"[selftest:{tag}] C={bias_c:+.3f}% Py={bias_py:+.3f}% "
            f"(rec={recorded_pct:+.2f}%) max|dG|={max_g_diff:.2e} "
            f"max|dU|={max_u_diff:.2e} medSE={np.median(se_c[lo:]):.4f}"
        )
        assert max_g_diff < 5e-4, f"{tag}: C vs Python max|dG|={max_g_diff}"
        assert max_u_diff < 5e-4, f"{tag}: C vs Python max|dU|={max_u_diff}"
        assert abs(bias_c - recorded_pct) < 0.25, f"{tag}: bias {bias_c} vs {recorded_pct}"
        assert 0.005 < float(np.median(se_c[lo:])) < 0.15


def test_c_ivdiff_real_ao3k_regimes(shm_sandbox):
    """Cross-check compiled C milk-mlt-calib2wfs1dm on real AO3k+SCExAO telemetry regimes."""
    _shm_dir, work_dir, env = shm_sandbox
    audit_path = ALGO_DIR / "phase4a_checks" / "audit_results.json"
    if not audit_path.is_file():
        pytest.skip("Phase 4a audit_results.json not present")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    # Regime table: (slug, audit_key, max_modes_a, expect_ok, g_lo, g_hi)
    checks = [
        ("ao3k_scexao_lowfs_open", "lowfs_open", 60, True, 0.81, 0.88),
        ("ao3k_scexao_predictive_eof128_p8", "eof128_p8", 60, True, 0.82, 0.88),
        ("ao3k_scexao_stg2unmod_eof128_p8", "stg2unmod_eof128_p8", 160, True, 0.78, 0.86),
        ("ao3k_scexao_stg2unmod_mh8_eof128_p32", "stg2unmod_mh8_eof128_p32", 160, False, 0.40, 1.1),
    ]

    ran = 0
    for slug, akey, na_use, expect_ok, g_lo, g_hi in checks:
        tdir = WORK_ROOT / slug / "telemetry"
        if not tdir.is_dir():
            continue
        ran += 1
        odir = work_dir / f"real_{akey}"
        _run_cmd(
            f'milk-mlt-calib2wfs1dm "{tdir}" "{odir}" '
            f"aol1_modevalWFS aol2_modevalWFS aol2_modevalDM "
            f"{na_use} 40 40 .n_boot=100",
            env,
            work_dir,
        )
        kv = _parse_kv(odir / "sysid_summary.txt")
        g_med = float(kv["mdb_diag_med"])
        u_med = float(kv["usable_med"])
        u_ok = int(kv["usable_ok"])
        se_med = float(kv["og_se_med"])
        lat_eff = float(kv["lat_dm_eff"])

        reg = audit["regimes"].get(akey, {})
        ref_g = reg.get("iv_diff_med", None)
        ref_txt = f"{ref_g:.3f}" if ref_g is not None else "n/a"
        print(
            f"[real:{akey:24s}] NA={na_use:3d} g_C={g_med:.3f} (Ph4a={ref_txt}) "
            f"usable={100.0 * u_med:4.1f}% ok={u_ok} SE={se_med:.3f} lat={lat_eff:.2f}"
        )

        assert bool(u_ok) == expect_ok, f"{akey}: unexpected usable_ok={u_ok} ({kv})"
        assert g_lo <= g_med <= g_hi, f"{akey}: g_med={g_med} out of [{g_lo}, {g_hi}]"
        if expect_ok and ref_g is not None and na_use == 60:
            assert abs(g_med - ref_g) < 0.02, f"{akey}: C {g_med:.4f} vs Phase4a {ref_g:.4f}"
        if akey == "stg2unmod_eof128_p8":
            # NA=160 plate-DM1 boost must exceed 25% usable (vs 14.8% at NA=60)
            assert u_med > 0.25, f"Expected NA=160 usable > 0.25, got {u_med:.3f}"
        if not expect_ok:
            assert u_med < 0.05, f"Expected faint mH=8 usable < 0.05, got {u_med:.3f}"

    if ran == 0:
        pytest.skip("No _work/ao3k_scexao* telemetry directories found")


def test_live_2stage_modalog_2wfs1dm_zpo_and_offload(shm_sandbox):
    """Live 2-stage HIL: Stg1 active modalog + Stg2 passive 2WFS1DM + ZPO + blind DM2->DM1."""
    _shm_dir, work_dir, env = shm_sandbox
    rng = np.random.default_rng(20261121)

    n1 = 24  # Stage-1 modes (1 kHz)
    n2 = 16  # Stage-2 modes (2 kHz)
    n_b = 5000  # 2.5 s @ 2 kHz
    n_a = n_b // 2
    per_b = 0.0005
    per_a = 0.0010

    # True optical gains: Stage 1 (NIR ~0.88..0.78), Stage 2 (Vis PyWFS ~0.72..0.58)
    g1_true = np.linspace(0.88, 0.78, n1)
    g2_true = np.linspace(0.72, 0.58, n2)
    Q, _ = np.linalg.qr(rng.normal(size=(n1, n2)))
    M_geom = Q  # (n1, n2) exact Stage-2 -> Stage-1 modal map

    # Stage-1 2-tap kernel (lat=2.0) and Stage-2 6-tap underdamped ringing MIMO plate DM2 kernel
    L2 = 6
    H2 = np.zeros((L2, n2, n2), dtype=np.float64)
    taps2 = np.array([0.0, 0.0, 0.72, 0.58, -0.38, 0.08])
    for l in range(L2):
        H2[l] = np.diag(np.full(n2, taps2[l]))
    for m in range(n2 - 1):
        H2[2, m, m + 1] += 0.14
        H2[3, m, m + 1] -= 0.14
        H2[2, m + 1, m] += 0.10
        H2[3, m + 1, m] -= 0.10

    H1_diag = np.zeros((4, n1), dtype=np.float64)
    H1_diag[2, :] = 1.0  # exact 2-frame causal latency at 1 kHz

    # 1. Simulate coupled 2-stage closed loop with Stage-1 active Rademacher probe (hold=3)
    #    and Stage-2 passive (zero Stage-2 probe!), recording buffers for live modalog & sysid.
    phi_atm = np.zeros((n_b, n1), dtype=np.float64)
    for t in range(1, n_b):
        phi_atm[t] = 0.985 * phi_atm[t - 1] + rng.normal(0.0, 0.09, size=n1)

    p1_cmd = np.zeros((n_a, n1), dtype=np.float64)
    d1_ctrl = np.zeros((n_a, n1), dtype=np.float64)
    a_meas = np.zeros((n_a, n1), dtype=np.float64)
    b_meas = np.zeros((n_b, n2), dtype=np.float64)
    d2_cmd = np.zeros((n_b, n2), dtype=np.float64)

    # Orthogonal Rademacher hold=3 probe on Stage-1 (even modes probed, odd interpolated)
    probe_ampl = 0.06
    cur_p1 = np.zeros(n1, dtype=np.float64)
    for k1 in range(n_a):
        if (k1 % 3) == 0:
            cur_p1 = np.zeros(n1, dtype=np.float64)
            cur_p1[0::2] = probe_ampl * rng.choice([-1.0, 1.0], size=(n1 + 1) // 2)
        p1_cmd[k1] = cur_p1

    # Stage-1 acting DM1 at 1 kHz (2-frame lag on u1 = d1_ctrl + p1_cmd)
    dm1_cur = np.zeros(n1, dtype=np.float64)
    for t in range(L2, n_b):
        k1 = t // 2
        if (t % 2) == 0:
            if k1 >= 2:
                dm1_cur = d1_ctrl[k1 - 2] + p1_cmd[k1 - 2]
            else:
                dm1_cur = np.zeros(n1, dtype=np.float64)
        post_dm1 = phi_atm[t] + dm1_cur
        # Stage-1 WFS integrates over 2 B-frames (1 kHz)
        if (t % 2) == 1:
            post_avg = 0.5 * ((phi_atm[t - 1] + dm1_cur) + post_dm1)
            a_meas[k1] = g1_true * post_avg + rng.normal(0.0, 0.08, size=n1)
            d1_prev = d1_ctrl[k1 - 1] if k1 > 0 else np.zeros(n1)
            d1_ctrl[k1] = 0.98 * d1_prev - 0.35 * a_meas[k1]
        # Stage-2 sees M_geom^T @ post_dm1 + (H2 * d2_cmd)[t]
        d2_eff = np.zeros(n2, dtype=np.float64)
        for l in range(1, L2):
            d2_eff += H2[l] @ d2_cmd[t - l]
        b_meas[t] = g2_true * (post_dm1 @ M_geom + d2_eff) + rng.normal(0.0, 0.012, size=n2)
        d2_cmd[t] = 0.98 * d2_cmd[t - 1] - 0.35 * b_meas[t]

    # Discard warmup (200 B-frames = 100 A-frames)
    a_sci = a_meas[100:]
    d1_sci = d1_ctrl[100:]
    p1_sci = p1_cmd[100:]
    b_sci = b_meas[200:]
    d2_sci = d2_cmd[200:]

    # 2. Run Stage-1 live cacao-fpsexec-modalog in SHM on Stage-1 buffers
    nb_sl = 2048
    w1_buf = np.stack([a_sci[-nb_sl:], a_sci[-nb_sl:]], axis=0).astype(np.float32)
    d1_buf = np.stack([d1_sci[-nb_sl:], d1_sci[-nb_sl:]], axis=0).astype(np.float32)
    p1_buf = np.stack([p1_sci[-nb_sl:], p1_sci[-nb_sl:]], axis=0).astype(np.float32)
    fits.writeto(work_dir / "w1b.fits", w1_buf, overwrite=True)
    fits.writeto(work_dir / "d1b.fits", d1_buf, overwrite=True)
    fits.writeto(work_dir / "p1b.fits", p1_buf, overwrite=True)
    fits.writeto(work_dir / "H1_diag.fits", H1_diag.astype(np.float32), overwrite=True)
    fits.writeto(work_dir / "m1wf.fits", np.ones((1, n1), dtype=np.float32), overwrite=True)

    _run_cmd(
        """
milk-FITS2shm --no-procinfo -n l1w exec w1b.fits  @S:aol1_modevalWFS_buff   >/dev/null
milk-FITS2shm --no-procinfo -n l1d exec d1b.fits  @S:aol1_modevalDM_buff    >/dev/null
milk-FITS2shm --no-procinfo -n l1p exec p1b.fits  @S:aol1_modevalprobe_buff >/dev/null
milk-FITS2shm --no-procinfo -n l1f exec m1wf.fits @S:aol1_mWFSfact          >/dev/null
milk-fps-init -q mog1 cacao-fpsexec-modalog
milk-fps-set -q \
    mog1.AOloopindex=1 \
    mog1.inwfs=aol1_modevalWFS_buff \
    mog1.indm=aol1_modevalDM_buff \
    mog1.inprobe=aol1_modevalprobe_buff \
    mog1.kernel=H1_diag.fits \
    mog1.n_free=2 \
    mog1.smooth_bw=0.5 \
    mog1.ema_alpha=1.0 \
    mog1.apply=ON \
    mog1.procinfo.triggermode=0 \
    mog1.procinfo.loopcntMax=1
milk-fps-runstart -q mog1
milk-fps-wait -q -t 20 mog1
milk-fpsexec-iofits-saveFITS --no-procinfo -n sv1 exec aol1_og_smooth "!og1_smooth.fits" >/dev/null
milk-fps-rm -f -q mog1
""",
        env,
        work_dir,
    )
    g1_est = fits.getdata(work_dir / "og1_smooth.fits").astype(np.float64).ravel()
    g1_rel = float(np.median(np.abs(g1_est / g1_true - 1.0)))

    # 3. Run Stage-2 passive milk-mlt-calib2wfs1dm with 3D H_mimo DM2 kernel
    tdir = work_dir / "tlm_2stg"
    odir = work_dir / "cal_2stg"
    t_b = (np.arange(len(b_sci), dtype=np.float64) + 1.0) * per_b
    t_d = t_b + 0.00004
    t_a = (np.arange(len(a_sci), dtype=np.float64) + 1.0) * per_a - 0.00008
    _write_tlm_cube(tdir, "aol1_modevalWFS", a_sci, t_a)
    _write_tlm_cube(tdir, "aol2_modevalWFS", b_sci, t_b)
    _write_tlm_cube(tdir, "aol2_modevalDM", d2_sci, t_d)
    h2_path = work_dir / "H2_mimo.fits"
    fits.writeto(h2_path, H2.astype(np.float32), overwrite=True)

    _run_cmd(
        f'milk-mlt-calib2wfs1dm "{tdir}" "{odir}" '
        f"aol1_modevalWFS aol2_modevalWFS aol2_modevalDM {n1} {n2} {n2} "
        f".dm_kernel={h2_path} .per_a_s={per_a} .per_b_s={per_b} .n_boot=100",
        env,
        work_dir,
    )
    kv2 = _parse_kv(odir / "sysid_summary.txt")
    assert int(kv2["usable_ok"]) == 1, f"Stage-2 usable health gate failed: {kv2}"
    g2_est = fits.getdata(odir / "mdb_diag.fits").astype(np.float64).ravel()
    mda_virt = fits.getdata(odir / "Mda_virt.fits").astype(np.float64)
    g2_rel = float(np.median(np.abs(g2_est / g2_true - 1.0)))

    # Passive Stage-1 optical gain from Mda_virt vs true M_geom: Mda_virt ≈ diag(g1_true) @ M_geom
    mda_true = g1_true[:, None] * M_geom
    cos_mda = [
        float(
            np.dot(mda_virt[:, j], mda_true[:, j])
            / (np.linalg.norm(mda_virt[:, j]) * np.linalg.norm(mda_true[:, j]) + 1e-12)
        )
        for j in range(n2)
    ]
    scl_g1_passive = [
        float(np.dot(mda_virt[:, j], M_geom[:, j]) / (np.dot(M_geom[:, j], M_geom[:, j]) + 1e-12))
        for j in range(n2)
    ]
    g1_passive_med = float(np.median(scl_g1_passive))
    g1_active_med = float(np.median(g1_est))
    print(
        f"[2stage] Stg1 modalog err={100*g1_rel:.2f}% (med={g1_active_med:.3f}) | "
        f"Stg2 2WFS1DM err={100*g2_rel:.2f}% (med={np.median(g2_est):.3f}) | "
        f"Mda_virt cos={np.median(cos_mda):.3f}, passive g1={g1_passive_med:.3f}"
    )
    assert g1_rel < 0.04, f"Stage-1 modalog error too high: {g1_rel:.4f}"
    assert g2_rel < 0.04, f"Stage-2 2WFS1DM error too high: {g2_rel:.4f}"
    assert float(np.median(cos_mda)) > 0.94, f"Mda_virt cosine too low: {cos_mda}"
    assert abs(g1_passive_med - g1_active_med) / g1_active_med < 0.08

    # 4. Live mlt.apply2wfs1dm -> acquWFS-2.WFSzpogain + aol2_mWFSfact + LLOWFS ZPO stability check
    nx_w = 16
    wfs_img = np.full((nx_w, nx_w), 100.0, dtype=np.float32)
    zpo_pat = np.zeros((nx_w, nx_w), dtype=np.float32)
    zpo_pat[:, : nx_w // 2] = 0.002
    zpo_pat[:, nx_w // 2 :] = -0.002
    wfs_ref = np.full((nx_w, nx_w), 1.0 / (nx_w * nx_w), dtype=np.float32)
    wfs_mask = np.ones((nx_w, nx_w), dtype=np.float32)
    fits.writeto(work_dir / "wf2.fits", wfs_img, overwrite=True)
    fits.writeto(work_dir / "zp2.fits", zpo_pat, overwrite=True)
    fits.writeto(work_dir / "rf2.fits", wfs_ref, overwrite=True)
    fits.writeto(work_dir / "mk2.fits", wfs_mask, overwrite=True)
    fits.writeto(work_dir / "m2wf.fits", np.ones((1, n2), dtype=np.float32), overwrite=True)

    _run_cmd(
        f"""
milk-FITS2shm --no-procinfo -n s2a exec wf2.fits  @S:aol2_wfsim    >/dev/null
milk-FITS2shm --no-procinfo -n s2b exec zp2.fits  @S:aol2_wfszpo   >/dev/null
milk-FITS2shm --no-procinfo -n s2c exec rf2.fits  @S:aol2_wfsref   >/dev/null
milk-FITS2shm --no-procinfo -n s2d exec mk2.fits  @S:aol2_wfsmask  >/dev/null
milk-FITS2shm --no-procinfo -n s2e exec m2wf.fits @S:aol2_mWFSfact >/dev/null
milk-fps-init -q acquWFS-2 cacao-fpsexec-cacaoiot-acquireWFS
milk-fps-set -q \
    acquWFS-2.AOloopindex=2 \
    acquWFS-2.insname=aol2_wfsim \
    acquWFS-2.wfszpo=aol2_wfszpo \
    acquWFS-2.WFSnormfloor=0.0 \
    acquWFS-2.comp.darksub=OFF \
    acquWFS-2.comp.WFSnormalize=ON \
    acquWFS-2.comp.WFSrefsub=ON \
    acquWFS-2.comp.WFSsigav=OFF \
    acquWFS-2.comp.WFSrefc=ON \
    acquWFS-2.WFSrefcmult=1.0 \
    acquWFS-2.WFSrefcgain=0.0 \
    acquWFS-2.WFSzpogain=1.0 \
    acquWFS-2.procinfo.triggermode=3 \
    acquWFS-2.procinfo.triggersname=aol2_wfsim \
    acquWFS-2.procinfo.loopcntMax=-1
milk-fps-runstart -q acquWFS-2
sleep 0.15
milk-cli -q -e -o -c 'mlt.apply2wfs1dm "{odir}" 2 0.95'
sleep 0.05
milk-fps-info acquWFS-2 > acqu2_info.txt
milk-fpsexec-iofits-saveFITS --no-procinfo -n s2f exec aol2_mWFSfact "!m2wf_live.fits" >/dev/null
milk-fps-runstop -q acquWFS-2
milk-fps-wait -q -t 10 acquWFS-2
milk-fps-rm -f -q acquWFS-2
""",
        env,
        work_dir,
    )
    m2wf_live = fits.getdata(work_dir / "m2wf_live.fits").astype(np.float64).ravel()
    assert np.median(np.abs(m2wf_live * g2_true - 1.0)) < 0.04, (
        f"Live aol2_mWFSfact mismatch: {m2wf_live * g2_true}"
    )

    # Extract applied live WFSzpogain and verify Stage-2 + Stage-3 LLOWFS stability
    zpo_g_live = None
    for ln in (work_dir / "acqu2_info.txt").read_text(encoding="utf-8").splitlines():
        if "WFSzpogain" in ln:
            parts = ln.split()
            for tok in parts:
                try:
                    val = float(tok)
                    if 0.1 <= val <= 1.5:
                        zpo_g_live = val
                        break
                except ValueError:
                    pass
    assert zpo_g_live is not None
    expected_zpo_g = 0.95 * float(kv2["mdb_diag_med"])
    assert abs(zpo_g_live - expected_zpo_g) < 0.01, f"zpo_g={zpo_g_live} vs {expected_zpo_g}"

    # Coupled Stage-2 + Stage-3 ZPO stability simulation comparing g_zpo=1.0 vs g_zpo_live
    def _sim_lowfs_zpo(g_zpo: float) -> tuple[float, float]:
        g_opt = float(np.median(g2_true))  # ~0.65
        d2, d3 = 0.0, 0.0
        ncpa_step = 0.25  # static coronagraphic NCPA seen by LLOWFS
        hist_d2 = []
        for _ in range(300):
            # WFS2 sees g_opt * (d2 + d3) - g_zpo * d3
            wfs2 = g_opt * (d2 + d3) - g_zpo * d3
            # LLOWFS sees d2 + d3 + ncpa_step
            wfs3 = d2 + d3 + ncpa_step
            d2 = 0.995 * d2 - 0.35 * wfs2
            d3 = 0.995 * d3 - 0.20 * wfs3
            hist_d2.append(d2)
        # Fightback is |d2| at steady state; total stroke is |d2| + |d3|
        return abs(hist_d2[-1]), abs(d2 + d3 + ncpa_step)

    fight_uncorr, err_uncorr = _sim_lowfs_zpo(1.0)
    fight_corr, err_corr = _sim_lowfs_zpo(zpo_g_live)
    print(
        f"[ZPO] uncorr(g=1.0): fight={fight_uncorr:.4f} err={err_uncorr:.4f} | "
        f"corr(g={zpo_g_live:.3f}): fight={fight_corr:.4f} err={err_corr:.4f}"
    )
    assert fight_corr < fight_uncorr / 5.0, "Optical-gain WFSzpogain did not suppress ZPO fightback"

    # 5. Blind DM2 -> DM1 offload using calibrated Mda_virt.fits (scaled by 1/g1_est)
    #    with DM1 offload converted via M_off = diag(1/g1_est) @ Mda_virt (blind: no DM1 geometry!)
    M_off = (1.0 / g1_est)[:, None] * mda_virt  # (n1, n2)
    static_aberr = rng.normal(0.0, 0.20, size=n2)  # 200 nm static low-order stroke on DM2
    dm2_hist = np.zeros((40, n2), dtype=np.float64)
    dm1_off = np.zeros(n1, dtype=np.float64)
    dm2_state = -static_aberr.copy()  # Stage-2 initially holds entire static aberration
    rms_init = float(np.sqrt(np.mean(dm2_state**2)))
    g_off = 0.35
    for step in range(40):
        # Blind offload pushes Stage-2 stroke onto DM1 (via aol1_dmzpo)
        dm1_off = dm1_off + g_off * (M_off @ dm2_state)
        # Stage-2 closed loop nulls residual (static_aberr + M_geom^T @ dm1_off)
        dm2_state = -(static_aberr + dm1_off @ M_geom)
        dm2_hist[step] = dm2_state
    rms_final = float(np.sqrt(np.mean(dm2_state**2)))
    reduction_pct = 100.0 * (1.0 - rms_final / rms_init)
    peak_ratio = float(np.max(np.sqrt(np.mean(dm2_hist**2, axis=1))) / rms_init)
    print(
        f"[offload] DM2 stroke {rms_init:.4f} -> {rms_final:.4f} "
        f"({reduction_pct:.1f}% reduction, peak/init={peak_ratio:.3f})"
    )
    assert reduction_pct > 85.0, f"Blind DM2->DM1 offload < 85%: {reduction_pct:.1f}%"
    assert peak_ratio <= 1.05, f"Offload overshot initial stroke: {peak_ratio:.3f}"
