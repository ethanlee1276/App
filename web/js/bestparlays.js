/* BEST PARLAYS — every parlay the game reports posted, ranked best to worst
   (js/bestparlays.js, loaded the first time its page opens).

   Ethan, 2026-11-21: "Add a feature where it takes the best two leg and three
   leg parlays for each sport and ranks them like how we rank the most likely
   picks for the best parlays to the worst parlays to pick. I want that on a
   separate page and I want player prop parlays and touchdown parlays to have
   their own separate sections for users to scroll through and look through".

   The ranking is the engine's (engine/gameparlays.rank_parlays, the board's
   `game_parlays.ranked`), made the way the Most Likely board ranks a pick:
   each ticket's checks, a tier from how they agree (Top parlays, Strong,
   Worth a look), then our chance inside the tier (a football scorer pair's
   research first). This page draws it for the league on the sport row: a
   section for the player-prop parlays, the two-leg and the three-leg ones
   each ranked on their own, and a section for the scorer pairs (football's
   touchdown pairs, hockey's goal scorers). Each ticket is a card: its place,
   its game, its legs with their prices and our chance of each, our chance of
   the whole ticket, its class, the one book that has it whole, the price to
   take it at, and what keeps it out of the tier above; the card opens its
   game and the report, and its Bet it button puts the ticket on a book's
   slip (js/report.js parlayBet, the button every report parlay wears: Ethan,
   2026-11-15, "add bet it buttons that adds the whole parlay too your sports
   book. Both td parlays and player prop parlays"). A game already under way leaves the list (this page is
   for picking). Members only, as the reports' parlays are. */

const BP_TIERS = [["top", "Top parlays", "Every check agrees."],
                  ["strong", "Strong", "All but one check agrees."],
                  ["look", "Worth a look", "Two checks or more are against it."]];
const BP_TIER_WORD = { top: "Top parlay", strong: "Strong", look: "Worth a look" };
//: What each check against a ticket says (engine/gameparlays.RANK_AGAINST, the same keys).
const BP_AGAINST = {
  class: "a long shot by the classes (under 25% together)",
  class2: "not Safe or Balanced (every leg 60%+ and 36%+ together)",
  book: "no one book has every leg at its number",
  own: "a leg is one of the game’s other props, not a report pick",
  price: "a book’s same-game price likely pays less than it needs",
  together: "it needs the game to go another way from this game’s other tickets",
  rule: "a scorer is under our touchdown rule (40%)",
  floor: "under the pair’s bar together",
  stand_in: "a stand-in scorer fills a place",
};
const BP_CLASS = { safe: "Safe", balanced: "Balanced", pop: "Pop", long: "Long shot" };
const BP_SCORE = { anytime_td: "to score a touchdown", anytime_goal: "to score a goal", goals: "to score a goal",
                   first_td: "to score the first touchdown" };
//: Cards a tier shows before "Show all".
const BP_PAGE = 20;
let _bpSize = "twos", _bpTier = { props: "all", scorers: "all" };
const _bpAll = new Set();
//: Each drawn card's ticket for its Bet it button, by the slot's number (filled once js/report.js is in).
let _bpBet = [];

const bpPct = (x) => `${Math.round(100 * Number(x || 0))}%`;
const bpOdds = (o) => { const n = Number(o); return Number.isFinite(n) && n ? (n > 0 ? `+${n}` : `${MINUS}${Math.abs(n)}`) : ""; };
//: A leg as [who, what]: "Malik Nabers", "over 4.5 receptions" (or "to score a touchdown").
function bpLegParts(l) {
  const m = String(l.market || "");
  const down = ["UNDER", "NO"].includes(String(l.side || "").toUpperCase());
  const num = (x) => { const v = Number(x); return Number.isInteger(v) ? String(v) : v.toFixed(1); };
  const what = BP_SCORE[m] ? `${down ? "not " : ""}${BP_SCORE[m]}`
    : `${down ? "under" : "over"}${l.line == null ? "" : ` ${num(l.line)}`} ${String(l.market_label || marketWord(m)).toLowerCase()}`;
  return [String(l.player || ""), what];
}
const bpLegWords = (l) => { const [who, what] = bpLegParts(l); return `<b>${escapeHtml(who)}</b> ${escapeHtml(what)}`; };
const bpLegText = (l) => bpLegParts(l).join(" ");
//: The scorer pairs in this league: the section's name, one pair's name and the tab's line
//: (football's touchdown pairs, hockey's goal scorers).
function bpPairWords(sport) {
  return ["nfl", "cfb"].includes(sport) ? ["Touchdown parlays", "touchdown pair", "Two players, each to score a touchdown"]
    : sport === "nhl" ? ["Goal-scorer parlays", "goal-scorer pair", "Two players, each to score a goal"]
    : ["Scorer parlays", "scorer pair", "Two players, each to score"];
}
//: A ranked ticket's game among the board's parlays: the entry the ranking names (`gi`), else the first
//: with its clubs; and the board's game for it, by its clubs, then its date and kickoff when two games
//: share them (a doubleheader).
function bpEntry(d, e) {
  const games = ((d || {}).game_parlays || {}).games || [];
  const at = games[e.gi];
  return at && `${at.away}@${at.home}` === e.game ? at
    : games.find((x) => x && `${x.away}@${x.home}` === e.game) || null;
}
function bpGame(d, key, x) {
  const [away, home] = String(key || "").split("@");
  const same = ((d && d.games) || []).filter((g) => g && g.away === away && g.home === home);
  const day = (v) => String(v || "").slice(0, 10);
  const pick = same.length > 1 && x
    ? same.find((g) => (!x.date || day(g.date) === day(x.date)) && (!x.kickoff || g.kickoff === x.kickoff)) : null;
  return pick || same[0] || null;
}
const bpStarted = (g) => { const s = ((g || {}).live || {}).state; return s === "live" || s === "final"; };

/* The ranked tickets of one kind still to play, each with its ticket and game: [{e, t, g}]. */
function bpRows(d, kind) {
  const ranked = (((d || {}).game_parlays || {}).ranked || {})[kind] || [];
  const out = [];
  ranked.forEach((e) => {
    const x = bpEntry(d, e);
    const t = x && (x[kind] || [])[e.i];
    const g = bpGame(d, e.game, x);
    if (!t || (t.legs || []).length < 2 || bpStarted(g)) return;
    out.push({ e, t, g, x });
  });
  return out;
}

function bpCardHTML(row, n, kind, sport) {
  const { e, t, g } = row;
  const [away, home] = e.game.split("@");
  const when = g ? whenLabel(g.date, g.kickoff) : "";
  const cls = kind !== "scorers" && t.class && BP_CLASS[t.class] ? t.class : "";
  const ob = t.one_book || {};
  const against = (e.against || []).map((k) => BP_AGAINST[k]).filter(Boolean);
  const size = kind === "twos" ? "Two-leg parlay" : kind === "threes" ? "Three-leg parlay" : bpPairWords(sport)[1].replace(/^./, (c) => c.toUpperCase());
  const research = kind === "scorers" && (t.legs || []).some((l) => l.research != null)
    ? (t.legs || []).reduce((a, l) => a + (Number(l.research) || 0), 0) : null;
  return `<article class="bp-card tier-${escapeAttr(e.tier)}">
    <div class="bp-head">
      <span class="bp-rank" aria-label="Number ${n}">${n}</span>
      <div class="bp-game"><b>${escapeHtml(teamName(away))} at ${escapeHtml(teamName(home))}</b>
        <span>${escapeHtml([size, when].filter(Boolean).join(" · "))}</span></div>
      <div class="bp-p"><b>${bpPct(t.joint)}</b><span>by our numbers</span></div>
    </div>
    <div class="bp-chips"><span class="bp-tier tier-${escapeAttr(e.tier)}">${escapeHtml(BP_TIER_WORD[e.tier] || "")}</span>${
      cls ? `<span class="bp-class ${escapeAttr(cls)}" title="${escapeAttr(t.class_why || "")}">${escapeHtml(BP_CLASS[cls])}</span>` : ""}${
      research != null ? `<span class="bp-research">Research ${research}</span>` : ""}${
      t.filled || t.stand_ins ? `<span class="bp-fill">A leg from beyond the report’s picks</span>` : ""}</div>
    <ol class="bp-legs">${(t.legs || []).map((l) => `<li>
      <span class="bp-leg-what">${bpLegWords(l)}</span>
      <span class="bp-leg-price">${escapeHtml([bpOdds(l.odds), l.book || ""].filter(Boolean).join(" "))}</span>
      <span class="bp-leg-p">${bpPct(l.p)}</span></li>`).join("")}</ol>
    <p class="bp-line">${t.take_words ? `Take it at <b>${escapeHtml(t.take_words)}</b> or better` : ""}${
      t.fair_words ? `${t.take_words ? " · " : ""}fair ${escapeHtml(t.fair_words)}` : ""}</p>
    ${ob.words ? `<p class="bp-book${ob.book ? " has" : ""}">${escapeHtml(ob.words)}</p>` : ""}
    ${against.length ? `<p class="bp-why">${e.tier === "strong" ? "One check against it" : "Against it"}: ${escapeHtml(against.join("; "))}.</p>` : ""}
    <div class="bp-acts"><span class="bp-bet" data-bp-bet="${_bpBet.push({ legs: t.legs || [],
      what: `${size} · ${(t.legs || []).map(bpLegText).join(" + ")}` }) - 1}"></span>${
      g ? `<button type="button" class="btn ghost bp-open" data-gid="${escapeAttr(gameId(g))}">Open the game and its report</button>` : ""}</div>
  </article>`;
}

/* One section: its tier chips, then each tier's tickets best to worst, numbered down the whole list. */
function bpSectionHTML(rows, kind, sport, section) {
  if (!rows.length) return "";
  const tier = BP_TIERS.some(([k]) => k === _bpTier[section]) ? _bpTier[section] : "all";
  const count = (k) => rows.filter((r) => r.e.tier === k).length;
  const chips = [["all", "All", rows.length], ...BP_TIERS.map(([k, title]) => [k, title, count(k)])]
    .filter(([k, , n]) => n || k === tier)
    .map(([k, title, n]) => `<button type="button" class="bp-chip tier-${k}${k === tier ? " on" : ""}" data-bp-tier="${k}"
      data-bp-section="${section}" aria-pressed="${k === tier}">${escapeHtml(title)} <span>${n}</span></button>`).join("");
  const groups = BP_TIERS.map(([k, title, words]) => {
    const mine = rows.map((r, i) => [r, i + 1]).filter(([r]) => r.e.tier === k);
    if (!mine.length || (tier !== "all" && tier !== k)) return "";
    const key = `${section}:${kind}:${k}`;
    const shown = _bpAll.has(key) ? mine : mine.slice(0, BP_PAGE);
    return `<section class="bp-tier-sec tier-${k}" aria-label="${escapeAttr(title)}">
      <h3 class="bp-tier-h">${escapeHtml(title)} <span>${mine.length}</span></h3>
      <p class="bp-tier-words">${escapeHtml(words)}</p>
      ${shown.map(([r, n]) => bpCardHTML(r, n, kind, sport)).join("")}
      ${shown.length < mine.length ? `<button type="button" class="btn ghost bp-more" data-bp-all="${escapeAttr(key)}">Show all ${
        mine.length}</button>` : ""}
    </section>`;
  }).join("");
  return `<div class="bp-chips-row" role="group" aria-label="Tiers">${chips}</div>${groups}`;
}

async function renderBestParlays() {
  const host = document.getElementById("bestparlays-body");
  if (!host) return;
  const d = state.data;
  if (!d) return;
  const sport = state.sport;
  const sub = document.getElementById("bestparlays-sub");
  _bpBet = [];
  if (d.locked && d.locked.game_parlays) {
    host.innerHTML = memberLockHTML("The best parlays are for members", "Every parlay our game reports posted, ranked best to "
      + "worst, with its legs, our chance and the one book that has it whole. How the reports’ parlays have done is free, on the Record page.");
    return;
  }
  const ranked = (d.game_parlays || {}).ranked;
  if (!ranked) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("trophy", 30)}</div>
      <div class="es-title">No parlays ranked on this board yet</div>
      <div class="es-sub">Every game report’s parlays land here, ranked best to worst, as the board builds them.</div></div>`;
    return;
  }
  const twos = bpRows(d, "twos"), threes = bpRows(d, "threes"), pairs = bpRows(d, "scorers");
  const size = _bpSize === "threes" || !twos.length ? (threes.length ? "threes" : "twos") : "twos";
  const [pairTitle, , pairHint] = bpPairWords(sport);
  const football = ["nfl", "cfb"].includes(sport);
  const sizeChips = [["twos", "Two-leg", twos.length], ["threes", "Three-leg", threes.length]].filter(([, , n]) => n)
    .map(([k, label, n]) => `<button type="button" class="bp-size${k === size ? " on" : ""}" data-bp-size="${k}" aria-pressed="${k === size}">${
      escapeHtml(label)} <span>${n}</span></button>`).join("");
  const props = twos.length || threes.length
    ? `<div class="bp-size-row" role="group" aria-label="Parlay size">${sizeChips}</div>
       <p class="bp-lead">Tier first, as on Most Likely, then our chance of the whole ticket. The checks: its class, one book has every leg, every leg is the report’s pick, the price can pay it, and it needs the same game as the other tickets.</p>
       ${bpSectionHTML(size === "twos" ? twos : threes, size, sport, "props")}`
    : "";
  const scorers = pairs.length
    ? `<p class="bp-lead">Tier first, then ${
        football ? "our research on the two scorers, then " : ""}our chance both score. The checks: ${
        football ? "each scorer at our 40% touchdown rule" : "the pair clears our bar together"}, no stand-in, and it needs the same game as the other tickets.</p>
       ${bpSectionHTML(pairs, "scorers", sport, "scorers")}`
    : "";
  const left = ranked.left_off || {};
  const started = (d.games || []).filter(bpStarted).length;
  // THE POST TIME (engine/gameparlays.hold_until_post, step ABD): a game's parlays post once, shortly before
  // it starts, from the newest news and lines, and never change; until then it is not listed, and the page
  // says when the next one posts.
  const nextAt = ranked.next_post ? Date.parse(ranked.next_post) : NaN;
  const waiting = left.waiting ? `${left.waiting === 1 ? "1 game’s" : `${left.waiting} games’`} parlays post later, about ${
    Number(ranked.post_lead) || 90} minutes before each starts, once the news is in${
    Number.isFinite(nextAt) ? ` (the next at ${typeof tzTime === "function" ? tzTime(new Date(nextAt)) : ""})` : ""}` : "";
  const foot = [waiting, started ? `${plural(started, "game")} already under way ${started === 1 ? "is" : "are"} not listed` : "",
                left.gone ? `${plural(left.gone, "ticket")} with a leg no book lists now ${left.gone === 1 ? "is" : "are"} left off` : ""]
    .filter(Boolean).join(" · ");
  if (sub) sub.textContent = "— every report parlay, ranked best to worst";
  const body = subtabbedHTML("bestparlays", [
    ["props", "Player prop parlays", "Two-leg and three-leg tickets", props],
    ["scorers", pairTitle, pairHint, scorers]]);
  // A ranking that failed says so (engine/gameparlays RANK_ERROR): its empty lists are not a quiet day.
  host.innerHTML = body.trim()
    ? `${body}${foot ? `<p class="set-note bp-foot">${escapeHtml(foot)}.</p>` : ""}`
    : ranked.error
    ? `<div class="empty-slate"><div class="es-icon">${icon("trophy", 30)}</div>
        <div class="es-title">The ranking did not build on this board</div>
        <div class="es-sub">Each game’s parlays are still on its report; this page ranks them again when the board next builds.</div></div>`
    : `<div class="empty-slate"><div class="es-icon">${icon("trophy", 30)}</div>
        <div class="es-title">No parlays to rank right now</div>
        <div class="es-sub">${escapeHtml(foot ? `${foot}.` : "The game reports post their parlays with the board; they land here, ranked, as it builds.")}</div></div>`;
  bindSubtabs(host);
  if (typeof revealChildren === "function") revealChildren(host);
  // Each card's Bet it button, the report's own (js/report.js parlayBet), once that file is in.
  if (_bpBet.length && typeof loadReport === "function") loadReport().then((R) => {
    if (!R || typeof R.parlayBet !== "function") return;
    host.querySelectorAll("[data-bp-bet]").forEach((el) => {
      const b = _bpBet[Number(el.dataset.bpBet)];
      el.outerHTML = b ? R.parlayBet(b.legs, b.what) || "" : "";
    });
  });
  host.querySelectorAll("[data-bp-size]").forEach((b) => b.addEventListener("click", () => {
    _bpSize = b.dataset.bpSize;
    renderBestParlays();
  }));
  host.querySelectorAll("[data-bp-tier]").forEach((b) => b.addEventListener("click", () => {
    _bpTier[b.dataset.bpSection] = b.dataset.bpTier;
    renderBestParlays();
  }));
  host.querySelectorAll("[data-bp-all]").forEach((b) => b.addEventListener("click", () => {
    _bpAll.add(b.dataset.bpAll);
    renderBestParlays();
  }));
}
