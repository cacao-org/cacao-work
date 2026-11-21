"""Known-truth two-stage, two-rate closed-loop AO toy model for calibration-estimator studies.

Structure mirrors the AO3k + SCExAO bench (1 kHz stage 1, 2 kHz stage 2, 8 kHz fine grid, DM
delay + first-order servo, 3-frame total loop delay) but everything is modal and linear, so the
true matrices are known exactly: Mdb = diag(gB), Mab = (gB/gA) [I 0].
"""

from collections import deque

import numpy as np

FS = 8000.0  # fine grid [Hz]
NA_T = 8  # ticks per WFS-A exposure (1 kHz)
NB_T = 4  # ticks per WFS-B exposure (2 kHz)

DEFAULTS = dict(
    t_sci=5.0,
    t_warm=1.0,
    n1=100,  # modes controlled by stage 1 and present in stream A
    dB=40,  # stage-2 modes (B and D)
    hi0=60,  # first stage-1 mode index that leaks into B ("modes beyond dA")
    gA=0.93,
    gB_mean=0.70,
    gB_slope=0.06,
    gain1=0.35,
    leak1=0.98,
    delay1_ticks=16,
    tau1_us=200.0,
    gain2=0.35,
    leak2=0.98,
    delay2_ticks=8,
    tau2_us=60.0,
    sig_nA=0.004,
    sig_nB=0.004,
    sig_vA=0.0,  # coloured (aliasing-like) measurement error in A, relative to turbulence
    c_hi=0.5,  # coupling of stage-1 modes hi0.. into B modes
    sig_alias=0.004,  # B-only open-loop-like disturbance, relative to turbulence sigma
    vd=1.25,  # wind speed / diameter [Hz]
    predictive=False,
    pf_order=8,
    pf_mix=0.9,
    pf_reg=1e-3,
    wfsfact=1.0,
    dither_nm=0.0,  # RMS of white DM2 dither per mode (same units as wavefront)
    gain2_switch=0.0,  # +/- fractional gain2 square-wave modulation
    gain2_switch_period=0.5,
    lo_modes=0,  # number of low-order modes driven by an unlogged stage-3 channel
    lo_gain=0.2,
    lo_sig_n=0.01,
    lo_zpo_gain=1.0,  # gain assumed by the zero-point-offset subtraction (truth is gB)
)


def radial_order(m):
    return np.floor((np.sqrt(8.0 * (m + 1) + 1.0) - 1.0) / 2.0)


def colored(rng, n_t, fc, sig):
    """Gaussian series (n_t, n_modes) with PSD ~ 1/(1+(f/fc)^2)^(17/6), unit-normalised * sig."""
    n_lo = n_t // 4 + 8  # synthesise at 2 kHz, then interpolate (no power above 1 kHz)
    f = np.fft.rfftfreq(n_lo, d=4.0 / FS)
    amp = (1.0 + (f[:, None] / fc[None, :]) ** 2) ** (-17.0 / 12.0)
    amp[0] = 0.0
    spec = (rng.standard_normal(amp.shape) + 1j * rng.standard_normal(amp.shape)) * amp
    x = np.fft.irfft(spec, n=n_lo, axis=0)
    x *= sig[None, :] / x.std(axis=0)[None, :]
    t_lo = np.arange(n_lo) * 4.0
    t_hi = np.arange(n_t, dtype=float)
    out = np.empty((n_t, len(fc)))
    for j in range(len(fc)):
        out[:, j] = np.interp(t_hi, t_lo, x[:, j])
    return out


def simulate(seed, **kw):
    p = {**DEFAULTS, **kw}
    rng = np.random.default_rng(seed)
    n1, dB, hi0 = p["n1"], p["dB"], p["hi0"]
    t_warm = p["t_warm"] + (0.3 if p["predictive"] else 0.0)
    n_t = int(round((t_warm + p["t_sci"]) * FS))
    n_t -= n_t % NA_T

    m = np.arange(n1)
    nrad = radial_order(m)
    fc = 0.3 * (nrad + 1.0) * p["vd"]
    sig = (nrad + 1.0) ** (-11.0 / 6.0)
    sig /= sig[0]
    theta = colored(rng, n_t, fc, sig)
    ual = colored(rng, n_t, fc[:dB], sig[:dB] * p["sig_alias"])
    n_hi = min(dB, n1 - hi0)
    vA = colored(rng, n_t, fc, sig * p["sig_vA"])[::NA_T] if p["sig_vA"] > 0 else None

    gB = p["gB_mean"] + p["gB_slope"] * (np.arange(dB) / (dB - 1.0) - 0.5)
    gA = p["gA"]
    a1 = 1.0 - np.exp(-1e6 / (FS * p["tau1_us"]))
    a2 = 1.0 - np.exp(-1e6 / (FS * p["tau2_us"]))

    dm1 = np.zeros(n1)
    dm1_tgt = np.zeros(n1)
    c1 = np.zeros(n1)
    dm2 = np.zeros(dB)
    dm2_tgt = np.zeros(dB)
    d_int = np.zeros(dB)
    c2 = np.zeros(dB)
    d3 = np.zeros(dB)
    d3_tgt = np.zeros(dB)
    c3 = np.zeros(dB)
    pend1, pend2, pend3 = deque(), deque(), deque()
    accA = np.zeros(n1)
    acc_phi = np.zeros(dB)
    acc_u = np.zeros(dB)
    acc_dm = np.zeros(dB)
    acc_d3 = np.zeros(dB)
    acc_lo = np.zeros(dB)
    n_lo_t = 16  # stage-3 exposure: 500 Hz

    nfa = n_t // NA_T
    nfb = n_t // NB_T
    A = np.zeros((nfa, n1))
    C1 = np.zeros((nfa, n1))
    B = np.zeros((nfb, dB))
    Bphi = np.zeros((nfb, dB))
    Bu = np.zeros((nfb, dB))
    Bdm = np.zeros((nfb, dB))
    Bd3 = np.zeros((nfb, dB))
    Bn = np.zeros((nfb, dB))
    D = np.zeros((nfb, dB))
    D3 = np.zeros((nfb, dB))
    D3e = np.zeros((nfb, dB))
    Dith = np.zeros((nfb, dB))
    ia = ib = 0

    pf_on = False
    F = None
    pol_hist = deque(maxlen=p["pf_order"])
    pol_log = []
    k_train = int(round(p["t_warm"] * FS / NB_T)) if p["predictive"] else -1
    lo = p["lo_modes"]
    hist_c = deque([np.zeros(dB)] * 4, maxlen=4)  # last commands, for pseudo-open-loop
    gain2 = p["gain2"]
    sw_frames = int(round(p["gain2_switch_period"] * FS / NB_T))

    for n in range(n_t):
        while pend1 and pend1[0][0] == n:
            dm1_tgt = pend1.popleft()[1]
        while pend2 and pend2[0][0] == n:
            dm2_tgt = pend2.popleft()[1]
        while pend3 and pend3[0][0] == n:
            d3_tgt = pend3.popleft()[1]
        dm1 += a1 * (dm1_tgt - dm1)
        dm2 += a2 * (dm2_tgt - dm2)
        phi1 = theta[n] + dm1
        accA += phi1
        acc_phi += phi1[:dB]
        u_now = ual[n].copy()
        u_now[:n_hi] += p["c_hi"] * phi1[hi0 : hi0 + n_hi]
        acc_u += u_now
        acc_dm += dm2
        if lo:
            d3 += a2 * (d3_tgt - d3)
            acc_d3 += d3
            acc_lo += phi1[:dB] + u_now + dm2 + d3

        if (n + 1) % NB_T == 0:
            bphi = gB * acc_phi / NB_T
            bu = gB * acc_u / NB_T
            bdm = gB * acc_dm / NB_T
            bd3 = gB * acc_d3 / NB_T
            bn = p["sig_nB"] * rng.standard_normal(dB)
            b = bphi + bu + bdm + bd3 + bn
            # zero-point offset: stage 2 is told to ignore the stage-3 command at an assumed gain
            b_ctrl = b - p["lo_zpo_gain"] * (acc_d3 / NB_T) if lo else b
            if p["gain2_switch"] > 0.0:
                sgn = 1.0 if (ib // sw_frames) % 2 == 0 else -1.0
                gain2 = p["gain2"] * (1.0 + sgn * p["gain2_switch"])
            d_int = p["leak2"] * d_int - gain2 * b_ctrl
            pol = b_ctrl / p["wfsfact"] - hist_c[-3]
            pol_hist.appendleft(pol)
            if p["predictive"] and not pf_on:
                pol_log.append(pol)
                if ib == k_train:
                    P = np.array(pol_log)
                    q, h = p["pf_order"], 3
                    F = np.zeros((dB, q))
                    for j in range(dB):
                        y = P[q - 1 + h :, j]
                        X = np.column_stack(
                            [P[q - 1 - i : len(P) - h - i, j] for i in range(q)]
                        )
                        G = X.T @ X
                        G += p["pf_reg"] * np.trace(G) / q * np.eye(q)
                        F[j] = np.linalg.solve(G, X.T @ y)
                    pf_on = True
            if pf_on and len(pol_hist) == p["pf_order"]:
                d_pf = -np.einsum("jq,qj->j", F, np.array(pol_hist))
                c2 = (1.0 - p["pf_mix"]) * d_int + p["pf_mix"] * d_pf
            else:
                c2 = d_int.copy()
            dith = p["dither_nm"] * rng.standard_normal(dB) if p["dither_nm"] > 0 else 0.0
            c2 = c2 + dith
            hist_c.append(c2.copy())
            pend2.append((n + 1 + p["delay2_ticks"], c2.copy()))
            if lo:
                bd3 = bd3 - p["lo_zpo_gain"] * (acc_d3 / NB_T)
                D3e[ib] = acc_d3 / NB_T
            B[ib], Bphi[ib], Bu[ib], Bdm[ib], Bd3[ib], Bn[ib] = b_ctrl, bphi, bu, bdm, bd3, bn
            D[ib] = c2
            D3[ib] = c3
            Dith[ib] = dith
            ib += 1
            acc_phi[:] = 0.0
            acc_u[:] = 0.0
            acc_dm[:] = 0.0
            acc_d3[:] = 0.0

        if lo and (n + 1) % n_lo_t == 0:
            meas = acc_lo / n_lo_t + p["lo_sig_n"] * rng.standard_normal(dB)
            c3 = 0.99 * c3
            c3[:lo] -= p["lo_gain"] * meas[:lo]
            pend3.append((n + 1 + p["delay2_ticks"], c3.copy()))
            acc_lo[:] = 0.0

        if (n + 1) % NA_T == 0:
            a = gA * accA / NA_T + p["sig_nA"] * rng.standard_normal(n1)
            if vA is not None:
                a = a + vA[ia]
            c1 = p["leak1"] * c1 - p["gain1"] * a
            pend1.append((n + 1 + p["delay1_ticks"], c1.copy()))
            A[ia] = a
            C1[ia] = c1
            ia += 1
            accA[:] = 0.0

    ka = int(round(t_warm * FS / NA_T))
    kb = int(round(t_warm * FS / NB_T))
    tA = (np.arange(nfa) + 1) * NA_T / FS
    tB = (np.arange(nfb) + 1) * NB_T / FS
    return dict(
        A=A[ka:],
        tA=tA[ka:],
        C1=C1[ka:],
        B=B[kb:],
        tB=tB[kb:],
        D=D[kb:],
        D3=D3[kb:],
        D3e=D3e[kb:],
        Dith=Dith[kb:],
        comp=dict(phi=Bphi[kb:], u=Bu[kb:], dm=Bdm[kb:], d3=Bd3[kb:], n=Bn[kb:]),
        gB=gB,
        gA=gA,
        F=F,
        p=p,
    )


if __name__ == "__main__":
    import time

    t0 = time.time()
    r = simulate(1)
    print("sim time %.2f s" % (time.time() - t0), r["A"].shape, r["B"].shape)
    c = r["comp"]
    for k, v in c.items():
        print(f"  B component {k:4s} rms (modes 0,10,39): ", np.round(v.std(0)[[0, 10, 39]], 4))
    print("  B total rms:", np.round(r["B"].std(0)[[0, 10, 39]], 4))
    print("  D rms:", np.round(r["D"].std(0)[[0, 10, 39]], 4))
    print("  A rms:", np.round(r["A"].std(0)[[0, 10, 39, 70]], 4))
    b_ol = c["phi"] + c["u"]
    print("  disturbance entering stage 2 rms:", np.round(b_ol.std(0)[[0, 10, 39]], 4))
