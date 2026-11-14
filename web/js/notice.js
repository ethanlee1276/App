/* THE OWNER'S NOTICE (engine/sitenotice; written on the owner's desk,
   js/owner.js). A line across the top of every page — "Tonight's picks are
   late: the odds feed is down" — until its hours run out, the desk takes it
   down, or the reader closes it for themselves (remembered by the notice's
   own id, so the next notice still shows).

   Loaded only when /api/billing/status carries a notice (app.js
   paywallCheck), so a page with none never pays for it. Drawn as text,
   never markup. */
(function () {
  const KEY = "qb.notice.closed";
  function draw(n) {
    let bar = document.getElementById("site-notice");
    let closed = "";
    try { closed = localStorage.getItem(KEY) || ""; } catch (e) { closed = ""; }
    if (!n || !n.text || closed === String(n.id || "")) {
      if (bar) bar.remove();
      return;
    }
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "site-notice";
      bar.setAttribute("role", "status");
      const main = document.querySelector("main");
      (main || document.body).prepend(bar);
    }
    const tone = ["info", "warn", "good"].includes(n.tone) ? n.tone : "info";
    bar.className = `site-notice ${tone}`;
    bar.innerHTML = `<span class="sn-text"></span><button type="button" class="sn-close" aria-label="Close this notice">×</button>`;
    bar.querySelector(".sn-text").textContent = n.text;
    bar.querySelector(".sn-close").addEventListener("click", () => {
      try { localStorage.setItem(KEY, String(n.id || "")); } catch (e) { /* closed for this visit, then */ }
      bar.remove();
    });
  }
  window.qbNotice = draw;
  draw(typeof _pwStatus !== "undefined" && _pwStatus ? _pwStatus.notice : null);
})();
