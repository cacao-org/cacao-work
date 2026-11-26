/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */
/* Interactive scaling calculator and CLI override builder for /turbulence/index.html. */
(function () {
  "use strict";

  var dataEl = document.getElementById("turb-model-data");
  if (!dataEl) return;
  var DATA;
  try {
    DATA = JSON.parse(dataEl.textContent || "{}");
  } catch (e) {
    return;
  }

  var seeIn = document.getElementById("tc-seeing");
  var windIn = document.getElementById("tc-wind-scale");
  var vibRmsIn = document.getElementById("tc-vib-rms");
  var petRmsIn = document.getElementById("tc-petal-rms");
  var petTauIn = document.getElementById("tc-petal-tau");
  var windVarCb = document.getElementById("tc-wind-var");
  var windBurstCb = document.getElementById("tc-wind-burst");
  var vibOnCb = document.getElementById("tc-vib-on");
  var petOnCb = document.getElementById("tc-petal-on");
  var resetBtn = document.getElementById("tc-reset-btn");
  var copyBtn = document.getElementById("tc-copy-btn");

  if (!seeIn || !windIn || !vibRmsIn || !petRmsIn || !petTauIn) return;

  function interpGrid(x, xs, ys) {
    if (!xs || !xs.length) return 0;
    if (x <= xs[0]) return ys[0];
    if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
    for (var i = 0; i < xs.length - 1; i++) {
      if (x >= xs[i] && x <= xs[i + 1]) {
        var t = (x - xs[i]) / Math.max(xs[i + 1] - xs[i], 1e-9);
        return ys[i] * (1 - t) + ys[i + 1] * t;
      }
    }
    return ys[ys.length - 1];
  }

  function ratioStr(val, defVal) {
    if (defVal <= 0) return "";
    var r = val / defVal;
    if (Math.abs(r - 1.0) < 0.015) return "";
    if (Math.abs(r - Math.round(r)) < 0.03 && Math.round(r) >= 2) {
      return Math.round(r) + "x default";
    }
    return r.toFixed(2) + "x default";
  }

  function update() {
    var d = DATA.defaults || {};
    var defSeeing = d.seeing || 0.8;
    var defVib = d.vib_rms_nm || 45.0;
    var defPetal = d.petal_rms_nm || 1000.0;
    var defTau = d.petal_tau_s || 3.0;

    var see = parseFloat(seeIn.value) || defSeeing;
    var wScale = parseFloat(windIn.value) || 1.0;
    var wVar = !!(windVarCb && windVarCb.checked);
    var wBurst = !!(windBurstCb && windBurstCb.checked);
    var vibOn = !!(vibOnCb && vibOnCb.checked);
    var vibRms = vibOn ? parseFloat(vibRmsIn.value) || 0 : 0;
    var petOn = !!(petOnCb && petOnCb.checked);
    var petRms = petOn ? parseFloat(petRmsIn.value) || 0 : 0;
    var petTau = parseFloat(petTauIn.value) || defTau;

    vibRmsIn.disabled = !vibOn;
    petRmsIn.disabled = !petOn;
    petTauIn.disabled = !petOn;

    document.getElementById("tc-seeing-val").textContent = see.toFixed(2) + '"';
    document.getElementById("tc-wind-scale-val").textContent = wScale.toFixed(2) + "x";
    document.getElementById("tc-vib-rms-val").textContent = vibOn
      ? Math.round(vibRms) + " nm"
      : "OFF";
    document.getElementById("tc-petal-rms-val").textContent = petOn
      ? Math.round(petRms) + " nm"
      : "OFF";
    document.getElementById("tc-petal-tau-val").textContent = petOn
      ? petTau.toFixed(1) + " s"
      : "OFF";

    var r0_500 = interpGrid(see, DATA.seeing_grid, DATA.r0_500_cm);
    var r0_165 = r0_500 * Math.pow(1.65 / 0.5, 1.2);
    var opdAtm = interpGrid(see, DATA.seeing_grid, DATA.opd_vk_nm);
    var vEff = (DATA.v_eff_nom_mps || 9.736) * wScale;
    var hEff = DATA.h_eff_m || 5622.7;
    var r0m = r0_500 / 100.0;
    var tau0Ms = (0.314 * r0m / Math.max(vEff, 1e-6)) * 1000.0;
    var fGHz = (0.427 * vEff) / Math.max(r0m, 1e-6);
    var theta0Arc = ((0.314 * r0m) / hEff) * (180.0 / Math.PI) * 3600.0;

    var totQuad = Math.sqrt(opdAtm * opdAtm + vibRms * vibRms + petRms * petRms);
    var zShares = DATA.vib_z_shares || [0.5206, 0.4125, 0.0342];
    var z2 = vibRms * Math.sqrt(zShares[0] || 0);
    var z3 = vibRms * Math.sqrt(zShares[1] || 0);
    var z4 = vibRms * Math.sqrt(zShares[2] || 0);

    var petPis = petRms * Math.sqrt(0.75);
    var petPtv = 2.0588 * petRms;
    var petFc = 1.0 / (2.0 * Math.PI * Math.max(petTau, 0.05));

    document.getElementById("tc-out-r0").textContent =
      r0_500.toFixed(1) + " / " + r0_165.toFixed(1) + " cm";
    document.getElementById("tc-out-tau0").textContent =
      vEff.toFixed(1) + " m/s · " + tau0Ms.toFixed(2) + " ms";
    document.getElementById("tc-out-fg").textContent =
      fGHz.toFixed(1) + ' Hz · ' + theta0Arc.toFixed(2) + '"';
    document.getElementById("tc-out-opd").textContent =
      Math.round(opdAtm) + " / " + Math.round(totQuad) + " nm";
    document.getElementById("tc-out-vib").textContent =
      vibOn && vibRms > 0
        ? z2.toFixed(1) + " / " + z3.toFixed(1) + " / " + z4.toFixed(1) + " nm"
        : "OFF (0 nm)";
    document.getElementById("tc-out-petal").textContent =
      petOn && petRms > 0
        ? Math.round(petPis) + " / " + Math.round(petPtv) + " nm · " + petFc.toFixed(3) + " Hz"
        : "OFF (0 nm)";

    // Build exact override flags & diff summary
    var flags = [];
    var diffs = [];
    if (Math.abs(see - defSeeing) > 0.005) {
      flags.push("--seeing " + see.toFixed(2));
      var rs = ratioStr(see, defSeeing);
      diffs.push('Seeing ' + see.toFixed(2) + '"' + (rs ? " (" + rs + ")" : ""));
    }
    if (Math.abs(wScale - 1.0) > 0.01) {
      flags.push("# FPS: csim_atmturb.wind_speed_scale=" + wScale.toFixed(2));
      diffs.push("Wind speed " + wScale.toFixed(2) + "x default");
    }
    var allOff = !wVar && !wBurst && (!vibOn || vibRms <= 0) && (!petOn || petRms <= 0);
    if (allOff) {
      flags.push("--no-perturb");
      diffs.push("All dynamic perturbations OFF");
    } else {
      if (!wVar) {
        flags.push("--no-wind-var");
        diffs.push("Wind meandering OFF");
      }
      if (!wBurst) {
        flags.push("--no-wind-burst");
        diffs.push("Gust bursts OFF");
      }
      if (!vibOn || vibRms <= 0) {
        flags.push("--no-vib");
        diffs.push("Vibrations OFF");
      } else if (Math.abs(vibRms - defVib) > 0.5) {
        flags.push("--vib-rms-nm " + vibRms.toFixed(0));
        var rv = ratioStr(vibRms, defVib);
        diffs.push("Vibrations " + Math.round(vibRms) + " nm" + (rv ? " (" + rv + ")" : ""));
      }
      if (!petOn || petRms <= 0) {
        flags.push("--no-petal");
        diffs.push("Petaling OFF");
      } else {
        if (Math.abs(petRms - defPetal) > 1.0) {
          flags.push("--petal-rms-nm " + petRms.toFixed(0));
          var rp = ratioStr(petRms, defPetal);
          diffs.push("Petaling " + Math.round(petRms) + " nm" + (rp ? " (" + rp + ")" : ""));
        }
        if (Math.abs(petTau - defTau) > 0.05) {
          flags.push("--petal-tau-s " + petTau.toFixed(1));
          diffs.push("Petaling tau=" + petTau.toFixed(1) + " s");
        }
      }
    }

    var cliFlags = flags.filter(function (f) {
      return f.indexOf("#") !== 0;
    });
    var noteFlags = flags.filter(function (f) {
      return f.indexOf("#") === 0;
    });
    var cmd = "./scripts/run-ao3k-scexao.sh" + (cliFlags.length ? " " + cliFlags.join(" ") : "");
    if (noteFlags.length) {
      cmd += "\n" + noteFlags.join("\n");
    }
    document.getElementById("tc-cli-cmd").textContent = cmd;

    var pill = document.getElementById("tc-diff-summary");
    if (!diffs.length) {
      pill.className = "turb-status-pill turb-pill-def";
      pill.textContent = "Matches Default Model";
    } else {
      pill.className = "turb-status-pill turb-pill-mod";
      pill.textContent = "Modified: " + diffs.join(" · ");
    }
  }

  [seeIn, windIn, vibRmsIn, petRmsIn, petTauIn].forEach(function (el) {
    el.addEventListener("input", update);
  });
  [windVarCb, windBurstCb, vibOnCb, petOnCb].forEach(function (el) {
    if (el) el.addEventListener("change", update);
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      var d = DATA.defaults || {};
      seeIn.value = String(d.seeing || 0.8);
      windIn.value = "1.00";
      vibRmsIn.value = String(d.vib_rms_nm || 45);
      petRmsIn.value = String(d.petal_rms_nm || 1000);
      petTauIn.value = String(d.petal_tau_s || 3.0);
      if (windVarCb) windVarCb.checked = true;
      if (windBurstCb) windBurstCb.checked = true;
      if (vibOnCb) vibOnCb.checked = true;
      if (petOnCb) petOnCb.checked = true;
      update();
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var cmdEl = document.getElementById("tc-cli-cmd");
      if (!cmdEl || !navigator.clipboard) return;
      navigator.clipboard.writeText(cmdEl.textContent || "").then(function () {
        var old = copyBtn.textContent;
        copyBtn.textContent = "Copied!";
        setTimeout(function () {
          copyBtn.textContent = old;
        }, 1200);
      });
    });
  }

  update();
})();
