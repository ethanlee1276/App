/* Qellys Book — service worker.
 *
 * WHY THIS IS NETWORK-FIRST AND NOT CACHE-FIRST, which is the opposite of
 * the usual advice. This site's entire value is that its numbers are
 * current: a board showing last night's prices, in an app-looking window
 * with no address bar to hint that anything is wrong, is worse than a
 * board that fails to load. The normal PWA pattern — serve the cache,
 * refresh in the background — would do exactly that, and the user would
 * have no way to tell. A stale line is a bet at a price that no longer
 * exists.
 *
 * So the rules, in order of how much they matter:
 *
 *   1. /api/*        never touched. Sessions, account data, billing.
 *                    Caching an authenticated response is how one user
 *                    gets served another user's page.
 *   2. /data/*.json  never cached. This is every board, every price,
 *                    every record. Network or nothing.
 *   3. everything    network first, and the cache is only ever a
 *      else          FALLBACK for when the network fails — the shell, so
 *                    an offline launch shows the app and its own honest
 *                    empty states rather than the browser's dinosaur.
 *
 * The cache is therefore a courtesy, never a source of truth, and its
 * name must change whenever the shell does — `activate` deletes every
 * other cache, so a stale bundle cannot outlive a deploy.
 */

// THE VERSION IS NO LONGER TYPED. It used to be, with a comment telling
// whoever came next to bump it; that instruction was missed on v1 (two
// shell deploys served pre-redesign copies) and missed again on v3,
// which sat here through 2,149 lines of index.html, styles.css, app.js
// and visuals.js — including the 2026-08-19 fix for the phone drawer
// that would not open. Network-first means a healthy phone still gets
// fresh files; the cache only answers when a request fails, which on
// cellular it does, and one stale styles.css inside an installed PWA
// looks exactly like a bug that was never fixed.
//
// So server.py rewrites this line on the way out, with a hash of the
// SHELL list below. Change any cached file and the name changes by
// itself. The literal here is the value when the file is served by
// something else — a bare file server, a local checkout — and is kept
// ahead of the last typed one so that path is never a downgrade.
const VERSION = "qb-v4";

/* The shell only: enough to boot the app and render its own "no data
 * yet" states. Deliberately NOT the boards. */
const SHELL = [
  "/",
  "/index.html",
  "/css/styles.css",
  "/js/app.js",
  "/js/teams.js",
  "/js/visuals.js",
  "/vendor/apexcharts.min.js",
  "/favicon.svg",
  "/icon-192.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  // One miss must not fail the whole install — a renamed asset would
  // otherwise leave the worker permanently uninstallable and silently
  // turn the install prompt off.
  e.waitUntil(caches.open(VERSION).then((c) =>
    Promise.allSettled(SHELL.map((u) => c.add(u)))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== "qb-shared").map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                 // never touch writes
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // embeds are theirs
  if (url.pathname.startsWith("/api/")) return;     // authenticated: never
  if (url.pathname.startsWith("/data/")) return;    // live numbers: never

  // THE SHELL'S OWN KINDS, and nothing else. The first cut cached any
  // successful same-origin GET, which measured out as the whole venue
  // photo library landing in the cache the moment somebody scrolled a
  // board — unbounded growth on a phone, for pictures. Documents,
  // scripts, styles and the manifest are what an offline launch needs;
  // an image that does not load leaves a gap, which is survivable.
  const kind = req.destination;
  const keep = kind === "document" || kind === "script" ||
               kind === "style" || kind === "manifest" || kind === "";

  e.respondWith(
    fetch(req)
      .then((res) => {
        if (keep && res && res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("/index.html")))
  );
});

/* A SLIP SHARED IN (manifest share_target, 2026-10-24): the one post this
 * worker answers itself, in a listener of its own after the main one (which
 * leaves every write alone). The picture is kept for the page to collect
 * (app.js sharedSlipIn) and Ask opens; nothing goes to the server here. */
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "POST" || new URL(req.url).pathname !== "/share-slip") return;
  e.respondWith((async () => {
    try {
      const form = await req.formData();
      const file = form.get("slip");
      if (file && file.size && file.size <= 12 * 1024 * 1024 && /^image\//.test(file.type || "image/")) {
        const box = await caches.open("qb-shared");
        await box.put("/shared-slip", new Response(file, { headers: { "Content-Type": file.type || "image/jpeg" } }));
      }
    } catch (err) { /* Ask opens either way */ }
    return Response.redirect("/?shared=slip#ask", 303);
  })());
});

/* ALERTS (engine/pushalerts, 2026-10-24): tonight's picks are up, last
 * night is graded. The push itself is an empty, signed knock — no words
 * travel through Google's, Apple's or Mozilla's push service — so the
 * worker asks the site what to say. A push must always show something, so
 * if the site cannot be reached it still says the board has moved. A tap
 * opens the page the alert is about, on this site and nowhere else. The
 * badge is the white mark Android draws in the status bar (a colour icon
 * there is a blank white square). */
self.addEventListener("push", (e) => {
  e.waitUntil((async () => {
    let msg = { title: "Qellys Book", body: "The board has moved — open it for the latest.", url: "/", tag: "qb" };
    try {
      const sub = await self.registration.pushManager.getSubscription();
      const r = await fetch("/api/push/latest", {
        method: "POST", credentials: "omit", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: sub ? sub.endpoint : "" }) });
      if (r.ok) msg = Object.assign(msg, await r.json());
    } catch (err) { /* the plain line above */ }
    return self.registration.showNotification(String(msg.title).slice(0, 80), {
      body: String(msg.body || "").slice(0, 200), tag: String(msg.tag || "qb").slice(0, 64),
      icon: "/icon-192.png", badge: "/icon-badge-96.png", data: { url: msg.url || "/" } });
  })());
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  let url = self.location.origin + "/";
  try {
    const u = new URL((e.notification.data || {}).url || "/", self.location.origin);
    if (u.origin === self.location.origin) url = u.href;
  } catch (err) { /* home */ }
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
    const mine = wins.find((w) => w.url.startsWith(self.location.origin));
    if (mine) return mine.navigate(url).then((w) => (w || mine).focus()).catch(() => mine.focus());
    return self.clients.openWindow(url);
  }));
});
