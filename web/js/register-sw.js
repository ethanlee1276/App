/* Register the service worker — the last thing on the page, and the
 * least important. Everything here is optional by design: the site works
 * identically with no worker at all, which is what makes it safe to
 * register and safe to fail.
 *
 * A SEPARATE FILE, not an inline block, so the Content-Security-Policy
 * can eventually drop 'unsafe-inline' from script-src without this being
 * the one thing holding it open.
 *
 * IT WILL DO NOTHING ON PLAIN http://, and that is correct. Service
 * workers need a secure context, so this is a no-op on the LAN address
 * and over Tailscale, and only comes alive once the site is behind TLS.
 * Guarded rather than assumed: `navigator.serviceWorker` is simply
 * undefined on an insecure origin, and reading `.register` off undefined
 * would throw on the last line of the page.
 *
 * ---------------------------------------------------------------------
 * WHY THIS ASKS FOR AN UPDATE INSTEAD OF WAITING TO BE OFFERED ONE.
 *
 * Registering is not the same as checking. A browser re-fetches sw.js on
 * a NAVIGATION, and an installed PWA on a phone barely navigates: it is
 * resumed, not opened. So a home-screen app can hold a shell for days
 * after the fix it is missing went live, and sw.js's own header records
 * what that looks like from the outside — "one stale styles.css inside
 * an installed PWA looks exactly like a bug that was never fixed."
 *
 * That is not hypothetical here. The phone drawer that dimmed the screen
 * and did not open was fixed on 2026-08-19, and was reported as still
 * happening afterwards. Whatever the delivery path turns out to be, a
 * client that never goes looking cannot be the one to notice.
 *
 * Hashing the worker's name (server.py) decided WHAT a new shell is
 * called. This decides WHEN the phone goes and asks.
 *
 * THE RELOAD WAITS FOR THE BACKGROUND. A new worker claims its clients
 * immediately, but the page in front of the reader is still running the
 * CSS and JS it loaded with — current only after a reload. Reloading
 * under a thumb mid-scroll is its own defect, so the refresh is deferred
 * until the app is hidden: the reader is handed a fresh shell the next
 * time they come back, and never watches one arrive.
 *
 * UNLESS NOTHING WOULD BE LOST, OR IT NEVER RUNS (2026-10-26). Ethan's
 * phone kept a My Bets clash that had been fixed for hours: the installed
 * app opens on the copy it kept, the new version arrives a moment later,
 * and a phone FREEZES a page it puts away, so the reload "when hidden"
 * often never ran — the old code lived on, session after session. Now:
 *   - a new version that arrives before the reader has touched the page
 *     (a launch, in practice) takes its place at once;
 *   - one that arrives after says so — a pill to tap — and still reloads
 *     when the app is put away;
 *   - coming back to a page a new version replaced reloads it right there.
 */
(function () {
  if (!("serviceWorker" in navigator)) return;

  // Don't re-ask on every app switch. Long enough that flipping between
  // apps costs nothing, short enough that a deploy reaches a phone the
  // same session it is looked at.
  var CHECK_MS = 15 * 60 * 1000;
  var lastCheck = 0;
  var reg = null;
  var stale = false;      // a newer shell is cached; this page is not it
  var reloading = false;  // one reload, ever — never a loop
  // A page that opened with no worker is claimed by the first one: that is
  // an install, not an update, and this page is already the new shell.
  var hadWorker = !!navigator.serviceWorker.controller;

  function check() {
    var now = Date.now();
    if (!reg || now - lastCheck < CHECK_MS) return;
    lastCheck = now;
    // A failed update check is a no-op, exactly like a failed register.
    try { reg.update(); } catch (e) {}
  }

  // Has the reader done anything on this page yet? Until they have, a new
  // version can take its place at once: nothing of theirs is lost.
  var touched = false;
  ["pointerdown", "keydown", "wheel"].forEach(function (t) {
    window.addEventListener(t, function () { touched = true; }, { capture: true, passive: true });
  });

  function reloadNow() {
    if (reloading) return;
    reloading = true;
    location.reload();
  }

  function refreshWhenHidden() {
    if (!stale || document.visibilityState !== "hidden") return;
    reloadNow();
  }

  // Touched already: say a new version is here and let them pick the moment.
  function offer() {
    if (!document.body || document.getElementById("qb-update")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.id = "qb-update";
    b.className = "tf-toast upd-pill";
    b.textContent = "A new version is ready \u2014 tap to refresh";
    b.addEventListener("click", reloadNow);
    document.body.appendChild(b);
  }

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").then(function (r) {
      reg = r;
      lastCheck = Date.now();   // registering just did the fetch
      // THE INSTALLED APP KEEPS ITS OWN COPY (sw.js "app-mode"): a Home
      // Screen app, the Play build or the iOS shell asks the worker to keep
      // every file of this version and to open from it. A browser tab does
      // not ask, so a one-time visitor downloads only what they open.
      var app = (typeof QB_STORE_APP !== "undefined" && QB_STORE_APP) || navigator.standalone === true;
      try { app = app || matchMedia("(display-mode: standalone), (display-mode: fullscreen)").matches; } catch (e) {}
      if (app) {
        navigator.serviceWorker.ready.then(function (ready) {
          if (ready.active) ready.active.postMessage({ type: "app-mode" });
        });
      }
    }).catch(function () {
      /* A failed registration is not a broken site. Swallowed on purpose:
         the alternative is an uncaught rejection in the console of every
         page load on a machine that cannot support workers, which trains
         everyone to ignore the console — and the console is where the
         render sweep looks for real faults. */
    });
  });

  // Resuming a home-screen app is this platform's version of opening it,
  // and it is the only moment a phone reliably gives us.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      // Back on a page a new version replaced while it was away (the reload
      // "when hidden" does not run on a page the phone froze).
      if (stale) { reloadNow(); return; }
      // Coming back is a fresh start: a version that lands before the
      // reader's first touch takes this page's place at once.
      touched = false;
      check();
    } else refreshWhenHidden();
  });

  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (!hadWorker) { hadWorker = true; return; }
    stale = true;
    // app.js's rooms read this: a room fetched now would be the new
    // version's, so a page asked for on this one reloads instead (loadRoom).
    // Its crash note reads it too: a fault on a stale page reloads.
    window.QB_STALE = true;
    if (!touched && document.visibilityState === "visible") { reloadNow(); return; }
    offer();
    refreshWhenHidden();
  });
})();
