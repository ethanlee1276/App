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

  function check() {
    var now = Date.now();
    if (!reg || now - lastCheck < CHECK_MS) return;
    lastCheck = now;
    // A failed update check is a no-op, exactly like a failed register.
    try { reg.update(); } catch (e) {}
  }

  function refreshWhenHidden() {
    if (!stale || reloading || document.visibilityState !== "hidden") return;
    reloading = true;
    location.reload();
  }

  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").then(function (r) {
      reg = r;
      lastCheck = Date.now();   // registering just did the fetch
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
    if (document.visibilityState === "visible") check();
    else refreshWhenHidden();
  });

  navigator.serviceWorker.addEventListener("controllerchange", function () {
    stale = true;
    refreshWhenHidden();
  });
})();
