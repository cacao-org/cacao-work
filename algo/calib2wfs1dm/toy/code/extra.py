"""Supplementary checks: (a) est_pem sanity on open-loop data, (b) dither with a whitened IV,
(d) held-out R^2 of the tool solution vs the truth-constrained fit, and the lag scan,
(e) frequency-local estimate conditional on the A-predicted disturbance (the practical
diagnostic)."""
import json
import numpy as np
from multiprocessing import Pool
from sim import simulate
import estimators as E
from theory1 import K_of, FR, NPS

REF = dict(sig_nA=0.002, sig_nB=0.002, c_hi=0.6)
LO = 4

def pem_sanity():
    rng = np.random.default_rng(0)
    N = 5000
    A = rng.standard_normal((N, 6)); D = rng.standard_normal((N, 3))
    for t in range(1, N):
        A[t] += 0.9 * A[t - 1]; D[t] += 0.8 * D[t - 1]
    Mab = rng.standard_normal((3, 6)); Mdb = np.diag([0.7, 0.6, 0.8])
    e = rng.standard_normal((N, 3))
    for t in range(1, N):
        e[t] += 0.95 * e[t - 1]
    B = A @ Mab.T + D @ Mdb.T + 3.0 * e
    o = E.est_ols(A, B, D)["Mdb"]; p = E.est_pem(A, B, D, order=4, iters=4, ra=1e-9, rd=1e-9)["Mdb"]
    return dict(ols_err=float(np.abs(np.diag(o) - np.diag(Mdb)).max()),
                pem_err=float(np.abs(np.diag(p) - np.diag(Mdb)).max()))

def dither_run(args):
    seed, kw, t_use = args
    sim = simulate(seed, **kw); g = sim["gB"]
    Ae, Be, De, Ze = E.sync_exact(sim, extra=[np.roll(sim["Dith"], 3, axis=0)])
    if t_use:
        n = int(t_use * 1000); Be, De, Ze = Be[:n], De[:n], Ze[:n]
    taps = E.ar_taps(Be - Be.mean(0), 4, 0.02)
    f = lambda x: E.fir_valid(x - x.mean(0), taps)
    gw = E.est_dither(f(Be), f(De), f(Ze)); gp = E.est_dither(Be, De, Ze)
    r = lambda gh: gh[LO:] / g[LO:] - 1
    return dict(w=(np.median(r(gw)) * 100, np.median(np.abs(r(gw))) * 100),
                p=(np.median(r(gp)) * 100, np.median(np.abs(r(gp))) * 100),
                frac=float(np.median(sim["Dith"].var(0)[LO:] / (sim["B"] / g).var(0)[LO:])))

def r2_run(args):
    seed, pred = args
    sim = simulate(seed, predictive=pred, **REF); g = sim["gB"]
    out = {}
    for lab in (-0.5, 0.0, 0.5):
        for ldb in (2.0, 2.5, 3.0):
            A, B, D = E.sync_tool(sim, lab, ldb)
            tl = E.est_tool(A, B, D, ra=0.01, rd=0.001)
            out[f"scan|{lab}|{ldb}"] = (tl["r2w"],
                                        100 * (np.median(np.diag(tl["Mdb"])[LO:] / g[LO:]) - 1))
    A, B, D = E.sync_tool(sim, 0.0, 2.5)
    tl = E.est_tool(A, B, D)
    N = len(A); ntr = int(0.7 * N)
    mu = [x[:ntr].mean(0) for x in (A, B, D)]
    trw = [E.fir_valid(x[:ntr] - m, tl["taps"]) for x, m in zip((A, B, D), mu)]
    tew = [E.fir_valid(x[ntr:] - m, tl["taps"]) for x, m in zip((A, B, D), mu)]
    def heldout(Mdb_fixed):
        Y = trw[1] - trw[2] @ Mdb_fixed.T
        S = trw[0].T @ trw[0]
        Mab = np.linalg.solve(S + tl["ra"] * np.diag(np.diag(S)), trw[0].T @ Y).T
        return E.r2_med(tew[1], tew[0] @ Mab.T + tew[2] @ Mdb_fixed.T)
    Saa, Sdd, Sad, Sba, Sbd = E.covs(trw[0], trw[2], trw[1])
    Mab_t, Mdb_t, _ = E.solve_block(Saa, Sdd, Sad, Sba, Sbd, tl["ra"], tl["rd"])
    out["r2_tool"] = E.r2_med(tew[1], tew[0] @ Mab_t.T + tew[2] @ Mdb_t.T)
    out["r2_truth"] = heldout(np.diag(g))
    out["bias_tool_train"] = 100 * (np.median(np.diag(Mdb_t)[LO:] / g[LO:]) - 1)
    # unwhitened: OLS solution vs truth
    tr = [x[:ntr] - m for x, m in zip((A, B, D), mu)]
    te = [x[ntr:] - m for x, m in zip((A, B, D), mu)]
    Mab_o, Mdb_o, _ = E.solve_block(*E.covs(tr[0], tr[2], tr[1]), 1e-2, 1e-3)
    out["r2raw_ols"] = E.r2_med(te[1], te[0] @ Mab_o.T + te[2] @ Mdb_o.T)
    Y = tr[1] - tr[2] * g[None, :]
    S = tr[0].T @ tr[0]; Mab = np.linalg.solve(S + 1e-2 * np.diag(np.diag(S)), tr[0].T @ Y).T
    out["r2raw_truth"] = E.r2_med(te[1], te[0] @ Mab.T + te[2] * g[None, :])
    out["bias_ols_train"] = 100 * (np.median(np.diag(Mdb_o)[LO:] / g[LO:]) - 1)
    return out

def cond_run(args):
    seed, pred = args
    sim = simulate(seed, predictive=pred, **REF); g = sim["gB"]
    D = np.roll(sim["D"], 3, axis=0)[8:]; B = sim["B"][8:]
    # A value of the enclosing A frame
    psi = np.repeat(sim["A"][:, :40], 2, axis=0)[: len(sim["B"])][8:]
    win = np.hanning(NPS)[:, None]
    acc = {k: 0.0 for k in ("dd", "pp", "bd", "bp", "pd")}
    for s0 in range(0, len(D) - NPS + 1, NPS // 2):
        f = lambda x: np.fft.rfft((x[s0:s0 + NPS] - x[s0:s0 + NPS].mean(0)) * win, axis=0)
        d, b, p_ = f(D), f(B), f(psi)
        acc["dd"] += np.abs(d) ** 2; acc["pp"] += np.abs(p_) ** 2
        acc["bd"] += b * d.conj(); acc["bp"] += b * p_.conj(); acc["pd"] += p_ * d.conj()
    num = (acc["bd"] - acc["bp"] * acc["pd"] / acc["pp"]).real
    den = acc["dd"] - np.abs(acc["pd"]) ** 2 / acc["pp"]
    K = K_of(sim, FR[1:])
    cfb = np.zeros((len(FR), 40))
    cfb[1:] = (-(1 / K).real).T if K.ndim == 2 else (-(1 / K).real)[:, None]
    return dict(gc=num / den / g[None, :], cfb=cfb / g[None, :], coh=1 - den / acc["dd"])

if __name__ == "__main__":
    res = {"pem_sanity": pem_sanity()}
    print("PEM sanity (open loop, AR(1) noise): max |diag err|", res["pem_sanity"])
    with Pool(20) as pool:
        for dn in (0.0005, 0.001, 0.002):
            for pred in (False, True):
                for tu in (None, 1.0, 2.0):
                    if tu and dn != 0.001:
                        continue
                    rs = pool.map(dither_run,
                                  [(100 + s, dict(REF, predictive=pred, dither_nm=dn), tu)
                                   for s in range(16)])
                    w = np.array([r["w"] for r in rs]); p = np.array([r["p"] for r in rs])
                    key = f"dither {dn}|{'pred' if pred else 'int'}|{tu or 5.0}s"
                    res[key] = dict(w_bias=w[:, 0].mean(), w_sd=w[:, 0].std(), w_pm=w[:, 1].mean(),
                                    p_bias=p[:, 0].mean(), p_sd=p[:, 0].std(), p_pm=p[:, 1].mean(),
                                    frac=rs[0]["frac"])
                    print(f"{key:28s} whitened IV: bias {w[:,0].mean():+5.1f}"
                          f" sd {w[:,0].std():4.1f} per-mode {w[:,1].mean():5.1f} | "
                          f"plain IV: bias {p[:,0].mean():+5.1f} sd {p[:,0].std():4.1f}"
                          f" per-mode {p[:,1].mean():5.1f} | frac {rs[0]['frac']:.3f}")
        for pred in (False, True):
            rs = pool.map(r2_run, [(100 + s, pred) for s in range(16)])
            m = {k: np.mean([r[k] for r in rs], 0) for k in rs[0]}
            tag = "pred" if pred else "int"
            res[f"r2|{tag}"] = {k: (v.tolist() if hasattr(v, "tolist") else float(v))
                                for k, v in m.items()}
            print(f"== {tag}: held-out whitened R2: tool solution {m['r2_tool']:.4f}"
                  f" (bias {m['bias_tool_train']:+.1f}%) vs truth-constrained"
                  f" {m['r2_truth']:.4f}")
            print(f"       held-out raw R2:      OLS solution  {m['r2raw_ols']:.4f}"
                  f" (bias {m['bias_ols_train']:+.1f}%) vs truth-constrained"
                  f" {m['r2raw_truth']:.4f}")
            print("       lag scan (R2_w, bias%):  " + "  ".join(
                f"ab={k.split('|')[1]},db={k.split('|')[2]}: {v[0]:.3f},{v[1]:+.0f}"
                for k, v in m.items() if k.startswith("scan")))
            rs = pool.map(cond_run, [(100 + s, pred) for s in range(16)])
            np.savez(f"cond_{tag}.npz", fr=FR, gc=np.mean([r["gc"] for r in rs], 0),
                     cfb=rs[0]["cfb"], coh=np.mean([r["coh"] for r in rs], 0))
    json.dump(res, open("extra.json", "w"), indent=1, default=float)
