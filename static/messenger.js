(function () {
  "use strict";
  var POLL_MS = 6000;
  var root = document.getElementById("jrc-messenger-root") || document.getElementById("jrc-mobile-chat");
  if (!root) return;

  var username = root.dataset.username || "";
  var isMobile = root.dataset.mobile === "1";
  var toggle = document.getElementById("jrc-messenger-toggle");
  var drawer = document.getElementById("jrc-messenger-drawer");
  var closeBtn = document.getElementById("jrc-messenger-close");
  var sessionsEl = document.getElementById("jrc-messenger-sessions");
  var threadEl = document.getElementById("jrc-messenger-thread");
  var messagesEl = document.getElementById("jrc-messenger-messages");
  var threadTitle = document.getElementById("jrc-messenger-thread-title");
  var backBtn = document.getElementById("jrc-messenger-back");
  var compose = document.getElementById("jrc-messenger-compose");
  var input = document.getElementById("jrc-messenger-input");
  var badge = document.getElementById("jrc-messenger-badge");

  var sessionId = null;
  var afterId = 0;
  var pollTimer = null;
  var sessions = [];

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function openDrawer() {
    if (!drawer) return;
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    loadSessions();
  }

  function closeDrawer() {
    if (!drawer) return;
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    stopPoll();
  }

  if (toggle) toggle.addEventListener("click", openDrawer);
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);

  if (backBtn) {
    backBtn.addEventListener("click", function () {
      sessionId = null;
      afterId = 0;
      if (threadEl) threadEl.hidden = !isMobile;
      if (sessionsEl) sessionsEl.hidden = false;
      stopPoll();
      if (isMobile) loadSessions();
    });
  }

  function stopPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function schedulePoll() {
    stopPoll();
    if (!sessionId) return;
    pollTimer = setTimeout(function () {
      pollMessages().finally(schedulePoll);
    }, POLL_MS);
  }

  function updateBadge(total) {
    if (!badge) return;
    if (total > 0) {
      badge.hidden = false;
      badge.textContent = total > 99 ? "99+" : String(total);
    } else {
      badge.hidden = true;
    }
  }

  function loadSessions() {
    return fetch("/api/messenger/sessions")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) return;
        sessions = data.sessions || [];
        updateBadge(data.unread_total || 0);
        renderSessions();
        if (isMobile && sessions.length && !sessionId) {
          openSession(sessions[0].id, sessions[0].title);
        }
      })
      .catch(function () {});
  }

  function renderSessions() {
    if (!sessionsEl) return;
    if (!sessions.length) {
      sessionsEl.innerHTML = "<p class='muted' style='padding:12px'>No chat sessions yet.</p>";
      return;
    }
    sessionsEl.innerHTML = sessions
      .map(function (s) {
        var unread = s.unread > 0
          ? "<span class='jrc-msg-unread-dot'>" + s.unread + "</span>"
          : "";
        return (
          "<button type='button' class='jrc-msg-session-item' data-id='" + s.id + "'>" +
          "<div class='title'><span>" + esc(s.title) + "</span>" + unread + "</div>" +
          "<div class='meta'>" + esc(s.channel_type) + " · " + esc(s.updated_at) + "</div>" +
          "</button>"
        );
      })
      .join("");
    sessionsEl.querySelectorAll(".jrc-msg-session-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = parseInt(btn.getAttribute("data-id"), 10);
        var sess = sessions.find(function (x) { return x.id === id; });
        openSession(id, sess ? sess.title : "Chat");
      });
    });
  }

  function openSession(id, title) {
    sessionId = id;
    afterId = 0;
    if (messagesEl) messagesEl.innerHTML = "";
    if (threadTitle) threadTitle.textContent = title || "Chat";
    if (sessionsEl) sessionsEl.hidden = true;
    if (threadEl) threadEl.hidden = false;
    fetch("/api/messenger/mark-read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: id }),
    }).catch(function () {});
    pollMessages().then(schedulePoll);
  }

  function renderMessage(m) {
    var mine = (m.username || "") === username;
    var div = document.createElement("div");
    div.className = "jrc-msg-bubble " + (mine ? "mine" : "theirs");
    var admin = m.is_admin_broadcast ? " <span class='jrc-msg-unread-dot'>ADMIN</span>" : "";
    div.innerHTML =
      "<div class='who'>" + esc(m.username) + admin + "</div>" +
      "<div class='body'>" + esc(m.body).replace(/\n/g, "<br>") + "</div>" +
      "<div class='when'>" + esc(m.created_at) + "</div>";
    return div;
  }

  function pollMessages() {
    if (!sessionId || !messagesEl) return Promise.resolve();
    return fetch(
      "/api/messenger/poll?session_id=" + sessionId + "&after_id=" + afterId
    )
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok || !data.messages) return;
        data.messages.forEach(function (m) {
          afterId = Math.max(afterId, m.id);
          messagesEl.appendChild(renderMessage(m));
        });
        if (data.messages.length) {
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      })
      .catch(function () {});
  }

  if (compose) {
    compose.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!sessionId || !input) return;
      var body = (input.value || "").trim();
      if (!body) return;
      fetch("/api/messenger/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, body: body }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            input.value = "";
            return pollMessages();
          }
          alert(data.error || "Send failed");
        })
        .catch(function () { alert("Send failed"); });
    });
  }

  loadSessions();
  setInterval(loadSessions, POLL_MS * 2);

  if (isMobile) {
    if (threadEl) threadEl.hidden = false;
    if (sessionsEl) sessionsEl.hidden = false;
  }
})();
