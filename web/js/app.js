/* Qellys Book — app shell.
 *
 * A small client-side router over three views (Recommended / Trending /
 * Players) sharing one data fetch. Rendering helpers draw the pick cards,
 * trending leaderboards and player profiles; visuals.js supplies the SVG art
 * (avatars, stadiums, wind, sparklines).
 */

const state = {
  data: null, minConf: 6.0, minEdge: 2.0, maxJuice: -350, showAll: false,
  view: "recommended", search: "",
  // Every sport with its own board. This list is the reason ?sport=wnba
  // silently fell back to NFL — a new league has to be added here too, or
  // the deep link and the launcher's own preflight URLs quietly lie.
  sport: (["mlb", "nba", "wnba", "cfb"].includes(new URLSearchParams(location.search).get("sport"))
    ? new URLSearchParams(location.search).get("sport") : "nfl"),
  static: new URLSearchParams(location.search).has("static"),
  bankroll: null, unitPct: 1.0,      // per-user bankroll sizing (localStorage)
};

/* ---------------- bankroll sizing ---------------- */
function loadBankroll() {
  const qp = new URLSearchParams(location.search);
  try {
    const b = localStorage.getItem("ge-bankroll");
    const u = localStorage.getItem("ge-unit-pct");
    if (b !== null && b !== "") state.bankroll = parseFloat(b);
    if (u !== null && u !== "") state.unitPct = parseFloat(u) || 1.0;
  } catch (e) {}
  // URL params win (shareable sizing), e.g. ?bankroll=2500&unit=1
  if (qp.has("bankroll")) { const b = parseFloat(qp.get("bankroll")); if (b > 0) state.bankroll = b; }
  if (qp.has("unit")) { const u = parseFloat(qp.get("unit")); if (u > 0) state.unitPct = u; }
}
function unitDollars() {
  return (state.bankroll && state.bankroll > 0) ? state.bankroll * (state.unitPct / 100) : 0;
}
function money(x) {
  return "$" + x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function stakeDollars(units) { return units * unitDollars(); }
function updateUnitNote() {
  const el = document.getElementById("unit-note");
  if (!el) return;
  const u = unitDollars();
  el.textContent = u > 0 ? `1u = ${money(u)}` : "enter to size bets";
}

const SPORT_META = {
  nfl: { logo: "🏈", tagline: "AI-powered NFL player-prop model",
         gamesTitle: "This week's stadiums",
         gamesSub: "real stadium shapes, roof state, live wind and the passing "
                   + "conditions each one is playing to right now",
         api: "/api/recommendations", fallback: "data/recommendations.json" },
  mlb: { logo: "⚾", tagline: "AI-powered MLB player-prop model",
         gamesTitle: "Tonight's ballparks",
         gamesSub: "real park shapes, roof state, live wind and the home-run "
                   + "factor each one is playing to right now",
         api: "/api/mlb/recommendations", fallback: "data/mlb_recommendations.json" },
  wnba: { logo: "🏀", tagline: "Scalpy — WNBA probability engine (on probation)",
          gamesTitle: "Tonight's slate",
          gamesSub: "same minutes-first model as the NBA board, tuned to a "
                    + "40-minute game — and journaled on probation until it "
                    + "has graded enough WNBA results to earn a stake",
          api: "/api/wnba/recommendations", fallback: "data/wnba.json" },
  nba: { logo: "🏀", tagline: "Scalpy — NBA probability engine",
         gamesTitle: "Tonight's slate",
         gamesSub: "minutes first, distributions not point estimates, every "
                   + "number clamped toward the de-vigged market",
         api: "/api/nba/recommendations", fallback: "data/nba.json" },
  cfb: { logo: "🏈", tagline: "College football — attention is the axis",
         gamesTitle: "Saturday's board",
         gamesSub: "134 teams, 60+ games, and no book prices a Wednesday MAC "
                   + "game the way it prices Ohio State – Michigan — so the "
                   + "haircut on our own edge is a dial, not a constant",
         api: "/api/cfb/recommendations", fallback: "data/cfb.json" },
};

/* Pages a sport has no engine for. Listed here rather than as conditions
   scattered through applySport, because "which pages does this sport
   have?" is one question and it should have one answer. */
const HIDDEN_VIEWS = {
  nba: ["longshots"],
  // The WNBA has no futures board: engine/futures.py has a shape for it but
  // futures_build.py does not run it, because there is no outrights key for
  // the league and its season is nearly over by the time this ships.
  wnba: ["longshots", "futures"],
  // §9.1 caps UFC at two legs in ONE fight, and every construction §9.3
  // permits pairs a winner with a method, distance or round-group market.
  // We price fight winners and nothing else, so there is no pair to screen
  // and a tab that can only ever say so is worse than no tab.
  // Futures are a SEASON market. A fight card, a prediction market and a
  // fantasy draft do not have one, and a tab that can only ever say so is
  // worse than no tab.
  ufc: ["parlays", "futures"],
  polymarket: ["parlays", "futures"],
  fantasy: ["parlays", "futures"],
  // CFB has 134 programs and no free player-level feed. A roster tab that
  // can only ever say "no data" is worse than no tab.
  cfb: ["longshots", "trending", "players", "rosters"],
};

/* College football's 134 identities ride in the payload rather than a
   checked-in file, so they aren't known until the slate lands — hence the
   refresh on every load as well as on every sport switch. */
function teamsForSport(sport) {
  if (sport === "mlb") return typeof MLB_TEAMS !== "undefined" ? MLB_TEAMS : {};
  if (sport === "nba") return typeof NBA_TEAMS !== "undefined" ? NBA_TEAMS : {};
  if (sport === "wnba") return typeof WNBA_TEAMS !== "undefined" ? WNBA_TEAMS : {};
  if (sport === "cfb") return (state.data && state.data.teams) || {};
  return typeof TEAMS !== "undefined" ? TEAMS : {};
}

/* ---------------- the desktop "More" menu ----------------
   Five tool buttons live behind it so the switcher stays one row. It has
   to behave like a real menu or it is worse than the row it replaced:
   closes on outside click, on Escape, and the moment you pick something;
   and it marks itself when the page you're on is one of its own, so
   "where am I" survives the collapse. */
function closeMoreMenu() {
  const wrap = document.getElementById("sport-more");
  const btn = document.getElementById("more-toggle");
  if (wrap) wrap.classList.remove("open");
  if (btn) btn.setAttribute("aria-expanded", "false");
}

function initMoreMenu() {
  const wrap = document.getElementById("sport-more");
  const btn = document.getElementById("more-toggle");
  if (!wrap || !btn) return;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = wrap.classList.toggle("open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  // A click anywhere else closes it — including on one of its own items,
  // which is the common case and should not need a second tap.
  document.addEventListener("click", (e) => {
    if (!wrap.contains(e.target)) closeMoreMenu();
  });
  wrap.querySelectorAll(".sport-btn:not(.more-toggle)")
      .forEach((b) => b.addEventListener("click", closeMoreMenu));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMoreMenu();
  });
}

function markMoreMenu() {
  const btn = document.getElementById("more-toggle");
  if (!btn) return;
  const inTools = !!document.querySelector(
    '.sport-more .sport-group[data-group="tools"] .sport-btn.active');
  btn.classList.toggle("has-active", inTools);
}

function applySport() {
  // A sport with no metadata used to throw here and leave the previous
  // league's page on screen under the new league's branding.
  const meta = SPORT_META[state.sport] || SPORT_META.nfl;
  window.ACTIVE_SPORT = state.sport;
  window.ACTIVE_TEAMS = teamsForSport(state.sport);
  // A page with no engine behind it hides rather than rendering empty. No
  // NBA/WNBA long-shot market exists (nothing like HR / anytime-TD), and
  // college football is full-game markets only — there is no CFB player
  // projection layer, so every prop-shaped page goes with it.
  const hidden = HIDDEN_VIEWS[state.sport] || [];
  document.querySelectorAll(".nav-btn[data-view]").forEach((b) => {
    b.style.display = hidden.includes(b.dataset.view) ? "none" : "";
  });
  if (hidden.includes(state.view)) switchView("recommended");
  document.getElementById("tagline").textContent = meta.tagline;
  const gt = document.getElementById("games-title");
  // innerHTML, not textContent: this is the page's hero and it carries a
  // subtitle. Assigning textContent silently deleted the .sub span.
  if (gt) gt.innerHTML = `${escapeHtml(meta.gamesTitle)}`
    + (meta.gamesSub ? ` <span class="sub">— ${escapeHtml(meta.gamesSub)}</span>` : "");
  document.querySelectorAll(".sport-btn").forEach((b) =>
    b.classList.toggle("active",
                       !!b.dataset.sport && b.dataset.sport === state.sport));
  markMoreMenu();
}

/* ---------------- formatting helpers ---------------- */
// NFL props grade A+/A/B+/Pass (the unified 0–100 grade, docs/NFL_MODEL.md
// §10 — no Leans); other modules still use the word grades.
/* "Conditional" is a college-football grade with no equivalent elsewhere:
   the number and the edge are real, the bet is waiting on news (a starting
   QB, a bowl roster). Amber, never green — it must not read as a play. */
const gradeClass = (g) => ({ "A+": "strong", "A": "play", "B+": "lean",
  "Strong Play": "strong", "Play": "play", "Lean": "lean", "Pass": "pass",
  "Conditional": "lean" }[g] || "pass");
const gradeColor = (g) => ({ "A+": "var(--good)", "A": "var(--cyan)", "B+": "var(--warn)",
  "Strong Play": "var(--good)", "Play": "var(--cyan)", "Lean": "var(--warn)",
  "Conditional": "var(--warn)", "Pass": "var(--text-mute)" }[g] || "var(--text-mute)");
const pct = (x) => `${(x * 100).toFixed(1)}%`;
const signedPct = (x) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
const american = (o) => (o > 0 ? `+${o}` : `${o}`);
const activeTeams = () => window.ACTIVE_TEAMS || (typeof TEAMS !== "undefined" ? TEAMS : {});
const teamName = (a) => (activeTeams()[a] && activeTeams()[a].nick) || a;
const teamPrimary = (a) => (activeTeams()[a] && activeTeams()[a].primary) || "var(--brand)";
/* A reason that WORKS AGAINST the bet must not wear a green check. The
   engine phrases negative factors consistently; match those phrasings and
   render them with a red ✗ instead. */
const NEG_REASON = new RegExp(
  ["suppress", "tough ", "holds (lefties|righties)", "capped",
   "strong late relief", "fewer ", "struggles", "knocks balls down",
   "kills carry", "cold", "underdog", "passing risk", "regression risk",
   "soft contact", "\\boverperforming", "reduced exit", "tight zone",
   "small zone", "moving against", "give back", "gives back",
   // College football: a reason that WITHHOLDS the bet is not a point in
   // its favour, whatever else the card says.
   "unconfirmed", "unverified", "^CONDITIONAL", "EXTREME"].join("|"), "i");

function reasonLI(x) {
  return `<li class="${NEG_REASON.test(x) ? "neg" : ""}">${escapeHtml(x)}</li>`;
}

/* ---------------------------------------------------------------------
   Icons, drawn rather than typed.

   The audit counted 18 distinct emoji doing real work on this page. Three
   problems with that, and only the third is about taste: they render as a
   different glyph on every platform (a ✓ on Android is not the ✓ on iOS),
   they cannot take the page's colour so a "won" tick is the same shade as
   a "lost" cross, and a status mark that is really a text character sits
   on the text baseline and drifts as the type ramp moves around it.

   These are strokes on a 16-unit grid using currentColor, so they inherit
   the colour of whatever says them — green on a win, red on a loss — and
   line up on the baseline the same way at every size. Deliberately NOT an
   icon library: Lucide-in-a-pastel-circle is the exact tell the audit was
   looking for, and trading one for another is not progress.

   Arrows are left alone on purpose. "890 → 1 recommended" is punctuation
   between two numbers, not an icon, and drawing it would be worse.
   -------------------------------------------------------------------- */
const ICON_PATHS = {
  check: '<path d="M3 8.5l3.2 3.4L13 4.6"/>',
  cross: '<path d="M4 4l8 8M12 4l-8 8"/>',
  dash: '<path d="M3.4 8h9.2"/>',
  // The one filled mark. A live indicator is not a glyph you read, it is a
  // thing you notice in peripheral vision, and an outline dot does not.
  dot: '<circle cx="8" cy="8" r="3.6" fill="currentColor" stroke="none"/>',
  warn: '<path d="M8 2.2L14.6 13.4H1.4z"/><path d="M8 6.6v3.1"/>'
        + '<path d="M8 11.6v.1"/>',
  search: '<circle cx="7.2" cy="7.2" r="4.3"/><path d="M10.4 10.4L14 14"/>',
  calendar: '<rect x="2.2" y="3.4" width="11.6" height="10.4" rx="1.6"/>'
            + '<path d="M2.2 6.6h11.6M5.4 2.2v2.4M10.6 2.2v2.4"/>',
  clock: '<circle cx="8" cy="8" r="6"/><path d="M8 4.3V8.2l2.6 1.6"/>',
  cloud: '<path d="M4.6 12.4a3 3 0 01.2-6 4 4 0 017.6.9 2.6 2.6 0 01-.5 5.1z"/>',
  // A roof over a ground line. The first attempt was a bowl seen from
  // above — two concentric ellipses — which at 13px reads unmistakably as
  // an EYE. Only the screenshot said so; the geometry looked fine written
  // down. Same mistake was made twice, here and in the dome wind gauge.
  stadium: '<path d="M2.2 12.5h11.6"/><path d="M2.7 12.5a5.3 4.6 0 0110.6 0"/>'
           + '<path d="M6.4 12.5V9.2h3.2v3.3"/>',
  mountain: '<path d="M1.4 12.9L5.9 5.3l3 4.7 1.9-2.9 3.8 5.8z"/>',
  // "3 books · best DK" is a price-shopping claim, so it wears a price tag.
  tag: '<path d="M8.6 1.9H14v5.4l-6.5 6.5a1.3 1.3 0 01-1.9 0L2.1 10.3a1.3 1.3 0 010-1.9z"/>'
       + '<path d="M11.2 4.8v.01"/>',
  moon: '<path d="M13.2 9.6A5.6 5.6 0 016.4 2.8a5.8 5.8 0 106.8 6.8z"/>',
  sun: '<circle cx="8" cy="8" r="3.1"/>'
       + '<path d="M8 1.4v1.6M8 13v1.6M1.4 8h1.6M13 8h1.6'
       + 'M3.3 3.3l1.2 1.2M11.5 11.5l1.2 1.2M12.7 3.3l-1.2 1.2M4.5 11.5l-1.2 1.2"/>',

  /* --- §6.12. Drawn marks for the places that still typed a picture. ---
     An emoji is somebody else's illustration at somebody else's weight: it
     renders as a different drawing on every platform, ignores the stroke and
     the colour of everything around it, and at 34px in an empty state it is
     the loudest thing on a page whose whole message is that there is
     nothing here. These are 1.7px strokes in currentColor, same as the rest.

     Deliberately literal rather than clever. The dome gauge and the first
     stadium mark were both drawn as concentric ellipses and both read as an
     EYE at 13px — twice, and only a screenshot ever said so. */
  rising: '<path d="M1.8 11.4l4.1-4.2 2.6 2.6 4.1-4.6"/>'
          + '<path d="M9.6 5.2h3.6v3.6"/>',
  falling: '<path d="M1.8 4.6l4.1 4.2 2.6-2.6 4.1 4.6"/>'
           + '<path d="M9.6 10.8h3.6V7.2"/>',
  // Heat: a flame is a teardrop with a kink, not a leaf.
  hot: '<path d="M8 1.8c2.4 2.6 4.2 4.5 4.2 7a4.2 4.2 0 11-8.4 0c0-1.3.6-2.4 1.6-3.6'
       + '.4 1 1 1.6 1.8 1.9C6.6 5.6 7 3.6 8 1.8z"/>',
  cold: '<path d="M8 1.6v12.8M2.4 4.8l11.2 6.4M13.6 4.8L2.4 11.2"/>',
  // Value: a cut stone, because "biggest edge" is the thing you dig for.
  gem: '<path d="M4.4 2.4h7.2l2.6 3.6L8 13.8 1.8 6z"/><path d="M1.8 6h12.4"/>',
  inbox: '<path d="M1.9 8.4h3.4l1 2h3.4l1-2h3.4"/>'
         + '<path d="M3.6 2.6h8.8l2.1 5.8v4a1.2 1.2 0 01-1.2 1.2H2.7a1.2 1.2 0 01-1.2-1.2v-4z"/>',
  book: '<path d="M2.4 2.6h4a2.2 2.2 0 012.2 2.2v8.4a1.7 1.7 0 00-1.7-1.7H2.4z"/>'
        + '<path d="M13.6 2.6h-4a2.2 2.2 0 00-2.2 2.2v8.4a1.7 1.7 0 011.7-1.7h4.5z"/>',
  signal: '<path d="M8 12.6v.01"/><path d="M5.6 10.2a3.4 3.4 0 014.8 0"/>'
          + '<path d="M3.2 7.8a6.8 6.8 0 019.6 0"/>'
          + '<path d="M.9 5.4a10.1 10.1 0 0114.2 0"/>',
  trophy: '<path d="M4.6 2.2h6.8v3.6a3.4 3.4 0 11-6.8 0z"/>'
          + '<path d="M4.6 3.2H2.4v1a2.4 2.4 0 002.4 2.4M11.4 3.2h2.2v1a2.4 2.4 0 01-2.4 2.4"/>'
          + '<path d="M8 9.2v2.4M5.4 13.8h5.2"/>',
  target: '<circle cx="8" cy="8" r="5.8"/><circle cx="8" cy="8" r="2.4"/>',
  list: '<path d="M5.4 4.4h7.8M5.4 8h7.8M5.4 11.6h7.8"/>'
        + '<path d="M2.8 4.4v.01M2.8 8v.01M2.8 11.6v.01"/>',
  chart: '<path d="M2.2 13.4V2.4"/><path d="M2.2 13.4h11.6"/>'
         + '<path d="M4.8 11V7.6M7.6 11V4.6M10.4 11V8.8M13 11V6"/>',
  glove: '<path d="M3.4 13.4V7.2a1.6 1.6 0 013.2 0V4.2a1.6 1.6 0 013.2 0v3'
         + 'a1.6 1.6 0 013.2 0v3.4a3.8 3.8 0 01-3.8 3.8z"/>',
};

function icon(name, size = 13) {
  const d = ICON_PATHS[name];
  if (!d) return "";
  return `<svg class="ic" viewBox="0 0 16 16" width="${size}" height="${size}"
    fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"
    stroke-linejoin="round" aria-hidden="true" focusable="false">${d}</svg>`;
}

/* A drawn mark sized to sit inside a line of text. `icon()` defaults to
   13px and is used inside chips and buttons; headings and column titles
   want it a touch larger and nudged onto the baseline. */
function iconMark(name, size = 14) {
  return `<span class="ico-mark">${icon(name, size)}</span>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------------- date / kickoff formatting ---------------- */
function formatGameDate(dateStr) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr || "");
  if (!m) return "";
  // Build a local date (avoids the UTC-parse off-by-one on YYYY-MM-DD).
  const d = new Date(+m[1], +m[2] - 1, +m[3]);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
function formatKickoff(kick) {
  if (!kick) return "";
  if (kick.includes("T")) {                       // ISO datetime (MLB first pitch)
    const d = new Date(kick);
    return isNaN(d) ? "" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  const m = /^(\d{1,2}):(\d{2})/.exec(kick);       // "HH:MM" 24h ET (NFL)
  if (m) { let h = +m[1]; const ap = h >= 12 ? "PM" : "AM"; h = h % 12 || 12; return `${h}:${m[2]} ${ap} ET`; }
  return kick;
}
function whenLabel(dateStr, kick) {
  return [formatGameDate(dateStr), formatKickoff(kick)].filter(Boolean).join(" · ");
}
function whenChip(dateStr, kick) {
  const w = whenLabel(dateStr, kick);
  return w ? `<span class="chip when">${escapeHtml(w)}</span>` : "";
}

/* ---------------- motion ---------------- */
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const revealObserver = ("IntersectionObserver" in window) && !reduceMotion
  ? new IntersectionObserver((entries, obs) => {
      entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); obs.unobserve(e.target); } });
    }, { threshold: 0.08, rootMargin: "0px 0px -6% 0px" })
  : null;

// Tag children for staggered reveal, then observe (or show immediately).
function revealChildren(container) {
  if (!container) return;
  const instant = reduceMotion || state.static || state.quiet || !revealObserver;
  const kids = container.children;
  for (let i = 0; i < kids.length; i++) {
    const el = kids[i];
    el.classList.add("reveal");
    el.style.setProperty("--i", Math.min(i, 12));
    if (instant) el.classList.add("in");
    else revealObserver.observe(el);
  }
}

// Subtle pointer tilt for stadium cards.
function enableTilt(container) {
  if (!container || reduceMotion) return;
  container.querySelectorAll(".tilt").forEach((card) => {
    card.addEventListener("pointermove", (ev) => {
      const r = card.getBoundingClientRect();
      const px = (ev.clientX - r.left) / r.width - 0.5;
      const py = (ev.clientY - r.top) / r.height - 0.5;
      card.classList.add("tilting");
      card.style.transform = `perspective(760px) rotateY(${px * 7}deg) rotateX(${-py * 7}deg) translateZ(6px)`;
    });
    card.addEventListener("pointerleave", () => {
      card.classList.remove("tilting");
      card.style.transform = "";
    });
  });
}

/* ---------------- theme ---------------- */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  // innerHTML, not textContent: an SVG is markup. Left as textContent this
  // would print the literal tag string into the button.
  if (btn) btn.innerHTML = icon(theme === "light" ? "sun" : "moon", 17);
  try { localStorage.setItem("ge-theme", theme); } catch (e) {}
}
function initTheme() {
  const param = new URLSearchParams(location.search).get("theme");
  let theme = param;
  if (!theme) { try { theme = localStorage.getItem("ge-theme"); } catch (e) {} }
  if (theme !== "light" && theme !== "dark") theme = "dark";
  applyTheme(theme);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(cur === "dark" ? "light" : "dark");
}

/* ---------------- data ---------------- */
function showSkeleton() {
  const host = document.getElementById("cards");
  if (host) host.innerHTML = Array.from({ length: 6 }, () => `<div class="skeleton-card"></div>`).join("");
}

/* Whatever a feed forgot to send must not crash the renderers — a slate
   missing `counts` used to throw mid-renderAll and leave the PREVIOUS
   sport's page on screen under the new sport's branding. Every slate
   passes through here so each renderer can trust the shared keys. */
function normalizeSlate(d) {
  d = (d && typeof d === "object") ? d : {};
  d.games = d.games || [];
  d.recommendations = d.recommendations || [];
  d.game_bets = d.game_bets || [];
  d.long_shots = d.long_shots || [];
  d.longshot_watch = d.longshot_watch || [];
  d.market_scan = d.market_scan || {};
  d.counts = d.counts || {};
  if (d.counts.props_analyzed == null) d.counts.props_analyzed = d.recommendations.length;
  return d;
}

async function load(quiet = false) {
  state.quiet = quiet;                       // silent re-render (no entrance anim)
  if (!quiet) showSkeleton();
  // The brand IS the refresh control now — it spins while data loads, so
  // a tap always has visible feedback even though the button is gone.
  const refreshBtn = document.getElementById("brand-home");
  if (refreshBtn && !quiet) refreshBtn.classList.add("loading");
  const meta = SPORT_META[state.sport];
  const params = new URLSearchParams({ min_confidence: state.minConf, min_edge: state.minEdge, max_juice: state.maxJuice });
  // When the payload came off disk the server stamps Last-Modified with the
  // build time. That, not the fetch time, is what "how fresh is this?"
  // means — a laptop whose refresh loop died still answers instantly with
  // a board from this morning.
  const stampFrom = (res) => {
    const lm = res.headers.get("Last-Modified");
    const t = lm ? Date.parse(lm) : NaN;
    state.builtAt = Number.isFinite(t) ? t : null;
  };
  try {
    // Cache-busted, and no-store. The poll URL was byte-identical on every
    // refresh — same sport, same three slider values — so iOS Safari
    // answered from its own cache and the page could sit on a board from
    // twenty minutes ago while the timer fired happily every 30 seconds.
    // Closing the tab and reopening it was the only thing that missed the
    // cache, which is exactly the symptom.
    const res = await fetch(`${meta.api}?${params}&_=${Date.now()}`,
                            { cache: "no-store" });
    if (!res.ok) throw new Error("api");
    stampFrom(res);
    state.data = normalizeSlate(await res.json());
  } catch (e) {
    // The fallback file can be missing too (a sport that has never been
    // built). An honest empty slate beats an unhandled rejection that
    // strands the old sport's page on screen.
    try {
      const res = await fetch(`${meta.fallback}?_=${Date.now()}`,
                              { cache: "no-store" });
      if (!res.ok) throw new Error("fallback");
      stampFrom(res);
      state.data = normalizeSlate(await res.json());
    } catch (e2) {
      state.builtAt = null;
      state.data = normalizeSlate({ date: "", status: "not built" });
    }
  }
  renderAll();
  state.lastLoad = Date.now();
  state.quiet = false;
  if (refreshBtn && !quiet) refreshBtn.classList.remove("loading");
  manageAutoRefresh();
  updateAgo();
}

/* Refresh the moment the page comes back, because a timer alone cannot.
 *
 * iOS Safari throttles setInterval hard when a tab is backgrounded and
 * suspends it outright when the phone locks. Come back ten minutes later
 * and the timer has not fired — and after a bfcache restore (swipe back,
 * or reopening the tab) the page resumes frozen with its timers dead and
 * no `load` event to restart them. The board then sits at whatever it was
 * when you looked away, ageing, until the tab is closed and reopened.
 *
 * `visibilitychange` covers unlock and tab-switch; `pageshow` with
 * `persisted` covers the bfcache restore that fires no other event. Both
 * are needed — neither catches the other's case.
 */
const RETURN_REFRESH_AFTER_MS = 10000;

function refreshOnReturn() {
  if (state.static) return;
  // A tab-switch storm should not become a request storm: if we loaded
  // seconds ago, the data on screen is already the data on disk.
  if (Date.now() - (state.lastLoad || 0) < RETURN_REFRESH_AFTER_MS) return;
  load(true);
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshOnReturn();
});
window.addEventListener("pageshow", (e) => {
  // persisted = restored from the back-forward cache with timers dead.
  if (e.persisted) refreshOnReturn();
});
window.addEventListener("focus", refreshOnReturn);

/* Poll for live updates every 30s while any game is in progress. */
function manageAutoRefresh() {
  const hasLive = (state.data?.games || []).some((g) => (g.live || {}).state === "live");
  const el = document.getElementById("live-refresh");
  // The freshness chip is ALWAYS shown. Two reasons: "how old is this?" is
  // worth answering on every page, not only when a game happens to be in
  // progress; and a chip that appears for one sport and vanishes for
  // another re-wrapped the status row, which changed the header's height
  // mid-tap — the "it enlarges when I switch sports" bug.
  if (el) el.style.display = "";
  state.livePolling = hasLive && !state.static;
  // Poll ALWAYS, just slower when nothing is in progress. The board moves
  // between builds even with no game on — new picks, settled bets, a paid
  // odds pull — and stopping the timer entirely meant the page only ever
  // aged, never updated, until it was reloaded by hand.
  const every = state.livePolling ? 30000 : 120000;
  if (state.static) {
    clearInterval(state.refreshTimer); state.refreshTimer = null;
  } else if (state.refreshEvery !== every || !state.refreshTimer) {
    clearInterval(state.refreshTimer);
    state.refreshEvery = every;
    state.refreshTimer = setInterval(() => load(true), every);
  }
  // The ticker runs regardless so the age stays honest between loads.
  if (!state.tickTimer) state.tickTimer = setInterval(updateAgo, 1000);
  updateAgo();
}

// The refresh loop rebuilds every board every 60s. Past a few minutes with
// no new build, something on the machine has stopped — asleep, crashed,
// off the network — and the number on screen is history, not tonight.
const STALE_AFTER_MS = 8 * 60 * 1000;

/* Pages with no data feed behind them. The freshness chip ages the SLATE,
   and on a pure reference page that is a lie of scope — "Stale — built
   10h ago" over a page of prose that has no build at all. */
const REFERENCE_VIEWS = ["why", "about"];

function updateAgo() {
  const el = document.getElementById("live-refresh");
  if (!el) return;
  if (REFERENCE_VIEWS.includes(state.view)) {
    el.style.visibility = "hidden";   // hidden, not display:none — the row
    return;                           // must not change height mid-tap
  }
  el.style.visibility = "";
  if (!state.lastLoad) return;
  // Age of the DATA where the server told us (Last-Modified), falling back
  // to the fetch time. The fallback flatters: it can only ever say
  // "seconds", which is exactly how a frozen board looked live from across
  // town — so when it's all we have, don't claim staleness either way.
  const known = state.builtAt != null;
  const since = known ? state.builtAt : state.lastLoad;
  const s = Math.max(0, Math.round((Date.now() - since) / 1000));
  const ago = s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`;
  const stale = known && (Date.now() - state.builtAt) > STALE_AFTER_MS;
  // Same wording either way so the chip's width barely moves; the live dot
  // is what says "and it's polling because games are running".
  el.innerHTML = (state.livePolling && !stale ? `<span class="live-dot"></span>` : "")
    + (stale ? `Stale — built ${ago} ago` : `Updated ${ago} ago`);
  el.classList.toggle("idle", !state.livePolling && !stale);
  el.classList.toggle("stale", stale);
  el.title = stale
    ? "The server hasn't rebuilt the board in a while — check that the "
      + "laptop is awake and python3 launch.py is still running."
    : "How long ago the server last rebuilt this board.";
}

function passesFilters(r) {
  return r.recommended && r.confidence >= state.minConf && r.edge * 100 >= state.minEdge
    && r.odds >= state.maxJuice && r.grade !== "Pass";
}

function slateDateLabel(d) {
  // Show the span of actual game dates when the slate covers more than one day.
  const dates = [...new Set((d.games || []).map((g) => g.date).filter(Boolean))].sort();
  if (!dates.length) return `Slate: ${d.date}`;
  if (dates.length === 1) return formatGameDate(dates[0]);
  return `${formatGameDate(dates[0])} – ${formatGameDate(dates[dates.length - 1])}`;
}

function renderDataSource(d) {
  const el = document.getElementById("data-source");
  if (!el) return;
  const src = String(d.generated_from || "");
  const live = src.startsWith("live");
  el.className = `data-source ${live ? "live" : "sample"}`;
  el.innerHTML = `<span class="src-dot"></span>${live ? "Live data" : "Sample data"}`;
  el.title = live
    ? (d.built_at ? `Real data · built ${d.built_at.replace("T", " ")}` : "Real live data")
    : "Illustrative sample data — run a live build (see LAUNCH.md) for real games";
}

/* A league whose tuning was fitted somewhere else does not get to bet on
   the strength of borrowed numbers. It journals and grades exactly like a
   live board, and the page says so — the same probation the long-shot
   watchlist and the Polymarket flow model sit under. Saying it once, at
   the top, beats a footnote nobody reads under a stake size. */
function renderProbation() {
  const host = document.getElementById("probation-note");
  if (!host) return;
  const d = state.data || {};
  if (!d.probation) { host.innerHTML = ""; return; }
  const t = d.tuning || {};
  host.innerHTML = `<div class="card" style="border-left:3px solid var(--warn);margin-bottom:12px">
    <div class="player">${iconMark("warn")}${escapeHtml((SPORT_META[state.sport] || {}).name || state.sport.toUpperCase())} is on probation — graded, not bet</div>
    <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:5px">
      ${escapeHtml(t.note || "This league's tuning has not been fitted to its own results yet.")}
      Everything below is priced and journaled exactly as a live board would be,
      so the record it builds is real — it just doesn't stake anything until that
      record clears the promotion bar${t.inherited_from
        ? ` (the numbers are the ${escapeHtml(t.inherited_from.toUpperCase())} model's for now)` : ""}.
    </div></div>`;
}

/* The talent prior, shown rather than assumed. It is the layer that
   carries a September projection — when a team's own results are two games
   against opponents nobody has measured either — so "is it on, and which
   of its four inputs actually arrived" is a question the page has to be
   able to answer. A prior quietly running on recruiting alone, with the
   portal missing, is a different number from a complete one. */
function renderTalent() {
  const host = document.getElementById("talent-note");
  if (!host) return;
  const t = (state.data || {}).talent;
  if (state.sport !== "cfb" || !t) { host.innerHTML = ""; return; }

  if (!t.available) {
    host.innerHTML = `<div class="card" style="border-left:3px solid var(--warn);margin-bottom:12px">
      <div class="player">${iconMark("list")}No preseason talent prior</div>
      <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:5px">
        The board is running on results only. In September that means an
        unproven Alabama and an unproven Kent State are both rated near
        average, which is wrong in a direction the market will take money
        for. ${escapeHtml(t.note || "")}
      </div></div>`;
    return;
  }
  const L = t.layers || {};
  const chip = (name, n) => `<span class="chip ${n ? "good" : "down"}">${
    escapeHtml(name)} ${n ? n : "—"}</span>`;
  const fit = t.fit || {};
  host.innerHTML = `<div class="card" style="border-left:3px solid var(--good);margin-bottom:12px">
    <div class="player">${iconMark("check")}Preseason talent prior — ${t.teams_with_prior} team(s)</div>
    <div class="lf-chips" style="margin:6px 0">
      ${chip("recruiting", L.talent)}${chip("blue-chip", L.blue_chip)}
      ${chip("returning", L.returning)}${chip("portal", L.portal)}
    </div>
    <div style="color:var(--text-body);font-size:var(--fs-md)">
      ${fit.fitted
        ? `One standard deviation of recruiting talent is worth
           ${escapeHtml(String(fit.points_per_sd))} net points a game, fitted on
           ${fit.samples} completed team-seasons (r=${escapeHtml(String(fit.r))}).`
        : `The talent-to-points slope is still a documented prior rather than a
           fit — ${escapeHtml(fit.note || "")}`}
      It carries ~25% of a Week-1 projection and decays toward 5% by November,
      because by then a team's own results have answered the question.
      ${(t.missing_layers || []).length
        ? `<b> Not loaded: ${escapeHtml((t.missing_layers || []).join(", "))}.</b>` : ""}
    </div></div>`;
}

function renderAll() {
  const d = state.data;
  if (!d) return;
  // CFB identities arrive WITH the slate, so they have to be picked up
  // here — applySport runs before the fetch and would leave every college
  // helmet drawing in the fallback brand colour.
  window.ACTIVE_TEAMS = teamsForSport(state.sport);
  // The header badge describes the ACTIVE page. While a standalone page
  // (Fantasy, Polymarket, NBA, UFC) is up, the sports slate finishing a
  // background load must not stamp its own source over it — that's how the
  // Fantasy page opened saying "Live data" and flipped to "Sample data"
  // (the offseason NFL slate's badge) about a feed that never stopped
  // being live. exitStandaloneMode() restores the slate's badge on return.
  if (!STANDALONE_MODES.includes(state.view)) {
    renderDataSource(d);
    document.getElementById("slate-date").textContent = slateDateLabel(d);
  }
  renderProbation();
  renderTalent();
  renderStats();
  renderEmptySlate();
  renderLivePicks();
  renderBestBets();
  renderTeamForm();
  renderGames();
  renderGameBets();
  renderIncentives();
  renderRestWatch();
  renderRecommended();
  renderEdgeBoard();
  renderScanner();
  renderLongShots();
  renderParlays();
  renderTrending();
  renderPlayers();
  // A deep link into a game lands before the slate has loaded, and the
  // 60s refresh replaces the data under an open game page — both need the
  // view redrawn once the new data is actually here.
  if (state.view === "game") renderGamePage();
  // Rosters live in their own per-sport payload rather than the slate, so
  // nothing above redraws them. Switching leagues while sitting on the tab
  // left the previous league's teams on screen under the new league's
  // header — the same class of bug as a standalone page keeping a stale
  // badge, and it looks like the switch silently failed.
  if (state.view === "rosters") renderRosters();
  if (state.view === "standings") renderStandings();
  if (state.view === "futures") renderFutures();
}

/* ============================================================
   Futures — the whole season, played out
   ============================================================
   The one page here that is about months rather than tonight, and it has to
   say two things the others never do.

   These probabilities come from simulating the remaining schedule twenty
   thousand times, not from reading a price. That is the point: a book posts
   futures earliest and revisits them least, so a number rebuilt from
   tonight's ratings is often looking at a months-old quote. Where we have a
   price the gap is shown; where we do not, the probability stands on its
   own, exactly as the Parlay Zone publishes a required price rather than
   inventing a quote.

   And in the preseason every rating is last season's. `prior_share` says how
   much, and the banner says it in words, because a division number in
   August is a prior wearing a projection's clothes and nothing about the
   figure itself communicates that. */
let _futuresCache = {};

async function renderFutures() {
  const host = document.getElementById("futures-body");
  if (!host) return;
  const sport = state.sport;
  let d = _futuresCache[sport];
  if (d === undefined) {
    host.innerHTML = `<p class="loading">Simulating the season…</p>`;
    try {
      const res = await fetch(`data/futures_${sport}.json?t=` + Date.now());
      d = res.ok ? await res.json() : null;
    } catch (e) { d = null; }
    _futuresCache[sport] = d;
  }
  if (state.view !== "futures" || state.sport !== sport) return;

  const teams = (d && d.teams) || [];
  if (!teams.length) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("target", 30)}</div>
      <div class="es-title">No season to project</div>
      <div class="es-sub">${escapeHtml((d && d.note)
        || "This sport has no futures board yet — run futures_build.py to make one.")}</div></div>`;
    return;
  }
  host.innerHTML = futuresDoctrine(d) + futuresTeamTable(d) + futuresTotals(d)
    + `<p class="rec-stamp">Built ${escapeHtml(d.generated_at || "")}
       · ${d.fixtures_remaining || 0} game(s) left to play
       · ${(d.trials || 0).toLocaleString()} simulations.</p>`;
  revealChildren(host);
}

/* The two caveats, and the preseason one is not a footnote. */
function futuresDoctrine(d) {
  const prior = Number(d.prior_share || 0);
  const warn = prior >= 0.5
    ? `<div class="fx-prior">${icon("warn")} <b>${(prior * 100).toFixed(0)}% of this is last season.</b>
       ${escapeHtml(d.note || "")}. Read it as a prior, not a projection —
       these numbers are real arithmetic on stale inputs, and they will be
       replaced by this year's evidence within a few weeks of kickoff.</div>`
    : "";
  return `${warn}${recDisclosure("How these numbers are made", `${escapeHtml(d.doctrine || "")}
    Each remaining game is one draw from the two teams' ratings plus home
    advantage; wins accumulate, division winners are the most wins, the
    playoff field fills per the league's own shape, and the bracket is played
    out game by game. Assumed, and worth knowing: ratings hold for the rest
    of the season — no injuries, no trades, no regression — every game is
    independent, and home advantage is one constant per sport.`)}`;
}

function futuresTeamTable(d) {
  const priced = (d.teams || []).some((t) => t.title_odds != null);
  const rows = (d.teams || []).slice(0, 20).map((t) => {
    const edge = t.title_edge_pts;
    const eCls = edge == null ? "" : edge > 0 ? "pos" : edge < 0 ? "neg" : "";
    return `<div class="fx-row">
      <span class="fx-team">${escapeHtml(t.team)}</span>
      <span class="fx-grp">${escapeHtml(t.conference || "")}${t.division ? " " + escapeHtml(t.division) : ""}</span>
      <span class="fx-rec">${t.wins}-${t.losses}</span>
      <span class="fx-proj">${t.proj_wins.toFixed(1)}
        <span class="fx-band">${t.proj_wins_lo}–${t.proj_wins_hi}</span></span>
      <span class="fx-div">${fxPct(t.p_division)}</span>
      <span class="fx-po">${fxPct(t.p_playoffs)}</span>
      <span class="fx-ttl">${fxPct(t.p_title)}</span>
      ${priced ? `<span class="fx-odds">${t.title_odds == null ? "—" : american(t.title_odds)}</span>
      <span class="fx-edge ${eCls}">${edge == null ? "" : (edge > 0 ? "+" : "") + edge.toFixed(1)}</span>` : ""}
    </div>`;
  }).join("");
  return `
    <div class="section-title">Season outlook
      <span class="sub">— projected wins with a 10th–90th band, and how often each
      finish happens across ${(d.trials || 0).toLocaleString()} simulated seasons.</span></div>
    <div class="card fx-table${priced ? " priced" : ""}" style="padding:0">
      <div class="fx-row fx-head">
        <span class="fx-team">Team</span><span class="fx-grp">Group</span>
        <span class="fx-rec">W-L</span><span class="fx-proj">Proj</span>
        <span class="fx-div">Div</span><span class="fx-po">Playoff</span>
        <span class="fx-ttl">Title</span>
        ${priced ? `<span class="fx-odds">Book</span><span class="fx-edge">Edge</span>` : ""}
      </div>${rows}</div>
    ${priced ? `<p class="fx-note">Edge is our simulated probability minus the
      book's implied one, in points. A book posts futures early and revisits
      them rarely, so a positive number here is usually a stale quote rather
      than a disagreement about the team.</p>`
      : `<p class="fx-note">No book price attached. The probability stands on its
      own — what the season looks like from here, whatever anyone is charging
      for it.</p>`}`;
}

/* Futures percentages round differently from the site's `pct`: a 3% title
   chance needs its decimal and a 68% division chance does not, and a table
   of "3.0%" next to "68.0%" reads as false precision on the big number. */
const fxPct = (p) => (p == null ? "—" : (p * 100).toFixed(p >= 0.1 ? 0 : 1) + "%");

function futuresTotals(d) {
  const blocks = (d.season_totals || []).filter((m) => (m.players || []).length);
  if (!blocks.length) return "";
  return `
    <div class="section-title">Season totals
      <span class="sub">— each player's rate so far, times the games his team has
      left, with the games he actually plays taken into account.</span></div>
    ${blocks.map((m) => `
      <div class="fx-market">
        <div class="fx-market-head">${escapeHtml(m.label)}</div>
        ${m.players.map((p) => `<div class="fx-prow">
          <span class="fx-pname">${escapeHtml(p.player)}</span>
          <span class="fx-pteam">${escapeHtml(p.team || "")}</span>
          <span class="fx-pnow">${p.banked}</span>
          <span class="fx-pproj"><b>${p.mean}</b>
            <span class="fx-band">±${p.sd}</span></span>
          <span class="fx-pav" title="Share of his team's games he has actually played">${(p.availability * 100).toFixed(0)}%</span>
          ${p.line == null ? `<span class="fx-pp"></span>`
            : `<span class="fx-pp ${p.p_over >= 0.5 ? "pos" : ""}">${fxPct(p.p_over)} o${p.line}</span>`}
        </div>`).join("")}
      </div>`).join("")}`;
}

/* ============================================================
   Empty state — nothing on the board
   ============================================================ */
function renderEmptySlate() {
  const el = document.getElementById("empty-slate");
  const noGames = !(state.data.games || []).length;
  const noProps = !(state.data.recommendations || []).length;

  /* Games on the schedule and no props is NOT a quiet night, and it used to
     render as one: a board with nothing on it and no explanation. The WNBA
     sat like that through a live season because every prop here is projected
     from stored player logs and that league had never been ingested. The
     build reports the gap; this shows it, with the games still listed —
     they are real, it is only our history that is missing. */
  const gap = state.data.history_gap;
  /* The panel normally sits eighth in the view, which is fine when the whole
     board is empty — everything above it is empty too. With a history gap
     the games ARE there, so it landed 900px down, below the slate, the
     probation note, the KPI tiles and best-bets: past the point where anyone
     has already decided the site is broken. It moves up under the slate for
     this case only, and moves back for every other. */
  const anchor = document.getElementById("games");
  if (el && el.parentElement && anchor) {
    if (gap) {
      if (el.previousElementSibling !== anchor) {
        el.dataset.homeIndex = el.dataset.homeIndex
          || [...el.parentElement.children].indexOf(el);
        anchor.after(el);
      }
    } else if (el.dataset.homeIndex) {
      const kids = el.parentElement.children;
      const back = kids[Number(el.dataset.homeIndex)];
      if (back && back !== el) back.after(el);
      delete el.dataset.homeIndex;
    }
  }
  if (gap && el) {
    el.style.display = "";
    document.getElementById("games-title").style.display = "";
    el.innerHTML = `<div class="es-icon">${icon("inbox", 30)}</div>
      <div class="es-title">Games tonight, but no player history to project from</div>
      <div class="es-sub">Every prop on this board is built from stored game
      logs, and this database has
      <b>${gap.players_found || 0}</b> player(s) with any history for tonight's
      teams — a prop needs three games. Nothing is broken and no odds are
      wasted; the league just hasn't been ingested yet.<br><br>
      Run once, then the board fills on the next refresh:<br>
      <code>${escapeHtml(gap.fix || "")}</code></div>`;
    return;
  }

  if (!noGames || !el) {
    if (el) el.style.display = "none";
    document.getElementById("games-title").style.display = "";
    return;
  }
  const live = String(state.data.generated_from || "").startsWith("live");
  el.style.display = "";
  el.innerHTML = state.data.status === "not built"
    ? `<div class="es-icon">${icon("clock", 30)}</div><div class="es-title">This slate hasn't been built yet</div>
       <div class="es-sub">If <code>launch.py</code> is running, it builds every sport on its next
       refresh cycle — give it a minute and hit Refresh. Otherwise see LAUNCH.md.</div>`
    : live
    ? `<div class="es-icon">${icon("calendar", 30)}</div><div class="es-title">No games on the board right now</div>
       <div class="es-sub">Nothing is scheduled or in progress for this slate yet. Check back closer to
       game time — the board refreshes automatically.</div>`
    : `<div class="es-icon">${icon("stadium", 30)}</div><div class="es-title">No slate loaded</div>
       <div class="es-sub">Build a live slate (see LAUNCH.md) or run <code>python3 generate.py</code>
       for the sample board.</div>`;
  // Nothing else to show; clear the busier sections.
  document.getElementById("games-title").style.display = noProps ? "none" : "";
}

/* ============================================================
   Best Bets Tonight — every measured signal, one ranked list.
   The ORDER is the point: structural certainties first (arbs), then the
   signals with measured or backtested records (sharp anchors, stale
   lines, the HR board's proven tier), model opinion last — because the
   edge audit showed the model's opinion ALONE doesn't beat the close.
   Every row says where its number comes from.
   ============================================================ */
let _recordCache = null;
async function loadRecordOnce() {
  if (_recordCache !== null) return _recordCache;
  try {
    const res = await fetch("data/record.json?t=" + (Date.now() / 60000 | 0));
    _recordCache = res.ok ? await res.json() : {};
  } catch (e) { _recordCache = {}; }
  return _recordCache;
}

async function renderBestBets() {
  const host = document.getElementById("best-bets");
  if (!host) return;
  const rec = await loadRecordOnce();
  const sig = tonightSignals();
  const ud = unitDollars();

  // ============ SPACE 1: TONIGHT'S PICKS — the actual bets ============
  // Exactly the bets the "Recommended bets" tile counts. Nothing else is
  // allowed in this box, so it can never contradict the tile again.
  const propKey = (p, m) => `${String(p || "").toLowerCase()}|${String(m || "").toLowerCase()}`;
  const staleByKey = new Map(sig.stale.filter((s) => s.player)
    .map((s) => [propKey(s.player, s.market), s]));

  // Which game each pick belongs to — matchup + first pitch on every row.
  const gameOf = (r) => ((state.data || {}).games || []).find((g) => propInGame(r, g));
  const propGameLine = (r) => {
    const g = gameOf(r);
    if (!g) return `${teamName(r.team)} vs ${teamName(r.opponent)}`;
    const when = whenLabel(g.date, g.kickoff);
    return `${teamName(g.away)} @ ${teamName(g.home)}`
      + (g.doubleheader ? ` · DH Game ${g.game_number || 1}` : "")
      + (when ? ` · ${when}` : "");
  };

  const picks = [];
  for (const b of sig.sharpBets) {
    // Show the ACTUAL numbers behind the gap (the first reason carries
    // them), so a big EV can be eyeballed instead of trusted.
    const anchor = (b.reasons || []).find((x) => String(x).startsWith("Sharp anchor"));
    picks.push({ tag: "SHARP", color: "var(--cyan)", quality: 95 + (b.ev_per_unit || 0),
      label: `${b.headline} · ${b.matchup} ${american(b.odds)}`,
      game: whenLabel(b.date, b.kickoff),
      metric: `${signedPct(b.ev_per_unit)} EV`, stake: b.stake_units, grade: b.grade,
      why: anchor || "sharp-anchor price gap — backtested +13.5% against real closes" });
  }
  for (const b of sig.modelBets) {
    picks.push({ tag: "GAME", color: "var(--brand)", quality: b.quality || b.confidence * 10 || 0,
      label: `${b.headline} · ${b.matchup} ${american(b.odds)}`,
      game: whenLabel(b.date, b.kickoff),
      metric: signedPct(b.edge), stake: b.stake_units, grade: b.grade,
      why: "game bet that cleared every gate" });
  }
  for (const r of sig.props) {
    const twin = staleByKey.get(propKey(r.player, r.market));
    picks.push({ tag: "PROP", color: "var(--brand)", quality: r.quality || r.confidence * 10 || 0,
      label: `${r.player} ${r.side} ${r.line} ${r.market_label} ${american(r.odds)} (${r.book})`,
      game: propGameLine(r),
      metric: signedPct(r.edge), stake: r.stake_units, grade: r.grade,
      why: (r.quality != null ? `quality ${r.quality}/100 · Tier ${r.tier} · ${r.volatility}` : "cleared every gate")
        + (twin ? ` · BONUS: ${twin.book} is lagging the field at ${american(twin.odds)} — take the cheaper price` : "") });
  }
  picks.sort((a, b) => b.quality - a.quality);

  // Journaled bets whose pick no longer clears the bar at the CURRENT
  // number. A bet doesn't unhappen when the line moves, so it stays on
  // this board — placed price and live price side by side — instead of
  // silently vanishing into the Live tab.
  const nrm = (s) => String(s || "").toLowerCase().trim();
  const onKeys = new Set();
  sig.props.forEach((r) => onKeys.add(`${nrm(r.player)}|${nrm(r.market)}`));
  [...sig.sharpBets, ...sig.modelBets].forEach((b) =>
    [b.team, b.player, b.pick].forEach((t) => t && onKeys.add(`${nrm(t)}|${nrm(b.market)}`)));
  const ridden = ((state.data || {}).live_picks || [])
    .filter((r) => r.phase === "upcoming" && r.status !== "unmapped"
      && !onKeys.has(`${nrm(r.player)}|${nrm(r.market)}`))
    .map((b) => ({ b,
      cur: ((state.data || {}).recommendations || []).find((r) =>
        nrm(r.player) === nrm(b.player) && nrm(r.market) === nrm(b.market)) }));

  const perf = rec.overall || {};
  const journalNote = perf.settled
    ? `The journal so far: ${perf.wins}-${perf.losses} (${signedPct(perf.roi || 0)} ROI) — every pick below is graded there nightly.`
    : "Every pick below is journaled at its real price and graded nightly on the Record page.";

  const pickRow = (p, i) => `
    <div style="display:flex;gap:12px;align-items:flex-start;padding:12px 14px;
                border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="opacity:.45;min-width:18px;font-weight:700">${i + 1}</span>
      <span class="grade ${gradeClass(p.grade)}" style="flex-shrink:0">${escapeHtml(p.grade || "")}</span>
      <span style="flex:1;min-width:0"><strong>${escapeHtml(p.label)}</strong>
        ${p.game ? `<span style="display:block;font-size:var(--fs-sm);margin-top:2px">${(SPORT_META[state.sport] || {}).logo || ""} ${escapeHtml(p.game)}</span>` : ""}
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${escapeHtml(p.why)}</span></span>
      <span style="text-align:right;white-space:nowrap"><span style="font-weight:800">${escapeHtml(p.metric)}</span>
        ${p.stake > 0 ? `<span style="display:block;color:var(--good);font-size:var(--fs-sm);font-weight:700">${
          ud > 0 ? money(stakeDollars(p.stake)) + " · " : ""}${p.stake.toFixed(2)}u</span>` : ""}</span>
    </div>`;

  const asOf = ((state.data || {}).odds_status || {}).at;
  const prePrice = prePriceHeadline();
  const picksBlock = picks.length ? `
    <div class="card" style="padding:0;border-left:3px solid var(--good)">
      <p style="padding:10px 14px 6px;margin:0;font-size:var(--fs-sm);color:var(--text-mute)">
        <b style="color:var(--text)">${picks.length} pick${picks.length === 1 ? "" : "s"} tonight — this is the whole list.</b>
        Same count as the tile above, ranked by quality. ${escapeHtml(journalNote)}${
        asOf ? ` Prices are from the ${escapeHtml(asOf)} odds pull — always confirm the number still stands before betting.` : ""}
        Every journaled bet is tracked on the <b style="color:var(--text)">Live</b> tab through settlement.</p>
      ${picks.map(pickRow).join("")}
      <details class="rec-disclose" style="margin:2px 14px 10px">
        <summary>Why only ${picks.length}? — where the other props died</summary>
        ${censusFunnelHTML()}
      </details>
    </div>` : `
    <div class="card" style="border-left:3px solid var(--warn)">
      <p style="margin:0;font-weight:800;font-size:var(--fs-lg)">${prePrice
        || "No qualifying plays at current numbers."}</p>
      <p style="margin:6px 0 0;color:var(--text-mute);font-size:var(--fs-md)">${prePrice
        ? `The gate counts below ran against the last pull, not today's prices — read them
           as stale, not as a verdict on today's slate.`
        : `That sentence is the system working, not failing — every market tonight either
           missed the tier's edge bar, failed a gate, or graded below 70. Loosening the
           sliders shows what was held and why.`}</p>
      ${censusFunnelHTML()}
    </div>`;

  // ======= SPACE 2: tracked signals — measurements, NOT picks =======
  const signals = [];
  for (const a of sig.arbs.slice(0, 2)) {
    signals.push({ tag: "ARB",
      label: `${a.bet}: Over ${a.over.line} ${american(a.over.odds)} (${a.over.book}) + Under ${a.under.line} ${american(a.under.odds)} (${a.under.book})`,
      metric: `+${(a.profit_pct * 100).toFixed(1)}%`,
      why: "locked profit whichever way it lands — price math, no forecast; not journaled (nothing to grade)" });
  }
  const lo = rec.loose_sampler || {};
  const looseRec = (lo.wins || 0) + (lo.losses || 0) > 0
    ? ` · sampler so far ${lo.wins}-${lo.losses} (${signedPct(lo.roi || 0)})` : "";
  for (const nm of ((state.data || {}).near_miss || []).slice(0, 3)) {
    signals.push({ tag: "NEAR",
      label: `${nm.player} ${nm.side} ${nm.line} ${nm.market_label} ${american(nm.odds)} (${nm.book})`,
      metric: signedPct(nm.edge),
      why: `missed the bar by a hair (${nm.missed_by}) — paper-tracked in the`
        + ` looser-gates sampler${looseRec}; if that bucket profits over 100+ graded,`
        + ` the real gates loosen` });
  }
  const st = rec.stale_flags || {};
  const staleRec = (st.wins || 0) + (st.losses || 0) > 0
    ? ` · sampler so far ${st.wins}-${st.losses} (${signedPct(st.roi || 0)})` : "";
  const pickKeys = new Set(sig.props.map((r) => propKey(r.player, r.market)));
  for (const s of sig.stale.filter((x) => !pickKeys.has(propKey(x.player, x.market))).slice(0, 3)) {
    signals.push({ tag: "STALE",
      label: `${s.bet} ${american(s.odds)} (${s.book}) — the field prices it ${american(s.fair_odds)}`,
      metric: `+${(s.gap_pts || 0).toFixed(1)}pt`,
      why: `one book lagging the field — beat the close 64.8% of 30k quotes${staleRec} · paper-tracked at 0.1u` });
  }
  for (const p of sig.hr.slice(0, 2)) {
    signals.push({ tag: "HR",
      label: `${p.player} — ${p.market_label} ${american(p.odds)} (${p.book})`,
      metric: pct(p.model_prob),
      why: "strict HR tier (+11% ROI over its first 214) · tracked in the long-shot bucket, never a headline pick" });
  }
  const signalsBlock = signals.length ? `
    <details class="rec-disclose" style="margin-top:10px">
      <summary>Tracked signals tonight (${signals.length}) — measurements, not picks</summary>
      <div style="padding:0">
        <p style="margin:6px 0 8px;font-size:var(--fs-sm);color:var(--text-mute)">These are NOT
        recommendations. They're the signal families the site paper-tracks in quarantined
        Record buckets — each has a fixed promotion bar, and none is money tonight.</p>
        ${signals.map((s) => `
          <div style="display:flex;gap:10px;align-items:flex-start;padding:8px 4px;
                      border-bottom:1px solid rgba(255,255,255,.05);opacity:.75">
            <span class="chip" style="min-width:50px;text-align:center;flex-shrink:0">${s.tag}</span>
            <span style="flex:1;min-width:0;font-size:var(--fs-sm)">${escapeHtml(s.label)}
              <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${escapeHtml(s.why)}</span></span>
            <span style="font-weight:700;font-size:var(--fs-sm);white-space:nowrap">${escapeHtml(s.metric)}</span>
          </div>`).join("")}
      </div>
    </details>` : "";

  // ======= the bets already placed whose price moved off the bar =======
  const riddenBlock = ridden.length ? `
    <div class="card" style="padding:0;border-left:3px solid var(--warn);margin-top:10px">
      <p style="padding:10px 14px 6px;margin:0;font-size:var(--fs-sm);color:var(--text-mute)">
        <b style="color:var(--text)">Riding from earlier pulls (${ridden.length}).</b>
        These WERE tonight's picks — journaled when they cleared the bar. The line has
        moved since, and at the current number they no longer qualify, so: the bet rides
        as placed, but don't add more at today's price. Tracked live on the Live tab.</p>
      ${ridden.map(({ b, cur }) => `
        <div style="display:flex;gap:12px;align-items:flex-start;padding:11px 14px;
                    border-bottom:1px solid rgba(255,255,255,.05);opacity:.85">
          <span class="chip" style="flex-shrink:0">OPEN</span>
          <span style="flex:1;min-width:0">
            <strong>${b.market === "moneyline"
              ? `${escapeHtml(teamName(b.player))} Moneyline`
              : `${escapeHtml(b.player)} ${escapeHtml(b.side)} ${b.line} ${escapeHtml(b.market_label)}`}</strong>
            <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">
              placed ${american(b.odds)}${cur && cur.odds != null
                ? ` · current best ${american(cur.odds)}${cur.line != null && Number(cur.line) !== Number(b.line)
                    ? ` (line now ${cur.line})` : ""} — doesn't clear the bar at this number`
                : ` · no live quote for this market right now`}</span>
          </span>
          <span style="text-align:right;white-space:nowrap;font-size:var(--fs-sm);color:var(--text-mute)">
            ${b.stake_units > 0 ? `${Number(b.stake_units).toFixed(2)}u<br>` : ""}riding</span>
        </div>`).join("")}
    </div>` : "";

  if (!picks.length && !signals.length && !ridden.length) { host.innerHTML = ""; return; }
  host.innerHTML = `
    <div class="section-title">Tonight's picks
      <span class="sub">— the one designated space for what we'd actually bet. If it isn't
      in this box, it isn't a pick.</span></div>
    ${picksBlock}
    ${riddenBlock}
    ${signalsBlock}`;
}

/* ============================================================
   Live picks — journaled PRE-GAME picks whose games are in progress,
   with the player's current stat line. The model never bets in-play;
   this answers "how are the bets we already made doing?" the moment
   the games start, instead of going dark until settlement.
   ============================================================ */
/* The gate-census funnel — why tonight's props died, gate by gate. Rendered
   inside the empty state AND as a collapsed drawer under a non-empty picks
   list: "890 analyzed → 1 recommended" must always be explainable. */
/* "753 props with no book price" reads like a dead feed at 9 AM. It isn't:
   books post hitter props close to first pitch, and our own pacer holds the
   paid pulls for the same window (spending credits at breakfast buys proxy
   lines and silence). Both facts lived only in the launcher's terminal —
   the one place you can't see from a phone at work. So say them here, on
   the number that prompts the question. */
/* Before the day's pricing window opens, an empty board is the SCHEDULE, not
   a verdict — and the two are not interchangeable. "Every market missed the
   edge bar" is a claim about today's prices; at 11 AM there are no today's
   prices to have missed anything, because the books have not posted hitter
   lines and the pacer is deliberately holding its credits for the window.
   Saying the wrong one of those makes a working system look broken and, worse,
   would make a genuinely dead feed indistinguishable from a normal morning.
   Returns "" once the window is open, and the old sentence stands. */
function prePriceHeadline() {
  const os = (state.data || {}).odds_status || {};
  const opens = os.window_opens_at ? os.window_opens_at * 1000 : 0;
  if (!opens || Date.now() >= opens) return "";
  const t = new Date(opens).toLocaleTimeString([],
    { hour: "numeric", minute: "2-digit" });
  return `Today's book prices haven't been pulled yet — the window opens ${t}.`;
}

function oddsClockHTML() {
  const os = (state.data || {}).odds_status || {};
  /* A bare "3:32 PM" on a timestamp from YESTERDAY reads as impossible at
     11 AM, and the only conclusion available is that the feed is broken.
     The whole job of this line is answering "how fresh is this" — the day
     it belongs to is part of that answer, not decoration. */
  const midnight = (ms) => new Date(ms).setHours(0, 0, 0, 0);
  const clock = (ts) => {
    const d = new Date(ts * 1000);
    const t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    const days = Math.round((midnight(Date.now()) - midnight(ts * 1000)) / 864e5);
    if (days <= 0) return t;
    if (days === 1) return `${t} <span style="opacity:.8">yesterday</span>`;
    return `${t} <span style="opacity:.8">on ${d.toLocaleDateString([],
      { month: "short", day: "numeric" })}</span>`;
  };
  const opens = os.window_opens_at ? os.window_opens_at * 1000 : 0;
  const waiting = opens && Date.now() < opens;
  const bits = [];
  if (os.priced_at) bits.push(`last pulled <b>${clock(os.priced_at)}</b>`);
  if (opens) {
    bits.push(waiting
      ? `today's pricing starts <b>${clock(os.window_opens_at)}</b>`
      : `pre-game window is open`);
  }
  /* The question this box exists to answer, an hour before first pitch, is
     "why is nothing priced" — and the answer is usually that the next paid
     pull is not due yet. That was only ever visible in the terminal. */
  const due = os.next_pull_at ? os.next_pull_at * 1000 : 0;
  if (due && due > Date.now()) {
    bits.push(`next paid pull <b>${clock(os.next_pull_at)}</b>`);
  }
  if (!bits.length) return "";
  /* Before the window, "no book price" is not a symptom of anything — it is
     the schedule. Say that as the first clause rather than leaving it to be
     inferred from two timestamps, because the reader arriving at this box
     has already decided something is wrong. */
  const why = waiting
    ? `Nothing is broken: the pre-game window opens 2½ hours before first
       pitch, which is both when the books post hitter lines and when our own
       pacer spends credits. Pulling at breakfast buys proxy lines and an
       empty board. Until then this page stays thin by design`
    : `Most of these fill in as the books post hitter lines near first pitch`;
  return `<div style="margin-top:6px;font-size:var(--fs-sm);color:var(--text-mute)">
    Book prices: ${bits.join(" · ")}. ${why} — the rest of the board (scores,
    lineups, live tracking) refreshes every minute regardless.</div>`;
}

/* The census keys that are counts of props, as opposed to bookkeeping — so
   "biggest reason" never reports a total as if it were a cause. */
function censusBuckets() {
  const gc = (state.data || {}).gate_census || {};
  return Object.entries(gc).filter(([k, v]) =>
    typeof v === "number" && v > 0 && !["recommended", "props_built",
      "calibration_markets", "no_price_markets"].includes(k));
}

function censusTotal() {
  return censusBuckets().reduce((a, [, v]) => a + v, 0);
}

function biggestCensusBucket() {
  const rows = censusBuckets().sort((a, b) => b[1] - a[1]);
  if (!rows.length) return ["", 0];
  const names = { no_real_price: "no real book price yet",
                  no_history: "no stored game log for that player" };
  return [names[rows[0][0]] || rows[0][0], rows[0][1]];
}

function censusFunnelHTML() {
  const gc = (state.data || {}).gate_census;
  if (!gc) return "";
  const names = { no_real_price: "no real book price yet",
    longshot_board: "home runs — live on the Long Shots board by design",
    credibility: "model-vs-market gap too big to trust (>10% raw = bad data)",
    calibration: "market's calibration unreliable — closed until refit",
    tier_edge_bar: "edge under the tier's minimum",
    price_net: "price doesn't clear break-even",
    quality_under_70: "quality grade under 70",
    held_by_rules: "held by rules (lineups pending, IL, live game, juice)",
    // Hoops: the two the build drops before the model ever sees them.
    no_history: "no stored game log for this player yet",
    props_built: "props built from history" };
  // TWO STAGES, not one list. The first two buckets are dropped by the BUILD
  // before the model runs; everything else is a prop the model priced and
  // then rejected. Merged into one column they read as contradictory — a
  // WNBA board showing "26 props analyzed" above "no real book price 761"
  // looks like 761 of 26, when it is really 787 built → 26 priced → 0 clear.
  const PRE = ["no_history", "no_real_price"];
  const line = ([k, v]) => `<div style="display:flex;justify-content:space-between;
      gap:10px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.05);
      font-size:var(--fs-sm)">
    <span style="color:var(--text-mute)">${escapeHtml(names[k] || k)}</span>
    <span style="font-weight:700">${v}</span></div>`;
  const live = Object.entries(gc).filter(([k, v]) => typeof v === "number"
    && v > 0 && k !== "recommended" && k !== "calibration_markets");
  const pre = live.filter(([k]) => PRE.includes(k));
  const gates = live.filter(([k]) => !PRE.includes(k));
  const reached = gates.reduce((n, [, v]) => n + v, 0)
    + (Number(gc.recommended) || 0);
  const sub = (t) => `<div style="font-size:var(--fs-xs);letter-spacing:.06em;
      text-transform:uppercase;color:var(--text-mute);margin:8px 0 2px">${t}</div>`;
  const rows = !live.length ? "" : [
    pre.length ? sub("Never reached the model") + pre.map(line).join("") : "",
    gates.length
      ? sub(`Priced and rejected — ${reached} prop(s) reached the model`)
        + gates.map(line).join("")
      : "",
  ].join("");
  const closed = (gc.calibration_markets || []).length
    ? `<div style="margin-top:6px;font-size:var(--fs-sm);color:var(--warn)">Closed by calibration:
       ${gc.calibration_markets.map(escapeHtml).join(", ")} — the nightly refit reopens
       a market when its fit lands back inside the search range.</div>` : "";
  // The biggest bucket deserves its own breakdown: "no real book price" is
  // mostly the shape of the books' menu (we project every hitter in the
  // lineup; books post lines for a subset), not a broken feed.
  const npm = gc.no_price_markets || {};
  const npmRows = Object.entries(npm).sort((a, b) => b[1] - a[1])
    .map(([m, n]) => `${escapeHtml(m)} ${n}`).join(" · ");
  const noPrice = npmRows
    ? `<div style="margin-top:6px;font-size:var(--fs-sm);color:var(--text-mute)">
       Unpriced by market: ${npmRows}. We project every hitter in the lineup;
       books post lines for a subset — that gap is normal, not a broken feed.
       A price we <em>paid</em> for and failed to match is a different thing:
       the build prints those as a name-match warning.</div>${oddsClockHTML()}` : "";
  return rows ? `<div style="margin-top:10px">
    <div style="font-size:var(--fs-sm);font-weight:700;margin-bottom:2px">Where tonight's props died</div>
    ${rows}${noPrice}${closed}</div>` : "";
}

function renderLivePicks() {
  const host = document.getElementById("live-picks");
  if (!host) return;
  const rows = (state.data || {}).live_picks || [];
  const elsewhere = (state.data || {}).open_elsewhere || 0;
  const trackerErr = (state.data || {}).live_picks_error;
  if (trackerErr) {
    // A broken tracker must say so — an empty space reads as "no bets".
    host.innerHTML = `<div class="card" style="border-left:3px solid var(--warn);margin-top:8px">
      <p style="margin:0;font-size:var(--fs-md)">${icon('warn')} Open-bet tracker hit an error this build:
      <code>${escapeHtml(trackerErr)}</code> — open bets still settle normally; see the Record page.</p></div>`;
    return;
  }
  if (!rows.length && !elsewhere) {
    // A full tab now — an empty day says so instead of rendering nothing.
    host.innerHTML = `
      <div class="section-title">${iconMark("target")} Open bets
        <span class="sub">— every journaled bet on today's card, tracked while its game runs</span></div>
      <div class="card"><p class="loading">No open bets on today's card. A pick journals the
        moment it's recommended and lives here until it settles — live progress bars, at-bat
        situation, and provisional grades as the games run.</p></div>`;
    return;
  }

  const ml = (r) => r.market === "moneyline";
  const betTxt = (r) => ml(r)
    ? `${escapeHtml(teamName(r.player))} Moneyline`
    : `${escapeHtml(r.player)} ${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}`;
  // What the board recommends at the CURRENT prices — so a journaled bet
  // whose pick has since dropped off (line moved, gate re-closed) can say
  // so instead of looking like a contradiction with Tonight's Picks.
  const sig = tonightSignals();
  const onBoard = new Set();
  const norm = (s) => String(s || "").toLowerCase().trim();
  sig.props.forEach((p) => onBoard.add(`${norm(p.player)}|${norm(p.market)}`));
  // Long shots are a board of their own. Leaving them out here marked every
  // tracked home-run bet "no longer on the board" while it sat, recommended,
  // on the Long Shots page two tabs over.
  (state.data.long_shots || []).forEach(
    (p) => onBoard.add(`${norm(p.player)}|${norm(p.market)}`));
  [...sig.sharpBets, ...sig.modelBets].forEach((b) => {
    [b.team, b.player, b.pick].forEach((t) => {
      if (t) onBoard.add(`${norm(t)}|${norm(b.market)}`);
    });
  });
  const offBoard = (r) => r.phase === "upcoming" && r.status !== "unmapped"
    && !onBoard.has(`${norm(r.player)}|${norm(r.market)}`);
  const statusBits = (r) => {
    if (r.status === "cleared")
      return `<span style="color:var(--good);font-weight:800">${icon('check')} CLEARED</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${r.current} so far — over ${r.line} is locked</span>`;
    if (r.status === "busted")
      return `<span style="color:var(--bad);font-weight:800">${icon('cross')} BUSTED</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${r.current} already — under ${r.line} can't cash</span>`;
    if (r.status === "won_pending")
      return `<span style="color:var(--good);font-weight:800">${icon('check')} WON</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${ml(r) ? "final" : `finished at ${r.current}`} — settles officially overnight</span>`;
    if (r.status === "lost_pending")
      return `<span style="color:var(--bad);font-weight:800">${icon('cross')} LOST</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${ml(r) ? "final" : `finished at ${r.current}`} — settles officially overnight</span>`;
    if (r.status === "push_pending")
      return `<span style="font-weight:800">${icon('dash')} PUSH</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">landed exactly on ${r.line}</span>`;
    if (r.status === "final_pending")
      return `<span style="color:var(--text-mute);font-weight:700">FINAL</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">awaiting the overnight settle</span>`;
    if (r.status === "upcoming")
      return `<span style="color:var(--text-mute);font-weight:700">UPCOMING</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${escapeHtml(whenLabel(r.game.date, r.game.kickoff) || "today")}</span>`;
    if (r.status === "unmapped")
      return `<span style="color:var(--warn);font-weight:700">OPEN</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">couldn't map to a game this cycle — still settles overnight</span>`;
    if (r.current != null) {
      const needs = r.side === "OVER"
        ? `needs ${Math.max(1, Math.ceil(r.line - r.current))} more`
        : `must stay at or under ${Math.floor(r.line)}`;
      return `<span style="font-weight:800">${r.current} so far</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${needs}</span>`;
    }
    return `<span style="color:var(--text-mute)">in play</span>`;
  };
  const gameLine = (g) => {
    if (!g || !g.home) return "";
    const score = (g.home_score != null)
      ? `${escapeHtml(teamName(g.away))} ${g.away_score}–${g.home_score} ${escapeHtml(teamName(g.home))}`
      : `${escapeHtml(teamName(g.away))} @ ${escapeHtml(teamName(g.home))}`;
    return `${score}${g.state === "final" ? " · Final" : g.period ? ` · ${escapeHtml(g.period)}` : ""}${
      g.doubleheader ? ` · DH Game ${g.game_number || 1}` : ""}`;
  };
  // The live situation strip: who's at the plate, outs, runners — plus a
  // loud badge when the batter IS this row's player.
  const sameName = (a, b) =>
    String(a || "").toLowerCase().trim() === String(b || "").toLowerCase().trim();
  const situationLine = (r) => {
    const s = (r.game || {}).situation;
    if (!s || r.phase !== "live") return "";
    const on = ["first", "second", "third"]
      .map((b, i) => (s.bases || {})[b] ? ["1st", "2nd", "3rd"][i] : null)
      .filter(Boolean);
    const runners = on.length === 3 ? "bases loaded"
      : on.length ? `runner${on.length > 1 ? "s" : ""} on ${on.join(" & ")}`
      : "bases empty";
    const mine = sameName(s.batter, r.player);
    const batter = s.batter
      ? (mine
          ? `<b style="color:var(--warn)">${iconMark("dot", 10)}${escapeHtml(s.batter)} — YOUR PICK — at the plate</b>`
          : `${iconMark("dot", 10)}${escapeHtml(s.batter)} at bat`)
      : "";
    const onDeck = !mine && s.on_deck && sameName(s.on_deck, r.player)
      ? ` · <b style="color:var(--warn)">${escapeHtml(r.player)} on deck</b>` : "";
    return `<span style="display:block;font-size:var(--fs-sm);margin-top:2px;color:var(--text-mute)">
      ${batter}${onDeck} · ${s.outs} out${s.outs === 1 ? "" : "s"} · ${runners}
      · ${s.balls}-${s.strikes} count</span>`;
  };
  // Sportsbook-style progress bar: fill = where the stat is now, tick = the
  // line. Green once an over is home, red once an under is dead, neutral
  // while it's still in the balance. Only for rows with a countable stat —
  // moneylines have no bar (the score line tells that story).
  const progressBar = (r) => {
    if (r.current == null || !(r.line > 0) || r.market === "moneyline") return "";
    // Span the bar to the first whole number past the line (what an OVER
    // actually needs), stretched if the stat has already sailed past it.
    const target = Math.max(Math.ceil(r.line + 0.001), 1);
    const span = Math.max(target, r.current, 1);
    const fillPct = Math.min(100, Math.max(0, (r.current / span) * 100));
    const tickPct = Math.min(98.5, (r.line / span) * 100);
    const good = r.status === "cleared" || r.status === "won_pending";
    const bad = r.status === "busted" || r.status === "lost_pending";
    const color = good ? "var(--good)" : bad ? "var(--bad)" : "var(--brand)";
    return `
      <span style="display:block;position:relative;margin-top:7px;height:5px;border-radius:3px;
                   background:rgba(255,255,255,.10);max-width:420px">
        <span style="position:absolute;left:0;top:0;bottom:0;width:${fillPct}%;
                     border-radius:3px;background:${color};transition:width .4s"></span>
        <span style="position:absolute;left:${tickPct}%;top:-3px;bottom:-3px;width:2px;
                     border-radius:1px;background:var(--text-mute)"></span>
      </span>
      <span style="display:block;font-size:var(--fs-xs);color:var(--text-mute);margin-top:3px">
        ${r.current} now · line ${r.line}</span>`;
  };
  const nLive = rows.filter((r) => r.phase === "live").length;

  host.innerHTML = `
    <div class="section-title">${nLive
        ? `<span style="color:var(--bad)">${icon('dot')}</span>`
        : `<span style="color:var(--brand)">${icon('dot')}</span>`} Open bets
      <span class="sub">— every journaled bet on today's card: live with real-time progress,
      finished awaiting the official settle, or waiting on first pitch. Never new in-play
      bets — everything here was placed pre-game.</span></div>
    <div class="card" style="padding:0;border-left:3px solid ${nLive ? "var(--bad)" : "var(--brand)"}">
      ${rows.map((r) => `
        <div style="display:flex;gap:12px;align-items:center;padding:11px 14px;
                    border-bottom:1px solid rgba(255,255,255,.05)${r.phase === "upcoming" ? ";opacity:.75" : ""}">
          ${r.phase === "live" ? `<span class="live-dot" style="flex-shrink:0"></span>`
            : `<span style="width:8px;flex-shrink:0"></span>`}
          <span style="flex:1;min-width:0">
            <strong>${betTxt(r)}</strong>
            <span style="color:var(--text-mute)"> · placed ${american(r.odds)}${
              r.stake_units > 0 ? ` · ${Number(r.stake_units).toFixed(2)}u` : ""}</span>
            <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${gameLine(r.game)}</span>
            ${situationLine(r)}
            ${offBoard(r) ? `<span style="display:block;font-size:var(--fs-xs);color:var(--warn);margin-top:2px">
              ${icon('warn')} the price has moved off the bar since this was journaled — riding at
              ${american(r.odds)} as placed (also listed under Tonight's Picks).</span>` : ""}
            ${progressBar(r)}
          </span>
          <span style="text-align:right;white-space:nowrap">${statusBits(r)}</span>
        </div>`).join("")}
      <p style="padding:8px 14px;margin:0;font-size:var(--fs-xs);color:var(--text-mute)">
        ${rows.length} open bet(s) on today's card${elsewhere
          ? ` · ${elsewhere} older open bet(s) awaiting results — graded on the Record page`
          : ""}. A bet journals the moment it's recommended and stays here until it
        settles — even if the pick later drops off Tonight's Picks because prices moved.
        Stat lines update with the board's refresh cycle; every bet settles
        officially against ingested final results overnight.</p>
    </div>`;
}

/* ============================================================
   Team form — hot & cold from our own ingested results (MLB).
   Track → measure → adjust, in that order: the audit line says whether
   hot form has predicted anything, and the sampler line says how backing
   hot teams at REAL prices is actually going. No vibes.
   ============================================================ */
async function renderTeamForm() {
  const host = document.getElementById("team-form");
  if (!host) return;
  const tf = (state.data || {}).team_form;
  if (!tf || (!(tf.hot || []).length && !(tf.cold || []).length)) {
    host.innerHTML = "";
    return;
  }
  const rec = await loadRecordOnce();
  const fm = rec.form_sampler || {};
  const gradedN = (fm.wins || 0) + (fm.losses || 0);
  const sampler = gradedN
    ? `sampler: backing hot teams at real prices is ${fm.wins}-${fm.losses} `
      + `(${signedPct(fm.roi || 0)} ROI) — graded on the Record page`
    : `sampler journals the hot side's moneyline in every hot-vs-cold matchup `
      + `at the real price — grades on the Record page`;
  const row = (r, tone) => `
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;
                padding:9px 4px;border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="display:flex;align-items:center;gap:8px;flex:1;min-width:150px">
        ${teamMark(r.team, 18)} <strong>${escapeHtml(teamName(r.team))}</strong></span>
      <span style="white-space:nowrap">${r.w}-${r.l}</span>
      <span class="val ${tone}" style="white-space:nowrap;min-width:88px;text-align:right"
            title="Run differential per game over the window minus the team's own season number — hot relative to itself, not the league">
        ${r.delta_diff >= 0 ? "+" : ""}${r.delta_diff.toFixed(1)} r/g</span>
      <span style="min-width:34px;text-align:right;color:${r.streak > 0 ? "var(--good)" : "var(--bad)"}">
        ${r.streak > 0 ? `W${r.streak}` : r.streak < 0 ? `L${-r.streak}` : "—"}</span>
    </div>`;
  const col = (title, icon, rows, tone) => `
    <div class="trend-col">
      <h3>${mark} ${title}</h3>
      ${rows.length ? rows.map((r) => row(r, tone)).join("")
        : `<div class="empty" style="padding:18px">Nobody qualifies.</div>`}
    </div>`;
  host.innerHTML = `
    <div class="section-title">Team form — last ${tf.window_days || 7} days
      <span class="sub">— from our own ingested results, refreshed nightly. Tracked and
      measured before it's ever allowed to move a bet.</span></div>
    <div class="trend-grid" style="grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr))">
      ${col("Running hot", iconMark("hot"), tf.hot || [], "pos")}
      ${col("Running cold", iconMark("cold"), tf.cold || [], "neg")}
    </div>
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:8px">
      ${tf.audit && tf.audit.verdict ? `Season audit: ${escapeHtml(tf.audit.verdict)}. ` : ""}${escapeHtml(sampler)}.</p>`;
}

/* ============================================================
   Game bets — grouped by market (moneyline / spread / total)
   ============================================================ */
function passesGameBet(r) {
  // A conditional is not a bet. It clears every filter on the numbers —
  // that is the point of publishing it — but counting it as recommended
  // would put "11 game bets — all journaled" on a page where five were
  // journaled and six are waiting on a quarterback.
  return r.confidence >= state.minConf && r.edge * 100 >= state.minEdge
    && r.odds >= state.maxJuice && r.grade !== "Pass" && !r.conditional;
}

const GAMEBET_GROUPS = [
  ["moneyline", "Moneyline"], ["spread", "Spread"],
  ["total", "Game total"], ["team_total", "Team total"],
];

function renderIncentives() {
  // NFL only: contract-incentive chases — "needs 62 more receiving yards
  // for $500,000" — measured against our own ingested season logs. Late
  // in the year this is usage information the player's own sideline acts
  // on; the tracker shows it, and matching prop cards carry the angle as
  // a reason. It never moves a probability.
  const host = document.getElementById("incentive-watch");
  if (!host) return;
  const inc = (state.data || {}).incentives;
  if (state.sport !== "nfl" || !inc) { host.innerHTML = ""; return; }
  const rows = inc.entries || [];
  const money = (v) => v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M`
    : `$${Math.round(v / 1000)}K`;
  const tone = (s) => ({ "hit": "var(--good)", "on pace": "var(--cyan)",
    "needs a push": "var(--warn)", "long shot": "var(--bad)",
    "missed": "var(--text-mute)" }[s] || "var(--text-mute)");
  const body = rows.length ? rows.map((r) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:8px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml(r.team || "")}</span>
      <span style="flex:1;min-width:150px;font-weight:600">${escapeHtml(r.player || "")}</span>
      <span style="min-width:130px">${(r.total ?? 0).toLocaleString()} of ${(r.threshold ?? 0).toLocaleString()} ${escapeHtml(r.stat_label || "")}</span>
      <span style="font-variant-numeric:tabular-nums" title="What he still needs, against his own per-game pace (${r.pace ?? "—"})">
        ${r.need > 0 ? `needs ${r.need.toLocaleString()} in ${r.games_left} game(s)` : "done"}</span>
      <span style="font-weight:700">${money(r.bonus_usd ?? 0)}</span>
      <span class="chip" style="color:${tone(r.status)}">${escapeHtml(r.status || "")}</span>
    </div>`).join("") : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      ${escapeHtml(inc.note || "No incentive chases on file.")}</p>`;
  host.innerHTML = `
    <div class="section-title">Incentive watch
      <span class="sub">— contract money on the line down the stretch. Each
      chase is measured from our own ingested game logs — season total,
      distance, and his real per-game pace — because a team feeds a player
      who is close, and the books are slow to price that. Picks touching a
      live chase say so on their card.</span></div>
    <div class="card" style="padding:0">${body}</div>`;
}

function renderRestWatch() {
  // NFL only: who is safe, who is dead, who might sit. Computed from our
  // own finals with tiebreaker-free certainty rules — a board should be
  // late before it is wrong — plus announced rests from the curated
  // table. Announced rest gates matching props; computed statuses warn.
  const host = document.getElementById("rest-watch");
  if (!host) return;
  const pic = (state.data || {}).playoff_picture;
  if (state.sport !== "nfl" || !pic) { host.innerHTML = ""; return; }
  const teams = pic.teams || {};
  const rows = Object.entries(teams)
    .filter(([, s]) => s.status !== "in the hunt" || s.risk)
    .sort(([, a], [, b]) => (b.risk ? 1 : 0) - (a.risk ? 1 : 0)
      || (b.wins ?? 0) - (a.wins ?? 0));
  const tone = (s) => s.risk === "announced rest" ? "var(--bad)"
    : s.risk ? "var(--warn)"
    : s.status.startsWith("clinched") ? "var(--good)"
    : s.status === "eliminated" ? "var(--text-mute)" : "var(--text)";
  const body = rows.length ? rows.map(([t, s]) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:8px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml(t)}</span>
      <span style="min-width:80px;font-variant-numeric:tabular-nums">${s.wins}-${s.losses}${s.ties ? `-${s.ties}` : ""}</span>
      <span style="flex:1;min-width:130px">${escapeHtml(s.status)}</span>
      ${s.risk ? `<span class="chip" style="color:${tone(s)}">${escapeHtml(s.risk)}</span>` : ""}
      ${s.note ? `<span style="color:var(--text-mute)">${escapeHtml(s.note)}</span>` : ""}
    </div>`).join("")
    : pic.active ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      No team has a certain status yet — every race is still live, and this
      board would rather be late than wrong.</p>` : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      ${escapeHtml(pic.note || "")}</p>`;
  host.innerHTML = `
    <div class="section-title">Rest watch
      <span class="sub">— the playoff picture's usage risks. A clinched team
      may rest starters, an eliminated one may shut veterans down, and an
      announced rest flips its props to Pass on this board — a season-usage
      prop on a benched rotation is a stale price, not an edge.</span></div>
    <div class="card" style="padding:0">${body}</div>`;
}

function renderGameBets() {
  const bets = (state.data.game_bets || []).map((r) => ({ ...r, _ok: passesGameBet(r) }));
  // Conditionals always show — a bet you can't see isn't one you can go and
  // confirm — but they render faded, amber and stake-less, because they are
  // not bets yet.
  const visible = bets.filter((r) => (state.showAll ? true : r._ok || r.conditional));
  const title = document.getElementById("gamebets-title");
  const host = document.getElementById("gamebets");
  if (!visible.length) {
    title.style.display = "none";
    host.innerHTML = "";
    return;
  }
  title.style.display = "";
  host.innerHTML = GAMEBET_GROUPS.map(([type, label]) => {
    const rows = visible.filter((b) => b.bet_type === type);
    if (!rows.length) return "";
    return `<div class="gb-group">
        <div class="gb-group-label">${label}<span>${rows.length}</span></div>
        <div class="cards">${rows.map(gameBetCard).join("")}</div>
      </div>`;
  }).join("");
  fillMeters(host);
  host.querySelectorAll(".gb-group .cards").forEach(revealChildren);
}

function gameBetCard(r) {
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const stakeChip = r._ok && r.stake_units > 0
    ? `<span class="chip stake">${stakeTxt}</span>` : "";
  // College football's conditionals: a real number waiting on real news.
  // The would-be stake is shown so it's obvious what a phone call is
  // worth, and it is deliberately NOT in the stake chip — nothing here has
  // been wagered.
  const condChip = r.conditional
    ? `<span class="chip cond" title="${escapeHtml((r.conditions_pending || []).join(" · "))}">${icon('clock')} Conditional`
      + (r.stake_if_confirmed_units > 0
        ? ` · ${r.stake_if_confirmed_units.toFixed(2)}u if confirmed` : "")
      + `</span>` : "";
  const tierChip = r.attention_tier
    ? `<span class="chip tier-${escapeHtml(r.attention_tier)}">${escapeHtml(r.attention_tier)} attention</span>`
    : "";
  const reasons = (r.reasons || []).map(reasonLI).join("");

  // Header (badge + title + sub) varies by bet type; the metrics are shared.
  let mark, title, sub;
  if (r.bet_type === "spread") {
    const ln = `${r.line > 0 ? "+" : ""}${r.line}`;
    mark = teamMark(r.team, 34);
    title = `${escapeHtml(teamName(r.team))} <span class="ml-odds">${ln}</span> <span class="book">${american(r.odds)}</span>`;
    sub = "Spread · cover the number";
  } else if (r.bet_type === "total") {
    const arrow = r.side === "Over" ? "▲" : "▼";
    mark = `<span class="total-badge ${r.side === "Over" ? "over" : "under"}">${arrow}</span>`;
    title = `${escapeHtml(r.side)} ${r.line} <span class="book">${american(r.odds)}</span>`;
    sub = "Total · combined score";
  } else if (r.bet_type === "team_total") {
    mark = teamMark(r.team, 34);
    title = `${escapeHtml(teamName(r.team))} ${escapeHtml(r.side)} ${r.line} <span class="book">${american(r.odds)}</span>`;
    sub = "Team total · this team only";
  } else { // moneyline
    mark = teamMark(r.team, 34);
    title = `${escapeHtml(teamName(r.team))} <span class="ml-odds">${american(r.odds)}</span>`;
    sub = "Moneyline · win outright";
  }

  return `
    <article class="card gamebet ${r._ok ? "" : "faded"}" style="--grade-color:${gradeColor(r.grade)}">
      ${r.live ? `<div class="live-ribbon"><span class="live-dot"></span>LIVE · in-play</div>` : ""}
      <div class="card-head">
        <div class="card-id">${mark}
          <div>
            <div class="player">${title}</div>
            <div class="subtitle">${escapeHtml(r.matchup)}${whenLabel(r.date, r.kickoff) ? ` · ${icon('calendar')} ${escapeHtml(whenLabel(r.date, r.kickoff))}` : ""}</div>
            <div class="pick">${sub}</div>
          </div>
        </div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">Model</div><div class="v">${pct(r.win_prob)}</div></div>
        <div class="metric"><div class="k">Book implied</div><div class="v">${pct(r.fair_prob)}</div></div>
        <div class="metric primary"><div class="k">Edge</div><div class="v ${r.edge >= 0 ? "pos" : "neg"}">${signedPct(r.edge)}</div></div>
      </div>
      ${confMeter(r)}
      ${(r.recent_values || []).length > 2
        ? `<div class="mini" style="margin-top:8px" title="Last ${r.recent_values.length} games — dashed line is the prop line">
             ${sparkline(r.recent_values, { line: r.line, stroke: teamPrimary(r.team), w: 260, h: 46 })}</div>`
        : ""}
      <div class="chips">${stakeChip}${condChip}${tierChip}</div>
      ${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
    </article>`;
}

/* ============================================================
   Recommended view
   ============================================================ */
/* ============================================================
   ONE definition of "what are we betting tonight."
   The stats tiles, Best Bets, the game cards and the boards all read
   from this — never from their own filters — so no two places on the
   site can show different counts for the same question. Props and game
   bets honor the user's sliders; stale flags, long shots and arbs are
   price-structure signals the sliders don't apply to, and they are
   never counted as recommended bets.
   ============================================================ */
function sharpBet(b) {
  return (b.reasons || []).some((r) => r.includes("Sharp anchor"));
}

function tonightSignals() {
  const d = state.data || {};
  const scan = d.market_scan || {};
  const bets = (d.game_bets || []).filter(passesGameBet);
  return {
    props: (d.recommendations || []).filter(passesFilters),
    sharpBets: bets.filter(sharpBet),
    modelBets: bets.filter((b) => !sharpBet(b)),
    arbs: (scan.arbs || []).filter((x) => !x.suspect),
    stale: (scan.stale || []).filter((x) => !x.live && !x.started),
    hr: (d.long_shots || []).filter((x) => !x.live),
  };
}

function renderStats() {
  const d = state.data;
  const sig = tonightSignals();
  const staked = [...sig.props, ...sig.sharpBets, ...sig.modelBets];
  const avgEdge = staked.reduce((s, r) => s + (r.edge || 0), 0) / (staked.length || 1);
  const exposure = staked.reduce((s, r) => s + (r.stake_units || 0), 0);
  const ud = unitDollars();
  const nb = sig.sharpBets.length + sig.modelBets.length;
  // College football prices full-game markets, not props — "18 props
  // analyzed" on a board with no player model is just wrong.
  const cfb = state.sport === "cfb";
  const waiting = (d.game_bets || []).filter((b) => b.conditional).length;
  // ONE OF THESE IS THE ANSWER, AND IT LEADS.
  //
  // Four tiles at one size meant none of them was: measured at 1.000
  // dominance across five boards at both widths — same 30px value, same
  // 307px column, four times over. A reader has to weigh all four to find
  // out which one the page is about.
  //
  // The page is called Recommended and the question it is opened with is
  // "what am I betting tonight". That is this number. Props analyzed is how
  // much was considered to get there, avg edge is how good they are, and
  // exposure is what they cost — all three are context FOR the count, so
  // they read as context.
  //
  // It leads when it is zero too. "No qualifying plays" is this board's
  // most common correct answer and a large honest 0 says so; shrinking it
  // on quiet nights would be the one dishonest version of this layout.
  const tiles = [
    { k: "Recommended bets", to: staked.length, dec: 0, lead: true,
      sub: cfb
        ? `${nb} game bet${nb === 1 ? "" : "s"} journaled`
          + (waiting ? ` · ${waiting} conditional, waiting on a starter` : "")
        : `${sig.props.length} prop${sig.props.length === 1 ? "" : "s"} · ${nb} game bet${nb === 1 ? "" : "s"} — all journaled` },
    { k: cfb ? "Markets priced" : "Props analyzed", to: d.counts.props_analyzed, dec: 0,
      sub: cfb ? `spreads, totals and moneylines across ${(d.games || []).length} game(s)` : "" },
    { k: "Avg edge", to: staked.length ? avgEdge * 100 : 0, dec: 1, suf: "%", pre: avgEdge >= 0 ? "+" : "", cls: "pos" },
    ud > 0
      ? { k: "Suggested exposure", to: exposure * ud, dec: 2, pre: "$", sub: `${exposure.toFixed(2)}u across all ${staked.length} bet(s)` }
      : { k: "Suggested exposure", to: exposure, dec: 2, suf: "u" },
  ];
  const fmt = (t) => (t.pre || "") + Number(t.to).toFixed(t.dec) + (t.suf || "");
  const instant = state.static || state.quiet;
  document.getElementById("stats").innerHTML = tiles.map((t) =>
    `<div class="tile${t.lead ? " lead" : ""}"><div class="k">${t.k}</div>
       <div class="v ${t.cls || ""}" data-to="${t.to}" data-dec="${t.dec}" data-pre="${t.pre || ""}" data-suf="${t.suf || ""}">${instant ? fmt(t) : "0"}</div>
       ${t.sub ? `<div class="tile-sub">${t.sub}</div>` : ""}</div>`
  ).join("");
  if (!instant) document.querySelectorAll("#stats .v[data-to]").forEach(countUp);
}

function renderGames() {
  const games = [...(state.data.games || [])];
  const host = document.getElementById("games");
  if (!games.length) { host.innerHTML = ""; return; }
  // Live games float to the front of the strip.
  const rank = (g) => ((g.live || {}).state === "live" ? 0 : (g.live || {}).state === "final" ? 2 : 1);
  games.sort((a, b) => rank(a) - rank(b));
  host.innerHTML = games.map(gameCard).join("");
  revealChildren(host);
  enableTilt(host);
  host.querySelectorAll(".game-card[data-gid]").forEach((el) => {
    const open = () => openGame(el.dataset.gid);
    el.addEventListener("click", open);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
  });
}

/* A stable handle for one game, safe in a URL hash. Two teams and a date
   identify a slate game uniquely — there is no id in the feed. */
const gameId = (g) => `${g.date || ""}_${g.away}@${g.home}${(g.game_number || 1) > 1 ? `_G${g.game_number}` : ""}`;
const findGame = (gid) => (((state.data || {}).games) || []).find((g) => gameId(g) === gid);

function gameCard(g) {
  const mlb = state.sport === "mlb";
  const nba = state.sport === "nba" || state.sport === "wnba";
  const cfb = state.sport === "cfb";
  const w = g.weather || {};
  const windTxt = mlb && w.wind_dir && !w.dome
    ? `${Math.round(w.wind_mph)}mph ${w.wind_dir}`
    : `${Math.round(w.wind_mph)}mph${w.wind_dir ? " " + w.wind_dir : ""}`;
  // No weather feed runs for college football, and a card that says
  // "NaN°F · NaNmph" is worse than one that says nothing — say what is
  // actually known about the venue instead.
  const cond = nba ? "Indoor hardwood"
    : cfb ? (g.indoor ? "Indoor" : "Outdoor · weather not pulled")
    : w.dome ? "Indoor" : `${Math.round(w.temp_f)}°F · ${windTxt}`;
  // `sub` is now MARKUP, not text, because two of its parts are drawn icons.
  // It used to be handed to escapeHtml at the point of use, which is correct
  // for text and turns an <svg> into visible angle brackets — the exact
  // failure a census over 8 sports found and a census over 2 could not. So
  // the escaping moves here, onto the individual DATA parts, and the caller
  // interpolates the result raw. Anything appended below must escape itself.
  const esc = escapeHtml;
  let sub;
  if (cfb) {
    const bits = [];
    if (g.attention_tier) bits.push(`${esc(g.attention_tier)} attention`);
    if (g.total != null) bits.push(`O/U ${Number(g.total).toFixed(1)}`);
    if (g.spread != null) bits.push(`${esc(teamName(g.spread < 0 ? g.home : g.away))} ${-Math.abs(g.spread)}`);
    if (!g.qb_confirmed) bits.push(`${icon('warn')} QB unconfirmed`);
    sub = bits.join(" · ") || "line not posted yet";
  } else if (nba) {
    const bits = [];
    if (g.total != null) bits.push(`O/U ${Number(g.total).toFixed(1)}`);
    if (g.spread) bits.push(`${esc(teamName(g.spread < 0 ? g.home : g.away))} ${-Math.abs(g.spread)}`);
    sub = bits.join(" · ") || "lines post closer to tip-off";
  } else if (mlb) {
    const bits = [`O/U ${g.total.toFixed(1)}`];
    if (g.park_name) bits.unshift(esc(g.park_name));
    if (g.doubleheader) bits.unshift(`${iconMark("calendar", 12)}DH Game ${esc(g.game_number || 1)}`);
    if (g.lineups_confirmed === false) bits.push(`${icon('warn')} lineups pending`);
    sub = bits.join(" · ");
  } else {
    const favTxt = (g.favorite && g.spread != null)
      ? `${esc(teamName(g.favorite))} −${Math.abs(g.spread).toFixed(1)}` : "";
    const ouTxt = g.total != null ? `O/U ${g.total.toFixed(1)}` : "line not posted yet";
    sub = [favTxt, ouTxt].filter(Boolean).join(" · ");
  }
  const art = mlb ? ballpark(g) : nba ? court(g) : stadium(g);
  // A ranked college team is called by its rank — that IS the identity.
  const ranked = (side) => (cfb && g[`${side}_rank`]
    ? `<span class="cfb-rank">#${g[`${side}_rank`]}</span> ` : "");
  const live = g.live || {};
  const isLive = live.state === "live";
  const isFinal = live.state === "final";
  // Score shown beside each team when the game has started.
  const score = (side) => (live.home_score != null && (isLive || isFinal))
    ? `<b class="score">${side === "home" ? live.home_score : live.away_score}</b>` : "";
  let badge = "";
  if (isLive) {
    badge = `<div class="status-badge live"><span class="live-dot"></span>LIVE
      <span class="per">${escapeHtml(live.period)}${live.clock ? " " + escapeHtml(live.clock) : ""}</span></div>`;
  } else if (isFinal) {
    badge = `<div class="status-badge final">FINAL${live.period && live.period !== "Final" ? " · " + escapeHtml(live.period) : ""}</div>`;
  }
  // MLB live: a mini base-state diamond replaces the outs/runners text.
  // NFL live: the down & distance line.
  let liveDetail = "";
  if (isLive && mlb) {
    const outs = live.outs == null ? 0 : live.outs;
    liveDetail = `
      <div class="live-detail base">
        ${baseDiamond(live.bases, live.outs)}
        <span class="base-label">${outs} out${outs === 1 ? "" : "s"}</span>
      </div>`;
  } else if (isLive && live.detail) {
    liveDetail = `<div class="live-detail"><span class="live-dot sm"></span>${escapeHtml(live.detail)}</div>`;
  }
  // The wind gauge and (for MLB live) the base diamond share the footer row.
  const footer = (nba || cfb)
    ? `<div class="wind-wrap"><span class="cond">${escapeHtml(cond)}</span>${liveDetail}</div>`
    : isLive && mlb
    ? `<div class="wind-wrap live-footer">${windGauge(w)}<span class="cond">${escapeHtml(cond)}</span>${liveDetail}</div>`
    : `<div class="wind-wrap">${windGauge(w)}<span class="cond">${escapeHtml(cond)}</span></div>`;
  // MLB: the probable starters, in the same away-@-home order as the
  // matchup line — the first question a bettor asks about a game, and the
  // model already knows the answer (it prices the matchup off these arms).
  let starters = "";
  if (mlb && g.pitchers && (g.pitchers.away || g.pitchers.home)) {
    const pfmt = (p) => (p && p.name)
      ? `${esc(p.name)}${p.throws || p.xera != null
          ? ` <span class="p-detail">(${[p.throws ? esc(p.throws) + "HP" : "",
              p.xera != null ? Number(p.xera).toFixed(2) + " xERA" : ""]
              .filter(Boolean).join(" · ")})</span>` : ""}`
      : "TBD";
    starters = `<div class="game-sub starters"
      title="Probable starters — throwing hand and expected ERA">
      ${iconMark("dot", 10)}${pfmt(g.pitchers.away)}
      <span class="at">@</span> ${pfmt(g.pitchers.home)}</div>`;
  }
  // The strip is the hero of the page, so each card is also the door into
  // that game: role/tabindex make it a real control for keyboard and screen
  // readers, not just a div that happens to listen for clicks.
  const n = gameBetCount(g);
  return `
    <article class="game-card tilt ${isLive ? "is-live" : ""}" data-gid="${escapeHtml(gameId(g))}"
             role="button" tabindex="0"
             aria-label="Open picks for ${escapeHtml(teamName(g.away))} at ${escapeHtml(teamName(g.home))}">
      <div class="stadium-wrap">${art}${badge}</div>
      <div class="game-info">
        <div class="matchup">
          <span class="mt away">${teamMark(g.away, 18)} ${ranked("away")}${escapeHtml(teamName(g.away))} ${score("away")}</span>
          <span class="at">@</span>
          <span class="mt home">${teamMark(g.home, 18)} ${ranked("home")}${escapeHtml(teamName(g.home))} ${score("home")}</span></div>
        ${starters}
        <div class="game-sub">${sub}</div>
        ${whenLabel(g.date, g.kickoff) ? `<div class="game-when">${icon('calendar')} ${escapeHtml(whenLabel(g.date, g.kickoff))}</div>` : ""}
        ${isLive && !mlb ? liveDetail : ""}
      </div>
      ${footer}
      <div class="game-cta">${n ? `${n} pick${n === 1 ? "" : "s"} for this game` : "See this game's board"}
        <span class="gc-arrow">→</span></div>
    </article>`;
}

/* How many things we'd actually recommend in this game — the number that
   makes the card worth tapping. Counts recommended props and game bets;
   the game page itself shows everything analyzed. */
function gameBetCount(g) {
  const props = (state.data.recommendations || []).filter(
    (r) => propInGame(r, g) && passesFilters(r)).length;
  const gbs = (state.data.game_bets || []).filter(
    (b) => b.home === g.home && b.away === g.away && passesGameBet(b)).length;
  return props + gbs;
}

function propInGame(r, g) {
  const pair = new Set([r.team, r.opponent]);
  return pair.has(g.home) && pair.has(g.away)
    && (!r.game_date || !g.date || r.game_date === g.date)
    // Doubleheader: a prop belongs to ONE leg, not both.
    && (!r.game_number || !g.game_number || r.game_number === g.game_number);
}

function fillMeters(host) {
  host.querySelectorAll(".conf-fill[data-w]").forEach((el) => {
    if (state.quiet) { el.style.transition = "none"; el.style.width = el.dataset.w; }
    else requestAnimationFrame(() => (el.style.width = el.dataset.w));
  });
}

function renderRecommended() {
  const host = document.getElementById("cards");
  // When the whole slate is empty, the empty-slate banner already explains it.
  if (!(state.data.games || []).length && !(state.data.recommendations || []).length) {
    host.innerHTML = "";
    return;
  }
  const recs = state.data.recommendations.map((r) => ({ ...r, _ok: passesFilters(r) }));
  // Home runs are long shots by nature: this page features only the top
  // three (hr_featured, stamped by the pipeline) — the same three that lead
  // the Long Shots page, where the FULL home-run board lives.
  const visible = recs.filter((r) => (state.showAll ? true : r._ok))
    .filter((r) => r.hr_featured !== false);
  if (!visible.length) {
    // Say WHY the board is empty. "Loosen the sliders" is bad advice when
    // the real reason is upstream of every slider: no real book price yet,
    // or the only priced games have already started. The owner moved every
    // slider to its loosest and still saw nothing — the message has to
    // name the actual blocker, not suggest a knob that cannot help.
    const real = recs.filter((r) => r.has_market !== false);
    const started = real.filter((r) => r.live
      || (r.warnings || []).some((w) => /already started/i.test(w)));
    let msg;
    if (recs.length && !real.length) {
      msg = noMarketExplainer();
    } else if (real.length && started.length === real.length) {
      msg = `${real.length} prop(s) carry real prices, but every one is on a
        game that has already started — pre-game picks are never made against
        in-play lines. The other ${recs.length - real.length} prop(s) are
        waiting on real book prices, which books post close to first pitch.
        The board fills as tonight's prices arrive; no slider changes that.`;
    } else if (!recs.length && censusTotal() > 0) {
      /* Nothing reached the board AT ALL, which the old copy answered with
         "loosen the sliders" — advice that cannot work, because a slider
         filters what arrives and nothing arrived. The WNBA sat on that
         sentence with 430 props built from history and 384 of them never
         priced by a book. Name the biggest actual cause instead. */
      const [why, n] = biggestCensusBucket();
      const built = ((state.data || {}).counts || {}).props_built;
      msg = `No props reached the board. The largest reason is
        <b>${escapeHtml(why)}</b> (${n})${built ? ` out of ${built} built from
        player history` : ""}. Sliders filter what arrives, so they cannot
        help here — the full breakdown is below.`;
    } else {
      msg = `No props clear the current thresholds. Loosen the sliders or
        enable “show non-recommended”.`;
    }
    // The funnel goes under EVERY empty message, not just the ones that
    // mention it. "Why is this blank" is the same question in all cases.
    host.innerHTML = `<p class="loading">${msg}</p>${censusFunnelHTML()}`;
    return;
  }
  // Group by market so all Total Bases props sit together, all Hits
  // together, and so on — full cards, just organized.
  const groups = new Map();
  visible.forEach((r) => {
    const k = r.market_label || r.market || "Other";
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  });
  const MARKET_ORDER = ["total bases", "hits", "home runs", "strikeouts",
                        "passing yards", "rushing yards", "receiving yards",
                        "receptions"];
  const keys = [...groups.keys()].sort((a, b) => {
    const ia = MARKET_ORDER.indexOf(a.toLowerCase());
    const ib = MARKET_ORDER.indexOf(b.toLowerCase());
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  host.innerHTML = keys.map((k) => {
    const rows = groups.get(k);
    const nRec = rows.filter((r) => r._ok).length;
    const hrNote = k.toLowerCase() === "home runs"
      ? ` · top 3 only — the full board is on the Long Shots page` : "";
    return `<div class="section-title subhead" style="grid-column:1/-1">
        ${escapeHtml(k)} <span class="sub">— ${rows.length} prop(s)${nRec ? `, ${nRec} recommended` : ""}${hrNote}</span>
      </div>` + rows.map(cardHTML).join("");
  }).join("");
  // "Analyzed 1030 → showing 3" is alarming unless the page says where the
  // rest went: most are analyzed-but-held (lineups not confirmed, edge too
  // small, or no real price) and non-featured home runs live on Long Shots.
  const hidden = recs.length - visible.length;
  if (hidden > 0) {
    host.innerHTML += `<p class="loading" style="grid-column:1/-1;margin-top:14px">
      ${hidden} more analyzed prop(s) not shown — ${state.showAll
        ? "non-featured home runs live on the Long Shots page"
        : "held (unconfirmed lineup, edge below the bar, or no real price yet) or featured elsewhere. Toggle “show non-recommended” to browse everything"}.</p>`;
  }
  fillMeters(host);
  revealChildren(host);
}

function projBar(r) {
  const lo = Math.min(r.proj_low, r.line), hi = Math.max(r.proj_high, r.line);
  const pad = (hi - lo) * 0.15 || 1, min = lo - pad, max = hi + pad;
  const pos = (v) => `${((v - min) / (max - min)) * 100}%`;
  return `
    <div class="projbar">
      <div class="labels"><span>Projection vs line</span><span>${r.market_label}</span></div>
      <div class="track">
        <div class="range" style="left:${pos(r.proj_low)};width:${((r.proj_high - r.proj_low) / (max - min)) * 100}%"></div>
        <div class="line-dot" style="left:${pos(r.line)}"></div>
        <div class="proj-dot" style="left:${pos(r.projection)}"></div>
      </div>
      <div class="legend"><span class="proj">Proj ${r.projection}</span><span class="line">Line ${r.line}</span></div>
    </div>`;
}

function confMeter(r) {
  const w = `${(r.confidence / 10) * 100}%`;
  /* No amber. Confidence is a NUMBER, and amber in this palette means a
     CONDITION is live or material — four amber confidence bars on one board
     were four amber elements saying nothing about conditions. The bar's
     LENGTH already encodes the value; colour was doing the same job twice,
     so it does the one thing length cannot and marks the top of the range. */
  const color = r.confidence >= 8.5 ? "var(--good)"
    : r.confidence >= 7 ? "var(--text)"
    : r.confidence >= 5.5 ? "var(--text-dim)" : "var(--text-mute)";
  return `<div class="conf-wrap"><div class="conf-meter"><div class="conf-fill" data-w="${w}" style="background:${color}"></div></div>
    <div class="conf-num">${r.confidence.toFixed(1)}/10</div></div>`;
}

function trendChip(r) {
  if (r.trend === "up") return `<span class="chip up">${icon("rising")} Trending up</span>`;
  if (r.trend === "down") return `<span class="chip down">${icon("falling")} Cooling off</span>`;
  return `<span class="chip">Steady form</span>`;
}
function booksChip(r) {
  const n = (r.all_lines || []).length;
  return n <= 1 ? "" : `<span class="chip books">${icon('tag')} ${n} books · best ${escapeHtml(r.book)}</span>`;
}
function moveChip(r) {
  const m = r.line_move;
  if (!m) return "";
  const what = Math.abs(m.delta || 0) > 1e-9
    ? `${m.open} → ${m.current}`
    : `${m.open_odds != null ? american(m.open_odds) : "?"} → ${m.current_odds != null ? american(m.current_odds) : "?"}`;
  const withUs = m.verdict === "with";
  const mark = m.steam ? iconMark("hot") : iconMark(withUs ? "rising" : "falling");
  return `<span class="chip ${withUs ? "up" : "down"}" title="${withUs ? "Books have re-priced toward our side since our first snapshot" : "Books have re-priced away from our side since our first snapshot"}">${mark} Market ${withUs ? "with" : "against"} pick · ${what}</span>`;
}

// §8/§10 chips: the market tier and volatility rating every play carries.
function tierChip(r) {
  if (r.tier == null) return "";
  const volColor = { LOW: "var(--good)", MEDIUM: "var(--cyan)",
                     HIGH: "var(--warn)", EXTREME: "var(--bad)" }[r.volatility] || "";
  return `<span class="chip" title="Tier 1 = count props (most modelable) · Tier 2 = yardage · Tier 3 = touchdowns. Volatility feeds the edge haircut and the stake size.">
    T${r.tier}${r.volatility ? ` · <span style="color:${volColor}">${escapeHtml(r.volatility)}</span>` : ""}</span>`;
}

function qualityChip(r) {
  if (r.quality == null) return "";
  return `<span class="chip" title="Unified bet quality 0–100: post-haircut edge 40% · usage stability 15% · market movement 15% · game-script fit 10% · matchup 10% · weather 10%. Below 70 is never a bet.">
    Q ${r.quality}/100</span>`;
}

function cardHTML(r) {
  const reasons = (r.reasons || []).map(reasonLI).join("");
  const corr = (r.correlations || []).map((c) =>
    `<div class="warning" style="border-color:var(--cyan)">${iconMark("tag")}${escapeHtml(c)}</div>`).join("");
  const warnings = (r.warnings || []).map((w) => `<div class="warning">${icon('warn')} ${escapeHtml(w)}</div>`).join("");
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const stakeChip = r._ok ? `<span class="chip stake">${stakeTxt}</span>` : "";
  return `
    <article class="card ${r._ok ? "" : "faded"}" style="--grade-color:${gradeColor(r.grade)}">
      ${r.live ? `<div class="live-ribbon"><span class="live-dot"></span>LIVE · in-play</div>` : ""}
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team, { headshot: r.headshot })}
          <div>
            <div class="player">${escapeHtml(r.player)}</div>
            <div class="subtitle">${escapeHtml(r.team)} vs ${escapeHtml(r.opponent)}${r.position ? ` · ${escapeHtml(r.position)}` : ""}</div>
            <div class="pick">${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}
              <span class="book">· ${escapeHtml(r.book)} ${american(r.odds)}</span></div>
          </div>
        </div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      ${projBar(r)}
      <div class="metrics">
        <div class="metric"><div class="k">Hit prob</div><div class="v">${pct(r.hit_prob)}</div></div>
        <div class="metric primary"><div class="k">Edge</div><div class="v ${r.has_market === false ? "" : (r.edge >= 0 ? "pos" : "neg")}">${r.has_market === false ? "—" : signedPct(r.edge)}</div></div>
        <div class="metric"><div class="k">EV / unit</div><div class="v ${r.ev_per_unit >= 0 ? "pos" : "neg"}">${signedPct(r.ev_per_unit)}</div></div>
      </div>
      ${confMeter(r)}
      ${(r.recent_values || []).length > 2
        ? `<div class="mini" style="margin-top:8px" title="Last ${r.recent_values.length} games — dashed line is the prop line">
             ${sparkline(r.recent_values, { line: r.line, stroke: teamPrimary(r.team), w: 260, h: 46 })}</div>`
        : ""}
      <div class="chips">${r.has_market === false ? `<span class="chip">No book line — model projection only</span>` : ""}${r.doubleheader ? `<span class="chip up" title="Two games today — this prop is priced for this specific game only">${iconMark("calendar", 11)}Doubleheader · Game ${r.game_number || 1}</span>` : ""}${whenChip(r.game_date, r.game_kickoff)}${qualityChip(r)}${tierChip(r)}${trendChip(r)}${moveChip(r)}${booksChip(r)}${stakeChip}</div>
      ${corr}${warnings}${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
    </article>`;
}

/* ============================================================
   Long Shots — NFL anytime TDs / MLB home runs
   ============================================================ */
function renderLongShots() {
  const mlb = state.sport === "mlb";
  const picks = state.data.long_shots || [];
  const host = document.getElementById("longshots");
  const note = document.getElementById("longshots-note");
  document.getElementById("longshots-sub").textContent = mlb
    ? "— home runs, priced on contact quality, park & weather"
    : "— anytime touchdowns, priced on opportunity not hype";

  // The board is three rows and there is no fourth. It used to list every
  // real-priced home run on the slate below the picks — two hundred names
  // most nights, which buried the three that were actually recommended.
  const watch = state.data.longshot_watch || [];
  if (!picks.length) {
    host.innerHTML = watchlistHTML(watch, mlb);
    note.innerHTML = watch.length
      ? `<div class="ls-note">No price clears the strict <b>value</b> bar tonight, so
         these are the model's most likely ${mlb ? "home runs" : "scorers"} instead, with
         the price shown honestly. They are <b>not</b> value picks and are not journaled
         as bets — read them as insight, not as a card.</div>`
      : `<div class="empty-slate"><div class="es-icon">${icon("target", 30)}</div>
      <div class="es-title">No ${mlb ? "home-run" : "touchdown"} board right now</div>
      <div class="es-sub">${escapeHtml(longshotEmptyReason(mlb))}</div></div>`;
    return;
  }
  note.innerHTML = `<div class="ls-note">Top ${picks.length} pick(s), ranked by
    <b>edge</b>, never by payout — the same ${picks.length === 1 ? "one" : picks.length}
    featured on the Recommended page.${watch.length ? ` Topped up to three with the
    model's most likely ${mlb ? "home run" : "scorer"}${watch.length > 1 ? "s" : ""},
    shown for context and not journaled as bets.` : ""}</div>`;
  host.innerHTML = picks.map(longShotCard).join("") + watchlistHTML(watch, mlb);
  fillMeters(host);
  revealChildren(host);
}

/* ============================================================
   Parlay Zone — a screen, not a builder (docs/PARLAY_MODEL.md)
   ============================================================
   The page is designed around the sentence it prints most often. §12 of the
   parlay model is explicit: "No qualifying parlay at current numbers" should
   be the most common output by a wide margin, and on a 12-game slate
   publishing that sentence IS the system working. So the verdict leads, the
   ticket is secondary, and the clash ledger below it carries the weight —
   that ledger is the answer to "which of tonight's props are fighting each
   other", which is the question this page exists to answer.

   Two things this page must never do. It must never show a parlay price as
   though we know one: no feed we ingest carries same-game-parlay quotes, so
   every ticket publishes the price it must BEAT and says that is what it is
   doing. And it must never show a stake: §13 puts parlays on the same
   probation as CFB and WNBA — graded, never staked, until 100 tickets clear
   ROI, CLV and z, and until the singles board clears its own bar first. */
function renderParlays() {
  const host = document.getElementById("parlays-body");
  if (!host) return;
  const z = state.data.parlays;

  /* A slate built before this module existed, or by a builder that has no
     screen wired in, has no `parlays` key at all. Saying so beats rendering
     an empty page that looks like a clean night. */
  if (!z) {
    host.innerHTML = `<div class="empty-slate">
      <div class="es-icon">${icon("dash", 30)}</div>
      <div class="es-title">No parlay screen on this board</div>
      <div class="es-sub">This slate was built before the parlay screen ran.
        It will appear on the next refresh — nothing is wrong with the picks
        above it.</div></div>`;
    return;
  }

  const tickets = z.tickets || [];
  const qualified = tickets.filter((t) => t.qualified);

  host.innerHTML = `
    <div class="pz-doctrine">${escapeHtml(z.doctrine || "")}</div>
    <div class="pz-verdict ${qualified.length ? "pz-yes" : "pz-no"}">
      <span class="pz-mark">${icon(qualified.length ? "check" : "cross", 15)}</span>
      ${escapeHtml(z.verdict || "")}
    </div>
    <div class="pz-probation">
      <span class="pz-mark">${icon("warn", 13)}</span>
      ${escapeHtml(z.probation_note || "")}
    </div>
    ${tickets.length ? `<div class="pz-sub pz-rank-title">
      ${qualified.length
        ? "Tonight's board, ranked — the first is the play"
        : "Tonight's board, ranked — best constructions available"}
      </div>` : ""}
    ${tickets.slice(0, 1).map((t) => parlayTicket(t, t.qualified)).join("")}
    ${parlayRunnersUp(tickets.slice(1))}
    ${parlayLedger(z)}
    ${(z.notes || []).map((n) =>
        `<div class="pz-note">${escapeHtml(n)}</div>`).join("")}
    <div class="pz-census">
      Screened ${z.considered} candidate ${z.considered === 1 ? "ticket" : "tickets"}
      built from ${z.eligible_legs} eligible ${z.eligible_legs === 1 ? "leg" : "legs"}
      on tonight's board.
      ${z.killed && z.killed.length
        ? `${z.killed.length} ${z.killed.length === 1 ? "was" : "were"} killed
           for the reasons above.` : ""}
    </div>`;
  revealChildren(host);
}

/* One ticket, laid out the way §12 prints it: legs, then the correlation
   that justifies the structure, then the clash screen, then the three
   joints side by side, then the price it has to beat — and last the honest
   case against it. `live` false means this is the closest miss on the
   board, shown as a record of what was looked at rather than as a play. */
function parlayTicket(t, live) {
  const pct = (x) => `${(x * 100).toFixed(1)}%`;
  const sign = (n) => (n > 0 ? `+${n}` : `${n}`);
  return `<div class="card pz-ticket${live ? "" : " pz-miss"}">
    <div class="card-head">
      <div class="card-id"><div class="player">
        <span class="pz-rank">#${t.rank}</span>
        Type ${escapeHtml(t.parlay_type)} · ${t.legs.length} legs</div></div>
      <div class="chips">
        <span class="chip pz-g-${t.grade}">${
          t.grade === "play" ? "clears at any plausible price"
          : t.grade === "marginal" ? "clears at a good price · check yours"
          : "does not clear"}</span>
        <span class="chip stake">graded · 0.00u</span>
      </div>
    </div>

    <ol class="pz-legs">
      ${t.legs.map((l) => `<li>
        <span class="pz-leg-name">${escapeHtml(l.player || "")}</span>
        <span class="pz-leg-mkt">${escapeHtml(l.side || "")} ${escapeHtml(String(l.line ?? ""))}
          ${escapeHtml(l.market_label || l.market || "")}</span>
        <span class="pz-leg-nums">${sign(l.odds)}${l.book ? ` · ${escapeHtml(l.book)}` : ""}
          <i>·</i> p ${pct(l.p_final)} <i>·</i> Tier ${l.tier}</span>
      </li>`).join("")}
    </ol>

    <div class="pz-sub">Correlation</div>
    <ul class="pz-pairs">
      ${t.pairs.map((p) => `<li>
        <div class="pz-pair-head">
          <span class="pz-pair-who">${escapeHtml(p.a || "")} ↔ ${escapeHtml(p.b || "")}</span>
          <span class="pz-pair-rho">ρ ${p.rho >= 0 ? "+" : ""}${p.rho.toFixed(2)}
            <i>→ priced ${p.rho_priced >= 0 ? "+" : ""}${p.rho_priced.toFixed(3)}</i></span>
        </div>
        <div class="pz-pair-why">${escapeHtml(p.mechanism || "")}</div>
      </li>`).join("")}
    </ul>
    <div class="pz-fine">${t.pairs.some((p) => p.rho_measured)
      ? `A ρ marked <b>measured</b> was counted on our own game history rather
         than taken from the model doc, so it is priced at face value: the
         humility clamp exists because a prior is a guess, and a counted
         number has nothing to be humble about. `
      : ""}The published ρ is the doc's prior; the priced ρ is that prior after
      the clamp this engine applies to every raw edge. Those magnitudes are
      professional estimates, not measured constants, and pricing an estimate
      at face value would invent edge out of a guess.</div>

    <div class="pz-sub">Clash screen</div>
    <div class="pz-clash">${icon("check", 12)} ${escapeHtml(t.clash_screen)}</div>

    <div class="pz-sub">Joint probability</div>
    <div class="metrics pz-joint">
      <div class="metric"><div class="k">Independent product</div>
        <div class="v">${pct(t.independent_joint)}</div></div>
      <div class="metric primary"><div class="k">Conditional chain</div>
        <div class="v">${pct(t.modeled_joint)}</div></div>
      <div class="metric"><div class="k">Threshold</div>
        <div class="v">${t.threshold_points.toFixed(1)} pts</div></div>
    </div>
    <div class="pz-fine">Never the product. §1.1: independence is a claim
      about the world, and inside one game it is almost always false.</div>

    <div class="pz-sub">Price</div>
    <div class="metrics pz-price">
      <div class="metric"><div class="k">Legs multiplied</div>
        <div class="v">${sign(t.naive_product_american)}</div></div>
      <div class="metric primary"><div class="k">You need at least</div>
        <div class="v">${sign(t.required_american)}</div></div>
      <div class="metric"><div class="k">What a book might pay</div>
        <div class="v ${t.qualified ? "pos" : "neg"}">${sign(t.best_case_american)}</div>
        <div class="pz-short">${t.shortfall_pct
          ? `short by ${t.shortfall_pct}%`
          : `to ${sign(t.likely_case_american)} at a stingy book`}</div></div>
    </div>
    <div class="pz-edge ${t.edge_at_ceiling_points > 0 ? "pos" : "neg"}">
      At that ceiling this ticket is
      <b>${t.edge_at_ceiling_points > 0 ? "+" : ""}${t.edge_at_ceiling_points} points</b>
      ${t.edge_at_ceiling_points > 0
        ? `of edge — still short of the ${t.threshold_points}-point bar.`
        : `<b>behind</b> the price. Even at the most generous number a book
           would plausibly offer, this loses money.`}
      That figure is what tonight's board is ranked on.</div>
    <div class="pz-fine">Nobody publishes what they charge to combine legs, so
      the two numbers above are a <b>band</b>, not a quote: this ticket is
      measured against a book taking
      ${(t.correlation_tax_best_case * 100).toFixed(0)}% and against one
      taking ${(t.correlation_tax_worst_case * 100).toFixed(0)}%, versus the
      4.3–4.8% a straight side costs. ${t.grade === "marginal"
        ? `It clears the first and not the second — which makes this a question
           about your book's actual number rather than about the model.`
        : t.grade === "play"
        ? `It clears both, so the price is not what stands between you and this
           ticket.` : ""}</div>

    <div class="pz-sub">Dominance</div>
    <div class="pz-dominance">These same legs bet separately are worth
      <b>${(t.singles_alternative_ev * 100).toFixed(1)}%</b> in expectation
      across ${t.legs.length} units${t.parlay_type === "A"
        ? `, or <b>${(t.singles_alternative_same_stake * 100).toFixed(1)}%</b>
           for the one unit this ticket risks` : ""}. A parlay has to beat
      that by ${t.dominance_required}× to be worth the variance and the
      single point of failure — if it only ties, <b>bet the singles</b>.</div>
    ${t.singles_beat_it ? `<div class="pz-edge neg">
      <b>The singles were the better bet here.</b> This ticket is shown
      because it is the best-constructed one on the board, not because it
      beat betting these legs separately.</div>` : ""}

    <div class="pz-verdict-line">${escapeHtml(t.verdict)}</div>
    <div class="pz-risk"><span class="pz-mark">${icon("warn", 12)}</span>
      ${escapeHtml(t.risk)}</div>
    <div class="pz-stake">Stake <b>0.00u</b> — graded, not staked.
      At the required price an eighth-Kelly stake would have been
      ${t.stake_if_promoted.toFixed(2)}u, capped at 1.0% of bankroll. That
      number is tracked so promotion day has something to promote; it is not
      a recommendation to bet it.</div>
  </div>`;
}

/* Ranks two and below, as rows rather than cards.
   Four full tickets stacked ran to six thousand pixels of near-identical
   blocks, which buries the one that matters. The top construction earns the
   card; the rest earn a line each — enough to compare them on the numbers
   the ranking uses and to click through in your head, and no more. */
function parlayRunnersUp(rows) {
  if (!rows.length) return "";
  const sign = (n) => (n > 0 ? `+${n}` : `${n}`);
  return `<div class="pz-sub pz-runners-title">Also on the board</div>
    <ul class="pz-runners">
      ${rows.map((t) => `<li>
        <span class="pz-rank">#${t.rank}</span>
        <span class="pz-run-legs">${t.legs.map((l) =>
          `${escapeHtml(l.player || "")} <i>${escapeHtml(l.side || "")}
           ${escapeHtml(String(l.line ?? ""))}
           ${escapeHtml(l.market_label || l.market || "")}</i>`).join(" + ")}</span>
        <span class="pz-run-num">Type ${escapeHtml(t.parlay_type)}</span>
        <span class="pz-run-num">ρ ${t.pairs.map((p) =>
          `${p.rho >= 0 ? "+" : ""}${p.rho.toFixed(2)}`).join(" ")}</span>
        <span class="pz-run-num ${t.edge_at_ceiling_points > 0 ? "" : "neg"}">
          ${sign(t.edge_at_ceiling_points)} pts</span>
        <span class="pz-run-num">need ${sign(t.required_american)}</span>
        <span class="pz-run-num">${t.shortfall_pct
          ? `short ${t.shortfall_pct}%` : "clears"}</span>
      </li>`).join("")}
    </ul>`;
}

/* The clash ledger. Every candidate that died, and the §3 type that killed
   it. This is the part of the page worth reading on a night with no ticket:
   it is the record of which of tonight's props cannot sit next to which,
   and why — a bare count would teach nobody anything. */
function parlayLedger(z) {
  const rows = z.killed || [];
  if (!rows.length) return "";
  return `<div class="pz-sub pz-ledger-title">What was screened out, and why</div>
    <ul class="pz-ledger">
      ${rows.map((k) => `<li>
        <div class="pz-kill-who">${escapeHtml(String(k.leg || ""))}</div>
        <div class="pz-kill-why">${escapeHtml(k.reason || "")}</div>
      </li>`).join("")}
    </ul>`;
}

function longshotEmptyReason(mlb) {
  const dg = state.data.longshot_diag;
  if (mlb && dg) {
    if (!dg.hr_props)
      return "No hitter props are built yet. Lineups aren't posted AND no recent " +
             "batting order could be projected — if games are on today, the next " +
             "refresh usually fixes this (the projector needs the free MLB Stats " +
             "API to be reachable).";
    if (!dg.real_priced)
      return `Lineups are in (${dg.hr_props} hitters) but no real home-run prices ` +
             "are attached yet — books post HR props close to game time, and the " +
             "board fills on the next odds refresh.";
    if (!dg.plus_money)
      return `${dg.real_priced} home-run price(s) are attached but none are ` +
             "plus-money in a believable range right now. This usually means " +
             "games are in progress (in-play prices) — tomorrow's board resets " +
             "with fresh pre-game quotes.";
    return `${dg.plus_money} real plus-money price(s) exist but every one failed ` +
           "a sanity guard (edge cap or odds window). If this persists on a " +
           "pre-game board, something is wrong — worth reporting.";
  }
  return "The model only surfaces " + (mlb ? "home-run" : "touchdown") +
         " picks that beat the book's price inside a sane odds range" +
         (mlb ? " (+250 to +650)." : " (-150 to +200).");
}

function watchlistHTML(watch, mlb) {
  if (!watch || !watch.length) return "";
  const rows = watch.map((r, i) => {
    const ev = (r.ev_per_unit * 100).toFixed(0);
    const evColor = r.ev_per_unit > 0 ? "var(--good, #3ddc84)" : "var(--text-mute, #889)";
    const spark = (r.recent_values || []).length > 2
      ? sparkline(r.recent_values, { line: 0.5, stroke: teamPrimary(r.team), w: 64, h: 22 })
      : "";
    return `<div class="drow" style="display:flex;align-items:center;gap:12px;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);white-space:nowrap;overflow:hidden">
      <span style="opacity:.5;min-width:18px;font-size:.85em">${i + 1}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">
        <strong>${escapeHtml(r.player)}</strong>
        <span style="opacity:.55;font-size:.85em"> ${teamName(r.team)} vs ${teamName(r.opponent)}
          · ${escapeHtml(r.primary_reason || "")}</span></span>
      <span class="mini" style="flex:0 0 auto" title="Home runs, last ${(r.recent_values || []).length} games">${spark}</span>
      <span style="min-width:96px;text-align:right;opacity:.85;font-size:.9em">
        ${(r.model_prob * 100).toFixed(0)}% vs ${(r.implied_prob * 100).toFixed(0)}%</span>
      <span style="min-width:56px;text-align:right">${american(r.odds)}</span>
      <span style="min-width:64px;text-align:right;color:${evColor};font-size:.9em">${r.ev_per_unit > 0 ? "+" : ""}${ev}% EV</span>
    </div>`;
  }).join("");
  return `<div style="grid-column:1/-1;min-width:0">
    <div class="section-title">Most likely ${mlb ? "to homer" : "to score"} tonight
      <span class="sub">— model % vs the book's implied %. Positive EV = price worth taking;
      negative = likely but overpriced. Never a guarantee.</span></div>
    <div class="card" style="padding:0">${rows}</div></div>`;
}

function longShotCard(r) {
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  // The primary reason already headlines the card in its own box —
  // repeating it as the first bullet read as a copy-paste mistake.
  const reasons = (r.reasons || []).filter((x) => x !== r.primary_reason)
    .slice(0, 6).map(reasonLI).join("");
  const caveats = (r.caveats || [])
    .map((c) => `<div class="warning">${icon('warn')} ${escapeHtml(c)}</div>`).join("");
  const oppLabel = state.sport === "mlb" ? "Expected PAs" : "RZ chances";
  return `
    <article class="card longshot" style="--grade-color:${gradeColor(r.grade)}">
      ${r.live ? `<div class="live-ribbon"><span class="live-dot"></span>LIVE · in-play</div>` : ""}
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team, { map: nflMap() })}
          <div>
            <div class="player">${escapeHtml(r.player)} <span class="ml-odds">${american(r.odds)}</span></div>
            <div class="subtitle">${escapeHtml(r.matchup)}${whenLabel(r.game_date, r.game_kickoff)
              ? ` · ${escapeHtml(whenLabel(r.game_date, r.game_kickoff))}` : ""}</div>
            <div class="pick">${escapeHtml(r.market_label)}
              <span class="book">· ${escapeHtml(r.book)}</span></div>
          </div>
        </div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">Model</div><div class="v">${pct(r.model_prob)}</div></div>
        <div class="metric"><div class="k">Book implied</div><div class="v">${pct(r.implied_prob)}</div></div>
        <div class="metric primary"><div class="k">Edge</div><div class="v ${r.edge >= 0 ? "pos" : "neg"}">${signedPct(r.edge)}</div></div>
        <div class="metric"><div class="k">${oppLabel}</div><div class="v">${r.expected_opportunities}</div></div>
      </div>
      ${confMeter(r)}
      ${(r.recent_values || []).length > 2
        ? `<div class="mini" style="margin-top:8px" title="Last ${r.recent_values.length} games — dashed line is the prop line">
             ${sparkline(r.recent_values, { line: r.line, stroke: teamPrimary(r.team), w: 260, h: 46 })}</div>`
        : ""}
      <div class="chips"><span class="chip stake">${stakeTxt}</span></div>
      <div class="ls-primary">${escapeHtml(r.primary_reason)}</div>
      ${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
      ${caveats}
    </article>`;
}

/* ============================================================
   Single game — everything the model has on one matchup.

   The stadium strip is the hero of the Recommended page, but until now
   the cards were decoration: you could look at Wrigley and the wind, then
   had to go hunt the board for the props that play in it. Each card is now
   the door into that game, and this view is the room behind it.
   ============================================================ */
function openGame(gid) {
  state.gameId = gid;
  switchView("game");
}

/* ---------------- Venue panels ----------------
   A ballpark changes what identical contact produces — 310 feet in front
   of a 37-foot wall is a different game from 420 to center — so MLB gets
   the full treatment: the three factors the model actually prices with,
   the dimensions that explain them, and what the park is known for.
   An NFL field is 100 yards everywhere, so that page gets the far shorter
   list of things that genuinely vary: roof, altitude, surface. */
/* One accent color for every bar, deliberately. Coloring these green and
   red would have to answer "good for whom" — a park that adds 8% to
   strikeouts is good news on the over and bad news on the under, and the
   same holds for all three factors. Direction is carried by which side of
   the league-average tick the bar sits on, which is a fact rather than a
   judgement. */
function factorRow(label, v, hint) {
  if (v == null) return "";
  const pctOff = (v - 1) * 100;
  // The bar is centered on 1.00: right of the tick is above the average
  // park, left is below. Clamped at ±30% so Coors doesn't set a scale
  // nothing else on the board can use.
  const frac = Math.max(-1, Math.min(1, pctOff / 30));
  const w = Math.abs(frac) * 50;
  return `<div class="pk-factor" title="${escapeHtml(hint)}">
    <span class="pk-fk">${escapeHtml(label)}</span>
    <span class="pk-fbar"><i style="${frac >= 0
      ? `left:50%;width:${w}%` : `left:${50 - w}%;width:${w}%`}"></i>
      <b></b></span>
    <span class="pk-fv">${pctOff >= 0 ? "+" : ""}${pctOff.toFixed(0)}%</span>
  </div>`;
}

function parkPanel(g) {
  const p = g.park;
  if (!p) return "";
  const f = g.factors || {};
  const dim = (v) => v ? `${v}'` : "—";
  // Whole feet: walls are quoted that way ("the 37-foot Green Monster"),
  // and a decimal reads as false precision — 37.2' looks like a surveyed
  // figure rather than "37 feet 2 inches, rounded".
  //
  // Only walls that change how the park plays are worth the line. Standard
  // is 8 feet; PNC's 6-foot left field and Daikin's 7-foot right are noise
  // dressed up as a fact. A wall has to be genuinely low (Fenway's 5-foot
  // right field, 302 away) or genuinely tall to earn the mention.
  const notable = (v) => v && (Math.round(v) >= 12 || Math.round(v) <= 5);
  const wall = (v) => notable(v) ? ` · ${Math.round(v)}' wall` : "";
  const facts = [
    p.opened ? `Opened ${p.opened}` : "",
    p.capacity ? `${p.capacity.toLocaleString()} seats` : "",
    p.altitude_ft ? `${p.altitude_ft.toLocaleString()} ft elevation` : "",
    p.roof && p.roof !== "open" ? `${p.roof} roof` : "",
    p.surface === "turf" ? "turf" : "",
  ].filter(Boolean).join(" · ");
  return `<div class="pk-panel">
    <div class="pk-head">${escapeHtml(p.name)}<span class="pk-facts">${escapeHtml(facts)}</span></div>
    <div class="pk-dims">
      <div class="pk-dim"><span class="k">Left</span><span class="v">${dim(p.lf_ft)}</span>
        <span class="s">${escapeHtml(wall(p.lf_wall_ft).replace(" · ", ""))}</span></div>
      <div class="pk-dim"><span class="k">Center</span><span class="v">${dim(p.cf_ft)}</span><span class="s"></span></div>
      <div class="pk-dim"><span class="k">Right</span><span class="v">${dim(p.rf_ft)}</span>
        <span class="s">${escapeHtml(wall(p.rf_wall_ft).replace(" · ", ""))}</span></div>
    </div>
    <div class="pk-factors">
      ${factorRow("Home runs", f.hr, "Park home-run factor vs the league-average park. This is a model input.")}
      ${factorRow("Runs", f.run, "Park run factor vs the league-average park. This is a model input.")}
      ${factorRow("Strikeouts", f.k, "Park strikeout factor. Above average favors pitchers.")}
    </div>
    ${p.plays ? `<p class="pk-plays">${escapeHtml(p.plays)}</p>` : ""}
  </div>`;
}

function stadiumPanel(g) {
  const s = g.stadium;
  if (!s || !s.name) return "";
  const indoors = s.roof === "dome" || s.roof === "retractable";
  const facts = [
    s.opened ? `Opened ${s.opened}` : "",
    s.capacity ? `${s.capacity.toLocaleString()} seats` : "",
    s.surface === "turf" ? "turf" : "grass",
  ].filter(Boolean).join(" · ");
  return `<div class="pk-panel">
    <div class="pk-head">${escapeHtml(s.name)}<span class="pk-facts">${escapeHtml(facts)}</span></div>
    <div class="chips" style="margin-top:8px">
      <span class="chip ${indoors ? "books" : ""}">${indoors
        ? (s.roof === "dome" ? `${icon('stadium')} Fixed dome` : `${icon('stadium')} Retractable roof`)
        : `${icon('cloud')} Open air`}</span>
      ${s.altitude_ft >= 2000
        ? `<span class="chip up" title="Thin air adds kicking range and lets the ball carry">${icon('mountain')} ${s.altitude_ft.toLocaleString()} ft</span>`
        : ""}
      <span class="chip">${s.surface === "turf" ? "Turf" : "Grass"}</span>
    </div>
    ${s.plays ? `<p class="pk-plays">${escapeHtml(s.plays)}</p>` : ""}
    <p class="pk-note">Football fields are the same size everywhere, so a venue's
      effect is almost entirely its environment — indoors vs outdoors first,
      then altitude. The live weather above is the number that moves a total.</p>
  </div>`;
}

function renderGamePage() {
  const host = document.getElementById("game-body");
  if (!host) return;
  // A deep link renders before the slate arrives; renderAll calls back.
  if (!state.data) { host.innerHTML = `<p class="loading">Loading the slate…</p>`; return; }
  const g = findGame(state.gameId);
  if (!g) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("stadium", 30)}</div>
      <div class="es-title">That game isn't on the current slate</div>
      <div class="es-sub">Slates roll over each day. Head back to the board for
      today's games.</div></div>
      <button class="btn ghost gp-back" id="gp-back" style="margin-top:14px">← Back to the board</button>`;
    const b = document.getElementById("gp-back");
    if (b) b.addEventListener("click", () => switchView("recommended"));
    return;
  }
  const mlb = state.sport === "mlb";
  const nba = state.sport === "nba" || state.sport === "wnba";
  const w = g.weather || {};
  const live = g.live || {};
  const isLive = live.state === "live";
  const isFinal = live.state === "final";

  const props = (state.data.recommendations || [])
    .map((r) => ({ ...r, _ok: passesFilters(r) }))
    .filter((r) => propInGame(r, g));
  const shown = props.filter((r) => (state.showAll ? true : r._ok));
  const bets = (state.data.game_bets || [])
    .map((b) => ({ ...b, _ok: passesGameBet(b) }))
    .filter((b) => b.home === g.home && b.away === g.away);
  const betsShown = bets.filter((b) => (state.showAll ? true : b._ok));
  const shots = (state.data.long_shots || []).filter((r) => propInGame(r, g));

  // The header re-uses the same art the strip card draws, at full width.
  const art = mlb ? ballpark(g) : nba ? court(g) : stadium(g);
  const cond = nba ? "Indoor hardwood"
    : w.dome ? "Indoor"
    : `${Math.round(w.temp_f)}°F · ${Math.round(w.wind_mph)}mph${w.wind_dir ? " " + w.wind_dir : ""}`;
  const f = g.factors || {};
  const factorChip = (k, label, hint) => f[k] == null ? "" :
    `<span class="chip ${f[k] > 1.02 ? "up" : f[k] < 0.98 ? "down" : ""}" title="${escapeHtml(hint)}">
       ${label} ${f[k].toFixed(2)}×</span>`;
  const score = (side) => (live.home_score != null && (isLive || isFinal))
    ? `<b class="score">${side === "home" ? live.home_score : live.away_score}</b>` : "";

  // Grouping by market earns its keep on a full board. Inside one game it
  // often means four headings above four single cards, which reads as
  // clutter — so below a handful of props they stay one section.
  const byMarket = new Map();
  const GROUP_FROM = 6;
  shown.forEach((r) => {
    const k = shown.length >= GROUP_FROM ? (r.market_label || r.market || "Other") : "Player props";
    if (!byMarket.has(k)) byMarket.set(k, []);
    byMarket.get(k).push(r);
  });
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  host.innerHTML = `
    <button class="btn ghost gp-back" id="gp-back">← Back to the board</button>
    <div class="gp-hero">
      <div class="gp-art">${art}
        ${isLive ? `<div class="status-badge live"><span class="live-dot"></span>LIVE
          <span class="per">${escapeHtml(live.period || "")}</span></div>` : ""}
        ${isFinal ? `<div class="status-badge final">FINAL</div>` : ""}</div>
      <div class="gp-meta">
        <div class="gp-teams">
          <span>${teamMark(g.away, 26)} ${escapeHtml(teamName(g.away))} ${score("away")}</span>
          <span class="gp-at">@</span>
          <span>${teamMark(g.home, 26)} ${escapeHtml(teamName(g.home))} ${score("home")}</span>
        </div>
        <div class="gp-sub">${escapeHtml([g.park_name, whenLabel(g.date, g.kickoff)]
          .filter(Boolean).join(" · "))}</div>
        <div class="chips gp-chips">
          ${g.doubleheader ? `<span class="chip up">${icon("calendar", 11)} Doubleheader · Game ${g.game_number || 1}</span>` : ""}
          <span class="chip">O/U ${g.total != null ? g.total.toFixed(1) : "—"}</span>
          ${g.favorite ? `<span class="chip">${escapeHtml(teamName(g.favorite))} −${Math.abs(g.spread).toFixed(1)}</span>`
            : nba && g.spread ? `<span class="chip">${escapeHtml(teamName(g.spread < 0 ? g.home : g.away))} −${Math.abs(g.spread).toFixed(1)}</span>` : ""}
          <span class="chip">${escapeHtml(cond)}</span>
          ${g.roof ? `<span class="chip">roof ${escapeHtml(g.roof)}</span>` : ""}
          ${g.lineups_confirmed === false ? `<span class="chip down">${icon('warn')} lineups pending</span>` : ""}
        </div>
        ${mlb ? parkPanel(g) : nba ? "" : stadiumPanel(g)}
      </div>
    </div>

    <div class="stats gp-stats">
      <div class="tile"><div class="k">Props analyzed</div><div class="v">${props.length}</div>
        <div class="tile-sub">in this game</div></div>
      <div class="tile"><div class="k">Recommended</div><div class="v">${props.filter((r) => r._ok).length + bets.filter((b) => b._ok).length}</div>
        <div class="tile-sub">props &amp; game bets</div></div>
      <div class="tile"><div class="k">Game bets</div><div class="v">${bets.filter((b) => b._ok).length}</div>
        <div class="tile-sub">moneyline, spread, totals</div></div>
      <div class="tile"><div class="k">Long shots</div><div class="v">${shots.length}</div>
        <div class="tile-sub">${mlb ? "home runs" : nba ? "none for NBA" : "anytime TDs"} · tracked separately</div></div>
    </div>

    ${betsShown.length ? `<div class="section-title">Game bets
        <span class="sub">— moneyline, spread and totals from the team model</span></div>
      <div class="cards gp-cards">${betsShown.map(gameBetCard).join("")}</div>` : ""}

    ${shown.length ? [...byMarket.keys()].map((k) => `
        <div class="section-title">${escapeHtml(k)}
          <span class="sub">— ${plural(byMarket.get(k).length, "prop", "props")}</span></div>
        <div class="cards gp-cards">${byMarket.get(k).map(cardHTML).join("")}</div>`).join("")
      : `<div class="empty-slate"><div class="es-icon">${icon("target", 30)}</div>
          <div class="es-title">No player props clear the filters in this game</div>
          <div class="es-sub">Either the model passes on everything here, or books haven't
          posted prices for it yet.</div>
          ${props.length ? `<button class="btn ghost" id="gp-showall" style="margin-top:12px">
            Show all ${props.length} analyzed prop(s) anyway</button>` : ""}</div>`}

    ${shots.length ? `<div class="section-title">Long shots
        <span class="sub">— tracked in their own bucket, never in the headline record</span></div>
      <div class="cards gp-cards">${shots.map(longShotCard).join("")}</div>` : ""}

    ${props.length > shown.length ? `<p class="loading" style="margin-top:14px">
      ${plural(props.length - shown.length, "more analyzed prop", "more analyzed props")}
      in this game ${props.length - shown.length === 1 ? "is" : "are"} held
      (edge below the bar, no real price, or lineup unconfirmed).</p>` : ""}`;

  const back = document.getElementById("gp-back");
  if (back) back.addEventListener("click", () => switchView("recommended"));
  // "Go back to the board, find the toggle, come back" was three steps for
  // one intention. The button flips the same global toggle in place.
  const showAll = document.getElementById("gp-showall");
  if (showAll) showAll.addEventListener("click", () => {
    state.showAll = true;
    const c = document.getElementById("show-all");
    if (c) c.checked = true;
    renderGamePage();
  });
  fillMeters(host);
  host.querySelectorAll(".cards").forEach(revealChildren);
}

/* ============================================================
   Trending view — momentum & value from the model
   ============================================================ */
function renderTrending() {
  const recs = state.data.recommendations;
  const risers = recs.filter((r) => (r.trend_delta || 0) > 0).sort((a, b) => b.trend_delta - a.trend_delta).slice(0, 6);
  const fallers = recs.filter((r) => (r.trend_delta || 0) < 0).sort((a, b) => a.trend_delta - b.trend_delta).slice(0, 6);
  const edges = [...recs].sort((a, b) => b.edge - a.edge).slice(0, 6);

  const cols = [
    { title: `${iconMark("hot")} Trending Up`, sub: "Biggest recent-form risers", rows: risers, metric: (r) => `<span class="val pos">+${r.trend_delta.toFixed(2)}</span>`, stroke: "var(--good)" },
    { title: `${iconMark("cold")} Cooling Off`, sub: "Production sliding vs prior form", rows: fallers, metric: (r) => `<span class="val neg">${r.trend_delta.toFixed(2)}</span>`, stroke: "var(--bad)" },
    { title: `${iconMark("gem")} Biggest Edges`, sub: "Model vs the sportsbook line — a big edge is not automatically a play; the approval gates decide", rows: edges, metric: (r) => `<span class="val cyan">${signedPct(r.edge)}</span>`, stroke: "var(--cyan)",
      // Say whether each edge actually IS a bet, so this column can never
      // contradict the Recommended page.
      tag: (r) => passesFilters(r)
        ? `<span style="color:var(--good)">${icon('check')} recommended</span>`
        : `<span style="opacity:.55">pass — didn't clear the gates</span>` },
  ];
  const host = document.getElementById("trending");
  host.innerHTML = cols.map((c) => `
    <div class="trend-col">
      <h3>${c.title}</h3><div class="colsub">${c.sub}</div>
      ${c.rows.length ? c.rows.map((r, i) => trendRow(r, i, c)).join("") : `<div class="empty" style="padding:24px">No movers.</div>`}
    </div>`).join("");
  revealChildren(host);
}

function trendRow(r, i, col) {
  const vals = (r.logs || []).map((l) => l.value);
  return `
    <div class="trow" onclick="openPlayer('${escapeHtml(r.player).replace(/'/g, "")}')">
      <div class="trank">${i + 1}</div>
      <div class="who"><div class="nm">${escapeHtml(r.player)}</div>
        <div class="mk">${escapeHtml(r.team)} · ${escapeHtml(r.market_label)}${col.tag ? ` · ${col.tag(r)}` : ""}</div></div>
      <div class="mini">${sparkline(vals, { w: 78, h: 30, stroke: col.stroke })}</div>
      ${col.metric(r)}
    </div>`;
}

/* ============================================================
   Players view — search + profile
   ============================================================ */
async function renderPlayers() {
  const q = state.search.trim().toLowerCase();
  let recs = state.data.recommendations;
  if (q) recs = recs.filter((r) => r.player.toLowerCase().includes(q));
  // one profile per player (first market listed)
  const seen = new Set();
  const players = recs.filter((r) => (seen.has(r.player) ? false : seen.add(r.player)));
  const host = document.getElementById("players");
  if (!players.length) {
    /* A profile is a prop card, so this pool is tonight's board — and a
       reliever who just got traded has no prop tonight. Searching him used
       to return a bare "no players match", which read as "we've never
       heard of him". Fall back to the roster directory: say who he is,
       where he plays, and why there is no card. */
    const misses = q ? await rosterMatches(q) : [];
    if (misses.length) {
      host.innerHTML = `
        <div class="empty" style="margin-bottom:12px">No prop on tonight's board for
          “${escapeHtml(state.search)}” — profiles here are prop cards.
          On the roster${misses.length > 1 ? "s" : ""}:</div>
        ${misses.map((m) => `
          <div class="card roster-hit" style="display:flex;gap:12px;align-items:center;padding:12px 16px;margin-bottom:8px">
            ${playerAvatar(m.player, m.team, { size: 40 })}
            <div style="flex:1;min-width:0">
              <strong>${escapeHtml(m.player)}</strong>
              <div style="font-size:.85em;color:var(--text-mute)">
                ${teamMark(m.team, 14)} ${escapeHtml(teamName(m.team))}
                · ${escapeHtml(m.position || "—")}
                ${m.games ? `· ${m.games} game(s) logged` : ""}
                ${m.status ? `· ${escapeHtml(m.status)}` : ""}</div>
            </div>
            <button class="btn" onclick="openRoster('${escapeHtml(m.team)}')">Roster</button>
          </div>`).join("")}`;
      return;
    }
    host.innerHTML = `<div class="empty">No players match “${escapeHtml(state.search)}”.</div>`;
    return;
  }
  host.innerHTML = players.map(profileHTML).join("");
  fillMeters(host);
  revealChildren(host);
}

async function rosterMatches(q) {
  const d = await loadRosters(state.sport);
  const out = [];
  for (const t of Object.values(d.teams || {})) {
    for (const p of t.players || []) {
      if ((p.player || "").toLowerCase().includes(q)) out.push(p);
    }
  }
  out.sort((a, b) => (b.games || 0) - (a.games || 0)
    || a.player.localeCompare(b.player));
  return out.slice(0, 12);
}

function openRoster(team) {
  switchView("rosters");
  const search = document.getElementById("roster-search");
  if (search) {
    search.value = team;
    search.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

function profileHTML(r) {
  const f = r.form || {};
  const tiles = [["L1", f.last1], ["L3", f.last3], ["L5", f.last5], ["L10", f.last10], ["Season", f.season]]
    .map(([k, v]) => `<div class="form-tile"><div class="k">${k}</div><div class="v">${v == null ? "—" : v}</div></div>`).join("");
  const vals = (r.logs || []).map((l) => l.value);
  // MLB/NBA logs are one GAME per row (with a real date); NFL logs are weeks.
  const mlb = state.sport !== "nfl";
  const rows = (r.logs || []).map((l) => {
    const hit = l.value > r.line;
    // "Wk" is football vocabulary — an MLB log without a stored date is
    // still a GAME index, not a week.
    const when = mlb ? (l.date ? formatGameDate(l.date) : `G ${l.week}`) : `Wk ${l.week}`;
    return `<tr><td>${escapeHtml(when)}</td><td>${l.home ? "vs" : "@"} ${escapeHtml(l.opponent)}</td>
      <td class="num ${hit ? "hit" : "miss"}">${l.value}</td></tr>`;
  }).join("");
  const grad = `linear-gradient(135deg, ${teamPrimary(r.team)}, transparent)`;
  return `
    <article class="profile" style="--profile-grad:${grad}">
      <div class="profile-head">
        ${playerAvatar(r.player, r.team, { size: 60, headshot: r.headshot })}
        <div class="meta"><div class="nm">${escapeHtml(r.player)}</div>
          <div class="sub">${teamMark(r.team, 16)} ${[teamName(r.team), r.position, "vs " + teamName(r.opponent)]
            .filter((x) => x && x !== "vs ").map(escapeHtml).join(" · ")}</div></div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>
      </div>
      <div class="form-tiles">${tiles}</div>
      <div class="profile-spark">${sparkline(vals, {
        line: r.line, stroke: teamPrimary(r.team), h: 72,
        labels: (r.logs || []).map((l) =>
          `${mlb ? (l.date ? formatGameDate(l.date) : "G " + l.week) : "Wk " + l.week} ${l.home ? "vs" : "@"} ${l.opponent}`),
      })}</div>
      <table class="log-table">
        <tr><th>${mlb ? "Game" : "Week"}</th><th>Opponent</th><th style="text-align:right">${escapeHtml(r.market_label)}</th></tr>
        ${rows}
      </table>
      <div class="profile-pick">
        <div class="lbl">${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}
          <small>${escapeHtml(r.book)} ${american(r.odds)} · proj ${r.projection}
            · <span title="Probability the ${escapeHtml(r.side)} hits. Can side against the raw projection: baseball stats are right-skewed, so a few big games pull the AVERAGE above the line while MOST games still land under it.">${pct(r.hit_prob)} to hit</span>
            · edge ${signedPct(r.edge)}</small></div>
        <div style="min-width:120px">${confMeter(r)}</div>
      </div>
    </article>`;
}

function openPlayer(name) {
  state.search = name;
  document.getElementById("player-search").value = name;
  switchView("players");
  renderPlayers();
}

/* ---------------- count-up ---------------- */
function countUp(el) {
  const to = parseFloat(el.dataset.to) || 0, dec = +el.dataset.dec || 0;
  const pre = el.dataset.pre || "", suf = el.dataset.suf || "";
  const final = pre + to.toFixed(dec) + suf;
  const dur = 700, t0 = performance.now();
  (function tick(t) {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = pre + (to * e).toFixed(dec) + suf;
    if (p < 1) requestAnimationFrame(tick);
  })(t0);
  // Safety net: guarantee the true value even if rAF is throttled/stalled.
  setTimeout(() => { el.textContent = final; }, dur + 120);
}

/* ---------------- routing ---------------- */
/* ============================================================
   Track Record — the journal, on the site
   ============================================================ */
/* The record page used its own bare `.stat` divs, which had almost no CSS —
   that alone is why it read as a spreadsheet bolted to a designed site. It
   now speaks the same component vocabulary as everything else: `.tile`, with
   a `lead` variant for the two numbers that actually decide whether the
   process is working (ROI and CLV). */
function recTile(label, value, sub, opts) {
  const o = opts || {};
  // opts.help is a hover explanation for the desktop; a phone can't show a
  // title, which is why anything load-bearing belongs in `sub` instead.
  return `<div class="tile${o.lead ? " lead" : ""}"${
      o.help ? ` title="${escapeHtml(o.help)}"` : ""}>
    <div class="k">${label}</div>
    <div class="v${o.tone ? " " + o.tone : ""}">${value}</div>
    ${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;
}

const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");

/* A four-up grid of flex rows with five fixed-width columns each was clipping
   its own numbers — the net-units column ran off the right edge of every
   table. Fixed columns in a grid that is allowed to be narrow is the bug;
   these rows are a real grid whose label column is the one that gives. */
function recBucketTable(title, bucket) {
  const keys = Object.keys(bucket || {});
  if (!keys.length) return "";
  const anyClv = keys.some((k) => bucket[k].avg_clv != null);
  const rows = keys
    .sort((a, b) => (bucket[b].w + bucket[b].l) - (bucket[a].w + bucket[a].l))
    .map((k) => {
      const d = bucket[k];
      const net = d.net_u || 0;
      const n = d.w + d.l;
      const rate = n ? d.w / n : 0;
      const clv = anyClv
        ? `<span class="rb-clv" title="Average closing-line value — beating the close is the earliest sign a module earns">${
            d.avg_clv == null ? "—"
              : `${d.avg_clv >= 0 ? "+" : ""}${d.avg_clv.toFixed(2)}`}</span>` : "";
      return `<div class="rb-row">
        <span class="rb-name" title="${escapeHtml(k)}">${escapeHtml(k)}</span>
        <span class="rb-bar" aria-hidden="true"><i style="width:${(rate * 100).toFixed(1)}%"></i></span>
        <span class="rb-wl">${d.w}-${d.l}</span>${clv}
        <span class="rb-net ${toneOf(net)}">${net >= 0 ? "+" : ""}${net.toFixed(2)}u</span></div>`;
    }).join("");
  return `<div class="rec-bucket">
    <div class="rb-head">${escapeHtml(title)}</div>
    <div class="rb-rows${anyClv ? " has-clv" : ""}">
      <div class="rb-row rb-labels">
        <span class="rb-name">&nbsp;</span><span class="rb-bar"></span>
        <span class="rb-wl">W-L</span>${anyClv ? `<span class="rb-clv">CLV</span>` : ""}
        <span class="rb-net">Net</span></div>
      ${rows}</div></div>`;
}

function recCurveChart(curve) {
  if (!curve || curve.length < 2) return "";
  const w = 640, h = 190, padL = 46, padR = 14, padT = 16, padB = 28;
  const cums = curve.map((p) => p.cum_u);
  let lo = Math.min(0, ...cums), hi = Math.max(0, ...cums);
  if (hi - lo < 0.5) { hi += 0.25; lo -= 0.25; }
  const x = (i) => padL + (i / (curve.length - 1)) * (w - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB);
  const path = curve.map((p, i) => `${x(i).toFixed(1)},${y(p.cum_u).toFixed(1)}`).join(" L");
  const last = curve[curve.length - 1];
  const color = last.cum_u >= 0 ? "var(--good,#3ddc84)" : "var(--bad,#ff6b7a)";
  const dots = curve.map((p, i) => {
    // day_u is derivable from the running total, so a payload without it
    // gets the derived number instead of a TypeError. This mattered: a
    // fixture missing the field crashed recCurveChart, and because the
    // whole page is one template literal, the exception blanked EVERY
    // section of the Record page — one optional field, zero pages.
    const dayU = p.day_u != null ? p.day_u
      : p.cum_u - (i ? curve[i - 1].cum_u : 0);
    const tip = `${p.date} · day ${dayU >= 0 ? "+" : ""}${dayU.toFixed(2)}u (${p.n} bet${p.n === 1 ? "" : "s"}) · running ${p.cum_u >= 0 ? "+" : ""}${p.cum_u.toFixed(2)}u`;
    return `<circle cx="${x(i).toFixed(1)}" cy="${y(p.cum_u).toFixed(1)}" r="${i === curve.length - 1 ? 3.4 : 2.4}" fill="${color}"/>
      <circle cx="${x(i).toFixed(1)}" cy="${y(p.cum_u).toFixed(1)}" r="10" fill="transparent"
        style="pointer-events:all;cursor:pointer" data-tip="${escapeHtml(tip)}"/>`;
  }).join("");
  const yLabel = (v) => `<text x="${padL - 8}" y="${y(v) + 3.5}" text-anchor="end" font-size="10"
      fill="currentColor" opacity="0.45">${v >= 0 ? "+" : ""}${v.toFixed(1)}u</text>`;
  const grid = (v) => `<line x1="${padL}" y1="${y(v)}" x2="${w - padR}" y2="${y(v)}"
      stroke="currentColor" stroke-width="1" opacity="0.07"/>`;
  // The line alone floated in an empty box. Filling the area under it toward
  // the break-even axis is what makes a P&L curve read as a P&L curve at a
  // glance — above the dashed line is profit, below it is not.
  const area = `M${padL},${y(0)} L${path} L${x(curve.length - 1).toFixed(1)},${y(0)} Z`;
  const gid = `pnlfill${Math.random().toString(36).slice(2, 8)}`;
  const net = last.cum_u;
  return `
    <div class="section-title">Running P&amp;L
      <span class="sub">— every settled pick, by slate date</span></div>
    <div class="card rec-chart">
      <div class="rc-head">
        <div class="rc-net ${toneOf(net)}">${net >= 0 ? "+" : ""}${net.toFixed(2)}u</div>
        <div class="rc-span">${escapeHtml(curve[0].date)} → ${escapeHtml(last.date)}
          · ${curve.length} slate${curve.length === 1 ? "" : "s"}</div>
      </div>
      <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;display:block" role="img"
           aria-label="Cumulative units won or lost over time">
        <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.32"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient></defs>
        ${grid(hi)}${lo < 0 ? grid(lo) : ""}
        <path d="${area}" fill="url(#${gid})" stroke="none"/>
        <line x1="${padL}" y1="${y(0)}" x2="${w - padR}" y2="${y(0)}"
              stroke="currentColor" stroke-width="1" stroke-dasharray="4 4" opacity="0.3"/>
        ${Math.abs(y(0) - y(hi)) > 14 ? yLabel(hi) : ""}${yLabel(0)}${
          lo < 0 && Math.abs(y(lo) - y(0)) > 14 ? yLabel(lo) : ""}
        <text x="${padL}" y="${h - 8}" font-size="10" fill="currentColor" opacity="0.45">${escapeHtml(curve[0].date)}</text>
        <text x="${w - padR}" y="${h - 8}" text-anchor="end" font-size="10" fill="currentColor" opacity="0.45">${escapeHtml(last.date)}</text>
        <path d="M${path}" fill="none" stroke="${color}" stroke-width="2.2"
              stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
      </svg>
      <div class="rc-foot">Hover a dot for that day's bets. Flat units — every pick
        weighted by its stake, no bankroll compounding.</div>
    </div>`;
}

function recEraSection(er) {
  const eras = (er || {}).eras || [];
  // Nothing to compare until there's more than one era with any activity.
  const active = eras.filter((e) => e.settled || e.open);
  if (eras.length < 2 || active.length < 1) return "";
  const row = (e, isCurrent) => {
    const graded = e.wins + e.losses;
    const range = e.from
      ? `since ${e.from}` : (e.to ? `through ${e.to}` : "");
    const roiTxt = graded
      ? `${e.roi >= 0 ? "+" : ""}${(e.roi * 100).toFixed(1)}%`
      : "—";
    const clv = e.avg_clv != null
      ? ` · CLV ${e.avg_clv >= 0 ? "+" : ""}${e.avg_clv.toFixed(2)} pts (${e.clv_n})`
      : "";
    const sports = Object.entries(e.by_sport || {}).map(([s, d]) =>
      `${s.toUpperCase()} ${d.w}-${d.l} (${d.net_u >= 0 ? "+" : ""}${d.net_u.toFixed(2)}u)`)
      .join(" · ");
    return `
      <div style="display:flex;gap:12px;align-items:center;padding:10px 14px;
                  border-bottom:1px solid rgba(255,255,255,.05)${isCurrent ? "" : ";opacity:.75"}">
        <span style="flex:1;min-width:0">
          <strong>${escapeHtml(e.label)}</strong>
          ${isCurrent ? `<span class="chip" style="margin-left:6px">running now</span>` : ""}
          <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">
            ${escapeHtml(range)}${sports ? ` · ${sports}` : ""}${clv}</span>
        </span>
        <span style="text-align:right;white-space:nowrap">
          <strong>${e.wins}-${e.losses}</strong>
          <span style="display:block;font-size:var(--fs-sm)" class="${toneOf(e.net_units)}">
            ${graded ? `${e.net_units >= 0 ? "+" : ""}${e.net_units.toFixed(2)}u · ${roiTxt} ROI`
                     : `${e.open} open — accruing`}</span>
        </span>
      </div>`;
  };
  return `
    <div class="section-title">Model eras — did the re-tune work?
      <span class="sub">— the record split at each model change. Old losses belong to
      gates that no longer exist; the current era is the model being judged now.</span></div>
    <div class="card" style="padding:0">
      ${eras.map((e) => row(e, e.key === er.current)).join("")}
      <p style="padding:8px 14px;margin:0;font-size:var(--fs-xs);color:var(--text-mute)">
        CLV (closing-line value) is the fast signal — beating the close consistently
        shows up weeks before the W-L means anything. Judge the new era on CLV first,
        ROI once it has 50+ graded bets.</p>
    </div>`;
}

/* The parlay bucket. §13 is explicit that this is reported separately and
   never blended, so it gets its own section, its own notional and its own
   ROI — and it leads with the one sentence that matters while the module is
   on probation: whether the same legs bet singly would have done better. */
function recParlaySection(pz) {
  if (!pz || (!pz.graded && !pz.open)) return "";
  const pr = pz.promotion || {};
  const sc = pz.singles_comparison || {};
  const cond = (ok, label) =>
    `<span class="pl-cond${ok ? " met" : ""}">${ok ? icon("check") : icon("dash")}
      ${escapeHtml(label)}</span>`;
  // The honest headline. If flat singles on the same legs beat the tickets,
  // that IS the finding, and it should not need reconstructing from a table.
  const verdict = sc.n
    ? `<div class="pl-verdict" style="color:var(--${
        sc.singles_better ? "warn" : "good"})">
       Across ${sc.n} graded ticket(s): parlays
       <strong>${sc.parlay_units >= 0 ? "+" : ""}${sc.parlay_units.toFixed(2)}u</strong>,
       the same legs bet singly
       <strong>${sc.singles_units >= 0 ? "+" : ""}${sc.singles_units.toFixed(2)}u</strong>.
       ${sc.singles_better
         ? "Singles were better — the structure is costing money."
         : "The structure has paid for itself so far."}</div>`
    : "";
  const codes = (pz.loss_codes || []).length
    ? `<div class="pl-codes">${pz.loss_codes.map((c) =>
        `<span class="chip">${escapeHtml(c.code)} ×${c.n}</span>`).join(" ")}</div>`
    : "";
  const rows = (pz.recent || []).map((t) => {
    const pnl = t.pnl_units || 0;
    const won = t.status === "won";
    const vd = t.status === "void";
    const legs = (t.legs || []).map((l) => {
      const s = l.status === "won" ? "won" : l.status === "lost" ? "lost" : "push";
      return `<span class="pl-leg ${s}"><span class="pl-mark">${
        l.status === "won" ? icon("check")
          : l.status === "lost" ? icon("cross") : icon("dash")}</span>${
        escapeHtml(l.player || "")} ${escapeHtml(l.side || "")} ${l.line ?? ""}
        <span style="opacity:.6">${escapeHtml(l.market || "")}</span></span>`;
    }).join("");
    return `<div class="rl-row has-legs ${vd ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${vd ? icon("dash") : won ? icon("check") : icon("cross")}</span>
      <span class="rl-date">${escapeHtml(t.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml((t.sport || "").toUpperCase())}
        ${(t.legs || []).length}-leg</strong>
        <span class="rl-bet">Type ${escapeHtml(t.parlay_type || "A")} ·
        ${escapeHtml(t.grade || "")}${t.was_play ? " · slate play" : ""}</span></span>
      <span class="rl-proc"></span>
      <span class="rl-odds">${t.assumed_american == null ? "—"
        : american(t.assumed_american)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
      <span class="pl-legs">${legs}</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">Parlays — graded, never staked
      <span class="sub">— on probation until 100 tickets clear the bar. Never
      mixed into the record above.</span></div>
    ${recDisclosure("Why these stake nothing", `${escapeHtml(pr.note || "")}
      Every ticket here is graded at a flat one-unit notional so the ROI means
      something, and at a zero real stake so the account never moves. Tickets
      we <em>declined</em> are journaled too — recording only the ones that
      cleared would measure the gates on the handful of nights they said yes,
      and never test the no. Prices are an assumption, not a quote: no odds
      feed we ingest carries same-game-parlay prices, so each ticket is graded
      at the modelled likely-case price and labelled as such.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI",
                (pz.roi >= 0 ? "+" : "") + ((pz.roi || 0) * 100).toFixed(1) + "%",
                `${pz.net_units >= 0 ? "+" : ""}${(pz.net_units || 0).toFixed(2)}u notional`,
                { lead: true, tone: toneOf(pz.roi) })}
      ${recTile("Ticket record", `${pz.wins || 0}-${pz.losses || 0}`,
                `${pz.open || 0} open · ${pz.voided || 0} void`)}
      ${recTile("Probation", `${pr.tickets_have || 0}/${pr.tickets_required || 100}`,
                "graded tickets before anything is staked")}
      ${recTile("Leg CLV", pz.avg_leg_clv == null ? "—"
                  : (pz.avg_leg_clv >= 0 ? "+" : "") + pz.avg_leg_clv.toFixed(2),
                pz.leg_clv_n ? `across ${pz.leg_clv_n} legs` : "accrues as legs settle",
                { tone: toneOf(pz.avg_leg_clv) })}
    </div>
    <div class="pl-conds">
      ${cond(pr.tickets_have >= pr.tickets_required,
             `${pr.tickets_required || 100} graded tickets`)}
      ${cond(pr.roi_positive, "positive flat-stake ROI")}
      ${cond(pr.clv_non_negative, "leg CLV at or above zero")}
      ${cond(pr.z_clears, `z ≥ ${pr.z_required || 2}${
        pz.z == null ? "" : ` (now ${pz.z.toFixed(2)})`}`)}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${verdict}${rows ||
      `<p class="loading" style="padding:12px">No ticket has settled yet — accrues from tonight's board.</p>`}${codes}</div>`;
}

function recLongshotSection(ls) {
  // Show whenever EITHER bucket has data — after the watchlist split the
  // picks record can be tiny while the calibration sample is huge.
  const hasWatch = ls && ls.watch && (ls.watch.graded || ls.watch.open);
  if (!ls || (!ls.settled && !ls.open && !hasWatch)) return "";
  const graded = ls.wins + ls.losses;
  const hitRate = graded ? (ls.wins / graded) * 100 : 0;
  const calib = ls.avg_model_prob != null
    ? `<div style="opacity:.7;font-size:.9em;padding:8px 14px">
         Calibration (picks + watchlist, ${ls.calibration_n || 0} graded): model claimed
         <strong>${(ls.avg_model_prob * 100).toFixed(1)}%</strong>
         on average · books implied <strong>${(ls.avg_implied_prob * 100).toFixed(1)}%</strong>
         · actually hit <strong>${(ls.actual_hit_rate * 100).toFixed(1)}%</strong>.
         Model above books AND actual above implied = the board finds real value.</div>` : "";
  const watch = ls.watch && (ls.watch.graded || ls.watch.open)
    ? `<div style="opacity:.7;font-size:.9em;padding:8px 14px;border-top:1px solid rgba(128,128,128,.15)">
         Watchlist sample — <b>closed, no longer growing</b>. This tracked every
         real-priced homer on the slate to tune the model, at a couple of hundred rows a
         night, and it was more journal than the picks it was meant to inform.
         Final: <strong>${ls.watch.wins}/${ls.watch.graded}</strong> graded
         (${ls.watch.open} still open), flat-stake
         <strong>${ls.watch.roi >= 0 ? "+" : ""}${(ls.watch.roi * 100).toFixed(1)}% ROI</strong>.
         It never entered the record above.</div>` : "";
  // Same row component as the main settled list, so it inherits the same
  // alignment and the same phone treatment instead of clipping mid-word.
  const rows = (ls.recent || []).map((b) => {
    const won = b.status === "won";
    const push = b.status === "push";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">${escapeHtml(b.market_label || "HR")}</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `model ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">Long Shots — tracked separately
      <span class="sub">— home runs &amp; anytime TDs, with their own ROI. Never mixed
      into the record above.</span></div>
    ${recDisclosure("Why these are quarantined", `Only the board's actual
      PICKS — three per night at most — count toward this record, graded at a flat 0.1u
      nominal stake with zero bankroll impact. The watchlist (every real-priced home run
      on the slate, sometimes 100+ names) is tracked separately as a calibration sample
      and never enters this W-L: recommend a couple hundred homers a night and a handful
      always land, which proves nothing. These markets are long shots by nature, so even
      picks that clear the main board's bar are quarantined here — a night of +650 darts
      would otherwise make the headline record describe the dart board instead of the
      picks the model stands behind. Judge the ROI and calibration over weeks, not the
      hit column.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", (ls.roi >= 0 ? "+" : "") + (ls.roi * 100).toFixed(1) + "%",
                `${ls.net_units >= 0 ? "+" : ""}${(ls.net_units || 0).toFixed(2)}u on ${(ls.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(ls.roi) })}
      ${recTile("Long-shot record", `${ls.wins}-${ls.losses}`,
                `picks only · ${ls.open} open`)}
      ${recTile("Hit rate", hitRate.toFixed(1) + "%",
                ls.avg_implied_prob != null
                  ? `books implied ${(ls.avg_implied_prob * 100).toFixed(1)}%`
                  : "plus-money — low is normal")}
      ${recTile("Avg price", ls.avg_odds == null ? "—" : american(ls.avg_odds),
                ls.odds_range ? `range ${american(ls.odds_range[0])} to ${american(ls.odds_range[1])}`
                              : "accrues as picks settle")}
    </div>
    ${Object.keys(ls.by_sport || {}).length > 1 ? `<div style="margin-top:8px">
      ${Object.entries(ls.by_sport).map(([s, d]) =>
        `<span class="chip">${escapeHtml(s.toUpperCase())} ${d.w}/${d.n}
           (${d.net_u >= 0 ? "+" : ""}${d.net_u.toFixed(2)}u)</span>`).join(" ")}</div>` : ""}
    <div class="card" style="padding:0;margin-top:12px">${calib}${rows ||
      `<p class="loading" style="padding:12px">Nothing settled yet — accrues from tonight's board.</p>`}${watch}</div>`;
}

/* Calibration: when the model said X%, how often did it actually happen.
   Rendered as honest rows with a sample-size band — small buckets read as
   "too early", never as verdicts. */
function calBucketRows(buckets) {
  return (buckets || []).map((b) => {
    const off = Math.abs(b.actual - b.predicted);
    const flag = b.n < 20 ? `<span style="opacity:.5">n=${b.n} — too early</span>`
      : b.in_band ? `<span style="color:var(--good)">${icon('check')} within noise (n=${b.n})</span>`
      : `<span style="color:var(--warn)">${icon('warn')} off by ${(off * 100).toFixed(0)} pts (n=${b.n})</span>`;
    const bar = (v, color) => `<span style="display:inline-block;height:8px;border-radius:4px;
        width:${Math.max(2, v * 100)}px;background:${color};vertical-align:middle"></span>`;
    return `<div style="display:flex;gap:12px;align-items:center;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);flex-wrap:wrap">
      <span style="min-width:78px;opacity:.7">${b.lo}–${b.hi}%</span>
      <span style="flex:1;min-width:220px">
        ${bar(b.predicted, "var(--brand)")} <span style="font-size:.8em;opacity:.65">said ${(b.predicted * 100).toFixed(0)}%</span>
        &nbsp; ${bar(b.actual, b.in_band ? "var(--good)" : "var(--warn)")} <span style="font-size:.8em;opacity:.65">hit ${(b.actual * 100).toFixed(0)}%</span>
      </span>
      <span style="min-width:150px;text-align:right;font-size:.85em">${flag}</span>
    </div>`;
  }).join("");
}

/* The reliability diagram — the bucket rows above as a picture.

   The rows are honest but they are a table, and a table hides the one thing
   this chart exists to show: the DIRECTION and SHAPE of the error. A model
   that runs hot everywhere sits entirely below the diagonal, which is a
   tempering problem with a one-line fix. A model that is hot on favourites
   and cold on longshots crosses the diagonal, which is a different problem
   entirely — and in a list of numbers the two look identical.

   Dot area is proportional to bucket population, not radius, because radius
   scaling triples the apparent weight of a bucket that is three times
   bigger. Whiskers are the same ±1.96·√(p(1−p)/n) band the rows use: a dot
   whose whisker crosses the diagonal has not missed, it just has not
   spoken yet. */
function reliabilityDiagram(buckets) {
  const pts = (buckets || []).filter((b) => b.n > 0);
  if (pts.length < 2) return "";
  // Square plot with headroom above it. The "perfect" label belongs at the
  // top end of the diagonal, which is also where a well-calibrated model's
  // biggest favourites sit — inside the box it lands on a dot. padT buys it
  // a line of its own without squashing the plot into a rectangle.
  const w = 320, pad = 34, padT = 48;
  const span = w - pad * 2;
  const h = padT + span + pad;
  const x = (v) => pad + v * span;
  const y = (v) => padT + (1 - v) * span;
  const maxN = Math.max(...pts.map((b) => b.n));
  const tick = (v) => `
    <line x1="${x(v)}" y1="${h - pad}" x2="${x(v)}" y2="${h - pad + 4}"
          stroke="currentColor" opacity=".35"/>
    <text x="${x(v)}" y="${h - pad + 15}" text-anchor="middle" font-size="9"
          fill="currentColor" opacity=".45">${(v * 100).toFixed(0)}</text>
    <line x1="${pad - 4}" y1="${y(v)}" x2="${pad}" y2="${y(v)}"
          stroke="currentColor" opacity=".35"/>
    <text x="${pad - 7}" y="${y(v) + 3}" text-anchor="end" font-size="9"
          fill="currentColor" opacity=".45">${(v * 100).toFixed(0)}</text>`;
  const dots = pts.map((b) => {
    const r = 3 + 7 * Math.sqrt(b.n / maxN);
    const col = b.n < 20 ? "var(--text-mute)"
      : b.in_band ? "var(--good)" : "var(--warn)";
    const lo = Math.max(0, b.actual - b.ci), hi = Math.min(1, b.actual + b.ci);
    return `<line x1="${x(b.predicted).toFixed(1)}" y1="${y(lo).toFixed(1)}"
                  x2="${x(b.predicted).toFixed(1)}" y2="${y(hi).toFixed(1)}"
                  stroke="${col}" stroke-width="1.5" opacity=".55"/>
      <circle cx="${x(b.predicted).toFixed(1)}" cy="${y(b.actual).toFixed(1)}"
              r="${r.toFixed(1)}" fill="${col}" fill-opacity=".75" stroke="${col}">
        <title>Said ${(b.predicted * 100).toFixed(0)}%, hit ${(b.actual * 100).toFixed(0)}% — ${b.n} bets</title>
      </circle>`;
  }).join("");
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;max-width:340px;height:auto;display:block;margin:0 auto"
       role="img" aria-label="Reliability diagram: forecast probability against realized hit rate">
    <rect x="${pad}" y="${padT}" width="${span}" height="${span}" fill="none"
          stroke="currentColor" opacity=".12"/>
    <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="currentColor"
          stroke-width="1" stroke-dasharray="4 4" opacity=".4"/>
    <text x="${x(1)}" y="${y(1) - 8}" text-anchor="end" font-size="9"
          fill="currentColor" opacity=".45">perfect</text>
    ${[0, 0.25, 0.5, 0.75, 1].map(tick).join("")}
    ${dots}
    <text x="${w / 2}" y="${h - 4}" text-anchor="middle" font-size="10"
          fill="currentColor" opacity=".55">model said (%)</text>
    <text x="11" y="${h / 2}" text-anchor="middle" font-size="10" fill="currentColor"
          opacity=".55" transform="rotate(-90 11 ${h / 2})">actually hit (%)</text>
  </svg>`;
}

/* Brier and log loss, side by side, each against the de-vigged market on the
   same picks. Two strictly proper rules rather than one, because they
   disagree in a way that is itself informative: Brier charges 0.90 for a
   confident miss and log loss charges 3.00, so a model that wins on Brier
   and loses on log loss is paying for rare, loud, wrong calls. */
function scoreRule(label, model, market, edge, note) {
  if (edge == null) return "";
  const good = edge > 0;
  return `<div style="flex:1;min-width:170px">
    <div style="font-size:.78em;letter-spacing:.04em;text-transform:uppercase;
                opacity:.55;margin-bottom:3px">${escapeHtml(label)}</div>
    <div style="font-size:1.05em;font-variant-numeric:tabular-nums">
      <span style="color:var(--${good ? "good" : "warn"})">${model}</span>
      <span style="opacity:.45"> vs ${market} market</span></div>
    <div style="font-size:.8em;opacity:.6;margin-top:2px">${escapeHtml(note)}</div>
  </div>`;
}

function calScoreBlock(cal) {
  const cards = [
    scoreRule("Brier", cal.brier_model, cal.brier_market, cal.brier_edge,
              cal.brier_edge > 0 ? "we forecast our own picks better"
                                 : "the market forecasts our picks better"),
    scoreRule("Log loss", cal.logloss_model, cal.logloss_market, cal.logloss_edge,
              cal.logloss_edge > 0 ? "and it holds under the harsher rule"
                                   : "the confident calls are where it costs"),
  ].filter(Boolean).join("");
  if (!cards) return "";
  const ece = cal.ece == null ? "" : `<div style="flex:1;min-width:170px">
    <div style="font-size:.78em;letter-spacing:.04em;text-transform:uppercase;
                opacity:.55;margin-bottom:3px">Calibration error</div>
    <div style="font-size:1.05em;font-variant-numeric:tabular-nums">${(cal.ece * 100).toFixed(1)} pts</div>
    <div style="font-size:.8em;opacity:.6;margin-top:2px">average distance from the diagonal</div>
  </div>`;
  const disagree = (cal.brier_edge != null && cal.logloss_edge != null
                    && (cal.brier_edge > 0) !== (cal.logloss_edge > 0))
    ? `<p style="margin:10px 0 0;font-size:.85em;color:var(--warn)">The two rules
        disagree. Both are strictly proper, so this is not a contradiction — it
        means the gap between us and the market is concentrated in the
        confident calls rather than spread across the book. Log loss is the
        one that punishes those, so it is the one to believe.</p>` : "";
  return `<div style="padding:12px 14px;border-top:1px solid rgba(255,255,255,.06)">
    <div style="display:flex;gap:18px;flex-wrap:wrap">${cards}${ece}</div>
    <p style="margin:10px 0 0;font-size:.85em;opacity:.62">Lower is better for both.
      Scored against the de-vigged closing price on the same bets — if we can't
      out-forecast the close on our own selections, the edge story is fiction.
      Shown either way, because a site that hides this number is a tout with a
      website.</p>${disagree}</div>`;
}

/* Calibration split by market and by horizon.

   The aggregate is the honest headline, and it is also where a real defect
   hides: a model three points hot on one market and three cold on another
   averages to a line that looks perfect. Measured on a test board, an
   aggregate ECE of 7.4 points covered one market sitting dead on the
   diagonal and another twenty points hot.

   Behind a disclosure because it is diagnostic, not the answer — and
   because a page that opens with eleven charts has no headline at all. */
function calSplitRow(label, c) {
  const ece = c.ece == null ? "—" : (c.ece * 100).toFixed(1) + " pts";
  const tone = c.ece == null ? "" : c.ece <= 0.03 ? "var(--good)"
    : c.ece <= 0.07 ? "var(--warn)" : "var(--bad)";
  return `<div style="display:flex;gap:12px;align-items:baseline;padding:6px 0;
      border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em">
    <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
                 white-space:nowrap">${escapeHtml(label)}</span>
    <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${c.n}</span>
    <span style="min-width:74px;text-align:right;color:${tone};
                 font-variant-numeric:tabular-nums">${ece}</span>
  </div>`;
}

function recCalibrationSplits(s) {
  if (!s) return "";
  // Raw market keys, as recBucketTable already shows them a few sections up.
  // Two names for one market on one page is worse than one ugly name.
  const mk = (s.markets || []).map((c) => calSplitRow(c.market, c)).join("");
  const hz = (s.horizons || []).map((c) => calSplitRow(c.label, c)).join("");
  if (!mk && !hz) return "";
  const held = s.markets_held_back
    ? `<p style="margin:6px 0 0;font-size:.82em;opacity:.55">
        ${s.markets_held_back} more market(s) haven't reached ${s.min_n} graded
        picks. They're in the headline number above — they just can't carry a
        row of their own yet, because the band would be wider than any miss it
        could show.</p>` : "";
  // Degenerate means fewer than two buckets clear the bar — so the rows are
  // worth showing but a COMPARISON between them is not yet supported. The
  // first draft of this copy said "every pick resolves the day it was
  // published" while a 1–3 day row sat underneath it, which is the kind of
  // sentence that quietly teaches a reader to stop trusting the captions.
  const hzBlock = !hz ? "" : s.horizon_degenerate
    ? `<div class="section-title">By horizon</div>
       <p style="margin:0;font-size:.85em;opacity:.6">Only one horizon has
         reached ${s.min_n} graded picks, so there is nothing to compare
         against yet — read these as counts, not as a trend. Calibration is
         known to decay the further out you forecast, and this will say
         something real once futures start settling.</p>${hz}`
    : `<div class="section-title">By horizon
         <span class="sub">— calibration decays the further out you forecast.</span></div>
       ${hz}`;
  return recDisclosure("Calibration by market and horizon", `
    <p style="margin:0 0 8px;font-size:.85em;opacity:.7">Distance from the
      diagonal, per slice. The headline number can look clean while covering a
      market that runs hot and one that runs cold — they average out, and the
      average is the one figure that cannot show it.</p>
    ${mk ? `<div class="section-title">By market</div>${mk}${held}` : ""}
    ${hzBlock}`);
}

/* The forecast log. "Permanent and time-stamped" is a promise until it is
   checkable; this is what makes it checkable. */
function recForecastLog(f) {
  if (!f || !f.n) return "";
  if (!f.ok) {
    return `<div class="card" style="padding:12px 14px;margin-top:12px;
        border-color:var(--bad)">
      <strong style="color:var(--bad)">Forecast log broken at #${f.broken_at}.</strong>
      <p style="margin:6px 0 0;font-size:.87em">Entries up to
        #${f.verified_through} still verify; everything after that one is no
        longer provable. Shown rather than hidden — a tamper-evident log that
        hides its own alarm is decoration.</p></div>`;
  }
  return `<div class="card" style="padding:12px 14px;margin-top:12px">
    <div style="font-size:.8em;letter-spacing:.04em;text-transform:uppercase;
                opacity:.55">Forecast log · ${f.n.toLocaleString()} sealed</div>
    <div style="font-family:var(--font-mono);font-size:.8em;word-break:break-all;
                margin-top:4px;opacity:.85">${escapeHtml(f.head || "")}</div>
    <p style="margin:6px 0 0;font-size:.84em;opacity:.62">Every pick is hashed
      together with the hash before it, so editing or deleting any past
      forecast changes every hash after it and the chain reports where. The
      log holds only what was CLAIMED — never the result, the P&amp;L or the
      closing line, which arrive later and would mean writing into a row
      that is supposed to be frozen. Write this number down: if it ever
      covers a different past, that is detectable rather than deniable.</p>
  </div>`;
}

/* The learning loop, on the page.

   Everything here happens nightly with nobody touching a dial: the refit
   reads every settled bet and turns one temperature per market, a fit that
   runs to its search boundary closes the market by itself, and every sweep
   is stamped with the commit that produced it. It was all real and all
   invisible — and a learning loop nobody can see is indistinguishable from
   a static model. */
function recRestatedSection(rs, sport) {
  // The record re-sized on today's staking scale (1u = 1% of bankroll,
  // grade caps, price-band ceilings). The official record stays the
  // receipts of bets as they were made — this answers "what WOULD it
  // read" without editing a settled row.
  if (!rs) return "";
  const r = sport ? (rs.by_sport || {})[sport] : rs.overall;
  if (!r || !r.settled) return "";
  const roi = (r.roi ?? 0) * 100;
  const tone = (v) => v >= 0 ? "var(--good)" : "var(--bad)";
  return `
    <div class="section-title">At today's sizing
      <span class="sub">— the same graded picks, re-staked by the current
      model: 1u = 1% of bankroll, conviction plays near a unit, +200-or-longer
      capped at a dime. The official record above is the receipts as bet;
      this is what those picks would have returned under the sizing that now
      governs the board.</span></div>
    <div class="stats">
      <div class="tile"><div class="k">Restated record</div>
        <div class="v">${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ""}</div>
        <div class="tile-sub">${(r.settled ?? 0).toLocaleString()} pick(s) re-sized</div></div>
      <div class="tile"><div class="k">Units staked</div>
        <div class="v">${(r.units_staked ?? 0).toLocaleString()}</div></div>
      <div class="tile"><div class="k">Net units</div>
        <div class="v" style="color:${tone(r.net_units ?? 0)}">${(r.net_units ?? 0) >= 0 ? "+" : ""}${(r.net_units ?? 0).toFixed(2)}</div></div>
      <div class="tile"><div class="k">Restated ROI</div>
        <div class="v" style="color:${tone(roi)}">${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%</div>
        <div class="tile-sub">weighted by conviction, not by ticket count</div></div>
    </div>
    ${r.excluded ? `<p class="loading" style="margin-top:8px">${r.excluded.toLocaleString()}
      old pick(s) are excluded — at their journaled probability and price,
      today's Kelly would not have made those bets at all.</p>` : ""}`;
}

function recProseSection(pz, sport) {
  // The prose lanes: the nightly postmortem and the weekly model brief.
  // The LLM narrates numbers the arithmetic already produced — never a
  // probability, never a pick. Scoped views show the sport's own
  // paragraph; coverage is structural (the engine back-fills every sport
  // it tracks), so a missing note means a missing night, not a mood.
  if (!pz || (!pz.postmortem && !pz.brief)) return "";
  const para = (e, missing) => {
    if (!e) return "";
    const note = sport ? ((e.by_sport || {})[sport] || missing) : e.overall;
    const when = e.date || e.week_of || "";
    return `
      <div style="padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.05)">
        <div style="font-weight:600;margin-bottom:4px">${escapeHtml(e.headline || "")}
          <span style="opacity:.45;font-weight:400;font-size:.85em"> · ${escapeHtml(when)}</span></div>
        <p style="margin:0;font-size:.9em;line-height:1.5">${escapeHtml(note || "")}</p>
        ${!sport && Object.keys(e.by_sport || {}).length ? `
          <div style="margin-top:8px;display:flex;flex-direction:column;gap:4px">
            ${Object.entries(e.by_sport).map(([sp, n]) => `
              <div style="font-size:.85em;color:var(--text-mute)">
                <span class="chip">${escapeHtml(sp.toUpperCase())}</span> ${escapeHtml(n)}</div>`).join("")}
          </div>` : ""}
      </div>`;
  };
  const capNote = pz.capped ? `
    <p style="padding:8px 14px;margin:0;font-size:.82em;color:var(--text-mute)">
      Paused for the month — the $${(pz.cap_usd ?? 5).toFixed(2)} LLM spend cap
      is reached ($${(pz.month_usd ?? 0).toFixed(2)} used). The arithmetic
      keeps learning either way; only the narration waits.</p>` : "";
  return `
    <div class="section-title">The night desk
      <span class="sub">— the one other job an AI that writes prose gets here:
      narrating. A nightly postmortem of what actually graded and a weekly
      note on what the learning ladder did — written from the arithmetic's
      own numbers, never setting one. Capped spend, every call on the
      ledger.</span></div>
    <div class="card" style="padding:0">
      ${para(pz.postmortem, `No ${escapeHtml((sport || "").toUpperCase())} picks graded that night.`)}
      ${para(pz.brief, `Quiet week for ${escapeHtml((sport || "").toUpperCase())}.`)}
      ${capNote}
    </div>`;
}

function recSelfTuningSection(st, sport) {
  // `sport` scopes the section to one league's own learning — the ladder
  // fits every sport separately, so each sport's record page shows ITS
  // rows rather than hiding the whole section behind the "All" scope
  // (which is how the learning shipped invisible: the page always lands
  // sport-scoped, and nobody clicks All).
  if (!st) return "";
  const only = (rows) => (rows || []).filter((r) => !sport || r.sport === sport);
  const markets = only(st.markets);
  const weights = only(st.weights);
  const players = only(st.players);
  const closed = only(st.closed);
  const trendEntries = Object.entries(st.trend || {})
    .filter(([sp]) => !sport || sp === sport);
  if (!markets.length && !weights.length && !players.length
      && !trendEntries.length) {
    if (!sport) return "";
    return `
    <div class="section-title">The model tunes itself
      <span class="sub">— settled bets fit the dials; nobody turns one by hand.</span></div>
    <div class="card"><p style="margin:0;padding:12px 14px;font-size:.87em;color:var(--text-mute)">
      Nothing tuned for ${escapeHtml(sport.toUpperCase())} yet. The fitters run
      on every settle pass, on this sport's own settled bets only, and adopt
      a correction only when it beats the spec in a walk-forward test — so this
      fills in as its journal deepens.</p></div>`;
  }
  const tone = (m) => m.at_boundary ? "var(--bad)"
    : Math.abs(m.temperature - 1) > 0.05 ? "var(--warn)" : "var(--good)";
  const rows = markets.map((m) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml((m.sport || "").toUpperCase())}</span>
      <span style="flex:1;min-width:120px">${escapeHtml(m.market)}</span>
      <span style="font-variant-numeric:tabular-nums" title="Temperature: >1 pulls probabilities toward 50% (the model ran hot), <1 pushes them out (it ran shy)">T ${(m.temperature ?? 1).toFixed(2)}</span>
      <span style="color:${tone(m)}">${escapeHtml(m.reading || "")}</span>
      <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${(m.samples ?? 0).toLocaleString()}</span>
      ${m.brier_before != null && m.brier_after != null && m.brier_after < m.brier_before
        ? `<span style="opacity:.6;font-variant-numeric:tabular-nums" title="Brier before → after the correction, on held-out outcomes">${m.brier_before.toFixed(4)} → ${m.brier_after.toFixed(4)}</span>` : ""}
    </div>`).join("");
  const weightRows = weights.map((w) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml((w.sport || "").toUpperCase())}</span>
      <span style="flex:1;min-width:120px">${escapeHtml(w.market || "")}</span>
      <span style="font-variant-numeric:tabular-nums" title="The recency dial: 0 is the hand-tuned spec curve, positive leans on recent form, negative on the long run. Moves only when the record beats the spec by a real margin.">dial ${(w.r ?? 0) >= 0 ? "+" : ""}${(w.r ?? 0).toFixed(1)}</span>
      <span style="color:${w.at_boundary ? "var(--bad)" : w.adopted ? "var(--warn)" : "var(--good)"}">${escapeHtml(w.reading || "")}</span>
      <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${(w.samples ?? 0).toLocaleString()}</span>
      ${w.adopted && w.brier_default != null && w.brier_fitted != null
        ? `<span style="opacity:.6;font-variant-numeric:tabular-nums" title="Walk-forward Brier, spec curve → fitted curve">${w.brier_default.toFixed(4)} → ${w.brier_fitted.toFixed(4)}</span>` : ""}
    </div>`).join("");
  const weightsBlock = !weightRows ? "" : `
    <div class="section-title">The recipe itself, refit
      <span class="sub">— not just the confidence: the blend a projection is built
      from. One dial per market decides how much recent form outweighs the long
      run; the record moves it only by beating the spec curve in a walk-forward
      test, and a dial it examined and left alone says so.</span></div>
    <div class="card" style="padding:0">${weightRows}</div>`;
  // The two walk-forward scores, shown whether the memory was adopted or
  // NOT. This used to render only on adopted rows, which meant a market
  // reading "memory off — didn't help" showed the verdict and hid the
  // evidence for it — you could not tell a memory that lost by a hair from
  // one that lost by a mile, and "didn't help" on its own reads like the
  // fit never ran. Both numbers are stored either way (playerfit.fit
  // computes them before it checks adoption), so there was nothing to
  // fetch — only something to stop hiding.
  const playerScore = (p) => {
    const before = p.score_baseline ?? p.brier_baseline;
    const after = p.score_corrected ?? p.brier_corrected;
    if (before == null || after == null) return "";
    const label = p.score_label || "Brier";
    // Lower is better for both Brier and projection error, so a fall is
    // the memory helping. Say which way it went in words — a reader should
    // not have to know that to read the row.
    const gain = before - after;
    const verdict = gain > 0 ? "memory scored better"
      : gain < 0 ? "memory scored worse" : "no difference";
    return `<span style="opacity:.6;font-variant-numeric:tabular-nums"
      title="Walk-forward ${escapeHtml(label)}, memory off → on: ${escapeHtml(verdict)} by ${Math.abs(gain).toFixed(5)}. Lower is better. Each bet's correction knew only that player's EARLIER games, so this is out-of-sample at every row. The memory switches on only when it wins by at least 0.0005.">${before.toFixed(4)} → ${after.toFixed(4)}</span>`;
  };
  const playerRows = players.map((p) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml((p.sport || "").toUpperCase())}</span>
      <span style="min-width:100px">${escapeHtml(p.market || "")}</span>
      <span style="flex:1;min-width:140px;color:${p.adopted ? "var(--warn)" : "var(--good)"}">${escapeHtml(p.reading || "")}</span>
      ${(p.top || []).length ? `<span style="opacity:.75">${(p.top || [])
        .map((t) => `${escapeHtml(t.player)} ×${(t.mult ?? 1).toFixed(2)}`)
        .join(" · ")}</span>` : ""}
      <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${(p.samples ?? 0).toLocaleString()}</span>
      ${playerScore(p)}
    </div>`).join("");
  const playersBlock = !playerRows ? "" : `
    <div class="section-title">Player memory
      <span class="sub">— who the blend persistently misreads. Each correction is
      shrunk by evidence and capped at ±15%, and the memory only switches on for
      a market when remembering players out-predicted forgetting them in a
      causal walk-forward test — "memory off" is a result, not a failure.</span></div>
    <div class="card" style="padding:0">${playerRows}</div>`;
  const trendRows = trendEntries.flatMap(([sp, mkts]) =>
    Object.entries(mkts).map(([mk, t]) => `
      <div style="display:flex;gap:12px;align-items:baseline;padding:6px 14px;
          border-bottom:1px solid rgba(255,255,255,.05);font-size:.86em;flex-wrap:wrap">
        <span class="chip">${escapeHtml(sp.toUpperCase())}</span>
        <span style="flex:1;min-width:120px">${escapeHtml(mk)}</span>
        <span style="font-variant-numeric:tabular-nums">ECE ${((t.first || {}).ece ?? 0).toFixed(3)}
          → <span style="color:var(--${t.improved ? "good" : "warn"})">${((t.last || {}).ece ?? 0).toFixed(3)}</span></span>
        <span style="opacity:.5">${t.runs} sweep${t.runs === 1 ? "" : "s"}${t.same_code ? "" : " · across code versions"}</span>
      </div>`)).join("");
  const lastRefit = st.last_refit ? st.last_refit.replace("T", " ") : "—";
  return `
    <div class="section-title">The model tunes itself
      <span class="sub">— a market is fitted once it clears 200 settled bets, and then
      LEFT ALONE. This is the site's AI lane: arithmetic on outcomes, reproducible and
      auditable, which is exactly why a chatbot never sets a probability here.</span></div>
    <div class="stats">
      <!-- This said "runs itself after every settle", which was not true and
           read as a broken feature when the date sat still for a day. The
           fitter DOES run after every settle; it deliberately skips any
           market it has already corrected, because those bets' outcomes
           were produced under the correction and refitting on them would
           compound. So the stamp only moves when a market is fitted for the
           FIRST time. Saying so is the difference between a frozen number
           that looks broken and one that looks finished. -->
      <div class="tile"><div class="k">Last new fit</div><div class="v" style="font-size:var(--fs-lg)">${escapeHtml(lastRefit)}</div>
        <div class="tile-sub">moves when a market is fitted for the first time —
          a corrected market is then left alone, since its later results
          were produced under that correction</div></div>
      <div class="tile"><div class="k">Markets tuned</div><div class="v">${markets.length}</div></div>
      <div class="tile"><div class="k">Self-closed</div><div class="v">${closed.length}</div>
        <div class="tile-sub">a fit at its boundary shuts its own market</div></div>
      <div class="tile"><div class="k">Improving</div><div class="v">${(() => {
        const flat = trendEntries.flatMap(([, mkts]) => Object.values(mkts));
        return flat.length
          ? `${flat.filter((t) => t.improved).length}/${flat.length}` : "—";
      })()}</div>
        <div class="tile-sub">markets whose calibration error is falling</div></div>
    </div>
    <div class="card" style="padding:0">${rows}</div>
    ${weightsBlock}
    ${playersBlock}
    ${trendRows ? `<div class="section-title">Is it getting better?
        <span class="sub">— the same measurement over time, each sweep stamped with the commit
        that produced it, so a move ties to a change rather than to a memory.</span></div>
      <div class="card" style="padding:0">${trendRows}</div>` : ""}
    ${recDisclosure("Why no chatbot sets these numbers", `
      <p style="margin:0;font-size:.87em">The refit is one parameter found by
      arithmetic over every settled outcome. That makes it reproducible (the same
      journal always yields the same temperature), auditable (each sweep is stored
      with its commit), and honest (the reliability chart above shows exactly what
      it did). A language model can do none of those: it does not reproduce run to
      run, cannot be swept over a quarter-million historical props, and cannot be
      temperature-scaled. So AI here means the system correcting itself from its
      own record — and prose staying prose. The decision is recorded in the
      competitive recipe, because it is the one pillar competitors who sell picks
      structurally cannot copy.</p>`)}`;
}

function recLossPatternsSection(lp, sport) {
  if (!lp || !(lp.n_records ?? 0)) return "";
  // Sport scope: each league's page shows the patterns mined from ITS
  // graded bets. The mining stats tiles stay whole-journal (one sweep
  // covers every sport) and say so when scoped.
  const findings = (lp.findings || [])
    .filter((f) => !sport || f.sport === sport);
  const closed = (lp.closed || []).filter((c) => !sport || c.sport === sport);
  const tone = (f) => f.action === "close" ? "var(--bad)"
    : (f.gap_pts ?? 0) > 0 ? "var(--warn)" : "var(--text-mute)";
  const rows = findings.map((f) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml((f.sport || "").toUpperCase())}</span>
      <span style="min-width:100px">${escapeHtml(f.market || "all markets")}</span>
      <span style="flex:1;min-width:140px;font-weight:600">${escapeHtml(f.value || "")}</span>
      <span style="color:${tone(f)}">${escapeHtml(f.reading || "")}</span>
      ${f.action === "close"
        ? `<span class="chip" style="color:var(--bad)">vetoing picks</span>` : ""}
    </div>`).join("");
  const empty = (sport && (lp.findings || []).length) ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      No pattern involves ${escapeHtml(sport.toUpperCase())} — its graded bets
      are in every night's sweep, and a clean sheet here is the sweep's
      verdict, not its absence.</p>` : (lp.tested ?? 0) > 0 ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      Scanned ${lp.tested} slice${lp.tested === 1 ? "" : "s"} of
      ${(lp.n_records ?? 0).toLocaleString()} graded bets — nothing survives
      false-discovery control yet. Patterns that look real on small samples
      usually aren't, and a bar that bends to make the page interesting
      stops meaning anything. The bar stays.</p>` : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      Not enough graded bets in any one slice yet — a slice is only tested
      at ${lp.min_n ?? 40}+ settled picks. Every night's grades feed this.</p>`;
  return `
    <div class="section-title">Learning from losses
      <span class="sub">— the miner slices every graded bet by side, price band,
      stated probability, horizon and book, hunting pockets where the model's
      claims systematically missed. A pocket that runs hot enough closes itself
      and blocks new picks — the same self-closure markets already live under,
      one level finer.</span></div>
    <div class="stats">
      <div class="tile"><div class="k">Record mined</div><div class="v">${(lp.n_records ?? 0).toLocaleString()}</div>
        <div class="tile-sub">graded bets${sport ? ", all sports" : ""}, re-mined after every settle</div></div>
      <div class="tile"><div class="k">Slices tested</div><div class="v">${lp.tested ?? 0}</div>
        ${sport ? `<div class="tile-sub">whole journal, one sweep</div>` : ""}</div>
      <div class="tile"><div class="k">Patterns found</div><div class="v">${findings.length}</div>
        <div class="tile-sub">survivors of false-discovery control${sport ? `, ${escapeHtml(sport.toUpperCase())}` : ""}</div></div>
      <div class="tile"><div class="k">Self-closed</div><div class="v">${closed.length}</div>
        <div class="tile-sub">slices now vetoing new picks</div></div>
    </div>
    <div class="card" style="padding:0">${rows || empty}</div>
    ${recDisclosure("How this avoids fake trends", `
      <p style="margin:0;font-size:.87em">Every "trends" tab in this industry
      is a pattern-hallucination machine: slice one record forty ways and luck
      alone hands you two impressive streaks. Two disciplines here. First, a
      slice is judged on whether the model's own stated probabilities missed
      reality (said 64%, hit 51%) — not on win rate, which would flag every
      honest longshot bucket. Second, every slice tested enters a
      Benjamini–Hochberg false-discovery correction, and only survivors are
      findings — the flagged set is expected to be at most
      ${Math.round(((lp.alpha ?? 0.05) * 100))}% luck. A pattern that clears
      both bars closes its slice automatically; the pick engines refuse
      anything that lands in it, and the veto's reason names this page.</p>`)}`;
}

function recHypothesisLab(hl, sport) {
  if (!hl) return "";
  // Sport scope: each league's page shows the hypotheses ABOUT it. The
  // watchlist stays on the combined view — its ideas are free text with
  // no sport field to filter on.
  const hyps = (hl.hypotheses || [])
    .filter((h) => !sport || h.sport === sport);
  const n_of = (s) => hyps.filter((h) => h.status === s).length;
  const tone = (h) => h.action === "close" ? "var(--bad)"
    : h.status === "confirmed" ? "var(--warn)"
    : h.status === "rejected" ? "var(--good)" : "var(--text-mute)";
  const glyph = (h) => h.status === "confirmed" ? icon("check")
    : h.status === "rejected" ? icon("cross") : icon("dash");
  const rows = hyps.map((h) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:8px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span style="color:${tone(h)}">${glyph(h)}</span>
      <span class="chip">${escapeHtml((h.sport || "").toUpperCase())}</span>
      <span style="min-width:90px">${escapeHtml(h.market || "all markets")}</span>
      <span style="flex:1;min-width:160px">${escapeHtml(h.claim || "")}
        <span style="opacity:.55;display:block;font-size:.92em">${
          Object.entries(h.dims || {}).map(([d, v]) => escapeHtml(String(v))).join(" × ")}</span></span>
      <span style="color:${tone(h)}">${escapeHtml(h.reading
        || (h.status === "collecting"
            ? `collecting — ${(h.n ?? 0)} matching bets so far` : ""))}</span>
      ${h.action === "close"
        ? `<span class="chip" style="color:var(--bad)">vetoing picks</span>` : ""}
    </div>`).join("");
  const watch = sport ? "" : (hl.watchlist || []).map((w) => `
    <div style="padding:6px 14px;border-bottom:1px solid rgba(255,255,255,.05);
        font-size:.85em;color:var(--text-mute)">· ${escapeHtml(w)}</div>`).join("");
  const empty = (sport && (hl.hypotheses || []).length) ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      No hypothesis touches ${escapeHtml(sport.toUpperCase())} yet. The next
      <code>python3 hypotheses.py</code> run reads every sport's record —
      including this one — and proposes wherever the evidence points.</p>` : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      The lab is idle. Add <code>ANTHROPIC_API_KEY</code> to secrets.local and
      run <code>python3 hypotheses.py</code> — the model reads the record's own
      summary and proposes slice intersections the miner doesn't test. Every
      proposal faces the same statistics as everything else on this page;
      nothing an AI writes here can ever set a probability.</p>`;
  return `
    <div class="section-title">The hypothesis lab
      <span class="sub">— the one safe job for an AI that writes prose: propose.
      A language model reads the record's summary and suggests loss patterns
      built strictly from the miner's own tested dimensions — the intersections
      no single-dimension sweep covers. The arithmetic disposes: same
      calibration test, same false-discovery bar, re-earned against the growing
      journal on every settle pass.</span></div>
    <div class="stats">
      <div class="tile"><div class="k">Confirmed</div><div class="v">${n_of("confirmed")}</div>
        <div class="tile-sub">survived the tribunal — so far</div></div>
      <div class="tile"><div class="k">Rejected</div><div class="v">${n_of("rejected")}</div>
        <div class="tile-sub">a published result, not a failure</div></div>
      <div class="tile"><div class="k">Collecting</div><div class="v">${n_of("collecting")}</div>
        <div class="tile-sub">under the ${hl.min_n ?? 40}-bet floor</div></div>
      <div class="tile"><div class="k">Vetoing</div><div class="v">${hyps.filter((h) => h.action === "close").length}</div>
        <div class="tile-sub">confirmed hot — blocking new picks</div></div>
    </div>
    <div class="card" style="padding:0">${rows || empty}${watch}</div>
    ${recDisclosure("Why the AI only proposes", `
      <p style="margin:0;font-size:.87em">The recorded rule stands: a language
      model never sets a probability, because it cannot be re-run, swept, or
      audited. Its one structural advantage is hypothesis generation — the
      miner tests every single dimension of the record but never their
      intersections, and a model that has read the summary can name the few
      worth testing. So proposals are constrained to the miner's own menu of
      dimensions, convicted or acquitted by the same statistics that govern
      every number on this page, and re-tried nightly as new bets settle —
      a confirmation that was luck decays on its own. The model saw the record
      before proposing, which is exactly why first confirmations are treated
      as provisional and re-earned forever after.</p>`)}`;
}

function recCalibrationSection(cal, era) {
  if (!cal || !cal.n || !(cal.buckets || []).length) return "";
  const rows = calBucketRows(cal.buckets);
  const brier = calScoreBlock(cal);
  const diagram = reliabilityDiagram(cal.buckets);
  const diagramBlock = !diagram ? "" : `
    <div style="padding:14px 14px 4px;border-top:1px solid rgba(255,255,255,.06)">
      ${diagram}
      <p style="margin:8px auto 10px;max-width:420px;font-size:.83em;opacity:.6;text-align:center">
        Each dot is one probability bucket; its area is how many bets sit in it, and
        the whisker is the same sample-size band as the rows above. On the dashed
        line means the number meant what it said. Below it we ran hot, above it we
        ran cold, and a line that crosses is two different problems wearing one
        average.</p>
    </div>`;
  // Era scoping: the all-time chart is dominated by picks from RETIRED
  // gates. Until the current model has a real sample, say so; after ~50
  // graded, give it its own chart.
  const eraN = (era || {}).n || 0;
  const eraNote = eraN >= 50 ? "" : `
    <p style="padding:10px 14px;margin:0;font-size:.85em;color:var(--text-mute);
              border-top:1px solid rgba(255,255,255,.06)">
      Era note: ${cal.n - eraN} of these ${cal.n} graded picks predate the model re-tune${
      (era || {}).since ? ` (${escapeHtml(era.since)})` : ""} — the misses above were mostly
      earned by gates that no longer exist. The current model gets its own chart here once
      ~50 of its picks settle (${eraN} so far). The nightly calibration refit already feeds
      these misses back into the model's tempering.</p>`;
  const eraBlock = eraN >= 50 ? `
    <div class="section-title">Current model only
      <span class="sub">— the same test, restricted to picks graded since the
      ${escapeHtml((era || {}).since || "")} re-tune (n=${eraN}).</span></div>
    <div class="card" style="padding:0">${calBucketRows(era.buckets)}
      <div style="padding:14px 14px 4px;border-top:1px solid rgba(255,255,255,.06)">
        ${reliabilityDiagram(era.buckets)}</div>${calScoreBlock(era)}</div>` : "";
  return `<div class="section-title">Calibration — did "60%" mean 60%?
      <span class="sub">— every settled pick, bucketed by the model's claimed probability.</span></div>
    <div class="card" style="padding:0">${rows}${diagramBlock}${brier}${eraNote}</div>
    ${eraBlock}`;
}

/* Account health: how sharp our own journaled action looks per book —
   inference from our patterns, clearly labeled as such. */
function recHealthSection(h) {
  if (!h || !(h.books || []).length) return "";
  const bandColor = { low: "var(--good)", moderate: "var(--warn)", elevated: "var(--bad)" };
  const cards = h.books.map((b) => `
    <div class="card" style="padding:14px 16px">
      <div style="display:flex;align-items:center;gap:10px">
        <strong style="flex:1">${escapeHtml(b.book)}</strong>
        <span style="font-weight:800;color:${bandColor[b.band] || "var(--brand)"}">${b.score}</span>
        <span class="chip" style="color:${bandColor[b.band] || "var(--brand)"}">${b.band} limit risk</span>
      </div>
      <div style="font-size:.85em;color:var(--text-mute);margin-top:6px">
        ${b.bets} graded bets · beats the close ${b.beat_close_rate == null ? "—" : (b.beat_close_rate * 100).toFixed(0) + "%"}
        · ${(b.concentration * 100).toFixed(0)}% in ${escapeHtml(b.top_market)}${
        b.prop_share == null ? "" : ` · ${(b.prop_share * 100).toFixed(0)}% props`}</div>
      ${(b.drivers || []).length ? `<ul style="margin:8px 0 0;padding-left:18px;font-size:.85em;color:var(--text-body)">
        ${b.drivers.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}
      ${(b.actions || []).length ? `<div style="margin-top:8px;font-size:.85em">
        <span style="color:var(--brand);font-weight:700">To stay welcome:</span>
        <ul style="margin:4px 0 0;padding-left:18px;color:var(--text-body)">
        ${b.actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
    </div>`).join("");
  // What the score CANNOT see, shipped beside it. A number built from four
  // of the seven signals a risk desk uses will be over-trusted by anyone who
  // can't tell which four — and one of the omissions is a decision rather
  // than a limitation, which is worth saying out loud.
  const blind = !(h.blind_spots || []).length ? "" : `
    <details style="margin-top:10px">
      <summary style="cursor:pointer;font-size:.85em;color:var(--text-mute)">
        What this score can't see — and why</summary>
      <ul style="margin:8px 0 0;padding-left:18px;font-size:.85em;color:var(--text-body)">
        ${h.blind_spots.map((s) => `<li><strong>${escapeHtml(s.signal)}</strong>
          — ${escapeHtml(s.why)}</li>`).join("")}
      </ul>
      <p style="font-size:.83em;opacity:.6;margin:8px 0 0">Books watch all of
        these. We score the four we can measure honestly and name the rest
        rather than implying a completeness this doesn't have.</p>
    </details>`;
  return `<div class="section-title">Account health
      <span class="sub">— books quietly limit winners; this estimates how limit-prone your action looks, per book.</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px">${cards}</div>
    <p style="opacity:.55;font-size:.82em;margin-top:8px">${escapeHtml(h.disclaimer || "")}</p>
    ${blind}`;
}

/* UFC record — journaled fight picks in their own probation bucket,
   graded from post-card results. */
function recUfcSection(u) {
  if (!u || (!u.settled && !u.open)) return "";
  const graded = (u.wins || 0) + (u.losses || 0);
  const rows = (u.recent || []).map((b) => {
    const won = b.status === "won";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${won ? "won" : "lost"}">
      <span class="rl-icon">${won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">moneyline</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `model ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">UFC — tracked separately
      <span class="sub">— every journaled fight pick, graded from post-card results.
      Never mixed into the record above.</span></div>
    ${recDisclosure("Why these are quarantined", `Scalpy MMA's picks journal at
      their real prices (one-fifth Kelly stakes) and settle automatically from ESPN's
      fight results after each card. UFC is the newest graded module, so it earns its
      way like every other signal: its own bucket, its own ROI, and no place in the
      headline record until a real sample says it belongs there.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", ((u.roi || 0) >= 0 ? "+" : "") + ((u.roi || 0) * 100).toFixed(1) + "%",
                `${(u.net_units || 0) >= 0 ? "+" : ""}${(u.net_units || 0).toFixed(2)}u on ${(u.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(u.roi || 0) })}
      ${recTile("UFC record", `${u.wins || 0}-${u.losses || 0}`, `${u.open || 0} open`)}
      ${recTile("Hit rate", graded ? ((u.wins / graded) * 100).toFixed(1) + "%" : "—",
                "cards are small samples — judge after 50+")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${rows ||
      `<p class="loading" style="padding:12px">Grades after each card's fights are official.</p>`}</div>`;
}

/* Polymarket flag record — the Intel page's graded flags, quarantined in
   their own bucket exactly like Long Shots: paper-tracked observations,
   never mixed into the headline record. */
/* The looser-gates sampler — the standing "should the filters be looser?"
   question, answered by its own paper-tracked record instead of a debate. */
function recLooseSection(lo) {
  if (!lo || (!lo.settled && !lo.open)) return "";
  const graded = (lo.wins || 0) + (lo.losses || 0);
  const rows = (lo.recent || []).map((b) => {
    const won = b.status === "won";
    const push = b.status === "push";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">${escapeHtml(b.side || "")} ${b.line ?? ""} ${escapeHtml(b.market)}</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `model ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">Looser-gates sampler — measurement in progress
      <span class="sub">— the props that JUST missed the bar, paper-tracked nightly.
      This bucket IS the answer to "should we loosen the filters?"</span></div>
    ${recDisclosure("How this decides anything", `Every build journals the
      near-misses — real-priced Tier 1/2 props within reach of the edge bar or a
      quality grade in the 60s — at a flat 0.1u with zero bankroll impact. If this
      bucket is PROFITABLE after 100+ graded, the real gates loosen and those props
      become picks. If it burns, the gates were right and the argument is over.
      Same promotion bar as every other probation signal on this page.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", graded ? (lo.roi >= 0 ? "+" : "") + (lo.roi * 100).toFixed(1) + "%" : "—",
                `${(lo.net_units || 0) >= 0 ? "+" : ""}${(lo.net_units || 0).toFixed(2)}u on ${(lo.units_staked || 0).toFixed(1)}u`,
                { lead: true, tone: toneOf(lo.roi || 0) })}
      ${recTile("Record", `${lo.wins || 0}-${lo.losses || 0}`, `${lo.open || 0} open`)}
      ${recTile("Toward the bar", `${graded}/100`,
                graded >= 100 ? "sample reached — read the ROI" : "graded picks needed")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${rows ||
      `<p class="loading" style="padding:12px">Nothing settled yet — accrues from tonight's near-misses.</p>`}</div>`;
}

function recPolymarketSection(v) {
  if (!v || !v.graded) return "";
  const pctv = (x) => `${(x * 100).toFixed(1)}%`;
  const rows = (v.recent || []).map((b) => `
    <div class="rl-row ${b.won ? "won" : "lost"}">
      <span class="rl-icon">${b.won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.resolved || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.side)} ${escapeHtml(b.outcome)}</strong>
        <span class="rl-bet">${escapeHtml(b.market)}</span></span>
      <span class="rl-proc" title="${escapeHtml(traderLabel(b))}">score ${b.score} · ${escapeHtml(traderLabel(b))}</span>
      <span class="rl-odds">${b.price != null ? (b.price * 100).toFixed(0) + "¢" : ""}</span>
      <span class="rl-pnl ${toneOf(b.roi)}">${b.roi >= 0 ? "+" : ""}${(b.roi * 100).toFixed(0)}%</span>
    </div>`).join("");
  return `
    <div class="section-title">Polymarket flags — tracked separately
      <span class="sub">— every informed-flow flag, graded when its market resolves.
      Paper-tracked, never mixed into the record above.</span></div>
    ${recDisclosure("Why these are quarantined", `The Polymarket page flags large
      anomalous trades and paper-tracks whether following that money wins. These are
      OBSERVATIONS graded at a flat nominal stake with zero bankroll impact — the fixed
      promotion bar (100+ graded, z ≥ 2, positive ROI) decides if they ever become
      recommendations. The verdict box on the Polymarket page always states the current
      answer.`)}
    <div class="stats rec-kpis">
      ${recTile("Flag record", `${v.wins}-${v.graded - v.wins}`,
                `${v.open || 0} open · ${v.graded} graded`)}
      ${recTile("Hit rate", pctv(v.hit_rate), `entry prices implied ${pctv(v.avg_implied)}`)}
      ${recTile("Flat-stake ROI", (v.roi >= 0 ? "+" : "") + pctv(v.roi),
                "if every flag were $1", { tone: toneOf(v.roi) })}
      ${recTile("Calibration z", String(v.z),
                v.z >= 2 ? "beating its prices" : "not yet distinguishable from price",
                { tone: v.z >= 2 ? "pos" : "" })}
    </div>
    <div class="card pm-rows" style="padding:0;margin-top:12px">${rows ||
      `<p class="loading" style="padding:12px">Flags settle as their markets resolve.</p>`}</div>`;
}

/* Which record you are looking at. The combined page answers "is the
   system making money", which is the owner's question. A per-sport page
   answers "is THIS model any good", which is what the next change to it
   depends on — and the aggregate actively hides it: a baseball model
   reading four points hot and a football model four points cold average
   to a perfect calibration line nobody should trust. */
let _recordScope = null;          // null = follow the sport you are on

function recordScopeHTML(d, scope) {
  const tracked = d.tracked_sports || [];
  const btn = (key, label, n) => `<button class="rec-scope${
    scope === key ? " active" : ""}" data-scope="${escapeHtml(key)}">${
    escapeHtml(label)}${n != null ? ` <span class="rec-scope-n">${n}</span>` : ""}</button>`;
  const parts = [btn("all", "All bets", (d.overall || {}).settled)];
  parts.push(btn("intel", "Polymarket", null));
  for (const sp of tracked) {
    const r = (d.by_sport || {})[sp] || {};
    const settled = (r.overall || {}).settled || 0;
    const open = (r.overall || {}).open || 0;
    // A sport with nothing journaled is still listed. Hiding it would
    // make "no bets yet" and "no such board" look identical.
    parts.push(btn(sp, (SPORT_META[sp] || {}).name || sp.toUpperCase(),
                   settled || open || 0));
  }
  return `<div class="rec-scopes">${parts.join("")}</div>`;
}

function bindRecordScopes(host) {
  host.querySelectorAll(".rec-scope").forEach((b) =>
    b.addEventListener("click", () => {
      _recordScope = b.dataset.scope;
      renderRecord();
    }));
}

/* §9 — the standing record line under the masthead.

   "Every tout site hides this; doing the opposite is the positioning." So
   it reads from the SAME journal the Record page reads (loadRecordOnce) —
   two renderings of one number can drift, and a masthead that disagrees
   with the Record page would be worse than no masthead line at all.

   It is deliberately quiet type in a loud position. A figure that shouts on
   a good night shouts on a bad one, and the claim being made is that this
   one is always there, not that it is good. */
async function renderStandingRecord() {
  const el = document.getElementById("standing-record");
  if (!el) return;
  let rec;
  try {
    rec = await loadRecordOnce();
  } catch (e) {
    return;                       // no journal yet: the line stays absent
  }
  const o = (rec && rec.overall) || {};
  if (!o.settled) {
    // Nothing graded yet. Say so rather than printing 0.0% — a zero here
    // reads as "we broke even", which is a claim, and this has none to make.
    el.innerHTML = `<span class="lbl">Record</span>
      <span>no settled picks yet — every pick is journaled at its real book
      price and graded here</span>`;
    return;
  }
  const roi = o.roi || 0;
  const neg = roi < 0;
  el.innerHTML = `
    <span class="lbl">Running ROI</span>
    <b class="${neg ? "neg" : ""}">${roi >= 0 ? "+" : ""}${(roi * 100).toFixed(1)}%</b>
    <span>${(o.net_units >= 0 ? "+" : "")}${(o.net_units || 0).toFixed(2)}u on
      ${(o.units_staked || 0).toFixed(1)}u staked</span>
    <span class="lbl">Record</span>
    <b class="${neg ? "neg" : ""}">${o.wins || 0}-${o.losses || 0}-${o.pushes || 0}</b>
    <span>${o.settled} settled${o.open ? ` · ${o.open} open` : ""}</span>
    <span>Every pick journaled at its real book price and graded in public.</span>`;
}

/* The Lab — the walk-forward backtests, published.

   The Book grades what we actually bet, going forward. This grades the
   MODEL, replayed over stored history, which is the only evidence that
   accrues faster than the forward sample. Two things it must never let
   the reader believe:

   1. That a big ROI against NAIVE baseline lines means we beat a book.
      It means the model beats a trailing average — a different and much
      weaker claim — so basis is stated on every row and a naive ROI is
      rendered muted with the caveat attached.
   2. That a good Brier is good. Brier has no natural scale; the bar is
      what you'd score predicting the base rate every time. Skill (vs
      that bar) leads, and hedging — forecasts huddling near the base
      rate — is called out, because a model that answers "about 50%" to
      everything is perfectly calibrated and perfectly useless. */
/* Under this many backtest bets, ROI is noise wearing a percentage. The
   harnesses say it in their own summaries ("ROI — last, and meaningless
   under ~100 bets"); the page has to say it too, or the one number
   everybody reads first is the one least entitled to be believed. */
const LAB_ROI_MIN_BETS = 100;

function labSkillTile(m) {
  const sk = m.skill;
  if (!sk) return recTile("Skill vs guessing", "—",
    `needs 100+ graded forecasts (have ${m.n})`);
  const beats = sk.skill > 0;
  return recTile("Skill vs guessing",
    `${sk.skill >= 0 ? "+" : ""}${(sk.skill * 100).toFixed(1)}%`,
    `vs always saying ${(sk.base_rate * 100).toFixed(0)}% (the base rate)`,
    { lead: true, tone: beats ? "pos" : "neg",
      help: "Brier scored against the base-rate baseline. Positive = the "
          + "model's probabilities carry information; negative = you would "
          + "do better ignoring it." });
}

function labBins(m) {
  const bins = (m.bins || []).filter((b) => b.n);
  if (!bins.length) return "";
  const rows = bins.map((b) => {
    const gap = b.hit_rate - b.mean_pred;
    const w = Math.min(100, Math.abs(gap) * 300);
    return `<tr>
      <td>${(b.lo * 100).toFixed(0)}–${(b.hi * 100).toFixed(0)}%</td>
      <td class="num">${(b.mean_pred * 100).toFixed(0)}%</td>
      <td class="num">${(b.hit_rate * 100).toFixed(0)}%</td>
      <td class="num ${gap >= 0 ? "pos" : "neg"}">${gap >= 0 ? "+" : ""}${(gap * 100).toFixed(0)}</td>
      <td><span class="lab-bar ${gap >= 0 ? "pos" : "neg"}" style="width:${w}%"></span></td>
      <td class="num">${b.n.toLocaleString()}</td></tr>`;
  }).join("");
  return `<table class="agate lab-bins">
    <thead><tr><th>Said</th><th class="num">Predicted</th><th class="num">Actual</th>
      <th class="num">Gap</th><th></th><th class="num">n</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function labPropCard(m, note) {
  const naive = m.basis === "naive";
  const sk = m.skill;
  const hedged = sk && sk.hedged > 0.5;
  // A backtest ROI under ~100 bets is noise wearing a percentage — the
  // harnesses say so in their own summaries, so the page must not render
  // it as a result. Below the bar it goes grey and says why.
  const thin = m.n_bets < LAB_ROI_MIN_BETS;
  // ROI is shown, but a naive-basis ROI is explicitly NOT an edge claim.
  const roiSub = thin
    ? `only ${m.n_bets} bets — under ${LAB_ROI_MIN_BETS} this is noise, not a result`
    : m.basis === "book"
      ? "priced against real harvested closes — market-relative"
      : m.basis === "mixed"
        ? `${m.used_real_lines.toLocaleString()} of ${m.total_priced.toLocaleString()} on real closes`
        : "vs a naive baseline line — NOT an edge over a book";
  const seg = Object.entries(m.segments || {}).map(([basis, g]) =>
    `<tr><td>${basis === "book" ? "vs real book lines" : "vs naive baseline"}</td>
      <td class="num">${g.n_bets}</td><td class="num">${g.wins}</td>
      <td class="num">${g.win_rate != null ? (g.win_rate * 100).toFixed(1) + "%" : "—"}</td>
      <td class="num ${toneOf(g.roi)}">${g.roi >= 0 ? "+" : ""}${(g.roi * 100).toFixed(1)}%</td>
      <td class="num ${toneOf(g.net)}">${g.net >= 0 ? "+" : ""}${g.net.toFixed(2)}u</td></tr>`).join("");
  return `<div class="card lab-card">
    <div class="lab-head"><strong>${escapeHtml(m.label)}</strong>
      <span class="chip ${naive ? "warn" : "good"}">${naive ? "naive lines" : m.basis === "mixed" ? "mixed basis" : "real closes"}</span>
      <span class="mini">${m.n.toLocaleString()} settled props</span></div>
    <div class="stats rec-kpis">
      ${labSkillTile(m)}
      ${recTile("Projection error", m.mae != null ? m.mae.toFixed(2) : "—",
                "mean absolute, in stat units")}
      ${recTile("Calibration", m.ece != null ? (m.ece * 100).toFixed(1) + "%" : "—",
                `Brier ${m.brier != null ? m.brier.toFixed(4) : "—"}`,
                { help: "Average gap between what it said and what happened." })}
      ${recTile("Backtest ROI", m.n_bets ? `${m.roi >= 0 ? "+" : ""}${(m.roi * 100).toFixed(1)}%` : "—",
                m.n_bets ? roiSub : "no bets cleared the gates",
                { tone: (naive || thin) ? "" : toneOf(m.roi) })}
    </div>
    ${hedged ? `<div class="warning">${icon("warn")} ${(sk.hedged * 100).toFixed(0)}% of
      forecasts sit within 5 points of the base rate — that is hedging, not
      forecasting. A model that answers "about average" to everything scores
      well on calibration and finds no edges worth betting.</div>` : ""}
    ${naive && m.n_bets ? `<div class="warning">${icon("warn")} ${escapeHtml(note || "")}</div>` : ""}
    ${labBins(m)}
    ${seg ? `<table class="agate"><thead><tr><th>Priced against</th>
      <th class="num">Bets</th><th class="num">Won</th><th class="num">Win%</th>
      <th class="num">ROI</th><th class="num">Net</th></tr></thead>
      <tbody>${seg}</tbody></table>` : ""}
  </div>`;
}

function labGameTable(games) {
  const rows = (games.markets || []).map((g) => `<tr>
    <td>${escapeHtml(g.market)}</td>
    <td class="num">${g.games_priced.toLocaleString()}</td>
    <td class="num">${g.mae != null ? g.mae.toFixed(2) : "—"}</td>
    <td class="num">${g.n_bets}</td>
    <td class="num">${g.win_rate != null ? (g.win_rate * 100).toFixed(1) + "%" : "—"}</td>
    <td class="num ${toneOf(g.roi)}">${g.roi != null ? (g.roi >= 0 ? "+" : "") + (g.roi * 100).toFixed(1) + "%" : "—"}</td>
  </tr>`).join("");
  if (!rows) return `<p class="mini" style="padding:4px 0">${escapeHtml(games.unavailable || "")}</p>`;
  return `<table class="agate"><thead><tr><th>Market</th>
    <th class="num">Games priced</th><th class="num">MAE vs close</th>
    <th class="num">Bets</th><th class="num">Win%</th><th class="num">ROI</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

async function renderLab() {
  const host = document.getElementById("lab-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/backtest.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d || !d.sports) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <div class="es-title">No backtests published yet</div>
      <div class="es-sub">The Lab replays the production model over stored history
      once a week, automatically, as part of the nightly maintenance pass. It
      appears here after the first run — or immediately with
      <code>python3 backtest_lab.py --force</code>.</div></div>`;
    return;
  }
  const order = ["mlb", "nfl", "cfb", "nba", "wnba", "ufc"];
  const has = (sport) => {
    const s = d.sports[sport];
    return (s.props || {}).markets || ((s.game_lines || {}).markets);
  };
  const blocks = order.filter((s) => d.sports[s] && has(s)).map((sport) => {
    const s = d.sports[sport];
    const props = s.props || {}, games = s.game_lines || {};
    const cards = (props.markets || []).map((m) => labPropCard(m, d.basis_note)).join("");
    return `<div class="lab-sport">
      <div class="section-title">${sport.toUpperCase()}
        ${props.season ? `<span class="sub">— ${props.season} season</span>` : ""}</div>
      ${cards || `<p class="mini">Player props — ${escapeHtml(props.unavailable || "nothing replayed")}</p>`}
      <div class="mini" style="margin-top:10px;opacity:.75">Game lines (spread &amp; total),
        graded against real closing numbers</div>
      ${labGameTable(games)}
    </div>`;
  }).join("");
  /* Sports with nothing replayed collapse into one honest table instead
     of six near-empty sections. A gap stated once is information; a gap
     restated six times over is what buries the page that has data. */
  const gaps = order.filter((s) => d.sports[s] && !has(s)).map((sport) => {
    const s = d.sports[sport];
    return `<tr><td>${sport.toUpperCase()}</td>
      <td>${escapeHtml((s.props || {}).unavailable || "—")}</td>
      <td>${escapeHtml((s.game_lines || {}).unavailable || "—")}</td></tr>`;
  }).join("");
  const gapBlock = gaps ? `<div class="section-title">Not replayed yet
      <span class="sub">— what each of these needs before it can appear above</span></div>
    <table class="agate"><thead><tr><th>Sport</th><th>Player props</th>
      <th>Game lines</th></tr></thead><tbody>${gaps}</tbody></table>` : "";
  host.innerHTML = `
    ${recDisclosure("What this page is, and what it isn't", `The Book grades the picks
      we actually made, going forward. This page grades the <em>model</em>, by
      replaying it over history it never saw at the time — projections for each
      game are built only from games before it, then settled against what
      actually happened. That is the only evidence that accrues faster than a
      forward record, which is why it exists. It is also the easiest thing in
      betting to fool yourself with: ${escapeHtml(d.basis_note)}`)}
    ${blocks}
    ${gapBlock}
    <p class="mini" style="opacity:.6;margin-top:14px">Replayed automatically every
      ${d.every_days} days as part of the maintenance pass · last run
      ${escapeHtml((d.generated_at || "").replace("T", " "))}</p>`;
}

async function renderRecord() {
  const host = document.getElementById("record-body");
  if (!host) return;
  let d = null, pmv = null;
  try {
    const res = await fetch("data/record.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  try {
    const res = await fetch("data/predmarkets.json?t=" + Date.now());
    if (res.ok) pmv = ((await res.json()) || {}).validation;
  } catch (e) {}
  if (!d || !d.overall || (!d.overall.settled && !d.overall.open)) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("book", 30)}</div>
      <div class="es-title">No graded picks yet</div>
      <div class="es-sub">Every recommended pick is journaled automatically at its real
      price and grades itself once results are ingested (nightly, automatic).
      Check back after tonight's games settle — this page becomes the honest
      scoreboard for everything the model recommends.</div></div>`;
    return;
  }
  // Default to the sport whose board you came from; "all" is a click away.
  const tracked = d.tracked_sports || [];
  let scope = _recordScope
    || (tracked.includes(state.sport) ? state.sport : "all");
  if (scope !== "all" && scope !== "intel" && !(d.by_sport || {})[scope])
    scope = "all";
  const scoped = (scope === "all") ? null
    : (scope === "intel" ? {overall: {}, curve: [], recent: [],
                            calibration: null, calibration_era: null}
                         : d.by_sport[scope]);
  const scopeBar = recordScopeHTML(d, scope);

  // Everything below reads ONE object. Scoping by swapping the source
  // rather than by filtering at each call site means a panel cannot
  // quietly keep showing the combined number next to a per-sport one.
  const src = scoped || d;
  const o = src.overall;
  if (scope === "intel") {
    host.innerHTML = scopeBar + (pmv
      ? recPolymarketSection(pmv)
      : `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
         <div class="es-title">No Polymarket flags graded yet</div>
         <div class="es-sub">Flags are recorded as the trade tape is read and
         grade when their markets resolve. This is a report card on the
         detector, not a betting P&L — nothing here is staked.</div></div>`);
    bindRecordScopes(host);
    return;
  }
  if (scoped && !o.settled && !o.open) {
    // An empty journal is not an empty MODEL: the ladder can already be
    // fitted for this sport from walk-forward history (the NFL's dials
    // adopted before its first journaled bet). Show the learning below
    // the empty state instead of hiding it behind the journal.
    host.innerHTML = scopeBar + `<div class="empty-slate"><div class="es-icon">${icon("book", 30)}</div>
      <div class="es-title">Nothing journaled for ${escapeHtml(
        (SPORT_META[scope] || {}).name || scope.toUpperCase())} yet</div>
      <div class="es-sub">This board has not recommended a bet that reached a
      result. It fills itself in — every pick is journaled at its real price
      the moment it is made, and grades when the games settle.</div></div>`
      + recRestatedSection(d.restated, scope)
      + recProseSection(d.prose, scope)
      + recSelfTuningSection(d.self_tuning, scope)
      + recLossPatternsSection(d.loss_patterns, scope)
      + recHypothesisLab(d.hypothesis_lab, scope);
    bindRecordScopes(host);
    return;
  }
  const unstaked = o.unstaked
    ? `<p class="loading" style="margin-top:10px">${iconMark("dash")}${o.unstaked} older settled pick(s)
       are held out of this record: a grading bug sized them at 0.00 units, so they were
       never really bets. Run <code>python3 launch.py --resize-unstaked</code> to stake
       them at a flat 0.1u and fold the profit (or loss) they produced back in.</p>` : "";
  const small = o.settled < 100
    ? `<p class="loading" style="margin-top:10px">${icon('warn')} ${o.settled} settled pick(s)${
       scoped ? ` for ${escapeHtml((SPORT_META[scope] || {}).name || scope)}` : ""} —
       results this small are mostly luck. Judge the model after 100+, and judge
       the process by CLV before that.</p>` : "";
  const pr = o.process || {};
  const nProc = (pr.good || 0) + (pr.bad || 0) + (pr.flat || 0);
  host.innerHTML = scopeBar + `
    <div class="stats rec-kpis">
      ${recTile("ROI", (o.roi >= 0 ? "+" : "") + (o.roi * 100).toFixed(1) + "%",
                `${o.net_units >= 0 ? "+" : ""}${o.net_units.toFixed(2)}u on ${(o.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(o.roi) })}
      ${recTile("Avg CLV", o.avg_clv == null ? "—" : (o.avg_clv >= 0 ? "+" : "") + o.avg_clv.toFixed(2) + ' <span class="unit">pts</span>',
                o.avg_clv == null ? "accrues as daily closes are captured" : "beat the close = sharp process",
                { lead: true, tone: o.avg_clv == null ? "" : toneOf(o.avg_clv) })}
      ${recTile("Record", `${o.wins}-${o.losses}-${o.pushes}`, `${o.open} open · ${o.settled} settled`)}
      ${recTile("Win rate", (o.win_rate * 100).toFixed(1) + "%", "break-even ≈ 52.4% at −110")}
      ${recTile("Process", nProc ? `${pr.good || 0}${icon('check')} ${pr.bad || 0}${icon('cross')}` : "—",
                // The count is the point. This grades a bet against the
                // CLOSING line, so it can only speak for the picks where a
                // close was captured — which is a small slice. Without the
                // denominator the tile looks frozen ("still 4?") when it is
                // just quiet, and worse, looks like a verdict on the whole
                // record when it is a verdict on four bets.
                nProc ? `${nProc} of ${o.settled} priced at close · `
                        + `${pr.lucky_wins || 0} lucky win(s), `
                        + `${pr.unlucky_losses || 0} good-bet loss(es)`
                      : "needs closing lines — none captured yet",
                { help: "Grades the DECISION, not the result: a win that "
                        + "closed worse than we bet it got lucky; a loss that "
                        + "beat the close was still a good bet. Only counts "
                        + "picks where we captured the closing line." })}
    </div>
    ${recDisclosure("What counts as a tracked bet", `Journals every
      <strong>Recommended</strong> bet — the same count the "Recommended bets"
      tile shows on each sport's board: player props plus game bets (moneyline,
      spread &amp; totals, sharp-anchor and model alike) — at the real book price
      shown when it was recommended. One entry per player &amp; market per day.
      Long Shots and stale-line flags are tracked in their own buckets at a flat
      0.1u — never mixed into this record — and the Edge Board is a watchlist,
      not tracked bets.`)}
    ${unstaked}
    ${small}
    ${recCurveChart(src.curve)}
    <div class="section-title">Splits
      <span class="sub">— where the units actually came from. The bar is win rate;
      the number that matters is net.</span></div>
    <div class="rec-buckets">
      ${recBucketTable("By market", o.by_market)}
      ${recBucketTable("By side", o.by_side)}
      ${recBucketTable("By grade", o.by_grade)}
      ${recBucketTable("By book", o.by_book)}
    </div>
    <div class="section-title">Recent settled picks
      <span class="sub">— newest first, at the price we actually got</span></div>
    <div class="card rec-list">
      ${(src.recent || []).map((b) => {
        const won = b.status === "won";
        const push = b.status === "push";
        const pnl = b.pnl_units || 0;
        // Process chip: judge the decision against the close, out loud.
        let procChip = `<span class="rl-proc none">no close</span>`;
        if (b.process === "bad" && won)
          procChip = `<span class="rl-proc warn" title="Won, but the market closed against us — a bad bet that got lucky">${iconMark("dot", 10)}lucky</span>`;
        else if (b.process === "good" && b.status === "lost")
          procChip = `<span class="rl-proc good" title="Lost, but we beat the closing line — good bet, bad night">${iconMark("rising", 11)}beat close</span>`;
        else if (b.clv != null)
          procChip = `<span class="rl-proc ${b.clv >= 0 ? "good" : "bad"}"
            title="Closing-line value — how far the market moved our way after the bet">${b.clv >= 0 ? "+" : ""}${b.clv.toFixed(1)} CLV</span>`;
        // Cause chip: the settle pass's measured circumstance on a loss.
        // Only the exceptional ones get a chip — "variance" is the story
        // a lost row already tells by itself.
        const causeChip = (b.status === "lost" && b.cause && !/^variance/.test(b.cause))
          ? `<span class="rl-proc warn" title="Measured at settle from the ingested results — the circumstance, not an excuse">${escapeHtml(b.cause)}</span>`
          : "";
        return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
          <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
          <span class="rl-date">${escapeHtml(b.date || "")}</span>
          <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
            <span class="rl-bet">${escapeHtml(b.side || "")} ${b.line ?? ""} ${escapeHtml(b.market)}</span></span>
          ${procChip}${causeChip}
          <span class="rl-odds">${american(b.odds)}</span>
          <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
        </div>`;
      }).join("") || `<p class="loading" style="padding:12px">Nothing settled yet.</p>`}
    </div>
    ${/* The samplers and account health are whole-journal by nature —
          a per-book limit risk and a cross-sport promotion bar are not
          per-sport questions — so they only appear on the combined view
          rather than repeating an unscoped number under a sport's name. */
      scoped ? "" : recEraSection(d.model_eras)}
    ${recCalibrationSection(src.calibration, src.calibration_era)}
    ${scoped ? "" : recCalibrationSplits(d.calibration_splits)}
    ${/* The learning ladder renders on EVERY scope, filtered to the
          sport being viewed — each league fits on its own bets, so each
          league's page shows its own learning. Hiding these behind "All"
          is how the whole ladder shipped invisible: the record page
          always lands sport-scoped. */""}
    ${recRestatedSection(d.restated, scoped ? scope : null)}
    ${recProseSection(d.prose, scoped ? scope : null)}
    ${recSelfTuningSection(d.self_tuning, scoped ? scope : null)}
    ${recLossPatternsSection(d.loss_patterns, scoped ? scope : null)}
    ${recHypothesisLab(d.hypothesis_lab, scoped ? scope : null)}
    ${scoped ? "" : recForecastLog(d.forecast_log)}
    ${scoped ? "" : recHealthSection(d.account_health)}
    ${scoped ? "" : recLongshotSection(d.longshots)}
    ${scoped ? "" : recParlaySection(d.parlays)}
    ${scoped ? "" : recStaleSection(d.stale_flags)}
    ${scoped ? "" : recFormSection(d.form_sampler)}
    ${scoped ? "" : recLooseSection(d.loose_sampler)}
    ${scoped && scope !== "ufc" ? "" : recUfcSection(d.ufc_record)}
    ${/* Polymarket's flags are not wagers in this ledger — they are graded
          by their own report card in predmarkets.json. Folding a flag rate
          into a betting P&L would make both numbers mean nothing, so it
          gets its own scope rather than a row in the table. */
      scoped && scope !== "intel" ? "" : recPolymarketSection(pmv)}
    <p class="rec-stamp">Updated ${escapeHtml(d.generated_at || "")}
      · settles automatically as results are ingested each day.</p>`;
  bindRecordScopes(host);
}

/* The stale-line sampler: every pre-game scanner flag, journaled at a flat
   nominal stake and settled like any bet. The signal's CLV was measured on
   30k harvested quotes; this bucket measures whether TAKING the flagged
   price actually cashes — the difference between a statistic and a bet. */
/* Team-form sampler — does backing HOT teams at real prices make money?
   Same quarantine pattern as the stale sampler. */
function recFormSection(fm) {
  if (!fm || (!fm.settled && !fm.open)) return "";
  const graded = fm.wins + fm.losses;
  const hitRate = graded ? (fm.wins / graded) * 100 : 0;
  const rows = (fm.recent || []).map((b) => {
    const won = b.status === "won";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${won ? "won" : "lost"}">
      <span class="rl-icon">${won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(teamName(b.player))}</strong>
        <span class="rl-bet">hot-team moneyline</span></span>
      <span class="rl-proc">form gap ${b.edge != null ? Number(b.edge).toFixed(2) : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">Team-form sampler — measurement in progress
      <span class="sub">— every hot-vs-cold matchup, hot side's moneyline at the real book
      price. Flat 0.1u, zero bankroll impact, never in the record above.</span></div>
    ${recDisclosure("What this is testing", `Streaks are the most public stat in
      sports, so the default assumption is the market already prices them — hot teams
      cost more to back. This bucket journals the hot team's moneyline in every
      hot-vs-cold matchup at the price someone could actually bet, and settles it
      against the real result. The promotion bar is the same as every sampler:
      100+ graded, z ≥ 2, positive ROI. Clear it and form becomes a model input;
      miss it and we've learned the market has streaks covered — cheaply.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", (fm.roi >= 0 ? "+" : "") + (fm.roi * 100).toFixed(1) + "%",
                `${fm.net_units >= 0 ? "+" : ""}${(fm.net_units || 0).toFixed(2)}u on ${(fm.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(fm.roi) })}
      ${recTile("Sampler record", `${fm.wins}-${fm.losses}`, `${fm.open} open`)}
      ${recTile("Hit rate", graded ? hitRate.toFixed(1) + "%" : "—",
                fm.avg_taken_implied != null
                  ? `needs ${(fm.avg_taken_implied * 100).toFixed(1)}% to break even`
                  : "accrues as games settle")}
      ${recTile("Avg form gap", fm.avg_form_gap != null ? fm.avg_form_gap.toFixed(2) : "—",
                "hot-vs-cold score spread sampled")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${rows ||
      `<p class="loading" style="padding:12px">Fills as hot-vs-cold matchups settle.</p>`}</div>`;
}

function recStaleSection(st) {
  if (!st || (!st.settled && !st.open)) return "";
  const graded = st.wins + st.losses;
  const hitRate = graded ? (st.wins / graded) * 100 : 0;
  const calib = st.avg_taken_implied != null
    ? `<div style="opacity:.7;font-size:.9em;padding:8px 14px">
         The flagged prices implied <strong>${(st.avg_taken_implied * 100).toFixed(1)}%</strong>
         · the field's consensus said <strong>${(st.avg_consensus_implied * 100).toFixed(1)}%</strong>
         · they actually hit <strong>${(st.actual_hit_rate * 100).toFixed(1)}%</strong>.
         Hitting above the taken price's implied = the cheap price was real value.</div>` : "";
  const rows = (st.recent || []).map((b) => {
    const won = b.status === "won";
    const push = b.status === "push";
    const pnl = b.pnl_units || 0;
    return `<div class="rl-row ${push ? "push" : won ? "won" : "lost"}">
      <span class="rl-icon">${push ? icon('dash') : won ? icon('check') : icon('cross')}</span>
      <span class="rl-date">${escapeHtml(b.date || "")}</span>
      <span class="rl-main"><strong>${escapeHtml(b.player)}</strong>
        <span class="rl-bet">${escapeHtml(b.side || "")} ${b.line ?? ""} ${escapeHtml(b.market)}</span></span>
      <span class="rl-proc">${b.hit_prob != null ? `field said ${(b.hit_prob * 100).toFixed(0)}%` : ""}</span>
      <span class="rl-odds">${american(b.odds)}</span>
      <span class="rl-pnl ${toneOf(pnl)}">${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}u</span>
    </div>`;
  }).join("");
  return `
    <div class="section-title">Stale-line sampler — measurement in progress
      <span class="sub">— every pre-game stale-line flag, taken at the flagged price. Flat 0.1u,
      zero bankroll impact, never in the record above.</span></div>
    ${recDisclosure("What this is testing", `The scanner flags a book pricing
      a side at least a point cheaper than every other book's consensus. On 30,448
      harvested quotes, taking that price beat the eventual close 64.8% of the time —
      but closing-line value is a statistic, not money. This bucket journals every
      pre-game flag automatically and settles it against the real result. If the hit
      rate clears the taken price's break-even over a real sample, the signal graduates
      from "interesting" to "bettable" — and if it doesn't, this table is how we find
      out cheaply.`)}
    <div class="stats rec-kpis">
      ${recTile("Flat-stake ROI", (st.roi >= 0 ? "+" : "") + (st.roi * 100).toFixed(1) + "%",
                `${st.net_units >= 0 ? "+" : ""}${(st.net_units || 0).toFixed(2)}u on ${(st.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(st.roi) })}
      ${recTile("Sampler record", `${st.wins}-${st.losses}${st.pushes ? "-" + st.pushes : ""}`,
                `${st.open} open`)}
      ${recTile("Hit rate", graded ? hitRate.toFixed(1) + "%" : "—",
                st.avg_taken_implied != null
                  ? `needs ${(st.avg_taken_implied * 100).toFixed(1)}% to break even`
                  : "accrues as flags settle")}
      ${recTile("Avg gap", st.avg_gap_pts != null ? st.avg_gap_pts.toFixed(1) + " pts" : "—",
                "flagged price vs field consensus")}
    </div>
    <div class="card" style="padding:0;margin-top:12px">${calib}${rows ||
      `<p class="loading" style="padding:12px">Nothing settled yet — flags journal on every
       paid pull and grade as results ingest.</p>`}</div>`;
}

/* Long explanatory prose is the right thing to have and the wrong thing to
   lead with — same progressive-disclosure pattern the section subtitles use.
   Open by default is wrong here: the numbers above it are the page. */
function recDisclosure(label, html) {
  return `<details class="rec-disclose"><summary>${escapeHtml(label)}</summary>
    <div>${html}</div></details>`;
}

/* ============================================================
   Odds status — say exactly why no real prices are attached
   ============================================================ */
function noMarketExplainer() {
  const os = state.data.odds_status;
  if (os && os.error)
    return `Odds feed problem on the last pull (${os.at || ""}): ${os.error} —
            the model keeps proxy lines and recommends nothing until real
            prices return.`;
  if (os && os.checked === false)
    return `The last refresh skipped the odds pull (budget pacing). Real
            prices attach on an upcoming cycle — no action needed.`;
  if (os && os.checked && os.matched === 0)
    return `The odds feed answered at ${os.at || "last refresh"} but had no
            player-prop prices yet (checked ${os.events} game(s)) — books post
            MLB props closer to first pitch. The board fills automatically as
            real prices arrive.`;
  return `Waiting on real sportsbook prices — picks are never recommended
          against placeholder lines. The board fills automatically as real
          prices arrive.`;
}

/* ============================================================
   Edge Board — every positively-priced bet, banded by odds
   ============================================================ */
const EDGE_BANDS = [
  ["Favorites (−105 and shorter)", (o) => o <= -105],
  ["Near even (−104 to +150)", (o) => o > -105 && o <= 150],
  ["Long odds (+151 and up)", (o) => o > 150],
];

function edgeBoardRows() {
  const props = (state.data.recommendations || [])
    .filter((r) => r.has_market !== false && (r.ev_per_unit || 0) > 0.005
                   && r.odds >= state.maxJuice)
    .map((r) => ({
      label: `${r.player} · ${r.side} ${r.line} ${r.market_label}`,
      sub: `${r.book || ""} · ${teamName(r.team)} vs ${teamName(r.opponent)}`,
      odds: r.odds, model: r.hit_prob, implied: r.fair_prob,
      // The check means "on the Recommended page RIGHT NOW", so it must apply the
      // user's sliders — the build-time flag can disagree with them.
      ev: r.ev_per_unit, grade: r.grade, rec: passesFilters(r),
    }));
  const games = (state.data.game_bets || [])
    .filter((b) => b.grade !== "Pass" && (b.ev_per_unit || 0) > 0.005)
    .map((b) => ({
      label: b.pick_label, sub: `${b.matchup} · ${b.market_label}`,
      odds: b.odds, model: b.win_prob, implied: b.fair_prob,
      ev: b.ev_per_unit, grade: b.grade, rec: passesGameBet(b),
    }));
  return [...props, ...games].sort((a, b) => b.ev - a.ev);
}

function edgeRowHTML(r, i) {
  const evPct = (r.ev * 100).toFixed(1);
  return `<div class="ls-row drow" style="display:flex;align-items:center;gap:14px;
       padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
    <span style="opacity:.5;min-width:20px">${i + 1}</span>
    <span style="flex:1"><strong>${escapeHtml(r.label)}</strong>
      <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(r.sub)}</span></span>
    <span style="min-width:64px;text-align:right">${r.odds > 0 ? "+" : ""}${r.odds}</span>
    <span style="min-width:120px;text-align:right;opacity:.8">
      ${(r.model * 100).toFixed(0)}% vs ${(r.implied * 100).toFixed(0)}%</span>
    <span style="min-width:70px;text-align:right;color:var(--green,#3ddc84)">
      +${evPct}% EV</span>
    <span style="min-width:86px;text-align:right;opacity:.75">${r.rec ? `${icon('check')} ` : ""}${escapeHtml(r.grade || "")}</span>
  </div>`;
}

function renderEdgeBoard() {
  const host = document.getElementById("edge-board");
  const note = document.getElementById("edge-note");
  if (!host) return;
  const rows = edgeBoardRows();
  if (!rows.length) {
    note.innerHTML = "";
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <h3>No positively-priced bets right now</h3>
      <p>${noMarketExplainer()}</p>
      <p style="opacity:.7">The Edge Board lists every bet whose real price
      beats the model's probability — including small edges and long odds that
      don't clear the Recommended bar. Expected value is honest math, not a
      guarantee: a +5% EV bet still loses often; the edge shows up over
      hundreds of bets.</p></div>`;
    return;
  }
  /* "18 positively-priced bets" sounds like a finding and is arithmetic. On
     a two-way market the de-vigged prices sum to 1, so the two sides' edges
     sum to exactly ZERO — one side is always non-negative, whatever the
     model thinks. A full board is the count of markets priced, not evidence
     of anything, and reading it as a haul is the single easiest way to talk
     yourself into a bad night. The checked count is the number that means
     something, so lead with it. */
  const plays = rows.filter((r) => r.rec).length;   // same flag the check uses
  note.innerHTML = `<b>${plays}</b> clear your current sliders · ${rows.length}
    market(s) priced against a real book number. One side of every two-way
    market always prices positive — the two sides' edges sum to zero by
    construction — so the length of this list is not a signal. Checked = a tracked
    bet; everything else is a watchlist.`;
  host.innerHTML = EDGE_BANDS.map(([title, test]) => {
    const band = rows.filter((r) => test(r.odds));
    if (!band.length) return "";
    return `<div class="section-title">${title}
        <span class="sub">— ${band.length} bet(s)</span></div>
      <div class="card" style="padding:0">${band.map(edgeRowHTML).join("")}</div>`;
  }).join("") || "";
}

/* ============================================================
   Market Scanner — arbitrage / middles / low holds / sharp money
   ============================================================ */
function scanPairRow(p, extra) {
  const leg = (side, l) =>
    `<span style="display:block"><strong>${side} ${l.line}</strong>
       <span style="opacity:.65">@ ${escapeHtml(l.book)} ${american(l.odds)}</span></span>`;
  return `<div class="drow" style="display:flex;align-items:center;gap:14px;padding:11px 16px;
      border-bottom:1px solid rgba(255,255,255,.05)">
    <span style="flex:1"><strong>${escapeHtml(p.bet)}</strong></span>
    <span style="min-width:170px">${leg("Over", p.over)}${leg("Under", p.under)}</span>
    <span style="min-width:150px;text-align:right">${extra}</span>
  </div>`;
}

function scanSection(title, sub, rows, rowFn, emptyText) {
  return `<div class="section-title">${title}
      <span class="sub">— ${sub}</span></div>
    <div class="card" style="padding:0">
      ${rows.length ? rows.map(rowFn).join("")
        : `<p class="loading" style="padding:12px">${emptyText}</p>`}
    </div>`;
}

function renderScanner() {
  const host = document.getElementById("scanner-body");
  if (!host) return;
  const scan = state.data.market_scan || {};
  const arbs = scan.arbs || [], middles = scan.middles || [], lows = scan.low_holds || [];

  // The scanner feeds on price DISAGREEMENT, which mostly appears when one
  // book moves before the others. On cached prices (one frozen frame per
  // budget pull) empty sections are the norm, not a bug — say so up front.
  const os = state.data.odds_status || {};
  const freshness = os.source === "cache"
    ? `<div class="ls-note">Prices are from the last budgeted pull (cached — no
       API spend). Arbs and middles come from catching books mid-move, so a
       single frozen snapshot rarely shows them; scanning sharpens when pulls
       resume normal frequency after the credit reset.</div>`
    : "";

  // Sharp money: anchor picks (priced off the sharp book's fair value) and
  // steam moves (several books re-pricing together = pro money footprint).
  const anchors = (state.data.game_bets || []).filter((b) =>
    (b.reasons || []).join(" ").toLowerCase().includes("sharp"));
  const steam = (state.data.recommendations || [])
    .filter((r) => r.line_move && r.line_move.steam)
    .map((r) => ({ r, m: r.line_move }));

  const stake = state.scanStake || 100;
  const stakeInput = `<div class="ls-note" style="display:flex;align-items:center;gap:8px">
    Total stake for the splits below: $
    <input id="scan-stake" type="number" min="10" step="10" value="${stake}"
      style="width:90px;background:transparent;color:inherit;border:1px solid rgba(255,255,255,.2);border-radius:var(--radius);padding:4px 8px" />
  </div>`;

  // With seven books on every prop, hundreds of quotes sit a point below
  // consensus. The board shows the biggest gaps and says how many exist.
  const staleNote = () => {
    const st = (state.data.market_scan && state.data.market_scan.stale) || [];
    const total = st.length ? (st[0].total_found || st.length) : 0;
    return total > st.length
      ? `showing the ${st.length} biggest gaps of ${total} found · ` : "";
  };

  const staleRow = (t) => `<div class="drow" style="display:flex;align-items:center;gap:14px;
      padding:11px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
    <span style="flex:1"><strong>${escapeHtml(t.bet)}</strong>
      <span style="display:block;opacity:.65;font-size:.85em">
        ${escapeHtml(t.book)} ${american(t.odds)} · the other
        ${t.books_compared - 1} book(s) average ${american(t.fair_odds)}</span></span>
    <span style="min-width:150px;text-align:right">
      <span style="color:var(--good);font-weight:700">${t.gap_pts.toFixed(2)} pts cheap</span>
      <span style="display:block;opacity:.6;font-size:.85em">
        ${(t.implied * 100).toFixed(1)}% vs field ${(t.consensus * 100).toFixed(1)}%</span></span>
  </div>`;

  host.innerHTML = freshness + stakeInput
    + scanSection("Stale lines",
      staleNote()
      + "a book pricing a side cheaper than every other book. No forecast involved — "
      + "measured on 30,448 harvested quotes, taking these beat the closing consensus "
      + "64.8% of the time for +1.49 points of CLV (z=11.6). Verify the price is still "
      + "up before betting; that is the whole game here",
      (state.data.market_scan && state.data.market_scan.stale) || [], staleRow,
      "No book is currently out of line with the field. This fills in as books "
      + "update at different speeds — most often right after lineups post.")
    + scanSection("Priced against you — plus-money props",
      "not a play, an avoidance rule. Measured on 27,226 settled quotes joined to real "
      + "results: backing plus-money props cost -16.7% per unit against -6.5% for short "
      + "prices — the books shade big payouts 2.6x harder. No forecast is involved and "
      + "none helps; this is what the PRICE costs before anyone has a view on the player",
      (state.data.market_scan && state.data.market_scan.longshots) || [],
      (t) => `<div class="drow" style="display:flex;align-items:center;gap:14px;padding:11px 16px;
          border-bottom:1px solid rgba(255,255,255,.05)">
        <span style="flex:1"><strong>${escapeHtml(t.bet)}</strong>
          <span style="display:block;opacity:.65;font-size:.85em">
            ${escapeHtml(t.book)} ${american(t.odds)} · implied ${(t.implied * 100).toFixed(1)}%
            ${t.grade ? ` · graded ${escapeHtml(t.grade)}` : ""}</span></span>
        <span style="min-width:170px;text-align:right">
          <span style="color:var(--bad);font-weight:700">${(t.measured_roi * 100).toFixed(1)}% historically</span>
          <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(t.band)} band</span></span>
      </div>`,
      "No plus-money quotes on today's board — main props or long shots. That's the cheap place to be.")
    + scanSection("Arbitrage", "opposite sides priced so a margin is locked whichever way it lands — IF both legs fill at the shown prices before they move. Rare across US books and gone in minutes",
      arbs, (a) => {
        const so = stake * a.stake_over_pct, su = stake * (1 - a.stake_over_pct);
        const ret = stake * a.profit_pct;
        const suspect = a.suspect
          ? `<span style="display:block;color:var(--warn,#e8b33e);font-size:.85em">${icon('warn')} 5%+ edge — likely a stale line or void risk; verify at both books</span>` : "";
        return scanPairRow(a,
          `<span style="color:var(--good,#3ddc84);font-weight:700">+${(a.profit_pct * 100).toFixed(2)}% · $${ret.toFixed(2)} locked</span>
           <span style="display:block;opacity:.7;font-size:.85em">$${so.toFixed(0)} Over / $${su.toFixed(0)} Under</span>${suspect}`);
      },
      "No arbitrage pairs right now. Real arbs across legal US books appear a few times a week and last minutes — this scanner checks every refresh.")
    + scanSection("Middles", "Over at a low line + Under at a higher one: land between them and BOTH win; miss and you only pay the vig. Ranked by EV from the sport's real outcome distribution — never by window width",
      middles, (m) => {
        const evLine = m.ev_per_unit != null
          ? `<span style="font-weight:700;color:${m.ev_per_unit >= 0 ? "var(--good,#3ddc84)" : "var(--text-mute,#889)"}">${m.ev_per_unit >= 0 ? "+" : ""}${(m.ev_per_unit * 100).toFixed(1)}% EV</span>
             <span style="display:block;opacity:.7;font-size:.85em">hits ${(m.middle_prob * 100).toFixed(0)}% of the time · both win +${(m.both_win_return * 100).toFixed(0)}% · worst ${(m.worst_case * 100).toFixed(0)}%</span>`
          : `<span style="font-weight:700">${m.gap} gap</span>
             <span style="display:block;opacity:.7;font-size:.85em">both win +${(m.both_win_return * 100).toFixed(0)}% · worst ${(m.worst_case * 100).toFixed(0)}%</span>`;
        return scanPairRow(m, evLine);
      },
      "No middle windows open — books currently agree on every line. Gaps open when one book moves before the others.")
    + scanSection("Low holds", "two-sided quotes under 2% combined juice — a turnover feature, not a profit feature: the cheapest way to churn promo/rollover volume or keep an account looking recreational",
      lows, (h) => scanPairRow(h,
        `<span style="font-weight:700">${(h.hold_pct * 100).toFixed(1)}% hold</span>
         <span style="display:block;opacity:.7;font-size:.85em">≈ $${(h.cost_per_1k != null ? h.cost_per_1k : h.hold_pct * 1000).toFixed(0)} per $1,000 bet through</span>`),
      "No low-hold pairs on the current board.")
    + `<div class="section-title">Sharp money
        <span class="sub">— where the professional side of the market is</span></div>
      <div class="card" style="padding:0">
        ${anchors.map((b) => `<div class="drow" style="display:flex;align-items:center;gap:14px;padding:11px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
            <span style="flex:1"><strong>${escapeHtml(b.pick_label || "")}</strong>
              <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(b.matchup || "")} · priced off the sharp book's fair value</span></span>
            <span style="min-width:64px;text-align:right">${american(b.odds)}</span>
            <span style="min-width:80px;text-align:right;color:var(--good,#3ddc84)">+${((b.ev_per_unit || 0) * 100).toFixed(1)}% EV</span>
          </div>`).join("")}
        ${steam.map(({ r, m }) => {
          // Every alert answers: is this still bettable, or already missed?
          const age = m.moved_ago_min;
          const cls = (age != null && age > 180)
            ? ["Stale", "var(--text-mute,#889)", "old move — informational only"]
            : ((r.ev_per_unit || 0) > 0
               ? ["Live", "var(--good,#3ddc84)", "value still available near the sharp number"]
               : ["Chase", "var(--warn,#e8b33e)", "line already moved past it — do not follow"]);
          return `<div class="drow" style="display:flex;align-items:center;gap:14px;padding:11px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
            <span>${iconMark("hot")}</span>
            <span style="flex:1"><strong>${escapeHtml(r.player)} ${escapeHtml(r.market_label || "")}</strong>
              <span style="display:block;opacity:.6;font-size:.85em">steam — several books moved together, ${m.verdict === "with" ? "toward" : "against"} our ${escapeHtml(r.side || "")}${age != null ? ` · ${age < 60 ? age + "m" : Math.round(age / 60) + "h"} ago` : ""} · ${cls[2]}</span></span>
            <span style="min-width:56px;text-align:right;font-weight:700;color:${cls[1]}">${cls[0]}</span>
            <span style="min-width:120px;text-align:right;opacity:.8">${Math.abs(m.delta || 0) > 1e-9 ? `${m.open} → ${m.current}` : `${m.open_odds != null ? american(m.open_odds) : "?"} → ${m.current_odds != null ? american(m.current_odds) : "?"}`}</span>
          </div>`;
        }).join("")}
        ${!anchors.length && !steam.length ? `<p class="loading" style="padding:12px">
          Nothing sharp-flagged right now. Sharp-anchor picks appear when a soft book's
          price beats the sharp book's fair value; steam appears when several books
          re-price together inside an hour.</p>` : ""}
      </div>
      <p style="opacity:.55;font-size:.85em;margin-top:12px">Positive-EV bets live on the
      <b>Recommended</b> and <b>Edge Board</b> pages — that's the model's job. This page
      needs no model: it's the books disagreeing with each other. Arbitrage and middle
      prices move fast; verify at the book before betting. Books limit accounts that
      only arb — mix it into normal betting.</p>`;

  const inp = document.getElementById("scan-stake");
  if (inp) inp.addEventListener("change", () => {
    state.scanStake = Math.max(10, parseFloat(inp.value) || 100);
    renderScanner();
  });
}

/* ============================================================
   Prediction Market Intel — informed-flow detection (Polymarket)
   ============================================================ */
function intelStatus(status) {
  const map = {
    Live: ["var(--good,#3ddc84)", "value still available near the flagged entry"],
    Chasing: ["var(--warn,#e8b33e)", "price has already run — the edge is mostly gone"],
    Historical: ["var(--text-mute,#889)", "old flag, informational only"],
  };
  const [color, tip] = map[status] || ["inherit", ""];
  return `<span style="min-width:78px;text-align:right;font-weight:700;color:${color}" title="${tip}">${status}</span>`;
}

function shortWallet(w) {
  return w && w.length > 12 ? `${w.slice(0, 6)}…${w.slice(-4)}` : (w || "");
}

/* Who made the trade, in the width a table cell has.

   Polymarket's `name` is a self-chosen display name, and plenty of traders
   never set one — the API then hands back the wallet address in that field,
   so `name || shortWallet(wallet)` took the branch that skips shortening and
   rendered all 42 characters. Middle-truncating by CSS instead would give
   "0x3DFb15…", which identifies nobody: the last four characters are how a
   wallet is recognised, and they are the ones an ellipsis eats.

   So: shorten anything address-SHAPED whichever field it arrived in, and
   leave real handles alone for the ellipsis to handle if they run long. */
const looksLikeWallet = (s) => /^0x[0-9a-fA-F]{6,}$/.test(s || "");

function traderLabel(b) {
  const raw = (b.name || b.wallet || "").trim();
  return looksLikeWallet(raw) ? shortWallet(raw) : raw;
}

function pmSpark(series, w = 96, h = 30) {
  // 30-day cumulative P&L curve. Zero line dashed; color by where the
  // month ended.
  if (!series || series.length < 2) return "";
  const pad = 2;
  const vals = series.map((p) => p[1]);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  const x = (i) => pad + (i / (series.length - 1)) * (w - 2 * pad);
  const y = (v) => pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad);
  const pts = series.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" L");
  const last = vals[vals.length - 1];
  const color = last >= 0 ? "var(--good)" : "var(--bad)";
  const fmt = (v) => `${v < 0 ? "−" : "+"}$${Math.abs(Math.round(v)).toLocaleString()}`;
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" style="display:block"
      data-tip="past month: ${fmt(vals[0])} → ${fmt(last)} (low ${fmt(Math.min(...vals))}, high ${fmt(Math.max(...vals))})">
    <line x1="${pad}" y1="${y(0).toFixed(1)}" x2="${w - pad}" y2="${y(0).toFixed(1)}"
      stroke="currentColor" stroke-width="0.7" stroke-dasharray="3 3" opacity="0.25"/>
    <path d="M${pts}" fill="none" stroke="${color}" stroke-width="1.6"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(series.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="2" fill="${color}"/>
  </svg>`;
}

function pmAgo(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/* Polymarket and Fantasy are top-level modes next to NFL/MLB, not tabs
   inside a sport — entering one hides the sport nav; leaving restores it. */
/* Rosters used to live here, which put "who is on this team" behind a
   tools menu and made it mean the NFL and only the NFL. It is a tab
   inside each sport now. */
const STANDALONE_MODES = ["intel", "fantasy", "ufc", "why", "about",
                          "record", "lab"];

// Header identity per standalone page — the tagline follows the ACTIVE
// page. Before this, opening Polymarket from the MLB tab left a baseball
// description in the corner of a page that has nothing to do with baseball.
const STANDALONE_BRAND = {
  intel: { tagline: "Polymarket informed-flow intelligence" },
  fantasy: { tagline: "Fantasy football — usage, scripts, draft kit" },
  ufc: { tagline: "Scalpy MMA — dossier-gated fight model" },
  why: { tagline: "See the math. Know if it's working." },
  record: { tagline: "The Book — every pick journaled, graded, learned from" },
  lab: { tagline: "The Lab — the model replayed against stored history" },
};

function enterStandaloneMode(name) {
  document.querySelectorAll(".sport-btn").forEach((x) =>
    x.classList.toggle("active", !!x.dataset.sport && x.dataset.sport === name));
  const nav = document.getElementById("nav");
  if (nav) nav.style.display = "none";
  // …and its menu label with it: a "PAGE" header over an empty space is
  // worse than no header. Standalone pages have no page list.
  const phead = document.querySelector('.menu-head[data-head="page"]');
  if (phead) phead.style.display = "none";
  markMoreMenu();          // the tool button just became active
  const brand = STANDALONE_BRAND[name];
  if (brand) {
    document.getElementById("tagline").textContent = brand.tagline;
  }
  // Fantasy is NFL — avatars must draw helmets even if MLB was selected.
  if (name === "fantasy") window.ACTIVE_SPORT = "nfl";
  // The Book's front door opens on the WHOLE record — the cross-sport
  // view where the learning ladder reads unscoped. The scope chips still
  // narrow to a league, and a chip already chosen this session is kept.
  if (name === "record" && !_recordScope) _recordScope = "all";
  switchView(name);
}

function exitStandaloneMode() {
  const nav = document.getElementById("nav");
  if (nav) nav.style.display = "";
  const phead = document.querySelector('.menu-head[data-head="page"]');
  if (phead) phead.style.display = "";
  document.querySelectorAll(".sport-btn").forEach((x) =>
    x.classList.toggle("active",
                       !!x.dataset.sport && x.dataset.sport === state.sport));
  markMoreMenu();
  // Restore the sport's own tagline along with its nav. (The Q tile is
  // constant now, so only the words change.)
  const meta = SPORT_META[state.sport];
  if (meta) {
    document.getElementById("tagline").textContent = meta.tagline;
  }
  window.ACTIVE_SPORT = state.sport;
  if (STANDALONE_MODES.includes(state.view)) {
    switchView("recommended");
    // Restore the sports slate's own data-source badge and date label.
    if (state.data) {
      renderDataSource(state.data);
      const el = document.getElementById("slate-date");
      if (el) el.textContent = slateDateLabel(state.data);
    }
  }
}

/* The header badge reflects the ACTIVE page. The sports slate may be on
   sample data (offseason) while Polymarket/Fantasy run on real feeds —
   showing "Sample data" over live pages was a lie of scope. */
function setStandaloneSource(label, dateLabel) {
  const el = document.getElementById("data-source");
  if (el) {
    el.className = "data-source live";
    el.innerHTML = `<span class="src-dot"></span>Live data`;
    el.title = label;
  }
  const dt = document.getElementById("slate-date");
  if (dt && dateLabel) dt.textContent = dateLabel;
}

/* The Kalshi board: the exchange's probability beside ours, per game.

   The one honest advantage an exchange has over a sportsbook as a DATA
   source: its mid IS the market's probability. A book's line carries the
   book's margin and has to be de-vigged on an assumption; a two-sided
   order book's midpoint is the market clearing price of the claim itself.
   So the board states three numbers per matched game — Kalshi's, ours, and
   the gap in points — and where a leg is missing it says which, because a
   price with no comparison is still information. */
function kalshiSectionHTML(k) {
  if (!k) return "";
  const rows = (k.rows || []).map((r) => {
    const edge = r.edge_pts == null ? `<span style="opacity:.45">—</span>`
      : `<span style="color:var(--${r.edge_pts > 0 ? "good" : "bad"});font-weight:700">
           ${r.edge_pts > 0 ? "+" : ""}${r.edge_pts} pts</span>`;
    const basis = r.price_basis === "last_trade"
      ? ` <span class="chip" title="One side of the book is empty — this is the last trade, not a two-sided mid">last trade</span>` : "";
    return `<div class="kx-row">
      <span class="kx-sport chip">${escapeHtml((r.sport || "").toUpperCase())}</span>
      <span class="kx-title" title="${escapeHtml(r.title)}">${escapeHtml(r.title)}
        ${r.matchup ? `<span class="kx-match">· ${escapeHtml(r.matchup)}</span>` : ""}${basis}</span>
      <span class="kx-num kx-k" title="Kalshi mid — the exchange's own probability">${(r.prob * 100).toFixed(0)}%</span>
      <span class="kx-num kx-m" title="Our model's probability for the same claim">${r.model_p == null ? "—" : (r.model_p * 100).toFixed(0) + "%"}</span>
      <span class="kx-num kx-e">${edge}</span>
      <span class="kx-vol" title="24h volume">$${Number(r.volume_24h || 0).toLocaleString()}</span>
    </div>`;
  }).join("");
  const empty = (k.rows || []).length ? "" : `
    <p class="loading" style="padding:12px">${escapeHtml(k.note
      || "No open sports markets seen on the last pull — the board fills as Kalshi lists games.")}</p>`;
  return `
    <div class="section-title">Kalshi board
      <span class="sub">— CFTC-regulated event contracts, all fifty states. The mid of a
      two-sided book is the market's probability with no vig to strip; "edge" is our model
      minus that, in points, and only appears where both numbers exist.</span></div>
    <div class="stats">
      <div class="tile"><div class="k">Sports markets</div><div class="v">${k.n_markets || 0}</div></div>
      <div class="tile"><div class="k">Matched to tonight</div><div class="v">${k.n_matched || 0}</div></div>
      <div class="tile"><div class="k">With a model number</div><div class="v">${k.n_modeled || 0}</div></div>
      <div class="tile"><div class="k">Tape stored</div><div class="v">${((k.tape || {}).stored_total || 0).toLocaleString()}</div>
        <div class="tile-sub">snapshots — order books can't be backfilled</div></div>
    </div>
    <div class="card kx-table" style="padding:0">${rows}${empty}</div>`;
}

async function renderIntel() {
  const host = document.getElementById("intel-body");
  if (!host) return;
  let d = null, kx = null;
  try {
    const res = await fetch("data/predmarkets.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  try {
    const res = await fetch("data/kalshi.json?t=" + Date.now());
    if (res.ok) kx = await res.json();
  } catch (e) {}
  if (!d || (!(d.flow || []).length && !(d.markets || []).length)) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No prediction-market data yet</div>
      <div class="es-sub">The launcher pulls Kalshi's order books and Polymarket's public
      market list and trade tape on every refresh (free, no key needed). If this persists,
      the machine may not be able to reach the venues.</div></div>`
      + kalshiSectionHTML(kx);
    return;
  }
  setStandaloneSource("Kalshi + Polymarket public feeds", "Prediction markets · live venue data");
  const tape = d.tape || {};
  const proven = pmSignalProven(d.validation);
  const cents = (p) => p == null ? "—" : `${(p * 100).toFixed(0)}¢`;
  const usd = (v) => `$${Number(v || 0).toLocaleString()}`;
  const statusColor = { Live: "var(--good)", Chasing: "var(--warn)", Historical: "var(--text-mute)" };
  const heat = (s) => s >= 70 ? "var(--bad)" : s >= 40 ? "var(--warn)" : "var(--brand)";
  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div>
    <div class="v">${v}</div>${sub ? `<div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${sub}</div>` : ""}</div>`;

  const flagCards = (d.flow || []).slice(0, 12).map((f) => {
    const color = statusColor[f.status] || "var(--brand)";
    const sigs = (f.signals || []).map((s) =>
      `<span class="chip" title="${escapeHtml(s.value)}">${escapeHtml(s.name)}</span>`).join("");
    return `<article class="card" style="--grade-color:${color}">
      <div class="card-head">
        <div class="card-id">
          <div class="score-ring" title="Composite informed-flow score (0–100)"
            style="background:conic-gradient(${heat(f.score)} ${f.score * 3.6}deg, rgba(255,255,255,.08) 0)">
            <span>${f.score}</span></div>
          <div>
            <div class="player"><a class="wallet" href="https://polymarket.com/profile/${escapeHtml(f.wallet)}"
              target="_blank" rel="noopener" style="color:inherit">${escapeHtml(traderLabel(f))}</a></div>
            <div class="subtitle">${pmAgo(f.ts)} · ${f.wallet_trades} trade(s) on our tape</div>
            <div class="pick">${escapeHtml(f.side)} ${escapeHtml(f.outcome)}
              <span class="book">· ${usd(f.usd)}</span></div>
          </div>
        </div>
        <span class="pm-status" style="color:${color}">${f.status.toUpperCase()}</span>
      </div>
      <!-- .pm-title so the stylesheet can find this link: it is the card's
           headline and its main tap target, and needs a thumb-sized hit
           box on a phone. -->
      <div class="pm-title" style="margin:8px 0 10px;font-weight:600;line-height:1.35">
        <a href="https://polymarket.com/market/${escapeHtml(f.slug)}" target="_blank"
           rel="noopener" style="color:inherit">${escapeHtml(f.market)}</a></div>
      <div class="metrics">
        <div class="metric"><div class="k">Position</div><div class="v">${usd(f.usd)}</div></div>
        <div class="metric"><div class="k">Entry</div><div class="v">${cents(f.entry_price)}</div></div>
        <div class="metric primary"><div class="k">Now</div><div class="v" style="color:${color}">${cents(f.current_price)}</div></div>
      </div>
      <div class="chips" style="margin-top:10px">${sigs}</div>
      <div style="margin-top:10px;font-size:var(--fs-sm);padding-top:8px;border-top:1px solid rgba(255,255,255,.06)">
        <span style="color:var(--text-mute)">The trade this flag points at:</span>
        <b>${escapeHtml(f.side)} ${escapeHtml(f.outcome)}</b> at ${cents(f.current_price)} or better
        · ${proven
          ? `<span style="color:var(--good);font-weight:700">recommended (signal proven — 0.1u)</span>`
          : `<span style="color:var(--warn)">tracked, not recommended</span> — graded on the Record page`}
      </div>
    </article>`;
  }).join("");

  const traderCards = (d.top_traders || []).map((t) => {
    const label = traderLabel(t);
    const initials = (t.name ? t.name.replace(/[^a-zA-Z0-9 ]/g, "").split(/\s+/)
      .map((w) => w[0]).slice(0, 2).join("") : t.wallet.slice(2, 4)) || "?";
    const last = (t.recent || [])[0];
    const lastTxt = last
      ? `${escapeHtml(last.side)} ${escapeHtml(last.outcome)} · ${usd(last.usd)} @ ${cents(last.price)} · ${escapeHtml(last.market)} · ${pmAgo(last.ts)}`
      : "no recent public trades pulled";
    return `<article class="card">
      <div class="card-head">
        <div class="card-id">
          <div class="pm-avatar">${escapeHtml(initials)}</div>
          <div>
            <div class="player">#${t.rank} <a class="wallet" href="https://polymarket.com/profile/${escapeHtml(t.wallet)}"
              target="_blank" rel="noopener" style="color:inherit">${escapeHtml(label)}</a></div>
            <div class="subtitle wallet">${shortWallet(t.wallet)}</div>
          </div>
        </div>
        <span style="font-weight:800;font-size:var(--fs-xl);color:${t.pnl >= 0 ? "var(--good)" : "var(--bad)"}">
          ${t.pnl ? `${t.pnl >= 0 ? "+" : "−"}${usd(Math.abs(t.pnl))}` : "—"}</span>
      </div>
      ${t.pnl_series && t.pnl_series.length > 1
        ? `<div style="margin-top:10px">${pmSpark(t.pnl_series, 300, 62)}
           <div style="color:var(--text-mute);font-size:var(--fs-xs);margin-top:3px">Cumulative P&amp;L — past month (hover for numbers)</div></div>` : ""}
      <div style="margin-top:10px;color:var(--text-body);font-size:var(--fs-sm)">
        <span style="color:var(--text-mute)">Latest:</span> ${lastTxt}</div>
    </article>`;
  }).join("");

  const marketRows = (d.markets || []).slice(0, 20).map((m, i) => `
    <div class="dl-row pm-market">
      <span class="dl-rank">${i + 1}</span>
      <span class="dl-main pm-q">
        <a href="https://polymarket.com/market/${escapeHtml(m.slug)}" target="_blank" rel="noopener"
           style="color:inherit;font-weight:600">${escapeHtml(m.question)}</a></span>
      <span class="dl-num strong">${cents(m.yes)}</span>
      <span class="dl-num vol">${usd(m.vol24)} / 24h</span>
      <span class="dl-num end">${escapeHtml(m.end_date || "")}</span>
    </div>`).join("");

  host.innerHTML = `
    <div class="stats">
      ${tile("Trades on tape", Number(tape.stored_total || 0).toLocaleString(), `+${tape.new_this_pull || 0} this pull`)}
      ${tile("Wallets seen", Number(tape.wallets_seen || 0).toLocaleString(), "recording since day one")}
      ${tile("Flow flags · 24h", (d.flow || []).length, "$5K+ scored trades")}
      ${tile("Updated", escapeHtml((d.generated_at || "").slice(11, 16)), "refreshes with the site")}
    </div>
    ${intelVerdict(d.validation)}
    <div class="section-title">Informed flow
      <span class="sub">— large trades scored for anomaly signals, with receipts on every chip
      (hover). Probabilities, never verdicts.</span></div>
    <div class="cards wide">${flagCards ||
      `<div class="empty-slate" style="grid-column:1/-1"><div class="es-icon">${icon("signal", 30)}</div>
        <div class="es-title">No flagged flow yet</div>
        <div class="es-sub">The feed scores the last 24h of recorded tape and accumulates
        across refreshes — big trades are a few per hour.</div></div>`}</div>
    ${intelReportCard(d.validation)}
    <div class="section-title">Top traders
      <span class="sub">— ${escapeHtml(d.traders_note || "by realized profit")}</span></div>
    <div class="cards wide">${traderCards ||
      `<p class="loading" style="grid-column:1/-1">No trader data yet — fills on the next refresh.</p>`}</div>
    <div class="section-title">Top markets
      <span class="sub">— live markets by 24h volume · YES price · resolution date</span></div>
    <div class="card" style="padding:0">${marketRows}</div>
    ${kalshiSectionHTML(kx)}
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Wallet-age signal
      matures as the tape accrues (it cannot be backfilled). Kalshi carries no public
      trader identity, which is why it appears above as a PRICE and not as flow.
      Analyzing public flow is market research; what the CFTC prosecutes
      (2026) is trading on information <i>you</i> hold a duty to keep confidential.</p>`;
}

/* ============================================================
   Fantasy Football — usage trends, buy-low/sell-high, game scripts
   ============================================================ */
async function renderFantasy() {
  const host = document.getElementById("fantasy-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/fantasy.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d || !d.season) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("trophy", 30)}</div>
      <div class="es-title">No NFL usage data yet</div>
      <div class="es-sub">${escapeHtml((d && d.note) || "Run `python3 ingest.py nfl` once — usage rows (targets, carries, air yards, PPR points) ride along with the normal player-log ingest, then this page fills automatically.")}</div></div>`;
    return;
  }
  setStandaloneSource(`Ingested NFL ${d.season} weekly stats (nflverse)`,
                      `NFL ${d.season} · ingested history`);
  const pct = (v) => v == null ? "—" : `${(v * 100).toFixed(0)}%`;
  const deltaChip = (dv) => {
    if (dv == null || Math.abs(dv) < 0.03) return `<span class="chip">steady</span>`;
    return dv > 0
      ? `<span class="chip up">▲ +${(dv * 100).toFixed(0)}pt<span class="chip-suffix"> vs 4wk</span></span>`
      : `<span class="chip down">▼ ${(dv * 100).toFixed(0)}pt<span class="chip-suffix"> vs 4wk</span></span>`;
  };

  // A flex row with one greedy name column left ~600px of empty table
  // between the player and the numbers on a laptop. It is now a grid, and
  // the space that opened up carries the thing this page says matters
  // most: last week's share as a bar, with a tick where the season
  // average sits — so a riser at 42% is visibly a riser, not just three
  // percentages you have to diff in your head.
  const shareBar = (u) => {
    const scale = 0.5;                              // 50% of team volume = full bar
    const w = (v) => `${Math.min(100, ((v || 0) / scale) * 100).toFixed(1)}%`;
    const up = (u.delta || 0) > 0.03, down = (u.delta || 0) < -0.03;
    const color = up ? "var(--good)" : down ? "var(--bad)" : "var(--brand)";
    return `<span class="ff-bar" title="Last week ${pct(u.last)} of team volume · season average ${pct(u.season)}">
      <i style="width:${w(u.last)};background:${color}"></i>
      ${u.season != null ? `<b style="left:${w(u.season)}"></b>` : ""}</span>`;
  };
  const usageRow = (u) => `
    <div class="ff-row">
      <span class="ff-who">${playerAvatar(u.player, u.team, { map: nflMap() })}
        <span class="ff-name"><strong>${escapeHtml(u.player)}</strong>
          <span class="ff-pos">${escapeHtml(u.position)} · ${nflName(u.team)}${
            u.moved_from ? ` <b style="color:var(--warn)">← traded from ${nflName(u.moved_from)}</b>` : ""}${
            u.roster_flag ? ` <b style="color:var(--warn)">(${escapeHtml(u.roster_flag)})</b>` : ""} · ${escapeHtml(u.metric)}</span></span></span>
      ${shareBar(u)}
      <span class="ff-n" title="season average">${pct(u.season)}</span>
      <span class="ff-n dim" title="4-week average">${pct(u.l4)}</span>
      <span class="ff-n lead" title="most recent week">${pct(u.last)}</span>
      <span class="ff-n trend">${deltaChip(u.delta)}</span>
      <span class="ff-n dim rz" title="TD equity from play-by-play">${u.rz_pg != null ? `${u.rz_pg} ${escapeHtml(u.rz_label || "RZ/g")}` : "—"}</span>
      <span class="ff-n mute">${u.fp_pg} ppg</span>
    </div>`;
  // The table is ranked by how big the role change is, so the top of it is
  // the point and the tail is reference. Showing all 40 at once buried
  // every other section on the page under ~3400px of near-identical rows.
  const USAGE_SHOWN = 12;
  const allUsage = (d.usage || []).slice(0, 40);
  const usageRows = allUsage.slice(0, USAGE_SHOWN).map(usageRow).join("")
    + (allUsage.length > USAGE_SHOWN
      ? `<div id="usage-rest" class="ff-hidden">${allUsage.slice(USAGE_SHOWN).map(usageRow).join("")}</div>
         <button class="ff-more" id="usage-more" aria-expanded="false" aria-controls="usage-rest">
           Show ${allUsage.length - USAGE_SHOWN} more movers ▾</button>` : "");

  const draftKit = draftKitHTML(d.draft_kit);
  const off = d.offseason || {};
  const coachChanged = {};
  (off.coach_changes || []).forEach((c) => { coachChanged[c.team] = c.now; });

  const bs = d.buy_sell || {};
  const tradeCard = (r, kind) => {
    const buy = kind === "buy";
    return `<article class="card" style="--grade-color:${buy ? "var(--good)" : "var(--warn)"}">
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team, { map: nflMap() })}
          <div><div class="player">${escapeHtml(r.player)}</div>
            <div class="subtitle">${escapeHtml(r.position)} · ${nflName(r.team)}${
              r.moved_from ? ` <b style="color:var(--warn)">← traded from ${nflName(r.moved_from)}</b>` : ""}${
              r.roster_flag ? ` <b style="color:var(--warn)">(${escapeHtml(r.roster_flag)})</b>` : ""} ·
              ${r.targets_pg} tgt/g · ${r.carries_pg} car/g</div></div>
        </div>
        <span class="pm-status" style="color:${buy ? "var(--good)" : "var(--warn)"}">${buy ? "BUY LOW" : "SELL HIGH"}</span>
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">Actual</div><div class="v">${r.actual_ppg}</div></div>
        <div class="metric"><div class="k">${r.basis === "xfp" ? "xFP says" : "Volume says"}</div><div class="v">${r.expected_ppg}</div></div>
        <div class="metric primary"><div class="k">Gap</div><div class="v ${r.gap < 0 ? "pos" : "neg"}">${r.gap > 0 ? "+" : ""}${r.gap}</div></div>
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:var(--fs-sm)">
        ${r.basis === "xfp"
          ? (buy ? "Expected points value every opportunity by WHERE it happened — his say the production is coming."
                 : "Scoring above what his situations support — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")
          : (buy ? "Usage says the production is coming — the volume is already there."
                 : "Producing above what the opportunity supports — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")}</div>
    </article>`;
  };

  const scriptCards = (d.scripts || []).slice(0, 16).map((s) => `
    <article class="card">
      <div class="card-head">
        <div><div class="player">${escapeHtml(s.away)} @ ${escapeHtml(s.home)}</div>
          <div class="subtitle">Week ${parseInt(s.week, 10) || escapeHtml(s.week)} · total ${s.total} · ${escapeHtml(s.favorite)} −${Math.abs(s.spread)}</div></div>
        <span class="chip">${escapeHtml(s.archetype)}</span>
      </div>
      ${[s.home, s.away].filter((t) => coachChanged[t]).map((t) =>
        `<div class="warning" style="margin-top:8px">${iconMark("clock")}${escapeHtml(t)} has a new head coach
           (${escapeHtml(coachChanged[t])}) — last season's tendencies (PROE included) may not carry</div>`).join("")}
      <div class="metrics">
        <div class="metric"><div class="k">${escapeHtml(s.home)} implied</div><div class="v">${s.home_implied}</div></div>
        <div class="metric"><div class="k">${escapeHtml(s.away)} implied</div><div class="v">${s.away_implied}</div></div>
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:var(--fs-sm)">${escapeHtml(s.read)}</div>
      ${s.home_proe != null || s.away_proe != null
        ? `<div style="margin-top:6px;color:var(--text-dim);font-size:var(--fs-sm)" title="Pass rate over expectation — intent vs situation, the stable half of game script">
            PROE: ${escapeHtml(s.home)} ${s.home_proe != null ? `${s.home_proe >= 0 ? "+" : ""}${(s.home_proe * 100).toFixed(1)}%` : "—"}
            · ${escapeHtml(s.away)} ${s.away_proe != null ? `${s.away_proe >= 0 ? "+" : ""}${(s.away_proe * 100).toFixed(1)}%` : "—"}</div>` : ""}
      ${s.home_epa != null || s.away_epa != null
        ? `<div style="margin-top:4px;color:var(--text-dim);font-size:var(--fs-sm)"
               title="EPA/play: offensive efficiency measured from every snap (league avg ≈ 0). Pace: seconds per snap with the game in the balance — lower is faster.">
            EPA/play: ${escapeHtml(s.home)} ${s.home_epa != null ? `${s.home_epa >= 0 ? "+" : ""}${s.home_epa.toFixed(2)}` : "—"}
            · ${escapeHtml(s.away)} ${s.away_epa != null ? `${s.away_epa >= 0 ? "+" : ""}${s.away_epa.toFixed(2)}` : "—"}${
            s.home_pace != null || s.away_pace != null
              ? ` &nbsp;·&nbsp; pace ${s.home_pace != null ? s.home_pace.toFixed(1) : "—"}s / ${
                  s.away_pace != null ? s.away_pace.toFixed(1) : "—"}s` : ""}</div>` : ""}
      <div style="margin-top:6px;color:var(--text-mute);font-size:var(--fs-sm)">Script confidence: ${escapeHtml(s.confidence)}</div>
    </article>`).join("");

  const bsCount = (bs.buy_low || []).length + (bs.sell_high || []).length;
  host.innerHTML = `
    <div class="stats">
      <div class="tile"><div class="k">Season</div><div class="v">${d.season}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${d.season < new Date().getFullYear()
          ? "last completed — live weekly in Sept" : "updating weekly"}</div></div>
      <div class="tile"><div class="k">Usage movers</div><div class="v">${(d.usage || []).length}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">biggest role changes tracked</div></div>
      <div class="tile"><div class="k">Trade flags</div><div class="v">${bsCount}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">outside the sustainable band</div></div>
      <div class="tile"><div class="k">Game scripts</div><div class="v">${(d.scripts || []).length}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">games with posted lines</div></div>
    </div>
    <div id="sleeper-zone"></div>
    ${campHTML(d.camp)}
    ${waiverPulseHTML(d.trending)}
    ${offseasonHTML(off)}
    ${draftKit}
    <div class="ls-note">Shares are of TEAM volume: targets for WR/TE/QB, carries for RB.
      The delta column is the money — a riser at 42% beats a flat 60%.</div>
    <div class="section-title">Usage movers
      <span class="sub">— season vs 4-week vs last week, biggest role changes first</span></div>
    <div class="card ff-table">
      <div class="ff-row ff-head">
        <span class="ff-who">Player</span><span class="ff-bar-h">Last week's share</span>
        <span class="ff-n">Season</span><span class="ff-n">4-week</span><span class="ff-n">Last</span>
        <span class="ff-n trend">Trend</span><span class="ff-n rz">RZ/g</span><span class="ff-n">PPR</span>
      </div>
      ${usageRows || `<p class="loading" style="padding:12px">No usage rows for this season yet.</p>`}
    </div>
    <div class="section-title">Buy low
      <span class="sub">— volume-expected points say the production is coming</span></div>
    <div class="cards wide">${(bs.buy_low || []).map((r) => tradeCard(r, "buy")).join("") ||
      `<p class="loading" style="grid-column:1/-1">Nobody outside the sustainable band right now.</p>`}</div>
    <div class="section-title">Sell high
      <span class="sub">— outrunning their opportunity; regression risk</span></div>
    <div class="cards wide">${(bs.sell_high || []).map((r) => tradeCard(r, "sell")).join("") ||
      `<p class="loading" style="grid-column:1/-1">Nobody outside the sustainable band right now.</p>`}</div>
    <div class="section-title">Game scripts
      <span class="sub">— Vegas is the input: implied totals, archetypes, and confidence that
      scales with the spread</span></div>
    <div class="cards wide">${scriptCards ||
      `<p class="loading" style="grid-column:1/-1">No upcoming NFL games with posted spreads and
       totals in the DB yet — fills when next season's lines are ingested.</p>`}</div>
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Expected points are
      fit from this season's own data (league value per target and per carry by position) —
      volume-based, so a player can legitimately sustain a positive gap; only gaps beyond
      ~${bs.band || 1.5} PPG are flagged. Updated ${escapeHtml(d.generated_at || "")}.</p>`;
  const more = document.getElementById("usage-more");
  if (more) more.addEventListener("click", () => {
    const rest = document.getElementById("usage-rest");
    const open = rest.classList.toggle("ff-hidden") === false;
    more.setAttribute("aria-expanded", String(open));
    more.textContent = open ? "Show fewer ▴"
      : `Show ${allUsage.length - USAGE_SHOWN} more movers ▾`;
  });
  initDraftKit(d.draft_kit);
  renderSleeperZone(d);
}

/* The Fantasy page is ALWAYS football, whatever sport tab the user
   arrived from — resolving its abbreviations through the active sport's
   map once rendered the Vikings as the Twins and the Ravens as the
   Orioles (both leagues use MIN and BAL). These helpers pin the map. */
const nflMap = () => (typeof TEAMS !== "undefined" ? TEAMS : {});
const nflName = (a) => (nflMap()[a] && nflMap()[a].nick) || a;

/* Camp watch — daily depth-chart snapshots diffed across the preseason.
   The chart is the coaching staff's own verdict; the DIFF is the signal:
   who won a job before Week 1 lines and fantasy drafts price it. */
function campHTML(camp) {
  if (!camp) return "";
  const slot = (r, o) => `${escapeHtml(r.position)}${o}`;
  const row = (r, tone) => `
    <div class="os-row"><span class="os-team">${escapeHtml(r.player)}
        <span class="dk-pt">${nflName(r.team)}${r.rookie ? " · rookie" : ""}</span></span>
      <span class="os-before">${slot(r, r.from_order)}</span>
      <span class="os-arrow">→</span>
      <span class="os-now" style="color:${tone}">${slot(r, r.to_order)}</span></div>`;
  const box = (title, sub, rows, empty) => `
    <article class="card os-card">
      <div class="card-head"><div><div class="player">${title}</div>
        <div class="subtitle">${sub}</div></div></div>
      <div class="os-body">${rows || `<p class="loading" style="padding:8px 0">${empty}</p>`}</div>
    </article>`;
  if ((camp.days || 0) < 2) {
    return `
      <div class="section-title">Camp watch
        <span class="sub">— depth charts snapshotted daily; movers appear as camp
        shakes them out</span></div>
      <div class="card"><p class="loading">Tracking started ${escapeHtml(camp.tracking_since || "today")} —
        the first movers show after a few days of snapshots. The depth chart is the coaching
        staff's own verdict; the change over camp is the honest preseason signal, not
        August box scores.</p></div>`;
  }
  const accruing = `No chart movement in the window yet.`;
  return `
    <div class="section-title">Camp watch
      <span class="sub">— depth-chart movement ${escapeHtml(camp.from)} → ${escapeHtml(camp.to)},
      from the coaching staffs' own charts. Preseason box scores are backups vs backups;
      WHO RUNS FIRST-TEAM is the signal that prices Week 1.</span></div>
    <div class="cards wide">
      ${box("New starters", "took over a №1 job during camp — the strongest Week-1 signal here",
            (camp.new_starters || []).map((r) => row(r, "var(--good)")).join(""), accruing)}
      ${box("Risers", "climbing the chart — roles headed their way",
            (camp.risers || []).map((r) => row(r, "var(--good)")).join(""), accruing)}
      ${box("Fallers", "sliding — last season's usage overstates their Week-1 role",
            (camp.fallers || []).map((r) => row(r, "var(--warn)")).join(""), accruing)}
    </div>`;
}

/* ============================================================
   Offseason panel — what changed since the stats were recorded.
   Coaching changes come from the schedule file itself (each game
   row is stamped with both head coaches); rosters and rookies
   from Sleeper's players feed. All data, no news-cycle memory.
   ============================================================ */
/* The 24h waiver-wire pulse — what every Sleeper league is grabbing and
   dumping RIGHT NOW. Market attention, not our model: the two disagreeing
   is the interesting case, so it sits beside the usage boards. Always
   NFL-labeled via nflMap, whatever sport tab the visitor came from. */
function waiverPulseHTML(t) {
  if (!t || (!(t.adds || []).length && !(t.drops || []).length)) return "";
  const fmt = (n) => n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, "") + "k" : String(n);
  const col = (title, rows, tone, verb) => `
    <div class="card" style="padding:14px 16px">
      <div style="font-weight:800;margin-bottom:8px">${title}</div>
      ${rows.slice(0, 8).map((r) => `
        <div class="dl-row">
          <span class="dl-main">${playerAvatar(r.player, r.team, { size: 26, map: nflMap() })}
            <span><strong>${escapeHtml(r.player)}</strong>
              <span class="dl-sub">${escapeHtml(r.position || "")} · ${escapeHtml(nflName(r.team))}</span></span></span>
          <span class="dl-num strong" style="color:${tone}"
                title="${verb} in ${fmt(t.lookback_hours || 24)}h across all Sleeper leagues">${fmt(r.count)}</span>
        </div>`).join("")}
    </div>`;
  return `
    <div class="section-title">Waiver-wire pulse
      <span class="sub">— who the fantasy world grabbed and dumped in the last
      ${t.lookback_hours || 24}h (every Sleeper league). Market attention, not our model —
      check the movers against the usage boards below before following the crowd.</span></div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:14px">
      ${(t.adds || []).length ? col(`${iconMark("hot")} Most added`, t.adds, "var(--good)", "adds") : ""}
      ${(t.drops || []).length ? col(`${iconMark("cold")} Most dropped`, t.drops, "var(--bad)", "drops") : ""}
    </div>`;
}

function offseasonHTML(off) {
  if (!off || (!off.upcoming_season && !(off.coach_changes || []).length
               && !off.rosters_live)) return "";
  const pair = (c) => `
    <div class="os-row"><span class="os-team">${teamMark(c.team, 20, nflMap())} ${escapeHtml(nflName(c.team))}</span>
      <span class="os-before">${escapeHtml(c.before)}</span>
      <span class="os-arrow">→</span>
      <span class="os-now">${escapeHtml(c.now)}</span></div>`;
  const move = (m) => `
    <div class="os-row"><span class="os-team">${escapeHtml(m.player)}
        <span class="dk-pt">${escapeHtml(m.position)}</span></span>
      <span class="os-before">${escapeHtml(nflName(m.from))}</span>
      <span class="os-arrow">→</span>
      <span class="os-now">${escapeHtml(nflName(m.to))}</span></div>`;
  const rookie = (r) => `
    <div class="os-row"><span class="os-team">${escapeHtml(r.player)}
        <span class="dk-pt">${escapeHtml(r.position)} · ${nflName(r.team)}</span></span>
      <span class="os-now">${escapeHtml(r.depth_pos)}${r.depth_order < 99 ? r.depth_order : ""} on depth chart</span></div>`;
  const box = (title, sub, rows, empty) => `
    <article class="card os-card">
      <div class="card-head"><div><div class="player">${title}</div>
        <div class="subtitle">${sub}</div></div></div>
      <div class="os-body">${rows || `<p class="loading" style="padding:8px 0">${empty}</p>`}</div>
    </article>`;
  const syncAge = (() => {
    if (!off.rosters_synced_at) return null;
    const ms = Date.now() - new Date(off.rosters_synced_at).getTime();
    return Number.isFinite(ms) ? ms / 36e5 : null;   // hours
  })();
  const rosterNote = !off.rosters_live ? `
    <div class="warning" style="margin-bottom:12px">${icon('warn')} Roster feed unreachable on the last
      build — team moves and rookies may be missing here until the next refresh.
      Coaching changes still current (they come from the schedule file).</div>`
    : syncAge != null && syncAge > 48 ? `
    <div class="warning" style="margin-bottom:12px">${icon('warn')} Rosters last synced
      ${escapeHtml(off.rosters_synced_at)} — over ${Math.floor(syncAge / 24)} days ago
      (the live pull has been failing and a cached copy is serving). Trades since then
      won't show until the feed comes back.</div>`
    : off.rosters_synced_at ? `
    <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-bottom:12px">
      Rosters synced ${escapeHtml(off.rosters_synced_at)} — trades checked on every
      launch, refreshed daily.</div>` : "";
  return `
    <div class="section-title">The ${off.upcoming_season || "upcoming"} offseason
      <span class="sub">— what the league changed under last season's numbers. Derived from
      the schedule and roster feeds on every build, not from a news list that goes stale.</span></div>
    ${rosterNote}
    <div class="cards wide">
      ${box("Coaching changes", "new head coach — last season's tendencies may not carry",
            (off.coach_changes || []).map(pair).join(""), "No changes detected.")}
      ${box("New starting QBs", "depth-chart QB1 now vs who actually started late last season",
            (off.qb_changes || []).map(pair).join(""), off.rosters_live
              ? "No changes detected." : "Needs the roster feed.")}
      ${box("Board players who moved", "their stats came from a different offense — flagged, never re-projected",
            (off.moves || []).map(move).join(""), off.rosters_live
              ? "Nobody on the board has changed teams." : "Needs the roster feed.")}
    </div>
    ${(off.rookies || []).length ? `
      <div class="section-title">Rookies
        <span class="sub">— on rosters now, deliberately unranked: no NFL volume exists,
        and projecting them would be invention. Depth-chart slot is the honest signal.</span></div>
      <div class="card" style="padding:8px 16px">
        <div class="os-rookies">${off.rookies.map(rookie).join("")}</div>
      </div>` : ""}`;
}

/* ============================================================
   Active rosters — every team as it stands today.
   ============================================================ */
/* One cache PER SPORT. Rosters used to be a single page that only ever
   meant the NFL; a roster belongs to a league, and "who is on this team"
   is a question you ask while looking at that league's board. */
const _rosterCache = {};
let _rosterOpen = null;          // which team's roster is expanded

async function loadRosters(sport) {
  const key = sport || state.sport || "nfl";
  if (_rosterCache[key] !== undefined) return _rosterCache[key];
  try {
    const res = await fetch(`data/rosters_${key}.json?t=` + (Date.now() / 60000 | 0));
    _rosterCache[key] = res.ok ? await res.json() : {};
  } catch (e) { _rosterCache[key] = {}; }
  return _rosterCache[key];
}

// Position groups, in the order a depth chart is normally read. Football
// only — the other leagues have no unit split worth grouping by, so their
// players list as one squad rather than under an invented heading.
const ROSTER_GROUPS = [
  ["Offense", ["QB", "RB", "FB", "WR", "TE", "OL", "OT", "OG", "C"]],
  ["Defense", ["DL", "DE", "DT", "NT", "LB", "ILB", "OLB", "CB", "S", "FS", "SS", "DB"]],
  ["Special teams", ["K", "P", "LS"]],
];

function rosterGroupOf(pos) {
  for (const [label, members] of ROSTER_GROUPS) if (members.includes(pos)) return label;
  return "Other";
}

/* What each league's roster tab is actually showing, said plainly. The
   NFL has a published depth chart; the others are built from who really
   appeared, and the page must not let those look like the same claim. */
/* The search box has to speak the sport it is sitting on. It shipped
   asking for "49ers, SF, Purdy" on every league, which on the MLB page is
   an example of nothing you can type. */
const ROSTER_PLACEHOLDER = {
  nfl: "Search a team or a player… (e.g. 49ers, SF, Purdy)",
  mlb: "Search a team or a player… (e.g. Yankees, NYY, Judge)",
  nba: "Search a team or a player… (e.g. Celtics, BOS, Tatum)",
  wnba: "Search a team or a player… (e.g. Liberty, NYL, Stewart)",
};

const ROSTER_COPY = {
  nfl: "— every team as it stands today, ordered by the coaching staff's own "
     + "depth chart. Players who are unavailable (IR, PUP, suspended) are listed "
     + "with their status rather than quietly removed.",
  mlb: "— the league's own active rosters, refreshed through the day, pitchers "
     + "first. The games column is measured from our own logs: playing time is "
     + "still the depth chart, the league feed just decides who exists.",
  nba: "— built from who has actually appeared for each club this season, most "
     + "minutes-logged games first. Measured playing time is the depth chart here, "
     + "rather than somebody's published guess at one.",
  wnba: "— built from who has actually appeared for each club this season, most "
      + "games first. Measured playing time is the depth chart here, rather than "
      + "somebody's published guess at one.",
};

/* One player line. The depth slot is the staff's opinion and is shown as
   such; an unranked player gets no number rather than an invented one. */
function rosterPlayerHTML(p, byAppearance) {
  const slot = byAppearance
    ? (p.games != null ? String(p.games) : "—")
    : (p.depth_order ? `${escapeHtml(p.depth_pos || p.position)}${p.depth_order}` : "—");
  const tags = [
    p.rookie ? `<span class="chip">rookie</span>` : "",
    p.unavailable ? `<span class="chip down">${escapeHtml(p.status || "out")}</span>` : "",
  ].join("");
  const colA = byAppearance
    ? (p.last_seen ? escapeHtml(String(p.last_seen).slice(5)) : "—")
    : (p.age != null ? p.age : "—");
  const colB = byAppearance
    ? "" : (p.years_exp != null ? (p.years_exp === 0 ? "R" : p.years_exp) : "—");
  return `<div class="ros-row${p.unavailable ? " out" : ""}">
    <span class="ros-slot">${escapeHtml(slot)}</span>
    <span class="ros-name">${escapeHtml(p.player)}${tags}</span>
    <span class="ros-pos">${escapeHtml(p.position)}</span>
    <span class="ros-n">${colA}</span>
    <span class="ros-n">${colB}</span>
  </div>`;
}

function rosterTeamHTML(abbr, team, expanded, byAppearance) {
  const meta = (typeof teamsForSport === "function"
    ? teamsForSport(state.sport)[abbr] : null)
    || ((typeof TEAMS !== "undefined" && TEAMS[abbr]) || {});
  const label = meta.name || abbr;
  if (!expanded) {
    return `<button class="ros-team" data-team="${escapeHtml(abbr)}">
      <span class="ros-mark" style="background:${escapeHtml(meta.primary || "#39405166")}">${escapeHtml(abbr)}</span>
      <span class="ros-team-name">${escapeHtml(label)}</span>
      <span class="ros-team-n">${team.count}</span>
    </button>`;
  }
  // Football splits into units; the other leagues do not, so they list as
  // one squad rather than under an invented heading.
  let groups;
  if (byAppearance) {
    groups = team.players.map((p) => rosterPlayerHTML(p, true)).join("");
  } else {
    const byGroup = {};
    for (const p of team.players) {
      (byGroup[rosterGroupOf(p.position)] ||= []).push(p);
    }
    groups = ROSTER_GROUPS.map(([g]) => g).concat("Other")
      .filter((g) => byGroup[g] && byGroup[g].length)
      .map((g) => `<div class="ros-group">${escapeHtml(g)}
          <span class="ros-group-n">${byGroup[g].length}</span></div>
        ${byGroup[g].map((p) => rosterPlayerHTML(p, false)).join("")}`).join("");
  }
  return `<div class="card ros-card">
    <button class="ros-team open" data-team="${escapeHtml(abbr)}">
      <span class="ros-mark" style="background:${escapeHtml(meta.primary || "#39405166")}">${escapeHtml(abbr)}</span>
      <span class="ros-team-name">${escapeHtml(label)}</span>
      <span class="ros-team-n">${team.count}${byAppearance ? "" : ` · ${team.rookies} rookie${team.rookies === 1 ? "" : "s"}`}${team.unavailable ? ` · ${team.unavailable} ${byAppearance ? "cold" : "out"}` : ""}</span>
    </button>
    <div class="ros-head">
      <span class="ros-slot">${byAppearance ? "GP" : "SLOT"}</span><span class="ros-name">PLAYER</span>
      <span class="ros-pos">POS</span><span class="ros-n">${byAppearance ? "LAST" : "AGE"}</span><span class="ros-n">${byAppearance ? "" : "EXP"}</span>
    </div>
    ${groups}</div>`;
}

/* Recent team changes, found by diffing our own daily snapshots — no news
   feed to curate and nothing to tell the site about. */
function transactionsHTML(tx) {
  const moves = (tx && tx.moves) || [];
  if (!moves.length) {
    return `<div class="ls-note">No team changes across the
      ${tx && tx.days ? tx.days : 0} day(s) tracked so far. This list fills
      itself in: each build records where every player is, and a trade is
      simply the day that answer changed.</div>`;
  }
  return `<div class="card" style="padding:0;margin-bottom:14px">
    ${moves.slice(0, 40).map((m) => `<div class="ros-move">
      <span class="ros-move-name">${escapeHtml(m.player)}</span>
      <span class="ros-move-teams">${escapeHtml(m.from)} → <b>${escapeHtml(m.to)}</b></span>
      <span class="ros-move-date">${escapeHtml(m.date)}</span>
    </div>`).join("")}</div>`;
}

/* ============================================================
   Standings + the postseason bracket.

   Both are counted from the same games the rest of the site reads, so a
   record here and a record on a matchup card are the same rows. The two
   are deliberately separate objects: standings are REGULAR SEASON, the
   bracket is postseason and is drawn only from games actually played.
   ============================================================ */
const _standingsCache = {};

async function loadStandings(sport) {
  const key = sport || state.sport || "nfl";
  if (_standingsCache[key] !== undefined) return _standingsCache[key];
  try {
    const res = await fetch(`data/standings_${key}.json?t=` + (Date.now() / 60000 | 0));
    _standingsCache[key] = res.ok ? await res.json() : {};
  } catch (e) { _standingsCache[key] = {}; }
  return _standingsCache[key];
}

function standingsRowHTML(t, label) {
  const meta = (typeof teamsForSport === "function"
    ? teamsForSport(state.sport)[t.team] : null) || {};
  const diff = t.diff > 0 ? `+${t.diff}` : `${t.diff}`;
  const cls = t.diff > 0 ? "good" : t.diff < 0 ? "bad" : "";
  const strk = t.streak > 0 ? "good" : t.streak < 0 ? "bad" : "";
  return `<div class="std-row">
    <span class="std-rank">${t.rank}</span>
    <span class="std-mark" style="background:${escapeHtml(meta.primary || "#39405166")}">${escapeHtml(t.team)}</span>
    <span class="std-name">${escapeHtml(meta.name || meta.nick || t.team)}</span>
    <span class="std-n std-rec">${escapeHtml(t.record)}</span>
    <span class="std-n">${t.pct.toFixed(3).replace(/^0/, "")}</span>
    <span class="std-n ${cls}">${escapeHtml(diff)}</span>
    <span class="std-n std-wide">${t.pf_per_game}/${t.pa_per_game}</span>
    <span class="std-n std-wide">${escapeHtml(t.home)}</span>
    <span class="std-n std-wide">${escapeHtml(t.away)}</span>
    <span class="std-n ${strk}">${escapeHtml(t.streak_label)}</span>
    <span class="std-n std-wide">${escapeHtml(t.last10_label)}</span>
  </div>`;
}

function standingsGroupHTML(g, scoreLabel) {
  return `<div class="card std-card">
    <div class="std-group">${escapeHtml(g.label || g.conference)}</div>
    <div class="std-head">
      <span class="std-rank">#</span><span class="std-mark"></span>
      <span class="std-name">TEAM</span>
      <span class="std-n std-rec">W-L</span><span class="std-n">PCT</span>
      <span class="std-n">DIFF</span>
      <span class="std-n std-wide">${escapeHtml(scoreLabel || "PF/PA")}</span>
      <span class="std-n std-wide">HOME</span><span class="std-n std-wide">AWAY</span>
      <span class="std-n">STRK</span><span class="std-n std-wide">L10</span>
    </div>
    ${g.teams.map((t) => standingsRowHTML(t)).join("")}
  </div>`;
}

/* The bracket. Every matchup on it happened; nothing here is projected —
   that is what `projected_seeds` is for, and it says so on its face. */
function bracketHTML(b) {
  if (!b || !b.started) {
    return `<div class="ls-note">${escapeHtml((b && b.note) || "")}</div>`;
  }
  return `<div class="brk">${b.rounds.map((r) => `
    <div class="brk-round">
      <div class="brk-round-name">${escapeHtml(r.name)}</div>
      <div class="brk-matches">${r.matchups.map((m) => {
        const [a, bb] = m.teams, [wa, wb] = m.score;
        const line = (team, score, won) => `<div class="brk-side${won ? " won" : ""}">
          <span class="brk-team">${escapeHtml(team)}</span>
          <span class="brk-score">${score}</span></div>`;
        return `<div class="brk-match">
          ${line(a, wa, m.leader === a)}
          ${line(bb, wb, m.leader === bb)}
        </div>`;
      }).join("")}</div>
    </div>`).join("")}</div>`;
}

function seedsHTML(seeds) {
  if (!seeds || !seeds.length) return "";
  return `<div class="section-title">If the season ended today
      <span class="sub">— a PROJECTION from the table above, not a bracket.
      Nothing below has been played, and seeding here uses our own order
      rather than the league's official tiebreakers.</span></div>
    <div class="ros-teams">${seeds.map((c) => `<div class="card std-card">
      <div class="std-group">${escapeHtml(c.conference)}</div>
      ${c.seeds.map((t) => `<div class="std-row">
        <span class="std-rank">${t.seed}</span>
        <span class="std-name">${escapeHtml(t.team)}</span>
        <span class="std-n std-rec">${escapeHtml(t.record)}</span>
        <span class="std-n">${t.pct.toFixed(3).replace(/^0/, "")}</span>
      </div>`).join("")}
    </div>`).join("")}</div>`;
}

async function renderStandings() {
  const host = document.getElementById("standings-body");
  if (!host) return;
  const sport = state.sport || "nfl";
  const d = await loadStandings(sport);
  const title = document.getElementById("standings-title");
  if (title) title.childNodes[0].nodeValue =
    `${(SPORT_META[sport] || {}).label || sport.toUpperCase()} standings `;
  const sub = document.getElementById("standings-sub");
  if (sub) {
    sub.textContent = d.season
      ? `— ${d.season} regular season · ${(d.games_counted || 0).toLocaleString()} games counted from our own results · ${d.order_note || ""}`
      : "— counted from our own results.";
  }
  const groups = d.groups || [];
  if (!groups.length) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <h3>No standings yet</h3><p>${escapeHtml(d.note
        || "Run `python3 standings_build.py` once.")}</p></div>`;
    return;
  }
  const b = d.bracket || {};
  host.innerHTML = `
    ${b.started ? `<div class="section-title tight">Postseason
        <span class="sub">— every matchup here was played. Series scores are
        games won, so an unfinished series shows where it stands.</span></div>
      ${bracketHTML(b)}` : ""}
    <div class="section-title"${b.started ? "" : ' style="margin-top:0"'}>Teams
      <span class="sub">— ${groups.length} group(s)</span></div>
    <div class="ros-teams">
      ${groups.map((g) => standingsGroupHTML(g, d.score_label)).join("")}
    </div>
    ${b.started ? "" : seedsHTML(d.projected_seeds)}
    ${b.started ? "" : `<div class="ls-note">${escapeHtml(b.note || "")}</div>`}`;
}

async function renderRosters() {
  const host = document.getElementById("rosters-body");
  if (!host) return;
  const sport = state.sport || "nfl";
  const d = await loadRosters(sport);
  // Only the NFL has a published depth chart. Everything else is built
  // from appearances, and the page must never let those read as the same
  // kind of claim.
  const byAppearance = (d.source === "appearances");
  const sub = document.getElementById("rosters-sub");
  if (sub) sub.textContent = ROSTER_COPY[sport] || "— every team as it stands today.";
  const search = document.getElementById("roster-search");
  if (search) search.placeholder = ROSTER_PLACEHOLDER[sport]
    || "Search a team or a player…";
  const title = document.getElementById("rosters-title");
  if (title) title.childNodes[0].nodeValue =
    `${(SPORT_META[sport] || {}).label || sport.toUpperCase()} rosters `;
  const teams = d.teams || {};
  const abbrs = Object.keys(teams).sort();
  if (!abbrs.length) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("list", 30)}</div>
      <h3>No roster data for ${escapeHtml(sport.toUpperCase())}</h3>
      <p>${escapeHtml(d.note
        || "Run `python3 rosters_build.py` once to build this sport's rosters.")}</p></div>`;
    return;
  }
  const q = (state.rosterQuery || "").trim().toLowerCase();
  // A player search jumps you to his team rather than showing a stray row:
  // "who is this guy with" and "show me that roster" are the same question.
  let shown = abbrs;
  if (q) {
    const known = (typeof teamsForSport === "function")
      ? teamsForSport(sport) : (typeof TEAMS !== "undefined" ? TEAMS : {});
    shown = abbrs.filter((a) => {
      const meta = known[a] || {};
      if (a.toLowerCase().includes(q)) return true;
      if ((meta.name || "").toLowerCase().includes(q)) return true;
      if ((meta.nick || "").toLowerCase().includes(q)) return true;
      if ((meta.loc || "").toLowerCase().includes(q)) return true;
      return teams[a].players.some((p) => p.player.toLowerCase().includes(q));
    });
  }
  // One match is unambiguous — open it instead of making you tap again.
  const open = shown.length === 1 ? shown[0] : _rosterOpen;
  const stale = d.feed === "unavailable"
    ? `<div class="warning" style="margin-bottom:12px">${icon('warn')} ${escapeHtml(d.note || "")}</div>` : "";
  // Team changes come from diffing daily roster snapshots, which only the
  // NFL feed produces. Showing an empty "recent moves" panel for a sport
  // that cannot detect one would read as "no trades happened".
  const moves = d.transactions ? `
    <div class="section-title">Recent team changes
      <span class="sub">— from diffing this site's own daily roster snapshots,
      not a news feed. Anything that changed teams shows up here on its own.</span></div>
    ${transactionsHTML(d.transactions)}` : "";
  host.innerHTML = stale + moves + `
    <div class="section-title">Teams
      <span class="sub">— ${shown.length} of ${abbrs.length} shown${q ? ` matching "${escapeHtml(q)}"` : ""}
      · ${(d.player_count || 0).toLocaleString()} players on file${
        byAppearance && d.season ? ` · ${d.season} season appearances` : ""}</span></div>
    ${shown.length ? `<div class="ros-teams">
        ${shown.map((a) => rosterTeamHTML(a, teams[a], a === open, byAppearance)).join("")}
      </div>` : `<p class="loading">No team or player matches "${escapeHtml(q)}".</p>`}`;
  host.querySelectorAll(".ros-team").forEach((b) => b.addEventListener("click", () => {
    _rosterOpen = _rosterOpen === b.dataset.team ? null : b.dataset.team;
    renderRosters();
  }));
}

/* ============================================================
   Draft kit — VORP board, tiers, and live Sleeper draft sync.
   ============================================================ */
const TIER_COLORS = ["var(--good)", "var(--cyan)", "var(--brand)",
                     "var(--warn)", "var(--text-mute)"];
const tierColor = (t) => TIER_COLORS[Math.min(t - 1, TIER_COLORS.length - 1)];

function draftKitHTML(kit) {
  if (!kit || !(kit.board || []).length) return "";
  const BOARD_SHOWN = 15;
  const moveNote = (r) => r.moved_from
    ? ` · <span class="dk-moved" title="Traded or signed since these stats — the volume behind this projection came in ${escapeHtml(nflName(r.moved_from))}'s offense">NEW TEAM, was ${escapeHtml(r.moved_from)}</span>`
    : r.roster_flag
      ? ` · <span class="dk-moved">${escapeHtml(r.roster_flag)}</span>` : "";
  const boardRow = (r, i) => `
    <div class="dl-row dk-row" data-ffp="${escapeHtml(ffNorm(r.player))}">
      <span class="dl-rank">${i + 1}</span>
      <span class="dl-main"><strong>${escapeHtml(r.player)}</strong>
        <span class="dl-sub">${escapeHtml(r.position)}${r.pos_rank} · ${nflName(r.team)}
          · ${r.games} gm${r.small_sample ? ` ${icon('warn')} small sample` : ""}${moveNote(r)}</span></span>
      <span class="dk-tier" style="color:${tierColor(r.tier)}">T${r.tier}</span>
      <span class="dl-num" title="projected PPR points per game">${r.proj}</span>
      <span class="dl-num strong pos" title="points per game over the best freely-available ${escapeHtml(r.position)}">+${r.vorp}</span>
    </div>`;
  const board = kit.board.slice(0, BOARD_SHOWN).map(boardRow).join("")
    + (kit.board.length > BOARD_SHOWN
      ? `<div id="dk-rest" class="ff-hidden">${kit.board.slice(BOARD_SHOWN)
           .map((r, i) => boardRow(r, i + BOARD_SHOWN)).join("")}</div>
         <button class="ff-more" id="dk-more" aria-expanded="false" aria-controls="dk-rest">
           Show the full board (${kit.board.length}) ▾</button>` : "");

  const posCard = (pos) => {
    const rows = (kit.tiers[pos] || []).slice(0, 15);
    if (!rows.length) return "";
    let lastTier = 0;
    const body = rows.map((r) => {
      const brk = r.tier !== lastTier
        ? `<div class="dk-tierlabel" style="color:${tierColor(r.tier)}">Tier ${r.tier}</div>` : "";
      lastTier = r.tier;
      return `${brk}<div class="dk-posrow" data-ffp="${escapeHtml(ffNorm(r.player))}">
        <span class="dk-pr">${r.pos_rank}</span>
        <span class="dk-pn">${escapeHtml(r.player)}
          <span class="dk-pt">${nflName(r.team)}</span></span>
        <span class="dk-pp">${r.proj}</span>
      </div>`;
    }).join("");
    return `<article class="card dk-poscard">
      <div class="card-head"><div><div class="player">${escapeHtml(pos)}</div>
        <div class="subtitle">replacement ≈ ${kit.replacement[pos] ?? "—"} PPG</div></div></div>
      <div class="dk-posbody">${body}</div>
    </article>`;
  };

  const sleepers = (kit.sleepers || []).map((r) => `
    <div class="dl-row dk-slrow" data-ffp="${escapeHtml(ffNorm(r.player))}">
      <span class="dl-main"><strong>${escapeHtml(r.player)}</strong>
        <span class="dl-sub">${escapeHtml(r.position)} · ${nflName(r.team)}</span></span>
      <span class="dl-num">${r.ppg} actual</span>
      <span class="dl-num strong pos">${r.xppg} expected</span>
    </div>`).join("");

  return `
    <div class="section-title">Draft kit
      <span class="sub">— last season's volume turned into value over replacement.
      Draft by tier, not rank; rookies are not on this board and it says so.</span></div>
    <div class="card dk-draftday">
      <div class="card-head"><div><div class="player">Draft day — live Sleeper sync</div>
        <div class="subtitle">Paste your Sleeper draft link (or its ID) once the draft room
          opens. Taken players cross off everywhere on this page and the best-available
          list stays current.</div></div>
        <span class="pm-status" id="dk-status" style="color:var(--text-mute)">NOT CONNECTED</span></div>
      <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
        <input id="dk-draft-id" type="text" placeholder="https://sleeper.com/draft/nfl/…  or draft ID"
          style="flex:1;min-width:220px;background:var(--panel-2);color:inherit;
          border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
        <button class="btn" id="dk-connect">Connect</button>
        <button class="btn ghost ff-hidden" id="dk-disconnect">Stop</button>
      </div>
      <div id="dk-best" class="ff-hidden" style="margin-top:12px"></div>
    </div>
    <div class="section-title">Overall board
      <span class="sub">— ordered by VORP, not points: value over the best player
      still on the wire at the same position</span></div>
    <div class="card" style="padding:0">${board}</div>
    <div class="section-title">Position tiers
      <span class="sub">— the gaps are the information: inside a tier the differences
      are noise</span></div>
    <div class="cards wide">${["QB", "RB", "WR", "TE"].map(posCard).join("")}</div>
    ${sleepers ? `<div class="section-title">Usage says buy
        <span class="sub">— expected points clearly above what they actually scored;
        the draft-day version of buy-low</span></div>
      <div class="card" style="padding:0">${sleepers}</div>` : ""}
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:10px">
      ${(kit.notes || []).map(escapeHtml).join(" ")}</p>`;
}

/* Live draft sync. One poll loop, keyed off the fantasy view being open —
   navigating away stops it, reconnecting resumes it. */
const dkState = { timer: null, kit: null };

function dkStop(msg) {
  if (dkState.timer) { clearInterval(dkState.timer); dkState.timer = null; }
  const st = document.getElementById("dk-status");
  if (st) { st.textContent = msg || "NOT CONNECTED"; st.style.color = "var(--text-mute)"; }
  const dis = document.getElementById("dk-disconnect");
  if (dis) dis.classList.add("ff-hidden");
}

function initDraftKit(kit) {
  const btn = document.getElementById("dk-connect");
  if (!btn || !kit) return;
  dkState.kit = kit;
  const more = document.getElementById("dk-more");
  if (more) more.addEventListener("click", () => {
    const rest = document.getElementById("dk-rest");
    const open = rest.classList.toggle("ff-hidden") === false;
    more.setAttribute("aria-expanded", String(open));
    more.textContent = open ? "Show fewer ▴" : `Show the full board (${kit.board.length}) ▾`;
  });
  const input = document.getElementById("dk-draft-id");
  const saved = localStorage.getItem("ff_draft_id");
  if (saved) input.value = saved;
  btn.addEventListener("click", () => {
    // Accept a full draft-room URL or a bare numeric ID.
    const m = String(input.value).match(/(\d{10,25})/);
    if (!m) {
      document.getElementById("dk-status").textContent = "NEED A DRAFT LINK OR ID";
      return;
    }
    localStorage.setItem("ff_draft_id", m[1]);
    dkStart(m[1]);
  });
  document.getElementById("dk-disconnect")
    .addEventListener("click", () => dkStop());
}

function dkStart(draftId) {
  dkStop();
  const st = document.getElementById("dk-status");
  st.textContent = "CONNECTING…"; st.style.color = "var(--warn)";
  document.getElementById("dk-disconnect").classList.remove("ff-hidden");
  const tick = async () => {
    // The page owns the loop, so leaving the view must end it.
    if (state.view !== "fantasy") { dkStop(); return; }
    let picks;
    try {
      picks = await sleeperGet("draft/" + draftId + "/picks");
    } catch (e) {
      st.textContent = "DRAFT UNREACHABLE"; st.style.color = "var(--bad)";
      return;                            // transient — next tick retries
    }
    const taken = new Set((picks || []).map((p) =>
      ffNorm(`${(p.metadata || {}).first_name || ""} ${(p.metadata || {}).last_name || ""}`))
      .filter((n) => n));
    st.textContent = `LIVE · ${taken.size} PICKED`; st.style.color = "var(--good)";
    document.querySelectorAll("[data-ffp]").forEach((el) =>
      el.classList.toggle("dk-taken", taken.has(el.dataset.ffp)));
    dkBestAvailable(taken);
  };
  tick();
  dkState.timer = setInterval(tick, 12000);
}

function dkBestAvailable(taken) {
  const host = document.getElementById("dk-best");
  if (!host || !dkState.kit) return;
  host.classList.remove("ff-hidden");
  const avail = dkState.kit.board.filter((r) => !taken.has(ffNorm(r.player)));
  const top = avail.slice(0, 5);
  const byPos = {};
  for (const r of avail) if (!byPos[r.position]) byPos[r.position] = r;
  host.innerHTML = `
    <div class="dk-bestrow"><span class="dk-bl">Best available</span>
      ${top.map((r) => `<span class="chip up">${escapeHtml(r.player)} · +${r.vorp}</span>`).join("")}</div>
    <div class="dk-bestrow"><span class="dk-bl">By position</span>
      ${["QB", "RB", "WR", "TE"].map((p) => byPos[p]
        ? `<span class="chip">${p}: ${escapeHtml(byPos[p].player)} (+${byPos[p].vorp})</span>` : "")
        .join("")}</div>`;
}

/* One box that answers the only question that matters on this page: "so
   what are you telling me to DO?" The answer is driven by the measured
   record, with the promotion bar stated up front — no vibes. */
function pmSignalProven(v) {
  return !!(v && v.graded >= 100 && v.z >= 2 && v.roi > 0);
}

function intelVerdict(v) {
  const pctv = (x) => `${(x * 100).toFixed(1)}%`;
  const body = pmSignalProven(v)
    ? `<div style="font-weight:800;font-size:var(--fs-xl);color:var(--good)">${icon('check')} The signal has earned
         recommendation status</div>
       <p style="margin:8px 0 0">Graded flags beat their entry prices over ${v.graded} resolutions
       (hit ${pctv(v.hit_rate)} vs ${pctv(v.avg_implied)} implied, ${v.roi >= 0 ? "+" : ""}${pctv(v.roi)} ROI,
       z ${v.z}). Following a fresh LIVE flag below — same side, at or better than the flagged
       entry price — is now a recommended play, sized small (flat 0.1u).</p>`
    : `<div style="font-weight:800;font-size:var(--fs-xl)">${iconMark("target", 16)}What we recommend right now: <span style="color:var(--warn)">nothing — watch, don't bet</span></div>
       <p style="margin:8px 0 0">This page detects large anomalous trades ("informed flow") and
       <b>paper-tracks every flag</b> to find out whether following that money actually wins.
       ${v && v.graded
         ? `So far, over <b>${v.graded}</b> graded flags: hit ${pctv(v.hit_rate)} vs ${pctv(v.avg_implied)}
            implied, ${v.roi >= 0 ? "+" : ""}${pctv(v.roi)} flat-stake ROI, z ${v.z} — statistically
            indistinguishable from the market price. Not enough to bet on.`
         : `No flags have resolved yet, so there is no evidence either way.`}</p>
       <p style="margin:6px 0 0;color:var(--text-mute)">The promotion bar is fixed and public:
       <b>100+ graded flags, z ≥ 2, positive ROI</b>. If the signal (or one wallet, or one
       score band) clears it, this box flips to a recommendation. Until then, every flag below
       is a tracked observation — not a play.</p>`;
  return `<div class="card" style="margin-bottom:16px;border-left:3px solid ${pmSignalProven(v) ? "var(--good)" : "var(--warn)"}">${body}</div>`;
}

function intelReportCard(v) {
  const head = `<div class="section-title">Flag report card
      <span class="sub">— do our flags actually win? Every flag is stored and graded when
      its market resolves. Published, not promised.</span></div>`;
  if (!v || !v.graded) {
    return `${head}<div class="card"><p class="loading" style="margin:0">No graded flags yet —
      flags settle when their markets resolve, so this fills as resolutions land.
      The recording started the moment the flow feed first ran.</p></div>`;
  }
  const pctv = (x) => `${(x * 100).toFixed(1)}%`;
  const zColor = v.z >= 1 ? "var(--good)" : v.z <= -1 ? "var(--bad)" : "var(--text)";
  const bands = (v.by_score || []).map((b) => `
    <div class="dl-row pm-band">
      <span class="dl-main"><strong>Score ${escapeHtml(b.band)}</strong></span>
      <span class="dl-num">${b.wins}-${b.n - b.wins}</span>
      <span class="dl-num implied">${pctv(b.hit_rate)} vs ${pctv(b.avg_implied)} implied</span>
      <span class="dl-num strong ${b.roi >= 0 ? "pos" : "neg"}">${b.roi >= 0 ? "+" : ""}${pctv(b.roi)} ROI</span>
    </div>`).join("");
  const wallets = (v.wallets || []).map((w) => `
    <div class="dl-row pm-wallet">
      <span class="dl-main"><a class="wallet" href="https://polymarket.com/profile/${escapeHtml(w.wallet)}" target="_blank"
        rel="noopener" style="color:inherit;font-weight:600">${escapeHtml(traderLabel(w))}</a></span>
      <span class="dl-num">${w.wins}-${w.n - w.wins}</span>
      <span class="dl-num implied">${pctv(w.hit_rate)} vs ${pctv(w.avg_implied)}</span>
      <span class="dl-num strong" title="calibration z — higher = less like luck">z ${w.z}</span>
    </div>`).join("");
  return `${head}
    <div class="stats">
      <div class="tile"><div class="k">Flags graded</div><div class="v">${v.graded}</div></div>
      <div class="tile"><div class="k">Hit rate</div><div class="v">${pctv(v.hit_rate)}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">prices implied ${pctv(v.avg_implied)}</div></div>
      <div class="tile"><div class="k">Flat-stake ROI</div><div class="v ${v.roi >= 0 ? "pos" : ""}">${v.roi >= 0 ? "+" : ""}${pctv(v.roi)}</div></div>
      <div class="tile"><div class="k">Calibration z</div><div class="v" style="color:${zColor}">${v.z}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">above 0 = flags beat their price</div></div>
    </div>
    ${bands ? `<div class="card" style="padding:0">${bands}</div>` : ""}
    ${wallets ? `<div class="section-title">Wallets least like luck
        <span class="sub">— graded flags only, min 3, ranked by calibration z</span></div>
      <div class="card" style="padding:0">${wallets}</div>` : ""}`;
}

/* ---------------- Sleeper league sync (free, read-only, no key) ---------- */
function ffNorm(s) {
  return String(s || "").toLowerCase().normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").replace(/[.'’`-]/g, " ")
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "").replace(/\s+/g, " ").trim();
}

async function sleeperGet(path) {
  const r = await fetch("/api/sleeper/" + path);
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error((body && body.error) || `Sleeper request failed (${r.status})`);
  return body;
}

function sleeperConnectHTML(msg) {
  return `<div class="card" style="margin-bottom:16px">
    <div class="card-head"><div><div class="player">My league — Sleeper sync</div>
      <div class="subtitle">Free and read-only: see YOUR roster's usage trends, trade flags,
        and who's unrostered in YOUR league. No password — just your Sleeper username.</div></div></div>
    <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
      <input id="sleeper-username" type="text" placeholder="Sleeper username"
        style="flex:1;min-width:180px;background:var(--panel-2);color:inherit;
        border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
      <button class="btn" id="sleeper-connect">Connect</button>
    </div>
    ${msg ? `<div class="warning" style="margin-top:10px">${icon('warn')} ${escapeHtml(msg)}</div>` : ""}
  </div>`;
}

async function renderSleeperZone(d, errMsg) {
  const zone = document.getElementById("sleeper-zone");
  if (!zone) return;
  const username = localStorage.getItem("ff_user");
  if (!username) {
    zone.innerHTML = sleeperConnectHTML(errMsg);
    const btn = document.getElementById("sleeper-connect");
    if (btn) btn.addEventListener("click", () => {
      const v = (document.getElementById("sleeper-username").value || "").trim();
      if (!v) return;
      localStorage.setItem("ff_user", v);
      renderSleeperZone(d);
    });
    return;
  }
  zone.innerHTML = `<p class="loading">Syncing ${escapeHtml(username)}'s Sleeper leagues…</p>`;
  try {
    const user = await sleeperGet(`user/${encodeURIComponent(username)}`);
    if (!user || !user.user_id) throw new Error(`No Sleeper user named “${username}”`);
    let seasonTried = new Date().getFullYear();
    let leagues = await sleeperGet(`user/${user.user_id}/leagues/nfl/${seasonTried}`) || [];
    if (!leagues.length) {
      seasonTried -= 1;
      leagues = await sleeperGet(`user/${user.user_id}/leagues/nfl/${seasonTried}`) || [];
    }
    if (!leagues.length) throw new Error("No NFL leagues found on that account");
    let leagueId = localStorage.getItem("ff_league");
    if (!leagues.some((l) => l.league_id === leagueId)) leagueId = leagues[0].league_id;
    const [rosters, lgUsers] = await Promise.all([
      sleeperGet(`league/${leagueId}/rosters`),
      sleeperGet(`league/${leagueId}/users`),
    ]);
    if (!window._slPlayers) window._slPlayers = await sleeperGet("players/nfl");
    renderSleeperPanel(d, { username, user, leagues, leagueId, rosters,
                            lgUsers, seasonTried });
  } catch (e) {
    localStorage.removeItem("ff_user");
    renderSleeperZone(d, String(e.message || e));
  }
}

function renderSleeperPanel(d, ctx) {
  const zone = document.getElementById("sleeper-zone");
  const players = window._slPlayers || {};
  const usageByName = {};
  (d.usage || []).forEach((u) => { usageByName[ffNorm(u.player)] = u; });
  const flagByName = {};
  ((d.buy_sell || {}).buy_low || []).forEach((r) => { flagByName[ffNorm(r.player)] = "BUY LOW"; });
  ((d.buy_sell || {}).sell_high || []).forEach((r) => { flagByName[ffNorm(r.player)] = "SELL HIGH"; });

  const mine = (ctx.rosters || []).find((r) => r.owner_id === ctx.user.user_id
    || (r.co_owners || []).includes(ctx.user.user_id));
  const takenNames = new Set();
  (ctx.rosters || []).forEach((r) => (r.players || []).forEach((pid) => {
    const p = players[pid];
    if (p) takenNames.add(ffNorm(`${p.first_name} ${p.last_name}`));
  }));

  const pct = (v) => v == null ? "—" : `${(v * 100).toFixed(0)}%`;
  const POS_ORDER = { QB: 0, RB: 1, WR: 2, TE: 3, K: 4, DEF: 5 };
  const myRows = (mine ? (mine.players || []) : []).map((pid) => {
    const p = players[pid];
    if (!p || !["QB", "RB", "WR", "TE"].includes(p.position)) return null;
    const name = `${p.first_name} ${p.last_name}`;
    const u = usageByName[ffNorm(name)];
    const flag = flagByName[ffNorm(name)];
    return { name, pos: p.position, team: p.team || "", u, flag,
             starter: (mine.starters || []).includes(pid) };
  }).filter(Boolean).sort((a, b) =>
    (POS_ORDER[a.pos] ?? 9) - (POS_ORDER[b.pos] ?? 9)
    || (b.u ? b.u.fp_pg : 0) - (a.u ? a.u.fp_pg : 0));

  const rowHTML = (r) => `
    <div class="drow" style="display:flex;align-items:center;gap:12px;padding:8px 16px;
        border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="flex:0 0 auto">${playerAvatar(r.name, r.team, { map: nflMap() })}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        <strong>${escapeHtml(r.name)}</strong>
        <span style="color:var(--text-mute)"> ${escapeHtml(r.pos)} · ${escapeHtml(r.team || "FA")}${r.starter ? " · starter" : ""}</span>
        ${r.flag ? `<span class="chip ${r.flag === "BUY LOW" ? "up" : "down"}" style="margin-left:6px">${r.flag}</span>` : ""}</span>
      ${r.u ? `<span style="min-width:150px;text-align:right;color:var(--text-dim)"
          title="season · 4-week · last week ${r.u.metric}">${pct(r.u.season)} → ${pct(r.u.l4)} → <b>${pct(r.u.last)}</b></span>
        <span style="min-width:70px;text-align:right;color:var(--text-mute)">${r.u.fp_pg} ppg</span>`
      : `<span style="min-width:220px;text-align:right;color:var(--text-mute)">not among the top usage movers</span>`}
    </div>`;

  const waivers = (d.usage || []).filter((u) =>
    (u.delta || 0) >= 0.03 && !takenNames.has(ffNorm(u.player))).slice(0, 8);

  const leagueOpts = ctx.leagues.map((l) =>
    `<option value="${escapeHtml(l.league_id)}" ${l.league_id === ctx.leagueId ? "selected" : ""}>
       ${escapeHtml(l.name || l.league_id)}</option>`).join("");

  zone.innerHTML = `<div class="card" style="margin-bottom:16px;padding-bottom:6px">
    <div class="card-head">
      <div><div class="player">My league — ${escapeHtml(ctx.username)}</div>
        <div class="subtitle">Sleeper · season ${ctx.seasonTried} · roster read-only</div></div>
      <div style="display:flex;gap:8px;align-items:center">
        <select id="sleeper-league" style="background:var(--panel-2);color:inherit;
          border:1px solid var(--border);border-radius:var(--radius);padding:7px 10px;font-family:inherit">${leagueOpts}</select>
        <button class="btn ghost" id="sleeper-disconnect">Disconnect</button>
      </div>
    </div>
    <div class="section-title">My roster
      <span class="sub">— usage trend (season → 4wk → last) and trade flags for YOUR players</span></div>
    <div style="margin:0 -18px">${myRows.map(rowHTML).join("") ||
      `<p class="loading" style="padding:12px 16px">Couldn't match a roster you own in this league.</p>`}</div>
    <div class="section-title">Waiver watch
      <span class="sub">— usage RISERS nobody in this league rosters</span></div>
    <div style="margin:0 -18px">${waivers.map((u) => rowHTML({
        name: u.player, pos: u.position, team: u.team, u, flag: flagByName[ffNorm(u.player)] })).join("") ||
      `<p class="loading" style="padding:12px 16px">Every notable riser is already rostered here.</p>`}</div>
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin:10px 2px 8px">Boards use PPR scoring;
      custom-scoring recompute lands with the in-season update.</p>
  </div>`;

  const sel = document.getElementById("sleeper-league");
  if (sel) sel.addEventListener("change", () => {
    localStorage.setItem("ff_league", sel.value);
    renderSleeperZone(d);
  });
  const dis = document.getElementById("sleeper-disconnect");
  if (dis) dis.addEventListener("click", () => {
    localStorage.removeItem("ff_user");
    localStorage.removeItem("ff_league");
    renderSleeperZone(d);
  });
}

/* ============================================================
   NBA — Scalpy probability engine
   ============================================================ */
/* Weigh-in state for one bout. "Not recorded" is drawn as its own thing
   on purpose: it and "made weight" are opposite facts, and a page that
   renders them the same way is the reason KILL IF went unenforced. */
function weighInHTML(wi) {
  if (!wi || (!wi.a && !wi.b)) return "";
  const one = (st) => {
    if (!st) return "";
    const n = escapeHtml(st.name || "?");
    if (st.state === "missed") {
      return `<span class="chip down">${n} ${icon('cross')} ${st.weight} (+${st.over} over)</span>`;
    }
    if (st.state === "made") return `<span class="chip up">${n} ${icon('check')} ${st.weight}</span>`;
    if (st.state === "unknown_division") {
      return `<span class="chip">${n} ${st.weight} · catchweight, no limit</span>`;
    }
    return `<span class="chip">${n} — weigh-in not recorded</span>`;
  };
  return `<div class="chips" style="margin-top:8px">${one(wi.a)}${one(wi.b)}</div>`;
}

/* ============================================================
   Live fight — the body diagram
   ============================================================
   The UFC's broadcast graphic is not a damage model. It is a count of
   significant strikes landed to each target area, and that distinction
   is the whole design: "damage" is a judgement nobody publishes, strikes
   to the head is a number somebody counts. Shaded by SHARE of what a
   fighter has absorbed — the deepest colour is where he is being hit
   most, which is what a viewer actually reads off it.

   The diagram shows what a fighter has TAKEN. His own landed strikes
   appear on his opponent. Getting that backwards would invert the whole
   picture while looking completely normal. */
let _liveTimer = null;

const BODY_REGIONS = [
  ["head", "Head"], ["body", "Body"], ["leg", "Legs"],
];

/* Intensity is a region's count against the HOTTEST region in the fight
   — across both fighters, so the two diagrams are directly comparable.

   Share-of-own-total was the first attempt and it was quietly useless: a
   fighter hit evenly in three places scores ~33% everywhere and comes out
   uniformly mid-red, so a man taking 41 to the head looked like a man
   taking 7 to the leg. Normalising to the fight's peak means the worst
   area on the card is the deepest colour and everything else reads
   against it, which is the comparison a viewer is actually making.

   Zero absorbed is not "safe", it is "nothing landed yet" — so an untouched
   diagram is flat panel colour rather than green. Colour never means good. */
function regionFill(n, peak) {
  if (!peak || n == null) return "var(--panel-3)";
  if (!n) return "var(--panel-3)";
  const a = 0.14 + Math.min(1, n / peak) * 0.76;
  return `rgba(239, 68, 68, ${a.toFixed(3)})`;
}

function bodySVG(absorbed, total, peak) {
  const share = (k) => (total > 0 ? (absorbed[k] || 0) / total : null);
  const seg = (k, d) => `<path d="${d}" fill="${regionFill(absorbed[k] || 0, peak)}"
      stroke="var(--border)" stroke-width="1.2"><title>${escapeHtml(
        BODY_REGIONS.find((r) => r[0] === k)[1])}: ${absorbed[k] || 0} landed${
        total > 0 ? ` (${Math.round((share(k) || 0) * 100)}%)` : ""}</title></path>`;
  return `<svg class="bodyfig" viewBox="0 0 100 200" role="img"
      aria-label="Significant strikes absorbed by target area">
    ${seg("head", "M50 6 c9 0 15 7 15 16 c0 10 -6 18 -15 18 c-9 0 -15 -8 -15 -18 c0 -9 6 -16 15 -16 Z")}
    ${seg("body", "M35 44 c-9 3 -14 9 -16 20 l-4 26 c-1 6 6 8 8 2 l4 -16 l1 34 c0 8 1 14 2 20 h60 c1 -6 2 -12 2 -20 l1 -34 l4 16 c2 6 9 4 8 -2 l-4 -26 c-2 -11 -7 -17 -16 -20 c-6 -2 -12 -3 -25 -3 c-13 0 -19 1 -25 3 Z")}
    ${seg("leg", "M30 132 c-1 22 -2 44 -4 60 c-1 6 12 6 13 0 l7 -44 l7 44 c1 6 14 6 13 0 c-2 -16 -3 -38 -4 -60 Z")}
  </svg>`;
}

function fighterPanelHTML(f, peak) {
  const abs = f.absorbed || {}, total = f.absorbed_total || 0;
  const rows = BODY_REGIONS.map(([k, label]) => {
    const n = abs[k] || 0;
    // The BAR is share of this fighter's own total — "where is he being
    // hit" — while the FIGURE is scaled to the fight's peak — "how hard,
    // compared to the other guy". Two questions, two encodings, and the
    // count on the right is the answer to neither being in doubt.
    const pct = total > 0 ? Math.round((n / total) * 100) : 0;
    return `<div class="lf-region">
      <span class="lf-region-name">${escapeHtml(label)}</span>
      <span class="lf-bar"><span style="width:${pct}%;
        background:${regionFill(n, peak)}"></span></span>
      <span class="lf-region-n">${n}</span>
    </div>`;
  }).join("");
  const t = f.totals || {};
  const chip = (label, v) => (v == null ? "" :
    `<span class="chip">${escapeHtml(label)} ${v}</span>`);
  return `<div class="lf-fighter">
    <div class="lf-name">${escapeHtml(f.name || "—")}${
      f.winner ? ` <span class="chip good">WINNER</span>` : ""}</div>
    ${bodySVG(abs, total, peak)}
    <div class="lf-absorbed">${total} significant strike${total === 1 ? "" : "s"} absorbed</div>
    ${rows}
    <div class="lf-chips">
      ${chip("landed", f.landed_total)}
      ${chip("of", t.sig_attempted)}
      ${chip("TD", t.takedowns)}
      ${chip("KD", t.knockdowns)}
    </div>
  </div>`;
}

function liveBoutHTML(b, stale) {
  const s = b.status || {};
  const badge = s.live
    ? `<span class="chip ${stale ? "warn" : "live"}">${stale ? "STALLED" : "LIVE"}${
        s.round ? ` · R${s.round}` : ""}${s.clock ? ` ${escapeHtml(s.clock)}` : ""}</span>`
    : `<span class="chip">${escapeHtml(s.detail || s.state || "")}</span>`;
  if (!b.has_targets) {
    return `<div class="card lf-card">
      <div class="lf-head">${escapeHtml(b.fighters.map((f) => f.name).join(" vs "))} ${badge}</div>
      <div class="ls-note">This bout is live, but the feed is not publishing
      strikes by target for it — so there is no body diagram to draw. Totals
      appear here as soon as it does. A diagram of zeros would look like a
      fight where nothing has landed, which is a different claim entirely.</div>
    </div>`;
  }
  // The hottest single region across BOTH corners sets the scale, so the
  // two figures can be read against each other rather than each against
  // itself.
  const peak = Math.max(1, ...b.fighters.flatMap(
    (f) => BODY_REGIONS.map(([k]) => (f.absorbed || {})[k] || 0)));
  return `<div class="card lf-card">
    <div class="lf-head">${escapeHtml(b.division || "")} ${badge}</div>
    <div class="lf-pair">${b.fighters.map((f) => fighterPanelHTML(f, peak)).join("")}</div>
  </div>`;
}

async function renderLiveFights(host) {
  if (!host) return false;
  let d = null;
  try {
    const res = await fetch("data/ufc_live.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d || !(d.bouts || []).length) { host.innerHTML = ""; return false; }

  const live = (d.bouts || []).filter((b) => b.status && b.status.live);
  if (!live.length) { host.innerHTML = ""; return false; }

  // Age of the DATA, not of the fetch. A count that last moved 90 seconds
  // ago is 90 seconds old however recently we asked for it, and a smoothly
  // redrawn stale number next to a fight somebody is watching is the worst
  // thing this page could do.
  const built = Date.parse(d.generated_at || "") || 0;
  const ageS = built ? Math.max(0, Math.round((Date.now() - built) / 1000)) : null;
  const stale = ageS != null && ageS > (d.stale_after_s || 75);

  host.innerHTML = `
    <div class="section-title tight">Live now
      <span class="sub">— ${escapeHtml(d.disclaimer || "")}</span></div>
    <div class="lf-age ${stale ? "warn" : ""}">${
      ageS == null ? "" : stale
        ? `${icon('warn')} these numbers last changed ${ageS}s ago — the feed has stopped moving`
        : `updated ${ageS}s ago`}</div>
    ${live.map((b) => liveBoutHTML(b, stale)).join("")}
    ${/* Each card already explains its own missing-target case, so the
          payload-level note would just say it a second time. Keep it only
          when it is telling you something the cards did not. */
      d.note && live.some((b) => b.has_targets)
        ? `<div class="ls-note">${escapeHtml(d.note)}</div>` : ""}`;
  return true;
}

async function renderUFC() {
  const host = document.getElementById("ufc-body");
  if (!host) return;
  // A live fight refreshes on its own clock — the 60s page cycle is far
  // too slow for something that moves in seconds. The timer is cleared on
  // the way out of the view so it cannot keep polling a page nobody is on.
  let liveHost = document.getElementById("ufc-live");
  if (!liveHost) {
    liveHost = document.createElement("div");
    liveHost.id = "ufc-live";
    host.parentNode.insertBefore(liveHost, host);
  }
  renderLiveFights(liveHost);
  if (_liveTimer) clearInterval(_liveTimer);
  _liveTimer = setInterval(() => {
    if (state.view !== "ufc") { clearInterval(_liveTimer); _liveTimer = null; return; }
    renderLiveFights(liveHost);
  }, 10000);
  let d = null;
  try {
    const res = await fetch("data/ufc.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  if (!d) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("glove", 30)}</div>
      <div class="es-title">No UFC data yet</div>
      <div class="es-sub">The launcher builds the card each refresh once you pull and relaunch.</div></div>`;
    return;
  }
  setStandaloneSource("The Odds API MMA events + our fighter dossiers",
                      `UFC · ${escapeHtml(d.event_date || d.status || "")}`);
  const pctv = (x) => x == null ? "—" : `${(x * 100).toFixed(1)}%`;

  if (d.status !== "card") {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("glove", 30)}</div>
      <div class="es-title">No card in the window</div>
      <div class="es-sub">${escapeHtml(d.note || "")}</div></div>
      <div class="ls-note" style="margin-top:14px">The Scalpy MMA doctrine, ready:
        style beats talent (highest-weight input) · win probability hard-capped at 88% —
        four-ounce gloves mean nobody is safer · method of victory is a JOINT distribution
        that must sum to 100% · durability weighs 1.5× finishing ability · the humility
        clamp kills any 15-point market disagreement · never worse than −300 · no cap on how
        many fights qualify — money is capped instead, and a 13-fight card with zero bets is
        a valid output.</div>`;
    return;
  }

  const methodBar = (m) => {
    const segs = [["a_ko", "var(--bad)"], ["a_sub", "var(--plum)"],
                  ["a_dec", "var(--brand)"], ["b_dec", "var(--cyan)"],
                  ["b_sub", "var(--warn)"], ["b_ko", "var(--good)"]];
    return `<div style="display:flex;height:10px;border-radius:var(--radius);overflow:hidden;margin-top:8px"
        title="method distribution — left: pick's KO/SUB/DEC, right: opponent's DEC/SUB/KO">
      ${segs.map(([k, c]) => `<span style="width:${(m[k] || 0) * 100}%;background:${c}"></span>`).join("")}
    </div>
    <div style="display:flex;justify-content:space-between;color:var(--text-mute);font-size:var(--fs-xs);margin-top:3px">
      <span>KO ${pctv(m.a_ko)} · SUB ${pctv(m.a_sub)} · DEC ${pctv(m.a_dec)}</span>
      <span>distance ${pctv(m.distance)}</span></div>`;
  };

  /* The bet is no longer always the moneyline. Books derive method props
     off the moneyline, so the distribution routinely finds its edge in a
     market the book barely thought about — the card has to say WHICH. */
  const MARKET_LABEL = { moneyline: "Moneyline", method: "Method",
                         distance: "Distance", fighter_finish: "Finish",
                         round: "Round", exact_round: "Exact round" };
  const shopRow = (c) => `
    <div class="ufc-shop-row">
      <span class="sr-m">${escapeHtml(MARKET_LABEL[c.market] || c.market)}</span>
      <span class="sr-s">${escapeHtml(c.selection)}</span>
      <span class="sr-o">${c.priced ? american(c.odds) : `fair ${american(c.fair_odds)}`}</span>
      <span class="sr-e ${c.priced ? (c.edge >= c.required_edge ? "pos" : "") : "mute"}">${
        c.priced ? `${c.edge >= 0 ? "+" : ""}${(c.edge * 100).toFixed(1)}%` : "shop it"}</span>
    </div>`;

  const pickCard = (p) => {
    const best = p.best_market || {};
    const shown = best.odds != null ? best.odds : p.odds;
    const title = p.selection || `${p.pick} ML`;
    const board = (p.market_board || []).filter((c) => c.priced || c.fair_odds);
    return `
    <article class="card" style="--grade-color:var(--good)">
      <div class="card-head">
        <div><div class="player">${escapeHtml(title)}</div>
          <div class="subtitle">${escapeHtml(p.fight)}${p.division ? ` · ${escapeHtml(p.division)}` : ""} ·
            ${escapeHtml(p.book)} ${american(shown)}</div></div>
        <span class="pm-status" style="color:var(--good)">${escapeHtml(p.grade_label || "")} ${p.grade_score != null ? p.grade_score : ""}</span>
      </div>
      <div class="chips" style="margin:2px 0 8px">
        <span class="chip">${escapeHtml(MARKET_LABEL[p.market] || p.market || "moneyline")} · tier ${p.market_tier || 1}</span>
        <span class="chip cond">${escapeHtml(p.volatility || "MEDIUM")} volatility</span>
        ${p.thin_data ? `<span class="chip" style="color:var(--warn);border-color:currentColor">thin data — higher bar</span>` : ""}
      </div>
      <div class="metrics">
        <div class="metric"><div class="k">p_model</div><div class="v">${pctv(p.p_model)}</div></div>
        <div class="metric"><div class="k">p_market</div><div class="v">${pctv(p.p_market)}</div></div>
        <div class="metric primary"><div class="k">p_final (w=${p.w})</div><div class="v">${pctv(p.p_final)}</div></div>
      </div>
      <div class="metrics" style="margin-top:6px">
        <div class="metric"><div class="k">Break-even</div><div class="v">${pctv(p.break_even)}</div></div>
        <div class="metric"><div class="k">Edge</div><div class="v pos">+${(p.edge * 100).toFixed(1)}pts</div></div>
        <div class="metric primary"><div class="k">EV</div><div class="v pos">+${(p.ev * 100).toFixed(1)}%</div></div>
      </div>
      ${methodBar(p.method || {})}
      <div style="margin-top:8px;color:var(--text-body);font-size:var(--fs-sm)">
        ${(p.style_notes || []).map(escapeHtml).join(" · ")} · hold ${(p.hold * 100).toFixed(1)}%
        · stake ${p.stake_units}u${p.required_edge ? ` · needs ${(p.required_edge * 100).toFixed(1)}%` : ""}</div>
      ${(p.environment && (p.environment.why || []).length)
        ? `<div style="margin-top:6px;color:var(--text-mute);font-size:var(--fs-sm)">${icon('stadium')} ${
            escapeHtml([(p.environment.cage || {}).note, (p.environment.altitude || {}).note]
              .filter(Boolean).join(" · "))}</div>` : ""}
      ${board.length ? `<details class="ufc-shop"><summary>Every market this fight implies (${board.length}) — shop the unpriced ones</summary>
        ${board.map(shopRow).join("")}</details>` : ""}
      ${weighInHTML(p.weigh_in)}
      <div class="warning" style="margin-top:8px">KILL IF: ${escapeHtml(p.kill_if)}</div>
    </article>`;
  };

  // A passed fight still shows both corners — the matchup is the whole
  // point of the page, and an unbet fight you can read is far more useful
  // than a one-line "no bet".
  const fmt = (v, suffix = "") => v == null ? "—" : `${v}${suffix}`;
  const fighterCol = (f) => {
    const flags = (f.red_flags || []).map((x) =>
      `<span class="chip" style="color:var(--bad);border-color:currentColor"
         title="${escapeHtml(x)}">${iconMark("warn", 11)}${escapeHtml(x.split("—")[0].trim())}</span>`).join("");
    const stats = f.covered
      ? `${fmt(f.slpm)}/${fmt(f.sapm)} strikes · TDD ${f.tdd == null ? "—" : (f.tdd * 100).toFixed(0) + "%"}
         · TD ${fmt(f.td_per15)}/15`
      : `<span style="color:var(--warn)">no tracked fight stats</span>`;
    return `<div class="ufc-corner">
      <div class="fc-name">${escapeHtml(f.name)}</div>
      <div class="fc-meta">${f.record ? escapeHtml(f.record) : "—"}${f.age ? ` · ${f.age}y` : ""}
        ${f.archetype ? ` · ${escapeHtml(f.archetype.replace(/_/g, " "))}` : ""}</div>
      <div class="fc-stats">${stats}</div>
      <div class="fc-cover">stats for ${f.covered || 0}${f.career ? ` of ${f.career}` : ""} fights</div>
      ${flags ? `<div style="margin-top:5px">${flags}</div>` : ""}
    </div>`;
  };

  const REASON_STYLE = {
    no_data: ["var(--warn)", "No data"],
    no_dossier: ["var(--warn)", "No dossier"],
    no_price: ["var(--text-mute)", "Awaiting price"],
    clamp_kill: ["var(--bad)", "Clamp kill"],
    gate: ["var(--cyan)", "No edge"],
  };

  const passCard = (m) => {
    const [color, label] = REASON_STYLE[m.reason_code] || ["var(--text-mute)", "Pass"];
    const fs = m.fighters || [];
    return `<article class="card" style="--grade-color:${color};padding:14px 16px">
      <div class="card-head" style="align-items:flex-start">
        <div><div class="player" style="font-size:var(--fs-lg)">${escapeHtml(m.fight)}</div>
          <div class="subtitle">${escapeHtml((m.division || "").replace(/_/g, " ") || "division n/a")}
            ${m.odds ? ` · ${escapeHtml(m.book || "")} ${american(m.odds)}` : ""}</div></div>
        <span class="pm-status" style="color:${color}">${m.near_miss ? "NEAR MISS" : label}</span>
      </div>
      <div class="ufc-vs">
        ${fs.map(fighterCol).join(`<span class="vs-sep">vs</span>`)}
      </div>
      ${m.p_final != null ? `<div class="metrics" style="margin-top:10px">
        <div class="metric"><div class="k">p_model</div><div class="v">${pctv(m.p_model)}</div></div>
        <div class="metric"><div class="k">p_market</div><div class="v">${pctv(m.p_market)}</div></div>
        <div class="metric primary"><div class="k">p_final</div><div class="v">${pctv(m.p_final)}</div></div>
      </div>` : ""}
      <div style="margin-top:10px;color:var(--text-body);font-size:var(--fs-sm)">
        <span style="color:${color};font-weight:700">Passed:</span> ${escapeHtml(m.why || "")}</div>
    </article>`;
  };

  const c = d.counts || {};
  const pl = d.pass_list || [];
  const nModeled = pl.filter((m) => ["gate", "clamp_kill"].includes(m.reason_code)).length
    + (d.picks || []).length;
  const nWaiting = pl.filter((m) => m.reason_code === "no_price").length;
  host.innerHTML = `
    <div class="stats">
      <div class="tile"><div class="k">Card</div><div class="v">${escapeHtml(d.event_date || "")}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${c.fights || 0} bouts</div></div>
      <div class="tile"><div class="k">Modeled</div><div class="v">${nModeled}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">priced &amp; run through the model</div></div>
      <div class="tile"><div class="k">Awaiting prices</div><div class="v">${nWaiting}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">books post MMA lines late</div></div>
      <div class="tile"><div class="k">Picks</div><div class="v">${c.picks || 0}</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">every fight that clears the bar</div></div>
      <div class="tile"><div class="k">Card exposure</div><div class="v">${((d.exposure || 0) * 100).toFixed(1)}%</div>
        <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">of bankroll · cap ${((d.card_cap || 0.08) * 100).toFixed(0)}%,
          the tightest in the system</div></div>
    </div>
    ${(d.correlation_flags || []).length ? `<div class="card" style="border-left:3px solid var(--warn);margin-bottom:12px">
        <div class="player">${icon('warn')} Correlation on this card</div>
        <ul class="reasons">${(d.correlation_flags || []).map((f) =>
          `<li class="neg">${escapeHtml(f)}</li>`).join("")}</ul></div>` : ""}
    ${d.card_venue && d.card_venue.venue
      ? `<div class="ls-note" style="margin-bottom:12px">${icon('stadium')} ${escapeHtml(d.card_venue.venue)}${
          d.card_venue.city ? `, ${escapeHtml(d.card_venue.city)}` : ""} — cage size and altitude
          are applied to every method and distance price on this card.</div>`
      : `<div class="ls-note" style="margin-bottom:12px">${icon('stadium')} Venue not set, so cage size and altitude
          are unchecked — a 25-foot cage raises finishes and altitude pushes them later.
          Set it with <code>python3 launch.py --card-venue "UFC Apex" "Las Vegas"</code>.</div>`}
    ${(() => {
      // Fight-by-fight edge table: every PRICED bout on one scannable
      // grid — model vs market vs break-even, and the verdict with its
      // reason. The per-fight cards below carry the depth.
      const rows = [...(d.picks || []).map((p) => ({ ...p, _pick: true })),
                    ...(d.pass_list || []).filter((m) => m.p_final != null)];
      if (!rows.length) return "";
      return `<div class="section-title">Fight-by-fight edge board
          <span class="sub">— every priced bout: the model's number vs the market's, and
          the verdict. Bet rows are journaled in the UFC record.</span></div>
        <div class="card" style="padding:0;overflow-x:auto;overflow-y:hidden">
          ${rows.map((r) => `
            <div class="ufc-edge-row" style="display:flex;gap:12px;align-items:center;padding:10px 14px;
                        border-bottom:1px solid rgba(255,255,255,.05);min-width:640px;
                        ${r._pick ? "" : "opacity:.72"}">
              <span style="min-width:74px;text-align:center;font-weight:800;flex-shrink:0;
                    color:${r._pick ? "var(--good)" : "var(--text-mute)"}">${r._pick ? "BET" : "PASS"}</span>
              <span style="flex:1;min-width:0"><strong>${escapeHtml(r.fight)}</strong>
                <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">
                  ${r._pick ? `${escapeHtml(r.selection || (r.pick + " ML"))} ${american((r.best_market || {}).odds != null ? r.best_market.odds : r.odds)} (${escapeHtml(r.book || "")}) · stake ${r.stake_units}u`
                            : escapeHtml(r.why || "")}</span></span>
              <span style="text-align:right;white-space:nowrap;font-size:var(--fs-sm)">
                model ${pctv(r.p_final)} · market ${pctv(r.p_market)}
                <span style="display:block;color:${(r.edge || 0) > 0 ? "var(--good)" : "var(--text-mute)"};font-weight:700">
                  ${r.edge != null ? `${r.edge >= 0 ? "+" : ""}${(r.edge * 100).toFixed(1)}pts vs break-even` : ""}</span></span>
            </div>`).join("")}
        </div>`;
    })()}
    ${await (async () => {
      // The UFC record — this card's picks are graded here after the
      // fights, same probation-bucket pattern as every new signal.
      const rec = await loadRecordOnce();
      const u = rec.ufc_record || {};
      if (!u.settled && !u.open) return "";
      const graded = (u.wins || 0) + (u.losses || 0);
      return `<div class="section-title">UFC record
          <span class="sub">— every journaled pick, graded from fight results after each card.
          Its own bucket until it earns more.</span></div>
        <div class="stats">
          <div class="tile"><div class="k">Record</div><div class="v">${u.wins || 0}-${u.losses || 0}</div>
            <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${u.open || 0} open</div></div>
          <div class="tile"><div class="k">Flat ROI</div><div class="v ${(u.roi || 0) >= 0 ? "pos" : "neg"}">
            ${(u.roi || 0) >= 0 ? "+" : ""}${((u.roi || 0) * 100).toFixed(1)}%</div>
            <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${(u.net_units || 0) >= 0 ? "+" : ""}${(u.net_units || 0).toFixed(2)}u</div></div>
          <div class="tile"><div class="k">Graded</div><div class="v">${graded}</div>
            <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">judge after 50+, not 5</div></div>
        </div>`;
    })()}
    ${(() => {
      // The page said "re-check after Friday weigh-ins" and then offered no
      // way to know whether anyone had. This is that status, up top, where
      // it changes what you do with the card below.
      const w = d.weigh_ins;
      if (!w) return "";
      if (w.missed) {
        return `<div class="card" style="border-left:3px solid var(--bad);margin-bottom:12px">
          <div class="player">${icon('cross')} ${w.missed} fighter(s) missed weight</div>
          <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:4px">Their fights are
          gated off the pick list automatically — that is what KILL IF always said and now
          enforces. ${w.unrecorded} weigh-in(s) still unrecorded.</div></div>`;
      }
      if (w.unrecorded) {
        return `<div class="card" style="border-left:3px solid var(--warn);margin-bottom:12px">
          <div class="player">${icon('clock')} ${w.unrecorded} weigh-in(s) not recorded yet</div>
          <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:4px">Fighters weigh in the
          morning before the card, and the site pulls the results on its own once they publish —
          nothing for you to do. Until then these fights are graded <em>without</em> the fight-week
          component rather than being marked down for it, so the picks below stand on their own.
          A miss, when one lands, gates that fight on the next build.</div></div>`;
      }
      return `<div class="card" style="border-left:3px solid var(--good);margin-bottom:12px">
        <div class="player">${icon('check')} Weigh-ins complete — ${w.made} on weight, none missed</div></div>`;
    })()}
    ${d.no_qualifying ? `<div class="card"><div class="player">No qualifying plays on this card.</div>
        <div style="color:var(--text-body);font-size:var(--fs-md);margin-top:6px">Most fights on any card
        have no exploitable edge — the pass list below says why, fight by fight. Re-check after
        Friday weigh-ins: missed weight and visible cut damage aren't fully priced for hours, and
        the weigh-in results land here automatically.</div></div>`
      : `<div class="section-title">Picks
          <span class="sub">— cleared the clamp AND the gate · one-fifth Kelly stakes · journaled
          at these prices and graded after the card</span></div>
        <div class="cards wide">${(d.picks || []).map(pickCard).join("")}</div>`}
    ${(() => {
      // Grouped so the page reads as a card, not a wall: fights we
      // actually priced first, then the ones waiting on books, then the
      // ones no data source covers.
      const groups = [
        ["Modeled — no edge at this price", ["gate", "clamp_kill"],
         "priced, run through the model, and rejected by the clamp or the gate"],
        ["Waiting on prices", ["no_price"],
         "books open MMA lines closer to the card — these re-evaluate every refresh"],
        ["Unmodelable — no tracked stats", ["no_data", "no_dossier"],
         "regional or uncovered records: no fight-by-fight data exists, so the model refuses"],
      ];
      const list = d.pass_list || [];
      const seen = new Set();
      let html = "";
      for (const [title, codes, sub] of groups) {
        const rows = list.filter((m) => codes.includes(m.reason_code));
        rows.forEach((m) => seen.add(m));
        if (!rows.length) continue;
        html += `<div class="section-title">${title}
            <span class="sub">— ${rows.length} fight(s) · ${sub}</span></div>
          <div class="cards wide">${rows.map(passCard).join("")}</div>`;
      }
      const rest = list.filter((m) => !seen.has(m));
      if (rest.length)
        html += `<div class="section-title">Other passes</div>
          <div class="cards wide">${rest.map(passCard).join("")}</div>`;
      return html || `<div class="section-title">Pass list</div>
        <p class="loading" style="padding:12px">Nothing to pass on.</p>`;
    })()}
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Dossiers draft themselves:
      run <code>python3 ufc_dossiers.py</code> before a card, then review the numbers it prints
      (red flags block bets until you confirm or delete them). The model refuses any fight
      missing a dossier. Updated ${escapeHtml(d.generated_at || "")}.</p>`;
}

/* ============================================================
   Why Us — positioning with receipts, plus the open math layer.
   Every formula here is the same math the engines run; showing it
   is the point. Nothing on this page needs a data feed.
   ============================================================ */
const amToDec = (o) => (o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o));
const amToProb = (o) => (o > 0 ? 100 / (o + 100) : Math.abs(o) / (Math.abs(o) + 100));
const probToAm = (p) => (p >= 0.5 ? -Math.round((p / (1 - p)) * 100) : Math.round(((1 - p) / p) * 100));

function devigMult(ps) {
  const s = ps.reduce((a, b) => a + b, 0);
  return ps.map((p) => p / s);
}

/* Power de-vig: raise each implied prob to the k that makes them sum to 1.
   Shades more of the vig onto favorites than plain division does. */
function devigPower(ps) {
  let lo = 0.5, hi = 8;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (ps.reduce((a, p) => a + Math.pow(p, mid), 0) > 1) lo = mid; else hi = mid;
  }
  const k = (lo + hi) / 2;
  const raw = ps.map((p) => Math.pow(p, k));
  const s = raw.reduce((a, b) => a + b, 0);
  return raw.map((p) => p / s);
}

/* Shin de-vig: models the overround as the book defending against a share z
   of insider money, which loads vig onto longshots (the favorite–longshot
   bias). Solve z by bisection so the fair probs sum to 1. */
function devigShin(ps) {
  const S = ps.reduce((a, b) => a + b, 0);
  if (S <= 1) return devigMult(ps);
  const at = (z) => ps.map((p) =>
    (Math.sqrt(z * z + 4 * (1 - z) * (p * p) / S) - z) / (2 * (1 - z)));
  let lo = 0, hi = 0.5;
  for (let i = 0; i < 80; i++) {
    const mid = (lo + hi) / 2;
    if (at(mid).reduce((a, b) => a + b, 0) > 1) lo = mid; else hi = mid;
  }
  return at((lo + hi) / 2);
}

/* Kelly criterion: f* = (b·p − q)/b at decimal payout b = dec − 1. */
const kellyFraction = (p, odds) => {
  const b = amToDec(odds) - 1;
  return (b * p - (1 - p)) / b;
};

function whyCalcDevig() {
  const a = parseFloat(document.getElementById("dv-a")?.value);
  const b = parseFloat(document.getElementById("dv-b")?.value);
  const out = document.getElementById("dv-out");
  if (!out) return;
  if (!isFinite(a) || !isFinite(b) || Math.abs(a) < 100 || Math.abs(b) < 100) {
    out.innerHTML = `<p class="loading" style="padding:8px 0">Enter both sides as American odds (±100 or longer).</p>`;
    return;
  }
  const ps = [amToProb(a), amToProb(b)];
  const hold = ps[0] + ps[1] - 1;
  const methods = [
    ["Multiplicative", devigMult(ps), "divide out the vig equally — quick, slightly kind to longshots"],
    ["Power", devigPower(ps), "loads more vig onto the favorite — closer to how props are priced"],
    ["Shin", devigShin(ps), "models insider risk — best for lopsided favorite/longshot prices"],
  ];
  const row = (name, f, note) => `<tr>
    <td style="padding:6px 10px"><strong>${name}</strong>
      <span style="display:block;font-size:.78em;color:var(--text-mute)">${note}</span></td>
    <td style="padding:6px 10px;text-align:right">${(f[0] * 100).toFixed(1)}% <span style="opacity:.6">(${american(probToAm(f[0]))})</span></td>
    <td style="padding:6px 10px;text-align:right">${(f[1] * 100).toFixed(1)}% <span style="opacity:.6">(${american(probToAm(f[1]))})</span></td>
  </tr>`;
  const bench = hold <= 0 ? "an ARBITRAGE — the books disagree enough to lock a margin"
    : hold <= 0.02 ? "a low-hold market — cheap to bet, hard to find"
    : hold <= 0.05 ? "typical main-line juice"
    : "prop-level juice — you need a real edge just to break even";
  out.innerHTML = `
    <p style="margin:8px 0 4px">Book implied: <strong>${(ps[0] * 100).toFixed(1)}%</strong> + <strong>${(ps[1] * 100).toFixed(1)}%</strong>
      = ${( (hold + 1) * 100).toFixed(1)}% → hold <strong style="color:${hold > 0.05 ? "var(--bad)" : hold > 0.02 ? "var(--warn)" : "var(--good)"}">${(hold * 100).toFixed(2)}%</strong>
      <span style="color:var(--text-mute)">— ${bench}.</span></p>
    <div style="overflow-x:auto;overflow-y:hidden"><table style="width:100%;border-collapse:collapse;font-size:.92em">
      <tr style="color:var(--text-mute);text-align:right">
        <td style="padding:4px 10px;text-align:left">Fair (vig removed)</td><td>Side A</td><td>Side B</td></tr>
      ${methods.map((m) => row(...m)).join("")}
    </table></div>
    <p style="font-size:.82em;color:var(--text-mute);margin-top:6px">Where the three agree, trust the number.
      Where they split, the truth is in the range — that honesty is the feature.
      Every board on this site prices edges against de-vigged probabilities, never raw juice.</p>`;
}

function whyCalcKelly() {
  const p = parseFloat(document.getElementById("ky-p")?.value) / 100;
  const odds = parseFloat(document.getElementById("ky-odds")?.value);
  const roll = parseFloat(document.getElementById("ky-roll")?.value);
  const frac = parseFloat(document.getElementById("ky-frac")?.value || "0.25");
  const out = document.getElementById("ky-out");
  if (!out) return;
  if (!isFinite(p) || p <= 0 || p >= 1 || !isFinite(odds) || Math.abs(odds) < 100) {
    out.innerHTML = `<p class="loading" style="padding:8px 0">Enter a win probability (1–99%) and American odds.</p>`;
    return;
  }
  const full = kellyFraction(p, odds);
  const edge = p * amToDec(odds) - 1;
  if (full <= 0) {
    out.innerHTML = `<p style="margin-top:8px"><strong style="color:var(--bad)">No bet.</strong>
      At ${american(odds)} you need ${(amToProb(odds) * 100).toFixed(1)}% to break even and you estimate ${(p * 100).toFixed(1)}% —
      EV ${signedPct(edge)}. Kelly's answer for a negative edge is a stake of zero, and it's the only honest one.</p>`;
    return;
  }
  const stakePct = full * frac;
  const dollars = isFinite(roll) && roll > 0 ? ` = <strong>$${(roll * stakePct).toFixed(2)}</strong> of your $${roll.toFixed(0)}` : "";
  out.innerHTML = `
    <p style="margin-top:8px">EV <strong style="color:var(--good)">${signedPct(edge)}</strong> per unit ·
      full Kelly <strong>${(full * 100).toFixed(1)}%</strong> of bankroll ·
      at your fraction: <strong style="color:var(--brand)">${(stakePct * 100).toFixed(2)}%</strong>${dollars}</p>
    <p style="font-size:.82em;color:var(--text-mute);margin-top:6px">Full Kelly assumes your probability is exactly right — it never is.
      Betting a quarter to a fifth of Kelly gives up little growth and cuts drawdowns enormously;
      the engines here stake fractional Kelly for exactly that reason. If the number feels big, your probability is too confident.</p>`;
}

// A -110/-110 market prices to 104.76%; stripping that leaves the fair
// number a leg is actually worth.
const TYPICAL_OVERROUND = 1.0476;

function whyCalcParlay() {
  const out = document.getElementById("pl-out");
  if (!out) return;
  const legs = [];
  for (let i = 1; i <= 3; i++) {
    const o = parseFloat(document.getElementById(`pl-o${i}`)?.value);
    if (!isFinite(o) || Math.abs(o) < 100) continue;
    const pv = parseFloat(document.getElementById(`pl-p${i}`)?.value);
    // A blank win% must NOT default to the book's implied probability:
    // that makes EV exactly zero by construction, so the comparison shows
    // "+0.0% vs +0.0%" and the verdict beneath it is arbitrary noise.
    // Strip a standard two-way overround instead, which is what the leg
    // is really worth — then the numbers show the vig compounding, which
    // is the entire lesson.
    legs.push({ odds: o, assumed: !(isFinite(pv) && pv > 0 && pv < 100),
                p: isFinite(pv) && pv > 0 && pv < 100
                   ? pv / 100 : amToProb(o) / TYPICAL_OVERROUND });
  }
  if (legs.length < 2) {
    out.innerHTML = `<p class="loading" style="padding:8px 0">Enter odds for at least two legs (win % optional — blank assumes the book's implied).</p>`;
    return;
  }
  const dec = legs.reduce((a, l) => a * amToDec(l.odds), 1);
  const prob = legs.reduce((a, l) => a * l.p, 1);
  const evParlay = prob * dec - 1;
  const evSingles = legs.reduce((a, l) => a + (l.p * amToDec(l.odds) - 1), 0) / legs.length;
  const assumed = legs.some((l) => l.assumed);
  const verdict = evParlay > evSingles + 1e-9
    ? "the parlay compounds it — only because every leg you entered is +EV"
    : "the singles are the better bet — the parlay multiplies the book's margin into every leg";
  out.innerHTML = `
    <p style="margin-top:8px">${legs.length}-leg parlay pays <strong>${american(probToAm(1 / dec))}</strong>
      (decimal ${dec.toFixed(2)}) · combined win probability <strong>${(prob * 100).toFixed(1)}%</strong></p>
    <p>EV: parlay <strong style="color:${evParlay >= 0 ? "var(--good)" : "var(--bad)"}">${signedPct(evParlay)}</strong>
      vs the same money on singles <strong style="color:${evSingles >= 0 ? "var(--good)" : "var(--bad)"}">${signedPct(evSingles)}</strong>
      <span style="color:var(--text-mute)">— ${verdict}.</span></p>
    ${assumed ? `<p style="font-size:.82em;color:var(--text-mute);margin-top:6px">
      Win % left blank, so each leg is valued at its price with a standard
      ${((TYPICAL_OVERROUND - 1) * 100).toFixed(1)}% overround removed — what the leg is
      really worth. Enter your own probabilities to test a specific edge.</p>` : ""}
    <p style="font-size:.82em;color:var(--text-mute);margin-top:6px">This is why books push parlays:
      at standard −110 juice each leg keeps ~4.5% hold, and a parlay charges it on every leg at once.
      Correlated same-game legs can flip this — but the books price those separately for exactly that reason.</p>`;
}

/* ============================================================
   About — what this site is, for someone who just landed on it.

   Written for a reader with no context: no jargon in the first screen,
   the limits stated as plainly as the strengths, and the legal and
   responsible-gambling terms in the same place rather than buried in a
   footer nobody opens. The tone is deliberately flat. A page that hypes
   the model on the way to a disclaimer has not really made the
   disclaimer.
   ============================================================ */
function renderAbout() {
  const host = document.getElementById("about-body");
  if (!host) return;
  const src = document.getElementById("data-source");
  if (src) {
    src.className = "data-source";
    src.textContent = "Reference";
    src.title = "Plain-English explainer — no data feed involved";
  }
  const dt = document.getElementById("slate-date");
  if (dt) dt.textContent = "About · terms · responsible play";

  const card = (title, body, accent) => `
    <article class="card about-card"${accent ? ` style="border-left:3px solid ${accent}"` : ""}>
      <div class="player">${title}</div>
      <div class="about-body">${body}</div>
    </article>`;

  host.innerHTML = `
    <div class="about-lede">
      <p><strong>Qellys Book is an analytics tool, not a sportsbook and not a
      tipster.</strong> You cannot place a bet here and no money changes hands
      on this site. What it does is take the same public information the
      sportsbooks use — every game, every player's recent form, injuries,
      weather, venues, and the live prices at ten different books — pull it
      into one place, and estimate its own probability for each outcome.</p>

      <p>Then it does the only thing that actually matters: it compares that
      probability to the price. When our number and the book's number
      disagree by enough to survive our own margin for error, the board
      shows it. When they don't, the board says <em>"no qualifying plays"</em>
      and shows you nothing. That happens often, and it is the system
      working rather than failing.</p>
    </div>

    <div class="section-title">Everything in one place
      <span class="sub">— the practical reason this exists</span></div>
    <div class="cards wide">
      ${card("The information is public. Having it together is the edge.", `
        <p>None of the data here is secret. Box scores, injury reports, depth
        charts, park factors, weather, recruiting rankings, fighter records —
        anyone can look all of it up. The problem is that "anyone" would need
        a dozen browser tabs and two hours per slate, and the line will have
        moved before they finish.</p>
        <p>This site does that gathering continuously and automatically, then
        prices it against <strong>ten sportsbooks at once</strong>. Two books
        quoting the same game differently is a real, ordinary occurrence, and
        on a two-way market a twenty-cent difference in price can be the whole
        margin. You cannot beat a book on information it also has; you can
        beat it on information it hasn't bothered to price carefully, and on
        being at the right window.</p>`)}

      ${card("What the model is actually doing", `
        <p>For each market it builds a full <strong>distribution</strong>, not a
        pick. Not "this player goes over" but "here is the range of outcomes
        and how likely each one is." It removes the book's built-in margin
        (the "vig") to find what the market really believes, compares that to
        our number, and then <strong>deliberately shrinks our own edge</strong>
        — because a model that trusts itself completely is a model that has
        stopped noticing it can be wrong.</p>
        <p>Whatever survives that gets graded 0–100 and sized by a fraction of
        the Kelly criterion, a standard bankroll formula. Anything under the
        bar is not shown as a weaker suggestion. It is not shown.</p>`)}

      ${card("We show our losses", `
        <p>Every play the model publishes is recorded at the price and time it
        was published, then graded against the real result — wins and losses
        both — on the <strong>Record</strong> page. Nothing is quietly deleted
        after it loses.</p>
        <p>Newer models are marked <em>on probation</em>: they are tracked and
        graded like everything else, but they have not yet earned the right to
        be staked. Where we are missing a data source, the page says so
        instead of filling the hole with a guess.</p>`)}
    </div>

    <div class="section-title">The honest part
      <span class="sub">— please read this bit properly</span></div>
    <div class="cards wide">
      ${card(`${icon('warn')} Anything can happen. Genuinely anything.`, `
        <p>Sports are random and betting is gambling. A 90% favourite loses
        one time in ten, and that one time can be tonight, and it can happen
        three nights in a row. A quarterback rolls an ankle on the first
        drive. A fighter who has never been stopped gets caught by a punch he
        did not see. A game gets called for weather in the sixth inning.</p>
        <p><strong>No model can predict a single event, and this one does not
        claim to.</strong> It claims something much smaller: that across
        hundreds of bets, taking prices that are better than they should be
        works out better than taking prices that aren't. Even if every number
        on this site were perfect, you would still have long losing runs. That
        is not a bug in the method — it is what randomness looks like from the
        inside.</p>
        <p>Nothing here is a guarantee, a lock, a sure thing, or a prediction.
        Past results — including ours — do not predict future results.</p>`,
        "var(--bad)")}

      ${card("This is not betting advice", `
        <p>Everything published here is <strong>automated statistical output
        and general information</strong>, produced by our model from public
        data. It is not financial advice, investment advice, or a
        recommendation that you place any particular wager. We are not your
        advisor and we have no idea what your circumstances are.</p>
        <p>Every decision you make with this information is yours alone, and
        so is every outcome. If you would not be comfortable losing the money,
        do not put it at risk.</p>`,
        "var(--warn)")}

      ${card("Legal — the rules that apply", `
        <ul class="about-list">
          <li><strong>You must be of legal gambling age</strong> where you are.
            That is 21 in most of the United States and 18 in some
            jurisdictions. If you are under it, this site is not for you.</li>
          <li><strong>Sports betting is not legal everywhere.</strong> Laws
            differ by country, state and province and they change. It is your
            responsibility to know the rules where you are and to follow
            them.</li>
          <li><strong>We are not affiliated with any sportsbook</strong>, and
            not with the NFL, MLB, NBA, WNBA, UFC, the NCAA or any team,
            school or league. Book names appear only to identify where a price
            was quoted. All trademarks belong to their owners.</li>
          <li><strong>We take no bets, hold no money and process no
            payments.</strong> No part of this site is a wagering service.</li>
          <li><strong>Prices change.</strong> Odds shown were correct when
            fetched and may be stale by the time you read them. The
            timestamp on each page tells you how old the data is — check it.
            Always confirm the current price at your book.</li>
          <li><strong>No warranty.</strong> Data can be wrong, feeds can break
            and models can be miscalibrated. Everything here is provided as-is,
            with no guarantee of accuracy or fitness for any purpose, and we
            accept no liability for losses arising from its use.</li>
          <li><strong>Personal use.</strong> This is a private analytics tool.
            It is not a licensed gambling operator or a paid tipping service,
            and nothing on it is an offer to provide one.</li>
        </ul>`,
        "var(--brand)")}

      ${card(`${iconMark("warn")}If it stops being fun, stop`, `
        <p>Gambling is genuinely addictive, and a tool that makes betting feel
        more rigorous can make it easier to bet more, not less. Bet only money
        you can afford to lose. Never chase a loss. Set a limit before you
        start rather than during. Take breaks. Betting is not a way to make
        a living or to fix a financial problem.</p>
        <p>If it has stopped being fun, or someone close to you thinks it has,
        help is free and confidential:</p>
        <ul class="about-list">
          <li><strong>United States</strong> — 1-800-GAMBLER
            (1-800-426-2537), or text 800GAM to 53342.
            <a href="https://www.ncpgambling.org" target="_blank"
               rel="noopener noreferrer">ncpgambling.org</a></li>
          <li><strong>United Kingdom</strong> — GamCare, 0808 8020 133.
            <a href="https://www.begambleaware.org" target="_blank"
               rel="noopener noreferrer">begambleaware.org</a></li>
          <li><strong>Canada</strong> — ConnexOntario, 1-866-531-2600</li>
          <li><strong>Anywhere</strong> — Gamblers Anonymous,
            <a href="https://www.gamblersanonymous.org" target="_blank"
               rel="noopener noreferrer">gamblersanonymous.org</a></li>
        </ul>
        <p>Most sportsbooks also offer deposit limits, time-outs and
        self-exclusion. Using them is a sign of good process, not weakness.</p>`,
        "var(--good)")}
    </div>

    <div class="ls-note" style="margin-top:18px">
      In one sentence: <strong>we gather every number in one place and tell you
      when a price looks wrong — you decide what, if anything, to do about
      it, and the result is never guaranteed.</strong>
    </div>`;
  revealChildren(host);
}

async function renderWhy() {
  const host = document.getElementById("why-body");
  if (!host) return;
  const src = document.getElementById("data-source");
  if (src) {
    src.className = "data-source";
    src.textContent = "Reference";
    src.title = "Explainer + calculators — no data feed involved";
  }
  const dt = document.getElementById("slate-date");
  if (dt) dt.textContent = "Why us · the open math";

  // Live receipts — the claims below link to real, current numbers.
  let rec = null;
  try {
    const res = await fetch("data/record.json?t=" + Date.now());
    if (res.ok) rec = await res.json();
  } catch (e) {}
  const o = rec && rec.overall;
  const proc = (o && o.process) || {};
  const procN = (proc.good || 0) + (proc.bad || 0) + (proc.flat || 0);
  const cal = rec && rec.calibration;
  const brierLine = cal && cal.brier_edge != null
    ? (cal.brier_edge > 0
      ? `model out-forecasts the de-vigged market on its own picks (Brier ${cal.brier_model} vs ${cal.brier_market})`
      : `the market still forecasts our picks better (Brier ${cal.brier_model} vs ${cal.brier_market}) — shown anyway, because hiding it would make us a tout`)
    : "accrues as picks settle";
  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div>
    ${sub ? `<div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${sub}</div>` : ""}</div>`;
  const proof = o && (o.settled || o.open)
    ? `<div class="stats" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
        ${tile("Journaled record", `${o.wins}-${o.losses}-${o.pushes}`, `${o.open} open · every pick, no deletions`)}
        ${tile("Avg CLV", o.avg_clv == null ? "—" : (o.avg_clv >= 0 ? "+" : "") + o.avg_clv.toFixed(2) + " pts",
               "did the market move our way after we bet")}
        ${tile("Process record", procN ? `${proc.good || 0} good · ${proc.bad || 0} bad` : "—",
               procN ? `${proc.lucky_wins || 0} lucky win(s) admitted` : "grades vs the closing line")}
        ${tile("Forecast test", cal && cal.brier_edge != null ? (cal.brier_edge > 0 ? "beating the close" : "not yet") : "—", brierLine)}
      </div>
      <p style="margin-top:8px"><button class="btn ghost" id="why-see-record">See the full record →</button></p>`
    : `<p style="color:var(--text-mute);font-size:.92em;margin:0 0 4px">The journal is
        young — every pick logs automatically and this strip fills with real,
        ungroomed numbers.</p>`;

  // Named `glyph`, not `icon`: a parameter called icon SHADOWS the drawing
  // helper for the whole body, so the next person to reach for a real icon
  // inside a pillar would get a silent string interpolation instead.
  const pillar = (glyph, title, body) => `<div class="card" style="padding:16px">
    <div style="font-size:1.6em">${glyph}</div>
    <h3 style="margin:6px 0 6px">${title}</h3>
    <p style="color:var(--text-body);font-size:.92em;margin:0">${body}</p></div>`;

  const vsRow = (them, us) => `<tr>
    <td style="padding:8px 12px;color:var(--text-mute);border-bottom:1px solid rgba(255,255,255,.05)">${them}</td>
    <td style="padding:8px 12px;border-bottom:1px solid rgba(255,255,255,.05)">${us}</td></tr>`;

  host.innerHTML = `
    <p style="font-size:1.06em;max-width:none;line-height:1.6;margin:0 0 4px"><strong>See the math. Know if it's working. Stay in the game.</strong>
      Most betting sites sell certainty. This one sells measurement — every probability is computed
      from data you can name, every pick is graded in public, and the math is on this page for you to check by hand.</p>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-top:14px">
      ${pillar(icon("search", 22), "Transparent math", `Park factors, umpire tendencies, lineup-slot plate appearances, bullpen fatigue,
        minutes engines — every factor on a card is measured from real data, and negative factors get a red ✗, not a hidden footnote.
        The de-vig, Kelly and EV formulas the engines run are open below.`)}
      ${pillar(icon("book", 22), "Graded in public", `Every recommended pick journals at its real book price the moment it appears and grades
        itself against the final result — wins, losses, closing-line value, and a calibration curve that says whether "60%" meant 60%.
        Long shots are tracked in a separate bucket, never blended into the headline record.`)}
      ${pillar(icon("cross", 22), "Built to pass", `Approval gates, humility clamps toward the market, hard pick caps, and pass lists that
        say why each game was skipped. "No qualifying plays tonight" is a correct output here — a service that must sell picks
        every night can never say it.`)}
    </div>

    <div class="section-title">The receipts, live
      <span class="sub">— these numbers come from the actual journal, right now, losses included.</span></div>
    ${proof}

    <div class="section-title">What picks services sell vs what this is</div>
    <div class="card" style="padding:0;overflow-x:auto;overflow-y:hidden">
      <table style="width:100%;border-collapse:collapse;font-size:.92em">
        <tr style="color:var(--text-mute)"><td style="padding:8px 12px">The usual pitch</td><td style="padding:8px 12px">Here</td></tr>
        ${vsRow("\"Locks\" and \"guaranteed winners\"", "Probabilities with uncertainty attached. A 60% play loses 4 times in 10 — we say so on the card.")}
        ${vsRow("A record you have to take on faith", "A journal that logs every pick automatically at its real price — it cannot be groomed after the fact.")}
        ${vsRow("Graded on wins and losses only", "Graded on process too: a win that closed worse than we bet is flagged as lucky; a loss that beat the close was a good bet.")}
        ${vsRow("A black-box \"algorithm\"", "Named factors on every card, red marks on the negatives, and the pricing math open on this page.")}
        ${vsRow("More picks when business is slow", "Hard caps and pass lists. The NBA engine maxes at 4 picks a slate; UFC passes on most of every card, with reasons.")}
      </table>
    </div>

    <div class="section-title">What we deliberately don't do</div>
    <div class="card" style="padding:14px 18px">
      <ul style="margin:0;padding-left:18px;line-height:1.9;color:var(--text-body)">
        <li>No guarantees, locks, or "can't-miss" anything — that language is how touts talk, and it's always false.</li>
        <li>No parlay pushing — the calculator below shows exactly what parlays cost, which is why books advertise them.</li>
        <li>No hiding losses — the Record page keeps every settled pick, and the lucky wins are labeled as lucky.</li>
        <li>No placing bets and no handling money — this recommends, journals, and grades. The decisions stay yours.</li>
        <li>No "premium tier" where the real picks supposedly live — everything the models produce is on these pages.</li>
      </ul>
    </div>

    <div class="section-title">The open math layer
      <span class="sub">— the same formulas the engines run, interactive. Punch in any real price and check our work.</span></div>

    <div class="card" style="padding:16px;margin-bottom:14px">
      <h3 style="margin:0 0 4px">Remove the vig — three ways</h3>
      <p style="color:var(--text-mute);font-size:.85em;margin:0 0 10px">A −110/−110 line isn't 50/50 — it's 52.4% + 52.4% = 104.8%.
        The extra 4.8% is the book's hold. Enter both sides of any market:</p>
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <label>Side A <input id="dv-a" type="number" value="-115" step="5" class="calc-in"></label>
        <label>Side B <input id="dv-b" type="number" value="-105" step="5" class="calc-in"></label>
      </div>
      <div id="dv-out"></div>
    </div>

    <div class="card" style="padding:16px;margin-bottom:14px">
      <h3 style="margin:0 0 4px">Kelly stake sizer</h3>
      <p style="color:var(--text-mute);font-size:.85em;margin:0 0 10px">Given your edge, how much should the bet be?
        The answer is usually "less than you think" and sometimes "zero".</p>
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        <label>Win prob % <input id="ky-p" type="number" value="55" min="1" max="99" step="0.5" class="calc-in"></label>
        <label>Odds <input id="ky-odds" type="number" value="-110" step="5" class="calc-in"></label>
        <label>Bankroll $ <input id="ky-roll" type="number" value="${state.bankroll || 1000}" min="0" step="50" class="calc-in"></label>
        <label>Fraction <select id="ky-frac" class="calc-in">
          <option value="1">Full Kelly</option><option value="0.5">Half</option>
          <option value="0.25" selected>Quarter</option><option value="0.2">Fifth</option>
        </select></label>
      </div>
      <div id="ky-out"></div>
    </div>

    <div class="card" style="padding:16px;margin-bottom:14px">
      <h3 style="margin:0 0 4px">Parlay vs singles</h3>
      <p style="color:var(--text-mute);font-size:.85em;margin:0 0 10px">Enter 2–3 legs. Win % is optional —
        left blank, each leg is assumed to hit exactly as often as the book's price implies.</p>
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
        ${[1, 2, 3].map((i) => `<span style="display:inline-flex;gap:6px;align-items:center">
          <label>Leg ${i} <input id="pl-o${i}" type="number" ${i < 3 ? `value="-110"` : ""} step="5" class="calc-in"></label>
          <label>win % <input id="pl-p${i}" type="number" min="1" max="99" step="0.5" class="calc-in" style="width:70px"></label>
        </span>`).join("")}
      </div>
      <div id="pl-out"></div>
    </div>

    <div class="card" style="padding:14px 18px;margin-top:20px;border-left:3px solid var(--warn)">
      <h3 style="margin:0 0 6px">Play the long game</h3>
      <p style="color:var(--text-body);font-size:.92em;margin:0">Even a real edge loses often — that's variance, not failure,
        and it's why stakes here are fractions of bankroll, never "bet big to catch up." 21+ only. Never bet money you
        can't afford to lose. If it stops feeling like a decision, call or text <strong>1-800-GAMBLER</strong> or the National
        Problem Gambling Helpline at <strong>1-800-522-4700</strong> — free, confidential, 24/7.</p>
    </div>`;

  const seeRec = document.getElementById("why-see-record");
  if (seeRec) seeRec.addEventListener("click", () => enterStandaloneMode("record"));
  [["dv-a", whyCalcDevig], ["dv-b", whyCalcDevig],
   ["ky-p", whyCalcKelly], ["ky-odds", whyCalcKelly], ["ky-roll", whyCalcKelly], ["ky-frac", whyCalcKelly],
   ["pl-o1", whyCalcParlay], ["pl-p1", whyCalcParlay], ["pl-o2", whyCalcParlay],
   ["pl-p2", whyCalcParlay], ["pl-o3", whyCalcParlay], ["pl-p3", whyCalcParlay],
  ].forEach(([id, fn]) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", fn);
  });
  whyCalcDevig(); whyCalcKelly(); whyCalcParlay();
}


/* ============================================================
   Progressive disclosure for the explanatory prose.

   Nearly every section here carries a paragraph explaining what the
   numbers mean and why they can be trusted. That honesty is the point of
   the product, but shipped all at once it buries the data under
   documentation — the eye hits three lines of grey text before reaching
   anything it came for. So the explanations collapse behind a "why?"
   toggle: the reasoning stays one click away and never has to be
   deleted, while the numbers lead.

   Sections re-render constantly (innerHTML on every refresh), so this
   runs off a MutationObserver rather than once at load, and marks what
   it has already handled.
   ============================================================ */
const SUB_COLLAPSE_CHARS = 90;   // one line is fine; a paragraph is not

function enhanceSectionSubs(root) {
  (root || document).querySelectorAll(".section-title .sub").forEach((sub) => {
    const title = sub.parentElement;
    if (!title || title.dataset.subEnhanced) return;
    const text = (sub.textContent || "").trim();
    if (text.length <= SUB_COLLAPSE_CHARS) return;
    title.dataset.subEnhanced = "1";
    sub.classList.add("sub-collapsed");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "why-toggle";
    btn.textContent = "why?";
    btn.setAttribute("aria-expanded", "false");
    btn.addEventListener("click", () => {
      const open = sub.classList.toggle("sub-collapsed");
      btn.setAttribute("aria-expanded", String(!open));
      btn.textContent = open ? "why?" : "hide";
    });
    sub.before(btn);
  });
}

function watchSectionSubs() {
  enhanceSectionSubs();
  const main = document.querySelector("main");
  if (!main || typeof MutationObserver === "undefined") return;
  const obs = new MutationObserver(() => enhanceSectionSubs());
  obs.observe(main, { childList: true, subtree: true });
}

const VIEW_ORDER = ["recommended", "live", "edge", "scanner", "longshots", "parlays", "futures", "trending", "players", "rosters", "standings", "record", "lab", "intel", "fantasy", "ufc", "why", "about"];

function switchView(name, push = false) {
  const dir = VIEW_ORDER.indexOf(name) - VIEW_ORDER.indexOf(state.view);
  state.view = name;
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active", "from-left", "from-right"));
  const target = document.getElementById(`view-${name}`);
  // Entering view slides in from the direction of travel between tabs.
  if (dir > 0) target.classList.add("from-right");
  else if (dir < 0) target.classList.add("from-left");
  target.classList.add("active");
  // The game view has no tab of its own — it belongs to the board it came
  // from, so Recommended stays lit while you're inside a game.
  const lit = name === "game" ? "recommended" : name;
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === lit));
  if (name === "game") {
    renderGamePage();
    if (state.gameId) history.replaceState(null, "", `#game/${encodeURIComponent(state.gameId)}`);
    moveIndicator();
    window.scrollTo({ top: 0, behavior: state.quiet ? "auto" : "smooth" });
    return;
  }
  if (name === "rosters") renderRosters();
  if (name === "standings") renderStandings();
  if (name === "record") renderRecord();
  if (name === "lab") renderLab();
  if (name === "intel") renderIntel();
  if (name === "fantasy") renderFantasy();
  if (name === "ufc") renderUFC();
  if (name === "why") renderWhy();
  if (name === "about") renderAbout();
  updateAgo();          // reference pages hide the freshness chip
  if (location.hash !== `#${name}`) {
    // A tab TAP is a navigation and earns a history entry, so the phone's
    // back-swipe returns to the tab you came from instead of leaving the
    // site. Programmatic switches (first load, a sport change, bouncing
    // off a hidden tab) replace instead — they are not places you chose to
    // be, and stacking them would make Back walk backwards through moves
    // you never made.
    if (push) history.pushState({ view: name }, "", `#${name}`);
    else history.replaceState({ view: name }, "", `#${name}`);
  }
  // Called HERE rather than at each tap, because switchView is the single
  // place the highlight changes. Wiring it to the click handlers only
  // covered taps: coming back with the phone's back-swipe re-rendered the
  // page but left the header reading the tab you had just left, so the one
  // line telling you where you are was the one line that was wrong.
  syncMenuLabel();
  moveIndicator();
}

function initialView() {
  const h = (location.hash || "").replace("#", "");
  // A tab this sport does not have must not be reachable by URL. CFB has
  // no roster feed, and #rosters would otherwise open a page whose own tab
  // is hidden — the nav and the content disagreeing about what exists.
  if ((HIDDEN_VIEWS[state.sport] || []).includes(h)) {
    switchView("recommended");
    return;
  }
  if (h.startsWith("game/")) { openGame(decodeURIComponent(h.slice(5))); return; }
  if (h === "nba") {           // legacy hash from when NBA was standalone
    state.sport = "nba"; applySport(); load(); switchView("recommended"); return;
  }
  if (STANDALONE_MODES.includes(h)) { enterStandaloneMode(h); return; }
  if (VIEW_ORDER.includes(h)) switchView(h);
}

function moveIndicator() {
  const active = document.querySelector(".nav-btn.active");
  const ind = document.getElementById("nav-indicator");
  if (!active || !ind) return;
  ind.style.left = active.offsetLeft + "px";
  ind.style.width = active.offsetWidth + "px";
}

/* ============================================================
   Mobile menu. Fourteen destinations (seven products, seven tabs) as a
   horizontally scrolling strip technically reaches everything, but it
   hides where you can go behind a gesture nobody is told about. On a
   phone they collapse into one menu that shows the current page and
   opens the full list.
   ============================================================ */
/* Home = the current sport's Recommended board, freshly loaded.

   Standalone pages (Polymarket, Fantasy, UFC, Why Us) aren't sports and
   have no Recommended view, so from there home means "back to the sport
   you were on" — exitStandaloneMode restores its nav and brand. */
function goHome() {
  closeMobileMenu();
  if (STANDALONE_MODES.includes(state.view)) {
    exitStandaloneMode();
  } else if (state.view !== "recommended") {
    switchView("recommended");
  }
  syncMenuLabel();
  window.scrollTo({ top: 0, behavior: state.quiet ? "auto" : "smooth" });
  load();                                   // always pull current numbers
}

function closeMobileMenu() {
  document.body.classList.remove("menu-open");
  const btn = document.getElementById("menu-toggle");
  if (btn) btn.setAttribute("aria-expanded", "false");
}

function syncMenuLabel() {
  const el = document.getElementById("menu-label");
  if (!el) return;
  // Whatever is highlighted right now IS where you are — read it back
  // rather than keeping a second copy of the routing state in sync.
  const active = document.querySelector(".sport-btn.active");
  const tab = document.querySelector(".nav-btn.active");
  const sport = active ? active.textContent.trim() : "";
  const inStandalone = STANDALONE_MODES.includes(state.view);
  el.textContent = inStandalone || !tab
    ? (sport || "Menu")
    : `${sport} · ${tab.textContent.trim()}`;
}

function initMobileMenu() {
  const btn = document.getElementById("menu-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    // Anchor FIRST, then freeze: the .menu-open class locks body scroll,
    // so scrolling after it lands leaves the page pinned wherever it
    // happened to be. Left scrollable, the board underneath kept moving
    // while the menu was up — and because a different sport's board is a
    // different LENGTH, switching sports re-anchored the scroll and
    // dragged the menu with it.
    if (!document.body.classList.contains("menu-open")) {
      // "instant", not "auto": auto defers to the stylesheet, which sets
      // scroll-behavior: smooth — so the page GLIDED to the top under the
      // opening menu, which is itself visible movement.
      window.scrollTo({ top: 0, behavior: "instant" });
    }
    const open = document.body.classList.toggle("menu-open");
    // The menu lives inside the header, so a retracted header must come
    // back before it opens — otherwise the panel opens off-screen.
    if (open) showHeader();
    btn.setAttribute("aria-expanded", String(open));
  });
  // Choosing a SPORT is step one of two: NFL/MLB/NBA each have their own
  // page list, so the panel stays open for the second tap (and the Page
  // section updates live — NBA drops Long Shots, for instance). Standalone
  // destinations (Polymarket, Fantasy, UFC, Why Us) have no page list, so
  // they behave like any other final choice and close.
  document.querySelectorAll(".sport-btn").forEach((b) =>
    b.addEventListener("click", () => {
      if (STANDALONE_MODES.includes(b.dataset.sport)) closeMobileMenu();
      syncMenuLabel();
    }));
  // Picking a PAGE is the end of the interaction — never leave the panel
  // covering the thing the tap just navigated to.
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => { closeMobileMenu(); syncMenuLabel(); }));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMobileMenu();
  });
  syncMenuLabel();
}

/* The phone header is four stacked rows — menu bar, brand, freshness, date
   — about 200px of an 844px screen, and position:sticky, so it sat there
   for the entire scroll. A quarter of the display permanently spent on
   chrome you are not currently using.

   It now follows the finger, the way YouTube's search bar does: the header
   is offset by exactly as much as you have scrolled since your last change
   of direction, clamped to its own height. Swipe up 40px and it moves up
   40px; reverse and it comes back down at the same rate, from wherever it
   happens to be, at any point on the page.

   That 1:1 tracking is the whole feel, and it is why there is no threshold
   and no animation here. A deadzone makes it ignore small drags; a CSS
   transition makes it glide on its own schedule instead of the finger's.
   Both read as the header lagging behind the page.

   TRANSFORM, never height or display: a transform is painted, not laid
   out, so nothing behind it can reflow. Resizing this header at runtime is
   what produced the "top of the page keeps enlarging" bug. */
let headerOffset = 0;    // 0 = fully down, -height = fully retracted

function showHeader() {
  headerOffset = 0;
  const bar = document.querySelector(".topbar");
  if (bar) bar.style.transform = "";
}

/* Phones and tablets in either orientation — never a desktop with a mouse,
   where a 177px header on a 900px window is not in the way. This has to be
   kept identical to the media query at the end of styles.css; the transform
   is written inline, so nothing else stops it running on a laptop.
   tests/test_headertuck.py asserts the two stay in sync. */
const HEADER_TUCK_MQ =
  "(max-width: 760px), (pointer: coarse) and (max-width: 1024px)";

function initHeaderTuck() {
  const bar = document.querySelector(".topbar");
  if (!bar) return;
  const touch = matchMedia(HEADER_TUCK_MQ);
  let last = Math.max(0, window.scrollY);
  let height = 0;          // cached: reading it per frame forces layout
  let ticking = false;

  const measure = () => { height = bar.offsetHeight || 0; };
  measure();
  // The header grows AFTER first paint — the freshness chip is display:none
  // until data lands, which is 11px. Measured once at startup, the clamp
  // was 11px short and the bar never fully cleared the screen. Watch it
  // instead of trusting one reading.
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(measure).observe(bar);
  }
  // Rotating or resizing changes the header's height, so a stale offset
  // would leave it parked at the wrong place — start it from home instead.
  const reset = () => { measure(); showHeader(); last = Math.max(0, window.scrollY); };
  addEventListener("resize", reset);
  addEventListener("orientationchange", reset);
  if (touch.addEventListener) touch.addEventListener("change", reset);

  const apply = () => {
    ticking = false;
    // iOS reports a NEGATIVE scrollY mid-overscroll-bounce. Unclamped, the
    // delta inverts and the header twitches at the top of every page.
    const y = Math.max(0, window.scrollY);
    const dy = y - last;
    last = y;
    // The menu panel lives inside this header; the body can't scroll while
    // it's open anyway. At the very top there is nothing to retract past.
    // And on a desktop the header stays put — see HEADER_TUCK_MQ.
    if (!touch.matches || document.body.classList.contains("menu-open")
        || y === 0) {
      showHeader();
      return;
    }
    if (!height) measure();
    headerOffset = Math.min(0, Math.max(-height, headerOffset - dy));
    // Empty string, not translateY(0), so the element drops back to its
    // stylesheet state rather than carrying a permanent inline transform.
    bar.style.transform = headerOffset ? `translateY(${headerOffset}px)` : "";
  };

  addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(apply);
  }, { passive: true });
}

/* ---------------- wiring ---------------- */
function bind() {
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => switchView(b.dataset.view, true)));

  /* The URL and the page must never disagree. Nothing listened for a hash
     change, so back, forward, a pasted #standings link and an in-page
     anchor all moved the address bar while leaving the previous view on
     screen — and then the URL you copied pointed at something you were not
     looking at. */
  window.addEventListener("hashchange", () => {
    const h = (location.hash || "").replace("#", "");
    if (h.startsWith("game/")) { openGame(decodeURIComponent(h.slice(5))); return; }
    // An EMPTY hash is a destination, not a no-op: it is the entry the
    // first tab tap pushed on top of, so backing all the way out landed on
    // "/" with the last tab still on screen and the URL claiming the board.
    // One more back would then leave the site from a page you were not on.
    if (!h) {
      if (state.view === "recommended") return;
      exitStandaloneMode();
      switchView("recommended");
      return;
    }
    if (h === state.view) return;
    if (!VIEW_ORDER.includes(h) || !document.getElementById(`view-${h}`)) return;
    // A tab this sport does not have stays unreachable by URL — and the
    // address bar is put back, because refusing to navigate while leaving
    // the URL pointing at the page you refused is the same lie in reverse.
    if ((HIDDEN_VIEWS[state.sport] || []).includes(h)) {
      history.replaceState({ view: state.view }, "", `#${state.view}`);
      return;
    }
    if (STANDALONE_MODES.includes(h)) { enterStandaloneMode(h); return; }
    exitStandaloneMode();
    switchView(h);
  });

  document.querySelectorAll(".sport-btn").forEach((b) =>
    b.addEventListener("click", () => {
      // The "More" toggle wears .sport-btn for its looks but is not a
      // sport. Without this guard it fell through to the switcher with an
      // undefined data-sport, blanked state.sport, and then matched the
      // active test because undefined === undefined — so opening the menu
      // marked itself as the current league and un-marked the real one.
      if (!b.dataset.sport) return;
      if (STANDALONE_MODES.includes(b.dataset.sport)) { enterStandaloneMode(b.dataset.sport); return; }
      exitStandaloneMode();
      if (state.sport === b.dataset.sport) return;
      state.sport = b.dataset.sport;
      state.search = "";
      const search = document.getElementById("player-search");
      if (search) search.value = "";
      // The roster tab is per-sport now: a team abbreviation and a player
      // search from the league you just left mean nothing in the one you
      // just entered.
      state.rosterQuery = "";
      _rosterOpen = null;
      const rsearch = document.getElementById("roster-search");
      if (rsearch) rsearch.value = "";
      const url = new URL(location.href);
      url.searchParams.set("sport", state.sport);
      history.replaceState(null, "", url);
      // Switching sports from an OPEN menu loads quietly. The skeleton
      // wipe and entrance animations exist for a page you are looking at;
      // firing them under the menu made the board collapse to placeholders
      // and rebuild while you were still choosing — the page appeared to
      // reload and throw you back into the menu. Picking a page closes the
      // menu and shows the finished board.
      applySport();
      load(document.body.classList.contains("menu-open"));
    }));

  const conf = document.getElementById("min-conf"), edge = document.getElementById("min-edge");
  conf.addEventListener("input", () => {
    state.minConf = parseFloat(conf.value);
    document.getElementById("conf-val").textContent = state.minConf.toFixed(1);
    load();
  });
  edge.addEventListener("input", () => {
    state.minEdge = parseFloat(edge.value);
    document.getElementById("edge-val").textContent = `${state.minEdge}%`;
    load();
  });
  const juice = document.getElementById("max-juice");
  juice.addEventListener("input", () => {
    state.maxJuice = parseInt(juice.value, 10);
    document.getElementById("juice-val").textContent = state.maxJuice;
    load();
  });
  document.getElementById("show-all").addEventListener("change", (e) => {
    state.showAll = e.target.checked; renderGameBets(); renderRecommended();
  });
  document.getElementById("player-search").addEventListener("input", (e) => {
    state.search = e.target.value; renderPlayers();
  });
  const rosterSearch = document.getElementById("roster-search");
  if (rosterSearch) rosterSearch.addEventListener("input", (e) => {
    state.rosterQuery = e.target.value;
    // Typing a new query abandons whatever was expanded: the old card
    // would otherwise stay open under a list it no longer belongs to.
    _rosterOpen = null;
    renderRosters();
  });

  const bankrollEl = document.getElementById("bankroll");
  const unitEl = document.getElementById("unit-pct");
  if (state.bankroll) bankrollEl.value = state.bankroll;
  unitEl.value = state.unitPct;
  const onBankrollChange = () => {
    const b = parseFloat(bankrollEl.value);
    state.bankroll = isFinite(b) && b > 0 ? b : null;
    const u = parseFloat(unitEl.value);
    state.unitPct = isFinite(u) && u > 0 ? u : 1.0;
    try {
      localStorage.setItem("ge-bankroll", state.bankroll == null ? "" : String(state.bankroll));
      localStorage.setItem("ge-unit-pct", String(state.unitPct));
    } catch (e) {}
    updateUnitNote();
    renderStats();
    renderBestBets();
    renderGameBets();
    renderRecommended();
    renderPlayers();
  };
  bankrollEl.addEventListener("input", onBankrollChange);
  unitEl.addEventListener("input", onBankrollChange);
  // Brand = home. Every site works this way, so nobody has to be taught
  // it: back to THIS sport's Recommended board, with fresh data. It
  // replaced the Refresh button outright — one control, no ambiguity
  // about which one gets you current numbers.
  const home = document.getElementById("brand-home");
  if (home) {
    home.addEventListener("click", (e) => {
      e.preventDefault();
      goHome();
    });
  }
  document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
  window.addEventListener("resize", moveIndicator);
}

initTheme();
loadBankroll();
bind();
applySport();
updateUnitNote();
initialView();
watchSectionSubs();
initMobileMenu();
initMoreMenu();
initHeaderTuck();
requestAnimationFrame(moveIndicator);
/* The tab labels are set in a web font. Measuring on the next frame reads
   the FALLBACK metrics, so the underline was drawn 114px wide under a 96px
   tab and stayed wrong until something else moved it. Re-measure once the
   real face has loaded. */
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(moveIndicator);
}
// §9: the standing record is masthead chrome, not a page — it renders once
// at boot and is independent of which view or sport is showing.
renderStandingRecord();
load();
