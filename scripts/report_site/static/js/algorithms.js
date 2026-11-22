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
   * Dynamic AO Algorithmic-Options Configurator (Zero-Reflow Hover + Click)
   * -------------------------------------------------------------------- */
  const pipeWorkspace = document.getElementById("algo-pipe-workspace");
  const pipeStatus = document.getElementById("algo-pipe-status");
  const pipeProfile = document.getElementById("algo-pipe-profile");
  if (!pipeWorkspace) return;

  let pipeGraph = {};
  const pipeGraphEl = document.getElementById("algo-pipe-graph-data");
  if (pipeGraphEl) {
    try {
      pipeGraph = JSON.parse(pipeGraphEl.textContent || "{}");
    } catch (_err) {
      pipeGraph = {};
    }
  }

  const pipeCards = Array.from(
    pipeWorkspace.querySelectorAll(".algo-pipe-card[data-pipe-code]")
  );
  const stageToggleBtns = Array.from(
    pipeWorkspace.querySelectorAll("[data-pipe-stage]")
  );
  const STAGE_LABELS = {
    stg1: "Stage 1",
    stg2: "Stage 2",
    stg3: "Stage 3",
  };
  const DEFAULT_STAGES = ["stg1", "stg2", "stg3"];
  const DEFAULT_SELECTED = [
    "SIM/FUSED",
    "SIM/PLATE",
    "SIM/TURB",
    "WFS/MOD",
    "MLAT",
    "RM/FAST",
    "INT/MGAIN",
    "PSOL/2TAP",
  ];

  const activeStages = new Set(DEFAULT_STAGES);
  const selectedCodes = new Set(DEFAULT_SELECTED.filter((c) => Boolean(pipeGraph[c])));
  let activePreset = null;
  let hoveredCode = null;
  let scopeDepth = "direct";
  let lastNotice = "";

  function flatReqs(node) {
    const out = [];
    (node.req_clauses || []).forEach((cl) => {
      cl.forEach((r) => {
        if (out.indexOf(r) === -1) out.push(r);
      });
    });
    return out;
  }

  function collectPipeTransitive(startCode, dir) {
    const visited = new Set();
    const stack = [startCode];
    while (stack.length) {
      const cur = stack.pop();
      const node = pipeGraph[cur];
      if (!node) continue;
      const neighbors =
        dir === "up"
          ? [].concat(flatReqs(node), node.opt || [])
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

  function missingPrereqs(code) {
    const node = pipeGraph[code];
    if (!node) return { stages: [], reqs: [] };
    const missStages = [];
    const sr = node.stage_req || { mode: "none", stages: [] };
    const reqSt = sr.stages || [];
    if (sr.mode === "all") {
      reqSt.forEach((s) => {
        if (!activeStages.has(s)) missStages.push(STAGE_LABELS[s] || s);
      });
    } else if (sr.mode === "any" && reqSt.length) {
      if (!reqSt.some((s) => activeStages.has(s))) {
        missStages.push(reqSt.map((s) => STAGE_LABELS[s] || s).join(" or "));
      }
    }
    const missReqs = [];
    (node.req_clauses || []).forEach((clause) => {
      if (clause.length && !clause.some((r) => selectedCodes.has(r))) {
        missReqs.push(clause.join(" or "));
      }
    });
    return { stages: missStages, reqs: missReqs };
  }

  function isSelectable(code) {
    const m = missingPrereqs(code);
    return m.stages.length === 0 && m.reqs.length === 0;
  }

  function pruneInvalidSelections() {
    let changed = true;
    while (changed) {
      changed = false;
      Array.from(selectedCodes).forEach((c) => {
        if (!isSelectable(c)) {
          selectedCodes.delete(c);
          changed = true;
        }
      });
    }
  }

  function formatMissingText(m) {
    const parts = [];
    if (m.stages.length) parts.push("stage " + m.stages.join(" + "));
    if (m.reqs.length) parts.push(m.reqs.join(" & "));
    return parts.join("; ");
  }

  function renderPipeline() {
    pruneInvalidSelections();

    stageToggleBtns.forEach((btn) => {
      const sk = btn.getAttribute("data-pipe-stage") || "";
      const on = activeStages.has(sk);
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });

    document.querySelectorAll("[data-pipe-preset]").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-pipe-preset") === activePreset);
    });

    let nSel = 0;
    let nAvail = 0;
    let nLocked = 0;

    pipeCards.forEach((el) => {
      const c = el.getAttribute("data-pipe-code") || "";
      const node = pipeGraph[c] || {};
      const isSim = node.role === "simulation";
      const sel = selectedCodes.has(c);
      const avail = !sel && isSelectable(c);

      el.classList.remove(
        "pipe-selected",
        "pipe-available",
        "pipe-locked",
        "pipe-dim",
        "pipe-focus",
        "pipe-up",
        "pipe-opt",
        "pipe-down",
        "pipe-fb",
        "pipe-excl"
      );

      if (sel) {
        el.classList.add("pipe-selected");
        el.setAttribute("aria-pressed", "true");
        el.setAttribute("aria-disabled", "false");
        el.setAttribute(
          "title",
          node.radio_group
            ? c + " is active"
            : c + " is selected — click to turn off"
        );
        if (!isSim) nSel += 1;
      } else if (avail) {
        el.classList.add("pipe-available");
        el.setAttribute("aria-pressed", "false");
        el.setAttribute("aria-disabled", "false");
        const exList = (node.excl || []).filter((x) => x !== c && selectedCodes.has(x));
        const exTip = exList.length ? " (switches off " + exList.join(", ") + ")" : "";
        el.setAttribute("title", "Click to select " + c + exTip);
        if (!isSim) nAvail += 1;
      } else {
        el.classList.add("pipe-locked");
        el.setAttribute("aria-pressed", "false");
        el.setAttribute("aria-disabled", "true");
        const miss = formatMissingText(missingPrereqs(c));
        el.setAttribute("title", "Locked — requires: " + (miss || "prerequisites"));
        if (!isSim) nLocked += 1;
      }
    });

    if (pipeProfile) {
      const stagePills = DEFAULT_STAGES.filter((s) => activeStages.has(s)).map(
        (s) => `<span class="algo-prof-tag algo-prof-stage">${STAGE_LABELS[s] || s}</span>`
      );
      const choicePills = pipeCards
        .map((el) => el.getAttribute("data-pipe-code") || "")
        .filter((c) => selectedCodes.has(c))
        .map((c) => {
          const r = (pipeGraph[c] || {}).role || "loop_operation";
          return `<span class="algo-prof-tag cat-${r}">${c}</span>`;
        });
      pipeProfile.innerHTML =
        '<span class="algo-prof-lbl">Active Simulation Profile:</span>' +
        (stagePills.length || choicePills.length
          ? stagePills.concat(choicePills).join("")
          : '<span class="muted">None selected</span>');
    }

    const focus = hoveredCode;
    if (focus && pipeGraph[focus]) {
      const node = pipeGraph[focus];
      let upReq = new Set(flatReqs(node));
      let upOpt = new Set(node.opt || []);
      const fbSet = new Set([].concat(node.fb_in || [], node.fb_out || []));
      let downSet = new Set(node.en || []);
      let downOpt = new Set(node.en_opt || []);
      const exclSet = new Set((node.excl || []).filter((x) => x !== focus));

      if (scopeDepth === "full") {
        const allUp = collectPipeTransitive(focus, "up");
        const allDown = collectPipeTransitive(focus, "down");
        const directReqs = flatReqs(node);
        upReq = new Set();
        upOpt = new Set();
        allUp.forEach((c) => {
          if ((node.opt || []).indexOf(c) !== -1 && directReqs.indexOf(c) === -1) {
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
        else if (exclSet.has(c)) el.classList.add("pipe-excl");
        else if (upReq.has(c)) el.classList.add("pipe-up");
        else if (downSet.has(c)) el.classList.add("pipe-down");
        else if (fbSet.has(c)) el.classList.add("pipe-fb");
        else if (upOpt.has(c) || downOpt.has(c)) el.classList.add("pipe-opt");
        else el.classList.add("pipe-dim");
      });

      if (pipeStatus) {
        const miss = missingPrereqs(focus);
        const stateStr =
          !selectedCodes.has(focus) && (miss.stages.length || miss.reqs.length)
            ? " &middot; <strong>Locked (needs: " + formatMissingText(miss) + ")</strong>"
            : selectedCodes.has(focus)
            ? node.radio_group
              ? " &middot; <strong>Active</strong>"
              : " &middot; <strong>Selected</strong> (click to turn off)"
            : " &middot; <strong>Selectable</strong> (click to enable)";
        const exclStr = exclSet.size
          ? " &middot; Exclusive: <strong>" + Array.from(exclSet).join(", ") + "</strong>"
          : "";
        const reqStr =
          (node.req_clauses || []).map((cl) => cl.join(" | ")).join(" + ") || "none";
        const enStr = Array.from(new Set([...downSet, ...fbSet])).join(", ") || "none";
        pipeStatus.innerHTML =
          `<span><strong>${focus} &mdash; ${node.name}</strong>${stateStr}${exclStr}` +
          ` &middot; Req: <strong>${reqStr}</strong>` +
          ` &middot; Enables: <strong>${enStr}</strong></span>`;
      }
      return;
    }

    if (pipeStatus) {
      const stList = DEFAULT_STAGES.filter((s) => activeStages.has(s)).map(
        (s) => STAGE_LABELS[s] || s
      );
      const stStr = stList.length ? stList.join(", ") : "None";
      const noteHtml = lastNotice ? ` &middot; <strong>${lastNotice}</strong>` : "";
      pipeStatus.innerHTML =
        `<span>Stages: <strong>${stStr}</strong> &middot; ` +
        `Choices: <strong>${nSel} selected</strong>, ` +
        `<strong>${nAvail} selectable</strong>, ` +
        `<strong>${nLocked} locked</strong>${noteHtml}</span>`;
    }
  }

  function toggleCode(code) {
    const node = pipeGraph[code];
    if (!node) return;
    activePreset = null;
    if (selectedCodes.has(code)) {
      if (node.radio_group) {
        lastNotice = `${code} is active — click its paired option to switch.`;
        renderPipeline();
        return;
      }
      const before = selectedCodes.size;
      selectedCodes.delete(code);
      pruneInvalidSelections();
      const dropped = before - selectedCodes.size - 1;
      lastNotice =
        dropped > 0
          ? `Turned off ${code} (and ${dropped} dependent choice${dropped === 1 ? "" : "s"}).`
          : `Turned off ${code}.`;
    } else if (!isSelectable(code)) {
      const miss = formatMissingText(missingPrereqs(code));
      lastNotice = `${code} is locked — enable ${miss} first.`;
    } else {
      const conflicts = (node.excl || []).filter(
        (x) => x !== code && selectedCodes.has(x)
      );
      const before = selectedCodes.size;
      conflicts.forEach((x) => selectedCodes.delete(x));
      selectedCodes.add(code);
      pruneInvalidSelections();
      const cascaded = Math.max(0, before - conflicts.length + 1 - selectedCodes.size);
      if (conflicts.length) {
        lastNotice =
          `Selected ${code} — switched off ${conflicts.join(", ")}` +
          (cascaded > 0 ? ` (+${cascaded} dependent).` : ".");
      } else {
        lastNotice = `Selected ${code}.`;
      }
    }
    renderPipeline();
  }

  function applyPreset(pid) {
    const pinfo = pipePresets[pid];
    if (!pinfo) return;
    const pCodes = (pinfo.codes || []).filter((c) => Boolean(pipeGraph[c]));

    activeStages.clear();
    pCodes.forEach((c) => {
      const sr = (pipeGraph[c] || {}).stage_req || { mode: "none", stages: [] };
      if (sr.mode === "all") {
        (sr.stages || []).forEach((s) => activeStages.add(s));
      }
    });
    if (activeStages.size === 0) activeStages.add("stg1");

    selectedCodes.clear();
    pCodes.forEach((c) => {
      const excls = ((pipeGraph[c] || {}).excl || []).filter((x) => x !== c);
      excls.forEach((x) => selectedCodes.delete(x));
      selectedCodes.add(c);
    });
    pruneInvalidSelections();
    activePreset = pid;
    lastNotice = `Loaded preset: ${pinfo.label}.`;
    renderPipeline();
  }

  stageToggleBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const sk = btn.getAttribute("data-pipe-stage") || "";
      if (!sk) return;
      activePreset = null;
      const before = selectedCodes.size;
      if (activeStages.has(sk)) {
        activeStages.delete(sk);
      } else {
        activeStages.add(sk);
      }
      pruneInvalidSelections();
      const dropped = before - selectedCodes.size;
      const lbl = STAGE_LABELS[sk] || sk;
      lastNotice = activeStages.has(sk)
        ? `Enabled ${lbl}.`
        : dropped > 0
        ? `Disabled ${lbl} (turned off ${dropped} choice${dropped === 1 ? "" : "s"}).`
        : `Disabled ${lbl}.`;
      renderPipeline();
    });
  });

  pipeCards.forEach((el) => {
    const code = el.getAttribute("data-pipe-code") || "";
    el.addEventListener("mouseenter", () => {
      hoveredCode = code;
      renderPipeline();
    });
    el.addEventListener("mouseleave", () => {
      hoveredCode = null;
      renderPipeline();
    });
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("a")) return;
      ev.preventDefault();
      toggleCode(code);
    });
    el.addEventListener("keydown", (ev) => {
      if (ev.target.closest("a")) return;
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        toggleCode(code);
      }
    });
  });

  document.querySelectorAll("[data-pipe-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-pipe-preset") || "";
      if (pid) applyPreset(pid);
    });
  });

  document.querySelectorAll("[data-pipe-depth]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-pipe-depth]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      scopeDepth = btn.getAttribute("data-pipe-depth") || "direct";
      renderPipeline();
    });
  });

  const pipeResetBtn = document.getElementById("algo-pipe-reset");
  if (pipeResetBtn) {
    pipeResetBtn.addEventListener("click", () => {
      activeStages.clear();
      DEFAULT_STAGES.forEach((s) => activeStages.add(s));
      selectedCodes.clear();
      DEFAULT_SELECTED.forEach((c) => {
        if (pipeGraph[c]) selectedCodes.add(c);
      });
      activePreset = null;
      hoveredCode = null;
      lastNotice = "Reset to baseline loop choices.";
      renderPipeline();
    });
  }

  const pipeClearBtn = document.getElementById("algo-pipe-clear");
  if (pipeClearBtn) {
    pipeClearBtn.addEventListener("click", () => {
      Array.from(selectedCodes).forEach((c) => {
        if ((pipeGraph[c] || {}).role !== "simulation") {
          selectedCodes.delete(c);
        }
      });
      activePreset = null;
      hoveredCode = null;
      lastNotice = "Cleared loop choices (top stage & simulation setup kept).";
      renderPipeline();
    });
  }

  renderPipeline();
})();
