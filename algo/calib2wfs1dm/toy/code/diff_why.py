"""Why first differences? Locate the plain lagged-A 2SLS bias in temporal frequency.

Per mode, the 2SLS error of the DM2 gain is exactly

    g_hat - g = <Dp, e0> / <Dp, Dp>

where Dp is the instrument-predicted DM2 command made orthogonal to the instrument-predicted
psi, and e0 = B - c psi - g D is the structural error: everything in B that is neither the true
DM2 response nor the true contribution of the wavefront that psi stands for. Both inner
products are sums over temporal frequency (Parseval), so each band's share of the identifying
strength (denominator) and its contribution to the error (numerator) can be read off.

Three ways of building psi separate the candidate causes:
  fit     : psi = A Mab0, Mab0 fitted on the same window (the recipe of iv_variants.py)
  oracle  : psi = (gB / gA) A, the true Mab (no preliminary fit at all)
  xfit    : Mab0 fitted on one half of the window and applied to the other half

The script also sweeps the quasi-difference x[t] - rho x[t-1] from rho = 0 (levels) to rho = 1
(first difference), with instruments (2SLS) and without (least squares on the same data).
"""
import json
from multiprocessing import Pool

import numpy as np

import estimators as E
from sim import simulate

LO = 4
FS_A = 1000.0
EDGES = np.array([0.0, 2.0, 10.0, 30.0, 100.0, 250.0, 500.01])
BANDS = ["0-2", "2-10", "10-30", "30-100", "100-250", "250-500"]
COMPS = ("aside", "u", "n", "lag")
KINDS = ("fit", "oracle", "xfit")
# (label, rho, instrument lags)
FORMS = [("levels, lags 1-8", 0.0, range(1, 9)), ("levels, lags 2-9", 0.0, range(2, 10))]
FORMS += [(f"rho={r:g}", r, range(2, 10)) for r in (0.5, 0.8, 0.9, 0.95, 0.98, 0.99)]
FORMS += [("first difference", 1.0, range(2, 10))]
SHOW = ("levels, lags 1-8", "first difference")
CASES = [("reference, 5 s, int", 0.002, 5.0, False), ("noises /4, 5 s, int", 0.0005, 5.0, False),
         ("noises /4, 5 s, pred", 0.0005, 5.0, True), ("noises /4, 20 s, int", 0.0005, 20.0, False)]
NSEED = 12


def band_sums(a, b):
    """Split sum_t a[t] b[t] into the frequency bands EDGES (exact, by Parseval)."""
    n = len(a)
    fa, fb = np.fft.rfft(a), np.fft.rfft(b)
    w = np.full(len(fa), 2.0)
    w[0] = 1.0
    if n % 2 == 0:
        w[-1] = 1.0
    prod = w * (fa * np.conj(fb)).real / n
    f = np.fft.rfftfreq(n, d=1.0 / FS_A)
    return np.array([prod[(f >= a0) & (f < a1)].sum() for a0, a1 in zip(EDGES[:-1], EDGES[1:])])


def cen(x):
    return x - x.mean(0)


def ridge_w(A, Y):
    Saa = A.T @ A
    return np.linalg.solve(Saa + 1e-2 * np.diag(np.diag(Saa)), A.T @ Y)


def filt(x, rho):
    return x if rho == 0.0 else x[1:] - rho * x[:-1]


def analyse(Bc, Dc, psi, cstar, comp, g, rho, lags):
    """2SLS per mode, plus the exact band and component split of its error."""
    y_a, p_a, d_a = filt(Bc, rho), filt(psi, rho), filt(Dc, rho)
    c_a = {k: filt(v, rho) for k, v in comp.items()}
    t = np.arange(10, len(y_a))
    nb = len(BANDS)
    r_iv, r_ols, use = [], [], []
    s_den, s_num, s_psi, s_d = (np.zeros(nb) for _ in range(4))
    s_cmp = {k: np.zeros(nb) for k in COMPS}
    for i in range(LO, 40):
        Z = np.column_stack([p_a[t - l, i] for l in lags])
        Q, _ = np.linalg.qr(Z)
        ps, d, y = p_a[t, i], d_a[t, i], y_a[t, i]
        psh, dh = Q @ (Q.T @ ps), Q @ (Q.T @ d)
        dp = dh - psh * (psh @ dh) / (psh @ psh)
        den = dp @ dp
        parts = dict(aside=c_a["phi"][t, i] - cstar[i] * ps, u=c_a["u"][t, i],
                     n=c_a["n"][t, i], lag=c_a["lag"][t, i])
        e0 = y - cstar[i] * ps - g[i] * d
        r_iv.append((dp @ e0) / den / g[i])
        X = np.column_stack([ps, d])
        r_ols.append(np.linalg.lstsq(X, y, rcond=None)[0][1] / g[i] - 1.0)
        use.append(den / (d @ d))
        s_den += band_sums(dp, dp) / den
        s_num += band_sums(dp, e0) / den / g[i]
        s_psi += band_sums(ps, ps) / (ps @ ps)
        s_d += band_sums(d, d) / (d @ d)
        for k in COMPS:
            s_cmp[k] += band_sums(dp, parts[k]) / den / g[i]
    m = 40 - LO
    r_iv, r_ols = np.array(r_iv), np.array(r_ols)
    return dict(med=100 * np.median(r_iv), mean=100 * r_iv.mean(),
                mae=100 * np.median(np.abs(r_iv)), ols=100 * np.median(r_ols),
                use=100 * np.median(use), den=(s_den / m).tolist(),
                num=(100 * s_num / m).tolist(), psi=(s_psi / m).tolist(), d=(s_d / m).tolist(),
                cmp={k: (100 * v / m).tolist() for k, v in s_cmp.items()})


def one(args):
    seed, kw = args
    sim = simulate(seed, **kw)
    g, gA, c = sim["gB"], sim["gA"], sim["comp"]
    Ae, Be, De, bphi, bu, bn, bdm = E.sync_exact(sim, extra=[c[k] for k in ("phi", "u", "n", "dm")])
    tle = E.est_tool(Ae, Be, De)
    Bc, Dc, Ac = cen(Be), cen(De), cen(Ae)
    Bol = Bc - Dc @ tle["Mdb"].T
    comp = dict(phi=cen(bphi), u=cen(bu), n=cen(bn), lag=cen(bdm) - Dc * g)
    idx = np.arange(40)
    W = ridge_w(Ac, Bol)
    h = len(Ac) // 2
    W1, W2 = ridge_w(Ac[:h], Bol[:h]), ridge_w(Ac[h:], Bol[h:])
    psis = dict(fit=(Ac @ W, g / (gA * W[idx, idx])),
                oracle=(Ac[:, :40] * (g / gA), np.ones(40)),
                xfit=(np.vstack([Ac[:h] @ W2, Ac[h:] @ W1]),
                      g / (gA * 0.5 * (W1[idx, idx] + W2[idx, idx]))))
    out = {}
    for kind, (psi, cstar) in psis.items():
        for label, rho, lags in FORMS:
            out[f"{kind}|{label}"] = analyse(Bc, Dc, psi, cstar, comp, g, rho, lags)
    return out


def avg(rs, key, fld):
    v = np.array([r[key][fld] for r in rs], dtype=float)
    return v.mean(0), v.std(0) / np.sqrt(len(rs))


def row(vals, fmt):
    return "".join(format(x, fmt) for x in vals)


if __name__ == "__main__":
    tasks = []
    for name, sn, tsci, pred in CASES:
        kw = dict(c_hi=0.6, sig_nA=sn, sig_nB=sn, t_sci=tsci, predictive=pred)
        tasks += [(300 + s, kw) for s in range(NSEED)]
    order = sorted(range(len(tasks)), key=lambda j: -tasks[j][1]["t_sci"])
    with Pool(20) as pool:
        done = pool.map(one, [tasks[j] for j in order], chunksize=1)
    allr = [None] * len(tasks)
    for j, r in zip(order, done):
        allr[j] = r
    res = {}
    for ci, (name, _, _, _) in enumerate(CASES):
        rs = allr[ci * NSEED : (ci + 1) * NSEED]
        res[name] = {}
        print(f"\n=== {name} ===")
        for kind in KINDS:
            print(f"\n psi: {kind:7s}     2SLS med  (se)   mean  |err|   LS med  usable%")
            for label, _, _ in FORMS:
                key = f"{kind}|{label}"
                v = {f: avg(rs, key, f) for f in ("med", "mean", "mae", "ols", "use")}
                rec = {f: [float(a), float(s)] for f, (a, s) in v.items()}
                for f in ("den", "num", "psi", "d"):
                    a, s = avg(rs, key, f)
                    rec[f] = [a.tolist(), s.tolist()]
                rec["cmp"] = {k: np.mean([r[key]["cmp"][k] for r in rs], axis=0).tolist()
                              for k in COMPS}
                res[name][key] = rec
                print(f"  {label:18s} {v['med'][0]:+6.1f} ({v['med'][1]:.1f}) {v['mean'][0]:+6.1f}"
                      f" {v['mae'][0]:6.1f} {v['ols'][0]:+8.1f} {v['use'][0]:8.2f}")
        for kind in KINDS:
            for label in SHOW:
                v = res[name][f"{kind}|{label}"]
                print(f"\n  psi {kind}, {label}: band [Hz] " + row(BANDS, ">9s"))
                print("    psi power share            " + row(v["psi"][0], "9.3f"))
                print("    D power share              " + row(v["d"][0], "9.3f"))
                print("    strength share             " + row(v["den"][0], "9.3f"))
                print("    error contribution [%]     " + row(v["num"][0], "+9.2f"))
                print("      standard error           " + row(v["num"][1], "9.2f"))
                for k in COMPS:
                    print(f"      from {k:5s}               " + row(v["cmp"][k], "+9.2f"))
    json.dump(res, open("diff_why.json", "w"), indent=1)
