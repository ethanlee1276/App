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
 */
(function () {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () {
      /* A failed registration is not a broken site. Swallowed on purpose:
         the alternative is an uncaught rejection in the console of every
         page load on a machine that cannot support workers, which trains
         everyone to ignore the console — and the console is where the
         render sweep looks for real faults. */
    });
  });
})();
