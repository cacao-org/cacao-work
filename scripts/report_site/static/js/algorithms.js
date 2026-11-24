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
  const roleSelect = document.getElementById("algo-role-select");
  const stageSelect = document.getElementById("algo-stage-select");
  const traceSelect = document.getElementById("algo-trace-select");
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
    if (traceSelect) {
      const hasOpt =
        activeTrace &&
        Array.from(traceSelect.options).some((o) => o.value === activeTrace);
      traceSelect.value = hasOpt ? activeTrace : "";
    }
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

  if (roleSelect) {
    roleSelect.addEventListener("change", () => {
      activeRole = roleSelect.value || "all";
      applyFilters();
    });
  }

  if (stageSelect) {
    stageSelect.addEventListener("change", () => {
      activeStage = stageSelect.value || "all";
      applyFilters();
    });
  }

  if (traceSelect) {
    traceSelect.addEventListener("change", () => {
      const v = traceSelect.value || "";
      activeTrace = null;
      applyTrace(v || null);
    });
  }

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
      if (roleSelect) roleSelect.value = "all";
      if (stageSelect) stageSelect.value = "all";
      if (traceSelect) traceSelect.value = "";
      if (searchInput) searchInput.value = "";
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
  const pipeGuidance = document.getElementById("algo-pipe-guidance");
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

  const toggleCards = Array.from(
    pipeWorkspace.querySelectorAll(".algo-pipe-toggle-card[data-pipe-code]")
  );
  const selectCards = Array.from(
    pipeWorkspace.querySelectorAll(".algo-pipe-select-card[data-pipe-select-group]")
  );
  const allPipeWidgets = [].concat(selectCards, toggleCards);
  const allOrderedCodes = Object.keys(pipeGraph);
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

  function missingPrereqsWithSet(code, activeSet) {
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
      if (clause.length && !clause.some((r) => activeSet.has(r))) {
        missReqs.push(clause.join(" or "));
      }
    });
    return { stages: missStages, reqs: missReqs };
  }

  function missingPrereqs(code) {
    return missingPrereqsWithSet(code, selectedCodes);
  }

  function isSelectable(code) {
    const m = missingPrereqs(code);
    return m.stages.length === 0 && m.reqs.length === 0;
  }

  function optionMissing(valStr, groupCodes) {
    if (!valStr) return { stages: [], reqs: [] };
    const parts = valStr.split("+").filter(Boolean);
    const trial = new Set(selectedCodes);
    (groupCodes || []).forEach((gc) => trial.delete(gc));
    for (let i = 0; i < parts.length; i += 1) {
      const m = missingPrereqsWithSet(parts[i], trial);
      if (m.stages.length || m.reqs.length) return m;
      trial.add(parts[i]);
    }
    return { stages: [], reqs: [] };
  }

  function isOptionSelectable(valStr, groupCodes) {
    const m = optionMissing(valStr, groupCodes);
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

  function activeCodeForSelectCard(card) {
    const sel = card.querySelector("select.algo-ctrl-select");
    if (!sel) return "";
    const curVal = sel.value || "";
    if (curVal) {
      const parts = curVal.split("+").filter(Boolean);
      return parts[parts.length - 1] || "";
    }
    const opts = Array.from(sel.options);
    for (let i = 0; i < opts.length; i += 1) {
      const pc = opts[i].getAttribute("data-pipe-code") || "";
      if (pc) return pc;
    }
    return "";
  }

  function renderPipeline() {
    pruneInvalidSelections();

    stageToggleBtns.forEach((btn) => {
      const sk = btn.getAttribute("data-pipe-stage") || "";
      const on = activeStages.has(sk);
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });

    const presetSel = document.getElementById("algo-pipe-preset-select");
    if (presetSel) {
      presetSel.value = activePreset || "";
    }

    let nSel = 0;
    let nAvail = 0;
    let nLocked = 0;

    // 1. Sync Pulldown (<select>) cards
    selectCards.forEach((card) => {
      const sel = card.querySelector("select.algo-ctrl-select");
      if (!sel) return;
      const groupCodes = (card.getAttribute("data-pipe-codes") || "")
        .split(",")
        .filter(Boolean);
      const allowOff = card.getAttribute("data-pipe-allow-off") === "1";
      const opts = Array.from(sel.options);

      // Determine best matching value from selectedCodes (prefer longest composite match)
      let matchedVal = "";
      let bestLen = 0;
      opts.forEach((opt) => {
        const val = opt.value || "";
        if (!val) return;
        const parts = val.split("+").filter(Boolean);
        if (parts.length > bestLen && parts.every((p) => selectedCodes.has(p))) {
          matchedVal = val;
          bestLen = parts.length;
        }
      });

      // Enable/disable individual <option> entries based on live prerequisites
      let anyNonOffSelectable = false;
      let firstLockedReason = "";
      const lockedOptItems = [];
      opts.forEach((opt) => {
        const val = opt.value || "";
        const baseLbl = opt.getAttribute("data-base-label") || opt.textContent || "";
        if (!val) {
          opt.disabled = false;
          opt.textContent = baseLbl;
          return;
        }
        const m = optionMissing(val, groupCodes);
        const ok = m.stages.length === 0 && m.reqs.length === 0;
        opt.disabled = !ok;
        if (ok) {
          anyNonOffSelectable = true;
          opt.textContent = baseLbl;
        } else {
          const reason = formatMissingText(m);
          if (!firstLockedReason) firstLockedReason = reason;
          const optCode = opt.getAttribute("data-pipe-code") || val;
          lockedOptItems.push({ code: optCode, reason: reason });
          opt.textContent = baseLbl + " [disabled: needs " + reason + "]";
        }
      });

      sel.value = matchedVal;
      const isLockedSelect = allowOff && !matchedVal && !anyNonOffSelectable;
      sel.disabled = isLockedSelect;
      if (isLockedSelect && opts[0] && !opts[0].value) {
        opts[0].textContent = "Off (Disabled)";
      }

      const lockNote = card.querySelector(".algo-lock-reason");
      if (lockNote) {
        if (isLockedSelect) {
          lockNote.textContent =
            "\u2298 Disabled \u2014 needs " + (firstLockedReason || "prerequisites");
          lockNote.classList.remove("hidden", "algo-lock-partial");
          lockNote.classList.add("algo-lock-full");
        } else if (lockedOptItems.length > 0) {
          const summary = lockedOptItems
            .map((it) => `${it.code} (needs ${it.reason})`)
            .join(" \u00b7 ");
          lockNote.textContent = "\u2298 Disabled choice: " + summary;
          lockNote.classList.remove("hidden", "algo-lock-full");
          lockNote.classList.add("algo-lock-partial");
        } else {
          lockNote.textContent = "";
          lockNote.classList.add("hidden");
          lockNote.classList.remove("algo-lock-full", "algo-lock-partial");
        }
      }

      // Sync active code badge & docs link in card header
      const badge = card.querySelector(".algo-select-active-badge");
      const dlink = card.querySelector(".algo-select-docs-link");
      const activeOpt = sel.selectedOptions && sel.selectedOptions[0];
      const firstRealOpt = opts.find((o) => Boolean(o.value));
      const refOpt = (activeOpt && activeOpt.value ? activeOpt : firstRealOpt) || null;
      const activeCode =
        activeOpt && activeOpt.value ? activeOpt.getAttribute("data-pipe-code") || "" : "";
      const refHref = refOpt ? refOpt.getAttribute("data-doc-href") || "#" : "#";
      const refCode = refOpt ? refOpt.getAttribute("data-pipe-code") || "" : "";

      if (badge) {
        badge.textContent = isLockedSelect ? "DISABLED" : activeCode || "OFF";
        badge.setAttribute("href", refHref);
        badge.setAttribute(
          "title",
          isLockedSelect
            ? "Disabled (needs " + (firstLockedReason || "prerequisites") + ") — click to view " + refCode + " docs"
            : activeCode
            ? "Open " + activeCode + " documentation"
            : "Currently off — click to view " + refCode + " documentation"
        );
        badge.classList.toggle("algo-badge-off", !activeCode && !isLockedSelect);
        badge.classList.toggle("algo-badge-locked", isLockedSelect);
      }
      if (dlink) {
        dlink.setAttribute("href", refHref);
        dlink.setAttribute("title", "Open " + (activeCode || refCode) + " documentation");
      }

      card.classList.remove(
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

      const isSimGroup = groupCodes.every((gc) => (pipeGraph[gc] || {}).role === "simulation");
      if (matchedVal) {
        card.classList.add("pipe-selected");
        card.setAttribute("title", activeCode + " is active — use pulldown to switch");
        if (!isSimGroup) nSel += 1;
      } else if (anyNonOffSelectable) {
        card.classList.add("pipe-available");
        card.setAttribute("title", "Off — choose an option from the pulldown");
        if (!isSimGroup) nAvail += 1;
      } else {
        card.classList.add("pipe-locked");
        card.setAttribute(
          "title",
          "Disabled — requires: " + (firstLockedReason || "prerequisites")
        );
        if (!isSimGroup) nLocked += 1;
      }
    });

    // 2. Sync ON/OFF Toggle Switch cards
    toggleCards.forEach((el) => {
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

      const swLbl = el.querySelector(".algo-switch-lbl");
      const lockNote = el.querySelector(".algo-lock-reason");
      if (sel) {
        el.classList.add("pipe-selected");
        el.setAttribute("aria-checked", "true");
        el.setAttribute("aria-disabled", "false");
        el.setAttribute("title", c + " is ON — click to turn OFF");
        if (swLbl) swLbl.textContent = "ON";
        if (lockNote) {
          lockNote.textContent = "";
          lockNote.classList.add("hidden");
          lockNote.classList.remove("algo-lock-full");
        }
        if (!isSim) nSel += 1;
      } else if (avail) {
        el.classList.add("pipe-available");
        el.setAttribute("aria-checked", "false");
        el.setAttribute("aria-disabled", "false");
        el.setAttribute("title", c + " is OFF — click to turn ON");
        if (swLbl) swLbl.textContent = "OFF";
        if (lockNote) {
          lockNote.textContent = "";
          lockNote.classList.add("hidden");
          lockNote.classList.remove("algo-lock-full");
        }
        if (!isSim) nAvail += 1;
      } else {
        el.classList.add("pipe-locked");
        el.setAttribute("aria-checked", "false");
        el.setAttribute("aria-disabled", "true");
        const miss = formatMissingText(missingPrereqs(c));
        el.setAttribute("title", "Disabled — requires: " + (miss || "prerequisites"));
        if (swLbl) swLbl.textContent = "DISABLED";
        if (lockNote) {
          lockNote.textContent = "\u2298 Disabled \u2014 needs " + (miss || "prerequisites");
          lockNote.classList.remove("hidden");
          lockNote.classList.add("algo-lock-full");
        }
        if (!isSim) nLocked += 1;
      }
    });

    if (pipeProfile) {
      const stagePills = DEFAULT_STAGES.filter((s) => activeStages.has(s)).map(
        (s) => `<span class="algo-prof-tag algo-prof-stage">${STAGE_LABELS[s] || s}</span>`
      );
      const choicePills = allOrderedCodes
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

    if (pipeGuidance) {
      const hasEof = selectedCodes.has("EOF/BASE");
      const hasAr = selectedCodes.has("PF/AR");
      const hasSlGlob = selectedCodes.has("SL/GLOBAL");
      const hasSlClust = selectedCodes.has("SL/CLUST");
      const hasMopt = selectedCodes.has("MOPT");
      const hasRot = selectedCodes.has("CMODES/ROT");
      const hasNotch = selectedCodes.has("CMODES/NOTCH");
      const hasMr = selectedCodes.has("DM/MR");
      const hasPresh = selectedCodes.has("PRESH/4K");
      const hasSlow = selectedCodes.has("WFS/SLOW");
      const hasUnmod = selectedCodes.has("WFS/UNMOD");

      let coreTier = "None";
      if (hasSlClust) coreTier = "Block-EOF + Cascaded Global & Clustered Self-Learning";
      else if (hasSlGlob) coreTier = "Block-EOF + Cascaded Global Online Adaptive Filter";
      else if (hasEof) coreTier = "Cross-Mode Block-EOF";
      else if (hasAr) coreTier = "Per-Mode Diagonal AR(P)";
      else if (hasMopt) coreTier = "Autotuned Leaky Integrator (MOPT)";
      else if (selectedCodes.has("INT/MGAIN")) coreTier = "Power-Law Modal Integrator";
      else if (selectedCodes.has("INT/LEAK")) coreTier = "Manual Uniform Leaky Integrator";

      let innerTier = "Fixed modal basis (standard modalfilter)";
      if (hasNotch) innerTier = "Decoupled Q-Rotation + 16-Mode AR(48) Notch (re-projected)";
      else if (hasRot) innerTier = "Decoupled Noise-Whitened Q-Rotation inside modalfilter";

      let dmTier = "Standard WFS-rate DM commands";
      if (hasMr && hasPresh) dmTier = "Multi-Rate Pacer (user f_DM) -> DMch2disp -> Plate Pre-Shaper (f_presh >= f_DM)";
      else if (hasMr) dmTier = "Multi-Rate Centered Linear-Ramp Pacer (mvalpacer @ user f_DM)";
      else if (hasPresh) dmTier = "2-8 kHz DM Mechanical Anti-Vibration Pre-Shaper (modal & per-actuator)";

      let rtCpu = "~22.6 us (1,255 modes baseline)";
      if (hasSlClust || hasSlGlob) {
        rtCpu = "~88.9 us @ 128 m (17.8% of 2 kHz) / ~113.9 us @ 256 m (22.8%)";
      } else if (hasEof && hasRot) {
        rtCpu = "~21.2 us @ 128 m (4.2% of 2 kHz)";
      } else if (hasEof) {
        rtCpu = "~18.8 us @ 128 m (applyEOFPF + modalfilter)";
      }

      const notes = [];
      if (hasSlGlob || hasSlClust) {
        notes.push(
          "Cascaded on Fixed-Basis Block-EOF: Stein gates hold pure white-noise leakage to 1.43 nm (1.000x vs 18.35 nm standalone)."
        );
      }
      if (hasRot && (hasEof || hasSlGlob || hasSlClust)) {
        notes.push(
          "Decoupled basis invariant: Q rotates strictly inside modalfilter (47.5 nm bumpless swaps vs 213-367 nm if rotating outer EOF/SL)."
        );
      }
      if (hasMr && hasPresh) {
        notes.push(
          "Optimal DM order: smooth ramps at user hardware rate f_DM upstream of dmpreshaper cut pre-shaper stroke 18-40%, HF ripple -35%, plate band -40%, 0 clips (AO3k f_DM=1 kHz benchmark)."
        );
      } else if (hasSlow && !hasMr) {
        notes.push(
          "Tip: With WFS/SLOW (250-500 Hz), pair EOF/BASE + DM/MR (supplying hardware DM rate f_DM) to replace coarse ZOH steps with smooth linear ramps (0.000 fr added lag)."
        );
      } else if (hasSlow && !hasEof) {
        notes.push(
          "Warning: Slowing WFS to 250 Hz without predictive control causes integrator Strehl collapse (50.7% -> 38.6% at m=10)."
        );
      }
      if (hasUnmod && hasEof && !hasSlClust) {
        notes.push(
          "Tip: Unmodulated 0 l/D PyWFS benefits strongly from Cascaded Clustered Self-Learning (SL/GLOBAL + SL/CLUST: -36.4% WFE)."
        );
      }

      const noteHtml = notes.length
        ? '<div class="algo-guid-notes">' +
          notes.map((n) => `<span class="algo-guid-note">${n}</span>`).join("") +
          "</div>"
        : "";

      pipeGuidance.innerHTML =
        '<div class="algo-guid-row">' +
        `<span><strong>Core Control:</strong> ${coreTier}</span>` +
        `<span><strong>Inner Modes:</strong> ${innerTier}</span>` +
        `<span><strong>DM Actuation:</strong> ${dmTier}</span>` +
        `<span><strong>Est. RT CPU:</strong> ${rtCpu}</span>` +
        "</div>" +
        noteHtml;
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

      function widgetCodes(el) {
        if (el.classList.contains("algo-pipe-select-card")) {
          return (el.getAttribute("data-pipe-codes") || "").split(",").filter(Boolean);
        }
        const c = el.getAttribute("data-pipe-code") || "";
        return c ? [c] : [];
      }

      allPipeWidgets.forEach((el) => {
        const codes = widgetCodes(el);
        const hasAny = (set) => codes.some((c) => set.has(c));
        if (codes.indexOf(focus) !== -1) el.classList.add("pipe-focus");
        else if (hasAny(upReq)) el.classList.add("pipe-up");
        else if (hasAny(downSet)) el.classList.add("pipe-down");
        else if (hasAny(fbSet)) el.classList.add("pipe-fb");
        else if (hasAny(exclSet)) el.classList.add("pipe-excl");
        else if (hasAny(upOpt) || hasAny(downOpt)) el.classList.add("pipe-opt");
        else el.classList.add("pipe-dim");
      });

      if (pipeStatus) {
        const miss = missingPrereqs(focus);
        const stateStr =
          !selectedCodes.has(focus) && (miss.stages.length || miss.reqs.length)
            ? " &middot; <strong>Locked (needs: " + formatMissingText(miss) + ")</strong>"
            : selectedCodes.has(focus)
            ? " &middot; <strong>Active</strong>"
            : " &middot; <strong>Available</strong>";
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
        `Controls: <strong>${nSel} active</strong>, ` +
        `<strong>${nAvail} available</strong>, ` +
        `<strong>${nLocked} disabled</strong>${noteHtml}</span>`;
    }
  }

  function applySelectGroup(card, valStr) {
    const groupCodes = (card.getAttribute("data-pipe-codes") || "")
      .split(",")
      .filter(Boolean);
    const labelEl = card.querySelector(".algo-select-lbl");
    const groupLbl = labelEl ? labelEl.textContent.trim() : "Choice";
    activePreset = null;

    if (valStr && !isOptionSelectable(valStr, groupCodes)) {
      const miss = formatMissingText(optionMissing(valStr, groupCodes));
      lastNotice = `${valStr} is locked — enable ${miss} first.`;
      renderPipeline();
      return;
    }

    const before = new Set(selectedCodes);
    groupCodes.forEach((gc) => selectedCodes.delete(gc));
    const added = [];
    if (valStr) {
      valStr
        .split("+")
        .filter(Boolean)
        .forEach((code) => {
          const excls = ((pipeGraph[code] || {}).excl || []).filter((x) => x !== code);
          excls.forEach((x) => selectedCodes.delete(x));
          selectedCodes.add(code);
          added.push(code);
        });
    }
    pruneInvalidSelections();

    let cascaded = 0;
    before.forEach((c) => {
      if (!selectedCodes.has(c) && groupCodes.indexOf(c) === -1) cascaded += 1;
    });
    if (!valStr) {
      lastNotice =
        cascaded > 0
          ? `Turned off ${groupLbl} (and ${cascaded} dependent option${cascaded === 1 ? "" : "s"}).`
          : `Turned off ${groupLbl}.`;
    } else {
      lastNotice =
        `Set ${groupLbl} → ${added.join(" + ")}` +
        (cascaded > 0 ? ` (turned off ${cascaded} incompatible/dependent).` : ".");
    }
    renderPipeline();
  }

  function toggleCode(code) {
    const node = pipeGraph[code];
    if (!node) return;
    activePreset = null;
    if (selectedCodes.has(code)) {
      const before = selectedCodes.size;
      selectedCodes.delete(code);
      pruneInvalidSelections();
      const dropped = before - selectedCodes.size - 1;
      lastNotice =
        dropped > 0
          ? `Turned off ${code} (and ${dropped} dependent option${dropped === 1 ? "" : "s"}).`
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
          `Enabled ${code} — switched off ${conflicts.join(", ")}` +
          (cascaded > 0 ? ` (+${cascaded} dependent).` : ".");
      } else {
        lastNotice = `Enabled ${code}.`;
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

  selectCards.forEach((card) => {
    const sel = card.querySelector("select.algo-ctrl-select");
    card.addEventListener("mouseenter", () => {
      hoveredCode = activeCodeForSelectCard(card) || null;
      renderPipeline();
    });
    card.addEventListener("mouseleave", () => {
      hoveredCode = null;
      renderPipeline();
    });
    if (sel) {
      sel.addEventListener("change", () => {
        applySelectGroup(card, sel.value || "");
        hoveredCode = activeCodeForSelectCard(card) || null;
        renderPipeline();
      });
    }
  });

  toggleCards.forEach((el) => {
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

  const pipePresetSelect = document.getElementById("algo-pipe-preset-select");
  if (pipePresetSelect) {
    pipePresetSelect.addEventListener("change", () => {
      const pid = pipePresetSelect.value || "";
      if (pid) applyPreset(pid);
    });
  }

  const pipeDepthSelect = document.getElementById("algo-pipe-depth-select");
  if (pipeDepthSelect) {
    pipeDepthSelect.addEventListener("change", () => {
      scopeDepth = pipeDepthSelect.value || "direct";
      renderPipeline();
    });
  }

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
