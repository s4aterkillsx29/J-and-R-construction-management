/* Mobile outbox client — IndexedDB queue */
(function () {
  var DB_NAME = "jrc_mobile_outbox";
  var STORE = "pending_outbox";
  window.jrcMobileOutbox = {
    enqueue: function (item) {
      return new Promise(function (resolve) {
        var req = indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = function (e) {
          e.target.result.createObjectStore(STORE, { keyPath: "client_id" });
        };
        req.onsuccess = function (e) {
          var db = e.target.result;
          var tx = db.transaction(STORE, "readwrite");
          tx.objectStore(STORE).put(item);
          tx.oncomplete = function () { resolve(true); };
        };
      });
    },
    flush: function () {
      if (!navigator.onLine) return Promise.resolve([]);
      return fetch("/api/mobile/outbox/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: [] }),
      }).then(function (r) { return r.json(); });
    },
  };
  window.addEventListener("online", function () {
    if (window.jrcMobileOutbox) window.jrcMobileOutbox.flush();
  });
})();
