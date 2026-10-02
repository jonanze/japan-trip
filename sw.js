// Offline cache for the Japan Trip app. The page is network-first (3 s timeout) so edits arrive when online,
// and falls back to the saved copy with no signal. Fonts and icons are cache-first.
var CACHE = "jp26-c62e3fa1f3";
var HOME = new URL("./", self.location).href;
var CORE = [HOME, "manifest.webmanifest", "apple-touch-icon.png"];
self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(CORE); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.map(function (k) {
      if (k === CACHE) return null;
      if (k.indexOf("jp26-") === 0) return caches.open(k).then(function (old) {
        // Carry font files across versions so they stay available offline
        return old.keys().then(function (rs) { return Promise.all(rs.map(function (r) {
          if (r.url.indexOf("fonts.g") < 0) return null;
          return old.match(r).then(function (res) { return caches.open(CACHE).then(function (c) { return c.put(r, res); }); });
        })); }).then(function () { return caches.delete(k); });
      });
      return null;
    }));
  }).then(function () { return self.clients.claim(); }));
});
function timeout(ms) { return new Promise(function (_, rej) { setTimeout(function () { rej(new Error("timeout")); }, ms); }); }
self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (req.mode === "navigate" || url.href === HOME) {
    e.respondWith(Promise.race([fetch(req), timeout(3000)]).then(function (res) {
      if (res && res.ok) { var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(HOME, copy); }); }
      return res;
    }).catch(function () { return caches.match(HOME).then(function (r) { return r || fetch(req); }); }));
    return;
  }
  if (url.origin === location.origin || url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") {
    e.respondWith(caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && (res.ok || res.type === "opaque")) { var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(req, copy); }); }
        return res;
      });
    }));
  }
});
