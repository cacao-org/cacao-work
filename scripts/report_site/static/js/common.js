/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

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
    if (!s || s === "\u2014" || s === "-") return null;
    var m = s.match(/^([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/);
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
