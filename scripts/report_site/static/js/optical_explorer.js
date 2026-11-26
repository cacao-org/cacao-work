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
  var legendEl = document.getElementById("opt-legend");
  if (!canvas || !canvas.getContext) return;
  var tabBtns = Array.from(document.querySelectorAll("[data-opt-tab]"));
  var activeTab = tabBtns[0] ? tabBtns[0].getAttribute("data-opt-tab") : "wfe";
  var lastPlot = null;

  function meanOf(arr) {
    if (!arr || !arr.length) return NaN;
    var s = 0, n = 0;
    for (var i = 0; i < arr.length; i++) {
      if (isFinite(arr[i])) { s += arr[i]; n++; }
    }
    return n ? (s / n) : NaN;
  }

  function renderLegend(series, noteHtml) {
    if (!legendEl) return;
    var items = [];
    series.forEach(function(s) {
      if (!s.on) return;
      var style = s.dashStyle || "solid";
      var stat = s.statLabel ? (' <span class="muted">(' + s.statLabel + ")</span>") : "";
      items.push(
        '<span class="opt-legend-item">' +
          '<span class="opt-legend-swatch" style="border-top-style:' + style + ";border-top-color:" + s.color + ';"></span>' +
          s.name + stat +
        "</span>"
      );
    });
    if (!items.length && !noteHtml) {
      legendEl.innerHTML = "";
      return;
    }
    legendEl.innerHTML =
      '<div class="opt-legend-items">' + items.join("") + "</div>" +
      (noteHtml ? ('<div class="opt-legend-note">' + noteHtml + "</div>") : "");
  }

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
    ctx.setLineDash([]);
    for (var gi = 0; gi <= 4; gi++) {
      var gy = pad.t + (ph * gi) / 4;
      ctx.beginPath();
      ctx.moveTo(pad.l, gy);
      ctx.lineTo(pad.l + pw, gy);
      ctx.stroke();
      var yv = ymax - (spanY * gi) / 4;
      var yLbl;
      if (spec.isLogNm) {
        var lin = Math.pow(10, yv);
        yLbl = lin >= 100 ? lin.toFixed(0) : (lin >= 10 ? lin.toFixed(1) : lin.toFixed(2));
      } else if (spec.isLog) {
        yLbl = "1e" + yv.toFixed(1);
      } else {
        yLbl = yv >= 100 ? yv.toFixed(0) : yv.toFixed(2);
      }
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
      ctx.lineWidth = ser.width || 2;
      ctx.setLineDash(ser.dash || []);
      ctx.beginPath();
      var started = false;
      for (var i = 0; i < xs.length; i++) {
        if (xs[i] < xmin || xs[i] > xmax) continue;
        var yRaw = ser.y[i];
        if (yRaw === null || yRaw === undefined || !isFinite(yRaw)) continue;
        var yPlot = spec.isLogNm ? Math.log10(Math.max(yRaw, 1.0)) : yRaw;
        var px = pad.l + ((xs[i] - xmin) / spanX) * pw;
        var py = pad.t + (1 - (yPlot - ymin) / spanY) * ph;
        if (!started) { ctx.moveTo(px, py); started = true; }
        else ctx.lineTo(px, py);
      }
      ctx.stroke();
    });
    ctx.setLineDash([]);
    lastPlot.pad = pad;
    lastPlot.pw = pw;
    lastPlot.ph = ph;
  }

  function renderActive() {
    if (legendEl) legendEl.innerHTML = "";
    if (activeTab === "wfe" && payload.wf_timeseries) {
      var wf = payload.wf_timeseries;
      var x = wf.t_phys_s || [];
      var hasCtrl = !!(wf.rms_stg1_in_nm && wf.rms_stg1_out_nm && wf.rms_stg1_in_nm.length === x.length);
      var meta = wf.ctrl_meta || {};
      var m1Tag = meta.stg1_modes ? (" " + meta.stg1_modes + "m") : "";
      var mfTag = meta.final_modes ? (" " + meta.final_modes + "m") : "";

      var ctrlHtml =
        '<label><input type="checkbox" id="tr-raw"' + (hasCtrl ? "" : " checked") + '> Raw WFE</label> ' +
        '<label><input type="checkbox" id="tr-s1" checked> Stage-1 WFE</label> ' +
        '<label><input type="checkbox" id="tr-fin" checked> Final WFE</label>';
      if (hasCtrl) {
        ctrlHtml +=
          '<span class="opt-ctrl-sep"></span>' +
          '<label title="Total pupil RMS WFE (solid)"><input type="checkbox" id="tr-tot" checked> Total</label> ' +
          '<label title="Component within controlled AO modes (dashed)"><input type="checkbox" id="tr-in" checked> Within Ctrl Modes</label> ' +
          '<label title="Component outside controlled AO modes / fitting error (dotted)"><input type="checkbox" id="tr-out" checked> Outside Ctrl Modes</label>';
      }
      ctrlHtml +=
        '<span class="opt-ctrl-sep"></span>' +
        '<label title="Logarithmic Y-axis (useful when comparing Raw with closed-loop)"><input type="checkbox" id="tr-logy"> Log Y</label>';
      ctrlBar.innerHTML = ctrlHtml;

      function mkStat(arr, totArr) {
        var m = meanOf(arr);
        if (!isFinite(m)) return "";
        var s = m >= 100 ? (m.toFixed(0) + " nm") : (m.toFixed(1) + " nm");
        if (totArr && totArr.length === arr.length) {
          var mt = meanOf(totArr);
          if (isFinite(mt) && mt > 1e-6) {
            var pct = Math.min(100, Math.max(0, (m * m) / (mt * mt) * 100));
            s += ", " + pct.toFixed(0) + "% var";
          }
        }
        return s;
      }

      var series = [
        { plane: "raw", comp: "tot", name: "Raw Total", y: wf.rms_raw_nm || [], color: "#94a3b8",
          dash: [], dashStyle: "solid", width: 2.0, statLabel: mkStat(wf.rms_raw_nm), on: !hasCtrl }
      ];
      if (hasCtrl && wf.rms_raw_in_nm && wf.rms_raw_out_nm) {
        series.push(
          { plane: "raw", comp: "in", name: "Raw Within Ctrl" + (mfTag ? " (" + mfTag.trim() + ")" : ""),
            y: wf.rms_raw_in_nm, totRef: wf.rms_raw_nm, color: "#cbd5e1",
            dash: [7, 4], dashStyle: "dashed", width: 1.7,
            statLabel: mkStat(wf.rms_raw_in_nm, wf.rms_raw_nm), on: false },
          { plane: "raw", comp: "out", name: "Raw Outside Ctrl",
            y: wf.rms_raw_out_nm, totRef: wf.rms_raw_nm, color: "#64748b",
            dash: [2, 3], dashStyle: "dotted", width: 1.8,
            statLabel: mkStat(wf.rms_raw_out_nm, wf.rms_raw_nm), on: false }
        );
      }
      series.push(
        { plane: "s1", comp: "tot", name: "Stage-1 Total", y: wf.rms_stg1_nm || [], color: "#2563eb",
          dash: [], dashStyle: "solid", width: 2.2, statLabel: mkStat(wf.rms_stg1_nm), on: true }
      );
      if (hasCtrl && wf.rms_stg1_in_nm && wf.rms_stg1_out_nm) {
        series.push(
          { plane: "s1", comp: "in", name: "Stage-1 Within Ctrl" + (m1Tag ? " (" + m1Tag.trim() + ")" : ""),
            y: wf.rms_stg1_in_nm, totRef: wf.rms_stg1_nm, color: "#38bdf8",
            dash: [7, 4], dashStyle: "dashed", width: 1.9,
            statLabel: mkStat(wf.rms_stg1_in_nm, wf.rms_stg1_nm), on: true },
          { plane: "s1", comp: "out", name: "Stage-1 Outside Ctrl",
            y: wf.rms_stg1_out_nm, totRef: wf.rms_stg1_nm, color: "#a855f7",
            dash: [2, 3], dashStyle: "dotted", width: 2.0,
            statLabel: mkStat(wf.rms_stg1_out_nm, wf.rms_stg1_nm), on: true }
        );
      }
      series.push(
        { plane: "fin", comp: "tot", name: "Final Total", y: wf.rms_final_nm || [], color: "#059669",
          dash: [], dashStyle: "solid", width: 2.2, statLabel: mkStat(wf.rms_final_nm), on: true }
      );
      if (hasCtrl && wf.rms_final_in_nm && wf.rms_final_out_nm) {
        series.push(
          { plane: "fin", comp: "in", name: "Final Within Ctrl" + (mfTag ? " (" + mfTag.trim() + ")" : ""),
            y: wf.rms_final_in_nm, totRef: wf.rms_final_nm, color: "#34d399",
            dash: [7, 4], dashStyle: "dashed", width: 1.9,
            statLabel: mkStat(wf.rms_final_in_nm, wf.rms_final_nm), on: true },
          { plane: "fin", comp: "out", name: "Final Outside Ctrl",
            y: wf.rms_final_out_nm, totRef: wf.rms_final_nm, color: "#f59e0b",
            dash: [2, 3], dashStyle: "dotted", width: 2.0,
            statLabel: mkStat(wf.rms_final_out_nm, wf.rms_final_nm), on: true }
        );
      }

      var noteHtml = "";
      if (hasCtrl) {
        var srcDesc = meta.source === "exact_per_frame"
          ? "exact per-frame pupil projection"
          : "orthogonal CMmodesDM projection (5-snapshot calibrated)";
        noteHtml = "&sigma;&sup2;<sub>tot</sub> = &sigma;&sup2;<sub>in</sub> + &sigma;&sup2;<sub>out</sub> &middot; " + srcDesc;
      }

      function upd() {
        var pOn = {
          raw: document.getElementById("tr-raw").checked,
          s1: document.getElementById("tr-s1").checked,
          fin: document.getElementById("tr-fin").checked
        };
        var cOn = {
          tot: hasCtrl ? document.getElementById("tr-tot").checked : true,
          in: hasCtrl ? document.getElementById("tr-in").checked : false,
          out: hasCtrl ? document.getElementById("tr-out").checked : false
        };
        var logY = document.getElementById("tr-logy").checked;
        var allY = [];
        series.forEach(function(s) {
          s.on = !!(pOn[s.plane] && cOn[s.comp] && s.y && s.y.length);
          if (s.on) {
            for (var i = 0; i < s.y.length; i++) {
              if (isFinite(s.y[i])) allY.push(s.y[i]);
            }
          }
        });
        var ymin, ymax;
        if (logY) {
          var minP = allY.length ? Math.max(1.0, Math.min.apply(null, allY)) : 10.0;
          var maxP = allY.length ? Math.max(minP * 2.0, Math.max.apply(null, allY)) : 1000.0;
          ymin = Math.log10(minP * 0.85);
          ymax = Math.log10(maxP * 1.15);
        } else {
          ymin = allY.length ? Math.max(0, Math.min.apply(null, allY) * 0.88) : 0;
          ymax = allY.length ? Math.max.apply(null, allY) * 1.08 : 100;
          if (ymax <= ymin + 1e-6) ymax = ymin + 10;
        }
        drawPlot({
          title: "Wavefront Error vs Physical Time [nm]" + (hasCtrl ? " — Total / Within vs Outside Control Modes" : ""),
          xLabel: "Time [s]",
          x: x,
          xmin: x[0] || 0,
          xmax: x[x.length - 1] || 1,
          ymin: ymin,
          ymax: ymax,
          series: series,
          xDec: 2,
          isLogNm: logY
        });
        renderLegend(series, noteHtml);
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
          var extra = "";
          if (s.totRef && isFinite(s.totRef[best]) && s.totRef[best] > 1e-6) {
            var pct = Math.min(100, Math.max(0, (val * val) / (s.totRef[best] * s.totRef[best]) * 100));
            extra = " (" + pct.toFixed(0) + "% var)";
          }
          var dot = '<span style="color:' + s.color + ';">&#9632;</span> ';
          lines.push(dot + s.name + ": " + vFmt + extra);
        }
      });
      tip.innerHTML = lines.join("<br>");
      tip.style.display = "block";
      tip.style.left = Math.min(rect.width - 210, mx + 12) + "px";
      tip.style.top = "12px";
    });
    canvas.addEventListener("mouseleave", function() { tip.style.display = "none"; });
  }

  window.addEventListener("resize", renderActive);
  renderActive();
})();
