(function () {
  "use strict";
  var modal = document.getElementById("jrc-admin-modal");
  var body = document.getElementById("jrc-admin-modal-body");
  var titleEl = document.getElementById("jrc-admin-modal-title");
  if (!modal || !body) return;

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function closeModal() {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    body.innerHTML = "";
  }

  function openModal() {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
  }

  modal.querySelectorAll("[data-jrc-modal-close]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  function apiAction(userId, action, extra) {
    return fetch("/api/admin/user-popup/" + userId + "/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ action: action }, extra || {})),
    }).then(function (r) { return r.json(); });
  }

  function renderUserPopup(data) {
    var u = data.user;
    titleEl.textContent = u.username + " — Admin Actions";
    var sessions = (data.sessions || [])
      .map(function (s) {
        return "<li>" + esc(s.ip_address) + " · " + esc(s.last_seen) + "</li>";
      })
      .join("");
    body.innerHTML =
      "<div class='jrc-popup-field'><label>Account</label><div>" +
      esc(u.username) + " · " + esc(u.role) + " · " +
      (u.active ? "Active" : "Inactive") + "</div></div>" +
      "<div class='jrc-popup-field'><label>Contact</label><div>" +
      esc(u.email || "—") + " · " + esc(u.phone || "—") + "</div></div>" +
      "<div class='jrc-popup-field'><label>Change role</label>" +
      "<select id='jrc-popup-role'>" +
      ["admin", "manager", "worker", "helper", "viewer", "customer"].map(function (r) {
        return "<option value='" + r + "'" + (r === u.role ? " selected" : "") + ">" + r + "</option>";
      }).join("") +
      "</select></div>" +
      "<div class='jrc-popup-field'><label>Broadcast to all users</label>" +
      "<textarea id='jrc-popup-broadcast' rows='2' placeholder='Office announcement…'></textarea></div>" +
      (sessions ? "<div class='jrc-popup-field'><label>Online sessions</label><ul>" + sessions + "</ul></div>" : "") +
      "<div class='jrc-popup-actions'>" +
      "<button type='button' class='btn' id='jrc-popup-save-role'>Save role</button>" +
      "<button type='button' class='btn btn2' id='jrc-popup-toggle-active'>" +
      (u.active ? "Deactivate" : "Activate") + "</button>" +
      "<button type='button' class='btn warn' id='jrc-popup-end-sessions'>End sessions</button>" +
      "<button type='button' class='btn' id='jrc-popup-broadcast-btn'>Send broadcast</button>" +
      "<a class='btn btn2' href='/admin/user/" + u.id + "'>Full edit</a>" +
      "</div>" +
      "<p id='jrc-popup-status' class='muted'></p>";

    document.getElementById("jrc-popup-save-role").addEventListener("click", function () {
      var role = document.getElementById("jrc-popup-role").value;
      apiAction(u.id, "set_role", { role: role }).then(showStatus);
    });
    document.getElementById("jrc-popup-toggle-active").addEventListener("click", function () {
      apiAction(u.id, "toggle_active").then(function (res) {
        showStatus(res);
        if (res.ok) loadUser(u.id);
      });
    });
    document.getElementById("jrc-popup-end-sessions").addEventListener("click", function () {
      if (!confirm("End all sessions for " + u.username + "?")) return;
      apiAction(u.id, "end_sessions").then(showStatus);
    });
    document.getElementById("jrc-popup-broadcast-btn").addEventListener("click", function () {
      var msg = document.getElementById("jrc-popup-broadcast").value.trim();
      if (!msg) return alert("Message required");
      apiAction(u.id, "broadcast", { body: msg }).then(showStatus);
    });
  }

  function showStatus(res) {
    var el = document.getElementById("jrc-popup-status");
    if (!el) return;
    el.textContent = res.ok ? (res.message || "Done") : (res.error || "Failed");
  }

  function loadUser(userId) {
    fetch("/api/admin/user-popup/" + userId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          alert(data.error || "Load failed");
          return;
        }
        renderUserPopup(data);
        openModal();
      })
      .catch(function () { alert("Load failed"); });
  }

  function resolveUserId(btn) {
    var uid = btn.getAttribute("data-user-id");
    if (uid) return parseInt(uid, 10);
    var uname = btn.getAttribute("data-username");
    if (!uname) return null;
    var row = btn.closest("tr");
    if (!row) return null;
    var link = row.querySelector("a[href*='/admin/user/']");
    if (link) {
      var m = link.getAttribute("href").match(/\/admin\/user\/(\d+)/);
      if (m) return parseInt(m[1], 10);
    }
    return null;
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".jrc-admin-popup-btn");
    if (!btn) return;
    e.preventDefault();
    var userId = resolveUserId(btn);
    if (!userId) {
      alert("User ID not found — use Admin Hub user table.");
      return;
    }
    loadUser(userId);
  });
})();
