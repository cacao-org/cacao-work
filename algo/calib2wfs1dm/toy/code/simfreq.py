"""Two-stage closed-loop toy model with arbitrary loop frequencies.

Same physics as sim.py (modal, linear, known truth Mdb = diag(gB)), but the two wavefront
sensors may run at any rates that are integer numbers of ticks of a fine grid, with an optional
offset between their frame clocks. Integrator control only.

    na_t, nb_t   ticks per WFS A / WFS B exposure      (rate = fs / n_t)
    b_off        ticks by which WFS B frame boundaries lag those of WFS A
    delay*_fr    loop delay from the end of an exposure to the DM update, in own frames
"""
from collections import deque

import numpy as np

DEFAULTS = dict(
    fs=24000.0, na_t=24, nb_t=12, b_off=0, t_sci=5.0, t_warm=1.0, n1=100, dB=40, hi0=60,
    gA=0.93, gB_mean=0.70, gB_slope=0.06, gain1=0.35, leak1=0.98, delay1_fr=2.0, tau1_us=200.0,
    gain2=0.35, leak2=0.98, delay2_fr=2.0, tau2_us=60.0, sig_nA=0.002, sig_nB=0.002,
    c_hi=0.6, sig_alias=0.004, vd=1.25,
    noise_ref_hz=(1000.0, 2000.0),  # frame rates at which sig_nA, sig_nB are quoted
)


def radial_order(m):
    return np.floor((np.sqrt(8.0 * (m + 1) + 1.0) - 1.0) / 2.0)


def colored(rng, n_t, fs, fc, sig):
    """Gaussian series with PSD ~ 1/(1+(f/fc)^2)^(17/6), synthesised at 2 kHz and interpolated."""
    step = fs / 2000.0
    n_lo = int(n_t / step) + 8
    f = np.fft.rfftfreq(n_lo, d=1.0 / 2000.0)
    amp = (1.0 + (f[:, None] / fc[None, :]) ** 2) ** (-17.0 / 12.0)
    amp[0] = 0.0
    spec = (rng.standard_normal(amp.shape) + 1j * rng.standard_normal(amp.shape)) * amp
    x = np.fft.irfft(spec, n=n_lo, axis=0)
    x *= sig[None, :] / x.std(axis=0)[None, :]
    t_lo, t_hi = np.arange(n_lo) * step, np.arange(n_t, dtype=float)
    return np.column_stack([np.interp(t_hi, t_lo, x[:, j]) for j in range(len(fc))])


def simulate(seed, **kw):
    p = {**DEFAULTS, **kw}
    rng = np.random.default_rng(seed)
    fs, na, nb, off = p["fs"], int(p["na_t"]), int(p["nb_t"]), int(p["b_off"])
    n1, dB, hi0 = p["n1"], p["dB"], p["hi0"]
    n_t = int(round((p["t_warm"] + p["t_sci"]) * fs))
    m = np.arange(n1)
    nrad = radial_order(m)
    fc = 0.3 * (nrad + 1.0) * p["vd"]
    sig = (nrad + 1.0) ** (-11.0 / 6.0)
    sig /= sig[0]
    theta = colored(rng, n_t, fs, fc, sig)
    ual = colored(rng, n_t, fs, fc[:dB], sig[:dB] * p["sig_alias"])
    n_hi = min(dB, n1 - hi0)
    gB = p["gB_mean"] + p["gB_slope"] * (np.arange(dB) / (dB - 1.0) - 0.5)
    gA = p["gA"]
    a1 = 1.0 - np.exp(-1e6 / (fs * p["tau1_us"]))
    a2 = 1.0 - np.exp(-1e6 / (fs * p["tau2_us"]))
    d1t, d2t = int(round(p["delay1_fr"] * na)), int(round(p["delay2_fr"] * nb))
    # photon-noise-like scaling: a shorter exposure is noisier
    snA = p["sig_nA"] * np.sqrt((fs / na) / p["noise_ref_hz"][0])
    snB = p["sig_nB"] * np.sqrt((fs / nb) / p["noise_ref_hz"][1])

    dm1, dm1_tgt, c1 = np.zeros(n1), np.zeros(n1), np.zeros(n1)
    dm2, dm2_tgt, c2 = np.zeros(dB), np.zeros(dB), np.zeros(dB)
    pend1, pend2 = deque(), deque()
    accA = np.zeros(n1)
    acc = {k: np.zeros(dB) for k in ("phi", "u", "dm")}
    cnt_b = 0
    A, a_end, B, b_end, D = [], [], [], [], []
    comp = {k: [] for k in ("phi", "u", "dm", "n")}
    for n in range(n_t):
        while pend1 and pend1[0][0] == n:
            dm1_tgt = pend1.popleft()[1]
        while pend2 and pend2[0][0] == n:
            dm2_tgt = pend2.popleft()[1]
        dm1 += a1 * (dm1_tgt - dm1)
        dm2 += a2 * (dm2_tgt - dm2)
        phi1 = theta[n] + dm1
        accA += phi1
        u_now = ual[n].copy()
        u_now[:n_hi] += p["c_hi"] * phi1[hi0:hi0 + n_hi]
        acc["phi"] += phi1[:dB]
        acc["u"] += u_now
        acc["dm"] += dm2
        cnt_b += 1
        if n + 1 > off and (n + 1 - off) % nb == 0:
            parts = {k: gB * v / cnt_b for k, v in acc.items()}
            bn = snB * rng.standard_normal(dB)
            b = parts["phi"] + parts["u"] + parts["dm"] + bn
            c2 = p["leak2"] * c2 - p["gain2"] * b
            pend2.append((n + 1 + d2t, c2.copy()))
            B.append(b)
            D.append(c2.copy())
            b_end.append(n + 1)
            for k in parts:
                comp[k].append(parts[k])
                acc[k][:] = 0.0
            comp["n"].append(bn)
            cnt_b = 0
        if (n + 1) % na == 0:
            a = gA * accA / na + snA * rng.standard_normal(n1)
            c1 = p["leak1"] * c1 - p["gain1"] * a
            pend1.append((n + 1 + d1t, c1.copy()))
            A.append(a)
            a_end.append(n + 1)
            accA[:] = 0.0
    t0 = int(round(p["t_warm"] * fs))  # first science tick
    return dict(A=np.array(A), a_end=np.array(a_end), B=np.array(B), b_end=np.array(b_end),
                D=np.array(D), comp={k: np.array(v) for k, v in comp.items()}, gB=gB, gA=gA,
                p=p, n_t=n_t, t0=t0, d2t=d2t)
