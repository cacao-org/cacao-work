/* SPDX-FileCopyrightText: 2026 Olivier Guyon et al
   SPDX-License-Identifier: LGPL-3.0-or-later */

(function() {
  var dropdowns = Array.from(document.querySelectorAll(".nav-dropdown"));

  function closeAllDropdowns(except) {
    dropdowns.forEach(function(dd) {
      if (dd !== except) {
        dd.classList.remove("open");
        var btn = dd.querySelector(".nav-drop-btn");
        if (btn) btn.setAttribute("aria-expanded", "false");
      }
    });
  }

  dropdowns.forEach(function(dd) {
    var btn = dd.querySelector(".nav-drop-btn");
    var menu = dd.querySelector(".nav-drop-menu");
    if (!btn || !menu) return;
    btn.addEventListener("click", function(ev) {
      ev.stopPropagation();
      var willOpen = !dd.classList.contains("open");
      closeAllDropdowns(willOpen ? dd : null);
      dd.classList.toggle("open", willOpen);
      btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
    });
    dd.addEventListener("keydown", function(ev) {
      var items = Array.from(menu.querySelectorAll("a.drop-item"));
      if (ev.key === "Escape") {
        closeAllDropdowns(null);
        btn.focus();
      } else if (ev.key === "ArrowDown" && items.length) {
        ev.preventDefault();
        if (!dd.classList.contains("open")) {
          closeAllDropdowns(dd);
          dd.classList.add("open");
          btn.setAttribute("aria-expanded", "true");
        }
        var cur = items.indexOf(document.activeElement);
        items[(cur + 1) % items.length].focus();
      } else if (ev.key === "ArrowUp" && items.length && dd.classList.contains("open")) {
        ev.preventDefault();
        var curU = items.indexOf(document.activeElement);
        items[(curU - 1 + items.length) % items.length].focus();
      }
    });
  });

  document.addEventListener("click", function(ev) {
    if (!ev.target.closest(".nav-dropdown")) closeAllDropdowns(null);
  });

  var sbBtn = document.getElementById("sidebar-toggle");
  var sbBackdrop = document.getElementById("sidebar-backdrop");
  var sidebarEl = document.getElementById("site-sidebar");
  if (sidebarEl) {
    var savedSb = null;
    try { savedSb = localStorage.getItem("cacao_sidebar"); } catch (e) {}
    if (savedSb === "collapsed" && window.innerWidth > 1024) {
      document.body.classList.add("sidebar-collapsed");
      if (sbBtn) sbBtn.setAttribute("aria-expanded", "false");
    }
  }
  function toggleSidebar() {
    if (!sidebarEl) return;
    if (window.innerWidth <= 1024) {
      var mobOpen = !document.body.classList.contains("sidebar-mobile-open");
      document.body.classList.toggle("sidebar-mobile-open", mobOpen);
      if (sbBtn) sbBtn.setAttribute("aria-expanded", mobOpen ? "true" : "false");
    } else {
      var collapsed = !document.body.classList.contains("sidebar-collapsed");
      document.body.classList.toggle("sidebar-collapsed", collapsed);
      if (sbBtn) sbBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      try { localStorage.setItem("cacao_sidebar", collapsed ? "collapsed" : "open"); } catch (e) {}
    }
  }
  if (sbBtn) sbBtn.addEventListener("click", toggleSidebar);
  if (sbBackdrop) {
    sbBackdrop.addEventListener("click", function() {
      document.body.classList.remove("sidebar-mobile-open");
      if (sbBtn) sbBtn.setAttribute("aria-expanded", "false");
    });
  }

  var tocLinks = Array.from(document.querySelectorAll(".sidebar-toc a.toc-link"));
  if (tocLinks.length > 0 && "IntersectionObserver" in window) {
    var mapById = {};
    tocLinks.forEach(function(a) {
      var href = a.getAttribute("href") || "";
      if (href.charAt(0) === "#") mapById[href.slice(1)] = a;
    });
    var obs = new IntersectionObserver(function(entries) {
      entries.forEach(function(ent) {
        if (ent.isIntersecting && mapById[ent.target.id]) {
          tocLinks.forEach(function(a) { a.classList.remove("active"); });
          mapById[ent.target.id].classList.add("active");
        }
      });
    }, { rootMargin: "-18% 0px -68% 0px", threshold: 0.01 });
    Object.keys(mapById).forEach(function(hid) {
      var hEl = document.getElementById(hid);
      if (hEl) obs.observe(hEl);
    });
  }

  var searchOpen = document.getElementById("global-search-open");
  var searchModal = document.getElementById("global-search-backdrop");
  var searchInput = document.getElementById("global-search-input");
  var searchRes = document.getElementById("global-search-results");
  var searchClose = document.getElementById("global-search-close");

  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderSearch(query) {
    if (!searchRes) return;
    var items = Array.isArray(window.CACAO_SEARCH_INDEX) ? window.CACAO_SEARCH_INDEX : [];
    var relRoot = document.documentElement.getAttribute("data-rel-root") || ".";
    var q = (query || "").toLowerCase().trim();
    var terms = q ? q.split(/\s+/) : [];
    var matches = items.filter(function(it) {
      if (!terms.length) return true;
      var hay = ((it.title || "") + " " + (it.domain || "") + " " +
        (it.kind || "") + " " + (it.summary || "")).toLowerCase();
      return terms.every(function(t) { return hay.indexOf(t) !== -1; });
    }).slice(0, 24);
    if (!matches.length) {
      searchRes.innerHTML = '<div class="cat-empty-note">No matching pages or reports.</div>';
      return;
    }
    searchRes.innerHTML = matches.map(function(it) {
      var href = relRoot.replace(/\/$/, "") + "/" + String(it.path || "").replace(/^\.\//, "");
      var sub = it.summary ? '<span class="drop-item-sub">' + escHtml(it.summary) + "</span>" : "";
      return '<a class="search-hit" href="' + escHtml(href) + '">' +
        "<div><strong>" + escHtml(it.title) + "</strong>" + sub + "</div>" +
        '<span class="search-hit-kind">' + escHtml(it.kind || "Page") + "</span></a>";
    }).join("");
  }

  function openSearch() {
    if (!searchModal) return;
    closeAllDropdowns(null);
    searchModal.classList.add("open");
    renderSearch(searchInput ? searchInput.value : "");
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }

  function closeSearch() {
    if (searchModal) searchModal.classList.remove("open");
  }

  if (searchOpen) searchOpen.addEventListener("click", openSearch);
  if (searchClose) searchClose.addEventListener("click", closeSearch);
  if (searchModal) {
    searchModal.addEventListener("click", function(ev) {
      if (ev.target === searchModal || ev.target.closest("a.search-hit")) closeSearch();
    });
  }
  if (searchInput) {
    searchInput.addEventListener("input", function() {
      renderSearch(searchInput.value);
    });
  }

  document.addEventListener("keydown", function(ev) {
    if (ev.key === "Escape") {
      closeAllDropdowns(null);
      closeSearch();
      document.body.classList.remove("sidebar-mobile-open");
    } else if (ev.key === "/" && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
      var tag = (document.activeElement && document.activeElement.tagName) || "";
      if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        ev.preventDefault();
        openSearch();
      }
    }
  });
})();
