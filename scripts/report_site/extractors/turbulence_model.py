#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Authoritative default turbulence & perturbation model spec and per-run diff analyzer."""

from __future__ import annotations

import math
from pathlib import Path

from .common import _parse_cmd_flag

# Exact 7-layer Maunakea von Karman atmospheric profile from
# AtmosphericTurbulenceSimul/src/AtmosphericTurbulence/atmturb_profile.c
DEFAULT_TEL_DIAM_M = 7.95
DEFAULT_SITE_ALT_M = 4215.0
DEFAULT_REF_LAMBDA_UM = 0.50
DEFAULT_SEEING_ARCSEC = 0.80
DEFAULT_VIB_RMS_NM = 45.0
DEFAULT_PETAL_RMS_NM = 1000.0
DEFAULT_PETAL_TAU_S = 3.0
DEFAULT_MASTER_HZ = 2000.0
DEFAULT_OVERSAMPLE = 4
DEFAULT_MASTER_SIZE = 1024
DEFAULT_NWF = 256
DEFAULT_PUP_DIAM_FRAC = 0.9375

DEFAULT_ATM_LAYERS: tuple[dict[str, object], ...] = (
    {
        "index": 0,
        "alt_asl_m": 4215.0,
        "alt_agl_m": 0.0,
        "regime": "Boundary Layer",
        "is_bl": True,
        "cn2_raw": 5.32,
        "speed_mps": 6.50,
        "dir_rad": 1.47,
        "L0_m": 25.0,
    },
    {
        "index": 1,
        "alt_asl_m": 4230.0,
        "alt_agl_m": 15.0,
        "regime": "Boundary Layer",
        "is_bl": True,
        "cn2_raw": 1.47,
        "speed_mps": 6.55,
        "dir_rad": 1.57,
        "L0_m": 25.0,
    },
    {
        "index": 2,
        "alt_asl_m": 4349.0,
        "alt_agl_m": 134.0,
        "regime": "Boundary Layer",
        "is_bl": True,
        "cn2_raw": 1.08,
        "speed_mps": 6.60,
        "dir_rad": 1.67,
        "L0_m": 25.0,
    },
    {
        "index": 3,
        "alt_asl_m": 5007.0,
        "alt_agl_m": 792.0,
        "regime": "Boundary Layer",
        "is_bl": True,
        "cn2_raw": 2.11,
        "speed_mps": 6.70,
        "dir_rad": 1.77,
        "L0_m": 25.0,
    },
    {
        "index": 4,
        "alt_asl_m": 12000.0,
        "alt_agl_m": 7785.0,
        "regime": "Free Atm (Jet)",
        "is_bl": False,
        "cn2_raw": 1.83,
        "speed_mps": 22.00,
        "dir_rad": 3.10,
        "L0_m": 100.0,
    },
    {
        "index": 5,
        "alt_asl_m": 16200.0,
        "alt_agl_m": 11985.0,
        "regime": "Free Atm",
        "is_bl": False,
        "cn2_raw": 1.48,
        "speed_mps": 9.50,
        "dir_rad": 3.20,
        "L0_m": 100.0,
    },
    {
        "index": 6,
        "alt_asl_m": 23701.0,
        "alt_agl_m": 19486.0,
        "regime": "Free Atm",
        "is_bl": False,
        "cn2_raw": 0.697,
        "speed_mps": 5.60,
        "dir_rad": 3.30,
        "L0_m": 100.0,
    },
)

# Exact 5-line telescope & optical-bench vibration resonators from
# cacaosim/src/common/cacaosim_perturb.c
DEFAULT_VIB_MODES: tuple[dict[str, object], ...] = (
    {
        "index": 1,
        "f0_hz": 14.5,
        "zeta": 0.035,
        "share": 0.22,
        "z_wt": (0.85, 0.5268, 0.0, 0.0, 0.0),
        "source": "Telescope truss / M2 wind-shake (elliptical tip/tilt)",
    },
    {
        "index": 2,
        "f0_hz": 31.0,
        "zeta": 0.015,
        "share": 0.16,
        "z_wt": (-0.45, 0.8930, 0.0, 0.0, 0.0),
        "source": "Nasmyth platform / M1 cell support (near-orthogonal tip/tilt)",
    },
    {
        "index": 3,
        "f0_hz": 49.5,
        "zeta": 0.008,
        "share": 0.38,
        "z_wt": (0.78, 0.5492, 0.30, 0.0, 0.0),
        "source": "Cryocooler / bench fundamental (tip/tilt + defocus)",
    },
    {
        "index": 4,
        "f0_hz": 99.0,
        "zeta": 0.008,
        "share": 0.15,
        "z_wt": (0.60, -0.65, 0.0, 0.35, 0.3082),
        "source": "Cryocooler 2nd harmonic / fan (tip/tilt + astigmatism)",
    },
    {
        "index": 5,
        "f0_hz": 138.0,
        "zeta": 0.010,
        "share": 0.09,
        "z_wt": (0.70, 0.7141, 0.0, 0.0, 0.0),
        "source": "High-frequency optical-bench / M2 structural mode (tip/tilt)",
    },
)

# Exact dynamic wind meandering & burst parameters from atmturb_dynwind.c
DEFAULT_DYNWIND_SPEC: dict[str, object] = {
    "bl_cutoff_agl_m": 2000.0,
    "bl_spd_tau_s": 3.5,
    "bl_spd_sigma_log": 0.22,
    "bl_dir_tau_s": 4.0,
    "bl_dir_sigma_deg": 22.0,
    "fa_spd_tau_s": 6.0,
    "fa_spd_sigma_log": 0.14,
    "fa_dir_tau_s": 6.5,
    "fa_dir_sigma_deg": 10.0,
    "lay_bl_tau_s": 3.0,
    "lay_bl_spd_sigma_log": 0.12,
    "lay_bl_dir_sigma_deg": 10.0,
    "lay_fa_tau_s": 5.0,
    "lay_fa_spd_sigma_log": 0.08,
    "lay_fa_dir_sigma_deg": 5.0,
    "band_weight": 0.78,
    "layer_weight": 0.62,
    "speed_clamp_min": 0.35,
    "speed_clamp_max": 3.20,
    "burst_first_gap_s": (1.8, 3.0),
    "burst_gap_s": (2.2, 4.4),
    "burst_rise_s": (0.25, 0.50),
    "burst_decay_s": (0.95, 1.80),
    "burst_spd_amp": (0.80, 1.35),
    "burst_dir_deg": (18.0, 36.0),
    "burst_cn2_amp": (0.22, 0.36),
    "burst_fa_wind_weight": 0.35,
    "burst_fa_cn2_weight": 0.20,
}

# Exact default perturbation parameter values in benches/ao3k_scexao/sim-ao3k-scexao.milk
DEFAULT_PERTURB_PARAMS: dict[str, object] = {
    "seeing": DEFAULT_SEEING_ARCSEC,
    "wind_speed_scale": 1.0,
    "wind_var": True,
    "wind_var_scale": 1.0,
    "wind_burst": True,
    "wind_burst_scale": 1.0,
    "vib_enable": True,
    "vib_rms_nm": DEFAULT_VIB_RMS_NM,
    "petal_enable": True,
    "petal_rms_nm": DEFAULT_PETAL_RMS_NM,
    "petal_tau_s": DEFAULT_PETAL_TAU_S,
    "wind_switch_sec": 0.0,
    "wind_switch_deg": 60.0,
    "boil_mode": 0,
}

TURBULENCE_VISUAL_FILES: tuple[tuple[str, str], ...] = (
    (
        "turb_profile_and_spectrum_2x2.png",
        "7-Layer Maunakea Cn2 Profile, Wind Hodograph, von Karman Structure Function & "
        "Seeing Scaling (2x2)",
    ),
    (
        "turb_wavefront_phase_screens_2x2.png",
        "Simulated Subaru 7.95 m Entrance-Pupil OPD (Atmosphere vs Atmosphere + "
        "Petaling + Vibrations), Spatial PSD & Zernike Variance (2x2)",
    ),
    (
        "turb_wind_dynamics_2x2.png",
        "Default Non-Stationary Wind Meandering, Asymmetric Gust Bursts, Stationary "
        "Speed/tau0 PDFs & Matern-3/2 Temporal PSD (2x2)",
    ),
    (
        "turb_vibrations_2x2.png",
        "Telescope & Optical Bench Vibrations: 5-Line AR(2) PSD, Cumulative RMS Budget "
        "(45 nm), Time-Series Beating & Orthonormal Z2-Z6 Basis (2x2)",
    ),
    (
        "turb_petaling_lwe_2x2.png",
        "Thermally Induced Petaling / Low-Wind Effect (LWE): Subaru V-Spider 4-Island "
        "Segmentation, OPD & H-Band PSF Split, 30 s Trajectories & Matern-3/2 PSD (2x2)",
    ),
)

_R0_CACHE: dict[float, float] = {}


def _kv_5_6(x: float) -> float:
    """Modified Bessel K_{5/6}(x) via 64-point trapezoid quadrature (matches atmturb_seeing.c)."""
    if x <= 1.0e-12:
        return 0.0
    arg = max(30.0 / x, 1.0)
    t_max = math.acosh(arg)
    nsteps = 64
    dt = t_max / float(nsteps)
    acc = 0.5 * (math.exp(-x) + math.exp(-x * math.cosh(t_max)) * math.cosh((5.0 / 6.0) * t_max))
    for i in range(1, nsteps):
        t = float(i) * dt
        acc += math.exp(-x * math.cosh(t)) * math.cosh((5.0 / 6.0) * t)
    return acc * dt


def _j0(x: float) -> float:
    """Bessel J0(x) via 48-point periodic trapezoid rule (matches atmturb_seeing.c)."""
    ax = abs(x)
    nsteps = 48
    dt = (0.5 * math.pi) / float(nsteps)
    acc = 0.5 * (1.0 + math.cos(ax))
    for i in range(1, nsteps):
        acc += math.cos(ax * math.sin(float(i) * dt))
    return (2.0 / math.pi) * dt * acc


def _unit_sf_layer(r_m: float, l0_m: float) -> float:
    if l0_m <= 0.0:
        return 6.883877 * (r_m ** (5.0 / 3.0))
    x = (2.0 * math.pi * r_m) / l0_m
    if x < 1.0e-6:
        return 6.883877 * (r_m ** (5.0 / 3.0))
    fac = (2.0 ** (1.0 / 6.0)) / math.gamma(5.0 / 6.0)
    bracket = 1.0 - fac * (x ** (5.0 / 6.0)) * _kv_5_6(x)
    return 0.172529795 * (l0_m ** (5.0 / 3.0)) * bracket


def get_normalized_layers() -> list[dict[str, object]]:
    """Return the 7 default Maunakea layers with normalized Cn2 fractions and deg headings."""
    tot = sum(float(layer["cn2_raw"]) for layer in DEFAULT_ATM_LAYERS)
    out: list[dict[str, object]] = []
    for layer in DEFAULT_ATM_LAYERS:
        w = float(layer["cn2_raw"]) / tot
        dir_rad = float(layer["dir_rad"])
        out.append(
            {
                **layer,
                "cn2_frac": w,
                "cn2_pct": w * 100.0,
                "dir_deg": math.degrees(dir_rad),
            }
        )
    return out


def compute_effective_l0_m(layers: list[dict[str, object]] | None = None) -> float:
    """Compute Cn2-weighted effective outer scale L0_eff = (sum w_k L0_k^(-1/3))^(-3)."""
    lay = layers if layers is not None else get_normalized_layers()
    acc = sum(
        float(l["cn2_frac"]) * (float(l["L0_m"]) ** (-1.0 / 3.0))
        for l in lay
        if float(l["L0_m"]) > 0.0
    )
    return (acc ** -3.0) if acc > 0.0 else 0.0


def solve_r0_for_seeing_m(seeing_arcsec: float, lambda_um: float = 0.50) -> float:
    """Solve von Karman Fried parameter r0 [m] at lambda_um matching seeing FWHM at 0.50 um.

    Exact pure-stdlib port of atmturb_solve_r0_for_seeing() in atmturb_seeing.c.
    """
    key = round(max(float(seeing_arcsec), 0.05), 4)
    if key in _R0_CACHE:
        r0_500 = _R0_CACHE[key]
    else:
        seeing_rad = key * (math.pi / (180.0 * 3600.0))
        lam_ref = 0.50e-6
        r0_kolm = 0.97586 * lam_ref / seeing_rad
        layers = get_normalized_layers()
        # Aggregate weights by unique L0_m (25 m and 100 m) for fast exact evaluation
        l0_weights: dict[float, float] = {}
        for l in layers:
            l0_v = float(l["L0_m"])
            l0_weights[l0_v] = l0_weights.get(l0_v, 0.0) + float(l["cn2_frac"])

        nr = 256
        r_max = 10.0 * r0_kolm
        dr = r_max / float(nr)
        k_half = (math.pi * seeing_rad) / lam_ref
        sf: list[float] = []
        wj: list[float] = []
        for j in range(nr):
            r = (float(j) + 0.5) * dr
            s = sum(w * _unit_sf_layer(r, l0_v) for l0_v, w in l0_weights.items())
            sf.append(s)
            wj.append(r * (_j0(k_half * r) - 0.5) * dr)

        def eval_root(a_val: float) -> float:
            return sum(math.exp(-0.5 * a_val * s_j) * w_j for s_j, w_j in zip(sf, wj))

        a_kolm = r0_kolm ** (-5.0 / 3.0)
        a_lo = 0.95 * a_kolm
        a_hi = 2.0 * a_kolm
        while eval_root(a_hi) < 0.0 and a_hi < a_kolm * 1.0e6:
            a_hi *= 2.0
        while eval_root(a_lo) > 0.0 and a_lo > a_kolm * 1.0e-6:
            a_lo *= 0.5
        for _ in range(48):
            a_mid = 0.5 * (a_lo + a_hi)
            if eval_root(a_mid) < 0.0:
                a_lo = a_mid
            else:
                a_hi = a_mid
        r0_500 = (0.5 * (a_lo + a_hi)) ** -0.6
        _R0_CACHE[key] = r0_500

    return r0_500 * ((lambda_um / 0.50) ** 1.2)


def compute_piston_removed_opd_nm(
    r0_500_m: float,
    tel_diam_m: float = DEFAULT_TEL_DIAM_M,
    layers: list[dict[str, object]] | None = None,
    *,
    kolmogorov: bool = False,
) -> float:
    """Exact piston-removed pupil OPD RMS [nm] via circular-aperture autocorrelation integral.

    Evaluates sigma_phi^2 = 0.5 * integral_0^D D_phi(r) * P_auto(r) dr with exact normalized
    aperture chord-length density P_auto(r) = (16 / (pi * D^2)) * r * [acos(u) - u*sqrt(1-u^2)].
    """
    lay = layers if layers is not None else get_normalized_layers()
    l0_weights: dict[float, float] = {}
    if kolmogorov:
        l0_weights[0.0] = 1.0
    else:
        for l in lay:
            l0_v = float(l["L0_m"])
            l0_weights[l0_v] = l0_weights.get(l0_v, 0.0) + float(l["cn2_frac"])

    npts = 64
    du = 1.0 / float(npts)
    var_unit = 0.0
    for i in range(npts):
        u = (float(i) + 0.5) * du
        r = u * tel_diam_m
        p_u = (16.0 / math.pi) * u * (math.acos(u) - u * math.sqrt(max(0.0, 1.0 - u * u)))
        sf_u = sum(w * _unit_sf_layer(r, l0_v) for l0_v, w in l0_weights.items())
        var_unit += 0.5 * sf_u * p_u * du
    var_rad2 = var_unit * (r0_500_m ** (-5.0 / 3.0))
    return math.sqrt(max(var_rad2, 0.0)) * (500.0 / (2.0 * math.pi))


def compute_atmosphere_stats(
    seeing_arcsec: float = DEFAULT_SEEING_ARCSEC,
    wind_speed_scale: float = 1.0,
    tel_diam_m: float = DEFAULT_TEL_DIAM_M,
) -> dict[str, object]:
    """Compute comprehensive analytical atmospheric statistics for the default 7-layer model."""
    layers = get_normalized_layers()
    l0_eff = compute_effective_l0_m(layers)
    bl_frac = sum(float(l["cn2_frac"]) for l in layers if l["is_bl"])
    fa_frac = 1.0 - bl_frac

    v_mean = sum(float(l["cn2_frac"]) * float(l["speed_mps"]) for l in layers) * wind_speed_scale
    v_eff = (
        sum(float(l["cn2_frac"]) * (float(l["speed_mps"]) ** (5.0 / 3.0)) for l in layers) ** 0.6
    ) * wind_speed_scale
    h_eff = (
        sum(
            float(l["cn2_frac"]) * (max(float(l["alt_agl_m"]), 1.0) ** (5.0 / 3.0))
            for l in layers
        )
        ** 0.6
    )

    seeing_rad = seeing_arcsec * (math.pi / (180.0 * 3600.0))
    r0_kolm_500 = 0.97586 * 0.50e-6 / seeing_rad
    r0_vk_500 = solve_r0_for_seeing_m(seeing_arcsec, 0.50)

    opd_kolm_nm = compute_piston_removed_opd_nm(r0_kolm_500, tel_diam_m, layers, kolmogorov=True)
    opd_vk_nm = compute_piston_removed_opd_nm(r0_vk_500, tel_diam_m, layers, kolmogorov=False)
    # Tip/tilt removed variance (Noll 1976: 0.134 * (D/r0)^(5/3) with minor outer-scale attenuation)
    opd_tt_rem_nm = math.sqrt(0.134 * ((tel_diam_m / r0_vk_500) ** (5.0 / 3.0))) * (
        500.0 / (2.0 * math.pi)
    )

    bands: list[dict[str, object]] = []
    for name, lam_um in (
        ("Ref (0.50 um)", 0.50),
        ("Vis / SCExAO WFS (0.75 um)", 0.75),
        ("J-Band / AO3k WFS (1.22 um)", 1.22),
        ("H-Band / Science & Coro (1.65 um)", 1.65),
    ):
        r0_m = solve_r0_for_seeing_m(seeing_arcsec, lam_um)
        tau0_ms = (0.314 * r0_m / max(v_eff, 1e-6)) * 1000.0
        f_g_hz = 0.427 * v_eff / max(r0_m, 1e-6)
        theta0_arcsec = math.degrees(0.314 * r0_m / max(h_eff, 1.0)) * 3600.0
        bands.append(
            {
                "band": name,
                "lambda_um": lam_um,
                "r0_cm": r0_m * 100.0,
                "d_over_r0": tel_diam_m / r0_m,
                "tau0_ms": tau0_ms,
                "greenwood_hz": f_g_hz,
                "theta0_arcsec": theta0_arcsec,
            }
        )

    return {
        "seeing_arcsec": seeing_arcsec,
        "wind_speed_scale": wind_speed_scale,
        "tel_diam_m": tel_diam_m,
        "l0_eff_m": l0_eff,
        "bl_cn2_pct": bl_frac * 100.0,
        "fa_cn2_pct": fa_frac * 100.0,
        "v_mean_mps": v_mean,
        "v_eff_53_mps": v_eff,
        "h_eff_53_m": h_eff,
        "r0_kolm_500_cm": r0_kolm_500 * 100.0,
        "r0_vk_500_cm": r0_vk_500 * 100.0,
        "opd_kolm_nm": opd_kolm_nm,
        "opd_vk_nm": opd_vk_nm,
        "opd_tt_removed_nm": opd_tt_rem_nm,
        "bands": bands,
    }


def compute_vibration_stats(vib_rms_nm: float = 45.0) -> dict[str, object]:
    """Compute exact stationary per-line and per-Zernike RMS breakdown for the vibration model."""
    lines: list[dict[str, object]] = []
    z_var = [0.0] * 5
    for m in DEFAULT_VIB_MODES:
        share = float(m["share"])
        zeta = float(m["zeta"])
        f0 = float(m["f0_hz"])
        q_fac = 1.0 / (2.0 * zeta)
        line_rms = vib_rms_nm * math.sqrt(share)
        z_wt = tuple(float(w) for w in m["z_wt"])  # type: ignore[union-attr]
        for idx in range(5):
            z_var[idx] += share * (z_wt[idx] ** 2)
        lines.append(
            {
                **m,
                "q_factor": q_fac,
                "fwhm_hz": f0 / q_fac,
                "rms_nm": line_rms,
                "share_pct": share * 100.0,
            }
        )
    z_names = ("Z2 (Tip)", "Z3 (Tilt)", "Z4 (Defocus)", "Z5 (Oblique Astig)", "Z6 (Vertical Astig)")
    z_modes = [
        {
            "mode": z_names[i],
            "rms_nm": vib_rms_nm * math.sqrt(z_var[i]),
            "share_pct": z_var[i] * 100.0,
        }
        for i in range(5)
    ]
    return {
        "total_rms_nm": vib_rms_nm,
        "lines": lines,
        "zernikes": z_modes,
    }


def compute_petaling_stats(
    petal_rms_nm: float = DEFAULT_PETAL_RMS_NM,
    petal_tau_s: float = DEFAULT_PETAL_TAU_S,
    n_petals: int = 4,
) -> dict[str, object]:
    """Compute exact stationary statistics for the thermal petaling / LWE model."""
    piston_rms_nm = petal_rms_nm * math.sqrt(0.75)
    # Individual raw draw sigma before mean removal: sig_pis = rms * sqrt(0.75 * N / (N - 1))
    per_island_piston_sigma_nm = petal_rms_nm * math.sqrt(0.75 * n_petals / max(n_petals - 1, 1))
    # Actual mean-removed island piston std dev (same as piston_rms_nm for equal-area islands)
    local_tip_rms_nm = petal_rms_nm * math.sqrt(0.125)
    local_tilt_rms_nm = petal_rms_nm * math.sqrt(0.125)
    corner_hz = 1.0 / (2.0 * math.pi * max(petal_tau_s, 0.05))
    # Range of (X_i - mean(X)) equals range of X_i; for N=4 iid N(0, sig_pis^2), E[R_4]=2.0588*sig.
    expected_ptv_nm = 2.0588 * per_island_piston_sigma_nm
    return {
        "total_rms_nm": petal_rms_nm,
        "tau_s": petal_tau_s,
        "n_petals": n_petals,
        "piston_share_pct": 75.0,
        "local_tip_share_pct": 12.5,
        "local_tilt_share_pct": 12.5,
        "piston_rms_nm": piston_rms_nm,
        "per_island_raw_sigma_nm": per_island_piston_sigma_nm,
        "local_tip_rms_nm": local_tip_rms_nm,
        "local_tilt_rms_nm": local_tilt_rms_nm,
        "corner_hz": corner_hz,
        "expected_ptv_nm": expected_ptv_nm,
    }


def _to_bool(val: object) -> bool | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "on", "yes"):
        return True
    if s in ("0", "false", "off", "no"):
        return False
    try:
        return float(s) != 0.0
    except ValueError:
        return None


def _to_float(val: object) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _has_cli_flag(cmd: str, flag: str) -> bool:
    if not cmd:
        return False
    return flag in cmd.split()


def _format_ratio(val: float, default: float) -> str:
    if default <= 0.0:
        return ""
    ratio = val / default
    if abs(ratio - 1.0) < 0.015:
        return ""
    if abs(ratio - round(ratio)) < 0.03 and round(ratio) >= 2:
        return f"{int(round(ratio))}x default"
    return f"{ratio:.2f}x default"


def extract_turbulence_profile(
    metrics_data: dict[str, object] | None,
    run_options: dict[str, object] | None = None,
    out_slug_dir: Path | None = None,
) -> dict[str, object]:
    """Resolve a simulation's turbulence & perturbation configuration and diff vs defaults.

    Returns a structured dict containing resolved settings, whether the run matches the default
    model, a human-readable list of explicit changes (with ratios & explanations), realized
    perturbation telemetry (when recorded), and compact summary pills for catalog tables.
    """
    data = metrics_data if isinstance(metrics_data, dict) else {}
    sa = data.get("star_and_atmosphere") if isinstance(data.get("star_and_atmosphere"), dict) else {}
    repro = data.get("reproducibility") if isinstance(data.get("reproducibility"), dict) else {}
    cmd = str(repro.get("run_command") or "")
    ts_m = data.get("timeseries_metrics") if isinstance(data.get("timeseries_metrics"), dict) else {}
    pert_tlm = ts_m.get("perturbations") if isinstance(ts_m.get("perturbations"), dict) else None

    raw_opts: dict[str, object] = {}
    if isinstance(run_options, dict):
        inner = run_options.get("options")
        raw_opts = inner if isinstance(inner, dict) else run_options

    has_pert_opts = any(
        k in raw_opts
        for k in ("wind_var", "wind_burst", "vib_enable", "petal_enable", "wind_var_scale")
    )
    has_pert_csv = bool(out_slug_dir and (out_slug_dir / "perturb_timeseries.csv").is_file())
    cli_no_perturb = _has_cli_flag(cmd, "--no-perturb")
    has_any_cli_pert = cli_no_perturb or any(
        _has_cli_flag(cmd, f) or (_parse_cmd_flag(cmd, f) is not None)
        for f in (
            "--no-wind-var",
            "--wind-var-scale",
            "--no-wind-burst",
            "--wind-burst-scale",
            "--no-vib",
            "--vib-rms-nm",
            "--no-petal",
            "--petal-rms-nm",
            "--petal-tau-s",
            "--wind-switch-sec",
            "--wind-speed-scale",
        )
    )

    # Legacy runs (before realistic perturbations were introduced) had neither run_options
    # perturbation keys nor perturb_timeseries.csv nor perturbation metrics: they ran pure
    # stationary 7-layer Maunakea frozen-flow with all 4 dynamic perturbation channels OFF.
    is_legacy_stationary = (
        not has_pert_opts and pert_tlm is None and not has_pert_csv and not has_any_cli_pert
    )

    # 1. Seeing
    seeing = _to_float(sa.get("seeing_arcsec_500nm"))
    if seeing is None:
        seeing = _to_float(raw_opts.get("seeing"))
    if seeing is None:
        seeing = _to_float(_parse_cmd_flag(cmd, "--seeing"))
    if seeing is None:
        seeing = DEFAULT_SEEING_ARCSEC

    # 2. Wind speed scale (optional override, e.g. --wind-speed-scale 2.0)
    wind_speed_scale = _to_float(raw_opts.get("wind_speed_scale"))
    if wind_speed_scale is None:
        wind_speed_scale = _to_float(sa.get("wind_speed_scale"))
    if wind_speed_scale is None:
        wind_speed_scale = _to_float(_parse_cmd_flag(cmd, "--wind-speed-scale"))
    if wind_speed_scale is None:
        wind_speed_scale = 1.0

    # 3. Wind meandering
    wind_var = _to_bool(raw_opts.get("wind_var"))
    if wind_var is None:
        if cli_no_perturb or _has_cli_flag(cmd, "--no-wind-var"):
            wind_var = False
        elif pert_tlm is not None and "wind_active" in pert_tlm:
            wind_var = bool(pert_tlm.get("wind_active"))
        elif is_legacy_stationary:
            wind_var = False
        else:
            wind_var = True
    wind_var_scale = _to_float(raw_opts.get("wind_var_scale"))
    if wind_var_scale is None:
        wind_var_scale = _to_float(_parse_cmd_flag(cmd, "--wind-var-scale"))
    if wind_var_scale is None:
        wind_var_scale = 1.0

    # 4. Wind bursts
    wind_burst = _to_bool(raw_opts.get("wind_burst"))
    if wind_burst is None:
        if cli_no_perturb or _has_cli_flag(cmd, "--no-wind-burst"):
            wind_burst = False
        elif pert_tlm is not None and "burst_active" in pert_tlm:
            wind_burst = bool(pert_tlm.get("burst_active"))
        elif is_legacy_stationary:
            wind_burst = False
        else:
            wind_burst = True
    wind_burst_scale = _to_float(raw_opts.get("wind_burst_scale"))
    if wind_burst_scale is None:
        wind_burst_scale = _to_float(_parse_cmd_flag(cmd, "--wind-burst-scale"))
    if wind_burst_scale is None:
        wind_burst_scale = 1.0

    # 5. Vibrations
    vib_enable = _to_bool(raw_opts.get("vib_enable"))
    if vib_enable is None:
        if cli_no_perturb or _has_cli_flag(cmd, "--no-vib"):
            vib_enable = False
        elif pert_tlm is not None and "vib_active" in pert_tlm:
            vib_enable = bool(pert_tlm.get("vib_active"))
        elif is_legacy_stationary:
            vib_enable = False
        else:
            vib_enable = True
    vib_rms_nm = _to_float(raw_opts.get("vib_rms_nm"))
    if vib_rms_nm is None:
        vib_rms_nm = _to_float(_parse_cmd_flag(cmd, "--vib-rms-nm"))
    if vib_rms_nm is None:
        vib_rms_nm = 45.0
    if vib_rms_nm <= 0.0:
        vib_enable = False

    # 6. Thermal petaling / LWE
    petal_enable = _to_bool(raw_opts.get("petal_enable"))
    if petal_enable is None:
        if cli_no_perturb or _has_cli_flag(cmd, "--no-petal"):
            petal_enable = False
        elif pert_tlm is not None and "petal_active" in pert_tlm:
            petal_enable = bool(pert_tlm.get("petal_active"))
        elif is_legacy_stationary:
            petal_enable = False
        else:
            petal_enable = True
    petal_rms_nm = _to_float(raw_opts.get("petal_rms_nm"))
    if petal_rms_nm is None:
        petal_rms_nm = _to_float(_parse_cmd_flag(cmd, "--petal-rms-nm"))
    if petal_rms_nm is None:
        petal_rms_nm = DEFAULT_PETAL_RMS_NM
    if petal_rms_nm <= 0.0:
        petal_enable = False
    petal_tau_s = _to_float(raw_opts.get("petal_tau_s"))
    if petal_tau_s is None:
        petal_tau_s = _to_float(_parse_cmd_flag(cmd, "--petal-tau-s"))
    if petal_tau_s is None:
        petal_tau_s = DEFAULT_PETAL_TAU_S

    # 7. Live wind-direction step
    wind_switch_sec = _to_float(raw_opts.get("wind_switch_sec"))
    if wind_switch_sec is None:
        wind_switch_sec = _to_float(_parse_cmd_flag(cmd, "--wind-switch-sec"))
    if wind_switch_sec is None:
        wind_switch_sec = 0.0
    wind_switch_deg = _to_float(raw_opts.get("wind_switch_deg"))
    if wind_switch_deg is None:
        wind_switch_deg = _to_float(_parse_cmd_flag(cmd, "--wind-switch-deg"))
    if wind_switch_deg is None:
        wind_switch_deg = 60.0

    # 8. Optional Fourier boiling override
    boil_mode_f = _to_float(raw_opts.get("boil_mode"))
    if boil_mode_f is None:
        boil_mode_f = _to_float(_parse_cmd_flag(cmd, "--boil-mode"))
    boil_mode = int(boil_mode_f) if boil_mode_f is not None else 0

    # Build explicit structured diff items vs Default Turbulence & Perturbation Model
    changes: list[dict[str, str]] = []
    short_tags: list[str] = []

    if abs(seeing - DEFAULT_SEEING_ARCSEC) > 0.005:
        r0_run = solve_r0_for_seeing_m(seeing, 0.50) * 100.0
        r0_def = solve_r0_for_seeing_m(DEFAULT_SEEING_ARCSEC, 0.50) * 100.0
        r_str = _format_ratio(seeing, DEFAULT_SEEING_ARCSEC)
        ratio_txt = f" ({r_str})" if r_str else ""
        changes.append(
            {
                "key": "seeing",
                "label": "Atmospheric Seeing (0.50 um)",
                "value": f'{seeing:.2f}"',
                "default": f'{DEFAULT_SEEING_ARCSEC:.2f}"',
                "explanation": (
                    f'Seeing changed to {seeing:.2f}"{ratio_txt} vs default '
                    f'{DEFAULT_SEEING_ARCSEC:.2f}" (von Karman r0 = {r0_run:.1f} cm vs '
                    f"default {r0_def:.1f} cm at 0.50 um)"
                ),
                "flag": "--seeing",
                "anchor": "atmosphere-profile",
            }
        )
        short_tags.append(f'Seeing {seeing:.2f}" ({r_str or "custom"})')

    if abs(wind_speed_scale - 1.0) > 0.01:
        r_str = _format_ratio(wind_speed_scale, 1.0) or f"{wind_speed_scale:.2f}x default"
        v_def = float(compute_atmosphere_stats(seeing, 1.0)["v_eff_53_mps"])
        v_run = v_def * wind_speed_scale
        changes.append(
            {
                "key": "wind_speed_scale",
                "label": "Layer Wind Speed Scale",
                "value": f"{wind_speed_scale:g}x",
                "default": "1.0x",
                "explanation": (
                    f"Layer wind speeds scaled to {r_str} "
                    f"(v_eff = {v_run:.1f} m/s vs default {v_def:.1f} m/s)"
                ),
                "flag": "--wind-speed-scale",
                "anchor": "wind-dynamics",
            }
        )
        short_tags.append(f"Wind speed {wind_speed_scale:g}x")

    if not wind_var:
        changes.append(
            {
                "key": "wind_var",
                "label": "Wind Meandering (Matern-3/2)",
                "value": "OFF",
                "default": "ON (1.0x)",
                "explanation": (
                    "Smooth wind speed & direction meandering turned OFF "
                    "(stationary layer wind vectors; default: ON at 1.0x)"
                ),
                "flag": "--no-wind-var",
                "anchor": "wind-dynamics",
            }
        )
        short_tags.append("Wind drift OFF")
    elif abs(wind_var_scale - 1.0) > 0.01:
        r_str = _format_ratio(wind_var_scale, 1.0) or f"{wind_var_scale:.2f}x default"
        changes.append(
            {
                "key": "wind_var_scale",
                "label": "Wind Meandering Scale",
                "value": f"{wind_var_scale:g}x",
                "default": "1.0x",
                "explanation": (
                    f"Wind speed & direction meandering amplitude scaled to {r_str} "
                    f"(--wind-var-scale {wind_var_scale:g})"
                ),
                "flag": "--wind-var-scale",
                "anchor": "wind-dynamics",
            }
        )
        short_tags.append(f"Wind drift {wind_var_scale:g}x")

    if not wind_burst:
        changes.append(
            {
                "key": "wind_burst",
                "label": "Wind Gust Bursts & Cn2 Surges",
                "value": "OFF",
                "default": "ON (1.0x)",
                "explanation": (
                    "Non-stationary wind gust bursts & Cn2 surges turned OFF "
                    "(default: ON at 1.0x)"
                ),
                "flag": "--no-wind-burst",
                "anchor": "wind-dynamics",
            }
        )
        short_tags.append("Gust bursts OFF")
    elif abs(wind_burst_scale - 1.0) > 0.01:
        r_str = _format_ratio(wind_burst_scale, 1.0) or f"{wind_burst_scale:.2f}x default"
        changes.append(
            {
                "key": "wind_burst_scale",
                "label": "Wind Gust Burst Scale",
                "value": f"{wind_burst_scale:g}x",
                "default": "1.0x",
                "explanation": (
                    f"Wind gust burst & Cn2 surge strength scaled to {r_str} "
                    f"(--wind-burst-scale {wind_burst_scale:g})"
                ),
                "flag": "--wind-burst-scale",
                "anchor": "wind-dynamics",
            }
        )
        short_tags.append(f"Gust bursts {wind_burst_scale:g}x")

    if not vib_enable:
        changes.append(
            {
                "key": "vib_enable",
                "label": "Telescope & Bench Vibrations",
                "value": "OFF",
                "default": "ON (45.0 nm RMS)",
                "explanation": (
                    "Stochastic 5-line mechanical vibrations (14.5-138 Hz) turned OFF "
                    "(default: ON at 45.0 nm RMS)"
                ),
                "flag": "--no-vib",
                "anchor": "vibrations-model",
            }
        )
        short_tags.append("Vibrations OFF")
    elif abs(vib_rms_nm - 45.0) > 0.2:
        r_str = _format_ratio(vib_rms_nm, 45.0)
        ratio_txt = f" ({r_str})" if r_str else ""
        changes.append(
            {
                "key": "vib_rms_nm",
                "label": "Vibration Amplitude RMS",
                "value": f"{vib_rms_nm:.1f} nm",
                "default": "45.0 nm",
                "explanation": (
                    f"Vibration OPD RMS set to {vib_rms_nm:.1f} nm{ratio_txt} "
                    "vs default 45.0 nm across 14.5-138 Hz lines"
                ),
                "flag": "--vib-rms-nm",
                "anchor": "vibrations-model",
            }
        )
        short_tags.append(f"Vib {vib_rms_nm:.0f} nm")

    if not petal_enable:
        changes.append(
            {
                "key": "petal_enable",
                "label": "Additional Thermal Petaling (LWE)",
                "value": "OFF",
                "default": f"ON ({DEFAULT_PETAL_RMS_NM:.1f} nm, tau={DEFAULT_PETAL_TAU_S:.1f} s)",
                "explanation": (
                    "Additional thermally induced island petaling / LWE turned OFF "
                    f"(default: ON at {DEFAULT_PETAL_RMS_NM:.1f} nm RMS, "
                    f"tau = {DEFAULT_PETAL_TAU_S:.1f} s)"
                ),
                "flag": "--no-petal",
                "anchor": "petaling-model",
            }
        )
        short_tags.append("Petaling OFF")
    else:
        if abs(petal_rms_nm - DEFAULT_PETAL_RMS_NM) > 0.5:
            r_str = _format_ratio(petal_rms_nm, DEFAULT_PETAL_RMS_NM)
            ratio_txt = f" ({r_str})" if r_str else ""
            changes.append(
                {
                    "key": "petal_rms_nm",
                    "label": "Thermal Petaling (LWE) RMS",
                    "value": f"{petal_rms_nm:.0f} nm",
                    "default": f"{DEFAULT_PETAL_RMS_NM:.0f} nm",
                    "explanation": (
                        f"Thermal petaling OPD RMS set to {petal_rms_nm:.0f} nm{ratio_txt} "
                        f"vs default {DEFAULT_PETAL_RMS_NM:.0f} nm"
                    ),
                    "flag": "--petal-rms-nm",
                    "anchor": "petaling-model",
                }
            )
            short_tags.append(f"Petal {petal_rms_nm:.0f} nm ({r_str or 'custom'})")
        if abs(petal_tau_s - DEFAULT_PETAL_TAU_S) > 0.05:
            r_str = _format_ratio(petal_tau_s, DEFAULT_PETAL_TAU_S)
            ratio_txt = f" ({r_str})" if r_str else ""
            changes.append(
                {
                    "key": "petal_tau_s",
                    "label": "Thermal Petaling Timescale",
                    "value": f"{petal_tau_s:g} s",
                    "default": f"{DEFAULT_PETAL_TAU_S:.1f} s",
                    "explanation": (
                        f"Thermal petaling correlation time set to tau = {petal_tau_s:g} s"
                        f"{ratio_txt} vs default {DEFAULT_PETAL_TAU_S:.1f} s"
                    ),
                    "flag": "--petal-tau-s",
                    "anchor": "petaling-model",
                }
            )
            short_tags.append(f"Petal tau={petal_tau_s:g}s")

    if wind_switch_sec > 0.0:
        changes.append(
            {
                "key": "wind_switch",
                "label": "Live Wind-Direction Step",
                "value": f"{wind_switch_deg:+.0f} deg @ t={wind_switch_sec:g} s",
                "default": "OFF (0 s)",
                "explanation": (
                    f"Phase-continuous live wind heading rotation of {wind_switch_deg:+.0f} deg "
                    f"injected at t_phys = {wind_switch_sec:g} s (default: OFF)"
                ),
                "flag": "--wind-switch-sec",
                "anchor": "wind-dynamics",
            }
        )
        short_tags.append(f"Wind rot {wind_switch_deg:+.0f}deg@{wind_switch_sec:g}s")

    if boil_mode != 0:
        b_lbl = f"AR({abs(boil_mode)})"
        changes.append(
            {
                "key": "boil_mode",
                "label": "Fourier Turbulence Boiling",
                "value": b_lbl,
                "default": "OFF (rolling cross-fade)",
                "explanation": (
                    f"Spatial-frequency-dependent Fourier {b_lbl} boiling enabled "
                    "(default: OFF, variance-preserving rolling screen cross-fade only)"
                ),
                "flag": "--boil-mode",
                "anchor": "atmosphere-profile",
            }
        )
        short_tags.append(f"Boiling {b_lbl}")

    all_perturb_off = not (wind_var or wind_burst or vib_enable or petal_enable)
    if all_perturb_off:
        if abs(seeing - DEFAULT_SEEING_ARCSEC) <= 0.005 and abs(wind_speed_scale - 1.0) <= 0.01:
            summary_label = (
                "Stationary frozen-flow (all dynamic perturbations OFF)"
                if not is_legacy_stationary
                else "Stationary 7-layer frozen-flow (perturbations OFF)"
            )
            compact_badge = "Stationary (perturb OFF)"
        else:
            summary_label = (
                f'Seeing {seeing:.2f}" + stationary frozen-flow (perturbations OFF)'
            )
            compact_badge = f'Seeing {seeing:.2f}" · perturb OFF'
    elif not changes:
        summary_label = "Default Turbulence & Perturbation Model (all parameters default)"
        compact_badge = "Default model"
    else:
        summary_label = "; ".join(short_tags)
        compact_badge = " · ".join(short_tags[:3])
        if len(short_tags) > 3:
            compact_badge += f" (+{len(short_tags) - 3})"

    atm_stats = compute_atmosphere_stats(seeing, wind_speed_scale)
    r0_eff_cm = (
        float(sa["r0_500nm_m"]) * 100.0
        if sa.get("r0_500nm_m") is not None
        else float(atm_stats["r0_vk_500_cm"])
    )

    realized: dict[str, object] = {}
    if isinstance(pert_tlm, dict) and pert_tlm:
        for rk in (
            "wind_scale_min",
            "wind_scale_mean",
            "wind_scale_max",
            "wind_deg_min",
            "wind_deg_max",
            "burst_peak",
            "burst_frac_pct",
            "cn2_scale_max",
            "vib_rms_nm_quad",
            "vib_tip_rms_nm",
            "vib_tilt_rms_nm",
            "vib_foc_rms_nm",
            "petal_rms_nm_mean",
            "petal_rms_nm_max",
            "petal_ptv_nm_max",
        ):
            if rk in pert_tlm and pert_tlm[rk] is not None:
                realized[rk] = round(float(pert_tlm[rk]), 4)

    return {
        "matches_default": len(changes) == 0,
        "is_legacy_stationary": is_legacy_stationary,
        "all_perturb_off": all_perturb_off,
        "summary_label": summary_label,
        "compact_badge": compact_badge,
        "changes": changes,
        "short_tags": short_tags,
        "resolved": {
            "seeing_arcsec": round(seeing, 3),
            "r0_500nm_cm": round(r0_eff_cm, 2),
            "l0_eff_m": round(float(atm_stats["l0_eff_m"]), 1),
            "v_eff_53_mps": round(float(atm_stats["v_eff_53_mps"]), 2),
            "tau0_500nm_ms": round(float(atm_stats["bands"][0]["tau0_ms"]), 2),  # type: ignore[index]
            "wind_speed_scale": wind_speed_scale,
            "wind_var": wind_var,
            "wind_var_scale": wind_var_scale,
            "wind_burst": wind_burst,
            "wind_burst_scale": wind_burst_scale,
            "vib_enable": vib_enable,
            "vib_rms_nm": vib_rms_nm,
            "petal_enable": petal_enable,
            "petal_rms_nm": petal_rms_nm,
            "petal_tau_s": petal_tau_s,
            "wind_switch_sec": wind_switch_sec,
            "wind_switch_deg": wind_switch_deg,
            "boil_mode": boil_mode,
        },
        "realized": realized,
    }
