# WFS to PSF Hessian model: algorithm and toy validation

Stand-alone study, 2026-11-20. Question: can an algorithm watch a wavefront sensor (WFS) stream
and a focal-plane (PSF) stream, synchronise them, and fit the quadratic ("Hessian") relation
between the two, after PCA on both sides? This directory holds the algorithm (`hessmodel.py`), a
toy simulator (`toysim.py`), the experiments and their results. Monochromatic light, no DM, no
coronagraph, wavefronts drawn directly (no AO loop). Nothing here touches milk shared memory.

All numbers below come from the runs logged in `out/`; `summary.py` prints every table.
R2 is the fraction of the frame-to-frame PSF variance explained on held-out frames, scored
against the noiseless PSF. Zones are distances from the PSF centre in lambda/D.

## 1. Findings

1. **The concept holds for small aberrations.** At 0.3 rad RMS over 80 modes, a degree-2
   polynomial of the WFS modes explains 95 to 99.9% of the frame-to-frame PSF variance on
   held-out frames, against 56 to 96% for a linear map (fig. 1). PCA modes of a pyramid WFS do as
   well as the true modal coefficients. The fitted coefficients match the analytic second-order
   expansion of the PSF (2.7% at 0.1 rad).
2. **It is a small-aberration model.** In the halo, R2 falls to 0.8-0.9 at 0.5 rad and to
   0.5-0.8 at 0.7 rad (fig. 2). Least squares returns the gradient and Hessian averaged over
   the wavefront distribution, which are the analytic ones times `exp(-rms^2)`.
3. **Two channels, plus a term that is not small without a coronagraph.** Each pixel's Hessian
   has two dominant positive eigen-directions, the real and imaginary parts of the speckle field,
   and passive data recover them (fig. 4). It also has a full-rank signed part, 44 to 78% of the
   speckle part in norm: the unaberrated field interfering with the second-order scattered
   field. So of the three models, two squared affine channels are the weakest (R2 0.87 to 0.94
   in the halo at 0.3 rad), the Hessian polynomial is in the middle (0.96 to 0.98), and two
   squared channels that are each a degree-2 polynomial of the modes, i.e. the field to second
   order, are the best and hold further out in amplitude: 0.99 at 0.3 rad, and 0.93 to 0.98 at
   0.5 rad where the polynomial gives 0.81 to 0.88 (fig. 5). The signed part scales with the
   unaberrated field, so a coronagraph should remove most of it; that is not tested here.
4. **WFS noise is the weak point.** Noise of relative variance `s2` per mode shrinks the fitted
   Hessian by exactly `1/(1 + s2)` and costs R2 fast: `s2 = 0.1` loses 10 points, `s2 = 1`
   leaves 0.37 to 0.48. Smoothing the modes in time before forming the products recovers much
   of it in a time-series test (0.41 to 0.48 becomes 0.74 to 0.86 at `s2 = 1`).
5. **Keep every excited WFS mode; PCA rank is not relevance.** PCA orders modes by WFS variance
   and the modulated pyramid senses low orders least, so dropping the 20 weakest of 80 PCA modes
   takes R2 in the core from 0.999 to 0.56. On the PSF side, PCA needs 400 to 800 modes for 2209
   pixels: it saves memory, not much else.
6. **Data volume.** About 6 frames per coefficient, i.e. `6 (K+1)(K+2)/2` PSF frames (20 000 for
   80 modes), whatever the number of PSF pixels. A cheaper estimator that uses only
   cross-moments needs about ten times more.
7. **Synchronisation comes from the model itself.** Averaging the quadratic features, not the
   modes, over each PSF exposure keeps the model exact for a camera slower than the WFS.
   Scanning the lag and taking the centre of the peak of the model's own held-out R2 recovers it
   to about 0.01 WFS frame for exposures of 1 and 4 WFS frames (0.03 to 0.11 frame early at 16),
   also from the purely quadratic part of the relation. Timing matters: one WFS frame of error
   costs 11 points of R2 for a PSF camera at the WFS rate (fig. 6).
8. **Implementation.** The fit is a streaming accumulation of normal equations: 0.26 ms per PSF
   frame and 147 MB for 80 modes and 2209 pixels, 0.7 s to solve (6 threads). The coefficient
   count grows as `K^2/2`, so a system with hundreds of sensed modes needs a structured model
   (channels) rather than a free Hessian per pixel (section 6).

## 2. Model

Wavefront `phi = sum_k b_k m_k` on the pupil `P` (modes `m_k`, coefficients `b_k` in rad). With
`E0 = FT[P]`, `M_k = FT[P m_k]`, `Q_kl = FT[P m_k m_l]`, the focal-plane field at point `u` is

    E(u) = E0 + i sum_k b_k M_k - (1/2) sum_kl b_k b_l Q_kl + O(b^3)

and the PSF `I = |E|^2 = (Re E)^2 + (Im E)^2` is, to second order,

    I(u) = c + sum_k g_k b_k + sum_kl (S_kl + T_kl) b_k b_l + O(b^3)

| term | expression | meaning |
|---|---|---|
| `c` | `abs(E0)^2` | unaberrated PSF |
| `g_k` | `-2 Im(E0* M_k)` | pinned speckles, first order; odd in `u` for a symmetric pupil |
| `S_kl` | `Re(M_k M_l*)` | speckle term: rank 2, positive: the two channels (Re and Im) |
| `T_kl` | `-Re(E0* Q_kl)` | unaberrated field times second-order field: full rank, signed |

`T` is what makes the Strehl ratio drop: at the PSF peak `S = 0` and `T = -identity`, so
`I(0) = 1 - sum b_k^2`. It vanishes where `E0` does, which is what a coronagraph arranges.

"Incoherent sum of two quadratic channels" can be read two ways, and the toy tests both:

- **Affine channels** (`aff2`): the field is affine in the modes, each channel's intensity is the
  square of an affine function. This carries `c`, `g` and `S`, not `T`.
- **Quadratic channels** (`quad2`): `Re E` and `Im E` are each a degree-2 polynomial of the
  modes and the PSF is the sum of their squares. This carries `c`, `g`, `S`, `T` and the cubic and
  quartic terms that go with them.

The plain **Hessian model** (`poly2`) sits in between: `I = c + g.a + a^T H a` with a free
symmetric `H` per pixel. It is exact to second order and has nothing beyond. It is the only one
of the three that is linear in its parameters, so it is the one the streaming algorithm fits.

The WFS modes `a` are (to first order) an invertible linear map of the sensed `b`, so the model
class is the same in WFS-mode coordinates. Polychromatic light adds two channels per wavelength;
detector pixels wider than a field sample add weak extra channels (measured below).

## 3. Algorithm

Implemented in `hessmodel.py`:

1. **WFS modes.** Photon-noise-weighted PCA of the WFS frames (pixel weights `1/sqrt(mean)`),
   keep `K` modes, whiten: `a(t)`.
2. **PSF outputs.** PSF pixels, or PSF PCA coefficients. Least squares is separable across
   outputs, so PCA on the PSF side changes cost and memory, not the fit.
3. **Features.** `z(a) = [1, a_k, (a_k^2 - 1)/sqrt(2), a_k a_l (k<l)]`, `F = (K+1)(K+2)/2`
   numbers per WFS frame, orthonormal for white Gaussian modes.
4. **Exposure averaging.** The model is linear in `z`, so a PSF frame exposed over `[t0, t1)`
   obeys it exactly with `z` replaced by its mean over that window, fractional WFS frames at the
   ends included. `FrameFeatures` keeps the running integral of `z`, so any window costs two
   look-ups. Averaging the modes first and squaring afterwards is not equivalent.
5. **Synchronisation.** For a trial lag `tau` (PSF lags WFS; same sign convention as
   `milk-mltools`), average the features over `[t0 - tau, t1 - tau)`, fit a small set of outputs,
   and record the held-out R2. The lag is the centre of symmetry of the R2 peak (`find_lag`).
6. **Accumulate and solve.** `G += z z^T`, `R += z y^T` (`QuadFit`), then
   `Theta = (G/n + ridge)^-1 R/n` by Cholesky. Memory is `F^2 + F J`, independent of the number of
   frames, so the same code runs as a monitor on live streams.
7. **Read out.** `unpack` gives `c(u)`, `g(u)`, `H(u)` per pixel; `eig_desc` gives the channels.

## 4. Toy simulation

`toysim.py`, pure numpy/scipy:

- Circular pupil, 32 pixels across in a 128 x 128 array (4 focal samples per lambda/D).
- 80 Kolmogorov Karhunen-Loeve modes; modal variances proportional to `(index)^(-5/6)`,
  roughly the spectrum of a servo-lag residual; total RMS set per run (0.3 rad in the
  reference case).
- PSF: one FFT, 2 x 2 samples summed per detector pixel (2 pixels per lambda/D), 47 x 47 pixels,
  field +-11.75 lambda/D. Checked against its analytic second-order expansion (`selftest`).
- WFS: pyramid from the same focal-plane field, field stop +-8 lambda/D, modulation 3 lambda/D
  on 16 points, 4 pupil images of 16 pixels diameter (912 pixels), optional photon noise.
- "True modes" (oracle WFS) means the whitened modal coefficients themselves are used as `a`.

Reference case: 0.3 rad RMS, 200 000 independent training frames, 10 000 test frames.

## 5. Results

### 5.1 Concept check

![model quality](fig1_model_quality.png)

Reference case, R2 per zone:

| model | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| linear in the true modes | 0.964 | 0.812 | 0.560 | 0.783 |
| Hessian, true modes | 0.999 | 0.987 | 0.954 | 0.967 |
| Hessian, pyramid PCA modes (K = 80, noiseless) | 0.999 | 0.987 | 0.954 | 0.967 |

The linear part is large here only because there is no coronagraph: it is the pinned-speckle
term `g`, proportional to the unaberrated field. The implementation is validated against the
analytic expansion: at 0.1 rad the fitted Hessians match it to 2.7% (median relative error over
1.25-8 lambda/D), with R2 of 0.999 or better in every zone.

### 5.2 Wavefront amplitude

![amplitude scan](fig2_amplitude.png)

100 000 training frames per point (200 000 at 0.3 rad), true modes, R2 as
core / 1.25-4 / 4-8 / >8:

| WF RMS [rad] | Hessian model | linear model | H fitted / H analytic | exp(-rms^2) |
|---|---|---|---:|---:|
| 0.1 | 1.000 / 1.000 / 0.999 / 1.000 | 0.996 / 0.977 / 0.927 / 0.973 | 0.989 | 0.990 |
| 0.2 | 1.000 / 0.997 / 0.988 / 0.993 | 0.984 / 0.910 / 0.751 / 0.897 | 0.957 | 0.961 |
| 0.3 | 0.999 / 0.987 / 0.954 / 0.967 | 0.964 / 0.812 / 0.560 / 0.783 | 0.906 | 0.914 |
| 0.5 | 0.992 / 0.919 / 0.802 / 0.800 | 0.905 / 0.571 / 0.272 / 0.503 | 0.760 | 0.779 |
| 0.7 | 0.971 / 0.780 / 0.599 / 0.517 | 0.820 / 0.355 / 0.132 / 0.271 | 0.587 | 0.613 |
| 1.0 | 0.896 / 0.509 / 0.324 / 0.242 | 0.656 / 0.155 / 0.057 / 0.117 | 0.346 | 0.368 |
| 1.5 | 0.635 / 0.180 / 0.093 / 0.146 | 0.365 / 0.052 / 0.037 / 0.067 | 0.103 | 0.105 |

- The degree-2 model is a small-aberration model: above 0.95 everywhere up to 0.3 rad, 0.8 to
  0.9 in the halo at 0.5 rad, 0.5 to 0.8 at 0.7 rad.
- The fitted Hessian is not the Taylor Hessian at zero aberration: least squares returns the
  Hessian averaged over the wavefront distribution. Its component along the analytic Hessian is
  `exp(-rms^2)` of it (within 2.5% at every amplitude, last two columns; the fitted gradient
  `g` scales the same way), and what is left over grows from 2% of the norm at 0.1 rad to 7% at
  0.3 rad, 19% at 0.5 rad and 68% at 1 rad. A model learned at one residual level is therefore
  not valid at another without at least a rescaling.
- The pyramid is not what limits the model. With noiseless pyramid PCA modes the R2 values equal
  the true-mode ones to within 0.01 up to 0.7 rad and within 0.03 at 1 rad, and the pyramid
  modes stay linear in the wavefront (median R2 0.9997 at 0.3 rad, 0.988 at 1 rad). One
  modulation setting only.

### 5.3 What the fit needs

![requirements](fig3_requirements.png)

**Frames.** With `F = 3321` coefficients per PSF pixel (K = 80), R2 as
core / 1.25-4 / 4-8 / >8:

| training frames | least squares | cross-moments only |
|---:|---|---|
| 2 000 | fails (fewer frames than coefficients) | fails |
| 5 000 | 0.997 / 0.960 / 0.863 / 0.903 | 0.320 / 0.294 / 0.257 / 0.281 |
| 10 000 | 0.998 / 0.980 / 0.930 / 0.950 | 0.658 / 0.642 / 0.603 / 0.623 |
| 20 000 | 0.999 / 0.984 / 0.945 / 0.961 | 0.822 / 0.813 / 0.777 / 0.795 |
| 50 000 | 0.999 / 0.986 / 0.951 / 0.965 | 0.932 / 0.918 / 0.884 / 0.899 |
| 200 000 | 0.999 / 0.987 / 0.954 / 0.967 | 0.982 / 0.969 / 0.937 / 0.951 |

Least squares is within 0.01 of its asymptote at about 6 F frames. "Cross-moments only" is
the cheap estimator `Theta = <z (y - mean y)>`, which needs no `F x F` matrix (it is exact in
expectation for white Gaussian modes); it needs roughly ten times more frames, because its error
scales with the total PSF variance instead of the unexplained part.

**WFS noise.** White noise of variance `s2` (relative to the signal) on each true mode:

| s2 | Hessian R2 | linear R2 | H fitted / H analytic | 0.906 / (1 + s2) |
|---:|---|---|---:|---:|
| 0.1 | 0.902 / 0.881 / 0.832 / 0.862 | 0.875 / 0.738 / 0.509 / 0.712 | 0.823 | 0.823 |
| 0.3 | 0.759 / 0.723 / 0.657 / 0.706 | 0.743 / 0.624 / 0.430 / 0.602 | 0.696 | 0.697 |
| 1 | 0.484 / 0.440 / 0.367 / 0.430 | 0.483 / 0.405 / 0.280 / 0.393 | 0.452 | 0.453 |
| 3 | 0.235 / 0.198 / 0.149 / 0.195 | 0.242 / 0.199 / 0.138 / 0.195 | 0.225 | 0.226 |

- The fitted Hessian shrinks by exactly `1/(1 + s2)` (errors in variables): what the data give
  is the best predictor of the PSF from the noisy WFS, not the optical Hessian. Recovering the
  optical one requires the WFS noise variance per mode.
- The prediction is more fragile than a linear one: a noise variance of 10% of the signal
  already costs 10 to 12 points of R2, because the quadratic terms lose `1/(1 + s2)^2`.
- The pyramid with photon noise behaves like the true modes with the equivalent `s2`:

| photons per WFS frame | equivalent s2 | Hessian R2 |
|---:|---:|---|
| 1e6 | 0.003 | 0.995 / 0.983 / 0.950 / 0.963 |
| 1e5 | 0.031 | 0.957 / 0.948 / 0.912 / 0.929 |
| 1e4 | 0.315 | 0.696 / 0.701 / 0.650 / 0.688 |
| 1e3 | 3.3 | 0.176 / 0.183 / 0.145 / 0.179 |

**Temporal smoothing recovers part of it.** In a time series (30 modes, time constants 1.5 to
5 WFS frames, PSF camera at the WFS rate, 60 000 frames, `exp_smooth.py`), smoothing the noisy
modes in time before forming the products gives:

| s2 | modes used in the features | R2 |
|---:|---|---|
| 0 | noiseless | 0.998 / 0.980 / 0.955 / 0.980 |
| 0.3 | noisy, as they are | 0.755 / 0.715 / 0.689 / 0.720 |
| 0.3 | Gaussian kernel, sigma 2 frames (best) | 0.934 / 0.886 / 0.831 / 0.884 |
| 0.3 | Wiener smoother | 0.935 / 0.893 / 0.853 / 0.894 |
| 1 | noisy, as they are | 0.482 / 0.431 / 0.414 / 0.442 |
| 1 | Gaussian kernel, sigma 3 frames (best) | 0.861 / 0.770 / 0.699 / 0.774 |
| 1 | Wiener smoother | 0.863 / 0.785 / 0.736 / 0.793 |
| 3 | noisy, as they are | 0.234 / 0.199 / 0.189 / 0.210 |
| 3 | Gaussian kernel, sigma 3 frames (best) | 0.692 / 0.595 / 0.525 / 0.605 |
| 3 | Wiener smoother | 0.707 / 0.601 / 0.540 / 0.617 |

The Wiener smoother is built from the noisy modes alone: the noise is white in time and the
wavefront is not, so the noise variance is the step of each mode's autocovariance at lag zero
(recovered within 3% here). The same estimate is what the Hessian debiasing above needs. How
much smoothing can recover depends on the ratio of the wavefront correlation time to the WFS
frame time, which this toy sets arbitrarily.

**PSF photon noise** only slows convergence (the fit stays unbiased). With 1e6 photons per PSF
frame the result equals the noiseless one except beyond 8 lambda/D (0.958 against 0.967). With
1e4 photons per frame and 200 000 frames: 0.998 / 0.983 / 0.930 / 0.102; the outer zone,
at about 0.1 photon per pixel per frame, is not yet constrained.

**WFS modes kept.** All 80 excited modes are needed, and PCA order is the wrong order to cut in:

| K kept | true modes, by wavefront variance | pyramid PCA, by WFS variance |
|---:|---|---|
| 20 | 0.997 / 0.895 / 0.066 / 0.459 | 0.045 / 0.154 / 0.139 / 0.207 |
| 40 | 0.998 / 0.975 / 0.197 / 0.634 | 0.256 / 0.255 / 0.394 / 0.322 |
| 60 | 0.999 / 0.985 / 0.648 / 0.791 | 0.564 / 0.704 / 0.681 / 0.602 |
| 80 | 0.999 / 0.987 / 0.954 / 0.967 | 0.999 / 0.987 / 0.954 / 0.967 |
| 120 | not run | 0.999 / 0.987 / 0.961 / 0.973 |

PCA ranks modes by their variance in the WFS image. The modulated pyramid is least sensitive to
the low-order modes, which carry the most wavefront variance and drive the PSF core, so they
come last: dropping the 20 weakest PCA modes loses even the core. Here the PCA spectrum has a
clear edge (eigenvalue 80 is 27 times eigenvalue 81), so "keep everything above the edge" is
well defined. The modes beyond 80 are the pyramid's own non-linear response; they add at most
0.007.

**PSF modes kept.** Fraction of the PSF variance retained by `J` PCA modes (of 2209 pixels):

| J | noise-weighted PCA | plain PCA |
|---:|---|---|
| 25 | 0.992 / 0.828 / 0.153 / 0.580 | 1.000 / 0.871 / 0.057 / 0.413 |
| 100 | 0.999 / 0.978 / 0.826 / 0.819 | 1.000 / 0.990 / 0.720 / 0.808 |
| 200 | 1.000 / 0.997 / 0.968 / 0.886 | 1.000 / 1.000 / 0.957 / 0.854 |
| 400 | 1.000 / 1.000 / 0.999 / 0.950 | 1.000 / 1.000 / 0.999 / 0.933 |
| 800 | 1.000 / 1.000 / 1.000 / 0.997 | 1.000 / 1.000 / 1.000 / 0.996 |

PCA compresses the PSF far less than the WFS: 80 wavefront modes give a PSF that needs 400 to
800 modes, because the PSF spans the pairwise products of the mode responses. Plain PCA puts
98% of the total variance in 10 modes, nearly all of it in and next to the core. On the PSF
side PCA is a memory saving (a factor 3 to 5 here), to be sized on the outer field.

### 5.4 Structure of the Hessians: the two channels

![channels](fig4_channels.png)

Per-pixel Hessians in whitened mode coordinates, where the eigenvalues squared are shares of
the PSF variance produced by the quadratic term. Medians per zone, reference case:

| quantity | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| share of the 2 largest positive eigenvalues, analytic `S` alone | 0.999 | 0.996 | 0.992 | 0.990 |
| same, analytic `S + T` | 0.860 | 0.852 | 0.726 | 0.654 |
| same, fitted from data | 0.856 | 0.861 | 0.717 | 0.654 |
| share of the negative eigenvalues, fitted | 0.124 | 0.077 | 0.138 | 0.237 |
| norm of `T` / norm of `S` | 0.487 | 0.441 | 0.659 | 0.776 |
| cosine of angle 1, fitted vs true channel plane | 0.992 | 0.999 | 0.995 | 0.966 |
| cosine of angle 2, fitted vs true channel plane | 0.990 | 0.998 | 0.967 | 0.795 |

- The speckle term `S` is two channels to better than 1%, even with detector pixels that sum
  2 x 2 field samples (with point samples it is exactly rank 2: 1.0000 in `bin1`).
- The term `T` is not small without a coronagraph: its norm is 44 to 78% of that of `S`, it is
  full rank and signed, and at the very centre the Hessian is negative definite (Strehl loss).
  Beyond the highest spatial frequency of the modes (about 6 lambda/D here) there are no
  first-order speckles and `T` dominates, which is the outer pattern in the maps.
- Passive data still recover the channel plane, i.e. the span of the real and imaginary parts of
  the field response `M_k(u)`: cosines above 0.97 inside 8 lambda/D (0.996 or better between
  1.25 and 6 lambda/D with point samples). The plane and its two eigenvalues give the field
  response up to one phase factor per pixel (and a complex conjugation).

**The three models fitted directly** (`exp_channels.py`). Median R2 over 36 pixels on two
radial cuts, true modes, 100 000 training frames:

![channel models](fig5_channel_models.png)

| WF RMS [rad] | model | core | 1.25-4 | 4-8 | >8 |
|---:|---|---:|---:|---:|---:|
| 0.3 | 2 squared affine channels | 0.976 | 0.935 | 0.908 | 0.865 |
| 0.3 | Hessian polynomial | 0.999 | 0.972 | 0.956 | 0.977 |
| 0.3 | 2 squared quadratic channels | 1.000 | 0.996 | 0.988 | 0.989 |
| 0.5 | 2 squared affine channels | 0.935 | 0.816 | 0.712 | 0.635 |
| 0.5 | Hessian polynomial | 0.994 | 0.877 | 0.809 | 0.855 |
| 0.5 | 2 squared quadratic channels | 0.997 | 0.975 | 0.936 | 0.931 |
| 0.7 | 2 squared affine channels | 0.871 | 0.630 | 0.420 | 0.406 |
| 0.7 | Hessian polynomial | 0.977 | 0.716 | 0.573 | 0.592 |
| 0.7 | 2 squared quadratic channels | 0.990 | 0.918 | 0.785 | 0.769 |
| 1.0 | 2 squared affine channels | 0.717 | 0.313 | 0.164 | 0.168 |
| 1.0 | Hessian polynomial | 0.913 | 0.442 | 0.260 | 0.241 |
| 1.0 | 2 squared quadratic channels | 0.960 | 0.726 | 0.423 | 0.285 |

- Two squared affine channels are the weakest of the three. A sum of squares of affine
  functions has a positive Hessian, so it cannot hold `T`: not the loss of light in the core,
  not the signed part elsewhere. Truncating each fitted Hessian of the reference case to its
  two positive channels gives the same picture: 0.685 / 0.941 / 0.919 / 0.784, against
  0.999 / 0.987 / 0.954 / 0.967 for the full Hessian (`exp_iid.py extra`).
- Two squared quadratic channels are the best, and the margin grows with the aberration. At
  0.5 rad they leave 2.5 to 7% of the halo variance unexplained where the Hessian polynomial
  leaves 12 to 19%; at 0.7 rad, 8 to 23% against 28 to 43%. This is the reading of "two
  quadratic channels" that matches the optics: the field to second order in the modes.
- The price: twice the coefficients of the Hessian polynomial (6642 per pixel here), a
  non-convex fit started from the Hessian solution (5 to 6 minutes for 36 pixels), no streaming
  form, and a gap between training and held-out error that grows with amplitude (unexplained
  0.13 against 0.17 at 0.7 rad, 0.40 against 0.54 at 1 rad).
- `T` and `g` scale with the unaberrated field `E0`. Where a coronagraph removes it, the
  second-order model reduces to `S` alone: two squared channels linear in the modes, `2K`
  coefficients per pixel instead of `K^2/2`. That is the case this toy does not cover.

### 5.5 Synchronisation and exposure time

Time series (`exp_sync.py`): 30 modes, 0.3 rad RMS, each mode a smooth stationary process with
time constants from 5 (first mode) to 1.5 WFS frames (last), 96 000 WFS frames. A pyramid frame
integrates over the WFS frame (1e6 photons); PCA gives the 30 modes. A PSF frame integrates
over 1, 4 or 16 WFS frames, starts at an arbitrary sub-frame time and is stamped with an
offset, the lag to recover (0, 2.25, -3.5 and 5.75 WFS frames were tried).

![synchronisation](fig6_sync.png)

**Lag recovery.** Trial lags are scored by the held-out R2 of 20 PSF PCA modes. Sync models:
`lin`, the linear terms of the 30 modes; `quad`, the full Hessian model; `qonly`, the quadratic
terms only, predicting the point-symmetric part of the PSF, `(I(u) + I(-u))/2`, which has no
linear term for a symmetric pupil (the situation behind a coronagraph); `lead12`, the full
model of the 12 highest-variance WFS modes. Errors in WFS frames:

| PSF exposure | sync model | R2 at peak | largest error, all frames | scatter, 1/8 of the frames |
|---:|---|---:|---:|---:|
| 1 | lin | 0.95 | 0.012 | 0.005 |
| 1 | quad | 1.00 | 0.013 | 0.008 |
| 1 | qonly | 0.99 | 0.013 | 0.005 |
| 4 | lin | 0.96 | 0.007 | 0.008 |
| 4 | quad | 1.00 | 0.007 | 0.016 |
| 4 | qonly | 1.00 | 0.012 | 0.011 |
| 16 | lin | 0.96 | 0.043 | 0.13 |
| 16 | quad | 1.00 | 0.051 | 0.49 |
| 16 | qonly | 1.00 | 0.113 | 0.21 |
| 1, 4, 16 | lead12 | 0.05 | not meaningful | 2.7 to 3.8 |

"All frames" is 96 000, 24 000 and 6 000 PSF frames for the three exposures (largest error
over the four true lags); the scatter is the RMS over eight disjoint eighths of the frames.

- For exposures of 1 and 4 WFS frames the lag is recovered to about 0.01 WFS frame from the
  linear terms, from the full model, and from the quadratic terms alone.
- At 16 frames per exposure all three read 0.03 to 0.11 frame early, by the same amount for the
  four true lags: a bias below 1% of the exposure, not investigated. With 750 PSF frames the
  496-coefficient models are under-determined and their scatter is large; the linear model
  (31 coefficients) still gives 0.13 frame.
- PSF photon noise (1e4 photons per frame, true lag 2.25) changes little for `lin` and `quad`
  (`quad` errors 0.013, 0.007 and -0.085 frame for the three exposures); `qonly` degrades most
  (0.009, 0.034 and -0.353).
- `lead12` fails: the 12 highest-variance WFS modes explain 5% of the PSF modes. A reduced sync
  model has to be chosen by relevance to the PSF, as in 5.3.
- The peak of R2 against lag is not a smooth maximum (boxcar exposures give a cusp, and for
  short exposures interpolating between two noisy WFS frames splits the top in two), so
  `find_lag` returns the centre of symmetry of the peak, not its highest point.

**Pairing WFS features with PSF frames.** Full model (496 coefficients per pixel), lag known,
PSF exposures starting half a WFS frame after a WFS frame boundary. R2 in the 4-8 lambda/D zone
(the other zones behave alike, see `summary.py`):

| pairing | exposure 1 | exposure 4 | exposure 16 |
|---|---:|---:|---:|
| features averaged over the exposure, exact timing | 0.951 | 0.960 | 0.969 |
| features of the exposure-averaged modes | 0.951 | 0.957 | 0.931 |
| nearest whole WFS frame | 0.918 | | |
| timing error 0.25 frame | 0.943 | 0.955 | 0.968 |
| timing error 0.5 frame | 0.918 | 0.943 | 0.965 |
| timing error 1 frame | 0.843 | 0.897 | 0.954 |
| timing error 2 frames | 0.629 | 0.742 | 0.911 |
| timing error 4 frames | 0.304 | 0.396 | 0.764 |
| linear model, exact timing | 0.733 | 0.753 | 0.800 |

- Averaging the features over the exposure keeps the model valid for a slow camera: R2 does
  not fall with the exposure length. Squaring the averaged modes instead costs nothing at 1
  frame, 0.3 point at 4 frames and 4 points at 16 frames; the loss grows with the exposure
  counted in wavefront correlation times.
- Timing matters at the sub-frame level for short exposures: at the WFS frame rate half a frame
  costs 3 points of R2, one frame 11 points, two frames 32 points. Pairing each PSF frame with
  the nearest whole WFS frame is a half-frame error here.

## 6. Not tested, and limits of the toy

- **Every wavefront mode is sensed.** Real residuals have unsensed and aliased content, which
  adds an unexplained floor and acts as noise in the fit. All R2 values here are upper bounds.
- **Statistics.** Independent Gaussian draws for sections 5.1 to 5.4; a smooth stationary
  process per mode, with no correlation between modes, for 5.5. No frozen flow, no closed loop.
- **Optics.** No DM, no coronagraph, one wavelength, no static or drifting aberration, no
  detector read noise, one pyramid setting. The term `T` and the linear term `g` both scale with
  the unaberrated field, so the balance between the terms will be different behind a coronagraph.
- **Monitoring.** The accumulators are streaming, but tracking a drifting system (a forgetting
  factor on `G` and `R`) was not exercised.
- **Scale.** 80 modes give 3321 coefficients per pixel. The count grows as `K^2/2`: 500 modes
  would mean 125 751 coefficients per pixel, a 126 GB normal matrix and of order a million
  frames. At that size the unconstrained per-pixel Hessian is not the right parametrisation;
  the channel models of 5.4, or restricting each pixel to the modes that can reach it, are the
  candidates. Neither was tested at scale.
- **Channel fits** (5.4) use the true modes, 36 pixels on two radial cuts and 300 L-BFGS
  iterations; they are not a streaming algorithm.

## 7. Porting notes (milk-mltools)

These scripts are the experiment and the numerical reference. A deployed version belongs in the
milk framework (calc operators, compute units) and `milk-mltools`, not in new Python. What
exists there already, read on 2026-11-20 (nothing was run or changed):

- The lag sign convention used here is the one of `mlt.tlmsync` / `mlt.latency`
  (`tau > 0`: stream B, the PSF, lags stream A, the WFS).
- `mlt.pca` covers step 1 (divide the frames by `sqrt(mean)` first for the noise weighting).
- `mlt.tlmsync` mode `expint` averages a stream over a window of width `texp` at a trial lag.
  Applied to the **feature** stream `z(a(t))` rather than to the modes, it is step 4.
- `mlt.latency` (linear PCA subspaces, AR whitening, cross-correlation) is the linear version of
  step 5. It should be enough whenever the linear PSF response is strong (no coronagraph).
- Missing pieces: the quadratic feature expansion, and the normal-equation accumulator and
  solver (`mlt.sysid` is linear in the streams).
- Telemetry time stamps mark the end of the exposure and the exposure time is not recorded
  (`milk-streamtelemetry-scan/TelemetryFormat.md`), so the window of a PSF frame stamped `t` is
  `[t - T_exp - tau, t - tau)` with `T_exp` supplied by the user, or scanned like the lag.

## 8. Files

| file | content |
|---|---|
| `toysim.py` | pupil, KL modes, PSF and pyramid forward model, analytic expansion, self-test |
| `hessmodel.py` | PCA, features, streaming fit, lag search, channel tools |
| `exp_iid.py` | independent-frame experiments: `ref`, `extra`, `amp`, `bin1` |
| `exp_channels.py` | two-channel models fitted by L-BFGS on a radial cut of pixels |
| `exp_sync.py` | time series, slower PSF camera, lag recovery, pairing methods |
| `exp_smooth.py` | noisy WFS modes in a time series, with and without temporal smoothing |
| `test_hessmodel.py` | unit checks (run directly or with pytest) |
| `summary.py`, `figs.py` | tables and figures from `out/*.npz` |
| `commands.txt` | the commands that produced `out/` |
