#!/usr/bin/env python3
"""Global vs sliding-window vs regime-indexed vs state-proximity EOF on synthetic telemetry."""
import os
import subprocess
import sys
import time

import numpy as np

S = os.path.dirname(os.path.abspath(__file__))
P = 8
LI, LA = 2, 0.4  # 2.4-frame latency
REGS = [1e-6, 1e-5, 1e-4, 1e-3, 1e-2]


def load(name, noise_frac, seed=11):
    d = np.load(os.path.join(S, name))
    a_true = d["a_true"]
    lab = d["lab"]
    n_t = a_true.shape[0]
    idx = np.arange(P - 1, n_t - LI - 2)
    fut = (1 - LA) * a_true[idx + LI] + LA * a_true[idx + LI + 1]
    zoh_mode = np.mean((fut - a_true[idx]) ** 2, axis=0)
    sig2 = noise_frac * float(np.median(zoh_mode))
    rng = np.random.default_rng(seed)
    a = a_true + np.sqrt(sig2) * rng.standard_normal(a_true.shape)
    x = np.hstack([a[idx - k] for k in range(P)])
    y = (1 - LA) * a[idx + LI] + LA * a[idx + LI + 1]
    return d, a_true, a, lab, idx, x, y, fut, sig2, zoh_mode


def ridge(g, r, reg):
    d_f = g.shape[0]
    lam = reg * float(np.trace(g)) / d_f
    return np.linalg.solve(g + lam * np.eye(d_f), r)


def res(yh, yt):
    return float(np.sum(np.mean((yh - yt) ** 2, axis=0)))


def best_reg(g, r, x_te, yt_te, regs=REGS):
    out = []
    for reg in regs:
        w = ridge(g, r, reg)
        out.append((res(x_te @ w, yt_te), reg, w))
    return min(out, key=lambda q: q[0])


def wind_descriptor(a, dx_op, dy_op, wz, n_fit, s=4):
    u = np.zeros_like(a)
    ab = np.zeros_like(a)
    u[s:] = a[s:] - a[:-s]
    ab[s:] = 0.5 * (a[s:] + a[:-s])
    gx = ab @ dx_op.T
    gy = ab @ dy_op.T
    w = 1.0 / np.var(u[s:n_fit], axis=0)

    def tsum(q):
        c = np.cumsum(q)
        out = c.copy()
        out[wz:] = c[wz:] - c[:-wz]
        return out

    axx, axy, ayy = tsum(np.sum(w * gx * gx, 1)), tsum(np.sum(w * gx * gy, 1)), tsum(
        np.sum(w * gy * gy, 1)
    )
    bx, by = tsum(np.sum(w * gx * u, 1)), tsum(np.sum(w * gy * u, 1))
    det = axx * ayy - axy**2
    det[det <= 0] = np.inf
    vx = -(ayy * bx - axy * by) / det / s
    vy = -(axx * by - axy * bx) / det / s
    return np.column_stack([vx, vy])


def gric_anchors(z, rlim, tag):
    """Fixed-radius leader clustering of a descriptor stream with the real gric-cluster."""
    wd = os.path.join(S, f"gric_{tag}")
    os.makedirs(wd, exist_ok=True)
    np.savetxt(os.path.join(wd, "z.txt"), z, fmt="%.6f")
    for f in ("z.txt.gricprof",):
        fp = os.path.join(wd, f)
        if os.path.exists(fp):
            os.remove(fp)
    out = subprocess.run(
        ["gric-cluster", f"{rlim}", "z.txt", "-outdir", "out"], cwd=wd, capture_output=True,
        text=True, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stdout[-400:] + out.stderr[-400:])
    txt = subprocess.run(
        ["gric-bin2ascii", "out/anchors.bin"], cwd=wd, capture_output=True, text=True, check=True
    ).stdout
    rows = [ln.split() for ln in txt.splitlines() if ln.strip() and not ln.startswith("#")]
    arr = np.array(rows, dtype=float)
    return arr[:, -z.shape[1] :]


def leader_anchors(z, rlim):
    anchors = [z[0]]
    for v in z[1:]:
        if np.min(np.linalg.norm(np.array(anchors) - v, axis=1)) > rlim:
            anchors.append(v)
    return np.array(anchors)


def main():
    name = sys.argv[1]
    noise_frac = float(sys.argv[2])
    t_tr = int(float(sys.argv[3]) * 1000)
    wz = int(sys.argv[4]) if len(sys.argv) > 4 else 500
    rlims = [float(q) for q in sys.argv[5].split(",")] if len(sys.argv) > 5 else [1.0]
    t0 = time.time()
    d, a_true, a, lab, idx, x, y, yt, sig2, zoh_mode = load(name, noise_frac)
    n_t, b = a.shape
    d_f = x.shape[1]
    tr = np.where(idx < t_tr - LI - 2)[0]
    te = np.where(idx >= t_tr)[0]
    x_tr, y_tr = x[tr], y[tr]
    x_te, yt_te = x[te], yt[te]
    zoh = res(a[idx[te]], yt_te)
    print(f"T={n_t} B={b} D={d_f} Ntr={tr.size} Nte={te.size} sig2={sig2:.3e} "
          f"lag-only ZOH={np.sum(zoh_mode):.3e} noisy ZOH={zoh:.3e}")

    def show(label, r, extra=""):
        print(f"  {label:<46s} resid/ZOH={r / zoh:6.4f}  VR={100 * (1 - r / zoh):6.2f}%  {extra}")

    # ---- global EOF
    g_all = x_tr.T @ x_tr
    r_all = x_tr.T @ y_tr
    rg, reg_g, w_g = best_reg(g_all, r_all, x_te, yt_te)
    yh_g = x_te @ w_g
    show("global EOF (all training data)", rg, f"reg={reg_g:g}")

    # ---- oracle per-regime EOF
    nreg = int(lab.max()) + 1
    t_tr_rows, t_te_rows = idx[tr], idx[te]
    pure_tr = (lab[t_tr_rows - P + 1] == lab[t_tr_rows + LI + 1])
    yh_o = np.zeros_like(yt_te)
    w_orc = []
    if nreg > 1:
        for reg_o in (1e-5, 1e-4, 1e-3):
            yh_tmp = np.zeros_like(yt_te)
            ws = []
            for k in range(nreg):
                m = pure_tr & (lab[t_tr_rows] == k)
                w_k = ridge(x_tr[m].T @ x_tr[m], x_tr[m].T @ y_tr[m], reg_o)
                ws.append(w_k)
                mt = lab[t_te_rows] == k
                yh_tmp[mt] = x_te[mt] @ w_k
            if not w_orc or res(yh_tmp, yt_te) < res(yh_o, yt_te):
                yh_o, w_orc, reg_best = yh_tmp, ws, reg_o
        show("oracle per-regime EOF (true labels)", res(yh_o, yt_te), f"reg={reg_best:g}")
        cross = np.zeros((nreg, nreg))
        for i in range(nreg):
            mt = lab[t_te_rows] == i
            zi = res(a[t_te_rows[mt]], yt_te[mt])
            for j in range(nreg):
                cross[i, j] = res(x_te[mt] @ w_orc[j], yt_te[mt]) / zi
        print("    resid/ZOH, rows=test regime, cols=filter trained on regime:")
        for i in range(nreg):
            gi = res(yh_g[lab[t_te_rows] == i], yt_te[lab[t_te_rows] == i]) / res(
                a[t_te_rows[lab[t_te_rows] == i]], yt_te[lab[t_te_rows] == i])
            print("     ", np.round(cross[i], 4), f" global={gi:.4f}")

    # ---- sliding-window EOF (as mkEOFPF: window nw, refit every 1 s)
    yh_w = {}
    for nw in (8192, 16384):
        best = None
        for reg_w in (1e-5, 1e-4, 1e-3):
            yh_tmp = np.zeros_like(yt_te)
            for u in range(t_tr, n_t, 1000):
                m = (idx >= u - nw) & (idx < u - LI - 2)
                w_k = ridge(x[m].T @ x[m], x[m].T @ y[m], reg_w)
                mt = (t_te_rows >= u) & (t_te_rows < u + 1000)
                yh_tmp[mt] = x_te[mt] @ w_k
            r_w = res(yh_tmp, yt_te)
            if best is None or r_w < best[0]:
                best = (r_w, reg_w, yh_tmp)
        yh_w[nw] = best[2]
        show(f"sliding-window EOF (N={nw}, refit 1 s)", best[0], f"reg={best[1]:g}")

    if nreg == 1:
        print(f"done {time.time() - t0:.1f}s")
        return

    # ---- regime descriptor (causal modal optical-flow wind estimate) + GRIC clustering
    pxs, fs = float(d["pxs"]), float(d["fs"])
    z = wind_descriptor(a, d["dx_op"], d["dy_op"], wz, t_tr) * pxs * fs  # m/s
    z[: wz + 8] = z[wz + 8]
    print(f"  descriptor window {wz} frames; per-regime mean / std [m/s]:")
    for k in range(nreg):
        m = (lab[:t_tr] == k)
        m[: wz + 8] = False
        print(f"     regime {k}: mean=({z[:t_tr][m, 0].mean():6.2f},{z[:t_tr][m, 1].mean():6.2f}) "
              f"std=({z[:t_tr][m, 0].std():5.2f},{z[:t_tr][m, 1].std():5.2f})")

    sw = np.flatnonzero(np.diff(lab) != 0) + 1
    last_sw = np.zeros(n_t, dtype=np.int64)
    last_sw[sw] = sw
    last_sw = np.maximum.accumulate(last_sw)
    tsw = (np.arange(n_t) - last_sw)[t_te_rows] / fs
    tsw[last_sw[t_te_rows] == 0] = 99.0
    bins = [(0, 0.5), (0.5, 1), (1, 2), (2, 4), (4, 8), (8, 100)]

    def by_tsw(yh):
        out = []
        for lo, hi in bins:
            m = (tsw >= lo) & (tsw < hi)
            out.append(res(yh[m], yt_te[m]) / res(a[t_te_rows[m]], yt_te[m]))
        return out

    results = {"global": yh_g, "oracle regime": yh_o, "slide 8192": yh_w[8192],
               "slide 16384": yh_w[16384]}

    for rlim in rlims:
        zs = z[wz + 8 : t_tr : 20]
        try:
            anchors = gric_anchors(zs, rlim, f"r{rlim}")
            src = "gric-cluster"
        except Exception as exc:  # noqa: BLE001
            print("   gric-cluster failed, using numpy leader clustering:", str(exc)[:200])
            anchors = leader_anchors(zs, rlim)
            src = "numpy-leader"
        la_n = leader_anchors(zs, rlim)
        dist = np.linalg.norm(z[:, None, :] - anchors[None, :, :], axis=2)
        cid = np.argmin(dist, axis=1)
        dmin = dist[np.arange(n_t), cid]
        k_n = anchors.shape[0]
        c_tr, c_te = cid[t_tr_rows], cid[t_te_rows]
        cnt = np.bincount(c_tr, minlength=k_n)
        purity = np.mean([np.bincount(lab[t_tr_rows][c_tr == k], minlength=nreg).max()
                          for k in range(k_n) for _ in range(cnt[k])]) if k_n > 1 else 0.0
        print(f"  rlim={rlim} m/s -> K={k_n} clusters ({src}; numpy leader K={la_n.shape[0]}) "
              f"counts={cnt.tolist()} regime purity={purity:.3f} "
              f"test frames beyond rlim={np.mean(dmin[t_te_rows] > rlim):.3f}")
        g_k, r_k = [], []
        for k in range(k_n):
            m = c_tr == k
            g_k.append(x_tr[m].T @ x_tr[m])
            r_k.append(x_tr[m].T @ y_tr[m])
        for kappa in (0.0, 0.03, 0.1, 0.3):
            best = None
            for reg_c in (1e-5, 1e-4, 1e-3):
                yh_tmp = np.zeros_like(yt_te)
                ws = []
                for k in range(k_n):
                    w_k = ridge(g_k[k] + kappa * (g_all - g_k[k]),
                                r_k[k] + kappa * (r_all - r_k[k]), reg_c)
                    ws.append(w_k)
                    mt = c_te == k
                    yh_tmp[mt] = x_te[mt] @ w_k
                r_c = res(yh_tmp, yt_te)
                if best is None or r_c < best[0]:
                    best = (r_c, reg_c, yh_tmp, ws)
            show(f"regime-cluster EOF rlim={rlim} K={k_n} kappa={kappa}", best[0],
                 f"reg={best[1]:g}")
            results[f"cluster r{rlim} k{kappa}"] = best[2]
            if kappa == 0.1:
                # error-gated selection among the cluster filters + global (causal)
                yh_all = np.stack([x_te @ w_k for w_k in best[3]] + [yh_g])
                y_te_noisy = y[te]
                e = np.sum((yh_all - y_te_noisy[None]) ** 2, axis=2)
                for we in (100, 500):
                    c = np.cumsum(e, axis=1)
                    tm = c.copy()
                    tm[:, we:] = c[:, we:] - c[:, :-we]
                    lagr = LI + 2
                    sel = np.zeros(te.size, dtype=np.int64)
                    sel[lagr:] = np.argmin(tm[:, :-lagr], axis=0)
                    sel[: lagr + we] = yh_all.shape[0] - 1
                    yh_e = yh_all[sel, np.arange(te.size)]
                    show(f"  error-gated among K+1 filters (window {we})", res(yh_e, yt_te))
                    results[f"errgate r{rlim} w{we}"] = yh_e

    print("  resid/ZOH vs time since last wind switch [s]: " + "  ".join(
        f"{lo}-{hi}" for lo, hi in bins) + f"   (frames: "
        + ",".join(str(int(np.sum((tsw >= lo) & (tsw < hi)))) for lo, hi in bins) + ")")
    for key, yh in results.items():
        print(f"     {key:<24s} " + "  ".join(f"{v:6.4f}" for v in by_tsw(yh)))
    print(f"done {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
