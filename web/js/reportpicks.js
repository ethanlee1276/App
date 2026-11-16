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
   on the Record page's Report section (record.js recReportSection). */

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

//: One game's section: its name and when, its picks, then a slot for its tickets.
function rpGameHTML(d, key, bets, tix) {
  const g = rpGame(d, key);
  const [away, home] = key.split("@");
  const when = g ? whenLabel(g.date, g.kickoff) : "";
  const pair = ["nfl", "cfb"].includes(state.sport) ? "touchdown" : state.sport === "nhl" ? "goal-scorer" : "scorer";
  const counts = [bets.length ? plural(bets.length, "pick") : "",
                  tix && (tix.threes || []).length ? plural(tix.threes.length, "parlay") : "",
                  tix && (tix.scorers || []).length ? plural(tix.scorers.length, `${pair} pair`) : ""].filter(Boolean);
  const rows = bets.map((r) => deckPickRow(r, { door: likelyOpen(r),
    note: (r.sources || []).map((s) => RP_SOURCE[s] || s).join(" · ") })).join("");
  return `<section class="rpk-game" id="rpk-${escapeAttr(away)}-${escapeAttr(home)}">
    <div class="rpk-head">
      <div class="rpk-title"><b>${escapeHtml(teamName(away))} at ${escapeHtml(teamName(home))}</b>
        <span>${escapeHtml([when, counts.join(" · ")].filter(Boolean).join(" · "))}</span></div>
      ${g ? `<button type="button" class="btn ghost rpk-open" data-gid="${escapeAttr(gameId(g))}">Open the report</button>` : ""}
    </div>
    ${rows ? `<div class="hd-card tn-rows">${rows}</div>` : `<p class="set-note">No single pick on this game clears our bars.</p>`}
    ${tix ? `<div class="rpk-tix" data-rpk-tix="${escapeAttr(key)}"></div>` : ""}
  </section>`;
}

async function renderReportPicks() {
  const host = document.getElementById("reportpicks-body");
  if (!host) return;
  const d = state.data;
  if (!d) return;
  if (d.locked && (d.locked.report_bets || d.locked.game_parlays)) {
    host.innerHTML = memberLockHTML("Report Picks",
      "Every bet and parlay our game reports posted, game by game, with the price and our chance, each graded on the Record page.");
    return;
  }
  const byGame = new Map();
  const add = (key) => byGame.get(key) || byGame.set(key, { bets: [], tix: null }).get(key);
  (d.report_bets || []).forEach((r) => { if (r && r.game) add(r.game).bets.push(r); });
  ((d.game_parlays || {}).games || []).forEach((x) => {
    if (x && x.away && x.home && ((x.threes || []).length || (x.scorers || []).length)) add(`${x.away}@${x.home}`).tix = x;
  });
  // The board's order (kickoff), then any game it no longer lists.
  const order = ((d.games || []).map((g) => `${g.away}@${g.home}`)).filter((k) => byGame.has(k));
  const keys = [...order, ...[...byGame.keys()].filter((k) => !order.includes(k))];
  if (!keys.length) {
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("book", 30)}</div>
      <div class="es-title">No game reports on this board yet</div>
      <div class="es-sub">The reports are written with the board, one for every game on it, and their picks and
        parlays land here as they are.</div></div>`;
    return;
  }
  const jump = keys.length > 1 ? `<div class="std-chips likely-jump rpk-jump">${keys.map((k) => {
    const [away, home] = k.split("@");
    return `<button class="al-cat" type="button" data-rpk-jump="rpk-${escapeAttr(away)}-${escapeAttr(home)}">${
      escapeHtml(away)} @ ${escapeHtml(home)}</button>`;
  }).join("")}</div>` : "";
  host.innerHTML = `<p class="set-note rpk-lead">Every pick our game reports posted (each report’s picks card, its
      matchup reads’ picks, its breakout candidates and fades), then the game’s parlays and pairs. Each one is graded on
      the <a href="#record">Record page</a> under Report bets.</p>
    <p class="mini rpk-rec" data-rpk-rec="1"></p>
    ${jump}
    ${keys.map((k) => rpGameHTML(d, k, byGame.get(k).bets, byGame.get(k).tix)).join("")}`;
  revealChildren(host);
  host.querySelectorAll("[data-rpk-jump]").forEach((b) => b.addEventListener("click", () => {
    const el = document.getElementById(b.dataset.rpkJump);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  loadRecordOnce().then((rec) => {
    const el = host.querySelector("[data-rpk-rec]");
    if (el) el.textContent = rpRecordLine(rec, state.sport);
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
