#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Figure 6: H-band coronagraphic PSFs and real-time compute Pareto frontier."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from matplotlib.colors import LogNorm
from matplotlib.gridspec import GridSpec
import matplotlib.pyplot as plt
import numpy as np

def plot_fig6_psf_and_compute(bundles: list[dict[str, Any]], out_dir: Path) -> None:
    """Figure 6: H-Band Coronagraphic PSFs (Top) + Real-Time Compute Scaling & Pareto (Bottom)."""
    n_runs = len(bundles)
    fig = plt.figure(figsize=(16.8, 9.8), constrained_layout=True)
    gs = GridSpec(2, 1, figure=fig, height_ratios=[0.95, 1.25])
    gs_top = gs[0].subgridspec(1, n_runs, wspace=0.06)
    gs_bot = gs[1].subgridspec(1, 3, wspace=0.20)
    fig.suptitle(
        "H-Band Lyot Coronagraphic PSFs, Real-Time Compute Scalability & Accuracy–Compute Pareto "
        "Frontier\n"
        "(All Orders Through AR(64) Achieve 0 Real-Time Timeouts; AR(16) Sits Squarely on the "
        "Pareto-Optimal Knee)",
        fontsize=11.5,
        fontweight="bold",
    )

    # Top row: 8 side-by-side H-band coronagraphic PSFs (log scale, zoomed +/-24 l/D)
    for i, b in enumerate(bundles):
        ax_p = fig.add_subplot(gs_top[0, i])
        psf = np.maximum(b["psf_coro"], 1e-8)
        ny, nx = psf.shape
        cy, cx = ny // 2, nx // 2
        # pixscale_ld is pixels per (lambda/D) (= 2.5); 1 pix = 0.4 l/D -> +/-60 pix = +/-24 l/D
        pix_per_ld = float(b["metrics"]["coronagraph_metrics"]["pixscale_ld"])
        ld_per_pix = 1.0 / max(pix_per_ld, 1e-6)
        half = min(60, cy, cx)
        crop = psf[cy - half : cy + half, cx - half : cx + half]
        ext = half * ld_per_pix
        im = ax_p.imshow(
            crop,
            origin="lower",
            cmap="inferno",
            norm=LogNorm(vmin=1e-6, vmax=8e-4),
            extent=[-ext, ext, -ext, ext],
        )
        ax_p.set_title(
            f"{b['spec']['short']}\nC(3–10)={b['summary']['coro_c3_10']:.2e}",
            fontsize=7.6,
            color=b["spec"]["color"],
            fontweight="bold",
        )
        ax_p.set_xlabel("Δα [λ/D]", fontsize=7.5)
        ax_p.tick_params(labelsize=7.2)
        if i == 0:
            ax_p.set_ylabel("Δδ [λ/D]", fontsize=7.8)
        else:
            ax_p.set_yticks([])
        if i == n_runs - 1:
            cb = fig.colorbar(im, ax=ax_p, fraction=0.055, pad=0.04)
            cb.set_label("Raw Contrast", fontsize=7.5)

    # Bottom-left: mkARPF Online Solver Latency [ms] vs Order P
    ax_mk = fig.add_subplot(gs_bot[0, 0])
    std_pf = [b for b in bundles if b["spec"]["order"] > 0 and not b["spec"]["is_ablation"]]
    ab_pf = [b for b in bundles if b["spec"]["is_ablation"]]
    ps = np.array([b["spec"]["order"] for b in std_pf], dtype=np.float64)
    mk1 = np.array([b["summary"]["procs"]["mkARPF-1"]["exec_p50_us"] / 1e3 for b in std_pf])
    mk2 = np.array([b["summary"]["procs"]["mkARPF-2"]["exec_p50_us"] / 1e3 for b in std_pf])
    ax_mk.plot(ps, mk1, "-o", color="#2563eb", lw=2.0, ms=6.0, label="mkARPF-1 (1965 m, N=2048)")
    ax_mk.plot(ps, mk2, "-s", color="#059669", lw=2.0, ms=6.0, label="mkARPF-2 (1255 m, N=2048)")
    if ab_pf:
        ps_ab = np.array([b["spec"]["order"] for b in ab_pf], dtype=np.float64)
        ab1 = np.array([b["summary"]["procs"]["mkARPF-1"]["exec_p50_us"] / 1e3 for b in ab_pf])
        ab2 = np.array([b["summary"]["procs"]["mkARPF-2"]["exec_p50_us"] / 1e3 for b in ab_pf])
        ax_mk.plot(
            ps_ab,
            ab1,
            ":*",
            color="#7c3aed",
            lw=1.4,
            ms=10.5,
            zorder=6,
            label="mkARPF-1 Warm* (N=4096)",
        )
        ax_mk.plot(
            ps_ab,
            ab2,
            ":P",
            color="#0891b2",
            lw=1.4,
            ms=8.0,
            zorder=6,
            label="mkARPF-2 Warm* (N=4096)",
        )
        for xv, y1, y2 in zip(ps_ab, ab1, ab2):
            ax_mk.annotate(
                f"{y1:.0f} ms",
                (xv, y1),
                xytext=(-40, 2),
                textcoords="offset points",
                fontsize=7.3,
                fontweight="bold",
                color="#6d28d9",
            )
            ax_mk.annotate(
                f"{y2:.0f} ms",
                (xv, y2),
                xytext=(-40, -10),
                textcoords="offset points",
                fontsize=7.3,
                fontweight="bold",
                color="#0e7490",
            )
    for xv, y1, y2 in zip(ps, mk1, mk2):
        if int(xv) == 8:
            continue
        xi = int(xv)
        off1 = {4: (0, 8), 16: (0, 7), 32: (16, -2), 64: (-28, 4)}.get(xi, (0, 7))
        off2 = {4: (14, -4), 16: (0, -13), 32: (0, -13), 64: (-28, -11)}.get(xi, (0, -13))
        ax_mk.annotate(
            f"{y1:.0f}",
            (xv, y1),
            xytext=off1,
            textcoords="offset points",
            ha="center",
            fontsize=7.3,
            color="#1d4ed8",
        )
        ax_mk.annotate(
            f"{y2:.0f}",
            (xv, y2),
            xytext=off2,
            textcoords="offset points",
            ha="center",
            fontsize=7.3,
            color="#047857",
        )
    ax_mk.set_xticks([4, 8, 16, 32, 64])
    ax_mk.set_xlim(0, 69)
    ax_mk.set_ylim(0, 1020)
    ax_mk.set_xlabel("AR Filter Order P")
    ax_mk.set_ylabel("Solver Update Latency p50 [ms]")
    ax_mk.set_title("Online Filter Solver Cost (mkARPF, O(N·P²))")
    ax_mk.grid(True, alpha=0.28)
    ax_mk.legend(loc="upper left", framealpha=0.92, fontsize=7.2)

    # Bottom-middle: applyARPF Real-Time Frame Latency [us] vs Order P
    ax_ap = fig.add_subplot(gs_bot[0, 1])
    ap1 = np.array([b["summary"]["procs"]["applyARPF-1"]["exec_p50_us"] for b in std_pf])
    ap2 = np.array([b["summary"]["procs"]["applyARPF-2"]["exec_p50_us"] for b in std_pf])
    ap1_99 = np.array([b["summary"]["procs"]["applyARPF-1"]["exec_p99_us"] for b in std_pf])
    ap2_99 = np.array([b["summary"]["procs"]["applyARPF-2"]["exec_p99_us"] for b in std_pf])
    ax_ap.plot(ps, ap1, "-o", color="#2563eb", lw=2.0, ms=5.8, label="applyARPF-1 p50 (1 kHz)")
    ax_ap.plot(ps, ap2, "-s", color="#059669", lw=2.0, ms=5.8, label="applyARPF-2 p50 (2 kHz)")
    ax_ap.fill_between(ps, ap1, ap1_99, color="#2563eb", alpha=0.14, label="Stg1 p50–p99")
    ax_ap.fill_between(ps, ap2, ap2_99, color="#059669", alpha=0.14, label="Stg2 p50–p99")
    for xv, y1, y2 in zip(ps, ap1, ap2):
        if int(xv) == 8:
            continue
        dx = -16 if int(xv) == 64 else 0
        ax_ap.annotate(
            f"{y1:.0f} µs",
            (xv, y1),
            xytext=(dx, 7),
            textcoords="offset points",
            ha="center",
            fontsize=7.3,
            color="#1d4ed8",
        )
        ax_ap.annotate(
            f"{y2:.0f} µs",
            (xv, y2),
            xytext=(dx, -13),
            textcoords="offset points",
            ha="center",
            fontsize=7.3,
            color="#047857",
        )
    ax_ap.set_xticks([4, 8, 16, 32, 64])
    ax_ap.set_xlim(0, 69)
    ax_ap.set_ylim(0, max(ap1_99) * 1.22)
    ax_ap.set_xlabel("AR Filter Order P")
    ax_ap.set_ylabel("Real-Time Inference Latency [µs / frame]")
    ax_ap.set_title("Real-Time Predictor Latency (applyARPF, 0 Timeouts)")
    ax_ap.grid(True, alpha=0.28)
    ax_ap.legend(loc="upper left", framealpha=0.92, fontsize=7.2)

    # Bottom-right: Accuracy vs Total Predictive CPU Pareto Frontier
    ax_pa = fig.add_subplot(gs_bot[0, 2])
    offsets = {
        "integrator": (6, -24),
        "ar4": (12, -2),
        "ar8": (10, -4),
        "ar16": (-12, 11),
        "ar32": (8, -6),
        "ar32_n4096": (4, -24),
        "ar64": (8, -6),
        "ar64_n4096": (-82, -24),
    }
    for b in bundles:
        sp = b["spec"]
        pr = b["summary"]["procs"]
        pf_cpu = sum(
            pr.get(nm, {}).get("cl_cpu_pct", 0.0)
            for nm in ("mkARPF-1", "mkARPF-2", "applyARPF-1", "applyARPF-2")
        )
        vis_sr = b["summary"]["vis_final_sr_pct"]
        ax_pa.scatter(
            [pf_cpu],
            [vis_sr],
            color=sp["color"],
            marker=sp["marker"],
            s=140 if sp["key"] in ("ar16", "ar32_n4096", "ar64_n4096") else 80,
            edgecolor="#0f172a",
            lw=0.9,
            zorder=5,
        )
        dx, dy = offsets.get(sp["key"], (6, 4))
        ax_pa.annotate(
            f"{sp['short']}\n({vis_sr:.1f}%, {pf_cpu:.0f}%)",
            (pf_cpu, vis_sr),
            textcoords="offset points",
            xytext=(dx, dy),
            fontsize=7.1,
            fontweight="bold",
            color=sp["color"],
        )
    # Draw Pareto frontier (Integrator -> AR(8) -> AR(16) -> AR(32)* -> AR(64)*)
    pareto_keys = ["integrator", "ar8", "ar16", "ar32_n4096", "ar64_n4096"]
    bmap = {b["spec"]["key"]: b for b in bundles}
    px_v = [
        sum(
            bmap[k]["summary"]["procs"].get(nm, {}).get("cl_cpu_pct", 0.0)
            for nm in ("mkARPF-1", "mkARPF-2", "applyARPF-1", "applyARPF-2")
        )
        for k in pareto_keys
    ]
    py_v = [bmap[k]["summary"]["vis_final_sr_pct"] for k in pareto_keys]
    ax_pa.plot(px_v, py_v, "--", color="#059669", lw=1.4, alpha=0.65, label="Pareto Frontier")
    ax_pa.set_xlim(-22, max(px_v) * 1.12)
    ax_pa.set_ylim(70.5, 83.2)
    ax_pa.set_xlabel("Total Predictive Control CPU Load [% of 1 Core]")
    ax_pa.set_ylabel("Final Visible (0.75 µm) Strehl Ratio [%]")
    ax_pa.set_title("Accuracy–Compute Pareto Frontier (AR(16) Knee)")
    ax_pa.grid(True, alpha=0.28)
    ax_pa.legend(loc="lower right", framealpha=0.92)

    fig.savefig(out_dir / "ar_order_psf_and_compute_2x3.png")
    plt.close(fig)
