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
  // The NFL and MLB taglines carry the model names — they moved here
  // from the sidebar's Models group when it dissolved (2026-08-17): its
  // three rows were the league chips wearing the model names, and this
  // line is where the identity actually belongs.
  nfl: { logo: "🏈", tagline: "The NFL Book — the pro-bettor prop model",
         gamesTitle: "This week’s stadiums",
         gamesSub: "real stadium shapes, roof state, live wind and the passing "
                   + "conditions each one is playing to right now",
         api: "/api/recommendations", fallback: "data/recommendations.json" },
  mlb: { logo: "⚾", tagline: "Scalpy 2.0 — the MLB prop model",
         gamesTitle: "Tonight’s ballparks",
         gamesSub: "real park shapes, roof state, live wind and the home-run "
                   + "factor each one is playing to right now",
         api: "/api/mlb/recommendations", fallback: "data/mlb_recommendations.json" },
  wnba: { logo: "🏀", tagline: "Scalpy — WNBA probability engine (on probation)",
          gamesTitle: "Tonight’s slate",
          gamesSub: "same minutes-first model as the NBA board, tuned to a "
                    + "40-minute game — and journaled on probation until it "
                    + "has graded enough WNBA results to earn a stake",
          api: "/api/wnba/recommendations", fallback: "data/wnba.json" },
  nba: { logo: "🏀", tagline: "Scalpy — NBA probability engine",
         gamesTitle: "Tonight’s slate",
         gamesSub: "minutes first, distributions not point estimates, every "
                   + "number clamped toward the de-vigged market",
         api: "/api/nba/recommendations", fallback: "data/nba.json" },
  cfb: { logo: "🏈", tagline: "College football — attention is the axis",
         gamesTitle: "Saturday’s board",
         gamesSub: "134 teams, 60+ games, and no book prices a Wednesday MAC "
                   + "game the way it prices Ohio State – Michigan — so the "
                   + "haircut on our own edge is a dial, not a constant",
         api: "/api/cfb/recommendations", fallback: "data/cfb.json" },
};

/* Pages a sport has no engine for. Listed here rather than as conditions
   scattered through applySport, because "which pages does this sport
   have?" is one question and it should have one answer. */
/* THE PREDICTION-DESK CACHE, DECLARED UP HERE ON PURPOSE.
   `let` is hoisted but stays in the temporal dead zone until its
   declaration line RUNS, so a `let` sitting near its own function at the
   bottom of a 14,000-line file throws for anything that reads it sooner.
   Weather and Alerts do exactly that — both read it while rendering, both
   crashed with "Cannot access '_railDeskCache' before initialization",
   and both pages came up blank below the fold. Found by opening every
   view in a browser; nothing in the test suite noticed, because the file
   parses perfectly and the fault only exists at runtime in one order. */
let _railDeskCache = null, _railDeskAt = 0;

const HIDDEN_VIEWS = {
  nba: ["longshots", "weather"],
  // The WNBA has no futures board: engine/futures.py has a shape for it but
  // futures_build.py does not run it, because there is no outrights key for
  // the league and its season is nearly over by the time this ships.
  wnba: ["longshots", "futures", "weather"],
  // §9.1 caps UFC at two legs in ONE fight, and every construction §9.3
  // permits pairs a winner with a method, distance or round-group market.
  // We price fight winners and nothing else, so there is no pair to screen
  // and a tab that can only ever say so is worse than no tab.
  // Futures are a SEASON market. A fight card, a prediction market and a
  // fantasy draft do not have one, and a tab that can only ever say so is
  // worse than no tab.
  // No commission publishes an MMA injury report and ESPN carries no
  // /injuries endpoint for it — what exists is camp rumor, which is
  // exactly what this site does not publish.
  ufc: ["parlays", "futures", "injuries", "weather"],
  polymarket: ["parlays", "futures", "weather"],
  fantasy: ["parlays", "futures", "weather"],
  // CFB has 134 programs and no free player-level feed. A roster tab that
  // can only ever say "no data" is worse than no tab.
  cfb: ["longshots", "trending", "players", "rosters", "weather"],
};

/* College football's 134 identities ride in the payload rather than a
   checked-in file, so they aren't known until the slate lands — hence the
   refresh on every load as well as on every sport switch. The Live tab
   is cross-sport, though: a CFB card drawn while the reader is on the
   MLB page has no CFB payload in state.data, so the last table any
   fetch delivered is kept here and preferred. */
let _cfbTeams = null;
function teamsForSport(sport) {
  if (sport === "mlb") return typeof MLB_TEAMS !== "undefined" ? MLB_TEAMS : {};
  if (sport === "nba") return typeof NBA_TEAMS !== "undefined" ? NBA_TEAMS : {};
  if (sport === "wnba") return typeof WNBA_TEAMS !== "undefined" ? WNBA_TEAMS : {};
  if (sport === "cfb") return _cfbTeams || (state.data && state.data.teams) || {};
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
    setSelected(b, !!b.dataset.sport && b.dataset.sport === state.sport));
  markMoreMenu();
}


/* Selected state, announced as well as drawn.
 *
 * The nav and sport buttons carried their selection in a CSS class only.
 * A class is invisible to assistive tech, so a screen reader read the whole
 * bar as eight identical buttons with no way to tell which board you were
 * on — and these are the controls the site is used through. `aria-current`
 * is the honest marking for "this one is the page you are on": it needs no
 * roving tabindex or arrow-key contract the way role="tab" would, so it
 * cannot be half-implemented into something worse than nothing. */
function setSelected(el, on) {
  el.classList.toggle("active", on);
  if (on) el.setAttribute("aria-current", "page");
  else el.removeAttribute("aria-current");
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
/* U+2212 MINUS SIGN, not U+002D HYPHEN-MINUS. Measured in this site's own
   subset files, because the difference is not a matter of taste:

     Archivo Narrow   + advance 479   - advance 273   − advance 479
     IBM Plex Mono    + ink 476       - ink 290       − ink 476

   In Archivo Narrow the hyphen is 43% narrower than the plus, so a column
   of +3.5 over -3.5 does not line up — the digits sit two hundred units
   apart. Plex Mono is monospaced so the advances match, but its hyphen bar
   is 290 units against the plus's 476: next to each other one reads as a
   stub. The true minus matches the plus exactly in both faces.

   This is a board made almost entirely of ±odds and ±percentages, so it is
   the highest-frequency glyph pair on the site. */
const MINUS = "−";
/* Only a hyphen that is actually a SIGN: one before a digit or a decimal
   point AND not preceded by a word character.
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   That second half was missing in the first cut and it mangled dates —
   `2026-08-07` in a numeric cell came out `2026−08−07`, because every
   hyphen in it is followed by a digit. A sign has nothing but whitespace,
   a delimiter, or the start of the string in front of it.

   Written with a capture rather than a lookbehind so it does not depend on
   a 2023-era Safari. Ranges between numbers (`3-5`) are deliberately left
   alone: they want an en dash, which is a different repair. */
const RE_SIGN = /(^|[^\w])-(?=[\d.])/g;
const trueMinus = (s) => String(s).replace(RE_SIGN, `$1${MINUS}`);

const pct = (x) => `${(x * 100).toFixed(1)}%`;
const signedPct = (x) => trueMinus(`${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);
const american = (o) => (o > 0 ? `+${o}` : trueMinus(`${o}`));
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

/* NFL_MODEL §2.3: "Label your knowledge tiers in every output ... because
   the fix for a bad bet depends on which tier failed."

   A one-word tag rather than a coloured pill, and set in the quietest
   type on the page, because there are up to five of these per card and a
   badge on each would shout louder than the reason it describes. The tag
   is the ANSWER to "why did this lose": a stale feed, a historical
   pattern that did not repeat, or the model's own reasoning — and only
   the third means the model is wrong.

   Classified in Python (`engine/knowledge.py`) and stamped into the slate
   as `reason_tiers`, never re-derived here: a mirrored registry in
   JavaScript would be right the day it was written and silently wrong the
   first time a module adds a reason. An unlabelled reason renders exactly
   as it always did. */
const TIER_LABEL = {
  measured: "measured",
  historical: "historical",
  inference: "inferred",
};

function reasonLI(x, tier) {
  const t = TIER_LABEL[tier]
    ? `<span class="r-tier r-${tier}">${TIER_LABEL[tier]}</span>` : "";
  return `<li class="${NEG_REASON.test(x) ? "neg" : ""}">${escapeHtml(x)}${t}</li>`;
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
  // Two widths of the same fact: the sentence for desktop, the bare age
  // for phones (Ethan, 2026-08-11: the bar was "way too crowded and
  // cutting itself off"). CSS picks; the title carries the sentence
  // everywhere, and the chip's colour already says updated-vs-stale.
  el.innerHTML = (state.livePolling && !stale ? `<span class="live-dot"></span>` : "")
    + `<span class="lr-full">${stale ? `Stale — built ${ago} ago` : `Updated ${ago} ago`}</span>`
    + `<span class="lr-short">${ago}</span>`;
  el.classList.toggle("idle", !state.livePolling && !stale);
  el.classList.toggle("stale", stale);
  el.title = stale
    ? "The server hasn’t rebuilt the board in a while — check that the "
      + "laptop is awake and python3 launch.py is still running."
    : "How long ago the server last rebuilt this board.";
}

function passesFilters(r) {
  // High Confidence Mode: the sidebar switch narrows the whole board to
  // A-grades (quality >= 80 — the same band the journal grades under).
  if (typeof hcmOn === "function" && hcmOn() && (r.quality || 0) < 80) return false;
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
      ${escapeHtml(t.note || "This league’s tuning has not been fitted to its own results yet.")}
      Everything below is priced and journaled exactly as a live board would be,
      so the record it builds is real — it just doesn’t stake anything until that
      record clears the promotion bar${t.inherited_from
        ? ` (the numbers are the ${escapeHtml(t.inherited_from.toUpperCase())} model’s for now)` : ""}.
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
      because by then a team’s own results have answered the question.
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
  renderSlateHorizon();
  renderTopPicks();
  renderHomePerf();
  renderRail();
  renderGameBets();
  renderIncentives();
  renderRestWatch();
  renderInjuryWatch();
  renderPreseason();
  renderRecommended();
  // AFTER the renderers, always. Which rooms exist is decided by what
  // they just wrote — grouping first would judge every block empty and
  // draw a single tab.
  groupRecommended();
  // Tonight owns its own host and is not one of the board's rooms, so it
  // draws after the grouping rather than between the board and it — a
  // call inserted in that gap reads as part of the sequence the grouping
  // depends on, which is exactly what a test caught it as.
  renderTonight();
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
  if (state.view === "prop") renderPropPage();
  // Rosters live in their own per-sport payload rather than the slate, so
  // nothing above redraws them. Switching leagues while sitting on the tab
  // left the previous league's teams on screen under the new league's
  // header — the same class of bug as a standalone page keeping a stale
  // badge, and it looks like the switch silently failed.
  if (state.view === "live") renderLiveBoard();
  if (state.view === "rosters") renderRosters();
  if (state.view === "injuries") renderInjuries();
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
       replaced by this year’s evidence within a few weeks of kickoff.</div>`
    : "";
  return `${warn}${recDisclosure("How these numbers are made", `${escapeHtml(d.doctrine || "")}
    Each remaining game is one draw from the two teams' ratings plus home
    advantage; wins accumulate, division winners are the most wins, the
    playoff field fills per the league’s own shape, and the bracket is played
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
      book’s implied one, in points. A book posts futures early and revisits
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
      <span class="sub">— each player’s rate so far, times the games his team has
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
          <span class="fx-pav" title="Share of his team’s games he has actually played">${(p.availability * 100).toFixed(0)}%</span>
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
      <b>${gap.players_found || 0}</b> player(s) with any history for tonight’s
      teams — a prop needs three games. Nothing is broken and no odds are
      wasted; the league just hasn’t been ingested yet.<br><br>
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

  /* PRESEASON IS NOT "NOTHING SCHEDULED". Ethan, 2026-08-14: "preseason
     started every other team for NFL yesterday and we didn't recommend
     props or anything like that."

     Not pricing preseason is deliberate and the Preseason block below
     says so in as many words. The failure was that the block below is
     BELOW: at the top of the same page, where he actually looked, this
     panel was saying "No games on the board right now — nothing is
     scheduled or in progress", with sixteen exhibition games listed
     further down the same screen. One page, two answers, and the one
     that reads first was the wrong one.

     The reason has to travel to where the question gets asked. */
  const pre = state.preseason;
  const preLeft = pre && pre.total ? (pre.total - (pre.complete || 0)) : 0;
  const preOn = !!pre && (state.sport || "nfl") === "nfl" && !!pre.total
    && (!pre.show_until || new Date().toISOString().slice(0, 10) <= pre.show_until);
  if (preOn) {
    el.innerHTML = `<div class="es-icon">${icon("calendar", 30)}</div>
      <div class="es-title">Preseason is on — and nothing in it is priced</div>
      <div class="es-sub">${pre.complete || 0} of ${pre.total} exhibition
      game(s) played${preLeft ? `, ${preLeft} still to come` : ""}. The
      schedule and scores are below.<br><br>
      This board stays empty on purpose. Every prop here is volume ×
      efficiency over prior games, and in August a starter plays a series
      and a half behind a line that will not start together again — a
      number built on last season’s snaps is not a worse answer, it is an
      answer about a different event. We have also never ingested a
      preseason snap, so there is nothing to fit a preseason model on.
      The regular-season board opens in Week 1.</div>`;
    document.getElementById("games-title").style.display = "none";
    return;
  }
  el.innerHTML = state.data.status === "not built"
    ? `<div class="es-icon">${icon("clock", 30)}</div><div class="es-title">This slate hasn’t been built yet</div>
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

/* WHO a bet belongs to, as one mark — the rule every board reads from.
   Ethan, 2026-08-12: "head shots or team logos next to the props
   depending on if they are a player prop or team prop. if its a game
   total or something, we can show the sports logo."

   A player prop wears the player's face. A side (moneyline, spread,
   team total) wears that team's logo. A game total belongs to the game
   itself and wears the league's mark — the only honest answer when both
   teams are equally the subject. Every layer falls back to the drawn
   chip underneath it, so a dead CDN costs nothing. */
const TEAM_SIDE_MARKETS = new Set(["moneyline", "spread", "team_total"]);

function betMark(r, size = 30) {
  const market = String(r.market || r.bet_type || "").toLowerCase();
  if (market === "total") return leagueMark(state.sport, size);
  if (TEAM_SIDE_MARKETS.has(market) || (!r.player && r.team))
    return teamMark(r.team || r.player, size);
  // A prop: a real name, and the face if the payload carries one.
  return playerAvatar(r.player, r.team, { size, headshot: r.headshot });
}

/* One line on the board when the selection haircut is actually moving the
   numbers under it. Silent when it is not: a measured-but-not-applied fit
   is a Record-page detail, and the amber rail means "a condition is live",
   never "there is a page about this somewhere". */
function haircutLine(sh) {
  if (!sh || !sh.live) return "";
  const p = sh.pooled || {};
  const applied = Object.values(sh.sports || {}).filter((e) => e && e.applied);
  const lead = p.applied ? p : (applied[0] || {});
  if (lead.claimed == null) return "";
  return `<p style="margin:0;padding:8px 14px;border-left:3px solid var(--brand);
             background:var(--panel-3);font-size:var(--fs-sm);color:var(--text-body)">
    <b style="color:var(--brand)">These probabilities are already cut.</b>
    Over ${lead.n} settled bets we claimed ${(lead.claimed * 100).toFixed(1)}% and
    landed ${(lead.landed * 100).toFixed(1)}%, so every claim below is moved
    ${lead.shift.toFixed(3)} in log-odds before its edge, EV and stake are
    computed — a 55% call ships as ${(lead.example_55 * 100).toFixed(1)}%. Fewer
    picks clear the bar and the ones that do ask for less. The working is on the
    <b style="color:var(--text)">Record</b> page.</p>`;
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
      id: betMark(b),
      label: `${b.headline} · ${b.matchup} ${american(b.odds)}`,
      game: whenLabel(b.date, b.kickoff),
      metric: `${signedPct(b.ev_per_unit)} EV`, stake: b.stake_units, grade: b.grade,
      why: anchor || "sharp-anchor price gap — backtested +13.5% against real closes" });
  }
  for (const b of sig.modelBets) {
    picks.push({ tag: "GAME", color: "var(--brand)", quality: b.quality || b.confidence * 10 || 0,
      id: betMark(b),
      label: `${b.headline} · ${b.matchup} ${american(b.odds)}`,
      game: whenLabel(b.date, b.kickoff),
      metric: signedPct(b.edge), stake: b.stake_units, grade: b.grade,
      why: "game bet that cleared every gate" });
  }
  for (const r of sig.props) {
    const twin = staleByKey.get(propKey(r.player, r.market));
    picks.push({ tag: "PROP", color: "var(--brand)", quality: r.quality || r.confidence * 10 || 0,
      id: betMark(r), open: propAttrs(r),
      label: `${r.player} ${r.side} ${r.line} ${r.market_label} ${american(r.odds)} (${r.book})`,
      game: propGameLine(r),
      metric: signedPct(r.edge), stake: r.stake_units, grade: r.grade,
      /* THE NUMBER THAT SIZED THE BET, beside the one that headlines it.
         `edge` is measured against the de-vigged fair; Kelly sizes on the
         margin over the PRICE WE GET, which is smaller by the juice. A
         board showing only the first advertises +4.3% on a bet with 0.6
         points of real margin, and the stake beside it then looks
         arbitrary — Ethan, 2026-08-12: "It doesn't make any sense and
         feels random." It never was; it was unreadable. */
      why: (r.quality != null ? `quality ${r.quality}/100 · Tier ${r.tier} · ${r.volatility}` : "cleared every gate")
        + (r.net_edge != null
           ? ` · ${signedPct(r.net_edge)} over the price you get`
           : "")
        + (r.stake_basis ? ` · stake: ${r.stake_basis}` : "")
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
  // Every probability below is post-haircut. Said once, here, rather than
  // on 26 rows: the numbers are already corrected, and a reader who does
  // not know that will read them as the model's raw opinion.
  const haircutNote = haircutLine(rec.selection_haircut);

  const pickRow = (p, i) => `
    <div class="${p.open ? "openable" : ""}"${p.open || ""}
         style="display:flex;gap:12px;align-items:flex-start;padding:12px 14px;
                border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="opacity:.45;min-width:18px;font-weight:700">${i + 1}</span>
      ${p.id ? `<span class="pick-id">${p.id}</span>` : ""}
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
      ${haircutNote}
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
        ? `The gate counts below ran against the last pull, not today’s prices — read them
           as stale, not as a verdict on today’s slate.`
        : `That sentence is the system working, not failing — every market tonight either
           missed the tier’s edge bar, failed a gate, or graded below 70. Loosening the
           sliders shows what was held and why.`}</p>
      ${/* THE FUNNEL IS NOT REPEATED HERE. Ethan, 2026-08-14: "we are
            showing 'where props died' twice."

            Two independent blocks were drawing it, and on the one night
            that matters — nothing recommended — both fired: this card,
            and the board's own empty message a scroll below. Same table,
            same numbers, twice on one screen, which reads as a rendering
            fault rather than as an explanation.

            It stays on the BOARD rather than here, and that is a
            deliberate choice rather than a coin flip: the funnel is an
            answer to "why is this list blank", the list is down there,
            and the sliders its copy tells you to loosen sit beside it.
            This card keeps its own sentence, which stands on its own.

            A first-come-wins flag would have been the other way to do it
            and it would have been worse — `renderBestBets` is async, so
            which block won the race would change between refreshes and
            the table would appear to move around the page. */""}
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
        recommendations. They’re the signal families the site paper-tracks in quarantined
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
        These WERE tonight’s picks — journaled when they cleared the bar. The line has
        moved since, and at the current number they no longer qualify, so: the bet rides
        as placed, but don’t add more at today’s price. Tracked live on the Live tab.</p>
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
                    ? ` (line now ${cur.line})` : ""} — doesn’t clear the bar at this number`
                : ` · no live quote for this market right now`}</span>
          </span>
          <span style="text-align:right;white-space:nowrap;font-size:var(--fs-sm);color:var(--text-mute)">
            ${b.stake_units > 0 ? `${Number(b.stake_units).toFixed(2)}u<br>` : ""}riding</span>
        </div>`).join("")}
    </div>` : "";

  if (!picks.length && !signals.length && !ridden.length) { host.innerHTML = ""; return; }
  host.innerHTML = `
    <div class="section-title">Tonight’s picks
      <span class="sub">— the one designated space for what we’d actually bet. If it isn’t
      in this box, it isn’t a pick.</span></div>
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
  return `Today’s book prices haven’t been pulled yet — the window opens ${t}.`;
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
      ? `today’s pricing starts <b>${clock(os.window_opens_at)}</b>`
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
    calibration: "market’s calibration unreliable — closed until refit",
    tier_edge_bar: "edge under the tier’s minimum",
    price_net: "price doesn’t clear break-even",
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
    <div style="font-size:var(--fs-sm);font-weight:700;margin-bottom:2px">Where tonight’s props died</div>
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
        <span class="sub">— every journaled bet on today’s card, tracked while its game runs</span></div>
      <div class="card"><p class="loading">No open bets on today’s card. A pick journals the
        moment it’s recommended and lives here until it settles — live progress bars, at-bat
        situation, and provisional grades as the games run.</p></div>`;
    return;
  }

  const ml = (r) => r.market === "moneyline";
  /* A team market's `player` field holds an ABBREVIATION and a game
     total's holds the journal key "AWAY@HOME" — neither is a name to
     print. The matchup already sits on the line below every row, so a
     total says what it is and lets the row underneath say which game. */
  const betTxt = (r) => {
    if (ml(r)) return `${escapeHtml(teamName(r.player))} Moneyline`;
    if (r.market === "total")
      return `${escapeHtml(r.market_label)} ${escapeHtml(r.side)} ${r.line}`;
    if (r.market === "spread")
      // Every journaled spread carries side OVER — the signed number is
      // what states the direction, so print that instead of the word.
      return `${escapeHtml(teamName(r.player))} ${r.line > 0 ? "+" : ""}${r.line} ${escapeHtml(r.market_label)}`;
    if (r.market === "team_total")
      return `${escapeHtml(teamName(r.player))} ${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}`;
    return `${escapeHtml(r.player)} ${escapeHtml(r.side)} ${r.line} ${escapeHtml(r.market_label)}`;
  };
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
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${r.current} already — under ${r.line} can’t cash</span>`;
    /* No chances left: the stat never passed the line, but nothing can
       move it now — the pitcher is out of the game, or the hitter's last
       turn through the order has gone by. Without this the row read
       "tracking · needs 2 more" all night about a bet that was over. */
    if (r.status === "dead")
      return `<span style="color:var(--bad);font-weight:800">${icon('cross')} NO CHANCES LEFT</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">stuck on ${r.current} — ${
          r.market === "strikeouts" ? "out of the game" : "won’t bat again"}</span>`;
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
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">couldn’t map to a game this cycle — still settles overnight</span>`;
    if (r.current != null) {
      const needs = r.side === "OVER"
        ? `needs ${Math.max(1, Math.ceil(r.line - r.current))} more`
        : `must stay at or under ${Math.floor(r.line)}`;
      return `<span style="font-weight:800">${r.current} so far</span>
        <span style="display:block;color:var(--text-mute);font-size:var(--fs-xs)">${needs}</span>`;
    }
    return `<span style="color:var(--text-mute)">in play</span>`;
  };
  /* The live win-probability chart on the bet's own row (2026-08-18,
     Ethan: "we should be showing that for ALL live games and also for
     our live bets"). TEAM markets only — for a moneyline, spread or
     team total, the game's tracked win probability IS the bet's market
     family, oriented to the bet's team. A prop's chance is a different
     quantity, and drawing the game line under a strikeouts bet would
     invite reading it as the prop's odds. The track lives on the BOARD
     game (the fast scoreboard has no odds), so the join runs against
     state.data.games by matchup. */
  const TEAM_MKTS = new Set(["moneyline", "spread", "team_total", "total"]);
  const betTrack = (r) => {
    if (r.phase !== "live" || !TEAM_MKTS.has(r.market) || !r.game) return "";
    const g = (state.data.games || []).find((x) =>
      x.home === r.game.home && x.away === r.game.away);
    if (!g || !g.line_track) return "";
    const team = r.market === "total" ? null : r.player;
    return `<div style="margin-top:6px">${
      lineTrackHTML(g, team ? { team } : {})}</div>`;
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
    const bad = r.status === "busted" || r.status === "lost_pending"
      || r.status === "dead";
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
  /* What the bet is worth RIGHT NOW.

     Ethan, 2026-08-14: "Are we able too track the win probability of bets
     we have made live too?" For a moneyline this is the live market's own
     de-vigged price; for a prop it is ours, computed from what the player
     has banked against how many cracks at it he has left — because books
     pull prop markets at first pitch and charge per game to be asked.

     The two are labelled differently on purpose. A market number and a
     model number are not the same kind of claim, and a reader who cannot
     tell which one they are looking at cannot tell whether we agree with
     the book or ARE the book. */
  const winProb = (r) => {
    const p = r.live_prob;
    if (p == null || r.phase !== "live") return "";
    // Certainty is not a forecast: a banked over says CLEARED and a bet
    // with no chances left says NO CHANCES LEFT, both in words, in the
    // verdict column. Repeating either as a percentage adds nothing and
    // reads as a model boasting about a fact it did not predict.
    if (p <= 0 || p >= 1) return "";
    // A long shot at 0.4% is not 0%, and rounding it there would put the
    // same number on it as a bet that is already dead. The two are very
    // different things to be holding.
    const pct = p < 0.005 ? "<1" : p > 0.995 ? ">99" : String(Math.round(p * 100));
    const src = r.market === "moneyline"
      ? "live market, de‑vigged"
      : "our model, from what’s left";
    const tone = p >= 0.60 ? "var(--good)" : p <= 0.25 ? "var(--bad)" : "var(--text)";
    return `
      <span style="display:block;margin-top:5px;font-size:var(--fs-xs);color:var(--text-mute)">
        <b style="color:${tone};font-size:var(--fs-sm)">${pct}%</b> to cash from here
        · <span style="opacity:.85">${src}</span></span>`;
  };
  /* Where the market has moved, for the two bets that carry a line.

     A spread or total gets no live win probability and the reason is not
     cost — both markets are pulled now. It is that the market quotes them
     at ITS number: a live price on −0.5 says nothing directly about a
     −1.5 ticket. Converting needs the dispersion of finals around a live
     line, which we have no sample of, so this reports the fact instead of
     manufacturing the forecast. */
  const marketLine = (r) => {
    const now = r.live_market;
    if (now == null || r.phase !== "live") return "";
    const sign = (v) => `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}`;
    const mine = r.market === "total"
      ? `${escapeHtml(r.side)} ${Number(r.line).toFixed(1)}` : sign(r.line);
    const theirs = r.market === "total"
      ? Number(now).toFixed(1) : sign(now);
    /* Which way is GOOD is not obvious and the first version had the
       spread backwards. A ticket on CHC -1.5 needs CHC to win by two; a
       market that has drifted to -0.5 now expects them to win by one, so
       the number moving UP (toward zero, or past it) is the bet getting
       worse. The team being MORE favoured than the number you took is the
       good direction, which on a signed spread is a SMALLER number.
       Totals are the intuitive way round: an over wants the line to
       climb. Both are compared on the bet's own side — `_live_market`
       flips the stored home spread for an away ticket. */
    const better = r.market === "total"
      ? (r.side === "OVER" ? now > r.line : now < r.line)
      : Number(now) < Number(r.line);
    return `
      <span style="display:block;margin-top:5px;font-size:var(--fs-xs);color:var(--text-mute)">
        market now <b style="color:${better ? "var(--good)" : "var(--bad)"}">${theirs}</b>
        · you have ${mine} · <span style="opacity:.85">live line, no forecast</span></span>`;
  };
  const nLive = rows.filter((r) => r.phase === "live").length;

  host.innerHTML = `
    <div class="section-title">${nLive
        ? `<span style="color:var(--bad)">${icon('dot')}</span>`
        : `<span style="color:var(--brand)">${icon('dot')}</span>`} Open bets
      <span class="sub">— every journaled bet on today’s card: live with real-time progress,
      finished awaiting the official settle, or waiting on first pitch. Never new in-play
      bets — everything here was placed pre-game.</span></div>
    <div class="card" style="padding:0;border-left:3px solid ${nLive ? "var(--bad)" : "var(--brand)"}">
      ${rows.map((r) => `
        <div style="display:flex;gap:12px;align-items:center;padding:11px 14px;
                    border-bottom:1px solid rgba(255,255,255,.05)${r.phase === "upcoming" ? ";opacity:.75" : ""}">
          ${r.phase === "live" ? `<span class="live-dot" style="flex-shrink:0"></span>`
            : `<span style="width:8px;flex-shrink:0"></span>`}
          <span class="pick-id">${betMark(r, 28)}</span>
          <span style="flex:1;min-width:0">
            <strong>${betTxt(r)}</strong>
            <span style="color:var(--text-mute)"> · placed ${american(r.odds)}${
              r.stake_units > 0 ? ` · ${Number(r.stake_units).toFixed(2)}u` : ""}</span>
            <span style="display:block;color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">${gameLine(r.game)}</span>
            ${situationLine(r)}
            ${offBoard(r) ? `<span style="display:block;font-size:var(--fs-xs);color:var(--warn);margin-top:2px">
              ${icon('warn')} the price has moved off the bar since this was journaled — riding at
              ${american(r.odds)} as placed (also listed under Tonight’s Picks).</span>` : ""}
            ${progressBar(r)}
            ${winProb(r)}
            ${marketLine(r)}
            ${betTrack(r)}
          </span>
          <span style="text-align:right;white-space:nowrap">${statusBits(r)}</span>
        </div>`).join("")}
      <p style="padding:8px 14px;margin:0;font-size:var(--fs-xs);color:var(--text-mute)">
        ${rows.length} open bet(s) on today’s card${elsewhere
          ? ` · ${elsewhere} open on other boards — a different sport, or a week that has not been played yet.`
            + ` This tab tracks THIS league’s card; the Record page counts them all`
          : ""}. A bet journals the moment it’s recommended and stays here until it
        settles — even if the pick later drops off Tonight’s Picks because prices moved.
        Stat lines update with the board’s refresh cycle; every bet settles
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
    : `sampler journals the hot side’s moneyline in every hot-vs-cold matchup `
      + `at the real price — grades on the Record page`;
  const row = (r, tone) => `
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;
                padding:9px 4px;border-bottom:1px solid rgba(255,255,255,.05)">
      <span style="display:flex;align-items:center;gap:8px;flex:1;min-width:150px">
        ${teamMark(r.team, 18)} <strong>${escapeHtml(teamName(r.team))}</strong></span>
      <span style="white-space:nowrap">${r.w}-${r.l}</span>
      <span class="val ${tone}" style="white-space:nowrap;min-width:88px;text-align:right"
            title="Run differential per game over the window minus the team’s own season number — hot relative to itself, not the league">
        ${r.delta_diff >= 0 ? "+" : ""}${r.delta_diff.toFixed(1)} r/g</span>
      <span style="min-width:34px;text-align:right;color:${r.streak > 0 ? "var(--good)" : "var(--bad)"}">
        ${r.streak > 0 ? `W${r.streak}` : r.streak < 0 ? `L${-r.streak}` : "—"}</span>
    </div>`;
  // THE PARAMETER IS `mark`, and it has to be. The emoji sweep (#50,
  // 2026-08-02) replaced the heading's emoji with `${mark}` and left the
  // parameter called `icon`, so this threw "mark is not defined" every
  // time a board actually had team form to show. It is inside an async
  // function, so the throw became an unhandled rejection rather than a
  // visible error: the page finished rendering and simply lost this
  // block. Thirteen days, every MLB-data view, nobody could see it —
  // until a headless sweep read the console.
  //
  // `mark` rather than `icon` for the second reason too: `icon` is a
  // global function here, and a parameter of that name shadows it inside
  // this closure.
  const col = (title, mark, rows, tone) => `
    <div class="trend-col">
      <h3>${mark} ${title}</h3>
      ${rows.length ? rows.map((r) => row(r, tone)).join("")
        : `<div class="empty" style="padding:18px">Nobody qualifies.</div>`}
    </div>`;
  host.innerHTML = `
    <div class="section-title">Team form — last ${tf.window_days || 7} days
      <span class="sub">— from our own ingested results, refreshed nightly. Tracked and
      measured before it’s ever allowed to move a bet.</span></div>
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

/* ============================================================
   NFL preseason — the fixture list, and nothing priced
   ============================================================
   Live for about five weeks a year, which is why it is a block on the
   board rather than a tab in the nav: a permanent destination that says
   nothing for eleven months is worse than no destination. It retires
   itself by comparing today against the last fixture's date, so nobody
   has to remember to take it down in September.

   IT CARRIES NO PROJECTION, NO PRICE AND NO PICK, on purpose. Preseason
   is the one part of the calendar where this engine's premise fails — a
   projection is volume times efficiency measured over prior games, and in
   August a starter plays a series and a half behind a line that will not
   start together again. A prop priced off last season's usage is not a
   slightly worse number, it is a number about a different event.
   ============================================================ */
let _preseasonCache;

async function loadPreseason() {
  if (_preseasonCache !== undefined) return _preseasonCache;
  try {
    const res = await fetch("data/nfl_preseason.json?t=" + (Date.now() / 60000 | 0));
    _preseasonCache = res.ok ? await res.json() : null;
  } catch (e) { _preseasonCache = null; }
  return _preseasonCache;
}

function preseasonScoreHTML(g) {
  // Label from `state`, never from the presence of a number: ESPN sends
  // score "0" for a game nobody has played, so "has a score" and "has been
  // played" are different questions. Asking the wrong one tagged 48
  // scheduled fixtures as in progress on the first real run.
  if (g.state === "post") {
    const aw = g.away_score, hm = g.home_score;
    const awWon = aw > hm, hmWon = hm > aw;
    return `<span class="pre-score">
      <b class="${awWon ? "won" : ""}">${aw}</b>–<b class="${hmWon ? "won" : ""}">${hm}</b>
    </span><span class="pre-state">Final</span>`;
  }
  if (g.state === "in") {
    return `<span class="pre-score">${g.away_score}–${g.home_score}</span>` +
           `<span class="pre-state live">Live</span>`;
  }
  // Local time, not the feed's UTC. ESPN sends Z-stamped kickoffs, and
  // printing them raw put "23:00 UTC" beside every fixture — a number no
  // one reading this is in, for a schedule whose entire job is telling you
  // when to watch.
  let t = "";
  if (g.kickoff) {
    const d = new Date(g.kickoff);
    if (!isNaN(d)) t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  return `<span class="pre-state">${escapeHtml(t || "—")}</span>`;
}

function preseasonGameHTML(g) {
  const teams = (typeof teamsForSport === "function")
    ? teamsForSport("nfl") : {};
  const mark = (ab) => {
    const m = teams[ab] || {};
    return `<span class="pre-team" style="border-color:${
      escapeHtml(m.primary || "#39405166")}">${escapeHtml(ab)}</span>`;
  };
  return `<div class="pre-game${g.state === "in" ? " is-live" : ""}">
    <span class="pre-date">${escapeHtml((g.date || "").slice(5))}</span>
    ${mark(g.away)}<span class="pre-at">@</span>${mark(g.home)}
    ${preseasonScoreHTML(g)}
    ${g.indoor ? '<span class="pre-roof">indoor</span>' : ""}
    ${starterScanHTML(g)}
    ${preseasonLineHTML(g)}
  </div>`;
}

/* WHO IS LIKELY TO PLAY, per side.

   Ethan, 2026-08-14: "make sure to implement scanning to see which teams
   will be playing starters and which ones wont."

   The measurement is the starting quarterback's preseason attempt count,
   because he is on the field exactly as long as the staff wants the first
   team out there and he is the one man guaranteed to leave a mark in a
   box score when he is. Bands come from the league's own distribution
   (`prestarters.bands`), not from a number somebody picked.

   A FIXTURE THAT HAS NOT BEEN PLAYED HAS NO TEAM SHEET, and no free feed
   announces who is sitting. What this shows is a HABIT — what the same
   staff has done before — and it says so, because a habit printed as a
   fact is the exact way this feature would start lying. */
function starterScanHTML(g) {
  const scan = ((state.preseason || {}).starter_scan || {});
  const row = (scan.games || []).find(
    (x) => x.home === g.home && x.away === g.away && x.date === g.date);
  if (!row) return "";
  const tone = { rests: "down", mixed: "warn", plays: "up" };
  const cells = ["away", "home"].map((side) => {
    const s = row.sides[side];
    if (!s || s.verdict === "unknown") return "";
    // THE COUNTS, NOT THE MEAN. A staff that sat its man three Augusts and
    // threw twelve in the fourth has a mean of three, which describes none
    // of the four outings. "played 1 of 4" does.
    // AND THE COUNTS ARE THE CLUB'S, NOT THIS MAN'S. Each past August is
    // measured against its own starter, so "2 of 5" is Cleveland across
    // five staffs — printed straight after "Shedeur Sanders" it credited a
    // 2025 rookie with five past outings. The team owns the history; the
    // quarterback named is who we expect to see this year.
    const of = s.played_of || [];
    const shape = of.length === 2 && of[1]
      ? `starter played ${of[0]} of ${of[1]}${
          s.att_when_played ? `, ${Number(s.att_when_played).toFixed(0)} att when he did` : ""}`
      : "";
    return `<span class="pre-scan-side">
      <b>${escapeHtml(s.team)}</b>
      <span class="chip ${tone[s.verdict] || ""}">${escapeHtml(s.verdict)}</span>
      ${shape ? `<span class="pre-scan-n">${escapeHtml(shape)}</span>` : ""}
      ${s.qb ? `<span class="pre-scan-qb">${escapeHtml(s.qb)}</span>` : ""}</span>`;
  }).filter(Boolean).join("");
  if (!cells) return "";
  return `<div class="pre-scan">${cells}
    <span class="pre-scan-note">habit, not a team sheet</span></div>`;
}

/* WHAT THE BOOK THINKS, beside what the coaches have done.

   Ethan, 2026-08-14: "i wanna show props for the pre season. i wanna show
   either money lines or over unders or whatever i dont car."

   This is the MARKET's number and only the market's number. There is no
   model price beside it, no edge and no pick, because the fit that would
   justify one has not convicted — `engine/nfl/prefit` measures whether
   starter usage moves an August result and `prices_allowed()` is hard
   False until the residual has been checked against posted lines we only
   started recording on 2026-08-14.

   So: posted numbers, and the reader draws their own line between "SF has
   played its starters 22 attempts a game in past Augusts" and "the market
   has them -3". Deliberately RAW prices rather than an implied
   percentage — a de-vigged probability on a card looks like a forecast,
   and this page does not have one. */
function preseasonLineHTML(g) {
  const m = g.market;
  if (!m) return "";
  const px = (v) => `${v > 0 ? "+" : ""}${v}`;
  const bits = [];
  if (m.spread != null) {
    // Stored from the HOME team's side — see parse_event_spreads.
    bits.push(`${escapeHtml(g.home)} ${px(Number(m.spread))}`);
  }
  if (m.total != null) bits.push(`o/u ${Number(m.total)}`);
  if (m.away_odds != null && m.home_odds != null) {
    bits.push(`${escapeHtml(g.away)} ${px(m.away_odds)}`
      + ` / ${escapeHtml(g.home)} ${px(m.home_odds)}`);
  }
  if (!bits.length) return "";
  return `<div class="pre-line">
    <span class="pre-line-lab">market</span>
    ${bits.map(b => `<span class="pre-line-n">${b}</span>`).join("")}
    ${m.books ? `<span class="pre-line-books">${m.books} book${
      m.books === 1 ? "" : "s"}</span>` : ""}
  </div>`;
}

/* WHY THERE IS A LINE AND NO PICK — said once, at the top, in the state
   the measurement is actually in.

   Three answers, and "never measured" is a different sentence from "we
   measured and there is nothing there". A block that just stays quiet
   makes those two look identical, which is how a page ends up implying it
   checked something it never ran. */
function preseasonFitHTML(data) {
  const f = (data || {}).fit;
  if (!f || !f.verdict) {
    return `Whether any of it is <i>predictable</i> has not been measured
      yet — run <code>python3 launch.py --prefit</code>.`;
  }
  const span = (f.seasons || []).length
    ? ` across ${f.seasons.length} August${f.seasons.length === 1 ? "" : "s"}`
    : "";
  if (f.verdict === "unmeasurable") {
    // A predictor that never took a second value. NOT a negative result —
    // the two look identical in a report and must not look identical here.
    return `The measurement could not run — a predictor it needs is empty
      in our data, so nothing has been concluded either way.`;
  }
  if (f.verdict === "insufficient") {
    return `Measured on ${f.n} game(s)${span} — not enough to conclude
      anything either way.`;
  }
  if (f.verdict === "no") {
    // TWO DIFFERENT NEGATIVES. A pair that failed on effect size has been
    // measured and is too small to matter. A pair that cleared the effect
    // and missed only significance has NOT been shown to be absent — it is
    // unresolvable at this sample — and printing the first sentence for
    // the second case claims more than the arithmetic did.
    if (f.noisy) {
      return `Measured on ${f.n} game(s)${span}: an effect may be there but
        ${f.n_scored || "this"} game(s) cannot resolve it${
        f.n_for_p ? ` — that would take roughly ${f.n_for_p.toLocaleString()},
        and an August supplies about 49` : ""}. Nothing is priced on a
        maybe.`;
    }
    return `Measured on ${f.n} game(s)${span}: starter usage does not
      predict an August result by enough to bet, so nothing is.`;
  }
  return `Measured on ${f.n} game(s)${span}: the effect is real. It is
    still not priced — that needs the posted numbers checked against it,
    and those only started being recorded this August.`;
}

async function renderPreseason() {
  const host = document.getElementById("preseason-board");
  if (!host) return;
  host.innerHTML = "";
  if ((state.sport || "nfl") !== "nfl") return;
  const data = await loadPreseason();
  if (!data || !data.total || !data.weeks) return;
  // The empty-slate panel needs this too, and it runs SYNCHRONOUSLY well
  // before the fetch lands. Stashing it here and re-running that panel is
  // what lets the top of the page stop contradicting the bottom of it —
  // see the note in renderEmptySlate.
  state.preseason = data;
  if (typeof renderEmptySlate === "function") setTimeout(renderEmptySlate, 0);
  // The horizon note reads `state.preseason`, and on the first pass this
  // fetch lands after it has already drawn. Re-run it now that the answer
  // exists — the same reason renderEmptySlate is poked above.
  if (typeof renderSlateHorizon === "function") setTimeout(renderSlateHorizon, 0);

  // Self-retiring. `show_until` is the last fixture's date; once it is
  // past, this block stops existing without anyone editing anything.
  const today = new Date().toISOString().slice(0, 10);
  if (data.show_until && today > data.show_until) return;

  // Only ONE week is expanded: the first that still has a game to play.
  // All four open is 49 rows and 2,168px of board — more than a screen,
  // below the picks, for a list whose useful part is "what is on next".
  // The rest are one click away and say enough collapsed to know whether
  // to bother (16 games · all final).
  const openWeek = data.weeks.find(w => w.games.some(g => (g.date || "") >= today))
                   || data.weeks[data.weeks.length - 1];

  const left = data.days_until;
  const when = left === null || left === undefined ? ""
    : left > 0 ? `starts in ${left} day${left === 1 ? "" : "s"}`
    : left === 0 ? "starts today"
    : `${data.complete} of ${data.total} played`;

  host.innerHTML = `
    <div class="section-title">Preseason
      <span class="sub">— ${escapeHtml(String(data.season))} exhibition schedule and scores${
        when ? ", " + escapeHtml(when) : ""}</span>
    </div>
    <div class="card pre-card">
      <p class="pre-note">Schedule, results and the <b>book’s</b> posted
        number — <b>nothing here is ours</b>. Preseason usage is not the
        season’s: starters play a series behind a line that will not start
        together again, so a projection built on last year’s snaps is a
        number about a different event. ${preseasonFitHTML(data)}</p>
      ${data.weeks.map(w => preseasonWeekHTML(w, w === openWeek)).join("")}
    </div>`;
}

function preseasonWeekHTML(w, isOpen) {
  const played = w.games.filter(g => g.state === "post").length;
  const live = w.games.some(g => g.state === "in");
  const dates = w.games.map(g => g.date).filter(Boolean).sort();
  const span = dates.length
    ? (dates[0] === dates[dates.length - 1] ? dates[0].slice(5)
       : `${dates[0].slice(5)}–${dates[dates.length - 1].slice(5)}`)
    : "";
  const note = live ? "live now"
    : played === w.games.length ? "all final"
    : played ? `${played} of ${w.games.length} played`
    : span;
  return `<details class="pre-week"${isOpen ? " open" : ""}>
    <summary class="pre-week-head">Week ${w.week === null ? "?" : w.week}
      <span class="pre-week-n">${w.games.length} game${
        w.games.length === 1 ? "" : "s"}${note ? " · " + escapeHtml(note) : ""}</span>
    </summary>
    ${w.games.map(preseasonGameHTML).join("")}
  </details>`;
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
      <span class="sub">— the playoff picture’s usage risks. A clinched team
      may rest starters, an eliminated one may shut veterans down, and an
      announced rest flips its props to Pass on this board — a season-usage
      prop on a benched rotation is a stale price, not an edge.</span></div>
    <div class="card" style="padding:0">${body}</div>`;
}

/* ------------------------------------------------------------------
   Injury watch — tonight's teams only, joined from the league board.

   The Injuries page answers "who is out, league-wide"; this block
   answers the narrower question a bettor actually has at 6pm: is
   anyone ON TONIGHT'S SLATE carrying a designation my price might not
   know about yet? Only RECENT filings show (ten days) — a fresh
   Questionable is the one that can be mispriced; a two-month IL entry
   is already in every number on this site. Context that shades a pick
   without being one, so it lives in the Watchlists room and journals
   nothing. */
let _injCache = { at: 0, data: null };

/* ESPN names teams in full ("Arizona Cardinals"); the slate carries
   abbreviations. The join goes through the sport's own TEAMS table by
   full name first, nickname as fallback — and an unmatched name simply
   doesn't join, because a wrong-team injury row is worse than a
   missing one. */
function injAbbrIndex() {
  const idx = {};
  for (const [abbr, t] of Object.entries(window.ACTIVE_TEAMS || {})) {
    const v = t || {};
    for (const key of [v.name, v.nick && `${v.loc} ${v.nick}`, v.nick]) {
      if (key && !(String(key).toLowerCase() in idx)) {
        idx[String(key).toLowerCase()] = abbr;
      }
    }
  }
  return idx;
}

async function renderInjuryWatch() {
  const host = document.getElementById("injury-watch");
  if (!host) return;
  if (Date.now() - _injCache.at > 10 * 60e3) {
    try {
      const res = await fetch("data/injuries.json?t=" + Date.now());
      if (res.ok) _injCache = { at: Date.now(), data: await res.json() };
    } catch (e) {}
  }
  const rows = ((_injCache.data || {}).sports || {})[state.sport] || [];
  const games = (state.data || {}).games || [];
  if (!rows.length || !games.length) { host.innerHTML = ""; return; }

  const idx = injAbbrIndex();
  const tonight = new Set();
  for (const g of games) { tonight.add(g.away); tonight.add(g.home); }
  const cutoff = Date.now() - 10 * 86400e3;
  const listed = rows
    .map((r) => ({ ...r, ts: Date.parse(r.date || "") || 0,
                   abbr: idx[(r.team || "").toLowerCase()] }))
    // A cleared-to-play notice is not an injury. ESPN keeps a player in
    // this feed after he is available again, status "Active" and no
    // injury named — which this box printed in green, on a board headed
    // "Injury watch", making a listed player look hurt and an actually
    // hurt one look fine. The page's fresh strip already cut them; two
    // surfaces reading one file must not disagree about what a row means.
    .filter((r) => r.abbr && tonight.has(r.abbr) && !isReturnRow(r));
  const fresh = listed.filter((r) => r.ts >= cutoff)
    .sort((a, b) => b.ts - a.ts);
  const older = listed.length - fresh.length;
  if (!listed.length) { host.innerHTML = ""; return; }

  const body = fresh.length ? fresh.map((r) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:8px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml(r.abbr)}</span>
      <span style="min-width:140px"><b>${escapeHtml(r.player)}</b>${
        r.pos ? ` <span class="inj-pos">${escapeHtml(r.pos)}</span>` : ""}</span>
      <b style="color:${injTone(r.status)}">${escapeHtml(r.status)}</b>
      <span style="flex:1;min-width:120px">${escapeHtml(r.injury || "")}</span>
      <span style="color:var(--text-mute);font-variant-numeric:tabular-nums"
        title="${escapeHtml(r.date || "")}">${injWhen(r.ts)}</span>
    </div>`).join("") : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      Nothing filed in the last ten days on tonight’s teams — the long-term
      list is on the Injuries page.</p>`;
  host.innerHTML = `
    <div class="section-title">Injury watch — tonight’s teams
      <span class="sub">— designations filed in the last ten days on teams playing
      tonight. A fresh listing is the one a price may not know yet; long-term
      entries are already in every number here.</span></div>
    <div class="card" style="padding:0">${body}
      <p style="padding:10px 14px;margin:0;font-size:var(--fs-sm);color:var(--text-mute);
          border-top:1px solid rgba(255,255,255,.05)">
        ${older ? `${older} longer-term entr${older === 1 ? "y" : "ies"} on these teams · ` : ""}
        <a href="#injuries" style="color:var(--brand)">full league board →</a></p></div>`;
  // The rooms were grouped before this async fill landed — re-judge, so
  // the Watchlists tab appears/disappears with what is actually here.
  groupRecommended();
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
  const reasons = (r.reasons || []).map(
    (x, i) => reasonLI(x, (r.reason_tiers || [])[i])).join("");

  // Header (badge + title + sub) varies by bet type; the metrics are shared.
  let mark, title, sub;
  if (r.bet_type === "spread") {
    const ln = `${r.line > 0 ? "+" : ""}${r.line}`;
    mark = teamMark(r.team, 34);
    title = `${escapeHtml(teamName(r.team))} <span class="ml-odds">${ln}</span> <span class="book">${american(r.odds)}</span>`;
    sub = "Spread · cover the number";
  } else if (r.bet_type === "total") {
    // A game total belongs to the GAME, so it wears the league's mark
    // rather than either team's. The direction rides as a corner pip —
    // the arrow used to BE the badge, and dropping it entirely would
    // cost the over/under scan cue this board is read with.
    const arrow = r.side === "Over" ? "▲" : "▼";
    mark = `<span class="mark-stack">${leagueMark(state.sport, 34)}
      <span class="mark-pip ${r.side === "Over" ? "over" : "under"}">${arrow}</span></span>`;
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
    <article class="card gamebet ${r._ok ? "" : "faded"} ${
        gameBetOpenable(r) ? "openable" : ""}"${gameBetAttrs(r)}
        style="--grade-color:${gradeColor(r.grade)}">
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
      ${gameBetChart(r)}
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

/* WHEN the slate above actually is, whenever that is not now.

   Ethan, 2026-08-14: "there is games tonight yet they are not showing on
   the website … its displaying the first week of the regular season."

   The board was never wrong about WHAT it was showing. `_current_nfl_week`
   reads nflverse's schedule, nflverse carries no preseason at all, so the
   nearest fixture it can see in mid-August is Week 1 — three weeks out and
   comfortably inside the 45-day run-up window. It builds that week and it
   is right to: Week 1 prep is the whole point of August.

   The lie was the TITLE. "This week's stadiums" over fixtures from
   September, while the football actually being played sat 900px further
   down under a heading nobody scrolls to. A static string cannot say
   when, so this says it instead.

   It draws NOTHING when the slate is today or tomorrow, which is every
   day of a real season — this is a note about an unusual state, and a
   note that appears constantly stops being read. */
function renderSlateHorizon() {
  const host = document.getElementById("slate-horizon");
  if (!host) return;
  host.innerHTML = "";
  const games = (state.data || {}).games || [];
  if (!games.length) return;
  const dates = games.map((g) => String(g.date || "").slice(0, 10))
                     .filter(Boolean).sort();
  if (!dates.length) return;
  const first = dates[0];
  const today = new Date().toISOString().slice(0, 10);
  // Midday, not midnight: a date-only difference across a DST boundary can
  // land on 0.96 of a day and floor to the wrong number.
  const days = Math.round(
    (new Date(first + "T12:00:00") - new Date(today + "T12:00:00")) / 86400000);
  if (days <= 1) return;                 // today or tomorrow — say nothing

  // Preseason is the only thing that can be on INSTEAD, and only for NFL.
  // `state.preseason` is stashed by renderPreseason; it may not have
  // landed yet on the first pass, and its absence simply means no pointer.
  const pre = state.sport === "nfl" ? state.preseason : null;
  const soon = pre && (pre.weeks || []).some(
    (w) => (w.games || []).some((g) => (g.date || "") >= today));
  /* A LINK, NOT A HOIST. The obvious fix was to move the preseason block
     above the strip while preseason is on. It does not survive:
     `groupRecommended` re-parents this whole view into subgroups AFTER
     every renderer has run, so a DOM move made here is undone moments
     later — measured, not guessed, when the two elements came back in
     different subgroups. Re-architecting the grouping to carry an
     ordering exception is a much larger change than the problem needs,
     so the note points at the block instead and gets you there in one
     click. */
  const pointer = soon
    ? ` <a href="#preseason-board" class="slate-jump">Preseason is what is
        being played now →</a>`
    : "";
  host.innerHTML = `
    <p class="slate-horizon">${icon("clock", 14)}
      This board is <b>${escapeHtml(formatGameDate(first))}</b> — ${days}
      days out. Nothing on it is tonight.${pointer}</p>`;

  /* The pointer is a link to a block that lives in ANOTHER SUB-TAB, so the
     browser's own jump is not enough — see `revealAnchor`. Open the room
     first, then scroll. Bound here rather than delegated because this
     host's innerHTML is rewritten on every render, which drops listeners;
     the anchor itself survives `groupRecommended` either way, since that
     moves nodes with appendChild rather than rebuilding them. */
  host.querySelectorAll("a.slate-jump").forEach((a) =>
    a.addEventListener("click", (e) => {
      const id = (a.getAttribute("href") || "").slice(1);
      const el = revealAnchor(id);
      if (!el) return;              // nothing to show: let the browser try
      e.preventDefault();
      history.replaceState(history.state, "", `#${id}`);
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
}

function renderGames() {
  const games = [...(state.data.games || [])];
  const host = document.getElementById("games");
  if (!games.length) { host.innerHTML = ""; return; }
  // Live games float to the front of the strip; behind them, the sort
  // control decides — kickoff order (the render's default) or most picks.
  const rank = (g) => ((g.live || {}).state === "live" ? 0 : (g.live || {}).state === "final" ? 2 : 1);
  let sortMode = "start";
  try { sortMode = localStorage.getItem("qb_games_sort") || "start"; } catch (e) {}
  const startKey = (g) => `${g.date || ""}T${g.kickoff || ""}`;
  games.sort((a, b) => rank(a) - rank(b)
    || (sortMode === "picks" ? gameBetCount(b) - gameBetCount(a) : 0)
    || startKey(a).localeCompare(startKey(b)));
  const sportSel = document.getElementById("games-sport");
  if (sportSel && sportSel.value !== state.sport) sportSel.value = state.sport;
  // TOP GAME — the render's ribbon, earned not asserted: the game the
  // model has the most recommended bets in tonight. Ties or an empty
  // board mean no ribbon; one game only.
  let topGid = null, topN = 0;
  games.forEach((g) => {
    const n = gameBetCount(g);
    if (n > topN) { topN = n; topGid = gameId(g); }
  });
  window._topGameId = topN > 0 ? topGid : null;
  host.innerHTML = games.map(gameCard).join("");
  revealChildren(host);
  enableTilt(host);
  if (typeof syncStripArrows === "function") syncStripArrows();
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

/* Venue render art. Ethan supplied one night render per lighting colour
   for each building family (2026-08-11: "can you just plug them in?"),
   sliced into web/img/venues/variants/. A card still tries the
   team-specific photo first (img/venues/{sport}/{HOME}.jpg — the path to
   real per-park identity stays open), and when that file does not exist
   it hops to the family render whose lighting matches the home team's
   colours instead of falling all the way back to the drawing. Live games
   never show a photo — the drawing carries the ball spot, bases, wind. */
const VENUE_FAMILY = { nfl: "football", cfb: "football", mlb: "baseball",
                       nba: "basketball", wnba: "basketball" };

/* THE RENDER VERSION, and why every venue URL has to carry it.
   ------------------------------------------------------------------
   Ethan, 2026-08-16: "the stadiums will show old renders of the
   stadiums on some games and the new renders on the others" — on both
   the site and the phone.

   Nothing is wrong with the files. `web/img/venues/variants/` holds one
   generation and the per-team photo directories are empty, so every card
   falls to a variant. The bug is that the variants were REBUILT three
   times (the 4x cinematic upscale, the re-cut from the PNG original, the
   colour-seam slicer) and every rebuild wrote the SAME filenames.
   `variants/baseball-blue.jpg` is a different picture than it was last
   week and its URL never changed, so a browser holding the old bytes has
   no reason to ask for them again.

   That is also why it looks random rather than broken: which cards are
   stale depends on which VARIANT each one uses and when that particular
   file entered the cache. Two cards on one screen legitimately pull
   different files, so one can be current and the other a week old.
   Phones show it worse because mobile browsers hold image caches longer
   and evict less eagerly.

   Bumping this string changes every venue URL, so every cached copy
   misses once and refetches. BUMP IT WHENEVER THE RENDERS ARE REBUILT —
   `tools/venues_ingest.py` writing new bytes under an old name is the
   whole failure mode, and nothing else in the chain can detect it. */
const VENUE_ART_V = "20260814";
const venueSrc = (path) => `${path}?v=${VENUE_ART_V}`;
/* WHICH COLOUR SLOTS HOLD ART THAT MATCHES THE REST.
//
// Ethan, 2026-08-13, after the cache-bust shipped: "the stadium issue is
// not fixed." He was right and my diagnosis was wrong. Busting the cache
// fixed a real problem, but not HIS problem.
//
// `variants/` holds TWO GENERATIONS. The three `*-steel.jpg` are the
// neutral SINGLES from the 2026-08-11 batch — full 1536x1024 renders,
// sharp, detailed. The fifteen colour files are TILES CUT OUT OF a
// five-colour sheet, ~1000-1500px each and visibly softer: different
// framing, less detail, heavier tint. Put a steel card beside a gold one
// and they do not look like the same site.
//
// And it is DETERMINISTIC, not random, which is why a hard refresh could
// never fix it: the rule below picks the slot from the home team's kit,
// so a neutral-kitted club shows the sharp render and a colour-kitted
// club shows a sheet tile, the same way every time. "Some games old, some
// new" is exactly what that produces.
//
// Until a matched colour set exists, only the generation we have all of
// is used. The colour rule below is deliberately LEFT INTACT rather than
// deleted — it is correct, it is tested, and the day fifteen matching
// renders land in incoming/ this is one line to revert. Ethan chose this
// over the alternatives on 2026-08-13, knowing it costs the tinting.
//
// TO RESTORE THE COLOURS: generate colour renders at the steel files'
// quality, drop them in web/img/venues/incoming/ named per the README,
// run `python3 tools/venues_ingest.py`, then add their names here.
//
// RESTORED 2026-08-14, and NOT because new art arrived. Ethan, seeing a
// board of white-lit stadiums: "what the fuck happened to all my colored
// renders. its only showing white renders for all sports. i want my
// colored renders back."
//
// So this now serves all six, and the 2026-08-13 trade is taken the
// other way round: a colour-kitted club shows its tinted sheet tile and
// a neutral-kitted one still shows the sharp steel single, which is the
// mismatch that started this. Both complaints are real and they point in
// opposite directions — there is no setting that is sharp, consistent
// AND coloured until fifteen matching renders exist. Given the choice,
// Ethan wants the colour.
//
// `launch.py --venues` still measures honestly and will still report
// fifteen files as off-generation. That is not a warning to act on any
// more; it is the standing description of what is being served on
// purpose. The probe says so rather than nagging. */
const VENUE_MATCHED = new Set(["steel", "red", "gold", "green", "blue", "violet"]);

function venueVariant(team) {
  // First team colour with real chroma decides the lighting; neutral
  // kits (black, silver, white) fall through to the steel render, which
  // is why the secondary gets a vote — PIT's black defers to its gold.
  for (const hex of [(team || {}).primary, (team || {}).secondary]) {
    if (!/^#[0-9a-fA-F]{6}$/.test(hex || "")) continue;
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    const mx = Math.max(r, g, b), d = mx - Math.min(r, g, b);
    // 0.22, not lower: the White Sox' near-black #27251f carries 20%
    // chroma that reads as warm grey, not gold — it must fall through
    // to the silver secondary and land on steel.
    if (!mx || d / mx < 0.22) continue;               // neutral — no vote
    let h = mx === r ? (g - b) / d : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h = (h * 60 + 360) % 360;
    let best = "steel", bd = 361;
    for (const [name, a] of [["red", 358], ["gold", 45], ["green", 150],
                             ["blue", 225], ["violet", 278]]) {
      const raw = Math.abs(h - a) % 360, dd = Math.min(raw, 360 - raw);
      if (dd < bd) { bd = dd; best = name; }
    }
    // The colour this kit earns — served only while that slot's art
    // belongs to the same generation as everything else on screen.
    return VENUE_MATCHED.has(best) ? best : "steel";
  }
  return "steel";
}
// The inline onerror hop: team photo missing -> family render -> if that
// is somehow gone too, remove and let the drawn scene show.
window.vpFall = (el) => {
  const alt = el.dataset.alt;
  if (alt) { el.removeAttribute("data-alt"); el.src = alt; }
  else { el.remove(); }
};

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
    // The park name moved up to the card's venue line (fidelity pass) —
    // repeating it here printed "Coors Field" twice on one card.
    const bits = [`O/U ${g.total.toFixed(1)}`];
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
  // MLB live: the count and the outs. The runners are on the park art
  // above, lit on the bases they are standing on, so this line no longer
  // repeats them.
  // NFL live: the down & distance line.
  let liveDetail = "";
  if (isLive && mlb) {
    liveDetail = `<div class="live-detail count">${countStrip(live)}</div>`;
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
  // The render's card hierarchy (2026-08-11, "exactly like this page
  // visually"): the night scene on top wearing its chips, then a
  // centred column — the two marks around "vs", the matchup name, the
  // venue line, tonight's numbers small, and the weather row. The CTA
  // row retired: the whole card is the door, the picks count rides the
  // art as a chip, and hover says clickable.
  const homeTeam = (window.ACTIVE_TEAMS || {})[g.home] || {};
  const venueBits = [];
  if (mlb && g.park_name) venueBits.push(esc(g.park_name));
  if (homeTeam.loc) venueBits.push(esc(homeTeam.loc));
  const venue = venueBits.length
    ? `<div class="gc-venue">${venueBits.join(" · ")}</div>` : "";
  const picksChip = n
    ? `<span class="gc-picks">${n} pick${n === 1 ? "" : "s"}</span>` : "";
  return `
    <article class="game-card tilt ${isLive ? "is-live" : ""}" data-gid="${escapeHtml(gameId(g))}"
             role="button" tabindex="0"
             aria-label="Open picks for ${escapeHtml(teamName(g.away))} at ${escapeHtml(teamName(g.home))}">
      <div class="stadium-wrap">${art}${
        // The photo slot (Ethan, 2026-08-11: wants the cards to look
        // exactly like his generated renders). A team-specific
        // web/img/venues/{sport}/{HOME}.jpg wins when it exists; the
        // onerror hop lands on the family render (vpFall).
        //
        // LIVE GAMES GET THE PHOTO TOO, since 2026-08-13. They used to
        // suppress it and show only the drawn scene, because the drawing
        // lights the occupied bases and the status line below had been
        // changed to stop repeating them. The cost was a flat vector
        // diagram sitting beside photoreal stadiums on the same strip —
        // which is the third and largest cause of the "old renders on
        // some games, new on others" Ethan reported three times, and the
        // one neither the cache token nor the one-generation gate could
        // reach. He chose photo-everywhere with the runners kept on top;
        // `runnerOverlay` is that, and it is why nothing is lost here.
        (() => {
          const fam = VENUE_FAMILY[state.sport];
          return `<img class="venue-photo" alt="" loading="lazy"
          src="${venueSrc(`img/venues/${escapeHtml(state.sport)}/${escapeHtml(g.home)}.jpg`)}"
          ${fam ? `data-alt="${venueSrc(`img/venues/variants/${fam}-${venueVariant(homeTeam)}.jpg`)}"
          onerror="vpFall(this)"` : `onerror="this.remove()"`}/>`;
        })()}${
        // The one thing the drawing carried that a photo cannot.
        mlb && isLive ? runnerOverlay(g) : ""}${badge}${
        window._topGameId === gameId(g) && !isLive && !isFinal
          ? `<span class="top-game-tag">Top game</span>` : ""}${
        !isLive && !isFinal && whenLabel(g.date, g.kickoff)
          ? `<span class="game-time-chip">${escapeHtml((whenLabel(g.date, g.kickoff).split("·").pop() || "").trim())}</span>` : ""}${
        // Temp + wind on the art itself (Ethan's stadium render rows,
        // 2026-08-11) — only outdoors, only when a real reading exists.
        !isLive && !isFinal && w.temp_f != null && !w.dome && !nba
          ? `<span class="game-wx-chip">${Math.round(w.temp_f)}° · ${Math.round(w.wind_mph || 0)}mph</span>` : ""}${picksChip}</div>
      <div class="game-info">
        <div class="gc-teams">
          <span class="gc-side">${teamMark(g.away, 30)}${score("away")}</span>
          <span class="gc-vs">${isLive || isFinal ? "@" : "vs"}</span>
          <span class="gc-side">${teamMark(g.home, 30)}${score("home")}</span></div>
        <div class="gc-name">${ranked("away")}${escapeHtml(teamName(g.away))} @ ${ranked("home")}${escapeHtml(teamName(g.home))}</div>
        ${venue}
        ${starters}
        <div class="game-sub">${sub}</div>
        ${whenLabel(g.date, g.kickoff) ? `<div class="game-when">${icon('calendar')} ${escapeHtml(whenLabel(g.date, g.kickoff))}</div>` : ""}
        ${isLive && !mlb ? liveDetail : ""}
      </div>
      ${footer}
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
    // data-w is a CSS percentage ("73%"); scaleX wants the fraction.
    const to = `scaleX(${(parseFloat(el.dataset.w) || 0) / 100})`;
    if (state.quiet) { el.style.transition = "none"; el.style.transform = to; }
    else requestAnimationFrame(() => (el.style.transform = to));
  });
}

/* ============================================================
   TONIGHT — every recommended bet, each with its own chart.
   ============================================================
   Ethan, 2026-08-13: "where it shows the 'props' button on the mobile
   site, that should be replaced with a page that shows todays reccomended
   bets with the bar graphs and shit like we have."

   The phone's second tab pointed at the Edge Board, which is the wrong
   page for that slot: it is a research table of every positively-priced
   number on the card, sorted by EV, most of which we are not betting.
   What a phone wants is tonight's actual card — the picks, the charts,
   nothing else — and that page did not exist on any screen size.

   It is the SAME cards the board draws, deliberately. `cardHTML` and
   `gameBetCard` already carry the chart, the grade, the price and the
   reasons; rebuilding a phone-shaped version of them would be a second
   place for the two to drift apart. What is different here is the
   selection — recommended only, props and game bets in one list — and
   the absence of everything else on the board page.  */
function renderTonight() {
  const host = document.getElementById("tonight-body");
  if (!host) return;
  const d = state.data || {};
  const props = (d.recommendations || [])
    .map((r) => ({ ...r, _ok: passesFilters(r) }))
    .filter((r) => r._ok && r.hr_featured !== false);
  const bets = (d.game_bets || [])
    .map((b) => ({ ...b, _ok: passesGameBet(b) }))
    .filter((b) => b._ok);
  const shots = (d.long_shots || []).slice(0, 3);
  const n = props.length + bets.length;
  if (!n && !shots.length) {
    host.innerHTML = `<div class="section-title">Tonight’s bets</div>
      <div class="empty-slate"><div class="es-icon">${icon("target", 30)}</div>
      <h3>Nothing clears the bar right now</h3>
      <p>${noMarketExplainer()}</p></div>`;
    return;
  }
  host.innerHTML = `
    <div class="section-title">Tonight’s bets
      <span class="sub">— every pick that clears the bar, with the last
      games it is priced against. ${n} bet(s) · journaled and graded in
      public on the Record page.</span></div>
    <div class="cards">${props.map(cardHTML).join("")}</div>
    ${bets.length ? `<div class="section-title minor">Game lines</div>
      <div class="cards">${bets.map(gameBetCard).join("")}</div>` : ""}
    ${shots.length ? `<div class="section-title minor">Long shots
      <span class="sub">— plus-money swings, sized like lottery tickets.</span></div>
      <div class="cards">${shots.map(longShotCard).join("")}</div>` : ""}`;
  if (typeof fillMeters === "function") fillMeters(host);
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
        The board fills as tonight’s prices arrive; no slider changes that.`;
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

/* §5's velocity tell, on the card. MLB_MODEL: "A drop of 1+ mph is a red
   flag — check injury and mechanics reporting before trusting any
   projection of him."

   PITCHER MARKETS ONLY, which is why most cards show nothing: the number
   is his own change against his own recent baseline, and a hitter prop
   has no such thing. An absent chip means unmeasured, never steady.

   NOTHING PRICES FROM THIS. The chip is deliberately worded as an
   instruction to go and read something, because a number on a card reads
   as a recommendation unless it says otherwise — and the claimed edge on
   this book is still indistinguishable from a coin flip
   (docs/THE_INFORMATION_TEST.md). */
function veloChip(r) {
  const d = r.velo_delta;
  if (d == null) return "";
  const drop = d <= -1.0;
  const mph = `${d >= 0 ? "+" : ""}${d.toFixed(1)} mph`;
  const tip = drop
    ? "Down a full mph or more on his main pitch against his own last "
      + "starts. §5 treats this as a red flag: check injury and mechanics "
      + "reporting before trusting the projection. It does not change the "
      + "price."
    : "Change on his main pitch against his own last starts. Evidence "
      + "only — nothing prices from it.";
  return `<span class="chip ${drop ? "down" : ""}" title="${tip}">`
       + `${drop ? iconMark("warn") : ""}Velo ${mph}`
       + `${drop ? " · check reports" : ""}</span>`;
}

/* §4: "Which book moved first matters — the first mover took the smart
   money; the rest are copying." Shown only when a SHARP book led, because
   that is the case §4 is about — a recreational book moving first is
   usually a stale number being corrected, which is noise on a card. */
function firstMoverChip(r) {
  const m = r.line_move;
  if (!m || !m.first_mover || !m.first_mover_sharp) return "";
  return `<span class="chip" title="A sharp book left its opening number `
       + `first and the rest followed. §4 reads that as the informed side `
       + `moving. Recorded and journaled; it does not change the price.">`
       + `${iconMark("signal", 11)}${escapeHtml(m.first_mover)} moved first</span>`;
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
  const reasons = (r.reasons || []).map(
    (x, i) => reasonLI(x, (r.reason_tiers || [])[i])).join("");
  const corr = (r.correlations || []).map((c) =>
    `<div class="warning" style="border-color:var(--cyan)">${iconMark("tag")}${escapeHtml(c)}</div>`).join("");
  const warnings = (r.warnings || []).map((w) => `<div class="warning">${icon('warn')} ${escapeHtml(w)}</div>`).join("");
  const ud = unitDollars();
  const stakeTxt = ud > 0
    ? `Stake ${money(stakeDollars(r.stake_units))} · ${r.stake_units.toFixed(2)}u`
    : `Stake ${r.stake_units.toFixed(2)}u`;
  const stakeChip = r._ok ? `<span class="chip stake">${stakeTxt}</span>` : "";
  return `
    <article class="card ${propOpenable(r) ? "openable" : ""} ${r._ok ? "" : "faded"}"${propAttrs(r)}
      style="--grade-color:${gradeColor(r.grade)}">
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
      ${propAnalysis(r)}
      <div class="chips">${r.has_market === false ? `<span class="chip">No book line — model projection only</span>` : ""}${r.doubleheader ? `<span class="chip up" title="Two games today — this prop is priced for this specific game only">${iconMark("calendar", 11)}Doubleheader · Game ${r.game_number || 1}</span>` : ""}${whenChip(r.game_date, r.game_kickoff)}${qualityChip(r)}${tierChip(r)}${trendChip(r)}${moveChip(r)}${firstMoverChip(r)}${veloChip(r)}${booksChip(r)}${stakeChip}</div>
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
         these are the model’s most likely ${mlb ? "home runs" : "scorers"} instead, with
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
    model’s most likely ${mlb ? "home run" : "scorer"}${watch.length > 1 ? "s" : ""},
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
    ${/* The answer to "why is there nothing here", directly under the
          verdict that raises the question. This used to render only in the
          notes list at the very BOTTOM of the page — below every ticket
          card, the runners-up and the ledger — so the explanation sat
          underneath the thing it explains. Scrolling from the top you hit
          "#1 does not clear", read a card about a ticket that was never
          going to qualify, and never reached the sentence saying why the
          board had nothing better to offer. */ ""}
    ${z.structural ? `<div class="pz-note pz-structural">
      <span class="pz-mark">${icon("search", 13)}</span>
      ${escapeHtml(z.structural)}
    </div>` : ""}
    <div class="pz-probation">
      <span class="pz-mark">${icon("warn", 13)}</span>
      ${escapeHtml(z.probation_note || "")}
    </div>
    ${tickets.length ? `<div class="pz-sub pz-rank-title">
      ${qualified.length
        ? "Tonight’s board, ranked — the first is the play"
        : "Tonight’s board, ranked — best constructions available"}
      </div>` : ""}
    ${tickets.slice(0, 1).map((t) => parlayTicket(t, t.qualified)).join("")}
    ${parlayRunnersUp(tickets.slice(1))}
    ${parlayLedger(z)}
    ${(z.notes || []).filter((n) => n !== z.structural).map((n) =>
        `<div class="pz-note">${escapeHtml(n)}</div>`).join("")}
    <div class="pz-census">
      Screened ${z.considered} candidate ${z.considered === 1 ? "ticket" : "tickets"}
      built from ${z.eligible_legs} eligible ${z.eligible_legs === 1 ? "leg" : "legs"}
      on tonight’s board.
      ${z.killed && z.killed.length
        ? `${z.killed.length} ${z.killed.length === 1 ? "was" : "were"} killed
           for the reasons above.` : ""}
    </div>`;
  revealChildren(host);
  if (typeof syncParlayMode === "function") syncParlayMode();
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
      : ""}The published ρ is the doc’s prior; the priced ρ is that prior after
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
      That figure is what tonight’s board is ranked on.</div>
    <div class="pz-fine">Nobody publishes what they charge to combine legs, so
      the two numbers above are a <b>band</b>, not a quote: this ticket is
      measured against a book taking
      ${(t.correlation_tax_best_case * 100).toFixed(0)}% and against one
      taking ${(t.correlation_tax_worst_case * 100).toFixed(0)}%, versus the
      4.3–4.8% a straight side costs. ${t.grade === "marginal"
        ? `It clears the first and not the second — which makes this a question
           about your book’s actual number rather than about the model.`
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

/* A ticket that cleared all seven gates and lost only to §10.2's
   one-per-slate cap is NOT the same animal as one that failed on merit.
   These rendered identically — same row, same weight, the demoted one
   reading a bare "clears" next to tickets that missed by 30%. The arbiter
   already writes that ticket its own verdict naming the sport that took
   the slot; nothing displayed it. */
const pzDemoted = (t) => t.slate_play === false && t.grade !== "short";

/* One summary line: the numbers the ranking is actually computed on, in
   the order a reader compares them. Doubles as the <summary> of the
   collapsible card below, so the row and the card can never disagree. */
function parlayRunnerRow(t) {
  const sign = (n) => (n > 0 ? `+${n}` : `${n}`);
  return `<span class="pz-rank">#${t.rank}</span>
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
      ? `short ${t.shortfall_pct}%`
      : pzDemoted(t) ? "cleared — capped" : "clears"}</span>`;
}

/* Ranks two and below, in full — but folded.
 *
 * Four full tickets stacked ran to six thousand pixels of near-identical
 * blocks, which buried the one that matters; that is why these were rows
 * for a while. Rows lost the other half of the point: the correlation, the
 * mechanism sentence, the clash screen and the dominance arithmetic are
 * the reason a construction is ranked where it is, and a line of numbers
 * cannot carry them.
 *
 * So every ticket now gets its whole card, behind a <details> whose summary
 * IS the old row. Open by default when the ticket CLEARED — tonight that is
 * the one the slate cap demoted, which a reader has an obvious reason to
 * inspect — and folded when it did not, because a ticket that loses money
 * at the most generous price a book would quote has earned a line, not a
 * screen. Native <details>: it survives with JS broken and it is keyboard
 * operable without writing either behaviour by hand. */
function parlayRunnersUp(rows) {
  if (!rows.length) return "";
  return `<div class="pz-sub pz-runners-title">Also on the board</div>
    <div class="pz-runners">
      ${rows.map((t) => `
      <details class="pz-runner${pzDemoted(t) ? " pz-demoted" : ""}"
               ${t.grade !== "short" ? "open" : ""}>
        <summary>${parlayRunnerRow(t)}</summary>
        ${pzDemoted(t) && t.verdict
          ? `<div class="pz-run-why">${escapeHtml(t.verdict)}</div>` : ""}
        ${parlayTicket(t, t.qualified)}
      </details>`).join("")}
    </div>`;
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
      return "No hitter props are built yet. Lineups aren’t posted AND no recent " +
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
             "games are in progress (in-play prices) — tomorrow’s board resets " +
             "with fresh pre-game quotes.";
    return `${dg.plus_money} real plus-money price(s) exist but every one failed ` +
           "a sanity guard (edge cap or odds window). If this persists on a " +
           "pre-game board, something is wrong — worth reporting.";
  }
  return "The model only surfaces " + (mlb ? "home-run" : "touchdown") +
         " picks that beat the book’s price inside a sane odds range" +
         (mlb ? " (+250 to +650)." : " (-150 to +200).");
}

function watchlistHTML(watch, mlb) {
  if (!watch || !watch.length) return "";
  const rows = watch.map((r, i) => {
    const ev = (r.ev_per_unit * 100).toFixed(0);
    const evColor = r.ev_per_unit > 0 ? "var(--good)" : "var(--text-mute)";
    const spark = (r.recent_values || []).length > 2
      ? gamelogBars(r.recent_values, { line: 0.5, stroke: teamPrimary(r.team), w: 64, h: 22 })
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
      <span class="sub">— model % vs the book’s implied %. Positive EV = price worth taking;
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
    <article class="card longshot ${propOpenable(r) ? "openable" : ""}"${propAttrs(r)}
      style="--grade-color:${gradeColor(r.grade)}">
      ${r.live ? `<div class="live-ribbon"><span class="live-dot"></span>LIVE · in-play</div>` : ""}
      <div class="card-head">
        <div class="card-id">${playerAvatar(r.player, r.team, { map: nflMap(), headshot: r.headshot })}
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
      ${propAnalysis(r)}
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
/* ============================================================
   ONE PROP — the page behind a recommended pick.
   ============================================================
   Ethan, 2026-08-13: "we should add a feature where we can click on the
   prop we recommend and it takes us to a page like the players page that
   shows the last 5 games of information for that prop including the bar
   graph we just added."

   WHAT MADE THIS WORTH BUILDING RATHER THAN FAKING. Every card on the
   board already carries a `logs` array the site had never rendered: 12-16
   entries, each with the opponent, the week, whether it was at home, the
   value, and the sport's own extra — wind for the NFL, the park and its
   HR factor for baseball. `form` carries the same player's last 1 / 3 / 5
   / 10 / season / career averages. All of it real, all of it already in
   the payload, none of it on screen anywhere before this.

   So the page states the case rather than restating the headline: the
   chart he just approved at full width, the last five games with WHO
   they came against, and the form ladder read against tonight's line so
   the reader can see which way the recent trend cuts.

   The prop's identity is (player, market, side, line) — not an index into
   a list, which would point at a different pick the moment the board
   rebuilds and a bookmarked link would quietly lie.  */
function propId(r) {
  return [r.player || "", r.market || "", r.side || "", r.line == null ? "" : r.line]
    .join("|");
}

/* IS THIS ROW A DOOR? One definition, used by every surface that lists a
   prop — the dashboard's best bets, the Edge Board, Top Picks, the rail,
   the game page and the two card boards.

   Ethan, 2026-08-13: "anywhere we show a prop, we need to offer the
   option to click on it and show more data of that prop with the bar
   graph like u just did."

   Two conditions, and both matter for the same reason — a door that
   opens onto nothing is worse than no door:

   * It has to be a PLAYER prop. Moneylines, spreads and game totals sit
     in these same lists and have no player and no game log, so the page
     would have nothing to draw.
   * It has to have HISTORY. `propAnalysis` itself returns "" under three
     values, so a prop with no log would open a page whose centrepiece is
     missing.

   Rows that fail either test simply are not clickable, which is honest:
   the affordance appears exactly where there is something behind it. */
function propOpenable(r) {
  if (!r || !r.player) return false;
  const logs = (r.logs || []).length;
  const vals = (r.recent_values || []).length;
  return logs >= 3 || vals >= 3;
}

function propAttrs(r) {
  return propOpenable(r)
    ? ` data-prop="${escapeAttr(propId(r))}" tabindex="0" role="link"` : "";
}

/* ---- GAME BETS ARE DOORS TOO -------------------------------------------
   Ethan, 2026-08-13, circling MIL +1.5 on the dashboard: "i dont think u
   get what im saying. i should be able to click on this prop and it shows
   more info for the prop and it will show the bar graph too."

   He was right and I had built half the feature. The pick he circled is a
   GAME bet, and `propOpenable` requires `r.player` — a run line has no
   player, so every card like it stayed inert while the props beside it
   opened. The gate was not wrong about props; it was answering the wrong
   question, which was "is this a player prop" instead of "is there
   anything behind this door".

   THE HISTORY A GAME BET HAS is the team's own last games, and the site
   has been ingesting those all along to grade itself with — see
   engine/teamlogs.py. Each market charts a different quantity out of the
   same row, and charting the wrong one would be worse than charting
   nothing:

       moneyline    the picked team's margin, against 0
       spread       the picked team's margin, against the handicap
       team total   what that team SCORED, against the number
       game total   the combined score, against the number

   A game bet's identity is the matchup, the market, the side and the
   line — same shape as a prop's, so one id space, one listener, one page.  */
function gameBetId(b) {
  return ["game", `${b.away || ""}@${b.home || ""}`, b.market || b.bet_type || "",
          b.side || b.team || "", b.line == null ? "" : b.line].join("|");
}

function teamRecent(team) {
  return ((state.data || {}).team_recent || {})[team] || [];
}

/* What this bet's bar chart is made of: the values, the threshold they
   are read against, and the words for both. Returns null when the market
   is one we have no honest series for — an unknown market draws nothing
   rather than a chart of the wrong number. */
function gameBetSeries(b) {
  const kind = b.bet_type || b.market || "";
  const team = b.team || (b.side === "home" ? b.home : b.away);
  const rows = kind === "total"
    ? teamRecent(b.home) : teamRecent(team);
  if (rows.length < 3) return null;
  // Who each bar was against — same fact the prop charts take from a
  // player's game log, taken here from the team's. Newest first, like
  // the values beside them; the chart reverses both together.
  const labels = rows.map((g) => (g.home ? "" : "@")
    + String(g.opponent || "").toUpperCase());
  // The chart head is set in caps, so the team name is upper-cased here
  // rather than left to CSS — `text-transform` would not survive a copy
  // out of the page, and a lower-case club name inside an upper-case
  // heading reads as a bug rather than a choice.
  const proper = (t) => (typeof teamName === "function" ? teamName(t) : t);
  const nm = (t) => String(proper(t) || "").toUpperCase();
  if (kind === "moneyline") {
    return { values: rows.map((g) => g.margin), line: 0, over: true,
             what: "MONEYLINE", labels, head: `LAST ${rows.length} ${nm(team)} RESULTS`,
             legend: ["WON", "LOST"], sideLabel: "WIN",
             note: "the margin in each game — above the line is a win" };
  }
  if (kind === "spread") {
    // A +1.5 handicap covers whenever the margin beats −1.5, so the
    // threshold is the handicap with its sign flipped. Getting this
    // backwards would colour every cover as a miss.
    return { values: rows.map((g) => g.margin), line: -Number(b.line),
             over: true, what: "SPREAD", labels,
             head: `LAST ${rows.length} ${nm(team)} MARGINS`,
             legend: ["COVERED", "MISSED"], sideLabel: "COVER",
             note: `each game’s margin against the ${
               b.line > 0 ? "+" : ""}${b.line} it has to beat` };
  }
  if (kind === "team_total") {
    return { values: rows.map((g) => g.scored), line: Number(b.line),
             over: String(b.side || "Over").toUpperCase() === "OVER",
             what: "TEAM TOTAL", labels, head: `LAST ${rows.length} ${nm(team)} SCORES`,
             legend: ["OVER", "UNDER"],
             note: "what this team alone scored in each of its last games" };
  }
  if (kind === "total") {
    return { values: rows.map((g) => g.total), line: Number(b.line),
             over: String(b.side || "Over").toUpperCase() === "OVER",
             what: "GAME TOTAL", labels,
             head: `LAST ${rows.length} ${nm(b.home)} GAMES — COMBINED`,
             legend: ["OVER", "UNDER"],
             note: `both teams' combined score in ${proper(b.home)}'s last games`,
             also: b.away };
  }
  return null;
}

/* The chart itself, wherever a game bet is drawn in full. Reuses
   `propAnalysis` rather than growing a second chart — one block, one set
   of rules about what colour is allowed to mean, one place to fix. */
function gameBetChart(b) {
  const s = gameBetSeries(b);
  if (!s) return "";
  const team = b.team || (b.side === "home" ? b.home : b.away);
  return propAnalysis({
    recent_values: s.values, line: s.line, side: s.over ? "OVER" : "UNDER",
    odds: b.odds, market: b.market, market_label: b.market_label || b.market,
    ev_per_unit: b.ev_per_unit, confidence: b.confidence, team: team,
  }, { head: s.head, what: s.what, legend: s.legend, sideLabel: s.sideLabel,
       labels: s.labels });
}

/* A GAME BET IS ALWAYS A DOOR, and that is a deliberate departure from
   the rule player props follow.

   `propOpenable` demands history because the prop page's whole centre is
   the chart — open one without a game log and you get an empty frame. A
   game bet's page is not like that: the model's number against the
   market's, the edge, the reasons and the model's own objections are all
   there whether or not we have ingested three of that club's games. The
   door leads somewhere either way.

   It also removes a way for this to look broken through no fault of the
   page. `team_recent` is built from the history DB at build time, so a
   thin ingest, a season boundary or a club we have not stored yet would
   make the card silently unclickable again — which is exactly the
   symptom Ethan reported, arriving by a different route. When the series
   is missing the page says so in a line, which is a fact rather than a
   dead end. */
function gameBetOpenable(b) {
  return !!(b && b.home && b.away && (b.market || b.bet_type));
}

function gameBetAttrs(b) {
  return gameBetOpenable(b)
    ? ` data-prop="${escapeAttr(gameBetId(b))}" tabindex="0" role="link"` : "";
}

function allProps() {
  const d = state.data || {};
  return [...(d.recommendations || []), ...(d.long_shots || []),
          ...(d.longshot_watch || [])];
}

/* ONE DELEGATED LISTENER, on the document. Prop cards are re-rendered
   constantly — every slider move, every refresh, every sport switch — so
   binding per card would leak a handler on each rebuild and miss every
   card drawn after the bind. Delegation survives all of it.

   `closest("a, button, input, label, select")` is the guard that matters:
   these cards carry a Play link and My Bets controls, and a card-wide
   click would otherwise swallow them. The inner control wins; anywhere
   else on the card opens the prop. */
document.addEventListener("click", (e) => {
  if (e.target.closest("a, button, input, label, select, .chip")) return;
  const card = e.target.closest("[data-prop]");
  if (!card) return;
  openProp(card.dataset.prop);
});

/* Keyboard parity: a card you can click is a control, and a control that
   only answers a mouse is not finished. */
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const card = e.target.closest && e.target.closest("[data-prop]");
  if (!card || e.target.closest("a, button, input, select")) return;
  e.preventDefault();
  openProp(card.dataset.prop);
});

function openProp(id) {
  state.propId = id;
  switchView("prop");
}

/* The last N games, with the context the bar chart cannot draw. A bar
   says how big; this says who against, where, and in what weather —
   which is the difference between "he went under twice" and "he went
   under twice against the two best defenses he has seen". */
function propLogRows(r, logs, line, over, n) {
  const won = (v) => (over ? v > line : v < line);
  const sport = state.sport;
  return logs.slice(0, n).map((g) => {
    const v = Number(g.value);
    const ok = Number.isFinite(v) && won(v);
    const when = g.date ? String(g.date).slice(5)
      : (g.week != null ? `Wk ${g.week}` : "—");
    const extra = [];
    if (g.wind != null) extra.push(`${g.wind} mph wind`);
    if (g.park) extra.push(String(g.park));
    if (g.park_hr != null) extra.push(`park ${Number(g.park_hr).toFixed(2)}× HR`);
    return `<div class="pp-log">
      <span class="pp-when">${escapeHtml(when)}</span>
      <span class="pp-opp">${g.home ? "vs" : "@"} ${escapeHtml(
        typeof teamName === "function" ? teamName(g.opponent) : (g.opponent || "?"))}</span>
      <span class="pp-extra">${escapeHtml(extra.join(" · "))}</span>
      <span class="pp-val ${ok ? "pos" : "neg"}">${
        Number.isFinite(v) ? v : "—"}</span>
      <span class="pp-hit ${ok ? "pos" : "neg"}">${ok ? "CLEARED" : "MISSED"}</span>
    </div>`;
  }).join("");
}

/* The form ladder against tonight's number. Averages on their own are
   trivia; averages beside the line are the argument. */
function propFormRows(form, line, over) {
  const LABELS = [["last1", "Last game"], ["last3", "Last 3"],
                  ["last5", "Last 5"], ["last10", "Last 10"],
                  ["season", "This season"], ["career", "Career"],
                  ["vs_opponent", "vs tonight’s opponent"]];
  return LABELS.map(([k, label]) => {
    const v = (form || {})[k];
    if (v == null) return "";
    const side = over ? v > line : v < line;
    const diff = v - line;
    return `<div class="pp-form">
      <span class="pp-fk">${escapeHtml(label)}</span>
      <span class="pp-fv">${Number(v).toFixed(1)}</span>
      <span class="pp-fd ${side ? "pos" : "neg"}">${
        diff >= 0 ? "+" : ""}${diff.toFixed(1)} vs line</span>
    </div>`;
  }).join("");
}

/* The same page, for a bet that has a team instead of a player. It reuses
   `propAnalysis` rather than growing a second chart: the block already
   knows how to draw values against a threshold, and one chart with one
   set of rules is the only way two surfaces stay honest with each other.
   The labels come in as options because a run line is not an "over". */
function renderGameBetPage(b) {
  const host = document.getElementById("prop-body");
  const s = gameBetSeries(b);
  const nm = (t) => (typeof teamName === "function" ? teamName(t) : t);
  const kind = b.bet_type || b.market || "";
  const team = b.team || (b.side === "home" ? b.home : b.away);
  const mark = kind === "total" ? leagueMark(state.sport, 56) : teamMark(team, 56);
  // The chart wants a prop-shaped row. Only the fields it reads are set,
  // and the values are the team's real results — nothing is synthesised.
  const asProp = s ? {
    recent_values: s.values, line: s.line, side: s.over ? "OVER" : "UNDER",
    odds: b.odds, market: b.market, market_label: b.market_label || b.market,
    ev_per_unit: b.ev_per_unit, confidence: b.confidence, team: team,
  } : null;
  const rows = (kind === "total" ? teamRecent(b.home) : teamRecent(team))
    .slice(0, 5);
  const won = (v) => (s ? (s.over ? v > s.line : v < s.line) : false);
  const val = (g) => kind === "team_total" ? g.scored
    : kind === "total" ? g.total : g.margin;
  const logRows = s ? rows.map((g) => {
    const v = val(g), ok = won(v);
    return `<div class="pp-log">
      <span class="pp-when">${escapeHtml(String(g.when).slice(5))}</span>
      <span class="pp-opp">${g.home ? "vs" : "@"} ${escapeHtml(nm(g.opponent))}</span>
      <span class="pp-extra">${escapeHtml(`${g.scored}–${g.allowed}`)}</span>
      <span class="pp-val ${ok ? "pos" : "neg"}">${v > 0 && kind !== "team_total"
        && kind !== "total" ? "+" : ""}${v}</span>
      <span class="pp-hit ${ok ? "pos" : "neg"}">${ok
        ? (s.legend[0]) : (s.legend[1])}</span>
    </div>`;
  }).join("") : "";
  const reasons = (b.reasons || []).slice(0, 8)
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const warn = (b.warnings || []).slice(0, 4)
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  host.innerHTML = `
    <button class="btn ghost gp-back" id="pp-back">← Back to the board</button>
    <article class="card pp-card">
      <div class="card-head">
        <div class="card-id">${mark}
          <div>
            <div class="player">${escapeHtml(b.pick_label || b.headline || "")}
              <span class="ml-odds">${b.odds > 0 ? "+" : ""}${b.odds}</span></div>
            <div class="subtitle">${escapeHtml(b.matchup
              || `${b.away} @ ${b.home}`)}</div>
            <div class="pick">${escapeHtml(b.market_label || b.market || "")}</div>
          </div>
        </div>
        ${b.grade ? `<span class="grade ${gradeClass(b.grade)}">${
          escapeHtml(b.grade)}</span>` : ""}
      </div>
      <div class="metrics">
        ${b.win_prob != null ? `<div class="metric"><div class="k">Model</div>
          <div class="v">${pct(b.win_prob)}</div></div>` : ""}
        ${b.fair_prob != null ? `<div class="metric"><div class="k">Market</div>
          <div class="v">${pct(b.fair_prob)}</div></div>` : ""}
        ${b.edge != null ? `<div class="metric primary"><div class="k">Edge</div>
          <div class="v ${b.edge >= 0 ? "pos" : "neg"}">${signedPct(b.edge)}</div></div>` : ""}
      </div>
      ${asProp ? propAnalysis(asProp, { head: s.head, what: s.what,
        legend: s.legend, sideLabel: s.sideLabel, labels: s.labels }) : `
      <p class="loading">No recent results for this team yet — the chart
      needs at least three games we have ingested.</p>`}
    </article>

    ${logRows ? `<div class="section-title">Last ${rows.length} game${
      rows.length === 1 ? "" : "s"}
      <span class="sub">— ${escapeHtml(s.note)}, newest first.</span></div>
    <div class="card pp-logs">${logRows}</div>` : ""}

    ${reasons ? `<div class="section-title minor">Why this pick</div>
      <div class="card"><ul class="reasons">${reasons}</ul></div>` : ""}
    ${warn ? `<div class="section-title minor">What argues against it
      <span class="sub">— the model’s own objections, not hidden.</span></div>
      <div class="card"><ul class="reasons">${warn}</ul></div>` : ""}`;
  const bk = document.getElementById("pp-back");
  if (bk) bk.addEventListener("click", () => switchView("recommended"));
  if (typeof fillMeters === "function") fillMeters(host);
}

function renderPropPage() {
  const host = document.getElementById("prop-body");
  if (!host) return;
  if (String(state.propId || "").startsWith("game|")) {
    const b = (state.data.game_bets || [])
      .find((x) => gameBetId(x) === state.propId);
    if (b) return renderGameBetPage(b);
  }
  const r = allProps().find((x) => propId(x) === state.propId);
  if (!r) {
    // A bookmarked or stale link. Say so — a blank page reads as broken.
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("search", 30)}</div>
      <h3>That pick is not on tonight’s board</h3>
      <p>Props are rebuilt every slate, so a link to one only lives as long
      as the pick does.</p>
      <button class="btn ghost gp-back" id="pp-back">← Back to the board</button></div>`;
    const b0 = document.getElementById("pp-back");
    if (b0) b0.addEventListener("click", () => switchView("recommended"));
    return;
  }
  const over = String(r.side || "OVER").toUpperCase() === "OVER";
  const line = Number(r.line);
  const logs = (r.logs || []).filter((g) => Number.isFinite(Number(g.value)));
  const N = 5;
  const shown = Math.min(N, logs.length);
  const proj = r.projection != null
    ? `<div class="metric"><div class="k">Projection</div><div class="v">${
        Number(r.projection).toFixed(1)}${r.proj_low != null
        ? ` <span class="sub">(${Number(r.proj_low).toFixed(0)}–${
            Number(r.proj_high).toFixed(0)})</span>` : ""}</div></div>` : "";
  const reasons = (r.reasons || []).slice(0, 8)
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  host.innerHTML = `
    <button class="btn ghost gp-back" id="pp-back">← Back to the board</button>
    <article class="card pp-card">
      <div class="card-head">
        <div class="card-id">${betMark(r, 56)}
          <div>
            <div class="player">${escapeHtml(r.player || "")}
              <span class="ml-odds">${r.odds > 0 ? "+" : ""}${r.odds}</span></div>
            <div class="subtitle">${escapeHtml([r.position,
              typeof teamName === "function" ? teamName(r.team) : r.team,
              r.opponent ? `vs ${typeof teamName === "function"
                ? teamName(r.opponent) : r.opponent}` : ""]
              .filter(Boolean).join(" · "))}</div>
            <div class="pick">${escapeHtml(r.side || "")} ${
              Number.isFinite(line) ? escapeHtml(String(line)) : ""} ${
              escapeHtml(r.market_label || r.market || "")}</div>
          </div>
        </div>
        ${r.grade ? `<span class="grade ${gradeClass(r.grade)}">${
          escapeHtml(r.grade)}</span>` : ""}
      </div>
      <div class="metrics">
        ${proj}
        ${r.hit_prob != null ? `<div class="metric"><div class="k">Model</div>
          <div class="v">${pct(r.hit_prob)}</div></div>` : ""}
        ${r.edge != null ? `<div class="metric primary"><div class="k">Edge</div>
          <div class="v ${r.edge >= 0 ? "pos" : "neg"}">${signedPct(r.edge)}</div></div>` : ""}
        ${/* EV deliberately absent: the chart's own stat row below carries
              it, and a number twice on one screen is the duplication Ethan
              had just finished pointing at on the prop cards. Three
              metrics also fill the row instead of wrapping one onto a
              second line by itself. */""}
      </div>
      ${propAnalysis(r)}
    </article>

    ${shown ? `<div class="section-title">Last ${shown} game${shown === 1 ? "" : "s"}
      <span class="sub">— every one measured against tonight’s
      ${Number.isFinite(line) ? escapeHtml(String(line)) : "line"}, newest
      first, with who it came against.</span></div>
    <div class="card pp-logs">${propLogRows(r, logs, line, over, N)}</div>` : ""}

    ${(r.form && Object.keys(r.form).length) ? `<div class="section-title minor">Form
      <span class="sub">— the same player over longer windows, each read
      against the same number.</span></div>
    <div class="card pp-forms">${propFormRows(r.form, line, over)}</div>` : ""}

    ${reasons ? `<div class="section-title minor">Why this pick</div>
      <div class="card"><ul class="reasons">${reasons}</ul></div>` : ""}`;
  const b = document.getElementById("pp-back");
  if (b) b.addEventListener("click", () => switchView("recommended"));
  if (typeof fillMeters === "function") fillMeters(host);
}

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
    <p class="pk-note">Football fields are the same size everywhere, so a venue’s
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
      <div class="es-title">That game isn’t on the current slate</div>
      <div class="es-sub">Slates roll over each day. Head back to the board for
      today’s games.</div></div>
      <button class="btn ghost gp-back" id="gp-back" style="margin-top:14px">← Back to the board</button>`;
    const b = document.getElementById("gp-back");
    if (b) b.addEventListener("click", () => switchView("recommended"));
    return;
  }
  const mlb = state.sport === "mlb";
  const nba = state.sport === "nba" || state.sport === "wnba";
  const w = g.weather || {};
  // Park factors. This line was DROPPED in the 08-11 desktop-sheet
  // rewrite while two Key-insights lines kept reading f.hr — and
  // because both sit behind `mlb &&`, the short-circuit hid the
  // ReferenceError from every NFL page while EVERY MLB game page
  // crashed blank for a week (Ethan, 2026-08-18: "it just takes you
  // to a blank screen"). A guard that only trips on one sport is why
  // the render sweep and the NFL-fixture tests stayed green.
  const f = g.factors || {};
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

  // The hero wears the same venue art chain as the strip card (Ethan's
  // desktop event-page render, 2026-08-11): team photo, else the
  // colour-matched family render, else the drawing.
  //
  // AND A LIVE GAME GETS THE PHOTO TOO. Ethan, 2026-08-13: "when you
  // click on the stadium, it still shows the old stadium on this page."
  // The strip card had exactly this bug and exactly this cause — a
  // `!isLive` guard that suppressed the photograph and left the drawn
  // ballpark showing — and fixing it there left the game page, which is
  // where you land when you click the card, still doing it. So the same
  // stadium changed appearance between the strip and the page behind it,
  // which reads as two different venues rather than one bug.
  //
  // The drawing carried the live bases, which is why the guard existed.
  // The runner overlay carries them now, over the photo, so nothing is
  // lost by showing it.
  const gpFam = VENUE_FAMILY[state.sport];
  const gpPhoto = `<img class="venue-photo" alt="" loading="lazy"
      src="${venueSrc(`img/venues/${escapeHtml(state.sport)}/${escapeHtml(g.home)}.jpg`)}"
      ${gpFam ? `data-alt="${venueSrc(`img/venues/variants/${gpFam}-${venueVariant((window.ACTIVE_TEAMS || {})[g.home] || {})}.jpg`)}"
      onerror="vpFall(this)"` : `onerror="this.remove()"`}/>`;
  // The render's GAME LINES table and KEY INSIGHTS panel. Lines come
  // straight off the slate; a cell without a real price shows a dash.
  // Insights are the game's own data fields, not narratives.
  const gpFav = g.favorite || g.home;
  const gpSp = (side) => g.spread == null ? "—"
    : `${side === gpFav ? "−" : "+"}${Math.abs(g.spread).toFixed(1)}`;
  const gpMl = (v) => v == null ? "—" : `${v > 0 ? "+" : ""}${v}`;
  const linesCard = (g.spread != null || g.total != null
                     || g.away_ml != null || g.home_ml != null) ? `
    <div class="card gp-lines"><div class="gp-panel-title">Game lines</div>
      <div class="lb-table">
        <span class="lb-th"></span><span class="lb-th">Spread</span>
        <span class="lb-th">Total</span><span class="lb-th">ML</span>
        <span class="lb-tm">${teamMark(g.away, 20)} ${escapeHtml(g.away)}</span>
        <b>${gpSp(g.away)}</b><b>${g.total != null ? "O " + g.total.toFixed(1) : "—"}</b>
        <b>${gpMl(g.away_ml)}</b>
        <span class="lb-tm">${teamMark(g.home, 20)} ${escapeHtml(g.home)}</span>
        <b>${gpSp(g.home)}</b><b>${g.total != null ? "U " + g.total.toFixed(1) : "—"}</b>
        <b>${gpMl(g.home_ml)}</b>
      </div></div>` : "";
  const notes = [];
  (g.injuries || []).slice(0, 4).forEach((i) => notes.push(
    `${i.player} (${i.team} ${i.position || ""}) — ${i.status}`));
  if (g.lineups_confirmed === false) notes.push("Lineups not confirmed yet");
  if (mlb && f.hr >= 1.05) notes.push(`Park boosts home runs +${Math.round((f.hr - 1) * 100)}%`);
  if (mlb && f.hr && f.hr <= 0.95) notes.push(`Park suppresses home runs ${Math.round((f.hr - 1) * 100)}%`);
  if (!w.dome && (w.wind_mph || 0) >= 12) notes.push(
    `${Math.round(w.wind_mph)}mph wind${w.wind_dir ? " " + w.wind_dir : ""}`);
  if (!w.dome && (w.precip_chance || 0) >= 0.4) notes.push(
    `${Math.round(w.precip_chance * 100)}% precipitation chance`);
  if (g.doubleheader) notes.push(`Doubleheader — game ${g.game_number || 1}`);
  const notesCard = notes.length ? `
    <div class="card gp-notes"><div class="gp-panel-title">Key insights
        <span class="gp-panel-sub">— this game’s own data, not narratives</span></div>
      <ul class="gp-note-list">${notes.map((n) =>
        `<li>${escapeHtml(n)}</li>`).join("")}</ul></div>` : "";
  // The replay panel — the drive sim's diagnostics for THIS game, shares
  // and shape only. It prices nothing (engine/drivesim.ENABLED stays
  // False until the public reconciliation says otherwise), and the card
  // says so in its own words.
  const sim = g.sim;
  const simCard = sim ? (() => {
    const share = (v) => `${Math.round(100 * (v || 0))}%`;
    const histLabels = [`${g.home} 15+`, `${g.home} 8–14`, `${g.home} 1–7`,
                        `${g.away} 1–7`, `${g.away} 8–14`, `${g.away} 15+`];
    const maxH = Math.max(...(sim.margin_hist || [0.001]), 0.001);
    return `
    <div class="card gp-sim"><div class="gp-panel-title">The replay
        <span class="gp-panel-sub">— this matchup run ${(sim.trials || 0).toLocaleString()}
        times, drive by drive</span></div>
      <div class="gp-sim-tiles">
        <span><b>${share(sim.p_home_win)}</b> ${escapeHtml(g.home)} wins</span>
        <span><b>${share(sim.one_score)}</b> one-score game</span>
        <span><b>${share(sim.blowout)}</b> decided by 14+</span>
      </div>
      <div class="gp-sim-viz">
        <div class="gp-sim-gauge" data-echart-gauge="${escapeAttr(JSON.stringify({
          value: sim.p_home_win || 0,
          title: `${g.home} win share`,
        }))}"></div>
        <div class="gp-sim-hist" data-echart-hist="${escapeAttr(JSON.stringify({
          values: sim.margin_hist || [], labels: histLabels,
        }))}">${(sim.margin_hist || []).map((v, i) => `
        <div class="gp-sim-col" title="${escapeAttr(histLabels[i])} — ${(100 * v).toFixed(1)}% of replays">
          <span class="gp-sim-bar" style="height:${Math.max(3, 56 * v / maxH).toFixed(0)}px"></span>
          <span class="gp-sim-lbl">${escapeHtml(histLabels[i])}</span>
        </div>`).join("")}</div>
      </div>
      <p class="gp-sim-joint">${escapeHtml(g.home)} covers ${share(sim.cover)} ·
        over ${share(sim.over)} · both ${share(sim.cover_and_over)}
        (${(sim.joint_lift || 0) >= 0 ? "+" : "−"}${Math.abs(100 * (sim.joint_lift || 0)).toFixed(1)}pt
        vs independent legs)</p>
      <p class="gp-sim-note">Anchored to the posted line — the replays reproduce the
        market’s expected points and add the shape of the game around them. This
        panel is not a pick, and the sim prices nothing until the public
        reconciliation says it should.</p>
    </div>`;
  })() : "";
  // Team shapes — the two-team radar (ECharts ladder, Ethan 2026-08-18).
  // Five measured axes, league percentiles from the last rankable
  // season's finals (engine/teamshape.py). The fallback INSIDE the
  // wrapper is the same numbers as a table, so an engine-less machine
  // still reads the comparison.
  const _shapes = (state.data || {}).team_shapes || {};
  const _sh = _shapes[g.home], _sa = _shapes[g.away];
  const shapeCard = _sh && _sa ? (() => {
    const season = state.data.team_shapes_season || "";
    const axes = ["offense", "defense", "form", "home_edge", "steadiness"];
    const names = { offense: "Offense", defense: "Defense", form: "Form",
                    home_edge: "Home edge", steadiness: "Steadiness" };
    const rows = axes.map((a) => `<tr><td>${names[a]}</td>
      <td class="num">${Number(_sh.pct[a]).toFixed(0)}</td>
      <td class="num">${Number(_sa.pct[a]).toFixed(0)}</td></tr>`).join("");
    return `
    <div class="card gp-shape"><div class="gp-panel-title">Team shapes
        <span class="gp-panel-sub">— ${season} measured profile, league
        percentiles (${_sh.games} and ${_sa.games} finals)</span></div>
      <div class="gp-shape-radar" data-echart-radar="${escapeAttr(JSON.stringify({
        axes: axes.map((a) => names[a]),
        series: [
          { name: g.home, values: axes.map((a) => Number(_sh.pct[a]) || 0) },
          { name: g.away, values: axes.map((a) => Number(_sa.pct[a]) || 0) },
        ],
      }))}"><table class="agate gp-shape-tbl"><thead><tr><th></th>
          <th>${escapeHtml(g.home)}</th><th>${escapeHtml(g.away)}</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <p class="gp-sim-note">Percentile against the whole league on last season’s
        finals: offense is points scored, defense is points allowed (fewer ranks
        higher), form is the last five margins, home edge is home-minus-road
        margin, steadiness is low variance. Measured shape, not a projection —
        and last season’s roster is not this season’s.</p>
    </div>`;
  })() : "";
  host.innerHTML = `
    <button class="btn ghost gp-back" id="gp-back">← Back to the board</button>
    <div class="gp-hero">
      <div class="gp-art">${art}${gpPhoto}
        ${mlb && isLive ? runnerOverlay(g) : ""}
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

    ${linesCard || notesCard ? `<div class="gp-row">${linesCard}${notesCard}</div>` : ""}
    ${simCard}
    ${shapeCard}

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
          <div class="es-sub">Either the model passes on everything here, or books haven’t
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
  // The replay panel's gauge + histogram upgrade in place when the
  // vendored ECharts loads; the div bars above stay as the fallback.
  if (typeof mountEChartsPanels === "function") mountEChartsPanels(host);
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
        : `<span style="opacity:.55">pass — didn’t clear the gates</span>` },
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
      <div class="mini">${gamelogBars(vals, { w: 78, h: 30, stroke: col.stroke })}</div>
      ${col.metric(r)}
    </div>`;
}

/* ============================================================
   Players view — search + profile
   ============================================================ */
async function renderPlayers() {
  const q = state.search.trim().toLowerCase();
  // Cached after the first call; every profile header tags a current
  // designation from it, whatever the sport.
  await loadInjuryBoard();
  let recs = state.data.recommendations;
  if (q) recs = recs.filter((r) => r.player.toLowerCase().includes(q));
  // One CARD per player, every market kept. The old dedupe ("first
  // market listed") threw the rest of a player's rows away — Ethan,
  // 2026-08-17: "when i search an nfl player it will only display yard
  // props … i also wanna be able to maybe see reception props with the
  // chart". The card's chips carry tonight's other priced markets AND
  // the build's player_stats history (engine/statlogs.py).
  _profRows = new Map();
  recs.forEach((r) => {
    if (!_profRows.has(r.player)) _profRows.set(r.player, []);
    _profRows.get(r.player).push(r);
  });
  const players = [..._profRows.keys()];
  const host = document.getElementById("players");
  if (!players.length) {
    /* THE LEAGUE, NOT THE BOARD. Ethan, 2026-08-18: "The search page for
       players isn't working still. You should be able too look up any
       player in the league too that specific sport." The board only
       knows tonight's priced players; /api/players/search reads the
       history DB — everyone who has ever appeared in an ingested game —
       and /api/players/logs returns the same multi-market shape the
       board's player_stats ships, so a searched-up bench bat gets the
       exact profile card a priced star gets. The roster directory stays
       as the offline fallback: a static host has no /api. */
    if (q) {
      const hits = await leagueSearch(q);
      if (state.search.trim().toLowerCase() !== q) return;  // stale keystroke
      if (hits.length) {
        const full = hits.slice(0, 4);
        await Promise.all(full.map(async (m) => {
          const store = (state.data.player_stats =
            state.data.player_stats || {});
          if (!store[m.player]) {
            const st = await leagueLogs(m.player);
            if (st && Object.keys(st).length) store[m.player] = st;
          }
          // A head-only row: profileHTML draws the history card from it
          // plus the injected stats. No market_label, so it can never
          // masquerade as a priced market.
          _profRows.set(m.player, [{ player: m.player, team: m.team,
                                     position: m.position, opponent: "",
                                     headshot: m.headshot }]);
        }));
        if (state.search.trim().toLowerCase() !== q) return;
        const drawn = full.filter((m) =>
          ((state.data.player_stats || {})[m.player]));
        const rest = hits.filter((m) => !drawn.some((d) => d.player === m.player));
        host.innerHTML = `
          <div class="section-title minor">From the
            ${escapeHtml(String(state.sport || "").toUpperCase())} game logs
            <span class="sub">— nothing priced on tonight’s board for
            “${escapeHtml(state.search)}”, so these are the logged games</span></div>
          <div class="player-grid">${drawn.map((m) => profileHTML(m.player)).join("")}</div>
          ${rest.length ? `<div class="section-title minor">Also matching</div>` : ""}
          ${rest.map((m) => `
            <div class="card roster-hit" style="display:flex;gap:12px;align-items:center;padding:12px 16px;margin-bottom:8px">
              ${playerAvatar(m.player, m.team, { size: 40, headshot: m.headshot })}
              <div style="flex:1;min-width:0">
                <strong>${escapeHtml(m.player)}</strong>${injTag(state.sport || "nfl", m.player)}
                <div style="font-size:.85em;color:var(--text-mute)">
                  ${teamMark(m.team, 14)} ${escapeHtml(teamName(m.team))}
                  · ${escapeHtml(m.position || "—")}
                  · ${m.games} game(s) logged</div>
              </div>
              <button class="btn" data-lookup="${escapeAttr(m.player)}">Profile</button>
            </div>`).join("")}`;
        host.querySelectorAll("[data-lookup]").forEach((b) =>
          b.addEventListener("click", () => {
            const inp = document.getElementById("player-search");
            state.search = b.dataset.lookup;
            if (inp) inp.value = b.dataset.lookup;
            renderPlayers();
          }));
        return;
      }
    }
    /* The roster directory — the offline fallback, and the only answer
       for a player who has never appeared in a logged game. */
    const misses = q ? await rosterMatches(q) : [];
    if (misses.length) {
      host.innerHTML = `
        <div class="empty" style="margin-bottom:12px">No prop on tonight’s board for
          “${escapeHtml(state.search)}” — profiles here are prop cards.
          On the roster${misses.length > 1 ? "s" : ""}:</div>
        ${misses.map((m) => `
          <div class="card roster-hit" style="display:flex;gap:12px;align-items:center;padding:12px 16px;margin-bottom:8px">
            ${playerAvatar(m.player, m.team, { size: 40, headshot: m.headshot })}
            <div style="flex:1;min-width:0">
              <strong>${escapeHtml(m.player)}</strong>${injTag(state.sport || "nfl", m.player)}
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
    if (!q) {
      /* Not a failed search — the BOARD is empty (an offseason league,
         or a slate not yet priced). Ethan's render sweep, 2026-08-18:
         NBA Players drew 20 characters — the failed-search apology with
         an empty quote in it, on a page nobody had searched. Say the
         true thing instead: profiles are prop cards, and this league
         has none priced tonight. */
      host.innerHTML = `<div class="empty">No priced props on the
        ${escapeHtml(String(state.sport || "").toUpperCase())} board tonight,
        so there are no player profiles to draw — they are built from the
        board’s prop cards. The page fills as soon as a slate prices.</div>`;
      return;
    }
    host.innerHTML = `<div class="empty">No players match “${escapeHtml(state.search)}”.</div>`;
    return;
  }
  // MEASURED IN CHROMIUM, 2026-08-08: with no query this rendered 293 full
  // profiles — 4,315 table rows and 139,451px of page. A hundred and
  // fifty-five screens, on the page whose own tab hint is "search a
  // player". The search box was filtering a DOM that had already been
  // built in full.
  //
  // So an unsearched visit shows a browsable handful and says how many
  // there are. Searching still reaches every one of them: the filter runs
  // over the whole list above and only the DISPLAY is capped.
  const cap = playerBrowseCap();
  const capped = !q && players.length > cap;
  const shown = capped ? players.slice(0, cap) : players;
  host.innerHTML = (capped ? `<p class="browse-note">Showing ${shown.length}
      of ${players.length} players with a prop on tonight’s board —
      type a name to find anyone else.</p>` : "")
    + shown.map(profileHTML).join("");
  fillMeters(host);
  revealChildren(host);
  // Market chips: swap ONE card in place, keep the rest of the page
  // still. Delegated and bound once — innerHTML above rebuilds children,
  // not the host, so a per-card listener would leak one copy per render.
  if (!host._profBound) {
    host._profBound = true;
    host.addEventListener("click", (e) => {
      const chip = e.target.closest(".prof-tab");
      if (!chip) return;
      _profTab[chip.dataset.player] = chip.dataset.mkt;
      const card = chip.closest(".profile");
      if (!card) return;
      const tmp = document.createElement("div");
      tmp.innerHTML = profileHTML(chip.dataset.player);
      const fresh = tmp.firstElementChild;
      if (!fresh) return;
      fresh.classList.add("reveal", "in");   // already on screen — no re-entrance
      card.replaceWith(fresh);
      fillMeters(fresh.parentElement || fresh);
    });
  }
}

//: The chosen market per player. Outlives renders on purpose: flipping
//: to Receptions and refreshing the search should not snap you back.
const _profTab = {};
//: Tonight's rec rows per player, rebuilt by every renderPlayers pass.
let _profRows = new Map();

//: How many profiles an unsearched Players page draws.
//:
//: TWO NUMBERS, BECAUSE THE GRID IS NOT ONE LAYOUT. A profile is a tall
//: card — chart, form table, meters — and `.player-grid` is
//: `auto-fill, minmax(420px, 1fr)`: three columns on a laptop, ONE on a
//: phone. Measured at 390x844 after the first cap shipped, twelve cards
//: stacked single-file came to 10,919px — 12.9 screens, which is the
//: original complaint again on the device least able to afford it.
//:
//: Read at render rather than at load: a rotated phone or a resized window
//: is the same visitor, and a constant captured once would leave them with
//: whichever layout they happened to start in.
function playerBrowseCap() {
  return (typeof window !== "undefined" && window.matchMedia
    && window.matchMedia("(max-width: 760px)").matches) ? 4 : 12;
}

/* The league-wide search pair. Cached per (sport, query) because the
   input handler re-renders on every keystroke and the answer for "jud"
   does not change between letters typed and deleted. A failed fetch
   caches [] for the session — the roster fallback takes over, and a
   static host is not retried on every key. */
const _leagueCache = new Map();
async function leagueSearch(q) {
  const key = `${state.sport}|${q}`;
  if (_leagueCache.has(key)) return _leagueCache.get(key);
  let hits = [];
  try {
    const r = await fetch(`/api/players/search?sport=${encodeURIComponent(state.sport)}&q=${encodeURIComponent(q)}`);
    if (r.ok) hits = (await r.json()).players || [];
  } catch (e) {}
  _leagueCache.set(key, hits);
  return hits;
}

async function leagueLogs(player) {
  try {
    const r = await fetch(`/api/players/logs?sport=${encodeURIComponent(state.sport)}&player=${encodeURIComponent(player)}`);
    if (r.ok) return (await r.json()).stats || {};
  } catch (e) {}
  return {};
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

/* One card, many markets. The chips list every market we can say
   anything about: tonight's PRICED rows first (chip shows the line),
   then history-only markets from the build's player_stats — receptions,
   targets, hits, homers — which chart the player's games without
   pretending there is a bet (no line, no pick block, and the card says
   so). Ethan, 2026-08-17: "i should be able to see how they did with
   multipul props." */
function profileHTML(player) {
  const rows = _profRows.get(player) || [];
  const stats = ((state.data || {}).player_stats || {})[player] || {};
  // A searched-up league player rides in on a HEAD-ONLY row (no
  // market_label) — it feeds _profileHead and must never register as a
  // priced market, or an unpriced chip draws the pick block.
  const priced = new Map(rows.filter((r) => r.market_label)
    .map((r) => [r.market_label, r]));
  const tabs = [...priced.keys(),
                ...Object.keys(stats).filter((k) => !priced.has(k))];
  if (!tabs.length) return "";
  let mkt = _profTab[player];
  if (!tabs.includes(mkt)) mkt = tabs[0];
  const chips = tabs.length > 1 ? `<div class="prof-tabs" role="tablist"
      aria-label="Markets for ${escapeAttr(player)}">
      ${tabs.map((t) => `<button type="button" role="tab"
          class="prof-tab ${t === mkt ? "active" : ""}"
          aria-selected="${t === mkt}"
          data-player="${escapeAttr(player)}" data-mkt="${escapeAttr(t)}">
          ${escapeHtml(t)}${priced.has(t)
            ? ` <b>${priced.get(t).line}</b>` : ""}</button>`).join("")}
    </div>` : "";
  return priced.has(mkt)
    ? pricedProfileHTML(priced.get(mkt), chips)
    : historyProfileHTML(rows[0], mkt, stats[mkt] || [], chips);
}

//: Shared head: who this is, on the market's accent.
function _profileHead(r, right) {
  return `<div class="profile-head">
        ${playerAvatar(r.player, r.team, { size: 60, headshot: r.headshot })}
        <div class="meta"><div class="nm">${escapeHtml(r.player)}${injTag(state.sport || "nfl", r.player)}</div>
          <div class="sub">${teamMark(r.team, 16)} ${[teamName(r.team), r.position, "vs " + teamName(r.opponent)]
            .filter((x) => x && x !== "vs ").map(escapeHtml).join(" · ")}</div></div>
        ${right}
      </div>`;
}

function pricedProfileHTML(r, chips) {
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
      ${_profileHead(r, `<span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade)}</span>`)}
      ${chips}
      <div class="form-tiles">${tiles}</div>
      <div class="profile-spark">${gamelogBars(vals, {
        line: r.line, stroke: teamPrimary(r.team), w: 320, h: 72,
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

/* A market nobody priced tonight: the history IS the content. Chart and
   log only — averages without a line to read them against would invite
   the reader to invent one. */
function historyProfileHTML(r0, label, logs, chips) {
  const vals = logs.map((l) => l.value);
  const nfl = logs.length && logs[0].week != null && !logs[0].date;
  const when = (l) => (nfl ? `Wk ${l.week}`
    : (l.date ? formatGameDate(l.date) : `G ${l.week}`));
  const rows = logs.map((l) => `<tr><td>${escapeHtml(when(l))}</td>
      <td>${l.home ? "vs" : "@"} ${escapeHtml(l.opponent)}</td>
      <td class="num">${l.value}</td></tr>`).join("");
  const grad = `linear-gradient(135deg, ${teamPrimary(r0.team)}, transparent)`;
  return `
    <article class="profile" style="--profile-grad:${grad}">
      ${_profileHead(r0, "")}
      ${chips}
      <div class="profile-spark">${gamelogBars(vals, {
        stroke: teamPrimary(r0.team), w: 320, h: 72,
        labels: logs.map((l) => `${when(l)} ${l.home ? "vs" : "@"} ${l.opponent}`),
      })}</div>
      <table class="log-table">
        <tr><th>${nfl ? "Week" : "Game"}</th><th>Opponent</th><th style="text-align:right">${escapeHtml(label)}</th></tr>
        ${rows}
      </table>
      <div class="profile-pick"><div class="lbl">${escapeHtml(label)}
        <small>no line on tonight’s board — his last ${logs.length} games, for the read</small></div></div>
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

function recCurveChart(curve, opts = {}) {
  if (!curve || curve.length < 2) return "";
  const w = 640, h = 190, padL = 46, padR = 14, padT = 16, padB = 28;
  const cums = curve.map((p) => p.cum_u);
  let lo = Math.min(0, ...cums), hi = Math.max(0, ...cums);
  if (hi - lo < 0.5) { hi += 0.25; lo -= 0.25; }
  const x = (i) => padL + (i / (curve.length - 1)) * (w - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB);
  const path = curve.map((p, i) => `${x(i).toFixed(1)},${y(p.cum_u).toFixed(1)}`).join(" L");
  const last = curve[curve.length - 1];
  const color = last.cum_u >= 0 ? "var(--good)" : "var(--bad)";
  // day_u is derivable from the running total, so a payload without it
  // gets the derived number instead of a TypeError. This mattered: a
  // fixture missing the field crashed recCurveChart, and because the
  // whole page is one template literal, the exception blanked EVERY
  // section of the Record page — one optional field, zero pages.
  const dayOf = (p, i) => (p.day_u != null ? p.day_u
    : p.cum_u - (i ? curve[i - 1].cum_u : 0));
  const dots = curve.map((p, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(p.cum_u).toFixed(1)}" r="${i === curve.length - 1 ? 3.4 : 2.4}" fill="${color}"/>`)
    .join("");
  // Scrubbing replaced the per-dot hover circles (2026-08-18, Ethan:
  // "glide your finger across it an it will show the data") — one
  // finger or cursor position, one label, no 10px targets to hunt for.
  const scrub = escapeAttr(JSON.stringify({
    padL, padR,
    l: curve.map((p) => `${p.date} · ${p.n} bet${p.n === 1 ? "" : "s"}`),
    v: curve.map((p, i) => {
      const dayU = dayOf(p, i);
      return `running ${p.cum_u >= 0 ? "+" : ""}${p.cum_u.toFixed(2)}u · day ${
        dayU >= 0 ? "+" : ""}${dayU.toFixed(2)}u`;
    }),
  }));
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
  const head = `
    <div class="section-title">Running P&amp;L
      <span class="sub">— every settled pick, by slate date</span></div>`;
  return `
    ${opts.head === false ? "" : head}
    <div class="card rec-chart">
      <div class="rc-head">
        <div class="rc-net ${toneOf(net)}">${net >= 0 ? "+" : ""}${net.toFixed(2)}u</div>
        <div class="rc-span">${escapeHtml(curve[0].date)} → ${escapeHtml(last.date)}
          · ${curve.length} slate${curve.length === 1 ? "" : "s"}</div>
      </div>
      <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;display:block" role="img"
           aria-label="Cumulative units won or lost over time" data-scrub="${scrub}">
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
      <div class="rc-foot">Slide a finger (or the cursor) along the chart for each
        day’s bets. Flat units — every pick weighted by its stake, no bankroll
        compounding.</div>
    </div>`;
}

/* The analytics block from Ethan's render sheet (2026-08-11): range
   chips over the equity curve, with NET / WIN RATE / ROI and the bet
   counts computed INSIDE the chosen window — the curve rows carry each
   day's wins, losses and stake precisely so a 1-month chart never sits
   above all-time numbers. Negative numbers stay red; a window with no
   graded bets says so instead of showing zeros. */
let _recRange = "all";
window._recSetRange = (k) => { _recRange = k; renderRecord(); };

/* Splits — ONE table with a switcher, not four stacked (2026-08-17,
   Ethan: "its very cluttered"). With a real journal the market table
   alone runs 14+ rows, and four tables of headers made the page read
   like a spreadsheet dump. Every split survives; one shows at a time. */
let _recSplit = "market";
window._recSetSplit = (k) => { _recSplit = k; renderRecord(); };

//: Raw market ids are engine vocabulary; the reader gets words. Only
//: known ids transform — grades, sides and book names pass through.
const MARKET_WORDS = {
  total_bases: "Total Bases", hits: "Hits", home_runs: "Home Runs",
  strikeouts: "Strikeouts", outs: "Outs Recorded",
  pass_yds: "Passing Yards", rush_yds: "Rushing Yards",
  rec_yds: "Receiving Yards", receptions: "Receptions",
  anytime_td: "Anytime TD", moneyline: "Moneyline", spread: "Spread",
  total: "Game Total", team_total: "Team Total", points: "Points",
  rebounds: "Rebounds", assists: "Assists", pra: "Pts+Reb+Ast",
};

function recSplitsSection(o) {
  const SPLITS = [["market", "Market", o.by_market],
                  ["side", "Side", o.by_side],
                  ["grade", "Grade", o.by_grade],
                  ["book", "Book", o.by_book]];
  const avail = SPLITS.filter(([, , t]) => t && Object.keys(t).length);
  if (!avail.length) return "";
  const cur = avail.find(([k]) => k === _recSplit) || avail[0];
  const pretty = cur[0] === "market"
    ? Object.fromEntries(Object.entries(cur[2]).map(([k, v]) =>
        [MARKET_WORDS[k] || k, v]))
    : cur[2];
  const chips = avail.length > 1 ? `<span class="ra-ranges">${avail.map(([k, label]) =>
    `<button class="ra-range ${k === cur[0] ? "active" : ""}"
       onclick="_recSetSplit('${k}')">${label}</button>`).join("")}</span>` : "";
  return `
    <div class="section-title">Splits
      <span class="sub">— where the units actually came from. The bar is win rate;
      the number that matters is net.</span>
      ${chips}</div>
    <div class="rec-buckets rec-buckets-one">
      ${recBucketTable(`By ${cur[1].toLowerCase()}`, pretty)}
    </div>`;
}

/* Recent picks — first dozen, then a real count on the button. Thirty
   rows of agate by default buried everything after it. */
let _recAllPicks = false;
window._recShowPicks = () => { _recAllPicks = true; renderRecord(); };

function recRecentSection(recent) {
  const shown = _recAllPicks ? recent : recent.slice(0, 12);
  const more = recent.length - shown.length;
  return `
    <div class="section-title">Recent settled picks
      <span class="sub">— newest first, at the price we actually got</span></div>
    <div class="card rec-list">
      ${shown.map(recSettledRow).join("") || `<p class="loading" style="padding:12px">Nothing settled yet.</p>`}
      ${more > 0 ? `<button class="rec-more" onclick="_recShowPicks()">
        Show all ${recent.length} settled picks</button>` : ""}
    </div>`;
}
function recAnalytics(curve, o) {
  if (!curve || curve.length < 2) return recCurveChart(curve);
  const spanDays = (new Date(curve[curve.length - 1].date)
                    - new Date(curve[0].date)) / 864e5;
  const RANGES = [["1w", 7], ["1m", 30], ["3m", 91], ["all", Infinity]];
  // A chip only exists when it would show a different window than ALL.
  const avail = RANGES.filter(([k, d]) => k === "all" || spanDays > d);
  let rk = avail.some(([k]) => k === _recRange) ? _recRange : "all";
  const days = (avail.find(([k]) => k === rk) || [null, Infinity])[1];
  // Guard the Date math: Infinity days (the ALL window) must never reach
  // toISOString — an invalid Date throws and, because the page is one
  // template literal, one throw blanks every section of the Record page.
  const rows = !isFinite(days) ? curve : curve.filter((p) =>
    p.date >= new Date(Date.now() - days * 864e5).toISOString().slice(0, 10));
  if (!rows.length) {
    return `<div class="section-title">Running P&amp;L
        <span class="sub">— every settled pick, by slate date</span>
        ${raChips(avail, rk)}</div>
      <p class="rail-quiet" style="margin:0 0 18px">Nothing settled in this
        window — pick a longer range.</p>`;
  }
  // Rebase the running total so the window tells the window's story.
  const first = curve.indexOf(rows[0]);
  const base = first > 0 ? curve[first - 1].cum_u : 0;
  const sliced = rows.map((p) => ({ ...p, cum_u: +(p.cum_u - base).toFixed(2) }));
  const net = sliced[sliced.length - 1].cum_u;
  const hasWL = rows.every((p) => p.w != null);
  const wins = hasWL ? rows.reduce((a, p) => a + p.w, 0) : (rk === "all" ? o.wins : null);
  const losses = hasWL ? rows.reduce((a, p) => a + p.l, 0) : (rk === "all" ? o.losses : null);
  const staked = hasWL ? rows.reduce((a, p) => a + (p.staked || 0), 0)
    : (rk === "all" ? o.units_staked : null);
  const nBets = rows.reduce((a, p) => a + (p.n || 0), 0);
  const roi = staked ? net / staked : null;
  const wr = wins != null && (wins + losses) > 0 ? wins / (wins + losses) : null;
  // DECLUTTERED 2026-08-17 (Ethan: "its very cluttered and nees to be
  // easiler to read"). This block used to repeat the scoreboard three
  // times: a 3-tile column beside the curve (net/win rate/ROI — all in
  // the hero tiles above), a graded/won/lost tile row (the RECORD tile,
  // again), and a 4-tile all-time row. Every number survives — the
  // range-scoped ones on one line under the curve, the all-time ones on
  // one ledger line — but each now appears ONCE.
  const line = (parts) => parts.filter(Boolean).join(" · ");
  const range = line([
    wins != null && `<b>${wins}-${losses}${nBets > wins + losses ? `-${nBets - wins - losses}` : ""}</b> in this window`,
    wr != null && `win rate <b>${(wr * 100).toFixed(1)}%</b>`,
    roi != null && `ROI <b class="${toneOf(roi)}">${roi >= 0 ? "+" : ""}${(roi * 100).toFixed(1)}%</b>`,
    `net <b class="${toneOf(net)}">${net >= 0 ? "+" : ""}${net.toFixed(2)}u</b>`,
  ]);
  const alltime = o.avg_price == null && o.best_streak == null ? "" : line([
    `<b>${(o.units_staked || 0).toFixed(1)}u</b> staked all-time`,
    `<b>${(o.returned_units || 0).toFixed(1)}u</b> returned (stake back + winnings)`,
    o.avg_price != null && `avg price <b>${(o.avg_price > 0 ? "+" : "") + o.avg_price}</b>`,
    o.best_streak != null && `best win streak <b>${o.best_streak}</b>`,
  ]);
  return `
    <div class="section-title">Running P&amp;L
      <span class="sub">— every settled pick, by slate date</span>
      ${raChips(avail, rk)}</div>
    <div class="ra-main">
      ${recCurveChart(sliced, { head: false })}
    </div>
    <p class="ra-line">${range}</p>
    ${alltime ? `<p class="ra-line ra-dim">${alltime}</p>` : ""}`;
}
function raChips(avail, rk) {
  if (avail.length < 2) return "";
  return `<span class="ra-ranges">${avail.map(([k]) =>
    `<button class="ra-range ${k === rk ? "active" : ""}"
       onclick="_recSetRange('${k}')">${k.toUpperCase()}</button>`).join("")}</span>`;
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
      `<p class="loading" style="padding:12px">No ticket has settled yet — accrues from tonight’s board.</p>`}${codes}</div>`;
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
    ${recDisclosure("Why these are quarantined", `Only the board’s actual
      PICKS — three per night at most — count toward this record, graded at a flat 0.1u
      nominal stake with zero bankroll impact. The watchlist (every real-priced home run
      on the slate, sometimes 100+ names) is tracked separately as a calibration sample
      and never enters this W-L: recommend a couple hundred homers a night and a handful
      always land, which proves nothing. These markets are long shots by nature, so even
      picks that clear the main board’s bar are quarantined here — a night of +650 darts
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
      `<p class="loading" style="padding:12px">Nothing settled yet — accrues from tonight’s board.</p>`}${watch}</div>`;
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
      Scored against the de-vigged closing price on the same bets — if we can’t
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
        ${s.markets_held_back} more market(s) haven’t reached ${s.min_n} graded
        picks. They’re in the headline number above — they just can’t carry a
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
  // The record re-priced AND re-sized by the model we have now: the
  // selection haircut applied to the claim, then the price ladder on the
  // stake. The official record stays the receipts of bets as they were
  // made — this answers "what WOULD it read" without editing a row.
  if (!rs) return "";
  const r = sport ? (rs.by_sport || {})[sport] : rs.overall;
  if (!r) return "";
  // NOT `!r.settled`. A restatement where the corrected probabilities
  // clear nothing is the loudest result this block can produce — today's
  // model would have refused the whole book — and returning "" made it
  // render as an absence. It has its own copy now.
  if (!r.settled) {
    return !r.excluded ? "" : `
      <div class="section-title">At today’s model
        <span class="sub">— the same graded picks, re-priced and re-staked
        by the board as it now runs.</span></div>
      <div class="card" style="border-left:3px solid var(--brand)">
        <p style="margin:0;font-size:var(--fs-md)">
          <b style="color:var(--brand)">It refuses all
          ${r.excluded.toLocaleString()} of them.</b> Corrected by the
          selection haircut, not one of these claims still clears
          break-even at the price it was taken at — so today’s model would
          not have placed the bet.</p>
        <p style="margin:8px 0 0;font-size:var(--fs-sm);color:var(--text-mute)">
          That is a statement about the CLAIMS, not the results. It does not
          mean these were bad nights; it means the probabilities behind them
          were about nine points too high, which is the gap the haircut was
          measured on. The record above is unchanged and stays unchanged —
          those bets were made at those stakes and the money moved.</p>
      </div>`;
  }
  const roi = (r.roi ?? 0) * 100;
  const tone = (v) => v >= 0 ? "var(--good)" : "var(--bad)";
  return `
    <div class="section-title">At today’s model
      <span class="sub">— the same graded picks, re-priced by the selection
      haircut and re-staked by the price ladder. Picks the corrected
      probability no longer clears are dropped, not re-sized. The official
      record above is the receipts as bet; this is what those nights would
      have returned under the board as it now runs.</span></div>
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
      today’s Kelly would not have made those bets at all.</p>` : ""}`;
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
      note on what the learning ladder did — written from the arithmetic’s
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
      on every settle pass, on this sport’s own settled bets only, and adopt
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
  // A dial resting at ±1.0 is NOT "the search range was too small". r
  // interpolates toward a named endpoint curve, so +1.0 is that curve
  // exactly; one step past it puts a negative weight on vs_opp, which
  // would mean subtracting a player's own history from his projection.
  // The grid cannot widen. What the edge means depends entirely on
  // whether the dial was adopted, so the row has to say which:
  //   adopted  → the model wants a hotter recipe than this family holds,
  //              and the anchor itself is what to revisit. Red.
  //   not      → nothing was applied, and `plateau` says how many dial
  //              settings tied the winner. Most of them tying means the
  //              surface is flat and the argmin landed on an edge because
  //              argmins land somewhere. That is not a defect, and
  //              painting it red sent people looking for a bug.
  const dialTone = (w) => w.adopted
    ? (w.at_boundary ? "var(--bad)" : "var(--warn)") : "var(--good)";
  const dialNote = (w) => {
    if (!w.at_boundary || !w.grid_n) return "";
    const flat = w.plateau >= Math.max(2, w.grid_n * 0.5);
    const txt = w.adopted
      ? `at the family’s edge — the anchor curve is the thing to revisit, not the grid`
      : flat
        ? `${w.plateau}/${w.grid_n} dial settings tied — flat surface, the edge is where the search landed`
        : `${w.plateau}/${w.grid_n} tied — a real slope, but under the adoption bar`;
    return `<span style="opacity:.55;font-size:.92em">${escapeHtml(txt)}</span>`;
  };
  const weightRows = weights.map((w) => `
    <div style="display:flex;gap:12px;align-items:baseline;padding:7px 14px;
        border-bottom:1px solid rgba(255,255,255,.05);font-size:.88em;flex-wrap:wrap">
      <span class="chip">${escapeHtml((w.sport || "").toUpperCase())}</span>
      <span style="flex:1;min-width:120px">${escapeHtml(w.market || "")}</span>
      <span style="font-variant-numeric:tabular-nums" title="The recency dial: 0 is the hand-tuned spec curve, positive leans on recent form, negative on the long run. ±1.0 is the end of the family, not the end of a search range. Moves only when the record beats the spec by a real margin.">dial ${(w.r ?? 0) >= 0 ? "+" : ""}${(w.r ?? 0).toFixed(1)}</span>
      <span style="color:${dialTone(w)}">${escapeHtml(w.reading || "")}</span>
      ${dialNote(w)}
      <span style="opacity:.5;font-variant-numeric:tabular-nums">n=${(w.samples ?? 0).toLocaleString()}</span>
      ${w.brier_default != null && w.brier_fitted != null
        ? `<span style="opacity:.6;font-variant-numeric:tabular-nums" title="Walk-forward Brier, spec curve → best curve on the grid. Lower is better; the dial is applied only when it wins by 0.0005 or more. Shown whether or not it was adopted — the margin IS the reason for the verdict.">${w.brier_default.toFixed(4)} → ${w.brier_fitted.toFixed(4)}</span>` : ""}
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
      title="Walk-forward ${escapeHtml(label)}, memory off → on: ${escapeHtml(verdict)} by ${Math.abs(gain).toFixed(5)}. Lower is better. Each bet’s correction knew only that player’s EARLIER games, so this is out-of-sample at every row. The memory switches on only when it wins by at least 0.0005.">${before.toFixed(4)} → ${after.toFixed(4)}</span>`;
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
      <span class="sub">— a market is fitted once it clears 200 settled bets, and
      REFITTED from every settled bet after that. This is the site’s AI lane:
      arithmetic on outcomes, reproducible and auditable, which is exactly why a
      chatbot never sets a probability here.</span></div>
    <div class="stats">
      <!-- The history of this caption is worth keeping, because it tracked a
           real defect for as long as the defect existed.

           It first said "runs itself after every settle", which was untrue.
           It was corrected to say the stamp only moves on a market’s FIRST
           fit — accurate, because the fitter skipped any market it had
           already corrected: those bets were priced UNDER the correction and
           refitting on them naively replaces a working number with ~1.0.

           That skip is now gone. A refit un-corrects each row by whatever was
           live when it was logged, so the whole journal is fittable and the
           stamp moves whenever any market learns something. The freeze was
           never the goal; it was the price of not having the inverse wired
           up. -->
      <div class="tile"><div class="k">Last fit</div><div class="v" style="font-size:var(--fs-lg)">${escapeHtml(lastRefit)}</div>
        <div class="tile-sub">every market refits from the whole journal —
          each bet’s claim is un-corrected by whatever was live when it was
          placed, so a correction can deepen instead of freezing</div></div>
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
      are in every night’s sweep, and a clean sheet here is the sweep’s
      verdict, not its absence.</p>` : (lp.tested ?? 0) > 0 ? `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      Scanned ${lp.tested} slice${lp.tested === 1 ? "" : "s"} of
      ${(lp.n_records ?? 0).toLocaleString()} graded bets — nothing survives
      false-discovery control yet. Patterns that look real on small samples
      usually aren’t, and a bar that bends to make the page interesting
      stops meaning anything. The bar stays.</p>` : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      Not enough graded bets in any one slice yet — a slice is only tested
      at ${lp.min_n ?? 40}+ settled picks. Every night’s grades feed this.</p>`;
  return `
    <div class="section-title">Learning from losses
      <span class="sub">— the miner slices every graded bet by side, price band,
      stated probability, horizon and book, hunting pockets where the model’s
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
      slice is judged on whether the model’s own stated probabilities missed
      reality (said 64%, hit 51%) — not on win rate, which would flag every
      honest longshot bucket. Second, every slice tested enters a
      Benjamini–Hochberg false-discovery correction, and only survivors are
      findings — the flagged set is expected to be at most
      ${Math.round(((lp.alpha ?? 0.05) * 100))}% luck. A pattern that clears
      both bars closes its slice automatically; the pick engines refuse
      anything that lands in it, and the veto’s reason names this page.</p>`)}`;
}

/* PREREGISTERED TESTS — the terms written down before the data.
   Ethan, 2026-08-13: "yeah do that, wire it into the lab."

   It sits beside the hypothesis lab and reads deliberately unlike it. The
   lab reports what a search FOUND; this reports what we said we would
   look for, and how far along it is. Those are different claims and the
   page must not let them look like the same one — a running total that
   reads like a result is exactly what preregistration is for. So a test
   still collecting shows PROGRESS and no number, and only a decided test
   shows a verdict. */
function recPrereg(pr) {
  const tests = (pr && pr.tests) || [];
  if (!tests.length) return "";
  const row = (t) => {
    if (t.status === "void") {
      return `<div class="pr-row"><span class="pr-claim">${escapeHtml(t.claim)}</span>
        <span class="chip down">void — terms changed</span></div>`;
    }
    if (t.status === "collecting") {
      const pct = Math.min(100, Math.round((t.n / t.min_n) * 100));
      return `<div class="pr-row">
        <span class="pr-claim">${escapeHtml(t.claim)}
          <span class="sub">registered ${escapeHtml(t.registered)} · deciding at
          ${t.min_n} bets, and not before</span></span>
        <span class="pr-prog"><i style="width:${pct}%"></i></span>
        <span class="pr-n">${t.n} / ${t.min_n}</span></div>`;
    }
    const tone = t.supported ? "down" : "";
    return `<div class="pr-row">
      <span class="pr-claim">${escapeHtml(t.claim)}
        <span class="sub">${escapeHtml(t.reading || "")}</span></span>
      <span class="chip ${tone}">${t.supported ? "supported" : "not supported"}</span></div>`;
  };
  return `<div class="section-title">Preregistered
      <span class="sub">— written down before the data arrived, and decided
      once at a sample size named in advance. A test still collecting shows
      progress, never a running result.</span></div>
    <div class="card">${tests.map(row).join("")}</div>`;
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
      <code>python3 hypotheses.py</code> run reads every sport’s record —
      including this one — and proposes wherever the evidence points.</p>` : `
    <p style="padding:12px 14px;margin:0;font-size:.87em;color:var(--text-mute)">
      The lab is idle. Add <code>ANTHROPIC_API_KEY</code> to secrets.local and
      run <code>python3 hypotheses.py</code> — the model reads the record’s own
      summary and proposes slice intersections the miner doesn’t test. Every
      proposal faces the same statistics as everything else on this page;
      nothing an AI writes here can ever set a probability.</p>`;
  return `
    <div class="section-title">The hypothesis lab
      <span class="sub">— the one safe job for an AI that writes prose: propose.
      A language model reads the record’s summary and suggests loss patterns
      built strictly from the miner’s own tested dimensions — the intersections
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
      worth testing. So proposals are constrained to the miner’s own menu of
      dimensions, convicted or acquitted by the same statistics that govern
      every number on this page, and re-tried nightly as new bets settle —
      a confirmation that was luck decays on its own. The model saw the record
      before proposing, which is exactly why first confirmations are treated
      as provisional and re-earned forever after.</p>`)}`;
}

/* The selection haircut — engine/selectionfit.py, rendered.

   The chart above this one grades the model's probability SURFACE, over
   every prop it can price. This grades the subset we actually bet, which
   is a different population and a much less flattering one: picking the
   top edges out of a noisy estimator picks, preferentially, the spots
   where the estimate is too high. A model can sit on the diagonal up
   there and still be nine points hot down here.

   Ethan asked for the lower number to be the one on display. So this
   block leads with the two figures side by side — what we claimed, what
   landed — and then says plainly what is being subtracted from every
   probability on the board as a result. */
function recSelectionHaircut(sh, scope) {
  if (!sh) return "";
  const pooled = sh.pooled || {};
  const sports = sh.sports || {};
  // Sport pages show their own row (and the pooled one they may be
  // borrowing); the all-sports page shows everything.
  const keys = Object.keys(sports).filter((s) => !scope || s === scope);
  if (!pooled.n && !keys.length) {
    return `<div class="section-title minor">The selection haircut
        <span class="sub">— not measured yet.</span></div>
      <div class="card"><p style="margin:0;font-size:var(--fs-sm);color:var(--text-mute)">
        Nothing has been fitted. The haircut is measured from settled bets at
        settle time; until a sport reaches ${sh.min_settled || 100} of them the
        board runs on the model’s own numbers.</p></div>`;
  }
  const pct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
  // Deliberately NOT .rl-row: that grid has six fixed tracks sized for the
  // receipts table, and dropping three children into it crushes the middle
  // one to a 90px column. This is its own flex row.
  const row = (name, e, using) => {
    const live = !!e.applied;
    const gap = e.gap == null ? null : e.gap * 100;
    return `<div style="display:flex;gap:12px;align-items:flex-start;
                padding:9px 0;border-bottom:var(--hairline) solid var(--border-soft)">
      <span style="min-width:52px;color:var(--text-mute);font-size:var(--fs-sm);
            text-transform:uppercase;letter-spacing:.04em;padding-top:1px">${
        escapeHtml(name)}</span>
      <span style="flex:1;min-width:0">
        <span style="font-variant-numeric:tabular-nums">claimed
          <strong>${pct(e.claimed)}</strong> · landed
          <strong class="${gap == null ? "" : toneOf(gap)}">${pct(e.landed)}</strong>
          ${gap == null ? "" : `<span class="${toneOf(gap)}">(${gap >= 0 ? "+" : ""}${
            gap.toFixed(1)} pts, ±${((e.se || 0) * 100).toFixed(1)})</span>`}
          · ${e.n || 0} settled</span>
        <div style="font-size:var(--fs-sm);color:var(--text-mute);margin-top:3px">
          ${escapeHtml(e.reason || "")}</div></span>
      <span class="chip" style="flex-shrink:0${live || using === "pooled"
        ? ";color:var(--brand)" : ""}">${
        live ? `${e.shift.toFixed(3)} log-odds`
             : using === "pooled" ? "on the pooled cut" : "not applied"}</span></div>`;
  };
  const rows = keys.map((s) => row(s, sports[s], (sh.using || {})[s])).join("");
  // The sentence that answers "so what does it actually do to a bet?".
  // Break-even at −110 is 52.38%, so a claim that used to clear the bar
  // by two points can stop clearing it at all — which is the intended
  // consequence, not a side effect, and the copy says so.
  const live = keys.filter((s) => sports[s].applied).length || pooled.applied;
  const ex = (pooled.applied ? pooled : (sports[keys.find(
    (s) => sports[s].applied)] || {}));
  const effect = !live ? "" : `
    <p style="margin:10px 0 0;font-size:var(--fs-sm);color:var(--text-body)">
      Every probability on the board is moved by this before anything is
      computed from it. A pick the model called <strong>55.0%</strong> now
      ships as <strong>${pct(ex.example_55)}</strong> — under the 52.4%
      a −110 price needs — so its edge, its EV and its stake all fall,
      and picks that only just cleared the bar stop clearing it. That is
      the correction working, not the board breaking.</p>`;
  // The held-out test is the reason to believe any of this, so it gets its
  // own sentence rather than living inside a row's fine print.
  const h = (ex || {}).holdout || {};
  const heldOut = !h.ran ? "" : `
    <p style="margin:8px 0 0;font-size:var(--fs-sm);color:var(--text-mute)">
      Validated out of sample before it was allowed to price anything: fitted on
      the first ${h.train_n} settled bets, then scored on the ${h.test_n} it had
      never seen. On those, the gap between claim and result went
      ${(h.gap_before * 100).toFixed(1)} → <strong>${(h.gap_after * 100).toFixed(1)}</strong>
      points and the Brier score ${h.brier_before.toFixed(4)} →
      <strong>${h.brier_after.toFixed(4)}</strong>. A correction that only
      improved the data it was fitted on would be refused here.</p>`;
  const borrowed = keys.filter((s) => (sh.using || {})[s] === "pooled");
  const borrowNote = !borrowed.length ? "" : `
    <p style="margin:8px 0 0;font-size:var(--fs-sm);color:var(--text-mute)">
      ${borrowed.map((s) => escapeHtml(s.toUpperCase())).join(", ")} ${
      borrowed.length > 1 ? "are" : "is"}
      still under the ${sh.min_settled || 100}-bet floor and ${
      borrowed.length > 1 ? "are" : "is"} borrowing the pooled number. What is
      being corrected is a property of how we SELECT — taking the top edges out
      of a noisy estimate — and that is shared by every sport on the board.</p>`;
  return `<div class="section-title">The selection haircut
      <span class="sub">— the chart above grades the model’s whole surface.
      This grades the bets we actually made.</span></div>
    <div class="card">
      <p style="margin:0 0 10px;font-size:var(--fs-sm);color:var(--text-mute)">
        Selecting the biggest edges selects for our own overestimates, so the
        picks run hotter than the surface they came from. Measured on settled
        bets, pooled across markets, per sport — one number, shrunk by its own
        standard error and never applied upward.</p>
      ${pooled.n && !scope ? row("all", pooled, "own") : ""}${rows}
      ${effect}${heldOut}${borrowNote}
      <p style="margin:10px 0 0;font-size:var(--fs-sm);color:var(--text-faint)">
        Last fitted ${escapeHtml(sh.fitted_at || "—")} · refits every settle
        pass, un-doing its own prior correction first so it cannot compound.</p>
    </div>`;
}

function recCalibrationSection(cal, era) {
  if (!cal || !cal.n || !(cal.buckets || []).length) return "";
  const rows = calBucketRows(cal.buckets);
  const brier = calScoreBlock(cal);
  // The hand-drawn diagram ships as the fallback; mountEChartsAnalytics
  // upgrades the wrapper to the interactive version (see visuals.js).
  const relWrap = (bks, svg) => !svg ? "" : `<div class="gloss-chart"
    style="min-height:240px" data-echart-reliability="${escapeAttr(JSON.stringify({
      buckets: (bks || []).filter((b) => b.n > 0).map((b) => ({
        predicted: b.predicted, actual: b.actual, n: b.n,
        ci: b.ci, in_band: b.in_band })),
    }))}">${svg}</div>`;
  const diagram = relWrap(cal.buckets, reliabilityDiagram(cal.buckets));
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
      these misses back into the model’s tempering.</p>`;
  const eraBlock = eraN >= 50 ? `
    <div class="section-title minor">Current model only
      <span class="sub">— the same test, restricted to picks graded since the
      ${escapeHtml((era || {}).since || "")} re-tune (n=${eraN}).</span></div>
    <div class="card" style="padding:0">${calBucketRows(era.buckets)}
      <div style="padding:14px 14px 4px;border-top:1px solid rgba(255,255,255,.06)">
        ${relWrap(era.buckets, reliabilityDiagram(era.buckets))}</div>${calScoreBlock(era)}</div>` : "";
  return `<div class="section-title">Calibration — did "60%" mean 60%?
      <span class="sub">— every settled pick, bucketed by the model’s claimed probability.</span></div>
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
        What this score can’t see — and why</summary>
      <ul style="margin:8px 0 0;padding-left:18px;font-size:.85em;color:var(--text-body)">
        ${h.blind_spots.map((s) => `<li><strong>${escapeHtml(s.signal)}</strong>
          — ${escapeHtml(s.why)}</li>`).join("")}
      </ul>
      <p style="font-size:.83em;opacity:.6;margin:8px 0 0">Books watch all of
        these. We score the four we can measure honestly and name the rest
        rather than implying a completeness this doesn’t have.</p>
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
    ${recDisclosure("Why these are quarantined", `Scalpy MMA’s picks journal at
      their real prices (one-fifth Kelly stakes) and settle automatically from ESPN’s
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
      `<p class="loading" style="padding:12px">Grades after each card’s fights are official.</p>`}</div>`;
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
    <div class="section-title minor">Looser-gates sampler — measurement in progress
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
      `<p class="loading" style="padding:12px">Nothing settled yet — accrues from tonight’s near-misses.</p>`}</div>`;
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
  parts.push(btn("intel", "Prediction Market", null));
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

/* ============================================================
   SUB-TABS — one page, several rooms
   ============================================================
   Ethan, 2026-08-08: "everything feels cluttered and kinda just thrown
   around in place when I say to add something."

   MEASURED, because "cluttered" is a feeling and a count is a fact: 81
   section titles across 47 render functions, and the Record page alone
   composes TWENTY-TWO of them into a single vertical scroll. Every one of
   them renders at identical visual weight, so "Running P&L" and
   "Team-form sampler — measurement in progress" look equally important.
   Nothing was badly built; things were appended, one at a time, to
   whichever page was nearest.

   This is the grouping that was always latent. It is deliberately NOT a
   set of new top-level tabs — the site already carries eleven of those
   plus a sport switcher, and adding more is the thing that made it hard
   to navigate in the first place.

   THREE RULES THAT MAKE IT SAFE:

   1. A TAB WITH NOTHING BEHIND IT IS NEVER DRAWN. The Record page hides
      most of its panels when scoped to one sport, so a fixed tab bar
      would offer five rooms and open two empty ones. Groups are built as
      strings first and only the ones with content become tabs.
   2. NOTHING IS UNREACHABLE. If every group but one is empty the bar
      disappears and the content renders plain — the page behaves exactly
      as it did before sub-tabs existed.
   3. THE CHOICE IS REMEMBERED, per view, for the session. Landing back on
      Receipts every time you glance at a sport is the kind of small tax
      that makes people stop opening a page. */

//: Where you were, per view. Not persisted — a new session should open on
//: the first tab, which is the one that answers "how am I doing".
const _subtab = {};

/**
 * Build a sub-tabbed view.
 * `groups` is [[id, label, hint, html], ...] in display order.
 * Returns the whole block: tab bar plus panels, ready to assign.
 */
function subtabbedHTML(view, groups) {
  const live = groups.filter((g) => (g[3] || "").trim());
  if (live.length < 2) return live.map((g) => g[3]).join("");
  const want = _subtab[view];
  const active = live.some((g) => g[0] === want) ? want : live[0][0];
  const tabs = live.map((g) => `
    <button class="subnav-btn${g[0] === active ? " active" : ""}" role="tab"
            type="button" data-subtab="${escapeAttr(g[0])}"
            aria-selected="${g[0] === active}"
            tabindex="${g[0] === active ? "0" : "-1"}"
            title="${escapeAttr(g[2] || "")}">${escapeHtml(g[1])}</button>`).join("");
  const hint = (live.find((g) => g[0] === active) || [])[2] || "";
  const panels = live.map((g) => `
    <div class="subgroup" data-subgroup="${escapeAttr(g[0])}" role="tabpanel"
         ${g[0] === active ? "" : "hidden"}>${g[3]}</div>`).join("");
  return `<div class="subnav-wrap" data-subnav="${escapeAttr(view)}">
    <div class="subnav" role="tablist" aria-label="Sections">${tabs}</div>
    <p class="subnav-hint">${escapeHtml(hint)}</p>
  </div>${panels}`;
}

/* ------------------------------------------------------------------
   THE SAME ROOMS, FOR A PAGE BUILT OUT OF STANDING CONTAINERS

   `subtabbedHTML` takes strings, which works for Record, Players and
   Fantasy because those pages compose their whole body in JavaScript.
   Recommended does not. Its fifteen blocks are declared in index.html and
   filled in place by fifteen separate render functions that each find
   their element by id — `renderGameBets` writes to `#gamebets`,
   `renderRestWatch` to `#rest-watch`, and so on.

   So this variant MOVES the existing nodes into panels instead of
   rebuilding them. Every id survives, every renderer keeps working, and
   nothing about what gets drawn changes — only where it sits. Rebuilding
   Recommended as strings to reuse the other function would have meant
   rewriting fifteen renderers to hit one page, which is a large change
   with nothing to show for it.

   WHY EMPTINESS IS RE-JUDGED ON EVERY CALL. The Record page knows what
   it has before it renders; this page does not. `#gamebets` is empty
   until the slate arrives, `#preseason-board` fills only in August, and
   switching leagues empties half the page and fills the other half. A
   room decided once at startup would offer a Game bets tab on a night
   with no game bets, which is rule 1 of the sub-tab contract broken by
   the only page that changes underneath it.

   AND WHY IT IS JUDGED BY CONTENT, NOT BY HEIGHT. Everything inside an
   inactive panel measures zero — `hidden` is display:none — so an
   offsetHeight test would call every room but the open one empty and
   collapse the bar to a single tab. Content is the only property that
   survives being off screen. */
function subtabbedDOM(view, host, groups) {
  let wrap = host.querySelector(":scope > .subnav-wrap");
  if (!wrap) {
    // First pass: build the bar and the panels, then move each block in.
    // Insertion point is where the first grouped element already sits, so
    // anything above it (a masthead note, say) stays above.
    const first = document.getElementById(groups[0][3][0]);
    wrap = document.createElement("div");
    wrap.className = "subnav-wrap";
    wrap.dataset.subnav = view;
    wrap.innerHTML = `<div class="subnav" role="tablist"
        aria-label="Sections"></div><p class="subnav-hint"></p>`;
    host.insertBefore(wrap, first);
    groups.forEach((g) => {
      const panel = document.createElement("div");
      panel.className = "subgroup";
      panel.dataset.subgroup = g[0];
      panel.setAttribute("role", "tabpanel");
      host.insertBefore(panel, null);
      g[3].forEach((id) => {
        const el = document.getElementById(id);
        if (el) panel.appendChild(el);
      });
    });
  }

  const filled = (el) => {
    if (!el) return false;
    // An element hidden by its own renderer is not content. `#empty-slate`
    // and `#gamebets-title` both sit in the markup permanently and are
    // switched on by display, so reading textContent alone would count
    // the "Game bets" heading on a night with no game bets.
    if (el.style && el.style.display === "none") return false;
    return el.children.length > 0 || (el.textContent || "").trim() !== "";
  };
  const live = groups.filter((g) => g[3].some((id) =>
    filled(document.getElementById(id))));

  const bar = wrap.querySelector(".subnav");
  // Rule 2: one room means no bar. The page then behaves exactly as it
  // did before sub-tabs existed, which is what makes this safe on a slate
  // that turns out to have only picks and nothing else.
  wrap.hidden = live.length < 2;
  const want = _subtab[view];
  const active = live.some((g) => g[0] === want) ? want : (live[0] || [])[0];
  bar.innerHTML = live.map((g) => `
    <button class="subnav-btn${g[0] === active ? " active" : ""}" role="tab"
            type="button" data-subtab="${escapeAttr(g[0])}"
            aria-selected="${g[0] === active}"
            tabindex="${g[0] === active ? "0" : "-1"}"
            title="${escapeAttr(g[2] || "")}">${escapeHtml(g[1])}</button>`)
    .join("");
  const hintEl = wrap.querySelector(".subnav-hint");
  hintEl.textContent = (live.find((g) => g[0] === active) || [])[2] || "";
  host.querySelectorAll(":scope > .subgroup").forEach((p) => {
    const on = live.some((g) => g[0] === p.dataset.subgroup);
    // An empty room's panel is hidden, never removed: its elements are
    // where the renderers write, and a renderer whose target has been
    // deleted fails silently for the rest of the session.
    p.hidden = !on || (live.length > 1 && p.dataset.subgroup !== active);
  });
  bindSubtabs(host);
}

/* Click and keyboard for whatever sub-tab bar is inside `host`.
   Arrow keys move between tabs because this is a real tablist and a
   keyboard user should not have to Tab through five buttons to reach the
   sixth. */
/* Say what the page you are on actually shows, in the words already
   written for the phone menu. Called from the view switch AND at startup:
   the first view is active in the markup and never goes through the
   switch, so a hint set only there is blank on the page people land on. */
function syncNavHint(view) {
  const el = document.getElementById("nav-hint");
  if (!el) return;
  const btn = document.querySelector(`.nav-btn[data-view="${view}"]`)
    || document.querySelector(".nav-btn.active");
  el.textContent = (btn && btn.dataset.hint) || "";
}

/* Reveal an element a sub-tab may be hiding, and hand it back.

   IN-PAGE ANCHORS STOPPED WORKING THE DAY SUB-TABS LANDED, and nothing
   said so. `subtabbedDOM` re-parents this view into panels and hides every
   panel but the active one with `display:none`; a native `href="#id"` jump
   into one of those finds a target with no box, scrolls nowhere, and looks
   for all the world like a dead button. That is exactly what the
   "Preseason is what is being played now →" pointer had become: it moved
   the address bar and nothing else, on the one page whose whole job is
   saying where the football is.

   The room is opened by CLICKING ITS REAL TAB rather than flipping
   `hidden` here. `bindSubtabs`'s handler also updates the bar highlight,
   aria-selected, the roving tabindex, the hint line and the remembered
   room — set `hidden` directly and the page shows one room while the bar
   claims another, which is a worse bug than the one being fixed. */
function revealAnchor(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const panel = el.closest(".subgroup");
  if (panel && panel.hidden) {
    const host = panel.parentElement;
    const room = panel.dataset.subgroup || "";
    const btn = host && [...host.querySelectorAll(".subnav-btn")]
      .find((b) => b.dataset.subtab === room);
    if (btn) btn.click();
    else panel.hidden = false;      // no bar (single room): just show it
  }
  return el;
}

function bindSubtabs(host) {
  const wrap = host.querySelector(".subnav-wrap");
  if (!wrap) return;
  const view = wrap.dataset.subnav;
  const btns = [...wrap.querySelectorAll(".subnav-btn")];
  const show = (id) => {
    _subtab[view] = id;
    btns.forEach((b) => {
      const on = b.dataset.subtab === id;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
      if (on) {
        const h = wrap.querySelector(".subnav-hint");
        if (h) h.textContent = b.title || "";
      }
    });
    host.querySelectorAll(".subgroup").forEach((p) => {
      p.hidden = p.dataset.subgroup !== id;
    });
  };
  btns.forEach((b, i) => {
    b.addEventListener("click", () => show(b.dataset.subtab));
    b.addEventListener("keydown", (e) => {
      const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      e.preventDefault();
      const next = btns[(i + step + btns.length) % btns.length];
      next.focus();
      show(next.dataset.subtab);
    });
  });
}

/* Recommended's rooms. MEASURED IN CHROMIUM, not eyeballed, because that
   is the standard the rest of this work was held to: the NFL board runs
   8.1 screens on a 1440x900 desktop, and two blocks are 4.8 of them —
   `#gamebets` at 3.23 screens and `#rest-watch` at 1.50. Everything a
   person opens this page to see was below both of them.

   THE VENUE BLOCK STAYS IN THE DEFAULT ROOM. Ethan put the ballparks
   first on purpose — park, roof and wind are what the picks are read
   against — so grouping is not licence to reorder. `games-title` and
   `games` open room one, exactly where they were.

   The sliders travel with the cards they filter. Leaving `#rec-controls`
   behind would put a Min-edge dial in a room containing no prop. */
const REC_ROOMS = [
  ["board", "Tonight’s board",
   "the venues, the designated picks, and every prop that cleared the bar",
   // games-head/games-outer are the strip's wrappers (controls +
   // arrows); moving the bare title/scroller out of them orphaned the
   // controls at the top of the page.
   // Ethan's order, 2026-08-11, from his phone: "top bets, the
   // stadiums, then roi." The room places blocks in THIS order — the
   // list, not the DOM, is what a reader sees.
   ["probation-note", "talent-note", "top-picks", "parlay-mode",
    "games-head", "games-outer", "stats", "home-perf",
    "best-bets", "empty-slate", "rec-controls", "cards"]],
  ["gamebets", "Game bets",
   "moneyline, spread and total edges from the team model",
   ["gamebets-title", "gamebets"]],
  ["watch", "Watchlists",
   "context that shades a pick without being one: rest, incentives, form, injuries",
   ["preseason-board", "team-form", "incentive-watch", "rest-watch",
    "injury-watch"]],
];

function groupRecommended() {
  const host = document.getElementById("view-recommended");
  if (host) subtabbedDOM("recommended", host, REC_ROOMS);
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
  // The one-line version carries the same claim. Filled from the same
  // object, so the two can never disagree — the full masthead and the
  // brief one are two renderings of one fact, not two facts.
  const brief = document.getElementById("mb-rec");
  if (brief) {
    brief.textContent =
      `${roi >= 0 ? "+" : ""}${(roi * 100).toFixed(1)}%  ·  ` +
      `${o.wins || 0}-${o.losses || 0}${o.pushes ? `-${o.pushes}` : ""}`;
    brief.classList.toggle("neg", neg);
  }
}

/* The masthead runs its full pitch once.
 *
 * It is ~790px on a phone — mark, wordmark, tagline, running ROI, record,
 * the journaling promise, the status chips — doing real work for a
 * first-time reader and none at all for the fifth visit, ahead of the
 * picks, every load. So it shows in full, marks itself seen, and collapses
 * to one line from then on. The line expands the whole block back, so a
 * reader who wants the pitch again can have it; nothing is removed.
 *
 * The flag is written on the FIRST load rather than on leaving, because a
 * reader who bounces has still seen it, and because there is no reliable
 * moment on the way out to write anything. */
function initMasthead() {
  const btn = document.getElementById("masthead-brief");
  if (!btn) return;
  try {
    if (!localStorage.getItem("qb-seen-intro"))
      localStorage.setItem("qb-seen-intro", String(Date.now()));
  } catch (e) {}
  /* A toggle has to toggle. The expanded state keeps this same button —
     collapsed to a quiet "Hide" under the full block — rather than
     removing it, because a control that vanishes on activation strands
     the reader in the state they just left AND throws away keyboard
     focus mid-interaction. */
  btn.addEventListener("click", () => {
    const open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", open ? "false" : "true");
    btn.title = open ? "Show the full masthead" : "Hide the full masthead";
  });
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
          + "model’s probabilities carry information; negative = you would "
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
  /* On a MIXED basis the headline used to be the blended ROI, and that was
     the single most misleading number on the site.

     Measured on the real board: total_bases blended to +2.7% — and its own
     segment table underneath read 25,145 bets vs a naive baseline against
     277 vs real book lines. The blend is 99% naive by bet count, so the
     green +2.7% WAS the naive number, sitting over a subtitle that said
     "8,485 of 293,479 on real closes" and coloured as though it were an
     edge over a market. Strikeouts did the same: +4.6% blended, -0.3% on
     the 102 bets that met a real price.

     The book-priced segment is the only market-relative figure there is,
     so it leads. If it is too thin to mean anything it says so and stays
     grey, which is the honest reading of 277 bets — rather than borrowing
     confidence from 25,145 bets against a trailing average. */
  const bookSeg = (m.segments || {}).book;
  const mixed = m.basis === "mixed";
  const headline = mixed && bookSeg ? bookSeg : { roi: m.roi, n_bets: m.n_bets };
  const thin = (headline.n_bets || 0) < LAB_ROI_MIN_BETS;
  const roiSub = mixed
    ? (bookSeg
        ? `${bookSeg.n_bets.toLocaleString()} bets met a real close`
          + (thin ? ` — under ${LAB_ROI_MIN_BETS}, noise not a result`
                  : " — market-relative")
        : "no bet met a real close — nothing here is market-relative")
    : thin
      ? `only ${m.n_bets} bets — under ${LAB_ROI_MIN_BETS} this is noise, not a result`
      : m.basis === "book"
        ? "priced against real harvested closes — market-relative"
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
      ${recTile(mixed ? "ROI vs real closes" : "Backtest ROI",
                headline.n_bets
                  ? `${headline.roi >= 0 ? "+" : ""}${(headline.roi * 100).toFixed(1)}%`
                  : "—",
                m.n_bets ? roiSub : "no bets cleared the gates",
                { tone: (naive || thin) ? "" : toneOf(headline.roi) })}
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
  const gapBlock = gaps ? `<div class="section-title minor">Not replayed yet
      <span class="sub">— what each of these needs before it can appear above</span></div>
    <table class="agate"><thead><tr><th>Sport</th><th>Player props</th>
      <th>Game lines</th></tr></thead><tbody>${gaps}</tbody></table>` : "";
  host.innerHTML = `
    ${recDisclosure("What this page is, and what it isn’t", `The Book grades the picks
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

/* The edge test, rendered as a verdict rather than three AUCs.

   Three numbers between 0.4 and 0.6 read as "fine" to anybody who is not
   already thinking about rank statistics, which is everybody at 1am. The
   verdict comes from `edgehistory.measure`, computed once server-side, so
   this panel and the nightly prose and the LLM's evidence pack cannot each
   invent their own reading of the same numbers. */
const EDGE_VERDICTS = {
  edge_is_noise: {
    tone: "neg", label: "No measurable edge",
    say: "Bets the model called better did not win more often than bets it "
       + "called worse. Its ranking and the market’s are the same ranking.",
    then: "Every gate, threshold and stake rule is a function of that "
        + "number, so tuning them cannot help. The model needs information "
        + "the market lacks, not better use of what it already has.",
  },
  edge_inverted: {
    tone: "neg", label: "Edge points backwards",
    say: "The claimed edge sorts winners BELOW losers.",
    then: "Worse than no signal — the gates are selecting against us.",
  },
  edge_predicts: {
    tone: "pos", label: "The edge signal is real",
    say: "Bets the model called better did win more often.",
    then: "The signal carries information, so losses are coming from price, "
        + "timing or sizing rather than from the pick itself.",
  },
};

function recEdgePanel(e, trend) {
  const v = EDGE_VERDICTS[e.verdict] || EDGE_VERDICTS.edge_is_noise;
  const ci = (lo, hi) => (lo == null || hi == null) ? ""
    : `[${lo.toFixed(3)}, ${hi.toFixed(3)}]`;
  const row = (name, val, lo, hi, lead) => `
    <tr${lead ? ' class="lead-row"' : ""}><td>${escapeHtml(name)}</td>
    <td class="num">${val == null ? "—" : val.toFixed(3)}</td>
    <td class="num mini">${ci(lo, hi)}</td></tr>`;
  /* The series, only once it can show a change. One point is not a trend
     and drawing it as one invites reading noise as movement. */
  const runs = (trend || []).filter((r) => r.auc_edge != null);
  const spark = runs.length < 3 ? "" : `
    <p class="mini" style="margin-top:8px">Claimed-edge AUC over the last
    ${runs.length} runs: ${runs.map((r) => r.auc_edge.toFixed(3)).join(" \u2192 ")}
    ${runs.length > 1 && Math.abs(runs[runs.length - 1].auc_edge - runs[0].auc_edge) < 0.02
      ? " — flat." : ""}</p>`;
  return `
  <div class="rec-edge tone-${v.tone}">
    <div class="section-title">Is there an edge at all?
      <span class="sub">— ${e.n} settled bets</span></div>
    <div class="rec-edge-verdict"><strong>${escapeHtml(v.label)}.</strong>
      ${escapeHtml(v.say)}</div>
    <table class="agate rec-edge-tbl"><thead><tr>
      <th>ranked by</th><th class="num">AUC</th><th class="num">95% CI</th>
    </tr></thead><tbody>
      ${row("the model’s own number", e.auc_model, e.auc_model_lo, e.auc_model_hi)}
      ${row("the market’s price", e.auc_market, e.auc_market_lo, e.auc_market_hi)}
      ${row("our claimed edge", e.auc_edge, e.auc_edge_lo, e.auc_edge_hi, true)}
      ${row("model minus market", e.diff, e.diff_lo, e.diff_hi)}
    </tbody></table>
    <p class="mini">0.500 is a coin flip — the chance a random winner is
      ranked above a random loser. Rank-based, so the vig cannot distort it.
      ${escapeHtml(v.then)}</p>
    ${e.clv_n ? `<p class="mini">Closing-line value over ${e.clv_n} bets with a
      close: ${(e.clv_mean * 100).toFixed(2)}% ± ${((e.clv_se || 0) * 100).toFixed(2)}
      — a second, independent instrument.</p>` : ""}
    ${spark}
  </div>`;
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
      Check back after tonight’s games settle — this page becomes the honest
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
      + recPrereg(d.prereg) + recHypothesisLab(d.hypothesis_lab, scope);
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
  /* IS THERE AN EDGE AT ALL — rendered ABOVE the ROI, because it is the
     frame the ROI should be read through rather than a footnote to it.

     On 2026-08-09 the model's ranking of its own bets was measured
     against the market's ranking of the same bets: +0.004 AUC apart, and
     the claimed edge indistinguishable from a coin flip. A -28% ROI next
     to "the edge signal carries no information" is one story with a
     cause. The same ROI on its own invites a search for the bad week
     that explains it, and there isn't one.

     Scoped panels get nothing: the measurement is computed over the whole
     main book, and slicing it per sport would print a number that was
     never calculated. See docs/THE_INFORMATION_TEST.md. */
  const edgePanel = (scoped || !d.edge_now) ? "" : recEdgePanel(d.edge_now, d.edge_trend);
  // The page's lead — what happened, in units. Built as a string so it can
  // be handed to the first room rather than rendered above the tab bar,
  // which would leave the tabs floating in the middle of the page.
  const receipts = edgePanel + `
    <div class="stats rec-kpis">
      ${recTile("ROI", (o.roi >= 0 ? "+" : "") + (o.roi * 100).toFixed(1) + "%",
                `${o.net_units >= 0 ? "+" : ""}${o.net_units.toFixed(2)}u on ${(o.units_staked || 0).toFixed(1)}u staked`,
                { lead: true, tone: toneOf(o.roi) })}
      ${recTile("Avg CLV", o.avg_clv == null ? "—" : (o.avg_clv >= 0 ? "+" : "") + o.avg_clv.toFixed(2) + ' <span class="unit">pts</span>',
                o.avg_clv == null ? "accrues as daily closes are captured"
                  : `line movement on ${o.clv_n ?? 0} bet${o.clv_n === 1 ? "" : "s"} — 0.00 where the line cannot move`,
                { lead: true, tone: o.avg_clv == null ? "" : toneOf(o.avg_clv) })}
      ${/* The price tile, which is the ONLY CLV a fixed-line market has.
            A home-run prop is quoted OVER 0.5 and closes at 0.5, so the
            line tile beside this one reads 0.00 for two thirds of the
            book and says nothing — while the price moved all evening.
            Kept as its own tile rather than folded in: line points and
            probability points are different units, and averaging them
            together would be arithmetic on two different things. */ ""}
      ${o.avg_price_clv == null ? "" : recTile(
          "Price CLV",
          (o.avg_price_clv >= 0 ? "+" : "") + (o.avg_price_clv * 100).toFixed(2) + ' <span class="unit">pts</span>',
          `how the PRICE moved on ${o.price_clv_n ?? 0} over${o.price_clv_n === 1 ? "" : "s"} — the only CLV a 0.5 line has`,
          { lead: true, tone: toneOf(o.avg_price_clv) })}
      ${recTile("Record", `${o.wins}-${o.losses}-${o.pushes}`, `${o.open} open · ${o.settled} settled`)}
      ${/* The break-even is read off the prices this book ACTUALLY took,
            not assumed to be -110. A book that buys short prices needs far
            more than 52.4%: on the MLB journal the real bar is near 58%,
            so a 47% win rate read as five points short when it was ten.
            The flat number flattered the record on the one figure a
            bettor checks first. Falls back to the -110 wording only when
            no odds are available to average. */ ""}
      ${recTile("Win rate", (o.win_rate * 100).toFixed(1) + "%",
                o.breakeven == null
                  ? "break-even ≈ 52.4% at −110"
                  : `break-even ${(o.breakeven * 100).toFixed(1)}% at the prices taken`,
                { tone: o.breakeven != null && o.win_rate < o.breakeven ? "bad" : "" })}
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
      tile shows on each sport’s board: player props plus game bets (moneyline,
      spread &amp; totals, sharp-anchor and model alike) — at the real book price
      shown when it was recommended. One entry per player &amp; market per day.
      Long Shots and stale-line flags are tracked in their own buckets at a flat
      0.1u — never mixed into this record — and the Edge Board is a watchlist,
      not tracked bets.`)}
    ${unstaked}
    ${small}
    ${recAnalytics(src.curve, o)}
    ${recSplitsSection(o)}
    ${recRecentSection(src.recent || [])}
  `;
  host.innerHTML = scopeBar
    + _recordRooms(d, src, pmv, scope, scoped, receipts)
    + `<p class="rec-stamp">Updated ${escapeHtml(d.generated_at || "")}
      · settles automatically as results are ingested each day.</p>`;
  bindRecordScopes(host);
  bindSubtabs(host);
}

/* The five rooms of the Record page.
   ------------------------------------------------------------------
   Twenty-two sections used to stack here in one scroll. They were never
   twenty-two subjects — they are five, and the grouping below is the one
   already implied by what each panel answers:

     Receipts       what happened, in units
     By product     the buckets kept OUT of the main P&L on purpose
     Calibration    did the probabilities mean what they said
     What it learned the four-rung ladder, showing its work
     Health         whether this account survives being right

   Which panels exist depends on scope, and that is why the groups are
   built as strings and handed to `subtabbedHTML` rather than declared as
   a fixed bar: scoped to one sport, most of "By product" is empty, and a
   tab that opens an empty room is worse than no tab at all. */
function _recordRooms(d, src, pmv, scope, scoped, receipts) {
  // Whole-journal panels are written as inline `scoped ? "" : X` rather
  // than through a helper. A helper reads better and hides the guard from
  // the tests that exist to prove it: six of them scan for `scoped` beside
  // each call, because "a per-book limit risk shown under one sport's
  // name" is a wrong number, not a layout slip. Legibility to the test is
  // worth more here than tidiness.
  // The learning ladder renders on EVERY scope, filtered to the sport in
  // view — each league fits on its own bets. Hiding these behind "All" is
  // how the whole ladder once shipped invisible: this page always lands
  // sport-scoped. Spelled out at each call for the same reason the scope
  // guards above are: a test proves this and can only read what is written.
  return subtabbedHTML("record", [
    ["receipts", "Receipts",
     "what happened, in units — the curve, the splits, every settled pick",
     (scoped ? "" : recPaperBook(d.paper, d.overall, d.paper_mode, d.paper_recent)) + receipts],
    ["products", "By product",
     "the buckets deliberately kept out of the main P&L",
     (scoped ? "" : recLongshotSection(d.longshots)) + (scoped ? "" : recParlaySection(d.parlays))
     + (scoped ? "" : recStaleSection(d.stale_flags)) + (scoped ? "" : recFormSection(d.form_sampler))
     + (scoped ? "" : recLooseSection(d.loose_sampler))
     + (scoped && scope !== "ufc" ? "" : recUfcSection(d.ufc_record))
     // Polymarket's flags are not wagers in this ledger — they are graded
     // by their own report card. Folding a flag rate into a betting P&L
     // would make both numbers mean nothing.
     + (scoped && scope !== "intel" ? "" : recPolymarketSection(pmv))],
    ["calibration", "Calibration",
     "did “60%” actually mean 60%?",
     (scoped ? "" : recEraSection(d.model_eras))
     + recCalibrationSection(src.calibration, src.calibration_era)
     + recSelectionHaircut(d.selection_haircut, scoped ? scope : null)
     + (scoped ? "" : recCalibrationSplits(d.calibration_splits))
     + (scoped ? "" : recForecastLog(d.forecast_log))],
    ["learning", "What it learned",
     "the four-rung ladder, showing its work",
     recRestatedSection(d.restated, scoped ? scope : null) + recProseSection(d.prose, scoped ? scope : null)
     + recSelfTuningSection(d.self_tuning, scoped ? scope : null)
     + recLossPatternsSection(d.loss_patterns, scoped ? scope : null)
     + recPrereg(d.prereg)
     + recHypothesisLab(d.hypothesis_lab, scoped ? scope : null)],
    ["health", "Health",
     "whether this account survives being right",
     (scoped ? "" : recHealthSection(d.account_health))],
  ]);
  if (typeof mountEChartsAnalytics === "function") mountEChartsAnalytics(host);
}

/* One settled row. Extracted so the paper book renders through the SAME
   function as the main receipts rather than a lookalike — Ethan asked for
   the paper bets posted, and a second copy of this markup would drift
   from the first the next time either is touched, leaving two lists that
   disagree about what a "lucky" chip means. */
function recSettledRow(b) {
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
      }

/* The paper book, which the export has always carried and the page has
   never shown. Ethan, 2026-08-16: "so did we learn something in paper
   mode??? i see its +17% roi but im not seeing that reflected in the roi
   on the website." He was right that it was missing and right to ask —
   `record.json` carries `paper` and `paper_mode` and nothing read either.

   The block leads with the fact that makes the comparison mean something:
   paper mode does not change a pick, a price or a settlement. It changes
   the row's category and the dollar column. So a gap between the two
   books is not something paper mode DID — it is an era effect, and the
   question it raises is what else changed on that date. */
function recPaperBook(paper, main, on, recent) {
  if (!paper || !(paper.settled || paper.wins || paper.losses)) return "";
  const band = (perf) => {
    const n = (perf.wins || 0) + (perf.losses || 0);
    if (!n) return null;
    const hit = (perf.wins || 0) / n;
    const staked = perf.units_staked || 0;
    let b = perf.wins ? ((perf.net_units || 0) / perf.wins)
                        / Math.max(staked / n, 1e-9) : 1;
    b = Math.min(Math.max(b, 0.5), 5);
    const se = Math.sqrt(Math.max(hit * (1 - hit), 1e-9)) * (1 + b) / Math.sqrt(n);
    return { n, roi: perf.roi || 0, se, z: se ? (perf.roi || 0) / se : 0 };
  };
  const rows = [["Paper rows — no money on them", paper],
                ["Money rows", main]]
    .map(([label, perf]) => {
      const s = band(perf);
      if (!s) return "";
      const sig = Math.abs(s.z) >= 2
        ? "distinguishable from zero"
        : `${Math.abs(s.z).toFixed(1)} SE from zero — not yet a result`;
      return `<div style="display:flex;gap:12px;align-items:baseline;
                  padding:9px 0;border-bottom:var(--hairline) solid var(--border-soft)">
        <span style="flex:1;min-width:0">${escapeHtml(label)}
          <span class="sub">${perf.wins || 0}&ndash;${perf.losses || 0} ·
          ${(perf.units_staked || 0).toFixed(1)}u staked</span></span>
        <span style="font-variant-numeric:tabular-nums" class="${toneOf(s.roi)}">
          <strong>${s.roi >= 0 ? "+" : ""}${(s.roi * 100).toFixed(1)}%</strong>
          ± ${(s.se * 100).toFixed(1)}%</span>
        <span class="chip" style="flex-shrink:0">${sig}</span></div>`;
    }).join("");
  return `<div class="section-title">Inside the record
      <span class="sub">— the same model, split by whether money rode on
      it.</span></div>
    <div class="card">
      <p style="margin:0 0 10px;font-size:var(--fs-sm);color:var(--text-mute)">
        <b style="color:var(--text)">These two lines are already added
        together in the record above.</b> Ethan, 2026-08-13: "combine our
        paper record and normal money record." They are one strategy, because
        paper mode${on ? " is on and" : ""} changes exactly two things — which
        book a row is filed in, and the dollar column. The pick, the price, the
        settlement and the CLV are identical, so there is no second model here
        to separate out. The split is kept below only because the DOLLARS
        differ: unit ROI pools honestly, dollars stay real-money-only, and no
        paper row has ever moved the bankroll.</p>
      ${rows}
      <p style="margin:10px 0 0;font-size:var(--fs-sm);color:var(--text-faint)">
        Each line carries a standard error because neither half is large, and
        a gap between them is an <b style="color:var(--text)">era</b> effect
        rather than something paper mode did — which is why pooling them is
        the honest read and separating them was the misleading one. A
        percentage on 74 bets without an error bar is how a coin flip gets
        read as a turnaround.</p>
    </div>
    ${!(recent || []).length ? "" : `
      <div class="section-title minor">Every paper bet
        <span class="sub">— all ${recent.length}, newest first, at the price
        we would have got. Same list, same grading, same closing-line check
        as the money book above it.</span></div>
      <div class="card rec-list">${recent.map(recSettledRow).join("")}</div>`}`;
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
    <div class="section-title minor">Team-form sampler — measurement in progress
      <span class="sub">— every hot-vs-cold matchup, hot side’s moneyline at the real book
      price. Flat 0.1u, zero bankroll impact, never in the record above.</span></div>
    ${recDisclosure("What this is testing", `Streaks are the most public stat in
      sports, so the default assumption is the market already prices them — hot teams
      cost more to back. This bucket journals the hot team’s moneyline in every
      hot-vs-cold matchup at the price someone could actually bet, and settles it
      against the real result. The promotion bar is the same as every sampler:
      100+ graded, z ≥ 2, positive ROI. Clear it and form becomes a model input;
      miss it and we’ve learned the market has streaks covered — cheaply.`)}
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
         · the field’s consensus said <strong>${(st.avg_consensus_implied * 100).toFixed(1)}%</strong>
         · they actually hit <strong>${(st.actual_hit_rate * 100).toFixed(1)}%</strong>.
         Hitting above the taken price’s implied = the cheap price was real value.</div>` : "";
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
    <div class="section-title minor">Stale-line sampler — measurement in progress
      <span class="sub">— every pre-game stale-line flag, taken at the flagged price. Flat 0.1u,
      zero bankroll impact, never in the record above.</span></div>
    ${recDisclosure("What this is testing", `The scanner flags a book pricing
      a side at least a point cheaper than every other book’s consensus. On 30,448
      harvested quotes, taking that price beat the eventual close 64.8% of the time —
      but closing-line value is a statistic, not money. This bucket journals every
      pre-game flag automatically and settles it against the real result. If the hit
      rate clears the taken price’s break-even over a real sample, the signal graduates
      from "interesting" to "bettable" — and if it doesn’t, this table is how we find
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
      market: r.market_label || r.market || "Props",
      // The check means "on the Recommended page RIGHT NOW", so it must apply the
      // user's sliders — the build-time flag can disagree with them.
      ev: r.ev_per_unit, grade: r.grade, rec: passesFilters(r),
      open: propAttrs(r),
      // Ethan, 2026-08-13: "we need to show headshots on this page." Every
      // other board leads with the player; this one was a wall of text,
      // which makes it the slowest list on the site to scan even though it
      // is the one with the most rows.
      mark: betMark(r, 30),
      // Ethan, 2026-08-17: "the 'player prop' page should have the charts
      // along with the player props." The history was already on every
      // row — it just never got drawn here.
      vals: (r.logs || []).map((l) => l.value),
      line: r.line, team: r.team,
    }));
  const games = (state.data.game_bets || [])
    .filter((b) => b.grade !== "Pass" && (b.ev_per_unit || 0) > 0.005)
    .map((b) => {
      const s = gameBetSeries(b);   // one call — it reads team_recent twice
      return {
        label: b.pick_label, sub: `${b.matchup} · ${b.market_label}`,
        odds: b.odds, model: b.win_prob, implied: b.fair_prob,
        market: "Game lines",
        ev: b.ev_per_unit, grade: b.grade, rec: passesGameBet(b),
        open: gameBetAttrs(b),
        mark: (b.bet_type === "total" ? leagueMark(state.sport, 30)
               : teamMark(b.team || b.home, 30)),
        vals: s ? s.values : [], line: s ? s.line : undefined,
        team: b.team || b.home,
      };
    });
  return [...props, ...games].sort((a, b) => b.ev - a.ev);
}

function edgeRowHTML(r, i) {
  const evPct = (r.ev * 100).toFixed(1);
  // Ethan, 2026-08-17: "the 'player prop' page should have the charts
  // along with the player props." Same bars the prop page draws large,
  // against the same line, from the row's own log.
  const spark = (r.vals || []).length >= 3
    ? `<span class="edge-spark" title="Last ${Math.min(r.vals.length, 10)} games against the line">${
        gamelogBars(r.vals, { line: r.line, w: 92, h: 34,
                              stroke: teamPrimary(r.team) })}</span>`
    : `<span class="edge-spark"></span>`;
  return `<div class="ls-row drow ${r.open ? "openable" : ""}"${r.open || ""}
       style="display:flex;align-items:center;gap:14px;
       padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
    <span style="opacity:.5;min-width:20px">${i + 1}</span>
    <span class="pick-id" style="flex-shrink:0">${r.mark || ""}</span>
    <span style="flex:1"><strong>${escapeHtml(r.label)}</strong>
      <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(r.sub)}</span></span>
    ${spark}
    <span style="min-width:64px;text-align:right">${r.odds > 0 ? "+" : ""}${r.odds}</span>
    <span style="min-width:120px;text-align:right;opacity:.8">
      ${(r.model * 100).toFixed(0)}% vs ${(r.implied * 100).toFixed(0)}%</span>
    <span style="min-width:70px;text-align:right;color:var(--good)">
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
      beats the model’s probability — including small edges and long odds that
      don’t clear the Recommended bar. Expected value is honest math, not a
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
  // The render's market grid (Ethan, 2026-08-11): one tile per market
  // actually priced tonight, its count real, tap to filter the board.
  const byMarket = {};
  rows.forEach((r) => { byMarket[r.market] = (byMarket[r.market] || 0) + 1; });
  const markets = Object.keys(byMarket).sort((a, b) => byMarket[b] - byMarket[a]);
  let mk = window._edgeMarket || "";
  if (mk && !byMarket[mk]) mk = "";
  const grid = markets.length > 1 ? `<div class="pm-grid">
      ${markets.map((m, i) => `<button class="pm-tile hue${i % 6} ${mk === m ? "active" : ""}"
        onclick="window._edgeMarket=window._edgeMarket==='${escapeHtml(m)}'?'':'${escapeHtml(m)}';renderEdgeBoard()">
        <span class="pm-name">${escapeHtml(m)}</span>
        <span class="pm-count">${byMarket[m]} priced</span></button>`).join("")}
    </div>` : "";
  const shown = mk ? rows.filter((r) => r.market === mk) : rows;
  host.innerHTML = grid + (EDGE_BANDS.map(([title, test]) => {
    const band = shown.filter((r) => test(r.odds));
    if (!band.length) return "";
    return `<div class="section-title">${title}
        <span class="sub">— ${band.length} bet(s)</span></div>
      <div class="card" style="padding:0">${band.map(edgeRowHTML).join("")}</div>`;
  }).join("") || "");
}

/* ============================================================
   Market Scanner — arbitrage / middles / low holds / sharp money
   ============================================================ */
/* The face/logo the other boards lead with (Ethan, 2026-08-17: "the
   line shopping page doesnt show any headshots"). Guarded, because a
   payload built before the scanner rows carried player/team should
   render the row it always rendered, not a broken avatar. */
function scanMark(t) {
  return (t.player || t.team)
    ? `<span class="pick-id" style="flex-shrink:0">${betMark(t, 26)}</span>` : "";
}

function scanPairRow(p, extra) {
  const leg = (side, l) =>
    `<span style="display:block"><strong>${side} ${l.line}</strong>
       <span style="opacity:.65">@ ${escapeHtml(l.book)} ${american(l.odds)}</span></span>`;
  return `<div class="drow" style="display:flex;align-items:center;gap:14px;padding:11px 16px;
      border-bottom:1px solid rgba(255,255,255,.05)">
    ${scanMark(p)}
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
    ${scanMark(t)}
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
        ${scanMark(t)}
        <span style="flex:1"><strong>${escapeHtml(t.bet)}</strong>
          <span style="display:block;opacity:.65;font-size:.85em">
            ${escapeHtml(t.book)} ${american(t.odds)} · implied ${(t.implied * 100).toFixed(1)}%
            ${t.grade ? ` · graded ${escapeHtml(t.grade)}` : ""}</span></span>
        <span style="min-width:170px;text-align:right">
          <span style="color:var(--bad);font-weight:700">${(t.measured_roi * 100).toFixed(1)}% historically</span>
          <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(t.band)} band</span></span>
      </div>`,
      "No plus-money quotes on today’s board — main props or long shots. That’s the cheap place to be.")
    + scanSection("Arbitrage", "opposite sides priced so a margin is locked whichever way it lands — IF both legs fill at the shown prices before they move. Rare across US books and gone in minutes",
      arbs, (a) => {
        const so = stake * a.stake_over_pct, su = stake * (1 - a.stake_over_pct);
        const ret = stake * a.profit_pct;
        const suspect = a.suspect
          ? `<span style="display:block;color:var(--warn);font-size:.85em">${icon('warn')} 5%+ edge — likely a stale line or void risk; verify at both books</span>` : "";
        return scanPairRow(a,
          `<span style="color:var(--good);font-weight:700">+${(a.profit_pct * 100).toFixed(2)}% · $${ret.toFixed(2)} locked</span>
           <span style="display:block;opacity:.7;font-size:.85em">$${so.toFixed(0)} Over / $${su.toFixed(0)} Under</span>${suspect}`);
      },
      "No arbitrage pairs right now. Real arbs across legal US books appear a few times a week and last minutes — this scanner checks every refresh.")
    + scanSection("Middles", "Over at a low line + Under at a higher one: land between them and BOTH win; miss and you only pay the vig. Ranked by EV from the sport’s real outcome distribution — never by window width",
      middles, (m) => {
        const evLine = m.ev_per_unit != null
          ? `<span style="font-weight:700;color:${m.ev_per_unit >= 0 ? "var(--good)" : "var(--text-mute)"}">${m.ev_per_unit >= 0 ? "+" : ""}${(m.ev_per_unit * 100).toFixed(1)}% EV</span>
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
              <span style="display:block;opacity:.6;font-size:.85em">${escapeHtml(b.matchup || "")} · priced off the sharp book’s fair value</span></span>
            <span style="min-width:64px;text-align:right">${american(b.odds)}</span>
            <span style="min-width:80px;text-align:right;color:var(--good)">+${((b.ev_per_unit || 0) * 100).toFixed(1)}% EV</span>
          </div>`).join("")}
        ${steam.map(({ r, m }) => {
          // Every alert answers: is this still bettable, or already missed?
          const age = m.moved_ago_min;
          const cls = (age != null && age > 180)
            ? ["Stale", "var(--text-mute)", "old move — informational only"]
            : ((r.ev_per_unit || 0) > 0
               ? ["Live", "var(--good)", "value still available near the sharp number"]
               : ["Chase", "var(--warn)", "line already moved past it — do not follow"]);
          return `<div class="drow" style="display:flex;align-items:center;gap:14px;padding:11px 16px;border-bottom:1px solid rgba(255,255,255,.05)">
            <span>${iconMark("hot")}</span>
            <span style="flex:1"><strong>${escapeHtml(r.player)} ${escapeHtml(r.market_label || "")}</strong>
              <span style="display:block;opacity:.6;font-size:.85em">steam — several books moved together, ${m.verdict === "with" ? "toward" : "against"} our ${escapeHtml(r.side || "")}${age != null ? ` · ${age < 60 ? age + "m" : Math.round(age / 60) + "h"} ago` : ""} · ${cls[2]}</span></span>
            <span style="min-width:56px;text-align:right;font-weight:700;color:${cls[1]}">${cls[0]}</span>
            <span style="min-width:120px;text-align:right;opacity:.8">${Math.abs(m.delta || 0) > 1e-9 ? `${m.open} → ${m.current}` : `${m.open_odds != null ? american(m.open_odds) : "?"} → ${m.current_odds != null ? american(m.current_odds) : "?"}`}</span>
          </div>`;
        }).join("")}
        ${!anchors.length && !steam.length ? `<p class="loading" style="padding:12px">
          Nothing sharp-flagged right now. Sharp-anchor picks appear when a soft book’s
          price beats the sharp book’s fair value; steam appears when several books
          re-price together inside an hour.</p>` : ""}
      </div>
      <p style="opacity:.55;font-size:.85em;margin-top:12px">Positive-EV bets live on the
      <b>Recommended</b> and <b>Edge Board</b> pages — that’s the model’s job. This page
      needs no model: it’s the books disagreeing with each other. Arbitrage and middle
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
const STANDALONE_MODES = ["intel", "fantasy", "memes", "ufc", "why", "about",
                          "record", "lab", "mybets"];

// Header identity per standalone page — the tagline follows the ACTIVE
// page. Before this, opening Polymarket from the MLB tab left a baseball
// description in the corner of a page that has nothing to do with baseball.
const STANDALONE_BRAND = {
  intel: { tagline: "Prediction Market — venue prices and informed flow" },
  fantasy: { tagline: "Fantasy football — usage, scripts, draft kit" },
  memes: { tagline: "Rocket Radar — meme-coin flow, danger drawn loudest" },
  ufc: { tagline: "Scalpy MMA — dossier-gated fight model" },
  why: { tagline: "See the math. Know if it’s working." },
  record: { tagline: "The Book — every pick journaled, graded, learned from" },
  lab: { tagline: "The Lab — the model replayed against stored history" },
  mybets: { tagline: "My Bets — your own sportsbook P&L, kept on this device" },
};

function enterStandaloneMode(name) {
  document.querySelectorAll(".sport-btn").forEach((x) =>
    setSelected(x, !!x.dataset.sport && x.dataset.sport === name));
  // The top nav stays: it is global chrome in the new shell, and the
  // sidebar (not the bar) carries the page context on standalone views.
  // The masthead's Running ROI is the SPORTS model's record. Above the
  // meme board it reads as meme P&L (Ethan's screenshot: "-14.9%" in
  // red directly over the coins), and My Bets is the user's own ledger
  // — on both pages the strip is a category error and a third of the
  // header's height. Everywhere else it stays: it is the site's pitch.
  const noRec = name === "memes" || name === "mybets";
  const rec = document.getElementById("standing-record");
  if (rec) rec.style.display = noRec ? "none" : "";
  const mbrec = document.getElementById("mb-rec");
  if (mbrec) mbrec.style.display = noRec ? "none" : "";
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
  const rec = document.getElementById("standing-record");
  if (rec) rec.style.display = "";
  const mbrec = document.getElementById("mb-rec");
  if (mbrec) mbrec.style.display = "";
  const phead = document.querySelector('.menu-head[data-head="page"]');
  if (phead) phead.style.display = "";
  document.querySelectorAll(".sport-btn").forEach((x) =>
    setSelected(x, !!x.dataset.sport && x.dataset.sport === state.sport));
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
/* The desk's actual recommendations (Ethan, 2026-08-11: "I've never
   once seen a recommended bet for our prediction market"). Two honest
   edge sources, each row saying WHY in its own numbers: our game models
   priced against Kalshi's sports markets, and the NWS forecast priced
   against the daily-high brackets. PAPER-staked until the bucket's own
   graded record earns promotion — the loose book's exact contract.
   Politics carries no recommendations on purpose: there is no public
   number to price it against, and the flow detector below already
   covers it with graded flags. */
function deskSectionHTML(k) {
  if (!k) return "";
  const sports = (k.rows || []).filter((r) => r.rec);
  const wx = (k.weather || []).filter((r) => r.rec);
  const paper = ((k.desk || {}).paper) || {};
  // A row with no recorded side renders nothing — a chip that can read
  // "undefined" is the widget printing its own missing field.
  const side = (s) => s
    ? `<span class="chip ${s === "YES" ? "up" : "down"}">${escapeHtml(s)}</span>` : "";
  const row = (r, why) => `<div class="kx-row">
      <span class="kx-sport chip">${escapeHtml((r.sport || r.city || "").toUpperCase())}</span>
      <span class="kx-title">${escapeHtml(r.title)} ${side(r.rec_side)}
        <span class="kx-match">· ${why}</span></span>
      <span class="kx-num kx-k">${(r.prob * 100).toFixed(0)}¢</span>
      <span class="kx-num kx-m">${(r.model_p * 100).toFixed(0)}%</span>
      <span class="kx-num kx-e"><span style="color:var(--${r.edge_pts > 0 ? "good" : "bad"});font-weight:700">${r.edge_pts > 0 ? "+" : ""}${r.edge_pts} pts</span></span>
      <span class="kx-vol">$${Number(r.volume_24h || 0).toLocaleString()}</span>
    </div>`;
  const rows = [
    ...sports.map((r) => row(r, `our model ${(r.model_p * 100).toFixed(0)}% vs the exchange&rsquo;s ${(r.prob * 100).toFixed(0)}¢`)),
    ...wx.map((r) => row(r, `NWS high ${r.forecast_f}&deg; &plusmn;${r.sigma_f}&deg; for ${escapeHtml(r.city)} ${escapeHtml(r.date)}`)),
  ].join("");
  const graded = paper.settled || 0;
  const paperLine = graded
    ? `${paper.wins || 0}&ndash;${paper.losses || 0} graded · ${((paper.roi || 0) * 100).toFixed(1)}% ROI on flat paper stakes`
    : "nothing graded yet — daily weather markets settle same-day, so this record fills fast";
  return `
    <div class="section-title">The desk’s recommendations
      <span class="sub">— all on Kalshi, because a recommendation needs a price we can
      model against and Polymarket rows carry no model number.
      Every row clears a written gate (edge &ge; 6 pts sports / 8 pts weather,
      a real two-sided book, live volume) and is journaled at a flat 0.1u PAPER stake.
      ${paperLine}. Promotion to real stakes takes 100+ graded rows in profit — the same
      bar every other bucket on this site has to clear.</span></div>
    ${rows ? `<div class="card kx-table" style="padding:0">${rows}</div>`
           : `<p class="loading" style="padding:12px">No market clears the gate right now.
      The desk needs: the Kalshi feed reachable at build time, a game our model prices
      (or a city the forecast covers), and a disagreement bigger than the bar. Each build
      prints which of those was missing — nothing here is ever forced.</p>`}`;
}

/* ONE board out of two venues.
   ------------------------------------------------------------------
   Ethan, 2026-08-12: "Combine the kalshi and polly market board. There
   is too much too scroll through and they are basically the same
   thing." They are: both are event contracts priced in cents, and
   reading them as two tables meant scrolling past one to compare with
   the other. So the row shape is normalized here and the venue becomes
   a COLUMN rather than a section heading.

   What does NOT get flattened is where the two feeds genuinely differ.
   Kalshi gives a two-sided book we can price against, so those rows
   carry a model number and an edge. Polymarket gives a public trade
   tape with wallet identity, which is flow — a different question, and
   it keeps its own tab. Where a venue has no answer the cell is a dash;
   inventing a model number for a Polymarket row to fill the column
   would be the kind of fake symmetry this merge is supposed to kill. */
function pmVenueRows(kx, d) {
  const rows = [];
  for (const r of ((kx || {}).rows || [])) {
    rows.push({
      venue: "KALSHI", title: r.title,
      sub: [(r.sport || "").toUpperCase(), r.matchup].filter(Boolean).join(" · "),
      price: r.prob, model: r.model_p, edge: r.edge_pts,
      vol: r.volume_24h, basis: r.price_basis, url: "",
      key: `k:${r.ticker || r.title}`, sport: (r.sport || "").toUpperCase(),
      rec: !!r.rec, rec_side: r.rec_side || "", matchup: r.matchup || "",
      spread_cents: r.spread_cents, ends: "",
    });
  }
  for (const m of ((d || {}).markets || [])) {
    rows.push({
      venue: "POLY", title: m.question,
      sub: m.end_date ? `resolves ${m.end_date}` : "",
      price: m.yes, model: null, edge: null,
      vol: m.vol24, basis: "", url: m.slug
        ? `https://polymarket.com/market/${m.slug}` : "",
      key: `p:${m.slug || m.question}`, sport: "", rec: false, rec_side: "",
      matchup: "", spread_cents: null, ends: m.end_date || "",
    });
  }
  // Volume is the one measure both venues report the same way, so it is
  // the only honest way to rank a mixed table.
  rows.sort((a, b) => (Number(b.vol) || 0) - (Number(a.vol) || 0));
  return rows;
}

/* --- The render-copy board (Ethan's Zenos renders, 2026-08-18) ----------
   "i really love the graphics and layouts of these renders so i wanna
   follow that pixel for pixel." The layout is the render's: category
   tabs, four stat tiles, the market table on the left, and a detail
   panel on the right that opens when a row's View is tapped. Our tokens,
   our name — and NO trade box: the render's "Trade Yes 62¢" block is
   the one element that must never cross, because this site takes no
   wagers (test-pinned). The detail panel's analysis card is BETTER than
   the render's marketing bullets: it prints the desk's actual gate
   conditions, pass or fail, with the measured numbers. */
let _pmSelKey = null;
let _pmCatSel = "top";
window._pmPick = (k) => { _pmSelKey = k; renderIntel(); };
window._pmCatSet = (c) => { _pmCatSel = c; renderIntel(); };

/* The desk's own gate, mirrored from engine/sources/kalshi.py so the
   checklist prints the real bars, not vibes. */
const PM_GATE = { edge: 6.0, vol: 250.0, spread: 6.0 };

function pmDetailHTML(r) {
  if (!r) return `<div class="pm-d-empty">${icon("signal", 26)}
    <p>Tap <b>View</b> on any market to open its full read here.</p></div>`;
  const yes = r.price == null ? null : Math.round(r.price * 100);
  const no = yes == null ? null : 100 - yes;
  const modeled = r.model != null;
  const check = (ok, text) => `<li class="${ok ? "ok" : "no"}">${
    icon(ok ? "check" : "cross", 12)} ${text}</li>`;
  const gates = r.venue !== "KALSHI" ? "" : `
    <div class="pm-d-card"><div class="gp-panel-title">The desk’s gate
        <span class="gp-panel-sub">— the real bars, pass or fail</span></div>
      <ul class="pm-d-checks">
        ${check(modeled && Math.abs(r.edge || 0) >= PM_GATE.edge,
          modeled ? `Edge ${r.edge > 0 ? "+" : ""}${r.edge} pts against the ${PM_GATE.edge}-pt bar`
                  : "No model number — we do not price this claim")}
        ${check(r.basis === "book" || r.basis === "mid",
          r.basis === "book" || r.basis === "mid"
            ? "Two-sided book — the mid is a real probability"
            : "One-sided book — price is the last trade, not a mid")}
        ${check(Number(r.vol) >= PM_GATE.vol,
          `24h volume $${Number(r.vol || 0).toLocaleString()} against the $${PM_GATE.vol} floor`)}
        ${r.spread_cents == null ? "" : check(r.spread_cents <= PM_GATE.spread,
          `Spread ${r.spread_cents}¢ against the ${PM_GATE.spread}¢ cap`)}
      </ul>
      ${r.rec ? `<p class="pm-d-verdict good">${icon("check", 12)} Clears every
        gate — journaled as a paper recommendation (${escapeHtml(r.rec_side)}).</p>`
      : `<p class="pm-d-verdict">Does not clear the gate — shown as a price,
        not a pick.</p>`}
    </div>`;
  const summary = `
    <div class="pm-d-card"><div class="gp-panel-title">Market summary</div>
      <div class="pm-d-rows">
        <div><span>Venue</span><b>${r.venue === "POLY" ? "Polymarket" : "Kalshi"}</b></div>
        <div><span>Type</span><b>Binary</b></div>
        ${r.ends ? `<div><span>Resolves</span><b>${escapeHtml(r.ends)}</b></div>` : ""}
        ${r.matchup ? `<div><span>Matched game</span><b>${escapeHtml(r.matchup)}</b></div>` : ""}
        <div><span>24h volume</span><b>$${Number(r.vol || 0).toLocaleString()}</b></div>
        ${r.basis ? `<div><span>Price basis</span><b>${escapeHtml(r.basis)}</b></div>` : ""}
      </div></div>`;
  return `
    <div class="pm-d-head">
      <span class="chip kx-venue">${r.venue}</span>
      <h3 class="pm-d-title">${r.url
        ? `<a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>`
        : escapeHtml(r.title)}</h3>
      ${r.sub ? `<div class="pm-d-sub">${escapeHtml(r.sub)}</div>` : ""}
    </div>
    <div class="pm-d-prices">
      <div class="pm-d-price yes"><b>${yes == null ? "—" : yes + "¢"}</b><span>Yes</span></div>
      <div class="pm-d-price no"><b>${no == null ? "—" : no + "¢"}</b><span>No</span></div>
      ${modeled ? `<div class="pm-d-edge" style="color:var(--${(r.edge || 0) >= 0 ? "good" : "bad"})">
        ${(r.edge || 0) >= 0 ? "+" : ""}${r.edge} pts<span>Qellys edge</span></div>` : ""}
    </div>
    ${modeled ? `<p class="pm-d-model">Our model prices the same claim at
      <b>${Math.round(r.model * 100)}%</b>.</p>` : ""}
    ${summary}
    ${gates}
    ${r.url ? `<a class="btn pm-d-out" href="${escapeAttr(r.url)}" target="_blank"
      rel="noopener">View on Polymarket ↗</a>` : ""}
    <p class="pm-d-note">Prices are the venues’ own. This panel is a read,
      not an order ticket — Qellys takes no wagers.</p>`;
}

const PM_BOARD_SHOWN = 40;

function pmBoardRowHTML(r) {
  const edge = r.edge == null ? `<span style="opacity:.45">—</span>`
    : `<span style="color:var(--${r.edge > 0 ? "good" : "bad"});font-weight:700">
         ${r.edge > 0 ? "+" : ""}${r.edge} pts</span>`;
  const basis = r.basis === "last_trade"
    ? ` <span class="chip" title="One side of the book is empty — this is the last trade, not a two-sided mid">last trade</span>` : "";
  const title = r.url
    ? `<a href="${escapeAttr(r.url)}" target="_blank" rel="noopener"
          style="color:inherit">${escapeHtml(r.title)}</a>`
    : escapeHtml(r.title);
  // The row's numbers, drawn as lengths — see the meter comment history.
  const pct = r.price == null ? null
    : Math.max(0, Math.min(100, r.price * 100));
  const mdl = r.model == null ? null
    : Math.max(0, Math.min(100, r.model * 100));
  const meter = pct == null ? "" : `<span class="kx-meter" aria-hidden="true">
      <span class="kx-meter-fill" style="width:${pct.toFixed(1)}%"></span>
      ${mdl == null ? "" : `<span class="kx-meter-model ${
        r.edge > 0 ? "up" : r.edge < 0 ? "down" : ""
      }" style="left:${mdl.toFixed(1)}%"></span>`}
    </span>`;
  const no = r.price == null ? null : Math.round((1 - r.price) * 100);
  return `<div class="kx-row${_pmSelKey === r.key ? " sel" : ""}">
    <span class="kx-sport chip kx-venue">${r.venue}</span>
    <span class="kx-title" title="${escapeAttr(r.title)}">${title}
      ${r.sub ? `<span class="kx-match">· ${escapeHtml(r.sub)}</span>` : ""}${basis}</span>
    <span class="kx-num kx-k" title="The venue’s own price for YES" style="color:var(--good)">${
      r.price == null ? "—" : (r.price * 100).toFixed(0) + "¢"}</span>
    <span class="kx-num kx-n" title="The venue’s implied price for NO" style="color:var(--bad)">${
      no == null ? "—" : no + "¢"}</span>
    <span class="kx-num kx-m" title="Our model’s probability for the same claim">${
      r.model == null ? "—" : (r.model * 100).toFixed(0) + "%"}</span>
    <span class="kx-num kx-e">${edge}</span>
    <span class="kx-vol" title="24h volume">$${Number(r.vol || 0).toLocaleString()}</span>
    <button class="btn pm-view" onclick="window._pmPick('${escapeAttr(r.key)}')">View</button>
    ${meter}
  </div>`;
}

function predBoardHTML(kx, d) {
  const all = pmVenueRows(kx, d);
  const k = kx || {};
  const modeled = ((k.rows) || []).filter((r) => r.model_p != null);
  const nRec = ((k.rows) || []).filter((r) => r.rec).length
    + ((k.weather) || []).filter((r) => r.rec).length;
  const tile = (label, v, sub) => `<div class="tile"><div class="k">${label}</div>
    <div class="v">${v}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;

  // Category tabs, the render's top strip. "Top opportunities" sorts the
  // PRICED markets by the size of the gap; everything else is the plain
  // volume table, filtered to one sport where one is picked.
  const cats = [["top", "Top opportunities"], ["all", "All markets"]];
  for (const s of [...new Set(all.map((r) => r.sport).filter(Boolean))].sort()) {
    cats.push([`s:${s}`, s]);
  }
  if (!cats.some(([c]) => c === _pmCatSel)) _pmCatSel = "top";
  const tabs = `<div class="pm-cats">${cats.map(([c, label]) =>
    `<button class="mbc-chip${_pmCatSel === c ? " active" : ""}"
       onclick="window._pmCatSet('${c}')">${escapeHtml(label)}</button>`).join("")}</div>`;

  let rows = all;
  if (_pmCatSel === "top") {
    rows = all.slice().sort((a, b) =>
      (b.edge == null ? -1 : Math.abs(b.edge)) - (a.edge == null ? -1 : Math.abs(a.edge)));
  } else if (_pmCatSel.startsWith("s:")) {
    rows = all.filter((r) => r.sport === _pmCatSel.slice(2));
  }
  const shown = rows.slice(0, PM_BOARD_SHOWN);
  const sel = all.find((r) => r.key === _pmSelKey) || null;

  const avgEdge = modeled.length
    ? modeled.reduce((s, r) => s + Math.abs(r.edge_pts || 0), 0) / modeled.length
    : null;
  const totVol = all.reduce((s, r) => s + (Number(r.vol) || 0), 0);

  return `
    ${deskSectionHTML(kx)}
    <div class="section-title">The board
      <span class="sub">— every live market from both venues. Kalshi runs a
      two-sided book we can price against, so those rows carry our number and
      the gap; Polymarket rows show the venue’s price and link out. A dash
      means we do not price that market, not that the edge is zero.</span></div>
    ${tabs}
    <div class="stats">
      ${tile("Markets tracked", all.length, "both venues, live now")}
      ${tile("Priced by our model", modeled.length, "Kalshi two-sided books")}
      ${tile("Average gap", avgEdge == null ? "—" : avgEdge.toFixed(1) + " pts",
             "model vs market, priced rows")}
      ${tile("24h volume", "$" + Math.round(totVol).toLocaleString(),
             `the desk recommends ${nRec}`)}
    </div>
    <div class="pm-layout">
      <div class="card kx-table pm-table" style="padding:0">${
        shown.map(pmBoardRowHTML).join("") || `
        <p class="loading" style="padding:12px">${escapeHtml(k.note
          || "No open markets on the last pull — the board fills as the venues list events.")}</p>`}
      </div>
      <aside class="card pm-detail">${pmDetailHTML(sel)}</aside>
    </div>
    ${rows.length > shown.length
      ? `<p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:8px">
         Showing ${shown.length} of ${rows.length} in this view.</p>` : ""}`;
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
  // Polymarket silent does not mean the page is empty: Kalshi is half of
  // this board and renders on its own. Same merged table, one venue in it.
  if (!d || (!(d.flow || []).length && !(d.markets || []).length)) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No Polymarket data on this pull</div>
      <div class="es-sub">The launcher pulls Kalshi’s order books and Polymarket’s public
      market list and trade tape on every refresh (free, no key needed). Kalshi’s side of
      the board is below; if both stay empty, the machine may not be able to reach the
      venues.</div></div>`
      + predBoardHTML(kx, d);
    if (typeof mountEChartsAnalytics === "function") mountEChartsAnalytics(host);
    return;
  }
  setStandaloneSource("Kalshi + Polymarket public feeds", "Prediction Market · live venue data");
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
      <!-- .pm-title so the stylesheet can find this link: it is the card’s
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

  /* THREE ROOMS, not one scroll. The page carried the desk, a Kalshi
     table, a Polymarket table, flow cards, trader cards and two
     validation blocks end to end — Ethan's "too much too scroll
     through". They are three different questions, so they are three
     tabs: what to bet, who is betting, and whether any of it works. */
  host.innerHTML = subtabbedHTML("intel", [
    ["board", "Board",
     "every live market from Kalshi and Polymarket in one table, plus the desk’s picks",
     predBoardHTML(kx, d)],
    ["flow", "Flow",
     "who is betting — Polymarket’s public tape, which Kalshi does not publish",
     `<div class="stats">
        ${tile("Trades on tape", Number(tape.stored_total || 0).toLocaleString(), `+${tape.new_this_pull || 0} this pull`)}
        ${tile("Wallets seen", Number(tape.wallets_seen || 0).toLocaleString(), "recording since day one")}
        ${tile("Flow flags · 24h", (d.flow || []).length, "$5K+ scored trades")}
        ${tile("Updated", escapeHtml((d.generated_at || "").slice(11, 16)), "refreshes with the site")}
      </div>
      <div class="section-title">Informed flow
        <span class="sub">— large trades scored for anomaly signals, with receipts on every chip
        (hover). Probabilities, never verdicts.</span></div>
      <div class="cards wide">${flagCards ||
        `<div class="empty-slate" style="grid-column:1/-1"><div class="es-icon">${icon("signal", 30)}</div>
          <div class="es-title">No flagged flow yet</div>
          <div class="es-sub">The feed scores the last 24h of recorded tape and accumulates
          across refreshes — big trades are a few per hour.</div></div>`}</div>
      <div class="section-title">Top traders
        <span class="sub">— ${escapeHtml(d.traders_note || "by realized profit")}</span></div>
      <div class="cards wide">${traderCards ||
        `<p class="loading" style="grid-column:1/-1">No trader data yet — fills on the next refresh.</p>`}</div>
      <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Wallet-age signal
        matures as the tape accrues (it cannot be backfilled). Kalshi carries no public
        trader identity, which is why it appears on the board as a PRICE and never here.
        Analyzing public flow is market research; what the CFTC prosecutes
        (2026) is trading on information <i>you</i> hold a duty to keep confidential.</p>`],
    ["proof", "Does it work?",
     "the flow signal graded against what actually happened",
     `${intelVerdict(d.validation)}${intelReportCard(d.validation)}`],
  ]);
  // Every other subtabbed page binds its rooms after writing them; without
  // this the tabs render and do nothing.
  bindSubtabs(host);
  if (typeof mountEChartsAnalytics === "function") mountEChartsAnalytics(host);
}

/* ============================================================
   MY BETS — the user's OWN sportsbook bets, tracked locally
   ============================================================
   Ethan, 2026-08-10: "Add a way to log into sportsbook accounts and
   track bets made by the user on the sportsbooks."

   WHY THERE IS NO ACCOUNT LOGIN HERE, and why that is the right call:
   no sportsbook publishes an API or an OAuth flow. The only way to
   "log in" programmatically is to store your DraftKings/FanDuel password
   and scrape the account — which their terms forbid, which trips bot
   detection that can freeze the account and its balance, and which would
   mean this site holding the credentials to your money. So this tracks
   the bets you LOG yourself, the way every honest personal tracker does.

   It is deliberately client-only: the entries live in this browser's
   localStorage, never touch a server, and are separate from the model's
   own journal (the Record page). Export writes a JSON file so you can
   back it up or move it to another device; import reads one back. The
   P&L math is standard American-odds payout, unit-tested by pinned
   known answers below. */
const MYBETS_KEY = "qb_mybets_v1";
const MYBETS_BOOKS = ["DraftKings", "FanDuel", "BetMGM", "Caesars",
                      "ESPN BET", "Fanatics", "bet365", "Other"];

function mbLoad() {
  try {
    const raw = localStorage.getItem(MYBETS_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch (e) { return []; }
}
function mbSave(bets) {
  try { localStorage.setItem(MYBETS_KEY, JSON.stringify(bets)); } catch (e) {}
  acctTouch("mybets");   // signed in → the account copy follows this one
}

/* American odds → decimal multiplier on the stake. +150 → 2.5, −120 →
   1.8333. The one piece of real math on the page, so it is its own pure
   function and the tests pin it. */
function mbDecimal(american) {
  const a = Number(american);
  if (!a || isNaN(a)) return null;
  return a > 0 ? 1 + a / 100 : 1 + 100 / Math.abs(a);
}

/* Profit (not return) on ONE settled bet. Win pays stake×(dec−1); a loss
   is −stake; a push is zero; a pending bet has no realized number. */
function mbProfit(bet) {
  const stake = Number(bet.stake) || 0;
  if (bet.result === "win") {
    const dec = mbDecimal(bet.odds);
    return dec == null ? 0 : stake * (dec - 1);
  }
  if (bet.result === "loss") return -stake;
  return 0;                          // push or pending
}

function mbStats(bets) {
  const settled = bets.filter((b) => ["win", "loss", "push"].includes(b.result));
  const staked = settled.reduce((s, b) => s + (Number(b.stake) || 0), 0);
  const profit = settled.reduce((s, b) => s + mbProfit(b), 0);
  const wins = settled.filter((b) => b.result === "win").length;
  const losses = settled.filter((b) => b.result === "loss").length;
  const pushes = settled.filter((b) => b.result === "push").length;
  const pending = bets.length - settled.length;
  const atRisk = bets.filter((b) => b.result === "pending")
    .reduce((s, b) => s + (Number(b.stake) || 0), 0);
  return { n: bets.length, settled: settled.length, pending, wins, losses,
           pushes, staked, profit, atRisk,
           roi: staked > 0 ? profit / staked : null,
           winPct: (wins + losses) > 0 ? wins / (wins + losses) : null };
}

function mbByBook(bets) {
  const books = {};
  for (const b of bets) {
    const k = b.book || "Other";
    const s = books[k] || (books[k] = { staked: 0, profit: 0, n: 0, pending: 0 });
    s.n += 1;
    if (b.result === "pending") { s.pending += 1; continue; }
    s.staked += Number(b.stake) || 0;
    s.profit += mbProfit(b);
  }
  return books;
}

/* ---- The insights layer: what your own book says about you. --------
   Realized results only, grouped where the sample is real. This is the
   half of a bet tracker that actually changes behavior — the list
   remembers, the groups accuse. */

/* American odds cluster into four habits. +100 is a coin flip priced
   even, so it opens the dogs. */
const MB_BAND_ORDER = ["Heavy favorites", "Favorites", "Small dogs",
                       "Longshots"];
function mbBand(odds) {
  const o = Number(odds);
  if (!o || isNaN(o)) return null;
  if (o <= -200) return "Heavy favorites";
  if (o < 0) return "Favorites";
  if (o < 200) return "Small dogs";
  return "Longshots";
}

/* Settled-only rollup by any labeller. Pushes ride in staked/profit
   (they cost nothing, they decide nothing) but not in the record. */
function mbGroup(bets, keyFn) {
  const out = {};
  for (const b of bets) {
    if (!["win", "loss", "push"].includes(b.result)) continue;
    const k = keyFn(b);
    if (!k) continue;
    const s = out[k] || (out[k] = { n: 0, wins: 0, losses: 0,
                                    staked: 0, profit: 0 });
    s.n += 1;
    if (b.result === "win") s.wins += 1;
    else if (b.result === "loss") s.losses += 1;
    s.staked += Number(b.stake) || 0;
    s.profit += mbProfit(b);
  }
  return out;
}

/* Cumulative P&L in date order — the bankroll curve. */
function mbCurve(bets) {
  const settled = bets.filter((b) =>
    ["win", "loss", "push"].includes(b.result))
    .slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  let run = 0;
  return settled.map((b) => ({ date: b.date || "",
                               pnl: (run += mbProfit(b)) }));
}

/* One-line reads, each gated on a real sample so the page never
   accuses a habit off six bets. At most three — a wall of verdicts
   reads like a horoscope. */
const MB_READ_MIN = 10;
function mbTakeaways(bets) {
  const takes = [];
  const dec = (s) => s.wins + s.losses;
  const bands = mbGroup(bets, (b) => mbBand(b.odds));
  let leak = null;
  for (const k of Object.keys(bands)) {
    const s = bands[k];
    if (dec(s) < MB_READ_MIN || s.staked <= 0) continue;
    const roi = s.profit / s.staked;
    if (roi < -0.10 && (!leak || roi < leak.roi)) leak = { k, s, roi };
  }
  if (leak) takes.push(`${leak.k} are the leak: `
    + `${mbMoney(leak.s.profit, true)} on ${mbMoney(leak.s.staked)} staked `
    + `(−${Math.abs(100 * leak.roi).toFixed(0)}% ROI).`);
  const sports = mbGroup(bets, (b) => b.sport || null);
  let carry = null;
  for (const k of Object.keys(sports)) {
    const s = sports[k];
    if (dec(s) < MB_READ_MIN || s.staked <= 0) continue;
    const roi = s.profit / s.staked;
    if (roi > 0.05 && (!carry || roi > carry.roi)) carry = { k, s, roi };
  }
  if (carry) takes.push(`${carry.k} is carrying you: `
    + `${mbMoney(carry.s.profit, true)} at +${(100 * carry.roi).toFixed(0)}% ROI.`);
  // Flat-stake break-even at YOUR average odds vs the rate you hit.
  const decided = bets.filter((b) => b.result === "win" || b.result === "loss");
  const priced = decided.filter((b) => mbDecimal(b.odds) != null);
  if (priced.length >= 2 * MB_READ_MIN) {
    const be = priced.reduce((s, b) => s + 1 / mbDecimal(b.odds), 0)
      / priced.length;
    const hit = decided.filter((b) => b.result === "win").length
      / decided.length;
    if (hit < be - 0.03) takes.push(`At your average odds you need `
      + `${(100 * be).toFixed(0)}% winners to break even — you’re hitting `
      + `${(100 * hit).toFixed(0)}%.`);
    else if (hit > be + 0.03) takes.push(`You’re beating your break-even: `
      + `${(100 * hit).toFixed(0)}% winners where `
      + `${(100 * be).toFixed(0)}% pays the freight.`);
  }
  const wins = decided.filter((b) => b.result === "win");
  const losses = decided.filter((b) => b.result === "loss");
  if (wins.length >= MB_READ_MIN && losses.length >= MB_READ_MIN) {
    const avg = (a) => a.reduce((s, b) => s + (Number(b.stake) || 0), 0)
      / a.length;
    const wAvg = avg(wins), lAvg = avg(losses);
    if (lAvg > wAvg * 1.25) takes.push(`You bet bigger on your losers — `
      + `${mbMoney(lAvg)} average on losses vs ${mbMoney(wAvg)} on wins.`);
  }
  return takes.slice(0, 3);
}

/* Mutations. Global because the page rebuilds its own innerHTML, so a
   captured closure would go stale on the first re-render. */
window.mbAdd = function () {
  const g = (id) => (document.getElementById(id) || {}).value || "";
  const stake = parseFloat(g("mb-stake"));
  const odds = parseInt(g("mb-odds"), 10);
  const desc = g("mb-desc").trim();
  const warn = document.getElementById("mb-form-warn");
  if (!desc || !stake || isNaN(stake) || stake <= 0 || !odds || isNaN(odds)) {
    if (warn) warn.textContent =
      "Need at least a description, a stake over $0, and American odds (e.g. −110).";
    return;
  }
  const bets = mbLoad();
  bets.push({
    id: Date.now() + "" + Math.floor(Math.random() * 1e4),
    book: g("mb-book") || "Other", sport: g("mb-sport") || "",
    date: g("mb-date") || new Date().toISOString().slice(0, 10),
    desc, stake, odds, result: "pending",
  });
  mbSave(bets);
  renderMyBets();
};
window.mbResult = function (id, result) {
  const bets = mbLoad();
  const b = bets.find((x) => x.id === id);
  if (b) { b.result = result; mbSave(bets); renderMyBets(); }
};
window.mbDelete = function (id) {
  const bets = mbLoad();
  const gone = bets.find((x) => x.id === id);
  if (gone) {
    // A deletion has to TRAVEL: without a tombstone, the account merge
    // (a union, so a device race can never lose a bet) would politely
    // resurrect this bet from whichever device still holds it.
    try {
      const dels = acctDeleted();
      dels.push(mbSig(gone));
      localStorage.setItem(ACCT_DEL_KEY, JSON.stringify(dels.slice(-500)));
    } catch (e) {}
  }
  mbSave(bets.filter((x) => x.id !== id));
  renderMyBets();
};
window.mbExport = function () {
  const blob = new Blob([JSON.stringify(mbLoad(), null, 1)],
                        { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "my-bets-" + new Date().toISOString().slice(0, 10) + ".json";
  a.click();
  URL.revokeObjectURL(a.href);
};
window.mbImport = function (input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const arr = JSON.parse(reader.result);
      if (!Array.isArray(arr)) throw new Error("not a list");
      // Merge by id, so importing a backup does not wipe newer entries.
      const have = new Set(mbLoad().map((b) => b.id));
      const merged = mbLoad().concat(arr.filter((b) => b && !have.has(b.id)));
      mbSave(merged);
      renderMyBets();
    } catch (e) {
      const warn = document.getElementById("mb-form-warn");
      if (warn) warn.textContent = "That file was not a My Bets export.";
    }
  };
  reader.readAsText(file);
};

function mbMoney(v, sign) {
  const n = Number(v) || 0;
  const s = "$" + Math.abs(n).toFixed(2);
  if (!sign) return s;
  return n > 0 ? "+" + s : n < 0 ? "−" + s : s;
}

/* ------------------------------------------------------------------
   Bulk import — the free version of Juice Reel's sync.

   Juice Reel auto-pulls bets by holding sportsbook credentials through
   an aggregator (SharpSports). The zero-cost, zero-credential version
   of the same outcome: every book — and Juice Reel itself — exports bet
   history as a CSV, and this reads one. Columns are matched by HEADER
   NAME, never by position (the espnhoops rule: order is not a promise
   anyone made us), the parse is previewed before anything commits, and
   a signature-dedupe means re-importing last month's export cannot
   double-count a single bet. All pure functions up to the preview, so
   the tests run the SHIPPED code under node. */
const MB_HEADERS = {
  date: ["date", "placed", "placed at", "date placed", "time placed",
         "bet date", "created", "created at", "settled at", "event date"],
  book: ["book", "sportsbook", "site", "operator", "bookmaker"],
  sport: ["sport", "league"],
  desc: ["bet", "description", "bet description", "selection", "pick",
         "wager", "name", "bet name", "event", "legs", "bet info"],
  odds: ["odds", "american odds", "price", "bet odds"],
  stake: ["stake", "risk", "risked", "wager amount", "amount",
          "bet amount", "stake amount", "risk amount"],
  result: ["result", "status", "outcome", "settlement", "win/loss",
           "won/lost", "grade"],
};

/* Quote-aware CSV/TSV split. Bet descriptions contain commas ("Judge
   o1.5 TB, live"), so a naive split corrupts exactly the rows this
   exists for. Delimiter is auto-detected from the header line: any tab
   means a spreadsheet paste, otherwise comma. */
function mbParseCSV(text) {
  const src = String(text || "");
  const head = src.slice(0, src.indexOf("\n") + 1 || src.length);
  const delim = head.includes("\t") ? "\t" : ",";
  const rows = [];
  let row = [], cell = "", q = false;
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (q) {
      if (c === '"') {
        if (src[i + 1] === '"') { cell += '"'; i++; } else q = false;
      } else cell += c;
    } else if (c === '"') q = true;
    else if (c === delim) { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && src[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      if (row.some((x) => String(x).trim())) rows.push(row);
      row = [];
    } else cell += c;
  }
  row.push(cell);
  if (row.some((x) => String(x).trim())) rows.push(row);
  return rows;
}

function mbMapHeaders(headerRow) {
  const norm = (s) => String(s || "").toLowerCase()
    .replace(/[$()._-]/g, " ").replace(/\s+/g, " ").trim();
  const map = { date: null, book: null, sport: null, desc: null,
                odds: null, stake: null, result: null };
  (headerRow || []).forEach((cell, i) => {
    const h = norm(cell);
    for (const field of Object.keys(MB_HEADERS)) {
      if (map[field] == null && MB_HEADERS[field].includes(h)) {
        map[field] = i;
        return;
      }
    }
  });
  return map;
}

/* Odds in the wild: "+150", "-110", "−110" (typographic minus from a
   pretty export), "EVEN", and decimal "1.91". American magnitude is
   always ≥100, so anything smaller WITH a decimal point is decimal odds
   and converts; a bare small integer is unreadable and the row says so
   rather than guessing. */
function mbParseOdds(s) {
  let t = String(s == null ? "" : s).trim().toLowerCase()
    .replace(/[,\s]/g, "").replace(/−/g, "-");
  if (!t) return null;
  if (t === "even" || t === "ev" || t === "evens" || t === "pk") return 100;
  const v = parseFloat(t);
  if (isNaN(v)) return null;
  if (Math.abs(v) >= 100) return Math.round(v);
  if (v > 1 && t.includes(".")) {
    return v >= 2 ? Math.round((v - 1) * 100) : -Math.round(100 / (v - 1));
  }
  return null;
}

function mbParseStake(s) {
  const v = parseFloat(String(s == null ? "" : s).replace(/[$,\s]/g, ""));
  return isNaN(v) ? null : v;
}

function mbParseDate(s) {
  const t = String(s || "").trim();
  if (!t) return null;
  const pad = (x) => String(x).padStart(2, "0");
  const iso = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (iso) return `${iso[1]}-${pad(iso[2])}-${pad(iso[3])}`;
  const us = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
  if (us) {
    const y = us[3].length === 2 ? "20" + us[3] : us[3];
    return `${y}-${pad(us[1])}-${pad(us[2])}`;
  }
  const d = new Date(t);
  return isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10);
}

/* "Void" pays back the stake — that is a push in this ledger. A cashout
   settled at some unknown partial value: grading it as a full win would
   invent profit, so it lands PENDING for the user to grade by hand. */
function mbNormResult(s) {
  const t = String(s || "").trim().toLowerCase();
  if (t.includes("cash")) return "pending";
  if (["win", "won", "w", "winner", "winning"].includes(t)) return "win";
  if (["loss", "lost", "lose", "l", "loser", "losing"].includes(t)) return "loss";
  if (["push", "void", "voided", "tie", "canceled", "cancelled",
       "refund", "refunded", "no action"].includes(t)) return "push";
  return "pending";
}

/* The identity of a bet for dedupe: same day, book, wording, stake and
   price IS the same bet — the id from an export run is not stable, so
   ids cannot be the key the way the JSON import uses them. */
function mbSig(b) {
  return [b.date, b.book, String(b.desc || "").toLowerCase().trim(),
          Number(b.stake), Number(b.odds)].join("|");
}

function mbRowsFromText(text, fallbackBook) {
  const rows = mbParseCSV(text);
  if (rows.length < 2) {
    return { bets: [], skipped: [{ line: 1, reason: "need a header row "
             + "plus at least one bet row" }], mapping: {} };
  }
  const map = mbMapHeaders(rows[0]);
  if (map.desc == null || map.stake == null || map.odds == null) {
    const missing = ["desc", "odds", "stake"].filter((k) => map[k] == null);
    return { bets: [], skipped: [{ line: 1, reason: "header row is missing "
             + `a recognizable ${missing.join(" + ")} column` }],
             mapping: map };
  }
  const today = new Date().toISOString().slice(0, 10);
  const bets = [], skipped = [];
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    const cell = (k) => map[k] == null ? "" : String(r[map[k]] == null ? "" : r[map[k]]).trim();
    const desc = cell("desc");
    if (!desc) { skipped.push({ line: i + 1, reason: "no bet description" }); continue; }
    const odds = mbParseOdds(cell("odds"));
    if (odds == null) {
      skipped.push({ line: i + 1, reason: `odds unreadable (${cell("odds") || "blank"})` });
      continue;
    }
    const stake = mbParseStake(cell("stake"));
    if (stake == null || stake <= 0) {
      skipped.push({ line: i + 1, reason: `stake unreadable (${cell("stake") || "blank"})` });
      continue;
    }
    bets.push({
      id: Date.now() + "" + i + Math.floor(Math.random() * 1e4),
      book: cell("book") || fallbackBook || "Other",
      sport: cell("sport").toUpperCase().slice(0, 12),
      date: mbParseDate(cell("date")) || today,
      desc: desc.slice(0, 90), stake, odds,
      result: map.result == null ? "pending" : mbNormResult(cell("result")),
    });
  }
  return { bets, skipped, mapping: map };
}

/* Parsed-but-not-committed rows between Preview and Add. */
let _mbPending = null;

window.mbBulkFile = function (input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => { mbBulkShow(String(reader.result)); input.value = ""; };
  reader.readAsText(file);
};
window.mbBulkPaste = function () {
  const ta = document.getElementById("mb-bulk-text");
  if (ta && ta.value.trim()) mbBulkShow(ta.value);
};
window.mbBulkCommit = function () {
  if (_mbPending && _mbPending.length) {
    mbSave(mbLoad().concat(_mbPending));
  }
  _mbPending = null;
  renderMyBets();
};

function mbBulkShow(text) {
  const box = document.getElementById("mb-bulk-preview");
  if (!box) return;
  const fallbackBook = (document.getElementById("mb-book") || {}).value || "Other";
  const parsed = mbRowsFromText(text, fallbackBook);
  const have = new Set(mbLoad().map(mbSig));
  const seen = new Set();
  const fresh = [], dupes = [];
  for (const b of parsed.bets) {
    const sig = mbSig(b);
    if (have.has(sig) || seen.has(sig)) dupes.push(b);
    else { seen.add(sig); fresh.push(b); }
  }
  _mbPending = fresh;
  const mapped = Object.keys(parsed.mapping || {})
    .filter((k) => parsed.mapping[k] != null);
  const sample = fresh.slice(0, 8).map((b) => `<tr>
      <td class="num">${escapeHtml(b.date)}</td>
      <td>${escapeHtml(b.book)}</td>
      <td>${escapeHtml(b.desc)}</td>
      <td class="num">${b.odds > 0 ? "+" : ""}${b.odds}</td>
      <td class="num">${mbMoney(b.stake)}</td>
      <td class="num">${escapeHtml(b.result)}</td>
    </tr>`).join("");
  box.innerHTML = `
    <div class="mb-bulk-summary">
      ${fresh.length} bet(s) ready to add
      ${dupes.length ? ` · ${dupes.length} duplicate(s) skipped (already logged)` : ""}
      ${parsed.skipped.length ? ` · ${parsed.skipped.length} row(s) unreadable` : ""}
      ${mapped.length ? `<span class="mb-bulk-cols">columns matched: ${mapped.join(", ")}</span>` : ""}
    </div>
    ${parsed.skipped.slice(0, 5).map((s) =>
      `<div class="mb-warn">row ${s.line}: ${escapeHtml(s.reason)}</div>`).join("")}
    ${fresh.length ? `
      <div class="card" style="padding:0;overflow-x:auto;margin:10px 0">
        <table class="agate"><thead><tr><th>Date</th><th>Book</th><th>Bet</th>
          <th>Odds</th><th>Stake</th><th>Result</th></tr></thead>
        <tbody>${sample}</tbody></table></div>
      ${fresh.length > 8 ? `<div class="mb-import-note">…and ${fresh.length - 8} more</div>` : ""}
      <button class="btn mb-add" type="button" onclick="mbBulkCommit()">
        Add ${fresh.length} bet(s)</button>`
    : `<div class="mb-import-note">Nothing new to add from that file.</div>`}`;
}

function renderMyBets() {
  const host = document.getElementById("mybets-body");
  if (!host) return;
  const acct = acctState();
  setStandaloneSource(acct ? `Account “${acct.name}” — synced through your own server`
                           : "Your device only — nothing is uploaded",
                      acct ? `My Bets · account ${acct.name}`
                           : "My Bets · local to this browser");
  const bets = mbLoad().slice().sort((a, b) =>
    (b.date || "").localeCompare(a.date || "") ||
    (b.id || "").localeCompare(a.id || ""));
  const st = mbStats(bets);
  const books = mbByBook(bets);
  const pcolor = (v) => v > 0 ? "var(--good)" : v < 0 ? "var(--bad)" : "var(--text-mute)";
  const tile = (k, v, sub, color) => `<div class="tile"><div class="k">${k}</div>
    <div class="v"${color ? ` style="color:${color}"` : ""}>${v}</div>${
      sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;

  const today = new Date().toISOString().slice(0, 10);
  const form = `
    <div class="card mb-form">
      <div class="mb-form-row">
        <label>Book<select id="mb-book">${MYBETS_BOOKS.map((b) =>
          `<option>${escapeHtml(b)}</option>`).join("")}</select></label>
        <label>Sport<select id="mb-sport">${
          ["", "NFL", "CFB", "MLB", "NBA", "WNBA", "UFC", "Other"].map((s) =>
          `<option value="${s}">${s || "—"}</option>`).join("")}</select></label>
        <label>Date<input id="mb-date" type="date" value="${today}"></label>
      </div>
      <div class="mb-form-row">
        <label class="mb-grow">Bet<input id="mb-desc" type="text" maxlength="90"
          placeholder="e.g. Yankees ML, or Judge Over 1.5 total bases"></label>
        <label>Stake $<input id="mb-stake" type="number" min="0" step="0.01"
          inputmode="decimal" placeholder="25"></label>
        <label>Odds<input id="mb-odds" type="number" step="1"
          inputmode="numeric" placeholder="-110"></label>
        <button class="btn mb-add" type="button" onclick="mbAdd()">Log bet</button>
      </div>
      <div id="mb-form-warn" class="mb-warn"></div>
    </div>`;

  const bookRows = Object.keys(books).sort((a, b) =>
    books[b].profit - books[a].profit).map((k) => {
    const s = books[k];
    return `<tr>
      <td>${escapeHtml(k)}</td>
      <td class="num">${s.n}</td>
      <td class="num">${mbMoney(s.staked)}</td>
      <td class="num" style="color:${pcolor(s.profit)};font-weight:700">${mbMoney(s.profit, true)}</td>
      <td class="num">${s.staked > 0 ? (100 * s.profit / s.staked).toFixed(1) + "%" : "—"}</td>
    </tr>`;
  }).join("");

  const resultTag = { win: ["WON", "var(--good)"], loss: ["LOST", "var(--bad)"],
                      push: ["PUSH", "var(--text-mute)"],
                      pending: ["OPEN", "var(--warn)"] };
  // Status chips + sport filter (Ethan's My Bets render, 2026-08-11).
  // "Open/Won/Lost" as top-level tabs, sports as a dropdown, and each
  // bet as a card with its stake and what it stands to return.
  const stF = window._mbStatus || "all";
  const spF = window._mbSport || "";
  const sportsSeen = [...new Set(bets.map((b) => b.sport).filter(Boolean))];
  const shown = bets.filter((b) =>
    (stF === "all" || (stF === "open" ? b.result === "pending" : b.result === stF))
    && (!spF || b.sport === spF));
  const chip = (val, label) => `<button class="mbc-chip ${stF === val ? "active" : ""}"
      onclick="window._mbStatus='${val}';renderMyBets()">${label}</button>`;
  const filterBar = bets.length ? `
    <div class="mbc-filters">
      <div class="mbc-chips">${chip("all", "All")}${chip("open", "Open")}${chip("win", "Won")}${chip("loss", "Lost")}${chip("push", "Push")}</div>
      ${sportsSeen.length > 1 ? `<select class="mbc-sport" onchange="window._mbSport=this.value;renderMyBets()">
        <option value="">All Sports</option>${sportsSeen.map((s) =>
          `<option${s === spF ? " selected" : ""}>${escapeHtml(s)}</option>`).join("")}</select>` : ""}
    </div>` : "";
  // What a pending bet stands to return — plain American-odds arithmetic
  // on the user's own stake and price, never a projection.
  const mbToWin = (b) => !b.odds || !b.stake ? 0
    : (b.odds > 0 ? b.stake * b.odds / 100 : b.stake * 100 / Math.abs(b.odds));
  const card = (b) => {
    const [label, color] = resultTag[b.result] || resultTag.pending;
    const legs = (b.desc || "").includes(" + ") ? (b.desc || "").split(" + ") : null;
    const actions = b.result === "pending"
      ? `<button class="mb-act win" onclick="mbResult('${b.id}','win')">Win</button>
         <button class="mb-act loss" onclick="mbResult('${b.id}','loss')">Loss</button>
         <button class="mb-act push" onclick="mbResult('${b.id}','push')">Push</button>`
      : `<button class="mb-act undo" onclick="mbResult('${b.id}','pending')">Reopen</button>`;
    const outcome = b.result === "pending"
      ? `To win <b>${mbMoney(mbToWin(b))}</b>`
      : `<b style="color:${pcolor(mbProfit(b))}">${mbMoney(mbProfit(b), true)}</b>`;
    return `<article class="mbc ${b.result === "pending" ? "open" : escapeHtml(b.result)}">
      <div class="mbc-head">
        <span class="mbc-title">${legs ? `${legs.length}-leg parlay` : escapeHtml(b.desc || "")}</span>
        <b class="mbc-odds">${b.odds > 0 ? "+" : ""}${escapeHtml(String(b.odds ?? ""))}</b>
        <b class="mbc-tag" style="color:${color}">${label}</b></div>
      ${legs ? `<ul class="mbc-legs">${legs.map((l) =>
        `<li>${escapeHtml(l)}</li>`).join("")}</ul>` : ""}
      <div class="mbc-sub">${escapeHtml(b.book || "")}${b.sport ? ` · ${escapeHtml(b.sport)}` : ""} · ${escapeHtml(b.date || "")}</div>
      <div class="mbc-foot"><span class="mbc-stake">${mbMoney(b.stake)} staked</span>
        <span class="mbc-outcome">${outcome}</span>
        <span class="mb-actions">${actions}
          <button class="mb-act del" title="Delete this bet" aria-label="Delete"
            onclick="mbDelete('${b.id}')">${icon("cross", 12)}</button></span></div>
    </article>`;
  };

  host.innerHTML = `
    <div class="card mb-safety">
      <b>No sportsbook passwords, ever.</b> Sportsbooks don’t offer a login for apps, so the
      only way to pull your account automatically would be to store your DraftKings or FanDuel
      password and scrape it — against their terms, and a risk to your account and your money.
      So you log bets here yourself. A <b>Qellys</b> account is a different thing: it is ours,
      you can change or delete it whenever you like, and it is what carries this log to your
      other devices.
    </div>
    ${acctStripHTML()}
    ${form}
    <details class="card mb-import">
      <summary>Bulk import — a CSV from your sportsbook, or a Juice Reel export</summary>
      <p class="mb-import-note">The free version of bet syncing: every book (and Juice
      Reel itself) can export your bet history as a spreadsheet/CSV. Choose the file or
      paste the rows — columns are matched by their header names (date, bet, odds,
      stake/risk, result…), in any order. Rows without a book column are filed under the
      Book selected in the form above. Re-importing the same export is safe: bets you
      already logged are skipped, not doubled. Nothing uploads.</p>
      <div class="mb-form-row">
        <label class="btn mb-io" style="cursor:pointer">Choose CSV<input type="file"
          accept=".csv,.txt,.tsv,text/csv,text/plain,text/tab-separated-values"
          style="display:none" onchange="mbBulkFile(this)"></label>
        <span style="color:var(--text-mute);font-size:var(--fs-sm)">or paste rows below,
          then Preview:</span>
      </div>
      <textarea id="mb-bulk-text" rows="4" spellcheck="false"
        placeholder="Date,Bet,Odds,Risk,Result&#10;2026-08-09,Yankees ML,-125,25,Won"></textarea>
      <div class="mb-form-row">
        <button class="btn" type="button" onclick="mbBulkPaste()">Preview</button>
      </div>
      <div id="mb-bulk-preview"></div>
    </details>
    <div class="stats">
      ${tile("Net profit", mbMoney(st.profit, true), `${st.settled} settled bet(s)`, pcolor(st.profit))}
      ${tile("ROI", st.roi == null ? "—" : (100 * st.roi).toFixed(1) + "%", "profit ÷ staked")}
      ${tile("Record", `${st.wins}–${st.losses}${st.pushes ? `–${st.pushes}` : ""}`,
             st.winPct == null ? "no decisions yet" : (100 * st.winPct).toFixed(0) + "% win")}
      ${tile("At risk", mbMoney(st.atRisk), `${st.pending} pending`)}
    </div>
    ${(() => {
      if (st.settled < 3) return "";
      const takes = mbTakeaways(bets);
      const curve = mbCurve(bets);
      const groupTable = (g, order) => {
        const keys = (order || Object.keys(g).sort((a, b) =>
          g[b].profit - g[a].profit)).filter((k) => g[k] && g[k].n);
        if (keys.length < 2) return "";
        return `<div class="card" style="padding:0;overflow-x:auto;margin-bottom:14px">
          <table class="agate"><thead><tr><th></th><th>Bets</th><th>Record</th>
            <th>Staked</th><th>Profit</th><th>ROI</th></tr></thead><tbody>
          ${keys.map((k) => { const s = g[k]; return `<tr>
            <td>${escapeHtml(k)}</td><td class="num">${s.n}</td>
            <td class="num">${s.wins}–${s.losses}</td>
            <td class="num">${mbMoney(s.staked)}</td>
            <td class="num" style="color:${pcolor(s.profit)};font-weight:700">${mbMoney(s.profit, true)}</td>
            <td class="num">${s.staked > 0 ? (100 * s.profit / s.staked).toFixed(1) + "%" : "—"}</td>
          </tr>`; }).join("")}</tbody></table></div>`;
      };
      const last = curve.length ? curve[curve.length - 1].pnl : 0;
      const spark = curve.length >= 2 ? `<div class="card" style="margin-bottom:14px">
        <div class="ffd-h">Bankroll curve</div>
        <div class="gloss-chart" data-gloss-curve="${escapeAttr(JSON.stringify({
          values: curve.map((p) => p.pnl), labels: curve.map((p) => p.date),
          tone: last >= 0 ? "up" : "down", money: true, h: 110,
        }))}">${sparkline(curve.map((p) => p.pnl).reverse(),
          { w: 360, h: 84, line: 0,
            stroke: last >= 0 ? "var(--good)" : "var(--bad)" })}</div>
        <p class="ffd-note" style="margin:4px 0 0">Cumulative P&L over your
          ${curve.length} settled bets, oldest to newest — the flat line is
          break-even.</p></div>` : "";
      return `
        <div class="section-title">What your book says about you
          <span class="sub">— realized results only; the one-line reads wait for
          ${MB_READ_MIN} decided bets in a group before claiming anything.</span></div>
        ${takes.length ? `<div class="card mb-takes"><ul>
          ${takes.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul></div>` : ""}
        ${spark}
        ${groupTable(mbGroup(bets, (b) => b.sport || null))}
        ${groupTable(mbGroup(bets, (b) => mbBand(b.odds)), MB_BAND_ORDER)}`;
    })()}
    ${bets.length ? `
    <div class="section-title">By book
      <span class="sub">— your realized P&L at each sportsbook, best first.</span></div>
    <div class="card" style="padding:0;overflow-x:auto">
      <table class="agate"><thead><tr><th>Book</th><th>Bets</th><th>Staked</th>
        <th>Profit</th><th>ROI</th></tr></thead><tbody>${bookRows}</tbody></table></div>
    <div class="section-title">Every bet
      <span class="sub">— newest first. Tap Win/Loss/Push when a bet settles; the totals
      update as you go.</span>
      <span style="float:right;font-size:var(--fs-sm)">
        <button class="btn mb-io" type="button" onclick="mbExport()">Export</button>
        <label class="btn mb-io" style="cursor:pointer">Import<input type="file"
          accept="application/json" style="display:none" onchange="mbImport(this)"></label>
      </span></div>
    ${filterBar}
    <div class="mbc-list">${shown.map(card).join("")
      || `<p class="rail-quiet" style="margin:4px 0 18px">Nothing matches this filter.</p>`}</div>`
    : `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
        <div class="es-title">No bets logged yet</div>
        <div class="es-sub">Add the first bet you placed at a book above. It stays on this
        device, tracks your P&L by book, and is separate from the model’s own record.</div></div>`}
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">
      This is a manual log for the bets YOU place — not the model’s picks (those are on the
      Record page) and not gambling advice. Data lives only in this browser; clearing your
      browser data erases it, so Export now and then if you want a backup.</p>`;
  if (typeof mountGlossCharts === "function") mountGlossCharts(host);
}

/* Weather — the Zeno sidebar's page (Ethan, 2026-08-12), built from
   numbers we already price with: each game's slate weather, plus the
   prediction desk's NWS-vs-Kalshi rows when those markets are live.
   Hidden for leagues with no weather feed — a page that can only say
   "indoor" is worse than no page. */
function renderWeather() {
  const host = document.getElementById("weather-body");
  if (!host) return;
  const games = ((state.data || {}).games || []).filter((g) => g.weather);
  const row = (g) => {
    const w = g.weather || {};
    const windy = !w.dome && (w.wind_mph || 0) >= 12;
    const chips = w.dome
      ? `<span class="chip books">${icon("stadium")} Dome — weather can’t reach it</span>`
      : [`<span class="chip">${Math.round(w.temp_f)}&deg;F</span>`,
         `<span class="chip ${windy ? "down" : ""}">${Math.round(w.wind_mph || 0)}mph${w.wind_dir ? " " + escapeHtml(w.wind_dir) : ""}${windy ? " — moves totals" : ""}</span>`,
         (w.precip_chance || 0) >= 0.2
           ? `<span class="chip">${Math.round(w.precip_chance * 100)}% precip</span>` : "",
        ].join("");
    return `<div class="wx-row" data-gid="${escapeHtml(gameId(g))}">
      <span class="wx-teams">${teamMark(g.away, 20)} ${escapeHtml(g.away)}
        <em>@</em> ${teamMark(g.home, 20)} ${escapeHtml(g.home)}</span>
      <span class="wx-park">${escapeHtml(g.park_name || (g.stadium || {}).name || "")}</span>
      <span class="wx-chips chips">${chips}</span>
    </div>`;
  };
  const deskWx = ((_railDeskCache || {}).weather || []);
  const deskRows = deskWx.length ? `
    <div class="section-title">The desk’s forecast board
      <span class="sub">— NWS daily highs priced against Kalshi’s brackets. Rows that clear
      the 8-point bar are the desk’s paper recommendations.</span></div>
    <div class="card kx-table" style="padding:0">${deskWx.slice(0, 10).map((r) => `
      <div class="kx-row">
        <span class="kx-sport chip">${escapeHtml(r.city || "")}</span>
        <span class="kx-title">${escapeHtml(r.subtitle || r.title)} · ${escapeHtml(r.date)}
          ${r.rec && r.rec_side ? `<span class="chip ${r.rec_side === "YES" ? "up" : "down"}">${escapeHtml(r.rec_side)}</span>` : ""}</span>
        <span class="kx-num">NWS ${r.forecast_f}&deg;</span>
        <span class="kx-num">${(r.prob * 100).toFixed(0)}&cent;</span>
        <span class="kx-num kx-e"><span style="color:var(--${r.edge_pts > 0 ? "good" : "bad"})">${r.edge_pts > 0 ? "+" : ""}${r.edge_pts}</span></span>
      </div>`).join("")}</div>` : "";
  host.innerHTML = (games.length ? `<div class="card" style="padding:0">
      ${games.map(row).join("")}</div>` :
    `<div class="empty-slate"><div class="es-icon">${icon("cloud", 30)}</div>
      <div class="es-title">No conditions to report</div>
      <div class="es-sub">The slate carries a weather reading for every outdoor game once
      it builds — check back when tonight’s board is up.</div></div>`) + deskRows;
  host.querySelectorAll(".wx-row").forEach((el) =>
    el.addEventListener("click", () => openGame(el.dataset.gid)));
  renderRailDesk();          // warms the cache the forecast board reads
}

/* Alerts — a DIGEST, deliberately: what changed on the data we already
   hold (line moves, the injury watch, the desk), rebuilt each refresh.
   Not a push service, and the page says so instead of pretending. */
let _alFilter = "all";
window._alSet = (k) => { _alFilter = k; renderAlerts(); };

function renderAlerts() {
  const host = document.getElementById("alerts-body");
  if (!host) return;
  const d = state.data || {};
  // Render 14's list: an icon chip, the alert on one line, the CONDITION
  // that fired it underneath. What never crosses is the render's per-row
  // toggle and "Create New Alert" — this page is a digest of feeds we
  // already hold, not a subscription service, and a switch that turns
  // nothing on would be a lie you can click.
  const alRow = (ic, tone, title, cond, right) => `
    <div class="al-row">
      <span class="al-ic ${tone}">${icon(ic, 15)}</span>
      <span class="al-t"><b>${title}</b><span class="al-c">${cond}</span></span>
      ${right || ""}
    </div>`;
  const moved = (d.recommendations || []).filter((r) =>
    r.move_delta != null && (Math.abs(r.move_delta) >= 0.5 || r.move_steam));
  const inj = (d.injury_watch || []).filter((i) => i && i.player);
  const k = _railDeskCache || {};
  const recs = [...(k.rows || []).filter((r) => r.rec),
                ...(k.weather || []).filter((r) => r.rec)];
  const cats = [["all", "All alerts", moved.length + inj.length + recs.length],
                ["moves", "Line moves", moved.length],
                ["injuries", "Injuries", inj.length],
                ["desk", "The desk", recs.length]];
  if (!cats.some(([kk, , n]) => kk === _alFilter && n)) _alFilter = "all";
  const chips = `<div class="al-cats">${cats.filter(([kk, , n]) => n || kk === "all")
    .map(([kk, label, n]) => `<button class="al-cat${kk === _alFilter ? " on" : ""}"
      type="button" onclick="_alSet('${kk}')">${escapeHtml(label)}
      <span class="al-n">${n}</span></button>`).join("")}</div>`;
  const show = (kk) => _alFilter === "all" || _alFilter === kk;
  const sections = [];
  if (moved.length && show("moves")) {
    sections.push(`<div class="section-title">Line movement
        <span class="sub">— tonight’s picks whose line has moved since open. Steam =
        several books moved together, which is the market talking.</span></div>
      <div class="card al-list">${moved.slice(0, 12).map((r) => alRow(
        r.move_delta > 0 ? "rising" : "falling",
        r.move_delta > 0 ? "good" : "bad",
        `${escapeHtml(r.player)} ${escapeHtml(r.side || "")} ${r.line}`,
        `${escapeHtml(r.market_label || r.market || "")} moved
         ${r.move_delta > 0 ? "+" : ""}${r.move_delta} since open`,
        `<span class="kx-num" style="color:var(--${r.move_delta > 0 ? "good" : "bad"})">
           ${r.move_delta > 0 ? "+" : ""}${r.move_delta}</span>${r.move_steam
          ? `<span class="chip down">steam</span>` : ""}`)).join("")}</div>`);
  }
  if (inj.length && show("injuries")) {
    sections.push(`<div class="section-title">Injury watch
        <span class="sub">— designations touching tonight’s board.
        <a href="#injuries">Full report &#8594;</a></span></div>
      <div class="card al-list">${inj.slice(0, 12).map((i) => alRow(
        "warn", "warn", escapeHtml(i.player),
        `${i.team ? escapeHtml(i.team) + " · " : ""}on tonight’s board with a designation`,
        `<span class="chip down">${escapeHtml(i.status || "")}</span>`)).join("")}</div>`);
  }
  if (recs.length && show("desk")) {
    sections.push(`<div class="section-title">The desk
        <span class="sub">— paper recommendations live right now.
        <a href="#intel">The full board &#8594;</a></span></div>
      <div class="card al-list">${recs.slice(0, 6).map((r) => alRow(
        "gem", "brand", escapeHtml(r.title),
        `cleared the desk’s gate at ${(r.prob * 100).toFixed(0)}¢`,
        `${r.rec_side ? `<span class="chip ${r.rec_side === "YES" ? "up" : "down"}">${escapeHtml(r.rec_side)}</span>` : ""}
         <span class="kx-num">${(r.prob * 100).toFixed(0)}&cent;</span>`)).join("")}</div>`);
  }
  host.innerHTML = (moved.length + inj.length + recs.length ? chips : "")
    + (sections.join("") || `<div class="empty-slate">
      <div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">Nothing moving right now</div>
      <div class="es-sub">Alerts fill from three real feeds — line movement on tonight’s
      picks, the injury watch, and the prediction desk. A quiet page means a quiet
      slate, not a broken one.</div></div>`);
  renderRailDesk();
}

/* Bankroll page extras (Ethan's desktop render, 2026-08-11): the goal
   bar and the balance-over-time chart — read entirely from the user's
   own sizing input and My Bets log. No held balance exists anywhere. */
function renderBankrollExtras() {
  const host = document.getElementById("bk-journal");
  if (!host) return;
  const goal = parseFloat(localStorage.getItem("qb_bk_goal")) || 0;
  const bank = state.bankroll || 0;
  const pct = goal > 0 && bank > 0 ? Math.min(100, 100 * bank / goal) : 0;
  const settled = mbLoad()
    .filter((b) => b.result && b.result !== "pending" && b.date)
    .sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  let curveHTML = "";
  if (settled.length > 1) {
    let cum = 0;
    const ys = settled.map((b) => { cum = +(cum + mbProfit(b)).toFixed(2); return cum; });
    const lo = Math.min(0, ...ys), hi = Math.max(0, ...ys), span = (hi - lo) || 1;
    const W = 560, H = 110;
    const xy = ys.map((y, i) => [
      +(i / (ys.length - 1) * W).toFixed(1),
      +(H - 10 - (y - lo) / span * (H - 20)).toFixed(1)]);
    const up = ys[ys.length - 1] >= 0;
    const tone = up ? "var(--good)" : "var(--bad)";
    const hex = up ? "#42C268" : "#DF5953";
    const gid = `bkfill${Math.random().toString(36).slice(2, 8)}`;
    curveHTML = `
      <div class="card bk-curve">
        <div class="gp-panel-title">Your logged P&amp;L over time
          <span class="gp-panel-sub">— every settled bet in your My Bets log</span></div>
        <div class="bk-curve-net" style="color:${tone}">${mbMoney(ys[ys.length - 1], true)}</div>
        <div class="gloss-chart" data-gloss-curve="${escapeAttr(JSON.stringify({
          values: ys,
          labels: settled.map((b) => `${b.date || ""} · ${b.desc || ""}`.trim()),
          tone: up ? "up" : "down", money: true, h: 120,
        }))}"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:auto;display:block" aria-hidden="true"
          data-scrub="${escapeAttr(JSON.stringify({
            l: settled.map((b) => `${b.date || ""} · ${b.player || b.bet || ""}`.trim()),
            v: ys.map((y) => mbMoney(y, true)),
          }))}">
          <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${hex}" stop-opacity="0.26"/>
            <stop offset="100%" stop-color="${hex}" stop-opacity="0"/>
          </linearGradient></defs>
          <path d="M0,${H} L${xy.map(([x, y]) => `${x},${y}`).join(" L")} L${W},${H} Z" fill="url(#${gid})"/>
          <polyline points="${xy.map(([x, y]) => `${x},${y}`).join(" ")}" fill="none"
            stroke="${tone}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
        </svg></div>
        <div class="bk-curve-span"><span>${escapeHtml(settled[0].date)}</span>
          <span>${escapeHtml(settled[settled.length - 1].date)}</span></div>
      </div>`;
  }
  host.innerHTML = `
    <div class="card bk-goal">
      <div class="gp-panel-title">Bankroll goal</div>
      <div class="bk-goal-row"><span class="pfx">$</span>
        <input id="bk-goal-in" type="number" min="0" step="50" placeholder="5000"
          inputmode="numeric" value="${goal || ""}">
        <span class="bk-goal-pct">${goal > 0 && bank > 0 ? pct.toFixed(0) + "%" : "—"}</span></div>
      <div class="bk-goal-bar"><i style="width:${pct}%"></i></div>
      <p class="bk-note">${goal > 0
        ? (bank > 0
          ? "Your bankroll above measured against your goal — arithmetic on your own two numbers."
          : "Enter your bankroll above and this bar measures it against your goal.")
        : "Set a number to measure your bankroll against. Stored in this browser."}</p>
    </div>
    ${curveHTML}`;
  if (typeof mountGlossCharts === "function") mountGlossCharts(host);
  const inp = document.getElementById("bk-goal-in");
  if (inp) inp.addEventListener("change", () => {
    localStorage.setItem("qb_bk_goal", inp.value || "0");
    renderBankrollExtras();
  });
}

/* ============================================================
   ROCKET RADAR — Solana meme coins, the danger channel drawn loudest
   ============================================================
   The build spec's own base rates are the most important thing on the
   page, so they render FIRST, above every score: ~1.4% graduate, 60% of
   traders lose, 82.8% of high-return tokens show artificial growth,
   41% of volume is wash, the median rug dies inside an hour. The page's
   honest value is FILTERING, not prophecy — which is why momentum and
   risk are two numbers that never blend, risk is a GATE, and nothing
   here journals a bet or touches the sports ledger.

   Token names, symbols and URLs are attacker-controlled strings — a
   token can be NAMED an HTML payload — so everything from the feed goes
   through escapeHtml and links render only for https URLs. */
const MC_BASE_RATES = [
  ["~1.4%", "of pump.fun tokens ever graduate to a real DEX listing"],
  ["60%", "of meme-coin traders lose money; ~3% ever clear $1,000"],
  ["82.8%", "of high-return tokens show evidence of artificial growth"],
  ["41.4%", "of Solana meme-coin volume is wash trading (VanEck)"],
  ["<1 hour", "median lifecycle of a rug pull; median hold is ~62 seconds"],
];

function mcMoney(v) {
  if (v == null || isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${Number(v).toFixed(0)}`;
}

function mcPrice(v) {
  if (v == null || isNaN(v)) return "—";
  return v >= 1 ? `$${v.toFixed(2)}` : `$${Number(v).toPrecision(3)}`;
}

function mcAge(min) {
  if (min == null || isNaN(min)) return "—";
  if (min < 1) return "<1m";
  if (min < 90) return `${Math.round(min)}m`;
  if (min < 48 * 60) return `${(min / 60).toFixed(1)}h`;
  return `${(min / 1440).toFixed(1)}d`;
}

function mcPct(v) {
  if (v == null || isNaN(v)) return `<span style="opacity:.45">—</span>`;
  const c = v > 0 ? "var(--good)" : v < 0 ? "var(--bad)" : "var(--text-mute)";
  return `<span style="color:${c};font-weight:600">${v > 0 ? "+" : ""}${v.toFixed(1)}%</span>`;
}

/* Price over our own snapshot tape — honest resolution (one point per
   launcher refresh, up to 6h), self-contained, no external bytes. The
   LIVE candle chart is the venue's own embed, opened per coin below. */
function mcSpark(series, w = 300, h = 44) {
  const pts = (series || []).filter((p) => p && p[1] != null);
  if (pts.length < 2) return "";
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = (t) => x1 === x0 ? 0 : ((t - x0) / (x1 - x0)) * (w - 2) + 1;
  const sy = (v) => y1 === y0 ? h / 2 : h - 3 - ((v - y0) / (y1 - y0)) * (h - 6);
  const d = pts.map((p) => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");
  const up = ys[ys.length - 1] >= ys[0];
  // Snapshots land one per refresh, not on a grid — the scrub data
  // carries each point's own x fraction so the finger snaps to real
  // points instead of an even spacing that doesn't exist.
  const fmtP = (v) => "$" + (v >= 1 ? v.toFixed(2)
    : v >= 0.01 ? v.toFixed(4) : Number(v).toPrecision(3));
  const scrub = escapeAttr(JSON.stringify({
    x: pts.map((p) => x1 === x0 ? 0 : (p[0] - x0) / (x1 - x0)),
    l: pts.map((p) => new Date(p[0]).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })),
    v: pts.map((p) => fmtP(p[1])),
  }));
  return `<svg class="mc-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"
    role="img" aria-label="price over our snapshot tape" data-scrub="${scrub}"><polyline points="${d}"
    fill="none" stroke="var(--${up ? "good" : "bad"})" stroke-width="1.5"/></svg>`;
}

/* Addresses come from third-party feeds and end up inside an onclick and
   an iframe src — nothing that fails the base58 shape gets either. */
const MC_B58 = /^[1-9A-HJ-NP-Za-km-z]{25,50}$/;

function mcChartRef(c) {
  if (c.pair && MC_B58.test(c.pair)) return { addr: c.pair, kind: "ds" };
  if (c.pool && MC_B58.test(c.pool)) return { addr: c.pool, kind: "gt" };
  return null;
}

//: The rendered board, keyed by mint, so a chart click carries one
//: validated token id instead of a bag of strings through an onclick.
let _mcCoins = {};
//: The coin whose chart is open, surviving re-renders: the board
//: self-refreshes every few seconds and losing your coin to a data
//: tick would make the terminal unusable.
let _mcOpenMint = null;

function mcChartBtn(c, cls) {
  if (!mcChartRef(c) || !MC_B58.test(c.mint || "")) return "";
  return `<button class="${cls || "btn mc-chart-btn"}" type="button"
    onclick="mcShowChart('${c.mint}')"
    title="Open the venue’s own live candle chart for this pool">Live chart</button>`;
}

/* ONE chart at a time, in the terminal room. Sixty live iframes is a
   tab-killer; one, where you asked for it, is a terminal. The embed is
   the venue's own page for the pool, so the candles are as live as
   Axiom's — they come from the same place. Called from a card or the
   board table it also walks you to the Charts room, because a chart
   opening in a hidden panel is a click that did nothing. */
window.mcShowChart = function (mint, scroll = true) {
  const c = _mcCoins[mint];
  const dock = document.getElementById("mc-chart-dock");
  if (!c || !dock) return;
  const ref = mcChartRef(c);
  if (!ref || !MC_B58.test(ref.addr || "")) return;
  _mcOpenMint = mint;
  const src = ref.kind === "gt"
    ? `https://www.geckoterminal.com/solana/pools/${ref.addr}?embed=1&info=0&swaps=0`
    : `https://dexscreener.com/solana/${ref.addr}?embed=1&theme=dark&info=0`;
  const i = c.ind || {};
  const stat = (k, v, color) => `<div class="metric"><div class="k">${k}</div>
    <div class="v"${color ? ` style="color:${color}"` : ""}>${v}</div></div>`;
  // ONE header line: name, the five numbers, momentum/risk — everything
  // above the candles is height taken from the candles.
  dock.innerHTML = `<div class="card mc-chart-card">
    <div class="card-head mc-dock-head"><div class="player mc-dock-id">${mcTile(c, 30)}${mcName(c)}
      <span style="color:var(--text-mute);font-weight:400"> — live from ${
        ref.kind === "gt" ? "GeckoTerminal" : "DexScreener"}</span></div>
      <div class="metrics mc-dock-stats">
        ${stat("Price", mcPrice(c.price_usd))}
        ${stat("5m", mcPct((c.price_change || {}).m5))}
        ${stat("1h", mcPct((c.price_change || {}).h1))}
        ${stat("Liq", mcMoney(c.liquidity))}
        ${stat("Top 10", i.top10_share != null ? (i.top10_share * 100).toFixed(0) + "%" : "—")}
      </div>
      <span title="MomentumScore / RiskScore" style="font-weight:800">
        <span style="color:var(--brand)">${c.momentum}</span>
        <span style="color:var(--text-mute)"> / </span>
        <span style="color:${c.risk >= 60 ? "var(--bad)" : "var(--warn)"}">${c.risk}</span></span></div>
    <iframe src="${src}" loading="lazy" title="Live pool chart"
      referrerpolicy="no-referrer" allow="clipboard-write"></iframe></div>`;
  document.querySelectorAll("#view-memes .mc-pick").forEach((b) =>
    b.classList.toggle("active", b.dataset.mint === mint));
  const panel = dock.closest(".subgroup");
  if (panel && panel.hidden) {
    const tab = document.querySelector(
      '#view-memes .subnav-btn[data-subtab="charts"]');
    if (tab) tab.click();
  }
  if (scroll) dock.scrollIntoView({ behavior: "smooth", block: "start" });
};

/* "Just landed": first sighting on OUR tape within the last ten
   minutes — the coins-moving-IN half of the question the scan exists
   to answer. The badge follows the coin everywhere its name renders. */
function mcNewTag(c) {
  const fs = Number(c && c.first_seen);
  if (!fs || (Date.now() / 1000 - fs) > 600) return "";
  return `<span class="mc-new" title="First seen by our scan under ten minutes ago — this is when it reached the radar, not when the pair was created.">new</span>`;
}

/* The coin's monogram tile — a stable colour from the symbol, so the
   same coin wears the same colour on the watchlist, the cards and the
   dock. No token images on the free feeds; a typed identity beats a
   broken-image icon. */
function mcTile(c, size = 34) {
  const sym = String(c.symbol || c.name || c.mint || "?").replace(/[^A-Za-z0-9]/g, "").slice(0, 4) || "?";
  let h = 0;
  for (const ch of sym) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `<span class="mc-tile" style="width:${size}px;height:${size}px;
    background:hsl(${h} 42% 24%);color:hsl(${h} 70% 78%)">${escapeHtml(sym.slice(0, 3))}</span>`;
}

/* Momentum as a bar you can read at a glance, not a bare digit. */
function mcMomBar(m) {
  const v = Math.max(0, Math.min(100, m || 0));
  const tone = v >= 70 ? "var(--good)" : v >= 45 ? "var(--brand-2)" : "var(--text-mute)";
  return `<span class="mc-mom" title="MomentumScore ${v}/100 — cohort-relative order flow: volume acceleration, unique-buyer growth, buy/sell pressure, price acceleration">
    <i style="width:${v}%;background:${tone}"></i><b style="color:${tone}">${v}</b></span>`;
}

/* Risk as a named badge. The number alone told a newcomer nothing —
   "risk 55" reads as noise; "ELEVATED 55" reads as a verdict. */
function mcRiskBadge(c, gate = 60) {
  const r = c.risk || 0;
  const [label, tone] = r >= gate ? ["GATED", "var(--bad)"]
    : r >= 35 ? ["ELEVATED", "var(--warn)"] : ["LOW RISK", "var(--good)"];
  const why = (c.risk_why || []).length ? ":\n" + c.risk_why.map((w) => "· " + w).join("\n") : "";
  return `<span class="mc-riskb" style="color:${tone};border-color:${tone}"
    title="RiskScore ${r}/100 — authorities, LP lock, holder concentration, liquidity, age, wash pattern${why}">${label} ${r}</span>`;
}

/* One coin's identity cell, shared by cards and the board table. */
function mcName(c) {
  const label = c.symbol || c.name || (c.mint || "").slice(0, 8);
  const inner = `<b>${escapeHtml(label)}</b>${c.name && c.symbol
    ? ` <span style="color:var(--text-mute);font-weight:400">${escapeHtml(String(c.name).slice(0, 28))}</span>` : ""}`;
  const linked = (c.url && /^https:\/\//.test(c.url))
    ? `<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener" style="color:inherit">${inner}</a>`
    : inner;
  return linked + mcNewTag(c);
}

async function renderMemes() {
  const host = document.getElementById("memes-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/memecoins.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}

  /* One line closed, the full block a tap away. The first cut of this
     page gave the base rates a five-tile card that pushed the charts —
     the product — below the fold ("you can barely see the charts").
     The facts stay unskippable: the strip renders on every room, closed
     or open, and the summary line IS the five numbers. */
  const honesty = `
    <details class="card mc-honesty">
      <summary><span class="mc-honesty-head">How to read this page — and the base rates</span>
        <span class="mc-honesty-line">~1.4% ever graduate · 60% of traders lose ·
        82.8% artificial growth · 41.4% wash volume · median rug &lt;1h</span></summary>
      <div class="mc-legend">
        <div class="mc-leg"><b>Momentum 0–100</b><span>Percentile vs the live cohort:
          volume acceleration 30%, unique-buyer growth 30%, buy/sell pressure 25%,
          price acceleration 15%. It ranks motion — it does not predict.</span></div>
        <div class="mc-leg"><b>Risk gate</b><span>Authorities, LP lock, holder
          concentration, liquidity, age and wash patterns score 0–100; at the gate
          the coin is barred from the rocket list no matter how hard it moves.</span></div>
        <div class="mc-leg"><b>Danger channel</b><span>Exit signals in priority
          order — liquidity draining, pressure flipping, price rolling over — fired
          for every coin, gated or not. Leaving matters most on the worst coins.</span></div>
      </div>
      <div class="mc-rates">${MC_BASE_RATES.map(([n, t]) =>
        `<div class="mc-rate"><span class="mc-rate-n">${n}</span><span>${t}</span></div>`).join("")}</div>
      <div class="mc-honesty-foot">A tracker’s genuine value is filtering scams and enforcing
      disciplined exits, not predicting moonshots. Nothing on this page is a buy signal,
      nothing is journaled as a bet, and none of it touches the sports model.</div>
    </details>`;

  if (!d || !(d.coins || []).length) {
    host.innerHTML = honesty + `
      <div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No meme-coin data yet</div>
      <div class="es-sub">The launcher polls GeckoTerminal’s new + trending Solana pools and
      DexScreener’s pair snapshots on every refresh (free, no key). If this persists, run
      <code>python3 launch.py --memes</code> — it says which feed is declining and why.</div></div>`;
    return;
  }
  setStandaloneSource("DexScreener + GeckoTerminal free feeds",
                      "Meme coins · live venue data");

  // The hero — Ethan (2026-08-10): "Meme coin page has no direction. I
  // have no clue what I'm looking at." The first thing on the page now
  // SAYS what the page is, what the three systems do, and how live the
  // data is. Everything in it is measured, nothing is a promise.
  const upd = (d.generated_at || "").slice(11, 19);
  const clear = (d.n || 0) - (d.gated || 0);
  const hero = `
    <div class="card mc-hero">
      <div class="mc-hero-words">
        <div class="mc-hero-title">Rocket Radar
          <span class="mc-hero-live">${icon("dot", 10)} live · rescans ~15s</span></div>
        <p>Solana meme coins, straight off the venues. <b>Momentum</b> ranks what’s
        moving right now (order flow, not hype). The <b>risk gate</b> keeps
        rug-shaped coins off the rocket list. The <b>danger channel</b> fires exit
        signals — including on coins the gate already refused. Tap any coin for its
        live chart; hover any score for its receipt.</p>
      </div>
      <div class="mc-hero-stats">
        <div class="mc-hs"><b>${d.n || 0}</b><span>tracked</span></div>
        <div class="mc-hs"><b style="color:var(--good)">${clear}</b><span>clear the gate</span></div>
        <div class="mc-hs"><b style="color:var(--warn)">${d.gated || 0}</b><span>gated</span></div>
        <div class="mc-hs"><b style="color:var(--bad)">${(d.exits || []).length}</b><span>flashing exit</span></div>
        <div class="mc-hs"><b>${escapeHtml(upd || "—")}</b><span>last scan</span></div>
      </div>
    </div>`;

  const byMint = {};
  for (const c of d.coins || []) byMint[c.mint] = c;
  const heat = (m) => m >= 70 ? "var(--good)" : m >= 45 ? "var(--brand)" : "var(--text-mute)";
  const riskColor = (r) => r >= (d.risk_gate || 60) ? "var(--bad)" : r >= 35 ? "var(--warn)" : "var(--good)";
  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div>
    <div class="v">${v}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;

  /* Indicator chips with receipts in the hover — same contract as the
     intel flags: every claim names its number. */
  const chipsFor = (c) => {
    const i = c.ind || {};
    const ch = [];
    ch.push(`<span class="chip" title="Pair age. Median rug dies inside an hour — under 30 minutes is a risk point.">${mcAge(i.age_min)} old</span>`);
    if (i.liq_mc != null) ch.push(`<span class="chip${i.liq_mc < 0.03 ? " down" : ""}" title="Liquidity ÷ market cap. Under 3% means one sell craters it.">liq/MC ${(i.liq_mc * 100).toFixed(1)}%</span>`);
    if (i.ratio_m5 != null) ch.push(`<span class="chip${i.ratio_m5 >= 1.2 ? " up" : i.ratio_m5 < 1 ? " down" : ""}" title="Buys per sell, last 5 minutes.">b/s ${i.ratio_m5.toFixed(2)}</span>`);
    if (i.vol_spike != null) ch.push(`<span class="chip" title="5-minute volume vs its share of the hour. 1.0 = steady pace.">vol ×${i.vol_spike.toFixed(1)}</span>`);
    if (i.buyers_m5 != null) ch.push(`<span class="chip" title="UNIQUE buying wallets in 5 minutes (GeckoTerminal) — broad wallet count is the anti-wash signal.">${i.buyers_m5} buyers/5m</span>`);
    if (i.top10_share != null) ch.push(`<span class="chip${i.top10_share > 0.30 ? " down" : ""}" title="Share of supply held by the ten largest accounts EXCLUDING the largest — which is almost always the pool’s own vault, market structure rather than an insider. Over 30% is the insider-concentration flag.">top10 ${(i.top10_share * 100).toFixed(0)}%</span>`);
    if (i.freeze_auth === true) ch.push(`<span class="chip down" title="RugCheck: the dev can FREEZE your tokens — the honeypot switch. The single worst flag on this board.">freeze auth</span>`);
    if (i.mint_auth === true) ch.push(`<span class="chip down" title="RugCheck: the dev can mint more supply at will.">mint auth</span>`);
    if (i.mint_auth === false && i.freeze_auth === false) ch.push(`<span class="chip up" title="RugCheck: mint and freeze authority both renounced — the two worst switches are off. A prerequisite, not a promise.">authorities renounced</span>`);
    if (i.lp_locked_pct != null && i.lp_locked_pct < 50) ch.push(`<span class="chip down" title="RugCheck: how much of the liquidity pool is locked. Unlocked LP can be pulled at any moment.">LP ${i.lp_locked_pct.toFixed(0)}% locked</span>`);
    if (c.carried) ch.push(`<span class="chip" title="No longer on the trending/new lists — kept on the scan while its tape lives (2h), because a dying coin leaves trending at exactly the moment the exit signals matter most.">off-trending</span>`);
    if (i.whale_share != null && i.whale_share > 0.15) ch.push(`<span class="chip down" title="The largest single account after the pool. One seller this size can crater the chart alone.">whale ${(i.whale_share * 100).toFixed(0)}%</span>`);
    if (i.vol_accel != null) ch.push(`<span class="chip${i.vol_accel > 0 ? " up" : ""}" title="Volume second derivative off our own snapshot tape — the ignition signal.">accel ${i.vol_accel > 0 ? "+" : ""}${i.vol_accel.toFixed(0)}</span>`);
    if (i.wash_flag) ch.push(`<span class="chip down" title="Volume spiked >500% while price moved <5% — volume with no one in it (arXiv:2507.01963).">wash pattern</span>`);
    if (c.boosted) ch.push(`<span class="chip down" title="Someone is PAYING DexScreener to promote this token.">paid promo</span>`);
    return ch.join("");
  };

  const rocketCards = (d.rocket || []).map((m) => byMint[m]).filter(Boolean)
    .map((c) => `<article class="card" style="--grade-color:${heat(c.momentum)}">
      <div class="card-head">
        <div class="card-id">
          <div class="score-ring" title="MomentumScore 0–100, percentile vs the live cohort — volume acceleration 30%, unique-buyer growth 30%, buy/sell pressure 25%, price acceleration 15%"
            style="background:conic-gradient(${heat(c.momentum)} ${c.momentum * 3.6}deg, rgba(255,255,255,.08) 0)">
            <span>${c.momentum}</span></div>
          <div>
            <div class="player">${mcName(c)}</div>
            <div class="subtitle">${mcPrice(c.price_usd)} · liq ${mcMoney(c.liquidity)} · MC ${mcMoney(c.market_cap || c.fdv)}</div>
            <div class="pick">5m ${mcPct((c.price_change || {}).m5)} · 1h ${mcPct((c.price_change || {}).h1)}</div>
          </div>
        </div>
        ${mcRiskBadge(c, d.risk_gate || 60)}
      </div>
      <div class="chips" style="margin-top:10px">${chipsFor(c)}</div>
      ${mcSpark(c.spark) ? `<div class="mc-spark-wrap" title="Price over our own snapshot tape — one point per refresh, up to six hours">${mcSpark(c.spark)}</div>` : ""}
      ${mcChartBtn(c) ? `<div style="margin-top:10px">${mcChartBtn(c)}</div>` : ""}
    </article>`).join("");

  const exitCards = (d.exits || []).map((m) => byMint[m]).filter(Boolean)
    .map((c) => `<article class="card" style="--grade-color:var(--bad)">
      <div class="card-head">
        <div class="card-id"><div>
          <div class="player">${mcName(c)}</div>
          <div class="subtitle">${mcPrice(c.price_usd)} · liq ${mcMoney(c.liquidity)} · 5m ${mcPct((c.price_change || {}).m5)}</div>
        </div></div>
        ${mcRiskBadge(c, d.risk_gate || 60)}
      </div>
      <ul class="mc-exit-why">${(c.exit_why || []).map((w) =>
        `<li>${escapeHtml(w)}</li>`).join("")}</ul>
      ${mcSpark(c.spark) ? `<div class="mc-spark-wrap">${mcSpark(c.spark)}</div>` : ""}
      ${mcChartBtn(c) ? `<div style="margin-top:10px">${mcChartBtn(c)}</div>` : ""}
    </article>`).join("");

  const rows = (d.coins || []).slice()
    .sort((a, b) => (b.momentum || 0) - (a.momentum || 0))
    .map((c, ix) => {
      const i = c.ind || {};
      const gated = c.risk >= (d.risk_gate || 60);
      return `<tr${gated ? ` class="mc-gated" title="RiskScore ${c.risk} — over the gate; excluded from the rocket list${(c.risk_why || []).length ? ":\n" + c.risk_why.map((w) => "· " + w).join("\n") : ""}"` : ""}>
        <td class="num">${ix + 1}</td>
        <td>${mcName(c)}</td>
        <td class="num">${mcAge(i.age_min)}</td>
        <td class="num">${mcPrice(c.price_usd)}</td>
        <td class="num">${mcPct((c.price_change || {}).m5)}</td>
        <td class="num">${mcPct((c.price_change || {}).h1)}</td>
        <td class="num">${mcMoney(c.liquidity)}</td>
        <td class="num">${mcMoney((c.volume || {}).h1)}</td>
        <td class="num">${i.ratio_m5 != null ? i.ratio_m5.toFixed(2) : "—"}</td>
        <td class="num">${i.buyers_m5 != null ? i.buyers_m5 : "—"}</td>
        <td class="num"${i.top10_share != null && i.top10_share > 0.30 ? ` style="color:var(--bad);font-weight:700"` : ""}>${i.top10_share != null ? (i.top10_share * 100).toFixed(0) + "%" : "—"}</td>
        <td class="num" style="color:${heat(c.momentum)};font-weight:700">${c.momentum}</td>
        <td class="num" style="color:${riskColor(c.risk)};font-weight:700">${c.risk}${gated ? `<span class="mc-gate-tag">gated</span>` : ""}</td>
        <td>${mcChartBtn(c, "mc-chart-link") || ""}</td>
      </tr>`;
    }).join("");

  /* THE ROOMS. Same organization the Record page earned: the tab bar is
     subtabbedHTML, the choice is remembered, an empty room never draws a
     tab. Charts is the FIRST room — Ethan: the charts lead, everything
     else is a tap away — with a coin-picker terminal that auto-opens the
     top coin so the page lands on live candles, not on a menu. */
  _mcCoins = byMint;
  const rocketSet = new Set(d.rocket || []);
  const chartable = [
    ...(d.rocket || []).map((m) => byMint[m]).filter(Boolean),
    ...(d.coins || []).slice()
      .sort((a, b) => (b.momentum || 0) - (a.momentum || 0))
      .filter((c) => !rocketSet.has(c.mint)),
  ].filter((c) => mcChartRef(c) && MC_B58.test(c.mint || "")).slice(0, 24);

  // The watchlist replaced a strip of bare coin names — "It just shows
  // coin names with rocket next to it." Every row now carries the
  // decision surface: rank, identity tile, price, 5-minute move, the
  // momentum bar and the named risk badge. Same machinery underneath
  // (mc-picker / mc-pick / mcShowChart), so the poll-and-restore
  // contract is untouched.
  const picker = chartable.map((c, ix) => `<button type="button"
      class="mc-pick" data-mint="${c.mint}" onclick="mcShowChart('${c.mint}')"
      title="Open the live chart">
      <span class="mc-rank">${ix + 1}</span>
      ${mcTile(c, 32)}
      <span class="mc-pick-id"><b>${escapeHtml((c.symbol || c.name || c.mint.slice(0, 6)).slice(0, 12))}${
        rocketSet.has(c.mint) ? ` <span class="mc-pick-tag">rocket</span>` : ""}${mcNewTag(c)}</b>
        <em>${escapeHtml(String(c.name || "").slice(0, 22))}</em></span>
      <span class="mc-pick-nums"><b>${mcPrice(c.price_usd)}</b>
        <span class="mc-pick-pct">${mcPct((c.price_change || {}).m5)} 5m</span></span>
      ${mcMomBar(c.momentum)}
    </button>`).join("");

  const chartsRoom = !chartable.length ? "" : `
    <div class="mc-term">
      <div class="mc-watch">
        <div class="mc-watch-head">Watchlist
          <span>momentum-ranked · tap a coin to chart it</span></div>
        <div class="mc-picker" role="group" aria-label="Pick a coin to chart">${picker}</div>
      </div>
      <div id="mc-chart-dock"></div>
    </div>`;

  const rocketRoom = `
    <div class="section-title">Rocket list
      <span class="sub">— highest momentum among coins UNDER the risk gate. Momentum is
      cohort-relative order flow: acceleration and unique buyers, not RSI lines. Hover any
      chip or score for its receipt.</span></div>
    <div class="cards wide">${rocketCards ||
      `<div class="empty-slate" style="grid-column:1/-1"><div class="es-icon">${icon("signal", 30)}</div>
        <div class="es-title">Nothing clears the gate right now</div>
        <div class="es-sub">Either every tracked coin is over the risk line — common, and the
        page working as designed — or the snapshot tape is too short: acceleration needs
        three sightings of a coin, so give the refresh loop a few minutes.</div></div>`}</div>`;

  const dangerRoom = `
    <div class="section-title">Danger channel
      <span class="sub">— exit signals in the spec’s priority order, IGNORING the gate: a
      dangerous coin crashing is exactly what this channel is for.</span></div>
    <div class="cards wide">${exitCards ||
      `<p class="loading" style="grid-column:1/-1">No exit signals on the current board.</p>`}</div>`;

  const boardRoom = `
    <div class="stats">
      ${tile("Coins tracked", d.n || 0, "GT new + trending, DS boosts")}
      ${tile("Clear the risk gate", (d.n || 0) - (d.gated || 0), `RiskScore under ${d.risk_gate || 60}`)}
      ${tile("Behind the gate", d.gated || 0, "momentum can’t buy them back")}
      ${tile("Flashing exit", (d.exits || []).length, "the danger channel")}
    </div>
    <div class="section-title">Full board
      <span class="sub">— every tracked coin, momentum-sorted. Dimmed rows are over the
      risk gate — shown, not hidden, because “filtered out” and “never seen” must not
      look identical (hover for the reasons).</span></div>
    <div class="card" style="padding:0;overflow-x:auto">
      <table class="agate mc-board"><thead><tr>
        <th>#</th><th>Coin</th><th>Age</th><th>Price</th><th>5m</th><th>1h</th>
        <th>Liq</th><th>Vol 1h</th><th title="Buys per sell, last 5 minutes">B/S 5m</th>
        <th title="Unique buying wallets, last 5 minutes">Buyers</th>
        <th title="Supply held by the ten largest accounts, excluding the largest (almost always the pool vault). Measured for the first 20 coins in discovery order.">Top 10</th>
        <th>Momentum</th><th>Risk</th><th></th>
      </tr></thead><tbody>${rows}</tbody></table></div>`;

  host.innerHTML = hero + honesty + subtabbedHTML("memes", [
    ["charts", "Radar",
     "the watchlist and the live chart — where you actually sit", chartsRoom],
    ["rocket", "Rockets",
     "the movers that also clear the risk gate, with their receipts", rocketRoom],
    ["danger", "Danger",
     "exit signals — get-out warnings, including on gated coins", dangerRoom],
    ["board", "Screener",
     "every tracked coin, every column, momentum-sorted", boardRoom],
  ]) + `
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">
      Top-10 holder share comes from Solana’s public RPC and EXCLUDES the largest account,
      which for a live coin is almost always the trading pool’s own vault — the number
      judges wallets, not market structure, and “—” means unmeasured, never safe.
      What this board still cannot see (paid firehose tier, deliberately parked — the doc
      has the map): mint/freeze authority, honeypot checks, dev-wallet sells, bundled
      snipers, holder velocity, smart-money wallets. Their absence is stated here rather
      than silently scored as safe. Volume acceleration and the sparklines run off our own
      snapshot tape and need a few sightings of a coin — young boards under-read them
      honestly. The Live chart button opens the venue’s own candle chart for the pool.
      Updated ${escapeHtml((d.generated_at || "").slice(11, 16))}; the launcher rescans
      every ~15 seconds (new-coin discovery ~25s — the free feeds’ rate-limit ceiling),
      and this page re-pulls on the same clock without disturbing an open chart.</p>`;
  bindSubtabs(host);
  // Land on candles, not on a menu — but never yank someone out of the
  // room they chose last time, and never scroll a page that just opened.
  // A re-render keeps the coin the user had open, falling back to the
  // top of the board only when that coin left it.
  const dock = document.getElementById("mc-chart-dock");
  if (chartable.length && dock && !dock.closest(".subgroup").hidden) {
    const want = (_mcOpenMint && byMint[_mcOpenMint]
                  && mcChartRef(byMint[_mcOpenMint]))
      ? _mcOpenMint : chartable[0].mint;
    mcShowChart(want, false);
  }
}

/* The board self-refreshes while you watch. The launcher rebuilds the
   JSON every ~15 seconds (its own thread — see launch.py), so the page
   re-pulls on a matching clock. Two refusals keep it civil: a hidden
   tab never polls, and an OPEN live chart is never yanked — the candle
   iframe is the venue's own stream and already moves second by second;
   re-rendering under it would reload the chart every tick, which is
   the one way to make a live terminal feel broken. The rocket/danger/
   board rooms refresh freely because nothing in them holds state. */
const MEMES_POLL_MS = 20000;
setInterval(() => {
  if (state.view !== "memes" || document.hidden) return;
  const dock = document.getElementById("mc-chart-dock");
  const watching = dock && dock.querySelector("iframe")
    && !dock.closest(".subgroup").hidden;
  if (watching) return;
  renderMemes();
}, MEMES_POLL_MS);

/* ============================================================
   Fantasy Football — usage trends, buy-low/sell-high, game scripts
   ============================================================ */
async function renderFantasy() {
  const host = document.getElementById("fantasy-body");
  if (!host) return;
  let d = null;
  try {
    // The injury board rides along so every roster surface can tag a
    // designation — missing is fine, the tags just come back empty.
    const [res] = await Promise.all([
      fetch("data/fantasy.json?t=" + Date.now()), loadInjuryBoard()]);
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
      <span class="ff-who" data-dossier="${escapeAttr(u.player)}">${playerAvatar(u.player, u.team, { map: nflMap(), headshot: u.headshot })}
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
        <div class="card-id" data-dossier="${escapeAttr(r.player)}">${playerAvatar(r.player, r.team, { map: nflMap(), headshot: r.headshot })}
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
          ? (buy ? "Expected points say the production is coming — his chances are worth more than he has scored from them so far."
                 : "Scoring above what his situations support — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")
          : (buy ? "Usage says the production is coming — the volume is already there."
                 : "Producing above what the opportunity supports — beyond the ~" + (bs.band || 1.5) + " PPG a good player sustains.")}</div>
    </article>`;
  };

  /* Rebuilt 2026-08-18 — Ethan, screenshot in hand: "organize this game
     script page better and also include team logos next to the team
     names, i think that makse it look more professional." The card used
     to spend THREE stacked prose lines on PROE, EPA and pace, each line
     naming both teams again in words — six team names per card and no
     way to compare down a column. Now the matchup header wears the
     clubs' marks and every per-team number sits in one two-row grid:
     read across for a team, down for a stat. Confidence rides the
     subtitle instead of dangling as its own footer line. */
  const gsRow = (t, implied, proe, epa, pace) => `
        <span class="gs-tm">${teamMark(t, 18, nflMap(), "nfl")}<b>${escapeHtml(t)}</b></span>
        <span class="num">${implied != null ? implied : "—"}</span>
        <span class="num">${proe != null ? `${proe >= 0 ? "+" : ""}${(proe * 100).toFixed(1)}%` : "—"}</span>
        <span class="num">${epa != null ? `${epa >= 0 ? "+" : ""}${epa.toFixed(2)}` : "—"}</span>
        <span class="num">${pace != null ? pace.toFixed(1) + "s" : "—"}</span>`;
  const scriptCards = (d.scripts || []).slice(0, 16).map((s) => `
    <article class="card">
      <div class="card-head">
        <div><div class="gs-match">${teamMark(s.away, 22, nflMap(), "nfl")}<b>${escapeHtml(s.away)}</b>
            <span class="gs-at">@</span>
            ${teamMark(s.home, 22, nflMap(), "nfl")}<b>${escapeHtml(s.home)}</b></div>
          <div class="subtitle">Week ${parseInt(s.week, 10) || escapeHtml(s.week)} · total ${s.total} ·
            ${escapeHtml(s.favorite)} −${Math.abs(s.spread)} · ${escapeHtml(s.confidence)} confidence</div></div>
        <span class="chip">${escapeHtml(s.archetype)}</span>
      </div>
      ${[s.home, s.away].filter((t) => coachChanged[t]).map((t) =>
        `<div class="warning" style="margin-top:8px">${iconMark("clock")}${escapeHtml(t)} has a new head coach
           (${escapeHtml(coachChanged[t])}) — last season’s tendencies (PROE included) may not carry</div>`).join("")}
      <div class="gs-grid">
        <span></span>
        <span class="gs-h" title="Points the total and spread imply for this club">Implied</span>
        <span class="gs-h" title="Pass rate over expectation — intent vs situation, the stable half of game script">PROE</span>
        <span class="gs-h" title="EPA/play: offensive efficiency measured from every snap (league avg ≈ 0)">EPA/play</span>
        <span class="gs-h" title="Seconds per snap with the game in the balance — lower is faster">Pace</span>
        ${gsRow(s.away, s.away_implied, s.away_proe, s.away_epa, s.away_pace)}
        ${gsRow(s.home, s.home_implied, s.home_proe, s.home_epa, s.home_pace)}
      </div>
      <div style="margin-top:8px;color:var(--text-body);font-size:var(--fs-sm)">${escapeHtml(s.read)}</div>
    </article>`).join("");

  const bsCount = (bs.buy_low || []).length + (bs.sell_high || []).length;
  // Four rooms, not one 11-screen scroll. Measured in Chromium: this page
  // was 9,906px with ten section titles stacked in a single column, and
  // the usage table — the thing the page is FOR — sat below camp reports,
  // the waiver pulse, the offseason tracker and the draft kit.
  const _ffLead = `
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
`;
  const _ffUsage = `    <div class="ls-note">Shares are of TEAM volume: targets for WR/TE/QB, carries for RB.
      The delta column is the money — a riser at 42% beats a flat 60%.</div>
    <div class="section-title">Usage movers
      <span class="sub">— season vs 4-week vs last week, biggest role changes first</span></div>
    <div class="card ff-table">
      <div class="ff-row ff-head">
        <span class="ff-who">Player</span><span class="ff-bar-h">Last week’s share</span>
        <span class="ff-n">Season</span><span class="ff-n">4-week</span><span class="ff-n">Last</span>
        <span class="ff-n trend">Trend</span><span class="ff-n rz">RZ/g</span><span class="ff-n">PPR</span>
      </div>
      ${usageRows || `<p class="loading" style="padding:12px">No usage rows for this season yet.</p>`}
    </div>
`;
  const _ffTrade = `    <div class="section-title">Buy low
      <span class="sub">— volume-expected points say the production is coming</span></div>
    <div class="cards wide">${(bs.buy_low || []).map((r) => tradeCard(r, "buy")).join("") ||
      `<p class="loading" style="grid-column:1/-1">Nobody outside the sustainable band right now.</p>`}</div>
    <div class="section-title">Sell high
      <span class="sub">— outrunning their opportunity; regression risk</span></div>
    <div class="cards wide">${(bs.sell_high || []).map((r) => tradeCard(r, "sell")).join("") ||
      `<p class="loading" style="grid-column:1/-1">Nobody outside the sustainable band right now.</p>`}</div>
`;
  const _ffScripts = `    <div class="section-title">Game scripts
      <span class="sub">— Vegas is the input: implied totals, archetypes, and confidence that
      scales with the spread</span></div>
    <div class="cards wide">${scriptCards ||
      `<p class="loading" style="grid-column:1/-1">No upcoming NFL games with posted spreads and
       totals in the DB yet — fills when next season’s lines are ingested.</p>`}</div>
`;
  const _ffFoot = `    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">Expected points are
      fit from this season’s own data (league value per target and per carry by position) —
      volume-based, so a player can legitimately sustain a positive gap; only gaps beyond
      ~${bs.band || 1.5} PPG are flagged. Updated ${escapeHtml(d.generated_at || "")}.</p>`;
  _mockKit = d.draft_kit || {};
  _ffData = d;
  host.innerHTML = _ffLead + subtabbedHTML("fantasy", [
    ["usage", "Usage", "who is getting the ball, and whose share is moving",
     _ffUsage],
    ["trade", "Trade targets",
     "buy low and sell high — where production and opportunity disagree",
     _ffTrade],
    ["scripts", "Game scripts",
     "what the market expects each game to look like", _ffScripts],
    ["ranks", "Rankings",
     "every source we can read without a password, and where they argue",
     rankBoardHTML(d.ranks)],
    ["days", "Calendar",
     "the best play for every game day — tap a day for the top five and why",
     ffCalendarHTML(d)],
    ["mock", "Mock draft",
     "a snake draft against the room — same board the kit publishes",
     `<div id="mock-room">${mockDraftHTML()}</div>`],
    ["league", "Around the league",
     "camp, the waiver wire, the offseason and the draft kit",
     acctStripHTML() + `<div id="sleeper-zone"></div>`
     + `<div id="league-desk"></div>`
     + `<div id="yahoo-zone"></div><div id="yahoo-desk"></div>`
     + campHTML(d.camp)
     + waiverPulseHTML(d.trending) + offseasonHTML(off) + draftKit],
  ]) + _ffFoot;
  bindSubtabs(host);
  _mockBind(host);
  const more = document.getElementById("usage-more");
  if (more) more.addEventListener("click", () => {
    const rest = document.getElementById("usage-rest");
    const open = rest.classList.toggle("ff-hidden") === false;
    more.setAttribute("aria-expanded", String(open));
    more.textContent = open ? "Show fewer ▴"
      : `Show ${allUsage.length - USAGE_SHOWN} more movers ▾`;
  });
  initDraftKit(d.draft_kit);
  window._ffRanks = d.ranks || null;
  initRankBoard();
  renderSleeperZone(d);
  renderYahooZone();
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
    <div class="os-row"><span class="os-team mk-idrow" data-dossier="${escapeAttr(r.player)}">${playerAvatar(r.player, r.team, { size: 24, map: nflMap(), headshot: r.headshot })}${escapeHtml(r.player)}
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
        staff’s own verdict; the change over camp is the honest preseason signal, not
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
      ${box("Fallers", "sliding — last season’s usage overstates their Week-1 role",
            (camp.fallers || []).map((r) => row(r, "var(--warn)")).join(""), accruing)}
    </div>`;
}

/* ============================================================
   ACCOUNTS — one name, every device.

   The personal data on this site (My Bets, the Sleeper league link,
   the bankroll) lived only in localStorage — which is per-browser AND
   per-address, so the laptop, the phone on the LAN address and a
   tailscale name were three empty copies, and iOS quietly evicts a
   site's storage after a week away. An account moves that data to a
   JSON file on the machine already serving this site — no cloud, no
   email, no third party, and still no sportsbook passwords, ever. The
   optional PIN keeps housemates out of your book; it rides plain HTTP
   on your own Wi-Fi, so it is a lock on the door, not cryptography.

   Sync is one POST that both pushes and pulls: the server merges
   (union by bet signature for My Bets so a device race can never lose
   a logged bet; last-writer-wins for fantasy + bankroll) and replies
   with the merged truth, which we adopt when its stamp is newer.
   ============================================================ */
const ACCT_KEY = "qb_acct_v1";       // {name, pin} — this device's sign-in
const ACCT_TS_KEY = "qb_acct_ts_v1"; // per-section last-local-change stamps
const ACCT_DEL_KEY = "qb_mybets_del_v1";  // deleted-bet signatures (tombstones)

function acctState() {
  try {
    const a = JSON.parse(localStorage.getItem(ACCT_KEY));
    return a && a.name ? a : null;
  } catch (e) { return null; }
}
function acctTs() {
  try { return JSON.parse(localStorage.getItem(ACCT_TS_KEY)) || {}; }
  catch (e) { return {}; }
}
function acctDeleted() {
  try { return JSON.parse(localStorage.getItem(ACCT_DEL_KEY)) || []; }
  catch (e) { return []; }
}

let _acctNote = "";                  // last sync outcome, painted on the card
let _acctPushT = null;

/* Called wherever a synced section changes locally. Stamps the section
   and (when signed in) schedules a push — debounced so typing a bet in
   does not fire a request per keystroke. */
function acctTouch(section) {
  const ts = acctTs();
  ts[section] = Date.now();
  try { localStorage.setItem(ACCT_TS_KEY, JSON.stringify(ts)); } catch (e) {}
  if (!acctState()) return;
  clearTimeout(_acctPushT);
  _acctPushT = setTimeout(() => acctSync(), 800);
}

function acctGather() {
  const ts = acctTs(), sections = {};
  const rows = mbLoad(), deleted = acctDeleted();
  if (rows.length || deleted.length || ts.mybets)
    sections.mybets = { ts: ts.mybets || 0, data: { rows, deleted } };
  const fu = localStorage.getItem("ff_user") || "";
  const fl = localStorage.getItem("ff_league") || "";
  const fd = localStorage.getItem("ff_draft_id") || "";
  // The pasted ranking rides along: it is typed once and wanted on the
  // phone at the draft table, which is the whole reason accounts exist.
  const fr = localStorage.getItem(FF_IMPORT_KEY) || "";
  if (fu || fl || fd || fr || ts.fantasy)
    sections.fantasy = { ts: ts.fantasy || 0,
                         data: { user: fu, league: fl, draft: fd, ranks: fr } };
  const bk = localStorage.getItem("ge-bankroll") || "";
  const up = localStorage.getItem("ge-unit-pct") || "";
  if (bk || up || ts.bankroll)
    sections.bankroll = { ts: ts.bankroll || 0,
                          data: { bankroll: bk, unitPct: up } };
  // Search history, new with real accounts. Rides the same last-writer-wins
  // rule as fantasy and bankroll — it is a convenience, not a ledger, and
  // it is the one section with a Clear button of its own.
  let searches = [];
  try { searches = JSON.parse(localStorage.getItem(ACCT_SEARCH_KEY) || "[]"); }
  catch (e) { searches = []; }
  if (searches.length || ts.search)
    sections.search = { ts: ts.search || 0, data: searches };
  return sections;
}

/* Adopt a section the server holds a newer copy of. Writes storage
   DIRECTLY (never through mbSave, which would re-stamp and re-push —
   an echo loop between two open devices). */
function acctApplySection(name, sec) {
  const d = sec.data || {};
  try {
    if (name === "mybets") {
      localStorage.setItem(MYBETS_KEY, JSON.stringify(d.rows || []));
      localStorage.setItem(ACCT_DEL_KEY, JSON.stringify(d.deleted || []));
    } else if (name === "fantasy") {
      const put = (k, v) => v ? localStorage.setItem(k, v)
                              : localStorage.removeItem(k);
      put("ff_user", d.user); put("ff_league", d.league);
      put("ff_draft_id", d.draft); put(FF_IMPORT_KEY, d.ranks);
    } else if (name === "search") {
      if (Array.isArray(d))
        localStorage.setItem(ACCT_SEARCH_KEY, JSON.stringify(d));
    } else if (name === "bankroll") {
      localStorage.setItem("ge-bankroll", d.bankroll || "");
      if (d.unitPct) localStorage.setItem("ge-unit-pct", d.unitPct);
      const el = document.getElementById("bankroll");
      const unit = document.getElementById("unit-pct");
      if (el) {
        el.value = d.bankroll || "";
        if (unit && d.unitPct) unit.value = d.unitPct;
        el.dispatchEvent(new Event("input"));   // reuse the render cascade
      }
    }
    const ts = acctTs();
    ts[name] = sec.ts || Date.now();
    localStorage.setItem(ACCT_TS_KEY, JSON.stringify(ts));
  } catch (e) {}
}

async function acctSync() {
  // A REAL ACCOUNT WINS WHEN THERE IS ONE. The email/password store and
  // the older name+PIN store answer the same shapes and share the same
  // merge on the server, so this is a change of address, not of contract
  // — and the legacy path stays live so nobody's existing book vanishes
  // the day they make an account.
  if (_acctUser && _acctUser.signed_in) return acctSyncAccount();
  const a = acctState();
  if (!a) return;
  try {
    const r = await fetch("/api/profile/" + encodeURIComponent(a.name), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: a.pin || "", sections: acctGather() }),
    });
    const body = await r.json().catch(() => null);
    if (!r.ok) {
      _acctNote = (body && body.error) || `sync failed (${r.status})`;
      acctPaintNote();
      return;
    }
    const ts = acctTs();
    let betsChanged = false;
    Object.keys(body.sections || {}).forEach((k) => {
      const s = body.sections[k];
      if (s && (s.ts || 0) > (ts[k] || 0)) {
        acctApplySection(k, s);
        if (k === "mybets") betsChanged = true;
      }
    });
    _acctNote = "synced " + new Date().toLocaleTimeString([],
                { hour: "numeric", minute: "2-digit" });
    if (betsChanged && state.view === "mybets") renderMyBets();
    else acctPaintNote();
  } catch (e) {
    _acctNote = "server offline — changes are saved here and will sync "
              + "when the live site is up";
    acctPaintNote();
  }
}

/* The render's green button, honestly framed. One tap opens My Bets
   with this pick's description, odds, book and sport already typed —
   the stake stays yours, focused and empty. Nothing is logged until
   you press Log bet. */
window.tpTrack = function (i) {
  const p = (window._tpPicks || [])[i];
  if (!p) return;
  enterStandaloneMode("mybets");
  setTimeout(() => {
    const put = (id, v) => { const el = document.getElementById(id); if (el != null && v != null && v !== "") el.value = v; };
    const bookSel = document.getElementById("mb-book");
    if (bookSel) {
      const hit = [...bookSel.options].find((o) => o.value.toLowerCase() === String(p.book).toLowerCase());
      bookSel.value = hit ? hit.value : "Other";
    }
    put("mb-sport", p.sport);
    put("mb-desc", p.desc);
    put("mb-odds", p.odds);
    const warn = document.getElementById("mb-form-warn");
    if (warn) warn.textContent = "Prefilled from tonight’s board — enter your stake, then Log bet.";
    const stake = document.getElementById("mb-stake");
    if (stake) stake.focus();
  }, 250);
};

function acctPaintNote() {
  document.querySelectorAll(".acct-note").forEach((el) => {
    el.textContent = _acctNote;
  });
}

/* ---------------- Qellys accounts: email and password -------------------

   Ethan, 2026-08-15: "make a feature where you can make an account on our
   website with email and password so we can store peoples bets and
   fantasy leauges and search history or anything like that."

   THE SESSION NEVER TOUCHES THIS FILE. Sign-in returns a cookie marked
   HttpOnly, which means page scripts — including this one — cannot read
   it. That is deliberate: if a script could read the token, then so could
   any script that ever got injected into the page. Everything below asks
   the server "am I signed in?" rather than inspecting a token, because
   asking is the only thing it is allowed to do.

   The password is typed, POSTed once, and never stored anywhere on the
   device. What comes back is a session, not a credential.

   WHAT WE DO NOT DO, still: this asks for an account HERE. It does not
   ask for a DraftKings or ESPN password, because a credential to somebody
   else's service cannot be scoped or revoked by us, and ours can. */
let _acctUser = null;                 // {signed_in, email} — server's answer
const ACCT_SEARCH_KEY = "qb_search_v1";
const SEARCH_KEEP = 100;

async function acctWho(force) {
  if (_acctUser && !force) return _acctUser;
  try {
    const r = await fetch("/api/account/me", { credentials: "same-origin" });
    _acctUser = r.ok ? await r.json() : { signed_in: false };
  } catch (e) { _acctUser = { signed_in: false }; }
  return _acctUser;
}

async function acctSyncAccount() {
  try {
    const r = await fetch("/api/account/data", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sections: acctGather() }),
    });
    if (r.status === 401) {              // session expired underneath us
      _acctUser = { signed_in: false };
      _acctNote = "Signed out — sign in again to keep syncing.";
      acctPaintNote();
      return;
    }
    const body = await r.json().catch(() => null);
    if (!r.ok) {
      _acctNote = (body && body.error) || `sync failed (${r.status})`;
      return acctPaintNote();
    }
    const ts = acctTs();
    let betsChanged = false;
    Object.keys(body.sections || {}).forEach((k) => {
      const s = body.sections[k];
      if (s && (s.ts || 0) > (ts[k] || 0)) {
        acctApplySection(k, s);
        if (k === "mybets") betsChanged = true;
      }
    });
    _acctNote = "synced " + new Date().toLocaleTimeString([],
                { hour: "numeric", minute: "2-digit" });
    if (betsChanged && state.view === "mybets") renderMyBets();
    else acctPaintNote();
  } catch (e) {
    _acctNote = "server offline — changes are saved here and will sync when "
              + "the site is back up";
    acctPaintNote();
  }
}

/* Search history. Ethan asked for it by name, so it is stored — and it is
   also the one section here that is a record of what somebody was
   THINKING rather than what they did, so it says plainly that it is kept
   and gives one button to wipe it. */
function acctSearchLog(q) {
  const term = String(q || "").trim();
  if (term.length < 2) return;
  let log = [];
  try { log = JSON.parse(localStorage.getItem(ACCT_SEARCH_KEY) || "[]"); }
  catch (e) { log = []; }
  if (log.length && log[log.length - 1].q === term) return;   // still typing
  log.push({ q: term, ts: Date.now() });
  if (log.length > SEARCH_KEEP) log = log.slice(-SEARCH_KEEP);
  try { localStorage.setItem(ACCT_SEARCH_KEY, JSON.stringify(log)); } catch (e) {}
  acctTouch("search");
}

window.acctSearchClear = function () {
  try { localStorage.removeItem(ACCT_SEARCH_KEY); } catch (e) {}
  acctTouch("search");
  _acctNote = "Search history cleared.";
  acctSync();
  if (state.view === "mybets") renderMyBets();
  else if (state.view === "fantasy") renderFantasy();
};

function acctSignedInHTML(u) {
  return `<div class="card" style="margin-bottom:16px">
    <div class="card-head">
      <div><div class="player">Signed in — ${escapeHtml(u.email)}</div>
        <div class="subtitle">Your bets, fantasy leagues and search history
          follow this account to every device you sign in on.</div></div>
      <div class="acct-btns">
        <button class="btn" onclick="acctSyncNow()">Sync now</button>
        <button class="btn ghost" onclick="acctSignOut()">Sign out</button>
      </div>
    </div>
    <div class="acct-note">${escapeHtml(_acctNote)}</div>
    <div id="billing-slot"></div>
    <details class="acct-more">
      <summary>Account settings</summary>
      <div class="acct-row">
        <input type="password" class="acct-old" placeholder="current password"
          autocomplete="current-password">
        <input type="password" class="acct-new" placeholder="new password"
          autocomplete="new-password">
        <button class="btn ghost" onclick="acctChangePassword(this)">Change password</button>
      </div>
      <p class="rank-help">Changing it signs out every other device — a
        password change is usually an answer to “somebody else may have
        this”, and leaving those sessions alive would answer it with
        nothing.</p>
      <div class="acct-row">
        <button class="btn ghost" onclick="acctExport()">Download my data</button>
        <button class="btn ghost" onclick="acctSearchClear()">Clear search history</button>
        <button class="btn ghost" onclick="acctDelete(this)">Delete my account</button>
      </div>
      <p class="rank-help">Delete removes the account, every bet, league and
        search we hold for it, and cannot be undone.</p>
    </details>
  </div>`;
}

/* The eye on the password field, from the render's login panel.

   IT IS NOT DECORATION ON A PHONE. A long password typed blind on a
   touch keyboard is the commonest reason somebody fails to sign in twice
   and gives up, and this site asks for ten characters or more. Toggling
   the input type is the whole mechanism; the value never leaves the
   field, so nothing is logged and nothing is sent anywhere. */
window.acctTogglePw = function (btn) {
  const wrap = btn.closest(".acct-pw-wrap");
  const input = wrap && wrap.querySelector("input");
  if (!input) return;
  const showing = input.type === "text";
  input.type = showing ? "password" : "text";
  btn.setAttribute("aria-pressed", String(!showing));
  btn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  btn.classList.toggle("on", !showing);
  input.focus();
};

function acctSignInHTML() {
  const legacy = acctState();
  // THE WARNING COMES BEFORE THE FORM, not after the password is typed.
  // The server refuses these requests anyway, but a refusal arrives too
  // late to be useful: by then the password is already in the box, and on
  // a phone it is already in the keyboard's suggestion history.
  const insecure = _acctUser && _acctUser.insecure;
  return `<div class="card" style="margin-bottom:16px">
    <div class="acct-brand" aria-hidden="true">
      <svg viewBox="0 0 40 40" fill="none" stroke="currentColor"
        stroke-width="2.5"><ellipse cx="20" cy="20" rx="17" ry="12"/>
        <circle cx="20" cy="20" r="3.5" fill="currentColor" stroke="none"/>
      </svg>
    </div>
    <div class="card-head acct-welcome"><div>
      <div class="player">Welcome back</div>
      <div class="subtitle">Your bets, fantasy leagues and search history
        are stored with your account, so they are there on every device you
        sign in on.</div></div></div>
    ${insecure ? `<div class="warning">${icon("warn")} <b>${
      _acctUser.allowed ? "This connection is not private."
                        : "Not over this connection."}</b>
      This page came over plain HTTP from another machine, so a password
      typed here crosses your network readable by anyone on it — and it is
      usually a password used somewhere else too.
      ${_acctUser.allowed
        ? `The server was started with <code>QB_ALLOW_INSECURE_LOGIN=1</code>,
           so it will accept it anyway. That setting removed the refusal,
           not the risk.`
        : `Sign in from the computer running the server, or give it an HTTPS
           address — <code>tailscale serve --bg 8000</code> prints one that
           works from anywhere.`}</div>` : ""}
    <div class="acct-row">
      <input type="email" class="acct-email" placeholder="you@example.com"
        autocomplete="email" maxlength="254" spellcheck="false">
      <div class="acct-pw-wrap">
        <input type="password" class="acct-pw" placeholder="password"
          autocomplete="current-password" maxlength="200">
        <button type="button" class="acct-eye" aria-label="Show password"
          aria-pressed="false" onclick="acctTogglePw(this)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" aria-hidden="true"><path d="M2 12s3.6-6 10-6
            10 6 10 6-3.6 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="3"/>
          </svg>
        </button>
      </div>
      <button class="btn" onclick="acctAuth(this, 'login')">Log in</button>
    </div>
    <div class="acct-alt">
      <span>Don’t have an account?</span>
      <button class="btn ghost" onclick="acctAuth(this, 'signup')">Sign up</button>
    </div>
    <label class="acct-confirm">
      <input type="checkbox" class="acct-age">
      <span>I am 21 or older, and I accept the
        <a href="terms.html" target="_blank" rel="noopener">Terms</a> and
        <a href="privacy.html" target="_blank" rel="noopener">Privacy Policy</a>.
        This site publishes model estimates and takes no bets.</span>
    </label>
    <div class="acct-note">${escapeHtml(_acctNote)}</div>
    <p class="rank-help">Ten characters or more — length is what makes a
      password hard to guess. We store a one-way scramble of it, never the
      password itself, which is why nobody here can ever tell you what
      yours is; a lost one gets replaced, not recovered.</p>
    <p class="rank-help">We still never ask for your sportsbook or ESPN
      password. Those belong to someone else’s service and could not be
      revoked by us. This one is ours, and you can delete it whenever you
      like.</p>
    ${legacy ? `<p class="rank-help">${icon("warn")} This device is still
      signed in to the older PIN profile <b>${escapeHtml(legacy.name)}</b>.
      It keeps working and nothing has been moved — make an account and
      its data syncs up on the next sync.</p>` : ""}
  </div>`;
}

window.acctAuth = async function (btn, mode) {
  const card = btn.closest(".card");
  const note = card.querySelector(".acct-note");
  const say = (t) => { if (note) note.textContent = t; };
  const email = (card.querySelector(".acct-email").value || "").trim();
  const password = card.querySelector(".acct-pw").value || "";
  if (!email || !password) return say("Email and password, both.");
  // Only on SIGN-UP. Asking an existing user to re-tick it every time
  // they sign in would train them to tick it without reading, which is
  // the opposite of what an acknowledgment is for.
  const ageBox = card.querySelector(".acct-age");
  const confirmed = !!(ageBox && ageBox.checked);
  if (mode === "signup" && !confirmed)
    return say("Please confirm you are 21 or older and accept the Terms.");
  say(mode === "signup" ? "Creating your account…" : "Signing in…");
  try {
    const r = await fetch(`/api/account/${mode}`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, confirmed }),
    });
    const body = await r.json().catch(() => null);
    if (!r.ok) return say((body && body.error) || `Failed (${r.status}).`);
    _acctUser = { signed_in: true, email: body.email };
    // The typed password is not kept anywhere. What we hold now is a
    // session cookie this script cannot even read.
    card.querySelector(".acct-pw").value = "";
    _acctNote = mode === "signup" ? "Account created — this device is synced."
                                  : "Signed in — pulling your data…";
    await acctSync();
    if (typeof renderGreeting === "function") renderGreeting();
    if (state.view === "mybets") renderMyBets();
    else if (state.view === "fantasy") renderFantasy();
  } catch (e) {
    say("The live server is not reachable — accounts need the site served "
        + "by launch.py, not a static copy.");
  }
};

/* ---------------- Subscription -----------------------------------------

   Ethan, 2026-08-15: "we will be accepting money for people to use the
   website once it is complete."

   NOTHING IS GATED YET, and that is deliberate rather than unfinished.
   The plumbing is here and the status is real, but no feature checks
   entitlement — the site is free today, and switching a paywall on
   before Ethan has said what is behind it would lock him out of his own
   board on the strength of an inference. This card reports the truth and
   sells a subscription; the day something becomes paid is a decision, not
   a deployment.

   AND THE CARD NEVER TOUCHES A CARD. Subscribe hands off to a Paddle
   page; Manage billing hands off to Paddle's portal, which is also where
   cancelling happens. A company that builds its own cancel flow is
   deciding how hard it is to leave, and this one is not going to be
   that. */
async function renderBilling() {
  const slot = document.getElementById("billing-slot");
  if (!slot) return;
  let s;
  try {
    const r = await fetch("/api/billing/status", { credentials: "same-origin" });
    s = await r.json();
  } catch (e) { slot.innerHTML = ""; return; }
  if (!s || !s.signed_in) { slot.innerHTML = ""; return; }
  if (!s.configured) {
    // Say nothing to a user; this is a note for whoever runs the server.
    slot.innerHTML = `<p class="rank-help">Subscriptions are not switched on
      yet — see <b>docs/BILLING.md</b>.</p>`;
    return;
  }
  slot.innerHTML = `
    <div class="acct-row">
      <span class="bill-state${s.entitled ? " on" : ""}">${
        escapeHtml(s.note || "")}</span>
      ${s.entitled || s.customer_id
        ? `<button class="btn ghost" onclick="billPortal(this)">Manage billing</button>`
        : `<button class="btn" onclick="billSubscribe(this)">Subscribe</button>`}
      ${s.live === false ? `<span class="chip warn">Paddle sandbox —
        no real money moves</span>` : ""}
    </div>`;
}

async function _billGo(btn, path) {
  const was = btn.textContent;
  btn.textContent = "Opening Paddle…";
  btn.disabled = true;
  try {
    const r = await fetch(`/api/billing/${path}`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: "{}",
    });
    const d = await r.json();
    if (!r.ok || !d.url) throw new Error((d && d.error) || `Failed (${r.status}).`);
    // Paddle's own page, in this tab: it is a payment flow and a popup
    // blocker eating it would look like a broken button.
    location.href = d.url;
  } catch (e) {
    btn.disabled = false;
    btn.textContent = was;
    const note = btn.closest(".card").querySelector(".acct-note");
    if (note) note.textContent = String((e && e.message) || e);
  }
}

window.billSubscribe = (btn) => _billGo(btn, "checkout");
window.billPortal = (btn) => _billGo(btn, "portal");

window.acctChangePassword = async function (btn) {
  const card = btn.closest(".card");
  const note = card.querySelector(".acct-note");
  const say = (t) => { if (note) note.textContent = t; };
  const old = card.querySelector(".acct-old").value || "";
  const nw = card.querySelector(".acct-new").value || "";
  if (!old || !nw) return say("Both the current and the new password.");
  try {
    const r = await fetch("/api/account/password", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old, new: nw }),
    });
    const body = await r.json().catch(() => null);
    if (!r.ok) return say((body && body.error) || `Failed (${r.status}).`);
    _acctUser = { signed_in: false };
    _acctNote = "Password changed. Every device is signed out, including "
              + "this one — sign in with the new one.";
    if (state.view === "mybets") renderMyBets();
    else if (state.view === "fantasy") renderFantasy();
  } catch (e) { say("Server not reachable."); }
};

window.acctExport = async function () {
  try {
    const r = await fetch("/api/account/export", { credentials: "same-origin" });
    if (!r.ok) return;
    const blob = new Blob([JSON.stringify(await r.json(), null, 1)],
                          { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "qellys-account.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (e) {}
};

window.acctDelete = async function (btn) {
  const card = btn.closest(".card");
  const note = card.querySelector(".acct-note");
  const pw = prompt("Deleting removes your account and everything in it, and "
                    + "cannot be undone.\n\nType your password to confirm:");
  if (!pw) return;
  try {
    const r = await fetch("/api/account/delete", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    });
    // Every failure used to read "Wrong password.", which was a guess
    // dressed as a diagnosis — a subscribed account is refused for a
    // completely different reason and the person needs to be told which.
    if (!r.ok) {
      let msg = "Wrong password.";
      try {
        const j = await r.json();
        if (j && j.error) msg = j.error;
      } catch (e) {}
      if (note) note.textContent = msg;
      return;
    }
    _acctUser = { signed_in: false };
    _acctNote = "Account deleted. Anything on this device is still here.";
    if (state.view === "mybets") renderMyBets();
    else if (state.view === "fantasy") renderFantasy();
  } catch (e) {}
};

/* One card, mounted on both My Bets and Fantasy. Handlers find their
   inputs through the card element itself, so the two mounts never fight
   over ids. */
/* ---------------- The account screen -------------------------------------

   Ethan, 2026-08-16: "the login page is hidden and should be on the main
   screen with maybe an account icon in the top right … it needs to look
   professional."

   It WAS hidden, and the diagnosis is worth keeping because the shape
   recurs: the sign-in form existed, worked, and was well tested — it was
   simply mounted three cards down inside My Bets, reachable only by
   pressing an unlabelled person glyph. Nothing was broken. It just had no
   address of its own, and a thing with no address cannot be linked to,
   cannot be bookmarked, and cannot be the destination of "you need an
   account for that".

   That last one is why this is the piece the paywall waits on: every
   locked board is about to need somewhere to send people.

   ONE COLUMN, NOT A CARD IN A STACK. A sign-in screen is the one page
   where a narrow measure is right — there is a single thing to do, and
   the width of a data table would leave the form stranded in a field of
   nothing. */
function acctScreenHTML() {
  const u = _acctUser;
  if (u && u.signed_in) {
    setTimeout(renderBilling, 0);
    return `<div class="acct-screen acct-screen-in">
      <div class="acct-screen-head">
        <span class="acct-avatar">${escapeHtml(
          (u.email || "?").trim().slice(0, 2).toUpperCase())}</span>
        <div>
          <h2>Your account</h2>
          <p class="acct-screen-sub">${escapeHtml(u.email)}</p>
        </div>
      </div>
      ${acctSignedInHTML(u)}
    </div>`;
  }
  // Signed out. A legacy PIN profile, if this device still has one, goes
  // BELOW the sign-in rather than above it: it is the old thing being
  // replaced, and putting it first would make the upgrade look optional.
  const legacy = acctState() ? acctLegacyCardHTML() : "";
  return `<div class="acct-screen">
    <div class="acct-screen-head">
      <div>
        <h2>Sign in to Qellys Book</h2>
        <p class="acct-screen-sub">One account carries your bet log, your
          fantasy leagues and your subscription to every device you use.</p>
      </div>
    </div>
    ${acctSignInHTML()}
    <ul class="acct-assure">
      <li>The site takes no bets and never holds your money.</li>
      <li>Card details go to Paddle, never to this server.</li>
      <li>Delete the account whenever you like, from this page.</li>
    </ul>
    ${legacy}
  </div>`;
}

/* Re-rendered whenever the server's answer changes — a screen still
   showing the sign-in form after a successful sign-in is the commonest
   way a page like this feels broken. */
function renderAccount() {
  const body = document.getElementById("account-body");
  if (!body) return;
  body.innerHTML = acctScreenHTML();
}

/* The compact strip that replaces the full card on My Bets and Fantasy.
   Those pages need to say whether the log is syncing; they do not need to
   be a second place to sign in, and two forms for one thing is how a
   password gets typed into the wrong one. */
function acctStripHTML() {
  const u = _acctUser;
  if (u && u.signed_in) {
    return `<div class="acct-strip">
      <span class="acct-avatar sm">${escapeHtml(
        (u.email || "?").trim().slice(0, 2).toUpperCase())}</span>
      <span>Syncing to <b>${escapeHtml(u.email)}</b></span>
      <button class="btn ghost" onclick="switchView('account', true)">Account</button>
    </div>`;
  }
  return `<div class="acct-strip acct-strip-out">
    <span>Not signed in — this stays in this browser only.</span>
    <button class="btn" onclick="switchView('account', true)">Sign in</button>
  </div>`;
}

function acctCardHTML() {
  // The email/password account is the front door now. `_acctUser` is the
  // SERVER's answer, fetched at boot; until it lands we draw the sign-in
  // form, which is the honest default — claiming "signed in" before the
  // server has confirmed it is how a stale card ends up offering Sync now
  // on an expired session.
  if (_acctUser && _acctUser.signed_in) {
    // Filled a tick later, once whoever asked for this string has actually
    // put it in the DOM. Hooked here rather than at each caller because
    // this card is mounted on both My Bets and Fantasy, and a second call
    // site is a second place to forget.
    setTimeout(renderBilling, 0);
    return acctSignedInHTML(_acctUser);
  }
  if (!acctState()) return acctSignInHTML();
  // A legacy PIN profile is still signed in on this device: show its card
  // AND the new one, so nothing disappears and the upgrade is visible.
  return acctLegacyCardHTML() + acctSignInHTML();
}

function acctLegacyCardHTML() {
  const a = acctState();
  if (a) {
    return `<div class="card" style="margin-bottom:16px">
      <div class="card-head"><div><div class="player">Account — ${escapeHtml(a.name)}</div>
        <div class="subtitle">Your bets, league link and bankroll follow this name to every
          device that signs in — stored on your own computer, nowhere else.</div></div>
        <div style="display:flex;gap:8px">
          <button class="btn" onclick="acctSyncNow()">Sync now</button>
          <button class="btn" onclick="acctSignOut()">Sign out</button>
        </div></div>
      <div class="acct-note" style="margin-top:8px;color:var(--text-mute);font-size:0.85em">${escapeHtml(_acctNote)}</div>
    </div>`;
  }
  return `<div class="card" style="margin-bottom:16px">
    <div class="card-head"><div><div class="player">Make an account (optional)</div>
      <div class="subtitle">Pick a name and this page’s info follows you to every device —
        it lives on your own computer, not a company’s server. The PIN is optional and
        just keeps others on your Wi-Fi out. Still no sportsbook logins, ever.</div></div></div>
    <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
      <input type="text" class="acct-name" placeholder="account name" maxlength="24"
        autocomplete="off" style="flex:1;min-width:140px;background:var(--panel-2);color:inherit;
        border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
      <input type="text" class="acct-pin" placeholder="PIN (optional)" maxlength="12"
        inputmode="numeric" autocomplete="off" style="width:120px;background:var(--panel-2);color:inherit;
        border:1px solid var(--border);border-radius:var(--radius);padding:9px 12px;font-family:inherit"/>
      <button class="btn" onclick="acctGo(this, true)">Create</button>
      <button class="btn" onclick="acctGo(this, false)">Sign in</button>
    </div>
    <div class="acct-note" style="margin-top:8px;color:var(--text-mute);font-size:0.85em">${escapeHtml(_acctNote)}</div>
  </div>`;
}

window.acctGo = async function (btn, creating) {
  const card = btn.closest(".card");
  const name = (card.querySelector(".acct-name").value || "").trim();
  const pin = (card.querySelector(".acct-pin").value || "").trim();
  const note = card.querySelector(".acct-note");
  const say = (t) => { if (note) note.textContent = t; };
  if (!/^[A-Za-z0-9_-]{2,24}$/.test(name))
    return say("Account names are 2–24 letters, digits, - or _ — no spaces.");
  if (pin && !/^\d{4,12}$/.test(pin))
    return say("The PIN is 4–12 digits (or leave it empty).");
  if (!creating) {
    // Signing in verifies first — a typo must not silently CREATE an
    // account and strand the real one.
    try {
      const r = await fetch("/api/profile/" + encodeURIComponent(name),
                            { headers: { "X-Profile-Pin": pin } });
      if (r.status === 404)
        return say(`No account named “${name}” — check the spelling, or use Create.`);
      if (!r.ok) {
        const b = await r.json().catch(() => null);
        return say((b && b.error) || `Sign-in failed (${r.status}).`);
      }
    } catch (e) {
      return say("The live server is not reachable — accounts need the site "
                 + "served by launch.py, not a static copy.");
    }
  }
  try { localStorage.setItem(ACCT_KEY, JSON.stringify({ name, pin })); } catch (e) {}
  _acctNote = creating ? "Account created — this device is now synced."
                       : "Signed in — pulling your info…";
  if (typeof renderGreeting === "function") renderGreeting();
  await acctSync();
  if (state.view === "mybets") renderMyBets();
  else if (state.view === "fantasy") renderFantasy();
};

window.acctSyncNow = function () { _acctNote = "syncing…"; acctPaintNote(); acctSync(); };

window.acctSignOut = async function () {
  // Ends the SERVER's session too. Forgetting the cookie locally while
  // leaving the session alive on the server is not signing out — it is
  // the same session, still valid, waiting for whoever has the cookie.
  if (_acctUser && _acctUser.signed_in) {
    try {
      await fetch("/api/account/logout", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: "{}",
      });
    } catch (e) {}
    _acctUser = { signed_in: false };
  }
  try { localStorage.removeItem(ACCT_KEY); } catch (e) {}
  if (typeof renderGreeting === "function") renderGreeting();
  _acctNote = "Signed out — everything stays on this device; sign back in anytime.";
  if (state.view === "mybets") renderMyBets();
  else if (state.view === "fantasy") renderFantasy();
};

/* Boot: adopt anything newer from the server shortly after first paint,
   then keep a slow heartbeat while the tab is visible, so a bet logged
   on the phone shows up on the laptop without a reload. */
setTimeout(async () => {
  // Ask the server who we are BEFORE the first sync, or a signed-in
  // browser's opening sync goes down the legacy path (or nowhere) and
  // the card paints "make an account" over an account that exists.
  await acctWho(true);
  // REPAINT WHATEVER THE ANSWER IS. The first cut only re-rendered when
  // signed IN, which left the not-signed-in card exactly as it was drawn
  // before the server answered — and that card is the one carrying the
  // "this connection is not private" warning. So the warning was invisible
  // in precisely the case it exists for. Found by opening the LAN address
  // in a browser; the source-level test passed the whole time, because the
  // string was there and only the timing was wrong.
  if (state.view === "mybets") renderMyBets();
  else if (state.view === "fantasy") renderFantasy();
  acctSync();
}, 1500);
setInterval(() => { if (!document.hidden) acctSync(); }, 60000);

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
          <span class="dl-main" data-dossier="${escapeAttr(r.player)}">${playerAvatar(r.player, r.team, { size: 26, map: nflMap(), headshot: r.headshot })}
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
    <div class="os-row"><span class="os-team">${teamMark(c.team, 20, nflMap(), "nfl")} ${escapeHtml(nflName(c.team))}</span>
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
      won’t show until the feed comes back.</div>`
    : off.rosters_synced_at ? `
    <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-bottom:12px">
      Rosters synced ${escapeHtml(off.rosters_synced_at)} — trades checked on every
      launch, refreshed daily.</div>` : "";
  return `
    <div class="section-title">The ${off.upcoming_season || "upcoming"} offseason
      <span class="sub">— what the league changed under last season’s numbers. Derived from
      the schedule and roster feeds on every build, not from a news list that goes stale.</span></div>
    ${rosterNote}
    <div class="cards wide">
      ${box("Coaching changes", "new head coach — last season’s tendencies may not carry",
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
  nfl: "— every team as it stands today, ordered by the coaching staff’s own "
     + "depth chart. Players who are unavailable (IR, PUP, suspended) are listed "
     + "with their status rather than quietly removed.",
  mlb: "— the league’s own active rosters, refreshed through the day, pitchers "
     + "first. The games column is measured from our own logs: playing time is "
     + "still the depth chart, the league feed just decides who exists.",
  nba: "— built from who has actually appeared for each club this season, most "
     + "minutes-logged games first. Measured playing time is the depth chart here, "
     + "rather than somebody’s published guess at one.",
  wnba: "— built from who has actually appeared for each club this season, most "
      + "games first. Measured playing time is the depth chart here, rather than "
      + "somebody’s published guess at one.",
};

/* One player line. The depth slot is the staff's opinion and is shown as
   such; an unranked player gets no number rather than an invented one. */
function rosterPlayerHTML(p, byAppearance) {
  const slot = byAppearance
    ? (p.games != null ? String(p.games) : "—")
    : (p.depth_order ? `${escapeHtml(p.depth_pos || p.position)}${p.depth_order}` : "—");
  // The weekly designation, which the roster read for the first time on
  // 2026-08-13. "Questionable" is not unavailable — he may well play —
  // but it is the single most useful flag on a board where you are about
  // to price his volume, so it shows in its own right rather than being
  // flattened into "active".
  // Where the ESPN injury report adds something the roster feed did not.
  // `back` is the return date; `contested` fires only when BOTH feeds
  // filed and they disagree about whether he plays — a gap the merge
  // filled is not a disagreement, and marking those would flag most of
  // the board.
  const back = p.return_date
    ? ` · back ${escapeHtml(String(p.return_date).slice(5))}` : "";
  const contested = p.injury_conflict
    ? `<span class="chip warn" title="Sleeper and the ESPN injury report
         disagree about whether he plays. The more pessimistic reading is
         shown — this board never clears a player on one feed’s word.">${
         icon("warn")} feeds disagree</span>` : "";
  const tags = [
    p.rookie ? `<span class="chip">rookie</span>` : "",
    p.unavailable ? `<span class="chip down">${escapeHtml(p.status || "out")}${
      p.injury ? ` · ${escapeHtml(p.injury)}` : ""}${back}</span>` : "",
    (!p.unavailable && p.questionable)
      ? `<span class="chip warn">${escapeHtml(p.status || "questionable")}${
          p.injury ? ` · ${escapeHtml(p.injury)}` : ""}${back}</span>` : "",
    contested,
  ].join("");
  const colA = byAppearance
    ? (p.last_seen ? escapeHtml(String(p.last_seen).slice(5)) : "—")
    : (p.age != null ? p.age : "—");
  const colB = byAppearance
    ? "" : (p.years_exp != null ? (p.years_exp === 0 ? "R" : p.years_exp) : "—");
  return `<div class="ros-row${p.unavailable ? " out" : ""}">
    <span class="ros-slot">${escapeHtml(slot)}</span>
    <span class="ros-name">${playerAvatar(p.player, p.team,
        { size: 26, map: nflMap(), headshot: p.headshot })}${escapeHtml(p.player)}${tags}</span>
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
      <span class="ros-mark">${teamMark(abbr, 30, null, state.sport)}</span>
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
      <span class="ros-mark">${teamMark(abbr, 30, null, state.sport)}</span>
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
      rather than the league’s official tiebreakers.</span></div>
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

/* ============================================================
   INJURY REPORT — every sport, one page per league
   ============================================================
   Ethan, 2026-08-10: "we should have it for every sport and it should
   be easier to find them [than] digging through fantasy." This is the
   CURRENT-STATUS board off ESPN's league feeds — what the team filed,
   when, and the projected return. The nflverse practice-report detail
   stays on the fantasy page, where it feeds the usage model; this page
   answers the question you actually walk in with: who is out, league
   wide, right now. */

/* A designation's tone is about AVAILABILITY, not severity: "Out" and
   a 60-day IL read red because the player is not playing; the
   questionable tier reads amber because the answer is "maybe". Unknown
   wordings stay neutral rather than guessing. */
/* A cleared-to-play notice, not a designation. ESPN keeps a player in the
   injuries feed after he is available again — status "Active", no injury
   named — and every surface that treats those as injuries reports healthy
   players as hurt. Mirrors engine/sources/espninjuries.is_return. */
function isReturnRow(r) {
  return /^\s*active\s*$/i.test((r || {}).status || "") && !(r || {}).injury;
}

function injTone(status) {
  const s = (status || "").toLowerCase();
  if (/(^|\b)(out|injured reserve|ir\b|60-day|suspension|season)/.test(s)) return "var(--bad)";
  if (/(doubtful|questionable|day-to-day|10-day|15-day|7-day|game-time)/.test(s)) return "var(--warn)";
  if (/(probable|available|active)/.test(s)) return "var(--good)";
  return "var(--text-dim)";
}

/* A duration in seconds, said the way a person says it. */
function ageText(seconds) {
  const mins = (Number(seconds) || 0) / 60;
  if (mins < 90) return `${Math.round(mins)} min`;
  const hours = mins / 60;
  if (hours < 36) return `${Math.round(hours)} hours`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"}`;
}

function injWhen(ts) {
  if (!ts) return "—";
  const days = (Date.now() - ts) / 86400e3;
  if (days < 1) return "today";
  if (days < 2) return "yesterday";
  if (days < 14) return `${Math.floor(days)}d ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/* Rebuilt 2026-08-18 from a six-column agate table. Ethan, screenshot of
   his phone: "organize this page better as well. it seems so smooshed" —
   and it was: Team + Player + Status + Injury + Filed + Return at 393px
   crushed every column and pushed Status half off the screen behind an
   overflow scroll. A row is now two lines with nothing to crush: who and
   what on the left, the verdict on the right. Same facts, zero columns. */
/* ---- The injury layer, shared beyond the injuries page ----------------
   One cached fetch of the league-wide board, and one lookup any surface
   can tag a player with. Born from the Cade Mays report: the draft kit
   was happily ranking a man who broke his wrist the week before, and
   nothing outside the injuries tab would have said so. */
let _injBoard = null;
let _injBoardAt = 0;
async function loadInjuryBoard() {
  if (_injBoard && Date.now() - _injBoardAt < 5 * 60e3) return _injBoard;
  try {
    const res = await fetch("data/injuries.json?t=" + Date.now());
    if (res.ok) { _injBoard = await res.json(); _injBoardAt = Date.now(); }
  } catch (e) {}
  return _injBoard;
}

/* The tag is agate type, so the status has to fit in a breath. Longest
   keys first — "60-day il" must not stop at "il". */
const INJ_SHORT = [
  ["injured reserve", "IR"], ["60-day", "60-IL"], ["15-day", "15-IL"],
  ["10-day", "10-IL"], ["7-day", "7-IL"], ["day-to-day", "DTD"],
  ["questionable", "Q"], ["doubtful", "D"], ["suspension", "SUSP"],
  ["out", "OUT"],
];
function injShort(status) {
  const s = (status || "").toLowerCase();
  for (const [k, v] of INJ_SHORT) if (s.includes(k)) return v;
  return status || "";
}

function injFind(sport, player) {
  const rows = (((_injBoard || {}).sports) || {})[sport] || [];
  const want = ffNorm(player || "");
  return rows.find((r) => !isReturnRow(r)
    && ffNorm(r.player || "") === want) || null;
}

/* A compact colored designation beside a name, or nothing. The detail
   rides the title so the row stays agate. */
function injTag(sport, player) {
  const r = injFind(sport, player);
  if (!r) return "";
  const detail = [r.injury, r.return_date ? `return ${r.return_date}` : ""]
    .filter(Boolean).join(" · ");
  return ` <span class="inj-tag" style="color:${injTone(r.status)}"
    title="${escapeAttr([r.status, detail].filter(Boolean).join(" — "))}"
    >${escapeHtml(injShort(r.status))}</span>`;
}

/* The dossier and full profile get the whole sentence, not the tag. */
function injLineHTML(r) {
  if (!r) return "";
  const bits = [r.injury, r.return_date ? `return ${r.return_date}` : ""]
    .filter(Boolean).join(", ");
  return `<div class="ffd-injline" style="color:${injTone(r.status)}">
    ${escapeHtml(r.status)}${bits ? ` — ${escapeHtml(bits)}` : ""}</div>`;
}

function injRow(r, withTeam) {
  const face = r.face && /^https:\/\//.test(r.face)
    ? `<img class="inj-face" src="${escapeHtml(r.face)}" alt="" loading="lazy"
         onerror="this.style.display='none'">` : "";
  const what = [
    withTeam ? escapeHtml(r.team) : "",
    escapeHtml(r.injury || "undisclosed") + (r.side ? ` (${escapeHtml(r.side)})` : ""),
    `<span title="${escapeHtml(r.date || "")}">filed ${injWhen(r.ts)}</span>`,
  ].filter(Boolean).join(" · ");
  return `<div class="inj-line"${r.comment ? ` title="${escapeHtml(r.comment)}"` : ""}>
    ${face}
    <span class="inj-line-main">
      <span><b>${escapeHtml(r.player)}</b>${
        r.pos ? ` <span class="inj-pos">${escapeHtml(r.pos)}</span>` : ""}</span>
      <span class="inj-line-sub">${what}</span>
    </span>
    <span class="inj-line-right">
      <b style="color:${injTone(r.status)}">${escapeHtml(r.status)}</b>
      ${r.return_date ? `<span class="inj-line-ret">return ${escapeHtml(r.return_date)}</span>` : ""}
    </span>
  </div>`;
}

async function renderInjuries() {
  const host = document.getElementById("injuries-body");
  if (!host) return;
  let d = null;
  try {
    const res = await fetch("data/injuries.json?t=" + Date.now());
    if (res.ok) d = await res.json();
  } catch (e) {}
  const sport = state.sport || "nfl";
  const rows = (((d || {}).sports) || {})[sport] || [];
  if (!rows.length) {
    const note = sport === "cfb"
      ? `College programs have no duty to report, so this feed runs sparse —
         emptiness here is the league’s opacity, not a fault to chase.`
      : `Either nobody in the league carries a designation right now — rare —
         or the feed declined on the last pull. The launcher retries every
         refresh, and <code>python3 launch.py --check</code> probes the host.`;
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("signal", 30)}</div>
      <div class="es-title">No injury designations to show</div>
      <div class="es-sub">${note}</div></div>`;
    return;
  }

  const parsed = rows.map((r) => ({ ...r, ts: Date.parse(r.date || "") || 0 }))
    .sort((a, b) => b.ts - a.ts);
  const outTier = parsed.filter((r) => injTone(r.status) === "var(--bad)");
  const maybeTier = parsed.filter((r) => injTone(r.status) === "var(--warn)");
  // ESPN's NFL feed lists RETURNS too — hundreds of "Active" rows with
  // no injury named. They stay in the by-team groups (a return IS news
  // about that team) but out of the fresh strip, which exists to answer
  // "who just went down", not "who practiced".
  const fresh = parsed.filter((r) => r.ts >= Date.now() - 7 * 86400e3
      && !isReturnRow(r))
    .slice(0, 40);

  /* WHEN these rows were collected, which is not when this file was
     written. A declining feed is answered from cache and raises nothing,
     so the build stamps a fresh `generated_at` over data that stopped
     moving days ago — the page then reports it with full confidence.
     The builder measures the cache's own age; if it is far past the TTL
     this says so, loudly, instead of letting a stale board pass as live. */
  const ageS = (((d || {}).ages_s) || {})[sport];
  const staleAfter = (d || {}).stale_after_s || 3600;
  const staleBanner = (ageS != null && ageS > staleAfter) ? `
    <div class="card" style="border-left:3px solid var(--warn);margin-bottom:14px">
      <p style="margin:0;font-size:var(--fs-md)">${icon('warn')} <b>These designations are
        ${escapeHtml(ageText(ageS))} old.</b> ESPN’s feed has been declining, so the board is
        being served from the last successful pull — treat every status here as
        unconfirmed until it clears. Run <code>python3 launch.py --injuries</code> to see
        the error the feed is returning.</p></div>` : "";

  const byTeam = {};
  for (const r of parsed) (byTeam[r.team] = byTeam[r.team] || []).push(r);
  const teams = Object.keys(byTeam)
    .sort((a, b) => byTeam[b].length - byTeam[a].length || a.localeCompare(b));

  const tile = (k, v, sub) => `<div class="tile"><div class="k">${k}</div>
    <div class="v">${v}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;
  host.innerHTML = `
    ${staleBanner}
    <div class="stats">
      ${tile("Players listed", parsed.filter((r) => !isReturnRow(r)).length,
             "carrying a designation")}
      ${tile("Out tier", outTier.length, "out, IR, long-term IL")}
      ${tile("Questionable tier", maybeTier.length, "doubtful through day-to-day")}
      ${tile("Teams affected", teams.length, "of the whole league")}
    </div>
    ${fresh.length ? `
      <div class="section-title">Fresh this week
        <span class="sub">— designations filed in the last seven days, newest first.
        Hover a row for the team’s own wording.</span></div>
      <div class="card inj-list">${fresh.map((r) => injRow(r, true)).join("")}</div>` : ""}
    <div class="section-title">By team
      <span class="sub">— most banged-up first. Every current designation the league
      lists, not just this week’s.</span></div>
    ${teams.map((t) => `
      <div class="inj-team-head">${escapeHtml(t)}
        <span class="inj-team-n">${byTeam[t].length}</span></div>
      <div class="card inj-list">${byTeam[t].map((r) => injRow(r, false)).join("")}</div>`).join("")}
    <p style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:14px">
      Statuses are the league’s own filings via ESPN’s public feed, refreshed with the
      site on a 30-minute cache, one row per player — his newest filing. The NFL’s
      practice-level detail (limited/DNP, the usage model’s injury inputs) lives on the
      Fantasy page — this board is availability, league-wide.
      ${ageS != null
        ? `Designations collected ${escapeHtml(ageText(ageS))} ago.`
        : `Page built ${escapeHtml(((d || {}).generated_at || "").slice(11, 16))}.`}</p>`;
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
    /* WHERE THE NUMBERS CAME FROM. The page used to say "counted from our
       own results" whatever had happened — including when that count was
       a half-ingested season showing baseball clubs with ties. The build
       now stamps `source`, and this line reports it rather than asserting
       one of the two. */
    const live = d.source === "league";
    sub.textContent = d.season
      ? `— ${d.season} regular season · `
        + (live
          ? "the league’s own records, refreshed with the site"
          : `${(d.games_counted || 0).toLocaleString()} games counted from our own results (the league’s feed was unavailable)`)
        + ` · ${d.order_note || ""}`
      : (live ? "— the league’s own records."
              : "— counted from our own results.");
  }
  const groups = d.groups || [];
  if (!groups.length) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("chart", 30)}</div>
      <h3>No standings yet</h3><p>${escapeHtml(d.note
        || "Run `python3 standings_build.py` once.")}</p></div>`;
    return;
  }
  const b = d.bracket || {};
  /* A fallback table that LOOKS official is the failure this page just
     had. When the league’s feed was unavailable and these are our own
     counted games, say so above the table — not only in a note the empty
     state would have shown. */
  const fallbackBanner = (d.source === "computed" && d.note) ? `
    <div class="card" style="border-left:3px solid var(--warn);margin-bottom:14px">
      <p style="margin:0;font-size:var(--fs-md)">${icon('warn')} <b>These are our
        counted games, not the league’s table.</b> ${escapeHtml(d.note)}</p></div>` : "";
  host.innerHTML = `
    ${fallbackBanner}
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
        || "Run `python3 rosters_build.py` once to build this sport’s rosters.")}</p></div>`;
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
  // ANY note the build wrote gets shown, not just the unavailable one.
  //
  // `rosters_build` captures exactly why it fell back to appearances —
  // "built from appearances because the league feed failed (...) —
  // pitchers don't bat, so they are missing from this view" — and then
  // this line dropped it on the floor, because the fallback payload is
  // stamped feed:"live" (it IS live data, just from a different source).
  //
  // So the page Ethan looked at on 2026-08-13 listed 18 Cubs, every one
  // of them a position player, with nothing anywhere saying a whole half
  // of the roster was missing or why. The build had already done the work
  // of explaining itself; the page just had to print it. A missing
  // pitcher that announces itself is a known gap. A silent one is a
  // wrong roster.
  const stale = (d.note || "")
    ? `<div class="warning" style="margin-bottom:12px">${icon('warn')} ${escapeHtml(d.note)}</div>` : "";
  // Team changes come from diffing daily roster snapshots, which only the
  // NFL feed produces. Showing an empty "recent moves" panel for a sport
  // that cannot detect one would read as "no trades happened".
  const moves = d.transactions ? `
    <div class="section-title">Recent team changes
      <span class="sub">— from diffing this site’s own daily roster snapshots,
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

/* ---------------- League desk: lineup + trades --------------------------

   Ethan, 2026-08-15: "since league after draft to optimize line ups each
   week" and "Have a trade generator to generate trades and know if they
   will m be accepted or not."

   Both answers come from /api/leaguedesk, which reads the league's OWN
   scoring and roster slots. That matters more than it sounds: a half-PPR
   TE-premium superflex league does not have the same best lineup as the
   default, and a generic ranking answers a different league's question.

   ON ACCEPTANCE — the panel shows whether THEIR starting lineup improves
   too, by how much, and whether the deal is lopsided enough to read as an
   insult. It does not show a probability, because there is nothing to fit
   one on: this app has never stored a proposed trade. The note says so,
   and the log button is what makes it answerable later. */
async function renderLeagueDesk(leagueId, userId, platform, hostId) {
  const host = document.getElementById(hostId || "league-desk");
  if (!host) return;
  if (!leagueId) { host.innerHTML = ""; return; }
  host.innerHTML = `<p class="loading">Reading your league\u2019s scoring and rosters\u2026</p>`;
  let d;
  try {
    const r = await fetch(`/api/leaguedesk?league=${encodeURIComponent(leagueId)}`
      + `&user=${encodeURIComponent(userId || "")}`
      + `&platform=${encodeURIComponent(platform || "sleeper")}`);
    d = await r.json();
    if (!r.ok) throw new Error(d && d.error);
  } catch (e) {
    host.innerHTML = `<div class="warning">${icon("warn")} League desk unavailable: ${
      escapeHtml(String((e && e.message) || e))}</div>`;
    return;
  }
  if (!d.has_me) {
    host.innerHTML = `<div class="warning">${icon("warn")} No roster in this
      league belongs to you, so there is no lineup to optimise. Pick the
      right league above.</div>`;
    return;
  }
  host.innerHTML = ffLineupHTML(d) + ffScoringGapsHTML(d) + ffTradesHTML(d);
  host.querySelectorAll("[data-logtrade]").forEach((b) =>
    b.addEventListener("click", () => ffLogTrade(b)));
}

function ffLineupHTML(d) {
  const L = d.lineup || {};
  const starters = L.starters || [];
  return `
    <div class="section-title">Your best lineup
      <span class="sub">\u2014 scored under ${escapeHtml(d.league || "your league")}\u2019s
        own settings, not a generic ranking</span></div>
    <div class="card">
      <div class="ld-total">${L.total ?? 0} projected points</div>
      <div class="rank-scroll"><table class="rank-table"><thead><tr>
        <th>Slot</th><th class="rank-name">Player</th><th>Pos</th>
        <th>Proj</th><th>PPR base</th>
        </tr></thead><tbody>
        ${starters.map((s) => `<tr>
          <td class="rank-name">${escapeHtml(s.slot)}</td>
          <td class="rank-name">${s.player ? escapeHtml(s.player)
            : '<span class="rank-none">\u2014 nobody eligible</span>'}${
            s.thin ? ' <span class="chip warn">thin sample</span>' : ""}</td>
          <td>${escapeHtml(s.position || "")}</td>
          <td>${s.points ?? "\u2014"}</td>
          <td class="rank-none">${s.base_ppr ?? "\u2014"}</td></tr>`).join("")}
      </tbody></table></div>
      ${(L.swaps || []).length ? `<div class="ld-swaps">
        <div class="rank-fight-head">Change these</div>
        ${L.swaps.map((w) => `<div class="rank-fight-row">
          <b>${escapeHtml(w.slot)}</b>
          <span class="chip down">out ${escapeHtml(w.out)}</span>
          <span class="chip up">in ${escapeHtml(w.in)}</span>
          <span class="rank-spread">+${w.gain}</span></div>`).join("")}
      </div>` : `<p class="rank-help">Nothing to change \u2014 this is already
        the best legal lineup on your roster.</p>`}
      ${L.exact === false ? `<p class="rank-help">${icon("warn")} Scored from
        the PPR baseline with your league\u2019s differences applied where we
        store the component. These could not be adjusted for:
        <b>${(L.missing || []).map(escapeHtml).join(", ")}</b> \u2014 so those
        rules are not reflected.</p>` : ""}
      <p class="rank-help">${escapeHtml(L.note || "")}</p>
    </div>`;
}

/* The rules we did NOT apply, split in two because they mean opposite
   things. `unmapped` is a gap in our map and a bug to fix; `not_modelled`
   is the kicker and defense scoring this app has never projected. Showing
   one number for both would hide a real miss inside a known limit — which
   is the shape of the `pass_att` bug this repo already paid for. */
function ffScoringGapsHTML(d) {
  const un = d.unmapped_scoring || [];
  const nm = d.not_modelled_scoring || [];
  if (!un.length && !nm.length) return "";
  const name = (u) => escapeHtml(String(u.name || u.statId || u.stat_id || "?"))
    + ` <span class="rank-none">${u.points > 0 ? "+" : ""}${u.points}</span>`;
  return `<div class="card">
    ${un.length ? `<p class="rank-help">${icon("warn")} <b>Scoring rules we
      could not read</b>, so they are not in any projection above:
      ${un.map(name).join(", ")}. That is a gap in our map, not in your
      league — tell me and it is a one-line fix.</p>` : ""}
    ${nm.length ? `<p class="rank-help">Kicker and defense scoring is read
      but never projected — this app models offensive production only, so
      those ${nm.length} rule${nm.length === 1 ? "" : "s"} sit unused and
      those slots are filled by eligibility alone.</p>` : ""}
  </div>`;
}

/* ---------------- Yahoo, the one platform that needs approval ----------

   Ethan, 2026-08-15, plays on Sleeper, ESPN and Yahoo.

   WHY THERE IS A CONNECT BUTTON HERE AND NOWHERE ELSE ON THIS SITE.
   Sleeper is public. ESPN is public when a league says so. Yahoo has no
   public read at all — but it has the RIGHT kind of private one: you
   approve it on Yahoo’s own screen, this app never sees a password, and
   you can revoke it from your Yahoo account page whenever you like. That
   is the opposite of pasting a session cookie, which is why a private
   ESPN league is still refused and this is not.

   The token never reaches this page. The browser is told THAT it is
   connected, never what makes it work. */
async function renderYahooZone() {
  const zone = document.getElementById("yahoo-zone");
  if (!zone) return;
  let s;
  try {
    const r = await fetch("/api/yahoo/status");
    s = await r.json();
  } catch (e) { zone.innerHTML = ""; return; }

  if (!s.app_registered) {
    zone.innerHTML = `<div class="card">
      <div class="section-title">Yahoo league
        <span class="sub">— one free registration, then no password ever</span></div>
      <p class="rank-help">Yahoo is the only platform here that needs
        approval, and the only one whose access you can hand back. Register
        a free app at <b>developer.yahoo.com</b> (any name, permission
        “Fantasy Sports read”), then put the two values it gives you into
        <b>secrets.local</b> as <b>YAHOO_CLIENT_ID</b> and
        <b>YAHOO_CLIENT_SECRET</b>. Restart the server and this panel turns
        into a connect button.</p>
      <p class="rank-help">Those identify the APP, not you. On their own
        they cannot read anybody’s league — a human still has to approve it
        on Yahoo’s screen.</p></div>`;
    return;
  }
  if (!s.connected) {
    zone.innerHTML = `<div class="card">
      <div class="section-title">Yahoo league
        <span class="sub">— approve once on Yahoo’s own page</span></div>
      <p class="rank-help">Yahoo will show you a short code. Paste it back
        here. No password is shared with this app, and you can revoke it
        from your Yahoo account page at any time.</p>
      <div class="ld-connect">
        <button class="btn" id="yahoo-open">Open Yahoo’s approval page</button>
        <input id="yahoo-code" class="rank-input" placeholder="Paste the code Yahoo shows"
          autocomplete="off" spellcheck="false">
        <button class="btn ghost" id="yahoo-connect">Connect</button>
      </div>
      <p class="rank-help" id="yahoo-msg"></p></div>`;
    const msg = document.getElementById("yahoo-msg");
    document.getElementById("yahoo-open").addEventListener("click", async () => {
      try {
        const r = await fetch("/api/yahoo/start");
        const d = await r.json();
        if (!r.ok) throw new Error(d && d.error);
        window.open(d.url, "_blank", "noopener");
      } catch (e) {
        msg.textContent = String((e && e.message) || e);
      }
    });
    document.getElementById("yahoo-connect").addEventListener("click", async () => {
      const code = (document.getElementById("yahoo-code").value || "").trim();
      msg.textContent = "Exchanging the code…";
      try {
        const r = await fetch("/api/yahoo/connect", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d && d.error);
        renderYahooZone();
      } catch (e) {
        msg.textContent = String((e && e.message) || e);
      }
    });
    return;
  }

  zone.innerHTML = `<div class="card"><p class="loading">Reading your Yahoo
    leagues…</p></div>`;
  let leagues = [];
  try {
    const r = await fetch("/api/yahoo/leagues");
    const d = await r.json();
    if (!r.ok) throw new Error(d && d.error);
    leagues = d.leagues || [];
  } catch (e) {
    zone.innerHTML = `<div class="card"><div class="warning">${icon("warn")}
      Yahoo connected, but the league list failed: ${
        escapeHtml(String((e && e.message) || e))}</div></div>`;
    return;
  }
  let picked = localStorage.getItem("ff_yahoo_league") || "";
  if (!leagues.some((l) => l.league_key === picked))
    picked = (leagues[0] || {}).league_key || "";

  zone.innerHTML = `<div class="card">
    <div class="card-head">
      <div><div class="player">Yahoo league</div>
        <div class="subtitle">connected · read-only · revocable from your
          Yahoo account page</div></div>
      <div class="ld-connect">
        ${leagues.length ? `<select id="yahoo-league" class="rank-input">
          ${leagues.map((l) => `<option value="${escapeHtml(l.league_key)}"
            ${l.league_key === picked ? "selected" : ""}>${
            escapeHtml(l.name)}${l.season ? ` · ${escapeHtml(l.season)}` : ""}
            </option>`).join("")}</select>` : ""}
        <button class="btn ghost" id="yahoo-disconnect">Disconnect</button>
      </div>
    </div>
    ${leagues.length ? "" : `<p class="rank-help">This Yahoo account is not
      in any NFL league right now.</p>`}</div>`;

  document.getElementById("yahoo-disconnect").addEventListener("click", async () => {
    await fetch("/api/yahoo/disconnect", { method: "POST" });
    const desk = document.getElementById("yahoo-desk");
    if (desk) desk.innerHTML = "";
    renderYahooZone();
  });
  const sel = document.getElementById("yahoo-league");
  if (sel) sel.addEventListener("change", () => {
    localStorage.setItem("ff_yahoo_league", sel.value);
    acctTouch("fantasy");
    renderLeagueDesk(sel.value, "", "yahoo", "yahoo-desk");
  });
  if (picked) {
    localStorage.setItem("ff_yahoo_league", picked);
    renderLeagueDesk(picked, "", "yahoo", "yahoo-desk");
  }
}

function ffTradesHTML(d) {
  const trades = d.trades || [];
  const sum = d.trade_summary || {};
  return `
    <div class="section-title">Trades worth proposing
      <span class="sub">\u2014 only deals where BOTH starting lineups improve</span></div>
    <div class="card">
      ${trades.length ? trades.map((t, i) => `
        <div class="ld-trade">
          <div class="ld-trade-head">
            <b>${escapeHtml(t.with)}</b>
            <span class="chip up">you +${t.my_gain}</span>
            <span class="chip ${t.their_gain > 0 ? "up" : "down"}">them +${t.their_gain}</span>
            ${t.lopsided ? `<span class="chip down">lopsided by ${t.gap}
              \u2014 will read as a fleece</span>` : ""}
          </div>
          <div class="ld-trade-body">
            <span class="rank-none">you send</span> ${t.give.map(escapeHtml).join(", ")}
            <span class="rank-none">\u2192 you get</span> ${t.get.map(escapeHtml).join(", ")}
          </div>
          <button class="btn ghost" data-logtrade="${i}"
            data-trade="${escapeHtml(JSON.stringify(t))}">Log as sent</button>
        </div>`).join("")
        : `<p class="rank-help">No trade improves both starting lineups right
           now. That is a real answer \u2014 a deal that only helps you is a
           request, not a trade.</p>`}
      <p class="rank-help">${escapeHtml(sum.acceptance_note || "")}</p>
    </div>`;
}

function ffLogTrade(btn) {
  // Kept on this device, like My Bets. The point is to accumulate rows so
  // "will they accept" can eventually be answered from evidence.
  let log = [];
  try { log = JSON.parse(localStorage.getItem("ff_trade_log") || "[]"); }
  catch (e) { log = []; }
  let trade = null;
  try { trade = JSON.parse(btn.dataset.trade); } catch (e) { return; }
  log.push({ ts: Date.now(), sent: true, outcome: "", ...trade });
  localStorage.setItem("ff_trade_log", JSON.stringify(log));
  acctTouch("fantasy");
  btn.textContent = "Logged \u2713";
  btn.disabled = true;
}

/* ---------------- Rankings, side by side --------------------------------

   Ethan, 2026-08-15: "add where we show every books ranking side by side".

   TWO OF THE FOUR COLUMNS ARE BUILT SERVER-SIDE (our VORP board, and
   Sleeper's own search_rank out of the players blob) and arrive in the
   payload. The other two only exist in this browser: the live pick order
   in YOUR draft, and whatever list you pasted. So the merge happens here
   — `ffRankMerge` overlays those two onto the built rows and recomputes
   the consensus, which is the one piece of arithmetic that has to exist
   in both languages. It is median / min / max and nothing else, kept
   deliberately small for exactly that reason.

   THE TABLE IS NOT THE POINT — THE DISAGREEMENT IS. Four columns in
   near-identical order tells you nothing. The row where our board has a
   man thirty spots above Sleeper is either the edge or the bug, so that
   view is drawn FIRST and the full table sits under it. */
const FF_RANK_SOURCES = [["ours", "Our board"], ["sleeper", "Sleeper"],
                         ["adp", "Your draft"], ["imported", "Imported"]];
const FF_IMPORT_KEY = "ff_ranks_import";

function ffRankParseImport(text) {
  // Mirrors engine/fantasy_ranks.parse_import: a leading number is
  // trusted when present (a keeper list numbered 1,2,5 means those gaps);
  // otherwise position in the file is the rank.
  const out = {};
  let seen = 0;
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim().replace(/,+$/, "");
    if (!line || line.startsWith("#")) continue;
    let cells = line.split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""))
      .filter(Boolean);
    if (!cells.length) continue;
    let rank = null;
    let m = cells[0].match(/^(\d{1,3})[.)]?$/);
    if (m) { rank = +m[1]; cells = cells.slice(1); }
    else {
      m = cells[0].match(/^(\d{1,3})[.)]?\s+(.*)$/);
      if (m) { rank = +m[1]; cells = [m[2]].concat(cells.slice(1)); }
    }
    if (!cells.length) continue;
    const key = ffNorm(cells[0]);
    if (!key || ["player", "name", "rank", "overall"].includes(key)) continue;
    if (out[key] != null) continue;
    seen += 1;
    out[key] = rank == null ? seen : rank;
  }
  return out;
}

function ffRankMerge(rows, extra) {
  // `extra` is {key: {adp, imported}}. Rows the overlay knows about but
  // the build did not are APPENDED rather than dropped — a rookie taken
  // in your draft is absent from our board by construction, and losing
  // him here would hide the pick that just happened.
  const byKey = {};
  const out = (rows || []).map((r) => {
    const copy = { ...r, ranks: { ...r.ranks } };
    byKey[r.key] = copy;
    return copy;
  });
  Object.entries(extra || {}).forEach(([key, add]) => {
    let row = byKey[key];
    if (!row) {
      row = { key, player: (add.player || key), sources: 0,
              ranks: { ours: null, sleeper: null, adp: null, imported: null } };
      byKey[key] = row;
      out.push(row);
    }
    if (add.adp != null) row.ranks.adp = add.adp;
    if (add.imported != null) row.ranks.imported = add.imported;
  });
  out.forEach((r) => {
    const have = Object.values(r.ranks).filter((v) => v != null).sort((a, b) => a - b);
    r.sources = have.length;
    r.best = have.length ? have[0] : null;
    r.worst = have.length ? have[have.length - 1] : null;
    // Median, matching the engine: mean of the middle two when even.
    const n = have.length, mid = n >> 1;
    r.consensus = !n ? null
      : n % 2 ? have[mid] : Math.round(((have[mid - 1] + have[mid]) / 2) * 10) / 10;
    // A spread needs two opinions; one source disagreeing with nothing
    // is not a disagreement, and an ABSENCE is never a low opinion.
    r.spread = n >= 2 ? r.worst - r.best : null;
  });
  out.sort((a, b) => (a.consensus - b.consensus) || a.player.localeCompare(b.player));
  return out;
}

function ffRankDisagreements(rows, limit) {
  const out = [];
  for (const r of rows) {
    if (!r.spread || r.sources < 2) continue;     // 0 spread is agreement
    const per = Object.entries(r.ranks).filter(([, v]) => v != null);
    per.sort((a, b) => a[1] - b[1]);
    out.push({ ...r, high_source: per[0][0], low_source: per[per.length - 1][0] });
  }
  out.sort((a, b) => (b.spread - a.spread) || (a.consensus - b.consensus));
  return out.slice(0, limit || 12);
}

const ffSrcLabel = (k) => (FF_RANK_SOURCES.find((s) => s[0] === k) || [k, k])[1];

function rankBoardHTML(ranks) {
  if (!ranks) return "";
  return `
    <div class="section-title">Rankings, side by side
      <span class="sub">— every source we can read without a password, and
        where they argue</span></div>
    <div class="card" id="rank-card">
      <p class="pre-note" id="rank-coverage"></p>
      <div id="rank-fight"></div>
      <div id="rank-table" class="rank-scroll"></div>
      <details class="rank-import">
        <summary>Add a ranking of your own ▾</summary>
        <p class="rank-help">Paste any list you can already see — a
          FantasyPros export, your league’s board, a friend’s tiers. One
          player per line, or <code>rank,player</code>. This is the honest
          route to the sites this app can’t fetch: their rankings sit
          behind a paid key or a login, and this app never takes a
          password.</p>
        <textarea id="rank-paste" rows="6" spellcheck="false"
          placeholder="1,Ja’Marr Chase&#10;2,Bijan Robinson&#10;3,Justin Jefferson"></textarea>
        <div class="rank-btns">
          <button class="btn" id="rank-apply">Apply</button>
          <button class="btn ghost" id="rank-clear">Clear</button>
          <span id="rank-import-note"></span>
        </div>
      </details>
    </div>`;
}

function renderRankBoard() {
  const host = document.getElementById("rank-table");
  if (!host || !window._ffRanks) return;
  const built = window._ffRanks.rows || [];
  const extra = {};
  // Your draft's real pick order — the only ADP that is about YOUR league.
  Object.entries(dkState.adp || {}).forEach(([k, v]) => {
    (extra[k] = extra[k] || {}).adp = v.rank;
    extra[k].player = v.player;
  });
  let imported = {};
  try { imported = ffRankParseImport(localStorage.getItem(FF_IMPORT_KEY) || ""); }
  catch (e) { imported = {}; }
  Object.entries(imported).forEach(([k, v]) => {
    (extra[k] = extra[k] || {}).imported = v;
  });
  const rows = ffRankMerge(built, extra);
  const counts = {};
  FF_RANK_SOURCES.forEach(([k]) => {
    counts[k] = rows.filter((r) => r.ranks[k] != null).length;
  });
  const cov = document.getElementById("rank-coverage");
  if (cov) {
    cov.innerHTML = FF_RANK_SOURCES.map(([k, label]) =>
      `<span class="chip ${counts[k] ? "" : "ff-dim"}">${escapeHtml(label)}: ${
        counts[k] ? counts[k] : "—"}</span>`).join(" ")
      + ` <span class="rank-help">A blank cell means that source doesn’t
          list him — not that it ranked him last. Every rookie is absent
          from our board by construction, and scoring that as rank 999
          would put the whole rookie class at the top of the arguments.</span>`;
  }
  const fight = document.getElementById("rank-fight");
  const dis = ffRankDisagreements(rows, 10);
  if (fight) {
    fight.innerHTML = !dis.length ? "" : `
      <div class="rank-fight-head">Where they disagree most</div>
      <div class="rank-fight-rows">${dis.map((r) => `
        <div class="rank-fight-row" data-dossier="${escapeAttr(r.player)}">
          ${playerAvatar(r.player, r.team || "", { size: 22, map: nflMap(), headshot: r.headshot })}<b>${escapeHtml(r.player)}</b>
          <span class="chip up">${escapeHtml(ffSrcLabel(r.high_source))} ${
            r.ranks[r.high_source]}</span>
          <span class="chip down">${escapeHtml(ffSrcLabel(r.low_source))} ${
            r.ranks[r.low_source]}</span>
          <span class="rank-spread">${r.spread} apart</span>
        </div>`).join("")}</div>`;
  }
  const cell = (v) => v == null ? `<td class="rank-none">—</td>`
    : `<td>${v}</td>`;
  host.innerHTML = `<table class="rank-table"><thead><tr>
      <th>Player</th>${FF_RANK_SOURCES.map(([, l]) =>
        `<th>${escapeHtml(l)}</th>`).join("")}
      <th>Consensus</th><th>Spread</th></tr></thead><tbody>
      ${rows.slice(0, 200).map((r) => `<tr>
        <td class="rank-name" data-dossier="${escapeAttr(r.player)}">${playerAvatar(r.player, r.team || "", { size: 20, map: nflMap(), headshot: r.headshot })}${escapeHtml(r.player)}</td>
        ${FF_RANK_SOURCES.map(([k]) => cell(r.ranks[k])).join("")}
        <td>${r.consensus == null ? "—" : r.consensus}</td>
        ${cell(r.spread)}</tr>`).join("")}
    </tbody></table>`;
}

function initRankBoard() {
  const apply = document.getElementById("rank-apply");
  const box = document.getElementById("rank-paste");
  const note = document.getElementById("rank-import-note");
  if (!apply || !box) return;
  const saved = localStorage.getItem(FF_IMPORT_KEY) || "";
  if (saved) box.value = saved;
  const say = () => {
    const n = Object.keys(ffRankParseImport(box.value)).length;
    if (note) note.textContent = n ? `${n} player(s) read` : "";
  };
  say();
  apply.addEventListener("click", () => {
    localStorage.setItem(FF_IMPORT_KEY, box.value);
    acctTouch("fantasy");
    say();
    renderRankBoard();
  });
  const clear = document.getElementById("rank-clear");
  if (clear) clear.addEventListener("click", () => {
    box.value = "";
    localStorage.removeItem(FF_IMPORT_KEY);
    acctTouch("fantasy");
    say();
    renderRankBoard();
  });
  renderRankBoard();
}

function draftKitHTML(kit) {
  if (!kit || !(kit.board || []).length) return "";
  const BOARD_SHOWN = 15;
  const moveNote = (r) => r.moved_from
    ? ` · <span class="dk-moved" title="Traded or signed since these stats — the volume behind this projection came in ${escapeHtml(nflName(r.moved_from))}'s offense">NEW TEAM, was ${escapeHtml(r.moved_from)}</span>`
    : r.roster_flag
      ? ` · <span class="dk-moved">${escapeHtml(r.roster_flag)}</span>` : "";
  const boardRow = (r, i) => `
    <div class="dl-row dk-row" data-ffp="${escapeHtml(ffNorm(r.player))}" data-dossier="${escapeAttr(r.player)}">
      <span class="dl-rank">${i + 1}</span>
      <span class="dl-main dl-id">${playerAvatar(r.player, r.team, { size: 26, map: nflMap(), headshot: r.headshot })}
        <span><strong>${escapeHtml(r.player)}</strong>${injTag("nfl", r.player)}
          <span class="dl-sub">${escapeHtml(r.position)}${r.pos_rank} · ${nflName(r.team)}
            · ${r.games} gm${r.small_sample ? ` ${icon('warn')} small sample` : ""}${moveNote(r)}</span></span></span>
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
      return `${brk}<div class="dk-posrow" data-ffp="${escapeHtml(ffNorm(r.player))}" data-dossier="${escapeAttr(r.player)}">
        <span class="dk-pr">${r.pos_rank}</span>
        ${playerAvatar(r.player, r.team, { size: 18, map: nflMap(), headshot: r.headshot })}
        <span class="dk-pn">${escapeHtml(r.player)}${injTag("nfl", r.player)}
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
    <div class="dl-row dk-slrow" data-ffp="${escapeHtml(ffNorm(r.player))}" data-dossier="${escapeAttr(r.player)}">
      <span class="dl-main dl-id">${playerAvatar(r.player, r.team, { size: 26, map: nflMap(), headshot: r.headshot })}
        <span><strong>${escapeHtml(r.player)}</strong>${injTag("nfl", r.player)}
          <span class="dl-sub">${escapeHtml(r.position)} · ${nflName(r.team)}</span></span></span>
      <span class="dl-num">${r.ppg} actual</span>
      <span class="dl-num strong pos">${r.xppg} expected</span>
    </div>`).join("");

  return `
    <div class="section-title">Draft kit
      <span class="sub">— last season’s volume turned into value over replacement.
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
      <div id="dk-advice"></div>
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

/* ---------------- The fantasy player dossier ----------------
   Ethan, 2026-08-18: "we should be able too click on players and it will
   show us useful fantasy information for that player." Every surface on
   this page already KNOWS something about him — the kit knows his value,
   usage knows his role, the rankings know where the sources argue, camp
   knows whether he just won a job — but each surface only tells its own
   slice. Tap any name and the dossier assembles all of it, plus his real
   weekly volume charts off the game-log API.

   One overlay, one document-level delegation on [data-dossier] (the
   kit's existing data-ffp attribute belongs to the Sleeper cross-off
   and keeps its meaning). Sections render only when the surface behind
   them has the row — an empty panel would be a guess wearing a
   heading. */
let _ffData = null;               // the fantasy payload, captured at render

function _ffDossierInfo(name) {
  const d = _ffData || {};
  const kit = d.draft_kit || {};
  const eq = (r) => r && r.player === name;
  const inRows = (rows) => (rows || []).find(eq);
  const info = {
    name,
    kit: inRows(kit.board) || inRows(kit.sleepers)
      || Object.values(kit.tiers || {}).map(inRows).find(Boolean),
    usage: inRows(d.usage),
    buy: inRows((d.buy_sell || {}).buy_low),
    sell: inRows((d.buy_sell || {}).sell_high),
    rank: inRows((d.ranks || {}).rows),
    camp: inRows(((d.camp || {}).risers || []).concat(
      (d.camp || {}).fallers || [], (d.camp || {}).new_starters || [])),
    move: ((d.offseason || {}).moves || []).find((m) => m.player === name),
  };
  const sources = [info.kit, info.usage, info.buy, info.sell,
                   info.rank, info.camp].filter(Boolean);
  const first = sources[0] || {};
  info.team = first.team || (info.move || {}).to || "";
  info.position = first.position || "";
  // Any board that knows his face will do — the boards are stamped by
  // different ingests, so the first row to match his NAME is often not
  // the one carrying his headshot.
  info.headshot = (sources.find((s) => s.headshot) || {}).headshot || "";
  info.inj = injFind("nfl", name);
  return info;
}

function ffDossierHTML(info) {
  const sect = (title, body) =>
    `<div class="ffd-sect"><div class="ffd-h">${title}</div>${body}</div>`;
  const stat = (k, v) => v == null || v === "" ? ""
    : `<span class="ffd-stat"><span class="k">${k}</span><b>${v}</b></span>`;
  const parts = [];
  const k = info.kit;
  if (k && k.proj != null) {
    parts.push(sect("Draft value", `<div class="ffd-stats">
      ${stat("Proj PPG", k.proj)}${stat("Last season", k.ppg)}
      ${stat("xFP", k.xppg)}${stat("VORP", k.vorp != null ? "+" + k.vorp : null)}
      ${stat("Tier", k.tier)}${stat("Pos rank", k.position && k.pos_rank
        ? k.position + k.pos_rank : null)}
    </div>`));
  }
  const u = info.usage;
  if (u) {
    parts.push(sect(`Usage — team ${escapeHtml(u.metric || "volume")}`,
      `<div class="ffd-stats">
      ${stat("Season", pct(u.season))}${stat("Last 4 wks", pct(u.l4))}
      ${stat("Last week", pct(u.last))}
      ${stat(u.rz_label || "RZ/g", u.rz_pg)}${stat("PPR/g", u.fp_pg)}
    </div><p class="ffd-note">${u.delta == null || Math.abs(u.delta) < 0.03
      ? "Role steady vs the last four weeks"
      : `${u.delta > 0 ? "\u25b2 +" : "\u25bc \u2212"}${Math.abs(u.delta * 100).toFixed(0)}pt vs his 4-week share`}
      — the delta is the money: a riser at 42% beats a flat 60%.</p>`));
  }
  const bs = info.buy || info.sell;
  if (bs) {
    parts.push(sect(info.buy ? "Buy low" : "Sell high", `<div class="ffd-stats">
      ${stat("Actual PPG", bs.actual_ppg)}${stat("Expected", bs.expected_ppg)}
      ${stat("Gap", (bs.gap > 0 ? "+" : "") + bs.gap)}
    </div><p class="ffd-note">${info.buy
      ? "Expected points say the production is coming — his chances are worth more than he has scored from them so far."
      : "Producing above what the opportunity supports — regression risk."}</p>`));
  }
  const r = info.rank;
  if (r && r.consensus != null) {
    const srcs = Object.entries(r.ranks || {})
      .filter(([, v]) => v != null)
      .map(([s, v]) => stat(ffSrcLabel(s), v)).join("");
    parts.push(sect("Where the rankings put him", `<div class="ffd-stats">
      ${stat("Consensus", r.consensus)}${stat("Spread", r.spread)}${srcs}
    </div>`));
  }
  if (info.camp) {
    const c = info.camp;
    parts.push(sect("Camp", `<p class="ffd-note">${escapeHtml(c.position || "")}
      depth chart: ${escapeHtml(String(c.from_order ?? "—"))} →
      ${escapeHtml(String(c.to_order ?? "—"))}${c.rookie ? " · rookie" : ""}</p>`));
  }
  if (info.move) {
    parts.push(sect("New team", `<p class="ffd-note">${escapeHtml(info.move.from || "?")}
      → ${escapeHtml(info.move.to || "?")} — last season\u2019s volume came in a
      different offense.</p>`));
  }
  if (!parts.length) {
    parts.push(`<p class="ffd-note">No fantasy read on him this season —
      the boards are built from last season\u2019s volume and this camp.</p>`);
  }
  return `
    <div class="ffd-head">
      ${playerAvatar(info.name, info.team, { size: 52, map: nflMap(),
                                             headshot: info.headshot })}
      <div class="ffd-who"><b>${escapeHtml(info.name)}</b>
        <span class="ffd-sub">${info.team ? teamMark(info.team, 16, nflMap(), "nfl") : ""}
          ${escapeHtml([nflName(info.team) || info.team, info.position]
            .filter(Boolean).join(" · "))}</span>${injLineHTML(info.inj)}</div>
      <button class="btn ghost ffd-close" aria-label="Close">${icon("cross", 14)}</button>
    </div>
    ${parts.join("")}
    <div class="ffd-sect" id="ffd-charts"><div class="ffd-h">Weekly volume</div>
      <p class="ffd-note">Loading his game log\u2026</p></div>`;
}

async function _ffDossierCharts(name, position) {
  const zone = document.getElementById("ffd-charts");
  if (!zone) return;
  const stats = await leagueLogs(name);   // sport-scoped; fantasy is NFL
  if (!document.getElementById("ffd-charts")) return;   // closed meanwhile
  const want = position === "QB"
    ? ["Passing Yards", "Carries"]
    : position === "RB" ? ["Carries", "Targets"]
    : ["Targets", "Receiving Yards"];
  const have = want.filter((w) => (stats[w] || []).length)
    .concat(Object.keys(stats).filter((s) => !want.includes(s)))
    .filter((s, i, a) => a.indexOf(s) === i).slice(0, 2);
  if (!have.length) {
    zone.innerHTML = `<div class="ffd-h">Weekly volume</div>
      <p class="ffd-note">No game logs on this machine — the droplet and
      the laptop fill these in.</p>`;
    return;
  }
  zone.innerHTML = `<div class="ffd-h">Weekly volume — last ${
      (stats[have[0]] || []).length} games</div>`
    + have.map((label) => {
      const logs = stats[label] || [];
      return `<div class="ffd-chart"><span class="ffd-chart-l">${escapeHtml(label)}</span>
        ${gamelogBars(logs.map((g) => g.value), {
          w: 320, h: 56, stroke: "var(--brand)",
          labels: logs.map((g) => `Wk ${g.week} ${g.home ? "vs" : "@"} ${g.opponent}`),
        })}</div>`;
    }).join("");
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

async function ffFetchProfile(name) {
  try {
    const r = await fetch(`/api/players/fantasy?player=${encodeURIComponent(name)}`);
    if (r.ok) {
      const p = await r.json();
      if (p && p.player) return p;
    }
  } catch (e) {}
  return null;
}

//: Snap-share ring — the render's donut, in house strokes.
function ffRing(pctVal, label) {
  const r = 34, c = 2 * Math.PI * r;
  const on = Math.max(0, Math.min(100, pctVal)) / 100 * c;
  return `<svg class="ffp-ring" viewBox="0 0 84 84" aria-hidden="true">
    <circle cx="42" cy="42" r="${r}" fill="none" stroke="var(--border)" stroke-width="7"/>
    <circle cx="42" cy="42" r="${r}" fill="none" stroke="var(--brand)" stroke-width="7"
      stroke-dasharray="${on.toFixed(1)} ${c.toFixed(1)}"
      stroke-linecap="butt" transform="rotate(-90 42 42)"/>
    <text x="42" y="40" text-anchor="middle" font-size="17" font-weight="800"
      fill="var(--text)">${Math.round(pctVal)}%</text>
    <text x="42" y="54" text-anchor="middle" font-size="7.5"
      fill="var(--text-mute)">${escapeHtml(label)}</text>
  </svg>`;
}

function _ffTakeaways(p, info) {
  const out = [];
  const k = info.kit;
  if (k && k.vorp != null) {
    out.push(`Tier ${k.tier} on the value board — ${k.position}${k.pos_rank}, `
      + `VORP +${k.vorp} over a replacement ${k.position}.`);
  }
  const u = info.usage;
  if (u && u.delta != null && Math.abs(u.delta) >= 0.03) {
    out.push(u.delta > 0
      ? `Role growing: +${(u.delta * 100).toFixed(0)}pt of team ${u.metric || "volume"} vs his 4-week average.`
      : `Role shrinking: \u2212${Math.abs(u.delta * 100).toFixed(0)}pt of team ${u.metric || "volume"} vs his 4-week average.`);
  }
  if (info.buy) out.push("Buy low — expected points say the production is coming.");
  if (info.sell) out.push("Sell high — producing above what the opportunity supports.");
  if (info.camp) out.push(`Camp mover: depth chart ${info.camp.from_order ?? "—"} \u2192 ${info.camp.to_order ?? "—"}.`);
  if (info.move) out.push(`New team (${info.move.from} \u2192 ${info.move.to}) — last season\u2019s volume came in a different offense.`);
  const nx = ((p.schedule || {}).next || [])[0];
  if (nx && nx.def_rank) {
    const of = (p.schedule || {}).def_rank_of;
    const soft = nx.def_rank > of * 0.67;
    out.push(`Opens ${nx.home ? "vs" : "@"} ${nx.opponent}, the No. ${nx.def_rank} `
      + `defense by fantasy points allowed to ${p.position}s `
      + `(${nx.allowed_pg}/g${soft ? " — a soft matchup" : ""}).`);
  }
  return out.slice(0, 4);
}

function ffProfileHTML(p, info, bio) {
  const marks = (t) => teamMark(t, 26, nflMap(), "nfl");
  const chip = (k, v) => v == null || v === "" ? ""
    : `<span class="ffp-bio"><span class="k">${k}</span><b>${v}</b></span>`;
  const tiles = (p.season_stats || []).map((t) => `
    <div class="ffp-tile"><b>${t.market === "fp_ppr" && t.per_game != null
        ? t.per_game : t.total}</b>
      <span class="k">${escapeHtml(t.market === "fp_ppr" ? "PPR pts/g" : t.label)}</span>
      ${t.rank ? `<span class="ffp-rank">${ordinal(t.rank)} of ${t.of}</span>` : ""}
    </div>`).join("");
  const k = info.kit || {};
  const tierDots = k.tier
    ? Array.from({ length: 5 }, (_, i) =>
        `<span class="ffp-dot${i < Math.max(1, 6 - k.tier) ? " on" : ""}"></span>`).join("")
    : "";
  // The render's little trend line in the projection tile \u2014 his own
  // last four weeks, PPR, not a modeled curve.
  const wk4 = (p.weekly || []).slice(-4);
  const projTrend = wk4.length >= 2 ? `
      <div class="ffp-proj-trend">${gamelogBars(wk4.map((w) => w.fp), {
        w: 150, h: 30, stroke: "var(--brand)",
        labels: wk4.map((w) => `Wk ${w.week}`),
      })}<span class="k">last ${wk4.length} weeks (PPR)</span></div>` : "";
  const proj = k.proj != null ? `
    <div class="ffp-proj card">
      <div class="ffd-h">Board projection</div>
      <b class="ffp-proj-n">${k.proj}</b>
      <span class="k">projected PPG, from last season\u2019s volume</span>
      ${k.pos_rank ? `<div class="ffp-proj-r">${escapeHtml(k.position)} rank <b>${k.pos_rank}</b></div>` : ""}
      ${tierDots ? `<div class="ffp-proj-r">Tier ${k.tier} ${tierDots}</div>` : ""}
      ${projTrend}
    </div>` : "";
  const weekly = p.weekly || [];
  // The render's floor/median/ceiling strip, sourced from the one place
  // a range honestly exists: his OWN weeks. Worst, median and best of
  // the season's games — measured, not modeled.
  let range = "";
  if (weekly.length >= 4) {
    const fps = weekly.map((w) => Number(w.fp) || 0).sort((a, b) => a - b);
    const med = fps.length % 2 ? fps[(fps.length - 1) / 2]
      : (fps[fps.length / 2 - 1] + fps[fps.length / 2]) / 2;
    const lo = fps[0], hi = fps[fps.length - 1];
    const at = (v) => hi > lo ? (100 * (v - lo) / (hi - lo)) : 50;
    range = `
    <div class="card ffp-panel"><div class="ffd-h">Weekly range — ${p.season} (PPR)</div>
      <div class="ffp-range"><span class="ffp-range-med"
        style="left:${at(med).toFixed(1)}%"></span></div>
      <div class="ffp-rangelbl">
        <span>Worst week<br><b>${lo.toFixed(1)}</b></span>
        <span class="mid">Median<br><b>${med.toFixed(1)}</b></span>
        <span class="end">Best week<br><b>${hi.toFixed(1)}</b></span>
      </div></div>`;
  }
  const fpChart = weekly.length >= 3 ? `
    <div class="card ffp-panel"><div class="ffd-h">Fantasy points — last ${weekly.length} games (PPR)</div>
      ${gamelogBars(weekly.map((w) => w.fp), {
        w: 320, h: 64, stroke: "var(--brand)",
        labels: weekly.map((w) => `Wk ${w.week} ${w.home ? "vs" : "@"} ${w.opponent}`),
      })}</div>` : "";
  const sc = p.schedule || {};
  const of = sc.def_rank_of || 32;
  const match = (sc.next || []).length ? `
    <div class="card ffp-panel"><div class="ffd-h">Matchup strength — next ${sc.next.length}</div>
      ${sc.next.map((n) => `
        <div class="ffp-mrow">
          <span class="ffp-mopp">${n.home ? "vs" : "@"} ${escapeHtml(n.opponent)}</span>
          ${n.def_rank ? `<span class="ffp-mbar"><i style="width:${
            Math.round(100 * n.def_rank / of)}%"></i></span>
          <span class="ffp-mnum">${ordinal(n.def_rank)}</span>
          <span class="ffp-mfp">${n.allowed_pg} FP/g</span>`
          : `<span class="ffp-mnum mute">no read yet</span>`}
        </div>`).join("")}
      <p class="ffd-note">Defenses ranked 1\u2013${of} by fantasy points per game
        allowed to ${escapeHtml(p.position)}s in ${sc.def_rank_season} —
        higher rank, softer matchup.</p></div>` : "";
  const u = p.utilization || {};
  const util = `
    <div class="card ffp-panel"><div class="ffd-h">Utilization</div>
      <div class="ffp-util">
        ${u.snap_pct != null ? ffRing(u.snap_pct, "SNAP SHARE") : ""}
        <div class="ffp-util-rows">
          ${(u.rows || []).map(([kk, v]) => `<div class="ffp-urow">
            <span>${escapeHtml(kk)}</span><b>${v}</b></div>`).join("")}
          ${u.fp_pg != null ? `<div class="ffp-urow"><span>PPR points / game</span><b>${u.fp_pg}</b></div>` : ""}
          ${u.xfp_pg != null ? `<div class="ffp-urow"><span>Expected FP / game</span><b>${u.xfp_pg}</b></div>` : ""}
        </div>
      </div></div>`;
  const gl = p.gamelog || {};
  const colLabel = (m) => (Object.fromEntries(
    (POSITION_STATS_LABELS[p.position] || [])) || {})[m] || m;
  const log = (gl.rows || []).length ? `
    <div class="card ffp-panel" style="padding:0;overflow-x:auto">
      <table class="agate ffp-log"><thead><tr><th>Wk</th><th>Opp</th><th>Result</th>
        ${(gl.columns || []).map((c) => `<th>${escapeHtml(colLabel(c))}</th>`).join("")}
        <th>FPTS</th></tr></thead><tbody>
      ${gl.rows.map((r) => `<tr><td>${r.week}</td>
        <td>${r.home ? "vs" : "@"} ${escapeHtml(r.opponent)}</td>
        <td class="${(r.result || "").startsWith("W") ? "hit" : (r.result || "").startsWith("L") ? "miss" : ""}">${escapeHtml(r.result || "—")}</td>
        ${(r.cols || []).map((v) => `<td class="num">${v != null ? v : "—"}</td>`).join("")}
        <td class="num"><b>${r.fp != null ? r.fp : "—"}</b></td></tr>`).join("")}
      </tbody></table></div>` : "";
  const up = sc.upcoming;
  const implied = up && up.spread != null && up.total != null
    ? (up.total / 2 + (up.we_are_home === (up.spread < 0) ? Math.abs(up.spread) : -Math.abs(up.spread)) / 2).toFixed(1)
    : null;
  const upcoming = up ? `
    <div class="card ffp-panel"><div class="ffd-h">Upcoming game</div>
      <div class="ffp-up">
        <span class="ffp-upteam">${marks(up.away_team)} <b>${escapeHtml(up.away_team)}</b></span>
        <span class="gs-at">@</span>
        <span class="ffp-upteam">${marks(up.home_team)} <b>${escapeHtml(up.home_team)}</b></span>
      </div>
      <p class="ffd-note">${escapeHtml(up.date)}${up.kickoff ? ` · ${escapeHtml(up.kickoff)} ET` : ""}</p>
      ${up.spread != null || up.total != null ? `<div class="ffp-upnums">
        ${up.spread != null ? `<span class="ffp-bio"><span class="k">Spread</span>
          <b>${up.home_team === p.team ? (up.spread > 0 ? "+" : "") + up.spread
              : (up.spread < 0 ? "+" : "\u2212") + Math.abs(up.spread)} ${escapeHtml(p.team)}</b></span>` : ""}
        ${up.total != null ? `<span class="ffp-bio"><span class="k">Total</span><b>${up.total}</b></span>` : ""}
        ${implied ? `<span class="ffp-bio"><span class="k">Implied ${escapeHtml(p.team)}</span><b>${implied}</b></span>` : ""}
      </div>` : ""}</div>` : "";
  const takes = _ffTakeaways(p, info);
  return `
    <div class="ffd-head ffp-head">
      ${playerAvatar(p.player, p.team, { size: 76, map: nflMap(),
                                         headshot: p.headshot || info.headshot })}
      <div class="ffd-who">
        <b class="ffp-name">${escapeHtml(p.player)}</b>
        <span class="ffd-sub">${teamMark(p.team, 16, nflMap(), "nfl")}
          ${escapeHtml([nflName(p.team) || p.team, p.position,
                        bio && bio.number != null ? "#" + bio.number : ""]
            .filter(Boolean).join(" \u00b7 "))}</span>${injLineHTML(injFind("nfl", p.player))}
        <span class="ffp-bios">
          ${chip("HT", bio && bio.height)}${chip("WT", bio && bio.weight)}
          ${chip("Age", bio && bio.age)}${chip("Exp", bio && bio.years_exp != null
            ? (bio.years_exp === 0 ? "Rookie" : bio.years_exp + " yr") : null)}
          ${chip("College", bio && bio.college)}
          ${chip("Games", p.games)}${chip("Season", p.season)}
        </span>
      </div>
      <button class="btn ghost ffd-close" aria-label="Close">${icon("cross", 14)}</button>
    </div>
    <div class="ffp-top">
      <div class="ffp-stats card"><div class="ffd-h">${p.season} season</div>
        <div class="ffp-tiles">${tiles}</div></div>
      ${proj}
    </div>
    <div class="ffp-grid">
      ${fpChart}${range}${match}${util}${log}${upcoming}
    </div>
    ${takes.length ? `<div class="card ffp-panel"><div class="ffd-h">Key takeaways</div>
      ${takes.map((t) => `<p class="ffp-take">${icon("check", 14)} ${t}</p>`).join("")}
    </div>` : ""}`;
}

const POSITION_STATS_LABELS = {
  QB: [["pass_yds", "Pass yds"], ["pass_td", "Pass TD"], ["pass_int", "INT"]],
  RB: [["carries", "Car"], ["rush_yds", "Rush yds"], ["rush_td", "Rush TD"]],
  WR: [["targets", "Tgt"], ["receptions", "Rec"], ["rec_yds", "Rec yds"]],
  TE: [["targets", "Tgt"], ["receptions", "Rec"], ["rec_yds", "Rec yds"]],
};

function openFfDossier(name) {
  let ov = document.getElementById("ffd-overlay");
  if (!ov) {
    ov = document.createElement("div");
    ov.id = "ffd-overlay";
    document.body.appendChild(ov);
    ov.addEventListener("click", (e) => {
      if (e.target === ov || e.target.closest(".ffd-close")) closeFfDossier();
    });
  }
  const info = _ffDossierInfo(name);
  ov.innerHTML = `<div class="ffd-card" role="dialog"
    aria-label="Fantasy dossier: ${escapeAttr(name)}">${ffDossierHTML(info)}</div>`;
  ov.classList.add("open");
  document.body.classList.add("ffd-open");
  _ffDossierCharts(name, info.position);
  // The full page, when the profile API answers (Ethan's render,
  // 2026-08-18). The compact card above is already on screen, so a
  // static host or a cold API costs nothing but the upgrade.
  ffFetchProfile(name).then(async (p) => {
    if (!p) return;
    const card = ov.querySelector(".ffd-card");
    if (!card || !ov.classList.contains("open")) return;
    let bio = null;
    try {
      const ros = await loadRosters("nfl");
      for (const t of Object.values(ros.teams || {})) {
        bio = (t.players || []).find((x) => x.player === name) || bio;
      }
    } catch (e) {}
    if (!ov.classList.contains("open")) return;
    card.classList.add("ffd-full");
    card.innerHTML = ffProfileHTML(p, info, bio);
  });
}

function closeFfDossier() {
  const ov = document.getElementById("ffd-overlay");
  if (ov) ov.classList.remove("open");
  document.body.classList.remove("ffd-open");
}

// Bound ONCE at load — the fantasy page re-renders constantly and a
// per-render binding would stack listeners.
document.addEventListener("click", (e) => {
  const t = e.target.closest && e.target.closest("[data-dossier]");
  if (t) openFfDossier(t.dataset.dossier);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeFfDossier();
});

/* ---------------- The fantasy calendar ----------------
   Ethan, 2026-08-18: "a calendar layout page displaying the best
   possible player to play in fantasy for that day … click on that
   specific day and we will show a list of the 5 best fantasy players
   … and in-depth analysis on why."

   Everything here is a JOIN of numbers the payload already defends:
   the kit's projection is the baseline, the game script's implied
   team points are the environment, and the day's score is simply
   baseline × (implied ÷ league-average implied) — shown as that
   arithmetic, never as an oracle. A man ruled out or on IR cannot be
   the best play on any day, so the out-tier is excluded by name. */
let _ffCalSel = null;
let _ffCalPick = null;    // player loaded in the right-hand read panel

function _ffImpliedAvg(d) {
  const vals = [];
  (d.scripts || []).forEach((s) => {
    if (s.home_implied != null) vals.push(s.home_implied);
    if (s.away_implied != null) vals.push(s.away_implied);
  });
  return vals.length
    ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

/* date → one entry per TEAM playing that day, wearing its script. */
function _ffDayEnv(d) {
  const byKey = {};
  (d.scripts || []).forEach((s) => { byKey[`${s.home}|${s.away}`] = s; });
  const days = {};
  (d.schedule || []).forEach((g) => {
    const s = byKey[`${g.home}|${g.away}`] || null;
    const push = (team, opp, home) => {
      (days[g.date] = days[g.date] || []).push({
        team, opp, home, week: g.week, time: g.time,
        implied: s ? (home ? s.home_implied : s.away_implied) : null,
        total: s ? s.total : null, spread: s ? s.spread : null,
        archetype: s ? s.archetype : null, read: s ? s.read : null });
    };
    push(g.home, g.away, true);
    push(g.away, g.home, false);
  });
  return days;
}

/* The day's board: every kit player whose team plays that date, scored
   and sorted. Ruled-out players are RETURNED separately so the panel
   can say who was excluded instead of silently thinning. */
function _ffDayBoard(d, date) {
  const env = _ffDayEnv(d)[date] || [];
  const byTeam = {};
  env.forEach((e) => { byTeam[e.team] = e; });
  const avg = _ffImpliedAvg(d);
  const rows = [], out = [];
  for (const r of ((d.draft_kit || {}).board || [])) {
    const e = byTeam[r.team];
    if (!e) continue;
    const inj = injFind("nfl", r.player);
    if (inj && injTone(inj.status) === "var(--bad)") {
      out.push({ r, inj });
      continue;
    }
    const mult = e.implied != null && avg ? e.implied / avg : 1;
    rows.push({ r, e, inj, mult, score: (Number(r.proj) || 0) * mult });
  }
  rows.sort((a, b) => b.score - a.score);
  return { rows, out };
}

const FFCAL_DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const FFCAL_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FFCAL_MON_FULL = ["January", "February", "March", "April", "May",
                        "June", "July", "August", "September", "October",
                        "November", "December"];
let _ffCalMonth = null;   // "YYYY-MM" being shown

function _ffCalSay(date) {
  const [y, m, dd] = date.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, dd));
  return `${FFCAL_DOW[dt.getUTCDay()]} ${FFCAL_MON[m - 1]} ${dd}`;
}

/* Per-date slate quality, from the same score every card prints.
   "Elite" is the top quarter of game days BY that number — the cut is
   computed from the season itself, never hand-picked. */
function _ffCalQual(d) {
  const days = _ffDayEnv(d);
  const out = {};
  for (const date of Object.keys(days)) {
    const { rows } = _ffDayBoard(d, date);
    const top = rows.slice(0, 5);
    out[date] = { games: days[date].length / 2, best: top[0] || null,
                  top5: top.length
                    ? top.reduce((s, x) => s + x.score, 0) / top.length : 0 };
  }
  const vals = Object.values(out).map((q) => q.top5).sort((a, b) => a - b);
  const cut = vals.length ? vals[Math.floor(vals.length * 0.75)] : Infinity;
  for (const q of Object.values(out)) {
    q.tier = q.top5 >= cut ? "elite" : q.games >= 4 ? "slate" : "light";
  }
  return out;
}

function ffCalendarHTML(d) {
  const days = _ffDayEnv(d);
  const dates = Object.keys(days).sort();
  if (!dates.length) {
    return `<div class="empty-slate"><div class="es-icon">${icon("calendar", 30)}</div>
      <div class="es-title">No schedule on this machine yet</div>
      <div class="es-sub">The calendar builds from the league schedule the fantasy
        build reads — it fills on the next build once the schedule cache exists.</div></div>`;
  }
  if (!_ffCalSel || !days[_ffCalSel]) _ffCalSel = dates[0];
  if (!_ffCalMonth) _ffCalMonth = _ffCalSel.slice(0, 7);
  const qual = _ffCalQual(d);
  const [yy, mm] = _ffCalMonth.split("-").map(Number);
  // Weeks covering the shown month: the Sunday on/before the 1st,
  // through the Saturday after the last day. Neighbour-month days stay
  // visible but dimmed, the way every calendar reads.
  const first = new Date(Date.UTC(yy, mm - 1, 1));
  first.setUTCDate(first.getUTCDate() - first.getUTCDay());
  const lastDay = new Date(Date.UTC(yy, mm, 0)).getUTCDate();
  const weeks = Math.ceil((new Date(Date.UTC(yy, mm - 1, 1)).getUTCDay()
                           + lastDay) / 7);
  const cells = [];
  for (let i = 0; i < weeks * 7; i++) {
    const dt = new Date(first);
    dt.setUTCDate(first.getUTCDate() + i);
    const iso = dt.toISOString().slice(0, 10);
    const inMonth = dt.getUTCMonth() === mm - 1;
    const q = days[iso] ? qual[iso] : null;
    cells.push(`<div class="ffcal-cell${q ? "" : " ffcal-empty"}${
        inMonth ? "" : " ffcal-other"}${iso === _ffCalSel ? " sel" : ""}${
        q && q.tier === "elite" ? " ffcal-elite" : ""}"${
        q ? ` data-calday="${iso}" role="button" tabindex="0"` : ""}>
      <span class="ffcal-num">${dt.getUTCDate()}</span>
      ${q ? `<span class="ffcal-mark ${q.tier}"></span>` : ""}
      ${q && q.best ? `<span class="ffcal-best">${playerAvatar(q.best.r.player,
          q.best.r.team, { size: 18, map: nflMap(), headshot: q.best.r.headshot })}
        <b>${escapeHtml((q.best.r.player || "").split(" ").slice(-1)[0])}</b>
        <span class="ffcal-pts">${q.best.score.toFixed(1)}</span></span>` : ""}
    </div>`);
  }
  const sel = qual[_ffCalSel] || {};
  const board = _ffDayBoard(d, _ffCalSel);
  const outN = board.out.length;
  // The render's per-sport count chips, translated to the one league
  // this calendar actually covers: playable positions on the day.
  const posN = {};
  board.rows.forEach((x) => {
    posN[x.r.position] = (posN[x.r.position] || 0) + 1;
  });
  const posChips = ["QB", "RB", "WR", "TE"]
    .concat(Object.keys(posN).filter((p) => !["QB", "RB", "WR", "TE"].includes(p)))
    .filter((p) => posN[p])
    .map((p) => `<span class="chip">${escapeHtml(p)} ${posN[p]}</span>`).join("");
  return `
    <div class="section-title">The start calendar
      <span class="sub">— each game day wears its best play: the board’s projection
      scaled by that day’s game environment. Tap a day for the top five and the
      arithmetic behind each.</span></div>
    <div class="ffcal-legend">
      <span><span class="ffcal-mark elite"></span> Elite slate — a top-quarter
        day by projected points</span>
      <span><span class="ffcal-mark slate"></span> Game day</span>
      <span><span class="ffcal-mark light"></span> Light slate</span>
    </div>
    <div class="ffcal-layout">
    <div class="ffcal-left">
    <div class="ffcal-nav">
      <button class="btn ghost" type="button" data-calnav="-1" aria-label="Previous month">‹</button>
      <b class="ffcal-month">${FFCAL_MON_FULL[mm - 1]} ${yy}</b>
      <button class="btn ghost" type="button" data-calnav="1" aria-label="Next month">›</button>
      <button class="btn ghost ffcal-today" type="button" data-calnav="first">First slate</button>
    </div>
    <div class="ffcal-head">${FFCAL_DOW.map((w) => `<span>${w}</span>`).join("")}</div>
    <div class="ffcal-grid" id="ffcal-grid">${cells.join("")}</div>
    <div class="card ffcal-summary">
      <div class="ffcal-sumtop"><b>${_ffCalSay(_ffCalSel)}</b>
      ${sel.tier === "elite" ? `<span class="chip up">ELITE SLATE</span>` : ""}</div>
      <span class="ffcal-sumsub">${sel.games || 0} game${sel.games === 1 ? "" : "s"}
        · top five average ${(sel.top5 || 0).toFixed(1)} projected${outN
          ? ` · ${outN} ruled out and excluded` : ""}</span>
      ${posChips ? `<div class="ffcal-poschips">${posChips}</div>` : ""}
    </div>
    </div>
    <div class="ffcal-mid" id="ffcal-day">${ffCalDayHTML(d, _ffCalSel)}</div>
    <aside class="card ffcal-panel">${ffCalPanelHTML(d, _ffCalSel)}</aside>
    </div>`;
}

function ffCalDayHTML(d, date) {
  const { rows, out } = _ffDayBoard(d, date);
  if (!rows.length) return "";
  const pickName = rows.some((x) => x.r.player === _ffCalPick)
    ? _ffCalPick : rows[0].r.player;
  // The render's middle column: compact ranked cards. The analysis they
  // used to carry inline now loads into the right-hand panel on tap.
  const card = (x, i) => {
    const { r, e, inj, score } = x;
    const vs = e.home ? "vs" : "at";
    return `<article class="card ffcal-card${i === 0 ? " top" : ""}${
        r.player === pickName ? " sel" : ""}"
        data-calpick="${escapeAttr(r.player)}" role="button" tabindex="0">
      <div class="ffcal-cardhead">
        <span class="ffcal-rank">${i + 1}</span>
        ${playerAvatar(r.player, r.team, { size: 40, map: nflMap(), headshot: r.headshot })}
        <span class="ffcal-who"><b>${escapeHtml(r.player)}</b>${inj ? injTag("nfl", r.player) : ""}
          <span class="ffcal-sub">${escapeHtml(r.position)}${r.pos_rank} · ${nflName(r.team)}
            ${vs} ${nflName(e.opp)}${r.ppg != null ? ` · ${r.ppg} FPPG last season` : ""}</span></span>
        <span class="ffcal-proj">${score.toFixed(1)}<span class="ffcal-projk">proj pts</span></span>
      </div>
    </article>`;
  };
  return `
    <div class="section-title minor">${_ffCalSay(date)} — the five best plays
      <span class="sub">— tap a card to load the read on it.</span></div>
    ${rows.slice(0, 5).map(card).join("")}
    ${out.length ? `<p class="ffcal-outnote">Ruled out that day and excluded:
      ${out.slice(0, 6).map((x) => `${escapeHtml(x.r.player)}
        (${escapeHtml(injShort(x.inj.status))})`).join(", ")}.</p>` : ""}`;
}

/* The right-hand column of the render: one player's full read. Every
   line is the same arithmetic the cards used to print inline — the
   baseline, the environment multiplier with its denominator, the
   script, the usage share — plus the two-team matchup tiles built from
   the implied points the environment term already runs on. */
function ffCalPanelHTML(d, date) {
  const { rows } = _ffDayBoard(d, date);
  if (!rows.length) {
    return `<p class="ffd-note">Tap a game day on the calendar and this
      panel carries the read on its best play.</p>`;
  }
  const x = rows.find((v) => v.r.player === _ffCalPick) || rows[0];
  const { r, e, inj, mult, score } = x;
  const avg = _ffImpliedAvg(d);
  const u = ((d.usage || []).find((w) => w.player === r.player)) || null;
  const vs = e.home ? "vs" : "at";
  const spreadSay = e.spread == null ? ""
    : `, ${e.spread < 0 === e.home ? "favored" : "underdog"} by ${Math.abs(e.spread)}`;
  // "Why He's a Top Play" — every line a fact the payload defends,
  // never a vibe.
  const why = [];
  why.push(`Baseline <b>${r.proj} PPG</b> — Tier ${r.tier} on the board,
    +${r.vorp} over a replacement ${escapeHtml(r.position)}.`);
  why.push(e.implied != null
    ? `Environment <b>×${mult.toFixed(2)}</b>: ${e.implied} implied points
       ${vs} ${nflName(e.opp)}${spreadSay}, game total ${e.total},
       against a league-average ${avg ? avg.toFixed(1) : "—"}.`
    : `No line posted for this game yet, so the baseline stands alone.`);
  if (e.read) why.push(`<b>${escapeHtml(e.archetype || "")}.</b>
    ${escapeHtml(e.read)}`);
  if (u) why.push(`Usage: ${pct(u.season)} of his team’s
    ${escapeHtml(u.metric || "volume")} this season${u.l4 != null
      ? `, ${pct(u.l4)} over the last four weeks` : ""} —
    the volume behind the baseline is ${u.delta != null && u.delta > 0.02
      ? "growing" : u.delta != null && u.delta < -0.02 ? "shrinking" : "steady"}.`);
  if (inj) why.push(`<span style="color:${injTone(inj.status)}">Carries a
    designation: ${escapeHtml(inj.status)}${inj.injury
      ? ` — ${escapeHtml(inj.injury)}` : ""}.</span>`);
  const oppImplied = e.implied != null && e.total != null
    ? Math.round((e.total - e.implied) * 10) / 10 : null;
  const stat = (k, v) => v == null || v === "" ? ""
    : `<span class="ffd-stat"><span class="k">${k}</span><b>${v}</b></span>`;
  return `
    <div class="ffd-head">
      ${playerAvatar(r.player, r.team, { size: 48, map: nflMap(), headshot: r.headshot })}
      <div class="ffd-who"><b>${escapeHtml(r.player)}</b>
        <span class="ffd-sub">${escapeHtml(r.position)}${r.pos_rank} ·
          ${nflName(r.team)} ${vs} ${nflName(e.opp)} ·
          ${_ffCalSay(date)}${e.time ? ` ${escapeHtml(e.time)}` : ""}</span>
        ${injLineHTML(inj)}</div>
    </div>
    <div class="ffcal-p-proj">
      <b class="ffcal-p-n">${score.toFixed(1)}</b>
      <span class="k">projected points that day — baseline ${r.proj}
        × ${mult.toFixed(2)} environment</span>
    </div>
    <div class="ffd-sect"><div class="ffd-h">Why he’s the play</div>
      <ul class="ffcal-checks">${why.map((w) =>
        `<li>${icon("check", 12)} <span>${w}</span></li>`).join("")}</ul></div>
    ${e.implied != null ? `
    <div class="ffd-sect"><div class="ffd-h">Matchup — the market’s split
      of ${e.total} total points</div>
      <div class="ffcal-vs">
        <div class="ffcal-vs-t${e.implied >= (oppImplied ?? 0) ? " lead" : ""}">
          ${teamMark(r.team, 18, nflMap(), "nfl")}<b>${e.implied}</b>
          <span class="k">${nflName(r.team)} implied</span></div>
        <div class="ffcal-vs-t${(oppImplied ?? 0) > e.implied ? " lead" : ""}">
          ${teamMark(e.opp, 18, nflMap(), "nfl")}<b>${oppImplied ?? "—"}</b>
          <span class="k">${nflName(e.opp)} implied</span></div>
      </div></div>` : ""}
    <div class="ffd-sect"><div class="ffd-h">Board line</div>
      <div class="ffd-stats">
        ${stat("Proj PPG", r.proj)}${stat("Last season", r.ppg)}
        ${stat("xFP", r.xppg)}${stat("VORP", r.vorp != null ? "+" + r.vorp : null)}
        ${stat("Tier", r.tier)}
      </div></div>
    <button class="btn ffcal-open" type="button"
      data-dossier="${escapeAttr(r.player)}">Open the full profile</button>`;
}

/* One delegated binding, document-level like the dossier's: the panel
   re-renders on every day tap, so per-cell listeners would die with the
   innerHTML. */
document.addEventListener("click", (e) => {
  if (!_ffData) return;
  const nav = e.target && e.target.closest("[data-calnav]");
  const cell = !nav && e.target && e.target.closest("[data-calday]");
  const pick = !nav && !cell && e.target && e.target.closest("[data-calpick]");
  if (!nav && !cell && !pick) return;
  if (nav) {
    if (nav.dataset.calnav === "first") {
      _ffCalMonth = null;             // recomputed from the first slate
      _ffCalSel = null;
    } else {
      const [y, m] = (_ffCalMonth || "").split("-").map(Number);
      if (!y) return;
      const dt = new Date(Date.UTC(y, m - 1 + Number(nav.dataset.calnav), 1));
      _ffCalMonth = dt.toISOString().slice(0, 7);
    }
    _ffCalPick = null;                // a new day gets its own best play
  } else if (cell) {
    _ffCalSel = cell.dataset.calday;
    _ffCalPick = null;
  } else {
    _ffCalPick = pick.dataset.calpick;
  }
  // Whole-tab re-render: the grid marks, the summary strip and the day
  // panel all move together, and the join is cheap.
  const zone = document.querySelector('[data-subgroup="days"]');
  if (zone) zone.innerHTML = ffCalendarHTML(_ffData);
});

/* ---------------- Mock draft simulator ----------------
   Ethan, 2026-08-18: "Add a mock draft simulator." A snake draft against
   value-hungry CPU rooms, drafted FROM THE KIT'S OWN BOARD — the same
   150 players, projections and VORP the draft kit already publishes, so
   the sim and the kit can never disagree about who is good.

   The CPU model is deliberately simple and stated: each pick samples
   from the best available by VORP, weighted toward the top with noise
   (rooms reach, but rarely far), scaled by a positional-need multiplier
   (a room holding a QB does not draft a second one in round 3). No
   hidden ratings, no personality knobs pretending to be information.

   The end-of-draft read is arithmetic, not a letter grade: your best
   starting lineup's projected PPG, ranked against the CPU rooms' own.
   A grade would imply a model of drafting skill nobody fitted. */
let _mock = null;                 // an in-progress draft survives re-renders
let _mockKit = null;              // the fantasy payload's draft kit, captured at render

//: Starting lineup a roster is judged on (bench fills the rest).
const MOCK_SLOTS = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 2 };
const MOCK_FLEX = new Set(["RB", "WR", "TE"]);

function _mockPicker(pickIdx, teams) {
  const round = Math.floor(pickIdx / teams);
  const i = pickIdx % teams;
  return round % 2 === 0 ? i : teams - 1 - i;          // the snake
}

function _mockStart(teams, slot) {
  const kit = _mockKit || {};
  const pool = (kit.board || []).slice()
    .sort((a, b) => (b.vorp || 0) - (a.vorp || 0));
  _mock = { teams, you: slot - 1, pool, pick: 0,
            rounds: Math.min(14, Math.floor(pool.length / teams)),
            rosters: Array.from({ length: teams }, () => []), log: [] };
  _mockAdvance();
}

function _mockNeed(roster, pos, round) {
  const n = roster.filter((p) => p.position === pos).length;
  // Onesie positions: a second QB/TE before the bench rounds is a
  // wasted pick, and even a CPU should know it.
  if ((pos === "QB" || pos === "TE") && n >= 1 && round < 9) return 0.1;
  if (pos === "RB" || pos === "WR") return n >= 5 ? 0.3 : 1.0;
  return n >= 2 ? 0.2 : 1.0;
}

/* A CPU manager reads the injury report. A man ruled out or on IR is
   not worth a premium pick to a season-long roster; a Questionable in
   August is Tuesday noise. A multiplier, not a ban — the late-round
   stash of a hurt star is a real strategy, and the human can always
   draft anyone the tags warned about. */
function _mockHealth(name) {
  const r = injFind("nfl", name);
  if (!r) return 1;
  return injTone(r.status) === "var(--bad)" ? 0.25 : 0.85;
}

function _mockCpuPick(ti) {
  const round = Math.floor(_mock.pick / _mock.teams);
  const roster = _mock.rosters[ti];
  const cands = _mock.pool.slice(0, 8).map((p, i) => ({
    p, w: Math.exp(-i / 2.5) * _mockNeed(roster, p.position, round)
          * _mockHealth(p.player)
          * (0.6 + Math.random() * 0.8) }));
  const total = cands.reduce((s, c) => s + c.w, 0) || 1;
  let roll = Math.random() * total;
  let choice = cands[0].p;
  for (const c of cands) { roll -= c.w; if (roll <= 0) { choice = c.p; break; } }
  _mockTake(ti, choice);
}

function _mockTake(ti, player) {
  _mock.pool = _mock.pool.filter((p) => p !== player);
  _mock.rosters[ti].push(player);
  _mock.log.push({ pick: _mock.pick, team: ti, player });
  _mock.pick += 1;
}

function _mockAdvance() {
  const total = _mock.teams * _mock.rounds;
  while (_mock.pick < total
         && _mockPicker(_mock.pick, _mock.teams) !== _mock.you) {
    _mockCpuPick(_mockPicker(_mock.pick, _mock.teams));
  }
  _mockRender();
}

//: The best legal starting lineup, slot by slot — the judged eleven.
//: Kept as ONE function so the final screen's starters list and the
//: PPG it is scored on can never disagree.
function _mockLineup(roster) {
  const by = { QB: [], RB: [], WR: [], TE: [] };
  roster.forEach((p) => (by[p.position] || []).push(p));
  Object.values(by).forEach((l) => l.sort((a, b) => (b.proj || 0) - (a.proj || 0)));
  const starters = [];
  for (const [pos, want] of Object.entries(MOCK_SLOTS)) {
    if (pos === "FLEX") continue;
    for (let i = 0; i < want; i++) {
      starters.push([want > 1 ? pos + (i + 1) : pos, by[pos].shift() || null]);
    }
  }
  const flexPool = [...by.RB, ...by.WR, ...by.TE]
    .sort((a, b) => (b.proj || 0) - (a.proj || 0));
  for (let i = 0; i < MOCK_SLOTS.FLEX; i++) {
    starters.push(["FLEX" + (i + 1), flexPool.shift() || null]);
  }
  const chosen = new Set(starters.map(([, p]) => p).filter(Boolean));
  const bench = roster.filter((p) => !chosen.has(p));
  return { starters, bench,
           ppg: starters.reduce((s, [, p]) => s + (p ? p.proj || 0 : 0), 0) };
}

function _mockStartersPPG(roster) {
  return _mockLineup(roster).ppg;
}

function _mockAdvice() {
  const roster = _mock.rosters[_mock.you];
  const best = _mock.pool[0];
  const count = (pos) => roster.filter((p) => p.position === pos).length;
  const thin = ["RB", "WR", "TE", "QB"].find((pos) =>
    count(pos) < (MOCK_SLOTS[pos] || 1));
  const bestThin = thin && _mock.pool.find((p) => p.position === thin);
  let line = `Best value on the board: <b>${escapeHtml(best.player)}</b>
    (${escapeHtml(best.position)}, VORP +${(best.vorp || 0).toFixed(1)},
    Tier ${best.tier || "—"}).`;
  if (bestThin && bestThin !== best) {
    line += ` Your thinnest spot is ${thin} — best left there:
      <b>${escapeHtml(bestThin.player)}</b> (+${(bestThin.vorp || 0).toFixed(1)}).`;
  }
  return line;
}

function mockDraftHTML() {
  const kit = _mockKit || {};
  if (!(kit.board || []).length) {
    return `<div class="empty">The mock draft drafts from the kit\u2019s own
      board, and this build has none yet — it fills with the season\u2019s
      first projections.</div>`;
  }
  if (!_mock) {
    return `<div class="section-title">Mock draft
        <span class="sub">— snake order against value-hungry CPU rooms,
        drafted from the kit\u2019s own 150-player board</span></div>
      <div class="card" style="padding:16px 18px">
        <div class="mk-setup">
          <label>League size
            <select id="mk-teams" class="mk-sel">
              ${[8, 10, 12].map((n) => `<option ${n === 12 ? "selected" : ""}>${n}</option>`).join("")}
            </select></label>
          <label>Your pick
            <select id="mk-slot" class="mk-sel">
              ${Array.from({ length: 12 }, (_, i) => `<option>${i + 1}</option>`).join("")}
            </select></label>
          <button class="btn primary" id="mk-start">Start the draft</button>
        </div>
        <p style="color:var(--text-mute);font-size:var(--fs-sm);margin:0">
          CPU rooms pick the best value available with a little human noise —
          they reach, but rarely far, and nobody drafts two quarterbacks in
          the first eight rounds. Your finished roster is judged on its
          starters\u2019 projected PPG against the room, not on a letter grade
          nobody fitted.</p>
      </div>`;
  }
  const m = _mock;
  const total = m.teams * m.rounds;
  const round = Math.floor(m.pick / m.teams) + 1;
  const yourTurn = m.pick < total && _mockPicker(m.pick, m.teams) === m.you;
  const face = (p, size) => playerAvatar(p.player, p.team,
    { size, map: nflMap(), headshot: p.headshot });
  const idBlock = (p, meta) => `
    <span class="mk-id" data-dossier="${escapeAttr(p.player)}"><b>${escapeHtml(p.player)}</b>${injTag("nfl", p.player)}
      <span class="mk-meta">${teamMark(p.team, 14, nflMap(), "nfl")}
        ${escapeHtml(p.team)} · ${escapeHtml(p.position)}${meta}</span></span>`;

  if (m.pick >= total) {
    const scores = m.rosters.map((r, i) => ({ i, ppg: _mockStartersPPG(r) }))
      .sort((a, b) => b.ppg - a.ppg);
    const place = scores.findIndex((s) => s.i === m.you) + 1;
    const yours = scores.find((s) => s.i === m.you);
    const lineup = _mockLineup(m.rosters[m.you]);
    const starterRow = ([slot, p]) => `
      <div class="mk-log-row">
        <span class="chip mk-slotchip">${escapeHtml(slot)}</span>
        ${p ? face(p, 28) + idBlock(p, ` · proj ${p.proj}`)
            : `<span class="mk-meta">— nobody drafted for this slot</span>`}
      </div>`;
    return `<div class="section-title">Draft complete</div>
      <div class="stats">
        <div class="tile"><div class="k">Your starters</div>
          <div class="v">${yours.ppg.toFixed(1)}</div>
          <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">projected PPG</div></div>
        <div class="tile"><div class="k">Finish</div>
          <div class="v">${place} of ${m.teams}</div>
          <div style="color:var(--text-mute);font-size:var(--fs-sm);margin-top:2px">by projected starters</div></div>
      </div>
      <div class="section-title minor">Your starting lineup</div>
      <div class="card mk-panel">${lineup.starters.map(starterRow).join("")}</div>
      ${lineup.bench.length ? `<div class="section-title minor">Bench</div>
      <div class="card mk-panel">${lineup.bench.map((p) => `
        <div class="mk-log-row">${face(p, 28)}${idBlock(p, ` · proj ${p.proj}`)}</div>`).join("")}</div>` : ""}
      <button class="btn" id="mk-again" style="margin-top:12px">Draft again</button>`;
  }

  const avail = m.pool.slice(0, 12).map((p) => `
    <div class="mk-log-row">
      ${face(p, 32)}
      ${idBlock(p, ` · VORP +${(p.vorp || 0).toFixed(1)} · Tier ${p.tier || "—"}`)}
      <button class="btn mk-take" data-mkp="${escapeAttr(p.player)}"
        ${yourTurn ? "" : "disabled"}>Draft</button></div>`).join("");
  const recent = m.log.slice(-m.teams).reverse().map((e) => `
    <div class="mk-log-row${e.team === m.you ? " you" : ""}">
      <span class="mk-pickno">${Math.floor(e.pick / m.teams) + 1}.${String(e.pick % m.teams + 1).padStart(2, "0")}</span>
      <span class="mk-room">${e.team === m.you ? "You" : "Room " + (e.team + 1)}</span>
      ${idBlock(e.player, "")}
      <span class="chip">${escapeHtml(e.player.position)}</span></div>`).join("");
  const roster = m.rosters[m.you].map((p) => `
    <div class="mk-log-row">${face(p, 28)}${idBlock(p, ` · proj ${p.proj}`)}
      <span class="chip">${escapeHtml(p.position)}</span></div>`).join("");
  return `<div class="section-title">Round ${round} of ${m.rounds}
      <span class="sub">— pick ${m.pick + 1} of ${total}</span></div>
    ${yourTurn ? `<div class="card mk-advice">
      <div class="mk-advice-head">Your pick — round ${round}</div>
      <div>${_mockAdvice()}</div></div>` : ""}
    <div class="section-title minor">Best available</div>
    <div class="card mk-panel">${avail}</div>
    <div class="section-title minor">Last round of picks</div>
    <div class="card mk-panel">${recent || `<div class="mk-log-row">
      <span class="mk-meta">Nobody has picked yet.</span></div>`}</div>
    <div class="section-title minor">Your roster</div>
    <div class="card mk-panel">${roster || `<div class="mk-log-row">
      <span class="mk-meta">Empty until your first pick.</span></div>`}</div>
    <button class="btn" id="mk-reset" style="margin-top:12px">Abandon this draft</button>`;
}

function _mockRender() {
  const room = document.getElementById("mock-room");
  if (room) room.innerHTML = mockDraftHTML();
}

function _mockBind(host) {
  const room = host.querySelector("#mock-room");
  if (!room) return;
  // Delegated, because the room's innerHTML is replaced on every pick.
  room.addEventListener("change", (e) => {
    if (e.target.id !== "mk-teams") return;
    // The slot picker follows the league size — an 8-team league has no
    // pick eleven, and silently clamping a stale choice would start the
    // reader from a seat they never chose.
    const teams = parseInt(e.target.value, 10);
    const slot = document.getElementById("mk-slot");
    const keep = Math.min(teams, parseInt(slot.value, 10) || 1);
    slot.innerHTML = Array.from({ length: teams }, (_, i) =>
      `<option ${i + 1 === keep ? "selected" : ""}>${i + 1}</option>`).join("");
  });
  room.addEventListener("click", (e) => {
    const t = e.target;
    if (t.id === "mk-start") {
      const teams = parseInt(document.getElementById("mk-teams").value, 10);
      const slot = Math.min(teams,
        parseInt(document.getElementById("mk-slot").value, 10));
      _mockStart(teams, slot);
    } else if (t.id === "mk-reset" || t.id === "mk-again") {
      _mock = null; _mockRender();
    } else if (t.dataset && t.dataset.mkp) {
      const p = _mock.pool.find((x) => x.player === t.dataset.mkp);
      if (p) { _mockTake(_mock.you, p); _mockAdvance(); }
    }
  });
}

/* Live draft sync. One poll loop, keyed off the fantasy view being open —
   navigating away stops it, reconnecting resumes it. */
const dkState = { timer: null, kit: null, adp: {} };

function dkStop(msg) {
  if (dkState.timer) { clearInterval(dkState.timer); dkState.timer = null; }
  const st = document.getElementById("dk-status");
  if (st) { st.textContent = msg || "NOT CONNECTED"; st.style.color = "var(--text-mute)"; }
  const dis = document.getElementById("dk-disconnect");
  if (dis) dis.classList.add("ff-hidden");
  // Drop the pick order with the connection. A disconnected draft's
  // column would otherwise sit there labelled "Your draft" long after it
  // stopped being live, which is the same lie as a stale price.
  dkState.adp = {};
  if (typeof renderRankBoard === "function") renderRankBoard();
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
    acctTouch("fantasy");
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
    // THE PICK ORDER IS A RANKING, and it is the only one that is about
    // YOUR league rather than a national average of strangers. Recorded
    // here so the side-by-side board gains a "Your draft" column the
    // moment picks start.
    dkState.adp = {};
    (picks || []).forEach((p, i) => {
      const meta = p.metadata || {};
      const name = `${meta.first_name || ""} ${meta.last_name || ""}`.trim();
      const key = ffNorm(name);
      if (!key || dkState.adp[key]) return;
      dkState.adp[key] = { rank: p.pick_no > 0 ? p.pick_no : i + 1, player: name };
    });
    if (typeof renderRankBoard === "function") renderRankBoard();
    st.textContent = `LIVE · ${taken.size} PICKED`; st.style.color = "var(--good)";
    document.querySelectorAll("[data-ffp]").forEach((el) =>
      el.classList.toggle("dk-taken", taken.has(el.dataset.ffp)));
    dkBestAvailable(taken);
    dkAdvice(draftId);
  };
  tick();
  dkState.timer = setInterval(tick, 12000);
}

/* PICK-BY-PICK ADVICE. Ethan, 2026-08-15: "We need to show pick by pick
   advice."

   The arithmetic lives in engine/fantasy_pick.py and is served by
   /api/draftadvice — it reads the SAME cached pick feed this loop is
   already polling, so it costs no extra request, and it stays unit
   tested rather than becoming another hundred lines of untested
   JavaScript deciding what to do with a first-round pick.

   What it adds over "best available" is the only question that actually
   decides a pick: which of these men will NOT be here at my next turn. */
async function dkAdvice(draftId) {
  const host = document.getElementById("dk-advice");
  if (!host) return;
  const me = (window._slUser && window._slUser.user_id) || "";
  let a;
  try {
    const r = await fetch(`/api/draftadvice?draft=${encodeURIComponent(draftId)}`
      + `&user=${encodeURIComponent(me)}`);
    a = await r.json();
    if (!r.ok) throw new Error(a && a.error);
  } catch (e) { host.innerHTML = ""; return; }
  if (!a || a.slot == null) {
    // No seat in this draft means we are watching, not drafting. Saying
    // so beats inventing advice for a team that is not yours.
    host.innerHTML = `<div class="dk-advice-note">Connected as a spectator —
      no seat in this draft, so there is no "your next pick" to advise on.
      ${me ? "" : "Connect your Sleeper username above to claim your seat."}</div>`;
    return;
  }
  const pct = (x) => `${Math.round(x * 100)}%`;
  const tone = { gone: "down", "toss-up": "warn", safe: "up" };
  const take = a.take;
  host.innerHTML = `
    <div class="dk-advice">
      <div class="dk-advice-head">
        Seat ${a.slot} of ${a.teams} · ${a.on_the_clock ? "ON THE CLOCK"
          : `next pick ${a.next_pick} — ${a.picks_until} pick(s) away`}
        <span class="dk-window">room reach ${a.window} deep${
          a.window_fitted ? "" : " (prior — too few picks to fit yet)"}</span>
      </div>
      ${take ? `<div class="dk-take">
        <b>${escapeHtml(take.player)}</b>${injTag("nfl", take.player)}
        <span class="chip">${escapeHtml(take.position)}</span>
        <span class="chip ${tone[take.verdict] || ""}">${
          take.verdict === "gone" ? "won’t last" :
          take.verdict === "safe" ? "will last" : "toss-up"} · ${
          pct(take.survives)} to be here at ${a.next_pick || "your next pick"}</span>
        ${take.fills_need ? `<span class="chip up">fills a starting slot</span>` : ""}
      </div>` : ""}
      ${a.can_wait && a.can_wait.length ? `<div class="dk-wait">
        <span class="dk-bl">Can wait</span>
        ${a.can_wait.slice(0, 4).map((r) => `<span class="chip">${
          escapeHtml(r.player)} · ${pct(r.survives)}</span>`).join("")}</div>` : ""}
      <div class="dk-advice-note">${escapeHtml(a.note || "")}</div>
    </div>`;
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
      ${top.map((r) => `<span class="chip up">${escapeHtml(r.player)} · +${r.vorp}${injTag("nfl", r.player)}</span>`).join("")}</div>
    <div class="dk-bestrow"><span class="dk-bl">By position</span>
      ${["QB", "RB", "WR", "TE"].map((p) => byPos[p]
        ? `<span class="chip">${p}: ${escapeHtml(byPos[p].player)} (+${byPos[p].vorp})${injTag("nfl", byPos[p].player)}</span>` : "")
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
    : `<div style="font-weight:800;font-size:var(--fs-xl)">${iconMark("target", 16)}What we recommend right now: <span style="color:var(--warn)">nothing — watch, don’t bet</span></div>
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
      <div class="subtitle">Free and read-only: see YOUR roster’s usage trends, trade flags,
        and who’s unrostered in YOUR league. No password — just your Sleeper username.</div></div></div>
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
      acctTouch("fantasy");
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
    // Stashed for the draft room: the advice endpoint needs the user id
    // to find your SEAT, and without it the panel correctly says it is
    // watching rather than inventing advice for somebody else's team.
    window._slUser = user;
    renderSleeperPanel(d, { username, user, leagues, leagueId, rosters,
                            lgUsers, seasonTried });
    // The lineup and the trades both need the league's OWN scoring and
    // slots, which only exist once a league is chosen.
    renderLeagueDesk(leagueId, user.user_id);
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
      <span style="flex:0 0 auto">${playerAvatar(r.name, r.team, { map: nflMap(), headshot: (r.u || {}).headshot || _ffDossierInfo(r.name).headshot })}</span>
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        <strong>${escapeHtml(r.name)}</strong>${injTag("nfl", r.name)}
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
    ${(() => {
      // The one line a manager checks first. Names, not a count — a
      // count sends him hunting through his own list.
      const hurt = myRows.map((r) => ({ r, inj: injFind("nfl", r.name) }))
        .filter((x) => x.inj);
      return hurt.length ? `<p class="rank-help" style="margin-top:0">
        ${icon("warn")} Carrying a designation:
        ${hurt.map((x) => `<b>${escapeHtml(x.r.name)}</b>
          <span style="color:${injTone(x.inj.status)}">${escapeHtml(injShort(x.inj.status))}</span>`).join(", ")}
        — details on the Injuries page.</p>` : "";
    })()}
    <div style="margin:0 -18px">${myRows.map(rowHTML).join("") ||
      `<p class="loading" style="padding:12px 16px">Couldn’t match a roster you own in this league.</p>`}</div>
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
    acctTouch("fantasy");
    renderSleeperZone(d);
  });
  const dis = document.getElementById("sleeper-disconnect");
  if (dis) dis.addEventListener("click", () => {
    localStorage.removeItem("ff_user");
    localStorage.removeItem("ff_league");
    acctTouch("fantasy");
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
        title="method distribution — left: pick’s KO/SUB/DEC, right: opponent’s DEC/SUB/KO">
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
      ${/* The Overhead — see docs/THE_OVERHEAD.md. UFC has a building
            after all: the promotion's own facility uses a 25-foot cage
            and arenas use 30, which the model already prices. Drawn to
            scale, so an Apex card is visibly tighter than an arena card.
            The prose stays underneath it — the drawing is the glance,
            the sentence is the reason. */""}
      ${(p.environment && ((p.environment.cage || {}).known || (p.environment.altitude || {}).known))
        ? `<div class="ufc-overhead">${octagon({
             venue: p.environment.venue || "",
             rounds: p.rounds, title_fight: p.title_fight,
             environment: p.environment })}</div>` : ""}
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
  // Card banner from Ethan's octagon renders (2026-08-11). UFC has no
  // home team to key a colour on, so the pick is a stable hash of the
  // card's identity — the same event always shows the same arena, and
  // different cards rotate through all six.
  const octN = ([...((d.event_date || "") + ((d.card_venue || {}).venue || ""))]
    .reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) >>> 0, 7) % 6) + 1;
  host.innerHTML = `
    <img class="ufc-banner" alt="" loading="lazy"
      src="${venueSrc(`img/venues/variants/octagon-${octN}.jpg`)}" onerror="this.remove()"/>
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
          <span class="sub">— every priced bout: the model’s number vs the market’s, and
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
        Friday weigh-ins: missed weight and visible cut damage aren’t fully priced for hours, and
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
      EV ${signedPct(edge)}. Kelly’s answer for a negative edge is a stake of zero, and it’s the only honest one.</p>`;
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
    out.innerHTML = `<p class="loading" style="padding:8px 0">Enter odds for at least two legs (win % optional — blank assumes the book’s implied).</p>`;
    return;
  }
  const dec = legs.reduce((a, l) => a * amToDec(l.odds), 1);
  const prob = legs.reduce((a, l) => a * l.p, 1);
  const evParlay = prob * dec - 1;
  const evSingles = legs.reduce((a, l) => a + (l.p * amToDec(l.odds) - 1), 0) / legs.length;
  const assumed = legs.some((l) => l.assumed);
  const verdict = evParlay > evSingles + 1e-9
    ? "the parlay compounds it — only because every leg you entered is +EV"
    : "the singles are the better bet — the parlay multiplies the book’s margin into every leg";
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
      <p><strong>Qellys Book is one book for everything a sharp bettor keeps
      open in ten tabs.</strong> Six leagues priced nightly by named models.
      A full fantasy football suite with its own draft room. Prediction-market
      intelligence. A live meme-coin radar. And underneath all of it, the one
      thing almost nobody else will show you: <strong>every pick this site has
      ever made, graded in public at the price it was published — losses
      included.</strong></p>

      <p>It is an analytics tool, not a sportsbook and not a tipster. You
      cannot place a bet here and no money changes hands on this site. The
      model estimates its own probability for each outcome and compares it to
      the live prices at ten books. When our number and the book’s number
      disagree by enough to survive our own margin for error, the board shows
      it — with the reasons on the card. When they don’t, the board says
      <em>"no qualifying plays"</em> and shows you nothing. That happens
      often, and it is the system working rather than failing.</p>
    </div>

    <div class="section-title">Six leagues, each with its own model
      <span class="sub">— not one formula wearing six logos</span></div>
    <div class="cards wide">
      ${card("NFL — The NFL Book", `<p>The pro-bettor spec: player props with
        usage bridges and coaching-reset detection, game lines off
        opponent-adjusted team ratings, anytime-TD long shots, and a Week 1
        board that prices from day one instead of going dark until October.</p>`)}
      ${card("MLB — Scalpy 2.0", `<p>Hitter and pitcher props from
        plate-appearance-level data: park factors, umpires, platoon splits,
        bullpen fatigue, Statcast contact quality. Home-run long shots, live
        win-probability charts, and a per-game simulator that deals every
        plate appearance.</p>`)}
      ${card("NBA + WNBA — Scalpy hoops", `<p>Points, rebounds, assists and
        threes through a minutes engine with on/off inheritance — who absorbs
        the shots when the star sits — plus the same public grading as every
        other league.</p>`)}
      ${card("College football", `<p>A market-attention model: it knows which
        games the sharps price hard and which Tuesday slates nobody is
        watching, and it refuses to grade a play whose quarterback nobody has
        confirmed.</p>`)}
      ${card("UFC — Scalpy MMA", `<p>Fighter dossiers with measured records,
        method and round markets, and a card that passes on most fights with
        the reason stated — because most fights deserve a pass.</p>`)}
      ${card("Futures, every league", `<p>Season-long boards priced the same
        honest way, with the hold named so you can see what the book is
        charging you to park money for six months.</p>`)}
    </div>

    <div class="section-title">The betting toolkit
      <span class="sub">— what you open every night</span></div>
    <div class="cards wide">
      ${card("A board with reasons, not emojis", `<p>Every recommended pick
        carries its grade, its stake, and the named factors behind it — with
        each reason labelled by evidence tier: measured tonight, stable
        history, or the model’s own inference. Negative factors get a red
        mark on the card, not a hidden footnote.</p>`)}
      ${card("Player props with the picture", `<p>Every prop card charts the
        player’s actual last ten games against tonight’s line — and the
        search reaches <strong>every player in the league</strong>, not just
        tonight’s board, with faces, multi-market profiles and full game
        logs.</p>`)}
      ${card("Line shopping across ten books", `<p>The same bet is not the
        same price everywhere. The board names the book quoting the best
        number on every pick, and the scanner hunts stale lines, arbitrage
        pairs, middles and low-hold markets across the whole slate.</p>`)}
      ${card("A parlay screen, not a parlay builder", `<p>Legs must earn the
        board as singles first. Then the correlation engine — measured on
        tens of thousands of real games, refined by a per-lineup simulator —
        prices the joint honestly and publishes <strong>the price the book
        must beat</strong> for the ticket to be worth anything.</p>`)}
      ${card("Live, while it plays", `<p>Every game in progress across the
        leagues on one board: score, situation, the posted lines, and a live
        win-probability chart drawn from de-vigged in-play prices. Your open
        bets track themselves as the games run.</p>`)}
      ${card("Long shots, priced honestly", `<p>Home runs and anytime
        touchdowns with real probabilities attached — tracked in their own
        record bucket so a +900 flier never inflates the headline
        win rate.</p>`)}
    </div>

    <div class="section-title">The fantasy football suite
      <span class="sub">— the same engine, pointed at your league</span></div>
    <div class="cards wide">
      ${card("A draft room", `<p>Rankings from every source we can read
        without a password, side by side, with the disagreements flagged — a
        draft kit with tiers, sleepers and a value board — and a
        <strong>mock draft simulator</strong>: snake order against
        value-hungry CPU rooms, judged on projected points, not vibes.</p>`)}
      ${card("Your actual league, synced", `<p>Connect Sleeper, Yahoo or ESPN
        and the desk reads your real roster: a lineup optimiser, a trade
        generator, waiver-wire trends and camp-battle watch — no passwords
        ever taken for sites that need one.</p>`)}
      ${card("The numbers under the names", `<p>Usage movers (whose role is
        growing before the points arrive), buy-low and sell-high flags from
        expected points, and game scripts built from what the betting market
        expects each game to look like.</p>`)}
    </div>

    <div class="section-title">Beyond the sportsbook
      <span class="sub">— two more markets, same discipline</span></div>
    <div class="cards wide">
      ${card("Prediction-market intel", `<p>Polymarket, watched like a tape:
        whale activity, flagged accounts, leaderboards, and market moves
        worth knowing about — the crowd’s real money, read continuously.</p>`)}
      ${card("Rocket Radar — the meme-coin screen", `<p>A live terminal for
        the fastest market there is: momentum measured on our own tape,
        holder concentration from the chain itself, rug-check safety flags
        and embedded live charts. The same honesty rules apply — measured
        numbers or a dash, never a guess.</p>`)}
      ${card("Your own book", `<p>My Bets logs the wagers you actually place
        at your sportsbook — typed in or bulk-imported — grades them, and
        keeps your bankroll curve. Make a free account and it follows you
        from phone to laptop. The whole site installs to your home screen
        like an app.</p>`)}
    </div>

    <div class="section-title">Why here, and not five other subscriptions
      <span class="sub">— the comparison, plainly</span></div>
    <div class="cards wide">
      ${card("One book instead of a stack of tools", `<p>A picks service, a
        props-charting tool, a line-shopping app, a fantasy optimiser and a
        crypto screener — the market sells those separately. Here they are
        one product sharing one data spine, so the injury report that moves
        a prop also moves the fantasy board and the live chart.</p>`)}
      ${card("The record is the product", `<p>Picks services show you a hot
        streak; ours shows you the journal — every pick at its published
        price, wins, losses, closing-line value, and a calibration curve that
        says whether our "60%" actually meant 60%. The
        <strong>Why&nbsp;us</strong> page opens the math itself, with
        calculators to check our work by hand.</p>`)}
      ${card("Built to say no", `<p>A tout must sell picks every night. This
        site caps its slates, passes with reasons, and prints "no qualifying
        plays" when the numbers do not clear — which is exactly the night a
        subscription tout invents a lock.</p>`)}
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
        beat it on information it hasn’t bothered to price carefully, and on
        being at the right window.</p>`)}

      ${card("What the model is actually doing", `
        <p>For each market it builds a full <strong>distribution</strong>, not a
        pick. Not "this player goes over" but "here is the range of outcomes
        and how likely each one is." It removes the book’s built-in margin
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
        works out better than taking prices that aren’t. Even if every number
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
    <p style="font-size:1.06em;max-width:none;line-height:1.6;margin:0 0 4px"><strong>See the math. Know if it’s working. Stay in the game.</strong>
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

    <div class="section-title">What we deliberately don’t do</div>
    <div class="card" style="padding:14px 18px">
      <ul style="margin:0;padding-left:18px;line-height:1.9;color:var(--text-body)">
        <li>No guarantees, locks, or "can’t-miss" anything — that language is how touts talk, and it’s always false.</li>
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
      <p style="color:var(--text-mute);font-size:.85em;margin:0 0 10px">A −110/−110 line isn’t 50/50 — it’s 52.4% + 52.4% = 104.8%.
        The extra 4.8% is the book’s hold. Enter both sides of any market:</p>
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
        left blank, each leg is assumed to hit exactly as often as the book’s price implies.</p>
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
      <p style="color:var(--text-body);font-size:.92em;margin:0">Even a real edge loses often — that’s variance, not failure,
        and it’s why stakes here are fractions of bankroll, never "bet big to catch up." 21+ only. Never bet money you
        can’t afford to lose. If it stops feeling like a decision, call or text <strong>1-800-GAMBLER</strong> or the National
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

/* Left-to-right nav order, used ONLY to pick which way a view slides in.
   Every routable view belongs here: `switchView` looks up both names with
   indexOf, and a missing one comes back -1, which is not "unknown" — it is
   "further left than everything", so the view always animates as though
   you had gone backwards to reach it.

   `mybets` and `game` were both missing. Measured: opening My Bets from
   Recommended slid in from-LEFT while its own neighbours Record and The
   Lab slid from-right, so the one page about the user's own money was the
   one that felt like a step back. Nothing else was affected — the view
   still switched correctly, which is why it survived: the bug is only
   visible as a 200ms animation going the wrong way. */
const VIEW_ORDER = ["recommended", "prop", "game", "tonight", "live", "edge", "scanner", "longshots", "futures", "trending", "players", "rosters", "injuries", "weather", "alerts", "standings", "bankroll", "mybets", "account", "record", "lab", "intel", "fantasy", "memes", "ufc", "why", "about"];

function switchView(name, push = false) {
  const dir = VIEW_ORDER.indexOf(name) - VIEW_ORDER.indexOf(state.view);
  if (typeof syncRail === "function") setTimeout(syncRail, 0);
  if (name === "live" && typeof renderLiveBoard === "function")
    setTimeout(renderLiveBoard, 0);
  state.view = name;
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active", "from-left", "from-right"));
  const target = document.getElementById(`view-${name}`);
  // Entering view slides in from the direction of travel between tabs.
  if (dir > 0) target.classList.add("from-right");
  else if (dir < 0) target.classList.add("from-left");
  target.classList.add("active");
  // The game view has no tab of its own — it belongs to the board it came
  // from, so Recommended stays lit while you're inside a game.
  // Neither the game page nor the prop page has a tab. Both belong to the
  // board they were opened from, so Recommended stays lit inside them.
  const lit = (name === "game" || name === "prop") ? "recommended" : name;
  document.querySelectorAll(".nav-btn").forEach((b) => setSelected(b, b.dataset.view === lit));
  syncNavHint(lit);
  if (name === "prop") {
    renderPropPage();
    if (state.propId)
      history.replaceState(null, "", `#prop/${encodeURIComponent(state.propId)}`);
  }
  if (name === "game") {
    renderGamePage();
    if (state.gameId) history.replaceState(null, "", `#game/${encodeURIComponent(state.gameId)}`);
    moveIndicator();
    window.scrollTo({ top: 0, behavior: state.quiet ? "auto" : "smooth" });
    return;
  }
  if (name === "tonight") renderTonight();
  if (name === "rosters") renderRosters();
  if (name === "injuries") renderInjuries();
  if (name === "standings") renderStandings();
  if (name === "record") renderRecord();
  if (name === "lab") renderLab();
  if (name === "intel") renderIntel();
  if (name === "fantasy") renderFantasy();
  if (name === "memes") renderMemes();
  if (name === "mybets") renderMyBets();
  // Awaited, unlike its neighbours: this screen's entire content depends
  // on the server's answer to "who is this", and drawing before it lands
  // shows the sign-in form to somebody who is already signed in.
  if (name === "account") acctWho().then(renderAccount);
  if (name === "bankroll") renderBankrollExtras();
  if (name === "weather") renderWeather();
  if (name === "alerts") renderAlerts();
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
  // The Parlay Zone page became Parlay Mode (2026-08-11), and the
  // hashchange handler migrates old #parlays bookmarks — but a COLD
  // load never fires hashchange, so the same branch has to live here
  // too. Found by the preservation walk: deep-linking #parlays landed
  // on Home with the mode still off. The key is a literal, not PZ_KEY:
  // this runs during boot, before the new-look module's const at the
  // end of the file has initialized — referencing it here is a TDZ
  // ReferenceError that a try/catch would swallow into a silent no-op
  // (which is exactly how the first version of this fix failed).
  if (h === "parlays") {
    try { localStorage.setItem("qb_pz", "1"); } catch (e) {}
    switchView("recommended");
    if (typeof syncParlayMode === "function") syncParlayMode();
    return;
  }
  // A tab this sport does not have must not be reachable by URL. CFB has
  // no roster feed, and #rosters would otherwise open a page whose own tab
  // is hidden — the nav and the content disagreeing about what exists.
  if ((HIDDEN_VIEWS[state.sport] || []).includes(h)) {
    switchView("recommended");
    return;
  }
  if (h.startsWith("game/")) { openGame(decodeURIComponent(h.slice(5))); return; }
  if (h.startsWith("prop/")) { openProp(decodeURIComponent(h.slice(5))); return; }
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
  // scaleX against a 1px base, so the measured width passes through
  // unchanged while the animation stays on the compositor. See the
  // .nav-indicator rule for why left/width were the wrong properties.
  ind.style.transform =
    `translateX(${active.offsetLeft}px) scaleX(${active.offsetWidth})`;
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
    // The drawer is position:fixed, so the page does NOT need anchoring
    // to the top before it opens. The scrollTo(0) that used to sit here
    // was a leftover from the in-flow dropdown era, and by the 08-17
    // recording it had become a bug of its own: open the menu from
    // mid-page, close it, and you are at the TOP of a page you never
    // scrolled — "stuck" in the wrong place. Open must not move the page.
    const open = document.body.classList.toggle("menu-open");
    // A retracted auto-hide header must come back before the drawer
    // opens — the drawer hangs below the bar.
    if (open) {
      showHeader();
      // Always open at the map's start (Leagues, Dashboard) — the
      // drawer keeps its scroll while hidden, and reopening mid-list
      // read as broken ("where did the leagues go?").
      const sb = document.getElementById("sidebar");
      if (sb) sb.scrollTop = 0;
    }
    btn.setAttribute("aria-expanded", String(open));
  });
  // The scrim is body::after — paint with no element to listen on, so
  // the exit lives at the document: while the drawer is open, a tap
  // anywhere outside it (and outside the bars, which manage themselves)
  // closes it. This was the exit the 08-17 recording reached for —
  // tapping the dimmed page did nothing, and the Menu corner was the
  // only way out.
  // Capture phase, and the event is swallowed: the scrim does not
  // reliably intercept hit-testing (it is a pseudo-element), so without
  // this the same tap that closes the drawer ALSO activates whatever
  // sits under the dimmed page — measured: a scrim tap on #futures
  // yanked the page from 600 to 0 through an element it hit underneath.
  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("menu-open")) return;
    if (e.target.closest && e.target.closest("#sidebar, .tabbar, .topbar")) return;
    e.preventDefault();
    e.stopPropagation();
    closeMobileMenu();
    syncMenuLabel();
  }, true);
  // iOS ignores body{overflow:hidden} for touch scrolling, so the board
  // kept sliding under the open drawer — the "super buggy" wobble in
  // the same recording. Swallow moves that start outside the drawer;
  // the drawer scrolls itself (overscroll-behavior: contain).
  document.addEventListener("touchmove", (e) => {
    if (!document.body.classList.contains("menu-open")) return;
    if (e.target.closest && e.target.closest("#sidebar")) return;
    e.preventDefault();
  }, { passive: false });
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
  syncNavHint();
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
    b.addEventListener("click", () => {
      // Anchor/sub-tab items wear .nav-btn for the sidebar's looks but
      // carry no view of their own — their handlers live in initNewLook.
      // Without this guard they fell through to switchView(undefined),
      // which is the sport-btn More-toggle bug all over again.
      if (!b.dataset.view) return;
      // The sidebar keeps page items on screen during standalone pages
      // (memes, My Bets, ...); the old header hid them there. Leaving
      // standalone properly restores the sport chrome first.
      if (STANDALONE_MODES.includes(state.view)) exitStandaloneMode();
      switchView(b.dataset.view, true);
    }));

  /* The URL and the page must never disagree. Nothing listened for a hash
     change, so back, forward, a pasted #standings link and an in-page
     anchor all moved the address bar while leaving the previous view on
     screen — and then the URL you copied pointed at something you were not
     looking at. */
  window.addEventListener("hashchange", () => {
    const h = (location.hash || "").replace("#", "");
    if (h.startsWith("game/")) { openGame(decodeURIComponent(h.slice(5))); return; }
  if (h.startsWith("prop/")) { openProp(decodeURIComponent(h.slice(5))); return; }
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
    // The Parlay Zone page became Parlay Mode (2026-08-11) — an old
    // #parlays bookmark turns the mode on and lands on the tickets.
    if (h === "parlays") {
      try { localStorage.setItem(PZ_KEY, "1"); } catch (e) {}
      exitStandaloneMode();
      switchView("recommended");
      if (typeof syncParlayMode === "function") syncParlayMode();
      return;
    }
    // An IN-PAGE ANCHOR, not a view: `#preseason-board` and anything like
    // it. The target may sit inside a sub-tab panel that is display:none,
    // where the browser's own jump lands nowhere — so open the room, then
    // scroll. Without this the address bar moved and the page did not,
    // which is the same lie this handler was written to stop.
    if (!VIEW_ORDER.includes(h) && document.getElementById(h)) {
      const el = revealAnchor(h);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
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
    state.showAll = e.target.checked;
    renderGameBets(); renderRecommended(); groupRecommended();
  });
  let _searchT;
  document.getElementById("player-search").addEventListener("input", (e) => {
    state.search = e.target.value; renderPlayers();
    // Recorded on a PAUSE, not per keystroke — otherwise "mahomes" logs
    // seven rows, six of which are prefixes nobody searched for.
    clearTimeout(_searchT);
    const q = e.target.value;
    _searchT = setTimeout(() => acctSearchLog(q), 900);
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
      acctTouch("bankroll");
    } catch (e) {}
    updateUnitNote();
    renderStats();
    renderBestBets();
    renderGameBets();
    renderRecommended();
    // Showing non-recommended props, or entering a bankroll, can empty a
    // room or fill one — the rooms have to be re-judged with the content.
    groupRecommended();
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
initMasthead();
load();

/* --- the true minus, applied where numbers stack --------------------------
   Every signed figure the site prints comes out of a template literal, and
   there are 229 toFixed calls across 88 innerHTML sinks. Converting each by
   hand would be a large diff that rots the first time somebody adds a
   column, so the substitution happens once, here, at the render boundary.

   Scoped deliberately. The manual's rule is that tabular figures matter
   where numbers STACK — in a column the eye reads down, a stubby hyphen
   breaks the left edge of the number. In running prose the same figures
   look mechanical, and a hyphen there is correct. So this walks only the
   elements the code already marks as numeric, and never touches body copy.

   Convergent by construction: U+2212 does not match RE_SIGN, so a pass over
   already-converted text is a no-op and the observer cannot chase its own
   writes. */
const NUM_SEL = "td.num, .tile .v, .metric-value, .fx-edge, .agate .num";

function applyTrueMinus(root) {
  if (!root || !root.querySelectorAll) return 0;
  let n = 0;
  const cells = [];
  if (root.matches && root.matches(NUM_SEL)) cells.push(root);
  root.querySelectorAll(NUM_SEL).forEach((el) => cells.push(el));
  for (const el of cells) {
    // Text nodes only: an attribute or a nested element's markup is none of
    // this function's business.
    for (const node of el.childNodes) {
      if (node.nodeType !== 3) continue;
      const was = node.nodeValue;
      if (was.indexOf("-") < 0) continue;      // cheap reject, the common case
      const now = trueMinus(was);
      if (now !== was) { node.nodeValue = now; n += 1; }
    }
  }
  return n;
}

/* One observer rather than a call in each of the thirty-odd render
   functions: a hand-maintained list is a list somebody forgets to add to,
   and the failure mode is one column silently keeping its hyphens. */
function watchNumbers() {
  const main = document.querySelector("main") || document.body;
  if (!main || typeof MutationObserver === "undefined") return null;
  applyTrueMinus(main);
  const obs = new MutationObserver((records) => {
    for (const r of records) {
      for (const node of r.addedNodes) {
        if (node.nodeType === 1) applyTrueMinus(node);
      }
    }
  });
  obs.observe(main, { childList: true, subtree: true });
  return obs;
}
watchNumbers();

/* ==================================================================
   NEW LOOK (2026-08-11) — the shell around every page.
   Ethan approved the render: sidebar of destinations, slim top bar,
   dashboard home, right rail. Copied faithfully MINUS the balance chip
   and the bet slip (his call, and the site's: no money is held here).
   The compact-nav experiment that lived in this spot is superseded —
   the sidebar IS the menu now, on every width.
   ================================================================== */

/* Greeting — the render's "Good evening, <name>", powered by the real
   account (accounts feature, 2026-08-10). No account → a plain welcome,
   never a fake name. */
function renderGreeting() {
  const hi = document.getElementById("sb-hi");
  const nm = document.getElementById("sb-name");
  if (!hi || !nm) return;
  const h = new Date().getHours();
  const day = h < 5 ? "Up late" : h < 12 ? "Good morning"
            : h < 17 ? "Good afternoon" : "Good evening";
  const a = (typeof acctState === "function") ? acctState() : null;
  hi.textContent = a ? day + "," : "Welcome";
  nm.textContent = a ? a.name : "to the Book";
}

/* High Confidence Mode — a real filter with the journal's own bands:
   ON shows A-grade picks only (quality >= 80) on the board and the Top
   Picks strip. Persisted like the theme. */
const HCM_KEY = "qb_hcm";

function hcmOn() {
  try { return localStorage.getItem(HCM_KEY) === "1"; } catch (e) { return false; }
}

function hcmPaint() {
  const btn = document.getElementById("hcm-toggle");
  if (!btn) return;
  const on = hcmOn();
  btn.setAttribute("aria-checked", on ? "true" : "false");
  btn.classList.toggle("on", on);
  const state = btn.querySelector(".sb-hcm-state");
  if (state) state.textContent = on ? "On" : "Off";
}

function initHcm() {
  const btn = document.getElementById("hcm-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    try { localStorage.setItem(HCM_KEY, hcmOn() ? "0" : "1"); } catch (e) {}
    hcmPaint();
    if (typeof renderCards === "function") renderCards();
    renderTopPicks();
  });
  hcmPaint();
}

/* Parlay Mode — the render's second sidebar toggle, replacing the
   Parlay Zone PAGE (Ethan, 2026-08-11: "ditch the parlay zone screen
   but keep the same rules"). The rules did not move: the engine's
   screen, the correlation pricing, the one-per-slate cap and the
   Record-page journaling are exactly what they were — this is only
   WHERE the tickets render (on Home, while the switch is on). */
const PZ_KEY = "qb_pz";

function pzOn() {
  try { return localStorage.getItem(PZ_KEY) === "1"; } catch (e) { return false; }
}

function syncParlayMode() {
  const wrap = document.getElementById("parlay-mode");
  if (!wrap) return;
  // Sports whose slates never carry a parlay screen (UFC's §9 refusal,
  // the standalone markets) keep the section dark even with the switch
  // on — an empty room with an explanation belongs to sports that COULD
  // have tickets tonight.
  const barred = (HIDDEN_VIEWS[state.sport] || []).includes("parlays");
  wrap.hidden = barred || !pzOn();
}

function initPz() {
  const btn = document.getElementById("pz-toggle");
  if (!btn) return;
  const paint = () => {
    const on = pzOn();
    btn.setAttribute("aria-checked", on ? "true" : "false");
    btn.classList.toggle("on", on);
    const s = btn.querySelector(".sb-hcm-state");
    if (s) s.textContent = on ? "On" : "Off";
  };
  btn.addEventListener("click", () => {
    try { localStorage.setItem(PZ_KEY, pzOn() ? "0" : "1"); } catch (e) {}
    paint();
    syncParlayMode();
    // Turning it on means "show me the tickets" — go where they are.
    if (pzOn()) {
      if (STANDALONE_MODES.includes(state.view)) exitStandaloneMode();
      if (state.view !== "recommended") switchView("recommended", true);
      const wrap = document.getElementById("parlay-mode");
      if (wrap && !wrap.hidden)
        setTimeout(() => wrap.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    }
  });
  paint();
  syncParlayMode();
}

/* The Top Picks strip — the render's "QELLY'S TOP PICKS" row. The same
   recommended list the board draws, compacted: best grades first, real
   prices, and the grade badge the journal will grade it under. */
function renderTopPicks() {
  const host = document.getElementById("top-picks");
  if (!host) return;
  const d = state.data || {};
  let recs = (d.recommendations || []).filter((r) => r.recommended);
  if (hcmOn()) recs = recs.filter((r) => (r.quality || 0) >= 80);
  recs = recs.slice().sort((a, b) => (b.quality || 0) - (a.quality || 0)).slice(0, 8);
  const gb = (d.game_bets || []).filter((g) => g.recommended)
    .sort((a, b) => (b.quality || 0) - (a.quality || 0)).slice(0, Math.max(0, 4 - recs.length));
  if (!recs.length && !gb.length) { host.innerHTML = ""; return; }
  const odds = (o) => o == null ? "" : (o > 0 ? "+" + o : String(o));
  // The picks the buttons refer to, cached for tpTrack (the render's
  // green action, honestly framed: it PREFILLS My Bets — the one thing
  // it never invents is your stake).
  window._tpPicks = [];
  const track = (pick, desc) => {
    window._tpPicks.push({ desc, odds: pick.odds, book: pick.book || "",
                           sport: (state.sport || "").toUpperCase() });
    return window._tpPicks.length - 1;
  };
  const propCard = (r) => {
    const desc = `${r.player} ${r.side || ""} ${r.line != null ? r.line : ""} ${r.market_label || r.market || ""}`
      .replace(/\s+/g, " ").trim();
    const i = track(r, desc);
    return `
    <div class="tp-card ${propOpenable(r) ? "openable" : ""}"${propAttrs(r)}>
      <div class="tp-top"><span class="tp-tile">${playerAvatar(r.player, r.team, { size: 40, headshot: r.headshot })}</span>
        <div class="tp-who"><b>${escapeHtml(r.player)}</b>
          <span>${escapeHtml(r.side || "")} ${r.line != null ? r.line : ""} ${escapeHtml(r.market_label || r.market || "")}</span>
          <span class="tp-when">${escapeHtml(r.team || "")}${r.opponent ? " vs " + escapeHtml(r.opponent) : ""}${r.edge != null ? ` · +${(100 * r.edge).toFixed(1)}% edge` : ""}</span></div>
        <span class="grade ${gradeClass(r.grade)}">${escapeHtml(r.grade || "")}</span></div>
      <div class="tp-foot"><b class="tp-odds">${odds(r.odds)}</b>
        <span class="tp-book">${escapeHtml(r.book || "")}</span>
        <button class="tp-add" type="button" onclick="tpTrack(${i})"
                title="Open My Bets with this pick prefilled — you enter the stake">+ My Bets</button></div>
    </div>`;
  };
  const gameCardMini = (g) => {
    const desc = `${g.pick_label || g.label || ""}`.trim() || `${g.away} @ ${g.home}`;
    const i = track(g, desc);
    return `
    <div class="tp-card ${gameBetOpenable(g) ? "openable" : ""}"${gameBetAttrs(g)}>
      <div class="tp-top"><span class="tp-tile">${teamMark(g.team || (g.side === "home" ? g.home : g.away), 30) || ""}</span>
        <div class="tp-who"><b>${escapeHtml(g.pick_label || g.label || "")}</b>
          <span>${escapeHtml(g.market_label || g.market || "")}</span>
          <span class="tp-when">${escapeHtml(g.away || "")} @ ${escapeHtml(g.home || "")}${g.edge != null ? ` · +${(100 * g.edge).toFixed(1)}% edge` : ""}</span></div>
        <span class="grade ${gradeClass(g.grade)}">${escapeHtml(g.grade || "")}</span></div>
      <div class="tp-foot"><b class="tp-odds">${odds(g.odds)}</b>
        <span class="tp-book">${escapeHtml(g.book || "")}</span>
        <button class="tp-add" type="button" onclick="tpTrack(${i})"
                title="Open My Bets with this pick prefilled — you enter the stake">+ My Bets</button></div>
    </div>`;
  };
  host.innerHTML = `
    <div class="section-title tp-title">Qellys’ top picks
      <span class="sub">— ${hcmOn() ? "A-grade only (High Confidence is on)" : "tonight’s best grades first"} · every one is journaled and graded in public</span>
      <a class="tp-more" href="#record">Why these picks?</a></div>
    <div class="tp-strip">${recs.map(propCard).join("")}${gb.map(gameCardMini).join("")}</div>`;
}

/* YOUR PERFORMANCE — the render's best panel, powered by the real
   journal export the Record page reads. Net units, win rate, ROI and
   the W-L record, the cumulative curve as a sparkline, and the
   wins/losses/pushes donut. Losing numbers render red, on purpose —
   showing the record IS the site. */
let _perfCache = null;
let _perfRange = "1m";
window._perfSetRange = (k) => { _perfRange = k; renderHomePerf(); };

async function renderHomePerf() {
  const host = document.getElementById("home-perf");
  if (!host) return;
  try {
    if (!_perfCache) {
      const r = await fetch("data/record.json", { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      _perfCache = await r.json();
    }
  } catch (e) { host.innerHTML = ""; return; }
  // SPORT-SCOPED (Ethan, 2026-08-17): "when you on a specific sport …
  // it should only show the performance for that specific sport." The
  // ledger has exported per-sport curves all along (record_by_sport);
  // this panel just never read them. When the sport in view has nothing
  // settled yet, it falls back to the whole book AND SAYS SO — an empty
  // panel reads as a broken one, an unlabelled global number on a
  // sport's own page is the bug being fixed.
  const tracked = (_perfCache.tracked_sports || []).includes(state.sport);
  const section = tracked ? (_perfCache.by_sport || {})[state.sport] : null;
  const scopedToSport = !!(section && (section.overall || {}).settled);
  const sportName = tracked ? String(state.sport || "").toUpperCase() : "";
  const all = scopedToSport ? section.overall : (_perfCache.overall || {});
  if (!all.settled) { host.innerHTML = ""; return; }
  // Range chips on the overview chart (Ethan's desktop render,
  // 2026-08-11). They used to window the CHART ONLY, with the tiles
  // staying all-time — and Ethan caught it on the phone: "when I click
  // the 1 week button here for the record, it still displays all the
  // information from our all time record."
  //
  // The old note here claimed the split was the safe choice, on the
  // grounds that a windowed chart over unlabelled all-time tiles is
  // confusing. It IS confusing — that is the bug, not the defence. A
  // panel with a range control on it is making one statement about one
  // period, and half of it silently answering a different question is
  // worse than either option, because nothing on the card says which
  // half is which. The number a bettor reads first was the wrong one.
  //
  // Every figure below now comes from the SAME window: the curve carries
  // per-day wins, losses, stake, dollars and each day's own break-even,
  // so a range block is arithmetic on real rows rather than a scaled
  // guess at them.
  const full = (scopedToSport ? section.curve : _perfCache.curve) || [];
  const spanDays = full.length > 1
    ? (new Date(full[full.length - 1].date) - new Date(full[0].date)) / 864e5 : 0;
  const PR = [["1w", 7], ["1m", 30], ["3m", 91], ["all", Infinity]];
  const avail = PR.filter(([k, d]) => k === "all" || spanDays > d);
  const rk = avail.some(([k]) => k === _perfRange) ? _perfRange : "all";
  const days = (avail.find(([k]) => k === rk) || [null, Infinity])[1];
  const windowed = !isFinite(days) ? full : full.filter((p) =>
    p.date >= new Date(Date.now() - days * 864e5).toISOString().slice(0, 10));
  const base = windowed.length && windowed[0] !== full[0]
    ? full[full.indexOf(windowed[0]) - 1].cum_u : 0;
  const curve = windowed.map((p) => ({ ...p, cum_u: +(p.cum_u - base).toFixed(2) }));
  // THE WINDOW'S OWN RECORD. Summed from the days on screen; falls back
  // to the stored all-time block when the range IS all-time, so the
  // headline figures still come from `performance()` — the one place
  // that decides what the record means — rather than being recomputed
  // slightly differently here.
  const windowStats = (rows) => {
    const sum = (k) => rows.reduce((t, r) => t + (Number(r[k]) || 0), 0);
    const w = sum("w"), l = sum("l"), n = sum("n");
    const staked = sum("staked"), net = sum("day_u");
    const beN = sum("be_n"), beSum = sum("be_sum");
    return {
      settled: n, wins: w, losses: l, pushes: Math.max(0, n - w - l),
      net_units: +net.toFixed(2),
      net_dollars: rows.some((r) => r.day_d != null) ? +sum("day_d").toFixed(2) : null,
      units_staked: +staked.toFixed(2),
      roi: staked ? net / staked : 0,
      win_rate: (w + l) ? w / (w + l) : 0,
      breakeven: beN ? beSum / beN : null,
    };
  };
  // An older record.json has no per-day dollars or break-even. Rather
  // than print a window computed from half the fields, the panel says it
  // is showing the whole book until the ledger is rebuilt — a stale
  // build should cost the feature, never the truth.
  const canWindow = full.every((r) => r.be_n != null && r.day_d != null);
  const o = (!isFinite(days) || !canWindow || !curve.length)
    ? all : windowStats(curve);
  const partial = isFinite(days) && !canWindow;
  const perfChips = avail.length > 1 ? `<span class="ra-ranges">${avail.map(([k]) =>
    `<button class="ra-range ${k === rk ? "active" : ""}"
       onclick="_perfSetRange('${k}')">${k.toUpperCase()}</button>`).join("")}</span>` : "";
  // What the numbers cover, in words, on every range including all-time.
  // The chip says which button is lit; this says what was counted, which
  // is the thing that was ambiguous.
  const betWord = scopedToSport ? `${sportName} bet(s)` : "bet(s)";
  const scopeLine = partial
    ? `<span class="perf-window">showing the whole book — rebuild the
       record for per-week figures</span>`
    : `<span class="perf-window">${!isFinite(days)
        ? `all ${all.settled} settled ${betWord}`
        : `${o.settled} settled ${betWord} over ${curve.length} graded day(s)`
      }${sportName && !scopedToSport
        ? ` — no ${sportName} picks settled yet, whole book shown` : ""}</span>`;
  const pcol = (v) => v > 0 ? "var(--good)" : v < 0 ? "var(--bad)" : "var(--text-mute)";
  const u = (v, sign) => (sign && v > 0 ? "+" : "") + Number(v).toFixed(2) + "u";
  // Sparkline: cumulative units over the last 30 graded days.
  let spark = "";
  if (curve.length > 1) {
    const ys = curve.map((c) => c.cum_u);
    const lo = Math.min(...ys), hi = Math.max(...ys), span = (hi - lo) || 1;
    const W = 560, H = 84;
    const xy = ys.map((y, i) => [
      +(i / (ys.length - 1) * W).toFixed(1),
      +(H - 8 - (y - lo) / span * (H - 16)).toFixed(1)]);
    const pts = xy.map(([x, y]) => `${x},${y}`).join(" ");
    const up = ys[ys.length - 1] >= ys[0];
    const tone = up ? "var(--good)" : "var(--bad)";
    const [ex, ey] = xy[xy.length - 1];
    // The render's chart is a filled area with a live end-point — the
    // fill fades to nothing so it reads as light under the line, not a
    // second data series.
    const scrub = escapeAttr(JSON.stringify({
      l: curve.map((c) => c.date),
      v: curve.map((c) => `${c.cum_u >= 0 ? "+" : ""}${Number(c.cum_u).toFixed(2)}u`),
    }));
    // The SVG stays as the fallback; mountGlossCharts upgrades the
    // wrapper in place to the animated, tooltip-scrubbing version when
    // the vendored library is present (see visuals.js).
    spark = `<div class="gloss-chart" style="min-height:${H}px"
      data-gloss-curve="${escapeAttr(JSON.stringify({
        values: ys, labels: curve.map((c) => c.date),
        tone: up ? "up" : "down", unit: "u", signed: true, h: H,
      }))}"><svg class="perf-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true" data-scrub="${scrub}">
      <defs><linearGradient id="perffill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${up ? "#42C268" : "#DF5953"}" stop-opacity="0.28"/>
        <stop offset="100%" stop-color="${up ? "#42C268" : "#DF5953"}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="M0,${H} L${xy.map(([x, y]) => `${x},${y}`).join(" L")} L${W},${H} Z"
            fill="url(#perffill)"/>
      <polyline points="${pts}" fill="none" stroke="${tone}" stroke-width="2.5"
        stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${ex}" cy="${ey}" r="4" fill="${tone}"/>
      <circle cx="${ex}" cy="${ey}" r="7.5" fill="${tone}" opacity="0.25"/>
    </svg></div>`;
  }
  const n = o.settled, w = o.wins || 0, l = o.losses || 0, p = o.pushes || 0;
  const seg = (count, color, off) => {
    const C = 2 * Math.PI * 40;
    return `<circle r="40" cx="50" cy="50" fill="none" stroke="${color}" stroke-width="12"
      stroke-dasharray="${(count / n * C).toFixed(1)} ${C.toFixed(1)}"
      stroke-dashoffset="${(-off / n * C).toFixed(1)}" />`;
  };
  const pct = (x) => n ? (100 * x / n).toFixed(1) + "%" : "—";
  // Render 3's Quick Tools row — doors to rooms that already exist, not
  // new features wearing buttons.
  const tools = `
    <div class="qt-row">
      <a class="qt-chip" href="#fantasy">${icon("trophy", 17)}<span class="qt-t">
        <b>Fantasy room</b><span class="k">draft kit · calendar · mock draft</span></span></a>
      <a class="qt-chip" href="#scanner">${icon("search", 17)}<span class="qt-t">
        <b>Props scanner</b><span class="k">filter every priced prop</span></span></a>
      <a class="qt-chip" href="#mybets">${icon("book", 17)}<span class="qt-t">
        <b>Bet tracker</b><span class="k">log your own tickets</span></span></a>
      <a class="qt-chip" href="#bankroll">${icon("chart", 17)}<span class="qt-t">
        <b>Bankroll</b><span class="k">stakes and limits</span></span></a>
    </div>`;
  // Render 3's Recent Results: the last graded slates, each with its own
  // record and units — the curve's tail, not a recomputation.
  const tail = full.slice(-5).reverse();
  const recent = tail.length && tail.every((r) => r.w != null) ? `
    <div class="perf-recent"><div class="perf-recent-h">Recent results</div>
      ${tail.map((r) => `<div class="perf-rrow"><span>${escapeHtml(r.date)}</span>
        <span class="rr-rec">${r.w}&#8211;${r.l}</span>
        <b style="color:${pcol(r.day_u)}">${u(r.day_u, true)}</b></div>`).join("")}
    </div>` : "";
  // Render 3's Sports Breakdown donut: settled bets per sport, from the
  // same per-sport ledger export the scoped panel reads. Always the
  // WHOLE book — the card says so in its own name, and where the desk's
  // volume sits is worth seeing from inside any one sport.
  let sportsCard = "";
  const sportRows = (_perfCache.tracked_sports || [])
    .map((s) => ({ s, o: ((_perfCache.by_sport || {})[s] || {}).overall || {} }))
    .filter((x) => x.o.settled).sort((a, b) => b.o.settled - a.o.settled);
  if (sportRows.length >= 2) {
    const tot = sportRows.reduce((t, x) => t + x.o.settled, 0);
    const cols = ["var(--brand)", "var(--good)", "var(--warn)", "var(--bad)",
                  "var(--brand-2)", "var(--text-dim)"];
    const C = 2 * Math.PI * 40;
    let off = 0;
    const segs = sportRows.map((x, i) => {
      const svg = `<circle r="40" cx="50" cy="50" fill="none"
        stroke="${cols[i % cols.length]}" stroke-width="12"
        stroke-dasharray="${(x.o.settled / tot * C).toFixed(1)} ${C.toFixed(1)}"
        stroke-dashoffset="${(-off / tot * C).toFixed(1)}"/>`;
      off += x.o.settled;
      return svg;
    }).join("");
    sportsCard = `
      <div class="card perf-card perf-sports-card">
        <div class="perf-head"><span class="rail-title">Sports breakdown</span></div>
        <div class="perf-donut-row">
          <svg class="perf-donut" viewBox="0 0 100 100" aria-hidden="true">${segs}
            <text x="50" y="47" text-anchor="middle" class="donut-n">${tot}</text>
            <text x="50" y="62" text-anchor="middle" class="donut-k">bets</text>
          </svg>
          <div class="perf-legend">${sportRows.map((x, i) => `
            <div><i style="background:${cols[i % cols.length]}"></i>
              ${escapeHtml(String(x.s).toUpperCase())} <b>${x.o.settled}</b>
              <span style="color:${pcol(x.o.net_units)}">${u(x.o.net_units || 0, true)}</span></div>`).join("")}
          </div>
        </div>
      </div>`;
  }
  host.innerHTML = `
    ${tools}
    <div class="perf-grid">
      <div class="card perf-card">
        <div class="perf-head"><span class="rail-title">Your ${scopedToSport
            ? sportName + " " : ""}performance</span>
          ${perfChips || `<span class="perf-window">${curve.length > 1
            ? "last " + curve.length + " graded days"
            : scopedToSport ? `all ${all.settled} settled ${sportName} bet(s)`
            : "the whole book"}${
            sportName && !scopedToSport
              ? ` — no ${sportName} picks settled yet` : ""}</span>`}</div>
        ${perfChips ? scopeLine : ""}
        ${(() => {
          // The render's "TODAY'S PROFIT/LOSS" headline — the most recent
          // graded slate, dated honestly when it isn't today's.
          const lastPt = curve[curve.length - 1];
          if (!lastPt || lastPt.day_u == null) return "";
          const today = new Date().toISOString().slice(0, 10);
          const label = lastPt.date === today ? "Today’s profit/loss"
            : `Last slate (${escapeHtml(lastPt.date)})`;
          return `<div class="perf-day"><span class="k">${label}</span>
            <b style="color:${pcol(lastPt.day_u)}">${u(lastPt.day_u, true)}</b></div>`;
        })()}
        <div class="perf-tiles">
          <div class="perf-tile"><span class="k">Net P&amp;L</span>
            <b style="color:${pcol(o.net_units)}">${u(o.net_units, true)}</b>
            ${o.net_dollars != null ? `<span class="sub2">${(o.net_dollars < 0 ? "−$" : "+$") + Math.abs(o.net_dollars).toFixed(2)}</span>` : ""}</div>
          <div class="perf-tile"><span class="k">Win rate</span><b>${(100 * (o.win_rate || 0)).toFixed(1)}%</b>
            ${o.breakeven != null ? `<span class="sub2">break-even ${
              (100 * o.breakeven).toFixed(1)}%</span>` : ""}</div>
          <div class="perf-tile"><span class="k">ROI</span>
            <b style="color:${pcol(o.roi)}">${(o.roi > 0 ? "+" : "") + (100 * (o.roi || 0)).toFixed(1)}%</b></div>
          <div class="perf-tile"><span class="k">Record</span><b>${w}&#8211;${l}${p ? "&#8211;" + p : ""}</b></div>
        </div>
        ${spark}
      </div>
      <div class="card perf-card perf-donut-card">
        <div class="perf-head"><span class="rail-title">Performance breakdown</span></div>
        <div class="perf-donut-row">
          <svg class="perf-donut" viewBox="0 0 100 100" aria-hidden="true">
            ${seg(w, "var(--good)", 0)}${seg(l, "var(--bad)", w)}${p ? seg(p, "var(--text-mute)", w + l) : ""}
            <text x="50" y="47" text-anchor="middle" class="donut-n">${n}</text>
            <text x="50" y="62" text-anchor="middle" class="donut-k">bets</text>
          </svg>
          <div class="perf-legend">
            <div><i style="background:var(--good)"></i>Wins <b>${w}</b> <span>(${pct(w)})</span></div>
            <div><i style="background:var(--bad)"></i>Losses <b>${l}</b> <span>(${pct(l)})</span></div>
            <div><i style="background:var(--text-mute)"></i>Pushes <b>${p}</b> <span>(${pct(p)})</span></div>
          </div>
        </div>
        ${recent}
        <a class="perf-link" href="#record">Full record &#8594;</a>
      </div>
      ${sportsCard}
    </div>`;
  if (typeof mountGlossCharts === "function") mountGlossCharts(host);
}

/* The right rail: KEY INSIGHTS (real reasons off tonight's best picks —
   the same notes the cards print) and LIVE NOW (games in progress from
   the same live states the stadium strip draws). */
function renderRail() {
  const ins = document.getElementById("rail-insights");
  const liv = document.getElementById("rail-live");
  if (!ins || !liv) return;
  const d = state.data || {};
  // Ethan's rail render (2026-08-11): dot-bulleted insights. His mock's
  // bullets are ATS-trend prose we don't compute — ours stay the real
  // sources: the model's own pick reasons, then the injury watch.
  const bullets = [];
  (d.recommendations || []).filter((r) => r.recommended)
    .sort((a, b) => (b.quality || 0) - (a.quality || 0))
    .forEach((r) => {
      const why = (r.reasons && r.reasons[0]) || r.why || "";
      if (why && bullets.length < 4)
        bullets.push(`<b>${escapeHtml(r.player)}</b> — ${escapeHtml(String(why))}`);
    });
  (d.injury_watch || []).slice(0, Math.max(0, 5 - bullets.length)).forEach((i) => {
    if (i && i.player && i.status)
      bullets.push(`<b>${escapeHtml(i.player)}</b> is ${escapeHtml(i.status)}`);
  });
  if (bullets.length) {
    ins.hidden = false;
    ins.innerHTML = `<div class="rail-title">Key insights</div>
      <ul class="rail-list">${bullets.map((b) => `<li>${b}</li>`).join("")}</ul>
      <a class="rail-more" href="#record">More insights &#8594;</a>`;
  } else { ins.hidden = true; ins.innerHTML = ""; }

  renderRailDesk();

  const games = (d.games || []).filter((g) => (g.live || {}).state === "live");
  const nLive = games.length;
  const badge = document.getElementById("sb-live-badge");
  if (badge) { badge.hidden = !nLive; badge.textContent = nLive || ""; }
  const count = document.getElementById("live-count");
  if (count) { count.hidden = !nLive; count.textContent = nLive || ""; }
  const tb = document.getElementById("tb-live-badge");
  if (tb) { tb.hidden = !nLive; tb.textContent = nLive || ""; }
  if (nLive) {
    // The render's LIVE NOW box: league + LIVE tag, logos and scores,
    // the diamond and situation on the right, tonight's line underneath
    // — every number from the slate, dashes never invented.
    const mlb = state.sport === "mlb";
    liv.hidden = false;
    liv.innerHTML = `<div class="rail-title">Live now
        <a class="rail-see" href="#live">See all</a></div>
      ${games.slice(0, 3).map((g) => {
        const lv = g.live || {};
        const fav = g.favorite || g.home;
        const sp = (side) => g.spread == null ? ""
          : `${side} ${side === fav ? "−" : "+"}${Math.abs(g.spread).toFixed(1)}`;
        const situation = [escapeHtml(lv.period || ""),
          mlb && lv.outs != null ? `${lv.outs} out${lv.outs === 1 ? "" : "s"}` : "",
          lv.clock ? escapeHtml(lv.clock) : ""].filter(Boolean).join("<br>");
        return `<div class="rlv">
          <div class="rlv-head"><span class="chip">${escapeHtml(state.sport.toUpperCase())}</span>
            <span class="rlv-live"><span class="live-dot"></span>LIVE</span></div>
          <div class="rlv-body">
            <div class="rlv-teams">
              <div class="rlv-row">${teamMark(g.away, 20)}
                <span>${escapeHtml(teamName(g.away))}</span>
                <b>${lv.away_score != null ? lv.away_score : "–"}</b></div>
              <div class="rlv-row">${teamMark(g.home, 20)}
                <span>${escapeHtml(teamName(g.home))}</span>
                <b>${lv.home_score != null ? lv.home_score : "–"}</b></div>
            </div>
            <div class="rlv-side">${mlb && lv.bases ? miniDiamond(lv.bases) : ""}
              <em>${situation}</em></div>
          </div>
          ${g.spread != null ? `<div class="rlv-lines">
            <span>${escapeHtml(sp(g.away))}${g.away_ml != null ? ` · ${g.away_ml > 0 ? "+" : ""}${g.away_ml}` : ""}</span>
            <span>${escapeHtml(sp(g.home))}${g.home_ml != null ? ` · ${g.home_ml > 0 ? "+" : ""}${g.home_ml}` : ""}</span>
          </div>` : ""}
        </div>`;
      }).join("")}`;
  } else {
    liv.hidden = false;
    liv.innerHTML = `<div class="rail-title">Live now</div>
      <p class="rail-quiet">No games in progress right now.</p>
      <a class="rail-more" href="#live">Open the live board &#8594;</a>`;
  }
}

/* The slip-shaped slot, honestly filled: the prediction desk's current
   recommendations, only when one exists, PAPER-labelled. Cached five
   minutes — the rail re-renders far more often than the desk changes.

   The cache itself is declared far ABOVE, next to the other module state,
   and the reason is written there. */
async function renderRailDesk() {
  const host = document.getElementById("rail-desk");
  if (!host) return;
  if (!_railDeskCache || Date.now() - _railDeskAt > 300000) {
    try {
      const res = await fetch("data/kalshi.json?t=" + Date.now());
      if (res.ok) { _railDeskCache = await res.json(); _railDeskAt = Date.now(); }
    } catch (e) { /* the rail just stays quiet */ }
  }
  const k = _railDeskCache || {};
  const recs = [...(k.rows || []).filter((r) => r.rec),
                ...(k.weather || []).filter((r) => r.rec)].slice(0, 2);
  if (!recs.length) { host.hidden = true; host.innerHTML = ""; return; }
  host.hidden = false;
  host.innerHTML = `<div class="rail-title">The desk
      <span class="chip rail-paper" title="Flat 0.1u paper stakes until the bucket proves itself — see the intel page">PAPER</span></div>
    ${recs.map((r) => `<div class="rail-rec">
      <span class="rail-rec-t">${escapeHtml(r.title)}</span>
      ${r.rec_side ? `<span class="chip ${r.rec_side === "YES" ? "up" : "down"}">${escapeHtml(r.rec_side)}</span>` : ""}
      <em>${r.forecast_f != null
        ? `NWS ${r.forecast_f}&deg; vs ${(r.prob * 100).toFixed(0)}&cent;`
        : `model ${(r.model_p * 100).toFixed(0)}% vs ${(r.prob * 100).toFixed(0)}&cent;`}</em>
    </div>`).join("")}
    <a class="rail-more" href="#intel">The desk&rsquo;s full board &#8594;</a>`;
}

/* The rail belongs to Home. Everywhere else the content gets the room. */
function syncRail() {
  const rail = document.getElementById("rail");
  if (!rail) return;
  const home = state.view === "recommended";
  document.body.classList.toggle("has-rail", home);
  rail.style.display = home ? "" : "none";
}

/* The strip's working controls — the render's row, with real handles.
   The league select is a MIRROR of the sidebar chips: changing it clicks
   the chip, so every side effect (hidden tabs, taglines, standalone
   exits) runs through the one existing pipeline. */
function initGamesControls() {
  const sportSel = document.getElementById("games-sport");
  if (sportSel) {
    ["nfl", "cfb", "mlb", "nba", "wnba", "ufc"].forEach((s) => {
      const o = document.createElement("option");
      o.value = s; o.textContent = s.toUpperCase();
      sportSel.appendChild(o);
    });
    sportSel.value = state.sport;
    sportSel.addEventListener("change", () => {
      const chip = document.querySelector(`.sb-chips .sport-btn[data-sport="${sportSel.value}"]`);
      if (chip) chip.click();
    });
  }
  const sortSel = document.getElementById("games-sort");
  if (sortSel) {
    try { sortSel.value = localStorage.getItem("qb_games_sort") || "start"; } catch (e) {}
    sortSel.addEventListener("change", () => {
      try { localStorage.setItem("qb_games_sort", sortSel.value); } catch (e) {}
      renderGames();
    });
  }
  const strip = document.getElementById("games-mode-strip");
  const grid = document.getElementById("games-mode-grid");
  const games = document.getElementById("games");
  const setMode = (m) => {
    if (games) games.classList.toggle("games-grid", m === "grid");
    if (strip) strip.setAttribute("aria-pressed", String(m !== "grid"));
    if (grid) grid.setAttribute("aria-pressed", String(m === "grid"));
    try { localStorage.setItem("qb_games_mode", m); } catch (e) {}
    syncStripArrows();
  };
  if (strip) strip.addEventListener("click", () => setMode("strip"));
  if (grid) grid.addEventListener("click", () => setMode("grid"));
  let mode = "strip";
  try { mode = localStorage.getItem("qb_games_mode") || "strip"; } catch (e) {}
  if (mode === "grid") setMode("grid");
  const step = (dir) => {
    const el = document.getElementById("games");
    if (el) el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: "smooth" });
  };
  const prev = document.getElementById("games-prev");
  const next = document.getElementById("games-next");
  if (prev) prev.addEventListener("click", () => step(-1));
  if (next) next.addEventListener("click", () => step(1));
  if (games) games.addEventListener("scroll",
    () => syncStripArrows(), { passive: true });
}

/* Arrows only exist while there is somewhere to scroll to. */
function syncStripArrows() {
  const el = document.getElementById("games");
  const prev = document.getElementById("games-prev");
  const next = document.getElementById("games-next");
  if (!el || !prev || !next) return;
  const scrollable = !el.classList.contains("games-grid")
    && el.scrollWidth > el.clientWidth + 8;
  prev.style.display = next.style.display = scrollable ? "" : "none";
  if (!scrollable) return;
  // Each arrow exists only while there is strip in its direction.
  const atStart = el.scrollLeft <= 4;
  const atEnd = el.scrollLeft >= el.scrollWidth - el.clientWidth - 4;
  prev.style.visibility = atStart ? "hidden" : "visible";
  next.style.visibility = atEnd ? "hidden" : "visible";
}

/* ---------------- LIVE NOW — the render's live board -----------------
   Every game in progress across the sports we model, one board. Each
   league's slate is already built to web/data; this fetches them all
   (30s cache), keeps the games whose live state says "live", and draws
   the render's card: the night art as backdrop, the two marks with big
   scores, the period (and outs/bases for MLB), and the real lines the
   slate carries — spread, total, and the moneyline when a game bet
   priced one. Only sports we actually model appear; there is no NHL
   chip because there is no NHL model. */
const LIVE_FEEDS = {
  nfl: "data/recommendations.json", mlb: "data/mlb_recommendations.json",
  nba: "data/nba.json", wnba: "data/wnba.json", cfb: "data/cfb.json",
};

/* SCORES DO NOT COME FROM THE MODEL BOARD ANY MORE — measured 2026-08-16.
   data/mlb_recommendations.json is 8MB and takes SEVEN MINUTES THIRTY-NINE
   SECONDS to build, because it prices 923 props. Live scores were read out
   of it, so a score that changes every pitch waited on the entire model and
   the site showed games 8-15 minutes behind. During a game in progress that
   reads as "the scores are broken", and nothing was broken: it was wired to
   the wrong file.

   live_build.py writes this one from a single cached schedule call. The
   BETS still come from the slow board, which is right — a price minutes old
   is defensible, a score minutes old is not. */
const LIVE_FAST = { mlb: "data/live_mlb.json" };
let _liveAll = { at: 0, games: [] };
let _liveChip = "all";

async function fetchAllLive() {
  if (Date.now() - _liveAll.at < 30000) return _liveAll.games;
  const out = [];
  await Promise.all(Object.entries(LIVE_FEEDS).map(async ([sport, url]) => {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) return;
      const d = await r.json();
      if (sport === "cfb" && d.teams) _cfbTeams = d.teams;
      // The fast scoreboard when this sport has one, the board otherwise.
      // FALLING BACK IS THE POINT: a missing or unbuilt live file must
      // leave the page exactly as it was rather than emptying it, because
      // the fast loop can be a minute behind a fresh deploy.
      let games = d.games || [];
      if (LIVE_FAST[sport]) {
        try {
          const rf = await fetch(LIVE_FAST[sport], { cache: "no-store" });
          if (rf.ok) {
            const df = await rf.json();
            if (Array.isArray(df.games) && df.games.length) {
              // MERGE, never replace. The fast file knows the score and
              // the clock; the BOARD knows the odds grid and the live
              // win-probability track. Wholesale replacement silently
              // unplugged both the moment the fast loop shipped —
              // Ethan, 2026-08-18: "the live probablility chart
              // definitly doesnt show or work." Fast fields win where
              // both speak (they are fresher); board-only fields
              // survive.
              const byKey = new Map(games.map((g) => [`${g.away}@${g.home}`, g]));
              games = df.games.map((fg) => {
                const bg = byKey.get(`${fg.away}@${fg.home}`);
                return bg ? { ...bg, ...fg,
                              live: { ...(bg.live || {}), ...(fg.live || {}) } } : fg;
              });
            }
          }
        } catch (e) {}
      }
      games.forEach((g) => {
        if ((g.live || {}).state === "live") out.push({ sport, g,
          bets: (d.game_bets || []).filter((b) => b.home === g.home && b.away === g.away) });
      });
    } catch (e) {}
  }));
  _liveAll = { at: Date.now(), games: out };
  return out;
}

function liveCardHTML({ sport, g, bets }) {
  const lv = g.live || {};
  const teams = teamsForSport(sport);
  const mark = (abbr) => teamMark(abbr, 34, teams, sport);
  const mlb = sport === "mlb";
  let situation = escapeHtml(lv.period || "");
  if (mlb && lv.outs != null) situation += ` · ${lv.outs} out${lv.outs === 1 ? "" : "s"}`;
  if (lv.clock) situation += ` ${escapeHtml(lv.clock)}`;
  // The render's line grid (Ethan, 2026-08-11): SPREAD | TOTAL | ML as
  // columns with one row per team. Only real numbers render — the slate
  // carries the line and both moneylines, but not per-side juice, so a
  // cell without a real price shows a dash, never an invented one.
  const fav = g.favorite || g.home;
  const sp = (side) => g.spread == null ? "—"
    : `${side === fav ? "−" : "+"}${Math.abs(g.spread).toFixed(1)}`;
  const mlOdds = (v) => v == null ? "—" : `${v > 0 ? "+" : ""}${v}`;
  const linesGrid = (g.spread != null || g.total != null
                     || g.away_ml != null || g.home_ml != null) ? `
    <div class="lb-table">
      <span class="lb-th"></span><span class="lb-th">Spread</span>
      <span class="lb-th">Total</span><span class="lb-th">ML</span>
      <span class="lb-tm">${escapeHtml(g.away)}</span><b>${sp(g.away)}</b>
      <b>${g.total != null ? "O " + Number(g.total).toFixed(1) : "—"}</b>
      <b>${mlOdds(g.away_ml)}</b>
      <span class="lb-tm">${escapeHtml(g.home)}</span><b>${sp(g.home)}</b>
      <b>${g.total != null ? "U " + Number(g.total).toFixed(1) : "—"}</b>
      <b>${mlOdds(g.home_ml)}</b>
    </div>` : "";
  return `
  <div class="lb-card" data-gid="${escapeHtml(gameId(g))}" data-lsport="${sport}">
    <div class="lb-head"><span class="lb-live">${icon("dot", 10)} LIVE</span>
      <span class="lb-sit">${situation}</span>
      <span class="lb-league">${sport.toUpperCase()}</span></div>
    <div class="lb-score">
      <span class="lb-team">${mark(g.away)}<em>${escapeHtml(g.away)}</em></span>
      <b>${lv.away_score != null ? lv.away_score : "–"}</b>
      <span class="lb-mid">${mlb && lv.bases ? miniDiamond(lv.bases) : ""}</span>
      <b>${lv.home_score != null ? lv.home_score : "–"}</b>
      <span class="lb-team">${mark(g.home)}<em>${escapeHtml(g.home)}</em></span>
    </div>
    ${linesGrid}
    ${lineTrackHTML(g)}
  </div>`;
}

/* How the market has moved since first pitch.

   Ethan, 2026-08-14: "when games are live, can we track the live line
   like this." It costs one credit a pull for the entire slate (see
   engine/livelines.py), and drawing it costs nothing at all — the
   history is already on disk by the time this runs.

   THE AXIS IS PROBABILITY, NOT THE PRICE. American odds have a hole in
   the middle: a team sliding from a hair-favourite to a hair-dog goes
   −101 → +101 and never takes a value between, so a chart of the raw
   number draws a cliff where the market barely twitched. The de-vigged
   probability is the same information, continuous, on an axis a reader
   already knows how to read.

   The dashed rule sits at 50% — the point where the market stops calling
   this team the favourite, which is the one crossing worth marking. */
function lineTrackHTML(g, opts = {}) {
  const t = g && g.line_track;
  if (!t || !(t.values || []).length) return "";
  // Oriented to a TEAM when a bet row asks (2026-08-18, Ethan: "also
  // for our live bets"): the stored series is the HOME win probability,
  // and a bet on the road team reads its own chance as 100 − p. Same
  // data, the bettor's side of it.
  const flip = opts.team && opts.team === t.away;
  const vals = flip ? t.values.map((v) => +(100 - v).toFixed(1)) : t.values;
  const opened = flip ? 100 - t.opened : t.opened;
  const nowV = flip ? 100 - t.now : t.now;
  const who = opts.team && (flip || opts.team === t.home) ? opts.team : t.home;
  const move = nowV - opened;
  // A move of nothing is not a story; only a real swing gets a colour.
  const cls = Math.abs(move) < 1 ? "flat" : (move > 0 ? "up" : "down");
  const pct = (v) => `${Number(v).toFixed(0)}%`;
  return `
    <div class="lb-track">
      <div class="lb-track-head">
        <span>${escapeHtml(teamName(who))} win probability, live market</span>
        <span class="lb-move ${cls}">${pct(opened)} → ${pct(nowV)}</span>
      </div>
      ${sparkline(vals, { w: 268, h: 52, line: 50, labels: t.labels,
                          stroke: "var(--brand)", minSpan: 20, unit: "%" })}
      <p class="lb-track-foot">${t.points} price${t.points === 1 ? "" : "s"}
        pulled since first pitch · de‑vigged across the books quoting both
        sides · the market’s number, not ours</p>
    </div>`;
}

/* The little diamond, occupied bases lit — the render's center graphic. */
function miniDiamond(bases) {
  const on = new Set(bases || []);
  const pt = (n, x, y) => `<rect x="${x - 4}" y="${y - 4}" width="8" height="8"
    transform="rotate(45 ${x} ${y})" fill="${on.has(n) ? "var(--gold)" : "none"}"
    stroke="${on.has(n) ? "var(--gold)" : "var(--text-faint)"}" stroke-width="1.6"/>`;
  return `<svg class="lb-diamond" viewBox="0 0 48 40" aria-hidden="true">
    ${pt(2, 24, 8)}${pt(3, 9, 22)}${pt(1, 39, 22)}</svg>`;
}

async function renderLiveBoard() {
  const host = document.getElementById("live-board");
  if (!host) return;
  const games = await fetchAllLive();
  const bySport = {};
  games.forEach((x) => { bySport[x.sport] = (bySport[x.sport] || 0) + 1; });
  const chips = ["all", ...Object.keys(LIVE_FEEDS)].filter(
    (s) => s === "all" || bySport[s]);
  const shown = games.filter((x) => _liveChip === "all" || x.sport === _liveChip);
  if (!games.length) {
    host.innerHTML = `<div class="section-title">Live now
        <span class="sub">— every game in progress across the sports we model</span></div>
      <p class="rail-quiet" style="margin:0 0 22px">No games in progress right now —
      the board below tracks tonight’s open bets as they start.</p>`;
    return;
  }
  host.innerHTML = `
    <div class="section-title">Live now
      <span class="sub">— every game in progress across the sports we model</span></div>
    <div class="lb-chips">${chips.map((s) => `
      <button class="lb-chip ${(_liveChip === s) ? "active" : ""}" data-chip="${s}">
        ${s === "all" ? "All" : s.toUpperCase()}
        <b>${s === "all" ? games.length : bySport[s]}</b></button>`).join("")}
    </div>
    <div class="lb-grid">${shown.map(liveCardHTML).join("")}</div>`;
  host.querySelectorAll(".lb-chip").forEach((b) =>
    b.addEventListener("click", () => { _liveChip = b.dataset.chip; renderLiveBoard(); }));
  host.querySelectorAll(".lb-card").forEach((el) =>
    el.addEventListener("click", () => {
      // Opening a game only works on its own sport's slate.
      const s = el.dataset.lsport;
      if (s !== state.sport) {
        const chip = document.querySelector(`.sb-chips .sport-btn[data-sport="${s}"]`);
        if (chip) chip.click();
        setTimeout(() => openGame(el.dataset.gid), 900);
      } else openGame(el.dataset.gid);
    }));
}

(function initNewLook() {
  renderGreeting();
  initHcm();
  initPz();
  initGamesControls();
  const tbMenu = document.getElementById("tb-menu");
  if (tbMenu) tbMenu.addEventListener("click", () => {
    const t = document.getElementById("menu-toggle");
    if (t) t.click();
  });
  window.addEventListener("resize", () => {
    if (typeof syncStripArrows === "function") syncStripArrows();
  });
  const search = document.getElementById("nav-search");
  if (search) search.addEventListener("click", () => {
    if (STANDALONE_MODES.includes(state.view)) exitStandaloneMode();
    switchView("players", true);
  });
  const bell = document.getElementById("nav-bell");
  if (bell) bell.addEventListener("click", () => {
    if (STANDALONE_MODES.includes(state.view)) exitStandaloneMode();
    switchView("injuries", true);
  });
  // The avatar chip: initials for a signed-in account, never a fake name.
  const acctBtn = document.getElementById("nav-acct");
  if (acctBtn) {
    const a = typeof acctState === "function" ? acctState() : null;
    if (a && a.name) acctBtn.innerHTML =
      `<span class="nav-acct-init">${escapeHtml(a.name.slice(0, 2).toUpperCase())}</span>`;
    acctBtn.addEventListener("click", () => {
      if (STANDALONE_MODES.includes(state.view)) exitStandaloneMode();
      switchView("account", true);
    });
    // WORDS WHEN SIGNED OUT. The glyph alone reads as "settings", and the
    // thing behind it is the only way to pay for anything. Resolved after
    // the server answers rather than from the local profile, because the
    // local one can say "signed in" for an account the server has since
    // deleted — and offering "Sign in" to somebody already signed in is a
    // smaller error than the reverse.
    (async () => {
      try {
        const u = await acctWho();
        if (u && u.signed_in) {
          const initials = (u.email || "?").trim().slice(0, 2).toUpperCase();
          acctBtn.innerHTML =
            `<span class="nav-acct-init">${escapeHtml(initials)}</span>`;
          acctBtn.title = `Signed in as ${u.email}`;
        } else {
          acctBtn.classList.add("nav-acct-out");
          acctBtn.innerHTML =
            `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" aria-hidden="true"><circle cx="12" cy="8" r="4"/>
               <path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/></svg><span>Sign in</span>`;
          acctBtn.title = "Sign in or create an account";
        }
      } catch (e) { /* the glyph on its own is the honest fallback */ }
    })();
  }
  // Anchor items (Top Picks, Stadiums): go Home, then scroll to the block.
  document.querySelectorAll(".sb-anchor").forEach((b) =>
    b.addEventListener("click", () => {
      if (STANDALONE_MODES.includes(state.view)) exitStandaloneMode();
      if (state.view !== "recommended") switchView("recommended", true);
      closeMobileMenu();
      // Through `revealAnchor` for the same reason the preseason pointer
      // is: if a target ever sits in a sub-tab that is not the open one,
      // a bare scroll lands nowhere and the menu item looks broken. Every
      // current target is in the default room, so this changes nothing
      // today — it is here so the next one added cannot be a dead button.
      const el = revealAnchor(b.dataset.anchor);
      // A null here is never legitimate: unlike a page anchor the browser
      // could still try, this id is OUR OWN data-anchor. Missing means the
      // block was renamed or removed and this menu item now navigates home
      // and stops — the precise shape of the preseason bug, silent again.
      // Said out loud so the headless render sweep (which fails on console
      // errors) catches the next one instead of a user reporting a button
      // that "doesn't do anything".
      if (!el) {
        console.error(`dead menu anchor: #${b.dataset.anchor} has no element`);
        return;
      }
      setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    }));
  // Sub-tab items (Game Lines, Watchlist): go Home, then open the tab —
  // through the subnav's own button so its state machinery all runs.
  document.querySelectorAll(".sb-subtab").forEach((b) =>
    b.addEventListener("click", () => {
      if (STANDALONE_MODES.includes(state.view)) exitStandaloneMode();
      if (state.view !== "recommended") switchView("recommended", true);
      closeMobileMenu();
      // The subnav is built by the room machinery after the view lands,
      // so the tab may not exist yet — retry briefly instead of racing.
      let tries = 0;
      const open = () => {
        const tab = document.querySelector(
          `#view-recommended .subnav [data-subtab="${b.dataset.subtab}"]`);
        if (tab) tab.click();
        else if (++tries < 8) setTimeout(open, 150);
      };
      setTimeout(open, 120);
    }));
  // Collapsible groups — the drawer had grown to 37 rows and two full
  // screens of scrolling (measured 1672px against a 788px phone
  // viewport, 2026-08-17). The reference pages fold behind a Library
  // heading; the daily surfaces ship open. The DEFAULT lives in the
  // markup (aria-expanded + [hidden]) so it holds before this runs, and
  // a person's choice outlives the default via localStorage.
  const FOLD_KEY = "qb_sb_folds";
  const folds = (() => {
    try { return JSON.parse(localStorage.getItem(FOLD_KEY)) || {}; }
    catch (e) { return {}; }
  })();
  document.querySelectorAll(".sb-fold").forEach((head) => {
    const grp = head.nextElementSibling;
    if (!grp || !grp.classList.contains("sb-group")) return;
    const paint = (open) => {
      head.setAttribute("aria-expanded", String(open));
      grp.hidden = !open;
    };
    const saved = folds[head.dataset.fold];
    if (saved === "open" || saved === "shut") paint(saved === "open");
    // else: the markup default already painted itself
    head.addEventListener("click", () => {
      const open = grp.hidden;
      paint(open);
      folds[head.dataset.fold] = open ? "open" : "shut";
      try { localStorage.setItem(FOLD_KEY, JSON.stringify(folds)); } catch (e) {}
    });
  });
  syncRail();
})();

