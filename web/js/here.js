/* WHO'S ON NOW: this tab's page, for the site owner's view (engine/whoson,
   the Privacy Policy's §2.13). Ethan, 2026-11-01: "lets me see all active
   users ... and what page they are on."

   WHAT IT SAYS, and nothing else: which of our pages this tab shows (the
   page's own name), its league or the game's room on a game page, and a
   random number the tab made up for itself (kept in this tab's session
   storage, gone when the tab closes). It says so when the page changes and
   once a minute while the tab is in front of somebody, and that it is
   leaving when it closes. The server holds the latest for a couple of
   minutes, in memory, and writes nothing down.

   Loaded after the first screen (app.js), so it never costs a first paint. */
(function () {
  if (window._qbHere || typeof fetch !== "function") return;
  window._qbHere = true;
  const ROOM = /^(nfl|cfb|nba|wnba|nhl|mlb)$/;
  let tab = "";
  try { tab = sessionStorage.getItem("qb.tab") || ""; } catch (e) { tab = ""; }
  if (!/^[a-f0-9]{16}$/.test(tab)) {
    const bytes = new Uint8Array(8);
    (window.crypto || {}).getRandomValues ? crypto.getRandomValues(bytes)
      : bytes.forEach((_, i) => { bytes[i] = Math.floor(Math.random() * 256); });
    tab = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    try { sessionStorage.setItem("qb.tab", tab); } catch (e) { /* this load's number, then */ }
  }
  const where = () => {
    const st = typeof state !== "undefined" ? state : {};
    const view = String(st.view || "recommended");
    const g = view === "pbp" && st.pbp;
    const league = String((g && g.league) || "").toLowerCase();
    const detail = g && ROOM.test(league) && /^[0-9]{1,14}$/.test(String(g.event || ""))
      ? `${league}_${g.event}` : String(st.sport || "").toLowerCase();
    return { view, detail: /^[a-z]{2,8}$|_/.test(detail) ? detail : "" };
  };
  const post = (body) => {
    try {
      fetch("/api/here", { method: "POST", credentials: "same-origin", keepalive: true,
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => {});
    } catch (e) { /* never worth an error */ }
  };
  let last = "";
  const tell = (force) => {
    if (document.visibilityState === "hidden") return;
    const w = where();
    const key = `${w.view}|${w.detail}`;
    if (!force && key === last) return;
    last = key;
    post({ tab, view: w.view, detail: w.detail });
  };
  // A page changes on the hash; the router has moved by the next moment.
  addEventListener("hashchange", () => setTimeout(() => tell(false), 60));
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") tell(true); });
  setInterval(() => tell(true), 60000);
  addEventListener("pagehide", () => {
    const body = JSON.stringify({ tab, leave: true });
    try {
      if (navigator.sendBeacon && navigator.sendBeacon("/api/here", new Blob([body], { type: "application/json" }))) return;
    } catch (e) { /* the fetch below, then */ }
    post({ tab, leave: true });
  });
  tell(true);
})();
