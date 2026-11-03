/* THE RACES (Ethan, 2026-10-29: "do all 3"; the NFL's, 2026-11-03: "do all
   of them") — the NFL's and college football's playoff races and the NBA
   Cup, one page each league, loaded the first time it
   opens (app.js loadRoom). A classic script like app.js: it shares the
   page's globals, and `renderRace` here replaces app.js's stub.

   WHAT IS WHOSE. The field if it started today, the standings and the
   point differentials are facts — the poll, the scoreboard — and every
   reader of the file gets them. The chances, each game left at our price
   and the games that swing the race are our model's, and a reader without
   a plan is served the file with them emptied (engine/gate,
   PAID_KEYS_BY_FILE); the page says what is behind them, never a number. */

const RACE_FILES = { nfl: "nfl_race.json", cfb: "cfp_race.json", nba: "nba_cup.json" };
const RACE_TITLES = { nfl: "NFL playoff race", cfb: "College Football Playoff race", nba: "NBA Cup" };

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
  if (title) title.childNodes[0].nodeValue = `${RACE_TITLES[sport] || "Playoff race"} `;
  if (!file) {
    if (sub) sub.textContent = "";
    host.innerHTML = `<div class="empty-slate"><h3>No race for this league</h3>
      <p>The race pages are the NFL’s and college football’s playoffs and the NBA Cup.</p></div>`;
    return;
  }
  host.innerHTML = `<div class="rc-wait" role="status">Loading the race…</div>`;
  const d = await rcLoad(file);
  if (state.view !== "race" || state.sport !== sport) return;
  if (!d || (!d.today && !d.groups)) {
    host.innerHTML = `<div class="empty-slate"><h3>The race has not been built yet</h3>
      <p>It is played out on every ${sport === "nba" ? "NBA" : sport === "nfl" ? "NFL" : "college"} build; the next one fills this page.</p></div>`;
    return;
  }
  if (sub) sub.textContent = sport === "nba"
    ? `— the groups, the differential tiebreaker and our chances, ${Number(d.sims || 0).toLocaleString()} tournaments played out.`
    : sport === "nfl"
      ? `— 14 teams, 7 a conference. Our ratings play the rest of the season ${Number(d.sims || 0).toLocaleString()} times.`
      : `— 12 teams. Our game model plays the rest of the season ${Number(d.sims || 0).toLocaleString()} times.`;
  host.innerHTML = sport === "nba" ? cupHTML(d) : sport === "nfl" ? nflHTML(d) : cfpHTML(d);
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

/* THE PLAYOFF ITSELF, FROM SELECTION DAY (engine/cfprace.playoff_bracket,
   2026-11-03; Ethan, on the audit's "College Football Playoff bracket after
   selection day": "do all of them"). The twelve the committee named, every
   round — the first round on the higher seed's campus, the quarterfinals
   and on in the bowls — each score as it lands with the winner in bold, and
   the champion on top. Our line on each game still to play and each team's
   chance to reach each round are a member's (`bracket_lines`, `chances`). */
function cfpKoSide(d, team, seed, score, won, tbd) {
  if (!team) return `<div class="rc-side rc-empty"><span></span><span></span><span class="rc-name">${escapeHtml(tbd)}</span></div>`;
  const s = ((d.bracket || {}).seeds || []).find((x) => x.team === team) || {};
  return `<div class="rc-side${won === true ? " rc-won" : won === false ? " rc-lost" : ""}">${teamMarkIn("cfb", team, 22)}
    <span class="rc-seed">${seed || ""}</span><b class="rc-name">${escapeHtml(s.name || team)}</b>
    ${score != null ? `<span class="rc-score">${escapeHtml(String(score))}</span>` : ""}</div>`;
}
function cfpKoGameHTML(d, g, tbd) {
  if (!g) return "";
  const b = d.bracket || {};
  const nm = (t) => ((b.seeds || []).find((x) => x.team === t) || {}).name || t;
  const line = (d.bracket_lines || {})[g.id];
  const where = g.neutral ? (g.bowl || "neutral site") : (g.home ? `at ${nm(g.home)}` : "at the higher seed");
  return `<div class="rc-match rc-ko${g.done ? " rc-done" : ""}">
    ${cfpKoSide(d, g.home, g.home_seed, g.home_score, g.done ? g.winner === g.home : null, tbd[0])}
    ${cfpKoSide(d, g.away, g.away_seed, g.away_score, g.done ? g.winner === g.away : null, tbd[1])}
    <span class="rc-host">${g.date ? `${escapeHtml(rcDay(g.date))} · ` : ""}${escapeHtml(where)}${g.done ? " · final score" : ""}${
      line && !g.done ? ` · our line ${escapeHtml(nm(g.home))} <b>${rcPct(line.p_home)}</b>` : ""}</span></div>`;
}
function cfpPlayoffHTML(d, locked) {
  const b = d.bracket || {};
  const nights = b.nights || {};
  const span = (k) => (nights[k] || []).map(rcDay).join(" – ");
  const nm = (t) => ((b.seeds || []).find((x) => x.team === t) || {}).name || t;
  const fr = b.first_round || [], qf = b.quarterfinals || [], sf = b.semifinals || [];
  const frLabel = (id) => { const g = fr.find((x) => x.id === id); return g ? `Winner of ${g.home_seed} v ${g.away_seed}` : "To be decided"; };
  const ch = d.chances || {};
  const odds = locked ? memberLockHTML("Our chances are for members",
      "Each team’s chance to reach the quarterfinals, the semifinals and the title game and to win it all — and our line on every playoff game still to play.")
    : `<div class="section-title">Our chances
        <span class="sub">— each of the twelve, to reach each round and to win it all, every result in kept.</span></div>
      <div class="rc-card rc-flush">
        <div class="rc-row rc-head"><span>Team</span><span>QF</span><span>Semis</span><span>Final</span><span>Title</span></div>
        ${(b.seeds || []).slice().sort((x, y) => ((ch[y.team] || {}).title || 0) - ((ch[x.team] || {}).title || 0)).map((s) => {
          const c = ch[s.team] || {};
          return `<div class="rc-row"><span class="rc-who">${teamMarkIn("cfb", s.team, 20)}<span><b>${s.seed} ${escapeHtml(s.name || s.team)}</b></span></span>
            <span class="rc-p">${rcPct(c.quarterfinals)}</span><span class="rc-p">${rcPct(c.semifinals)}</span>
            <span class="rc-p">${rcPct(c.final)}</span><span class="rc-p rc-lead">${rcPct(c.title)}</span></div>`;
        }).join("")}
      </div>`;
  return `${b.champion ? `<div class="rc-card rc-champ">${teamMarkIn("cfb", b.champion, 28)}<b>${escapeHtml(nm(b.champion))} win the national championship</b></div>` : ""}
    <div class="section-title">The College Football Playoff
      <span class="sub">— the twelve the committee named on selection day, seeded by its final ranking; the first round on the higher seed’s campus, the rest in the bowls.</span></div>
    <div class="rc-card"><b>The twelve</b>
      <ol class="rc-tb rc-twelve">${(b.seeds || []).map((s) => `<li>${escapeHtml(s.name || s.team)} <small>${escapeHtml(s.record || "")} · ${escapeHtml(s.bid || "")}</small></li>`).join("")}</ol></div>
    <div class="rc-brk">
      <div class="rc-col"><div class="rc-col-h">First round · ${escapeHtml(span("first_round"))}</div>
        ${fr.map((g) => cfpKoGameHTML(d, g, ["", ""])).join("")}</div>
      <div class="rc-col"><div class="rc-col-h">Quarterfinals · ${escapeHtml(span("quarterfinals"))}</div>
        ${qf.map((g) => cfpKoGameHTML(d, g, ["", frLabel((g.from || [])[0])])).join("")}</div>
      <div class="rc-col"><div class="rc-col-h">Semifinals · ${escapeHtml(span("semifinals"))}</div>
        ${sf.map((g) => cfpKoGameHTML(d, g, ["Quarterfinal winner", "Quarterfinal winner"])).join("")}</div>
      <div class="rc-col"><div class="rc-col-h">National championship · ${escapeHtml(span("final"))}</div>
        ${cfpKoGameHTML(d, b.final, ["Semifinal winner", "Semifinal winner"])}</div>
    </div>
    ${odds}
    ${cfpStandingsHTML(d)}
    ${d.generated_at ? `<p class="rc-note">Built ${escapeHtml(String(d.generated_at).replace("T", " ").slice(0, 16))}.</p>` : ""}`;
}

function cfpHTML(d) {
  const locked = rcLocked(d);
  const a = d.assumptions || {};
  if (d.bracket && d.bracket.set) return cfpPlayoffHTML(d, locked);
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

/* ---------------- the NFL ----------------
   Ethan, 2026-11-03 (the audit's list: "an NFL playoff race ... each team's
   chance at the playoffs, the seeds if it ended today, and the Sunday games
   that swing it"): "do all of them". engine/nflrace plays the rest of the
   season out; the seeds and the standings are the results', free, and the
   chances, the games left at our price and the swing games are members'. */

const RC_NFL_CONFS = ["AFC", "NFC"];

function rcNflName(t) { return (typeof teamNameIn === "function" && teamNameIn("nfl", t)) || t; }

/* IF THE SEASON ENDED TODAY: each conference's seven, the four division
   leaders first, then the wild cards; the one bye marked; then the clubs
   just outside and how far back of the seventh they are. */
function rcNflSeedsHTML(d) {
  const t = d.today || {};
  return `<div class="section-title">If the season ended today
      <span class="sub">— the four division leaders seeded 1–4, then the three best records left. Only the 1 seed rests the first weekend.</span></div>
    <div class="rc-brk">${RC_NFL_CONFS.map((c) => {
      const conf = t[c] || {};
      const hunt = conf.hunt || [];
      return `<div class="rc-col"><div class="rc-col-h">${c}</div>
        <div class="rc-match">${(conf.seeds || []).map((s) => `<div class="rc-side">${teamMarkIn("nfl", s.team, 22)}<span class="rc-seed">${s.seed}</span>
          <b class="rc-name">${escapeHtml(rcNflName(s.team))}</b>
          <span class="rc-meta">${escapeHtml(s.record)} · ${escapeHtml(s.why)}${s.seed === 1 ? " · the bye" : ""}</span></div>`).join("")}</div>
        ${hunt.length ? `<p class="rc-note">In the hunt: ${hunt.map((h) => `${escapeHtml(rcNflName(h.team))} ${escapeHtml(h.record)}${
          h.back != null ? ` (${h.back > 0 ? `${h.back} back` : "level"})` : ""}`).join(", ")}.</p>` : ""}</div>`;
    }).join("")}</div>`;
}

/* One conference's race: every club, best chance first, each one's games
   left at our price under it. */
function rcNflTeamsHTML(d, c) {
  const ch = d.chances || {}, rem = d.remaining || {};
  const rows = (d.teams || []).filter((r) => r.conference === c && ch[r.team]);
  if (!rows.length) return "";
  return `<div class="rc-card rc-flush">
    <div class="rc-conf-h">${c}</div>
    <div class="rc-row rc-head"><span>Team</span><span>In</span><span>Div</span><span>No. 1</span><span>Title</span></div>
    ${rows.map((r) => {
      const x = ch[r.team];
      const games = rem[r.team] || [];
      return `<details class="rc-team">
        <summary class="rc-row">
          <span class="rc-who">${teamMarkIn("nfl", r.team, 22)}<span><b>${escapeHtml(rcNflName(r.team))}</b>
            <small>${escapeHtml(r.record)} · ${escapeHtml(r.division)}</small></span></span>
          <span class="rc-p rc-lead">${rcPct(x.playoffs)}</span><span class="rc-p">${rcPct(x.division)}</span>
          <span class="rc-p">${rcPct(x.bye)}</span><span class="rc-p">${rcPct(x.title)}</span></summary>
        <div class="rc-games">
          ${games.length ? games.map((g) => `<span class="rc-game">Wk ${g.week} · ${g.home ? "vs" : g.neutral ? "vs" : "at"}
            ${escapeHtml(rcNflName(g.opp))} <b class="${g.p >= 0.5 ? "pos" : "neg"}">${rcPct(g.p)}</b></span>`).join("")
            : `<span class="rc-game">No regular-season games left.</span>`}
          <p class="rc-note">Projected ${x.proj ? `${x.proj[0]}–${x.proj[1]}` : "—"}${
            x.seed != null ? ` · average seed ${x.seed} when in` : ""} · wins its conference ${rcPct(x.conference)}.</p>
        </div></details>`;
    }).join("")}
  </div>`;
}

/* The week's games that move the field most, with each club they move —
   its chance to get in either way the game goes, the better way green. */
function rcNflSwingHTML(d) {
  const sw = d.swing || [];
  if (!sw.length) return "";
  return `<div class="section-title">The games that swing it
      <span class="sub">— week ${escapeHtml(String(d.week || ""))}’s games that move the field most: each club’s chance to make it, either way the game goes.</span></div>
    <div class="rc-grid">${sw.map((g) => `<div class="rc-card">
      <div class="rc-sw-h">${teamMarkIn("nfl", g.away, 20)}<b>${escapeHtml(rcNflName(g.away))}</b>
        ${g.neutral ? "vs" : "at"} ${teamMarkIn("nfl", g.home, 20)}<b>${escapeHtml(rcNflName(g.home))}</b></div>
      <p class="rc-note">${escapeHtml(rcDay(g.date))} · ${escapeHtml(rcNflName(g.home))} ${rcPct(g.p_home)} to win</p>
      <div class="rc-row rc-sw rc-head"><span>To get in</span><span>${escapeHtml(rcNflName(g.home))} win</span>
        <span>${escapeHtml(rcNflName(g.away))} win</span></div>
      ${(g.moves || []).map((m) => `<div class="rc-row rc-sw"><span class="rc-who"><span>${escapeHtml(rcNflName(m.team))}</span></span>
        <span class="rc-p ${m.if_home > m.if_away ? "pos" : "neg"}">${rcPct(m.if_home)}</span>
        <span class="rc-p ${m.if_away > m.if_home ? "pos" : "neg"}">${rcPct(m.if_away)}</span></div>`).join("")}
    </div>`).join("")}</div>`;
}

/* The eight divisions, in the order the tiebreakers stand them. */
function rcNflStandingsHTML(d) {
  const st = d.standings || {};
  const divs = Object.keys(st);
  if (!divs.length) return "";
  return `<div class="section-title">The divisions
      <span class="sub">— in tiebreaker order; the leader of each takes a top-four seed.</span></div>
    <div class="rc-grid">${divs.map((k) => `<div class="rc-card rc-flush">
      <div class="rc-conf-h">${escapeHtml(k)}</div>
      <div class="rc-row rc-crow rc-head"><span>Team</span><span>W-L</span><span>Div</span><span>Conf</span><span>Diff</span></div>
      ${st[k].map((r, i) => {
        const diff = (r.pf || 0) - (r.pa || 0);
        return `<div class="rc-row rc-crow${i === 0 ? " rc-lead-row" : ""}"><span class="rc-who">${teamMarkIn("nfl", r.team, 18)}
          <span>${escapeHtml(rcNflName(r.team))}</span></span>
          <span class="rc-p">${escapeHtml(r.record)}</span><span class="rc-p">${escapeHtml(r.div)}</span>
          <span class="rc-p">${escapeHtml(r.conf)}</span>
          <span class="rc-p rc-pd ${diff > 0 ? "pos" : diff < 0 ? "neg" : ""}">${diff > 0 ? "+" : ""}${diff}</span></div>`;
      }).join("")}</div>`).join("")}</div>`;
}

function nflHTML(d) {
  const locked = rcLocked(d);
  return `<p class="rc-note rc-lede">Week ${escapeHtml(String(d.week || "—"))} next · ${plural(d.games_played || 0, "game")} played,
      ${d.games_left || 0} left in the regular season.</p>
    ${rcNflSeedsHTML(d)}
    ${locked ? memberLockHTML("Our chances are for members",
      "Every club’s chance to make the playoffs, win its division, take the 1 seed and win the Super Bowl — each game it has left at our price, and the week’s games that swing the field.")
      : `<div class="section-title">The race
          <span class="sub">— each club’s chances: in the playoffs, the division, the 1 seed, the Super Bowl. Tap a club for its games left.</span></div>
        <div class="rc-grid">${RC_NFL_CONFS.map((c) => rcNflTeamsHTML(d, c)).join("")}</div>${rcNflSwingHTML(d)}`}
    ${rcNflStandingsHTML(d)}
    <p class="rc-note">Ties in the standings are broken by ${escapeHtml(d.tiebreakers || "the league’s own steps")}.
      ${locked ? "" : `Each game left is played at our win chance off the same ratings as the Futures page; they stay where
      they are for the rest of the season, and no game is drawn as a tie. The playoffs are played out too: the Wild Card round
      at the higher seed, the divisional round reseeded, the Super Bowl on neutral ground.`}
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

/* THE KNOCKOUT ROUNDS (engine/nbacup.bracket, 2026-11-03; Ethan, on the
   audit's "NBA Cup knockout bracket": "do all of them"). Each conference's
   quarterfinals (1 v 4 and 2 v 3, at the higher seed) and its semifinal (the
   winners, at the better seed's arena), then the final in Indianapolis —
   the scores as they land, the winner of each game in bold, the champion
   on top once there is one. While group play runs it is the bracket if it
   ended today. Our line on each game still to play is a member's
   (`bracket_lines`, emptied for anyone else). */
function cupSide(d, team, seed, score, won, tbd) {
  if (!team) return `<div class="rc-side rc-empty"><span></span><span></span><span class="rc-name">${escapeHtml(tbd)}</span></div>`;
  return `<div class="rc-side${won === true ? " rc-won" : won === false ? " rc-lost" : ""}">${teamMarkIn("nba", team, 22)}
    <span class="rc-seed">${seed || ""}</span><b class="rc-name">${escapeHtml(((d.names || {})[team]) || team)}</b>
    ${score != null ? `<span class="rc-score">${escapeHtml(String(score))}</span>` : ""}</div>`;
}
function cupGameHTML(d, g, tbd) {
  if (!g) return "";
  const nm = (t) => ((d.names || {})[t]) || t;
  const line = (d.bracket_lines || {})[g.id];
  const where = g.site === "home" ? (g.home && g.away ? `at ${nm(g.home)}` : "at the better seed")
    : `in ${g.site}`;
  return `<div class="rc-match rc-ko${g.done ? " rc-done" : ""}">
    ${cupSide(d, g.home, g.home_seed, g.home_score, g.done ? g.winner === g.home : null, tbd[0])}
    ${cupSide(d, g.away, g.away_seed, g.away_score, g.done ? g.winner === g.away : null, tbd[1])}
    <span class="rc-host">${escapeHtml(rcDay(g.date))} · ${escapeHtml(where)}${g.done ? " · final score" : ""}${
      line && !g.done ? ` · our line ${escapeHtml(nm(g.home))} <b>${rcPct(line.p_home)}</b>` : ""}</span></div>`;
}
function cupBracketHTML(d) {
  const b = d.bracket || {};
  const confs = b.conferences || {};
  if (!confs.East || !confs.West) return "";
  const nights = b.nights || {};
  const span = (k) => (nights[k] || []).map(rcDay).join(" – ");
  const nm = (t) => ((d.names || {})[t]) || t;
  const champ = b.champion;
  return `<div class="section-title">${b.set ? "The knockout rounds" : "If group play ended today"}
      <span class="sub">— ${b.set
        ? "the eight, the quarterfinals at the higher seed, each semifinal at the better seed’s arena, the final in Indianapolis."
        : "each conference’s group winners seeded by record, its wild card fourth; the quarterfinals at the higher seed."}</span></div>
    ${champ ? `<div class="rc-card rc-champ">${teamMarkIn("nba", champ, 28)}<b>${escapeHtml(nm(champ))} win the NBA Cup</b></div>` : ""}
    ${["East", "West"].map((c) => `<div class="rc-conf-k">${c}</div>
      <div class="rc-brk">
        <div class="rc-col"><div class="rc-col-h">Quarterfinals · ${escapeHtml(span("quarterfinals"))}</div>
          ${confs[c].quarterfinals.map((g) => cupGameHTML(d, g, ["", ""])).join("")}</div>
        <div class="rc-col"><div class="rc-col-h">Semifinal · ${escapeHtml(span("semifinals"))}</div>
          ${cupGameHTML(d, confs[c].semifinal, ["Winner of 1 v 4", "Winner of 2 v 3"])}</div>
      </div>`).join("")}
    <div class="rc-conf-k">The final · ${escapeHtml(span("final"))}</div>
    <div class="rc-brk">${cupGameHTML(d, b.final, ["East champion", "West champion"])}</div>`;
}

function cupHTML(d) {
  const locked = rcLocked(d);
  // Once group play is over the bracket leads the page; before, it follows
  // the groups as the bracket if group play ended today.
  const set = !!((d.bracket || {}).set);
  const g = d.groups || {};
  const ko = d.knockouts || {};
  const win = d.window || [];
  const started = (d.played || 0) > 0;
  return `<p class="rc-note rc-lede">${started ? `${plural(d.played, "group game")} played, ${d.games_left} left` : "Group play has not started"}
      · group nights ${escapeHtml(rcDay(win[0]))} – ${escapeHtml(rcDay(win[1]))} · quarterfinals ${escapeHtml(rcDay(ko.quarterfinals))}
      and semifinals ${escapeHtml(rcDay(ko.semifinals))} at the better seed’s arena · the final ${escapeHtml(rcDay(ko.final))}, Indianapolis.</p>
    ${set ? cupBracketHTML(d) : ""}
    <div class="section-title">The groups
      <span class="sub">— each group’s winner goes through, and the best of the rest in each conference.</span></div>
    <div class="rc-grid">${Object.entries(g).map(([name, rows]) => cupGroupHTML(name, rows, d, locked)).join("")}</div>
    <div class="section-title">The wild card race
      <span class="sub">— no head-to-head here: record, then point differential, then points.</span></div>
    <div class="rc-grid">${cupWildHTML(d)}</div>
    ${set ? "" : cupBracketHTML(d)}
    <div class="rc-card"><b>How a tie is broken</b>
      <ol class="rc-tb">${(d.tiebreakers || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ol>
      <p class="rc-note">A group game that goes to overtime counts zero in the differential, so a team cannot run it up
        in extra time — and its overtime points count toward nothing.</p></div>
    ${locked ? memberLockHTML("Our chances are for members",
      "Every team’s chance to win its group, take the wild card, reach the final and win the Cup — every group game left at our price and margin, and our line on every knockout game.")
      : cupOddsHTML(d)}
    ${d.generated_at ? `<p class="rc-note">Built ${escapeHtml(String(d.generated_at).replace("T", " ").slice(0, 16))}.</p>` : ""}`;
}
