(function () {
  var pollMs = 8000;
  var toggle = document.getElementById("jrc-messenger-toggle");
  var drawer = document.getElementById("jrc-messenger-drawer");
  if (!toggle || !drawer) return;
  var sessionId = drawer.dataset.sessionId || "";
  var afterId = 0;
  var timer = null;
  toggle.addEventListener("click", function () {
    drawer.classList.toggle("open");
    if (drawer.classList.contains("open")) poll();
  });
  function poll() {
    if (!sessionId) return;
    fetch("/api/messenger/poll?session_id=" + sessionId + "&after_id=" + afterId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok && data.messages && data.messages.length) {
          var box = document.getElementById("jrc-messenger-messages");
          if (box) {
            data.messages.forEach(function (m) {
              afterId = Math.max(afterId, m.id);
              var p = document.createElement("div");
              p.textContent = (m.username || "") + ": " + (m.body || "");
              box.appendChild(p);
            });
          }
        }
      })
      .catch(function () {});
    if (drawer.classList.contains("open")) timer = setTimeout(poll, pollMs);
  }
})();
