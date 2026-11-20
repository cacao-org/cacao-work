#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CSS and zero-dependency vanilla JS assets for the cacao-work web repository."""

from __future__ import annotations

CSS_STYLES = """\
:root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-alt: #f1f5f9;
  --text: #0f172a;
  --muted: #475569;
  --border: #e2e8f0;
  --accent: #1d4ed8;
  --accent-hover: #1e40af;
  --accent-soft: #eff6ff;
  --good: #059669;
  --good-soft: #ecfdf5;
  --warn: #d97706;
  --warn-soft: #fffbeb;
  --code-bg: #f1f5f9;
  --pre-bg: #0f172a;
  --pre-text: #e2e8f0;
  --shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  --cat-simulation: #7e22ce;
  --cat-simulation-soft: #f3e8ff;
  --cat-simulation-border: #c084fc;
  --cat-simulation-text: #6b21a8;
  --cat-simulation-solid: #7e22ce;
  --cat-calibration: #b45309;
  --cat-calibration-soft: #fef3c7;
  --cat-calibration-border: #f59e0b;
  --cat-calibration-text: #92400e;
  --cat-calibration-solid: #b45309;
  --cat-loop_operation: #0369a1;
  --cat-loop_operation-soft: #e0f2fe;
  --cat-loop_operation-border: #38bdf8;
  --cat-loop_operation-text: #075985;
  --cat-loop_operation-solid: #0369a1;
  --cat-analysis: #047857;
  --cat-analysis-soft: #d1fae5;
  --cat-analysis-border: #34d399;
  --cat-analysis-text: #065f46;
  --cat-analysis-solid: #047857;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0b1120;
    --surface: #111827;
    --surface-alt: #1e293b;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --border: #334155;
    --accent: #60a5fa;
    --accent-hover: #93c5fd;
    --accent-soft: #172554;
    --good: #34d399;
    --good-soft: #064e3b;
    --warn: #fbbf24;
    --warn-soft: #451a03;
    --code-bg: #1e293b;
    --pre-bg: #020617;
    --pre-text: #e2e8f0;
    --shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
    --cat-simulation: #a855f7;
    --cat-simulation-soft: rgba(147, 51, 234, 0.20);
    --cat-simulation-border: #9333ea;
    --cat-simulation-text: #e9d5ff;
    --cat-simulation-solid: #7e22ce;
    --cat-calibration: #f59e0b;
    --cat-calibration-soft: rgba(217, 119, 6, 0.22);
    --cat-calibration-border: #d97706;
    --cat-calibration-text: #fde68a;
    --cat-calibration-solid: #b45309;
    --cat-loop_operation: #38bdf8;
    --cat-loop_operation-soft: rgba(2, 132, 199, 0.22);
    --cat-loop_operation-border: #0284c7;
    --cat-loop_operation-text: #bae6fd;
    --cat-loop_operation-solid: #0369a1;
    --cat-analysis: #34d399;
    --cat-analysis-soft: rgba(5, 150, 105, 0.22);
    --cat-analysis-border: #059669;
    --cat-analysis-text: #a7f3d0;
    --cat-analysis-solid: #047857;
  }
}
:root[data-theme="dark"] {
  --bg: #0b1120;
  --surface: #111827;
  --surface-alt: #1e293b;
  --text: #f1f5f9;
  --muted: #94a3b8;
  --border: #334155;
  --accent: #60a5fa;
  --accent-hover: #93c5fd;
  --accent-soft: #172554;
  --good: #34d399;
  --good-soft: #064e3b;
  --warn: #fbbf24;
  --warn-soft: #451a03;
  --code-bg: #1e293b;
  --pre-bg: #020617;
  --pre-text: #e2e8f0;
  --shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
  --cat-simulation: #a855f7;
  --cat-simulation-soft: rgba(147, 51, 234, 0.20);
  --cat-simulation-border: #9333ea;
  --cat-simulation-text: #e9d5ff;
  --cat-simulation-solid: #7e22ce;
  --cat-calibration: #f59e0b;
  --cat-calibration-soft: rgba(217, 119, 6, 0.22);
  --cat-calibration-border: #d97706;
  --cat-calibration-text: #fde68a;
  --cat-calibration-solid: #b45309;
  --cat-loop_operation: #38bdf8;
  --cat-loop_operation-soft: rgba(2, 132, 199, 0.22);
  --cat-loop_operation-border: #0284c7;
  --cat-loop_operation-text: #bae6fd;
  --cat-loop_operation-solid: #0369a1;
  --cat-analysis: #34d399;
  --cat-analysis-soft: rgba(5, 150, 105, 0.22);
  --cat-analysis-border: #059669;
  --cat-analysis-text: #a7f3d0;
  --cat-analysis-solid: #047857;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.58;
}
.site-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 30;
  box-shadow: var(--shadow);
}
.nav-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0.65rem 1.25rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
}
.brand {
  font-weight: 700;
  font-size: 0.96rem;
  color: var(--text);
  text-decoration: none;
}
.nav-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}
.nav-links a, .theme-btn {
  text-decoration: none;
  color: var(--muted);
  font-size: 0.87rem;
  font-weight: 500;
  padding: 0.32rem 0.68rem;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
}
.nav-links a:hover, .theme-btn:hover {
  color: var(--accent);
  background: var(--accent-soft);
}
.nav-links a.active {
  color: var(--accent);
  background: var(--accent-soft);
  border-color: var(--border);
}
.subnav-bar {
  background: var(--surface-alt);
  border-bottom: 1px solid var(--border);
}
.subnav-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0.45rem 1.25rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.subnav-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.subnav-tabs a {
  text-decoration: none;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
  padding: 0.3rem 0.72rem;
  border-radius: 6px;
  border: 1px solid transparent;
}
.subnav-tabs a:hover {
  color: var(--accent);
  background: var(--surface);
}
.subnav-tabs a.active {
  color: var(--accent);
  background: var(--surface);
  border-color: var(--border);
  box-shadow: var(--shadow);
}
.sim-switcher {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.82rem;
  color: var(--muted);
}
.sim-switcher select {
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.82rem;
  max-width: 280px;
}
main.container {
  max-width: 1280px;
  margin: 1.25rem auto 2.5rem;
  padding: 1.75rem 2rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
}
@media (max-width: 720px) {
  main.container { margin: 0.65rem; padding: 1rem; }
}
.breadcrumb {
  font-size: 0.82rem;
  color: var(--muted);
  margin-bottom: 0.65rem;
}
.breadcrumb a { color: var(--muted); text-decoration: none; }
.breadcrumb a:hover { color: var(--accent); text-decoration: underline; }
h1, h2, h3, h4 {
  line-height: 1.25;
  margin-top: 1.6rem;
  margin-bottom: 0.7rem;
}
h1 {
  margin-top: 0;
  font-size: 1.65rem;
  border-bottom: 2px solid var(--border);
  padding-bottom: 0.5rem;
}
h2 {
  font-size: 1.26rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.3rem;
}
a { color: var(--accent); }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.87em;
  background: var(--code-bg);
  padding: 0.14rem 0.34rem;
  border-radius: 4px;
}
.pre-wrap {
  position: relative;
  margin: 0.85rem 0;
}
pre {
  background: var(--pre-bg);
  color: var(--pre-text);
  padding: 0.95rem 1rem;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.84rem;
  margin: 0;
}
pre code {
  background: transparent;
  padding: 0;
  color: inherit;
}
.copy-btn {
  position: absolute;
  top: 0.45rem;
  right: 0.5rem;
  padding: 0.2rem 0.55rem;
  font-size: 0.74rem;
  font-weight: 600;
  border-radius: 5px;
  border: 1px solid #475569;
  background: #1e293b;
  color: #e2e8f0;
  cursor: pointer;
  opacity: 0.85;
}
.copy-btn:hover { opacity: 1; background: var(--accent); border-color: var(--accent); }
blockquote.callout {
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  border-left: 4px solid var(--accent);
  background: var(--accent-soft);
  border-radius: 0 8px 8px 0;
}
blockquote.callout p { margin: 0.25rem 0; }
.table-wrap {
  overflow-x: auto;
  margin: 0.85rem 0 1.4rem;
  border: 1px solid var(--border);
  border-radius: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
th, td {
  padding: 0.5rem 0.7rem;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
th {
  background: var(--surface-alt);
  font-weight: 600;
}
th.sort-col { cursor: pointer; user-select: none; }
th.sort-col:hover { color: var(--accent); }
th.sort-col::after { content: " ⇅"; font-size: 0.72em; opacity: 0.45; }
th.sort-asc::after { content: " ▲"; opacity: 0.95; color: var(--accent); }
th.sort-desc::after { content: " ▼"; opacity: 0.95; color: var(--accent); }
tr:last-child td { border-bottom: none; }
tbody tr:hover { background: var(--surface-alt); }
.wrap-cell {
  white-space: normal;
  min-width: 220px;
}
.param-cell {
  white-space: normal;
  min-width: 230px;
  max-width: 390px;
}
.param-list, .badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.32rem;
  margin: 0.35rem 0;
}
.metric-pill {
  display: inline-block;
  padding: 0.14rem 0.5rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--text);
}
.metric-pill-accent {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}
.param-pill {
  display: inline-block;
  padding: 0.12rem 0.44rem;
  border-radius: 6px;
  font-size: 0.77rem;
  line-height: 1.35;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--muted);
}
.param-pill-diff {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--text);
}
.param-pill-base {
  background: var(--surface);
  border: 1px dashed var(--border);
  color: var(--muted);
  font-weight: 600;
}
.shared-params {
  margin: -0.75rem 0 1.4rem;
  padding: 0.55rem 0.85rem;
  border-radius: 8px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  font-size: 0.82rem;
  color: var(--muted);
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: 0.75rem;
  margin: 1rem 0 1.25rem;
}
.kpi-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.75rem 0.9rem;
  background: var(--surface-alt);
}
.kpi-label { font-size: 0.76rem; color: var(--muted); font-weight: 600; }
.kpi-value { font-size: 1.25rem; font-weight: 700; margin: 0.15rem 0; }
.kpi-sub { font-size: 0.75rem; color: var(--muted); }
.subpage-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(235px, 1fr));
  gap: 0.85rem;
  margin: 1rem 0 1.5rem;
}
.subpage-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem;
  background: var(--surface-alt);
  text-decoration: none;
  color: var(--text);
  transition: border-color 0.15s, transform 0.12s;
}
.subpage-card:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
}
.subpage-card h3 { margin: 0 0 0.35rem; font-size: 1.02rem; color: var(--accent); }
.subpage-card p { margin: 0; font-size: 0.84rem; color: var(--muted); }
.subpage-cta { margin-top: 0.65rem; font-size: 0.82rem; font-weight: 600; color: var(--accent); }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  margin: 0.75rem 0;
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--surface-alt);
}
.toolbar-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}
.search-input, .select-input {
  padding: 0.34rem 0.62rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.84rem;
}
.chip-btn, .btn-sm {
  padding: 0.28rem 0.62rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
}
.chip-btn:hover, .btn-sm:hover { border-color: var(--accent); color: var(--accent); }
.chip-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #ffffff;
}
.btn {
  display: inline-block;
  padding: 0.34rem 0.72rem;
  border-radius: 6px;
  background: var(--accent);
  color: #ffffff;
  text-decoration: none;
  font-size: 0.84rem;
  font-weight: 500;
  border: 1px solid transparent;
  cursor: pointer;
}
.btn:hover { background: var(--accent-hover); }
.btn-secondary {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
}
.btn-secondary:hover { background: var(--surface-alt); color: var(--accent); }
.sublinks-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.28rem;
  font-size: 0.77rem;
}
.sublinks-row a {
  padding: 0.08rem 0.38rem;
  border-radius: 4px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  text-decoration: none;
  color: var(--muted);
}
.sublinks-row a:hover { color: var(--accent); border-color: var(--accent); }
.cmp-drawer {
  border: 1px solid var(--accent);
  border-radius: 10px;
  padding: 1rem;
  background: var(--surface-alt);
  margin: 0.75rem 0 1rem;
}
.toc-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.38rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-alt);
  margin: 0.75rem 0 1.25rem;
  font-size: 0.8rem;
}
.toc-label { font-weight: 700; color: var(--muted); margin-right: 0.25rem; }
.toc-chip {
  padding: 0.16rem 0.52rem;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
  text-decoration: none;
}
.toc-chip:hover { border-color: var(--accent); color: var(--accent); }
.figure-stack, .figure-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.15rem;
  margin: 1rem 0 1.4rem;
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
  gap: 1rem;
  margin: 0.85rem 0 1.35rem;
}
figure.report-figure {
  margin: 0;
  padding: 0.7rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-alt);
}
figure.report-figure img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 6px;
  background: #ffffff;
  cursor: zoom-in;
}
figure.report-figure video {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 6px;
  background: #0f172a;
}
figure.report-figure figcaption {
  margin-top: 0.45rem;
  font-size: 0.86rem;
  font-weight: 500;
  color: var(--muted);
  text-align: center;
}
.mermaid-wrap {
  overflow-x: auto;
  margin: 1rem 0;
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #ffffff;
}
pre.mermaid {
  background: transparent;
  color: #0f172a;
  margin: 0;
  text-align: center;
}
.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.5rem;
  margin-bottom: 0.8rem;
}
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.bench-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.8rem;
  margin: 0.8rem 0 1.2rem;
}
.bench-card {
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 0.75rem 0.9rem;
  background: var(--surface-alt);
  font-size: 0.83rem;
}
.bench-card-hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.45rem;
}
.bench-kv {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.18rem 0.55rem;
  font-size: 0.78rem;
}
.bench-kv dt { color: var(--muted); font-family: monospace; }
.bench-kv dd { margin: 0; font-family: monospace; word-break: break-all; }
.explorer-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem;
  background: var(--surface-alt);
  margin: 1rem 0 1.4rem;
}
.canvas-wrap {
  position: relative;
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem;
}
canvas.chart-canvas {
  display: block;
  width: 100%;
  height: 310px;
}
.canvas-tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(15, 23, 42, 0.92);
  color: #f8fafc;
  padding: 0.35rem 0.55rem;
  border-radius: 6px;
  font-size: 0.76rem;
  white-space: nowrap;
  display: none;
  z-index: 10;
}
.hbar-list { display: flex; flex-direction: column; gap: 0.45rem; margin-top: 0.65rem; }
.hbar-row {
  display: grid;
  grid-template-columns: minmax(220px, 290px) 1fr 80px;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.82rem;
}
.hbar-label {
  display: flex;
  align-items: center;
  gap: 0.42rem;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
@media (max-width: 640px) {
  .hbar-row { grid-template-columns: 155px 1fr 64px; }
}
.hbar-track {
  height: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  overflow: hidden;
}
.hbar-fill { height: 100%; background: var(--accent); border-radius: 999px; }
.hbar-fill.cat-simulation { background: var(--cat-simulation-solid); }
.hbar-fill.cat-calibration { background: var(--cat-calibration-solid); }
.hbar-fill.cat-loop_operation { background: var(--cat-loop_operation-solid); }
.hbar-fill.cat-analysis { background: var(--cat-analysis-solid); }
.customizer-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: 0.65rem;
  margin: 0.65rem 0;
}
.field-box {
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
  font-size: 0.79rem;
}
.field-box label { font-weight: 600; color: var(--muted); }
.field-box input, .field-box select {
  padding: 0.32rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.83rem;
}
.checklist { display: flex; flex-direction: column; gap: 0.7rem; margin: 0.8rem 0; }
.checklist-item {
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 0.75rem 0.9rem;
  background: var(--surface-alt);
}
.checklist-item.done { border-color: var(--good); background: var(--good-soft); }
.checklist-item.cat-simulation { border-left: 4px solid var(--cat-simulation); }
.checklist-item.cat-calibration { border-left: 4px solid var(--cat-calibration); }
.checklist-item.cat-loop_operation { border-left: 4px solid var(--cat-loop_operation); }
.checklist-item.cat-analysis { border-left: 4px solid var(--cat-analysis); }
.checklist-item.done.cat-simulation { border-left-color: var(--cat-simulation); }
.checklist-item.done.cat-calibration { border-left-color: var(--cat-calibration); }
.checklist-item.done.cat-loop_operation { border-left-color: var(--cat-loop_operation); }
.checklist-item.done.cat-analysis { border-left-color: var(--cat-analysis); }
.checklist-hdr {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem;
  font-weight: 700;
  cursor: pointer;
}
.progress-track {
  width: 180px;
  height: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  overflow: hidden;
}
.progress-fill { height: 100%; background: var(--good); transition: width 0.15s; }
.detail-row td {
  background: var(--surface);
  white-space: normal;
  font-size: 0.82rem;
}
.cat-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 0.95rem;
  align-items: center;
  padding: 0.55rem 0.85rem;
  margin: 0.7rem 0 1rem;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--surface-alt);
  font-size: 0.8rem;
}
.cat-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
}
.cat-dot {
  display: inline-block;
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 999px;
  margin-right: 0.32rem;
  vertical-align: middle;
  flex-shrink: 0;
}
.cat-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.11rem 0.48rem;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 600;
  line-height: 1.35;
  white-space: nowrap;
  border: 1px solid var(--border);
}
.cat-badge.cat-simulation {
  background: var(--cat-simulation-soft);
  border-color: var(--cat-simulation-border);
  color: var(--cat-simulation-text);
}
.cat-badge.cat-simulation .cat-dot { background: var(--cat-simulation); }
.cat-badge.cat-calibration {
  background: var(--cat-calibration-soft);
  border-color: var(--cat-calibration-border);
  color: var(--cat-calibration-text);
}
.cat-badge.cat-calibration .cat-dot { background: var(--cat-calibration); }
.cat-badge.cat-loop_operation {
  background: var(--cat-loop_operation-soft);
  border-color: var(--cat-loop_operation-border);
  color: var(--cat-loop_operation-text);
}
.cat-badge.cat-loop_operation .cat-dot { background: var(--cat-loop_operation); }
.cat-badge.cat-analysis {
  background: var(--cat-analysis-soft);
  border-color: var(--cat-analysis-border);
  color: var(--cat-analysis-text);
}
.cat-badge.cat-analysis .cat-dot { background: var(--cat-analysis); }
.cat-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.cat-pill.cat-simulation {
  border-color: var(--cat-simulation-border);
  color: var(--cat-simulation-text);
}
.cat-pill.cat-simulation .cat-dot { background: var(--cat-simulation); }
.cat-pill.cat-simulation.active {
  background: var(--cat-simulation-solid);
  border-color: var(--cat-simulation-solid);
  color: #ffffff;
}
.cat-pill.cat-calibration {
  border-color: var(--cat-calibration-border);
  color: var(--cat-calibration-text);
}
.cat-pill.cat-calibration .cat-dot { background: var(--cat-calibration); }
.cat-pill.cat-calibration.active {
  background: var(--cat-calibration-solid);
  border-color: var(--cat-calibration-solid);
  color: #ffffff;
}
.cat-pill.cat-loop_operation {
  border-color: var(--cat-loop_operation-border);
  color: var(--cat-loop_operation-text);
}
.cat-pill.cat-loop_operation .cat-dot { background: var(--cat-loop_operation); }
.cat-pill.cat-loop_operation.active {
  background: var(--cat-loop_operation-solid);
  border-color: var(--cat-loop_operation-solid);
  color: #ffffff;
}
.cat-pill.cat-analysis {
  border-color: var(--cat-analysis-border);
  color: var(--cat-analysis-text);
}
.cat-pill.cat-analysis .cat-dot { background: var(--cat-analysis); }
.cat-pill.cat-analysis.active {
  background: var(--cat-analysis-solid);
  border-color: var(--cat-analysis-solid);
  color: #ffffff;
}
.cat-pill.active .cat-dot { background: #ffffff; }
tr.cat-group-row td {
  white-space: normal;
  font-size: 0.84rem;
  padding: 0.5rem 0.75rem;
}
.cat-group-hdr {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.cat-group-title {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.cat-group-count { font-size: 0.79rem; font-weight: 600; opacity: 0.88; }
tr.cat-group-row.cat-simulation,
tbody tr.cat-group-row.cat-simulation:hover {
  background: var(--cat-simulation-soft);
  color: var(--cat-simulation-text);
  border-top: 2px solid var(--cat-simulation-border);
}
tr.cat-group-row.cat-simulation td:first-child {
  border-left: 4px solid var(--cat-simulation);
}
tr.cat-group-row.cat-calibration,
tbody tr.cat-group-row.cat-calibration:hover {
  background: var(--cat-calibration-soft);
  color: var(--cat-calibration-text);
  border-top: 2px solid var(--cat-calibration-border);
}
tr.cat-group-row.cat-calibration td:first-child {
  border-left: 4px solid var(--cat-calibration);
}
tr.cat-group-row.cat-loop_operation,
tbody tr.cat-group-row.cat-loop_operation:hover {
  background: var(--cat-loop_operation-soft);
  color: var(--cat-loop_operation-text);
  border-top: 2px solid var(--cat-loop_operation-border);
}
tr.cat-group-row.cat-loop_operation td:first-child {
  border-left: 4px solid var(--cat-loop_operation);
}
tr.cat-group-row.cat-analysis,
tbody tr.cat-group-row.cat-analysis:hover {
  background: var(--cat-analysis-soft);
  color: var(--cat-analysis-text);
  border-top: 2px solid var(--cat-analysis-border);
}
tr.cat-group-row.cat-analysis td:first-child {
  border-left: 4px solid var(--cat-analysis);
}
.cat-row.cat-simulation td:first-child,
.cat-detail-row.cat-simulation td:first-child {
  border-left: 4px solid var(--cat-simulation);
}
.cat-row.cat-calibration td:first-child,
.cat-detail-row.cat-calibration td:first-child {
  border-left: 4px solid var(--cat-calibration);
}
.cat-row.cat-loop_operation td:first-child,
.cat-detail-row.cat-loop_operation td:first-child {
  border-left: 4px solid var(--cat-loop_operation);
}
.cat-row.cat-analysis td:first-child,
.cat-detail-row.cat-analysis td:first-child {
  border-left: 4px solid var(--cat-analysis);
}
.section-cat-badges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  vertical-align: middle;
  margin-left: 0.45rem;
}
.cat-empty-note {
  padding: 0.85rem 1rem;
  border: 1px dashed var(--border);
  border-radius: 8px;
  color: var(--muted);
  text-align: center;
  margin: 0.65rem 0;
}
.sim-filter-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.75rem 0.9rem;
  margin: 0.75rem 0;
  background: var(--surface-alt);
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}
.filter-categories {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  align-items: stretch;
}
.filter-cat-box {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.48rem 0.68rem;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  gap: 0.38rem;
}
.filter-cat-box.cat-loop_operation { border-left: 4px solid var(--cat-loop_operation); }
.filter-cat-box.cat-calibration { border-left: 4px solid var(--cat-calibration); }
.filter-cat-title {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  display: flex;
  align-items: center;
}
.filter-cat-box.cat-loop_operation .filter-cat-title .cat-dot {
  background: var(--cat-loop_operation);
}
.filter-cat-box.cat-calibration .filter-cat-title .cat-dot {
  background: var(--cat-calibration);
}
.tristate {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--surface-alt);
}
.tristate-btn {
  border: none;
  border-right: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  padding: 0.28rem 0.56rem;
  font-size: 0.79rem;
  font-weight: 500;
  cursor: pointer;
}
.tristate-btn:last-child { border-right: none; }
.tristate-btn:hover { background: var(--surface); color: var(--text); }
.tristate-btn.active { font-weight: 700; }
.tristate-btn.active[data-val="any"] {
  background: var(--accent-soft);
  color: var(--accent);
}
.tristate-btn.active[data-val="on"] {
  background: #047857;
  color: #ffffff;
}
.tristate-btn.active[data-val="off"] {
  background: #475569;
  color: #ffffff;
}
.filter-actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border);
}
.filter-inline-label {
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--muted);
  margin-right: 0.15rem;
}
.lightbox-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(2, 6, 23, 0.88);
  display: none;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 1.5rem;
}
.lightbox-backdrop.open { display: flex; }
.lightbox-backdrop img {
  max-width: 94vw;
  max-height: 82vh;
  border-radius: 8px;
  background: #ffffff;
}
.lightbox-bar {
  margin-top: 0.75rem;
  color: #f1f5f9;
  display: flex;
  align-items: center;
  gap: 1rem;
  font-size: 0.9rem;
}
.muted { color: var(--muted); font-size: 0.88em; }
.hidden { display: none !important; }
.site-footer {
  max-width: 1280px;
  margin: 0 auto 2rem;
  padding: 0 1.25rem;
  color: var(--muted);
  font-size: 0.84rem;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
}
"""

COMMON_JS = """\
(function() {
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem("cacao_theme"); } catch (e) {}
  if (saved === "dark" || saved === "light") {
    root.setAttribute("data-theme", saved);
  }
  var tBtn = document.getElementById("theme-toggle");
  if (tBtn) {
    tBtn.addEventListener("click", function() {
      var cur = root.getAttribute("data-theme");
      var isDark = cur === "dark" || (!cur && window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
      var next = isDark ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("cacao_theme", next); } catch (e) {}
    });
  }

  document.querySelectorAll("pre").forEach(function(pre) {
    if (pre.classList.contains("mermaid") || pre.parentElement.classList.contains("pre-wrap")) {
      return;
    }
    var wrap = document.createElement("div");
    wrap.className = "pre-wrap";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.addEventListener("click", function() {
      var txt = pre.innerText || pre.textContent || "";
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(function() {
          btn.textContent = "Copied";
          setTimeout(function() { btn.textContent = "Copy"; }, 1200);
        });
      }
    });
    wrap.appendChild(btn);
  });

  function parseCellVal(text) {
    var s = (text || "").replace(/,/g, "").trim();
    if (!s || s === "—" || s === "-") return null;
    var m = s.match(/^([+-]?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)/);
    if (m) return parseFloat(m[1]);
    return null;
  }

  document.querySelectorAll('div.table-wrap[data-sortable="1"] table, table[data-sortable="1"]')
    .forEach(function(tbl) {
      var thead = tbl.querySelector("thead");
      var tbodies = Array.from(tbl.querySelectorAll("tbody"));
      if (!thead || !tbodies.length) return;
      var ths = Array.from(thead.querySelectorAll("th"));
      ths.forEach(function(th, colIdx) {
        if (th.hasAttribute("data-nosort")) return;
        th.classList.add("sort-col");
        th.addEventListener("click", function() {
          var asc = !th.classList.contains("sort-asc");
          ths.forEach(function(h) { h.classList.remove("sort-asc", "sort-desc"); });
          th.classList.add(asc ? "sort-asc" : "sort-desc");
          tbodies.forEach(function(tbody) {
            var allRows = Array.from(tbody.children).filter(function(el) {
              return el.tagName === "TR";
            });
            var groupRows = [];
            var pairs = [];
            for (var i = 0; i < allRows.length; i++) {
              var r = allRows[i];
              if (r.classList.contains("cat-group-row")) {
                groupRows.push(r);
                continue;
              }
              if (r.classList.contains("detail-row")) continue;
              var nxt = allRows[i + 1];
              var det = (nxt && nxt.classList.contains("detail-row")) ? nxt : null;
              if (det) i++;
              pairs.push({ row: r, detail: det });
            }
            pairs.sort(function(a, b) {
              var ca = a.row.children[colIdx] ? a.row.children[colIdx].innerText : "";
              var cb = b.row.children[colIdx] ? b.row.children[colIdx].innerText : "";
              var na = parseCellVal(ca);
              var nb = parseCellVal(cb);
              if (na !== null && nb !== null) {
                return asc ? (na - nb) : (nb - na);
              }
              return asc ? ca.localeCompare(cb) : cb.localeCompare(ca);
            });
            groupRows.forEach(function(gr) { tbody.appendChild(gr); });
            pairs.forEach(function(p) {
              tbody.appendChild(p.row);
              if (p.detail) tbody.appendChild(p.detail);
            });
          });
        });
      });
    });

  window.cacaoInitCatFilter = function(opts) {
    var tbl = document.getElementById(opts.tableId);
    if (!tbl) return null;
    var prefix = opts.prefix;
    var rowSel = opts.rowSelector || "tr:not(.cat-group-row):not(.detail-row)";
    var noun = opts.noun || "items";
    var searchEl = opts.searchId ? document.getElementById(opts.searchId) : null;
    var countEl = document.getElementById(prefix + "-visible-count");
    var emptyEl = document.getElementById(prefix + "-empty-msg");
    var catBtns = Array.from(document.querySelectorAll("[data-" + prefix + "-cat]"));
    var actBtns = Array.from(document.querySelectorAll("[data-" + prefix + "-action]"));
    var selected = {};
    catBtns.forEach(function(b) {
      var k = b.getAttribute("data-" + prefix + "-cat");
      if (k && b.classList.contains("active")) selected[k] = true;
    });

    function syncBtns() {
      catBtns.forEach(function(b) {
        var k = b.getAttribute("data-" + prefix + "-cat");
        var on = Boolean(k && selected[k]);
        b.classList.toggle("active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    function apply() {
      var q = searchEl ? searchEl.value.toLowerCase().trim() : "";
      var tbodies = Array.from(tbl.querySelectorAll("tbody.cat-tbody"));
      var targets = tbodies.length ? tbodies : Array.from(tbl.querySelectorAll("tbody"));
      var totalAll = 0;
      var totalVis = 0;
      targets.forEach(function(tb) {
        var grpCat = tb.getAttribute("data-category");
        var rows = Array.from(tb.querySelectorAll(rowSel)).filter(function(r) {
          return !r.classList.contains("cat-group-row") && !r.classList.contains("detail-row");
        });
        var visInGrp = 0;
        rows.forEach(function(tr) {
          totalAll++;
          var c = tr.getAttribute("data-category") || grpCat || "";
          var det = tr.nextElementSibling;
          var hasDet = Boolean(det && det.classList.contains("detail-row"));
          var dTxt = hasDet ? (det.innerText || "") : "";
          var txt = ((tr.innerText || "") + " " + dTxt).toLowerCase();
          var ok = Boolean(selected[c]) &&
            (q === "" || txt.indexOf(q) !== -1) &&
            (!opts.extraPred || opts.extraPred(tr));
          tr.classList.toggle("hidden", !ok);
          if (hasDet && !ok) det.classList.add("hidden");
          if (ok) { visInGrp++; totalVis++; }
        });
        var cntSpan = tb.querySelector(".cat-group-count");
        if (cntSpan) cntSpan.textContent = visInGrp + " / " + rows.length;
        if (tb.classList.contains("cat-tbody")) {
          tb.classList.toggle("hidden", !(grpCat && selected[grpCat]) || visInGrp === 0);
        }
      });
      if (countEl) countEl.textContent = "Showing " + totalVis + " / " + totalAll + " " + noun;
      if (emptyEl) emptyEl.classList.toggle("hidden", totalVis > 0);
    }

    catBtns.forEach(function(b) {
      b.addEventListener("click", function() {
        var k = b.getAttribute("data-" + prefix + "-cat");
        if (!k) return;
        selected[k] = !selected[k];
        syncBtns();
        apply();
      });
    });
    actBtns.forEach(function(b) {
      b.addEventListener("click", function() {
        var act = b.getAttribute("data-" + prefix + "-action");
        catBtns.forEach(function(cb) {
          var k = cb.getAttribute("data-" + prefix + "-cat");
          if (k) selected[k] = (act === "all");
        });
        syncBtns();
        apply();
      });
    });
    if (searchEl) searchEl.addEventListener("input", apply);
    syncBtns();
    apply();
    return { apply: apply };
  };

  var triggers = Array.from(document.querySelectorAll("a.lightbox-trigger"));
  if (triggers.length > 0) {
    var lb = document.createElement("div");
    lb.className = "lightbox-backdrop";
    lb.innerHTML =
      '<img alt=""><div class="lightbox-bar">' +
      '<button type="button" class="btn-sm" id="lb-prev">Prev</button>' +
      '<span id="lb-cap"></span>' +
      '<a id="lb-raw" class="btn-sm" target="_blank" rel="noopener">Open Raw</a>' +
      '<button type="button" class="btn-sm" id="lb-next">Next</button>' +
      '<button type="button" class="btn-sm" id="lb-close">Close (Esc)</button></div>';
    document.body.appendChild(lb);
    var lbImg = lb.querySelector("img");
    var lbCap = lb.querySelector("#lb-cap");
    var lbRaw = lb.querySelector("#lb-raw");
    var curIdx = 0;

    function showLb(idx) {
      curIdx = (idx + triggers.length) % triggers.length;
      var el = triggers[curIdx];
      var href = el.getAttribute("href");
      lbImg.src = href;
      lbRaw.href = href;
      lbCap.textContent = el.getAttribute("data-caption") || "";
      lb.classList.add("open");
    }

    triggers.forEach(function(el, i) {
      el.addEventListener("click", function(ev) {
        if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
        ev.preventDefault();
        showLb(i);
      });
    });
    lb.querySelector("#lb-prev").addEventListener("click", function() { showLb(curIdx - 1); });
    lb.querySelector("#lb-next").addEventListener("click", function() { showLb(curIdx + 1); });
    lb.querySelector("#lb-close").addEventListener("click", function() {
      lb.classList.remove("open");
    });
    lb.addEventListener("click", function(ev) {
      if (ev.target === lb) lb.classList.remove("open");
    });
    document.addEventListener("keydown", function(ev) {
      if (!lb.classList.contains("open")) return;
      if (ev.key === "Escape") lb.classList.remove("open");
      else if (ev.key === "ArrowLeft") showLb(curIdx - 1);
      else if (ev.key === "ArrowRight") showLb(curIdx + 1);
    });
  }
})();
"""

FRONT_PAGE_JS = """\
(function() {
  var techInput = document.getElementById("tech-search");
  var techTbl = document.getElementById("tech-reports-table");
  if (techInput && techTbl) {
    techInput.addEventListener("input", function() {
      var q = techInput.value.toLowerCase().trim();
      techTbl.querySelectorAll("tbody tr").forEach(function(tr) {
        var txt = (tr.innerText || "").toLowerCase();
        tr.classList.toggle("hidden", q !== "" && txt.indexOf(q) === -1);
      });
    });
  }

  var simTbl = document.getElementById("sim-reports-table");
  if (!simTbl) return;
  var simSearch = document.getElementById("sim-search");
  var simCount = document.getElementById("sim-count");
  var simEmpty = document.getElementById("sim-empty-msg");
  var simReset = document.getElementById("sim-filter-reset");
  var ctrlBtns = Array.from(document.querySelectorAll("[data-sim-ctrl]"));
  var triGroups = Array.from(document.querySelectorAll("[data-sim-tri]"));
  var selectedCtrls = {};
  var triState = {};

  ctrlBtns.forEach(function(b) {
    var k = b.getAttribute("data-sim-ctrl");
    if (k && b.classList.contains("active")) selectedCtrls[k] = true;
  });
  triGroups.forEach(function(g) {
    var gk = g.getAttribute("data-sim-tri");
    var act = g.querySelector(".tristate-btn.active");
    if (gk) triState[gk] = act ? (act.getAttribute("data-val") || "any") : "any";
  });

  function applySimFilter() {
    var q = simSearch ? simSearch.value.toLowerCase().trim() : "";
    var rows = Array.from(simTbl.querySelectorAll("tbody tr"));
    var shown = 0;
    rows.forEach(function(tr) {
      var rc = tr.getAttribute("data-ctrl") || "";
      var okCtrl = ctrlBtns.length === 0 || Boolean(selectedCtrls[rc]);
      var okTri = true;
      triGroups.forEach(function(g) {
        var gk = g.getAttribute("data-sim-tri");
        var want = gk ? (triState[gk] || "any") : "any";
        if (want !== "any") {
          var rv = tr.getAttribute("data-" + gk) || "";
          if (rv !== want) okTri = false;
        }
      });
      var txt = (tr.innerText || "").toLowerCase();
      var okQ = q === "" || txt.indexOf(q) !== -1;
      var vis = okCtrl && okTri && okQ;
      tr.classList.toggle("hidden", !vis);
      if (vis) shown++;
    });
    if (simCount) simCount.textContent = shown + " / " + rows.length + " simulations";
    if (simEmpty) simEmpty.classList.toggle("hidden", shown > 0);
  }

  ctrlBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      var k = b.getAttribute("data-sim-ctrl");
      if (!k) return;
      selectedCtrls[k] = !selectedCtrls[k];
      b.classList.toggle("active", selectedCtrls[k]);
      b.setAttribute("aria-pressed", selectedCtrls[k] ? "true" : "false");
      applySimFilter();
    });
  });

  triGroups.forEach(function(g) {
    var gk = g.getAttribute("data-sim-tri");
    var btns = Array.from(g.querySelectorAll(".tristate-btn"));
    btns.forEach(function(b) {
      b.addEventListener("click", function() {
        var v = b.getAttribute("data-val") || "any";
        if (gk) triState[gk] = v;
        btns.forEach(function(x) {
          var on = x === b;
          x.classList.toggle("active", on);
          x.setAttribute("aria-pressed", on ? "true" : "false");
        });
        applySimFilter();
      });
    });
  });

  if (simReset) {
    simReset.addEventListener("click", function() {
      ctrlBtns.forEach(function(b) {
        var k = b.getAttribute("data-sim-ctrl");
        if (k) selectedCtrls[k] = true;
        b.classList.add("active");
        b.setAttribute("aria-pressed", "true");
      });
      triGroups.forEach(function(g) {
        var gk = g.getAttribute("data-sim-tri");
        if (gk) triState[gk] = "any";
        g.querySelectorAll(".tristate-btn").forEach(function(b) {
          var isAny = (b.getAttribute("data-val") || "") === "any";
          b.classList.toggle("active", isAny);
          b.setAttribute("aria-pressed", isAny ? "true" : "false");
        });
      });
      if (simSearch) simSearch.value = "";
      applySimFilter();
    });
  }

  if (simSearch) simSearch.addEventListener("input", applySimFilter);

  var cmpDataEl = document.getElementById("front-sim-compare-data");
  var cmpDrawer = document.getElementById("cmp-drawer");
  var cmpChart = document.getElementById("cmp-chart");
  var cmpMetricSel = document.getElementById("cmp-metric-select");
  if (!cmpDataEl || !cmpDrawer || !cmpChart) return;
  var simMap = {};
  try { simMap = JSON.parse(cmpDataEl.textContent || "{}"); } catch (e) {}

  function getSelectedSlugs() {
    var out = [];
    simTbl.querySelectorAll("input.sim-cmp-cb:checked").forEach(function(cb) {
      out.push(cb.value);
    });
    return out;
  }

  function renderCompareChart() {
    var slugs = getSelectedSlugs();
    if (slugs.length === 0) {
      cmpDrawer.classList.add("hidden");
      return;
    }
    cmpDrawer.classList.remove("hidden");
    var metric = cmpMetricSel ? cmpMetricSel.value : "vis_sr_pct";
    var labels = {
      vis_sr_pct: ["Visible 0.75 um Strehl Ratio [%]", "%", false],
      nir_sr_pct: ["H-Band 1.65 um Strehl Ratio [%]", "%", false],
      wfe_nm: ["Post-SCExAO Wavefront Error [nm] (lower is better)", " nm", false],
      stg1_wfe_nm: ["Post-AO3k Wavefront Error [nm] (lower is better)", " nm", false],
      planet_contrast_3_10ld: ["Coronagraph Mean Planet Contrast 3-10 l/D (log10)", "", true]
    };
    var info = labels[metric] || [metric, "", false];
    var vals = slugs.map(function(s) {
      var d = simMap[s] || {};
      var v = d[metric];
      return typeof v === "number" ? v : null;
    });
    var valid = vals.filter(function(v) { return v !== null; });
    if (valid.length === 0) {
      cmpChart.innerHTML = '<p class="muted">No numeric data for selected metric.</p>';
      return;
    }
    var maxV = Math.max.apply(null, valid);
    if (info[2]) {
      maxV = Math.max.apply(
        null, valid.map(function(v) { return -Math.log10(Math.max(v, 1e-9)); })
      );
    }
    var html = "<strong>" + info[0] + '</strong><div class="hbar-list">';
    slugs.forEach(function(s, idx) {
      var v = vals[idx];
      if (v === null) return;
      var frac = info[2]
        ? ((-Math.log10(Math.max(v, 1e-9))) / Math.max(maxV, 1)) * 100
        : (v / Math.max(maxV, 1e-6)) * 100;
      var vStr = info[2] ? v.toExponential(2) : (v.toFixed(1) + info[1]);
      html += '<div class="hbar-row"><code>' + s + '</code>' +
        '<div class="hbar-track"><div class="hbar-fill" style="width:' +
        Math.min(100, Math.max(3, frac)).toFixed(1) + '%"></div></div>' +
        '<span style="text-align:right;"><strong>' + vStr + "</strong></span></div>";
    });
    html += "</div>";
    cmpChart.innerHTML = html;
  }

  simTbl.querySelectorAll("input.sim-cmp-cb").forEach(function(cb) {
    cb.addEventListener("change", renderCompareChart);
  });
  if (cmpMetricSel) cmpMetricSel.addEventListener("change", renderCompareChart);

  document.querySelectorAll("[data-cmp-preset]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var preset = btn.getAttribute("data-cmp-preset");
      var cbs = Array.from(simTbl.querySelectorAll("input.sim-cmp-cb"));
      cbs.forEach(function(cb) {
        if (preset === "clear") { cb.checked = false; return; }
        var s = cb.value;
        if (preset === "ar-sweep") {
          cb.checked = /(_lowfs_closed|_predictive_ar(4|8|16|32|64))$/.test(s);
        } else if (preset === "eof-vs-ar") {
          cb.checked = /(ar16_w14s|ar16_matched_w14s|eof64_p8|eof128_p8)$/.test(s);
        }
      });
      renderCompareChart();
    });
  });
})();
"""

CONFIG_PAGE_JS = """\
(function() {
  document.querySelectorAll(".gui-tabs").forEach(function(wrap) {
    var btns = Array.from(wrap.querySelectorAll(".tab-btn"));
    var panels = Array.from(wrap.querySelectorAll(".tab-panel"));
    btns.forEach(function(b) {
      b.addEventListener("click", function() {
        var target = b.getAttribute("data-tab");
        btns.forEach(function(x) { x.classList.toggle("active", x === b); });
        panels.forEach(function(p) {
          p.classList.toggle("active", p.getAttribute("data-panel") === target);
        });
      });
    });
  });

  var benchGrid = document.getElementById("bench-card-grid");
  if (benchGrid) {
    var bSearch = document.getElementById("bench-search");
    var bBtns = Array.from(document.querySelectorAll("[data-bench-cat]"));
    var activeCat = "all";
    function filterBench() {
      var q = bSearch ? bSearch.value.toLowerCase().trim() : "";
      benchGrid.querySelectorAll(".bench-card").forEach(function(card) {
        var cat = (card.getAttribute("data-cat") || "").toLowerCase();
        var txt = (card.innerText || "").toLowerCase();
        var ok = (activeCat === "all" || cat === activeCat) &&
          (q === "" || txt.indexOf(q) !== -1);
        card.classList.toggle("hidden", !ok);
      });
    }
    bBtns.forEach(function(btn) {
      btn.addEventListener("click", function() {
        activeCat = btn.getAttribute("data-bench-cat") || "all";
        bBtns.forEach(function(b) { b.classList.toggle("active", b === btn); });
        filterBench();
      });
    });
    if (bSearch) bSearch.addEventListener("input", filterBench);
  }
})();
"""

OPTICAL_PAGE_JS = """\
(function() {
  var dataEl = document.getElementById("optical-explorer-data");
  if (!dataEl) return;
  var payload = {};
  try { payload = JSON.parse(dataEl.textContent || "{}"); } catch (e) { return; }
  var canvas = document.getElementById("opt-canvas");
  var tip = document.getElementById("opt-tooltip");
  var ctrlBar = document.getElementById("opt-controls");
  if (!canvas || !canvas.getContext) return;
  var tabBtns = Array.from(document.querySelectorAll("[data-opt-tab]"));
  var activeTab = tabBtns[0] ? tabBtns[0].getAttribute("data-opt-tab") : "wfe";
  var lastPlot = null;

  function drawPlot(spec) {
    lastPlot = spec;
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 760;
    var h = 310;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    var pad = { l: 58, r: 20, t: 24, b: 38 };
    var pw = Math.max(80, w - pad.l - pad.r);
    var ph = Math.max(80, h - pad.t - pad.b);
    var xs = spec.x;
    var xmin = spec.xmin, xmax = spec.xmax;
    var ymin = spec.ymin, ymax = spec.ymax;
    var spanX = Math.max(xmax - xmin, 1e-9);
    var spanY = Math.max(ymax - ymin, 1e-9);

    var isDark = document.documentElement.getAttribute("data-theme") === "dark" ||
      (!document.documentElement.getAttribute("data-theme") && window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
    var gridCol = isDark ? "#334155" : "#e2e8f0";
    var textCol = isDark ? "#cbd5e1" : "#475569";

    ctx.strokeStyle = gridCol;
    ctx.fillStyle = textCol;
    ctx.font = "11px sans-serif";
    for (var gi = 0; gi <= 4; gi++) {
      var gy = pad.t + (ph * gi) / 4;
      ctx.beginPath();
      ctx.moveTo(pad.l, gy);
      ctx.lineTo(pad.l + pw, gy);
      ctx.stroke();
      var yv = ymax - (spanY * gi) / 4;
      var yLbl = spec.isLog ? ("1e" + yv.toFixed(1)) : (yv >= 100 ? yv.toFixed(0) : yv.toFixed(2));
      ctx.fillText(yLbl, 6, gy + 4);
    }
    for (var xi = 0; xi <= 5; xi++) {
      var gx = pad.l + (pw * xi) / 5;
      var xv = xmin + (spanX * xi) / 5;
      ctx.fillText(xv.toFixed(spec.xDec || 1), gx - 10, pad.t + ph + 16);
    }
    ctx.fillText(spec.xLabel || "", pad.l + pw / 2 - 40, h - 5);
    ctx.fillText(spec.title || "", pad.l, 14);

    spec.series.forEach(function(ser) {
      if (!ser.on) return;
      ctx.strokeStyle = ser.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      var started = false;
      for (var i = 0; i < xs.length; i++) {
        if (xs[i] < xmin || xs[i] > xmax) continue;
        var yRaw = ser.y[i];
        if (yRaw === null || yRaw === undefined || !isFinite(yRaw)) continue;
        var px = pad.l + ((xs[i] - xmin) / spanX) * pw;
        var py = pad.t + (1 - (yRaw - ymin) / spanY) * ph;
        if (!started) { ctx.moveTo(px, py); started = true; }
        else ctx.lineTo(px, py);
      }
      ctx.stroke();
    });
    lastPlot.pad = pad;
    lastPlot.pw = pw;
    lastPlot.ph = ph;
  }

  function renderActive() {
    if (activeTab === "wfe" && payload.wf_timeseries) {
      var wf = payload.wf_timeseries;
      var x = wf.t_phys_s || [];
      ctrlBar.innerHTML =
        '<label><input type="checkbox" id="tr-raw" checked> Raw WFE</label> ' +
        '<label><input type="checkbox" id="tr-s1" checked> Stage-1 WFE</label> ' +
        '<label><input type="checkbox" id="tr-fin" checked> Final WFE</label>';
      var series = [
        { name: "Raw [nm]", y: wf.rms_raw_nm || [], color: "#94a3b8", on: true },
        { name: "Stage-1 [nm]", y: wf.rms_stg1_nm || [], color: "#2563eb", on: true },
        { name: "Final [nm]", y: wf.rms_final_nm || [], color: "#059669", on: true }
      ];
      function upd() {
        series[0].on = document.getElementById("tr-raw").checked;
        series[1].on = document.getElementById("tr-s1").checked;
        series[2].on = document.getElementById("tr-fin").checked;
        var allY = [];
        series.forEach(function(s) { if (s.on) allY = allY.concat(s.y); });
        var ymin = allY.length ? Math.min.apply(null, allY) * 0.9 : 0;
        var ymax = allY.length ? Math.max.apply(null, allY) * 1.05 : 100;
        drawPlot({
          title: "Wavefront Error vs Physical Time [nm]",
          xLabel: "Time [s]",
          x: x,
          xmin: x[0] || 0,
          xmax: x[x.length - 1] || 1,
          ymin: ymin,
          ymax: ymax,
          series: series,
          xDec: 2
        });
      }
      ctrlBar.querySelectorAll("input").forEach(function(i) { i.addEventListener("change", upd); });
      upd();
    } else if (activeTab === "strehl" && payload.strehl_timeseries) {
      var sr = payload.strehl_timeseries;
      var x = sr.t_phys_s || [];
      ctrlBar.innerHTML =
        '<label><input type="checkbox" id="sr-v" checked> Vis Final SR [%]</label> ' +
        '<label><input type="checkbox" id="sr-h" checked> H Final SR [%]</label> ' +
        '<label><input type="checkbox" id="sr-vs1" checked> Vis Stg1 SR [%]</label>';
      var series = [
        { name: "Vis Final [%]", y: (sr.vis_final_inst || []).map(function(v) { return v * 100; }),
          color: "#2563eb", on: true },
        { name: "H Final [%]", y: (sr.nir_final_inst || []).map(function(v) { return v * 100; }),
          color: "#059669", on: true },
        { name: "Vis Stg1 [%]", y: (sr.vis_stg1_inst || []).map(function(v) { return v * 100; }),
          color: "#d97706", on: true }
      ];
      function updS() {
        series[0].on = document.getElementById("sr-v").checked;
        series[1].on = document.getElementById("sr-h").checked;
        series[2].on = document.getElementById("sr-vs1").checked;
        drawPlot({
          title: "Instantaneous Optical Strehl Ratio [%]",
          xLabel: "Time [s]",
          x: x,
          xmin: x[0] || 0,
          xmax: x[x.length - 1] || 1,
          ymin: 0,
          ymax: 102,
          series: series,
          xDec: 2
        });
      }
      ctrlBar.querySelectorAll("input").forEach(function(i) {
        i.addEventListener("change", updS);
      });
      updS();
    } else if (activeTab === "modal" && payload.modal_stages && payload.modal_stages.length) {
      var opts = payload.modal_stages.map(function(st, i) {
        return '<option value="' + i + '">' + st.label + " (" + st.n_modes + " modes)</option>";
      }).join("");
      ctrlBar.innerHTML =
        'Stage: <select class="select-input" id="m-stg-sel">' + opts + "</select>";
      var sel = document.getElementById("m-stg-sel");
      function updM() {
        var st = payload.modal_stages[parseInt(sel.value, 10) || 0];
        var sList = [{ name: "Modal Gain", y: st.mgain || [], color: "#2563eb", on: true }];
        if (st.rel_grad) {
          sList.push({ name: "Rel. Grad", y: st.rel_grad, color: "#059669", on: true });
        }
        drawPlot({
          title: st.label + " Modal Gain & Normalized Singular Values",
          xLabel: "Mode Index",
          x: st.mode_idx || [],
          xmin: 0,
          xmax: st.n_modes || 1,
          ymin: 0,
          ymax: 1.05,
          series: sList,
          xDec: 0
        });
      }
      sel.addEventListener("change", updM);
      updM();
    } else if (activeTab === "coro" && payload.contrast_table) {
      ctrlBar.innerHTML = '<span class="muted">Log10 coronagraphic contrast vs separation</span>';
      var ct = payload.contrast_table;
      var x = ct.map(function(r) { return r.sep_ld; });
      function lg(v) { return Math.log10(Math.max(v || 1e-8, 1e-8)); }
      var sList = [
        {
          name: "CL Planet",
          y: ct.map(function(r) { return lg(r.cl_planet); }),
          color: "#2563eb",
          on: true
        },
        {
          name: "CL 5-sig",
          y: ct.map(function(r) { return lg(r.cl_5sig); }),
          color: "#dc2626",
          on: true
        },
        {
          name: "DL Raw",
          y: ct.map(function(r) { return lg(r.dl_raw); }),
          color: "#059669",
          on: true
        }
      ];
      drawPlot({
        title: "H-Band Coronagraphic Contrast Curve (log10)",
        xLabel: "Separation [lambda/D]",
        x: x,
        xmin: x[0] || 0,
        xmax: x[x.length - 1] || 20,
        ymin: -6.5,
        ymax: -2.0,
        series: sList,
        xDec: 0,
        isLog: true
      });
    }
  }

  tabBtns.forEach(function(btn) {
    btn.addEventListener("click", function() {
      activeTab = btn.getAttribute("data-opt-tab");
      tabBtns.forEach(function(b) { b.classList.toggle("active", b === btn); });
      renderActive();
    });
  });

  if (tip) {
    canvas.addEventListener("mousemove", function(ev) {
      if (!lastPlot || !lastPlot.x || !lastPlot.x.length) return;
      var rect = canvas.getBoundingClientRect();
      var mx = ev.clientX - rect.left;
      var pad = lastPlot.pad;
      if (mx < pad.l || mx > pad.l + lastPlot.pw) { tip.style.display = "none"; return; }
      var frac = (mx - pad.l) / lastPlot.pw;
      var targetX = lastPlot.xmin + frac * (lastPlot.xmax - lastPlot.xmin);
      var best = 0;
      var bestD = Infinity;
      for (var i = 0; i < lastPlot.x.length; i++) {
        var d = Math.abs(lastPlot.x[i] - targetX);
        if (d < bestD) { bestD = d; best = i; }
      }
      var lines = ["x = " + lastPlot.x[best].toFixed(lastPlot.xDec || 2)];
      lastPlot.series.forEach(function(s) {
        if (!s.on) return;
        var val = s.y[best];
        if (val !== undefined && isFinite(val)) {
          var vFmt = lastPlot.isLog ? Math.pow(10, val).toExponential(2) : val.toFixed(2);
          lines.push(s.name + ": " + vFmt);
        }
      });
      tip.innerHTML = lines.join("<br>");
      tip.style.display = "block";
      tip.style.left = Math.min(rect.width - 150, mx + 12) + "px";
      tip.style.top = "12px";
    });
    canvas.addEventListener("mouseleave", function() { tip.style.display = "none"; });
  }

  window.addEventListener("resize", renderActive);
  renderActive();
})();
"""

RUNTIME_PAGE_JS = """\
(function() {
  var dataEl = document.getElementById("runtime-explorer-data");
  if (!dataEl) return;
  var rt = {};
  try { rt = JSON.parse(dataEl.textContent || "{}"); } catch (e) { return; }

  var barBox = document.getElementById("rt-phase-bars");
  var metricSel = document.getElementById("rt-phase-metric");
  var catLbls = {
    simulation: "Simulation",
    calibration: "Calibration",
    loop_operation: "Loop Operation",
    analysis: "Analysis"
  };
  if (barBox && metricSel && Array.isArray(rt.phases)) {
    function drawBars() {
      var m = metricSel.value;
      var rows = rt.phases.filter(function(p) { return p.id !== "overall"; });
      var maxV = Math.max.apply(
        null, rows.map(function(p) { return Number(p[m] || 0); }).concat([1e-6])
      );
      barBox.innerHTML = rows.map(function(p) {
        var v = Number(p[m] || 0);
        var pct = Math.min(100, (v / maxV) * 100);
        var cat = p.category || "loop_operation";
        var clbl = p.category_label || catLbls[cat] || cat;
        return '<div class="hbar-row"><div class="hbar-label">' +
          '<span class="cat-badge cat-' + cat + '"><span class="cat-dot"></span>' +
          clbl + '</span><code>' + p.id + '</code></div>' +
          '<div class="hbar-track"><div class="hbar-fill cat-' + cat + '" style="width:' +
          pct.toFixed(1) + '%"></div></div>' +
          '<span style="text-align:right;">' + v.toFixed(1) + "</span></div>";
      }).join("");
    }
    metricSel.addEventListener("change", drawBars);
    drawBars();
  }

  if (window.cacaoInitCatFilter) {
    window.cacaoInitCatFilter({
      tableId: "rt-proc-table",
      prefix: "rt-proc",
      searchId: "rt-proc-search",
      noun: "processes"
    });
  }

  var shmZeroBtn = document.getElementById("rt-shm-zero");
  var onlyZero = false;
  var shmFilter = window.cacaoInitCatFilter ? window.cacaoInitCatFilter({
    tableId: "rt-shm-table",
    prefix: "rt-shm",
    searchId: "rt-shm-search",
    noun: "streams",
    extraPred: function(tr) {
      return !onlyZero || parseInt(tr.getAttribute("data-readers") || "0", 10) === 0;
    }
  }) : null;
  if (shmZeroBtn) {
    shmZeroBtn.addEventListener("click", function() {
      onlyZero = !onlyZero;
      shmZeroBtn.classList.toggle("active", onlyZero);
      shmZeroBtn.setAttribute("aria-pressed", onlyZero ? "true" : "false");
      if (shmFilter) shmFilter.apply();
    });
  }
})();
"""

HOW_TO_RUN_JS = """\
(function() {
  var defEl = document.getElementById("howtorun-defaults");
  if (defEl) {
    var defs = {};
    try { defs = JSON.parse(defEl.textContent || "{}"); } catch (e) {}
    var fields = ["seeing", "phys_time", "bench_mode", "oversample", "gain1", "gain2",
      "gain3", "llowfs", "pf_mode", "pf_order", "pf_blocksize", "pf_reg",
      "calib_2wfs1dm", "telemetry"];
    function loadDefs() {
      fields.forEach(function(k) {
        var el = document.getElementById("cust-" + k);
        if (el && defs[k] !== undefined) el.value = String(defs[k]);
      });
      updateCmds();
    }
    function val(k) {
      var el = document.getElementById("cust-" + k);
      return el ? el.value : "";
    }
    function updateCmds() {
      var slug = defs.slug || "ao3k_scexao";
      var cmd = "./scripts/run-ao3k-scexao.sh --seeing " + val("seeing") +
        " --phys-time " + val("phys_time") +
        " --oversample " + val("oversample") +
        " --bench-mode " + val("bench_mode") +
        " --gain1 " + val("gain1") + " --gain2 " + val("gain2");
      if (val("llowfs") === "open") cmd += " --no-lowfs";
      else cmd += " --gain3 " + val("gain3");
      var pf = val("pf_mode");
      if (pf === "ar") {
        cmd += " --predictive --pf-mode ar --pf-order " + val("pf_order") +
          " --pf-reg " + val("pf_reg");
      } else if (pf === "eof") {
        cmd += " --predictive --pf-mode eof --pf-blocksize " + val("pf_blocksize") +
          " --pf-order " + val("pf_order") + " --pf-reg " + val("pf_reg") +
          " --pf-warmup-sec 14.0";
      }
      if (val("calib_2wfs1dm") === "on") cmd += " --calib-2wfs1dm";
      if (val("telemetry") !== "none") cmd += " --save-telemetry " + val("telemetry");
      cmd += " --save-rm _work/ao3k_scexao_rm --outdir _work/" + slug;

      var c1 = document.getElementById("cmd-turnkey");
      if (c1) c1.textContent = "source env.sh\\n" + cmd;

      var c2 = document.getElementById("cmd-cacaosim");
      if (c2) {
        c2.textContent = "source env.sh\\n" +
          "cacaosim-bench deploy -c benches/ao3k_scexao/ao3k_scexao.bench \\\\\\n" +
          "  --mode " + val("bench_mode") + " --oversample " + val("oversample") +
          " --atmturb --seeing " + val("seeing");
      }
      var c3 = document.getElementById("cmd-cacaoloop");
      if (c3) {
        var pfLines = "";
        if (pf !== "off") {
          pfLines = "\\nCACAO_PF_MODE=" + pf + " CACAO_PF_ORDER=" + val("pf_order") +
            " ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 pf-on 0.90" +
            "\\nCACAO_PF_MODE=" + pf + " CACAO_PF_ORDER=" + val("pf_order") +
            " ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 pf-on 0.90";
        }
        var s3Line = val("llowfs") === "open"
          ? "# Stage 3 LLOWFS kept OPEN"
          : "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 3 close " + val("gain3");
        c3.textContent =
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 deploy && " +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 calibrate\\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 deploy && " +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 calibrate\\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 3 deploy && " +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 3 calibrate\\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 close " +
          val("gain1") + "\\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 close " +
          val("gain2") + "\\n" +
          s3Line + pfLines;
      }
      var note = document.getElementById("cust-advice");
      if (note) {
        var msgs = [];
        if (pf === "ar" && parseInt(val("pf_order"), 10) > 16) {
          msgs.push(
            "Tip: AR order > 16 benefits from N_train=4096 / N_min=1024 for stable warmup."
          );
        }
        if (pf === "eof") {
          msgs.push(
            "Tip: Block-EOF bootstraps with Diagonal AR(16) before switching at 12k/24k frames."
          );
        }
        if (val("bench_mode") === "modular") {
          msgs.push(
            "Modular mode splits csim_htsim into per-element FPS daemons for optical inspection."
          );
        }
        note.textContent = msgs.join(" ") || "Configuration matches balanced real-time execution.";
      }
    }
    fields.forEach(function(k) {
      var el = document.getElementById("cust-" + k);
      if (el) el.addEventListener("change", updateCmds);
    });
    var rst = document.getElementById("cust-reset");
    if (rst) rst.addEventListener("click", loadDefs);
    loadDefs();
  }

  if (window.cacaoInitCatFilter) {
    window.cacaoInitCatFilter({
      tableId: "compute-units-table",
      prefix: "cu",
      rowSelector: "tr.unit-row",
      searchId: "cu-search",
      noun: "units"
    });
  }
  var cuTbl = document.getElementById("compute-units-table");
  if (cuTbl) {
    cuTbl.querySelectorAll("tbody tr.unit-row").forEach(function(tr) {
      tr.style.cursor = "pointer";
      tr.addEventListener("click", function() {
        var det = tr.nextElementSibling;
        if (det && det.classList.contains("detail-row")) {
          det.classList.toggle("hidden");
        }
      });
    });
  }

  var cbs = Array.from(document.querySelectorAll("input.deploy-step-cb"));
  var progTxt = document.getElementById("deploy-progress-text");
  var progBar = document.getElementById("deploy-progress-fill");
  function updateProg() {
    if (!cbs.length) return;
    var done = 0;
    cbs.forEach(function(cb) {
      var item = cb.closest(".checklist-item");
      if (item) item.classList.toggle("done", cb.checked);
      if (cb.checked) done++;
    });
    if (progTxt) progTxt.textContent = done + " / " + cbs.length + " steps completed";
    if (progBar) progBar.style.width = ((done / cbs.length) * 100).toFixed(0) + "%";
  }
  cbs.forEach(function(cb) { cb.addEventListener("change", updateProg); });
  updateProg();
})();
"""
