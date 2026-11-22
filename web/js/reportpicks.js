/* REPORT PICKS — every bet and parlay our game reports posted, game by game
   (js/reportpicks.js, loaded the first time its page opens).

   Ethan, 2026-11-16: "we should have a page like the most likely bets page
   but all game report parlays and bets". The board carries the reports' bets
   in one list (engine/reportbets, `report_bets`: each pick once a game, with
   where the report shows it, its price and our chance) and each game's
   parlays (`game_parlays`). This page lays them out game by game, in the
   board's order, with a chip to jump to each: the game's picks as the
   Tonight tab draws a pick (app.js deckPickRow: the face, the pick, the
   price, our chance, and on a finished game how it went), each saying where
   the report shows it, then the game's three-leg tickets and pairs as the
   report draws them (js/report.js gameTickets, graded once the game is
   over). A pick opens the page it opens everywhere (app.js likelyOpen); the
   game's name opens the game and its report. Every pick and ticket is graded
   on the Record page's "The Game Report Picks and Parlays" (record.js
   recReportBook), which this page's own Record tab draws too. */

// Where the report shows a pick (engine/reportbets.SOURCE_WORDS).
const RP_SOURCE = { card: "Our picks", read: "Matchup read", breakout: "Breakout candidate", fade: "Fade" };
/* A pick's line under its name says where else the report makes its case. Every row under "Picks" said "Our
   picks", four times a game (19 November 2026): the card's own pick is the plain case and says nothing; a
   matchup read's, a breakout candidate's or a fade's pick names itself, and a card pick a read also backs
   says so ("Also a matchup read"), which is the one worth knowing. */
function rpSourceNote(r) {
  const got = (r && r.sources) || [];
  const other = got.filter((s) => s !== "card").map((s) => RP_SOURCE[s] || s);
  if (!other.length) return "";
  return got.includes("card") ? `Also a ${other.join(" and a ").toLowerCase()}` : other.join(" · ");
}

//: The board's game for a report's "AWAY@HOME".
function rpGame(d, key) {
  const [away, home] = String(key || "").split("@");
  return ((d && d.games) || []).find((g) => g && g.away === away && g.home === home) || null;
}

//: The record so far: the report book's picks and the reports' parlays, this league's.
function rpRecordLine(rec, sport) {
  const r = ((rec || {}).report_by_sport || {})[sport] || {};
  const g = ((rec || {}).two_leg || {}).game || {};
  const pair = ["nfl", "cfb"].includes(sport) ? "touchdown pairs" : sport === "nhl" ? "goal-scorer pairs" : "scorer pairs";
  const bits = [];
  if (r.settled) {
    const u = Number(r.net_units || 0);
    bits.push(`picks ${r.wins}-${r.losses}${r.pushes ? `-${r.pushes}` : ""} (${u >= 0 ? "+" : MINUS}${Math.abs(u).toFixed(2)}u)`);
  }
  [["two", "two-leg parlays"], ["three", "three-leg parlays"], ["scorers", pair]].forEach(([k, w]) => {
    const t = ((g[k] || {}).by_sport || {})[sport] || {};
    if (t.graded) bits.push(`${w} ${t.wins} of ${t.graded} hit`);
  });
  return bits.length ? `On the record so far: ${bits.join(" · ")}.` : "";
}

//: A game's parlays, both sizes: its two-leg tickets (engine/gameparlays.tickets_of, 2026-11-18) and its three-leg ones.
function rpParlays(tix) {
  return ((tix || {}).twos || []).length + ((tix || {}).threes || []).length;
}
//: Where a game stands: "live", "final", or "next" (not started yet).
function rpPhase(g) {
  const s = ((g || {}).live || {}).state;
  return s === "live" ? "live" : s === "final" ? "final" : "next";
}
//: How a finished game's picks and tickets went (app.js reportResults): {w, l, hit, tickets}, or null before its final.
/* A READ, NOT A BET (engine/gamereport.READ_ONLY, ZT; Ethan, 20 November 2026: "label the yardage
   picks"): a pick on a market we can rank but not price. Listed with its game's picks, said so, and left out
   of every count of picks and of a finished game's tally, as the record leaves it out (reportbets.journal). */
const RP_READ = "Read, not a bet: a market we can rank but not price yet";
const rpBetsOnly = (bets) => (bets || []).filter((b) => !(b && b.read_only));
function rpTally(g, bets, tix) {
  const R = g ? reportResults(g) : null;
  if (!R) return null;
  const st = rpBetsOnly(bets).map((b) => (R.grade(b) || {}).status);
  const tk = [...((tix || {}).twos || []), ...((tix || {}).threes || []), ...((tix || {}).scorers || [])]
    .map((t) => (R.ticket((t || {}).legs || []) || {}).status);
  return { w: st.filter((s) => s === "won").length, l: st.filter((s) => s === "lost").length,
           hit: tk.filter((s) => s === "won").length, tickets: tk.filter((s) => s === "won" || s === "lost").length };
}
function rpTallyWords(t) {
  if (!t) return "";
  return [t.w + t.l ? `picks ${t.w}-${t.l}` : "",
          t.tickets ? `${t.hit} of ${plural(t.tickets, "ticket")} hit` : ""].filter(Boolean).join(" · ");
}

/* ONE GAME, FOLDED TO ONE LINE (2026-11-16). Ethan: "organize the page better
   to make it easier to read and go through." The line says the game, when it
   is (or that it is on, or its final), what it carries, and once it is final
   how its picks and tickets went; the fold holds its picks, then its parlays
   and pairs, then the door to its report. A game saved for later (app.js
   spoiledG) says neither its score nor how it went. */
/* A GAME WHOSE PICKS POST LATER SAYS WHEN (step ABQ, 22 November 2026): a report's picks post with its parlays
   (engine/gamereport.picks_timeline, the same post time), so a game still before it has no pick yet, which is not
   "No single pick on this game clears our bars". The time in the reader's own zone, as every start on the site. */
function rpWaitWords(tix) {
  const t = Date.parse((tix || {}).post_at || "");
  if (!Number.isFinite(t) || t <= Date.now()) return "";
  let w = "";
  try { w = typeof bpNextWhen === "function" ? bpNextWhen(t) : (typeof tzTime === "function" ? tzTime(new Date(t)) : ""); }
  catch (e) { w = ""; }
  return `This game's picks post ${w ? `at ${w}` : "shortly before it starts"}, with its parlays, and never change after.`;
}

function rpGameHTML(d, key, bets, tix, open) {
  const g = rpGame(d, key);
  const [away, home] = key.split("@");
  const hidden = !!(g && typeof spoiledG === "function" && spoiledG(state.sport, g));
  const phase = rpPhase(g);
  const fin = phase === "final" && !hidden ? resFinal(g) : null;
  const when = !g ? "" : phase === "live" ? "On now"
    : phase === "final" ? (fin && fin.away != null
      ? `Final: ${teamName(away)} ${fin.away}, ${teamName(home)} ${fin.home}` : "Final")
    : whenLabel(g.date, g.kickoff);
  const pair = ["nfl", "cfb"].includes(state.sport) ? "touchdown" : state.sport === "nhl" ? "goal-scorer" : "scorer";
  const nBets = rpBetsOnly(bets).length, nReads = bets.length - nBets;
  const counts = [nBets ? plural(nBets, "pick") : "", nReads ? plural(nReads, "read") : "",
                  tix && rpParlays(tix) ? plural(rpParlays(tix), "parlay") : "",
                  tix && (tix.scorers || []).length ? plural(tix.scorers.length, `${pair} pair`) : ""].filter(Boolean);
  const tally = fin ? rpTallyWords(rpTally(g, bets, tix)) : "";
  const rows = bets.map((r) => {
    // The price grade where the league has one (engine/pricegrade): Green, Yellow or Red.
    const grade = r && r.price_grade && !r.read_only && r.price_grade.label ? r.price_grade : null;
    let row = deckPickRow(r, { door: likelyOpen(r),
      note: [r && r.read_only ? RP_READ : "", grade ? grade.label : "", rpSourceNote(r)].filter(Boolean).join(" · ") });
    // …in its own colour, with the grade said whole on a long press or a hover.
    if (grade) {
      row = row.replace(escapeHtml(grade.label), `<span class="rpk-grade ${escapeAttr(grade.grade || "")}" title="${
        escapeAttr(grade.words || "")}">${escapeHtml(grade.label)}</span>`);
    }
    // A read's chance is drawn muted, as a dropped pick's is: our number ranks it and can't price it.
    return r && r.read_only ? row.replace('class="hd-row', 'class="hd-row rpk-read') : row;
  }).join("");
  return `<details class="rpk-game" id="rpk-${escapeAttr(away)}-${escapeAttr(home)}"${open ? " open" : ""}>
    <summary class="rpk-head">
      <span class="rpk-title"><b>${escapeHtml(teamName(away))} at ${escapeHtml(teamName(home))}</b>${
        // Ethan's featured games (engine/featured: the Lions, a Thursday or a Monday night; college's Thursday
        // nights since step AAW), as on their cards.
        g && (g.featured || []).length ? ` <span class="rpk-fx-tag">Featured</span>` : ""}
        <span>${escapeHtml([when, counts.join(" · ")].filter(Boolean).join(" · "))}</span>${
        tally ? `<span class="rpk-tally">${escapeHtml(tally)}</span>` : ""}</span>
      <span class="row-fold-chev" aria-hidden="true"></span>
    </summary>
    <div class="rpk-body">
      <h4 class="rpk-sub">Picks</h4>
      ${rows ? `<div class="hd-card tn-rows">${rows}</div>` : `<p class="set-note">${escapeHtml(rpWaitWords(tix)
        || "No single pick on this game clears our bars.")}</p>`}
      ${tix ? `<h4 class="rpk-sub">${(tix.scorers || []).length ? "Parlays and pairs" : "Parlays"}</h4><div class="rpk-tix" data-rpk-tix="${escapeAttr(key)}"></div>` : ""}
      ${g ? `<button type="button" class="btn ghost rpk-open" data-gid="${escapeAttr(gameId(g))}">Open the report</button>` : ""}
    </div>
  </details>`;
}

/* THE LIKELIEST TICKETS TODAY (ZM, 20 November 2026). Ethan: "make better picks and make better
   selections with the information we're given". A night posts a game's two- and three-leg parlays by
   the dozen, a fold a game, and the record says the likeliest of them hit most: the two-leg tickets
   are 26 of 36 in hockey and basketball. Above the games, each game still to play offers its likeliest
   ticket by our numbers, and the three likeliest of those are a line each: the game and how many legs,
   the legs in words, our chance and the price to take it at. A line is a door to its game, where the
   ticket is drawn in full (said once). Scorer pairs are long by design, and a ticket our own card says
   to pass on (`playable` false: no book likely pays enough for it) is not offered, nor is one with a leg
   whose number no book lists any more (`one_book.gone`, engine/gameparlays: it cannot be placed as
   written). Fewer than two games to choose from is no ranking, and draws nothing. */
const RP_TOP_MAX = 3;
function rpTopTickets(d, byGame, keys) {
  const best = [];
  keys.forEach((k) => {
    const g = rpGame(d, k);
    const x = (byGame.get(k) || {}).tix;
    if (!g || !x || rpPhase(g) !== "next") return;
    const pick = [...(x.twos || []).map((t) => ["two", t]), ...(x.threes || []).map((t) => ["three", t])]
      .filter(([, t]) => t && (t.legs || []).length && Number(t.joint) > 0 && t.playable !== false
        && !(t.one_book || {}).gone)
      .sort((a, b) => Number(b[1].joint) - Number(a[1].joint))[0];
    if (pick) best.push({ key: k, kind: pick[0], t: pick[1] });
  });
  best.sort((a, b) => Number(b.t.joint) - Number(a.t.joint));
  return best.length >= 2 ? best.slice(0, RP_TOP_MAX) : [];
}
function rpTopHTML(items) {
  if (!items.length) return "";
  return `<section class="rpk-top" aria-label="The likeliest tickets today">
    <h4 class="rpk-top-h">The likeliest tickets today<span>by our numbers, one a game</span></h4>
    ${items.map(({ key, kind, t }) => {
      const [away, home] = key.split("@");
      const take = t.take_words ? ` · take it at ${escapeHtml(t.take_words)} or better` : "";
      return `<button type="button" class="rpk-top-row" data-rpk-jump="rpk-${escapeAttr(away)}-${escapeAttr(home)}">
        <span class="rpk-top-game">${escapeHtml(teamName(away))} at ${escapeHtml(teamName(home))} · ${
          kind === "two" ? "two legs" : "three legs"}</span>
        <span class="rpk-top-legs">${(t.legs || []).map(rpBetWords).join(" + ")}</span>
        <span class="rpk-top-p"><b>${Math.round(100 * Number(t.joint))}%</b> by our numbers${take}</span>
      </button>`;
    }).join("")}
  </section>`;
}

/* TODAY'S PICKS, the first tab: what the day carries and how its finished
   games went, the likeliest tickets still to play, a chip a game, then the
   games by where they stand (on now, still to play, finished), each folded
   to its line, the next one open. */
const RP_PHASES = [["live", "On now"], ["next", "Still to play"], ["final", "Finished"]];
function rpTodayHTML(d, byGame, keys) {
  const pair = ["nfl", "cfb"].includes(state.sport) ? "touchdown" : state.sport === "nhl" ? "goal-scorer" : "scorer";
  let picks = 0, threes = 0, pairs = 0;
  const done = { w: 0, l: 0, hit: 0, tickets: 0 };
  keys.forEach((k) => {
    const x = byGame.get(k);
    picks += rpBetsOnly(x.bets).length;
    threes += rpParlays(x.tix);
    pairs += ((x.tix || {}).scorers || []).length;
    const g = rpGame(d, k);
    if (rpPhase(g) !== "final" || (typeof spoiledG === "function" && spoiledG(state.sport, g))) return;
    const t = rpTally(g, x.bets, x.tix);
    if (t) Object.keys(done).forEach((f) => { done[f] += t[f]; });
  });
  const carries = [plural(keys.length, "game"), picks ? plural(picks, "pick") : "", threes ? plural(threes, "parlay") : "",
                   pairs ? plural(pairs, `${pair} pair`) : ""].filter(Boolean).join(" · ");
  const sofar = rpTallyWords(done);
  const jump = keys.length > 1 ? `<div class="std-chips likely-jump rpk-jump">${keys.map((k) => {
    const [away, home] = k.split("@");
    return `<button class="al-cat" type="button" data-rpk-jump="rpk-${escapeAttr(away)}-${escapeAttr(home)}">${
      escapeHtml(away)} @ ${escapeHtml(home)}</button>`;
  }).join("")}</div>` : "";
  let opened = false;
  const groups = RP_PHASES.map(([ph, title]) => {
    const ks = keys.filter((k) => rpPhase(rpGame(d, k)) === ph);
    if (!ks.length) return "";
    return `<h3 class="rpk-group">${escapeHtml(title)} <span>${ks.length}</span></h3>${ks.map((k) => {
      const open = !opened && ph !== "final";
      if (open) opened = true;
      return rpGameHTML(d, k, byGame.get(k).bets, byGame.get(k).tix, open);
    }).join("")}`;
  }).join("");
  return `<div class="rpk-summary"><b>${escapeHtml(carries)}</b>${
      sofar ? `<span>Finished so far: ${escapeHtml(sofar)}</span>` : ""}
      <button type="button" class="rpk-rec" data-rpk-rec="1" data-rpk-tab="record"></button></div>
    ${rpTopHTML(rpTopTickets(d, byGame, keys))}${jump}${groups}`;
}

/* HOW OUR REPORTS DID (engine/reportrecord, 2026-11-16). Ethan: "think about
   what users would want to see after the game's over ... if the data we were
   giving them were correct or not, and the read we had was correct or not ...
   we need to fact check ourselves after the game's over and see if we were
   correct or not." Every finished game's report is graded on its box score and
   kept; /api/report_record sends the counts (free, as the Record is): the totals
   first, then every finished game, newest first, each with its picks and
   parlays marked won or lost (/api/report_tickets, below) and opening its own
   graded report (/api/report_archive, members). */
const RP_FACTS = new Map();
//: "34 of 52 (65%)" — a count of right with its share.
function rpShare(pair) {
  const [a, n] = pair || [0, 0];
  return n ? `${a} of ${n} (${Math.round((100 * a) / n)}%)` : "";
}
//: How each kind of read is said, in the order the reports' summary says them (engine/reportgrade.GROUPS).
const RP_KINDS = [["matchups", "Matchup reads"], ["candidates", "Breakout candidates"], ["fades", "Fades"],
  ["starters", "Starters"], ["angles", "The angles"], ["units", "Offense against defense"],
  ["script", "How the game would go"]];
//: [right, of] for the players a report listed: the record's pair less the regulars who sat off it.
function rpListed(x) {
  const inj = (x || {}).injuries;
  return inj ? [inj[0], Math.max(0, inj[1] - ((x || {}).missed || 0))] : [0, 0];
}
function rpTotalsHTML(t) {
  if (!t || !t.games) return `<p class="set-note">No finished game graded in this stretch.</p>`;
  const tile = (k, pair, sub) => pair && pair[1] ? `<div class="rpk-fact-tile"><span class="rpk-fact-k">${escapeHtml(k)}</span>
      <b class="rpk-fact-v">${Math.round((100 * pair[0]) / pair[1])}%</b><span class="rpk-fact-sub">${escapeHtml(sub || `${pair[0]} of ${pair[1]}`)}</span></div>` : "";
  const td = t.tds && t.tds[1] ? `<div class="rpk-fact-tile"><span class="rpk-fact-k">Touchdown chances</span>
      <b class="rpk-fact-v">${t.tds[0]} scored</b><span class="rpk-fact-sub">${escapeHtml(`of ${t.tds[1]}; our chances said ${Number(t.tds[2]).toFixed(1)}`)}</span></div>` : "";
  const kinds = RP_KINDS.map(([k, w]) => (t.groups || {})[k] && t.groups[k][1]
    ? `<li><b>${escapeHtml(w)}:</b> ${escapeHtml(rpShare(t.groups[k]))} right</li>` : "").join("");
  /* The players it listed, apart from the regulars it missed (engine/reportrecord.track_lines): a miss sits in
     the record's second number, and college basketball — whose feed lists almost no one — read "0% · 0 of 5
     right" for five misses and nobody listed. */
  const missedN = t.missed || 0;
  const listed = rpListed(t);
  const missed = missedN ? `; ${plural(missedN, "regular")} sat without being on it` : "";
  const inj = listed[1] ? tile("The injury report", listed, `${listed[0]} of ${listed[1]} right${missed}`)
    : missedN ? `<div class="rpk-fact-tile"><span class="rpk-fact-k">The injury report</span>
      <b class="rpk-fact-v">${missedN} missed</b><span class="rpk-fact-sub">${escapeHtml(
        `${plural(missedN, "regular")} sat without being on it`)}</span></div>` : "";
  return `<div class="rpk-fact-tiles">
      ${tile("Who we think wins", t.call)}${tile("The reads", t.reads)}${tile("Our ratings alone", t.ratings)}
      ${tile("Our simulation", t.sim)}${inj}${td}</div>
    ${kinds ? `<ul class="rpk-fact-kinds">${kinds}</ul>` : ""}
    ${rpCalibHTML(t.calibration)}
    <p class="mini rpk-fact-span">${escapeHtml(plural(t.games, "finished game"))}${t.since ? escapeHtml(`, ${formatGameDate(t.since)}`
      + (t.through && t.through !== t.since ? ` to ${formatGameDate(t.through)}` : "")) : ""}.</p>`;
}
/* HOW SURE WE WERE, AND HOW OFTEN IT HELD (engine/reportrecord.BANDS): each
   tenth of a chance, how often the side we gave it won — the call's chance and
   our ratings' own. A side given 70% should win about seven in ten. */
function rpCalibHTML(c) {
  const call = (c || {}).call || {}, rat = (c || {}).ratings || {};
  const n = (x) => (x || [0, 0])[1];
  const bands = ["50", "60", "70", "80", "90"].filter((b) => n(call[b]) || n(rat[b]));
  if (!bands.length) return "";
  const cell = (x) => (n(x) ? `${x[0]} of ${x[1]} (${Math.round((100 * x[0]) / x[1])}%)` : "—");
  const withRat = bands.some((b) => n(rat[b]));
  return `<div class="rpk-fact-calib"><h4 class="rpk-fact-h">How sure we were, and how often it held</h4>
    <table class="agate rpk-fact-table"><thead><tr><th>We gave it</th><th class="num">Who we think wins</th>${
      withRat ? `<th class="num">Our ratings alone</th>` : ""}</tr></thead>
    <tbody>${bands.map((b) => `<tr><td>${b}–${Number(b) + 10}%</td><td class="num">${cell(call[b])}</td>${
      withRat ? `<td class="num">${cell(rat[b])}</td>` : ""}</tr>`).join("")}</tbody></table>
    <p class="mini rpk-fact-span">A side we gave 70% should win about seven times in ten. Each row is the games
      where the side we picked had that chance, and how many of them it won.</p></div>`;
}
//: One finished game: the final, then its checks as chips, then a door to its report.
function rpFactRowHTML(r) {
  // A name the row carries, unless it is the code itself (a report that named no side): then the page's own.
  const nm = (t) => { const n = (r.names || {})[t]; return n && n !== t ? n : teamName(t); };
  const f = r.final || {};
  const score = f.home != null && f.away != null ? `${nm(r.away)} ${f.away} at ${nm(r.home)} ${f.home}` : `${nm(r.away)} at ${nm(r.home)}`;
  const chip = (ok, words) => `<span class="${ok === true ? "rpk-fact-chip won" : ok === false ? "rpk-fact-chip lost" : "rpk-fact-chip"}">${escapeHtml(words)}</span>`;
  const chips = [];
  if (r.call) chips.push(chip(!!r.call.right, `Call ${r.call.right ? "right" : "wrong"}: ${nm(r.call.team)}`));
  if (r.reads && r.reads[1]) chips.push(chip(r.reads[0] * 2 >= r.reads[1], `Reads ${r.reads[0]} of ${r.reads[1]}`));
  if (r.ratings) chips.push(chip(r.ratings === "right", `Ratings ${r.ratings}`));
  if (r.sim) chips.push(chip(r.sim === "right", `Simulation ${r.sim}${r.script ? ` · Script ${r.script}` : ""}`));
  const listed = rpListed(r);
  if (listed[1]) chips.push(chip(listed[0] === listed[1], `Injury report ${listed[0]} of ${listed[1]}`));
  if (r.missed) chips.push(chip(false, `${plural(r.missed, "regular")} sat off the report`));
  if (r.tds && r.tds[1]) chips.push(chip(null, `TD chances ${r.tds[0]} of ${r.tds[1]} scored`));
  const ln = r.lines || {};
  const lines = [ln.cover ? `${nm(ln.cover)} covered` : ln.cover === "" ? "spread pushed" : "",
    ln.side ? (ln.side === "push" ? "total pushed" : `${ln.side} the total`) : ""].filter(Boolean).join(", ");
  if (lines) chips.push(chip(null, lines));
  const key = [r.date, r.away, r.home].join("|");
  return `<div class="rpk-fact-row">
    <div class="rpk-fact-game"><b>${escapeHtml(score)}</b><span>${escapeHtml(formatGameDate(r.date))}</span></div>
    <div class="rpk-fact-chips">${chips.join("")}</div>
    <div class="rpk-fact-bets" data-rpk-bets="${escapeAttr(key)}"></div>
    <button type="button" class="btn ghost rpk-fact-open" data-rpk-arch="${escapeAttr(key)}">Read the report</button>
    <div class="rpk-fact-report" data-rpk-arch-slot="${escapeAttr(key)}"></div>
  </div>`;
}
/* ETHAN'S FEATURED GAMES, APART (engine/featured, FEATURED1, 2026-11-19). Ethan: "the main game reports that I
   want to focus on is any game reports that has to do with a Lions game, any game reports on a Thursday night, or
   any game reports on a Monday night. Those are the three main ones that we need to have dialed in completely and
   have a separate record for." Their own record, every featured game and each kind, then each game: the report's
   picks at one unit a pick at the price posted, the parlays its report carried at kickoff, and who we said would
   win. The list below can show only these games, each pick and parlay with its check or X. */
const RP_FX_TICKETS = [["threes", "Three-leg parlays"], ["twos", "Two-leg parlays"], ["scorers", "Touchdown pairs"]];
function rpFxSigned(u) {
  const n = Number(u) || 0;
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}`;
}
//: One line of a featured block or game: "Picks 9-6 · +1.8 units · Three-leg parlays 1 of 4 · Who wins 2 of 3".
//: ``pairs``: the league's own word for its scorer pairs (the featured games are the NFL's: touchdown pairs).
function rpFxLine(b, pairs) {
  const parts = [];
  const [w, l, p] = b.picks || [0, 0, 0];
  if (w + l) {
    const tone = b.units > 0 ? "won" : b.units < 0 ? "lost" : "";
    parts.push(`Picks <b>${w}-${l}${p ? `-${p}` : ""}</b> <span class="rpk-fx-u ${tone}">${rpFxSigned(b.units)} units</span>`);
  }
  RP_FX_TICKETS.forEach(([k, word]) => {
    const t = (b.tickets || {})[k];
    if (t && t[0] + t[1]) parts.push(`${k === "scorers" && pairs ? pairs : word} <b>${t[0]} of ${t[0] + t[1]}</b>`);
  });
  const c = b.call || [0, 0];
  if (c[1]) parts.push(`Who wins <b>${c[0]} of ${c[1]}</b>`);
  const open = (b.open || 0) + (b.tickets_open || 0);
  if (open) parts.push(escapeHtml(`${open} still waiting on the box score`));
  return parts.length ? parts.join(" · ") : "Nothing of its report was on the record.";
}
/* Which games a league features, in its own words: the NFL's "Lions games, Thursday nights and Monday nights",
   college's "Thursday nights" (engine/featured.SPORT_TAGS, step AAW). */
function rpFxKinds(fx) {
  const plurals = (fx && fx.plural) || {};
  const ks = ((fx && fx.order) || []).map((k) => plurals[k] || k);
  return ks.length > 1 ? `${ks.slice(0, -1).join(", ")} and ${ks[ks.length - 1]}` : ks[0] || "";
}
function rpFeaturedHTML(fx) {
  if (!fx || !fx.all || !fx.all.games) return "";
  const words = fx.words || {}, plurals = fx.plural || {};
  const kinds = (fx.order || []).filter((k) => (fx.kinds || {})[k]);
  const kind = (title, b) => `<div class="rpk-fx-kind"><h5>${escapeHtml(title)}<span>${escapeHtml(plural(b.games, "game"))}</span></h5>
      <p>${rpFxLine(b)}</p></div>`;
  const games = (fx.games || []).map((g) => {
    const nm = (t) => { const n = (g.names || {})[t]; return n && n !== t ? n : teamName(t); };
    const f = g.final || {};
    const score = f.home != null && f.away != null ? `${nm(g.away)} ${f.away} at ${nm(g.home)} ${f.home}`
      : `${nm(g.away)} at ${nm(g.home)}`;
    const tags = (g.kinds || []).map((k) => `<span class="rpk-fx-tag">${escapeHtml(words[k] || k)}</span>`).join("");
    const one = { picks: g.picks, units: g.units, tickets: g.tickets, open: g.open, tickets_open: g.tickets_open,
                  call: g.call ? [g.call.right ? 1 : 0, 1] : [0, 0] };
    return `<li class="rpk-fx-game"><div class="rpk-fact-game"><b>${escapeHtml(score)}</b><span>${
      escapeHtml(formatGameDate(g.date))}</span></div><div class="rpk-fx-tags">${tags}</div><p>${rpFxLine(one)}</p></li>`;
  }).join("");
  return `<section class="rpk-fx" data-rpk-fx>
    <h4 class="rpk-fact-h"><span class="rpk-fx-star" aria-hidden="true">★</span>Featured games: ${escapeHtml(rpFxKinds(fx))}</h4>
    <p class="mini rpk-fact-span">Kept apart from the rest: each finished featured game’s report picks, at one unit
      a pick at the price posted, the parlays its report carried at kickoff, and who we said would win.</p>
    <div class="rpk-fx-kinds">${kind("Every featured game", fx.all)}${kinds.map((k) => kind(plurals[k] || k, fx.kinds[k])).join("")}</div>
    <details class="rpk-fx-each"${(fx.games || []).length <= 6 ? " open" : ""}><summary>Each featured game</summary>
      <ul class="rpk-fx-games">${games}</ul></details>
  </section>`;
}

//: The league's report record (/api/report_record: free, as the Record is), read once and kept five minutes:
//: How our reports did and the last slate's line both draw from it.
function rpRecord(sport) {
  let rec = RP_FACTS.get(sport);
  if (!rec || Date.now() - rec.at > 5 * 60 * 1000) {
    rec = { at: Date.now(), body: fetch(`/api/report_record?league=${encodeURIComponent(sport)}`, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null) };
    RP_FACTS.set(sport, rec);
  }
  return rec.body;
}

/* THE LAST SLATE AT A GLANCE (engine/reportrecord.last_slate, LASTNIGHT1, 2026-11-19). Ethan asks most days whether
   the reports' picks hit and their parlays did not; the answer was two tabs and a scroll away, a game at a time. The
   newest day with a finished game, summed in one line above today's picks: the picks at one unit a pick, each kind
   of parlay as the Record counts it (the set each report carried at the start), and who we said would win. Free,
   as everything settled is. The line this device last saw is drawn at once and corrected when the record answers,
   so the page does not jump on a return visit. */
const RP_SLATE_KEY = "qb.rpkSlate";
function rpSlateSeen(sport, ls) {
  let kept = {};
  try { kept = JSON.parse(localStorage.getItem(RP_SLATE_KEY)) || {}; } catch (e) { kept = {}; }
  if (ls === undefined) return kept[sport] || null;
  if (JSON.stringify(kept[sport] || null) !== JSON.stringify(ls || null)) {
    if (ls) kept[sport] = ls; else delete kept[sport];
    try { localStorage.setItem(RP_SLATE_KEY, JSON.stringify(kept)); } catch (e) { /* drawn from the record next time */ }
  }
  return ls;
}
function rpSlateHTML(ls, sport) {
  if (!ls || !ls.games) return "";
  // The slate's day against the reader's own calendar: games that finished this evening are today's so far,
  // yesterday's are last night's, and an older slate is said by its day ("Sunday, Nov 22").
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const now = new Date(Date.now());
  const y = iso(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
  const when = ls.date === iso(now) ? "Today so far" : typeof recapDayLabel === "function" ? recapDayLabel(ls.date, y) : "Last slate";
  const day = /^(Today so far|Last night|Last slate)$/.test(when) ? when : `${when}, ${formatGameDate(ls.date).replace(/^\w+, /, "")}`;
  const pairs = ["nfl", "cfb"].includes(sport) ? "Touchdown pairs" : sport === "nhl" ? "Goal-scorer pairs" : "Scorer pairs";
  return `<section class="rpk-slate" aria-label="How the last slate’s reports did">
    <h4 class="rpk-slate-h">${escapeHtml(day)}<span>${escapeHtml(plural(ls.games, "game"))}</span></h4>
    <p class="rpk-slate-line">${rpFxLine(ls, pairs)}</p>
    <button class="rpk-slate-go" type="button" data-rpk-slate-go>Each game, pick by pick ${icon("chev", 12)}</button>
  </section>`;
}
async function rpSlateFill(host, sport) {
  const slot = host.querySelector("[data-rpk-slate]");
  if (!slot) return;
  // Drawn again only when the line changed (the kept one, then the record's), and its door bound with it.
  let drawn = null;
  const draw = (ls) => {
    const html = rpSlateHTML(ls, sport);
    if (html === drawn) return;
    slot.innerHTML = drawn = html;
    const go = slot.querySelector("[data-rpk-slate-go]");
    if (go) go.addEventListener("click", () => {
      const tab = host.querySelector('.subnav-btn[data-subtab="facts"]');
      if (tab) tab.click();
    });
  };
  draw(rpSlateSeen(sport));
  const b = await rpRecord(sport);
  if (!slot.isConnected || state.sport !== sport || !b) return;
  draw(rpSlateSeen(sport, b.last_slate || null));
}

async function rpFactsFill(host, league) {
  const slot = host.querySelector("[data-rpk-facts]");
  if (!slot) return;
  const sport = league || state.sport;
  const b = await rpRecord(sport);
  if (!slot.isConnected || (!league && state.sport !== sport)) return;
  if (!b || !(b.games || []).length) {
    slot.querySelector("[data-rpk-facts-body]").innerHTML = `<p class="set-note">No finished game of this league has been
      graded yet. Each one is checked here once its box score is in: the call, every read, the lines, the injury
      report.</p>`;
    return;
  }
  const body = slot.querySelector("[data-rpk-facts-body]");
  const recentN = (b.recent || {}).games || 0;
  // Every game and the last month, as two chips, once the archive runs past a month.
  const split = recentN && recentN < (b.totals || {}).games;
  const every = b.games || [];
  // The rows the list draws: every game, or the featured games alone (the chip below).
  let games = every;
  // The featured games' keys, for the list's own chip (FEATURED1).
  const fx = b.featured && b.featured.all && b.featured.all.games ? b.featured : null;
  const fxKeys = new Set(((fx || {}).games || []).map((g) => [g.date, g.away, g.home].join("|")));
  body.innerHTML = `${split ? `<div class="std-chips rpk-fact-span-chips">
      <button class="al-cat on" type="button" data-rpk-span="all">Every game</button>
      <button class="al-cat" type="button" data-rpk-span="recent">Last ${b.recent_days} days</button></div>` : ""}
    <div data-rpk-totals>${rpTotalsHTML(b.totals)}</div>
    ${rpFeaturedHTML(fx)}
    <h4 class="rpk-fact-h">Every finished game</h4>
    ${fxKeys.size ? `<div class="std-chips rpk-fact-span-chips">
      <button class="al-cat on" type="button" data-rpk-list="all">Every game</button>
      <button class="al-cat" type="button" data-rpk-list="featured">Featured games</button></div>` : ""}
    <p class="mini rpk-fact-span">Each game’s picks and parlays, ${RP_MARK_WORDS}: a parlay’s mark is the whole ticket,
      and its legs carry their own.</p>
    <div class="rpk-fact-list"></div>
    <button type="button" class="btn ghost rpk-fact-more" data-rpk-more hidden></button>
    ${b.more ? `<p class="mini">${escapeHtml(plural(b.more, "older game"))} not shown.</p>` : ""}`;
  body.querySelectorAll("[data-rpk-span]").forEach((btn) => btn.addEventListener("click", () => {
    body.querySelectorAll("[data-rpk-span]").forEach((x) => x.classList.toggle("on", x === btn));
    body.querySelector("[data-rpk-totals]").innerHTML = rpTotalsHTML(btn.dataset.rpkSpan === "recent" ? b.recent : b.totals);
  }));
  // One listener on the list for every row's report, the rows drawn later too.
  const list = body.querySelector(".rpk-fact-list");
  list.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("[data-rpk-arch]");
    if (btn && list.contains(btn)) rpArchiveOpen(body, btn);
  });
  const more = body.querySelector("[data-rpk-more]");
  const page = () => {
    const from = list.children.length, rows = games.slice(from, from + RP_FACT_PAGE);
    list.insertAdjacentHTML("beforeend", rows.map(rpFactRowHTML).join(""));
    const left = games.length - list.children.length;
    more.hidden = left <= 0;
    more.textContent = `Show ${Math.min(left, RP_FACT_PAGE)} more ${left === 1 ? "game" : "games"}`;
    rpBetsFill(list, sport, rows, !from);
    revealChildren(list);
  };
  more.addEventListener("click", page);
  // Every game, or the featured games alone: the list starts again from its first page.
  body.querySelectorAll("[data-rpk-list]").forEach((btn) => btn.addEventListener("click", () => {
    body.querySelectorAll("[data-rpk-list]").forEach((x) => x.classList.toggle("on", x === btn));
    games = btn.dataset.rpkList === "featured" ? every.filter((r) => fxKeys.has([r.date, r.away, r.home].join("|"))) : every;
    list.innerHTML = "";
    page();
  }));
  page();
  revealChildren(slot);
  return games.length;
}

/* EVERY PICK AND PARLAY, A CHECK OR AN X (2026-11-17). Ethan, on this list:
   "I wanna be able too see each parlay and pick on this page along side and x
   or checkmark if the whole parlay hit and if the individual picks hit". Each
   finished game's report picks and its tickets come off the record
   (/api/report_tickets, engine/reportoutcome.for_games), asked for a page of
   rows at a time: under the game's checks, a strip of marks, one a pick and
   one a ticket, opening to every pick by name and every ticket with each of
   its legs, each with its mark and the number it finished with. What has
   settled is free, as the Record's rows are; a member also sees what is still
   waiting on the box score. */
//: The rows the list draws at a time, and the games one ask names (reportoutcome.MAX_GAMES).
const RP_FACT_PAGE = 20;
const RP_MARK_WORDS = "a check for each one that hit and an X for each one that missed";
const RP_BETS = new Map();
//: The reader's word for each market the answers named (engine/markets.label), before marketWord's own guess.
const RP_WORDS = {};
async function rpBetsFill(list, sport, rows, first) {
  const keys = (rows || []).map((r) => [r.date, r.away, r.home].join("|"));
  const need = keys.filter((k) => !RP_BETS.has(`${sport}|${k}`));
  if (need.length) {
    let body = null;
    try {
      const q = new URLSearchParams({ league: sport, games: need.join(",") });
      const r = await fetch(`/api/report_tickets?${q}`, { credentials: "same-origin" });
      body = r.ok ? await r.json() : null;
    } catch (e) { body = null; }
    // A game the record could not be asked about is asked again next time; one it holds nothing for is kept as such.
    if (body && body.games) need.forEach((k) => RP_BETS.set(`${sport}|${k}`, body.games[k] || null));
    if (body && body.words) Object.assign(RP_WORDS, body.words);
  }
  if (!list.isConnected) return;
  keys.forEach((k, i) => {
    const slot = [...list.querySelectorAll("[data-rpk-bets]")].find((x) => x.dataset.rpkBets === k);
    const x = RP_BETS.get(`${sport}|${k}`);
    if (slot && x) slot.innerHTML = rpBetsHTML(x, sport, first && i === 0);
  });
}
//: A verdict's mark and its tone: a check, an X, or a dash for a push, a void or one still waiting.
function rpMk(status) {
  const t = status === "won" ? "won" : status === "lost" ? "lost" : status === "push" || status === "void" ? "push" : "wait";
  return `<i class="rpk-mk ${t}" aria-hidden="true">${icon(t === "won" ? "check" : t === "lost" ? "cross" : "dash", 12)}</i>`;
}
//: "5 of 7 hit": the ones that hit of the ones won or lost.
function rpHit(list) {
  const won = list.filter((x) => x.status === "won").length, lost = list.filter((x) => x.status === "lost").length;
  return { won, n: won + lost, tone: !(won + lost) ? "" : won * 2 > won + lost ? "won" : won * 2 < won + lost ? "lost" : "" };
}
//: One pick or leg in plain words, as the game's page says it (js/detail.js gprPickWords; that room is the game page's).
const RP_SCORE = { anytime_td: "to score a touchdown", anytime_goal: "to score a goal", goals: "to score a goal",
                   first_td: "to score the first touchdown" };
function rpBetWords(p) {
  const m = String(p.market || "");
  const down = ["UNDER", "NO"].includes(String(p.side || "").toUpperCase());
  const num = (x) => { const v = Number(x); return Number.isInteger(v) ? String(v) : v.toFixed(1); };
  const club = escapeHtml(teamName(p.team || p.player || ""));
  if (p.game || RES_GAME_MARKETS.has(m)) {
    if (m === "moneyline") return `${club} to win`;
    if (m === "spread") {
      const ln = -Number(p.line);
      return Number.isFinite(ln) ? `${club} ${ln > 0 ? "+" : ln < 0 ? MINUS : ""}${num(Math.abs(ln))}` : `${club} spread`;
    }
    if (m === "total") return `${down ? "Under" : "Over"} ${num(p.line)} total`;
    if (m === "team_total") return `${club} ${down ? "under" : "over"} ${num(p.line)}`;
  }
  const who = escapeHtml(p.player || "");
  if (RP_SCORE[m]) return `${who} ${down ? "not " : ""}${RP_SCORE[m]}`;
  // The leg's own word first (a board's leg carries `market_label`, "3-Pointers Made"): the engine's words
  // (marketWord) arrive with the record, after the page's first draw, and before them a key read "fg3m".
  return `${who} ${down ? "under" : "over"}${p.line == null ? "" : ` ${num(p.line)}`} ${
    escapeHtml((p.market_label || RP_WORDS[m] || marketWord(m)).toLowerCase())}`;
}
function rpPickLI(p) {
  const st = String(p.status || ""), m = String(p.market || ""), a = Number(p.actual);
  const did = p.actual == null || !Number.isFinite(a) ? (st === "void" ? "didn’t play" : st === "push" ? "push"
      : st === "won" || st === "lost" ? "" : "waiting on the box score")
    : RP_SCORE[m] ? (a > 0 ? `scored${a > 1 ? ` ${a}` : ""}` : "didn’t score")
    : RES_GAME_MARKETS.has(m) ? "" : `had ${Number.isInteger(a) ? a : a.toFixed(1)}`;
  return `<li class="rpk-bet ${st === "won" ? "won" : st === "lost" ? "lost" : ""}">${rpMk(st)}<span>${rpBetWords(p)}${
    did ? ` <span class="rpk-bet-did">${escapeHtml(did)}</span>` : ""}</span></li>`;
}
//: A ticket's verdict in words: "Hit", "Missed by one leg", "Missed: 2 of 3 legs".
function rpTicketWords(t) {
  const legs = t.legs || [];
  const lost = legs.filter((l) => l.status === "lost").length;
  if (t.status === "won") return "Hit";
  if (t.status === "lost") return lost === 1 ? "Missed by one leg" : `Missed: ${plural(lost, "leg")} lost`;
  if (t.status === "push" || t.status === "void") return "Void";
  return "Waiting on the box score";
}
function rpTicketsHTML(list, kind, sport) {
  const name = kind === "threes" ? "Parlay" : kind === "twos" ? "Two-leg parlay" : ["nfl", "cfb"].includes(sport) ? "Touchdown pair"
    : sport === "nhl" ? "Goal-scorer pair" : "Scorer pair";
  return list.map((t, i) => `<li class="rpk-bet-tix ${t.status === "won" ? "won" : t.status === "lost" ? "lost" : ""}">
      <div class="rpk-bet-tix-h">${rpMk(t.status)}<b>${escapeHtml(`${name} ${i + 1}`)}</b> <span>${
        escapeHtml(rpTicketWords(t))}</span></div>
      <ul class="rpk-bet-legs">${(t.legs || []).map(rpPickLI).join("")}</ul></li>`).join("");
}
//: The marks a kind's strip draws before it counts the rest ("+24"): the list under it has every one.
const RP_STRIP_MAX = 12;
/* THE REPORT'S OWN TICKETS (engine/reportoutcome._own_tickets): the set the
   report carried at the start, the one set a game the Record counts
   (parlayledger.mark_at_start), and nothing else. Ethan, 20 November, on rows
   reading "Parlays 0 of 28": "There should only be 3 parlays made per game".
   The versions the board posted and replaced before the start are not listed or
   counted, and a game whose set was never kept (before 16 November) lists none
   and says why ("unkept"). A size the league had on paper at the start was
   never posted (GPWIN2): its tickets stand apart, said so, and a game with none
   says why it posted none. */
//: A size of ticket on paper (the holds of 17-20 November, since retired): its words and the rate it needed.
const RP_PAPER = { threes: ["three-leg parlays", "25%"], twos: ["two-leg parlays", "36%"] };
//: The game's picks and tickets: a strip of marks a kind, opening to every one by name.
function rpBetsHTML(x, sport, open) {
  const picks = x.picks || [], twos = x.twos || [], threes = x.threes || [], pairs = x.scorers || [];
  const paper = x.paper || {}, pTwos = paper.twos || [], pThrees = paper.threes || [];
  const pairWord = ["nfl", "cfb"].includes(sport) ? "Touchdown pairs" : sport === "nhl" ? "Goal-scorer pairs" : "Scorer pairs";
  // The three-leg tickets, the two-leg ones, then the scorer pairs.
  const parts = [["Picks", picks], [twos.length ? "Three-leg parlays" : "Parlays", threes], ["Two-leg parlays", twos],
                 ["Three-leg on paper", pThrees], ["Two-leg on paper", pTwos],
                 [pairWord, pairs]].filter(([, l]) => l.length);
  // A size on paper at the start, said once: its tickets were never posted, or there were none.
  const paperNote = (x.on_paper || []).map((k) => {
    const [w, bar] = RP_PAPER[k] || [];
    if (!w) return "";
    const had = (paper[k] || []).length;
    return `<p class="mini rpk-bets-note">${had ? `These ${w} were on paper, never posted`
      : `No ${w} were posted for this game`}: the league’s were on paper at the start, built and graded only to
      learn from while they hit under ${bar}.</p>`;
  }).join("");
  const held = x.held ? `<p class="mini rpk-bets-held">${escapeHtml(plural(x.held, "more pick or ticket", "more picks and tickets"))
    } waiting on the box score: members see ${x.held === 1 ? "it" : "them"} now.</p>` : "";
  // One short line: on a week of old games it is read once a row.
  const unkept = x.unkept ? `<p class="mini rpk-bets-note">Parlays weren’t saved for games before 16 November.</p>` : "";
  if (!parts.length) return unkept + paperNote + held;
  const strip = parts.map(([w, l]) => {
    const h = rpHit(l);
    const more = l.length > RP_STRIP_MAX ? `<span class="rpk-marks-more">+${l.length - RP_STRIP_MAX}</span>` : "";
    return `<span class="rpk-bets-part"><span class="rpk-bets-k">${escapeHtml(w)}</span>${
      h.n ? ` <b class="${h.tone}">${h.won} of ${h.n}</b>` : ""} <span class="rpk-marks">${
      l.slice(0, RP_STRIP_MAX).map((y) => rpMk(y.status)).join("")}${more}</span></span>`;
  }).join("");
  const sec = (title, inner) => `<h5 class="rpk-bets-h">${escapeHtml(title)}</h5><ul class="rpk-bet-list">${inner}</ul>`;
  return `<details class="rpk-bets"${open ? " open" : ""}>
      <summary class="rpk-bets-sum">${strip}<span class="row-fold-chev" aria-hidden="true"></span></summary>
      <div class="rpk-bets-body">
        ${picks.length ? sec("The picks", picks.map(rpPickLI).join("")) : ""}
        ${unkept}
        ${threes.length ? sec(twos.length ? "The three-leg parlays" : "The parlays", rpTicketsHTML(threes, "threes", sport)) : ""}
        ${twos.length ? sec("The two-leg parlays", rpTicketsHTML(twos, "twos", sport)) : ""}
        ${pThrees.length ? sec("The three-leg parlays on paper", rpTicketsHTML(pThrees, "threes", sport)) : ""}
        ${pTwos.length ? sec("The two-leg parlays on paper", rpTicketsHTML(pTwos, "twos", sport)) : ""}
        ${paperNote}
        ${pairs.length ? sec(`The ${pairWord.toLowerCase()}`, rpTicketsHTML(pairs, "scorers", sport)) : ""}
        ${rpEarlierHTML(x.earlier, sport, pairWord)}
      </div>
    </details>${held}`;
}
/* POSTED EARLIER, REPLACED BEFORE THE GAME (step ABB, 21 November 2026; engine/reportoutcome `earlier`).
   Ethan: "I put in a bet that is no longer being recorded or shown in the game reports". Until that night
   a game's parlays could change during its day and only the set at the start was listed; every version
   replaced before the start is listed here, each with its mark, apart from the game's own tallies. Since
   then a posted parlay never changes, so a newer game has none. */
function rpEarlierHTML(earlier, sport, pairWord) {
  const e = earlier || {};
  const parts = [["threes", "Three-leg parlays"], ["twos", "Two-leg parlays"], ["scorers", pairWord]]
    .filter(([k]) => (e[k] || []).length);
  if (!parts.length) return "";
  const n = parts.reduce((a, [k]) => a + e[k].length, 0);
  const h = rpHit(parts.flatMap(([k]) => e[k]));
  return `<details class="rpk-earlier"><summary class="rpk-earlier-sum">Posted earlier, replaced before the game · ${
      escapeHtml(plural(n, "parlay"))}${h.n ? ` · <b class="${h.tone}">${h.won} of ${h.n}</b> hit` : ""}</summary>
    <p class="mini rpk-bets-note">Until 21 November a game’s parlays could change during its day. These were posted for
      this game and replaced before it started; they aren’t in its counts above. Since then a posted parlay stays as it
      was posted.</p>
    ${parts.map(([k, w]) => `<h5 class="rpk-bets-h">${escapeHtml(w)} posted earlier</h5><ul class="rpk-bet-list">${
      rpTicketsHTML(e[k], k, sport)}</ul>`).join("")}
  </details>`;
}
//: A finished game's own report, graded, under its row (a member's; the rest are told what it holds).
async function rpArchiveOpen(body, btn) {
  const key = btn.dataset.rpkArch;
  const slot = [...body.querySelectorAll("[data-rpk-arch-slot]")].find((x) => x.dataset.rpkArchSlot === key);
  if (!slot) return;
  if (slot.innerHTML.trim()) { slot.innerHTML = ""; btn.textContent = "Read the report"; return; }
  const [date, away, home] = key.split("|");
  // The league the section draws (the Record page's scope, else the board's).
  const sec = btn.closest("[data-rpk-facts]");
  const league = (sec && sec.dataset.rpkSport) || state.sport;
  slot.innerHTML = `<p class="loading">Loading the report…</p>`;
  let doc = null;
  try {
    const q = new URLSearchParams({ league, date, away, home });
    const r = await fetch(`/api/report_archive?${q}`, { credentials: "same-origin" });
    doc = r.ok ? await r.json() : r.status === 402 ? { locked: true } : null;
  } catch (e) { doc = null; }
  if (!doc || doc.locked) {
    slot.innerHTML = doc && doc.locked
      ? `<div class="card ms-locked"><b>Our report on this game</b> — written before it and graded after it: every read
          right or wrong, every pick and parlay won or lost — is part of the subscription.</div>`
      : `<p class="set-note">This game’s report could not be found.</p>`;
    return;
  }
  const R = await loadReport();
  if (!R || !R.html || !doc.report) { slot.innerHTML = ""; return; }
  const fin = doc.final || {};
  const g = { home: doc.home, away: doc.away, date: doc.date, kickoff: doc.kickoff,
              live: { state: "final", home_score: fin.home, away_score: fin.away } };
  slot.innerHTML = R.html(doc.report, { embedded: true, sport: doc.sport, parlays: doc.parlays || null,
                                        results: reportResults(g, doc.results || {}) });
  btn.textContent = "Close the report";
  revealChildren(slot);
}
//: The section's frame, drawn with the page and filled once the record is read; ``league``
//: names the league it draws when that is not the board's (the Record page's scope).
function rpFactsHTML(league) {
  return `<section class="rpk-facts"${league ? "" : ` id="rpk-facts"`} data-rpk-facts="1"${
    league ? ` data-rpk-sport="${escapeAttr(league)}"` : ""}>
    <div class="section-title">How our reports did <span class="sub">— every finished game, fact-checked</span></div>
    <p class="set-note rpk-lead">After each game we check our own report against what happened: whether the call on who
      wins was right, every read against the box score, our ratings’ and the simulation’s picks, the lines, and the injury
      report. Every game is counted, the misses with the hits.</p>
    <div data-rpk-facts-body><p class="loading">Loading how our reports did…</p></div>
  </section>`;
}

/* THE PAGE IN THREE TABS (2026-11-16). Ethan: "On the report picks page, we
   should have a record page on there too to see if the parlays won and if the
   individual picks won from the game reports. Also organize the page better to
   make it easier to read and go through." Today's picks (rpTodayHTML); the
   Record, the same "The Game Report Picks and Parlays" the Record page draws,
   for this league (record.js renderReportBook), read the first time its tab
   opens; and How our reports did (rpFactsHTML), the same. The record and the
   checks are free, as the Record page is; today's picks are a member's. */
//: A tab's content drawn the first time the tab shows, by a tap or the arrow keys.
function rpOnShow(host, id, fill) {
  const panel = host.querySelector(`.subgroup[data-subgroup="${id}"]`);
  if (!panel) return;
  const go = () => {
    if (panel.hidden || panel.dataset.rpkDrawn) return;
    panel.dataset.rpkDrawn = "1";
    fill(panel);
  };
  host.querySelectorAll(".subnav-btn").forEach((b) => ["click", "keydown"].forEach((ev) =>
    b.addEventListener(ev, () => setTimeout(go, 0))));
  go();
}
async function renderReportPicks() {
  const host = document.getElementById("reportpicks-body");
  if (!host) return;
  const d = state.data;
  if (!d) return;
  // Opened from a finished game's Final card (js/detail.js): straight to how the reports did.
  if (window._rpWantFacts) _subtab.reportpicks = "facts";
  const locked = !!(d.locked && (d.locked.report_bets || d.locked.game_parlays));
  const byGame = new Map();
  const add = (key) => byGame.get(key) || byGame.set(key, { bets: [], tix: null }).get(key);
  (d.report_bets || []).forEach((r) => { if (r && r.game) add(r.game).bets.push(r); });
  ((d.game_parlays || {}).games || []).forEach((x) => {
    // A game whose parlays post later (engine/gameparlays.hold_until_post, step ABD) says when, under its picks.
    if (x && x.away && x.home && (rpParlays(x) || (x.scorers || []).length || x.post_note)) add(`${x.away}@${x.home}`).tix = x;
  });
  // The board's order (kickoff), then any game it no longer lists.
  const order = ((d.games || []).map((g) => `${g.away}@${g.home}`)).filter((k) => byGame.has(k));
  const keys = [...order, ...[...byGame.keys()].filter((k) => !order.includes(k))];
  const today = locked
    // The page's own title says what they are: the card says who they are for (18 November 2026).
    ? memberLockHTML("Today’s picks are for members", "Each one with its price and our chance, game by game. "
      + "How they have done is free, in the Record tab.")
    : !keys.length ? `<div class="empty-slate"><div class="es-icon">${icon("book", 30)}</div>
      <div class="es-title">No game reports on this board yet</div>
      <div class="es-sub">The reports are written with the board, one for every game on it, and their picks and
        parlays land here as they are.</div></div>`
    : rpTodayHTML(d, byGame, keys);
  // A league's three-leg parlays on paper (17-19 November, a hold since retired) say why once, here.
  const paper = locked ? "" : ["threes_paper", "twos_paper"].map((k) => ((d.game_parlays || {})[k] || {}).note || "")
    .filter(Boolean).map((n) => `<p class="set-note">${escapeHtml(n)}</p>`).join("");
  // The heading's own line says what the page is; each tab's line says the rest.
  /* THE RANKED PAGE, ONE TAP AWAY (Ethan, 21 November 2026: "I want the game report parlays too have its own
     page like the most likely picks where it ranks and lays out the parlays best to worst so people and go
     through the 2 leg and 3 leg parlays and see what's best"). It is Best Parlays (js/bestparlays.js), and this
     page, where he reads the reports' parlays game by game, never said so: its door is at the top of the day. */
  const bpDoor = `<button type="button" class="rpk-bp-go" data-rpk-bp>
      <span><b>Best Parlays</b> Every report parlay, two-leg and three-leg, ranked best to worst</span>${icon("chev", 14)}</button>`;
  host.innerHTML = `${paper}${subtabbedHTML("reportpicks", [
      ["today", "Today’s picks", "Every game’s picks, then its parlays and pairs", `${bpDoor}<div data-rpk-slate></div>${today}`],
      ["record", "Record", "Every report pick and parlay, won or lost", `<div class="rpk-book" data-rpk-book="1"></div>`],
      ["facts", "How our reports did", "Every finished game’s report, fact-checked", rpFactsHTML()]])}`;
  bindSubtabs(host);
  revealChildren(host);
  host.querySelectorAll("[data-rpk-bp]").forEach((b) => b.addEventListener("click", () => switchView("bestparlays", true)));
  rpOnShow(host, "record", (p) => renderReportBook(p.querySelector("[data-rpk-book]"), state.sport));
  rpOnShow(host, "facts", () => rpFactsFill(host));
  rpSlateFill(host, state.sport);
  rpFactsScroll(host);
  host.querySelectorAll("[data-rpk-jump]").forEach((b) => b.addEventListener("click", (e) => {
    const el = document.getElementById(b.dataset.rpkJump);
    if (!el) return;
    e.preventDefault();
    if (el.tagName === "DETAILS") el.open = true;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  host.querySelectorAll("[data-rpk-tab]").forEach((b) => b.addEventListener("click", () => {
    const tab = host.querySelector(`.subnav-btn[data-subtab="${b.dataset.rpkTab}"]`);
    if (tab) tab.click();
  }));
  if (locked || !keys.length) return;
  loadRecordOnce().then((rec) => {
    const el = host.querySelector("[data-rpk-rec]");
    const line = rpRecordLine(rec, state.sport);
    if (el && line) el.textContent = `${line} See the record ›`;
  });
  loadReport().then((R) => {
    if (!R || !R.gameTickets) return;
    host.querySelectorAll("[data-rpk-tix]").forEach((el) => {
      const x = byGame.get(el.dataset.rpkTix);
      if (!x || !x.tix) return;
      // A finished game's tickets say how they went (app.js reportResults).
      el.innerHTML = R.gameTickets(x.tix, state.sport, { results: () => reportResults(rpGame(d, el.dataset.rpkTix)) });
    });
    revealChildren(host);
  });
}
//: Opened from a finished game's Final card (js/detail.js): straight to how the reports did.
function rpFactsScroll(host) {
  if (!window._rpWantFacts) return;
  window._rpWantFacts = false;
  const el = host.querySelector("#rpk-facts");
  if (el) requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
}
/* THE SAME RECORD ON THE RECORD PAGE (js/record.js recFactsMount, 2026-11-16;
   Ethan said yes to putting it where anyone can see it): drawn into the slot
   the page leaves for it, for the league in its scope. The counts are free;
   a game's own report still opens for members only. */
//: Answers with how many finished games it listed (the Record page lists their receipts once, record.js recReceiptsOnce).
async function rpFactsInto(slot, league) {
  if (!slot || !league) return 0;
  slot.innerHTML = rpFactsHTML(league);
  return (await rpFactsFill(slot, league)) || 0;
}

