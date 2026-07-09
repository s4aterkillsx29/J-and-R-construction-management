/* Mobile SPA shell stub — bottom nav hooks */
(function () {
  document.addEventListener("DOMContentLoaded", function () {
    var nav = document.querySelector(".mobile-bottom-nav");
    if (!nav) return;
    nav.querySelectorAll("[data-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tab = btn.getAttribute("data-tab");
        document.querySelectorAll("[data-mobile-panel]").forEach(function (p) {
          p.hidden = p.getAttribute("data-mobile-panel") !== tab;
        });
      });
    });
  });
})();
