/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */
/* Interactive view switcher, role/stage filtering, and dependency tracing for /algorithms/. */

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

  let activeView = "catalog";
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
    activeView = viewName;
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
      const neighbors = dir === "up"
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
})();
