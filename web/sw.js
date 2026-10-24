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
  "/js/boot.js",
  "/js/app.js",
  "/js/teams.js",
  "/js/teams_mlb.js",
  "/js/teams_nba.js",
  "/js/teams_wnba.js",
  "/js/teams_nhl.js",
  "/js/visuals.js",
  "/js/register-sw.js",
  "/vendor/apexcharts.min.js",
  "/favicon.svg",
  "/icon-192.png",
  "/icon-badge-96.png",
  "/manifest.webmanifest",
];

/* THE REST OF THE APP'S CODE, the pages it loads the first time they open.
 * Cached with the shell only on a device running the installed app (below),
 * so a one-time visitor on cellular never downloads every page; and in the
 * version's hash (server.py), so a change to any of them is a new version. */
const LAZY = [
  "/js/fantasy.js", "/css/fantasy.css", "/js/record.js", "/js/detail.js", "/js/account.js", "/js/more.js", "/js/memes.js", "/css/memes.css", "/js/extras.js", "/css/extras.css", "/js/social.js", "/css/social.css",
  "/js/gamecast.js", "/css/gamecast.css", "/js/hoopscast.js", "/css/hoopscast.css",
  "/js/rinkcast.js", "/css/rinkcast.css", "/js/slip.js", "/css/slip.css",
  "/js/report.js", "/css/report.css", "/js/carrychart.js", "/css/carrychart.css",
  "/js/fantasyweek.js", "/js/lab.js", "/css/lab.css",
  "/js/chart-hoops.js", "/js/chart-kicks.js", "/js/chart-matchup.js", "/js/chart-mlb.js",
  "/js/chart-nhl.js", "/js/chart-role.js", "/js/chart-ufc.js",
];

/* THE INSTALLED APP OPENS FROM ITS OWN COPY (Ethan, 2026-10-24: "build
 * everything" — docs/IDEAS.md's first). The rule above, network first, is
 * about PRICES and stays theirs: /data/ and /api/ are never cached. The
 * app's own CODE is another matter. An installed app on a weak signal used
 * to wait for the network before it could show anything; a store app opens
 * from what it has. So once the page says it is the installed app
 * (register-sw.js posts "app-mode": a Home Screen app, the Play build or the
 * iOS shell), this device keeps every file of the app, shell and pages,
 * under this version's name, and serves them from there.
 *
 * ONE VERSION AT A TIME, never file by file: the cache is filled whole when
 * a version installs and nothing in it is refreshed piecemeal, so a new
 * app.js can never meet an old page script. A deploy renames the version
 * (server.py hashes SHELL and LAZY), the phone fetches the new worker within
 * fifteen minutes or on its next launch, the new one fills its own cache,
 * and register-sw.js reloads the page the next time it is out of sight. */
const MODE_BOX = "qb-mode";
let APP_MODE = null;                       // read from MODE_BOX on first use
async function appMode() {
  if (APP_MODE === null) {
    try { APP_MODE = !!(await (await caches.open(MODE_BOX)).match("/app")); } catch (err) { APP_MODE = false; }
  }
  return APP_MODE;
}
const SHELL_PATHS = new Set(SHELL);
const LAZY_PATHS = new Set(LAZY);
/* The next version's copies are fetched fresh, past the browser's own cache. */
function fill(box, urls) {
  return Promise.allSettled(urls.map((u) => box.add(new Request(u, { cache: "reload" }))));
}
async function fromThisVersion(req, url) {
  const box = await caches.open(VERSION);
  const doc = url.pathname === "/" || url.pathname === "/index.html";
  const hit = await box.match(doc ? url.pathname : req, { ignoreSearch: doc });
  if (hit) return hit;
  const res = await fetch(req);
  if (res && res.ok && res.type === "basic") box.put(doc ? url.pathname : req, res.clone()).catch(() => {});
  return res;
}
self.addEventListener("message", (e) => {
  if (!e.data || e.data.type !== "app-mode") return;
  e.waitUntil((async () => {
    await (await caches.open(MODE_BOX)).put("/app", new Response("1"));
    APP_MODE = true;
    const box = await caches.open(VERSION);
    const have = new Set((await box.keys()).map((r) => new URL(r.url).pathname));
    await fill(box, [...SHELL, ...LAZY].filter((u) => !have.has(u)));
  })());
});

self.addEventListener("install", (e) => {
  // One miss must not fail the whole install — a renamed asset would
  // otherwise leave the worker permanently uninstallable and silently
  // turn the install prompt off.
  e.waitUntil((async () => {
    const box = await caches.open(VERSION);
    await fill(box, (await appMode()) ? [...SHELL, ...LAZY] : SHELL);
  })().then(() => self.skipWaiting()));
});

/* Boxes that are not a version: the app-mode mark, a slip mid-share, the
 * record's offline copy. */
const KEEP_BOXES = [MODE_BOX, "qb-shared", "qb-offline"];

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION && !KEEP_BOXES.includes(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                 // never touch writes
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // embeds are theirs
  if (url.pathname.startsWith("/api/")) return;     // authenticated: never
  if (url.pathname.startsWith("/data/")) return;    // live numbers: never

  // The app's own files: from this version's copy on the installed app,
  // network first everywhere else (fromThisVersion, above).
  if (SHELL_PATHS.has(url.pathname) || LAZY_PATHS.has(url.pathname)) {
    e.respondWith(appMode().then((on) => (on ? fromThisVersion(req, url) : networkFirst(req, true))));
    return;
  }

  // THE SHELL'S OWN KINDS, and nothing else. The first cut cached any
  // successful same-origin GET, which measured out as the whole venue
  // photo library landing in the cache the moment somebody scrolled a
  // board — unbounded growth on a phone, for pictures. Documents,
  // scripts, styles and the manifest are what an offline launch needs;
  // an image that does not load leaves a gap, which is survivable.
  const kind = req.destination;
  const keep = kind === "document" || kind === "script" ||
               kind === "style" || kind === "manifest" || kind === "";

  e.respondWith(networkFirst(req, keep));
});

/* Network first, the cache only when the network fails: everything that is
 * not the installed app's own code. */
function networkFirst(req, keep) {
  return fetch(req)
    .then((res) => {
      if (keep && res && res.ok && res.type === "basic") {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    })
    .catch(() => caches.match(req).then((hit) => hit || caches.match("/index.html")));
}

/* THE RECORD, OFFLINE (docs/IDEAS.md). The record is free and it is a
 * history, not a price: the one /data/ file worth having with no signal.
 * Network first like every board; each good answer is kept, and when the
 * network fails the kept copy answers with the moment it was kept
 * (X-QB-Offline-Copy), which the Record page says out loud. The main
 * listener above leaves /data/ alone; this one answers only these two. */
const OFFLINE_COPIES = new Set(["/data/record.json", "/data/record_head.json"]);
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !OFFLINE_COPIES.has(url.pathname)) return;
  const kept = () => caches.open("qb-offline").then((c) => c.match(url.pathname));
  e.respondWith(fetch(req).then((res) => {
    if (res && res.ok) {
      res.clone().blob().then((b) => caches.open("qb-offline").then((c) => c.put(url.pathname, new Response(b, {
        headers: { "Content-Type": "application/json", "X-QB-Offline-Copy": new Date().toISOString() } })))).catch(() => {});
      return res;
    }
    // The box down (a 5xx) reads like no signal; a 404 is "no record yet".
    return res && res.status >= 500 ? kept().then((hit) => hit || res) : res;
  }).catch(() => kept().then((hit) => hit || Response.error())));
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
