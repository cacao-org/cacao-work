/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

(function() {
  var root = document.getElementById("options-ref-root");
  if (!root) return;

  var tabBtns = Array.from(root.querySelectorAll(".ref-tab-btn"));
  var tabPanels = Array.from(root.querySelectorAll(".ref-tab-panel"));

  function activateTab(name) {
    tabBtns.forEach(function(b) {
      var on = b.getAttribute("data-ref-tab") === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    tabPanels.forEach(function(p) {
      p.classList.toggle("active", p.getAttribute("data-ref-panel") === name);
    });
  }

  tabBtns.forEach(function(btn) {
    btn.addEventListener("click", function() {
      activateTab(btn.getAttribute("data-ref-tab") || "bench");
    });
  });

  // ── Tab 1: .bench Optical Elements ────────────────────────────────────────
  var benchRows = Array.from(root.querySelectorAll("tr.ref-bench-row"));
  var benchSecBtns = Array.from(root.querySelectorAll("[data-ref-sec]"));
  var benchModeBtns = Array.from(root.querySelectorAll("[data-ref-mode]"));
  var benchTierBtns = Array.from(root.querySelectorAll("[data-ref-tier]"));
  var benchSearch = document.getElementById("ref-bench-search");
  var benchCount = document.getElementById("ref-bench-count");
  var benchEmpty = document.getElementById("ref-bench-empty");
  var benchReset = document.getElementById("ref-bench-reset");
  var bState = { sec: "all", mode: "all", tier: "all" };

  function filterBench() {
    var q = benchSearch ? benchSearch.value.toLowerCase().trim() : "";
    var vis = 0;
    benchRows.forEach(function(tr) {
      var ok =
        (bState.sec === "all" || tr.getAttribute("data-sec") === bState.sec) &&
        (bState.mode === "all" || tr.getAttribute("data-mode") === bState.mode) &&
        (bState.tier === "all" || tr.getAttribute("data-tier") === bState.tier) &&
        (q === "" || (tr.getAttribute("data-search") || "").indexOf(q) !== -1);
      tr.classList.toggle("hidden", !ok);
      if (ok) vis++;
    });
    if (benchCount) benchCount.textContent = vis + " / " + benchRows.length;
    if (benchEmpty) benchEmpty.classList.toggle("hidden", vis > 0);
  }

  function resetBenchFilters() {
    bState = { sec: "all", mode: "all", tier: "all" };
    benchSecBtns.forEach(function(b) {
      b.classList.toggle("active", b.getAttribute("data-ref-sec") === "all");
    });
    benchModeBtns.forEach(function(b) {
      b.classList.toggle("active", b.getAttribute("data-ref-mode") === "all");
    });
    benchTierBtns.forEach(function(b) {
      b.classList.toggle("active", b.getAttribute("data-ref-tier") === "all");
    });
    if (benchSearch) benchSearch.value = "";
    filterBench();
  }

  benchSecBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      bState.sec = b.getAttribute("data-ref-sec") || "all";
      benchSecBtns.forEach(function(x) { x.classList.toggle("active", x === b); });
      filterBench();
    });
  });
  benchModeBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      bState.mode = b.getAttribute("data-ref-mode") || "all";
      benchModeBtns.forEach(function(x) { x.classList.toggle("active", x === b); });
      filterBench();
    });
  });
  benchTierBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      bState.tier = b.getAttribute("data-ref-tier") || "all";
      benchTierBtns.forEach(function(x) { x.classList.toggle("active", x === b); });
      filterBench();
    });
  });
  if (benchSearch) benchSearch.addEventListener("input", filterBench);
  if (benchReset) benchReset.addEventListener("click", resetBenchFilters);

  // ── Tab 2: FPS Runtime Units ──────────────────────────────────────────────
  var fpsRows = Array.from(root.querySelectorAll("tr.ref-fps-row"));
  var fpsPkgBtns = Array.from(root.querySelectorAll("[data-ref-pkg]"));
  var fpsAccBtns = Array.from(root.querySelectorAll("[data-ref-acc]"));
  var fpsUnitChips = Array.from(root.querySelectorAll("[data-ref-unit-jump]"));
  var fpsUnitSel = document.getElementById("ref-fps-unit-select");
  var fpsSearch = document.getElementById("ref-fps-search");
  var fpsCount = document.getElementById("ref-fps-count");
  var fpsEmpty = document.getElementById("ref-fps-empty");
  var fpsReset = document.getElementById("ref-fps-reset");
  var fState = { pkg: "all", acc: "all", unit: "all" };

  function filterFps() {
    var q = fpsSearch ? fpsSearch.value.toLowerCase().trim() : "";
    var vis = 0;
    fpsRows.forEach(function(tr) {
      var ok =
        (fState.pkg === "all" || tr.getAttribute("data-pkg") === fState.pkg) &&
        (fState.acc === "all" || tr.getAttribute("data-access") === fState.acc) &&
        (fState.unit === "all" || tr.getAttribute("data-unit") === fState.unit) &&
        (q === "" || (tr.getAttribute("data-search") || "").indexOf(q) !== -1);
      tr.classList.toggle("hidden", !ok);
      if (ok) vis++;
    });
    fpsUnitChips.forEach(function(c) {
      c.classList.toggle("active", c.getAttribute("data-ref-unit-jump") === fState.unit);
    });
    if (fpsUnitSel) fpsUnitSel.value = fState.unit;
    if (fpsCount) fpsCount.textContent = vis + " / " + fpsRows.length;
    if (fpsEmpty) fpsEmpty.classList.toggle("hidden", vis > 0);
  }

  function resetFpsFilters() {
    fState = { pkg: "all", acc: "all", unit: "all" };
    fpsPkgBtns.forEach(function(b) {
      b.classList.toggle("active", b.getAttribute("data-ref-pkg") === "all");
    });
    fpsAccBtns.forEach(function(b) {
      b.classList.toggle("active", b.getAttribute("data-ref-acc") === "all");
    });
    if (fpsSearch) fpsSearch.value = "";
    filterFps();
  }

  fpsPkgBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      fState.pkg = b.getAttribute("data-ref-pkg") || "all";
      fState.unit = "all";
      fpsPkgBtns.forEach(function(x) { x.classList.toggle("active", x === b); });
      filterFps();
    });
  });
  fpsAccBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      fState.acc = b.getAttribute("data-ref-acc") || "all";
      fpsAccBtns.forEach(function(x) { x.classList.toggle("active", x === b); });
      filterFps();
    });
  });
  fpsUnitChips.forEach(function(c) {
    c.addEventListener("click", function() {
      var u = c.getAttribute("data-ref-unit-jump") || "all";
      fState.unit = fState.unit === u ? "all" : u;
      filterFps();
    });
  });
  if (fpsUnitSel) {
    fpsUnitSel.addEventListener("change", function() {
      fState.unit = fpsUnitSel.value || "all";
      filterFps();
    });
  }
  if (fpsSearch) fpsSearch.addEventListener("input", filterFps);
  if (fpsReset) fpsReset.addEventListener("click", resetFpsFilters);

  // ── Tab 3: CLI Flags & Runner Env Vars ────────────────────────────────────
  var cliRows = Array.from(root.querySelectorAll("tr.ref-cli-row"));
  var cliToolBtns = Array.from(root.querySelectorAll("[data-ref-tool]"));
  var cliSearch = document.getElementById("ref-cli-search");
  var cliCount = document.getElementById("ref-cli-count");
  var cliEmpty = document.getElementById("ref-cli-empty");
  var cliReset = document.getElementById("ref-cli-reset");
  var cTool = "all";

  function filterCli() {
    var q = cliSearch ? cliSearch.value.toLowerCase().trim() : "";
    var vis = 0;
    cliRows.forEach(function(tr) {
      var ok =
        (cTool === "all" || tr.getAttribute("data-tool") === cTool) &&
        (q === "" || (tr.getAttribute("data-search") || "").indexOf(q) !== -1);
      tr.classList.toggle("hidden", !ok);
      if (ok) vis++;
    });
    if (cliCount) cliCount.textContent = vis + " / " + cliRows.length;
    if (cliEmpty) cliEmpty.classList.toggle("hidden", vis > 0);
  }

  function resetCliFilters() {
    cTool = "all";
    cliToolBtns.forEach(function(b) {
      b.classList.toggle("active", b.getAttribute("data-ref-tool") === "all");
    });
    if (cliSearch) cliSearch.value = "";
    filterCli();
  }

  cliToolBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      cTool = b.getAttribute("data-ref-tool") || "all";
      cliToolBtns.forEach(function(x) { x.classList.toggle("active", x === b); });
      filterCli();
    });
  });
  if (cliSearch) cliSearch.addEventListener("input", filterCli);
  if (cliReset) cliReset.addEventListener("click", resetCliFilters);

  // ── Copy Deep Link Buttons ────────────────────────────────────────────────
  root.addEventListener("click", function(ev) {
    var btn = ev.target.closest(".opt-copy-btn");
    if (!btn) return;
    var anchor = btn.getAttribute("data-copy-anchor") || "";
    var url = window.location.href.split("#")[0] + anchor;
    if (history.replaceState) history.replaceState(null, "", anchor);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).catch(function() {});
    }
    var orig = btn.textContent;
    btn.textContent = "\u2713";
    setTimeout(function() { btn.textContent = orig; }, 900);
  });

  // ── Deep-Link Hash Routing ────────────────────────────────────────────────
  function focusHash() {
    var raw = (window.location.hash || "").replace(/^#/, "");
    if (!raw) return;
    var target = document.getElementById(raw);
    if (!target) return;
    var panel = target.closest(".ref-tab-panel");
    if (panel) {
      var tab = panel.getAttribute("data-ref-panel") || "bench";
      activateTab(tab);
      if (tab === "bench") resetBenchFilters();
      else if (tab === "fps") resetFpsFilters();
      else if (tab === "cli") resetCliFilters();
    }
    if (target.classList.contains("ref-unit-chip")) {
      var ukey = target.getAttribute("data-ref-unit-jump") || "all";
      fState.unit = ukey;
      filterFps();
    }
    target.classList.remove("opt-row-flash");
    void target.offsetWidth;
    target.classList.add("opt-row-flash");
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  window.addEventListener("hashchange", focusHash);
  focusHash();
})();
