/* THE RACES (Ethan, 2026-10-29: "do all 3"; the NFL's, 2026-11-03: "do all
   of them"; college basketball's, 2026-11-14: "make it like nba cup ... I
   want all the features like this is a complete sport") — the NFL's and
   college football's playoff races, the NBA Cup and the NCAA tournament,
   one page each league, loaded the first time it
   opens (app.js loadRoom). A classic script like app.js: it shares the
   page's globals, and `renderRace` here replaces app.js's stub.

   WHAT IS WHOSE. The field if it started today, the standings and the
   point differentials are facts — the poll, the scoreboard — and every
   reader of the file gets them. The chances, each game left at our price
   and the games that swing the race are our model's, and a reader without
   a plan is served the file with them emptied (engine/gate,
   PAID_KEYS_BY_FILE); the page says what is behind them, never a number. */

const RACE_FILES = { nfl: "nfl_race.json", cfb: "cfp_race.json", nba: "nba_cup.json", cbb: "ncaa_race.json" };
const RACE_TITLES = { nfl: "NFL playoff race", cfb: "College Football Playoff race", nba: "NBA Cup",
                      cbb: "NCAA tournament" };

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
      <p>The race pages are the NFL’s and college football’s playoffs, the NBA Cup and the NCAA tournament.</p></div>`;
    return;
  }
  host.innerHTML = `<div class="rc-wait" role="status">Loading the race…</div>`;
  const d = await rcLoad(file);
  if (state.view !== "race" || state.sport !== sport) return;
  if (!d || (!d.today && !d.groups)) {
    host.innerHTML = `<div class="empty-slate"><h3>The race has not been built yet</h3>
      <p>${sport === "cbb"
        ? "It is played out on the college basketball build once the season’s schedule has been read off the scoreboard; the next one fills this page."
        : `It is played out on every ${sport === "nba" ? "NBA" : sport === "nfl" ? "NFL" : "college"} build; the next one fills this page.`}</p></div>`;
    return;
  }
  if (sub) sub.textContent = sport === "cbb"
    ? ((d.bracket || {}).set
      ? `— the 68 the committee named. Our ratings play the bracket out ${Number(d.sims || 0).toLocaleString()} times.`
      : `— 68 teams: every conference’s champion and the committee’s at-large picks. Our ratings play the rest of the season ${Number(d.sims || 0).toLocaleString()} times.`)
    : sport === "nba"
    ? `— the groups, the differential tiebreaker and our chances, ${Number(d.sims || 0).toLocaleString()} tournaments played out.`
    : sport === "nfl"
      ? `— 14 teams, 7 a conference. Our ratings play the rest of the season ${Number(d.sims || 0).toLocaleString()} times.`
      : (d.bracket || {}).set
        ? `— the twelve the committee named. Our game model plays the playoff out ${Number(d.sims || 0).toLocaleString()} times.`
        : `— 12 teams. Our game model plays the rest of the season ${Number(d.sims || 0).toLocaleString()} times.`;
  host.innerHTML = sport === "nba" ? cupHTML(d) : sport === "nfl" ? nflHTML(d) : sport === "cbb" ? ncaaHTML(d) : cfpHTML(d);
}

/* ---------------- college football ---------------- */

/* ---------------- a bracket, drawn as one ----------------
   BRACKET1 (2026-11-17; Ethan, on the NFL playoff race's seed lists: "the
   playoff page should be layed out as a bracket and not this chart"). The
   rounds left to right, each game a card centred beside the games that feed
   it, a line from each to the game it feeds, the way a bracket is read. A
   round is {title, groups}: each group the games that feed one game of the
   next round, two, or one where a seed waits on a single winner. A side is
   {team, seed, name, meta} or {tbd, meta}: who is not known yet is said in
   words ("Lowest seed left"), never guessed. A mirrored bracket (the NFC,
   beside the AFC where there is room) runs right to left (race.css
   .rc-bk-mirror). */
function rcBkSide(sport, s) {
  const meta = s && s.meta ? `<small>${escapeHtml(s.meta)}</small>` : "";
  if (!s || !s.team) {
    return `<div class="rc-bk-side rc-bk-tbd"><i class="rc-bk-dot" aria-hidden="true"></i><span class="rc-bk-who"><b>${
      escapeHtml((s && s.tbd) || "To be decided")}</b>${meta}</span></div>`;
  }
  const done = s.won === true ? " rc-bk-won" : s.won === false ? " rc-bk-lost" : "";
  const mine = rcFollows(sport, s.team);
  return `<div class="rc-bk-side${done}${mine ? " rc-bk-mine" : ""}">${teamMarkIn(sport, s.team, 20)}<span class="rc-bk-who"><b><span class="rc-bk-seed">${
    escapeHtml(String(s.seed || ""))}</span>${escapeHtml(s.name || s.team)}${
    mine ? `<span class="rc-bk-star" title="A team you follow" aria-label="a team you follow">★</span>` : ""}</b>${meta}</span>${
    s.score != null ? `<span class="rc-bk-score">${escapeHtml(String(s.score))}</span>` : ""}</div>`;
}
/* A game: its two sides, and under them, when it has one, its note (the
   night, the site, the final, our line), already escaped by its maker. */
function rcBkGameHTML(sport, g) {
  return `<div class="rc-bk-game${g.done ? " rc-bk-done" : ""}">${(g.sides || []).map((x) => rcBkSide(sport, x)).join("")}${
    g.note ? `<div class="rc-bk-note">${g.note}</div>` : ""}</div>`;
}
/* A KNOCKOUT GAME OFF THE ENGINE (cfprace's and nbacup's bracket): each side
   its club, seed and score, the winner marked once it is final, who is not
   known yet in words (`tbd`, home's then away's); and under it the night, the
   site, "final score" once played, and our line on it while it is still to
   play (a member's: the free copy carries no bracket_lines). */
function rcKoGame(sport, d, g, tbd, nm, where) {
  if (!g) return { sides: [{ tbd: tbd[0] }, { tbd: tbd[1] }] };
  const side = (team, seed, score, i) => (team
    ? { team, seed, name: nm(team), score, won: g.done ? g.winner === team : null }
    : { tbd: tbd[i] || "To be decided" });
  const line = (d.bracket_lines || {})[g.id];
  const note = [g.date ? escapeHtml(rcDay(g.date)) : "", where ? escapeHtml(where) : "", g.done ? "final score" : "",
    line && !g.done ? `our line ${escapeHtml(nm(g.home))} <b>${rcPct(line.p_home)}</b>` : ""].filter(Boolean).join(" · ");
  return { done: !!g.done, note, sides: [side(g.home, g.home_seed, g.home_score, 0), side(g.away, g.away_seed, g.away_score, 1)] };
}

function rcBkRoundsHTML(sport, rounds, mirror) {
  return `<div class="rc-bk-scroll"><div class="rc-bk-rounds${mirror ? " rc-bk-mirror" : ""}">${rounds.map((r) => `<div class="rc-bk-col">
      <div class="rc-bk-colh">${escapeHtml(r.title)}</div>
      <div class="rc-bk-games">${r.groups.map((grp) => `<div class="rc-bk-pair${grp.length === 1 ? " rc-bk-one" : ""}">${
        grp.map((g) => rcBkGameHTML(sport, g)).join("")}</div>`).join("")}</div></div>`).join("")}</div></div>`;
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
  const side = (n) => {
    const s = by[n];
    return s ? { team: s.team, seed: n, name: s.name, meta: [s.rank ? `#${s.rank}` : "", s.record].filter(Boolean).join(" · ") }
      : { tbd: `The ${n} seed` };
  };
  // Each bye seed meets this first-round game's winner (engine/cfprace QUARTERS), drawn in the
  // order the semifinals pair them (SEMIS): 1 with 4's side, 2 with 3's.
  const meets = { 1: [8, 9], 2: [7, 10], 3: [6, 11], 4: [5, 12] };
  const order = [1, 4, 2, 3];
  const first = (n) => fr.find(([x, y]) => meets[n].includes(x) && meets[n].includes(y)) || meets[n];
  const rounds = [
    { title: "First round", groups: order.map((n) => {
        const [x, y] = first(n);
        return [{ sides: [side(x), side(y)] }];
      }) },
    { title: "Quarterfinals", groups: [[1, 4], [2, 3]].map((pair) => pair.map((n) => ({
        sides: [side(n), { tbd: `${meets[n].join("/")} winner` }] }))) },
    { title: "Semifinals", groups: [[[1, 4], [2, 3]].map((pair) => ({
        sides: pair.map((n) => ({ tbd: `${n} v ${meets[n].join("/")} winner` })) }))] },
    { title: "National title", groups: [[{ sides: [{ tbd: "Semifinal winner" }, { tbd: "Semifinal winner" }] }]] },
  ];
  const poll = (d.poll || {}).name || "the poll";
  const out = (t.first_four_out || []).map((x) => `${escapeHtml(x.name || x.team)}${x.rank ? ` (#${x.rank})` : ""}`).join(", ");
  return `<div class="section-title">If it started today
      <span class="sub">— ${escapeHtml(poll)} as the ranking, today’s conference leaders as the champions.</span></div>
    <div class="rc-bk-wrap"><div class="rc-bk rc-bk-solo">
      <section class="rc-bk-conf" aria-label="The College Football Playoff if it started today">${rcBkRoundsHTML("cfb", rounds)}</section>
    </div></div>
    <p class="rc-note">The top four seeds wait out the first round; 5 through 12 play it on the better seed’s campus,
      and the quarterfinals on are in the bowls.${out ? ` First four out: ${out}.` : ""}</p>`;
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
function cfpPlayoffHTML(d, locked) {
  const b = d.bracket || {};
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
  // The bracket as the engine plays it (engine/cfprace QUARTERS, SEMIS): the 1 and 4 seeds' sides meet in
  // one semifinal and the 2 and 3 seeds' in the other, so the quarterfinals are drawn in that order, each
  // with the first-round game that feeds it beside it.
  const where = (g) => (g.neutral ? (g.bowl || "neutral site") : (g.home ? `at ${nm(g.home)}` : "at the higher seed"));
  const game = (g, tbd) => rcKoGame("cfb", d, g, tbd, nm, g ? where(g) : "");
  const qs = [0, 3, 1, 2].map((k) => qf[k]).filter(Boolean);
  const feeds = (q) => fr.find((x) => x.id === ((q.from || [])[0]));
  const rounds = [
    { title: "First round", groups: qs.map((q) => [game(feeds(q), ["", ""])]) },
    { title: "Quarterfinals",
      groups: [qs.slice(0, 2), qs.slice(2)].map((pair) => pair.map((q) => game(q, ["", frLabel((q.from || [])[0])]))) },
    { title: "Semifinals",
      groups: [sf.map((g) => game(g, ["Quarterfinal winner", "Quarterfinal winner"]))] },
    { title: "National championship",
      groups: [[game(b.final, ["Semifinal winner", "Semifinal winner"])]] },
  ];
  return `${b.champion ? `<div class="rc-card rc-champ">${teamMarkIn("cfb", b.champion, 28)}<b>${escapeHtml(nm(b.champion))} win the national championship</b></div>` : ""}
    <div class="section-title">The College Football Playoff
      <span class="sub">— the twelve the committee named on selection day, seeded by its final ranking; the first round on the higher seed’s campus, the rest in the bowls.</span></div>
    <div class="rc-bk-wrap"><div class="rc-bk rc-bk-solo">
      <section class="rc-bk-conf" aria-label="The College Football Playoff">${rcBkRoundsHTML("cfb", rounds)}</section>
    </div></div>
    <div class="rc-card"><b>The twelve</b>
      <ol class="rc-tb rc-twelve">${(b.seeds || []).map((s) => `<li>${escapeHtml(s.name || s.team)} <small>${escapeHtml(s.record || "")} · ${escapeHtml(s.bid || "")}</small></li>`).join("")}</ol></div>
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

/* IF THE SEASON ENDED TODAY, AS A BRACKET (BRACKET1, 2026-11-17; Ethan: "the
   playoff page should be layed out as a bracket and not this chart"). Each
   conference's seven as the playoffs run: the 1 seed's bye, then 4 v 5, 3 v 6
   and 2 v 7 at the better seed; the divisional round; the conference's title
   game; and the Super Bowl between the two. The rounds after the first say
   who meets whom, not who wins: the divisional round is reseeded, the 1 seed
   at home to the lowest seed left and the other two winners at the better
   seed's, so its games are said that way. AFC on the left and the NFC
   mirrored on the right where there is room, one above the other on a phone;
   then the clubs just outside and how far back of the seventh they are. */
/* YOUR TEAMS ON THE BRACKET (2026-11-17): a team you follow (Settings, or
   the star on its page) is lit wherever the bracket draws it, and the NFL's
   race says first where each of yours stands: its seed if the season ended
   today, how far back of the 7 seed, and, for a member, its chance to get in. */
function rcFollows(sport, team) {
  return !!team && typeof isFavTeam === "function" && isFavTeam(team, sport);
}
function rcNflMineHTML(d) {
  const mine = (typeof settings === "function" ? settings().teams || [] : [])
    .filter((k) => String(k).startsWith("nfl:")).map((k) => String(k).slice(4));
  const t = d.today || {};
  const rows = mine.map((team) => {
    let where = "";
    for (const c of RC_NFL_CONFS) {
      const s = ((t[c] || {}).seeds || []).find((x) => x.team === team);
      const h = ((t[c] || {}).hunt || []).find((x) => x.team === team);
      if (s) where = `the ${c}’s ${s.seed} seed if the season ended today`;
      else if (h && h.back != null) where = h.back > 0 ? `${h.back} game${h.back === 1 ? "" : "s"} back of the ${c}’s 7 seed`
        : `level with the ${c}’s 7 seed, out on the tiebreaker`;
      if (where) break;
    }
    const ch = ((d.chances || {})[team] || {}).playoffs;
    const odds = ch != null ? `, ${rcPct(ch)} to make the playoffs` : "";
    return where || odds ? `<li>${teamMarkIn("nfl", team, 20)}<span><b>${escapeHtml(rcNflName(team))}</b>: ${
      escapeHtml(where || "outside the race today")}${odds}</span></li>` : "";
  }).filter(Boolean);
  return rows.length ? `<div class="rc-card rc-mine"><b>Your teams</b><ul class="rc-mine-list">${rows.join("")}</ul></div>` : "";
}
function rcNflSeedSide(s) {
  if (!s) return { tbd: "Seed open" };
  const why = String(s.why || "").replace(/^(AFC|NFC)\s+/, "");
  return { team: s.team, seed: s.seed, name: rcNflName(s.team), meta: `${s.record} · ${why}` };
}
function rcNflSeedsHTML(d) {
  const t = d.today || {};
  const conf = (c) => {
    const by = {};
    ((t[c] || {}).seeds || []).forEach((s) => { by[s.seed] = s; });
    const rounds = [
      { title: "Wild Card", groups: [
          [{ sides: [rcNflSeedSide(by[1]), { tbd: "Bye", meta: "rests this round" }] },
           { sides: [rcNflSeedSide(by[4]), rcNflSeedSide(by[5])] }],
          [{ sides: [rcNflSeedSide(by[3]), rcNflSeedSide(by[6])] },
           { sides: [rcNflSeedSide(by[2]), rcNflSeedSide(by[7])] }]] },
      { title: "Divisional", groups: [[
          { sides: [by[1] ? { team: by[1].team, seed: 1, name: rcNflName(by[1].team), meta: "at home" } : { tbd: "The 1 seed" },
                    { tbd: "Lowest seed left" }] },
          { sides: [{ tbd: "Wild Card winner" }, { tbd: "Wild Card winner" }] }]] },
      { title: `${c} title game`, groups: [[{ sides: [{ tbd: "Divisional winner" }, { tbd: "Divisional winner" }] }]] },
    ];
    return `<section class="rc-bk-conf rc-bk-${c === "AFC" ? "l" : "r"}" aria-label="${escapeHtml(`${c} if the season ended today`)}">
      <div class="rc-bk-k">${c}</div>${rcBkRoundsHTML("nfl", rounds, c === "NFC")}</section>`;
  };
  const hunt = RC_NFL_CONFS.map((c) => {
    const h = (t[c] || {}).hunt || [];
    // "Back" is games behind the 7 seed (engine/nflrace back()); said in full once, then short.
    const back = (b, first) => (b == null ? "" : b > 0 ? `, ${b} game${b === 1 ? "" : "s"} back${first ? " of the 7 seed" : ""}`
      : `, level${first ? " with the 7 seed" : ""}`);
    return h.length ? `<p class="rc-note"><b>Just outside in the ${c}:</b> ${h.map((x, i) =>
      `${escapeHtml(rcNflName(x.team))} ${escapeHtml(x.record)}${back(x.back, !i)}`).join("; ")}.</p>` : "";
  }).join("");
  return `<div class="section-title">If the season ended today
      <span class="sub">— the four division leaders seeded 1–4, then the three best records left. Only the 1 seed rests the first weekend.</span></div>
    <div class="rc-bk-wrap"><div class="rc-bk">
      ${conf("AFC")}
      <section class="rc-bk-c" aria-label="The Super Bowl"><div class="rc-bk-k">Super Bowl</div>${rcBkRoundsHTML("nfl",
        [{ title: "Neutral site", groups: [[{ sides: [{ tbd: "AFC champion" }, { tbd: "NFC champion" }] }]] }])}</section>
      ${conf("NFC")}
    </div></div>
    <p class="rc-note">Every game is at the better seed’s home until the Super Bowl. The divisional round is reseeded:
      the 1 seed hosts the lowest seed left, and the other two winners meet.</p>
    ${hunt}`;
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
    ${rcNflMineHTML(d)}
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
function cupBracketHTML(d) {
  const b = d.bracket || {};
  const confs = b.conferences || {};
  if (!confs.East || !confs.West) return "";
  const nm = (t) => ((d.names || {})[t]) || t;
  const champ = b.champion;
  const where = (g) => (g.site === "home" ? (g.home && g.away ? `at ${nm(g.home)}` : "at the better seed") : `in ${g.site}`);
  const game = (g, tbd) => rcKoGame("nba", d, g, tbd, nm, g ? where(g) : "");
  // Each conference's side: its two quarterfinals (1 v 4, 2 v 3) feeding its semifinal; the West mirrors the
  // East across the final where there is room (race.css .rc-bk-mirror).
  const half = (c) => `<section class="rc-bk-conf rc-bk-${c === "East" ? "l" : "r"}" aria-label="The ${c}">
      <div class="rc-bk-k">${c}</div>${rcBkRoundsHTML("nba", [
        { title: "Quarterfinals",
          groups: [confs[c].quarterfinals.map((g) => game(g, ["", ""]))] },
        { title: "Semifinal",
          groups: [[game(confs[c].semifinal, ["Winner of 1 v 4", "Winner of 2 v 3"])]] }], c === "West")}</section>`;
  return `<div class="section-title">${b.set ? "The knockout rounds" : "If group play ended today"}
      <span class="sub">— ${b.set
        ? "the eight, the quarterfinals at the higher seed, each semifinal at the better seed’s arena, the final in Indianapolis."
        : "each conference’s group winners seeded by record, its wild card fourth; the quarterfinals at the higher seed."}</span></div>
    ${champ ? `<div class="rc-card rc-champ">${teamMarkIn("nba", champ, 28)}<b>${escapeHtml(nm(champ))} win the NBA Cup</b></div>` : ""}
    <div class="rc-bk-wrap"><div class="rc-bk">${half("East")}
      <section class="rc-bk-c" aria-label="The final"><div class="rc-bk-k">The final</div>${rcBkRoundsHTML("nba",
        [{ title: "Championship", groups: [[game(b.final, ["East champion", "West champion"])]] }])}</section>
      ${half("West")}</div></div>`;
}

function cupHTML(d) {
  const locked = rcLocked(d);
  // Once group play is over the bracket leads the page; before, it follows
  // the groups as the bracket if group play ended today.
  const set = !!((d.bracket || {}).set);
  const g = d.groups || {};
  const ko = d.knockouts || {};
  // Each round's nights, both of a two-night round (the bracket's own).
  const nights = (d.bracket || {}).nights || {};
  const span = (k) => ((nights[k] || []).length ? nights[k] : [ko[k]]).filter(Boolean).map(rcDay).join(" – ");
  const win = d.window || [];
  const started = (d.played || 0) > 0;
  return `<p class="rc-note rc-lede">${started ? `${plural(d.played, "group game")} played, ${d.games_left} left` : "Group play has not started"}
      · group nights ${escapeHtml(rcDay(win[0]))} – ${escapeHtml(rcDay(win[1]))} · quarterfinals ${escapeHtml(span("quarterfinals"))}
      and semifinals ${escapeHtml(span("semifinals"))} at the better seed’s arena · the final ${escapeHtml(rcDay(ko.final))}, Indianapolis.</p>
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

/* ---------------- college basketball: the NCAA tournament ----------------
   Ethan, 2026-11-14: "make it like nba cup and shit I want all the features
   like this is a complete sport." engine/ncaarace plays the season out: the
   field if it ended today, the bubble and the conference races are free;
   each school's chances, its games ahead at our price, the games that swing
   the field and our line on every tournament game are members'. From
   selection Sunday the page is the bracket itself, off the scoreboard. */

/* A school's name as a reader knows it ("Duke", not "Blue Devils"): the
   board's table first (every school a build has seen), then the race's own
   names, then the code. */
function ncNm(d, t) {
  if (!t) return "";
  const c = ((typeof teamsForSport === "function" && teamsForSport("cbb")) || {})[t];
  return (c && (c.short || c.name)) || ((d && d.names) || {})[t] || String(t);
}

/* One school on a projected region's line: its mark, its seed, its name
   (a poll rank before it), "auto" for today's automatic bid, its record. A
   First Four pair is both schools on one line. */
function ncLine(d, rows, seed) {
  if (!rows || !rows.length) return `<div class="rc-reg-l rc-empty"><span></span><span class="rc-seed">${seed}</span><span class="rc-name">—</span><small></small></div>`;
  if (rows.length > 1) {
    const [a, b] = rows;
    return `<div class="rc-reg-l">${teamMarkIn("cbb", a.team, 20)}<span class="rc-seed">${seed}</span>
      <span class="rc-name">${escapeHtml(ncNm(d, a.team))} / ${escapeHtml(ncNm(d, b.team))}<span class="rc-tag">First Four</span></span>
      <small><span class="rc-rec">${escapeHtml(a.record || "")}</span> · <span class="rc-rec">${escapeHtml(b.record || "")}</span></small></div>`;
  }
  const r = rows[0];
  return `<div class="rc-reg-l">${teamMarkIn("cbb", r.team, 20)}<span class="rc-seed">${seed}</span>
    <span class="rc-name">${r.rank ? `<small>#${r.rank}</small> ` : ""}${escapeHtml(ncNm(d, r.team))}${
      r.bid === "auto" ? `<span class="rc-tag">auto</span>` : ""}</span>
    <small class="rc-rec">${escapeHtml(r.record || "")}</small></div>`;
}

/* THE FIELD IF THE SEASON ENDED TODAY: four regions, each named for its 1
   seed (the committee names the real ones on selection Sunday), each with
   its eight first-round games in bracket order, one line a school. */
function ncFieldHTML(d) {
  const t = d.today || {};
  const rows = t.field || [];
  if (!rows.length) return "";
  const by = [{}, {}, {}, {}];
  rows.forEach((r) => {
    if (r.region == null || !r.seed || !by[r.region]) return;
    (by[r.region][r.seed] = by[r.region][r.seed] || []).push(r);
  });
  const fr = (d.format || {}).first_round || [[1, 16], [8, 9], [5, 12], [4, 13], [6, 11], [3, 14], [7, 10], [2, 15]];
  const tops = t.region_tops || [];
  const auto = (d.format || {}).auto || 0;
  return `<div class="section-title">If the season ended today
      <span class="sub">— ${auto} conference leaders as the automatic bids (“auto”), the rest at large by our selection score, seeded on the S-curve.</span></div>
    <div class="rc-grid">${[0, 1, 2, 3].map((i) => `<div class="rc-card rc-flush">
      <div class="rc-conf-h">${tops[i] ? `${escapeHtml(ncNm(d, tops[i]))}’s region` : `Region ${i + 1}`}</div>
      <div class="rc-reg">${fr.map(([a, b]) => `<div class="rc-reg-m">${ncLine(d, by[i][a], a)}${ncLine(d, by[i][b], b)}</div>`).join("")}</div>
    </div>`).join("")}</div>`;
}

function ncBubbleHTML(d) {
  const t = d.today || {};
  const list = (title, rows) => (rows && rows.length) ? `<div class="rc-card"><b>${title}</b>
    <ol class="rc-tb">${rows.map((r) => `<li>${escapeHtml(ncNm(d, r.team))} <small>${escapeHtml(r.record || "")} · ${
      escapeHtml(r.conf || "")}</small></li>`).join("")}</ol></div>` : "";
  const body = list("Last four in", t.last_four_in) + list("First four out", t.first_four_out) + list("Next four out", t.next_four_out);
  return body ? `<div class="section-title">The bubble
      <span class="sub">— either side of the cut today. The last four in play the First Four in Dayton.</span></div>
    <div class="rc-grid">${body}</div>` : "";
}

/* THE CONTENDERS: every school in today's field and the likeliest of the
   rest, each one's chances, and under it its next games at our price. The
   first NC_SHOWN are open; the rest — mostly one-bid leagues' hopefuls,
   each at its conference's automatic bid — fold under one line. */
const NC_SHOWN = 36;
function ncTeamsHTML(d) {
  const ch = d.chances || {}, rem = d.remaining || {};
  const rows = (d.teams || []).filter((r) => ch[r.team]);
  if (!rows.length) return "";
  const one = (r) => {
        const c = ch[r.team];
        const games = rem[r.team] || [];
        return `<details class="rc-team">
          <summary class="rc-row">
            <span class="rc-who">${teamMarkIn("cbb", r.team, 22)}<span><b>${r.rank ? `#${r.rank} ` : ""}${escapeHtml(ncNm(d, r.team))}</b>
              <small><span class="rc-rec">${escapeHtml(r.record)}</span> · ${escapeHtml(r.conf || "")} <span class="rc-rec">${
                escapeHtml(r.conf_record || "")}</span></small></span></span>
            <span class="rc-p rc-lead">${rcPct(c.field)}</span><span class="rc-p">${rcPct(c.top4)}</span>
            <span class="rc-p">${rcPct(c.s16)}</span><span class="rc-p">${rcPct(c.f4)}</span>
            <span class="rc-p">${rcPct(c.title)}</span></summary>
          <div class="rc-games">
            ${games.length ? games.map((g) => `<span class="rc-game">${escapeHtml(rcDay(g.date))} ·
              ${g.home || g.neutral ? "vs" : "at"} ${escapeHtml(ncNm(d, g.opp))}
              <b class="${g.p >= 0.5 ? "pos" : "neg"}">${rcPct(g.p)}</b></span>`).join("")
              : `<span class="rc-game">No regular-season games left.</span>`}
            <p class="rc-note">Projected ${c.proj ? `${c.proj[0]}–${c.proj[1]}` : "—"}${
              c.conf_proj ? `, ${c.conf_proj[0]}–${c.conf_proj[1]} in its conference` : ""} · its conference’s automatic bid ${rcPct(c.auto)}${
              c.seed != null ? ` · average seed ${c.seed} when in` : ""}.</p>
          </div></details>`;
  };
  const shown = rows.slice(0, NC_SHOWN), rest = rows.slice(NC_SHOWN);
  return `<div class="section-title">The contenders
      <span class="sub">— each school’s chance to make the field, earn a top-four seed, reach the Sweet 16 (S16) and the Final Four (F4) and win it all. Tap a school.</span></div>
    <div class="rc-card rc-flush">
      <div class="rc-row rc-head"><span>School</span><span>Field</span><span>Top 4</span><span>S16</span><span>F4</span><span>Title</span></div>
      ${shown.map(one).join("")}
      ${rest.length ? `<details class="rc-more"><summary>Every other school with a chance (${rest.length})</summary>
        ${rest.map(one).join("")}</details>` : ""}
    </div>`;
}

/* THE GAMES THAT SWING IT: the coming days' games that move the field
   most, each school they move and its chance either way, the better way
   green — a team not in the game is listed only when the move is too big
   for chance (engine/ncaarace.swings). */
function ncSwingHTML(d) {
  const sw = d.swing || [];
  if (!sw.length) return "";
  return `<div class="section-title">The games that swing it
      <span class="sub">— the next few days’ games that move the bubble most: each school’s chance to make the field, either way the game goes.</span></div>
    <div class="rc-grid">${sw.map((g) => `<div class="rc-card">
      <div class="rc-sw-h">${teamMarkIn("cbb", g.away, 20)}<b>${escapeHtml(ncNm(d, g.away))}</b>
        ${g.neutral ? "vs" : "at"} ${teamMarkIn("cbb", g.home, 20)}<b>${escapeHtml(ncNm(d, g.home))}</b></div>
      <p class="rc-note">${escapeHtml(rcDay(g.date))} · ${escapeHtml(ncNm(d, g.home))} ${rcPct(g.p_home)} to win</p>
      <div class="rc-row rc-sw rc-head"><span>To make the field</span><span>${escapeHtml(ncNm(d, g.home))} win</span>
        <span>${escapeHtml(ncNm(d, g.away))} win</span></div>
      ${(g.moves || []).map((m) => `<div class="rc-row rc-sw"><span class="rc-who"><span>${escapeHtml(ncNm(d, m.team))}</span></span>
        <span class="rc-p ${m.if_home > m.if_away ? "pos" : "neg"}">${rcPct(m.if_home)}</span>
        <span class="rc-p ${m.if_away > m.if_home ? "pos" : "neg"}">${rcPct(m.if_away)}</span></div>`).join("")}
    </div>`).join("")}</div>`;
}

/* EVERY CONFERENCE'S RACE: its schools by conference record, today's leader
   (or, once its tournament is played, its champion) marked; for a member,
   each school's chance at the automatic bid. Folded, one line each. */
function ncConfHTML(d, locked) {
  const cs = d.conferences || {};
  const keys = Object.keys(cs);
  if (!keys.length) return "";
  const bids = d.bids || {};
  return `<div class="section-title">The conference races
      <span class="sub">— by conference record. Every conference’s tournament champion goes in automatically.</span></div>
    ${keys.map((k) => {
      const c = cs[k];
      const lead = c.champion || c.leader;
      return `<details class="rc-card rc-flush rc-conf">
        <summary class="rc-conf-h">${escapeHtml(c.name || k)}${lead ? ` · ${c.champion ? "champion" : "leads"}: ${escapeHtml(ncNm(d, lead))}` : ""}${
          c.auto_bid === false ? " · no automatic bid" : ""}</summary>
        <div class="rc-row rc-crow rc-head"><span>School</span><span>Conf</span><span>All</span>${locked ? "" : "<span>Bid</span>"}</div>
        ${(c.teams || []).map((r, i) => `<div class="rc-row rc-crow${r.team === lead ? " rc-lead-row" : ""}">
          <span class="rc-who">${teamMarkIn("cbb", r.team, 18)}<span>${i + 1}. ${r.rank ? `#${r.rank} ` : ""}${escapeHtml(ncNm(d, r.team))}${
            r.out ? "<small>out of its tournament</small>" : ""}</span></span>
          <span class="rc-p">${escapeHtml(r.conf_record)}</span><span class="rc-p">${escapeHtml(r.record)}</span>${
          locked ? "" : `<span class="rc-p">${r.team === c.champion ? "in" : rcPct(bids[r.team] || 0)}</span>`}</div>`).join("")}
      </details>`;
    }).join("")}`;
}

/* ONE BRACKET GAME: both schools with their seeds and, once it is played,
   the score with the winner bold; our line on a game still to play is a
   member's. A side not yet decided says where it comes from. */
function ncSlotSide(d, team, seed, score, won, tbd) {
  if (!team) return `<div class="rc-side rc-empty"><span></span><span class="rc-seed">${seed || ""}</span><span class="rc-name">${escapeHtml(tbd || "To be decided")}</span></div>`;
  return `<div class="rc-side${won === true ? " rc-won" : won === false ? " rc-lost" : ""}">${teamMarkIn("cbb", team, 22)}
    <span class="rc-seed">${seed || ""}</span><b class="rc-name">${escapeHtml(ncNm(d, team))}</b>
    ${score != null ? `<span class="rc-score">${escapeHtml(String(Math.round(score)))}</span>` : ""}</div>`;
}
function ncSlotHTML(d, s, tbd, where) {
  if (!s) return "";
  const line = s.id ? (d.bracket_lines || {})[s.id] : null;
  const done = !!s.w;
  const note = [where || "", s.date ? rcDay(s.date) : "", done ? "final score" : ""].filter(Boolean).join(" · ");
  return `<div class="rc-match rc-ko${done ? " rc-done" : ""}">
    ${ncSlotSide(d, s.a, s.sa, s.as, done ? s.w === s.a : null, (tbd || [])[0])}
    ${ncSlotSide(d, s.b, s.sb, s.bs, done ? s.w === s.b : null, (tbd || [])[1])}
    ${note || (line && !done) ? `<span class="rc-host">${escapeHtml(note)}${
      line && !done ? `${note ? " · " : ""}our line ${escapeHtml(ncNm(d, line.home))} <b>${rcPct(line.p_home)}</b>` : ""}</span>` : ""}</div>`;
}

/* THE BRACKET, FROM SELECTION SUNDAY: the First Four, each region's four
   rounds, the Final Four and the title game, every result as it lands and
   the champion on top; then each school's chance to go on, for members. */
function ncBracketHTML(d, locked) {
  const b = d.bracket || {};
  const nights = d.nights || {};
  const span = (k) => [].concat(nights[k] || []).map(rcDay).join(" – ");
  const ROUND = [["r64", "First round"], ["r32", "Second round"], ["s16", "Sweet 16"], ["e8", "Elite Eight"]];
  const ch = d.chances || {};
  const seeds = b.seeds || {};
  const alive = Object.keys(seeds).filter((t) => ch[t]).sort((x, y) => (ch[y].title || 0) - (ch[x].title || 0)
    || (ch[y].f4 || 0) - (ch[x].f4 || 0));
  const odds = locked ? memberLockHTML("Our chances are for members",
      "Each school’s chance to reach the second round, the Sweet 16, the Elite Eight and the Final Four and to win it all — and our line on every tournament game still to play.")
    : `<div class="section-title">Our chances
        <span class="sub">— each of the 68 to reach each round and win it all, every result in kept.</span></div>
      <div class="rc-card rc-flush">
        <div class="rc-row rc-head"><span>School</span><span>R32</span><span>S16</span><span>E8</span><span>F4</span><span>Title</span></div>
        ${alive.map((t) => {
          const c = ch[t];
          return `<div class="rc-row"><span class="rc-who">${teamMarkIn("cbb", t, 20)}<span><b>${seeds[t][0]} ${escapeHtml(ncNm(d, t))}</b>
            <small>${escapeHtml(seeds[t][1])}</small></span></span>
            <span class="rc-p">${rcPct(c.r32)}</span><span class="rc-p">${rcPct(c.s16)}</span><span class="rc-p">${rcPct(c.e8)}</span>
            <span class="rc-p">${rcPct(c.f4)}</span><span class="rc-p rc-lead">${rcPct(c.title)}</span></div>`;
        }).join("")}
      </div>`;
  const semis = b.semis || [];
  return `${b.champion ? `<div class="rc-card rc-champ">${teamMarkIn("cbb", b.champion, 28)}<b>${escapeHtml(ncNm(d, b.champion))} win the national championship</b></div>` : ""}
    ${(b.first_four || []).length ? `<div class="section-title">The First Four · ${escapeHtml(span("first_four"))}
        <span class="sub">— in Dayton; each winner takes its place in the first round.</span></div>
      <div class="rc-grid">${b.first_four.map((s) => ncSlotHTML(d, s, null, `${s.region || ""} ${s.sa} seed`.trim())).join("")}</div>` : ""}
    ${(b.regions || []).map((reg) => `<div class="section-title">The ${escapeHtml(reg.name)} region</div>
      <div class="rc-brk">${reg.rounds.map((rnd, k) => `<div class="rc-col"><div class="rc-col-h">${ROUND[k][1]} · ${escapeHtml(span(ROUND[k][0]))}</div>
        ${rnd.map((s) => ncSlotHTML(d, s, k ? ["Winner of the game before", "Winner of the game before"] : ["First Four winner", "First Four winner"])).join("")}</div>`).join("")}</div>`).join("")}
    <div class="section-title">The Final Four · ${escapeHtml(d.site || "")}
      <span class="sub">— ${semis.length ? semis.map((p) => `${escapeHtml(p[0])} against ${escapeHtml(p[1])}`).join(", ") : ""}${
        b.semis_from === "ours" ? " (our reading of the committee’s order until the scoreboard lists the games)" : ""}.</span></div>
    <div class="rc-brk">
      <div class="rc-col"><div class="rc-col-h">National semifinals · ${escapeHtml(span("f4"))}</div>
        ${(b.final_four || []).map((s, i) => ncSlotHTML(d, s, semis[i] ? [`${semis[i][0]} champion`, `${semis[i][1]} champion`] : [])).join("")}</div>
      <div class="rc-col"><div class="rc-col-h">National championship · ${escapeHtml(span("final"))}</div>
        ${ncSlotHTML(d, b.final, ["Semifinal winner", "Semifinal winner"])}</div>
    </div>
    ${odds}`;
}

function ncNoteHTML(d, locked) {
  const a = d.assumptions || {};
  const built = d.generated_at ? ` Built ${escapeHtml(String(d.generated_at).replace("T", " ").slice(0, 16))}.` : "";
  return `<p class="rc-note">The 2026–27 tournament: 68 teams, every Division I conference’s tournament champion and
      the committee’s at-large picks, seeded 1–16 in four regions; the First Four in Dayton, then six rounds to the
      title game in ${escapeHtml(d.site || "the Final Four’s city")}. ${locked ? "" : `Our selection score is a stand-in for the
      committee: our rating plus ${a.resume_points || 1.5} points for every win above what the
      ${a.bubble_rank || 45}th-best team would manage against the same schedule. On the last three seasons it named 104 of
      the 110 teams the committee took at large and seeded the field within 0.7 of a line on average. Conference
      tournaments not yet played are stood in for by each conference’s top eight, and the committee’s rule against early
      meetings of conference rivals is not modelled.`}${d.prior && d.prior.schools === 0
        ? " Last season’s games are not on the box yet, so every school started this season even."
        : ""}${built}</p>`;
}

function ncaaHTML(d) {
  const locked = rcLocked(d);
  if (d.bracket && d.bracket.set) return ncBracketHTML(d, locked) + ncConfHTML(d, locked) + ncNoteHTML(d, locked);
  const nt = d.nights || {};
  return `<p class="rc-note rc-lede">${plural(d.played || 0, "game")} played, ${Number(d.games_left || 0).toLocaleString()} left
      before the conference tournaments · Selection Sunday ${escapeHtml(rcDay(nt.selection))} · the Final Four
      ${escapeHtml(rcDay([].concat(nt.f4 || [])[0]))}${d.site ? `, ${escapeHtml(d.site)}` : ""}.</p>
    ${ncFieldHTML(d)}
    ${ncBubbleHTML(d)}
    ${locked ? memberLockHTML("Our chances are for members",
      "Every contender’s chance to make the field, earn a top-four seed, reach the Sweet 16 and the Final Four and win it all — each game it has ahead at our price, every school’s chance at its conference’s automatic bid, and the games that swing the bubble.")
      : ncTeamsHTML(d) + ncSwingHTML(d)}
    ${ncConfHTML(d, locked)}
    ${ncNoteHTML(d, locked)}`;
}
