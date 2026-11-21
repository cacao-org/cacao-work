
### Amplitude scan (R2 pooled per zone; zones in lambda/D)

| WF RMS [rad] | Hessian core | Hessian 1.25-4 | Hessian 4-8 | Hessian >8 | linear core | linear 1.25-4 | linear 4-8 | linear >8 | H fit / H Taylor | exp(-s^2) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.1 | 1.000 | 1.000 | 0.999 | 0.999 | 0.996 | 0.976 | 0.928 | 0.971 | 0.989 | 0.990 |
| 0.2 | 1.000 | 0.997 | 0.988 | 0.991 | 0.984 | 0.907 | 0.755 | 0.888 | 0.956 | 0.961 |
| 0.3 | 0.999 | 0.986 | 0.953 | 0.959 | 0.964 | 0.805 | 0.563 | 0.765 | 0.905 | 0.914 |
| 0.5 | 0.992 | 0.916 | 0.800 | 0.765 | 0.904 | 0.561 | 0.272 | 0.468 | 0.759 | 0.779 |
| 0.7 | 0.971 | 0.776 | 0.594 | 0.478 | 0.818 | 0.345 | 0.130 | 0.246 | 0.584 | 0.613 |
| 1 | 0.898 | 0.514 | 0.315 | 0.232 | 0.657 | 0.153 | 0.054 | 0.112 | 0.342 | 0.368 |
| 1.5 | 0.627 | 0.177 | 0.084 | 0.137 | 0.358 | 0.052 | 0.034 | 0.063 | 0.101 | 0.105 |

Pyramid PCA modes (K = 80, noiseless) versus true modes, Hessian model:

| WF RMS [rad] | pyramid core | pyramid 1.25-4 | pyramid 4-8 | pyramid >8 | WFS modes linear in WF (median R2) |
|---|---:|---:|---:|---:|---:|
| 0.1 | 1.0000 | 0.9998 | 0.9991 | 0.9994 | 1.0000 |
| 0.2 | 0.9997 | 0.9969 | 0.9877 | 0.9905 | 0.9999 |
| 0.3 | 0.9983 | 0.9859 | 0.9531 | 0.9583 | 0.9998 |
| 0.5 | 0.9882 | 0.9156 | 0.7990 | 0.7620 | 0.9993 |
| 0.7 | 0.9588 | 0.7743 | 0.5934 | 0.4735 | 0.9979 |
| 1 | 0.8738 | 0.5149 | 0.3172 | 0.2226 | 0.9944 |
| 1.5 | 0.6063 | 0.1906 | 0.0926 | 0.1176 | 0.9823 |

### Training frames (reference case, 3321 coefficients per pixel)

| frames | LS core | LS 1.25-4 | LS 4-8 | LS >8 | cross-moments core | cross-moments 1.25-4 | cross-moments 4-8 | cross-moments >8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000 | -16.563 | -0.667 | -0.116 | -1.613 | -0.682 | -0.733 | -0.824 | -0.743 |
| 5000 | 0.997 | 0.959 | 0.861 | 0.878 | 0.323 | 0.295 | 0.256 | 0.271 |
| 10000 | 0.998 | 0.979 | 0.929 | 0.937 | 0.657 | 0.641 | 0.604 | 0.616 |
| 20000 | 0.999 | 0.983 | 0.944 | 0.950 | 0.822 | 0.812 | 0.777 | 0.785 |
| 50000 | 0.999 | 0.985 | 0.950 | 0.956 | 0.932 | 0.917 | 0.884 | 0.891 |
| 100000 | 0.999 | 0.986 | 0.952 | 0.958 | 0.965 | 0.951 | 0.919 | 0.925 |
| 200000 | 0.999 | 0.986 | 0.953 | 0.959 | 0.982 | 0.969 | 0.937 | 0.942 |

### WFS noise on the true modes (variance ratio s2 per mode)

| s2 | Hessian core | Hessian 1.25-4 | Hessian 4-8 | Hessian >8 | linear core | linear 1.25-4 | linear 4-8 | linear >8 | H gain | expected H gain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.1 | 0.902 | 0.880 | 0.832 | 0.853 | 0.875 | 0.732 | 0.512 | 0.694 | 0.822 | 0.822 |
| 0.3 | 0.759 | 0.721 | 0.658 | 0.698 | 0.743 | 0.619 | 0.433 | 0.588 | 0.695 | 0.696 |
| 1 | 0.483 | 0.438 | 0.369 | 0.421 | 0.482 | 0.402 | 0.281 | 0.381 | 0.450 | 0.452 |
| 3 | 0.236 | 0.197 | 0.149 | 0.190 | 0.243 | 0.198 | 0.138 | 0.190 | 0.225 | 0.226 |

### Pyramid WFS with photon noise (PCA, K = 80)

| photons / WFS frame | equivalent s2 | Hessian core | Hessian 1.25-4 | Hessian 4-8 | Hessian >8 |
|---|---:|---:|---:|---:|---:|
| noiseless | 0.000 | 0.998 | 0.986 | 0.953 | 0.958 |
| 1e6 | 0.003 | 0.989 | 0.981 | 0.948 | 0.953 |
| 1e5 | 0.031 | 0.909 | 0.940 | 0.908 | 0.907 |
| 1e4 | 0.313 | 0.503 | 0.675 | 0.636 | 0.629 |
| 1e3 | 3.471 | 0.032 | 0.149 | 0.129 | 0.129 |

### PSF photon noise (true modes; scored against noiseless PSFs)

| photons / PSF frame, frames | Hessian core | Hessian 1.25-4 | Hessian 4-8 | Hessian >8 |
|---|---:|---:|---:|---:|
| 1e+06, 20000 | 0.998 | 0.982 | 0.938 | 0.726 |
| 1e+06, 200000 | 0.999 | 0.986 | 0.953 | 0.940 |
| 10000, 20000 | 0.979 | 0.900 | 0.372 | -21.414 |
| 10000, 200000 | 0.997 | 0.979 | 0.905 | -0.915 |

### WFS modes kept

| K | true modes core | true modes 1.25-4 | true modes 4-8 | true modes >8 |
|---|---:|---:|---:|---:|
| 10 | 0.995 | 0.707 | 0.045 | 0.300 |
| 20 | 0.997 | 0.896 | 0.073 | 0.409 |
| 40 | 0.998 | 0.974 | 0.205 | 0.586 |
| 60 | 0.999 | 0.985 | 0.653 | 0.758 |
| 80 | 0.999 | 0.986 | 0.953 | 0.959 |

| K | pyramid PCA core | pyramid PCA 1.25-4 | pyramid PCA 4-8 | pyramid PCA >8 |
|---|---:|---:|---:|---:|
| 20 | 0.012 | 0.150 | 0.134 | 0.146 |
| 40 | 0.014 | 0.258 | 0.357 | 0.215 |
| 60 | 0.019 | 0.525 | 0.652 | 0.446 |
| 80 | 0.998 | 0.986 | 0.953 | 0.958 |
| 100 | 0.998 | 0.986 | 0.956 | 0.963 |
| 120 | 0.999 | 0.987 | 0.960 | 0.967 |

Pyramid PCA eigenvalues: ev1/ev80 = 9.6, ev80/ev81 = 11.9

### PSF PCA modes kept (variance of the true PSF retained)

| J | weighted core | weighted 1.25-4 | weighted 4-8 | weighted >8 | plain core | plain 1.25-4 | plain 4-8 | plain >8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.964 | 0.727 | 0.052 | 0.322 | 0.998 | 0.648 | 0.041 | 0.271 |
| 25 | 0.991 | 0.831 | 0.156 | 0.529 | 1.000 | 0.869 | 0.064 | 0.371 |
| 50 | 0.996 | 0.896 | 0.549 | 0.758 | 1.000 | 0.958 | 0.183 | 0.528 |
| 100 | 1.000 | 0.979 | 0.800 | 0.806 | 1.000 | 0.990 | 0.697 | 0.792 |
| 200 | 1.000 | 0.997 | 0.966 | 0.876 | 1.000 | 1.000 | 0.954 | 0.846 |
| 400 | 1.000 | 1.000 | 0.999 | 0.949 | 1.000 | 1.000 | 0.999 | 0.933 |
| 800 | 1.000 | 1.000 | 1.000 | 0.999 | 1.000 | 1.000 | 1.000 | 0.999 |
| 1600 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### Structure of the per-pixel Hessians (medians per zone)

| quantity | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| top-2 share, analytic speckle term | 1.000 | 0.999 | 0.999 | 0.999 |
| top-2 share, analytic full 2nd order | 0.851 | 0.859 | 0.716 | 0.498 |
| top-2 share, fitted | 0.846 | 0.860 | 0.707 | 0.495 |
| negative share, analytic | 0.128 | 0.084 | 0.160 | 0.342 |
| negative share, fitted | 0.134 | 0.079 | 0.138 | 0.315 |
| relative error fitted vs analytic H | 0.098 | 0.102 | 0.127 | 0.167 |
| relative error fitted vs analytic g | 0.088 | 0.102 | 0.118 | 0.139 |
| norm ratio pinned / speckle term | 0.524 | 0.419 | 0.674 | 0.969 |
| cos angle 1, fitted vs true channel plane | 0.988 | 0.999 | 0.996 | 0.910 |
| cos angle 2, fitted vs true channel plane | 0.980 | 0.999 | 0.962 | 0.621 |

### Truncating the fitted Hessians to channels (reference case)

| model | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| full Hessian | 0.999 | 0.986 | 0.953 | 0.959 |
| c + g.a + 1 positive channel(s) of H | 0.693 | 0.885 | 0.697 | 0.824 |
| c + g.a + 2 positive channel(s) of H | 0.691 | 0.938 | 0.917 | 0.822 |
| c + g.a + 4 positive channel(s) of H | 0.689 | 0.918 | 0.912 | 0.792 |
| c + g.a + 8 positive channel(s) of H | 0.687 | 0.891 | 0.888 | 0.706 |
| 1 squared affine channel(s) | 0.673 | 0.853 | 0.647 | 0.791 |
| 2 squared affine channel(s) | 0.672 | 0.938 | 0.909 | 0.813 |
| 4 squared affine channel(s) | 0.668 | 0.924 | 0.915 | 0.791 |
| 8 squared affine channel(s) | 0.666 | 0.895 | 0.893 | 0.704 |

### Unbinned PSF samples (6 per lambda/D), field +-6 lambda/D

| WF RMS, quantity | core | 1.25-4 | 4-8 |
|---|---:|---:|---:|
| 0.1, Hessian R2 | 1.000 | 1.000 | 0.999 |
| 0.1, top-2 share, analytic speckle term | 1.0000 | 1.0000 | 1.0000 |
| 0.1, top-2 share, analytic full | 0.8028 | 0.8550 | 0.8530 |
| 0.1, top-2 share, fitted | 0.8021 | 0.8546 | 0.8541 |
| 0.1, cos angle 2 fitted vs true plane | 0.956 | 0.999 | 0.997 |
| 0.3, Hessian R2 | 0.999 | 0.986 | 0.952 |
| 0.3, top-2 share, analytic speckle term | 1.0000 | 1.0000 | 1.0000 |
| 0.3, top-2 share, analytic full | 0.8028 | 0.8550 | 0.8530 |
| 0.3, top-2 share, fitted | 0.7960 | 0.8538 | 0.8581 |
| 0.3, cos angle 2 fitted vs true plane | 0.957 | 0.999 | 0.996 |

### Channel models on a radial cut of pixels (median R2 per zone, true modes)


WF RMS 0.3 rad:

| model | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| linear | 0.938 | 0.726 | 0.607 | 0.637 |
| 2 squared affine channels | 0.975 | 0.936 | 0.878 | 0.846 |
| degree-2 polynomial (Hessian) | 0.999 | 0.974 | 0.951 | 0.959 |
| 2 squared quadratic channels | 1.000 | 0.997 | 0.988 | 0.983 |

WF RMS 0.5 rad:

| model | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| linear | 0.860 | 0.464 | 0.304 | 0.367 |
| 2 squared affine channels | 0.930 | 0.817 | 0.671 | 0.533 |
| degree-2 polynomial (Hessian) | 0.994 | 0.872 | 0.765 | 0.796 |
| 2 squared quadratic channels | 0.998 | 0.980 | 0.922 | 0.904 |

WF RMS 0.7 rad:

| model | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| linear | 0.762 | 0.236 | 0.151 | 0.190 |
| 2 squared affine channels | 0.862 | 0.589 | 0.413 | 0.299 |
| degree-2 polynomial (Hessian) | 0.977 | 0.700 | 0.519 | 0.473 |
| 2 squared quadratic channels | 0.991 | 0.914 | 0.731 | 0.685 |

WF RMS 1 rad:

| model | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| linear | 0.607 | 0.102 | 0.069 | 0.128 |
| 2 squared affine channels | 0.708 | 0.316 | 0.170 | 0.174 |
| degree-2 polynomial (Hessian) | 0.914 | 0.419 | 0.242 | 0.229 |
| 2 squared quadratic channels | 0.966 | 0.731 | 0.458 | 0.260 |

### Noisy WFS modes in a time series, with temporal smoothing (R2 per zone)

| case | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| noiseless | 0.998 | 0.980 | 0.955 | 0.976 |
| s2=0.3, raw | 0.754 | 0.713 | 0.691 | 0.722 |
| s2=0.3, Gaussian sigma 2 frames | 0.934 | 0.885 | 0.833 | 0.879 |
| s2=0.3, Wiener | 0.935 | 0.892 | 0.853 | 0.890 |
| s2=1, raw | 0.480 | 0.430 | 0.414 | 0.444 |
| s2=1, Gaussian sigma 3 frames | 0.860 | 0.772 | 0.704 | 0.771 |
| s2=1, Wiener | 0.861 | 0.786 | 0.739 | 0.792 |
| s2=3, raw | 0.235 | 0.196 | 0.186 | 0.205 |
| s2=3, Gaussian sigma 3 frames | 0.693 | 0.592 | 0.523 | 0.591 |
| s2=3, Wiener | 0.709 | 0.598 | 0.540 | 0.605 |

### Lag recovery (errors in WFS frames)

| PSF exposure, model | max abs error, all frames | R2 at peak | mean error, 1/8 segments | scatter, 1/8 segments | PSF frames per segment | seconds per estimate |
|---|---:|---:|---:|---:|---:|---:|
| 1, lin | 0.012 | 0.948 | -0.001 | 0.008 | 11999.250 | 2.714 |
| 1, quad | 0.012 | 0.993 | 0.003 | 0.010 | 11999.250 | 55.843 |
| 1, qonly | 0.012 | 0.989 | -0.004 | 0.008 | 11999.250 | 52.671 |
| 1, lead12 | 0.172 | 0.004 | -0.114 | 5.000 | 11999.000 | 9.041 |
| 4, lin | 0.003 | 0.953 | -0.003 | 0.010 | 2999.250 | 0.716 |
| 4, quad | 0.004 | 0.997 | 0.003 | 0.015 | 2999.250 | 11.685 |
| 4, qonly | 0.006 | 0.994 | -0.006 | 0.017 | 2999.250 | 10.208 |
| 4, lead12 | 0.332 | 0.003 | -0.005 | 4.965 | 2999.000 | 1.840 |
| 16, lin | 0.047 | 0.963 | 0.008 | 0.128 | 749.250 | 0.148 |
| 16, quad | 0.050 | 0.998 | 0.167 | 0.472 | 749.250 | 2.413 |
| 16, qonly | 0.107 | 0.996 | -0.022 | 0.214 | 749.250 | 2.066 |
| 16, lead12 | 0.842 | -0.006 | -0.476 | 5.729 | 749.000 | 0.273 |

With PSF photon noise (1e4 photons per frame), true lag 2.25:

| PSF exposure, model | error, all frames | scatter, 1/8 segments |
|---|---:|---:|
| 1, lin | 0.008 | 0.012 |
| 1, quad | 0.007 | 0.011 |
| 1, qonly | -0.001 | 0.021 |
| 1, lead12 | -0.235 | 5.059 |
| 4, lin | 0.004 | 0.011 |
| 4, quad | 0.003 | 0.019 |
| 4, qonly | 0.008 | 0.064 |
| 4, lead12 | -0.351 | 4.965 |
| 16, lin | -0.037 | 0.107 |
| 16, quad | -0.047 | 0.505 |
| 16, qonly | -0.146 | 0.672 |
| 16, lead12 | -0.924 | 7.092 |

### Full model versus pairing of WFS features with PSF frames (R2 per zone)


PSF exposure = 1 WFS frame(s):

| pairing | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| exposure-averaged features | 0.994 | 0.977 | 0.950 | 0.972 |
| same, linear model | 0.950 | 0.763 | 0.737 | 0.825 |
| features of the averaged modes | 0.994 | 0.977 | 0.951 | 0.973 |
| nearest WFS frame | 0.982 | 0.955 | 0.918 | 0.949 |
| timing error 0.25 frame | 0.991 | 0.971 | 0.942 | 0.966 |
| timing error 0.5 frame | 0.982 | 0.955 | 0.918 | 0.949 |
| timing error 1 frame | 0.960 | 0.905 | 0.846 | 0.897 |
| timing error 2 frame | 0.873 | 0.745 | 0.638 | 0.733 |
| timing error 4 frame | 0.635 | 0.419 | 0.315 | 0.427 |

PSF exposure = 4 WFS frame(s):

| pairing | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| exposure-averaged features | 0.996 | 0.981 | 0.959 | 0.977 |
| same, linear model | 0.954 | 0.776 | 0.758 | 0.836 |
| features of the averaged modes | 0.996 | 0.980 | 0.957 | 0.976 |
| timing error 0.25 frame | 0.995 | 0.978 | 0.955 | 0.974 |
| timing error 0.5 frame | 0.990 | 0.968 | 0.943 | 0.965 |
| timing error 1 frame | 0.971 | 0.934 | 0.899 | 0.930 |
| timing error 2 frame | 0.899 | 0.812 | 0.747 | 0.809 |
| timing error 4 frame | 0.677 | 0.495 | 0.406 | 0.505 |

PSF exposure = 16 WFS frame(s):

| pairing | core | 1.25-4 | 4-8 | >8 |
|---|---:|---:|---:|---:|
| exposure-averaged features | 0.998 | 0.985 | 0.969 | 0.982 |
| same, linear model | 0.964 | 0.816 | 0.807 | 0.867 |
| features of the averaged modes | 0.995 | 0.957 | 0.933 | 0.966 |
| timing error 0.25 frame | 0.997 | 0.984 | 0.968 | 0.982 |
| timing error 0.5 frame | 0.995 | 0.982 | 0.965 | 0.980 |
| timing error 1 frame | 0.988 | 0.972 | 0.955 | 0.971 |
| timing error 2 frame | 0.958 | 0.934 | 0.914 | 0.934 |
| timing error 4 frame | 0.844 | 0.797 | 0.771 | 0.804 |
