/* THE COLOURS CHANGE WITHOUT A SNAP (WASHFADE1, 2026-11-17; a room of its own, fetched after the first paint:
   app.js; Ethan: "make transitions smooth. Like when
   the colors switch from somebody's personal team colors they have set ... to when they go to a team
   page and it switches to the team's colors, make that transition smooth and not some like quick, like
   glitchy switch"). Three things paint the screen's colours: the layer under every page (.ambient, or
   a game page's own wash), the bar, and the strip under the clock in the installed app. Whenever what
   one of them paints changes (your colours to a club's on its page, one player's page to the next's, a
   game's two clubs, the theme, the setting) a copy of what it painted a moment ago is laid over it and
   faded away: opacity alone, so the phone's compositor does it and nothing is repainted per frame.
   <html>, <body> and the game page's view are watched, so it is every change and no page asks for it;
   the look is read once a frame at most, before that frame is painted. Nothing fades for a reader who
   asked for less motion, on a page nobody is looking at, or while the app is first drawing itself. */
const WF_MS = 420;
const WF_PROPS = ["backgroundImage", "backgroundColor", "backgroundSize", "backgroundPosition", "backgroundRepeat"];
let _wfLook = null, _wfFrame = 0, _wfTimer = 0;
//: The layer under the page in view: a game page's own wash while it is drawn (detail.js marks it
//: data-wash; its classes are that room's own), else the site's.
function wfBackdrop() {
  const own = document.querySelector("[data-wash]");
  return own && own.getClientRects().length ? own : document.querySelector(".ambient");
}
function wfRead(el, pseudo) {
  if (!el) return null;
  const cs = getComputedStyle(el, pseudo || null);
  // The strip is the installed app's alone: no such box, nothing to fade.
  if (pseudo && (!cs.content || cs.content === "none" || cs.content === "normal")) return null;
  const look = {};
  WF_PROPS.forEach((k) => { look[k] = cs[k]; });
  return look;
}
const wfLooks = () => ({ back: wfRead(wfBackdrop()), bar: wfRead(document.querySelector(".topbar")),
                         strip: wfRead(document.body, "::before") });
const wfSame = (a, b) => (!a && !b) || (!!a && !!b && a.backgroundImage === b.backgroundImage
  && a.backgroundColor === b.backgroundColor);
const wfStill = () => document.visibilityState !== "visible"
  || !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
//: The copy of one surface as it looked, put where it covers that surface and nothing above it.
function wfCopy(cls, place) {
  let el = document.querySelector(`.wf-copy.${cls}`);
  if (!el) {
    el = document.createElement("div");
    el.className = `wf-copy ${cls}`;
    el.setAttribute("aria-hidden", "true");
  }
  place(el);
  return el;
}
function wfFade(from, to) {
  const jobs = [];
  const back = wfBackdrop(), bar = document.querySelector(".topbar");
  if (from.back && back && !wfSame(from.back, to.back)) {
    jobs.push([wfCopy("wf-back", (el) => { if (back.nextElementSibling !== el) back.insertAdjacentElement("afterend", el); }), from.back]);
  }
  if (from.bar && bar && !wfSame(from.bar, to.bar)) {
    jobs.push([wfCopy("wf-bar", (el) => { if (bar.firstElementChild !== el) bar.insertAdjacentElement("afterbegin", el); }), from.bar]);
  }
  if (from.strip && to.strip && !wfSame(from.strip, to.strip)) {
    jobs.push([wfCopy("wf-strip", (el) => { if (el.parentNode !== document.body) document.body.appendChild(el); }), from.strip]);
  }
  if (!jobs.length) return;
  jobs.forEach(([el, look]) => {
    WF_PROPS.forEach((k) => { el.style[k] = look[k]; });
    el.style.transition = "none";
    el.style.opacity = "1";
    el.hidden = false;
  });
  void jobs[0][0].offsetWidth;                    // the copy is on screen, whole, before it starts to go
  jobs.forEach(([el]) => { el.style.transition = `opacity ${WF_MS}ms ease`; el.style.opacity = "0"; });
  clearTimeout(_wfTimer);
  _wfTimer = setTimeout(() => document.querySelectorAll(".wf-copy").forEach((el) => { el.hidden = true; }), WF_MS + 80);
}
function wfCheck() {
  _wfFrame = 0;
  const now = wfLooks();
  if (_wfLook && !wfStill()) wfFade(_wfLook, now);
  _wfLook = now;
}
function wfWatch() {
  if (_wfLook || typeof MutationObserver === "undefined" || !document.body) return;
  _wfLook = wfLooks();
  const soon = () => { if (!_wfFrame) _wfFrame = requestAnimationFrame(wfCheck); };
  const mo = new MutationObserver(soon);
  const watch = { attributes: true, attributeFilter: ["class", "style", "data-theme"] };
  [document.documentElement, document.body, document.getElementById("view-pbp")].forEach((el) => el && mo.observe(el, watch));
  // Back from another app or tab: what is painted now is the look, with nothing to fade from.
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") _wfLook = wfLooks(); });
}

wfWatch();
