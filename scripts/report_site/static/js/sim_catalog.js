/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

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
  var domainBtns = Array.from(document.querySelectorAll("[data-sim-domain]"));
  var ctrlBtns = Array.from(document.querySelectorAll("[data-sim-ctrl]"));
  var triGroups = Array.from(document.querySelectorAll("[data-sim-tri]"));
  var selectedDomains = {};
  var selectedCtrls = {};
  var triState = {};

  domainBtns.forEach(function(b) {
    var k = b.getAttribute("data-sim-domain");
    if (k && b.classList.contains("active")) selectedDomains[k] = true;
  });
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
      var rd = tr.getAttribute("data-domain") || "";
      var okDom = domainBtns.length === 0 || Boolean(selectedDomains[rd]);
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
      var vis = okDom && okCtrl && okTri && okQ;
      tr.classList.toggle("hidden", !vis);
      if (vis) shown++;
    });
    if (simCount) simCount.textContent = shown + " / " + rows.length + " simulations";
    if (simEmpty) simEmpty.classList.toggle("hidden", shown > 0);
  }

  domainBtns.forEach(function(b) {
    b.addEventListener("click", function() {
      var k = b.getAttribute("data-sim-domain");
      if (!k) return;
      selectedDomains[k] = !selectedDomains[k];
      b.classList.toggle("active", selectedDomains[k]);
      b.setAttribute("aria-pressed", selectedDomains[k] ? "true" : "false");
      applySimFilter();
    });
  });

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
      domainBtns.forEach(function(b) {
        var k = b.getAttribute("data-sim-domain");
        if (k) selectedDomains[k] = true;
        b.classList.add("active");
        b.setAttribute("aria-pressed", "true");
      });
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
        if (preset === "all") {
          var tr = cb.closest("tr");
          cb.checked = !tr || !tr.classList.contains("hidden");
          return;
        }
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
