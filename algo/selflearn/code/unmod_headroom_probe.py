#!/usr/bin/env python3
"""Offline headroom, GRIC key recurrence, and hierarchical RLS study on AO telemetry.

Evaluates candidate low-dimensional state/condition keys and 2-level hierarchical GRIC +
forgetting RLS payloads (dense vs factorized diag-AR + shared-low-order + bias) on real
cacaosim telemetry (single-stage unmodulated PyWFS scao_pyr, Stage-2 unmodulated PyWFS
exp2/exp3, and wind-switch exp1), using:
  1. Real `gric-knn` -> `gric-dimdensity` (LID) and `gric-cluster` (K(half)/K(full) saturation).
  2. Held-out second-stage headroom on top of global linear predictor, with shifted-pairing
     negative control.
  3. Strictly causal online streaming simulation of Level-0 global RLS + Level-1 GRIC local
     factorized RLS with hierarchical shrinkage toward Level 0.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
from astropy.io import fits

T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def load_stream(tdir: str, prefix: str) -> tuple[np.ndarray, np.ndarray]:
    files = sorted(glob.glob(f"{tdir}/{prefix}_*.fits"))
    if not files:
        raise FileNotFoundError(f"No files matching {tdir}/{prefix}_*.fits")
    vals, times = [], []
    for f in files:
        d = fits.getdata(f)
        vals.append(d.reshape(-1, d.shape[-1]).astype(np.float64))
        txt = f[:-5] + ".txt"
        if os.path.isfile(txt):
            arr = np.atleast_2d(np.loadtxt(txt))
            if arr.shape[1] >= 6:
                times.append(arr[:, [3, 5]])
    val = np.concatenate(vals, axis=0)
    if times:
        tc = np.concatenate(times, axis=0)
        return val, tc
    return val, np.zeros((len(val), 2))


def ridge(X: np.ndarray, Y: np.ndarray, lam: float) -> np.ndarray:
    G = X.T @ X
    tr = float(np.trace(G))
    G[np.diag_indices_from(G)] += lam * max(tr / G.shape[0], 1e-12)
    return np.linalg.solve(G, X.T @ Y)


def oof_ridge(X: np.ndarray, Y: np.ndarray, nfold: int = 5) -> tuple[float, np.ndarray]:
    edges = np.linspace(0, len(X), nfold + 1).astype(int)
    best = None
    for lam in (1e-4, 1e-3, 1e-2, 1e-1, 1.0):
        P = np.empty_like(Y)
        for i in range(nfold):
            m = np.ones(len(X), dtype=bool)
            m[edges[i] : edges[i + 1]] = False
            P[~m] = X[~m] @ ridge(X[m], Y[m], lam)
        sse = float(((Y - P) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, lam, P)
    assert best is not None
    return best[1], best[2]


def build_candidate_keys(
    W: np.ndarray, D: np.ndarray, OL: np.ndarray, t: np.ndarray, ntr: int
) -> dict[str, np.ndarray]:
    """Build low-dimensional candidate keys standardized using training frames only."""
    tr = t < ntr
    nmode = W.shape[1]
    sig_w = np.maximum(W[:ntr].std(axis=0), 1e-12)
    Wz = W / sig_w

    h_e = 8

    def band_log_e(a: int, b: int) -> np.ndarray:
        b = min(b, nmode)
        if b <= a:
            return np.zeros(len(t))
        ef = (Wz[:, a:b] ** 2).mean(axis=1)
        cs = np.concatenate([[0.0], np.cumsum(ef)])
        ew = np.maximum((cs[t + 1] - cs[t + 1 - h_e]) / h_e, 1e-12)
        return np.log(ew)

    e_lo = band_log_e(0, min(10, nmode))
    e_hi = band_log_e(min(10, nmode), min(nmode, 128))
    E2 = np.column_stack([e_lo, e_hi])
    E4 = np.column_stack([
        band_log_e(0, 4),
        band_log_e(4, min(16, nmode)),
        band_log_e(min(16, nmode), min(48, nmode)),
        band_log_e(min(48, nmode), min(128, nmode)),
    ])
    w_rms_tot = np.log(np.maximum((Wz[t, : min(128, nmode)] ** 2).mean(axis=1), 1e-12))[:, None]

    w2 = Wz[t, :2]
    w4 = Wz[t, : min(4, nmode)]
    dw2 = Wz[t, :2] - Wz[t - 2, :2]
    d2 = (D[t, :2] - D[:ntr, :2].mean(0)) / np.maximum(D[:ntr, :2].std(0), 1e-12)

    ol_sig = np.maximum(OL[:ntr, : min(48, nmode)].std(axis=0), 1e-12)
    Oz = OL[:, : min(48, nmode)] / ol_sig
    d1 = ((Oz[1:] - Oz[:-1]) ** 2).mean(axis=1)
    d1 = np.concatenate([[d1[0]], d1])
    cs_d1 = np.concatenate([[0.0], np.cumsum(d1)])
    h_r = 64
    t_clip = np.maximum(t + 1 - h_r, 0)
    vel_rate = np.log(
        np.maximum((cs_d1[t + 1] - cs_d1[t_clip]) / np.maximum(t + 1 - t_clip, 1), 1e-12)
    )[:, None]

    raw_keys = {
        "e1_logE": w_rms_tot,
        "e4_bands": E4,
        "wfs_lo4": w4,
        "tt2_e2": np.column_stack([w2, E2]),
        "tt2_abs_e2": np.column_stack([w2, np.abs(w2), E2]),
        "lo4_e2": np.column_stack([w4, E2]),
        "tt2_dm2_e2": np.column_stack([w2, d2, E2]),
        "tt2_vel_e2": np.column_stack([w2, dw2, E2]),
        "regime_e2_vel": np.column_stack([E2, vel_rate]),
    }

    keys: dict[str, np.ndarray] = {}
    for name, Z in raw_keys.items():
        mu = Z[tr].mean(axis=0)
        sd = np.maximum(Z[tr].std(axis=0), 1e-12)
        keys[name] = (Z - mu) / sd
    return keys


def run_gric_diagnostics(name: str, Z: np.ndarray, rlims: tuple[float, ...]) -> None:
    """Run real gric-knn -> gric-dimdensity (LID) and gric-cluster (K saturation) on key Z."""
    gric_bin = shutil.which("gric-cluster")
    knn_bin = shutil.which("gric-knn")
    dim_bin = shutil.which("gric-dimdensity")
    a2b = shutil.which("gric-ascii2bin")
    b2a = shutil.which("gric-bin2ascii")
    if not gric_bin or not a2b:
        print("  [warn] gric binaries not on PATH; skipping native GRIC check")
        return

    with tempfile.TemporaryDirectory(prefix="gric_sl_") as tmp:
        txt_p = os.path.join(tmp, "key.txt")
        bin_p = os.path.join(tmp, "key.bin")
        np.savetxt(txt_p, Z.astype(np.float64), fmt="%.6f")
        subprocess.run(
            [a2b, txt_p, bin_p], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        lid_str = "n/a"
        if knn_bin and dim_bin:
            knn_dir = os.path.join(tmp, "knn")
            os.makedirs(knn_dir, exist_ok=True)
            k_res = subprocess.run(
                [knn_bin, bin_p, "-k", "20", "-outdir", knn_dir],
                capture_output=True, text=True, check=False,
            )
            dist_bin = os.path.join(knn_dir, "knn_distances.bin")
            if k_res.returncode == 0 and os.path.isfile(dist_bin):
                d_res = subprocess.run(
                    [dim_bin, dist_bin], capture_output=True, text=True, check=False
                )
                for line in d_res.stdout.splitlines():
                    if "Median-Unb" in line:
                        parts = line.split()
                        # Metric: Dim (Median-Unb k-4/3) mean ± std P10 P25 P50 ...
                        m = re.search(r"([0-9.]+)\s*±\s*([0-9.]+)", line)
                        if m:
                            lid_str = f"LID={m.group(1)}±{m.group(2)}"
                        break

        k_parts = []
        n_half = len(Z) // 2
        for rl in rlims:
            od = os.path.join(tmp, f"out_{rl}")
            subprocess.run(
                [gric_bin, f"{rl}", bin_p, "-tm", "0.5", "-outdir", od],
                capture_output=True, text=True, check=False,
            )
            fm_p = os.path.join(od, "frame_membership.bin")
            if os.path.isfile(fm_p) and b2a:
                txt = subprocess.run(
                    [b2a, fm_p], capture_output=True, text=True, check=True
                ).stdout
                cids = [
                    int(float(ln.split()[-1]))
                    for ln in txt.splitlines()
                    if ln.strip() and not ln.startswith("#")
                ]
                if len(cids) >= n_half:
                    k_half = len(set(cids[:n_half]))
                    k_full = len(set(cids))
                    k_parts.append(f"r={rl:.1f}: K={k_half}/{k_full}")
                else:
                    k_parts.append(f"r={rl:.1f}: n={len(cids)}")
            else:
                k_parts.append(f"r={rl:.1f}: missing")
        k_join = "  |  ".join(k_parts)
        print(f"  GRIC [{name:14s}, D={Z.shape[1]:2d}]  {k_join}  |  {lid_str}")


def eval_hierarchical_online(
    Z: np.ndarray,
    W_cur: np.ndarray,
    W_prev: np.ndarray,
    Y: np.ndarray,
    delta: int,
    rlim: float,
    kmax: int = 16,
    q_shared: int = 4,
    lam0: float = 20.0,
    lam1: float = 40.0,
    gamma0: float = 0.999,
    gamma1: float = 0.9995,
    n_warmup: int = 40,
    eval_start: int = 1000,
    enable_level1: bool = True,
) -> tuple[float, float, float, int]:
    """Strictly causal 2-level hierarchical GRIC + factorized per-mode RLS.

    For each target mode m in 0..M-1:
      - Regressor phi_{t,m} = [1, W_cur[t,m], W_prev[t,m], W_cur[t,0..q-1]]  (size p = 3 + q)
      - Level 0 (global online RLS, forgetting gamma0): y0_{t,m} = w0_m^T phi_{t,m}
      - Level 1 (GRIC cluster c = assign(Z[t]), forgetting gamma1, prior lam1 toward 0):
          learns residual e_{s,m} = Y[s,m] - y0_{s,m} via per-cluster factorized RLS:
          dy_{t,m} = gate(d_t <= rlim) * (N_c / (N_c + n_warmup)) * dw_{c,m}^T phi_{t,m}
      - Total prediction: y_hat_{t,m} = y0_{t,m} + dy_{t,m}

    Returns: (total_vr, level1_extra_vr_over_l0, level1_shifted_ctrl_vr, k_used).
    """
    n, d_z = Z.shape
    m_out = Y.shape[1]
    q = min(q_shared, W_cur.shape[1])
    p = 3 + q  # [1, w_m(t), w_m(t-1), w_{0..q-1}(t)]

    # Build per-mode feature tensor Phi[n, m_out, p]
    Phi = np.empty((n, m_out, p), dtype=np.float64)
    Phi[:, :, 0] = 1.0
    Phi[:, :, 1] = W_cur[:, :m_out]
    Phi[:, :, 2] = W_prev[:, :m_out]
    if q > 0:
        Phi[:, :, 3 : 3 + q] = W_cur[:, None, :q]

    # Level-0 global RLS state: P0[m, p, p], w0[m, p]
    P0 = np.broadcast_to((1.0 / lam0) * np.eye(p), (m_out, p, p)).copy()
    w0 = np.zeros((m_out, p), dtype=np.float64)
    n0 = 0.0

    # Level-1 GRIC cluster state
    anchors = np.empty((kmax, d_z), dtype=np.float64)
    k_used = 0
    r2 = rlim * rlim
    P1 = np.empty((kmax, m_out, p, p), dtype=np.float64)
    w1 = np.zeros((kmax, m_out, p), dtype=np.float64)
    n_eff = np.zeros(kmax, dtype=np.float64)

    cids = np.empty(n, dtype=np.int64)
    Y0 = np.zeros((n, m_out), dtype=np.float64)
    dY1 = np.zeros((n, m_out), dtype=np.float64)

    inv_g0 = 1.0 / gamma0
    inv_g1 = 1.0 / gamma1
    eye_p = np.eye(p, dtype=np.float64)

    for t in range(n):
        # 1. Causal delayed update for s = t - delta (whose target Y[s] is now known)
        s = t - delta
        if s >= 0:
            xs = Phi[s]  # [m_out, p]
            # Level-0 prediction error at s using current/causal y0
            # Update Level 0 (vectorized over modes m)
            Px0 = np.einsum("mij,mj->mi", P0, xs)
            den0 = gamma0 + np.einsum("mi,mi->m", xs, Px0)
            kg0 = Px0 / den0[:, None]
            err0 = Y[s] - np.einsum("mi,mi->m", xs, w0)
            w0 += kg0 * err0[:, None]
            P0 = inv_g0 * (P0 - np.einsum("mi,mj->mij", kg0, Px0))
            n0 = gamma0 * n0 + 1.0

            # Update Level 1 on the Level-0 causal residual e_s = Y[s] - Y0[s]
            if enable_level1:
                ck = int(cids[s])
                if 0 <= ck < k_used:
                    e_s = Y[s] - Y0[s]
                    Pk = P1[ck]
                    Px1 = np.einsum("mij,mj->mi", Pk, xs)
                    den1 = gamma1 + np.einsum("mi,mi->m", xs, Px1)
                    kg1 = Px1 / den1[:, None]
                    err1 = e_s - np.einsum("mi,mi->m", xs, w1[ck])
                    w1[ck] += kg1 * err1[:, None]
                    P1[ck] = inv_g1 * (Pk - np.einsum("mi,mj->mij", kg1, Px1))
                    n_eff[ck] = gamma1 * n_eff[ck] + 1.0

        # 2. Assign current key Z[t] causally via GRIC leader rule
        z = Z[t]
        if k_used == 0:
            anchors[0] = z
            P1[0] = (1.0 / lam1) * eye_p
            w1[0].fill(0.0)
            n_eff[0] = 0.0
            ck = 0
            dist = 0.0
            k_used = 1
        else:
            diff = anchors[:k_used] - z
            d2 = (diff * diff).sum(axis=1)
            best = int(np.argmin(d2))
            if d2[best] > r2 and k_used < kmax:
                ck = k_used
                anchors[ck] = z
                P1[ck] = (1.0 / lam1) * eye_p
                w1[ck].fill(0.0)
                n_eff[ck] = 0.0
                dist = 0.0
                k_used += 1
            else:
                ck = best
                dist = float(np.sqrt(d2[best]))
        cids[t] = ck

        # 3. Predict at time t
        xt = Phi[t]
        sh0 = n0 / (n0 + 20.0)
        Y0[t] = sh0 * np.einsum("mi,mi->m", xt, w0)
        if enable_level1 and dist <= rlim and n_eff[ck] >= 1.0:
            sh1 = n_eff[ck] / (n_eff[ck] + float(n_warmup))
            dY1[t] = sh1 * np.einsum("mi,mi->m", xt, w1[ck])

    Ye = Y[eval_start:]
    Y0e = Y0[eval_start:]
    dY1e = dY1[eval_start:]
    E0e = Ye - Y0e
    E0c = np.roll(E0e, 400, axis=0)

    tot_vr = 1.0 - float(((Ye - (Y0e + dY1e)) ** 2).sum()) / float((Ye ** 2).sum())
    l1_vr = 1.0 - float(((E0e - dY1e) ** 2).sum()) / float((E0e ** 2).sum())
    l1_ctrl = 1.0 - float(((E0c - dY1e) ** 2).sum()) / float((E0c ** 2).sum())
    return tot_vr, l1_vr, l1_ctrl, k_used


def analyze_dataset(
    label: str, tdir: str, stage: str, nmodes_block: int = 20, h: int = 8, delta: int = 2
) -> None:
    print(f"\n{'=' * 78}")
    print(f"DATASET: {label} ({stage}, modes 0..{nmodes_block - 1}, h={h}, delta={delta})")
    print(f"{'=' * 78}")
    W, tcW = load_stream(tdir, f"{stage}_modevalWFS")
    D, _ = load_stream(tdir, f"{stage}_modevalDM")
    OL, _ = load_stream(tdir, f"{stage}_modevalOL")
    n = min(len(W), len(D), len(OL))
    W, D, OL = W[:n], D[:n], OL[:n]
    m_blk = min(nmodes_block, W.shape[1])
    drops = int(np.sum(np.diff(tcW[:n, 1].astype(np.int64)) != 1)) if len(tcW) >= n else -1
    log(
        f"loaded N={n}, M={W.shape[1]}, drops={drops}, "
        f"WFS rms(0..{m_blk - 1})={np.sqrt((W[:, :m_blk] ** 2).mean()):.5f}, "
        f"DM rms={np.sqrt((D[:, :m_blk] ** 2).mean()):.5f}, "
        f"OL rms={np.sqrt((OL[:, :m_blk] ** 2).mean()):.5f}"
    )

    t = np.arange(max(h, 64), n - delta)
    ntr = int(0.55 * n)
    gap = int(0.05 * n)
    tr = t < ntr
    te = t >= ntr + gap
    eval_start = int(np.searchsorted(t, ntr + gap))
    idx = np.arange(m_blk)

    keys = build_candidate_keys(W, D, OL, t, ntr)

    print("\n--- 1. Native GRIC Recurrence (K half/full) & Local Intrinsic Dim (LID) ---")
    for kname in ("e4_bands", "wfs_lo4", "tt2_e2", "tt2_abs_e2", "tt2_dm2_e2", "regime_e2_vel"):
        run_gric_diagnostics(kname, keys[kname], rlims=(1.5, 2.0, 2.5))

    # Standardize W_cur, W_prev using training std for numerical stability
    sd_w = np.maximum(W[t[tr]][:, idx].std(axis=0), 1e-12)
    W_cur = W[t][:, idx] / sd_w
    W_prev = W[t - 1][:, idx] / sd_w
    Y_wfs = W[t + delta][:, idx]
    Y_wfs = Y_wfs - Y_wfs[tr].mean(0)

    # Also test PSOL increment Y_dol = OL[t+delta] - OL[t]
    Y_dol = OL[t + delta][:, idx] - OL[t][:, idx]
    Y_dol = Y_dol - Y_dol[tr].mean(0)
    OL_cur = (OL[t][:, idx] - OL[t - 1][:, idx]) / np.maximum(
        (OL[t[tr]][:, idx] - OL[t[tr] - 1][:, idx]).std(0), 1e-12
    )
    OL_prev = (OL[t - 1][:, idx] - OL[t - 2][:, idx]) / np.maximum(
        (OL[t[tr]][:, idx] - OL[t[tr] - 1][:, idx]).std(0), 1e-12
    )

    # Compare global offline linear vs Hierarchical Level-0 + Level-1 GRIC Factorized RLS
    for tgt_name, Fc, Fp, Yt in (
        ("WFS_future_W[t+d]", W_cur, W_prev, Y_wfs),
        ("PSOL_incr_dOL[t+d]", W_cur, OL_cur, Y_dol),
    ):
        print(f"\n--- 2. Target: {tgt_name} (eval frames={len(t) - eval_start}) ---")
        # Baseline global offline linear ridge on h lags of (W, D)
        X_full = np.hstack(
            [np.hstack([W[t - j][:, idx], D[t - j][:, idx]]) for j in range(h)]
        )
        Xn = (X_full - X_full[tr].mean(0)) / np.maximum(X_full[tr].std(0), 1e-12)
        lam_lin, _ = oof_ridge(Xn[tr], Yt[tr])
        P_lin = Xn[te] @ ridge(Xn[tr], Yt[tr], lam_lin)
        lin_vr = 1.0 - float(((Yt[te] - P_lin) ** 2).sum()) / float((Yt[te] ** 2).sum())
        print(
            f"  Offline global linear (h={h} lags W+D, lam={lam_lin:g}): "
            f"{100 * lin_vr:+6.2f}% var"
        )

        # Level-0 only (causal online factorized RLS, no clustering)
        tot0, _, _, _ = eval_hierarchical_online(
            keys["e1_logE"], Fc, Fp, Yt, delta=delta, rlim=10.0, kmax=1,
            q_shared=4, lam0=20.0, gamma0=0.999, eval_start=eval_start, enable_level1=False,
        )
        print(f"  Causal Level-0 global online factorized RLS (q=4):      {100 * tot0:+6.2f}% var")

        # Level-0 + Level-1 GRIC hierarchical clusters
        for kname, rl in (
            ("e1_logE", 0.8),
            ("e4_bands", 2.0),
            ("wfs_lo4", 2.0),
            ("tt2_e2", 2.0),
            ("tt2_abs_e2", 2.5),
            ("tt2_dm2_e2", 2.5),
            ("regime_e2_vel", 1.5),
        ):
            tot1, l1_vr, l1_ctrl, kk = eval_hierarchical_online(
                keys[kname], Fc, Fp, Yt, delta=delta, rlim=rl, kmax=16,
                q_shared=4, lam0=20.0, lam1=50.0, gamma0=0.999, gamma1=0.9995,
                n_warmup=40, eval_start=eval_start, enable_level1=True,
            )
            print(
                f"    + Level-1 GRIC [{kname:13s}] r={rl:.1f} K={kk:2d}: "
                f"total={100 * tot1:+6.2f}%  L1_over_L0={100 * l1_vr:+6.2f}%  "
                f"(ctrl {100 * l1_ctrl:+6.2f}%)"
            )


def main() -> None:
    runs = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            parts = arg.split(":")
            tdir = parts[0]
            stage = parts[1] if len(parts) > 1 else "aol1"
            delta = int(parts[2]) if len(parts) > 2 else 2
            runs.append((os.path.basename(os.path.dirname(tdir)), tdir, stage, delta))
    else:
        base = "/home/guyon/src/cacao-work/_work"
        p15 = f"{base}/ao3k_phases1to5_bench"
        runs = [
            (
                'scao_pyr unmod PyWFS (mod=0, 0.7")',
                f"{base}/selflearn_scao_unmod0/telemetry",
                "aol1",
                2,
            ),
            ("exp2_unmod_mh6_base Stg2", f"{p15}/exp2_unmod_mh6_base/telemetry", "aol2", 3),
            ("exp1_windsw_base Stg1 (+60 deg)", f"{p15}/exp1_windsw_base/telemetry", "aol1", 3),
        ]
    for label, tdir, stage, delta in runs:
        if os.path.isdir(tdir):
            analyze_dataset(label, tdir, stage, nmodes_block=20, h=8, delta=delta)
        else:
            print(f"[skip] missing {tdir}")


if __name__ == "__main__":
    main()
