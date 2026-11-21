/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

(function() {
  var defEl = document.getElementById("howtorun-defaults");
  if (defEl) {
    var defs = {};
    try { defs = JSON.parse(defEl.textContent || "{}"); } catch (e) {}
    var advSpecs = [];
    var advEl = document.getElementById("howtorun-adv-specs");
    if (advEl) {
      try { advSpecs = JSON.parse(advEl.textContent || "[]"); } catch (e) {}
    }
    var fields = ["seeing", "phys_time", "bench_mode", "oversample", "gain1", "gain2",
      "gain3", "llowfs", "pf_mode", "pf_order", "pf_blocksize", "pf_reg",
      "calib_2wfs1dm", "telemetry"];
    function loadDefs() {
      fields.forEach(function(k) {
        var el = document.getElementById("cust-" + k);
        if (el && defs[k] !== undefined) el.value = String(defs[k]);
      });
      advSpecs.forEach(function(sp) {
        var el = document.getElementById("cust-adv-" + sp.key);
        if (!el) return;
        if (sp.type === "bool") {
          el.checked = sp.init === "1" || sp.init === "true" || sp.init === "ON";
        } else {
          el.value = sp.init || "";
        }
      });
      updateCmds();
    }
    function val(k) {
      var el = document.getElementById("cust-" + k);
      return el ? el.value : "";
    }
    function updateCmds() {
      var slug = defs.slug || "ao3k_scexao";
      var cmd = "./scripts/run-ao3k-scexao.sh --seeing " + val("seeing") +
        " --phys-time " + val("phys_time") +
        " --oversample " + val("oversample") +
        " --bench-mode " + val("bench_mode") +
        " --gain1 " + val("gain1") + " --gain2 " + val("gain2");
      if (val("llowfs") === "open") cmd += " --no-lowfs";
      else cmd += " --gain3 " + val("gain3");
      var pf = val("pf_mode");
      if (pf === "ar") {
        cmd += " --predictive --pf-mode ar --pf-order " + val("pf_order") +
          " --pf-reg " + val("pf_reg");
      } else if (pf === "eof") {
        cmd += " --predictive --pf-mode eof --pf-blocksize " + val("pf_blocksize") +
          " --pf-order " + val("pf_order") + " --pf-reg " + val("pf_reg") +
          " --pf-warmup-sec 14.0";
      }
      if (val("calib_2wfs1dm") === "on") cmd += " --calib-2wfs1dm";
      if (val("telemetry") !== "none") cmd += " --save-telemetry " + val("telemetry");
      advSpecs.forEach(function(sp) {
        var el = document.getElementById("cust-adv-" + sp.key);
        if (!el) return;
        if (sp.type === "bool") {
          if (el.checked) cmd += " " + sp.flag;
        } else {
          var v = (el.value || "").trim();
          if (v !== "") cmd += " " + sp.flag + " " + v;
        }
      });
      cmd += " --save-rm _work/ao3k_scexao_rm --outdir _work/" + slug;

      var c1 = document.getElementById("cmd-turnkey");
      if (c1) c1.textContent = "source env.sh\n" + cmd;

      var c2 = document.getElementById("cmd-cacaosim");
      if (c2) {
        c2.textContent = "source env.sh\n" +
          "cacaosim-bench deploy -c benches/ao3k_scexao/ao3k_scexao.bench \\\n" +
          "  --mode " + val("bench_mode") + " --oversample " + val("oversample") +
          " --atmturb --seeing " + val("seeing");
      }
      var c3 = document.getElementById("cmd-cacaoloop");
      if (c3) {
        var pfLines = "";
        if (pf !== "off") {
          pfLines = "\nCACAO_PF_MODE=" + pf + " CACAO_PF_ORDER=" + val("pf_order") +
            " ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 pf-on 0.90" +
            "\nCACAO_PF_MODE=" + pf + " CACAO_PF_ORDER=" + val("pf_order") +
            " ./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 pf-on 0.90";
        }
        var s3Line = val("llowfs") === "open"
          ? "# Stage 3 LLOWFS kept OPEN"
          : "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 3 close " + val("gain3");
        c3.textContent =
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 deploy && " +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 calibrate\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 deploy && " +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 calibrate\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 3 deploy && " +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 3 calibrate\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 1 close " +
          val("gain1") + "\n" +
          "./benches/ao3k_scexao/cacaoloop-ao3k-scexao.milk --stage 2 close " +
          val("gain2") + "\n" +
          s3Line + pfLines;
      }
      var note = document.getElementById("cust-advice");
      if (note) {
        var msgs = [];
        if (pf === "ar" && parseInt(val("pf_order"), 10) > 16) {
          msgs.push(
            "Tip: AR order > 16 benefits from N_train=4096 / N_min=1024 for stable warmup."
          );
        }
        if (pf === "eof") {
          msgs.push(
            "Tip: Block-EOF bootstraps with Diagonal AR(16) before switching at 12k/24k frames."
          );
        }
        if (val("bench_mode") === "modular") {
          msgs.push(
            "Modular mode splits csim_htsim into per-element FPS daemons for optical inspection."
          );
        }
        note.textContent = msgs.join(" ") || "Configuration matches balanced real-time execution.";
      }
    }
    fields.forEach(function(k) {
      var el = document.getElementById("cust-" + k);
      if (el) el.addEventListener("change", updateCmds);
    });
    advSpecs.forEach(function(sp) {
      var el = document.getElementById("cust-adv-" + sp.key);
      if (el) {
        el.addEventListener("change", updateCmds);
        el.addEventListener("input", updateCmds);
      }
    });
    var rst = document.getElementById("cust-reset");
    if (rst) rst.addEventListener("click", loadDefs);
    loadDefs();
  }

  if (window.cacaoInitCatFilter) {
    window.cacaoInitCatFilter({
      tableId: "compute-units-table",
      prefix: "cu",
      rowSelector: "tr.unit-row",
      searchId: "cu-search",
      noun: "units"
    });
  }
  var cuTbl = document.getElementById("compute-units-table");
  if (cuTbl) {
    cuTbl.querySelectorAll("tbody tr.unit-row").forEach(function(tr) {
      tr.style.cursor = "pointer";
      tr.addEventListener("click", function() {
        var det = tr.nextElementSibling;
        if (det && det.classList.contains("detail-row")) {
          det.classList.toggle("hidden");
        }
      });
    });
  }

  var cbs = Array.from(document.querySelectorAll("input.deploy-step-cb"));
  var progTxt = document.getElementById("deploy-progress-text");
  var progBar = document.getElementById("deploy-progress-fill");
  function updateProg() {
    if (!cbs.length) return;
    var done = 0;
    cbs.forEach(function(cb) {
      var item = cb.closest(".checklist-item");
      if (item) item.classList.toggle("done", cb.checked);
      if (cb.checked) done++;
    });
    if (progTxt) progTxt.textContent = done + " / " + cbs.length + " steps completed";
    if (progBar) progBar.style.width = ((done / cbs.length) * 100).toFixed(0) + "%";
  }
  cbs.forEach(function(cb) { cb.addEventListener("change", updateProg); });
  updateProg();
})();
