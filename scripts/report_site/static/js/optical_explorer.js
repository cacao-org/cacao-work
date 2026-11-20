/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

(function() {
  var dataEl = document.getElementById("optical-explorer-data");
  if (!dataEl) return;
  var payload = {};
  try { payload = JSON.parse(dataEl.textContent || "{}"); } catch (e) { return; }
  var canvas = document.getElementById("opt-canvas");
  var tip = document.getElementById("opt-tooltip");
  var ctrlBar = document.getElementById("opt-controls");
  if (!canvas || !canvas.getContext) return;
  var tabBtns = Array.from(document.querySelectorAll("[data-opt-tab]"));
  var activeTab = tabBtns[0] ? tabBtns[0].getAttribute("data-opt-tab") : "wfe";
  var lastPlot = null;

  function drawPlot(spec) {
    lastPlot = spec;
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 760;
    var h = 310;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    var pad = { l: 58, r: 20, t: 24, b: 38 };
    var pw = Math.max(80, w - pad.l - pad.r);
    var ph = Math.max(80, h - pad.t - pad.b);
    var xs = spec.x;
    var xmin = spec.xmin, xmax = spec.xmax;
    var ymin = spec.ymin, ymax = spec.ymax;
    var spanX = Math.max(xmax - xmin, 1e-9);
    var spanY = Math.max(ymax - ymin, 1e-9);

    var isDark = document.documentElement.getAttribute("data-theme") === "dark" ||
      (!document.documentElement.getAttribute("data-theme") && window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
    var gridCol = isDark ? "#334155" : "#e2e8f0";
    var textCol = isDark ? "#cbd5e1" : "#475569";

    ctx.strokeStyle = gridCol;
    ctx.fillStyle = textCol;
    ctx.font = "11px sans-serif";
    for (var gi = 0; gi <= 4; gi++) {
      var gy = pad.t + (ph * gi) / 4;
      ctx.beginPath();
      ctx.moveTo(pad.l, gy);
      ctx.lineTo(pad.l + pw, gy);
      ctx.stroke();
      var yv = ymax - (spanY * gi) / 4;
      var yLbl = spec.isLog ? ("1e" + yv.toFixed(1)) : (yv >= 100 ? yv.toFixed(0) : yv.toFixed(2));
      ctx.fillText(yLbl, 6, gy + 4);
    }
    for (var xi = 0; xi <= 5; xi++) {
      var gx = pad.l + (pw * xi) / 5;
      var xv = xmin + (spanX * xi) / 5;
      ctx.fillText(xv.toFixed(spec.xDec || 1), gx - 10, pad.t + ph + 16);
    }
    ctx.fillText(spec.xLabel || "", pad.l + pw / 2 - 40, h - 5);
    ctx.fillText(spec.title || "", pad.l, 14);

    spec.series.forEach(function(ser) {
      if (!ser.on) return;
      ctx.strokeStyle = ser.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      var started = false;
      for (var i = 0; i < xs.length; i++) {
        if (xs[i] < xmin || xs[i] > xmax) continue;
        var yRaw = ser.y[i];
        if (yRaw === null || yRaw === undefined || !isFinite(yRaw)) continue;
        var px = pad.l + ((xs[i] - xmin) / spanX) * pw;
        var py = pad.t + (1 - (yRaw - ymin) / spanY) * ph;
        if (!started) { ctx.moveTo(px, py); started = true; }
        else ctx.lineTo(px, py);
      }
      ctx.stroke();
    });
    lastPlot.pad = pad;
    lastPlot.pw = pw;
    lastPlot.ph = ph;
  }

  function renderActive() {
    if (activeTab === "wfe" && payload.wf_timeseries) {
      var wf = payload.wf_timeseries;
      var x = wf.t_phys_s || [];
      ctrlBar.innerHTML =
        '<label><input type="checkbox" id="tr-raw" checked> Raw WFE</label> ' +
        '<label><input type="checkbox" id="tr-s1" checked> Stage-1 WFE</label> ' +
        '<label><input type="checkbox" id="tr-fin" checked> Final WFE</label>';
      var series = [
        { name: "Raw [nm]", y: wf.rms_raw_nm || [], color: "#94a3b8", on: true },
        { name: "Stage-1 [nm]", y: wf.rms_stg1_nm || [], color: "#2563eb", on: true },
        { name: "Final [nm]", y: wf.rms_final_nm || [], color: "#059669", on: true }
      ];
      function upd() {
        series[0].on = document.getElementById("tr-raw").checked;
        series[1].on = document.getElementById("tr-s1").checked;
        series[2].on = document.getElementById("tr-fin").checked;
        var allY = [];
        series.forEach(function(s) { if (s.on) allY = allY.concat(s.y); });
        var ymin = allY.length ? Math.min.apply(null, allY) * 0.9 : 0;
        var ymax = allY.length ? Math.max.apply(null, allY) * 1.05 : 100;
        drawPlot({
          title: "Wavefront Error vs Physical Time [nm]",
          xLabel: "Time [s]",
          x: x,
          xmin: x[0] || 0,
          xmax: x[x.length - 1] || 1,
          ymin: ymin,
          ymax: ymax,
          series: series,
          xDec: 2
        });
      }
      ctrlBar.querySelectorAll("input").forEach(function(i) { i.addEventListener("change", upd); });
      upd();
    } else if (activeTab === "strehl" && payload.strehl_timeseries) {
      var sr = payload.strehl_timeseries;
      var x = sr.t_phys_s || [];
      ctrlBar.innerHTML =
        '<label><input type="checkbox" id="sr-v" checked> Vis Final SR [%]</label> ' +
        '<label><input type="checkbox" id="sr-h" checked> H Final SR [%]</label> ' +
        '<label><input type="checkbox" id="sr-vs1" checked> Vis Stg1 SR [%]</label>';
      var series = [
        { name: "Vis Final [%]", y: (sr.vis_final_inst || []).map(function(v) { return v * 100; }),
          color: "#2563eb", on: true },
        { name: "H Final [%]", y: (sr.nir_final_inst || []).map(function(v) { return v * 100; }),
          color: "#059669", on: true },
        { name: "Vis Stg1 [%]", y: (sr.vis_stg1_inst || []).map(function(v) { return v * 100; }),
          color: "#d97706", on: true }
      ];
      function updS() {
        series[0].on = document.getElementById("sr-v").checked;
        series[1].on = document.getElementById("sr-h").checked;
        series[2].on = document.getElementById("sr-vs1").checked;
        drawPlot({
          title: "Instantaneous Optical Strehl Ratio [%]",
          xLabel: "Time [s]",
          x: x,
          xmin: x[0] || 0,
          xmax: x[x.length - 1] || 1,
          ymin: 0,
          ymax: 102,
          series: series,
          xDec: 2
        });
      }
      ctrlBar.querySelectorAll("input").forEach(function(i) {
        i.addEventListener("change", updS);
      });
      updS();
    } else if (activeTab === "modal" && payload.modal_stages && payload.modal_stages.length) {
      var opts = payload.modal_stages.map(function(st, i) {
        return '<option value="' + i + '">' + st.label + " (" + st.n_modes + " modes)</option>";
      }).join("");
      ctrlBar.innerHTML =
        'Stage: <select class="select-input" id="m-stg-sel">' + opts + "</select>";
      var sel = document.getElementById("m-stg-sel");
      function updM() {
        var st = payload.modal_stages[parseInt(sel.value, 10) || 0];
        var sList = [{ name: "Modal Gain", y: st.mgain || [], color: "#2563eb", on: true }];
        if (st.rel_grad) {
          sList.push({ name: "Rel. Grad", y: st.rel_grad, color: "#059669", on: true });
        }
        drawPlot({
          title: st.label + " Modal Gain & Normalized Singular Values",
          xLabel: "Mode Index",
          x: st.mode_idx || [],
          xmin: 0,
          xmax: st.n_modes || 1,
          ymin: 0,
          ymax: 1.05,
          series: sList,
          xDec: 0
        });
      }
      sel.addEventListener("change", updM);
      updM();
    } else if (activeTab === "coro" && payload.contrast_table) {
      ctrlBar.innerHTML = '<span class="muted">Log10 coronagraphic contrast vs separation</span>';
      var ct = payload.contrast_table;
      var x = ct.map(function(r) { return r.sep_ld; });
      function lg(v) { return Math.log10(Math.max(v || 1e-8, 1e-8)); }
      var sList = [
        { name: "CL Planet", y: ct.map(function(r) { return lg(r.cl_planet); }), color: "#2563eb", on: true },
        { name: "CL 5-sig", y: ct.map(function(r) { return lg(r.cl_5sig); }), color: "#dc2626", on: true },
        { name: "DL Raw", y: ct.map(function(r) { return lg(r.dl_raw); }), color: "#059669", on: true }
      ];
      drawPlot({
        title: "H-Band Coronagraphic Contrast Curve (log10)",
        xLabel: "Separation [lambda/D]",
        x: x,
        xmin: x[0] || 0,
        xmax: x[x.length - 1] || 20,
        ymin: -6.5,
        ymax: -2.0,
        series: sList,
        xDec: 0,
        isLog: true
      });
    }
  }

  tabBtns.forEach(function(btn) {
    btn.addEventListener("click", function() {
      activeTab = btn.getAttribute("data-opt-tab");
      tabBtns.forEach(function(b) { b.classList.toggle("active", b === btn); });
      renderActive();
    });
  });

  if (tip) {
    canvas.addEventListener("mousemove", function(ev) {
      if (!lastPlot || !lastPlot.x || !lastPlot.x.length) return;
      var rect = canvas.getBoundingClientRect();
      var mx = ev.clientX - rect.left;
      var pad = lastPlot.pad;
      if (mx < pad.l || mx > pad.l + lastPlot.pw) { tip.style.display = "none"; return; }
      var frac = (mx - pad.l) / lastPlot.pw;
      var targetX = lastPlot.xmin + frac * (lastPlot.xmax - lastPlot.xmin);
      var best = 0;
      var bestD = Infinity;
      for (var i = 0; i < lastPlot.x.length; i++) {
        var d = Math.abs(lastPlot.x[i] - targetX);
        if (d < bestD) { bestD = d; best = i; }
      }
      var lines = ["x = " + lastPlot.x[best].toFixed(lastPlot.xDec || 2)];
      lastPlot.series.forEach(function(s) {
        if (!s.on) return;
        var val = s.y[best];
        if (val !== undefined && isFinite(val)) {
          var vFmt = lastPlot.isLog ? Math.pow(10, val).toExponential(2) : val.toFixed(2);
          lines.push(s.name + ": " + vFmt);
        }
      });
      tip.innerHTML = lines.join("<br>");
      tip.style.display = "block";
      tip.style.left = Math.min(rect.width - 150, mx + 12) + "px";
      tip.style.top = "12px";
    });
    canvas.addEventListener("mouseleave", function() { tip.style.display = "none"; });
  }

  window.addEventListener("resize", renderActive);
  renderActive();
})();
