"""Monte-Carlo benchmark of Mdb estimators on the known-truth two-stage loop."""
import json, sys, time
import numpy as np
from multiprocessing import Pool
from sim import simulate
import estimators as E

LO = 4  # modes 0..3 are reported separately in the real system; here all modes behave alike

def score(gh, g):
    r = gh[LO:] / g[LO:] - 1.0
    return float(np.median(r) * 100.0), float(np.median(np.abs(r)) * 100.0)

def one(args):
    seed, kw, t_use = args
    sim = simulate(seed, **kw)
    g = sim["gB"]
    out = {}
    A, B, D = E.sync_tool(sim, 0.0, 2.5)
    Ae, Be, De, Ze = E.sync_exact(sim, extra=[np.roll(sim["Dith"], 3, axis=0)])
    if t_use is not None:
        n = int(t_use * 1000)
        A, B, D, Ae, Be, De, Ze = (x[:n] for x in (A, B, D, Ae, Be, De, Ze))
    tl = E.est_tool(A, B, D)
    out["ols"] = score(np.diag(E.est_ols(A, B, D)["Mdb"]), g)
    out["tool_wz"] = score(np.diag(tl["Mdb"]), g)
    tle = E.est_tool(Ae, Be, De)
    out["wz_exact"] = score(np.diag(tle["Mdb"]), g)
    for p_ord in (1, 2, 8):
        out[f"wz_p{p_ord}"] = score(np.diag(E.est_tool(A, B, D, order=p_ord)["Mdb"]), g)
    out["band_exact"] = score(np.diag(E.est_freq_proto(Ae, Be, De)["Mdb"]), g)
    out["band_tool"] = score(np.diag(E.est_freq_proto(A, B, D)["Mdb"]), g)
    for p_ord in (8, 32):
        out[f"pem{p_ord}"] = score(np.diag(E.est_pem(Ae, Be, De, order=p_ord)["Mdb"]), g)
    # A-predicted disturbance direction from the tool's own pseudo-open-loop refit of Mab
    Bol = (Be - Be.mean(0)) - (De - De.mean(0)) @ tle["Mdb"].T
    Ac = Ae - Ae.mean(0)
    Saa = Ac.T @ Ac
    Mab0 = np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), Ac.T @ Bol).T
    past = lambda n: tuple(range(-n, 0))
    for nm, lags, ia in (("iv_past2", past(2), True), ("iv_past4", past(4), True),
                         ("iv_past8", past(8), True), ("iv_past16", past(16), True),
                         ("iv_past32", past(32), True),
                         ("iv_past8_f2", past(8) + (1, 2), True),
                         ("iv_sym8", tuple(l for l in range(-8, 9) if l), True),
                         ("iv_past8_noEIV", past(8), False)):
        iv = E.est_iv_modal(Ae, Be, De, Mab0, lags, ia)
        out[nm] = score(iv["g"], g)
        if nm == "iv_past8":
            out["iv_strength"] = float(np.median(iv["pr2"][LO:]))
            out["iv_c"] = float(np.median(iv["c"][LO:]))
    # same estimator on the tool's (triangle-kernel) alignment, where Mab is not exactly static
    Bol_t = (B - B.mean(0)) - (D - D.mean(0)) @ tl["Mdb"].T
    At = A - A.mean(0)
    Saat = At.T @ At
    Mab0t = np.linalg.solve(Saat + 1e-2 * np.diag(np.diag(Saat)), At.T @ Bol_t).T
    out["iv_past8_toolsync"] = score(E.est_iv_modal(A, B, D, Mab0t, past(8), True)["g"], g)
    if kw.get("dither_nm", 0.0) > 0.0:
        out["dither"] = score(E.est_dither(Be, De, Ze), g)
        out["dither_frac"] = float(np.median(sim["Dith"].var(0)[LO:] / (sim["B"] / g).var(0)[LO:]))
    out["eta_raw"] = float(np.median(tl["eta_raw"]))
    out["eta_w"] = float(np.median(tl["eta"]))
    ac1, cd, r2 = E.ecol_diag(A, B, D, g)
    out["ac1"], out["corr_eD"], out["r2_ol"] = ac1, cd, r2
    out["w_dc_db"] = float(20 * np.log10(abs(tl["taps"].sum())))
    out["resid_rms"] = float(np.median((sim["B"] / g).std(0)[LO:]))
    mda, _ = E.est_mda(Ae, Be, De)
    out["mda_scale"] = float(np.median(np.diag(mda)[LO:] / sim["gA"]))
    return out

def agg(rs):
    o = {}
    for k in rs[0]:
        v = np.array([r[k] for r in rs], dtype=float)
        if v.ndim == 2:
            o[k] = dict(bias=float(v[:, 0].mean()), sd=float(v[:, 0].std()),
                        permode=float(v[:, 1].mean()))
        else:
            o[k] = float(v.mean())
    return o

if __name__ == "__main__":
    nseed = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    base = dict(sig_nA=0.002, sig_nB=0.002, c_hi=0.6)
    conds = {
        "ref": {},
        "noise/2": dict(sig_nA=0.001, sig_nB=0.001),
        "noise x2": dict(sig_nA=0.004, sig_nB=0.004),
        "nB x2 only": dict(sig_nB=0.004),
        "nA x3 only": dict(sig_nA=0.006),
        "unmodelled/2": dict(c_hi=0.3),
        "unmodelled x1.7": dict(c_hi=1.0),
        "no unmodelled": dict(c_hi=0.0, sig_alias=0.0),
        "nA = 0": dict(sig_nA=0.0),
        "nA = 0, no unmodelled": dict(sig_nA=0.0, c_hi=0.0, sig_alias=0.0),
        "A coloured error": dict(sig_vA=0.002),
        "gain2 0.25": dict(gain2=0.25),
        "gain2 0.45": dict(gain2=0.45),
    }
    jobs, keys = [], []
    for cn, ck in conds.items():
        for pred in (False, True):
            kw = dict(base, **ck, predictive=pred)
            for s in range(nseed):
                jobs.append((100 + s, kw, None)); keys.append((cn, "pred" if pred else "int", "5s"))
    for dn in (0.0005, 0.001, 0.002):
        for pred in (False, True):
            kw = dict(base, predictive=pred, dither_nm=dn)
            for s in range(nseed):
                jobs.append((100 + s, kw, None))
                keys.append((f"dither {dn}", "pred" if pred else "int", "5s"))
    for tu in (0.5, 1.0, 2.0):
        for pred in (False, True):
            for dn in (0.0, 0.001):
                kw = dict(base, predictive=pred, dither_nm=dn)
                for s in range(nseed):
                    jobs.append((100 + s, kw, tu))
                    keys.append(("ref" if dn == 0 else f"dither {dn}", "pred" if pred else "int",
                                 f"{tu}s"))
    t0 = time.time()
    with Pool(22) as pool:
        res = pool.map(one, jobs, chunksize=2)
    groups = {}
    for k, r in zip(keys, res):
        groups.setdefault("|".join(k), []).append(r)
    summary = {k: agg(v) for k, v in groups.items()}
    json.dump(summary, open("bench.json", "w"), indent=1)
    print("done in %.0f s, %d runs" % (time.time() - t0, len(jobs)))
