/* Decided BEFORE first paint, or the full masthead renders and then
   collapses — a 790px jump on every load. A file rather than an inline
   <script> since the site audit (2026-09-24, M-4): the content policy
   refuses inline script, and this is loaded in <head>, blocking, exactly
   where the inline block ran. */
try {
  if (localStorage.getItem("qb-seen-intro"))
    document.documentElement.classList.add("intro-seen");
} catch (e) {}

/* THE FIRST SCREEN DOES NOT JUMP (2026-10-24, measured on a mid phone: the
   page moved 0.42 of a screen while it loaded — Google calls 0.1 good).
   Until app.js has drawn the real page, the markup's placeholder board is
   kept invisible and a quiet shimmer holds its place, the way an app's
   launch screen does; app.js lifts `booting` the frame after it draws.
   styles.css reveals the page on its own after a few seconds, so a script
   that never arrives can never leave it blank. */
document.documentElement.classList.add("booting");
/* An iPhone Home Screen app (Safari's own standalone flag): it wears the
   iOS capsule tab bar, like the store's iOS build (styles.css). */
if (navigator.standalone === true) document.documentElement.classList.add("ios-home");

/* THE STORE APP (Ethan, 2026-10-24: "do both from my call ... we just need
   it to work with the app store"). The same site runs in the Play build (a
   Trusted Web Activity started at ?app=play, which Chrome also announces
   with an android-app:// referrer) and the iOS shell (Capacitor, its user
   agent ending "QellysApp/<version> (ios)"). In there the page leaves out
   what a store reviewer reads as facilitating wagering — the Bet it and
   Tail it sportsbook links (Play's gambling policy; Apple 5.3.4) — or as
   someone else's property — league logos and player photos (Apple 5.2.1,
   4.1) — and the meme-coin page. Our own drawn helmets, caps and team-
   colour marks stand in, the same art every photo already falls back to.
   The website keeps all of it. ?app=web forgets the app on this phone.

   The Android app shares Chrome's storage with the browser, so a stored
   "play" counts only in an app window: a Chrome tab on the same phone is
   the website. Checkout: Apple's US storefront allows the link out to buy
   (3.1.1(a)); Play needs the US external-links enrolment first
   (docs/APP_STORES.md), so the Play build sells nothing until it is on. */
var QB_STORE_APP = "";
var QB_STORE_CHECKOUT = { ios: true, play: false };
try {
  var qbQ = (location.search.match(/[?&]app=([a-z]+)/) || [])[1] || "";
  var qbUA = navigator.userAgent || "";
  var qbGot = /^(play|ios)$/.test(qbQ) ? qbQ
    : (document.referrer || "").indexOf("android-app://com.qellysbook.app") === 0 ? "play"
    : /QellysApp\/[\d.]+ \(ios\)/.test(qbUA) ? "ios" : "";
  if (qbQ === "web") localStorage.removeItem("qb-store-app");
  else if (qbGot) localStorage.setItem("qb-store-app", qbGot);
  else qbGot = localStorage.getItem("qb-store-app") || "";
  if (qbGot === "play" && qbQ !== "play"
      && !matchMedia("(display-mode: standalone), (display-mode: fullscreen), (display-mode: minimal-ui)").matches)
    qbGot = "";
  QB_STORE_APP = qbGot;
  if (qbGot) {
    document.documentElement.classList.add("store-app", "store-" + qbGot);
    if (!QB_STORE_CHECKOUT[qbGot]) document.documentElement.classList.add("store-nobuy");
  }
} catch (e) {}

/* THE SCREEN'S LAST STRIP (Ethan, 2026-10-28, from his iPhone: "Fix this
   black bar": the menu and its shade stopping 62pt above the bottom of the
   screen over a bare strip). iOS 26 can open a Home Screen app with its
   page a status bar shorter than the screen until it settles (innerHeight
   = the screen less the status bar), and everything pinned to the bottom
   stops that far up. On an iPhone, where the app always fills the screen,
   the shortfall is measured and handed to styles.css as --vgap, which the
   layers pinned to the bottom reach down by. It is measured again on every
   resize, and once iOS catches up it is gone; while one stands it is also
   checked every second, so a settle that fires no event still takes it
   away. A shortfall over 100px is no status bar (the keyboard, a pinch
   zoom) and is left alone. The iOS build
   is known by its own user agent here, not the remembered QB_STORE_APP: a
   Safari tab that once opened ?app=ios remembers that too, and a tab's own
   bars are no shortfall. */
try {
  (function () {
    var ua = navigator.userAgent || "";
    if (!/iPhone/.test(ua) || !(navigator.standalone === true || /QellysApp\/[\d.]+ \(ios\)/.test(ua))) return;
    var root = document.documentElement, last = -1, poll = 0;
    function vgap() {
      var s = window.screen;
      var full = innerWidth < innerHeight ? Math.max(s.width, s.height) : Math.min(s.width, s.height);
      var gap = Math.round(full - innerHeight);
      if (!(gap > 0 && gap <= 100)) gap = 0;
      if (gap === last) return;
      last = gap;
      if (gap) root.style.setProperty("--vgap", gap + "px");
      else root.style.removeProperty("--vgap");
      clearInterval(poll);
      if (gap) poll = setInterval(vgap, 1000);
    }
    vgap();
    addEventListener("resize", vgap);
    addEventListener("orientationchange", vgap);
    addEventListener("pageshow", vgap);
    addEventListener("load", vgap);
    if (window.visualViewport) visualViewport.addEventListener("resize", vgap);
  })();
} catch (e) {}

/* THE IPHONE DUO'S SIDE STRIP (Ethan, 2026-10-29, his closed iPhone Duo
   with the tab bar circled and an arrow to the black strip beside the
   clock: "move this bar ... to the right side ... only for the iPhone
   Duo"). An app built with the iOS 27.1 SDK reaches the screen's edge, and
   the strip beside the clock and camera comes to the page as a safe-area
   inset on that side alone (84pt, by developers' reports), where the
   system stands its own bars on end under the clock. When one side's inset
   is a strip that wide and the other side has none, the bar moves into it:
   html.side-rail (and side-rail-left when the strip is on the left, as in
   Split View), its width in --strip-w (styles.css). An iPhone on its side
   insets both sides alike and keeps its bar at the foot; an app built with
   an older SDK is never given the strip, so nothing moves there. Measured
   again whenever the window changes: the Duo opens and closes.

   OPEN ON ITS SIDE, TOO (Ethan, 2026-10-29: the tab bar "on the side like
   how we do in the folded view"; Apple's guide for the Duo: "The controls
   remain on the side when the device opens in landscape"). A finger on a
   wide, short screen, the open Duo on its side (951 by 543 to 589 in
   Safari, 890 by 626 by Apple's pixels, 910 by 703 as a Home Screen app on
   Ethan's own) or a small tablet held the same way, is html.duo-side: the bar stands on the right edge whether or not
   iOS gives the page the strip (a Home Screen app is still drawn beside it
   today), the strip's own width when it does, 84px when not. */
try {
  (function () {
    var root = document.documentElement, probe = null, last = "";
    var DUO_SIDE = "(pointer: coarse) and (min-width: 761px) and (max-width: 1060px) and (min-height: 500px) and (max-height: 760px) and (min-aspect-ratio: 5/4)";
    function rail() {
      if (!document.body) return;
      if (!probe) {
        probe = document.createElement("div");
        probe.setAttribute("aria-hidden", "true");
        probe.style.cssText = "position:fixed;top:0;left:0;width:0;height:0;visibility:hidden;pointer-events:none;"
          + "padding-left:env(safe-area-inset-left,0px);padding-right:env(safe-area-inset-right,0px)";
        document.body.appendChild(probe);
      }
      var cs = getComputedStyle(probe);
      var l = parseFloat(cs.paddingLeft) || 0, r = parseFloat(cs.paddingRight) || 0;
      var duo = !!(window.matchMedia && matchMedia(DUO_SIDE).matches);
      var side = r >= 60 && l <= 16 ? "right" : l >= 60 && r <= 16 ? "left" : duo ? "right" : "";
      var w = side === "left" ? l : r >= 60 ? r : 84;
      var key = side + (side ? Math.round(w) : "") + (duo ? "+duo" : "");
      if (key === last) return;
      last = key;
      root.classList.toggle("duo-side", duo);
      root.classList.toggle("side-rail", !!side);
      root.classList.toggle("side-rail-left", side === "left");
      // The bar in the system's own strip (the clock above it), or drawn beside it.
      root.classList.toggle("side-rail-inset", !!side && (side === "left" ? l : r) >= 60);
      if (side) root.style.setProperty("--strip-w", Math.round(w) + "px");
      else root.style.removeProperty("--strip-w");
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", rail);
    else rail();
    addEventListener("resize", rail);
    addEventListener("orientationchange", rail);
    addEventListener("pageshow", rail);
  })();
} catch (e) {}

/* The net under the art rule. visuals.js asks for no league logo or player
   photo in the app, but a picture can arrive by a road it does not cover
   (a board's own image field, a chart's photo). Any <img> from another
   host is taken out the moment it lands, before it paints, and the drawn
   mark beneath it shows — exactly what a photo that fails to load does. */
if (QB_STORE_APP && window.MutationObserver) {
  (function () {
    function foreign(img) {
      var s = img.getAttribute("src") || "";
      if (!s || /^(data:|blob:)/.test(s)) return false;
      try { return new URL(s, location.href).origin !== location.origin; } catch (e) { return true; }
    }
    function check(n) {
      if (n.nodeType !== 1) return;
      if (n.tagName === "IMG") { if (foreign(n)) n.remove(); return; }
      if (n.getElementsByTagName) {
        var imgs = n.getElementsByTagName("img");
        for (var i = imgs.length - 1; i >= 0; i--) if (foreign(imgs[i])) imgs[i].remove();
      }
    }
    new MutationObserver(function (rs) {
      for (var i = 0; i < rs.length; i++) {
        var r = rs[i];
        if (r.type === "attributes") check(r.target);
        else for (var j = 0; j < r.addedNodes.length; j++) check(r.addedNodes[j]);
      }
    }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["src"] });
  })();
}

/* THE PICKS ASKED FOR WITH THE PAGE (2026-10-25, Lighthouse on a slow phone
   network). The board's light copy (engine/lightboard) was asked for only
   once app.js had arrived and run, so the picks landed a download after the
   page. The league this visit opens is known now (app.js startSport's
   rules: ?sport=, the kept league, the season), so its light copy is asked
   for here and app.js's paidFetch takes this answer instead of asking
   again. Only at the site's root: a clean path names its own league and
   page, and a wrong guess would cost a download nothing uses. */
var QB_EARLY_BOARD = null;
try {
  (function () {
    if (!window.fetch || !/^\/(index\.html)?$/.test(location.pathname) || /[?&]static\b/.test(location.search)) return;
    var light = { nfl: "recommendations_picks.json", mlb: "mlb_recommendations_picks.json", nba: "nba_picks.json",
                  wnba: "wnba_picks.json", cfb: "cfb_picks.json", nhl: "nhl_picks.json" };
    var sport = (location.search.match(/[?&]sport=([a-z]+)/) || [])[1];
    if (!light[sport]) {
      var kept = null;
      try { kept = localStorage.getItem("qb.sport"); } catch (e) {}
      var d = new Date(), md = (d.getMonth() + 1) * 100 + d.getDate();
      sport = light[kept] ? kept : md >= 901 || md < 215 ? "nfl" : md < 326 ? "nba" : "mlb";
    }
    var name = light[sport];
    var ask = fetch("/api/board/" + name);
    ask.catch(function () {});
    QB_EARLY_BOARD = { name: name, ask: ask };
  })();
} catch (e) {}
