/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */
/* Interactive Catalog/Matrix switcher, 5-column Pipeline Board wires & Detail Flow Strip. */

(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  function makeSvgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) {
        el.setAttribute(k, String(attrs[k]));
      }
    }
    return el;
  }

  function ensureMarkers(svg, prefix) {
    const defs = makeSvgEl("defs", {});
    const specs = [
      { id: prefix + "-base", color: "#94a3b8" },
      { id: prefix + "-req", color: "#d97706" },
      { id: prefix + "-opt", color: "#0f766e" },
      { id: prefix + "-down", color: "#0284c7" },
      { id: prefix + "-fb", color: "#0284c7" },
    ];
    specs.forEach((s) => {
      const m = makeSvgEl("marker", {
        id: s.id,
        viewBox: "0 0 10 10",
        refX: "8.5",
        refY: "5",
        markerWidth: "6",
        markerHeight: "6",
        orient: "auto-start-reverse",
      });
      m.appendChild(makeSvgEl("path", { d: "M 0 1.2 L 9 5 L 0 8.8 z", fill: s.color }));
      defs.appendChild(m);
    });
    svg.appendChild(defs);
  }

  function buildCurvePath(a, b, boardRect) {
    const ax1 = a.left - boardRect.left;
    const ax2 = a.right - boardRect.left;
    const ay = (a.top + a.bottom) * 0.5 - boardRect.top;
    const bx1 = b.left - boardRect.left;
    const bx2 = b.right - boardRect.left;
    const by = (b.top + b.bottom) * 0.5 - boardRect.top;

    // Same column: vertical gap connector for adjacent downward, right-gutter arc otherwise
    if (Math.abs(ax1 - bx1) < 25) {
      const aBot = a.bottom - boardRect.top;
      const bTop = b.top - boardRect.top;
      if (bTop > aBot && bTop - aBot < 36) {
        const mx = (ax1 + ax2) * 0.5;
        return `M ${mx.toFixed(1)} ${aBot.toFixed(1)} L ${mx.toFixed(1)} ${(bTop - 2).toFixed(1)}`;
      }
      const bulge = Math.min(34, Math.max(18, Math.abs(by - ay) * 0.16));
      const xStart = ax2;
      const xEnd = bx2;
      const cx = Math.max(xStart, xEnd) + bulge;
      return (
        `M ${xStart.toFixed(1)} ${ay.toFixed(1)} ` +
        `C ${cx.toFixed(1)} ${ay.toFixed(1)}, ${cx.toFixed(1)} ${by.toFixed(1)}, ` +
        `${(xEnd + 2).toFixed(1)} ${by.toFixed(1)}`
      );
    }

    // Forward cross-column (left -> right)
    if (bx1 >= ax2 - 8) {
      const dx = Math.max(24, (bx1 - ax2) * 0.46);
      return (
        `M ${ax2.toFixed(1)} ${ay.toFixed(1)} ` +
        `C ${(ax2 + dx).toFixed(1)} ${ay.toFixed(1)}, ` +
        `${(bx1 - dx).toFixed(1)} ${by.toFixed(1)}, ` +
        `${(bx1 - 2).toFixed(1)} ${by.toFixed(1)}`
      );
    }

    // Backward cross-column (right -> left feedback)
    const dx = Math.max(24, (ax1 - bx2) * 0.46);
    return (
      `M ${ax1.toFixed(1)} ${ay.toFixed(1)} ` +
      `C ${(ax1 - dx).toFixed(1)} ${ay.toFixed(1)}, ` +
      `${(bx2 + dx).toFixed(1)} ${by.toFixed(1)}, ` +
      `${(bx2 + 2).toFixed(1)} ${by.toFixed(1)}`
    );
  }

  /* ----------------------------------------------------------------------
   * 1. Detail page 3-Column Flow Strip (#algo-detail-flow)
   * -------------------------------------------------------------------- */
  const detailFlow = document.getElementById("algo-detail-flow");
  const detailSvg = document.getElementById("algo-detail-flow-svg");
  if (detailFlow && detailSvg) {
    const drawDetailFlow = () => {
      while (detailSvg.firstChild) detailSvg.removeChild(detailSvg.firstChild);
      if (window.innerWidth <= 960) return;
      ensureMarkers(detailSvg, "df");
      const bRect = detailFlow.getBoundingClientRect();
      const centerEl = detailFlow.querySelector('[data-flow-side="center"]');
      if (!centerEl) return;
      const cRect = centerEl.getBoundingClientRect();

      detailFlow.querySelectorAll('[data-flow-side="up"]').forEach((el) => {
        const kind = el.getAttribute("data-flow-kind") || "req";
        const cls = kind === "opt" ? "pipe-wire-opt" : kind === "fb" ? "pipe-wire-fb" : "pipe-wire-req";
        const mk = kind === "opt" ? "df-opt" : kind === "fb" ? "df-fb" : "df-req";
        const p = makeSvgEl("path", {
          d: buildCurvePath(el.getBoundingClientRect(), cRect, bRect),
          class: cls,
          "marker-end": `url(#${mk})`,
        });
        detailSvg.appendChild(p);
      });
      detailFlow.querySelectorAll('[data-flow-side="down"]').forEach((el) => {
        const kind = el.getAttribute("data-flow-kind") || "req";
        const cls = kind === "opt" ? "pipe-wire-opt" : kind === "fb" ? "pipe-wire-fb" : "pipe-wire-down";
        const mk = kind === "opt" ? "df-opt" : kind === "fb" ? "df-fb" : "df-down";
        const p = makeSvgEl("path", {
          d: buildCurvePath(cRect, el.getBoundingClientRect(), bRect),
          class: cls,
          "marker-end": `url(#${mk})`,
        });
        detailSvg.appendChild(p);
      });
    };
    window.addEventListener("resize", drawDetailFlow);
    window.addEventListener("load", drawDetailFlow);
    requestAnimationFrame(drawDetailFlow);
  }

  /* ----------------------------------------------------------------------
   * 2. Algorithms Index Page (#algorithms-root + #algo-pipeline-board)
   * -------------------------------------------------------------------- */
  const root = document.getElementById("algorithms-root");
  if (!root) return;

  let depGraph = {};
  const graphEl = document.getElementById("algo-dep-graph-data");
  if (graphEl) {
    try {
      depGraph = JSON.parse(graphEl.textContent || "{}");
    } catch (_err) {
      depGraph = {};
    }
  }

  let pipePresets = {};
  const presetsEl = document.getElementById("algo-pipe-presets");
  if (presetsEl) {
    try {
      pipePresets = JSON.parse(presetsEl.textContent || "{}");
    } catch (_err) {
      pipePresets = {};
    }
  }

  let activeRole = "all";
  let activeStage = "all";
  let activeTrace = null;

  const viewBtns = Array.from(root.querySelectorAll("[data-algo-view]"));
  const panels = Array.from(root.querySelectorAll("[data-algo-panel]"));
  const roleBtns = Array.from(root.querySelectorAll("[data-algo-role-filter]"));
  const stageBtns = Array.from(root.querySelectorAll("[data-algo-stage-filter]"));
  const searchInput = document.getElementById("algo-search");
  const resetBtn = document.getElementById("algo-reset");
  const countEl = document.getElementById("algo-count");
  const emptyEl = document.getElementById("algo-empty");
  const traceBanner = document.getElementById("algo-trace-banner");
  const traceText = document.getElementById("algo-trace-text");
  const traceClear = document.getElementById("algo-trace-clear");
  const catalogRows = Array.from(root.querySelectorAll("tr.algo-row"));
  const groupRows = Array.from(root.querySelectorAll("tr.algo-group-row"));
  const matrixRows = Array.from(root.querySelectorAll("tr.dep-matrix-row"));

  function setView(viewName) {
    viewBtns.forEach((btn) => {
      const isAct = btn.getAttribute("data-algo-view") === viewName;
      btn.classList.toggle("active", isAct);
      btn.setAttribute("aria-selected", isAct ? "true" : "false");
    });
    panels.forEach((p) => {
      p.classList.toggle("active", p.getAttribute("data-algo-panel") === viewName);
    });
  }

  function collectTransitive(startCode, dir) {
    const visited = new Set();
    const stack = [startCode];
    while (stack.length) {
      const cur = stack.pop();
      const node = depGraph[cur];
      if (!node) continue;
      const neighbors =
        dir === "up"
          ? [].concat(node.req || [], node.opt || [])
          : [].concat(node.en || [], node.en_opt || [], node.fb_out || []);
      for (let i = 0; i < neighbors.length; i += 1) {
        const nxt = neighbors[i];
        if (!visited.has(nxt) && nxt !== startCode) {
          visited.add(nxt);
          stack.push(nxt);
        }
      }
    }
    return visited;
  }

  function applyTrace(code) {
    activeTrace = code && activeTrace !== code ? code : null;
    root.querySelectorAll("[data-algo-trace]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-algo-trace") === activeTrace);
    });
    catalogRows.forEach((tr) => {
      tr.classList.remove("algo-dimmed", "algo-selected", "algo-req", "algo-enables");
    });

    if (!activeTrace || !depGraph[activeTrace]) {
      if (traceBanner) traceBanner.classList.add("hidden");
      return;
    }

    const up = collectTransitive(activeTrace, "up");
    const down = collectTransitive(activeTrace, "down");
    catalogRows.forEach((tr) => {
      const rc = tr.getAttribute("data-code") || "";
      if (rc === activeTrace) tr.classList.add("algo-selected");
      else if (up.has(rc)) tr.classList.add("algo-req");
      else if (down.has(rc)) tr.classList.add("algo-enables");
      else tr.classList.add("algo-dimmed");
    });
    if (traceBanner && traceText) {
      const meta = depGraph[activeTrace];
      traceText.textContent =
        "Dependency chain for " +
        activeTrace +
        " (" +
        (meta.name || "") +
        "): " +
        up.size +
        " upstream prereq(s) -> " +
        activeTrace +
        " -> " +
        down.size +
        " downstream algorithm(s).";
      traceBanner.classList.remove("hidden");
    }
    setView("catalog");
  }

  function applyFilters() {
    const q = searchInput ? searchInput.value.trim().toLowerCase() : "";
    const visibleRoles = new Set();
    let shown = 0;
    catalogRows.forEach((tr) => {
      const role = tr.getAttribute("data-role") || "";
      const stages = (tr.getAttribute("data-stages") || "").split(" ");
      const blob = tr.getAttribute("data-search") || "";
      const ok =
        (activeRole === "all" || role === activeRole) &&
        (activeStage === "all" || stages.indexOf(activeStage) !== -1) &&
        (!q || blob.indexOf(q) !== -1);
      tr.classList.toggle("hidden", !ok);
      if (ok) {
        shown += 1;
        visibleRoles.add(role);
      }
    });
    groupRows.forEach((gtr) => {
      const gr = gtr.getAttribute("data-group-role") || "";
      gtr.classList.toggle("hidden", !visibleRoles.has(gr));
    });
    matrixRows.forEach((mtr) => {
      const role = mtr.getAttribute("data-role") || "";
      const stages = (mtr.getAttribute("data-stages") || "").split(" ");
      const blob = mtr.getAttribute("data-search") || "";
      const ok =
        (activeRole === "all" || role === activeRole) &&
        (activeStage === "all" || stages.indexOf(activeStage) !== -1) &&
        (!q || blob.indexOf(q) !== -1);
      mtr.classList.toggle("hidden", !ok);
    });
    if (countEl) countEl.textContent = shown + " / " + catalogRows.length;
    if (emptyEl) emptyEl.classList.toggle("hidden", shown > 0);
  }

  viewBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      setView(btn.getAttribute("data-algo-view") || "catalog");
    });
  });

  roleBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      roleBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeRole = btn.getAttribute("data-algo-role-filter") || "all";
      applyFilters();
    });
  });

  stageBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      stageBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeStage = btn.getAttribute("data-algo-stage-filter") || "all";
      applyFilters();
    });
  });

  root.addEventListener("click", (ev) => {
    const tbtn = ev.target.closest("[data-algo-trace]");
    if (!tbtn) return;
    ev.preventDefault();
    applyTrace(tbtn.getAttribute("data-algo-trace") || "");
  });

  if (traceClear) {
    traceClear.addEventListener("click", () => applyTrace(null));
  }
  if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
  }
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      activeRole = "all";
      activeStage = "all";
      if (searchInput) searchInput.value = "";
      roleBtns.forEach((b) =>
        b.classList.toggle("active", b.getAttribute("data-algo-role-filter") === "all")
      );
      stageBtns.forEach((b) =>
        b.classList.toggle("active", b.getAttribute("data-algo-stage-filter") === "all")
      );
      applyTrace(null);
      applyFilters();
    });
  }

  if (window.location.hash === "#matrix") {
    setView("matrix");
  }

  /* ----------------------------------------------------------------------
   * 3. 5-Column Pipeline Architecture Board (#algo-pipeline-board)
   * -------------------------------------------------------------------- */
  const pipeBoard = document.getElementById("algo-pipeline-board");
  const pipeSvgBase = document.getElementById("algo-pipe-svg-base");
  const pipeSvg = document.getElementById("algo-pipe-svg");
  const pipeStatus = document.getElementById("algo-pipe-status");
  if (!pipeBoard || !pipeSvg || !pipeSvgBase) return;

  const pipeCards = Array.from(pipeBoard.querySelectorAll(".algo-pipe-card[data-pipe-code]"));
  const cardByCode = {};
  pipeCards.forEach((el) => {
    cardByCode[el.getAttribute("data-pipe-code") || ""] = el;
  });

  let pinnedCode = null;
  let activePreset = null;
  let hoveredCode = null;
  let wireDepth = "direct";
  const defaultStatusHtml = pipeStatus ? pipeStatus.innerHTML : "";

  function drawBaseBackbone() {
    while (pipeSvgBase.firstChild) pipeSvgBase.removeChild(pipeSvgBase.firstChild);
    ensureMarkers(pipeSvgBase, "pb");
    const bRect = pipeBoard.getBoundingClientRect();
    const backbone = [
      ["SIM/PLATE", "MLAT"],
      ["MLAT", "RM"],
      ["RM", "3DRM/P1"],
      ["3DRM/P1", "PRESH/CAL"],
      ["PRESH/CAL", "PRESH"],
      ["PRESH", "3DRM/P2"],
      ["3DRM/P2", "3DRM/FACT"],
      ["3DRM/FACT", "LAG/2PT"],
      ["LAG/2PT", "PSOL"],
      ["INT", "PSOL"],
      ["PSOL", "EOF"],
      ["WIND", "EOF"],
      ["2WFS/LIVE", "ZPO"],
      ["2WFS/LIVE", "OFFL"],
      ["EOF", "WHITE"],
    ];
    backbone.forEach(([s, d]) => {
      const se = cardByCode[s];
      const de = cardByCode[d];
      if (!se || !de) return;
      pipeSvgBase.appendChild(
        makeSvgEl("path", {
          d: buildCurvePath(se.getBoundingClientRect(), de.getBoundingClientRect(), bRect),
          class: "pipe-wire-base",
          "marker-end": "url(#pb-base)",
        })
      );
    });
  }

  function renderPipelineFocus() {
    while (pipeSvg.firstChild) pipeSvg.removeChild(pipeSvg.firstChild);
    ensureMarkers(pipeSvg, "pa");

    pipeCards.forEach((el) => {
      el.classList.remove("pipe-dim", "pipe-focus", "pipe-up", "pipe-opt", "pipe-down");
    });
    document.querySelectorAll("[data-pipe-pin]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-pipe-pin") === pinnedCode);
    });
    document.querySelectorAll("[data-pipe-preset]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-pipe-preset") === activePreset);
    });

    const bRect = pipeBoard.getBoundingClientRect();

    // Preset stack mode (when no card is hovered or pinned)
    if (!hoveredCode && !pinnedCode && activePreset && pipePresets[activePreset]) {
      const pinfo = pipePresets[activePreset];
      const pset = new Set(pinfo.codes || []);
      pipeCards.forEach((el) => {
        const c = el.getAttribute("data-pipe-code") || "";
        if (pset.has(c)) el.classList.add("pipe-focus");
        else el.classList.add("pipe-dim");
      });
      // Draw all internal edges among preset members
      (pinfo.codes || []).forEach((dst) => {
        const node = depGraph[dst];
        if (!node || !cardByCode[dst]) return;
        const dRect = cardByCode[dst].getBoundingClientRect();
        (node.req || []).forEach((src) => {
          if (pset.has(src) && cardByCode[src]) {
            pipeSvg.appendChild(
              makeSvgEl("path", {
                d: buildCurvePath(cardByCode[src].getBoundingClientRect(), dRect, bRect),
                class: "pipe-wire-req",
                "marker-end": "url(#pa-req)",
              })
            );
          }
        });
        (node.opt || []).forEach((src) => {
          if (pset.has(src) && cardByCode[src]) {
            pipeSvg.appendChild(
              makeSvgEl("path", {
                d: buildCurvePath(cardByCode[src].getBoundingClientRect(), dRect, bRect),
                class: "pipe-wire-opt",
                "marker-end": "url(#pa-opt)",
              })
            );
          }
        });
      });
      if (pipeStatus) {
        pipeStatus.innerHTML =
          `<span><strong>Stack Preset: ${pinfo.label}</strong> &mdash; ` +
          `${(pinfo.codes || []).join(" &middot; ")}</span>`;
      }
      return;
    }

    const focus = hoveredCode || pinnedCode;
    if (!focus || !depGraph[focus]) {
      if (pipeStatus) pipeStatus.innerHTML = defaultStatusHtml;
      return;
    }

    const node = depGraph[focus];
    let upReq = new Set(node.req || []);
    let upOpt = new Set(node.opt || []);
    let downSet = new Set([].concat(node.en || [], node.en_opt || [], node.fb_out || []));
    const edges = [];

    if (wireDepth === "full") {
      const allUp = collectTransitive(focus, "up");
      const allDown = collectTransitive(focus, "down");
      upReq = new Set();
      upOpt = new Set();
      allUp.forEach((c) => {
        if ((node.opt || []).indexOf(c) !== -1 && (node.req || []).indexOf(c) === -1) {
          upOpt.add(c);
        } else {
          upReq.add(c);
        }
      });
      downSet = allDown;
      const activeNodes = new Set([focus, ...allUp, ...allDown]);
      activeNodes.forEach((dst) => {
        const dn = depGraph[dst];
        if (!dn) return;
        (dn.req || []).forEach((src) => {
          if (activeNodes.has(src)) {
            const isDownEdge = dst !== focus && (allDown.has(dst) || src === focus);
            edges.push([src, dst, isDownEdge ? "down" : "req"]);
          }
        });
        (dn.opt || []).forEach((src) => {
          if (activeNodes.has(src) && (src === focus || dst === focus)) {
            edges.push([src, dst, "opt"]);
          }
        });
      });
    } else {
      (node.req || []).forEach((src) => edges.push([src, focus, "req"]));
      (node.opt || []).forEach((src) => edges.push([src, focus, "opt"]));
      (node.en || []).forEach((dst) => edges.push([focus, dst, "down"]));
      (node.en_opt || []).forEach((dst) => edges.push([focus, dst, "opt"]));
      (node.fb_out || []).forEach((dst) => edges.push([focus, dst, "fb"]));
    }

    pipeCards.forEach((el) => {
      const c = el.getAttribute("data-pipe-code") || "";
      if (c === focus) el.classList.add("pipe-focus");
      else if (upReq.has(c)) el.classList.add("pipe-up");
      else if (upOpt.has(c)) el.classList.add("pipe-opt");
      else if (downSet.has(c)) el.classList.add("pipe-down");
      else el.classList.add("pipe-dim");
    });

    edges.forEach(([src, dst, kind]) => {
      const se = cardByCode[src];
      const de = cardByCode[dst];
      if (!se || !de) return;
      const cls =
        kind === "opt"
          ? "pipe-wire-opt"
          : kind === "down"
            ? "pipe-wire-down"
            : kind === "fb"
              ? "pipe-wire-fb"
              : "pipe-wire-req";
      const mk =
        kind === "opt"
          ? "pa-opt"
          : kind === "down"
            ? "pa-down"
            : kind === "fb"
              ? "pa-fb"
              : "pa-req";
      pipeSvg.appendChild(
        makeSvgEl("path", {
          d: buildCurvePath(se.getBoundingClientRect(), de.getBoundingClientRect(), bRect),
          class: cls,
          "marker-end": `url(#${mk})`,
        })
      );
    });

    if (pipeStatus) {
      const reqStr = (node.req || []).join(", ") || "none";
      const optStr = (node.opt || []).join(", ") || "none";
      const enStr = [].concat(node.en || [], node.en_opt || [], node.fb_out || []).join(", ") || "none";
      pipeStatus.innerHTML =
        `<span><strong>${focus} &mdash; ${node.name}</strong> &middot; ` +
        `Requires: <strong>${reqStr}</strong> &middot; ` +
        `Optional: <strong>${optStr}</strong> &middot; ` +
        `Enables: <strong>${enStr}</strong></span>`;
    }
  }

  pipeCards.forEach((el) => {
    const code = el.getAttribute("data-pipe-code") || "";
    el.addEventListener("mouseenter", () => {
      hoveredCode = code;
      renderPipelineFocus();
    });
    el.addEventListener("mouseleave", () => {
      hoveredCode = null;
      renderPipelineFocus();
    });
  });

  pipeBoard.addEventListener("click", (ev) => {
    const pbtn = ev.target.closest("[data-pipe-pin]");
    if (!pbtn) return;
    ev.preventDefault();
    ev.stopPropagation();
    const code = pbtn.getAttribute("data-pipe-pin") || "";
    pinnedCode = pinnedCode === code ? null : code;
    activePreset = null;
    renderPipelineFocus();
  });

  document.querySelectorAll("[data-pipe-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-pipe-preset") || "";
      activePreset = activePreset === pid ? null : pid;
      pinnedCode = null;
      hoveredCode = null;
      renderPipelineFocus();
    });
  });

  document.querySelectorAll("[data-pipe-depth]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-pipe-depth]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      wireDepth = btn.getAttribute("data-pipe-depth") || "direct";
      renderPipelineFocus();
    });
  });

  const pipeClearBtn = document.getElementById("algo-pipe-clear");
  if (pipeClearBtn) {
    pipeClearBtn.addEventListener("click", () => {
      pinnedCode = null;
      activePreset = null;
      hoveredCode = null;
      renderPipelineFocus();
    });
  }

  const redrawAll = () => {
    drawBaseBackbone();
    renderPipelineFocus();
  };
  window.addEventListener("resize", redrawAll);
  window.addEventListener("load", redrawAll);
  requestAnimationFrame(redrawAll);
})();
