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
 * The cache is therefore a courtesy, never a source of truth. Bump
 * VERSION on any shell change; `activate` deletes every older cache, so
 * a stale bundle cannot outlive a deploy.
 */

const VERSION = "qb-v1";

/* The shell only: enough to boot the app and render its own "no data
 * yet" states. Deliberately NOT the boards. */
const SHELL = [
  "/",
  "/index.html",
  "/css/styles.css",
  "/js/app.js",
  "/js/teams.js",
  "/js/visuals.js",
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
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
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
