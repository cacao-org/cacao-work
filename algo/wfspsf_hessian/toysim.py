#!/usr/bin/env python3
"""Toy optics for the WFS -> PSF Hessian study.

Monochromatic, no DM, no coronagraph. A wavefront phi (radians) on a circular pupil gives the
focal-plane field through a matrix Fourier transform (MFT) evaluated only over the field of
interest. The PSF is its squared modulus summed over detector pixels; the pyramid WFS image is
obtained by filtering that same field, inside a square field stop, with a four-faced phase
mask, summed over a circular tip/tilt modulation.

Sampling (defaults):
- pupil: 128 pixels across with an anti-aliased edge. A coarse hard-edged pupil aliases the
  PSF wings (replicas of the PSF every `dpix` lambda/D): 32 pixels with a hard edge is wrong
  by 20 to 80% beyond 4 lambda/D, the default by about 1% out to 11.5 lambda/D;
- focal plane: 6 field samples per lambda/D, summed 2 x 2 into detector pixels of 1/3
  lambda/D, i.e. 1.5 x Nyquist; 69 x 69 pixels, +-11.5 lambda/D;
- pyramid: field stop +-12 lambda/D, pupil images 24 detector pixels across.

Units: modal coefficients are radians RMS over the pupil; images are fractions of the total
flux per pixel; focal-plane coordinates are in lambda/D.
"""
import ctypes
import multiprocessing as mp
import os

import numpy as np
import scipy.fft as sf
from scipy.linalg import eigh
from scipy.signal import lfilter

HERE = os.path.dirname(os.path.abspath(__file__))
NPROC = int(os.environ.get("TOY_NPROC", "8"))
_POOL_OPT = None


def _single_thread_blas():
    """Forked workers must not each start a BLAS thread pool."""
    for lib in ("libopenblas.so.0", "libopenblas.so"):
        try:
            ctypes.CDLL(lib).openblas_set_num_threads(1)
            return True
        except (OSError, AttributeError):
            continue
    return False


def _forward_block(args):
    return _POOL_OPT._forward_modes(*args)


class Optics:
    """Pupil, Karhunen-Loeve modes, PSF sampler and modulated pyramid WFS."""

    def __init__(self, dpix=128, ld=6, kmodes=80, psf_half=69, psf_bin=2, mod_rad=3.0,
                 n_mod=16, wfs_npix=144):
        self.dpix, self.ld = dpix, ld  # pupil diameter [pupil pixels], focal samples / (l/D)
        self.neq = dpix * ld  # size of the FFT that would give the same focal sampling
        # Pupil on its bounding box, edge pixels weighted by the fraction of their area inside.
        npb, sub = dpix + 2, 8
        c = np.arange(npb) - (npb - 1) / 2.0
        fine = (c[:, None] + (np.arange(sub) + 0.5) / sub - 0.5).ravel()
        inside = fine[:, None] ** 2 + fine[None, :] ** 2 <= (dpix / 2.0) ** 2
        amp = inside.reshape(npb, sub, npb, sub).mean((1, 3))
        self.npb, self.xp = npb, c
        self.pidx = np.flatnonzero(amp > 0)
        self.npup = self.pidx.size
        self.pamp = amp.ravel()[self.pidx].astype(np.float32)
        self.pnorm2 = float((self.pamp.astype(np.float64) ** 2).sum())
        # Focal grid of the field stop: nw samples per axis, centred on the PSF (half-sample
        # offsets, so the pyramid tip and the detector pixel corners fall between samples).
        nw = wfs_npix
        nu = np.arange(nw) - nw / 2.0 + 0.5
        if (2 * psf_half) % psf_bin or 2 * psf_half > nw:
            raise ValueError("need 2*psf_half <= wfs_npix and a multiple of psf_bin")
        self.nw, self.psf_half, self.psf_bin = nw, psf_half, psf_bin
        mft = np.exp(-2j * np.pi * np.outer(nu, c) / self.neq)  # (nw, npb)
        c0 = nw // 2 - psf_half
        self._psl = slice(c0, c0 + 2 * psf_half)
        self._mft64 = mft[self._psl]  # rows of the PSF field, complex128, for taylor()
        self._mft = mft.astype(np.complex64)
        self._mft_t = np.ascontiguousarray(self._mft.T)
        self._mftp = np.ascontiguousarray(self._mft[self._psl])
        self._mftp_t = np.ascontiguousarray(self._mftp.T)
        self.nside = 2 * psf_half // psf_bin
        self.npsf = self.nside**2
        self.psf_norm = 1.0 / (float(self.neq) ** 2 * self.pnorm2)
        ax = nu[self._psl].reshape(-1, psf_bin).mean(1) / ld
        self.psf_ax = ax
        self.psf_r = np.hypot(ax[:, None], ax[None, :]).ravel()
        self.kmodes = kmodes
        self.modes = self._kl_modes(kmodes) if kmodes else None
        # Pyramid masks: phase slope pi/2 per focal sample moves each pupil image by a quarter
        # of the nw x nw detector array. Modulation: the pyramid tip visits n_mod points of a
        # circle (integer numbers of focal samples).
        nm = n_mod if mod_rad > 0 else 1
        masks = []
        for jm in range(nm):
            th = 2 * np.pi * (jm + 0.5) / nm
            dy = int(round(mod_rad * ld * np.sin(th)))
            dx = int(round(mod_rad * ld * np.cos(th)))
            ph = np.abs(nu - dy)[:, None] + np.abs(nu - dx)[None, :]
            masks.append(np.exp(0.5j * np.pi * ph))
        self.pymasks = np.array(masks).astype(np.complex64)
        # Re-imaged pupil plane: nw x nw detector pixels of pitch neq/nw pupil pixels; the four
        # pupil images are centred on (nw/4, 3nw/4) x (nw/4, 3nw/4).
        self.wfs_pitch = self.neq / nw
        self.wfs_centres = (nw // 4, 3 * nw // 4)
        my, mx = np.indices((nw, nw))
        sel = np.zeros((nw, nw), bool)
        for cy in self.wfs_centres:
            for cx in self.wfs_centres:
                sel |= np.hypot(mx - cx, my - cy) <= dpix / 2.0 / self.wfs_pitch + 0.4
        self.wfs_sel = np.flatnonzero(sel)
        self.nwfs = self.wfs_sel.size
        self.wfs_norm = float(nw) ** 2 / (float(self.neq) ** 2 * self.pnorm2 * nm)

    def _kl_modes(self, k):
        """Kolmogorov KL modes on the pupil pixels: piston-free and orthonormal for the pupil
        weights (unit weighted mean square). The eigen-decomposition is cached on disk."""
        kk = max(k, 80)
        cache = os.path.join(HERE, f"kl_cache_dpix{self.dpix}_k{kk}.npy")
        if os.path.exists(cache):
            return np.load(cache)[:k]
        y, x = np.unravel_index(self.pidx, (self.npb, self.npb))
        d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
        d /= self.dpix
        np.power(d, 5.0 / 3.0, out=d)
        d *= 6.88
        w = self.pamp.astype(np.float64)
        w /= w.sum()
        a = d @ w
        d -= a[:, None]
        d -= a[None, :]
        d += w @ a
        d *= -0.5  # piston-removed phase covariance
        sw = np.sqrt(w)
        d *= sw[:, None]
        d *= sw[None, :]
        n = self.npup
        ev, vec = eigh(d, subset_by_index=[n - kk, n - 1], overwrite_a=True)
        modes = np.ascontiguousarray((vec[:, ::-1] / sw[:, None]).T)
        np.save(cache, modes)
        return modes[:k]

    def _fields(self, phi, mft, mft_t):
        e = np.zeros((phi.shape[0], self.npb * self.npb), np.complex64)
        e[:, self.pidx] = np.exp(1j * phi.astype(np.float32)) * self.pamp
        return np.matmul(np.matmul(mft, e.reshape(-1, self.npb, self.npb)), mft_t)

    def _psf(self, f):
        i = (f.real**2 + f.imag**2) * self.psf_norm
        if self.psf_bin > 1:
            m, b = self.nside, self.psf_bin
            i = i.reshape(-1, m, b, m, b).sum((2, 4))
        return i.reshape(len(f), -1)

    def _wfs(self, f):
        acc = np.zeros(f.shape, np.float32)
        for m in self.pymasks:
            g = sf.ifft2(f * m, workers=1, overwrite_x=True)
            acc += g.real**2 + g.imag**2
        return acc.reshape(len(f), -1)[:, self.wfs_sel] * self.wfs_norm

    def _forward_modes(self, b, want_wfs=True, chunk=8):
        """b: (B, K) modal coefficients -> psf (B, npsf), wfs (B, nwfs), single thread."""
        nb = b.shape[0]
        modes = self._modes32[: b.shape[1]]
        psf = np.empty((nb, self.npsf), np.float32)
        wfs = np.empty((nb, self.nwfs), np.float32) if want_wfs else None
        for i0 in range(0, nb, chunk):
            phi = b[i0 : i0 + chunk].astype(np.float32) @ modes
            if want_wfs:
                f = self._fields(phi, self._mft, self._mft_t)
                psf[i0 : i0 + chunk] = self._psf(f[:, self._psl, self._psl])
                wfs[i0 : i0 + chunk] = self._wfs(f)
            else:
                psf[i0 : i0 + chunk] = self._psf(self._fields(phi, self._mftp, self._mftp_t))
        return psf, wfs

    def forward(self, b, want_wfs=True, nproc=NPROC, block=512):
        """b: (N, K) modal coefficients [rad]. Returns psf (N, npsf), wfs (N, nwfs) float32.

        Large batches are split over nproc forked workers, each with single-thread BLAS and
        FFT: on a shared machine this is much faster than threaded transforms.
        """
        global _POOL_OPT
        nb = b.shape[0]
        self._modes32 = self.modes.astype(np.float32)
        if nproc <= 1 or nb < 4 * block:
            return self._forward_modes(b, want_wfs)
        psf = np.empty((nb, self.npsf), np.float32)
        wfs = np.empty((nb, self.nwfs), np.float32) if want_wfs else None
        starts = range(0, nb, block)
        _POOL_OPT = self
        try:
            with mp.get_context("fork").Pool(nproc, initializer=_single_thread_blas) as pool:
                jobs = ((b[i : i + block], want_wfs) for i in starts)
                for i, (p, w) in zip(starts, pool.imap(_forward_block, jobs)):
                    psf[i : i + block] = p
                    if want_wfs:
                        wfs[i : i + block] = w
        finally:
            _POOL_OPT = None
        return psf, wfs

    def _crop_field(self, x):
        """Pupil-plane arrays (B, npup), without the pupil amplitude -> focal samples of the
        PSF field (B, nsamp), normalised so that their squared modulus is the flux fraction."""
        e = np.zeros((x.shape[0], self.npb * self.npb), np.complex128)
        e[:, self.pidx] = x * self.pamp
        f = np.matmul(np.matmul(self._mft64, e.reshape(-1, self.npb, self.npb)), self._mft64.T)
        return f.reshape(len(x), -1) * np.sqrt(self.psf_norm)

    def _binpix(self, i):
        """Sum focal samples (..., nsamp) into detector pixels (..., npsf)."""
        if self.psf_bin == 1:
            return i
        m, b = self.nside, self.psf_bin
        return i.reshape(i.shape[:-1] + (m, b, m, b)).sum((-3, -1)).reshape(i.shape[:-1] + (-1,))

    def taylor(self, k):
        """Second-order expansion of the PSF in the first k modes (coefficients b in rad).

        field(u) = e0 + i sum_k b_k M_k - 0.5 sum_kl b_k b_l Q_kl + O(b^3), hence
        psf(u) = c0 + sum_k g_k b_k + sum_kl (hs_kl + hp_kl) b_k b_l + O(b^3) with
        g_k = -2 Im(e0* M_k), hs_kl = Re(M_k M_l*) (speckle term, two squared channels) and
        hp_kl = -Re(e0* Q_kl) (interference of the unaberrated field with the 2nd-order field).
        Returns dict with c0 (npsf,), g (k, npsf), hs, hp (k, k, npsf) and the complex focal
        samples e0 (nsamp,), m (k, nsamp).
        """
        e0 = self._crop_field(np.ones((1, self.npup)))[0]
        mk = self._crop_field(self.modes[:k])
        c0 = self._binpix(np.abs(e0) ** 2)
        g = self._binpix(-2.0 * np.imag(np.conj(e0)[None] * mk))
        hs = np.empty((k, k, self.npsf), np.float32)
        hp = np.empty((k, k, self.npsf), np.float32)
        for i in range(k):
            hs[i] = self._binpix(np.real(mk[i][None] * np.conj(mk)))
            q = self._crop_field(self.modes[i][None] * self.modes[:k])
            hp[i] = self._binpix(-np.real(np.conj(e0)[None] * q))
        return dict(c0=c0, g=g, hs=hs, hp=hp, e0=e0, m=mk)


def mode_sigmas(k, total_rms, gamma=5.0 / 6.0):
    """Per-mode RMS [rad]: variance ~ (index+1)^-gamma, total RMS = total_rms."""
    v = (np.arange(k) + 1.0) ** (-gamma)
    return total_rms * np.sqrt(v / v.sum())


def ar2_series(nsteps, sig, tau, rng):
    """Smooth stationary Gaussian series (nsteps, K): two cascaded AR(1) stages per mode.

    sig: per-mode RMS; tau: per-mode e-folding time of each stage, in steps.
    """
    sig, tau = np.asarray(sig, float), np.asarray(tau, float)
    burn = int(30 * tau.max())
    out = np.empty((nsteps, sig.size), np.float32)
    for i in range(sig.size):
        rho = np.exp(-1.0 / tau[i])
        e = rng.standard_normal(nsteps + burn)
        y = lfilter([1.0], [1.0, -2.0 * rho, rho * rho], e)[burn:]
        out[:, i] = y * sig[i] * np.sqrt((1.0 - rho**2) ** 3 / (1.0 + rho**2))
    return out


def add_photon_noise(x, nphot, rng, read=0.0):
    """Gaussian approximation of photon noise for images in flux-fraction units."""
    if nphot is None:
        return x
    v = np.maximum(x, 0) / nphot + (read / nphot) ** 2
    return x + np.sqrt(v) * rng.standard_normal(x.shape, dtype=np.float32)


def selftest():
    """Taylor expansion against the exact PSF (the error must scale as amplitude^3), and the
    pupil sampling against a four times finer one."""
    rng = np.random.default_rng(1)
    for pbin, half in ((1, 36), (2, 69)):
        o = Optics(kmodes=20, psf_half=half, psf_bin=pbin)
        t = o.taylor(20)
        d = rng.standard_normal((4, 20))
        d /= np.sqrt((d**2).sum(1, keepdims=True))
        errs = []
        for amp in (0.02, 0.04, 0.08):
            b = amp * d
            psf, _ = o.forward(b, want_wfs=False)
            h = (t["hs"] + t["hp"]).astype(np.float64)
            quad = np.einsum("nk,nl,klp->np", b, b, h)
            lin = t["c0"][None] + b @ t["g"]
            e1 = np.abs(psf - lin).max() / t["c0"].max()
            e2 = np.abs(psf - lin - quad).max() / t["c0"].max()
            errs.append((amp, e1, e2))
        print(f"bin={pbin}: npup={o.npup} npsf={o.npsf} nwfs={o.nwfs} peak={t['c0'].max():.4f}")
        for amp, e1, e2 in errs:
            print(f"   amp={amp:.2f} rad  err(1st order)={e1:.2e}  err(2nd order)={e2:.2e}")
        r1 = errs[1][2] / errs[0][2]
        r2 = errs[2][2] / errs[1][2]
        print(f"   2nd-order error ratios for 2x amplitude: {r1:.2f}, {r2:.2f} (expect ~8)")
    o = Optics(kmodes=20)
    psf0, w0 = o.forward(np.zeros((1, 20)))
    print(f"pyramid: flux in selected pixels (flat WF) = {w0.sum():.3f} of total; "
          f"PSF flux in the +-{o.psf_half / o.ld:g} l/D field = {psf0.sum():.3f}")
    ref = Optics(dpix=4 * o.dpix, kmodes=0)
    ref.modes = np.zeros((1, ref.npup))
    pref, _ = ref.forward(np.zeros((1, 1)), want_wfs=False)
    rel = np.abs(psf0[0] - pref[0]) / pref[0]
    for lo, hi in ((0, 4), (4, 8), (8, 11.5)):
        m = (o.psf_r >= lo) & (o.psf_r < hi)
        print(f"   unaberrated PSF vs a {ref.dpix}-pixel pupil, {lo}-{hi} l/D: median "
              f"{np.median(rel[m]):.4f}, 95th percentile {np.percentile(rel[m], 95):.4f}")


if __name__ == "__main__":
    selftest()
