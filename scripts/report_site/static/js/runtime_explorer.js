/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

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
