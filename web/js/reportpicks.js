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
function rpTally(g, bets, tix) {
  const R = g ? reportResults(g) : null;
  if (!R) return null;
  const st = (bets || []).map((b) => (R.grade(b) || {}).status);
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
  const counts = [bets.length ? plural(bets.length, "pick") : "",
                  tix && rpParlays(tix) ? plural(rpParlays(tix), "parlay") : "",
                  tix && (tix.scorers || []).length ? plural(tix.scorers.length, `${pair} pair`) : ""].filter(Boolean);
  const tally = fin ? rpTallyWords(rpTally(g, bets, tix)) : "";
  const rows = bets.map((r) => deckPickRow(r, { door: likelyOpen(r),
    note: (r.sources || []).map((s) => RP_SOURCE[s] || s).join(" · ") })).join("");
  return `<details class="rpk-game" id="rpk-${escapeAttr(away)}-${escapeAttr(home)}"${open ? " open" : ""}>
    <summary class="rpk-head">
      <span class="rpk-title"><b>${escapeHtml(teamName(away))} at ${escapeHtml(teamName(home))}</b>
        <span>${escapeHtml([when, counts.join(" · ")].filter(Boolean).join(" · "))}</span>${
        tally ? `<span class="rpk-tally">${escapeHtml(tally)}</span>` : ""}</span>
      <span class="row-fold-chev" aria-hidden="true"></span>
    </summary>
    <div class="rpk-body">
      <h4 class="rpk-sub">Picks</h4>
      ${rows ? `<div class="hd-card tn-rows">${rows}</div>` : `<p class="set-note">No single pick on this game clears our bars.</p>`}
      ${tix ? `<h4 class="rpk-sub">Parlays and pairs</h4><div class="rpk-tix" data-rpk-tix="${escapeAttr(key)}"></div>` : ""}
      ${g ? `<button type="button" class="btn ghost rpk-open" data-gid="${escapeAttr(gameId(g))}">Open the report</button>` : ""}
    </div>
  </details>`;
}

/* TODAY'S PICKS, the first tab: what the day carries and how its finished
   games went, a chip a game, then the games by where they stand (on now,
   still to play, finished), each folded to its line, the next one open. */
const RP_PHASES = [["live", "On now"], ["next", "Still to play"], ["final", "Finished"]];
function rpTodayHTML(d, byGame, keys) {
  const pair = ["nfl", "cfb"].includes(state.sport) ? "touchdown" : state.sport === "nhl" ? "goal-scorer" : "scorer";
  let picks = 0, threes = 0, pairs = 0;
  const done = { w: 0, l: 0, hit: 0, tickets: 0 };
  keys.forEach((k) => {
    const x = byGame.get(k);
    picks += x.bets.length;
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
    ${jump}${groups}`;
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
function rpTotalsHTML(t) {
  if (!t || !t.games) return `<p class="set-note">No finished game graded in this stretch.</p>`;
  const tile = (k, pair, sub) => pair && pair[1] ? `<div class="rpk-fact-tile"><span class="rpk-fact-k">${escapeHtml(k)}</span>
      <b class="rpk-fact-v">${Math.round((100 * pair[0]) / pair[1])}%</b><span class="rpk-fact-sub">${escapeHtml(sub || `${pair[0]} of ${pair[1]}`)}</span></div>` : "";
  const td = t.tds && t.tds[1] ? `<div class="rpk-fact-tile"><span class="rpk-fact-k">Touchdown chances</span>
      <b class="rpk-fact-v">${t.tds[0]} scored</b><span class="rpk-fact-sub">${escapeHtml(`of ${t.tds[1]}; our chances said ${Number(t.tds[2]).toFixed(1)}`)}</span></div>` : "";
  const kinds = RP_KINDS.map(([k, w]) => (t.groups || {})[k] && t.groups[k][1]
    ? `<li><b>${escapeHtml(w)}:</b> ${escapeHtml(rpShare(t.groups[k]))} right</li>` : "").join("");
  const missed = t.missed ? `; ${plural(t.missed, "regular")} sat without being on it` : "";
  return `<div class="rpk-fact-tiles">
      ${tile("Who we think wins", t.call)}${tile("The reads", t.reads)}${tile("Our ratings alone", t.ratings)}
      ${tile("Our simulation", t.sim)}${tile("The injury report", t.injuries,
        t.injuries && t.injuries[1] ? `${t.injuries[0]} of ${t.injuries[1]} right${missed}` : "")}${td}</div>
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
  if (r.injuries && r.injuries[1]) chips.push(chip(r.injuries[0] === r.injuries[1], `Injury report ${r.injuries[0]} of ${r.injuries[1]}`));
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
async function rpFactsFill(host, league) {
  const slot = host.querySelector("[data-rpk-facts]");
  if (!slot) return;
  const sport = league || state.sport;
  let rec = RP_FACTS.get(sport);
  if (!rec || Date.now() - rec.at > 5 * 60 * 1000) {
    try {
      const r = await fetch(`/api/report_record?league=${encodeURIComponent(sport)}`, { credentials: "same-origin" });
      rec = { at: Date.now(), body: r.ok ? await r.json() : null };
    } catch (e) { rec = { at: Date.now(), body: null }; }
    RP_FACTS.set(sport, rec);
  }
  if (!slot.isConnected || (!league && state.sport !== sport)) return;
  const b = rec.body;
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
  const games = b.games || [];
  body.innerHTML = `${split ? `<div class="std-chips rpk-fact-span-chips">
      <button class="al-cat on" type="button" data-rpk-span="all">Every game</button>
      <button class="al-cat" type="button" data-rpk-span="recent">Last ${b.recent_days} days</button></div>` : ""}
    <div data-rpk-totals>${rpTotalsHTML(b.totals)}</div>
    <h4 class="rpk-fact-h">Every finished game</h4>
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
  return `${who} ${down ? "under" : "over"}${p.line == null ? "" : ` ${num(p.line)}`} ${
    escapeHtml((RP_WORDS[m] || marketWord(m)).toLowerCase())}`;
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
/* THE REPORT'S OWN TICKETS (engine/reportoutcome._own_tickets). The board posts
   a game's parlays afresh as lines and news move, and the record grades every
   version; the list is the set the report carried at the start, and a line
   under it counts the earlier versions. A game kept before the start was (16
   November) lists every version the board posted, and says so. */
function rpEarlierHTML(x, kind, word) {
  const e = (x.earlier || {})[kind];
  if (e && e[1]) {
    return `<p class="mini rpk-bets-note">Before the start the board also posted ${escapeHtml(plural(e[1], `earlier version of its ${word}`,
      `earlier versions of its ${word}`))}; ${e[0]} of them hit. Every one counts on the Record.</p>`;
  }
  return x.versions ? `<p class="mini rpk-bets-note">Every version of this game’s ${escapeHtml(word)} the board posted before
    the start, as the record kept them: the report’s own set at the start was not yet kept on this date.</p>` : "";
}
//: The game's picks and tickets: a strip of marks a kind, opening to every one by name.
function rpBetsHTML(x, sport, open) {
  const picks = x.picks || [], twos = x.twos || [], threes = x.threes || [], pairs = x.scorers || [];
  const pairWord = ["nfl", "cfb"].includes(sport) ? "Touchdown pairs" : sport === "nhl" ? "Goal-scorer pairs" : "Scorer pairs";
  // The two sizes apart, the easier one first (two picks hit together far more often than three).
  const parts = [["Picks", picks], ["Two-leg parlays", twos], [twos.length ? "Three-leg parlays" : "Parlays", threes],
                 [pairWord, pairs]].filter(([, l]) => l.length);
  const held = x.held ? `<p class="mini rpk-bets-held">${escapeHtml(plural(x.held, "more pick or ticket", "more picks and tickets"))
    } waiting on the box score: members see ${x.held === 1 ? "it" : "them"} now.</p>` : "";
  if (!parts.length) return held;
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
        ${twos.length ? sec("The two-leg parlays", rpTicketsHTML(twos, "twos", sport))
          + rpEarlierHTML(x, "twos", "two-leg parlays") : ""}
        ${threes.length ? sec(twos.length ? "The three-leg parlays" : "The parlays", rpTicketsHTML(threes, "threes", sport))
          + rpEarlierHTML(x, "threes", "parlays") : ""}
        ${pairs.length ? sec(`The ${pairWord.toLowerCase()}`, rpTicketsHTML(pairs, "scorers", sport))
          + rpEarlierHTML(x, "scorers", pairWord.toLowerCase()) : ""}
      </div>
    </details>${held}`;
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
    if (x && x.away && x.home && (rpParlays(x) || (x.scorers || []).length)) add(`${x.away}@${x.home}`).tix = x;
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
  // A league's three-leg parlays on paper (engine/parlayhold) say why once, here.
  const paper = locked ? "" : ["threes_paper", "twos_paper"].map((k) => ((d.game_parlays || {})[k] || {}).note || "")
    .filter(Boolean).map((n) => `<p class="set-note">${escapeHtml(n)}</p>`).join("");
  // The heading's own line says what the page is; each tab's line says the rest.
  host.innerHTML = `${paper}${subtabbedHTML("reportpicks", [
      ["today", "Today’s picks", "Every game’s picks, then its parlays and pairs", today],
      ["record", "Record", "Every report pick and parlay, won or lost", `<div class="rpk-book" data-rpk-book="1"></div>`],
      ["facts", "How our reports did", "Every finished game’s report, fact-checked", rpFactsHTML()]])}`;
  bindSubtabs(host);
  revealChildren(host);
  rpOnShow(host, "record", (p) => renderReportBook(p.querySelector("[data-rpk-book]"), state.sport));
  rpOnShow(host, "facts", () => rpFactsFill(host));
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

