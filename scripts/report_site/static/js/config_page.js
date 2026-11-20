/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

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
