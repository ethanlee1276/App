/* SETTLED TICKETS — js/settled.js, with css/settled.css (step ACC, 22 November 2026).

   Loaded with the pages that draw a finished game's report tickets, never with the first paint (the first
   visit keeps its budget, tests/test_the_first_paint_has_a_budget.py): the game's report (app.js
   loadReport), Report Picks and the Record (app.js ROOM_WITH). Reads app.js's pick grader's words
   (RES_GAME_MARKETS, RES_SCORE_MARKETS), marketWord, icon, teamMark, playerAvatar and teamsForSport. */
/* A SETTLED TICKET, DRAWN AS A BETTING APP'S "RECENTLY SETTLED" LIST DRAWS ONE (step ACC, 22 November 2026).
   Ethan, with a screenshot of one: "how you can scroll through and see how each leg is highlighted green if it
   won, and if it's highlighted red, that leg lost, and then the whole parlay will be highlighted green if that
   parlay won. So that's how I want it to look like when you scroll through the game report data, looking to see
   if those parlays and picks won or lost." One drawing for every list of a finished game's report tickets (the
   game's report, Report Picks, the Record): the ticket's name over how it went and its legs' tally ("Won · 3
   wins", "Lost · 2 wins, 1 loss"), the units it won or lost at its price on the right, then each leg in its own
   box, its border green when it won and red when it lost: the bet ("Over 249.5 · Joe Burrow Passing Yards"),
   and under it what he did, the two clubs with the final score, and the day ("409 · PIT 18 – 38 CIN · Final
   11/15"). The whole ticket's border and tint say how it went. Each box carries a check or an X and the ticket
   says won or lost in words, so the colour is never the only sign. A report pick is one such box. */
const SETTLED_SCORE = { anytime_td: "To score a touchdown", anytime_goal: "To score a goal",
                        goals: "To score a goal", first_td: "To score the first touchdown" };
const SETTLED_WORD = { won: "Won", lost: "Lost", push: "Push", void: "Void", pending: "Waiting on the box score" };
const settledNum = (x) => { const v = Number(x); return Number.isInteger(v) ? String(v) : v.toFixed(1); };
const settledGameBet = (b) => !!b && (b.game === true || !!b._game_leg || b.kind === "game"
  || RES_GAME_MARKETS.has(String(b.market || "").toLowerCase()));
//: The bet as the screenshot says it, the side and line first: "Over 249.5 · Joe Burrow Passing Yards",
//: "Ja’Marr Chase · To score a touchdown". A game bet is said in its caller's own words (``gameWords``).
function settledBetWords(b, gameWords) {
  if (!b) return "";
  const m = String(b.market || "").toLowerCase();
  const down = ["UNDER", "NO"].includes(String(b.side || "").toUpperCase());
  if (settledGameBet(b)) return gameWords || "";
  if (SETTLED_SCORE[m]) return `${b.player || ""} · ${down ? "Not to score" : SETTLED_SCORE[m]}`;
  const line = b.line == null || b.line === "" || !Number.isFinite(Number(b.line)) ? "" : ` ${settledNum(b.line)}`;
  return `${down ? "Under" : "Over"}${line} · ${b.player || ""} ${b.market_label || marketWord(m)}`;
}
//: What the leg's man did, first on its line: "409", "Scored 2", "Didn’t play"; a game bet's final says it.
function settledDid(b, res) {
  if (!res) return "";
  if (res.status === "void") return "Didn’t play";
  if (res.status === "pending") return SETTLED_WORD.pending;
  const a = Number(res.actual);
  if (settledGameBet(b) || res.actual == null || !Number.isFinite(a)) return "";
  const m = String((b && b.market) || "").toLowerCase();
  if (SETTLED_SCORE[m] || RES_SCORE_MARKETS.has(m)) return a >= 1 ? `Scored${a > 1 ? ` ${settledNum(a)}` : ""}` : "Didn’t score";
  return settledNum(a);
}
//: "PIT [logo] 18 – 38 [logo] CIN · Final 11/15" (g: {sport, home, away, final, date}); without a final,
//: "PIT at CIN" and the day. ``lead``: after what he did, its own dot first, so it wraps whole on a phone.
function settledGameHTML(g, lead) {
  if (!g || !g.home || !g.away) return "";
  const sport = g.sport || state.sport;
  const map = typeof teamsForSport === "function" ? teamsForSport(sport) : null;
  const mark = (t) => (typeof teamMark === "function" ? teamMark(t, 16, map, sport) : "");
  const f = g.final || {};
  const fin = f.home != null && f.away != null && Number.isFinite(Number(f.home)) && Number.isFinite(Number(f.away));
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(g.date || ""));
  const day = m ? `${Number(m[1])}/${Number(m[2])}` : "";
  // Beside its mark a club's code is the mark's own label ("CHI"), so a screen reader heard each one twice,
  // "CHI CHI 39 – 35 DET DET": the printed code steps aside for it there. With no mark it is the only name.
  const club = (t, marked) => `<span class="st-club"${marked ? ' aria-hidden="true"' : ""}>${escapeHtml(t)}</span>`;
  const am = fin ? mark(g.away) : "", hm = fin ? mark(g.home) : "";
  const game = fin
    ? `${club(g.away, !!am)}${am}<b class="st-score">${settledNum(f.away)} – ${settledNum(f.home)}</b>${hm}${club(g.home, !!hm)}`
    : `${club(g.away)}<span>at</span>${club(g.home)}`;
  const when = [fin ? "Final" : "", day].filter(Boolean).join(" ");
  // The day keeps its dot: on a phone it wraps whole onto the next line, never leaving a dot behind.
  return `<span class="st-game">${lead ? '<span class="st-dot" aria-hidden="true">·</span>' : ""}${game}</span>${when
    ? `<span class="st-when"><span class="st-dot" aria-hidden="true">·</span>${when}</span>` : ""}`;
}
//: One leg or one pick in its box: {bet, res (pickResult's verdict), words (a game bet's), open, note}.
function settledLegHTML(l, g) {
  const b = l.bet || {}, res = l.res || null, st = (res && res.status) || "pending";
  const tone = st === "won" ? "won" : st === "lost" ? "lost" : "even";
  const did = settledDid(b, res);
  // Each part after the first carries its own dot, so a line that wraps never ends on one.
  const dot = '<span class="st-dot" aria-hidden="true">·</span>';
  const sub = [did ? `<span class="st-did">${escapeHtml(did)}</span>` : "", settledGameHTML(g, !!did),
               l.note ? `<span class="st-note">${dot}${escapeHtml(l.note)}</span>` : ""].filter(Boolean).join("");
  const mark = icon(st === "won" ? "check" : st === "lost" ? "cross" : "dash", 13);
  const door = l.open && b.player && !settledGameBet(b) ? ` data-open="player:${escapeAttr(slugify(b.player))}"` : "";
  return `<li class="st-leg ${tone}"${door}><span class="st-leg-text"><b class="st-leg-bet">${
      escapeHtml(settledBetWords(b, l.words))}</b>${sub ? `<span class="st-leg-sub">${sub}</span>` : ""}</span>
    <span class="st-leg-mark ${tone}"><span class="st-sr">${SETTLED_WORD[st] || ""}</span>${mark}</span></li>`;
}
//: How a ticket's legs went: "3 wins", "2 wins, 1 loss", "1 win, 1 void, 1 waiting".
function settledTally(legs) {
  const n = (s) => legs.filter((l) => (((l || {}).res || {}).status || "pending") === s).length;
  return [[n("won"), "win", "wins"], [n("lost"), "loss", "losses"], [n("push"), "push", "pushes"],
          [n("void"), "void", "voids"], [n("pending"), "waiting", "waiting"]]
    .filter(([k]) => k).map(([k, one, many]) => `${k} ${k === 1 ? one : many}`).join(", ");
}
//: The units a ticket won or lost at its price ("+1.68u", "−1.00u"): ``units`` when the record has them.
function settledUnits(status, dec, units) {
  const u = units != null && Number.isFinite(Number(units)) ? Number(units)
    : status === "won" && dec > 1 ? dec - 1 : status === "lost" ? -1 : status === "push" || status === "void" ? 0 : null;
  return u == null ? "" : `${u > 0 ? "+" : u < 0 ? MINUS : ""}${Math.abs(u).toFixed(2)}u`;
}
//: The whole ticket: {title, status, legs: [{bet, res, words, open}], dec (its price), units, note, more (HTML under it)}.
function settledTicketHTML(t, g) {
  const legs = t.legs || [], st = t.status || "pending";
  const tone = st === "won" ? "won" : st === "lost" ? "lost" : "even";
  const verdict = { won: "Won", lost: "Lost", push: "Void", void: "Void", pending: "Waiting" }[st] || "";
  const dec = Number(t.dec);
  const price = dec > 1 ? (dec >= 2 ? `+${Math.round((dec - 1) * 100)}` : `${MINUS}${Math.round(100 / (dec - 1))}`) : "";
  const pay = settledUnits(st, dec, t.units);
  const sport = (g && g.sport) || state.sport;
  const map = typeof teamsForSport === "function" ? teamsForSport(sport) : null;
  // Up to three of its legs' faces, a club's mark for a game bet, as the screenshot's ticket wears them.
  const faces = legs.slice(0, 3).map((l) => {
    const b = l.bet || {};
    if (settledGameBet(b) || !b.player) return b.team && typeof teamMark === "function" ? teamMark(b.team, 22, map, sport) : "";
    return typeof playerAvatar === "function" ? playerAvatar(b.player, b.team, { size: 22, headshot: b.headshot, map }) : "";
  }).filter(Boolean);
  const tally = settledTally(legs);
  return `<div class="st-tix ${tone}">
    <div class="st-tix-head">${faces.length ? `<span class="st-tix-faces n${faces.length}" aria-hidden="true">${
        faces.map((f) => `<span>${f}</span>`).join("")}</span>` : ""}
      <span class="st-tix-name"><b>${escapeHtml(t.title || "Parlay")}</b><span class="st-tix-tally"><span class="st-tix-verdict">${
        verdict}</span>${tally ? ` · ${escapeHtml(tally)}` : ""}${t.note ? ` · ${escapeHtml(t.note)}` : ""}</span></span>
      ${pay || price ? `<span class="st-tix-pay">${pay ? `<b>${pay}</b>` : ""}${price ? `<span>${price}</span>` : ""}</span>` : ""}
    </div>
    <ol class="st-legs">${legs.map((l) => settledLegHTML(l, g)).join("")}</ol>${t.more || ""}
  </div>`;
}
