/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */
/* Interactive Catalog/Matrix switcher & bold outline-code Pipeline Map highlighting. */

(function () {
  "use strict";

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
   * 5-Column Pipeline Map — Pure Bold Outline-Code Highlighting (No Arrows)
   * -------------------------------------------------------------------- */
  const pipeBoard = document.getElementById("algo-pipeline-board");
  const pipeStatus = document.getElementById("algo-pipe-status");
  if (!pipeBoard) return;

  const pipeCards = Array.from(pipeBoard.querySelectorAll(".algo-pipe-card[data-pipe-code]"));
  let pinnedCode = null;
  let activePreset = null;
  let hoveredCode = null;
  let scopeDepth = "direct";
  const defaultStatusHtml = pipeStatus ? pipeStatus.innerHTML : "";

  function renderPipelineFocus() {
    pipeCards.forEach((el) => {
      el.classList.remove("pipe-dim", "pipe-focus", "pipe-up", "pipe-opt", "pipe-down", "pipe-fb");
    });
    document.querySelectorAll("[data-pipe-pin]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-pipe-pin") === pinnedCode);
    });
    document.querySelectorAll("[data-pipe-preset]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-pipe-preset") === activePreset);
    });

    if (!hoveredCode && !pinnedCode && activePreset && pipePresets[activePreset]) {
      const pinfo = pipePresets[activePreset];
      const pset = new Set(pinfo.codes || []);
      // Also outline mandatory calibrations needed by this stack preset
      const extraReq = new Set();
      (pinfo.codes || []).forEach((c) => {
        const up = collectTransitive(c, "up");
        up.forEach((u) => {
          if (!pset.has(u)) extraReq.add(u);
        });
      });
      pipeCards.forEach((el) => {
        const c = el.getAttribute("data-pipe-code") || "";
        if (pset.has(c)) el.classList.add("pipe-focus");
        else if (extraReq.has(c)) el.classList.add("pipe-up");
        else el.classList.add("pipe-dim");
      });
      if (pipeStatus) {
        const reqList = Array.from(extraReq);
        pipeStatus.innerHTML =
          `<span><strong>Stack Preset: ${pinfo.label}</strong> &middot; ` +
          `Active: <strong>${(pinfo.codes || []).join(", ")}</strong>` +
          (reqList.length ? ` &middot; Prereqs: <strong>${reqList.join(", ")}</strong>` : "") +
          "</span>";
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
    let fbSet = new Set([].concat(node.fb_in || [], node.fb_out || []));
    let downSet = new Set(node.en || []);
    let downOpt = new Set(node.en_opt || []);

    if (scopeDepth === "full") {
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
      downSet = new Set();
      downOpt = new Set();
      allDown.forEach((c) => {
        if (!fbSet.has(c)) downSet.add(c);
      });
    }

    pipeCards.forEach((el) => {
      const c = el.getAttribute("data-pipe-code") || "";
      if (c === focus) el.classList.add("pipe-focus");
      else if (upReq.has(c)) el.classList.add("pipe-up");
      else if (downSet.has(c)) el.classList.add("pipe-down");
      else if (fbSet.has(c)) el.classList.add("pipe-fb");
      else if (upOpt.has(c) || downOpt.has(c)) el.classList.add("pipe-opt");
      else el.classList.add("pipe-dim");
    });

    if (pipeStatus) {
      const reqStr = Array.from(upReq).join(", ") || "none";
      const optStr = Array.from(new Set([...upOpt, ...downOpt])).join(", ") || "none";
      const enStr = Array.from(new Set([...downSet, ...fbSet])).join(", ") || "none";
      pipeStatus.innerHTML =
        `<span><strong>${focus} &mdash; ${node.name}</strong> &middot; ` +
        `Required: <strong>${reqStr}</strong> &middot; ` +
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
      scopeDepth = btn.getAttribute("data-pipe-depth") || "direct";
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
})();
