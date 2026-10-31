/* THE RACES (Ethan, 2026-10-29: "do all 3") — college football's playoff
   race and the NBA Cup, one page each league, loaded the first time it
   opens (app.js loadRoom). A classic script like app.js: it shares the
   page's globals, and `renderRace` here replaces app.js's stub.

   WHAT IS WHOSE. The field if it started today, the standings and the
   point differentials are facts — the poll, the scoreboard — and every
   reader of the file gets them. The chances, each game left at our price
   and the games that swing the race are our model's, and a reader without
   a plan is served the file with them emptied (engine/gate,
   PAID_KEYS_BY_FILE); the page says what is behind them, never a number. */

const RACE_FILES = { cfb: "cfp_race.json", nba: "nba_cup.json" };

/* A chance as a reader takes it in: whole points, and never "0%" or
   "100%" for something a run of the season merely did not see happen —
   a thousand draws that never put a team in the field say "<1%", because
   the next thousand might. Only a settled fact prints as a certainty. */
function rcPct(x) {
  if (x == null || !isFinite(x)) return "—";
  if (x <= 0) return "0%";
  if (x >= 1) return "100%";
  return x < 0.005 ? "<1%" : x > 0.995 ? ">99%" : `${Math.round(x * 100)}%`;
}

function rcDay(iso) {
  const s = String(iso || "").slice(0, 10);
  return (typeof formatGameDate === "function" && formatGameDate(s)) || s;
}

async function rcLoad(name) {
  try {
    const res = await paidFetch(name);
    return res.ok ? await res.json() : null;
  } catch (e) { return null; }
}

/* The model's half was emptied for this reader (engine/gate.redact). */
function rcLocked(d) {
  return !!(d && d.locked) && !Object.keys(d.chances || {}).length;
}

async function renderRace() {
  const host = document.getElementById("race-body");
  if (!host) return;
  const sport = state.sport;
  const title = document.getElementById("race-title");
  const sub = document.getElementById("race-sub");
  const file = RACE_FILES[sport];
  if (title) title.childNodes[0].nodeValue = `${sport === "nba" ? "NBA Cup" : "College Football Playoff race"} `;
  if (!file) {
    if (sub) sub.textContent = "";
    host.innerHTML = `<div class="empty-slate"><h3>No race for this league</h3>
      <p>The race pages are college football’s playoff and the NBA Cup.</p></div>`;
    return;
  }
  host.innerHTML = `<div class="rc-wait" role="status">Loading the race…</div>`;
  const d = await rcLoad(file);
  if (state.view !== "race" || state.sport !== sport) return;
  if (!d || (!d.today && !d.groups)) {
    host.innerHTML = `<div class="empty-slate"><h3>The race has not been built yet</h3>
      <p>It is played out on every ${sport === "nba" ? "NBA" : "college"} build; the next one fills this page.</p></div>`;
    return;
  }
  if (sub) sub.textContent = sport === "nba"
    ? `— the groups, the differential tiebreaker and our chances, ${Number(d.sims || 0).toLocaleString()} tournaments played out.`
    : `— 12 teams. Our game model plays the rest of the season ${Number(d.sims || 0).toLocaleString()} times.`;
  host.innerHTML = sport === "nba" ? cupHTML(d) : cfpHTML(d);
}

/* ---------------- college football ---------------- */

function rcSide(s, sport) {
  if (!s) return `<div class="rc-side rc-empty">—</div>`;
  return `<div class="rc-side">${teamMarkIn(sport, s.team, 22)}<span class="rc-seed">${s.seed}</span>
    <b class="rc-name">${escapeHtml(s.name || s.team)}</b>
    <span class="rc-meta">${s.rank ? `#${s.rank} · ` : ""}${escapeHtml(s.record || "")}${
      s.bid ? ` · ${escapeHtml(s.bid)}` : ""}</span></div>`;
}

/* THE FIELD IF IT STARTED TODAY. The four bye seeds in one column, each
   with the first-round game whose winner it meets (1 meets 8/9, 2 meets
   7/10, 3 meets 6/11, 4 meets 5/12, the 2026 bracket), and the four
   first-round games in the next, at the better seed's campus. Each team
   wears the reason it is in — a conference leader, the Group of Six's best,
   Notre Dame in the top twelve, or at large — because "why is that team
   here" is the first question a bracket gets. */
function cfpBracketHTML(d) {
  const t = d.today || {};
  const by = {};
  (t.seeds || []).forEach((s) => { by[s.seed] = s; });
  const fr = ((d.format || {}).first_round || [[5, 12], [6, 11], [7, 10], [8, 9]]);
  // Each bye seed meets this first-round game's winner (engine/cfprace QUARTERS).
  const meets = { 1: [8, 9], 2: [7, 10], 3: [6, 11], 4: [5, 12] };
  const poll = (d.poll || {}).name || "the poll";
  const out = (t.first_four_out || []).map((x) => `${escapeHtml(x.name || x.team)}${x.rank ? ` (#${x.rank})` : ""}`).join(", ");
  return `<div class="section-title">If it started today
      <span class="sub">— ${escapeHtml(poll)} as the ranking, today’s conference leaders as the champions.</span></div>
    <div class="rc-brk">
      <div class="rc-col"><div class="rc-col-h">Byes</div>
        ${[1, 2, 3, 4].map((n) => `<div class="rc-match">${rcSide(by[n], "cfb")}
          <span class="rc-host">meets the ${meets[n].join("/")} winner</span></div>`).join("")}</div>
      <div class="rc-col"><div class="rc-col-h">First round · Dec 18–19</div>
        ${fr.map(([a, b]) => `<div class="rc-match">${rcSide(by[a], "cfb")}${rcSide(by[b], "cfb")}
          <span class="rc-host">${by[a] ? `at ${escapeHtml(by[a].name || by[a].team)}` : ""}</span></div>`).join("")}</div>
    </div>
    ${out ? `<p class="rc-note">First four out: ${out}.</p>` : ""}`;
}

function cfpTeamsHTML(d) {
  const ch = d.chances || {}, rem = d.remaining || {};
  const rows = (d.teams || []).filter((r) => ch[r.team]);
  if (!rows.length) return "";
  return `<div class="section-title">The contenders
      <span class="sub">— each one’s chances, and every game it has left at our price. Tap a team.</span></div>
    <div class="rc-card rc-flush">
      <div class="rc-row rc-head"><span>Team</span><span>In</span><span>Bye</span><span>Conf</span><span>Title</span><span>Win out</span></div>
      ${rows.map((r) => {
        const c = ch[r.team];
        const games = rem[r.team] || [];
        const ifOut = c.in_if_win_out != null ? ` · in ${rcPct(c.in_if_win_out)} of the times it does` : "";
        return `<details class="rc-team">
          <summary class="rc-row">
            <span class="rc-who">${teamMarkIn("cfb", r.team, 22)}<span><b>${r.rank ? `#${r.rank} ` : ""}${escapeHtml(r.name || r.team)}</b>
              <small>${escapeHtml(r.record)} · ${escapeHtml(r.conference === "FBS Independents" ? "Independent" : r.conference)}</small></span></span>
            <span class="rc-p rc-lead">${rcPct(c.playoff)}</span><span class="rc-p">${rcPct(c.bye)}</span>
            <span class="rc-p">${rcPct(c.conf)}</span><span class="rc-p">${rcPct(c.title)}</span>
            <span class="rc-p">${rcPct(c.win_out)}</span></summary>
          <div class="rc-games">
            ${games.length ? games.map((g) => `<span class="rc-game">${escapeHtml(rcDay(g.date))} ·
              ${g.home ? "vs" : g.neutral ? "vs" : "at"} ${escapeHtml(g.opp)}
              <b class="${g.p >= 0.5 ? "pos" : "neg"}">${rcPct(g.p)}</b></span>`).join("")
              : `<span class="rc-game">No regular-season games left.</span>`}
            <p class="rc-note">Projected ${c.proj ? `${c.proj[0]}–${c.proj[1]}` : "—"}${
              c.seed != null ? ` · average seed ${c.seed} when in` : ""} · wins out ${rcPct(c.win_out)}${ifOut}.</p>
          </div></details>`;
      }).join("")}
    </div>`;
}

/* THE GAMES THAT SWING IT: each of this week's games that moves the field
   most, with every team it moves — that team's chance to get in if the
   home side wins, and if it loses. The better of the two is green for that
   team, so a reader scanning for their own side sees at once whom to
   root for, including in games their team is not playing in. */
function cfpSwingHTML(d) {
  const sw = d.swing || [];
  if (!sw.length) return "";
  const nm = (t) => {
    const r = (d.teams || []).find((x) => x.team === t);
    return (r && r.name) || t;
  };
  return `<div class="section-title">The games that swing it
      <span class="sub">— this week’s games that move the field most: each team’s chance to make it, either way the game goes.</span></div>
    <div class="rc-grid">${sw.map((g) => `<div class="rc-card">
      <div class="rc-sw-h">${teamMarkIn("cfb", g.away, 20)}<b>${escapeHtml(g.away_name || g.away)}</b>
        ${g.neutral ? "vs" : "at"} ${teamMarkIn("cfb", g.home, 20)}<b>${escapeHtml(g.home_name || g.home)}</b></div>
      <p class="rc-note">${escapeHtml(rcDay(g.date))} · ${escapeHtml(g.home_name || g.home)} ${rcPct(g.p_home)} to win</p>
      <div class="rc-row rc-sw rc-head"><span>To get in</span><span>${escapeHtml(g.home_name || g.home)} win</span>
        <span>${escapeHtml(g.away_name || g.away)} win</span></div>
      ${(g.moves || []).map((m) => `<div class="rc-row rc-sw"><span class="rc-who"><span>${escapeHtml(nm(m.team))}</span></span>
        <span class="rc-p ${m.if_home > m.if_away ? "pos" : "neg"}">${rcPct(m.if_home)}</span>
        <span class="rc-p ${m.if_away > m.if_home ? "pos" : "neg"}">${rcPct(m.if_away)}</span></div>`).join("")}
    </div>`).join("")}</div>`;
}

function cfpStandingsHTML(d) {
  const st = d.standings || {};
  const confs = Object.keys(st);
  if (!confs.length) return "";
  return `<div class="section-title">The conferences
      <span class="sub">— by conference record; the top two meet in each title game.</span></div>
    ${confs.map((c, i) => `<details class="rc-card rc-flush rc-conf"${i ? "" : " open"}>
      <summary class="rc-conf-h">${escapeHtml(c)}</summary>
      ${st[c].map((r, k) => `<div class="rc-row rc-crow"><span class="rc-who">${teamMarkIn("cfb", r.team, 18)}
        <span>${k + 1}. ${r.rank ? `#${r.rank} ` : ""}${escapeHtml(r.name || r.team)}</span></span>
        <span class="rc-p">${escapeHtml(r.conf)}</span><span class="rc-p">${escapeHtml(r.all)}</span></div>`).join("")}
    </details>`).join("")}`;
}

function cfpHTML(d) {
  const locked = rcLocked(d);
  const a = d.assumptions || {};
  return `${cfpBracketHTML(d)}
    ${locked ? memberLockHTML("Our chances are for members",
      "Every contender’s chance to make the twelve, earn a bye, win its conference and win it all — each game it has left at our price, and the games this week that swing the field.")
      : cfpTeamsHTML(d) + cfpSwingHTML(d)}
    ${cfpStandingsHTML(d)}
    <p class="rc-note">The 2026 format: the four Power Four champions and the highest-ranked Group of Six team get in
      automatically, Notre Dame does in the top 12, and the rest are at large; seeded 1–12 straight off the
      committee’s final ranking, with 1–4 off the first round. ${locked ? "" : `Our final ranking in each run is a stand-in for the
      committee — a team’s rating plus ${a.win_points || 8} points for every win above what an elite team would manage
      against the same schedule, and ${a.champ_points || 4} for a title. Those two weights are assumptions, not a fit to
      past committees. Title games are between the two best conference records, ties to the better rating.`}
      ${d.generated_at ? `Built ${escapeHtml(String(d.generated_at).replace("T", " ").slice(0, 16))}.` : ""}</p>`;
}

/* ---------------- the NBA Cup ---------------- */

/* ONE GROUP: the table in the league's own order (the engine applies the
   tiebreakers, so the rows already stand as they would be read out), the
   differential in its own coloured column because it is the tiebreaker
   most often reached, and for a member each game left listed once — from
   the home side — with our chance and the margin we expect, since a margin
   is what moves the differential. */
function cupGroupHTML(name, rows, d, locked) {
  const ch = d.chances || {}, rem = d.remaining || {};
  const today = d.today || {};
  // NO ONE LEADS BEFORE A GAME IS PLAYED: at 0-0 the order is our rating's,
  // and a tag would put a claim on it (the 2026-10-30 audit, the night
  // before group play).
  const started = (d.played || 0) > 0;
  const leader = started ? (today.winners || {})[name] : "";
  const wild = started ? Object.values(today.wildcards || {}) : [];
  const left = [];
  rows.forEach((r) => (rem[r.team] || []).forEach((g) => { if (g.home) left.push({ ...g, team: r.team }); }));
  return `<div class="rc-card rc-flush">
    <div class="rc-conf-h">${escapeHtml(name)}</div>
    <div class="rc-row rc-cup rc-head"><span>Team</span><span>W-L</span><span>Diff</span><span>Pts</span><span>Left</span>${
      locked ? "" : "<span>Adv</span>"}</div>
    ${rows.map((r) => `<div class="rc-row rc-cup${r.team === leader ? " rc-lead-row" : ""}">
      <span class="rc-who">${teamMarkIn("nba", r.team, 20)}<span>${escapeHtml(teamNameIn("nba", r.team))}${
        r.team === leader ? `<small class="pos">leads the group</small>` : wild.includes(r.team) ? `<small>holds the wild card</small>` : ""}</span></span>
      <span class="rc-p">${r.w}-${r.l}</span>
      <span class="rc-p rc-pd ${r.pd > 0 ? "pos" : r.pd < 0 ? "neg" : ""}">${r.pd > 0 ? "+" : ""}${r.pd}</span>
      <span class="rc-p">${r.pf}</span><span class="rc-p">${r.left}</span>
      ${locked ? "" : `<span class="rc-p rc-lead">${rcPct((ch[r.team] || {}).advance)}</span>`}</div>`).join("")}
    ${!locked && left.length ? `<details class="rc-left"><summary>Group games left, at our price</summary>
      ${left.sort((x, y) => (x.date < y.date ? -1 : 1)).map((g) => `<span class="rc-game">${escapeHtml(rcDay(g.date))} ·
        ${escapeHtml(teamNameIn("nba", g.opp))} at ${escapeHtml(teamNameIn("nba", g.team))}
        <b class="${g.p >= 0.5 ? "pos" : "neg"}">${escapeHtml(teamNameIn("nba", g.team))} ${rcPct(g.p)}</b>
        <small>by ${Math.abs(g.margin).toFixed(1)} ${g.margin >= 0 ? "" : "the other way"}</small></span>`).join("")}</details>` : ""}
  </div>`;
}

/* THE WILD CARD RACE, by conference: every club that is not leading its
   group, best record first, then the differential, then points — the
   league's order for the wild card, which has no head-to-head because the
   clubs come from different groups. The holder is the engine's own pick,
   so this list and the tag can never disagree about who holds it. */
function cupWildHTML(d) {
  const g = d.groups || {}, today = d.today || {};
  return ["East", "West"].map((conf) => {
    const leaders = Object.entries(today.winners || {}).filter(([k]) => k.startsWith(conf)).map(([, t]) => t);
    const rest = Object.entries(g).filter(([k]) => k.startsWith(conf)).flatMap(([, rows]) => rows)
      .filter((r) => !leaders.includes(r.team))
      .sort((a, b) => (b.w - b.l) - (a.w - a.l) || b.w - a.w || b.pd - a.pd || b.pf - a.pf).slice(0, 4);
    return `<div class="rc-card rc-flush"><div class="rc-conf-h">${conf} wild card</div>
      ${rest.map((r) => `<div class="rc-row rc-crow"><span class="rc-who">${teamMarkIn("nba", r.team, 18)}
        <span>${escapeHtml(teamNameIn("nba", r.team))}${(d.played || 0) > 0 && (today.wildcards || {})[conf] === r.team ? `<small class="pos">holds it today</small>` : ""}</span></span>
        <span class="rc-p">${r.w}-${r.l}</span><span class="rc-p rc-pd ${r.pd > 0 ? "pos" : r.pd < 0 ? "neg" : ""}">${r.pd > 0 ? "+" : ""}${r.pd}</span></div>`).join("")}
    </div>`;
  }).join("");
}

function cupOddsHTML(d) {
  const ch = d.chances || {};
  const rows = Object.entries(ch).sort((a, b) => b[1].cup - a[1].cup || b[1].advance - a[1].advance).slice(0, 10);
  if (!rows.length) return "";
  return `<div class="section-title">To win the Cup
      <span class="sub">— our chances through every round: out of the group, the quarterfinal, the semifinal, the final.</span></div>
    <div class="rc-card rc-flush">
      <div class="rc-row rc-head"><span>Team</span><span>Adv</span><span>Semis</span><span>Final</span><span>Cup</span></div>
      ${rows.map(([t, c]) => `<div class="rc-row"><span class="rc-who">${teamMarkIn("nba", t, 20)}<span>${escapeHtml(teamNameIn("nba", t))}</span></span>
        <span class="rc-p">${rcPct(c.advance)}</span><span class="rc-p">${rcPct(c.semis)}</span>
        <span class="rc-p">${rcPct(c.final)}</span><span class="rc-p rc-lead">${rcPct(c.cup)}</span></div>`).join("")}
    </div>`;
}

function cupHTML(d) {
  const locked = rcLocked(d);
  const g = d.groups || {};
  const ko = d.knockouts || {};
  const win = d.window || [];
  const started = (d.played || 0) > 0;
  return `<p class="rc-note rc-lede">${started ? `${plural(d.played, "group game")} played, ${d.games_left} left` : "Group play has not started"}
      · group nights ${escapeHtml(rcDay(win[0]))} – ${escapeHtml(rcDay(win[1]))} · quarterfinals ${escapeHtml(rcDay(ko.quarterfinals))}
      and semifinals ${escapeHtml(rcDay(ko.semifinals))} at the better seed’s arena · the final ${escapeHtml(rcDay(ko.final))}, Indianapolis.</p>
    <div class="section-title">The groups
      <span class="sub">— each group’s winner goes through, and the best of the rest in each conference.</span></div>
    <div class="rc-grid">${Object.entries(g).map(([name, rows]) => cupGroupHTML(name, rows, d, locked)).join("")}</div>
    <div class="section-title">The wild card race
      <span class="sub">— no head-to-head here: record, then point differential, then points.</span></div>
    <div class="rc-grid">${cupWildHTML(d)}</div>
    <div class="rc-card"><b>How a tie is broken</b>
      <ol class="rc-tb">${(d.tiebreakers || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ol>
      <p class="rc-note">A group game that goes to overtime counts zero in the differential, so a team cannot run it up
        in extra time — and its overtime points count toward nothing.</p></div>
    ${locked ? memberLockHTML("Our chances are for members",
      "Every team’s chance to win its group, take the wild card, reach the final and win the Cup — and every group game left at our price and margin.")
      : cupOddsHTML(d)}
    ${d.generated_at ? `<p class="rc-note">Built ${escapeHtml(String(d.generated_at).replace("T", " ").slice(0, 16))}.</p>` : ""}`;
}
