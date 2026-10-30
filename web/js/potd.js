/* THE PICK OF THE DAY, EVERY LEAGUE — the one pick a reader without a plan
   is given (js/potd.js, loaded the first time its page opens).

   Ethan, 2026-10-30: "make the picks of the day free. just the pick of the
   day. not the best bet or anything like that." So this page is every
   league's card side by side, read from the one small file the refresh
   cycle writes beside the day's top pick (`day_top_pick.json`, `leagues`),
   and it is where a free account's Home tab lands (app.js _switchViewNow).

   WHAT IS NOT HERE IS THE POINT. The public copy of that file carries the
   pick on a day it is a bet and nothing else from the board (engine/gate
   free_potd): never the lean a card declined, never the board's best bet on
   a day the pick sits out — a member sees that line here, a reader without
   a plan sees that one exists — and never the pick tracked live, which is
   the Live tab's and a member's. */

// The leagues in the order a reader looks for them; a league with no card
// today (out of season, not built yet) is simply absent.
const PD_ORDER = ["nfl", "cfb", "nba", "nhl", "mlb", "wnba", "ufc"];
// Whose number the fair is, in the home card's own words.
const PD_WITNESS = { exchange: "the exchange’s price", sharp: "the sharp book’s fair",
                     market: "the market’s fair", model: "our number" };
// The page re-reads the file while it stays open, as the boards rebuild.
const PD_REFRESH_MS = 180000;
let _pdTimer = null;

async function renderPotdPage() {
  const host = document.getElementById("potd-body");
  if (!host) return;
  clearTimeout(_pdTimer);
  const walled = isWalled();
  const sub = document.getElementById("potd-sub");
  if (sub) sub.textContent = walled ? "— one pick a day in every league, free" : "— every league’s pick today";
  if (!host.firstElementChild) host.innerHTML = `<div class="skeleton-card" aria-hidden="true"></div>`;
  let top = {};
  try {
    const res = await paidFetch("day_top_pick.json");
    top = res.ok ? await res.json() : {};
  } catch (e) { top = {}; }
  // The home card's own line reads the same file; keep it as fresh.
  if (top && typeof top === "object" && "pick" in top) _topPickCache = top;
  const rec = await loadRecordOnce().catch(() => ({})) || {};
  if (state.view !== "potd") return;
  host.innerHTML = pdPageHTML(top || {}, rec, walled);
  _pdTimer = setTimeout(() => { if (state.view === "potd") renderPotdPage(); }, PD_REFRESH_MS);
}

// When the file was written, on the reader's clock.
function pdWhen(iso) {
  const t = new Date(String(iso || ""));
  if (isNaN(t)) return "";
  return `<p class="pd-when">Updated ${escapeHtml(t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }))}</p>`;
}

function pdName(s) { return (SPORT_META[s] || {}).name || LEAGUE_LABEL[s] || String(s).toUpperCase(); }

// A card names a bet, rather than the nearest thing to one (potd.has_pick).
function pdIsBet(card) {
  const pick = (card || {}).pick, call = String(((card || {}).verdict || {}).call || "bet");
  return !!(pick && typeof pick === "object" && !String(pick.below_bar || "").trim() && call === "bet");
}

// W-L, units and hit rate, or "" before anything has settled.
function pdTally(r) {
  if (!r || !r.settled) return "";
  const u = Number(r.net_units || 0);
  return `${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ""} · ${u >= 0 ? "+" : MINUS}${Math.abs(u).toFixed(2)}u · ${
    Math.round((r.win_rate || 0) * 100)}% hit`;
}

// The pick's face: a player's photo, a side's logo, a total's league mark.
function pdMark(pick, sport) {
  const m = String(pick.market || "").toLowerCase();
  if (m === "total") return leagueMark(sport, 30);
  if (["moneyline", "spread", "team_total"].includes(m) || (!pick.player && pick.team))
    return teamMarkIn(sport, pick.team || pick.player, 30);
  return playerAvatar(pick.player, pick.team, { size: 30, headshot: pick.headshot });
}

function pdBetHTML(card, sport) {
  const pick = card.pick;
  const pays = pick.payout_units == null ? "" : `pays ${Number(pick.payout_units).toFixed(2)}u on 1u`;
  const vs = pick.opponent ? `${teamNameIn(sport, pick.team)} vs ${teamNameIn(sport, pick.opponent)}` : "";
  const price = pick.odds != null ? american(pick.odds) + (pick.book ? ` at ${escapeHtml(pick.book)}` : "") : escapeHtml(pick.book || "");
  const fair = pick.fair_prob == null ? null : Math.round(pick.fair_prob * 100);
  const theirs = pick.price_implied != null ? Math.round(pick.price_implied * 100) : null;
  // Our own number never leads (the home card's rule): a model-only pick is
  // refused by the engine, and the fair shown is whoever priced it.
  const why = fair == null || pick.evidence === "model" ? ""
    : `<p class="pd-fair"><b>${fair}%</b> ${PD_WITNESS[pick.evidence] || "the market’s fair"}${
        theirs != null ? ` · this price implies ${theirs}%` : ""}</p>`;
  return `<div class="pd-bet"><span class="pick-id">${pdMark(pick, sport)}</span>
      <span class="pd-bet-t"><b>${potdBetText(pick, sport)}</b>
        <small>${[price, pays, vs].filter(Boolean).join(" · ")}</small></span></div>
    ${why}${betItHTML(pick, "btn primary potd-betit")}`;
}

function pdCardHTML(sport, card, ctx) {
  const { rec, locked, walled, topSport } = ctx;
  const name = pdName(sport);
  const tally = pdTally(((rec || {}).potd_by_sport || {})[sport]);
  const days = ((((rec || {}).potd_days || {}).by_sport) || {})[sport];
  const often = days && days.slates ? `a pick on ${days.picked} of the last ${plural(days.slates, "slate")}` : "";
  const bet = pdIsBet(card);
  let body;
  if (card.off_day) {
    body = `<p class="pd-why">${icon("clock", 12)} ${escapeHtml(String(card.note || "Not a pick day for this league."))}</p>`;
  } else if (bet) {
    body = potdCallStrip(card) + pdBetHTML(card, sport);
  } else {
    // NO BET, said once (the strip carries the reason), then what a member
    // has on such a day — the board's best bet — or that one exists.
    const bb = card.board_best;
    const n = Number(locked[`leagues.${sport}.board_best`] || 0);
    body = potdCallStrip(card) + (bb
      ? `<p class="pd-best">${icon("star", 13)} Best on the board${bb.tonight ? " tonight" : ""}: <b>${escapeHtml(bb.label || "")}</b> ${
          bb.odds != null ? american(bb.odds) : ""}${bb.book ? ` at ${escapeHtml(bb.book)}` : ""}</p>`
      : n && walled
        ? `<p class="pd-best pd-locked">${icon("lock", 12)} Members see the board’s best bet tonight${
            n > 1 ? ` — one of ${n} staked` : ""}.</p>` : "");
  }
  const lead = sport === topSport && bet;
  return `<article class="card pd-card${lead ? " pd-lead" : ""}${bet ? " is-bet" : ""}">
    <header class="pd-head"><span class="pd-logo">${leagueMark(sport, 22)}</span>
      <b>${escapeHtml(name)}</b>${lead ? `<span class="pd-tag">Top pick today</span>` : ""}</header>
    ${body}
    ${tally || often ? `<p class="pd-rec">${[tally ? `${escapeHtml(name)} Picks of the Day: ${tally}` : "", often].filter(Boolean).join(" · ")}</p>` : ""}
    ${walled ? "" : `<a class="pd-door" href="#${escapeAttr(sport)}">Open the ${escapeHtml(name)} board →</a>`}
  </article>`;
}

function pdPageHTML(top, rec, walled) {
  const leagues = top.leagues && typeof top.leagues === "object" ? top.leagues : {};
  const locked = top.locked && typeof top.locked === "object" ? top.locked : {};
  const topSport = pdIsBet(top) ? String(top.sport || "") : "";
  // The day's top pick first, then the leagues' other bets in the order the
  // ranking left them, then the cards that sat out, then the days off.
  const beat = (top.runners_up || []).map((p) => p.sport);
  const rank = (s) => {
    const c = leagues[s];
    if (s === topSport) return -1;
    if (pdIsBet(c)) return beat.includes(s) ? beat.indexOf(s) : 50;
    return c && c.off_day ? 200 : 100;
  };
  const shown = Object.keys(leagues).filter((s) => leagues[s] && typeof leagues[s] === "object")
    .sort((a, b) => rank(a) - rank(b) || PD_ORDER.indexOf(a) - PD_ORDER.indexOf(b));
  const all = (rec || {}).potd, days = (rec || {}).potd_days || {};
  const head = pdTally(all);
  const lede = `<p class="pd-lede">One bet a day per league — priced against a sharp book’s fair, never our model alone —
    and every one of them graded on the Record, the misses with the wins.${
    head ? ` <b>So far: ${head}</b>${all.open ? ` (${all.open} riding)` : ""}.` : ""}${
    days.slates ? ` It named a pick on ${days.picked} of the last ${plural(days.slates, "slate day")}; the rest it sat out.` : ""}</p>`;
  const ctx = { rec, locked, walled, topSport };
  const cards = shown.length
    ? `<div class="pd-grid">${shown.map((s) => pdCardHTML(s, leagues[s], ctx)).join("")}</div>`
    : `<div class="card pd-empty">${icon("clock", 14)} No league has named today’s pick yet — each board names its own as it builds,
        and its card lands here when it does.</div>`;
  const when = pdWhen(top.generated_at);
  const lock = walled ? memberLockHTML("Everything else on the boards is for members",
    "Most Likely, the Edge picks, every prop and game line we price, Best Bets, the Pick of the Day tracked live with its chance to cash, and Ask Qellys open with a plan.") : "";
  return lede + cards + when + lock;
}
