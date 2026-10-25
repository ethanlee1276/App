/* THE DETAIL PAGES — loaded the first time a game, a pick or a play-by-play page opens (app.js loadRoom,
   2026-10-24): a game's page and its written report, a pick's own page, and the play-by-play page.
   A classic script like app.js: it shares the page's globals, and each
   page's renderer here replaces app.js's stub of the same name. Every
   declaration was moved whole out of app.js, in order, with its own
   comments: nothing outside these pages calls any of it (chosen by
   TypeScript's own reading of the file, and checked by name against every
   other script and page). */
/* INACTIVES, 90 MINUTES BEFORE KICKOFF (every research write-up, 2026-10-07:
   "inactives come out about 6:45 PM ET — confirm Otton and Godwin are
   active"). The NFL posts them 90 minutes out; the game page says when,
   while the game is still ahead. The bare "HH:MM" kickoff is Eastern. */
function inactivesNote(g) {
  if (state.sport !== "nfl" || !g || !g.kickoff) return "";
  const st = String((g.live || {}).state || "scheduled");
  if (!["scheduled", "pre", "upcoming"].includes(st)) return "";
  const m = /^(\d{1,2}):(\d{2})/.exec(String(g.kickoff));
  if (!m) return "";
  let mins = (+m[1]) * 60 + (+m[2]) - 90;
  if (mins < 0) mins += 24 * 60;
  const h = Math.floor(mins / 60), mm = String(mins % 60).padStart(2, "0");
  const ap = h >= 12 ? "PM" : "AM";
  return ` · <span class="gp-inactives">inactives ${(h % 12) || 12}:${mm} ${ap} ET</span>`;
}

function pulledAgo(iso) {
  const t = Date.parse(iso || "");
  if (!isFinite(t)) return "";
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
}

function crowdLinesHTML(g, c) {
  const rows = [];
  const pct = pctPrice;
  // Polymarket's and, since 2026-09-27, Kalshi's (engine/crowd.kalshi_lines).
  for (const [cover, over, venue] of [["poly_home_cover", "poly_over", "Polymarket"],
                                      ["kalshi_home_cover", "kalshi_over", "Kalshi"]]) {
    if (c[cover] != null && c.spread_home_line != null) {
      const hl = Number(c.spread_home_line);
      const homeGives = hl < 0;
      const fav = homeGives ? g.home : g.away;
      const p = homeGives ? c[cover] : 1 - c[cover];
      rows.push(`<li><b>${escapeHtml(teamName(fav))} ${MINUS}${Math.abs(hl).toFixed(1)}</b> covers ${pct(p)}
        <span class="mini">on ${venue}</span></li>`);
    }
    if (c[over] != null && c.total_line != null) {
      rows.push(`<li><b>Over ${Number(c.total_line).toFixed(1)}</b> ${pct(c[over])}
        <span class="mini">on ${venue}</span></li>`);
    }
  }
  return rows.length ? `<ul class="gp-crowd-lines">${rows.join("")}</ul>` : "";
}

/* WHERE THE MONEY IS GOING (engine/moneysplit). Ethan, 2026-09-28, with
   DraftKings' "% of bets placed" bars beside our game page: show "what
   percent of money is on what team and on what spread and on what
   Moneyline." A book's split is its own customers' and has no free feed,
   so these are the prediction markets' — Kalshi's and Polymarket's public
   tapes, the side each trade's taker bought — and the section says so.
   Away on the left, as the sportsbooks draw it. */
function gameMoneyHTML(g) {
  const m = (g && g.money) || null;
  if (!m || !(m.ml || m.spread || m.total)) return "";
  const pct = (p) => `${Math.round(Number(p) * 100)}%`;
  const num = (x) => `${x > 0 ? "+" : x < 0 ? MINUS : ""}${Math.abs(Number(x)).toFixed(1)}`;
  const usd = (x) => `$${Math.round(Number(x) || 0).toLocaleString("en-US")}`;
  const row = (kind, l, lk, r, rk, s) => {
    const lp = Number(s[lk]), rp = Number(s[rk]);
    return `<div class="gp-money-row">
      <div class="gp-money-top"><span><b>${pct(lp)}</b> ${escapeHtml(l)}</span>
        <span class="gp-money-kind">${kind}</span>
        <span>${escapeHtml(r)} <b>${pct(rp)}</b></span></div>
      <div class="gp-money-bar" role="img" aria-label="${escapeAttr(`${kind}: ${pct(lp)} of the money on ${l}, ${pct(rp)} on ${r}`)}">
        <i class="l" style="width:${(lp * 100).toFixed(1)}%"></i><i class="r" style="width:${(rp * 100).toFixed(1)}%"></i></div>
      <div class="gp-money-sub"><span>${pct(s[`${lk}_bets`])} of trades</span>
        <span>${usd(s.usd)} on ${Number(s.n).toLocaleString("en-US")} trades</span>
        <span>${pct(s[`${rk}_bets`])} of trades</span></div>
    </div>`;
  };
  const rows = [];
  if (m.ml) rows.push(row("Moneyline", g.away, "away", g.home, "home", m.ml));
  if (m.spread && m.spread.line != null) {
    const hl = Number(m.spread.line);
    rows.push(row("Spread", `${g.away} ${num(-hl)}`, "away", `${g.home} ${num(hl)}`, "home", m.spread));
  }
  if (m.total && m.total.line != null) {
    const t = Number(m.total.line).toFixed(1);
    rows.push(row("Total", `Over ${t}`, "over", `Under ${t}`, "under", m.total));
  }
  const venues = (m.venues || []).join(" and ") || "the prediction markets";
  return `<div class="gp-money">
    <div class="gp-crowd-head">Where the money is going <span class="mini">% of money</span></div>
    ${rows.join("")}
    <p class="mini gp-money-note">Traders on ${escapeHtml(venues)}: the side each trade’s taker bought,
      over each market’s latest trades before kickoff${m.at ? ` · updated ${escapeHtml(m.at)}` : ""}.
      Exchange traders, not sportsbook customers.</p>
  </div>`;
}

function crowdStripHTML(g) {
  const c = (g && g.crowd) || null;
  if (!c) return "";
  const cells = [["kalshi", "Kalshi"], ["polymarket", "Polymarket"], ["books", "Books"]]
    .filter(([k]) => c[k] != null);
  const lines = crowdLinesHTML(g, c);
  if (!cells.some(([k]) => k === "kalshi" || k === "polymarket")) {
    return lines ? `<div class="gp-crowd"><div class="gp-crowd-head">The prediction markets on this line</div>${lines}</div>` : "";
  }
  const pct = pctPrice;
  // THE GAP, ALWAYS (V-9). It used to print only at 3 points or more, so
  // "the markets agree" and "we did not say" looked the same.
  const gap = c.gap_pts == null ? ""
    : Math.abs(c.gap_pts) < 0.5
    ? `<p class="mini gp-crowd-gap">The prediction markets and the books agree on this one (within half a point).</p>`
    : `<p class="mini gp-crowd-gap">The prediction markets rate ${escapeHtml(teamName(c.gap_pts > 0 ? g.home : g.away))}
        ${Math.abs(c.gap_pts).toFixed(1)} points higher than the books do.</p>`;
  const when = pulledAgo(c.at);
  return `<div class="gp-crowd"><div class="gp-crowd-head">Win chance, every market${
      when ? ` <span class="mini">· exchange prices pulled ${escapeHtml(when)}</span>` : ""}</div>
    <table class="gp-crowd-t"><thead><tr><th scope="col" aria-label="Team"></th>${
      cells.map(([, l]) => `<th scope="col">${l}</th>`).join("")}</tr></thead>
    <tbody>${[["away", (p) => 1 - p], ["home", (p) => p]].map(([side, f]) => `<tr><th scope="row">${
      escapeHtml(teamName(g[side]))}</th>${cells.map(([k]) => `<td>${pct(f(c[k]))}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>${gap}${lines}</div>`;
}
function obGameHTML(g) {
  const k = `${g.away}@${g.home}`;
  const rows = oneBoardAllRows().filter((r) => r.game === k);
  if (!rows.length) return "";
  return `<div id="gp-sec-matchup" class="matchup-picks one-board"><div class="section-title">Most likely · this game
      <span class="sub">— every pick in this game, with the four checks behind its tier</span></div>
    ${obTierSections(rows, { sort: false })}</div>`;
}
function gpMatchupHTML(g) {
  if (oneBoardOn()) return obGameHTML(g);
  const m = ((state.data || {}).matchup_picks || []).find((x) => x && x.away === g.away && x.home === g.home);
  if (!m || !((m.td || []).length || (m.props || []).length)) return "";
  return `<div id="gp-sec-matchup" class="matchup-picks"><div class="section-title">Matchup picks
      <span class="sub">— this game broken down offence against defence: its scorers, and the
      yards and catches for who could shine or struggle, where our number agrees</span></div>
    ${matchupGameHTML(m, { head: false })}</div>`;
}
function matchupPickCount(g) {
  if (oneBoardOn()) return oneBoardAllRows().filter((r) => r.game === `${g.away}@${g.home}`).length;
  const m = ((state.data || {}).matchup_picks || []).find((x) => x && x.away === g.away && x.home === g.home);
  return m ? (m.td || []).length + (m.props || []).length : 0;
}

/* The last N games, with the context the bar chart cannot draw. A bar
   says how big; this says who against, where, and in what weather —
   which is the difference between "he went under twice" and "he went
   under twice against the two best defenses he has seen". */
/* THE NUMBER WAS SHOPPED, and the page says so (2026-09-23, Ethan on
   Garrett Wilson UNDER 79.5 at −233 beside a defence ranked softest:
   "why is it offering an under prop"). An under takes the HIGHEST line
   any book posts (engine/odds.best_under_line — the cushion is what the
   −233 pays for), an over the lowest; the chart and the hit rate then
   read against that number. A reader comparing it with the defence needs
   the market's centre beside it. */
function shoppedLineNote(r) {
  const lines = ((r && r.all_lines) || []).map((l) => Number(l && l.line)).filter(Number.isFinite);
  const line = Number(r && r.line);
  if (lines.length < 2 || !Number.isFinite(line)) return "";
  const sorted = [...lines].sort((a, b) => a - b);
  const centre = sorted[Math.floor(sorted.length / 2)];
  const counting = Math.abs(centre) < 20;
  if (Math.abs(line - centre) < (counting ? 0.5 : 1)) return "";
  const over = String(r.side || "OVER").toUpperCase() === "OVER";
  const edge = over ? line <= sorted[0] : line >= sorted[sorted.length - 1];
  return `<p class="pp-shopped">Shopped number: this is the ${over ? "over" : "under"} at ${line}${
    edge ? `, the ${over ? "lowest" : "highest"} number any book posts` : ""} (${oddsTxt(r.odds)});
    the market’s centre is ${centre}. The chart and the hit rate below read against ${line}.</p>`;
}

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
    if (g.partial) extra.push(`left early${g.snaps != null ? ` · ${Math.round(g.snaps * 100)}% of snaps` : ""}`);
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
  /* ONE CHART, ONE CALL SITE. This page used to build its own
     prop-shaped row and pass its own options, and the two drifted: the
     fix that stopped the strip reading "SPREAD Spread" (2026-08-25)
     landed in `gameBetChart` and never reached here, and neither did
     `lineText` or `pill` — so the full page charted every spread with
     "LINE 0" and a baseline pill saying 0, while the card beside it on
     the board said "-3.5 COVERS" off the same series. Both surfaces
     draw through `gameBetChart` now; there is nothing left to drift. */
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
  /* A Most Likely game row (likely.from_game_bet, `kind: "game"`) is
     that board's pick: its chance, the book's number and the model's
     own rating head the page, not Model / Market / Edge — which for a
     row ranked on the market's number read 68.9% / 68.9% / +0.0%. */
  const likely = b.kind === "game";
  const likelyMetrics = `<div class="metrics">
        ${b.model_prob != null ? `<div class="metric primary"><div class="k">Chance</div>
          <div class="v pos">${wholePct(b.model_prob)}</div></div>` : ""}
        ${b.implied_prob != null ? `<div class="metric"><div class="k">Book implies</div>
          <div class="v">${wholePct(b.implied_prob)}</div></div>` : ""}
        ${b.win_prob != null ? `<div class="metric"><div class="k">Our model alone</div>
          <div class="v">${wholePct(b.win_prob)}</div></div>` : ""}
      </div>`;
  const edgeMetrics = `<div class="metrics">
        ${b.win_prob != null ? `<div class="metric"><div class="k">Model</div>
          <div class="v">${pct(b.win_prob)}</div></div>` : ""}
        ${b.fair_prob != null ? `<div class="metric"><div class="k">Market</div>
          <div class="v">${pct(b.fair_prob)}</div></div>` : ""}
        ${b.edge != null ? `<div class="metric primary"><div class="k">Edge</div>
          <div class="v ${b.edge >= 0 ? "pos" : "neg"}">${signedPct(b.edge)}</div></div>` : ""}
      </div>`;
  const warn = (b.warnings || []).filter((x) => !(likely && GAME_EDGE_ONLY.test(x))).slice(0, 4)
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  host.innerHTML = `
    <div class="pp-nav">
      <button class="btn-quiet gp-back" id="pp-back">${escapeHtml(detailBackLabel())}</button>
      <span class="pp-nav-right">
        ${b.odds != null ? `<button class="btn ghost"
          data-slip="${escapeAttr(gameBetId(b))}">${slipHas(b)
            ? "On slip" : "+ Parlay"}</button>` : ""}
        <button class="btn ghost qb-share" data-card="${escapeAttr(gameBetId(b))}"
          >Share card</button>
      </span>
    </div>
    <article class="card pp-card">
      <div class="card-head">
        <div class="card-id">${mark}
          <div>
            <div class="player">${escapeHtml(b.pick_label || b.headline || "")}
              <span class="ml-odds">${oddsTxt(b.odds)}</span></div>
            <div class="subtitle">${b.away && b.home
              ? `${teamLinkHTML(state.sport, b.away, b.away)} @ ${teamLinkHTML(state.sport, b.home, b.home)}`
              : escapeHtml(b.matchup || "")}</div>
            <div class="pick">${escapeHtml(b.market_label || b.market || "")}</div>
          </div>
        </div>
        ${b.grade ? `<span class="grade ${gradeClass(b.grade)}">${
          escapeHtml(b.grade)}</span>` : ""}
      </div>
      ${likely ? likelyMetrics : edgeMetrics}
      ${whyGameHTML(b, likely)}
      ${s ? gameBetChart(b) : `
      ${panelEmpty("No recent results for this team yet — the chart needs at least three games we have ingested.")}`}
    </article>

    ${logRows ? `<div class="section-title">Last ${rows.length} game${
      rows.length === 1 ? "" : "s"}
      <span class="sub">— ${escapeHtml(s.note)}, newest first.</span></div>
    <div class="card pp-logs">${logRows}</div>` : ""}

    ${warn ? `<div class="section-title minor">What argues against it
      <span class="sub">— the model’s own objections, not hidden.</span></div>
      <div class="card"><ul class="reasons">${warn}</ul></div>` : ""}`;
  const bk = document.getElementById("pp-back");
  if (bk) bk.addEventListener("click", detailBack);
  if (typeof fillMeters === "function") fillMeters(host);
}

/* The tiles a Most Likely pick leads with: its chance (the hero — the
   number the board ranked it on), the projection, and what the price
   implies beside it. */
function likelyMetricsHTML(lk, proj) {
  return `${lk.model_prob != null && Number.isFinite(Number(lk.model_prob))
    ? `<div class="metric primary"><div class="k">Chance</div>
      <div class="v pos">${wholePct(lk.model_prob)}</div></div>` : ""}
    ${proj}
    ${lk.implied_prob != null ? `<div class="metric"><div class="k">Book implies</div>
      <div class="v">${wholePct(lk.implied_prob)}</div></div>` : ""}`;
}

/* EVERY BET GETS ONE (Ethan, 2026-09-24, beside a Packers moneyline
   page that had none: "Every single bet we offer needs too have a why
   it's likely section"). A Most Likely pick brings its own row (`lk`);
   an Edge pick or a long shot is read off its own card — its chance, its
   line, its price — and the section says which board it is on. */
function whyBoardOf(r) {
  const d = state.data || {};
  if ((d.long_shots || []).includes(r) || (d.longshot_watch || []).includes(r)) return "longshot";
  return r.recommended === false ? "pass" : "edge";
}

/* A scorer bet (anytime touchdown, a home run) is yes-or-no, not a
   number against a line: its section reads like the Most Likely board's
   anytime rows (line null), never "0.2 home runs, 0.3 below the 0.5". */
const WHY_SCORER = /anytime|first_td|home_run/;

/* "On the board": how long the board has held a pick, and at what
   (engine/likely.HOLD_MARGIN). Shared by props and game bets. */
function whyHeldItem(lk, p) {
  const held = likelyHeld(lk);
  if (!held) return null;
  const was = Number(lk.first_prob);
  const moved = Math.abs(was - p) >= 0.005 && Number.isFinite(was)
    ? `${wholePct(was)} when it went up, ${wholePct(p)} now` : `${wholePct(p)} since it went up`;
  const side = String(lk.side || "").toLowerCase();
  return ["On the board", `${held.fresh ? `New — went up at ${escapeHtml(held.when)}`
    : `Since ${escapeHtml(held.when)}, held through every refresh`}: ${moved}.${lk.first_line != null
    ? ` It went up at ${escapeHtml(side)} ${escapeHtml(String(lk.first_line))}; that number no
      longer clears the board’s bars at its best price, so it shows at ${escapeHtml(String(lk.line))} —
      and goes back to ${escapeHtml(String(lk.first_line))} if it clears again.` : ""}${lk.locked && lk.lock_note
    ? ` Locked in: ${escapeHtml(lk.lock_note)}` : ""} A pick stays up until its game — only its game
    starting or its player being ruled out takes it down.`];
}
function caseHighTotal() { return state.sport === "cfb" ? 56 : GS_HIGH_TOTAL; }
function caseLowTotal() { return state.sport === "cfb" ? 46 : 41; }

/* What the lines say about how the game goes, for this market, from the
   over's side. A close spread with a high total is its own script — a
   back-and-forth game — not "the favourite ahead". */
function caseScriptFact(r, g, chainWhy) {
  if (!g || !["nfl", "cfb"].includes(state.sport)) return null;
  const exp = scriptExpected(g);
  const tot = exp.total, sp = exp.spread;
  if (tot == null && sp == null) return null;
  const mkt = String(r.market || "").toLowerCase();
  const mine = r.team ? teamName(r.team) : "his team";
  const fav = exp.fav && exp.fav === r.team, dog = exp.fav && exp.fav !== r.team;
  const lines = [sp != null && exp.fav ? `${teamName(exp.fav)} ${MINUS}${sp.toFixed(1)}` : "",
    tot != null ? `total ${tot}` : ""].filter(Boolean).join(", ");
  const close = sp != null && sp <= CASE_CLOSE_SPREAD, wide = sp != null && sp >= CASE_WIDE_SPREAD;
  const high = tot != null && tot >= caseHighTotal(), low = tot != null && tot <= caseLowTotal();
  let sign = 0, text = "";
  if (GS_CATCH.test(mkt) || GS_PASS.test(mkt)) {
    if (close && high) { sign = 1; text = `The lines expect a close, high-scoring game (${lines}) — a back-and-forth game keeps both teams throwing to the end`; }
    else if (wide && dog) { sign = 1; text = `${mine} are ${sp.toFixed(1)}-point underdogs (${lines}) — a team playing from behind throws more`; }
    else if (wide && fav) { sign = -1; text = `${mine} are ${sp.toFixed(1)}-point favorites (${lines}) — a team that gets ahead throws less late`; }
    else if (low) { sign = -1; text = `A low total (${lines}) — fewer plays and fewer throws for everyone`; }
    else if (high) { sign = 1; text = `A high total (${lines}) — more plays and more throws`; }
    else { text = `The lines expect a close, middling game (${lines}) — no strong lean either way`; }
  } else if (GS_RUSH.test(mkt)) {
    if (wide && fav) { sign = 1; text = `${mine} are ${sp.toFixed(1)}-point favorites (${lines}) — a team ahead runs the clock`; }
    else if (wide && dog) { sign = -1; text = `${mine} are ${sp.toFixed(1)}-point underdogs (${lines}) — a team behind passes more and runs less`; }
    else if (close && high) { text = `A close, high-scoring game (${lines}) — both teams lean on the pass, but the carries stay`; }
    else { text = `The lines expect a close game (${lines}) — no strong lean on the carries`; }
  } else {
    return null;
  }
  const inNum = /script|ahead|behind|trail|lead|favou?red|underdog|spread/i.test(chainWhy || "");
  return { text, sign, in_number: inNum, kind: "script" };
}

function pickCase(r, lk, x, g) {
  const side = String((lk && lk.side) || r.side || "").toLowerCase();
  const over = !/under|^no$/.test(side);
  const mkt = String(r.market || "").toLowerCase();
  const scorer = WHY_SCORER.test(mkt);
  const facts = ((x && x.facts) || []).filter((f) => !f.markets || f.markets.includes(mkt)
    || (scorer && f.markets.some((m) => WHY_SCORER.test(m))));
  const steps = ((r.chain && r.chain.steps) || []);
  const chainWhy = steps.filter((st) => /matchup|context/.test(String(st.key || ""))).map((st) => st.why || "").join(" ");
  const sf = caseScriptFact(r, g, chainWhy);
  const all = facts.slice();
  if (sf) all.push(sf);
  /* HIS RED-ZONE ROLE, first on a scorer (every touchdown scan opens with
     "6 red-zone carries, 3 inside the 5"). In our number: the chain reads
     it through his red-zone share and xFP. A back needs more touches a
     game than a receiver to count as a real goal-line role. */
  const gl = scorer && r.goal_line;
  if (gl && gl.games) {
    const per = ((gl.rz_car || 0) + (gl.rz_tgt || 0)) / gl.games;
    const rb = /^RB$/i.test(String((x && x.pos) || r.position || ""));
    const hi = rb ? 1.5 : 1.0, lo = rb ? 0.5 : 0.3;
    const chances = Number(r.rz_chances);
    all.push({ text: `${r.goal_line_text || "Red-zone work measured"}${
        Number.isFinite(chances) && chances > 0 ? ` — about ${chances.toFixed(1)} red-zone chances expected this week` : ""}`,
      sign: per >= hi ? 1 : per <= lo ? -1 : 0, in_number: true, kind: "goal_line" });
  }
  // His own games against this line.
  const line = Number((lk && lk.line != null ? lk.line : r.line));
  const logs = (r.logs || []).filter((gm) => Number.isFinite(Number(gm.value))).slice(0, 10);
  if (logs.length >= 4) {
    const anytime = scorer || !Number.isFinite(line);
    const hits = logs.filter((gm) => anytime ? Number(gm.value) > 0 : Number(gm.value) > line).length;
    const rate = hits / logs.length;
    all.push({ text: anytime ? `Scored in ${hits} of his last ${logs.length} games`
        : `Went over ${String(line)} in ${hits} of his last ${logs.length} games`,
      sign: rate >= 0.6 ? 1 : rate <= 0.4 ? -1 : 0, in_number: true, kind: "form" });
  }
  // THE LINE'S OWN MOVE (the breakdowns' "pushed from 78.5 to 84.5 — the
  // market already knows"): a line that rose has made the over dearer.
  const tape = (r.line_tape || []).filter((t) => t && t.line != null);
  if (tape.length >= 2 && !scorer) {
    const a = Number(tape[0].line), b = Number(tape[tape.length - 1].line);
    if (Number.isFinite(a) && Number.isFinite(b) && Math.abs(b - a) >= 0.5) {
      all.push({ text: `The line moved ${a} → ${b} in the last day — the market moved ${b > a ? "toward the over, so the over needs more now" : "toward the under, so the over needs less now"}`,
        sign: b > a ? -1 : 1, in_number: false, kind: "line" });
    }
  }
  const dir = over ? 1 : -1;
  const forBet = all.filter((f) => f.sign * dir > 0);
  const against = all.filter((f) => f.sign * dir < 0);
  const neutral = all.filter((f) => !f.sign);
  const opp = r.opponent || (g ? (g.home === r.team ? g.away : g.home) : "");
  const cov = g && g.scan && g.scan.coverage && g.scan.coverage[opp];
  const wr = /^(WR)$/i.test(String((x && x.pos) || r.position || ""));
  const te = /^(TE)$/i.test(String((x && x.pos) || r.position || ""));
  return { side, over, scorer, forBet, against, neutral, opp,
           corners: (wr || te) && cov ? (cov.corners || []) : [], te,
           lead: x && x.usage && (x.usage.tgt_share || 0) >= 0.2 };
}

function pickCaseHTML(r, lk, x, g, p) {
  const c = pickCase(r, lk, x, g);
  if (!c.forBet.length && !c.against.length && !c.corners.length) return "";
  const sideWord = c.scorer ? (c.over ? "touchdown" : "no touchdown")
    : `${c.over ? "over" : "under"}${(lk && lk.line != null) || r.line != null ? ` ${(lk && lk.line != null) ? lk.line : r.line}` : ""}`;
  const proj = Number(r.projection), line = Number(lk && lk.line != null ? lk.line : r.line);
  const num = (v) => Number(v).toFixed(1).replace(/\.0$/, "");
  const what = String(r.market_label || r.market || "").toLowerCase();
  let verdict = "";
  if (!c.scorer && Number.isFinite(proj) && Number.isFinite(line)) {
    const gap = proj - line;
    verdict = `We project ${num(proj)} ${escapeHtml(what)} — ${num(Math.abs(gap))} ${gap >= 0 ? "above" : "below"} the ${num(line)} line.`;
  } else if (Number.isFinite(p)) {
    verdict = `We give it ${wholePct(p)}.`;
  }
  const inAg = c.against.filter((f) => f.in_number), shownAg = c.against.filter((f) => !f.in_number);
  if (!c.against.length) {
    verdict += " Everything we read on this game points the same way.";
  } else if (!inAg.length) {
    verdict += ` What points the other way isn’t part of our number: each of ${shownAg.length === 1 ? "those facts" : "those facts"} was tested over four seasons and did not predict this stat — so it is shown, not counted.`;
  } else {
    verdict += ` ${inAg.length === 1 ? "One thing in our number pulls" : `${inAg.length} things in our number pull`} the other way, and ${
      inAg.length === 1 ? "it is" : "they are"} why this sits at ${Number.isFinite(p) ? wholePct(p) : "its chance"} and not higher.`;
  }
  /* THE PRICE IT IS WORTH (every breakdown's "fair -186, max playable
     -175"): our chance as odds, and the worst price that still leaves a
     3-point cushion over what the book's price implies. */
  if (Number.isFinite(p) && p > 0.05 && p < 0.97) {
    const am = (q) => q >= 0.5 ? `${MINUS}${Math.round(100 * q / (1 - q))}` : `+${Math.round(100 * (1 - q) / q)}`;
    const cap = Math.max(0.05, p - 0.03);
    verdict += ` At ${wholePct(p)} this is worth ${am(p)}; don’t take it past ${am(cap)}.`;
  }
  const li = (f) => `<li class="pc-fact${f.in_number ? "" : " pc-shown"}"><span>${escapeHtml(f.text)}</span><em>${
    f.in_number ? "in our number" : "shown — not in our number"}</em></li>`;
  const col = (title, list, cls) => list.length ? `<div class="pc-col ${cls}"><div class="pc-col-k">${title}</div>
    <ul>${list.map(li).join("")}</ul></div>` : "";
  let corners = "";
  if (c.corners.length) {
    const who = c.te
      ? `Tight ends draw linebackers and safeties more than corners; these are ${escapeHtml(c.opp)}’s corners for the snaps he lines up wide.`
      : c.lead
      ? `As his team’s lead receiver he lines up outside on most snaps, so he sees ${escapeHtml(c.opp)}’s outside corners most, and the nickel when he moves inside.`
      : `${escapeHtml(c.opp)}’s corners — outside and in the slot.`;
    corners = `<div class="pc-cover"><div class="pc-col-k">Who covers him</div><p class="pc-cover-note">${who}
      No free data publishes which corner shadows which receiver, so this is the room, not a confirmed assignment.</p>
      <div class="pc-table" role="table">
        <div class="pc-tr pc-th" role="row"><span>Corner</span><span>Targets</span><span>Catches</span><span>Yards</span><span>Yds/target</span><span>Rating</span><span>TD</span></div>
        ${c.corners.map((k) => `<div class="pc-tr" role="row"><span><b>${escapeHtml(k.name)}</b> ${escapeHtml(k.spot === "NB" ? "slot" : k.spot)}${
          k.status ? ` · ${escapeHtml(String(k.status).toLowerCase())}` : ""}${k.next_man_up ? " · fills in" : ""}</span><span>${k.targets ?? "—"}</span><span>${
          k.cmp ?? "—"}</span><span>${k.yds ?? "—"}</span><span>${k.yds_per_tgt != null ? num(k.yds_per_tgt) : "—"}</span><span>${
          k.rating != null ? Math.round(k.rating) : "—"}</span><span>${k.td ?? "—"}</span></div>`).join("")}
      </div><p class="pc-cover-note">This season, in coverage (passer rating allowed: 158 is perfect, about 90 is league average).</p></div>`;
  }
  return `<section class="pick-case" aria-label="The case for the ${escapeHtml(sideWord)}">
    <div class="pc-head">The case for the ${escapeHtml(sideWord)}</div>
    ${verdict ? `<p class="pc-verdict">${verdict}</p>` : ""}
    <div class="pc-cols">${col(`Backs the ${escapeHtml(c.scorer ? (c.over ? "touchdown" : "no") : (c.over ? "over" : "under"))}`, c.forBet, "pc-for")}${
      col("Works against it", c.against, "pc-against")}</div>
    ${c.neutral.length ? `<details class="pc-more"><summary>Neutral here (${c.neutral.length})</summary><ul>${c.neutral.map(li).join("")}</ul></details>` : ""}
    ${corners}
  </section>`;
}

function whyLikelyHTML(v, r, lk) {
  const board = lk ? (lk.board || "likely") : whyBoardOf(r);
  if (!lk) {
    const scorer = WHY_SCORER.test(String(r.market || "")) && !(Number(r.line) >= 1);
    lk = { model_prob: r.hit_prob != null ? r.hit_prob : r.model_prob,
           line: scorer ? null : r.line, side: r.side, lineup_confirmed: r.lineup_confirmed,
           implied_prob: r.odds != null && Number(r.odds) ? impliedOf(r.odds) : null };
  }
  const items = [];
  const p = Number(lk.model_prob);
  const t = probTier(p);
  const over = String(v.side || "OVER").toUpperCase() === "OVER";
  const line = Number(v.line);
  const anytime = lk.line == null || !Number.isFinite(line);
  const what = String(r.market_label || r.market || "").toLowerCase();
  const num = (x) => Number(x).toFixed(1).replace(/\.0$/, "");
  if (Number.isFinite(p)) {
    items.push(["Our chance", `${wholePct(p)}${t ? ` — ${t.word}, the ${t.band} band`
      : p < 0.5 ? ` — it lands about ${Math.max(1, Math.round(p * 10))} times in 10` : ""}. ${lk.bet
      ? `Our number when this bet was placed; the Record page grades it at the price it was taken at.`
      : board === "likely"
      ? `The number this board is ranked on, calibrated against how its picks have landed; the
        Record page checks every band.`
      : `The model’s own number for this side, calibrated against how its picks have landed.`}`]);
  }
  const heldItem = whyHeldItem(lk, p);
  if (heldItem) items.push(heldItem);
  const proj = Number(r.projection);
  if (!anytime && Number.isFinite(proj)) {
    const gap = proj - line;
    const withIt = over ? gap > 0 : gap < 0;
    items.push(["The projection", `We have him at ${num(proj)} ${escapeHtml(what)} —
      ${num(Math.abs(gap))} ${gap >= 0 ? "above" : "below"} the ${num(line)} line${withIt
        ? "" : ", the other side of it: the chance comes from how widely his games spread"}.`]);
  }
  const logs = (r.logs || []).filter((g) => Number.isFinite(Number(g.value))).slice(0, 10);
  if (logs.length >= 3) {
    const hit = (g) => anytime ? Number(g.value) > 0
      : over ? Number(g.value) > line : Number(g.value) < line;
    const hits = logs.filter(hit).length;
    const early = logs.filter((g) => g.partial);
    const missed = early.filter((g) => !hit(g)).length;
    items.push(["His games", `${anytime ? (/home_run/.test(String(r.market || "")) ? "Homered" : "Scored")
      : `${over ? "Over" : "Under"} ${num(line)}`} in
      ${hits} of his last ${logs.length}${early.length ? ` — ${early.length === 1
        ? `one was a game he left early${missed ? ", and it is one of the misses" : ""}`
        : `${early.length} were games he left early`}` : ""}.`]);
  }
  const c = r.chain;
  if (c && (c.steps || []).length) {
    const moved = c.steps.filter((s) => Math.abs(Number(s.mult) - 1) >= 0.02)
      .sort((a, b) => Math.abs(Number(b.mult) - 1) - Math.abs(Number(a.mult) - 1)).slice(0, 4);
    items.push(["What moved it", moved.length
      ? `<ul class="wl-moves">${moved.map((s) => {
          const m = Number(s.mult);
          // THE WHOLE REASON, every clause: a step can hold two effects
          // (the matchup step carries the defence AND the game-script
          // tilt), and its first clause alone printed "(×1.05)" beside a
          // +8% the reader could not reconcile.
          const why = String(s.why || "");
          return `<li><b class="${m >= 1 ? "pos" : "neg"}">${escapeHtml(s.label || s.key)}
            ${m >= 1 ? "+" : "−"}${Math.abs(Math.round((m - 1) * 100))}%</b>${why
            ? ` — ${escapeHtml(why.length > 240 ? why.slice(0, 237) + "…" : why)}` : ""}</li>`;
        }).join("")}</ul>`
      : "Nothing around him — matchup, weather, who plays — moved his number by as much as 2%; it is his own form."]);
  }
  if (v.odds != null) {
    const book = v.book ? `${escapeHtml(v.book)} ` : "";
    const fresh = !lk.bet && lk.price_refreshed;
    items.push(["The price", `${lk.bet ? "Placed at " : ""}${book}${escapeHtml(oddsTxt(v.odds))}${fresh
      ? ` now (posted at ${escapeHtml(oddsTxt(lk.posted_odds))}${lk.posted_book
          ? ` at ${escapeHtml(lk.posted_book)}` : ""}, the price it is graded at)`
      : lk.implied_prob != null
      ? ` implies ${wholePct(lk.implied_prob)}; we have it at ${wholePct(p)}` : ""}.${lk.rung === "alt"
      && lk.main_line != null ? ` An alternate line: the book’s main number is
        ${escapeHtml(String(lk.main_side || "").toLowerCase())} ${escapeHtml(String(lk.main_line))}${
        lk.main_odds != null ? ` at ${escapeHtml(oddsTxt(lk.main_odds))}` : ""}, and this one is
        the likelier rung of its ladder.` : ""}`]);
  }
  const cautions = [];
  const thin = ((state.data || {}).thin || {})[r.player];
  if (thin && thin.games) {
    cautions.push(`only ${thin.games} game${thin.games === 1 ? "" : "s"} this season to go on — shown, not staked`);
  }
  if (lk.lineup_confirmed === false) {
    cautions.push("his team’s lineup card is not out yet — he is projected to play, and the pick is recorded only once it posts");
  }
  if (r.qb_card && r.qb_card.headline) cautions.push(escapeHtml(r.qb_card.headline));
  if (r.mate_card && r.mate_card.headline) cautions.push(escapeHtml(r.mate_card.headline));
  if (cautions.length) items.push(["Worth knowing", cautions.join("; ") + "."]);
  // What game this pick needs, and what it pulls against (gameScriptsHTML).
  { const gs = scriptWhyItem(lk && lk.player ? { ...r, ...lk } : r); if (gs) items.push(gs); }
  /* THE MATCHUP SCAN'S READ ON HIM, here with the rest of the reasons
     (Ethan, 2026-09-25: the scan said why St. Brown could do well and
     "Why it's likely" did not). */
  /* THE CASE (pickCaseHTML) replaces the read's flat list here: the same
     facts, sorted for this bet and each marked in-our-number or shown. */
  const rr = lk && lk.player ? { ...r, ...lk } : r;
  const x = pickScanRead(lk && lk.player ? { ...r, ...lk } : r);
  const caseHTML = typeof pickCaseHTML === "function"
    ? pickCaseHTML(rr, lk, x, typeof scriptGameOf === "function" ? scriptGameOf(rr) : null, p) : "";
  if (x && !caseHTML) {
    const bits = scanUsageBits(x);
    const said = scanReadForBet(x, (lk && lk.side) || r.side);
    items.push([`The matchup — ${escapeHtml(said ? said.text : x.label)}`,
      `${bits.length ? `<div class="ms-use">${escapeHtml(teamName(x.team))} ${escapeHtml(x.pos || "")} · ${
        escapeHtml(bits.join(" · "))}</div>` : ""}${scanWhyList(x)}`]);
  }
  return whySectionHTML(items, p, board, caseHTML);
}

function whyGameHTML(b, likely) {
  const items = [];
  const p = Number(likely ? b.model_prob : (b.win_prob != null ? b.win_prob : b.model_prob));
  const t = probTier(p);
  const kind = b.bet_type || b.market || "";
  const team = b.team || (b.side === "home" ? b.home : b.away);
  const nm = (x) => escapeHtml(typeof teamName === "function" ? teamName(x) : x);
  if (Number.isFinite(p)) {
    items.push(["Our chance", `${wholePct(p)}${t ? ` — ${t.word}, the ${t.band} band` : ""}. ${likely
      ? `The number this board is ranked on, calibrated against how its picks have landed; the
        Record page checks every band.`
      : `The model’s own number for this side.`}`]);
  }
  if (likely && b.rank_note) {
    items.push(["How it’s rated", escapeHtml(b.rank_note)]);
  } else if (!likely && b.win_prob != null && b.fair_prob != null) {
    items.push(["How it’s rated", `Our team model has it at ${wholePct(b.win_prob)}; the book’s price,
      with its margin taken out, says ${wholePct(b.fair_prob)}. The gap is the edge.`]);
  }
  const heldItem = likely ? whyHeldItem(b, p) : null;
  if (heldItem) items.push(heldItem);
  const s = gameBetSeries(b);
  if (s && (s.values || []).length >= 3) {
    const vals = s.values.slice(0, 10).map(Number).filter(Number.isFinite);
    const hits = vals.filter((v) => (s.over ? v > s.line : v < s.line)).length;
    const n = vals.length;
    const line = Number(b.line);
    const said = kind === "moneyline" ? `${nm(team)} won ${hits} of their last ${n}`
      : kind === "spread" ? `${nm(team)} covered ${escapeHtml(s.lineText || String(b.line))} in ${hits} of their last ${n}`
      : kind === "team_total" ? `${nm(team)} went ${s.over ? "over" : "under"} ${line} in ${hits} of their last ${n}`
      : `${nm(b.home)}’s last ${n} games went ${s.over ? "over" : "under"} ${line} in ${hits}`;
    items.push(["Recent games", `${said}.`]);
  }
  const notes = (likely ? likelyNotes(b) : (b.reasons || [])).slice(0, 5);
  if (notes.length) {
    items.push(["What goes into it", `<ul class="wl-moves">${notes.map((x) =>
      `<li>${escapeHtml(x.length > 240 ? x.slice(0, 237) + "…" : x)}</li>`).join("")}</ul>`]);
  }
  if (b.odds != null) {
    const implied = b.implied_prob != null ? Number(b.implied_prob)
      : Number(b.odds) ? impliedOf(b.odds) : null;
    items.push(["The price", `${b.book ? `${escapeHtml(b.book)} ` : ""}${escapeHtml(oddsTxt(b.odds))}${
      implied != null ? ` implies ${wholePct(implied)}` : ""}${Number.isFinite(p) ? `; we have it at ${wholePct(p)}` : ""}.`]);
  }
  { const gs = scriptWhyItem(b); if (gs) items.push(gs); }
  return whySectionHTML(items, p, likely ? "likely" : b.recommended === false ? "pass" : "edge");
}

function renderPropPage() {
  const host = document.getElementById("prop-body");
  if (!host) return;
  if (String(state.propId || "").startsWith("game|")) {
    /* `(state.data || {})`, and this one is REACHABLE. A shared game-bet
       link — #prop/game|… — is opened cold, and `initialView()` routes
       to it before `load()` has answered, so `state.data` is still null.
       `state.data.game_bets` then threw, and the throw was SILENT:
       renderPropPage runs inside document.startViewTransition, where an
       exception becomes a rejected promise the browser swallows. The
       reader got a blank page and the console said nothing.

       Measured: opening #prop/game|… with the board fetch blocked
       rendered an empty view, while the same link to a PLAYER prop
       rendered "That pick is not on tonight's board" correctly — because
       `allProps()` already guards and this line did not. */
    /* Both lists: a likelihood game row can be the OTHER side of the
       edge card — the side the board ranks where the edge board backed
       the other one on price — and it carries the card shape
       (likely.from_game_bet), so the same page draws it. */
    const b = findGameRow(state.propId);
    // Opened from Most Likely, that board's row — when both boards carry
    // the same id, findGameRow answers with the edge board's first.
    const lkRow = state.propLikely && ((state.data || {}).most_likely || [])
      .find((g) => g.kind === "game" && gameBetId(g) === state.propId);
    if (lkRow || b) return renderGameBetPage(lkRow || b);
  }
  // A Most Likely pick with no prop on the edge board is drawn from its
  // own row (likelyTarget) — the row is its own pick.
  const lkRow = state.propLikely && state.propLikelyId ? findLikelyProp(state.propLikelyId) : null;
  let r = findProp(state.propId) || (state.propLikely ? findLikelyProp(state.propId) : null);
  // NEVER ANOTHER OF HIS PROPS UNDER THIS PICK: the page draws the tapped
  // row's own market, or the row itself (Geno Smith, 2026-09-25).
  if (lkRow && (!r || r.player !== lkRow.player || r.market !== lkRow.market)) {
    r = likelyTarget(lkRow);
  }
  if (!r) {
    // A bookmarked or stale link. Say so — a blank page reads as broken.
    host.innerHTML = `<div class="empty-slate"><div class="es-icon">${icon("search", 30)}</div>
      <h3>That pick is not on tonight’s board</h3>
      <p>Props are rebuilt every slate, so a link to one only lives as long
      as the pick does.</p>
      <button class="btn ghost gp-back" id="pp-back">${escapeHtml(detailBackLabel())}</button></div>`;
    const b0 = document.getElementById("pp-back");
    if (b0) b0.addEventListener("click", detailBack);
    return;
  }
  /* OPENED FROM MOST LIKELY, the page is that board's pick (2026-09-23,
     Ethan: "when I click on them it just shows charts, it doesn't show
     the page we show when you click on edge bets"). The pick page led
     with the EDGE board's reading of the same prop — "Edge +0.0%", a
     grade, a 66% that was not the 71% on the row he tapped — and the
     first explanation sat under the charts, sixty percent of the way
     down, opening "No credible market edge". Now: the row's own side,
     line, book, price and chance head the page; "Why it’s likely" comes
     straight after; the chart and the logs read against that line; and
     the edge board's gates and price refusals stay on the edge board. */
  const lk = state.propLikely ? (lkRow || likelyFor(r)) : betPickFor(r);
  const v0 = lk && lk.line != null
    ? { ...r, side: lk.side || r.side, line: lk.line, odds: lk.odds, book: lk.book }
    : lk ? { ...r, odds: lk.odds, book: lk.book } : r;
  /* AN ANYTIME SCORER IS OVER 0.5 (2026-09-25). A Most Likely scorer row
     carries side "yes" and no line; read literally that was UNDER a line
     of 0 — "yes 0 Anytime TD", "ODDS (UNDER)", and a 0/10 hit rate on
     Amon-Ra St. Brown, who scores in half his games (Ethan's screenshot).
     The bet is one touchdown or more, and every number here reads it so. */
  const scorer = WHY_SCORER.test(String(r.market || "")) && !(Number(v0.line) >= 1);
  const v = scorer
    ? { ...v0, side: /^(no|under)$/i.test(String(v0.side || "")) ? "UNDER" : "OVER", line: 0.5 }
    : v0;
  const over = String(v.side || "OVER").toUpperCase() === "OVER";
  const line = Number(v.line);
  const logs = (r.logs || []).filter((g) => Number.isFinite(Number(g.value)));
  const N = 5;
  const shown = Math.min(N, logs.length);
  const tier = lk ? probTier(lk.model_prob) : null;
  const proj = r.projection != null
    ? `<div class="metric"><div class="k">Projection</div><div class="v">${
        Number(r.projection).toFixed(1)}${r.proj_low != null
        ? ` <span class="sub">(${Number(r.proj_low).toFixed(0)}–${
            Number(r.proj_high).toFixed(0)})</span>` : ""}</div></div>` : "";
  const reasons = (lk ? likelyNotes(r) : (r.reasons || [])).slice(0, 8)
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  /* SIX PILL BUTTONS WERE PILED ABOVE THIS CARD, wrapping into two
     rows on a phone (Ethan, 2026-08-25, circling them: "It feels cheap
     just having all these buttons here"). The cleanup is structural,
     not cosmetic: NAVIGATION (back, the player page) stays above the
     card as two quiet text links, and the ACTIONS on the pick (parlay,
     send, copy link, share card) become one hairline-divided strip
     INSIDE the card, under the pick's identity — where an action on a
     thing belongs. Every data-attribute survives; only the furniture
     moved. */
  const keep = ccKeep(host);
  host.innerHTML = `
    <div class="pp-nav">
      <button class="btn-quiet gp-back" id="pp-back">${escapeHtml(detailBackLabel())}</button>
      ${r.player ? `<button class="btn-quiet" data-player-page="${escapeAttr(slugify(r.player))}"
        >Player page →</button>` : ""}
    </div>
    <article class="card pp-card">
      <div class="card-head">
        <div class="card-id">${betMark(r, 56, 76)}
          <div>
            <div class="player">${escapeHtml(r.player || "")}
              <span class="ml-odds">${oddsTxt(v.odds)}</span></div>
            <div class="subtitle">${[r.position ? escapeHtml(r.position) : "",
              r.team ? teamLinkHTML(state.sport, r.team) : "",
              r.opponent ? `vs ${teamLinkHTML(state.sport, r.opponent)}` : ""]
              .filter(Boolean).join(" · ")}</div>
            <div class="pick">${scorer ? `${escapeHtml(r.market_label || r.market || "")} · ${over ? "Yes" : "No"}`
              : `${escapeHtml(v.side || "")} ${Number.isFinite(line) ? escapeHtml(String(line)) : ""} ${
              escapeHtml(r.market_label || r.market || "")}`}${lk && v.book
              ? ` <span class="pp-book">· ${escapeHtml(v.book)}</span>` : ""}</div>
            ${lk && lk.bet ? `<div class="pp-board">${escapeHtml(lk.book_name)} · placed ${escapeHtml(oddsTxt(lk.odds))}${
                lk.placed_at ? ` · ${escapeHtml(placedStamp(lk.placed_at))}` : ""}</div>`
              : lk ? `<div class="pp-board">Most Likely${tier ? ` · ${escapeHtml(tier.word)}` : ""}</div>` : ""}
            ${pickWarnHTML(lk || r)}
            ${lk && lk.locked && lk.lock_note ? `<div class="lk-lock mini">${icon("lock", 12)} Locked in — ${escapeHtml(lk.lock_note)}</div>` : ""}
            ${/* Priced from the sharp book's own pair at this line
                  (betting.sharp_anchor_for) — on every NFL row since it
                  was built and drawn nowhere until the audit's L-7. */
              r.sharp_anchored ? `<div class="pp-sharp" title="The chance is read off the sharp book’s own two-way price at this line">Priced off the sharp book</div>` : ""}
          </div>
        </div>
        ${lk ? "" : r.grade ? `<span class="grade ${gradeClass(r.grade)}">${
          escapeHtml(r.grade)}</span>` : ""}
      </div>
      <div class="pp-actions">
        ${lk && lk.bet ? "" : betItHTML(lk || r, "btn primary")}
        ${r.player && r.odds != null && !(lk && lk.bet) ? `<button class="btn ghost"
          data-slip="${escapeAttr(propId(r))}">${slipHas(r)
            ? "On slip" : "+ Parlay"}</button>` : ""}
        ${/* ONE SHARE, NOT THREE (the site audit, 2026-09-24): Send,
              Copy link and Share card sat side by side, six buttons across
              a 390px phone. Share opens the three together under the
              strip (the [data-send-pick] listener). */""}
        <button class="btn ghost" data-send-pick aria-controls="fr-send-slot"
          >Share</button>
        <button class="btn ghost" data-explain aria-controls="pp-explain"
          >Explain</button>
        <button class="btn ghost" data-ask-pick="${escapeAttr(propId(r))}"
          data-ask-label="${escapeAttr(`${r.player || ""} ${v.side || ""} ${v.line ?? ""} ${r.market_label || ""}`.replace(/\s+/g, " ").trim())}"
          >Ask</button>
      </div>
      <div id="fr-send-slot"></div>
      <div id="pp-explain" class="pp-explain" hidden aria-live="polite"></div>
      <div class="metrics">
        ${lk ? likelyMetricsHTML(lk, proj) : proj}
        ${!lk && r.hit_prob != null ? modelMetric(r, r.hit_prob) : ""}
        ${!lk && r.edge != null ? `<div class="metric primary"><div class="k">Edge</div>
          <div class="v ${r.edge >= 0 ? "pos" : "neg"}">${signedPct(r.edge)}</div></div>` : ""}
        ${/* EV deliberately absent: the chart's own stat row below carries
              it, and a number twice on one screen is the duplication Ethan
              had just finished pointing at on the prop cards. Three
              metrics also fill the row instead of wrapping one onto a
              second line by itself. */""}
      </div>
      ${whyLikelyHTML(v, r, lk)}
      ${lk && lk.bet ? "" : shoppedLineNote(v)}
      ${lk ? propAnalysis({ ...v, logs: r.logs }, { chance: lk.model_prob, tier: tier && tier.word, min: 1 })
           : propAnalysis(r, { min: 1 })}
    </article>

    ${booksTableHTML(r)}
    ${lineMoveHTML(r)}
    <div id="pp-books"></div>
    <div id="pp-lab"></div>

    ${shown ? `<div class="section-title">Last ${shown} game${shown === 1 ? "" : "s"}
      <span class="sub">— every one measured against tonight’s
      ${Number.isFinite(line) ? escapeHtml(String(line)) : "line"}, newest
      first, with who it came against.</span></div>
    <div class="card pp-logs">${propLogRows(r, logs, line, over, N)}</div>` : ""}

    ${(r.form && Object.keys(r.form).length) ? `<div class="section-title minor">Form
      <span class="sub">— the same player over longer windows, each read
      against the same number.</span></div>
    <div class="card pp-forms">${propFormRows(r.form, line, over)}</div>` : ""}

    ${chartSlot(r)}

    ${scriptCardHTML(r)}
    ${rippleCardHTML(r)}

    ${(() => { const vs = vsBlockHTML(r.player, state.sport, r.opponent || "");
      return vs ? `<div class="section-title minor">Versus
        <span class="sub">— his games against ${escapeHtml(teamName(r.opponent || ""))}
        and any other club he has faced.</span></div>
      <div class="card">${vs}</div>` : ""; })()}

    ${r.mate_card ? `<div class="section-title minor">${mateCardHTML(r.mate_card, 1)}
        <span class="sub">— ${({ "Teammate out": "a teammate is ruled out, and what the model did with it",
          "Teammate back": "a teammate is back; his games without him count for less",
          "Teammate questionable": "a teammate may not play, and what the model does if he sits" })[mateCardHTML(r.mate_card, 1)]}.</span></div>
      ${mateCardHTML(r.mate_card)}` : ""}

    ${r.qb_card ? `<div class="section-title minor">Quarterback
        <span class="sub">— his team is not starting its usual one.</span></div>
      ${qbCardHTML(r.qb_card)}` : ""}

    ${r.matchup_card ? `<div class="section-title minor">Matchup
        <span class="sub">— what ${escapeHtml(r.matchup_card.opponent || r.opponent || "")}
        give up to his position, and what the model did with it.</span></div>
      ${matchupCardHTML(r)}` : ""}

    ${reasons ? `<div class="section-title minor">${lk ? "The model’s notes" : "Why this pick"}</div>
      <div class="card"><ul class="reasons">${reasons}</ul></div>` : ""}

    ${/* The three sections that answer "how does this thing think", in the
          order the question is actually asked: where the number came from,
          what it had to survive, and what happened the last time we were
          here. Each draws nothing when its data is absent, so a slate
          built before they existed renders exactly as it did. */
      chainHTML(r)}
    ${lk ? "" : checksHTML(r)}
    ${compsHTML(r)}
    ${simLabHTML(r)}`;
  keep(host);
  const b = document.getElementById("pp-back");
  if (b) b.addEventListener("click", detailBack);
  if (typeof fillMeters === "function") fillMeters(host);
  // Every book's line and the steam (js/extras.js).
  // ...and the inventions' readings of this pick (js/extras.js pickLab).
  if (r.player && r.market) loadExtras().then((X) => X && (X.bookLines(document.getElementById("pp-books"), state.sport, r.player, r.market),
    X.pickLab(document.getElementById("pp-lab"), state.sport, r)));
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
    ${stadiumTonightHTML(g)}
  </div>`;
}

/* TONIGHT, IN THE MODEL'S OWN WORDS (Ethan, 2026-09-24, beside Lambeau at
   69°F under a note about late-season cold: "we are giving misleading
   info here … make sure weather is linked correctly"). The venue note is
   the building; this is the forecast for this kickoff, at this stadium,
   and what the model did with it — `conditions.why`, the same
   engine/weather read every prop at the game was priced with, so the page
   cannot say one thing while the number does another. Temperature is
   named when it moved nothing, because a reader sees it in the chip above
   and will otherwise assume it counted. */
function stadiumTonightHTML(g) {
  const w = g.weather || {};
  // The engine's provenance tail ("(measured: the 2016-2025 effects …)")
  // is for the methodology page; the reader gets the effect.
  const why = ((g.conditions || {}).why || []).filter(Boolean)
    .map((x) => String(x).replace(/\s*\(measured[^)]*\)\s*$/, ""));
  const lines = [...why];
  if (!w.dome && w.measured !== false && w.temp_f != null
      && !why.some((x) => /°F/.test(x))) {
    lines.push(`${Math.round(w.temp_f)}°F — temperature is not adjusted for: in ten seasons of games, `
      + "cold on its own showed no clear effect once wind, rain and snow were separated.");
  }
  if (!lines.length) return "";
  return `<div class="pk-tonight"><div class="pk-tonight-k">Tonight’s weather, as the model used it</div>
    <ul>${lines.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>`;
}

/* The pick page's line: what this pick needs, and which picks in the
   same game need the opposite. */
function scriptWhyItem(r) {
  const n = scriptNeed(r);
  if (!n.game || (!n.margin && !n.points)) return null;
  const needs = [n.whyMargin, n.whyPoints].filter(Boolean).join(", and ");
  const same = ((state.data || {}).most_likely || []).filter((x) => x !== r && showableLikelyRow(x)
    && scriptPickLabel(x) !== scriptPickLabel(r));
  const against = scriptClashes([r, ...same]).filter((c) => c.a === r || c.b === r)
    .map((c) => scriptPickLabel(c.a === r ? c.b : c.a));
  const exp = scriptExpected(n.game);
  const helps = exp.shootout && n.shoot ? (n.shoot > 0 ? "helps" : "hurts")
    : exp.margin && n.margin ? (exp.margin === n.margin ? "helps" : "hurts")
    : exp.points && n.points ? (exp.points === n.points ? "helps" : "hurts") : "";
  const expect = exp.shootout ? `a close, back-and-forth game (total ${exp.total})`
    : exp.fav ? `${teamName(exp.fav)} ahead${exp.spread != null ? ` by about ${exp.spread.toFixed(1)}` : ""}${
      exp.points ? `, ${exp.points > 0 ? "high" : "low"}-scoring` : ""}` : "";
  return ["Game script", `Needs ${needs}.${expect ? ` The lines expect ${expect} — that ${helps || "is neutral for"} this pick${helps ? "" : ""}.` : ""}${against.length
    ? ` It pulls against ${against.slice(0, 3).join(", ")} in the same game — keep them off one parlay.` : ""}`];
}

/* The game page's sections as a chip row that scrolls to each one —
   the segmented-markets convention every book's event page uses
   (Popular / Game lines / Player props), done as jumps rather than
   tabs so nothing on the page is hidden behind a tab nobody opens.
   Only sections the page drew get a chip; one section needs no row. */
function gpJumpHTML(jumps) {
  const list = (jumps || []).filter(Boolean);
  if (list.length < 2) return "";
  return `<nav class="std-chips gp-jump" aria-label="Sections of this game">${
    list.map(([id, label]) => `<button type="button" class="chip" data-jump="${escapeAttr(id)}">${
      escapeHtml(label)}</button>`).join("")}</nav>`;
}

/* One line per team's bullpen: its season rank and, when the last two
   days worked it past the model's threshold, the workload (L-7). */
const PEN_TIRED = 6;
function mlbPenNotes(g) {
  const rank = g.bullpen_rank || {}, tired = g.bullpen_fatigue || {};
  return [g.away, g.home].map((t) => {
    const r = Number(rank[t]), f = Number(tired[t]);
    const bits = [];
    if (r > 0) bits.push(`ranks ${ordinal(r)} of 30`);
    if (f >= PEN_TIRED) bits.push(`tired — ${f.toFixed(1)} relief innings over two days (about 5 is normal)`);
    return bits.length ? `${t} bullpen ${bits.join(", ")}` : "";
  }).filter(Boolean);
}

/* EACH TEAM'S NAME IS ITS TEAM PAGE (Ethan, 2026-09-24, circling
   "Cardinals @ 49ers" on the game page: "when you click on the teams
   names it will pull you to the team page where it shows the whole teams
   data"). The same door the team search's chips use — [data-team-open],
   with the league on the button, since the game page knows it and
   `_teamState` may not. */
function gpTeamDoor(team, opp) {
  return `<button type="button" class="gp-team" data-team-sport="${escapeAttr(state.sport)}"
    data-team-open="${escapeAttr(team)}"${opp ? ` data-team-against="${escapeAttr(opp)}"` : ""} title="${escapeAttr(`${teamName(team)} team page`)}"
    >${teamMark(team, 26)} <span class="gp-team-name">${escapeHtml(teamName(team))}</span></button>`;
}

/* ═══ THE MATCHUP SCAN (2026-09-24) ════════════════════════════════════
   Ethan, with a Falcons @ Packers breakdown he wanted for every game:
   "ranking the defenses and offenses and looking at where exactly in the
   defense and offense is good and bad and what players could shine and
   what players could hurt". engine/gamescan builds it per game: the
   units ranked 1-32 (opponent-adjusted, blended with last season), the
   widest unit-vs-unit gaps, each defence's corners with what they have
   allowed, its scheme and pass rush, the injuries and what they open —
   all on the game, free — and, in the paid `scan_reads`, a read on
   every player with a prop and the props it points at. Nothing here
   moves a number: a reason joins the model once it is measured. */
const SCAN_UNITS = [["overall", "Overall", "offense", "defense"],
  ["passing", "Passing", "passing offense", "pass defense"],
  ["rushing", "Rushing", "run game", "run defense"],
  ["explosive", "Explosive plays", "big-play offense", "big-play defense"],
  ["pressure", "Protection vs pass rush", "pass protection", "pass rush"],
  ["success", "Success rate", "offense", "defense"],
  // 2026-10-04: conversions per third down; touchdowns per red-zone trip.
  ["third_down", "Third downs", "third-down offense", "third-down defense"],
  ["redzone", "Red-zone touchdowns", "red-zone offense", "red-zone defense"],
  // 2026-10-08: yards a target on short (under 10 air yards), intermediate
  // (10–19) and deep (20+) throws — the defence rated by zone, for the
  // receiver whose targets live in one of them (engine/sources/nflunits).
  ["short", "Short throws", "short passing game", "short-throw defense"],
  ["mid", "Intermediate throws", "intermediate passing game", "intermediate-throw defense"],
  ["deep", "Deep throws", "deep passing game", "deep-throw defense"],
  // College only (CFBD's advanced table): havoc is sacks, tackles for
  // loss and takeaways; line yards credit the blocking, stuffs the front.
  ["havoc", "Havoc", "ball security", "havoc"],
  ["line", "Line yards", "run blocking", "front"],
  ["stuff", "Runs stuffed at the line", "run game", "run-stopping front"]];

// The scan ranks the league it was given: 32 NFL teams, about 134 FBS.
const scanTeams = (scan) => ((scan && scan.method) || {}).teams || 32;

/* THE TALE OF THE TAPE (2026-09-25). Ethan, on the two cards this
   replaced: "it's hard to tell whose defense is good and whose defense is
   bad". Each card crossed one team's offense with the other's defense
   under two columns headed OFF and DEF, so every row had to be decoded,
   and "BUF EDGE" came in two colours. Now: one column per team, its
   offense ranks together and its defense ranks together, every rank with
   the word for it, and the two questions a reader has answered in a line
   at the top. The crossings — offense against the other defense — are
   the mismatch sentences under it, each naming the team with the edge. */
const TAPE_LABELS = {
  overall: ["Overall", "Overall"], passing: ["Passing", "Pass defense"],
  rushing: ["Rushing", "Run defense"], explosive: ["Big plays", "Big plays allowed"],
  pressure: ["Pass protection", "Pass rush"], success: ["Play success rate", "Stopping plays"],
  havoc: ["Ball security", "Havoc (sacks, TFLs, takeaways)"], line: ["Run blocking", "Run front"],
  stuff: ["Avoiding stuffed runs", "Stuffing runs"],
  third_down: ["Third-down conversions", "Third-down stops"],
  redzone: ["Red-zone TD rate", "Red-zone TDs allowed"],
  short: ["Short throws (yds a target)", "Short throws allowed"],
  mid: ["Intermediate throws", "Intermediate throws allowed"],
  deep: ["Deep throws", "Deep throws allowed"],
};

//: What a rank means, in a word, by quarter of the league.
function tapeTier(r, n = 32) {
  if (r == null) return null;
  const q = r / n;
  return q <= 0.25 ? ["good", "Strong"] : q <= 0.5 ? ["", "Above avg"]
    : q <= 0.75 ? ["", "Below avg"] : ["bad", "Weak"];
}

function tapeCell(r, n, now) {
  const t = tapeTier(r, n);
  if (!t) return `<span class="tp-cell">—</span>`;
  /* THIS SEASON ALONE, under the blended rank (engine/gamescan
     _stamp_now_ranks): the blend is mostly last season after two games,
     so a defence 10th this year read "28th · Weak" with nothing beside
     it saying so (Ethan, 2026-09-27, on the Jets). */
  /* One short centred line under a hairline, on every cell that has one,
     so a row's two boxes match (Ethan, 2026-09-27: "fix how the boxes
     look and the wording, it looks buggy" — "17th this season" in mono
     wrapped to two left-aligned lines in a 92px cell). */
  const nowLine = now != null
    ? `<small class="tp-now">This season <span class="tp-now-n">${ordinal(now)}</span></small>` : "";
  return `<span class="tp-cell ${t[0]}"><b>${ordinal(r)}</b><em>${t[1]}</em>${nowLine}</span>`;
}

function tapeVerdict(scan, a, b, side) {
  const ra = ((((scan.units || {})[a] || {})[side] || {}).overall || {}).rank;
  const rb = ((((scan.units || {})[b] || {})[side] || {}).overall || {}).rank;
  if (ra == null || rb == null) return "";
  const word = side === "off" ? "offense" : "defense";
  if (Math.abs(ra - rb) < 3) {
    return `<div class="tp-verdict"><span>Better ${word}</span><b>About even</b>
      <em>${ordinal(ra)} and ${ordinal(rb)}</em></div>`;
  }
  const [w, wr, lr] = ra < rb ? [a, ra, rb] : [b, rb, ra];
  return `<div class="tp-verdict"><span>Better ${word}</span><b>${teamMark(w, 18)} ${escapeHtml(teamName(w))}</b>
    <em>${ordinal(wr)} vs ${ordinal(lr)}</em></div>`;
}

/* WHICH SEASON THESE RANKS ARE (2026-09-25). Ethan, on the Jets' defence
   ranked 27th going into week 4: "we are pulling incorrect information or
   stale information or 2025 information". They were mostly 2025's — the
   ratings leaned on last season until midseason and the card never said
   so. This line says the split — since 2026-09-27 the measured one,
   growing with this season's games (engine/gamescan.unit_share,
   scanblendfit.py), last season still in — Ethan, 2026-09-25: "2025 data
   should def be used". */
function tapeBasis(scan, away, home) {
  const u = (t) => ((scan.units || {})[t]) || {};
  const games = Math.min(...[away, home].map((t) => Number(u(t).games) || 0));
  const last = Math.max(...[away, home].map((t) => 1 - (u(t).blend ?? 1)));
  if (!games) return "Last season’s numbers — no games yet this season";
  const g = `${games} game${games === 1 ? "" : "s"}`;
  return last > 0.005
    ? `This season (${g}) with last season filling in — ${Math.round(last * 100)}% of each rank is last season`
    : `This season only · ${g} each`;
}

/* …AND WHAT CHANGED ON EACH TEAM (2026-09-27). The engine names every
   new QB, head coach and coordinator (engine/teamchange); MEASURED
   (scanblendfit.py), only a new starting QB makes a season's own games
   predict more, so only that side's split moves (gamescan.unit_share).
   A side whose split moved says its share; a coaching change is named
   and says it left the split alone — never a percentage it did not
   cause. */
function tapeChanges(scan, away, home) {
  const lines = [];
  for (const t of [away, home]) {
    const u = ((scan.units || {})[t]) || {};
    const why = u.changed || {};
    const base = Math.round((u.blend ?? 0) * 100);
    const pct = (side) => Math.round((u[`blend_${side}`] ?? u.blend ?? 0) * 100);
    const said = new Set(), staff = [];
    for (const side of ["off", "def"]) {
      if (!(why[side] || []).length || pct(side) === base) continue;
      lines.push(`${teamName(t)} ${side === "off" ? "offense" : "defense"}: ${pct(side)}% this season — ${why[side].join("; ")}`);
      why[side].forEach((r) => said.add(r));
    }
    for (const side of ["off", "def"]) {
      for (const r of why[side] || []) if (!said.has(r) && !staff.includes(r)) staff.push(r);
    }
    if (staff.length) {
      lines.push(`${teamName(t)}: ${staff.join("; ")} — same split as every team (new coaches measured no faster change, 2022–25)`);
    }
  }
  return lines.map((l) => `<p class="tp-basis tp-changed">${escapeHtml(l)}</p>`).join("");
}

/* THIS SEASON'S RAW NUMBERS beside the adjusted ranks (engine/gamescan.
   season_numbers): the table every bettor's breakdown leads with. */
const SEASON_NUMBER_ROWS = [["pts_for", "Points scored a game", "n"], ["pts_against", "Points allowed a game", "n"],
  ["rush_allowed", "Rushing yards allowed a game", "n"], ["ypc_allowed", "Yards a carry allowed", "d"],
  ["third_off", "Third-down conversions", "p"], ["third_def", "Third downs allowed", "p"],
  ["rz_off", "Red-zone TD rate", "p"], ["rz_def", "Red-zone TD rate allowed", "p"],
  ["run_rate", "Run rate", "p"], ["sacks", "Sacks a game", "d"]];
function seasonNumbersHTML(scan, away, home) {
  const nums = (scan && scan.numbers) || {};
  if (!nums[away] && !nums[home]) return "";
  const fmt = (c, kind) => !c || c.value == null ? "—"
    : kind === "p" ? `${Math.round(c.value * 100)}%` : kind === "d" ? Number(c.value).toFixed(1) : Number(c.value).toFixed(1);
  const cellOf = (t, k, kind) => { const c = (nums[t] || {})[k];
    return `<span class="tp-num">${fmt(c, kind)}${c && c.rank ? ` <em>${ordinal(c.rank)}</em>` : ""}</span>`; };
  const rows = SEASON_NUMBER_ROWS.filter(([k]) => (nums[away] || {})[k] || (nums[home] || {})[k])
    .map(([k, label, kind]) => `<div class="tp-row"><span class="tp-k">${escapeHtml(label)}</span>${cellOf(away, k, kind)}${cellOf(home, k, kind)}</div>`).join("");
  if (!rows) return "";
  const g = Math.max((nums[away] || {}).games || 0, (nums[home] || {}).games || 0);
  return `<div class="tp-group">This season, as played${g ? ` (${g} game${g === 1 ? "" : "s"})` : ""} — raw numbers, league rank</div>${rows}`;
}

function scanTapeHTML(scan, away, home) {
  const n = scanTeams(scan);
  const u = (t, side, k) => (((((scan.units || {})[t] || {})[side] || {})[k]) || {}).rank;
  const un = (t, side, k) => (((((scan.units || {})[t] || {})[side] || {})[k]) || {}).now_rank;
  const group = (side, title) => {
    const rows = SCAN_UNITS.map(([k]) => {
      const ra = u(away, side, k), rh = u(home, side, k);
      if (ra == null && rh == null) return "";
      const label = (TAPE_LABELS[k] || [k, k])[side === "off" ? 0 : 1];
      return `<div class="tp-row"><span class="tp-k">${escapeHtml(label)}</span>
        ${tapeCell(ra, n, un(away, side, k))}${tapeCell(rh, n, un(home, side, k))}</div>`;
    }).join("");
    return rows ? `<div class="tp-group">${title}</div>${rows}` : "";
  };
  return `<div class="card ms-tape">
      <div class="tp-verdicts">${tapeVerdict(scan, away, home, "off")}${tapeVerdict(scan, away, home, "def")}</div>
      <p class="tp-basis">${escapeHtml(tapeBasis(scan, away, home))}</p>${tapeChanges(scan, away, home)}
      <div class="tp-row tp-head"><span class="tp-k">Rank of ${n}, 1 = best</span>
        <span class="tp-team">${teamMark(away, 22)}<b>${escapeHtml(teamName(away))}</b></span>
        <span class="tp-team">${teamMark(home, 22)}<b>${escapeHtml(teamName(home))}</b></span></div>
      ${group("off", "Offense")}
      ${group("def", "Defense")}
      ${seasonNumbersHTML(scan, away, home)}
    </div>`;
}

function scanEdgeLine(e) {
  const u = SCAN_UNITS.find(([k]) => k === e.unit) || [e.unit, e.label, "offense", "defense"];
  const offBetter = e.gap > 0;
  // "Packers’", not "Packers’s": most team names are plural.
  const poss = (t) => { const n = teamName(t); return /s$/.test(n) ? `${n}’` : `${n}’s`; };
  const a = `${poss(e.off)} ${u[2]} (${ordinal(e.off_rank)})`;
  const b = `${poss(e.def)} ${u[3]} (${ordinal(e.def_rank)})`;
  return offBetter ? [`Edge ${teamName(e.off)}`, `${a} against ${b}`]
    : [`Edge ${teamName(e.def)}`, `${b} against ${a}`];
}

function scanCoverageHTML(scan, team) {
  const room = (scan.coverage || {})[team] || {};
  const sch = (scan.scheme || {})[team];
  const rush = (scan.rush || {})[team] || [];
  // THIS SEASON'S CHARTING (engine/sources/ftn, 2026-09-28): the blitz and
  // the box from FTN's file, current where the coverage line is a season
  // behind; and the offence's own habits under it.
  const ch = scan.charting || {};
  const cd = (ch.defense || {})[team];
  const co = (ch.offense || {})[team];
  // College has no defender files: no room, no scheme, no rushers, no card.
  if (!(room.corners || []).length && !(room.missing || []).length && !sch && !rush.length && !cd && !co) return "";
  const pct = pctRoundOr;
  const when = ch.season ? ` <span class="mini">(${escapeHtml(String(ch.season))} charting${ch.weeks ? `, ${ch.weeks} week${ch.weeks === 1 ? "" : "s"}` : ""}${ch.partial ? ` + part of week ${ch.partial}` : ""})</span>` : "";
  const nowLine = cd ? `Blitz ${pct(cd.blitz_rate)} of dropbacks · 8+ in the box ${pct(cd.heavy_box_rate)} of runs · light boxes ${pct(cd.light_box_rate)}` : "";
  const offLine = co ? `Play action ${pct(co.play_action_rate)} · motion ${pct(co.motion_rate)} · RPO ${pct(co.rpo_rate)} · screens ${pct(co.screen_rate)} · no-huddle ${pct(co.no_huddle_rate)}` : "";
  const corners = (room.corners || []).map((c) => {
    const spot = { LCB: "Left CB", RCB: "Right CB", NB: "Nickel" }[c.spot] || c.spot;
    const st = c.status ? ` <span class="chip down">${escapeHtml(c.status.toLowerCase())}</span>` : "";
    const now = c.targets ? `${c.targets} targets · ${c.yds_per_tgt ?? "—"} yds/target · ${c.rating != null ? Math.round(c.rating) : "—"} rating allowed`
      : "no targets yet this season";
    const last = c.last && c.last.targets ? `last season ${c.last.targets} targets, ${c.last.rating != null ? Math.round(c.last.rating) : "—"} rating` : "";
    const soft = room.weakest === c.name ? `<span class="ms-soft">Soft spot</span>` : "";
    return `<div class="ms-cb"><span class="ms-cb-spot">${escapeHtml(spot)}${c.next_man_up ? " · next man up" : ""}</span>
      <span class="ms-cb-who"><b>${escapeHtml(c.name)}</b>${st}${soft}</span>
      <span class="ms-cb-num">${escapeHtml(now)}${last ? `<br><span class="mini">${escapeHtml(last)}</span>` : ""}</span></div>`;
  }).join("");
  const out = (room.missing || []).map((m) => `${escapeHtml(m.name)} (${escapeHtml(m.spot)}, ${escapeHtml(m.status.toLowerCase())})`);
  const schLine = sch ? `Zone ${Math.round(sch.zone * 100)}% · man ${Math.round(sch.man * 100)}% · single-high (Cover 1/3) ${Math.round(sch.mofc * 100)}% · two-high or open middle ${Math.round(sch.mofo * 100)}% · blitz ${Math.round(sch.blitz * 100)}% · pressure ${Math.round(sch.pressure * 100)}%` : "";
  const rushLine = rush.length ? rush.map((r) => `${escapeHtml(r.name)} ${r.pressures} pressures${r.status ? ` (${escapeHtml(r.status.toLowerCase())})` : ""}`).join(" · ") : "";
  return `<div class="ms-cov card">
      <div class="ms-cov-head">${teamMark(team, 22)} <b>${escapeHtml(teamName(team))} defense</b></div>
      ${schLine ? `<p class="ms-cov-line"><b>How it covers</b> ${schLine}${scan.scheme_season ? ` <span class="mini">(${escapeHtml(String(scan.scheme_season))} charting)</span>` : ""}</p>` : ""}
      ${nowLine ? `<p class="ms-cov-line"><b>This season</b> ${nowLine}${when}</p>` : ""}
      ${offLine ? `<p class="ms-cov-line"><b>On offense</b> ${offLine}</p>` : ""}
      ${corners ? `<div class="ms-cbs">${corners}</div>` : ""}
      ${out.length ? `<p class="ms-cov-line"><b>Out</b> ${out.join(", ")}</p>` : ""}
      ${rushLine ? `<p class="ms-cov-line"><b>Pass rush</b> ${rushLine}</p>` : ""}
    </div>`;
}

/* HIS QUARTERBACK, ON HIS READ. Ethan, 2026-09-28, on Colston Loveland with
   Caleb Williams out: "are we using that in our picks … I don't see it
   displayed here like it's a factor for these players." It was used where
   it was measured (engine/qbchange: behind a downgrade a team's receivers
   lost ~10% of their yards and ~9% of their catches, every season 2022-25;
   tight ends, backs and touchdowns did not move enough to price) — and the
   read said none of it. Now it says who is throwing and what that did to
   this player's numbers, in the terms the board used. */
function scanQbLine(x) {
  const cards = ((state.data || {}).qb_changes) || [];
  const c = cards.find((k) => k && k.team === x.team);
  if (!c) return "";
  const pos = String(x.pos || "").toUpperCase();
  let what;
  if (c.status === "RETURNS") what = "His usual quarterback is back — nothing adjusted.";
  else if (pos === "QB") what = c.replacement && x.player === c.replacement
    ? `Starting in place of ${escapeHtml(c.starter)}.` : "";
  else if (pos === "WR" && c.tier === "downgrade")
    what = "Behind a quarterback this far below the starter, receivers lost about 10% of their yards and 9% of their catches over four seasons — taken off his numbers.";
  else if (pos === "WR")
    what = "The quarterback coming in has thrown like the starter, so his numbers are left as they are.";
  else if (pos === "RB")
    what = "Over five seasons (2021–25) teams behind a replacement ran only about 3% more often and their backs’ carries and yards did not move, so his numbers are left alone. His touchdown chance still moves with the points his team is expected to score, which the lines set with the new quarterback in.";
  else if (pos === "TE")
    what = "Tight ends are the exception: behind a backup their catches rose about 5% over five seasons (2021–25) — the short, safe throw — but not by enough to price, so his numbers are left alone. His touchdown chance still moves with the points his team is expected to score, which the lines set with the new quarterback in.";
  else
    what = "Over four seasons a quarterback change did not move these numbers enough to price, so his are left alone. His touchdown chance still moves with the points his team is expected to score, which the lines set with the new quarterback in.";
  // THE TEAM'S OWN VOLUME, on every read of every team with a change
  // (Ethan, 2026-09-28: "you should do it for all the teams") — so "they'll
  // be losing and throw more" meets what those teams actually did.
  const vol = c.status !== "RETURNS" && c.volume ? `<span class="ms-read-qb-vol">${escapeHtml(c.volume)}.</span>` : "";
  return `<p class="ms-read-qb"><b>QB change:</b> ${escapeHtml(c.headline || "")}${what ? ` — ${what}` : ""}${vol ? ` ${vol}` : ""}</p>`;
}

function scanReadHTML(x) {
  const bits = scanUsageBits(x);
  const door = scanDoor(x);
  return `<div class="ms-read ${escapeHtml(x.read)}"${door.attrs}>
      <button type="button" class="ms-read-head"${door.attrs}>${playerAvatar(x.player, x.team, { size: 36, headshot: x.headshot })}
        <span class="ms-read-who"><b>${escapeHtml(x.player)}</b>
          <span>${escapeHtml(teamName(x.team))} ${escapeHtml(x.pos)}${bits.length ? ` · ${bits.join(" · ")}` : ""}</span></span>
        <span class="ms-read-tag ${SCAN_READ_TONE[x.read] || ""}">${escapeHtml(x.label)}</span></button>
      ${scanPickHTML(x)}${scanTdHTML(x)}
      ${scanQbLine(x)}
      ${scanWhyList(x)}
      <span class="ms-open">Open ${escapeHtml(door.what)} →</span>
    </div>`;
}

function scanMicroHTML(m) {
  const door = scanDoor({ player: m.player, team: m.team }, m.market);
  return `<div class="ms-micro"${door.attrs} role="link" tabindex="0">
      <span class="ms-micro-bet"><b>${escapeHtml(m.player)}</b> ${escapeHtml(m.side || "")} ${escapeHtml(String(m.line ?? ""))} ${escapeHtml(m.market_label || m.market || "")}</span>
      <span class="ms-micro-price">${m.odds != null ? american(m.odds) : "—"}${m.book ? ` · ${escapeHtml(m.book)}` : ""}</span>
      <span class="ms-micro-p">${m.prob != null ? wholePct(m.prob) : "—"}</span>
      ${m.clears || m.edge_pick ? `<span class="ms-micro-tags">${m.clears ? `<span class="chip up">clears 65% · −250</span>` : ""}${
        m.edge_pick ? `<span class="chip up">edge pick</span>` : ""}</span>` : ""}
    </div>`;
}

/* THE GAME PLAN (engine/gameplan; Ethan, 2026-09-27: "focus on the way
   the ai thinks and finds its bets … the steps it goes through"). One
   game read in a bettor's order: the line and the script, who is out and
   where the work goes, the matchup, the plays that fit (volume first —
   catches and touchdowns are bets on a role), the plays to avoid, what
   changes the read before kickoff, and where our raw number disagrees
   with the market (named, never staked, on paper). Every row is one the
   board already prices; the plan is the order they are read in. Paid,
   like the reads: locked, the section says what it is. */
function gamePlanFor(g) {
  const d = state.data || {};
  return (d.game_plans || []).find((p) => p && p.away === g.away && p.home === g.home) || null;
}
function planRowHTML(r, kind) {
  const td = r.kind === "td" || r.market === "anytime_td";
  /* The read's tag rides only on a fit: on an avoid or a gap row the
     scan's "good matchup" beside "chasing last week" reads as a quarrel. */
  const base = kind === "fits" ? r : { ...r, no_read_tag: true };
  const shown = td ? { ...base, line: null, market_label: `Anytime TD${r.label ? ` · ${r.label}` : ""}` }
    : { ...base, market_label: `${r.market_label || r.market}${kind === "fits" && r.label ? ` · ${r.label}` : ""}` };
  const row = likelyRow(shown);
  const why = Array.isArray(r.why) ? r.why : r.why ? [r.why] : [];
  const tag = kind !== "fits" ? "" : r.on_board
    ? `<span class="chip up">${escapeHtml(r.tier_label || "on the Most Likely board")}</span>`
    : `<span class="chip">the read’s play — not on the board</span>`;
  return `<div class="sc-row gplan-row ${kind}">${td ? row.replace(/ data-open="[^"]*"/g, "") : row}
    ${tag || why.length ? `<ul class="sc-lines">${tag ? `<li class="gplan-tag">${tag}</li>` : ""}${
      why.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>` : ""}</div>`;
}
function gamePlanHTML(g, opts) {
  const d = state.data || {};
  const p = gamePlanFor(g);
  const locked = !p && d.locked && d.locked.game_plans && g.scan && g.scan.units;
  if (!p && !locked) return "";
  /* WITH THE GAME REPORT ON THE PAGE the plan keeps only its plays: the
     line, who is out, the matchup and what changes the read are the
     report's own sections, written out (one copy of everything). */
  const skip = new Set((opts && opts.skip) || []);
  const head = `<div class="section-title">Game plan
      <span class="sub">— ${skip.size ? "the plays; the read behind them is the game report above"
        : "this game read in order: the line, who is out, the matchup, the plays that fit, the plays to avoid, what changes the read, who scores"}</span></div>`;
  if (locked) {
    return `<div id="gp-sec-plan" class="ms gplan">${head}<div class="card ms-locked"><b>The game plan</b> —
      the seven steps, the plays that fit and the plays to avoid with our chance on each, is part of the
      subscription.</div></div>`;
  }
  const by = {};
  (p.steps || []).forEach((s) => { if (s && s.key && !skip.has(s.key)) by[s.key] = s; });
  const step = (s, body) => !s || !body ? "" : `<div class="card gplan-step gplan-${escapeHtml(s.key)}">
      <div class="ms-sub">${escapeHtml(s.title)}</div>${body}${s.note ? `<p class="ms-note">${escapeHtml(s.note)}</p>` : ""}</div>`;
  const lines = (s) => s && (s.lines || []).length
    ? `<ul class="gplan-lines">${s.lines.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>` : "";
  const people = (s) => s && (s.rows || []).length ? s.rows.map((i) => `<div class="ms-inj-row">${
      i.player ? playerAvatar(i.player, i.team, { size: 32, headshot: i.headshot })
        : `<span class="gplan-wx">${icon("cloud", 18)}</span>`}
      <span class="ms-inj-who"><b>${escapeHtml(i.player || "Weather")}</b>${i.team
        ? ` <span class="mini">${escapeHtml(i.team)} ${escapeHtml(i.position || "")}</span>` : ""}
        ${i.status && i.status !== "weather" ? `<span class="chip ${String(i.status).toUpperCase() === "QUESTIONABLE"
          ? "" : "down"}">${escapeHtml(String(i.status).toLowerCase())}</span>` : ""}</span>
      <span class="ms-inj-opens">${escapeHtml(i.opens || i.text || "")}</span></div>`).join("") : "";
  const rows = (s, kind) => s && (s.rows || []).length
    ? `<div class="ml-rows">${s.rows.map((r) => planRowHTML(r, kind)).join("")}</div>` : "";
  const note = (t) => `<p class="ms-note">${t}</p>`;
  return `<div id="gp-sec-plan" class="ms gplan">${head}
    ${step(by.line, lines(by.line))}
    ${step(by.out, people(by.out) || note("Nobody of note is out or questionable."))}
    ${step(by.matchup, lines(by.matchup))}
    ${step(by.who, rows(by.who, "who"))}
    ${step(by.fits, rows(by.fits, "fits") || note("No play fits today: no read of this game leans a side where our number agrees at 55% or better at a price worth laying."))}
    ${step(by.avoid, rows(by.avoid, "avoid"))}
    ${step(by.watch, people(by.watch))}
    ${step(by.gap, rows(by.gap, "gap"))}
  </div>`;
}
function gameReportFor(g) {
  const d = state.data || {};
  if (_grFailed) return null;
  return (d.game_reports || []).find((r) => r && r.away === g.away && r.home === g.home) || null;
}
function gameReportHTML(g, extras) {
  const d = state.data || {};
  const r = gameReportFor(g);
  // Every league's board writes a report for every game it holds
  // (engine/gamereport, engine/leaguereport), so a locked board teases
  // each of them.
  const locked = !r && !_grFailed && d.locked && d.locked.game_reports;
  if (!r && !locked) return "";
  if (window.QBReport) return window.QBReport.html(r, extras);
  const id = state.gameId;
  loadReport().then(() => { if (state.view === "game" && state.gameId === id) renderGamePage(); });
  return `<div id="gp-sec-report" class="gr"><p class="loading">Loading the game report…</p></div>`;
}

function matchupScanHTML(g) {
  const scan = g && g.scan;
  if (!scan || !scan.units) return "";
  const away = g.away, home = g.home;
  const d = state.data || {};
  const reads = (d.scan_reads || {})[`${away}@${home}`];
  const locked = !reads && d.locked && d.locked.scan_reads;
  const u0 = (scan.units || {})[home] || (scan.units || {})[away] || {};
  const blend = u0.blend != null && u0.games ? `After ${u0.games} game${u0.games === 1 ? "" : "s"}, the big number is ${Math.round(u0.blend * 100)}% this season and ${100 - Math.round(u0.blend * 100)}% last season — the mix that best predicted the rest of a season when we tested it. “This season” under it is this season on its own.` : "";
  /* ONE LIST OF MISMATCHES. The game plan's "The matchup" step says the
     scan's top three edges (engine/gameplan.matchup_lines); with a plan on
     the page this box keeps only the ones after them — Ethan, 2026-09-28:
     "remove the other duplicate the same way." */
  const planOn = !!gamePlanFor(g);
  const edges = (scan.edges || []).slice(planOn ? 3 : 0, 5);
  /* ONE INJURY LIST. The game plan's "Who is out, and where the work goes"
     step is built from these same rows (engine/gameplan.absences), so with
     a plan on the page this card was the list twice — Ethan, 2026-09-28,
     PHI@CHI: "We show the injuries twice." Without a plan (locked, or none
     built) the scan keeps its own. */
  const inj = planOn ? [] : (scan.injuries || []);
  const players = (reads && reads.players) || [];
  const micro = (reads && reads.microscope) || [];
  const n = scanTeams(scan);
  const adjusted = ((scan.method || {}).opponent_adjusted) !== false;
  const cov = scanCoverageHTML(scan, away) + scanCoverageHTML(scan, home);
  return `<div id="gp-sec-scan" class="ms">
    <div class="section-title">Matchup scan
      <span class="sub">— where each side is strong and weak, who could shine and who could struggle</span></div>
    ${scanTapeHTML(scan, away, home)}
    ${/* WHO THE BOOKS TOOK DOWN before kickoff (engine/pricedplayers):
          Zay Flowers, 2026-09-26, off every book while the report still
          read Questionable. No read for them below, and this says why. */
      (scan.pulled || []).length ? `<p class="ms-note ms-pulled"><b>Taken down by the books:</b> ${
        escapeHtml(scan.pulled.join(", "))} — priced in an earlier pull and on no book now, before kickoff.
        Treated as out: no read for ${scan.pulled.length === 1 ? "him" : "them"} below, until the report or the books say otherwise.</p>` : ""}
    <p class="ms-note">Ranked 1–${n}, 1 best, ${adjusted ? "adjusted for the opponents each team has faced"
      : "not adjusted for schedule, so a soft schedule flatters a unit"}. ${escapeHtml(blend)}</p>
    ${edges.length ? `<div class="card ms-edges"><div class="ms-sub">${planOn ? "More mismatches" : "Biggest mismatches"}</div>
      <ul>${edges.map((e) => { const [who, what] = scanEdgeLine(e);
        return `<li class="${e.gap > 0 ? "off" : "def"}"><b>${escapeHtml(who)}</b> — ${escapeHtml(what)}</li>`; }).join("")}</ul></div>` : ""}
    ${inj.length ? `<div class="card ms-inj"><div class="ms-sub">Injuries and what they open</div>
      ${inj.map((i) => `<div class="ms-inj-row">${playerAvatar(i.player, i.team, { size: 32, headshot: i.headshot })}
        <span class="ms-inj-who"><b>${escapeHtml(i.player)}</b> <span class="mini">${escapeHtml(i.team || "")} ${escapeHtml(i.position || "")}</span>
          <span class="chip ${i.status === "QUESTIONABLE" ? "" : "down"}">${escapeHtml(i.status.toLowerCase())}</span></span>
        <span class="ms-inj-opens">${escapeHtml(i.opens || "")}</span></div>`).join("")}</div>` : ""}
    ${cov ? `<div class="ms-cov-row">${cov}</div>` : ""}
    ${players.length ? `<div class="ms-sub ms-sub-top">Who could shine, who could struggle</div>
      <div class="ms-reads">${players.map(scanReadHTML).join("")}</div>` : locked
      ? `<div class="card ms-locked"><b>Who could shine and who could struggle</b> — a read on every player with a prop,
          with the reasons for and against, is part of the subscription.</div>` : ""}
    ${micro.length ? `<div class="card ms-micros"><div class="ms-sub">Props under the microscope</div>
      <p class="ms-note">The markets the good reads point at, as this board prices them, likeliest first.</p>
      ${micro.map(scanMicroHTML).join("")}</div>` : ""}
    <p class="ms-note">${adjusted
      ? `Each player read counts only what the model measured to predict: his share of the work, what this
      defense gives up in the bet’s own stat, and the points the lines expect his team to score — the same
      numbers already inside our chances, so the scan moves none of them. The rest is shown as “also
      noticed”: pressure, unit rankings, missed tackles, a starting corner out, a receiver’s zone-or-man
      split. Tested against the NFL’s 2022–2025 games, none predicted a player’s line beyond those. Coverage
      and pass-rush counts are this season’s (Pro Football Reference, via nflverse); man and zone rates come
      from the newest season charted.`
      : `None of this moves our numbers: the NFL versions of these reasons, tested against four seasons,
      added nothing to the model, and the college ones have not been measured. College units are
      CollegeFootballData’s advanced season numbers with garbage time taken out; there is no public
      coverage charting for college.`}</p>
  </div>`;
}

/* THE MLB MATCHUP SCAN on the game page (engine/mlb/scan; Ethan,
   2026-09-26: "who's going to struggle and who's going to do good ... left
   hand and right hand"). Each starter against the other lineup — his hand,
   strikeout rate, expected ERA and the slugging he allows to lefties and
   righties — the pens, the park, the wind and the umpire; then the read on
   every hitter and starter, in the football scan's own rows. */
function mlbScanHTML(g) {
  const t = g && g.mlb_tape;
  if (!t || !t.sides) return "";
  const d = state.data || {};
  const reads = (d.scan_reads || {})[`${g.away}@${g.home}`];
  const locked = !reads && d.locked && d.locked.scan_reads;
  const players = (reads && reads.players) || [];
  const pct = pctOr;
  const slg = (x) => x == null ? "—" : `.${Math.round(x * 1000)}`;
  const side = (team) => {
    const s = t.sides[team] || {}, sp = s.starter;
    const opp = team === g.home ? g.away : g.home;
    const lineK = (t.sides[opp] || {}).k_rate;
    const vh = (t.sides[opp] || {}).vs_hand;
    return `<div class="card mlb-tape-side">
      <div class="ms-sub">${escapeHtml(teamName(team))}</div>
      ${sp ? `<div class="mlb-tape-row"><b>${escapeHtml(sp.name)}</b> <span class="mini">${escapeHtml(sp.throws || "")}HP</span></div>
        <div class="mlb-tape-row">Strikes out ${pct(sp.k_rate)} · expected ERA ${Number(sp.xera).toFixed(2)}</div>
        <div class="mlb-tape-row">Slugging allowed: lefties ${slg(sp.slg_vs_l)} · righties ${slg(sp.slg_vs_r)}</div>
        ${s.mix ? `<div class="mlb-tape-row">Throws ${escapeHtml(s.mix)}</div>` : ""}
        <div class="mlb-tape-row">Facing a lineup that strikes out ${pct(lineK)}${vh ? ` and hits ${escapeHtml(vh.hand)}HP ${
          vh.factor >= 1 ? "+" : "−"}${Math.abs(Math.round((vh.factor - 1) * 100))}% vs its usual (${vh.hitters} hitters measured)` : ""}</div>`
        : `<div class="mlb-tape-row mini">Starter not announced yet</div>`}
      <div class="mlb-tape-row mini">Bullpen${s.pen_rank ? ` ranks ${s.pen_rank}` : ""}${
        s.pen_fatigue != null ? ` · ${Number(s.pen_fatigue).toFixed(1)} relief innings the last two days` : ""}</div>
    </div>`;
  };
  const env = [];
  if (t.park) env.push(`${escapeHtml(t.park.name)}: home runs ${Math.round((t.park.hr - 1) * 100) >= 0 ? "+" : ""}${Math.round((t.park.hr - 1) * 100)}%`);
  if (t.weather && !t.weather.roof_closed && t.weather.wind_mph) env.push(`wind ${Math.round(t.weather.wind_mph)} mph ${escapeHtml(t.weather.wind || "")}`);
  if (t.weather && t.weather.roof_closed) env.push("closed roof");
  if (t.umpire && t.umpire.name) env.push(`plate umpire ${escapeHtml(t.umpire.name)}`);
  return `<div id="gp-sec-scan" class="ms">
    <div class="section-title">Matchup scan
      <span class="sub">— each starter against the other lineup, and who could shine or struggle</span></div>
    <div class="mlb-tape">${side(g.away)}${side(g.home)}</div>
    ${env.length ? `<p class="ms-note">${env.join(" · ")}</p>` : ""}
    ${players.length ? `<div class="ms-sub ms-sub-top">Who could shine, who could struggle</div>
      <div class="ms-reads">${players.map(scanReadHTML).join("")}</div>` : locked
      ? `<div class="card ms-locked"><b>Who could shine and who could struggle</b> — a read on every hitter and
          starter, with the reasons for and against, is part of the subscription.</div>` : ""}
    <p class="ms-note">None of this moves our numbers: every piece — the hitter’s own split against this hand,
      the slugging the starter allows to his side, expected stats, the park by the batter’s hand, the wind,
      the pens and the umpire — is already inside the model’s chance. The read picks a side; career numbers
      against tonight’s starter are shown and never counted, the samples are too small.</p>
  </div>`;
}

/* THE NHL MATCHUP SCAN on the game page (engine/nhl/scan; Ethan,
   2026-10-03: "the who could do good and who could struggle and all that").
   Scalpy NHL 1.0's order: each side's probable starter first (goals saved
   above expected when the shot model has him), then goals, shots and 5-on-5
   expected goals for and against a game with their league ranks, rest and
   the expected goals; who is out; then the read on every key skater and both
   starters, in the football scan's own rows. */
function nhlScanHTML(g) {
  const t = g && g.nhl_tape;
  if (!t || !t.sides) return "";
  const d = state.data || {};
  const reads = (d.scan_reads || {})[`${g.away}@${g.home}`];
  const locked = !reads && d.locked && d.locked.scan_reads;
  const players = (reads && reads.players) || [];
  const n = t.teams || 32;
  const num = (v, dp = 2) => (v == null || !isFinite(Number(v)) ? "—" : Number(v).toFixed(dp));
  const rk = (r) => (r ? ` <span class="mini">${r} of ${n}</span>` : "");
  const sv = (v) => (v == null ? "" : ` · .${String(Math.round(Number(v) * 1000)).padStart(3, "0")} save rate`);
  const side = (team) => {
    const s = t.sides[team] || {}, r = s.ranks || {};
    const inj = (s.injuries || []).slice(0, 4);
    return `<div class="card mlb-tape-side">
      <div class="ms-sub">${escapeHtml(teamName(team))}</div>
      <div class="mlb-tape-row">${s.starter ? `<b>${escapeHtml(s.starter)}</b>${sv(s.starter_sv)}${
        s.starter_gsax != null ? ` · ${Number(s.starter_gsax) > 0 ? "+" : ""}${num(s.starter_gsax, 1)} saved above expected` : ""}${
        s.starter_sure ? "" : ` <span class="chip">not settled</span>`}` : `<span class="mini">Starter not known yet</span>`}</div>
      <div class="mlb-tape-row">Goals a game ${num(s.gf)}${rk(r.gf)} · allowed ${num(s.ga)}${rk(r.ga)}</div>
      <div class="mlb-tape-row">Shots a game ${num(s.sog_for, 1)}${rk(r.sog_for)} · allowed ${num(s.sog_against, 1)}${rk(r.sog_against)}</div>
      ${s.xgf_ev != null ? `<div class="mlb-tape-row">5-on-5 expected goals ${num(s.xgf_ev)}${rk(r.xgf_ev)} · allowed ${num(s.xga_ev)}${rk(r.xga_ev)}</div>` : ""}
      ${s.xg != null ? `<div class="mlb-tape-row">Expected tonight: ${num(s.xg)} regulation goals</div>` : ""}
      ${s.b2b ? `<div class="mlb-tape-row"><span class="chip down">second night of a back-to-back</span></div>` : ""}
      ${inj.length ? `<div class="mlb-tape-row mini">Injury report: ${inj.map((i) => `${escapeHtml(i.player)} (${escapeHtml(String(i.status || "").toLowerCase())})`).join(", ")}</div>` : ""}
    </div>`;
  };
  const s0 = t.sides[g.home] || t.sides[g.away] || {};
  const blend = s0.season_weight != null && s0.gp_season
    ? `After ${s0.gp_season} game${s0.gp_season === 1 ? "" : "s"} this season, team strength is ${Math.round(s0.season_weight * 100)}% this season and ${100 - Math.round(s0.season_weight * 100)}% last season — early nights lean on the bigger sample.` : "";
  return `<div id="gp-sec-scan" class="ms">
    <div class="section-title">Matchup scan
      <span class="sub">— the starters, each side’s goals and shots, and who could shine or struggle</span></div>
    <div class="mlb-tape">${side(g.away)}${side(g.home)}</div>
    ${(t.pulled || []).length ? `<p class="ms-note ms-pulled"><b>Taken down by the books:</b> ${
      escapeHtml(t.pulled.join(", "))} — priced earlier, on no book now. Treated as out: no read below.</p>` : ""}
    ${blend ? `<p class="ms-note">${escapeHtml(blend)}</p>` : ""}
    ${players.length ? `<div class="ms-sub ms-sub-top">Who could shine, who could struggle</div>
      <div class="ms-reads">${players.map(scanReadHTML).join("")}</div>` : locked
      ? `<div class="card ms-locked"><b>Who could shine and who could struggle</b> — a read on every key skater and
          both starters, with the reasons for and against, is part of the subscription.</div>` : ""}
    <p class="ms-note">None of this moves our numbers: the opposing starter, the shots each side gives up,
      the expected goals and rest are already inside the model’s chance. The read picks a side for the Most
      Likely board, and a player who is out — on the report or taken down by every book — gets no read.</p>
  </div>`;
}

/* THE NBA MATCHUP SCAN on the game page (engine/nba/scan; Ethan, 2026-10-20:
   "offense vs defense ... matchup details ... key matchups and breakout
   players"). The engine formats the tape's rows — scoring, the ratings per
   100, pace, shooting, the threes, the glass, the turnovers, each with its
   rank — and writes the key matchups and the basis; this draws them in the
   football tape's own cells, then the reads. */
function nbaScanHTML(g) {
  const t = g && g.nba_tape;
  if (!t || !(t.rows || []).length) return "";
  const d = state.data || {};
  const reads = (d.scan_reads || {})[`${g.away}@${g.home}`];
  const players = (reads && reads.players) || [];
  const n = t.teams || 30;
  const cell = (v, r, plain) => `<span class="tp-cell ${plain ? "" : (tapeTier(r, n) || [""])[0]}"><b>${escapeHtml(v)}</b>${r ? `<em>${ordinal(r)}</em>` : ""}</span>`;
  const head = (tm) => `<span class="tp-team">${teamMark(tm, 22)}<b>${escapeHtml(teamName(tm))}</b></span>`;
  return `<div id="gp-sec-scan" class="ms">
    <div class="section-title">Matchup scan <span class="sub">— offense against defense, and who could shine or struggle</span></div>
    <div class="card ms-tape"><div class="tp-row tp-head"><span class="tp-k">Rank of ${n}</span>${head(g.away)}${head(g.home)}</div>
      ${t.rows.map((r) => `<div class="tp-row"><span class="tp-k">${escapeHtml(r.label)}</span>${cell(r.a, r.ar, r.plain)}${cell(r.h, r.hr, r.plain)}</div>`).join("")}</div>
    ${(t.edges || []).length ? `<div class="card ms-edges"><div class="ms-sub">Key matchups</div>
      <ul>${t.edges.map((e) => `<li class="${e.tone === "def" ? "def" : "off"}">${escapeHtml(e.text)}</li>`).join("")}</ul></div>` : ""}
    ${t.note ? `<p class="ms-note">${escapeHtml(t.note)}</p>` : ""}
    ${players.length ? `<div class="ms-sub ms-sub-top">Who could shine, who could struggle</div>
      <div class="ms-reads">${players.map(scanReadHTML).join("")}</div>` : !reads && d.locked && d.locked.scan_reads
      ? `<div class="card ms-locked"><b>Who could shine, who could struggle, who could break out</b> — a read on every
          key player, with the reasons for and against, is part of the subscription.</div>` : ""}
    <p class="ms-note">${escapeHtml(t.basis || "")}</p>
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
      <button class="btn ghost gp-back" id="gp-back" style="margin-top:14px">${escapeHtml(detailBackLabel())}</button>`;
    const b = document.getElementById("gp-back");
    if (b) b.addEventListener("click", detailBack);
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
  const shown = props.filter((r) => (state.gameShowAll ? true : r._ok));
  const bets = (state.data.game_bets || [])
    .map((b) => ({ ...b, _ok: passesGameBet(b) }))
    .filter((b) => b.home === g.home && b.away === g.away);
  const betsShown = bets.filter((b) => (state.gameShowAll ? true : b._ok));
  const shots = (state.data.long_shots || []).filter((r) => propInGame(r, g));
  /* THE OTHER BOARD, WHICH THIS PAGE HAS NEVER DRAWN. Ethan, 2026-09-09,
     looking at the Week 1 opener: "when you click on a game on the
     reccomended page and u scroll down to the reccomended props, is that
     showing just edge bets? if so, we need to show both edge bets and
     most likley bets."

     It was. `recommendations`, `game_bets` and `long_shots` are all one
     book — the edge book — and the likelihood board was never read here
     at all. On NE/SEA that meant a page showing one prop while two of
     its players sat on the Most Likely board, with nothing on screen to
     say the other rows existed.

     ITS OWN SECTION, AND OUT OF THE HEADLINE COUNT. The two books do not
     share a record and must not (tests/test_books_never_bleed.py); a
     page that adds them into one "Recommended" number is exactly where
     that separation would start to rot. So the tile is separate, the
     section is separate, and the wording says which book you are looking
     at — the same way Long shots already does.

     `showableLikelyRow` is the gate the Most Likely page itself applies,
     so a row refused there is refused here rather than surfacing on a
     page nobody thought to re-check. */
  const gameLikely = (state.data.most_likely || [])
    .filter(showableLikelyRow)
    .filter((r) => propInGame(r, g));
  const likelies = oneBoardOn() ? [] : gameLikely.filter((r) => !likelyDropped(r));
  // …the ones whose chance has fallen under the bar since (likelyDropped)…
  const droppedHere = gameLikely.filter(likelyDropped);
  // …and this game's picks that came off the board, with why (likelyPulled).
  const pulled = likelyPulled().filter((e) => (e.kind === "game"
    ? [e.home, e.away].includes(g.home) && [e.home, e.away].includes(g.away)
      || e.matchup === `${g.away} @ ${g.home}`
    : propInGame(e, g)));
  // The old shelf's two folds (dropped, pulled), counted once for the
  // jump row and the heading below.
  const offHere = droppedHere.length + pulled.length;

  // The header re-uses the same art the strip card draws, at full width.
  const art = mlb ? ballpark(g) : nba ? court(g) : state.sport === "nhl" ? rink(g) : stadium(g);
  const cond = nba ? "Indoor hardwood" : state.sport === "nhl" ? "Indoor ice"
    : w.dome ? "Indoor"
    // Same rule as the strip card: an unmeasured prior is not a forecast.
    : w.measured === false ? "Outdoor · weather not pulled"
    : `${Math.round(w.temp_f)}°F · ${Math.round(w.wind_mph)}mph${w.wind_dir ? " " + w.wind_dir : ""}${
      isLive || isFinal ? "" : mlb ? " · first-pitch forecast" : " · kickoff forecast"}`;
  const gpLines = gameMarketsHTML(g, { mlb, isFinal, open: true });
  const gpCrowd = isFinal ? "" : crowdStripHTML(g);
  const gpMoney = isFinal ? "" : gameMoneyHTML(g);
  const gpScripts = gameScriptsHTML(g, likelies);
  const score = (side) => (live.home_score != null && (isLive || isFinal))
    ? `<b class="score">${side === "home" ? live.home_score : live.away_score}</b>` : "";

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
  // The board card's own tag, so the strip and the page behind it can
  // never disagree about the venue.
  const gpPhoto = venuePhotoTag(state.sport, g.home, (window.ACTIVE_TEAMS || {})[g.home] || {});
  // The render's GAME LINES table and KEY INSIGHTS panel. Lines come
  // straight off the slate; a cell without a real price shows a dash.
  // Insights are the game's own data fields, not narratives.
  const gpFav = g.favorite || g.home;
  const gpSp = (side) => g.spread == null ? "—"
    : `${side === gpFav ? "−" : "+"}${Math.abs(g.spread).toFixed(1)}`;
  const gpMl = (v) => v == null ? "—" : oddsTxt(v);
  // NOT TWICE (the 2026-09-27 sweep): the hero already draws these three
  // markets (gpLines, the Home card's grid) for any game not yet final,
  // and the card below repeated the same six numbers straight under it.
  // It stays for a finished game, where the hero draws none.
  const linesCard = !gpLines && (g.spread != null || g.total != null
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
  if (g.lineups_confirmed === false) notes.push(lineupPendingWords(g));
  if (mlb && f.hr >= 1.05) notes.push(`Park boosts home runs +${Math.round((f.hr - 1) * 100)}%`);
  if (mlb && f.hr && f.hr <= 0.95) notes.push(`Park suppresses home runs ${Math.round((f.hr - 1) * 100)}%`);
  // The wind is not repeated here: the hero's conditions chip (`cond`)
  // prints it for every measured outdoor game, and the weather panel
  // under it says what the model did with it.
  if (!w.dome && w.measured !== false && (w.precip_chance || 0) >= 0.4) notes.push(
    `${Math.round(w.precip_chance * 100)}% precipitation chance`);
  if (g.doubleheader) notes.push(`Doubleheader — game ${g.game_number || 1}`);
  /* THE BULLPENS AND THE INJURED LIST (the site audit, 2026-09-24, L-7).
     Both were on every MLB board and drawn nowhere: the pen's season rank
     and its two-day workload are inputs to every hitter on this page
     (engine/mlb/bullpen.pen_multiplier), and a tired pen is the thing a
     bettor would most want said. Rank 1 is the best pen; a workload of
     6+ weighted relief innings is where the model starts to move. */
  if (mlb) notes.push(...mlbPenNotes(g));
  if (mlb) {
    const il = new Set(state.data.injured_list || []);
    const out = [...new Set(props.filter((r) => il.has(r.player)).map((r) => r.player))];
    if (out.length) notes.push(`On the injured list: ${out.slice(0, 4).join(", ")}${
      out.length > 4 ? ` and ${out.length - 4} more` : ""} — never a pick until activated`);
  }
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
    /* WHICH SEASONS (2026-09-27). The build blends this season with last
       at the matchup scan's split (engine/teamshape.blended_shapes); the
       label says how much of each team's shape is this season. An older
       payload with one season still reads as it did. */
    const thisPct = (x) => x.blend ? Math.round(((x.blend.off + x.blend.def) / 2) * 100) : null;
    const sub = _sh.blend && _sa.blend
      ? `— ${season} blended with ${Number(season) - 1}, league percentiles · ${escapeHtml(g.home)} ${
          thisPct(_sh)}% this season (${plural(_sh.games, "game")}), ${escapeHtml(g.away)} ${
          thisPct(_sa)}% (${plural(_sa.games, "game")})`
      : `— ${season} measured profile, league percentiles (${_sh.games} and ${_sa.games} finals)`;
    const rows = axes.map((a) => `<tr><td>${names[a]}</td>
      <td class="num">${Number(_sh.pct[a]).toFixed(0)}</td>
      <td class="num">${Number(_sa.pct[a]).toFixed(0)}</td></tr>`).join("");
    return `
    <div class="card gp-shape"><div class="gp-panel-title">Team shapes
        <span class="gp-panel-sub">${sub}</span></div>
      <div class="gp-shape-radar" data-echart-radar="${escapeAttr(JSON.stringify({
        axes: axes.map((a) => names[a]),
        series: [
          { name: g.home, values: axes.map((a) => Number(_sh.pct[a]) || 0) },
          { name: g.away, values: axes.map((a) => Number(_sa.pct[a]) || 0) },
        ],
      }))}"><table class="agate gp-shape-tbl"><thead><tr><th></th>
          <th>${escapeHtml(g.home)}</th><th>${escapeHtml(g.away)}</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <p class="gp-sim-note">${_sh.blend ? `Percentile against the whole league on this
        season and last, blended the way the matchup scan blends its ranks — this
        season counting for more as its games come in, faster for a new starting QB` : "Percentile against the whole league on last season’s finals"}:
        offense is points scored, defense is points allowed (fewer ranks
        higher), form is the last five margins, home edge is home-minus-road
        margin, steadiness is low variance. Measured shape, not a projection.</p>
    </div>`;
  })() : "";
  /* WATCH, ONLY WHILE THE GAME IS ON (Ethan, 2026-10-07: "We should not
     show the 'watch' button until the game is live"). The fast file can
     know a game is live before the board does, so its row decides. */
  if (!isFinal && typeof fetchAllLive === "function") {
    fetchAllLive().then(() => {
      const slot = document.getElementById("gp-watch-slot");
      const row = liveRowFor(state.sport, g);
      if (slot && row && state.view === "game") {
        slot.innerHTML = (row.live || {}).state === "live" ? watchHTML(row, state.sport, "gp-watch") : "";
      }
    }).catch(() => {});
  }
  /* THE GAME REPORT LEADS WHEN THERE IS ONE (gameReportHTML): the matchup
     scan and the plan's narrative steps step aside, and the replay moves
     into the report's "How the game could go". */
  const report = gameReportFor(g);
  const reportHTML = gameReportHTML(g, { scripts: report && simCard ? simCard : "",
                                         url: cleanURL("game", gameSlug(g)), sport: state.sport });
  const planHTML = gamePlanHTML(g, report ? { skip: ["line", "out", "matchup", "watch"] } : null);
  host.innerHTML = `
    <div class="pp-nav">
      <button class="btn-quiet gp-back" id="gp-back">${escapeHtml(detailBackLabel())}</button>
      <span class="pp-nav-right">
        <span id="gp-pbp-slot"></span>
        ${shareBtn("game", gameSlug(g))}
        ${favBtn(g.away)}${favBtn(g.home)}
      </span>
    </div>
    ${/* THE PICK OF THE DAY'S LOOK (Ethan, 2026-09-24, beside the POTD
          card: "overlay the venue on this part like how we do for the pick
          of the day"). The venue fills the top of the card and fades into
          it; a gold eyebrow, the matchup in the headline serif, the when
          in mono — the potd-hero's dress on the game page's own pieces. */""}
    <div class="gp-hero is-hero">
      <div class="gp-art">${art}${gpPhoto}
        ${mlb && isLive ? runnerOverlay(g) : ""}
        ${isLive ? `<div class="status-badge live"><span class="live-dot"></span>LIVE
          <span class="per">${escapeHtml(live.period || "")}</span></div>` : ""}
        ${isFinal ? `<div class="status-badge final">FINAL</div>` : ""}</div>
      <div class="gp-meta">
        <div class="gp-eyebrow">${icon("stadium", 14)} ${escapeHtml([
          (LEAGUE_LABEL[state.sport] || state.sport || "").toUpperCase(),
          g.week ? `Week ${g.week}` : "", isLive ? "Live" : isFinal ? "Final" : "",
          (g.stadium || {}).name || g.park_name || ""].filter(Boolean).join(" · "))}</div>
        <div class="gp-teams">
          <span>${gpTeamDoor(g.away, g.home)} ${score("away")}</span>
          <span class="gp-at">@</span>
          <span>${gpTeamDoor(g.home, g.away)} ${score("home")}</span>
        </div>
        <div class="gp-sub">${escapeHtml(whenLabel(g.date, g.kickoff))}${inactivesNote(g)}</div>
        <div id="gp-watch-slot">${isLive ? watchHTML(liveRowFor(state.sport, g) || g, state.sport, "gp-watch") : ""}</div>
        ${/* THE CARD'S LINES, ON THE PAGE THE CARD OPENS (Ethan, 2026-09-24,
              circling the spread · ML · total grid on the Home card: "we
              should be showing the info I have circled"). The same
              function draws both, so they cannot disagree; the O/U and
              favourite chips it replaces stay only when it draws nothing. */
          gpLines}
        ${gpCrowd}
        ${gpMoney}
        <div class="chips gp-chips">
          ${g.doubleheader ? `<span class="chip up">${icon("calendar", 11)} Doubleheader · Game ${g.game_number || 1}</span>` : ""}
          ${gpLines ? "" : `<span class="chip">O/U ${g.total != null ? g.total.toFixed(1) : "—"}</span>`}
          ${gpLines ? "" : g.favorite ? `<span class="chip">${escapeHtml(teamName(g.favorite))} −${Math.abs(g.spread).toFixed(1)}</span>`
            : nba && g.spread ? `<span class="chip">${escapeHtml(teamName(g.spread < 0 ? g.home : g.away))} −${Math.abs(g.spread).toFixed(1)}</span>` : ""}
          <span class="chip">${escapeHtml(cond)}</span>
          ${g.roof ? `<span class="chip">${escapeHtml(({ outdoors: "Outdoors", open: "Roof open",
            closed: "Roof closed", dome: "Dome", retractable: "Retractable roof" })[g.roof] || `Roof ${g.roof}`)}</span>` : ""}
          ${g.lineups_confirmed === false ? `<span class="chip">${icon('clock')} ${escapeHtml(lineupPendingWords(g, true))}</span>` : ""}
        </div>
        ${mlb ? parkPanel(g) : nba || state.sport === "nhl" ? "" : stadiumPanel(g)}
      </div>
    </div>

    ${gpJumpHTML([
      linesCard || notesCard ? ["gp-sec-lines", "Lines & insights"] : null,
      reportHTML ? ["gp-sec-report", "Game report"] : null,
      planHTML ? ["gp-sec-plan", "Game plan"] : null,
      !report && ((g.scan && g.scan.units) || g.mlb_tape || g.nhl_tape || g.nba_tape) ? ["gp-sec-scan", "Matchup scan"] : null,
      simCard && !report ? ["gp-sec-replay", "Replay"] : null,
      shapeCard ? ["gp-sec-shapes", "Team shapes"] : null,
      matchupPickCount(g) ? ["gp-sec-matchup", `${oneBoardOn() ? "Most likely" : "Matchup picks"} · ${matchupPickCount(g)}`] : null,
      // ONE "Most likely" CHIP (Ethan, 2026-10-01: "Most likely · 15" beside
      // "Most likely · 0"). With the one board on, the board's section is the
      // chip; this section only holds the pulled/dropped folds, so it is
      // offered only when the board has no picks in this game.
      (oneBoardOn() ? !matchupPickCount(g) && offHere : likelies.length || offHere)
        ? ["gp-sec-likely", `Most likely · ${likelies.length}`] : null,
      gpScripts ? ["gp-sec-scripts", "Game scripts"] : null,
      betsShown.length ? ["gp-sec-bets", `Game bets · ${betsShown.length}`] : null,
      ["gp-sec-props", shown.length ? `Edge picks · ${shown.length}` : "Edge picks"],
      shots.length ? ["gp-sec-shots", `Long shots · ${shots.length}`] : null,
    ])}
    ${linesCard || notesCard ? `<div class="gp-row" id="gp-sec-lines">${linesCard}${notesCard}</div>` : ""}
    ${pressurePairHTML(state.sport, g)}
    ${reportHTML}
    ${planHTML}
    ${report ? "" : matchupScanHTML(g) || mlbScanHTML(g) || nhlScanHTML(g) || nbaScanHTML(g)}
    ${simCard && !report ? `<div id="gp-sec-replay">${simCard}</div>` : ""}
    <div id="gp-lab"></div>
    ${shapeCard ? `<div id="gp-sec-shapes">${shapeCard}</div>` : ""}

    <div class="stats gp-stats">
      <div class="tile"><div class="k">Props analyzed</div><div class="v">${props.length}</div>
        <div class="tile-sub">in this game</div></div>
      <div class="tile"><div class="k">Edge picks</div><div class="v">${props.filter((r) => r._ok).length + bets.filter((b) => b._ok).length}</div>
        <div class="tile-sub">props &amp; game bets that clear the edge bar</div></div>
      <div class="tile"><div class="k">Edge game bets</div><div class="v">${bets.filter((b) => b._ok).length}</div>
        <div class="tile-sub">moneyline, spread, totals</div></div>
      <div class="tile"><div class="k">Most likely</div><div class="v">${
        /* The one board's picks in this game when it is on — the section
           below draws them; `likelies` is the old shelf and is empty then
           (Ethan, 2026-09-27: the tile read 0 above Top picks 2, Strong 12). */
        oneBoardOn() ? matchupPickCount(g) : likelies.length}</div>
        <div class="tile-sub">on the Most Likely board · own book</div></div>
      <div class="tile"><div class="k">Long shots</div><div class="v">${shots.length}</div>
        <div class="tile-sub">${mlb ? "home runs" : nba ? "none for NBA" : state.sport === "nhl" ? "none for NHL" : "anytime TDs"} · tracked separately</div></div>
    </div>

    ${gpMatchupHTML(g)}

    ${likelies.length || offHere ? `<div id="gp-sec-likely">${
        // Under the one board's own section its folds need no second
        // heading; without board picks here, the heading says so.
        oneBoardOn() && matchupPickCount(g) ? ""
        : oneBoardOn() ? `<div class="section-title">Most likely · this game
        <span class="sub">— nothing on the board in this game right now; the picks
        that came off are below</span></div>`
        : `<div class="section-title">Most likely to hit
        <span class="sub">— ranked by how often they land, not by how good the
        price is; kept in its own book, never in the headline record</span></div>`}
      ${likelies.length ? `<div class="cards gp-cards">${likelies.map(likelyCard).join("")}</div>` : ""}
      ${likelyDroppedHTML(droppedHere, { open: !likelies.length })}
      ${likelyPulledHTML(pulled, { title: "Pulled from this game", open: !likelies.length })}</div>` : ""}

    ${gpScripts ? `<div id="gp-sec-scripts"><div class="section-title">How these picks fit together
        <span class="sub">— each pick needs the game to go a certain way; picks that need the
        same game win together, and picks that need opposite games hurt each other in a parlay</span></div>
      ${gpScripts}</div>` : ""}

    ${betsShown.length ? `<div id="gp-sec-bets"><div class="section-title">Game bets
        <span class="sub">— moneyline, spread and totals from the team model</span></div>
      <div class="cards gp-cards">${betsShown.map(gameBetCard).join("")}</div></div>` : ""}

    ${/* THE PRICED GAME MARKETS THIS GAME WAS TURNED DOWN ON. The props
          below have carried this line since they had one; the game
          markets never did, so a game the model priced three ways and
          refused three times rendered as a page with no game section at
          all — indistinguishable from a game no book had posted.
          It matters most on the college board, where `engine.cfb.model`
          promises a Group of Five game is "priced, shown with its number
          and its edge, never a play" and this page is where that promise
          is kept or broken. */""}
    ${bets.length > betsShown.length ? `<p class="list-note" style="margin-top:10px">
      ${plural(bets.length - betsShown.length, "priced game market",
               "priced game markets")} in this game
      ${bets.length - betsShown.length === 1 ? "was" : "were"} turned down
      (no power-conference side, edge under the tier’s bar, or a Pass grade). The
      number and the price are on ${bets.length - betsShown.length === 1
        ? "it" : "them"}; the money is not.
      <button class="btn ghost" id="gp-showbets" type="button"
        >Show ${bets.length - betsShown.length} anyway</button></p>` : ""}

    ${/* THE EDGE PICKS IN THIS GAME, as the Edge page draws them (Ethan,
          2026-09-27, crossing out the old "Player props" cards: "this is
          the old page still hiding in our new stuff") — one row each, the
          price and the EV in the pills, the full card one tap away. */""}
    <div id="gp-sec-props">${shown.length ? `
        <div class="section-title">Edge picks · this game
          <span class="sub">— ${plural(shown.length, "prop", "props")} that clear the edge bar; tap one for the full card</span></div>
        <div class="card" style="padding:0">${shown.map(edgePropRow).sort((a, b) => b.ev - a.ev).map(edgeRowHTML).join("")}</div>`
      : `<div class="empty-slate"><div class="es-icon">${icon("target", 30)}</div>
          <div class="es-title">No player props clear the filters in this game</div>
          <div class="es-sub">Either the model passes on everything here, or books haven’t
          posted prices for it yet.</div>
          ${props.length ? `<button class="btn ghost" id="gp-showall" style="margin-top:12px">
            Show all ${props.length} analyzed ${pluralWord(props.length, "prop")} anyway</button>` : ""}</div>`}</div>

    ${shots.length ? `<div id="gp-sec-shots"><div class="section-title">Long shots
        <span class="sub">— tracked in their own bucket, never in the headline record</span></div>
      <div class="cards gp-cards">${shots.map(longShotCard).join("")}</div></div>` : ""}

    ${props.length > shown.length ? `<p class="list-note" style="margin-top:14px">
      ${plural(props.length - shown.length, "more analyzed prop", "more analyzed props")}
      in this game ${props.length - shown.length === 1 ? "is" : "are"} held
      (edge below the bar, no real price, or lineup unconfirmed).</p>` : ""}

    ${/* THE WAY BACK. The reveal was a one-way flip while the board
          carried a "show non-recommended" checkbox to undo it; that
          checkbox went on 2026-09-14, so the page that turns the reveal
          on is the page that has to turn it off. */""}
    ${state.gameShowAll && props.length ? `<p class="list-note" style="margin-top:14px">
      Showing every prop analyzed for this game, including the ones the model
      passed on. <button class="btn ghost" id="gp-hideall" type="button"
        >Show only the picks</button></p>` : ""}`;

  const back = document.getElementById("gp-back");
  if (back) back.addEventListener("click", detailBack);
  host.querySelectorAll(".gp-jump [data-jump], .gr-toc [data-jump]").forEach((b) =>
    b.addEventListener("click", () => {
      const el = document.getElementById(b.dataset.jump);
      if (el) el.scrollIntoView({ behavior: state.quiet ? "auto" : "smooth", block: "start" });
    }));
  // THE DOOR TO THE PLAY-BY-PLAY, for a game in progress or just over,
  // drawn only once its id has been found in the league's fast
  // scoreboard — a button that opens on "no game selected" is the fake
  // button Ethan's rule is about. The page it opens knows to come back
  // here.
  if ((isLive || isFinal) && LIVE_FAST[state.sport]) {
    const slot = document.getElementById("gp-pbp-slot");
    pbpIdFor(g, state.sport).then((id) => {
      if (!id || !slot || !slot.isConnected) return;
      slot.innerHTML = `<button type="button" class="btn ghost gp-pbp-door" id="gp-pbp-door">${
        isLive ? `<span class="live-dot sm"></span>Watch play-by-play` : "Play-by-play"} →</button>`;
      slot.firstElementChild.addEventListener("click", () => openPbp(state.sport, id, "game"));
    }).catch(() => {});
  }
  // "Go back to the board, find the toggle, come back" was three steps for
  // one intention. The button flips the same global toggle in place.
  // Two buttons, one intention: the props empty-slate's and the game
  // markets' held-note. Both flip the same global toggle in place.
  host.querySelectorAll("#gp-showall, #gp-showbets").forEach((b) =>
    b.addEventListener("click", () => {
      state.gameShowAll = true;
      renderGamePage();
    }));
  const hideAll = host.querySelector("#gp-hideall");
  if (hideAll) hideAll.addEventListener("click", () => {
    state.gameShowAll = false;
    renderGamePage();
  });
  fillMeters(host);
  host.querySelectorAll(".cards").forEach(revealChildren);
  loadExtras().then((X) => X && X.gameLab(document.getElementById("gp-lab"), state.sport, g));
  // The replay panel's gauge + histogram upgrade in place when the
  // vendored ECharts loads; the div bars above stay as the fallback.
  if (typeof mountEChartsPanels === "function") mountEChartsPanels(host);
}

/* The game page's two-team table. Drawn from the cache when the league's
   standings are already in it; otherwise a placeholder that fills
   itself in when the file lands, so the page never waits on it. */
function pressurePairHTML(sport, g) {
  if (_standingsCache[sport] === undefined) {
    loadStandings(sport).then(() => {
      const host = document.getElementById("gp-pressure");
      if (host) host.outerHTML = pressurePairHTML(sport, g);
    });
    return `<div id="gp-pressure" hidden></div>`;
  }
  const pr = (_standingsCache[sport] || {}).pressure;
  if (!pr) return "";
  const rows = [g.away, g.home].map((t) => [t, pr.teams[t]]).filter(([, r]) => r);
  if (!rows.length) return "";
  return `
    <div class="card gp-pressure" id="gp-pressure"><div class="gp-panel-title">Under pressure
        <span class="k">${escapeHtml(String(pr.season_used))} · one-score means within ${
          escapeHtml(pressureUnit(pr))}</span></div>
      <div class="pr-table">
        <span class="lb-th"></span>${PRESSURE_RATES.map(([, t]) =>
          `<span class="lb-th">${t}</span>`).join("")}
        ${rows.map(([t, r]) => `<span class="lb-tm">${teamMark(t, 20)} ${escapeHtml(t)}
            <span class="k">${escapeHtml(r.record)}</span></span>${
          PRESSURE_RATES.map(([k]) => `<b>${pressurePct(r[k])}</b>`).join("")}`).join("")}
      </div>
      ${pr.note ? `<div class="pr-defs">${escapeHtml(pr.note)}</div>` : ""}
      <div class="pr-defs">${PRESSURE_RATES.map(([, t, n]) =>
        `<span><b>${t}</b> ${escapeHtml(n)}</span>`).join("")}</div>
    </div>`;
}

/* ---- Under pressure, live, on the play-by-play page --------------------
   Ethan, 2026-09-08: "I know we added under pressure data for teams, like
   clutch win % and reliability % and comeback % and choke % and see if we
   can have that as live data as well like when games are going. That's
   something we should be showing on the live play by play page yeah? And
   use live data for it where we can."

   The rates are season counts (engine/pressure.py) and do not change
   during a game. What changes is the QUESTION the scoreboard asks of
   them — which is what `pressureSituation` reads for the live card's one
   line, and what this reads every twelve seconds off the deep file's
   live block: the score, the period, the clock, who has the ball. It
   says which rate is being asked of whom and lights those two cells in
   the table; beside them sits the one live number this site holds that
   IS a probability — the live market's de-vigged moneyline, when the
   board tracks it for this game. Nothing here is a model number: a
   clutch rate is a count, and the market's number is the market's. Pure,
   run in node by tests/test_pbp_pressure.py. */
function pressureMoment({ sport, d, boardGame, pr }) {
  const teams = (pr && pr.teams) || {};
  const home = d.home, away = d.away;
  const h = teams[home], a = teams[away];
  if (!h || !a) return null;
  const lv = d.live || {};
  const g = { home, away, live: lv,
              favorite: (boardGame || {}).favorite, spread: (boardGame || {}).spread };
  const line = pressureSituation({ sport, g, pr });
  const live = lv.state === "live" && lv.home_score != null && lv.away_score != null;
  const margin = live ? Math.abs(lv.home_score - lv.away_score) : null;
  const one = live && margin <= (PRESSURE_ONE_SCORE[sport] || 0);
  const late = live && pressureLate(sport, lv.period);
  const fav = pressureFav(g);
  const dog = fav === home ? away : fav === away ? home : null;
  const lead = !live ? null
    : lv.home_score > lv.away_score ? home : lv.away_score > lv.home_score ? away : null;
  // WHICH RATE THE SCOREBOARD IS ASKING, of whom — the same reading the
  // sentence makes, as cells the table can light.
  const asks = [];
  if (live && fav && dog && lead && lead !== fav) {
    asks.push({ team: fav, rate: "reliability" }, { team: dog, rate: "comeback" });
  } else if (one && late && fav && dog) {
    asks.push({ team: fav, rate: "choke" }, { team: dog, rate: "clutch" });
  } else if (one && late) {
    asks.push({ team: home, rate: "clutch" }, { team: away, rate: "clutch" });
  } else if (!live) {
    asks.push({ team: home, rate: "clutch" }, { team: away, rate: "clutch" });
  }
  const chips = [];
  if (live) {
    const unit = sport === "mlb" ? (margin === 1 ? "run" : "runs") : "points";
    chips.push(one ? "one-score game" : `${margin}-${unit.replace(/s$/, "")} game`);
    if (late) chips.push(sport === "mlb" ? "late innings" : "late");
    if (fav && lead && lead !== fav) chips.push(`${fav} trails as the favourite`);
    if (lv.possession) chips.push(`${lv.possession} has the ball`);
  }
  const t = (boardGame || {}).line_track;
  const market = t && t.now != null ? { home, now: t.now, opened: t.opened } : null;
  return { line, asks, chips, live, market, fav, lead, margin, one, late };
}

function pbpModelWinProbHTML(d) {
  /* OUR live read of the game, beside the market's.
   *
   * `engine/livewp` computes this server-side and `livescore_build`
   * copies it onto the row the deep play-by-play file carries, so the
   * maths lives in exactly one place. Writing the normal CDF again in
   * JavaScript is the two-copies-of-one-rule mistake that left baseball
   * game cards with no book name for a fortnight.
   *
   * Absent for good reasons the page does not need to distinguish: a
   * pre-game card, overtime, a clock the feed did not give, or a sport
   * with no measured margin variance. No block, no card — never a
   * neutral 50%, which looks like information and is not.
   */
  const wp = ((d || {}).live || {}).win_prob;
  if (!wp || wp.home_win_prob == null) return "";
  const rows = [[wp.home, wp.home_win_prob], [wp.away, wp.away_win_prob]];
  return `<div class="card pbp-wp">
    <div class="pbp-rail-head">Win probability
      <span class="mini">${escapeHtml(wp.basis)}</span></div>
    ${rows.map(([t, p]) => `<div class="pbp-wp-row">
      <span class="pbp-wp-tm">${escapeHtml(String(t || ""))}</span>
      <span class="pbp-wp-bar"><i style="transform:scaleX(${
        Math.max(0, Math.min(1, Number(p))).toFixed(3)})"></i></span>
      <b>${Math.round(Number(p) * 100)}%</b></div>`).join("")}
    ${wp.possession_blind ? `<p class="mini pbp-wp-blind">${escapeHtml(wp.caveat)}</p>` : ""}
    <p class="mini" style="opacity:.6">Ours, from the score and the clock — not a
      price, and nothing is staked on it.</p>
  </div>`;
}

function pbpPressureHTML(d, league, boardGame) {
  const pr = (_standingsCache[league] || {}).pressure;
  if (!pr) return "";
  const m = pressureMoment({ sport: league, d, boardGame, pr });
  if (!m) return "";
  const teams = pr.teams || {};
  const asked = (t, k) => m.asks.some((x) => x.team === t && x.rate === k);
  const rows = [d.away, d.home].map((t) => [t, teams[t] || {}]);
  return `<div class="card pbp-pressure">
    <div class="pbp-rail-head">Under pressure${
      m.live ? ` <span class="lb-live">${icon("dot", 10)} LIVE</span>` : ""}
      <span class="mini">${escapeHtml(String(pr.season_used))} · one-score means within ${
        escapeHtml(pressureUnit(pr))}</span></div>
    ${m.chips.length ? `<div class="pbp-pr-chips">${m.chips.map((c) =>
      `<span class="chip">${escapeHtml(c)}</span>`).join("")}</div>` : ""}
    <p class="pbp-pr-line">${escapeHtml(m.line)}</p>
    ${m.market ? `<p class="pbp-pr-market">Live market: <b>${escapeHtml(d.home)} ${
      Number(m.market.now).toFixed(0)}%</b> to win, from ${
      Number(m.market.opened).toFixed(0)}% at the open — the market’s number, not ours.</p>` : ""}
    <div class="pr-table">
      <span class="lb-th"></span>${PRESSURE_RATES.map(([, t]) =>
        `<span class="lb-th">${t}</span>`).join("")}
      ${rows.map(([t, r]) => `<span class="lb-tm">${teamMarkIn(league, t, 20)} ${escapeHtml(t)}
          <span class="k">${escapeHtml(r.record || "")}</span></span>${
        PRESSURE_RATES.map(([k]) => `<b${asked(t, k) ? ' class="pbp-pr-asked"' : ""}>${
          pressurePct(r[k])}</b>`).join("")}`).join("")}
    </div>
    <div class="pr-defs">${PRESSURE_RATES.map(([, t, n]) =>
      `<span><b>${t}</b> ${escapeHtml(n)}</span>`).join("")}</div>
    <p class="mini" style="opacity:.6">Season counts from ${escapeHtml(String(pr.season_used))}
      finished games; the scoreboard decides which one is being asked, ${
      m.live ? "re-read with every pass of the fast loop" : "and asks nothing until the game starts"}.</p>
  </div>`;
}              // { view, y } while inside a detail

/* BACK GOES WHERE YOU CAME FROM. Ethan, 2026-09-28, on a pick page opened
   from the Most Likely page: "Back to the board … will just take me back
   to the home screen. It should take me back to the page I was previously
   on." Every detail page's Back used to switch to Home by name; it now
   returns to the page the detail was opened from (_boardReturn, which
   also restores the scroll), and says which page that is. A page opened
   cold — a pasted link — still goes Home. */
const BACK_NAMES = { recommended: "the board", likely: "Most Likely", edge: "Edge Picks",
  live: "Live", tonight: "Tonight", longshots: "Long Shots", props: "Player Props",
  scanner: "the scanner", futures: "Futures", team: "the team", players: "Players",
  injuries: "Injuries", record: "the Record" };
function detailBackLabel() {
  return `← Back to ${BACK_NAMES[detailBackView()] || "the board"}`;
}
/* The fast file's row for one game, any state — scheduled rows carry
   the carriers before kickoff (the Watch button on the game page). */
function liveRowFor(sport, g) {
  if (!g) return null;
  const hit = ((_liveAll && _liveAll.all) || []).find((x) => x.sport === sport
    && x.g && x.g.home === g.home && x.g.away === g.away);
  return hit ? hit.g : null;
}
/* `_pbpShowAll` used to live here, beside its readers. It is declared
   near the top of the file now — see the comment there. */
let _pbpTab = "gamecast";
/* ---------------- The page's other rooms ----------------
   Ethan, 2026-09-05: "the play by plays other rooms". The render's
   sub-tabs: Game info (the park facts), Our picks (the Most Likely and
   edge picks on this game, tracked — it was "Live props", the tracker's
   open tickets as one list, until 2026-09-26), Injuries (both clubs'
   designations from the injury board), Player stats (the box score the
   fast loop now writes into the deep file, from the parsers the tracker
   trusts). Team stats and Splits are not built FOR BASEBALL: the MLB
   deep file is the MLB builder's own shape, and a room drawn from an
   unread shape would be the fabricated number this site exists not to
   print. Football, hoops and hockey have them since 2026-10-08 — the
   summary's box and team blocks, read by livescore_build.pbp_doc and
   drawn by js/gamecast.js (GC_TABS below). */
const PBP_TABS = [["info", "Game info"], ["props", "Our picks"], ["injuries", "Injuries"], ["players", "Player stats"]];
const pbpTabsFor = (league) => league === "mlb" ? PBP_TABS : GC_TABS;

/* Both clubs' designations, matched on the injury feed's own club name
   — the team table's `name` — never on a nickname. */
function pbpInjuryRows(rows, league, d) {
  const teams = teamsForSport(league) || {};
  const nameOf = (abbr) => ((teams[abbr] || {}).name || "").toLowerCase();
  const want = new Set([nameOf(d.home), nameOf(d.away)].filter(Boolean));
  return (rows || []).filter((r) => r && !isReturnRow(r) && want.has(String(r.team || "").toLowerCase()));
}

/* WHAT THE ROOF AND THE FIELD ARE CALLED, in words rather than in the
   feed's spelling. The board carries `roof` as "outdoors" and `surface`
   as "fieldturf", and the panel printed them raw — "Roof: outdoors"
   over "fieldturf", which is a label and a value that are not a pair
   and a proper noun with no capital letter. Ethan, 2026-09-10: "fix the
   wording."

   An unmapped value is TITLE-CASED AND SHOWN, not swallowed: a feed
   that starts writing "retractable-closed" should read a little oddly
   rather than disappear. */
const PBP_ROOF_WORD = { outdoors: "Open air", outdoor: "Open air", open: "Roof open",
                        closed: "Roof closed", dome: "Dome", retractable: "Retractable" };
const PBP_SURFACE_WORD = { fieldturf: "FieldTurf", grass: "Grass", turf: "Turf",
                           astroturf: "AstroTurf", matrixturf: "MatrixTurf",
                           sportturf: "SportTurf", a_turf: "A-Turf", dessograss: "DessoGrass" };
const pbpTitleCase = (v) => String(v || "").replace(/[_-]+/g, " ")
  .replace(/\b\w/g, (c) => c.toUpperCase());

function pbpInjuriesHTML(d, league) {
  const rows = pbpInjuryRows((((_injBoard || {}).sports) || {})[league], league, d);
  if (!rows.length) return `<p class="rail-quiet">No designations listed for either club on the injury board.</p>`;
  return `<div class="inj-list">${rows.map((r) => injRow(r, true)).join("")}</div>`;
}

function pbpTabsHTML(active, boardGame, tabs) {
  return `<div class="pbp-tabs">${(tabs || PBP_TABS).map(([k, label]) =>
    `<button type="button" class="pbp-tab${k === active ? " active" : ""}" data-pbp-tab="${k}">${label}</button>`).join("")}${
    boardGame ? `<button type="button" class="pbp-tab-door" id="pbp-game-door" data-gid="${escapeAttr(gameId(boardGame))}">Full game page →</button>` : ""}</div>`;
}

/* Where Back goes from the play-by-play, and what it says. The game
   page only when there is still a game to go back to. */
function pbpBack() {
  const from = state.pbpFrom;
  if (from === "recommended") return { view: "recommended", label: "← Back to the board" };
  if (from === "game" && state.gameId) return { view: "game", label: "← Back to the game" };
  return { view: "live", label: "← Back to Live" };
}

function pbpStripHTML(league, games, current) {
  if (!games.length) return "";
  const chip = (g) => {
    const lv = g.live || {};
    const id = String(g.event_id || g.game_pk || "");
    const on = !!id && id === current;
    const door = !!id && (lv.state === "live" || lv.state === "final");
    /* A GAME NOT UNDER WAY OPENS ITS GAME PAGE (Ethan, 2026-09-24,
       circling the 3:10 and 6:05 chips: "I should be able to click on
       the games up here as well and it takes us to the normal game
       page"). There is no play-by-play before first pitch, so the chip
       was disabled; it now opens the board's game when the board has it. */
    const bg = !door && state.sport === league && state.data
      ? ((state.data.games || []).find((x) => x.home === g.home && x.away === g.away) || null) : null;
    // A game starting inside the hour counts down to it ("in 12:34"), ticked
    // by the page's one timer (pbpCountStart); later ones say the time.
    const start = Date.parse(lv.start_time || ""), left = start - Date.now();
    const head = lv.state === "live" ? `<span class="lb-live">${icon("dot", 8)} LIVE</span>`
      : lv.state === "final" ? `<span class="pbp-chip-final">FINAL</span>`
      : left > 0 && left <= PBP_COUNT_MS ? `<span class="pbp-chip-time" data-pbp-count="${start}" data-pbp-pre="in "
          data-pbp-done="Starting">in ${pbpCountdown(left)}</span>`
      : `<span class="pbp-chip-time">${escapeHtml(pbpTime(lv.start_time) || "TBD")}</span>`;
    const row = (abbr, score) => `<span class="pbp-chip-row">${teamMarkIn(league, abbr, 16)}<em>${
      escapeHtml(abbr || "")}</em><b>${score != null ? score : ""}</b></span>`;
    return `<button type="button" class="pbp-chip${on ? " active" : ""}${door || bg ? " door" : ""}"${
      door ? ` data-pbp="${escapeAttr(id)}"` : bg ? ` data-pbp-game="${escapeAttr(gameId(bg))}"
      title="Open this game’s page"` : " disabled"}>
      <div class="pbp-chip-head">${head}</div>
      ${row(g.away, lv.away_score)}${row(g.home, lv.home_score)}
      <div class="pbp-chip-foot">${escapeHtml(lv.state === "live" ? (lv.period || "") : "")}</div>
    </button>`;
  };
  return `<div class="pbp-strip" role="list">${games.map(chip).join("")}</div>`;
}

/* --- the situation strip: who is up, the count, the bases, who is throwing --- */
function pbpFaces(league) {
  if (state.sport !== league || !state.data) return {};
  const out = {};
  [...(state.data.recommendations || []), ...(state.data.long_shots || []),
   ...(state.data.most_likely || [])].forEach((r) => {
    if (r && r.player && r.headshot && !out[String(r.player).toLowerCase()])
      out[String(r.player).toLowerCase()] = r.headshot;
  });
  return out;
}
function pbpFaceHTML(name, faces) {
  const src = name ? faces[String(name).toLowerCase()] : "";
  return src ? `<img class="pbp-face" src="${escapeAttr(src)}" alt="" loading="lazy">`
    : `<span class="pbp-face pbp-face-blank">${icon("user", 16)}</span>`;
}
function pbpSituationHTML(d, league, faces) {
  if (league !== "mlb") return "";
  const lv = d.live || {};
  const cur = d.current || {};
  const count = (lv.balls != null && lv.strikes != null) ? `${lv.balls}-${lv.strikes}` : "";
  const outs = lv.outs != null ? `${lv.outs} out${lv.outs === 1 ? "" : "s"}` : "";
  const half = cur.half === "T" ? "Top" : cur.half === "B" ? "Bottom" : "";
  // THE TEAM BADGES (Ethan's render, 2026-09-06): his AT BAT / PITCHING
  // panels carry the club's mark, which is the fastest way to read who is
  // hitting on a page where the two names are strangers to most readers.
  // Derived, never guessed — the batting side is whichever half it is,
  // and the pitching side is the other one. With no half known, neither
  // badge draws rather than picking one at random.
  const batTeam = cur.half === "T" ? d.away : cur.half === "B" ? d.home : "";
  const pitTeam = cur.half === "T" ? d.home : cur.half === "B" ? d.away : "";
  const badge = (abbr) => abbr
    ? `<span class="pbp-sit-badge">${teamMarkIn(league, abbr, 22)}</span>` : "";
  return `
    <div class="pbp-sit">
      <div class="pbp-sit-side">
        ${badge(batTeam)}
        ${pbpFaceHTML(cur.batter, faces)}
        <div><div class="k">AT BAT${batTeam ? ` · ${escapeHtml(batTeam)}` : ""}</div>
          <b>${escapeHtml(cur.batter || "—")}</b>
          <div class="mini">${cur.pitches != null && cur.batter ? `${cur.pitches} pitch${cur.pitches === 1 ? "" : "es"} this at-bat` : ""}</div></div>
      </div>
      <div class="pbp-sit-mid">
        ${miniDiamond(lv.bases)}
        <b class="pbp-count">${escapeHtml(count || "–")}</b>
        <div class="mini">${escapeHtml([half && cur.inning ? `${half} ${pbpOrd(cur.inning)}` : "", outs].filter(Boolean).join(" · "))}</div>
      </div>
      <div class="pbp-sit-side pbp-sit-right">
        <div><div class="k">PITCHING${pitTeam ? ` · ${escapeHtml(pitTeam)}` : ""}</div>
          <b>${escapeHtml(cur.pitcher || "—")}</b></div>
        ${pbpFaceHTML(cur.pitcher, faces)}
        ${badge(pitTeam)}
      </div>
    </div>`;
}

/* --- the rail --- */
const PBP_CALL_KIND = (code) => {
  const c = String(code || "");
  if (["B", "*B", "V", "I", "P"].includes(c)) return "ball";
  if (["F", "R", "L", "T", "O"].includes(c)) return "foul";
  if (["X", "D", "E", "J", "Z", "H"].includes(c)) return "inplay";
  return "strike";
};
function pbpBaseballGroups(d) {
  const rows = (d.events && d.events.length) ? d.events
    : (d.plays || []).map((p) => ({ ...p, kind: "atbat" }));
  const groups = []; const byKey = {};
  rows.forEach((r) => {
    const k = `${r.half || ""}${r.inning || ""}`;
    if (!byKey[k]) {
      const batting = r.half === "T" ? d.away : r.half === "B" ? d.home : "";
      const head = r.inning ? `${r.half === "T" ? "Top" : r.half === "B" ? "Bottom" : ""} ${pbpOrd(r.inning)}`.trim() : "—";
      byKey[k] = { head, sub: batting ? `${batting} batting` : "", tag: "", rows: [], batting };
      groups.push(byKey[k]);
    }
    byKey[k].rows.push(r);
  });
  groups.forEach((g) => g.rows.reverse());
  return groups.reverse();
}
function pbpRowHTML(r, league, batting) {
  const when = pbpTime(r.time);
  if (r.kind === "pitch") {
    const kind = PBP_CALL_KIND(r.code);
    const detail = [r.speed != null ? `${Number(r.speed).toFixed(0)} mph` : "", r.pitch || ""].filter(Boolean).join(" ");
    const cnt = (r.balls != null && r.strikes != null) ? ` · ${r.balls}-${r.strikes}` : "";
    return `<div class="pbp-row pitch">
      <span class="pbp-dot ${kind}"></span>
      <span class="pbp-what"><b>${escapeHtml(r.call || "Pitch")}</b>${detail ? ` · ${escapeHtml(detail)}` : ""}${cnt}
        <span class="pbp-who">${escapeHtml(r.batter || "")}</span></span>
      <span class="pbp-time">${escapeHtml(when)}</span></div>`;
  }
  const h = r.hit || null;
  const hitTxt = h ? [h.launch_speed != null ? `${Number(h.launch_speed).toFixed(1)} mph` : "",
                      h.distance != null ? `${Math.round(h.distance)} ft` : ""].filter(Boolean).join(" · ") : "";
  const rbi = r.rbi ? ` <span class="lb-rbi">${r.rbi} RBI</span>` : "";
  return `<div class="pbp-row atbat${r.scoring ? " scoring" : ""}">
    <span class="pbp-mark">${teamMarkIn(league, batting, 18)}</span>
    <span class="pbp-what"><b>${escapeHtml(r.event || "")}</b>${rbi}
      <span class="pbp-who">${escapeHtml(r.batter || "")}${hitTxt ? ` · ${escapeHtml(hitTxt)}` : ""}</span></span>
    <span class="pbp-time">${escapeHtml(when)}</span></div>`;
}

function pbpRailHTML(d, league) {
  const PEEK = 40;
  const mlb = league === "mlb";
  const groups = mlb ? pbpBaseballGroups(d) : pbpGroups(d);
  const total = groups.reduce((a, g) => a + g.rows.length, 0);
  let budget = _pbpShowAll ? Infinity : PEEK;
  const shown = [];
  for (const g of groups) {
    if (budget <= 0) break;
    const rows = g.rows.slice(0, budget);
    budget -= rows.length;
    shown.push({ ...g, rows });
  }
  const group = (g) => `
    <div class="pbp-group">
      <div class="pbp-group-head"><span><b>${escapeHtml(g.head)}</b>${
        g.sub ? ` — ${escapeHtml(g.sub)}` : ""}</span>${
        g.tag ? `<span class="pbp-tag${g.tag === "TURNOVER" ? " turnover" : ""}">${escapeHtml(g.tag)}</span>` : ""}</div>
      ${mlb ? g.rows.map((r) => pbpRowHTML(r, league, g.batting)).join("")
            : (playsHTML({ plays: g.rows }) || `<p class="rail-quiet" style="margin:0 0 8px">No plays yet.</p>`)}
    </div>`;
  const more = total - shown.reduce((a, g) => a + g.rows.length, 0);
  return `${shown.length ? shown.map(group).join("") : `<div class="card">${panelEmpty("Nothing has happened yet.")}</div>`}
    ${more > 0 ? `<button class="btn ghost" type="button" id="pbp-more">View full play by play (${total}) →</button>` : ""}`;
}

/* THE PARK'S SCOREBOARD, LIT (Ethan, 2026-10-25, circling the blank board
   on the photograph: "for the mlb live view, we should display the live
   score where I circled … make it look good and blend it and make it look
   like it's a real mlb score board").

   THE SCREEN IS MEASURED OFF THE PHOTOGRAPH, like the wall marks and the
   bags (app.js PBP_PHOTO, PBP_BASES): the inside of the board's white
   frame, corner by corner, read off a half-unit grid in the same 240x150
   box at twelve times zoom, then drawn back over the picture to check it
   sits on the frame. The board faces a little to the right, so its left
   edge stands taller than its right (16.6 units to 15.1).

   SO IT IS DRAWN IN PERSPECTIVE, not pasted flat on top. SVG has no
   projective transform, so the board is laid out in a flat 100x50 face
   and every piece of it rides the screen's own projective map: a point
   goes through it exactly, and each piece of text takes the map's local
   slope at its anchor — the way a painter's lettering leans with the
   wall it is painted on. Lines between two points are exact (a
   projective map keeps straight lines straight).

   WHAT IT SHOWS IS WHAT THE LIVE FEED HOLDS: both teams and their runs,
   the inning and its half, the runners on base, balls, strikes and outs,
   and a lamp beside the team at bat. A real board's hits and errors are not in our live
   state, so they are not drawn rather than drawn as zeros. Before the
   first pitch it shows the first pitch; at the end, FINAL; in a delay,
   the delay. A run that has just scored flashes once, as boards do.
   Decorative to a screen reader: the score above the photograph says
   all of this in words. */
const PBP_BOARD = [[20.3, 24.1], [52.9, 24.7], [52.9, 39.8], [21.0, 40.7]];   // TL TR BR BL
const PBP_BOARD_LED = { amber: "#FFC94A", white: "#F4F6FA", dim: "#8C95A8", off: "#262B36",
                        ball: "#3DDC84", strike: "#FF5A4E", panel: "#05070C", rule: "#FFFFFF",
                        face: "#07080C", clock: "#FFD34A", lamp: "#FF3B30", shot: "#120707" };
// The three bags on the board's face (base, x, y): second at the top.
const PBP_BOARD_BASES = [[1, 96.2, 15], [2, 91.2, 10], [3, 86.2, 15]];
let _pbpBoardLast = null;

/* The projective map from the board's flat face (0..1 by 0..1) onto the
   screen's four corners, with its slope at the point (Heckbert's square
   to quad). */
function pbpBoardMap(quad = PBP_BOARD) {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = quad;
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3;
  const dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
  const den = dx1 * dy2 - dx2 * dy1;
  const g = (dx3 * dy2 - dx2 * dy3) / den, h = (dx1 * dy3 - dx3 * dy1) / den;
  const a = x1 - x0 + g * x1, b = x3 - x0 + h * x3, d = y1 - y0 + g * y1, e = y3 - y0 + h * y3;
  return (u, v) => {
    const w = g * u + h * v + 1, X = (a * u + b * v + x0) / w, Y = (d * u + e * v + y0) / w;
    return { X, Y, xu: (a - X * g) / w, yu: (d - Y * g) / w, xv: (b - X * h) / w, yv: (e - Y * h) / w };
  };
}

/* A team's colour that shows on a black board: its primary, or its
   secondary when the primary is a navy or a black that would vanish. */
function pbpBoardColor(abbr, league = "mlb") {
  const table = (typeof teamsForSport === "function" && teamsForSport(league))
    || (typeof MLB_TEAMS !== "undefined" ? MLB_TEAMS : {});
  const t = (table && table[abbr]) || {};
  // A colour shows on the board's black when it stands 3:1 off it, the
  // contrast a mark needs to be seen (WCAG's for a graphic): the Bucs' and
  // the Reds' red do, the Brewers' and the Cowboys' navy do not. A team with
  // none that bright keeps its brightest past 2:1 (the Jets' green, the
  // Texans' red) before it falls to the board's grey.
  const lum = (hex) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ""));
    if (!m) return 0;
    const n = parseInt(m[1], 16);
    const ch = (c) => (c /= 255) <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    return 0.2126 * ch(n >> 16) + 0.7152 * ch((n >> 8) & 255) + 0.0722 * ch(n & 255);
  };
  const off = (c) => (lum(c) + 0.05) / (lum(PBP_BOARD_LED.panel) + 0.05);
  // College's table names its second colour `alt` (cfbdata.parse_teams).
  const all = [t.primary, t.secondary, t.tertiary, t.alt].filter(Boolean);
  const pick = all.find((c) => off(c) >= 3) || all.filter((c) => off(c) >= 2).sort((a, b) => off(b) - off(a))[0];
  return pick || PBP_BOARD_LED.dim;
}

/* BIG MOMENTS (Ethan, 2026-10-25: "keep adding life to the app"). A home
   run, a touchdown, a field goal, a takeaway: the play that just happened
   goes up on the board the way a stadium's board shouts it, and a home run
   or a touchdown sets off fireworks over the stands.

   Only a play that lands while the page is open counts. The board keeps
   the newest play it drew and when it drew it; the page asks again every
   twelve seconds, so a newer play drawn under forty seconds later is news.
   A page left and come back to does not celebrate what it missed, and a
   first drawing celebrates nothing. Every play since the last drawing is
   read, not only the newest, so a touchdown and its extra point landing
   in one pass still read TOUCHDOWN.

   ONCE UP, IT STAYS UP until the next pass (eleven seconds): the page is
   redrawn for other reasons too (the slate finishing loading, a tab
   picked), and a redraw keeps the word and runs the fireworks on from
   where they had got to (--t, the time since the play, in css/detail.css)
   rather than wiping them or starting them over. */
const PBP_MOMENT_MS = 40000, PBP_MOMENT_UP_MS = 11000;
const PBP_MOMENTS = [                    // football, the biggest first: word, the play, fireworks
  ["TOUCHDOWN", (p) => p.scoring && /touchdown/i.test(p.event || ""), true],
  ["FIELD GOAL", (p) => p.scoring && /field goal/i.test(p.event || ""), false],
  ["SAFETY", (p) => p.scoring && /safety/i.test(p.event || ""), false],
  ["INTERCEPTION", (p) => p.turnover && /interception/i.test(p.event || ""), false],
  ["FUMBLE", (p) => p.turnover && /fumble/i.test(p.event || ""), false],
];
// The sport a league plays, for the plays it reads and the moments it has.
const pbpSportOf = (league) => league === "nfl" || league === "cfb" ? "football"
  : league === "nba" || league === "wnba" ? "hoops" : league === "nhl" ? "hockey" : "baseball";
// A game clock in seconds: "5:10", "0.4", "45.2" (app.js pbpClockSecs is
// a drive's length, and reads only a plain m:ss).
function pbpGameClockSecs(c) {
  const s = String(c == null ? "" : c).trim();
  const m = /^(\d+):(\d{1,2}(?:\.\d+)?)$/.exec(s);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  return /^\d+(?:\.\d+)?$/.test(s) ? Number(s) : null;
}
/* Hockey's strength on the ice: the side on the power play and the side
   whose net is empty. The power play is the page's own when it hands one
   over (rinkcast works it out from the penalties when the feed is silent),
   else the feed's block, else the newest event's situation code (away
   goalie, away skaters, home skaters, home goalie: nhlrink.situation, a
   pulled goalie's extra man not counted as a power play). */
function pbpRinkSit(d, opt = {}) {
  const rk = (d && d.rink) || {}, s = rk.situation || {};
  const side = (abbr) => (abbr && abbr === d.home ? "home" : abbr && abbr === d.away ? "away" : "");
  const code = String(((rk.events || []).filter((r) => r && r.sc).pop() || {}).sc || "");
  let pp = opt.pp !== undefined ? opt.pp || "" : side(s.pp), en = "";
  if (/^[01][3-6][3-6][01]$/.test(code)) {
    const [ag, ask, hsk, hg] = code.split("").map(Number);
    const a = ask - (ag === 0 ? 1 : 0), h = hsk - (hg === 0 ? 1 : 0);
    if (opt.pp === undefined && s.pp === undefined) pp = h > a ? "home" : a > h ? "away" : "";
    en = ag === 0 ? "away" : hg === 0 ? "home" : "";
  }
  return { pp, en, left: opt.ppLeft != null ? pbpCountdown(opt.ppLeft * 1000) : s.left || "" };
}
function pbpMoment(d, league, prev, opt = {}) {
  const lv = (d && d.live) || {}, sport = pbpSportOf(league);
  const plays = sport === "football" ? (d.plays || []).filter((r) => r && r.kind === "football")
    : sport === "hoops" ? (d.plays || []).filter((r) => r && r.kind === "hoops")
    : sport === "hockey" ? (((d.rink || {}).events) || []).filter((r) => r && r.id != null)
    : (d.events || []).filter((r) => r && r.kind === "atbat");
  const keyOf = (r) => String((sport === "baseball" ? r.at_bat : r.id) ?? "");
  const key = plays.length ? keyOf(plays[plays.length - 1]) : "";
  const sit = sport === "hockey" ? pbpRinkSit(d, opt) : null;
  const was = prev && prev.moment;
  if (was && prev.play === key && prev.state === lv.state && Date.now() - was.at < PBP_MOMENT_UP_MS) return { ...was, sit };
  const out = { key, word: "", big: false, side: "", at: Date.now(), sit };
  if (!prev || !(Date.now() - prev.at < PBP_MOMENT_MS)) return out;
  // Every play since the last drawing (none drawn yet: every play is new).
  let fresh = [];
  if (key && prev.play != null && prev.play !== key) {
    const seen = plays.findIndex((r) => keyOf(r) === prev.play);
    fresh = seen >= 0 ? plays.slice(seen + 1) : prev.play === "" ? plays : plays.slice(-1);
  }
  const sideOf = (team) => (team && team === d.home ? "home" : team && team === d.away ? "away" : "");
  const lead = (a, h) => (a > h ? "away" : h > a ? "home" : "");
  const set = (word, big, side) => Object.assign(out, { word, big, side: side || "" });
  if (sport === "football") {
    const hit = PBP_MOMENTS.find(([, is]) => fresh.some(is));
    if (hit) set(hit[0], hit[2]);
  } else if (sport === "baseball") {
    const hr = fresh.filter((r) => r.event_type === "home_run").pop();
    if (hr) set(hr.rbi >= 4 ? "GRAND SLAM" : "HOME RUN", true, hr.half === "T" ? "away" : "home");
  } else if (sport === "hoops") {
    // A make at the horn (a field goal with a second or less left) beats a
    // three, a three a dunk, a dunk the lead changing hands, that a timeout.
    const made = fresh.filter((r) => r.shot && r.scoring && Number(r.points) >= 2);
    const horn = made.filter((r) => { const s = pbpGameClockSecs(r.clock); return s != null && s <= 1; }).pop();
    const three = made.filter((r) => Number(r.points) === 3).pop();
    const dunk = made.filter((r) => /dunk/i.test(r.event || "")).pop();
    const timeout = fresh.filter((r) => /timeout/i.test(r.event || "")).pop();
    const before = lead(prev.away, prev.home), now = lead(lv.away_score, lv.home_score);
    if (horn) set("BUZZER BEATER", true, sideOf(horn.team));
    else if (three) set("3-POINTER", false, sideOf(three.team));
    else if (dunk) set("DUNK", false, sideOf(dunk.team));
    else if (before && now && before !== now) set("LEAD CHANGE", false, now);
    else if (timeout) set("TIMEOUT", false, sideOf(timeout.team));
  } else {
    const goal = fresh.filter((r) => r.kind === "goal").pop();
    const had = prev.sit || {};
    if (goal) set("GOAL", true, sideOf(goal.team));
    else if (sit.pp && sit.pp !== had.pp) set("POWER PLAY", false, sit.pp);
    else if (sit.en && sit.en !== had.en) set("EMPTY NET", false, sit.en);
  }
  // THE FINAL HORN, seen live: every game's last moment, whatever led to it
  // (a walk-off or a buzzer-beater says so instead).
  if (!out.word && prev.state === "live" && lv.state === "final") set("FINAL", true, lead(lv.away_score, lv.home_score));
  // Fireworks burn in the colours of the side whose score went up.
  if (out.big && !out.side) out.side = lv.home_score > prev.home ? "home" : lv.away_score > prev.away ? "away" : "";
  return out;
}
// What a board remembers between drawings: the score, the state, the
// strength on the ice, the newest play and when, and a moment that is up.
function pbpBoardKeep(id, lv, moment) {
  return { id, away: lv.away_score, home: lv.home_score, state: lv.state, sit: moment.sit || null,
           play: moment.key, at: Date.now(), moment: moment.word ? moment : null };
}

/* The fireworks: bursts over the stands, rings of sparks in the board's
   gold, white and the scoring side's colour, opening one after another
   (css/detail.css runs them; reduced motion never shows them). The spots
   are each photograph's sky and upper deck, clear of its boards. */
const PBP_BOOM_MS = 5200;                // the last burst's second fade ends by then
const PBP_BOOM_SPOTS = {
  mlb: [[150, 10, 13], [100, 15, 11], [198, 17, 12], [126, 27, 9], [176, 8, 10]],
  football: [[62, 30, 12], [178, 30, 12], [120, 42, 10], [40, 12, 9], [200, 12, 9]],
};
function pbpBoomSVG(spots, color, since = 0, unit = 1, inline = false) {
  const L = PBP_BOARD_LED, f = (n) => n.toFixed(2);
  const inks = [L.amber, color || L.white, L.white];
  const bursts = spots.map(([x, y, r], i) => {
    const sparks = Array.from({ length: 16 }, (_, k) => {
      const a = (k / 16) * Math.PI * 2 + i * 0.4, c = Math.cos(a), s = Math.sin(a);
      return `<line x1="${f(c * r * .3)}" y1="${f(s * r * .3)}" x2="${f(c * r)}" y2="${f(s * r)}"/>`
        + `<circle cx="${f(c * r * 1.1)}" cy="${f(s * r * 1.1)}" r="${f(.55 * unit)}" stroke="none"/>`;
    }).join("");
    return `<g transform="translate(${x} ${y})"><g class="pbp-boom-b" stroke="${inks[i % 3]}" fill="${inks[i % 3]}"
      stroke-width="${f(.45 * unit)}" stroke-linecap="round">${sparks}</g></g>`;
  }).join("");
  return inline ? `<g class="pbp-boom" style="--t:${Math.round(since)}ms">${bursts}</g>`
    : `<svg class="pbp-boom" viewBox="0 0 240 150" preserveAspectRatio="xMidYMax slice" aria-hidden="true"
    style="--t:${Math.round(since)}ms">${bursts}</svg>`;
}

/* THE LAST HOUR, COUNTED DOWN. Inside an hour of the start a game counts
   to it a second at a time: its chip in the strip along the top of every
   live page ("in 12:34"), and both boards when the page is the game's own
   ("FIRST PITCH IN 12:34", "KICKOFF IN 4:05"; a game's file is written
   once it is live, so that is the rarer of the two). The number is drawn
   with the moment it counts to, and one timer for the page (pbpCountStart,
   started by renderPbpPage when there is one to run) ticks every number on
   it. At zero the page asks for the games again; from ten minutes out a
   game's own page asks every twelve seconds (pbpStartsSoon), so its board
   goes live without a refresh. */
const PBP_COUNT_MS = 60 * 60000;
let _pbpCountTimer = null;
function pbpCountdown(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  const two = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${two(m)}:${two(s % 60)}` : `${m}:${two(s % 60)}`;
}
function pbpCountStart() {
  if (_pbpCountTimer) return;
  _pbpCountTimer = setInterval(() => {
    const els = document.querySelectorAll("[data-pbp-count]");
    if (!els.length || state.view !== "pbp") { clearInterval(_pbpCountTimer); _pbpCountTimer = null; return; }
    let rang = false;
    els.forEach((el) => {
      const left = Number(el.dataset.pbpCount) - Date.now();
      if (left > 0) { el.textContent = (el.dataset.pbpPre || "") + pbpCountdown(left); return; }
      el.removeAttribute("data-pbp-count");
      el.textContent = el.dataset.pbpDone || "";
      rang = true;
    });
    if (rang) renderPbpPage();
  }, 1000);
}
// From ten minutes before the start to an hour after it (a game that never
// starts stops being asked about).
function pbpStartsSoon(lv) {
  if (!lv || lv.state === "live" || lv.state === "final" || !lv.start_time) return false;
  const left = Date.parse(lv.start_time) - Date.now();
  return left < 10 * 60000 && left > -60 * 60000;
}

/* THE WIND OVER THE PARK (Ethan, 2026-10-25). The header says "12 mph
   blowing out"; here it is seen: streaks running over the outfield the way
   the wind runs, out toward the wall or in toward the plate, more of them
   and faster the harder it blows. Only what the feed holds is drawn:
   baseball's wind is its relation to the park, so "out" and "in" are
   drawn; a crosswind's side is not held, so it is not (the header still
   says it), nor a wind under 5 mph, nor one under a closed roof. Each
   streak runs over the outfield grass, from the back of the infield's
   dirt (y 79-95 on the photograph) over the wall (app.js PBP_PHOTO: centre
   field's at 120,58, the poles at 26,72 and 216,73), centre field first. */
const PBP_GUSTS = [
  [119, 94, 119.5, 74, 120, 52], [104, 95, 94, 76, 82, 58], [134, 95, 145, 76, 157, 58],
  [90, 100, 72, 86, 52, 74], [148, 100, 166, 86, 186, 74],
];
function pbpWindSVG(w) {
  const mph = Number((w || {}).wind_mph) || 0, dir = String((w || {}).wind_dir || "").trim().toLowerCase();
  if (!w || w.dome || mph < 5 || (dir !== "out" && dir !== "in")) return "";
  const band = mph < 10 ? "pbp-wind-light" : mph < 15 ? "pbp-wind-brisk" : "pbp-wind-strong";
  const gusts = PBP_GUSTS.slice(0, band === "pbp-wind-light" ? 3 : 5).map(([x0, y0, cx, cy, x1, y1]) => dir === "out"
    ? `<path d="M${x0} ${y0}Q${cx} ${cy} ${x1} ${y1}"/>` : `<path d="M${x1} ${y1}Q${cx} ${cy} ${x0} ${y0}"/>`).join("");
  return `<svg class="pbp-wind ${band}" viewBox="0 0 240 150" preserveAspectRatio="xMidYMax slice" aria-hidden="true"
    fill="none" stroke="${PBP_BOARD_LED.white}" stroke-linecap="round">${gusts}</svg>`;
}

function pbpBoardSVG(d, league = "mlb", boardGame = null) {
  if (league === "nfl" || league === "cfb") return pbpFieldBoardSVG(d, league);
  const lv = (d && d.live) || {};
  const away = String(d.away || ""), home = String(d.home || "");
  if (!away || !home) return "";
  const L = PBP_BOARD_LED, map = pbpBoardMap();
  const W = 100, H = 50;
  const f = (n) => n.toFixed(2);
  const pt = (x, y) => { const m = map(x / W, y / H); return `${f(m.X)},${f(m.Y)}`; };
  const at = (x, y, inner) => {
    const m = map(x / W, y / H);
    return `<g transform="matrix(${f(m.xu / W)} ${f(m.yu / W)} ${f(m.xv / H)} ${f(m.yv / H)} ${f(m.X)} ${f(m.Y)})">${inner}</g>`;
  };
  const line = (x1, y1, x2, y2) => {
    const [a, b] = [pt(x1, y1).split(","), pt(x2, y2).split(",")];
    return `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${L.rule}" stroke-opacity=".12" stroke-width=".18"/>`;
  };
  const live = lv.state === "live", final = lv.state === "final";
  const per = String(lv.period || "");
  const inn = /^(top|bottom|bot|middle|mid|end)\b\D*(\d+)/i.exec(per);
  const half = inn ? inn[1].toLowerCase().slice(0, 3) : "";
  const batting = live && half === "top" ? "away" : live && half === "bot" ? "home" : "";
  // A run that scored since the last time this board was drawn flashes.
  const id = `mlb:${away}@${home}`;
  const prev = _pbpBoardLast && _pbpBoardLast.id === id ? _pbpBoardLast : null;
  const moment = pbpMoment(d, "mlb", prev);
  _pbpBoardLast = pbpBoardKeep(id, lv, moment);
  const row = (side, abbr, runs, cy) => {
    const fresh = prev && runs != null && prev[side] != null && runs !== prev[side];
    // Two digits step down a size, so a twelve keeps clear of "ARI".
    const r = runs != null ? String(runs) : "", rs = r.length > 1 ? 15 : 21;
    return (batting === side ? at(3.2, cy, `<path d="M-1.4 -2.2 L1.8 0 L-1.4 2.2 Z" fill="url(#pbp-mlb-gold)"/>`) : "")
      + at(6.6, cy, `<rect x="-1.2" y="-6" width="2.4" height="12" rx=".6" fill="${pbpBoardColor(abbr)}"
          filter="url(#pbp-mlb-glow)"/>`)
      + at(10.5, cy, `<text y="5.4" font-size="15.5" fill="url(#pbp-mlb-silver)" letter-spacing=".5"
          filter="url(#pbp-mlb-glow)">${escapeHtml(abbr)}</text>`)
      + (r ? at(62, cy, `<text class="pbp-lit-num${fresh ? " pbp-sb-new" : ""}" y="${f(rs * 0.35)}" font-size="${rs}"
          text-anchor="end" fill="url(#pbp-mlb-gold)" filter="url(#pbp-mlb-glow)">${escapeHtml(r)}</text>`) : "");
  };
  // The right side: the inning and the count, or what stands in for them.
  // A word is sized to its room (the column's 30 of 36 units unless told
  // otherwise), never past it.
  let side = "";
  // Lit words wear the photograph's gold or silver and glow; a dim one is
  // the board's grey.
  const word = (txt, y, max, fill, mono, cx = 82, room = 30, attrs = "") => {
    const size = Math.min(max, room / (Math.max(1, txt.length) * 0.62));
    const ink = fill === L.amber ? "url(#pbp-mlb-gold)" : fill === L.white ? "url(#pbp-mlb-silver)" : fill;
    return at(cx, y, `<text${mono ? ' class="pbp-lit-num"' : ""} font-size="${f(size)}" text-anchor="middle"
      fill="${ink}"${fill !== L.dim ? ' filter="url(#pbp-mlb-glow)"' : ""}${attrs}>${escapeHtml(txt)}</text>`);
  };
  const hold = typeof liveHoldWord === "function" ? liveHoldWord(lv) : "";
  if (moment.word) {
    // HOME RUN across the column, blinking, until the next pass redraws it.
    const [a, b] = moment.word.split(" ");
    side = `<g class="pbp-sb-moment" style="--t:${Date.now() - moment.at}ms">${b
      ? word(a, 19.5, 14, L.amber, true, 82, 34) + word(b, 37, 14, L.amber, true, 82, 34)
      : word(a, 28.5, 14, L.amber, true, 82, 34)}</g>`;
  } else if (live && hold) {
    // "Delayed — Rain": the state, and under it why.
    const [what, why] = hold.split(/\s[\u2014-]\s/);
    side = word(what.toUpperCase(), why ? 24 : 28, 8, L.amber) + (why ? word(why.toUpperCase(), 33.5, 6.4, L.dim) : "");
  } else if (live && inn) {
    // The inning on the left of the column (x 64-82), the runners on its
    // right, the count under both.
    const n = inn[2], two = n.length > 1;
    side = half === "top" || half === "bot"
      ? at(two ? 67.3 : 67.8, 13, `<path d="${half === "top" ? "M-3 2.2 L0 -2.6 L3 2.2 Z" : "M-3 -2.2 L0 2.6 L3 -2.2 Z"}"
          fill="url(#pbp-mlb-gold)"${two ? ' transform="scale(.8)"' : ""}/>`) + at(two ? 76 : 75.6, 13, `<text class="pbp-lit-num"
            y="${two ? 3.5 : 5.1}" font-size="${two ? 10 : 14.5}" text-anchor="middle" fill="url(#pbp-mlb-gold)"
            filter="url(#pbp-mlb-glow)">${escapeHtml(n)}</text>`)
      : word(half === "mid" ? "MID" : "END", 9.6, 6.4, L.dim, false, 74.5, 15)
        + word(n, 22.4, 12, L.amber, true, 74.5, 15);
    // THE RUNNERS (Ethan, 2026-10-25: "next to the score we added on the
    // board, should also show the batters on base"), the way a board and
    // a broadcast draw them: three bags, second at the top, first on the
    // right, lit where `live.bases` has a runner. The same base numbers
    // the photograph's own bag markers read (app.js pbpBasesSVG).
    const on = new Set(lv.bases || []);
    side += PBP_BOARD_BASES.map(([bag, x, y]) => at(x, y, `<rect x="-2.2" y="-2.2" width="4.4" height="4.4"
        transform="rotate(45)" fill="${on.has(bag) ? L.amber : L.off}"${
        on.has(bag) ? ' filter="url(#pbp-mlb-glow)"' : ""}/>`)).join("");
    const lamps = (label, cy, lit, of, color) => at(69, cy, `<text y="2.3" font-size="6.4" text-anchor="middle"
        fill="${L.dim}">${label}</text>`) + Array.from({ length: of }, (_, i) => at(75 + i * 6.5, cy,
        `<circle r="2.2" fill="${i < (lit || 0) ? color : L.off}"/>`)).join("");
    side += `<g filter="url(#pbp-mlb-glow)">${lamps("B", 30, lv.balls, 3, L.ball) + lamps("S", 37.5, lv.strikes, 2, L.strike)
      + lamps("O", 45, lv.outs, 2, L.strike)}</g>`;
  } else if (final) {
    side = word("FINAL", 28.5, 11, L.white);
  } else if (!live && lv.start_time && typeof tzTime === "function") {
    const start = Date.parse(lv.start_time), left = start - Date.now();
    if (left > 0 && left <= PBP_COUNT_MS) {
      side = word("FIRST", 12.5, 6, L.dim) + word("PITCH IN", 19, 6, L.dim) + word(pbpCountdown(left), 32, 11,
        L.amber, true, 82, 30, ` data-pbp-count="${start}" data-pbp-done="NOW"`);
    } else {
      // "7:10 PM": the time lit, its half of the day small under it.
      const [clock, ampm] = String(tzTime(lv.start_time)).split(/\s+/);
      side = word("FIRST", 12.5, 6, L.dim) + word("PITCH", 19, 6, L.dim) + word(clock || "", 31.5, 11, L.amber, true)
        + (ampm ? word(ampm.toUpperCase(), 40.5, 6, L.dim) : "");
    }
  }
  return `<svg class="pbp-board" viewBox="0 0 240 150" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs>${pbpLitDefs("pbp-mlb", 0.75, 0.12)}<linearGradient id="pbp-sb-sheen" x1="0" y1="0" x2=".35" y2="1">
      <stop offset="0" stop-color="${L.rule}" stop-opacity=".07"/><stop offset=".5" stop-color="${L.rule}" stop-opacity="0"/>
    </linearGradient></defs>
    <polygon points="${PBP_BOARD.map(([x, y]) => `${x},${y}`).join(" ")}" fill="${L.panel}" fill-opacity=".9"/>
    <polygon points="${PBP_BOARD.map(([x, y]) => `${x},${y}`).join(" ")}" fill="url(#pbp-sb-sheen)"/>
    ${line(3, 25, 61, 25)}${line(64, 4, 64, 46)}
    ${row("away", away, lv.away_score, 13.5)}${row("home", home, lv.home_score, 36.5)}
    ${side}
  </svg>${pbpWindSVG((boardGame || {}).weather)}${moment.big && Date.now() - moment.at < PBP_BOOM_MS
    ? pbpBoomSVG(PBP_BOOM_SPOTS.mlb, pbpBoardColor(moment.side === "away" ? away : home), Date.now() - moment.at) : ""}${
    pbpMomentBannerHTML(d, "mlb")}`;
}

/* THE FOOTBALL FIELD'S BOARD, LIT (Ethan, 2026-10-25: "keep going with any
   more ideas like that" — after the ballpark's scoreboard).

   THE CENTRE-HUNG BOARD over the field photographs (all four: the pro and
   college fields, either side on offence) has a main screen carrying our
   crown and wordmark, and a framed screen on each side. A real stadium's
   centre-hung board puts the teams on its side screens, so ours does: the
   away team on the left, the home team on the right, each with a stripe
   of its colour, its score, and a football under the side that has the
   ball. The crown stays; the wordmark under it becomes the game: the
   quarter and the clock and the down ("Q3 4:12 · 3RD & 8"), HALFTIME,
   FINAL, or the kickoff before it.

   What it shows is what the live state holds, and a score that has just
   changed flashes, as on the ballpark's board. How it is drawn into the
   photograph is the note under this one. */
/* PART OF THE BOARD, NOT ON IT (Ethan, 2026-10-25, his phone's screenshot:
   "it looks ugly ... It looks like you place stickers or something on top
   of it ... Make sure it looks real and blended in"). Two things made the
   first draft a sticker. Its panels were cards of our own (a grey border,
   rounded corners, a code font's digits) laid over the photograph's
   screens; and on his phone the picture's box came out 1.5:1, where every
   drawing kept the picture's 1.6:1 and slid off it (all of them now cover
   and sit on the bottom, as the photograph does: preserveAspectRatio
   "xMidYMax slice", css/styles.css .pbp-photo says the same).

   So the screens here are the photograph's own. Its gold frames stay; only
   the face inside each is painted, in that face's own black (sampled off
   each of the four renders), its edge feathered into the picture. On it,
   the board's own lettering: the team in the wordmark's silver, the score
   in the logo's gold, both glowing as the logo does. The wordmark's line
   on the main screen becomes the game in the wordmark's own hand.

   THE FOUR RENDERS AGREE on the frames to a pixel or two (the side
   screens' gold lines at 85.6-98.7 and 140.4-153.8, 13.1 to 26.6 down)
   and on the wordmark (107.6-132.0 x 22.3-25.3 between them). The faces
   painted sit half a unit inside the lines; the logo they cover is
   88.1-96.0 x 15.6-23.1. Which render is up is app.js pbpFieldHTML's
   choice: the newest play's team, else the possession. */
const PBP_FIELD_BOARD = {
  away: [86.3, 13.8, 98, 26],            // a side screen's face: x0 y0 x1 y1
  home: [141.1, 13.8, 153.1, 26],
  line: [107, 21.7, 132.6, 25.9],        // the wordmark's line, with a margin
};
// Each render's screens' own black: the side faces, the main face.
const PBP_FIELD_FACES = {
  "nfl-home": ["#07090E", "#080A0E"], "nfl-away": ["#08080D", "#0C0D11"],
  "cfb-home": ["#04080D", "#08090D"], "cfb-away": ["#04060A", "#07080D"],
};
// The boards' lit lettering, in the photographs' own colours: the logo's
// gold, the wordmark's silver, the glow both have, a painted face's edge.
// The filters work in sRGB: in the default linear space, at eight bits, a
// face as dark as (8, 10, 14) comes back (13, 13, 13), a grey box on the
// screen it was painted to match.
function pbpLitDefs(id = "pbp-lit", glow = 0.28, soft = 0.2) {
  return `<linearGradient id="${id}-gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF3C8"/>
      <stop offset=".52" stop-color="#F3C24E"/><stop offset="1" stop-color="#BD8428"/></linearGradient>
    <linearGradient id="${id}-silver" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/>
      <stop offset="1" stop-color="#C3C8D0"/></linearGradient>
    <filter id="${id}-glow" x="-25%" y="-45%" width="150%" height="190%" color-interpolation-filters="sRGB">
      <feGaussianBlur in="SourceGraphic" stdDeviation="${glow}" result="b"/>
      <feComponentTransfer in="b" result="g"><feFuncA type="linear" slope=".6"/></feComponentTransfer>
      <feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="${id}-soft" x="-10%" y="-25%" width="120%" height="150%" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="${soft}"/></filter>`;
}

function pbpFieldBoardSVG(d, league) {
  const lv = (d && d.live) || {};
  const away = String(d.away || ""), home = String(d.home || "");
  if (!away || !home) return "";
  const L = PBP_BOARD_LED, f = (n) => n.toFixed(2);
  const live = lv.state === "live", final = lv.state === "final";
  const id = `${league}:${away}@${home}`;
  const prev = _pbpBoardLast && _pbpBoardLast.id === id ? _pbpBoardLast : null;
  const moment = pbpMoment(d, league, prev);
  _pbpBoardLast = pbpBoardKeep(id, lv, moment);
  const hold = live && typeof liveHoldWord === "function" ? liveHoldWord(lv) : "";
  const last = (d.plays || []).filter((r) => r && r.kind === "football").pop();
  const who = (last && last.team) || lv.possession || "";
  const [faceInk, mainInk] = PBP_FIELD_FACES[`${league === "cfb" ? "cfb" : "nfl"}-${who && who === away ? "away" : "home"}`];
  const screen = (side, abbr, pts) => {
    const [x0, y0, x1, y1] = PBP_FIELD_BOARD[side], cx = (x0 + x1) / 2;
    const fresh = prev && pts != null && prev[side] != null && pts !== prev[side];
    const ball = live && !hold && lv.possession && lv.possession === abbr;     // no one has it at the half
    const s = pts != null ? String(pts) : "";
    return `<rect x="${x0}" y="${y0}" width="${f(x1 - x0)}" height="${f(y1 - y0)}" fill="${faceInk}" filter="url(#pbp-lit-soft)"/>
      <text class="pbp-lit-name" x="${f(cx)}" y="${f(y0 + 3.6)}" font-size="2.7" text-anchor="middle" letter-spacing=".3"
        fill="url(#pbp-lit-silver)" filter="url(#pbp-lit-glow)">${escapeHtml(abbr)}</text>
      <rect x="${f(cx - 2.6)}" y="${f(y0 + 4.5)}" width="5.2" height=".32" rx=".16" fill="${pbpBoardColor(abbr, league)}"
        filter="url(#pbp-lit-glow)"/>${s ? `
      <text class="pbp-lit-num${fresh ? " pbp-sb-new" : ""}" x="${f(cx)}" y="${f(y0 + 10.5)}"
        font-size="${s.length > 2 ? 5 : 6.6}" text-anchor="middle" fill="url(#pbp-lit-gold)" filter="url(#pbp-lit-glow)">${
        escapeHtml(s)}</text>` : ""}${ball ? `
      <g class="pbp-sb-ball" transform="translate(${f(cx)} ${f(y1 - .7)})" filter="url(#pbp-lit-glow)"><ellipse rx="1" ry=".55"
        fill="url(#pbp-lit-gold)"/><path d="M-.45 0H.45M-.22 -.2V.2M0 -.2V.2M.22 -.2V.2" stroke="${faceInk}" stroke-width=".13"/></g>` : ""}`;
  };
  // The main screen's line: what the game is doing now.
  const per = String(lv.period || "");
  let msg = "", count = "";
  if (moment.word) {
    msg = moment.word;
  } else if (hold) {
    // "Halftime", "Delayed", "End of 3rd" (ESPN's "End of 3rd Quarter", shortened).
    msg = hold.split(/\s[\u2014-]\s/)[0].replace(/\s+quarter$/i, "").toUpperCase();
  } else if (live) {
    const q = /^Q(\d+)$/.exec(per), n = q ? +q[1] : 0;
    const quarter = n > 4 ? (n === 5 ? "OT" : `${n - 4}OT`) : per;
    const down = String(lv.detail || "").split(/\s+at\s+/i)[0].toUpperCase();
    msg = [quarter + (lv.clock ? ` ${lv.clock}` : ""), down].filter((x) => x.trim()).join(" · ");
  } else if (final) {
    msg = (per || "Final").toUpperCase();
  } else if (lv.start_time && typeof tzTime === "function") {
    const start = Date.parse(lv.start_time), left = start - Date.now();
    msg = left > 0 && left <= PBP_COUNT_MS ? `KICKOFF IN ${pbpCountdown(left)}` : `KICKOFF ${tzTime(lv.start_time)}`;
    if (left > 0 && left <= PBP_COUNT_MS) count = ` data-pbp-count="${start}" data-pbp-pre="KICKOFF IN " data-pbp-done="KICKOFF"`;
  }
  // In the wordmark's hand: its height (3.4) and its wide spacing for a
  // short line, set closer and smaller for a long one so it keeps to the
  // wordmark's width.
  const [lx0, ly0, lx1, ly1] = PBP_FIELD_BOARD.line;
  const ls = msg.length <= 12 ? 0.3 : 0.1;
  const size = Math.min(3.4, (lx1 - lx0 - 1.4) / (Math.max(1, msg.length) * (0.5 + ls)));
  const line = msg ? `<rect x="${lx0}" y="${ly0}" width="${f(lx1 - lx0)}" height="${f(ly1 - ly0)}" fill="${mainInk}"
      filter="url(#pbp-lit-soft)"/>
    <text class="pbp-lit-line${moment.word ? ` pbp-sb-moment" style="--t:${Date.now() - moment.at}ms` : ""}"
      x="${f((lx0 + lx1) / 2 + size * ls / 2)}" y="25.1" font-size="${f(size)}" letter-spacing="${f(size * ls)}"
      text-anchor="middle" fill="url(#pbp-lit-${moment.word ? "gold" : "silver"})" filter="url(#pbp-lit-glow)"${count}>${
      escapeHtml(msg)}</text>` : "";
  return `<svg class="pbp-board" viewBox="0 0 240 150" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs>${pbpLitDefs()}</defs>
    ${screen("away", away, lv.away_score)}${screen("home", home, lv.home_score)}
    ${line}
  </svg>${moment.big && Date.now() - moment.at < PBP_BOOM_MS
    ? pbpBoomSVG(PBP_BOOM_SPOTS.football, moment.side ? pbpBoardColor(moment.side === "away" ? away : home, league) : "",
      Date.now() - moment.at) : ""}${pbpMomentBannerHTML(d, league)}`;
}

/* THE ARENAS, LIT (Ethan, 2026-10-25: "do the nba and nhl next ... make
   sure all additions and features and changes we have added and done has
   been done to all sports"). js/hoopscast.js and js/rinkcast.js draw over
   their arena photographs in the renders' 1672 x 941 (the files are the
   same picture at 1280 x 720), and each page shows a window of it: a wide
   screen the floor and the stands under the centre-hung board (basketball
   from y 230 down, so only the board's ring band shows; hockey nearly all
   of it), a phone the floor alone. So each arena is lit where its page
   shows it, measured off the picture:

   BASKETBALL (both leagues play in the one arena). The board's ring band
   (693-981 x 277-309) and the scorer's table along the far sideline
   (660-1018 x 556-584) carry the game: "LAL 10 · Q2 5:10 · BOS 8". The
   shot clocks over both baskets were painted 5:24 and 18 and never moved;
   they carry the game clock now, and the quarter in the red beneath it.
   The shot clock itself is in no feed we read, so it is not drawn.

   HOCKEY. The last-play card covers the main screen's left half on a wide
   screen, down to y 256, so the score rides the board's ring band under
   its screens (708-961 x 289-323) and the period and clock its lit halo
   beneath (centre 836,366), with the power play or an empty net under
   them. The centre panel of the far boards (755-922 x 576-595) is the one
   piece of them every phone window holds, and carries the score there. A
   goal says GOAL on the main screen and lights the red lamp behind the net
   it went in: rinkcast's own goal lines at (294, 682) and (1391, 682), the
   away side shooting at the left, the home side at the right.

   A big moment goes up on all of them (pbpMoment), with fireworks for a
   buzzer-beater, a goal and the final horn; on a phone, where all of this
   is a few pixels high, the moment also gets its banner. What a board
   shows is what the feed holds: timeouts, fouls and the bonus stay on the
   page's own scoreboard. */
const PBP_ARENA = {
  hoops: {
    ring: [693, 277, 981, 309],
    table: [660, 556, 1018, 584],
    // The shot clocks' faces inside their frames (TL TR BR BL): the left
    // basket's leans in from the left, the right one's from the right.
    clocks: [[[314.8, 460], [347.5, 454.2], [347.5, 499.9], [316.1, 511]],
             [[1328.5, 454.2], [1359.9, 460], [1358.5, 510.4], [1327.2, 499.9]]],
    boom: [[260, 430, 70], [1410, 430, 70], [520, 470, 56], [1150, 470, 56], [836, 480, 60]],
    // Each surface's own dark, sampled off the render: the band, the table,
    // the shot clocks' red-black faces.
    ink: { ring: "#090807", table: "#14100E", clock: "#330600" },
  },
  hockey: {
    ring: [708, 289, 961, 323],
    halo: [836, 366, 96, 23],                                 // cx cy rx ry
    boards: [755, 576, 922, 595],
    screen: [[663.6, 115], [1009.7, 115], [994.1, 283.6], [679.3, 283.6]],
    nets: { away: [294, 682, 252], home: [1391, 682, 1433] },  // the goal line, and the lamp's x behind it
    boom: [[260, 340, 70], [1410, 340, 70], [500, 420, 56], [1170, 420, 56], [836, 505, 50]],
    ink: { ring: "#080400", halo: "#1A0A00", boards: "#1E1307", screen: "#171009" },
  },
};
// The period as an arena's boards say it: Q2, OT, 2OT; 1ST, 3RD, OT, SO.
function pbpArenaPeriod(lv, league, d) {
  const per = String((lv || {}).period || "");
  if (league === "nhl") {
    const m = /^P(\d+)$/.exec(per), n = m ? +m[1] : 0;
    if (!n) return per.toUpperCase();
    if (n <= 3) return ["1ST", "2ND", "3RD"][n - 1];
    return n === 4 ? "OT" : (((d || {}).rink || {}).game_type === 3 ? `${n - 3}OT` : "SO");
  }
  const m = /^Q(\d+)$/.exec(per), n = m ? +m[1] : 0;
  return !n ? per.toUpperCase() : n <= 4 ? `Q${n}` : n === 5 ? "OT" : `${n - 4}OT`;
}
// What the game is doing, in a board's words; inside the last hour, counted.
function pbpArenaStatus(d, league) {
  const lv = (d && d.live) || {};
  const hold = lv.state === "live" && typeof liveHoldWord === "function" ? liveHoldWord(lv) : "";
  if (hold) return { text: hold.split(/\s[\u2014-]\s/)[0].replace(/\s+(quarter|period)$/i, "").toUpperCase() };
  if (lv.state === "live") return { text: [pbpArenaPeriod(lv, league, d), lv.clock || ""].filter(Boolean).join(" ") };
  if (lv.state === "final") return { text: String(lv.period || "Final").toUpperCase() };
  if (lv.start_time) {
    const start = Date.parse(lv.start_time), left = start - Date.now(), word = league === "nhl" ? "PUCK DROP" : "TIP-OFF";
    if (left > 0 && left <= PBP_COUNT_MS) return { text: `${word} IN ${pbpCountdown(left)}`, start, pre: `${word} IN `, done: word };
    if (typeof tzTime === "function") return { text: `${word} ${tzTime(lv.start_time)}` };
  }
  return { text: "" };
}
// One lit line across a rectangle of the picture: the board's own black
// over what was painted there, the words centred and sized to fit (the
// face is mono, so a character is 0.6 of its size). `parts` colour it.
function pbpLedLine([x0, y0, x1, y1], parts, max, blink = null, ink = PBP_BOARD_LED.face) {
  const f = (n) => n.toFixed(1);
  const n = parts.map((p) => p.t).join("").length;
  const size = Math.min(max, (x1 - x0) * 0.92 / (Math.max(1, n) * 0.58));
  return `<rect x="${x0}" y="${y0}" width="${f(x1 - x0)}" height="${f(y1 - y0)}" fill="${ink}" filter="url(#pbp-ar-soft)"/>
    <text class="pbp-ar-line${blink != null ? ` pbp-sb-moment" style="--t:${blink}ms` : ""}" x="${f((x0 + x1) / 2)}"
      y="${f((y0 + y1) / 2 + size * 0.36)}" font-size="${f(size)}" letter-spacing="${f(size * 0.05)}" text-anchor="middle"
      filter="url(#pbp-ar-glow)">${parts.map((p) => `<tspan fill="${p.c}"${p.a || ""}>${escapeHtml(p.t)}</tspan>`).join("")}</text>`;
}
// Words on a screen the picture sees at an angle, drawn on its own face
// (W 100 by H across) and carried onto the picture by its four corners.
function pbpOnQuad(quad, H, inner) {
  const map = pbpBoardMap(quad), W = 100, f = (n) => n.toFixed(3);
  return inner.map(([x, y, svg]) => {
    const m = map(x / W, y / H);
    return `<g transform="matrix(${f(m.xu / W)} ${f(m.yu / W)} ${f(m.xv / H)} ${f(m.yv / H)} ${f(m.X)} ${f(m.Y)})">${svg}</g>`;
  }).join("");
}
// A shot clock: the game clock in yellow over the period in red, LED
// digits on the clock's own red-black face.
function pbpShotClockSVG(quad, top, bottom, ink = PBP_BOARD_LED.shot) {
  const L = PBP_BOARD_LED, fit = (s, max) => Math.min(max, 92 / (Math.max(1, s.length) * 0.6)).toFixed(1);
  const glyph = (s, max, fill) => `<text class="pbp-sb-num" font-size="${fit(s, max)}" text-anchor="middle" fill="${fill}"
    filter="url(#pbp-ar-glow)">${escapeHtml(s)}</text>`;
  return `<polygon points="${quad.map(([x, y]) => `${x},${y}`).join(" ")}" fill="${ink}" filter="url(#pbp-ar-soft)"/>` + pbpOnQuad(quad, 150, [
    ...(top ? [[50, 52, glyph(top, 40, L.clock)]] : []), ...(bottom ? [[50, 124, glyph(bottom, 56, L.strike)]] : [])]);
}
function pbpArenaSVG(d, league, opt = {}) {
  const lv = (d && d.live) || {};
  const away = String((d && d.away) || ""), home = String((d && d.home) || "");
  if (!away || !home) return "";
  const hockey = league === "nhl", A = hockey ? PBP_ARENA.hockey : PBP_ARENA.hoops, L = PBP_BOARD_LED;
  const id = `${league}:${away}@${home}`;
  const prev = _pbpBoardLast && _pbpBoardLast.id === id ? _pbpBoardLast : null;
  const moment = pbpMoment(d, league, prev, opt);
  _pbpBoardLast = pbpBoardKeep(id, lv, moment);
  const since = Date.now() - moment.at, blink = moment.word ? since : null;
  const st = pbpArenaStatus(d, league);
  // A count drawn here ticks on the page's one timer (renderPbpPage hands
  // these pages over before it would start it).
  if (st.start && typeof document !== "undefined") pbpCountStart();
  const T = (t) => ({ t, c: "url(#pbp-ar-silver)" }), N = (n) => ({ t: String(n), c: "url(#pbp-ar-gold)" });
  const S = (t) => ({ t, c: L.dim });
  const now = st.text ? { t: st.text, c: "url(#pbp-ar-gold)",
    a: st.start ? ` data-pbp-count="${st.start}" data-pbp-pre="${st.pre}" data-pbp-done="${st.done}"` : "" } : null;
  const scored = lv.away_score != null && lv.home_score != null;
  const shout = moment.word ? [{ t: moment.word, c: "url(#pbp-ar-gold)" }, ...(moment.side ? [S(" · "), T(d[moment.side])] : [])] : null;
  let out = "";
  if (!hockey) {
    const game = shout || [T(scored ? `${away} ` : away), ...(scored ? [N(lv.away_score)] : []),
      ...(now ? [S(" · "), now] : []), S(" · "), T(scored ? `${home} ` : home), ...(scored ? [N(lv.home_score)] : [])];
    const top = lv.state === "live" ? String(lv.clock || "") : lv.state === "final" ? "0.0" : "";
    const bottom = lv.state === "live" ? pbpArenaPeriod(lv, league, d) : lv.state === "final" ? "FINAL" : "";
    out = pbpLedLine(A.ring, game, 22, blink, A.ink.ring) + pbpLedLine(A.table, game, 19, blink, A.ink.table)
      + A.clocks.map((q) => pbpShotClockSVG(q, top, bottom, A.ink.clock)).join("");
  } else {
    const score = shout || (scored ? [T(`${away} `), N(lv.away_score), S(" – "), N(lv.home_score), T(` ${home}`)]
      : [T(away), S(" · "), T(home)]);
    const [cx, cy, rx, ry] = A.halo, sit = moment.sit || {};
    const strength = lv.state !== "live" ? "" : sit.en ? `${d[sit.en]} EMPTY NET`
      : sit.pp ? `${d[sit.pp]} POWER PLAY${sit.left ? ` ${sit.left}` : ""}` : "";
    const fit = (s, room, max) => Math.min(max, room / (Math.max(1, s.length) * 0.6)).toFixed(1);
    const halo = `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="${A.ink.halo}" filter="url(#pbp-ar-soft)"/>${now
      ? `<text class="pbp-lit-num" x="${cx}" y="${(strength ? cy - 2 : cy + 8).toFixed(1)}" font-size="${fit(now.t, 168, 25)}"
        text-anchor="middle" fill="url(#pbp-ar-gold)" filter="url(#pbp-ar-glow)"${now.a}>${escapeHtml(now.t)}</text>` : ""}${strength
      ? `<text x="${cx}" y="${cy + 16}" font-size="${fit(strength, 156, 15)}" text-anchor="middle" letter-spacing=".6"
        fill="url(#pbp-ar-silver)" filter="url(#pbp-ar-glow)">${escapeHtml(strength)}</text>` : ""}`;
    out = pbpLedLine(A.ring, score, 24, blink, A.ink.ring) + halo + pbpLedLine(A.boards, score, 15, blink, A.ink.boards);
    if (moment.word === "GOAL" && moment.side) {
      // The main screen says it, and the lamp behind the net it went in burns.
      const [x, y, lx] = A.nets[moment.side];
      out += `<polygon points="${A.screen.map(([px, py]) => `${px},${py}`).join(" ")}" fill="${A.ink.screen}"
        filter="url(#pbp-ar-soft)"/>
        <g class="pbp-sb-moment" style="--t:${since}ms">${pbpOnQuad(A.screen, 50, [
          [50, 31, `<text class="pbp-lit-num" font-size="27" text-anchor="middle" fill="url(#pbp-ar-gold)">GOAL</text>`],
          [50, 44, `<text font-size="9" text-anchor="middle" fill="${pbpBoardColor(d[moment.side], league)}" letter-spacing=".8">${
            escapeHtml(d[moment.side])}</text>`]])}</g>
        <g class="pbp-lamp" style="--t:${since}ms"><ellipse cx="${x}" cy="${y - 18}" rx="110" ry="70" fill="url(#pbp-ar-lamp)"/>
          <rect x="${lx - 10}" y="${y - 84}" width="20" height="14" rx="5" fill="${L.lamp}" filter="url(#pbp-ar-glow)"/></g>`;
    }
  }
  return `<defs>${pbpLitDefs("pbp-ar", 2.2, 1.6)}<radialGradient id="pbp-ar-lamp"><stop offset="0" stop-color="${L.lamp}" stop-opacity=".6"/>
      <stop offset="1" stop-color="${L.lamp}" stop-opacity="0"/></radialGradient></defs>
    <g class="pbp-board pbp-arena">${out}</g>${moment.big && since < PBP_BOOM_MS
      ? pbpBoomSVG(A.boom, moment.side ? pbpBoardColor(d[moment.side], league) : "", since, 6.5, true) : ""}`;
}
/* THE BIG MOMENT ON A PHONE. A phone shows every picture whole or cropped
   to its play, and a board's words there are a few pixels high: the moment
   gets a lit banner over the picture in the boards' own face, in, three
   blinks and out (css/detail.css; a wide screen reads the boards). It sits
   where its picture has room: the ballpark's sky, under the field's board,
   an arena's corner. */
function pbpMomentBannerHTML(d, league) {
  const m = _pbpBoardLast && _pbpBoardLast.id === `${league}:${d.away}@${d.home}` ? _pbpBoardLast.moment : null;
  if (!m || !m.word || !(Date.now() - m.at < PBP_MOMENT_UP_MS)) return "";
  const where = league === "nfl" || league === "cfb" ? " pbp-mb-below" : league === "mlb" ? "" : " pbp-mb-left";
  const team = m.side ? String(d[m.side] || "") : "";
  return `<div class="pbp-moment-banner${where}" style="--t:${Date.now() - m.at}ms" aria-hidden="true"><b>${
    escapeHtml(m.word)}</b>${team ? `<span>${escapeHtml(team)}</span>` : ""}</div>`;
}

async function renderPbpPage() {
  const host = document.getElementById("pbp-body");
  if (!host) return;
  if (_pbpTimer) { clearTimeout(_pbpTimer); _pbpTimer = null; }
  const { league, event } = state.pbp || {};
  const way = pbpBack();
  const back = `<button class="btn ghost gp-back" id="pbp-back" style="margin-top:14px">${way.label}</button>`;
  const wire = () => {
    const b = document.getElementById("pbp-back");
    if (b) b.addEventListener("click", () => { markBackNav(); switchView(way.view); });
    host.querySelectorAll(".pbp-chip.door").forEach((el) =>
      el.addEventListener("click", () => (el.dataset.pbpGame
        ? openGame(el.dataset.pbpGame) : openPbp(league, el.dataset.pbp))));
    const m = document.getElementById("pbp-more");
    if (m) m.addEventListener("click", () => { _pbpShowAll = true; renderPbpPage(); });
    const g = document.getElementById("pbp-game-door");
    if (g) g.addEventListener("click", () => openGame(g.dataset.gid));
    host.querySelectorAll("[data-pbp-tab]").forEach((b) =>
      b.addEventListener("click", () => { _pbpTab = b.dataset.pbpTab; renderPbpPage(); }));
    // The box score's team toggle (js/gamecast.js keeps the choice).
    host.querySelectorAll("[data-gc-team]").forEach((b) =>
      b.addEventListener("click", () => {
        if (window.QBGamecast) window.QBGamecast.setTeam(b.dataset.gcTeam);
        renderPbpPage();
      }));
  };
  if (!league || !event) {
    host.innerHTML = `${emptySlate("stadium", "No game selected",
      "Open a game in progress from the Live tab or the board to read its play-by-play.")}${back}`;
    wire();
    return;
  }
  let d = null;
  let strip = [];
  try {
    // Through boardFetch, like every other board file: a fetch that
    // fails here must count toward the wire-down banner, not vanish.
    const [res, games] = await Promise.all([
      boardFetch(`data/pbp/${encodeURIComponent(league)}_${encodeURIComponent(event)}.json`,
                 { cache: "no-store" }),
      pbpStripGames(league),
      // The league's standings, for the two teams' under-pressure rates
      // (2026-09-08): cached after the first read, so the card draws
      // synchronously with the rest of the page on every pass.
      pressureWarm([league]),
    ]);
    strip = games;
    if (res.ok) d = await res.json();
  } catch (e) { d = null; }
  if (state.view !== "pbp") return;                // moved on while fetching
  const again = () => {
    _pbpTimer = setTimeout(() => {
      _pbpTimer = null;
      if (state.view === "pbp") renderPbpPage();
    }, 12000);
  };
  const stripHTML = pbpStripHTML(league, strip, event);
  // A chip counting down its last hour: the page's timer ticks it, whichever
  // way the page goes on to draw itself (each draws it synchronously).
  if (stripHTML.includes("data-pbp-count")) pbpCountStart();
  if (!d) {
    host.innerHTML = `${stripHTML}${emptySlate("stadium", "No play-by-play on file for this game",
      "The file is written while a game is in progress — up to eight games at a "
      + "time — and kept for about a day and a half. A game past that cap keeps its "
      + "score and has no play list; one that has just kicked off gets its file on "
      + "the next pass.")}${back}`;
    wire();
    again();                                       // it may appear on the next pass
    return;
  }
  const lv = d.live || {};
  const mark = (abbr) => teamMarkIn(league, abbr, 44);
  const name = (abbr, full) => escapeHtml(full || teamNameIn(league, abbr) || abbr || "");
  let situation = escapeHtml(lv.period || "");
  if (lv.clock) situation += ` ${escapeHtml(lv.clock)}`;
  if (league === "mlb" && lv.outs != null) situation += ` · ${lv.outs} out${lv.outs === 1 ? "" : "s"}`;
  if (lv.detail && league !== "mlb") situation += ` · ${escapeHtml(lv.detail)}`;
  if (liveHoldWord(lv)) situation += ` · ${escapeHtml(liveHoldWord(lv))}`;
  const stateWord = lv.state === "live" && liveHoldWord(lv)
      ? liveHoldWord(lv).split(/\s[\u2014-]\s/)[0].toUpperCase()
    : lv.state === "live" ? `${icon("dot", 10)} LIVE`
    : lv.state === "final" ? "FINAL" : "SCHEDULED";
  // The league's board, when the visitor is standing on it: faces, the
  // park's facts, the weather, the live win-probability track.
  const boardGame = (state.sport === league && state.data)
    ? ((state.data.games || []).find((x) => x.home === d.home && x.away === d.away) || null) : null;
  const faces = pbpFaces(league);
  const events = d.events || [];
  // THE PLAY THE ART DRAWS. Baseball wants the newest ball actually hit;
  // football wants simply the newest play, and reads it from `plays`
  // rather than `events` because the football deep file has no `events`
  // — livescore_build writes `drives` and a flattened `plays`, and the
  // MLB builder is the only one that writes `events`. Renamed from
  // `lastHit` when football joined: it is not a hit any more.
  const lastPlay = PBP_FOOTBALL.has(league)
    ? ((d.plays || []).slice().reverse().find((r) => r && r.kind === "football") || null)
    : (events.slice().reverse().find((r) => r.kind === "atbat" && r.hit) || null);
  const park = (boardGame || {}).park || {};
  const wx = (boardGame || {}).weather || {};
  /* THE TILE IS A LABEL AND A VALUE, IN THAT ORDER. These read
     `60°F` over nothing, `6 mph` over nothing and `Roof: outdoors` over
     `fieldturf` — three tiles where the big text was sometimes the
     value and sometimes the label, and one where the small text was a
     second fact with no name on it. A reader should not have to work
     out which of the two lines is the question. */
  const infoCards = boardGame ? [
    park.name ? [icon("stadium", 18), "Venue", park.name] : null,
    boardGame.roof ? [icon("field", 18), "Roof",
      PBP_ROOF_WORD[String(boardGame.roof).toLowerCase()] || pbpTitleCase(boardGame.roof)] : null,
    boardGame.surface ? [icon("field", 18), "Surface",
      PBP_SURFACE_WORD[String(boardGame.surface).toLowerCase()] || pbpTitleCase(boardGame.surface)] : null,
    wx.temp_f != null ? [icon("sun", 18), "Temperature", `${Math.round(wx.temp_f)}°F`] : null,
    wx.wind_mph != null && !wx.dome
      ? [icon("wind", 18), "Wind",
         `${Math.round(wx.wind_mph)} mph${wx.wind_dir ? ` ${wx.wind_dir}` : ""}`] : null,
    park.capacity ? [icon("users", 18), "Capacity", Number(park.capacity).toLocaleString()] : null,
  ].filter(Boolean) : [];
  const factsHTML = infoCards.length ? `<div class="pbp-info">${infoCards.map(([ic, label, val]) => `
      <div class="pbp-info-card"><span class="pbp-info-ico">${ic}</span>
        <div><div class="pbp-info-k">${escapeHtml(label)}</div>
          <b>${escapeHtml(String(val))}</b></div></div>`).join("")}
    </div>` : "";
  /* THE TOTALS LEAD, because they are about the game being watched and
     the park facts are about the building. The room used to be the
     building alone, over half a screen of nothing. */
  const totalsHTML = pbpTotalsHTML(d, league);
  const infoPanel = (totalsHTML || factsHTML)
    ? `${totalsHTML}${factsHTML}`
    : `<p class="rail-quiet">Team totals fill in from the drives as they are played. Park and
       weather facts come off the league’s board — open the ${
       escapeHtml(LEAGUE_LABEL[league] || league.toUpperCase())} tab for them.</p>`;
  /* THE GAMECAST (2026-10-08): football, hoops and hockey draw ESPN's
     tab set from js/gamecast.js — the drive in progress, the last play
     with the players in it, the leaders, the whole box score, the drives,
     the team stats. Loaded on the first live game opened; until it lands
     the panel says so and the page redraws itself when it does. Baseball
     keeps its own four rooms. */
  const tabs = pbpTabsFor(league);
  const tab = tabs.some(([k]) => k === _pbpTab) ? _pbpTab : tabs[0][0];
  const GC = league === "mlb" ? null : (window.QBGamecast || null);
  // Baseball loads it too, for the at-bat's pitches (QBGamecast.zone).
  if (!window.QBGamecast) {
    loadGamecast().then((mod) => { if (mod && state.view === "pbp") renderPbpPage(); });
  }
  // Basketball: Ethan's render, its own page (js/hoopscast.js via QBGamecast.hoops).
  if (GC && GC.hoops && GC.hoops(host, { d, league, stripHTML, back, boardGame, faces, wire })) { if (lv.state === "live") again(); return; }
  const panel = tab === "props" ? pbpPropsHTML(d, league)
    : tab === "injuries" ? pbpInjuriesHTML(d, league)
    : tab === "players" ? pbpPlayersHTML(d, league)
    : league === "mlb" ? infoPanel
    : GC ? GC.panel(tab, { d, league, faces, boardGame })
    : `<p class="rail-quiet">Loading the gamecast…</p>`;
  const infoHTML = `${pbpTabsHTML(tab, boardGame, tabs)}<div class="pbp-panel" data-pbp-panel="${tab}">${panel}</div>`;
  const winProb = boardGame && boardGame.line_track ? `<div class="card">${lineTrackHTML(boardGame)}</div>` : "";
  // The two records and the carrier (ESPN's header: "TB 0-4", "Prime
  // Video"), from the summary's header and the scoreboard — absent, nothing.
  const rec = (abbr) => (d.records || {})[abbr]
    ? `<div class="mini pbp-hero-rec">${escapeHtml((d.records || {})[abbr])}</div>` : "";
  // Live, the Watch button already names the carrier; the pill is for
  // before and after, when there is no button.
  const carrier = (d.tv || [])[0] && lv.state !== "live"
    ? `<span class="pbp-hero-tv">${escapeHtml((d.tv || [])[0])}</span>` : "";
  host.innerHTML = `
    ${stripHTML}
    <div class="pbp-layout">
      <div class="pbp-main">
        <div class="card pbp-hero">
          <div class="pbp-hero-side">${mark(d.away)}<div><div class="mini">${escapeHtml(LEAGUE_LABEL[league] || league.toUpperCase())}</div>
            <b>${name(d.away, d.away_name)}</b>${rec(d.away)}</div></div>
          <b class="pbp-hero-score">${lv.away_score != null ? lv.away_score : "–"}</b>
          <div class="pbp-hero-mid"><span class="lb-live">${stateWord}</span><span class="lb-sit">${situation}</span>${carrier}
            <span class="mini" style="opacity:.6">${escapeHtml(pbpAgo(d.generated_at))}</span></div>
          <b class="pbp-hero-score">${lv.home_score != null ? lv.home_score : "–"}</b>
          <div class="pbp-hero-side pbp-hero-home"><div><div class="mini">&nbsp;</div>
            <b>${name(d.home, d.home_name)}</b>${rec(d.home)}</div>${mark(d.home)}</div>
          ${lv.state === "live" ? watchHTML(d, league, "pbp-watch") : ""}
        </div>
        <div class="card pbp-parkcard">
          ${pbpParkHeadHTML(league, boardGame)}
          ${pbpParkHTML(d, league, boardGame, lastPlay)}
          ${pbpSituationHTML(d, league, faces)}${league === "mlb" && window.QBGamecast && QBGamecast.zone ? QBGamecast.zone(d) : ""}
        </div>
        ${infoHTML}
        ${back}
      </div>
      <aside class="pbp-rail">
        <div class="card pbp-railcard">
          <div class="pbp-rail-head">Play by play <span class="mini">${(events.length || (d.plays || []).length)} on file</span></div>
          ${pbpRailHTML(d, league)}
        </div>
        ${winProb}
        ${pbpModelWinProbHTML(d)}
        ${pbpPressureHTML(d, league, boardGame)}
      </aside>
    </div>`;
  wire();
  if (host.querySelector("[data-pbp-count]")) pbpCountStart();
  if (lv.state === "live" || pbpStartsSoon(lv)) again();
}
