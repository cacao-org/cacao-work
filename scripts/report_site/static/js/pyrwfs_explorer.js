/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

(function() {
  var dataEl = document.getElementById("pyrwfs-explorer-data");
  if (!dataEl) return;
  var payload = {};
  try { payload = JSON.parse(dataEl.textContent || "{}"); } catch (e) { return; }
  var tsMap = payload.timeseries || {};
  var stageKeys = Object.keys(tsMap).filter(function(k) {
    return tsMap[k] && tsMap[k].t_phys_s && tsMap[k].t_phys_s.length > 0;
  });
  if (!stageKeys.length) return;

  var canvas = document.getElementById("pyrwfs-canvas");
  var tip = document.getElementById("pyrwfs-tooltip");
  var legendEl = document.getElementById("pyrwfs-legend");
  if (!canvas || !canvas.getContext) return;

  var tabBtns = Array.from(document.querySelectorAll("[data-pyr-tab]"));
  var stgBtns = Array.from(document.querySelectorAll("[data-pyr-stg]"));
  var activeTab = tabBtns[0] ? tabBtns[0].getAttribute("data-pyr-tab") : "flux";
  var activeStg = stgBtns[0] ? stgBtns[0].getAttribute("data-pyr-stg") : "both";
  if (stageKeys.length === 1) activeStg = stageKeys[0];
  var lastPlot = null;

  var STAGE_COL = { stage1: "#2563eb", stage2: "#d97706" };
  var STAGE_LBL = { stage1: "Stg1 NIR", stage2: "Stg2 Vis" };

  function meanOf(arr) {
    if (!arr || !arr.length) return NaN;
    var s = 0, n = 0;
    for (var i = 0; i < arr.length; i++) {
      if (isFinite(arr[i])) { s += arr[i]; n++; }
    }
    return n ? (s / n) : NaN;
  }

  function scaleArr(arr, mult) {
    return (arr || []).map(function(v) { return isFinite(v) ? v * mult : NaN; });
  }

  function buildSeries() {
    var selKeys = (activeStg === "both") ? stageKeys : stageKeys.filter(function(k) { return k === activeStg; });
    if (!selKeys.length) selKeys = stageKeys;
    var series = [];
    var yLabel = "";
    var title = "";
    var refZero = false;

    selKeys.forEach(function(sk, si) {
      var ts = tsMap[sk];
      var xs = ts.t_phys_s || [];
      var baseCol = STAGE_COL[sk] || "#2563eb";
      var sl = STAGE_LBL[sk] || sk;
      if (activeTab === "flux") {
        title = "Packed-Zone Flux Fractions [% of Net Camera Flux]";
        yLabel = "Flux Fraction [%]";
        series.push({ name: sl + " f_pup", x: xs, y: scaleArr(ts.f_pup, 100), color: baseCol, dash: [] });
        series.push({ name: sl + " f_diam", x: xs, y: scaleArr(ts.f_diam, 100), color: si === 0 ? "#0ea5e9" : "#f59e0b", dash: [6, 3] });
        series.push({ name: sl + " f_out", x: xs, y: scaleArr(ts.f_out, 100), color: si === 0 ? "#6366f1" : "#b45309", dash: [2, 3] });
      } else if (activeTab === "dfpup") {
        title = "Defocus-Invariant Flux Shift Δf_pup = f_pup − f_pup0 [%]";
        yLabel = "Δf_pup [%]";
        refZero = true;
        series.push({ name: sl + " Δf_pup", x: xs, y: scaleArr(ts.df_pup, 100), color: baseCol, dash: [] });
      } else if (activeTab === "aniso") {
        title = "Bridge Anisotropy & Even-Mode Nonlinearity Ratio";
        yLabel = "Dimensionless";
        refZero = true;
        series.push({ name: sl + " Aniso", x: xs, y: ts.aniso || [], color: baseCol, dash: [] });
        series.push({ name: sl + " NL Ratio", x: xs, y: ts.nl_ratio || [], color: si === 0 ? "#059669" : "#dc2626", dash: [5, 3] });
      } else if (activeTab === "align") {
        title = "6-DOF Edge-Based Pupil Registration Shifts [pix]";
        yLabel = "Shift [pix]";
        refZero = true;
        series.push({ name: sl + " dx", x: xs, y: ts.pup_dx || [], color: baseCol, dash: [] });
        series.push({ name: sl + " dy", x: xs, y: ts.pup_dy || [], color: si === 0 ? "#059669" : "#dc2626", dash: [6, 3] });
        series.push({ name: sl + " ds", x: xs, y: ts.pup_ds || [], color: si === 0 ? "#7c3aed" : "#0891b2", dash: [2, 3] });
      } else if (activeTab === "jitter") {
        title = "Quad-Cell Tip/Tilt Centering & Jitter RMS";
        yLabel = "Quad-Cell Signal";
        refZero = true;
        var qtt = (ts.qx_rms || []).map(function(v, idx) {
          var vy = (ts.qy_rms || [])[idx] || 0;
          return Math.hypot(v || 0, vy);
        });
        series.push({ name: sl + " TT RMS", x: xs, y: qtt, color: baseCol, dash: [] });
        series.push({ name: sl + " qx_mean", x: xs, y: ts.qx_mean || [], color: si === 0 ? "#059669" : "#dc2626", dash: [6, 3] });
        series.push({ name: sl + " qy_mean", x: xs, y: ts.qy_mean || [], color: si === 0 ? "#7c3aed" : "#0891b2", dash: [2, 3] });
      } else {
        title = "Pupil Scintillation (Raw & Debiased), Slope Curl/Div Ratio & Spider LWE";
        yLabel = "Metric Value";
        refZero = true;
        var hasDeb = Array.isArray(ts.scint_debias) && ts.scint_debias.some(function(v) { return isFinite(v); });
        if (hasDeb) {
          series.push({ name: sl + " Scint (deb)", x: xs, y: ts.scint_debias, color: baseCol, dash: [] });
          series.push({ name: sl + " Scint (raw)", x: xs, y: ts.scint_idx || [], color: si === 0 ? "#60a5fa" : "#fbbf24", dash: [4, 3] });
        } else {
          series.push({ name: sl + " Scint", x: xs, y: ts.scint_idx || [], color: baseCol, dash: [] });
        }
        series.push({ name: sl + " Curl/Div", x: xs, y: ts.curl_ratio || [], color: si === 0 ? "#059669" : "#dc2626", dash: [6, 3] });
        series.push({ name: sl + " Spider LWE", x: xs, y: ts.lwe_metric || [], color: si === 0 ? "#7c3aed" : "#0891b2", dash: [2, 3] });
      }
    });

    var xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
    series.forEach(function(s) {
      for (var i = 0; i < s.x.length; i++) {
        var xv = s.x[i], yv = s.y[i];
        if (isFinite(xv)) { if (xv < xmin) xmin = xv; if (xv > xmax) xmax = xv; }
        if (isFinite(yv)) { if (yv < ymin) ymin = yv; if (yv > ymax) ymax = yv; }
      }
    });
    if (!isFinite(xmin)) { xmin = 0; xmax = 1; }
    if (!isFinite(ymin)) { ymin = -1; ymax = 1; }
    if (refZero) { ymin = Math.min(ymin, 0); ymax = Math.max(ymax, 0); }
    var padY = (ymax - ymin) * 0.12 || 0.05;
    return {
      title: title,
      yLabel: yLabel,
      refZero: refZero,
      xmin: xmin,
      xmax: xmax,
      ymin: ymin - padY,
      ymax: ymax + padY,
      series: series
    };
  }

  function renderLegend(spec) {
    if (!legendEl) return;
    var items = spec.series.map(function(s) {
      var st = s.dash && s.dash.length ? (s.dash[0] <= 2 ? "dotted" : "dashed") : "solid";
      var m = meanOf(s.y);
      var stat = isFinite(m) ? (' <span class="muted">(mean ' + m.toFixed(3) + ")</span>") : "";
      return '<span class="opt-legend-item">' +
        '<span class="opt-legend-swatch" style="border-top-style:' + st + ";border-top-color:" + s.color + ';"></span>' +
        s.name + stat + "</span>";
    });
    legendEl.innerHTML = '<div class="opt-legend-items">' + items.join("") + "</div>";
  }

  function draw() {
    var spec = buildSeries();
    lastPlot = spec;
    renderLegend(spec);

    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 760;
    var h = 310;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    var pad = { l: 62, r: 20, t: 28, b: 38 };
    var pw = Math.max(80, w - pad.l - pad.r);
    var ph = Math.max(80, h - pad.t - pad.b);
    var spanX = Math.max(spec.xmax - spec.xmin, 1e-9);
    var spanY = Math.max(spec.ymax - spec.ymin, 1e-9);
    spec._geom = { pad: pad, pw: pw, ph: ph, spanX: spanX, spanY: spanY };

    var isDark = document.documentElement.getAttribute("data-theme") === "dark" ||
      (!document.documentElement.getAttribute("data-theme") && window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
    var gridCol = isDark ? "#334155" : "#e2e8f0";
    var textCol = isDark ? "#cbd5e1" : "#475569";

    ctx.font = "bold 12px sans-serif";
    ctx.fillStyle = textCol;
    ctx.textAlign = "left";
    ctx.fillText(spec.title, pad.l, 16);

    ctx.font = "11px sans-serif";
    ctx.strokeStyle = gridCol;
    ctx.setLineDash([]);
    for (var gi = 0; gi <= 4; gi++) {
      var gy = pad.t + (ph * gi) / 4;
      ctx.beginPath();
      ctx.moveTo(pad.l, gy);
      ctx.lineTo(pad.l + pw, gy);
      ctx.stroke();
      var yv = spec.ymax - (spanY * gi) / 4;
      ctx.textAlign = "right";
      ctx.fillText(Math.abs(yv) >= 10 ? yv.toFixed(1) : yv.toFixed(3), pad.l - 6, gy + 4);
    }
    for (var xi = 0; xi <= 5; xi++) {
      var gx = pad.l + (pw * xi) / 5;
      var xv = spec.xmin + (spanX * xi) / 5;
      ctx.textAlign = "center";
      ctx.fillText(xv.toFixed(2) + " s", gx, pad.t + ph + 16);
    }
    ctx.textAlign = "center";
    ctx.fillText("Physical Time [s]", pad.l + pw / 2, h - 6);

    if (spec.refZero && spec.ymin < 0 && spec.ymax > 0) {
      var zy = pad.t + ((spec.ymax - 0) / spanY) * ph;
      ctx.strokeStyle = isDark ? "#64748b" : "#94a3b8";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.l, zy);
      ctx.lineTo(pad.l + pw, zy);
      ctx.stroke();
    }

    spec.series.forEach(function(s) {
      if (!s.x.length || !s.y.length) return;
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 1.7;
      ctx.setLineDash(s.dash || []);
      ctx.beginPath();
      var started = false;
      for (var i = 0; i < Math.min(s.x.length, s.y.length); i++) {
        var xv = s.x[i], yv = s.y[i];
        if (!isFinite(xv) || !isFinite(yv)) { started = false; continue; }
        var px = pad.l + ((xv - spec.xmin) / spanX) * pw;
        var py = pad.t + ((spec.ymax - yv) / spanY) * ph;
        if (!started) { ctx.moveTo(px, py); started = true; }
        else ctx.lineTo(px, py);
      }
      ctx.stroke();
    });
    ctx.setLineDash([]);
  }

  tabBtns.forEach(function(btn) {
    btn.addEventListener("click", function() {
      activeTab = btn.getAttribute("data-pyr-tab");
      tabBtns.forEach(function(b) { b.classList.toggle("active", b === btn); });
      draw();
    });
  });
  stgBtns.forEach(function(btn) {
    btn.addEventListener("click", function() {
      activeStg = btn.getAttribute("data-pyr-stg");
      stgBtns.forEach(function(b) { b.classList.toggle("active", b === btn); });
      draw();
    });
  });

  if (tip) {
    canvas.addEventListener("mousemove", function(ev) {
      if (!lastPlot || !lastPlot._geom) return;
      var rect = canvas.getBoundingClientRect();
      var mx = ev.clientX - rect.left;
      var g = lastPlot._geom;
      if (mx < g.pad.l || mx > g.pad.l + g.pw) { tip.style.display = "none"; return; }
      var tHover = lastPlot.xmin + ((mx - g.pad.l) / g.pw) * g.spanX;
      var lines = ["<strong>t = " + tHover.toFixed(3) + " s</strong>"];
      lastPlot.series.forEach(function(s) {
        if (!s.x.length) return;
        var best = 0, bestD = Infinity;
        for (var i = 0; i < s.x.length; i++) {
          var d = Math.abs(s.x[i] - tHover);
          if (d < bestD) { bestD = d; best = i; }
        }
        var yv = s.y[best];
        if (isFinite(yv)) {
          lines.push('<span style="color:' + s.color + '">&#9632;</span> ' + s.name + ": <code>" + yv.toFixed(4) + "</code>");
        }
      });
      tip.innerHTML = lines.join("<br>");
      tip.style.display = "block";
      tip.style.left = Math.min(rect.width - 190, Math.max(8, mx + 12)) + "px";
      tip.style.top = "12px";
    });
    canvas.addEventListener("mouseleave", function() { tip.style.display = "none"; });
  }

  window.addEventListener("resize", draw);
  var obs = new MutationObserver(draw);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  draw();
})();
