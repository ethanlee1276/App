/* YOUR TIME HERE, A ROW A DAY (engine/activity.py). Loaded only when the
   server says `activity: true` on /api/billing/status: the site keeps it
   (QB_ACTIVITY=1, with the Privacy Policy's section on it), the reader is
   signed in, and they have not turned it off in Settings → Your activity.

   What leaves the page, every five minutes and when it is put away: the
   seconds it was in front of somebody (the tab visible and touched in the
   last two minutes, or half an hour on a live game, which people watch
   rather than touch), split by the page's own view name and its league;
   whether this is a new visit (a tab opened, or one come back to after
   half an hour away) and whether one of our alerts opened it. Never a
   click, a word typed, an address or anything about another site. The
   box adds the hour itself; the day is the box's. */
(function () {
  if (typeof document === "undefined" || typeof window === "undefined" || window._qbAct) return;
  window._qbAct = true;
  const TICK_S = 5, BEAT_MS = 5 * 60 * 1000, IDLE_S = 120, WATCH_IDLE_S = 1800, NEW_VISIT_MS = 30 * 60 * 1000;
  let secs = 0, views = {}, sports = {}, fresh = true, input = Date.now(), hiddenAt = 0;
  // Whether one of our alerts opened this load (app.js _anAlert): told with
  // its first visit only, never with a later one.
  let tapped = typeof _anAlert !== "undefined" && !!_anAlert;
  const on = () => !!(typeof _pwStatus !== "undefined" && _pwStatus && _pwStatus.activity);
  // A live game's pages: people watch these rather than touch them.
  const watching = () => {
    const v = (typeof state !== "undefined" && state.view) || "";
    return v === "pbp" || v === "gamecast" || v === "live";
  };
  const touched = () => { input = Date.now(); };
  ["pointerdown", "keydown", "wheel", "touchstart", "scroll"].forEach((e) =>
    window.addEventListener(e, touched, { passive: true, capture: true }));
  setInterval(() => {
    if (document.visibilityState !== "visible") return;
    if ((Date.now() - input) / 1000 > (watching() ? WATCH_IDLE_S : IDLE_S)) return;
    const v = String((typeof state !== "undefined" && state.view) || "").toLowerCase().slice(0, 32);
    const sp = String((typeof state !== "undefined" && state.sport) || "").toLowerCase().slice(0, 8);
    secs += TICK_S;
    if (v) views[v] = (views[v] || 0) + TICK_S;
    if (sp) sports[sp] = (sports[sp] || 0) + TICK_S;
  }, TICK_S * 1000);
  function send() {
    if (!on()) { secs = 0; views = {}; sports = {}; return; }
    if (!secs && !fresh) return;
    const body = JSON.stringify({ s: secs, v: views, sp: sports, n: fresh ? 1 : 0, a: fresh && tapped ? 1 : 0 });
    if (fresh) tapped = false;
    secs = 0; views = {}; sports = {}; fresh = false;
    try {
      if (navigator.sendBeacon && navigator.sendBeacon("/api/activity", new Blob([body], { type: "application/json" }))) return;
      fetch("/api/activity", { method: "POST", credentials: "same-origin", keepalive: true,
        headers: { "Content-Type": "application/json" }, body }).catch(() => {});
    } catch (e) { /* a beat is never worth an error */ }
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      hiddenAt = Date.now();
      send();
    } else {
      if (hiddenAt && Date.now() - hiddenAt > NEW_VISIT_MS) fresh = true;
      hiddenAt = 0;
      touched();
    }
  });
  window.addEventListener("pagehide", send);
  setInterval(send, BEAT_MS);
  // The visit is counted at once, not at the first beat.
  send();
})();
