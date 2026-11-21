#!/usr/bin/env python3
"""Synthetic 2-layer frozen-flow modal telemetry, with optional switching wind regimes.

Usage: gen.py <out.npz> <T_seconds> <switch 0|1> <seed>
"""
import sys
import time

import numpy as np
import scipy.ndimage as ndi

NP_PIX = 24  # pupil diameter [px]
DTEL = 8.0  # telescope diameter [m]
PXS = DTEL / NP_PIX  # [m/px]
NS = 4096  # screen size [px]
L0 = 25.0  # outer scale [m]
FS = 1000.0  # loop rate [Hz]
NMODE = 64
ANG0 = 17.3  # base angle offset [deg] so tracks never retrace on the periodic screen

# layer-1 (jet) wind regimes: (speed m/s, direction deg); layer 2 (ground) is constant
REGIMES = [(14.0, 0.0), (14.0, 40.0), (8.0, -30.0)]
GROUND = (4.0, 200.0)
FRAC1 = 0.6


KCUT = 0.35


def make_psd():
    f = np.fft.fftfreq(NS)
    kx, ky = np.meshgrid(f, f, indexing="ij")
    k2 = kx**2 + ky**2
    k0 = PXS / L0
    psd = (k2 + k0**2) ** (-11.0 / 6.0)
    psd[0, 0] = 0.0
    psd[np.sqrt(k2) > KCUT] = 0.0
    return psd


def make_screen(psd, seed):
    r = np.random.default_rng(seed)
    w = r.standard_normal((NS, NS)) + 1j * r.standard_normal((NS, NS))
    scr = np.fft.ifft2(w * np.sqrt(psd)).real
    scr /= scr.std()
    return ndi.spline_filter(scr, order=3, mode="grid-wrap")


def vel_px(speed, ang_deg):
    a = np.deg2rad(ang_deg + ANG0)
    return np.array([np.cos(a), np.sin(a)]) * speed / PXS / FS  # px / frame


def main():
    global KCUT
    if len(sys.argv) > 5:
        KCUT = float(sys.argv[5])
    basis = sys.argv[6] if len(sys.argv) > 6 else "kl"
    frac1 = float(sys.argv[7]) if len(sys.argv) > 7 else FRAC1
    out, t_sec = sys.argv[1], float(sys.argv[2])
    do_switch, seed = int(sys.argv[3]), int(sys.argv[4])
    rng = np.random.default_rng(seed)
    n_t = int(t_sec * FS)
    t0 = time.time()
    psd = make_psd()

    # pupil pixels
    xx, yy = np.meshgrid(np.arange(NP_PIX), np.arange(NP_PIX), indexing="ij")
    cx = (NP_PIX - 1) / 2.0
    mask = (xx - cx) ** 2 + (yy - cx) ** 2 <= (NP_PIX / 2.0) ** 2
    px = xx[mask].astype(np.float64)
    py = yy[mask].astype(np.float64)
    n_pix = px.size

    # exact pupil covariance from the screen autocorrelation -> KL modes
    acf = np.fft.ifft2(psd).real
    acf /= acf[0, 0]

    def cov_shift(dx, dy):
        ix = (px[:, None] - px[None, :] + dx).astype(int) % NS
        iy = (py[:, None] - py[None, :] + dy).astype(int) % NS
        return acf[ix, iy]

    c0 = cov_shift(0, 0)
    pm = np.eye(n_pix) - np.ones((n_pix, n_pix)) / n_pix
    if basis == "fourier":
        # cos/sin pairs sorted by spatial frequency, orthonormalized in order on the pupil
        xa = (px - cx) / NP_PIX
        ya = (py - cx) / NP_PIX
        ks = [(kx, ky) for kx in range(-9, 10) for ky in range(0, 10) if (ky > 0 or kx > 0)]
        ks.sort(key=lambda k: (k[0] ** 2 + k[1] ** 2, k[1], k[0]))
        cols = [np.ones_like(xa)]
        for kx, ky in ks[: NMODE // 2 + 1]:
            ph = 2 * np.pi * (kx * xa + ky * ya)
            cols += [np.cos(ph), np.sin(ph)]
        q_mat, _ = np.linalg.qr(np.column_stack(cols)[:, : NMODE + 1])
        modes = q_mat[:, 1:]
    else:
        ev, evec = np.linalg.eigh(pm @ c0 @ pm)
        order = np.argsort(ev)[::-1][:NMODE]
        modes = evec[:, order]
    caa = modes.T @ c0 @ modes
    lam = np.diag(caa).copy()
    caa_inv = np.linalg.inv(caa)
    # optimal linear modal derivative operators: d a / d x ~ Dx a
    dx_op = (modes.T @ (cov_shift(1, 0) - cov_shift(-1, 0)) @ modes) / 2.0 @ caa_inv
    dy_op = (modes.T @ (cov_shift(0, 1) - cov_shift(0, -1)) @ modes) / 2.0 @ caa_inv

    # regime schedule for layer 1
    lab = np.zeros(n_t, dtype=np.int64)
    if do_switch:
        t = 0
        cur = 0
        while t < n_t:
            d = int(rng.uniform(6.0, 14.0) * FS)
            lab[t : t + d] = cur
            t += d
            nxt = int(rng.integers(len(REGIMES) - 1))
            cur = nxt if nxt < cur else nxt + 1
    v1 = np.array([vel_px(*REGIMES[k]) for k in lab])
    v2 = np.tile(vel_px(*GROUND), (n_t, 1))

    a_true = np.zeros((n_t, NMODE))
    for li, (vel, frac) in enumerate(((v1, frac1), (v2, 1.0 - frac1))):
        scr = make_screen(psd, seed * 100 + li + 1)
        pos = np.cumsum(vel, axis=0) + rng.uniform(0, NS, size=2)
        chunk = 4000
        for s in range(0, n_t, chunk):
            p = pos[s : s + chunk]
            cxs = (px[None, :] - p[:, 0:1]).ravel()
            cys = (py[None, :] - p[:, 1:2]).ravel()
            ph = ndi.map_coordinates(scr, [cxs, cys], order=3, mode="grid-wrap", prefilter=False)
            a_true[s : s + chunk] += np.sqrt(frac) * (ph.reshape(-1, n_pix) @ modes)
        print(f"layer {li} done {time.time() - t0:.1f}s", flush=True)

    np.savez(out, a_true=a_true, lab=lab, lam=lam, dx_op=dx_op, dy_op=dy_op, pxs=PXS, fs=FS,
             regimes=np.array(REGIMES), ground=np.array(GROUND))
    print("modal var (first 8):", np.var(a_true, axis=0)[:8].round(4), "lam:", lam[:8].round(4))
    print(f"wrote {out} T={n_t} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
