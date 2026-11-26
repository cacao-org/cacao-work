/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

(function() {
  var data = window.CACAO_EOF_PF_DATA;
  var panel = document.getElementById("eof-pf-panel");
  if (!data || !panel || !Array.isArray(data.stages) || !data.stages.length) return;

  var visGrid = document.getElementById("eof-pf-vis-grid");
  var mainCanvas = document.getElementById("eof-pf-main-canvas");
  var sliceCanvas = document.getElementById("eof-pf-slice-canvas");
  var kernCanvas = document.getElementById("eof-pf-kernel-canvas");
  var tip = document.getElementById("eof-pf-tooltip");
  var sliceTip = document.getElementById("eof-pf-slice-tooltip");
  var stageBtnsWrap = document.getElementById("eof-pf-stage-btns");
  var blkSel = document.getElementById("eof-pf-block-sel");
  var viewBtns = Array.from(document.querySelectorAll("[data-pf-view]"));
  var lagSlider = document.getElementById("eof-pf-lag-slider");
  var lagPrevBtn = document.getElementById("eof-pf-lag-prev");
  var lagNextBtn = document.getElementById("eof-pf-lag-next");
  var lagReadout = document.getElementById("eof-pf-lag-readout");
  var playBtn = document.getElementById("eof-pf-play-btn");
  var zoomSel = document.getElementById("eof-pf-zoom-sel");
  var cmapSel = document.getElementById("eof-pf-cmap-sel");
  var hideDiagCb = document.getElementById("eof-pf-hide-diag");
  var threshSlider = document.getElementById("eof-pf-thresh-slider");
  var threshValEl = document.getElementById("eof-pf-thresh-val");
  var resetBtn = document.getElementById("eof-pf-reset-btn");
  var slicePillEl = document.getElementById("eof-pf-slice-pill");
  var sliceTitleEl = document.getElementById("eof-pf-slice-title");
  var sliceMetaEl = document.getElementById("eof-pf-slice-meta");
  var sliceAutoCb = document.getElementById("eof-pf-slice-autoscale");
  var pairTitleEl = document.getElementById("eof-pf-pair-title");
  var statsEl = document.getElementById("eof-pf-stats");
  var pairsEl = document.getElementById("eof-pf-pairs");
  var hintEl = document.getElementById("eof-pf-hint");
  if (!mainCanvas || !mainCanvas.getContext) return;

  var state = {
    stgIdx: 0,
    blkIdx: 0,
    view: "cube3d",
    lag: 0,
    zoomN: 0,
    cmap: "rdbu",
    hideDiag: false,
    sliceAutoScale: sliceAutoCb ? Boolean(sliceAutoCb.checked) : true,
    threshStep: threshSlider ? (parseInt(threshSlider.value, 10) || 6) : 6,
    azim: -53 * Math.PI / 180,
    elev: 23 * Math.PI / 180,
    selOut: 0,
    selIn: 0,
    playing: false,
    playTimer: null,
    drag: null,
    last2D: null,
    lastSlice2D: null,
    lastKern: null,
    cubeCache: null
  };

  function isDark() {
    var attr = document.documentElement.getAttribute("data-theme");
    if (attr === "dark") return true;
    if (attr === "light") return false;
    return Boolean(window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  function fmtScaleVal(v) {
    var av = Math.abs(v);
    if (av === 0) return "0";
    if (av >= 0.1) return v.toFixed(2);
    if (av >= 0.01) return v.toFixed(3);
    if (av >= 0.001) return v.toFixed(4);
    return v.toExponential(1);
  }

  function decodeBlock(st, blk) {
    if (blk._tensor) return blk;
    var bin = atob(blk.data_b64 || "");
    var n = bin.length;
    var arr = new Float32Array(n);
    var vmax = blk.vmax || 1.0;
    var histAll = new Int32Array(128);
    var histOff = new Int32Array(128);
    var b = blk.b;
    var P = st.order;
    for (var idx = 0; idx < n; idx++) {
      var u = bin.charCodeAt(idx);
      var q = u > 127 ? u - 256 : u;
      var aq = Math.min(127, Math.abs(q));
      histAll[aq] += 1;
      var oi0 = Math.floor(idx / (P * b));
      var ij0 = idx % b;
      if (oi0 !== ij0) histOff[aq] += 1;
      if (q !== 0) {
        var f = q / 127.0;
        arr[idx] = (q > 0 ? 1 : -1) * f * f * vmax;
      }
    }
    function pct99FromHist(hist, total) {
      var target = Math.max(1, Math.floor(total * 0.01));
      var acc = 0;
      for (var qv = 127; qv >= 0; qv--) {
        acc += hist[qv];
        if (acc >= target) {
          var fr = qv / 127.0;
          return Math.max(fr * fr * vmax, 1e-4);
        }
      }
      return Math.max(vmax * 0.05, 1e-4);
    }
    blk._tensor = arr;
    blk._v3dRef = pct99FromHist(histAll, n);
    blk._v3dOffRef = pct99FromHist(histOff, Math.max(1, n - b * P));
    var l2 = new Float32Array(b * b);
    var l2max = 0;
    var l2offMax = 0;
    for (var oi = 0; oi < b; oi++) {
      for (var ij = 0; ij < b; ij++) {
        var s2 = 0;
        for (var kk = 0; kk < P; kk++) {
          var v = arr[(oi * P + kk) * b + ij];
          s2 += v * v;
        }
        var nrm = Math.sqrt(s2);
        l2[oi * b + ij] = nrm;
        if (nrm > l2max) l2max = nrm;
        if (oi !== ij && nrm > l2offMax) l2offMax = nrm;
      }
    }
    blk._l2 = l2;
    blk._l2max = Math.max(l2max, 1e-4);
    blk._l2offMax = Math.max(l2offMax, 1e-4);
    return blk;
  }

  function interpStops(stops, t) {
    var x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
    var i0 = Math.floor(x);
    var i1 = Math.min(stops.length - 1, i0 + 1);
    var f = x - i0;
    return [
      Math.round(stops[i0][0] + (stops[i1][0] - stops[i0][0]) * f),
      Math.round(stops[i0][1] + (stops[i1][1] - stops[i0][1]) * f),
      Math.round(stops[i0][2] + (stops[i1][2] - stops[i0][2]) * f)
    ];
  }

  var RDBU_LIGHT_POS = [[248, 250, 252], [248, 113, 113], [202, 0, 32], [103, 0, 31]];
  var RDBU_LIGHT_NEG = [[248, 250, 252], [96, 165, 250], [5, 113, 176], [5, 48, 97]];
  var RDBU_DARK_POS = [[18, 25, 42], [185, 28, 28], [248, 113, 113], [254, 226, 202]];
  var RDBU_DARK_NEG = [[18, 25, 42], [29, 78, 216], [56, 189, 248], [224, 242, 254]];
  var RDBU_3D_DARK_POS = [[220, 38, 38], [244, 63, 94], [255, 138, 128]];
  var RDBU_3D_DARK_NEG = [[37, 99, 235], [14, 165, 233], [125, 211, 252]];
  var RDBU_3D_LIGHT_POS = [[239, 68, 68], [185, 28, 28], [103, 0, 31]];
  var RDBU_3D_LIGHT_NEG = [[59, 130, 246], [29, 78, 216], [15, 42, 97]];
  var MAGMA = [
    [6, 4, 16], [59, 15, 112], [140, 41, 129],
    [222, 73, 104], [254, 159, 109], [252, 253, 191]
  ];
  var MAGMA_3D = [
    [168, 48, 128], [234, 88, 108], [254, 168, 102], [252, 253, 191]
  ];

  function colorSignedSymLog(v, vmax, dark) {
    var safeMax = Math.max(vmax, 1e-5);
    var lt = Math.min(0.008, Math.max(safeMax * 0.05, 1e-5));
    var denom = Math.log10(1.0 + safeMax / lt);
    var t = Math.log10(1.0 + Math.abs(v) / lt) / Math.max(denom, 1e-6);
    if (dark) {
      return interpStops(v >= 0 ? RDBU_DARK_POS : RDBU_DARK_NEG, t);
    }
    return interpStops(v >= 0 ? RDBU_LIGHT_POS : RDBU_LIGHT_NEG, t);
  }

  function color3DSigned(v, refMax, dark) {
    var safeMax = Math.max(refMax, 1e-5);
    var lt = Math.max(safeMax * 0.15, 1e-5);
    var denom = Math.log10(1.0 + safeMax / lt);
    var t = Math.log10(1.0 + Math.abs(v) / lt) / Math.max(denom, 1e-6);
    if (dark) {
      return interpStops(v >= 0 ? RDBU_3D_DARK_POS : RDBU_3D_DARK_NEG, t);
    }
    return interpStops(v >= 0 ? RDBU_3D_LIGHT_POS : RDBU_3D_LIGHT_NEG, t);
  }

  function colorLogMagma(val, vmin, vmax, for3D) {
    var lo = Math.log10(Math.max(vmin, 1e-6));
    var hi = Math.log10(Math.max(vmax, vmin * 1.5));
    var t = (Math.log10(Math.max(val, vmin)) - lo) / Math.max(hi - lo, 1e-6);
    return interpStops(for3D ? MAGMA_3D : MAGMA, t);
  }

  function get3DScaleAndCut(blk) {
    var ref = state.hideDiag ? blk._v3dOffRef : blk._v3dRef;
    ref = Math.max(ref || blk.vmax || 0.05, 1e-4);
    var thr = (state.threshStep * 0.06) * ref;
    return { ref: ref, thr: thr };
  }

  function getSliceScale(blk, slStats) {
    if (state.sliceAutoScale) {
      var vmax = Math.max(slStats.absMax, 1e-4);
      var vmin = Math.min(vmax * 0.4, Math.max(vmax * 5e-3, 1e-5));
      return { vmax: vmax, vmin: vmin };
    }
    return { vmax: Math.max(blk.vmax || 0.1, 0.05), vmin: 2e-3 };
  }

  function curStage() {
    return data.stages[state.stgIdx] || data.stages[0];
  }

  function curBlock(st) {
    var blk = st.blocks[state.blkIdx] || st.blocks[0];
    return decodeBlock(st, blk);
  }

  function dispDim(blk) {
    if (state.zoomN > 0 && state.zoomN < blk.b) return state.zoomN;
    return blk.b;
  }

  function pickDefaultPair(st, blk) {
    if (blk.top_pairs && blk.top_pairs.length) {
      state.selOut = blk.top_pairs[0][0] - blk.s0;
      state.selIn = blk.top_pairs[0][1] - blk.s0;
    } else {
      state.selOut = 0;
      state.selIn = blk.b > 1 ? 1 : 0;
    }
    var n = dispDim(blk);
    if (state.selOut >= n || state.selIn >= n) {
      state.selOut = Math.min(state.selOut, n - 1);
      state.selIn = Math.min(state.selIn, n - 1);
    }
  }

  function computeSliceStats(st, blk, lagIdx, n) {
    var P = st.order;
    var b = blk.b;
    var absMax = 0;
    var totSq = 0;
    var offSq = 0;
    for (var oi = 0; oi < n; oi++) {
      var rowOff = (oi * P + lagIdx) * b;
      for (var ij = 0; ij < n; ij++) {
        var v = (state.hideDiag && oi === ij) ? 0 : blk._tensor[rowOff + ij];
        var av = Math.abs(v);
        if (av > absMax) absMax = av;
        var v2 = v * v;
        totSq += v2;
        if (oi !== ij) offSq += v2;
      }
    }
    var offPct = totSq > 1e-30 ? (offSq / totSq) * 100.0 : 0.0;
    return {
      absMax: absMax,
      rms: Math.sqrt(totSq / Math.max(n * n, 1)),
      offPct: offPct
    };
  }

  function makeSliceCanvas(st, blk, lagIdx, n, for3D, customVmax, customVmin, dark) {
    var off = document.createElement("canvas");
    off.width = n;
    off.height = n;
    var octx = off.getContext("2d");
    var img = octx.createImageData(n, n);
    var px = img.data;
    var P = st.order;
    var b = blk.b;
    var isDarkMode = dark !== undefined ? dark : isDark();
    var sc3d = for3D ? get3DScaleAndCut(blk) : null;
    var vmax = for3D
      ? sc3d.ref
      : (customVmax !== undefined
        ? Math.max(customVmax, 1e-5)
        : Math.max(blk.vmax || 0.1, 0.05));
    var vmin = for3D
      ? Math.max(sc3d.thr, vmax * 0.05, 1e-5)
      : (customVmin !== undefined ? Math.max(customVmin, 1e-6) : 2e-3);
    var thr = for3D ? sc3d.thr : 0;
    for (var oi = 0; oi < n; oi++) {
      var py = n - 1 - oi;
      var rowOff = (oi * P + lagIdx) * b;
      for (var ij = 0; ij < n; ij++) {
        var v = (state.hideDiag && oi === ij) ? 0 : blk._tensor[rowOff + ij];
        var a = 255;
        var rgb;
        if (for3D) {
          var av = Math.abs(v);
          if (av <= 0 || av < thr) {
            continue;
          }
          rgb = state.cmap === "magma"
            ? colorLogMagma(av, vmin, vmax, true)
            : color3DSigned(v, vmax, isDarkMode);
          var frac = Math.min(1, (av - thr) / Math.max(vmax - thr, 1e-5));
          a = Math.round(105 + 145 * Math.sqrt(frac));
        } else {
          rgb = state.cmap === "magma"
            ? colorLogMagma(Math.abs(v), vmin, vmax, false)
            : colorSignedSymLog(v, vmax, isDarkMode);
        }
        var p = (py * n + ij) * 4;
        px[p] = rgb[0];
        px[p + 1] = rgb[1];
        px[p + 2] = rgb[2];
        px[p + 3] = a;
      }
    }
    octx.putImageData(img, 0, 0);
    return off;
  }

  function getCachedCubeSlices(st, blk, n, dark) {
    var key = state.stgIdx + ":" + state.blkIdx + ":" + n + ":" + state.cmap + ":" +
      (state.hideDiag ? 1 : 0) + ":" + state.threshStep + ":" + (dark ? 1 : 0);
    if (state.cubeCache && state.cubeCache.key === key) {
      return state.cubeCache.slices;
    }
    var P = st.order;
    var slices = [];
    for (var kk = 0; kk < P; kk++) {
      slices.push(makeSliceCanvas(st, blk, kk, n, true, undefined, undefined, dark));
    }
    state.cubeCache = { key: key, slices: slices };
    return slices;
  }

  function makeL2Canvas(blk, n) {
    var off = document.createElement("canvas");
    off.width = n;
    off.height = n;
    var octx = off.getContext("2d");
    var img = octx.createImageData(n, n);
    var px = img.data;
    var vmax = state.hideDiag ? blk._l2offMax : blk._l2max;
    for (var oi = 0; oi < n; oi++) {
      var py = n - 1 - oi;
      for (var ij = 0; ij < n; ij++) {
        var v = (state.hideDiag && oi === ij) ? 0 : blk._l2[oi * blk.b + ij];
        var rgb = colorLogMagma(v, 2e-3, vmax);
        var p = (py * n + ij) * 4;
        px[p] = rgb[0];
        px[p + 1] = rgb[1];
        px[p + 2] = rgb[2];
        px[p + 3] = 255;
      }
    }
    octx.putImageData(img, 0, 0);
    return off;
  }

  function makeModeLagCanvas(st, blk, n, inJ, dark) {
    var P = st.order;
    var off = document.createElement("canvas");
    off.width = P;
    off.height = n;
    var octx = off.getContext("2d");
    var img = octx.createImageData(P, n);
    var px = img.data;
    var vmax = Math.max(blk.vmax || 0.1, 0.05);
    var isDarkMode = dark !== undefined ? dark : isDark();
    for (var oi = 0; oi < n; oi++) {
      var py = n - 1 - oi;
      for (var kk = 0; kk < P; kk++) {
        var v = (state.hideDiag && oi === inJ)
          ? 0
          : blk._tensor[(oi * P + kk) * blk.b + inJ];
        var rgb = state.cmap === "magma"
          ? colorLogMagma(Math.abs(v), 2e-3, vmax, false)
          : colorSignedSymLog(v, vmax, isDarkMode);
        var p = (py * P + kk) * 4;
        px[p] = rgb[0];
        px[p + 1] = rgb[1];
        px[p + 2] = rgb[2];
        px[p + 3] = 255;
      }
    }
    octx.putImageData(img, 0, 0);
    return off;
  }

  function project3D(nx, ny, nz, cx, cy, scale) {
    var ca = Math.cos(state.azim);
    var sa = Math.sin(state.azim);
    var ce = Math.cos(state.elev);
    var se = Math.sin(state.elev);
    var rx = nx * ca - ny * sa;
    var ry = nx * sa + ny * ca;
    var sy = ry * se + nz * ce;
    return {
      x: cx + rx * scale,
      y: cy - sy * scale,
      depth: -ry * ce + nz * se
    };
  }

  function drawColorbar(ctx, x, y, w, h, vmin, vmax, isSigned, label, textCol, borderCol, dark) {
    var isDarkMode = dark !== undefined ? dark : isDark();
    for (var row = 0; row < h; row++) {
      var frac = 1.0 - row / Math.max(h - 1, 1);
      var rgb;
      if (isSigned) {
        var v = (frac * 2 - 1) * vmax;
        rgb = colorSignedSymLog(v, vmax, isDarkMode);
      } else {
        var lv = Math.log10(vmin) + frac * (Math.log10(vmax) - Math.log10(vmin));
        rgb = colorLogMagma(Math.pow(10, lv), vmin, vmax, false);
      }
      ctx.fillStyle = "rgb(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + ")";
      ctx.fillRect(x, y + row, w, 1);
    }
    ctx.strokeStyle = borderCol;
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = textCol;
    ctx.font = "11px sans-serif";
    ctx.textAlign = "left";
    if (isSigned) {
      ctx.fillText("+" + fmtScaleVal(vmax), x + w + 5, y + 9);
      ctx.fillText("0", x + w + 5, y + h / 2 + 4);
      ctx.fillText("-" + fmtScaleVal(vmax), x + w + 5, y + h);
    } else {
      ctx.fillText(fmtScaleVal(vmax), x + w + 5, y + 9);
      ctx.fillText(fmtScaleVal(Math.sqrt(vmin * vmax)), x + w + 5, y + h / 2 + 4);
      ctx.fillText(vmin < 1e-3 ? vmin.toExponential(0) : fmtScaleVal(vmin), x + w + 5, y + h);
    }
    ctx.save();
    ctx.translate(x + w + 50, y + h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText(label, 0, 0);
    ctx.restore();
  }

  function renderCube3D(ctx, w, h, st, blk, n, activeSliceCanvas) {
    var dark = isDark();
    var textCol = dark ? "#cbd5e1" : "#334155";
    var gridCol = dark ? "rgba(148, 163, 184, 0.18)" : "rgba(100, 116, 139, 0.22)";
    var wallCol = dark ? "rgba(24, 34, 52, 0.62)" : "rgba(241, 245, 249, 0.72)";
    var borderCol = dark ? "#475569" : "#94a3b8";

    var cx = (w - 64) * 0.50;
    var cy = h * 0.52;
    var scale = Math.min(w - 115, h - 62) * 0.84;
    var P = st.order;

    var ca = Math.cos(state.azim);
    var sa = Math.sin(state.azim);
    var ce = Math.cos(state.elev);
    var se = Math.sin(state.elev);
    var vx = -sa * ce;
    var vy = -ca * ce;
    var vz = se;
    var bxWall = vx >= 0 ? -0.5 : 0.5;
    var byWall = vy >= 0 ? -0.5 : 0.5;
    var bzWall = vz >= 0 ? -0.5 : 0.5;

    function poly(pts, fill, stroke) {
      ctx.beginPath();
      pts.forEach(function(p, idx) {
        var pr = project3D(p[0], p[1], p[2], cx, cy, scale);
        if (idx === 0) ctx.moveTo(pr.x, pr.y);
        else ctx.lineTo(pr.x, pr.y);
      });
      ctx.closePath();
      if (fill) { ctx.fillStyle = fill; ctx.fill(); }
      if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
    }

    poly([[bxWall, -0.5, -0.5], [bxWall, 0.5, -0.5],
          [bxWall, 0.5, 0.5], [bxWall, -0.5, 0.5]], wallCol, borderCol);
    poly([[-0.5, byWall, -0.5], [0.5, byWall, -0.5],
          [0.5, byWall, 0.5], [-0.5, byWall, 0.5]], wallCol, borderCol);
    poly([[-0.5, -0.5, bzWall], [0.5, -0.5, bzWall],
          [0.5, 0.5, bzWall], [-0.5, 0.5, bzWall]], wallCol, borderCol);

    ctx.strokeStyle = gridCol;
    ctx.lineWidth = 0.8;
    for (var gi = 1; gi < 4; gi++) {
      var gv = -0.5 + gi * 0.25;
      var p1 = project3D(bxWall, gv, -0.5, cx, cy, scale);
      var p2 = project3D(bxWall, gv, 0.5, cx, cy, scale);
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
      p1 = project3D(gv, byWall, -0.5, cx, cy, scale);
      p2 = project3D(gv, byWall, 0.5, cx, cy, scale);
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    }

    var kOrder = [];
    for (var k = 0; k < P; k++) kOrder.push(k);
    if (vz < 0) kOrder.reverse();
    var cachedSlices = getCachedCubeSlices(st, blk, n, dark);
    var activeCorner = null;

    kOrder.forEach(function(kk) {
      var nz = P > 1 ? (kk / (P - 1) - 0.5) : 0;
      var p00 = project3D(-0.5, 0.5, nz, cx, cy, scale);
      var p10 = project3D(0.5, 0.5, nz, cx, cy, scale);
      var p01 = project3D(-0.5, -0.5, nz, cx, cy, scale);
      var p11 = project3D(0.5, -0.5, nz, cx, cy, scale);
      var isActive = (kk === state.lag);

      if (isActive) {
        activeCorner = project3D(bxWall, -byWall, nz, cx, cy, scale);
      }

      var slCanvas = (isActive && activeSliceCanvas) ? activeSliceCanvas : cachedSlices[kk];
      ctx.save();
      ctx.transform(
        (p10.x - p00.x) / n, (p10.y - p00.y) / n,
        (p01.x - p00.x) / n, (p01.y - p00.y) / n,
        p00.x, p00.y
      );
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(slCanvas, 0, 0);
      ctx.restore();

      if (isActive || kk === 0 || kk === P - 1 || P <= 12 || kk % 4 === 0) {
        ctx.beginPath();
        ctx.moveTo(p00.x, p00.y);
        ctx.lineTo(p10.x, p10.y);
        ctx.lineTo(p11.x, p11.y);
        ctx.lineTo(p01.x, p01.y);
        ctx.closePath();
        ctx.strokeStyle = isActive ? "#f59e0b" : gridCol;
        ctx.lineWidth = isActive ? 2.6 : 0.7;
        ctx.stroke();
      }
    });

    if (state.selOut < n && state.selIn < n) {
      var pinX = (state.selIn + 0.5) / n - 0.5;
      var pinY = (state.selOut + 0.5) / n - 0.5;
      var pinBot = project3D(pinX, pinY, -0.5, cx, cy, scale);
      var pinTop = project3D(pinX, pinY, 0.5, cx, cy, scale);
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 1.6;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(pinBot.x, pinBot.y);
      ctx.lineTo(pinTop.x, pinTop.y);
      ctx.stroke();
      ctx.setLineDash([]);
      var pinAct = project3D(
        pinX, pinY, P > 1 ? (state.lag / (P - 1) - 0.5) : 0, cx, cy, scale
      );
      ctx.fillStyle = "#f59e0b";
      ctx.beginPath();
      ctx.arc(pinAct.x, pinAct.y, 4.5, 0, Math.PI * 2);
      ctx.fill();
    }

    var fxWall = -bxWall;
    var fyWall = -byWall;
    var pOrigin = project3D(-0.5, -0.5, bzWall, cx, cy, scale);
    var pInEnd = project3D(0.5, fyWall, bzWall, cx, cy, scale);
    var pInMid = project3D(0, fyWall, bzWall, cx, cy, scale);
    var pOutMid = project3D(fxWall, 0, bzWall, cx, cy, scale);
    var pZTop = project3D(fxWall, byWall, 0.5, cx, cy, scale);
    var pZBot = project3D(fxWall, byWall, -0.5, cx, cy, scale);
    var pZMid = project3D(fxWall, byWall, 0, cx, cy, scale);

    ctx.fillStyle = textCol;
    ctx.font = "bold 11.5px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(
      "Input Mode j (" + blk.s0 + ".." + (blk.s0 + n - 1) + ")",
      pInMid.x, pInMid.y + 18
    );
    ctx.fillText(
      "Output Mode i (" + blk.s0 + ".." + (blk.s0 + n - 1) + ")",
      pOutMid.x + (fxWall > 0 ? 34 : -34), pOutMid.y + 16
    );
    ctx.fillText("Lag k", pZMid.x + (fxWall > 0 ? 28 : -28), pZMid.y - 4);
    ctx.font = "10.5px sans-serif";
    ctx.fillText("k=0", pZBot.x + (fxWall > 0 ? 18 : -18), pZBot.y + 4);
    ctx.fillText("k=" + (P - 1), pZTop.x + (fxWall > 0 ? 20 : -20), pZTop.y + 4);
    if (activeCorner) {
      var onLeft = activeCorner.x < cx;
      ctx.fillStyle = dark ? "#fbbf24" : "#b45309";
      ctx.font = "bold 11px sans-serif";
      ctx.textAlign = onLeft ? "right" : "left";
      ctx.fillText(
        "k=" + state.lag,
        activeCorner.x + (onLeft ? -8 : 8),
        activeCorner.y + 4
      );
    }
    if (pOrigin && pInEnd) {
      ctx.fillStyle = textCol;
      ctx.font = "bold 11.5px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(
        "Stage " + st.stage + " (" + (st.rate_hz / 1000).toFixed(1) + " kHz) | Blk " +
        blk.blk + " | Active k=" + state.lag +
        " (t-" + (state.lag * st.dt_ms).toFixed(2) + " ms)",
        14, 18
      );
    }

    var sc3d = get3DScaleAndCut(blk);
    var vmin3d = Math.min(sc3d.ref * 0.4, Math.max(sc3d.thr, sc3d.ref * 0.05, 1e-5));
    drawColorbar(
      ctx, w - 76, 40, 14, h - 84, vmin3d, sc3d.ref,
      state.cmap !== "magma", state.cmap === "magma" ? "|F| (3D p99)" : "F (3D p99)",
      textCol, borderCol, dark
    );
    state.last2D = null;
  }

  function drawSquareMatrix2D(ctx, w, h, st, blk, n, off, opts) {
    var dark = isDark();
    var textCol = dark ? "#cbd5e1" : "#334155";
    var borderCol = dark ? "#475569" : "#94a3b8";
    var pad = { l: 54, r: 88, t: 28, b: 42 };
    var availW = Math.max(80, w - pad.l - pad.r);
    var availH = Math.max(80, h - pad.t - pad.b);
    var P = st.order;
    var isML = Boolean(opts.isML);
    var plotW = isML ? availW : Math.min(availW, availH);
    var plotH = isML ? availH : plotW;
    var ox = pad.l + (availW - plotW) * 0.5;
    var oy = pad.t + (availH - plotH) * 0.5;

    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, ox, oy, plotW, plotH);
    ctx.restore();

    ctx.strokeStyle = opts.frameCol || borderCol;
    ctx.lineWidth = opts.frameCol ? 1.6 : 1.2;
    ctx.strokeRect(ox, oy, plotW, plotH);

    ctx.fillStyle = textCol;
    ctx.font = "bold 11.5px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(opts.title || "", ox, 16);

    ctx.font = "11px sans-serif";
    if (isML) {
      ctx.textAlign = "center";
      var kStep = P > 16 ? 4 : (P > 10 ? 2 : 1);
      for (var kk = 0; kk < P; kk++) {
        if (kk % kStep !== 0 && kk !== P - 1) continue;
        var tx = ox + ((kk + 0.5) / P) * plotW;
        ctx.fillText("k=" + kk, tx, oy + plotH + 16);
      }
      ctx.fillText("Lookback Lag k [frames]", ox + plotW * 0.5, oy + plotH + 34);
    } else {
      ctx.textAlign = "center";
      var nTicks = n > 1 ? 4 : 1;
      for (var ti = 0; ti <= nTicks; ti++) {
        var fracT = nTicks > 0 ? ti / nTicks : 0;
        var mIdx = Math.round((n - 1) * fracT);
        var gx = ox + fracT * plotW;
        ctx.fillText(String(blk.s0 + mIdx), gx, oy + plotH + 16);
      }
      ctx.fillText("Input Mode j (Past History)", ox + plotW * 0.5, oy + plotH + 34);
    }

    ctx.textAlign = "right";
    var yTicks = n > 1 ? 4 : 1;
    for (var yi = 0; yi <= yTicks; yi++) {
      var fracY = yTicks > 0 ? yi / yTicks : 0;
      var oIdx = Math.round((n - 1) * fracY);
      var gy = oy + (1 - fracY) * plotH;
      ctx.fillText(String(blk.s0 + oIdx), ox - 7, gy + 4);
    }
    ctx.save();
    ctx.translate(14, oy + plotH * 0.5);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText("Predicted Output Mode i", 0, 0);
    ctx.restore();

    if (state.selOut < n && state.selIn < n) {
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 1.8;
      if (isML) {
        var cw = plotW / P;
        var ch = plotH / n;
        var rx = ox + state.lag * cw;
        var ry = oy + (n - 1 - state.selOut) * ch;
        ctx.strokeRect(rx, ry, cw, ch);
      } else {
        var cxCell = ox + ((state.selIn + 0.5) / n) * plotW;
        var cyCell = oy + ((n - 1 - state.selOut + 0.5) / n) * plotH;
        ctx.beginPath();
        ctx.arc(cxCell, cyCell, Math.max(4, (plotW / n) * 0.85), 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    drawColorbar(
      ctx, ox + plotW + 12, oy, 14, plotH, opts.vmin, opts.vmax,
      opts.isSigned, opts.cbLabel, textCol, borderCol, dark
    );
    return { ox: ox, oy: oy, w: plotW, h: plotH, n: n, P: P, isML: isML };
  }

  function renderHeatmap2D(ctx, w, h, st, blk, n) {
    var dark = isDark();
    var off;
    var vmax;
    var vmin = 2e-3;
    var isSigned = false;
    var cbLabel = "";
    var title = "";
    var isML = (state.view === "modelag");

    if (state.view === "l2norm") {
      off = makeL2Canvas(blk, n);
      vmax = state.hideDiag ? blk._l2offMax : blk._l2max;
      cbLabel = "||F[i, :, j]||_2";
      title = st.label + " | Block " + blk.blk + " L2 Coupling Norm (origin=lower)";
    } else {
      var safeIn = Math.min(state.selIn, n - 1);
      off = makeModeLagCanvas(st, blk, n, safeIn, dark);
      vmax = Math.max(blk.vmax || 0.1, 0.05);
      isSigned = state.cmap !== "magma";
      cbLabel = isSigned ? "F[i, k, j]" : "|F[i, k, j]|";
      title = st.label + " | Cross-Section for Input Mode j=" + (blk.s0 + safeIn);
    }

    state.last2D = drawSquareMatrix2D(ctx, w, h, st, blk, n, off, {
      isML: isML,
      vmin: vmin,
      vmax: vmax,
      isSigned: isSigned,
      cbLabel: cbLabel,
      title: title
    });
  }

  function renderSelectedSlice2D(st, blk, n, slStats, slScale, activeSliceCanvas) {
    if (!sliceCanvas || !sliceCanvas.getContext) return;
    var dtStr = (state.lag * st.dt_ms).toFixed(2);
    if (slicePillEl) {
      slicePillEl.textContent = "k=" + state.lag + " (-" + dtStr + " ms)";
    }
    if (sliceTitleEl) {
      sliceTitleEl.textContent = "Selected Timeslice (2D Image)";
    }
    if (sliceMetaEl) {
      sliceMetaEl.textContent = "max |F|=" + fmtScaleVal(slStats.absMax) +
        " \u00b7 off-diag " + slStats.offPct.toFixed(1) + "%";
    }

    var dpr = window.devicePixelRatio || 1;
    var w = sliceCanvas.clientWidth || 460;
    var h = state.view === "slice2d" ? 460 : 416;
    sliceCanvas.width = w * dpr;
    sliceCanvas.height = h * dpr;
    var ctx = sliceCanvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    var isSigned = state.cmap !== "magma";
    var title = "Stage " + st.stage + " | Blk " + blk.blk +
      " (Modes " + blk.s0 + ".." + (blk.s0 + n - 1) + ")" +
      (state.hideDiag ? " [no diag]" : "");

    state.lastSlice2D = drawSquareMatrix2D(ctx, w, h, st, blk, n, activeSliceCanvas, {
      isML: false,
      vmin: slScale.vmin,
      vmax: slScale.vmax,
      isSigned: isSigned,
      cbLabel: isSigned ? "F[i, k, j]" : "|F[i, k, j]|",
      title: title,
      frameCol: "#f59e0b"
    });
  }

  function renderKernelChart(st, blk) {
    if (!kernCanvas || !kernCanvas.getContext) return;
    var dpr = window.devicePixelRatio || 1;
    var w = kernCanvas.clientWidth || 320;
    var h = 195;
    kernCanvas.width = w * dpr;
    kernCanvas.height = h * dpr;
    var ctx = kernCanvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    var P = st.order;
    var b = blk.b;
    var oi = Math.min(state.selOut, b - 1);
    var ij = Math.min(state.selIn, b - 1);
    var wFwd = [];
    var wRev = [];
    var absMax = 0.05;
    for (var k = 0; k < P; k++) {
      var vf = blk._tensor[(oi * P + k) * b + ij];
      var vr = blk._tensor[(ij * P + k) * b + oi];
      wFwd.push(vf);
      wRev.push(vr);
      if (Math.abs(vf) > absMax) absMax = Math.abs(vf);
      if (oi !== ij && Math.abs(vr) > absMax) absMax = Math.abs(vr);
    }
    var ymax = absMax * 1.18;
    var ymin = -ymax;
    var pad = { l: 46, r: 14, t: 22, b: 28 };
    var pw = Math.max(60, w - pad.l - pad.r);
    var ph = Math.max(50, h - pad.t - pad.b);

    var dark = isDark();
    var gridCol = dark ? "#334155" : "#e2e8f0";
    var textCol = dark ? "#cbd5e1" : "#475569";

    ctx.strokeStyle = gridCol;
    ctx.fillStyle = textCol;
    ctx.font = "10.5px sans-serif";
    for (var g = 0; g <= 4; g++) {
      var gy = pad.t + (ph * g) / 4;
      ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(pad.l + pw, gy); ctx.stroke();
      var yv = ymax - (2 * ymax * g) / 4;
      ctx.textAlign = "right";
      ctx.fillText(yv.toFixed(2), pad.l - 5, gy + 3);
    }

    var xZero = pad.l;
    var yZero = pad.t + ph * 0.5;
    ctx.strokeStyle = dark ? "#64748b" : "#94a3b8";
    ctx.beginPath(); ctx.moveTo(xZero, yZero); ctx.lineTo(pad.l + pw, yZero); ctx.stroke();

    var actX = pad.l + (P > 1 ? (state.lag / (P - 1)) * pw : pw * 0.5);
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 1.4;
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(actX, pad.t); ctx.lineTo(actX, pad.t + ph); ctx.stroke();
    ctx.setLineDash([]);

    function drawCurve(arr, col, dashed) {
      ctx.strokeStyle = col;
      ctx.lineWidth = 2.0;
      if (dashed) ctx.setLineDash([5, 3]);
      ctx.beginPath();
      for (var k = 0; k < P; k++) {
        var px = pad.l + (P > 1 ? (k / (P - 1)) * pw : pw * 0.5);
        var py = pad.t + (1 - (arr[k] - ymin) / (ymax - ymin)) * ph;
        if (k === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = col;
      for (var k2 = 0; k2 < P; k2++) {
        var px2 = pad.l + (P > 1 ? (k2 / (P - 1)) * pw : pw * 0.5);
        var py2 = pad.t + (1 - (arr[k2] - ymin) / (ymax - ymin)) * ph;
        ctx.beginPath();
        ctx.arc(px2, py2, k2 === state.lag ? 4 : 2.6, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    drawCurve(wFwd, "#2563eb", false);
    if (oi !== ij) drawCurve(wRev, "#059669", true);

    ctx.fillStyle = textCol;
    ctx.textAlign = "center";
    var kStep = P > 16 ? 4 : (P > 10 ? 2 : 1);
    for (var tk = 0; tk < P; tk++) {
      if (tk % kStep !== 0 && tk !== P - 1) continue;
      var tx = pad.l + (P > 1 ? (tk / (P - 1)) * pw : pw * 0.5);
      ctx.fillText(String(tk), tx, pad.t + ph + 14);
    }
    ctx.textAlign = "left";
    ctx.fillText(
      "F[" + (blk.s0 + oi) + ", k, " + (blk.s0 + ij) + "]" +
      (oi !== ij ? " vs F[" + (blk.s0 + ij) + ", k, " + (blk.s0 + oi) + "]" : " (self)"),
      pad.l, 13
    );
    state.lastKern = { pad: pad, pw: pw, P: P };
  }

  function renderStatsAndPairs(st, blk) {
    var oi = Math.min(state.selOut, blk.b - 1);
    var ij = Math.min(state.selIn, blk.b - 1);
    var P = st.order;
    var dc = 0;
    var valLag = blk._tensor[(oi * P + state.lag) * blk.b + ij];
    for (var kk = 0; kk < P; kk++) dc += blk._tensor[(oi * P + kk) * blk.b + ij];
    var l2Val = blk._l2[oi * blk.b + ij];
    var gOut = blk.s0 + oi;
    var gIn = blk.s0 + ij;

    if (pairTitleEl) {
      pairTitleEl.textContent = "Kernel: Mode " + gOut + " <- Mode " + gIn;
    }
    if (statsEl) {
      var items = [
        ["PSOL Lag d", st.pflatency_fr.toFixed(2) + " fr (" +
          (st.pflatency_fr * st.dt_ms).toFixed(2) + " ms)"],
        ["Var Red.", st.var_red_pct.toFixed(1) + "%"],
        ["Blk Off-Diag", blk.offdiag_pct.toFixed(1) + "%"],
        ["Lag Energy", (st.lag_energy_pct[state.lag] || 0).toFixed(1) + "% (off " +
          (st.lag_offdiag_pct[state.lag] || 0).toFixed(0) + "%)"],
        ["F(k=" + state.lag + ")", (valLag >= 0 ? "+" : "") + valLag.toFixed(4)],
        ["Pair L2 / DC", l2Val.toFixed(3) + " / " + (dc >= 0 ? "+" : "") + dc.toFixed(3)]
      ];
      statsEl.innerHTML = items.map(function(kv) {
        return '<div class="eof-pf-stat"><span>' + kv[0] +
          "</span><strong>" + kv[1] + "</strong></div>";
      }).join("");
    }
    if (pairsEl) {
      var tp = blk.top_pairs || [];
      if (!tp.length) {
        pairsEl.innerHTML = '<span class="muted">No off-diagonal couplings in block.</span>';
      } else {
        pairsEl.innerHTML = tp.map(function(pair) {
          var active = (pair[0] === gOut && pair[1] === gIn);
          return '<button type="button" class="chip-btn' + (active ? " active" : "") +
            '" data-pair-o="' + (pair[0] - blk.s0) + '" data-pair-i="' +
            (pair[1] - blk.s0) + '">' + pair[0] + "&larr;" + pair[1] +
            " (" + pair[2].toFixed(2) + ")</button>";
        }).join("");
        pairsEl.querySelectorAll("[data-pair-o]").forEach(function(btn) {
          btn.addEventListener("click", function() {
            state.selOut = parseInt(btn.getAttribute("data-pair-o"), 10) || 0;
            state.selIn = parseInt(btn.getAttribute("data-pair-i"), 10) || 0;
            renderAll();
          });
        });
      }
    }
  }

  function renderAll() {
    var st = curStage();
    var blk = curBlock(st);
    var n = dispDim(blk);
    if (state.selOut >= n) state.selOut = n - 1;
    if (state.selIn >= n) state.selIn = n - 1;
    if (state.lag >= st.order) state.lag = st.order - 1;
    if (state.lag < 0) state.lag = 0;

    if (lagSlider) {
      lagSlider.max = String(Math.max(0, st.order - 1));
      lagSlider.value = String(state.lag);
    }
    if (lagPrevBtn) lagPrevBtn.disabled = state.lag <= 0;
    if (lagNextBtn) lagNextBtn.disabled = state.lag >= st.order - 1;
    if (lagReadout) {
      lagReadout.textContent = "k=" + state.lag +
        " (-" + (state.lag * st.dt_ms).toFixed(2) + " ms)";
    }
    var dark = isDark();
    var sc3d = get3DScaleAndCut(blk);
    var slStats = computeSliceStats(st, blk, state.lag, n);
    var slScale = getSliceScale(blk, slStats);
    var activeSliceCanvas = makeSliceCanvas(
      st, blk, state.lag, n, false, slScale.vmax, slScale.vmin, dark
    );

    if (threshValEl) threshValEl.textContent = fmtScaleVal(sc3d.thr);
    if (visGrid) {
      visGrid.classList.toggle("is-slice-only", state.view === "slice2d");
    }
    if (hintEl) {
      hintEl.textContent = state.view === "cube3d"
        ? "Drag 3D cube to orbit; selected lag k renders as an opaque 2D image in 3D and at right."
        : "Hover for exact tensor weights; click any cell to inspect its temporal kernel.";
    }

    if (state.view !== "slice2d") {
      var dpr = window.devicePixelRatio || 1;
      var w = mainCanvas.clientWidth || 540;
      var h = 450;
      mainCanvas.width = w * dpr;
      mainCanvas.height = h * dpr;
      var ctx = mainCanvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      mainCanvas.style.cursor = state.view === "cube3d"
        ? (state.drag ? "grabbing" : "grab")
        : "crosshair";

      if (state.view === "cube3d") renderCube3D(ctx, w, h, st, blk, n, activeSliceCanvas);
      else renderHeatmap2D(ctx, w, h, st, blk, n);
    } else {
      state.last2D = null;
      if (tip) tip.style.display = "none";
    }

    renderSelectedSlice2D(st, blk, n, slStats, slScale, activeSliceCanvas);
    renderKernelChart(st, blk);
    renderStatsAndPairs(st, blk);
  }

  function populateStageAndBlockControls() {
    if (stageBtnsWrap) {
      stageBtnsWrap.innerHTML = data.stages.map(function(st, i) {
        return '<button type="button" class="chip-btn' + (i === state.stgIdx ? " active" : "") +
          '" data-pf-stg="' + i + '">Stage ' + st.stage + " (" + st.n_modes + "m)</button>";
      }).join("");
      stageBtnsWrap.querySelectorAll("[data-pf-stg]").forEach(function(btn) {
        btn.addEventListener("click", function() {
          state.stgIdx = parseInt(btn.getAttribute("data-pf-stg"), 10) || 0;
          state.blkIdx = 0;
          populateStageAndBlockControls();
          var st = curStage();
          pickDefaultPair(st, curBlock(st));
          renderAll();
        });
      });
    }
    var st = curStage();
    if (blkSel) {
      blkSel.innerHTML = st.blocks.map(function(blk, i) {
        var s1 = blk.s0 + blk.b - 1;
        return '<option value="' + i + '"' + (i === state.blkIdx ? " selected" : "") +
          ">Block " + blk.blk + " (Modes " + blk.s0 + "-" + s1 + ", " +
          blk.offdiag_pct.toFixed(1) + "% off)</option>";
      }).join("");
    }
  }

  if (blkSel) {
    blkSel.addEventListener("change", function() {
      state.blkIdx = parseInt(blkSel.value, 10) || 0;
      var st = curStage();
      pickDefaultPair(st, curBlock(st));
      renderAll();
    });
  }
  viewBtns.forEach(function(btn) {
    btn.addEventListener("click", function() {
      state.view = btn.getAttribute("data-pf-view") || "cube3d";
      viewBtns.forEach(function(b) { b.classList.toggle("active", b === btn); });
      renderAll();
    });
  });
  if (lagSlider) {
    lagSlider.addEventListener("input", function() {
      state.lag = parseInt(lagSlider.value, 10) || 0;
      renderAll();
    });
  }
  if (lagPrevBtn) {
    lagPrevBtn.addEventListener("click", function() {
      if (state.lag > 0) { state.lag -= 1; renderAll(); }
    });
  }
  if (lagNextBtn) {
    lagNextBtn.addEventListener("click", function() {
      var st = curStage();
      if (state.lag < st.order - 1) { state.lag += 1; renderAll(); }
    });
  }
  if (playBtn) {
    playBtn.addEventListener("click", function() {
      state.playing = !state.playing;
      playBtn.textContent = state.playing ? "Pause" : "Play";
      if (state.playTimer) { clearInterval(state.playTimer); state.playTimer = null; }
      if (state.playing) {
        state.playTimer = setInterval(function() {
          var st = curStage();
          state.lag = (state.lag + 1) % Math.max(1, st.order);
          renderAll();
        }, 420);
      }
    });
  }
  if (zoomSel) {
    zoomSel.addEventListener("change", function() {
      state.zoomN = parseInt(zoomSel.value, 10) || 0;
      renderAll();
    });
  }
  if (cmapSel) {
    cmapSel.addEventListener("change", function() {
      state.cmap = cmapSel.value || "rdbu";
      renderAll();
    });
  }
  if (hideDiagCb) {
    hideDiagCb.addEventListener("change", function() {
      state.hideDiag = Boolean(hideDiagCb.checked);
      renderAll();
    });
  }
  if (sliceAutoCb) {
    sliceAutoCb.addEventListener("change", function() {
      state.sliceAutoScale = Boolean(sliceAutoCb.checked);
      renderAll();
    });
  }
  if (threshSlider) {
    threshSlider.addEventListener("input", function() {
      state.threshStep = parseInt(threshSlider.value, 10) || 0;
      renderAll();
    });
  }
  if (resetBtn) {
    resetBtn.addEventListener("click", function() {
      state.azim = -53 * Math.PI / 180;
      state.elev = 23 * Math.PI / 180;
      renderAll();
    });
  }

  mainCanvas.addEventListener("mousedown", function(ev) {
    if (state.view !== "cube3d") return;
    state.drag = { x: ev.clientX, y: ev.clientY, azim: state.azim, elev: state.elev };
    renderAll();
  });
  mainCanvas.addEventListener("touchstart", function(ev) {
    if (state.view !== "cube3d" || !ev.touches || !ev.touches.length) return;
    var t = ev.touches[0];
    state.drag = { x: t.clientX, y: t.clientY, azim: state.azim, elev: state.elev };
  }, { passive: true });
  window.addEventListener("mousemove", function(ev) {
    if (!state.drag) return;
    var dx = ev.clientX - state.drag.x;
    var dy = ev.clientY - state.drag.y;
    state.azim = state.drag.azim + dx * 0.008;
    var el = state.drag.elev + dy * 0.008;
    state.elev = Math.max(-1.45, Math.min(1.45, el));
    renderAll();
  });
  window.addEventListener("touchmove", function(ev) {
    if (!state.drag || !ev.touches || !ev.touches.length) return;
    var t = ev.touches[0];
    state.azim = state.drag.azim + (t.clientX - state.drag.x) * 0.008;
    var el = state.drag.elev + (t.clientY - state.drag.y) * 0.008;
    state.elev = Math.max(-1.45, Math.min(1.45, el));
    renderAll();
  }, { passive: true });
  window.addEventListener("mouseup", function() {
    if (state.drag) { state.drag = null; renderAll(); }
  });
  window.addEventListener("touchend", function() {
    if (state.drag) { state.drag = null; renderAll(); }
  });

  function hitCanvas2D(canvas, box, ev) {
    if (!canvas || !box) return null;
    var rect = canvas.getBoundingClientRect();
    var mx = ev.clientX - rect.left;
    var my = ev.clientY - rect.top;
    if (mx < box.ox || mx > box.ox + box.w || my < box.oy || my > box.oy + box.h) return null;
    var fracX = (mx - box.ox) / box.w;
    var fracY = 1.0 - (my - box.oy) / box.h;
    var oi = Math.max(0, Math.min(box.n - 1, Math.floor(fracY * box.n)));
    var col = box.isML
      ? Math.max(0, Math.min(box.P - 1, Math.floor(fracX * box.P)))
      : Math.max(0, Math.min(box.n - 1, Math.floor(fracX * box.n)));
    return { oi: oi, col: col, mx: mx, my: my, rect: rect };
  }

  function show2DTooltip(tipEl, hit, isML) {
    var st = curStage();
    var blk = curBlock(st);
    var gOut = blk.s0 + hit.oi;
    if (isML) {
      var safeInHit = Math.min(state.selIn, blk.b - 1);
      var gIn = blk.s0 + safeInHit;
      var vml = blk._tensor[(hit.oi * st.order + hit.col) * blk.b + safeInHit];
      tipEl.innerHTML = "Out " + gOut + " &larr; In " + gIn + "<br>Lag k=" + hit.col +
        " (-" + (hit.col * st.dt_ms).toFixed(2) + " ms)<br>F = " + vml.toFixed(4);
    } else {
      var gIn2 = blk.s0 + hit.col;
      var v2d = blk._tensor[(hit.oi * st.order + state.lag) * blk.b + hit.col];
      var l2v = blk._l2[hit.oi * blk.b + hit.col];
      tipEl.innerHTML = "Out " + gOut + " &larr; In " + gIn2 +
        "<br>F(k=" + state.lag + ") = " + v2d.toFixed(4) +
        "<br>||F||_2 = " + l2v.toFixed(4);
    }
    tipEl.style.display = "block";
    tipEl.style.left = Math.min(Math.max(8, hit.rect.width - 175), hit.mx + 14) + "px";
    tipEl.style.top = Math.max(8, hit.my - 14) + "px";
  }

  mainCanvas.addEventListener("mousemove", function(ev) {
    if (state.drag || !tip) return;
    var hit = hitCanvas2D(mainCanvas, state.last2D, ev);
    if (!hit) { tip.style.display = "none"; return; }
    show2DTooltip(tip, hit, state.last2D.isML);
  });

  mainCanvas.addEventListener("mouseleave", function() {
    if (tip) tip.style.display = "none";
  });

  mainCanvas.addEventListener("click", function(ev) {
    var hit = hitCanvas2D(mainCanvas, state.last2D, ev);
    if (!hit) return;
    state.selOut = hit.oi;
    if (state.last2D.isML) state.lag = hit.col;
    else state.selIn = hit.col;
    renderAll();
  });

  if (sliceCanvas) {
    sliceCanvas.addEventListener("mousemove", function(ev) {
      if (!sliceTip) return;
      var hit = hitCanvas2D(sliceCanvas, state.lastSlice2D, ev);
      if (!hit) { sliceTip.style.display = "none"; return; }
      show2DTooltip(sliceTip, hit, false);
    });
    sliceCanvas.addEventListener("mouseleave", function() {
      if (sliceTip) sliceTip.style.display = "none";
    });
    sliceCanvas.addEventListener("click", function(ev) {
      var hit = hitCanvas2D(sliceCanvas, state.lastSlice2D, ev);
      if (!hit) return;
      state.selOut = hit.oi;
      state.selIn = hit.col;
      renderAll();
    });
  }

  if (kernCanvas) {
    kernCanvas.addEventListener("click", function(ev) {
      var kbox = state.lastKern;
      if (!kbox || kbox.P <= 1) return;
      var rect = kernCanvas.getBoundingClientRect();
      var mx = ev.clientX - rect.left;
      if (mx < kbox.pad.l || mx > kbox.pad.l + kbox.pw) return;
      var frac = (mx - kbox.pad.l) / kbox.pw;
      state.lag = Math.max(0, Math.min(kbox.P - 1, Math.round(frac * (kbox.P - 1))));
      renderAll();
    });
  }

  var tBtn = document.getElementById("theme-toggle");
  if (tBtn) tBtn.addEventListener("click", function() { setTimeout(renderAll, 20); });
  window.addEventListener("resize", renderAll);

  populateStageAndBlockControls();
  var st0 = curStage();
  pickDefaultPair(st0, curBlock(st0));
  renderAll();
})();
