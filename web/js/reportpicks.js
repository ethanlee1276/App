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
  [["three", "three-leg parlays"], ["scorers", pair]].forEach(([k, w]) => {
    const t = ((g[k] || {}).by_sport || {})[sport] || {};
    if (t.graded) bits.push(`${w} ${t.wins} of ${t.graded} hit`);
  });
  return bits.length ? `On the record so far: ${bits.join(" · ")}.` : "";
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
  const tk = [...((tix || {}).threes || []), ...((tix || {}).scorers || [])]
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
                  tix && (tix.threes || []).length ? plural(tix.threes.length, "parlay") : "",
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
    threes += ((x.tix || {}).threes || []).length;
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
   first, then every finished game, newest first, each opening its own graded
   report (/api/report_archive, members). */
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
  const nm = (t) => (r.names || {})[t] || teamName(t);
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
  body.innerHTML = `${split ? `<div class="std-chips rpk-fact-span-chips">
      <button class="al-cat on" type="button" data-rpk-span="all">Every game</button>
      <button class="al-cat" type="button" data-rpk-span="recent">Last ${b.recent_days} days</button></div>` : ""}
    <div data-rpk-totals>${rpTotalsHTML(b.totals)}</div>
    <h4 class="rpk-fact-h">Every finished game</h4>
    <div class="rpk-fact-list">${(b.games || []).map(rpFactRowHTML).join("")}</div>
    ${b.more ? `<p class="mini">${escapeHtml(plural(b.more, "older game"))} not shown.</p>` : ""}`;
  body.querySelectorAll("[data-rpk-span]").forEach((btn) => btn.addEventListener("click", () => {
    body.querySelectorAll("[data-rpk-span]").forEach((x) => x.classList.toggle("on", x === btn));
    body.querySelector("[data-rpk-totals]").innerHTML = rpTotalsHTML(btn.dataset.rpkSpan === "recent" ? b.recent : b.totals);
  }));
  body.querySelectorAll("[data-rpk-arch]").forEach((btn) => btn.addEventListener("click", () => rpArchiveOpen(body, btn)));
  revealChildren(slot);
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
   for this league (record.js recReportBookInto), read the first time its tab
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
    if (x && x.away && x.home && ((x.threes || []).length || (x.scorers || []).length)) add(`${x.away}@${x.home}`).tix = x;
  });
  // The board's order (kickoff), then any game it no longer lists.
  const order = ((d.games || []).map((g) => `${g.away}@${g.home}`)).filter((k) => byGame.has(k));
  const keys = [...order, ...[...byGame.keys()].filter((k) => !order.includes(k))];
  const today = locked
    ? memberLockHTML("Report Picks", "Every bet and parlay our game reports posted, game by game, with the price and "
      + "our chance. How they have done is free, in the Record tab.")
    : !keys.length ? `<div class="empty-slate"><div class="es-icon">${icon("book", 30)}</div>
      <div class="es-title">No game reports on this board yet</div>
      <div class="es-sub">The reports are written with the board, one for every game on it, and their picks and
        parlays land here as they are.</div></div>`
    : rpTodayHTML(d, byGame, keys);
  host.innerHTML = `<p class="set-note rpk-lead">Every pick and parlay our game reports post, game by game, and how
      they have done.</p>${subtabbedHTML("reportpicks", [
      ["today", "Today’s picks", "Every game’s picks, then its parlays and pairs", today],
      ["record", "Record", "Every report pick and parlay, won or lost", `<div class="rpk-book" data-rpk-book="1"></div>`],
      ["facts", "How our reports did", "Every finished game’s report, fact-checked", rpFactsHTML()]])}`;
  bindSubtabs(host);
  revealChildren(host);
  rpOnShow(host, "record", (p) => recReportBookInto(p.querySelector("[data-rpk-book]"), state.sport));
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
async function rpFactsInto(slot, league) {
  if (!slot || !league) return;
  slot.innerHTML = rpFactsHTML(league);
  await rpFactsFill(slot, league);
}

