"""Native 2 kHz, per-mode check of the closed-loop blend formula:
   g_hat(f) = (1 - rho(f)) g + rho(f) * (-Re 1/K(f)),
with rho = share of DM2 power driven by the unmeasured disturbance + noise, K = known controller.
Uses the oracle disturbance (B_phi) so that only the D term is being identified."""
import sys
import numpy as np
from multiprocessing import Pool
from sim import simulate
import estimators as E

NPS = 512
FR = np.fft.rfftfreq(NPS, 1 / 2000.0)

def K_of(sim, f):
    p = sim["p"]; z1 = np.exp(-2j * np.pi * f / 2000.0)
    Ki = p["gain2"] / (1 - p["leak2"] * z1)
    if sim["F"] is None:
        return (z1 ** 3) * Ki
    F = sim["F"]                                   # (dB, q)
    Fz = (F[:, :, None] * (z1[None, None, :] ** np.arange(F.shape[1])[None, :, None])).sum(1)
    mix = p["pf_mix"]
    Kc = ((1 - mix) * Ki[None, :] + mix * Fz / p["wfsfact"]) / (1 - mix * Fz * z1 ** 3)
    return (z1 ** 3) * Kc                          # (dB, nf)

def one(args):
    seed, kw = args
    sim = simulate(seed, **kw)
    g = sim["gB"]; c = sim["comp"]
    D = np.roll(sim["D"], 3, axis=0)[8:]           # D_eff[k] = D[k-3]
    Y = (sim["B"] - c["phi"])[8:]                  # oracle: remove measured-disturbance term
    V = (c["u"] + c["n"])[8:]
    P = (c["phi"] / g)[8:]
    dB = len(g)
    Sdd = np.zeros((len(FR), dB)); Syd = np.zeros((len(FR), dB), complex)
    Svv = np.zeros((len(FR), dB)); Spp = np.zeros((len(FR), dB))
    win = np.hanning(NPS)[:, None]; nseg = 0
    for s0 in range(0, len(D) - NPS + 1, NPS // 2):
        f = lambda x: np.fft.rfft((x[s0:s0 + NPS] - x[s0:s0 + NPS].mean(0)) * win, axis=0)
        d, y, v, ph = f(D), f(Y), f(V), f(P)
        Sdd += np.abs(d) ** 2; Syd += y * d.conj(); Svv += np.abs(v) ** 2; Spp += np.abs(ph) ** 2
        nseg += 1
    ghat_f = Syd.real / Sdd
    rho = Svv / (g[None, :] ** 2 * Spp + Svv)
    K = K_of(sim, FR[1:])
    cfb = np.zeros((len(FR), dB))
    cfb[1:] = (-(1 / K).real).T if K.ndim == 2 else (-(1 / K).real)[:, None]
    pred = (1 - rho) * g[None, :] + rho * cfb
    # plain time-domain OLS on D only (oracle), and iterated AR(p) residual whitening (PEM)
    out = {"ols": (Y * D).sum(0) / (D * D).sum(0)}
    for p_ord in (4, 16, 64):
        gh = out["ols"].copy()
        for _ in range(6):
            new = np.zeros(dB)
            for j in range(dB):
                e = Y[:, j] - gh[j] * D[:, j]
                r = np.array([np.dot(e[m:], e[:len(e) - m]) for m in range(p_ord + 1)])
                R = np.array([[r[abs(a - b)] for b in range(p_ord)] for a in range(p_ord)])
                a = np.linalg.solve(R + 1e-9 * r[0] * np.eye(p_ord), r[1:])
                taps = np.r_[1.0, -a]
                yf = np.convolve(Y[:, j], taps, mode="valid")
                df = np.convolve(D[:, j], taps, mode="valid")
                new[j] = np.dot(yf, df) / np.dot(df, df)
            gh = new
        out[f"pem{p_ord}"] = gh
    return dict(g=g, ghat_f=ghat_f, pred=pred, rho=rho, cfb=cfb, **out)

if __name__ == "__main__":
    kw = {k: float(v) for k, v in (a.split("=") for a in sys.argv[1:])}
    for pred in (False, True):
        with Pool(6) as pool:
            res = pool.map(one, [(s, dict(predictive=pred, **kw)) for s in range(16)])
        g = res[0]["g"]; sl = slice(4, 40)
        gf = np.mean([r["ghat_f"] for r in res], 0); pf = np.mean([r["pred"] for r in res], 0)
        rho = np.mean([r["rho"] for r in res], 0); cfb = res[0]["cfb"]
        print("== %s: frequency-local estimate / g vs blend prediction"
              " (median over modes 4..39)" % ("PREDICTIVE" if pred else "INTEGRATOR"))
        print("  f[Hz]   g_hat/g   blend/g   rho   -Re(1/K)/g")
        for fi in (1, 2, 4, 8, 13, 20, 28, 40, 60, 80, 110, 150, 200, 255):
            print(f"  {FR[fi]:6.1f}  {np.median(gf[fi, sl] / g[sl]):+7.2f}"
                  f"  {np.median(pf[fi, sl] / g[sl]):+7.2f}  "
                  f"{np.median(rho[fi, sl]):.2f}  {np.median(cfb[fi, sl] / g[sl]):+7.2f}")
        np.savez(f"theory_{'pred' if pred else 'int'}.npz", fr=FR, g=g, gf=gf, pf=pf,
                 rho=rho, cfb=cfb,
                 **{k: np.array([r[k] for r in res]) for k in ("ols", "pem4", "pem16", "pem64")})
        for k in ("ols", "pem4", "pem16", "pem64"):
            v = np.array([np.median(r[k][sl] / g[sl]) for r in res])
            print(f"  time-domain {k:6s}: median g_hat/g = {v.mean():.3f} +/- {v.std():.3f}"
                  " (run-to-run)")
